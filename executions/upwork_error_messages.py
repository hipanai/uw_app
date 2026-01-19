#!/usr/bin/env python3
"""
Upwork Error Messages

Provides user-friendly error messages with clear explanations and suggested next steps.
This module transforms technical errors into actionable, understandable messages.

Feature #87: User-friendly error messages

Usage:
    from upwork_error_messages import format_error, ErrorCode

    # Format an error with context
    message = format_error(ErrorCode.API_KEY_MISSING, context={"service": "Anthropic"})

    # Format an exception
    message = format_error_from_exception(exception, operation="scoring jobs")
"""

import os
import re
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum, auto

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if os.getenv("DEBUG") else logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ErrorCode(Enum):
    """Categorized error codes for the Upwork pipeline."""
    # Configuration errors (1xx)
    API_KEY_MISSING = auto()
    API_KEY_INVALID = auto()
    ENV_VAR_MISSING = auto()
    CONFIG_FILE_MISSING = auto()
    TOKEN_EXPIRED = auto()
    TOKEN_REFRESH_FAILED = auto()

    # Network/API errors (2xx)
    NETWORK_ERROR = auto()
    API_RATE_LIMITED = auto()
    API_TIMEOUT = auto()
    API_SERVER_ERROR = auto()
    API_INVALID_RESPONSE = auto()
    SSL_ERROR = auto()

    # Google services errors (3xx)
    GOOGLE_AUTH_FAILED = auto()
    GOOGLE_SHEET_NOT_FOUND = auto()
    GOOGLE_SHEET_PERMISSION_DENIED = auto()
    GOOGLE_DOC_CREATE_FAILED = auto()
    GOOGLE_DRIVE_UPLOAD_FAILED = auto()

    # Slack errors (4xx)
    SLACK_AUTH_FAILED = auto()
    SLACK_CHANNEL_NOT_FOUND = auto()
    SLACK_MESSAGE_FAILED = auto()
    SLACK_SIGNATURE_INVALID = auto()

    # HeyGen errors (5xx)
    HEYGEN_AUTH_FAILED = auto()
    HEYGEN_VIDEO_FAILED = auto()
    HEYGEN_TIMEOUT = auto()

    # Data errors (6xx)
    JOB_NOT_FOUND = auto()
    INVALID_JOB_DATA = auto()
    PARSE_ERROR = auto()
    ATTACHMENT_DOWNLOAD_FAILED = auto()

    # Pipeline errors (7xx)
    PIPELINE_STAGE_FAILED = auto()
    SCRAPER_FAILED = auto()
    PREFILTER_FAILED = auto()
    EXTRACTION_FAILED = auto()
    DELIVERABLE_GENERATION_FAILED = auto()
    SUBMISSION_FAILED = auto()

    # Browser/Playwright errors (8xx)
    BROWSER_LAUNCH_FAILED = auto()
    PAGE_LOAD_FAILED = auto()
    ELEMENT_NOT_FOUND = auto()
    LOGIN_REQUIRED = auto()

    # Generic errors (9xx)
    UNKNOWN_ERROR = auto()
    OPERATION_CANCELLED = auto()
    PERMISSION_DENIED = auto()


@dataclass
class UserFriendlyError:
    """A user-friendly error with explanation and suggested actions."""
    code: ErrorCode
    title: str
    message: str
    next_steps: List[str]
    technical_details: Optional[str] = None
    severity: str = "error"  # "error", "warning", "info"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code.name,
            "title": self.title,
            "message": self.message,
            "next_steps": self.next_steps,
            "technical_details": self.technical_details,
            "severity": self.severity
        }

    def format_for_display(self, include_technical: bool = False) -> str:
        """Format error for display to user."""
        lines = [
            f"Error: {self.title}",
            "",
            self.message,
            "",
            "What to do next:"
        ]
        for i, step in enumerate(self.next_steps, 1):
            lines.append(f"  {i}. {step}")

        if include_technical and self.technical_details:
            lines.extend(["", f"Technical details: {self.technical_details}"])

        return "\n".join(lines)

    def format_for_log(self) -> str:
        """Format error for logging."""
        steps = " | ".join(self.next_steps)
        return f"[{self.code.name}] {self.title}: {self.message} (Next steps: {steps})"


