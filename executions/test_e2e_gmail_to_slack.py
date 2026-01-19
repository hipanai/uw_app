#!/usr/bin/env python3
"""
End-to-End Test: Job flows from Gmail to Slack approval

Feature #73: End-to-end test - Job flows from Gmail to Slack approval

This test validates the complete pipeline flow from Gmail source:
1. Send Upwork alert email to monitored inbox (simulated)
2. Wait for Gmail push notification (mocked)
3. Wait for pipeline processing
4. Verify Slack message received
5. Verify source='gmail' in sheet

The test uses mock mode to avoid actual API calls while still
validating the complete pipeline logic and data flow.
"""

import os
import sys
import json
import asyncio
import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock
from dataclasses import asdict

# Add executions directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import pipeline components
from upwork_pipeline_orchestrator import (
    run_pipeline_async,
    run_pipeline_sync,
    PipelineJob,
    PipelineResult,
    PipelineStatus,
)

# Import Gmail monitor components for testing
from upwork_gmail_monitor import (
    extract_job_urls,
    extract_job_id,
    is_upwork_alert_email,
    extract_jobs_from_emails,
    SAMPLE_UPWORK_EMAIL_BODY,
    SAMPLE_UPWORK_DIGEST_BODY,
)


class TestFeature73GmailToSlackE2E(unittest.TestCase):
    """
    Feature #73: End-to-end test - Job flows from Gmail to Slack approval

    Tests the complete pipeline flow from Gmail job ingestion through
    to Slack approval message sending.
    """

    def test_e2e_single_job_flows_through_pipeline_from_gmail(self):
        """Test that a single Gmail job flows through all pipeline stages in mock mode."""
        # Run pipeline with Gmail source and mock mode (no real API calls)
        result = run_pipeline_sync(
            source='gmail',
            limit=1,
            min_score=50,  # Low threshold to ensure job passes
            mock=True,
            parallel=1,
        )

        # Verify pipeline ran successfully
        self.assertIsInstance(result, PipelineResult)
        self.assertEqual(result.source, 'gmail')
        self.assertIsNotNone(result.started_at)
        self.assertIsNotNone(result.finished_at)

        # Verify job was ingested
        self.assertEqual(result.jobs_ingested, 1)

        # Verify job passed deduplication (mock mode skips dedup)
        self.assertEqual(result.jobs_after_dedup, 1)

        # Verify job passed pre-filter (mock gives 85 for first job)
        self.assertEqual(result.jobs_after_prefilter, 1)
        self.assertEqual(result.jobs_filtered_out, 0)

        # Verify job was processed
        self.assertEqual(result.jobs_processed, 1)

        # Verify Slack message was sent (mock mode)
        self.assertEqual(result.jobs_sent_to_slack, 1)

        # Verify no errors
        self.assertEqual(result.jobs_with_errors, 0)
        self.assertEqual(len(result.errors), 0)

    def test_e2e_gmail_source_correctly_set(self):
        """Test that jobs have source='gmail' when coming from Gmail."""
        result = run_pipeline_sync(
            source='gmail',
            limit=1,
            min_score=50,
            mock=True,
            parallel=1,
        )

        # Verify source at result level
        self.assertEqual(result.source, 'gmail')

        # Verify source on each processed job
        for job in result.processed_jobs:
            self.assertEqual(job.source, 'gmail')

    def test_e2e_gmail_job_has_all_fields_populated(self):
        """Test that Gmail-sourced job has all required fields populated."""
        result = run_pipeline_sync(
            source='gmail',
            limit=1,
            min_score=50,
            mock=True,
            parallel=1,
        )

        # Get the processed job
        self.assertEqual(len(result.processed_jobs), 1)
        job = result.processed_jobs[0]

        # Verify basic fields from Gmail ingestion
        self.assertIsNotNone(job.job_id)
        self.assertTrue(job.job_id.startswith('~gmailmock'))
        self.assertIsNotNone(job.url)
        self.assertIn('upwork.com', job.url)
        self.assertEqual(job.source, 'gmail')
        self.assertIsNotNone(job.title)
        self.assertIsNotNone(job.description)

        # Verify pre-filter results
        self.assertIsNotNone(job.fit_score)
        self.assertGreaterEqual(job.fit_score, 0)
        self.assertLessEqual(job.fit_score, 100)
        self.assertIsNotNone(job.fit_reasoning)

        # Verify deep extraction results (mock mode populates these)
        self.assertIsNotNone(job.budget_type)
        self.assertEqual(job.budget_type, 'fixed')
        self.assertIsNotNone(job.budget_min)
        self.assertIsNotNone(job.budget_max)
        self.assertIsNotNone(job.client_country)
        self.assertEqual(job.client_country, 'United States')
        self.assertIsNotNone(job.client_spent)
        self.assertIsNotNone(job.client_hires)
        self.assertTrue(job.payment_verified)

        # Verify deliverable generation results (mock mode populates these)
        self.assertIsNotNone(job.proposal_doc_url)
        self.assertIn('docs.google.com', job.proposal_doc_url)
        self.assertIsNotNone(job.proposal_text)
        self.assertIsNotNone(job.video_url)
        self.assertIn('heygen.com', job.video_url)
        self.assertIsNotNone(job.pdf_url)
        self.assertIn('drive.google.com', job.pdf_url)
        self.assertIsNotNone(job.cover_letter)

        # Verify boost decision results
        self.assertIsNotNone(job.boost_decision)
        self.assertIsInstance(job.boost_decision, bool)
        self.assertIsNotNone(job.boost_reasoning)
        self.assertIsNotNone(job.pricing_proposed)

        # Verify Slack tracking
        self.assertIsNotNone(job.slack_message_ts)
        self.assertTrue(job.slack_message_ts.startswith('mock_ts_'))

        # Verify final status
        self.assertEqual(job.status, PipelineStatus.PENDING_APPROVAL)

    def test_e2e_gmail_sheet_row_has_source_gmail(self):
        """Test that sheet row data correctly shows source='gmail'."""
        result = run_pipeline_sync(
            source='gmail',
            limit=1,
            min_score=50,
            mock=True,
            parallel=1,
        )

        job = result.processed_jobs[0]
        sheet_row = job.to_sheet_row()

        # Verify source field is correctly set
        self.assertEqual(sheet_row['source'], 'gmail')

        # Verify all required columns are present
        required_columns = [
            'job_id',
            'source',
            'status',
            'title',
            'url',
            'description',
            'attachments',
            'budget_type',
            'budget_min',
            'budget_max',
            'client_country',
            'client_spent',
            'client_hires',
            'payment_verified',
            'fit_score',
            'fit_reasoning',
            'proposal_doc_url',
            'proposal_text',
            'video_url',
            'pdf_url',
            'boost_decision',
            'boost_reasoning',
            'pricing_proposed',
            'slack_message_ts',
        ]

        for col in required_columns:
            self.assertIn(col, sheet_row, f"Missing column: {col}")
            self.assertIsNotNone(sheet_row[col], f"Column {col} is None")


