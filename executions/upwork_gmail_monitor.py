#!/usr/bin/env python3
"""
Upwork Gmail Monitor

Monitors Gmail for Upwork job alert emails and extracts job URLs/IDs.

Usage:
    # Check for new Upwork alerts
    python executions/upwork_gmail_monitor.py --check

    # Check and output jobs as JSON
    python executions/upwork_gmail_monitor.py --check --output .tmp/gmail_jobs.json

    # Check specific account
    python executions/upwork_gmail_monitor.py --check --account leftclick

    # Test URL extraction with sample email content
    python executions/upwork_gmail_monitor.py --test-extract

    # Mark processed emails
    python executions/upwork_gmail_monitor.py --check --mark-read
"""

import os
import sys
import re
import json
import argparse
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Gmail API imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import base64

# Gmail scopes - readonly is sufficient for monitoring
SCOPES_READONLY = ["https://www.googleapis.com/auth/gmail.readonly"]
SCOPES_MODIFY = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify"
]

# Upwork email patterns
UPWORK_FROM_PATTERNS = [
    "upwork.com",
    "notifications@upwork.com",
    "donotreply@upwork.com"
]

UPWORK_SUBJECT_PATTERNS = [
    r"new job",
    r"job that matches",
    r"jobs? for you",
    r"job alert",
    r"job invitation",
    r"jobs matching",
    r"recommended jobs?"
]

# Upwork job URL patterns
UPWORK_JOB_URL_PATTERN = re.compile(
    r'https?://(?:www\.)?upwork\.com/(?:jobs|ab/jobs|freelance-jobs)/[~\w\-/]+',
    re.IGNORECASE
)

# More specific pattern to extract job ID
UPWORK_JOB_ID_PATTERN = re.compile(
    r'https?://(?:www\.)?upwork\.com/(?:jobs|ab/jobs|freelance-jobs)/~(\w+)',
    re.IGNORECASE
)


class GmailAuth:
    """Handle Gmail authentication."""

    def __init__(self, token_path: str = None, credentials_path: str = None, scopes: List[str] = None):
        self.token_path = token_path or self._find_token_path()
        self.credentials_path = credentials_path or self._find_credentials_path()
        self.scopes = scopes or SCOPES_READONLY
        self._service = None

    def _find_token_path(self) -> str:
        """Find existing token file."""
        paths = [
            "config/token.json",
            "configuration/token.json",
            os.path.expanduser("~/.config/gmail/token.json")
        ]
        for path in paths:
            if os.path.exists(path):
                return path
        return "config/token.json"  # Default for new tokens

    def _find_credentials_path(self) -> str:
        """Find credentials file."""
        paths = [
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
            "config/credentials.json",
            "configuration/credentials.json"
        ]
        for path in paths:
            if path and os.path.exists(path):
                return path
        return "config/credentials.json"

    def get_credentials(self) -> Optional[Credentials]:
        """Get valid Gmail credentials."""
        creds = None

        # Load existing token
        if os.path.exists(self.token_path):
            try:
                creds = Credentials.from_authorized_user_file(self.token_path, self.scopes)
            except Exception as e:
                print(f"Warning: Error loading token: {e}")

        # Refresh or get new credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    # Save refreshed token
                    os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
                    with open(self.token_path, 'w') as f:
                        f.write(creds.to_json())
                except Exception as e:
                    print(f"Warning: Token refresh failed: {e}")
                    creds = None

            if not creds:
                # Need to run OAuth flow
                if not os.path.exists(self.credentials_path):
                    print(f"ERROR: Credentials file not found: {self.credentials_path}")
                    print("Please set up Google OAuth credentials.")
                    return None

                from google_auth_oauthlib.flow import InstalledAppFlow
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, self.scopes)
                creds = flow.run_local_server(port=0)

                # Save new token
                os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
                with open(self.token_path, 'w') as f:
                    f.write(creds.to_json())

        return creds

    def get_service(self):
        """Get Gmail API service."""
        if self._service is None:
            creds = self.get_credentials()
            if creds:
                self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def verify_scopes(self) -> Tuple[bool, List[str]]:
        """Verify token has required scopes."""
        if not os.path.exists(self.token_path):
            return False, []

        try:
            with open(self.token_path, 'r') as f:
                token_data = json.load(f)
            scopes = token_data.get('scopes', [])
            has_readonly = any('gmail.readonly' in s for s in scopes)
            return has_readonly, scopes
        except:
            return False, []


