import importlib
import sys
import types
import unittest
from unittest import mock


class _DummyWidget:
    def __init__(self):
        self.text = None
        self.enabled = None

    def setText(self, text):
        self.text = text

    def setEnabled(self, enabled):
        self.enabled = enabled


class _DummyLog:
    def __init__(self):
        self.lines = []

    def appendPlainText(self, text):
        self.lines.append(text)


class _DummyCheckBox(_DummyWidget):
    def __init__(self, checked=False):
        super().__init__()
        self._checked = checked

    def isChecked(self):
        return self._checked

    def setChecked(self, checked):
        self._checked = bool(checked)


class _DummySpin:
    def __init__(self, value):
        self._value = value

    def value(self):
        return self._value


class _DummyLineEdit:
    def __init__(self, text=""):
        self._text = text

    def text(self):
        return self._text

    def setText(self, text):
        self._text = str(text)


class _DummyCombo:
    def __init__(self, text="Iso"):
        self._text = text

    def currentText(self):
        return self._text


class _DummyPlainTextEdit:
    def __init__(self, text=""):
        self._text = text

    def toPlainText(self):
        return self._text

    def setPlainText(self, text):
        self._text = str(text)


class _DummyTimer:
    def __init__(self):
        self.stopped = False
        self.started = False

    def stop(self):
        self.stopped = True

    def start(self):
        self.started = True

    def isActive(self):
        return self.started and not self.stopped


class _FakeDisconnectedSender:
    def __init__(self, lines=None, reason="[serial error] serial lost"):
        self._lines = list(lines or [])
        self._reason = reason

    def poll(self):
        lines = list(self._lines)
        self._lines = []
        return lines

    def is_connected(self):
        return False

    def get_disconnect_reason(self):
        return self._reason

    def get_status(self):
        return None

    def get_progress(self):
        return {
            "streaming": False,
            "paused": False,
            "awaiting_ok": False,
            "sent": 0,
            "acked": 0,
            "total": 0,
            "last_error": self._reason,
        }

    def is_streaming(self):
        return False


class _FakeConnectedSender:
    def __init__(self, status=None, streaming=False):
        self.commands = []
        self.started_lines = None
        self.cancelled = False
        self._status = status if status is not None else {"state": "Idle"}
        self._streaming = streaming

    def send_line(self, command):
        self.commands.append(command)

    def send_and_collect(self, command, timeout=5.0):
        self.commands.append(command)
        return ["ok"]

    def start_stream(self, lines):
        self.started_lines = list(lines)
        self._streaming = True

    def cancel_jog(self):
        self.cancelled = True

    def is_connected(self):
        return True

    def is_streaming(self):
        return self._streaming

    def get_status(self):
        return self._status

    def get_progress(self):
        total = len(self.started_lines or [])
        return {
            "streaming": self._streaming,
            "paused": False,
            "awaiting_ok": False,
            "sent": 0,
            "acked": 0,
            "total": total,
            "last_error": None,
        }


