#!/usr/bin/env python3
"""
Unit tests for upwork_gmail_monitor.py

Tests Features #6-9 from feature_list.json:
- Feature #6: Gmail monitor can authenticate with Google account
- Feature #7: Gmail monitor can detect Upwork alert emails
- Feature #8: Gmail monitor can extract job URLs from Upwork alert emails
- Feature #9: Gmail monitor handles multiple jobs in single alert email

Run with: python executions/test_upwork_gmail_monitor.py
"""

import sys
import os
import unittest

# Add executions to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from upwork_gmail_monitor import (
    extract_job_urls,
    extract_job_id,
    is_upwork_alert_email,
    extract_jobs_from_emails,
    GmailAuth,
    SAMPLE_UPWORK_EMAIL_BODY,
    SAMPLE_UPWORK_DIGEST_BODY
)


class TestFeature6_GmailAuthentication(unittest.TestCase):
    """Feature #6: Gmail monitor can authenticate with Google account"""

    def test_gmail_auth_class_exists(self):
        """GmailAuth class should exist and be importable"""
        self.assertIsNotNone(GmailAuth)

    def test_gmail_auth_finds_token_paths(self):
        """Step 2: GmailAuth can find token.json paths"""
        auth = GmailAuth()
        # Should have a token path configured
        self.assertIsNotNone(auth.token_path)
        self.assertTrue(auth.token_path.endswith('token.json'))

    def test_gmail_auth_has_readonly_scope(self):
        """Step 3: Default scopes include gmail.readonly"""
        auth = GmailAuth()
        has_readonly = any('readonly' in scope for scope in auth.scopes)
        self.assertTrue(has_readonly, "Should have gmail.readonly scope")

    def test_verify_scopes_method_exists(self):
        """Step 4: verify_scopes method exists for checking token"""
        auth = GmailAuth()
        self.assertTrue(hasattr(auth, 'verify_scopes'))
        # Method should return tuple of (bool, list)
        result = auth.verify_scopes()
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)


class TestFeature7_UpworkEmailDetection(unittest.TestCase):
    """Feature #7: Gmail monitor can detect Upwork alert emails"""

    def test_detects_upwork_job_alert(self):
        """Step 3: Verify email is detected by subject pattern"""
        test_cases = [
            ("notifications@upwork.com", "New job that matches your skills", True),
            ("notifications@upwork.com", "Job Alert: 5 new jobs for you", True),
            ("notifications@upwork.com", "Jobs matching your profile", True),
            ("donotreply@upwork.com", "Recommended jobs for you", True),
            ("upwork.com", "New job invitation", True),
        ]

        for from_addr, subject, expected in test_cases:
            result = is_upwork_alert_email(from_addr, subject)
            self.assertEqual(result, expected,
                f"Failed for from='{from_addr}' subject='{subject}'")

    def test_rejects_non_upwork_emails(self):
        """Should reject emails not from Upwork"""
        test_cases = [
            ("spam@example.com", "New job opportunity", False),
            ("jobs@linkedin.com", "New job alert", False),
            ("noreply@indeed.com", "Jobs for you", False),
        ]

        for from_addr, subject, expected in test_cases:
            result = is_upwork_alert_email(from_addr, subject)
            self.assertEqual(result, expected,
                f"Should reject from='{from_addr}'")

    def test_rejects_non_job_upwork_emails(self):
        """Should reject Upwork emails that aren't job alerts"""
        test_cases = [
            ("notifications@upwork.com", "Your weekly earnings summary", False),
            ("notifications@upwork.com", "Payment received", False),
            ("notifications@upwork.com", "Contract ended", False),
        ]

        for from_addr, subject, expected in test_cases:
            result = is_upwork_alert_email(from_addr, subject)
            self.assertEqual(result, expected,
                f"Should reject subject='{subject}'")


class TestFeature8_URLExtraction(unittest.TestCase):
    """Feature #8: Gmail monitor can extract job URLs from Upwork alert emails"""

    def test_extracts_job_urls(self):
        """Step 2: Run URL extraction logic"""
        urls = extract_job_urls(SAMPLE_UPWORK_EMAIL_BODY)
        self.assertGreater(len(urls), 0, "Should extract at least one URL")

    def test_url_is_correctly_parsed(self):
        """Step 3: Verify job URL is correctly parsed"""
        urls = extract_job_urls(SAMPLE_UPWORK_EMAIL_BODY)
        for url in urls:
            self.assertTrue(
                url.startswith("https://www.upwork.com/") or
                url.startswith("http://www.upwork.com/"),
                f"URL should be valid Upwork URL: {url}"
            )
            self.assertIn("/jobs/", url, f"URL should contain /jobs/: {url}")

    def test_job_id_extracted_from_url(self):
        """Step 4: Verify job ID is extracted from URL"""
        urls = extract_job_urls(SAMPLE_UPWORK_EMAIL_BODY)
        for url in urls:
            job_id = extract_job_id(url)
            self.assertIsNotNone(job_id, f"Should extract ID from {url}")
            self.assertTrue(job_id.startswith("~"),
                f"Job ID should start with ~: {job_id}")

    def test_handles_different_url_formats(self):
        """Should handle various Upwork URL formats"""
        test_urls = [
            ("https://www.upwork.com/jobs/~01abc123", "~01abc123"),
            ("https://www.upwork.com/ab/jobs/~02def456", "~02def456"),
            ("https://upwork.com/jobs/~03ghi789", "~03ghi789"),
            ("http://www.upwork.com/jobs/~04jkl012", "~04jkl012"),
        ]

        for url, expected_id in test_urls:
            extracted = extract_job_id(url)
            self.assertEqual(extracted, expected_id,
                f"URL {url} should give ID {expected_id}, got {extracted}")


