"""RouterKing dock widget UI."""

try:
    from PySide2 import QtCore, QtWidgets, QtGui
except ImportError:  # pragma: no cover - fallback for older FreeCAD builds
    from PySide import QtCore, QtWidgets, QtGui

import re
import time

import FreeCAD as App
import FreeCADGui as Gui

try:
    import serial as _serial
    from serial.tools import list_ports as _list_ports
except Exception:
    try:
        from ..vendor import import_serial as _import_serial
    except ImportError:
        from vendor import import_serial as _import_serial
    _serial = _import_serial()
    from serial.tools import list_ports as _list_ports

try:
    from ..gcode.parser import iter_gcode_lines, parse_gcode
    from ..grbl.sender import GrblSender
except ImportError:
    from gcode.parser import iter_gcode_lines, parse_gcode
    from grbl.sender import GrblSender

_dock = None


def _status_message(text, error=False):
    if hasattr(Gui, "addStatusMessage"):
        Gui.addStatusMessage(text)
        return
    try:
        if error:
            App.Console.PrintError(text)
        else:
            App.Console.PrintMessage(text)
    except Exception:
        pass


_PREFS = App.ParamGet("User parameter:BaseApp/Preferences/RouterKing")
_ALARM_CODES = {
    1: "Hard limit triggered. Machine position may be lost.",
    2: "Soft limit alarm. Target exceeds machine travel.",
    3: "Reset while in motion. Position may be lost.",
    4: "Probe fail. Probe did not contact.",
    5: "Probe fail. Probe contacted before motion.",
    6: "Homing fail. Reset during homing.",
    7: "Homing fail. Door opened during homing.",
    8: "Homing fail. Pull-off failed.",
    9: "Homing fail. Could not find switch.",
}


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
        self._ports_cache = []
        self._last_console_line = None
        self._last_alarm_info = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title = QtWidgets.QLabel("RouterKing GRBL Sender")
        title.setObjectName("RouterKingTitle")
        layout.addWidget(title)

        connect_row = QtWidgets.QHBoxLayout()
        self._port = QtWidgets.QComboBox()
        self._port.setEditable(True)
        self._port.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self._port.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToContentsOnFirstShow)
        port_editor = self._port.lineEdit()
        if port_editor is not None:
            port_editor.setPlaceholderText("/dev/ttyUSB0 or /dev/cu.wchusbserial...")
        self._refresh_ports_btn = QtWidgets.QPushButton("Refresh")
        self._auto_btn = QtWidgets.QPushButton("Auto")
        self._connect_btn = QtWidgets.QPushButton("Connect")
        connect_row.addWidget(self._port)
        connect_row.addWidget(self._refresh_ports_btn)
        connect_row.addWidget(self._auto_btn)
        connect_row.addWidget(self._connect_btn)
        layout.addLayout(connect_row)

        status_row = QtWidgets.QHBoxLayout()
        self._connection_status = QtWidgets.QLabel("Connection: disconnected")
        self._machine_status = QtWidgets.QLabel("Machine: n/a")
        self._alarm_status = QtWidgets.QLabel("Alarm: none")
        self._job_status = QtWidgets.QLabel("Job: idle")
        status_row.addWidget(self._connection_status)
        status_row.addWidget(self._machine_status)
        status_row.addWidget(self._alarm_status)
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
        self._refresh_ports_btn.clicked.connect(self._refresh_ports)
        self._auto_btn.clicked.connect(self._auto_connect)

        self._refresh_ports()

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

        console_controls = QtWidgets.QHBoxLayout()
        self._console_verbose = QtWidgets.QCheckBox("Verbose")
        self._console_verbose.setChecked(False)
        self._console_verbose.setToolTip("Show status and ok messages.")
        self._clear_console_btn = QtWidgets.QPushButton("Clear")
        console_controls.addWidget(self._console_verbose)
        console_controls.addStretch(1)
        console_controls.addWidget(self._clear_console_btn)
        console_layout.addLayout(console_controls)

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
        self._clear_console_btn.clicked.connect(self._console.clear)

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
            self._alarm_status.setText("Alarm: none")
            self._last_alarm_info = None
            self._connect_btn.setText("Connect")
            self._port.setEnabled(True)
            self._refresh_ports()
            self._append_console("Disconnected.")
            self._update_job_controls()
            _status_message("RouterKing: disconnected\n")
            return

        port = self._current_port()
        if not port:
            if self._auto_connect():
                return
            self._append_console("Connect failed: no serial port set.")
            _status_message("RouterKing: no serial port set\n", error=True)
            return

        self._connect_to_port(port)

    def _drain_sender(self):
        lines = self._sender.poll()
        for line in lines:
            self._handle_console_line(line)

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
            self._update_alarm_status(state)

        self._update_job_controls()

    def _append_console(self, text, force=False):
        if not force and self._console_verbose is not None and not self._console_verbose.isChecked():
            if text == self._last_console_line:
                return
        self._console.appendPlainText(text)
        self._last_console_line = text

    def _handle_console_line(self, line):
        if self._is_status_line(line):
            if self._console_verbose.isChecked():
                self._append_console(line)
            return
        lower = line.strip().lower()
        if lower.startswith("alarm:"):
            message, label = self._format_alarm(line)
            self._last_alarm_info = label
            self._alarm_status.setText(f"Alarm: {label}")
            self._append_console(message, force=True)
            return
        if lower.startswith("error:"):
            self._append_console(line, force=True)
            return
        if lower == "ok" and not self._console_verbose.isChecked():
            return
        self._append_console(line)

    @staticmethod
    def _is_status_line(line):
        line = line.strip()
        return line.startswith("<") and line.endswith(">")

    def _format_alarm(self, line):
        match = re.match(r"ALARM:(\\d+)", line.strip(), flags=re.IGNORECASE)
        if not match:
            return line, line
        code = int(match.group(1))
        desc = _ALARM_CODES.get(code)
        if desc:
            message = f"ALARM:{code} {desc}"
            label = f"{desc} (ALARM:{code})"
            return message, label
        return f"ALARM:{code}", f"Code {code}"

    def _update_alarm_status(self, state):
        if str(state).lower() == "alarm":
            if self._last_alarm_info:
                self._alarm_status.setText(f"Alarm: {self._last_alarm_info}")
            else:
                self._alarm_status.setText("Alarm: active (no code yet)")
            return
        self._alarm_status.setText("Alarm: none")
        self._last_alarm_info = None

    def _connect_to_port(self, port):
        try:
            self._sender.connect(port)
        except Exception as exc:
            self._append_console(f"Connect failed: {exc}")
            _status_message(f"RouterKing: connect failed ({exc})\n", error=True)
            return False

        self._connection_status.setText(f"Connection: connected ({port})")
        self._alarm_status.setText("Alarm: none")
        self._last_alarm_info = None
        self._connect_btn.setText("Disconnect")
        self._port.setEnabled(False)
        self._append_console("Connected.")
        self._poll_timer.start()
        self._update_job_controls()
        _status_message("RouterKing: connected\n")
        self._remember_port(port)
        return True

    def _current_port(self):
        data = self._port.currentData()
        if data:
            return str(data).strip()
        return self._port.currentText().strip()

    def _remember_port(self, port):
        try:
            _PREFS.SetString("LastPort", str(port))
        except Exception:
            pass

    def _refresh_ports(self):
        current = self._current_port()
        if not current:
            try:
                current = _PREFS.GetString("LastPort")
            except Exception:
                current = ""
        self._port.blockSignals(True)
        self._port.clear()
        ports = []
        try:
            ports = list(_list_ports.comports())
        except Exception as exc:
            self._append_console(f"Port scan failed: {exc}")
        self._ports_cache = ports
        for port in ports:
            desc = port.description or ""
            manu = getattr(port, "manufacturer", "") or ""
            label = port.device
            if desc:
                label = f"{label} - {desc}"
            if manu:
                label = f"{label} ({manu})"
            self._port.addItem(label, port.device)
        if current:
            index = self._port.findData(current)
            if index >= 0:
                self._port.setCurrentIndex(index)
            else:
                self._port.setEditText(current)
        elif self._port.count() == 1:
            self._port.setCurrentIndex(0)
        self._port.blockSignals(False)

    def _auto_connect(self):
        if self._sender.is_connected():
            return True
        self._refresh_ports()
        ports = self._rank_ports(self._ports_cache)
        filtered = []
        for port in ports:
            text = " ".join(
                [
                    str(port.device or ""),
                    str(port.description or ""),
                ]
            ).lower()
            if "bluetooth" in text:
                continue
            filtered.append(port)
        ports = filtered
        if not ports:
            self._append_console("Auto connect failed: no serial ports found.")
            return False
        self._append_console(f"Auto connect: probing {len(ports)} port(s)...")
        for port in ports:
            device = port.device
            self._append_console(f"Probing {device}...")
            ok, detail = self._probe_port(device)
            if detail:
                self._append_console(detail)
            if ok:
                index = self._port.findData(device)
                if index >= 0:
                    self._port.setCurrentIndex(index)
                self._append_console(f"GRBL detected on {device}.")
                return self._connect_to_port(device)
        self._append_console("Auto connect failed: no GRBL response detected.")
        return False

    def _rank_ports(self, ports):
        def score(port):
            text = " ".join(
                [
                    str(port.device or ""),
                    str(port.description or ""),
                    str(getattr(port, "manufacturer", "") or ""),
                    str(getattr(port, "hwid", "") or ""),
                ]
            ).lower()
            keywords = ("grbl", "wch", "ch340", "usb", "serial", "ftdi", "cp210", "silabs", "arduino")
            return sum(1 for key in keywords if key in text)

        return sorted(ports, key=score, reverse=True)

    def _probe_port(self, device):
        try:
            serial = _serial.Serial(
                port=device,
                baudrate=115200,
                timeout=0.2,
                write_timeout=0.2,
            )
        except Exception as exc:
            return False, f"Probe failed: {exc}"
        try:
            try:
                serial.reset_input_buffer()
            except Exception:
                pass
            serial.write(b"\r\n\r\n")
            serial.flush()
            time.sleep(0.1)
            serial.write(b"?")
            serial.flush()
            deadline = time.time() + 0.8
            data = b""
            while time.time() < deadline:
                chunk = serial.read(128)
                if chunk:
                    data += chunk
                    decoded = data.decode("utf-8", errors="replace")
                    if self._is_grbl_response(decoded):
                        return True, "GRBL response detected."
            if data:
                preview = data.decode("utf-8", errors="replace").strip()
                if len(preview) > 200:
                    preview = f"{preview[:200]}..."
                return False, f"No GRBL signature (got: {preview})"
            return False, ""
        finally:
            try:
                serial.close()
            except Exception:
                pass

    @staticmethod
    def _is_grbl_response(text):
        if "Grbl" in text:
            return True
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("<") and line.endswith(">"):
                return True
        if "<" in text and ">" in text and ("MPos" in text or "WPos" in text):
            return True
        return False

    def _send_command(self, command):
        try:
            self._sender.send_line(command)
            self._append_console(f"> {command}")
        except Exception as exc:
            self._append_console(f"Send failed: {exc}")
            _status_message(f"RouterKing: send failed ({exc})\n", error=True)

    def _send_realtime(self, command):
        try:
            self._sender.send_realtime_command(command)
        except Exception as exc:
            self._append_console(f"Realtime failed: {exc}")
            _status_message(f"RouterKing: realtime failed ({exc})\n", error=True)

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
