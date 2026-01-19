#!/usr/bin/env python3
"""
Upwork Slack Approval

Sends job approval messages to Slack with interactive buttons for approve/edit/reject.
Messages include job details, fit score, proposal preview, and video link.

Features #42-48: Slack approval workflow

Usage:
    # Send approval for a single job
    python executions/upwork_slack_approval.py --job job.json

    # Send approvals for multiple jobs
    python executions/upwork_slack_approval.py --jobs jobs.json

    # Test mode (don't actually send to Slack)
    python executions/upwork_slack_approval.py --test
"""

import os
import sys
import json
import argparse
import logging
import hashlib
import hmac
import time
from datetime import datetime, timezone
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any, Callable, Union
from pathlib import Path

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
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
SLACK_APPROVAL_CHANNEL = os.getenv("SLACK_APPROVAL_CHANNEL")

# Slack API endpoint
SLACK_API_BASE = "https://slack.com/api"

# Slack message formatting constants for consistent styling (Feature #85)
SLACK_MESSAGE_FORMAT = {
    "header": {
        "emoji": "📋",
        "max_length": 75,  # Max title length before truncation
        "prefix": "New Job:"
    },
    "buttons": {
        "approve": {
            "text": "✅ Approve",
            "style": "primary",
            "action_id": "approve_job"
        },
        "edit": {
            "text": "✏️ Edit",
            "style": None,  # Default style
            "action_id": "edit_job"
        },
        "reject": {
            "text": "❌ Reject",
            "style": "danger",
            "action_id": "reject_job"
        }
    },
    "colors": {
        "excellent": "#36a64f",  # Green for score >= 85
        "good": "#ffc107",       # Yellow/amber for score >= 70
        "low": "#dc3545",        # Red for score < 70
        "unknown": "#808080"     # Gray for None
    },
    "emojis": {
        "excellent": "🟢",
        "good": "🟡",
        "low": "🔴",
        "unknown": "⚪"
    },
    "score_thresholds": {
        "excellent": 85,
        "good": 70
    },
    "status_emojis": {
        "approved": "✅",
        "rejected": "❌",
        "editing": "✏️"
    },
    "section_order": [
        "header",
        "budget_score",
        "client_info",
        "fit_reasoning",
        "divider_1",
        "proposal_preview",
        "links",
        "boost_recommendation",
        "pricing",
        "divider_2",
        "actions",
        "footer"
    ],
    "divider_positions": ["before_proposal", "before_actions"],
    "separator": " | "  # Separator for client info
}

# Google Sheets configuration
UPWORK_PIPELINE_SHEET_ID = os.getenv("UPWORK_PIPELINE_SHEET_ID")

# Import Google Sheets utilities
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


