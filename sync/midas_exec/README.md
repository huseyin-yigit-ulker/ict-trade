# `sync/midas_exec/` — MIDAS real-money-capable Binance executor (TESTNET / DRY-RUN first)

Runs the **MIDAS** gold strategy (XAUUSDT 1m anchored-VWAP trend-continuation) as real Binance
USDⓈ-M Futures orders — the same way **OPUS** (`sync/live_exec`) runs the Donchian scale-out stream,
but with MIDAS's own mechanics. Built to run on **testnet + dry-run first**; mainnet is user-gated.

## ⚠️ Cost reality (read first)
MIDAS is validated at **+142R** on a **$0.50/oz FX/ECN** cost. On **Binance taker (~10 bps ≈ $4/oz)**
the same trades are ≈ **−92R** (`FX-GOLD-VWAP-RAPORU.md`, `MIDAS.md`). The chandelier trailing exit is
a `STOP_MARKET` (taker), so even the post-only maker entry doesn't fully rescue it. **A Binance-fee
simulation MUST pass before any mainnet arming** — this bridge is testnet/paper infrastructure until
then. The real-money default is fail-closed (`LIVE_TRADING_ENABLED` / `MIDAS_EXEC_ENABLED` = false).

## What it does
- Reads the `mode='midas'` live signals (`ict_trade.signals`) the paper feed already emits.
- Places a **post-only maker LIMIT** entry at the pullback close (`GTX`); cancels/skips on timeout or
  slip past `MIDAS_ENTRY_MAX_SLIP_R` (maker-only — never chases with a taker).
- Manages the exit with `sync/midas/strategy.track_open` — the **same** 1.5×ATR init stop → 3.5×ATR
  chandelier trail → 8h cap → session flatten the paper `canli.py` drives (parity by construction).
- **Testnet**: synthetic model — recompute the chandelier each tick, MARKET-close on the exit trigger
  (testnet rejects conditional orders with `-4120`).
- **Mainnet**: lays a resting `STOP_MARKET(closePosition)` at the stop and cancel/replaces it as the
  chandelier ratchets (dead-band throttled).
- On close, writes the real result back to `ict_trade.trading_signals` under `version='midasx'`
  (distinct from the nightly-rewritten paper `'midas'`), with the trailing-stop context for the chart.

## Isolation from OPUS
Separate DB tables (`ict_trade.midas_positions` / `midas_orders`), separate `MIDAS_*` env namespace,
and a killswitch/safety-sweep scoped to `XAUUSDT` only — the two executors can never flatten each
other's positions. Shares only the strategy-agnostic infra (`binance_futures`, `exchange_info`,
`sizing`, `notify`) by import, plus the `live_account`/`live_account_snapshot` dashboard tables.

## Files
| File | Role |
|---|---|
| `executor.py` | cron #1 — read signals → maker entry → chandelier trailing → exits → reconcile |
| `config.py` | `MidasExecCfg` + `load_cfg()`; `MIDAS_*` env; fail-closed |
| `state.py` | only-writer of `midas_positions`; deterministic `mdx-…` coids; context-aware writeback |
| `schema.sql` | additive DDL (`midas_positions` / `midas_orders`) |
| `safety_sweep.py` | cron #2 — orphan / reconciler-freshness, scoped to XAUUSDT |
| `killswitch.py` | operator CLI `--status` / `--flatten` / `--halt` (MIDAS-only) |
| `parity_report.py` | Faz-0 gate — `track_open` replay vs the backtest `walk()` (0 mismatches) |

## Run
> **⚠️ Prerequisite:** gold is a Binance `TRADIFI_PERPETUAL` — accept the **"TradFi-Perps agreement"**
> once per account (testnet + mainnet) or every order returns `-4411`. The executor detects this and
> logs/pings a clear hint.

```bash
# 0) one-time: create the tables
psql "$DB_CONNECTION_STRING" -f sync/midas_exec/schema.sql

# 1) parity gate (blocking) — executor engine == backtest
.venv/bin/python sync/midas_exec/parity_report.py

# 2) dry-run (no orders, no keys needed) — logs intents
MIDAS_EXEC_DRY_RUN=true .venv/bin/python sync/midas_exec/executor.py

# 3) TESTNET armed (needs BINANCE_TESTNET_API_KEY/SECRET)
LIVE_TRADING_ENABLED=true MIDAS_EXEC_ENABLED=true MIDAS_EXEC_DRY_RUN=false \
  BINANCE_TESTNET=true .venv/bin/python sync/midas_exec/executor.py

# emergency
.venv/bin/python sync/midas_exec/killswitch.py --status
.venv/bin/python sync/midas_exec/killswitch.py --flatten
.venv/bin/python sync/midas_exec/killswitch.py --halt      # MIDAS_EXEC_ENABLED=false (MIDAS only)
```

Cron (in `dag/crontab`, no-op until armed): executor every minute (to match the 1m chandelier),
safety sweep every 3 minutes. See `MIDAS.md` for the full ops + the mainnet fee-sim gate.
