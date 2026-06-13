"""KARMA stream per-symbol selection map — which parent set and exit model each
symbol trades under (the winning cell of the 2026 Jan-Jun 4-cell matrix
{main, impulse} x {tam, yarim}; see sync/backtest_karma.py).

  KARMA_MAP[symbol] = {"set": "main"|"impulse", "half": bool}
    set  : live source — "main" reads mode='live' signals, "impulse" mode='impulse'
    half : exit model — True = partial-TP + breakeven (yarim), False = full TP (tam)

GENERATED from sync/out/karma_selection_2026.csv — regenerate after a fresh
selection run:
  python sync/backtest_karma.py --year 2026          # writes the selection CSV
  (then update this dict + the KARMA_MAP constant in src/context/TradeContext.jsx)

NB: the selection is IN-SAMPLE on 2026 Jan-Jun data — treat the blended stream as
an upper bound until it accrues out-of-sample months.
"""

# Generated 2026-06-12 from the full 36-symbol 2026 Jan-Jun selection run.
# Cell totals: karma +170.2R vs pure streams main/tam +120.3R, impulse/tam +158.2R,
# main/yarim +29.2R, impulse/yarim +68.2R. (33x main / 3x impulse; 30x tam / 6x yarim.)
KARMA_MAP: dict[str, dict] = {
    "1000PEPEUSDT": {"set": "main", "half": True},
    "AAOIUSDT": {"set": "main", "half": False},
    "ADAUSDT": {"set": "impulse", "half": True},
    "AMATUSDT": {"set": "main", "half": False},
    "AMZNUSDT": {"set": "main", "half": False},
    "ARBUSDT": {"set": "main", "half": False},
    "AVGOUSDT": {"set": "main", "half": False},
    "BABAUSDT": {"set": "main", "half": True},
    "BNBUSDT": {"set": "main", "half": False},
    "BTCUSDT": {"set": "main", "half": False},
    "BXUSDT": {"set": "main", "half": False},
    "COINUSDT": {"set": "main", "half": False},
    "CRCLUSDT": {"set": "main", "half": False},
    "CRDOUSDT": {"set": "main", "half": False},
    "CRWDUSDT": {"set": "main", "half": False},
    "ETHUSDT": {"set": "impulse", "half": False},
    "FETUSDT": {"set": "main", "half": True},
    "HOODUSDT": {"set": "main", "half": False},
    "HPEUSDT": {"set": "main", "half": False},
    "INTCUSDT": {"set": "main", "half": False},
    "IWMUSDT": {"set": "main", "half": False},
    "METAUSDT": {"set": "main", "half": False},
    "MSFTUSDT": {"set": "main", "half": False},
    "MSTRUSDT": {"set": "main", "half": False},
    "NEARUSDT": {"set": "main", "half": False},
    "NVDAUSDT": {"set": "main", "half": False},
    "ONDOUSDT": {"set": "main", "half": False},
    "ORDIUSDT": {"set": "main", "half": False},
    "PLTRUSDT": {"set": "main", "half": True},
    "SOLUSDT": {"set": "main", "half": True},
    "SUIUSDT": {"set": "main", "half": False},
    "SUSDT": {"set": "main", "half": False},
    "TSLAUSDT": {"set": "main", "half": False},
    "WIFUSDT": {"set": "main", "half": False},
    "XAGUSDT": {"set": "main", "half": False},
    "XAUUSDT": {"set": "impulse", "half": False},
    # 2026-06-13 crypto re-add (best cell each; net-negative in 2026 except LINK +3.2R —
    # included for universe consistency, re-validate next audit).
    "XRPUSDT": {"set": "main", "half": False},
    "DOGEUSDT": {"set": "main", "half": False},
    "LINKUSDT": {"set": "main", "half": False},
    "AVAXUSDT": {"set": "main", "half": True},
}
