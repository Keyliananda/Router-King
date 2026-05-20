import importlib
import json
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

    def setValue(self, value):
        self._value = value


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

    def setCurrentText(self, text):
        self._text = str(text)


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
        sender = _FakeConnectedSender(
            status={
                "state": "Idle",
                "MPos": "-150.000,-190.000,-25.000",
                "WPos": "-150.000,-190.000,-25.000",
                "WCO": "0.000,0.000,0.000",
            }
        )
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._explore_active = False
        widget._limits = {"X": 300.0, "Y": 380.0, "Z": 50.0}
        widget._append_console = mock.Mock()
        widget._send_jog(x=0.5, y=-0.25, z=0.0, feed=600, source="test")

        self.assertEqual(sender.commands, ["$J=G91 X0.500 Y-0.250 F600"])

    def test_send_jog_blocks_machine_limit_overrun(self):
        main_dock = _load_main_dock_module()
        sender = _FakeConnectedSender(
            status={
                "state": "Idle",
                "MPos": "-0.000,-190.000,-25.000",
                "WPos": "-0.000,-190.000,-25.000",
                "WCO": "0.000,0.000,0.000",
            }
        )
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._explore_active = False
        widget._limits = {"X": 300.0, "Y": 380.0, "Z": 50.0}
        widget._append_console = mock.Mock()

        result = widget._send_jog(x=0.5, feed=600, source="test")

        self.assertFalse(result)
        self.assertEqual(sender.commands, [])
        widget._append_console.assert_called_once()

    def test_send_jog_recovers_guard_from_idle_wpos_wco_status_after_limit_block(self):
        main_dock = _load_main_dock_module()
        sender = _FakeConnectedSender(
            status={
                "state": "Idle",
                "WPos": "-150.000,-190.000,-25.000",
                "WCO": "0.000,0.000,0.000",
            }
        )
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._explore_active = False
        widget._limits = {"X": 300.0, "Y": 380.0, "Z": 50.0}
        widget._controller_guard_mpos = {"x": -2.0, "y": -190.0, "z": -25.0}
        widget._append_console = mock.Mock()

        blocked = widget._send_jog(x=0.5, feed=600, source="test")
        widget._update_controller_guard_position(sender.get_status())
        recovered = widget._send_jog(x=0.5, feed=600, source="test")

        self.assertFalse(blocked)
        self.assertTrue(recovered)
        self.assertEqual(sender.commands, ["$J=G91 X0.500 F600"])

    def test_send_jog_uses_margin_before_machine_limit(self):
        main_dock = _load_main_dock_module()
        sender = _FakeConnectedSender(
            status={
                "state": "Idle",
                "MPos": "-297.500,-190.000,-25.000",
                "WPos": "-297.500,-190.000,-25.000",
                "WCO": "0.000,0.000,0.000",
            }
        )
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._explore_active = False
        widget._limits = {"X": 300.0, "Y": 380.0, "Z": 50.0}
        widget._append_console = mock.Mock()

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=({}, "")):
            first = widget._send_jog(x=-0.5, feed=600, source="test")
            second = widget._send_jog(x=-0.5, feed=600, source="test")

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(sender.commands, ["$J=G91 X-0.500 F600"])

    def test_current_machine_limits_uses_settings_travel_with_profile_orientation(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._limits = {"X": None, "Y": None, "Z": None}
        profile = {
            "machine_limits": {"x": [0.0, 500.0], "y": [10.0, 210.0], "z": [-80.0, 20.0]},
            "settings": {"$130": "400.000", "$131": "400.000", "$132": "60.000"},
        }

        limits = widget._current_machine_limits(profile)

        self.assertEqual(limits, {"x": (0.0, 400.0), "y": (0.0, 400.0), "z": (-48.0, 12.0)})

    def test_current_machine_limits_orients_live_travel_like_profile_limits(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._limits = {"X": 410.0, "Y": 220.0, "Z": 70.0}
        profile = {
            "machine_limits": {"x": [0.0, 500.0], "y": [10.0, 210.0], "z": [-80.0, 20.0]},
            "settings": {"$130": "400.000", "$131": "400.000", "$132": "60.000"},
        }

        limits = widget._current_machine_limits(profile)

        self.assertEqual(limits, {"x": (0.0, 410.0), "y": (0.0, 220.0), "z": (-56.0, 14.0)})

    def test_current_machine_limits_ignores_stale_smaller_session_limits_when_profile_is_authoritative(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._limits = {"X": 300.0, "Y": 380.0, "Z": 50.0}
        profile = {
            "prefer_profile_limits": True,
            "machine_limits": {"x": [-400.0, 0.0], "y": [-400.0, 0.0], "z": [-60.0, 0.0]},
            "work_envelope_mm": {"x": 400.0, "y": 400.0, "z": 60.0},
            "settings": {"$130": "400.000", "$131": "400.000", "$132": "60.000"},
        }

        limits = widget._current_machine_limits(profile)

        self.assertEqual(limits, {"x": (-400.0, 0.0), "y": (-400.0, 0.0), "z": (-60.0, 0.0)})

    def test_send_jog_blocks_below_positive_oriented_dynamic_limits(self):
        main_dock = _load_main_dock_module()
        sender = _FakeConnectedSender(
            status={"state": "Idle", "MPos": "0.000,200.000,25.000", "WPos": "0.000,200.000,25.000"}
        )
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._explore_active = False
        widget._limits = {}
        widget._append_console = mock.Mock()
        profile = {
            "machine_limits": {"x": [0.0, 300.0], "y": [0.0, 300.0], "z": [0.0, 50.0]},
            "settings": {"$130": "400.000", "$131": "400.000", "$132": "60.000"},
        }

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=(profile, "/tmp/profile.json")):
            result = widget._send_jog(x=-0.5, feed=600, source="test")

        self.assertFalse(result)
        self.assertEqual(sender.commands, [])
        widget._append_console.assert_called_once()

    def test_send_jog_blocks_below_zero_at_negative_home_work_origin(self):
        main_dock = _load_main_dock_module()
        sender = _FakeConnectedSender(
            status={
                "state": "Idle",
                "MPos": "-297.000,-377.000,-3.000",
                "WPos": "0.000,0.000,0.000",
                "WCO": "-297.000,-377.000,-3.000",
            }
        )
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._explore_active = False
        widget._limits = {}
        widget._append_console = mock.Mock()
        profile = {"machine_limits": {"x": [-300.0, 0.0], "y": [-380.0, 0.0], "z": [-50.0, 0.0]}}

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=(profile, "/tmp/profile.json")):
            negative = widget._send_jog(x=-0.5, feed=600, source="test")
            positive = widget._send_jog(x=0.5, feed=600, source="test")

        self.assertFalse(negative)
        self.assertTrue(positive)
        self.assertEqual(sender.commands, ["$J=G91 X0.500 F600"])

    def test_send_jog_blocks_negative_y_at_zero_when_work_limits_end_at_zero(self):
        main_dock = _load_main_dock_module()
        sender = _FakeConnectedSender(
            status={
                "state": "Idle",
                "MPos": "0.000,0.000,-3.000",
                "WPos": "0.000,0.000,-3.000",
                "WCO": "0.000,0.000,0.000",
            }
        )
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._explore_active = False
        widget._limits = {}
        widget._append_console = mock.Mock()
        widget._request_status = mock.Mock()
        profile = {"machine_limits": {"x": [-400.0, 0.0], "y": [-400.0, 0.0], "z": [-60.0, 0.0]}}

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=(profile, "/tmp/profile.json")):
            result = widget._send_jog(y=-0.5, feed=600, source="test")

        self.assertFalse(result)
        self.assertEqual(sender.commands, [])
        widget._request_status.assert_called_once_with()

    def test_manual_xyz_blocks_negative_xy_from_prepare_origin_without_wpos(self):
        main_dock = _load_main_dock_module()
        sender = _FakeConnectedSender(status={"state": "Idle", "MPos": "-297.000,-377.000,-3.000"})
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._explore_active = False
        widget._limits = {"X": 400.0, "Y": 400.0, "Z": 60.0}
        widget._controller_manual_xyz_active = True
        widget._manual_xyz_prepare_mpos = {"x": -297.0, "y": -377.0, "z": -3.0}
        widget._manual_xyz_prepare_wpos = {"x": 0.0, "y": 0.0, "z": 0.0}
        widget._manual_xyz_work_origin_fallback = True
        widget._controller_guard_wpos = {"x": 0.0, "y": 0.0, "z": 0.0}
        widget._append_console = mock.Mock()
        widget._request_status = mock.Mock()
        profile = {
            "machine_limits": {"x": [-400.0, 0.0], "y": [-400.0, 0.0], "z": [-60.0, 0.0]},
            "settings": {"$23": "3"},
        }

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=(profile, "/tmp/profile.json")):
            negative_x = widget._send_jog(x=-0.5, feed=600, source="test")
            negative_y = widget._send_jog(y=-0.5, feed=600, source="test")
            positive_x = widget._send_jog(x=0.5, feed=600, source="test")

        self.assertFalse(negative_x)
        self.assertFalse(negative_y)
        self.assertTrue(positive_x)
        self.assertEqual(sender.commands, ["$J=G91 X0.500 F600"])

    def test_manual_xyz_fallback_uses_work_envelope_when_machine_position_starts_at_zero(self):
        main_dock = _load_main_dock_module()
        sender = _FakeConnectedSender(status={"state": "Idle", "MPos": "0.000,0.000,0.000"})
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._explore_active = False
        widget._limits = {"X": 400.0, "Y": 400.0, "Z": 60.0}
        widget._controller_manual_xyz_active = True
        widget._manual_xyz_prepare_wpos = {"x": 0.0, "y": 0.0, "z": 0.0}
        widget._manual_xyz_work_origin_fallback = True
        widget._controller_guard_wpos = {"x": 0.0, "y": 0.0, "z": 0.0}
        widget._append_console = mock.Mock()
        widget._request_status = mock.Mock()
        profile = {
            "machine_limits": {"x": [-400.0, 0.0], "y": [-400.0, 0.0], "z": [-60.0, 0.0]},
            "settings": {"$23": "3"},
        }

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=(profile, "/tmp/profile.json")):
            negative_x = widget._send_jog(x=-0.5, feed=600, source="test")
            positive_x = widget._send_jog(x=0.5, feed=600, source="test")

        self.assertFalse(negative_x)
        self.assertTrue(positive_x)
        self.assertEqual(sender.commands, ["$J=G91 X0.500 F600"])

    def test_manual_xyz_fallback_clamps_return_from_actual_status_not_sent_distance(self):
        main_dock = _load_main_dock_module()
        sender = _FakeConnectedSender(status={"state": "Idle", "MPos": "60.000,0.000,0.000"})
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._explore_active = False
        widget._limits = {"X": 400.0, "Y": 400.0, "Z": 60.0}
        widget._controller_manual_xyz_active = True
        widget._manual_xyz_prepare_mpos = {"x": 0.0, "y": 0.0, "z": 0.0}
        widget._manual_xyz_prepare_wpos = {"x": 0.0, "y": 0.0, "z": 0.0}
        widget._manual_xyz_work_origin_fallback = True
        widget._controller_guard_wpos = {"x": 80.0, "y": 0.0, "z": 0.0}
        widget._append_console = mock.Mock()
        widget._request_status = mock.Mock()
        profile = {
            "machine_limits": {"x": [-400.0, 0.0], "y": [-400.0, 0.0], "z": [-60.0, 0.0]},
            "settings": {"$23": "3"},
        }

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=(profile, "/tmp/profile.json")):
            result = widget._send_jog(x=-80.0, feed=600, source="test")

        self.assertTrue(result)
        self.assertEqual(sender.commands, ["$J=G91 X-58.000 F600"])
        widget._request_status.assert_called_once_with()

    def test_manual_xyz_treats_missing_work_status_as_fallback_even_if_flag_was_lost(self):
        main_dock = _load_main_dock_module()
        sender = _FakeConnectedSender(status={"state": "Idle", "MPos": "0.000,0.000,0.000"})
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._explore_active = False
        widget._limits = {"X": 400.0, "Y": 400.0, "Z": 60.0}
        widget._controller_manual_xyz_active = True
        widget._manual_xyz_prepare_mpos = {"x": 0.0, "y": 0.0, "z": 0.0}
        widget._manual_xyz_prepare_wpos = {"x": 0.0, "y": 0.0, "z": 0.0}
        widget._manual_xyz_work_origin_fallback = False
        widget._controller_guard_wpos = None
        widget._append_console = mock.Mock()
        widget._request_status = mock.Mock()
        profile = {
            "machine_limits": {"x": [-400.0, 0.0], "y": [-400.0, 0.0], "z": [-60.0, 0.0]},
            "settings": {"$23": "3"},
        }

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=(profile, "/tmp/profile.json")):
            negative_x = widget._send_jog(x=-0.5, feed=600, source="test")
            positive_x = widget._send_jog(x=0.5, feed=600, source="test")

        self.assertFalse(negative_x)
        self.assertTrue(positive_x)
        self.assertEqual(sender.commands, ["$J=G91 X0.500 F600"])

    def test_jog_without_explicit_wpos_uses_current_mpos_as_work_origin(self):
        main_dock = _load_main_dock_module()
        sender = _FakeConnectedSender(status={"state": "Idle", "MPos": "-297.000,-377.000,-3.000"})
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._explore_active = False
        widget._limits = {"X": 400.0, "Y": 400.0, "Z": 60.0}
        widget._append_console = mock.Mock()
        widget._request_status = mock.Mock()
        profile = {
            "machine_limits": {"x": [-400.0, 0.0], "y": [-400.0, 0.0], "z": [-60.0, 0.0]},
            "settings": {"$23": "3"},
        }

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=(profile, "/tmp/profile.json")):
            negative_x = widget._send_jog(x=-1.0, feed=600, source="test")
            positive_x = widget._send_jog(x=1.0, feed=600, source="test")

        self.assertFalse(negative_x)
        self.assertTrue(positive_x)
        self.assertEqual(sender.commands, ["$J=G91 X1.000 F600"])

    def test_jog_wco_without_wpos_still_uses_work_origin_fallback(self):
        main_dock = _load_main_dock_module()
        sender = _FakeConnectedSender(
            status={"state": "Idle", "MPos": "-298.000,-377.000,-3.000", "WCO": "0.000,0.000,1.000"}
        )
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._explore_active = False
        widget._limits = {"X": 400.0, "Y": 400.0, "Z": 60.0}
        widget._append_console = mock.Mock()
        widget._request_status = mock.Mock()
        profile = {
            "machine_limits": {"x": [-400.0, 0.0], "y": [-400.0, 0.0], "z": [-60.0, 0.0]},
            "settings": {"$23": "3"},
        }

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=(profile, "/tmp/profile.json")):
            result = widget._send_jog(x=-1.0, feed=600, source="test")

        self.assertFalse(result)
        self.assertEqual(sender.commands, [])

    def test_travel_test_uses_dynamic_machine_limit_interval(self):
        main_dock = _load_main_dock_module()
        sender = _FakeConnectedSender(status={"state": "Idle"})
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._limits = {"X": 400.0, "Y": 300.0, "Z": 60.0}
        widget._travel_margin = _DummySpin(3.0)
        widget._travel_feed = _DummySpin(500.0)
        widget._confirm_travel_test = mock.Mock(return_value=True)
        widget._append_console = mock.Mock()

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=({}, "")):
            widget._on_travel_test()

        self.assertEqual(
            sender.started_lines,
            [
                "G90",
                "G21",
                "G53 G1 X-3.000 Y-3.000 F500",
                "G53 G1 X-397.000 F500",
                "G53 G1 X-3.000",
                "G53 G1 Y-297.000 F500",
                "G53 G1 Y-3.000",
            ],
        )

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

    def test_jog_error_invalidates_guard_and_requests_status(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._controller_guard_mpos = {"x": -2.0, "y": -190.0, "z": -25.0}
        widget._controller_guard_mpos_at = 123.0
        widget._controller_was_active = True
        widget._explore_active = False
        widget._console_verbose = _DummyCheckBox(False)
        widget._append_console = mock.Mock()
        widget._request_status = mock.Mock()

        widget._handle_console_line("error:15")

        self.assertIsNone(widget._controller_guard_mpos)
        self.assertEqual(widget._controller_guard_mpos_at, 0.0)
        self.assertFalse(widget._controller_was_active)
        widget._request_status.assert_called_once_with()
        widget._append_console.assert_called_once_with("error:15", force=True)

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

    def test_manual_xyz_preview_position_tracks_live_wpos_without_saving_start(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._controller_manual_xyz_active = True
        widget._manual_xyz_preview_wpos = None
        widget._manual_xyz_preview_last_at = 0.0
        widget._schedule_preview_update = mock.Mock()
        status = {
            "MPos": "-140.000,-180.000,-39.000",
            "WPos": "10.000,10.000,1.000",
            "WCO": "-150.000,-190.000,-40.000",
        }

        widget._update_manual_xyz_preview_position(status, force=True)

        self.assertEqual(widget._manual_xyz_preview_wpos, {"x": 10.0, "y": 10.0, "z": 1.0})
        self.assertIsNone(getattr(widget, "_gcode_manual_start_wpos", None))
        widget._schedule_preview_update.assert_called_once_with()

    def test_manual_xyz_preview_keeps_visible_cut_start_on_prepare(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._controller_manual_xyz_active = True
        widget._manual_xyz_preview_wpos = None
        widget._manual_xyz_preview_last_at = 0.0
        widget._schedule_preview_update = mock.Mock()
        widget._gcode_edit = _DummyPlainTextEdit("G90\nG0 X80 Y100 Z6\nG1 Z-1 F300")
        widget._last_template_spec = None
        prepare_status = {
            "MPos": "-140.000,-180.000,-39.000",
            "WPos": "10.000,10.000,1.000",
            "WCO": "-150.000,-190.000,-40.000",
        }
        moved_status = {
            "MPos": "-135.000,-178.000,-39.000",
            "WPos": "15.000,12.000,1.000",
            "WCO": "-150.000,-190.000,-40.000",
        }

        widget._prepare_manual_xyz_preview_baseline(prepare_status)
        widget._update_manual_xyz_preview_position(prepare_status, force=True)
        widget._update_manual_xyz_preview_position(moved_status, force=True)

        self.assertEqual(widget._manual_xyz_preview_origin_wpos, {"x": 80.0, "y": 100.0, "z": 1.0})
        self.assertEqual(widget._manual_xyz_preview_wpos, {"x": 85.0, "y": 102.0, "z": 1.0})

    def test_manual_xyz_preview_delta_is_one_to_one_machine_mm(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._controller_manual_xyz_active = True
        widget._manual_xyz_preview_wpos = None
        widget._manual_xyz_preview_last_at = 0.0
        widget._schedule_preview_update = mock.Mock()
        widget._gcode_edit = _DummyPlainTextEdit("G90\nG1 X0 Y0 Z0")
        widget._last_template_spec = None
        prepare_status = {
            "MPos": "-297.000,-377.000,-3.000",
            "WPos": "0.000,0.000,0.000",
            "WCO": "-297.000,-377.000,-3.000",
        }
        moved_status = {
            "MPos": "-287.000,-372.000,-3.000",
            "WPos": "10.000,5.000,0.000",
            "WCO": "-297.000,-377.000,-3.000",
        }

        widget._prepare_manual_xyz_preview_baseline(prepare_status)
        widget._update_manual_xyz_preview_position(moved_status, force=True)

        self.assertEqual(widget._manual_xyz_preview_wpos, {"x": 10.0, "y": 5.0, "z": 0.0})

    def test_manual_xyz_preview_uses_local_origin_when_status_has_wco_without_wpos(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._controller_manual_xyz_active = True
        widget._manual_xyz_preview_wpos = None
        widget._manual_xyz_preview_last_at = 0.0
        widget._schedule_preview_update = mock.Mock()
        prepare_status = {
            "MPos": "-297.000,-377.000,-3.000",
            "WCO": "0.000,0.000,1.000",
        }
        moved_status = {
            "MPos": "-287.000,-372.000,-3.000",
            "WCO": "0.000,0.000,1.000",
        }

        widget._prepare_manual_xyz_preview_baseline(prepare_status)
        widget._update_manual_xyz_preview_position(moved_status, force=True)

        self.assertTrue(widget._manual_xyz_work_origin_fallback)
        self.assertEqual(widget._manual_xyz_preview_origin_wpos, {"x": 0.0, "y": 0.0, "z": 0.0})
        self.assertEqual(widget._manual_xyz_preview_wpos, {"x": 10.0, "y": 5.0, "z": 0.0})

    def test_manual_xyz_preview_keeps_visible_cut_start_when_status_has_only_mpos(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._controller_manual_xyz_active = True
        widget._manual_xyz_preview_wpos = None
        widget._manual_xyz_preview_last_at = 0.0
        widget._schedule_preview_update = mock.Mock()
        widget._gcode_edit = _DummyPlainTextEdit("G90\nG0 X80 Y100 Z0\nG1 X100 Y100 F500")
        prepare_status = {
            "state": "Idle",
            "MPos": "-297.000,-377.000,-3.000",
        }
        moved_status = {
            "state": "Idle",
            "MPos": "-292.000,-375.000,-3.000",
        }

        widget._prepare_manual_xyz_preview_baseline(prepare_status)
        widget._update_manual_xyz_preview_position(prepare_status, force=True)
        widget._update_manual_xyz_preview_position(moved_status, force=True)

        self.assertTrue(widget._manual_xyz_work_origin_fallback)
        self.assertEqual(widget._manual_xyz_preview_origin_wpos, {"x": 80.0, "y": 100.0, "z": 0.0})
        self.assertEqual(widget._manual_xyz_preview_wpos, {"x": 85.0, "y": 102.0, "z": 0.0})

    def test_manual_xyz_preview_moves_template_path_to_live_cut_start(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._controller_manual_xyz_active = True
        widget._manual_xyz_preview_wpos = {"x": 10.0, "y": 20.0, "z": 0.0}
        widget._last_template_spec = None
        widget._template_controls = {
            "name": _DummyLineEdit("Manual Preview Pocket"),
            "width": _DummySpin(40.0),
            "height": _DummySpin(30.0),
            "depth": _DummySpin(2.0),
            "tool_diameter": _DummySpin(4.0),
            "step_down": _DummySpin(1.0),
            "step_over": _DummySpin(2.0),
            "feed_rate": _DummySpin(500.0),
            "plunge_rate": _DummySpin(100.0),
            "safe_z": _DummySpin(6.0),
            "start_z": _DummySpin(0.0),
            "start_x": _DummySpin(0.0),
            "start_y": _DummySpin(0.0),
            "origin": _DummyCombo("center"),
            "swap_xy": _DummyCheckBox(False),
            "rotation_z": _DummyCombo("0"),
            "pass_axis": _DummyCombo("x"),
            "path_direction": _DummyCombo("forward"),
            "final_contour": _DummyCheckBox(False),
            "contour_direction": _DummyCombo("cw"),
        }
        widget._selected_template_source = mock.Mock(return_value={})

        path = widget._preview_path_from_current_state("")
        first_cut = next(segment.start for segment in path.segments if not segment.rapid)

        self.assertEqual(first_cut.x, 10.0)
        self.assertEqual(first_cut.y, 20.0)

    def test_manual_xyz_preview_maps_physical_xy_through_rotated_swapped_template(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._controller_manual_xyz_active = True
        widget._manual_xyz_preview_wpos = {"x": 10.0, "y": 20.0, "z": 0.0}
        widget._last_template_spec = None
        widget._template_controls = {
            "name": _DummyLineEdit("Manual Preview Pocket"),
            "width": _DummySpin(40.0),
            "height": _DummySpin(30.0),
            "depth": _DummySpin(2.0),
            "tool_diameter": _DummySpin(4.0),
            "step_down": _DummySpin(1.0),
            "step_over": _DummySpin(2.0),
            "feed_rate": _DummySpin(500.0),
            "plunge_rate": _DummySpin(100.0),
            "safe_z": _DummySpin(6.0),
            "start_z": _DummySpin(0.0),
            "start_x": _DummySpin(0.0),
            "start_y": _DummySpin(0.0),
            "origin": _DummyCombo("center"),
            "swap_xy": _DummyCheckBox(True),
            "rotation_z": _DummyCombo("90"),
            "pass_axis": _DummyCombo("x"),
            "path_direction": _DummyCombo("forward"),
            "final_contour": _DummyCheckBox(False),
            "contour_direction": _DummyCombo("cw"),
        }
        widget._selected_template_source = mock.Mock(return_value={})

        path = widget._preview_path_from_current_state("")
        first_cut = next(segment.start for segment in path.segments if not segment.rapid)
        tool_at_segment_z = main_dock.PreviewPoint(10.0, 20.0, first_cut.z)

        self.assertEqual((first_cut.x, first_cut.y), (10.0, 20.0))
        self.assertEqual(
            widget._preview_project_point(first_cut, "top", rotation_z=270),
            widget._preview_project_point(tool_at_segment_z, "top", rotation_z=270),
        )
        self.assertEqual(
            widget._preview_project_point(first_cut, "iso", rotation_z=270),
            widget._preview_project_point(tool_at_segment_z, "iso", rotation_z=270),
        )

    def test_manual_start_aligns_rotated_tee_tablett_pocket_to_lower_left_toolpath_corner(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        spec = main_dock.rectangle_pocket_preset("tee_tablett")

        aligned = widget._template_spec_aligned_to_manual_start(spec, {"x": 0.0, "y": 0.0, "z": 0.0})
        path = main_dock.parse_gcode_preview(main_dock.rectangle_pocket(aligned).gcode)
        cut_points = [
            point
            for segment in path.segments
            if not segment.rapid
            for point in (segment.start, segment.end)
        ]
        first_cut = next(segment.start for segment in path.segments if not segment.rapid)

        self.assertEqual(aligned.start_x, 61.0)
        self.assertEqual(aligned.start_y, 96.0)
        self.assertEqual((first_cut.x, first_cut.y), (0.0, 0.0))
        self.assertEqual(min(point.x for point in cut_points), 0.0)
        self.assertEqual(min(point.y for point in cut_points), 0.0)
        self.assertEqual(max(point.x for point in cut_points), 122.0)
        self.assertEqual(max(point.y for point in cut_points), 192.0)

    def test_preview_overlay_z_prefers_live_manual_xyz_position_while_active(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._controller_manual_xyz_active = True
        widget._manual_xyz_preview_wpos = {"x": 1.0, "y": 2.0, "z": 3.0}
        widget._gcode_manual_start_wpos = {"x": 4.0, "y": 5.0, "z": 6.0}

        self.assertEqual(widget._preview_overlay_z(), 3.0)

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
        self.assertEqual(spec.rotation_z, 90)

    def test_default_rectangle_template_loads_saved_settings(self):
        main_dock = _load_main_dock_module()
        store = {
            "last_spec_json": json.dumps(
                {
                    "name": "Saved Pocket",
                    "width": 230.0,
                    "height": 160.0,
                    "depth": 4.0,
                    "tool_diameter": 38.0,
                    "step_down": 1.0,
                    "step_over": 13.3,
                    "feed_rate": 800.0,
                    "plunge_rate": 300.0,
                    "safe_z": 6.0,
                    "start_z": 0.0,
                    "origin": "center",
                    "start_x": -80.0,
                    "start_y": -115.0,
                    "swap_xy": False,
                    "rotation_z": 90,
                    "pass_axis": "y",
                    "path_direction": "forward",
                    "final_contour": True,
                    "contour_direction": "ccw",
                    "cut_start_x": -19.0,
                    "cut_start_y": -19.0,
                }
            )
        }
        params = types.SimpleNamespace(
            GetString=lambda key, default="": store.get(key, default),
            SetString=lambda key, value: store.__setitem__(key, value),
        )
        with mock.patch.object(main_dock.App, "ParamGet", return_value=params):
            widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
            widget._last_template_spec = None
            widget._manual_start_safe_z = mock.Mock(return_value=5.0)
            spec = widget._default_rectangle_template_spec()

        self.assertEqual(spec.name, "Saved Pocket")
        self.assertEqual(spec.start_x, -80.0)
        self.assertEqual(spec.start_y, -115.0)
        self.assertEqual(spec.pass_axis, "y")
        self.assertTrue(spec.final_contour)
        self.assertEqual(spec.contour_direction, "ccw")
        self.assertEqual(spec.cut_start_x, -19.0)

    def test_save_rectangle_template_settings_persists_controls(self):
        main_dock = _load_main_dock_module()
        store = {}
        params = types.SimpleNamespace(
            GetString=lambda key, default="": store.get(key, default),
            SetString=lambda key, value: store.__setitem__(key, value),
        )
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._last_template_spec = None
        widget._template_controls = {
            "name": _DummyLineEdit("Saved Controls"),
            "width": _DummySpin(230.0),
            "height": _DummySpin(160.0),
            "depth": _DummySpin(4.0),
            "tool_diameter": _DummySpin(38.0),
            "step_down": _DummySpin(1.0),
            "step_over": _DummySpin(13.3),
            "feed_rate": _DummySpin(800.0),
            "plunge_rate": _DummySpin(300.0),
            "safe_z": _DummySpin(6.0),
            "start_z": _DummySpin(0.0),
            "start_x": _DummySpin(-80.0),
            "start_y": _DummySpin(-115.0),
            "origin": _DummyCombo("center"),
            "swap_xy": _DummyCheckBox(False),
            "rotation_z": _DummyCombo("90"),
            "pass_axis": _DummyCombo("y"),
            "path_direction": _DummyCombo("forward"),
            "final_contour": _DummyCheckBox(True),
            "contour_direction": _DummyCombo("ccw"),
        }
        widget._selected_template_source = mock.Mock(return_value={})
        widget._append_console = mock.Mock()

        with mock.patch.object(main_dock.App, "ParamGet", return_value=params):
            widget._on_save_rectangle_template_settings()

        saved = json.loads(store["last_spec_json"])
        self.assertEqual(saved["name"], "Saved Controls")
        self.assertEqual(saved["start_x"], -80.0)
        self.assertEqual(saved["start_y"], -115.0)
        self.assertEqual(saved["rotation_z"], 90)
        self.assertEqual(saved["pass_axis"], "y")
        self.assertTrue(saved["final_contour"])
        widget._append_console.assert_called_once()

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
            "rotation_z": _DummyCombo("90"),
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
        self.assertEqual(spec.rotation_z, 90)
        self.assertEqual(spec.pass_axis, "y")
        self.assertEqual(spec.path_direction, "reverse")
        self.assertTrue(spec.final_contour)
        self.assertEqual(spec.contour_direction, "ccw")
        self.assertEqual(spec.cut_start_x, 4.0)
        self.assertEqual(spec.cut_start_y, 5.0)
        self.assertEqual(spec.source_document, "tee-tablett")
        self.assertEqual(spec.source_object, "Body")
        self.assertEqual(spec.source_feature, "Pocket002")

    def test_use_manual_start_in_template_sets_cut_start_target_and_gcode(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._gcode_manual_start_wpos = {"x": 18.0, "y": 13.0, "z": 1.5}
        widget._last_template_spec = None
        widget._template_controls = {
            "name": _DummyLineEdit("Manual Pocket"),
            "width": _DummySpin(40.0),
            "height": _DummySpin(30.0),
            "depth": _DummySpin(2.0),
            "tool_diameter": _DummySpin(4.0),
            "step_down": _DummySpin(1.0),
            "step_over": _DummySpin(2.0),
            "feed_rate": _DummySpin(500.0),
            "plunge_rate": _DummySpin(100.0),
            "safe_z": _DummySpin(6.0),
            "start_z": _DummySpin(0.0),
            "start_x": _DummySpin(0.0),
            "start_y": _DummySpin(0.0),
            "origin": _DummyCombo("center"),
            "swap_xy": _DummyCheckBox(False),
            "rotation_z": _DummyCombo("0"),
            "pass_axis": _DummyCombo("x"),
            "path_direction": _DummyCombo("forward"),
            "final_contour": _DummyCheckBox(False),
            "contour_direction": _DummyCombo("cw"),
        }
        widget._selected_template_source = mock.Mock(return_value={})
        widget._gcode_edit = _DummyPlainTextEdit("")
        widget._append_console = mock.Mock()
        widget._update_preview = mock.Mock()
        widget._update_job_controls = mock.Mock()

        widget._on_use_manual_start_in_template()

        self.assertEqual(widget._template_controls["start_x"].value(), 36.0)
        self.assertEqual(widget._template_controls["start_y"].value(), 26.0)
        self.assertEqual(widget._template_controls["start_z"].value(), 1.5)
        self.assertEqual(widget._last_template_spec.start_x, 36.0)
        self.assertEqual(widget._last_template_spec.start_y, 26.0)
        self.assertEqual(widget._last_template_spec.cut_start_x, 18.0)
        self.assertEqual(widget._last_template_spec.cut_start_y, 13.0)
        self.assertIn("; start: X36 Y26", widget._gcode_edit.toPlainText())
        self.assertIn("; cut start target: X18 Y13", widget._gcode_edit.toPlainText())
        self.assertIn("G0 X18 Y13", widget._gcode_edit.toPlainText())
        widget._update_preview.assert_called_once_with()
        widget._update_job_controls.assert_called_once_with()

    def test_preview_work_area_converts_machine_limits_to_work_coordinates(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = _FakeConnectedSender(status={"WCO": "10.000,20.000,0.000"})
        widget._gcode_manual_start_wco = None
        profile = {"machine_limits": {"x": [-300.0, 0.0], "y": [-380.0, 0.0], "z": [-50.0, 0.0]}}

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=(profile, "/tmp/profile.json")):
            area = widget._preview_work_area()

        self.assertEqual(
            area,
            {"x_min": -310.0, "x_max": -10.0, "y_min": -400.0, "y_max": -20.0, "z_min": -50.0, "z_max": 0.0},
        )

    def test_preview_work_area_uses_current_z_limit_without_profile_z_default(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = _FakeConnectedSender(status={"WCO": "0.000,0.000,0.000"})
        widget._gcode_manual_start_wco = None
        widget._limits = {"X": None, "Y": None, "Z": 72.0}
        profile = {"machine_limits": {"x": [-300.0, 0.0], "y": [-380.0, 0.0]}}

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=(profile, "/tmp/profile.json")):
            area = widget._preview_work_area()

        self.assertEqual(
            area,
            {"x_min": -300.0, "x_max": 0.0, "y_min": -380.0, "y_max": 0.0, "z_min": -72.0, "z_max": 0.0},
        )

    def test_preview_work_area_requires_dynamic_z_limit(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = _FakeConnectedSender(status={"WCO": "0.000,0.000,0.000"})
        widget._gcode_manual_start_wco = None
        widget._limits = {"X": None, "Y": None, "Z": None}
        profile = {"machine_limits": {"x": [-300.0, 0.0], "y": [-380.0, 0.0]}}

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=(profile, "/tmp/profile.json")):
            area = widget._preview_work_area()

        self.assertIsNone(area)

    def test_preview_work_area_uses_live_negative_home_wco_without_shrinking_envelope(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = _FakeConnectedSender(status={"WCO": "-297.000,-377.000,-3.000"})
        widget._gcode_manual_start_wco = {"x": 0.0, "y": 0.0, "z": 0.0}
        profile = {"machine_limits": {"x": [-300.0, 0.0], "y": [-380.0, 0.0], "z": [-50.0, 0.0]}}

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=(profile, "/tmp/profile.json")):
            area = widget._preview_work_area()

        self.assertEqual(
            area,
            {"x_min": -3.0, "x_max": 297.0, "y_min": -3.0, "y_max": 377.0, "z_min": -47.0, "z_max": 3.0},
        )
        self.assertEqual(area["x_max"] - area["x_min"], 300.0)
        self.assertEqual(area["y_max"] - area["y_min"], 380.0)
        self.assertEqual(area["z_max"] - area["z_min"], 50.0)

    def test_preview_work_area_keeps_foxalien_profile_dimensions_with_live_wco(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = _FakeConnectedSender(status={"WCO": "-397.000,-397.000,-3.000"})
        widget._gcode_manual_start_wco = None
        profile = {
            "machine_limits": {"x": [-400.0, 0.0], "y": [-400.0, 0.0], "z": [-60.0, 0.0]},
            "settings": {"$23": "3", "$27": "3"},
            "prefer_profile_limits": True,
        }

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=(profile, "/tmp/profile.json")):
            area = widget._preview_work_area()
            home = widget._preview_home_point()

        self.assertEqual(area["x_max"] - area["x_min"], 400.0)
        self.assertEqual(area["y_max"] - area["y_min"], 400.0)
        self.assertEqual(area["z_max"] - area["z_min"], 60.0)
        self.assertEqual((home.x, home.y, home.z), (0.0, 0.0, 0.0))

    def test_manual_xyz_home_stays_work_area_home_when_status_has_wco_without_wpos(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = _FakeConnectedSender(status={"MPos": "-264.900,-339.475,-3.000", "WCO": "0.000,0.000,1.000"})
        widget._controller_manual_xyz_active = True
        widget._manual_xyz_preview_wpos = None
        widget._manual_xyz_preview_last_at = 0.0
        widget._schedule_preview_update = mock.Mock()
        widget._gcode_manual_start_wco = None
        profile = {
            "machine_limits": {"x": [-300.0, 0.0], "y": [-380.0, 0.0], "z": [-50.0, 0.0]},
            "settings": {"$23": "3", "$27": "3"},
        }

        widget._prepare_manual_xyz_preview_baseline(widget._sender.get_status())
        widget._update_manual_xyz_preview_position(widget._sender.get_status(), force=True)
        path = main_dock.parse_gcode_preview("G90\nG0 X230 Y160 Z6\nG1 Z-1 F300")

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=(profile, "/tmp/profile.json")):
            home = widget._preview_home_point()
            cut_start = widget._preview_cut_start_point(path)

        self.assertAlmostEqual(home.x, -32.1)
        self.assertAlmostEqual(home.y, -37.525)
        self.assertEqual((cut_start.x, cut_start.y, cut_start.z), (0.0, 0.0, 0.0))
        self.assertNotEqual(widget._preview_project_point(home, "top"), widget._preview_project_point(cut_start, "top"))
        self.assertNotEqual(widget._preview_project_point(home, "iso"), widget._preview_project_point(cut_start, "iso"))

    def test_manual_xyz_work_area_uses_prepare_baseline_instead_of_stale_live_wco(self):
        main_dock = _load_main_dock_module()
        status = {"MPos": "-264.900,-339.475,-3.000", "WCO": "0.000,0.000,1.000"}
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = _FakeConnectedSender(status=status)
        widget._controller_manual_xyz_active = True
        widget._manual_xyz_preview_wpos = None
        widget._manual_xyz_preview_last_at = 0.0
        widget._schedule_preview_update = mock.Mock()
        widget._gcode_manual_start_wco = None
        profile = {
            "machine_limits": {"x": [-300.0, 0.0], "y": [-380.0, 0.0], "z": [-50.0, 0.0]},
            "settings": {"$23": "3", "$27": "3"},
        }

        widget._prepare_manual_xyz_preview_baseline(status)
        widget._update_manual_xyz_preview_position(status, force=True)

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=(profile, "/tmp/profile.json")):
            area = widget._preview_work_area()

        expected = {
            "x_min": -35.1,
            "x_max": 264.9,
            "y_min": -40.525,
            "y_max": 339.475,
            "z_min": -47.0,
            "z_max": 3.0,
        }
        for key, value in expected.items():
            self.assertAlmostEqual(area[key], value)

    def test_manual_xyz_home_marker_stays_work_area_home_while_cut_start_tracks_tool(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = _FakeConnectedSender(status={"WCO": "-397.000,-397.000,-3.000"})
        widget._controller_manual_xyz_active = True
        widget._manual_xyz_preview_wpos = {"x": 7.0, "y": 8.0, "z": 0.0}
        profile = {
            "machine_limits": {"x": [-400.0, 0.0], "y": [-400.0, 0.0], "z": [-60.0, 0.0]},
            "settings": {"$23": "3", "$27": "3"},
        }

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=(profile, "/tmp/profile.json")):
            home = widget._preview_home_point()
            cut_start = widget._preview_cut_start_point(None)

        self.assertEqual((home.x, home.y), (0.0, 0.0))
        self.assertEqual((cut_start.x, cut_start.y), (7.0, 8.0))
        self.assertNotEqual(
            widget._preview_project_point(home, "top"),
            widget._preview_project_point(cut_start, "top"),
        )

    def test_preview_work_area_derives_wco_from_mpos_and_wpos_when_status_lacks_wco(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = _FakeConnectedSender(
            status={"MPos": "-297.000,-377.000,-3.000", "WPos": "0.000,0.000,0.000"}
        )
        widget._gcode_manual_start_wco = {"x": 100.0, "y": 100.0, "z": 0.0}
        profile = {"machine_limits": {"x": [-300.0, 0.0], "y": [-380.0, 0.0], "z": [-50.0, 0.0]}}

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=(profile, "/tmp/profile.json")):
            area = widget._preview_work_area()

        self.assertEqual(
            area,
            {"x_min": -3.0, "x_max": 297.0, "y_min": -3.0, "y_max": 377.0, "z_min": -47.0, "z_max": 3.0},
        )

    def test_preview_work_area_derives_wco_from_template_cut_start_when_disconnected(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = _FakeDisconnectedSender()
        widget._gcode_manual_start_wco = None
        widget._gcode_manual_start_wpos = None
        widget._controller_manual_xyz_active = False
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
            cut_start_x=0.0,
            cut_start_y=0.0,
        )
        profile = {
            "machine_limits": {"x": [-300.0, 0.0], "y": [-380.0, 0.0], "z": [-50.0, 0.0]},
            "settings": {"$23": "3", "$27": "3"},
        }

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=(profile, "/tmp/profile.json")):
            area = widget._preview_work_area()
            home = widget._preview_home_point()

        self.assertEqual(
            area,
            {"x_min": -3.0, "x_max": 297.0, "y_min": -3.0, "y_max": 377.0, "z_min": -47.0, "z_max": 3.0},
        )
        self.assertEqual((home.x, home.y), (0.0, 0.0))

    def test_preview_work_area_does_not_invent_wco_from_gcode_when_connected_status_lacks_wco(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = _FakeConnectedSender(status={"MPos": "-229.000,-331.000,-3.000"})
        widget._gcode_manual_start_wco = None
        widget._gcode_manual_start_wpos = None
        widget._controller_manual_xyz_active = False
        widget._gcode_edit = _DummyPlainTextEdit("G90\nG0 X80 Y100\nG1 Z-1 F300")
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
            cut_start_x=80.0,
            cut_start_y=100.0,
        )
        profile = {"machine_limits": {"x": [-400.0, 0.0], "y": [-400.0, 0.0], "z": [-60.0, 0.0]}}

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=(profile, "/tmp/profile.json")):
            area = widget._preview_work_area()

        self.assertEqual(area, {"x_min": -400.0, "x_max": 0.0, "y_min": -400.0, "y_max": 0.0, "z_min": -60.0, "z_max": 0.0})

    def test_preview_cut_start_marker_uses_actual_first_cut_over_stale_template_target(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._controller_manual_xyz_active = False
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
            cut_start_x=99.0,
            cut_start_y=88.0,
        )
        path = main_dock.parse_gcode_preview("G90\nG0 X4 Y5 Z2\nG1 Z-1 F300\nG1 X7 Y5 F400")

        point = widget._preview_cut_start_point(path)

        self.assertEqual((point.x, point.y, point.z), (4.0, 5.0, 2.0))

    def test_preview_display_path_reanchors_leading_rapid_to_home(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        path = main_dock.parse_gcode_preview("G90\nG0 X100 Y100 Z6\nG1 Z-1 F300\nG1 X110 Y100 F400")
        widget._preview_home_point = mock.Mock(return_value=main_dock.PreviewPoint(10.0, 20.0, 0.0))

        display_path = widget._preview_path_for_display(path)

        self.assertEqual(len(display_path.segments), 3)
        self.assertTrue(display_path.segments[0].rapid)
        self.assertEqual(display_path.segments[0].motion, "HOME")
        self.assertEqual((display_path.segments[0].start.x, display_path.segments[0].start.y), (10.0, 20.0))
        self.assertEqual((display_path.segments[0].end.x, display_path.segments[0].end.y), (100.0, 100.0))
        self.assertFalse(display_path.segments[1].rapid)

    def test_manual_xyz_preview_display_path_does_not_add_home_lead_to_cut_start(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        path = main_dock.parse_gcode_preview("G90\nG0 X100 Y100 Z6\nG1 Z-1 F300\nG1 X110 Y100 F400")
        widget._controller_manual_xyz_active = True
        widget._manual_xyz_preview_wpos = {"x": 100.0, "y": 100.0, "z": 0.0}
        widget._preview_home_point = mock.Mock(return_value=main_dock.PreviewPoint(10.0, 20.0, 0.0))

        display_path = widget._preview_path_for_display(path)

        self.assertEqual(len(display_path.segments), 2)
        self.assertFalse(any(segment.motion == "HOME" for segment in display_path.segments))
        self.assertFalse(display_path.segments[0].rapid)
        self.assertEqual((display_path.segments[0].start.x, display_path.segments[0].start.y), (100.0, 100.0))

    def test_manual_xyz_preview_display_path_trims_setup_rapid_without_home_point(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        path = main_dock.parse_gcode_preview("G90\nG0 X100 Y100 Z6\nG1 Z-1 F300\nG1 X110 Y100 F400")
        widget._controller_manual_xyz_active = True
        widget._preview_home_point = mock.Mock(return_value=None)

        display_path = widget._preview_path_for_display(path)

        self.assertEqual(len(display_path.segments), 2)
        self.assertFalse(any(segment.motion == "HOME" for segment in display_path.segments))
        self.assertFalse(display_path.segments[0].rapid)
        self.assertEqual((display_path.segments[0].start.x, display_path.segments[0].start.y), (100.0, 100.0))

    def test_preview_display_path_does_not_add_home_lead_when_xy_start_matches_home(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        path = main_dock.parse_gcode_preview("G90\nG0 X10 Y20 Z6\nG1 Z-1 F300\nG1 X15 Y20 F400")
        widget._preview_home_point = mock.Mock(return_value=main_dock.PreviewPoint(10.0, 20.0, 0.0))

        display_path = widget._preview_path_for_display(path)

        self.assertEqual(len(display_path.segments), 2)
        self.assertFalse(display_path.segments[0].rapid)

    def test_machine_profile_from_controls_persists_foxalien_travel_settings(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._machine_profile_controls = {
            "model": _DummyLineEdit("FoxAlien Masuter Pro"),
            "x": _DummySpin(400.0),
            "y": _DummySpin(400.0),
            "z": _DummySpin(60.0),
            "pull_off": _DummySpin(3.0),
        }

        profile = widget._machine_profile_from_controls({"settings": {"$130": "300.000"}})

        self.assertEqual(profile["model"], "FoxAlien Masuter Pro")
        self.assertEqual(profile["machine_limits"], {"x": [-400.0, 0.0], "y": [-400.0, 0.0], "z": [-60.0, 0.0]})
        self.assertEqual(profile["work_envelope_mm"], {"x": 400.0, "y": 400.0, "z": 60.0})
        self.assertEqual(profile["settings"]["$130"], "400.000")
        self.assertEqual(profile["settings"]["$131"], "400.000")
        self.assertEqual(profile["settings"]["$132"], "60.000")
        self.assertEqual(profile["settings"]["$27"], "3.000")

    def test_preview_display_transform_keeps_machine_xy_without_mutating_point(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        point = main_dock.PreviewPoint(2.0, 4.0, -1.0)

        display = widget._preview_display_point(point)
        projected = widget._preview_project_point(point, "top")

        self.assertEqual((display.x, display.y, display.z), (2.0, 4.0, -1.0))
        self.assertEqual(projected, (2.0, -4.0))
        rotated = widget._preview_display_point(point, rotation_z=90)
        self.assertEqual((rotated.x, rotated.y, rotated.z), (-4.0, 2.0, -1.0))

    def test_preview_transform_is_shared_by_top_and_iso_projection(self):
        main_dock = _load_main_dock_module()
        transform = main_dock.PreviewTransform(swap_xy=True, rotation_z=180)
        point = main_dock.PreviewPoint(10.0, 40.0, -3.0)

        world = transform.point(point)

        self.assertEqual((world.x, world.y, world.z), (-40.0, -10.0, -3.0))
        self.assertEqual(transform.project(point, "top"), main_dock.project_point(world, "top"))
        self.assertEqual(transform.project(point, "iso"), main_dock.project_point(world, "iso"))

    def test_preview_snap_candidates_use_same_transform_as_rendered_iso_path(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        path = main_dock.parse_gcode_preview("G90\nG1 X10 Y5 Z-1")

        display_path = widget._preview_display_path(path, rotation_z=90)
        candidates = widget._preview_snap_candidates(path, "iso", rotation_z=90)

        self.assertEqual(candidates[-1].projected, main_dock.project_point(display_path.segments[-1].end, "iso"))

    def test_preview_snap_candidates_keep_machine_coordinates_but_project_machine_view(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        path = main_dock.parse_gcode_preview("G90\nG1 X10 Y5")

        candidates = widget._preview_snap_candidates(path, "top")

        self.assertEqual(candidates[-1].point.x, 10.0)
        self.assertEqual(candidates[-1].point.y, 5.0)
        self.assertEqual(candidates[-1].projected, (10.0, -5.0))
        rotated = widget._preview_snap_candidates(path, "top", rotation_z=90)
        self.assertEqual(rotated[-1].projected, (-5.0, -10.0))

    def test_fit_candidates_place_each_rectangle_corner_inside_work_area(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        spec = main_dock.TemplateSpec(
            width=40.0,
            height=30.0,
            depth=2.0,
            tool_diameter=4.0,
            step_down=1.0,
            step_over=2.0,
            feed_rate=500.0,
            plunge_rate=100.0,
            safe_z=6.0,
            origin="center",
        )
        area = {"x_min": 0.0, "x_max": 100.0, "y_min": 0.0, "y_max": 100.0}

        candidates = widget._template_fit_candidates_for_point(spec, 50.0, 50.0, area)

        self.assertEqual([candidate["corner"] for candidate in candidates[:4]], [
            "lower_left",
            "lower_right",
            "upper_left",
            "upper_right",
        ])
        self.assertEqual([candidate["rotation_z"] for candidate in candidates[:4]], [0, 0, 0, 0])
        self.assertEqual([candidate["rotation_z"] for candidate in candidates[4:]], [90, 90, 90, 90])
        self.assertEqual(candidates[0]["start_x"], 70.0)
        self.assertEqual(candidates[0]["start_y"], 65.0)
        self.assertEqual(candidates[3]["start_x"], 30.0)
        self.assertEqual(candidates[3]["start_y"], 35.0)

    def test_fit_candidates_use_z_rotation_for_effective_size(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        spec = main_dock.TemplateSpec(
            width=40.0,
            height=30.0,
            depth=2.0,
            tool_diameter=4.0,
            step_down=1.0,
            step_over=2.0,
            feed_rate=500.0,
            plunge_rate=100.0,
            safe_z=6.0,
            origin="center",
            rotation_z=90,
        )
        area = {"x_min": 0.0, "x_max": 100.0, "y_min": 0.0, "y_max": 100.0}

        candidates = widget._template_fit_candidates_for_point(spec, 50.0, 50.0, area)

        self.assertEqual(candidates[0]["start_x"], 65.0)
        self.assertEqual(candidates[0]["start_y"], 70.0)
        self.assertEqual(candidates[0]["bounds"], {
            "x_min": 50.0,
            "x_max": 80.0,
            "y_min": 50.0,
            "y_max": 90.0,
        })

    def test_apply_fit_candidate_updates_template_start_and_preview_gcode(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._template_controls = {
            "name": _DummyLineEdit("Fit Pocket"),
            "width": _DummySpin(40.0),
            "height": _DummySpin(30.0),
            "depth": _DummySpin(2.0),
            "tool_diameter": _DummySpin(4.0),
            "step_down": _DummySpin(1.0),
            "step_over": _DummySpin(2.0),
            "feed_rate": _DummySpin(500.0),
            "plunge_rate": _DummySpin(100.0),
            "safe_z": _DummySpin(6.0),
            "start_z": _DummySpin(0.0),
            "start_x": _DummySpin(0.0),
            "start_y": _DummySpin(0.0),
            "origin": _DummyCombo("center"),
            "swap_xy": _DummyCheckBox(False),
            "rotation_z": _DummyCombo("0"),
            "pass_axis": _DummyCombo("x"),
            "path_direction": _DummyCombo("forward"),
            "final_contour": _DummyCheckBox(False),
            "contour_direction": _DummyCombo("cw"),
        }
        widget._selected_template_source = mock.Mock(return_value={})
        widget._select_template_source = mock.Mock()
        widget._gcode_edit = _DummyPlainTextEdit("")
        widget._append_console = mock.Mock()
        widget._update_preview = mock.Mock()
        widget._update_job_controls = mock.Mock()
        widget._fit_status = _DummyWidget()
        widget._template_fit_candidates = [
            {
                "corner": "lower_left",
                "rotation_z": 90,
                "start_x": 70.0,
                "start_y": 65.0,
                "cut_start_x": 50.0,
                "cut_start_y": 50.0,
                "bounds": {"x_min": 50.0, "x_max": 90.0, "y_min": 50.0, "y_max": 80.0},
            }
        ]

        widget._apply_template_fit_candidate(0)

        self.assertEqual(widget._template_controls["start_x"].value(), 70.0)
        self.assertEqual(widget._template_controls["start_y"].value(), 65.0)
        self.assertEqual(widget._template_controls["rotation_z"].currentText(), "90")
        self.assertEqual(widget._last_template_spec.rotation_z, 90)
        self.assertEqual(widget._last_template_spec.cut_start_x, 50.0)
        self.assertEqual(widget._last_template_spec.cut_start_y, 50.0)
        self.assertIn("; start: X70 Y65", widget._gcode_edit.toPlainText())
        self.assertIn("; cut start target: X50 Y50", widget._gcode_edit.toPlainText())
        self.assertEqual(widget._fit_status.text, "Fit: 1/1 LL 90deg")

    def test_fit_status_distinguishes_unpicked_and_failed_fit(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._fit_status = _DummyWidget()
        widget._template_fit_candidates = []
        widget._template_fit_index = None
        widget._template_fit_pick_active = False
        widget._template_fit_point = None

        widget._update_fit_status()
        self.assertEqual(widget._fit_status.text, "Fit: pick corner")

        widget._template_fit_point = {"x": 999.0, "y": 999.0}
        widget._update_fit_status()
        self.assertEqual(widget._fit_status.text, "Fit: no placement")

        widget._template_fit_pick_active = True
        widget._update_fit_status()
        self.assertEqual(widget._fit_status.text, "Fit: picking")

    def test_preview_home_point_uses_homing_direction_and_work_offset(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = _FakeConnectedSender(status={"WCO": "10.000,20.000,0.000"})
        widget._gcode_manual_start_wco = None
        widget._last_template_spec = None
        profile = {
            "machine_limits": {"x": [-300.0, 0.0], "y": [-380.0, 0.0], "z": [-50.0, 0.0]},
            "homing": {"directions": {"x": "positive", "y": "positive"}, "pull_off_mm": 0.0},
        }

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=(profile, "/tmp/profile.json")):
            point = widget._preview_home_point()

        self.assertEqual(point.x, -10.0)
        self.assertEqual(point.y, -20.0)

    def test_preview_home_point_uses_post_homing_pull_off_position(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = _FakeConnectedSender(status={"WCO": "-297.000,-377.000,-3.000"})
        widget._gcode_manual_start_wco = None
        widget._last_template_spec = None
        profile = {
            "machine_limits": {"x": [-300.0, 0.0], "y": [-380.0, 0.0], "z": [-50.0, 0.0]},
            "settings": {"$23": "3", "$27": "3"},
            "homing": {"directions": {"x": "positive", "y": "positive"}},
        }

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=(profile, "/tmp/profile.json")):
            point = widget._preview_home_point()

        self.assertEqual(point.x, 0.0)
        self.assertEqual(point.y, 0.0)

    def test_preview_home_and_manual_cut_start_project_to_same_point_at_post_homing_wco(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = _FakeConnectedSender(status={"WCO": "-297.000,-377.000,-3.000"})
        widget._gcode_manual_start_wco = None
        widget._last_template_spec = None
        widget._controller_manual_xyz_active = True
        widget._manual_xyz_preview_wpos = {"x": 0.0, "y": 0.0, "z": 0.0}
        profile = {
            "machine_limits": {"x": [-300.0, 0.0], "y": [-380.0, 0.0], "z": [-50.0, 0.0]},
            "settings": {"$23": "3", "$27": "3"},
        }

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=(profile, "/tmp/profile.json")):
            home = widget._preview_home_point()
        cut_start = widget._preview_cut_start_point(None)

        self.assertEqual((home.x, home.y), (0.0, 0.0))
        self.assertEqual((cut_start.x, cut_start.y), (0.0, 0.0))
        self.assertEqual(widget._preview_project_point(home, "top"), widget._preview_project_point(cut_start, "top"))
        self.assertEqual(widget._preview_project_point(home, "iso"), widget._preview_project_point(cut_start, "iso"))
        self.assertEqual(widget._preview_project_point(home, "iso", rotation_z=180), widget._preview_project_point(cut_start, "iso", rotation_z=180))

    def test_preview_home_point_prefers_grbl_homing_mask_over_stale_direction_labels(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = _FakeConnectedSender(status={"WCO": "10.000,20.000,0.000"})
        widget._gcode_manual_start_wco = None
        widget._last_template_spec = None
        profile = {
            "machine_limits": {"x": [-300.0, 0.0], "y": [-380.0, 0.0], "z": [-50.0, 0.0]},
            "settings": {"$23": "3", "$27": "3"},
            "homing": {"directions": {"x": "positive", "y": "positive"}},
        }

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=(profile, "/tmp/profile.json")):
            point = widget._preview_home_point()

        self.assertEqual(point.x, -307.0)
        self.assertEqual(point.y, -397.0)

    def test_preview_cut_start_point_uses_actual_first_cut_before_template_fallback(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._controller_manual_xyz_active = False
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
            cut_start_x=12.0,
            cut_start_y=-3.0,
        )
        path = main_dock.parse_gcode_preview("G90\nG0 X1 Y2 Z5\nG1 Z-1\nG1 X3 Y2")

        point = widget._preview_cut_start_point(path)

        self.assertEqual(point.x, 1.0)
        self.assertEqual(point.y, 2.0)

        fallback = widget._preview_cut_start_point(None)
        self.assertEqual(fallback.x, 12.0)
        self.assertEqual(fallback.y, -3.0)

    def test_preview_cut_start_point_prefers_live_manual_xyz_position(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._controller_manual_xyz_active = True
        widget._manual_xyz_preview_wpos = {"x": 7.0, "y": 8.0, "z": 9.0}
        widget._gcode_manual_start_wpos = None
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
            cut_start_x=12.0,
            cut_start_y=-3.0,
        )
        path = main_dock.parse_gcode_preview("G90\nG0 X1 Y2 Z5\nG1 Z-1\nG1 X3 Y2")

        point = widget._preview_cut_start_point(path)

        self.assertEqual(point.x, 7.0)
        self.assertEqual(point.y, 8.0)

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

    def test_template_cut_start_candidates_use_preview_display_transform(self):
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
        path = main_dock.parse_gcode_preview("G90\nG0 X10 Y5 Z5\nG1 Z-1\nG1 X12 Y5")

        candidates = widget._template_cut_start_candidates(path, "top")
        first = next(candidate for candidate in candidates if candidate.point.x == 10.0 and candidate.point.y == 5.0)

        self.assertEqual((first.point.x, first.point.y), (10.0, 5.0))
        self.assertEqual(first.projected, (10.0, -5.0))

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
        widget._gcode_preview_rotation_z = _DummyCombo("90")
        widget._preview_scene = mock.Mock()
        widget._preview_view = mock.Mock()
        dialog = mock.Mock()
        dialog.isVisible.return_value = True
        widget._preview_dialog = dialog

        with mock.patch.object(widget, "_render_gcode_preview") as render:
            widget._update_preview()

        render.assert_called_once_with(widget._preview_scene, widget._preview_view, "top", rotation_z=90)
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

    def test_controller_tick_fast_z_only_uses_step_interval_without_shoulders(self):
        main_dock = _load_main_dock_module()
        state = types.SimpleNamespace(
            name="Pad",
            x=0.0,
            y=0.0,
            z=1.0,
            speed_label="fast",
            speed_multiplier=3.0,
        )
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._controller_enable = _DummyCheckBox(True)
        widget._controller = types.SimpleNamespace(
            is_connected=lambda: True,
            poll_mapped=mock.Mock(return_value=state),
            error="",
        )
        widget._controller_feed = _DummySpin(600.0)
        widget._controller_deadzone = _DummySpin(0.2)
        widget._controller_z_step = _DummySpin(0.1)
        widget._controller_xy_step = _DummySpin(0.5)
        widget._controller_last_jog_at = 100.0
        widget._controller_was_active = False
        widget._controller_manual_xyz_active = False
        widget._controller_status = _DummyWidget()
        widget._controller_binding_strings = mock.Mock(return_value={})
        widget._send_jog = mock.Mock(return_value=True)

        with mock.patch.object(main_dock.time, "time", return_value=100.13):
            widget._controller_tick()

        widget._send_jog.assert_called_once_with(
            x=0.0,
            y=0.0,
            z=0.30000000000000004,
            feed=1800.0,
            source="Controller",
            log=False,
        )

    def test_controller_tick_fast_xy_still_uses_fast_interval(self):
        main_dock = _load_main_dock_module()
        state = types.SimpleNamespace(
            name="Pad",
            x=1.0,
            y=0.0,
            z=0.0,
            speed_label="fast",
            speed_multiplier=3.0,
        )
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._controller_enable = _DummyCheckBox(True)
        widget._controller = types.SimpleNamespace(
            is_connected=lambda: True,
            poll_mapped=mock.Mock(return_value=state),
            error="",
        )
        widget._controller_feed = _DummySpin(600.0)
        widget._controller_deadzone = _DummySpin(0.2)
        widget._controller_z_step = _DummySpin(0.1)
        widget._controller_xy_step = _DummySpin(0.5)
        widget._controller_last_jog_at = 100.0
        widget._controller_was_active = False
        widget._controller_manual_xyz_active = False
        widget._controller_status = _DummyWidget()
        widget._controller_binding_strings = mock.Mock(return_value={})
        widget._send_jog = mock.Mock(return_value=True)

        with mock.patch.object(main_dock.time, "time", return_value=100.13):
            widget._controller_tick()

        widget._send_jog.assert_not_called()

    def test_controller_tick_keeps_fast_xy_while_manual_xyz_active(self):
        main_dock = _load_main_dock_module()
        state = types.SimpleNamespace(
            name="Pad",
            x=1.0,
            y=0.0,
            z=0.0,
            speed_label="fast",
            speed_multiplier=3.0,
        )
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._controller_enable = _DummyCheckBox(True)
        widget._controller = types.SimpleNamespace(
            is_connected=lambda: True,
            poll_mapped=mock.Mock(return_value=state),
            error="",
        )
        widget._controller_feed = _DummySpin(600.0)
        widget._controller_deadzone = _DummySpin(0.2)
        widget._controller_z_step = _DummySpin(0.1)
        widget._controller_xy_step = _DummySpin(0.5)
        widget._controller_last_jog_at = 100.0
        widget._controller_was_active = False
        widget._controller_manual_xyz_active = True
        widget._controller_status = _DummyWidget()
        widget._controller_binding_strings = mock.Mock(return_value={})
        widget._controller_fast_xy_allowed = mock.Mock(return_value=True)
        widget._send_jog = mock.Mock(return_value=True)

        with mock.patch.object(main_dock.time, "time", return_value=100.23):
            widget._controller_tick()

        widget._send_jog.assert_called_once_with(
            x=8.4,
            y=0.0,
            z=0.0,
            feed=1800.0,
            source="Controller",
            log=False,
        )
        self.assertIn("[fast]", widget._controller_status.text)

    def test_controller_tick_smooths_manual_xyz_slow_xy(self):
        main_dock = _load_main_dock_module()
        state = types.SimpleNamespace(
            name="Pad",
            x=1.0,
            y=0.0,
            z=0.0,
            speed_label="slow",
            speed_multiplier=1.0,
        )
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._controller_enable = _DummyCheckBox(True)
        widget._controller = types.SimpleNamespace(
            is_connected=lambda: True,
            poll_mapped=mock.Mock(return_value=state),
            error="",
        )
        widget._controller_feed = _DummySpin(600.0)
        widget._controller_deadzone = _DummySpin(0.2)
        widget._controller_z_step = _DummySpin(0.1)
        widget._controller_xy_step = _DummySpin(0.5)
        widget._controller_last_jog_at = 100.0
        widget._controller_was_active = False
        widget._controller_manual_xyz_active = True
        widget._controller_status = _DummyWidget()
        widget._controller_binding_strings = mock.Mock(return_value={})
        widget._controller_fast_xy_allowed = mock.Mock(return_value=True)
        widget._send_jog = mock.Mock(return_value=True)

        with mock.patch.object(main_dock.time, "time", return_value=100.23):
            widget._controller_tick()

        widget._send_jog.assert_called_once()
        kwargs = widget._send_jog.call_args.kwargs
        self.assertAlmostEqual(kwargs["x"], 2.8)
        self.assertEqual(
            {key: kwargs[key] for key in ("y", "z", "feed", "source", "log")},
            {"y": 0.0, "z": 0.0, "feed": 600.0, "source": "Controller", "log": False},
        )
        self.assertIn("[slow]", widget._controller_status.text)

    def test_controller_tick_slows_fast_xy_near_work_edge(self):
        main_dock = _load_main_dock_module()
        state = types.SimpleNamespace(
            name="Pad",
            x=1.0,
            y=0.0,
            z=0.0,
            speed_label="fast",
            speed_multiplier=3.0,
        )
        sender = _FakeConnectedSender(status={"state": "Jog", "MPos": "-40.000,-200.000,-3.000"})
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._sender = sender
        widget._controller_enable = _DummyCheckBox(True)
        widget._controller = types.SimpleNamespace(
            is_connected=lambda: True,
            poll_mapped=mock.Mock(return_value=state),
            error="",
        )
        widget._controller_feed = _DummySpin(600.0)
        widget._controller_deadzone = _DummySpin(0.2)
        widget._controller_z_step = _DummySpin(0.1)
        widget._controller_xy_step = _DummySpin(0.5)
        widget._controller_last_jog_at = 100.0
        widget._controller_was_active = False
        widget._controller_manual_xyz_active = True
        widget._manual_xyz_prepare_mpos = {"x": -400.0, "y": -200.0, "z": -3.0}
        widget._manual_xyz_prepare_wpos = {"x": 0.0, "y": 0.0, "z": 0.0}
        widget._manual_xyz_work_origin_fallback = True
        widget._controller_status = _DummyWidget()
        widget._controller_binding_strings = mock.Mock(return_value={})
        widget._send_jog = mock.Mock(return_value=True)
        widget._limits = {"X": 400.0, "Y": 400.0, "Z": 60.0}
        widget._explore_active = False
        profile = {
            "machine_limits": {"x": [-400.0, 0.0], "y": [-400.0, 0.0], "z": [-60.0, 0.0]},
            "settings": {"$23": "3"},
        }

        with mock.patch.object(main_dock, "grbl_load_machine_profile", return_value=(profile, "/tmp/profile.json")):
            with mock.patch.object(main_dock.time, "time", return_value=100.13):
                widget._controller_tick()

        widget._send_jog.assert_called_once_with(
            x=0.5,
            y=0.0,
            z=0.0,
            feed=600.0,
            source="Controller",
            log=False,
        )
        self.assertIn("[edge]", widget._controller_status.text)


if __name__ == "__main__":
    unittest.main()
