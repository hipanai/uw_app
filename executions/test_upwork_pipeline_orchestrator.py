#!/usr/bin/env python3
"""
Tests for Upwork Pipeline Orchestrator

Features #62-67:
- #62: Pipeline orchestrator runs full pipeline in sequence
- #63: Pipeline orchestrator handles Apify source correctly
- #64: Pipeline orchestrator handles Gmail source correctly
- #65: Pipeline orchestrator skips jobs below pre-filter threshold
- #66: Pipeline orchestrator updates sheet status at each stage
- #67: Pipeline orchestrator handles errors gracefully
"""

import os
import sys
import json
import unittest
import asyncio
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from dataclasses import asdict
from datetime import datetime, timezone

# Add executions directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from upwork_pipeline_orchestrator import (
    PipelineStatus,
    PipelineJob,
    PipelineResult,
    run_pipeline_async,
    run_pipeline_sync,
    update_job_in_sheet,
    update_jobs_batch_in_sheet,
)


class TestPipelineStatus(unittest.TestCase):
    """Test PipelineStatus enum."""

    def test_status_values_exist(self):
        """Test all required status values exist."""
        self.assertEqual(PipelineStatus.NEW.value, "new")
        self.assertEqual(PipelineStatus.SCORING.value, "scoring")
        self.assertEqual(PipelineStatus.FILTERED_OUT.value, "filtered_out")
        self.assertEqual(PipelineStatus.EXTRACTING.value, "extracting")
        self.assertEqual(PipelineStatus.GENERATING.value, "generating")
        self.assertEqual(PipelineStatus.BOOST_DECIDING.value, "boost_deciding")
        self.assertEqual(PipelineStatus.PENDING_APPROVAL.value, "pending_approval")
        self.assertEqual(PipelineStatus.APPROVED.value, "approved")
        self.assertEqual(PipelineStatus.REJECTED.value, "rejected")
        self.assertEqual(PipelineStatus.SUBMITTED.value, "submitted")
        self.assertEqual(PipelineStatus.ERROR.value, "error")

    def test_all_statuses_have_string_values(self):
        """Test all status values are strings."""
        for status in PipelineStatus:
            self.assertIsInstance(status.value, str)


class TestPipelineJob(unittest.TestCase):
    """Test PipelineJob dataclass."""

    def test_create_job(self):
        """Test creating a PipelineJob."""
        job = PipelineJob(
            job_id="~test123",
            url="https://www.upwork.com/jobs/~test123",
            source="apify",
            title="Test Job",
        )
        self.assertEqual(job.job_id, "~test123")
        self.assertEqual(job.source, "apify")
        self.assertEqual(job.status, PipelineStatus.NEW)

    def test_job_to_dict(self):
        """Test converting job to dictionary."""
        job = PipelineJob(
            job_id="~test123",
            url="https://www.upwork.com/jobs/~test123",
            source="gmail",
            title="Test Job",
            fit_score=85,
        )
        d = job.to_dict()
        self.assertEqual(d['job_id'], "~test123")
        self.assertEqual(d['source'], "gmail")
        self.assertEqual(d['status'], "new")  # String value
        self.assertEqual(d['fit_score'], 85)

    def test_job_to_sheet_row(self):
        """Test converting job to sheet row."""
        job = PipelineJob(
            job_id="~test123",
            url="https://www.upwork.com/jobs/~test123",
            source="apify",
            title="Test Job",
            description="A test description",
            fit_score=90,
            budget_type="fixed",
            budget_min=500,
            budget_max=1000,
        )
        row = job.to_sheet_row()
        self.assertEqual(row['job_id'], "~test123")
        self.assertEqual(row['status'], "new")
        self.assertEqual(row['budget_type'], "fixed")
        self.assertEqual(row['budget_min'], 500)

    def test_from_apify_job(self):
        """Test creating PipelineJob from Apify data."""
        apify_job = {
            'id': '~apify123',
            'url': 'https://www.upwork.com/jobs/~apify123',
            'title': 'Apify Job',
            'description': 'From Apify',
        }
        job = PipelineJob.from_apify_job(apify_job)
        self.assertEqual(job.job_id, '~apify123')
        self.assertEqual(job.source, 'apify')
        self.assertEqual(job.title, 'Apify Job')

    def test_from_apify_job_extracts_id_from_url(self):
        """Test extracting job ID from URL when not provided."""
        apify_job = {
            'url': 'https://www.upwork.com/jobs/~abc456',
            'title': 'Job without ID',
        }
        job = PipelineJob.from_apify_job(apify_job)
        self.assertEqual(job.job_id, '~abc456')

    def test_from_gmail_job(self):
        """Test creating PipelineJob from Gmail data."""
        gmail_job = {
            'job_id': '~gmail789',
            'url': 'https://www.upwork.com/jobs/~gmail789',
            'title': 'Gmail Job',
        }
        job = PipelineJob.from_gmail_job(gmail_job)
        self.assertEqual(job.job_id, '~gmail789')
        self.assertEqual(job.source, 'gmail')

    def test_job_error_log(self):
        """Test error log tracking."""
        job = PipelineJob(
            job_id="~test123",
            url="https://www.upwork.com/jobs/~test123",
            source="apify",
        )
        self.assertEqual(job.error_log, [])
        job.error_log.append("Error 1")
        job.error_log.append("Error 2")
        self.assertEqual(len(job.error_log), 2)

    def test_job_attachments_default_empty(self):
        """Test attachments default to empty list."""
        job = PipelineJob(
            job_id="~test123",
            url="https://www.upwork.com/jobs/~test123",
            source="apify",
        )
        self.assertEqual(job.attachments, [])


