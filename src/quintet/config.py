"""Quintet trading system configuration.

All configuration values centralized here, organized by functional group.
"""

from pathlib import Path

# =============================================================================
# IBKR CONNECTION
# =============================================================================
HOST = "127.0.0.1"
PORT = 4002
CLIENT_ID = 0
CONTRACT_DETAILS_TIMEOUT = 5

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

# =============================================================================
# ORDER PLACEMENT
# =============================================================================
LIMIT_OFFSET = 0.000  # Buffer for limit prices (percentage)

# =============================================================================
# DATA PROCESSING
# =============================================================================
INTRADAY_CUTOFF_HOUR = 6  # Hour defining trading day boundary for daily OHLC

# Indicators per system, in output column order: Sup/Res first, then the 4
# features the system's model expects. Window suffix is the integer arg
# passed to the matching Indicators.* method.
INDICATORS = {
    "C4":  ["Sup_4",  "Res_4",  "VNS_4",  "sEMA_11", "nATR_13", "Mo_29"],
    "CS4": ["Sup_4",  "Res_4",  "VNS_4",  "sEMA_13", "sEMA_59", "VNS_79"],
    "E4":  ["Sup_4",  "Res_4",  "VNS_4",  "Mo_17",   "VNS_7",   "nATR_59"],
    "E7":  ["Sup_7",  "Res_7",  "VNS_7",  "sEMA_13", "Mo_79",   "nATR_43"],
    "E13": ["Sup_13", "Res_13", "VNS_13", "sEMA_23", "nATR_31", "VNS_79"],
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

# =============================================================================
# IB ERROR CODES
# =============================================================================
# Error codes that indicate broker rejection (not user action)
IB_BROKER_REJECTION_CODES = {
    103,  # Order rejected - duplicate order
    104,  # Order rejected - cannot modify a filled order
    201,  # Order rejected - no trading permission (compliance)
    202,  # Order cancelled
}

# Non-error status messages to suppress
IB_INFO_CODES = {2104, 2106, 2158}  # Market data farm connected messages
