# MIDAS — Gold-only intraday VWAP-trend stream · Runbook & changelog

> Single source of truth for the **MIDAS** trading stream: what it is, every component, how to bring it
> up from a **fresh clone**, how to operate it, and a **changelog** that is appended as things change.
> Deep research write-up (why it works, why it's gold-only): [FX-GOLD-VWAP-RAPORU.md](FX-GOLD-VWAP-RAPORU.md).

---

## 0. TL;DR — what is MIDAS?

A **gold-only (XAUUSDT) 1-minute intraday trend-continuation** strategy, independent from the repo's
Donchian/ICT book. In an established VWAP-slope trend it **buys the pullback to the anchored VWAP** (sells
the rally), risks **1.5×ATR(15m) = 1R**, takes **NO fixed target**, and rides a **3.5×ATR chandelier
trailing stop** to a session/8h exit. Intraday only — never holds across the weekend.

**Validated 2026-H1** (market-open hours, $0.50/oz ECN-FX cost): **+142R settled · PF 1.48 · WR 37% ·
IS(Jan-Apr) +83 / OOS(May-Jun) +61**, confirmed by a parameter plateau, honest IS→OOS selection, a
random-entry null test (p<0.005), a liquid-hours test, a per-day bootstrap, and an independent
from-scratch reimplementation that reproduced it to the decimal.

**It is gold-specific** — tested and does NOT transfer to XAG / BTC / ETH / platinum / palladium / copper
/ S&P / Nasdaq. Keep it XAU-only.

⚠️ **Cost reality:** MIDAS uses an **FX/ECN cost model ($0.50/oz ≈ 1 bp)**. On Binance taker fees
(~10 bps ≈ $4/oz) it turns **negative** (+142R → ≈ −92R). MIDAS is therefore a **PAPER** stream
(signals + Telegram + dashboard). A real-money-capable Binance bridge now exists — **MIDAS-X**
(`sync/midas_exec/`, version `midasx`) — but it runs **TESTNET / dry-run only**; a Binance-fee
simulation MUST show a positive net-of-fee edge before any mainnet arming (see §5). Real-money
mainnet today = OPUS only.

---

## 1. Architecture / data flow

```
                         ┌─────────────────────── BACKTEST (authoritative book) ───────────────────────┐
 Binance XAUUSDT 1m ──►  sync/midas/backfill.py  ──►  ict_trade.trading_signals (version='midas')  ──►  UI "Backtest"
   (nightly 01:30)         · full 2026 replay              · SETTLED trades only                          (version='midas')
                           · single-position walk          · trailing path in context.trail
                           · excludes still-open trades

                         ┌─────────────────────────── LIVE (paper signal feed) ───────────────────────┐
 Binance XAUUSDT 1m ──►  sync/midas/canli.py     ──►  ict_trade.signals (mode='midas')          ──►  UI "Live"
   (cron, EVERY MINUTE)    · emit fresh setups            · pos / cur_sl / locked_r / trail in context   (mode='midas')
                           · track open position          · Telegram: entry / SL-change / exit
                           · single-position (no overlap)
                           └────────────────────────────────────────────────────────────────────────────┘
   open trade settles into the backtest on the next nightly backfill once it actually closes.
```

- **Single position at a time** (like OPUS). A signal arriving while a position is open is **ignored**
  (same OR opposite direction — MIDAS does **not** reverse; the trailing stop manages the exit). The
  backtest (`walk`) and live (`canli`) both enforce this, so they match.
- **Two databases** (external Postgres / Supabase, persist across machines):
  - **Live DB** (`DB_CONNECTION_STRING` / REST `VITE_SUPABASE_URL`): `ict_trade.signals` — the live feed.
  - **Backtest DB** (`BACKTESTING_DB_CONNECTION_STRING` / REST `BACKTESTING_VITE_SUPABASE_URL`):
    `ict_trade.trading_signals` — the backtest book.

---

## 2. Components (file map)

### Strategy / backend — `sync/midas/`
| File | Role |
|---|---|
| `strategy.py` | Core. Data load + FX-gold market-hours filter, anchored VWAP, ATR(15m), `signals()` (VWAP-pullback + London 07-13 UTC skip + 2h session-maturity), `walk()` (leak-free single-position backtest with 3.5×ATR trailing), `generate_trades()`, `track_open()` (live trailing replay for one open position), `current_open()` (self-heal). All tuned constants live at the top (`SLOPE_N`, `ATR_INIT_MULT`, `TRAIL_MULT`, `MAX_HOLD_MIN`, `COST_RT`, `SKIP_UTC_START/END`, `MATURE_MIN`). |
| `backfill.py` | Nightly: replays 2026, writes **SETTLED-only** trades to `trading_signals` (`version='midas'`), stores the trailing-stop path in `context.trail`. `--dry-run` / `--apply`. |
| `canli.py` | Per-minute live: emits fresh setups + tracks the open position → `signals` (`mode='midas'`); Telegram on entry / **every trailing-stop change** (`--sl-step 0`) / exit. `--dry-run` / `--emit`, `--sl-step N`, `--no-telegram`, `--lookback-min N`. |

Shared engine helpers reused from `sync/trade_sync_common.py` (DB connections, `fetch_klines`, `build_row`) and `backtest/ict/data.py` (Binance klines).

### Real-money bridge — `sync/midas_exec/` (TESTNET / dry-run first; version `midasx`)
Clones the OPUS executor pattern (`sync/live_exec`) but implements MIDAS's own mechanics: a post-only
maker LIMIT entry, the 1.5×ATR initial stop, and the 3.5×ATR chandelier trailing exit driven by the
**same `strategy.track_open`** the paper feed uses (so live == paper by construction). See §5 + `sync/midas_exec/README.md`.
| File | Role |
|---|---|
| `executor.py` | cron #1 — reads `mode='midas'` → maker entry → chandelier trailing → 8h/session exit → reconcile (idempotent, deterministic `mdx-…` coids). Testnet = synthetic MARKET-on-trigger; mainnet = resting `STOP_MARKET` + cancel/replace. |
| `config.py` | `MidasExecCfg` + `load_cfg()`; `MIDAS_*` env; **fail-closed**; `MIDAS_BINANCE_TESTNET` (own network flag, testnet-first) so MIDAS can be testnet while OPUS is mainnet. |
| `state.py` | only-writer of `ict_trade.midas_positions`; context-aware writeback to `trading_signals` (`version='midasx'`). |
| `schema.sql` | additive `midas_positions` / `midas_orders` (separate from OPUS's `live_positions`). |
| `safety_sweep.py` / `killswitch.py` | XAUUSDT-scoped guards + operator CLI (`--halt` flips `MIDAS_EXEC_ENABLED`, OPUS untouched). |
| `parity_report.py` | Faz-0 gate — `track_open` replay vs the backtest `walk()` (0 mismatches). |

Depends on a one-line additive fix in `sync/live_exec/exchange_info.py`: gold is a `TRADIFI_PERPETUAL`
(not `PERPETUAL`), so `is_tradable(sym, allow=('PERPETUAL','TRADIFI_PERPETUAL'))` accepts XAUUSDT while
`is_tradable_perp` (the OPUS gate) still rejects it.

### Frontend — `src/` (React + Vite)
| File | MIDAS-relevant change |
|---|---|
| `pages/MidasXLivePage.jsx` | **Binance Paper · Altın** page (`/binance-altin`) — the MIDAS-X gold executor's live view: reads `ict_trade.midas_positions` + `live_account_snapshot`(XAUUSDT) + `live_account`(testnet) via PostgREST, shows account KPIs + open positions (İlk SL / İz-Süren SL / Kilitli R / live K-Z / live R / countdown) + recently-closed. Reuses `LivePositionsPage.css`; badged **PAPER/TESTNET**, never "GERÇEK". |
| `pages/LivePositionsPage.jsx` | (OPUS real-money) — the sibling this clones. |
| `App.jsx` / `layout/Sidebar.jsx` | route `/binance-altin` + a second pinned nav link "Binance Paper · Altın" (amber PAPER accent) directly under "Binance Canlı". |
| `utils/streamStats.js` | MIDAS entry in the `STREAMS` registry (`version:'midas'`). |
| `components/layout/Sidebar.jsx` | MIDAS nav entry (live+paper badge). |
| `components/layout/Topbar.jsx` | `midas: 'Midas'` label. |
| `context/TradeContext.jsx` | `STRATEGY_VERSION/LIVE_MODE/LTF` maps; maps `trail`/`initSl` from `context` (backtest + live); MIDAS-aware live status (`computeLiveStatusFromCandles` → from `context.pos`, never a phantom nominal-TP close). |
| `components/ChartModal.jsx` | Entry/exit + **stepped trailing-stop line** (backtest & live), fixed `SL (1R)` line, green zone, **no** fixed TP / R:R / "Ters Onay"; live trail auto-grows (15s poll of `context.trail` + flat-extends to the current bar). |
| `components/Dashboard.jsx` | MIDAS session-info card (`renderMidasSessions`) + per-session trade distribution; MIDAS cards drop R:R pill / risk-bar, show Exit instead. |
| `utils/strategyInfo.js` | MIDAS intro card (TR/EN). |
| `context/LanguageContext.jsx` | EN strings (Trailing Stop, session card, …). |
| `assets/css/style.css` | `.session-card` styling. |

### Ops — `dag/crontab`
The VM crontab (applied with `crontab dag/crontab`). MIDAS lines: per-minute `canli.py --emit`
(paper) and nightly `backfill.py --apply` at 01:30 UTC. **MIDAS-X** adds a per-minute
`midas_exec/executor.py` + a `*/3` `midas_exec/safety_sweep.py` — both **no-op** until
`LIVE_TRADING_ENABLED=true` AND `MIDAS_EXEC_ENABLED=true` AND `MIDAS_EXEC_DRY_RUN=false` (log →
`~/ict-midas-exec.log`).

---

## 3. Setup from a FRESH CLONE (→ fully working)

> Everything code lives in git. The pieces that do **not** (gitignored) are: `.env` (secrets), `.venv`,
> `node_modules`, `dist`, `scratchpad/` (research caches). Recreate them as below. The two databases are
> external and persist — point `.env` at them.

```bash
# 1. Clone
git clone https://github.com/huseyin-yigit-ulker/ict-trade.git
cd ict-trade

# 2. Recreate .env at the repo root (gitignored — never committed). Required keys in §4.

# 3. Python env
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt   # pandas requests sqlalchemy psycopg2-binary python-dotenv PyGithub
.venv/bin/pip install python-dotenv          # 'dotenv' import name; install python-dotenv

# 4. Node + UI (Node 22.x)
npm install
npm run build                                # outputs dist/ (serve this, or deploy via your host)

# 5. Backtest data: populate version='midas' in the backtest DB
.venv/bin/python sync/midas/backfill.py --dry-run    # sanity (prints totR/PF, no write)
.venv/bin/python sync/midas/backfill.py --apply      # writes ~527 settled trades for 2026

# 6. Live: smoke-test the emitter (no Telegram, no write)
.venv/bin/python sync/midas/canli.py --dry-run

# 7. Install the cron (activates MIDAS + the existing OPUS/FABLE/Donchian jobs)
crontab -l > dag/crontab.backup.live-$(date +%Y%m%d-%H%M%S)   # backup current first
crontab dag/crontab
crontab -l | grep midas                                       # verify the 2 MIDAS lines
```

After this: the **backtest** view shows MIDAS (from step 5), and within a minute **canli** starts emitting
+ tracking the live position (step 7) and the dashboard "Live" view + Telegram come alive.

**Verify it's running:**
```bash
tail -f $HOME/ict-midas.log          # per-minute canli output
crontab -l | grep -c canli.py        # MIDAS + Donchian emit lines present
```

---

## 4. `.env` keys (names only — set your own values)

**Required for MIDAS:**
| Key | Purpose |
|---|---|
| `DB_CONNECTION_STRING`, `DB_TABLE` | Live signals DB (`ict_trade.signals`) — canli writes here. |
| `BACKTESTING_DB_CONNECTION_STRING`, `BACKTESTING_DB_TABLE` | Backtest DB (`ict_trade.trading_signals`) — backfill writes here. |
| `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY` | Live DB REST — UI "Live" view + the chart's 15s trail poll. |
| `BACKTESTING_VITE_SUPABASE_URL`, `BACKTESTING_VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY` | Backtest DB REST — UI "Backtest" view. |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | MIDAS Telegram alerts (same bot as OPUS/FABLE). |

**Ops (optional):** `GITHUB_TOKEN` (git push over HTTPS).

**Not used by the paper MIDAS stream** (`canli.py` / `backfill.py`) — but the **MIDAS-X** real-money
bridge (`sync/midas_exec/`, §5) uses `LIVE_TRADING_ENABLED` + `MIDAS_EXEC_ENABLED` + `MIDAS_EXEC_DRY_RUN`
+ `MIDAS_BINANCE_TESTNET` + `BINANCE_[TESTNET_]API_KEY/SECRET` + the `MIDAS_*` sizing knobs
(see `sync/midas_exec/.env.example`). **OPUS-only** (unused by anything MIDAS): `EXEC_*`, `LEVERAGE*`,
`MARGIN_TYPE`, `RISK_PER_TRADE_USD`, `MAX_*`, `AUTO_LEVERAGE`, `CLOSE_FRAC`, `HORIZON_DAYS`,
`RUNNER_CAP_R`, `DCH_*`, `LIVE_ENTRY_MODE`. Leave all of these unset for a paper-only MIDAS box.

> `VITE_*` vars are read by Vite **at build time** → rebuild (`npm run build`) after changing them.

---

## 5. Operating MIDAS

**Cron jobs** (`dag/crontab`):
- `* * * * *  … canli.py --emit --lookback-min 3 --sl-step 0` — every minute: emit + track + Telegram.
- `30 1 * * * … backfill.py --apply` — nightly 01:30 UTC: rebuild the settled backtest book.

**Tuning the Telegram volume** (edit the cron `--sl-step`, then re-`crontab dag/crontab`):
- `--sl-step 0` → alert on **every** trailing-stop change (current).
- `--sl-step 0.5` → alert only on **locked-R milestones** (breakeven, +0.5R, +1R, …).
- `--no-telegram` → mute MIDAS alerts (signals still written + tracked).

**Telegram messages:** entry formation · each trailing-stop ratchet (direction, entry→last, new stop +
previous + delta, locked R, breakeven state, duration) · exit (price, reason, final R).

**Strategy params** (`sync/midas/strategy.py`): `SLOPE_N=60`, `ATR_INIT_MULT=1.5` (=1R), `TRAIL_MULT=3.5`,
`MAX_HOLD_MIN=480` (8h), `TOUCH_TOL=0.25`, `COST_RT=0.50` ($/oz), `SKIP_UTC_START=7 / END=13` (London skip),
`MATURE_MIN=120` (session-maturity: no NEW entries in the first 2h after the 18:00 ET fx-day open),
`HOLIDAY_FULL_ET` / `HOLIDAY_EARLY_ET` (US-holiday calendar — full-close days off entirely, early-close
days flat 13:00→18:00 ET; **extend yearly**).
Sessions traded: Asia 22-07 (after the 2h maturity window), London-NY overlap 13-17, NY 17-21 UTC;
**London 07-13 UTC skipped**; flat Fri 16:00 ET (weekend buffer); never holds the weekend.

**DB row shapes:**
- Backtest `trading_signals`: one row/trade, `version='midas'`, `context={kind,init_sl,trail:[[unix_sec,price],…]}`.
- Live `signals`: `mode='midas'`, `context={pos:'open'|'closed', cur_sl, best, locked_r, trail, init_sl, …}`.

### MIDAS-X — real-money bridge (TESTNET first) — `sync/midas_exec/`
The gold executor that turns the `mode='midas'` signals into real Binance orders "like OPUS". **It is
fail-closed and testnet/dry-run by default.**

> **⚠️ One-time account prerequisite — sign the "TradFi-Perps agreement".** Gold (XAUUSDT) is a Binance
> `TRADIFI_PERPETUAL`. An account that hasn't accepted the TradFi-Perps agreement gets **`-4411 "Please
> sign TradFi-Perps agreement"`** on every order (verified on testnet). Accept it once in the Binance
> Futures UI (or API) on **each** account you'll use (testnet for validation, mainnet later) BEFORE
> arming — otherwise no XAU order will ever fill. The executor detects `-4411`, logs a clear hint, and
> pings Telegram instead of silently failing.

Bring-up:

```bash
# 0) one-time: create the tables (idempotent, additive — never touches OPUS's live_positions)
psql "$DB_CONNECTION_STRING" -f sync/midas_exec/schema.sql

# 1) parity gate (BLOCKING) — the executor's exit engine must reproduce the backtest to the decimal
.venv/bin/python sync/midas_exec/parity_report.py            # expect: mismatches 0 -> PASS

# 2) dry-run (no orders, no keys) — logs the intended maker entry + stop for each fresh signal
.venv/bin/python sync/midas_exec/executor.py

# 3) TESTNET armed — set BINANCE_TESTNET_API_KEY/SECRET, then:
LIVE_TRADING_ENABLED=true MIDAS_EXEC_ENABLED=true MIDAS_EXEC_DRY_RUN=false \
  MIDAS_BINANCE_TESTNET=true .venv/bin/python sync/midas_exec/executor.py
# or set those in .env and let the cron run it every minute; watch ~/ict-midas-exec.log
```
Emergency: `killswitch.py --status | --flatten | --halt` (`--halt` = `MIDAS_EXEC_ENABLED=false`, MIDAS-only).

**🚧 Mainnet gate (MUST pass before flipping `MIDAS_BINANCE_TESTNET=false`).** MIDAS is validated on a
$0.50/oz FX cost (+142R); at Binance taker (~$4/oz) the same trades are ≈ −92R, and the chandelier exit
is an inherently-taker `STOP_MARKET`. So before ANY mainnet money: re-run the settled MIDAS trades
through the **real Binance fee schedule** (maker on filled entries, taker on the stop exit) instead of
`COST_RT`. Arm mainnet only if that shows a **positive net-of-fee** edge — and even then start at
`MIDAS_RISK_PER_TRADE_USD` $2-5. The near-term value of MIDAS-X is the testnet-validated infra + a
real maker fill-rate/slippage study, not mainnet P&L.

---

## 6. Changelog

> Append a dated entry here whenever MIDAS changes (kept newest-first).

### 2026-06-30 — initial ship + iterations (commits b901404…d75c029)
- **Strategy + research:** built and validated MIDAS (VWAP-trend pullback + 3.5×ATR trailing). Found it
  gold-specific (XAG/BTC/ETH/PT/PD/COPPER/SPY/QQQ all tested, none robust). Report: FX-GOLD-VWAP-RAPORU.md.
- **Backend:** `sync/midas/{strategy,backfill,canli}.py`. Nightly settled-only backfill; per-minute paper
  live emit + trailing track.
- **Session plan:** dropped the London 07-13 UTC session (only net-negative session) → +118R→+142R.
  Weekend buffer (flat Fri 16:00 ET, no weekend positions).
- **Position mgmt:** single-position, ignore-while-open, **no reverse** (tested: reverse hurts −17%).
  Backtest excludes still-open trades (they stay live, settle at EOD via the next nightly backfill).
- **UI:** stream registration; ChartModal entry/exit + stepped trailing-stop line (backtest & live, no
  fixed TP/R:R/"Ters Onay"); live trail auto-grows (15s poll + flat-extend to current bar); Dashboard
  session-info card; MIDAS-aware live status (from `context.pos`).
- **Telegram:** on entry / **every** trailing-stop change (`--sl-step 0`, enriched message) / exit.
- **Cron:** `canli` every minute, `backfill` nightly 01:30. Deployed on the VM (`crontab dag/crontab`).

### 2026-06-30 — VWAP-anchor + single-position + chart fixes (commits a314f7f, b9b7c66, def97ea, e48b68e)
- **Live signal bug FIXED (`strategy.latest_setup`):** it loaded only a 12h window, but the anchored
  VWAP resets at 18:00 ET and a session runs up to ~24h — so it anchored VWAP at the window start
  (~4033) instead of the session open (~4008), ~20-25 pts off. That flipped close>VWAP / close<VWAP and
  fired spurious, often opposite-direction setups (the back-to-back XAU shorts). Now a 2-day warmup like
  `generate_trades` / `track_open`. Live VWAP now matches the backtest.
- **Emitter single-position made DB-AUTHORITATIVE (`canli`):** the guard leaned on `current_open` (a
  sliding-10h re-derivation that returns None in chop), so `latest_setup` kept firing and piled up
  conflicting long+short "open" rows (14 phantoms in ~90 min). Now: if an OPEN midas row exists in the
  live table, emit NOTHING; only look for a setup when flat. Cleaned the phantom rows.
- **Live view staleness FIXED (`TradeContext`):** MIDAS open/closed lives in `context.pos`, refreshed
  only by `loadLive`, which ran only in the 15-min-aligned window → a closed trade lingered as 'AKTİF'
  with a ticking duration. Now MIDAS refetches every 30s + on tab focus (`visibilitychange`).
- **Live chart at the top of the MIDAS live view (`MidasLiveChart`, embedded in `Dashboard`):** a
  trade-independent XAU 1m monitor pinned above the trade list (midas + live only), recomputed every
  30s — anchored VWAP (validated == backend to the cent), ±0.25·ATR(15m) pullback band, AL/SAT markers
  where the core rule fires (== backend signals() over the session), a metrics header, AND a live
  **signal-conditions checklist** (per direction: slope / price-vs-VWAP / pullback-to-VWAP / candle /
  session, each ✓/✗; 🟢/🔴 HAZIR when all met). The per-trade ChartModal VWAP overlay tried first was
  reverted (metrics live on this chart, not the trade chart); the early standalone /midas/chart route
  was folded into the live-view embed.

### 2026-06-30 (2) — closed-trade cards + per-day backtest chart (commits d2468a8, …)
- **Cards show realised R + status, closed trades stop fetching:** `getLiveRLabel` reads the trailing
  trade's stored `context.pnl_r` (e.g. +2.11R / −1.04R) and the `Çıkış` field shows `context.exit_px`;
  a MIDAS row with `context.pos='closed'` is excluded from the live candle poll (TradeContext
  updateStatuses) so closed trades stop pulling price ("kapanan işlem veri almayı kessin"). Surfaces
  once the 30s/visibility loadLive refetch sees pos=closed.
- **Per-day BACKTEST chart (`MidasLiveChart` static mode):** the component now takes optional
  `startMs`/`endMs` props → a fixed historical-day window (no polling, VWAP anchored at that session,
  fit-to-window, no live conditions panel). Embedded in the MIDAS backtest day-notebook ABOVE the
  day's cards: that day's XAU 1m price + anchored VWAP + ±0.25·ATR band + signal-formation AL/SAT
  markers, with the day's trade cards below.
- **Highlight the traded signals:** on the backtest day chart, the signals that actually OPENED a
  trade (the day's cards) render as a bright arrow + "AL/SAT ±R" at their signal bar, while the rest
  of the clustered signal-formation markers are dimmed — so you see which of the many buy/sell signals
  were taken (MIDAS is one-position-at-a-time, so most clustered signals are skipped). Chart + card
  times are all UTC (axis, crosshair, and cards).
- **All signals shown + entry/exit marks, 1m via pagination:** the backtest day chart shows EVERY
  signal-formation (dimmed cluster) with the taken trades highlighted — an amber AL/SAT arrow at the
  ENTRY bar and a result-coloured "Çıkış ±R" circle at the EXIT bar. To keep 1m on a wide day (two
  FX-sessions, ~26h > 1500 bars) the 1m fetch is PAGINATED (up to ~4 pages) instead of coarsening, so
  all client-side signal markers stay accurate. (e.g. 2026-06-29: 1759 bars, 101 signals, 2 trades.)

### 2026-07-01 — ChartModal: closed live MIDAS trade shows the FULL trade (entry→exit path), not a collapsed stub (commit bb61248)
- Root cause of the broken per-trade chart (entry+exit markers piled on the FIRST bar, price never
  reaching the SL): a UNIT bug. `snapBar()` expects milliseconds (it does `Math.floor(ms/1000)`), but
  the MIDAS-live block fed it SECONDS — `entryTs` is already seconds (line ~438) and the trail
  timestamps are UNIX seconds. Dividing a seconds value by 1000 collapses every target to ~1970, so
  `find(time >= t)` matched candles[0] → closeBarSec = the first bar → the candle slice trimmed to
  ~31 bars ending well before the real exit → the SL-hit bar was cut off and Giriş/Çıkış both landed
  on bar 0.
- Fix: pass ms — `snapBar(signalOpenMs + ltfMs)` for the entry fill and `snapBar(trail[-1][0] * 1000)`
  for the close. Verified headless on both live closed trades: SL 3539 (22:03→23:45, window
  21:56→00:15, Giriş@22:03 · Çıkış@23:45, price visibly drops to the 4009.32 stop) and TP 3467
  (05:32→12:57, the 26-point trailing-stop staircase climbs 3966→4012 and the Çıkış lands where it's
  hit, +2.11R). Panels already correct (Süre/Giriş/Çıkış/R); this was chart-geometry only.

### 2026-07-02 — MIDAS-X: real-money-capable Binance bridge (TESTNET / dry-run first) — `sync/midas_exec/`
- **New package `sync/midas_exec/`** — the gold executor that runs MIDAS on Binance "like OPUS", but
  cloned to MIDAS's own mechanics: a **post-only maker LIMIT** entry at the pullback close, the 1.5×ATR
  initial stop, and the **3.5×ATR chandelier trailing** exit driven by the **same
  `strategy.track_open`** the paper feed uses (so live == paper by construction). No fixed TP, no
  reverse, single position. `executor.py` (cron #1) + `config.py` + `state.py` + `schema.sql` +
  `safety_sweep.py` (cron #2) + `killswitch.py` + `parity_report.py` + README/.env.example.
- **Load-bearing fix — `sync/live_exec/exchange_info.py` (additive, backward-compatible):** Binance
  lists gold as `contractType=TRADIFI_PERPETUAL`, NOT `PERPETUAL`, so the old `is_tradable_perp` screen
  silently rejected every XAUUSDT signal (`XAU tradable=False`). Added `is_tradable(sym, allow=…)` +
  retained `contract_type`/`status`; MIDAS passes `allow=('PERPETUAL','TRADIFI_PERPETUAL')`, OPUS's
  `is_tradable_perp` is unchanged. Verified on live mainnet **and** testnet exchangeInfo.
- **Isolation from OPUS:** separate DB tables (`ict_trade.midas_positions`/`midas_orders`, applied via
  `schema.sql`), separate `MIDAS_*` env namespace, and a killswitch/safety-sweep scoped to `XAUUSDT`
  only — the two executors can never flatten each other. Own network flag `MIDAS_BINANCE_TESTNET`
  (testnet-first) so MIDAS validates on testnet while OPUS keeps trading mainnet on the same `.env`.
- **Writeback:** real fills land in `trading_signals` under **`version='midasx'`** (context-aware, with
  the trailing path) — distinct from the paper `'midas'` the nightly backfill DELETE-rewrites.
- **Execution model:** testnet = synthetic (recompute chandelier each tick, MARKET-close on the exit
  trigger — testnet rejects conditional orders with -4120); mainnet = resting `STOP_MARKET(closePosition)`
  + dead-band cancel/replace as the stop ratchets. Maker-only entries: cancel/skip on timeout or
  `MIDAS_ENTRY_MAX_SLIP_R` slip, never chase with a taker. Fail-closed; deterministic `mdx-…` coids
  (crash-safe/idempotent). Realized R/USD from `userTrades`, not the `COST_RT` model.
- **Cron:** added a per-minute `midas_exec/executor.py` + `*/3` `midas_exec/safety_sweep.py` to
  `dag/crontab` — **both no-op** until `LIVE_TRADING_ENABLED=true` AND `MIDAS_EXEC_ENABLED=true` AND
  `MIDAS_EXEC_DRY_RUN=false`. Real-money executor (OPUS) **untouched**.
- **Verified:** `parity_report.py` PASS — **531/531 settled 2026 trades, 0 mismatches** (`track_open`
  replay == backtest `walk()`) + the live paper `mode='midas'` feed (5/5). Dry-run runs clean on the
  testnet base with `XAUUSDT tradable=True`; sizing/slip-guard/intent-logging exercised; armed-testnet
  order path wired (blocked only by the `-4411` account agreement below).
- **Account prerequisite discovered — `-4411`:** gold (a `TRADIFI_PERPETUAL`) needs the account to have
  accepted the Binance **"TradFi-Perps agreement"** or every order is rejected `-4411` (seen on testnet).
  Accept it once per account before arming; the executor now detects `-4411` and logs/pings a clear hint.
- **⚠️ Cost caveat still binding:** +142R (FX) → ≈ −92R (Binance taker). **MIDAS-X stays testnet/paper
  until a Binance-fee simulation shows a positive net-of-fee edge** — this bridge is validated infra, not
  a mainnet green light. See §5 "Mainnet gate".

### 2026-07-02 — Maker-LIMIT entry does NOT rescue MIDAS on Binance fees (the §5 mainnet-gate sim → NEGATIVE)
- This IS the "Binance-fee simulation" the MIDAS-X mainnet gate (above / §5) waits on. Result:
  **maker-limit entry does NOT produce a positive net-of-fee edge → do NOT arm MIDAS-X mainnet.**
- Q: could a **post-only maker LIMIT** entry (0.02% maker vs 0.05% taker) turn MIDAS net-positive on
  Binance? Backtest `scratchpad/midas_maker_bt.py` clones the shipped `walk()` and swaps only the entry
  (validation: FX-flat baseline reproduced +142.8R / 531tr). The maker idea forks into two dead ends:
  - **Limit @ CLOSE ("at current price", ≈ marketable):** fills ~99% but a marketable order is charged
    **taker** in reality → collapses to the market baseline **−47R**. Prints +9R only by *assuming* a
    maker fee it would not actually receive.
  - **Limit @ VWAP (genuinely passive, below market = the pullback target):** earns the maker fee but
    **misses 40-60% of signals** — price runs away without returning to VWAP (adverse selection on the
    very continuation runners that are the edge). Fill-effect alone (FX-flat) already halves it
    +142→+60R; with the Binance % fee the tighter VWAP→stop distance shrinks 1R so fee-in-R explodes →
    **−170R**. Theoretical ceiling (market fill + maker fee, same trades) is only **+16.7R**, unattainable.
- Verdict: you either pay taker (−47R) or miss the runners (−170R). The edge needs (a) EVERY
  continuation fill and (b) a low FIXED cost; Binance's % fee on gold's ~$4600 notional is structurally
  incompatible. MIDAS stays PAPER on Binance; real-money only via a low-fixed-cost FX/ECN broker
  (OANDA v20 / IBKR `ib_async` / cTrader Open API — reliable market fills, ~$0.20-0.50/oz round-trip).
  (Per-trade recompute puts the plain taker+taker loss at −47R, cleaner than the earlier −92R estimate.)

### 2026-07-02 — Session-maturity filter shipped (`MATURE_MIN=120`): no entries in the fx-day's first 2h
- **Loss-anatomy audit of the 2026 book found one structural defect:** the first 2h after the 18:00 ET
  VWAP-anchor reset produced a 188-trade flood worth ≈ 0R net. Root cause is mechanical, not regime:
  (a) with a fresh anchor, price ≈ VWAP by construction → the "pullback touch" fires constantly;
  (b) the 60-bar slope window **crosses the anchor reset**, comparing the fresh VWAP against the prior
  day's full-session VWAP → the trend gate is meaningless there. Proof: masking the slope to
  within-session-only gives **identical** results to skipping the first 60 min.
- **Fix:** `MATURE_MIN=120` in `signals()` — no NEW entries in the first 120 min of the fx-day (open
  positions/exits untouched). 2026-H1: +139.5R/528tr → **+145.0R/396tr**, PF 1.46→**1.68**, maxDD
  −23→**−18**, worst month +11.1→+17.3, **IS +81→+85 AND OOS +58→+60 both improve**; plateau smooth
  across 30–180 min. 25% fewer trades = lower fixed-cost drag. DB rebased: 530 → **400 rows, +150.5R,
  WR 40%, PF 1.70** (full year through Jul-2). Backfill + canli pick it up automatically (single
  `signals()` path).
- Rejected after honest IS/OOS tests (kept out deliberately): breakeven-ratchet at +1R (standalone
  +6R but redundant with maturity — combo LOSES R; a `BE(1.0→+0.1R)` combo trades ~11R for WR 37%→54%
  if smoothness is ever wanted); extending the 8h time-stop (10h/12h/∞ all worse — the cap locks
  profit near its peak); strong-slope entry filter (IS/OOS inconsistent); same-day loss-streak cooldown
  (inverted: trades after 2-3 same-day losses are the BEST bucket, avgR ~0.8, IS+OOS consistent).
- London 07-13 UTC salvage re-tested: trend-in-window −9.9R, VWAP-fade +24.9 IS → **−31.1 OOS**
  (sign-flip mirage), tight fade −18.4R → the skip stays; the window is dead, not mis-traded.

### 2026-07-02 (5) — MIDAS-X cron installed on the VM (dry-run) + TradFi still blocking
- Installed the two MIDAS-X cron lines into the live crontab (`crontab dag/crontab`; backed up first to
  `dag/crontab.backup.pre-midasx-*`). Diff confirmed the ONLY change vs the running crontab was the
  MIDAS-X block. It runs **dry-run** (MIDAS_EXEC_* unset → not armed): every minute it refreshes the
  testnet `live_account`/XAU snapshot (so the "Binance Paper · Altın" page stays fresh, no "5 dk eski")
  and logs intended orders — NO orders, NO positions. Log: `~/ict-midas-exec.log`.
- TradFi-Perps agreement STILL unsigned (re-probed → `-4411`), so arming now would only spam `-4411`
  per signal with zero fills. To start real testnet paper trades: sign the agreement, then set
  `MIDAS_EXEC_ENABLED=true` + `MIDAS_EXEC_DRY_RUN=false` (one flip). Kept dry-run deliberately until then.

### 2026-07-02 (4) — fix: MIDAS-X testnet account row made the OPUS "Binance Canlı" page read stale
- Regression from adding MIDAS-X: it writes a second `ict_trade.live_account` row (network='testnet')
  into the table OPUS's `LivePositionsPage` reads with `acc[0]` (unordered) → PostgREST returned the
  testnet row first, so the real-money page showed the stale testnet account + a false "5 dk'dan eski"
  warning (OPUS's mainnet executor was actually fresh, ~20-47s). Fix (`src/pages/LivePositionsPage.jsx`):
  pick `acc.find(a=>a.network==='mainnet') || acc[0]`, and scope the snapshot query to
  `network=eq.mainnet`. MIDAS-X page already reads its own network via the XAU snapshot. Needs a UI
  rebuild/deploy to reach the live dashboard. (MIDAS-X page's own "stale" is correct — it isn't running:
  cron not installed + not armed.)

### 2026-07-02 (3) — strict paper/live API-key separation
- MIDAS-X `config.py` key selection is now STRICT: paper (testnet) uses ONLY `BINANCE_TESTNET_API_KEY/
  SECRET`, live (mainnet) uses ONLY `BINANCE_API_KEY/SECRET` — removed the testnet→mainnet fallback so
  the paper executor can never borrow the real-money key. Missing the required key while armed →
  fail-closed. Verified: MIDAS-X paper → testnet base + testnet key (not live); MIDAS-X mainnet → live
  key; OPUS unchanged (mainnet + live key, still armed). (`.env BINANCE_TESTNET=false` = OPUS mainnet.)

### 2026-07-02 (2) — UI: "Binance Paper · Altın" page for MIDAS-X (under Binance Canlı)
- Added `src/pages/MidasXLivePage.jsx` at route **`/binance-altin`**, pinned in the Sidebar directly
  under the real-money **Binance Canlı** (OPUS) link with an amber **PAPER** badge (never the gold
  "Binance · GERÇEK"). It's a clone of `LivePositionsPage` pointed at MIDAS-X's tables:
  `ict_trade.midas_positions` + `live_account_snapshot`(symbol=XAUUSDT) + `live_account`(testnet),
  read anon via PostgREST (grants from `sync/midas_exec/schema.sql`). Columns fit the trailing model:
  Giriş / Mark / İlk SL / **İz-Süren SL** (cur_sl) / **Kilitli R** (locked_r) / live K-Z / live R /
  countdown (entry_deadline or 8h time-stop), + account KPIs + recently-closed. Network chip auto-reads
  the XAU snapshot's network (TESTNET now). Reuses `LivePositionsPage.css`; `npm run build` clean.
- The page is empty until MIDAS-X actually runs (arm on testnet + install the cron); it's a live
  30s-refresh view of whatever the executor has snapshotted.

### 2026-07-02 (6) — Filter audit: DST anchor bug fixed + US-holiday calendar added
- **Full audit of the session/market-hours filters** (user request), three parts: (1) calendar logic —
  all 7 rules PASS on 259,581 bars, zero violations, and the Mon-Thu 17:00-18:00 ET break is confirmed
  BY DATA (min-volume ET hour = 17:00 in every month, volume −85..95%, tracking DST 22→21 UTC exactly);
  (2) trade-book compliance — 0 London-window entries, 0 immature entries, 0 positions held through a
  closed bar, latest Friday exit 15:59 ET, longest hold exactly 8h, fill always signal+1 bar;
  (3) two real defects found and fixed:
- **BUG — DST spring-forward anchor slide.** `_fx_day` used `(et − 18h).normalize()`; the 18h
  subtraction crosses the 02:00 DST jump, so on 2026-03-08 the fx-day boundary slid to 19:00 ET: the
  Sunday-open hour glued onto the synthetic-weekend group → weekend-contaminated VWAP + bypassed
  maturity filter → 4 phantom trades (bars_in showed 1380). **Fix: `(et + 6h).normalize()`** — the
  6h span 18:00→midnight never contains the 02:00 jump, provably DST-safe both directions; boundaries
  now pin to 18:00 ET on every day incl. transitions.
- **GAP — no holiday model.** Binance keeps printing synthetic EWMA bars through real-market halts:
  Jan-1 medVol **0.0**, MLK **2.4** (vs ~105 normal) yet the book "filled" 16 trades worth +13.5R of
  partly-phantom liquidity across 6 US holidays. Added a volume-calibrated CME/COMEX calendar:
  `HOLIDAY_FULL_ET` (Jan-1, Good-Friday, Christmas, New-Year-27: whole ET day off) +
  `HOLIDAY_EARLY_ET` (MLK, Presidents, Memorial, Juneteenth, Jul-3, Labor, Thanksgiving+Fri, Dec-24:
  flat 13:00→18:00 ET — data shows the 18:00 evening reopen is real volume, so it stays on).
  **Extend the lists yearly.**
- Net effect (honest correction DOWN): 2026-H1 +145.0R/396tr → **+139.5R/385tr, PF 1.67** (phantom
  profit removed); full-year DB rebased 400 → **389 rows, +145.0R, WR 39%, PF 1.70**. IS +80.8 / OOS
  +58.7 both still comfortably positive. Live cron picks both fixes up automatically (single
  `add_market_open`/`_fx_day` path); first live effect: Jul-3 (July-4th observed) flat from 13:00 ET.

### 2026-07-02 (7) — Live/backtest parity audit PASS + 3 orphan live rows deleted
- **Parity audit** (cron + signal formation + chart data): installed crontab == dag/crontab, canli
  fresh to the minute; matched live signals have 0 SL / 0 entry-ref mismatches; the two settled trades
  common to both sides match the backtest book **to the cent** (05:31 +2.11R, 20:02 −0.33R);
  `parity_report.py` (track_open vs walk) 0 mismatches under the new filter code; backtest rows 12/12
  integrity PASS (trail endpoints/monotonic ratchet/pnl recompute/no overlap/London+holiday compliance).
- **Deleted 3 orphan `mode='midas'` live rows** (user: "görmeyeyim") that today's filters would never
  emit — they were real alerts from older code eras, absent from the authoritative book:
  Jun-30 18:34 LONG −1.04R (pre-VWAP-anchor-fix b9b7c66 artifact), Jun-30 22:02 LONG −1.06R and
  Jul-1 22:01 LONG +3.65R (session-open flood, pre-`MATURE_MIN` era). Net −1.55R of phantom live
  history removed; live view now shows exactly the book-consistent trades. One transition artifact
  noted, no action needed: the book's Jul-2 00:43 +3.30R trade has no live twin (live was held by the
  pre-filter 22:01 position at the time; self-resolves).

### 2026-07-03 — MIDAS-X ARMED on TESTNET (paper): TradFi agreement signed via API, $5 risk
- **The -4411 blocker is GONE**: the TradFi-Perps agreement can be signed via the API —
  `POST /fapi/v1/stock/contract` (signed request) — done on the TESTNET account; verified by a
  far-from-market post-only probe order (ACCEPTED status=NEW, then cancelled clean). Testnet
  balance $5055 USDT.
- **Armed the paper executor** (.env, backed up first): `MIDAS_EXEC_ENABLED=true`,
  `MIDAS_EXEC_DRY_RUN=false`, `MIDAS_BINANCE_TESTNET=true` (explicit), `MIDAS_RISK_PER_TRADE_USD=5`
  (user: $5/trade risk, OPUS convention). First armed cycle:
  `ARMED (LIVE ORDERS) | testnet | XAUUSDT risk $5 5x ISOLATED | maker=True` — cron (every minute)
  now places REAL testnet orders on the next mode='midas' signal and manages the 1.5×ATR stop +
  3.5×ATR chandelier trailing continuously (track_open-driven, synthetic MARKET-on-trigger on testnet).
- Guardrails unchanged: testnet-only key (strict separation — can never borrow the mainnet key),
  XAUUSDT-scoped killswitch/safety-sweep, OPUS untouched, **mainnet still gated OFF** (the fee study
  proved MIDAS dies on Binance % fees — this is a fill-quality/slippage study, not a mainnet
  green light). "Binance Paper · Altın" (`/binance-altin`) page will populate as positions open.

### 2026-07-04 — MIDAS-X multi-user (kullanıcı-bazlı paper execution; RUNBOOK §8a)
- MIDAS-X executor'ı OPUS ile aynı **çift-modlu** multi-user desenine geçirildi:
  `EXEC_MULTI_USER=false` (şu an) = bugünkü tek-hesap davranış birebir; `true` = onaylı kullanıcılar
  kendi **testnet** anahtarlarıyla paper işlem açar (`sync/users/store.load_exec_users(stream='midas')`
  network'ü testnet'e kilitler; DB tarafında da `user_stream_settings` CHECK'i MIDAS mainnet'i reddeder —
  fee analizi kararı değişmedi, mainnet kapalı).
- `config.py` (`cfg_for_user`), `state.py` (dual-mode act-once insert + user-scoped okuma),
  `executor.py` (`SharedTick` 1m-kline/exchangeInfo cache — */1 cadence'ta kritik; kill-switch gate,
  günlük zarar limiti, kişisel push `push_outbox`; Telegram + `trading_signals(version='midasx')`
  writeback sadece canonical/owner), `safety_sweep.py` (kullanıcı başına orphan taraması),
  `killswitch.py` (`flatten_positions` + `--user <email>`). Maker-entry/chandelier mantığına dokunulmadı.
- Cutover MIDAS için ayrı adım gerektirmez: OPUS'un Faz-5 penceresindeki `005b` index swap'i midas
  tablolarını da kapsar, aynı `EXEC_MULTI_USER` bayrağı iki executor'ı birlikte çevirir.

### 2026-07-07 — AFTER-LOSS exec-kapısı (MIDAS_EXEC_AFTER_LOSS_ONLY) + realized_r race düzeltmesi
- **Kapı (exec-only overlay):** executor artık `MIDAS_EXEC_AFTER_LOSS_ONLY=true` iken yalnızca **aynı
  fx-gününün önceki settled paper işlemi negatif kapandıysa** pozisyon açıyor (`_after_loss_gate` +
  `_fx_day_open_utc`, DST-güvenli +6h konvansiyonu). Günün ilk sinyali ve kazanç-sonrası sinyaller
  SKIP loglanır; **paper feed'e (mode='midas') dokunulmadı** — "önceki işlem" tanımını zaten paper akışı
  sağlıyor. Dry-run intent yolu da aynı kapıyı gösterir. Multi-user'da `cfg_for_user` → `dataclasses.replace`
  ile tüm hesaplara taşınır. `.env`'de AÇIK (yedek: `~/env.backup.pre-afterloss-20260707`).
- **Neden (2026-07-07 backtest, oturum harness'i):** 2026 Binance-vol setinde kapı = 204 işlem,
  $0.50'de +113.7R/PF 2.08; **taker 10bp'de +53.6R/PF 1.37** (tam set +27.1R/PF 1.09'un ~2 katı),
  taker IS +32.9 / OOS +20.7 ikisi de pozitif; runner yakalama 26/41 (+146/+222R). Gevşek tanım
  (herhangi pnl_r<0; session/time negatifleri dahil) katı "sadece SL≤−0.8R" tanımından İYİ (o: taker
  IS +4.3). ⚠️ **Rejim kalkanı DEĞİL:** HistData çok-yıllık testte 2024 −16.9R / 2025 −19.7R ($0.50,
  TWAP; tam set −66.6/−28.3'ten yumuşak ama hâlâ negatif); taker'da kötü rejim ~−18R/ay kanar.
  Temmuz-2026'da kural −4.9R (ayın runner'ı +3.63R günün İLK işlemiydi → kaçtı). Mainnet kararı
  değişmedi: **testnet'te veri topluyoruz**, mainnet kapalı.
- **realized_r=0.000 düzeltmesi:** `_finalize` exit MARKET emrinden hemen sonra `userTrades`'i
  sorguladığında fill henüz düşmemiş olabiliyor ve `_realized_since` hem gecikmede hem `BinanceError`'da
  sessizce 0.0 dönüyordu → pozisyon #3/#6 kalıcı `realized_r=0.000` yazıldı (2026-07-03/06). Şimdi:
  walk breakeven demiyorsa (|res_pnl_r|>0.02) 3×2s retry + `BinanceError` artık loglanıyor. Ölçüm-only;
  emir yoluna dokunulmadı.
- Doğrulama: `py_compile` temiz; kapı canlı DB'de 4/4 bilinen vakayla test edildi (07-06 01:06 PASS,
  07-07 00:31 ilk-işlem SKIP, 07-03 06:05 kazanç-sonrası SKIP, 07-06 02:00 PASS; flag=false → no-op);
  armed testnet tick temiz (açık pozisyon #46 trail takibi sürüyor).

### 2026-07-07 (2) — Kapı kararları görünür: context.exec_gate + Telegram bildirimi + live sayfa tablosu
- **Executor (`_mark_gate`):** kapı kararı artık paper sinyal satırına yazılıyor —
  `context.exec_gate = {skipped, reason, at}`, atomik `jsonb ||` merge + `? 'exec_gate'` guard'ı
  (sinyal 15 dk giriş penceresinde kaldığı için dedup şart; ilk işaretleyen tek Telegram/push atar).
  SKIP → 🚧 Telegram (owner) + kişisel push (`kind='system'`); PASS → sadece işaret (giriş alert'i
  zaten var). Dry-run yolu DB'ye yazmaz (eski davranış). canli `_track_open_positions`'ın
  read-modify-write'ı ile çakışma cron ofsetleri (:20s vs :35s) sayesinde pratikte yok; en kötü
  ihtimal bir kez yeniden işaretleme = 1 duplike alert.
- **UI (`MidasXLivePage`):** başlığa "🚧 Kayıp-sonrası kapı" rozeti (tooltip'te kural) + yeni
  **"Sinyaller · Kapı Kararları"** tablosu: son 10 mode='midas' sinyali — kapı hükmü (AÇILMADI /
  EMİR AÇILDI / kapı öncesi), sebep, ve **Paper Sonucu** kolonu (atlanan işlemin paper R'si =
  kapının kaçırdığı/kurtardığı canlı canlı izlenir — karşı-olgu takibi).
- Doğrulama: `_mark_gate` SQL'i gerçek satırda transaction+ROLLBACK ile test edildi (ilk mark yazar,
  ikincisi dedup None), py_compile + esbuild temiz; Telegram kanalı raw API ile teyit (200 ok).
  Aktivasyon duyurusu kanala gönderildi. 2026-07-07 14:36 sinyali kasıtlı "kapı öncesi" kalır
  (pozisyon #46 kapıdan önce girildi — sahte tarih yazılmadı).

### 2026-07-07 (3) — 🔴 MIDAS-X MAINNET'E ALINDI: $3 risk + oto-kaldıraç + borsa-tarafı iz-süren stop
- **KULLANICI KARARI** (soru-cevapla teyit: kaldıraç=oto/25x cap, giriş=maker GTX, arm=evet):
  MIDAS-X artık Binance MAINNET'te GERÇEK PARA işler. Araştırma kaydı değişmedi — çok-yıllı OOS
  negatif, 2026 @taker after-loss kapısıyla +53.6R PF1.37; küçük boyut + kitap takibi şart.
- **Konfig**: `MIDAS_RISK_PER_TRADE_USD=3` (kullanıcı: "$3 SL"), `MIDAS_MAKER_ENTRY=true`
  (kullanıcı tercihi; taker+taker doğrulanmış sete karşı maker'ın koşucu-kaçırma riski kabul edildi),
  `MIDAS_BINANCE_TESTNET=false`, `MIDAS_EXEC_AFTER_LOSS_ONLY=true` (değişmedi).
- **Oto-kaldıraç (kullanıcı isteği, OPUS kuralı)**: `MIDAS_AUTO_LEVERAGE=true`, işlem başına
  `L = min(MIDAS_LEVERAGE_MAX=25, floor(0.5/SL%))` — likidasyon her zaman SL'in ≥2 katı uzakta;
  altının küçük SL%'si fiilen 25x'e sabitler = paylaşılan cüzdanda asgari marj. `executor._place_entry`
  girişten önce `set_leverage` çağırır, hata halinde `MIDAS_LEVERAGE=20` sabitine düşer; pozisyon
  satırına `leverage` yazılır, GİRİŞ Telegram'ına "· {lev}x (oto)" eklendi.
- **İz-süren SL mainnet'te borsa tarafında**: mevcut `_place_protective_stop` / `_update_trailing`
  yolu (resting `STOP_MARKET(closePosition)` + dead-band'li cancel/replace) artık aktif — testnet'in
  sentetik modelinden farkı bu; kod değişikliği gerekmedi, sadece ağ değişti.
- **Kilit açma**: migration `012_midas_mainnet.sql` (`midas_testnet_only` CHECK düştü, UYGULANDI) +
  `sync/users/store.py` testnet hard-lock kaldırıldı. `tg_uss_guard` taban korumaları aynen (geçerli
  anahtar, bakiye %25 tavanı: $3×1 ≤ $111×%25 ✓, one-way, universe).
- **Satırlar**: owner `user_stream_settings` midas/mainnet EKLENDİ (enabled, risk 3, mc 1,
  max_total 3, XAUUSDT); midas/testnet satırı `enabled=false` → DRAIN (açık #46 LONG kapanana dek
  yönetilir — `has_open` yüklemeyi sürdürür — yeni giriş açılmaz, sonra satır kendiliğinden düşer).
- **Mainnet hazırlık doğrulaması**: TradFi-Perps mainnet hesapta zaten kabul — uzak-fiyatlı post-only
  prob emri KABUL (status=NEW) edilip temiz iptal edildi; bracket tier-1 100x/50k (25x serbest);
  XAUUSDT mainnet TRADING/TRADIFI_PERPETUAL, tick 0.01 / minQty 0.001 / minNotional $5.
- **İlk armed tick teyidi**: `ARMED (LIVE ORDERS) | MAINNET | risk $3` — 2 satır yükleniyor
  (mainnet giriş-açık + testnet drain), safety sweep iki ağda 0 breach, snapshot'lar per-network.
- **UI**: MidasXLivePage artık AĞ-DİNAMİK (mainnet-öncelikli snapshot; başlık/rozet/uyarı GERÇEK↔PAPER
  veriden; drain'deki testnet satırı "PAPER" etiketiyle, mark/uPnL kendi ağının snapshot'ından).
  Sidebar: altın panosu "Binance · Altın ● GERÇEK", MIDAS grubu real rozetli. İşlem Merkezi:
  midas mainnet satırı eklendi (yazılı GERÇEK PARA onayı akışı OPUS'la aynı). strategyInfo caveat
  güncellendi. Cüzdan notu: mainnet $111 OPUS'la paylaşılıyor — geniş-ATR günlerinde marj yetmezse
  giriş atlanır (fail-safe), gerekirse bakiye ekle.
- Geri alma: `user_stream_settings` midas/mainnet `enabled=false` (aç pozisyon varsa drain) veya
  `killswitch.py --flatten`; `.env` `MIDAS_BINANCE_TESTNET=true` + testnet satırını enable et.

### 2026-07-07 (4) — ARAŞTIRMA (kod değişikliği YOK): flip/whipsaw + rejim incelemesi — filtre SHIP EDİLMEDİ
- **Soru 1 (kullanıcı): "AL/SAT eşiği çok ince, AL deyip hemen SAT diyebiliyor — nasıl daha valid olur?"**
  Kök neden: trend yönü `sign(vwap − vwap.shift(60))` ve ölü-bant yok (`strategy.py` signals);
  flat-VWAP'ta işaret bar-bar döner, giriş şartı da fiyatı tam o bölgeye ister.
  **Empirik sonuç (2026 Oca–Tem, 397 işlem, gerçek yeniden-yürütme):** hızlı flip'ler KÂRLI —
  çıkış→ters-giriş ≤60dk olan 86 işlem toplam +43R (ort +0.50R). Denenen tüm sağlamlaştırıcılar
  toplam R'yi düşürdü: ölü-bant |slope|≥k·ATR (k=0.05→+117R, 0.15→+64R vs base +143.5R),
  histerezis/Schmitt per-day-reset (k=0.20→+107R), dwell M-bar (15→+135R, 60→+89R).
  Tek makul aday: **60dk ters-yön cooldown** → +122.2R/PF1.65, ≤60dk flip=0 (yapısal),
  IS +50/OOS +73 (base OOS +62'den İYİ); maliyet ~%15 R, tamamı IS'te. SHIP edilmedi
  (istenirse lab varyantı veya UI/push flip-etiketi olabilir).
  **Literatür (deep-research, 20 kaynak):** ölü-bant/histerezis klasik whipsaw reçetesi
  (BLL 1992 %1 band; STW 1998 katalog; US Patent 7,496,534 "break penalty" + 15dk min-dwell)
  AMA (a) whipsaw trend-takibin yapısal maliyeti, son whipsaw'ları silmek için ayar = overfitting;
  (b) intraday FX'te optimal band ≈ işlem maliyeti ve net edge'i kurtarmıyor (Neely–Weller 1999);
  (c) edge trend-anlamlılığıyla lineer büyür ama t≳1.8–2 üstü trendler DÖNER (Schmidhuber 2020) —
  agresif eğim filtresi ters teper; (d) Shannon AVWAP pratiği: flat VWAP = nötr 3. durum,
  "buy strength after the dip" (bizim `c>o` confirm mumu bunun mekanize hali).
- **Soru 2 (kullanıcı): "rejim trend olunca / geçiş durumuna göre incele."**
  **Concurrent teşhis (tam-gün bilgisi):** edge'in TAMAMI trend günlerinde — day-ER üst tercile
  +143.6R (≈toplamın %100'ü), RANGE günleri −6.8R; gün yönüyle uyumlu işlemler +232R / ters −88.5R;
  en iyi 10 gün toplamın %66'sı. **Predictive (sinyal anında bilinen) — hiçbiri filtre olacak güçte
  değil** (tüm Spearman |ρ|≤0.10): slope-flip'ten ≤60dk sonraki "GEÇİŞ" girişleri EN İYİ bucket
  (n=166, ort +0.45R, PF 1.78, IS+OOS pozitif — "geçişte sinyal şüpheli" sezgisinin tersi);
  er240 düşük tercile iyi (sakin piyasadan doğan trende erken giriş); ADX orta-bant (19–28) iyi ama
  non-monotonik; eğim dikliği bilgisiz; "dün RANGE'di → girme" filtresi +19.8R atar → net kayıp.
  Sonuç: rejim edge'i eşzamanlı yaşıyor, önceden yakalanamıyor (Donchian regime-timing-fails'in
  MIDAS kopyası). **Hiçbir rejim filtresi ship edilmedi; mevcut yapı (her pullback'i al, trailing
  ayıklasın) korunuyor.**
- Scriptler (scratchpad, commit edilmez): `flip_analysis.py`, `flip_variants_bt.py`, `regime_analysis.py`.

### 2026-07-07 — "MIDAS'tan iyi XAU stratejisi" taraması: 30+ aile, kazanan aday KELT075 (Keltner alt-bant pullback) — SHIP edilmedi, portföy adayı
- **Soru (kullanıcı):** MIDAS gibi iz-süren stoplu ama VWAP dışı metriklerle, 2026 XAU'da MIDAS'tan
  daha başarılı strateji bul; literatür/blog/YouTube tara.
- **Yöntem:** 2 web-araştırma ajanı (akademik: Gao/Jin ITSM, Zarattini Noise-Area/ORB, Kaminski–Lo
  stop literatürü; pratisyen: Asya-range, EMA-pullback, Supertrend/UT-Bot/chandelier aileleri) +
  4 tur backtest taraması (~90 varyant), hepsi MIDAS iskeletiyle (1.5×ATR stop, 3.5×ATR trail,
  8h cap, sabit TP yok, $0.50/oz, shipped seans maskesi + m120, engine.py, no-lookahead).
  Benchmark repro: +142.6R/390tr ≈ shipped +145R/396tr ✓.
- **Elenenler (2026-H1 XAU, totR):** EMA/KAMA-pullback +5..+27 (VWAP→EMA ikamesi edge'i öldürüyor
  — MIDAS edge'i VWAP'a özgü), Supertrend flip/pullback −21..+2, PSAR −34..−2, Donchian-1m
  −50..−9 (gövde-kalite filtresi de kurtarmıyor), ORB (NY/LDN/FX-open) −23..+12, önceki-gün H/L
  −13, Asya-range −18..+6 (kalite kapılı hiç sinyal üretmedi), TSM/ITSM −35..+26, Zarattini
  Noise-Area −21..+20, haber/PM-fix devam −23..−16, TTM-squeeze +11..+20, Fib golden-pocket +9..+89
  (IS-ağır), Hull +4..+7. Sweep-reclaim'in ilk +99R/PF7.4 sonucu fx-günü sarmalı LOOKAHEAD çıktı
  (22-23 UTC barları gelecekteki Asya kutusunu görüyordu); düzeltince +8R/12tr.
  Vol-ratio kapısı (seans-içi kümTR / 14-gün aynı-dakika ort — literatürün "yüksek-vol günü" koşulu)
  PF'yi 1.68→1.86 yükseltiyor ama totR'yi kırpıyor (+142.6→+87.5..+113.8) — bilinen filtre paterni.
- **Kazanan aday: KELT075** = 15m Keltner(EMA20, ATR20) alt/üst bandına (kmult 0.75) derin pullback,
  trend=15m EMA20 4-bar slope, giriş=banda değip in-trend kapanış (c>o), MIDAS filtreleriyle
  (skip 07-13 UTC + m120). 2026-H1: **+87.5R/314tr, PF 1.54, DD −8.3** (MIDAS +142.6/DD −18.0).
  Plateau düz (kmult .625-.875 × trail 3.5-4.0 → +75..+88), random-null P=0.000 (~3σ),
  IS +55.9 / OOS +31.6.
- **Çok-yıllık PAXG OOS (asıl koz):** KELT 2024 −168.8 / 2025 **+114.5 (PF 1.33)** / 2026 +93.5
  (PF 1.55, DD −9.7) = 3-yıl **+39.2R** vs MIDAS-repro −298.3 / +20.6 / +94.7 = **−183.0R**.
  KELT hacim kullanmadığından PAXG'de tutarlı; 2025'te MIDAS'ı ezip geçiyor, 2024 kaybı yarısı.
- **Portföy:** zaman-çakışma %80 ama günlük R korelasyonu 0.396; MIDAS+KELT 2026-H1
  **+230.1R, DD −21.1**, her ay +26..+50. Temmuz 1-6 mini-OOS anlamsız küçük (KELT −3.2/9tr,
  MIDAS +1.5/10tr).
- **Karar: SHIP edilmedi.** Tek başına KELT 2026 totR'de MIDAS'ı geçemiyor; "daha başarılı" tek
  konfigürasyon MIDAS+KELT portföyü (+%61 R, DD +%17) + çok-yıllık dayanıklılık KELT'te.
  İstenirse sonraki adım: `sync/kelt/` paper stream (MIDAS şablonundan) + UI.
- Scriptler (scratchpad, commit edilmez): `fx_gold/strategies2.py`, `scan2{,b,c,d}.py`,
  `validate_kelt.py`, `kelt_overlap_july.py`.

### 2026-07-07 (2) — Tarama kazananı KELT075 SHIP EDİLDİ → yeni akış TALOS (ANTARES)
- Yukarıdaki taramanın kazanan adayı kullanıcı kararıyla 3. canlı akış oldu: **TALOS** (paper-only,
  executor yok) — `sync/talos/` (MIDAS'ın walk/trailing/seans motorunu import eder, yalnız giriş
  metriği farklı: 15m Keltner alt/üst bandına derin pullback). 2026 backtest version='talos'
  (+87.7R/323tr/PF1.53), canlı mode='talos' her dk (+30s) Telegram ON, nightly backfill 01:40,
  migration 013, UI uçtan uca (canlı Keltner grafiği dahil). Detay: RUNBOOK.md changelog 2026-07-07 (11).

### 2026-07-08 — MIDAS-X kaçan işlem post-mortem: maker→taker fallback (pos#47)
- **Şikayet (kullanıcı):** dünkü MIDAS sinyali Binance'te işlenmemiş.
- **Teşhis (loglar):** mainnet cutover (07-07 18:11) sonrası 2 sinyal: (1) 07-08 00:05 LONG →
  `after-loss gate` SKIP (fx-gününün ilk işlemi — TASARIM GEREĞİ, bug değil; paper'da −0.27R kapandı,
  kapı doğru çalıştı); (2) 07-08 01:12 LONG → pozisyon #47 yaratıldı, maker GTX limit 4108.91'e
  kondu, 01:14'te fiyat 0.25R toleransın ötesine kaçınca **"entry slipped — cancelled"** — işlem
  tamamen KAÇTI (paper işlem koşarken Binance flat). Ayrıca 07-07 00:33 testnet SHORT'u da aynı
  yoldan iptal olmuştu; 14:37 LONG testnet'te dolmuştu.
- **Kök neden:** saf GTX giriş ters-seçilim tuzağı — pasif limit yalnız fiyat aleyhe DÖNÜNCE dolar;
  kaçan fiyat = tam da edge'in yaşadığı runner. 2026-07-02 maker araştırmasının canlıdaki tezahürü
  (pasif maker runner'ların %40-60'ını kaçırır; taker+kapı kitabı +53.6R).
- **Düzeltme (executor.py + config.py):** **maker→taker fallback** — GTX
  `MIDAS_ENTRY_TAKER_FALLBACK_SEC` (varsayılan 60 sn; 0=eski saf-maker) içinde dolmazsa VE fiyat
  hâlâ `MIDAS_ENTRY_MAX_SLIP_R` (0.25R) toleransındaysa limit iptal + MARKET giriş (kendi coid
  gen'i; cancel/fill yarışı MARKET'ten önce yeniden sorgulanır — dolmuşsa çift pozisyon açılmaz;
  parsiyel dolumlar fallback dışı; fallback bir kez ateşlenir, sonraki retry'lar taker kalır).
  Tolerans DIŞINA kaçan fiyatta davranış değişmedi (iptal — geç girmek başka bir işlemdir).
  `_manage_entry` artık kayıtlı `entry_coid`'i okur; `_enter_open` gerçek fill'in coid'ini saklar.
- Beklenen etki: giriş fiyatı sinyalin ≤0.25R yakınında garanti (backtest pariteye uygun), maker
  indirimi fırsat varsa alınır, runner kaçırma biter. README + RUNBOOK env listesi güncellendi.

### 2026-07-08 (2) — ARAŞTIRMA (canlı kod değişikliği YOK): ML meta-labeling denemesi — NO-SHIP, rapor ML-XAU-RAPORU.md
- **Soru:** DL/ML ile XAU sinyal modeli — literatürde ne çalışıyor + repo'nun ilk ML deneyi.
- **Literatür karnesi (ML-XAU-RAPORU.md §1):** çalışan = meta-labeling (López de Prado/H&T),
  GBM+tabular-özellik, triple-barrier+purged-CV, günlük DL-momentum (1m'e taşınmaz); çalışmayan =
  "LSTM altın tahmini" ailesi (naif-gecikme/maliyetsiz), LOB-DL (maliyet-sonrası ölür), RL ajanlar.
- **Deney (Aday A):** SHIP'li MIDAS sinyalleri üzerinde LightGBM meta-model P(R>0), 21 sinyal-anı
  özellik, 2020 işlem (XAU26 396/+143R ✓ + PAXG24 860/−297R + PAXG25 764/+19R). Purged 5-fold
  (1g embargo) OOF AUC 0.563; null-shuffle 0.511 ✓; transfer 24+25→26 AUC 0.572 (sinyal taşınıyor).
  **No-lookahead truncation denetimi PASS (60 sinyal, fark 0.00e+00)** — `lookahead_check_ml.py`.
- **Ekonomi = NO-SHIP:** deploy yönünde (24+25 eğit → 26 test) eşit-n'de meta +78.9R < canlıdaki
  AFTER-LOSS kapısı +114.8R; kombinasyonlar kapıyı geçemedi (∨p≥0.60: +117.0 ≈ gürültü). Prob-
  kantilleri 2026'da monoton değil (kalibrasyon rejim-kaymalı). Ters yön: kötü-yıl kanamasını
  −278→−53R'a yumuşatıyor (AFTER-LOSS'tan iyi) ama pozitife çeviremiyor — rejim kalkanı DEĞİL.
- **Yorum:** MIDAS'ın girişleri zaten 3 süzgeçli (London-skip+MATURE_MIN+AFTER-LOSS); meta'nın tüm
  katkısı bu bilinen yapıya indirgeniyor (top özellikler: mins_in, dist_vwap, atr_ratio). Sonraki
  adaylar raporda: 15m TB yön modeli, KELT075/TALOS üstünde meta (süzgeci zayıf birincil).
- **Dosyalar:** `scratchpad/fx_gold/ml/{features,labels,meta_midas,combo_test,lookahead_check_ml}.py`
  + `ML-XAU-RAPORU.md`. `.venv`'e sklearn 1.7.2+lightgbm 4.6.0+scipy kuruldu (requirements'a
  EKLENMEDİ — araştırma bağımlılığı). Canlı kod/DB/cron dokunulmadı.

### 2026-07-08 (3) — ARAŞTIRMA (kod değişikliği YOK): büyük-frekans ML rejim-kapısı — ÇALIŞMIYOR (ML-XAU-RAPORU.md §4b)
- **Soru (kullanıcı):** daha büyük frekansta bir model MIDAS'ın işlem açıp açmamasına kapı olabilir mi
  (farklı model / ensemble serbest, önce 2026)?
- **Deney (`gate_midas.py`):** 3-model ensemble (logistic+RF+LightGBM), purged-CV, 2026. V1 = fx-günü
  kapısı, karar anchor+120dk (MATURE_MIN sayesinde ilk girişten önce biten kaçaksız ilk-2saat penceresi),
  etiket=günün R toplamı>0. V2 = işlem-anı ama YALNIZ yüksek-TF bağlam (2h/6h/24h ER, çok-saat getiri/
  aralık, vol rejimi) — sinyal-barı mikro özellikleri dışarıda.
- **Sonuç:** V1 131 gün OOF AUC **0.475** (yazı-tura altı; null 0.530), corr(p,günR)=−0.085, her eşik
  R kaybettiriyor; V2 AUC 0.531 ≈ gürültü, tüm eşikler AFTER-LOSS'tan kötü. Oracle tavanı +239R FX /
  +179R taker — var ama ulaşılamıyor.
- **Yorum:** 2026-07-07 rejim incelemesinin ML-teyidi: MIDAS'ın gün-tipi ex-ante öngörülemiyor; çalışan
  tek kapı (AFTER-LOSS) rejim değil gün-İÇİ dizi etkisi. Edge yapısı "her gün dene, trend gününde koş" —
  gün-kapısı arayışı yapıya ters. NO-SHIP, canlı dokunulmadı.

### 2026-07-08 (4) — ARAŞTIRMA (kod değişikliği YOK): bağımsız ML sinyal üretimi — tek pozitif TRIPLE-BARRIER LightGBM (ML-XAU-RAPORU.md §4c)
- **Soru (kullanıcı):** kapıyı bırak, ML doğrudan XAU sinyali üretsin; literatür ailelerini 2026'da değerlendir.
- **Düzenek (`ml_signal_xau.py`):** 15m barlar, aylık genişleyen walk-forward (OOS Mar-Tem), 1-gün purge,
  eşik=eğitim-kantili (q90/q97), denetlenmiş engine ekonomisi, random-giriş null bandı, çift maliyet.
  5 aile: TB-LGBM (AFML), FH-LGBM (klasik sabit-ufuk), TB-LOGIT, TB-MLP, SEQ-MLP ("LSTM diyeti") + ensemble.
- **Sonuç:** TEK pozitif = **TB-LGBM: OOS AUC 0.651 (aylık 0.57→0.72↑), q97 83tr +27.8R PF1.57 DD−10.3,
  taker +3.1, null −5±8R (~4σ)**; plato q93-q98 sağlıklı. FH etiketi AUC 0.510 (aynı model!) → etiket>model;
  SEQ-MLP 0.504 → "LSTM altın tahmini" ailesi 2026'da ampirik çürük; TB-LOGIT AUC 0.625 ama para kaybediyor
  (AUC≠para). Kâr Mayıs-yoğun (%77), short-taraf ağırlıklı; MIDAS ile 55/83 örtüşme ama günlük-R corr 0.247;
  Mar-Tem birleşik +129.7R vs MIDAS-yalnız +102.0R.
- **Karar:** ship-grade DEĞİL (tek yıl, 5 OOS ayı, Mayıs-yoğunluğu) ama ilk gerçek pozitif bağımsız ML sinyali.
  Sonraki kapı: PAXG 2024-25 çok-yıl OOS + SL/TP/H geometri platosu + canlı-paper izleme. Canlı dokunulmadı.

### 2026-07-08 (5) — ARAŞTIRMA (kod değişikliği YOK): STACKING — strateji sinyalleri ML-özelliği olarak — EK DEĞER YOK (ML-XAU-RAPORU.md §4d)
- **Soru (kullanıcı):** tüm XAU stratejilerini birleştirip sinyallerini ML ile harmanla + yeni özellikler ekle.
- **Deney (`stack_xau.py`):** 12 kural-strateji sinyali (MIDAS, TALOS-KELT075, Keltner-mid, EMA200/KAMA,
  Supertrend×2, Donchian, PDHL, Asya, PSAR, TSMOM) + 4 durum + 6 çapraz-varlık (XAG/BTC/SPY) özelliği,
  §4c harness'ında 4 set yarıştı.
- **Sonuç:** STRAT-only AUC **0.503** (giriş-anları bilgisiz); BASE+STRAT 0.644 ≈ BASE 0.640 ama q97
  ekonomisi SULANIYOR (+27.8→+11.1R, boyut laneti); çapraz-varlık gain %25 kapıyor ama OOS para üretmiyor.
  Piyasa-özellikli sade TB-LGBM en iyisi kalıyor.
- **Ders:** kural stratejilerinin edge'i ÇIKIŞ motorunda, giriş-anı bilgi içeriğinde değil (Donchian
  "exit is the lever" bulgusunun ML-aynası). Doğru birleştirme seviyesi PORTFÖY (düşük-korelasyonlu
  kitaplar: MIDAS+ML Mar-Tem +129.7R, corr 0.247), özellik-karışımı değil. Canlı dokunulmadı.

### 2026-07-08 (6) — ARAŞTIRMA (kod değişikliği YOK): trader-tipi confluence HİBRİT — MIDAS varyantına çöküyor, yeni kitap YOK (ML-XAU-RAPORU.md §4e)
- **Soru (kullanıcı):** ML'siz, trader'ların kompleks hibrit stratejilerinden bir sistem kur.
- **Deney (`scratchpad/fx_gold/hybrid_xau.py`):** 5-katman checklist (HTF hiza / VWAP trend / bölge:
  VWAP∪Keltner∪PDH-L / tetik mumu / hacim onayı) + seans disiplini, k-of-5 taraması, MIDAS trail
  motoru vs sabit-2R; ayrıca kırılım+retest klasiği. 2026 IS/OOS, çift maliyet.
- **Sonuç:** en iyi = tam checklist k5: 334tr +101.4R PF1.59 DD−15.3 her-ay-yeşil taker≈0 — ama
  MIDAS'la günlük-R corr **0.732** (256/334 örtüşme) ve MIDAS'tan az (+143.1'e karşı) → bağımsız
  kitap değil, süzülmüş MIDAS. Ablasyon: 5 katmandan yalnız C2-trend+C3-bölge bilgi taşıyor; tetik
  mumu ÇIKARINCA iyileşiyor (+117.3), HTF/hacim nötr. Sabit-2R her k'da trail'den kötü (çıkış
  dogması teyit). Kırılım-retest OOS −1.4 ölü.
- **Ders:** "confluence" ritüelinin çekirdeği trend+lokasyon = zaten MIDAS; ekstra katmanlar R kırpan
  dekor (entry-filtre taramasının 3. teyidi). Karmaşıklık ≠ edge. Canlı dokunulmadı.

### 2026-07-08 (7) — ui: Londra-penceresi bilgilendirmesi detaylandı (TR saati + kesin sınırlar)
- **Şikayet (kullanıcı):** canlı grafikte "seans uygun (07-13 UTC dışı)" — TR kullanıcısı için
  belirsiz (07-13 UTC = 10-16 TR); ardından kesin sınır gösterimi istendi (07:00 ≤ saat < 13:00).
- **Düzeltme (2 dosya, mantık değişmedi — filtre zaten UTC ile doğru):**
  - `adminStreamInfo.js` REAL_MIDAS_CONDS.sess + REAL_TALOS_CONDS.sess çipi →
    "seans uygun · Londra dışı (07:00 ≤ UTC < 13:00 · TR 10:00 ≤ saat < 16:00 · yalnız yeni giriş)".
  - `strategyInfo.js` MIDAS "Evren & saat" (tr+en) + TALOS "Giriş" (tr+en): kesin sınır anlambilimi
    (06:59 UTC kapanışlı bar sinyal verebilir, 13:00'ten itibaren açık), pencerenin yalnız YENİ
    girişi engellediği (açık pozisyon trailing ile koşar), backtest+canlının aynı signals()
    fonksiyonunu paylaştığı. Dist Render'da main'den derlenir.

### 2026-07-08 (8) — feat: TALOS-ICHI araştırma/PAPER akışı SHIP EDİLDİ (TALOS + Ichimoku Kumo yön filtresi)
- **İstek (kullanıcı):** "talosu direkt ichimoku ile live backtest cron paper account olarak güncelle;
  sadece TALOS olan stratejiyi research'e ekle; backtestde MIDAS kuralları (tek pozisyon) geçerli."
- **Ne:** yeni araştırma/paper akışı `talos_ichi` (public kod adı MENKAR). TALOS'un birebir aynısı
  (deep Keltner pullback + MIDAS motoru: 1.5×ATR stop, sabit hedef yok, 3.5×ATR trailing, 8h, seans-
  düz, tek pozisyon) + Ichimoku Kumo-rengi YÖN filtresi: LONG yalnız bulut yeşil (Senkou A>B), SHORT
  yalnız kırmızı. Senkou span +26 ileri kaydırık → bulut ≥26 bar geçmişten (lookahead yok).
- **Neden:** 2026-07-08 araştırması (bkz [[TALOS-Ichimoku]] hafıza + scratchpad/fx_gold/ichimoku_xau.py):
  Kumo filtresi TALOS'ta 3-yıl OOS'ta (XAU-2026 + PAXG-2024/25) avgR/WR/PF'i HER yıl yükseltti, 2024
  zararını yarıya indirdi (3-yıl +35.6R→+118.3R). MIDAS'ta AYNI filtre 2025'te tersine döndü → yalnız
  TALOS varyantı. Doğrulama (aynı taze veri): TALOS 325tr/+85.6R/PF1.51 → TALOS-ICHI 230tr/+111.7R/PF2.00.
- **Backend (yeni, sync/talos_ichi/):** strategy.py (TALOS'u import edip signals()'i Kumo ile süzer),
  backfill.py (version='talos_ichi', gece 01:50), canli.py (mode='talos_ichi' paper emit, +45s, Telegram+
  WebPush). Executor YOK — gerçek para YOK.
- **DB:** migration 015 uygulandı (user_signal_watch CHECK += 'talos_ichi', stream_universe +XAUUSDT).
  Backfill --apply ile 230 satır yazıldı (backtest DB).
- **UI (research/backtest bölümü, LIVE değil):** streamMask CODENAMES (MENKAR, LIVE_STREAM_KEYS'e
  EKLENMEDİ = admin/features.backtest-only), adminStreamInfo REAL_NAMES/LABELS/REAL_TALOS_ICHI_CONDS,
  strategyInfo talos_ichi kartı (tr+en), streamStats, Sidebar backtest GROUPS, TradeContext (3 dict +
  trailing kontrolleri), Dashboard/ChartModal isTrailing, MidasLiveChart isTalos (Keltner görselleri
  paylaşımlı; Kumo çipi backend-tarafı, canlı-grafik pill'i sonraki geliştirme). Prod build PASS.
- **Cron:** VM'e kuruldu (canli her dk +45s, backfill 01:50), log $HOME/ict-talos-ichi.log.
- **ÇEKİNCE:** tam ship bataryasından (Ichimoku periyot platosu 9/26/52, random-null, aylık) HENÜZ
  geçmedi → laboratuvar/paper varyantı, canlı ürün DEĞİL. Otorite kitap = gece backtest'i.

### 2026-07-08 (9) — TALOS-ICHI TAM DOĞRULAMA BATARYASINI GEÇTİ (paper/araştırma statüsü doğrulandı)
- **İstek (kullanıcı):** TALOS-ICHI'yi tam doğrula (+ TALOS'un paper'dan kaldırılmadığı teyidi: kaldırılmadı,
  ikisi ayrı akış olarak çalışıyor; son commit yalnız sync/talos_ichi/'ye dokundu).
- **Batarya (scratchpad/fx_gold/talos_ichi_validate.py), 4 test PASS:**
  1. **Periyot platosu düz** — tenkan 7-11 / kijun 22-30 / senkou_b 44-60 / shift 26-30 hepsi
     +84..+96R / PF ~2.0; varsayılan 9/26/52/26 platonun ortasında (knife-edge değil).
  2. **Random-drop null p=0.004** — gerçek Kumo +89.6R/avgR0.501/PF2.04, aynı sayıya (179/323) rastgele
     düşürme +48.4±16.7R/avgR0.270 → Kumo seçimi becerikli ~2.6σ (repo çıtası p<0.005 karşılandı).
  3. **2026 aylık 6/7 ay yeşil** (Tem kısmi −1 hariç).
  4. **Çok-yıl OOS her yıl avgR/WR/PF artar** (2024 −167.7→−61.1 PF0.55→0.66, 2025 +117.2→+89.7 avgR
     0.196→0.293, 2026 +86.1→+89.6 PF1.51→2.04). 2024 filtreliyken hâlâ net zarar (rejim kalkanı değil).
- **Sonuç:** TALOS-ICHI ship-grade doğrulamayı geçti — TALOS'un kendi 3-yıl'ından (+39R) daha ikna edici
  (+118R, her yıl kalite↑). Statü: DOĞRULANMIŞ paper/araştırma adayı. Canlı gerçek-paraya alma AYRI bir
  kullanıcı kararı (MIDAS-X gibi soru-cevapla). strategyInfo caveat (tr+en) "doğrulandı" olarak güncellendi.

### 2026-07-08 (10) — TALOS-ICHI CANLI PAPER'a alındı (TALOS'un yerine); canlı grafikte Ichimoku metriği
- **İstek (kullanıcı):** TALOS'u araştırma/backtest'e indir, TALOS-ICHI'yi onun yerine canlı paper yap,
  canlı sinyal metriklerini Ichimoku tarafı dahil canlı göster.
- **Üyelik takası (UI):** `streamMask.LIVE_STREAM_KEYS` talos→talos_ichi; Sidebar GROUPS: talos_ichi
  live'a (modes live+backtest, section live), talos backtest'e (modes backtest, section backtest).
  adminStreamInfo REAL_LABELS + strategyInfo caveat'ları (tr+en) güncellendi (talos_ichi=canlı PAPER,
  talos=backtest-only). talos_ichi HERKESE görünür canlı akış oldu; talos admin/features.backtest-only.
- **Cron:** TALOS canlı emit EMEKLİ (dag/crontab'ta '#'lendi, geri-alma notu; nightly backfill 01:40
  DEVAM). TALOS-ICHI canlı emit (+45s) zaten aktifti — canlı akış artık o.
- **Canlı grafikte Ichimoku (MidasLiveChart.jsx):** talos_ichi için `kumo15()` (15m Senkou A/B, +26
  ileri kaydırık, no-lookahead) eklendi; `computeTalos(candles, km)` Kumo geçidi alır (long→bulut yeşil
  A>B, short→kırmızı A<B); marker'lar + SİNYAL KOŞULLARI checklist'ine Kumo çipi (kumoLong/kumoShort)
  + header'a canlı "Kumo 🟢yeşil/🔴kırmızı" göstergesi. useStreamDisplay.talosIchiConds() +
  adminStreamInfo.REAL_TALOS_ICHI_CONDS (admin gerçek metin, diğerleri nötr "Koşul F"). Prod build PASS.
- **DOKUNULMADI:** backend strateji/backfill/canli (talos & talos_ichi) — yalnız üyelik/cron/grafik.
  TALOS-ICHI hâlâ PAPER (executor YOK); canlı gerçek-para ayrı karar.

### 2026-07-08 (11) — ui: TALOS-ICHI canlı grafiğe Ichimoku bulut çizgileri (Senkou A/B) + aç-kapa toggle
- **İstek (kullanıcı):** canlı grafiğe Ichimoku çizgilerini aç-kapa şekilde ekle; yalnız ilgili çizgiler.
- **Ne (MidasLiveChart.jsx):** talos_ichi için grafiğe 2 çizgi serisi — Senkou A (yeşil) + Senkou B
  (kırmızı) = Kumo filtresinin baktığı bulut sınırları (ilgili çizgiler; Tenkan/Kijun/Chikou çizilmez).
  computeTalos km varken kumoAData/kumoBData döndürür (15m span'lar +26 ileri, no-lookahead). Seriler
  gizli oluşturulur; header'daki "☁️ Kumo çizgileri açık/kapalı" butonu görünürlüğü toggle'lar (ayrı
  useEffect, data-load effect'ini tetiklemeden — 30s poll'a dokunmaz). Yalnız talos_ichi'de görünür.
  Backend/strateji dokunulmadı. Prod build PASS.

### 2026-07-08 (12) — fix: TALOS-ICHI canlı grafiğinde Kumo çizgileri boştu → warmup geçmiş verisi eklendi
- **Şikayet (kullanıcı):** "açınca görünmüyor" — Ichimoku çizgileri toggle açılınca çıkmıyor.
- **Kök neden:** canlı grafik fx-seans açılışından veri çekiyordu; Ichimoku Kumo ~20h 15m geçmişi
  (52+26 bucket) ister → seans yeniyse yeterli bucket yok → Senkou span NaN → kumoAData boş → çizgi yok.
- **Düzeltme (MidasLiveChart.jsx):** Keltner/Ichimoku ROLLING gösterge (seans-anchored değil); talos_ichi
  için anchor = end−2.5gün warmup (talos için 1gün), görünür pencere yine son ~4h (fazlası sola kaydırılır).
  Static (backtest-günü) için warmup sola yüklenir, görünür aralık yalnız istenen gün (setVisibleRange).
  MIDAS anchor (VWAP seans) dokunulmadı. Böylece çizgiler ilk görünür bardan itibaren dolu, sonra canlı
  devam eder. Prod build PASS.

### 2026-07-08 (13) — 🔴 TALOS-ICHI-X MAINNET GERÇEK PARA (MIDAS-X'in yerine); MIDAS paper'a indi
- **Kullanıcı kararı (soru-cevap teyitli):** OPUS + TALOS-ICHI canlı gerçek-para; MIDAS paper'a. TALOS-ICHI
  arming=direkt mainnet, risk=$3 (MIDAS-X'ten devir), MIDAS-X=pozisyon varsa kapat + paper'a devam.
- **Neden TALOS-ICHI mainnet'e uygun:** tam doğrulama bataryasını geçti (plato+null p=0.004+aylık+çok-yıl);
  Binance taker'da MIDAS'tan dayanıklı (2026 taker +46R vs MIDAS +23R). Kritik kısıt: Binance hesap-başına
  tek net XAUUSDT pozisyonu → iki gold executor çakışır → MIDAS-X ÖNCE emekli edilmeli.
- **MIDAS-X emekli:** açık pozisyon YOK (DB 0, borsa XAUUSDT flat, kapatılacak şey yok — uPnL OPUS'tandı).
  `.env` MIDAS_EXEC_ENABLED=false, owner (midas,mainnet) row enabled=false, cron 2 satır '#'lendi. MIDAS
  PAPER feed (canli +20s, backfill 01:30) DEVAM. TALOS-X (testnet) da disable + cron emekli.
- **TALOS-ICHI-X kuruldu (`sync/talos_ichi_exec/`):** talos_exec'ten klon; mode='talos_ichi', strateji
  sync/talos_ichi, env TALOS_ICHI_*, tablolar talos_ichi_positions/orders, coid tix-, version talos_ichix,
  isim TALOS-ICHI-X. MIDAS-X'in birebir kardeşi (maker GTX+60sn taker fallback, oto-kaldıraç ≤25x, borsa-
  tarafı STOP_MARKET cancel/replace iz-süren stop, killswitch/safety_sweep/parity_report).
- **DB:** migration 016 (user_stream_settings CHECK += talos_ichi, MAINNET kilidi YOK, owner (talos_ichi,
  mainnet,$3) satırı), schema.sql (talos_ichi tabloları), store.py _POS_TABLES += talos_ichi. Uygulandı.
- **Doğrulama:** parity_report PASS (18 işlem, 0 uyuşmazlık — track_open == backtest); dry-run temiz;
  ARMED header doğru (MAINNET/$3/20x/maker); safety_sweep 0 breach. after_loss_only=**false** (doğrulanan
  tam kitap; after-loss MIDAS'a özgü, TALOS-ICHI için test edilmedi).
- **Cron:** TALOS-ICHI-X executor +48s, safety_sweep +58s (VM'e kuruldu). Log ict-talos-ichi-exec.log.
- ⚠️ FX-maliyet modeli: çok-yıl taker OOS negatif (2026-rejim riski); $3 küçük risk, kitabı izle. `.env`
  commit edilmez (gitignored). Geri-alma: MIDAS.md/crontab yorumlarında.

### 2026-07-08 (14) — ui: gerçek-para rozetleri güncellendi (TALOS-ICHI = Binance canlı altın; MIDAS = paper)
- **İstek (kullanıcı):** takas sonrası bayat rozetleri güncelle (Binance gerçek-para / VWAP / MIDAS).
- **Değişenler:** streams.js STREAM_ROWS: gerçek-para gold satırı midas→talos_ichi (MIDAS executor'suz,
  aktivasyon tablosundan düştü). strategyInfo caveat'ları: MIDAS "🔵 PAPER (MIDAS-X emekli)", talos_ichi
  "🔴 MAINNET GERÇEK PARA (MIDAS-X'in yerine, $3)". /binance-altin canlı board (MidasXLivePage) +
  LivePositionsPage: pozisyon tablosu midas_positions→talos_ichi_positions, paper mode midas→talos_ichi.
- **Güvenlik:** talos_ichi_positions'a RLS + `ti_select_own` policy eklendi (user_id=auth.uid() OR admin) —
  eksikti (RLS=False), multi-user'da tüm satırları sızdırırdı; schema.sql'e kalıcı + DB'ye uygulandı.
- Prod build PASS. Canlı gerçek-para board artık TALOS-ICHI-X pozisyonlarını gösterir.

### 2026-07-08 (15) — TALOS-ICHI-X kaçan işlem post-mortem #2: GTX cross → taker eskalasyonu + fallback penceresi (pos#1)
- **Şikayet (kullanıcı):** TALOS-ICHI sinyali fill olmadı.
- **Teşhis (loglar + DB):** pos#1 XAUUSDT LONG (`signal_time` 14:08, `signal_entry` 4067.48, kayıt
  14:09:50.33) → `state=CANCELLED`, `exit_reason='unfilled'` @ 14:11:50.71. Kritik kanıt:
  **`entry_coid` ve `entry_order_id` NULL** — borsada hiçbir zaman emir DURMADI. "Dolmadı" değil,
  "hiç gönderilemedi". İki bağımsız kusur üst üste bindi:
- **Kusur 1 — GTX alış limiti ask'in üstünde, maker olamaz.** Sinyal barı kapanışı (14:08 C=4067.47)
  ile executor'ün ilk tick'i (14:09:50) arasında fiyat aşağı kaydı (14:09 C=4066.32). 4067.48'e
  post-only BUY = ask üstünde limit → anında eşleşir → Binance `-2010` → red. `_place_entry` bunu
  yakalayıp `retry next tick` yazıp dönüyordu ve sonraki tick **aynı fiyatı** deniyordu →
  deterministik no-op döngü. Keltner alt-bant pullback LONG'unda bu istisna DEĞİL, normal hal:
  sinyal fiyat banda düşerken doğar, dolayısıyla execution anında ask genelde bar kapanışının
  altındadır. Maker bacağı ancak fiyat sinyalin TERSİNE gitmişse kabul edilir — 07-02 maker
  araştırmasının ve pos#47'nin aynı ters-seçilim tuzağı, bu kez red tarafından.
- **Kusur 2 — maker→taker fallback penceresine sıfır tick düştü.** `entry_timeout_sec`=120,
  `entry_taker_fallback_sec`=60, cron periyodu 60 sn — üçü de aynı saniyeye faz-kilitli (`sleep 48`).
  Pencere `[created+60, deadline]` = `[14:10:50.256, 14:11:50.256]`; 14:10 tick'i ~14:10:49.9'da
  (erken), 14:11 tick'i 14:11:50.714'te (deadline'ı geçmiş) koştu. Nominal 60 sn'lik pencerenin içine
  hiç tick düşmedi; sonucu ~0.5 sn cron jitter'ı belirledi. Üstelik `expired` kontrolü fallback
  bloğundan ÖNCE çalıştığı için geç gelen tick fallback yerine iptali seçti. Fiyat hiçbir an tolerans
  dışına çıkmamıştı (`slip` = −1.18, LEHTE; `exit_reason` da `slipped` değil `unfilled`) — yani
  fallback tetiklenmeli ve ~4064.7'den market girmeliydi.
- **Düzeltme 1 (executor.py `_place_entry`):** `-2010/-5022` reddi artık `retry` değil **taker
  eskalasyonu**. Red, kitabın zaten `signal_entry`'den iyi-veya-eşit olduğunu KANITLAR (LONG'da ask ≤
  entry). GTX ancak fiyat sinyal aleyhine dönerse dinlenebilir, aynı fiyatı yeniden göndermek no-op.
  `_manage_entry`'nin `slipped` guard'ı fiyatın toleransta olduğunu zaten tesis etmiş ve burada LEHTE
  tarafta — al. `ctx.taker_fallback` işaretlenir (idempotent, tek atış), `talos_ichi_orders`'a
  `action='reject'` forensic satırı + Telegram uyarısı yazılır, MARKET gönderilir. `taker=True`
  yolunda `-2010` (ör. yetersiz teminat) genel hata dalına düşer → sonsuz özyineleme yok.
- **Düzeltme 2 (executor.py `_manage_entry`):** sıralama `slipped → fallback → expired` oldu (eski:
  `slipped|expired → fallback`). Tolerans dışına kaçan fiyat saatten bağımsız hâlâ iptal edilir
  (kovalamak +0.5R sinyali −0.5R'a çevirir); ama fiyat toleranstayken geç gelen tick artık işlemi
  DÜŞÜRMEZ, alır. Fallback ateşlendikten sonra deadline taker bacağını da sınırlar (MARKET dönmezse
  bir sonraki tick `unfilled` iptal eder) → sınırsız değil.
- **Düzeltme 3 (config.py):** `TALOS_ICHI_ENTRY_TAKER_FALLBACK_SEC` varsayılanı 60 → **45 sn**. Bu
  değer bir cron periyodu (60 sn) ile `entry_timeout_sec` (120 sn) arasında, İKİ tarafta da marjla
  durmalı; 45 sn t+60 tick'ine ~15 sn slack verir. Yorum satırına gerekçe yazıldı.
- **Gözlenebilirlik:** giriş iptalleri (`slipped`/`unfilled`) ortak `_abandon_entry` yardımcısına
  çıkarıldı ve artık `talos_ichi_orders`'a `action='cancel'` forensic satırı yazıyor. Önceden `-2010`
  reddi HİÇBİR yere yazılmıyordu (ne DB ne Telegram) — bu yüzden olay 30 dk sessiz kaldı.
- **Doğrulama:** pos#1'i birebir canlandıran 7 senaryoluk hedefli test (stub Binance client):
  (1) pos#1 replay → GTX red → MARKET fill @4064.70 (sinyalden İYİ); (2) eski pencerede kaybolan
  t+59.6 sn tick'i → fallback ateşler; (3) deadline'ı 0.4 sn geçen tick → iptal değil fallback;
  (4) fiyat kaçtı (>0.25R) → hâlâ `slipped` iptal; (5) fallback ateşlemiş + MARKET dönmemiş →
  deadline `unfilled` iptal (sınırlı); (6) GTX kabul (fiyat aleyhte) → dinlenir, eskalasyon yok;
  (7) dinlenen GTX dolar → `_enter_open`, MARKET yok. 7/7 PASS. Ayrıca executor tam yolu koşturuldu.
- **Bu olayın parası:** paper işlem −1.03R kapandı, yani bu kaçırma ~$3 KAZANDIRDI. Mekanizma
  yön-kör olduğu için kazananları da aynı şekilde kaçırırdı — düzeltme yine de doğru.
- **⚠️ Açık bulgu (düzeltilmedi, ayrı karar):** dört executor'ün de config'i
  `env = {**os.environ, **tsc._read_env()}` yapıyor (`live_exec`, `midas_exec`, `talos_exec`,
  `talos_ichi_exec`) — yorum "process env for cron overrides" dese de **`.env` process env'i EZİYOR**.
  `.env`'de `TALOS_ICHI_EXEC_DRY_RUN=false` olduğu için executor.py docstring'inde BELGELENEN
  `TALOS_ICHI_EXEC_DRY_RUN=true python sync/talos_ichi_exec/executor.py` komutu gerçek parayla ARMED
  koşuyor. Gerçek-para köprüsünde ayak-silahı; `.env` düzenlemeden shell'den dry-run mümkün değil.
- **Not:** `midas_exec` ve `talos_exec` aynı 60 sn faz-kilitli pencere hatasını taşımaya devam ediyor
  (ikisi de cron'da EMEKLİ/yorumlu, gerçek para akmıyor). Yeniden armanmadan önce bu commit'teki
  `_manage_entry` sıralaması + 45 sn varsayılan oraya da taşınmalı.

### 2026-07-08 (15) — 🔴 POST-MORTEM pos#13: OPUS'un sweep'i TALOS-ICHI-X'in CANLI altın SHORT'unu kapattı
- **Şikayet (kullanıcı):** "açılan altın işlemini neden kapattın". Telegram: `✅ GİRİŞ XAUUSDT SHORT #13`
  → `🚨 XAUUSDT ORPHAN flattened (-0.163)` → `⚠️ exec hata: Object of type Decimal is not JSON serializable`.
- **Olay:** 17:02:06 SELL 0.163 @4063.75 (maker, SL 4082.12 borsada). 17:05:54 BUY 0.163 @4064.34 (taker)
  → pozisyon MARKET'ten kapatıldı. Gerçekleşen: rPnL −$0.096 + komisyon $0.265 ≈ **−$0.36**. Stop hiç
  tetiklenmedi (4082'deydi); executor'ın kendi flatten emri yok (sadece entry+sl legs).
- **KÖK NEDEN 1 — çapraz-executor flatten (asıl suçlu):** `sync/live_exec/safety_sweep.py` (OPUS, cron
  `*/5 +50s` → 17:05:50 ✓) borsadaki HER pozisyonu kendi `live_positions` tablosunda arıyordu; sembol
  kapsamı YOKTU. Altın artık `talos_ichi_positions`'ta olduğu için XAUUSDT "ORPHAN" görünüp market'ten
  kapatıldı. Hesap OPUS ile paylaşımlı; bu mayın MIDAS-X döneminde de patlamış (`ict-exec.log`:
  `ORPHAN XAUUSDT amt=0.537`) ama fark edilmemiş — MIDAS-X'in mainnet pozisyonu 5-dk sweep'e denk gelmemiş.
  **Düzeltme:** orphan döngüsüne `if sym not in cfg.symbols: continue` (EXEC_ENABLED_SYMBOLS). OPUS artık
  yalnız kendi sembollerini yargılar; başka executor'ün pozisyonuna DOKUNMAZ. Doğrulandı (breaches=0).
- **KÖK NEDEN 2 — writeback çöküyordu:** `state.writeback_trading_signals` context'ine `exit_px`/`pnl_r`
  DB'den **Decimal** olarak giriyordu; `Json()→json.dumps` serialize edemeyip tick'i öldürüyordu.
  `float()` cast eklendi (talos_ichi_exec + latent aynı bug olan midas_exec/talos_exec).
- **KÖK NEDEN 3 — version taşması:** `trading_signals.version` **varchar(10)**, `talos_ichix` 11 karakter →
  writeback her seferinde `StringDataRightTruncation`. Exec tag `talos_ichix` → **`tichix`** (config+state,
  mevcut 2 pozisyon satırı güncellendi). Paper `talos_ichi` tam 10, etkilenmedi.
- **Telafi:** pos#13 düzeltilmiş kodla `trading_signals` (version='tichix') tablosuna yazıldı. Her iki
  executor de temiz koşuyor. **Ders: paylaşımlı Binance hesabında her sweep KENDİ sembol evreniyle sınırlı olmalı.**

### 2026-07-08 (16) — pos#13 telafisi (elle yeniden giriş, pos#22) + kaldıraç cap 25→75 (marj $42→$14)
- **Telafi (sahip isteği "bu seferlik aynı setuptan anlık fiyattan aç"):** pos#13 OPUS-sweep bug'ıyla haksız
  kapatıldığı için AYNI setup'tan (SL 4082.12) anlık fiyata yeniden girildi. Elle emir yazılmadı — `ict_trade.signals`'a
  `mode='talos_ichi'` bir satır yazılıp (context: `manual_reentry:true` + gerekçe) executor'ın KENDİ yolundan
  alındı (boyutlandırma/kaldıraç/borsa-tarafı stop/trailing/writeback hepsi test edilmiş kod).
  Sonuç **pos#22**: SHORT 0.259 @ 4070.98, SL 4082.12 (1R=11.56), 75x. Entry legs: `reject`(GTX −2010) →
  `place`(MARKET) — yani 0cd3733 taker-eskalasyon düzeltmesi CANLIDA çalıştı. Koruyucu STOP_MARKET borsada
  (`openAlgoOrders`, closePosition=true, algoId 1000002434045256; `openOrders`'ta GÖRÜNMEZ — algo emri).
- **OPUS sweep düzeltmesi canlı doğrulandı:** açık altın pozisyonuyla `skip XAUUSDT (outside OPUS universe —
  other executor owns it)` · breaches=0. Artık kardeş executor'ün pozisyonuna dokunmuyor.
- **HEDEF-MARJ KALDIRAÇ (sahip isteği: "SL noktasına göre $3 zarar, $10-20 marj"):** `TALOS_ICHI_TARGET_MARGIN_USD=15`
  eklendi (config+executor); `LEVERAGE_MAX` 25→100 (artık borsa tavanı, belirleyici hedef-marj).
  - **Kayıp SL'de KALDIRAÇTAN BAĞIMSIZ:** `qty = risk_usd/|giriş−SL|` ⇒ stop yerse kayıp = $3, her zaman.
    Kaldıraç yalnız MARJI ve likidasyon mesafesini belirler.
  - `notional = risk/slpct` (stop mesafesi sabitler) ⇒ `marj = notional/L` ⇒ **`L = notional/hedef_marj`**.
  - Değişmez: **liq yastığı = hedef_marj/risk = 5× SL mesafesi**, stop genişliğinden bağımsız.
  - Güvenlik sınırı korundu: `L ≤ floor(0.5/slpct)` (liq ≥ 2× SL) — `hedef_marj > 2·risk` iken zaten sağlanır,
    yalnız yanlış-konfigürasyona karşı bekçi. Simülasyon (SL% 0.27/0.5/1/2): marj $15.0, kayıp $3.00, liq 5.0× ✓.
  - **OPUS'un `LEVERAGE_MAX=25`'i ayrı anahtar, dokunulmadı.**
- ⚠️ ISOLATED'da açık pozisyonun kaldıracını değiştirmek tahsisli marjı GERİ ÇEKMEZ (pos#22 `isolatedMargin`
  $40.92, liq 4211 — 25x'te açıldığı için). Zorla çekmek liq'i stopa yaklaştıracağı ve sahip yalnız YENİ
  işlemler için istediği için **dokunulmadı**; kapanınca serbest kalır. Kural yalnız yeni girişlerde
  (giriş öncesi `set_leverage`). Serbest bakiye $55.7, OPUS kısıtlanmıyor.

### 2026-07-08 (17) — canlı XAU pozisyonu açıkken paper feed SUSAR (yeni emit yok, Telegram/push yok)
- **İstek (sahip):** "aktif XAU işlemi varsa TALOS yeni işlem almasın, kapanmasını beklesin, Telegram'a ve
  app'e bildirim atmasın."
- **Sorun:** `sync/talos_ichi/canli.py` yalnız KENDİ paper sinyal tablosuna bakıyordu. Paper trailing replay'i
  (dolum/kayma farkı yüzünden) işlemi gerçek pozisyondan ÖNCE kapalı sayabilir → yeni setup yayınlar,
  formation Telegram+WebPush atar, oysa executor `max_concurrent=1` ile o işlemi zaten alamaz. Ayrıca açık
  işlemde paper tracker ile executor AYNI trailing/çıkış için ÇİFT Telegram atıyordu.
- **Düzeltme (`canli.py`):** (1) `has_open` kapısına `ict_trade.talos_ichi_positions` (state ∈ PENDING_ENTRY/
  ENTRY_WORKING/OPEN) kontrolü eklendi → gerçek pozisyon açıkken **hiç emit yok** ⇒ formation Telegram/push
  da yok. (2) Tracker `no_telegram = args.no_telegram OR exec_open` ile çağrılıyor: paper trailing durumu
  (context/pos) güncellenmeye devam eder ama SESSİZ — açık gerçek işlemin tek yetkili bildiricisi
  TALOS-ICHI-X executor'dur. Tablo yoksa fail-safe (rollback, paper feed kırılmaz).
- **Doğrulama (pos#22 açıkken):** canli → `IN POSITION · EXEC POSITION OPEN (canlı işlem açık — bildirim yok)`,
  `0 fresh setup · 0 formation-alert · 0 SL-update · 0 exit`. Executor kendi trailing takibini sürdürüyor.

### 2026-07-08 (17) — MIDAS-X TESTNET/PAPER'da yeniden açıldı + pos#1 giriş düzeltmesi midas_exec'e taşındı
- **İstek (kullanıcı):** "paper account'ta çalışsın midas".
- **Durum tespiti:** MIDAS sinyali aslında paper FEED'de işleniyordu (17:31 SHORT emit → `mode='midas'`,
  `pos='open'`, trailing takip, Telegram). İşlenmeyen şey Binance emriydi: MIDAS-X sabah emekli
  edilmişti (cron yorumlu, `MIDAS_EXEC_ENABLED=false`, owner satırı `enabled=false`) — `midas_positions`'ın
  en yeni satırı 01:12'deki #47. MIDAS'ın "PAPER"ı bir Binance hesabı değil, salt-DB simülasyondu.
- **Yapılan (paper = TESTNET):** `.env` `MIDAS_EXEC_ENABLED=true` + **`MIDAS_BINANCE_TESTNET=true`** +
  `MIDAS_EXEC_DRY_RUN=false` (yedek `~/env.backup.pre-midas-paper-20260708-174713`);
  `user_stream_settings` midas/**testnet** `enabled=true` (midas/**mainnet** `enabled=false` KALDI);
  `dag/crontab` midas_exec iki satırı yorumdan çıkarıldı + `crontab dag/crontab`
  (yedek `~/crontab.backup.pre-midas-paper-*`). Doğrulama sırası: önce `MIDAS_EXEC_DRY_RUN=true` ile tek
  el koşuldu (`DRY-RUN (no orders) | testnet`, testnet anahtarı çözüldü, `XAUUSDT tradable=True`,
  risk $5 satırdan) → sonra arm. Canlı tick `ARMED (LIVE ORDERS) | testnet`, sweep `swept 0 | breaches=0`.
- **Neden testnet gerçekten güvenli:** `cfg_for_user` ağı satırdan alır (`u.network`) ve anahtarlar
  network-özel + çapraz-fallback YOK (strict separation). Testnet MIDAS-X, mainnet TALOS-ICHI-X'in
  altınını GÖREMEZ → tek-executor/sembol kuralı bozulmaz. Doğrulandı: `talos_ichi_positions` #22 SHORT
  açık kaldı, trailing SL ratchet'i sürdü, kendi sweep'i `swept 1 managed`.
- **⚠️ Mainnet'e almak için `MIDAS_BINANCE_TESTNET=false` YETMEZ:** o an XAUUSDT'de İKİ executor olur ve
  iki sweep birbirinin pozisyonunu ORPHAN sanıp market'ten kapatır (bugünün `6e4a201` post-mortem'i).
  Önce TALOS-ICHI-X durdurulmalı. Crontab yorumuna da yazıldı.
- **Kod: pos#1 giriş düzeltmesi midas_exec'e PORT EDİLDİ** (`0cd3733`'ün birebir eşi). Aksi halde paper
  hesap tam olarak aynı "sinyal fill olmadı" arızasını üretirdi — `midas_exec/executor.py` düzeltme
  öncesi `talos_ichi_exec` ile satır satır aynıydı. Üç değişiklik: (1) `-2010/-5022` post-only cross →
  `retry next tick` yerine **taker eskalasyonu** (red, kitabın `signal_entry`'den iyi-veya-eşit olduğunu
  kanıtlar; GTX ancak fiyat sinyal aleyhine dönerse dinlenebilir); (2) `_manage_entry` sıralaması
  `slipped → fallback → expired` (60 sn faz-kilitli pencereye sıfır tick düşmesi sorunu); (3)
  `MIDAS_ENTRY_TAKER_FALLBACK_SEC` varsayılanı 60 → **45 sn**. Ortak `_abandon_entry` yardımcısı
  `midas_orders`'a `action='cancel'`, red ise `action='reject'` forensic satırı + Telegram yazar.
- **Doğrulama:** aynı 7 senaryoluk stub-client testi midas_exec üzerinde **7/7 PASS** (pos#1 replay →
  MARKET @4064.70; kayıp t+59.6sn tick'i → fallback; deadline+0.4sn → iptal değil fallback; slipped →
  iptal; fallback sonrası deadline → iptal; GTX kabul → dinlenir; GTX dolar → `_enter_open`).
- **Not:** açık paper SHORT (17:31) AYNALANMADI — 15 dk'lık `NEW_SIGNAL_LOOKBACK_MIN` tazelik penceresinin
  dışında kalmıştı (`0 recent midas signal(s)`). MIDAS-X bir sonraki sinyalden itibaren işler; açık
  işleme ortadan girmek paper/live pariteyi bozardı. `MIDAS_EXEC_AFTER_LOSS_ONLY=true` de AÇIK kaldı —
  fx-gününün ilk sinyalini tasarım gereği atlar. `talos_exec` hâlâ eski (60 sn) pencereyi taşır; cron'da
  emekli, yeniden armanmadan önce port edilmeli.

### 2026-07-13 — ⛔ MIDAS EMEKLİ: backtest-only'ye indi (canlı emit + MIDAS-X executor KAPATILDI)

**Sahip kararı:** "MIDAS'ı backtest tarafına taşıyalım, paper account'a da canlı işlem açmayalım. Canlıda
şu an OPUS ve TALOS-ICHI çalışsın."

**Emeklilik öncesi güvenlik kontrolü (kapatmadan ÖNCE yapıldı):**
- DB `midas_positions`: 13 CLOSED + 4 CANCELLED → **açık/bekleyen pozisyon YOK**.
- Testnet borsa (`position_risk` + `open_orders`, XAUUSDT): **0 açık pozisyon · 0 bekleyen emir**.
- Yani sahipsiz bırakılan emir/pozisyon yok; kapatma güvenli.

**Kapatılanlar (savunma katmanları — üçü birden):**
1. **Cron** (3 satır yorumlandı): `midas/canli.py --emit` (paper sinyal emit + trailing track),
   `midas_exec/executor.py`, `midas_exec/safety_sweep.py`. Geri alma talimatı crontab'da yazılı.
2. **`.env`**: `MIDAS_EXEC_ENABLED=false` + `MIDAS_EXEC_DRY_RUN=true` (fail-closed).
3. **DB**: `user_stream_settings` (midas, testnet) `enabled=false`. Ayrıca tutarlılık için
   (talos, testnet) da `enabled=false` — TALOS-X'in cron'u zaten yorumluydu ama DB satırı açık kalmıştı
   (latent tuzak: cron geri açılsa TALOS-X silahlanırdı). `talos_positions` BOŞ, güvenli.

**Doğrulama:** `sync/midas_exec/executor.py` elle koşturulduğunda banner artık `DRY-RUN (no orders)` +
`0 exec user-network row(s) loaded` → hem .env hem DB kapısı kapalı, emir açması imkânsız.
(Bkz. bilinen tuzak: `.env` process env'i EZER, banner tek güvenilir kaynaktır.)

**DEVAM EDEN:** gece backfill'i `30 1 * * * sync/midas/backfill.py --apply` (version='midas') —
kitap her gece tazelenir, MIDAS Dashboard'da araştırma/backtest akışı olarak yaşamaya devam eder.
Sadece **hiçbir işlem açılmaz** (paper dahil).

**UI:** `streamMask.js` `LIVE_STREAM_KEYS` = `['d30so8f3h7', 'talos_ichi']` (midas çıkarıldı → artık
`isResearchStream`, yani yalnız admin'e / `user_features.backtest=true` olan kullanıcıya görünür).
`adminStreamInfo.js` etiketi + `strategyInfo.js` MIDAS kartının caveat'ı güncellendi (tr+en).

**Gerekçe (kayda geçsin):** MIDAS'ın çok-yıl OOS'u zaten breakeven/negatifti ve FX-maliyet modeli
($0.50/oz) Binance taker'da (~$4/oz) çöküyordu — yani gerçek-para yolu kapalıydı. Paper executor'ün
tek işlevi altyapı doğrulamasıydı; o iş bitti (TALOS-ICHI-X aynı köprüyü mainnet'te koşuyor).

**CANLI SET ARTIK: OPUS (kripto, gerçek para) + TALOS-ICHI-X (altın, gerçek para). Başka hiçbir şey.**

**Geri alma:** crontab'daki 3 satırın `# ` işaretini kaldır + `.env` `MIDAS_EXEC_ENABLED=true` /
`MIDAS_EXEC_DRY_RUN=false` + `user_stream_settings` (midas,testnet) `enabled=true` + `streamMask.js`
`LIVE_STREAM_KEYS`'e `'midas'` geri ekle.

<!-- NEXT ENTRY GOES ABOVE THIS LINE -->
```
### YYYY-MM-DD — <summary> (commit <hash>)
- <what changed>
```