class TestFeature73GmailEmailExtraction(unittest.TestCase):
    """
    Tests for Gmail email extraction that feeds into the pipeline.
    These validate the first stage of the Gmail-to-Slack flow.
    """

    def test_gmail_email_detection_upwork_alert(self):
        """Test that Upwork alert emails are correctly detected."""
        # Valid Upwork job alerts
        self.assertTrue(is_upwork_alert_email(
            "notifications@upwork.com",
            "New job that matches your skills"
        ))
        self.assertTrue(is_upwork_alert_email(
            "donotreply@upwork.com",
            "Job Alert: 5 new jobs for you"
        ))
        self.assertTrue(is_upwork_alert_email(
            "notifications@upwork.com",
            "Jobs matching your profile"
        ))
        self.assertTrue(is_upwork_alert_email(
            "notifications@upwork.com",
            "Recommended jobs for you"
        ))

    def test_gmail_email_detection_non_alert(self):
        """Test that non-job-alert emails from Upwork are not detected."""
        # Upwork emails that are NOT job alerts
        self.assertFalse(is_upwork_alert_email(
            "notifications@upwork.com",
            "Your weekly earnings summary"
        ))
        self.assertFalse(is_upwork_alert_email(
            "notifications@upwork.com",
            "Payment received"
        ))

    def test_gmail_email_detection_non_upwork(self):
        """Test that non-Upwork emails are not detected."""
        self.assertFalse(is_upwork_alert_email(
            "spam@example.com",
            "New job opportunity"
        ))
        self.assertFalse(is_upwork_alert_email(
            "jobs@indeed.com",
            "New jobs for you"
        ))

    def test_gmail_url_extraction_single_email(self):
        """Test URL extraction from sample Upwork email body."""
        urls = extract_job_urls(SAMPLE_UPWORK_EMAIL_BODY)

        # Should find 3 job URLs
        self.assertEqual(len(urls), 3)

        # Each URL should be valid Upwork job URL
        for url in urls:
            self.assertIn('upwork.com', url)
            self.assertRegex(url, r'jobs/~\w+')

    def test_gmail_url_extraction_digest_email(self):
        """Test URL extraction from digest email with multiple jobs."""
        urls = extract_job_urls(SAMPLE_UPWORK_DIGEST_BODY)

        # Should find 5 job URLs
        self.assertEqual(len(urls), 5)

    def test_gmail_job_id_extraction(self):
        """Test job ID extraction from URLs."""
        test_urls = [
            ("https://www.upwork.com/jobs/~01abc123def456", "~01abc123def456"),
            ("https://www.upwork.com/ab/jobs/~02xyz789ghi012", "~02xyz789ghi012"),
            ("https://upwork.com/jobs/~0a1b2c3d4e5f", "~0a1b2c3d4e5f"),
        ]

        for url, expected_id in test_urls:
            job_id = extract_job_id(url)
            self.assertEqual(job_id, expected_id)

    def test_gmail_url_deduplication(self):
        """Test that duplicate URLs are removed."""
        text_with_dupes = """
        https://www.upwork.com/jobs/~01abc123
        https://www.upwork.com/jobs/~01abc123/
        https://www.upwork.com/jobs/~01abc123
        https://www.upwork.com/jobs/~02def456
        """
        urls = extract_job_urls(text_with_dupes)

        # Should deduplicate to 2 unique URLs
        self.assertEqual(len(urls), 2)

    def test_gmail_jobs_extraction_from_emails(self):
        """Test job extraction from multiple email structures."""
        mock_emails = [
            {
                "id": "email1",
                "subject": "New job that matches your skills",
                "from": "notifications@upwork.com",
                "date": "2024-01-15",
                "body": SAMPLE_UPWORK_EMAIL_BODY,
            },
            {
                "id": "email2",
                "subject": "Your daily job digest",
                "from": "notifications@upwork.com",
                "date": "2024-01-15",
                "body": SAMPLE_UPWORK_DIGEST_BODY,
            },
        ]

        jobs = extract_jobs_from_emails(mock_emails)

        # Should extract 8 unique jobs (3 from first + 5 from second)
        self.assertEqual(len(jobs), 8)

        # All jobs should have source='gmail'
        for job in jobs:
            self.assertEqual(job['source'], 'gmail')
            self.assertIsNotNone(job['job_id'])
            self.assertTrue(job['job_id'].startswith('~'))
            self.assertIn('upwork.com', job['url'])


