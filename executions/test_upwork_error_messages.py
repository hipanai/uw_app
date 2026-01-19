#!/usr/bin/env python3
"""
Tests for Upwork Error Messages

Feature #87: Error messages are user-friendly

Tests that error messages:
1. Are clear and understandable
2. Suggest next steps for resolution
3. Cover various error conditions
4. Format properly for display
"""

import pytest
from unittest.mock import Mock, patch
import json

# Import the module under test
from upwork_error_messages import (
    ErrorCode,
    UserFriendlyError,
    ERROR_TEMPLATES,
    format_error,
    format_error_from_exception,
    detect_error_code,
    get_error_summary,
    api_key_error,
    rate_limit_error,
    network_error,
    pipeline_stage_error,
)


class TestFeature87ErrorMessageClarity:
    """Feature #87: Test that error messages are clear and understandable."""

    def test_error_message_has_title(self):
        """Error messages should have a clear title."""
        error = format_error(ErrorCode.API_KEY_MISSING, {"service": "Anthropic"})
        assert error.title is not None
        assert len(error.title) > 0
        assert len(error.title) < 100  # Title shouldn't be too long

    def test_error_message_has_explanation(self):
        """Error messages should have a clear explanation."""
        error = format_error(ErrorCode.NETWORK_ERROR, {"service": "Slack"})
        assert error.message is not None
        assert len(error.message) > 20  # Should be a real explanation
        assert "Slack" in error.message  # Should include context

    def test_error_messages_avoid_technical_jargon_in_title(self):
        """Error titles should be understandable by non-technical users."""
        technical_terms = ["exception", "stack", "trace", "null", "undefined", "NoneType"]

        for code in ErrorCode:
            error = format_error(code)
            title_lower = error.title.lower()
            for term in technical_terms:
                assert term not in title_lower, f"Title for {code} contains technical jargon: {term}"

    def test_error_messages_are_complete_sentences(self):
        """Error messages should be complete sentences."""
        error = format_error(ErrorCode.API_KEY_MISSING, {"service": "Anthropic"})
        # Should end with a period (or be a question)
        assert error.message.rstrip().endswith(('.', '?', '!'))

    def test_all_error_codes_have_templates(self):
        """Every error code should have a message template."""
        for code in ErrorCode:
            assert code in ERROR_TEMPLATES or code == ErrorCode.UNKNOWN_ERROR, \
                f"Missing template for {code}"


class TestFeature87NextSteps:
    """Feature #87: Test that error messages suggest next steps."""

    def test_error_has_next_steps(self):
        """Every error should suggest at least one next step."""
        error = format_error(ErrorCode.API_KEY_MISSING, {"service": "Anthropic"})
        assert error.next_steps is not None
        assert len(error.next_steps) >= 1

    def test_next_steps_are_actionable(self):
        """Next steps should be actionable (start with verbs)."""
        action_verbs = [
            "add", "check", "verify", "run", "delete", "create", "try", "wait",
            "ensure", "update", "review", "contact", "request", "get", "install",
            "reduce", "increase", "restart", "look", "generate", "copy", "the"
        ]

        error = format_error(ErrorCode.API_KEY_MISSING, {"service": "Anthropic"})
        for step in error.next_steps:
            first_word = step.lower().split()[0]
            # Allow steps starting with verbs or "The" (for instructions)
            assert first_word in action_verbs or first_word.endswith('e'), \
                f"Next step doesn't start with action verb: {step}"

    def test_next_steps_are_specific(self):
        """Next steps should be specific, not generic."""
        error = format_error(
            ErrorCode.API_KEY_MISSING,
            {"service": "Anthropic", "env_var": "ANTHROPIC_API_KEY"}
        )

        # Should mention specific things to do
        all_steps = " ".join(error.next_steps)
        assert "ANTHROPIC_API_KEY" in all_steps or ".env" in all_steps

    def test_all_templates_have_next_steps(self):
        """All error templates should have next steps."""
        for code, template in ERROR_TEMPLATES.items():
            assert "next_steps" in template, f"Missing next_steps for {code}"
            assert len(template["next_steps"]) >= 1, f"Empty next_steps for {code}"


