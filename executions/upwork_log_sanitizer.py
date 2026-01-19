#!/usr/bin/env python3
"""
Log sanitizer for Upwork Auto-Apply Pipeline.

Prevents accidental exposure of API keys, tokens, and other secrets in logs.

Usage:
    from upwork_log_sanitizer import setup_secure_logging, sanitize_string, SecretFilter

    # Option 1: Set up secure logging globally
    setup_secure_logging()

    # Option 2: Add filter to existing logger
    logger.addFilter(SecretFilter())

    # Option 3: Sanitize a string manually
    safe_string = sanitize_string(potentially_sensitive_data)

Features:
- Pattern-based detection of API keys, tokens, and secrets
- Masking preserves first/last few characters for debugging
- Works with Python's logging module
- Zero external dependencies

Feature #81: API keys are not logged or exposed
"""

import os
import re
import logging
from typing import List, Pattern, Optional


# Secret patterns to detect and mask
# Each tuple: (pattern_name, regex_pattern, mask_format)
SECRET_PATTERNS: List[tuple] = [
    # Anthropic API keys: sk-ant-api03-xxx or sk-ant-xxx
    ("anthropic_key", r"sk-ant-[a-zA-Z0-9_-]{20,}", "sk-ant-***MASKED***"),

    # Slack tokens: xoxb-xxx, xoxp-xxx, xoxa-xxx, xoxr-xxx
    ("slack_token", r"xox[bpar]-[a-zA-Z0-9-]{20,}", "xox*-***MASKED***"),

    # Slack signing secret (32 char hex)
    ("slack_signing_secret", r"[a-f0-9]{32}", "***SIGNING_SECRET***"),

    # Slack webhook URLs
    ("slack_webhook", r"https://hooks\.slack\.com/services/[A-Z0-9]+/[A-Z0-9]+/[a-zA-Z0-9]+", "https://hooks.slack.com/services/***MASKED***"),

    # HeyGen API keys
    ("heygen_key", r"[a-f0-9]{32,}", "***HEYGEN_KEY***"),

    # Apify tokens
    ("apify_token", r"apify_api_[a-zA-Z0-9]{20,}", "apify_api_***MASKED***"),

    # Google OAuth tokens (JWT format)
    ("google_token", r"ya29\.[a-zA-Z0-9_-]{50,}", "ya29.***MASKED***"),

    # Google refresh tokens
    ("google_refresh", r"1//[a-zA-Z0-9_-]{40,}", "1//***MASKED***"),

    # Generic API key patterns
    ("api_key", r"['\"]?api[_-]?key['\"]?\s*[:=]\s*['\"]?([a-zA-Z0-9_-]{16,})['\"]?", "api_key=***MASKED***"),

    # Generic token patterns
    ("bearer_token", r"Bearer\s+[a-zA-Z0-9_.-]+", "Bearer ***MASKED***"),

    # Authorization headers
    ("auth_header", r"Authorization['\"]?\s*[:=]\s*['\"]?[a-zA-Z0-9_.-]+['\"]?", "Authorization: ***MASKED***"),

    # OpenAI API keys
    ("openai_key", r"sk-[a-zA-Z0-9]{20,}", "sk-***MASKED***"),

    # Generic secrets in JSON
    ("json_secret", r'"(api_key|token|secret|password|key)":\s*"[^"]{8,}"', '"\\1": "***MASKED***"'),

    # PandaDoc API keys
    ("pandadoc_key", r"[a-f0-9]{64}", "***PANDADOC_KEY***"),

    # Instantly API keys
    ("instantly_key", r"[a-zA-Z0-9]{20,40}", None),  # Too generic, handled separately
]

# Compiled patterns for efficiency
_COMPILED_PATTERNS: List[tuple] = []


def _compile_patterns():
    """Compile regex patterns for efficiency."""
    global _COMPILED_PATTERNS
    if not _COMPILED_PATTERNS:
        _COMPILED_PATTERNS = [
            (name, re.compile(pattern, re.IGNORECASE), mask)
            for name, pattern, mask in SECRET_PATTERNS
            if mask is not None  # Skip patterns without masks (handled separately)
        ]


def _mask_value(value: str, visible_chars: int = 4) -> str:
    """
    Mask a value, keeping first and last few characters visible.

    Args:
        value: The value to mask
        visible_chars: Number of characters to keep visible at start/end

    Returns:
        Masked value like "sk-a***ed***xyz"
    """
    if len(value) <= visible_chars * 2 + 3:
        return "***MASKED***"

    return f"{value[:visible_chars]}***MASKED***{value[-visible_chars:]}"


def sanitize_string(text: str) -> str:
    """
    Sanitize a string by masking any detected secrets.

    Args:
        text: The string to sanitize

    Returns:
        Sanitized string with secrets masked
    """
    if not text or not isinstance(text, str):
        return text

    _compile_patterns()

    result = text

    for name, pattern, mask in _COMPILED_PATTERNS:
        if mask:
            result = pattern.sub(mask, result)

    # Additional specific masking for known env var names
    env_vars_to_mask = [
        "ANTHROPIC_API_KEY",
        "HEYGEN_API_KEY",
        "SLACK_BOT_TOKEN",
        "SLACK_SIGNING_SECRET",
        "SLACK_WEBHOOK_URL",
        "APIFY_API_TOKEN",
        "OPENAI_API_KEY",
        "GOOGLE_MAPS_API_KEY",
        "PANDADOC_API_KEY",
        "INSTANTLY_API_KEY",
        "ANYMAILFINDER_API_KEY",
    ]

    for var_name in env_vars_to_mask:
        value = os.getenv(var_name)
        if value and len(value) > 8 and value in result:
            result = result.replace(value, _mask_value(value))

    return result


