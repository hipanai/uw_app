#!/usr/bin/env python3
"""
Create and configure Google Sheets for Upwork Auto-Apply Pipeline.

This script creates two sheets:
1. Upwork Job Pipeline - Main tracking sheet with all job data
2. Upwork Processed IDs - Deduplication tracking

Usage:
    python executions/upwork_sheets_setup.py --create
    python executions/upwork_sheets_setup.py --verify --pipeline-id SHEET_ID --processed-id SHEET_ID
"""

import os
import sys
import json
import argparse
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Google Sheets imports
import gspread
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Column definitions for Upwork Job Pipeline sheet
PIPELINE_COLUMNS = [
    "job_id",           # Primary key - Upwork job ID
    "source",           # apify or gmail
    "status",           # new, scoring, extracting, generating, pending_approval, approved, submitted, rejected, filtered_out, error
    "title",            # Job title
    "url",              # Job URL
    "description",      # Job description text
    "attachments",      # JSON array of attachment info
    "budget_type",      # fixed, hourly, or unknown
    "budget_min",       # Minimum budget/rate
    "budget_max",       # Maximum budget/rate
    "client_country",   # Client location
    "client_spent",     # Total $ spent on platform
    "client_hires",     # Total past hires
    "payment_verified", # true/false
    "fit_score",        # 0-100 pre-filter score
    "fit_reasoning",    # AI reasoning for score
    "proposal_doc_url", # Google Doc URL
    "proposal_text",    # Cover letter text
    "video_url",        # HeyGen video URL
    "pdf_url",          # PDF attachment URL
    "boost_decision",   # true/false
    "boost_reasoning",  # AI reasoning for boost
    "pricing_proposed", # Proposed rate/price
    "slack_message_ts", # Slack message timestamp for updates
    "approved_at",      # Timestamp when approved
    "submitted_at",     # Timestamp when submitted
    "error_log",        # Error details if any
    "created_at",       # When job was first seen
    "updated_at"        # Last update timestamp
]

# Column definitions for Upwork Processed IDs sheet (deduplication)
PROCESSED_IDS_COLUMNS = [
    "job_id",           # Primary key - Upwork job ID
    "first_seen",       # Timestamp when first encountered
    "source"            # Source where first seen (apify or gmail)
]


def get_credentials():
    """Get OAuth2 credentials for Google Sheets API."""
    creds = None

    # Try loading existing token
    token_paths = ['config/token.json', 'configuration/token.json']
    token_path = None

    for path in token_paths:
        if os.path.exists(path):
            token_path = path
            break

    if token_path:
        try:
            with open(token_path, 'r') as token:
                token_data = json.load(token)
                creds = Credentials.from_authorized_user_info(token_data, SCOPES)
        except Exception as e:
            print(f"Error loading token: {e}")

    # Refresh or get new credentials if needed
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            from google_auth_oauthlib.flow import InstalledAppFlow
            creds_paths = [
                os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
                "config/credentials.json",
                "configuration/credentials.json"
            ]
            creds_file = None
            for path in creds_paths:
                if path and os.path.exists(path):
                    creds_file = path
                    break

            if not creds_file:
                print("ERROR: No credentials file found.")
                print("Please create config/credentials.json with your Google OAuth credentials.")
                print("See: https://console.cloud.google.com/apis/credentials")
                sys.exit(1)

            flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save refreshed credentials
        os.makedirs('config', exist_ok=True)
        with open('config/token.json', 'w') as token:
            token.write(creds.to_json())

    return creds


def create_sheet(client, title, columns):
    """
    Create a new Google Sheet with specified columns as headers.

    Args:
        client: Authorized gspread client
        title: Sheet title
        columns: List of column headers

    Returns:
        Spreadsheet object
    """
    # Create new spreadsheet
    spreadsheet = client.create(title)
    worksheet = spreadsheet.sheet1

    # Set headers
    worksheet.update('A1', [columns])

    # Format header row (bold)
    worksheet.format('A1:Z1', {
        'textFormat': {'bold': True},
        'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9}
    })

    # Freeze header row
    worksheet.freeze(rows=1)

    # Auto-resize columns (set reasonable widths)
    # Note: gspread doesn't support auto-resize, so we set fixed widths

    print(f"Created sheet: {title}")
    print(f"  URL: {spreadsheet.url}")
    print(f"  ID: {spreadsheet.id}")

    return spreadsheet


def verify_sheet(client, sheet_id, expected_columns, sheet_name):
    """
    Verify a sheet has the expected columns.

    Args:
        client: Authorized gspread client
        sheet_id: Google Sheet ID
        expected_columns: List of expected column headers
        sheet_name: Display name for logging

    Returns:
        tuple (success: bool, missing_columns: list, extra_columns: list)
    """
    try:
        spreadsheet = client.open_by_key(sheet_id)
        worksheet = spreadsheet.sheet1

        existing_headers = worksheet.row_values(1)

        missing = [col for col in expected_columns if col not in existing_headers]
        extra = [col for col in existing_headers if col not in expected_columns]

        if not missing:
            print(f"[OK] {sheet_name} has all required columns")
            if extra:
                print(f"  Note: Extra columns found: {', '.join(extra)}")
            return True, missing, extra
        else:
            print(f"[ERROR] {sheet_name} is missing columns: {', '.join(missing)}")
            return False, missing, extra

    except Exception as e:
        print(f"[ERROR] Error verifying {sheet_name}: {e}")
        return False, expected_columns, []


