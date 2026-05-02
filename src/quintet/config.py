"""Quintet trading system configuration.

All configuration values centralized here, organized by functional group.
"""

from pathlib import Path

# =============================================================================
# IBKR CONNECTION
# =============================================================================
HOST = "127.0.0.1"
PORT = 4002
# Client 0 is required for broker-state collection: it can see/bind manual
# TWS/Gateway orders as well as orders submitted by this flow.
CLIENT_ID = 0

# =============================================================================
# SCHEDULER
# =============================================================================
# Daily EOD break run. America/Chicago matches CME local time.
SCHEDULER_TIMEZONE = "America/Chicago"
SCHEDULER_RUN_TIME = "16:30"
SCHEDULER_WEEKDAYS = (0, 1, 2, 3, 4)  # Monday-Friday
SCHEDULER_MODE = "live"  # "live" or "dry-run"
SCHEDULER_EXTRA_ARGS: tuple[str, ...] = ()

# =============================================================================
# TRADING SYSTEMS
# =============================================================================
# Keyed by alias. Label alone can't key — label-4 appears in C4, CS4, and E4.
SYSTEMS = ["C4", "CS4", "E4", "E7", "E13"]

VOICE_MAP = {
    "C4":  "trumpet",
    "CS4": "tenor",
    "E4":  "piano",
    "E7":  "bass",
    "E13": "drums",
}
VOICE_TO_SYSTEM = {v: k for k, v in VOICE_MAP.items()}

SYSTEM_LABEL    = {"C4": 4, "CS4": 4, "E4": 4, "E7": 7, "E13": 13}
SYSTEM_UNIVERSE = {"C4": "commodities", "CS4": "commodities", "E4": "equities", "E7": "equities", "E13": "equities"}
SYSTEM_SIDE     = {"C4": "long", "CS4": "short", "E4": "long", "E7": "long", "E13": "long"}

# =============================================================================
# RISK MANAGEMENT
# =============================================================================
HEAT = {
    "C4":  0.0085,
    "CS4": 0.0085,
    "E4":  0.0085,
    "E7":  0.0085,
    "E13": 0.0085,
}
EXECUTION_LOOKBACK_HOURS = 48

# =============================================================================
# ROLL (equities only)
# =============================================================================
ROLL_ENABLED   = {"C4": False, "CS4": False, "E4": True, "E7": True, "E13": True}
ROLL_RSPOS_MIN = {"E4": 0.85, "E7": 0.85, "E13": 0.15}
# Reporting horizon for last_day countdown (held position warnings).
# Held positions whose last_day is within this many calendar days are
# surfaced in the run report so the operator can see roll/exit events
# coming. NOT used to auto-extend the daily fetch/process scope —
# the proper data-scope fix for roll-target indicators is open work.
ROLL_LOOKAHEAD_DAYS = 5

# =============================================================================
# ORDER PLACEMENT
# =============================================================================
LIMIT_OFFSET = 0.000  # Buffer for limit prices (percentage)

# =============================================================================
# DATA PROCESSING
# =============================================================================
INTRADAY_CUTOFF_HOUR = 6  # Hour defining trading day boundary for daily OHLC

# Indicators per system, in output column order: Sup/Res first, then RSpos
# (equity systems only — used by the roll-in filter), then the 4 features
# the system's model expects. Window suffix is the integer arg passed to
# the matching Indicators.* method.
INDICATORS = {
    "C4":  ["Sup_4",  "Res_4",             "VNS_4",  "sEMA_11", "nATR_13", "Mo_29"],
    "CS4": ["Sup_4",  "Res_4",             "VNS_4",  "sEMA_13", "sEMA_59", "VNS_79"],
    "E4":  ["Sup_4",  "Res_4",  "RSpos_4",  "VNS_4",  "Mo_17",   "VNS_7",   "nATR_59"],
    "E7":  ["Sup_7",  "Res_7",  "RSpos_7",  "VNS_7",  "sEMA_13", "Mo_79",   "nATR_43"],
    "E13": ["Sup_13", "Res_13", "RSpos_13", "VNS_13", "sEMA_23", "nATR_31", "VNS_79"],
}

# =============================================================================
# PREDICTIONS / ML
# =============================================================================
MODELS_DIR = Path(__file__).parent / "data" / "models"

# =============================================================================
# WILSON-SCORE THRESHOLD (replaces tau)
# =============================================================================
# Per-system precision target; threshold derived via Wilson lower-bound walkdown
# over the last LOOKBACK_WINDOW bars at confidence (1 - WILSON_ALPHA).
PRECISION = {
    "C4":  0.3202,
    "CS4": 0.2689,
    "E4":  0.3568,
    "E7":  0.4206,
    "E13": 0.4677,
}
WILSON_ALPHA = 0.20
LOOKBACK_WINDOW = 60
TARGET_MARGIN = 0.02  # Buy_B/Sell_A margin: long = (prev_close − sup) × this; short = (res − prev_close) × this. Mirrors data_pipeline.

# =============================================================================
# CROSS-SECTIONAL CLUSTER FILTER
# =============================================================================
# Each day, after per-product probabilities are produced, the system clusters
# its live universe by VNS_{SYSTEM_LABEL} (the seed/strength feature) using
# k-means, sorts cluster ids by centroid value (ascending), and fails the
# cluster gate for products whose cluster id is not in INCLUDE_CLUSTERS.
#
# N_CLUSTERS=None disables the filter for that system (E13).
N_CLUSTERS = {
    "C4":  3,
    "CS4": 4,
    "E4":  4,
    "E7":  4,
    "E13": None,
}
INCLUDE_CLUSTERS = {
    "C4":  {0, 2},
    "CS4": {0},
    "E4":  {3},
    "E7":  {3},
    "E13": None,
}