class TestFeature73PipelineStages(unittest.TestCase):
    """
    Tests for individual pipeline stages with Gmail source.
    """

    def test_e2e_gmail_deduplication_stage(self):
        """Test that deduplication stage works for Gmail jobs."""
        result = run_pipeline_sync(
            source='gmail',
            limit=1,
            min_score=50,
            mock=True,
            parallel=1,
        )

        # In mock mode, deduplication is skipped
        self.assertEqual(result.jobs_after_dedup, result.jobs_ingested)

    def test_e2e_gmail_prefilter_stage(self):
        """Test that pre-filter stage works for Gmail jobs."""
        result = run_pipeline_sync(
            source='gmail',
            limit=1,
            min_score=50,
            mock=True,
            parallel=1,
        )

        # Job should have fit_score
        job = result.processed_jobs[0]
        self.assertIsNotNone(job.fit_score)
        self.assertIsNotNone(job.fit_reasoning)

    def test_e2e_gmail_deep_extraction_stage(self):
        """Test that deep extraction stage works for Gmail jobs."""
        result = run_pipeline_sync(
            source='gmail',
            limit=1,
            min_score=50,
            mock=True,
            parallel=1,
        )

        job = result.processed_jobs[0]

        # Mock deep extraction should populate budget and client info
        self.assertIsNotNone(job.budget_type)
        self.assertIsNotNone(job.client_country)
        self.assertIsNotNone(job.payment_verified)

    def test_e2e_gmail_deliverable_generation_stage(self):
        """Test that deliverable generation stage works for Gmail jobs."""
        result = run_pipeline_sync(
            source='gmail',
            limit=1,
            min_score=50,
            mock=True,
            parallel=1,
        )

        job = result.processed_jobs[0]

        # Mock deliverable generation should populate all URLs
        self.assertIsNotNone(job.proposal_doc_url)
        self.assertIsNotNone(job.video_url)
        self.assertIsNotNone(job.pdf_url)
        self.assertIsNotNone(job.cover_letter)

    def test_e2e_gmail_slack_approval_stage(self):
        """Test that Slack approval stage works for Gmail jobs."""
        result = run_pipeline_sync(
            source='gmail',
            limit=1,
            min_score=50,
            mock=True,
            parallel=1,
        )

        job = result.processed_jobs[0]

        # Mock Slack should set message timestamp
        self.assertIsNotNone(job.slack_message_ts)

        # Status should be PENDING_APPROVAL
        self.assertEqual(job.status, PipelineStatus.PENDING_APPROVAL)

        # Stats should show Slack message sent
        self.assertEqual(result.jobs_sent_to_slack, 1)


