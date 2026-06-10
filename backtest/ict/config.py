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
