import tempfile
import unittest
from unittest.mock import patch

from RouterKing.ai.results import AnalysisIssue, AnalysisResult
import RouterKing.ai.reporting as reporting


class FakeApp:
    def __init__(self, base_dir):
        self._base_dir = base_dir

    def getUserAppDataDir(self):
        return self._base_dir


class TestAiReporting(unittest.TestCase):
    def test_format_report_entry(self):
        result = AnalysisResult(
            summary="All good",
            stats={"edges": 3},
            issues=[AnalysisIssue(severity="info", message="Test issue")],
        )
        entry = reporting.format_report_entry("Analyze", result, details="detail")
        self.assertIn("Analyze", entry)
        self.assertIn("Summary: All good", entry)
        self.assertIn("Stats: edges=3", entry)
        self.assertIn("info: Test issue", entry)

    def test_append_load_clear_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_app = FakeApp(tmpdir)
            with patch.object(reporting, "App", fake_app):
                reporting.clear_report()
                entry = "Test entry\n"
                reporting.append_report(entry)
                loaded = reporting.load_report()
                self.assertIn("Test entry", loaded)
                reporting.clear_report()
                loaded_after = reporting.load_report()
                self.assertEqual(loaded_after, "")


if __name__ == "__main__":
    unittest.main()