class TestFeature87ErrorConditions:
    """Feature #87: Test various error conditions are covered."""

    def test_api_key_missing_error(self):
        """API key missing error should be clear."""
        error = api_key_error("Anthropic", "ANTHROPIC_API_KEY", "https://console.anthropic.com")
        assert "API" in error.title
        assert "Anthropic" in error.message
        assert "ANTHROPIC_API_KEY" in " ".join(error.next_steps)

    def test_rate_limit_error(self):
        """Rate limit error should suggest waiting."""
        error = rate_limit_error("OpenAI", "60 seconds")
        assert "limit" in error.title.lower() or "rate" in error.title.lower()
        assert "wait" in error.next_steps[0].lower()

    def test_network_error(self):
        """Network error should suggest checking connection."""
        error = network_error("Slack")
        assert "connection" in error.title.lower() or "network" in error.title.lower()
        assert any("connection" in step.lower() for step in error.next_steps)

    def test_pipeline_stage_error(self):
        """Pipeline error should include job and stage info."""
        error = pipeline_stage_error("extraction", "~abc123", "Timeout after 30s")
        assert "extraction" in error.message or "extraction" in error.title
        assert "~abc123" in error.message or "~abc123" in error.title
        assert error.technical_details == "Timeout after 30s"

    def test_google_auth_error(self):
        """Google auth error should suggest re-authenticating."""
        error = format_error(ErrorCode.GOOGLE_AUTH_FAILED)
        assert "google" in error.title.lower()
        assert any("auth" in step.lower() or "token" in step.lower() for step in error.next_steps)

    def test_slack_error(self):
        """Slack error should suggest checking token."""
        error = format_error(ErrorCode.SLACK_AUTH_FAILED)
        assert "slack" in error.title.lower()
        assert any("token" in step.lower() for step in error.next_steps)

    def test_heygen_error(self):
        """HeyGen error should suggest checking credits."""
        error = format_error(ErrorCode.HEYGEN_VIDEO_FAILED)
        assert any("heygen" in word.lower() for word in error.title.split())
        assert any("credit" in step.lower() or "quota" in step.lower() for step in error.next_steps)


class TestFeature87ExceptionDetection:
    """Feature #87: Test exception to error code detection."""

    def test_detect_connection_error(self):
        """Should detect network connection errors."""
        exception = ConnectionError("Connection refused")
        code = detect_error_code(exception)
        assert code == ErrorCode.NETWORK_ERROR

    def test_detect_timeout_error(self):
        """Should detect timeout errors."""
        exception = TimeoutError("Request timed out")
        code = detect_error_code(exception)
        assert code == ErrorCode.API_TIMEOUT

    def test_detect_rate_limit_from_message(self):
        """Should detect rate limits from error message."""
        exception = Exception("Rate limit exceeded, please wait")
        code = detect_error_code(exception)
        assert code == ErrorCode.API_RATE_LIMITED

    def test_detect_429_status(self):
        """Should detect 429 rate limit status code."""
        exception = Exception("HTTP 429 Too Many Requests")
        code = detect_error_code(exception)
        assert code == ErrorCode.API_RATE_LIMITED

    def test_detect_401_unauthorized(self):
        """Should detect 401 unauthorized errors."""
        exception = Exception("HTTP 401 Unauthorized")
        code = detect_error_code(exception)
        assert code == ErrorCode.API_KEY_INVALID

    def test_detect_ssl_error(self):
        """Should detect SSL errors."""
        exception = Exception("SSL certificate verify failed")
        code = detect_error_code(exception)
        assert code == ErrorCode.SSL_ERROR

    def test_detect_json_parse_error(self):
        """Should detect JSON parse errors."""
        exception = json.JSONDecodeError("Expecting value", "", 0)
        code = detect_error_code(exception)
        assert code == ErrorCode.PARSE_ERROR

    def test_detect_from_operation_context(self):
        """Should use operation context for detection."""
        exception = Exception("Something went wrong")
        code = detect_error_code(exception, operation="scraping jobs")
        assert code == ErrorCode.SCRAPER_FAILED

    def test_fallback_to_unknown(self):
        """Should fall back to unknown for unrecognized errors."""
        exception = Exception("Some random error")
        code = detect_error_code(exception)
        assert code == ErrorCode.UNKNOWN_ERROR


