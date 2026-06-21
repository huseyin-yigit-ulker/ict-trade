# `sync/live_exec` — DONCHIAN 30m+4h·WR **8R ·0.5R** (`d30so8c`) → Binance USDⓈ-M live execution

Drives **real** Binance Futures orders that reproduce the `d30so8c` scale-out backtest. It does
**not** recompute signals — it consumes the same `dch30_4h` rows from `ict_trade.signals` that the
dashboard and `sync/sync_daily.py::resolve_scaleout_stream` use, so the live trade set ≡ backtest.

## Mechanic (Mode B, ·0.5R confirmed entry — long; short mirrors)
`risk0 = |entry_close − sl|`
- **Entry**: `STOP_MARKET` at `entry_close + 0.5·risk0`; once it confirms+fills, `risk_eff ≈ 1.5·risk0`.
- **Full SL**: `STOP_MARKET closePosition` at the structural `sl = entry_close − risk0`.
- **TP1 (+1R)**: `TAKE_PROFIT_MARKET reduceOnly` at `avgFill + 1·risk_eff`, books **60%** → +0.6R floor.
- **Runner (40%)** after TP1: BE-stop at `avgFill`, **cap** `TAKE_PROFIT_MARKET` at the structural
  `entry_close + 8·risk0` (= `avgFill + 5·risk_eff`, the row's `tp_price`); whichever of BE / cap /
  **3-day** mark-to-market comes first.

All levels come from [levels.py](levels.py) — one deterministic source shared by the executor and
the parity report, so live can't drift from `scaleout.resolve_scaleout`.

## Modules
| File | Role |
|---|---|
| `config.py` | `LiveCfg` + `load_cfg()` (fail-closed); mirrors `scaleout` constants |
| `levels.py` | deterministic leg prices (`compute_levels`, `reanchor`) |
| `binance_futures.py` | signed REST client (raw `requests` + HMAC), idempotent error codes |
| `exchange_info.py` | tick/step rounding, min-notional, tradable-perp screen (rejects XAU) |
| `sizing.py` | `qty = risk_usd/|entry−sl|`, 60/40 split |
| `state.py` | `live_positions`/`live_orders` persistence, deterministic `clientOrderId`, writeback to `trading_signals` |
| `executor.py` | **cron #1** reconciler + Faz-0 dry-run intent logger |
| `safety_sweep.py` | **cron #2** orphan/stop/skew/risk-cap guard |
| `killswitch.py` | `--status` / `--flatten` / `--halt` |
| `parity_report.py` | live-intent vs `resolve_scaleout` diff (Faz-0 gate) |
| `schema.sql` | `live_positions` + `live_orders` DDL (idempotent) |

## Setup
1. `psql "$DB_CONNECTION_STRING" -f sync/live_exec/schema.sql`
2. Copy `.env.example` keys into the VM `.env`; fill `BINANCE_API_KEY/SECRET` (Futures-only, IP-restricted, withdrawal OFF).
3. **Rotate the leaked Supabase/Telegram secrets first** (they are in git history).

## Cron (add to `dag/crontab`; offset off the `:00/:30` boundary). Both no-op while `LIVE_TRADING_ENABLED=false`.
```
*/2 * * * * sleep 25 && cd $HOME/ict-trade && DCH_SO_RUNNER_CAP=8 DCH_ENTRY_AT_CONFIRM=1 .venv/bin/python sync/live_exec/executor.py     >> $HOME/ict-exec.log 2>&1
*/5 * * * * sleep 50 && cd $HOME/ict-trade && .venv/bin/python sync/live_exec/safety_sweep.py  >> $HOME/ict-exec.log 2>&1
```

## Phases
- **Faz 0 (dry-run)** `EXEC_DRY_RUN=true`: `executor.py` logs intended orders; `parity_report.py`
  must print **PASS** (0 mismatches vs `resolve_scaleout`).
- **Faz 2 (small mainnet)** `EXEC_DRY_RUN=false LIVE_TRADING_ENABLED=true`, $5/3x/max-3 on BTC/ETH/SOL.
  Verify a full trade end-to-end, reconcile `userTrades` ↔ `live_orders`, test `--flatten` + `--halt`
  once, and kill/restart the cron mid-trade to confirm state recovery.
- **Faz 3**: widen `EXEC_ENABLED_SYMBOLS` from `SO_SYMBOLS` in small batches.