def extract_job_urls(text: str) -> List[str]:
    """Extract Upwork job URLs from text."""
    urls = UPWORK_JOB_URL_PATTERN.findall(text)
    # Deduplicate while preserving order
    seen = set()
    unique_urls = []
    for url in urls:
        # Normalize URL
        url = url.rstrip('/')
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    return unique_urls


def extract_job_id(url: str) -> Optional[str]:
    """Extract job ID from Upwork URL."""
    match = UPWORK_JOB_ID_PATTERN.search(url)
    if match:
        return f"~{match.group(1)}"
    return None


def is_upwork_alert_email(from_addr: str, subject: str) -> bool:
    """Check if email is an Upwork job alert."""
    # Check from address
    from_lower = from_addr.lower()
    is_from_upwork = any(pattern in from_lower for pattern in UPWORK_FROM_PATTERNS)

    if not is_from_upwork:
        return False

    # Check subject
    subject_lower = subject.lower()
    is_job_alert = any(re.search(pattern, subject_lower) for pattern in UPWORK_SUBJECT_PATTERNS)

    return is_job_alert


def get_email_body(payload: dict) -> str:
    """Extract plain text body from email payload."""
    body = ""

    def extract_text(part):
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
        # Also try HTML as fallback
        if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
            html = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
            # Basic HTML to text - just extract URLs, we don't need full text
            return html
        for sub in part.get("parts", []):
            result = extract_text(sub)
            if result:
                return result
        return ""

    body = extract_text(payload)
    if not body and payload.get("body", {}).get("data"):
        body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

    return body


def search_upwork_emails(service, query: str = None, max_results: int = 50) -> List[dict]:
    """
    Search for Upwork alert emails.

    Args:
        service: Gmail API service
        query: Additional search query (optional)
        max_results: Maximum emails to fetch

    Returns:
        List of email dicts with id, subject, from, date, body
    """
    # Build search query for Upwork emails
    base_query = "(from:upwork.com OR from:notifications@upwork.com)"

    if query:
        full_query = f"{base_query} {query}"
    else:
        full_query = base_query

    messages = []
    page_token = None

    try:
        while len(messages) < max_results:
            results = service.users().messages().list(
                userId="me",
                q=full_query,
                pageToken=page_token,
                maxResults=min(100, max_results - len(messages))
            ).execute()

            batch = results.get("messages", [])
            if not batch:
                break

            # Fetch full message details
            for msg_ref in batch:
                try:
                    msg = service.users().messages().get(
                        userId="me",
                        id=msg_ref["id"],
                        format="full"
                    ).execute()

                    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
                    from_addr = headers.get("From", "")
                    subject = headers.get("Subject", "")

                    # Only include if it's actually a job alert
                    if is_upwork_alert_email(from_addr, subject):
                        body = get_email_body(msg.get("payload", {}))
                        messages.append({
                            "id": msg["id"],
                            "thread_id": msg.get("threadId"),
                            "subject": subject,
                            "from": from_addr,
                            "date": headers.get("Date", ""),
                            "body": body,
                            "labels": msg.get("labelIds", [])
                        })

                except HttpError as e:
                    print(f"Warning: Error fetching message {msg_ref['id']}: {e}")

                if len(messages) >= max_results:
                    break

            page_token = results.get("nextPageToken")
            if not page_token:
                break

    except HttpError as e:
        print(f"Error searching emails: {e}")

    return messages


def extract_jobs_from_emails(emails: List[dict]) -> List[dict]:
    """
    Extract job information from Upwork alert emails.

    Args:
        emails: List of email dicts from search_upwork_emails

    Returns:
        List of job dicts with job_id, url, source, email_id, email_subject
    """
    jobs = []
    seen_job_ids = set()

    for email in emails:
        body = email.get("body", "")
        urls = extract_job_urls(body)

        for url in urls:
            job_id = extract_job_id(url)
            if job_id and job_id not in seen_job_ids:
                seen_job_ids.add(job_id)
                jobs.append({
                    "job_id": job_id,
                    "url": url,
                    "source": "gmail",
                    "email_id": email.get("id"),
                    "email_subject": email.get("subject"),
                    "email_date": email.get("date"),
                    "discovered_at": datetime.now().isoformat()
                })

    return jobs


