"""
Local FastAPI server for running agentic directives.
Same code as Modal, but runs on your laptop.

Run: uvicorn execution.local_server:app --reload --port 8000
Expose: ngrok http 8000

Endpoints:
  GET  /               - Server info
  POST /webhook/{slug} - Execute directive by slug
  GET  /webhooks       - List available webhooks

  # Web UI API
  POST /api/auth/login    - Login with password
  GET  /api/auth/verify   - Verify JWT token
  GET  /api/jobs          - List jobs with filters
  GET  /api/jobs/stats    - Get job statistics
  GET  /api/jobs/{job_id} - Get single job
  GET  /api/approvals/pending       - List pending approvals
  POST /api/approvals/{job_id}/approve - Approve job
  POST /api/approvals/{job_id}/reject  - Reject job
  PUT  /api/approvals/{job_id}/proposal - Update proposal
  POST /api/approvals/{job_id}/submit   - Submit job
  GET  /api/admin/config   - Get config
  POST /api/admin/pipeline/trigger - Trigger pipeline
  GET  /api/admin/pipeline/status  - Get pipeline status
  GET  /api/admin/logs     - Get logs
  GET  /api/admin/health   - Get health status
"""

import os
import json
import logging
import subprocess
import sys
import secrets
import re
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict

from fastapi import FastAPI, HTTPException, Depends, Header, Query, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from anthropic import Anthropic
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("local-orchestrator")

# Store logs in memory for the admin panel
LOG_BUFFER: List[Dict] = []
MAX_LOG_ENTRIES = 1000

class LogHandler(logging.Handler):
    """Custom log handler that stores logs in memory."""
    def emit(self, record):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name
        }
        LOG_BUFFER.append(log_entry)
        if len(LOG_BUFFER) > MAX_LOG_ENTRIES:
            LOG_BUFFER.pop(0)

# Add custom handler to root logger
logging.getLogger().addHandler(LogHandler())

app = FastAPI(title="Claude Orchestrator (Local)", version="1.0")

# CORS middleware for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# JWT AUTHENTICATION
# ============================================================================

# JWT settings
UI_PASSWORD = os.getenv("UI_PASSWORD", "changeme")
JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# Simple JWT implementation (no external dependency)
import base64
import hmac
import hashlib

def base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')

def base64url_decode(data: str) -> bytes:
    padding = 4 - len(data) % 4
    if padding != 4:
        data += '=' * padding
    return base64.urlsafe_b64decode(data)

def create_jwt(payload: dict) -> str:
    """Create a simple JWT token."""
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}

    # Add expiration
    payload["exp"] = (datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)).timestamp()
    payload["iat"] = datetime.now(timezone.utc).timestamp()

    header_b64 = base64url_encode(json.dumps(header).encode())
    payload_b64 = base64url_encode(json.dumps(payload).encode())

    message = f"{header_b64}.{payload_b64}"
    signature = hmac.new(
        JWT_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).digest()
    signature_b64 = base64url_encode(signature)

    return f"{message}.{signature_b64}"

def verify_jwt(token: str) -> Optional[dict]:
    """Verify a JWT token and return payload if valid."""
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None

        header_b64, payload_b64, signature_b64 = parts

        # Verify signature
        message = f"{header_b64}.{payload_b64}"
        expected_signature = hmac.new(
            JWT_SECRET.encode(),
            message.encode(),
            hashlib.sha256
        ).digest()

        actual_signature = base64url_decode(signature_b64)

        if not hmac.compare_digest(expected_signature, actual_signature):
            return None

        # Decode payload
        payload = json.loads(base64url_decode(payload_b64))

        # Check expiration
        if payload.get("exp", 0) < datetime.now(timezone.utc).timestamp():
            return None

        return payload
    except Exception as e:
        logger.error(f"JWT verification error: {e}")
        return None

