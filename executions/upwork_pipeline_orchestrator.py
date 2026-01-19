#!/usr/bin/env python3
"""
Upwork Pipeline Orchestrator

Runs the full Upwork job application pipeline in sequence:
1. Ingest jobs (Apify scrape or Gmail alerts)
2. Deduplicate across sources
3. Pre-filter for relevance (AI scoring)
4. Deep extraction (Playwright)
5. Generate deliverables (proposal doc, PDF, HeyGen video)
6. Boost decision
7. Send Slack approval

Features #62-67: Pipeline orchestration
- #62: Run full pipeline in sequence
- #63: Handle Apify source
- #64: Handle Gmail source
- #65: Skip jobs below pre-filter threshold
- #66: Update sheet status at each stage
- #67: Handle errors gracefully

Usage:
    # Run full pipeline with Apify source
    python executions/upwork_pipeline_orchestrator.py --source apify --limit 10

    # Run pipeline with Gmail source
    python executions/upwork_pipeline_orchestrator.py --source gmail

    # Run with specific jobs (manual trigger)
    python executions/upwork_pipeline_orchestrator.py --jobs jobs.json

    # Test mode (don't submit to Slack or update sheets)
    python executions/upwork_pipeline_orchestrator.py --source apify --test
"""

import os
import sys
import json
import asyncio
import argparse
import logging
import traceback
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Callable
from pathlib import Path
from enum import Enum

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if os.getenv("DEBUG") else logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Try to load dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Environment variables
PREFILTER_MIN_SCORE = int(os.getenv("PREFILTER_MIN_SCORE", "70"))
UPWORK_PIPELINE_SHEET_ID = os.getenv("UPWORK_PIPELINE_SHEET_ID")

# Import pipeline components
try:
    from upwork_apify_scraper import scrape_upwork_jobs, filter_jobs
    APIFY_AVAILABLE = True
except ImportError:
    APIFY_AVAILABLE = False
    logger.warning("upwork_apify_scraper not available")

try:
    from upwork_gmail_monitor import check_gmail_for_upwork_jobs
    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False
    logger.warning("upwork_gmail_monitor not available")

try:
    from upwork_deduplicator import LocalDeduplicator, deduplicate_jobs
    DEDUPLICATOR_AVAILABLE = True
except ImportError:
    DEDUPLICATOR_AVAILABLE = False
    logger.warning("upwork_deduplicator not available")

try:
    from upwork_prefilter import score_job_sync, score_jobs_batch_async
    PREFILTER_AVAILABLE = True
except ImportError:
    PREFILTER_AVAILABLE = False
    logger.warning("upwork_prefilter not available")

# Anthropic client for async scoring
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logger.warning("anthropic not available")

try:
    from upwork_deep_extractor import extract_job_sync, extract_jobs_batch_async
    DEEP_EXTRACTOR_AVAILABLE = True
except ImportError:
    DEEP_EXTRACTOR_AVAILABLE = False
    logger.warning("upwork_deep_extractor not available")

try:
    from upwork_deliverable_generator import generate_deliverables, generate_deliverables_batch_async
    DELIVERABLE_GENERATOR_AVAILABLE = True
except ImportError:
    DELIVERABLE_GENERATOR_AVAILABLE = False
    logger.warning("upwork_deliverable_generator not available")

try:
    from upwork_boost_decider import decide_boost_sync, decide_boost_batch_async
    BOOST_DECIDER_AVAILABLE = True
except ImportError:
    BOOST_DECIDER_AVAILABLE = False
    logger.warning("upwork_boost_decider not available")

try:
    from upwork_slack_approval import send_approval_message
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False
    logger.warning("upwork_slack_approval not available")

# Google Sheets integration
try:
    import gspread
    from google.oauth2.credentials import Credentials as UserCredentials
    from google.auth.transport.requests import Request
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False
    logger.warning("gspread not available - sheet updates will be mocked")

# Google Sheets scopes
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]


