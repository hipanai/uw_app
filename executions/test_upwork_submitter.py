#!/usr/bin/env python3
"""
Unit tests for Upwork Submitter.

Tests Features #52-61:
- #52: Navigate to Upwork apply page
- #53: Fill cover letter field
- #54: Attach video file
- #55: Attach PDF file
- #56: Set proposed rate/price
- #57: Apply boost if recommended
- #58: Click submit button
- #59: Detect successful submission
- #60: Handle submission errors
- #61: Use persistent browser profile
"""

import os
import sys
import json
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from upwork_submitter import (
    UpworkSubmitter,
    SubmissionResult,
    SubmissionStatus,
    extract_job_id_from_url,
    job_url_to_apply_url,
    job_id_to_apply_url,
)


class TestJobIdExtraction(unittest.TestCase):
    """Test job ID extraction from URLs."""

    def test_extract_from_jobs_url(self):
        """Test extraction from standard job URL."""
        url = "https://www.upwork.com/jobs/~01abc123def456"
        job_id = extract_job_id_from_url(url)
        self.assertEqual(job_id, "~01abc123def456")

    def test_extract_from_apply_url(self):
        """Test extraction from apply URL."""
        url = "https://www.upwork.com/nx/proposals/job/~01abc123def456/apply/"
        job_id = extract_job_id_from_url(url)
        self.assertEqual(job_id, "~01abc123def456")

    def test_extract_from_freelance_jobs_url(self):
        """Test extraction from freelance jobs URL."""
        url = "https://www.upwork.com/freelance-jobs/apply/some-job-title_~01abc123"
        job_id = extract_job_id_from_url(url)
        self.assertEqual(job_id, "~01abc123")

    def test_invalid_url_raises_error(self):
        """Test that invalid URL raises ValueError."""
        url = "https://www.upwork.com/some-other-page"
        with self.assertRaises(ValueError):
            extract_job_id_from_url(url)

    def test_case_insensitive_extraction(self):
        """Test that extraction is case insensitive."""
        url = "https://www.upwork.com/jobs/~01AbCdEf"
        job_id = extract_job_id_from_url(url)
        self.assertEqual(job_id, "~01AbCdEf")


class TestUrlConversion(unittest.TestCase):
    """Test URL conversion functions - Feature #98."""

    def test_job_url_to_apply_url(self):
        """Test converting job URL to apply URL."""
        job_url = "https://www.upwork.com/jobs/~01abc123"
        apply_url = job_url_to_apply_url(job_url)
        self.assertEqual(apply_url, "https://www.upwork.com/nx/proposals/job/~01abc123/apply/")

    def test_job_url_with_title(self):
        """Test converting job URL that includes title."""
        job_url = "https://www.upwork.com/jobs/Some-Job-Title_~01abc123"
        apply_url = job_url_to_apply_url(job_url)
        self.assertEqual(apply_url, "https://www.upwork.com/nx/proposals/job/~01abc123/apply/")

    def test_job_id_to_apply_url(self):
        """Test converting job ID to apply URL."""
        job_id = "~01abc123"
        apply_url = job_id_to_apply_url(job_id)
        self.assertEqual(apply_url, "https://www.upwork.com/nx/proposals/job/~01abc123/apply/")

    def test_job_id_without_tilde(self):
        """Test converting job ID without tilde prefix."""
        job_id = "01abc123"
        apply_url = job_id_to_apply_url(job_id)
        self.assertEqual(apply_url, "https://www.upwork.com/nx/proposals/job/~01abc123/apply/")