async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """Dependency to get current authenticated user."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization[7:]
    payload = verify_jwt(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return payload

# ============================================================================
# GOOGLE SHEETS UTILITIES
# ============================================================================

UPWORK_PIPELINE_SHEET_ID = os.getenv("UPWORK_PIPELINE_SHEET_ID")

# Import column definitions
try:
    from upwork_sheets_setup import PIPELINE_COLUMNS, get_credentials
    SHEETS_AVAILABLE = True
except ImportError:
    PIPELINE_COLUMNS = [
        "job_id", "source", "status", "title", "url", "description",
        "attachments", "budget_type", "budget_min", "budget_max",
        "client_country", "client_spent", "client_hires", "payment_verified",
        "fit_score", "fit_reasoning", "proposal_doc_url", "proposal_text",
        "video_url", "pdf_url", "boost_decision", "boost_reasoning",
        "pricing_proposed", "slack_message_ts", "approved_at", "submitted_at",
        "error_log", "created_at", "updated_at"
    ]
    SHEETS_AVAILABLE = False

try:
    import gspread
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False
    logger.warning("gspread not available")

def get_sheets_client():
    """Get authenticated gspread client."""
    if not GSPREAD_AVAILABLE:
        return None

    token_paths = ['config/token.json', 'configuration/token.json']
    creds = None

    for token_path in token_paths:
        if os.path.exists(token_path):
            try:
                with open(token_path) as f:
                    token_data = json.load(f)
                creds = Credentials(
                    token=token_data.get("token"),
                    refresh_token=token_data.get("refresh_token"),
                    token_uri=token_data.get("token_uri"),
                    client_id=token_data.get("client_id"),
                    client_secret=token_data.get("client_secret"),
                    scopes=token_data.get("scopes")
                )
                break
            except Exception as e:
                logger.warning(f"Failed to load token from {token_path}: {e}")

    if not creds:
        return None

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as e:
            logger.error(f"Failed to refresh credentials: {e}")
            return None

    try:
        return gspread.authorize(creds)
    except Exception as e:
        logger.error(f"Failed to authorize gspread: {e}")
        return None

def get_all_jobs_from_sheet() -> List[Dict]:
    """Get all jobs from Google Sheet."""
    if not UPWORK_PIPELINE_SHEET_ID:
        return []

    client = get_sheets_client()
    if not client:
        return []

    try:
        spreadsheet = client.open_by_key(UPWORK_PIPELINE_SHEET_ID)
        worksheet = spreadsheet.get_worksheet(0)
        records = worksheet.get_all_records()

        # Convert to proper types
        for record in records:
            # Convert numeric fields
            for field in ['budget_min', 'budget_max', 'client_spent', 'fit_score', 'client_hires']:
                if record.get(field) and record[field] != '':
                    try:
                        record[field] = float(record[field]) if '.' in str(record[field]) else int(record[field])
                    except (ValueError, TypeError):
                        record[field] = None
                else:
                    record[field] = None

            # Convert boolean fields
            for field in ['payment_verified', 'boost_decision']:
                val = record.get(field, '')
                record[field] = str(val).lower() in ('true', '1', 'yes')

        return records
    except Exception as e:
        logger.error(f"Failed to get jobs from sheet: {e}")
        return []

def update_job_in_sheet(job_id: str, updates: Dict[str, Any]) -> bool:
    """Update a job in Google Sheet."""
    if not UPWORK_PIPELINE_SHEET_ID:
        return False

    client = get_sheets_client()
    if not client:
        return False

    try:
        spreadsheet = client.open_by_key(UPWORK_PIPELINE_SHEET_ID)
        worksheet = spreadsheet.get_worksheet(0)

        # Find the job row
        all_job_ids = worksheet.col_values(1)
        row_index = None
        for i, cell_value in enumerate(all_job_ids):
            if cell_value == job_id:
                row_index = i + 1
                break

        if not row_index:
            return False

        # Get headers
        headers = worksheet.row_values(1)

        # Prepare updates
        batch_updates = []
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()

        for field_name, field_value in updates.items():
            if field_name in headers:
                col = headers.index(field_name) + 1
                if isinstance(field_value, datetime):
                    field_value = field_value.isoformat()
                elif isinstance(field_value, bool):
                    field_value = str(field_value).lower()
                batch_updates.append({
                    'range': gspread.utils.rowcol_to_a1(row_index, col),
                    'values': [[field_value]]
                })

        if batch_updates:
            worksheet.batch_update(batch_updates)

        return True
    except Exception as e:
        logger.error(f"Failed to update job {job_id}: {e}")
        return False

def add_jobs_to_sheet(jobs: List[Dict]) -> int:
    """Add new jobs to Google Sheet, skipping duplicates.

    Args:
        jobs: List of job dicts from scraper (with id, title, description, etc.)

    Returns:
        Number of jobs added
    """
    if not UPWORK_PIPELINE_SHEET_ID:
        logger.error("UPWORK_PIPELINE_SHEET_ID not set")
        return 0

    client = get_sheets_client()
    if not client:
        logger.error("Could not get sheets client")
        return 0

    try:
        spreadsheet = client.open_by_key(UPWORK_PIPELINE_SHEET_ID)
        worksheet = spreadsheet.get_worksheet(0)

        # Get existing job IDs to avoid duplicates
        existing_ids = set(worksheet.col_values(1)[1:])  # Skip header

        # Get headers
        headers = worksheet.row_values(1)

        now = datetime.now(timezone.utc).isoformat()
        added_count = 0
        rows_to_add = []

        for job in jobs:
            # Handle different ID field names from various scrapers
            job_id = str(job.get('id') or job.get('uid') or job.get('job_id') or '')
            if not job_id or job_id in existing_ids:
                continue

            # Parse budget
            budget_raw = job.get('budget_raw', {})
            hourly = budget_raw.get('hourlyRate', {})
            fixed = budget_raw.get('fixedBudget')

            if fixed:
                budget_type = 'fixed'
                budget_min = fixed
                budget_max = fixed
            elif hourly.get('min') or hourly.get('max'):
                budget_type = 'hourly'
                budget_min = hourly.get('min')
                budget_max = hourly.get('max')
            else:
                budget_type = 'unknown'
                budget_min = None
                budget_max = None

            client_data = job.get('client', {})

            # Map job data to sheet columns
            row_data = {
                'job_id': job_id,
                'source': job.get('source', 'apify'),
                'status': 'new',
                'title': job.get('title', '')[:500],  # Truncate long titles
                'url': job.get('url', ''),
                'description': job.get('description', '')[:5000],  # Truncate long descriptions
                'attachments': '',
                'budget_type': budget_type,
                'budget_min': budget_min or '',
                'budget_max': budget_max or '',
                'client_country': client_data.get('country', ''),
                'client_spent': client_data.get('total_spent', ''),
                'client_hires': client_data.get('total_hires', ''),
                'payment_verified': str(client_data.get('payment_verified', False)).lower(),
                'fit_score': '',
                'fit_reasoning': '',
                'proposal_doc_url': '',
                'proposal_text': '',
                'video_url': '',
                'pdf_url': '',
                'boost_decision': '',
                'boost_reasoning': '',
                'pricing_proposed': '',
                'slack_message_ts': '',
                'approved_at': '',
                'submitted_at': '',
                'error_log': '',
                'created_at': now,
                'updated_at': now,
            }

            # Build row in column order
            row = []
            for col in headers:
                row.append(row_data.get(col, ''))

            rows_to_add.append(row)
            existing_ids.add(job_id)  # Prevent duplicates within batch
            added_count += 1

        # Batch add all new rows
        if rows_to_add:
            worksheet.append_rows(rows_to_add, value_input_option='USER_ENTERED')
            logger.info(f"Added {added_count} jobs to sheet")

        return added_count
    except Exception as e:
        logger.error(f"Failed to add jobs to sheet: {e}")
        return 0

# ============================================================================
# PIPELINE STATUS TRACKING
# ============================================================================

PIPELINE_STATUS = {
    "is_running": False,
    "last_run_time": None,
    "last_run_status": None,
    "current_run_id": None,
    "jobs_processed_today": 0,
    "last_reset_date": datetime.now(timezone.utc).date().isoformat()
}

def reset_daily_counter():
    """Reset daily counter if it's a new day."""
    today = datetime.now(timezone.utc).date().isoformat()
    if PIPELINE_STATUS["last_reset_date"] != today:
        PIPELINE_STATUS["jobs_processed_today"] = 0
        PIPELINE_STATUS["last_reset_date"] = today

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class LoginRequest(BaseModel):
    password: str

class PipelineTriggerRequest(BaseModel):
    source: str = "apify"
    limit: int = 10
    keywords: Optional[str] = None  # Comma-separated keywords to filter jobs
    location: Optional[str] = None  # Location filter (e.g., "United States", "Remote")
    run_full_pipeline: bool = False  # If True, run full pipeline (score, extract, generate, approve)
    min_score: int = 70  # Minimum fit score for full pipeline

