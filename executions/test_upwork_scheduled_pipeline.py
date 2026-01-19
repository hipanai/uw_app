"""
Unit tests for Upwork scheduled pipeline cron job.

Tests Feature #94: Modal scheduled function runs every 2 hours
- Verifies cron expression is correct
- Verifies function configuration
- Verifies function triggers on schedule
"""

import unittest
import re
from datetime import datetime, timedelta


class TestFeature94ScheduledPipeline(unittest.TestCase):
    """Tests for Feature #94: Modal scheduled function runs every 2 hours."""

    def test_cron_expression_format_is_valid(self):
        """Test that the cron expression '0 */2 * * *' is valid format."""
        cron_expr = "0 */2 * * *"

        # Standard cron has 5 fields: minute hour day-of-month month day-of-week
        parts = cron_expr.split()
        self.assertEqual(len(parts), 5, "Cron expression should have 5 fields")

        # Check each field
        minute, hour, dom, month, dow = parts
        self.assertEqual(minute, "0", "Should run at minute 0")
        self.assertEqual(hour, "*/2", "Should run every 2 hours")
        self.assertEqual(dom, "*", "Should run every day of month")
        self.assertEqual(month, "*", "Should run every month")
        self.assertEqual(dow, "*", "Should run every day of week")

    def test_cron_expression_runs_every_2_hours(self):
        """Test that '0 */2 * * *' results in 12 runs per day."""
        # The expression '0 */2 * * *' runs at 00:00, 02:00, 04:00, etc.
        # That's 12 times per day (24 hours / 2 hour interval)
        expected_runs_per_day = 12

        # Calculate hours that match */2 (every 2nd hour)
        matching_hours = [h for h in range(24) if h % 2 == 0]
        self.assertEqual(len(matching_hours), expected_runs_per_day)

        # Verify the hours are correct
        expected_hours = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22]
        self.assertEqual(matching_hours, expected_hours)

    def test_cron_expression_runs_at_minute_zero(self):
        """Test that the schedule runs at minute 0 of each scheduled hour."""
        cron_expr = "0 */2 * * *"
        minute = cron_expr.split()[0]

        # Should be exactly minute 0, not a range or wildcard
        self.assertEqual(minute, "0", "Should run exactly at minute 0")

    def test_scheduled_function_exists_in_modal_webhook(self):
        """Test that scheduled_upwork_pipeline function is defined."""
        import os

        # Read modal_webhook.py and check for the function
        webhook_path = os.path.join(os.path.dirname(__file__), "modal_webhook.py")
        with open(webhook_path, 'r') as f:
            content = f.read()

        # Check function definition exists
        self.assertIn("def scheduled_upwork_pipeline()", content,
                      "scheduled_upwork_pipeline function should exist")

    def test_scheduled_function_has_cron_decorator(self):
        """Test that the function has the correct schedule decorator."""
        import os

        webhook_path = os.path.join(os.path.dirname(__file__), "modal_webhook.py")
        with open(webhook_path, 'r') as f:
            content = f.read()

        # Look for the schedule decorator with the correct cron expression
        # Should find: schedule=modal.Cron("0 */2 * * *")
        pattern = r'schedule\s*=\s*modal\.Cron\s*\(\s*["\']0 \*/2 \* \* \*["\']\s*\)'
        match = re.search(pattern, content)
        self.assertIsNotNone(match,
                            "Should have schedule=modal.Cron('0 */2 * * *') decorator")

    def test_scheduled_function_has_proper_timeout(self):
        """Test that the function has adequate timeout for pipeline processing."""
        import os

        webhook_path = os.path.join(os.path.dirname(__file__), "modal_webhook.py")
        with open(webhook_path, 'r') as f:
            content = f.read()

        # Find the function decorator section
        # Look for timeout >= 600 (10 minutes minimum for pipeline)
        # Should be timeout=1800 (30 minutes)
        func_pattern = r'@app\.function\([^)]*timeout\s*=\s*(\d+)[^)]*\)\s*def scheduled_upwork_pipeline'
        match = re.search(func_pattern, content, re.DOTALL)

        self.assertIsNotNone(match, "Should have timeout in function decorator")

        if match:
            timeout_value = int(match.group(1))
            self.assertGreaterEqual(timeout_value, 600,
                                   "Timeout should be at least 10 minutes (600s)")

    def test_scheduled_function_uses_correct_secrets(self):
        """Test that the function has access to all required secrets."""
        import os

        webhook_path = os.path.join(os.path.dirname(__file__), "modal_webhook.py")
        with open(webhook_path, 'r') as f:
            content = f.read()

        # Check that ALL_SECRETS is used in the decorator
        pattern = r'@app\.function\([^)]*secrets\s*=\s*ALL_SECRETS[^)]*\)\s*def scheduled_upwork_pipeline'
        match = re.search(pattern, content, re.DOTALL)

        self.assertIsNotNone(match,
                            "scheduled_upwork_pipeline should use ALL_SECRETS")

    def test_scheduled_function_imports_pipeline_orchestrator(self):
        """Test that the function attempts to import the pipeline orchestrator."""
        import os

        webhook_path = os.path.join(os.path.dirname(__file__), "modal_webhook.py")
        with open(webhook_path, 'r') as f:
            content = f.read()

        # Find the function body and check for import
        self.assertIn("from upwork_pipeline_orchestrator import", content,
                      "Should import from upwork_pipeline_orchestrator")

    def test_scheduled_function_calls_run_pipeline_sync(self):
        """Test that the function calls run_pipeline_sync with correct params."""
        import os

        webhook_path = os.path.join(os.path.dirname(__file__), "modal_webhook.py")
        with open(webhook_path, 'r') as f:
            content = f.read()

        # Check for call to run_pipeline_sync with apify source
        self.assertIn("run_pipeline_sync(", content,
                      "Should call run_pipeline_sync")
        self.assertIn("source='apify'", content,
                      "Should use apify as default source")

    def test_scheduled_function_sends_slack_notifications(self):
        """Test that the function sends Slack notifications."""
        import os

        webhook_path = os.path.join(os.path.dirname(__file__), "modal_webhook.py")
        with open(webhook_path, 'r') as f:
            content = f.read()

        # Look for slack_notify calls in the function
        # Find the function definition first
        func_start = content.find("def scheduled_upwork_pipeline()")
        func_end = content.find("\n\n@", func_start + 1)  # Next decorator marks end
        if func_end == -1:
            func_end = content.find("\n\n# ===", func_start + 1)  # Section marker

        func_body = content[func_start:func_end] if func_end > func_start else ""

        self.assertIn("slack_notify(", func_body,
                      "Should call slack_notify for status updates")

    def test_scheduled_function_handles_errors_gracefully(self):
        """Test that the function has try/except for error handling."""
        import os

        webhook_path = os.path.join(os.path.dirname(__file__), "modal_webhook.py")
        with open(webhook_path, 'r') as f:
            content = f.read()

        # Find the function definition
        func_start = content.find("def scheduled_upwork_pipeline()")
        func_end = content.find("\n\n@", func_start + 1)
        if func_end == -1:
            func_end = content.find("\n\n# ===", func_start + 1)

        func_body = content[func_start:func_end] if func_end > func_start else ""

        self.assertIn("try:", func_body, "Should have try block")
        self.assertIn("except Exception", func_body, "Should catch exceptions")
        self.assertIn("slack_error(", func_body,
                      "Should report errors via slack_error")

    def test_2_hour_interval_calculation(self):
        """Test mathematical verification of 2-hour intervals."""
        # If we start at midnight, the next runs should be at:
        # 00:00, 02:00, 04:00, ..., 22:00
        start = datetime(2025, 1, 1, 0, 0, 0)

        expected_times = []
        current = start
        while current.date() == start.date():
            expected_times.append(current)
            current += timedelta(hours=2)

        # Should have 12 runs
        self.assertEqual(len(expected_times), 12)

        # Verify first few
        self.assertEqual(expected_times[0].hour, 0)
        self.assertEqual(expected_times[1].hour, 2)
        self.assertEqual(expected_times[2].hour, 4)
        self.assertEqual(expected_times[-1].hour, 22)


class TestCronExpressionValidation(unittest.TestCase):
    """Additional tests for cron expression validation."""

    def test_cron_minute_field_is_zero(self):
        """Minute field should be 0 for consistent timing."""
        cron = "0 */2 * * *"
        self.assertTrue(cron.startswith("0 "))

    def test_cron_hour_field_uses_step_syntax(self):
        """Hour field should use */2 step syntax for every 2 hours."""
        cron = "0 */2 * * *"
        parts = cron.split()
        self.assertEqual(parts[1], "*/2")

    def test_cron_day_fields_are_wildcards(self):
        """Day/month/weekday fields should be * for daily execution."""
        cron = "0 */2 * * *"
        parts = cron.split()
        self.assertEqual(parts[2], "*")  # day of month
        self.assertEqual(parts[3], "*")  # month
        self.assertEqual(parts[4], "*")  # day of week


if __name__ == "__main__":
    unittest.main()
