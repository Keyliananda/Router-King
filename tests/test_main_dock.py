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


class _DummyTimer:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


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
    def test_apply_disconnected_state_resets_explore_state(self):
        main_dock = _load_main_dock_module()
        widget = main_dock.RouterKingDockWidget.__new__(main_dock.RouterKingDockWidget)
        widget._poll_timer = _DummyTimer()
        widget._status_tick = 3
        widget._sender_was_connected = True
        widget._connection_status = _DummyWidget()
        widget._machine_status = _DummyWidget()
        widget._alarm_status = _DummyWidget()
        widget._connect_btn = _DummyWidget()
        widget._port = _DummyWidget()
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


if __name__ == "__main__":
    unittest.main()