class PipelineStatus(Enum):
    """Status values for jobs in the pipeline."""
    NEW = "new"
    SCORING = "scoring"
    FILTERED_OUT = "filtered_out"
    EXTRACTING = "extracting"
    GENERATING = "generating"
    BOOST_DECIDING = "boost_deciding"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUBMITTED = "submitted"
    SUBMISSION_FAILED = "submission_failed"
    ERROR = "error"


@dataclass
class PipelineJob:
    """Job data as it flows through the pipeline."""
    job_id: str
    url: str
    source: str  # 'apify' or 'gmail'
    status: PipelineStatus = PipelineStatus.NEW

    # Basic info from scraper
    title: Optional[str] = None
    description: Optional[str] = None

    # Pre-filter results
    fit_score: Optional[int] = None
    fit_reasoning: Optional[str] = None

    # Deep extraction results
    budget_type: Optional[str] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    client_country: Optional[str] = None
    client_spent: Optional[float] = None
    client_hires: Optional[int] = None
    payment_verified: bool = False
    attachments: List[Dict] = field(default_factory=list)
    attachment_content: Optional[str] = None

    # Deliverable results
    proposal_doc_url: Optional[str] = None
    proposal_text: Optional[str] = None
    video_url: Optional[str] = None
    pdf_url: Optional[str] = None
    cover_letter: Optional[str] = None

    # Boost decision
    boost_decision: Optional[bool] = None
    boost_reasoning: Optional[str] = None
    pricing_proposed: Optional[float] = None

    # Slack tracking
    slack_message_ts: Optional[str] = None
    approved_at: Optional[str] = None
    submitted_at: Optional[str] = None

    # Error tracking
    error_log: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        result['status'] = self.status.value
        return result

    def to_sheet_row(self) -> dict:
        """Convert to flat dictionary for Google Sheets."""
        return {
            'job_id': self.job_id,
            'source': self.source,
            'status': self.status.value,
            'title': self.title,
            'url': self.url,
            'description': self.description[:1000] if self.description else None,
            'attachments': json.dumps([a.get('filename', '') for a in self.attachments]) if self.attachments else '[]',
            'budget_type': self.budget_type,
            'budget_min': self.budget_min,
            'budget_max': self.budget_max,
            'client_country': self.client_country,
            'client_spent': self.client_spent,
            'client_hires': self.client_hires,
            'payment_verified': self.payment_verified,
            'fit_score': self.fit_score,
            'fit_reasoning': self.fit_reasoning,
            'proposal_doc_url': self.proposal_doc_url,
            'proposal_text': self.proposal_text[:2000] if self.proposal_text else None,
            'video_url': self.video_url,
            'pdf_url': self.pdf_url,
            'boost_decision': self.boost_decision,
            'boost_reasoning': self.boost_reasoning,
            'pricing_proposed': self.pricing_proposed,
            'slack_message_ts': self.slack_message_ts,
            'approved_at': self.approved_at,
            'submitted_at': self.submitted_at,
            'error_log': json.dumps(self.error_log) if self.error_log else None,
        }

    @classmethod
    def from_apify_job(cls, job: dict) -> 'PipelineJob':
        """Create PipelineJob from Apify scraper output."""
        # Extract job_id - Apify may use 'id', 'uid', or 'job_id'
        url = job.get('url', '')
        job_id = job.get('id') or job.get('uid') or job.get('job_id') or ''

        # Try to extract from URL if not found
        if not job_id and url:
            import re
            match = re.search(r'~0?(\d+)', url)
            if match:
                job_id = match.group(1)

        return cls(
            job_id=str(job_id),
            url=url,
            source='apify',
            title=job.get('title'),
            description=job.get('description'),
        )

    @classmethod
    def from_gmail_job(cls, job: dict) -> 'PipelineJob':
        """Create PipelineJob from Gmail monitor output."""
        return cls(
            job_id=job.get('job_id', ''),
            url=job.get('url', ''),
            source='gmail',
            title=job.get('title'),
            description=job.get('description'),
        )


