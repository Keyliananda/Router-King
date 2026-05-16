import unittest
from unittest.mock import patch

from RouterKing.ai.actions import (
    _action_machine_prepare_manual_xy,
    _action_machine_probe_config,
    _action_machine_probe_z,
    _parse_probe_response_line,
)


class _ProbeSender:
    def __init__(self, *, initial_status=None, final_status=None, probe_lines=None):
        self._initial_status = initial_status or {
            "state": "Idle",
            "WPos": "0.000,0.000,2.000",
            "WCO": "-297.000,-377.000,-3.000",
        }
        self._final_status = final_status or {
            "state": "Idle",
            "WPos": "0.000,0.000,0.000",
            "WCO": "-297.000,-377.000,-3.000",
        }
        self._status_request_count = 0
        self._probe_lines = list(probe_lines or [])
        self._connected = True
        self._streaming = False
        self.commands = []
        self.unlocked = False

    def is_connected(self):
        return self._connected

    def is_streaming(self):
        return self._streaming

    def poll(self):
        return []

    def request_status(self):
        self._status_request_count += 1

    def get_status(self):
        if self._status_request_count <= 1:
            return dict(self._initial_status)
        return dict(self._final_status)

    def send_and_collect(self, command, timeout=2.0):
        self.commands.append((command, float(timeout)))
        if command.startswith("G91 G38.2"):
            return list(self._probe_lines)
        if command == "$X":
            self.unlocked = True
            return []
        return []


class TestProbeParsing(unittest.TestCase):
    def test_parse_prb_line_success(self):
        parsed = _parse_probe_response_line("[PRB:1.234,2.345,-3.456:1]")
        self.assertIsInstance(parsed, dict)
        self.assertAlmostEqual(parsed["x"], 1.234)
        self.assertAlmostEqual(parsed["y"], 2.345)
        self.assertAlmostEqual(parsed["z"], -3.456)
        self.assertEqual(parsed["success"], 1)

    def test_parse_prb_line_invalid(self):
        self.assertIsNone(_parse_probe_response_line("[GC:G0 G54 G17]"))