class TestSubmissionResult(unittest.TestCase):
    """Test SubmissionResult dataclass."""

    def test_default_values(self):
        """Test default values."""
        result = SubmissionResult(
            job_id="~01abc123",
            job_url="https://www.upwork.com/jobs/~01abc123"
        )
        self.assertEqual(result.status, SubmissionStatus.PENDING)
        self.assertIsNone(result.error)
        self.assertEqual(result.error_log, [])
        self.assertFalse(result.cover_letter_filled)
        self.assertFalse(result.price_set)
        self.assertFalse(result.video_attached)
        self.assertFalse(result.pdf_attached)
        self.assertFalse(result.boost_applied)

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = SubmissionResult(
            job_id="~01abc123",
            job_url="https://www.upwork.com/jobs/~01abc123",
            status=SubmissionStatus.SUCCESS,
            submitted_at="2024-01-01T12:00:00"
        )
        d = result.to_dict()
        self.assertEqual(d['job_id'], "~01abc123")
        self.assertEqual(d['status'], "success")
        self.assertEqual(d['submitted_at'], "2024-01-01T12:00:00")

    def test_to_sheet_update_success(self):
        """Test sheet update format for success."""
        result = SubmissionResult(
            job_id="~01abc123",
            job_url="https://www.upwork.com/jobs/~01abc123",
            status=SubmissionStatus.SUCCESS,
            submitted_at="2024-01-01T12:00:00"
        )
        update = result.to_sheet_update()
        self.assertEqual(update['status'], 'submitted')
        self.assertEqual(update['submitted_at'], "2024-01-01T12:00:00")

    def test_to_sheet_update_failed(self):
        """Test sheet update format for failure."""
        result = SubmissionResult(
            job_id="~01abc123",
            job_url="https://www.upwork.com/jobs/~01abc123",
            status=SubmissionStatus.FAILED,
            error_log=["Error 1", "Error 2"]
        )
        update = result.to_sheet_update()
        self.assertEqual(update['status'], 'submission_failed')
        self.assertIn("Error 1", update['error_log'])


class TestSubmitterInitialization(unittest.TestCase):
    """Test UpworkSubmitter initialization - Feature #61."""

    def test_requires_user_data_dir(self):
        """Test that user_data_dir is required."""
        with self.assertRaises(ValueError):
            UpworkSubmitter(user_data_dir=None)

    def test_accepts_user_data_dir(self):
        """Test that submitter accepts user_data_dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            submitter = UpworkSubmitter(user_data_dir=tmpdir)
            self.assertEqual(submitter.user_data_dir, tmpdir)

    def test_default_headless(self):
        """Test default headless mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            submitter = UpworkSubmitter(user_data_dir=tmpdir)
            self.assertTrue(submitter.headless)

    def test_custom_timeout(self):
        """Test custom timeout setting."""
        with tempfile.TemporaryDirectory() as tmpdir:
            submitter = UpworkSubmitter(user_data_dir=tmpdir, timeout=30000)
            self.assertEqual(submitter.timeout, 30000)

    def test_tmp_dir_created(self):
        """Test that tmp directory is created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = os.path.join(tmpdir, "test_tmp")
            submitter = UpworkSubmitter(user_data_dir=tmpdir, tmp_dir=tmp_path)
            self.assertTrue(os.path.exists(tmp_path))


class TestFeature52NavigateToApplyPage(unittest.TestCase):
    """Test Feature #52: Navigate to Upwork apply page."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.submitter = UpworkSubmitter(user_data_dir=self.tmpdir)

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch('upwork_submitter.async_playwright')
    async def test_navigate_to_apply_page_success(self, mock_playwright):
        """Test successful navigation to apply page."""
        # Mock page
        mock_page = AsyncMock()
        mock_page.url = "https://www.upwork.com/nx/proposals/job/~01abc123/apply/"
        mock_page.goto = AsyncMock()
        mock_page.wait_for_selector = AsyncMock(return_value=MagicMock())

        # Mock context
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        self.submitter._context = mock_context
        self.submitter._page = None

        result = await self.submitter.navigate_to_apply_page(
            "https://www.upwork.com/jobs/~01abc123"
        )

        self.assertEqual(result.status, SubmissionStatus.NAVIGATED)
        self.assertEqual(result.job_id, "~01abc123")
        self.assertEqual(result.apply_url, "https://www.upwork.com/nx/proposals/job/~01abc123/apply/")

    @patch('upwork_submitter.async_playwright')
    async def test_navigate_detects_login_redirect(self, mock_playwright):
        """Test detection of login redirect."""
        mock_page = AsyncMock()
        mock_page.url = "https://www.upwork.com/login"
        mock_page.goto = AsyncMock()
        mock_page.wait_for_selector = AsyncMock(return_value=None)

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        self.submitter._context = mock_context

        result = await self.submitter.navigate_to_apply_page(
            "https://www.upwork.com/jobs/~01abc123"
        )

        self.assertEqual(result.status, SubmissionStatus.ERROR)
        self.assertIn("Login required", result.error)

    def test_navigate_handles_invalid_url(self):
        """Test handling of invalid job URL."""
        import asyncio

        async def _test():
            self.submitter._context = AsyncMock()
            result = await self.submitter.navigate_to_apply_page(
                "https://www.upwork.com/invalid-page"
            )
            return result

        result = asyncio.get_event_loop().run_until_complete(_test())
        self.assertEqual(result.status, SubmissionStatus.ERROR)
        self.assertEqual(result.job_id, "unknown")


