"""DB-backed lifecycle state for TALOS-ICHI live positions — persistence + clientOrderId + writeback.

talos_ichi_positions rows live in the LIVE db (ict_trade.signals' connection). This module is the ONLY
writer of that table: it creates positions idempotently (UNIQUE act-once), reads the open set,
patches fields/state, appends to the talos_ichi_orders forensic log, and on CLOSE upserts the result into
ict_trade.trading_signals (version='talos_ichix', context-aware) so a live TALOS-ICHI trade lands on the
dashboard — distinct from the paper 'talos_ichi' curve that the nightly backfill rewrites.

The reconcile LOGIC lives in executor.py; this module only persists. clientOrderIds are deterministic
— f"tix-{pos_id}-{leg}-{gen}" — so a crashed reconciler re-derives the exact same ids and never
double-places.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from psycopg2.extras import Json, execute_values

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))                # sync/ -> trade_sync_common
import trade_sync_common as tsc                           # noqa: E402

# lifecycle states (also referenced by the partial-unique open-symbol index in schema.sql)
PENDING_ENTRY = "PENDING_ENTRY"      # signal accepted, maker entry not yet resting
ENTRY_WORKING = "ENTRY_WORKING"      # maker LIMIT (GTX) resting on the book, unfilled
OPEN = "OPEN"                        # entry filled, chandelier trailing in force
CLOSED = "CLOSED"
CANCELLED = "CANCELLED"              # entry never filled within the window (or slipped past)

OPEN_STATES = (PENDING_ENTRY, ENTRY_WORKING, OPEN)


def coid(pos_id: int, leg: str, gen: int = 0) -> str:
    """Deterministic clientOrderId. gen bumps when a leg is legitimately re-placed (e.g. the resting
    stop trailed to a new level) so the new order isn't rejected as a -4015 duplicate of the old one."""
    return f"tix-{pos_id}-{leg}-{gen}"


# DUAL-MODE act-once insert. The legacy env path (user_id=None) keeps the ORIGINAL column set
# and conflict target (schema.sql's uq_talos_ichi_positions_key) so the currently-armed single-user
# executor is bit-identical until the Phase-5 cutover; the multi-user path targets the 005b
# per-user index (user_id, network, symbol, signal_time, direction, version) NULLS NOT DISTINCT.
# The two are mutually exclusive with the index swap: legacy insert works only pre-005b, user
# insert only post-005b — which is exactly the EXEC_MULTI_USER flip done inside the same halt
# window as 005b.
_INSERT_LEGACY = """
INSERT INTO ict_trade.talos_ichi_positions
  (symbol, signal_time, version, direction, side,
   signal_entry, signal_sl, risk0, cur_sl, qty, leverage, state, entry_deadline, context)
VALUES (%s,%s,%s,%s,%s, %s,%s,%s,%s,%s,%s,%s,%s,%s)
ON CONFLICT (symbol, signal_time, direction, version) DO NOTHING
RETURNING id
"""

_INSERT_USER = """
INSERT INTO ict_trade.talos_ichi_positions
  (user_id, network, symbol, signal_time, version, direction, side,
   signal_entry, signal_sl, risk0, cur_sl, qty, leverage, state, entry_deadline, context)
VALUES (%s,%s, %s,%s,%s,%s,%s, %s,%s,%s,%s,%s,%s,%s,%s,%s)
ON CONFLICT (user_id, network, symbol, signal_time, direction, version) DO NOTHING
RETURNING id
"""