class TestProbeAction(unittest.TestCase):
    def test_probe_z_success_flow(self):
        sender = _ProbeSender(probe_lines=["[PRB:10.000,20.000,-12.500:1]"])

        with patch("RouterKing.ai.actions._get_sender", return_value=sender):
            result = _action_machine_probe_z(
                {
                    "type": "machine_probe_z",
                    "block_height": 15.0,
                    "confirm": True,
                },
                {},
            )

        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("data", {}).get("success"), True)
        self.assertEqual(result.get("data", {}).get("block_height"), 15.0)
        self.assertEqual(result.get("data", {}).get("new_z_zero"), "Z0 is now at workpiece surface")
        self.assertEqual(result.get("data", {}).get("probe_position", {}).get("z"), -12.5)

        sent_commands = [item[0] for item in sender.commands]
        self.assertTrue(any(cmd.startswith("G91 G38.2") for cmd in sent_commands))
        self.assertIn("G10 L20 P1 Z15.000", sent_commands)
        self.assertLess(sent_commands.index("G10 L20 P1 Z15.000"), sent_commands.index("G91 G0 Z3.000"))

    def test_probe_z_alarm4_unlocks(self):
        sender = _ProbeSender(probe_lines=["[PRB:0.000,0.000,-30.000:0]", "ALARM:4"])

        with patch("RouterKing.ai.actions._get_sender", return_value=sender):
            result = _action_machine_probe_z(
                {
                    "type": "machine_probe_z",
                    "block_height": 15.0,
                    "confirm": True,
                },
                {},
            )

        self.assertIsInstance(result, str)
        self.assertIn("ALARM:4", result)
        self.assertTrue(sender.unlocked)
        self.assertTrue(any(command == "$X" for command, _ in sender.commands))

    def test_probe_z_rejects_already_triggered_pin(self):
        sender = _ProbeSender(initial_status={"state": "Idle", "Pn": "P"})

        with patch("RouterKing.ai.actions._get_sender", return_value=sender):
            result = _action_machine_probe_z(
                {
                    "type": "machine_probe_z",
                    "block_height": 15.0,
                    "confirm": True,
                },
                {},
            )

        self.assertIsInstance(result, str)
        self.assertIn("ALARM:5", result)
        self.assertFalse(any(command.startswith("G91 G38.2") for command, _ in sender.commands))

    def test_prepare_manual_xy_lowers_to_ten_percent_touch_plate_height(self):
        sender = _ProbeSender(
            initial_status={"state": "Idle", "WPos": "0.000,0.000,15.000"},
            final_status={"state": "Idle", "WPos": "0.000,0.000,1.500"},
        )
        profile = {"probe": {"block_height": 15.0, "probe_feed": 50.0, "retract_height": 3.0}}

        with patch("RouterKing.ai.actions._get_sender", return_value=sender):
            with patch("RouterKing.ai.actions.grbl_load_machine_profile", return_value=(profile, "/tmp/machine_profile.json")):
                result = _action_machine_prepare_manual_xy(
                    {
                        "type": "machine_prepare_manual_xy",
                        "confirm": True,
                    },
                    {},
                )

        self.assertIsInstance(result, dict)
        self.assertEqual(result["data"]["block_height"], 15.0)
        self.assertAlmostEqual(result["data"]["target_clearance"], 1.5)
        self.assertAlmostEqual(result["data"]["descent_percent"], 90.0)
        sent_commands = [item[0] for item in sender.commands]
        self.assertIn("G90 G21", sent_commands)
        self.assertIn("G0 Z1.500", sent_commands)

    def test_prepare_manual_xy_does_not_move_x_or_y(self):
        sender = _ProbeSender(initial_status={"state": "Idle", "WPos": "4.000,5.000,15.000"})
        profile = {"probe": {"block_height": 20.0}}

        with patch("RouterKing.ai.actions._get_sender", return_value=sender):
            with patch("RouterKing.ai.actions.grbl_load_machine_profile", return_value=(profile, "/tmp/machine_profile.json")):
                _action_machine_prepare_manual_xy(
                    {
                        "type": "machine_prepare_manual_xy",
                        "target_clearance": 2.0,
                        "confirm": True,
                    },
                    {},
                )

        sent_commands = [item[0] for item in sender.commands]
        self.assertIn("G0 Z2.000", sent_commands)
        self.assertFalse(any(" X" in command or " Y" in command for command in sent_commands))


class TestProbeConfigAction(unittest.TestCase):
    def test_probe_config_read(self):
        profile = {
            "settings": {"$6": "1"},
            "probe": {"block_height": 15.0, "probe_feed": 40.0, "retract_height": 2.0},
        }
        with patch("RouterKing.ai.actions.grbl_load_machine_profile", return_value=(profile, "/tmp/machine_profile.json")):
            result = _action_machine_probe_config({"type": "machine_probe_config"}, {})

        self.assertIsInstance(result, dict)
        self.assertEqual(result["data"]["probe"]["block_height"], 15.0)
        self.assertEqual(result["data"]["probe"]["probe_feed"], 40.0)
        self.assertEqual(result["data"]["probe"]["retract_height"], 2.0)
        self.assertEqual(result["data"]["probe_pin_invert"], True)

    def test_probe_config_update(self):
        profile = {"settings": {"$6": "0"}, "probe": {"block_height": 12.0, "probe_feed": 50.0, "retract_height": 3.0}}
        saved = {}

        def _save(payload, path):
            saved["payload"] = payload
            return path or "/tmp/machine_profile.json"

        with patch("RouterKing.ai.actions.grbl_load_machine_profile", return_value=(profile, "/tmp/machine_profile.json")):
            with patch("RouterKing.ai.actions.grbl_save_machine_profile", side_effect=_save):
                result = _action_machine_probe_config(
                    {
                        "type": "machine_probe_config",
                        "probe_feed": 35.0,
                        "retract": 1.5,
                    },
                    {},
                )

        self.assertIsInstance(result, dict)
        self.assertEqual(saved["payload"]["probe"]["probe_feed"], 35.0)
        self.assertEqual(saved["payload"]["probe"]["retract_height"], 1.5)
        self.assertEqual(result["data"]["probe"]["probe_feed"], 35.0)


if __name__ == "__main__":
    unittest.main()
