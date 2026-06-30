# ict-trade — System Runbook

> **Master operations & setup guide for the whole project.** What it is, system requirements, every
> component, how to bring up the **entire system from a fresh clone**, how to operate it, and a
> **changelog** appended on every change. Stream-specific deep dives are linked in §4 / §10.

---

## 1. What this is

A quantitative crypto/FX **trading research + live signal system**:

- **Backtest engines** (Python) replay Binance 1-minute data into a Postgres DB.
- **Live emitters** (cron, every bar) detect fresh signals and write them to a live DB.
- A **React/Vite dashboard** reads both DBs (live feed + backtest drill-down Year→Month→Day, with
  TradingView-style charts).
- A **real-money Binance Futures executor** trades exactly one stream (**OPUS**); everything else is
  **paper** (signals + Telegram + dashboard only).
- **Telegram** alerts on formations / trade lifecycle.

Three streams are surfaced live; the rest of the "Donchian book" is backtest-only research.

| Stream | What | Live? | Money |
|---|---|---|---|
| **OPUS** (`d30so8f3h7`) | Donchian 30m breakout + 4h confirm, scale-out (60% @ +1R, runner +8R cap / BE / 7d) | ✅ | **REAL** (Binance Futures) |
| **FABLE** (`d30so8f3vg`) | OPUS twin, only taken when daily volume is contracting (vch<0.9) | ✅ | paper |
| **MIDAS** (`midas`) | Gold-only (XAUUSDT) 1m VWAP-trend pullback + 3.5×ATR trailing | ✅ | paper |
| Donchian book (`donchianc`, `d1h_so*`, `d30so*`, …) | breakout families, various exits | backtest-only | — |

Deep dives: **[MIDAS.md](MIDAS.md)** (gold stream), [STRATEJI-RAPORU.md](STRATEJI-RAPORU.md) &
[FX-GOLD-VWAP-RAPORU.md](FX-GOLD-VWAP-RAPORU.md) (research), `sync/live_exec/README.md` (executor).

---

## 2. System requirements

| Need | Detail |
|---|---|
| **OS** | Linux (Ubuntu 22.04/24.04). Reference deploy = Oracle Cloud **Always Free** VM (1 vCPU / 1–6 GB). |
| **⚠️ Region** | Must be where **Binance API is reachable** (EU: Frankfurt/Amsterdam). **US IPs get HTTP 451** — that's why the bot runs on a VM, not US GitHub runners. |
| **Python** | 3.10+ with `venv`. Deps in `requirements.txt` / `backtest/requirements.txt` / `dag/requirements.txt` (pandas, numpy, requests, sqlalchemy, psycopg2-binary, python-dotenv, PyGithub). |
| **Node** | 22.x (for the Vite dashboard build). |
| **Databases** | Two external **Postgres** (Supabase) schemas: **live** (`ict_trade.signals`) + **backtest** (`ict_trade.trading_signals`). Persist across machines. |
| **External services** | Binance Futures API (klines; + API key/secret only for the OPUS executor), Telegram bot, GitHub (push), Supabase (DB + REST + RLS). |
| **cron** | Standard crond (the live loop). |

VM provisioning specifics (Oracle account → instance → SSH → firewall): **[dag/DEPLOY_ORACLE.md](dag/DEPLOY_ORACLE.md)**.
Idempotent installer: **`dag/setup_vm.sh`**.

---

## 3. Repository layout