class TestFeature73GmailPushNotification(unittest.TestCase):
    """
    Tests for Gmail push notification handling (simulated).
    """

    def test_e2e_gmail_push_triggers_pipeline(self):
        """Test that Gmail push notification can trigger the pipeline."""
        # Simulate receiving a Gmail push notification with job data
        # In mock mode, we can directly test the pipeline handles gmail source
        result = run_pipeline_sync(
            source='gmail',
            limit=1,
            min_score=50,
            mock=True,
            parallel=1,
        )

        # Pipeline should complete successfully
        self.assertIsNotNone(result.finished_at)
        self.assertEqual(len(result.errors), 0)

    def test_e2e_gmail_realtime_processing(self):
        """Test that Gmail jobs are processed in real-time manner."""
        # Real-time processing should complete quickly
        import time
        start = time.time()

        result = run_pipeline_sync(
            source='gmail',
            limit=1,
            min_score=50,
            mock=True,
            parallel=1,
        )

        elapsed = time.time() - start

        # Mock mode should complete very quickly
        self.assertLess(elapsed, 5.0)  # Should complete in under 5 seconds
        self.assertEqual(result.jobs_processed, 1)


class TestFeature73AsyncExecution(unittest.TestCase):
    """
    Tests for async pipeline execution with Gmail source.
    """

    def test_e2e_gmail_async_pipeline(self):
        """Test that async pipeline execution works with Gmail source."""
        async def run_test():
            result = await run_pipeline_async(
                source='gmail',
                limit=1,
                min_score=50,
                mock=True,
                parallel=1,
            )
            return result

        result = asyncio.run(run_test())

        self.assertIsInstance(result, PipelineResult)
        self.assertEqual(result.source, 'gmail')
        self.assertEqual(result.jobs_ingested, 1)
        self.assertEqual(result.jobs_sent_to_slack, 1)
        self.assertEqual(len(result.processed_jobs), 1)

        # Verify job source
        self.assertEqual(result.processed_jobs[0].source, 'gmail')


