"""ICT signal layer parameters. Defaults from ICT_Signal_Strategies.md."""

ATR_PERIOD = 14

SWING_N_ITF = 3
SWING_N_HTF = 5

EQUAL_LEVEL_TOL_PCT = 0.0005
EQUAL_LEVEL_TOL_ATR = 0.3

IMPULSE_ATR_MULT = 2.0
IMPULSE_BAR_WINDOW = 5
IMPULSE_CONSEC_BARS = 3

OB_FVG_OVERLAP_MIN = 0.3  # was 0.5 (spec); empirically rare on 1h, 0.3 still meaningful confluence
STRAT_C_PROXIMITY_ATR = 2.0  # spec says 1; 1h-scaled markets need a bit more headroom

# Max age (in primary-TF bars) for an OB or FVG to remain a valid signal source.
# Old zones that price has long left behind generate signals nowhere near price.
ZONE_MAX_AGE_BARS = 100

SWEEP_LOOKBACK_BARS = 5
CHOCH_AFTER_SWEEP_BARS = 5
ENTRY_EXPIRY_BARS = 12          # legacy fallback; engine now computes from EXPIRY_MINUTES
EXPIRY_MINUTES = 180            # bar-agnostic: 3 hours of opportunity to fill the limit

SL_ATR_BUFFER = 0.2
SL_ATR_BUFFER_C = 0.3

# One zone = one trade. A live OB/FVG zone re-fires a near-identical signal on
# every bar it survives (2026 audit: 5x the same XAG trade 15m apart; same-day
# 14:00/18:00 silver-bullet copies), inflating trade counts and stacking risk on
# a single setup. A signal is suppressed when another signal with the same
# direction and ~the same entry fired within the previous cooldown window.
DEDUP_COOLDOWN_MINUTES = 1440   # 24h rolling; 0 disables
DEDUP_ENTRY_TOL_PCT = 0.0005    # entries within 0.05% of each other = same zone

# Floor on SL distance: max(pct-of-entry, ATR multiple). Razor-thin zones put
# the stop inside the spread (pulse audit: median stop 0.12% of price, wins
# pinned at the 13.33R cap) — fantasy R that live fills can't deliver.
MIN_SL_DIST_PCT = 0.0015        # 0.15% of entry
MIN_SL_DIST_ATR = 0.5           # half an ATR

# Round-trip friction applied by the backtester when computing pnl_r.
# Binance futures taker is 0.045-0.05%/side; spread/slippage rides on top.
FEE_PCT_PER_SIDE = 0.0005

MIN_RR_DEFAULT = 2.0
MIN_RR_SILVER_BULLET = 3.0

# Strategy D (silver bullet) is symbol-sensitive: 2026 Jan-Jun v1 audit showed it
# net-negative on these even though the symbols stay positive overall via C.
# D returns None for them; other strategies still run.
D_EXCLUDE_SYMBOLS = {"NVDAUSDT", "NEARUSDT", "AMZNUSDT", "ORDIUSDT"}

# Cap TP1 distance to avoid 16R unrealistic targets caused by sparse liquidity.
# 0 disables capping.
TP_MAX_ATR_MULT = 4.0

# --- RADAR (strategy F: vol-compression Donchian breakout -> mode='radar'/version='v3') ---
# Trend-continuation stream: enters on a retest of a fresh 120-bar channel break that
# emerged from below-average volatility. Deliberately the structural opposite of the
# ICT zone-reversal strategies (A-E fade into zones; F joins breakouts out of squeeze).
# STATUS 2026-06-10: Jan-Jun 2026 backtest FAILED the acceptance gates (-60R, 15% win,
# only January positive); the sync/experiment_v3.py ablation showed market-at-close
# entries and 2R targets are also negative — the live stream stays OFF (dag.py
# RADAR_ENABLED=0) pending a redesign.
RADAR_DONCHIAN_LOOKBACK = 120    # channel = max/min of the PRIOR 120 bars (fire bar excluded)
RADAR_ATR_PERIOD        = 24
RADAR_COMPRESSION_SMA   = 240    # SMA window over ATR24
RADAR_COMPRESSION_MAX   = 0.85   # ATR24[i-1] < 0.85 * SMA240(ATR24)[i-1]
RADAR_DEEP_COMPRESSION  = 0.70   # graded confluence factor threshold
RADAR_VOL_MEDIAN_BARS   = 20
RADAR_VOL_SURGE_MIN     = 1.5    # volume[i] > 1.5 * median(prior 20)
RADAR_STRONG_VOLUME     = 2.5    # graded confluence factor threshold
RADAR_EMA_PERIOD        = 200    # regime filter: close above/below EMA200
RADAR_SL_ATR_MULT       = 2.5    # SL = entry -/+ 2.5 * ATR24 (MIN_SL_DIST floor never binds)
RADAR_TP_R_MULT         = 3.0    # TP = 3R fixed (NOT _cap_tp'd — 7.5xATR24 would clip to ~1.6R)
RADAR_CHASE_MAX_ATR     = 1.2    # skip if |close - level| > 1.2 * ATR24 (won't retest)
RADAR_ENTRY_EXPIRY_BARS = 24     # 24h retest window (overrides the engine 3-bar default)
RADAR_REFIRE_BARS       = 24     # no same-direction RAW trigger in the prior 24 bars