class SecretFilter(logging.Filter):
    """
    Logging filter that sanitizes log messages to remove secrets.

    Usage:
        logger = logging.getLogger(__name__)
        logger.addFilter(SecretFilter())
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter and sanitize log record.

        Args:
            record: The log record to filter

        Returns:
            Always True (we modify, not filter out)
        """
        # Sanitize the main message
        if record.msg:
            if isinstance(record.msg, str):
                record.msg = sanitize_string(record.msg)

        # Sanitize args if present
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: sanitize_string(str(v)) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    sanitize_string(str(arg)) if isinstance(arg, str) else arg
                    for arg in record.args
                )

        return True


class SecureFormatter(logging.Formatter):
    """
    Logging formatter that sanitizes output.

    Usage:
        handler = logging.StreamHandler()
        handler.setFormatter(SecureFormatter('%(asctime)s - %(levelname)s - %(message)s'))
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format and sanitize the log record."""
        result = super().format(record)
        return sanitize_string(result)


def setup_secure_logging(
    level: int = None,
    format_string: str = None,
    logger_name: Optional[str] = None
):
    """
    Set up secure logging that automatically sanitizes secrets.

    Args:
        level: Logging level (default: INFO, or DEBUG if DEBUG env var is set)
        format_string: Custom format string (default: timestamp - level - message)
        logger_name: Specific logger to configure (default: root logger)

    Example:
        # Set up secure logging at module start
        setup_secure_logging()

        # Now all logs are automatically sanitized
        logger.info(f"Using API key: {api_key}")  # Key will be masked
    """
    if level is None:
        level = logging.DEBUG if os.getenv("DEBUG") else logging.INFO

    if format_string is None:
        format_string = '%(asctime)s - %(levelname)s - %(message)s'

    # Get the target logger
    if logger_name:
        target_logger = logging.getLogger(logger_name)
    else:
        target_logger = logging.getLogger()

    # Set level
    target_logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    for handler in target_logger.handlers[:]:
        target_logger.removeHandler(handler)

    # Create new handler with secure formatter
    handler = logging.StreamHandler()
    handler.setFormatter(SecureFormatter(format_string))
    handler.addFilter(SecretFilter())

    target_logger.addHandler(handler)

    return target_logger


def verify_no_secrets_in_log(log_content: str) -> dict:
    """
    Verify that log content doesn't contain exposed secrets.

    Args:
        log_content: The log content to verify

    Returns:
        Dict with 'safe' boolean and 'issues' list of detected problems
    """
    issues = []

    _compile_patterns()

    for name, pattern, _ in _COMPILED_PATTERNS:
        matches = pattern.findall(log_content)
        if matches:
            # Check if the match is masked or real
            for match in matches:
                if "***MASKED***" not in match and "***" not in str(match):
                    issues.append(f"Potential {name} exposure detected")

    # Check for known env var values
    sensitive_vars = [
        "ANTHROPIC_API_KEY",
        "HEYGEN_API_KEY",
        "SLACK_BOT_TOKEN",
        "SLACK_SIGNING_SECRET",
        "APIFY_API_TOKEN",
    ]

    for var_name in sensitive_vars:
        value = os.getenv(var_name)
        if value and len(value) > 8 and value in log_content:
            issues.append(f"{var_name} value found in log content")

    return {
        'safe': len(issues) == 0,
        'issues': issues
    }


# Auto-configure when imported in scripts
def _auto_setup():
    """Auto-setup logging filter on import if not already done."""
    root_logger = logging.getLogger()

    # Check if we already have a SecretFilter
    has_filter = any(isinstance(f, SecretFilter) for f in root_logger.filters)

    if not has_filter:
        root_logger.addFilter(SecretFilter())


# Only auto-setup if this is not the main module
# This allows testing without side effects
if __name__ != "__main__":
    _auto_setup()


def main():
    """Test the log sanitizer."""
    import sys

    # Set up secure logging for testing
    setup_secure_logging(level=logging.DEBUG)
    logger = logging.getLogger(__name__)

    print("Testing log sanitizer...\n")

    # Test cases
    test_cases = [
        "Normal message without secrets",
        "API key: sk-ant-api03-abc123def456ghi789jkl012mno345",
        "Slack token: xoxb-FAKE-TOKEN-HERE",
        "Bearer ya29.A0ARrdaM-abc123_def456_ghi789_jkl012_mno345_pqr678",
        '{"api_key": "super_secret_key_12345678"}',
        "Authorization: sk-ant-api03-secret123",
        "Multiple: sk-ant-xxx and xoxb-yyy in same message",
    ]

    print("=" * 60)
    print("Input -> Sanitized Output")
    print("=" * 60)

    for test in test_cases:
        sanitized = sanitize_string(test)
        print(f"\nInput:  {test[:50]}...")
        print(f"Output: {sanitized[:50]}...")

    print("\n" + "=" * 60)
    print("Testing logging integration")
    print("=" * 60 + "\n")

    # These should be masked in output
    logger.info("Testing with fake API key: sk-ant-api03-test12345678901234")
    logger.debug("Slack token test: xoxb-FAKE-TOKEN")
    logger.warning("Authorization header: Bearer ya29.A0test1234567890abcdef")

    print("\n" + "=" * 60)
    print("Verification test")
    print("=" * 60)

    # Test verification
    safe_log = "Normal log message without any secrets"
    unsafe_log = "API key is sk-ant-api03-abc123def456ghi789"

    safe_result = verify_no_secrets_in_log(safe_log)
    unsafe_result = verify_no_secrets_in_log(unsafe_log)

    print(f"\nSafe log check: {safe_result}")
    print(f"Unsafe log check: {unsafe_result}")

    print("\n" + "=" * 60)
    print("All tests complete!")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
