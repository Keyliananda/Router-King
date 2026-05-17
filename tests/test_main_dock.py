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
        self.cancelled = False
        self._status = status if status is not None else {"state": "Idle"}
        self._streaming = streaming

    def send_line(self, command):
        self.commands.append(command)

    def send_and_collect(self, command, timeout=5.0):
        self.commands.append(command)
        return ["ok"]

    def cancel_jog(self):
        self.cancelled = True

    def is_connected(self):
        return True

    def is_streaming(self):
        return self._streaming

    def get_status(self):
        return self._status


def _load_main_dock_module():
    sys.modules.pop("RouterKing.ui.main_dock", None)

    qtcore = types.SimpleNamespace(
        QObject=type("QObject", (), {}),
        QThread=type("QThread", (), {}),
        Signal=lambda *args, **kwargs: object(),
        Qt=types.SimpleNamespace(Horizontal=1, RightDockWidgetArea=2),
    )
    qtwidgets = types.SimpleNamespace(
        QWidget=type("QWidget", (), {}),
        QDialog=type("QDialog", (), {}),
        QDockWidget=type("QDockWidget", (), {}),
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

    def test_send_jog_advances_predicted_position_to_prevent_repeated_stale_status_overrun(self):
        main_dock = _load_main_dock_module()
        sender = _FakeConnectedSender(status={"state": "Idle", "MPos": "-299.800,-190.000,-25.000"})
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._explore_active = False
        widget._limits = {"X": 300.0, "Y": 380.0, "Z": 50.0}
        widget._append_console = mock.Mock()

        first = widget._send_jog(x=-0.5, feed=600, source="test")
        second = widget._send_jog(x=-0.5, feed=600, source="test")

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(sender.commands, ["$J=G91 X-0.200 F600"])

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
