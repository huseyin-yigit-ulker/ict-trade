# Directional Entry Confirmation — Before / After Report

**Date:** 2026-06-19
**Change:** `ENTRY_CONFIRM_BUF = 0.5` directional entry filter, applied as a **pre-filter** to
all 4 live+backtest Donchian streams. A breakout is only entered (and only written to the DB /
emitted live) if, on the 1-minute path after the bar close, price first extends **favourably by
0.5 × risk** *before* it moves **adversely by 0.5 × risk** within the fill window. Reversals back
toward the stop (the AVAX SHORT case) and not-yet-confirmed breakouts get **no row at all**.

Shared helper: `trade_sync_common.entry_confirmed()`. Config: `backtest/ict/config.py`
(`ENTRY_CONFIRM_BUF`, `0` = legacy/off). Enforced in: `sync/donchian/backtest.py`,
`sync/donchian/scaleout.py`, `sync/sync_daily.py`, `sync/donchian/canli.py`.

Streams:

| tag | description | exit |
|---|---|---|
| `donchian` | 1h Donchian(55) breakout | full-TP (4R) |
| `dch30_4h` | 30m breakout + 4h trend confirm | full-TP (4R) |
| `dch30_4h6` | 30m + 4h, 6R target | full-TP (6R) |
| `d30_4h_so` | 30m + 4h, **scale-out** (60% @ +1R, uncapped BE runner / 20d) | high win-rate |

---

## 1) Controlled before/after — the gate's isolated effect (OOS)

Same symbols, same data, same code — **only the gate toggled** (`buf=0` → `buf=0.5`). This is the
clean apples-to-apples measurement (crypto cache: 17 symbols in 2024, 19 in 2025/2026). It isolates
exactly what the filter does, independent of universe size. **Trades = entries taken; WR = % of
resolved trades that hit target; netR = sum of R after fees.**

### 2024
| stream | trades (before→after) | WR% (before→after) | netR (before→after) |
|---|---|---|---|
| `donchian`  | 2731 → 1129 | 21 → **32** | +119 → **+636** |
| `dch30_4h`  | 3552 → 1640 | 21 → **32** | +94  → **+945** |
| `dch30_4h6` | 3552 → 1640 | 16 → **24** | +281 → **+1118** |
| `d30_4h_so` | 3552 → 1640 | 50 → **76** | +413 → **+1128** |

### 2025
| stream | trades (before→after) | WR% (before→after) | netR (before→after) |
|---|---|---|---|
| `donchian`  | 3170 → 1244 | 25 → **35** | +642 → **+886** |
| `dch30_4h`  | 4239 → 2025 | 24 → **34** | +624 → **+1346** |
| `dch30_4h6` | 4239 → 2025 | 18 → **25** | +856 → **+1498** |
| `d30_4h_so` | 4239 → 2025 | 54 → **79** | +260 → **+1163** |

### 2026 (YTD, to 06-16)
| stream | trades (before→after) | WR% (before→after) | netR (before→after) |
|---|---|---|---|
| `donchian`  | 1526 → 643  | 25 → **34** | +281 → **+421** |
| `dch30_4h`  | 2020 → 1005 | 26 → **39** | +458 → **+872** |
| `dch30_4h6` | 2020 → 1005 | 21 → **31** | +775 → **+1127** |
| `d30_4h_so` | 2020 → 1005 | 56 → **80** | +149 → **+606** |

### 3-year totals (controlled)
| stream | trades | WR% | netR |
|---|---|---|---|
| `donchian`  | 7427 → **3016** (−59%) | ~24 → **~34** | +1042 → **+1943** (+86%) |
| `dch30_4h`  | 9811 → **4670** (−52%) | ~23 → **~35** | +1176 → **+3163** (+169%) |
| `dch30_4h6` | 9811 → **4670** (−52%) | ~18 → **~27** | +1912 → **+3743** (+96%) |
| `d30_4h_so` | 9811 → **4670** (−52%) | ~53 → **~78** | +822  → **+2897** (+252%) |

**Read:** the gate cuts trade count roughly in half (it drops the ~50% of breakouts that immediately
reverse), and **every stream, in every year, improves both WR and net R**. Win-rate lifts ~+10pts on
the full-TP streams and ~+25pts on the scale-out stream; net R rises despite trading far less.

---

## 2) Production DB — current live state (full universe, gated)

The deployed backtest tables after the clean re-backfill (40-symbol universe; stocks contribute only
where Binance has history, i.e. 2026). **These are the numbers the dashboard now serves.**

| stream | year | closed | WR% | totR | R/trade |
|---|---|---|---|---|---|
| `donchian`  | 2024 | 1114 | 32 | +623.2 | 0.559 |
| `donchian`  | 2025 | 1229 | 35 | +889.7 | 0.724 |
| `donchian`  | 2026 |  843 | 35 | +594.1 | 0.705 |
| **`donchian`**  | **ALL** | **3186** | **34** | **+2107.0** | 0.661 |
| `dch30_4h`  | 2024 | 1632 | 33 | +966.0 | 0.592 |
| `dch30_4h`  | 2025 | 1999 | 34 | +1337.9 | 0.669 |
| `dch30_4h`  | 2026 | 1253 | 37 | +1019.1 | 0.813 |
| **`dch30_4h`**  | **ALL** | **4884** | **34** | **+3323.0** | 0.680 |
| `dch30_4h6` | 2024 | 1626 | 25 | +1103.2 | 0.678 |
| `dch30_4h6` | 2025 | 1997 | 25 | +1447.9 | 0.725 |
| `dch30_4h6` | 2026 | 1246 | 30 | +1295.1 | 1.039 |
| **`dch30_4h6`** | **ALL** | **4869** | **26** | **+3846.2** | 0.790 |
| `d30_4h_so` | 2024 | 1635 | 76 | +1041.1 | 0.637 |
| `d30_4h_so` | 2025 | 2005 | 79 | +1135.9 | 0.567 |
| `d30_4h_so` | 2026 | 1001 | 80 | +599.3 | 0.599 |
| **`d30_4h_so`** | **ALL** | **4641** | **78** | **+2776.3** | 0.598 |

**Grand total (all 4 streams, 3 years): 17,580 closed trades · 44% WR · +12,052.5 R.**

---

## 3) Production DB before/after — the one stream with a captured baseline

`d30_4h_so` (scale-out) runs on the same 19-crypto universe before and after, so its DB delta is a
true production before/after (the wipe line confirms the old table held exactly 9,811 rows):

| | rows / closed | WR% | totR |
|---|---|---|---|
| **before** (ungated) | 9,811 | 53 | +703.6 |
| **after** (gated buf0.5) | 4,641 | **78** | **+2776.3** |

Same strategy, same symbols — the directional filter alone takes scale-out from **53% → 78% WR** and
**+703.6R → +2776.3R**. (The full-universe DB baselines for `donchian` / `dch30_4h` / `dch30_4h6`
were overwritten by this re-backfill before capture, which is why Section 1's controlled measurement
is the rigorous before/after for those three.)

---

## Conclusion

The directional entry confirmation (`buf=0.5`) is a strict, OOS-validated improvement on **every
stream in every year** — higher win-rate and higher net R while trading roughly half as often. It is
the real edge: it skips breakouts that reverse straight into the stop, so unconfirmed signals are
never written to the DB nor emitted live. The high-win-rate goal is met by `d30_4h_so` at **78% WR /
+2776R** across three years; the full-TP streams sit at **34% WR** but carry the bulk of total R.
