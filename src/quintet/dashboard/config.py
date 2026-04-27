"""Dashboard configuration - colors, chart settings, and UI options."""

# =============================================================================
# COLORS - Support/Resistance
# =============================================================================
SUPPORT_COLOR = "darkred"
RESISTANCE_COLOR = "darkgreen"

# =============================================================================
# COLORS - Vertical Lines
# =============================================================================
SCAN_START_COLOR = "rgba(150, 150, 150, 0.6)"
SCAN_END_COLOR = "rgba(150, 150, 150, 0.6)"
LAST_DAY_COLOR = "rgba(150, 150, 150, 0.8)"

# =============================================================================
# COLORS - OHLC
# =============================================================================
OHLC_INCREASING = "#26A69A"  # Green
OHLC_DECREASING = "#EF5350"  # Red

# =============================================================================
# CHART LAYOUT
# =============================================================================
CHART_HEIGHT = 800
SUBPLOT_ROW_HEIGHTS = [0.75, 0.25]

CHART_CONFIG = {
    "displaylogo": False,
    "displayModeBar": True,
    "modeBarButtonsToRemove": [
        "lasso2d",
        "select2d",
        "zoomIn2d",
        "zoomOut2d",
        "resetScale2d",
        "hoverClosestCartesian",
        "sendDataToCloud",
        "toImage",
        "editInChartStudio",
    ],
    "scrollZoom": True,
    "showLink": False,
    "linkText": "",
    "showEditInChartStudio": False,
    "showSendToCloud": False,
    "plotlyServerURL": "",
    "editable": False,
    "staticPlot": False,
}

# =============================================================================
# MONTH CODES
# =============================================================================
MONTH_CODES = {
    "F": "January",
    "G": "February",
    "H": "March",
    "J": "April",
    "K": "May",
    "M": "June",
    "N": "July",
    "Q": "August",
    "U": "September",
    "V": "October",
    "X": "November",
    "Z": "December",
}

# =============================================================================
# PRODUCT GROUPS - all 63 active quintet products
# =============================================================================
PRODUCT_GROUPS = [
    ("CME Metals", ["GC", "HG", "PA", "PL", "SI"]),
    ("LME Metals", ["CA", "NI", "PB", "SNLME", "ZSLME"]),
    ("Energy", ["CL", "RB", "HO", "COIL", "GOIL"]),
    ("Equity Indices", ["ES", "NQ", "RTY", "YM", "NKD", "SIXM", "IXR", "SIXT", "IXE", "IXY", "IXV", "IXI", "IXU", "SIXRE", "IXB", "XAZ"]),
    ("Crypto", ["BRR", "ETHUSDRR"]),
    ("Softs", ["CC", "CT", "KC", "D", "W", "OJ", "SB", "LBR"]),
    ("Grains", ["ZL", "ZC", "KE", "ZO", "ZR", "ZS", "ZM", "ZW"]),
    ("Meat and Dairy", ["CSC", "DA", "GF", "LE", "HE"]),
    ("Asia", ["SCI", "TSR20", "XINA50"]),
    ("FX", ["DX"]),
    ("Rates", ["SR3", "ZB", "ZF", "ZN", "ZT"]),
]
