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

MIN_RR_DEFAULT = 2.0
MIN_RR_SILVER_BULLET = 3.0

# Cap TP1 distance to avoid 16R unrealistic targets caused by sparse liquidity.
# 0 disables capping.
TP_MAX_ATR_MULT = 4.0

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
}

CONFLUENCE_MIN_PUBLISH = 6
CONFLUENCE_HIGH = 9
CONFLUENCE_MAX = 12