def add_missing_columns(client, sheet_id, missing_columns):
    """Add missing columns to an existing sheet."""
    try:
        spreadsheet = client.open_by_key(sheet_id)
        worksheet = spreadsheet.sheet1

        existing_headers = worksheet.row_values(1)

        # Add missing columns at the end
        for col in missing_columns:
            col_index = len(existing_headers) + 1
            worksheet.update_cell(1, col_index, col)
            existing_headers.append(col)
            print(f"  Added column: {col}")

        return True
    except Exception as e:
        print(f"Error adding columns: {e}")
        return False


def create_pipeline_sheet(client):
    """Create the main Upwork Job Pipeline sheet."""
    title = f"Upwork Job Pipeline"
    return create_sheet(client, title, PIPELINE_COLUMNS)


def create_processed_ids_sheet(client):
    """Create the Upwork Processed IDs deduplication sheet."""
    title = f"Upwork Processed IDs"
    return create_sheet(client, title, PROCESSED_IDS_COLUMNS)


def main():
    parser = argparse.ArgumentParser(
        description="Set up Google Sheets for Upwork Auto-Apply Pipeline"
    )

    parser.add_argument(
        "--create",
        action="store_true",
        help="Create new sheets (both Pipeline and Processed IDs)"
    )
    parser.add_argument(
        "--create-pipeline",
        action="store_true",
        help="Create only the Pipeline sheet"
    )
    parser.add_argument(
        "--create-processed",
        action="store_true",
        help="Create only the Processed IDs sheet"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify existing sheets have correct columns"
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Add missing columns to existing sheets"
    )
    parser.add_argument(
        "--pipeline-id",
        help="Sheet ID for Pipeline (for --verify or --fix)"
    )
    parser.add_argument(
        "--processed-id",
        help="Sheet ID for Processed IDs (for --verify or --fix)"
    )
    parser.add_argument(
        "--list-columns",
        action="store_true",
        help="List the expected columns for each sheet"
    )

    args = parser.parse_args()

    # Handle --list-columns without needing credentials
    if args.list_columns:
        print("\n=== Upwork Job Pipeline Columns ===")
        for i, col in enumerate(PIPELINE_COLUMNS, 1):
            print(f"  {i:2}. {col}")

        print("\n=== Upwork Processed IDs Columns ===")
        for i, col in enumerate(PROCESSED_IDS_COLUMNS, 1):
            print(f"  {i:2}. {col}")
        return 0

    # Get credentials
    print("Authenticating with Google...")
    creds = get_credentials()
    client = gspread.authorize(creds)
    print("[OK] Authentication successful\n")

    results = {}

    # Create sheets
    if args.create or args.create_pipeline:
        print("Creating Upwork Job Pipeline sheet...")
        pipeline_sheet = create_pipeline_sheet(client)
        results['pipeline_id'] = pipeline_sheet.id
        print()

    if args.create or args.create_processed:
        print("Creating Upwork Processed IDs sheet...")
        processed_sheet = create_processed_ids_sheet(client)
        results['processed_id'] = processed_sheet.id
        print()

    # Verify sheets
    if args.verify:
        pipeline_id = args.pipeline_id or os.getenv('UPWORK_PIPELINE_SHEET_ID')
        processed_id = args.processed_id or os.getenv('UPWORK_PROCESSED_IDS_SHEET_ID')

        if pipeline_id:
            print(f"Verifying Pipeline sheet ({pipeline_id})...")
            success, missing, extra = verify_sheet(
                client, pipeline_id, PIPELINE_COLUMNS, "Pipeline"
            )
            results['pipeline_valid'] = success
            results['pipeline_missing'] = missing
        else:
            print("No Pipeline sheet ID provided (use --pipeline-id or set UPWORK_PIPELINE_SHEET_ID)")

        if processed_id:
            print(f"\nVerifying Processed IDs sheet ({processed_id})...")
            success, missing, extra = verify_sheet(
                client, processed_id, PROCESSED_IDS_COLUMNS, "Processed IDs"
            )
            results['processed_valid'] = success
            results['processed_missing'] = missing
        else:
            print("No Processed IDs sheet ID provided (use --processed-id or set UPWORK_PROCESSED_IDS_SHEET_ID)")

    # Fix sheets
    if args.fix:
        pipeline_id = args.pipeline_id or os.getenv('UPWORK_PIPELINE_SHEET_ID')
        processed_id = args.processed_id or os.getenv('UPWORK_PROCESSED_IDS_SHEET_ID')

        if pipeline_id:
            print(f"Checking Pipeline sheet for missing columns...")
            success, missing, extra = verify_sheet(
                client, pipeline_id, PIPELINE_COLUMNS, "Pipeline"
            )
            if missing:
                print(f"Adding {len(missing)} missing columns...")
                add_missing_columns(client, pipeline_id, missing)

        if processed_id:
            print(f"\nChecking Processed IDs sheet for missing columns...")
            success, missing, extra = verify_sheet(
                client, processed_id, PROCESSED_IDS_COLUMNS, "Processed IDs"
            )
            if missing:
                print(f"Adding {len(missing)} missing columns...")
                add_missing_columns(client, processed_id, missing)

    # Output environment variable suggestions
    if results.get('pipeline_id') or results.get('processed_id'):
        print("\n" + "=" * 50)
        print("Add these to your .env file:")
        print("=" * 50)
        if results.get('pipeline_id'):
            print(f"UPWORK_PIPELINE_SHEET_ID={results['pipeline_id']}")
        if results.get('processed_id'):
            print(f"UPWORK_PROCESSED_IDS_SHEET_ID={results['processed_id']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