class ProposalUpdateRequest(BaseModel):
    proposal_text: str

class ConfigUpdateRequest(BaseModel):
    config: Dict[str, str]

# ============================================================================
# AUTH ENDPOINTS
# ============================================================================

@app.post("/api/auth/login")
async def api_login(request: LoginRequest):
    """Login with password and get JWT token."""
    if request.password != UI_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid password")

    token = create_jwt({"sub": "user", "type": "access"})
    return {"token": token, "expires_in": JWT_EXPIRATION_HOURS * 3600}

@app.get("/api/auth/verify")
async def api_verify(user: dict = Depends(get_current_user)):
    """Verify JWT token is valid."""
    return {"valid": True, "user": user.get("sub")}

# ============================================================================
# JOBS ENDPOINTS
# ============================================================================

@app.get("/api/jobs")
async def api_get_jobs(
    status: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    user: dict = Depends(get_current_user)
):
    """List jobs with filters and pagination."""
    jobs = get_all_jobs_from_sheet()

    # Filter by status
    if status:
        jobs = [j for j in jobs if j.get("status") == status]

    # Filter by search
    if search:
        search_lower = search.lower()
        jobs = [j for j in jobs if
                search_lower in (j.get("title") or "").lower() or
                search_lower in (j.get("description") or "").lower() or
                search_lower in (j.get("job_id") or "").lower()]

    # Sort
    reverse = sort_order == "desc"
    jobs.sort(key=lambda x: x.get(sort_by) or "", reverse=reverse)

    # Paginate
    total = len(jobs)
    start = (page - 1) * per_page
    end = start + per_page
    jobs = jobs[start:end]

    return {
        "jobs": jobs,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page
    }

@app.get("/api/jobs/stats")
async def api_get_job_stats(user: dict = Depends(get_current_user)):
    """Get job statistics."""
    jobs = get_all_jobs_from_sheet()

    # Count by status
    by_status = {}
    for job in jobs:
        status = job.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1

    # Calculate average fit score
    scores = [j.get("fit_score") for j in jobs if j.get("fit_score") is not None]
    avg_score = sum(scores) / len(scores) if scores else None

    # Count today's processed
    today = datetime.now(timezone.utc).date().isoformat()
    today_count = sum(1 for j in jobs if
                     j.get("submitted_at", "").startswith(today) or
                     j.get("approved_at", "").startswith(today))

    reset_daily_counter()

    return {
        "total": len(jobs),
        "by_status": by_status,
        "avg_fit_score": avg_score,
        "today_processed": today_count or PIPELINE_STATUS["jobs_processed_today"]
    }

@app.get("/api/jobs/{job_id}")
async def api_get_job(job_id: str, user: dict = Depends(get_current_user)):
    """Get a single job by ID."""
    jobs = get_all_jobs_from_sheet()

    for job in jobs:
        if job.get("job_id") == job_id:
            return job

    raise HTTPException(status_code=404, detail="Job not found")

# ============================================================================
# APPROVALS ENDPOINTS
# ============================================================================

@app.get("/api/approvals/pending")
async def api_get_pending_approvals(user: dict = Depends(get_current_user)):
    """Get all pending approval jobs."""
    jobs = get_all_jobs_from_sheet()
    pending = [j for j in jobs if j.get("status") == "pending_approval"]

    # Sort by fit score (highest first)
    pending.sort(key=lambda x: x.get("fit_score") or 0, reverse=True)

    return pending

@app.post("/api/approvals/{job_id}/approve")
async def api_approve_job(job_id: str, user: dict = Depends(get_current_user)):
    """Approve a job for submission."""
    now = datetime.now(timezone.utc)

    success = update_job_in_sheet(job_id, {
        "status": "approved",
        "approved_at": now.isoformat()
    })

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update job")

    logger.info(f"Job {job_id} approved via Web UI")

    return {
        "success": True,
        "job_id": job_id,
        "status": "approved",
        "approved_at": now.isoformat()
    }

@app.post("/api/approvals/{job_id}/reject")
async def api_reject_job(job_id: str, user: dict = Depends(get_current_user)):
    """Reject a job."""
    success = update_job_in_sheet(job_id, {
        "status": "rejected"
    })

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update job")

    logger.info(f"Job {job_id} rejected via Web UI")

    return {
        "success": True,
        "job_id": job_id,
        "status": "rejected"
    }

@app.put("/api/approvals/{job_id}/proposal")
async def api_update_proposal(
    job_id: str,
    request: ProposalUpdateRequest,
    user: dict = Depends(get_current_user)
):
    """Update a job's proposal text."""
    success = update_job_in_sheet(job_id, {
        "proposal_text": request.proposal_text
    })

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update proposal")

    logger.info(f"Proposal updated for job {job_id}")

    return {
        "success": True,
        "job_id": job_id,
        "message": "Proposal updated"
    }

@app.post("/api/approvals/{job_id}/submit")
async def api_submit_job(job_id: str, user: dict = Depends(get_current_user)):
    """Trigger submission for an approved job."""
    # First check job is approved
    jobs = get_all_jobs_from_sheet()
    job = next((j for j in jobs if j.get("job_id") == job_id), None)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("status") != "approved":
        raise HTTPException(status_code=400, detail="Job must be approved before submission")

    now = datetime.now(timezone.utc)

    # Update status to submitted
    success = update_job_in_sheet(job_id, {
        "status": "submitted",
        "submitted_at": now.isoformat()
    })

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update job")

    PIPELINE_STATUS["jobs_processed_today"] += 1
    logger.info(f"Job {job_id} submitted via Web UI")

    return {
        "success": True,
        "job_id": job_id,
        "status": "submitted",
        "submitted_at": now.isoformat()
    }

# ============================================================================
# ADMIN ENDPOINTS
# ============================================================================

