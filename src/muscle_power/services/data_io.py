"""CSV/Excel import-export and PDF report generation."""
from __future__ import annotations

import hashlib
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from fpdf import FPDF

from muscle_power.utils.errors import DataImportError, ExportError
from muscle_power.utils.logger import get_logger, log_action

_log = get_logger(__name__)

NUMERIC_FIELDS = {"avg_power", "peak_power", "duration_seconds", "fatigue_index"}
SESSION_COLUMNS = [
    "date", "muscle_group", "sensor_id", "duration_seconds",
    "avg_power", "peak_power", "fatigue_index", "rep_count", "notes",
]


def _session_hash(s: dict[str, Any]) -> str:
    key = f"{s.get('date')}|{s.get('muscle_group')}|{s.get('avg_power')}|{s.get('peak_power')}"
    return hashlib.md5(key.encode()).hexdigest()  # noqa: S324 — dedup only, not security


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export_sessions_csv(sessions: list[dict[str, Any]], filepath: str | Path) -> None:
    """Export sessions to a UTF-8-BOM CSV file (Excel compatible)."""
    fp = Path(filepath)
    try:
        pd.DataFrame(sessions).to_csv(fp, index=False, encoding="utf-8-sig")
        log_action(_log, "export_csv", {"rows": len(sessions), "path": str(fp)})
    except PermissionError as exc:
        raise ExportError(
            "Cannot write to file — it may be open in Excel. Close the file and try again."
        ) from exc
    except OSError as exc:
        if getattr(exc, "errno", 0) == 28 or "disk" in str(exc).lower():
            raise ExportError(
                "Cannot save session — disk is full. Free up space and try again."
            ) from exc
        raise ExportError(f"Export failed: {exc}") from exc


def export_sessions_excel(sessions: list[dict[str, Any]], filepath: str | Path) -> None:
    """Export sessions to Excel (.xlsx)."""
    fp = Path(filepath)
    try:
        with pd.ExcelWriter(fp, engine="openpyxl") as writer:
            pd.DataFrame(sessions).to_excel(writer, sheet_name="Sessions", index=False)
        log_action(_log, "export_excel", {"rows": len(sessions), "path": str(fp)})
    except PermissionError as exc:
        raise ExportError("Cannot write Excel file — it may be open. Close and try again.") from exc
    except OSError as exc:
        raise ExportError(f"Excel export failed: {exc}") from exc


def export_sessions_pdf(
    sessions: list[dict[str, Any]],
    filepath: str | Path,
    title: str = "Muscle Power - Workout Session Report",
) -> None:
    """Generate a PDF summary report."""
    fp = Path(filepath)
    pdf = FPDF()
    pdf.set_margins(15, 15, 15)
    pdf.add_page()

    # Title
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0, 6,
        f"Generated: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        new_x="LMARGIN", new_y="NEXT", align="C",
    )
    pdf.ln(6)

    # Table
    col_w = [42, 28, 24, 24, 24, 16]
    headers = ["Date", "Muscle Group", "Duration(s)", "Avg Power", "Peak Power", "Reps"]
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(228, 0, 43)
    pdf.set_text_color(255, 255, 255)
    for w, h in zip(col_w, headers):
        pdf.cell(w, 8, h, border=1, fill=True)
    pdf.ln()

    pdf.set_text_color(26, 26, 46)
    fill = False
    for sess in sessions:
        pdf.set_font("Helvetica", "", 8)
        if fill:
            pdf.set_fill_color(245, 245, 247)
        else:
            pdf.set_fill_color(255, 255, 255)
        values = [
            str(sess.get("date", ""))[:19],
            str(sess.get("muscle_group", "")),
            f"{sess['duration_seconds']:.0f}" if sess.get("duration_seconds") is not None else "—",
            f"{sess['avg_power']:.5f}" if sess.get("avg_power") is not None else "—",
            f"{sess['peak_power']:.5f}" if sess.get("peak_power") is not None else "—",
            str(sess.get("rep_count", "—")),
        ]
        for w, v in zip(col_w, values):
            pdf.cell(w, 7, str(v)[:22], border=1, fill=True)
        pdf.ln()
        fill = not fill

    try:
        pdf.output(str(fp))
        log_action(_log, "export_pdf", {"rows": len(sessions), "path": str(fp)})
    except PermissionError as exc:
        raise ExportError("Cannot write PDF file — check file permissions.") from exc
    except OSError as exc:
        raise ExportError(f"PDF export failed: {exc}") from exc


def get_export_bytes(sessions: list[dict[str, Any]], fmt: str = "csv") -> bytes:
    """Return exported content as bytes suitable for st.download_button."""
    with tempfile.TemporaryDirectory() as tmp:
        fp = Path(tmp) / f"muscle_power_export.{fmt}"
        dispatch = {
            "csv": export_sessions_csv,
            "xlsx": export_sessions_excel,
            "pdf": export_sessions_pdf,
        }
        fn = dispatch.get(fmt)
        if fn is None:
            raise ExportError(f"Unsupported format: {fmt}")
        fn(sessions, fp)
        return fp.read_bytes()


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def import_sessions_csv(
    filepath: str | Path,
    deduplicate: bool = True,
) -> list[dict[str, Any]]:
    """Import sessions from a CSV file with validation and optional deduplication."""
    fp = Path(filepath)
    try:
        df = pd.read_csv(fp, encoding="utf-8-sig")
    except Exception as exc:
        raise DataImportError(f"Cannot read CSV file: {exc}") from exc

    errors: list[str] = []
    valid_rows: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()

    for row_idx, row in df.iterrows():
        row_num = int(row_idx) + 2  # 1-based + header
        row_dict = row.where(row.notna(), None).to_dict()

        # Validate timestamp
        date_val = row_dict.get("date")
        if not date_val:
            errors.append(f"Row {row_num}: missing 'date' field")
            continue
        try:
            datetime.fromisoformat(str(date_val))
        except ValueError:
            errors.append(f"Row {row_num}: invalid date format '{date_val}'")
            continue

        # Validate numeric fields
        row_ok = True
        for field in NUMERIC_FIELDS:
            val = row_dict.get(field)
            if val is not None and val != "":
                try:
                    row_dict[field] = float(val)
                except (ValueError, TypeError):
                    errors.append(f"Row {row_num}: '{field}' must be numeric, got '{val}'")
                    row_ok = False
        if not row_ok:
            continue

        # Duplicate detection
        h = _session_hash(row_dict)
        if deduplicate and h in seen_hashes:
            continue
        seen_hashes.add(h)
        valid_rows.append(row_dict)

    if errors:
        log_action(_log, "import_csv_errors", {"count": len(errors), "sample": errors[:5]}, level="WARN")
    log_action(_log, "import_csv", {
        "imported": len(valid_rows),
        "skipped": len(df) - len(valid_rows),
        "errors": len(errors),
    })
    return valid_rows


def import_sessions_excel(filepath: str | Path, *, deduplicate: bool = True) -> list[dict[str, Any]]:
    """Import sessions from an Excel file."""
    fp = Path(filepath)
    try:
        df = pd.read_excel(fp, engine="openpyxl")
    except Exception as exc:
        raise DataImportError(f"Cannot read Excel file: {exc}") from exc
    # Reuse CSV validation pipeline via temp CSV
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w", encoding="utf-8-sig") as tmp:
        df.to_csv(tmp, index=False)
        tmp_path = tmp.name
    return import_sessions_csv(tmp_path, deduplicate=deduplicate)
