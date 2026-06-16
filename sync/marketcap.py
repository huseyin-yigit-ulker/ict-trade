"""Crypto market-cap regime map — TOTAL / TOTAL2 / TOTAL3 breadth context.

The mirror of sync/regime.py, but at the MARKET level instead of the per-symbol
level. Where regime.py asks "is THIS symbol trending or chopping?" (Efficiency
Ratio), this module asks "is the whole crypto market in risk-on or risk-off?"
using the three aggregate market-cap series TradingView calls TOTAL/2/3:

    TOTAL   = total crypto market cap                       (BTC-led, whole market)
    TOTAL2  = TOTAL - BTC                                   ("everything but BTC")
    TOTAL3  = TOTAL - BTC - ETH                             (pure altcoin appetite)

Why this is a regime map and NOT a trade stream: like regime.py it produces a
per-bar series + an at-or-before lookup; gates/analyses consume it. It is wired to
nothing live until sync/marketcap_analysis.py shows it adds ORTHOGONAL value over
the ER bands (the project has been burned by 2026-in-sample overfits before —
KARMA, regime-sizing — so this ships as a lookup + an OOS-aware audit, not a gate).

TWO data layers
---------------
1. PROXY series (historical, available now, backtest-safe): cap_i(t) = Binance
   4h close_i(t) x circulating_supply_i, summed over the top non-stable coins.
   Reuses the klines we already fetch -> no new lookahead surface beyond slow
   supply drift (supplies are ~constant over a backtest window; we snapshot them
   once and cache). This is a RISK-ASSET cap proxy (stablecoins excluded), which
   is what you want for a risk-on/off read anyway.

2. LIVE snapshot (ground truth, accrues forward): CoinGecko /global gives the
   exact TOTAL in USD plus BTC/ETH dominance, from which TOTAL2/TOTAL3 follow
   precisely. snapshot_live() appends one row per call to out/marketcap_live.csv;
   wire it into the daily sync and the real series builds itself over time.

Missing data -> permissive (never over-filter on absence), same contract as
regime.py.

EMPIRICAL FINDING (sync/marketcap_analysis.py, 2026 in-sample + 2025 OOS)
------------------------------------------------------------------------
Breadth IS orthogonal to ER — it splits R *within* an ER band. The one
OOS-ROBUST pocket is the LIGHT ER band (where most of our R lives):

    light + risk_on  : avg R  -0.23 (2026)  /  -0.42 (2025)   <- consistently BAD
    light + neutral  : avg R  +0.98 (2026)  /  +0.02 (2025)   <- consistently best

i.e. a fast-RISING TOTAL3 (risk_on euphoria) is a HEADWIND for these entries —
the opposite of the naive "trade with risk-on" prior. The strong/chop risk_off
effects seen in 2026 INVERT in 2025 (in-sample noise), so do NOT gate on those.

No clean profitable GATE ships from this: the streams where the pocket is
strongest (MAIN/OPUS) are net-negative OOS anyway, and the one profitable stream
(RANGE) shows no robust breadth edge. So this stays a regime-map LOOKUP + a live
monitor — use riskon helpers for research/sizing studies, not as a hard gate,
until a stream shows OOS lift from them. (Mind the direction: the robust headwind
is risk_ON, not risk_off — riskon_ok below is the GENERIC primitive, not a
recommendation.)
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import trade_sync_common as tsc

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "sync" / "out"
SUPPLY_CACHE = OUT / "marketcap_supplies.json"
LIVE_CSV = OUT / "marketcap_live.csv"

CG_GLOBAL = "https://api.coingecko.com/api/v3/global"
CG_MARKETS = "https://api.coingecko.com/api/v3/coins/markets"

# Top non-stable coins by mcap that trade as <SYM>USDT perps on Binance — enough
# to track the SLOPE of TOTAL/2/3 (we care about direction, not the absolute USD
# level). Stablecoins are intentionally excluded: a flat ~11% of TOTAL that only
# damps the risk signal. Supplies are pulled live (fetch_supplies) but this is the
# universe we sum over.
PROXY_COINS = [
    "BTC", "ETH", "BNB", "XRP", "SOL", "DOGE", "ADA", "TRX", "LINK", "AVAX",
    "SUI", "NEAR", "LTC", "DOT", "ARB", "FET", "ONDO", "ORDI", "WIF", "PEPE",
]
STABLES = {"USDT", "USDC", "DAI", "FDUSD", "TUSD", "USDE", "BUSD"}

_AGG = {"open": "first", "high": "max", "low": "min", "close": "last"}

# --- regime thresholds (4h bars). Deliberately conservative; TUNE + OOS-validate
# via marketcap_analysis.py before trusting these as a gate. ---------------------
EMA_SPAN = 10        # 4h EMA of TOTAL3 (~1.7 days) — smooths the breadth line
SLOPE_N = 6          # bars back for the slope read (~1 day)
SLOPE_EPS = 0.005    # |Δ| below this = flat/neutral (0.5% over SLOPE_N bars)


# ---------------------------------------------------------------- supplies (cache)
def fetch_supplies(refresh: bool = False) -> dict[str, float]:
    """{BINANCE_SYMBOL: circulating_supply} for PROXY_COINS, cached to disk.

    One CoinGecko call; cached because supplies drift slowly. Pass refresh=True to
    re-pull. Binance symbol = COIN + 'USDT' (matches our universe; 1000PEPE handled)."""
    if SUPPLY_CACHE.exists() and not refresh:
        return json.loads(SUPPLY_CACHE.read_text())
    r = requests.get(CG_MARKETS, params={
        "vs_currency": "usd", "order": "market_cap_desc",
        "per_page": 100, "page": 1}, timeout=20)
    r.raise_for_status()
    want = set(PROXY_COINS)
    out: dict[str, float] = {}
    for c in r.json():
        sym = (c.get("symbol") or "").upper()
        sup = c.get("circulating_supply")
        if sym in want and sup:
            out[_binance_symbol(sym)] = float(sup)
    OUT.mkdir(parents=True, exist_ok=True)
    SUPPLY_CACHE.write_text(json.dumps(out, indent=2, sort_keys=True))
    return out


def _binance_symbol(coin: str) -> str:
    """CoinGecko coin symbol -> Binance perp symbol (PEPE trades as 1000PEPEUSDT)."""
    if coin == "PEPE":
        return "1000PEPEUSDT"
    return f"{coin}USDT"


def _multiplier(symbol: str) -> float:
    """Binance lists low-priced coins in 1000-token units (1000PEPEUSDT quotes the
    price of 1000 PEPE). The cap must divide by that multiplier so close x supply
    stays in single-token terms. Returns 1000 for a '1000' prefix, else 1."""
    return 1000.0 if symbol.startswith("1000") else 1.0


# ---------------------------------------------------------------- proxy series
def build_marketcap(start: pd.Timestamp, end: pd.Timestamp,
                    supplies: dict[str, float] | None = None) -> pd.DataFrame | None:
    """Per-4h-bar TOTAL/TOTAL2/TOTAL3 proxy + derived breadth, over [start, end].

    Columns: total, total2, total3, btc_d (BTC dominance of the proxy),
             t3_ema, t3_slope (pct change of t3_ema over SLOPE_N bars),
             t3_t2_ratio (altseason breadth: TOTAL3/TOTAL2).
    None if no coin had data. Caps are summed only over the bars where a coin has a
    close (an unlisted/new coin simply doesn't contribute until it exists)."""
    supplies = supplies or fetch_supplies()
    caps: dict[str, pd.Series] = {}
    for sym, sup in supplies.items():
        df1 = tsc.fetch_1h(sym, start, end)
        if df1 is None or df1.empty:
            continue
        c4 = df1.resample("4h", label="right", closed="right").agg(_AGG)["close"].dropna()
        if c4.empty:
            continue
        caps[sym] = c4 * (sup / _multiplier(sym))
    if not caps:
        return None

    cap_df = pd.concat(caps, axis=1).sort_index()
    total = cap_df.sum(axis=1, min_count=1)
    btc = cap_df.get("BTCUSDT")
    eth = cap_df.get("ETHUSDT")
    total2 = total - btc.reindex(total.index).fillna(0.0) if btc is not None else total
    sub = (btc.reindex(total.index).fillna(0.0) if btc is not None else 0.0) \
        + (eth.reindex(total.index).fillna(0.0) if eth is not None else 0.0)
    total3 = total - sub

    out = pd.DataFrame({"total": total, "total2": total2, "total3": total3})
    out["btc_d"] = (btc.reindex(total.index) / total) if btc is not None else np.nan
    out["t3_ema"] = total3.ewm(span=EMA_SPAN, adjust=False).mean()
    out["t3_slope"] = out["t3_ema"].pct_change(SLOPE_N)
    out["t3_t2_ratio"] = total3 / total2
    return out.dropna(subset=["total3"])


# ---------------------------------------------------------------- lookup + regime
def _row_at(mc: pd.DataFrame | None, ts):
    """Row at the last 4h bar at/before ts, or None (same contract as regime._er_at)."""
    if mc is None or len(mc) == 0:
        return None
    idx = mc.index
    t = pd.Timestamp(ts)
    if t.tz is None:
        t = t.tz_localize("UTC")
    pos = int(idx.searchsorted(t, side="right")) - 1
    if pos < 0 or pos >= len(mc):
        return None
    return mc.iloc[pos]


def regime_at(mc: pd.DataFrame | None, ts) -> str:
    """Market breadth regime at ts: 'risk_on' | 'risk_off' | 'neutral' | 'unknown'.

    Read off the TOTAL3 (altcoin cap) EMA slope: rising breadth = money flowing
    into risk; falling = retreat (often into BTC/stables)."""
    row = _row_at(mc, ts)
    if row is None or row.get("t3_slope") is None or pd.isna(row.get("t3_slope")):
        return "unknown"
    s = float(row["t3_slope"])
    if s > SLOPE_EPS:
        return "risk_on"
    if s < -SLOPE_EPS:
        return "risk_off"
    return "neutral"


def riskon_ok(mc: pd.DataFrame | None, ts) -> bool:
    """Gate: True unless breadth is confirmed risk_off. Missing -> True (never
    over-filter on absence). The permissive complement, mirroring regime.chop_ok."""
    return regime_at(mc, ts) != "risk_off"


def is_riskoff(mc: pd.DataFrame | None, ts) -> bool:
    """True only when breadth is PRESENT and risk_off (the confirmed complement,
    mirroring regime.is_choppy). Missing -> False."""
    return regime_at(mc, ts) == "risk_off"


# ---------------------------------------------------------------- live snapshot
def fetch_live() -> dict:
    """Exact current TOTAL/TOTAL2/TOTAL3 (USD) + BTC/ETH dominance from CoinGecko
    /global. TOTAL2/3 derived from dominance the same way TradingView does."""
    r = requests.get(CG_GLOBAL, timeout=20)
    r.raise_for_status()
    d = r.json()["data"]
    total = float(d["total_market_cap"]["usd"])
    pct = d["market_cap_percentage"]
    btc_d = float(pct.get("btc", 0.0)) / 100.0
    eth_d = float(pct.get("eth", 0.0)) / 100.0
    total2 = total * (1.0 - btc_d)
    total3 = total * (1.0 - btc_d - eth_d)
    return {
        "ts": pd.Timestamp.utcnow().floor("min").isoformat(),
        "total": total, "total2": total2, "total3": total3,
        "btc_d": btc_d, "eth_d": eth_d,
    }


def snapshot_live(csv_path: Path = LIVE_CSV) -> dict:
    """Fetch the live snapshot and APPEND it to the ground-truth CSV (header on
    first write). Call this from the daily sync; the real series accrues forward."""
    snap = fetch_live()
    OUT.mkdir(parents=True, exist_ok=True)
    new = not csv_path.exists()
    line = "{ts},{total},{total2},{total3},{btc_d},{eth_d}\n".format(**snap)
    with csv_path.open("a") as f:
        if new:
            f.write("ts,total,total2,total3,btc_d,eth_d\n")
        f.write(line)
    return snap


def _human(x: float) -> str:
    for unit, div in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if abs(x) >= div:
            return f"${x / div:.3f}{unit}"
    return f"${x:.0f}"


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="TOTAL/2/3 market-cap regime map")
    ap.add_argument("--live", action="store_true", help="print exact live snapshot (CoinGecko)")
    ap.add_argument("--snapshot", action="store_true", help="append live snapshot to the CSV")
    ap.add_argument("--days", type=int, default=14, help="proxy history window to print")
    ap.add_argument("--refresh-supplies", action="store_true")
    args = ap.parse_args()

    if args.snapshot:
        s = snapshot_live()
        print(f"appended {LIVE_CSV.name}: {s['ts']}  TOTAL={_human(s['total'])} "
              f"TOTAL2={_human(s['total2'])} TOTAL3={_human(s['total3'])} "
              f"BTC.D={s['btc_d']*100:.1f}%")

    if args.live or not (args.snapshot):
        s = fetch_live()
        print("=== LIVE (CoinGecko /global, exact) ===")
        print(f"  TOTAL  {_human(s['total'])}")
        print(f"  TOTAL2 {_human(s['total2'])}  (TOTAL - BTC)")
        print(f"  TOTAL3 {_human(s['total3'])}  (TOTAL - BTC - ETH)")
        print(f"  BTC.D  {s['btc_d']*100:.1f}%   ETH.D {s['eth_d']*100:.1f}%")
        print(f"  TOTAL3/TOTAL2 = {s['total3']/s['total2']:.3f}  (altseason breadth)")

    end = pd.Timestamp.now(tz="UTC")
    start = end - pd.Timedelta(days=args.days + 5)  # +warmup for EMA/slope
    sup = fetch_supplies(refresh=args.refresh_supplies)
    print(f"\n=== PROXY series (Binance x supply, {len(sup)} coins) ===")
    mc = build_marketcap(start, end, sup)
    if mc is None or mc.empty:
        print("  no proxy data")
    else:
        tail = mc.loc[mc.index >= mc.index[-1] - pd.Timedelta(days=args.days)]
        for ts, row in tail.iloc[::max(1, len(tail) // 12)].iterrows():
            reg = regime_at(mc, ts)
            print(f"  {ts:%Y-%m-%d %H:%M}  T3={_human(row['total3'])} "
                  f"slope={row['t3_slope']*100:+5.2f}%  BTC.D={row['btc_d']*100:4.1f}%  -> {reg}")
        print(f"  current regime: {regime_at(mc, mc.index[-1])}")