# Error message templates with user-friendly explanations
ERROR_TEMPLATES: Dict[ErrorCode, Dict[str, Any]] = {
    # Configuration errors
    ErrorCode.API_KEY_MISSING: {
        "title": "API Key Not Configured",
        "message": "The {service} API key is not set. This key is required to use {service} services.",
        "next_steps": [
            "Add {env_var} to your .env file",
            "Get your API key from {provider_url}",
            "Restart the application after adding the key"
        ],
        "severity": "error"
    },
    ErrorCode.API_KEY_INVALID: {
        "title": "Invalid API Key",
        "message": "The {service} API key appears to be invalid or has been revoked.",
        "next_steps": [
            "Check that {env_var} in .env is correct",
            "Generate a new API key at {provider_url}",
            "Ensure there are no extra spaces or quotes around the key"
        ],
        "severity": "error"
    },
    ErrorCode.ENV_VAR_MISSING: {
        "title": "Required Configuration Missing",
        "message": "The environment variable {env_var} is required but not set.",
        "next_steps": [
            "Add {env_var} to your .env file",
            "Check .env.example for the expected format",
            "Restart the application after adding the variable"
        ],
        "severity": "error"
    },
    ErrorCode.CONFIG_FILE_MISSING: {
        "title": "Configuration File Not Found",
        "message": "The configuration file {file_path} was not found.",
        "next_steps": [
            "Create the missing file at {file_path}",
            "Copy from template if available (e.g., {file_path}.example)",
            "Check that the file path is correct"
        ],
        "severity": "error"
    },
    ErrorCode.TOKEN_EXPIRED: {
        "title": "Authentication Token Expired",
        "message": "Your {service} authentication token has expired.",
        "next_steps": [
            "Run the authentication flow again to refresh your token",
            "Delete config/token.json and re-authenticate",
            "Check if your refresh token is still valid"
        ],
        "severity": "error"
    },
    ErrorCode.TOKEN_REFRESH_FAILED: {
        "title": "Token Refresh Failed",
        "message": "Unable to refresh the {service} authentication token.",
        "next_steps": [
            "Delete the token file and re-authenticate from scratch",
            "Check your internet connection",
            "Verify your credentials haven't been revoked"
        ],
        "severity": "error"
    },

    # Network/API errors
    ErrorCode.NETWORK_ERROR: {
        "title": "Network Connection Failed",
        "message": "Could not connect to {service}. There may be a network issue.",
        "next_steps": [
            "Check your internet connection",
            "Verify {service} is not experiencing an outage",
            "Try again in a few moments",
            "Check if a firewall is blocking the connection"
        ],
        "severity": "error"
    },
    ErrorCode.API_RATE_LIMITED: {
        "title": "Rate Limit Reached",
        "message": "You've made too many requests to {service}. The service has temporarily limited your access.",
        "next_steps": [
            "Wait {wait_time} before trying again",
            "Reduce the number of parallel requests",
            "Consider upgrading your API plan for higher limits"
        ],
        "severity": "warning"
    },
    ErrorCode.API_TIMEOUT: {
        "title": "Request Timed Out",
        "message": "The request to {service} took too long to complete.",
        "next_steps": [
            "Try the operation again",
            "Check if {service} is experiencing slow response times",
            "Reduce the size of the request if possible"
        ],
        "severity": "warning"
    },
    ErrorCode.API_SERVER_ERROR: {
        "title": "Service Unavailable",
        "message": "{service} is experiencing technical difficulties (HTTP {status_code}).",
        "next_steps": [
            "Wait a few minutes and try again",
            "Check {service} status page for outage information",
            "Contact support if the issue persists"
        ],
        "severity": "error"
    },
    ErrorCode.API_INVALID_RESPONSE: {
        "title": "Unexpected Response",
        "message": "Received an unexpected response from {service}.",
        "next_steps": [
            "Try the operation again",
            "Check if the service API has been updated",
            "Review the logs for more details"
        ],
        "severity": "error"
    },
    ErrorCode.SSL_ERROR: {
        "title": "Secure Connection Failed",
        "message": "Could not establish a secure connection to {service}.",
        "next_steps": [
            "Check your system date and time are correct",
            "Update your SSL certificates",
            "Try on a different network"
        ],
        "severity": "error"
    },

    # Google services errors
    ErrorCode.GOOGLE_AUTH_FAILED: {
        "title": "Google Authentication Failed",
        "message": "Could not authenticate with Google services.",
        "next_steps": [
            "Run the Google OAuth flow again",
            "Check that config/credentials.json is valid",
            "Delete config/token.json and re-authenticate",
            "Verify the required scopes are enabled in Google Cloud Console"
        ],
        "severity": "error"
    },
    ErrorCode.GOOGLE_SHEET_NOT_FOUND: {
        "title": "Google Sheet Not Found",
        "message": "The Google Sheet '{sheet_name}' could not be found.",
        "next_steps": [
            "Verify the sheet ID in UPWORK_PIPELINE_SHEET_ID is correct",
            "Check that the sheet hasn't been deleted or moved",
            "Ensure your Google account has access to the sheet"
        ],
        "severity": "error"
    },
    ErrorCode.GOOGLE_SHEET_PERMISSION_DENIED: {
        "title": "Sheet Access Denied",
        "message": "You don't have permission to access the Google Sheet.",
        "next_steps": [
            "Request edit access from the sheet owner",
            "Verify you're using the correct Google account",
            "Check that the OAuth token has spreadsheet scopes"
        ],
        "severity": "error"
    },
    ErrorCode.GOOGLE_DOC_CREATE_FAILED: {
        "title": "Document Creation Failed",
        "message": "Could not create a Google Doc for the proposal.",
        "next_steps": [
            "Check your Google Drive storage quota",
            "Verify OAuth token has document creation permissions",
            "Try again - this may be a temporary issue"
        ],
        "severity": "error"
    },
    ErrorCode.GOOGLE_DRIVE_UPLOAD_FAILED: {
        "title": "File Upload Failed",
        "message": "Could not upload the file to Google Drive.",
        "next_steps": [
            "Check your Google Drive storage quota",
            "Verify the file isn't too large (max 5TB)",
            "Try again - this may be a temporary issue"
        ],
        "severity": "error"
    },

    # Slack errors
    ErrorCode.SLACK_AUTH_FAILED: {
        "title": "Slack Authentication Failed",
        "message": "Could not authenticate with Slack.",
        "next_steps": [
            "Verify SLACK_BOT_TOKEN is set correctly in .env",
            "Reinstall the Slack app to get a new token",
            "Check that the bot has required permissions"
        ],
        "severity": "error"
    },
    ErrorCode.SLACK_CHANNEL_NOT_FOUND: {
        "title": "Slack Channel Not Found",
        "message": "The Slack channel '{channel}' could not be found.",
        "next_steps": [
            "Verify SLACK_APPROVAL_CHANNEL in .env is the channel ID (not name)",
            "Ensure the bot has been added to the channel",
            "Check that the channel hasn't been archived or deleted"
        ],
        "severity": "error"
    },
    ErrorCode.SLACK_MESSAGE_FAILED: {
        "title": "Slack Message Failed",
        "message": "Could not send message to Slack.",
        "next_steps": [
            "Verify the bot is a member of the target channel",
            "Check that the message content is valid",
            "Review Slack API rate limits"
        ],
        "severity": "error"
    },
    ErrorCode.SLACK_SIGNATURE_INVALID: {
        "title": "Invalid Request Signature",
        "message": "The Slack request signature verification failed.",
        "next_steps": [
            "This may indicate a security issue - verify the request source",
            "Check that SLACK_SIGNING_SECRET is correct",
            "Ensure your server clock is accurate (within 5 minutes)"
        ],
        "severity": "error"
    },

    # HeyGen errors
    ErrorCode.HEYGEN_AUTH_FAILED: {
        "title": "HeyGen Authentication Failed",
        "message": "Could not authenticate with HeyGen.",
        "next_steps": [
            "Verify HEYGEN_API_KEY is set correctly in .env",
            "Check your HeyGen subscription status",
            "Generate a new API key from HeyGen dashboard"
        ],
        "severity": "error"
    },
    ErrorCode.HEYGEN_VIDEO_FAILED: {
        "title": "Video Generation Failed",
        "message": "HeyGen could not generate the video.",
        "next_steps": [
            "Check your HeyGen credits/quota",
            "Verify the avatar ID is valid",
            "Try with a shorter script",
            "Check HeyGen status page for outages"
        ],
        "severity": "error"
    },
    ErrorCode.HEYGEN_TIMEOUT: {
        "title": "Video Generation Timed Out",
        "message": "The HeyGen video took too long to generate.",
        "next_steps": [
            "Check HeyGen dashboard for video status",
            "The video may still be processing - check back later",
            "Try with a shorter script for faster generation"
        ],
        "severity": "warning"
    },

    # Data errors
    ErrorCode.JOB_NOT_FOUND: {
        "title": "Job Not Found",
        "message": "The job '{job_id}' could not be found.",
        "next_steps": [
            "Verify the job ID is correct",
            "The job may have been removed from Upwork",
            "Check the Google Sheet for the job record"
        ],
        "severity": "error"
    },
    ErrorCode.INVALID_JOB_DATA: {
        "title": "Invalid Job Data",
        "message": "The job data is missing required fields or has invalid values.",
        "next_steps": [
            "Check that job_id and url are provided",
            "Verify the data format matches expected structure",
            "Re-scrape the job to get fresh data"
        ],
        "severity": "error"
    },
    ErrorCode.PARSE_ERROR: {
        "title": "Data Parse Error",
        "message": "Could not parse the {data_type} data.",
        "next_steps": [
            "Check that the data format is correct (JSON expected)",
            "Look for syntax errors in the data",
            "Try with a simpler data set"
        ],
        "severity": "error"
    },
    ErrorCode.ATTACHMENT_DOWNLOAD_FAILED: {
        "title": "Attachment Download Failed",
        "message": "Could not download the job attachment '{filename}'.",
        "next_steps": [
            "The attachment may require Upwork login",
            "Check if the attachment still exists",
            "Try manual download and provide the file path"
        ],
        "severity": "warning"
    },

    # Pipeline errors
    ErrorCode.PIPELINE_STAGE_FAILED: {
        "title": "Pipeline Stage Failed",
        "message": "The {stage} stage failed for job '{job_id}'.",
        "next_steps": [
            "Check the error log for specific failure details",
            "Retry the pipeline from the failed stage",
            "The job will be marked with error status in the sheet"
        ],
        "severity": "error"
    },
    ErrorCode.SCRAPER_FAILED: {
        "title": "Job Scraping Failed",
        "message": "Could not scrape jobs from {source}.",
        "next_steps": [
            "Check your Apify API credentials",
            "Verify the scraper actor is running",
            "Check Apify dashboard for actor logs"
        ],
        "severity": "error"
    },
    ErrorCode.PREFILTER_FAILED: {
        "title": "Pre-filter Scoring Failed",
        "message": "Could not score the job for relevance.",
        "next_steps": [
            "Check your Anthropic API key",
            "The job will be assigned a default score of 0",
            "Review the job manually if needed"
        ],
        "severity": "warning"
    },
    ErrorCode.EXTRACTION_FAILED: {
        "title": "Job Extraction Failed",
        "message": "Could not extract detailed information from the job posting.",
        "next_steps": [
            "The job URL may be invalid or expired",
            "Upwork may have changed their page structure",
            "Try extracting the job manually"
        ],
        "severity": "warning"
    },
    ErrorCode.DELIVERABLE_GENERATION_FAILED: {
        "title": "Deliverable Generation Failed",
        "message": "Could not generate {deliverable_type} for the job.",
        "next_steps": [
            "Check the relevant API credentials (Anthropic, Google, HeyGen)",
            "Review the job data for completeness",
            "Try generating individual deliverables separately"
        ],
        "severity": "error"
    },
    ErrorCode.SUBMISSION_FAILED: {
        "title": "Application Submission Failed",
        "message": "Could not submit the application to Upwork.",
        "next_steps": [
            "Check your Upwork session is still active",
            "Verify you haven't exceeded daily application limits",
            "The job may have been filled or removed",
            "Try submitting manually"
        ],
        "severity": "error"
    },

    # Browser/Playwright errors
    ErrorCode.BROWSER_LAUNCH_FAILED: {
        "title": "Browser Launch Failed",
        "message": "Could not start the browser for web automation.",
        "next_steps": [
            "Ensure Playwright browsers are installed (playwright install)",
            "Check system resources (memory, disk space)",
            "Try running with --headed flag for debugging"
        ],
        "severity": "error"
    },
    ErrorCode.PAGE_LOAD_FAILED: {
        "title": "Page Load Failed",
        "message": "Could not load the page at {url}.",
        "next_steps": [
            "Check your internet connection",
            "The page may be temporarily unavailable",
            "Try increasing the timeout setting"
        ],
        "severity": "error"
    },
    ErrorCode.ELEMENT_NOT_FOUND: {
        "title": "Page Element Not Found",
        "message": "Could not find the expected element on the page.",
        "next_steps": [
            "The page structure may have changed",
            "Try refreshing and retrying",
            "Check if you're logged in to Upwork"
        ],
        "severity": "error"
    },
    ErrorCode.LOGIN_REQUIRED: {
        "title": "Login Required",
        "message": "You need to be logged in to Upwork to perform this action.",
        "next_steps": [
            "Run the browser with your persistent profile",
            "Log in to Upwork manually in the profile",
            "Check that your session hasn't expired"
        ],
        "severity": "error"
    },

    # Generic errors
    ErrorCode.UNKNOWN_ERROR: {
        "title": "Unexpected Error",
        "message": "An unexpected error occurred during {operation}.",
        "next_steps": [
            "Check the error log for more details",
            "Try the operation again",
            "Contact support if the issue persists"
        ],
        "severity": "error"
    },
    ErrorCode.OPERATION_CANCELLED: {
        "title": "Operation Cancelled",
        "message": "The operation was cancelled.",
        "next_steps": [
            "Restart the operation if needed",
            "Check for partial results that may need cleanup"
        ],
        "severity": "info"
    },
    ErrorCode.PERMISSION_DENIED: {
        "title": "Permission Denied",
        "message": "You don't have permission to {operation}.",
        "next_steps": [
            "Check your account permissions",
            "Verify you're using the correct credentials",
            "Contact the administrator for access"
        ],
        "severity": "error"
    },
}

