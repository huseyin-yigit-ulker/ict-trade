"""DB-backed lifecycle state for live positions — persistence + clientOrderId + result writeback.

live_positions rows live in the LIVE db (ict_trade.signals' connection). This module is the only
writer of that table: it creates positions idempotently (UNIQUE act-once), reads the open set,
patches fields/state, appends to the live_orders forensic log, and on CLOSE upserts the result
into ict_trade.trading_signals (version='d30so8c') via tsc.build_row/upsert_rows — so a live
trade lands on the exact same dashboard curve as its backtest twin.

The reconcile LOGIC (which orders should exist in each state) lives in executor.py; this module
only persists. clientOrderIds are deterministic — f"so8-{pos_id}-{leg}-{gen}" — so a crashed
reconciler re-derives the exact same ids and never double-places.
"""
from __future__ import annotations

import sys
import json
from pathlib import Path

import pandas as pd
from psycopg2.extras import Json

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))                    # live_exec -> _bootenv
sys.path.insert(0, str(_HERE.parents[1]))                # sync/     -> trade_sync_common
sys.path.insert(0, str(_HERE.parents[1] / "donchian"))   # donchian  -> scaleout
import os                                    # noqa: E402
import _bootenv                              # noqa: E402,F401  -- sets DCH_SO_RUNNER_CAP before scaleout
import trade_sync_common as tsc              # noqa: E402
import scaleout as _so                       # noqa: E402

# Version tag for live result writeback to trading_signals. EXEC_VERSION (.env) overrides so the live
# bridge records under the strategy it ACTUALLY runs (e.g. 'd30so8f3h7' = close_frac 0.3 + 7d), which
# the so.VERSION cap-derived tag can't express (it only encodes the runner cap). Default = so.VERSION
# (cap8 -> d30so8c, cap6 -> d30so6c). NEW positions tag with this; on CLOSE a position's OWN stored
# version is used (so changing it mid-stream never re-tags still-open older positions).
VERSION = (tsc._read_env().get("EXEC_VERSION") or os.environ.get("EXEC_VERSION") or _so.VERSION)

# lifecycle states (also referenced by the partial-unique open-symbol index in schema.sql)
PENDING_ENTRY = "PENDING_ENTRY"      # signal accepted, entry order to be / is placed
ENTRY_WORKING = "ENTRY_WORKING"      # entry order live on the book, unfilled
OPEN_FULL = "OPEN_FULL"              # entry filled, before +1R (full SL + TP1 working)
RUNNER = "RUNNER"                    # TP1 booked, 40% runner (BE-stop + cap working)
CLOSING = "CLOSING"                  # exit detected, legs being reaped
CLOSED = "CLOSED"
CANCELLED = "CANCELLED"              # entry never filled within the window

OPEN_STATES = (PENDING_ENTRY, ENTRY_WORKING, OPEN_FULL, RUNNER, CLOSING)
RISK_STATES = (OPEN_FULL, RUNNER)    # states where a protective stop MUST exist on the exchange


def coid(pos_id: int, leg: str, gen: int = 0) -> str:
    """Deterministic clientOrderId. gen bumps when a leg is legitimately re-placed (e.g. BE-stop
    after TP1) so the new order isn't rejected as a -4015 duplicate of the cancelled one."""
    return f"so8-{pos_id}-{leg}-{gen}"


# DUAL-MODE act-once insert. The legacy env path (user_id=None) keeps the ORIGINAL column set
# and conflict target so the currently-armed single-user executor is bit-identical until the
# Phase-5 cutover; the multi-user path targets the 005b per-user index (user_id, network,
# symbol, signal_time, direction, version) NULLS NOT DISTINCT. The two are mutually exclusive
# with the index swap: legacy insert works only pre-005b, user insert only post-005b — which is
# exactly the EXEC_MULTI_USER flip done inside the same halt window as 005b.
_INSERT_LEGACY = """
INSERT INTO ict_trade.live_positions
  (symbol, signal_time, version, direction, side, entry_mode,
   signal_entry, signal_sl, signal_cap, risk0,
   eff_entry, eff_sl, eff_tp1, eff_be, eff_cap,
   qty, tp1_qty, leverage, state, entry_deadline, context)
VALUES (%s,%s,%s,%s,%s,%s, %s,%s,%s,%s, %s,%s,%s,%s,%s, %s,%s,%s,%s,%s,%s)
ON CONFLICT (symbol, signal_time, direction, version) DO NOTHING
RETURNING id
"""

_INSERT_USER = """
INSERT INTO ict_trade.live_positions
  (user_id, network, symbol, signal_time, version, direction, side, entry_mode,
   signal_entry, signal_sl, signal_cap, risk0,
   eff_entry, eff_sl, eff_tp1, eff_be, eff_cap,
   qty, tp1_qty, leverage, state, entry_deadline, context)
VALUES (%s,%s, %s,%s,%s,%s,%s,%s, %s,%s,%s,%s, %s,%s,%s,%s,%s, %s,%s,%s,%s,%s,%s)
ON CONFLICT (user_id, network, symbol, signal_time, direction, version) DO NOTHING
RETURNING id
"""


