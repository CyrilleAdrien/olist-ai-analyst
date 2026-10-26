"""Pick a chart for a query result, without asking the LLM: the shape of the data decides.

- one row: no chart, the answer quotes the figure;
- a date column then a number: a line over time;
- a label (state, category, flag) then a number: horizontal bars, largest first, top 20;
- anything else: no chart, the table is enough.

Only the first numeric column is drawn: two measures never share one axis.
"""

import datetime as dt
from decimal import Decimal
from typing import Any

import plotly.graph_objects as go

BLUE = "#2a78d6"
INK = "#0b0b0b"
INK_QUIET = "#52514e"
GRID = "#e8e7e3"
SURFACE = "#fcfcfb"
MAX_BARS = 20


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float | Decimal) and not isinstance(value, bool)


def _is_date(value: Any) -> bool:
    return isinstance(value, dt.date)


def _title(name: str) -> str:
    return name.replace("_", " ").capitalize()


def _layout(fig: go.Figure, title: str) -> go.Figure:
    fig.update_layout(
        title={"text": title, "font": {"size": 16, "color": INK}, "x": 0, "xanchor": "left"},
        plot_bgcolor=SURFACE,
        paper_bgcolor=SURFACE,
        font={"family": "system-ui, sans-serif", "size": 13, "color": INK_QUIET},
        margin={"l": 16, "r": 24, "t": 56, "b": 16},
        hoverlabel={"bgcolor": "white", "font": {"color": INK}},
        showlegend=False,
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False, automargin=True)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, automargin=True)
    return fig


def make_chart(columns: list[str], rows: list[tuple[Any, ...]]) -> go.Figure | None:
    if len(rows) < 2 or len(columns) < 2:
        return None
    first = [row[0] for row in rows]
    measure = next(
        (i for i in range(1, len(columns)) if all(_is_number(row[i]) for row in rows)), None
    )
    if measure is None or any(v is None for v in first):
        return None
    values = [float(row[measure]) for row in rows]
    title = f"{_title(columns[measure])} by {_title(columns[0]).lower()}"

    if all(_is_date(v) for v in first):
        points = sorted(zip(first, values, strict=True))
        fig = go.Figure(
            go.Scatter(
                x=[p[0] for p in points],
                y=[p[1] for p in points],
                mode="lines+markers",
                line={"color": BLUE, "width": 2},
                marker={"size": 8, "color": BLUE},
                hovertemplate="%{x|%b %Y}<br>%{y:,.2f}<extra></extra>",
            )
        )
        fig.update_yaxes(rangemode="tozero")
        return _layout(fig, title)

    if all(isinstance(v, str | bool) for v in first):
        bars = sorted(zip(first, values, strict=True), key=lambda p: p[1], reverse=True)
        bars = bars[:MAX_BARS][::-1]  # plotly draws the first bar at the bottom
        labels = [("oui" if v else "non") if isinstance(v, bool) else v for v, _ in bars]
        fig = go.Figure(
            go.Bar(
                x=[v for _, v in bars],
                y=labels,
                orientation="h",
                marker={"color": BLUE, "cornerradius": 4},
                hovertemplate="%{y}<br>%{x:,.2f}<extra></extra>",
            )
        )
        fig.update_layout(height=max(320, 28 * len(bars) + 96), bargap=0.25)
        fig.update_yaxes(type="category", gridcolor=SURFACE)
        return _layout(fig, title)

    return None
