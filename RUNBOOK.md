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

<!-- NEXT ENTRY GOES ABOVE THIS LINE -->
```
### YYYY-MM-DD — <summary> (commit <hash>)
- <what changed>
```