def create_position(conn, *, symbol, signal_time, direction, side, signal_entry, signal_sl,
                    risk0, qty, leverage, entry_deadline, version, context=None,
                    user_id=None, network=None) -> int | None:
    """Idempotent insert (act-once on the signal tuple, per user+network). Returns the new id, or
    None if the signal already produced a position (duplicate/re-read, or a previously cancelled
    attempt) — caller skips."""
    st = signal_time.to_pydatetime() if isinstance(signal_time, pd.Timestamp) else signal_time
    common = (
        symbol, st, version, direction.upper(), side,
        float(signal_entry), float(signal_sl), float(risk0), float(signal_sl),
        qty, leverage, PENDING_ENTRY,
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
    """Append the per-user filter. user_id=None = legacy single-tenant (no filter — the SQL never
    references the 005a columns, so it is safe before the migration lands)."""
    if user_id is not None:
        q += " AND user_id = %s"
        params.append(user_id)
        if network is not None:
            q += " AND network = %s"
            params.append(network)
    return q


def fetch_open(conn, symbols=None, *, user_id=None, network=None) -> list[dict]:
    """All TALOS-ICHI positions in an OPEN state (optionally restricted to `symbols` and one user/network)."""
    cur = conn.cursor()
    q = "SELECT * FROM ict_trade.talos_ichi_positions WHERE state = ANY(%s)"
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


def reload(conn, pos_id: int) -> dict:
    cur = conn.cursor()
    cur.execute("SELECT * FROM ict_trade.talos_ichi_positions WHERE id = %s", (pos_id,))
    cols = [d[0] for d in cur.description]
    row = dict(zip(cols, cur.fetchone()))
    cur.close()
    return row


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
    cur.execute(f"UPDATE ict_trade.talos_ichi_positions SET {sets} WHERE id = %s",
                tuple(fields.values()) + (pos_id,))
    conn.commit()
    cur.close()


def log_order(conn, *, position_id, symbol, leg, action, client_order_id=None,
              order_id=None, payload=None, user_id=None) -> None:
    cur = conn.cursor()
    if user_id is None:            # legacy shape — safe even before 005a added the column
        cur.execute("""
            INSERT INTO ict_trade.talos_ichi_orders
              (position_id, symbol, leg, action, client_order_id, order_id, payload)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (position_id, symbol, leg, action, client_order_id, order_id,
              Json(payload) if payload is not None else None))
    else:
        cur.execute("""
            INSERT INTO ict_trade.talos_ichi_orders
              (position_id, symbol, leg, action, client_order_id, order_id, payload, user_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (position_id, symbol, leg, action, client_order_id, order_id,
              Json(payload) if payload is not None else None, user_id))
    conn.commit()
    cur.close()


def count_open(conn, symbols=None, *, user_id=None, network=None) -> int:
    cur = conn.cursor()
    q = "SELECT count(*) FROM ict_trade.talos_ichi_positions WHERE state = ANY(%s)"
    params: list = [list(OPEN_STATES)]
    if symbols:
        q += " AND symbol = ANY(%s)"
        params.append(list(symbols))
    q = _user_scope(q, params, user_id, network)
    cur.execute(q, tuple(params))
    n = int(cur.fetchone()[0])
    cur.close()
    return n


# ---- writeback to the dashboard (context-aware; version='talos_ichix') -------------------------------
# tsc.upsert_rows drops `context`, so TALOS-ICHI needs its own upsert that carries the trailing-stop path
# jsonb — the exact shape ChartModal / TradeContext render for a TALOS-ICHI trade. Mirrors
# sync/talos_ichi/backfill._CTX_UPSERT so the live 'talos_ichix' rows and the paper 'talos_ichi' rows are identical
# in structure (only the version tag + the real fills differ).
_CTX_COLS = tsc._COLS + ["context"]
_CTX_UPSERT = f"""
INSERT INTO {tsc.TABLE} ({", ".join(_CTX_COLS)}) VALUES %s
ON CONFLICT (symbol, signal_time, trade_type, version) DO UPDATE SET
  status=EXCLUDED.status, real_entry_time=EXCLUDED.real_entry_time, exit_time=EXCLUDED.exit_time,
  exit_price=EXCLUDED.exit_price, pnl_r=EXCLUDED.pnl_r, signal_price=EXCLUDED.signal_price,
  entry_price=EXCLUDED.entry_price, sl_price=EXCLUDED.sl_price, tp_price=EXCLUDED.tp_price,
  strategy=EXCLUDED.strategy, quality=EXCLUDED.quality, confluence_score=EXCLUDED.confluence_score,
  context=EXCLUDED.context
"""


def writeback_trading_signals(bt_conn, pos: dict) -> None:
    """On close, upsert the live TALOS-ICHI result into ict_trade.trading_signals (version = the position's
    own tag, e.g. 'talos_ichix') with the trailing-stop context, so it joins the dashboard track-record."""
    ctx = pos.get("context")
    if isinstance(ctx, str):
        import json
        try:
            ctx = json.loads(ctx)
        except (ValueError, TypeError):
            ctx = {}
    ctx = ctx or {}

    reason = pos.get("exit_reason")
    pnl = pos.get("realized_r")
    if reason in ("unfilled", "slipped") and not pos.get("entry_fill_time"):
        status = "cancelled"                                # never entered
    else:
        status = "closed_sl" if (pnl is not None and float(pnl) < 0) else "closed_tp"

    entry = float(pos.get("eff_entry") or pos["signal_entry"])
    sl = float(pos["signal_sl"])
    tp_ref = float(ctx.get("tp_ref") or pos.get("exit_px") or entry)   # UI nominal line (no fixed R:R)
    outcome = {
        "status": status,
        "real_entry_time": pos.get("entry_fill_time"),
        "exit_time": pos.get("exit_time"),
        "exit_price": float(pos["exit_px"]) if pos.get("exit_px") is not None else None,
        "pnl_r": float(pos["realized_r"]) if pos.get("realized_r") is not None else None,
    }
    row = tsc.build_row(pos["symbol"], pos["signal_time"], pos["direction"], entry, sl, tp_ref,
                        outcome, strategy=(ctx.get("strategy") or "TALOS-ICHI Keltner-Trend (live, Binance)"),
                        quality="TREND", confluence_score=None)
    row["version"] = pos.get("version") or "talos_ichix"
    row["context"] = {
        "kind": "trailing", "init_sl": float(ctx.get("init_sl") or sl),
        "trail_mult": ctx.get("trail_mult", 3.5), "atr_mult": ctx.get("atr_mult", 1.5),
        "trail": ctx.get("trail") or [], "pos": "closed",
        "exit_px": pos.get("exit_px"), "pnl_r": pos.get("realized_r"), "live": True,
    }
    vals = [tuple(Json(row[c]) if c == "context" else row[c] for c in _CTX_COLS)]
    cur = bt_conn.cursor()
    execute_values(cur, _CTX_UPSERT, vals, page_size=1)
    bt_conn.commit()
    cur.close()
