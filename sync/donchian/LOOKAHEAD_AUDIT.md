# Look-Ahead & Live-Parity Audit — All Strategies

**Date:** 2026-06-19
**Question asked:** prove the backtest data of every strategy has **no look-ahead (future-data)
bias**, and that **live will produce the same results as backtest**.

**Verdict: PASS.** No look-ahead found in any live or backtest signal path. Live ≡ backtest is
proven both by code (one shared signal path) and empirically (every live row reproduced by the
backtest engine, prices to 1e-4). Details and the reproducible tests below.

---

## 1) Scope

| Strategy (version) | Status | Signal path | Resolution |
|---|---|---|---|
| `donchian` (1h) | **LIVE** | `strategy.generate_signals` (1h) | `tsc.simulate` → `simulate_signal` |
| `dch30_4h` (30m+4h) | **LIVE** | `generate_signals` (30m) + `htf_confirm` (4h) | same |
| `dch30_4h6` (30m+4h, 6R) | **LIVE** | same as dch30_4h, RR=6 (TP only) | same |
| `d30_4h_so` (scale-out) | **LIVE** | reuses `dch30_4h` signals | `scaleout.resolve_scaleout` (forward 1m walk) |
| ICT engine (MAIN/IMPULSE, `strategy_b/c/d/e`) | retired live, backtest rows exist | `engine.run_engine` | `simulate_signal` |
| KARMA / OPUS / RANGE / *_light | backtest-only | per-symbol map / Burak deviation | see §6 |

The four Donchian streams are what the dashboard serves and the cron emits, so they get the
deepest treatment (§3–§5). The retired/backtest-only strategies are covered in §6.

---

## 2) Methodology

Four independent lines of evidence:

1. **Static causality audit** — read every indicator and the resolver, line by line, checking
   that bar *i*'s decision uses only data available at bar *i*'s close (§3).
2. **Dynamic truncation-invariance test** — re-generate signals on data truncated to "everything
   closed by time *T*" and require an exact match with the full-history run for every *T* (§4).
   This is the gold-standard automated look-ahead proof: any future-data dependence shows up as a
   signal that appears/disappears when the future is hidden.
3. **Live-vs-backtest parity** — re-run the production signal path against the live DB rows and
   require every live signal to be reproduced by the backtest engine, same bar, prices to 1e-4 (§5).
4. **DB invariant audit** — query the shipped backtest rows for impossible orderings that a leak
   would produce (exit before entry, entry before the bar even closed, etc.) (§7).

New reproducible tooling (added this audit):
- `sync/donchian/lookahead_check.py` — truncation test for the live Donchian paths.
- `sync/donchian/live_parity.py` — live-DB vs backtest-engine parity for the 3 emit modes.

---

## 3) Static causality audit (Donchian)

Every input to a bar-*i* decision is `≤ i` and known at bar *i*'s close:

