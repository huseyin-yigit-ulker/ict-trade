"""Diagnose why strategies B/C/E rarely fire.

For each strategy, walks every bar in the eligible killzone and counts how many
bars are rejected at each filter, so we can see exactly which filter is the
bottleneck."""

from __future__ import annotations
import sys
from collections import Counter
from pathlib import Path

import click
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from ict.data import fetch_klines
from ict.detectors import in_killzones, htf_bias
from ict.strategies import (
    _next_opposite_liquidity, _next_persistent_liquidity, _cap_tp,
    _resolve_bias, _atr_at, _asia_range_for, _overlap_pct, _rr,
)
from ict import config as C
from engine import build_detectors


def diagnose_b(df: pd.DataFrame, bundle) -> Counter:
    cnt: Counter = Counter()
    n = len(df)
    for i in range(C.ATR_PERIOD + 5, n):
        ts = df.index[i]
        cnt["bars_total"] += 1
        if not in_killzones(ts, ["london_open", "ny_open"]):
            cnt["1_killzone_miss"] += 1
            continue
        cnt["1_in_killzone"] += 1
        rng = _asia_range_for(df, i)
        if not rng:
            cnt["2_no_asia_range"] += 1
            continue
        cnt["2_asia_range_ok"] += 1
        a_hi, a_lo, _, asia_end_i = rng
        a = _atr_at(bundle.atr, i)
        if a <= 0:
            cnt["3_no_atr"] += 1
            continue
        if (a_hi - a_lo) > C.ASIA_RANGE_MAX_ATR * a:
            cnt["3_asia_range_too_wide"] += 1
            continue
        cnt["3_asia_range_narrow"] += 1
        sweep_dir = None
        sweep_idx = None
        for j in range(asia_end_i + 1, i + 1):
            if df["high"].iloc[j] > a_hi and df["close"].iloc[j] < a_hi:
                sweep_dir, sweep_idx = "above", j
                break
            if df["low"].iloc[j] < a_lo and df["close"].iloc[j] > a_lo:
                sweep_dir, sweep_idx = "below", j
                break
        if sweep_dir is None:
            cnt["4_no_manipulation"] += 1
            continue
        cnt["4_manipulation_found"] += 1
        direction = "short" if sweep_dir == "above" else "long"
        choch = next(
            (e for e in bundle.structure
             if e.type == "CHoCH"
             and sweep_idx <= e.broken_at_index <= i
             and ((direction == "short" and e.direction == "bearish") or
                  (direction == "long" and e.direction == "bullish"))),
            None
        )
        if not choch:
            cnt["5_no_choch_after_sweep"] += 1
            continue
        cnt["5_choch_present"] += 1
        impulse_range = range(sweep_idx, choch.broken_at_index + 1)
        side = "bullish" if direction == "long" else "bearish"
        has_zone = any(
            o for o in bundle.order_blocks
            if o.created_at_index in impulse_range and not o.mitigated and o.type == f"{side}_ob"
        ) or any(
            f for f in bundle.fvgs
            if f.created_at_index in impulse_range and f.fill_status != "filled" and f.type == f"{side}_fvg"
        )
        if not has_zone:
            cnt["6_no_ob_or_fvg_in_impulse"] += 1
            continue
        cnt["7_zone_present"] += 1
    return cnt


def diagnose_c(df: pd.DataFrame, bundle) -> Counter:
    cnt: Counter = Counter()
    n = len(df)
    for i in range(C.ATR_PERIOD + 5, n):
        cnt["bars_total"] += 1
        bias = _resolve_bias(bundle.structure, i, bundle.htf_bias_series)
        if bias == "range":
            cnt["1_htf_range"] += 1
            continue
        cnt["1_htf_directional"] += 1
        bos_seq = [e for e in bundle.structure if e.type == "BOS" and e.broken_at_index <= i]
        if len(bos_seq) < 2 or bos_seq[-1].direction != bos_seq[-2].direction:
            cnt["2_no_double_bos"] += 1
            continue
        cnt["2_double_bos_ok"] += 1
        side = "bullish" if bias == "bullish" else "bearish"
        a = _atr_at(bundle.atr, i)
        if a <= 0:
            cnt["3_no_atr"] += 1
            continue
        age_floor = i - C.ZONE_MAX_AGE_BARS
        valid_obs = [o for o in bundle.order_blocks
                     if age_floor <= o.created_at_index <= i and not o.mitigated and o.type == f"{side}_ob"]
        valid_fvgs = [f for f in bundle.fvgs
                      if age_floor <= f.created_at_index <= i and f.fill_status != "filled" and f.type == f"{side}_fvg"]
        cnt["3_valid_obs"] += len(valid_obs)
        cnt["3_valid_fvgs"] += len(valid_fvgs)
        if not valid_obs or not valid_fvgs:
            cnt["4_missing_ob_or_fvg_for_side"] += 1
            continue
        cnt["4_both_present"] += 1
        # NEAREST overlap zone (matches strategy_c logic)
        price = float(df["close"].iloc[i])
        best = None  # (dist_atr, ovl)
        for o in valid_obs:
            for f in valid_fvgs:
                ovl = _overlap_pct(o.top, o.bottom, f.top, f.bottom)
                if ovl < C.OB_FVG_OVERLAP_MIN:
                    continue
                top = max(o.top, f.top)
                bot = min(o.bottom, f.bottom)
                mid = (top + bot) / 2
                dist_atr = abs(price - mid) / a
                if best is None or dist_atr < best[0]:
                    best = (dist_atr, ovl)
        if best is None:
            cnt["5_no_overlap_zone"] += 1
            continue
        cnt["5_overlap_zone_exists"] += 1
        d = best[0]
        bucket = "0_2" if d <= 2 else ("2_5" if d <= 5 else ("5_10" if d <= 10 else "10+"))
        cnt[f"6_nearest_dist_atr_{bucket}"] += 1
        if d <= C.STRAT_C_PROXIMITY_ATR:
            cnt["7_within_proximity"] += 1
        else:
            cnt["7_too_far"] += 1
    return cnt


