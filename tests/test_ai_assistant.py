import unittest

from RouterKing.ai.assistant import ask_assistant, AssistantContext


class TestAiAssistant(unittest.TestCase):
    def test_rule_based_pad_failure(self):
        messages = [{"role": "user", "content": "Warum schlaegt Pad fehl?"}]
        response = ask_assistant(
            messages,
            api_key="",
            allow_llm=False,
            context=AssistantContext(),
        )
        self.assertIn("Pad", response.text)
        self.assertFalse(response.used_llm)
        self.assertEqual(response.source, "rules")


if __name__ == "__main__":
    unittest.main()