# Define config items with metadata
CONFIG_ITEMS = [
    {"key": "UPWORK_PIPELINE_SHEET_ID", "label": "Pipeline Sheet ID", "sensitive": False, "editable": True, "description": "Google Sheet ID for job pipeline"},
    {"key": "UPWORK_PROCESSED_IDS_SHEET_ID", "label": "Processed IDs Sheet ID", "sensitive": False, "editable": True, "description": "Google Sheet ID for deduplication"},
    {"key": "PREFILTER_MIN_SCORE", "label": "Min Pre-filter Score", "sensitive": False, "editable": True, "description": "Minimum score (0-100) to proceed with processing"},
    {"key": "SLACK_BOT_TOKEN", "label": "Slack Bot Token", "sensitive": True, "editable": True, "description": "Slack bot token for notifications"},
    {"key": "SLACK_APPROVAL_CHANNEL", "label": "Slack Approval Channel", "sensitive": False, "editable": True, "description": "Slack channel ID for approvals"},
    {"key": "OPENAI_API_KEY", "label": "OpenAI API Key", "sensitive": True, "editable": True, "description": "OpenAI API key"},
    {"key": "ANTHROPIC_API_KEY", "label": "Anthropic API Key", "sensitive": True, "editable": True, "description": "Anthropic API key for Claude"},
    {"key": "APIFY_API_TOKEN", "label": "Apify API Token", "sensitive": True, "editable": True, "description": "Apify token for web scraping"},
    {"key": "HEYGEN_API_KEY", "label": "HeyGen API Key", "sensitive": True, "editable": True, "description": "HeyGen API key for video generation"},
    {"key": "HEYGEN_AVATAR_ID", "label": "HeyGen Avatar ID", "sensitive": False, "editable": True, "description": "HeyGen avatar ID for videos"},
    {"key": "UI_PASSWORD", "label": "UI Password", "sensitive": True, "editable": True, "description": "Password for web UI login"},
    {"key": "JWT_SECRET", "label": "JWT Secret", "sensitive": True, "editable": False, "description": "Secret key for JWT tokens (auto-generated)"},
]

def read_env_file() -> Dict[str, str]:
    """Read .env file and return key-value pairs."""
    env_path = Path(__file__).parent.parent / ".env"
    env_vars = {}

    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                # Parse key=value
                if '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()

    return env_vars

