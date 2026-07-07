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
| **TALOS** (`talos`) | Gold-only (XAUUSDT) 1m Keltner-trend: DEEP pullback to the 15m EMA20±0.75·ATR band + the same 3.5×ATR trailing engine as MIDAS (shared code) | ✅ | paper feed (no executor) |
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
│   ├── talos/               TALOS gold stream (Keltner sibling of MIDAS; PAPER-only): strategy.py
│   │                        (imports the MIDAS walk/trailing engine), backfill.py, canli.py
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
| `20 1 * * *` | `volgate_backfill.py --apply` | FABLE backtest refresh (live emit retired 2026-07-07; re-enable command in the crontab comment) |
| `30 1 * * *` | `midas/backfill.py --apply` | MIDAS backtest refresh |
| `* * * * *` (+30s) | `talos/canli.py --emit --lookback-min 3 --sl-step 0` | **TALOS** emit + trailing track + Telegram |
| `40 1 * * *` | `talos/backfill.py --apply` | TALOS backtest refresh |
| `*/2 * * * *` | `live_exec/executor.py` | **REAL-MONEY** OPUS reconciler |
| `*/5 * * * *` | `live_exec/safety_sweep.py` | executor safety guard |
| `* * * * *` | `midas_exec/executor.py` | **MIDAS-X** reconciler (**REAL-MONEY mainnet** since 2026-07-07) |
| `*/3 * * * *` | `midas_exec/safety_sweep.py` | MIDAS-X safety guard (XAUUSDT-scoped) |
| `* * * * *` (+40s) | `users/verify_keys.py` | multi-user API-key verification |
| `* * * * *` (+45s) | `push_notify.py --drain` | personal Web-Push outbox drain |

Logs: `~/ict-donchian.log`, `~/ict-midas.log`, `~/ict-talos.log`, `~/ict-midas-exec.log`,
`~/ict-sync.log`, `~/ict-exec.log`, `~/ict-users.log`.

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

**MIDAS-X gold executor only** (leave unset on a paper box): `MIDAS_EXEC_ENABLED`,
`MIDAS_EXEC_DRY_RUN`, `MIDAS_BINANCE_TESTNET` (MIDAS's own network flag, independent of `BINANCE_TESTNET`;
**false = mainnet real money since 2026-07-07**), `MIDAS_RISK_PER_TRADE_USD` (mainnet: 3),
`MIDAS_LEVERAGE`/`MIDAS_AUTO_LEVERAGE`/`MIDAS_LEVERAGE_MAX`, `MIDAS_MARGIN_TYPE`, `MIDAS_MAKER_ENTRY`,
`MIDAS_ENTRY_TIMEOUT_SEC`, `MIDAS_ENTRY_MAX_SLIP_R`, `MIDAS_SL_DEADBAND_TICKS`,
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

<!-- NEXT ENTRY GOES ABOVE THIS LINE -->
```
### YYYY-MM-DD — <summary> (commit <hash>)
- <what changed>
```
