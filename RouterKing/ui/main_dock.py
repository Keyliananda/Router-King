"""RouterKing dock widget UI."""

try:
    from PySide2 import QtCore, QtWidgets, QtGui
except ImportError:  # pragma: no cover - fallback for older FreeCAD builds
    from PySide import QtCore, QtWidgets, QtGui

import FreeCADGui as Gui

try:
    from ..gcode.parser import iter_gcode_lines, parse_gcode
    from ..grbl.sender import GrblSender
except ImportError:
    from gcode.parser import iter_gcode_lines, parse_gcode
    from grbl.sender import GrblSender

_dock = None


def _find_main_window():
    for widget in QtWidgets.QApplication.topLevelWidgets():
        if widget.metaObject().className() == "Gui::MainWindow":
            return widget
    return None


def show_panel():
    global _dock

    main_window = _find_main_window()
    if not main_window:
        return

    if _dock is None:
        _dock = QtWidgets.QDockWidget("RouterKing", main_window)
        _dock.setObjectName("RouterKingDock")
        _dock.setWidget(RouterKingDockWidget())
        main_window.addDockWidget(QtCore.Qt.RightDockWidgetArea, _dock)

    _dock.show()
    _dock.raise_()


class RouterKingDockWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._sender = GrblSender()
        self._last_gcode_path = None
        self._status_tick = 0
        self._fixed_font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title = QtWidgets.QLabel("RouterKing GRBL Sender")
        title.setObjectName("RouterKingTitle")
        layout.addWidget(title)

        connect_row = QtWidgets.QHBoxLayout()
        self._port = QtWidgets.QLineEdit()
        self._port.setPlaceholderText("/dev/ttyUSB0 or /dev/cu.wchusbserial...")
        self._connect_btn = QtWidgets.QPushButton("Connect")
        connect_row.addWidget(self._port)
        connect_row.addWidget(self._connect_btn)
        layout.addLayout(connect_row)

        status_row = QtWidgets.QHBoxLayout()
        self._connection_status = QtWidgets.QLabel("Connection: disconnected")
        self._machine_status = QtWidgets.QLabel("Machine: n/a")
        self._job_status = QtWidgets.QLabel("Job: idle")
        status_row.addWidget(self._connection_status)
        status_row.addWidget(self._machine_status)
        status_row.addWidget(self._job_status)
        status_row.addStretch(1)
        layout.addLayout(status_row)

        self._tabs = QtWidgets.QTabWidget()
        layout.addWidget(self._tabs, 1)

        self._control_tab = QtWidgets.QWidget()
        self._gcode_tab = QtWidgets.QWidget()
        self._tabs.addTab(self._control_tab, "Control")
        self._tabs.addTab(self._gcode_tab, "G-Code")

        self._build_control_tab(self._control_tab)
        self._build_gcode_tab(self._gcode_tab)

        self._poll_timer = QtCore.QTimer(self)
        self._poll_timer.setInterval(100)
        self._poll_timer.timeout.connect(self._drain_sender)

        self._connect_btn.clicked.connect(self._on_connect)

    def _build_control_tab(self, parent):
        layout = QtWidgets.QVBoxLayout(parent)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        command_row = QtWidgets.QHBoxLayout()
        self._home_btn = QtWidgets.QPushButton("Home")
        self._unlock_btn = QtWidgets.QPushButton("Unlock")
        self._reset_btn = QtWidgets.QPushButton("Reset")
        self._hold_btn = QtWidgets.QPushButton("Hold")
        self._resume_btn = QtWidgets.QPushButton("Resume")
        self._status_btn = QtWidgets.QPushButton("Status")
        for btn in [
            self._home_btn,
            self._unlock_btn,
            self._reset_btn,
            self._hold_btn,
            self._resume_btn,
            self._status_btn,
        ]:
            command_row.addWidget(btn)
        layout.addLayout(command_row)

        jog_group = QtWidgets.QGroupBox("Jog")
        jog_layout = QtWidgets.QVBoxLayout(jog_group)

        jog_controls = QtWidgets.QHBoxLayout()
        jog_controls.addWidget(QtWidgets.QLabel("Step (mm)"))
        self._jog_step = QtWidgets.QDoubleSpinBox()
        self._jog_step.setDecimals(3)
        self._jog_step.setRange(0.001, 1000.0)
        self._jog_step.setValue(1.0)
        jog_controls.addWidget(self._jog_step)
        jog_controls.addWidget(QtWidgets.QLabel("Feed"))
        self._jog_feed = QtWidgets.QDoubleSpinBox()
        self._jog_feed.setDecimals(0)
        self._jog_feed.setRange(1, 20000)
        self._jog_feed.setValue(600)
        jog_controls.addWidget(self._jog_feed)
        jog_controls.addStretch(1)
        jog_layout.addLayout(jog_controls)

        jog_row = QtWidgets.QHBoxLayout()
        self._jog_xm = QtWidgets.QPushButton("X-")
        self._jog_xp = QtWidgets.QPushButton("X+")
        self._jog_ym = QtWidgets.QPushButton("Y-")
        self._jog_yp = QtWidgets.QPushButton("Y+")
        self._jog_zm = QtWidgets.QPushButton("Z-")
        self._jog_zp = QtWidgets.QPushButton("Z+")
        for btn in [self._jog_xm, self._jog_xp, self._jog_ym, self._jog_yp, self._jog_zm, self._jog_zp]:
            jog_row.addWidget(btn)
        jog_layout.addLayout(jog_row)
        layout.addWidget(jog_group)

        console_group = QtWidgets.QGroupBox("Console")
        console_layout = QtWidgets.QVBoxLayout(console_group)
        self._console = QtWidgets.QPlainTextEdit()
        self._console.setReadOnly(True)
        self._console.setPlaceholderText("GRBL console output will appear here.")
        self._console.setFont(self._fixed_font)
        console_layout.addWidget(self._console, 1)

        command_input = QtWidgets.QHBoxLayout()
        self._command_line = QtWidgets.QLineEdit()
        self._command_line.setPlaceholderText("Enter a GRBL command (e.g. $$, $H, G0 X0)")
        self._send_cmd_btn = QtWidgets.QPushButton("Send")
        command_input.addWidget(self._command_line)
        command_input.addWidget(self._send_cmd_btn)
        console_layout.addLayout(command_input)
        layout.addWidget(console_group, 1)

        self._home_btn.clicked.connect(lambda: self._send_command("$H"))
        self._unlock_btn.clicked.connect(lambda: self._send_command("$X"))
        self._reset_btn.clicked.connect(self._send_soft_reset)
        self._hold_btn.clicked.connect(lambda: self._send_realtime("!"))
        self._resume_btn.clicked.connect(lambda: self._send_realtime("~"))
        self._status_btn.clicked.connect(self._request_status)
        self._jog_xm.clicked.connect(lambda: self._jog("X", -1))
        self._jog_xp.clicked.connect(lambda: self._jog("X", 1))
        self._jog_ym.clicked.connect(lambda: self._jog("Y", -1))
        self._jog_yp.clicked.connect(lambda: self._jog("Y", 1))
        self._jog_zm.clicked.connect(lambda: self._jog("Z", -1))
        self._jog_zp.clicked.connect(lambda: self._jog("Z", 1))
        self._send_cmd_btn.clicked.connect(self._on_send_command)
        self._command_line.returnPressed.connect(self._on_send_command)

    def _build_gcode_tab(self, parent):
        layout = QtWidgets.QVBoxLayout(parent)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        file_row = QtWidgets.QHBoxLayout()
        self._load_btn = QtWidgets.QPushButton("Load")
        self._save_btn = QtWidgets.QPushButton("Save")
        self._preview_btn = QtWidgets.QPushButton("Preview")
        file_row.addWidget(self._load_btn)
        file_row.addWidget(self._save_btn)
        file_row.addWidget(self._preview_btn)
        file_row.addStretch(1)
        layout.addLayout(file_row)

        job_row = QtWidgets.QHBoxLayout()
        self._start_btn = QtWidgets.QPushButton("Start")
        self._pause_btn = QtWidgets.QPushButton("Pause")
        self._stop_btn = QtWidgets.QPushButton("Stop")
        job_row.addWidget(self._start_btn)
        job_row.addWidget(self._pause_btn)
        job_row.addWidget(self._stop_btn)
        job_row.addStretch(1)
        layout.addLayout(job_row)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self._gcode_edit = QtWidgets.QPlainTextEdit()
        self._gcode_edit.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self._gcode_edit.setPlaceholderText("Load G-code to preview or send.")
        self._gcode_edit.setFont(self._fixed_font)
        self._preview_scene = QtWidgets.QGraphicsScene(self)
        self._preview_view = QtWidgets.QGraphicsView(self._preview_scene)
        self._preview_view.setRenderHint(QtGui.QPainter.Antialiasing)
        splitter.addWidget(self._gcode_edit)
        splitter.addWidget(self._preview_view)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        self._load_btn.clicked.connect(self._on_load_gcode)
        self._save_btn.clicked.connect(self._on_save_gcode)
        self._preview_btn.clicked.connect(self._update_preview)
        self._start_btn.clicked.connect(self._on_start_job)
        self._pause_btn.clicked.connect(self._on_pause_resume_job)
        self._stop_btn.clicked.connect(self._on_stop_job)

        self._update_job_controls()

    def _on_connect(self):
        if self._sender.is_connected():
            self._sender.disconnect()
            self._poll_timer.stop()
            self._connection_status.setText("Connection: disconnected")
            self._machine_status.setText("Machine: n/a")
            self._connect_btn.setText("Connect")
            self._port.setEnabled(True)
            self._append_console("Disconnected.")
            self._update_job_controls()
            Gui.addStatusMessage("RouterKing: disconnected\n")
            return

        port = self._port.text().strip()
        if not port:
            self._append_console("Connect failed: no serial port set.")
            Gui.addStatusMessage("RouterKing: no serial port set\n")
            return

        try:
            self._sender.connect(port)
        except Exception as exc:
            self._append_console(f"Connect failed: {exc}")
            Gui.addStatusMessage(f"RouterKing: connect failed ({exc})\n")
            return

        self._connection_status.setText(f"Connection: connected ({port})")
        self._connect_btn.setText("Disconnect")
        self._port.setEnabled(False)
        self._append_console("Connected.")
        self._poll_timer.start()
        self._update_job_controls()
        Gui.addStatusMessage("RouterKing: connected\n")

    def _drain_sender(self):
        lines = self._sender.poll()
        for line in lines:
            self._append_console(line)

        if self._sender.is_connected():
            self._status_tick += 1
            if self._status_tick >= 10:
                self._request_status()
                self._status_tick = 0

        status = self._sender.get_status()
        if status:
            state = status.get("state", "?")
            pos = status.get("WPos") or status.get("MPos")
            if pos:
                self._machine_status.setText(f"Machine: {state} | Pos: {pos}")
            else:
                self._machine_status.setText(f"Machine: {state}")

        self._update_job_controls()

    def _append_console(self, text):
        self._console.appendPlainText(text)

    def _send_command(self, command):
        try:
            self._sender.send_line(command)
            self._append_console(f"> {command}")
        except Exception as exc:
            self._append_console(f"Send failed: {exc}")
            Gui.addStatusMessage(f"RouterKing: send failed ({exc})\n")

    def _send_realtime(self, command):
        try:
            self._sender.send_realtime_command(command)
        except Exception as exc:
            self._append_console(f"Realtime failed: {exc}")
            Gui.addStatusMessage(f"RouterKing: realtime failed ({exc})\n")

    def _send_soft_reset(self):
        try:
            self._sender.send_soft_reset()
            self._append_console("Soft reset sent.")
        except Exception as exc:
            self._append_console(f"Reset failed: {exc}")

    def _request_status(self):
        try:
            self._sender.request_status()
        except Exception:
            pass

    def _jog(self, axis, direction):
        step = self._jog_step.value()
        feed = self._jog_feed.value()
        value = step * direction
        command = f"$J=G91 {axis}{value:.3f} F{feed:.0f}"
        self._send_command(command)

    def _on_send_command(self):
        command = self._command_line.text().strip()
        if not command:
            return
        self._command_line.clear()
        self._send_command(command)

    def _on_load_gcode(self):
        filters = "G-code (*.nc *.gcode *.tap *.txt);;All Files (*)"
        start_dir = self._last_gcode_path or ""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open G-code", start_dir, filters)
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                self._gcode_edit.setPlainText(handle.read())
            self._last_gcode_path = path
            self._append_console(f"Loaded G-code: {path}")
            self._update_preview()
        except Exception as exc:
            self._append_console(f"Load failed: {exc}")

    def _on_save_gcode(self):
        filters = "G-code (*.nc *.gcode *.tap *.txt);;All Files (*)"
        start_dir = self._last_gcode_path or ""
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save G-code", start_dir, filters)
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(self._gcode_edit.toPlainText())
            self._last_gcode_path = path
            self._append_console(f"Saved G-code: {path}")
        except Exception as exc:
            self._append_console(f"Save failed: {exc}")

    def _on_start_job(self):
        if not self._sender.is_connected():
            self._append_console("Start failed: not connected.")
            return
        lines = list(iter_gcode_lines(self._gcode_edit.toPlainText()))
        if not lines:
            self._append_console("Start failed: G-code is empty.")
            return
        try:
            self._sender.start_stream(lines)
            self._append_console(f"Streaming {len(lines)} lines.")
        except Exception as exc:
            self._append_console(f"Start failed: {exc}")
        self._update_job_controls()

    def _on_pause_resume_job(self):
        if not self._sender.is_streaming():
            return
        if self._sender.is_paused():
            self._sender.resume_stream()
            self._append_console("Job resumed.")
        else:
            self._sender.pause_stream()
            self._append_console("Job paused.")
        self._update_job_controls()

    def _on_stop_job(self):
        if not self._sender.is_streaming():
            return
        self._sender.stop_stream()
        self._append_console("Job stopped.")
        self._update_job_controls()

    def _update_job_controls(self):
        progress = self._sender.get_progress()
        total = progress.get("total", 0)
        acked = progress.get("acked", 0)
        if total:
            state = "paused" if progress.get("paused") else "running" if progress.get("streaming") else "idle"
            self._job_status.setText(f"Job: {acked}/{total} ({state})")
        else:
            self._job_status.setText("Job: idle")

        streaming = progress.get("streaming")
        paused = progress.get("paused")
        self._start_btn.setEnabled(self._sender.is_connected() and not streaming)
        self._pause_btn.setEnabled(streaming)
        self._stop_btn.setEnabled(streaming)
        self._pause_btn.setText("Resume" if paused else "Pause")

    def _update_preview(self):
        text = self._gcode_edit.toPlainText()
        path = parse_gcode(text)
        self._preview_scene.clear()
        if not path.segments:
            return
        for x0, y0, x1, y1, rapid in path.segments:
            color = QtGui.QColor(150, 150, 150) if rapid else QtGui.QColor(0, 120, 255)
            pen = QtGui.QPen(color, 0)
            self._preview_scene.addLine(x0, -y0, x1, -y1, pen)
        bounds = self._preview_scene.itemsBoundingRect()
        if not bounds.isNull():
            self._preview_view.fitInView(bounds, QtCore.Qt.KeepAspectRatio)