# Default context values for template substitution
DEFAULT_CONTEXT: Dict[str, str] = {
    "service": "the service",
    "env_var": "the environment variable",
    "provider_url": "the provider's website",
    "file_path": "the file",
    "sheet_name": "the sheet",
    "channel": "the channel",
    "job_id": "the job",
    "stage": "the stage",
    "source": "the source",
    "deliverable_type": "deliverables",
    "data_type": "the data",
    "filename": "the file",
    "url": "the URL",
    "operation": "the operation",
    "wait_time": "a few minutes",
    "status_code": "5xx",
}


def format_error(
    code: ErrorCode,
    context: Optional[Dict[str, Any]] = None,
    technical_details: Optional[str] = None
) -> UserFriendlyError:
    """
    Format an error code into a user-friendly error message.

    Args:
        code: The error code
        context: Dictionary of values to substitute in the message template
        technical_details: Optional technical details to include

    Returns:
        UserFriendlyError with formatted message and next steps
    """
    template = ERROR_TEMPLATES.get(code, ERROR_TEMPLATES[ErrorCode.UNKNOWN_ERROR])

    # Merge default context with provided context
    full_context = {**DEFAULT_CONTEXT}
    if context:
        full_context.update(context)

    # Format the message and next steps with context
    try:
        title = template["title"].format(**full_context)
        message = template["message"].format(**full_context)
        next_steps = [step.format(**full_context) for step in template["next_steps"]]
    except KeyError as e:
        # Handle missing context keys gracefully
        logger.warning(f"Missing context key in error template: {e}")
        title = template["title"]
        message = template["message"]
        next_steps = list(template["next_steps"])

    return UserFriendlyError(
        code=code,
        title=title,
        message=message,
        next_steps=next_steps,
        technical_details=technical_details,
        severity=template.get("severity", "error")
    )


