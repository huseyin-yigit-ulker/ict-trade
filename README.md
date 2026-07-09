<div align="center">

# 🎯 PUSU — Liquidity Ambush Intelligence

**A production quantitative trading system: backtest research → live signals → real-money execution.**

Crypto & FX/Gold strategies, replayed on Binance 1-minute data, emitted live every bar, and — for the two that survived out-of-sample — traded with **real money** on Binance Futures. Multi-user, RLS-secured, Telegram + phone-push alerts, and a React dashboard with Year→Month→Day backtest drill-down.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![Vite](https://img.shields.io/badge/Vite-build-646CFF?logo=vite&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-Postgres%20%2B%20RLS-3ECF8E?logo=supabase&logoColor=white)
![Binance](https://img.shields.io/badge/Binance-Futures%20API-F0B90B?logo=binance&logoColor=black)
![Status](https://img.shields.io/badge/status-live%20(real%20money)-c0392b)

</div>

---

## ⚡ At a glance

| | |
|---|---|
| 🗓️ **Timeline** | 436 commits over ~5 months (Feb 2026 → live today) |
| 🐍 **Engine** | 187 Python files — backtest engines, ICT detectors, live emitters, executors |
| 🖥️ **Dashboard** | React + Vite, 42 components, TR/EN, live feed + backtest drill-down + TradingView charts |
| 💰 **Real money** | **2 live executors** on Binance Futures mainnet (crypto + gold), auto-leverage, exchange-side trailing stops |
| 🔬 **Discipline** | 20+ strategies tested → most **rejected** on out-of-sample; every survivor passes a bit-identical no-lookahead audit |
| 🔐 **Multi-user** | GoTrue auth, admin-approved signup, **RSA-encrypted** API keys, per-user execution fan-out, Postgres **RLS** everywhere |

---

## 🟢 The live book — what's actually trading

Three streams are surfaced live. Two place **real orders**; the rest of the research book is backtest-only (opt-in lab surfaces).

| Stream | Strategy | Market | Money | Headline result |
|---|---|---|---|---|
| 🔴 **OPUS** (`d30so8f3h7`) | Donchian 30m breakout + 4h confirm, scale-out (60 % @ +1R, runner to +8R cap / BE / 7-day stop) | Crypto (BTC/ETH/SOL/FET/ARB) | **REAL** · mainnet | **+388.6R** / 2 806 trades / PF **1.29** / WR **54 %** — every year positive (2024 +45.8 · 2025 +200.9 · 2026 +141.9) |
| 🔴 **TALOS-ICHI-X** (`talos_ichi`) | Gold Keltner-band deep pullback + **Ichimoku Kumo** direction filter, 3.5×ATR chandelier trail | XAUUSDT · 1m | **REAL** · mainnet · $3/trade | Ichimoku filter lifts a 3-yr OOS book **+35.6R → +118.3R** (avgR/WR/PF up every year) |
| 🟡 **MIDAS-X** (`midas`) | Gold VWAP-trend pullback + 3.5×ATR trail, AFTER-LOSS gate | XAUUSDT · 1m | paper (testnet) | **+142R** settled 2026-H1 / PF **1.48** on an FX/ECN cost model — dies on Binance taker fees, so kept paper |

> **Why gold is paper on Binance:** MIDAS/VWAP-trend clears **+142R** at an FX/ECN cost (~$0.50/oz) but flips to **≈ −92R** at Binance taker fees (~$4/oz). TALOS-ICHI won the real-money slot because it survives the fee model with an exchange-side trailing stop. This cost-honesty is the whole point — see [MIDAS.md](MIDAS.md).

---

## 🔬 Research highlights (and the rigor behind them)

The interesting story isn't the winners — it's how many **plausible** strategies died on honest testing.

- **Out-of-sample is the judge.** In-sample (2026) nearly *everything* was green; replaying on the 2025 regime **killed almost all of it** (MAIN v1 −245R, IMPULSE v2 −221R OOS). The surviving insight: our ICT set is a **range / mean-reversion** system — edge lives in genuine range regimes, not in trend/momentum. → [STRATEJI-RAPORU.md](STRATEJI-RAPORU.md)
- **No-lookahead audits, bit-identical.** Every stream is re-run on month-end-truncated data and must reproduce the full run's signal set exactly (2026: 15/15, 2025: 63/63 clean). The ML feature frame was truncation-tested to **0.00e+00** max difference. So OOS collapse is *real overfit*, never a code bug.
- **Gold, from scratch.** An independent FX/gold study rebuilt ORB / VWAP / mean-reversion / session-momentum on 2026-H1 XAUUSDT 1m at realistic cost. One model survived: **VWAP-Trend Pullback + ATR trail, +115R / PF 1.32**, validated by a parameter plateau, honest IS→OOS split, a random-entry null test (**p < 0.005**), and a from-scratch reimplementation that matched to the decimal. → [FX-GOLD-VWAP-RAPORU.md](FX-GOLD-VWAP-RAPORU.md)
- **We even say no to ML.** A LightGBM triple-barrier meta-labeling model on gold learns a real, cross-year signal (purged-CV AUC **0.563**, shuffle-null 0.511) — but can't beat the one-feature AFTER-LOSS gate already live. Verdict: **NO-SHIP**, documented honestly. → [ML-XAU-RAPORU.md](ML-XAU-RAPORU.md)

---

## 🏗️ Architecture

```
                      Binance Futures (XAUUSDT / crypto perps, 1m klines)
                                          │
        ┌─────────────────────────────────┼──────────────────────────────────┐
        ▼ nightly ETL                      ▼ cron, every bar                   ▼ every 1–2 min
  Backtest engines               Live signal emitters               Real-money EXECUTORS
  (full 2024–26 replay,          (fresh setups → Telegram +          OPUS  → crypto mainnet
   commission-aware,              phone push)                        TALOS-ICHI-X → gold mainnet
   single-position walk)               │                                   │  (maker GTX entry,
        │                              │                                   │   exchange-side trail,
        ▼                              ▼                                   ▼   after-loss gate,
  ict_trade.trading_signals     ict_trade.signals               ict_trade.*_positions / live_account
  (Postgres · backtest DB)      (Postgres · live DB)            (managed state machines + safety sweep)
        └──────────────┬───────────────┴──────────────┬─────────────────────┘
                       ▼                               ▼
              React + Vite dashboard         Supabase RLS + GoTrue auth
        (live feed · Year→Month→Day          (multi-user, RSA-encrypted keys,
         drill-down · TradingView charts)     per-user execution fan-out)
```

Runs on an Oracle Cloud **Always-Free** VM in an EU region (US IPs get HTTP 451 from Binance). Full data-flow and fresh-clone bring-up: **[RUNBOOK.md](RUNBOOK.md)**.

---

## 🖥️ The application

React/Vite dashboard — `npm run dev` → `localhost:5173`, deployed from `main`. Surface map:

| Route | Surface |
|---|---|
| `/binance` · `/binance-paper` | **Binance Live / Paper** boards — open positions, live P/L, TP/SL, session clock |
| `/binance-altin` | **Gold detail** — TALOS-ICHI-X real-money gold, trailing-stop / locked-R view |
| `/trading` | **Trading Hub** — connect keys, arm/disarm streams, per-stream risk knobs |
| `/:strategy/:mode` | **Backtest drill-down** — Year → Month → Day, per-trade charts (all streams) |
| `/intelligence` · `/total` · `/trend` | Market intelligence, portfolio totals, regime/trend views |
| `/admin` | **Admin console** — users, approvals, features, global kill, announcements, cron toggles, audit log |
| `/settings` · `/login` | Prefs (theme/lang/notifications), soft client-side gate over RLS |

Alerts go out over **Telegram** (formation + trade lifecycle) and **Web Push** (VAPID phone notifications).

---

## 🧰 Tech stack

**Frontend** React 18 · Vite · Context API · TradingView lightweight charts · TR/EN i18n · CSP-hardened build
**Backend / data** Python 3.10+ (pandas · numpy) · Postgres (Supabase) · PostgREST · **RLS** · GoTrue auth
**Trading** Binance Futures REST · custom signed client (clock-drift self-heal, maker GTX + taker fallback) · exchange-side trailing stops
**Ops** cron on Oracle Cloud Free VM · Telegram Bot API · Web Push (`pywebpush` / VAPID) · GitHub Actions (nightly export)

---

## 🚀 Quickstart

```bash
# Dashboard
npm install
npm run dev          # localhost:5173
npm run build        # production bundle → dist/
npm run lint

# Backtest / live engine (Python)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python sync/donchian/canli.py --stream all      # emit live signals
python sync/midas/backfill.py                   # replay the gold book
```

Full setup (DBs, `.env`, cron install, VM provisioning): **[RUNBOOK.md §6](RUNBOOK.md)** · **[dag/DEPLOY_ORACLE.md](dag/DEPLOY_ORACLE.md)** · idempotent installer `dag/setup_vm.sh`.

---

## 📚 Documentation

| Doc | What's inside |
|---|---|
| **[RUNBOOK.md](RUNBOOK.md)** | Master ops & setup — every component, fresh-clone bring-up, cron, full changelog |
| **[MIDAS.md](MIDAS.md)** | Gold stream deep dive — strategy, executor, fee-reality, validation battery |
| **[STRATEJI-RAPORU.md](STRATEJI-RAPORU.md)** | Full strategy history — what was tried, what died on OOS, the lessons |
| **[FX-GOLD-VWAP-RAPORU.md](FX-GOLD-VWAP-RAPORU.md)** | From-scratch FX/gold research — the VWAP-trend model & its null tests |
| **[ML-XAU-RAPORU.md](ML-XAU-RAPORU.md)** | ML/DL literature review + honest meta-labeling experiment (NO-SHIP) |
| **[ICT_Signal_Strategies.md](ICT_Signal_Strategies.md)** · **[medium/](medium/)** | ICT concepts (FVG, OB, sweep, BOS/CHoCH, killzones) + write-up series |

---

## 🔐 Security

This is a **static frontend** — the login screen is a soft client-side gate; the real boundary is **Supabase RLS**.

- **Secrets never ship to the bundle.** `.env` is gitignored (Telegram token, Postgres DSN, Binance keys are backend-only); only `VITE_*` values reach the client (`vite.config.js > envPrefix`). User API keys are stored **RSA-encrypted**.
- **CSP** is injected at build (Supabase + Binance + TradingView + Google Fonts allow-list).
- **Auth hardening** — admin-approved signup, per-user RLS scoping, exponential backoff on failed logins (5 tries → 30 s, doubling to 15 min).
- The Supabase publishable key is visible in the bundle **by design** — RLS is what limits data access.

---

> ⚠️ **Disclaimer.** This is a personal research + trading system, not investment advice or a product. It places **real money** orders; strategies can and do lose. Backtest results are historical and cost-model-dependent — read the reports before drawing conclusions.