```
ict-trade/
├── src/                     React + Vite dashboard (live feed + backtest drill-down + charts)
│   ├── context/             TradeContext (data load), LanguageContext (TR/EN)
│   ├── components/          Dashboard, ChartModal, layout/ (Sidebar, Topbar)
│   └── utils/               streamStats (stream registry), strategyInfo, symbolMeta, sessions
├── sync/                    Backtest backfills + live emitters + nightly ETL  (the engine room)
│   ├── donchian/            Donchian strategy: strategy.py, canli.py (live emit), scaleout*.py,
│   │                        portfolio_backfill.py, volgate_backfill.py (FABLE), …
│   ├── midas/               MIDAS gold stream: strategy.py, backfill.py, canli.py   → see MIDAS.md
│   ├── live_exec/           REAL-MONEY Binance executor (OPUS): executor.py, safety_sweep.py,
│   │                        config.py, binance_futures.py, killswitch.py, state.py, schema.sql
│   ├── sync_daily.py        Nightly ETL: resolve live signals → backtest versions
│   └── trade_sync_common.py Shared: DB conns, fetch_klines, outcome sim, row upsert
├── backtest/                Backtest engine + ICT detectors (backtester.py, ict/, engine.py, validation/)
├── dag/                     dag.py (original ICT signal generator), crontab (VM cron), setup_vm.sh,
│                            DEPLOY_ORACLE.md
├── scripts/                 gen-login-hash.mjs (login creds)
├── supabase/                DB schema/policies
├── .github/workflows/       daily_run.yml — nightly JSON export (update_data.py) committed to repo
├── requirements.txt         Python deps (root)
├── package.json             Node deps + scripts (dev / build / lint / preview)
├── README.md                Frontend + security notes
├── RUNBOOK.md               ← this file
└── MIDAS.md                 MIDAS stream runbook + changelog
```

Gitignored (recreate per §6): `.env`, `.venv`, `node_modules`, `dist`, `__pycache__`, `scratchpad/`
(research caches), `dag/crontab.backup.*`.

---

## 4. Architecture / data flow

```
 Binance 1m klines
        │
        ├─► LIVE EMIT (cron, each bar)                         ┌────────── DASHBOARD (React/Vite) ──────────┐
        │     donchian/canli.py  (OPUS, FABLE, 1h, 6R)         │  "Live"     ← ict_trade.signals (REST)      │
        │     midas/canli.py     (MIDAS, every minute)   ──►   │  "Backtest" ← ict_trade.trading_signals     │
        │        └─► ict_trade.signals (live DB, mode=…)       │  drill Year→Month→Day + TradingView charts  │
        │                                                       └─────────────────────────────────────────────┘
        ├─► NIGHTLY ETL (cron 00:30+)                          ▲
        │     sync_daily.py --stream all                       │  resolve live signals → version rows
        │     midas/backfill.py, volgate_backfill.py     ──►  ict_trade.trading_signals (backtest DB, version=…)
        │
        └─► REAL-MONEY EXECUTOR (cron */2)  ── reads OPUS signals ──►  Binance Futures orders (live_exec/)
              executor.py + safety_sweep.py (*/5)                       gated by .env LIVE_TRADING_ENABLED
```

- **Two DBs** (external, persist): **live** = `ict_trade.signals` (mode-tagged feed); **backtest** =
  `ict_trade.trading_signals` (version-tagged settled book). The UI reads both over Supabase REST.
- **Streams = (mode tag → live) + (version tag → backtest)**. The nightly ETL resolves emitted live
  signals into backtest `version` rows. (MIDAS backfills standalone from data, not via ETL.)
- Only **OPUS** reaches Binance with real orders; **FABLE/MIDAS/Donchian-book = paper**.

---

## 5. The cron loop (`dag/crontab`)

Applied with `crontab dag/crontab`. All times UTC. (See §8 for safety on the real-money lines.)

