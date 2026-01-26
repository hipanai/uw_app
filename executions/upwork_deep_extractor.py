#!/usr/bin/env python3
"""
Upwork Deep Extractor - Playwright-based job detail extraction.

Features #15-23: Extracts comprehensive job data including:
- Job title, description, requirements
- Budget/rate information (fixed or hourly)
- Client information (country, spend history, hires, payment verification)
- Attachment detection and download (PDF, DOCX)
- Job page screenshot capture

Usage:
    python upwork_deep_extractor.py --url "https://www.upwork.com/jobs/~123"
    python upwork_deep_extractor.py --url "..." --screenshot
    python upwork_deep_extractor.py --url "..." --download-attachments
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

# PDF extraction
try:
    import PyPDF2
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False

# DOCX extraction
try:
    from docx import Document
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False


@dataclass
class ClientInfo:
    """Client information extracted from job posting."""
    country: Optional[str] = None
    total_spent: Optional[str] = None
    total_spent_numeric: Optional[float] = None
    hires: Optional[int] = None
    payment_verified: bool = False
    rating: Optional[float] = None
    reviews_count: Optional[int] = None


@dataclass
class BudgetInfo:
    """Budget information extracted from job posting."""
    budget_type: str = "unknown"  # "fixed", "hourly", "unknown"
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    budget_raw: Optional[str] = None


@dataclass
class Attachment:
    """Information about a job attachment."""
    filename: str
    url: Optional[str] = None
    local_path: Optional[str] = None
    content_type: Optional[str] = None
    extracted_text: Optional[str] = None


@dataclass
class ExtractedJob:
    """Complete extracted job data."""
    job_id: str
    url: str
    title: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    budget: Optional[BudgetInfo] = None
    client: Optional[ClientInfo] = None
    attachments: list[Attachment] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    experience_level: Optional[str] = None
    project_length: Optional[str] = None
    proposals_count: Optional[str] = None
    posted_date: Optional[str] = None
    screenshot_path: Optional[str] = None
    extracted_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        # Convert nested dataclasses
        if self.budget:
            result['budget'] = asdict(self.budget)
        if self.client:
            result['client'] = asdict(self.client)
        if self.attachments:
            result['attachments'] = [asdict(a) for a in self.attachments]
        return result

    def to_sheet_row(self) -> dict:
        """Convert to flat dictionary for Google Sheets."""
        return {
            'job_id': self.job_id,
            'url': self.url,
            'title': self.title,
            'description': self.description,
            'attachments': json.dumps([a.filename for a in self.attachments]) if self.attachments else '[]',
            'budget_type': self.budget.budget_type if self.budget else 'unknown',
            'budget_min': self.budget.budget_min if self.budget else None,
            'budget_max': self.budget.budget_max if self.budget else None,
            'client_country': self.client.country if self.client else None,
            'client_spent': self.client.total_spent if self.client else None,
            'client_hires': self.client.hires if self.client else None,
            'payment_verified': self.client.payment_verified if self.client else False,
        }


def extract_job_id_from_url(url: str) -> str:
    """Extract job ID from Upwork URL."""
    # Handle various URL formats
    # https://www.upwork.com/jobs/~01abc123
    # https://www.upwork.com/freelance-jobs/apply/...~01abc123
    # https://www.upwork.com/nx/proposals/job/~01abc123/apply/
    match = re.search(r'~([a-f0-9]+)', url, re.IGNORECASE)
    if match:
        return f"~{match.group(1)}"
    raise ValueError(f"Could not extract job ID from URL: {url}")


def parse_budget(budget_text: str) -> BudgetInfo:
    """Parse budget text into structured BudgetInfo."""
    budget = BudgetInfo(budget_raw=budget_text)

    if not budget_text:
        return budget

    text_lower = budget_text.lower()

    # Check for hourly rate
    if '/hr' in text_lower or 'hourly' in text_lower:
        budget.budget_type = 'hourly'
        # Extract range like "$25.00-$50.00"
        range_match = re.search(r'\$?([\d,]+(?:\.\d{2})?)\s*-\s*\$?([\d,]+(?:\.\d{2})?)', budget_text)
        if range_match:
            budget.budget_min = float(range_match.group(1).replace(',', ''))
            budget.budget_max = float(range_match.group(2).replace(',', ''))
        else:
            # Single value
            single_match = re.search(r'\$?([\d,]+(?:\.\d{2})?)', budget_text)
            if single_match:
                value = float(single_match.group(1).replace(',', ''))
                budget.budget_min = value
                budget.budget_max = value

    # Check for fixed price
    elif 'fixed' in text_lower or 'budget' in text_lower:
        budget.budget_type = 'fixed'
        # Extract range or single value
        range_match = re.search(r'\$?([\d,]+(?:\.\d{2})?)\s*-\s*\$?([\d,]+(?:\.\d{2})?)', budget_text)
        if range_match:
            budget.budget_min = float(range_match.group(1).replace(',', ''))
            budget.budget_max = float(range_match.group(2).replace(',', ''))
        else:
            single_match = re.search(r'\$?([\d,]+(?:\.\d{2})?)', budget_text)
            if single_match:
                value = float(single_match.group(1).replace(',', ''))
                budget.budget_min = value
                budget.budget_max = value

    # Just a dollar amount without type indicator
    else:
        amount_match = re.search(r'\$?([\d,]+(?:\.\d{2})?)', budget_text)
        if amount_match:
            value = float(amount_match.group(1).replace(',', ''))
            budget.budget_min = value
            budget.budget_max = value
            # Try to guess type from context
            if value > 200:  # Likely fixed price
                budget.budget_type = 'fixed'
            else:
                budget.budget_type = 'hourly'

    return budget


def parse_client_spent(spent_text: str) -> tuple[str, Optional[float]]:
    """Parse client total spent text into raw string and numeric value."""
    if not spent_text:
        return None, None

    # Handle formats like "$10K", "$1.5M", "$500", etc.
    text_clean = spent_text.strip().upper()

    match = re.search(r'\$?([\d,]+(?:\.\d+)?)\s*(K|M)?', text_clean)
    if match:
        value = float(match.group(1).replace(',', ''))
        multiplier = match.group(2)

        if multiplier == 'K':
            value *= 1000
        elif multiplier == 'M':
            value *= 1000000

        return spent_text.strip(), value

    return spent_text.strip(), None


def parse_hires_count(hires_text: str) -> Optional[int]:
    """Parse client hires count."""
    if not hires_text:
        return None

    match = re.search(r'(\d+)\s*hire', hires_text.lower())
    if match:
        return int(match.group(1))
    return None


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text content from a PDF file."""
    if not HAS_PYPDF2:
        return "[PDF extraction requires PyPDF2 package]"

    try:
        text_parts = []
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text_parts.append(page.extract_text() or '')
        return '\n'.join(text_parts).strip()
    except Exception as e:
        return f"[Error extracting PDF: {e}]"


