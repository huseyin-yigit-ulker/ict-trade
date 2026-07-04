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
- A **real-money Binance Futures executor** trades exactly one stream on mainnet (**OPUS**); everything
  else is **paper** (signals + Telegram + dashboard only). A second executor, **MIDAS-X**
  (`sync/midas_exec/`), can place real gold orders but runs **TESTNET / dry-run only** until a
  Binance-fee simulation clears it for mainnet.
- **Telegram** alerts on formations / trade lifecycle.

Three streams are surfaced live; the rest of the "Donchian book" is backtest-only research.

| Stream | What | Live? | Money |
|---|---|---|---|
| **OPUS** (`d30so8f3h7`) | Donchian 30m breakout + 4h confirm, scale-out (60% @ +1R, runner +8R cap / BE / 7d) | ✅ | **REAL** (Binance Futures) |
| **FABLE** (`d30so8f3vg`) | OPUS twin, only taken when daily volume is contracting (vch<0.9) | ✅ | paper |
| **MIDAS** (`midas`) | Gold-only (XAUUSDT) 1m VWAP-trend pullback + 3.5×ATR trailing | ✅ | paper |
| **MIDAS-X** (`midasx`) | MIDAS as real Binance orders (maker entry + chandelier trailing) | ✅ | **TESTNET** (dry-run first; mainnet gated on a fee sim) |
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
│   ├── midas_exec/          MIDAS-X gold executor (testnet-first): executor.py, config.py, state.py,
│   │                        schema.sql, safety_sweep.py, killswitch.py, parity_report.py → see MIDAS.md §5
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
| `* * * * *` | `midas_exec/executor.py` | **MIDAS-X** reconciler (testnet; no-op until armed) |
| `*/3 * * * *` | `midas_exec/safety_sweep.py` | MIDAS-X safety guard (XAUUSDT-scoped) |

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

**Web Push / PWA (optional — native phone notifications):**
- Frontend (Vite, build-time): `VITE_VAPID_PUBLIC_KEY` — the public VAPID key the browser subscribes with.
- VM only (never exposed to the browser): `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` (a `mailto:`/`https:` contact URI).
- Generate all three with `python scripts/gen_vapid.py`. Leave unset to disable push (the emitters no-op).

**Real-money OPUS executor only** (leave unset on a paper/research box):
`LIVE_TRADING_ENABLED`, `BINANCE_TESTNET`, `BINANCE_TESTNET_API_KEY/SECRET` (+ mainnet keys), `EXEC_*`
(`EXEC_NAME/VERSION/ENABLED_SYMBOLS/DRY_RUN`), `RISK_PER_TRADE_USD`, `MAX_TOTAL_RISK_USD`,
`MAX_CONCURRENT_POSITIONS`, `LEVERAGE`/`LEVERAGE_MAX`/`AUTO_LEVERAGE`, `MARGIN_TYPE`, `LIVE_ENTRY_MODE`,
`CLOSE_FRAC`, `HORIZON_DAYS`, `RUNNER_CAP_R`, `DCH_ENTRY_AT_CONFIRM`, `DCH_SO_RUNNER_CAP`.