class TestFeature9_MultipleJobsInEmail(unittest.TestCase):
    """Feature #9: Gmail monitor handles multiple jobs in single alert email"""

    def test_extracts_multiple_urls(self):
        """Step 3: Verify all 5 job URLs are extracted from digest"""
        urls = extract_job_urls(SAMPLE_UPWORK_DIGEST_BODY)
        self.assertEqual(len(urls), 5, "Should extract 5 URLs from digest email")

    def test_all_job_ids_unique(self):
        """Step 4: Verify all 5 job IDs are unique"""
        urls = extract_job_urls(SAMPLE_UPWORK_DIGEST_BODY)
        job_ids = [extract_job_id(url) for url in urls]

        # All should be valid
        for job_id in job_ids:
            self.assertIsNotNone(job_id, "All job IDs should be valid")

        # All should be unique
        unique_ids = set(job_ids)
        self.assertEqual(len(job_ids), len(unique_ids),
            "All job IDs should be unique")

    def test_url_deduplication(self):
        """Duplicate URLs in email should be deduplicated"""
        text_with_dupes = """
        https://www.upwork.com/jobs/~01abc123
        https://www.upwork.com/jobs/~01abc123/
        https://www.upwork.com/jobs/~01abc123
        https://www.upwork.com/jobs/~02def456
        """
        urls = extract_job_urls(text_with_dupes)
        self.assertEqual(len(urls), 2, "Should deduplicate to 2 unique URLs")

    def test_extract_jobs_from_emails_structure(self):
        """extract_jobs_from_emails returns proper job structure"""
        mock_emails = [{
            "id": "msg123",
            "subject": "New jobs for you",
            "date": "2024-01-18",
            "body": SAMPLE_UPWORK_DIGEST_BODY
        }]

        jobs = extract_jobs_from_emails(mock_emails)

        self.assertEqual(len(jobs), 5, "Should extract 5 jobs")

        # Check structure of first job
        job = jobs[0]
        self.assertIn("job_id", job)
        self.assertIn("url", job)
        self.assertIn("source", job)
        self.assertEqual(job["source"], "gmail")
        self.assertIn("email_id", job)
        self.assertEqual(job["email_id"], "msg123")


class TestEdgeCases(unittest.TestCase):
    """Additional edge case tests"""

    def test_empty_body(self):
        """Should handle empty email body"""
        urls = extract_job_urls("")
        self.assertEqual(len(urls), 0)

    def test_no_urls_in_body(self):
        """Should handle body with no Upwork URLs"""
        urls = extract_job_urls("This is a regular email with no job links.")
        self.assertEqual(len(urls), 0)

    def test_non_upwork_urls_ignored(self):
        """Should ignore non-Upwork URLs"""
        text = """
        Check out https://www.google.com
        And https://www.linkedin.com/jobs/123
        But also https://www.upwork.com/jobs/~01abc123
        """
        urls = extract_job_urls(text)
        self.assertEqual(len(urls), 1)
        self.assertIn("upwork.com", urls[0])

    def test_extract_jobs_deduplicates_across_emails(self):
        """Same job in multiple emails should be deduplicated"""
        mock_emails = [
            {"id": "msg1", "subject": "Jobs", "date": "2024-01-18",
             "body": "https://www.upwork.com/jobs/~01abc123"},
            {"id": "msg2", "subject": "More Jobs", "date": "2024-01-18",
             "body": "https://www.upwork.com/jobs/~01abc123"},  # Same job
        ]

        jobs = extract_jobs_from_emails(mock_emails)
        self.assertEqual(len(jobs), 1, "Should deduplicate same job across emails")


def run_tests():
    """Run all tests and return success status."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestFeature6_GmailAuthentication))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature7_UpworkEmailDetection))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature8_URLExtraction))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature9_MultipleJobsInEmail))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return len(result.failures) == 0 and len(result.errors) == 0


if __name__ == "__main__":
    success = run_tests()

    if success:
        print("\n" + "=" * 60)
        print("ALL GMAIL MONITOR TESTS PASSED!")
        print("=" * 60)
        print("\nFeatures verified:")
        print("  - Feature #6: Gmail authentication structure")
        print("  - Feature #7: Upwork email detection")
        print("  - Feature #8: Job URL extraction")
        print("  - Feature #9: Multiple jobs in digest emails")
        sys.exit(0)
    else:
        print("\n" + "=" * 60)
        print("SOME TESTS FAILED")
        print("=" * 60)
        sys.exit(1)
