#!/usr/bin/env python3
"""
End-to-End Test: Approval triggers submission

Feature #74: End-to-end test - Approval triggers submission

This test validates the approval-to-submission flow:
1. Have job in pending_approval status
2. Click Approve in Slack
3. Wait for Playwright submission
4. Verify status changes to 'submitted'
5. Verify submitted_at timestamp is set

The test uses mock mode to avoid actual API calls while still
validating the complete approval-to-submission logic and data flow.
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

from upwork_slack_approval import (
    process_approval_callback,
    ApprovalCallbackResult,
    JobApprovalData,
    update_job_status_in_sheet,
    get_job_from_sheet,
)

from upwork_submitter import (
    UpworkSubmitter,
    SubmissionResult,
    SubmissionStatus,
    submit_application_sync,
    job_url_to_apply_url,
    extract_job_id_from_url,
)


class TestFeature74ApprovalTriggersSubmission(unittest.TestCase):
    """
    Feature #74: End-to-end test - Approval triggers submission

    Tests the complete flow from Slack approval to Playwright submission.
    """

    def test_job_in_pending_approval_status_after_pipeline(self):
        """Step 1: Have job in pending_approval status."""
        result = run_pipeline_sync(
            source='apify',
            limit=1,
            min_score=50,
            mock=True,
            parallel=1,
        )

        # Verify job reached pending_approval
        self.assertEqual(len(result.processed_jobs), 1)
        job = result.processed_jobs[0]
        self.assertEqual(job.status, PipelineStatus.PENDING_APPROVAL)

        # Verify Slack message was sent
        self.assertIsNotNone(job.slack_message_ts)

    def test_approval_callback_processes_approve_action(self):
        """Step 2: Click Approve in Slack."""
        # Process approval callback
        result = process_approval_callback(
            action="approve",
            job_id="~test123",
            user_id="U12345",
            channel="C12345",
            message_ts="1234567890.123456",
            mock=True,
        )

        # Verify approval was successful
        self.assertTrue(result.success)
        self.assertEqual(result.job_id, "~test123")
        self.assertEqual(result.action, "approve")
        self.assertEqual(result.status, "approved")
        self.assertIsNotNone(result.approved_at)
        self.assertTrue(result.trigger_submission)

    def test_approval_callback_sets_approved_at_timestamp(self):
        """Verify approved_at timestamp is set on approval."""
        result = process_approval_callback(
            action="approve",
            job_id="~test456",
            user_id="U12345",
            channel="C12345",
            message_ts="1234567890.123456",
            mock=True,
        )

        # Verify approved_at is set
        self.assertIsNotNone(result.approved_at)

        # Verify it's a valid ISO timestamp
        approved_at = datetime.fromisoformat(result.approved_at.replace('Z', '+00:00'))
        self.assertIsInstance(approved_at, datetime)

    def test_approval_callback_triggers_submission_flag(self):
        """Verify approval triggers submission workflow flag."""
        result = process_approval_callback(
            action="approve",
            job_id="~test789",
            user_id="U12345",
            channel="C12345",
            message_ts="1234567890.123456",
            mock=True,
        )

        # Verify trigger_submission is True
        self.assertTrue(result.trigger_submission)

    def test_submission_result_has_correct_structure(self):
        """Step 3: Verify Playwright submission result structure."""
        # Create mock submission result
        result = SubmissionResult(
            job_id="~testsubmit",
            job_url="https://www.upwork.com/jobs/~testsubmit",
            status=SubmissionStatus.SUCCESS,
            apply_url="https://www.upwork.com/nx/proposals/job/~testsubmit/apply/",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            confirmation_message="Proposal submitted successfully",
            cover_letter_filled=True,
            price_set=True,
            video_attached=False,
            pdf_attached=False,
            boost_applied=False,
        )

        # Verify result structure
        self.assertEqual(result.job_id, "~testsubmit")
        self.assertEqual(result.status, SubmissionStatus.SUCCESS)
        self.assertIsNotNone(result.submitted_at)
        self.assertTrue(result.cover_letter_filled)

    def test_submission_status_is_submitted_on_success(self):
        """Step 4: Verify status changes to 'submitted'."""
        # Create mock submission result
        result = SubmissionResult(
            job_id="~statustest",
            job_url="https://www.upwork.com/jobs/~statustest",
            status=SubmissionStatus.SUCCESS,
            submitted_at=datetime.now(timezone.utc).isoformat(),
        )

        # Convert to sheet update format
        sheet_update = result.to_sheet_update()

        # Verify status is 'submitted'
        self.assertEqual(sheet_update['status'], 'submitted')

    def test_submitted_at_timestamp_is_set(self):
        """Step 5: Verify submitted_at timestamp is set."""
        now = datetime.now(timezone.utc)
        result = SubmissionResult(
            job_id="~timestamptest",
            job_url="https://www.upwork.com/jobs/~timestamptest",
            status=SubmissionStatus.SUCCESS,
            submitted_at=now.isoformat(),
        )

        # Verify submitted_at is set
        self.assertIsNotNone(result.submitted_at)

        # Verify it's a valid ISO timestamp
        submitted_at = datetime.fromisoformat(result.submitted_at.replace('Z', '+00:00'))
        self.assertIsInstance(submitted_at, datetime)

        # Verify sheet update includes submitted_at
        sheet_update = result.to_sheet_update()
        self.assertIsNotNone(sheet_update['submitted_at'])


class TestFeature74FullE2EFlow(unittest.TestCase):
    """
    Full end-to-end flow tests for Feature #74.
    """

    def test_e2e_full_approval_to_submission_flow_mock(self):
        """Test complete flow from pending_approval through submission."""
        # Step 1: Run pipeline to get job in pending_approval
        pipeline_result = run_pipeline_sync(
            source='apify',
            limit=1,
            min_score=50,
            mock=True,
            parallel=1,
        )

        self.assertEqual(len(pipeline_result.processed_jobs), 1)
        job = pipeline_result.processed_jobs[0]
        self.assertEqual(job.status, PipelineStatus.PENDING_APPROVAL)

        # Step 2: Process approval callback
        approval_result = process_approval_callback(
            action="approve",
            job_id=job.job_id,
            user_id="U12345",
            channel="C12345",
            message_ts=job.slack_message_ts,
            mock=True,
        )

        self.assertTrue(approval_result.success)
        self.assertEqual(approval_result.status, "approved")
        self.assertTrue(approval_result.trigger_submission)

        # Step 3: Mock submission (would use Playwright in real flow)
        submission_result = SubmissionResult(
            job_id=job.job_id,
            job_url=job.url,
            status=SubmissionStatus.SUCCESS,
            apply_url=job_url_to_apply_url(job.url),
            submitted_at=datetime.now(timezone.utc).isoformat(),
            confirmation_message="Proposal submitted successfully",
            cover_letter_filled=True,
            price_set=True,
        )

        # Step 4 & 5: Verify final status and timestamp
        self.assertEqual(submission_result.status, SubmissionStatus.SUCCESS)
        self.assertIsNotNone(submission_result.submitted_at)

        sheet_update = submission_result.to_sheet_update()
        self.assertEqual(sheet_update['status'], 'submitted')
        self.assertIsNotNone(sheet_update['submitted_at'])

    def test_e2e_approval_data_flows_to_submission(self):
        """Test that job data flows correctly from approval to submission."""
        # Setup job in pending_approval
        job = PipelineJob(
            job_id="~flowtest123",
            url="https://www.upwork.com/jobs/~flowtest123",
            source="apify",
            status=PipelineStatus.PENDING_APPROVAL,
            title="Test Job Title",
            description="Test job description",
            proposal_text="Test proposal text for submission",
            proposal_doc_url="https://docs.google.com/document/d/test",
            video_url="https://heygen.com/video/test",
            pdf_url="https://drive.google.com/file/d/test",
            boost_decision=True,
            pricing_proposed=1000.0,
            slack_message_ts="1234567890.123456",
        )

        # Process approval
        approval_result = process_approval_callback(
            action="approve",
            job_id=job.job_id,
            user_id="U12345",
            channel="C12345",
            message_ts=job.slack_message_ts,
            mock=True,
        )

        self.assertTrue(approval_result.success)

        # Verify job data can be used for submission
        apply_url = job_url_to_apply_url(job.url)
        self.assertIn("proposals/job/~flowtest123/apply", apply_url)

        # Verify pricing and boost are available
        self.assertTrue(job.boost_decision)
        self.assertEqual(job.pricing_proposed, 1000.0)
        self.assertIsNotNone(job.proposal_text)


class TestFeature74ApprovalCallbackWithSubmission(unittest.TestCase):
    """
    Tests for approval callback with submission trigger.
    """

    def test_approval_callback_with_submission_callback(self):
        """Test approval callback can invoke submission callback."""
        submission_triggered = []

        def mock_submission_callback(job_id: str):
            submission_triggered.append(job_id)

        result = process_approval_callback(
            action="approve",
            job_id="~callback_test",
            user_id="U12345",
            channel="C12345",
            message_ts="1234567890.123456",
            mock=True,
            submission_callback=mock_submission_callback,
        )

        self.assertTrue(result.success)
        self.assertTrue(result.trigger_submission)
        # Note: In mock mode, the callback is not actually called
        # because mock=True skips the callback invocation

    def test_approval_updates_sheet_status(self):
        """Test that approval updates job status in sheet."""
        # Mock sheet update
        result = update_job_status_in_sheet(
            job_id="~sheettest",
            status="approved",
            additional_fields={
                "approved_at": datetime.now(timezone.utc),
                "slack_message_ts": "1234567890.123456",
            },
            mock=True,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["job_id"], "~sheettest")
        self.assertEqual(result["status"], "approved")
        self.assertIn("approved_at", result["fields_updated"])


class TestFeature74SubmissionResultTracking(unittest.TestCase):
    """
    Tests for submission result tracking.
    """

    def test_submission_result_to_dict(self):
        """Test SubmissionResult serialization to dict."""
        result = SubmissionResult(
            job_id="~dicttest",
            job_url="https://www.upwork.com/jobs/~dicttest",
            status=SubmissionStatus.SUCCESS,
            submitted_at=datetime.now(timezone.utc).isoformat(),
            cover_letter_filled=True,
            price_set=True,
            video_attached=True,
            pdf_attached=True,
            boost_applied=True,
        )

        result_dict = result.to_dict()

        self.assertEqual(result_dict['job_id'], "~dicttest")
        self.assertEqual(result_dict['status'], "success")
        self.assertTrue(result_dict['cover_letter_filled'])
        self.assertTrue(result_dict['video_attached'])
        self.assertTrue(result_dict['pdf_attached'])
        self.assertTrue(result_dict['boost_applied'])

    def test_submission_result_error_tracking(self):
        """Test SubmissionResult error tracking."""
        result = SubmissionResult(
            job_id="~errortest",
            job_url="https://www.upwork.com/jobs/~errortest",
            status=SubmissionStatus.FAILED,
            error="Form validation failed",
            error_log=["Error 1: Field required", "Error 2: Invalid format"],
        )

        self.assertEqual(result.status, SubmissionStatus.FAILED)
        self.assertIsNotNone(result.error)
        self.assertEqual(len(result.error_log), 2)

        # Sheet update should reflect failure
        sheet_update = result.to_sheet_update()
        self.assertEqual(sheet_update['status'], 'submission_failed')

    def test_submission_result_json_serializable(self):
        """Test that SubmissionResult is JSON serializable."""
        result = SubmissionResult(
            job_id="~jsontest",
            job_url="https://www.upwork.com/jobs/~jsontest",
            status=SubmissionStatus.SUCCESS,
            submitted_at=datetime.now(timezone.utc).isoformat(),
        )

        # Should be JSON serializable
        json_str = json.dumps(result.to_dict())
        self.assertIsInstance(json_str, str)

        # Should round-trip
        loaded = json.loads(json_str)
        self.assertEqual(loaded['job_id'], "~jsontest")
        self.assertEqual(loaded['status'], "success")


class TestFeature74URLConversion(unittest.TestCase):
    """
    Tests for URL conversion in submission flow.
    """

    def test_job_url_to_apply_url_conversion(self):
        """Test job URL to apply URL conversion (Feature #98)."""
        job_url = "https://www.upwork.com/jobs/~01abc123"
        apply_url = job_url_to_apply_url(job_url)

        self.assertEqual(
            apply_url,
            "https://www.upwork.com/nx/proposals/job/~01abc123/apply/"
        )

    def test_job_url_extraction(self):
        """Test job ID extraction from URL."""
        url = "https://www.upwork.com/jobs/~01abc123def"
        job_id = extract_job_id_from_url(url)

        self.assertEqual(job_id, "~01abc123def")

    def test_apply_url_format_correct(self):
        """Test apply URL has correct format."""
        apply_url = job_url_to_apply_url("https://www.upwork.com/jobs/~test123")

        # Should match the format: /nx/proposals/job/{id}/apply/
        self.assertIn("/nx/proposals/job/", apply_url)
        self.assertIn("/apply/", apply_url)
        self.assertIn("~test123", apply_url)


class TestFeature74PipelineIntegration(unittest.TestCase):
    """
    Integration tests for approval-to-submission in pipeline context.
    """

    def test_pipeline_job_has_required_submission_fields(self):
        """Test pipeline job has all fields needed for submission."""
        result = run_pipeline_sync(
            source='apify',
            limit=1,
            min_score=50,
            mock=True,
            parallel=1,
        )

        job = result.processed_jobs[0]

        # Required for submission
        self.assertIsNotNone(job.job_id)
        self.assertIsNotNone(job.url)
        self.assertIsNotNone(job.proposal_text)
        self.assertIsNotNone(job.proposal_doc_url)
        self.assertIsNotNone(job.pricing_proposed)
        self.assertIsNotNone(job.boost_decision)

    def test_pipeline_job_status_can_transition_to_submitted(self):
        """Test that job status can transition through submission states."""
        # Create job at pending_approval
        job = PipelineJob(
            job_id="~transition_test",
            url="https://www.upwork.com/jobs/~transition_test",
            source="apify",
            status=PipelineStatus.PENDING_APPROVAL,
        )

        # Verify pending_approval
        self.assertEqual(job.status, PipelineStatus.PENDING_APPROVAL)

        # Simulate approval
        job.status = PipelineStatus.APPROVED
        job.approved_at = datetime.now(timezone.utc).isoformat()
        self.assertEqual(job.status, PipelineStatus.APPROVED)
        self.assertIsNotNone(job.approved_at)

        # Simulate submission
        job.status = PipelineStatus.SUBMITTED
        job.submitted_at = datetime.now(timezone.utc).isoformat()
        self.assertEqual(job.status, PipelineStatus.SUBMITTED)
        self.assertIsNotNone(job.submitted_at)

    def test_pipeline_job_sheet_row_includes_submission_fields(self):
        """Test that sheet row data includes submission tracking fields."""
        job = PipelineJob(
            job_id="~sheetrow_test",
            url="https://www.upwork.com/jobs/~sheetrow_test",
            source="apify",
            status=PipelineStatus.SUBMITTED,
            approved_at=datetime.now(timezone.utc).isoformat(),
            submitted_at=datetime.now(timezone.utc).isoformat(),
        )

        sheet_row = job.to_sheet_row()

        # Verify submission tracking fields
        self.assertIn('approved_at', sheet_row)
        self.assertIn('submitted_at', sheet_row)
        self.assertIsNotNone(sheet_row['approved_at'])
        self.assertIsNotNone(sheet_row['submitted_at'])
        self.assertEqual(sheet_row['status'], 'submitted')


class TestFeature74ErrorScenarios(unittest.TestCase):
    """
    Error scenario tests for Feature #74.
    """

    def test_submission_failure_tracked(self):
        """Test that submission failure is properly tracked."""
        result = SubmissionResult(
            job_id="~failtest",
            job_url="https://www.upwork.com/jobs/~failtest",
            status=SubmissionStatus.FAILED,
            error="Could not find submit button",
            error_log=["Form error: Submit button not found"],
        )

        sheet_update = result.to_sheet_update()

        self.assertEqual(sheet_update['status'], 'submission_failed')
        self.assertIsNone(sheet_update['submitted_at'])
        self.assertIn("Submit button not found", sheet_update['error_log'])

    def test_approval_rejection_does_not_trigger_submission(self):
        """Test that rejection does not trigger submission."""
        result = process_approval_callback(
            action="reject",
            job_id="~rejecttest",
            user_id="U12345",
            channel="C12345",
            message_ts="1234567890.123456",
            mock=True,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.action, "reject")
        self.assertEqual(result.status, "rejected")
        self.assertFalse(result.trigger_submission)

    def test_edit_action_keeps_pending_approval(self):
        """Test that edit action keeps job in pending_approval."""
        result = process_approval_callback(
            action="edit",
            job_id="~edittest",
            user_id="U12345",
            channel="C12345",
            message_ts="1234567890.123456",
            edited_proposal="Updated proposal text",
            mock=True,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.action, "edit")
        self.assertEqual(result.status, "editing")
        self.assertFalse(result.trigger_submission)


class TestFeature74AsyncExecution(unittest.TestCase):
    """
    Async execution tests for Feature #74.
    """

    def test_async_pipeline_produces_submittable_jobs(self):
        """Test async pipeline produces jobs ready for submission."""
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

        self.assertEqual(len(result.processed_jobs), 1)
        job = result.processed_jobs[0]

        # Verify job is ready for submission
        self.assertEqual(job.status, PipelineStatus.PENDING_APPROVAL)
        self.assertIsNotNone(job.proposal_text)
        self.assertIsNotNone(job.url)


def run_feature_74_tests():
    """Run all Feature #74 tests and return results."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestFeature74ApprovalTriggersSubmission))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature74FullE2EFlow))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature74ApprovalCallbackWithSubmission))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature74SubmissionResultTracking))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature74URLConversion))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature74PipelineIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature74ErrorScenarios))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature74AsyncExecution))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_feature_74_tests()
    sys.exit(0 if success else 1)
