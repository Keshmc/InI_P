"""Sentiment score visualization helpers."""

from __future__ import annotations

import streamlit as st


def render_sentiment_meter(score: float) -> None:
    """Render sentiment score from -1 to +1 on a red-to-green scale."""
    clamped = max(-1.0, min(1.0, float(score)))
    marker_left = ((clamped + 1.0) / 2.0) * 100.0

    st.markdown(
        """
        <style>
        .sentiment-wrap {
            border: 1px solid #dcdcdc;
            border-radius: 12px;
            padding: 14px 14px 8px 14px;
            background: #ffffff;
        }
        .sentiment-scale {
            position: relative;
            width: 100%;
            height: 22px;
            border-radius: 999px;
            background: linear-gradient(90deg, #c0392b 0%, #f39c12 45%, #f4d03f 50%, #58d68d 65%, #1e8449 100%);
        }
        .sentiment-marker {
            position: absolute;
            top: -5px;
            width: 3px;
            height: 32px;
            border-radius: 8px;
            background: #111111;
            transform: translateX(-50%);
        }
        .sentiment-labels {
            margin-top: 8px;
            display: flex;
            justify-content: space-between;
            font-size: 0.85rem;
            color: #555555;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        (
            "<div class='sentiment-wrap'>"
            "<div class='sentiment-scale'>"
            f"<div class='sentiment-marker' style='left:{marker_left:.2f}%'></div>"
            "</div>"
            "<div class='sentiment-labels'>"
            "<span>-1.0 (negative)</span>"
            "<span>0.0 (neutral)</span>"
            "<span>+1.0 (positive)</span>"
            "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