@dataclass
class PipelineResult:
    """Result of running the pipeline."""
    started_at: str
    finished_at: Optional[str] = None
    source: str = "unknown"
    jobs_ingested: int = 0
    jobs_after_dedup: int = 0
    jobs_after_prefilter: int = 0
    jobs_processed: int = 0
    jobs_sent_to_slack: int = 0
    jobs_filtered_out: int = 0
    jobs_with_errors: int = 0
    processed_jobs: List[PipelineJob] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        result['processed_jobs'] = [j.to_dict() for j in self.processed_jobs]
        return result


def get_sheets_credentials():
    """Get OAuth2 credentials for Google Sheets API."""
    if not GSPREAD_AVAILABLE:
        return None

    creds = None
    token_paths = ['config/token.json', 'configuration/token.json']

    for token_path in token_paths:
        if os.path.exists(token_path):
            try:
                creds = UserCredentials.from_authorized_user_file(token_path, SCOPES)
                break
            except Exception as e:
                logger.warning(f"Failed to load token from {token_path}: {e}")

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as e:
            logger.error(f"Failed to refresh credentials: {e}")
            creds = None

    return creds


def get_sheets_client():
    """Get authenticated gspread client."""
    if not GSPREAD_AVAILABLE:
        return None

    creds = get_sheets_credentials()
    if not creds:
        logger.warning("No valid Google credentials available")
        return None

    try:
        return gspread.authorize(creds)
    except Exception as e:
        logger.error(f"Failed to authorize gspread: {e}")
        return None


def update_job_in_sheet(job: PipelineJob, sheet_id: Optional[str] = None, mock: bool = False) -> bool:
    """
    Update or insert job in Google Sheet.

    Args:
        job: PipelineJob to update
        sheet_id: Sheet ID (defaults to env var)
        mock: If True, don't actually update

    Returns:
        True if successful, False otherwise
    """
    if mock:
        logger.info(f"[MOCK] Would update sheet for job {job.job_id} with status {job.status.value}")
        return True

    sheet_id = sheet_id or UPWORK_PIPELINE_SHEET_ID
    if not sheet_id:
        logger.warning("No sheet ID configured, skipping sheet update")
        return False

    client = get_sheets_client()
    if not client:
        logger.warning("Could not get sheets client, skipping sheet update")
        return False

    try:
        sheet = client.open_by_key(sheet_id).sheet1

        # Find existing row by job_id (returns None if not found in gspread >= 5.0)
        cell = sheet.find(job.job_id)

        if cell is not None:
            # Update existing row
            row_num = cell.row
            row_data = job.to_sheet_row()
            headers = sheet.row_values(1)
            updates = []
            for col_idx, header in enumerate(headers, 1):
                if header in row_data and row_data[header] is not None:
                    updates.append({
                        'range': gspread.utils.rowcol_to_a1(row_num, col_idx),
                        'values': [[row_data[header]]]
                    })

            if updates:
                sheet.batch_update(updates)

            logger.info(f"Updated existing row for job {job.job_id}")
            return True
        else:
            # Insert new row
            row_data = job.to_sheet_row()
            headers = sheet.row_values(1)
            new_row = [row_data.get(h, '') for h in headers]
            sheet.append_row(new_row)
            logger.info(f"Inserted new row for job {job.job_id}")
            return True

    except Exception as e:
        logger.error(f"Failed to update sheet: {e}")
        return False


