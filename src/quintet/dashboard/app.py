"""Main Dash application factory."""

import os
from pathlib import Path

os.environ["PLOTLY_RENDERER"] = "browser"

from dash import Dash, page_container
import dash_bootstrap_components as dbc
import plotly.io as pio

pio.templates.default = "plotly_dark"


def create_app() -> Dash:
    pages_folder = Path(__file__).parent / "pages"

    app = Dash(
        __name__,
        use_pages=True,
        pages_folder=str(pages_folder),
        external_stylesheets=[dbc.themes.DARKLY],
        suppress_callback_exceptions=True,
        title="Quintet Dashboard",
    )

    app.layout = dbc.Container([page_container], fluid=True)

    return app


def main():
    app = create_app()
    app.run(debug=True, host="127.0.0.1", port=8050, dev_tools_ui=False)


if __name__ == "__main__":
    main()
