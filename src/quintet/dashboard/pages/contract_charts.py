"""Products page - contracts for the selected product within a group."""

import dash
from dash import Input, Output, callback, dcc, html
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

from quintet.dashboard.components.charts.contract_chart import create_contract_figure
from quintet.dashboard.components.controls.selectors import (
    ALL_GROUPS_VALUE,
    create_control_row,
)
from quintet.dashboard.config import CHART_CONFIG, PRODUCT_GROUPS
from quintet.dashboard.data.loader import (
    format_chart_title,
    get_contract_dates,
    get_contracts,
    get_symbols,
    load_contract,
)

dash.register_page(__name__, path="/product", name="Products", order=0)


def layout() -> dbc.Container:
    return dbc.Container(
        [
            create_control_row(),
            dbc.Spinner(html.Div(id="charts-container"), color="primary"),
        ],
        fluid=True,
        className="mt-4",
    )


def _symbols_in_group(group: str | None) -> list[str]:
    available = set(get_symbols())
    if not group or group == ALL_GROUPS_VALUE:
        return [s for _, members in PRODUCT_GROUPS for s in members if s in available]
    members = dict(PRODUCT_GROUPS).get(group, [])
    return [s for s in members if s in available]


@callback(
    Output("product-dropdown", "options"),
    Output("product-dropdown", "value"),
    Input("group-dropdown", "value"),
)
def update_product_options(group: str | None):
    symbols = _symbols_in_group(group)
    options = [{"label": s, "value": s} for s in symbols]
    value = symbols[0] if symbols else None
    return options, value


@callback(
    Output("charts-container", "children"),
    Input("product-dropdown", "value"),
)
def update_charts(product: str | None):
    if not product:
        return html.Div("No products available.", className="text-muted text-center mt-5")

    contracts = get_contracts(product)
    if not contracts:
        return html.Div(
            f"No contracts found for {product}.",
            className="text-muted text-center mt-5",
        )

    charts = [_create_chart_component(product, c) for c in contracts]
    charts = [c for c in charts if c is not None]
    if not charts:
        return html.Div("No data available.", className="text-muted text-center mt-5")
    return charts


def _create_chart_component(symbol: str, contract: str) -> html.Div:
    try:
        df = load_contract(symbol, contract)
        contract_dates = get_contract_dates(symbol, contract)
        title = format_chart_title(symbol, contract)
        fig = create_contract_figure(df=df, days=180, contract_dates=contract_dates)
        return html.Div(
            [
                html.H5(
                    title,
                    style={
                        "color": "#ccc",
                        "textAlign": "center",
                        "marginBottom": "10px",
                        "fontWeight": "500",
                    },
                ),
                dcc.Graph(figure=fig, config=CHART_CONFIG),
            ],
            className="mb-4",
        )
    except Exception as e:
        fig = go.Figure()
        fig.add_annotation(
            text=f"Error loading {contract}: {e}",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(size=16, color="red"),
        )
        fig.update_layout(height=200)
        return html.Div([dcc.Graph(figure=fig, config=CHART_CONFIG)], className="mb-4")