def _load_main_dock_module():
    sys.modules.pop("RouterKing.ui.main_dock", None)

    class _QGraphicsView:
        ScrollHandDrag = 1
        NoDrag = 0
        AnchorUnderMouse = 2

        def __init__(self, *_args, **_kwargs):
            pass

        def setRenderHint(self, *_args, **_kwargs):
            pass

        def setDragMode(self, *_args, **_kwargs):
            pass

        def setTransformationAnchor(self, *_args, **_kwargs):
            pass

    qtcore = types.SimpleNamespace(
        QObject=type("QObject", (), {}),
        QThread=type("QThread", (), {}),
        Signal=lambda *args, **kwargs: object(),
        Slot=lambda *args, **kwargs: (lambda fn: fn),
        Qt=types.SimpleNamespace(Horizontal=1, RightDockWidgetArea=2, LeftButton=1, KeepAspectRatio=3),
        QPoint=lambda x, y: types.SimpleNamespace(x=lambda: x, y=lambda: y),
    )
    qtwidgets = types.SimpleNamespace(
        QWidget=type("QWidget", (), {}),
        QDialog=type("QDialog", (), {}),
        QDockWidget=type("QDockWidget", (), {}),
        QGraphicsView=_QGraphicsView,
        QApplication=type(
            "QApplication",
            (),
            {
                "topLevelWidgets": staticmethod(lambda: []),
                "processEvents": staticmethod(lambda: None),
            },
        ),
    )
    qtgui = types.SimpleNamespace(
        QFontDatabase=type(
            "QFontDatabase",
            (),
            {
                "FixedFont": 0,
                "systemFont": staticmethod(lambda *_args, **_kwargs: None),
            },
        )
    )

    pyside2 = types.ModuleType("PySide2")
    pyside2.QtCore = qtcore
    pyside2.QtWidgets = qtwidgets
    pyside2.QtGui = qtgui

    class _Prefs:
        def GetString(self, _key):
            return ""

        def SetString(self, _key, _value):
            return None

    freecad = types.ModuleType("FreeCAD")
    freecad.ParamGet = lambda _path: _Prefs()
    freecad.Console = types.SimpleNamespace(
        PrintError=lambda _text: None,
        PrintMessage=lambda _text: None,
    )

    freecad_gui = types.ModuleType("FreeCADGui")
    freecad_gui.addStatusMessage = lambda _text: None

    serial = types.ModuleType("serial")
    serial.Serial = object
    serial_tools = types.ModuleType("serial.tools")
    serial_list_ports = types.ModuleType("serial.tools.list_ports")
    serial_list_ports.comports = lambda: []
    serial_tools.list_ports = serial_list_ports
    serial.tools = serial_tools

    stubs = {
        "PySide2": pyside2,
        "FreeCAD": freecad,
        "FreeCADGui": freecad_gui,
        "serial": serial,
        "serial.tools": serial_tools,
        "serial.tools.list_ports": serial_list_ports,
    }
    with mock.patch.dict(sys.modules, stubs):
        return importlib.import_module("RouterKing.ui.main_dock")