def write_env_file(updates: Dict[str, str]) -> bool:
    """Update .env file with new values, preserving comments and structure."""
    env_path = Path(__file__).parent.parent / ".env"

    if not env_path.exists():
        return False

    # Read existing file
    with open(env_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Track which keys we've updated
    updated_keys = set()
    new_lines = []

    for line in lines:
        stripped = line.strip()

        # Keep comments and empty lines as-is
        if not stripped or stripped.startswith('#'):
            new_lines.append(line)
            continue

        # Parse key=value
        if '=' in stripped:
            key = stripped.split('=', 1)[0].strip()
            if key in updates:
                # Replace with new value
                new_lines.append(f"{key}={updates[key]}\n")
                updated_keys.add(key)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    # Add any new keys that weren't in the file
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}\n")

    # Write back
    with open(env_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

    # Reload environment variables
    for key, value in updates.items():
        os.environ[key] = value

    return True

@app.get("/api/admin/config")
async def api_get_config(user: dict = Depends(get_current_user)):
    """Get configuration with metadata."""
    # Read current values from .env file (not just os.environ)
    env_values = read_env_file()

    config_items = []
    for item in CONFIG_ITEMS:
        key = item["key"]
        raw_value = env_values.get(key) or os.getenv(key, "")

        # Mask sensitive values for display
        if item["sensitive"] and raw_value:
            if len(raw_value) > 8:
                display_value = raw_value[:4] + "****" + raw_value[-4:]
            else:
                display_value = "****"
        else:
            display_value = raw_value or "(not set)"

        config_items.append({
            "key": key,
            "label": item["label"],
            "value": display_value,
            "raw_value": raw_value if not item["sensitive"] else "",  # Only send raw for non-sensitive
            "sensitive": item["sensitive"],
            "editable": item["editable"],
            "description": item["description"],
            "is_set": bool(raw_value)
        })

    return {"config": config_items}

@app.put("/api/admin/config")
async def api_update_config(
    request: ConfigUpdateRequest,
    user: dict = Depends(get_current_user)
):
    """Update configuration values in .env file."""
    # Validate that all keys are editable
    editable_keys = {item["key"] for item in CONFIG_ITEMS if item["editable"]}

    updates = {}
    for key, value in request.config.items():
        if key not in editable_keys:
            raise HTTPException(
                status_code=400,
                detail=f"Config key '{key}' is not editable"
            )
        # Don't update if value is masked (unchanged sensitive field)
        if "****" not in value:
            updates[key] = value

    if not updates:
        return {"success": True, "message": "No changes to save", "updated": []}

    # Write updates to .env file
    success = write_env_file(updates)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update .env file")

    logger.info(f"Config updated: {list(updates.keys())}")

    return {
        "success": True,
        "message": f"Updated {len(updates)} config value(s)",
        "updated": list(updates.keys())
    }

@app.post("/api/admin/pipeline/trigger")
async def api_trigger_pipeline(
    request: PipelineTriggerRequest,
    user: dict = Depends(get_current_user)
):
    """Trigger a pipeline run."""
    if PIPELINE_STATUS["is_running"]:
        raise HTTPException(status_code=409, detail="Pipeline is already running")

    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    PIPELINE_STATUS["is_running"] = True
    PIPELINE_STATUS["current_run_id"] = run_id
    PIPELINE_STATUS["last_run_time"] = datetime.now(timezone.utc).isoformat()
    PIPELINE_STATUS["last_run_status"] = "running"

    logger.info(f"Pipeline triggered: source={request.source}, limit={request.limit}, keywords={request.keywords}, location={request.location}, run_full={request.run_full_pipeline}, run_id={run_id}")

    # Run pipeline in background thread
    import threading

    def run_pipeline():
        output_file = Path(__file__).parent.parent / ".tmp" / "ui_triggered_jobs.json"
        jobs_added = 0

        try:
            if request.run_full_pipeline:
                # Run full pipeline orchestrator (scrape → score → extract → generate → approve)
                logger.info("Running FULL pipeline with orchestrator...")
                cmd = [
                    sys.executable, "executions/upwork_pipeline_orchestrator.py",
                    "--source", request.source,
                    "--limit", str(request.limit),
                    "--min-score", str(request.min_score),
                    "--parallel", "2",
                    "-o", str(output_file.with_suffix('.result.json'))
                ]
                # Add keywords if provided
                if request.keywords:
                    cmd.extend(["--keywords", request.keywords])

                logger.info(f"Running command: {' '.join(cmd)}")

                # Run with longer timeout for full pipeline
                result = subprocess.run(
                    cmd,
                    cwd=str(Path(__file__).parent.parent),
                    capture_output=True,
                    text=True,
                    timeout=900  # 15 minute timeout for full pipeline
                )

                if result.returncode != 0:
                    logger.error(f"Pipeline orchestrator failed: {result.stderr}")
                    PIPELINE_STATUS["last_run_status"] = "error"
                    PIPELINE_STATUS["is_running"] = False
                    return

                logger.info(f"Pipeline output: {result.stdout[-1000:]}")

                # Parse results from orchestrator output
                result_file = output_file.with_suffix('.result.json')
                if result_file.exists():
                    with open(result_file) as f:
                        pipeline_result = json.load(f)
                    jobs_added = pipeline_result.get('jobs_processed', 0)
                    logger.info(f"Pipeline result: {pipeline_result.get('jobs_ingested', 0)} ingested, "
                              f"{pipeline_result.get('jobs_after_prefilter', 0)} after filter, "
                              f"{pipeline_result.get('jobs_sent_to_slack', 0)} sent to approval")

            elif request.source == "apify":
                # Run scrape-only mode (just import jobs to sheet)
                logger.info("Running SCRAPE ONLY mode...")
                cmd = [
                    sys.executable, "executions/upwork_apify_scraper.py",
                    "--limit", str(request.limit),
                    "-o", str(output_file)
                ]
                # Add optional filters (keywords passed as comma-separated for server-side Apify filtering)
                if request.keywords:
                    cmd.extend(["--keywords", request.keywords])
                if request.location:
                    # Location filter not supported by scraper yet, log it
                    logger.info(f"Location filter requested: {request.location} (not yet implemented in scraper)")

                logger.info(f"Running command: {' '.join(cmd)}")

                # Run synchronously and wait for completion
                result = subprocess.run(
                    cmd,
                    cwd=str(Path(__file__).parent.parent),
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minute timeout
                )

                if result.returncode != 0:
                    logger.error(f"Scraper failed: {result.stderr}")
                    PIPELINE_STATUS["last_run_status"] = "error"
                    PIPELINE_STATUS["is_running"] = False
                    return

                logger.info(f"Scraper output: {result.stdout[-500:]}")

                # Load scraped jobs and add to sheet
                if output_file.exists():
                    with open(output_file) as f:
                        jobs = json.load(f)
                    logger.info(f"Loaded {len(jobs)} jobs from scraper output")

                    # Add jobs to Google Sheet
                    jobs_added = add_jobs_to_sheet(jobs)
                    logger.info(f"Added {jobs_added} new jobs to sheet")
                else:
                    logger.warning(f"Output file not found: {output_file}")

            else:
                # Gmail source
                cmd = [
                    sys.executable, "executions/gmail_unified.py",
                    "--check-upwork-alerts"
                ]
                result = subprocess.run(
                    cmd,
                    cwd=str(Path(__file__).parent.parent),
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                if result.returncode != 0:
                    logger.error(f"Gmail check failed: {result.stderr}")

            PIPELINE_STATUS["last_run_status"] = "success"
            PIPELINE_STATUS["jobs_processed_today"] += jobs_added
            logger.info(f"Pipeline completed successfully. Jobs added: {jobs_added}")

        except subprocess.TimeoutExpired:
            logger.error("Pipeline timed out")
            PIPELINE_STATUS["last_run_status"] = "error"
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            PIPELINE_STATUS["last_run_status"] = "error"
        finally:
            PIPELINE_STATUS["is_running"] = False

    threading.Thread(target=run_pipeline, daemon=True).start()

    return {
        "success": True,
        "run_id": run_id,
        "source": request.source,
        "limit": request.limit,
        "keywords": request.keywords,
        "location": request.location
    }

@app.post("/api/admin/pipeline/import")
async def api_import_jobs(user: dict = Depends(get_current_user)):
    """Import jobs from the last scraper output file to the sheet."""
    output_file = Path(__file__).parent.parent / ".tmp" / "ui_triggered_jobs.json"

    if not output_file.exists():
        raise HTTPException(status_code=404, detail="No scraper output file found")

    try:
        with open(output_file) as f:
            jobs = json.load(f)

        jobs_added = add_jobs_to_sheet(jobs)

        return {
            "success": True,
            "jobs_in_file": len(jobs),
            "jobs_added": jobs_added,
            "message": f"Imported {jobs_added} new jobs (skipped {len(jobs) - jobs_added} duplicates)"
        }
    except Exception as e:
        logger.error(f"Import failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class ProcessJobsRequest(BaseModel):
    job_ids: List[str]  # List of job IDs to process
    min_score: int = 70

@app.post("/api/admin/pipeline/process")
async def api_process_jobs(
    request: ProcessJobsRequest,
    user: dict = Depends(get_current_user)
):
    """
    Process specific jobs through the remaining pipeline stages.
    Takes jobs that are already in the sheet and runs them through:
    scoring → extraction → deliverable generation → boost decision → approval
    """
    if PIPELINE_STATUS["is_running"]:
        raise HTTPException(status_code=409, detail="Pipeline is already running")

    if not request.job_ids:
        raise HTTPException(status_code=400, detail="No job IDs provided")

    run_id = f"process_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    PIPELINE_STATUS["is_running"] = True
    PIPELINE_STATUS["current_run_id"] = run_id
    PIPELINE_STATUS["last_run_time"] = datetime.now(timezone.utc).isoformat()
    PIPELINE_STATUS["last_run_status"] = "running"

    logger.info(f"Processing {len(request.job_ids)} jobs: {request.job_ids[:5]}...")

    import threading

    def process_jobs():
        try:
            # Get job details from sheet
            jobs_to_process = []
            client = get_sheets_client()
            if not client:
                logger.error("Could not get sheets client")
                PIPELINE_STATUS["last_run_status"] = "error"
                PIPELINE_STATUS["is_running"] = False
                return

            spreadsheet = client.open_by_key(UPWORK_PIPELINE_SHEET_ID)
            worksheet = spreadsheet.get_worksheet(0)
            all_data = worksheet.get_all_records()

            for row in all_data:
                if str(row.get('job_id', '')) in request.job_ids:
                    jobs_to_process.append({
                        'job_id': str(row.get('job_id', '')),
                        'url': row.get('url', ''),
                        'title': row.get('title', ''),
                        'description': row.get('description', ''),
                        'source': row.get('source', 'manual'),
                    })

            if not jobs_to_process:
                logger.warning(f"No matching jobs found for IDs: {request.job_ids}")
                PIPELINE_STATUS["last_run_status"] = "success"
                PIPELINE_STATUS["is_running"] = False
                return

            logger.info(f"Found {len(jobs_to_process)} jobs to process")

            # Save jobs to temp file for orchestrator
            jobs_file = Path(__file__).parent.parent / ".tmp" / "jobs_to_process.json"
            jobs_file.parent.mkdir(exist_ok=True)
            with open(jobs_file, 'w') as f:
                json.dump(jobs_to_process, f)

            # Run orchestrator with manual source
            output_file = Path(__file__).parent.parent / ".tmp" / "process_result.json"
            cmd = [
                sys.executable, "executions/upwork_pipeline_orchestrator.py",
                "--source", "manual",
                "--jobs", str(jobs_file),
                "--min-score", str(request.min_score),
                "--parallel", "2",
                "-o", str(output_file)
            ]

            logger.info(f"Running: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                cwd=str(Path(__file__).parent.parent),
                capture_output=True,
                text=True,
                timeout=900
            )

            if result.returncode != 0:
                logger.error(f"Processing failed: {result.stderr}")
                PIPELINE_STATUS["last_run_status"] = "error"
            else:
                logger.info(f"Processing output: {result.stdout[-1000:]}")
                PIPELINE_STATUS["last_run_status"] = "success"

        except subprocess.TimeoutExpired:
            logger.error("Processing timed out")
            PIPELINE_STATUS["last_run_status"] = "error"
        except Exception as e:
            logger.error(f"Processing error: {e}")
            PIPELINE_STATUS["last_run_status"] = "error"
        finally:
            PIPELINE_STATUS["is_running"] = False

    threading.Thread(target=process_jobs, daemon=True).start()

    return {
        "success": True,
        "run_id": run_id,
        "job_count": len(request.job_ids),
        "message": f"Processing {len(request.job_ids)} jobs in background"
    }

@app.get("/api/admin/pipeline/status")
async def api_get_pipeline_status(user: dict = Depends(get_current_user)):
    """Get pipeline status."""
    reset_daily_counter()
    return PIPELINE_STATUS

@app.get("/api/admin/logs")
async def api_get_logs(
    level: Optional[str] = None,
    limit: int = 100,
    user: dict = Depends(get_current_user)
):
    """Get execution logs."""
    logs = LOG_BUFFER.copy()

    # Filter by level
    if level:
        logs = [l for l in logs if l.get("level") == level.upper()]

    # Sort by timestamp (newest first) and limit
    logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    logs = logs[:limit]

    return {"logs": logs, "total": len(LOG_BUFFER)}

@app.get("/api/admin/health")
async def api_get_health(user: dict = Depends(get_current_user)):
    """Get system health status."""
    services = {
        "sheets": False,
        "slack": False,
        "openai": False
    }

    # Check Google Sheets
    if UPWORK_PIPELINE_SHEET_ID and get_sheets_client():
        services["sheets"] = True

    # Check Slack (just check token exists)
    if os.getenv("SLACK_BOT_TOKEN"):
        services["slack"] = True

    # Check OpenAI (just check key exists)
    if os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"):
        services["openai"] = True

    # Overall status
    all_healthy = all(services.values())
    some_healthy = any(services.values())

    status = "healthy" if all_healthy else ("degraded" if some_healthy else "unhealthy")

    return {
        "status": status,
        "services": services,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# ============================================================================
# TOOL IMPLEMENTATIONS (Original webhook functionality)
# ============================================================================

def send_email_impl(to: str, subject: str, body: str) -> dict:
    """Send email via Gmail API."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
    from email.mime.text import MIMEText
    import base64

    # Load token
    token_path = Path("config/token.json")
    if not token_path.exists():
        return {"error": "token.json not found"}

    token_data = json.loads(token_path.read_text())

    creds = Credentials(
        token=token_data["token"],
        refresh_token=token_data["refresh_token"],
        token_uri=token_data["token_uri"],
        client_id=token_data["client_id"],
        client_secret=token_data["client_secret"],
        scopes=token_data["scopes"]
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    service = build("gmail", "v1", credentials=creds)
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    result = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    logger.info(f"Email sent to {to} | ID: {result['id']}")
    return {"status": "sent", "message_id": result["id"]}


def read_sheet_impl(spreadsheet_id: str, range: str) -> dict:
    """Read from Google Sheet."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request

    token_path = Path("config/token.json")
    if not token_path.exists():
        return {"error": "token.json not found"}

    token_data = json.loads(token_path.read_text())

    creds = Credentials(
        token=token_data["token"],
        refresh_token=token_data["refresh_token"],
        token_uri=token_data["token_uri"],
        client_id=token_data["client_id"],
        client_secret=token_data["client_secret"],
        scopes=token_data["scopes"]
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    service = build("sheets", "v4", credentials=creds)
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range
    ).execute()

    values = result.get("values", [])
    logger.info(f"Read {len(values)} rows from sheet")
    return {"rows": len(values), "values": values}


def update_sheet_impl(spreadsheet_id: str, range: str, values: list) -> dict:
    """Update Google Sheet."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request

    token_path = Path("config/token.json")
    if not token_path.exists():
        return {"error": "token.json not found"}

    token_data = json.loads(token_path.read_text())

    creds = Credentials(
        token=token_data["token"],
        refresh_token=token_data["refresh_token"],
        token_uri=token_data["token_uri"],
        client_id=token_data["client_id"],
        client_secret=token_data["client_secret"],
        scopes=token_data["scopes"]
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    service = build("sheets", "v4", credentials=creds)
    result = service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=range,
        valueInputOption="USER_ENTERED",
        body={"values": values}
    ).execute()

    logger.info(f"Updated {result.get('updatedCells', 0)} cells")
    return {"updated_cells": result.get("updatedCells", 0)}


# Map tool names to implementations
TOOL_IMPLEMENTATIONS = {
    "send_email": lambda **kwargs: send_email_impl(**kwargs),
    "read_sheet": lambda **kwargs: read_sheet_impl(**kwargs),
    "update_sheet": lambda **kwargs: update_sheet_impl(**kwargs),
}

# Tool definitions for Claude
ALL_TOOLS = {
    "send_email": {
        "name": "send_email",
        "description": "Send an email via Gmail.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject line"},
                "body": {"type": "string", "description": "Email body content"}
            },
            "required": ["to", "subject", "body"]
        }
    },
    "read_sheet": {
        "name": "read_sheet",
        "description": "Read data from a Google Sheet.",
        "input_schema": {
            "type": "object",
            "properties": {
                "spreadsheet_id": {"type": "string", "description": "The Google Sheet ID"},
                "range": {"type": "string", "description": "A1 notation range"}
            },
            "required": ["spreadsheet_id", "range"]
        }
    },
    "update_sheet": {
        "name": "update_sheet",
        "description": "Update cells in a Google Sheet.",
        "input_schema": {
            "type": "object",
            "properties": {
                "spreadsheet_id": {"type": "string", "description": "The Google Sheet ID"},
                "range": {"type": "string", "description": "A1 notation range"},
                "values": {"type": "array", "description": "2D array of values"}
            },
            "required": ["spreadsheet_id", "range", "values"]
        }
    },
}

# ============================================================================
# SCRIPT EXECUTION
# ============================================================================

SCRIPT_HANDLERS = {}

def run_upwork_scrape_apply(input_data: dict) -> dict:
    """Run the Upwork scrape and apply pipeline."""
    limit = input_data.get("limit", 50)
    days = input_data.get("days", 1)
    workers = input_data.get("workers", 5)
    keywords = input_data.get("keywords", None)

    results = {"steps": [], "errors": []}

    # Step 1: Scrape jobs
    logger.info(f"Scraping Upwork jobs (limit={limit}, days={days})")
    scrape_cmd = [
        sys.executable, "execution/upwork_apify_scraper.py",
        "--limit", str(limit),
        "--days", str(days),
        "-o", ".tmp/upwork_jobs_batch.json"
    ]
    if input_data.get("verified_payment"):
        scrape_cmd.append("--verified-payment")

    try:
        scrape_result = subprocess.run(
            scrape_cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(Path(__file__).parent.parent)
        )
        results["steps"].append({
            "step": "scrape",
            "returncode": scrape_result.returncode,
            "stdout": scrape_result.stdout[-2000:] if scrape_result.stdout else "",
            "stderr": scrape_result.stderr[-1000:] if scrape_result.stderr else ""
        })
        if scrape_result.returncode != 0:
            results["errors"].append(f"Scrape failed: {scrape_result.stderr}")
            return results
    except subprocess.TimeoutExpired:
        results["errors"].append("Scrape timed out after 5 minutes")
        return results
    except Exception as e:
        results["errors"].append(f"Scrape error: {str(e)}")
        return results

    # Step 2: Generate proposals
    logger.info(f"Generating proposals (workers={workers})")
    proposal_cmd = [
        sys.executable, "execution/upwork_proposal_generator.py",
        "--input", ".tmp/upwork_jobs_batch.json",
        "--workers", str(workers),
        "--output", ".tmp/upwork_jobs_with_proposals.json"
    ]
    if keywords:
        proposal_cmd.extend(["--filter-keywords", keywords])

    try:
        proposal_result = subprocess.run(
            proposal_cmd,
            capture_output=True,
            text=True,
            timeout=1800,  # 30 min for proposal generation
            cwd=str(Path(__file__).parent.parent)
        )
        results["steps"].append({
            "step": "proposals",
            "returncode": proposal_result.returncode,
            "stdout": proposal_result.stdout[-2000:] if proposal_result.stdout else "",
            "stderr": proposal_result.stderr[-1000:] if proposal_result.stderr else ""
        })
        if proposal_result.returncode != 0:
            results["errors"].append(f"Proposal generation failed: {proposal_result.stderr}")
    except subprocess.TimeoutExpired:
        results["errors"].append("Proposal generation timed out after 30 minutes")
    except Exception as e:
        results["errors"].append(f"Proposal error: {str(e)}")

    # Try to load output
    output_path = Path(__file__).parent.parent / ".tmp/upwork_jobs_with_proposals.json"
    if output_path.exists():
        try:
            with open(output_path) as f:
                output_data = json.load(f)
            results["jobs_processed"] = len(output_data) if isinstance(output_data, list) else output_data.get("count", 0)
        except Exception:
            pass

    # Extract Google Sheet URL from proposal stdout
    proposal_stdout = results["steps"][-1]["stdout"] if results["steps"] else ""
    sheet_match = re.search(r'https://docs\.google\.com/spreadsheets/d/[a-zA-Z0-9_-]+', proposal_stdout)
    if sheet_match:
        results["sheet_url"] = sheet_match.group(0)

    results["status"] = "success" if not results["errors"] else "partial" if results.get("jobs_processed") else "failed"

    # Clean response - remove verbose stdout/stderr from steps
    results["steps"] = [{"step": s["step"], "status": "ok" if s["returncode"] == 0 else "failed"} for s in results["steps"]]

    return results


SCRIPT_HANDLERS["upwork_scrape_apply"] = run_upwork_scrape_apply


def run_script(script_name: str, input_data: dict) -> dict:
    """Run a script by name with input data."""
    if script_name in SCRIPT_HANDLERS:
        return SCRIPT_HANDLERS[script_name](input_data)

    # Generic script runner for other scripts
    script_path = Path(__file__).parent / f"{script_name}.py"
    if not script_path.exists():
        return {"error": f"Script not found: {script_name}.py"}

    # Write input to temp file
    input_file = Path(__file__).parent.parent / ".tmp" / f"{script_name}_input.json"
    input_file.parent.mkdir(exist_ok=True)
    with open(input_file, "w") as f:
        json.dump(input_data, f)

    try:
        result = subprocess.run(
            [sys.executable, str(script_path), "--input", str(input_file)],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(Path(__file__).parent.parent)
        )
        return {
            "status": "success" if result.returncode == 0 else "failed",
            "returncode": result.returncode,
            "stdout": result.stdout[-3000:] if result.stdout else "",
            "stderr": result.stderr[-1000:] if result.stderr else ""
        }
    except subprocess.TimeoutExpired:
        return {"error": "Script timed out after 10 minutes"}
    except Exception as e:
        return {"error": str(e)}


# ============================================================================
# CORE FUNCTIONS
# ============================================================================

def load_webhook_config() -> dict:
    """Load webhook configuration."""
    config_path = Path("execution/webhooks.json")
    if not config_path.exists():
        return {"webhooks": {}}
    return json.loads(config_path.read_text())


def load_directive(directive_name: str) -> str:
    """Load a directive file."""
    directive_path = Path(f"directives/{directive_name}.md")
    if not directive_path.exists():
        raise FileNotFoundError(f"Directive not found: {directive_name}")
    return directive_path.read_text()


def run_directive(
    slug: str,
    directive_content: str,
    input_data: dict,
    allowed_tools: list,
    max_turns: int = 15
) -> dict:
    """Execute a directive with scoped tools."""
    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # Build prompt
    prompt = f"""You are executing a specific directive. Follow it precisely.

## DIRECTIVE
{directive_content}

## INPUT DATA
{json.dumps(input_data, indent=2) if input_data else "No input data provided."}

## INSTRUCTIONS
1. Read and understand the directive above
2. Use the available tools to accomplish the task
3. Report your results clearly

Execute the directive now."""

    # Filter tools
    tools = [ALL_TOOLS[t] for t in allowed_tools if t in ALL_TOOLS]

    messages = [{"role": "user", "content": prompt}]
    conversation_log = []
    thinking_log = []
    total_input_tokens = 0
    total_output_tokens = 0
    turn_count = 0

    logger.info(f"Executing directive: {slug}")

    response = client.messages.create(
        model="claude-opus-4-5-20251101",
        max_tokens=16000,
        tools=tools,
        messages=messages,
        thinking={"type": "enabled", "budget_tokens": 32000}
    )

    total_input_tokens += response.usage.input_tokens
    total_output_tokens += response.usage.output_tokens

    while response.stop_reason == "tool_use" and turn_count < max_turns:
        turn_count += 1

        # Process thinking
        for block in response.content:
            if block.type == "thinking":
                thinking_log.append({"turn": turn_count, "thinking": block.thinking})
                logger.info(f"Turn {turn_count} thinking: {block.thinking[:100]}...")

        # Find tool call
        tool_use = next((b for b in response.content if b.type == "tool_use"), None)
        if not tool_use:
            break

        # Security check
        if tool_use.name not in allowed_tools:
            tool_result = json.dumps({"error": f"Tool '{tool_use.name}' not permitted"})
            is_error = True
        else:
            logger.info(f"Turn {turn_count} - {tool_use.name}: {tool_use.input}")
            conversation_log.append({"turn": turn_count, "tool": tool_use.name, "input": tool_use.input})

            # Execute tool
            is_error = False
            try:
                impl = TOOL_IMPLEMENTATIONS.get(tool_use.name)
                if impl:
                    result = impl(**tool_use.input)
                    tool_result = json.dumps(result)
                else:
                    tool_result = json.dumps({"error": f"No implementation for {tool_use.name}"})
                    is_error = True
            except Exception as e:
                logger.error(f"Tool error: {e}")
                tool_result = json.dumps({"error": str(e)})
                is_error = True

            conversation_log[-1]["result"] = tool_result
            logger.info(f"{'Error' if is_error else 'Success'}: {tool_result[:200]}")

        # Continue conversation
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": tool_use.id, "content": tool_result}
        ]})

        response = client.messages.create(
            model="claude-opus-4-5-20251101",
            max_tokens=16000,
            tools=tools,
            messages=messages,
            thinking={"type": "enabled", "budget_tokens": 32000}
        )

        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

    # Extract final response
    final_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            final_text += block.text
        if block.type == "thinking":
            thinking_log.append({"turn": "final", "thinking": block.thinking})

    usage = {
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "turns": turn_count
    }

    logger.info(f"Complete - {usage['turns']} turns, {usage['input_tokens']} -> {usage['output_tokens']} tokens")

    return {
        "response": final_text,
        "thinking": thinking_log,
        "conversation": conversation_log,
        "usage": usage
    }


# ============================================================================
# ORIGINAL ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """Server info."""
    return {
        "service": "Claude Orchestrator (Local)",
        "status": "running",
        "endpoints": {
            "webhook": "POST /webhook/{slug}",
            "list": "GET /webhooks",
            "api": "/api/*"
        }
    }


@app.get("/webhooks")
async def list_webhooks():
    """List available webhooks."""
    config = load_webhook_config()
    webhooks = config.get("webhooks", {})

    return {
        "webhooks": {
            slug: {
                "directive": cfg.get("directive"),
                "script": cfg.get("script"),
                "description": cfg.get("description", ""),
                "tools": cfg.get("tools", [])
            }
            for slug, cfg in webhooks.items()
        }
    }


@app.post("/webhook/{slug}")
async def execute_webhook(slug: str, payload: Optional[dict] = None):
    """Execute a directive or script by slug."""
    payload = payload or {}
    input_data = payload.get("data", payload)
    max_turns = payload.get("max_turns", 15)

    # Load config
    config = load_webhook_config()
    webhooks = config.get("webhooks", {})

    if slug not in webhooks:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown webhook slug: {slug}"
        )

    webhook_config = webhooks[slug]
    directive_name = webhook_config.get("directive")
    script_name = webhook_config.get("script")

    # Handle script-type webhooks
    if script_name:
        logger.info(f"Running script: {script_name}")
        try:
            result = run_script(script_name, input_data)
            return {
                "status": result.get("status", "completed"),
                "slug": slug,
                "mode": "local",
                "type": "script",
                "script": script_name,
                "result": result,
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Script error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Handle directive-type webhooks
    if not directive_name:
        raise HTTPException(
            status_code=400,
            detail="Webhook must have either 'directive' or 'script' defined"
        )

    allowed_tools = webhook_config.get("tools", ["send_email"])

    try:
        directive_content = load_directive(directive_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        result = run_directive(
            slug=slug,
            directive_content=directive_content,
            input_data=input_data,
            allowed_tools=allowed_tools,
            max_turns=max_turns
        )

        return {
            "status": "success",
            "slug": slug,
            "mode": "local",
            "type": "directive",
            "directive": directive_name,
            "response": result["response"],
            "thinking": result["thinking"],
            "conversation": result["conversation"],
            "usage": result["usage"],
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# STATIC FILE SERVING (for production frontend)
# ============================================================================

# Serve frontend static files if they exist
frontend_dist = Path(__file__).parent.parent / "static" / "frontend"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    @app.get("/{path:path}")
    async def serve_spa(path: str):
        """Serve SPA for all unmatched routes."""
        # Don't catch API routes
        if path.startswith("api/") or path.startswith("webhook"):
            raise HTTPException(status_code=404)

        index_file = frontend_dist / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        raise HTTPException(status_code=404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
