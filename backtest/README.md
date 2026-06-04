# ICT Backtest

Python implementation of the signal layer described in [`../ICT_Signal_Strategies.md`](../ICT_Signal_Strategies.md).

Five strategies (A–E), shared detector library, confluence scoring, and a bar-by-bar backtest engine.

## Layout

```
backtest/
├── ict/
│   ├── config.py        # all tunables (ATR multipliers, killzones, weights)
│   ├── data.py          # Binance kline fetch + CSV loader + MTF aggregation
│   ├── indicators.py    # ATR
│   ├── detectors.py     # swings, BOS/CHoCH, liquidity, OB, FVG, killzone, P/D
│   ├── strategies.py    # Strategy A–E, returning Signal objects
│   └── confluence.py    # multi-strategy merge + score thresholds
├── engine.py            # build_detectors + run_engine (per symbol)
├── backtester.py        # simulate_signal, compute_metrics, export_results
└── run_backtest.py      # CLI
```

## Install

```bash
cd backtest
pip install -r requirements.txt
```

## Usage

Pull data from Binance and run:

```bash
python run_backtest.py --symbol BTCUSDT --interval 5m --days 60
```

Use a local CSV (`timestamp,open,high,low,close,volume`):

```bash
python run_backtest.py --csv data/btc_5m.csv --symbol BTCUSDT
```

Date range:

```bash
python run_backtest.py --symbol ETHUSDT --interval 15m \
  --start 2025-01-01 --end 2025-04-01
```

## Output

`./out/{symbol}_{interval}_{from}_{to}.json` with two top-level keys:

- `metrics`: total signals, win rate, expectancy in R, drawdown, per-strategy breakdown.
- `trades`: every signal with its lifecycle outcome (TP_HIT / SL_HIT / EXPIRED / INVALIDATED / ACTIVE) and PnL in R.

## Tuning

All knobs are in [`ict/config.py`](ict/config.py):

- `IMPULSE_ATR_MULT` (default `2.0`) — sensitivity of OB detection.
- `MIN_RR_DEFAULT` / `MIN_RR_SILVER_BULLET` — gating thresholds per spec.
- `CONFLUENCE_WEIGHTS` and `CONFLUENCE_MIN_PUBLISH` — scoring + publish gate.
- `KILLZONES_NY` — session windows in NY local time.

The spec's section 9 lists known limitations. Walk-forward optimisation of the
weight table is recommended before any live use.

## Notes

- All detectors are pure functions of the bar series — no external state.
- No look-ahead: each signal at bar `i` is computed from data `[0..i]` only.
  Verified by [`test_no_lookahead.py`](test_no_lookahead.py) — engine produces
  identical signals on full vs truncated data across 200+ sample bars.
- The backtester simulates limit-style entry; if both TP and SL are touched in
  the same bar after entry, SL is assumed first (worst-case).
- The "ACTIVE" status means a position was filled but neither TP nor SL hit
  before the dataset ended.

## Live Mode

Production live signals run from [`../dag/dag.py`](../dag/dag.py) — the same engine,
standalone (no Airflow required). It runs the engine on the most recent closed bar
and writes new signals to the **live** Supabase table (`ict_trade.signals`) plus an
optional Telegram notification.

Required env (via `.env` or process env):

| Var | Purpose |
|---|---|
| `DB_CONNECTION_STRING` | Postgres DSN to the **live** Supabase project |
| `TELEGRAM_BOT_TOKEN` | optional — without it Telegram is skipped |
| `TELEGRAM_CHAT_ID` | optional — channel/group id |
| `BINANCE_PROXY` | optional — proxy URL for geo-blocked (US 451) runners |

Deployment is an hourly cron on a EU-region VM (Binance blocks US IPs with 451).
See [`../dag/DEPLOY_ORACLE.md`](../dag/DEPLOY_ORACLE.md) for the Oracle Cloud
Always Free setup. The runner is idempotent: it checks
`(symbol, signal_time, direction)` before inserting, so re-running an hour is safe.
