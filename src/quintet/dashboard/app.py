"""Main Dash application factory."""

import os
from pathlib import Path

os.environ["PLOTLY_RENDERER"] = "browser"

import dash
from dash import Dash, html, page_container
import dash_bootstrap_components as dbc
import plotly.io as pio

pio.templates.default = "plotly_dark"


_INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>"""


def _build_navbar() -> dbc.Navbar:
    pages = sorted(
        (p for p in dash.page_registry.values() if p.get("path")),
        key=lambda p: p.get("order", 99),
    )
    nav_items = [
        dbc.NavItem(dbc.NavLink(p["name"], href=p["path"], active="exact"))
        for p in pages
    ]
    return dbc.Navbar(
        dbc.Container(
            [
                html.A(
                    "Quintet Dashboard",
                    href="/",
                    style={
                        "color": "#fff",
                        "fontWeight": 600,
                        "textDecoration": "none",
                        "marginRight": "24px",
                    },
                ),
                dbc.Nav(nav_items, navbar=True),
            ],
            fluid=True,
        ),
        color="dark",
        dark=True,
        className="mb-2",
    )


def create_app() -> Dash:
    pages_folder = Path(__file__).parent / "pages"

    app = Dash(
        __name__,
        use_pages=True,
        pages_folder=str(pages_folder),
        external_stylesheets=[dbc.themes.DARKLY],
        suppress_callback_exceptions=True,
        title="Quintet Dashboard",
        index_string=_INDEX_TEMPLATE,
    )

    app.layout = dbc.Container([_build_navbar(), page_container], fluid=True)

    return app


def main():
    app = create_app()
    app.run(debug=True, host="127.0.0.1", port=8050, dev_tools_ui=False)


if __name__ == "__main__":
    main()
