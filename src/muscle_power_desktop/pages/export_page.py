"""Export / Import page for the desktop app."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QGroupBox, QFileDialog,
    QMessageBox, QAbstractItemView, QCheckBox,
)

from muscle_power_desktop.app import AppState
from muscle_power.services.data_io import (
    export_sessions_csv,
    export_sessions_excel,
    export_sessions_pdf,
    import_sessions_csv,
    import_sessions_excel,
)
from muscle_power.utils.errors import ExportError, DataImportError


class ExportPage(QWidget):
    """Export sessions to CSV / Excel / PDF; import from CSV / Excel."""

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__(parent)
        self._state = state
        self._sessions: list[dict] = []
        self._build_ui()
        self._load_sessions()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        title = QLabel("📁 Export & Import")
        title.setObjectName("titleLabel")
        root.addWidget(title)

        # ── Export section ─────────────────────────────────────────────
        export_box = QGroupBox("Export Sessions")
        exp_layout = QVBoxLayout(export_box)

        exp_layout.addWidget(QLabel(
            "Select sessions to export (Ctrl+Click for multiple, or select none to export all):"
        ))

        self._session_list = QListWidget()
        self._session_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._session_list.setMinimumHeight(160)
        exp_layout.addWidget(self._session_list)

        btn_row = QHBoxLayout()
        self._csv_btn = QPushButton("💾 Export CSV")
        self._csv_btn.clicked.connect(self._on_export_csv)
        btn_row.addWidget(self._csv_btn)

        self._excel_btn = QPushButton("📊 Export Excel")
        self._excel_btn.clicked.connect(self._on_export_excel)
        btn_row.addWidget(self._excel_btn)

        self._pdf_btn = QPushButton("📄 Export PDF")
        self._pdf_btn.clicked.connect(self._on_export_pdf)
        btn_row.addWidget(self._pdf_btn)

        btn_row.addStretch()
        exp_layout.addLayout(btn_row)

        refresh_btn = QPushButton("🔄 Refresh list")
        refresh_btn.clicked.connect(self._load_sessions)
        exp_layout.addWidget(refresh_btn)

        root.addWidget(export_box)

        # ── Import section ─────────────────────────────────────────────
        import_box = QGroupBox("Import Sessions")
        imp_layout = QVBoxLayout(import_box)

        imp_row = QHBoxLayout()
        imp_csv_btn = QPushButton("📂 Import from CSV")
        imp_csv_btn.clicked.connect(self._on_import_csv)
        imp_row.addWidget(imp_csv_btn)

        imp_excel_btn = QPushButton("📂 Import from Excel")
        imp_excel_btn.clicked.connect(self._on_import_excel)
        imp_row.addWidget(imp_excel_btn)
        imp_row.addStretch()
        imp_layout.addLayout(imp_row)

        self._import_status = QLabel("")
        self._import_status.setObjectName("dimLabel")
        imp_layout.addWidget(self._import_status)

        root.addWidget(import_box)
        root.addStretch()

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _load_sessions(self) -> None:
        try:
            tracker = self._state.tracker
            self._sessions = tracker.get_sessions(
                user_id=self._state.current_user_id
            )
        except Exception:
            self._sessions = []

        self._session_list.clear()
        for s in self._sessions:
            date_str = (s.get("date") or "")[:19].replace("T", " ")
            muscle = s.get("muscle_group") or "—"
            dur = f"{s.get('duration_seconds') or 0:.0f}s"
            text = f"{date_str}  |  {muscle}  |  {dur}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, s)
            self._session_list.addItem(item)

    def _get_export_sessions(self) -> list[dict]:
        selected = self._session_list.selectedItems()
        if selected:
            return [item.data(Qt.ItemDataRole.UserRole) for item in selected]
        return self._sessions

    # ------------------------------------------------------------------
    # Export slots
    # ------------------------------------------------------------------

    def _on_export_csv(self) -> None:
        sessions = self._get_export_sessions()
        if not sessions:
            QMessageBox.information(self, "Nothing to export", "No sessions found.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save CSV", "muscle_power_export.csv",
            "CSV files (*.csv);;All files (*)"
        )
        if not path:
            return
        try:
            export_sessions_csv(sessions, path)
            QMessageBox.information(self, "Export complete",
                                    f"Exported {len(sessions)} sessions to:\n{path}")
        except ExportError as e:
            QMessageBox.critical(self, "Export failed", str(e))

    def _on_export_excel(self) -> None:
        sessions = self._get_export_sessions()
        if not sessions:
            QMessageBox.information(self, "Nothing to export", "No sessions found.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Excel", "muscle_power_export.xlsx",
            "Excel files (*.xlsx);;All files (*)"
        )
        if not path:
            return
        try:
            export_sessions_excel(sessions, path)
            QMessageBox.information(self, "Export complete",
                                    f"Exported {len(sessions)} sessions to:\n{path}")
        except ExportError as e:
            QMessageBox.critical(self, "Export failed", str(e))

    def _on_export_pdf(self) -> None:
        sessions = self._get_export_sessions()
        if not sessions:
            QMessageBox.information(self, "Nothing to export", "No sessions found.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save PDF", "muscle_power_report.pdf",
            "PDF files (*.pdf);;All files (*)"
        )
        if not path:
            return
        try:
            export_sessions_pdf(sessions, path)
            QMessageBox.information(self, "Export complete",
                                    f"Report saved to:\n{path}")
        except ExportError as e:
            QMessageBox.critical(self, "Export failed", str(e))

    # ------------------------------------------------------------------
    # Import slots
    # ------------------------------------------------------------------

    def _on_import_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open CSV", "",
            "CSV files (*.csv);;All files (*)"
        )
        if not path:
            return
        try:
            records = import_sessions_csv(path)
            self._import_status.setText(
                f"✅ Imported {len(records)} sessions from CSV."
            )
            self._load_sessions()
        except DataImportError as e:
            QMessageBox.critical(self, "Import failed", str(e))

    def _on_import_excel(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Excel", "",
            "Excel files (*.xlsx *.xls);;All files (*)"
        )
        if not path:
            return
        try:
            records = import_sessions_excel(path)
            self._import_status.setText(
                f"✅ Imported {len(records)} sessions from Excel."
            )
            self._load_sessions()
        except DataImportError as e:
            QMessageBox.critical(self, "Import failed", str(e))