class TestMainDock(unittest.TestCase):
    def _make_widget(self, main_dock, sender=None):
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender or _FakeDisconnectedSender()
        widget._poll_timer = _DummyTimer()
        widget._status_tick = 3
        widget._sender_was_connected = True
        widget._connection_status = _DummyWidget()
        widget._machine_status = _DummyWidget()
        widget._alarm_status = _DummyWidget()
        widget._job_status = _DummyWidget()
        widget._limit_x = _DummyWidget()
        widget._limit_y = _DummyWidget()
        widget._limit_z = _DummyWidget()
        widget._connect_btn = _DummyWidget()
        widget._port = _DummyWidget()
        widget._start_btn = _DummyWidget()
        widget._pause_btn = _DummyWidget()
        widget._stop_btn = _DummyWidget()
        widget._read_limits_btn = _DummyWidget()
        widget._travel_test_btn = _DummyWidget()
        widget._explore_limits_btn = _DummyWidget()
        widget._explore_z_btn = _DummyWidget()
        widget._z_speed_test_btn = _DummyWidget()
        widget._last_alarm_info = "Hard limit"
        widget._limits = {"X": 100.0, "Y": 200.0, "Z": 50.0}
        widget._limits_announced = True
        widget._last_console_line = None
        widget._explore_active = True
        widget._explore_phase = "move"
        widget._explore_axis_queue = ["X", "Y"]
        widget._explore_axis = "X"
        widget._explore_distance = 25.0
        widget._explore_pending = True
        widget._explore_next_action = 10.0
        widget._explore_results = {"X": 98.0}
        widget._explore_unlock_sent_at = 1.0
        widget._explore_unlocked = True
        widget._explore_last_command_at = 2.0
        widget._explore_recover_attempts = 1
        widget._explore_dir_override = {"X": 1, "Y": None, "Z": None}
        widget._explore_retry_axes = {"Y"}
        widget._explore_retry_axis = "Y"
        widget._explore_known_limits = {"X": 100.0}
        widget._explore_retry_measurements = {"Y": 90.0}
        widget._explore_ramp_remaining = 15.0
        widget._explore_ramp_feed = 400.0
        widget._explore_ramp_increment_current = 25.0
        widget._explore_ramp_max_feed_axis = 800.0
        widget._explore_ramp_last_step = 5.0
        widget._explore_preflight_sent = True
        widget._explore_preflight_started_at = 4.0
        widget._append_console = mock.Mock()
        widget._refresh_ports = mock.Mock()
        return widget

    def test_apply_disconnected_state_resets_explore_state(self):
        main_dock = _load_main_dock_module()
        widget = self._make_widget(main_dock)
        widget._update_limit_labels = mock.Mock()
        widget._update_job_controls = mock.Mock()
        widget._update_machine_controls = mock.Mock()

        with mock.patch.object(main_dock, "_status_message") as status_message:
            widget._apply_disconnected_state("Serial connection lost.", unexpected=True)

        self.assertTrue(widget._poll_timer.stopped)
        self.assertFalse(widget._sender_was_connected)
        self.assertFalse(widget._explore_active)
        self.assertIsNone(widget._explore_phase)
        self.assertEqual(widget._explore_axis_queue, [])
        self.assertIsNone(widget._explore_axis)
        self.assertFalse(widget._explore_pending)
        self.assertEqual(widget._explore_results, {})
        self.assertEqual(widget._explore_retry_axes, set())
        self.assertIsNone(widget._explore_retry_axis)
        self.assertEqual(widget._explore_retry_measurements, {})
        self.assertEqual(widget._explore_dir_override, {"X": None, "Y": None, "Z": None})
        self.assertFalse(widget._explore_preflight_sent)
        self.assertEqual(widget._connection_status.text, "Connection: disconnected")
        self.assertEqual(widget._connect_btn.text, "Connect")
        widget._refresh_ports.assert_called_once_with()
        widget._append_console.assert_called_once_with("Serial connection lost.", force=True)
        status_message.assert_called_once_with(
            "RouterKing: disconnected unexpectedly (Serial connection lost.)\n",
            error=True,
        )

    def test_drain_sender_applies_disconnect_state_for_active_job(self):
        main_dock = _load_main_dock_module()
        sender = _FakeDisconnectedSender(
            lines=["[serial error] serial lost"],
            reason="[serial error] serial lost",
        )
        widget = self._make_widget(main_dock, sender=sender)
        widget._handle_console_line = mock.Mock()
        widget._request_status = mock.Mock()
        widget._explore_tick = mock.Mock()

        with mock.patch.object(main_dock, "_status_message") as status_message:
            widget._drain_sender()

        widget._handle_console_line.assert_called_once_with("[serial error] serial lost")
        self.assertTrue(widget._poll_timer.stopped)
        self.assertFalse(widget._sender_was_connected)
        self.assertEqual(widget._connection_status.text, "Connection: disconnected")
        self.assertEqual(widget._machine_status.text, "Machine: n/a")
        self.assertEqual(widget._alarm_status.text, "Alarm: none")
        self.assertEqual(widget._job_status.text, "Job: idle")
        self.assertEqual(widget._connect_btn.text, "Connect")
        self.assertEqual(widget._pause_btn.text, "Pause")
        self.assertEqual(widget._explore_limits_btn.text, "Explore Limits")
        self.assertFalse(widget._start_btn.enabled)
        self.assertFalse(widget._pause_btn.enabled)
        self.assertFalse(widget._stop_btn.enabled)
        self.assertFalse(widget._sender_was_connected)
        widget._refresh_ports.assert_called_once_with()
        widget._append_console.assert_called_once_with("[serial error] serial lost", force=True)
        widget._explore_tick.assert_not_called()
        widget._request_status.assert_not_called()
        status_message.assert_called_once_with(
            "RouterKing: disconnected unexpectedly ([serial error] serial lost)\n",
            error=True,
        )

    def test_send_jog_builds_guarded_grbl_jog_command(self):
        main_dock = _load_main_dock_module()
        sender = _FakeConnectedSender(status={"state": "Idle", "MPos": "-150.000,-190.000,-25.000"})
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._explore_active = False
        widget._limits = {"X": 300.0, "Y": 380.0, "Z": 50.0}
        widget._append_console = mock.Mock()
        widget._send_jog(x=0.5, y=-0.25, z=0.0, feed=600, source="test")

        self.assertEqual(sender.commands, ["$J=G91 X0.500 Y-0.250 F600"])

    def test_send_jog_blocks_machine_limit_overrun(self):
        main_dock = _load_main_dock_module()
        sender = _FakeConnectedSender(status={"state": "Idle", "MPos": "-0.000,-190.000,-25.000"})
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._explore_active = False
        widget._limits = {"X": 300.0, "Y": 380.0, "Z": 50.0}
        widget._append_console = mock.Mock()

        result = widget._send_jog(x=0.5, feed=600, source="test")

        self.assertFalse(result)
        self.assertEqual(sender.commands, [])
        widget._append_console.assert_called_once()

    def test_send_jog_uses_margin_before_machine_limit(self):
        main_dock = _load_main_dock_module()
        sender = _FakeConnectedSender(status={"state": "Idle", "MPos": "-297.500,-190.000,-25.000"})
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._explore_active = False
        widget._limits = {"X": 300.0, "Y": 380.0, "Z": 50.0}
        widget._append_console = mock.Mock()

        first = widget._send_jog(x=-0.5, feed=600, source="test")
        second = widget._send_jog(x=-0.5, feed=600, source="test")

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(sender.commands, ["$J=G91 X-0.500 F600"])

    def test_send_jog_blocks_when_sender_streaming(self):
        main_dock = _load_main_dock_module()
        sender = _FakeConnectedSender(streaming=True)
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._explore_active = False
        widget._append_console = mock.Mock()
        result = widget._send_jog(x=0.5, feed=600, source="test")

        self.assertFalse(result)
        self.assertEqual(sender.commands, [])
        widget._append_console.assert_called_once()

    def test_prepare_manual_xyz_enables_controller_without_motion(self):
        main_dock = _load_main_dock_module()
        sender = _FakeConnectedSender()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._explore_active = False
        widget._controller_manual_clearance = _DummySpin(1.5)
        widget._controller_manual_xyz_active = False
        widget._controller_enable = _DummyCheckBox(False)
        widget._controller_timer = _DummyTimer()
        widget._controller = types.SimpleNamespace(is_connected=lambda: True)
        widget._append_console = mock.Mock()
        widget._request_status = mock.Mock()
        widget._update_machine_controls = mock.Mock()

        widget._on_prepare_manual_xyz()

        self.assertEqual(sender.commands, [])
        self.assertTrue(widget._controller_manual_xyz_active)
        self.assertTrue(widget._controller_enable.isChecked())
        self.assertTrue(widget._controller_timer.started)
        widget._request_status.assert_called_once_with()

    def test_prepare_manual_xyz_blocks_when_machine_not_idle(self):
        main_dock = _load_main_dock_module()
        sender = _FakeConnectedSender(status={"state": "Run"})
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._explore_active = False
        widget._append_console = mock.Mock()

        widget._on_prepare_manual_xyz()

        self.assertEqual(sender.commands, [])
        widget._append_console.assert_called_once()

    def test_set_manual_start_saves_live_position_without_motion(self):
        main_dock = _load_main_dock_module()
        sender = _FakeConnectedSender(
            status={
                "state": "Idle",
                "MPos": "-150.000,-190.000,-40.000",
                "WPos": "0.000,0.000,0.000",
                "WCO": "-150.000,-190.000,-40.000",
            }
        )
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._explore_active = False
        widget._manual_start_status = _DummyWidget()
        widget._append_console = mock.Mock()
        widget._update_job_controls = mock.Mock()

        widget._on_set_manual_start()

        self.assertEqual(sender.commands, [])
        self.assertEqual(widget._gcode_manual_start_wpos, {"x": 0.0, "y": 0.0, "z": 0.0})
        self.assertEqual(widget._manual_start_status.text, "Manual start: X0.000 Y0.000 Z0.000")

    def test_go_to_manual_start_safely_moves_z_before_xy(self):
        main_dock = _load_main_dock_module()
        sender = _FakeConnectedSender(
            status={
                "state": "Idle",
                "MPos": "-150.000,-190.000,-40.000",
                "WPos": "0.000,0.000,0.000",
                "WCO": "-150.000,-190.000,-40.000",
            }
        )
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._explore_active = False
        widget._gcode_manual_start_wpos = {"x": 12.0, "y": -3.0, "z": 0.0}
        widget._gcode_manual_start_wco = {"x": -150.0, "y": -190.0, "z": -40.0}
        widget._controller_manual_clearance = _DummySpin(1.5)
        widget._append_console = mock.Mock()
        widget._request_status = mock.Mock()

        widget._on_go_to_manual_start_safely()

        self.assertEqual(sender.commands, ["G90 G21", "G0 Z1.500", "G0 X12.000 Y-3.000"])
        widget._request_status.assert_called_once_with()

    def test_go_to_manual_start_blocks_when_work_offset_changed(self):
        main_dock = _load_main_dock_module()
        sender = _FakeConnectedSender(
            status={
                "state": "Idle",
                "MPos": "-150.000,-190.000,-40.000",
                "WPos": "0.000,0.000,0.000",
                "WCO": "-150.000,-190.000,-40.000",
            }
        )
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._explore_active = False
        widget._gcode_manual_start_wpos = {"x": 12.0, "y": -3.0, "z": 0.0}
        widget._gcode_manual_start_wco = {"x": -149.0, "y": -190.0, "z": -40.0}
        widget._append_console = mock.Mock()

        widget._on_go_to_manual_start_safely()

        self.assertEqual(sender.commands, [])
        widget._append_console.assert_called_once()

    def test_air_run_streams_transformed_validated_lines(self):
        main_dock = _load_main_dock_module()
        sender = _FakeConnectedSender(
            status={
                "state": "Idle",
                "MPos": "-150.000,-190.000,-40.000",
                "WPos": "0.000,0.000,0.000",
                "WCO": "-150.000,-190.000,-40.000",
            }
        )
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._gcode_edit = _DummyPlainTextEdit("G90\nM3 S10000\nG1 X1 Y2 Z-2 F500")
        widget._controller_manual_clearance = _DummySpin(1.5)
        widget._append_console = mock.Mock()
        widget._update_job_controls = mock.Mock()

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=({"settings": {}}, "/tmp/profile.json")):
            with mock.patch.object(
                main_dock,
                "grbl_validate_gcode",
                return_value={"valid": True, "line_count": 2, "bounding_box": {"x": [0, 1], "y": [0, 2], "z": [1.5, 1.5]}},
            ) as validate:
                widget._on_air_run()

        self.assertEqual(sender.started_lines, ["G90", "G1 X1 Y2 Z1.5 F500"])
        validate.assert_called_once()

    def test_show_apply_air_run_replaces_editor_without_machine_action(self):
        main_dock = _load_main_dock_module()
        sender = _FakeConnectedSender(status={"state": "Idle"})
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._gcode_edit = _DummyPlainTextEdit("G90\nM3 S10000\nG1 X1 Y2 Z-2 F500")
        widget._controller_manual_clearance = _DummySpin(1.5)
        widget._append_console = mock.Mock()
        widget._update_job_controls = mock.Mock()

        widget._on_show_apply_air_run()

        self.assertEqual(widget._gcode_edit.toPlainText(), "G90\nG1 X1 Y2 Z1.5 F500\n")
        self.assertEqual(sender.commands, [])
        self.assertIsNone(sender.started_lines)
        widget._append_console.assert_called_once_with(
            "Show/Apply Air Run: applied 2 transformed line(s); no machine commands sent.",
            force=True,
        )
        widget._update_job_controls.assert_called_once_with()

    def test_show_apply_air_run_enabled_without_connection(self):
        main_dock = _load_main_dock_module()
        widget = self._make_widget(main_dock)
        widget._gcode_edit = _DummyPlainTextEdit("G90\nG1 X1")
        widget._air_run_apply_btn = _DummyWidget()

        widget._update_job_controls()

        self.assertTrue(widget._air_run_apply_btn.enabled)

    def test_insert_template_uses_dialog_spec_and_records_last_spec(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        spec = main_dock.TemplateSpec(
            name="Test Pocket",
            width=20.0,
            height=10.0,
            depth=2.0,
            tool_diameter=2.0,
            step_down=1.0,
            step_over=1.0,
            feed_rate=400.0,
            plunge_rate=100.0,
            safe_z=5.0,
        )
        widget._gcode_edit = _DummyPlainTextEdit("")
        widget._show_rectangle_template_dialog = mock.Mock(return_value=spec)
        widget._append_console = mock.Mock()
        widget._update_preview = mock.Mock()
        widget._update_job_controls = mock.Mock()

        widget._on_insert_gcode_template()

        self.assertIs(widget._last_template_spec, spec)
        self.assertIn("; RouterKing rectangle pocket template: Test Pocket", widget._gcode_edit.toPlainText())
        self.assertIn("; size: 20 x 10 x 2 mm", widget._gcode_edit.toPlainText())
        widget._update_preview.assert_called_once_with()
        widget._update_job_controls.assert_called_once_with()

    def test_default_rectangle_template_uses_tee_tablett_preset(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._last_template_spec = None
        widget._manual_start_safe_z = mock.Mock(return_value=5.0)

        spec = widget._default_rectangle_template_spec()

        self.assertEqual(spec.name, "Tee-Tablett Pocket002 bottom-up 230 x 160 x 4 mm, 38 mm cutter")
        self.assertEqual(spec.width, 230.0)
        self.assertEqual(spec.height, 160.0)
        self.assertEqual(spec.depth, 4.0)
        self.assertEqual(spec.tool_diameter, 38.0)
        self.assertEqual(spec.safe_z, 6.0)

    def test_apply_template_start_snap_regenerates_with_selected_point(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._last_template_spec = main_dock.TemplateSpec(
            width=20.0,
            height=10.0,
            depth=2.0,
            tool_diameter=2.0,
            step_down=1.0,
            step_over=1.0,
            feed_rate=400.0,
            plunge_rate=100.0,
            safe_z=5.0,
        )
        widget._gcode_edit = _DummyPlainTextEdit("")
        widget._disable_template_snap = mock.Mock()
        widget._append_console = mock.Mock()
        widget._update_preview = mock.Mock()
        widget._update_job_controls = mock.Mock()
        point = types.SimpleNamespace(x=12.0, y=-3.0)

        widget._apply_template_start_snap(point)

        self.assertEqual(widget._last_template_spec.start_x, 0.0)
        self.assertEqual(widget._last_template_spec.start_y, 0.0)
        self.assertEqual(widget._last_template_spec.cut_start_x, 12.0)
        self.assertEqual(widget._last_template_spec.cut_start_y, -3.0)
        self.assertIn("; start: X0 Y0", widget._gcode_edit.toPlainText())
        self.assertIn("; cut start target: X12 Y-3", widget._gcode_edit.toPlainText())
        widget._disable_template_snap.assert_called_once_with()

    def test_read_template_controls_keeps_cut_start_and_records_source(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._last_template_spec = main_dock.TemplateSpec(
            width=20.0,
            height=10.0,
            depth=2.0,
            tool_diameter=2.0,
            step_down=1.0,
            step_over=1.0,
            feed_rate=400.0,
            plunge_rate=100.0,
            safe_z=5.0,
            cut_start_x=4.0,
            cut_start_y=5.0,
        )
        widget._template_controls = {
            "name": _DummyLineEdit("CAD Pocket"),
            "width": _DummySpin(230.0),
            "height": _DummySpin(160.0),
            "depth": _DummySpin(4.0),
            "tool_diameter": _DummySpin(3.0),
            "step_down": _DummySpin(1.0),
            "step_over": _DummySpin(1.05),
            "feed_rate": _DummySpin(800.0),
            "plunge_rate": _DummySpin(300.0),
            "safe_z": _DummySpin(6.0),
            "start_z": _DummySpin(0.0),
            "start_x": _DummySpin(1.0),
            "start_y": _DummySpin(2.0),
            "origin": _DummyCombo("center"),
            "swap_xy": _DummyCheckBox(True),
            "pass_axis": _DummyCombo("y"),
            "path_direction": _DummyCombo("reverse"),
            "final_contour": _DummyCheckBox(True),
            "contour_direction": _DummyCombo("ccw"),
        }
        widget._selected_template_source = mock.Mock(
            return_value={"document": "tee-tablett", "object": "Body", "feature": "Pocket002"}
        )

        spec = widget._read_rectangle_template_controls()

        self.assertEqual(spec.name, "CAD Pocket")
        self.assertEqual(spec.width, 230.0)
        self.assertTrue(spec.swap_xy)
        self.assertEqual(spec.pass_axis, "y")
        self.assertEqual(spec.path_direction, "reverse")
        self.assertTrue(spec.final_contour)
        self.assertEqual(spec.contour_direction, "ccw")
        self.assertEqual(spec.cut_start_x, 4.0)
        self.assertEqual(spec.cut_start_y, 5.0)
        self.assertEqual(spec.source_document, "tee-tablett")
        self.assertEqual(spec.source_object, "Body")
        self.assertEqual(spec.source_feature, "Pocket002")

    def test_template_cut_start_candidates_ignore_safe_z_points(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._last_template_spec = main_dock.TemplateSpec(
            width=20.0,
            height=10.0,
            depth=2.0,
            tool_diameter=2.0,
            step_down=1.0,
            step_over=1.0,
            feed_rate=400.0,
            plunge_rate=100.0,
            safe_z=5.0,
            start_z=0.0,
        )
        path = main_dock.parse_gcode_preview("G90\nG0 X1 Y2 Z5\nG1 Z-1\nG1 X3 Y2")

        candidates = widget._template_cut_start_candidates(path, "top")

        self.assertTrue(candidates)
        self.assertTrue(all(candidate.point.z <= 0.0 for candidate in candidates))

    def test_start_job_blocks_when_validation_fails(self):
        main_dock = _load_main_dock_module()
        sender = _FakeConnectedSender(status={"state": "Idle"})
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._gcode_edit = _DummyPlainTextEdit("G10 L20 P1 X0")
        widget._dry_run_check = _DummyCheckBox(False)
        widget._append_console = mock.Mock()

        widget._on_start_job()

        self.assertIsNone(sender.started_lines)
        widget._append_console.assert_called()

    def test_open_gcode_preview_reuses_existing_dialog(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        existing = mock.Mock()
        widget._preview_dialog = existing

        widget._on_open_gcode_preview()

        existing.refresh.assert_called_once_with()
        existing.show.assert_called_once_with()
        existing.raise_.assert_called_once_with()
        existing.activateWindow.assert_called_once_with()

    def test_update_preview_refreshes_visible_detached_preview(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._gcode_preview_projection = _DummyCombo("Top")
        widget._preview_scene = mock.Mock()
        widget._preview_view = mock.Mock()
        dialog = mock.Mock()
        dialog.isVisible.return_value = True
        widget._preview_dialog = dialog

        with mock.patch.object(widget, "_render_gcode_preview") as render:
            widget._update_preview()

        render.assert_called_once_with(widget._preview_scene, widget._preview_view, "top")
        dialog.refresh.assert_called_once_with()

    def test_mcp_machine_event_updates_visible_shared_sender_state(self):
        main_dock = _load_main_dock_module()
        sender = _FakeConnectedSender()
        sender._serial = types.SimpleNamespace(port="/dev/cu.test")
        widget = self._make_widget(main_dock, sender=sender)
        widget._explore_active = False
        widget._poll_timer = _DummyTimer()
        widget._mcp_status = _DummyWidget()
        widget._mcp_log = _DummyLog()
        widget._console_verbose = _DummyCheckBox(False)
        widget._console = _DummyLog()
        widget._last_console_line = None
        widget._drain_sender = mock.Mock()
        widget._update_job_controls = mock.Mock()
        widget._update_machine_controls = mock.Mock()

        widget._record_mcp_action_event("success", "machine_request_status", message="State: Idle")

        self.assertEqual(widget._mcp_status.text, "MCP ok: machine_request_status - State: Idle")
        self.assertEqual(widget._mcp_log.lines[-1], "MCP ok: machine_request_status - State: Idle")
        self.assertEqual(widget._connection_status.text, "Connection: connected (/dev/cu.test)")
        self.assertEqual(widget._connect_btn.text, "Disconnect")
        self.assertFalse(widget._port.enabled)
        self.assertTrue(widget._poll_timer.started)
        widget._drain_sender.assert_called_once_with()

    def test_append_controller_binding_token_deduplicates_and_saves(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        edit = _DummyLineEdit("Right X, DPad Right")
        widget._controller_binding_edits = {"x_axes": edit}
        widget._save_controller_defaults = mock.Mock()

        widget._append_controller_binding_token("x_axes", "Right X")
        widget._append_controller_binding_token("x_axes", "DPad Left")

        self.assertEqual(edit.text(), "Right X, DPad Right, DPad Left")
        self.assertEqual(widget._save_controller_defaults.call_count, 2)


if __name__ == "__main__":
    unittest.main()