def extract_text_from_docx(docx_path: str) -> str:
    """Extract text content from a DOCX file."""
    if not HAS_DOCX:
        return "[DOCX extraction requires python-docx package]"

    try:
        doc = Document(docx_path)
        text_parts = []
        for para in doc.paragraphs:
            text_parts.append(para.text)
        return '\n'.join(text_parts).strip()
    except Exception as e:
        return f"[Error extracting DOCX: {e}]"


class UpworkDeepExtractor:
    """Playwright-based deep extractor for Upwork job pages."""

    def __init__(
        self,
        headless: bool = True,
        user_data_dir: Optional[str] = None,
        tmp_dir: str = ".tmp"
    ):
        self.headless = headless
        self.user_data_dir = user_data_dir
        self.tmp_dir = Path(tmp_dir)
        self.tmp_dir.mkdir(exist_ok=True)

        self._playwright = None
        self._browser = None
        self._context = None

    async def __aenter__(self):
        await self._init_browser()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._close_browser()

    async def _init_browser(self):
        """Initialize Playwright browser."""
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()

        # Use persistent context if user_data_dir provided (for auth)
        if self.user_data_dir:
            self._context = await self._playwright.chromium.launch_persistent_context(
                self.user_data_dir,
                headless=self.headless,
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}
            )
        else:
            self._browser = await self._playwright.chromium.launch(headless=self.headless)
            self._context = await self._browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}
            )

    async def _close_browser(self):
        """Close Playwright browser."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def extract_job(
        self,
        url: str,
        capture_screenshot: bool = False,
        download_attachments: bool = False
    ) -> ExtractedJob:
        """Extract job data from URL.

        Args:
            url: Upwork job URL
            capture_screenshot: Whether to capture a screenshot of the job page
            download_attachments: Whether to download and parse attachments

        Returns:
            ExtractedJob with extracted data
        """
        try:
            job_id = extract_job_id_from_url(url)
        except ValueError as e:
            return ExtractedJob(job_id="unknown", url=url, error=str(e))

        job = ExtractedJob(job_id=job_id, url=url)

        try:
            page = await self._context.new_page()

            # Navigate to job page
            await page.goto(url, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)  # Let dynamic content load

            # Handle potential Cloudflare challenge
            if "challenge" in page.url.lower():
                await asyncio.sleep(5)
                await page.reload(wait_until="networkidle")
                await asyncio.sleep(2)

            # Extract job data
            job.title = await self._extract_title(page)
            job.description = await self._extract_description(page)
            job.budget = await self._extract_budget(page)
            job.client = await self._extract_client_info(page)
            job.skills = await self._extract_skills(page)
            job.experience_level = await self._extract_experience_level(page)
            job.project_length = await self._extract_project_length(page)
            job.proposals_count = await self._extract_proposals(page)
            job.posted_date = await self._extract_posted_date(page)

            # Detect attachments
            job.attachments = await self._extract_attachments(page)

            # Download attachments if requested
            if download_attachments and job.attachments:
                for attachment in job.attachments:
                    await self._download_attachment(page, attachment, job_id)

            # Capture screenshot if requested
            if capture_screenshot:
                job.screenshot_path = await self._capture_screenshot(page, job_id)

            await page.close()

        except Exception as e:
            job.error = str(e)

        return job

    async def _extract_title(self, page) -> Optional[str]:
        """Extract job title."""
        selectors = [
            '[data-test="job-title"]',
            'h1',
            '.job-title',
            '[data-cy="job-title"]'
        ]

        for selector in selectors:
            try:
                elem = await page.query_selector(selector)
                if elem:
                    text = await elem.inner_text()
                    if text and text.strip():
                        return text.strip()
            except:
                continue
        return None

    async def _extract_description(self, page) -> Optional[str]:
        """Extract job description."""
        selectors = [
            '[data-test="job-description"]',
            '[data-test="Description"]',
            '.job-description',
            '[data-cy="job-description"]',
            '.up-card-section p'
        ]

        for selector in selectors:
            try:
                elem = await page.query_selector(selector)
                if elem:
                    text = await elem.inner_text()
                    if text and len(text.strip()) > 20:
                        return text.strip()
            except:
                continue
        return None

    async def _extract_budget(self, page) -> BudgetInfo:
        """Extract budget/rate information."""
        budget_text = None

        # Try multiple selectors
        selectors = [
            '[data-test="budget"]',
            '[data-test="hourly-rate"]',
            '[data-test="BudgetAmount"]',
            '.up-card-section:has-text("Budget")',
            'li:has-text("Budget")',
            'li:has-text("/hr")'
        ]

        for selector in selectors:
            try:
                elem = await page.query_selector(selector)
                if elem:
                    text = await elem.inner_text()
                    if text and ('$' in text or 'Budget' in text or '/hr' in text):
                        budget_text = text.strip()
                        break
            except:
                continue

        return parse_budget(budget_text) if budget_text else BudgetInfo()

    async def _extract_client_info(self, page) -> ClientInfo:
        """Extract client information."""
        client = ClientInfo()

        # Payment verified
        try:
            verified = await page.query_selector('[data-test="payment-verified"], .payment-verified')
            if verified:
                text = await verified.inner_text()
                client.payment_verified = 'verified' in text.lower()
        except:
            pass

        # Client location/country
        try:
            location = await page.query_selector('[data-test="client-location"], [data-test="location"]')
            if location:
                client.country = (await location.inner_text()).strip()
        except:
            pass

        # Total spent
        try:
            spent = await page.query_selector('[data-test="total-spent"], [data-test="client-spendings"]')
            if spent:
                text = await spent.inner_text()
                client.total_spent, client.total_spent_numeric = parse_client_spent(text)
        except:
            pass

        # Hires count
        try:
            hires = await page.query_selector('[data-test="client-hires"], :has-text("hires")')
            if hires:
                text = await hires.inner_text()
                client.hires = parse_hires_count(text)
        except:
            pass

        # Rating
        try:
            rating = await page.query_selector('[data-test="client-rating"] .air3-rating-value-text')
            if rating:
                text = await rating.inner_text()
                try:
                    client.rating = float(text.strip())
                except:
                    pass
        except:
            pass

        return client

    async def _extract_skills(self, page) -> list[str]:
        """Extract required skills/tags."""
        skills = []

        try:
            # Find skills container
            skills_container = await page.query_selector('[data-test="Skills"], [data-test="skill-list"], .skills-list')
            if skills_container:
                skill_elems = await skills_container.query_selector_all('[data-test="token"], .skill-badge, .up-skill-badge')
                for elem in skill_elems:
                    text = await elem.inner_text()
                    if text and text.strip():
                        skills.append(text.strip())
        except:
            pass

        return skills

    async def _extract_experience_level(self, page) -> Optional[str]:
        """Extract required experience level."""
        selectors = [
            '[data-test="experience-level"]',
            ':has-text("Experience Level")',
            '.experience-level'
        ]

        for selector in selectors:
            try:
                elem = await page.query_selector(selector)
                if elem:
                    text = await elem.inner_text()
                    # Extract the level from text
                    for level in ['Entry', 'Intermediate', 'Expert']:
                        if level.lower() in text.lower():
                            return level
            except:
                continue
        return None

    async def _extract_project_length(self, page) -> Optional[str]:
        """Extract project length/duration."""
        selectors = [
            '[data-test="project-length"]',
            '[data-test="duration"]',
            ':has-text("Project Length")'
        ]

        for selector in selectors:
            try:
                elem = await page.query_selector(selector)
                if elem:
                    text = await elem.inner_text()
                    if text and text.strip():
                        return text.strip()
            except:
                continue
        return None

    async def _extract_proposals(self, page) -> Optional[str]:
        """Extract proposals count."""
        selectors = [
            '[data-test="proposals-tier"]',
            '[data-test="proposals"]',
            ':has-text("Proposals")'
        ]

        for selector in selectors:
            try:
                elem = await page.query_selector(selector)
                if elem:
                    text = await elem.inner_text()
                    if text and 'proposal' in text.lower():
                        return text.strip()
            except:
                continue
        return None

    async def _extract_posted_date(self, page) -> Optional[str]:
        """Extract posted date."""
        selectors = [
            '[data-test="posted-on"]',
            '[data-test="job-posted-date"]',
            ':has-text("Posted")'
        ]

        for selector in selectors:
            try:
                elem = await page.query_selector(selector)
                if elem:
                    text = await elem.inner_text()
                    if text and text.strip():
                        return text.strip()
            except:
                continue
        return None

    async def _extract_attachments(self, page) -> list[Attachment]:
        """Detect attachments on the job posting."""
        attachments = []

        try:
            # Look for attachment links
            attachment_selectors = [
                'a[href*="attachment"]',
                'a[href*="download"]',
                '[data-test="attachment"]',
                '.attachment-link',
                'a:has-text(".pdf")',
                'a:has-text(".doc")',
                'a:has-text(".docx")'
            ]

            for selector in attachment_selectors:
                try:
                    elems = await page.query_selector_all(selector)
                    for elem in elems:
                        href = await elem.get_attribute('href')
                        text = await elem.inner_text()

                        # Extract filename from text or href
                        filename = text.strip() if text else None
                        if not filename and href:
                            filename = href.split('/')[-1].split('?')[0]

                        if filename and (filename.endswith('.pdf') or filename.endswith('.doc') or filename.endswith('.docx')):
                            attachment = Attachment(
                                filename=filename,
                                url=href if href and href.startswith('http') else None
                            )
                            # Avoid duplicates
                            if not any(a.filename == filename for a in attachments):
                                attachments.append(attachment)
                except:
                    continue
        except:
            pass

        return attachments

    async def _download_attachment(self, page, attachment: Attachment, job_id: str):
        """Download and parse an attachment."""
        if not attachment.url:
            return

        try:
            # Create downloads directory
            downloads_dir = self.tmp_dir / "downloads"
            downloads_dir.mkdir(exist_ok=True)

            # Sanitize filename
            safe_filename = re.sub(r'[^\w\-_\.]', '_', attachment.filename)
            local_path = downloads_dir / f"{job_id}_{safe_filename}"

            # Download file using page context
            async with page.expect_download() as download_info:
                await page.click(f'a[href="{attachment.url}"]')
            download = await download_info.value
            await download.save_as(str(local_path))

            attachment.local_path = str(local_path)

            # Extract text based on file type
            if local_path.suffix.lower() == '.pdf':
                attachment.extracted_text = extract_text_from_pdf(str(local_path))
                attachment.content_type = 'application/pdf'
            elif local_path.suffix.lower() in ['.doc', '.docx']:
                attachment.extracted_text = extract_text_from_docx(str(local_path))
                attachment.content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

        except Exception as e:
            attachment.extracted_text = f"[Error downloading: {e}]"

    async def _capture_screenshot(self, page, job_id: str, full_page: bool = True) -> str:
        """Capture a screenshot of the job page.

        Args:
            page: Playwright page object
            job_id: Job ID for filename
            full_page: If True, captures entire scrollable page. If False, captures viewport only.

        Returns:
            Path to saved screenshot
        """
        screenshots_dir = self.tmp_dir / "screenshots"
        screenshots_dir.mkdir(exist_ok=True)

        screenshot_path = screenshots_dir / f"job_snapshot_{job_id}.png"

        # Scroll to top first
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(0.5)

        # Set viewport width (height doesn't matter for full-page)
        await page.set_viewport_size({"width": 1920, "height": 1080})

        # Take screenshot - full_page=True captures entire scrollable content
        await page.screenshot(path=str(screenshot_path), full_page=full_page)

        return str(screenshot_path)


def extract_job_sync(
    url: str,
    capture_screenshot: bool = False,
    download_attachments: bool = False,
    headless: bool = True,
    user_data_dir: Optional[str] = None,
    tmp_dir: str = ".tmp"
) -> ExtractedJob:
    """Synchronous wrapper for extract_job.

    Args:
        url: Upwork job URL
        capture_screenshot: Whether to capture screenshot
        download_attachments: Whether to download attachments
        headless: Run browser in headless mode
        user_data_dir: Path to browser profile for persistent auth
        tmp_dir: Directory for temporary files

    Returns:
        ExtractedJob with extracted data
    """
    async def _run():
        async with UpworkDeepExtractor(
            headless=headless,
            user_data_dir=user_data_dir,
            tmp_dir=tmp_dir
        ) as extractor:
            return await extractor.extract_job(
                url,
                capture_screenshot=capture_screenshot,
                download_attachments=download_attachments
            )

    return asyncio.run(_run())


async def extract_jobs_batch_async(
    urls: list[str],
    capture_screenshots: bool = False,
    download_attachments: bool = False,
    headless: bool = True,
    user_data_dir: Optional[str] = None,
    tmp_dir: str = ".tmp",
    max_concurrent: int = 3
) -> list[ExtractedJob]:
    """Extract multiple jobs with concurrency control.

    Args:
        urls: List of Upwork job URLs
        capture_screenshots: Whether to capture screenshots
        download_attachments: Whether to download attachments
        headless: Run browser in headless mode
        user_data_dir: Path to browser profile
        tmp_dir: Directory for temporary files
        max_concurrent: Maximum concurrent extractions

    Returns:
        List of ExtractedJob objects
    """
    results = []
    semaphore = asyncio.Semaphore(max_concurrent)

    async def extract_with_semaphore(extractor, url):
        async with semaphore:
            return await extractor.extract_job(
                url,
                capture_screenshot=capture_screenshots,
                download_attachments=download_attachments
            )

    async with UpworkDeepExtractor(
        headless=headless,
        user_data_dir=user_data_dir,
        tmp_dir=tmp_dir
    ) as extractor:
        tasks = [extract_with_semaphore(extractor, url) for url in urls]
        results = await asyncio.gather(*tasks)

    return results


def main():
    """CLI interface for deep extractor."""
    parser = argparse.ArgumentParser(description="Deep extract Upwork job data")
    parser.add_argument("--url", "-u", required=True, help="Upwork job URL")
    parser.add_argument("--screenshot", "-s", action="store_true", help="Capture job page screenshot")
    parser.add_argument("--download-attachments", "-d", action="store_true", help="Download and parse attachments")
    parser.add_argument("--output", "-o", help="Output JSON file")
    parser.add_argument("--headless", action="store_true", default=True, help="Run headless (default: true)")
    parser.add_argument("--no-headless", action="store_true", help="Run with visible browser")
    parser.add_argument("--profile", "-p", help="Browser profile directory for persistent auth")
    parser.add_argument("--tmp-dir", default=".tmp", help="Temp directory for files")

    args = parser.parse_args()

    headless = not args.no_headless if args.no_headless else args.headless

    print(f"Extracting job from: {args.url}")

    job = extract_job_sync(
        url=args.url,
        capture_screenshot=args.screenshot,
        download_attachments=args.download_attachments,
        headless=headless,
        user_data_dir=args.profile,
        tmp_dir=args.tmp_dir
    )

    # Print results
    print(f"\n=== Extracted Job Data ===")
    print(f"Job ID: {job.job_id}")
    print(f"Title: {job.title}")
    print(f"Description: {job.description[:200] + '...' if job.description and len(job.description) > 200 else job.description}")

    if job.budget:
        print(f"Budget: {job.budget.budget_type} ${job.budget.budget_min}-${job.budget.budget_max}")

    if job.client:
        print(f"Client: {job.client.country}, Spent: {job.client.total_spent}, Hires: {job.client.hires}, Verified: {job.client.payment_verified}")

    if job.skills:
        print(f"Skills: {', '.join(job.skills)}")

    if job.attachments:
        print(f"Attachments: {len(job.attachments)} found")
        for att in job.attachments:
            print(f"  - {att.filename}")
            if att.extracted_text:
                print(f"    Text preview: {att.extracted_text[:100]}...")

    if job.screenshot_path:
        print(f"Screenshot: {job.screenshot_path}")

    if job.error:
        print(f"Error: {job.error}")

    # Save output
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(job.to_dict(), f, indent=2)
        print(f"\nSaved to {args.output}")

    return job


if __name__ == "__main__":
    main()
