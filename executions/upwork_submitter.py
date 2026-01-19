#!/usr/bin/env python3
"""
Upwork Submitter - Playwright-based job application submission.

Features #52-61: Handles the final submission of Upwork job applications:
- Navigate to job apply page
- Fill cover letter
- Attach video and PDF files
- Set proposed rate/price
- Apply boost if recommended
- Submit application
- Detect success/failure

Usage:
    python upwork_submitter.py --job-id "~01abc123" --proposal-text "..." --profile "/path/to/profile"
    python upwork_submitter.py --job-url "https://www.upwork.com/jobs/~01abc123" --proposal-text "..."
"""

import os
import re
import json
import time
import asyncio
import argparse
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum


class SubmissionStatus(Enum):
    """Status of the submission attempt."""
    PENDING = "pending"
    NAVIGATED = "navigated"
    FORM_FILLED = "form_filled"
    SUBMITTED = "submitted"
    SUCCESS = "success"
    FAILED = "failed"
    ERROR = "error"


@dataclass
class SubmissionResult:
    """Result of a submission attempt."""
    job_id: str
    job_url: str
    status: SubmissionStatus = SubmissionStatus.PENDING
    apply_url: Optional[str] = None
    error: Optional[str] = None
    error_log: list[str] = field(default_factory=list)
    screenshot_path: Optional[str] = None
    submitted_at: Optional[str] = None
    confirmation_message: Optional[str] = None

    # Form fill tracking
    cover_letter_filled: bool = False
    price_set: bool = False
    video_attached: bool = False
    pdf_attached: bool = False
    boost_applied: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        result['status'] = self.status.value
        return result

    def to_sheet_update(self) -> dict:
        """Convert to flat dictionary for Google Sheets update."""
        return {
            'status': 'submitted' if self.status == SubmissionStatus.SUCCESS else 'submission_failed',
            'submitted_at': self.submitted_at,
            'error_log': json.dumps(self.error_log) if self.error_log else None,
        }


def extract_job_id_from_url(url: str) -> str:
    """Extract job ID from Upwork URL."""
    match = re.search(r'~([a-f0-9]+)', url, re.IGNORECASE)
    if match:
        return f"~{match.group(1)}"
    raise ValueError(f"Could not extract job ID from URL: {url}")


def job_url_to_apply_url(job_url: str) -> str:
    """Convert job URL to apply page URL.

    Feature #98: Job URL format conversion
    Input: https://www.upwork.com/jobs/~123
    Output: https://www.upwork.com/nx/proposals/job/~123/apply/
    """
    job_id = extract_job_id_from_url(job_url)
    return f"https://www.upwork.com/nx/proposals/job/{job_id}/apply/"


def job_id_to_apply_url(job_id: str) -> str:
    """Convert job ID to apply page URL."""
    if not job_id.startswith('~'):
        job_id = f'~{job_id}'
    return f"https://www.upwork.com/nx/proposals/job/{job_id}/apply/"


