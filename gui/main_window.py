"""
main_window.py — QMainWindow for the ambit dyeCO2 controller GUI.
"""

import time
from datetime import datetime
from pathlib import Path

import pyqtgraph as pg

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

import device_manager
import protocol
from data_buffer import BmeBuffer, SpecBuffer
from recorder import Recorder
from serial_worker import SerialWorker

# ---------------------------------------------------------------------------
# Colour palettes for plots
# ---------------------------------------------------------------------------

SPEC_COLORS = [
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4",
    "#42d4f4", "#f032e6", "#bfef45", "#fabed4", "#469990",
    "#dcbeff", "#9A6324", "#fffac8", "#800000", "#aaffc3",
    "#808000", "#ffd8b1", "#000075",
]

BME_COLORS = {
    "T":   "#e6194b",   # red
    "P":   "#4363d8",   # blue
    "RH":  "#3cb44b",   # green
    "Gas": "#f58231",   # orange
}

BME_UNITS = {"T": "°C", "P": "hPa", "RH": "%RH", "Gas": "Ω"}

# Interval dropdown: label → seconds
INTERVALS = [
    ("1 s",    1),
    ("2 s",    2),
    ("5 s",    5),
    ("10 s",  10),
    ("30 s",  30),
    ("1 min",  60),
    ("5 min",  300),
    ("10 min", 600),
    ("30 min", 1800),
    ("1 hour", 3600),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ambit dyeCO2 Controller")
        self.resize(1280, 800)

        # State
        self._worker: SerialWorker | None = None
        self._spec_buffer = SpecBuffer()
        self._bme_buffer = BmeBuffer()
        self._recorder = Recorder(Path(__file__).parent / "data")
        self._model = "AS7341"        # updated on status
        self._running = False         # acquisition running
        self._acq_timer = QTimer(self)
        self._acq_timer.timeout.connect(self._on_acquire_tick)
        self._last_spec: dict | None = None
        self._last_bme: dict | None = None
        self._acq_pending = False
        self._gain = 5
        self._atime = 100
        self._astep = 999
        self._led = 10

        # Pyqtgraph global style
        pg.setConfigOption("background", "#1e1e2e")
        pg.setConfigOption("foreground", "#cdd6f4")

        self._build_ui()
        self._refresh_ports()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # Left panel
        left_panel = self._build_left_panel()
        left_panel.setFixedWidth(230)

        # Right panel (plots + controls)
        right_panel = self._build_right_panel()

        root.addWidget(left_panel)
        root.addWidget(right_panel, stretch=1)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Not connected")

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # --- Connection group ---
        grp_conn = QGroupBox("Connection")
        form_conn = QFormLayout(grp_conn)
        form_conn.setLabelAlignment(Qt.AlignLeft)

        self._port_combo = QComboBox()
        self._port_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._refresh_btn = QPushButton("⟳")
        self._refresh_btn.setFixedWidth(28)
        self._refresh_btn.setToolTip("Refresh port list")
        self._refresh_btn.clicked.connect(self._refresh_ports)

        port_row = QWidget()
        port_row_h = QHBoxLayout(port_row)
        port_row_h.setContentsMargins(0, 0, 0, 0)
        port_row_h.addWidget(self._port_combo, stretch=1)
        port_row_h.addWidget(self._refresh_btn)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.clicked.connect(self._on_connect_clicked)

        self._spec_status_lbl = QLabel("Spectrometer: —")
        self._bme_status_lbl  = QLabel("BME: —")

        form_conn.addRow("Port:", port_row)
        form_conn.addRow(self._connect_btn)
        form_conn.addRow(self._spec_status_lbl)
        form_conn.addRow(self._bme_status_lbl)

        layout.addWidget(grp_conn)

        # --- Settings group ---
        grp_set = QGroupBox("Settings")
        form_set = QFormLayout(grp_set)
        form_set.setLabelAlignment(Qt.AlignLeft)

        # Interval
        self._interval_combo = QComboBox()
        for label, _ in INTERVALS:
            self._interval_combo.addItem(label)
        self._interval_combo.setCurrentIndex(0)  # 1 s default

        # Mode
        mode_widget = QWidget()
        mode_h = QHBoxLayout(mode_widget)
        mode_h.setContentsMargins(0, 0, 0, 0)
        self._mode_ambient = QRadioButton("Ambient")
        self._mode_flash   = QRadioButton("Flash")
        self._mode_flash.setChecked(True)
        mode_h.addWidget(self._mode_ambient)
        mode_h.addWidget(self._mode_flash)

        # Gain
        self._gain_combo = QComboBox()
        self._populate_gain_combo()

        # ATIME
        self._atime_spin = QSpinBox()
        self._atime_spin.setRange(0, 255)
        self._atime_spin.setValue(100)

        # ASTEP
        self._astep_spin = QSpinBox()
        self._astep_spin.setRange(0, 65534)
        self._astep_spin.setValue(999)

        # LED
        self._led_spin = QSpinBox()
        self._led_spin.setRange(0, 20)
        self._led_spin.setValue(10)
        self._led_spin.setSuffix(" mA")

        self._apply_btn = QPushButton("Apply Settings")
        self._apply_btn.clicked.connect(self._on_apply_settings)
        self._apply_btn.setEnabled(False)

        form_set.addRow("Interval:", self._interval_combo)
        form_set.addRow("Mode:", mode_widget)
        form_set.addRow("Gain:", self._gain_combo)
        form_set.addRow("ATIME:", self._atime_spin)
        form_set.addRow("ASTEP:", self._astep_spin)
        form_set.addRow("LED:", self._led_spin)
        form_set.addRow(self._apply_btn)

        layout.addWidget(grp_set)
        layout.addStretch()
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Splitter with two plots
        splitter = QSplitter(Qt.Vertical)

        self._spec_plot = pg.PlotWidget(title="Spectrometer")
        self._spec_plot.setLabel("left", "Counts")
        self._spec_plot.setLabel("bottom", "Time", units="s")
        self._spec_plot.showGrid(x=True, y=True, alpha=0.3)
        self._spec_legend = self._spec_plot.addLegend(offset=(10, 10))
        self._spec_curves: dict[str, pg.PlotDataItem] = {}

        self._bme_plot = pg.PlotWidget(title="BME68x Environment")
        self._bme_plot.setLabel("bottom", "Time", units="s")
        self._bme_plot.showGrid(x=True, y=True, alpha=0.3)
        self._bme_legend = self._bme_plot.addLegend(offset=(10, 10))
        self._bme_curves: dict[str, pg.PlotDataItem] = {}
        self._bme_axes: dict[str, pg.AxisItem] = {}
        self._bme_vbs: dict[str, pg.ViewBox] = {}
        self._build_bme_axes()

        splitter.addWidget(self._spec_plot)
        splitter.addWidget(self._bme_plot)
        splitter.setSizes([400, 300])

        layout.addWidget(splitter, stretch=1)

        # Controls bar
        ctrl = self._build_controls_bar()
        layout.addWidget(ctrl)

        return panel

    def _build_bme_axes(self):
        """Add one independent y-axis + ViewBox per BME field."""
        fields = ["T", "P", "RH", "Gas"]
        main_vb = self._bme_plot.getViewBox()

        # First field (T) uses the built-in left axis and main ViewBox
        first = fields[0]
        self._bme_plot.setLabel("left", f"{first} ({BME_UNITS[first]})",
                                color=BME_COLORS[first])
        self._bme_axes[first] = self._bme_plot.getAxis("left")
        self._bme_vbs[first] = main_vb

        # Remaining fields get their own ViewBox + right-side axis
        for col, field in enumerate(fields[1:], start=3):
            ax = pg.AxisItem("right")
            ax.setLabel(f"{field} ({BME_UNITS[field]})", color=BME_COLORS[field])

            vb = pg.ViewBox()
            self._bme_plot.scene().addItem(vb)
            ax.linkToView(vb)
            vb.setXLink(main_vb)

            self._bme_plot.plotItem.layout.addItem(ax, 2, col)
            self._bme_axes[field] = ax
            self._bme_vbs[field] = vb

        # Keep overlay ViewBoxes in sync when the main plot is resized
        main_vb.sigResized.connect(self._sync_bme_viewboxes)

    def _sync_bme_viewboxes(self):
        """Keep overlay ViewBoxes geometry in sync with the main ViewBox."""
        main_vb = self._bme_plot.getViewBox()
        rect = main_vb.sceneBoundingRect()
        if rect.width() == 0 or rect.height() == 0:
            return
        for field, vb in self._bme_vbs.items():
            if vb is not main_vb:
                vb.setGeometry(rect)

    @staticmethod
    def _connect_legend_toggle(legend, curve):
        """Make the last-added legend item clickable to toggle curve visibility."""
        if not legend.items:
            return
        sample, label = legend.items[-1]

        def on_click(ev, c=curve, s=sample, lb=label):
            visible = not c.isVisible()
            c.setVisible(visible)
            s.setOpacity(1.0 if visible else 0.3)
            lb.setOpacity(1.0 if visible else 0.3)

        sample.mousePressEvent = on_click
        label.mousePressEvent = on_click

    def _build_controls_bar(self) -> QWidget:
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)

        self._start_btn = QPushButton("▶  Start")
        self._start_btn.setEnabled(False)
        self._start_btn.clicked.connect(self._on_start)

        self._stop_btn = QPushButton("■  Stop")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._on_stop)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.clicked.connect(self._on_clear)

        self._autoscale_chk = QCheckBox("Autoscale")
        self._autoscale_chk.setChecked(True)

        h.addWidget(self._start_btn)
        h.addWidget(self._stop_btn)
        h.addWidget(self._clear_btn)
        h.addWidget(self._autoscale_chk)
        h.addStretch()

        # Recording controls
        rec_grp = QGroupBox("Record")
        rec_h = QHBoxLayout(rec_grp)
        rec_h.setContentsMargins(4, 4, 4, 4)

        self._filename_edit = QLineEdit("DATA")
        self._filename_edit.setMaximumWidth(150)
        self._filename_edit.setPlaceholderText("filename (no ext)")

        self._record_btn = QPushButton("⏺  Record")
        self._record_btn.setEnabled(False)
        self._record_btn.clicked.connect(self._on_record_start)

        self._stop_rec_btn = QPushButton("⏹  Stop Rec")
        self._stop_rec_btn.setEnabled(False)
        self._stop_rec_btn.clicked.connect(self._on_record_stop)

        rec_h.addWidget(QLabel("File:"))
        rec_h.addWidget(self._filename_edit)
        rec_h.addWidget(self._record_btn)
        rec_h.addWidget(self._stop_rec_btn)

        h.addWidget(rec_grp)
        return bar

    # ------------------------------------------------------------------
    # Gain combo helpers
    # ------------------------------------------------------------------

    def _populate_gain_combo(self):
        self._gain_combo.clear()
        labels = protocol.gain_labels(self._model)
        for idx in sorted(labels):
            self._gain_combo.addItem(f"{idx}  ({labels[idx]})", idx)
        # Select closest to current gain
        for i in range(self._gain_combo.count()):
            if self._gain_combo.itemData(i) == self._gain:
                self._gain_combo.setCurrentIndex(i)
                break

    # ------------------------------------------------------------------
    # Port management
    # ------------------------------------------------------------------

    def _refresh_ports(self):
        self._port_combo.clear()
        ports = device_manager.list_ports()
        for p in ports:
            self._port_combo.addItem(p)
        if not ports:
            self._port_combo.addItem("(no ports found)")

    def _on_connect_clicked(self):
        if self._worker and self._worker.isRunning():
            # Disconnect
            self._running = False
            self._acq_timer.stop()
            self._worker.close_port()
            self._connect_btn.setText("Connect")
            self._start_btn.setEnabled(False)
            self._apply_btn.setEnabled(False)
            self._status_bar.showMessage("Disconnected")
        else:
            port = self._port_combo.currentText()
            if not port or port.startswith("("):
                return
            self._status_bar.showMessage(f"Checking {port}…")
            if not device_manager.check_port(port):
                self._status_bar.showMessage(
                    f"{port}: no ambit device found (no hello response)"
                )
                return
            if self._worker is not None:
                self._worker.deleteLater()
            self._worker = SerialWorker(self)
            self._worker.spec_received.connect(self._on_spec)
            self._worker.bme_received.connect(self._on_bme)
            self._worker.status_received.connect(self._on_status)
            self._worker.spec_config_received.connect(self._on_spec_config)
            self._worker.error_received.connect(self._on_error)
            self._worker.connected.connect(self._on_connected)
            self._worker.disconnected.connect(self._on_disconnected)
            self._worker.open_port(port)
            self._connect_btn.setText("Disconnect")
            self._status_bar.showMessage(f"Connecting to {port}…")

    # ------------------------------------------------------------------
    # Worker signal handlers
    # ------------------------------------------------------------------

    def _on_connected(self, port: str):
        self._status_bar.showMessage(f"Connected: {port}")
        self._start_btn.setEnabled(True)
        self._apply_btn.setEnabled(True)

    def _on_disconnected(self):
        self._running = False
        self._acq_timer.stop()
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(False)
        self._apply_btn.setEnabled(False)
        self._connect_btn.setText("Connect")
        self._spec_status_lbl.setText("Spectrometer: —")
        self._bme_status_lbl.setText("BME: —")
        self._status_bar.showMessage("Disconnected")
        if self._recorder.is_recording:
            self._recorder.stop_recording()

    def _on_status(self, data: dict):
        spec_info = data.get("spectrometer", {})
        bme_info  = data.get("bme", {})

        if spec_info:
            model = spec_info.get("model", "Unknown")
            avail = spec_info.get("available", False)
            self._model = model
            icon = "✓" if avail else "✗"
            color = "green" if avail else "red"
            self._spec_status_lbl.setText(
                f'<span style="color:{color}">{icon} {model}</span>'
            )
            if not avail:
                self._status_bar.showMessage(f"Warning: spectrometer {model} not available")
            # Update gain combo range for this model
            self._populate_gain_combo()
            # Update atime/astep defaults
            defs = protocol.defaults_for_model(model)
            self._atime_spin.setValue(spec_info.get("atime", defs["atime"]))
            self._astep_spin.setValue(spec_info.get("astep", defs["astep"]))
            gain_val = spec_info.get("gain", defs["gain"])
            self._gain = gain_val
            for i in range(self._gain_combo.count()):
                if self._gain_combo.itemData(i) == gain_val:
                    self._gain_combo.setCurrentIndex(i)
                    break

        if bme_info:
            avail = bme_info.get("available", False)
            icon  = "✓" if avail else "✗"
            color = "green" if avail else "red"
            self._bme_status_lbl.setText(
                f'<span style="color:{color}">{icon} BME68x</span>'
            )

    def _on_spec(self, data: dict):
        self._acq_pending = False
        ts = time.time()
        channels = data.get("channels", {})
        self._last_spec = channels
        self._spec_buffer.append(ts, channels)
        self._update_spec_plot()
        if self._recorder.is_recording:
            self._recorder.write_row(
                datetime.fromtimestamp(ts).isoformat(timespec="milliseconds"),
                channels,
                self._last_bme,
            )

    def _on_bme(self, data: dict):
        ts = time.time()
        self._last_bme = data
        self._bme_buffer.append(ts, data)
        self._update_bme_plot()

    def _on_spec_config(self, cfg: dict):
        if "led_current_ma" in cfg:
            self._status_bar.showMessage(f"LED set to {cfg['led_current_ma']} mA")
        else:
            self._status_bar.showMessage(
                f"Config applied — gain={cfg.get('gain')}, "
                f"atime={cfg.get('atime')}, astep={cfg.get('astep')}"
            )

    def _on_error(self, msg: str):
        self._acq_pending = False
        self._status_bar.showMessage(f"Error: {msg}")

    # ------------------------------------------------------------------
    # Acquisition control
    # ------------------------------------------------------------------

    def _on_acquire_tick(self):
        if not self._worker or not self._worker.isRunning():
            return
        if self._acq_pending:
            return  # previous cycle still in progress
        self._acq_pending = True
        # Send env first so BME data arrives before spec (fixes data alignment)
        self._worker.send_command(protocol.CMD_ENV)
        if self._mode_flash.isChecked():
            self._worker.send_command(protocol.CMD_SPEC_FLASH)
        else:
            self._worker.send_command(protocol.CMD_SPEC)

    def _on_start(self):
        if not self._worker:
            return
        interval_ms = INTERVALS[self._interval_combo.currentIndex()][1] * 1000
        self._running = True
        self._acq_timer.start(interval_ms)
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._record_btn.setEnabled(True)
        self._status_bar.showMessage("Acquiring…")
        # Immediate first sample
        self._on_acquire_tick()

    def _on_stop(self):
        self._running = False
        self._acq_timer.stop()
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._record_btn.setEnabled(False)
        if self._recorder.is_recording:
            self._on_record_stop()
        self._status_bar.showMessage("Stopped")

    def _on_clear(self):
        self._spec_buffer.clear()
        self._bme_buffer.clear()
        # Remove spec curves and legend
        for curve in self._spec_curves.values():
            self._spec_plot.removeItem(curve)
        self._spec_curves.clear()
        self._spec_legend.clear()
        # Remove BME curves from their ViewBoxes and legend
        for field, curve in self._bme_curves.items():
            self._bme_vbs[field].removeItem(curve)
        self._bme_curves.clear()
        self._bme_legend.clear()
        self._last_spec = None
        self._last_bme = None

    # ------------------------------------------------------------------
    # Recording control
    # ------------------------------------------------------------------

    def _on_record_start(self):
        filename = self._filename_edit.text().strip() or "DATA"
        mode = "flash" if self._mode_flash.isChecked() else "ambient"
        path = self._recorder.start_recording(
            filename=filename,
            model=self._model,
            mode=mode,
            gain=self._gain,
            atime=self._atime_spin.value(),
            astep=self._astep_spin.value(),
            led=self._led_spin.value(),
            spec_channels=protocol.channels_for_model(self._model),
        )
        self._record_btn.setEnabled(False)
        self._stop_rec_btn.setEnabled(True)
        self._status_bar.showMessage(f"Recording → {path.name}")

    def _on_record_stop(self):
        self._recorder.stop_recording()
        self._record_btn.setEnabled(self._running)
        self._stop_rec_btn.setEnabled(False)
        self._status_bar.showMessage("Recording stopped")

    # ------------------------------------------------------------------
    # Settings application
    # ------------------------------------------------------------------

    def _on_apply_settings(self):
        if not self._worker or not self._worker.isRunning():
            return
        gain_val = self._gain_combo.currentData()
        atime_val = self._atime_spin.value()
        astep_val = self._astep_spin.value()
        led_val   = self._led_spin.value()
        self._gain  = gain_val
        self._atime = atime_val
        self._astep = astep_val
        self._led   = led_val
        self._worker.send_command(protocol.cmd_set_gain(gain_val))
        self._worker.send_command(protocol.cmd_set_atime(atime_val))
        self._worker.send_command(protocol.cmd_set_astep(astep_val))
        self._worker.send_command(protocol.cmd_set_led(led_val))

    # ------------------------------------------------------------------
    # Plot update helpers
    # ------------------------------------------------------------------

    def _update_spec_plot(self):
        if len(self._spec_buffer) == 0:
            return

        times = self._spec_buffer.times()
        t0 = times[0]
        t_rel = times - t0

        channels = self._spec_buffer.channel_names()
        ordered = [c for c in protocol.channels_for_model(self._model) if c in channels]
        ordered += [c for c in channels if c not in ordered]

        for i, ch in enumerate(ordered):
            color = SPEC_COLORS[i % len(SPEC_COLORS)]
            vals = self._spec_buffer.channel(ch)
            if len(vals) != len(t_rel):
                continue
            if ch not in self._spec_curves:
                label = protocol.channel_display_name(ch)
                pen = pg.mkPen(color=color, width=1.5)
                curve = self._spec_plot.plot(pen=pen, name=label)
                self._spec_curves[ch] = curve
                self._connect_legend_toggle(self._spec_legend, curve)
            self._spec_curves[ch].setData(t_rel, vals)

        if self._autoscale_chk.isChecked():
            self._spec_plot.enableAutoRange()

    def _update_bme_plot(self):
        if len(self._bme_buffer) == 0:
            return

        times = self._bme_buffer.times()
        t0 = times[0]
        t_rel = times - t0

        for field in BmeBuffer.FIELDS:
            vals = self._bme_buffer.field(field)
            if len(vals) != len(t_rel):
                continue
            color = BME_COLORS[field]
            vb = self._bme_vbs[field]
            if field not in self._bme_curves:
                label = f"{field} ({BME_UNITS[field]})"
                pen = pg.mkPen(color=color, width=1.5)
                curve = pg.PlotDataItem(pen=pen, name=label)
                vb.addItem(curve)
                self._bme_legend.addItem(curve, label)
                self._bme_curves[field] = curve
                self._connect_legend_toggle(self._bme_legend, curve)
            self._bme_curves[field].setData(t_rel, vals)

        # Ensure overlay ViewBoxes have correct geometry (needed on first data)
        self._sync_bme_viewboxes()

        if self._autoscale_chk.isChecked():
            for vb in self._bme_vbs.values():
                vb.enableAutoRange()

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        if self._recorder.is_recording:
            self._recorder.stop_recording()
        if self._worker and self._worker.isRunning():
            self._worker.close_port()
        super().closeEvent(event)