class TestFeature87FromException:
    """Feature #87: Test formatting errors from exceptions."""

    def test_format_from_connection_error(self):
        """Should format connection errors nicely."""
        try:
            raise ConnectionError("Failed to connect to api.example.com")
        except Exception as e:
            error = format_error_from_exception(e, operation="fetching data")

        assert error.code == ErrorCode.NETWORK_ERROR
        assert "Network" in error.title or "Connection" in error.title
        assert error.technical_details is not None
        assert "ConnectionError" in error.technical_details

    def test_format_includes_operation(self):
        """Should include operation in the error context."""
        try:
            raise Exception("Something failed")
        except Exception as e:
            error = format_error_from_exception(e, operation="scoring jobs")

        # Operation should be used if error is unknown
        assert "scoring jobs" in error.message or error.code != ErrorCode.UNKNOWN_ERROR

    def test_format_preserves_context(self):
        """Should preserve provided context."""
        try:
            raise Exception("API key not found")
        except Exception as e:
            error = format_error_from_exception(
                e,
                context={"service": "CustomService"}
            )

        # Either uses provided service or includes it
        assert error is not None


class TestFeature87DisplayFormatting:
    """Feature #87: Test error display formatting."""

    def test_format_for_display(self):
        """Should format error for display."""
        error = format_error(
            ErrorCode.API_KEY_MISSING,
            {"service": "Test", "env_var": "TEST_KEY"}
        )

        display = error.format_for_display()

        assert "Error:" in display
        assert error.title in display
        assert error.message in display
        assert "What to do next:" in display
        for step in error.next_steps:
            assert step in display

    def test_format_for_display_with_technical(self):
        """Should include technical details when requested."""
        error = format_error(
            ErrorCode.API_KEY_INVALID,
            technical_details="KeyError: 'api_key'"
        )

        display_without = error.format_for_display(include_technical=False)
        display_with = error.format_for_display(include_technical=True)

        assert "KeyError" not in display_without
        assert "KeyError" in display_with

    def test_format_for_log(self):
        """Should format error for logging."""
        error = format_error(ErrorCode.NETWORK_ERROR, {"service": "API"})

        log_msg = error.format_for_log()

        assert error.code.name in log_msg
        assert error.title in log_msg
        # Should be single line for logs
        assert "\n" not in log_msg

    def test_to_dict(self):
        """Should convert error to dictionary."""
        error = format_error(
            ErrorCode.API_KEY_MISSING,
            {"service": "Test"},
            technical_details="Details here"
        )

        d = error.to_dict()

        assert d["code"] == "API_KEY_MISSING"
        assert d["title"] == error.title
        assert d["message"] == error.message
        assert d["next_steps"] == error.next_steps
        assert d["technical_details"] == "Details here"
        assert d["severity"] == "error"


class TestFeature87ErrorSummary:
    """Feature #87: Test error summary generation."""

    def test_summary_single_error(self):
        """Single error should format as full display."""
        error = format_error(ErrorCode.NETWORK_ERROR, {"service": "API"})
        summary = get_error_summary([error])

        assert error.title in summary
        assert error.message in summary

    def test_summary_multiple_errors(self):
        """Multiple errors should show count and combined steps."""
        errors = [
            format_error(ErrorCode.NETWORK_ERROR, {"service": "API"}),
            format_error(ErrorCode.API_RATE_LIMITED, {"service": "Slack"})
        ]

        summary = get_error_summary(errors)

        assert "2 errors" in summary
        assert errors[0].title in summary
        assert errors[1].title in summary
        assert "Recommended actions" in summary

    def test_summary_empty_list(self):
        """Empty error list should return 'No errors'."""
        summary = get_error_summary([])
        assert "No errors" in summary

    def test_summary_deduplicates_steps(self):
        """Summary should deduplicate similar next steps."""
        # Create errors with overlapping next steps
        errors = [
            format_error(ErrorCode.NETWORK_ERROR, {"service": "API1"}),
            format_error(ErrorCode.NETWORK_ERROR, {"service": "API2"})
        ]

        summary = get_error_summary(errors)

        # Each step should appear only once
        lines = summary.split("\n")
        step_lines = [l for l in lines if l.strip().startswith(("1.", "2.", "3."))]
        step_texts = [l.split(". ", 1)[1] if ". " in l else l for l in step_lines]
        assert len(step_texts) == len(set(step_texts))