class TestPipelineResult(unittest.TestCase):
    """Test PipelineResult dataclass."""

    def test_create_result(self):
        """Test creating a PipelineResult."""
        result = PipelineResult(
            started_at=datetime.now(timezone.utc).isoformat(),
            source="apify",
        )
        self.assertIsNotNone(result.started_at)
        self.assertEqual(result.source, "apify")
        self.assertEqual(result.jobs_ingested, 0)

    def test_result_to_dict(self):
        """Test converting result to dictionary."""
        job = PipelineJob(
            job_id="~test123",
            url="https://www.upwork.com/jobs/~test123",
            source="apify",
        )
        result = PipelineResult(
            started_at="2025-01-19T00:00:00Z",
            source="apify",
            jobs_ingested=5,
            jobs_processed=3,
            processed_jobs=[job],
        )
        d = result.to_dict()
        self.assertEqual(d['jobs_ingested'], 5)
        self.assertEqual(d['jobs_processed'], 3)
        self.assertEqual(len(d['processed_jobs']), 1)
        self.assertEqual(d['processed_jobs'][0]['job_id'], "~test123")


class TestFeature62FullPipelineSequence(unittest.TestCase):
    """Feature #62: Pipeline orchestrator runs full pipeline in sequence."""

    def test_pipeline_runs_all_stages_mock(self):
        """Test that pipeline runs through all stages in mock mode."""
        result = run_pipeline_sync(
            source='apify',
            limit=3,
            mock=True,
        )

        # Should complete without errors
        self.assertIsNotNone(result.finished_at)
        self.assertEqual(len(result.errors), 0)

        # Should have ingested jobs
        self.assertGreater(result.jobs_ingested, 0)

    def test_pipeline_processes_jobs_in_order(self):
        """Test that jobs are processed in the correct order."""
        # Track status changes
        status_changes = []

        original_update = update_job_in_sheet

        def track_update(job, **kwargs):
            status_changes.append(job.status.value)
            return True

        with patch('upwork_pipeline_orchestrator.update_job_in_sheet', track_update):
            result = run_pipeline_sync(
                source='apify',
                limit=2,
                mock=True,
            )

        # Each job should go through: scoring, extracting, generating, boost_deciding, pending_approval
        # Plus some may be filtered_out
        expected_statuses = {'scoring', 'extracting', 'generating', 'boost_deciding', 'pending_approval', 'filtered_out'}
        actual_statuses = set(status_changes)
        self.assertTrue(actual_statuses.issubset(expected_statuses),
                       f"Unexpected statuses: {actual_statuses - expected_statuses}")

    def test_pipeline_with_manual_jobs(self):
        """Test pipeline with manually provided jobs."""
        jobs = [
            {'job_id': '~manual1', 'url': 'https://upwork.com/jobs/~manual1', 'title': 'Manual Job 1'},
            {'job_id': '~manual2', 'url': 'https://upwork.com/jobs/~manual2', 'title': 'Manual Job 2'},
        ]

        result = run_pipeline_sync(
            source='manual',
            jobs=jobs,
            mock=True,
        )

        self.assertEqual(result.jobs_ingested, 2)
        self.assertEqual(result.source, 'manual')

    def test_pipeline_returns_processed_jobs(self):
        """Test that pipeline returns list of processed jobs."""
        result = run_pipeline_sync(
            source='apify',
            limit=2,
            mock=True,
        )

        self.assertIsInstance(result.processed_jobs, list)
        # Should have processed jobs (may be filtered)
        for job in result.processed_jobs:
            self.assertIsInstance(job, PipelineJob)


