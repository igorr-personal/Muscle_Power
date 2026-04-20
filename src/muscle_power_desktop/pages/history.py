"""Workout History page — browse and compare past sessions."""
from __future__ import annotations

from typing import Optional

import pyqtgraph as pg
import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QSplitter, QFrame, QAbstractItemView,
)
from PyQt6.QtGui import QColor

from muscle_power_desktop.app import AppState


class HistoryPage(QWidget):
    """Workout session browser with trend chart."""

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__(parent)
        self._state = state
        self._sessions: list[dict] = []
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Title
        root.addWidget(self._make_label("📊 Workout History", "titleLabel"))

        # ── Filter row ─────────────────────────────────────────────────
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Muscle group:"))
        self._muscle_filter = QComboBox()
        self._muscle_filter.addItem("All")
        self._muscle_filter.setMinimumWidth(140)
        self._muscle_filter.currentIndexChanged.connect(self._apply_filters)
        filter_row.addWidget(self._muscle_filter)

        filter_row.addWidget(QLabel("Period:"))
        self._days_filter = QComboBox()
        self._days_filter.addItems(["All time", "Last 7 days", "Last 30 days", "Last 90 days"])
        self._days_filter.currentIndexChanged.connect(self._apply_filters)
        filter_row.addWidget(self._days_filter)

        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self._load_sessions)
        filter_row.addWidget(refresh_btn)
        filter_row.addStretch()
        root.addLayout(filter_row)

        # ── KPI summary row ────────────────────────────────────────────
        kpi_row = QHBoxLayout()
        self._kpi_total = self._make_kpi_card("Total Sessions", "0")
        self._kpi_duration = self._make_kpi_card("Total Time", "0 min")
        self._kpi_peak = self._make_kpi_card("Best Peak", "---")
        self._kpi_reps = self._make_kpi_card("Total Reps", "0")
        kpi_row.addWidget(self._kpi_total)
        kpi_row.addWidget(self._kpi_duration)
        kpi_row.addWidget(self._kpi_peak)
        kpi_row.addWidget(self._kpi_reps)
        root.addLayout(kpi_row)

        # ── Splitter: chart above, table below ────────────────────────
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Trend chart
        chart_frame = QGroupBox("Progress Trend")
        chart_layout = QVBoxLayout(chart_frame)

        metric_row = QHBoxLayout()
        metric_row.addWidget(QLabel("Metric:"))
        self._metric_combo = QComboBox()
        self._metric_combo.addItems([
            "avg_power", "peak_power", "duration_seconds",
            "fatigue_index", "rep_count",
        ])
        self._metric_combo.currentIndexChanged.connect(self._update_chart)
        metric_row.addWidget(self._metric_combo)
        metric_row.addStretch()
        chart_layout.addLayout(metric_row)

        self._trend_plot = pg.PlotWidget()
        self._trend_plot.setMinimumHeight(160)
        self._trend_plot.showGrid(x=True, y=True, alpha=0.15)
        self._trend_plot.setMenuEnabled(False)
        chart_layout.addWidget(self._trend_plot)
        splitter.addWidget(chart_frame)

        # Session table
        table_frame = QGroupBox("Sessions")
        table_layout = QVBoxLayout(table_frame)
        self._table = QTableWidget()
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels([
            "Date", "Muscle group", "Duration (s)", "Avg power",
            "Peak power", "Fatigue idx", "Reps", "Notes",
        ])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.verticalHeader().hide()
        table_layout.addWidget(self._table)
        splitter.addWidget(table_frame)

        splitter.setSizes([200, 300])
        root.addWidget(splitter, stretch=1)

        # Load data
        self._load_sessions()

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _load_sessions(self) -> None:
        days_map = {0: None, 1: 7, 2: 30, 3: 90}
        days = days_map.get(self._days_filter.currentIndex())

        muscle_text = self._muscle_filter.currentText()
        muscle = None if muscle_text == "All" else muscle_text

        try:
            tracker = self._state.tracker
            self._sessions = tracker.get_sessions(
                muscle_group=muscle,
                days=days,
                user_id=self._state.current_user_id,
            )
        except Exception as e:
            self._sessions = []

        # Rebuild muscle filter (preserve current selection if possible)
        prev = self._muscle_filter.currentText()
        self._muscle_filter.blockSignals(True)
        self._muscle_filter.clear()
        self._muscle_filter.addItem("All")
        groups = sorted({s["muscle_group"] for s in self._sessions if s["muscle_group"]})
        self._muscle_filter.addItems(groups)
        idx = self._muscle_filter.findText(prev)
        self._muscle_filter.setCurrentIndex(max(0, idx))
        self._muscle_filter.blockSignals(False)

        self._apply_filters()

    def _apply_filters(self) -> None:
        days_map = {0: None, 1: 7, 2: 30, 3: 90}
        days = days_map.get(self._days_filter.currentIndex())
        muscle_text = self._muscle_filter.currentText()
        muscle = None if muscle_text == "All" else muscle_text

        filtered = [
            s for s in self._sessions
            if (muscle is None or s["muscle_group"] == muscle)
        ]

        self._populate_table(filtered)
        self._update_kpis(filtered)
        self._update_chart()

    def _populate_table(self, sessions: list[dict]) -> None:
        self._table.setRowCount(len(sessions))
        for row, s in enumerate(sessions):
            date_str = s.get("date", "")[:19].replace("T", " ") if s.get("date") else ""
            vals = [
                date_str,
                s.get("muscle_group", ""),
                f"{s.get('duration_seconds', '') or '---'}",
                f"{s.get('avg_power', '') or '---'}",
                f"{s.get('peak_power', '') or '---'}",
                f"{s.get('fatigue_index', '') or '---'}",
                f"{s.get('rep_count', '') or '---'}",
                s.get("notes", ""),
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, col, item)

    def _update_kpis(self, sessions: list[dict]) -> None:
        n = len(sessions)
        total_min = sum(
            (s.get("duration_seconds") or 0) for s in sessions
        ) / 60
        peaks = [s.get("peak_power") or 0 for s in sessions]
        best_peak = max(peaks) if peaks else 0
        total_reps = sum(s.get("rep_count") or 0 for s in sessions)

        self._set_kpi(self._kpi_total, "Total Sessions", str(n))
        self._set_kpi(self._kpi_duration, "Total Time", f"{total_min:.1f} min")
        self._set_kpi(self._kpi_peak, "Best Peak",
                      f"{best_peak * 1000:.2f} mV" if best_peak else "---")
        self._set_kpi(self._kpi_reps, "Total Reps", str(total_reps))

    def _update_chart(self) -> None:
        metric = self._metric_combo.currentText()
        muscle_text = self._muscle_filter.currentText()
        muscle = None if muscle_text == "All" else muscle_text

        filtered = [
            s for s in self._sessions
            if (muscle is None or s["muscle_group"] == muscle)
            and s.get(metric) is not None
        ]
        self._trend_plot.clear()
        if not filtered:
            return

        y_vals = [float(s[metric]) for s in filtered]
        x_vals = list(range(len(y_vals)))

        pen = pg.mkPen(color="#E4002B", width=2)
        scatter_pen = pg.mkPen(color="#E4002B", width=0)
        scatter_brush = pg.mkBrush(color="#E4002B")

        self._trend_plot.plot(x_vals, y_vals, pen=pen)
        scatter = pg.ScatterPlotItem(x=x_vals, y=y_vals, pen=scatter_pen,
                                     brush=scatter_brush, size=8)
        self._trend_plot.addItem(scatter)
        self._trend_plot.setLabel("left", metric.replace("_", " "))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_label(self, text: str, obj_name: str = "") -> QLabel:
        lbl = QLabel(text)
        if obj_name:
            lbl.setObjectName(obj_name)
        return lbl

    def _make_kpi_card(self, title: str, value: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: rgba(255,255,255,0.05); "
            "border: 1px solid rgba(255,255,255,0.12); "
            "border-radius: 8px; padding: 8px; }"
        )
        layout = QVBoxLayout(card)
        layout.setSpacing(2)
        title_lbl = QLabel(title)
        title_lbl.setObjectName(f"kpi_title_{title}")
        title_lbl.setStyleSheet("color: #888; font-size: 11px;")
        val_lbl = QLabel(value)
        val_lbl.setObjectName(f"kpi_value_{title}")
        val_lbl.setObjectName("kpiValue")
        layout.addWidget(title_lbl)
        layout.addWidget(val_lbl)
        card.setMinimumWidth(120)
        return card

    def _set_kpi(self, card: QFrame, title: str, value: str) -> None:
        val_lbl = card.findChild(QLabel, "kpiValue")
        if val_lbl:
            val_lbl.setText(value)

    # ------------------------------------------------------------------
    # User switch hook
    # ------------------------------------------------------------------

    def on_user_changed(self) -> None:
        self._load_sessions()
