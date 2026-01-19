#!/usr/bin/env python3
"""
Quick verification script for Feature #87: User-friendly error messages

Verifies that:
1. Error messages are clear and understandable
2. Error messages suggest next steps for resolution
"""

import sys
import os

# Add executions to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'executions'))

from upwork_error_messages import (
    ErrorCode, format_error, format_error_from_exception,
    api_key_error, rate_limit_error, network_error, pipeline_stage_error,
    get_error_summary
)

def verify():
    """Run verification tests for Feature #87."""
    print("=" * 60)
    print("Feature #87: User-Friendly Error Messages - Verification")
    print("=" * 60)

    tests_passed = 0
    tests_failed = 0

    # Test 1: Error messages are clear
    print("\n[Test 1] Error messages are clear and understandable")
    error = format_error(ErrorCode.API_KEY_MISSING, {"service": "Anthropic"})
    assert error.title == "API Key Not Configured", f"Expected clear title, got: {error.title}"
    assert "Anthropic" in error.message, "Message should include context"
    assert len(error.message) > 20, "Message should be substantive"
    print("  PASSED: Error has clear title and message")
    tests_passed += 1

    # Test 2: Error messages suggest next steps
    print("\n[Test 2] Error messages suggest next steps")
    assert len(error.next_steps) >= 1, "Should have at least one next step"
    assert any(".env" in step for step in error.next_steps), "Should mention .env file"
    print(f"  PASSED: Error has {len(error.next_steps)} next steps")
    tests_passed += 1

    # Test 3: Various error conditions are covered
    print("\n[Test 3] Various error conditions are covered")
    errors_to_test = [
        ErrorCode.NETWORK_ERROR,
        ErrorCode.API_RATE_LIMITED,
        ErrorCode.GOOGLE_AUTH_FAILED,
        ErrorCode.SLACK_AUTH_FAILED,
        ErrorCode.HEYGEN_VIDEO_FAILED,
        ErrorCode.PIPELINE_STAGE_FAILED,
        ErrorCode.JOB_NOT_FOUND,
    ]
    for code in errors_to_test:
        err = format_error(code)
        assert err.title, f"Missing title for {code}"
        assert err.message, f"Missing message for {code}"
        assert err.next_steps, f"Missing next_steps for {code}"
    print(f"  PASSED: {len(errors_to_test)} error types have complete definitions")
    tests_passed += 1

    # Test 4: Exception detection works
    print("\n[Test 4] Exception detection works")
    exception = ConnectionError("Failed to connect")
    detected = format_error_from_exception(exception, operation="calling API")
    assert detected.code == ErrorCode.NETWORK_ERROR, "Should detect network error"
    print("  PASSED: Exception correctly detected as network error")
    tests_passed += 1

    # Test 5: Display formatting works
    print("\n[Test 5] Display formatting works")
    display = error.format_for_display()
    assert "Error:" in display, "Should have Error: prefix"
    assert "What to do next:" in display, "Should have next steps section"
    assert error.title in display, "Should include title"
    print("  PASSED: Display formatting includes all required sections")
    tests_passed += 1

    # Test 6: Convenience functions work
    print("\n[Test 6] Convenience functions work")
    api_err = api_key_error("Test", "TEST_KEY", "https://example.com")
    assert api_err.code == ErrorCode.API_KEY_MISSING

    rate_err = rate_limit_error("Test", "5 minutes")
    assert rate_err.code == ErrorCode.API_RATE_LIMITED

    net_err = network_error("Test")
    assert net_err.code == ErrorCode.NETWORK_ERROR

    pipe_err = pipeline_stage_error("extraction", "~job123", "Details")
    assert pipe_err.code == ErrorCode.PIPELINE_STAGE_FAILED
    print("  PASSED: All convenience functions work correctly")
    tests_passed += 1

    # Test 7: Error summary works
    print("\n[Test 7] Error summary works")
    errors = [api_err, net_err, rate_err]
    summary = get_error_summary(errors)
    assert "3 errors" in summary, "Should indicate error count"
    assert "Recommended actions" in summary, "Should have recommendations"
    print("  PASSED: Error summary correctly aggregates multiple errors")
    tests_passed += 1

    # Show example output
    print("\n" + "=" * 60)
    print("EXAMPLE OUTPUT - User-Friendly Error Message")
    print("=" * 60)
    example = api_key_error("Anthropic", "ANTHROPIC_API_KEY", "https://console.anthropic.com")
    print(example.format_for_display())

    print("\n" + "=" * 60)
    print(f"VERIFICATION RESULTS: {tests_passed} passed, {tests_failed} failed")
    print("=" * 60)

    if tests_failed == 0:
        print("\nFeature #87: PASSED")
        return 0
    else:
        print("\nFeature #87: FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(verify())
