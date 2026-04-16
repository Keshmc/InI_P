"""Reusable export helpers for compact page-level download actions."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
import json
from typing import Any
import zipfile

import streamlit as st


def render_export_downloads(
    sections: dict[str, list[dict[str, Any]]],
    file_stem: str,
    key_prefix: str,
    caption: str = "Download the current results in a compact export bundle.",
) -> None:
    """Render compact CSV, JSON, and Excel download buttons for export sections."""
    csv_zip_bytes = _build_csv_zip_bytes(sections)
    json_bytes = json.dumps(sections, ensure_ascii=True, indent=2).encode("utf-8")
    excel_bytes, excel_error = _build_excel_bytes(sections)

    st.caption(caption)
    col_csv, col_json, col_excel = st.columns(3)
    with col_csv:
        st.download_button(
            "CSV (ZIP)",
            data=csv_zip_bytes,
            file_name=f"{file_stem}_tables.zip",
            mime="application/zip",
            key=f"{key_prefix}_csv",
            width="stretch",
        )
    with col_json:
        st.download_button(
            "JSON",
            data=json_bytes,
            file_name=f"{file_stem}_tables.json",
            mime="application/json",
            key=f"{key_prefix}_json",
            width="stretch",
        )
    with col_excel:
        st.download_button(
            "Excel",
            data=excel_bytes or b"",
            file_name=f"{file_stem}_tables.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            disabled=excel_bytes is None,
            key=f"{key_prefix}_excel",
            width="stretch",
        )

    if excel_error:
        st.caption(excel_error)


def build_export_file_stem(prefix: str, parts: list[str] | None = None) -> str:
    """Build a filesystem-safe export filename stem with a UTC timestamp."""
    clean_parts: list[str] = []
    for value in parts or []:
        normalized = "".join(ch if ch.isalnum() else "_" for ch in str(value).strip())[:40].strip("_")
        if normalized:
            clean_parts.append(normalized)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if clean_parts:
        return f"{prefix}_{'_'.join(clean_parts)}_{timestamp}"
    return f"{prefix}_{timestamp}"


def to_export_cell(value: Any) -> Any:
    """Convert nested structures to stable JSON strings for exports."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    return value


def _build_csv_zip_bytes(sections: dict[str, list[dict[str, Any]]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, rows in sections.items():
            archive.writestr(f"{name}.csv", _rows_to_csv_text(rows))
    return buffer.getvalue()


def _rows_to_csv_text(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""

    fieldnames: list[str] = list(rows[0].keys())
    for row in rows[1:]:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: to_export_cell(row.get(key)) for key in fieldnames})
    return output.getvalue()


def _build_excel_bytes(sections: dict[str, list[dict[str, Any]]]) -> tuple[bytes | None, str | None]:
    try:
        import pandas as pd  # type: ignore[import-not-found]
    except ImportError:
        return None, "Excel export is unavailable until `pandas` and `openpyxl` are installed."

    buffer = io.BytesIO()
    try:
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            for name, rows in sections.items():
                dataframe = pd.DataFrame(rows)
                if dataframe.empty:
                    dataframe = pd.DataFrame([{}])
                dataframe.to_excel(writer, sheet_name=name[:31], index=False)
    except Exception as exc:  # noqa: BLE001
        return None, f"Excel export failed: {exc}"
    return buffer.getvalue(), None