def update_job_status_in_sheet(
    job_id: str,
    status: str,
    additional_fields: Optional[Dict[str, Any]] = None,
    sheet_id: Optional[str] = None,
    mock: bool = False
) -> Dict:
    """
    Update job status and fields in Google Sheet.

    Args:
        job_id: The job ID to update
        status: New status value
        additional_fields: Additional fields to update (e.g., approved_at)
        sheet_id: Sheet ID (defaults to env var)
        mock: If True, don't actually update

    Returns:
        Dict with success status and details
    """
    if mock:
        return {
            "success": True,
            "job_id": job_id,
            "status": status,
            "fields_updated": ["status"] + list(additional_fields.keys() if additional_fields else []),
            "mock": True
        }

    sheet_id = sheet_id or UPWORK_PIPELINE_SHEET_ID
    if not sheet_id:
        return {
            "success": False,
            "error": "UPWORK_PIPELINE_SHEET_ID not configured"
        }

    if not GSPREAD_AVAILABLE:
        return {
            "success": False,
            "error": "gspread not available"
        }

    try:
        client = get_sheets_client()
        if not client:
            return {
                "success": False,
                "error": "Failed to get sheets client"
            }

        # Open the sheet
        spreadsheet = client.open_by_key(sheet_id)
        worksheet = spreadsheet.get_worksheet(0)

        # Find the job row by job_id
        # First, get all job_ids from column A
        all_job_ids = worksheet.col_values(1)  # Column A (job_id)

        # Find the row index (1-based in gspread)
        row_index = None
        for i, cell_value in enumerate(all_job_ids):
            if cell_value == job_id:
                row_index = i + 1  # Convert to 1-based
                break

        if not row_index:
            return {
                "success": False,
                "error": f"Job {job_id} not found in sheet"
            }

        # Get header row to find column indices
        headers = worksheet.row_values(1)

        # Prepare updates
        updates = []

        # Update status (column 3 - 'status')
        if 'status' in headers:
            status_col = headers.index('status') + 1
            updates.append({
                'range': f'{gspread.utils.rowcol_to_a1(row_index, status_col)}',
                'values': [[status]]
            })

        # Update additional fields
        if additional_fields:
            for field_name, field_value in additional_fields.items():
                if field_name in headers:
                    col = headers.index(field_name) + 1
                    # Convert value to string for sheet
                    if isinstance(field_value, datetime):
                        field_value = field_value.isoformat()
                    elif isinstance(field_value, bool):
                        field_value = str(field_value).lower()
                    updates.append({
                        'range': f'{gspread.utils.rowcol_to_a1(row_index, col)}',
                        'values': [[field_value]]
                    })

        # Update updated_at timestamp
        if 'updated_at' in headers:
            updated_col = headers.index('updated_at') + 1
            updates.append({
                'range': f'{gspread.utils.rowcol_to_a1(row_index, updated_col)}',
                'values': [[datetime.now(timezone.utc).isoformat()]]
            })

        # Batch update
        if updates:
            worksheet.batch_update(updates)

        fields_updated = ["status"]
        if additional_fields:
            fields_updated.extend(additional_fields.keys())
        fields_updated.append("updated_at")

        logger.info(f"Updated job {job_id}: status={status}, fields={fields_updated}")

        return {
            "success": True,
            "job_id": job_id,
            "status": status,
            "row_index": row_index,
            "fields_updated": fields_updated
        }

    except Exception as e:
        logger.error(f"Failed to update job {job_id} in sheet: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def get_job_from_sheet(
    job_id: str,
    sheet_id: Optional[str] = None,
    mock: bool = False
) -> Optional[Dict]:
    """
    Get job data from Google Sheet by job_id.

    Args:
        job_id: The job ID to find
        sheet_id: Sheet ID (defaults to env var)
        mock: If True, return mock data

    Returns:
        Job data dictionary or None if not found
    """
    if mock:
        return {
            "job_id": job_id,
            "title": f"Mock Job {job_id}",
            "url": f"https://upwork.com/jobs/{job_id}",
            "status": "pending_approval",
            "proposal_text": "Mock proposal text",
            "proposal_doc_url": "https://docs.google.com/d/mock",
            "video_url": "https://heygen.com/v/mock"
        }

    sheet_id = sheet_id or UPWORK_PIPELINE_SHEET_ID
    if not sheet_id or not GSPREAD_AVAILABLE:
        return None

    try:
        client = get_sheets_client()
        if not client:
            return None

        spreadsheet = client.open_by_key(sheet_id)
        worksheet = spreadsheet.get_worksheet(0)

        # Get all data
        all_data = worksheet.get_all_records()

        # Find the job
        for row in all_data:
            if row.get('job_id') == job_id:
                return row

        return None

    except Exception as e:
        logger.error(f"Failed to get job {job_id} from sheet: {e}")
        return None


@dataclass
class ApprovalCallbackResult:
    """Result of processing an approval callback."""
    success: bool
    job_id: str
    action: str  # approve, reject, edit
    status: Optional[str] = None  # approved, rejected, editing
    approved_at: Optional[str] = None
    trigger_submission: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