def mark_emails_as_read(service, email_ids: List[str]) -> int:
    """Mark emails as read. Returns count of successfully modified."""
    if not email_ids:
        return 0

    success = 0
    for email_id in email_ids:
        try:
            service.users().messages().modify(
                userId="me",
                id=email_id,
                body={"removeLabelIds": ["UNREAD"]}
            ).execute()
            success += 1
        except HttpError as e:
            print(f"Warning: Failed to mark {email_id} as read: {e}")

    return success


# Test data for unit testing
SAMPLE_UPWORK_EMAIL_BODY = """
Hey there,

We found some new jobs that match your skills:

1. Need AI automation expert for workflow project
https://www.upwork.com/jobs/~01abc123def456

2. Looking for n8n developer
https://www.upwork.com/jobs/~02xyz789ghi012

3. Zapier integration specialist needed
https://www.upwork.com/ab/jobs/~03jkl345mno678

View more jobs at Upwork.

Best,
The Upwork Team
"""

SAMPLE_UPWORK_DIGEST_BODY = """
Your daily job digest

Here are 5 new jobs matching your profile:

• AI Chatbot Developer - https://www.upwork.com/jobs/~0a1b2c3d4e5f
• Automation Consultant - https://www.upwork.com/jobs/~0f5e4d3c2b1a
• Make.com Expert - https://www.upwork.com/jobs/~0123456789ab
• Data Pipeline Engineer - https://www.upwork.com/jobs/~0abcdef12345
• LLM Integration Specialist - https://www.upwork.com/jobs/~09876543210f

Click any link to apply!
"""


def run_tests() -> bool:
    """Run unit tests for URL extraction."""
    print("Running URL extraction tests...\n")

    all_passed = True

    # Test 1: Extract URLs from sample email
    print("Test 1: Extract job URLs from single email body")
    urls = extract_job_urls(SAMPLE_UPWORK_EMAIL_BODY)
    expected_count = 3
    if len(urls) == expected_count:
        print(f"  PASS: Found {len(urls)} URLs (expected {expected_count})")
    else:
        print(f"  FAIL: Found {len(urls)} URLs (expected {expected_count})")
        all_passed = False

    # Test 2: Extract job IDs
    print("\nTest 2: Extract job IDs from URLs")
    for url in urls:
        job_id = extract_job_id(url)
        if job_id and job_id.startswith("~"):
            print(f"  PASS: {url} -> {job_id}")
        else:
            print(f"  FAIL: Could not extract ID from {url}")
            all_passed = False

    # Test 3: Digest email with multiple jobs
    print("\nTest 3: Extract from digest email (5 jobs)")
    urls = extract_job_urls(SAMPLE_UPWORK_DIGEST_BODY)
    expected_count = 5
    if len(urls) == expected_count:
        print(f"  PASS: Found {len(urls)} URLs (expected {expected_count})")
    else:
        print(f"  FAIL: Found {len(urls)} URLs (expected {expected_count})")
        all_passed = False

    # Test 4: All IDs are unique
    print("\nTest 4: All job IDs are unique")
    job_ids = [extract_job_id(url) for url in urls]
    unique_ids = set(job_ids)
    if len(job_ids) == len(unique_ids):
        print(f"  PASS: All {len(job_ids)} IDs are unique")
    else:
        print(f"  FAIL: Found duplicate IDs")
        all_passed = False

    # Test 5: Upwork email detection
    print("\nTest 5: Upwork email detection")
    test_cases = [
        ("notifications@upwork.com", "New job that matches your skills", True),
        ("donotreply@upwork.com", "Job Alert: 5 new jobs for you", True),
        ("notifications@upwork.com", "Your weekly earnings summary", False),
        ("spam@example.com", "New job opportunity", False),
        ("notifications@upwork.com", "Jobs matching your profile", True),
    ]
    for from_addr, subject, expected in test_cases:
        result = is_upwork_alert_email(from_addr, subject)
        status = "PASS" if result == expected else "FAIL"
        print(f"  {status}: from='{from_addr}' subject='{subject}' -> {result} (expected {expected})")
        if result != expected:
            all_passed = False

    # Test 6: URL normalization (no duplicates)
    print("\nTest 6: URL deduplication")
    text_with_dupes = """
    https://www.upwork.com/jobs/~01abc123
    https://www.upwork.com/jobs/~01abc123/
    https://www.upwork.com/jobs/~01abc123
    https://www.upwork.com/jobs/~02def456
    """
    urls = extract_job_urls(text_with_dupes)
    if len(urls) == 2:
        print(f"  PASS: Deduplicated to 2 unique URLs")
    else:
        print(f"  FAIL: Got {len(urls)} URLs (expected 2)")
        all_passed = False

    return all_passed