class TestFeature53FillCoverLetter(unittest.TestCase):
    """Test Feature #53: Fill cover letter field."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.submitter = UpworkSubmitter(user_data_dir=self.tmpdir)

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch('upwork_submitter.async_playwright')
    async def test_fill_cover_letter_success(self, mock_playwright):
        """Test successful cover letter fill."""
        # Mock element
        mock_element = AsyncMock()
        mock_element.click = AsyncMock()
        mock_element.fill = AsyncMock()

        # Mock page
        mock_page = AsyncMock()
        mock_page.wait_for_selector = AsyncMock(return_value=mock_element)

        self.submitter._page = mock_page

        result = SubmissionResult(
            job_id="~01abc123",
            job_url="https://www.upwork.com/jobs/~01abc123"
        )

        result = await self.submitter.fill_cover_letter(result, "Test proposal text")

        self.assertTrue(result.cover_letter_filled)
        mock_element.fill.assert_called_once_with("Test proposal text")

    @patch('upwork_submitter.async_playwright')
    async def test_fill_cover_letter_element_not_found(self, mock_playwright):
        """Test handling when cover letter element not found."""
        mock_page = AsyncMock()
        mock_page.wait_for_selector = AsyncMock(return_value=None)

        self.submitter._page = mock_page

        result = SubmissionResult(
            job_id="~01abc123",
            job_url="https://www.upwork.com/jobs/~01abc123"
        )

        result = await self.submitter.fill_cover_letter(result, "Test text")

        self.assertFalse(result.cover_letter_filled)
        self.assertTrue(len(result.error_log) > 0)

    async def test_fill_cover_letter_no_page(self):
        """Test error when no page available."""
        self.submitter._page = None

        result = SubmissionResult(
            job_id="~01abc123",
            job_url="https://www.upwork.com/jobs/~01abc123"
        )

        result = await self.submitter.fill_cover_letter(result, "Test text")

        self.assertEqual(result.status, SubmissionStatus.ERROR)


class TestFeature54AttachVideo(unittest.TestCase):
    """Test Feature #54: Attach video file."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.submitter = UpworkSubmitter(user_data_dir=self.tmpdir)

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch('upwork_submitter.async_playwright')
    async def test_attach_video_success(self, mock_playwright):
        """Test successful video attachment."""
        # Create a test file
        video_path = os.path.join(self.tmpdir, "test_video.mp4")
        with open(video_path, 'w') as f:
            f.write("fake video content")

        mock_input = AsyncMock()
        mock_input.set_input_files = AsyncMock()

        mock_page = AsyncMock()
        mock_page.wait_for_selector = AsyncMock(return_value=mock_input)

        self.submitter._page = mock_page

        result = SubmissionResult(
            job_id="~01abc123",
            job_url="https://www.upwork.com/jobs/~01abc123"
        )

        result = await self.submitter.attach_file(result, video_path, "video")

        self.assertTrue(result.video_attached)
        mock_input.set_input_files.assert_called_once_with(video_path)

    async def test_attach_video_file_not_found(self):
        """Test handling when video file not found."""
        mock_page = AsyncMock()
        self.submitter._page = mock_page

        result = SubmissionResult(
            job_id="~01abc123",
            job_url="https://www.upwork.com/jobs/~01abc123"
        )

        result = await self.submitter.attach_file(result, "/nonexistent/video.mp4", "video")

        self.assertFalse(result.video_attached)
        self.assertTrue(any("not found" in err.lower() for err in result.error_log))


