import unittest
from types import SimpleNamespace

from RouterKing.ui.gamepad import (
    GamepadAxis,
    GamepadButton,
    GamepadSnapshot,
    GamepadState,
    PygameGamepad,
    active_binding_tokens,
    apply_deadzone,
    make_fast_xy_jog_vector,
    make_jog_vector,
    state_from_snapshot,
)


class TestGamepadHelpers(unittest.TestCase):
    def test_apply_deadzone_zeros_small_values(self):
        self.assertEqual(apply_deadzone(0.1, 0.2), 0.0)
        self.assertEqual(apply_deadzone(-0.1, 0.2), 0.0)

    def test_apply_deadzone_scales_remaining_range(self):
        self.assertAlmostEqual(apply_deadzone(0.6, 0.2), 0.5)
        self.assertAlmostEqual(apply_deadzone(-0.6, 0.2), -0.5)

    def test_make_jog_vector_uses_axis_specific_steps(self):
        state = GamepadState(name="Pad", x=1.0, y=-0.6, z=0.5, deadman=True)
        x, y, z = make_jog_vector(state, deadzone=0.2, xy_step=0.5, z_step=0.1)

        self.assertAlmostEqual(x, 0.5)
        self.assertAlmostEqual(y, -0.25)
        self.assertAlmostEqual(z, 0.0375)

    def test_controller_mapping_uses_right_stick_and_triggers(self):
        axes = {
            0: 0.9,
            1: 0.9,
            2: 0.25,
            3: -0.5,
            4: 0.0,
            5: 0.75,
        }
        buttons = {6: True, 7: False}
        fake_controller = SimpleNamespace(
            get_axis=lambda axis: axes.get(axis, 0.0),
            get_button=lambda button: buttons.get(button, False),
        )
        fake_pygame = SimpleNamespace(
            CONTROLLER_AXIS_LEFTX=0,
            CONTROLLER_AXIS_LEFTY=1,
            CONTROLLER_AXIS_RIGHTX=2,
            CONTROLLER_AXIS_RIGHTY=3,
            CONTROLLER_AXIS_TRIGGERLEFT=4,
            CONTROLLER_AXIS_TRIGGERRIGHT=5,
            CONTROLLER_BUTTON_LEFTSHOULDER=6,
            CONTROLLER_BUTTON_RIGHTSHOULDER=7,
        )

        pad = PygameGamepad(pygame_module=fake_pygame)
        pad._controller = fake_controller
        pad._name = "Pad"

        state = pad._poll_controller(fake_pygame)

        self.assertEqual(state.name, "Pad")
        self.assertAlmostEqual(state.x, 0.25)
        self.assertAlmostEqual(state.y, 0.5)
        self.assertAlmostEqual(state.z, 0.75)
        self.assertTrue(state.deadman)
        self.assertEqual(state.speed_label, "slow")
        self.assertEqual(state.speed_multiplier, 1.0)

    def test_snapshot_reports_controller_axes_and_buttons(self):
        axes = {
            0: -0.1,
            1: 0.2,
            2: 0.3,
            3: -0.4,
            4: 0.5,
            5: 0.6,
        }
        buttons = {0: True, 1: False, 6: True}
        fake_controller = SimpleNamespace(
            get_axis=lambda axis: axes.get(axis, 0.0),
            get_button=lambda button: buttons.get(button, False),
        )
        fake_pygame = SimpleNamespace(
            event=SimpleNamespace(pump=lambda: None),
            CONTROLLER_AXIS_LEFTX=0,
            CONTROLLER_AXIS_LEFTY=1,
            CONTROLLER_AXIS_RIGHTX=2,
            CONTROLLER_AXIS_RIGHTY=3,
            CONTROLLER_AXIS_TRIGGERLEFT=4,
            CONTROLLER_AXIS_TRIGGERRIGHT=5,
            CONTROLLER_BUTTON_A=0,
            CONTROLLER_BUTTON_B=1,
            CONTROLLER_BUTTON_LEFTSHOULDER=6,
        )

        pad = PygameGamepad(pygame_module=fake_pygame)
        pad._controller = fake_controller
        pad._name = "Pad"

        snapshot = pad.snapshot()

        self.assertEqual(snapshot.name, "Pad")
        self.assertEqual([axis.name for axis in snapshot.axes], ["Left X", "Left Y", "Right X", "Right Y", "L2", "R2"])
        self.assertAlmostEqual(snapshot.axes[2].value, 0.3)
        self.assertEqual([button.name for button in snapshot.buttons], ["Cross / A", "Circle / B", "L1"])
        self.assertTrue(snapshot.buttons[0].pressed)
        self.assertFalse(snapshot.buttons[1].pressed)
        self.assertTrue(snapshot.buttons[2].pressed)

    def test_snapshot_normalizes_controller_triggers_to_positive_range(self):
        axes = {
            4: -1.0,
            5: 1.0,
        }
        fake_controller = SimpleNamespace(
            get_axis=lambda axis: axes.get(axis, 0.0),
            get_button=lambda button: False,
        )
        fake_pygame = SimpleNamespace(
            event=SimpleNamespace(pump=lambda: None),
            CONTROLLER_AXIS_TRIGGERLEFT=4,
            CONTROLLER_AXIS_TRIGGERRIGHT=5,
        )

        pad = PygameGamepad(pygame_module=fake_pygame)
        pad._controller = fake_controller
        pad._name = "Pad"

        snapshot = pad.snapshot()

        self.assertEqual([axis.name for axis in snapshot.axes], ["L2", "R2"])
        self.assertAlmostEqual(snapshot.axes[0].value, 0.0)
        self.assertAlmostEqual(snapshot.axes[1].value, 1.0)

    def test_snapshot_calibrates_nonstandard_trigger_rest_position(self):
        axes = {
            4: -0.216,
            5: -0.216,
        }
        fake_controller = SimpleNamespace(
            get_axis=lambda axis: axes.get(axis, 0.0),
            get_button=lambda button: False,
        )
        fake_pygame = SimpleNamespace(
            event=SimpleNamespace(pump=lambda: None),
            CONTROLLER_AXIS_TRIGGERLEFT=4,
            CONTROLLER_AXIS_TRIGGERRIGHT=5,
        )

        pad = PygameGamepad(pygame_module=fake_pygame)
        pad._controller = fake_controller
        pad._controller_trigger_rest = {4: -0.216, 5: -0.216}
        pad._name = "Pad"

        snapshot = pad.snapshot()

        self.assertAlmostEqual(snapshot.axes[0].value, 0.0)
        self.assertAlmostEqual(snapshot.axes[1].value, 0.0)

        axes[4] = 1.0
        snapshot = pad.snapshot()
        self.assertAlmostEqual(snapshot.axes[0].value, 1.0)

    def test_state_from_snapshot_maps_l2_to_z_down(self):
        snapshot = GamepadSnapshot(
            name="Pad",
            axes=(
                GamepadAxis("L2", 1.0),
                GamepadAxis("R2", 0.0),
            ),
            buttons=(),
        )

        state = state_from_snapshot(snapshot)

        self.assertEqual(state.z, -1.0)

    def test_state_from_snapshot_supports_multiple_bindings(self):
        snapshot = GamepadSnapshot(
            name="Pad",
            axes=(
                GamepadAxis("Right X", 0.25),
                GamepadAxis("Right Y", -0.5),
                GamepadAxis("L2", 0.0),
                GamepadAxis("R2", 0.4),
            ),
            buttons=(
                GamepadButton("DPad Right", True),
                GamepadButton("DPad Up", True),
                GamepadButton("L1", True),
            ),
        )

        state = state_from_snapshot(snapshot)

        self.assertEqual(state.name, "Pad")
        self.assertEqual(state.x, 1.0)
        self.assertEqual(state.y, 1.0)
        self.assertAlmostEqual(state.z, 0.4)
        self.assertTrue(state.deadman)
        self.assertEqual(state.speed_label, "slow")
        self.assertEqual(state.speed_multiplier, 1.0)

    def test_state_from_snapshot_uses_speed_buttons_not_deadman_gate(self):
        fast = state_from_snapshot(
            GamepadSnapshot(
                name="Pad",
                axes=(GamepadAxis("Right X", 1.0),),
                buttons=(GamepadButton("L1", False), GamepadButton("R1", False)),
            )
        )
        medium = state_from_snapshot(
            GamepadSnapshot(
                name="Pad",
                axes=(GamepadAxis("Right X", 1.0),),
                buttons=(GamepadButton("L1", False), GamepadButton("R1", True)),
            )
        )
        slow = state_from_snapshot(
            GamepadSnapshot(
                name="Pad",
                axes=(GamepadAxis("Right X", 1.0),),
                buttons=(GamepadButton("L1", True), GamepadButton("R1", True)),
            )
        )

        self.assertTrue(fast.deadman)
        self.assertEqual((fast.speed_label, fast.speed_multiplier), ("fast", 3.0))
        self.assertEqual((medium.speed_label, medium.speed_multiplier), ("medium", 2.0))
        self.assertEqual((slow.speed_label, slow.speed_multiplier), ("slow", 1.0))

    def test_make_jog_vector_applies_speed_multiplier(self):
        state = GamepadState(name="Pad", x=1.0, y=0.0, z=1.0, speed_multiplier=3.0)

        x, y, z = make_jog_vector(state, deadzone=0.2, xy_step=0.5, z_step=0.1)

        self.assertAlmostEqual(x, 1.5)
        self.assertEqual(y, 0.0)
        self.assertAlmostEqual(z, 0.3)

    def test_make_fast_xy_jog_vector_uses_feed_lookahead_for_xy(self):
        state = GamepadState(name="Pad", x=1.0, y=0.0, z=0.0, speed_multiplier=3.0, speed_label="fast")

        x, y, z = make_fast_xy_jog_vector(state, deadzone=0.2, xy_feed=1800.0, lookahead_s=0.28, z_step=0.1)

        self.assertAlmostEqual(x, 8.4)
        self.assertEqual(y, 0.0)
        self.assertEqual(z, 0.0)

    def test_state_from_snapshot_allows_custom_button_rebinding(self):
        snapshot = GamepadSnapshot(
            name="Pad",
            axes=(),
            buttons=(
                GamepadButton("Cross / A", True),
                GamepadButton("Square / X", True),
            ),
        )

        state = state_from_snapshot(
            snapshot,
            {
                "x_axes": "",
                "y_axes": "",
                "z_axes": "",
                "x_pos_buttons": "Cross / A, DPad Right",
                "slow_buttons": "Square / X",
            },
        )

        self.assertEqual(state.x, 1.0)
        self.assertTrue(state.deadman)
        self.assertEqual(state.speed_label, "slow")

    def test_active_binding_tokens_prefers_buttons_and_thresholded_axes(self):
        snapshot = GamepadSnapshot(
            name="Pad",
            axes=(
                GamepadAxis("Right X", 0.2),
                GamepadAxis("Right Y", -0.7),
                GamepadAxis("L2", 0.3),
                GamepadAxis("R2", 0.8),
            ),
            buttons=(
                GamepadButton("DPad Left", False),
                GamepadButton("Cross / A", True),
            ),
        )

        self.assertEqual(active_binding_tokens(snapshot), ("Cross / A", "-Right Y", "R2"))


if __name__ == "__main__":
    unittest.main()