def create_position(conn, *, symbol, signal_time, direction, side, entry_mode,
                    lv, qty, tp1_qty, leverage, entry_deadline, context=None,
                    user_id=None, network=None) -> int | None:
    """Idempotent insert (act-once on the signal tuple, per user+network). Returns the new id,
    or None if the signal already produced a position (duplicate emit) — caller skips."""
    st = signal_time.to_pydatetime() if isinstance(signal_time, pd.Timestamp) else signal_time
    common = (
        symbol, st, VERSION, direction.upper(), side, entry_mode,
        lv.entry_close, lv.sl, lv.cap, lv.risk0,
        lv.eff_entry, lv.sl, lv.tp1, lv.be, lv.cap,
        qty, tp1_qty, leverage, PENDING_ENTRY,
        entry_deadline.to_pydatetime() if isinstance(entry_deadline, pd.Timestamp) else entry_deadline,
        Json(context or {}),
    )
    cur = conn.cursor()
    if user_id is None:
        cur.execute(_INSERT_LEGACY, common)
    else:
        cur.execute(_INSERT_USER, (user_id, network) + common)
    row = cur.fetchone()
    conn.commit()
    cur.close()
    return int(row[0]) if row else None


def _user_scope(q: str, params: list, user_id, network) -> str:
    """Append the per-user filter. user_id=None = legacy single-tenant (no filter)."""
    if user_id is not None:
        q += " AND user_id = %s"
        params.append(user_id)
        if network is not None:
            q += " AND network = %s"
            params.append(network)
    return q


def fetch_open(conn, symbols=None, *, user_id=None, network=None) -> list[dict]:
    """All positions in an OPEN state (optionally restricted to `symbols` and one user/network)."""
    cur = conn.cursor()
    q = "SELECT * FROM ict_trade.live_positions WHERE state = ANY(%s)"
    params: list = [list(OPEN_STATES)]
    if symbols:
        q += " AND symbol = ANY(%s)"
        params.append(list(symbols))
    q = _user_scope(q, params, user_id, network)
    q += " ORDER BY symbol, signal_time"
    cur.execute(q, tuple(params))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


def open_symbols(conn, *, user_id=None, network=None) -> set[str]:
    cur = conn.cursor()
    q = "SELECT DISTINCT symbol FROM ict_trade.live_positions WHERE state = ANY(%s)"
    params: list = [list(OPEN_STATES)]
    q = _user_scope(q, params, user_id, network)
    cur.execute(q, tuple(params))
    out = {r[0] for r in cur.fetchall()}
    cur.close()
    return out


def patch(conn, pos_id: int, **fields) -> None:
    """Update arbitrary columns on a position row (always bumps updated_at)."""
    if not fields:
        return
    fields = dict(fields)
    for k, v in list(fields.items()):
        if isinstance(v, pd.Timestamp):
            fields[k] = v.to_pydatetime()
        elif isinstance(v, dict):
            fields[k] = Json(v)
    sets = ", ".join(f"{k} = %s" for k in fields) + ", updated_at = current_timestamp"
    cur = conn.cursor()
    cur.execute(f"UPDATE ict_trade.live_positions SET {sets} WHERE id = %s",
                tuple(fields.values()) + (pos_id,))
    conn.commit()
    cur.close()


def log_order(conn, *, position_id, symbol, leg, action, client_order_id=None,
              order_id=None, payload=None, user_id=None) -> None:
    cur = conn.cursor()
    if user_id is None:            # legacy shape — safe even before 005a added the column
        cur.execute("""
            INSERT INTO ict_trade.live_orders
              (position_id, symbol, leg, action, client_order_id, order_id, payload)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (position_id, symbol, leg, action, client_order_id, order_id,
              Json(payload) if payload is not None else None))
    else:
        cur.execute("""
            INSERT INTO ict_trade.live_orders
              (position_id, symbol, leg, action, client_order_id, order_id, payload, user_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (position_id, symbol, leg, action, client_order_id, order_id,
              Json(payload) if payload is not None else None, user_id))
    conn.commit()
    cur.close()


def total_open_risk_usd(conn, risk_usd_per_trade: float, *, user_id=None, network=None) -> float:
    """Summed risk of currently-open positions (each ≈ one risk_usd unit). Cheap proxy used by
    the executor + safety sweep to enforce MAX_TOTAL_RISK_USD without re-pricing every stop."""
    cur = conn.cursor()
    q = "SELECT count(*) FROM ict_trade.live_positions WHERE state = ANY(%s)"
    params: list = [list(OPEN_STATES)]
    q = _user_scope(q, params, user_id, network)
    cur.execute(q, tuple(params))
    n = int(cur.fetchone()[0])
    cur.close()
    return n * risk_usd_per_trade


def writeback_trading_signals(bt_conn, pos: dict) -> None:
    """On close, upsert the live result into ict_trade.trading_signals (version='d30so8c') so it
    joins the dashboard track-record. Maps live_positions -> the tsc.build_row contract."""
    direction = pos["direction"]
    reason = pos.get("exit_reason")
    pnl = pos.get("realized_r")
    if reason in ("entry_expired", "reversed") and not pos.get("entry_fill_time"):
        status = "cancelled"                                # never entered
    elif reason == "sl":
        status = "closed_sl"
    elif reason:                                            # tp1_be/cap/breakeven/time_stop/reversed/closed_externally
        status = "closed_sl" if (pnl is not None and float(pnl) < 0) else "closed_tp"
    else:
        status = pos.get("state")
    outcome = {
        "status": status,
        "real_entry_time": pos.get("entry_fill_time"),
        "exit_time": pos.get("exit_time"),
        "exit_price": float(pos["exit_px"]) if pos.get("exit_px") is not None else None,
        "pnl_r": float(pos["realized_r"]) if pos.get("realized_r") is not None else None,
    }
    row = tsc.build_row(
        pos["symbol"], pos["signal_time"], direction,
        float(pos.get("eff_entry") or pos["signal_entry"]),
        float(pos["signal_sl"]), float(pos["signal_cap"]), outcome,
        strategy=(pos.get("context") or {}).get("strategy") if isinstance(pos.get("context"), dict) else None,
    )
    row["version"] = pos.get("version") or VERSION   # the position's OWN cap, not the current one
    tsc.upsert_rows(bt_conn, [row])