class TestFeature55AttachPDF(unittest.TestCase):
    """Test Feature #55: Attach PDF file."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.submitter = UpworkSubmitter(user_data_dir=self.tmpdir)

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch('upwork_submitter.async_playwright')
    async def test_attach_pdf_success(self, mock_playwright):
        """Test successful PDF attachment."""
        # Create a test file
        pdf_path = os.path.join(self.tmpdir, "test.pdf")
        with open(pdf_path, 'w') as f:
            f.write("fake pdf content")

        mock_input = AsyncMock()
        mock_input.set_input_files = AsyncMock()

        mock_page = AsyncMock()
        mock_page.wait_for_selector = AsyncMock(return_value=mock_input)

        self.submitter._page = mock_page

        result = SubmissionResult(
            job_id="~01abc123",
            job_url="https://www.upwork.com/jobs/~01abc123"
        )

        result = await self.submitter.attach_file(result, pdf_path, "pdf")

        self.assertTrue(result.pdf_attached)


class TestFeature56SetProposedPrice(unittest.TestCase):
    """Test Feature #56: Set proposed rate/price."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.submitter = UpworkSubmitter(user_data_dir=self.tmpdir)

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch('upwork_submitter.async_playwright')
    async def test_set_hourly_rate_success(self, mock_playwright):
        """Test setting hourly rate."""
        mock_element = AsyncMock()
        mock_element.click = AsyncMock()
        mock_element.fill = AsyncMock()

        mock_page = AsyncMock()
        mock_page.wait_for_selector = AsyncMock(return_value=mock_element)

        self.submitter._page = mock_page

        result = SubmissionResult(
            job_id="~01abc123",
            job_url="https://www.upwork.com/jobs/~01abc123"
        )

        result = await self.submitter.set_proposed_price(result, 75.00, is_hourly=True)

        self.assertTrue(result.price_set)
        mock_element.fill.assert_called_with("75.0")

    @patch('upwork_submitter.async_playwright')
    async def test_set_fixed_price_success(self, mock_playwright):
        """Test setting fixed price."""
        mock_element = AsyncMock()
        mock_element.click = AsyncMock()
        mock_element.fill = AsyncMock()

        mock_page = AsyncMock()
        mock_page.wait_for_selector = AsyncMock(return_value=mock_element)

        self.submitter._page = mock_page

        result = SubmissionResult(
            job_id="~01abc123",
            job_url="https://www.upwork.com/jobs/~01abc123"
        )

        result = await self.submitter.set_proposed_price(result, 500.00, is_hourly=False)

        self.assertTrue(result.price_set)


