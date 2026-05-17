"""Optional gamepad support for manual RouterKing jogging."""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import os
from typing import Any
import warnings


@dataclass(frozen=True)
class GamepadState:
    name: str
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    deadman: bool = False


@dataclass(frozen=True)
class GamepadAxis:
    name: str
    value: float


@dataclass(frozen=True)
class GamepadButton:
    name: str
    pressed: bool


@dataclass(frozen=True)
class GamepadSnapshot:
    name: str
    axes: tuple[GamepadAxis, ...]
    buttons: tuple[GamepadButton, ...]


DEFAULT_CONTROLLER_BINDINGS = {
    "x_axes": "Right X",
    "y_axes": "-Right Y",
    "z_axes": "R2, -L2",
    "x_neg_buttons": "DPad Left",
    "x_pos_buttons": "DPad Right",
    "y_neg_buttons": "DPad Down",
    "y_pos_buttons": "DPad Up",
    "z_neg_buttons": "",
    "z_pos_buttons": "",
    "deadman_buttons": "L1, R1",
}


def active_binding_tokens(snapshot: GamepadSnapshot, axis_threshold: float = 0.6) -> tuple[str, ...]:
    tokens = []
    threshold = max(0.05, min(1.0, float(axis_threshold)))
    for button in snapshot.buttons:
        if button.pressed:
            tokens.append(button.name)
    for axis in snapshot.axes:
        value = float(axis.value)
        if abs(value) >= threshold:
            tokens.append(f"-{axis.name}" if value < 0 else axis.name)
    return tuple(tokens)


class PygameGamepad:
    """Small pygame wrapper kept optional for FreeCAD installations."""

    DEFAULT_DEADMAN_BUTTONS = (4, 5)

    def __init__(self, pygame_module: Any | None = None):
        self._pygame = pygame_module
        self._controller_module = None
        self._controller = None
        self._joystick = None
        self._name = ""
        self._error = ""

    @property
    def error(self) -> str:
        return self._error

    def is_available(self) -> bool:
        return self._load_pygame() is not None

    def connect(self, index: int = 0) -> bool:
        pygame = self._load_pygame()
        if pygame is None:
            return False
        if self._connect_controller(index=index):
            return True
        try:
            joystick_module = pygame.joystick
            joystick_module.init()
            count = int(joystick_module.get_count())
            if count <= 0:
                self._error = "No gamepad detected."
                self._joystick = None
                self._name = ""
                return False
            if index < 0 or index >= count:
                index = 0
            joystick = joystick_module.Joystick(index)
            joystick.init()
            self._joystick = joystick
            self._name = str(joystick.get_name() or f"Gamepad {index + 1}")
            self._error = ""
            return True
        except Exception as exc:
            self._error = f"Gamepad connect failed: {exc}"
            self._joystick = None
            self._name = ""
            return False

    def disconnect(self) -> None:
        controller = self._controller
        joystick = self._joystick
        self._controller = None
        self._joystick = None
        self._name = ""
        try:
            if controller is not None:
                controller.quit()
        except Exception:
            pass
        try:
            if joystick is not None:
                joystick.quit()
        except Exception:
            pass

    def is_connected(self) -> bool:
        return self._controller is not None or self._joystick is not None

    def name(self) -> str:
        return self._name

    def poll(self, *, deadman_buttons: tuple[int, ...] | None = None) -> GamepadState | None:
        if self._controller is None and self._joystick is None:
            return None
        pygame = self._load_pygame()
        if pygame is None:
            return None
        try:
            pygame.event.pump()
            if self._controller is not None:
                return self._poll_controller(pygame)
            joystick = self._joystick
            x = _axis(joystick, 3)
            y = -_axis(joystick, 4)
            z = _trigger(_axis(joystick, 5)) - _trigger(_axis(joystick, 2))
            buttons = deadman_buttons or self.DEFAULT_DEADMAN_BUTTONS
            deadman = any(_button(joystick, index) for index in buttons)
            return GamepadState(name=self._name, x=x, y=y, z=z, deadman=deadman)
        except Exception as exc:
            self._error = f"Gamepad read failed: {exc}"
            self.disconnect()
            return None

    def poll_mapped(self, bindings: dict[str, str] | None = None) -> GamepadState | None:
        snapshot = self.snapshot()
        if snapshot is None:
            return None
        return state_from_snapshot(snapshot, bindings or DEFAULT_CONTROLLER_BINDINGS)

    def snapshot(self) -> GamepadSnapshot | None:
        if self._controller is None and self._joystick is None:
            return None
        pygame = self._load_pygame()
        if pygame is None:
            return None
        try:
            pygame.event.pump()
            if self._controller is not None:
                return self._snapshot_controller(pygame)
            return self._snapshot_joystick()
        except Exception as exc:
            self._error = f"Gamepad read failed: {exc}"
            self.disconnect()
            return None

    def _connect_controller(self, index: int = 0) -> bool:
        try:
            controller_module = importlib.import_module("pygame._sdl2.controller")
            controller_module.init()
            count = int(controller_module.get_count())
            if count <= 0:
                return False
            candidates = [index] + [i for i in range(count) if i != index]
            for candidate in candidates:
                try:
                    if hasattr(controller_module, "is_controller") and not controller_module.is_controller(candidate):
                        continue
                    controller = controller_module.Controller(candidate)
                    controller.init()
                    self._controller_module = controller_module
                    self._controller = controller
                    self._joystick = None
                    name_attr = getattr(controller, "name", "")
                    controller_name = name_attr() if callable(name_attr) else name_attr
                    self._name = str(controller_name or f"Controller {candidate + 1}")
                    self._error = ""
                    return True
                except Exception:
                    continue
        except Exception:
            return False
        return False

    def _poll_controller(self, pygame) -> GamepadState:
        controller = self._controller
        x = _controller_axis(controller, pygame.CONTROLLER_AXIS_RIGHTX)
        y = -_controller_axis(controller, pygame.CONTROLLER_AXIS_RIGHTY)
        z = _controller_trigger(controller, pygame.CONTROLLER_AXIS_TRIGGERRIGHT) - _controller_trigger(
            controller,
            pygame.CONTROLLER_AXIS_TRIGGERLEFT,
        )
        deadman = any(
            _controller_button(controller, index)
            for index in (
                pygame.CONTROLLER_BUTTON_LEFTSHOULDER,
                pygame.CONTROLLER_BUTTON_RIGHTSHOULDER,
            )
        )
        return GamepadState(name=self._name, x=x, y=y, z=z, deadman=deadman)

    def _snapshot_controller(self, pygame) -> GamepadSnapshot:
        controller = self._controller
        axes = tuple(
            GamepadAxis(label, _controller_axis(controller, axis))
            for label, axis in _controller_axis_specs(pygame)
        )
        buttons = tuple(
            GamepadButton(label, _controller_button(controller, button))
            for label, button in _controller_button_specs(pygame)
        )
        return GamepadSnapshot(name=self._name, axes=axes, buttons=buttons)

    def _snapshot_joystick(self) -> GamepadSnapshot:
        joystick = self._joystick
        axes = tuple(
            GamepadAxis(f"Axis {index}", _axis(joystick, index))
            for index in range(int(joystick.get_numaxes()))
        )
        buttons = tuple(
            GamepadButton(f"Button {index}", _button(joystick, index))
            for index in range(int(joystick.get_numbuttons()))
        )
        return GamepadSnapshot(name=self._name, axes=axes, buttons=buttons)

    def _load_pygame(self):
        if self._pygame is not None:
            return self._pygame
        try:
            os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message=r"pkg_resources is deprecated.*",
                    category=UserWarning,
                )
                self._pygame = importlib.import_module("pygame")
                self._pygame.init()
        except Exception as exc:
            self._error = f"pygame unavailable: {exc}"
            self._pygame = None
        return self._pygame