def update_jobs_batch_in_sheet(
    jobs: List[PipelineJob],
    sheet_id: Optional[str] = None,
    mock: bool = False
) -> dict:
    """
    Batch update multiple jobs in Google Sheet using fewer API calls.

    This function uses batch operations to update multiple jobs efficiently:
    - Single API call to get headers
    - Single API call to get all existing data
    - Single batch_update call for all cell updates
    - Single append_rows call for all new rows

    Args:
        jobs: List of PipelineJobs to update
        sheet_id: Sheet ID (defaults to env var)
        mock: If True, don't actually update

    Returns:
        dict with 'updated', 'inserted', 'failed' counts and 'api_calls' count
    """
    result = {'updated': 0, 'inserted': 0, 'failed': 0, 'api_calls': 0}

    if not jobs:
        return result

    if mock:
        for job in jobs:
            logger.info(f"[MOCK] Would batch update job {job.job_id} with status {job.status.value}")
        result['updated'] = len(jobs)
        return result

    sheet_id = sheet_id or UPWORK_PIPELINE_SHEET_ID
    if not sheet_id:
        logger.warning("No sheet ID configured, skipping batch sheet update")
        result['failed'] = len(jobs)
        return result

    client = get_sheets_client()
    if not client:
        logger.warning("Could not get sheets client, skipping batch sheet update")
        result['failed'] = len(jobs)
        return result

    try:
        sheet = client.open_by_key(sheet_id).sheet1
        result['api_calls'] += 1  # open_by_key

        # Get headers once
        headers = sheet.row_values(1)
        result['api_calls'] += 1

        # Get all existing data to find rows by job_id
        all_data = sheet.get_all_values()
        result['api_calls'] += 1

        # Build index of job_id -> row number
        job_id_col = headers.index('job_id') if 'job_id' in headers else 0
        job_id_to_row = {}
        for row_idx, row in enumerate(all_data[1:], start=2):  # Skip header, 1-indexed
            if row_idx > 1 and len(row) > job_id_col:
                job_id_to_row[row[job_id_col]] = row_idx

        # Prepare batch updates and new rows
        batch_updates = []
        new_rows = []

        for job in jobs:
            try:
                row_data = job.to_sheet_row()

                if job.job_id in job_id_to_row:
                    # Update existing row
                    row_num = job_id_to_row[job.job_id]
                    for col_idx, header in enumerate(headers, 1):
                        if header in row_data and row_data[header] is not None:
                            batch_updates.append({
                                'range': gspread.utils.rowcol_to_a1(row_num, col_idx),
                                'values': [[row_data[header]]]
                            })
                    result['updated'] += 1
                else:
                    # Prepare new row
                    new_row = [row_data.get(h, '') for h in headers]
                    new_rows.append(new_row)
                    result['inserted'] += 1

            except Exception as e:
                logger.error(f"Failed to prepare job {job.job_id} for batch update: {e}")
                result['failed'] += 1

        # Execute batch update for existing rows
        if batch_updates:
            sheet.batch_update(batch_updates)
            result['api_calls'] += 1
            logger.info(f"Batch updated {result['updated']} existing jobs ({len(batch_updates)} cells)")

        # Execute batch append for new rows
        if new_rows:
            sheet.append_rows(new_rows, value_input_option='RAW')
            result['api_calls'] += 1
            logger.info(f"Batch inserted {result['inserted']} new jobs")

        logger.info(f"Batch sheet update complete: {result['updated']} updated, {result['inserted']} inserted, {result['api_calls']} API calls")
        return result

    except Exception as e:
        logger.error(f"Failed to batch update sheet: {e}")
        result['failed'] = len(jobs)
        return result


