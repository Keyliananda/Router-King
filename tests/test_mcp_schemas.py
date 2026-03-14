import unittest

from mcp.server.schemas import ActionDefinition, coerce_action, make_response, normalize_actions_payload


class TestMcpSchemas(unittest.TestCase):
    def test_make_response_has_expected_shape(self):
        response = make_response(True, "ok", data={"value": 1}, errors=["warn"])
        self.assertEqual(
            response,
            {
                "success": True,
                "message": "ok",
                "data": {"value": 1},
                "errors": ["warn"],
            },
        )

    def test_normalize_actions_payload_accepts_actions_wrapper(self):
        actions, errors = normalize_actions_payload({"actions": [{"type": "create_sketch"}]})
        self.assertEqual(errors, [])
        self.assertEqual(actions, [{"type": "create_sketch"}])

    def test_coerce_action_requires_type(self):
        action, errors = coerce_action({"params": {}})
        self.assertEqual(action, {})
        self.assertEqual(errors, ["Action is missing a type."])


if __name__ == "__main__":
    unittest.main()

