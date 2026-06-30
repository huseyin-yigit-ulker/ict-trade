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
(~10 bps ≈ $4/oz) it turns **negative**. MIDAS is therefore a **PAPER** stream (signals + Telegram +
dashboard), NOT a real-money Binance stream. The real-money executor trades only OPUS (d30so8f3h7).

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
| `strategy.py` | Core. Data load + FX-gold market-hours filter, anchored VWAP, ATR(15m), `signals()` (VWAP-pullback + London 07-13 UTC skip), `walk()` (leak-free single-position backtest with 3.5×ATR trailing), `generate_trades()`, `track_open()` (live trailing replay for one open position), `current_open()` (self-heal). All tuned constants live at the top (`SLOPE_N`, `ATR_INIT_MULT`, `TRAIL_MULT`, `MAX_HOLD_MIN`, `COST_RT`, `SKIP_UTC_START/END`). |
| `backfill.py` | Nightly: replays 2026, writes **SETTLED-only** trades to `trading_signals` (`version='midas'`), stores the trailing-stop path in `context.trail`. `--dry-run` / `--apply`. |
| `canli.py` | Per-minute live: emits fresh setups + tracks the open position → `signals` (`mode='midas'`); Telegram on entry / **every trailing-stop change** (`--sl-step 0`) / exit. `--dry-run` / `--emit`, `--sl-step N`, `--no-telegram`, `--lookback-min N`. |

Shared engine helpers reused from `sync/trade_sync_common.py` (DB connections, `fetch_klines`, `build_row`) and `backtest/ict/data.py` (Binance klines).

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
The VM crontab (applied with `crontab dag/crontab`). MIDAS lines: per-minute `canli.py --emit` and nightly `backfill.py --apply` at 01:30 UTC.

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

**NOT used by MIDAS** (they drive the OPUS real-money Binance executor — leave as-is / unset for a MIDAS-only
box): `BINANCE_TESTNET*`, `LIVE_TRADING_ENABLED`, `EXEC_*`, `LEVERAGE*`, `MARGIN_TYPE`, `RISK_PER_TRADE_USD`,
`MAX_*`, `AUTO_LEVERAGE`, `CLOSE_FRAC`, `HORIZON_DAYS`, `RUNNER_CAP_R`, `DCH_*`, `LIVE_ENTRY_MODE`.

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
`MAX_HOLD_MIN=480` (8h), `TOUCH_TOL=0.25`, `COST_RT=0.50` ($/oz), `SKIP_UTC_START=7 / END=13` (London skip).
Sessions traded: Asia 22-07, London-NY overlap 13-17, NY 17-21 UTC; **London 07-13 UTC skipped**; flat Fri
16:00 ET (weekend buffer); never holds the weekend.

**DB row shapes:**
- Backtest `trading_signals`: one row/trade, `version='midas'`, `context={kind,init_sl,trail:[[unix_sec,price],…]}`.
- Live `signals`: `mode='midas'`, `context={pos:'open'|'closed', cur_sl, best, locked_r, trail, init_sl, …}`.

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

<!-- NEXT ENTRY GOES ABOVE THIS LINE -->
```
### YYYY-MM-DD — <summary> (commit <hash>)
- <what changed>
```