def apply_deadzone(value: float, deadzone: float) -> float:
    value = max(-1.0, min(1.0, float(value)))
    deadzone = max(0.0, min(0.95, float(deadzone)))
    magnitude = abs(value)
    if magnitude <= deadzone:
        return 0.0
    scaled = (magnitude - deadzone) / (1.0 - deadzone)
    return scaled if value > 0 else -scaled


def make_jog_vector(
    state: GamepadState,
    *,
    deadzone: float,
    xy_step: float,
    z_step: float,
) -> tuple[float, float, float]:
    x = apply_deadzone(state.x, deadzone) * float(xy_step)
    y = apply_deadzone(state.y, deadzone) * float(xy_step)
    z = apply_deadzone(state.z, deadzone) * float(z_step)
    return (_round_zero(x), _round_zero(y), _round_zero(z))


def state_from_snapshot(snapshot: GamepadSnapshot, bindings: dict[str, str] | None = None) -> GamepadState:
    bindings = dict(DEFAULT_CONTROLLER_BINDINGS | dict(bindings or {}))
    axes = {axis.name: float(axis.value) for axis in snapshot.axes}
    buttons = {button.name: bool(button.pressed) for button in snapshot.buttons}
    x = _binding_axis_value(axes, bindings.get("x_axes", "")) - _button_value(buttons, bindings.get("x_neg_buttons", ""))
    x += _button_value(buttons, bindings.get("x_pos_buttons", ""))
    y = _binding_axis_value(axes, bindings.get("y_axes", "")) - _button_value(buttons, bindings.get("y_neg_buttons", ""))
    y += _button_value(buttons, bindings.get("y_pos_buttons", ""))
    z = _binding_axis_value(axes, bindings.get("z_axes", "")) - _button_value(buttons, bindings.get("z_neg_buttons", ""))
    z += _button_value(buttons, bindings.get("z_pos_buttons", ""))
    deadman = _button_value(buttons, bindings.get("deadman_buttons", "")) > 0.0
    return GamepadState(
        name=snapshot.name,
        x=_round_zero(max(-1.0, min(1.0, x))),
        y=_round_zero(max(-1.0, min(1.0, y))),
        z=_round_zero(max(-1.0, min(1.0, z))),
        deadman=deadman,
    )