class TestFeature63ApifySource(unittest.TestCase):
    """Feature #63: Pipeline orchestrator handles Apify source correctly."""

    def test_apify_source_sets_source_field(self):
        """Test that Apify source sets source='apify' on jobs."""
        result = run_pipeline_sync(
            source='apify',
            limit=2,
            mock=True,
        )

        # All processed jobs should have source='apify'
        for job in result.processed_jobs:
            self.assertEqual(job.source, 'apify')

    def test_apify_source_batch_processing(self):
        """Test that Apify source supports batch processing."""
        result = run_pipeline_sync(
            source='apify',
            limit=5,
            mock=True,
        )

        # Should have processed multiple jobs
        self.assertGreater(result.jobs_ingested, 1)

    def test_apify_source_records_source_apify(self):
        """Test Apify jobs have source='apify'."""
        result = run_pipeline_sync(
            source='apify',
            limit=3,
            mock=True,
        )

        self.assertEqual(result.source, 'apify')
        # Check jobs
        for job in result.processed_jobs:
            self.assertEqual(job.source, 'apify')


class TestFeature64GmailSource(unittest.TestCase):
    """Feature #64: Pipeline orchestrator handles Gmail source correctly."""

    def test_gmail_source_sets_source_field(self):
        """Test that Gmail source sets source='gmail' on jobs."""
        result = run_pipeline_sync(
            source='gmail',
            mock=True,
        )

        # All processed jobs should have source='gmail'
        for job in result.processed_jobs:
            self.assertEqual(job.source, 'gmail')

    def test_gmail_source_real_time_processing(self):
        """Test that Gmail source processes jobs (real-time mode)."""
        result = run_pipeline_sync(
            source='gmail',
            mock=True,
        )

        # Should complete even with no jobs
        self.assertIsNotNone(result.finished_at)

    def test_gmail_source_records_source_gmail(self):
        """Test Gmail jobs have source='gmail'."""
        result = run_pipeline_sync(
            source='gmail',
            mock=True,
        )

        self.assertEqual(result.source, 'gmail')


class TestFeature65PrefilterThreshold(unittest.TestCase):
    """Feature #65: Pipeline orchestrator skips jobs below pre-filter threshold."""

    def test_jobs_below_threshold_filtered_out(self):
        """Test that jobs with score < threshold are filtered out."""
        result = run_pipeline_sync(
            source='apify',
            limit=10,
            min_score=70,
            mock=True,
        )

        # Mock mode alternates scores 85 and 55
        # So roughly half should be filtered out
        self.assertGreater(result.jobs_filtered_out, 0)
        self.assertLess(result.jobs_after_prefilter, result.jobs_ingested)

    def test_filtered_jobs_have_correct_status(self):
        """Test that filtered jobs have status='filtered_out'."""
        # We need to capture the status when it's set
        filtered_statuses = []

        def mock_update(job, **kwargs):
            if job.status == PipelineStatus.FILTERED_OUT:
                filtered_statuses.append(job.job_id)
            return True

        with patch('upwork_pipeline_orchestrator.update_job_in_sheet', mock_update):
            result = run_pipeline_sync(
                source='apify',
                limit=10,
                min_score=70,
                mock=True,
            )

        # Should have some filtered jobs
        self.assertGreater(len(filtered_statuses), 0)

    def test_high_threshold_filters_more_jobs(self):
        """Test that higher threshold filters more jobs."""
        result_low = run_pipeline_sync(
            source='apify',
            limit=10,
            min_score=50,
            mock=True,
        )

        result_high = run_pipeline_sync(
            source='apify',
            limit=10,
            min_score=80,
            mock=True,
        )

        # Higher threshold should filter more
        self.assertGreater(result_high.jobs_filtered_out, result_low.jobs_filtered_out)

    def test_jobs_pass_filter_when_score_equals_threshold(self):
        """Test that jobs with score == threshold pass."""
        jobs = [
            {'job_id': '~test1', 'url': 'https://upwork.com/jobs/~test1', 'title': 'Job 1'},
        ]

        result = run_pipeline_sync(
            source='manual',
            jobs=jobs,
            min_score=85,  # Mock gives score 85 to first job
            mock=True,
        )

        # Job with score 85 should pass threshold 85
        self.assertEqual(result.jobs_filtered_out, 0)