| Schedule | Job | Stream |
|---|---|---|
| `0 * * * *` | `donchian/canli.py --emit` (1h breakout) | Donchian 1h |
| `0,30 * * * *` | `donchian/canli.py --emit --tf 30m --confirm-htf 4h --name OPUS` | **OPUS** emit |
| `0,30 * * * *` | `… --rr 6 --no-telegram` | 6R twin (silent) |
| `0,30 * * * *` | `… --volume-gate 0.9 --name FABLE` | **FABLE** emit |
| `* * * * *` | `midas/canli.py --emit --lookback-min 3 --sl-step 0` | **MIDAS** emit + trailing track + Telegram |
| `30 0 * * *` | `sync_daily.py --stream all` | nightly resolve (all streams) |
| `45 0 * * *` | `sync_daily.py --stream d30_4h_so` (cap 6) | scale-out 6R |
| `0 1 * * *` | `sync_daily.py --stream d30_4h_so` (cap 8) | scale-out 8R |
| `20 1 * * *` | `volgate_backfill.py --apply` | FABLE backtest refresh |
| `30 1 * * *` | `midas/backfill.py --apply` | MIDAS backtest refresh |
| `*/2 * * * *` | `live_exec/executor.py` | **REAL-MONEY** OPUS reconciler |
| `*/5 * * * *` | `live_exec/safety_sweep.py` | executor safety guard |

Logs: `~/ict-donchian.log`, `~/ict-midas.log`, `~/ict-sync.log`, `~/ict-exec.log`.

---

## 6. Environment setup (`.env` keys)

`.env` lives at the repo root, **gitignored — never committed**. Set your own values. Vite reads only
`VITE_*` / `BACKTESTING_VITE_*` into the frontend bundle (`vite.config.js > envPrefix`).

**Databases (Python pipeline):**
- `DB_CONNECTION_STRING`, `DB_TABLE` — live DB (`ict_trade.signals`).
- `BACKTESTING_DB_CONNECTION_STRING`, `BACKTESTING_DB_TABLE` — backtest DB (`ict_trade.trading_signals`).

**Dashboard (Vite, build-time):**
- `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY` — live DB REST.
- `BACKTESTING_VITE_SUPABASE_URL`, `BACKTESTING_VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY` — backtest DB REST.
- Login gate (optional): `VITE_LOGIN_USER_SHA256`, `VITE_LOGIN_PBKDF2` (`node scripts/gen-login-hash.mjs`).

**Telegram:** `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
**Git push:** `GITHUB_TOKEN`.

**Real-money OPUS executor only** (leave unset on a paper/research box):
`LIVE_TRADING_ENABLED`, `BINANCE_TESTNET`, `BINANCE_TESTNET_API_KEY/SECRET` (+ mainnet keys), `EXEC_*`
(`EXEC_NAME/VERSION/ENABLED_SYMBOLS/DRY_RUN`), `RISK_PER_TRADE_USD`, `MAX_TOTAL_RISK_USD`,
`MAX_CONCURRENT_POSITIONS`, `LEVERAGE`/`LEVERAGE_MAX`/`AUTO_LEVERAGE`, `MARGIN_TYPE`, `LIVE_ENTRY_MODE`,
`CLOSE_FRAC`, `HORIZON_DAYS`, `RUNNER_CAP_R`, `DCH_ENTRY_AT_CONFIRM`, `DCH_SO_RUNNER_CAP`.

---

## 7. Bring up the WHOLE system from a fresh clone

```bash
# 0. Provision a Binance-reachable Linux VM (EU). See dag/DEPLOY_ORACLE.md.
sudo apt update && sudo apt install -y python3-venv python3-pip git
git clone https://github.com/huseyin-yigit-ulker/ict-trade.git && cd ict-trade

# 1. .env at repo root with the §6 keys (point DB strings at your Postgres/Supabase).

# 2. Python env (idempotent helper exists)
bash dag/setup_vm.sh            # creates .venv + installs deps + connectivity test
# (or manually: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r backtest/requirements.txt)

# 3. Dashboard (only if this box serves the UI)
#    Install Node 22, then:
npm install && npm run build    # → dist/  (serve it, or deploy via your static host)

