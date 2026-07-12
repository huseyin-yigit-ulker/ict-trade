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
- **Two real-money Binance Futures executors**: **OPUS** (`sync/live_exec/`) and — since 2026-07-07 —
  **MIDAS-X** (`sync/midas_exec/`, gold, $3 risk, maker GTX entry, exchange-side trailing stop,
  AFTER-LOSS gate). Everything else is **paper** (signals + Telegram + dashboard only).
- **Telegram** alerts on formations / trade lifecycle.

Three streams are surfaced live (**OPUS + MIDAS** real-money capable, user decision 2026-07-07;
**TALOS** paper-only, added later the same day); FABLE and the rest of the "Donchian book" are
backtest-only research (opt-in lab surfaces).

| Stream | What | Live? | Money |
|---|---|---|---|
| **OPUS** (`d30so8f3h7`) | Donchian 30m breakout + 4h confirm, scale-out (60% @ +1R, runner +8R cap / BE / 7d) | ✅ | **REAL** (Binance Futures) |
| **MIDAS** (`midas`) | Gold-only (XAUUSDT) 1m VWAP-trend pullback + 3.5×ATR trailing (paper signal feed) | ✅ | paper feed |
| **TALOS** (`talos`) | Gold-only (XAUUSDT) 1m Keltner-trend: DEEP pullback to the 15m EMA20±0.75·ATR band + the same 3.5×ATR trailing engine as MIDAS (shared code) | ✅ | paper feed |
| **TALOS-X** (`talosx`) | TALOS as real Binance TESTNET orders (maker GTX + 60s taker fallback; tick-level step-by-step trailing stop) | ✅ | **paper** (testnet-locked: env + DB CHECK) |
| **MIDAS-X** (`midasx`) | MIDAS as real Binance orders (maker GTX entry + exchange-side trailing SL + after-loss gate) | ✅ | **REAL mainnet** since 2026-07-07 ($3 risk; wallet shared with OPUS) |
| **FABLE** (`d30so8f3vg`) | OPUS twin, only taken when daily volume is contracting (vch<0.9) | backtest-only (live emit retired 2026-07-07) | — |
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
│   ├── talos/               TALOS gold stream (Keltner sibling of MIDAS): strategy.py
│   │                        (imports the MIDAS walk/trailing engine), backfill.py, canli.py
│   ├── talos_exec/          TALOS-X testnet executor (verbatim sibling of midas_exec/: own
│   │                        talos_positions/talos_orders tables + killswitch; testnet-locked)
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
| `0 * * * *` | `donchian/canli.py --emit --no-telegram` (1h breakout, silent — feeds nightly `donchianc` resolve) | Donchian 1h |
| `0,30 * * * *` | `donchian/canli.py --emit --tf 30m --confirm-htf 4h --name OPUS` | **OPUS** emit |
| `0,30 * * * *` | `… --rr 6 --no-telegram` | 6R twin (silent) |
| `* * * * *` | `midas/canli.py --emit --lookback-min 3 --sl-step 0` | **MIDAS** emit + trailing track + Telegram |
| `30 0 * * *` | `sync_daily.py --stream all` | nightly resolve (all streams) |
| `45 0 * * *` | `sync_daily.py --stream d30_4h_so` (cap 6) | scale-out 6R |
| `0 1 * * *` | `sync_daily.py --stream d30_4h_so` (cap 8) | scale-out 8R |
| `30 2 * * *` | `donchian/atrx_backfill.py --apply` | **OPUS·SQZ + OPUS·Q5** backtest refresh (ATRX-kapılı OPUS ikizleri, dinamik 18+83 sembol evreni, 2026-07-12) |
| `20 1 * * *` | `volgate_backfill.py --apply` | FABLE backtest refresh (live emit retired 2026-07-07; re-enable command in the crontab comment) |
| `30 1 * * *` | `midas/backfill.py --apply` | MIDAS backtest refresh |
| `* * * * *` (+30s) | `talos/canli.py --emit --lookback-min 3 --sl-step 0` | **TALOS** emit + trailing track + Telegram |
| `40 1 * * *` | `talos/backfill.py --apply` | TALOS backtest refresh |
| `* * * * *` (+42s) | `talos_exec/executor.py` | **TALOS-X** reconciler (Binance **TESTNET**/paper) |
| `*/3 * * * *` (+55s) | `talos_exec/safety_sweep.py` | TALOS-X safety guard (XAUUSDT-scoped, testnet) |
| `*/2 * * * *` | `live_exec/executor.py` | **REAL-MONEY** OPUS reconciler |
| `*/5 * * * *` | `live_exec/safety_sweep.py` | executor safety guard |
| `* * * * *` | `midas_exec/executor.py` | **MIDAS-X** reconciler (**REAL-MONEY mainnet** since 2026-07-07) |
| `*/3 * * * *` | `midas_exec/safety_sweep.py` | MIDAS-X safety guard (XAUUSDT-scoped) |
| `* * * * *` (+40s) | `users/verify_keys.py` | multi-user API-key verification |
| `* * * * *` (+45s) | `push_notify.py --drain` | personal Web-Push outbox drain |

Logs: `~/ict-donchian.log`, `~/ict-midas.log`, `~/ict-talos.log`, `~/ict-midas-exec.log`,
`~/ict-talos-exec.log`, `~/ict-sync.log`, `~/ict-exec.log`, `~/ict-users.log`.

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