def process_approval_callback(
    action: str,
    job_id: str,
    user_id: str,
    channel: str,
    message_ts: str,
    edited_proposal: Optional[str] = None,
    mock: bool = False,
    submission_callback: Optional[Callable[[str], None]] = None
) -> ApprovalCallbackResult:
    """
    Process an approval callback from Slack.

    This is the main entry point for handling button clicks.
    It updates the Google Sheet and triggers appropriate workflows.

    Args:
        action: The action (approve, reject, edit)
        job_id: The job ID
        user_id: Slack user who clicked
        channel: Slack channel ID
        message_ts: Slack message timestamp
        edited_proposal: Updated proposal text (for edit action)
        mock: If True, mock all operations
        submission_callback: Optional callback to trigger submission

    Returns:
        ApprovalCallbackResult with action details
    """
    now = datetime.now(timezone.utc)

    if action == "approve":
        # Update job status to 'approved' and set approved_at
        sheet_result = update_job_status_in_sheet(
            job_id=job_id,
            status="approved",
            additional_fields={
                "approved_at": now,
                "slack_message_ts": message_ts
            },
            mock=mock
        )

        if not sheet_result.get("success"):
            return ApprovalCallbackResult(
                success=False,
                job_id=job_id,
                action=action,
                error=sheet_result.get("error", "Failed to update sheet")
            )

        # Update Slack message
        job_data = get_job_from_sheet(job_id, mock=mock) or {"job_id": job_id, "title": "Job", "url": ""}
        job = JobApprovalData.from_dict(job_data)
        blocks = build_status_update_blocks(job, "approved", user_id)

        update_slack_message(
            channel=channel,
            message_ts=message_ts,
            blocks=blocks,
            text=f"Job approved: {job_id}",
            mock=mock
        )

        # Trigger submission workflow if callback provided
        trigger_submission = True
        if submission_callback and not mock:
            try:
                submission_callback(job_id)
            except Exception as e:
                logger.error(f"Failed to trigger submission for {job_id}: {e}")

        return ApprovalCallbackResult(
            success=True,
            job_id=job_id,
            action=action,
            status="approved",
            approved_at=now.isoformat(),
            trigger_submission=trigger_submission
        )

    elif action == "reject":
        # Update job status to 'rejected'
        sheet_result = update_job_status_in_sheet(
            job_id=job_id,
            status="rejected",
            additional_fields={
                "slack_message_ts": message_ts
            },
            mock=mock
        )

        if not sheet_result.get("success"):
            return ApprovalCallbackResult(
                success=False,
                job_id=job_id,
                action=action,
                error=sheet_result.get("error", "Failed to update sheet")
            )

        # Update Slack message
        job_data = get_job_from_sheet(job_id, mock=mock) or {"job_id": job_id, "title": "Job", "url": ""}
        job = JobApprovalData.from_dict(job_data)
        blocks = build_status_update_blocks(job, "rejected", user_id)

        update_slack_message(
            channel=channel,
            message_ts=message_ts,
            blocks=blocks,
            text=f"Job rejected: {job_id}",
            mock=mock
        )

        return ApprovalCallbackResult(
            success=True,
            job_id=job_id,
            action=action,
            status="rejected"
        )

    elif action == "edit":
        # For edit, we update the proposal text if provided
        additional_fields = {}
        if edited_proposal:
            additional_fields["proposal_text"] = edited_proposal

        if additional_fields:
            sheet_result = update_job_status_in_sheet(
                job_id=job_id,
                status="pending_approval",  # Keep in pending_approval while editing
                additional_fields=additional_fields,
                mock=mock
            )

        return ApprovalCallbackResult(
            success=True,
            job_id=job_id,
            action=action,
            status="editing"
        )

    else:
        return ApprovalCallbackResult(
            success=False,
            job_id=job_id,
            action=action,
            error=f"Unknown action: {action}"
        )


@dataclass
class JobApprovalData:
    """Job data for approval message."""
    job_id: str
    title: str
    url: str
    budget_type: str = "unknown"
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    fit_score: Optional[int] = None
    fit_reasoning: Optional[str] = None
    proposal_text: Optional[str] = None
    proposal_doc_url: Optional[str] = None
    video_url: Optional[str] = None
    pdf_url: Optional[str] = None
    boost_decision: Optional[bool] = None
    boost_reasoning: Optional[str] = None
    client_country: Optional[str] = None
    client_spent: Optional[float] = None
    client_hires: Optional[int] = None
    payment_verified: bool = False
    pricing_proposed: Optional[float] = None
    description: Optional[str] = None
    skills: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict) -> 'JobApprovalData':
        """Create JobApprovalData from a dictionary."""
        # Handle job_id from various sources
        job_id = data.get('job_id') or data.get('id') or ''
        if not job_id and data.get('url'):
            import re
            match = re.search(r'~(\w+)', data['url'])
            if match:
                job_id = f"~{match.group(1)}"

        # Handle skills
        skills = data.get('skills', [])
        if isinstance(skills, str):
            skills = [s.strip() for s in skills.split(',') if s.strip()]

        # Handle client data from nested structure
        client = data.get('client', {})
        if isinstance(client, dict):
            client_country = client.get('country') or data.get('client_country')
            client_spent = client.get('total_spent') or data.get('client_spent')
            client_hires = client.get('total_hires') or data.get('client_hires')
        else:
            client_country = data.get('client_country')
            client_spent = data.get('client_spent')
            client_hires = data.get('client_hires')

        return cls(
            job_id=job_id,
            title=data.get('title', ''),
            url=data.get('url', ''),
            budget_type=data.get('budget_type', 'unknown'),
            budget_min=data.get('budget_min'),
            budget_max=data.get('budget_max'),
            fit_score=data.get('fit_score'),
            fit_reasoning=data.get('fit_reasoning'),
            proposal_text=data.get('proposal_text'),
            proposal_doc_url=data.get('proposal_doc_url'),
            video_url=data.get('video_url'),
            pdf_url=data.get('pdf_url'),
            boost_decision=data.get('boost_decision'),
            boost_reasoning=data.get('boost_reasoning'),
            client_country=client_country,
            client_spent=client_spent,
            client_hires=client_hires,
            payment_verified=data.get('payment_verified', False),
            pricing_proposed=data.get('pricing_proposed'),
            description=data.get('description'),
            skills=skills
        )

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class SlackMessageResult:
    """Result of sending a Slack message."""
    success: bool
    message_ts: Optional[str] = None
    channel: Optional[str] = None
    error: Optional[str] = None
    color: Optional[str] = None  # Color used for the message sidebar (Feature #86)

    def to_dict(self) -> Dict:
        return asdict(self)


