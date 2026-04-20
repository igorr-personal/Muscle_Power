"""Tests for data_io.py."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from muscle_power.services.data_io import (
    export_sessions_csv,
    export_sessions_excel,
    export_sessions_pdf,
    get_export_bytes,
    import_sessions_csv,
)
from muscle_power.utils.errors import DataImportError, ExportError


SAMPLE_SESSIONS = [
    {
        "date": "2025-01-01T10:00:00",
        "muscle_group": "biceps",
        "sensor_id": "AA:BB:CC:DD:EE:FF",
        "duration_seconds": 300,
        "avg_power": 0.75,
        "peak_power": 1.2,
        "fatigue_index": 0.12,
        "rep_count": 8,
        "notes": "",
    },
    {
        "date": "2025-01-02T11:00:00",
        "muscle_group": "triceps/rear deltoid",
        "sensor_id": "AA:BB:CC:DD:EE:FF",
        "duration_seconds": 600,
        "avg_power": 0.55,
        "peak_power": 0.9,
        "fatigue_index": 0.20,
        "rep_count": 12,
        "notes": "felt tired",
    },
]

DUPLICATE_SESSIONS = [
    *SAMPLE_SESSIONS,
    {  # exact duplicate of first row
        "date": "2025-01-01T10:00:00",
        "muscle_group": "biceps",
        "sensor_id": "AA:BB:CC:DD:EE:FF",
        "duration_seconds": 300,
        "avg_power": 0.75,
        "peak_power": 1.2,
        "fatigue_index": 0.12,
        "rep_count": 8,
        "notes": "",
    },
]


class TestCSVExportImport:
    def test_export_creates_file(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            export_sessions_csv(SAMPLE_SESSIONS, path)
            assert Path(path).exists()
            assert Path(path).stat().st_size > 0
        finally:
            os.unlink(path)

    def test_import_roundtrip(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            export_sessions_csv(SAMPLE_SESSIONS, path)
            imported = import_sessions_csv(path, deduplicate=False)
            assert len(imported) == len(SAMPLE_SESSIONS)
            assert imported[0]["muscle_group"] == "biceps"
            assert imported[1]["muscle_group"] == "triceps/rear deltoid"
        finally:
            os.unlink(path)

    def test_deduplication_removes_exact_duplicates(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            export_sessions_csv(DUPLICATE_SESSIONS, path)
            imported = import_sessions_csv(path, deduplicate=True)
            assert len(imported) == 2
        finally:
            os.unlink(path)

    def test_special_chars_in_muscle_group(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            export_sessions_csv(SAMPLE_SESSIONS, path)
            imported = import_sessions_csv(path)
            muscle_groups = [r["muscle_group"] for r in imported]
            assert "triceps/rear deltoid" in muscle_groups
        finally:
            os.unlink(path)

    def test_import_invalid_date_skipped(self):
        bad = [
            {
                "date": "not-a-date",
                "muscle_group": "biceps",
                "avg_power": 0.5,
                "peak_power": 1.0,
            }
        ]
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            import csv
            writer = csv.DictWriter(f, fieldnames=bad[0].keys())
            writer.writeheader()
            writer.writerows(bad)
            path = f.name
        try:
            imported = import_sessions_csv(path)
            assert len(imported) == 0
        finally:
            os.unlink(path)

    def test_import_non_numeric_power_skipped(self):
        bad_csv = "date,muscle_group,avg_power,peak_power\n"
        bad_csv += "2025-01-01T10:00:00,biceps,NOT_A_NUMBER,1.0\n"
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            f.write(bad_csv)
            path = f.name
        try:
            imported = import_sessions_csv(path)
            assert len(imported) == 0
        finally:
            os.unlink(path)

    def test_import_file_not_found(self):
        with pytest.raises(DataImportError):
            import_sessions_csv("/nonexistent/path/file.csv")


class TestExcelExport:
    def test_export_creates_xlsx(self):
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            path = f.name
        try:
            export_sessions_excel(SAMPLE_SESSIONS, path)
            assert Path(path).exists()
            assert Path(path).stat().st_size > 100
        finally:
            os.unlink(path)


class TestPDFExport:
    def test_export_creates_pdf(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name
        try:
            export_sessions_pdf(SAMPLE_SESSIONS, path)
            assert Path(path).exists()
            assert Path(path).stat().st_size > 100
            # Check PDF magic bytes
            with open(path, "rb") as f:
                assert f.read(4) == b"%PDF"
        finally:
            os.unlink(path)


class TestGetExportBytes:
    def test_csv_bytes(self):
        data = get_export_bytes(SAMPLE_SESSIONS, fmt="csv")
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_xlsx_bytes(self):
        data = get_export_bytes(SAMPLE_SESSIONS, fmt="xlsx")
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_pdf_bytes(self):
        data = get_export_bytes(SAMPLE_SESSIONS, fmt="pdf")
        assert isinstance(data, bytes)
        assert data[:4] == b"%PDF"

    def test_unsupported_format_raises(self):
        with pytest.raises(ExportError, match="Unsupported format"):
            get_export_bytes(SAMPLE_SESSIONS, fmt="xyz")
