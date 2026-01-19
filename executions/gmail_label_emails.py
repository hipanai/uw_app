#!/usr/bin/env python3
"""
Label emails and export to Google Sheet for agent testing.

Usage:
    python3 execution/gmail_label_emails.py --query "in:inbox" --label "Agent Tester" --limit 100 --sheet "Agent Test Set"
"""

import os
import sys
import argparse
import json
import re
import html
from datetime import datetime
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import base64

load_dotenv()

# Only scopes that exist in the token
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

TOKEN_FILE = "config/token_nicksaraev.json"
CREDENTIALS_FILE = "config/credentials.json"


def get_gmail_service():
    """Get Gmail API service."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                print(f"Error: {CREDENTIALS_FILE} not found")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def get_sheets_service():
    """Get Sheets API service using same credentials."""
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("sheets", "v4", credentials=creds)


def get_or_create_label(service, label_name: str) -> str:
    """Get label ID by name, creating if needed."""
    results = service.users().labels().list(userId="me").execute()
    labels = results.get("labels", [])

    for label in labels:
        if label["name"].lower() == label_name.lower():
            return label["id"]

    label_body = {
        "name": label_name,
        "labelListVisibility": "labelShow",
        "messageListVisibility": "show"
    }
    created = service.users().labels().create(userId="me", body=label_body).execute()
    print(f"Created label: {label_name}")
    return created["id"]


def search_messages(service, query: str, max_results: int = 100) -> list:
    """Search for messages and get metadata."""
    message_ids = []
    page_token = None

    while len(message_ids) < max_results:
        remaining = max_results - len(message_ids)
        results = service.users().messages().list(
            userId="me",
            q=query,
            pageToken=page_token,
            maxResults=min(500, remaining)
        ).execute()

        batch = results.get("messages", [])
        if batch:
            message_ids.extend([msg["id"] for msg in batch])

        page_token = results.get("nextPageToken")
        if not page_token:
            break

    message_ids = message_ids[:max_results]

    if not message_ids:
        return []

    # Batch fetch metadata
    messages = []
    for i in range(0, len(message_ids), 50):
        batch_ids = message_ids[i:i+50]
        for msg_id in batch_ids:
            try:
                msg = service.users().messages().get(
                    userId="me",
                    id=msg_id,
                    format="full"
                ).execute()

                headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}

                # Extract body
                body = extract_body(msg.get("payload", {}))

                messages.append({
                    "id": msg_id,
                    "subject": headers.get("Subject", "(no subject)"),
                    "from": headers.get("From", ""),
                    "to": headers.get("To", ""),
                    "date": headers.get("Date", ""),
                    "body": body[:5000] if body else ""  # Truncate long bodies
                })
            except HttpError as e:
                print(f"  Error fetching {msg_id}: {e}")

        print(f"  Fetched {len(messages)}/{len(message_ids)} emails...")

    return messages


def html_to_plaintext(html_content: str) -> str:
    """Convert HTML to clean plaintext."""
    if not html_content:
        return ""

    # Remove style and script tags with content
    text = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)

    # Replace common block elements with newlines
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?(?:p|div|tr|li|h[1-6])[^>]*>', '\n', text, flags=re.IGNORECASE)

    # Remove all other HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Decode HTML entities
    text = html.unescape(text)

    # Clean up whitespace
    text = re.sub(r'[ \t]+', ' ', text)  # Collapse horizontal whitespace
    text = re.sub(r'\n\s*\n', '\n\n', text)  # Collapse multiple newlines to max 2
    text = text.strip()

    return text


def extract_body(payload, prefer_plain=True):
    """Extract body from message payload, converting HTML to plaintext."""
    plain_body = None
    html_body = None

    def find_parts(part):
        nonlocal plain_body, html_body
        mime_type = part.get("mimeType", "")
        data = part.get("body", {}).get("data")

        if data:
            decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            if mime_type == "text/plain" and not plain_body:
                plain_body = decoded
            elif mime_type == "text/html" and not html_body:
                html_body = decoded

        for sub in part.get("parts", []):
            find_parts(sub)

    find_parts(payload)

    # Prefer plaintext, fall back to converted HTML
    if plain_body:
        return plain_body.strip()
    elif html_body:
        return html_to_plaintext(html_body)

    return ""


def batch_add_label(service, message_ids: list, label_id: str):
    """Add label to messages in batches."""
    for i in range(0, len(message_ids), 100):
        batch = message_ids[i:i+100]
        service.users().messages().batchModify(
            userId="me",
            body={
                "ids": batch,
                "addLabelIds": [label_id]
            }
        ).execute()
    print(f"Added label to {len(message_ids)} emails")


def create_or_get_sheet(sheets_service, title: str) -> str:
    """Create a new spreadsheet or get existing one."""
    # Try to find existing
    drive_service = build("drive", "v3", credentials=sheets_service._http.credentials)
    results = drive_service.files().list(
        q=f"name='{title}' and mimeType='application/vnd.google-apps.spreadsheet'",
        spaces="drive",
        fields="files(id, name)"
    ).execute()

    files = results.get("files", [])
    if files:
        print(f"Found existing sheet: {title}")
        return files[0]["id"]

    # Create new
    spreadsheet = sheets_service.spreadsheets().create(
        body={"properties": {"title": title}}
    ).execute()
    print(f"Created new sheet: {title}")
    return spreadsheet["spreadsheetId"]


def populate_sheet(sheets_service, spreadsheet_id: str, messages: list):
    """Populate sheet with email data."""
    # Headers
    headers = [
        "Email ID", "From", "Subject", "Date", "Body",
        "Ground Truth Label", "Ground Truth Reply",
        "Test 1 Label", "Test 1 Reply",
        "Test 2 Label", "Test 2 Reply",
        "Test 3 Label", "Test 3 Reply",
        "Test 4 Label", "Test 4 Reply",
        "Test 5 Label", "Test 5 Reply"
    ]

    # Data rows
    rows = [headers]
    for msg in messages:
        rows.append([
            msg["id"],
            msg["from"],
            msg["subject"],
            msg["date"],
            msg["body"],
            "", "",  # Ground Truth Label, Reply
            "", "",  # Test 1 Label, Reply
            "", "",  # Test 2 Label, Reply
            "", "",  # Test 3 Label, Reply
            "", "",  # Test 4 Label, Reply
            "", "",  # Test 5 Label, Reply
        ])

    # Write to sheet
    sheets_service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="A1",
        valueInputOption="RAW",
        body={"values": rows}
    ).execute()

    # Format header row
    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "requests": [
                {
                    "repeatCell": {
                        "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 1},
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.2},
                                "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}
                            }
                        },
                        "fields": "userEnteredFormat(backgroundColor,textFormat)"
                    }
                },
                {
                    "updateSheetProperties": {
                        "properties": {"sheetId": 0, "gridProperties": {"frozenRowCount": 1}},
                        "fields": "gridProperties.frozenRowCount"
                    }
                }
            ]
        }
    ).execute()

    print(f"Populated sheet with {len(messages)} emails")
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"


def main():
    parser = argparse.ArgumentParser(description="Label emails and export to sheet")
    parser.add_argument("--query", "-q", default="in:inbox", help="Gmail search query")
    parser.add_argument("--label", "-l", default="Agent Tester", help="Label to apply")
    parser.add_argument("--limit", "-n", type=int, default=100, help="Number of emails")
    parser.add_argument("--sheet", "-s", default="Agent Test Set", help="Sheet name")
    parser.add_argument("--no-label", action="store_true", help="Skip labeling, just export")

    args = parser.parse_args()

    print(f"Connecting to Gmail (nick@nicksaraev.com)...")
    gmail = get_gmail_service()

    print(f"Searching: {args.query} (limit: {args.limit})")
    messages = search_messages(gmail, args.query, args.limit)
    print(f"Found {len(messages)} emails")

    if not messages:
        print("No emails found!")
        return 1

    if not args.no_label:
        print(f"Creating/getting label: {args.label}")
        label_id = get_or_create_label(gmail, args.label)

        print(f"Adding label to emails...")
        batch_add_label(gmail, [m["id"] for m in messages], label_id)

    print(f"Setting up Google Sheet: {args.sheet}")
    sheets = get_sheets_service()
    sheet_id = create_or_get_sheet(sheets, args.sheet)

    print("Populating sheet...")
    sheet_url = populate_sheet(sheets, sheet_id, messages)

    print(f"\nDone!")
    print(f"Sheet URL: {sheet_url}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
