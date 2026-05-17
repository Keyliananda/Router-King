"""RouterKing dock widget UI."""

try:
    from PySide2 import QtCore, QtWidgets, QtGui
except ImportError:  # pragma: no cover - fallback for older FreeCAD builds
    from PySide import QtCore, QtWidgets, QtGui

import json
import math
import os
import re
import time
from dataclasses import replace

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
    from ..cam.templates import TemplateSpec, rectangle_pocket, rectangle_pocket_preset
    from ..gcode.parser import iter_gcode_lines, prepare_stream_lines
    from ..gcode.transform import prepare_air_run_lines
    from ..grbl.sender import GrblSender
    from ..grbl.validator import (
        load_machine_profile as grbl_load_machine_profile,
        parse_xyz_value as grbl_parse_xyz_value,
        resolve_machine_limits as grbl_resolve_machine_limits,
        validate_gcode as grbl_validate_gcode,
    )
    from .gamepad import (
        DEFAULT_CONTROLLER_BINDINGS,
        PygameGamepad,
        active_binding_tokens,
        make_fast_xy_jog_vector,
        make_jog_vector,
    )
    from .gcode_preview import (
        PreviewPoint,
        PreviewSnapCandidate,
        nearest_preview_snap,
        parse_gcode_preview,
        project_point,
        preview_snap_candidates,
        render_preview_scene,
    )
except ImportError:
    from cam.templates import TemplateSpec, rectangle_pocket, rectangle_pocket_preset
    from gcode.parser import iter_gcode_lines, prepare_stream_lines
    from gcode.transform import prepare_air_run_lines
    from grbl.sender import GrblSender
    from grbl.validator import (
        load_machine_profile as grbl_load_machine_profile,
        parse_xyz_value as grbl_parse_xyz_value,
        resolve_machine_limits as grbl_resolve_machine_limits,
        validate_gcode as grbl_validate_gcode,
    )
    from ui.gamepad import (
        DEFAULT_CONTROLLER_BINDINGS,
        PygameGamepad,
        active_binding_tokens,
        make_fast_xy_jog_vector,
        make_jog_vector,
    )
    from ui.gcode_preview import (
        PreviewPoint,
        PreviewSnapCandidate,
        nearest_preview_snap,
        parse_gcode_preview,
        project_point,
        preview_snap_candidates,
        render_preview_scene,
    )

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


def _controller_log(text):
    try:
        base_dir = App.getUserAppDataDir()
    except Exception:
        base_dir = os.path.expanduser("~/Library/Application Support/FreeCAD")
    try:
        os.makedirs(base_dir, exist_ok=True)
        with open(os.path.join(base_dir, "routerking_controller.log"), "a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text}\n")
    except Exception:
        pass


_PREFS = App.ParamGet("User parameter:BaseApp/Preferences/RouterKing")
_CONTROLLER_LIMIT_MARGIN_MM = 2.0
_CONTROLLER_FAST_LOOKAHEAD_S = 0.28
_CONTROLLER_FAST_INTERVAL_S = 0.22
_CONTROLLER_STEP_INTERVAL_S = 0.12
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
_DEFAULT_AI_MODELS = ["gpt-5.2", "gpt-5-mini", "gpt-4o", "gpt-4o-mini"]
_AI_MODEL_SHORTLIST = [
    "gpt-5.2",
    "gpt-5.2-pro",
    "gpt-5.1",
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-5-pro",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "gpt-4o",
    "gpt-4o-mini",
    "o4-mini",
    "o3",
    "o3-mini",
    "o3-pro",
    "o1",
    "o1-mini",
    "gpt-4",
    "gpt-3.5-turbo",
]
_AI_MODEL_PREFIX_ORDER = [
    "gpt-6", "gpt-5", "gpt-4.1", "gpt-4o", 
    "o5", "o4", "o3", "o2", "o1", 
    "gpt-4", "gpt-3.5"
]

_CONTROLLER_BINDING_FIELDS = (
    ("x_axes", "X axis"),
    ("y_axes", "Y axis"),
    ("z_axes", "Z axis"),
    ("x_neg_buttons", "X- buttons"),
    ("x_pos_buttons", "X+ buttons"),
    ("y_neg_buttons", "Y- buttons"),
    ("y_pos_buttons", "Y+ buttons"),
    ("z_neg_buttons", "Z- buttons"),
    ("z_pos_buttons", "Z+ buttons"),
    ("slow_buttons", "Slow speed"),
    ("medium_buttons", "Medium speed"),
)


def _set_layout_visible(layout, visible):
    for index in range(layout.count()):
        item = layout.itemAt(index)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.setVisible(visible)
        elif child_layout is not None:
            _set_layout_visible(child_layout, visible)


def _make_collapsible(group, *, collapsed=False):
    group.setCheckable(True)

    def apply(expanded):
        layout = group.layout()
        if layout is not None:
            _set_layout_visible(layout, bool(expanded))

    group.toggled.connect(apply)
    group.setChecked(not collapsed)
    apply(not collapsed)
    return group


def _property_float(value):
    if value is None:
        return None
    if hasattr(value, "Value"):
        value = value.Value
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class ControllerTestDialog(QtWidgets.QDialog):
    """Live pygame controller inspector. It never sends GRBL commands."""

    def __init__(self, gamepad, parent=None):
        super().__init__(parent)
        self._gamepad = gamepad
        self._owns_connection = False
        self._closing = False
        self._axis_widgets = {}
        self._button_widgets = {}
        self.setWindowTitle("RouterKing Controller Test")
        self.setMinimumWidth(640)
        try:
            self.setWindowFlags(
                self.windowFlags()
                | QtCore.Qt.Window
                | QtCore.Qt.WindowMinimizeButtonHint
                | QtCore.Qt.WindowCloseButtonHint
            )
        except Exception:
            pass

        layout = QtWidgets.QVBoxLayout(self)
        self._status = QtWidgets.QLabel("Controller: checking...")
        layout.addWidget(self._status)

        mapping = QtWidgets.QLabel("Jog mapping: right stick X/Y, L2 Z-, R2 Z+. L1 slow, R1 medium, no shoulder fast.")
        layout.addWidget(mapping)

        axes_group = QtWidgets.QGroupBox("Axes")
        self._axes_layout = QtWidgets.QGridLayout(axes_group)
        _make_collapsible(axes_group)
        layout.addWidget(axes_group)

        buttons_group = QtWidgets.QGroupBox("Buttons")
        self._buttons_layout = QtWidgets.QGridLayout(buttons_group)
        _make_collapsible(buttons_group)
        layout.addWidget(buttons_group)

        close_row = QtWidgets.QHBoxLayout()
        close_row.addStretch(1)
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._refresh)
        self._connect_if_needed()

    def closeEvent(self, event):
        self._stop()
        super().closeEvent(event)

    def accept(self):
        self._stop()
        super().accept()

    def reject(self):
        self._stop()
        super().reject()

    def _connect_if_needed(self):
        if not self._gamepad.is_available():
            self._status.setText(f"Controller: pygame unavailable ({self._gamepad.error})")
            return
        if not self._gamepad.is_connected():
            self._owns_connection = bool(self._gamepad.connect())
        if not self._gamepad.is_connected():
            self._status.setText(f"Controller: {self._gamepad.error or 'not found'}")
            return
        self._timer.start()
        self._refresh()

    def _stop(self):
        self._closing = True
        if getattr(self, "_timer", None) is not None:
            self._timer.stop()
        if self._owns_connection:
            self._gamepad.disconnect()
            self._owns_connection = False

    def _refresh(self):
        if self._closing:
            return
        try:
            snapshot = self._gamepad.snapshot()
            if snapshot is None:
                self._status.setText(f"Controller: {self._gamepad.error or 'disconnected'}")
                return
            self._status.setText(f"Controller: {snapshot.name}")
            self._refresh_axes(snapshot.axes)
            self._refresh_buttons(snapshot.buttons)
        except Exception as exc:
            self._status.setText(f"Controller test stopped: {exc}")
            self._timer.stop()

    def _refresh_axes(self, axes):
        for row, axis in enumerate(axes):
            if axis.name not in self._axis_widgets:
                name_label = QtWidgets.QLabel(axis.name)
                value_label = QtWidgets.QLabel("+0.000")
                bar = QtWidgets.QProgressBar()
                bar.setRange(0, 2000)
                bar.setTextVisible(False)
                self._axes_layout.addWidget(name_label, row, 0)
                self._axes_layout.addWidget(bar, row, 1)
                self._axes_layout.addWidget(value_label, row, 2)
                self._axis_widgets[axis.name] = (bar, value_label)
            bar, value_label = self._axis_widgets[axis.name]
            value = max(-1.0, min(1.0, float(axis.value)))
            bar.setValue(int((value + 1.0) * 1000))
            value_label.setText(f"{value:+.3f}")

    def _refresh_buttons(self, buttons):
        for index, button in enumerate(buttons):
            if button.name not in self._button_widgets:
                label = QtWidgets.QLabel(button.name)
                label.setAlignment(QtCore.Qt.AlignCenter)
                label.setMinimumWidth(92)
                label.setAutoFillBackground(True)
                self._buttons_layout.addWidget(label, index // 4, index % 4)
                self._button_widgets[button.name] = label
            label = self._button_widgets[button.name]
            if button.pressed:
                label.setStyleSheet("QLabel { background: #2d9c4b; color: white; padding: 6px; border-radius: 4px; }")
            else:
                label.setStyleSheet("QLabel { background: #3b3b3b; color: #dddddd; padding: 6px; border-radius: 4px; }")


class ControllerBindingCaptureDialog(QtWidgets.QDialog):
    """Capture one controller input token without sending machine commands."""

    def __init__(self, gamepad, binding_label, callback, parent=None):
        super().__init__(parent)
        self._gamepad = gamepad
        self._binding_label = binding_label
        self._callback = callback
        self._owns_connection = False
        self._closing = False
        self.setWindowTitle(f"Learn Controller Binding: {binding_label}")
        self.setMinimumWidth(420)
        try:
            self.setWindowFlags(
                self.windowFlags()
                | QtCore.Qt.Window
                | QtCore.Qt.WindowMinimizeButtonHint
                | QtCore.Qt.WindowCloseButtonHint
            )
        except Exception:
            pass

        layout = QtWidgets.QVBoxLayout(self)
        self._status = QtWidgets.QLabel(f"Press or move a controller input for: {binding_label}")
        layout.addWidget(self._status)
        self._hint = QtWidgets.QLabel("Buttons are captured directly. Axes are captured past 60% deflection.")
        layout.addWidget(self._hint)
        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch(1)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        button_row.addWidget(cancel)
        layout.addLayout(button_row)

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._refresh)
        self._connect_if_needed()

    def closeEvent(self, event):
        self._stop()
        super().closeEvent(event)

    def accept(self):
        self._stop()
        super().accept()

    def reject(self):
        self._stop()
        super().reject()

    def _connect_if_needed(self):
        if not self._gamepad.is_available():
            self._status.setText(f"Controller unavailable: {self._gamepad.error}")
            return
        if not self._gamepad.is_connected():
            self._owns_connection = bool(self._gamepad.connect())
        if not self._gamepad.is_connected():
            self._status.setText(f"Controller not found: {self._gamepad.error}")
            return
        self._timer.start()

    def _stop(self):
        self._closing = True
        if getattr(self, "_timer", None) is not None:
            self._timer.stop()
        if self._owns_connection:
            self._gamepad.disconnect()
            self._owns_connection = False

    def _refresh(self):
        if self._closing:
            return
        try:
            snapshot = self._gamepad.snapshot()
            if snapshot is None:
                self._status.setText(f"Controller disconnected: {self._gamepad.error}")
                return
            tokens = active_binding_tokens(snapshot)
            if not tokens:
                self._status.setText(f"Waiting for input: {self._binding_label}")
                return
            token = tokens[0]
            self._status.setText(f"Captured: {token}")
            self._callback(token)
            self.accept()
        except Exception as exc:
            self._status.setText(f"Capture stopped: {exc}")
            self._timer.stop()
_AI_MODEL_EXCLUDE_SUBSTRINGS = (
    "realtime",
    "audio",
    "vision",
    "transcribe",
    "whisper",
    "tts",
    "embedding",
    "moderation",
    "dall-e",
    "image",
)
_AI_SETTINGS_HELP_TEXT = "Stored in FreeCAD preferences (plain text). ENV overrides saved values."

_CAM_PRESETS = [
    ("Custom", {}),
    (
        "Bamboo Pocket 4mm (3.175mm endmill)",
        {
            "prefer_cam": True,
            "units": "mm",
            "feed_rate": 500.0,
            "plunge_rate": 150.0,
            "spindle_speed": 10000,
            "safe_z": 5.0,
            "start_z": 0.0,
            "cut_z": -4.0,
            "pass_depth": 0.5,
            "ramp_length": 8.0,
            "lead_in": 0.5,
            "lead_out": 0.5,
            "start_depth": 0.0,
            "final_depth": -4.0,
            "step_down": 0.5,
            "step_over": 35.0,
            "profile_side": "Outside",
            "profile_direction": "CCW",
            "start_spindle": True,
        },
    ),
    (
        "CNC Plywood 10mm (6mm endmill)",
        {
            "prefer_cam": True,
            "units": "mm",
            "feed_rate": 1000.0,
            "plunge_rate": 300.0,
            "spindle_speed": 18000,
            "safe_z": 5.0,
            "start_z": 0.0,
            "cut_z": -3.0,
            "pass_depth": 2.0,
            "ramp_length": 4.0,
            "lead_in": 1.0,
            "lead_out": 1.0,
            "start_depth": 0.0,
            "final_depth": -10.0,
            "step_down": 2.0,
            "profile_side": "Outside",
            "profile_direction": "CCW",
            "start_spindle": True,
        },
    ),
    (
        "CNC Aluminum 3mm (3mm endmill)",
        {
            "prefer_cam": True,
            "units": "mm",
            "feed_rate": 400.0,
            "plunge_rate": 150.0,
            "spindle_speed": 12000,
            "safe_z": 5.0,
            "start_z": 0.0,
            "cut_z": -1.0,
            "pass_depth": 0.5,
            "ramp_length": 2.0,
            "lead_in": 0.5,
            "lead_out": 0.5,
            "start_depth": 0.0,
            "final_depth": -3.0,
            "step_down": 0.5,
            "profile_side": "Outside",
            "profile_direction": "CCW",
            "start_spindle": True,
        },
    ),
    (
        "Laser Plywood 3mm",
        {
            "prefer_cam": False,
            "units": "mm",
            "feed_rate": 1200.0,
            "plunge_rate": 0.0,
            "laser_power": 1000,
            "safe_z": 5.0,
            "start_z": 0.0,
            "cut_z": 0.0,
            "pass_depth": 0.0,
            "ramp_length": 0.0,
            "lead_in": 0.0,
            "lead_out": 0.0,
            "start_depth": 0.0,
            "final_depth": 0.0,
            "step_down": 0.1,
            "profile_side": "On",
            "profile_direction": "CCW",
            "start_spindle": True,
        },
    ),
    (
        "Laser Acrylic 3mm",
        {
            "prefer_cam": False,
            "units": "mm",
            "feed_rate": 800.0,
            "plunge_rate": 0.0,
            "laser_power": 900,
            "safe_z": 5.0,
            "start_z": 0.0,
            "cut_z": 0.0,
            "pass_depth": 0.0,
            "ramp_length": 0.0,
            "lead_in": 0.0,
            "lead_out": 0.0,
            "start_depth": 0.0,
            "final_depth": 0.0,
            "step_down": 0.1,
            "profile_side": "On",
            "profile_direction": "CCW",
            "start_spindle": True,
        },
    ),
]


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
        allow_actions,
        context_payload=None,
        context_summary="",
    ):
        super().__init__()
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._messages = messages
        self._reasoning_effort = reasoning_effort
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        self._allow_actions = allow_actions
        self._context_payload = context_payload
        self._context_summary = context_summary

    def run(self):
        try:
            from ..ai.assistant import ask_assistant
        except ImportError:
            from ai.assistant import ask_assistant

        try:
            response = ask_assistant(
                self._messages,
                api_key=self._api_key,
                base_url=self._base_url,
                model=self._model,
                reasoning_effort=self._reasoning_effort,
                temperature=self._temperature,
                max_output_tokens=self._max_output_tokens,
                context=self._context_payload,
                context_summary=self._context_summary,
                allow_llm=True,
                allow_actions=self._allow_actions,
            )
        except Exception as exc:
            self.finished.emit("", exc)
            return

        self.finished.emit(response.text, None)


class _AiModelListWorker(QtCore.QObject):
    finished = QtCore.Signal(object, object)

    def __init__(self, api_key, base_url):
        super().__init__()
        self._api_key = api_key
        self._base_url = base_url

    def run(self):
        try:
            from ..ai.client import list_models
        except ImportError:
            from ai.client import list_models

        try:
            models = list_models(self._api_key, self._base_url)
        except Exception as exc:
            self.finished.emit(None, exc)
            return

        self.finished.emit(models, None)


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


class GcodePreviewView(QtWidgets.QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self._snap_enabled = False
        self._snap_candidates = ()
        self._snap_callback = None
        self._snap_marker = None
        self._projection_name = "iso"
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)

    def set_snap_mode(self, enabled, candidates=(), callback=None):
        self._snap_enabled = bool(enabled)
        self._snap_candidates = tuple(candidates or ())
        self._snap_callback = callback
        self.setDragMode(
            QtWidgets.QGraphicsView.NoDrag
            if self._snap_enabled
            else QtWidgets.QGraphicsView.ScrollHandDrag
        )
        self._clear_snap_marker()

    def set_snap_candidates(self, candidates):
        self._snap_candidates = tuple(candidates or ())

    def set_projection_name(self, projection):
        self._projection_name = str(projection or "iso").lower()

    def wheelEvent(self, event):
        try:
            delta = event.angleDelta().y()
        except Exception:
            delta = 0
        factor = 1.15 if delta > 0 else 1.0 / 1.15
        self.scale(factor, factor)

    def mouseMoveEvent(self, event):
        if self._snap_enabled:
            self._update_snap_marker(event.pos())
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if self._snap_enabled and event.button() == QtCore.Qt.LeftButton:
            match = self._snap_match_at(event.pos())
            if match is not None and self._snap_callback is not None:
                self._snap_callback(match.candidate.point)
                event.accept()
                return
        super().mousePressEvent(event)

    def _snap_match_at(self, view_pos):
        scene_pos = self.mapToScene(view_pos)
        scene_units = self._scene_units_per_pixel()
        return nearest_preview_snap(
            self._snap_candidates,
            (scene_pos.x(), scene_pos.y()),
            pixel_tolerance=5.0,
            scene_units_per_pixel=scene_units,
        )

    def _update_snap_marker(self, view_pos):
        match = self._snap_match_at(view_pos)
        if match is None:
            self._clear_snap_marker()
            return
        x_val, y_val = match.candidate.projected
        self._draw_snap_marker(x_val, y_val, QtGui.QColor(255, 210, 0, 80), pixel_radius=5.0)

    def _draw_snap_marker(self, x_val, y_val, color, pixel_radius=5.0):
        radius = max(self._scene_units_per_pixel() * float(pixel_radius), 0.25)
        if self._snap_marker is not None:
            try:
                self.scene().removeItem(self._snap_marker)
            except Exception:
                pass
        pen = QtGui.QPen(QtGui.QColor(255, 210, 0), 0)
        brush = QtGui.QBrush(color)
        self._snap_marker = self.scene().addEllipse(
            x_val - radius,
            y_val - radius,
            radius * 2.0,
            radius * 2.0,
            pen,
            brush,
        )

    def _clear_snap_marker(self):
        if self._snap_marker is None:
            return
        try:
            self.scene().removeItem(self._snap_marker)
        except Exception:
            pass
        self._snap_marker = None

    def _scene_units_per_pixel(self):
        try:
            left = self.mapToScene(QtCore.QPoint(0, 0))
            right = self.mapToScene(QtCore.QPoint(1, 0))
            return max(abs(right.x() - left.x()), 1e-9)
        except Exception:
            return 1.0


class GcodePreviewDialog(QtWidgets.QDialog):
    def __init__(self, dock, parent=None):
        super().__init__(parent)
        self._dock = dock
        self.setWindowTitle("RouterKing G-code Preview")
        self.resize(900, 700)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        toolbar = QtWidgets.QHBoxLayout()
        toolbar.addWidget(QtWidgets.QLabel("Projection"))
        self._projection = QtWidgets.QComboBox()
        self._projection.addItems(["Iso", "Top", "Side", "Front"])
        current_projection = dock._preview_projection_name().capitalize()
        index = self._projection.findText(current_projection)
        if index >= 0:
            self._projection.setCurrentIndex(index)
        self._refresh_btn = QtWidgets.QPushButton("Refresh")
        toolbar.addWidget(self._projection)
        toolbar.addWidget(self._refresh_btn)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self._scene = QtWidgets.QGraphicsScene(self)
        self._view = GcodePreviewView(self._scene)
        layout.addWidget(self._view, 1)

        self._projection.currentTextChanged.connect(self.refresh)
        self._refresh_btn.clicked.connect(self.refresh)
        self.refresh()

    def refresh(self):
        projection = str(self._projection.currentText() or "Iso").lower()
        self._dock._render_gcode_preview(self._scene, self._view, projection)


class RouterKingDockWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Create sender and register as global singleton so MCP can access it
        self._sender = GrblSender()
        try:
            from ..grbl.manager import set_sender
        except ImportError:
            from grbl.manager import set_sender
        set_sender(self._sender)
        self._sender_was_connected = False
        self._last_gcode_path = None
        self._last_dxf_path = None
        self._gcode_manual_start_wpos = None
        self._gcode_manual_start_mpos = None
        self._gcode_manual_start_wco = None
        self._gcode_manual_start_at = 0.0
        self._gcode_last_validation = None
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
        self._ai_models_loading = False
        self._ai_model_worker = None
        self._ai_model_worker_thread = None
        self._ai_preview_objects = []
        self._ai_last_optimization = None
        self._cam_status = None
        self._cam_check_btn = None
        self._cam_activate_btn = None
        self._cam_generate_btn = None
        self._import_dxf_btn = None
        self._gcode_preview_projection = None
        self._preview_refresh_timer = None
        self._preview_dialog = None
        self._last_template_spec = None
        self._template_controls = {}
        self._template_group = None
        self._template_source_combo = None
        self._template_source_summary = None
        self._template_cad_tool_summary = None
        self._template_snap_active = False
        self._template_fit_pick_active = False
        self._template_fit_candidates = []
        self._template_fit_index = None
        self._template_fit_point = None
        self._cam_generate_defaults = {}
        self._cam_user_presets = []
        self._dxf_import_defaults = {}
        self._controller = PygameGamepad()
        self._controller_defaults = {}
        self._controller_last_jog_at = 0.0
        self._controller_was_active = False
        self._controller_guard_mpos = None
        self._controller_guard_mpos_at = 0.0
        self._controller_manual_xyz_active = False
        self._controller_test_dialog = None
        self._controller_binding_capture_dialog = None

        self._load_cam_generate_defaults()
        self._load_dxf_import_defaults()
        self._load_controller_defaults()

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
        self._controller_timer = QtCore.QTimer(self)
        self._controller_timer.setInterval(120)
        self._controller_timer.timeout.connect(self._controller_tick)

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

        mcp_group = QtWidgets.QGroupBox("Agent / MCP")
        mcp_layout = QtWidgets.QVBoxLayout(mcp_group)
        self._mcp_status = QtWidgets.QLabel("MCP: idle")
        mcp_layout.addWidget(self._mcp_status)
        self._mcp_log = QtWidgets.QPlainTextEdit()
        self._mcp_log.setReadOnly(True)
        self._mcp_log.setMaximumHeight(72)
        self._mcp_log.setPlaceholderText("Shared MCP actions appear here.")
        mcp_layout.addWidget(self._mcp_log)
        _make_collapsible(mcp_group)
        layout.addWidget(mcp_group)

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
        _make_collapsible(jog_group)
        layout.addWidget(jog_group)

        controller_group = QtWidgets.QGroupBox("Controller Jog")
        controller_layout = QtWidgets.QVBoxLayout(controller_group)
        controller_top = QtWidgets.QHBoxLayout()
        self._controller_connect_btn = QtWidgets.QPushButton("Connect Controller")
        self._controller_test_btn = QtWidgets.QPushButton("Test Controller")
        self._controller_enable = QtWidgets.QCheckBox("Enable")
        self._controller_status = QtWidgets.QLabel("Controller: unavailable")
        controller_top.addWidget(self._controller_connect_btn)
        controller_top.addWidget(self._controller_test_btn)
        controller_top.addWidget(self._controller_enable)
        controller_top.addWidget(self._controller_status, 1)
        controller_layout.addLayout(controller_top)

        controller_settings = QtWidgets.QHBoxLayout()
        controller_settings.addWidget(QtWidgets.QLabel("XY step"))
        self._controller_xy_step = QtWidgets.QDoubleSpinBox()
        self._controller_xy_step.setDecimals(3)
        self._controller_xy_step.setRange(0.001, 10.0)
        self._controller_xy_step.setValue(float(self._controller_defaults.get("xy_step", 0.5)))
        controller_settings.addWidget(self._controller_xy_step)
        controller_settings.addWidget(QtWidgets.QLabel("Z step"))
        self._controller_z_step = QtWidgets.QDoubleSpinBox()
        self._controller_z_step.setDecimals(3)
        self._controller_z_step.setRange(0.001, 5.0)
        self._controller_z_step.setValue(float(self._controller_defaults.get("z_step", 0.1)))
        controller_settings.addWidget(self._controller_z_step)
        controller_settings.addWidget(QtWidgets.QLabel("Feed"))
        self._controller_feed = QtWidgets.QDoubleSpinBox()
        self._controller_feed.setDecimals(0)
        self._controller_feed.setRange(1, 5000)
        self._controller_feed.setValue(float(self._controller_defaults.get("feed_rate", 600.0)))
        controller_settings.addWidget(self._controller_feed)
        controller_settings.addWidget(QtWidgets.QLabel("Deadzone"))
        self._controller_deadzone = QtWidgets.QDoubleSpinBox()
        self._controller_deadzone.setDecimals(2)
        self._controller_deadzone.setRange(0.0, 0.95)
        self._controller_deadzone.setSingleStep(0.05)
        self._controller_deadzone.setValue(float(self._controller_defaults.get("deadzone", 0.20)))
        controller_settings.addWidget(self._controller_deadzone)
        controller_layout.addLayout(controller_settings)

        bindings_group = QtWidgets.QGroupBox("Controller Bindings")
        bindings_layout = QtWidgets.QGridLayout(bindings_group)
        self._controller_binding_edits = {}
        for row, (key, label) in enumerate(_CONTROLLER_BINDING_FIELDS):
            bindings_layout.addWidget(QtWidgets.QLabel(label), row, 0)
            edit = QtWidgets.QLineEdit()
            edit.setText(str(self._controller_defaults.get(key, DEFAULT_CONTROLLER_BINDINGS.get(key, ""))))
            edit.setPlaceholderText(DEFAULT_CONTROLLER_BINDINGS.get(key, ""))
            bindings_layout.addWidget(edit, row, 1)
            learn_btn = QtWidgets.QPushButton("Learn")
            clear_btn = QtWidgets.QPushButton("Clear")
            bindings_layout.addWidget(learn_btn, row, 2)
            bindings_layout.addWidget(clear_btn, row, 3)
            learn_btn.clicked.connect(lambda _checked=False, k=key, l=label: self._on_learn_controller_binding(k, l))
            clear_btn.clicked.connect(lambda _checked=False, e=edit: e.clear())
            self._controller_binding_edits[key] = edit
        bindings_help = QtWidgets.QLabel("Comma-separated names. Prefix axes with '-' to invert, e.g. -Right Y.")
        bindings_layout.addWidget(bindings_help, len(_CONTROLLER_BINDING_FIELDS), 0, 1, 2)
        _make_collapsible(bindings_group, collapsed=True)
        controller_layout.addWidget(bindings_group)

        manual_row = QtWidgets.QHBoxLayout()
        manual_row.addWidget(QtWidgets.QLabel("Manual XYZ Z clearance"))
        self._controller_manual_clearance = QtWidgets.QDoubleSpinBox()
        self._controller_manual_clearance.setDecimals(3)
        self._controller_manual_clearance.setRange(0.0, 50.0)
        self._controller_manual_clearance.setSingleStep(0.1)
        self._controller_manual_clearance.setValue(float(self._controller_defaults.get("manual_clearance", 1.5)))
        manual_row.addWidget(self._controller_manual_clearance)
        self._controller_manual_prepare_btn = QtWidgets.QPushButton("Prepare Manual XYZ")
        self._controller_manual_exit_btn = QtWidgets.QPushButton("Exit Manual XYZ")
        manual_row.addWidget(self._controller_manual_prepare_btn)
        manual_row.addWidget(self._controller_manual_exit_btn)
        controller_layout.addLayout(manual_row)

        controller_note = QtWidgets.QLabel("Default: right stick + DPad X/Y, L2 Z-, R2 Z+. L1 slow, R1 medium, no shoulder fast.")
        controller_layout.addWidget(controller_note)
        self._controller_enable.setChecked(bool(self._controller_defaults.get("enabled", False)))
        _make_collapsible(controller_group)
        layout.addWidget(controller_group)

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
        _make_collapsible(machine_group, collapsed=True)
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
        _make_collapsible(console_group, collapsed=True)
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
        self._controller_connect_btn.clicked.connect(self._on_controller_connect)
        self._controller_test_btn.clicked.connect(self._on_controller_test)
        self._controller_enable.toggled.connect(self._on_controller_enabled_changed)
        self._controller_xy_step.valueChanged.connect(lambda _value: self._save_controller_defaults())
        self._controller_z_step.valueChanged.connect(lambda _value: self._save_controller_defaults())
        self._controller_feed.valueChanged.connect(lambda _value: self._save_controller_defaults())
        self._controller_deadzone.valueChanged.connect(lambda _value: self._save_controller_defaults())
        self._controller_manual_clearance.valueChanged.connect(lambda _value: self._save_controller_defaults())
        for edit in self._controller_binding_edits.values():
            edit.editingFinished.connect(self._save_controller_defaults)
        self._controller_manual_prepare_btn.clicked.connect(self._on_prepare_manual_xyz)
        self._controller_manual_exit_btn.clicked.connect(self._on_exit_manual_xyz)
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
        self._import_dxf_btn = QtWidgets.QPushButton("Import DXF")
        self._template_btn = QtWidgets.QPushButton("Template")
        self._preview_btn = QtWidgets.QPushButton("Preview")
        self._cam_generate_btn = QtWidgets.QPushButton("FreeCAD CAM")
        self._cam_generate_btn.setToolTip("Open the FreeCAD CAM generator. Rectangle templates use Apply Template below.")
        file_row.addWidget(self._load_btn)
        file_row.addWidget(self._save_btn)
        file_row.addWidget(self._import_dxf_btn)
        file_row.addWidget(self._template_btn)
        file_row.addWidget(self._preview_btn)
        file_row.addWidget(self._cam_generate_btn)
        file_row.addStretch(1)
        layout.addLayout(file_row)

        job_row = QtWidgets.QHBoxLayout()
        self._start_btn = QtWidgets.QPushButton("Start")
        self._validate_btn = QtWidgets.QPushButton("Validate")
        self._air_run_apply_btn = QtWidgets.QPushButton("Show/Apply Air Run")
        self._air_run_btn = QtWidgets.QPushButton("Air Run")
        self._pause_btn = QtWidgets.QPushButton("Pause")
        self._stop_btn = QtWidgets.QPushButton("Stop")
        job_row.addWidget(self._validate_btn)
        job_row.addWidget(self._air_run_apply_btn)
        job_row.addWidget(self._air_run_btn)
        job_row.addWidget(self._start_btn)
        job_row.addWidget(self._pause_btn)
        job_row.addWidget(self._stop_btn)
        self._dry_run_check = QtWidgets.QCheckBox("Dry Run")
        self._dry_run_check.setToolTip("Skip spindle/laser commands (M3/M4/M5) while streaming.")
        job_row.addWidget(self._dry_run_check)
        job_row.addStretch(1)
        layout.addLayout(job_row)

        manual_start_row = QtWidgets.QHBoxLayout()
        self._set_manual_start_btn = QtWidgets.QPushButton("Set Manual Start")
        self._use_manual_start_template_btn = QtWidgets.QPushButton("Use Manual Start In Template")
        self._go_manual_start_btn = QtWidgets.QPushButton("Go To Manual Start Safely")
        self._manual_start_status = QtWidgets.QLabel("Manual start: not set")
        manual_start_row.addWidget(self._set_manual_start_btn)
        manual_start_row.addWidget(self._use_manual_start_template_btn)
        manual_start_row.addWidget(self._go_manual_start_btn)
        manual_start_row.addWidget(self._manual_start_status, 1)
        layout.addLayout(manual_start_row)

        cam_row = QtWidgets.QHBoxLayout()
        self._cam_status = QtWidgets.QLabel("CAM Workbench: unknown")
        self._cam_check_btn = QtWidgets.QPushButton("Check CAM")
        self._cam_activate_btn = QtWidgets.QPushButton("Activate CAM")
        self._cam_activate_btn.setEnabled(False)
        cam_row.addWidget(self._cam_status, 1)
        cam_row.addWidget(self._cam_check_btn)
        cam_row.addWidget(self._cam_activate_btn)
        cam_row.addStretch(1)
        layout.addLayout(cam_row)

        preview_row = QtWidgets.QHBoxLayout()
        preview_row.addWidget(QtWidgets.QLabel("Preview"))
        self._gcode_preview_projection = QtWidgets.QComboBox()
        self._gcode_preview_projection.addItems(["Iso", "Top", "Side", "Front"])
        self._gcode_preview_projection.setToolTip("Choose the G-code preview projection.")
        self._open_preview_btn = QtWidgets.QPushButton("Open Preview")
        self._snap_start_btn = QtWidgets.QPushButton("Set Cut Start Snap")
        self._preview_tool_area_check = QtWidgets.QCheckBox("Show Tool Area")
        self._preview_tool_area_check.setChecked(True)
        self._pick_fit_corner_btn = QtWidgets.QPushButton("Pick Fit Corner")
        self._prev_fit_btn = QtWidgets.QPushButton("Prev Fit")
        self._next_fit_btn = QtWidgets.QPushButton("Next Fit")
        self._fit_status = QtWidgets.QLabel("Fit: pick corner")
        preview_row.addWidget(self._gcode_preview_projection)
        preview_row.addWidget(self._open_preview_btn)
        preview_row.addWidget(self._snap_start_btn)
        preview_row.addWidget(self._preview_tool_area_check)
        preview_row.addWidget(self._pick_fit_corner_btn)
        preview_row.addWidget(self._prev_fit_btn)
        preview_row.addWidget(self._next_fit_btn)
        preview_row.addWidget(self._fit_status)
        preview_row.addStretch(1)
        layout.addLayout(preview_row)

        self._template_group = self._build_template_parameters_group()
        layout.addWidget(self._template_group)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self._gcode_edit = QtWidgets.QPlainTextEdit()
        self._gcode_edit.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self._gcode_edit.setPlaceholderText("Load G-code to preview or send.")
        self._gcode_edit.setFont(self._fixed_font)
        self._preview_scene = QtWidgets.QGraphicsScene(self)
        self._preview_view = GcodePreviewView(self._preview_scene)
        self._preview_view.setMinimumWidth(220)
        splitter.addWidget(self._gcode_edit)
        splitter.addWidget(self._preview_view)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        self._load_btn.clicked.connect(self._on_load_gcode)
        self._save_btn.clicked.connect(self._on_save_gcode)
        self._import_dxf_btn.clicked.connect(self._on_import_dxf)
        self._template_btn.clicked.connect(self._on_insert_gcode_template)
        self._preview_btn.clicked.connect(self._update_preview)
        self._cam_generate_btn.clicked.connect(self._on_cam_generate)
        self._validate_btn.clicked.connect(self._on_validate_gcode)
        self._air_run_apply_btn.clicked.connect(self._on_show_apply_air_run)
        self._air_run_btn.clicked.connect(self._on_air_run)
        self._start_btn.clicked.connect(self._on_start_job)
        self._pause_btn.clicked.connect(self._on_pause_resume_job)
        self._stop_btn.clicked.connect(self._on_stop_job)
        self._set_manual_start_btn.clicked.connect(self._on_set_manual_start)
        self._use_manual_start_template_btn.clicked.connect(self._on_use_manual_start_in_template)
        self._go_manual_start_btn.clicked.connect(self._on_go_to_manual_start_safely)
        self._cam_check_btn.clicked.connect(self._on_cam_check)
        self._cam_activate_btn.clicked.connect(self._on_cam_activate)
        self._gcode_edit.textChanged.connect(self._update_job_controls)
        self._gcode_edit.textChanged.connect(self._schedule_preview_update)
        self._gcode_preview_projection.currentTextChanged.connect(self._update_preview)
        self._preview_tool_area_check.toggled.connect(self._update_preview)
        self._open_preview_btn.clicked.connect(self._on_open_gcode_preview)
        self._snap_start_btn.clicked.connect(self._on_set_template_start_from_snap)
        self._pick_fit_corner_btn.clicked.connect(self._on_pick_template_fit_corner)
        self._prev_fit_btn.clicked.connect(self._on_previous_template_fit)
        self._next_fit_btn.clicked.connect(self._on_next_template_fit)

        self._preview_refresh_timer = QtCore.QTimer(self)
        self._preview_refresh_timer.setSingleShot(True)
        self._preview_refresh_timer.setInterval(250)
        self._preview_refresh_timer.timeout.connect(self._update_preview)

        self._update_job_controls()
        self._update_machine_controls()
        self._refresh_cam_status()

    def _build_template_parameters_group(self):
        group = QtWidgets.QGroupBox("Rectangle Pocket Parameters")
        layout = QtWidgets.QVBoxLayout(group)
        layout.setSpacing(4)

        source_row = QtWidgets.QHBoxLayout()
        source_row.addWidget(QtWidgets.QLabel("CAD source"))
        self._template_source_combo = QtWidgets.QComboBox()
        self._template_source_combo.setMinimumWidth(240)
        self._template_source_summary = QtWidgets.QLabel("No CAD source selected")
        self._template_source_summary.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self._template_cad_tool_summary = QtWidgets.QLabel("CAD tool: unknown")
        self._template_cad_tool_summary.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        refresh_source_btn = QtWidgets.QPushButton("Refresh CAD Sources")
        source_row.addWidget(self._template_source_combo, 1)
        source_row.addWidget(refresh_source_btn)
        layout.addLayout(source_row)

        default = self._default_rectangle_template_spec()
        controls = {
            "name": QtWidgets.QLineEdit(default.name or ""),
            "width": self._template_spin(default.width, 0.001, 10000.0),
            "height": self._template_spin(default.height, 0.001, 10000.0),
            "depth": self._template_spin(default.depth, 0.001, 1000.0),
            "tool_diameter": self._template_spin(default.tool_diameter, 0.001, 1000.0),
            "step_down": self._template_spin(default.step_down, 0.001, 1000.0),
            "step_over": self._template_spin(default.step_over, 0.001, 1000.0),
            "feed_rate": self._template_spin(default.feed_rate, 0.001, 50000.0, decimals=1),
            "plunge_rate": self._template_spin(default.plunge_rate, 0.001, 50000.0, decimals=1),
            "safe_z": self._template_spin(default.safe_z, -1000.0, 1000.0),
            "start_z": self._template_spin(default.start_z, -1000.0, 1000.0),
            "start_x": self._template_spin(default.start_x, -10000.0, 10000.0),
            "start_y": self._template_spin(default.start_y, -10000.0, 10000.0),
            "origin": QtWidgets.QComboBox(),
            "swap_xy": QtWidgets.QCheckBox("Swap X/Y machining direction"),
            "pass_axis": QtWidgets.QComboBox(),
            "path_direction": QtWidgets.QComboBox(),
            "final_contour": QtWidgets.QCheckBox("Add final contour pass at full depth"),
            "contour_direction": QtWidgets.QComboBox(),
        }
        controls["origin"].addItems(["center", "lower_left"])
        controls["origin"].setCurrentText(default.origin)
        controls["swap_xy"].setChecked(bool(default.swap_xy))
        controls["pass_axis"].addItems(["x", "y"])
        controls["pass_axis"].setCurrentText(default.pass_axis)
        controls["pass_axis"].setToolTip("Raster pass direction: X means long cutting moves along X, stepping in Y.")
        controls["path_direction"].addItems(["forward", "reverse"])
        controls["path_direction"].setCurrentText(default.path_direction)
        controls["final_contour"].setChecked(bool(default.final_contour))
        controls["contour_direction"].addItems(["cw", "ccw"])
        controls["contour_direction"].setCurrentText(default.contour_direction)
        self._template_controls = controls

        tabs = QtWidgets.QTabWidget()
        geometry_tab = QtWidgets.QWidget()
        geometry_form = QtWidgets.QFormLayout(geometry_tab)
        geometry_form.addRow("Name", controls["name"])
        geometry_form.addRow("Width (mm)", controls["width"])
        geometry_form.addRow("Length (mm)", controls["height"])
        geometry_form.addRow("Depth (mm)", controls["depth"])
        geometry_form.addRow("Origin", controls["origin"])
        geometry_form.addRow("Start X (mm)", controls["start_x"])
        geometry_form.addRow("Start Y (mm)", controls["start_y"])
        geometry_form.addRow("Start Z (mm)", controls["start_z"])
        geometry_form.addRow("Safe Z (mm)", controls["safe_z"])
        tabs.addTab(geometry_tab, "Geometry")

        tool_tab = QtWidgets.QWidget()
        tool_form = QtWidgets.QFormLayout(tool_tab)
        tool_form.addRow("Template cutter diameter (mm)", controls["tool_diameter"])
        tool_form.addRow("Step down (mm)", controls["step_down"])
        tool_form.addRow("Step over (mm)", controls["step_over"])
        tool_form.addRow("Feed (mm/min)", controls["feed_rate"])
        tool_form.addRow("Plunge (mm/min)", controls["plunge_rate"])
        tabs.addTab(tool_tab, "Tool & Feeds")

        axes_tab = QtWidgets.QWidget()
        axes_form = QtWidgets.QFormLayout(axes_tab)
        axes_form.addRow(controls["swap_xy"])
        axes_form.addRow("Raster pass axis", controls["pass_axis"])
        axes_form.addRow("Path order", controls["path_direction"])
        axes_form.addRow(controls["final_contour"])
        axes_form.addRow("Contour direction", controls["contour_direction"])
        tabs.addTab(axes_tab, "Axes & Path")

        cad_tab = QtWidgets.QWidget()
        cad_layout = QtWidgets.QVBoxLayout(cad_tab)
        cad_layout.addWidget(QtWidgets.QLabel("Header source"))
        cad_layout.addWidget(self._template_source_summary)
        cad_layout.addWidget(QtWidgets.QLabel("CAD tool"))
        cad_layout.addWidget(self._template_cad_tool_summary)
        cad_layout.addStretch(1)
        tabs.addTab(cad_tab, "CAD Link")
        layout.addWidget(tabs)

        button_row = QtWidgets.QHBoxLayout()
        self._template_apply_btn = QtWidgets.QPushButton("Apply Template")
        self._template_reset_btn = QtWidgets.QPushButton("Reset Tee-Tablett")
        button_row.addWidget(self._template_apply_btn)
        button_row.addWidget(self._template_reset_btn)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        refresh_source_btn.clicked.connect(self._refresh_template_cad_sources)
        self._template_source_combo.currentIndexChanged.connect(self._update_template_source_summary)
        self._template_apply_btn.clicked.connect(self._on_insert_gcode_template)
        self._template_reset_btn.clicked.connect(self._on_reset_rectangle_template_controls)
        self._populate_rectangle_template_controls(default)
        self._refresh_template_cad_sources()
        _make_collapsible(group, collapsed=True)
        return group

    def _refresh_cam_status(self):
        try:
            from ..cam.workbench import get_cam_workbench_status
        except ImportError:
            from cam.workbench import get_cam_workbench_status

        status = get_cam_workbench_status()
        self._apply_cam_status(status)

    def _apply_cam_status(self, status):
        if self._cam_status is None:
            return

        if status.available:
            label = "CAM Workbench: available"
            if status.module_name:
                label += f" ({status.module_name})"
        else:
            label = "CAM Workbench: unavailable"

        if status.reason:
            label += f" - {status.reason}"
        self._cam_status.setText(label)

        if self._cam_activate_btn is not None:
            self._cam_activate_btn.setEnabled(bool(status.available and status.workbench_name))

    def _on_cam_check(self):
        self._refresh_cam_status()

    def _on_cam_activate(self):
        try:
            from ..cam.workbench import activate_cam_workbench, get_cam_workbench_status
        except ImportError:
            from cam.workbench import activate_cam_workbench, get_cam_workbench_status

        status = get_cam_workbench_status()
        ok, message = activate_cam_workbench(status)
        if message:
            _status_message(f"{message}\n", error=not ok)
        self._refresh_cam_status()

    def _on_cam_generate(self):
        try:
            from ..ai.context import get_selection_context
        except ImportError:
            from ai.context import get_selection_context

        try:
            from ..cam.hybrid import CamJobSettings, SimpleJobSettings, generate_hybrid_gcode
        except ImportError:
            from cam.hybrid import CamJobSettings, SimpleJobSettings, generate_hybrid_gcode

        settings = self._show_cam_settings_dialog()
        if settings is None:
            return
        cam_settings, simple_settings, prefer_cam = settings

        context = get_selection_context()
        target = None
        label = ""
        if context.items:
            item = context.items[0]
            target = item.obj
            label = item.label
        else:
            doc = getattr(App, "ActiveDocument", None)
            active = getattr(doc, "ActiveObject", None) if doc else None
            if active is not None:
                target = active
                label = getattr(active, "Label", None) or getattr(active, "Name", "<active>")

        if target is None:
            message = "; ".join(context.warnings or ["No selection or active object."])
            self._append_console(f"CAM generate failed: {message}", force=True)
            _status_message(f"CAM generate failed: {message}\n", error=True)
            return

        self._append_console(f"Generating CAM for {label}...", force=True)
        try:
            result = generate_hybrid_gcode(
                target,
                cam_settings=cam_settings,
                simple_settings=simple_settings,
                prefer_cam=prefer_cam,
            )
        except Exception as exc:
            self._append_console(f"CAM generate failed: {exc}", force=True)
            _status_message(f"CAM generate failed: {exc}\n", error=True)
            return

        for warning in result.warnings:
            self._append_console(warning, force=True)

        self._gcode_edit.setPlainText(result.gcode or "")
        self._update_preview()
        self._append_console(f"Generated G-code via {result.engine} engine.", force=True)
        _status_message(f"G-code generated via {result.engine} engine.\n")

    def _on_import_dxf(self):
        filters = "DXF (*.dxf);;All Files (*)"
        start_dir = self._last_dxf_path or ""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Import DXF", start_dir, filters)
        if not path:
            return

        settings = self._show_dxf_import_dialog(path)
        if settings is None:
            return

        dxf_path, gcode_settings, import_settings = settings
        if not dxf_path:
            return

        try:
            from ..cam.dxf_import import generate_gcode_from_dxf
        except ImportError:
            from cam.dxf_import import generate_gcode_from_dxf

        self._append_console(f"Generating G-code from DXF: {dxf_path}", force=True)
        try:
            gcode = generate_gcode_from_dxf(dxf_path, gcode_settings, import_settings)
        except Exception as exc:
            self._append_console(f"DXF import failed: {exc}", force=True)
            _status_message(f"DXF import failed: {exc}\n", error=True)
            return

        self._gcode_edit.setPlainText(gcode or "")
        self._last_dxf_path = dxf_path
        self._update_preview()
        self._append_console(f"Generated G-code from DXF: {dxf_path}", force=True)
        _status_message("G-code generated from DXF.\n")

    def _load_cam_generate_defaults(self):
        if App is None:
            return
        params = App.ParamGet("User parameter:BaseApp/Preferences/RouterKing/CAM")
        self._cam_generate_defaults = {
            "prefer_cam": params.GetBool("prefer_cam", True),
            "preset_name": params.GetString("preset_name", "Custom"),
            "units": params.GetString("units", "mm"),
            "feed_rate": params.GetFloat("feed_rate", 500.0),
            "plunge_rate": params.GetFloat("plunge_rate", 150.0),
            "post_processor": params.GetString("post_processor", "grbl_post"),
            "start_depth": params.GetFloat("start_depth", 0.0),
            "final_depth": params.GetFloat("final_depth", -1.0),
            "step_down": params.GetFloat("step_down", 0.5),
            "step_over": params.GetFloat("step_over", 35.0),
            "profile_side": params.GetString("profile_side", "Outside"),
            "profile_direction": params.GetString("profile_direction", "CCW"),
            "safe_z": params.GetFloat("safe_z", 5.0),
            "start_z": params.GetFloat("start_z", 0.0),
            "cut_z": params.GetFloat("cut_z", -1.0),
            "pass_depth": params.GetFloat("pass_depth", 0.5),
            "ramp_length": params.GetFloat("ramp_length", 8.0),
            "lead_in": params.GetFloat("lead_in", 0.5),
            "lead_out": params.GetFloat("lead_out", 0.5),
            "spindle_speed": params.GetInt("spindle_speed", 10000),
            "laser_power": params.GetInt("laser_power", 0),
            "start_spindle": params.GetBool("start_spindle", True),
        }
        self._cam_user_presets = self._load_cam_user_presets(params)

    def _save_cam_generate_defaults(self):
        if App is None:
            return
        params = App.ParamGet("User parameter:BaseApp/Preferences/RouterKing/CAM")
        defaults = self._cam_generate_defaults or {}
        params.SetBool("prefer_cam", bool(defaults.get("prefer_cam", True)))
        params.SetString("preset_name", str(defaults.get("preset_name", "Custom")))
        params.SetString("units", str(defaults.get("units", "mm")))
        params.SetFloat("feed_rate", float(defaults.get("feed_rate", 500.0)))
        params.SetFloat("plunge_rate", float(defaults.get("plunge_rate", 150.0)))
        params.SetString("post_processor", str(defaults.get("post_processor", "grbl_post")))
        params.SetFloat("start_depth", float(defaults.get("start_depth", 0.0)))
        params.SetFloat("final_depth", float(defaults.get("final_depth", -1.0)))
        params.SetFloat("step_down", float(defaults.get("step_down", 0.5)))
        params.SetFloat("step_over", float(defaults.get("step_over", 35.0)))
        params.SetString("profile_side", str(defaults.get("profile_side", "Outside")))
        params.SetString("profile_direction", str(defaults.get("profile_direction", "CCW")))
        params.SetFloat("safe_z", float(defaults.get("safe_z", 5.0)))
        params.SetFloat("start_z", float(defaults.get("start_z", 0.0)))
        params.SetFloat("cut_z", float(defaults.get("cut_z", -1.0)))
        params.SetFloat("pass_depth", float(defaults.get("pass_depth", 0.5)))
        params.SetFloat("ramp_length", float(defaults.get("ramp_length", 8.0)))
        params.SetFloat("lead_in", float(defaults.get("lead_in", 0.5)))
        params.SetFloat("lead_out", float(defaults.get("lead_out", 0.5)))
        params.SetInt("spindle_speed", int(defaults.get("spindle_speed", 10000)))
        params.SetInt("laser_power", int(defaults.get("laser_power", 0)))
        params.SetBool("start_spindle", bool(defaults.get("start_spindle", True)))

    def _load_dxf_import_defaults(self):
        if App is None:
            return
        params = App.ParamGet("User parameter:BaseApp/Preferences/RouterKing/DXF")
        self._dxf_import_defaults = {
            "preset_name": params.GetString("preset_name", "Custom"),
            "units": params.GetString("units", "mm"),
            "feed_rate": params.GetFloat("feed_rate", 800.0),
            "plunge_rate": params.GetFloat("plunge_rate", 300.0),
            "safe_z": params.GetFloat("safe_z", 5.0),
            "start_z": params.GetFloat("start_z", 0.0),
            "cut_z": params.GetFloat("cut_z", -1.0),
            "pass_depth": params.GetFloat("pass_depth", 0.0),
            "ramp_length": params.GetFloat("ramp_length", 0.0),
            "lead_in": params.GetFloat("lead_in", 0.0),
            "lead_out": params.GetFloat("lead_out", 0.0),
            "spindle_speed": params.GetInt("spindle_speed", 0),
            "laser_power": params.GetInt("laser_power", 0),
            "start_spindle": params.GetBool("start_spindle", True),
            "deflection": params.GetFloat("deflection", 0.1),
            "arc_segment_angle": params.GetFloat("arc_segment_angle", 10.0),
            "merge_tolerance": params.GetFloat("merge_tolerance", 1e-6),
            "prefer_ezdxf": params.GetBool("prefer_ezdxf", True),
            "use_freecad": params.GetBool("use_freecad", True),
        }

    def _save_dxf_import_defaults(self):
        if App is None:
            return
        params = App.ParamGet("User parameter:BaseApp/Preferences/RouterKing/DXF")
        defaults = self._dxf_import_defaults or {}
        params.SetString("preset_name", str(defaults.get("preset_name", "Custom")))
        params.SetString("units", str(defaults.get("units", "mm")))
        params.SetFloat("feed_rate", float(defaults.get("feed_rate", 800.0)))
        params.SetFloat("plunge_rate", float(defaults.get("plunge_rate", 300.0)))
        params.SetFloat("safe_z", float(defaults.get("safe_z", 5.0)))
        params.SetFloat("start_z", float(defaults.get("start_z", 0.0)))
        params.SetFloat("cut_z", float(defaults.get("cut_z", -1.0)))
        params.SetFloat("pass_depth", float(defaults.get("pass_depth", 0.0)))
        params.SetFloat("ramp_length", float(defaults.get("ramp_length", 0.0)))
        params.SetFloat("lead_in", float(defaults.get("lead_in", 0.0)))
        params.SetFloat("lead_out", float(defaults.get("lead_out", 0.0)))
        params.SetInt("spindle_speed", int(defaults.get("spindle_speed", 0)))
        params.SetInt("laser_power", int(defaults.get("laser_power", 0)))
        params.SetBool("start_spindle", bool(defaults.get("start_spindle", True)))
        params.SetFloat("deflection", float(defaults.get("deflection", 0.1)))
        params.SetFloat("arc_segment_angle", float(defaults.get("arc_segment_angle", 10.0)))
        params.SetFloat("merge_tolerance", float(defaults.get("merge_tolerance", 1e-6)))
        params.SetBool("prefer_ezdxf", bool(defaults.get("prefer_ezdxf", True)))
        params.SetBool("use_freecad", bool(defaults.get("use_freecad", True)))

    def _load_controller_defaults(self):
        if App is None:
            return
        params = App.ParamGet("User parameter:BaseApp/Preferences/RouterKing/Controller")
        manual_clearance = params.GetFloat("manual_clearance", -1.0)
        if manual_clearance < 0.0:
            manual_clearance = self._default_manual_xyz_clearance()
        self._controller_defaults = {
            "enabled": params.GetBool("enabled", False),
            "xy_step": params.GetFloat("xy_step", 0.5),
            "z_step": params.GetFloat("z_step", 0.1),
            "feed_rate": params.GetFloat("feed_rate", 600.0),
            "deadzone": params.GetFloat("deadzone", 0.20),
            "manual_clearance": manual_clearance,
        }
        for key, default_value in DEFAULT_CONTROLLER_BINDINGS.items():
            try:
                value = params.GetString(key, default_value)
            except TypeError:
                value = params.GetString(key) or default_value
            self._controller_defaults[key] = value

    def _save_controller_defaults(self):
        if App is None:
            return
        params = App.ParamGet("User parameter:BaseApp/Preferences/RouterKing/Controller")
        enable = getattr(self, "_controller_enable", None)
        xy_step = getattr(self, "_controller_xy_step", None)
        z_step = getattr(self, "_controller_z_step", None)
        feed = getattr(self, "_controller_feed", None)
        deadzone = getattr(self, "_controller_deadzone", None)
        manual_clearance = getattr(self, "_controller_manual_clearance", None)
        binding_edits = getattr(self, "_controller_binding_edits", {})
        defaults = {
            "enabled": bool(enable.isChecked()) if enable is not None else False,
            "xy_step": float(xy_step.value()) if xy_step is not None else 0.5,
            "z_step": float(z_step.value()) if z_step is not None else 0.1,
            "feed_rate": float(feed.value()) if feed is not None else 600.0,
            "deadzone": float(deadzone.value()) if deadzone is not None else 0.20,
            "manual_clearance": (
                float(manual_clearance.value()) if manual_clearance is not None else self._default_manual_xyz_clearance()
            ),
        }
        for key, default_value in DEFAULT_CONTROLLER_BINDINGS.items():
            edit = binding_edits.get(key)
            defaults[key] = str(edit.text()).strip() if edit is not None else default_value
        params.SetBool("enabled", defaults["enabled"])
        params.SetFloat("xy_step", defaults["xy_step"])
        params.SetFloat("z_step", defaults["z_step"])
        params.SetFloat("feed_rate", defaults["feed_rate"])
        params.SetFloat("deadzone", defaults["deadzone"])
        params.SetFloat("manual_clearance", defaults["manual_clearance"])
        for key in DEFAULT_CONTROLLER_BINDINGS:
            params.SetString(key, defaults[key])
        self._controller_defaults = defaults

    def _default_manual_xyz_clearance(self):
        try:
            profile, _profile_path = grbl_load_machine_profile(None)
        except Exception:
            profile = {}
        probe = dict((profile or {}).get("probe") or {})
        try:
            block_height = float(probe.get("block_height", 15.0))
        except (TypeError, ValueError):
            block_height = 15.0
        return max(0.0, block_height * 0.10)

    def _load_cam_user_presets(self, params=None):
        if App is None:
            return []
        if params is None:
            params = App.ParamGet("User parameter:BaseApp/Preferences/RouterKing/CAM")
        raw = params.GetString("user_presets", "")
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except Exception:
            return []
        presets = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name", "")).strip()
            values = entry.get("values")
            if not name or not isinstance(values, dict):
                continue
            presets.append((name, values))
        return presets

    def _save_cam_user_presets(self, params=None):
        if App is None:
            return
        if params is None:
            params = App.ParamGet("User parameter:BaseApp/Preferences/RouterKing/CAM")
        payload = [{"name": name, "values": values} for name, values in self._cam_user_presets]
        try:
            raw = json.dumps(payload, separators=(",", ":"))
        except Exception:
            return
        params.SetString("user_presets", raw)

    def _show_cam_settings_dialog(self):
        try:
            from ..cam.hybrid import CamJobSettings
        except ImportError:
            from cam.hybrid import CamJobSettings
        try:
            from ..cam.simple_engine import SimpleJobSettings
        except ImportError:
            from cam.simple_engine import SimpleJobSettings

        defaults = dict(self._cam_generate_defaults or {})
        cam_defaults = CamJobSettings()
        simple_defaults = SimpleJobSettings()

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Generate CAM G-code")
        layout = QtWidgets.QVBoxLayout(dialog)

        general_group = QtWidgets.QGroupBox("General")
        general_layout = QtWidgets.QFormLayout(general_group)
        prefer_cam = QtWidgets.QCheckBox("Prefer CAM/Path when available")
        prefer_cam.setChecked(defaults.get("prefer_cam", True))
        general_layout.addRow(prefer_cam)

        preset_combo = QtWidgets.QComboBox()
        preset_name = defaults.get("preset_name", "Custom")
        preset_row = QtWidgets.QHBoxLayout()
        preset_row.addWidget(preset_combo, 1)
        preset_apply_btn = QtWidgets.QPushButton("Apply Preset")
        preset_save_btn = QtWidgets.QPushButton("Save Preset")
        preset_delete_btn = QtWidgets.QPushButton("Delete Preset")
        preset_row.addWidget(preset_apply_btn)
        preset_row.addWidget(preset_save_btn)
        preset_row.addWidget(preset_delete_btn)
        general_layout.addRow("Preset", preset_row)

        units = QtWidgets.QComboBox()
        units.addItems(["mm", "inch"])
        units.setCurrentText(defaults.get("units", simple_defaults.units))
        general_layout.addRow("Units", units)

        feed_rate = QtWidgets.QDoubleSpinBox()
        feed_rate.setDecimals(1)
        feed_rate.setRange(0, 50000)
        feed_rate.setValue(defaults.get("feed_rate", cam_defaults.feed_rate))
        general_layout.addRow("Feed rate (mm/min)", feed_rate)

        plunge_rate = QtWidgets.QDoubleSpinBox()
        plunge_rate.setDecimals(1)
        plunge_rate.setRange(0, 50000)
        plunge_rate.setValue(defaults.get("plunge_rate", cam_defaults.plunge_rate))
        general_layout.addRow("Plunge rate (mm/min)", plunge_rate)
        layout.addWidget(general_group)

        cam_group = QtWidgets.QGroupBox("CAM/Path job")
        cam_layout = QtWidgets.QFormLayout(cam_group)
        post_processor = QtWidgets.QLineEdit(defaults.get("post_processor", cam_defaults.post_processor))
        cam_layout.addRow("Post processor", post_processor)

        start_depth = QtWidgets.QDoubleSpinBox()
        start_depth.setDecimals(3)
        start_depth.setRange(-1000, 1000)
        start_depth.setValue(defaults.get("start_depth", cam_defaults.start_depth))
        cam_layout.addRow("Start depth", start_depth)

        final_depth = QtWidgets.QDoubleSpinBox()
        final_depth.setDecimals(3)
        final_depth.setRange(-1000, 1000)
        final_depth.setValue(defaults.get("final_depth", cam_defaults.final_depth))
        cam_layout.addRow("Final depth", final_depth)

        step_down = QtWidgets.QDoubleSpinBox()
        step_down.setDecimals(3)
        step_down.setRange(0, 1000)
        step_down.setValue(defaults.get("step_down", cam_defaults.step_down))
        cam_layout.addRow("Step down", step_down)

        profile_side = QtWidgets.QComboBox()
        profile_side.addItems(["Outside", "Inside", "On"])
        profile_side.setCurrentText(defaults.get("profile_side", cam_defaults.profile_side))
        cam_layout.addRow("Profile side", profile_side)

        profile_direction = QtWidgets.QComboBox()
        profile_direction.addItems(["CCW", "CW"])
        profile_direction.setCurrentText(defaults.get("profile_direction", cam_defaults.profile_direction))
        cam_layout.addRow("Profile direction", profile_direction)
        layout.addWidget(cam_group)

        simple_group = QtWidgets.QGroupBox("Simple fallback")
        simple_layout = QtWidgets.QFormLayout(simple_group)
        safe_z = QtWidgets.QDoubleSpinBox()
        safe_z.setDecimals(3)
        safe_z.setRange(-1000, 1000)
        safe_z.setValue(defaults.get("safe_z", simple_defaults.safe_z))
        simple_layout.addRow("Safe Z", safe_z)

        start_z = QtWidgets.QDoubleSpinBox()
        start_z.setDecimals(3)
        start_z.setRange(-1000, 1000)
        start_z.setValue(defaults.get("start_z", simple_defaults.start_z))
        simple_layout.addRow("Start Z", start_z)

        cut_z = QtWidgets.QDoubleSpinBox()
        cut_z.setDecimals(3)
        cut_z.setRange(-1000, 1000)
        cut_z.setValue(defaults.get("cut_z", simple_defaults.cut_z))
        simple_layout.addRow("Cut Z", cut_z)

        pass_depth = QtWidgets.QDoubleSpinBox()
        pass_depth.setDecimals(3)
        pass_depth.setRange(0, 1000)
        pass_depth.setValue(defaults.get("pass_depth", simple_defaults.pass_depth))
        simple_layout.addRow("Pass depth", pass_depth)

        ramp_length = QtWidgets.QDoubleSpinBox()
        ramp_length.setDecimals(3)
        ramp_length.setRange(0, 10000)
        ramp_length.setValue(defaults.get("ramp_length", simple_defaults.ramp_length))
        simple_layout.addRow("Ramp length", ramp_length)

        lead_in = QtWidgets.QDoubleSpinBox()
        lead_in.setDecimals(3)
        lead_in.setRange(0, 10000)
        lead_in.setValue(defaults.get("lead_in", simple_defaults.lead_in))
        simple_layout.addRow("Lead-in", lead_in)

        lead_out = QtWidgets.QDoubleSpinBox()
        lead_out.setDecimals(3)
        lead_out.setRange(0, 10000)
        lead_out.setValue(defaults.get("lead_out", simple_defaults.lead_out))
        simple_layout.addRow("Lead-out", lead_out)

        spindle_speed = QtWidgets.QSpinBox()
        spindle_speed.setRange(0, 60000)
        spindle_speed.setValue(defaults.get("spindle_speed", simple_defaults.spindle_speed))
        simple_layout.addRow("Spindle speed (M3 S)", spindle_speed)

        laser_power = QtWidgets.QSpinBox()
        laser_power.setRange(0, 10000)
        laser_power.setValue(defaults.get("laser_power", simple_defaults.laser_power))
        simple_layout.addRow("Laser power (M3 S)", laser_power)

        start_spindle = QtWidgets.QCheckBox("Start spindle/laser (M3)")
        start_spindle.setChecked(defaults.get("start_spindle", simple_defaults.start_spindle))
        simple_layout.addRow(start_spindle)
        layout.addWidget(simple_group)

        preset_map = {}

        def refresh_preset_combo(selected=None):
            entries = list(_CAM_PRESETS) + list(self._cam_user_presets)
            names = [name for name, _preset in entries]
            preset_combo.blockSignals(True)
            preset_combo.clear()
            preset_combo.addItems(names)
            if selected in names:
                preset_combo.setCurrentText(selected)
            else:
                preset_combo.setCurrentText("Custom")
            preset_combo.blockSignals(False)
            preset_map.clear()
            preset_map.update({name: preset for name, preset in entries})

        builtin_names = {preset_name for preset_name, _preset in _CAM_PRESETS}

        def apply_preset(name):
            if name == "Custom":
                return
            preset = preset_map.get(name, {})
            if not preset:
                return
            if "prefer_cam" in preset:
                prefer_cam.setChecked(bool(preset["prefer_cam"]))
            if "units" in preset:
                units.setCurrentText(preset["units"])
            if "feed_rate" in preset:
                feed_rate.setValue(preset["feed_rate"])
            if "plunge_rate" in preset:
                plunge_rate.setValue(preset["plunge_rate"])
            if "post_processor" in preset:
                post_processor.setText(preset["post_processor"])
            if "start_depth" in preset:
                start_depth.setValue(preset["start_depth"])
            if "final_depth" in preset:
                final_depth.setValue(preset["final_depth"])
            if "step_down" in preset:
                step_down.setValue(preset["step_down"])
            if "profile_side" in preset:
                profile_side.setCurrentText(preset["profile_side"])
            if "profile_direction" in preset:
                profile_direction.setCurrentText(preset["profile_direction"])
            if "safe_z" in preset:
                safe_z.setValue(preset["safe_z"])
            if "start_z" in preset:
                start_z.setValue(preset["start_z"])
            if "cut_z" in preset:
                cut_z.setValue(preset["cut_z"])
            if "pass_depth" in preset:
                pass_depth.setValue(preset["pass_depth"])
            if "ramp_length" in preset:
                ramp_length.setValue(preset["ramp_length"])
            if "lead_in" in preset:
                lead_in.setValue(preset["lead_in"])
            if "lead_out" in preset:
                lead_out.setValue(preset["lead_out"])
            if "spindle_speed" in preset:
                spindle_speed.setValue(preset["spindle_speed"])
            if "laser_power" in preset:
                laser_power.setValue(preset["laser_power"])
            if "start_spindle" in preset:
                start_spindle.setChecked(bool(preset["start_spindle"]))

        preset_combo.currentTextChanged.connect(apply_preset)
        preset_apply_btn.clicked.connect(lambda: apply_preset(preset_combo.currentText()))
        refresh_preset_combo(preset_name)

        def collect_preset_values():
            return {
                "prefer_cam": prefer_cam.isChecked(),
                "units": units.currentText(),
                "feed_rate": feed_rate.value(),
                "plunge_rate": plunge_rate.value(),
                "post_processor": post_processor.text().strip() or cam_defaults.post_processor,
                "start_depth": start_depth.value(),
                "final_depth": final_depth.value(),
                "step_down": step_down.value(),
                "profile_side": profile_side.currentText(),
                "profile_direction": profile_direction.currentText(),
                "safe_z": safe_z.value(),
                "start_z": start_z.value(),
                "cut_z": cut_z.value(),
                "pass_depth": pass_depth.value(),
                "ramp_length": ramp_length.value(),
                "lead_in": lead_in.value(),
                "lead_out": lead_out.value(),
                "spindle_speed": spindle_speed.value(),
                "laser_power": laser_power.value(),
                "start_spindle": start_spindle.isChecked(),
            }

        def save_preset():
            name, ok = QtWidgets.QInputDialog.getText(
                dialog,
                "Save Preset",
                "Preset name:",
                text=preset_combo.currentText(),
            )
            if not ok:
                return
            name = name.strip()
            if not name:
                QtWidgets.QMessageBox.warning(dialog, "Save Preset", "Preset name cannot be empty.")
                return
            if name == "Custom":
                QtWidgets.QMessageBox.warning(dialog, "Save Preset", "'Custom' is reserved.")
                return
            if name in builtin_names:
                QtWidgets.QMessageBox.warning(
                    dialog,
                    "Save Preset",
                    "Preset name matches a built-in preset. Choose another name.",
                )
                return

            existing_index = None
            for idx, (existing_name, _preset) in enumerate(self._cam_user_presets):
                if existing_name == name:
                    existing_index = idx
                    break
            if existing_index is not None:
                result = QtWidgets.QMessageBox.question(
                    dialog,
                    "Overwrite Preset?",
                    f"Preset '{name}' already exists. Overwrite it?",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                )
                if result != QtWidgets.QMessageBox.Yes:
                    return
                self._cam_user_presets[existing_index] = (name, collect_preset_values())
            else:
                self._cam_user_presets.append((name, collect_preset_values()))

            self._save_cam_user_presets()
            self._cam_generate_defaults["preset_name"] = name
            self._save_cam_generate_defaults()
            refresh_preset_combo(name)
            _status_message(f"Saved preset: {name}\n")

        preset_save_btn.clicked.connect(save_preset)

        def delete_preset():
            name = preset_combo.currentText()
            if not name or name == "Custom":
                QtWidgets.QMessageBox.information(
                    dialog,
                    "Delete Preset",
                    "Select a user preset to delete.",
                )
                return
            if name in builtin_names:
                QtWidgets.QMessageBox.information(
                    dialog,
                    "Delete Preset",
                    "Built-in presets cannot be deleted.",
                )
                return

            match_index = None
            for idx, (existing_name, _preset) in enumerate(self._cam_user_presets):
                if existing_name == name:
                    match_index = idx
                    break
            if match_index is None:
                QtWidgets.QMessageBox.information(
                    dialog,
                    "Delete Preset",
                    "Preset not found.",
                )
                return

            result = QtWidgets.QMessageBox.question(
                dialog,
                "Delete Preset?",
                f"Delete preset '{name}'?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            )
            if result != QtWidgets.QMessageBox.Yes:
                return

            self._cam_user_presets.pop(match_index)
            self._save_cam_user_presets()
            self._cam_generate_defaults["preset_name"] = "Custom"
            self._save_cam_generate_defaults()
            refresh_preset_combo("Custom")
            _status_message(f"Deleted preset: {name}\n")

        preset_delete_btn.clicked.connect(delete_preset)

        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch(1)
        ok_btn = QtWidgets.QPushButton("Generate")
        cancel_btn = QtWidgets.QPushButton("Cancel")
        button_row.addWidget(ok_btn)
        button_row.addWidget(cancel_btn)
        layout.addLayout(button_row)

        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return None

        cam_settings = CamJobSettings(
            post_processor=post_processor.text().strip() or cam_defaults.post_processor,
            start_depth=start_depth.value(),
            final_depth=final_depth.value(),
            step_down=step_down.value(),
            profile_side=profile_side.currentText(),
            profile_direction=profile_direction.currentText(),
            feed_rate=feed_rate.value(),
            plunge_rate=plunge_rate.value(),
        )
        simple_settings = SimpleJobSettings(
            safe_z=safe_z.value(),
            cut_z=cut_z.value(),
            start_z=start_z.value(),
            pass_depth=pass_depth.value(),
            ramp_length=ramp_length.value(),
            lead_in=lead_in.value(),
            lead_out=lead_out.value(),
            feed_rate=feed_rate.value(),
            plunge_rate=plunge_rate.value(),
            units=units.currentText(),
            spindle_speed=spindle_speed.value(),
            laser_power=laser_power.value(),
            start_spindle=start_spindle.isChecked(),
        )

        self._cam_generate_defaults = {
            "prefer_cam": prefer_cam.isChecked(),
            "preset_name": preset_combo.currentText(),
            "units": units.currentText(),
            "feed_rate": feed_rate.value(),
            "plunge_rate": plunge_rate.value(),
            "post_processor": cam_settings.post_processor,
            "start_depth": cam_settings.start_depth,
            "final_depth": cam_settings.final_depth,
            "step_down": cam_settings.step_down,
            "profile_side": cam_settings.profile_side,
            "profile_direction": cam_settings.profile_direction,
            "safe_z": simple_settings.safe_z,
            "start_z": simple_settings.start_z,
            "cut_z": simple_settings.cut_z,
            "pass_depth": simple_settings.pass_depth,
            "ramp_length": simple_settings.ramp_length,
            "lead_in": simple_settings.lead_in,
            "lead_out": simple_settings.lead_out,
            "spindle_speed": simple_settings.spindle_speed,
            "laser_power": simple_settings.laser_power,
            "start_spindle": simple_settings.start_spindle,
        }
        self._save_cam_generate_defaults()

        return cam_settings, simple_settings, prefer_cam.isChecked()

    def _show_dxf_import_dialog(self, path):
        try:
            from ..cam.dxf_import import DxfImportSettings
        except ImportError:
            from cam.dxf_import import DxfImportSettings
        try:
            from ..cam.simple_engine import SimpleJobSettings
        except ImportError:
            from cam.simple_engine import SimpleJobSettings

        defaults = dict(self._dxf_import_defaults or {})
        simple_defaults = SimpleJobSettings()
        import_defaults = DxfImportSettings()

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Import DXF")
        layout = QtWidgets.QVBoxLayout(dialog)

        file_group = QtWidgets.QGroupBox("DXF file")
        file_layout = QtWidgets.QHBoxLayout(file_group)
        file_path = QtWidgets.QLineEdit(path)
        file_path.setReadOnly(True)
        browse_btn = QtWidgets.QPushButton("Browse")
        file_layout.addWidget(file_path, 1)
        file_layout.addWidget(browse_btn)
        layout.addWidget(file_group)

        def browse_path():
            start_dir = os.path.dirname(file_path.text()) or (self._last_dxf_path or "")
            new_path, _ = QtWidgets.QFileDialog.getOpenFileName(
                dialog,
                "Select DXF",
                start_dir,
                "DXF (*.dxf);;All Files (*)",
            )
            if new_path:
                file_path.setText(new_path)

        browse_btn.clicked.connect(browse_path)

        preset_group = QtWidgets.QGroupBox("Preset")
        preset_layout = QtWidgets.QFormLayout(preset_group)
        preset_combo = QtWidgets.QComboBox()
        preset_row = QtWidgets.QHBoxLayout()
        preset_row.addWidget(preset_combo, 1)
        preset_apply_btn = QtWidgets.QPushButton("Apply Preset")
        preset_save_btn = QtWidgets.QPushButton("Save Preset")
        preset_delete_btn = QtWidgets.QPushButton("Delete Preset")
        preset_row.addWidget(preset_apply_btn)
        preset_row.addWidget(preset_save_btn)
        preset_row.addWidget(preset_delete_btn)
        preset_layout.addRow("Preset", preset_row)
        layout.addWidget(preset_group)

        settings_group = QtWidgets.QGroupBox("Toolpath")
        settings_layout = QtWidgets.QFormLayout(settings_group)

        units = QtWidgets.QComboBox()
        units.addItems(["mm", "inch"])
        units.setCurrentText(defaults.get("units", simple_defaults.units))
        settings_layout.addRow("Units", units)

        feed_rate = QtWidgets.QDoubleSpinBox()
        feed_rate.setDecimals(1)
        feed_rate.setRange(0, 50000)
        feed_rate.setValue(defaults.get("feed_rate", simple_defaults.feed_rate))
        settings_layout.addRow("Feed rate (mm/min)", feed_rate)

        plunge_rate = QtWidgets.QDoubleSpinBox()
        plunge_rate.setDecimals(1)
        plunge_rate.setRange(0, 50000)
        plunge_rate.setValue(defaults.get("plunge_rate", simple_defaults.plunge_rate))
        settings_layout.addRow("Plunge rate (mm/min)", plunge_rate)

        safe_z = QtWidgets.QDoubleSpinBox()
        safe_z.setDecimals(3)
        safe_z.setRange(-1000, 1000)
        safe_z.setValue(defaults.get("safe_z", simple_defaults.safe_z))
        settings_layout.addRow("Safe Z", safe_z)

        start_z = QtWidgets.QDoubleSpinBox()
        start_z.setDecimals(3)
        start_z.setRange(-1000, 1000)
        start_z.setValue(defaults.get("start_z", simple_defaults.start_z))
        settings_layout.addRow("Start Z", start_z)

        cut_z = QtWidgets.QDoubleSpinBox()
        cut_z.setDecimals(3)
        cut_z.setRange(-1000, 1000)
        cut_z.setValue(defaults.get("cut_z", simple_defaults.cut_z))
        settings_layout.addRow("Cut Z", cut_z)

        pass_depth = QtWidgets.QDoubleSpinBox()
        pass_depth.setDecimals(3)
        pass_depth.setRange(0, 1000)
        pass_depth.setValue(defaults.get("pass_depth", simple_defaults.pass_depth))
        settings_layout.addRow("Pass depth", pass_depth)

        ramp_length = QtWidgets.QDoubleSpinBox()
        ramp_length.setDecimals(3)
        ramp_length.setRange(0, 10000)
        ramp_length.setValue(defaults.get("ramp_length", simple_defaults.ramp_length))
        settings_layout.addRow("Ramp length", ramp_length)

        lead_in = QtWidgets.QDoubleSpinBox()
        lead_in.setDecimals(3)
        lead_in.setRange(0, 10000)
        lead_in.setValue(defaults.get("lead_in", simple_defaults.lead_in))
        settings_layout.addRow("Lead-in", lead_in)

        lead_out = QtWidgets.QDoubleSpinBox()
        lead_out.setDecimals(3)
        lead_out.setRange(0, 10000)
        lead_out.setValue(defaults.get("lead_out", simple_defaults.lead_out))
        settings_layout.addRow("Lead-out", lead_out)

        spindle_speed = QtWidgets.QSpinBox()
        spindle_speed.setRange(0, 60000)
        spindle_speed.setValue(defaults.get("spindle_speed", simple_defaults.spindle_speed))
        settings_layout.addRow("Spindle speed (M3 S)", spindle_speed)

        laser_power = QtWidgets.QSpinBox()
        laser_power.setRange(0, 10000)
        laser_power.setValue(defaults.get("laser_power", simple_defaults.laser_power))
        settings_layout.addRow("Laser power (M3 S)", laser_power)

        start_spindle = QtWidgets.QCheckBox("Start spindle/laser (M3)")
        start_spindle.setChecked(defaults.get("start_spindle", simple_defaults.start_spindle))
        settings_layout.addRow(start_spindle)
        layout.addWidget(settings_group)

        import_group = QtWidgets.QGroupBox("DXF import")
        import_layout = QtWidgets.QFormLayout(import_group)

        deflection = QtWidgets.QDoubleSpinBox()
        deflection.setDecimals(4)
        deflection.setRange(0, 10.0)
        deflection.setValue(defaults.get("deflection", import_defaults.deflection))
        import_layout.addRow("Deflection", deflection)

        arc_segment_angle = QtWidgets.QDoubleSpinBox()
        arc_segment_angle.setDecimals(1)
        arc_segment_angle.setRange(1.0, 90.0)
        arc_segment_angle.setValue(
            defaults.get("arc_segment_angle", import_defaults.arc_segment_angle)
        )
        import_layout.addRow("Arc segment angle", arc_segment_angle)

        merge_tolerance = QtWidgets.QDoubleSpinBox()
        merge_tolerance.setDecimals(6)
        merge_tolerance.setRange(0.0, 1.0)
        merge_tolerance.setValue(defaults.get("merge_tolerance", import_defaults.merge_tolerance))
        import_layout.addRow("Merge tolerance", merge_tolerance)

        use_freecad = QtWidgets.QCheckBox("Use FreeCAD import when available")
        use_freecad.setChecked(defaults.get("use_freecad", import_defaults.use_freecad))
        import_layout.addRow(use_freecad)

        prefer_ezdxf = QtWidgets.QCheckBox("Prefer ezdxf")
        prefer_ezdxf.setChecked(defaults.get("prefer_ezdxf", import_defaults.prefer_ezdxf))
        import_layout.addRow(prefer_ezdxf)
        layout.addWidget(import_group)

        preset_map = {}

        def refresh_preset_combo(selected=None):
            entries = list(_CAM_PRESETS) + list(self._cam_user_presets)
            names = [name for name, _preset in entries]
            preset_combo.blockSignals(True)
            preset_combo.clear()
            preset_combo.addItems(names)
            if selected in names:
                preset_combo.setCurrentText(selected)
            else:
                preset_combo.setCurrentText("Custom")
            preset_combo.blockSignals(False)
            preset_map.clear()
            preset_map.update({name: preset for name, preset in entries})

        builtin_names = {preset_name for preset_name, _preset in _CAM_PRESETS}

        def apply_preset(name):
            if name == "Custom":
                return
            preset = preset_map.get(name, {})
            if not preset:
                return
            if "units" in preset:
                units.setCurrentText(preset["units"])
            if "feed_rate" in preset:
                feed_rate.setValue(preset["feed_rate"])
            if "plunge_rate" in preset:
                plunge_rate.setValue(preset["plunge_rate"])
            if "safe_z" in preset:
                safe_z.setValue(preset["safe_z"])
            if "start_z" in preset:
                start_z.setValue(preset["start_z"])
            if "cut_z" in preset:
                cut_z.setValue(preset["cut_z"])
            if "pass_depth" in preset:
                pass_depth.setValue(preset["pass_depth"])
            if "ramp_length" in preset:
                ramp_length.setValue(preset["ramp_length"])
            if "lead_in" in preset:
                lead_in.setValue(preset["lead_in"])
            if "lead_out" in preset:
                lead_out.setValue(preset["lead_out"])
            if "spindle_speed" in preset:
                spindle_speed.setValue(preset["spindle_speed"])
            if "laser_power" in preset:
                laser_power.setValue(preset["laser_power"])
            if "start_spindle" in preset:
                start_spindle.setChecked(bool(preset["start_spindle"]))

        preset_combo.currentTextChanged.connect(apply_preset)
        preset_apply_btn.clicked.connect(lambda: apply_preset(preset_combo.currentText()))
        refresh_preset_combo(defaults.get("preset_name", "Custom"))

        def collect_preset_values():
            return {
                "units": units.currentText(),
                "feed_rate": feed_rate.value(),
                "plunge_rate": plunge_rate.value(),
                "safe_z": safe_z.value(),
                "start_z": start_z.value(),
                "cut_z": cut_z.value(),
                "pass_depth": pass_depth.value(),
                "ramp_length": ramp_length.value(),
                "lead_in": lead_in.value(),
                "lead_out": lead_out.value(),
                "spindle_speed": spindle_speed.value(),
                "laser_power": laser_power.value(),
                "start_spindle": start_spindle.isChecked(),
            }

        def save_preset():
            name, ok = QtWidgets.QInputDialog.getText(
                dialog,
                "Save Preset",
                "Preset name:",
                text=preset_combo.currentText(),
            )
            if not ok:
                return
            name = name.strip()
            if not name:
                QtWidgets.QMessageBox.warning(dialog, "Save Preset", "Preset name cannot be empty.")
                return
            if name == "Custom":
                QtWidgets.QMessageBox.warning(dialog, "Save Preset", "'Custom' is reserved.")
                return
            if name in builtin_names:
                QtWidgets.QMessageBox.warning(
                    dialog,
                    "Save Preset",
                    "Preset name matches a built-in preset. Choose another name.",
                )
                return

            existing_index = None
            for idx, (existing_name, _preset) in enumerate(self._cam_user_presets):
                if existing_name == name:
                    existing_index = idx
                    break
            if existing_index is not None:
                result = QtWidgets.QMessageBox.question(
                    dialog,
                    "Overwrite Preset?",
                    f"Preset '{name}' already exists. Overwrite it?",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                )
                if result != QtWidgets.QMessageBox.Yes:
                    return
                self._cam_user_presets[existing_index] = (name, collect_preset_values())
            else:
                self._cam_user_presets.append((name, collect_preset_values()))

            self._save_cam_user_presets()
            self._dxf_import_defaults["preset_name"] = name
            self._save_dxf_import_defaults()
            refresh_preset_combo(name)
            _status_message(f"Saved preset: {name}\n")

        preset_save_btn.clicked.connect(save_preset)

        def delete_preset():
            name = preset_combo.currentText()
            if not name or name == "Custom":
                QtWidgets.QMessageBox.information(
                    dialog,
                    "Delete Preset",
                    "Select a user preset to delete.",
                )
                return
            if name in builtin_names:
                QtWidgets.QMessageBox.information(
                    dialog,
                    "Delete Preset",
                    "Built-in presets cannot be deleted.",
                )
                return

            match_index = None
            for idx, (existing_name, _preset) in enumerate(self._cam_user_presets):
                if existing_name == name:
                    match_index = idx
                    break
            if match_index is None:
                QtWidgets.QMessageBox.information(
                    dialog,
                    "Delete Preset",
                    "Preset not found.",
                )
                return

            result = QtWidgets.QMessageBox.question(
                dialog,
                "Delete Preset?",
                f"Delete preset '{name}'?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            )
            if result != QtWidgets.QMessageBox.Yes:
                return

            self._cam_user_presets.pop(match_index)
            self._save_cam_user_presets()
            self._dxf_import_defaults["preset_name"] = "Custom"
            self._save_dxf_import_defaults()
            refresh_preset_combo("Custom")
            _status_message(f"Deleted preset: {name}\n")

        preset_delete_btn.clicked.connect(delete_preset)

        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch(1)
        ok_btn = QtWidgets.QPushButton("Generate")
        cancel_btn = QtWidgets.QPushButton("Cancel")
        button_row.addWidget(ok_btn)
        button_row.addWidget(cancel_btn)
        layout.addLayout(button_row)

        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return None

        dxf_path = file_path.text().strip()
        if not dxf_path:
            return None

        simple_settings = SimpleJobSettings(
            safe_z=safe_z.value(),
            cut_z=cut_z.value(),
            start_z=start_z.value(),
            pass_depth=pass_depth.value(),
            ramp_length=ramp_length.value(),
            lead_in=lead_in.value(),
            lead_out=lead_out.value(),
            feed_rate=feed_rate.value(),
            plunge_rate=plunge_rate.value(),
            units=units.currentText(),
            spindle_speed=spindle_speed.value(),
            laser_power=laser_power.value(),
            start_spindle=start_spindle.isChecked(),
        )
        import_settings = DxfImportSettings(
            deflection=deflection.value(),
            arc_segment_angle=arc_segment_angle.value(),
            merge_tolerance=merge_tolerance.value(),
            prefer_ezdxf=prefer_ezdxf.isChecked(),
            use_freecad=use_freecad.isChecked(),
        )

        self._dxf_import_defaults = {
            "preset_name": preset_combo.currentText(),
            "units": units.currentText(),
            "feed_rate": feed_rate.value(),
            "plunge_rate": plunge_rate.value(),
            "safe_z": safe_z.value(),
            "start_z": start_z.value(),
            "cut_z": cut_z.value(),
            "pass_depth": pass_depth.value(),
            "ramp_length": ramp_length.value(),
            "lead_in": lead_in.value(),
            "lead_out": lead_out.value(),
            "spindle_speed": spindle_speed.value(),
            "laser_power": laser_power.value(),
            "start_spindle": start_spindle.isChecked(),
            "deflection": deflection.value(),
            "arc_segment_angle": arc_segment_angle.value(),
            "merge_tolerance": merge_tolerance.value(),
            "prefer_ezdxf": prefer_ezdxf.isChecked(),
            "use_freecad": use_freecad.isChecked(),
        }
        self._save_dxf_import_defaults()

        return dxf_path, simple_settings, import_settings

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
        self._ai_model.addItems(list(_DEFAULT_AI_MODELS))
        settings_layout.addWidget(self._ai_model, 3, 1)

        settings_layout.addWidget(QtWidgets.QLabel("Reasoning effort"), 4, 0)
        self._ai_reasoning = QtWidgets.QComboBox()
        self._ai_reasoning.addItems(["off", "low", "medium", "high"])
        settings_layout.addWidget(self._ai_reasoning, 4, 1)

        settings_layout.addWidget(QtWidgets.QLabel("Allow AI actions"), 5, 0)
        self._ai_allow_actions = QtWidgets.QCheckBox("Enable model-driven edits")
        self._ai_allow_actions.setToolTip(
            "Allow the LLM to create/modify geometry via RouterKing actions."
        )
        settings_layout.addWidget(self._ai_allow_actions, 5, 1)

        self._ai_save_btn = QtWidgets.QPushButton("Save Settings")
        self._ai_settings_status = QtWidgets.QLabel()
        self._set_ai_settings_status()
        settings_layout.addWidget(self._ai_save_btn, 6, 1)
        settings_layout.addWidget(self._ai_settings_status, 7, 0, 1, 2)
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
        self._ai_cam_btn = QtWidgets.QPushButton("Analyze G-Code")
        self._ai_clear_btn = QtWidgets.QPushButton("Clear")
        action_row.addWidget(self._ai_analyze_btn)
        action_row.addWidget(self._ai_optimize_btn)
        action_row.addWidget(self._ai_cam_btn)
        action_row.addWidget(self._ai_clear_btn)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        apply_row = QtWidgets.QHBoxLayout()
        self._ai_apply_btn = QtWidgets.QPushButton("Apply Preview")
        self._ai_discard_btn = QtWidgets.QPushButton("Discard Preview")
        self._ai_apply_btn.setEnabled(False)
        self._ai_discard_btn.setEnabled(False)
        apply_row.addWidget(self._ai_apply_btn)
        apply_row.addWidget(self._ai_discard_btn)
        apply_row.addStretch(1)
        layout.addLayout(apply_row)

        self._ai_status = QtWidgets.QLabel("Select geometry and click Analyze.")
        layout.addWidget(self._ai_status)

        self._ai_progress = QtWidgets.QProgressBar()
        self._ai_progress.setVisible(False)
        self._ai_progress.setRange(0, 0)
        layout.addWidget(self._ai_progress)

        self._ai_results = QtWidgets.QTreeWidget()
        self._ai_results.setHeaderLabels(["Severity", "Issue", "Suggestion"])
        self._ai_results.setRootIsDecorated(False)
        self._ai_results.setAlternatingRowColors(True)
        layout.addWidget(self._ai_results, 1)

        report_group = QtWidgets.QGroupBox("AI Report")
        report_layout = QtWidgets.QVBoxLayout(report_group)
        self._ai_report_log = QtWidgets.QPlainTextEdit()
        self._ai_report_log.setReadOnly(True)
        self._ai_report_log.setPlaceholderText("Audit log will appear here.")
        report_layout.addWidget(self._ai_report_log, 1)
        report_btn_row = QtWidgets.QHBoxLayout()
        self._ai_report_refresh = QtWidgets.QPushButton("Refresh Report")
        self._ai_report_clear = QtWidgets.QPushButton("Clear Report")
        report_btn_row.addWidget(self._ai_report_refresh)
        report_btn_row.addWidget(self._ai_report_clear)
        report_btn_row.addStretch(1)
        report_layout.addLayout(report_btn_row)
        layout.addWidget(report_group, 1)

        self._ai_analyze_btn.clicked.connect(self._on_ai_analyze)
        self._ai_optimize_btn.clicked.connect(self._on_ai_optimize_preview)
        self._ai_cam_btn.clicked.connect(self._on_ai_cam_analysis)
        self._ai_clear_btn.clicked.connect(self._on_ai_clear)
        self._ai_apply_btn.clicked.connect(self._on_ai_apply_optimization)
        self._ai_discard_btn.clicked.connect(self._on_ai_discard_preview)
        self._ai_save_btn.clicked.connect(self._on_ai_settings_save)
        self._ai_api_key_show.toggled.connect(self._on_ai_toggle_key_visibility)
        self._ai_chat_send.clicked.connect(self._on_ai_send)
        self._ai_chat_clear.clicked.connect(self._on_ai_clear_chat)
        self._ai_chat_input.returnPressed.connect(self._on_ai_send)
        self._ai_report_refresh.clicked.connect(self._on_ai_report_refresh)
        self._ai_report_clear.clicked.connect(self._on_ai_report_clear)

        self._load_ai_settings()
        self._load_ai_report()

    def _on_ai_clear(self):
        self._clear_ai_preview()
        self._ai_results.clear()
        self._ai_status.setText("Select geometry and click Analyze.")
        self._ai_last_optimization = None
        self._update_ai_action_state()

    def _on_ai_analyze(self):
        try:
            from ..ai.analysis import analyze_selection
        except ImportError:
            from ai.analysis import analyze_selection

        self._set_ai_busy(True, "Analyzing selection...")
        try:
            result = analyze_selection()
        except Exception as exc:
            self._ai_status.setText("Analysis failed.")
            _status_message(f"RouterKing AI analysis failed: {exc}\n", error=True)
            self._set_ai_busy(False)
            return

        self._render_ai_results(result)
        self._record_ai_report("Analyze Selection", result)
        self._set_ai_busy(False)

    def _on_ai_optimize_preview(self):
        try:
            from ..ai.optimization import optimize_selection
        except ImportError:
            from ai.optimization import optimize_selection

        self._clear_ai_preview()
        self._set_ai_busy(True, "Optimizing splines (preview)...")
        try:
            result = optimize_selection(create_preview=True)
        except Exception as exc:
            self._ai_status.setText("Optimization failed.")
            _status_message(f"RouterKing AI optimization failed: {exc}\n", error=True)
            self._set_ai_busy(False)
            return

        self._ai_preview_objects = result.preview_objects
        self._ai_last_optimization = result
        self._render_ai_results(result)
        self._record_ai_report("Preview Spline Optimization", result)
        self._set_ai_busy(False)
        self._update_ai_action_state()

    def _on_ai_cam_analysis(self):
        try:
            from ..ai.cam_analysis import analyze_gcode
        except ImportError:
            from ai.cam_analysis import analyze_gcode

        gcode_text = self._gcode_edit.toPlainText() if self._gcode_edit is not None else ""
        self._set_ai_busy(True, "Analyzing G-code...")
        try:
            result = analyze_gcode(gcode_text)
        except Exception as exc:
            self._ai_status.setText("CAM analysis failed.")
            _status_message(f"RouterKing CAM analysis failed: {exc}\n", error=True)
            self._set_ai_busy(False)
            return

        self._render_ai_results(result)
        self._record_ai_report("CAM Risk Check", result)
        self._set_ai_busy(False)

    def _on_ai_apply_optimization(self):
        try:
            from ..ai.optimization import create_optimized_object
        except ImportError:
            from ai.optimization import create_optimized_object

        result = self._ai_last_optimization
        if result is None or not result.optimized_targets:
            self._ai_status.setText("No optimization preview to apply.")
            return

        doc = App.ActiveDocument
        if doc is None:
            self._ai_status.setText("No active document.")
            return

        self._set_ai_busy(True, "Applying optimization...")
        applied = 0
        transaction_open = False
        try:
            doc.openTransaction("RouterKing Apply Spline Optimization")
            transaction_open = True
        except Exception:
            transaction_open = False

        try:
            for target in result.optimized_targets:
                optimized_obj = create_optimized_object(doc, target.label, target.shape)
                if optimized_obj is not None:
                    applied += 1
        except Exception as exc:
            self._ai_status.setText("Apply failed.")
            _status_message(f"RouterKing AI apply failed: {exc}\n", error=True)
            if transaction_open:
                try:
                    doc.abortTransaction()
                except Exception:
                    pass
            self._set_ai_busy(False)
            return

        if transaction_open:
            try:
                doc.commitTransaction()
            except Exception:
                pass
        try:
            doc.recompute()
        except Exception:
            pass

        self._ai_status.setText(f"Applied optimization to {applied} object(s).")
        self._record_ai_report("Apply Spline Optimization", result, details=f"applied={applied}")
        try:
            from ..ai.learning import record_feedback
        except ImportError:
            from ai.learning import record_feedback
        try:
            record_feedback("optimization.spline_preview", True, meta={"applied": applied})
        except Exception:
            pass
        self._clear_ai_preview()
        self._set_ai_busy(False)
        self._update_ai_action_state()

    def _on_ai_discard_preview(self):
        if self._ai_preview_objects:
            try:
                from ..ai.learning import record_feedback
            except ImportError:
                from ai.learning import record_feedback
            try:
                record_feedback(
                    "optimization.spline_preview",
                    False,
                    meta={"discarded": len(self._ai_preview_objects)},
                )
            except Exception:
                pass
        self._clear_ai_preview()
        self._ai_last_optimization = None
        self._ai_status.setText("Preview discarded.")
        self._update_ai_action_state()

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

    def _update_ai_action_state(self):
        has_preview = bool(self._ai_preview_objects)
        self._ai_apply_btn.setEnabled(has_preview and not self._ai_progress.isVisible())
        self._ai_discard_btn.setEnabled(has_preview and not self._ai_progress.isVisible())

    def _set_ai_busy(self, busy, message=None):
        self._ai_progress.setVisible(busy)
        if message:
            self._ai_status.setText(message)
        self._ai_analyze_btn.setEnabled(not busy)
        self._ai_optimize_btn.setEnabled(not busy)
        self._ai_cam_btn.setEnabled(not busy)
        self._ai_clear_btn.setEnabled(not busy)
        self._update_ai_action_state()
        QtWidgets.QApplication.processEvents()

    def _record_ai_report(self, action, result, details=None):
        try:
            from ..ai.reporting import append_report, format_report_entry, load_report
        except ImportError:
            from ai.reporting import append_report, format_report_entry, load_report

        try:
            entry = format_report_entry(action, result, details=details)
            append_report(entry)
            self._ai_report_log.setPlainText(load_report())
        except Exception as exc:
            _status_message(f"RouterKing AI report failed: {exc}\n", error=True)

    def _load_ai_report(self):
        try:
            from ..ai.reporting import load_report
        except ImportError:
            from ai.reporting import load_report

        try:
            self._ai_report_log.setPlainText(load_report())
        except Exception:
            pass

    def _on_ai_report_refresh(self):
        self._load_ai_report()

    def _on_ai_report_clear(self):
        try:
            from ..ai.reporting import clear_report
        except ImportError:
            from ai.reporting import clear_report

        try:
            clear_report()
            self._ai_report_log.clear()
        except Exception as exc:
            _status_message(f"RouterKing AI report clear failed: {exc}\n", error=True)

    def _render_ai_results(self, result):
        self._ai_results.clear()
        issues = list(getattr(result, "issues", []) or [])
        try:
            from ..ai.learning import apply_issue_weights
        except ImportError:
            from ai.learning import apply_issue_weights
        try:
            issues = apply_issue_weights(issues)
        except Exception:
            pass
        for issue in issues:
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
        self._ai_allow_actions.setChecked(bool(provider.get("allow_actions", False)))
        self._ai_system_prompt = chat.get(
            "system_prompt",
            "You are RouterKing AI, a helpful assistant for FreeCAD CNC workflows.",
        )
        self._ai_temperature = float(chat.get("temperature", 0.2))
        self._ai_max_output_tokens = int(chat.get("max_output_tokens", 512))
        self._refresh_ai_models()

    def _set_ai_settings_status(self, message=None):
        if message:
            self._ai_settings_status.setText(f"{message}\n{_AI_SETTINGS_HELP_TEXT}")
        else:
            self._ai_settings_status.setText(_AI_SETTINGS_HELP_TEXT)

    def _refresh_ai_models(self, force=False):
        if self._ai_models_loading:
            return
        api_key = self._ai_api_key.text().strip()
        if not api_key:
            if force:
                self._set_ai_settings_status("API key required to load models.")
            return
        base_url = self._ai_base_url.text().strip() or "https://api.openai.com/v1"
        self._ai_models_loading = True
        self._set_ai_settings_status("Loading models...")

        self._ai_model_worker_thread = QtCore.QThread(self)
        self._ai_model_worker = _AiModelListWorker(api_key, base_url)
        self._ai_model_worker.moveToThread(self._ai_model_worker_thread)
        self._ai_model_worker_thread.started.connect(self._ai_model_worker.run)
        self._ai_model_worker.finished.connect(self._on_ai_models_ready)
        self._ai_model_worker.finished.connect(self._ai_model_worker_thread.quit)
        self._ai_model_worker_thread.finished.connect(self._ai_model_worker.deleteLater)
        self._ai_model_worker_thread.finished.connect(self._ai_model_worker_thread.deleteLater)
        self._ai_model_worker_thread.start()

    def _on_ai_models_ready(self, model_ids, error):
        self._ai_models_loading = False
        if error:
            self._set_ai_settings_status("Model list unavailable; using cached/default.")
            _status_message(f"RouterKing AI model list failed: {error}\n", error=True)
            return

        models = self._select_ai_models(model_ids)
        if not models:
            self._set_ai_settings_status("Model list empty; using cached/default.")
            return

        self._apply_ai_model_items(models)
        self._set_ai_settings_status(f"Loaded {len(models)} models.")

    def _apply_ai_model_items(self, models):
        try:
            from ..ai.pricing import format_model_with_cost
        except ImportError:
            from ai.pricing import format_model_with_cost
        
        current_text = self._ai_model.currentText().strip()
        current_model = self._strip_ai_model_cost(current_text)
        
        self._ai_model.blockSignals(True)
        self._ai_model.clear()
        
        # Add models with cost indicators
        formatted_models = [format_model_with_cost(m) for m in models]
        self._ai_model.addItems(formatted_models)
        
        if current_model:
            # Try to find the model (with or without cost indicator)
            index = -1
            for i, formatted in enumerate(formatted_models):
                if current_model in formatted or formatted.startswith(current_model + " "):
                    index = i
                    break
            
            if index != -1:
                self._ai_model.setCurrentIndex(index)
            else:
                # Insert the original selection if not found
                self._ai_model.insertItem(0, current_text)
                self._ai_model.setCurrentIndex(0)
        self._ai_model.blockSignals(False)

    def _select_ai_models(self, model_ids):
        if not model_ids:
            return []
        normalized = [m.strip() for m in model_ids if isinstance(m, str)]
        normalized = [m for m in normalized if m]
        candidates = sorted(set(m for m in normalized if self._is_ai_chat_model(m)))
        if not candidates:
            return []
        selected = [model for model in _AI_MODEL_SHORTLIST if model in candidates]
        remaining = [model for model in candidates if model not in selected]

        families = {}
        for model_id in remaining:
            family = self._ai_model_family(model_id)
            families.setdefault(family, []).append(model_id)
        best_per_family = []
        for family_models in families.values():
            best = sorted(family_models, key=self._ai_model_rank_key)[0]
            if best not in selected:
                best_per_family.append(best)
        best_per_family.sort(key=self._ai_model_display_sort_key)

        merged = selected + best_per_family
        max_models = max(len(selected), 12)
        return merged[:max_models]

    def _is_ai_chat_model(self, model_id):
        lowered = model_id.lower()
        # Exclude fine-tuned models
        if lowered.startswith("ft:") or ":ft-" in lowered:
            return False
        # Include all GPT models and o-series reasoning models (o1, o3, o4, etc.)
        if not (lowered.startswith("gpt-") or re.match(r"^o\d", lowered)):
            return False
        # Exclude specialized models (audio, vision, embeddings, etc.)
        for token in _AI_MODEL_EXCLUDE_SUBSTRINGS:
            if token in lowered:
                return False
        return True

    def _ai_model_family(self, model_id):
        return re.sub(r"-(\d{4}-\d{2}-\d{2}|\d{8})$", "", model_id)

    def _ai_model_date_key(self, model_id):
        match = re.search(r"-(\d{4}-\d{2}-\d{2}|\d{8})$", model_id)
        if not match:
            return None
        digits = match.group(1).replace("-", "")
        try:
            return int(digits)
        except ValueError:
            return None

    def _ai_model_rank_key(self, model_id):
        lowered = model_id.lower()
        penalty = 0
        if "preview" in lowered or "beta" in lowered or "test" in lowered:
            penalty += 1
        date_value = self._ai_model_date_key(model_id)
        if date_value is None:
            date_value = 99999999
        return (penalty, -date_value, len(model_id), model_id)

    def _ai_model_display_sort_key(self, model_id):
        lowered = model_id.lower()
        rank = len(_AI_MODEL_PREFIX_ORDER)
        for idx, prefix in enumerate(_AI_MODEL_PREFIX_ORDER):
            if lowered.startswith(prefix):
                rank = idx
                break
        return (rank, len(model_id), model_id)

    def _on_ai_settings_save(self):
        params = App.ParamGet("User parameter:BaseApp/Preferences/RouterKing/AI")
        params.SetString("provider", self._ai_provider.currentText())
        params.SetString("openai_api_key", self._ai_api_key.text().strip())
        params.SetString("openai_base_url", self._ai_base_url.text().strip())
        
        model_text = self._ai_model.currentText().strip()
        model_name = self._strip_ai_model_cost(model_text)
        params.SetString("openai_model", model_name)
        
        params.SetString("openai_reasoning_effort", self._ai_reasoning.currentText().strip())
        params.SetBool("allow_actions", self._ai_allow_actions.isChecked())
        self._set_ai_settings_status("Saved to FreeCAD preferences.")
        _status_message("RouterKing AI settings saved.\n")
        self._refresh_ai_models(force=True)

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
        model = self._strip_ai_model_cost(self._ai_model.currentText().strip())
        reasoning = self._ai_reasoning.currentText().strip()
        allow_actions = self._ai_allow_actions.isChecked()
        context_payload = None
        context_summary = ""
        try:
            from ..ai.assistant import collect_assistant_context, summarize_context
        except ImportError:
            from ai.assistant import collect_assistant_context, summarize_context
        try:
            context_payload = collect_assistant_context()
            context_summary = summarize_context(context_payload)
        except Exception:
            context_payload = None
            context_summary = ""

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
            allow_actions,
            context_payload=context_payload,
            context_summary=context_summary,
        )
        self._ai_worker.moveToThread(self._ai_worker_thread)
        self._ai_worker_thread.started.connect(self._ai_worker.run)
        self._ai_worker.finished.connect(self._on_ai_chat_finished)
        self._ai_worker.finished.connect(self._ai_worker_thread.quit)
        self._ai_worker_thread.finished.connect(self._ai_worker.deleteLater)
        self._ai_worker_thread.finished.connect(self._ai_worker_thread.deleteLater)
        self._ai_worker_thread.start()

    @staticmethod
    def _strip_ai_model_cost(text):
        return re.sub(r"\s*\([$$]+\)\s*$", "", text or "").strip()

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
            self._apply_disconnected_state("Disconnected.", unexpected=False)
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

        connected = self._sender.is_connected()
        if connected:
            self._status_tick += 1
            if self._status_tick >= 10:
                self._request_status()
                self._status_tick = 0
        elif self._sender_was_connected:
            reason = self._sender.get_disconnect_reason() or "Serial connection lost."
            self._apply_disconnected_state(reason, unexpected=True)
            return

        status = self._sender.get_status()
        if status:
            self._update_controller_guard_position(status)
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
        self._sender_was_connected = connected

    def _append_console(self, text, force=False):
        if not force and self._console_verbose is not None and not self._console_verbose.isChecked():
            if text == self._last_console_line:
                return
        self._console.appendPlainText(text)
        self._last_console_line = text

    def _record_mcp_action_event(self, event, action_type, message="", errors=None):
        errors = list(errors or [])
        label = {
            "start": "running",
            "success": "ok",
            "error": "error",
        }.get(str(event), str(event))
        line = f"MCP {label}: {action_type}"
        if message:
            line += f" - {message}"
        if errors:
            line += f" - {'; '.join(str(error) for error in errors)}"
        status = getattr(self, "_mcp_status", None)
        if status is not None:
            status.setText(line)
        log = getattr(self, "_mcp_log", None)
        if log is not None:
            log.appendPlainText(line)
        self._append_console(line, force=True)
        if str(action_type).startswith("machine_"):
            self._sync_shared_sender_ui(action_type=action_type, event=event)

    def _sync_shared_sender_ui(self, *, action_type="", event=""):
        connected = self._sender.is_connected()
        if connected:
            port = self._sender_port_label()
            if port:
                self._connection_status.setText(f"Connection: connected ({port})")
            else:
                self._connection_status.setText("Connection: connected")
            self._connect_btn.setText("Disconnect")
            self._port.setEnabled(False)
            self._sender_was_connected = True
            if getattr(self, "_poll_timer", None) is not None:
                try:
                    active = self._poll_timer.isActive()
                except Exception:
                    active = False
                if not active:
                    self._poll_timer.start()
            try:
                self._drain_sender()
            except Exception:
                pass
        elif action_type == "machine_disconnect" and event == "success":
            self._apply_disconnected_state("MCP disconnected.", unexpected=False)
            return
        self._update_job_controls()
        self._update_machine_controls()

    def _sender_port_label(self):
        serial_obj = getattr(self._sender, "_serial", None)
        for attr in ("port", "portstr", "name"):
            value = getattr(serial_obj, attr, None)
            if value:
                return str(value)
        return ""

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

    def _reset_explore_state(self):
        self._explore_active = False
        self._explore_phase = None
        self._explore_axis_queue = []
        self._explore_axis = None
        self._explore_distance = 0.0
        self._explore_pending = False
        self._explore_next_action = 0.0
        self._explore_results = {}
        self._explore_unlock_sent_at = None
        self._explore_unlocked = False
        self._explore_last_command_at = None
        self._explore_recover_attempts = 0
        self._explore_dir_override = {"X": None, "Y": None, "Z": None}
        self._explore_retry_axes.clear()
        self._explore_retry_axis = None
        self._explore_known_limits = {}
        self._explore_retry_measurements = {}
        self._explore_ramp_remaining = 0.0
        self._explore_ramp_feed = 0.0
        self._explore_ramp_increment_current = 0.0
        self._explore_ramp_max_feed_axis = 0.0
        self._explore_ramp_last_step = 0.0
        self._explore_preflight_sent = False
        self._explore_preflight_started_at = 0.0

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
        self._sender_was_connected = True
        self._connect_btn.setText("Disconnect")
        self._port.setEnabled(False)
        self._append_console("Connected.")
        self._poll_timer.start()
        self._request_status()
        self._update_job_controls()
        self._update_machine_controls()
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
            self._reset_explore_state()
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
        kwargs = {"x": 0.0, "y": 0.0, "z": 0.0}
        kwargs[axis.lower()] = value
        self._send_jog(feed=feed, source="Jog", **kwargs)

    def _send_jog(self, x=0.0, y=0.0, z=0.0, feed=300.0, source="Jog", log=True):
        allowed, reason = self._can_jog()
        if not allowed:
            if log:
                self._append_console(f"{source} blocked: {reason}", force=True)
            return False
        x, y, z, limit_reason = self._limit_jog_delta(x, y, z)
        if limit_reason:
            if log:
                self._append_console(f"{source} limited: {limit_reason}", force=True)
            else:
                status = getattr(self, "_controller_status", None)
                if status is not None:
                    prefix = "Manual XYZ" if getattr(self, "_controller_manual_xyz_active", False) else "Controller"
                    status.setText(f"{prefix}: limited - {limit_reason}")
            if abs(float(x)) < 0.0005 and abs(float(y)) < 0.0005 and abs(float(z)) < 0.0005:
                return False
        parts = []
        if abs(float(x)) >= 0.0005:
            parts.append(f"X{float(x):.3f}")
        if abs(float(y)) >= 0.0005:
            parts.append(f"Y{float(y):.3f}")
        if abs(float(z)) >= 0.0005:
            parts.append(f"Z{float(z):.3f}")
        if not parts:
            return False
        command = "$J=G91 " + " ".join(parts) + f" F{float(feed):.0f}"
        self._send_command(command, log=log)
        self._advance_controller_guard_position(x=x, y=y, z=z)
        return True

    def _can_jog(self):
        if not self._sender.is_connected():
            return False, "not connected"
        if self._sender.is_streaming():
            return False, "sender busy"
        if self._explore_active:
            return False, "limit explore active"
        state = self._machine_state()
        if state in (None, "", "idle", "jog"):
            return True, ""
        return False, f"machine state is {state}"

    def _limit_jog_delta(self, x=0.0, y=0.0, z=0.0):
        requested = {"x": float(x), "y": float(y), "z": float(z)}
        limits = self._machine_limits_for_jog()
        if not limits:
            self._request_status_for_jog()
            return 0.0, 0.0, 0.0, "machine limits unknown"
        position = self._machine_position_for_jog()
        if not position:
            self._request_status_for_jog()
            return 0.0, 0.0, 0.0, "machine position unknown"

        adjusted = dict(requested)
        limited_axes = []
        for axis in ("x", "y", "z"):
            delta = requested[axis]
            if abs(delta) < 0.0005:
                continue
            axis_limits = limits.get(axis)
            current = position.get(axis)
            if axis_limits is None or current is None:
                adjusted[axis] = 0.0
                limited_axes.append(axis.upper())
                continue
            min_limit, max_limit = axis_limits
            margin = _CONTROLLER_LIMIT_MARGIN_MM
            guarded_min = min_limit + margin
            guarded_max = max_limit - margin
            if guarded_min < guarded_max:
                min_limit = guarded_min
                max_limit = guarded_max
            target = current + delta
            if target < min_limit:
                allowed_delta = min_limit - current
                adjusted[axis] = allowed_delta if delta < 0.0 and allowed_delta < 0.0 else 0.0
                limited_axes.append(axis.upper())
            elif target > max_limit:
                allowed_delta = max_limit - current
                adjusted[axis] = allowed_delta if delta > 0.0 and allowed_delta > 0.0 else 0.0
                limited_axes.append(axis.upper())

        reason = ""
        if limited_axes:
            reason = " ".join(sorted(set(limited_axes))) + " machine limit"
        return adjusted["x"], adjusted["y"], adjusted["z"], reason

    def _machine_limits_for_jog(self):
        values = {}
        for axis in ("X", "Y", "Z"):
            value = getattr(self, "_limits", {}).get(axis)
            if value is not None:
                try:
                    travel = abs(float(value))
                except (TypeError, ValueError):
                    travel = 0.0
                if travel > 0.0:
                    values[axis.lower()] = (-travel, 0.0)
        if len(values) == 3:
            return values
        try:
            profile, _profile_path = grbl_load_machine_profile(None)
            settings = dict((profile or {}).get("settings") or {})
            limits, _source = grbl_resolve_machine_limits(profile, settings)
            return {
                axis: (float(axis_limits[0]), float(axis_limits[1]))
                for axis, axis_limits in limits.items()
                if axis_limits and len(axis_limits) >= 2
            }
        except Exception:
            return values if len(values) == 3 else None

    def _machine_position_for_jog(self):
        guard_position = getattr(self, "_controller_guard_mpos", None)
        if guard_position:
            return dict(guard_position)
        status = self._sender.get_status() or {}
        position = grbl_parse_xyz_value(status.get("MPos"))
        if position is None:
            return None
        position = {axis: float(position[axis]) for axis in ("x", "y", "z")}
        self._controller_guard_mpos = dict(position)
        self._controller_guard_mpos_at = time.time()
        return position

    def _update_controller_guard_position(self, status):
        position = grbl_parse_xyz_value((status or {}).get("MPos"))
        if position is None:
            return
        self._controller_guard_mpos = {axis: float(position[axis]) for axis in ("x", "y", "z")}
        self._controller_guard_mpos_at = time.time()

    def _advance_controller_guard_position(self, x=0.0, y=0.0, z=0.0):
        position = getattr(self, "_controller_guard_mpos", None)
        if not position:
            return
        updated = dict(position)
        for axis, delta in (("x", x), ("y", y), ("z", z)):
            updated[axis] = float(updated.get(axis, 0.0)) + float(delta)
        self._controller_guard_mpos = updated
        self._controller_guard_mpos_at = time.time()

    def _request_status_for_jog(self):
        try:
            self._request_status()
        except Exception:
            pass

    def _can_prepare_manual_xyz(self):
        if not self._sender.is_connected():
            return False, "not connected"
        if self._sender.is_streaming():
            return False, "sender busy"
        if self._explore_active:
            return False, "limit explore active"
        state = self._machine_state()
        if state in (None, "", "idle"):
            return True, ""
        return False, f"machine state is {state}"

    def _on_prepare_manual_xyz(self):
        allowed, reason = self._can_prepare_manual_xyz()
        if not allowed:
            self._append_console(f"Manual XYZ blocked: {reason}", force=True)
            _controller_log(f"manual xyz blocked: {reason}")
            return
        self._controller_manual_xyz_active = True
        self._append_console(
            "Manual XYZ ready: no automatic move sent. "
            "Controller jog is guarded by homed machine limits.",
            force=True,
        )
        status = self._sender.get_status() or {}
        self._update_controller_guard_position(status)
        _controller_log(f"manual xyz prepared: no automatic move; mpos={status.get('MPos', 'unknown')}")
        if self._controller.is_connected():
            self._controller_enable.setChecked(True)
            self._controller_timer.start()
        else:
            self._append_console("Manual XYZ ready, but no controller is connected.", force=True)
        self._request_status()
        self._update_machine_controls()

    def _on_exit_manual_xyz(self):
        self._controller_manual_xyz_active = False
        if self._controller_enable.isChecked():
            self._controller_enable.setChecked(False)
        else:
            self._controller_stop()
            self._update_machine_controls()
        self._append_console("Manual XYZ mode stopped.", force=True)

    def _send_checked_command(self, command, timeout=5.0):
        try:
            if hasattr(self._sender, "send_and_collect"):
                self._append_console(f"> {command}")
                lines = self._sender.send_and_collect(command, timeout=timeout)
                error = next(
                    (
                        str(line).strip()
                        for line in lines
                        if str(line).strip().lower().startswith(("error", "alarm"))
                    ),
                    "",
                )
                if error:
                    self._append_console(f"Manual XYZ failed: {error}", force=True)
                    return False
            else:
                self._send_command(command)
        except Exception as exc:
            self._append_console(f"Manual XYZ failed while sending {command}: {exc}", force=True)
            _status_message(f"RouterKing Manual XYZ failed ({exc})\n", error=True)
            return False
        return True

    def _on_controller_connect(self):
        if self._controller.is_connected():
            self._controller_stop()
            name = self._controller.name()
            self._controller.disconnect()
            self._controller_manual_xyz_active = False
            self._controller_status.setText("Controller: disconnected")
            self._controller_connect_btn.setText("Connect Controller")
            _controller_log(f"disconnected: {name or 'controller'}")
            self._update_machine_controls()
            return
        if not self._controller.is_available():
            self._controller_status.setText("Controller: pygame missing")
            self._append_console(
                "Controller unavailable: install pygame into FreeCAD's Python environment.",
                force=True,
            )
            _controller_log(f"unavailable: {self._controller.error or 'pygame missing'}")
            return
        if not self._controller.connect():
            self._controller_status.setText(f"Controller: {self._controller.error or 'not found'}")
            _controller_log(f"connect failed: {self._controller.error or 'not found'}")
            return
        self._controller_status.setText(f"Controller: {self._controller.name()}")
        self._controller_connect_btn.setText("Disconnect Controller")
        _controller_log(f"connected: {self._controller.name()}")
        if self._controller_enable.isChecked():
            self._controller_timer.start()
        self._update_machine_controls()

    def _on_controller_test(self):
        if self._controller_enable.isChecked():
            self._controller_enable.setChecked(False)
        else:
            self._controller_stop()
        existing = getattr(self, "_controller_test_dialog", None)
        if existing is not None and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            return
        gamepad = self._controller if self._controller.is_connected() else PygameGamepad()
        dialog = ControllerTestDialog(gamepad, self)
        self._controller_test_dialog = dialog
        _controller_log("test dialog opened")
        try:
            dialog.finished.connect(lambda _result, dlg=dialog: self._on_controller_test_closed(dlg))
        except Exception:
            pass
        dialog.show()

    def _on_controller_test_closed(self, dialog):
        if getattr(self, "_controller_test_dialog", None) is dialog:
            self._controller_test_dialog = None
        if self._controller.is_connected():
            self._controller_status.setText(f"Controller: {self._controller.name()}")
            self._controller_connect_btn.setText("Disconnect Controller")
        self._update_machine_controls()

    def _on_learn_controller_binding(self, key, label):
        if self._controller_enable.isChecked():
            self._controller_enable.setChecked(False)
        else:
            self._controller_stop()
        existing = getattr(self, "_controller_binding_capture_dialog", None)
        if existing is not None and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            return
        gamepad = self._controller if self._controller.is_connected() else PygameGamepad()
        dialog = ControllerBindingCaptureDialog(
            gamepad,
            label,
            lambda token, k=key: self._append_controller_binding_token(k, token),
            self,
        )
        self._controller_binding_capture_dialog = dialog
        try:
            dialog.finished.connect(lambda _result, dlg=dialog: self._on_controller_binding_capture_closed(dlg))
        except Exception:
            pass
        dialog.show()

    def _on_controller_binding_capture_closed(self, dialog):
        if getattr(self, "_controller_binding_capture_dialog", None) is dialog:
            self._controller_binding_capture_dialog = None
        if self._controller.is_connected():
            self._controller_status.setText(f"Controller: {self._controller.name()}")
            self._controller_connect_btn.setText("Disconnect Controller")
        self._update_machine_controls()

    def _append_controller_binding_token(self, key, token):
        edit = getattr(self, "_controller_binding_edits", {}).get(key)
        if edit is None:
            return
        existing = [part.strip() for part in edit.text().split(",") if part.strip()]
        if token not in existing:
            existing.append(token)
        edit.setText(", ".join(existing))
        self._save_controller_defaults()

    def _on_controller_enabled_changed(self, _checked):
        self._save_controller_defaults()
        if self._controller_enable.isChecked() and self._controller.is_connected():
            self._controller_timer.start()
        else:
            self._controller_manual_xyz_active = False
            self._controller_stop()
        self._update_machine_controls()

    def _controller_tick(self):
        if not self._controller_enable.isChecked() or not self._controller.is_connected():
            self._controller_stop()
            return
        state = self._controller.poll_mapped(self._controller_binding_strings())
        if state is None:
            self._controller_stop()
            self._controller_status.setText(f"Controller: {self._controller.error or 'disconnected'}")
            self._controller_connect_btn.setText("Connect Controller")
            self._update_machine_controls()
            return
        speed_label = getattr(state, "speed_label", "slow")
        speed_multiplier = max(1.0, float(getattr(state, "speed_multiplier", 1.0) or 1.0))
        feed = min(5000.0, float(self._controller_feed.value()) * speed_multiplier)
        if speed_label == "fast":
            x, y, z = make_fast_xy_jog_vector(
                state,
                deadzone=self._controller_deadzone.value(),
                xy_feed=feed,
                lookahead_s=_CONTROLLER_FAST_LOOKAHEAD_S,
                z_step=self._controller_z_step.value(),
            )
            interval = _CONTROLLER_FAST_INTERVAL_S
        else:
            x, y, z = make_jog_vector(
                state,
                deadzone=self._controller_deadzone.value(),
                xy_step=self._controller_xy_step.value(),
                z_step=self._controller_z_step.value(),
            )
            interval = _CONTROLLER_STEP_INTERVAL_S
        if x == 0.0 and y == 0.0 and z == 0.0:
            if self._controller_was_active:
                self._controller_cancel_jog()
            self._controller_was_active = False
            return
        now = time.time()
        if now - self._controller_last_jog_at < interval:
            return
        if self._send_jog(x=x, y=y, z=z, feed=feed, source="Controller", log=False):
            self._controller_last_jog_at = now
            self._controller_was_active = True
            prefix = "Manual XYZ" if self._controller_manual_xyz_active else "Controller"
            self._controller_status.setText(
                f"{prefix}: {state.name} [{speed_label}] | X{x:+.3f} Y{y:+.3f} Z{z:+.3f}"
            )
        elif self._controller_was_active:
            self._controller_cancel_jog()
            self._controller_was_active = False

    def _controller_binding_strings(self):
        edits = getattr(self, "_controller_binding_edits", {})
        bindings = {}
        for key, default_value in DEFAULT_CONTROLLER_BINDINGS.items():
            edit = edits.get(key)
            bindings[key] = str(edit.text()).strip() if edit is not None else str(default_value)
        return bindings

    def _controller_stop(self):
        if getattr(self, "_controller_timer", None) is not None:
            self._controller_timer.stop()
        if getattr(self, "_controller_was_active", False):
            self._controller_cancel_jog()
        self._controller_was_active = False

    def _controller_cancel_jog(self):
        try:
            if hasattr(self._sender, "cancel_jog"):
                self._sender.cancel_jog()
            else:
                self._sender.send_realtime_command(b"\x85")
        except Exception:
            pass

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

    def _on_insert_gcode_template(self):
        if self._gcode_edit.toPlainText().strip() and not self._confirm_replace_gcode():
            return
        self._clear_template_fit_selection()
        spec = self._read_rectangle_template_controls()
        if spec is None:
            spec = self._show_rectangle_template_dialog()
        if spec is None:
            return
        try:
            program = rectangle_pocket(spec)
        except ValueError as exc:
            self._append_console(f"Template failed: {exc}", force=True)
            return
        self._last_template_spec = spec
        self._gcode_edit.setPlainText(program.gcode + "\n")
        self._append_console(
            "Inserted template: "
            f"{spec.name or 'rectangle pocket'} "
            f"{spec.width:g} x {spec.height:g} x {spec.depth:g} mm.",
            force=True,
        )
        self._populate_rectangle_template_controls(spec)
        self._update_preview()
        self._update_job_controls()

    def _read_rectangle_template_controls(self):
        controls = getattr(self, "_template_controls", None)
        if not controls:
            return None
        source = self._selected_template_source()
        previous = getattr(self, "_last_template_spec", None)
        cut_start_x = previous.cut_start_x if previous is not None else None
        cut_start_y = previous.cut_start_y if previous is not None else None
        return TemplateSpec(
            name=controls["name"].text().strip() or None,
            width=controls["width"].value(),
            height=controls["height"].value(),
            depth=controls["depth"].value(),
            tool_diameter=controls["tool_diameter"].value(),
            step_down=controls["step_down"].value(),
            step_over=controls["step_over"].value(),
            feed_rate=controls["feed_rate"].value(),
            plunge_rate=controls["plunge_rate"].value(),
            safe_z=controls["safe_z"].value(),
            start_z=controls["start_z"].value(),
            origin=controls["origin"].currentText(),
            start_x=controls["start_x"].value(),
            start_y=controls["start_y"].value(),
            swap_xy=controls["swap_xy"].isChecked(),
            pass_axis=controls["pass_axis"].currentText(),
            path_direction=controls["path_direction"].currentText(),
            final_contour=controls["final_contour"].isChecked(),
            contour_direction=controls["contour_direction"].currentText(),
            cut_start_x=cut_start_x,
            cut_start_y=cut_start_y,
            source_document=source.get("document"),
            source_object=source.get("object"),
            source_feature=source.get("feature"),
        )

    def _populate_rectangle_template_controls(self, spec):
        controls = getattr(self, "_template_controls", None)
        if not controls:
            return
        controls["name"].setText(spec.name or "")
        for key in (
            "width",
            "height",
            "depth",
            "tool_diameter",
            "step_down",
            "step_over",
            "feed_rate",
            "plunge_rate",
            "safe_z",
            "start_z",
            "start_x",
            "start_y",
        ):
            controls[key].setValue(float(getattr(spec, key)))
        controls["origin"].setCurrentText(spec.origin)
        controls["swap_xy"].setChecked(bool(spec.swap_xy))
        controls["pass_axis"].setCurrentText(spec.pass_axis)
        controls["path_direction"].setCurrentText(spec.path_direction)
        controls["final_contour"].setChecked(bool(spec.final_contour))
        controls["contour_direction"].setCurrentText(spec.contour_direction)
        self._select_template_source(spec)

    def _on_reset_rectangle_template_controls(self):
        spec = self._default_rectangle_template_spec()
        spec = replace(
            spec,
            cut_start_x=None,
            cut_start_y=None,
            source_document=None,
            source_object=None,
            source_feature=None,
        )
        self._populate_rectangle_template_controls(spec)
        self._last_template_spec = spec
        self._append_console("Rectangle template parameters reset to Tee-Tablett defaults.", force=True)
        self._clear_template_fit_selection()
        self._update_preview()

    def _show_rectangle_template_dialog(self):
        default = self._default_rectangle_template_spec()
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Rectangle Pocket Template")
        layout = QtWidgets.QVBoxLayout(dialog)

        form = QtWidgets.QFormLayout()
        name_edit = QtWidgets.QLineEdit(default.name or "")
        form.addRow("Name", name_edit)

        width = self._template_spin(default.width, 0.001, 10000.0)
        height = self._template_spin(default.height, 0.001, 10000.0)
        depth = self._template_spin(default.depth, 0.001, 1000.0)
        tool_diameter = self._template_spin(default.tool_diameter, 0.001, 1000.0)
        step_down = self._template_spin(default.step_down, 0.001, 1000.0)
        step_over = self._template_spin(default.step_over, 0.001, 1000.0)
        feed_rate = self._template_spin(default.feed_rate, 0.001, 50000.0, decimals=1)
        plunge_rate = self._template_spin(default.plunge_rate, 0.001, 50000.0, decimals=1)
        safe_z = self._template_spin(default.safe_z, -1000.0, 1000.0)
        start_z = self._template_spin(default.start_z, -1000.0, 1000.0)
        start_x = self._template_spin(default.start_x, -10000.0, 10000.0)
        start_y = self._template_spin(default.start_y, -10000.0, 10000.0)
        origin = QtWidgets.QComboBox()
        origin.addItems(["center", "lower_left"])
        origin.setCurrentText(default.origin)
        swap_xy = QtWidgets.QCheckBox("Swap X/Y machining direction")
        swap_xy.setChecked(bool(default.swap_xy))

        form.addRow("Width (mm)", width)
        form.addRow("Length (mm)", height)
        form.addRow("Depth (mm)", depth)
        form.addRow("Cutter diameter (mm)", tool_diameter)
        form.addRow("Step down (mm)", step_down)
        form.addRow("Step over (mm)", step_over)
        form.addRow("Feed rate (mm/min)", feed_rate)
        form.addRow("Plunge rate (mm/min)", plunge_rate)
        form.addRow("Safe Z (mm)", safe_z)
        form.addRow("Start Z (mm)", start_z)
        form.addRow("Start X (mm)", start_x)
        form.addRow("Start Y (mm)", start_y)
        form.addRow("Origin", origin)
        form.addRow(swap_xy)
        layout.addLayout(form)

        buttons = QtWidgets.QHBoxLayout()
        cancel_btn = QtWidgets.QPushButton("Cancel")
        generate_btn = QtWidgets.QPushButton("Generate")
        buttons.addStretch(1)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(generate_btn)
        layout.addLayout(buttons)
        cancel_btn.clicked.connect(dialog.reject)
        generate_btn.clicked.connect(dialog.accept)

        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return None

        return TemplateSpec(
            name=name_edit.text().strip() or None,
            width=width.value(),
            height=height.value(),
            depth=depth.value(),
            tool_diameter=tool_diameter.value(),
            step_down=step_down.value(),
            step_over=step_over.value(),
            feed_rate=feed_rate.value(),
            plunge_rate=plunge_rate.value(),
            safe_z=safe_z.value(),
            start_z=start_z.value(),
            origin=origin.currentText(),
            start_x=start_x.value(),
            start_y=start_y.value(),
            swap_xy=swap_xy.isChecked(),
            cut_start_x=default.cut_start_x,
            cut_start_y=default.cut_start_y,
        )

    def _default_rectangle_template_spec(self):
        if self._last_template_spec is not None:
            return replace(self._last_template_spec)
        safe_z = max(self._manual_start_safe_z(), 6.0)
        return rectangle_pocket_preset("tee_tablett", safe_z=safe_z)

    def _refresh_template_cad_sources(self):
        combo = getattr(self, "_template_source_combo", None)
        if combo is None:
            return
        current = self._selected_template_source()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Manual / no CAD source", {})
        for source in self._template_cad_sources():
            combo.addItem(source["label"], source)
        combo.blockSignals(False)
        self._select_template_source_data(current)
        self._update_template_source_summary()
        self._update_template_cad_tool_summary()

    def _template_cad_sources(self):
        document = getattr(App, "ActiveDocument", None)
        if document is None:
            return []
        document_name = getattr(document, "Label", "") or getattr(document, "Name", "") or "ActiveDocument"
        objects = list(getattr(document, "Objects", []) or [])
        sources = []
        seen = set()
        for obj in objects:
            object_name = getattr(obj, "Name", "") or getattr(obj, "Label", "")
            if not object_name:
                continue
            label = getattr(obj, "Label", "") or object_name
            type_id = getattr(obj, "TypeId", "")
            key = (document_name, object_name)
            if key in seen:
                continue
            seen.add(key)
            display = f"{document_name}: {object_name}"
            if label != object_name:
                display += f" ({label})"
            if type_id:
                display += f" - {type_id}"
            sources.append({
                "label": display,
                "document": document_name,
                "object": object_name,
                "feature": label if label != object_name else None,
            })
        return sources

    def _selected_template_source(self):
        combo = getattr(self, "_template_source_combo", None)
        if combo is None:
            return {}
        try:
            data = combo.itemData(combo.currentIndex())
        except Exception:
            data = None
        return data if isinstance(data, dict) else {}

    def _select_template_source(self, spec):
        target = {
            "document": spec.source_document,
            "object": spec.source_object,
            "feature": spec.source_feature,
        }
        self._select_template_source_data(target)
        self._update_template_source_summary()

    def _select_template_source_data(self, target):
        combo = getattr(self, "_template_source_combo", None)
        if combo is None:
            return
        target = target or {}
        for index in range(combo.count()):
            data = combo.itemData(index)
            if not isinstance(data, dict):
                continue
            if (
                data.get("document") == target.get("document")
                and data.get("object") == target.get("object")
                and data.get("feature") == target.get("feature")
            ):
                combo.setCurrentIndex(index)
                return
        combo.setCurrentIndex(0)

    def _update_template_source_summary(self, *_args):
        label = getattr(self, "_template_source_summary", None)
        if label is None:
            return
        source = self._selected_template_source()
        if not source:
            label.setText("G-code header: no CAD source")
            return
        parts = [source.get("document"), source.get("object"), source.get("feature")]
        label.setText("G-code header: " + " / ".join(part for part in parts if part))

    def _update_template_cad_tool_summary(self):
        label = getattr(self, "_template_cad_tool_summary", None)
        if label is None:
            return
        tool = self._active_cad_tool_values()
        if not tool:
            label.setText("CAD tool: none detected")
            return
        parts = [tool.get("label") or tool.get("name") or "tool"]
        if tool.get("diameter") is not None:
            parts.append(f"diameter {tool['diameter']:g} mm")
        if tool.get("shank_diameter") is not None:
            parts.append(f"shank {tool['shank_diameter']:g} mm")
        if tool.get("horiz_feed") is not None:
            parts.append(f"CAD feed {tool['horiz_feed']:g}")
        if tool.get("vert_feed") is not None:
            parts.append(f"CAD plunge {tool['vert_feed']:g}")
        label.setText("CAD tool: " + ", ".join(parts))

    def _active_cad_tool_values(self):
        document = getattr(App, "ActiveDocument", None)
        if document is None:
            return {}
        objects = list(getattr(document, "Objects", []) or [])
        tool = {}
        for obj in objects:
            diameter = _property_float(getattr(obj, "Diameter", None))
            if diameter is None:
                continue
            name = getattr(obj, "Name", "") or ""
            label = getattr(obj, "Label", "") or name
            tool = {
                "name": name,
                "label": label,
                "diameter": diameter,
                "shank_diameter": _property_float(getattr(obj, "ShankDiameter", None)),
            }
            break
        for obj in objects:
            name = getattr(obj, "Name", "") or ""
            if "TC" not in name and "Tool" not in name:
                continue
            horiz = _property_float(getattr(obj, "HorizFeed", None))
            vert = _property_float(getattr(obj, "VertFeed", None))
            if horiz is not None:
                tool["horiz_feed"] = horiz
            if vert is not None:
                tool["vert_feed"] = vert
            if tool:
                break
        return tool

    def _template_spin(self, value, minimum, maximum, decimals=3):
        spin = QtWidgets.QDoubleSpinBox()
        spin.setDecimals(decimals)
        spin.setRange(minimum, maximum)
        spin.setValue(float(value))
        return spin

    def _confirm_replace_gcode(self):
        result = QtWidgets.QMessageBox.question(
            self,
            "Replace G-code?",
            "Replace current editor contents with the template?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        return result == QtWidgets.QMessageBox.Yes

    def _on_set_manual_start(self):
        allowed, reason = self._can_set_manual_start()
        if not allowed:
            self._append_console(f"Set manual start blocked: {reason}", force=True)
            if reason == "missing live position":
                self._request_status()
            return
        status = self._sender.get_status() or {}
        live = self._extract_live_xyz(status)
        if live is None:
            self._append_console("Set manual start blocked: missing live position", force=True)
            self._request_status()
            return
        self._gcode_manual_start_wpos = live["wpos"]
        self._gcode_manual_start_mpos = live["mpos"]
        self._gcode_manual_start_wco = live["wco"]
        self._gcode_manual_start_at = time.time()
        self._manual_start_status.setText(
            "Manual start: "
            f"X{live['wpos']['x']:.3f} Y{live['wpos']['y']:.3f} Z{live['wpos']['z']:.3f}"
        )
        self._append_console(
            "Manual start saved: "
            f"WPos X{live['wpos']['x']:.3f} Y{live['wpos']['y']:.3f} Z{live['wpos']['z']:.3f}",
            force=True,
        )
        self._update_preview()
        self._update_job_controls()

    def _on_use_manual_start_in_template(self):
        start = getattr(self, "_gcode_manual_start_wpos", None)
        if not start:
            self._append_console("Use manual start blocked: manual start not set.", force=True)
            return
        controls = getattr(self, "_template_controls", None)
        if not controls:
            self._append_console("Use manual start blocked: template controls unavailable.", force=True)
            return
        controls["start_z"].setValue(float(start["z"]))
        spec = self._read_rectangle_template_controls()
        if spec is None:
            return
        spec = replace(
            spec,
            start_z=float(start["z"]),
            cut_start_x=float(start["x"]),
            cut_start_y=float(start["y"]),
        )
        try:
            program = rectangle_pocket(spec)
        except ValueError as exc:
            self._append_console(f"Use manual start failed: {exc}", force=True)
            return
        self._last_template_spec = spec
        self._gcode_edit.setPlainText(program.gcode + "\n")
        self._append_console(
            "Manual start applied as cut start target: "
            f"X{start['x']:.3f} Y{start['y']:.3f} Z{start['z']:.3f}.",
            force=True,
        )
        self._update_preview()
        self._update_job_controls()

    def _can_set_manual_start(self):
        if not self._sender.is_connected():
            return False, "not connected"
        if self._sender.is_streaming():
            return False, "sender busy"
        if self._explore_active:
            return False, "limit explore active"
        if self._machine_state() != "idle":
            return False, f"machine state is {self._machine_state() or '?'}"
        if self._extract_live_xyz(self._sender.get_status() or {}) is None:
            return False, "missing live position"
        return True, ""

    def _on_go_to_manual_start_safely(self):
        allowed, reason = self._can_go_to_manual_start()
        if not allowed:
            self._append_console(f"Go to manual start blocked: {reason}", force=True)
            if reason == "missing live position":
                self._request_status()
            return
        start = self._gcode_manual_start_wpos
        safe_z = self._manual_start_safe_z()
        commands = [
            "G90 G21",
            f"G0 Z{safe_z:.3f}",
            f"G0 X{start['x']:.3f} Y{start['y']:.3f}",
        ]
        for command in commands:
            if not self._send_checked_command(command, timeout=8.0):
                return
        self._append_console("Moved safely to manual start X/Y at safe Z.", force=True)
        self._request_status()

    def _can_go_to_manual_start(self):
        if not self._gcode_manual_start_wpos:
            return False, "manual start not set"
        if not self._sender.is_connected():
            return False, "not connected"
        if self._sender.is_streaming():
            return False, "sender busy"
        if self._explore_active:
            return False, "limit explore active"
        if self._machine_state() != "idle":
            return False, f"machine state is {self._machine_state() or '?'}"
        live = self._extract_live_xyz(self._sender.get_status() or {})
        if live is None:
            return False, "missing live position"
        if self._gcode_manual_start_wco and not self._xyz_close(live["wco"], self._gcode_manual_start_wco):
            return False, "work offset changed"
        return True, ""

    def _on_validate_gcode(self):
        lines, _removed = prepare_stream_lines(self._gcode_edit.toPlainText(), dry_run=False)
        report = self._validate_gcode_lines(lines, label="Validate")
        self._gcode_last_validation = report
        self._update_job_controls()

    def _on_air_run(self):
        allowed, reason = self._can_stream_job()
        if not allowed:
            self._append_console(f"Air Run failed: {reason}", force=True)
            return
        lines = prepare_air_run_lines(self._gcode_edit.toPlainText(), air_z=self._manual_start_safe_z())
        if not lines:
            self._append_console("Air Run failed: G-code is empty.")
            return
        report = self._validate_gcode_lines(lines, label="Air Run")
        if not report or not report.get("valid"):
            return
        self._start_stream_lines(lines, "Air Run")

    def _on_show_apply_air_run(self):
        lines = prepare_air_run_lines(self._gcode_edit.toPlainText(), air_z=self._manual_start_safe_z())
        if not lines:
            self._append_console("Show/Apply Air Run failed: G-code is empty.", force=True)
            return
        self._gcode_edit.setPlainText("\n".join(lines) + "\n")
        self._append_console(
            f"Show/Apply Air Run: applied {len(lines)} transformed line(s); no machine commands sent.",
            force=True,
        )
        self._update_job_controls()

    def _can_stream_job(self):
        if not self._sender.is_connected():
            return False, "not connected"
        if self._sender.is_streaming():
            return False, "sender busy"
        state = self._machine_state()
        if state is None:
            self._request_status()
            return False, "machine status unknown"
        if state != "idle":
            return False, f"machine not idle ({state})"
        return True, ""

    def _validate_gcode_lines(self, lines, label="Validate"):
        if not lines:
            self._append_console(f"{label} failed: G-code is empty.")
            return None
        blocked = self._find_blocked_stream_command(lines)
        if blocked is not None:
            line_no, command, reason = blocked
            self._append_console(f"{label} failed at line {line_no}: {reason} ({command})", force=True)
            return {"valid": False, "errors": [{"line": line_no, "command": command, "reason": reason}]}
        status = self._sender.get_status() or {}
        profile, _profile_path = grbl_load_machine_profile(None)
        report = grbl_validate_gcode(
            lines,
            machine_profile=profile,
            grbl_settings=profile.get("settings") if isinstance(profile, dict) else None,
            status=status,
        )
        if report.get("valid"):
            bbox = report.get("bounding_box") or {}
            self._append_console(
                f"{label} ok: {report.get('line_count', len(lines))} lines, "
                f"bbox X{bbox.get('x')} Y{bbox.get('y')} Z{bbox.get('z')}.",
                force=True,
            )
        else:
            errors = report.get("errors") or []
            first = errors[0] if errors else {}
            self._append_console(
                f"{label} failed at line {first.get('line', '?')}: {first.get('reason', 'unknown error')}",
                force=True,
            )
        return report

    def _start_stream_lines(self, lines, label):
        try:
            self._sender.start_stream(lines)
            self._append_console(f"{label}: streaming {len(lines)} lines.")
        except Exception as exc:
            self._append_console(f"{label} failed: {exc}")
        self._update_job_controls()

    def _manual_start_safe_z(self):
        clearance = getattr(self, "_controller_manual_clearance", None)
        try:
            value = float(clearance.value()) if clearance is not None else 5.0
        except Exception:
            value = 5.0
        return max(value, 0.0)

    def _extract_live_xyz(self, status):
        status = status or {}
        mpos = grbl_parse_xyz_value(status.get("MPos"))
        wco = grbl_parse_xyz_value(status.get("WCO"))
        wpos = grbl_parse_xyz_value(status.get("WPos"))
        if wpos is None and mpos is not None and wco is not None:
            wpos = {axis: float(mpos[axis]) - float(wco[axis]) for axis in ("x", "y", "z")}
        if mpos is None or wco is None or wpos is None:
            return None
        return {
            "mpos": {axis: float(mpos[axis]) for axis in ("x", "y", "z")},
            "wco": {axis: float(wco[axis]) for axis in ("x", "y", "z")},
            "wpos": {axis: float(wpos[axis]) for axis in ("x", "y", "z")},
        }

    def _xyz_close(self, left, right, tolerance=0.01):
        if not left or not right:
            return False
        return all(abs(float(left[axis]) - float(right[axis])) <= tolerance for axis in ("x", "y", "z"))

    def _find_blocked_stream_command(self, lines):
        for line_no, line in enumerate(lines, start=1):
            command = str(line).strip()
            upper = command.upper()
            if upper.startswith("$H"):
                return line_no, command, "Homing is not allowed in normal G-code streaming"
            words = re.findall(r"([A-Z])\s*([-+]?\d*\.?\d+)", upper)
            for letter, number_text in words:
                try:
                    number = float(number_text)
                except ValueError:
                    continue
                if letter == "G" and any(abs(number - value) < 1e-9 for value in (10.0, 28.0, 30.0)):
                    return line_no, command, f"G{int(round(number))} is not allowed in normal G-code streaming"
        return None

    def _on_start_job(self):
        allowed, reason = self._can_stream_job()
        if not allowed:
            self._append_console(f"Start failed: {reason}.")
            return
        dry_run = self._dry_run_check.isChecked()
        lines, removed = prepare_stream_lines(self._gcode_edit.toPlainText(), dry_run=dry_run)
        if not lines:
            self._append_console("Start failed: G-code is empty.")
            return
        report = self._validate_gcode_lines(lines, label="Start")
        if not report or not report.get("valid"):
            return
        if dry_run and removed:
            self._append_console(f"Dry run active: skipped {len(removed)} spindle/laser command(s).")
        self._start_stream_lines(lines, "Start")

    def _on_pause_resume_job(self):
        if not self._sender.is_streaming():
            return
        try:
            if self._sender.is_paused():
                self._sender.resume_stream()
                self._append_console("Job resumed.")
            else:
                self._sender.pause_stream()
                self._append_console("Job paused with feed hold.")
        except Exception as exc:
            self._append_console(f"Pause/Resume failed: {exc}")
        self._update_job_controls()

    def _on_stop_job(self):
        if not self._sender.is_streaming():
            return
        try:
            self._sender.abort_stream()
            self._append_console("Job aborted with soft reset.")
        except Exception as exc:
            self._append_console(f"Stop failed: {exc}")
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
        connected = self._sender.is_connected()
        idle = self._machine_state() == "idle"
        has_gcode = bool(getattr(self, "_gcode_edit", None) is not None and self._gcode_edit.toPlainText().strip())
        self._start_btn.setEnabled(connected and not streaming and idle and has_gcode)
        self._pause_btn.setEnabled(streaming)
        self._stop_btn.setEnabled(streaming)
        self._pause_btn.setText("Resume" if paused else "Pause")
        validate_btn = getattr(self, "_validate_btn", None)
        if validate_btn is not None:
            validate_btn.setEnabled(not streaming and has_gcode)
        air_run_apply_btn = getattr(self, "_air_run_apply_btn", None)
        if air_run_apply_btn is not None:
            air_run_apply_btn.setEnabled(not streaming and has_gcode)
        air_run_btn = getattr(self, "_air_run_btn", None)
        if air_run_btn is not None:
            air_run_btn.setEnabled(connected and not streaming and idle and has_gcode)
        set_manual_start_btn = getattr(self, "_set_manual_start_btn", None)
        if set_manual_start_btn is not None:
            set_manual_start_btn.setEnabled(connected and not streaming and idle and not self._explore_active)
        go_manual_start_btn = getattr(self, "_go_manual_start_btn", None)
        if go_manual_start_btn is not None:
            go_manual_start_btn.setEnabled(
                connected
                and not streaming
                and idle
                and not self._explore_active
                and bool(getattr(self, "_gcode_manual_start_wpos", None))
            )
        use_manual_start_btn = getattr(self, "_use_manual_start_template_btn", None)
        if use_manual_start_btn is not None:
            use_manual_start_btn.setEnabled(bool(getattr(self, "_gcode_manual_start_wpos", None)))
        pick_fit_btn = getattr(self, "_pick_fit_corner_btn", None)
        if pick_fit_btn is not None:
            pick_fit_btn.setEnabled(not streaming)
            pick_fit_btn.setText("Cancel Fit Pick" if getattr(self, "_template_fit_pick_active", False) else "Pick Fit Corner")
        fit_candidates = getattr(self, "_template_fit_candidates", None) or []
        can_cycle_fit = len(fit_candidates) > 1 and not streaming
        prev_fit_btn = getattr(self, "_prev_fit_btn", None)
        if prev_fit_btn is not None:
            prev_fit_btn.setEnabled(can_cycle_fit)
        next_fit_btn = getattr(self, "_next_fit_btn", None)
        if next_fit_btn is not None:
            next_fit_btn.setEnabled(can_cycle_fit)

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
        controller_enable = getattr(self, "_controller_enable", None)
        if controller_enable is not None:
            controller_enable.setEnabled(
                connected
                and not streaming
                and not self._explore_active
                and getattr(self, "_controller", None) is not None
                and self._controller.is_connected()
                and not alarm_active
            )
        manual_prepare = getattr(self, "_controller_manual_prepare_btn", None)
        if manual_prepare is not None:
            state = self._machine_state()
            manual_prepare.setEnabled(
                connected
                and not streaming
                and not self._explore_active
                and not alarm_active
                and state in (None, "", "idle")
            )
        manual_exit = getattr(self, "_controller_manual_exit_btn", None)
        if manual_exit is not None:
            manual_exit.setEnabled(bool(getattr(self, "_controller_manual_xyz_active", False)))
        if self._explore_active:
            self._explore_limits_btn.setText("Stop Explore")
            self._read_limits_btn.setEnabled(False)
            self._travel_test_btn.setEnabled(False)
        else:
            self._explore_limits_btn.setText("Explore Limits")

    def _machine_state(self):
        status = self._sender.get_status() or {}
        state = str(status.get("state", "")).strip().lower()
        return state or None

    def _apply_disconnected_state(self, message=None, unexpected=False):
        self._poll_timer.stop()
        self._controller_stop()
        self._controller_manual_xyz_active = False
        self._status_tick = 0
        self._sender_was_connected = False
        self._reset_explore_state()
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
        if message and message != self._last_console_line:
            self._append_console(message, force=unexpected)
        self._update_job_controls()
        self._update_machine_controls()
        if unexpected:
            _status_message(f"RouterKing: disconnected unexpectedly ({message})\n", error=True)
        else:
            _status_message("RouterKing: disconnected\n")

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
        projection = self._preview_projection_name()
        scene = getattr(self, "_preview_scene", None)
        view = getattr(self, "_preview_view", None)
        if scene is not None and view is not None:
            self._render_gcode_preview(scene, view, projection)
        self._refresh_detached_preview()

    def _preview_projection_name(self):
        projection_widget = getattr(self, "_gcode_preview_projection", None)
        if projection_widget is not None:
            return str(projection_widget.currentText() or "Iso").lower()
        return "iso"

    def _render_gcode_preview(self, scene, view, projection):
        text = self._gcode_edit.toPlainText()
        path = parse_gcode_preview(text)
        scene.clear()
        if hasattr(view, "set_projection_name"):
            view.set_projection_name(projection)
        bounds = render_preview_scene(scene, path, projection=projection, clear=False)
        self._render_preview_tool_area_overlay(scene, projection)
        candidates = preview_snap_candidates(path, projection)
        if hasattr(view, "set_snap_candidates"):
            if getattr(self, "_template_fit_pick_active", False):
                view.set_snap_candidates(self._template_fit_pick_candidates(projection))
            else:
                view.set_snap_candidates(candidates)
        scene_bounds = scene.itemsBoundingRect()
        if bounds is None and scene_bounds.isNull():
            return
        if not scene_bounds.isNull():
            view.fitInView(scene_bounds, QtCore.Qt.KeepAspectRatio)

    def _render_preview_tool_area_overlay(self, scene, projection):
        if not self._preview_tool_area_enabled():
            return
        self._add_preview_machine_area(scene, projection)
        self._add_preview_template_fit_candidates(scene, projection)
        self._add_preview_manual_tool_dummy(scene, projection)

    def _preview_tool_area_enabled(self):
        checkbox = getattr(self, "_preview_tool_area_check", None)
        if checkbox is None:
            return True
        try:
            return checkbox.isChecked()
        except Exception:
            return True

    def _add_preview_machine_area(self, scene, projection):
        area = self._preview_work_area()
        if area is None:
            return
        qt_gui = QtGui
        pen = qt_gui.QPen(qt_gui.QColor(80, 180, 110, 160), 0)
        z_value = self._preview_overlay_z()
        corners = [
            PreviewPoint(area["x_min"], area["y_min"], z_value),
            PreviewPoint(area["x_max"], area["y_min"], z_value),
            PreviewPoint(area["x_max"], area["y_max"], z_value),
            PreviewPoint(area["x_min"], area["y_max"], z_value),
        ]
        for start, end in zip(corners, corners[1:] + corners[:1]):
            scene.addLine(*project_point(start, projection), *project_point(end, projection), pen)

    def _add_preview_template_fit_candidates(self, scene, projection):
        candidates = getattr(self, "_template_fit_candidates", None) or []
        if not candidates:
            return
        selected = getattr(self, "_template_fit_index", None)
        z_value = self._preview_overlay_z()
        qt_gui = QtGui
        for index, candidate in enumerate(candidates):
            bounds = candidate.get("bounds") or {}
            if index == selected:
                color = qt_gui.QColor(255, 210, 0, 230)
            else:
                color = qt_gui.QColor(255, 210, 0, 90)
            pen = qt_gui.QPen(color, 0)
            corners = [
                PreviewPoint(bounds["x_min"], bounds["y_min"], z_value),
                PreviewPoint(bounds["x_max"], bounds["y_min"], z_value),
                PreviewPoint(bounds["x_max"], bounds["y_max"], z_value),
                PreviewPoint(bounds["x_min"], bounds["y_max"], z_value),
            ]
            for start, end in zip(corners, corners[1:] + corners[:1]):
                scene.addLine(*project_point(start, projection), *project_point(end, projection), pen)

    def _add_preview_manual_tool_dummy(self, scene, projection):
        start = getattr(self, "_gcode_manual_start_wpos", None)
        if not start:
            return
        point = PreviewPoint(float(start["x"]), float(start["y"]), float(start.get("z", 0.0)))
        x_val, y_val = project_point(point, projection)
        radius = self._preview_tool_radius()
        qt_gui = QtGui
        pen = qt_gui.QPen(qt_gui.QColor(255, 210, 0), 0)
        brush = qt_gui.QBrush(qt_gui.QColor(255, 210, 0, 60))
        scene.addEllipse(x_val - radius, y_val - radius, radius * 2.0, radius * 2.0, pen, brush)
        cross = max(radius * 1.4, 2.0)
        scene.addLine(x_val - cross, y_val, x_val + cross, y_val, pen)
        scene.addLine(x_val, y_val - cross, x_val, y_val + cross, pen)

    def _preview_tool_radius(self):
        spec = self._read_rectangle_template_controls()
        if spec is not None:
            try:
                return max(float(spec.tool_diameter) / 2.0, 1.0)
            except (TypeError, ValueError):
                pass
        return 1.0

    def _preview_overlay_z(self):
        start = getattr(self, "_gcode_manual_start_wpos", None)
        if start:
            try:
                return float(start.get("z", 0.0))
            except (TypeError, ValueError):
                pass
        spec = getattr(self, "_last_template_spec", None)
        if spec is not None:
            return float(spec.start_z)
        return 0.0

    def _preview_work_area(self):
        profile = {}
        try:
            profile, _profile_path = grbl_load_machine_profile(None)
        except Exception:
            profile = {}
        limits = profile.get("machine_limits") or {}
        if not isinstance(limits, dict):
            return None
        x_limits = limits.get("x")
        y_limits = limits.get("y")
        if not x_limits or not y_limits:
            return None
        wco = self._preview_work_offset(profile)
        try:
            return {
                "x_min": float(x_limits[0]) - wco["x"],
                "x_max": float(x_limits[1]) - wco["x"],
                "y_min": float(y_limits[0]) - wco["y"],
                "y_max": float(y_limits[1]) - wco["y"],
            }
        except (TypeError, ValueError, IndexError):
            return None

    def _preview_work_offset(self, profile):
        sender = getattr(self, "_sender", None)
        status = getattr(sender, "get_status", lambda: None)() or {}
        live = self._extract_live_xyz(status)
        if live is not None and live.get("wco") is not None:
            return live["wco"]
        wco = grbl_parse_xyz_value(status.get("WCO"))
        if wco is not None:
            return {axis: float(wco[axis]) for axis in ("x", "y", "z")}
        stored = getattr(self, "_gcode_manual_start_wco", None)
        if stored:
            return stored
        profile_offset = profile.get("work_offset") if isinstance(profile, dict) else None
        if isinstance(profile_offset, dict):
            return {
                "x": float(profile_offset.get("x", 0.0)),
                "y": float(profile_offset.get("y", 0.0)),
                "z": float(profile_offset.get("z", 0.0)),
            }
        return {"x": 0.0, "y": 0.0, "z": 0.0}

    def _on_pick_template_fit_corner(self):
        if getattr(self, "_template_fit_pick_active", False):
            self._disable_template_fit_pick()
            self._append_console("Fit corner pick cancelled.", force=True)
            return
        spec = self._read_rectangle_template_controls()
        if spec is None:
            self._append_console("Pick fit corner blocked: template controls unavailable.", force=True)
            return
        area = self._preview_work_area()
        if area is None:
            self._append_console("Pick fit corner blocked: machine work area unavailable.", force=True)
            return
        if getattr(self, "_template_snap_active", False):
            self._disable_template_snap()
        self._template_fit_pick_active = True
        self._enable_template_fit_snap()
        self._update_fit_status()
        self._append_console(
            "Pick fit corner: move near a green work-area corner and click the snap marker.",
            force=True,
        )
        self._update_job_controls()

    def _template_fit_pick_candidates(self, projection):
        area = self._preview_work_area()
        if area is None:
            return ()
        z_value = self._preview_overlay_z()
        points = (
            PreviewPoint(area["x_min"], area["y_min"], z_value),
            PreviewPoint(area["x_max"], area["y_min"], z_value),
            PreviewPoint(area["x_max"], area["y_max"], z_value),
            PreviewPoint(area["x_min"], area["y_max"], z_value),
        )
        return tuple(
            PreviewSnapCandidate(
                point=point,
                projected=project_point(point, projection),
                reasons=("work_area_corner",),
                segment_indices=(),
                line_nos=(),
            )
            for point in points
        )

    def _disable_template_fit_pick(self):
        self._template_fit_pick_active = False
        for view in self._active_preview_views():
            view.set_snap_mode(False)
        self._update_job_controls()

    def _clear_template_fit_selection(self):
        self._template_fit_candidates = []
        self._template_fit_index = None
        self._template_fit_point = None
        self._update_fit_status()

    def _apply_template_fit_pick(self, point):
        spec = self._read_rectangle_template_controls()
        if spec is None:
            return
        area = self._preview_work_area()
        if area is None:
            self._append_console("Pick fit corner failed: machine work area unavailable.", force=True)
            self._disable_template_fit_pick()
            return
        candidates = self._template_fit_candidates_for_point(spec, point.x, point.y, area)
        self._disable_template_fit_pick()
        if not candidates:
            self._template_fit_candidates = []
            self._template_fit_index = None
            self._template_fit_point = point
            self._update_fit_status()
            self._update_preview()
            self._append_console(
                f"No fit candidate for X{point.x:.3f} Y{point.y:.3f}; rectangle does not fit there.",
                force=True,
            )
            return
        self._template_fit_candidates = candidates
        self._template_fit_index = 0
        self._template_fit_point = point
        self._apply_template_fit_candidate(0)
        self._append_console(
            f"Fit corner picked at X{point.x:.3f} Y{point.y:.3f}: "
            f"{len(candidates)} placement candidate(s). Use Prev/Next Fit to cycle.",
            force=True,
        )

    def _template_fit_candidates_for_point(self, spec, x_value, y_value, area):
        width, height = self._template_effective_size(spec)
        candidates = []
        for corner in ("lower_left", "lower_right", "upper_left", "upper_right"):
            start_x, start_y = self._template_start_for_corner(spec, width, height, x_value, y_value, corner)
            bounds = self._template_bounds_for_start(spec, width, height, start_x, start_y)
            if self._bounds_fit_area(bounds, area):
                candidates.append(
                    {
                        "corner": corner,
                        "start_x": start_x,
                        "start_y": start_y,
                        "cut_start_x": float(x_value),
                        "cut_start_y": float(y_value),
                        "bounds": bounds,
                    }
                )
        return candidates

    def _template_effective_size(self, spec):
        if bool(getattr(spec, "swap_xy", False)):
            return float(spec.height), float(spec.width)
        return float(spec.width), float(spec.height)

    def _template_start_for_corner(self, spec, width, height, x_value, y_value, corner):
        origin = str(getattr(spec, "origin", "center") or "center").strip().lower().replace("-", "_")
        if origin == "lower_left":
            if corner == "lower_left":
                return float(x_value), float(y_value)
            if corner == "lower_right":
                return float(x_value) - width, float(y_value)
            if corner == "upper_left":
                return float(x_value), float(y_value) - height
            return float(x_value) - width, float(y_value) - height

        if corner == "lower_left":
            return float(x_value) + width / 2.0, float(y_value) + height / 2.0
        if corner == "lower_right":
            return float(x_value) - width / 2.0, float(y_value) + height / 2.0
        if corner == "upper_left":
            return float(x_value) + width / 2.0, float(y_value) - height / 2.0
        return float(x_value) - width / 2.0, float(y_value) - height / 2.0

    def _template_bounds_for_start(self, spec, width, height, start_x, start_y):
        origin = str(getattr(spec, "origin", "center") or "center").strip().lower().replace("-", "_")
        if origin == "lower_left":
            return {
                "x_min": float(start_x),
                "x_max": float(start_x) + width,
                "y_min": float(start_y),
                "y_max": float(start_y) + height,
            }
        return {
            "x_min": float(start_x) - width / 2.0,
            "x_max": float(start_x) + width / 2.0,
            "y_min": float(start_y) - height / 2.0,
            "y_max": float(start_y) + height / 2.0,
        }

    def _bounds_fit_area(self, bounds, area, tolerance=1e-6):
        return (
            bounds["x_min"] >= area["x_min"] - tolerance
            and bounds["x_max"] <= area["x_max"] + tolerance
            and bounds["y_min"] >= area["y_min"] - tolerance
            and bounds["y_max"] <= area["y_max"] + tolerance
        )

    def _on_previous_template_fit(self):
        self._cycle_template_fit(-1)

    def _on_next_template_fit(self):
        self._cycle_template_fit(1)

    def _cycle_template_fit(self, direction):
        candidates = getattr(self, "_template_fit_candidates", None) or []
        if not candidates:
            self._append_console("Fit cycle blocked: no placement candidates.", force=True)
            return
        current = getattr(self, "_template_fit_index", None)
        if current is None:
            current = 0
        self._apply_template_fit_candidate((int(current) + int(direction)) % len(candidates))

    def _apply_template_fit_candidate(self, index):
        candidates = getattr(self, "_template_fit_candidates", None) or []
        if index < 0 or index >= len(candidates):
            return
        candidate = candidates[index]
        controls = getattr(self, "_template_controls", None)
        if controls:
            controls["start_x"].setValue(float(candidate["start_x"]))
            controls["start_y"].setValue(float(candidate["start_y"]))
        spec = self._read_rectangle_template_controls()
        if spec is None:
            return
        spec = replace(
            spec,
            start_x=float(candidate["start_x"]),
            start_y=float(candidate["start_y"]),
            cut_start_x=float(candidate["cut_start_x"]),
            cut_start_y=float(candidate["cut_start_y"]),
        )
        try:
            program = rectangle_pocket(spec)
        except ValueError as exc:
            self._append_console(f"Apply fit failed: {exc}", force=True)
            return
        self._template_fit_index = index
        self._last_template_spec = spec
        self._gcode_edit.setPlainText(program.gcode + "\n")
        self._populate_rectangle_template_controls(spec)
        self._update_fit_status()
        self._update_preview()
        self._update_job_controls()

    def _update_fit_status(self):
        label = getattr(self, "_fit_status", None)
        if label is None:
            return
        candidates = getattr(self, "_template_fit_candidates", None) or []
        index = getattr(self, "_template_fit_index", None)
        if getattr(self, "_template_fit_pick_active", False):
            label.setText("Fit: picking")
            return
        if not candidates or index is None:
            label.setText("Fit: no placement" if getattr(self, "_template_fit_point", None) else "Fit: pick corner")
            return
        candidate = candidates[index]
        label.setText(
            f"Fit: {index + 1}/{len(candidates)} "
            f"{str(candidate.get('corner', '')).replace('_', ' ')}"
        )

    def _schedule_preview_update(self):
        timer = getattr(self, "_preview_refresh_timer", None)
        if timer is None:
            self._update_preview()
            return
        timer.start()

    def _on_open_gcode_preview(self):
        dialog = getattr(self, "_preview_dialog", None)
        if dialog is None:
            dialog = GcodePreviewDialog(self, self)
            self._preview_dialog = dialog
        else:
            dialog.refresh()
        dialog.show()
        dialog.raise_()
        if hasattr(dialog, "activateWindow"):
            dialog.activateWindow()
        if getattr(self, "_template_fit_pick_active", False) and getattr(dialog, "_view", None) is not None:
            self._enable_template_fit_snap()

    def _refresh_detached_preview(self):
        dialog = getattr(self, "_preview_dialog", None)
        if dialog is None:
            return
        try:
            visible = dialog.isVisible()
        except Exception:
            visible = True
        if visible:
            dialog.refresh()

    def _on_set_template_start_from_snap(self):
        if getattr(self, "_template_fit_pick_active", False):
            self._disable_template_fit_pick()
        spec = getattr(self, "_last_template_spec", None)
        if spec is None:
            self._append_console("Set cut start snap blocked: generate a rectangle template first.", force=True)
            return
        path = parse_gcode_preview(self._gcode_edit.toPlainText())
        projection = self._preview_projection_name()
        candidates = self._template_cut_start_candidates(path, projection)
        if not candidates:
            self._append_console("Set cut start snap blocked: no preview snap points.", force=True)
            return
        self._template_snap_active = True
        self._enable_template_snap(candidates)
        self._append_console(
            "Set cut start snap: move near a path corner or direction change and click within 5 px.",
            force=True,
        )

    def _template_cut_start_candidates(self, path, projection):
        spec = getattr(self, "_last_template_spec", None)
        start_z = float(spec.start_z) if spec is not None else 0.0
        return tuple(
            candidate
            for candidate in preview_snap_candidates(path, projection)
            if candidate.point.z <= start_z + 1e-6
        )

    def _enable_template_snap(self, candidates):
        callback = self._apply_template_start_snap
        for view in self._active_preview_views():
            view.set_snap_mode(True, candidates, callback)

    def _enable_template_fit_snap(self):
        for view in self._active_preview_views():
            projection = getattr(view, "_projection_name", self._preview_projection_name())
            candidates = self._template_fit_pick_candidates(projection)
            view.set_snap_mode(True, candidates, self._apply_template_fit_pick)

    def _disable_template_snap(self):
        self._template_snap_active = False
        for view in self._active_preview_views():
            view.set_snap_mode(False)

    def _active_preview_views(self):
        views = []
        if getattr(self, "_preview_view", None) is not None:
            views.append(self._preview_view)
        dialog = getattr(self, "_preview_dialog", None)
        if dialog is not None and getattr(dialog, "_view", None) is not None:
            views.append(dialog._view)
        return views

    def _apply_template_start_snap(self, point):
        spec = getattr(self, "_last_template_spec", None)
        if spec is None:
            return
        spec = replace(spec, cut_start_x=point.x, cut_start_y=point.y)
        try:
            program = rectangle_pocket(spec)
        except ValueError as exc:
            self._append_console(f"Set cut start snap failed: {exc}", force=True)
            return
        self._last_template_spec = spec
        self._disable_template_snap()
        self._gcode_edit.setPlainText(program.gcode + "\n")
        self._populate_rectangle_template_controls(spec)
        self._append_console(
            f"Cut start set from snap: X{point.x:.3f} Y{point.y:.3f}. Template regenerated without moving the pocket.",
            force=True,
        )
        self._update_preview()
        self._update_job_controls()
