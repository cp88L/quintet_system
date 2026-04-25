"""Control components - dropdowns and selectors."""

from dash import dcc
import dash_bootstrap_components as dbc

from quintet.dashboard.config import (
    DATE_RANGE_OPTIONS,
    DEFAULT_DATE_RANGE,
    PRODUCT_GROUPS,
)
from quintet.dashboard.data.loader import get_product_info, get_symbols


def create_product_dropdown(id: str = "product-dropdown") -> dbc.Col:
    """Grouped product dropdown with disabled '── Group Name ──' headers."""
    symbols = set(get_symbols())
    options = []
    default = None

    for group_name, group_symbols in PRODUCT_GROUPS:
        available = [s for s in group_symbols if s in symbols]
        if not available:
            continue

        options.append({
            "label": f"── {group_name} ──",
            "value": f"_group_{group_name}",
            "disabled": True,
        })

        for s in available:
            info = get_product_info(s)
            long_name = info.get("longName", s)
            label = f"  {long_name} ({s})" if long_name != s else f"  {s}"
            options.append({"label": label, "value": s})
            if default is None:
                default = s

    return dbc.Col(
        [
            dbc.Label("Product", html_for=id),
            dcc.Dropdown(
                id=id,
                options=options,
                value=default,
                clearable=False,
                placeholder="Select product...",
                persistence=True,
                persistence_type="session",
            ),
        ],
        md=5,
    )


def create_system_filter_dropdown(id: str = "system-filter-dropdown") -> dbc.Col:
    """All / per-system overlay filter."""
    options = [{"label": "All", "value": "all"}]
    options.extend({"label": s, "value": s} for s in ("C4", "CS4", "E4", "E7", "E13"))

    return dbc.Col(
        [
            dbc.Label("System", html_for=id),
            dcc.Dropdown(
                id=id,
                options=options,
                value="all",
                clearable=False,
                persistence=True,
                persistence_type="session",
            ),
        ],
        md=3,
    )


def create_date_range_picker(id: str = "date-range-dropdown") -> dbc.Col:
    return dbc.Col(
        [
            dbc.Label("Date Range", html_for=id),
            dcc.Dropdown(
                id=id,
                options=DATE_RANGE_OPTIONS,
                value=DEFAULT_DATE_RANGE,
                clearable=False,
                persistence=True,
                persistence_type="session",
            ),
        ],
        md=2,
    )


def create_control_row() -> dbc.Row:
    return dbc.Row(
        [
            create_product_dropdown(),
            create_system_filter_dropdown(),
            create_date_range_picker(),
        ],
        className="mb-4",
    )