async def run_pipeline_async(
    source: str = 'apify',
    jobs: Optional[List[dict]] = None,
    limit: int = 10,
    keywords: Optional[List[str]] = None,
    min_score: int = None,
    mock: bool = False,
    parallel: int = 3,
) -> PipelineResult:
    """
    Run the full Upwork job pipeline asynchronously.

    Args:
        source: Job source - 'apify', 'gmail', or 'manual'
        jobs: Pre-provided jobs (for manual source)
        limit: Max jobs to scrape from Apify
        keywords: Keywords for Apify search (server-side filtering)
        min_score: Minimum pre-filter score (defaults to env var)
        mock: If True, don't make real API calls
        parallel: Number of parallel jobs for batch processing

    Returns:
        PipelineResult with statistics and processed jobs
    """
    result = PipelineResult(
        started_at=datetime.now(timezone.utc).isoformat(),
        source=source,
    )

    min_score = min_score or PREFILTER_MIN_SCORE

    try:
        # STAGE 1: Ingest jobs
        logger.info(f"=== STAGE 1: Ingest jobs from {source} ===")

        if jobs:
            # Manual source - jobs provided directly
            pipeline_jobs = [
                PipelineJob(
                    job_id=j.get('job_id', j.get('id', '')),
                    url=j.get('url', ''),
                    source='manual',
                    title=j.get('title'),
                    description=j.get('description'),
                )
                for j in jobs
            ]
        elif source == 'apify':
            if not APIFY_AVAILABLE:
                raise RuntimeError("Apify scraper not available")

            if mock:
                # Mock Apify response
                raw_jobs = [
                    {'id': f'~mock{i}', 'url': f'https://www.upwork.com/jobs/~mock{i}',
                     'title': f'Mock Job {i}', 'description': f'Description for mock job {i}'}
                    for i in range(min(limit, 5))
                ]
            else:
                raw_jobs = scrape_upwork_jobs(limit=limit, keywords=keywords)

            # Add source field to each job
            for job in raw_jobs:
                job['source'] = 'apify'

            pipeline_jobs = [PipelineJob.from_apify_job(j) for j in raw_jobs]

        elif source == 'gmail':
            if not GMAIL_AVAILABLE:
                raise RuntimeError("Gmail monitor not available")

            if mock:
                # Mock Gmail response
                raw_jobs = [
                    {'job_id': '~gmailmock1', 'url': 'https://www.upwork.com/jobs/~gmailmock1',
                     'title': 'Gmail Mock Job', 'description': 'Description from Gmail'}
                ]
            else:
                raw_jobs = check_gmail_for_upwork_jobs()

            # Add source field to each job
            for job in raw_jobs:
                job['source'] = 'gmail'

            pipeline_jobs = [PipelineJob.from_gmail_job(j) for j in raw_jobs]

        else:
            raise ValueError(f"Unknown source: {source}")

        result.jobs_ingested = len(pipeline_jobs)
        logger.info(f"Ingested {result.jobs_ingested} jobs from {source}")

        if not pipeline_jobs:
            logger.info("No jobs to process")
            result.finished_at = datetime.now(timezone.utc).isoformat()
            return result

        # STAGE 2: Deduplicate
        logger.info(f"=== STAGE 2: Deduplicate ===")

        if DEDUPLICATOR_AVAILABLE and not mock:
            job_dicts = [{'job_id': j.job_id, 'source': j.source} for j in pipeline_jobs]
            logger.debug(f"Job dicts for dedup: {job_dicts}")
            # Create deduplicator and check for new jobs
            deduplicator = LocalDeduplicator()
            processed_before = deduplicator.get_processed_ids()
            logger.debug(f"Processed IDs before dedup: {len(processed_before)} items")
            new_jobs, dup_jobs = deduplicate_jobs(job_dicts, deduplicator)
            logger.debug(f"Dedup result: {len(new_jobs)} new, {len(dup_jobs)} duplicates")
            new_job_ids = set(j.get('job_id') or j.get('id') for j in new_jobs)
            logger.debug(f"New job IDs: {new_job_ids}")
            pipeline_jobs = [j for j in pipeline_jobs if j.job_id in new_job_ids]

        result.jobs_after_dedup = len(pipeline_jobs)
        logger.info(f"After deduplication: {result.jobs_after_dedup} jobs")

        if not pipeline_jobs:
            logger.info("All jobs already processed")
            result.finished_at = datetime.now(timezone.utc).isoformat()
            return result

        # STAGE 3: Pre-filter
        logger.info(f"=== STAGE 3: Pre-filter (min_score={min_score}) ===")

        for job in pipeline_jobs:
            job.status = PipelineStatus.SCORING
            update_job_in_sheet(job, mock=mock)

        if PREFILTER_AVAILABLE and ANTHROPIC_AVAILABLE:
            if mock:
                # Mock scoring - alternate high/low scores
                for i, job in enumerate(pipeline_jobs):
                    job.fit_score = 85 if i % 2 == 0 else 55
                    job.fit_reasoning = "Mock scoring result"
            else:
                # Real scoring - create async anthropic client
                async_client = anthropic.AsyncAnthropic()
                job_dicts = [{'job_id': j.job_id, 'title': j.title, 'description': j.description}
                            for j in pipeline_jobs]
                scored = await score_jobs_batch_async(job_dicts, async_client, max_concurrent=parallel)

                for job, scored_data in zip(pipeline_jobs, scored):
                    job.fit_score = scored_data.get('fit_score')
                    job.fit_reasoning = scored_data.get('fit_reasoning')
        elif PREFILTER_AVAILABLE and not ANTHROPIC_AVAILABLE:
            # Pre-filter available but anthropic not - assume all pass
            for job in pipeline_jobs:
                job.fit_score = 100
                job.fit_reasoning = "Anthropic client unavailable"
        else:
            # No pre-filter - assume all pass
            for job in pipeline_jobs:
                job.fit_score = 100
                job.fit_reasoning = "Pre-filter unavailable"

        # Filter by score
        filtered_jobs = []
        for job in pipeline_jobs:
            if job.fit_score and job.fit_score >= min_score:
                filtered_jobs.append(job)
            else:
                job.status = PipelineStatus.FILTERED_OUT
                result.jobs_filtered_out += 1
                update_job_in_sheet(job, mock=mock)
                logger.info(f"Job {job.job_id} filtered out (score={job.fit_score})")

        pipeline_jobs = filtered_jobs
        result.jobs_after_prefilter = len(pipeline_jobs)
        logger.info(f"After pre-filter: {result.jobs_after_prefilter} jobs (filtered out {result.jobs_filtered_out})")

        if not pipeline_jobs:
            logger.info("No jobs passed pre-filter")
            result.finished_at = datetime.now(timezone.utc).isoformat()
            return result

        # STAGE 4: Deep extraction
        logger.info(f"=== STAGE 4: Deep extraction ===")

        for job in pipeline_jobs:
            job.status = PipelineStatus.EXTRACTING
            update_job_in_sheet(job, mock=mock)

        if DEEP_EXTRACTOR_AVAILABLE and not mock:
            try:
                extracted_jobs = await extract_jobs_batch_async(
                    [j.url for j in pipeline_jobs],
                    max_concurrent=parallel
                )

                for job, extracted in zip(pipeline_jobs, extracted_jobs):
                    if extracted.error:
                        job.error_log.append(f"Extraction error: {extracted.error}")
                        continue

                    job.title = extracted.title or job.title
                    job.description = extracted.description or job.description

                    if extracted.budget:
                        job.budget_type = extracted.budget.budget_type
                        job.budget_min = extracted.budget.budget_min
                        job.budget_max = extracted.budget.budget_max

                    if extracted.client:
                        job.client_country = extracted.client.country
                        job.client_spent = extracted.client.total_spent_numeric
                        job.client_hires = extracted.client.hires
                        job.payment_verified = extracted.client.payment_verified

                    if extracted.attachments:
                        job.attachments = [asdict(a) for a in extracted.attachments]
                        # Combine attachment content
                        contents = [a.extracted_text for a in extracted.attachments if a.extracted_text]
                        if contents:
                            job.attachment_content = '\n\n'.join(contents)[:5000]

            except Exception as e:
                logger.error(f"Deep extraction error: {e}")
                for job in pipeline_jobs:
                    job.error_log.append(f"Deep extraction error: {str(e)}")
        elif mock:
            # Mock extraction
            for job in pipeline_jobs:
                job.budget_type = 'fixed'
                job.budget_min = 500
                job.budget_max = 1000
                job.client_country = 'United States'
                job.client_spent = 15000
                job.client_hires = 25
                job.payment_verified = True

        logger.info(f"Deep extraction completed for {len(pipeline_jobs)} jobs")

        # STAGE 5: Generate deliverables
        logger.info(f"=== STAGE 5: Generate deliverables ===")

        for job in pipeline_jobs:
            job.status = PipelineStatus.GENERATING
            update_job_in_sheet(job, mock=mock)

        if DELIVERABLE_GENERATOR_AVAILABLE:
            try:
                job_datas = [job.to_dict() for job in pipeline_jobs]

                if mock:
                    # Mock deliverable generation
                    for job in pipeline_jobs:
                        job.proposal_doc_url = f"https://docs.google.com/document/d/mock_{job.job_id}"
                        job.proposal_text = f"Mock proposal for {job.title}"
                        job.video_url = f"https://heygen.com/video/mock_{job.job_id}"
                        job.pdf_url = f"https://drive.google.com/file/d/mock_pdf_{job.job_id}/view"
                        job.cover_letter = f"Mock cover letter for {job.title}"
                else:
                    deliverables = await generate_deliverables_batch_async(
                        job_datas,
                        max_concurrent=parallel,
                        mock=False
                    )

                    for job, deliv in zip(pipeline_jobs, deliverables):
                        if deliv.error:
                            job.error_log.append(f"Deliverable error: {deliv.error}")
                            continue

                        job.proposal_doc_url = deliv.proposal_doc_url
                        job.proposal_text = deliv.proposal_text
                        job.video_url = deliv.video_url
                        job.pdf_url = deliv.pdf_url
                        job.cover_letter = deliv.cover_letter

            except Exception as e:
                logger.error(f"Deliverable generation error: {e}")
                for job in pipeline_jobs:
                    job.error_log.append(f"Deliverable generation error: {str(e)}")
        else:
            logger.warning("Deliverable generator not available")

        logger.info(f"Deliverable generation completed for {len(pipeline_jobs)} jobs")

        # STAGE 6: Boost decision
        logger.info(f"=== STAGE 6: Boost decision ===")

        for job in pipeline_jobs:
            job.status = PipelineStatus.BOOST_DECIDING
            update_job_in_sheet(job, mock=mock)

        if BOOST_DECIDER_AVAILABLE and ANTHROPIC_AVAILABLE:
            try:
                job_dicts = [job.to_dict() for job in pipeline_jobs]

                if mock:
                    # Mock boost decision
                    for job in pipeline_jobs:
                        job.boost_decision = job.client_spent and job.client_spent > 10000
                        job.boost_reasoning = "Mock boost decision"
                        job.pricing_proposed = job.budget_max or job.budget_min or 100
                else:
                    # Create async anthropic client for boost decisions
                    async_client = anthropic.AsyncAnthropic()
                    boost_results = await decide_boost_batch_async(job_dicts, async_client, max_concurrent=parallel)

                    for job, boost in zip(pipeline_jobs, boost_results):
                        job.boost_decision = boost.boost_decision
                        job.boost_reasoning = boost.reasoning
                        # Use midpoint of budget range for pricing
                        if job.budget_min and job.budget_max:
                            job.pricing_proposed = (job.budget_min + job.budget_max) / 2
                        elif job.budget_min:
                            job.pricing_proposed = job.budget_min
                        elif job.budget_max:
                            job.pricing_proposed = job.budget_max

            except Exception as e:
                logger.error(f"Boost decision error: {e}")
                for job in pipeline_jobs:
                    job.error_log.append(f"Boost decision error: {str(e)}")
        elif BOOST_DECIDER_AVAILABLE and not ANTHROPIC_AVAILABLE:
            logger.warning("Boost decider available but anthropic not available")
        else:
            logger.warning("Boost decider not available")

        logger.info(f"Boost decision completed for {len(pipeline_jobs)} jobs")

        # STAGE 7: Send to Slack for approval
        logger.info(f"=== STAGE 7: Send Slack approvals ===")

        for job in pipeline_jobs:
            job.status = PipelineStatus.PENDING_APPROVAL
            update_job_in_sheet(job, mock=mock)

            if SLACK_AVAILABLE and not mock:
                try:
                    slack_result = send_approval_message(job.to_dict(), mock=False)
                    if slack_result.get('success'):
                        job.slack_message_ts = slack_result.get('message_ts')
                        result.jobs_sent_to_slack += 1
                        logger.info(f"Sent Slack approval for job {job.job_id}")
                    else:
                        job.error_log.append(f"Slack error: {slack_result.get('error')}")
                except Exception as e:
                    job.error_log.append(f"Slack error: {str(e)}")
            elif mock:
                job.slack_message_ts = f"mock_ts_{job.job_id}"
                result.jobs_sent_to_slack += 1
                logger.info(f"[MOCK] Sent Slack approval for job {job.job_id}")

            # Final sheet update
            update_job_in_sheet(job, mock=mock)
            result.jobs_processed += 1

            # Track errors
            if job.error_log:
                result.jobs_with_errors += 1

        result.processed_jobs = pipeline_jobs

    except Exception as e:
        error_msg = f"Pipeline error: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        result.errors.append(error_msg)

    result.finished_at = datetime.now(timezone.utc).isoformat()

    logger.info(f"=== Pipeline Complete ===")
    logger.info(f"  Ingested: {result.jobs_ingested}")
    logger.info(f"  After dedup: {result.jobs_after_dedup}")
    logger.info(f"  After pre-filter: {result.jobs_after_prefilter}")
    logger.info(f"  Filtered out: {result.jobs_filtered_out}")
    logger.info(f"  Processed: {result.jobs_processed}")
    logger.info(f"  Sent to Slack: {result.jobs_sent_to_slack}")
    logger.info(f"  With errors: {result.jobs_with_errors}")

    return result