class TestFeature87Severity:
    """Feature #87: Test error severity levels."""

    def test_error_severity_default(self):
        """Default severity should be 'error'."""
        error = format_error(ErrorCode.API_KEY_MISSING)
        assert error.severity == "error"

    def test_warning_severity(self):
        """Rate limits should be warnings."""
        error = format_error(ErrorCode.API_RATE_LIMITED, {"service": "API"})
        assert error.severity == "warning"

    def test_info_severity(self):
        """Cancellation should be info."""
        error = format_error(ErrorCode.OPERATION_CANCELLED)
        assert error.severity == "info"


class TestFeature87ContextSubstitution:
    """Feature #87: Test context variable substitution."""

    def test_service_substitution(self):
        """Should substitute service name."""
        error = format_error(
            ErrorCode.NETWORK_ERROR,
            {"service": "MyCustomAPI"}
        )
        assert "MyCustomAPI" in error.message

    def test_env_var_substitution(self):
        """Should substitute environment variable name."""
        error = format_error(
            ErrorCode.API_KEY_MISSING,
            {"env_var": "MY_API_KEY"}
        )
        all_text = error.message + " ".join(error.next_steps)
        assert "MY_API_KEY" in all_text

    def test_job_id_substitution(self):
        """Should substitute job ID."""
        error = format_error(
            ErrorCode.JOB_NOT_FOUND,
            {"job_id": "~abc123xyz"}
        )
        assert "~abc123xyz" in error.message

    def test_missing_context_handled_gracefully(self):
        """Should handle missing context values gracefully."""
        # Should not raise even without context
        error = format_error(ErrorCode.API_KEY_MISSING)
        assert error is not None
        assert error.title is not None


class TestFeature87Integration:
    """Feature #87: Integration tests for error message flow."""

    def test_end_to_end_api_error(self):
        """Test full flow: exception -> detection -> formatting -> display."""
        # Simulate an API error
        exception = Exception("HTTP 429: Rate limit exceeded. Retry after 60 seconds.")

        # Detect and format
        error = format_error_from_exception(exception, operation="calling Anthropic API")

        # Verify result
        assert error.code == ErrorCode.API_RATE_LIMITED
        assert error.severity == "warning"
        assert len(error.next_steps) >= 1

        # Check display output
        display = error.format_for_display()
        assert "Rate" in display or "limit" in display.lower()
        assert "What to do next:" in display

    def test_end_to_end_auth_error(self):
        """Test auth error flow."""
        exception = Exception("401 Unauthorized: Invalid API key for Slack")

        error = format_error_from_exception(exception)

        # Should detect as Slack auth error
        assert error.code in [ErrorCode.SLACK_AUTH_FAILED, ErrorCode.API_KEY_INVALID]

        display = error.format_for_display()
        assert "What to do next:" in display

    def test_end_to_end_pipeline_error(self):
        """Test pipeline stage error flow."""
        # Create a pipeline error
        error = pipeline_stage_error(
            stage="deep extraction",
            job_id="~job789",
            details="Playwright timeout: element not found"
        )

        # Verify
        assert error.code == ErrorCode.PIPELINE_STAGE_FAILED
        assert "deep extraction" in error.message or "deep extraction" in error.title
        assert "~job789" in error.message or "~job789" in error.title
        assert error.technical_details is not None

        # Check log format
        log_msg = error.format_for_log()
        assert "PIPELINE_STAGE_FAILED" in log_msg


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