def _binding_axis_value(axes: dict[str, float], binding_text: str) -> float:
    value = 0.0
    for token in _split_binding_tokens(binding_text):
        sign = -1.0 if token.startswith("-") else 1.0
        name = token[1:].strip() if token.startswith("-") else token
        value += sign * axes.get(name, 0.0)
    return max(-1.0, min(1.0, value))


def _button_value(buttons: dict[str, bool], binding_text: str) -> float:
    return 1.0 if any(buttons.get(token, False) for token in _split_binding_tokens(binding_text)) else 0.0


def _split_binding_tokens(binding_text: str) -> tuple[str, ...]:
    return tuple(token.strip() for token in str(binding_text or "").split(",") if token.strip())


def _axis(joystick: Any, index: int) -> float:
    try:
        if index >= int(joystick.get_numaxes()):
            return 0.0
        return float(joystick.get_axis(index))
    except Exception:
        return 0.0


def _controller_axis(controller: Any, axis: int) -> float:
    try:
        value = float(controller.get_axis(axis))
        if abs(value) > 1.0:
            value = value / 32767.0
        return max(-1.0, min(1.0, value))
    except Exception:
        return 0.0


def _controller_trigger(controller: Any, axis: int) -> float:
    return _trigger(_controller_axis(controller, axis))


def _trigger(value: float) -> float:
    value = max(-1.0, min(1.0, float(value)))
    if value < 0.0:
        return (value + 1.0) / 2.0
    return value


def _controller_button(controller: Any, index: int) -> bool:
    try:
        return bool(controller.get_button(index))
    except Exception:
        return False


def _button(joystick: Any, index: int) -> bool:
    try:
        if index < 0 or index >= int(joystick.get_numbuttons()):
            return False
        return bool(joystick.get_button(index))
    except Exception:
        return False


def _round_zero(value: float) -> float:
    return 0.0 if abs(value) < 0.0005 else float(value)


def _controller_axis_specs(pygame) -> tuple[tuple[str, int], ...]:
    specs = (
        ("Left X", "CONTROLLER_AXIS_LEFTX"),
        ("Left Y", "CONTROLLER_AXIS_LEFTY"),
        ("Right X", "CONTROLLER_AXIS_RIGHTX"),
        ("Right Y", "CONTROLLER_AXIS_RIGHTY"),
        ("L2", "CONTROLLER_AXIS_TRIGGERLEFT"),
        ("R2", "CONTROLLER_AXIS_TRIGGERRIGHT"),
    )
    return tuple((label, getattr(pygame, attr)) for label, attr in specs if hasattr(pygame, attr))


def _controller_button_specs(pygame) -> tuple[tuple[str, int], ...]:
    specs = (
        ("Cross / A", "CONTROLLER_BUTTON_A"),
        ("Circle / B", "CONTROLLER_BUTTON_B"),
        ("Square / X", "CONTROLLER_BUTTON_X"),
        ("Triangle / Y", "CONTROLLER_BUTTON_Y"),
        ("Share / Back", "CONTROLLER_BUTTON_BACK"),
        ("Guide / PS", "CONTROLLER_BUTTON_GUIDE"),
        ("Options / Start", "CONTROLLER_BUTTON_START"),
        ("Left Stick", "CONTROLLER_BUTTON_LEFTSTICK"),
        ("Right Stick", "CONTROLLER_BUTTON_RIGHTSTICK"),
        ("L1", "CONTROLLER_BUTTON_LEFTSHOULDER"),
        ("R1", "CONTROLLER_BUTTON_RIGHTSHOULDER"),
        ("DPad Up", "CONTROLLER_BUTTON_DPAD_UP"),
        ("DPad Down", "CONTROLLER_BUTTON_DPAD_DOWN"),
        ("DPad Left", "CONTROLLER_BUTTON_DPAD_LEFT"),
        ("DPad Right", "CONTROLLER_BUTTON_DPAD_RIGHT"),
        ("Touchpad", "CONTROLLER_BUTTON_TOUCHPAD"),
    )
    return tuple((label, getattr(pygame, attr)) for label, attr in specs if hasattr(pygame, attr))
