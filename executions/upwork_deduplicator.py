#!/usr/bin/env python3
"""
Upwork Job Deduplicator

Tracks processed job IDs across sources (Apify, Gmail) to prevent duplicate processing.
Uses Google Sheets for persistent storage or local JSON file for testing.

Usage:
    # Production mode (Google Sheets)
    python executions/upwork_deduplicator.py --jobs jobs.json --output new_jobs.json

    # Test mode (local file)
    python executions/upwork_deduplicator.py --jobs jobs.json --output new_jobs.json --local

    # Check if specific job exists
    python executions/upwork_deduplicator.py --check-id "~01abc123"
"""

import os
import sys
import json
import argparse
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Local storage for testing
LOCAL_PROCESSED_IDS_FILE = ".tmp/processed_ids.json"


class LocalDeduplicator:
    """File-based deduplicator for testing without Google Sheets."""

    def __init__(self, filepath: str = LOCAL_PROCESSED_IDS_FILE):
        self.filepath = filepath
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        """Create file if it doesn't exist."""
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        if not os.path.exists(self.filepath):
            with open(self.filepath, 'w') as f:
                json.dump([], f)

    def get_processed_ids(self) -> Dict[str, dict]:
        """Get all processed job IDs as dict keyed by job_id."""
        with open(self.filepath, 'r') as f:
            records = json.load(f)
        return {r['job_id']: r for r in records}

    def add_processed_id(self, job_id: str, source: str) -> bool:
        """Add a new processed ID. Returns True if added, False if already exists."""
        processed = self.get_processed_ids()

        if job_id in processed:
            return False

        with open(self.filepath, 'r') as f:
            records = json.load(f)

        records.append({
            'job_id': job_id,
            'first_seen': datetime.now().isoformat(),
            'source': source
        })

        with open(self.filepath, 'w') as f:
            json.dump(records, f, indent=2)

        return True

    def add_processed_ids_batch(self, jobs: List[Dict]) -> int:
        """Add multiple job IDs at once. Returns count of new IDs added."""
        processed = self.get_processed_ids()

        with open(self.filepath, 'r') as f:
            records = json.load(f)

        added = 0
        now = datetime.now().isoformat()

        for job in jobs:
            job_id = job.get('job_id') or job.get('id')
            source = job.get('source', 'unknown')

            if job_id and job_id not in processed:
                records.append({
                    'job_id': job_id,
                    'first_seen': now,
                    'source': source
                })
                processed[job_id] = True  # Mark as processed for this batch
                added += 1

        with open(self.filepath, 'w') as f:
            json.dump(records, f, indent=2)

        return added

    def is_processed(self, job_id: str) -> bool:
        """Check if a job ID has been processed."""
        return job_id in self.get_processed_ids()

    def get_source(self, job_id: str) -> Optional[str]:
        """Get the source where a job was first seen."""
        processed = self.get_processed_ids()
        if job_id in processed:
            return processed[job_id].get('source')
        return None

    def clear(self):
        """Clear all processed IDs (for testing)."""
        with open(self.filepath, 'w') as f:
            json.dump([], f)


class SheetsDeduplicator:
    """Google Sheets-based deduplicator for production."""

    def __init__(self, sheet_id: Optional[str] = None):
        self.sheet_id = sheet_id or os.getenv('UPWORK_PROCESSED_IDS_SHEET_ID')
        self._client = None
        self._worksheet = None

    def _get_client(self):
        """Lazy-load Google Sheets client."""
        if self._client is None:
            import gspread
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request

            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]

            token_path = 'config/token.json'
            if not os.path.exists(token_path):
                raise RuntimeError(
                    "No Google credentials found. Run upwork_sheets_setup.py first."
                )

            with open(token_path, 'r') as f:
                token_data = json.load(f)

            creds = Credentials.from_authorized_user_info(token_data, scopes)

            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(token_path, 'w') as f:
                    f.write(creds.to_json())

            self._client = gspread.authorize(creds)

        return self._client

    def _get_worksheet(self):
        """Get the Processed IDs worksheet."""
        if self._worksheet is None:
            if not self.sheet_id:
                raise RuntimeError(
                    "No sheet ID configured. Set UPWORK_PROCESSED_IDS_SHEET_ID in .env"
                )
            client = self._get_client()
            spreadsheet = client.open_by_key(self.sheet_id)
            self._worksheet = spreadsheet.sheet1

        return self._worksheet

    def get_processed_ids(self) -> Dict[str, dict]:
        """Get all processed job IDs as dict keyed by job_id."""
        worksheet = self._get_worksheet()
        records = worksheet.get_all_records()
        return {r['job_id']: r for r in records}

    def add_processed_id(self, job_id: str, source: str) -> bool:
        """Add a new processed ID. Returns True if added, False if already exists."""
        processed = self.get_processed_ids()

        if job_id in processed:
            return False

        worksheet = self._get_worksheet()
        worksheet.append_row([
            job_id,
            datetime.now().isoformat(),
            source
        ], value_input_option='RAW')

        return True

    def add_processed_ids_batch(self, jobs: List[Dict]) -> int:
        """Add multiple job IDs at once. Returns count of new IDs added."""
        processed = self.get_processed_ids()
        worksheet = self._get_worksheet()

        rows_to_add = []
        now = datetime.now().isoformat()

        for job in jobs:
            job_id = job.get('job_id') or job.get('id')
            source = job.get('source', 'unknown')

            if job_id and job_id not in processed:
                rows_to_add.append([job_id, now, source])
                processed[job_id] = True  # Mark as processed for this batch

        if rows_to_add:
            # Use batch append for efficiency
            worksheet.append_rows(rows_to_add, value_input_option='RAW')

        return len(rows_to_add)

    def is_processed(self, job_id: str) -> bool:
        """Check if a job ID has been processed."""
        return job_id in self.get_processed_ids()

    def get_source(self, job_id: str) -> Optional[str]:
        """Get the source where a job was first seen."""
        processed = self.get_processed_ids()
        if job_id in processed:
            return processed[job_id].get('source')
        return None