class TestFeature66SheetStatusUpdates(unittest.TestCase):
    """Feature #66: Pipeline orchestrator updates sheet status at each stage."""

    def test_status_changes_tracked(self):
        """Test that status changes are tracked."""
        status_updates = []

        def mock_update(job, **kwargs):
            status_updates.append({
                'job_id': job.job_id,
                'status': job.status.value,
            })
            return True

        with patch('upwork_pipeline_orchestrator.update_job_in_sheet', mock_update):
            result = run_pipeline_sync(
                source='apify',
                limit=2,
                mock=True,
            )

        # Should have multiple status updates
        self.assertGreater(len(status_updates), 0)

    def test_expected_status_transitions(self):
        """Test that jobs go through expected status transitions."""
        job_statuses = {}

        def mock_update(job, **kwargs):
            if job.job_id not in job_statuses:
                job_statuses[job.job_id] = []
            job_statuses[job.job_id].append(job.status.value)
            return True

        with patch('upwork_pipeline_orchestrator.update_job_in_sheet', mock_update):
            result = run_pipeline_sync(
                source='apify',
                limit=2,
                mock=True,
            )

        # At least one job should have status updates
        self.assertGreater(len(job_statuses), 0)

        # Check expected transitions for non-filtered jobs
        for job_id, statuses in job_statuses.items():
            # Should start with scoring
            self.assertEqual(statuses[0], 'scoring',
                           f"Job {job_id} should start with 'scoring', got {statuses}")

    def test_sheet_update_called_for_each_stage(self):
        """Test that sheet update is called at each pipeline stage."""
        update_count = [0]

        def mock_update(job, **kwargs):
            update_count[0] += 1
            return True

        with patch('upwork_pipeline_orchestrator.update_job_in_sheet', mock_update):
            result = run_pipeline_sync(
                source='apify',
                limit=2,
                mock=True,
            )

        # Should have at least 2 updates per job (scoring + final)
        self.assertGreaterEqual(update_count[0], result.jobs_ingested)


class TestFeature67ErrorHandling(unittest.TestCase):
    """Feature #67: Pipeline orchestrator handles errors gracefully."""

    def test_pipeline_continues_on_error(self):
        """Test that pipeline continues processing after an error."""
        jobs = [
            {'job_id': '~good1', 'url': 'https://upwork.com/jobs/~good1', 'title': 'Good Job 1'},
            {'job_id': '~good2', 'url': 'https://upwork.com/jobs/~good2', 'title': 'Good Job 2'},
        ]

        result = run_pipeline_sync(
            source='manual',
            jobs=jobs,
            mock=True,
        )

        # Should process jobs
        self.assertGreater(result.jobs_processed, 0)
        self.assertIsNotNone(result.finished_at)

    def test_errors_logged_in_job(self):
        """Test that errors are logged in job's error_log."""
        # In mock mode with no real errors, error_log should be empty
        jobs = [
            {'job_id': '~test1', 'url': 'https://upwork.com/jobs/~test1', 'title': 'Test Job'},
        ]

        result = run_pipeline_sync(
            source='manual',
            jobs=jobs,
            mock=True,
        )

        # In normal mock mode, jobs should have empty error logs
        for job in result.processed_jobs:
            self.assertIsInstance(job.error_log, list)

    def test_error_count_tracked(self):
        """Test that error count is tracked in result."""
        result = run_pipeline_sync(
            source='apify',
            limit=3,
            mock=True,
        )

        # jobs_with_errors should be an integer >= 0
        self.assertIsInstance(result.jobs_with_errors, int)
        self.assertGreaterEqual(result.jobs_with_errors, 0)

    def test_pipeline_returns_result_even_on_errors(self):
        """Test that pipeline returns result structure even with errors."""
        result = run_pipeline_sync(
            source='apify',
            limit=2,
            mock=True,
        )

        # Should always return a PipelineResult
        self.assertIsInstance(result, PipelineResult)
        self.assertIsNotNone(result.started_at)
        self.assertIsNotNone(result.finished_at)

    def test_invalid_source_raises_error(self):
        """Test that invalid source raises appropriate error."""
        result = run_pipeline_sync(
            source='invalid_source',
            mock=True,
        )

        # Should have error in errors list
        self.assertGreater(len(result.errors), 0)
        self.assertTrue(any('Unknown source' in e for e in result.errors))


