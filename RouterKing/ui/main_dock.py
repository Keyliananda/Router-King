"""RouterKing dock widget UI."""

try:
    from PySide2 import QtCore, QtWidgets, QtGui
except ImportError:  # pragma: no cover - fallback for older FreeCAD builds
    from PySide import QtCore, QtWidgets, QtGui

import math
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


class _AiChatWorker(QtCore.QObject):
    finished = QtCore.Signal(str, object)

    def __init__(
        self,
        api_key,
        base_url,
        model,
        messages,
        reasoning_effort,
        temperature,
        max_output_tokens,
    ):
        super().__init__()
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._messages = messages
        self._reasoning_effort = reasoning_effort
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens

    def run(self):
        try:
            from ..ai.client import send_chat_request
        except ImportError:
            from ai.client import send_chat_request

        try:
            response = send_chat_request(
                self._api_key,
                self._base_url,
                self._model,
                self._messages,
                reasoning_effort=self._reasoning_effort,
                temperature=self._temperature,
                max_output_tokens=self._max_output_tokens,
            )
        except Exception as exc:
            self.finished.emit("", exc)
            return

        self.finished.emit(response, None)


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
        self._limits = {"X": None, "Y": None, "Z": None}
        self._limits_announced = False
        self._homing_dir_mask = 0
        self._axis_max_feed = {"X": None, "Y": None, "Z": None}
        self._explore_active = False
        self._explore_phase = None
        self._explore_axis_queue = []
        self._explore_axis = None
        self._explore_step = 5.0
        self._explore_feed = 800.0
        self._explore_margin = 2.0
        self._explore_distance = 0.0
        self._explore_pending = False
        self._explore_next_action = 0.0
        self._explore_results = {}
        self._explore_dir = 1.0
        self._explore_backoff = 5.0
        self._explore_unlock_sent_at = None
        self._homing_pull_off = 3.0
        self._explore_unlocked = False
        self._explore_last_command_at = None
        self._explore_recover_attempts = 0
        self._explore_dir_override = {"X": None, "Y": None, "Z": None}
        self._explore_safe_moves_done = False
        self._explore_retry_axes = set()
        self._explore_retry_axis = None
        self._explore_known_limits = {}
        self._explore_retry_measurements = {}
        self._explore_ramp_remaining = 0.0
        self._explore_ramp_feed = 0.0
        self._explore_ramp_increment_current = 0.0
        self._explore_ramp_max_feed_axis = 0.0
        self._explore_ramp_target_feed = 0.0
        self._explore_ramp_accel_remaining = 0.0
        self._explore_ramp_last_step = 0.0
        self._explore_prehome_pull_off = 0.0
        self._explore_preflight_sent = False
        self._explore_preflight_started_at = 0.0
        self._ai_messages = []
        self._ai_worker = None
        self._ai_worker_thread = None
        self._ai_chat_busy = False
        self._ai_preview_objects = []

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
        self._ai_tab = QtWidgets.QWidget()
        self._tabs.addTab(self._control_tab, "Control")
        self._tabs.addTab(self._gcode_tab, "G-Code")
        self._tabs.addTab(self._ai_tab, "AI Tools")

        self._build_control_tab(self._control_tab)
        self._build_gcode_tab(self._gcode_tab)
        self._build_ai_tab(self._ai_tab)

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

        machine_group = QtWidgets.QGroupBox("Machine Limits / Tests")
        machine_layout = QtWidgets.QGridLayout(machine_group)
        machine_layout.addWidget(QtWidgets.QLabel("X max (mm)"), 0, 0)
        self._limit_x = QtWidgets.QLabel("—")
        machine_layout.addWidget(self._limit_x, 0, 1)
        machine_layout.addWidget(QtWidgets.QLabel("Y max (mm)"), 0, 2)
        self._limit_y = QtWidgets.QLabel("—")
        machine_layout.addWidget(self._limit_y, 0, 3)
        machine_layout.addWidget(QtWidgets.QLabel("Z max (mm)"), 0, 4)
        self._limit_z = QtWidgets.QLabel("—")
        machine_layout.addWidget(self._limit_z, 0, 5)

        self._read_limits_btn = QtWidgets.QPushButton("Read Limits")
        self._travel_test_btn = QtWidgets.QPushButton("XY Travel Test")
        self._explore_limits_btn = QtWidgets.QPushButton("Explore Limits")
        self._explore_z_btn = QtWidgets.QPushButton("Explore Z axis")
        self._z_speed_test_btn = QtWidgets.QPushButton("Test Z speed")
        machine_layout.addWidget(self._read_limits_btn, 1, 0, 1, 2)
        machine_layout.addWidget(self._travel_test_btn, 1, 2, 1, 2)
        machine_layout.addWidget(self._explore_limits_btn, 1, 4, 1, 2)
        action_layout = QtWidgets.QHBoxLayout()
        action_layout.addWidget(self._explore_z_btn)
        action_layout.addWidget(self._z_speed_test_btn)
        action_layout.addStretch(1)
        machine_layout.addLayout(action_layout, 4, 0, 1, 6)

        machine_layout.addWidget(QtWidgets.QLabel("Margin (mm)"), 2, 0)
        self._travel_margin = QtWidgets.QDoubleSpinBox()
        self._travel_margin.setDecimals(2)
        self._travel_margin.setRange(0.0, 20.0)
        self._travel_margin.setValue(2.0)
        machine_layout.addWidget(self._travel_margin, 2, 1)
        machine_layout.addWidget(QtWidgets.QLabel("Test feed"), 2, 2)
        self._travel_feed = QtWidgets.QDoubleSpinBox()
        self._travel_feed.setDecimals(0)
        self._travel_feed.setRange(1, 20000)
        self._travel_feed.setValue(1200)
        machine_layout.addWidget(self._travel_feed, 2, 3)
        machine_layout.addWidget(QtWidgets.QLabel("Explore step (mm)"), 2, 4)
        self._explore_step_spin = QtWidgets.QDoubleSpinBox()
        self._explore_step_spin.setDecimals(2)
        self._explore_step_spin.setRange(0.1, 50.0)
        self._explore_step_spin.setValue(5.0)
        machine_layout.addWidget(self._explore_step_spin, 2, 5)
        machine_layout.addWidget(QtWidgets.QLabel("Z dir"), 3, 0)
        self._explore_z_dir = QtWidgets.QComboBox()
        self._explore_z_dir.addItems(["Auto", "+", "-"])
        self._explore_z_dir.setCurrentText("-")
        machine_layout.addWidget(self._explore_z_dir, 3, 1)
        machine_layout.addWidget(
            QtWidgets.QLabel("Requires homing + clear workspace. Explore hits limits."),
            5,
            0,
            1,
            6,
        )
        layout.addWidget(machine_group)

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
        self._read_limits_btn.clicked.connect(self._read_limits)
        self._travel_test_btn.clicked.connect(self._on_travel_test)
        self._explore_limits_btn.clicked.connect(self._on_explore_limits)
        self._explore_z_btn.clicked.connect(self._on_explore_z_axis)
        self._z_speed_test_btn.clicked.connect(self._on_z_speed_test)

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
        self._update_machine_controls()

    def _build_ai_tab(self, parent):
        layout = QtWidgets.QVBoxLayout(parent)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        header = QtWidgets.QLabel("AI Tools")
        layout.addWidget(header)

        settings_group = QtWidgets.QGroupBox("Provider Settings")
        settings_layout = QtWidgets.QGridLayout(settings_group)
        settings_layout.addWidget(QtWidgets.QLabel("Provider"), 0, 0)
        self._ai_provider = QtWidgets.QComboBox()
        self._ai_provider.addItems(["openai"])
        settings_layout.addWidget(self._ai_provider, 0, 1)

        settings_layout.addWidget(QtWidgets.QLabel("API key"), 1, 0)
        key_row = QtWidgets.QHBoxLayout()
        self._ai_api_key = QtWidgets.QLineEdit()
        self._ai_api_key.setEchoMode(QtWidgets.QLineEdit.Password)
        self._ai_api_key.setPlaceholderText("sk-...")
        self._ai_api_key_show = QtWidgets.QCheckBox("Show")
        key_row.addWidget(self._ai_api_key, 1)
        key_row.addWidget(self._ai_api_key_show)
        settings_layout.addLayout(key_row, 1, 1)

        settings_layout.addWidget(QtWidgets.QLabel("Base URL"), 2, 0)
        self._ai_base_url = QtWidgets.QLineEdit()
        self._ai_base_url.setPlaceholderText("https://api.openai.com/v1")
        settings_layout.addWidget(self._ai_base_url, 2, 1)

        settings_layout.addWidget(QtWidgets.QLabel("Model"), 3, 0)
        self._ai_model = QtWidgets.QComboBox()
        self._ai_model.setEditable(True)
        self._ai_model.addItems(["gpt-4o", "gpt-4o-mini", "o1-mini", "o1"])
        settings_layout.addWidget(self._ai_model, 3, 1)

        settings_layout.addWidget(QtWidgets.QLabel("Reasoning effort"), 4, 0)
        self._ai_reasoning = QtWidgets.QComboBox()
        self._ai_reasoning.addItems(["off", "low", "medium", "high"])
        settings_layout.addWidget(self._ai_reasoning, 4, 1)

        self._ai_save_btn = QtWidgets.QPushButton("Save Settings")
        self._ai_settings_status = QtWidgets.QLabel(
            "Stored in FreeCAD preferences (plain text). ENV overrides saved values."
        )
        settings_layout.addWidget(self._ai_save_btn, 5, 1)
        settings_layout.addWidget(self._ai_settings_status, 6, 0, 1, 2)
        layout.addWidget(settings_group)

        chat_group = QtWidgets.QGroupBox("AI Chat")
        chat_layout = QtWidgets.QVBoxLayout(chat_group)
        self._ai_chat_log = QtWidgets.QPlainTextEdit()
        self._ai_chat_log.setReadOnly(True)
        self._ai_chat_log.setPlaceholderText("Chat history will appear here.")
        chat_layout.addWidget(self._ai_chat_log, 1)

        chat_input_row = QtWidgets.QHBoxLayout()
        self._ai_chat_input = QtWidgets.QLineEdit()
        self._ai_chat_input.setPlaceholderText("Ask the RouterKing AI assistant...")
        self._ai_chat_send = QtWidgets.QPushButton("Send")
        self._ai_chat_clear = QtWidgets.QPushButton("Clear Chat")
        chat_input_row.addWidget(self._ai_chat_input, 1)
        chat_input_row.addWidget(self._ai_chat_send)
        chat_input_row.addWidget(self._ai_chat_clear)
        chat_layout.addLayout(chat_input_row)
        layout.addWidget(chat_group, 1)

        action_row = QtWidgets.QHBoxLayout()
        self._ai_analyze_btn = QtWidgets.QPushButton("Analyze Selection")
        self._ai_optimize_btn = QtWidgets.QPushButton("Preview Spline Optimization")
        self._ai_clear_btn = QtWidgets.QPushButton("Clear")
        action_row.addWidget(self._ai_analyze_btn)
        action_row.addWidget(self._ai_optimize_btn)
        action_row.addWidget(self._ai_clear_btn)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self._ai_status = QtWidgets.QLabel("Select geometry and click Analyze.")
        layout.addWidget(self._ai_status)

        self._ai_results = QtWidgets.QTreeWidget()
        self._ai_results.setHeaderLabels(["Severity", "Issue", "Suggestion"])
        self._ai_results.setRootIsDecorated(False)
        self._ai_results.setAlternatingRowColors(True)
        layout.addWidget(self._ai_results, 1)

        self._ai_analyze_btn.clicked.connect(self._on_ai_analyze)
        self._ai_optimize_btn.clicked.connect(self._on_ai_optimize_preview)
        self._ai_clear_btn.clicked.connect(self._on_ai_clear)
        self._ai_save_btn.clicked.connect(self._on_ai_settings_save)
        self._ai_api_key_show.toggled.connect(self._on_ai_toggle_key_visibility)
        self._ai_chat_send.clicked.connect(self._on_ai_send)
        self._ai_chat_clear.clicked.connect(self._on_ai_clear_chat)
        self._ai_chat_input.returnPressed.connect(self._on_ai_send)

        self._load_ai_settings()

    def _on_ai_clear(self):
        self._clear_ai_preview()
        self._ai_results.clear()
        self._ai_status.setText("Select geometry and click Analyze.")

    def _on_ai_analyze(self):
        try:
            from ..ai.analysis import analyze_selection
        except ImportError:
            from ai.analysis import analyze_selection

        try:
            result = analyze_selection()
        except Exception as exc:
            self._ai_status.setText("Analysis failed.")
            _status_message(f"RouterKing AI analysis failed: {exc}\n", error=True)
            return

        self._render_ai_results(result)

    def _on_ai_optimize_preview(self):
        try:
            from ..ai.optimization import optimize_selection
        except ImportError:
            from ai.optimization import optimize_selection

        self._clear_ai_preview()
        try:
            result = optimize_selection(create_preview=True)
        except Exception as exc:
            self._ai_status.setText("Optimization failed.")
            _status_message(f"RouterKing AI optimization failed: {exc}\n", error=True)
            return

        self._ai_preview_objects = result.preview_objects
        self._render_ai_results(result)

    def _clear_ai_preview(self):
        if not self._ai_preview_objects:
            return
        try:
            doc = App.ActiveDocument
        except Exception:
            doc = None

        for obj in list(self._ai_preview_objects):
            obj_name = getattr(obj, "Name", None)
            if doc is None or not obj_name:
                continue
            try:
                if doc.getObject(obj_name) is not None:
                    doc.removeObject(obj_name)
            except Exception:
                pass

        self._ai_preview_objects = []
        if doc is not None:
            try:
                doc.recompute()
            except Exception:
                pass

    def _render_ai_results(self, result):
        self._ai_results.clear()
        for issue in result.issues:
            item = QtWidgets.QTreeWidgetItem([issue.severity, issue.message, issue.suggestion])
            self._ai_results.addTopLevelItem(item)
        if result.summary:
            self._ai_status.setText(result.summary)
        elif result.issues:
            self._ai_status.setText(f"Found {len(result.issues)} issue(s).")
        else:
            self._ai_status.setText("No issues detected.")

    def _on_ai_toggle_key_visibility(self, checked):
        if checked:
            self._ai_api_key.setEchoMode(QtWidgets.QLineEdit.Normal)
        else:
            self._ai_api_key.setEchoMode(QtWidgets.QLineEdit.Password)

    def _load_ai_settings(self):
        try:
            from ..ai.config import load_config
        except ImportError:
            from ai.config import load_config

        config = load_config()
        provider = config.get("provider", {})
        chat = config.get("chat", {})
        name = provider.get("name", "openai")
        index = self._ai_provider.findText(name)
        if index != -1:
            self._ai_provider.setCurrentIndex(index)
        self._ai_api_key.setText(provider.get("openai_api_key", ""))
        self._ai_base_url.setText(provider.get("openai_base_url", ""))
        model = provider.get("openai_model", "gpt-4o-mini")
        model_index = self._ai_model.findText(model)
        if model_index != -1:
            self._ai_model.setCurrentIndex(model_index)
        else:
            self._ai_model.setEditText(model)
        reasoning = provider.get("openai_reasoning_effort", "off")
        reasoning_index = self._ai_reasoning.findText(reasoning)
        if reasoning_index != -1:
            self._ai_reasoning.setCurrentIndex(reasoning_index)
        self._ai_system_prompt = chat.get(
            "system_prompt",
            "You are RouterKing AI, a helpful assistant for FreeCAD CNC workflows.",
        )
        self._ai_temperature = float(chat.get("temperature", 0.2))
        self._ai_max_output_tokens = int(chat.get("max_output_tokens", 512))

    def _on_ai_settings_save(self):
        params = App.ParamGet("User parameter:BaseApp/Preferences/RouterKing/AI")
        params.SetString("provider", self._ai_provider.currentText())
        params.SetString("openai_api_key", self._ai_api_key.text().strip())
        params.SetString("openai_base_url", self._ai_base_url.text().strip())
        params.SetString("openai_model", self._ai_model.currentText().strip())
        params.SetString("openai_reasoning_effort", self._ai_reasoning.currentText().strip())
        self._ai_settings_status.setText("Saved to FreeCAD preferences.")
        _status_message("RouterKing AI settings saved.\n")

    def _on_ai_clear_chat(self):
        self._ai_chat_log.clear()
        self._ai_messages = []
        self._ai_chat_busy = False
        self._ai_chat_send.setEnabled(True)
        self._ai_chat_input.setEnabled(True)

    def _on_ai_send(self):
        if self._ai_chat_busy:
            return

        text = self._ai_chat_input.text().strip()
        if not text:
            return

        if not self._ai_messages:
            self._ai_messages.append({"role": "system", "content": self._ai_system_prompt})

        self._ai_messages.append({"role": "user", "content": text})
        self._append_chat("You", text)
        self._ai_chat_input.clear()
        self._ai_start_chat_request()

    def _append_chat(self, speaker, message):
        self._ai_chat_log.appendPlainText(f"{speaker}: {message}\n")

    def _ai_start_chat_request(self):
        api_key = self._ai_api_key.text().strip()
        base_url = self._ai_base_url.text().strip() or "https://api.openai.com/v1"
        model = self._ai_model.currentText().strip()
        reasoning = self._ai_reasoning.currentText().strip()

        self._ai_chat_busy = True
        self._ai_chat_send.setEnabled(False)
        self._ai_chat_input.setEnabled(False)
        self._append_chat("System", "Sending request...")

        self._ai_worker_thread = QtCore.QThread(self)
        self._ai_worker = _AiChatWorker(
            api_key,
            base_url,
            model,
            list(self._ai_messages),
            reasoning,
            self._ai_temperature,
            self._ai_max_output_tokens,
        )
        self._ai_worker.moveToThread(self._ai_worker_thread)
        self._ai_worker_thread.started.connect(self._ai_worker.run)
        self._ai_worker.finished.connect(self._on_ai_chat_finished)
        self._ai_worker.finished.connect(self._ai_worker_thread.quit)
        self._ai_worker_thread.finished.connect(self._ai_worker.deleteLater)
        self._ai_worker_thread.finished.connect(self._ai_worker_thread.deleteLater)
        self._ai_worker_thread.start()

    def _on_ai_chat_finished(self, response, error):
        if error:
            self._append_chat("Error", str(error))
        else:
            self._ai_messages.append({"role": "assistant", "content": response})
            self._append_chat("AI", response)

        self._ai_chat_busy = False
        self._ai_chat_send.setEnabled(True)
        self._ai_chat_input.setEnabled(True)

    def _on_connect(self):
        if self._sender.is_connected():
            self._sender.disconnect()
            self._poll_timer.stop()
            self._connection_status.setText("Connection: disconnected")
            self._machine_status.setText("Machine: n/a")
            self._alarm_status.setText("Alarm: none")
            self._last_alarm_info = None
            self._limits = {"X": None, "Y": None, "Z": None}
            self._limits_announced = False
            self._update_limit_labels()
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
        self._update_machine_controls()
        self._explore_tick()

    def _append_console(self, text, force=False):
        if not force and self._console_verbose is not None and not self._console_verbose.isChecked():
            if text == self._last_console_line:
                return
        self._console.appendPlainText(text)
        self._last_console_line = text

    def _handle_console_line(self, line):
        if self._parse_setting_line(line):
            if self._console_verbose.isChecked():
                self._append_console(line)
            return
        lower = line.strip().lower()
        if self._explore_active:
            if lower.startswith("grbl"):
                self._append_console("Controller reset detected.", force=True)
                self._explore_unlocked = False
                self._explore_pending = False
                self._explore_phase = "unlock"
                self._explore_next_action = time.time() + 0.5
                return
            if "to unlock" in lower or "check limits" in lower:
                self._explore_unlocked = False
                self._explore_pending = False
                self._explore_phase = "unlock"
                self._explore_next_action = time.time() + 0.2
        if self._is_status_line(line):
            if self._console_verbose.isChecked():
                self._append_console(line)
            return
        if lower == "ok" and self._explore_active and self._explore_pending:
            self._handle_explore_ok()
            if not self._console_verbose.isChecked():
                return
        if lower.startswith("alarm:"):
            message, label = self._format_alarm(line)
            self._last_alarm_info = label
            self._alarm_status.setText(f"Alarm: {label}")
            self._append_console(message, force=True)
            if self._explore_active:
                self._handle_explore_alarm(label)
            return
        if self._explore_active and "unlocked" in lower:
            self._explore_unlocked = True
            self._explore_pending = False
        if lower.startswith("error:"):
            self._append_console(line, force=True)
            return
        if lower == "ok" and not self._console_verbose.isChecked():
            return
        self._append_console(line)

    def _parse_setting_line(self, line):
        cleaned = re.sub(r"[\x00-\x1f]", "", line).strip()
        match = re.search(r"\$(13[0-2])=([-+]?[0-9]*[.,]?[0-9]+)", cleaned)
        if not match:
            other = re.search(r"\$(\d+)=([-+]?[0-9]*[.,]?[0-9]+)", cleaned)
            if not other:
                return False
            code = int(other.group(1))
            value_text = other.group(2).replace(",", ".")
            try:
                value = float(value_text)
            except ValueError:
                return False
            if code == 27:
                self._homing_pull_off = value
            elif code == 23:
                self._homing_dir_mask = int(value)
            elif code == 110:
                self._axis_max_feed["X"] = value
            elif code == 111:
                self._axis_max_feed["Y"] = value
            elif code == 112:
                self._axis_max_feed["Z"] = value
            return False
        code = int(match.group(1))
        value_text = match.group(2).replace(",", ".")
        try:
            value = float(value_text)
        except ValueError:
            return False
        if code == 130:
            self._limits["X"] = value
        elif code == 131:
            self._limits["Y"] = value
        elif code == 132:
            self._limits["Z"] = value
        self._update_limit_labels()
        if (
            not self._limits_announced
            and self._limits["X"] is not None
            and self._limits["Y"] is not None
            and self._limits["Z"] is not None
        ):
            self._limits_announced = True
            self._append_console(
                f"Limits read: X={self._limits['X']:.3f} "
                f"Y={self._limits['Y']:.3f} "
                f"Z={self._limits['Z']:.3f}",
                force=True,
            )
        return True

    @staticmethod
    def _is_status_line(line):
        line = line.strip()
        return line.startswith("<") and line.endswith(">")

    def _format_alarm(self, line):
        match = re.match(r"ALARM:(\d+)", line.strip(), flags=re.IGNORECASE)
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

    def _update_limit_labels(self):
        def format_value(value):
            return f"{value:.3f}" if value is not None else "—"

        self._limit_x.setText(format_value(self._limits["X"]))
        self._limit_y.setText(format_value(self._limits["Y"]))
        self._limit_z.setText(format_value(self._limits["Z"]))
        self._update_machine_controls()

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
        self._limits_announced = False
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

    def _send_command(self, command, log=True):
        try:
            self._sender.send_line(command)
            if log:
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

    def _read_limits(self):
        if not self._sender.is_connected():
            self._append_console("Read limits failed: not connected.")
            return
        self._append_console("Reading limits ($130/$131/$132)...")
        self._send_command("$$")

    def _on_travel_test(self):
        if not self._sender.is_connected():
            self._append_console("Travel test failed: not connected.")
            return
        if self._sender.is_streaming():
            self._append_console("Travel test failed: sender busy.")
            return
        status = self._sender.get_status()
        if status and str(status.get("state", "")).lower() == "alarm":
            self._append_console("Travel test blocked: alarm active. Unlock and home first.")
            return
        max_x = self._limits.get("X")
        max_y = self._limits.get("Y")
        if max_x is None or max_y is None:
            self._append_console("Travel test failed: read limits first.")
            return
        margin = self._travel_margin.value()
        target_x = max_x - margin
        target_y = max_y - margin
        if target_x <= 0 or target_y <= 0:
            self._append_console("Travel test failed: margin too large for limits.")
            return
        feed = self._travel_feed.value()
        if not self._confirm_travel_test(max_x, max_y, target_x, target_y, margin, feed):
            return
        lines = [
            "G90",
            "G21",
            f"G53 G1 X0 Y0 F{feed:.0f}",
            f"G53 G1 X{target_x:.3f} F{feed:.0f}",
            "G53 G1 X0",
            f"G53 G1 Y{target_y:.3f} F{feed:.0f}",
            "G53 G1 Y0",
        ]
        self._sender.start_stream(lines)
        self._append_console("Travel test started.")

    def _on_explore_limits(self):
        if self._explore_active:
            self._explore_active = False
            self._explore_phase = None
            self._explore_axis_queue = []
            self._explore_pending = False
            self._append_console("Explore limits stopped.")
            self._update_machine_controls()
            return
        if not self._sender.is_connected():
            self._append_console("Explore limits failed: not connected.")
            return
        if self._sender.is_streaming():
            self._append_console("Explore limits failed: sender busy.")
            return
        status = self._sender.get_status()
        if status and str(status.get("state", "")).lower() == "alarm":
            self._append_console("Explore limits blocked: alarm active. Unlock and home first.")
            return
        if not self._prepare_explore_parameters():
            return
        if not self._confirm_explore_limits(self._explore_step, self._explore_feed, self._explore_margin):
            return
        self._start_explore(["X", "Y", "Z"])

    def _prepare_explore_parameters(self):
        self._explore_step = self._explore_step_spin.value()
        self._explore_feed = self._travel_feed.value()
        self._explore_margin = self._travel_margin.value()
        self._explore_backoff = max(
            self._homing_pull_off + 5.0,
            self._explore_margin + 5.0,
            self._explore_step * 2.0,
        )
        self._explore_prehome_pull_off = max(
            self._homing_pull_off + 2.0,
            self._explore_margin + 2.0,
        )
        self._explore_recover_attempts = 0
        if self._explore_step <= 0:
            self._append_console("Explore limits failed: step must be > 0.")
            return False
        return True

    def _on_explore_z_axis(self):
        if self._explore_active:
            self._append_console("Explore limits already running.")
            self._update_machine_controls()
            return
        if not self._sender.is_connected():
            self._append_console("Explore limits failed: not connected.")
            return
        if self._sender.is_streaming():
            self._append_console("Explore limits failed: sender busy.")
            return
        status = self._sender.get_status()
        if status and str(status.get("state", "")).lower() == "alarm":
            self._append_console("Explore limits blocked: alarm active. Unlock and home first.")
            return
        if not self._prepare_explore_parameters():
            return
        if not self._confirm_explore_limits(self._explore_step, self._explore_feed, self._explore_margin):
            return
        self._start_explore(["Z"])

    def _on_z_speed_test(self):
        if not self._sender.is_connected():
            self._append_console("Z speed test failed: not connected.")
            return
        if self._sender.is_streaming() or self._explore_active:
            self._append_console("Z speed test failed: sender busy.")
            return
        step = self._explore_step_spin.value()
        if step <= 0:
            self._append_console("Z speed test failed: step must be > 0.")
            return
        feed = self._travel_feed.value()
        direction = self._axis_explore_dir("Z")
        distance = direction * step
        self._append_console(
            f"Z speed test: moving {step:.3f} mm at {feed:.0f} mm/min "
            f"(direction {'+' if direction > 0 else '-'})"
        )
        self._send_command("G91 G21")
        self._send_command(f"G1 Z{distance:.3f} F{feed:.0f}")
        self._send_command(f"G0 Z{-distance:.3f}")
        self._send_command("G90")

    def _confirm_explore_limits(self, step, feed, margin):
        message = (
            "This mode intentionally runs each axis into its limit switch to\n"
            "discover maximum travel. This can trigger hard limit alarms and\n"
            "controller resets.\n\n"
            f"Step: {step:.2f} mm\n"
            f"Feed: {feed:.0f} mm/min\n"
            f"Margin: {margin:.2f} mm\n\n"
            "Make sure the machine is homed, spindle/laser is off, and the\n"
            "workspace is clear. Continue?"
        )
        result = QtWidgets.QMessageBox.warning(
            self,
            "Explore Limits?",
            message,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        return result == QtWidgets.QMessageBox.Yes

    def _start_explore(self, axes=None):
        self._explore_active = True
        self._explore_phase = "preflight"
        axes_to_run = list(axes) if axes else ["X", "Y", "Z"]
        if not axes_to_run:
            self._append_console("Explore limits failed: no axes selected.")
            self._explore_active = False
            return
        self._explore_axis_queue = axes_to_run
        self._explore_axis = None
        self._explore_distance = 0.0
        self._explore_pending = False
        self._explore_next_action = time.time()
        self._explore_results = {}
        self._explore_unlock_sent_at = None
        self._explore_unlocked = False
        self._explore_last_command_at = None
        self._explore_recover_attempts = 0
        self._explore_known_limits = dict(self._limits)
        self._explore_retry_axes.clear()
        self._explore_retry_axis = None
        self._explore_retry_measurements = {}
        self._explore_dir_override = {"X": None, "Y": None, "Z": None}
        self._explore_preflight_sent = False
        self._explore_preflight_started_at = 0.0
        self._append_console("Explore limits started.", force=True)
        self._update_machine_controls()

    def _start_next_explore_axis(self):
        if self._explore_retry_axis is not None:
            self._explore_axis = self._explore_retry_axis
            self._explore_retry_axis = None
        else:
            if not self._explore_axis_queue:
                self._finish_explore()
                return
            self._explore_axis = self._explore_axis_queue.pop(0)
        self._explore_distance = 0.0
        self._explore_phase = "move"
        self._explore_pending = False
        self._explore_unlocked = False
        self._explore_last_command_at = None
        self._explore_recover_attempts = 0
        self._explore_dir = self._axis_explore_dir(self._explore_axis)
        self._explore_dir_override[self._explore_axis] = None
        self._explore_ramp_remaining = 0.0
        self._explore_ramp_feed = 0.0
        self._explore_ramp_increment_current = 0.0
        self._explore_ramp_max_feed_axis = 0.0
        self._explore_ramp_last_step = 0.0
        self._append_console(f"Exploring {self._explore_axis} axis...", force=True)

    def _explore_tick(self):
        if not self._explore_active:
            return
        if time.time() < self._explore_next_action:
            return
        status = self._sender.get_status() or {}
        state = str(status.get("state", "")).lower()
        if self._explore_phase == "preflight":
            if not self._explore_preflight_sent:
                self._explore_preflight_sent = True
                self._explore_preflight_started_at = time.time()
                self._limits_announced = False
                self._append_console("Explore preflight: reading limits...", force=True)
                self._send_command("$$", log=False)
                self._explore_next_action = time.time() + 0.2
                return
            if self._limits_announced:
                self._explore_phase = "move"
                self._explore_next_action = time.time() + 0.2
                self._start_next_explore_axis()
                return
            if time.time() - self._explore_preflight_started_at > 2.0:
                self._append_console(
                    "Explore preflight: limits not confirmed, continuing.",
                    force=True,
                )
                self._explore_phase = "move"
                self._explore_next_action = time.time() + 0.2
                self._start_next_explore_axis()
                return
            return
        if self._explore_phase == "wait_idle":
            if state == "idle":
                self._explore_next_action = time.time() + 0.2
                self._start_next_explore_axis()
            return
        if self._explore_phase == "unlock":
            if self._explore_unlocked:
                self._explore_phase = "backoff"
                self._explore_pending = False
                return
            if (
                not self._explore_pending
                or not self._explore_last_command_at
                or time.time() - self._explore_last_command_at > 1.0
            ):
                self._explore_pending = True
                self._explore_unlock_sent_at = time.time()
                self._explore_last_command_at = time.time()
                self._send_command("$X", log=False)
            return
        if self._explore_phase == "backoff":
            axis = self._explore_axis
            if not self._explore_pending:
                direction = -self._explore_dir
                distance = self._explore_backoff
                self._explore_pending = True
                self._explore_last_command_at = time.time()
                self._send_command(f"G91 G21 G0 {axis}{direction * distance:.3f}", log=False)
                return
            if state == "idle":
                self._explore_pending = False
                self._explore_phase = "ramp"
            return
        if self._explore_phase == "ramp":
            if self._explore_pending:
                return
            if self._explore_ramp_remaining <= 0.0:
                self._explore_phase = "prehome_pull_off"
                return
            if state == "alarm":
                return
            axis = self._explore_axis
            step = min(self._explore_step, self._explore_ramp_remaining)
            direction = -self._explore_dir
            feed = min(self._explore_ramp_feed, self._explore_ramp_max_feed_axis)
            self._explore_ramp_feed = feed
            self._explore_ramp_last_step = step
            self._explore_pending = True
            self._explore_last_command_at = time.time()
            self._send_command(
                f"G91 G21 G1 {axis}{direction * step:.3f} F{feed:.0f}",
                log=False,
            )
            return
        if self._explore_phase == "prehome_pull_off":
            if self._explore_pending:
                return
            if state == "alarm":
                return
            axis = self._explore_axis
            direction = self._explore_dir
            distance = self._explore_prehome_pull_off
            if distance <= 0:
                self._explore_phase = "home"
                return
            self._explore_pending = True
            self._explore_last_command_at = time.time()
            self._send_command(
                f"G91 G21 G0 {axis}{direction * distance:.3f}",
                log=False,
            )
            return
        if self._explore_phase == "home":
            if self._explore_pending:
                return
            if state != "idle":
                return
            self._explore_pending = True
            self._explore_last_command_at = time.time()
            self._send_command("$H", log=False)
            self._explore_phase = "wait_idle"
            return
        if self._explore_phase == "move":
            if self._explore_pending:
                return
            if state == "alarm":
                return
            self._send_explore_step()

    def _send_explore_step(self):
        axis = self._explore_axis
        step = self._explore_step
        feed = self._explore_feed
        self._explore_pending = True
        self._explore_last_command_at = time.time()
        self._send_command(f"G91 G21 G1 {axis}{self._explore_dir * step:.3f} F{feed:.0f}", log=False)

    def _handle_explore_ok(self):
        if self._explore_phase == "move":
            self._explore_distance += self._explore_step
            self._explore_pending = False
            return
        if self._explore_phase == "ramp":
            self._explore_pending = False
            self._explore_ramp_remaining = max(
                0.0,
                self._explore_ramp_remaining - self._explore_ramp_last_step,
            )
            if self._explore_ramp_feed < self._explore_ramp_max_feed_axis:
                self._explore_ramp_feed = min(
                    self._explore_ramp_max_feed_axis,
                    self._explore_ramp_feed + self._explore_ramp_increment_current,
                )
            return
        if self._explore_phase == "prehome_pull_off":
            self._explore_pending = False
            self._explore_phase = "home"
            return

    def _handle_explore_alarm(self, label):
        if self._explore_phase not in ("move", "backoff", "ramp", "prehome_pull_off", "home", "unlock"):
            return
        if self._explore_phase != "move":
            if "homing fail" in label.lower():
                self._explore_recover_attempts += 1
                if self._explore_recover_attempts <= 3:
                    self._explore_backoff *= 1.5
                    self._explore_unlocked = False
                    self._explore_pending = False
                    self._explore_phase = "unlock"
                    self._explore_next_action = time.time() + 0.5
                    self._append_console(
                        "Homing failed. Increasing backoff and retrying unlock/home.",
                        force=True,
                    )
                    return
            self._append_console("Explore halted due to alarm during recovery.", force=True)
            self._explore_active = False
            self._explore_phase = None
            self._update_machine_controls()
            return
        axis = self._explore_axis
        measured = max(0.0, self._explore_distance - self._explore_margin)
        if axis in self._explore_retry_measurements:
            previous = self._explore_retry_measurements.pop(axis)
            measured = max(previous, measured)
        elif self._should_retry_explore_axis(axis, measured):
            self._explore_retry_axes.add(axis)
            self._explore_retry_measurements[axis] = measured
            self._explore_retry_axis = axis
            self._explore_dir_override[axis] = -self._explore_dir
            self._append_console(
                f"Explore: {axis} alarm too early; retrying opposite direction.",
                force=True,
            )
            self._explore_phase = "unlock"
            self._explore_unlocked = False
            self._explore_pending = False
            self._explore_next_action = time.time() + 0.5
            return
        self._explore_results[axis] = measured
        self._limits[axis] = measured
        self._update_limit_labels()
        axis_max_feed = self._axis_max_feed.get(axis)
        if axis_max_feed is None or axis_max_feed <= 0:
            axis_max_feed = self._explore_feed
            self._append_console(
                "Explore ramp: max feed unknown; using test feed.",
                force=True,
            )
        if self._explore_feed > axis_max_feed:
            self._append_console(
                f"Explore ramp: test feed capped to {axis_max_feed:.0f} mm/min.",
                force=True,
            )
        self._explore_ramp_max_feed_axis = axis_max_feed
        self._explore_ramp_feed = min(self._explore_feed, axis_max_feed)
        self._explore_ramp_last_step = 0.0
        self._explore_ramp_remaining = max(
            0.0,
            measured - self._explore_backoff - self._explore_prehome_pull_off,
        )
        if self._explore_ramp_remaining > 0.0 and self._explore_step > 0:
            steps_available = max(1, int(self._explore_ramp_remaining / self._explore_step))
            ramp_delta = self._explore_ramp_max_feed_axis - self._explore_ramp_feed
            self._explore_ramp_increment_current = max(0.0, ramp_delta / steps_available)
        else:
            self._explore_ramp_increment_current = 0.0
        self._append_console(
            f"Explore: {axis} limit hit. Stored {measured:.3f} mm "
            f"(margin {self._explore_margin:.2f}).",
            force=True,
        )
        self._explore_phase = "unlock"
        self._explore_unlocked = False
        self._explore_pending = False
        self._explore_next_action = time.time() + 0.5

    def _finish_explore(self):
        self._explore_active = False
        self._explore_phase = None
        self._explore_axis = None
        self._explore_pending = False
        self._append_console("Explore limits complete.", force=True)
        self._update_machine_controls()
        self._prompt_apply_limits()
        self._send_unlock_home_after_explore()

    def _send_unlock_home_after_explore(self):
        if not self._sender.is_connected():
            return
        if self._sender.is_streaming():
            return
        self._send_command("$X")
        self._send_command("$H")

    def _prompt_apply_limits(self):
        if not self._explore_results:
            return
        x = self._limits.get("X")
        y = self._limits.get("Y")
        z = self._limits.get("Z")
        if x is None or y is None or z is None:
            return
        message = (
            "Apply measured limits to the controller?\n\n"
            f"$130 (X max): {x:.3f}\n"
            f"$131 (Y max): {y:.3f}\n"
            f"$132 (Z max): {z:.3f}\n"
        )
        result = QtWidgets.QMessageBox.question(
            self,
            "Write Limits?",
            message,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if result == QtWidgets.QMessageBox.Yes:
            self._send_command(f"$130={x:.3f}")
            self._send_command(f"$131={y:.3f}")
            self._send_command(f"$132={z:.3f}")
            self._append_console("Limits written to controller.", force=True)
    def _confirm_travel_test(self, max_x, max_y, target_x, target_y, margin, feed):
        message = (
            "This will move X/Y to machine limits using G53.\n\n"
            f"X max: {max_x:.3f} mm (target: {target_x:.3f} mm)\n"
            f"Y max: {max_y:.3f} mm (target: {target_y:.3f} mm)\n"
            f"Margin: {margin:.2f} mm\n"
            f"Feed: {feed:.0f} mm/min\n\n"
            "Make sure the machine is homed, spindle/laser is off, and the\n"
            "workspace is clear. Continue?"
        )
        result = QtWidgets.QMessageBox.warning(
            self,
            "Run XY Travel Test?",
            message,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        return result == QtWidgets.QMessageBox.Yes

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

    def _update_machine_controls(self):
        connected = self._sender.is_connected()
        streaming = self._sender.is_streaming()
        status = self._sender.get_status() or {}
        alarm_active = str(status.get("state", "")).lower() == "alarm"
        has_limits = self._limits.get("X") is not None and self._limits.get("Y") is not None
        self._read_limits_btn.setEnabled(connected and not streaming)
        self._travel_test_btn.setEnabled(connected and not streaming and has_limits and not alarm_active)
        self._explore_limits_btn.setEnabled(connected and not streaming)
        explore_action_enabled = connected and not streaming and not self._explore_active
        self._explore_z_btn.setEnabled(explore_action_enabled)
        self._z_speed_test_btn.setEnabled(explore_action_enabled)
        if self._explore_active:
            self._explore_limits_btn.setText("Stop Explore")
            self._read_limits_btn.setEnabled(False)
            self._travel_test_btn.setEnabled(False)
        else:
            self._explore_limits_btn.setText("Explore Limits")

    def _axis_explore_dir(self, axis):
        override = self._explore_dir_override.get(axis)
        if override is not None:
            return override
        if axis == "Z":
            choice = self._explore_z_dir.currentText()
            if choice == "+":
                return 1.0
            if choice == "-":
                return -1.0
        bit = {"X": 0, "Y": 1, "Z": 2}.get(axis, 0)
        homing_positive = bool(self._homing_dir_mask & (1 << bit))
        return -1.0 if homing_positive else 1.0

    def _expected_explore_limit(self, axis):
        if not self._explore_known_limits:
            return None
        value = self._explore_known_limits.get(axis)
        if value is None:
            return None
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    def _should_retry_explore_axis(self, axis, measured):
        if axis in self._explore_retry_axes:
            return False
        expected = self._expected_explore_limit(axis)
        if expected is not None:
            return measured < expected * 0.8
        return measured < self._explore_step * 2.0

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