def deduplicate_jobs(
    jobs: List[Dict],
    deduplicator,
    add_new: bool = True
) -> Tuple[List[Dict], List[Dict]]:
    """
    Separate new jobs from already-processed jobs.

    Args:
        jobs: List of job dictionaries with 'job_id' or 'id' field
        deduplicator: Deduplicator instance (Local or Sheets)
        add_new: Whether to add new jobs to processed list

    Returns:
        Tuple of (new_jobs, duplicate_jobs)
    """
    processed = deduplicator.get_processed_ids()
    seen_in_batch = set()  # Track IDs seen within this batch

    new_jobs = []
    duplicate_jobs = []

    for job in jobs:
        job_id = job.get('job_id') or job.get('id')

        if not job_id:
            print(f"Warning: Job missing ID, skipping: {job.get('title', 'Unknown')}")
            continue

        # Check both existing processed IDs and IDs seen in this batch
        if job_id in processed or job_id in seen_in_batch:
            duplicate_jobs.append(job)
        else:
            new_jobs.append(job)
            seen_in_batch.add(job_id)  # Mark as seen in this batch

    # Add new jobs to processed list
    if add_new and new_jobs:
        deduplicator.add_processed_ids_batch(new_jobs)

    return new_jobs, duplicate_jobs


def main():
    parser = argparse.ArgumentParser(
        description="Deduplicate Upwork jobs across sources"
    )

    parser.add_argument(
        "--jobs",
        help="Path to JSON file with jobs to deduplicate"
    )
    parser.add_argument(
        "--output", "-o",
        help="Path to save new (non-duplicate) jobs"
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Use local file storage instead of Google Sheets"
    )
    parser.add_argument(
        "--sheet-id",
        help="Google Sheet ID for processed IDs (overrides env var)"
    )
    parser.add_argument(
        "--check-id",
        help="Check if a specific job ID has been processed"
    )
    parser.add_argument(
        "--add-id",
        help="Manually add a job ID as processed"
    )
    parser.add_argument(
        "--source",
        default="manual",
        help="Source for --add-id (default: manual)"
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear all processed IDs (local mode only, for testing)"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show statistics about processed IDs"
    )

    args = parser.parse_args()

    # Initialize deduplicator
    if args.local:
        dedup = LocalDeduplicator()
        print("Using local file storage for deduplication")
    else:
        dedup = SheetsDeduplicator(sheet_id=args.sheet_id)
        print("Using Google Sheets for deduplication")

    # Handle --clear
    if args.clear:
        if not args.local:
            print("Error: --clear only works with --local mode")
            return 1
        dedup.clear()
        print("Cleared all processed IDs")
        return 0

    # Handle --check-id
    if args.check_id:
        if dedup.is_processed(args.check_id):
            source = dedup.get_source(args.check_id)
            print(f"Job {args.check_id} has been processed (source: {source})")
            return 0
        else:
            print(f"Job {args.check_id} has NOT been processed")
            return 1

    # Handle --add-id
    if args.add_id:
        if dedup.add_processed_id(args.add_id, args.source):
            print(f"Added job {args.add_id} (source: {args.source})")
        else:
            print(f"Job {args.add_id} already exists")
        return 0

    # Handle --stats
    if args.stats:
        processed = dedup.get_processed_ids()
        print(f"\nProcessed IDs Statistics:")
        print(f"  Total: {len(processed)}")

        # Count by source
        sources = {}
        for job_id, data in processed.items():
            source = data.get('source', 'unknown')
            sources[source] = sources.get(source, 0) + 1

        print(f"  By source:")
        for source, count in sorted(sources.items()):
            print(f"    {source}: {count}")

        return 0

    # Handle job deduplication
    if args.jobs:
        # Load jobs
        with open(args.jobs, 'r') as f:
            jobs = json.load(f)

        print(f"Loaded {len(jobs)} jobs from {args.jobs}")

        # Deduplicate
        new_jobs, duplicates = deduplicate_jobs(jobs, dedup)

        print(f"\nResults:")
        print(f"  New jobs: {len(new_jobs)}")
        print(f"  Duplicates: {len(duplicates)}")

        # Save new jobs if output specified
        if args.output and new_jobs:
            with open(args.output, 'w') as f:
                json.dump(new_jobs, f, indent=2)
            print(f"\nSaved {len(new_jobs)} new jobs to {args.output}")

        return 0

    # No action specified
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