def detect_error_code(exception: Exception, operation: Optional[str] = None) -> ErrorCode:
    """
    Detect the appropriate error code from an exception.

    Args:
        exception: The exception to analyze
        operation: Optional operation context for better detection

    Returns:
        The most appropriate ErrorCode
    """
    error_str = str(exception).lower()
    error_type = type(exception).__name__.lower()

    # Network errors
    if "connection" in error_str or "connect" in error_type:
        return ErrorCode.NETWORK_ERROR
    if "timeout" in error_str or "timed out" in error_str:
        return ErrorCode.API_TIMEOUT
    if "ssl" in error_str or "certificate" in error_str:
        return ErrorCode.SSL_ERROR

    # Rate limiting
    if "rate" in error_str and "limit" in error_str:
        return ErrorCode.API_RATE_LIMITED
    if "429" in error_str:
        return ErrorCode.API_RATE_LIMITED

    # Authentication errors
    if "401" in error_str or "unauthorized" in error_str:
        if "slack" in error_str:
            return ErrorCode.SLACK_AUTH_FAILED
        if "google" in error_str:
            return ErrorCode.GOOGLE_AUTH_FAILED
        if "heygen" in error_str:
            return ErrorCode.HEYGEN_AUTH_FAILED
        return ErrorCode.API_KEY_INVALID

    # API key errors
    if "api key" in error_str or "api_key" in error_str:
        if "invalid" in error_str or "wrong" in error_str:
            return ErrorCode.API_KEY_INVALID
        if "missing" in error_str or "not set" in error_str or "not found" in error_str:
            return ErrorCode.API_KEY_MISSING

    # Permission errors
    if "403" in error_str or "forbidden" in error_str or "permission" in error_str:
        if "sheet" in error_str:
            return ErrorCode.GOOGLE_SHEET_PERMISSION_DENIED
        return ErrorCode.PERMISSION_DENIED

    # Not found errors
    if "404" in error_str or "not found" in error_str:
        if "sheet" in error_str:
            return ErrorCode.GOOGLE_SHEET_NOT_FOUND
        if "channel" in error_str:
            return ErrorCode.SLACK_CHANNEL_NOT_FOUND
        if "job" in error_str:
            return ErrorCode.JOB_NOT_FOUND

    # Server errors
    if any(code in error_str for code in ["500", "502", "503", "504"]):
        return ErrorCode.API_SERVER_ERROR

    # Token errors
    if "token" in error_str:
        if "expired" in error_str:
            return ErrorCode.TOKEN_EXPIRED
        if "refresh" in error_str:
            return ErrorCode.TOKEN_REFRESH_FAILED

    # Parse errors
    if "json" in error_str or "parse" in error_str or "decode" in error_str:
        return ErrorCode.PARSE_ERROR

    # File errors
    if "file" in error_str and ("not found" in error_str or "missing" in error_str):
        return ErrorCode.CONFIG_FILE_MISSING

    # Browser errors
    if "browser" in error_str or "playwright" in error_str:
        if "element" in error_str:
            return ErrorCode.ELEMENT_NOT_FOUND
        if "load" in error_str or "navigate" in error_str:
            return ErrorCode.PAGE_LOAD_FAILED
        return ErrorCode.BROWSER_LAUNCH_FAILED

    # Slack-specific
    if "slack" in error_str:
        if "signature" in error_str:
            return ErrorCode.SLACK_SIGNATURE_INVALID
        if "message" in error_str:
            return ErrorCode.SLACK_MESSAGE_FAILED

    # HeyGen-specific
    if "heygen" in error_str:
        if "video" in error_str:
            return ErrorCode.HEYGEN_VIDEO_FAILED

    # Operation-specific fallbacks
    if operation:
        op_lower = operation.lower()
        if "scrap" in op_lower:
            return ErrorCode.SCRAPER_FAILED
        if "filter" in op_lower or "scor" in op_lower:
            return ErrorCode.PREFILTER_FAILED
        if "extract" in op_lower:
            return ErrorCode.EXTRACTION_FAILED
        if "deliverable" in op_lower or "proposal" in op_lower or "video" in op_lower:
            return ErrorCode.DELIVERABLE_GENERATION_FAILED
        if "submit" in op_lower:
            return ErrorCode.SUBMISSION_FAILED

    return ErrorCode.UNKNOWN_ERROR