**TALOS-X testnet executor** (namespaced `TALOS_*`, mirrors the `MIDAS_*` set): `TALOS_EXEC_ENABLED`,
`TALOS_EXEC_DRY_RUN`, `TALOS_BINANCE_TESTNET` (**stays true — mainnet is double-locked**: this env
default + migration 014's `talos_testnet_only` CHECK), `TALOS_RISK_PER_TRADE_USD` (5), plus the same
entry/trailing knobs (`TALOS_ENTRY_TAKER_FALLBACK_SEC` etc.).

**MIDAS-X gold executor only** (leave unset on a paper box): `MIDAS_EXEC_ENABLED`,
`MIDAS_EXEC_DRY_RUN`, `MIDAS_BINANCE_TESTNET` (MIDAS's own network flag, independent of `BINANCE_TESTNET`;
**false = mainnet real money since 2026-07-07**), `MIDAS_RISK_PER_TRADE_USD` (mainnet: 3),
`MIDAS_LEVERAGE`/`MIDAS_AUTO_LEVERAGE`/`MIDAS_LEVERAGE_MAX`, `MIDAS_MARGIN_TYPE`, `MIDAS_MAKER_ENTRY`,
`MIDAS_ENTRY_TIMEOUT_SEC`, `MIDAS_ENTRY_MAX_SLIP_R`, `MIDAS_ENTRY_TAKER_FALLBACK_SEC` (maker→taker fallback, default 60; 0=kapalı), `MIDAS_SL_DEADBAND_TICKS`,
`MIDAS_EXEC_AFTER_LOSS_ONLY` (enter only if the previous same-fx-day paper trade closed negative),
`MIDAS_EXEC_VERSION`, `MIDAS_EXEC_NAME` (+ shares `LIVE_TRADING_ENABLED`, Binance key pairs). Full list:
`sync/midas_exec/.env.example`.

**Multi-user layer (2026-07-04 — §8a):**
- VM: `EXEC_PRIV_KEY_PATH` (RSA private PEM decrypting user API keys, `scripts/gen_exec_keypair.py`;
  **never** in the repo), `EXEC_MULTI_USER` (false = legacy single-env account; flip to true ONLY in the
  §8a Phase-5 cutover window — both OPUS and MIDAS-X executors read the same flag).
- Render (frontend build): `VITE_EXEC_PUBKEY_B64` (the SPKI-b64 public key printed by the generator;
  the browser RSA-OAEP-encrypts user-submitted Binance keys with it), optional `VITE_VM_EGRESS_IP`
  (shown in the UI as the IP to whitelist on Binance keys).

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

**Fresh DATABASE too? (not just a fresh box)** The two Supabase DBs are external and normally persist —
a machine move does NOT touch them. Only if you are standing up a brand-new Supabase project as well:
1. Live DB: apply `supabase/migrations/001..012` **in order** via
   `.venv/bin/python sync/users/apply_sql.py --file supabase/migrations/<f>.sql` (001–005a, 008–012 are
   additive; 005b+007 are the Phase-5/6 cutover pair — see §8a), then `apply_sql.py --seed-universe`,
   plus `supabase/push_subscriptions_schema.sql`, `sync/live_exec/schema.sql`, `sync/midas_exec/schema.sql`.
2. Backtest DB: `ict_trade.trading_signals` per `supabase/` schema; then re-run the §7-step-4 backfills.
3. Recreate the owner: sign up in the UI → `sync/users/seed_owner.py --email <owner>` (admin+canonical+keys).

---

## 7a. MIGRATE the system to a NEW machine (cutover checklist)

Everything durable lives OFF the box (Supabase DBs, GitHub repo, Render frontend, Telegram) — the VM is
**stateless except `.env`, the RSA private key, and the crontab**. A move is therefore: bring up the new
box (§7), copy the secrets, swap the cron. ~15 min of executor downtime, no data loss.

```bash
# ON THE OLD BOX ─ freeze real-money activity first
.venv/bin/python sync/live_exec/killswitch.py --status         # note open positions (they stay open on
.venv/bin/python sync/midas_exec/killswitch.py --status        #  Binance — exchange-side SL protects them)
crontab -l > /tmp/crontab.old && crontab -r                    # STOP the loop (executors, emitters, all)

# COPY the secrets the repo does NOT carry:
#   1. .env                (repo root — all §6 keys)
#   2. the RSA private key (path in .env EXEC_PRIV_KEY_PATH — decrypts user API keys; NOT recoverable
#                           from the DB. If lost: regenerate keypair + every user re-enters keys)
scp .env $NEW:~/ict-trade/.env
scp <EXEC_PRIV_KEY_PATH> $NEW:<same path as in .env>

# ON THE NEW BOX ─ §7 steps 0–5 (clone, .env in place, setup_vm.sh, smoke-test emitters dry-run)
# ⚠️ the new box's egress IP must be EU/Binance-reachable AND whitelisted on the Binance API keys
#    (owner keys + every multi-user key: users re-whitelist or temporarily drop the IP restriction).
#    Update the Render env VITE_VM_EGRESS_IP so the UI shows users the new IP to whitelist.
.venv/bin/python sync/live_exec/executor.py                    # one manual tick: must reconcile the
.venv/bin/python sync/midas_exec/executor.py                   #  open positions noted via --status above
crontab dag/crontab                                            # start the loop on the NEW box

# DECOMMISSION the old box: watch new-box logs for 2 clean ticks → old box stays cron-less → terminate.
```

Notes:
- **Never let both boxes run cron simultaneously** — two reconcilers on one Binance account will fight
  (duplicate orders / double cancels). `crontab -r` on the old box BEFORE arming the new one is the hard rule.
- Open positions survive the move: protection is exchange-side (algo SL / STOP_MARKET), and the executors
  rebuild state from DB + Binance on their first tick (coid-based reconcile).
- The dashboard (Render), both DBs, and the GitHub Action are untouched by a VM move.
- Nothing points AT the VM (no inbound service) — only its outbound egress IP matters
  (Binance whitelist + `VITE_VM_EGRESS_IP`).

---

## 8. Operations & safety

- **Logs:** `tail -f ~/ict-{donchian,midas,midas-exec,sync,exec}.log`.
- **Real-money executor (OPUS):** `sync/live_exec/` — `executor.py` (reconciler, */2), `safety_sweep.py`
  (orphan/protective-stop/risk-cap guard, */5), `killswitch.py` (emergency flatten). Protection is
  **exchange-side** (algo SL/TP placed at entry). Gated by `.env LIVE_TRADING_ENABLED`; per-trade $ risk,
  max concurrent, max total risk, auto-leverage all from `.env`. **Read `sync/live_exec/README.md` before
  enabling.**
- **MIDAS-X gold executor (REAL-MONEY mainnet since 2026-07-07):** `sync/midas_exec/` — `executor.py`
  (reconciler, every min), `safety_sweep.py` (*/3, XAUUSDT-scoped), `killswitch.py`
  (`--status/--flatten/--halt`; `--halt` flips `MIDAS_EXEC_ENABLED` only — OPUS untouched). Separate DB
  tables + `MIDAS_*` env. Gated by `LIVE_TRADING_ENABLED` **and** `MIDAS_EXEC_ENABLED` **and**
  `MIDAS_EXEC_DRY_RUN=false`. Mainnet config (user decision, MIDAS.md 2026-07-07 (3)): $3 risk,
  maker GTX entry, auto-leverage (25x cap), exchange-side STOP_MARKET trailing (cancel/replace),
  AFTER-LOSS gate (`MIDAS_EXEC_AFTER_LOSS_ONLY=true`); wallet shared with OPUS — if margin is short the
  entry is skipped (fail-safe). Economics caveat: taker+taker 2026 ≈ +27R/PF1.09 (after-loss +54R) and
  multi-year OOS is negative — this is a deliberately small-risk live experiment, not a proven edge.
  Rollback: `user_stream_settings` midas/mainnet `enabled=false` or `MIDAS_BINANCE_TESTNET=true`.
- **Deploy an update (this VM):** `git pull` → if UI changed `npm run build` → if cron changed
  `crontab dag/crontab` → push code with `GITHUB_TOKEN`
  (`git push "https://x-access-token:$TOKEN@github.com/huseyin-yigit-ulker/ict-trade.git" HEAD:main`).
- **Telegram volume:** MIDAS `--sl-step 0` = every trailing change; `0.5` = milestones; `--no-telegram` = mute.
- **GitHub Action** `daily_run.yml` (01:00 UTC) exports yesterday's signals to `src/assets/data/*.json`
  and commits them (frontend's static snapshot) — independent of the VM cron.

---

## 8a. Multi-user (kayıt/giriş + kişisel API key + kullanıcı-bazlı execution)

Shipped 2026-07-04. Signals stay CENTRAL (one emitter set); execution fans out per user.

**Model:** Supabase Auth (GoTrue) e-posta+şifre; signup → `ict_trade.profiles` satırı `pending`
(trigger `on_auth_user_created`) → admin `/admin`'den onaylar. Kullanıcı `/trading`'de Binance
mainnet/testnet API anahtarlarını girer — tarayıcı **RSA-OAEP-SHA256** ile şifreler
(`VITE_EXEC_PUBKEY_B64`), DB'ye SADECE ciphertext yazılır (`ict_trade.user_api_keys`, client'a
SELECT yok; okuma sadece sanitize `user_api_keys_public` view'ı). VM her dakika doğrular
(`sync/users/verify_keys.py`: bakiye, futures yetkisi, one-way mod; **withdrawal yetkili anahtar
REDDEDİLİR**). Aktivasyon/risk/semboller `ict_trade.user_stream_settings` (OPUS mainnet+testnet,
MIDAS testnet-only — DB CHECK + fee analizi, MIDAS.md §5). Sert kurallar DB trigger'ında
(`tg_uss_guard`): geçerli anahtar şart, `risk×max_concurrent ≤ bakiye×%25`, hedge-mod reddi,
sembol ⊆ `stream_universe`. Kill-switch (`kill_requested`) executor'ın ilk gate'i: flatten + disable.
Günlük zarar limiti (`daily_loss_cap_usd`) aşılınca o gün yeni giriş yok. Kişisel bildirimler:
executor → `push_outbox` → `push_notify.py --drain` → kullanıcının push abonelikleri
(`push_subscriptions.user_id`). Telegram = sadece owner/canonical kanal (değişmedi);
`trading_signals` writeback'i de sadece `profiles.is_canonical=true` (owner) için akar.

**Dosyalar:** `supabase/migrations/001..007` (idempotent; 005b+007 sıralı-fazlı), `sync/users/`
(crypto/store/verify_keys/seed_owner/apply_sql), `scripts/gen_exec_keypair.py`; executor'lar
çift-modlu (`EXEC_MULTI_USER=false` → bugünkü tek-hesap davranış birebir).

**Kurulum sırası (fazlar; ayrıntı: plan dosyası + migration başlıkları):**
1. ✅ `apply_sql.py --phase1` + `--seed-universe` (additive; 2026-07-04'te uygulandı).
2. Supabase dashboard: Authentication → Sign In/Up → Email → **"Confirm email" KAPAT** (admin onayı
   var; kapatılmazsa signup'lar mail onayına takılır). Site URL = Render domain, şifre min ≥10.
3. Render env: `VITE_EXEC_PUBKEY_B64` ekle → deploy (git push zaten tetikler).
4. Owner UI'dan kayıt olur → `seed_owner.py --email ugur_yigit@hotmail.com` (admin+canonical yapar,
   .env anahtarlarını şifreli içeri alır, inline doğrular, bugünkü risk/sembol ayarlarını yazar).
5. **Faz-5 cutover (≤10 dk, saat :05–:25):** `killswitch.py --halt` → `seed_owner.py --email ... --backfill`
   → `apply_sql.py --file supabase/migrations/005b_user_scope_indexes.sql` → `.env EXEC_MULTI_USER=true`
   → `LIVE_TRADING_ENABLED=true` geri aç → `~/ict-exec.log`'da 2 tick izle (owner pozisyonları AYNI
   coid'lerle devam etmeli). Rollback: `EXEC_MULTI_USER=false`.
6. Faz-6: frontend zaten JWT'yle okuyor → `apply_sql.py --file supabase/migrations/007_rls_tighten.sql`
   (live_positions/midas_positions/account tabloları kullanıcıya-özel olur, anon push policy'leri düşer).
7. **008 (2026-07-05, additive): ✅ UYGULANDI (2026-07-05, apply_sql.py ile — auth.users yetkisi sorunsuz).**
   `user_prefs` (tema/dil/açılış sayfası + bildirim tercihleri) + `user_features` (admin'in kullanıcı-başına
   backtest/istihbarat/işlem yüzeyi kapatması) + `admin_set_features` / `admin_delete_user` RPC'leri.

**Cron ekleri (kurulu):** `verify_keys.py` (*/1 +40s) + `push_notify.py --drain` (*/1 +45s) → `~/ict-users.log`.
**Kill:** kullanıcı UI'dan; admin `/admin`'den veya `killswitch.py --flatten --user <email>`.

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

### 2026-07-12
- **OPUS·SQZ + OPUS·Q5: ATRX-kapılı OPUS ikizleri (backtest-only) ana işlem menüsünde.**
  - 2026-07-12 sembol-durum çalışması (101 Binance kripto perp × 39 bakışsız senaryo, 2024-25
    dinamik-evren OOS doğrulamalı; scriptler `scratchpad/opus_scn_*.py` + `opus_dyn_*.py`):
    hacim/momentum/dip-tepe koşullarının HEPSİ yıldan yıla işaret değiştirdi; üç yılda da tutan
    tek durum **günlük ATRX = ATR(5)/ATR(20)** (D-1 kapanışı, bakışsız) idi.
  - Yeni backtest versiyonları (OPUS sinyal+çıkış modeli birebir, yalnız sembol-durum kapısı):
    **`d30so8f3sq` / OPUS·SQZ / PYXIS** — ATRX<0.8 squeeze-only (WR oyunu: WR %55-59 her yıl);
    **`d30so8f3q5` / OPUS·Q5 / CARINA** — ATRX≤1.25 genişleme-atla (totR oyunu: üç yılda da
    baseline üstü). Motor: `sync/donchian/atrx_backfill.py` (`--dry-run`/`--apply`, DELETE+upsert
    idempotent, tek event-build'den iki versiyon türetir).
  - UI: Sidebar backtest bölümü + streamMask CODENAMES (PYXIS/CARINA) + adminStreamInfo
    REAL_NAMES/REAL_LABELS + `strategyInfo.js`'e iki TAM detaylı kart (tr+en: kapı tanımı,
    çalışma gerekçesi, 3-yıl sayılar, bedel/karşılaştırma, caveat) + TradeContext 4 harita +
    push_notify maskeleri. Canlı OPUS'a ve LIVE_STREAM_KEYS'e dokunulmadı.
  - ✅ Cron KURULU (2026-07-12): `30 2 * * * cd $HOME/ict-trade && .venv/bin/python
    sync/donchian/atrx_backfill.py --apply >> $HOME/ict-sync.log 2>&1`.

### 2026-07-12 (2)
- **ATRX ikizlerinin evreni GENİŞLETİLDİ: "kapıyı geçen her sembol sinyal üretsin".**
  - `atrx_backfill.py` artık DİNAMİK evren koşar: çekirdek 18 kripto-perp (kitap 2024-01'den) +
    83 ek Binance kripto-perp (kitap 2026-01'den — paylaşımlı 1m cache'in başladığı yer;
    hisse-perp + metal hariç). Delisted/veri-yok semboller per-symbol try/except ile atlanır.
  - Cron 01:10 → **02:30**'a taşındı (101-sembollük iş 01:20-01:50 backfill kümesiyle
    çakışmasın). strategyInfo kartları + adminStreamInfo etiketleri dinamik evreni anlatacak
    şekilde güncellendi (83 sembol yalnız 2026 kitabına katkı verir — caveat'ta belirtildi).

### 2026-07-11 (7)
- **Kullanıcı modunda grafik varsayılanı NATIVE + istihbarat paneli sızıntı düzeltmesi.**
  - Sinyal kartına tıklayınca artık TV embed'i değil **PUSU native grafiği** açılır
    (giriş/TP/SL/Ters-Onay overlay'li) — `UserShell` mount'ta `setChartView('chart')`;
    kullanıcı modal içi toggle'dan TV'ye yine geçebilir. Admin davranışı değişmedi.
  - **GİZLİLİK FİX:** ChartModal bilgi panelindeki motor-içi satırlar (ham
    `Strateji: DONCHIAN_BO`, Kalite, Konfluens, HTF/LTF) HERKESE görünüyordu —
    artık `sd.isAdmin` kapılı. Emülatörde assert: TV iframe=0, DONCHIAN_BO=0.

### 2026-07-11 (6)
- **Kullanıcı modu: işleme tıklayınca GRAFİK + Sinyaller'e haftalık karne.**
  - **TradeChart** (`src/components/user/TradeChart.jsx`, lightweight-charts): pozisyonun
    ömrünü mum grafikte çizer — Giriş/SL/TP1/Hedef seviye çizgileri (nötr etiketler,
    maskeye uygun; altında iz-süren SL) + giriş oku ve "Çıkış ±R" işareti. Binance klines,
    pencereye göre 1m→4h otomatik kabalaşır. `LivePositionModal`'a `showChart` prop'u
    eklendi — **yalnız kullanıcı sayfaları (Portföy/İşlemler) true geçer**; admin panoları
    default false ile eski davranışta (da42fb1 "kart yeterli" admin'de korunur).
  - **Haftalık karne (Sinyaller):** filtrelerin altında kompakt şerit — Son 7 gün toplam R
    (scale-out: `scaleOutLiveR` statü modeli; iz-sürenlerde nightly `pnlR`), Kazanma %,
    TP/SL sayısı, Aktif sayısı. statusFilter'dan bağımsız hesaplanır.

### 2026-07-11 (5)
- **Admin tam-sayfa UI denetimi (web+mobil, emülatör) + düzeltmeler.** 10 sayfa × 2 cihaz
  mock-verili Playwright turuyla tarandı (`scratchpad/admin_audit.mjs`, ekranlar
  `scratchpad/audit/`); hiçbir sayfada yatay taşma yok.
  - **Topbar route-duyarlı yapıldı (en büyük bulgu):** başlık ve TP/SL/sembol filtreleri
    her sayfada strateji görünümüne kilitliydi — /admin'de bile "OPUS · Canlı" + filtre
    şeridi görünüyordu. Artık başlık haritası (/admin=Yönetim, /binance=Binance Canlı,
    /trading=İşlem Merkezi, /total, /binance-paper, /binance-altin) ve filtreler YALNIZ
    /:strategy/:mode görünümünde (Topbar.jsx).
  - **Yönetim'e yeni kontrol:** "Yeni Üye Özeti" bayrak çipi — `app_flags.newuser_digest`
    admin panelinden aç/kapa (admin_set_flag; Açık İşlem Özeti çipinin ikizi).
  - **ChartModal mobil:** Kapat butonu ile mum/çizgi toggle'ının üst üste binmesi
    giderildi (chart-header-top sağ boşluk); Kapat 10px köşe.

### 2026-07-11 (4)
- **Admin arayüzü modern yenileme (yalnız görünüm).** `style.css` sonuna tek override bloğu
  ("ADMIN MODERN REFRESH"): kartlar 6→14px köşe + yumuşak sınır + hover, kpi-hero 16px,
  Topbar yarı saydam + blur (user header ile aynı dil), Sidebar nav hap (10px, sol çizgi
  kaldırıldı), buton/girdi köşeleri 10px, durum filtreleri pill, livex tablo/KPI kutuları
  12px, masaüstü modallar 16px (mobil tam-ekran davranışı değişmedi). DOM/yerleşim/işlev
  AYNEN; geri almak = bloğu silmek. Mock-admin emülatör turuyla masaüstü+iPhone doğrulandı.

### 2026-07-11 (3)
- **Yeni kullanıcı paketi 2: Yardım/SSS + önce-Paper önerisi + ilk-hafta günlük özet push'u.**
  - **Yardım & SSS** (`/yardim`, `src/pages/user/HelpPage.jsx`): 8 soruluk statik mini rehber
    (nasıl çalışır / güvenlik / risk / durdurma / ücretler / Paper / bildirim / sinyaller) —
    anonimleştirme sınırına uygun (strateji mekaniği yok). Girişler: Profil üstü kısayol
    kartı + Kurulum Adımları kartı alt linki + Bot'taki Paper kartı.
  - **Önce-Paper önerisi** (BotPage): hiç akış çalışmıyorken 💡 kart — testnet.binancefuture.com
    anahtar linki + Paper ağıyla risksiz deneme yönlendirmesi.
  - **İlk-hafta günlük özeti** (`sync/newuser_digest.py` + cron `5 18 * * *`, canlı crontab'a
    KURULDU): ilk API anahtarı ≤7 gün olan, push-abonelikli kullanıcılara akşam tek push —
    "Bugün: N işlem, ±$X · Açık: M pozisyon · Toplam: ±$Y" (kind='system', user_prefs'e uyar;
    aktivite yoksa 3. günden sonra susar). Salt-okunur/best-effort; `app_flags 'newuser_digest'`
    ile kapatılır. Teslimat mevcut push_outbox --drain kuyruğundan. Dry-run doğrulandı.

### 2026-07-11 (2)
- **Yeni kullanıcı onboarding'i: Portföy'de "Kurulum Adımları" kartı.**
  `src/components/user/OnboardingCard.jsx` — 4 canlı adım, kullanıcının kendi satırlarından
  otomatik işaretlenir: ① hesap onayı (`profiles.status`) ② API anahtarı
  (`user_api_keys_public`; `pending_verify` → "doğrulanıyor…") ③ akış başlat
  (`user_stream_settings.enabled+symbols`) ④ bildirimleri aç (push aboneliği —
  karttan tek dokunuşla `enablePush`; SW/push desteklenmiyorsa adım gizli, `pushState`
  1.5s zaman-aşımı korumalı). İlerleme çubuğu + aktif adım vurgusu; 4/4 olunca kart
  kendini gizler. Eski statik "Botu kurun" CTA'sının yerini aldı; `SETTINGS_EVT` ile
  canlı tazelenir. İşlemler boş-durumuna "Botu kurun →" butonu eklendi. ~15 yeni EN
  çevirisi. Emülatör senaryoları: `scratchpad/newuser_shots.mjs` (taze / onay bekleyen /
  anahtar-doğrulanıyor) — ekranlar `scratchpad/usermode/newuser_*.png`.

### 2026-07-11
- **ROL AYRIMLI ARAYÜZ: admin-dışı kullanıcılar Binance-tarzı 4 sekmeli basit kabuğa taşındı.**
  Router seviyesinde rol çatalı (`src/AppRoutes.jsx`): **admin = mevcut arayüzün tamamı birebir**
  (eski `App.jsx` rota ağacı `AdminRoutes`'a taşındı, sıfır davranış değişikliği); **user =
  yeni `UserShell`** (`src/components/user/`, `src/pages/user/`, `src/assets/css/user.css`):
  - Sekmeler: **Portföy** (`/portfoy` — toplam bakiye + göz-gizle + açık pozisyon kartları +
    son işlem teaser'ı), **İşlemler** (`/islemler` — açık/kapalı filtre + özet şerit +
    `LivePositionModal` paylaşım kartı), **Sinyaller** (`/sinyaller` — kod adlı akış çipleri
    ATLAS/SIRIUS/MENKAR, gün gruplu sinyal kartları, tık → mevcut `ChartModal`), **Bot**
    (`/bot` — hero durum kartı + MEVCUT İşlem Merkezi kartları aynen; İnce Ayar katlanır).
    Profil (`/profil`) header avatarında → `SettingsPage` sarmalayıcı. Mobil ≤768px alt sekme
    çubuğu, masaüstü slim üst-nav.
  - Kullanıcıya kapanan yüzeyler: strateji hub'ı, `/trend`, `/total`, `/:strategy/:mode`,
    araştırma/backtest, `/admin`, `/intelligence` → hepsi `/portfoy`'a redirect. Push/bookmark
    alias'ları: `/binance(-paper)`→`/portfoy`, `/binance-altin`→`/islemler`, `/trading`→`/bot`,
    `/settings`→`/profil`. Varsayılan giriş: user `/portfoy`, admin `/` (değişmedi).
  - Veri: yeni `src/utils/useLiveExec.js` (LivePositionsPage fetch/R-matematiğinin iki-ağ
    birleşik hook hali; RLS zaten kullanıcıya kilitler). Sinyal tesisatı %100 `TradeContext`
    (UserShell mount'ta canlı akışa priming — bayat localStorage backtest fetch'i engellenir).
  - Gizlilik: stream kimliği yalnız `codenameFor`/`useStreamDisplay`; Cap+R ekonomisi "Hedef"
    maskeli; `adminStreamInfo` ayrı lazy chunk olarak build'de doğrulandı (40 kB).
  - `features.trading=false` → Bot sekmesi bilgi kartı (redirect yok); pending/disabled →
    `/bot` RequireActive kapısı. `USER_PAGE_CHOICES` (`userPrefs.js`) + SettingsPage açılış
    sayfası seçenekleri role göre. i18n: ~45 yeni EN karşılığı; `'İşlemler'` EN'i
    'Actions'→'Trades' (eski kullanım yalnız AdminPage tablo başlığıydı).
  - **Emülatör testi (Playwright cihaz emülasyonu):** `scratchpad/user_mode_shots.mjs` —
    iPhone 14 / Pixel 7 / 1440px masaüstü / açık tema; GoTrue+PostgREST+Binance route-mock
    (üretime yazmadan, sentetik mum path'leriyle TP/AKTİF/BEKLİYOR/İPTAL durumları); tüm gizli
    rota redirect'leri assert edildi. `scratchpad/admin_mock_tour.mjs` — admin dalının eski
    kabuğu (Sidebar+IntroPage) aynen render ettiği doğrulandı. Ekran görüntüleri:
    `scratchpad/usermode/`. NOT: `scratchpad/login.mjs`'teki hesap **role='user'** çıktı —
    gerçek admin hesabıyla canlı doğrulama deploy sonrası owner'da.

### 2026-07-09
- **PUSU kartı ALTIN akışlarına da: TALOS-ICHI-X + MIDAS-X.** `/binance` (mainnet) ve `/binance-paper`
  (testnet) sayfalarındaki **Altın bölümü** satırları da tıklanır oldu → aynı `LivePositionModal`
  (gerçek Binance rakamları + paylaşılabilir kart). Mainnet altın = TALOS-ICHI-X, testnet altın = MIDAS-X
  (ikisi de aynı iz-süren şema, aynı bölüm). Altın için `totalUsd/totalR` OPUS `liveCalc` yerine
  `goldCalc`'tan (`{upnl, liveR}`) beslenir; `sel` artık `{pos, isGold}`. Altın çıkış-sebepleri
  (İz-süren stop / Süre 8s / Seans sonu / Fiyat kaçtı) modal REASON'a + EN çevirilerine eklendi.
  Doğrulandı: TALOS #39 XAUUSDT (closed_externally, +0.20R, ROI +4.0%) + MIDAS #63 XAUUSDT
  (trail/stop, +0.56R, ROI +3.3%) — kart + gerçek rakamlar + paylaşım.
- **`/binance` pozisyon kartı: kapananlar da tıklanır + GRAFİK KALDIRILDI (kart yeterli).**
  - **Kapanmış işlemler de dokunulabilir** ("Son Kapananlar" satırları; yalnız gerçekten dolmuş
    `state=CLOSED && entry_fill_time` — iptaller hariç). Modal kapananda **nihai** veriyi gösterir:
    kicker "KAPANDI", ROI/Toplam = `realized_usd`, R = `realized_r`, "Çıkış" fiyatı + `exit_reason`
    etiketi + süre = exit−entry. Açıkta eskisi gibi canlı (mark/uPnL).
  - **Lightweight-charts grafiği kaldırıldı** — kart + gerçek rakam hücreleri yeterli. Fiyat çizgileri,
    markerlar, canlı-mark efekti gitti; yalnız paylaşım kartının **sparkline**'ı için hafif kline çekimi
    kaldı (best-effort). Modal artık çok daha hafif (lightweight-charts import yok).
  - **Paylaşım kartı** açık/kapalı ikisini de basar (kapananda 2. hücre "Çıkış", kicker "KAPANDI").
  - 🐛 FIX: `Date.now()` render/`useMemo` içinde impure — açık pozisyonun "şimdi"si `requestAnimationFrame`
    ile bir kez yakalanıp memo'ya verildi. + kapanış-durum etiketleri (KAPANDI/Sonuç/Borsa kapanışı vb.)
    için EN çevirileri (owner EN modunda Türkçe sızıyordu).
- **YENİ: `/binance` açık pozisyon modalı — gerçek Binance rakamları + canlı/nihai PUSU kartı + paylaş.**
  Canlı pozisyonlar tablosunda bir satıra dokununca açılır (`livex__row--tap`).
  - **Yeni bileşen `src/components/trading/LivePositionModal.jsx`:**
    - **Canlı PUSU kartı** — dev ROI, toplam $, marj, süre, `WAIT · TRAP · EXECUTE` (Telegram kapanış
      kartının açık-pozisyon muadili).
    - **Grafik** (lightweight-charts) — Binance public klines + Cap / TP1 / Giriş / BE / SL fiyat
      çizgileri + **canlı Mark** çizgisi + giriş oku. Aynı fiyata düşen seviyeler birleşir
      (RUNNER'da `eff_be == entry_fill_px` → "Giriş·BE"), fiyatlar 5 anlamlı basamak.
    - **Gerçek Binance rakamları** (`live_account_snapshot`): fiili dolum, mark, kaldıraç, marj,
      uPnL (açık bacak), funding, toplam, R.
  - **ROI tanımı:** `toplam / başlangıç marjı`, toplam = TP1'de realize olan + açık bacağın uPnL'i
    (`liveCalc`). Yani **işlem-seviyesi** ROI; Binance'in açık-bacak ROE'si DEĞİL — kartta yazıyor.
  - 🐛 **FIX (bu iş sırasında bulundu):** grafik "yükleniyor"da takılıyordu — `calc` prop'u her render
    yeni obje, sayfada 1sn'lik `forceTick` var → `useMemo`/efekt saniyede bir grafiği yıkıp kuruyordu.
    Efekt bağımlılıkları primitifleştirildi; canlı **mark** çizgisi ayrı efekte alındı (yenilemede
    zoom kaybolmasın).
  - 🐛 **FIX (uygulama geneli):** `index.html`'de `<html lang="tr">` sabitti ve hiç güncellenmiyordu →
    EN modunda `text-transform: uppercase` Türkçe kuralıyla çalışıp `FILL→FİLL`, `MARGIN→MARGİN`
    üretiyordu. `LanguageContext` artık `document.documentElement.lang`'ı dile göre günceller.
  - **Paylaş butonu (`src/utils/shareCard.js`):** kart **Canvas 2D** ile PNG'ye çizilir (1080×608) →
    `navigator.share({files})` ile mobil native paylaşım sayfası; desteklenmiyorsa/iptal edilirse PNG
    indirilir. DOM→görüntü kütüphanesi (html2canvas vb.) KULLANILMADI: yeni bağımlılık + foreignObject'te
    `color-mix()`/gradient/web-font güvenilmez. Kart Telegram'daki matplotlib kartıyla aynı kimlikte
    (nişangâh, dev ROI, fiyat-yolu sparkline'ı, `WAIT · TRAP · EXECUTE`). Web Share dosya paylaşımı
    güvenli bağlam (HTTPS) ister — prod'da çalışır.
  - Modal etiketleri + paylaşım metinleri için EN çevirileri eklendi (`LanguageContext`).
  - **Ops:** yalnız frontend; migration/cron/env YOK. Owner hesabıyla gerçek açık pozisyon
    (#131 ARBUSDT LONG RUNNER, 15x) üzerinde iPhone-13 viewport'ta doğrulandı.
- **YENİ: kapanış raporu — Telegram'a PUSU paylaşım kartı + grafik + Binance'ten NET ROI (OPUS + TALOS-ICHI-X).**
  Bir pozisyon TAM kapandığında Telegram'a TEK bildirimde İKİ görsel gider: (1) paylaşılabilir PUSU
  sonuç kartı, (2) mum grafiği (giriş / SL / TP1 / BE / cap seviyeleri + giriş ▲ ve çıkış ✕).
  - **Yeni modül `sync/live_exec/trade_report.py`** (talos_ichi_exec de sys.path üzerinden kullanır):
    - `net_pnl()` — Binance'in KENDİ kayıtları: `userTrades.realizedPnl` (brüt) − `userTrades.commission`
      + `income(FUNDING_FEE)` (işaretli) = **NET**. USDT-dışı komisyon (BNB) ayrı raporlanır.
      MARKET dolumu userTrades'e düşmemişse bir kez 2sn bekleyip tekrar okur.
    - `render_chart()` — matplotlib (Agg, headless). İşlem süresine göre mum aralığı (1m/5m/15m/1h).
      Aynı fiyattaki etiketler birleşir (OPUS'ta BE==Giriş); görünür aralık dışındaki seviye (uzak cap)
      y-eksenini ezmesin diye kenarda ok ile gösterilir.
    - `render_card()` — **PUSU'ya özgün paylaşım kartı**: taktik ızgara + nişangâh motifi (eksen kare
      olmadığından daireler `ASPECT`=7.2/4.05 ile düzeltilir), dev NET ROI, işlemin kendi fiyat yolu
      (sparkline: giriş ● / çıkış ✕ / kesikli giriş çizgisi — renk **sonucu** kodlar, fiyat yönünü değil),
      GİRİŞ/ÇIKIŞ/SÜRE/SONUÇ hücreleri, `WAIT · TRAP · EXECUTE` imzası.
    - `send_photo()` / `send_media_group()` — kart + grafik TEK bildirimde (caption ilk görselde);
      medya grubu hata verirse sırayla `sendPhoto`'ya düşer. Mum verisi yoksa yalnız kart gider.
    - ⚠️ **Binance'in "pozisyon paylaş" görseli API'den ALINAMAZ:** resmî fapi'de böyle bir uç nokta yok;
      o kartı üreten `www.binance.com/bapi/...` uçları public değil, dokümante değil ve API key/secret
      kabul etmiyor (web oturumu + CSRF ister). Bu yüzden kendi kartımızı çiziyoruz. Referans kodu da
      işlem-bazlı değil **hesap-sabiti** bir metindir (API'si de yok) — karta konmadı.
    - ROI% = net / başlangıç marjı, marj = giriş×qty/kaldıraç.
  - **Kancalar:** OPUS `_close()` (sl/tp1_be/breakeven/cap/time_stop — 5 çağrı, `client`/`cfg` eklendi)
    + `_reconcile_to_closed` (closed_externally) + `_reverse_close`. TALOS-ICHI-X `_finalize()`
    (yalnız `cfg.armed`). TP1 kısmi booking'de mesaj YOK — sadece tam kapanış.
  - ⚠️ **BEST-EFFORT sözleşmesi:** `report_close()` hiçbir koşulda exception fırlatmaz (Binance hatası,
    bozuk pos, client=None, matplotlib yok → sessizce `False`). Emir yönetimi ETKİLENMEZ. `dry_run`da
    ve TALOS-ICHI `armed=false`da hiç gönderilmez. `EXEC_CLOSE_REPORT=false` ile kapatılabilir.
  - **Not:** caption'daki `R` DB'deki `realized_r`'dir (brüt-türetilmiş), `Net`/`ROI` ise komisyon+funding
    düşülmüş cüzdan gerçeğidir — ikisi kasıtlı olarak farklı şeyleri ölçer.
  - **Ops:** `matplotlib` requirements.txt'e eklendi ve VM `.venv`'ine KURULDU (executor'ler oradan koşar).
    Migration/cron/env değişikliği YOK. Doğrulama: gerçek kapanmış pozisyon #124 ETHUSDT (time_stop,
    brüt +1.64$ · komisyon −0.15$ · funding −0.23$ → **net +1.26$, ROI +12.1%**) grafikle Telegram'a
    gönderildi; hata yolları (Binance patlar / pos bozuk / client None) exception fırlatmadan atlandı.
- **Genel Bakış sadeleştirme: filtre/sıralama/arama kaldırıldı + kart istatistikleri 2×2 (gerçek-cihaz).**
  - **`IntroPage`: kontrol satırı tümüyle kaldırıldı** — Tümü/Range/Seans filtre çipleri, SIRALA sıralama
    (Toplam R/İsabet/Beklenti/PF) ve "Akım ara…" arama kutusu. Kartlar artık sabit **Toplam R azalan**
    sırasında (ATLAS→SIRIUS→MENKAR). Kullanılmayan `cat/sort/query` state + `CATS/SORTS/matchCat/metricOf`
    temizlendi; `visible` tek satıra indi.
  - **Kart istatistikleri mobilde 2×2 grid (`style.css`):** `.intro-stats` tek-sıra flex'te 4 mono değer
    (özellikle lead "+387.7R") dar ekranda taşıp `overflow:hidden` ile PF/değerler kırpılıyordu. Mobil
    media query'de `.intro-stats` → `grid-template-columns: 1fr 1fr` + `.intro-stat{min-width:0}` → 2×2,
    tüm değerler tam okunur, kırpılma yok (360/393px doğrulandı).
  - **Ops:** yalnız frontend; migration/cron/env YOK.
- **Alt çubuk kısayolları güncellendi + Genel Bakış hero taşma düzeltmesi (gerçek-cihaz geri bildirimi).**
  - **MobileTabBar: Genel · Binance · Strateji · Menü** (herkes). "Binance" → canlı pozisyonlar
    (`binanceTo` aktivasyona göre mainnet/paper, sekme her zaman görünür). "Strateji" → ana canlı
    stratejinin komuta merkezi `/${slugFor(LIVE_STREAM_KEYS[0])}/live` (= ATLAS/atlas/live). Yeni
    `IStrat` ikonu. (Önceki "Genel·Canlı·Menü" sade sürümünden revize.)
  - **Hero "sola kayık"/kırpılma FIX (`style.css`):** `.intro-inner` grid'inde `.intro-hero__content`
    grid-item'ı max-content ile boyutlanıp dar ekranda (≤~375px) viewport'u sağdan taşıyor, `overflow:hidden`
    ile disclaimer kırpılıyor + içerik sola kaymış görünüyordu. Mobil media query'e `grid-template-columns:
    minmax(0,1fr)` + hero/leaders/disclaimer'a `width/max-width:100%; min-width:0` eklendi → 360px'te
    simetrik (left=right=24), kırpılma yok.
  - **Ops:** yalnız frontend; migration/cron/env YOK. iPhone-13 + 360/393px viewport doğrulandı.
- **Alt navigasyon sadeleştirme + uzun sistem-açıklama metinlerinin kaldırılması (mobil-doğrulandı).**
  Kullanıcı isteği: normal kullanıcı yalnız öz/gerekli görsün, ekranlar okunur olsun.
  - **Mobil alt çubuk (MobileTabBar) herkeste sade: Genel · Canlı · Menü.** "İşlem Merkezi" ve "İstihbarat"
    sekmeleri alt çubuktan kaldırıldı → Menü drawer'ında (Sidebar) erişilir. Canlı sekmesi yalnız aktivasyon
    varsa görünür (yoksa Genel · Menü). Kullanılmayan `IGear`/`IIntel` ikonları + `useAuth` importu temizlendi.
  - **Uzun "sistem/yöntem açıklaması" prose blokları herkes için kaldırıldı** (risk uyarıları + kurulum
    rehberleri KORUNDU): Rejim Haritası (`TrendPage`) 6-yöntem açıklaması + "Rejim Doğruluğu" iki metodoloji
    paragrafı (tile'lar kaldı); TOTAL (`MarketCapPage`) katman-açıklaması + backtest-gruplama + "Bulgu"
    paragrafları; Genel Bakış (`IntroPage`) "likidite avı felsefesi" manifesto satırı; Seanslar
    (`SessionInfo`) bayat ABD-hisse seans açıklaması. Feragatname ("2026 backtest — örneklem içi",
    "geçmiş performans garanti değil") ve İşlem Merkezi API-kurulum rehberleri DOKUNULMADI.
  - **Ops:** yalnız frontend; migration/cron/env YOK. iPhone-13 viewport doğrulandı (alt çubuk Genel·Menü,
    metinler gitti, layout temiz).
- **Kullanıcı yüzeyi sadeleştirme + Rejim Haritası veri tutarlılığı (mobil-doğrulandı).** Amaç: normal
  (non-admin) kullanıcı yalnız gerekli/öz bilgiyi görsün; analist/operasyon yüzeyleri admin'e kalsın.
  - **İstihbarat artık admin-only.** Kurumsal quant tearsheet (Sharpe/Sortino/drawdown/aylık ısı-haritası)
    son kullanıcı ürünü değil. Route `/intelligence` → `RequireAdmin`; Sidebar + MobileTabBar nav gizleme
    `isAdmin`; Settings ▸ Açılış Sayfası seçeneği de admin'e. Eski `user_features.intelligence=true`
    izinleri artık **yok sayılır** (DB'ye dokunulmadı — geri-alınabilir kod-tabanlı gating). Bu, 07-05
    kaydındaki per-user intelligence feature'ını (RequireFeature) admin-only ile **geçersiz kılar**;
    `trading` opt-out feature'ı aynen korunur.
  - **Ayarlar sadeleştirme:** "Veri & Motor" (PUSU Engine/DB durumu/Bağlantı testi) ve "Semboller"
    (20-sembol seçici) blokları **admin-only**. Non-admin'de kalan: Görünüm · Bildirimler · Hesap · Hakkında.
  - **Rejim Haritası (`/trend`) yalnız canlı evren.** `TradeContext` sembol seti ikiye ayrıldı:
    `CRYPTO_METAL_SYMBOLS` (canlı 20) + `STOCK_PERP_SYMBOLS` (yalnız backtest laboratuvarı);
    `BACKTEST_ALLOWED_SYMBOLS = [...ikisi]` (backtest tabloları/cache aynı, sıra korundu). TrendPage artık
    canlı 20'yi besliyor → ebd03d4 ile atılan ~20 US-hisse perp'i kullanıcıya gösterilmiyor (sayfa
    ~18.3k→~10.8k px kısaldı).
  - **BUG FIX — `RequireFeature`/feature-guard direkt-yükleme race'i:** tam-sayfa direkt yüklemede, mount
    efekti çalışmadan önceki ilk render'da context `features=DEFAULT_FEATURES` döndürüyordu; feature
    fail-closed olunca (intelligence opt-in) gerçek izinler gelmeden gated sayfayı `/`'e atıyordu (eskiden
    default açık olduğu için maskeliydi). Düzeltme: oturum diskte varsa `profileLoading` baştan `true`
    başlatılır (`AuthContext`), guard gerçek profil/features yüklenene dek karar vermez. `/trading` gibi
    tüm gated sayfaları sağlamlaştırır.
  - **Ops:** yalnız frontend (React) değişikliği; migration/cron/env YOK. Doğrulama: iPhone-13 viewport'ta
    (Playwright/Chromium headless) giriş yapılıp login/genel/trend/ayarlar/istihbarat-guard/trading akışları
    gezildi — yatay taşma yok, nav/guard tutarlı.

### 2026-07-05
- **Admin merkezî kontrol + kullanıcı ekleme/silme + kullanıcı tercihleri + bildirim tercihleri (§8a devamı).**
  Tüm kullanıcı kontrolleri artık `/admin`'de; kullanıcı tarafında tema/dil/açılış sayfası + bildirim
  tercihleri hesapla birlikte taşınır.
  - **Admin — kullanıcı ekle:** `/admin` yeni "Kullanıcı Ekle" kartı — anonim GoTrue signup (admin
    oturumuna dokunmaz, dönen session kaydedilmez) → profil trigger'la `pending` doğar → "Aktif olarak
    başlat" işaretliyse `admin_set_user` ile anında aktive. Geçici şifre admin tarafından belirlenir.
  - **Admin — kullanıcı sil:** yeni `admin_delete_user(p_user)` RPC (`supabase/migrations/008`) —
    çift onaylı; kendi hesabını, canonical (owner) hesabı ve **açık pozisyonu olan** hesabı REDDEDER
    (önce KILL). `auth.users` silinir → cascade profiles → keys/settings/prefs/features;
    `push_subscriptions`/`push_outbox` elle temizlenir; audit satırı silinmeden önce yazılır.
  - **Admin — rol yönetimi:** satırda "Admin Yap / Adminliği Al" (admin_set_user `p_role`); kendi rolünü
    değiştiremez.
  - **Admin — yüzey erişimleri (user_features):** kullanıcı-başına `backtest / intelligence / trading`
    çipleri (BT/İSTH/İŞL) — `admin_set_features` RPC (audit'li; client'a UPDATE grant'i yok). Frontend
    gating: Sidebar + MobileTabBar nav gizleme + `RequireFeature` route guard (`/trading`,
    `/intelligence`) + CommandCenter backtest deep-link reddi. Satır yoksa **hepsi açık** (varsayılan).
  - **Kullanıcı tercihleri (user_prefs):** tema/dil/açılış sayfası Supabase'te kullanıcı-başına kalıcı —
    ThemeContext/LanguageContext setter'ları best-effort upsert eder (`src/utils/userPrefs.js`), login'de
    sunucudaki değer uygulanır (`persist:false` ile geri yankı yok), `location.state.from` yoksa giriş
    kullanıcının **Açılış Sayfası** tercihine yönlenir. Settings ▸ Görünüm'e "Açılış Sayfası" seçici eklendi.
  - **Bildirim tercihleri:** Settings ▸ Bildirimler'e 5 olay anahtarı — girişler / kapanışlar /
    ara hedef·iz süren / sinyal yayınları / sistem. Uygulama noktaları: `store.push_user(kind=...)`
    (executor `_alert` çağrıları `entry|exit|milestone|system` etiketli; tercih kapalıysa outbox'a
    yazılmaz — Telegram/owner kanalı ETKİLENMEZ) + `push_notify.send_push` broadcast'te
    `notify_signals=false` kullanıcıların abonelikleri atlanır. Tercih satırı/tablosu yoksa her şey
    gönderilir (default-açık, kırılmaz).
  - **Grafik lejantı (anlaşılır grafik):** ChartModal başlığına sade-dil çizgi rehberi — "Giriş fiyatı /
    Hedef (kâr al) / Stop (zararı kes) / İz süren stop — kâr kilitlenir / Giriş-Çıkış anları"; mobilde tek
    satır yatay kayar (`.chart-legend`).
  - **Ops: ✅ migration 008 canlı DB'ye UYGULANDI (2026-07-05, apply_sql.py, sorunsuz).** Cron/env
    değişikliği YOK.
  - **Owner hesabı oluşturuldu + seed edildi (2026-07-05):** admin e-postası
    **ulkerhuseyin1905@gmail.com** (GoTrue signup, geçici şifreyle; onay maili gönderildi —
    "Confirm email" dashboard'da kapatılana kadar giriş için maildeki linke tıklanmalı).
    `seed_owner.py` çalıştı: profil admin/active/**canonical**; mainnet anahtar **valid**
    (bakiye ~$117, withdrawal yok, one-way ✓), testnet **valid** (~$5041); ayarlar: opus/mainnet
    AÇIK ($5 risk, 5 sembol), opus/testnet kapalı, midas/testnet AÇIK. Ayarlar → "Şifre Değiştir"
    kartı eklendi (GoTrue PUT /auth/v1/user) — geçici şifre ilk girişte değiştirilmeli.

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

### 2026-07-04 — MULTI-USER: kayıt/giriş, kişisel API key, kullanıcı-bazlı execution (§8a)
- **Auth:** tek-şifreli soft gate → **Supabase Auth (GoTrue)**, raw REST (`src/utils/gotrue.js`,
  `supa.js`); `AuthContext` rewrite (session+profil, proaktif refresh, PWA resume), LoginScreen'e
  **Kayıt Ol** sekmesi; kayıt admin-onaylı (`profiles.status='pending'` → `/admin`).
- **DB:** `supabase/migrations/001..007` — `profiles` (+`on_auth_user_created` trigger, `is_admin()`),
  `audit_log` (+`tg_audit`), `user_api_keys` (client'a write-only; RSA-OAEP ciphertext; sanitize view),
  `user_stream_settings` (+`tg_uss_guard`: valid-key/`%25`-bakiye/hedge-mod/universe sert kuralları;
  MIDAS mainnet CHECK ile kilitli), `stream_universe`, `push_outbox`, `push_subscriptions.user_id`,
  executor tablolarına `user_id`+`network` (005a additive ✅ uygulandı; 005b index/PK swap = Faz-5).
- **Executor'lar çift-modlu:** `EXEC_MULTI_USER=false` (şu an) = bugünkü tek-hesap davranışı birebir;
  `true` = `sync/users/store.load_exec_users` üzerinden kullanıcı başına fan-out (kendi anahtarı/riski/
  sembolleri; per-user try/except izolasyon; `SharedTick` ile sinyal/kline/exchangeInfo tek sefer —
  IP rate-limit koruması; coid formatı DEĞİŞMEDİ → owner pozisyonları cutover'da kesintisiz).
  Kill-switch gate + günlük zarar limiti + kişisel push (`push_outbox`); Telegram ve `trading_signals`
  writeback sadece canonical/owner. `killswitch.py --flatten --user <email>` eklendi.
- **UI:** `/trading` İşlem Merkezi (anahtar ekle/rotate + doğrulama durumu, aktivasyon (mainnet yazılı
  onay "GERÇEK PARA"), risk editörü (bakiye-uyarılı), sembol seçimi + backtest sıralaması), `/admin`
  (onay/devre dışı/kill/audit), Sidebar **CANLI MODÜL** (OPUS·FABLE·MIDAS) / **BACKTEST** ayrımı,
  MobileTabBar'a İşlem sekmesi, push aboneliği kullanıcıya bağlandı.
- **Ops:** `sync/users/` paketi + `scripts/gen_exec_keypair.py` (keypair üretildi, `.env`
  `EXEC_PRIV_KEY_PATH`/`EXEC_MULTI_USER=false`); cron +2 satır (`verify_keys`, `push_notify --drain`);
  Faz-1 migration'lar + universe seed UYGULANDI; signup→pending-profil trigger'ı canlıda doğrulandı.
  Kalan manuel adımlar + Faz-5 cutover: **§8a**.
- **GİZLİLİK / strateji anonimleştirme (kullanıcı isteği):** admin dışındaki HERKES (login ekranı
  dahil) akışları nötr kod adlarıyla görür — `src/utils/streamMask.js` haritası: OPUS→ATLAS,
  FABLE→NOVA, MIDAS→SIRIUS, backtest ailesi→VEGA/LYRA/ORION/RIGEL/… Teknik etiketler, strateji
  kartları (strategyInfo) ve XAU grafiğindeki referans çizgisinin gerçek adı (VWAP→**T-REF**) +
  sinyal-koşul metinleri SADECE admin'de görünür ve `adminStreamInfo.js` lazy chunk'ından yüklenir —
  ana bundle'da gerçek isim/mekanik string'i YOK. URL'ler kod adı slug'ı taşır (`/atlas/live`;
  eski ham anahtarlar çalışmaya devam eder). Broadcast Web Push metinleri admin olmayan abonelere
  `push_notify._mask_text` ile kod adlarına çevrilir (owner Telegram'ı değişmedi). Kod adı haritası
  DEĞİŞTİRİLMEZ (kullanıcılar isme alışır); yeni akış = yeni kod adı ekle.

### 2026-07-05 (2) — Admin modülü genişletildi: sistem durumu, global kill, duyuru, e-posta onayı (migration 009 ✅)
- **Migration `009_admin_tools.sql` (UYGULANDI):** `admin_list_users()` (profiles ⋈ auth.users:
  e-posta onayı + son giriş), `admin_confirm_email(p_user)` (dashboard'sız onay — "Confirm email"
  açıkken kullanıcı girişinin önünü admin açar), `admin_notify(p_title,p_body,p_user)` (tek
  kullanıcıya veya tüm aktiflere push duyurusu; push_outbox → mevcut --drain cron'u), `admin_kill_all()`
  (global acil durdurma, audit'li), `admin_user_stats()` (kullanıcı başına açık poz + bugün/toplam $),
  `admin_overview()` (kullanıcı sayıları, executor kalp atışı per network, son sinyal, son anahtar
  doğrulaması, bekleyen outbox, geçersiz anahtar, aktif akış sayısı). Hepsi `is_admin()` korumalı
  security-definer; canlıda admin JWT ile uçtan uca doğrulandı.
- **`tg_uss_guard` FİXİ (kritik):** arming-doğrulaması (geçerli anahtar / %25-bakiye / hedge-mod)
  artık yalnız enable geçişinde veya risk/sembol/ağ DEĞİŞİMİNDE koşuyor — `kill_requested` gibi flag
  güncellemeleri hiçbir koşulda bloklanamaz (önceki sürümde bakiye düşen kullanıcının KILL'i
  trigger'a takılabilirdi).
- **/admin UI:** "Sistem Durumu" kartı (kalp atışı tazelik renkleri, kullanıcı/pozisyon/akış sayaçları)
  + **GLOBAL KILL** butonu (çift onay), kullanıcı tablosuna **Son Giriş / e-posta-onay çipi /
  Açık Poz. / Bugün $** kolonları + **"E-postayı Onayla"** aksiyonu, **"Duyuru Gönder"** kartı
  (hedef: tüm aktifler veya tek kullanıcı; strateji adı yazmama uyarısı). i18n TR/EN + CSS.
- **Owner giriş sorunu çözüldü:** e-posta onayı sunucu tarafında işlendi + şifre yenilendi; giriş
  GoTrue + RLS ile uçtan uca doğrulandı. Not: kullanıcı istatistik kolonları (Açık Poz./Bugün)
  pozisyon satırları user_id'siz olduğundan Faz-5 backfill'e kadar '—' gösterir.

### 2026-07-05 (3) — Sidebar: CANLI İŞLEMLER ayrı bölüm
- Kullanıcı isteği: **CANLI MODÜL** artık yalnız canlı strateji akışlarını (3 stream) içeriyor;
  Binance pozisyon panoları yeni **CANLI İŞLEMLER** bölümüne taşındı — **Binance Mainnet**
  (`/binance`, GERÇEK rozetli) + **Paper · Altın** (`/binance-altin`, PAPER rozetli) + İşlem
  Merkezi (`/trading`) + Yönetim (`/admin`, admin-only). Yeni bölümün katlanma durumu
  `pusu.navExec` (default açık). i18n TR/EN eklendi.

### 2026-07-05 (4) — Canlı işlem panolarına ExecGate: anahtarsız kullanıcı admin verisini görmesin
- **Sorun:** yeni kullanıcı (`ulkerhsyn1905`) `/binance`'e girince owner'ın (admin) Binance
  verisini görüyordu — canlı tablolar RLS ile ayrılmadığından (007 Faz-6'da) ve executor tek-hesap
  modda (EXEC_MULTI_USER=false) yalnız owner'ı yazdığından, sayfa "kim girdiyse" filtresi yapmıyordu.
- **Çözüm (`src/components/ExecGate.jsx`, üretim DB'sine dokunmaz):** `/binance` (mainnet) +
  `/binance-altin` (testnet) route'ları `<ExecGate network=...>` ile sarıldı. Owner (`is_canonical`)
  legacy panosunu görür; owner-olmayan kullanıcı KENDİ geçerli anahtarını (`user_api_keys_public`,
  RLS-scoped) eklemeden pano MOUNT edilmez → "API Anahtarı Ekle" → `/trading` yönlendirmesi (anahtarı
  varsa "hesabınız hazırlanıyor"). Böylece başka hesabın verisi asla gösterilmez. i18n TR/EN.
- **NOT — tam çok-kullanıcı canlı execution hâlâ Faz-5 cutover'a bağlı:** kullanıcıların KENDİ
  hesaplarından işlem açıp kendi verilerini görmesi için `--backfill` + `005b` + `EXEC_MULTI_USER=true`
  + `007` gerekir (armed mainnet'i ~10 dk duraklatan üretim migration'ı — auto-mode dışında, operatör
  onayıyla). ExecGate o güne kadarki güvenli ara-durum. Bu turda executor/`.env` DEĞİŞMEDİ (legacy).

### 2026-07-05 (5) — ✅ FAZ-5 + FAZ-6 CUTOVER TAMAMLANDI: çok-kullanıcı canlı execution CANLI
- **Operatör `scratchpad/faz5_cutover.sh`'yi çalıştırdı** (auto-mode classifier üretim-DB yazımını
  bloke ettiği için operatör çalıştırdı): `killswitch --halt` → `seed_owner --backfill` → NULL-kontrol
  → `005b` index/PK swap → `EXEC_MULTI_USER=true` → yeniden ARMED. Ardından bu oturum **`007` RLS**'i
  uyguladı.
- **Doğrulandı:** OPUS (owner/mainnet) + MIDAS-X (owner/testnet) her ikisi de `ARMED | MULTI-USER`,
  hatasız reconcile; owner'ın 2 açık RUNNER pozisyonu (BTC #123, ETH #124) **AYNI coid'lerle** devam
  ediyor; `live_positions`/`midas_positions` 0 NULL user_id; `live_account` PK `(user_id,network)`,
  `live_account_snapshot` PK `(user_id,network,symbol)` (7 satır damgalı). **007:** RLS 4 tabloda açık,
  policy'ler var, **anon SELECT reddediliyor** (sızıntı DB'de kapandı), executor owner-DSN ile bypass
  edip normal çalışıyor.
- **ExecGate güncellendi** (post-cutover): kapı artık `isCanonical` yerine kullanıcının o ağ için KENDİ
  GEÇERLİ anahtarına bakıyor — geçerli anahtarı olan owner-olmayan kullanıcı da KENDİ panosunu görür
  (RLS satırları kilitler); pending → "doğrulanıyor"; anahtar yok → /trading. Artık ikinci kullanıcı
  (`ulkerhsyn1905`) kendi mainnet/testnet anahtarını ekleyip aktive edince kendi hesabından işlem görür
  ve yalnız kendi verisini görür.
- **Durum:** `.env EXEC_MULTI_USER=true`, `LIVE_TRADING_ENABLED=true`. Geri dönüş: `EXEC_MULTI_USER=false`.

### 2026-07-05 (6) — Ürün/laboratuvar ayrımı: 18 backtest-only araştırma varyantı kullanıcıdan gizlendi
- **Sorun:** genel bakış (IntroPage), login vitrini (LoginScreen), İstihbarat karşılaştırması ve BACKTEST
  nav bölümü 21 akışın TAMAMINI (3 canlı + 18 shipe-edilmemiş araştırma varyantı) her kullanıcıya, gerçek
  backtest R'leriyle gösteriyordu — ürün vitrini ile araştırma defteri aynı yüzeyde (choice-paralysis +
  cherry-pick optiği + mekanik sızıntısı; canlı-vs-backtest çerçevesi yok).
- **Yeni kural:** yalnız 3 CANLI akım (OPUS/FABLE/MIDAS = `LIVE_STREAM_KEYS`, `streamMask.js`) ürün olarak
  herkese görünür; diğer 18 = `isResearchStream()` → **opt-in**: yalnız admin, ya da admin'in backtest
  yüzeyini `user_features.backtest=true` ile açtığı kullanıcı görür. Canlı akımların KENDİ backtest sekmesi
  (track record) bu kuraldan bağımsız — herkese açık (CANLI MODÜL bölümünde, araştırma bölümünde değil).
- **Uygulandı:** `DEFAULT_FEATURES.backtest`/`DEFAULT_FEAT` = false (opt-out→opt-in); Sidebar BACKTEST bölümü
  `isAdmin || features.backtest`; CommandCenterPage deep-link guard artık stream-farkındalıklı (araştırma
  varyantları yetkisiz kullanıcıda `/` redirect — doğrudan-URL bypass kapandı); IntroPage & IntelligencePage
  sayaç+sıralama+seçiciler entitled havuzdan türer (İstihbarat A/B varsayılanları araştırma akımı olduğu için
  havuza clamp'lenir); LoginScreen public vitrini yalnız canlı akımlar. İşlem Merkezi'ne "geçmiş/backtest
  performansı garanti değildir; canlı R altında kalır" risk çerçevesi (gerçek-para activation yüzeyi).
- **Doğrulama:** esbuild syntax + full-bundle module-graph resolve temiz. Vite dev bu kutuda boot etmiyor
  (vite-plugin-pwa eksik + Node 20.18<20.19) — prod build Render'da.
- **Bekleyen (opsiyonel):** `user_features.backtest` SQL kolon default'u hâlâ `true` (008); `admin_set_features`
  daima üçlüyü açık yazdığından pratikte inert, tam tutarlılık için ileride false'a çekilebilir.
- Dosyalar: streamMask.js, AuthContext.jsx, AdminPage.jsx, Sidebar.jsx, CommandCenterPage.jsx, IntroPage.jsx,
  IntelligencePage.jsx, LoginScreen.jsx, TradingSettingsPage.jsx, assets/css/style.css. (commit: pending)

### 2026-07-05 (7) — Sinyal bildirim izleme listesi: kullanıcı strateji+sembol seçince o sinyalde telefon push'u
- **İstek:** kullanıcı seçtiği strateji + sembolde sinyal oluşunca mobil bildirim alsın; seçebilsin.
- **Bugün:** sinyal→push saf broadcast'ti (herkese; yalnız `notify_signals` mute + codename maske). Hedefli
  abonelik yoktu.
- **Model (opt-in, geriye-uyumlu):** `notify_signals` KAPALI → hiç sinyal push'u; AÇIK + liste BOŞ → tüm
  sinyaller (eski davranış); AÇIK + liste DOLU → yalnız seçilen (strateji, sembol) çiftleri.
- **DB:** migration **011** `user_signal_watch (user_id, strategy∈{d30so8f3h7,d30so8f3vg,midas}, symbols text[])`
  + RLS (kendi satırı / admin hepsi). execution'dan (user_stream_settings) ve stream_universe'den ayrı.
- **Frontend:** `SignalWatchCard` (SymbolPickerCard'ı yansıtır) — 3 canlı akışın (codename) her biri için
  `stream_universe`'den sembol çoklu-seçimi + Kaydet; Ayarlar→Bildirimler'de, push açık & "Sinyal yayınları"
  açıkken görünür. `utils/signalWatch.js` (fetch/upsert). NOVA/`d30so8f3vg` OPUS'un `opus` evrenini paylaşır.
- **Backend (`sync/push_notify.py`):** `push_signal_watchers(mode,symbol,…)` — sinyal-insert'te (TÜM taranan
  evren, owner Telegram gate'inden bağımsız) izleyicilere kişisel push'u `push_outbox`'a yazar (mevcut `--drain`
  cron dağıtır), kullanıcı-başına codename maskeler. `send_push` broadcast'i artık izleme-listesi olan
  kullanıcıları ATLAR (çift bildirim yok). Scanner çağrıları: `donchian/canli.py` + `midas/canli.py`.
- **Doğrulama:** py_compile (3 dosya) + esbuild full module-graph resolve temiz.
- **Deploy adımları (kullanıcı):** (1) `apply_sql.py --file supabase/migrations/011_user_signal_watch.sql`
  (owner DSN, prod DB); (2) frontend build (Render); (3) VM'de yeni `push_notify.py`/scanner'lar cron'la
  zaten canlı — ek adım yok (VAPID zaten yapılandırılmış).
- Dosyalar: 011_user_signal_watch.sql, utils/signalWatch.js, components/trading/SignalWatchCard.jsx,
  pages/SettingsPage.jsx, assets/css/style.css, sync/push_notify.py, sync/donchian/canli.py, sync/midas/canli.py.
  (commit: pending)

### 2026-07-07 — MIDAS-X: AFTER-LOSS exec-kapısı + realized_r race düzeltmesi (detay MIDAS.md)
- **Kapı:** `MIDAS_EXEC_AFTER_LOSS_ONLY=true` (.env'de AÇIK; yedek `~/env.backup.pre-afterloss-20260707`)
  — executor yalnızca aynı fx-gününün önceki settled paper işlemi NEGATİF kapandıysa pozisyon açar
  (günün ilk sinyali / kazanç-sonrası sinyaller SKIP). Exec-only overlay: paper feed (mode='midas'),
  backfill, UI değişmedi. Gerekçe: 2026 backtest'te taker ekonomisini +27.1R/PF1.09 → **+53.6R/PF1.37**'ye
  taşıyor; ⚠️ rejim kalkanı değil (2024/25 çok-yıllık hâlâ negatif) — mainnet kapalı, testnet veri topluyor.
- **Düzeltme:** `_finalize`'daki `realized_r=0.000` kalıcı yanlış-yazımı (userTrades'in exit fill'inden
  önce sorgulanması / sessiz BinanceError) → 3×2s retry + hata logu. Ölçüm-only.
- Dosyalar: sync/midas_exec/config.py (flag), sync/midas_exec/executor.py (`_after_loss_gate`,
  `_fx_day_open_utc`, retry), MIDAS.md changelog. Cron değişikliği yok (executor zaten */1 koşuyor).

### 2026-07-07 (2) — MIDAS-X kapı kararları: Telegram bildirimi + live sayfada görünürlük
- Executor kapı hükmünü sinyal satırına yazar (`context.exec_gate`, atomik merge + dedup); atlanan
  her sinyal için BİR kez Telegram (owner) + kişisel push (`kind='system'`). `MidasXLivePage`'e
  "🚧 Kayıp-sonrası kapı" rozeti + "Sinyaller · Kapı Kararları" tablosu (hüküm, sebep, atlanan
  işlemin paper R'si). Dosyalar: sync/midas_exec/executor.py, src/pages/MidasXLivePage.jsx,
  MIDAS.md. Frontend build Render'da (push tetikler); cron değişikliği yok.

### 2026-07-07 (3) — CANLI SET = OPUS + MIDAS: FABLE backtest'e indi, Telegram sadeleşti, 🔴 MIDAS-X MAINNET
- **Kullanıcı kararı**: canlıda yalnız OPUS + MIDAS çalışır ve Telegram atar; FABLE (d30so8f3vg)
  backtest bölümüne indirildi; MIDAS-X mainnet'e alındı ($3 risk + oto-kaldıraç + borsa-tarafı
  iz-süren stop — tüm detay MIDAS.md 2026-07-07 (3)).
- **Cron (KURULDU: `crontab dag/crontab`)**: FABLE emit satırı EMEKLİ (yorumda geri-alma komutu);
  1h Donchian emit'e `--no-telegram` (emit kaldı — nightly `sync_daily` donchianc'yi bu canlı
  satırlardan çözer); 6R emit zaten sessizdi; MIDAS canli + OPUS emit Telegram'ı değişmedi.
  01:20 `volgate_backfill` kaldı → FABLE backtest'i gece tazelenmeye devam eder (canlı emit'ten
  bağımsız). `push_notify._MODE_TO_STREAM`'den `dch30_4hvg` düşüldü.
- **UI**: `streamMask.LIVE_STREAM_KEYS` → ['d30so8f3h7','midas'] (NOVA artık araştırma-varyantı:
  Intro/Login vitrinlerinden ve sinyal-izleme listesinden otomatik düşer, yalnız admin/backtest-yetkili
  görür). Sidebar: NOVA backtest bölümüne (yalnız Backtest yaprağı); MIDAS grubu ● Binance · GERÇEK;
  altın panosu "Binance · Altın ● GERÇEK". IntroPage: araştırma kartlarında Live düğmesi gizlendi
  (sidebar'la tutarlı). İşlem Merkezi: midas mainnet aktivasyon satırı. MidasXLivePage ağ-dinamik.
- **Mobil/QA**: LanguageContext'te 19 duplicate çeviri anahtarı temizlendi (davranış birebir korunarak;
  EN'de gerçek karşılığı olan 6 anahtar EN map sonuna taşındı), tüm düzenlenen dosyalar esbuild'den
  temiz, `main.jsx` tam-bundle smoke PASS; mobil kart-reflow `data-label`'ları korunuyor.
- Dosyalar: dag/crontab, sync/users/store.py, sync/push_notify.py, sync/midas_exec/{config,executor}.py,
  supabase/migrations/012_midas_mainnet.sql, src/utils/{streamMask,streamStats,strategyInfo}.js,
  src/components/layout/Sidebar.jsx, src/components/trading/{streams.js,SignalWatchCard,StreamActivationCard}.jsx,
  src/pages/{MidasXLivePage,IntroPage}.jsx, src/context/LanguageContext.jsx, src/assets/css/style.css.

### 2026-07-07 (4) — Altın panosu Binance Mainnet sayfasına katıldı (ayrı sidebar linki kaldırıldı)
- Kullanıcı: "live trading binance gold kaldır … binance mainnet de olur zaten" → ayrı
  "Binance · Altın" sidebar linki KALDIRILDI (MIDAS-X mainnet executor'a DOKUNULMADI — işlem sürüyor).
- `/binance` (Binance Mainnet) sayfasına "Altın · MIDAS" bölümü eklendi: açık altın pozisyonları
  (giriş/mark/iz-süren SL/kilitli R/canlı K-Z-R/geri sayım) + son kapananlar, `midas_positions`
  network=mainnet'ten (best-effort fetch — tablo/grant yoksa sayfa bozulmaz); "Açık Pozisyon" KPI'ı
  artık OPUS+altın toplamı. Bölüm başlığındaki "Detay →" `/binance-altin`'a gider (route + detay
  sayfası DURUYOR, sadece sidebar'dan çıktı). Mobil kart-reflow `data-label`'ları tam.
- 3 yeni EN çevirisi (İz-Süren SL / Kilitli R / boş-durum metni); `npm run build` PASS.
- Dosyalar: src/pages/LivePositionsPage.{jsx,css}, src/components/layout/Sidebar.jsx,
  src/context/LanguageContext.jsx.

### 2026-07-07 (5) — Pano görünürlüğü KİŞİSEL AKTİVASYONA bağlandı ("diğer türlü boş olsun")
- Kullanıcı kuralı: paper anahtar + sembol aktifleştiren PAPER panosunu, mainnet anahtar + sembol
  aktifleştiren CANLI panoyu görür; hiçbiri yoksa bu yüzeyler boş/CTA.
- Yeni `src/utils/execActivation.js` (useExecActivation): aktivasyon = o ağda GEÇERLİ API anahtarı
  (user_api_keys_public) VE enabled+sembollü akış satırı (user_stream_settings) — her iki sorgu
  `user_id=eq.<uid>` ile daralır (RLS admin'e tüm satırları açtığından şart), İşlem Merkezi'nin
  SETTINGS_EVT'iyle canlı tazelenir, modül-cache'li.
- Sidebar + MobileTabBar: "Binance Mainnet" linki yalnız mainnet-aktif, YENİ "Binance Paper" linki
  (route `/binance-paper`) yalnız testnet-aktif kullanıcıya; mobil "Canlı" sekmesi aynı kurala göre
  hedef seçer/gizlenir. İşlem Merkezi her zaman görünür (aktivasyon orada yapılır).
- `LivePositionsPage` artık `network` prop'lu (mainnet/testnet aynı pano, ağ-kapsamlı sorgular;
  live_positions'ta tüm satırlar network'lü — NULL yok, doğrulandı). `/binance-altin` kapısı
  `network="any"` (ağ-dinamik detay).
- ExecGate genişledi: anahtar + AKTİF AKIŞ ikisi birden aranır; anahtar var ama akış kapalıysa yeni
  "Akış ve sembol aktifleştirin" boş-durumu → /trading. `npm run build` PASS.
- Dosyalar: src/utils/execActivation.js (yeni), src/components/ExecGate.jsx,
  src/components/layout/{Sidebar,MobileTabBar}.jsx, src/pages/LivePositionsPage.jsx, src/App.jsx,
  src/context/LanguageContext.jsx.

### 2026-07-07 (6) — Sidebar amaç-bazlı yeniden düzenlendi, bölüm adları standartlaştı
- Yeni düzen (yukarıdan aşağı): Genel Bakış → **STRATEJİLER** (canlı akışlar; eski "CANLI MODÜL")
  → **İŞLEM** (Binance Canlı/Paper panoları — kişisel aktivasyona bağlı — + İşlem Merkezi; eski
  "CANLI İŞLEMLER") → **PİYASA** (YENİ bölüm: Rejim Haritası + TOTAL + İstihbarat, eskiden dağınık
  düz linklerdi) → **ARAŞTIRMA** (opt-in lab; eski "BACKTEST") → ayraç → Ayarlar + Yönetim
  (Yönetim İŞLEM içinden alta, Ayarlar'ın yanına taşındı — sistem yönetimi işlem değil).
- Ad standardizasyonu: "Binance Mainnet" linki → "Binance Canlı" (sayfa başlığıyla aynı; ExecGate
  metni de eşitlendi). EN: STRATEGIES / TRADING / MARKET / RESEARCH / Binance Live.
- PİYASA bölümü katlanabilir (pusu.navMarket, varsayılan açık); diğer bölümlerin localStorage
  anahtarları değişmedi. `npm run build` PASS.
- Dosyalar: src/components/layout/Sidebar.jsx, src/components/ExecGate.jsx,
  src/context/LanguageContext.jsx.

### 2026-07-07 (7) — İşlem Merkezi yeni-kullanıcı sadeleştirmesi: Kurulum Rehberi + Hazır Şablonlar + i18n backfill
- **Kurulum Rehberi kartı** (`SetupGuideCard`, İşlem Merkezi'nin tepesinde, tam genişlik): 4 adımlı
  otomatik-işaretli onboarding — (1) Binance'te API anahtarı oluştur (katlanabilir adım-adım kılavuz:
  API Management linki, Enable Futures, ÇEKİM YETKİSİ YASAK, IP kısıtı `VITE_VM_EGRESS_IP`, one-way mod),
  (2) anahtarı ekle/doğrulat, (3) şablon seç, (4) akışı etkinleştir. Durumlar kullanıcının kendi
  `user_api_keys_public` + `user_stream_settings` satırlarından okunur; 4/4 olunca tek satıra katlanır.
- **Hazır Şablonlar kartı** (`TemplatesCard`): 3 preset (Temkinli Başlangıç $2×2 / Dengeli $5×3 /
  Geniş Portföy $5×5) — sembol önerisi backtest sıralaması ∩ stream_universe (RPC düşerse majors
  fallback), risk alanlarıyla birlikte tek tıkla upsert; akışı ASLA otomatik açmaz. `fetchRanking`
  streams.js'e taşındı (SymbolPickerCard ile ortak). Şablon metinleri yalnız risk dili — strateji
  mekaniği anlatılmaz (anonimleştirme sınırı korunur).
- **Sayfa akışı sadeleşti:** Rehber → API Anahtarları → Şablonlar → Aktivasyon → "İNCE AYAR" ayracı →
  Risk + Sembol Seçimi (ileri düzey). ApiKeysCard'a Binance API yönetim sayfası linki eklendi.
- **Anonimleştirme sıkılaştırması:** TOTAL sayfasındaki "Akış × genişlik rejimi" tablosu (satır adları
  gerçek akış adları MAIN/OPUS/RANGE) artık YALNIZ admin'e render edilir; MAIN/OPUS/RANGE geçen
  araştırma dipnotu ortak çeviri haritasından çıkarılıp `adminStreamInfo.MARKETCAP_NOTE` lazy chunk'ına
  taşındı (`useStreamDisplay().marketcapNote()`); MidasLiveChart'taki bundle'da hayatta kalan
  `aboveVWAP/belowVWAP/vwapData/vwap` property adları nötrleştirildi (`above/below/refData/ref`).
  Doğrulama: ana bundle'da Donchian/VWAP/breakout/MAIN-OPUS **0 eşleşme** (yalnız admin chunk'ında).
- **TR/EN i18n backfill:** `t()` anahtarı ↔ EN sözlüğü denetimi (scratchpad script) 90 eksik buldu;
  ~75 gerçek eksik çevrildi (canlı pano, seans durumu, TOTAL sayfası, bildirim/ayarlar, grafik modal
  + tüm yeni modül adları: Setup Guide / Quick Templates / Fine-Tuning). Kalan 15 kasıtlı
  İngilizce-anahtar (TP/SL/Win Rate... EN'de anahtarın kendisi). MobileTabBar "İşlem" sekmesi EN'de
  yanlışlıkla "Trades" gösteriyordu → `t('Trade')` + TR override. `npm run build` PASS.
- Dosyalar: src/components/trading/{SetupGuideCard,TemplatesCard}.jsx (yeni), streams.js,
  SymbolPickerCard.jsx, ApiKeysCard.jsx, src/pages/{TradingSettingsPage,MarketCapPage}.jsx,
  src/components/{MidasLiveChart,layout/MobileTabBar}.jsx, src/utils/{adminStreamInfo,useStreamDisplay}.js,
  src/context/LanguageContext.jsx, src/assets/css/style.css.

### 2026-07-07 (8) — Push bildirimlerine mizah katmanı + PWA oto-güncelleme + mobil yatay taşma düzeltmesi
- **Mizah katmanı** (`sync/users/push_flair.py`, kullanıcı isteği): telefon (Web Push) bildirimi
  gövdesinin SONUNA kind'e göre kısa espri satırı — entry ("Pusu kuruldu — şimdi bekleme sanatı 🎯"),
  skip/iptal, exit (işaretli-R'den kazanç/kayıp sezilir: "Kasa gülümsüyor 😎" / "Stop dostumuzdur 🛡️"),
  milestone, signal ("Radar öttü 📡"). `kind='system'` ASLA espri almaz; Telegram/owner kanalı ve
  başlıklar değişmez; espriler strateji-nötr (anonimleştirme). Kapatma: `.env PUSH_FLAIR=0`.
  Entegrasyon: `users/store.py push_user` (executor kişisel push'ları) + `push_notify.py`
  send_push/push_signal_watchers (sinyal broadcast/izleme). venv import + kind-matrisi test edildi.
- **PWA oto-güncelleme** (src/main.jsx): `controllerchange` → tek seferlik `location.reload()`
  (ilk-kurulum guard'lı). sw.js zaten skipWaiting+clients.claim yapıyordu; artık yeni deploy,
  uygulama açıkken SW devri olur olmaz kendini gösterir — kullanıcının elle yenilemesi/yeniden
  kurması gerekmez (PWA kendi kendine güncellenir, mağaza/Chrome "indir" adımı yok).
- **Mobil "soldan kayma"** (kullanıcı ekran görüntüsü, Genel Bakış): `html, body { overflow-x: clip }`
  — sayfa düzeyi yatay pan kökten kapandı (dekoratif mutlak elemanlar/geniş içerik kendi kabında
  kırpılır/kayar). `clip` seçildi (`hidden` değil) → scroll container oluşmaz, sticky topbar bozulmaz.
  Headless-chromium harness ile 360/412px'te intro klonu ölçüldü (docScrollWidth ≤ viewport PASS).
- Dosyalar: sync/users/push_flair.py (yeni), sync/users/store.py, sync/push_notify.py,
  src/main.jsx, src/assets/css/style.css. `npm run build` PASS.

### 2026-07-07 (8) — Runbook tazeleme + §7a "yeni makineye taşıma" cutover prosedürü (kod değişikliği YOK)
- **Kullanıcı isteği:** "sistemi komple başka ortama taşımamı sağlayan .md — clone edip kur deyince
  live/backtest/cron/DB hazır olsun, ve dosya değişikliklerle güncel tutulsun." Bu dosya (RUNBOOK.md)
  zaten o dosya; bu turda güncel duruma eşitlendi + taşıma prosedürü eklendi. Güncel-tutma disiplini
  değişmedi: **her değişiklikte tarihli changelog girdisi + kurulum bölümleri güncellenir** (sistem →
  RUNBOOK.md, MIDAS → MIDAS.md).
- **§7a eklendi — MIGRATE to a NEW machine:** VM'in durum taşımayan yapısı ( kalıcı her şey dışarıda;
  kutuda yalnız `.env` + RSA private key + crontab), eski kutuda killswitch --status → `crontab -r`,
  secret kopyalama, yeni kutuda §7 + manuel executor tick'i + `crontab dag/crontab`, çift-cron yasağı,
  borsa-tarafı SL sayesinde açık pozisyonların taşınmadan hayatta kalması, Binance IP whitelist +
  `VITE_VM_EGRESS_IP` güncellemesi.
- **§7'ye "fresh DATABASE" notu:** sıfır Supabase projesi kurulacaksa migration sırası
  (001..012 + seed-universe + push/exec schema'ları) ve owner seed adımı.
- **Bayat bölümler güncellendi (2026-07-07 (3) sonrası):** §1 akış tablosu (canlı set = OPUS+MIDAS;
  MIDAS-X 🔴 mainnet GERÇEK; FABLE backtest-only), §5 cron tablosu kurulu crontab'la birebir
  eşitlendi (FABLE emit emekli, 1h emit sessiz, verify_keys + push_notify satırları ve
  `~/ict-midas-exec.log`/`~/ict-users.log` eklendi), §6 MIDAS-X env listesi
  (`MIDAS_EXEC_AFTER_LOSS_ONLY`, auto-leverage), §8 MIDAS-X bölümü (mainnet config + ekonomi
  uyarısı + rollback).
- Ayrıca MIDAS.md'ye 2026-07-07 (4) araştırma girdisi eklendi (flip/whipsaw + rejim incelemesi —
  filtre ship edilmedi; detay orada).

### 2026-07-07 (10) — "Liquidity Ambush Intelligence" sloganı login + Genel Bakış'tan kaldırıldı
- Kullanıcı isteği: LoginScreen (`boot-sub`) ve IntroPage (`intro-sub`) alt başlık satırları silindi;
  logo/başlık ("PUSU") duruyor. Footer'lardaki "© 2026 PUSU · Likidite Avı" ile PWA manifest
  adı/açıklaması dokunulmadı. `npm run build` PASS.

### 2026-07-07 (11) — TALOS: 3. canlı akış (altın Keltner-trend, PAPER) — sync + cron + DB + UI uçtan uca
- **Ne:** "MIDAS'tan iyi XAU" taramasının (MIDAS.md changelog 2026-07-07) kazanan adayı KELT075,
  **TALOS** adıyla (kod adı **ANTARES**) 3. canlı akış olarak ürünleşti. Kullanıcı kararı: paper
  live + 2026 backtest + cron + Telegram + grafikler; isim seçimi bana bırakıldı.
- **Strateji:** XAUUSDT 1m; 15m EMA(20) trend (4-bar eğim), giriş = EMA∓0.75×ATR(20,15m) Keltner
  bandına DERİN sarkıp in-trend kapanış; iskelet MIDAS'la birebir (1.5×ATR stop, sabit hedef yok,
  3.5×ATR iz-süren, 8s, seans-düz, Londra 07-13 skip, m120) ve **kod paylaşımlı** (sync/talos/strategy.py
  MIDAS'ın walk/track_open/seans motorunu import eder; yalnız signals() farklı). Hacim kullanmaz.
  2026: +87.7R/323tr/PF 1.53 (DB'ye yazıldı); PAXG çok-yıllık OOS 3yıl +39.2R vs MIDAS-repro −183R.
- **Parçalar:** `sync/talos/{strategy,backfill,canli}.py` (backfill 01:40 nightly, canli her dk +30s
  Telegram ON formasyon+trailing+çıkış); migration **013** (user_signal_watch CHECK'e 'talos' +
  stream_universe'e (talos,XAUUSDT)) UYGULANDI; `push_notify` maske (TALOS→ANTARES, Keltner→K-BANT)
  + mode→stream haritası; UI: streamMask CODENAMES/LIVE_STREAM_KEYS, adminStreamInfo (REAL_NAMES/
  LABELS + REAL_TALOS_CONDS), strategyInfo kartı (tr/en), streamStats, Sidebar canlı bölümü,
  TradeContext (version/mode/ltf + trailing özel-durumları midas|talos), ChartModal (trailing set),
  Dashboard (isTrailing + seans kartı + canlı grafik), **MidasLiveChart `variant="talos"`**
  (15m Keltner bandı + AL/SAT işaretleri + koşul pill'leri — VWAP yerine Keltner çizer),
  SignalWatchCard (talos evreni). İşlem Merkezi/executor kasten YOK (paper-only;
  user_stream_settings CHECK'i opus/midas kaldı).
- **Doğrulama:** backfill dry-run 2026 +87.7R (araştırma taramasıyla uyumlu), canli --emit koştu
  (0 setup, in-position kilidi çalışıyor), crontab kuruldu, prod build temiz (TALOS/Keltner ana
  bundle'a sızmıyor — yalnız REAL_TALOS_CONDS özellik adı, REAL_MIDAS_CONDS ile aynı desen).

### 2026-07-08 (2) — TALOS-X: TALOS emirleri Binance TESTNET'e (paper) + adım-adım iz-süren stop
- **Kullanıcı isteği:** "talos emirlerini paper accounta gönder, iz süren SL de adım adım kaydırılsın."
- **Ne:** `sync/talos_exec/` — MIDAS-X'in birebir kopyası (sed-rename), **gerçek-para MIDAS-X koduna
  dokunulmadı**. mode='talos' sinyallerini okur, maker GTX giriş + 60sn maker→taker fallback (dünkü
  düzeltme kopyada da var), çıkış = `sync/talos/strategy.track_open` chandelier'ı. TESTNET'te iz-süren
  stop SENTETİK modelle her dakika yeniden hesaplanıp adım adım kaydırılır (cur_sl/locked_r/trail_gen
  satırda; testnet koşullu emirleri -4120 ile reddettiği için borsa-tarafı resting stop yok — tetikte
  MARKET-close; mainnet'e taşınırsa cancel/replace kodu hazır). Kapanış version='talosx' →
  trading_signals (dashboard'a düşer), Telegram giriş/stop/çıkış bildirimleri executor'dan da gelir.
- **Guardrail'ler:** TALOS mainnet ÇİFT kilitli — `TALOS_BINANCE_TESTNET=true` env + migration **014**
  `talos_testnet_only` CHECK (user_stream_settings'te talos+mainnet satırı açılamaz). Kendi
  `talos_positions/talos_orders` tabloları (multi-user user_id/network + user-scoped unique indeksler
  doğuştan), kendi killswitch/safety-sweep'i — OPUS/MIDAS-X ile çapraz müdahale imkânsız.
- **DB/ops:** talos_exec/schema.sql UYGULANDI; migration 014 UYGULANDI (stream CHECK'e 'talos' +
  owner'a talos/testnet enabled satırı, $5 risk); store.py _POS_TABLES'a talos eklendi; .env'e
  TALOS_EXEC_* bloğu (VM); cron: executor her dk +42s, safety sweep */3 +55s → ~/ict-talos-exec.log.
  Dry-run + ARMED ilk koşu + safety sweep temiz (0 sinyal penceresi, testnet erişimi OK).

### 2026-07-08 — OPUS (d30so8f3h7) KRİPTO-ONLY: backtest evreni 40 → 18 sembole daraltıldı
- **Karar (kullanıcı):** "OPUS'u sadece crypto için çalıştır, diğerlerine gerek yok — backtest'te de
  canlıda da." Canlı executor zaten kripto-only (`EXEC_ENABLED_SYMBOLS=BTC/ETH/SOL/FET/ARB`); bayat olan
  BACKTEST kitabıydı (40 sembol: 18 kripto + XAU/XAG + 20 hisse-perp).
- **Kod:** `sync/donchian/portfolio_backfill.py` — `CRYPTO_SYMBOLS` (18) + `Stream.symbols` alanı;
  yalnız `d30so8f3h7` kriptoya bağlandı (diğer streamler tam evrende kalır). `run_stream` evren seçimi:
  CLI `--symbols` (test) > stream kısıtı > tam evren. Altının kendi akışları var (MIDAS paper / TALOS-ICHI-X).
- **Yeniden backfill (--apply):** 3046 eski satır silindi → **2806 kripto satır**.
- **Sonuç:** ÖNCE (40 sem) n=3046 +395.4R avgR 0.130 WR%54 · SONRA (18 kripto) n=2806 **+388.6R**
  avgR **0.138** WR%54 PF 1.29. Kripto-dışı 19 sembol 263 işlemde yalnız +11.0R üretiyordu (gürültü) —
  atılınca toplam R ~aynı, işlem-başı kalite arttı.
- **Yıl bazında (hepsi pozitif, iyileşen):** 2024 +45.8 (WR52%) · 2025 +200.9 (WR54%) · 2026 +141.9 (WR58%).
- **En iyi 5 sembol:** FET +62.2, ETH +48.1, SOL +33.9, ARB +30.7, ADA +26.1 — canlı 5'linin 4'ü
  (FET/ETH/SOL/ARB) burada; canlı sembol seçimi backtest'le doğrulanıyor.

### 2026-07-08 — AÇIK İŞLEM ÖZETİ: 5 dakikada bir TEK Telegram mesajı (sync/positions_digest.py)
- **İstek (sahip):** "5 dakikada bir açık işlemleri Telegram'a tek mesajda anlık durumlarıyla bildiren cron."
- **Ne:** salt-okunur raporcu — **emir göndermez**. Tek `positionRisk` çağrısıyla borsadan ANLIK
  mark/uPnL/liq/isolatedMargin/kaldıraç; `ict_trade.live_positions` (OPUS scale-out) +
  `ict_trade.talos_ichi_positions` (TALOS-ICHI-X trailing) satırlarından state/risk0/SL/locked_r/süre.
  Pozisyon başına: yön, akış, state (RUNNER'da "TP1 alındı"), giriş→anlık (lehte/aleyhte %), uPnL $ ve R,
  SL (+kilitli R), süre, kaldıraç, marj, liq. Altta hesap: cüzdan / serbest / toplam uPnL.
- **Spam koruması:** açık pozisyon yoksa **sessiz** çıkar. `--always` boşken de atar, `--dry-run` göndermeden
  basar, `--testnet` testnet hesabını raporlar.
- **R hesabı:** `R = (mark − eff_entry)·yön / risk0`. OPUS RUNNER'da ilk hedef (+1R) çoktan kısmen alınmıştır,
  gösterilen R kalan bacağındır — mesajda "TP1 alındı" ibaresiyle işaretlenir.
- **Cron:** `*/5 * * * * sleep 15` (boş offset), log `$HOME/ict-digest.log`. VM'e kuruldu, canlı test gönderildi
  (3 pozisyon: ETH/FET OPUS-RUNNER + XAU TALOS-ICHI-X).

### 2026-07-08 — fix: -1021 (saat kayması) self-heal — imzalı çağrılar taze damga + resync + retry
- **Şikayet (sahip):** "MIDAS paper işlem açma hata veriyor — `[-1021] Timestamp outside recvWindow`".
- **Teşhis:** anlık kayma küçük (~40ms), yani `-1021` VM saatinin ANLIK sıçraması (NTP step/jitter). Ama
  `binance_futures._request` **timestamp'i döngü DIŞINDA bir kez** hesaplıyordu → retry'lar aynı BAYAT
  damgayı yeniden gönderiyor, ve `-1021`'de self-heal yoktu → reconcile/emir başarısız.
- **Düzeltme (`sync/live_exec/binance_futures.py` — TÜM executor'lerce paylaşılan client, gerçek para dahil):**
  (1) imzalı sorgu HER denemede taze `timestamp` ile kuruluyor; (2) `-1021` alınınca `sync_time()` ile
  server-time offset RESYNC edilip retry — anlık saat sıçramasını otomatik iyileştirir; (3) `recvWindow`
  5000→10000 ms (jitter payı). Geriye-dönük uyumlu; salt dayanıklılık artışı.
- **Doğrulama:** yapay −20000ms kayma enjekte edildi → ilk imzalı çağrı resync edip başardı (offset −117ms'e
  döndü). Üç executor de temiz koştu (`-1021` yok): MIDAS-X(testnet), TALOS-ICHI-X(mainnet), OPUS(mainnet).

### 2026-07-09 — DONCHIAN KRİPTO+METAL: US-hisse perp'leri evrenden atıldı + eski sinyaller silindi
- **Karar (sahip):** "Kripto ve metaller kalsın, sadece tüm Donchian'larda; US hisseleri gitsin. midas/talos'a
  dokunma. Donchian metal+kripto çalışsın; metaller Donchian'da zaten live işlem almıyor, sadece sinyal üretsin."
- **Neden:** OPUS kripto-only yapılırken (2026-07-08) görüldü ki 40-sembol evrenindeki 20 tokenize US hisse
  (NVDA/META/AMZN/COIN/MSTR/CRCL/PLTR/TSLA/INTC/HOOD/MSFT/AVGO/BABA/BX/HPE/AMAT/CRWD/CRDO/AAOI/IWM) gürültüydü.
- **Yeni evren:** `strategy.CRYPTO_METAL_SYMBOLS` (20 = 18 kripto + XAU + XAG). `STOCK_SYMBOLS` (20) düşülür.
  Metaller SİNYAL-ONLY kalır (canlı executor `EXEC_ENABLED_SYMBOLS` kripto-only → XAU/XAG hiç gerçek-para fill almaz).
- **Kod (üreticiler kısıldı):** `canli.py` `--symbols` default → CRYPTO_METAL; `portfolio_backfill.SYMBOLS` →
  CRYPTO_METAL (volgate_backfill onu kullanır); `sync_daily.py` upsert öncesi STOCK_SYMBOLS güvenlik-filtresi.
  d30so8f3h7 (OPUS, gerçek-para ayna) KENDİ `symbols=CRYPTO_SYMBOLS` kısıtıyla **kripto-only** kalır (metalsiz) —
  backtest kitabı executor'ü aynalamaya devam etsin diye; bilinçli istisna.
- **DB temizliği (tek sefer):** hisse satırları silindi — LIVE `signals` 213 (547→334), BACKTEST `trading_signals`
  3426 (54388→50962). Kripto + XAU/XAG + altın akışları (midas 403 / talos 327 / talos_ichi 232 / tichix / midasx)
  DOKUNULMADI. Silme sonrası her iki DB'de kalan hisse = 0; altın akış sayıları değişmedi.
- **ICT akışları (v1/v2/main/impulse) — ayrı kitap, dokunulmadı** (live emisyonu 2026-06-14'te emekliydi); bu
  temizlik yalnız Donchian kapsamı. Script: `scratchpad/delete_stock_signals.py` (--apply).

### 2026-07-09 (2) — Admin: açık-işlem özeti cron'unu web'den aç/kapa + altın panosu TALOS etiketi
- **İstek (sahip):** (1) "Binance Live'daki altın işlemleri artık MIDAS değil TALOS; detay linki de paper'a
  gönderiyor" — düzelt. (2) "Açık işlemler cron job'unu webden kontrol edilen buton açsın/kapasın."
- **(1) Altın etiketi:** veri sorguları zaten gerçek-para TALOS-ICHI (`talos_ichi_positions`,
  `mode=eq.talos_ichi`) idi; sadece görünen isim `sd.name('midas')` (paper kod adı) ile çözülüyordu.
  `LivePositionsPage.jsx` altın başlığı + `MidasXLivePage.jsx` rozet/uyarıları → `sd.name('talos_ichi')`.
  Salt etiket; veri/rota (`/binance-altin`) değişmedi.
- **(2) Cron aç/kapa — bayrak kalıbı:** cron VM crontab'ında sabit (`dag/crontab` `*/5`), web'den satır
  silinemez → executor `kill_requested` kalıbı: cron her tetiklemede DB bayrağını okur, KAPALI ise sessizce
  no-op (Binance'i bile çağırmadan çıkar). `--always`/`--dry-run` elle çalıştırmayı bloklamaz.
  - **DB (migration 017 ✅ uygulandı):** `ict_trade.app_flags` (key/enabled, RLS: authenticated SELECT) +
    `admin_set_flag(key,bool)` RPC (`is_admin()` korumalı, audit_log'a yazar). Seed `positions_digest=true`.
  - **Python:** `trade_sync_common.flag_enabled(conn,key,default=True)` (tablo yoksa default → cron kırılmaz);
    `positions_digest.py` `live_conn()` sonrası gate.
  - **Frontend:** AdminPage Sistem Durumu kartında **🔔 Açık İşlem Özeti: AÇIK/KAPALI** butonu (admin-only).
- **Doğrulama:** bayrak KAPALI → cron elle koşuldu → `=== açık işlem özeti KAPALI (app_flags) — atlanıyor ===`,
  Binance/Telegram'a gitmedi, exit 0; bayrak tekrar AÇIK. Frontend Render'da main'den derlenince buton görünür.

### 2026-07-09 (3) — README vitrin: proje highlight'ı (strateji + sonuç + mimari + uygulama)
- **İstek (sahip):** "Repoyu güzelleştir; strateji ve sonuçları, yapılan çalışmaları, uygulama linklerini
  ekleyerek repoyu highlight et."
- **Değişiklik:** `README.md` ince frontend+güvenlik notundan tam bir vitrin sayfasına yeniden yazıldı
  (İngilizce, GitHub showcase standardı; RUNBOOK zaten İngilizce): rozetler, "at a glance" metrikleri
  (436 commit / ~5 ay / 187 py / 42 jsx), **canlı kitap tablosu gerçek sonuçlarla** (OPUS +388.6R/PF1.29,
  TALOS-ICHI-X +35.6→+118.3R, MIDAS +142R/PF1.48 + fee-honesty), research highlights (OOS eleme, bit-identical
  no-lookahead, VWAP-trend +115R null p<0.005, ML NO-SHIP), ASCII mimari diyagramı, uygulama rota haritası,
  tech stack, quickstart, doküman indeksi, güvenlik, disclaimer.
- **Rakam kaynağı:** RUNBOOK/MIDAS/STRATEJI/FX-GOLD/ML raporları + curated memory; uydurma yok. Tüm doküman
  linkleri mevcut dosyalara bağlı. Salt dokümantasyon — kod/DB/cron değişmedi.

<!-- NEXT ENTRY GOES ABOVE THIS LINE -->
```
### YYYY-MM-DD — <summary> (commit <hash>)
- <what changed>
```