class UpworkSubmitter:
    """Playwright-based submitter for Upwork job applications.

    Features:
    - #52: Navigate to apply page
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

    # Selectors for Upwork apply form elements
    SELECTORS = {
        # Cover letter / proposal text
        'cover_letter': [
            '[data-test="cover-letter-textarea"]',
            'textarea[name="coverLetter"]',
            '#cover-letter',
            'textarea[placeholder*="cover letter"]',
            'textarea[placeholder*="proposal"]',
            '.cover-letter-textarea',
            '[data-cy="cover-letter"]',
        ],

        # Rate/price input
        'rate_input': [
            '[data-test="rate-input"]',
            'input[name="rate"]',
            'input[name="hourlyRate"]',
            'input[name="amount"]',
            'input[name="bid"]',
            '[data-test="bid-amount"]',
            '.rate-input',
            'input[type="number"][placeholder*="rate"]',
        ],

        # Fixed price input
        'fixed_price_input': [
            '[data-test="fixed-price-input"]',
            'input[name="fixedPrice"]',
            'input[name="projectBid"]',
            '[data-test="project-bid"]',
        ],

        # File attachment input
        'file_input': [
            'input[type="file"]',
            '[data-test="file-upload-input"]',
            '.file-upload input',
            'input[accept*="pdf"]',
            'input[accept*="video"]',
        ],

        # Boost checkbox/toggle
        'boost_toggle': [
            '[data-test="boost-checkbox"]',
            '[data-test="boost-toggle"]',
            'input[name="boost"]',
            '.boost-toggle',
            '[data-cy="boost"]',
            'label:has-text("Boost")',
        ],

        # Submit button
        'submit_button': [
            '[data-test="submit-proposal"]',
            'button[type="submit"]',
            'button:has-text("Submit")',
            'button:has-text("Apply")',
            'button:has-text("Send Proposal")',
            '.submit-proposal',
            '[data-cy="submit-proposal"]',
        ],

        # Success indicators
        'success_message': [
            '[data-test="proposal-submitted"]',
            '.success-message',
            ':has-text("Proposal submitted")',
            ':has-text("Application sent")',
            ':has-text("Your proposal has been submitted")',
            '[data-test="success"]',
        ],

        # Error indicators
        'error_message': [
            '[data-test="error-message"]',
            '.error-message',
            '.alert-danger',
            '[role="alert"]',
            '.form-error',
            ':has-text("error")',
            ':has-text("failed")',
        ],

        # Apply form container
        'apply_form': [
            '[data-test="proposal-form"]',
            'form[name="proposal"]',
            '.proposal-form',
            '#apply-form',
            '[data-cy="proposal-form"]',
        ],

        # Connects/credits remaining indicator
        'connects_indicator': [
            '[data-test="connects-remaining"]',
            '.connects-count',
            ':has-text("Connects")',
        ],
    }

    def __init__(
        self,
        user_data_dir: str,
        headless: bool = True,
        tmp_dir: str = ".tmp",
        timeout: int = 60000,
    ):
        """Initialize the submitter.

        Args:
            user_data_dir: Path to browser profile directory (required for auth)
            headless: Run browser in headless mode
            tmp_dir: Directory for temporary files
            timeout: Default timeout for operations in milliseconds
        """
        if not user_data_dir:
            raise ValueError("user_data_dir is required for persistent auth")

        self.user_data_dir = user_data_dir
        self.headless = headless
        self.tmp_dir = Path(tmp_dir)
        self.tmp_dir.mkdir(exist_ok=True)
        self.timeout = timeout

        self._playwright = None
        self._context = None
        self._page = None

    async def __aenter__(self):
        await self._init_browser()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._close_browser()

    async def _init_browser(self):
        """Initialize Playwright with persistent browser profile."""
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()

        # Use persistent context for Upwork authentication
        self._context = await self._playwright.chromium.launch_persistent_context(
            self.user_data_dir,
            headless=self.headless,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            accept_downloads=True,
        )

    async def _close_browser(self):
        """Close browser and cleanup."""
        if self._page:
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._playwright:
            await self._playwright.stop()

    async def _find_element(self, page, selector_group: str, timeout: int = 5000):
        """Find element using multiple possible selectors.

        Args:
            page: Playwright page
            selector_group: Key in SELECTORS dict
            timeout: Max time to wait per selector

        Returns:
            Element handle or None
        """
        selectors = self.SELECTORS.get(selector_group, [])

        for selector in selectors:
            try:
                elem = await page.wait_for_selector(selector, timeout=timeout, state="visible")
                if elem:
                    return elem
            except:
                continue
        return None

    async def _fill_text_field(self, page, selector_group: str, text: str) -> bool:
        """Fill a text field using multiple possible selectors.

        Returns:
            True if successful, False otherwise
        """
        elem = await self._find_element(page, selector_group)
        if elem:
            try:
                await elem.click()
                await elem.fill(text)
                return True
            except Exception as e:
                print(f"Error filling {selector_group}: {e}")
        return False

    async def _click_element(self, page, selector_group: str) -> bool:
        """Click an element using multiple possible selectors.

        Returns:
            True if successful, False otherwise
        """
        elem = await self._find_element(page, selector_group)
        if elem:
            try:
                await elem.click()
                return True
            except Exception as e:
                print(f"Error clicking {selector_group}: {e}")
        return False

    async def navigate_to_apply_page(
        self,
        job_url: str,
    ) -> SubmissionResult:
        """Navigate to the apply page for a job.

        Feature #52: Navigate to Upwork apply page

        Args:
            job_url: Job URL or apply URL

        Returns:
            SubmissionResult with navigation status
        """
        try:
            job_id = extract_job_id_from_url(job_url)
        except ValueError as e:
            return SubmissionResult(
                job_id="unknown",
                job_url=job_url,
                status=SubmissionStatus.ERROR,
                error=str(e)
            )

        result = SubmissionResult(
            job_id=job_id,
            job_url=job_url,
        )

        # Convert to apply URL if needed
        if '/apply' not in job_url:
            apply_url = job_url_to_apply_url(job_url)
        else:
            apply_url = job_url

        result.apply_url = apply_url

        try:
            self._page = await self._context.new_page()

            # Navigate to apply page
            print(f"Navigating to: {apply_url}")
            await self._page.goto(apply_url, wait_until="networkidle", timeout=self.timeout)
            await asyncio.sleep(2)  # Let dynamic content load

            # Check if we're on the apply page (not login page)
            current_url = self._page.url
            if 'login' in current_url.lower() or 'signin' in current_url.lower():
                result.status = SubmissionStatus.ERROR
                result.error = "Login required - browser profile may not have valid session"
                result.error_log.append("Redirected to login page - session expired or invalid profile")
                return result

            # Look for the apply form
            apply_form = await self._find_element(self._page, 'apply_form', timeout=10000)
            if not apply_form:
                # Try finding the cover letter field as backup
                cover_letter = await self._find_element(self._page, 'cover_letter', timeout=5000)
                if not cover_letter:
                    result.status = SubmissionStatus.ERROR
                    result.error = "Apply form not found on page"
                    result.error_log.append(f"Current URL: {current_url}")
                    return result

            result.status = SubmissionStatus.NAVIGATED
            print(f"Successfully navigated to apply page for job {job_id}")

        except Exception as e:
            result.status = SubmissionStatus.ERROR
            result.error = str(e)
            result.error_log.append(f"Navigation error: {str(e)}")

        return result

    async def fill_cover_letter(
        self,
        result: SubmissionResult,
        proposal_text: str,
    ) -> SubmissionResult:
        """Fill the cover letter field.

        Feature #53: Fill cover letter field

        Args:
            result: Current submission result
            proposal_text: Text to fill in cover letter

        Returns:
            Updated SubmissionResult
        """
        if not self._page:
            result.status = SubmissionStatus.ERROR
            result.error = "No page available - call navigate_to_apply_page first"
            return result

        try:
            # Find and fill cover letter
            success = await self._fill_text_field(self._page, 'cover_letter', proposal_text)

            if success:
                result.cover_letter_filled = True
                print("Cover letter filled successfully")
            else:
                result.error_log.append("Could not find cover letter field")

        except Exception as e:
            result.error_log.append(f"Error filling cover letter: {str(e)}")

        return result

    async def attach_file(
        self,
        result: SubmissionResult,
        file_path: str,
        file_type: str = "generic",  # "video", "pdf", "generic"
    ) -> SubmissionResult:
        """Attach a file to the application.

        Features #54, #55: Attach video and PDF files

        Args:
            result: Current submission result
            file_path: Path to file to attach
            file_type: Type of file ("video", "pdf", "generic")

        Returns:
            Updated SubmissionResult
        """
        if not self._page:
            result.status = SubmissionStatus.ERROR
            result.error = "No page available - call navigate_to_apply_page first"
            return result

        if not os.path.exists(file_path):
            result.error_log.append(f"File not found: {file_path}")
            return result

        try:
            # Find file input
            file_input = await self._find_element(self._page, 'file_input', timeout=5000)

            if file_input:
                # Upload file
                await file_input.set_input_files(file_path)
                await asyncio.sleep(1)  # Wait for upload to process

                if file_type == "video":
                    result.video_attached = True
                    print(f"Video attached: {file_path}")
                elif file_type == "pdf":
                    result.pdf_attached = True
                    print(f"PDF attached: {file_path}")
                else:
                    print(f"File attached: {file_path}")
            else:
                result.error_log.append(f"Could not find file input for {file_type}")

        except Exception as e:
            result.error_log.append(f"Error attaching {file_type}: {str(e)}")

        return result

    async def set_proposed_price(
        self,
        result: SubmissionResult,
        amount: float,
        is_hourly: bool = True,
    ) -> SubmissionResult:
        """Set the proposed rate or fixed price.

        Feature #56: Set proposed rate/price

        Args:
            result: Current submission result
            amount: Proposed amount
            is_hourly: True for hourly rate, False for fixed price

        Returns:
            Updated SubmissionResult
        """
        if not self._page:
            result.status = SubmissionStatus.ERROR
            result.error = "No page available - call navigate_to_apply_page first"
            return result

        try:
            selector_group = 'rate_input' if is_hourly else 'fixed_price_input'

            # Try primary selector group first
            success = await self._fill_text_field(self._page, selector_group, str(amount))

            # If not found, try the other one
            if not success:
                alt_group = 'fixed_price_input' if is_hourly else 'rate_input'
                success = await self._fill_text_field(self._page, alt_group, str(amount))

            if success:
                result.price_set = True
                print(f"Price set to ${amount} ({'hourly' if is_hourly else 'fixed'})")
            else:
                result.error_log.append("Could not find rate/price input field")

        except Exception as e:
            result.error_log.append(f"Error setting price: {str(e)}")

        return result

    async def apply_boost(
        self,
        result: SubmissionResult,
        should_boost: bool = True,
    ) -> SubmissionResult:
        """Apply boost to the proposal if recommended.

        Feature #57: Apply boost if recommended

        Args:
            result: Current submission result
            should_boost: Whether to enable boost

        Returns:
            Updated SubmissionResult
        """
        if not self._page or not should_boost:
            return result

        try:
            boost_elem = await self._find_element(self._page, 'boost_toggle', timeout=3000)

            if boost_elem:
                # Check if it's already enabled
                is_checked = await boost_elem.is_checked() if hasattr(boost_elem, 'is_checked') else False

                if not is_checked:
                    await boost_elem.click()
                    await asyncio.sleep(0.5)

                result.boost_applied = True
                print("Boost applied")
            else:
                result.error_log.append("Boost toggle not found (may not be available)")

        except Exception as e:
            result.error_log.append(f"Error applying boost: {str(e)}")

        return result

    async def submit_proposal(
        self,
        result: SubmissionResult,
    ) -> SubmissionResult:
        """Click the submit button and handle the result.

        Features #58, #59, #60: Submit and detect success/failure

        Args:
            result: Current submission result

        Returns:
            Updated SubmissionResult with final status
        """
        if not self._page:
            result.status = SubmissionStatus.ERROR
            result.error = "No page available - call navigate_to_apply_page first"
            return result

        # Mark as form filled if cover letter was filled
        if result.cover_letter_filled:
            result.status = SubmissionStatus.FORM_FILLED

        try:
            # Find and click submit button
            submit_clicked = await self._click_element(self._page, 'submit_button')

            if not submit_clicked:
                result.status = SubmissionStatus.ERROR
                result.error = "Could not find or click submit button"
                return result

            result.status = SubmissionStatus.SUBMITTED
            print("Submit button clicked, waiting for response...")

            # Wait for response - either success or error
            await asyncio.sleep(3)

            # Check for success indicators
            success_elem = await self._find_element(self._page, 'success_message', timeout=10000)

            if success_elem:
                result.status = SubmissionStatus.SUCCESS
                result.submitted_at = datetime.utcnow().isoformat()

                try:
                    result.confirmation_message = await success_elem.inner_text()
                except:
                    result.confirmation_message = "Proposal submitted successfully"

                print(f"SUCCESS: {result.confirmation_message}")
                return result

            # Check for error indicators
            error_elem = await self._find_element(self._page, 'error_message', timeout=3000)

            if error_elem:
                try:
                    error_text = await error_elem.inner_text()
                    result.error = error_text
                    result.error_log.append(f"Form error: {error_text}")
                except:
                    result.error = "Unknown form error"

                result.status = SubmissionStatus.FAILED
                print(f"FAILED: {result.error}")
                return result

            # Check URL change as success indicator
            current_url = self._page.url
            if 'success' in current_url.lower() or 'submitted' in current_url.lower() or 'proposals' in current_url.lower():
                result.status = SubmissionStatus.SUCCESS
                result.submitted_at = datetime.utcnow().isoformat()
                result.confirmation_message = "Redirected to success/proposals page"
                print("SUCCESS: Detected via URL redirect")
                return result

            # Uncertain result
            result.status = SubmissionStatus.FAILED
            result.error = "Could not determine submission result"
            result.error_log.append(f"Final URL: {current_url}")

        except Exception as e:
            result.status = SubmissionStatus.ERROR
            result.error = str(e)
            result.error_log.append(f"Submission error: {str(e)}")

        return result

    async def capture_screenshot(
        self,
        result: SubmissionResult,
        stage: str = "final",
    ) -> SubmissionResult:
        """Capture a screenshot of the current page state.

        Args:
            result: Current submission result
            stage: Label for the screenshot (e.g., "final", "error")

        Returns:
            Updated SubmissionResult with screenshot path
        """
        if not self._page:
            return result

        try:
            screenshots_dir = self.tmp_dir / "submission_screenshots"
            screenshots_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = screenshots_dir / f"submission_{result.job_id}_{stage}_{timestamp}.png"

            await self._page.screenshot(path=str(screenshot_path), full_page=False)
            result.screenshot_path = str(screenshot_path)
            print(f"Screenshot saved: {screenshot_path}")

        except Exception as e:
            result.error_log.append(f"Screenshot error: {str(e)}")

        return result

    async def submit_full_application(
        self,
        job_url: str,
        proposal_text: str,
        pricing_proposed: Optional[float] = None,
        is_hourly: bool = True,
        video_path: Optional[str] = None,
        pdf_path: Optional[str] = None,
        should_boost: bool = False,
        capture_screenshots: bool = True,
    ) -> SubmissionResult:
        """Execute the full submission workflow.

        This is the main entry point for submitting a complete application.

        Args:
            job_url: Upwork job URL
            proposal_text: Cover letter text
            pricing_proposed: Proposed rate/price (optional)
            is_hourly: True for hourly, False for fixed price
            video_path: Path to video file to attach (optional)
            pdf_path: Path to PDF file to attach (optional)
            should_boost: Whether to apply boost
            capture_screenshots: Whether to capture screenshots

        Returns:
            SubmissionResult with final status
        """
        # Step 1: Navigate to apply page
        result = await self.navigate_to_apply_page(job_url)

        if result.status == SubmissionStatus.ERROR:
            if capture_screenshots:
                await self.capture_screenshot(result, "error_navigate")
            return result

        # Step 2: Fill cover letter
        result = await self.fill_cover_letter(result, proposal_text)

        # Step 3: Set price if provided
        if pricing_proposed is not None:
            result = await self.set_proposed_price(result, pricing_proposed, is_hourly)

        # Step 4: Attach video if provided
        if video_path:
            result = await self.attach_file(result, video_path, "video")

        # Step 5: Attach PDF if provided
        if pdf_path:
            result = await self.attach_file(result, pdf_path, "pdf")

        # Step 6: Apply boost if recommended
        if should_boost:
            result = await self.apply_boost(result, should_boost)

        if capture_screenshots:
            await self.capture_screenshot(result, "before_submit")

        # Step 7: Submit
        result = await self.submit_proposal(result)

        if capture_screenshots:
            await self.capture_screenshot(result, "final")

        return result


def submit_application_sync(
    job_url: str,
    proposal_text: str,
    user_data_dir: str,
    pricing_proposed: Optional[float] = None,
    is_hourly: bool = True,
    video_path: Optional[str] = None,
    pdf_path: Optional[str] = None,
    should_boost: bool = False,
    headless: bool = True,
    tmp_dir: str = ".tmp",
) -> SubmissionResult:
    """Synchronous wrapper for submit_full_application.

    Args:
        job_url: Upwork job URL
        proposal_text: Cover letter text
        user_data_dir: Path to browser profile
        pricing_proposed: Proposed rate/price
        is_hourly: True for hourly, False for fixed price
        video_path: Path to video file
        pdf_path: Path to PDF file
        should_boost: Whether to apply boost
        headless: Run headless
        tmp_dir: Temp directory

    Returns:
        SubmissionResult
    """
    async def _run():
        async with UpworkSubmitter(
            user_data_dir=user_data_dir,
            headless=headless,
            tmp_dir=tmp_dir,
        ) as submitter:
            return await submitter.submit_full_application(
                job_url=job_url,
                proposal_text=proposal_text,
                pricing_proposed=pricing_proposed,
                is_hourly=is_hourly,
                video_path=video_path,
                pdf_path=pdf_path,
                should_boost=should_boost,
            )

    return asyncio.run(_run())


def main():
    """CLI interface for submitter."""
    parser = argparse.ArgumentParser(description="Submit Upwork job application")

    # Required arguments
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--job-url", "-u", help="Upwork job URL")
    group.add_argument("--job-id", "-j", help="Upwork job ID (e.g., ~01abc123)")

    parser.add_argument("--proposal-text", "-t", required=True, help="Cover letter text")
    parser.add_argument("--profile", "-p", required=True, help="Browser profile directory")

    # Optional arguments
    parser.add_argument("--price", type=float, help="Proposed rate/price")
    parser.add_argument("--hourly", action="store_true", default=True, help="Hourly rate (default)")
    parser.add_argument("--fixed", action="store_true", help="Fixed price")
    parser.add_argument("--video", help="Path to video file to attach")
    parser.add_argument("--pdf", help="Path to PDF file to attach")
    parser.add_argument("--boost", action="store_true", help="Apply boost")
    parser.add_argument("--headless", action="store_true", default=True, help="Run headless (default)")
    parser.add_argument("--no-headless", action="store_true", help="Run with visible browser")
    parser.add_argument("--output", "-o", help="Output JSON file")
    parser.add_argument("--tmp-dir", default=".tmp", help="Temp directory")

    args = parser.parse_args()

    # Determine job URL
    if args.job_id:
        job_url = job_id_to_apply_url(args.job_id)
    else:
        job_url = args.job_url

    headless = not args.no_headless if args.no_headless else args.headless
    is_hourly = not args.fixed if args.fixed else args.hourly

    print(f"Submitting application for: {job_url}")

    result = submit_application_sync(
        job_url=job_url,
        proposal_text=args.proposal_text,
        user_data_dir=args.profile,
        pricing_proposed=args.price,
        is_hourly=is_hourly,
        video_path=args.video,
        pdf_path=args.pdf,
        should_boost=args.boost,
        headless=headless,
        tmp_dir=args.tmp_dir,
    )

    # Print results
    print(f"\n=== Submission Result ===")
    print(f"Job ID: {result.job_id}")
    print(f"Status: {result.status.value}")
    print(f"Cover Letter: {'Yes' if result.cover_letter_filled else 'No'}")
    print(f"Price Set: {'Yes' if result.price_set else 'No'}")
    print(f"Video Attached: {'Yes' if result.video_attached else 'No'}")
    print(f"PDF Attached: {'Yes' if result.pdf_attached else 'No'}")
    print(f"Boost Applied: {'Yes' if result.boost_applied else 'No'}")

    if result.status == SubmissionStatus.SUCCESS:
        print(f"Submitted At: {result.submitted_at}")
        print(f"Confirmation: {result.confirmation_message}")

    if result.error:
        print(f"Error: {result.error}")

    if result.error_log:
        print(f"Error Log:")
        for err in result.error_log:
            print(f"  - {err}")

    if result.screenshot_path:
        print(f"Screenshot: {result.screenshot_path}")

    # Save output
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(result.to_dict(), f, indent=2)
        print(f"\nSaved to {args.output}")

    return result


if __name__ == "__main__":
    main()
