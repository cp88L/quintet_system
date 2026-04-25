"""Contract Charts page - one chart per contract for the selected product."""

import dash
from dash import Input, Output, callback, dcc, html
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

from quintet.dashboard.components.charts.contract_chart import create_contract_figure
from quintet.dashboard.components.controls.selectors import create_control_row
from quintet.dashboard.config import CHART_CONFIG
from quintet.dashboard.data.loader import (
    format_chart_title,
    get_contract_dates,
    get_contracts,
    load_contract,
)

dash.register_page(__name__, path="/", name="Contract Charts", order=0)


def layout() -> dbc.Container:
    return dbc.Container(
        [
            create_control_row(),
            dbc.Spinner(html.Div(id="charts-container"), color="primary"),
        ],
        fluid=True,
        className="mt-4",
    )


@callback(
    Output("charts-container", "children"),
    Input("product-dropdown", "value"),
    Input("system-filter-dropdown", "value"),
    Input("date-range-dropdown", "value"),
)
def update_charts(product: str | None, system_filter: str, days: int):
    if not product:
        return html.Div("Select a product.", className="text-muted text-center mt-5")

    contracts = get_contracts(product)
    if not contracts:
        return html.Div(
            f"No contracts found for {product}.",
            className="text-muted text-center mt-5",
        )

    charts = []
    for contract in contracts:
        chart = _create_chart_component(product, contract, days, system_filter)
        if chart is not None:
            charts.append(chart)

    if not charts:
        return html.Div("No data available.", className="text-muted text-center mt-5")

    return charts


def _create_chart_component(
    symbol: str, contract: str, days: int, system_filter: str = "all"
) -> html.Div:
    try:
        df = load_contract(symbol, contract)
        contract_dates = get_contract_dates(symbol, contract)
        title = format_chart_title(symbol, contract)
        fig = create_contract_figure(
            df=df,
            days=days,
            contract_dates=contract_dates,
            system_filter=system_filter,
        )
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