class TestFeature57ApplyBoost(unittest.TestCase):
    """Test Feature #57: Apply boost if recommended."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.submitter = UpworkSubmitter(user_data_dir=self.tmpdir)

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch('upwork_submitter.async_playwright')
    async def test_apply_boost_success(self, mock_playwright):
        """Test applying boost."""
        mock_element = AsyncMock()
        mock_element.click = AsyncMock()
        mock_element.is_checked = AsyncMock(return_value=False)

        mock_page = AsyncMock()
        mock_page.wait_for_selector = AsyncMock(return_value=mock_element)

        self.submitter._page = mock_page

        result = SubmissionResult(
            job_id="~01abc123",
            job_url="https://www.upwork.com/jobs/~01abc123"
        )

        result = await self.submitter.apply_boost(result, should_boost=True)

        self.assertTrue(result.boost_applied)

    async def test_no_boost_when_not_recommended(self):
        """Test no boost applied when not recommended."""
        self.submitter._page = AsyncMock()

        result = SubmissionResult(
            job_id="~01abc123",
            job_url="https://www.upwork.com/jobs/~01abc123"
        )

        result = await self.submitter.apply_boost(result, should_boost=False)

        self.assertFalse(result.boost_applied)


class TestFeature58SubmitProposal(unittest.TestCase):
    """Test Feature #58: Click submit button."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.submitter = UpworkSubmitter(user_data_dir=self.tmpdir)

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch('upwork_submitter.async_playwright')
    async def test_submit_button_clicked(self, mock_playwright):
        """Test that submit button is clicked."""
        mock_submit = AsyncMock()
        mock_submit.click = AsyncMock()

        mock_success = AsyncMock()
        mock_success.inner_text = AsyncMock(return_value="Proposal submitted!")

        mock_page = AsyncMock()
        mock_page.url = "https://www.upwork.com/nx/proposals/success"

        # First call finds submit button, second finds success message
        mock_page.wait_for_selector = AsyncMock(side_effect=[mock_submit, mock_success])

        self.submitter._page = mock_page

        result = SubmissionResult(
            job_id="~01abc123",
            job_url="https://www.upwork.com/jobs/~01abc123",
            cover_letter_filled=True
        )

        result = await self.submitter.submit_proposal(result)

        mock_submit.click.assert_called_once()


class TestFeature59DetectSuccess(unittest.TestCase):
    """Test Feature #59: Detect successful submission."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.submitter = UpworkSubmitter(user_data_dir=self.tmpdir)

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch('upwork_submitter.async_playwright')
    async def test_detect_success_message(self, mock_playwright):
        """Test detection of success message."""
        mock_submit = AsyncMock()
        mock_submit.click = AsyncMock()

        mock_success = AsyncMock()
        mock_success.inner_text = AsyncMock(return_value="Your proposal has been submitted")

        mock_page = AsyncMock()
        mock_page.url = "https://www.upwork.com/nx/proposals/job/~01abc123/apply/"
        mock_page.wait_for_selector = AsyncMock(side_effect=[mock_submit, mock_success])

        self.submitter._page = mock_page

        result = SubmissionResult(
            job_id="~01abc123",
            job_url="https://www.upwork.com/jobs/~01abc123",
            cover_letter_filled=True
        )

        result = await self.submitter.submit_proposal(result)

        self.assertEqual(result.status, SubmissionStatus.SUCCESS)
        self.assertIsNotNone(result.submitted_at)
        self.assertEqual(result.confirmation_message, "Your proposal has been submitted")

    @patch('upwork_submitter.async_playwright')
    async def test_detect_success_via_url_redirect(self, mock_playwright):
        """Test detection of success via URL redirect."""
        mock_submit = AsyncMock()
        mock_submit.click = AsyncMock()

        mock_page = AsyncMock()
        mock_page.url = "https://www.upwork.com/nx/proposals/submitted"
        mock_page.wait_for_selector = AsyncMock(side_effect=[mock_submit, None, None])

        self.submitter._page = mock_page

        result = SubmissionResult(
            job_id="~01abc123",
            job_url="https://www.upwork.com/jobs/~01abc123",
            cover_letter_filled=True
        )

        result = await self.submitter.submit_proposal(result)

        # Should detect success from URL containing "proposals"
        self.assertEqual(result.status, SubmissionStatus.SUCCESS)


class TestFeature60HandleErrors(unittest.TestCase):
    """Test Feature #60: Handle submission errors."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.submitter = UpworkSubmitter(user_data_dir=self.tmpdir)

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch('upwork_submitter.async_playwright')
    async def test_detect_form_error(self, mock_playwright):
        """Test detection of form errors."""
        mock_submit = AsyncMock()
        mock_submit.click = AsyncMock()

        mock_error = AsyncMock()
        mock_error.inner_text = AsyncMock(return_value="Please enter a valid bid amount")

        mock_page = AsyncMock()
        mock_page.url = "https://www.upwork.com/nx/proposals/job/~01abc123/apply/"
        # Submit found, success not found, error found
        mock_page.wait_for_selector = AsyncMock(side_effect=[mock_submit, None, mock_error])

        self.submitter._page = mock_page

        result = SubmissionResult(
            job_id="~01abc123",
            job_url="https://www.upwork.com/jobs/~01abc123",
            cover_letter_filled=True
        )

        result = await self.submitter.submit_proposal(result)

        self.assertEqual(result.status, SubmissionStatus.FAILED)
        self.assertEqual(result.error, "Please enter a valid bid amount")
        self.assertTrue(len(result.error_log) > 0)

    @patch('upwork_submitter.async_playwright')
    async def test_handle_submit_button_not_found(self, mock_playwright):
        """Test handling when submit button not found."""
        mock_page = AsyncMock()
        mock_page.wait_for_selector = AsyncMock(return_value=None)

        self.submitter._page = mock_page

        result = SubmissionResult(
            job_id="~01abc123",
            job_url="https://www.upwork.com/jobs/~01abc123"
        )

        result = await self.submitter.submit_proposal(result)

        self.assertEqual(result.status, SubmissionStatus.ERROR)
        self.assertIn("submit button", result.error.lower())

    async def test_error_log_populated(self):
        """Test that errors are logged to error_log."""
        self.submitter._page = AsyncMock()
        self.submitter._page.wait_for_selector = AsyncMock(side_effect=Exception("Network error"))

        result = SubmissionResult(
            job_id="~01abc123",
            job_url="https://www.upwork.com/jobs/~01abc123"
        )

        result = await self.submitter.submit_proposal(result)

        self.assertEqual(result.status, SubmissionStatus.ERROR)
        self.assertTrue(len(result.error_log) > 0)