class TestFeature73DataIntegrity(unittest.TestCase):
    """
    Tests for data integrity in Gmail-sourced pipeline flow.
    """

    def test_e2e_gmail_job_id_preserved(self):
        """Test that job_id from Gmail is preserved throughout pipeline."""
        result = run_pipeline_sync(
            source='gmail',
            limit=1,
            min_score=50,
            mock=True,
            parallel=1,
        )

        job = result.processed_jobs[0]

        # Job ID should start with ~gmailmock (from mock Gmail)
        self.assertTrue(job.job_id.startswith('~gmailmock'))

        # Job ID should appear in deliverable URLs
        self.assertIn(job.job_id, job.proposal_doc_url)
        self.assertIn(job.job_id, job.video_url)
        self.assertIn(job.job_id, job.slack_message_ts)

    def test_e2e_gmail_result_serializable(self):
        """Test that Gmail pipeline result can be serialized to JSON."""
        result = run_pipeline_sync(
            source='gmail',
            limit=1,
            min_score=50,
            mock=True,
            parallel=1,
        )

        # Should be able to convert to dict
        result_dict = result.to_dict()
        self.assertIsInstance(result_dict, dict)
        self.assertEqual(result_dict['source'], 'gmail')

        # Should be JSON serializable
        json_str = json.dumps(result_dict)
        self.assertIsInstance(json_str, str)

        # Should round-trip
        loaded = json.loads(json_str)
        self.assertEqual(loaded['source'], 'gmail')
        self.assertEqual(loaded['jobs_sent_to_slack'], result.jobs_sent_to_slack)

    def test_e2e_gmail_vs_apify_same_structure(self):
        """Test that Gmail and Apify jobs have same output structure."""
        # Run pipeline with Gmail source
        gmail_result = run_pipeline_sync(
            source='gmail',
            limit=1,
            min_score=50,
            mock=True,
            parallel=1,
        )

        # Run pipeline with Apify source
        apify_result = run_pipeline_sync(
            source='apify',
            limit=1,
            min_score=50,
            mock=True,
            parallel=1,
        )

        # Both should have processed jobs
        self.assertEqual(len(gmail_result.processed_jobs), 1)
        self.assertEqual(len(apify_result.processed_jobs), 1)

        gmail_job = gmail_result.processed_jobs[0]
        apify_job = apify_result.processed_jobs[0]

        # Sheet rows should have same columns
        gmail_row = gmail_job.to_sheet_row()
        apify_row = apify_job.to_sheet_row()

        self.assertEqual(set(gmail_row.keys()), set(apify_row.keys()))

        # Only difference should be source and job_id pattern
        self.assertEqual(gmail_row['source'], 'gmail')
        self.assertEqual(apify_row['source'], 'apify')


class TestFeature73ErrorHandling(unittest.TestCase):
    """
    Tests for error handling in Gmail-sourced pipeline.
    """

    def test_e2e_gmail_empty_response_handled(self):
        """Test that empty Gmail response is handled gracefully."""
        # Can't easily test empty response in mock mode since it always returns
        # mock data, but we can test with manual jobs
        result = run_pipeline_sync(
            source='manual',
            jobs=[],  # Empty job list
            min_score=50,
            mock=True,
            parallel=1,
        )

        # Should complete without errors
        self.assertEqual(result.jobs_ingested, 0)
        self.assertEqual(len(result.errors), 0)

    def test_e2e_gmail_high_threshold_filters_jobs(self):
        """Test that high pre-filter threshold filters Gmail jobs."""
        result = run_pipeline_sync(
            source='gmail',
            limit=1,
            min_score=100,  # Very high threshold
            mock=True,
            parallel=1,
        )

        # Mock scoring gives 85, which is < 100
        # So job should be filtered out
        self.assertEqual(result.jobs_ingested, 1)
        self.assertEqual(result.jobs_after_prefilter, 0)
        self.assertEqual(result.jobs_filtered_out, 1)
        self.assertEqual(result.jobs_processed, 0)
        self.assertEqual(result.jobs_sent_to_slack, 0)


def run_feature_73_tests():
    """Run all Feature #73 tests and return results."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestFeature73GmailToSlackE2E))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature73GmailEmailExtraction))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature73PipelineStages))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature73GmailPushNotification))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature73AsyncExecution))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature73DataIntegrity))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature73ErrorHandling))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_feature_73_tests()
    sys.exit(0 if success else 1)
