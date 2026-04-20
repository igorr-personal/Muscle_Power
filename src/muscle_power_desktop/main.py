"""Desktop app entry point.

Usage:
    python -m muscle_power_desktop
    python src/muscle_power_desktop/main.py
"""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from muscle_power.db.migrations import run_migrations
from muscle_power.utils.logger import get_logger
from muscle_power_desktop.app import get_app_state
from muscle_power_desktop.windows.auth_dialog import AuthDialog
from muscle_power_desktop.windows.main_window import MainWindow

_log = get_logger(__name__)


def main() -> int:
    # Ensure DB schema is up to date
    try:
        run_migrations()
    except Exception as exc:
        _log.error("Migration failed: %s", exc)

    app = QApplication(sys.argv)
    app.setApplicationName("Muscle Power")
    app.setOrganizationName("MusclePower")

    # Apply dark theme stylesheet
    _apply_stylesheet(app)

    state = get_app_state()

    # Show auth dialog — blocks until user logs in or cancels
    dlg = AuthDialog(state)
    if dlg.exec() == 0:  # Rejected / closed
        return 0

    # Launch main window
    win = MainWindow(state)
    win.show()

    return app.exec()


def _apply_stylesheet(app: QApplication) -> None:
    """Apply glassmorphism-inspired dark QSS theme matching the web version."""
    app.setStyleSheet("""
        /* ── Global ─────────────────────────────────────────────────────── */
        QWidget {
            background-color: #0a0818;
            color: #E8E8F0;
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 13px;
        }

        /* ── Main Window / Tabs ─────────────────────────────────────────── */
        QMainWindow {
            background-color: #0a0818;
        }
        QTabWidget::pane {
            border: 1px solid rgba(255,255,255,0.12);
            background-color: rgba(255,255,255,0.03);
            border-radius: 8px;
        }
        QTabBar::tab {
            background: rgba(255,255,255,0.06);
            color: #aaa;
            padding: 8px 18px;
            border-radius: 6px 6px 0 0;
            margin-right: 2px;
        }
        QTabBar::tab:selected {
            background: rgba(228,0,43,0.30);
            color: #E8E8F0;
            border-bottom: 2px solid #E4002B;
        }
        QTabBar::tab:hover:!selected {
            background: rgba(255,255,255,0.10);
            color: #E8E8F0;
        }

        /* ── Buttons ────────────────────────────────────────────────────── */
        QPushButton {
            background: rgba(255,255,255,0.08);
            color: #E8E8F0;
            border: 1px solid rgba(255,255,255,0.18);
            border-radius: 6px;
            padding: 6px 14px;
        }
        QPushButton:hover {
            background: rgba(255,255,255,0.15);
            border-color: rgba(255,255,255,0.35);
        }
        QPushButton:pressed {
            background: rgba(228,0,43,0.25);
        }
        QPushButton#primaryBtn {
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #E4002B, stop:1 #a00020);
            color: #fff;
            border: none;
            font-weight: bold;
        }
        QPushButton#primaryBtn:hover {
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #ff1a45, stop:1 #c0002a);
        }
        QPushButton#dangerBtn {
            background: rgba(220,53,69,0.20);
            color: #ff6b6b;
            border: 1px solid rgba(220,53,69,0.40);
        }
        QPushButton#dangerBtn:hover {
            background: rgba(220,53,69,0.35);
        }

        /* ── Inputs ─────────────────────────────────────────────────────── */
        QLineEdit, QTextEdit, QPlainTextEdit {
            background: rgba(255,255,255,0.07);
            color: #E8E8F0;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 6px;
            padding: 5px 8px;
            selection-background-color: rgba(228,0,43,0.40);
        }
        QLineEdit:focus, QTextEdit:focus {
            border-color: rgba(228,0,43,0.60);
        }

        /* ── ComboBox ───────────────────────────────────────────────────── */
        QComboBox {
            background: rgba(255,255,255,0.08);
            color: #E8E8F0;
            border: 1px solid rgba(255,255,255,0.18);
            border-radius: 6px;
            padding: 5px 8px;
        }
        QComboBox:hover { border-color: rgba(255,255,255,0.35); }
        QComboBox::drop-down { border: none; width: 20px; }
        QComboBox QAbstractItemView {
            background: #130826;
            color: #E8E8F0;
            selection-background-color: rgba(228,0,43,0.35);
            border: 1px solid rgba(255,255,255,0.18);
        }

        /* ── Sliders ────────────────────────────────────────────────────── */
        QSlider::groove:horizontal {
            height: 4px;
            background: rgba(255,255,255,0.15);
            border-radius: 2px;
        }
        QSlider::handle:horizontal {
            background: #E4002B;
            width: 14px; height: 14px;
            border-radius: 7px;
            margin: -5px 0;
        }
        QSlider::sub-page:horizontal {
            background: rgba(228,0,43,0.55);
            border-radius: 2px;
        }

        /* ── Spinbox ────────────────────────────────────────────────────── */
        QSpinBox, QDoubleSpinBox {
            background: rgba(255,255,255,0.07);
            color: #E8E8F0;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 6px;
            padding: 4px 6px;
        }
        QSpinBox::up-button, QDoubleSpinBox::up-button,
        QSpinBox::down-button, QDoubleSpinBox::down-button {
            background: rgba(255,255,255,0.10);
            border: none;
        }

        /* ── CheckBox / RadioButton ─────────────────────────────────────── */
        QCheckBox, QRadioButton {
            color: #E8E8F0;
            spacing: 6px;
        }
        QCheckBox::indicator, QRadioButton::indicator {
            width: 16px; height: 16px;
            border: 1px solid rgba(255,255,255,0.30);
            border-radius: 3px;
            background: rgba(255,255,255,0.07);
        }
        QCheckBox::indicator:checked {
            background: #E4002B;
            border-color: #E4002B;
            image: none;
        }
        QRadioButton::indicator { border-radius: 8px; }
        QRadioButton::indicator:checked {
            background: #E4002B;
            border-color: #E4002B;
        }

        /* ── GroupBox ───────────────────────────────────────────────────── */
        QGroupBox {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 8px;
            margin-top: 14px;
            padding: 8px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            color: #E8E8F0;
            font-weight: bold;
        }

        /* ── Splitter ───────────────────────────────────────────────────── */
        QSplitter::handle {
            background: rgba(255,255,255,0.10);
            width: 4px;
        }
        QSplitter::handle:hover {
            background: rgba(228,0,43,0.50);
        }

        /* ── ScrollBar ──────────────────────────────────────────────────── */
        QScrollBar:vertical {
            background: rgba(255,255,255,0.04);
            width: 8px;
            border-radius: 4px;
        }
        QScrollBar::handle:vertical {
            background: rgba(255,255,255,0.20);
            border-radius: 4px;
            min-height: 20px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

        /* ── Table / List ───────────────────────────────────────────────── */
        QTableWidget, QListWidget {
            background: rgba(255,255,255,0.04);
            alternate-background-color: rgba(255,255,255,0.07);
            gridline-color: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 6px;
        }
        QTableWidget::item:selected, QListWidget::item:selected {
            background: rgba(228,0,43,0.30);
            color: #E8E8F0;
        }
        QHeaderView::section {
            background: rgba(255,255,255,0.08);
            color: #aaa;
            border: none;
            padding: 5px 8px;
        }
        QHeaderView::section:first { border-radius: 6px 0 0 0; }

        /* ── Status Bar ─────────────────────────────────────────────────── */
        QStatusBar {
            background: rgba(255,255,255,0.04);
            color: #aaa;
            border-top: 1px solid rgba(255,255,255,0.10);
        }

        /* ── Label ──────────────────────────────────────────────────────── */
        QLabel {
            background: transparent;
        }
        QLabel#titleLabel {
            color: #E4002B;
            font-size: 20px;
            font-weight: bold;
        }
        QLabel#sectionLabel {
            color: #E8E8F0;
            font-weight: bold;
            font-size: 13px;
        }
        QLabel#dimLabel {
            color: #888;
            font-size: 12px;
        }
        QLabel#kpiValue {
            color: #E4002B;
            font-size: 22px;
            font-weight: bold;
        }
        QLabel#kpiUnit {
            color: #aaa;
            font-size: 11px;
        }

        /* ── ToolTip ────────────────────────────────────────────────────── */
        QToolTip {
            background: #130826;
            color: #E8E8F0;
            border: 1px solid rgba(255,255,255,0.20);
            border-radius: 4px;
            padding: 4px 8px;
        }

        /* ── Menu / MenuBar ─────────────────────────────────────────────── */
        QMenuBar {
            background: rgba(255,255,255,0.04);
            color: #E8E8F0;
        }
        QMenuBar::item:selected {
            background: rgba(228,0,43,0.25);
        }
        QMenu {
            background: #130826;
            color: #E8E8F0;
            border: 1px solid rgba(255,255,255,0.15);
        }
        QMenu::item:selected {
            background: rgba(228,0,43,0.30);
        }
    """)


if __name__ == "__main__":
    sys.exit(main())