# 4. Seed the backtest DB (idempotent; re-runnable)
.venv/bin/python sync/midas/backfill.py --apply             # MIDAS
.venv/bin/python sync/donchian/volgate_backfill.py --apply  # FABLE
.venv/bin/python sync/donchian/portfolio_backfill.py --stream all --apply   # Donchian book (optional, heavy)
#    (the OPUS/FABLE/Donchian *live* versions also re-resolve nightly via sync_daily.py)

# 5. Smoke-test emitters (no write / no Telegram)
.venv/bin/python sync/midas/canli.py --dry-run
.venv/bin/python sync/donchian/canli.py --dry-run

# 6. Activate the live loop
crontab -l > dag/crontab.backup.live-$(date +%Y%m%d-%H%M%S) 2>/dev/null || true   # backup
crontab dag/crontab
crontab -l | grep -E "canli|backfill|executor"                                    # verify

# ⚠️ REAL MONEY: the executor only trades when .env LIVE_TRADING_ENABLED=true (+ valid Binance keys).
#    Leave it false to run the whole system in paper mode.
```

Result: live emitters fire each bar, the dashboard shows live + backtest, Telegram alerts flow, and (if
enabled) the OPUS executor trades real Binance Futures.

---

## 8. Operations & safety

- **Logs:** `tail -f ~/ict-{donchian,midas,sync,exec}.log`.
- **Real-money executor:** `sync/live_exec/` — `executor.py` (reconciler, */2), `safety_sweep.py`
  (orphan/protective-stop/risk-cap guard, */5), `killswitch.py` (emergency flatten). Protection is
  **exchange-side** (algo SL/TP placed at entry). Gated by `.env LIVE_TRADING_ENABLED`; per-trade $ risk,
  max concurrent, max total risk, auto-leverage all from `.env`. **Read `sync/live_exec/README.md` before
  enabling.**
- **Deploy an update (this VM):** `git pull` → if UI changed `npm run build` → if cron changed
  `crontab dag/crontab` → push code with `GITHUB_TOKEN`
  (`git push "https://x-access-token:$TOKEN@github.com/huseyin-yigit-ulker/ict-trade.git" HEAD:main`).
- **Telegram volume:** MIDAS `--sl-step 0` = every trailing change; `0.5` = milestones; `--no-telegram` = mute.
- **GitHub Action** `daily_run.yml` (01:00 UTC) exports yesterday's signals to `src/assets/data/*.json`
  and commits them (frontend's static snapshot) — independent of the VM cron.

---

## 9. Related docs
- **[MIDAS.md](MIDAS.md)** — gold stream (strategy, files, setup, changelog).
- **[dag/DEPLOY_ORACLE.md](dag/DEPLOY_ORACLE.md)** — Oracle VM provisioning.
- `sync/live_exec/README.md` — real-money executor.
- [STRATEJI-RAPORU.md](STRATEJI-RAPORU.md), [FX-GOLD-VWAP-RAPORU.md](FX-GOLD-VWAP-RAPORU.md) — strategy research.
- [README.md](README.md) — frontend + security (login gate, CSP, Supabase RLS).

---

## 10. Changelog (project-wide)

> Append a dated entry on any system-level change (newest-first). Stream-specific detail goes in the
> stream's own doc (e.g. MIDAS changes → MIDAS.md).

### 2026-06-30
- Added **MIDAS** (gold-only VWAP-trend, paper) — full stream: `sync/midas/`, UI, cron (per-minute emit +
  nightly backfill). See [MIDAS.md](MIDAS.md). Deployed on the VM + pushed to main.
- Added this **RUNBOOK.md** (project-wide system runbook).
- UI: marked **OPUS** as real-money with a distinct **Binance-gold badge** ("Binance · GERÇEK", vs green
  CANLI / amber PAPER); pinned the **Binance Canlı** nav link directly above the strategies list.

<!-- NEXT ENTRY GOES ABOVE THIS LINE -->
```
### YYYY-MM-DD — <summary> (commit <hash>)
- <what changed>
```
