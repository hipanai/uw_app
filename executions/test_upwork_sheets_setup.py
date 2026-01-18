#!/usr/bin/env python3
"""
Unit tests for upwork_sheets_setup.py

These tests verify the column definitions match the app_spec.txt requirements.
Run with: python executions/test_upwork_sheets_setup.py
"""

import sys
import unittest

# Import the module to test
from upwork_sheets_setup import PIPELINE_COLUMNS, PROCESSED_IDS_COLUMNS


class TestSheetColumns(unittest.TestCase):
    """Test that column definitions match app_spec.txt requirements."""

    def test_pipeline_has_job_id_as_primary_key(self):
        """Feature #1 Step 2: job_id column exists as primary key"""
        self.assertEqual(PIPELINE_COLUMNS[0], "job_id",
            "job_id should be first column (primary key)")

    def test_pipeline_has_basic_fields(self):
        """Feature #1 Step 3: source, status, title, url, description columns exist"""
        required = ["source", "status", "title", "url", "description"]
        for col in required:
            self.assertIn(col, PIPELINE_COLUMNS,
                f"Pipeline should have {col} column")

    def test_pipeline_has_attachment_and_budget_fields(self):
        """Feature #1 Step 4: attachments, budget_type, budget_min, budget_max columns exist"""
        required = ["attachments", "budget_type", "budget_min", "budget_max"]
        for col in required:
            self.assertIn(col, PIPELINE_COLUMNS,
                f"Pipeline should have {col} column")

    def test_pipeline_has_client_fields(self):
        """Feature #1 Step 5: client_country, client_spent, client_hires, payment_verified"""
        required = ["client_country", "client_spent", "client_hires", "payment_verified"]
        for col in required:
            self.assertIn(col, PIPELINE_COLUMNS,
                f"Pipeline should have {col} column")

    def test_pipeline_has_fit_and_proposal_fields(self):
        """Feature #1 Step 6: fit_score, fit_reasoning, proposal_doc_url, proposal_text"""
        required = ["fit_score", "fit_reasoning", "proposal_doc_url", "proposal_text"]
        for col in required:
            self.assertIn(col, PIPELINE_COLUMNS,
                f"Pipeline should have {col} column")

    def test_pipeline_has_deliverable_fields(self):
        """Feature #1 Step 7: video_url, pdf_url, boost_decision, boost_reasoning"""
        required = ["video_url", "pdf_url", "boost_decision", "boost_reasoning"]
        for col in required:
            self.assertIn(col, PIPELINE_COLUMNS,
                f"Pipeline should have {col} column")

    def test_pipeline_has_submission_fields(self):
        """Feature #1 Step 8: pricing_proposed, slack_message_ts, approved_at, submitted_at, error_log"""
        required = ["pricing_proposed", "slack_message_ts", "approved_at", "submitted_at", "error_log"]
        for col in required:
            self.assertIn(col, PIPELINE_COLUMNS,
                f"Pipeline should have {col} column")

    def test_processed_ids_has_job_id(self):
        """Feature #2 Step 2: job_id column exists"""
        self.assertIn("job_id", PROCESSED_IDS_COLUMNS,
            "Processed IDs should have job_id column")

    def test_processed_ids_has_first_seen(self):
        """Feature #2 Step 3: first_seen timestamp column exists"""
        self.assertIn("first_seen", PROCESSED_IDS_COLUMNS,
            "Processed IDs should have first_seen column")

    def test_processed_ids_has_source(self):
        """Feature #2 Step 4: source column exists"""
        self.assertIn("source", PROCESSED_IDS_COLUMNS,
            "Processed IDs should have source column")

    def test_processed_ids_minimal_columns(self):
        """Processed IDs should have exactly 3 required columns"""
        required = ["job_id", "first_seen", "source"]
        for col in required:
            self.assertIn(col, PROCESSED_IDS_COLUMNS,
                f"Processed IDs should have {col} column")


class TestColumnCounts(unittest.TestCase):
    """Test column counts are reasonable."""

    def test_pipeline_has_sufficient_columns(self):
        """Pipeline should have at least 20 columns per spec"""
        self.assertGreaterEqual(len(PIPELINE_COLUMNS), 20,
            "Pipeline should have at least 20 columns")

    def test_processed_ids_is_minimal(self):
        """Processed IDs should be minimal (3-5 columns)"""
        self.assertLessEqual(len(PROCESSED_IDS_COLUMNS), 5,
            "Processed IDs should have 5 or fewer columns (minimal for dedup)")


def run_tests():
    """Run all tests and return success status."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestSheetColumns))
    suite.addTests(loader.loadTestsFromTestCase(TestColumnCounts))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Return success status
    return len(result.failures) == 0 and len(result.errors) == 0


if __name__ == "__main__":
    success = run_tests()

    if success:
        print("\n" + "=" * 50)
        print("ALL TESTS PASSED!")
        print("=" * 50)
        print("\nColumn definitions match app_spec.txt requirements.")
        print("\nTo create actual sheets, run:")
        print("  python executions/upwork_sheets_setup.py --create")
        print("\n(Requires Google OAuth credentials in config/credentials.json)")
        sys.exit(0)
    else:
        print("\n" + "=" * 50)
        print("SOME TESTS FAILED")
        print("=" * 50)
        sys.exit(1)