class TestFeature61PersistentProfile(unittest.TestCase):
    """Test Feature #61: Use persistent browser profile."""

    def test_persistent_profile_required(self):
        """Test that persistent profile is required."""
        with self.assertRaises(ValueError):
            UpworkSubmitter(user_data_dir=None)

    def test_persistent_profile_path_stored(self):
        """Test that profile path is stored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            submitter = UpworkSubmitter(user_data_dir=tmpdir)
            self.assertEqual(submitter.user_data_dir, tmpdir)

    @patch('upwork_submitter.async_playwright')
    async def test_persistent_context_launched(self, mock_playwright):
        """Test that persistent context is launched."""
        with tempfile.TemporaryDirectory() as tmpdir:
            submitter = UpworkSubmitter(user_data_dir=tmpdir)

            mock_context = AsyncMock()
            mock_chromium = AsyncMock()
            mock_chromium.launch_persistent_context = AsyncMock(return_value=mock_context)

            mock_pw = AsyncMock()
            mock_pw.chromium = mock_chromium

            mock_playwright.return_value.start = AsyncMock(return_value=mock_pw)

            await submitter._init_browser()

            mock_chromium.launch_persistent_context.assert_called_once()
            call_args = mock_chromium.launch_persistent_context.call_args
            self.assertEqual(call_args[0][0], tmpdir)


class TestFullSubmissionWorkflow(unittest.TestCase):
    """Test complete submission workflow."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.submitter = UpworkSubmitter(user_data_dir=self.tmpdir)

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch('upwork_submitter.async_playwright')
    async def test_full_workflow_success(self, mock_playwright):
        """Test full submission workflow success."""
        # Create test files
        video_path = os.path.join(self.tmpdir, "video.mp4")
        pdf_path = os.path.join(self.tmpdir, "proposal.pdf")
        with open(video_path, 'w') as f:
            f.write("video")
        with open(pdf_path, 'w') as f:
            f.write("pdf")

        # Mock all elements
        mock_element = AsyncMock()
        mock_element.click = AsyncMock()
        mock_element.fill = AsyncMock()
        mock_element.set_input_files = AsyncMock()
        mock_element.is_checked = AsyncMock(return_value=False)

        mock_success = AsyncMock()
        mock_success.inner_text = AsyncMock(return_value="Proposal submitted!")

        mock_page = AsyncMock()
        mock_page.url = "https://www.upwork.com/nx/proposals/job/~01abc123/apply/"
        mock_page.goto = AsyncMock()
        mock_page.screenshot = AsyncMock()

        # Return mock element for all queries except specific success check
        async def mock_wait(selector, **kwargs):
            if "success" in selector.lower() or "submitted" in selector.lower():
                return mock_success
            return mock_element

        mock_page.wait_for_selector = mock_wait

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        self.submitter._context = mock_context

        result = await self.submitter.submit_full_application(
            job_url="https://www.upwork.com/jobs/~01abc123",
            proposal_text="This is my proposal",
            pricing_proposed=75.00,
            is_hourly=True,
            video_path=video_path,
            pdf_path=pdf_path,
            should_boost=True,
            capture_screenshots=False,
        )

        self.assertEqual(result.status, SubmissionStatus.SUCCESS)
        self.assertTrue(result.cover_letter_filled)
        self.assertTrue(result.price_set)
        self.assertTrue(result.video_attached)
        self.assertTrue(result.pdf_attached)
        self.assertTrue(result.boost_applied)


