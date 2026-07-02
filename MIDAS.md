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

<!-- NEXT ENTRY GOES ABOVE THIS LINE -->
```
### YYYY-MM-DD — <summary> (commit <hash>)
- <what changed>
```
