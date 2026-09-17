"""Build the customer-alert audit report in JSON, XLSX or PDF.

The report contains every customer whose retention offer was *flagged for
audit* (cost above the policy threshold). It is the artefact a human auditor
reviews after the workflow has processed 100% of the portfolio automatically.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_REPORT_TITLE = "Informe de Alertas — Retención de Clientes"
_PDF_COLUMNS = [
    ("customer_id", "Cliente"),
    ("risk_level", "Riesgo"),
    ("churn_probability", "P(churn)"),
    ("clv", "CLV"),
    ("offer_name", "Oferta"),
    ("offer_cost", "Costo"),
    ("roi", "ROI"),
]


def _timestamp() -> str:
    """Return an ISO-8601 UTC timestamp for the report header."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def build_json_report(rows: list[dict[str, Any]]) -> bytes:
    """Serialise the alert rows as a pretty-printed JSON document.

    Args:
        rows: Alert rows produced by ``reporting.alerted_rows``.

    Returns:
        UTF-8 encoded JSON bytes.
    """
    document = {
        "report": _REPORT_TITLE,
        "generated_at": _timestamp(),
        "alert_count": len(rows),
        "alerts": rows,
    }
    return json.dumps(document, indent=2, ensure_ascii=False).encode("utf-8")


def build_xlsx_report(rows: list[dict[str, Any]]) -> bytes:
    """Serialise the alert rows as a formatted Excel workbook.

    Args:
        rows: Alert rows produced by ``reporting.alerted_rows``.

    Returns:
        The ``.xlsx`` file content as bytes.
    """
    frame = pd.DataFrame(rows)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="alertas", index=False)
        sheet = writer.sheets["alertas"]
        sheet.freeze_panes = "A2"
        for column_cells in sheet.columns:
            width = max(len(str(c.value or "")) for c in column_cells) + 2
            sheet.column_dimensions[column_cells[0].column_letter].width = min(width, 40)
    return buffer.getvalue()


def build_pdf_report(rows: list[dict[str, Any]]) -> bytes:
    """Render the alert rows as a landscape PDF with a summary header.

    Args:
        rows: Alert rows produced by ``reporting.alerted_rows``.

    Returns:
        The PDF file content as bytes.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
    )
    styles = getSampleStyleSheet()
    story: list[Any] = [
        Paragraph(_REPORT_TITLE, styles["Title"]),
        Paragraph(
            f"Generado: {_timestamp()} · Alertas: {len(rows)}",
            styles["Normal"],
        ),
        Spacer(1, 14),
    ]

    if not rows:
        story.append(Paragraph("No hay alertas en este lote.", styles["Normal"]))
    else:
        header = [label for _, label in _PDF_COLUMNS]
        body = [[_format_cell(row.get(key, "")) for key, _ in _PDF_COLUMNS] for row in rows]
        table = Table([header] + body, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a2b4a")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8d2e0")),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#f2f6fb")],
                    ),
                    ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(table)

    doc.build(story)
    return buffer.getvalue()


def _format_cell(value: Any) -> str:
    """Format a cell value for the PDF table."""
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def build_alert_report(rows: list[dict[str, Any]], fmt: str) -> bytes:
    """Build the alert report in the requested format.

    Args:
        rows: Alert rows produced by ``reporting.alerted_rows``.
        fmt: One of ``"json"``, ``"xlsx"`` or ``"pdf"``.

    Returns:
        The report file content as bytes.

    Raises:
        ValueError: If ``fmt`` is not one of the supported formats.
    """
    builders = {
        "json": build_json_report,
        "xlsx": build_xlsx_report,
        "pdf": build_pdf_report,
    }
    if fmt not in builders:
        raise ValueError(f"unsupported format '{fmt}'; use json, xlsx or pdf")
    return builders[fmt](rows)