def format_error_from_exception(
    exception: Exception,
    operation: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None
) -> UserFriendlyError:
    """
    Create a user-friendly error from an exception.

    Args:
        exception: The exception to format
        operation: Optional operation context (e.g., "scoring jobs")
        context: Additional context for the error message

    Returns:
        UserFriendlyError with formatted message
    """
    error_code = detect_error_code(exception, operation)

    # Build context from exception if not provided
    full_context = context or {}
    if operation and "operation" not in full_context:
        full_context["operation"] = operation

    # Add exception details as technical info
    technical_details = f"{type(exception).__name__}: {str(exception)}"

    return format_error(error_code, full_context, technical_details)


def get_error_summary(errors: List[UserFriendlyError]) -> str:
    """
    Create a summary of multiple errors for display.

    Args:
        errors: List of UserFriendlyError objects

    Returns:
        Formatted summary string
    """
    if not errors:
        return "No errors"

    if len(errors) == 1:
        return errors[0].format_for_display()

    lines = [f"Encountered {len(errors)} errors:", ""]

    for i, error in enumerate(errors, 1):
        lines.append(f"{i}. {error.title}: {error.message}")

    # Collect unique next steps
    all_steps = []
    seen_steps = set()
    for error in errors:
        for step in error.next_steps:
            if step not in seen_steps:
                all_steps.append(step)
                seen_steps.add(step)

    if all_steps:
        lines.extend(["", "Recommended actions:"])
        for i, step in enumerate(all_steps[:5], 1):  # Limit to 5 steps
            lines.append(f"  {i}. {step}")

    return "\n".join(lines)