def get_score_color(score: Optional[int]) -> str:
    """Get color indicator based on fit score using SLACK_MESSAGE_FORMAT constants."""
    colors = SLACK_MESSAGE_FORMAT["colors"]
    thresholds = SLACK_MESSAGE_FORMAT["score_thresholds"]

    if score is None:
        return colors["unknown"]
    if score >= thresholds["excellent"]:
        return colors["excellent"]
    if score >= thresholds["good"]:
        return colors["good"]
    return colors["low"]


def get_score_emoji(score: Optional[int]) -> str:
    """Get emoji indicator based on fit score using SLACK_MESSAGE_FORMAT constants."""
    emojis = SLACK_MESSAGE_FORMAT["emojis"]
    thresholds = SLACK_MESSAGE_FORMAT["score_thresholds"]

    if score is None:
        return emojis["unknown"]
    if score >= thresholds["excellent"]:
        return emojis["excellent"]
    if score >= thresholds["good"]:
        return emojis["good"]
    return emojis["low"]


def format_budget(job: JobApprovalData) -> str:
    """Format budget display string."""
    if job.budget_type == "fixed":
        if job.budget_min and job.budget_max and job.budget_min != job.budget_max:
            return f"Fixed: ${job.budget_min:,.0f}-${job.budget_max:,.0f}"
        elif job.budget_min:
            return f"Fixed: ${job.budget_min:,.0f}"
        return "Fixed: Not specified"
    elif job.budget_type == "hourly":
        if job.budget_min and job.budget_max:
            return f"Hourly: ${job.budget_min:.0f}-${job.budget_max:.0f}/hr"
        elif job.budget_min:
            return f"Hourly: ${job.budget_min:.0f}/hr"
        return "Hourly: Not specified"
    return "Budget: Not specified"


def format_client_info(job: JobApprovalData) -> str:
    """Format client information display."""
    parts = []

    if job.client_country:
        parts.append(f"📍 {job.client_country}")

    if job.client_spent is not None:
        if job.client_spent >= 1000:
            parts.append(f"💰 ${job.client_spent/1000:.1f}k spent")
        else:
            parts.append(f"💰 ${job.client_spent:.0f} spent")

    if job.client_hires is not None:
        parts.append(f"👥 {job.client_hires} hires")

    if job.payment_verified:
        parts.append("✅ Verified")
    else:
        parts.append("⚠️ Unverified")

    return " | ".join(parts) if parts else "Client info not available"


