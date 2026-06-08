"""Reusable Vega-Lite chart helpers for the news analyzer view layer."""

from __future__ import annotations

from typing import Any

import streamlit as st

_SENTIMENT_DOMAIN = ["Positive", "Neutral", "Negative"]
_SENTIMENT_RANGE = ["#1e8449", "#f4d03f", "#c0392b"]


def render_sentiment_donut(
    rows: list[dict[str, Any]],
    legend_title: str = "Label",
    empty_message: str = "No sentiment data yet.",
) -> None:
    """Render a sentiment-distribution donut with percent labels and zero-slice guard.

    Filters out zero-count slices (Vega-Lite arc distorts with zero values) and
    bails to a friendly info message when the total count is zero.
    """
    cleaned = [
        {"label": str(item.get("label", "")).strip(), "count": int(item.get("count", 0))}
        for item in rows
        if isinstance(item, dict) and int(item.get("count", 0)) > 0
    ]
    total = sum(item["count"] for item in cleaned)

    if total <= 0:
        st.info(empty_message, icon="📊")
        return

    enriched = [
        {
            "label": item["label"],
            "count": item["count"],
            "percent": round(item["count"] / total * 100.0, 1),
        }
        for item in cleaned
    ]

    color_encoding = {
        "field": "label",
        "type": "nominal",
        "scale": {"domain": _SENTIMENT_DOMAIN, "range": _SENTIMENT_RANGE},
        "legend": {"title": legend_title, "orient": "right"},
    }

    spec = {
        "height": 280,
        "view": {"stroke": None},
        "layer": [
            {
                "mark": {
                    "type": "arc",
                    "innerRadius": 60,
                    "outerRadius": 110,
                    "stroke": "#ffffff",
                    "strokeWidth": 2,
                },
                "encoding": {
                    "theta": {"field": "count", "type": "quantitative", "stack": True},
                    "color": color_encoding,
                    "tooltip": [
                        {"field": "label", "type": "nominal", "title": "Label"},
                        {"field": "count", "type": "quantitative", "title": "Articles"},
                        {"field": "percent", "type": "quantitative", "title": "Share %"},
                    ],
                },
            },
            {
                "mark": {
                    "type": "text",
                    "radius": 135,
                    "fontSize": 12,
                    "fontWeight": 600,
                    "fill": "#1f2937",
                },
                "encoding": {
                    "theta": {"field": "count", "type": "quantitative", "stack": True},
                    "text": {"field": "count", "type": "quantitative", "format": "d"},
                },
            },
        ],
    }

    st.vega_lite_chart(enriched, spec, width="stretch")
