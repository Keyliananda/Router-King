"""Tests for machine G-code pre-stream validation."""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from RouterKing.ai.actions import _action_machine_stream_gcode, _action_machine_validate_gcode


class _FakeSender:
    def __init__(self, *, status=None, settings=None, coordinate_lines=None, connected=True, streaming=False):
        self._status = status or {}
        self._settings = settings or {
            "$110": "2000",
            "$111": "2000",
            "$112": "500",
            "$130": "300",
            "$131": "380",
            "$132": "50",
            "$23": "3",
            "$27": "3",
            "$32": "0",
        }
        self._coordinate_lines = coordinate_lines or []
        self._connected = connected
        self._streaming = streaming
        self.started_lines = None

    def is_connected(self):
        return self._connected

    def is_streaming(self):
        return self._streaming

    def poll(self):
        return []

    def request_status(self):
        return None

    def get_status(self):
        return dict(self._status)

    def send_and_collect(self, command, timeout=2.0):
        if command == "$#":
            return list(self._coordinate_lines)
        if command != "$$":
            return []
        return [f"{key}={value}" for key, value in self._settings.items()]

    def start_stream(self, lines):
        self.started_lines = list(lines)


class TestMachineGcodeValidator(unittest.TestCase):
    def test_stream_rejects_line_outside_z_limit(self):
        sender = _FakeSender(
            status={
                "state": "Idle",
                "WPos": "0.000,0.000,0.000",
                "WCO": "-297.000,-377.000,-3.000",
            },
        )
        gcode = "G90 G21\nG0 Z11\nG1 X-10 Y-10 Z-1"

        with patch("RouterKing.ai.actions._get_sender", return_value=sender):
            message = _action_machine_stream_gcode(
                {"type": "machine_stream_gcode", "gcode": gcode, "confirm": True},
                {},
            )

        self.assertIn("validation failed", message)
        self.assertIn("line 2", message)
        self.assertIn("Z=", message)
        self.assertIsNone(sender.started_lines)

    def test_stream_starts_when_validation_passes(self):
        sender = _FakeSender(
            status={
                "state": "Idle",
                "WPos": "0.000,0.000,0.000",
                "WCO": "-297.000,-377.000,-3.000",
            },
        )
        gcode = "G90 G21\nG0 Z2\nG1 X-1 Y-1 Z-1 F300"

        with patch("RouterKing.ai.actions._get_sender", return_value=sender):
            message = _action_machine_stream_gcode(
                {"type": "machine_stream_gcode", "gcode": gcode, "confirm": True},
                {},
            )

        self.assertIn("Streaming started", message)
        self.assertEqual(sender.started_lines, ["G90 G21", "G0 Z2", "G1 X-1 Y-1 Z-1 F300"])

    def test_stream_uses_live_g54_from_coordinate_parameters_over_stale_profile(self):
        sender = _FakeSender(
            status={
                "state": "Idle",
                "MPos": "-297.000,-377.000,-3.000",
            },
            coordinate_lines=[
                "[G54:-150.000,-190.000,-25.238]",
                "[G92:0.000,0.000,0.000]",
                "[TLO:0.000]",
            ],
        )
        gcode = "\n".join(
            [
                "G90 G21",
                "G54",
                "G0 Z9",
                "G0 X112.5 Y-67",
                "G1 Z-2 F300",
            ]
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
            json.dump(
                {
                    "settings": sender._settings,
                    "work_offset": {"x": -297, "y": -347, "z": -3},
                    "work_position": {"x": 0, "y": 0, "z": 0},
                },
                handle,
            )
            profile_path = handle.name

        try:
            with patch("RouterKing.ai.actions._get_sender", return_value=sender):
                message = _action_machine_stream_gcode(
                    {
                        "type": "machine_stream_gcode",
                        "gcode": gcode,
                        "machine_profile_path": profile_path,
                        "confirm": True,
                    },
                    {},
                )
        finally:
            os.unlink(profile_path)

        self.assertIn("Streaming started", message)
        self.assertEqual(sender.started_lines, gcode.splitlines())

    def test_validate_reports_live_coordinate_parameter_offset_source(self):
        sender = _FakeSender(
            status={
                "state": "Idle",
                "MPos": "-297.000,-377.000,-3.000",
            },
            coordinate_lines=["[G54:-150.000,-190.000,-25.238]", "[G92:0.000,0.000,0.000]"],
        )
        gcode = "G90 G21\nG54\nG0 Z9\nG0 X112.5 Y-67\nG1 Z-2 F300"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
            json.dump(
                {
                    "settings": sender._settings,
                    "work_offset": {"x": -297, "y": -347, "z": -3},
                    "work_position": {"x": 0, "y": 0, "z": 0},
                },
                handle,
            )
            profile_path = handle.name

        try:
            with patch("RouterKing.ai.actions._get_sender", return_value=sender):
                message = _action_machine_validate_gcode(
                    {
                        "type": "machine_validate_gcode",
                        "gcode": gcode,
                        "machine_profile_path": profile_path,
                    },
                    {},
                )
        finally:
            os.unlink(profile_path)

        self.assertIsInstance(message, dict)
        self.assertTrue(message["data"]["valid"])
        self.assertEqual(message["data"]["offset_source"], "status.WCO")
        self.assertEqual(message["data"]["work_offset"], {"x": -150.0, "y": -190.0, "z": -25.238})

    def test_validate_uses_machine_profile_when_controller_unavailable(self):
        sender = _FakeSender(connected=False)
        gcode = "G90 G21\nG0 X0 Y0 Z2\nG1 X-1 Y-1 Z-1 F300"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
            json.dump(
                {
                    "$110": 2000,
                    "$111": 2000,
                    "$112": 500,
                    "$130": 300,
                    "$131": 380,
                    "$132": 50,
                    "$27": 3,
                    "$32": 0,
                    "work_offset": {"x": -297, "y": -377, "z": -3},
                    "work_position": {"x": 0, "y": 0, "z": 0},
                },
                handle,
            )
            profile_path = handle.name

        try:
            with patch("RouterKing.ai.actions._get_sender", return_value=sender):
                message = _action_machine_validate_gcode(
                    {
                        "type": "machine_validate_gcode",
                        "gcode": gcode,
                        "machine_profile_path": profile_path,
                    },
                    {},
                )
        finally:
            os.unlink(profile_path)

        self.assertIsInstance(message, dict)
        self.assertTrue(message.get("data", {}).get("valid"))
        self.assertIn("G-code validation passed", message.get("message", ""))


if __name__ == "__main__":
    unittest.main()