def diagnose_e(df: pd.DataFrame, bundle) -> Counter:
    cnt: Counter = Counter()
    n = len(df)
    eq_count = sum(1 for l in bundle.liquidity if l.type in ("EQH", "EQL"))
    eq_swept = sum(1 for l in bundle.liquidity if l.type in ("EQH", "EQL") and l.swept)
    cnt["info_eq_levels_total"] = eq_count
    cnt["info_eq_levels_swept_ever"] = eq_swept

    for i in range(C.ATR_PERIOD + 5, n):
        cnt["bars_total"] += 1
        ts = df.index[i]
        if not in_killzones(ts, ["london_open", "ny_open"]):
            cnt["1_killzone_miss"] += 1
            continue
        cnt["1_in_killzone"] += 1
        bias = _resolve_bias(bundle.structure, i, bundle.htf_bias_series)
        if bias == "range":
            cnt["2_htf_range"] += 1
            continue
        cnt["2_htf_directional"] += 1
        eq_recent = [
            l for l in bundle.liquidity
            if l.type in ("EQH", "EQL") and l.swept and l.swept_at_index is not None
            and i - 3 <= l.swept_at_index <= i
        ]
        if not eq_recent:
            cnt["3_no_eq_swept_in_3_bars"] += 1
            continue
        cnt["3_eq_swept_recently"] += 1
        swept = eq_recent[-1]
        direction = "short" if swept.type == "EQH" else "long"
        if (direction == "long" and bias != "bullish") or (direction == "short" and bias != "bearish"):
            cnt["4_direction_mismatch_bias"] += 1
            continue
        cnt["5_bias_aligned"] += 1
        side = "bullish" if direction == "long" else "bearish"
        impulse_range = range(swept.swept_at_index, i + 1)
        cand_obs = [o for o in bundle.order_blocks
                    if o.created_at_index in impulse_range
                    and not o.mitigated and o.type == f"{side}_ob"]
        cand_fvgs = [f for f in bundle.fvgs
                     if f.created_at_index in impulse_range
                     and f.fill_status != "filled" and f.type == f"{side}_fvg"]
        if not cand_obs and not cand_fvgs:
            cnt["6_no_zone_in_impulse"] += 1
            continue
        cnt["6_zone_in_impulse"] += 1
        # ATR + RR check
        a = _atr_at(bundle.atr, i)
        if a <= 0:
            cnt["7_no_atr"] += 1
            continue
        if cand_obs:
            zt, zb = cand_obs[-1].top, cand_obs[-1].bottom
        else:
            zt, zb = cand_fvgs[-1].top, cand_fvgs[-1].bottom
        entry = (zt + zb) / 2
        if direction == "long":
            stop = swept.sweep_extreme - C.SL_ATR_BUFFER * a
        else:
            stop = swept.sweep_extreme + C.SL_ATR_BUFFER * a
        tp1 = _next_opposite_liquidity(entry, direction, bundle.liquidity, i)
        tp1 = _cap_tp(entry, tp1, direction, a)
        if tp1 is None:
            cnt["7_no_tp"] += 1
            continue
        rr = _rr(entry, stop, tp1, direction)
        if rr < C.MIN_RR_DEFAULT:
            cnt["7_rr_too_low"] += 1
            continue
        cnt["8_signal_ok"] += 1
    return cnt


def print_counter(name: str, c: Counter):
    click.echo(f"\n--- {name} ---")
    for k in sorted(c.keys()):
        click.echo(f"  {k:<40s} {c[k]:>8}")


@click.command()
@click.option("--symbol", default="BTCUSDT")
@click.option("--days", default=60, type=int)
@click.option("--interval", default="1h")
def main(symbol: str, days: int, interval: str):
    end = pd.Timestamp.now(tz="UTC")
    start = end - pd.Timedelta(days=days)
    click.echo(f"diagnosing {symbol} {interval} for {days} days")
    df = fetch_klines(symbol, interval,
                      int(start.timestamp() * 1000),
                      int(end.timestamp() * 1000))
    click.echo(f"  {len(df)} bars")
    bundle = build_detectors(df)
    click.echo(f"  swings={len(bundle.swings)}  structure={len(bundle.structure)}  "
               f"liquidity={len(bundle.liquidity)}  OBs={len(bundle.order_blocks)}  "
               f"FVGs={len(bundle.fvgs)}")

    eq_count = sum(1 for l in bundle.liquidity if l.type in ("EQH", "EQL"))
    pdh_count = sum(1 for l in bundle.liquidity if l.type in ("PDH", "PDL", "PWH", "PWL"))
    click.echo(f"  EQH/EQL count: {eq_count}    PDH/PDL/PWH/PWL count: {pdh_count}")

    htf_dist = bundle.htf_bias_series.value_counts() if bundle.htf_bias_series is not None else "N/A"
    click.echo(f"  HTF bias distribution: {dict(htf_dist) if hasattr(htf_dist, 'to_dict') else htf_dist}")

    print_counter("Strategy B (Power of Three)", diagnose_b(df, bundle))
    print_counter("Strategy C (FVG + OB Confluence)", diagnose_c(df, bundle))
    print_counter("Strategy E (EQH/EQL Run)", diagnose_e(df, bundle))


if __name__ == "__main__":
    main()