def run_pipeline_sync(
    source: str = 'apify',
    jobs: Optional[List[dict]] = None,
    limit: int = 10,
    keywords: Optional[List[str]] = None,
    min_score: int = None,
    mock: bool = False,
    parallel: int = 3,
) -> PipelineResult:
    """
    Synchronous wrapper for run_pipeline_async.
    """
    return asyncio.run(run_pipeline_async(
        source=source,
        jobs=jobs,
        limit=limit,
        keywords=keywords,
        min_score=min_score,
        mock=mock,
        parallel=parallel,
    ))


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Upwork Pipeline Orchestrator")
    parser.add_argument("--source", choices=["apify", "gmail", "manual"], default="apify",
                       help="Job source (default: apify)")
    parser.add_argument("--jobs", help="JSON file with jobs (for manual source)")
    parser.add_argument("--limit", type=int, default=10,
                       help="Max jobs to scrape from Apify (default: 10)")
    parser.add_argument("--keywords", help="Keywords for Apify search (comma-separated)")
    parser.add_argument("--min-score", type=int, help="Min pre-filter score (default: env var)")
    parser.add_argument("--parallel", type=int, default=3,
                       help="Parallel processing count (default: 3)")
    parser.add_argument("--output", "-o", help="Output JSON file for results")
    parser.add_argument("--test", action="store_true", help="Test mode (mock API calls)")
    parser.add_argument("--mock", action="store_true", help="Alias for --test")

    args = parser.parse_args()

    # Load jobs from file if provided
    jobs = None
    if args.jobs:
        with open(args.jobs, 'r') as f:
            jobs = json.load(f)
        if args.source == "apify":
            args.source = "manual"

    # Parse keywords
    keywords = None
    if args.keywords:
        keywords = [k.strip() for k in args.keywords.split(',') if k.strip()]

    mock = args.test or args.mock

    # Run pipeline
    result = run_pipeline_sync(
        source=args.source,
        jobs=jobs,
        limit=args.limit,
        keywords=keywords,
        min_score=args.min_score,
        mock=mock,
        parallel=args.parallel,
    )

    # Output results
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(result.to_dict(), f, indent=2)
        print(f"Results written to {args.output}")
    else:
        print(json.dumps(result.to_dict(), indent=2))

    return 0 if not result.errors else 1


if __name__ == "__main__":
    sys.exit(main())
