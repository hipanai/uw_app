"""Submitter using big-brain.io/upwork-application Apify actor.

Replaces the Playwright-based UpworkSubmitter with an Apify actor that
handles login, form fill, and submit via managed proxies.
"""

import re
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

from ..apify_runner import run_actor, ActorRunFailed, ActorTimeout
from ..config import (
    APIFY_API_TOKEN,
    BIGBRAIN_ACTOR_ID,
    UPWORK_USERNAME,
    UPWORK_PASSWORD,
    UPWORK_FREELANCER_NAME,
    UPWORK_DEFAULT_ANSWER,
    UPWORK_PROXY_GROUP,
)

logger = logging.getLogger(__name__)


@dataclass
class SubmissionResult:
    """Result of a submission attempt.

    Compatible with the existing upwork_submitter.SubmissionResult interface.
    """

    job_id: str
    job_url: str
    status: str = "pending"  # pending | submitted | success | failed | error
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
        return asdict(self)

    def to_sheet_update(self) -> dict:
        import json

        return {
            "status": "submitted" if self.status == "success" else "submission_failed",
            "submitted_at": self.submitted_at,
            "error_log": json.dumps(self.error_log) if self.error_log else None,
        }


def _extract_job_id(url: str) -> str:
    """Extract the ciphertext job ID from an Upwork URL."""
    match = re.search(r"~([a-f0-9]+)", url, re.IGNORECASE)
    if match:
        return f"~{match.group(1)}"
    raise ValueError(f"Could not extract job ID from URL: {url}")


def submit_application(
    job_url: str,
    proposal_text: str,
    should_boost: bool = False,
    test_mode: bool = False,
) -> SubmissionResult:
    """Submit an Upwork application via the big-brain.io actor.

    Args:
        job_url: Upwork job URL
        proposal_text: Cover letter text (should already contain any
            cloud-hosted video/PDF links)
        should_boost: Whether to boost the proposal
        test_mode: If True, run the actor but don't actually submit

    Returns:
        SubmissionResult compatible with the existing pipeline
    """
    try:
        job_id = _extract_job_id(job_url)
    except ValueError as e:
        return SubmissionResult(
            job_id="unknown",
            job_url=job_url,
            status="error",
            error=str(e),
        )

    apply_url = f"https://www.upwork.com/nx/proposals/job/{job_id}/apply/"

    result = SubmissionResult(
        job_id=job_id,
        job_url=job_url,
        apply_url=apply_url,
    )

    # Validate credentials
    if not UPWORK_USERNAME or not UPWORK_PASSWORD:
        result.status = "error"
        result.error = "UPWORK_USERNAME and UPWORK_PASSWORD must be set in .env"
        return result

    # Build actor input (matches big-brain.io/upwork-application schema)
    default_answer = UPWORK_DEFAULT_ANSWER or "Yes, I'm available. Let's discuss on a call."
    actor_input = {
        "startUrls": [{"url": apply_url}],
        "username": UPWORK_USERNAME,
        "password": UPWORK_PASSWORD,
        "coverLetter": proposal_text,
        "boostProposal": should_boost,
        "defaultAnswer": default_answer,
        "securityQuestion": default_answer,
        "autoRefill": False,
        "debugMode": False,
        "ignoreDuplicateProposals": False,
        "testMode": test_mode,
    }

    if UPWORK_PROXY_GROUP:
        actor_input["proxyConfig"] = {
            "useApifyProxy": True,
            "apifyProxyGroups": [UPWORK_PROXY_GROUP],
        }
    else:
        actor_input["proxyConfig"] = {"useApifyProxy": True}

    logger.info(f"Submitting application for job {job_id} via big-brain.io actor")
    logger.info(f"Actor input: {actor_input}")

    try:
        items = run_actor(
            actor_id=BIGBRAIN_ACTOR_ID,
            input_data=actor_input,
            token=APIFY_API_TOKEN,
            max_wait=300,
        )

        # Parse actor result
        if items:
            actor_result = items[0]
            actor_status = actor_result.get("status", "").lower()

            if actor_status in ("success", "submitted"):
                result.status = "success"
                result.submitted_at = datetime.now(timezone.utc).isoformat()
                result.confirmation_message = actor_result.get(
                    "message", "Application submitted via Apify"
                )
                result.cover_letter_filled = True
                result.boost_applied = should_boost
                logger.info(f"Application submitted successfully for {job_id}")
            else:
                result.status = "failed"
                result.error = actor_result.get("error") or f"Actor returned status: {actor_status}"
                result.error_log.append(result.error)
                logger.warning(f"Submission failed for {job_id}: {result.error}")
        else:
            # Actor succeeded but returned no items — treat as success for
            # actors that don't write to dataset
            result.status = "success"
            result.submitted_at = datetime.now(timezone.utc).isoformat()
            result.confirmation_message = "Actor run completed (no dataset output)"
            result.cover_letter_filled = True
            result.boost_applied = should_boost

    except ActorRunFailed as e:
        result.status = "failed"
        result.error = str(e)
        result.error_log.append(str(e))
        logger.error(f"Actor run failed for {job_id}: {e}")

    except ActorTimeout as e:
        result.status = "error"
        result.error = str(e)
        result.error_log.append(str(e))
        logger.error(f"Actor timed out for {job_id}: {e}")

    except Exception as e:
        result.status = "error"
        result.error = str(e)
        result.error_log.append(str(e))
        logger.error(f"Unexpected error submitting {job_id}: {e}")

    return result