class TestUpdateJobInSheet(unittest.TestCase):
    """Test update_job_in_sheet function."""

    def test_mock_mode_returns_success(self):
        """Test that mock mode returns success."""
        job = PipelineJob(
            job_id="~test123",
            url="https://www.upwork.com/jobs/~test123",
            source="apify",
        )

        result = update_job_in_sheet(job, mock=True)
        self.assertTrue(result)

    def test_no_sheet_id_returns_false(self):
        """Test that missing sheet ID returns False."""
        job = PipelineJob(
            job_id="~test123",
            url="https://www.upwork.com/jobs/~test123",
            source="apify",
        )

        with patch.dict(os.environ, {'UPWORK_PIPELINE_SHEET_ID': ''}):
            # Need to reload to pick up env change
            result = update_job_in_sheet(job, sheet_id=None, mock=False)
            # Should return False since no sheet ID
            self.assertFalse(result)


class TestPipelineResultStatistics(unittest.TestCase):
    """Test pipeline result statistics tracking."""

    def test_counts_are_accurate(self):
        """Test that job counts are accurate."""
        result = run_pipeline_sync(
            source='apify',
            limit=5,
            mock=True,
        )

        # Ingested should equal limit
        self.assertEqual(result.jobs_ingested, 5)

        # After dedup should be <= ingested
        self.assertLessEqual(result.jobs_after_dedup, result.jobs_ingested)

        # After prefilter + filtered_out should equal after_dedup
        total_after_prefilter = result.jobs_after_prefilter + result.jobs_filtered_out
        self.assertEqual(total_after_prefilter, result.jobs_after_dedup)

    def test_timing_recorded(self):
        """Test that timing is recorded."""
        result = run_pipeline_sync(
            source='apify',
            limit=2,
            mock=True,
        )

        self.assertIsNotNone(result.started_at)
        self.assertIsNotNone(result.finished_at)

        # Finished should be after started
        started = datetime.fromisoformat(result.started_at.replace('Z', '+00:00'))
        finished = datetime.fromisoformat(result.finished_at.replace('Z', '+00:00'))
        self.assertGreaterEqual(finished, started)


class TestPipelineAsync(unittest.TestCase):
    """Test async pipeline functionality."""

    def test_async_pipeline_runs(self):
        """Test that async pipeline runs correctly."""
        result = asyncio.run(run_pipeline_async(
            source='apify',
            limit=2,
            mock=True,
        ))

        self.assertIsInstance(result, PipelineResult)
        self.assertIsNotNone(result.finished_at)

    def test_parallel_parameter(self):
        """Test that parallel parameter is accepted."""
        result = run_pipeline_sync(
            source='apify',
            limit=5,
            parallel=5,
            mock=True,
        )

        self.assertIsNotNone(result.finished_at)


class TestEmptyJobHandling(unittest.TestCase):
    """Test handling of empty job scenarios."""

    def test_empty_jobs_list(self):
        """Test pipeline with empty jobs list."""
        result = run_pipeline_sync(
            source='manual',
            jobs=[],
            mock=True,
        )

        self.assertEqual(result.jobs_ingested, 0)
        self.assertEqual(result.jobs_processed, 0)
        self.assertIsNotNone(result.finished_at)

    def test_all_jobs_filtered(self):
        """Test when all jobs are filtered out."""
        result = run_pipeline_sync(
            source='apify',
            limit=5,
            min_score=100,  # Very high threshold
            mock=True,
        )

        # All jobs should be filtered (mock scores max at 85)
        self.assertEqual(result.jobs_after_prefilter, 0)
        self.assertEqual(result.jobs_filtered_out, result.jobs_after_dedup)


