"""Control components - dropdowns and selectors."""

import dash_bootstrap_components as dbc

from quintet.dashboard.config import PRODUCT_GROUPS

ALL_GROUPS_VALUE = "_all"


def create_group_dropdown(id: str = "group-dropdown") -> dbc.Col:
    """Product-group selector: 'All' plus each group from PRODUCT_GROUPS.

    Uses dbc.Select (native <select> with Bootstrap `form-select`) so it
    inherits the DARKLY theme. dcc.Dropdown won't — Dash 4's redesigned
    dropdown no longer emits the `.Select-*` classes that the dbc-team
    `dash-bootstrap-css` stylesheet targets.
    """
    options = [{"label": "All", "value": ALL_GROUPS_VALUE}]
    options.extend({"label": name, "value": name} for name, _ in PRODUCT_GROUPS)

    return dbc.Col(
        [
            dbc.Label("Group", html_for=id),
            dbc.Select(
                id=id,
                options=options,
                value=ALL_GROUPS_VALUE,
                persistence=True,
                persistence_type="session",
            ),
        ],
        md=4,
    )


def create_product_dropdown(id: str = "product-dropdown") -> dbc.Col:
    """Product selector. Options/default are populated by the page callback
    based on the current group selection."""
    return dbc.Col(
        [
            dbc.Label("Product", html_for=id),
            dbc.Select(id=id, options=[], value=None),
        ],
        md=4,
    )


def create_control_row() -> dbc.Row:
    return dbc.Row(
        [create_group_dropdown(), create_product_dropdown()],
        className="mb-4",
    )