class TestSelectors(unittest.TestCase):
    """Test that all required selectors are defined."""

    def test_cover_letter_selectors(self):
        """Test cover letter selectors exist."""
        self.assertIn('cover_letter', UpworkSubmitter.SELECTORS)
        self.assertTrue(len(UpworkSubmitter.SELECTORS['cover_letter']) > 0)

    def test_rate_input_selectors(self):
        """Test rate input selectors exist."""
        self.assertIn('rate_input', UpworkSubmitter.SELECTORS)
        self.assertTrue(len(UpworkSubmitter.SELECTORS['rate_input']) > 0)

    def test_file_input_selectors(self):
        """Test file input selectors exist."""
        self.assertIn('file_input', UpworkSubmitter.SELECTORS)
        self.assertTrue(len(UpworkSubmitter.SELECTORS['file_input']) > 0)

    def test_submit_button_selectors(self):
        """Test submit button selectors exist."""
        self.assertIn('submit_button', UpworkSubmitter.SELECTORS)
        self.assertTrue(len(UpworkSubmitter.SELECTORS['submit_button']) > 0)

    def test_success_message_selectors(self):
        """Test success message selectors exist."""
        self.assertIn('success_message', UpworkSubmitter.SELECTORS)
        self.assertTrue(len(UpworkSubmitter.SELECTORS['success_message']) > 0)

    def test_error_message_selectors(self):
        """Test error message selectors exist."""
        self.assertIn('error_message', UpworkSubmitter.SELECTORS)
        self.assertTrue(len(UpworkSubmitter.SELECTORS['error_message']) > 0)


def run_async_test(coro):
    """Helper to run async tests."""
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# Convert async tests to sync for unittest
for cls in [
    TestFeature52NavigateToApplyPage,
    TestFeature53FillCoverLetter,
    TestFeature54AttachVideo,
    TestFeature55AttachPDF,
    TestFeature56SetProposedPrice,
    TestFeature57ApplyBoost,
    TestFeature58SubmitProposal,
    TestFeature59DetectSuccess,
    TestFeature60HandleErrors,
    TestFeature61PersistentProfile,
    TestFullSubmissionWorkflow,
]:
    for name in dir(cls):
        if name.startswith('test_'):
            method = getattr(cls, name)
            if asyncio.iscoroutinefunction(method):
                def make_sync(async_method):
                    def sync_method(self):
                        return run_async_test(async_method(self))
                    return sync_method
                setattr(cls, name, make_sync(method))


if __name__ == '__main__':
    # Run tests
    unittest.main(verbosity=2)