# --- SQUEEZE (strategy G: funding-extreme squeeze fade -> mode='squeeze'/version='v4') ---
# Derivative-positioning stream: fades CROWDED positioning revealed by extreme perp
# funding. Very negative funding = crowded shorts paying longs -> LONG on a squeeze
# ignition bar (SHORT mirrored on positive extremes). Uses NO price geometry at all —
# the judge panel's lowest-correlation candidate vs A-E (zone reversal) and F (breakout).
# Funding accrual is NOT credited in the backtest PnL; the fade direction RECEIVES
# funding while in the trade, so reported R is conservative by construction.
# Rates are normalized to an 8h-equivalent (some symbols settle every 4h) using each
# event's actual spacing to its predecessor; the first event of a series has no
# spacing and is excluded from both triggering and the percentile distribution.
# STATUS 2026-06-10: Jan-Jun 2026 backtest FAILED the acceptance gates (116 closed,
# 24.1% win, -52.3R; both directions negative; only June +1.9R). Losses concentrate
# in Mar/Apr and the metals + stock-backed perps — extreme funding marked positioning
# that was RIGHT about the trend in this regime. The sync/experiment_squeeze.py
# ablation found NO one-knob variant with a positive sign (best -36R) — the live
# stream stays OFF (dag.py SQUEEZE_ENABLED=0) pending a redesign.
SQUEEZE_ATR_PERIOD       = 24      # same smoother horizon as RADAR's ATR24
SQUEEZE_ABS_MIN_8H       = 0.0005  # |rate_8h| >= 0.05%/8h (5x the 0.01% baseline)
SQUEEZE_SEVERE_8H        = 0.0010  # graded confluence factor threshold (0.10%/8h)
SQUEEZE_PCTL_WINDOW      = "30D"   # trailing event window for the crowding percentile
SQUEEZE_PCTL             = 0.95    # extreme = beyond the 95th/5th pctl of PRIOR events
SQUEEZE_MIN_EVENTS       = 40      # prior events required in window (warmup guard)
SQUEEZE_STALE_HOURS      = 12.0    # no signal if the last settled event is older than this
SQUEEZE_IGNITION_ATR     = 0.25    # fire bar must close >= 0.25*ATR24 in squeeze direction
SQUEEZE_RETRACE_ATR      = 0.35    # entry = retrace limit 0.35*ATR24 inside the close
SQUEEZE_SL_ATR_MULT      = 2.0     # SL = entry -/+ 2.0*ATR24 (floor never binds)
SQUEEZE_TP_R_MULT        = 2.0     # TP = 2R fixed (squeezes resolve fast)
SQUEEZE_ENTRY_EXPIRY_BARS = 12     # 12h fill window — crowding signals are time-sensitive
SQUEEZE_REFIRE_BARS      = 48      # one trade per crowding episode (raw-trigger cooldown)

# Higher timeframe used for bias detection. Resampled from the primary df.
HTF_RULE = "4h"

OTE_LOW = 0.62
OTE_HIGH = 0.79

ASIA_RANGE_MAX_ATR = 3.0  # was 1.5; on 1h the 5h Asia session naturally spans 2-3 ATRs

NY_TZ = "America/New_York"

# (start_hour, end_hour) in NY local time. End exclusive. None means crosses midnight.
KILLZONES_NY = {
    "asia_range":       (19, 24),  # 19:00 -> 00:00
    "london_open":      (2, 5),
    "ny_open":           (7, 10),
    "silver_bullet_am": (10, 11),
    "london_close":     (10, 12),
    "silver_bullet_pm": (14, 15),
}

CONFLUENCE_WEIGHTS = {
    "htf_aligned":        3,
    "liquidity_swept":    2,
    "ltf_choch":          2,
    "discount_premium":   1,
    "ote_zone":           1,
    "in_killzone":        1,
    "ob_fvg_overlap":     2,
    "eqh_eql_swept":      1,
    "silver_bullet":      2,
    "power_of_three":     2,
    "multi_strategy":     3,
    # radar / strategy F factors (required trio scores 7 >= publish; both graded
    # extras reach 9 = CONFLUENCE_HIGH -> quality 'high')
    "regime_aligned":     3,
    "vol_compression":    2,
    "volume_surge":       2,
    "deep_compression":   1,
    "strong_volume":      1,
    # squeeze / strategy G factors (required trio scores 7 >= publish; both graded
    # extras reach 9 = CONFLUENCE_HIGH -> quality 'high')
    "funding_extreme":     3,
    "crowding_percentile": 2,
    "squeeze_ignition":    2,
    "funding_severe":      1,
    "funding_unwind":      1,
}

CONFLUENCE_MIN_PUBLISH = 6
CONFLUENCE_HIGH = 9
CONFLUENCE_MAX = 12