**MIDAS-X gold executor only** (testnet-first; leave unset on a paper box): `MIDAS_EXEC_ENABLED`,
`MIDAS_EXEC_DRY_RUN`, `MIDAS_BINANCE_TESTNET` (MIDAS's own network flag, independent of `BINANCE_TESTNET`),
`MIDAS_RISK_PER_TRADE_USD`, `MIDAS_LEVERAGE`, `MIDAS_MARGIN_TYPE`, `MIDAS_MAKER_ENTRY`,
`MIDAS_ENTRY_TIMEOUT_SEC`, `MIDAS_ENTRY_MAX_SLIP_R`, `MIDAS_SL_DEADBAND_TICKS`, `MIDAS_EXEC_VERSION`,
`MIDAS_EXEC_NAME` (+ shares `LIVE_TRADING_ENABLED`, `BINANCE_TESTNET_API_KEY/SECRET`). Full list:
`sync/midas_exec/.env.example`.

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

- **Logs:** `tail -f ~/ict-{donchian,midas,midas-exec,sync,exec}.log`.
- **Real-money executor (OPUS):** `sync/live_exec/` — `executor.py` (reconciler, */2), `safety_sweep.py`
  (orphan/protective-stop/risk-cap guard, */5), `killswitch.py` (emergency flatten). Protection is
  **exchange-side** (algo SL/TP placed at entry). Gated by `.env LIVE_TRADING_ENABLED`; per-trade $ risk,
  max concurrent, max total risk, auto-leverage all from `.env`. **Read `sync/live_exec/README.md` before
  enabling.**
- **MIDAS-X gold executor (testnet-first):** `sync/midas_exec/` — `executor.py` (reconciler, every min),
  `safety_sweep.py` (*/3, XAUUSDT-scoped), `killswitch.py` (`--status/--flatten/--halt`; `--halt` flips
  `MIDAS_EXEC_ENABLED` only — OPUS untouched). Separate DB tables + `MIDAS_*` env; testnet uses a
  synthetic bracket. Gated by `LIVE_TRADING_ENABLED` **and** `MIDAS_EXEC_ENABLED` **and**
  `MIDAS_EXEC_DRY_RUN=false`. **Do NOT set `MIDAS_BINANCE_TESTNET=false` (mainnet) until the Binance-fee
  simulation passes** — MIDAS is −92R on taker. See MIDAS.md §5.
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

### 2026-07-04
- **Binance Canlı now shows funding-fee paid on open positions.** Perps settle funding every 8h and
  it is NOT part of `userTrades.realizedPnl`, so it was invisible. New `BinanceFutures.income()`
  (`/fapi/v1/income`, `incomeType=FUNDING_FEE`); both executors (`sync/live_exec/executor.py` OPUS +
  `sync/midas_exec/executor.py` MIDAS-X) sum funding **since the position's `entry_fill_time`** and write
  it to a new `ict_trade.live_account_snapshot.funding_fee` column (`<0` = we paid). Dashboard: a
  **Funding** column per open position + a **Funding (açık)** KPI on the OPUS "Binance Canlı" page, and
  the same column on the MIDAS-X "Binance Paper · Altın" page. Read-only (browser never signs a request).
  - **Ops:** the `funding_fee` column is added by an idempotent `alter table … add column if not exists`
    already applied to the live DB (also baked into `sync/live_exec/schema.sql` + `sync/midas_exec/schema.sql`
    for fresh installs); anon SELECT grant already covers the new column. Rebuild/redeploy the dashboard
    off-box (Render) to serve the new UI. No cron/env change.
- **PUSU is now an installable mobile app (PWA) + native Web Push.** No new hosting/accounts/Mac — the
  existing Render static host + Supabase + the Oracle VM cover everything; Web Push uses VAPID directly
  (no Apple Developer / Firebase).
  - **Installable PWA:** `vite-plugin-pwa` (`injectManifest`, custom `src/sw.js`) + web app manifest +
    icons (`public/icons/*`, generated from `public/pusu.svg` via `scripts/gen_pwa_icons.py`) + iOS
    home-screen meta tags in `index.html`. SW precaches the app **shell only**; Supabase/Binance/CoinGecko
    are left on the network (never stale trading data). CSP (`vite.config.js`) gained `api.coingecko.com`
    (fixes a latent block), `worker-src`, `manifest-src`.
  - **Mobile UX pass:** the sidebar becomes a slide-in **drawer** on phones (`AppShell`/`Topbar`/`Sidebar`
    + `mobileNav*` state in `TradeContext`); full-screen modals, ≥44px touch targets, scrollable dense
    tables, and `env(safe-area-inset-*)` for notch/home-indicator in `src/assets/css/style.css` (new
    ≤768px tier; the 820px icon-rail bounded to 769–820px).
  - **Web Push:** Settings ▸ *Bildirimler* toggle (`src/utils/push.js`) subscribes and stores the
    subscription in `ict_trade.push_subscriptions` (`supabase/push_subscriptions_schema.sql`). The VM
    sender `sync/push_notify.py` (`pywebpush`) fans out **alongside Telegram** from `sync/donchian/canli.py`
    + `sync/midas/canli.py` (guarded, best-effort; prunes dead endpoints). **No new cron line.**
  - **Ops to activate (all safe no-ops until done):**
    1. `python scripts/gen_vapid.py` → put `VITE_VAPID_PUBLIC_KEY` in the frontend env, `VAPID_PRIVATE_KEY`
       + `VAPID_SUBJECT` in the VM `.env`.
    2. Apply `supabase/push_subscriptions_schema.sql` in the live Supabase SQL editor.
    3. VM: `pip install -r requirements.txt` (adds `pywebpush`).
    4. Build the dashboard on a Node box (`npm install` picks up `vite-plugin-pwa`, then `npm run build`)
       and deploy `dist/`. **iOS push requires the PWA be Added to Home Screen first (iOS 16.4+).**
    5. Render (recommended): add a no-cache header rule for `/sw.js`, `/registerSW.js`, `/manifest.webmanifest`,
       `/index.html` so shell/version updates propagate.

### 2026-06-30
- Added **MIDAS** (gold-only VWAP-trend, paper) — full stream: `sync/midas/`, UI, cron (per-minute emit +
  nightly backfill). See [MIDAS.md](MIDAS.md). Deployed on the VM + pushed to main.
- Added this **RUNBOOK.md** (project-wide system runbook).
- UI: marked **OPUS** as real-money with a distinct **Binance-gold badge** ("Binance · GERÇEK", vs green
  CANLI / amber PAPER); pinned the **Binance Canlı** nav link directly above the strategies list.

### 2026-07-02
- Added **MIDAS-X** (`sync/midas_exec/`) — a real-money-capable Binance executor for the gold stream,
  running **TESTNET / dry-run first**. Reads the `mode='midas'` signals and drives a post-only maker
  entry + 3.5×ATR chandelier trailing exit via `strategy.track_open` (live == paper by construction).
  Separate DB tables (`ict_trade.midas_positions/midas_orders`), `MIDAS_*` env, and an XAUUSDT-scoped
  killswitch/safety-sweep — fully isolated from the OPUS executor (never cross-flatten). Added 2 cron
  lines (both no-op until `LIVE_TRADING_ENABLED` + `MIDAS_EXEC_ENABLED` + `MIDAS_EXEC_DRY_RUN=false`).
- Additive fix to `sync/live_exec/exchange_info.py`: gold is a `TRADIFI_PERPETUAL` (not `PERPETUAL`) —
  added `is_tradable(sym, allow=…)`; OPUS's `is_tradable_perp` unchanged. Verified mainnet + testnet.
- **Cost caveat unchanged:** MIDAS is +142R on FX cost but ≈ −92R on Binance taker; MIDAS-X stays
  testnet/paper until a Binance-fee simulation shows a positive net-of-fee edge (MIDAS.md §5). OPUS
  remains the only mainnet real-money stream. Parity gate PASS (531/531 settled 2026 trades, 0 mismatches).
- **Account prerequisite:** gold is a `TRADIFI_PERPETUAL` → the trading account must accept Binance's
  **"TradFi-Perps agreement"** once (testnet + mainnet) or every XAU order returns `-4411`. See MIDAS.md §5.

### 2026-07-03
- Fix: the **Binance Canlı** page (`src/pages/LivePositionsPage.jsx`) still computed the locked-R / TP1
  split with the OLD `d30so6c` economics (`closeFrac 0.6`, `CAP_R 6`), but the live executor runs
  `d30so8f3h7` (`.env CLOSE_FRAC=0.3`, `RUNNER_CAP_R=8`). It overstated the runner's locked floor ~2×
  (showed +0.60R vs the real +0.30R). Set `CAP_R=8`, `SO.closeFrac=0.3`, and the header badge to
  `d30so8f3h7 · +8R · %30 TP1`. Verified against the live ETH RUNNER: `tp1_qty 0.04 / qty 0.135 = 29.6%`
  (≈30%), locked now +0.30R ($1.40) = the actual booked TP1 leg ($1.385, floor of 0.0405→0.04).

<!-- NEXT ENTRY GOES ABOVE THIS LINE -->
```
### YYYY-MM-DD — <summary> (commit <hash>)
- <what changed>
```
