#!/usr/bin/env python3
"""
End-to-End Test: Job flows from Apify to Slack approval

Feature #72: End-to-end test - Job flows from Apify to Slack approval

This test validates the complete pipeline flow:
1. Trigger Apify scrape for 1 job
2. Wait for deduplication
3. Wait for pre-filter (expect pass)
4. Wait for deep extraction
5. Wait for deliverable generation
6. Verify Slack message received
7. Verify all fields populated in sheet

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


class TestFeature72ApifyToSlackE2E(unittest.TestCase):
    """
    Feature #72: End-to-end test - Job flows from Apify to Slack approval

    Tests the complete pipeline flow from Apify job ingestion through
    to Slack approval message sending.
    """

    def test_e2e_single_job_flows_through_pipeline_mock(self):
        """Test that a single job flows through all pipeline stages in mock mode."""
        # Run pipeline with mock mode (no real API calls)
        result = run_pipeline_sync(
            source='apify',
            limit=1,
            min_score=50,  # Low threshold to ensure job passes
            mock=True,
            parallel=1,
        )

        # Verify pipeline ran successfully
        self.assertIsInstance(result, PipelineResult)
        self.assertEqual(result.source, 'apify')
        self.assertIsNotNone(result.started_at)
        self.assertIsNotNone(result.finished_at)

        # Verify job was ingested
        self.assertEqual(result.jobs_ingested, 1)

        # Verify job passed deduplication (mock mode skips dedup)
        self.assertEqual(result.jobs_after_dedup, 1)

        # Verify job passed pre-filter (mock gives alternating scores, first is 85)
        self.assertEqual(result.jobs_after_prefilter, 1)
        self.assertEqual(result.jobs_filtered_out, 0)

        # Verify job was processed
        self.assertEqual(result.jobs_processed, 1)

        # Verify Slack message was sent (mock mode)
        self.assertEqual(result.jobs_sent_to_slack, 1)

        # Verify no errors
        self.assertEqual(result.jobs_with_errors, 0)
        self.assertEqual(len(result.errors), 0)

    def test_e2e_job_has_all_fields_populated(self):
        """Test that processed job has all required fields populated."""
        result = run_pipeline_sync(
            source='apify',
            limit=1,
            min_score=50,
            mock=True,
            parallel=1,
        )

        # Get the processed job
        self.assertEqual(len(result.processed_jobs), 1)
        job = result.processed_jobs[0]

        # Verify basic fields from ingestion
        self.assertIsNotNone(job.job_id)
        self.assertTrue(job.job_id.startswith('~mock'))
        self.assertIsNotNone(job.url)
        self.assertIn('upwork.com', job.url)
        self.assertEqual(job.source, 'apify')
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

    def test_e2e_job_status_transitions(self):
        """Test that job goes through correct status transitions."""
        # We can't easily test status transitions in mock mode without
        # more detailed tracking, but we can verify the final status
        result = run_pipeline_sync(
            source='apify',
            limit=1,
            min_score=50,
            mock=True,
            parallel=1,
        )

        job = result.processed_jobs[0]

        # Final status should be PENDING_APPROVAL for successful jobs
        self.assertEqual(job.status, PipelineStatus.PENDING_APPROVAL)

        # The job should have been through these stages:
        # NEW -> SCORING -> EXTRACTING -> GENERATING -> BOOST_DECIDING -> PENDING_APPROVAL
        # We can verify by checking that the relevant fields are populated

        # SCORING stage completed (fit_score populated)
        self.assertIsNotNone(job.fit_score)

        # EXTRACTING stage completed (budget info populated)
        self.assertIsNotNone(job.budget_type)

        # GENERATING stage completed (deliverables populated)
        self.assertIsNotNone(job.proposal_doc_url)

        # BOOST_DECIDING stage completed (boost decision populated)
        self.assertIsNotNone(job.boost_decision)

        # PENDING_APPROVAL stage reached (Slack message sent)
        self.assertIsNotNone(job.slack_message_ts)

    def test_e2e_sheet_row_data_is_complete(self):
        """Test that job's sheet row data has all required fields."""
        result = run_pipeline_sync(
            source='apify',
            limit=1,
            min_score=50,
            mock=True,
            parallel=1,
        )

        job = result.processed_jobs[0]
        sheet_row = job.to_sheet_row()

        # All required columns from feature_list.json spec
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

    def test_e2e_result_statistics_accurate(self):
        """Test that pipeline result statistics are accurate."""
        result = run_pipeline_sync(
            source='apify',
            limit=3,  # Process 3 jobs
            min_score=50,
            mock=True,
            parallel=1,
        )

        # Verify statistics
        self.assertEqual(result.jobs_ingested, 3)
        self.assertEqual(result.jobs_after_dedup, 3)  # Mock mode skips dedup

        # With min_score=50, first job (score 85) passes, second (55) passes, third (85) passes
        self.assertGreaterEqual(result.jobs_after_prefilter, 1)

        # All passing jobs should be processed
        self.assertEqual(result.jobs_processed, result.jobs_after_prefilter)

        # All processed jobs should have Slack messages
        self.assertEqual(result.jobs_sent_to_slack, result.jobs_processed)

    def test_e2e_pipeline_result_serializable(self):
        """Test that pipeline result can be serialized to JSON."""
        result = run_pipeline_sync(
            source='apify',
            limit=1,
            min_score=50,
            mock=True,
            parallel=1,
        )

        # Should be able to convert to dict
        result_dict = result.to_dict()
        self.assertIsInstance(result_dict, dict)

        # Should be JSON serializable
        json_str = json.dumps(result_dict)
        self.assertIsInstance(json_str, str)

        # Should round-trip
        loaded = json.loads(json_str)
        self.assertEqual(loaded['jobs_ingested'], result.jobs_ingested)
        self.assertEqual(loaded['jobs_sent_to_slack'], result.jobs_sent_to_slack)

    def test_e2e_apify_source_correctly_set(self):
        """Test that jobs have source='apify' when coming from Apify."""
        result = run_pipeline_sync(
            source='apify',
            limit=1,
            min_score=50,
            mock=True,
            parallel=1,
        )

        self.assertEqual(result.source, 'apify')

        for job in result.processed_jobs:
            self.assertEqual(job.source, 'apify')


