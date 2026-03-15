"""Tests for structured GRBL machine status data."""

import unittest

from RouterKing.ai.actions import _parse_position, _parse_feed_speed


class TestParsePosition(unittest.TestCase):
    def test_parses_valid_position(self):
        result = _parse_position("1.000,2.500,3.750")
        self.assertEqual(result, {"x": 1.0, "y": 2.5, "z": 3.75})

    def test_returns_none_for_none(self):
        self.assertIsNone(_parse_position(None))

    def test_returns_none_for_empty(self):
        self.assertIsNone(_parse_position(""))

    def test_returns_raw_for_bad_format(self):
        result = _parse_position("1.0,2.0")
        self.assertEqual(result, {"raw": "1.0,2.0"})

    def test_returns_raw_for_non_numeric(self):
        result = _parse_position("a,b,c")
        self.assertEqual(result, {"raw": "a,b,c"})

    def test_negative_values(self):
        result = _parse_position("-10.5,0.000,-3.2")
        self.assertEqual(result, {"x": -10.5, "y": 0.0, "z": -3.2})


class TestParseFeedSpeed(unittest.TestCase):
    def test_parses_feed_and_spindle(self):
        result = _parse_feed_speed("500,12000")
        self.assertEqual(result, {"feed": 500.0, "spindle": 12000.0})

    def test_returns_none_for_none(self):
        self.assertIsNone(_parse_feed_speed(None))

    def test_returns_none_for_empty(self):
        self.assertIsNone(_parse_feed_speed(""))

    def test_feed_only(self):
        result = _parse_feed_speed("300")
        self.assertEqual(result, {"feed": 300.0})

    def test_zero_values(self):
        result = _parse_feed_speed("0,0")
        self.assertEqual(result, {"feed": 0.0, "spindle": 0.0})


class TestMachineStatusThroughBridge(unittest.TestCase):
    """Test that machine_request_status returns structured data through the bridge."""

    def test_structured_status_in_result_data(self):
        from RouterKing.mcp.bridge import RouterKingBridge

        status_response = {
            "messages": ["Status requested (state=Idle)."],
            "errors": [],
            "data": {
                "machine_status": {
                    "state": "Idle",
                    "machine_position": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "work_position": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "feed_speed": {"feed": 0.0, "spindle": 0.0},
                    "connected": True,
                    "streaming": False,
                    "paused": False,
                    "stream_progress": {"sent": 0, "acked": 0, "total": 0},
                    "last_error": None,
                    "raw": {"state": "Idle", "MPos": "0.000,0.000,0.000", "FS": "0,0"},
                }
            },
        }

        def executor(actions):
            return status_response

        bridge = RouterKingBridge(
            action_executor=executor,
            context_module=type(
                "Ctx", (), {
                    "get_scene_info": staticmethod(lambda: {
                        "document": None, "object_count": 0, "objects": [],
                        "selection": [], "selection_count": 0, "warnings": [],
                    }),
                },
            ),
            screenshot_module=type(
                "Ss", (), {
                    "capture_view": staticmethod(lambda output_path=None: {
                        "available": False, "path": None, "message": "no screenshot",
                    }),
                },
            ),
            transaction_factory=lambda: type(
                "Tx", (), {
                    "open": lambda self, name="": False,
                    "commit": lambda self: False,
                    "abort": lambda self: False,
                },
            )(),
        )

        response = bridge.apply_actions(
            {"actions": [{"type": "machine_request_status", "confirm": True, "reason": "test"}]},
            include_context=False,
        )
        self.assertTrue(response["success"])
        result = response["data"]["results"][0]
        self.assertIn("data", result)
        self.assertIn("machine_status", result["data"])
        status = result["data"]["machine_status"]
        self.assertEqual(status["state"], "Idle")
        self.assertEqual(status["machine_position"], {"x": 0.0, "y": 0.0, "z": 0.0})
        self.assertEqual(status["feed_speed"]["feed"], 0.0)

    def test_string_response_has_no_data_key(self):
        """Actions returning plain strings should not have a data key."""
        from RouterKing.mcp.bridge import RouterKingBridge

        bridge = RouterKingBridge(
            action_executor=lambda actions: (["Box created."], []),
            context_module=type(
                "Ctx", (), {
                    "get_scene_info": staticmethod(lambda: {
                        "document": None, "object_count": 0, "objects": [],
                        "selection": [], "selection_count": 0, "warnings": [],
                    }),
                },
            ),
            screenshot_module=type(
                "Ss", (), {
                    "capture_view": staticmethod(lambda output_path=None: {
                        "available": False, "path": None, "message": "no screenshot",
                    }),
                },
            ),
            transaction_factory=lambda: type(
                "Tx", (), {
                    "open": lambda self, name="": True,
                    "commit": lambda self: True,
                    "abort": lambda self: True,
                },
            )(),
        )
        response = bridge.apply_actions(
            {"actions": [{"type": "create_part_box", "length": 10, "width": 20, "height": 5}]},
            include_context=False,
        )
        self.assertTrue(response["success"])
        result = response["data"]["results"][0]
        self.assertNotIn("data", result)


if __name__ == "__main__":
    unittest.main()