# Convenience functions for common error scenarios
def api_key_error(service: str, env_var: str, provider_url: str) -> UserFriendlyError:
    """Create an API key missing error."""
    return format_error(
        ErrorCode.API_KEY_MISSING,
        {"service": service, "env_var": env_var, "provider_url": provider_url}
    )


def rate_limit_error(service: str, wait_time: str = "a few minutes") -> UserFriendlyError:
    """Create a rate limit error."""
    return format_error(
        ErrorCode.API_RATE_LIMITED,
        {"service": service, "wait_time": wait_time}
    )


def network_error(service: str) -> UserFriendlyError:
    """Create a network error."""
    return format_error(ErrorCode.NETWORK_ERROR, {"service": service})


def pipeline_stage_error(stage: str, job_id: str, details: Optional[str] = None) -> UserFriendlyError:
    """Create a pipeline stage error."""
    return format_error(
        ErrorCode.PIPELINE_STAGE_FAILED,
        {"stage": stage, "job_id": job_id},
        technical_details=details
    )


if __name__ == "__main__":
    # Demo/test the error messages
    print("User-Friendly Error Messages Demo\n" + "="*50)

    # Example 1: API key missing
    error1 = api_key_error("Anthropic", "ANTHROPIC_API_KEY", "https://console.anthropic.com")
    print("\nExample 1: API Key Missing")
    print(error1.format_for_display())

    # Example 2: Rate limit
    print("\n" + "="*50)
    error2 = rate_limit_error("OpenAI", "60 seconds")
    print("\nExample 2: Rate Limited")
    print(error2.format_for_display())

    # Example 3: From exception
    print("\n" + "="*50)
    try:
        raise ConnectionError("Failed to connect to api.anthropic.com: Connection refused")
    except Exception as e:
        error3 = format_error_from_exception(e, operation="scoring jobs")
        print("\nExample 3: From Exception")
        print(error3.format_for_display(include_technical=True))

    # Example 4: Multiple errors summary
    print("\n" + "="*50)
    errors = [
        error1,
        network_error("Google Sheets"),
        rate_limit_error("Slack")
    ]
    print("\nExample 4: Error Summary")
    print(get_error_summary(errors))