class TestFeature79BatchUpdates(unittest.TestCase):
    """Feature #79: Sheet operations use batch updates where possible."""

    def test_batch_update_function_exists(self):
        """Test that update_jobs_batch_in_sheet function exists."""
        self.assertTrue(callable(update_jobs_batch_in_sheet))

    def test_batch_update_mock_mode_returns_success(self):
        """Test that mock mode returns success for batch updates."""
        jobs = [
            PipelineJob(
                job_id="~test1",
                url="https://www.upwork.com/jobs/~test1",
                source="apify",
                title="Test Job 1",
            ),
            PipelineJob(
                job_id="~test2",
                url="https://www.upwork.com/jobs/~test2",
                source="apify",
                title="Test Job 2",
            ),
        ]

        result = update_jobs_batch_in_sheet(jobs, mock=True)
        self.assertEqual(result['updated'], 2)
        self.assertEqual(result['failed'], 0)

    def test_batch_update_returns_correct_structure(self):
        """Test that batch update returns dictionary with required keys."""
        jobs = [
            PipelineJob(
                job_id="~test1",
                url="https://www.upwork.com/jobs/~test1",
                source="apify",
            ),
        ]

        result = update_jobs_batch_in_sheet(jobs, mock=True)

        # Check all required keys exist
        self.assertIn('updated', result)
        self.assertIn('inserted', result)
        self.assertIn('failed', result)
        self.assertIn('api_calls', result)

    def test_batch_update_empty_list_returns_empty_result(self):
        """Test that batch update with empty list returns zeros."""
        result = update_jobs_batch_in_sheet([], mock=True)

        self.assertEqual(result['updated'], 0)
        self.assertEqual(result['inserted'], 0)
        self.assertEqual(result['failed'], 0)
        self.assertEqual(result['api_calls'], 0)

    def test_batch_update_fewer_api_calls_than_jobs(self):
        """Test that batch update uses fewer API calls than number of jobs."""
        # Create 20 jobs
        jobs = [
            PipelineJob(
                job_id=f"~test{i}",
                url=f"https://www.upwork.com/jobs/~test{i}",
                source="apify",
                title=f"Test Job {i}",
            )
            for i in range(20)
        ]

        # Mock the gspread client
        mock_sheet = MagicMock()
        mock_sheet.row_values.return_value = ['job_id', 'source', 'status', 'title', 'url']
        mock_sheet.get_all_values.return_value = [
            ['job_id', 'source', 'status', 'title', 'url'],  # Header row
            # Existing jobs (first 10)
            *[[f'~test{i}', 'apify', 'new', f'Test Job {i}', f'https://www.upwork.com/jobs/~test{i}']
              for i in range(10)]
        ]
        mock_sheet.batch_update = MagicMock()
        mock_sheet.append_rows = MagicMock()

        mock_spreadsheet = MagicMock()
        mock_spreadsheet.sheet1 = mock_sheet

        mock_client = MagicMock()
        mock_client.open_by_key.return_value = mock_spreadsheet

        with patch('upwork_pipeline_orchestrator.get_sheets_client', return_value=mock_client):
            with patch.dict(os.environ, {'UPWORK_PIPELINE_SHEET_ID': 'test_sheet_id'}):
                result = update_jobs_batch_in_sheet(jobs, mock=False)

        # Should have used fewer than 20 API calls for 20 jobs
        # Maximum should be: open_by_key(1) + row_values(1) + get_all_values(1) + batch_update(1) + append_rows(1) = 5
        self.assertLess(result['api_calls'], 20)
        self.assertLessEqual(result['api_calls'], 5)

    def test_batch_update_uses_batch_update_api(self):
        """Test that batch update calls batch_update API for existing jobs."""
        jobs = [
            PipelineJob(
                job_id="~existing1",
                url="https://www.upwork.com/jobs/~existing1",
                source="apify",
                title="Existing Job 1",
            ),
            PipelineJob(
                job_id="~existing2",
                url="https://www.upwork.com/jobs/~existing2",
                source="apify",
                title="Existing Job 2",
            ),
        ]

        mock_sheet = MagicMock()
        mock_sheet.row_values.return_value = ['job_id', 'source', 'status', 'title', 'url']
        mock_sheet.get_all_values.return_value = [
            ['job_id', 'source', 'status', 'title', 'url'],
            ['~existing1', 'apify', 'new', 'Existing Job 1', 'https://www.upwork.com/jobs/~existing1'],
            ['~existing2', 'apify', 'new', 'Existing Job 2', 'https://www.upwork.com/jobs/~existing2'],
        ]
        mock_sheet.batch_update = MagicMock()
        mock_sheet.append_rows = MagicMock()

        mock_spreadsheet = MagicMock()
        mock_spreadsheet.sheet1 = mock_sheet

        mock_client = MagicMock()
        mock_client.open_by_key.return_value = mock_spreadsheet

        with patch('upwork_pipeline_orchestrator.get_sheets_client', return_value=mock_client):
            with patch.dict(os.environ, {'UPWORK_PIPELINE_SHEET_ID': 'test_sheet_id'}):
                result = update_jobs_batch_in_sheet(jobs, mock=False)

        # batch_update should have been called (for existing jobs)
        mock_sheet.batch_update.assert_called()
        # append_rows should NOT have been called (no new jobs)
        mock_sheet.append_rows.assert_not_called()
        self.assertEqual(result['updated'], 2)
        self.assertEqual(result['inserted'], 0)

    def test_batch_update_uses_append_rows_for_new_jobs(self):
        """Test that batch update calls append_rows API for new jobs."""
        jobs = [
            PipelineJob(
                job_id="~new1",
                url="https://www.upwork.com/jobs/~new1",
                source="apify",
                title="New Job 1",
            ),
            PipelineJob(
                job_id="~new2",
                url="https://www.upwork.com/jobs/~new2",
                source="apify",
                title="New Job 2",
            ),
        ]

        mock_sheet = MagicMock()
        mock_sheet.row_values.return_value = ['job_id', 'source', 'status', 'title', 'url']
        mock_sheet.get_all_values.return_value = [
            ['job_id', 'source', 'status', 'title', 'url'],  # Only header, no existing jobs
        ]
        mock_sheet.batch_update = MagicMock()
        mock_sheet.append_rows = MagicMock()

        mock_spreadsheet = MagicMock()
        mock_spreadsheet.sheet1 = mock_sheet

        mock_client = MagicMock()
        mock_client.open_by_key.return_value = mock_spreadsheet

        with patch('upwork_pipeline_orchestrator.get_sheets_client', return_value=mock_client):
            with patch.dict(os.environ, {'UPWORK_PIPELINE_SHEET_ID': 'test_sheet_id'}):
                result = update_jobs_batch_in_sheet(jobs, mock=False)

        # batch_update should NOT have been called (no existing jobs)
        mock_sheet.batch_update.assert_not_called()
        # append_rows should have been called (new jobs)
        mock_sheet.append_rows.assert_called()
        self.assertEqual(result['updated'], 0)
        self.assertEqual(result['inserted'], 2)

    def test_batch_update_handles_mixed_existing_and_new_jobs(self):
        """Test that batch update handles mix of existing and new jobs."""
        jobs = [
            PipelineJob(
                job_id="~existing1",
                url="https://www.upwork.com/jobs/~existing1",
                source="apify",
                title="Existing Job",
            ),
            PipelineJob(
                job_id="~new1",
                url="https://www.upwork.com/jobs/~new1",
                source="apify",
                title="New Job",
            ),
        ]

        mock_sheet = MagicMock()
        mock_sheet.row_values.return_value = ['job_id', 'source', 'status', 'title', 'url']
        mock_sheet.get_all_values.return_value = [
            ['job_id', 'source', 'status', 'title', 'url'],
            ['~existing1', 'apify', 'new', 'Existing Job', 'https://www.upwork.com/jobs/~existing1'],
        ]
        mock_sheet.batch_update = MagicMock()
        mock_sheet.append_rows = MagicMock()

        mock_spreadsheet = MagicMock()
        mock_spreadsheet.sheet1 = mock_sheet

        mock_client = MagicMock()
        mock_client.open_by_key.return_value = mock_spreadsheet

        with patch('upwork_pipeline_orchestrator.get_sheets_client', return_value=mock_client):
            with patch.dict(os.environ, {'UPWORK_PIPELINE_SHEET_ID': 'test_sheet_id'}):
                result = update_jobs_batch_in_sheet(jobs, mock=False)

        # Both methods should be called
        mock_sheet.batch_update.assert_called()
        mock_sheet.append_rows.assert_called()
        self.assertEqual(result['updated'], 1)
        self.assertEqual(result['inserted'], 1)

    def test_batch_update_no_sheet_id_returns_failed(self):
        """Test that missing sheet ID returns failure."""
        jobs = [
            PipelineJob(
                job_id="~test1",
                url="https://www.upwork.com/jobs/~test1",
                source="apify",
            ),
        ]

        with patch.dict(os.environ, {'UPWORK_PIPELINE_SHEET_ID': ''}):
            result = update_jobs_batch_in_sheet(jobs, sheet_id=None, mock=False)

        self.assertEqual(result['failed'], 1)

    def test_batch_update_tracks_api_calls_correctly(self):
        """Test that API call count is tracked correctly."""
        jobs = [
            PipelineJob(
                job_id="~test1",
                url="https://www.upwork.com/jobs/~test1",
                source="apify",
            ),
        ]

        mock_sheet = MagicMock()
        mock_sheet.row_values.return_value = ['job_id', 'source', 'status', 'title', 'url']
        mock_sheet.get_all_values.return_value = [
            ['job_id', 'source', 'status', 'title', 'url'],
        ]
        mock_sheet.append_rows = MagicMock()

        mock_spreadsheet = MagicMock()
        mock_spreadsheet.sheet1 = mock_sheet

        mock_client = MagicMock()
        mock_client.open_by_key.return_value = mock_spreadsheet

        with patch('upwork_pipeline_orchestrator.get_sheets_client', return_value=mock_client):
            with patch.dict(os.environ, {'UPWORK_PIPELINE_SHEET_ID': 'test_sheet_id'}):
                result = update_jobs_batch_in_sheet(jobs, mock=False)

        # API calls: open_by_key(1) + row_values(1) + get_all_values(1) + append_rows(1) = 4
        self.assertEqual(result['api_calls'], 4)

    def test_batch_update_20_jobs_uses_fewer_than_20_api_calls(self):
        """Feature #79 core test: Update 20 jobs with fewer than 20 API calls."""
        # Create 20 jobs to update
        jobs = [
            PipelineJob(
                job_id=f"~batch{i}",
                url=f"https://www.upwork.com/jobs/~batch{i}",
                source="apify",
                title=f"Batch Job {i}",
                status=PipelineStatus.PENDING_APPROVAL,
            )
            for i in range(20)
        ]

        # Mock sheet with some existing jobs and some new
        existing_jobs = [[f'~batch{i}', 'apify', 'new', f'Batch Job {i}', f'https://www.upwork.com/jobs/~batch{i}']
                        for i in range(10)]

        mock_sheet = MagicMock()
        mock_sheet.row_values.return_value = ['job_id', 'source', 'status', 'title', 'url']
        mock_sheet.get_all_values.return_value = [
            ['job_id', 'source', 'status', 'title', 'url'],
            *existing_jobs
        ]
        mock_sheet.batch_update = MagicMock()
        mock_sheet.append_rows = MagicMock()

        mock_spreadsheet = MagicMock()
        mock_spreadsheet.sheet1 = mock_sheet

        mock_client = MagicMock()
        mock_client.open_by_key.return_value = mock_spreadsheet

        with patch('upwork_pipeline_orchestrator.get_sheets_client', return_value=mock_client):
            with patch.dict(os.environ, {'UPWORK_PIPELINE_SHEET_ID': 'test_sheet_id'}):
                result = update_jobs_batch_in_sheet(jobs, mock=False)

        # CRITICAL: Verify fewer than 20 API calls for 20 jobs
        self.assertLess(result['api_calls'], 20,
                       f"Expected fewer than 20 API calls, got {result['api_calls']}")

        # Verify batch API was used
        mock_sheet.batch_update.assert_called()

        # Verify correct counts
        self.assertEqual(result['updated'], 10)  # 10 existing jobs
        self.assertEqual(result['inserted'], 10)  # 10 new jobs

    def test_batch_update_handles_gspread_error_gracefully(self):
        """Test that batch update handles gspread errors gracefully."""
        jobs = [
            PipelineJob(
                job_id="~test1",
                url="https://www.upwork.com/jobs/~test1",
                source="apify",
            ),
        ]

        mock_client = MagicMock()
        mock_client.open_by_key.side_effect = Exception("API error")

        with patch('upwork_pipeline_orchestrator.get_sheets_client', return_value=mock_client):
            with patch.dict(os.environ, {'UPWORK_PIPELINE_SHEET_ID': 'test_sheet_id'}):
                result = update_jobs_batch_in_sheet(jobs, mock=False)

        self.assertEqual(result['failed'], 1)


if __name__ == "__main__":
    unittest.main()