def main():
    parser = argparse.ArgumentParser(
        description="Monitor Gmail for Upwork job alerts"
    )

    parser.add_argument(
        "--check",
        action="store_true",
        help="Check for new Upwork alert emails"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file for extracted jobs (JSON)"
    )
    parser.add_argument(
        "--query", "-q",
        help="Additional Gmail search query (e.g., 'is:unread')"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum emails to check (default: 50)"
    )
    parser.add_argument(
        "--mark-read",
        action="store_true",
        help="Mark processed emails as read"
    )
    parser.add_argument(
        "--token-path",
        help="Path to token.json file"
    )
    parser.add_argument(
        "--verify-auth",
        action="store_true",
        help="Verify Gmail authentication is working"
    )
    parser.add_argument(
        "--test-extract",
        action="store_true",
        help="Run URL extraction tests (no Gmail connection needed)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )

    args = parser.parse_args()

    # Run extraction tests
    if args.test_extract:
        success = run_tests()
        print("\n" + "=" * 50)
        if success:
            print("ALL TESTS PASSED")
            return 0
        else:
            print("SOME TESTS FAILED")
            return 1

    # Verify auth
    if args.verify_auth:
        auth = GmailAuth(token_path=args.token_path)
        has_scope, scopes = auth.verify_scopes()

        print("Gmail Authentication Status:")
        print(f"  Token file: {auth.token_path}")
        print(f"  Token exists: {os.path.exists(auth.token_path)}")
        print(f"  Has readonly scope: {has_scope}")
        if scopes:
            print(f"  Scopes: {', '.join(scopes)}")

        # Try to get service
        service = auth.get_service()
        if service:
            print("  Service: OK (authenticated)")
            return 0
        else:
            print("  Service: FAILED (not authenticated)")
            return 1

    # Check for emails
    if args.check:
        auth = GmailAuth(token_path=args.token_path, scopes=SCOPES_MODIFY if args.mark_read else SCOPES_READONLY)
        service = auth.get_service()

        if not service:
            print("ERROR: Could not authenticate with Gmail")
            print("Run with --verify-auth to check authentication status")
            return 1

        print(f"Searching for Upwork alert emails...")
        query = args.query or "is:unread"  # Default to unread
        emails = search_upwork_emails(service, query=query, max_results=args.limit)
        print(f"Found {len(emails)} Upwork alert emails")

        if not emails:
            if args.json:
                print(json.dumps({"emails": 0, "jobs": []}))
            return 0

        # Extract jobs
        jobs = extract_jobs_from_emails(emails)
        print(f"Extracted {len(jobs)} unique jobs")

        # Output results
        if args.json:
            print(json.dumps({
                "emails": len(emails),
                "jobs": jobs
            }, indent=2))
        else:
            for job in jobs:
                print(f"\n  Job ID: {job['job_id']}")
                print(f"  URL: {job['url']}")
                print(f"  From: {job['email_subject']}")

        # Save to file
        if args.output and jobs:
            os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
            with open(args.output, 'w') as f:
                json.dump(jobs, f, indent=2)
            print(f"\nSaved {len(jobs)} jobs to {args.output}")

        # Mark as read
        if args.mark_read and emails:
            email_ids = [e['id'] for e in emails]
            count = mark_emails_as_read(service, email_ids)
            print(f"Marked {count} emails as read")

        return 0

    # No action specified
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