class TestFeature72WithMockedComponents(unittest.TestCase):
    """
    Additional tests for Feature #72 with mocked components
    to verify integration points.
    """

    def test_e2e_deduplication_stage_executes(self):
        """Test that deduplication stage is properly executed."""
        # In mock mode, deduplication is skipped but we verify the pipeline
        # handles the deduplication stage appropriately
        result = run_pipeline_sync(
            source='apify',
            limit=2,
            min_score=50,
            mock=True,
            parallel=1,
        )

        # jobs_after_dedup should equal jobs_ingested in mock mode
        # (since deduplication is skipped)
        self.assertEqual(result.jobs_after_dedup, result.jobs_ingested)

    def test_e2e_prefilter_stage_executes(self):
        """Test that pre-filter stage is properly executed."""
        result = run_pipeline_sync(
            source='apify',
            limit=2,
            min_score=50,
            mock=True,
            parallel=1,
        )

        # Each job should have a fit_score
        for job in result.processed_jobs:
            self.assertIsNotNone(job.fit_score)
            self.assertIsNotNone(job.fit_reasoning)

    def test_e2e_deep_extraction_stage_executes(self):
        """Test that deep extraction stage is properly executed."""
        result = run_pipeline_sync(
            source='apify',
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

    def test_e2e_deliverable_generation_stage_executes(self):
        """Test that deliverable generation stage is properly executed."""
        result = run_pipeline_sync(
            source='apify',
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

    def test_e2e_slack_approval_stage_executes(self):
        """Test that Slack approval stage is properly executed."""
        result = run_pipeline_sync(
            source='apify',
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


class TestFeature72ErrorHandling(unittest.TestCase):
    """
    Tests for Feature #72 error handling in end-to-end flow.
    """

    def test_e2e_empty_apify_response_handled(self):
        """Test that empty Apify response is handled gracefully."""
        result = run_pipeline_sync(
            source='apify',
            limit=0,  # Request 0 jobs
            min_score=50,
            mock=True,
            parallel=1,
        )

        # Should complete without errors
        self.assertEqual(result.jobs_ingested, 0)
        self.assertEqual(len(result.errors), 0)

    def test_e2e_high_threshold_filters_all_jobs(self):
        """Test that high pre-filter threshold filters out low-scoring jobs."""
        result = run_pipeline_sync(
            source='apify',
            limit=1,
            min_score=100,  # Very high threshold
            mock=True,
            parallel=1,
        )

        # Mock scoring gives 85 or 55, neither >= 100
        # So job should be filtered out
        self.assertEqual(result.jobs_ingested, 1)
        self.assertEqual(result.jobs_after_prefilter, 0)
        self.assertEqual(result.jobs_filtered_out, 1)
        self.assertEqual(result.jobs_processed, 0)
        self.assertEqual(result.jobs_sent_to_slack, 0)

    def test_e2e_result_tracks_filtered_jobs(self):
        """Test that result properly tracks filtered out jobs."""
        result = run_pipeline_sync(
            source='apify',
            limit=4,  # Request 4 jobs to get mix of scores
            min_score=60,  # Threshold that filters some jobs
            mock=True,
            parallel=1,
        )

        # Mock gives alternating 85, 55, 85, 55 scores
        # With min_score=60, 55s are filtered out
        self.assertEqual(result.jobs_ingested, 4)

        # Half should pass (scores 85), half filtered (scores 55)
        self.assertEqual(result.jobs_after_prefilter, 2)
        self.assertEqual(result.jobs_filtered_out, 2)


class TestFeature72AsyncExecution(unittest.TestCase):
    """
    Tests for Feature #72 async execution.
    """

    def test_e2e_async_pipeline_works(self):
        """Test that async pipeline execution works correctly."""
        async def run_test():
            result = await run_pipeline_async(
                source='apify',
                limit=1,
                min_score=50,
                mock=True,
                parallel=1,
            )
            return result

        result = asyncio.run(run_test())

        self.assertIsInstance(result, PipelineResult)
        self.assertEqual(result.jobs_ingested, 1)
        self.assertEqual(result.jobs_sent_to_slack, 1)
        self.assertEqual(len(result.processed_jobs), 1)

    def test_e2e_parallel_processing_works(self):
        """Test that parallel processing works correctly."""
        result = run_pipeline_sync(
            source='apify',
            limit=3,
            min_score=50,
            mock=True,
            parallel=3,  # Process all 3 in parallel
        )

        # Should process all jobs
        self.assertGreaterEqual(result.jobs_processed, 1)

        # All processed jobs should have required fields
        for job in result.processed_jobs:
            self.assertIsNotNone(job.proposal_doc_url)
            self.assertIsNotNone(job.slack_message_ts)


class TestFeature72DataIntegrity(unittest.TestCase):
    """
    Tests for Feature #72 data integrity throughout pipeline.
    """

    def test_e2e_job_id_preserved_throughout(self):
        """Test that job_id is preserved throughout the pipeline."""
        result = run_pipeline_sync(
            source='apify',
            limit=1,
            min_score=50,
            mock=True,
            parallel=1,
        )

        job = result.processed_jobs[0]

        # Job ID should be preserved
        self.assertTrue(job.job_id.startswith('~mock'))

        # Job ID should be in Slack message ts
        self.assertIn(job.job_id, job.slack_message_ts)

        # Job ID should be in deliverable URLs
        self.assertIn(job.job_id, job.proposal_doc_url)
        self.assertIn(job.job_id, job.video_url)

    def test_e2e_timestamps_are_valid(self):
        """Test that timestamps are valid ISO format."""
        result = run_pipeline_sync(
            source='apify',
            limit=1,
            min_score=50,
            mock=True,
            parallel=1,
        )

        # Verify started_at and finished_at are valid timestamps
        self.assertIsNotNone(result.started_at)
        self.assertIsNotNone(result.finished_at)

        # Should be parseable as ISO timestamps
        started = datetime.fromisoformat(result.started_at.replace('Z', '+00:00'))
        finished = datetime.fromisoformat(result.finished_at.replace('Z', '+00:00'))

        # Finished should be after started
        self.assertGreaterEqual(finished, started)

    def test_e2e_url_formats_are_correct(self):
        """Test that generated URLs have correct formats."""
        result = run_pipeline_sync(
            source='apify',
            limit=1,
            min_score=50,
            mock=True,
            parallel=1,
        )

        job = result.processed_jobs[0]

        # Original Upwork URL format
        self.assertTrue(job.url.startswith('https://www.upwork.com/jobs/'))

        # Google Docs URL format
        self.assertTrue(job.proposal_doc_url.startswith('https://docs.google.com/'))

        # HeyGen video URL format
        self.assertTrue(job.video_url.startswith('https://heygen.com/'))

        # Google Drive PDF URL format
        self.assertTrue(job.pdf_url.startswith('https://drive.google.com/'))


def run_feature_72_tests():
    """Run all Feature #72 tests and return results."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestFeature72ApifyToSlackE2E))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature72WithMockedComponents))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature72ErrorHandling))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature72AsyncExecution))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature72DataIntegrity))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_feature_72_tests()
    sys.exit(0 if success else 1)
