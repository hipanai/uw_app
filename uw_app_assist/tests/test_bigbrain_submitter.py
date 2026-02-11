"""Tests for the big-brain.io Apify submitter."""

from unittest.mock import patch

import pytest

from uw_app_assist.apify_runner import ActorRunFailed, ActorTimeout
from uw_app_assist.submitter.bigbrain_submitter import (
    submit_application,
    SubmissionResult,
    _extract_job_id,
)

JOB_URL = "https://www.upwork.com/jobs/~01abc123def456"
JOB_ID = "~01abc123def456"
PROPOSAL = "I'd love to help with your project."

_MOD = "uw_app_assist.submitter.bigbrain_submitter"
_RUN_ACTOR = f"{_MOD}.run_actor"


@pytest.fixture(autouse=True)
def _fake_creds():
    """Patch Upwork/Apify credentials for every test."""
    with (
        patch(f"{_MOD}.UPWORK_USERNAME", "user"),
        patch(f"{_MOD}.UPWORK_PASSWORD", "pass"),
        patch(f"{_MOD}.APIFY_API_TOKEN", "token"),
        patch(f"{_MOD}.BIGBRAIN_ACTOR_ID", "actor-id"),
        patch(f"{_MOD}.UPWORK_FREELANCER_NAME", ""),
        patch(f"{_MOD}.UPWORK_DEFAULT_ANSWER", ""),
        patch(f"{_MOD}.UPWORK_PROXY_GROUP", ""),
    ):
        yield


# -- extract_job_id ----------------------------------------------------------

def test_extract_job_id_valid():
    assert _extract_job_id(JOB_URL) == JOB_ID


def test_extract_job_id_invalid():
    with pytest.raises(ValueError):
        _extract_job_id("https://www.upwork.com/jobs/no-id-here")


# -- submit_application: success paths ----------------------------------------

@patch(_RUN_ACTOR, return_value=[{"status": "success", "message": "Done!"}])
def test_success_with_dataset_item(mock_run):
    result = submit_application(JOB_URL, PROPOSAL)

    assert result.status == "success"
    assert result.job_id == JOB_ID
    assert result.cover_letter_filled is True
    assert result.confirmation_message == "Done!"
    assert result.submitted_at is not None
    mock_run.assert_called_once()


@patch(_RUN_ACTOR, return_value=[{"status": "submitted"}])
def test_success_submitted_status(mock_run):
    result = submit_application(JOB_URL, PROPOSAL)
    assert result.status == "success"


@patch(_RUN_ACTOR, return_value=[])
def test_success_no_dataset_items(mock_run):
    result = submit_application(JOB_URL, PROPOSAL)
    assert result.status == "success"
    assert "no dataset output" in result.confirmation_message


@patch(_RUN_ACTOR, return_value=[{"status": "success"}])
def test_boost_applied_flag(mock_run):
    result = submit_application(JOB_URL, PROPOSAL, should_boost=True)
    assert result.boost_applied is True


@patch(_RUN_ACTOR, return_value=[{"status": "success"}])
def test_test_mode_passed_to_actor(mock_run):
    submit_application(JOB_URL, PROPOSAL, test_mode=True)
    actor_input = mock_run.call_args[1]["input_data"]
    assert actor_input["testMode"] is True


# -- submit_application: failure paths ----------------------------------------

@patch(_RUN_ACTOR, return_value=[{"status": "failed", "error": "Login failed"}])
def test_actor_returns_failure_status(mock_run):
    result = submit_application(JOB_URL, PROPOSAL)
    assert result.status == "failed"
    assert "Login failed" in result.error
    assert len(result.error_log) == 1


@patch(_RUN_ACTOR, return_value=[{"status": "blocked"}])
def test_actor_returns_unknown_status(mock_run):
    result = submit_application(JOB_URL, PROPOSAL)
    assert result.status == "failed"
    assert "blocked" in result.error


@patch(_RUN_ACTOR, side_effect=ActorRunFailed("actor-id", "FAILED", "run-1"))
def test_actor_run_failed_exception(mock_run):
    result = submit_application(JOB_URL, PROPOSAL)
    assert result.status == "failed"
    assert "failed" in result.error.lower()
    assert len(result.error_log) == 1


@patch(_RUN_ACTOR, side_effect=ActorTimeout("actor-id", 300, "run-1"))
def test_actor_timeout_exception(mock_run):
    result = submit_application(JOB_URL, PROPOSAL)
    assert result.status == "error"
    assert "timed out" in result.error.lower()


@patch(_RUN_ACTOR, side_effect=RuntimeError("Connection reset"))
def test_unexpected_exception(mock_run):
    result = submit_application(JOB_URL, PROPOSAL)
    assert result.status == "error"
    assert "Connection reset" in result.error


# -- submit_application: validation -------------------------------------------

def test_invalid_job_url():
    result = submit_application("https://example.com/no-job-id", PROPOSAL)
    assert result.status == "error"
    assert result.job_id == "unknown"
    assert "Could not extract job ID" in result.error


@patch(_RUN_ACTOR)
def test_missing_credentials(mock_run):
    with patch(f"{_MOD}.UPWORK_USERNAME", ""), \
         patch(f"{_MOD}.UPWORK_PASSWORD", ""):
        result = submit_application(JOB_URL, PROPOSAL)

    assert result.status == "error"
    assert "UPWORK_USERNAME" in result.error
    mock_run.assert_not_called()


# -- SubmissionResult helpers -------------------------------------------------

def test_to_dict():
    r = SubmissionResult(job_id="~abc", job_url=JOB_URL, status="success")
    d = r.to_dict()
    assert d["job_id"] == "~abc"
    assert d["status"] == "success"


def test_to_sheet_update_success():
    r = SubmissionResult(job_id="~abc", job_url=JOB_URL, status="success",
                         submitted_at="2026-01-01T00:00:00Z")
    update = r.to_sheet_update()
    assert update["status"] == "submitted"
    assert update["submitted_at"] == "2026-01-01T00:00:00Z"


def test_to_sheet_update_failure():
    r = SubmissionResult(job_id="~abc", job_url=JOB_URL, status="failed",
                         error_log=["some error"])
    update = r.to_sheet_update()
    assert update["status"] == "submission_failed"
    assert "some error" in update["error_log"]
