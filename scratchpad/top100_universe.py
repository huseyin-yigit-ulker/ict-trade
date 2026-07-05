"""Top-N crypto (CoinGecko market-cap) ∩ Binance USDT perps (exchangeInfo) with 2026 data.
Handles 1000x listings (SHIB->1000SHIBUSDT). Excludes stables/wrapped. -> top100_symbols.txt"""
import sys
sys.path.insert(0, "sync"); sys.path.insert(0, "sync/donchian"); sys.path.insert(0, "sync/live_exec")
import requests, pandas as pd
import trade_sync_common as tsc

STABLE = {"USDT","USDC","DAI","FDUSD","TUSD","USDE","BUSD","USDD","PYUSD","USDS","USD1","FRAX",
          "LUSD","GUSD","USDP","SUSD","CRVUSD","USDX","RLUSD","USDF","XUSD"}
WRAPPED = {"WBTC","WETH","WEETH","WBETH","STETH","WSTETH","RETH","CBBTC","LBTC","SOLVBTC","BNSOL",
           "JITOSOL","MSOL","WBNB","WHYPE","BSC-USD","SUSDE","SUSDS","BUIDL","BGB","LEO"}

perps = set()
d = requests.get("https://fapi.binance.com/fapi/v1/exchangeInfo", timeout=25).json()
for s in d["symbols"]:
    if s.get("contractType") == "PERPETUAL" and s["symbol"].endswith("USDT") and s.get("status") == "TRADING":
        perps.add(s["symbol"])
print(f"Binance USDT perps: {len(perps)}", flush=True)

cg = requests.get("https://api.coingecko.com/api/v3/coins/markets",
                  params={"vs_currency": "usd", "order": "market_cap_desc", "per_page": 250, "page": 1},
                  timeout=30).json()
print(f"CoinGecko coins: {len(cg)}", flush=True)

S26 = int(pd.Timestamp("2026-01-01", tz="UTC").timestamp() * 1000)
E26 = int(pd.Timestamp("2026-06-22", tz="UTC").timestamp() * 1000)


def ok2026(sym):
    df = tsc.fetch_klines(sym, "1d", S26, E26)
    return df is not None and len(df) >= 120


universe = []
for c in cg:
    if len(universe) >= 100:
        break
    sym = (c.get("symbol") or "").upper()
    rank = c.get("market_cap_rank")
    if sym in STABLE or sym in WRAPPED:
        continue
    cand = next((x for x in (f"{sym}USDT", f"1000{sym}USDT") if x in perps), None)
    if cand and ok2026(cand):
        universe.append(cand)
        print(f"  #{rank:<4} {cand}", flush=True)

open("scratchpad/top100_symbols.txt", "w").write("\n".join(universe))
print(f"\n=> {len(universe)} symbols with 2026 data -> scratchpad/top100_symbols.txt")