| Component | File:line | Why it is causal |
|---|---|---|
| Donchian channel | [strategy.py:218-219](strategy.py#L218-L219) | `high.rolling(55).max().shift(1)` / `low…min().shift(1)` — the `.shift(1)` **excludes the current bar**, so the channel is the *prior* 55 bars only. |
| Fresh-break test | [strategy.py:227-228](strategy.py#L227-L228) | `c[i] > hi[i] and c[i-1] <= hi[i-1]` — uses only bar *i* (its close) and *i-1*. |
| Entry / SL / TP | [strategy.py:230-238](strategy.py#L230-L238) | `entry = close[i]` (the breakout bar's close = the fire price); `SL = entry ∓ 2·ATR`, `TP = entry ± RR·risk` — all fixed at the fire bar. |
| ATR | [strategy.py:187-191](strategy.py#L187-L191) | TR uses `close.shift(1)`; EWM at *i* uses bars `≤ i`. |
| Efficiency ratio | [strategy.py:194-198](strategy.py#L194-L198) | `close.diff(n)` and `rolling(n).sum()` over the last *n* bars `≤ i`. |
| 4h trend confirm | [strategy.py:129-143](strategy.py#L129-L143) | `close_time = htf.index + htf_bar`; `searchsorted(fire, 'right')-1` consults **only HTF bars whose close ≤ the base bar's close**. Midline uses `.shift(1)`. |
| US-hours gate | [strategy.py:101-107](strategy.py#L101-L107) | Pure time-of-day on the fire time. |
| Directional confirm gate | [trade_sync_common.py:140-174](../trade_sync_common.py#L140-L174) | Walks 1m **forward** from the bar close; ties → adverse (pessimistic). |
| Fill + TP/SL resolver | [backtester.py:136-221](../../backtest/backtester.py#L136-L221) | Walks **forward** from `bar_index+1`; entry must fill before TP/SL (else INVALIDATED); same-bar TP+SL tie → **SL** (pessimistic). |
| Scale-out legs | [scaleout.py:107-171](scaleout.py#L107-L171) | Fills via `tsc.simulate`, then walks `[fill, fill+20d]` **forward**; same-bar +1R/−1R tie → stop (`t_stop ≤ t_tf`). |

No component reads a bar dated after the decision bar. Tie-breaks are pessimistic, so if anything
the model **understates** edge — the opposite of a look-ahead inflation.

---

## 4) Dynamic truncation-invariance test (Donchian) — `lookahead_check.py`

For each cut time *T*, both frames (base tf, and the 4h confirm tf) are truncated to bars closed
by *T* — exactly what the live emitter sees — and signals are regenerated. A leak would make a
signal appear only with future data (missing when truncated) or be vetoed by future data (extra).

```
2026  | 1h + 30m+4h | BTC ETH SOL XAU         : 800 signals,  0 diffs  PASS
2025  | 1h + 30m+4h | BTC ETH XAU             : 778 signals,  0 diffs  PASS
2026  | 1h + 30m+4h | BTC ETH SOL BNB XRP AVAX XAU NVDA : 1447 signals, 0 diffs  PASS
```

**Total: 3,025 signal-checks across 2 years, 8 symbols (crypto + metal + stock-perp), both live
configs — 0 look-ahead differences.** (RR=6 shares this proof: RR only sets `TP = entry ± RR·risk`
at the fire bar and does not touch the break/confirm logic.)

Re-run: `python sync/donchian/lookahead_check.py --year 2026 --symbols BTCUSDT ETHUSDT …`

---

## 5) Live-vs-backtest parity (Donchian) — `live_parity.py`

Every row currently in `ict_trade.signals` (modes `donchian` / `dch30_4h` / `dch30_4h6`) was
re-derived by the backtest engine from freshly-fetched klines.

```
live rows = 61
FORWARD  reproduced (live ≡ backtest, prices ≤1e-4) = 61
         price-mismatch = 0
         live-row-without-backtest-twin = 0
REVERSE  (gate-applied) confirmed backtest breakout due-but-absent-from-live = 0
RESULT: PASS — canlı Donchian sinyalleri ≡ backtest
```

Interpretation: the live emitter and the backtester run the **same** `generate_signals` /
`htf_confirm` / `us_hours_gate` / `entry_confirmed` / `simulate` code, so given the same
(immutable, once-closed) Binance bars they cannot diverge. The forward direction proves no live
row is fabricated; the reverse (after applying the same confirm gate) proves none is missed. The
constants match across the stack — backend `ENTRY_CONFIRM_BUF=0.5`, `EXPIRY_MINUTES=180`,
`FEE_PCT_PER_SIDE=0.0005`; the React mirror ([TradeContext.jsx:34,41](../../src/context/TradeContext.jsx#L34))
uses the identical `0.5` / `180`. `d30_4h_so` consumes the `dch30_4h` signals verbatim
([sync_daily.py:295-346](../sync_daily.py#L295-L346)), so its parity follows transitively.

---

## 6) Auxiliary / backtest-only strategies

A dedicated sweep audited every non-Donchian strategy's signal generation and resolution, and
re-ran the ICT-engine truncation test.

**ICT engine (MAIN / IMPULSE = `strategy_b/c/d/e`)** — `backtest/validation/lookahead_check.py`:

```
2026 | BTC/ETH/XAU | 15 cuts | PASS — 0 missing, 0 extra on every cut
2025 | BTC/ETH/XAU | 40 cuts | PASS — 0 missing, 0 extra on every cut
```

Every month-end cut reproduced the full run's `bar_index ≤ t` signals bit-for-bit. The ICT
detectors (`detect_structure` / `mark_sweeps` / `detect_fvgs` / `detect_order_blocks` / swings)
compute forward-dated objects but every consuming strategy guards with `… ≤ at_index`
(e.g. `strategies.py:179, 341, 436, 57-59`), and the truncation PASS is the definitive proof those
guards are complete.

**Verdict table:**

| Module | Signal gen | Resolution | Verdict |
|---|---|---|---|
| ICT engine (B/C/D/E) | causal | shared resolver | **causal-OK** (test-proven, both yrs) |
| Shared resolver `simulate_signal` / `tsc.simulate` | — | strictly forward, pessimistic SL ties | **causal-OK** |
| `backtest_karma.py` + `karma_map.py` | causal (ICT engine) | forward 1m | **IN-SAMPLE SELECTION** (not look-ahead) |
| `backtest_opus.py` + `opus_map.py` | causal (ICT + session gate on `signal_time`) | forward 1m | **IN-SAMPLE SELECTION** (not look-ahead) |
| `backfill_range.py` + `burak_strategy.py` | causal (range window `…i-DEV_GAP`, pivots confirmed at `i-PIVOT_K`) | forward 1m | **causal-OK** (in-sample universe caveat) |
| `regime_ensemble.py` (RANGE 4h gate) | causal (last 4h bar closed ≤ fire) | — | **causal-OK** |
| `range_complement.py` | reuses RANGE pipeline (no DB write) | reuses `tsc.simulate` | **causal-OK** |

**Key distinction — selection bias ≠ look-ahead.** KARMA and OPUS pick their per-symbol cell /
trading session using outcomes computed over the **same 2026-H1 window** they then report, so
their headline R is an in-sample **upper bound** (overfit). This is *not* future-data leakage —
no single trade consumes a bar dated after its decision. Both are self-documented as such
(`karma_map.py:14`, `opus_map.py:17`), and crucially the 2026-selected maps are applied **forward**
in live `sync_daily` over a rolling recent window, which is a legitimate out-of-sample test of the
selection. RANGE carries a milder version (the 29-symbol universe + `trend`-verdict gate were
chosen in-sample) but its per-trade mechanics are fully causal. None of these three is live today
(backtest-only), so none affects live parity.

> **Post-audit note (2026-06-19):** the `d30_4h_so` runner exit was subsequently capped at +4R with
> a 3-day time-exit (was uncapped/20d). This is a **resolution-only, forward-walking** change (it
> never consults a bar dated after the runner's exit), so it introduces no look-ahead; the §7 DB
> invariants were re-run on the re-backfilled rows and remain clean (closed_tp `pnl_r` now bounded
> at the +2.19R cap). Signal generation is untouched, so §3–§5 are unaffected.

---

## 7) DB invariant audit (shipped backtest rows)

Queried all four versions for orderings a leak would produce:

| version | rows | closed | exit<entry | entry<bar-close | closed w/o entry | entry≠breakout-close | SL with +PnL |
|---|---|---|---|---|---|---|---|
| `donchian` | 3248 | 3186 | 0 | 0 | 0 | 0 | 0 |
| `dch30_4h` | 4945 | 4884 | 0 | 0 | 0 | 0 | 0 |
| `dch30_4h6` | 4945 | 4869 | 0 | 0 | 0 | 0 | 0 |
| `d30_4h_so` | 4670 | 4641 | 0 | 0 | 0 | 0 | 0 |

All look-ahead invariants are zero. The only values beyond a clean `−1R` stop are a handful of
low-ATR XAU/XAG/NVDA losses where `pnl_r = −1 − fee` and the fee, `0.001·entry/risk`, is large
because the ATR stop is tighter than the 0.1% round-trip fee (risk 0.086–0.3% of price). Predicted
`−1 − fee` matches the stored `pnl_r` to 3 decimals on every such row — it is the **fee model**,
not a leak, and it is conservative (it makes losses bigger, never wins).

---

## 8) Conclusion

- **No look-ahead** in any live or backtest signal path (static audit + 3,025 truncation checks +
  DB invariants all clean).
- **Live ≡ backtest** by construction (one shared code path) and empirically (61/61 live rows
  reproduced, 0 mismatch, bidirectional).
- Where ambiguity exists (same-bar fills, tie-breaks, neither-target-in-horizon), the model resolves
  **pessimistically**, so realised live R should track — or modestly beat — the backtest, not fall short.

**Re-run everything:**
```bash
python sync/donchian/lookahead_check.py --year 2026          # Donchian truncation
python sync/donchian/lookahead_check.py --year 2025
python sync/donchian/live_parity.py                          # live ≡ backtest
python backtest/validation/lookahead_check.py --year 2026    # ICT engine (MAIN/IMPULSE)
```