def truncate_text(text: str, max_length: int = 300) -> str:
    """Truncate text to max length with ellipsis."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def validate_message_format(blocks: List[Dict]) -> Dict:
    """
    Validate that message blocks follow the consistent formatting rules.

    Feature #85: Ensures all Slack messages use consistent formatting.

    Args:
        blocks: List of Slack Block Kit blocks

    Returns:
        Dict with 'valid' (bool) and 'errors' (list of error messages)
    """
    errors = []

    # Check for header
    headers = [b for b in blocks if b.get("type") == "header"]
    if not headers:
        errors.append("Missing header block")
    else:
        header = headers[0]
        header_text = header.get("text", {}).get("text", "")
        expected_emoji = SLACK_MESSAGE_FORMAT["header"]["emoji"]
        if not header_text.startswith(expected_emoji):
            errors.append(f"Header should start with emoji '{expected_emoji}'")

    # Check for actions block
    actions = [b for b in blocks if b.get("type") == "actions"]
    if not actions:
        errors.append("Missing actions block")
    else:
        actions_block = actions[0]
        elements = actions_block.get("elements", [])

        # Check for required buttons
        required_action_ids = ["approve_job", "edit_job", "reject_job"]
        found_action_ids = [e.get("action_id") for e in elements]

        for action_id in required_action_ids:
            if action_id not in found_action_ids:
                errors.append(f"Missing button with action_id '{action_id}'")

        # Verify button count
        if len(elements) != 3:
            errors.append(f"Expected 3 buttons, found {len(elements)}")

        # Verify button order
        if found_action_ids != required_action_ids:
            errors.append(f"Buttons not in expected order: {required_action_ids}")

        # Verify button styles
        for element in elements:
            action_id = element.get("action_id")
            if action_id == "approve_job":
                if element.get("style") != "primary":
                    errors.append("Approve button should have 'primary' style")
            elif action_id == "reject_job":
                if element.get("style") != "danger":
                    errors.append("Reject button should have 'danger' style")

    # Check for at least one divider
    dividers = [b for b in blocks if b.get("type") == "divider"]
    if len(dividers) < 2:
        errors.append(f"Expected at least 2 dividers, found {len(dividers)}")

    return {
        "valid": len(errors) == 0,
        "errors": errors
    }


def build_approval_blocks(job: JobApprovalData) -> List[Dict]:
    """
    Build Slack Block Kit blocks for the approval message.

    Features:
    - Job title and link
    - Budget and fit score
    - Client information
    - Proposal preview (truncated)
    - Links to doc, video, PDF
    - Approve/Edit/Reject buttons
    """
    blocks = []

    # Header with job title (using constants for consistency - Feature #85)
    header_config = SLACK_MESSAGE_FORMAT["header"]
    max_len = header_config["max_length"]
    header_emoji = header_config["emoji"]
    header_prefix = header_config["prefix"]
    truncated_title = job.title[:max_len] + ('...' if len(job.title) > max_len else '')

    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"{header_emoji} {header_prefix} {truncated_title}",
            "emoji": True
        }
    })

    # Job link and score section
    score_emoji = get_score_emoji(job.fit_score)
    score_text = f"{score_emoji} *Fit Score:* {job.fit_score}/100" if job.fit_score else f"{score_emoji} *Fit Score:* N/A"
    budget_text = format_budget(job)

    blocks.append({
        "type": "section",
        "fields": [
            {"type": "mrkdwn", "text": f"*Budget:* {budget_text}"},
            {"type": "mrkdwn", "text": score_text}
        ],
        "accessory": {
            "type": "button",
            "text": {"type": "plain_text", "text": "View Job", "emoji": True},
            "url": job.url,
            "action_id": "view_job"
        }
    })

    # Client info section
    client_info = format_client_info(job)
    blocks.append({
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": f"*Client:* {client_info}"}
        ]
    })

    # Fit reasoning (if available)
    if job.fit_reasoning:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Why this fits:* {truncate_text(job.fit_reasoning, 200)}"
            }
        })

    blocks.append({"type": "divider"})

    # Proposal preview section
    if job.proposal_text:
        proposal_preview = truncate_text(job.proposal_text, 500)
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Proposal Preview:*\n```{proposal_preview}```"
            }
        })

    # Links section (doc, video, PDF)
    link_elements = []
    if job.proposal_doc_url:
        link_elements.append({"type": "mrkdwn", "text": f"📄 <{job.proposal_doc_url}|Proposal Doc>"})
    if job.video_url:
        link_elements.append({"type": "mrkdwn", "text": f"🎬 <{job.video_url}|Video>"})
    if job.pdf_url:
        link_elements.append({"type": "mrkdwn", "text": f"📎 <{job.pdf_url}|PDF>"})

    if link_elements:
        blocks.append({
            "type": "context",
            "elements": link_elements
        })

    # Boost recommendation (if available)
    if job.boost_decision is not None:
        boost_text = "🚀 *Boost Recommended*" if job.boost_decision else "⏸️ *No Boost Recommended*"
        if job.boost_reasoning:
            boost_text += f": {truncate_text(job.boost_reasoning, 100)}"
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": boost_text}]
        })

    # Pricing (if proposed)
    if job.pricing_proposed:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"💵 *Proposed Price:* ${job.pricing_proposed:,.2f}"}]
        })

    blocks.append({"type": "divider"})

    # Action buttons (using constants for consistency - Feature #85)
    button_config = SLACK_MESSAGE_FORMAT["buttons"]

    approve_btn = {
        "type": "button",
        "text": {"type": "plain_text", "text": button_config["approve"]["text"], "emoji": True},
        "style": button_config["approve"]["style"],
        "action_id": button_config["approve"]["action_id"],
        "value": json.dumps({"job_id": job.job_id, "action": "approve"})
    }

    edit_btn = {
        "type": "button",
        "text": {"type": "plain_text", "text": button_config["edit"]["text"], "emoji": True},
        "action_id": button_config["edit"]["action_id"],
        "value": json.dumps({"job_id": job.job_id, "action": "edit"})
    }
    # Edit button has no style (default)

    reject_btn = {
        "type": "button",
        "text": {"type": "plain_text", "text": button_config["reject"]["text"], "emoji": True},
        "style": button_config["reject"]["style"],
        "action_id": button_config["reject"]["action_id"],
        "value": json.dumps({"job_id": job.job_id, "action": "reject"})
    }

    blocks.append({
        "type": "actions",
        "block_id": f"approval_actions_{job.job_id}",
        "elements": [approve_btn, edit_btn, reject_btn]
    })

    # Timestamp footer
    blocks.append({
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": f"Job ID: `{job.job_id}` | Received: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"}
        ]
    })

    return blocks


def send_slack_message(
    channel: str,
    blocks: List[Dict],
    text: str = "New Upwork Job Approval Request",
    token: Optional[str] = None,
    mock: bool = False,
    color: Optional[str] = None
) -> SlackMessageResult:
    """
    Send a message to Slack using the Web API.

    Args:
        channel: Slack channel ID
        blocks: Block Kit blocks
        text: Fallback text
        token: Slack bot token (defaults to env var)
        mock: If True, don't actually send
        color: Optional color for the message sidebar (hex color code, e.g., "#36a64f")
               Used for fit score color coding (Feature #86)

    Returns:
        SlackMessageResult with message_ts and channel
    """
    if mock:
        return SlackMessageResult(
            success=True,
            message_ts=f"mock_{datetime.utcnow().timestamp()}",
            channel=channel,
            color=color  # Include color in mock result for testing
        )

    token = token or SLACK_BOT_TOKEN
    if not token:
        return SlackMessageResult(
            success=False,
            error="SLACK_BOT_TOKEN not configured"
        )

    try:
        import urllib.request

        payload = {
            "channel": channel,
            "text": text,
            "blocks": blocks
        }

        # Add attachments with color sidebar for fit score visual indicator (Feature #86)
        if color:
            payload["attachments"] = [{
                "color": color,
                "blocks": []  # Empty blocks, color bar shows alongside main blocks
            }]

        data = json.dumps(payload).encode('utf-8')
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }

        req = urllib.request.Request(
            f"{SLACK_API_BASE}/chat.postMessage",
            data=data,
            headers=headers,
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))

        if result.get("ok"):
            return SlackMessageResult(
                success=True,
                message_ts=result.get("ts"),
                channel=result.get("channel")
            )
        else:
            return SlackMessageResult(
                success=False,
                error=result.get("error", "Unknown Slack API error")
            )

    except Exception as e:
        logger.error(f"Failed to send Slack message: {e}")
        return SlackMessageResult(
            success=False,
            error=str(e)
        )


def update_slack_message(
    channel: str,
    message_ts: str,
    blocks: List[Dict],
    text: str = "Updated",
    token: Optional[str] = None,
    mock: bool = False
) -> SlackMessageResult:
    """Update an existing Slack message."""
    if mock:
        return SlackMessageResult(
            success=True,
            message_ts=message_ts,
            channel=channel
        )

    token = token or SLACK_BOT_TOKEN
    if not token:
        return SlackMessageResult(
            success=False,
            error="SLACK_BOT_TOKEN not configured"
        )

    try:
        import urllib.request

        payload = {
            "channel": channel,
            "ts": message_ts,
            "text": text,
            "blocks": blocks
        }

        data = json.dumps(payload).encode('utf-8')
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }

        req = urllib.request.Request(
            f"{SLACK_API_BASE}/chat.update",
            data=data,
            headers=headers,
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))

        if result.get("ok"):
            return SlackMessageResult(
                success=True,
                message_ts=result.get("ts"),
                channel=result.get("channel")
            )
        else:
            return SlackMessageResult(
                success=False,
                error=result.get("error", "Unknown Slack API error")
            )

    except Exception as e:
        logger.error(f"Failed to update Slack message: {e}")
        return SlackMessageResult(
            success=False,
            error=str(e)
        )


def verify_slack_signature(
    timestamp: str,
    body: str,
    signature: str,
    signing_secret: Optional[str] = None
) -> bool:
    """
    Verify Slack request signature.

    Args:
        timestamp: X-Slack-Request-Timestamp header
        body: Raw request body
        signature: X-Slack-Signature header
        signing_secret: Slack signing secret (defaults to env var)

    Returns:
        True if signature is valid
    """
    signing_secret = signing_secret or SLACK_SIGNING_SECRET
    if not signing_secret:
        logger.warning("SLACK_SIGNING_SECRET not configured")
        return False

    # Check timestamp (prevent replay attacks - allow 5 min window)
    try:
        if abs(time.time() - float(timestamp)) > 300:
            logger.warning("Slack request timestamp too old")
            return False
    except (ValueError, TypeError):
        logger.warning("Invalid Slack timestamp")
        return False

    # Compute expected signature
    sig_basestring = f"v0:{timestamp}:{body}"
    expected_sig = "v0=" + hmac.new(
        signing_secret.encode('utf-8'),
        sig_basestring.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    # Compare signatures (timing-safe)
    return hmac.compare_digest(expected_sig, signature)


def send_approval_message(
    job: Union[JobApprovalData, Dict],
    channel: Optional[str] = None,
    token: Optional[str] = None,
    mock: bool = False
) -> SlackMessageResult:
    """
    Send an approval message for a job.

    Args:
        job: Job approval data (JobApprovalData or dict, dict will be converted)
        channel: Slack channel ID (defaults to env var)
        token: Slack bot token (defaults to env var)
        mock: If True, don't actually send

    Returns:
        SlackMessageResult with message_ts and color (Feature #86)
    """
    # Convert dict to JobApprovalData if needed
    if isinstance(job, dict):
        job = JobApprovalData.from_dict(job)

    channel = channel or SLACK_APPROVAL_CHANNEL
    if not channel:
        return SlackMessageResult(
            success=False,
            error="SLACK_APPROVAL_CHANNEL not configured"
        )

    blocks = build_approval_blocks(job)
    fallback_text = f"New Upwork Job: {job.title} (Score: {job.fit_score or 'N/A'})"

    # Get color based on fit score for visual indicator (Feature #86)
    score_color = get_score_color(job.fit_score)

    result = send_slack_message(
        channel=channel,
        blocks=blocks,
        text=fallback_text,
        token=token,
        mock=mock,
        color=score_color  # Pass color for sidebar indicator (Feature #86)
    )

    if result.success:
        logger.info(f"Approval message sent for job {job.job_id}: ts={result.message_ts}, color={score_color}")
    else:
        logger.error(f"Failed to send approval for job {job.job_id}: {result.error}")

    return result


def build_status_update_blocks(
    job: JobApprovalData,
    status: str,
    user: Optional[str] = None
) -> List[Dict]:
    """Build blocks for a status update (approved/rejected).

    Uses SLACK_MESSAGE_FORMAT constants for consistent emoji display (Feature #85).
    """
    status_emojis = SLACK_MESSAGE_FORMAT["status_emojis"]

    if status == "approved":
        emoji = status_emojis["approved"]
        title = "APPROVED"
        color_style = "primary"
    elif status == "rejected":
        emoji = status_emojis["rejected"]
        title = "REJECTED"
        color_style = "danger"
    else:
        emoji = status_emojis["editing"]
        title = "EDITING"
        color_style = None

    blocks = []

    # Updated header
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"{emoji} {title}: {job.title[:60]}{'...' if len(job.title) > 60 else ''}",
            "emoji": True
        }
    })

    # Status info
    status_text = f"*Status:* {title}"
    if user:
        status_text += f" by <@{user}>"

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": status_text}
    })

    # Original job link
    blocks.append({
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": f"Job ID: `{job.job_id}` | <{job.url}|View Job>"}
        ]
    })

    # Links to deliverables
    link_elements = []
    if job.proposal_doc_url:
        link_elements.append({"type": "mrkdwn", "text": f"📄 <{job.proposal_doc_url}|Proposal>"})
    if job.video_url:
        link_elements.append({"type": "mrkdwn", "text": f"🎬 <{job.video_url}|Video>"})

    if link_elements:
        blocks.append({
            "type": "context",
            "elements": link_elements
        })

    # Timestamp
    blocks.append({
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": f"Updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"}
        ]
    })

    return blocks


def handle_button_action(
    action_id: str,
    value: str,
    user_id: str,
    channel: str,
    message_ts: str,
    mock: bool = False
) -> Dict:
    """
    Handle a button action from Slack.

    Args:
        action_id: The action ID (approve_job, edit_job, reject_job)
        value: JSON-encoded action value
        user_id: Slack user ID who clicked
        channel: Channel ID
        message_ts: Original message timestamp
        mock: If True, don't actually update

    Returns:
        Dict with action result
    """
    try:
        action_data = json.loads(value)
        job_id = action_data.get("job_id")
        action = action_data.get("action")
    except json.JSONDecodeError:
        return {"success": False, "error": "Invalid action value"}

    # Create minimal job data for status update
    job = JobApprovalData(job_id=job_id, title="Job", url="")

    if action == "approve":
        status = "approved"
    elif action == "reject":
        status = "rejected"
    elif action == "edit":
        # Edit action returns modal info (handled separately)
        return {
            "success": True,
            "action": "edit",
            "job_id": job_id,
            "trigger_modal": True
        }
    else:
        return {"success": False, "error": f"Unknown action: {action}"}

    # Update the message
    blocks = build_status_update_blocks(job, status, user_id)
    result = update_slack_message(
        channel=channel,
        message_ts=message_ts,
        blocks=blocks,
        text=f"Job {status}: {job_id}",
        mock=mock
    )

    return {
        "success": result.success,
        "action": action,
        "job_id": job_id,
        "status": status,
        "error": result.error
    }


def main():
    parser = argparse.ArgumentParser(description="Send Upwork job approval messages to Slack")
    parser.add_argument("--job", "-j", help="JSON file with single job data")
    parser.add_argument("--jobs", help="JSON file with multiple jobs")
    parser.add_argument("--channel", "-c", help="Slack channel ID (overrides env)")
    parser.add_argument("--mock", action="store_true", help="Mock mode (don't send to Slack)")
    parser.add_argument("--test", action="store_true", help="Run with test data")
    parser.add_argument("--output", "-o", help="Output JSON file for results")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Test mode
    if args.test:
        test_job = JobApprovalData(
            job_id="~test123abc",
            title="Build AI-Powered Lead Generation Pipeline with n8n and Claude",
            url="https://www.upwork.com/jobs/~test123abc",
            budget_type="fixed",
            budget_min=1500,
            budget_max=2500,
            fit_score=87,
            fit_reasoning="Strong match for AI automation expertise. Client needs n8n workflows with Claude API integration - exactly our specialty.",
            proposal_text="Hey.\n\nI spent ~15 minutes putting this together for you. In short, it's how I would create your AI lead gen pipeline end to end.\n\nI've worked with companies like Anthropic and have extensive experience building similar systems.\n\nMy proposed approach\n\n1. First, I would analyze your current lead sources...\n2. Then build the n8n workflow with Claude integration...\n3. Test thoroughly with sample data...\n4. Deploy and document everything.",
            proposal_doc_url="https://docs.google.com/document/d/1234567890/edit",
            video_url="https://heygen.com/videos/test123",
            pdf_url="https://drive.google.com/file/d/abc123/view",
            boost_decision=True,
            boost_reasoning="High-value client with $15k+ spent and verified payment.",
            client_country="United States",
            client_spent=15000,
            client_hires=12,
            payment_verified=True,
            pricing_proposed=2000,
            skills=["n8n", "AI", "Claude API", "Python", "Automation"]
        )

        print("Test job data:")
        print(json.dumps(test_job.to_dict(), indent=2))
        print("\n" + "="*50 + "\n")

        print("Building approval blocks...")
        blocks = build_approval_blocks(test_job)
        print(json.dumps(blocks, indent=2))
        print("\n" + "="*50 + "\n")

        print("Sending approval message (mock mode)...")
        result = send_approval_message(
            job=test_job,
            channel=args.channel or "C0123456789",
            mock=True
        )
        print(f"Result: {json.dumps(result.to_dict(), indent=2)}")
        return

    # Load job(s)
    if args.job:
        with open(args.job) as f:
            job_data = json.load(f)
        jobs = [JobApprovalData.from_dict(job_data)]
    elif args.jobs:
        with open(args.jobs) as f:
            jobs_data = json.load(f)
        jobs = [JobApprovalData.from_dict(j) for j in jobs_data]
    else:
        print("Error: Must provide --job, --jobs, or --test")
        sys.exit(1)

    # Send approval messages
    results = []
    for job in jobs:
        result = send_approval_message(
            job=job,
            channel=args.channel,
            mock=args.mock
        )
        results.append({
            "job_id": job.job_id,
            **result.to_dict()
        })

    # Output results
    output = results if len(results) > 1 else results[0]

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(output, f, indent=2)
        print(f"Results saved to {args.output}")
    else:
        print(json.dumps(output, indent=2))

    # Summary
    success_count = sum(1 for r in results if r.get("success"))
    print(f"\nSent {success_count}/{len(results)} approval messages")


if __name__ == "__main__":
    main()
