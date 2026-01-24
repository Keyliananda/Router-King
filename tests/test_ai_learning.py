import tempfile
import unittest
from unittest.mock import patch

from RouterKing.ai.results import AnalysisIssue
import RouterKing.ai.learning as learning


class FakeApp:
    def __init__(self, base_dir):
        self._base_dir = base_dir

    def getUserAppDataDir(self):
        return self._base_dir


class TestAiLearning(unittest.TestCase):
    def test_record_feedback_and_weight(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_app = FakeApp(tmpdir)
            with patch.object(learning, "App", fake_app):
                weight = learning.record_feedback("optimization.spline_preview", True)
                self.assertGreater(weight, 0.4)
                stored = learning.get_weight("optimization.spline_preview")
                self.assertAlmostEqual(stored, weight)

    def test_apply_issue_weights(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_app = FakeApp(tmpdir)
            with patch.object(learning, "App", fake_app):
                learning.record_feedback("analysis.spline_poles", True)
                issues = [
                    AnalysisIssue(
                        severity="warning",
                        message="Test",
                        suggestion="Test",
                        feedback_key="analysis.spline_poles",
                    )
                ]
                weighted = learning.apply_issue_weights(issues)
                self.assertEqual(len(weighted), 1)
                self.assertGreater(weighted[0].weight, 0.4)


if __name__ == "__main__":
    unittest.main()
