#!/usr/bin/env python3
"""
Tests for Feature #81: API keys are not logged or exposed.

Tests the log sanitizer module to ensure:
1. API keys are properly masked in logs
2. Various secret patterns are detected
3. .env is in .gitignore
4. Verbose logging doesn't expose keys
"""

import os
import sys
import logging
import unittest
from io import StringIO
from unittest.mock import patch

# Add executions directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from upwork_log_sanitizer import (
    sanitize_string,
    SecretFilter,
    SecureFormatter,
    setup_secure_logging,
    verify_no_secrets_in_log,
    _mask_value,
)


class TestSanitizeString(unittest.TestCase):
    """Test sanitize_string function."""

    def test_normal_string_unchanged(self):
        """Normal strings without secrets should not change."""
        text = "This is a normal log message"
        self.assertEqual(sanitize_string(text), text)

    def test_anthropic_key_masked(self):
        """Anthropic API keys should be masked."""
        text = "Using key: sk-ant-api03-abc123def456ghi789jkl012"
        result = sanitize_string(text)
        self.assertNotIn("abc123def456ghi789jkl012", result)
        self.assertIn("***MASKED***", result)

    def test_slack_bot_token_masked(self):
        """Slack bot tokens should be masked."""
        text = "Token: xoxb-FAKE-TEST-TOKEN-PLACEHOLDER"
        result = sanitize_string(text)
        self.assertNotIn("123456789012", result)
        self.assertIn("***MASKED***", result)

    def test_slack_user_token_masked(self):
        """Slack user tokens should be masked."""
        text = "Token: xoxp-FAKE-TEST-TOKEN-PLACEHOLDER"
        result = sanitize_string(text)
        self.assertIn("***MASKED***", result)

    def test_google_oauth_token_masked(self):
        """Google OAuth tokens should be masked."""
        text = "Token: ya29.A0ARrdaM-abc123_def456_ghi789_jkl012_mno345_pqr678_stu"
        result = sanitize_string(text)
        self.assertNotIn("abc123_def456", result)
        self.assertIn("***MASKED***", result)

    def test_bearer_token_masked(self):
        """Bearer tokens should be masked."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = sanitize_string(text)
        self.assertIn("***MASKED***", result)

    def test_slack_webhook_masked(self):
        """Slack webhook URLs should be masked."""
        text = "Webhook: https://hooks.slack.com/services/TXXXFAKE/BXXXFAKE/FAKEHOOKNOTREAL"
        result = sanitize_string(text)
        self.assertNotIn("T00000000", result)
        self.assertIn("***MASKED***", result)

    def test_apify_token_masked(self):
        """Apify tokens should be masked."""
        text = "Token: apify_api_abc123def456ghi789jkl012"
        result = sanitize_string(text)
        self.assertNotIn("abc123def456", result)
        self.assertIn("***MASKED***", result)

    def test_json_secret_masked(self):
        """JSON format secrets should be masked."""
        text = '{"api_key": "super_secret_key_12345678901234567890"}'
        result = sanitize_string(text)
        self.assertIn("***MASKED***", result)

    def test_openai_key_masked(self):
        """OpenAI API keys should be masked."""
        text = "Key: sk-proj-abc123def456ghi789jkl012"
        result = sanitize_string(text)
        self.assertIn("***MASKED***", result)

    def test_multiple_secrets_masked(self):
        """Multiple secrets in one string should all be masked."""
        text = "Keys: sk-ant-api03-secret1234567890123456 and xoxb-FAKE-TOKEN"
        result = sanitize_string(text)
        self.assertNotIn("secret1234567890123456", result)
        self.assertNotIn("1234567890-abcdefghijklmnop", result)
        self.assertEqual(result.count("***MASKED***"), 2)

    def test_empty_string(self):
        """Empty strings should be handled."""
        self.assertEqual(sanitize_string(""), "")

    def test_none_returns_none(self):
        """None should be returned as-is."""
        self.assertIsNone(sanitize_string(None))


class TestMaskValue(unittest.TestCase):
    """Test the _mask_value function."""

    def test_long_value_masked(self):
        """Long values should show first/last chars."""
        result = _mask_value("abcdefghijklmnopqrstuvwxyz", visible_chars=4)
        self.assertEqual(result, "abcd***MASKED***wxyz")

    def test_short_value_fully_masked(self):
        """Short values should be fully masked."""
        result = _mask_value("short", visible_chars=4)
        self.assertEqual(result, "***MASKED***")


class TestSecretFilter(unittest.TestCase):
    """Test the SecretFilter logging filter."""

    def test_filter_sanitizes_message(self):
        """Filter should sanitize log record message."""
        filter_obj = SecretFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="API key: sk-ant-api03-secret1234567890123456",
            args=(),
            exc_info=None
        )

        filter_obj.filter(record)
        self.assertIn("***MASKED***", record.msg)
        self.assertNotIn("secret1234567890123456", record.msg)

    def test_filter_returns_true(self):
        """Filter should always return True (don't filter out records)."""
        filter_obj = SecretFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Normal message",
            args=(),
            exc_info=None
        )

        self.assertTrue(filter_obj.filter(record))

    def test_filter_handles_args(self):
        """Filter should sanitize args tuple."""
        filter_obj = SecretFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Key: %s",
            args=("sk-ant-api03-secret1234567890123456",),
            exc_info=None
        )

        filter_obj.filter(record)
        self.assertIn("***MASKED***", str(record.args))


class TestSecureFormatter(unittest.TestCase):
    """Test the SecureFormatter."""

    def test_formatter_sanitizes_output(self):
        """Formatter should sanitize the final output."""
        formatter = SecureFormatter('%(message)s')
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Token: xoxb-FAKE-TEST-TOKEN",
            args=(),
            exc_info=None
        )

        output = formatter.format(record)
        self.assertIn("***MASKED***", output)


class TestSetupSecureLogging(unittest.TestCase):
    """Test setup_secure_logging function."""

    def test_setup_adds_filter(self):
        """Setup should add SecretFilter to logger."""
        logger = setup_secure_logging(logger_name="test_setup")
        has_secret_filter = any(
            isinstance(f, SecretFilter)
            for f in logger.filters
        )
        has_handler_filter = any(
            any(isinstance(f, SecretFilter) for f in h.filters)
            for h in logger.handlers
        )
        self.assertTrue(has_secret_filter or has_handler_filter)

    def test_setup_respects_debug_env(self):
        """Setup should use DEBUG level when DEBUG env is set."""
        with patch.dict(os.environ, {'DEBUG': '1'}):
            logger = setup_secure_logging(logger_name="test_debug")
            self.assertEqual(logger.level, logging.DEBUG)


class TestVerifyNoSecrets(unittest.TestCase):
    """Test verify_no_secrets_in_log function."""

    def test_safe_log_passes(self):
        """Safe log content should pass verification."""
        log = "Normal log message without any secrets"
        result = verify_no_secrets_in_log(log)
        self.assertTrue(result['safe'])
        self.assertEqual(len(result['issues']), 0)

    def test_masked_log_passes(self):
        """Already masked content should pass."""
        log = "Token: ***MASKED***"
        result = verify_no_secrets_in_log(log)
        self.assertTrue(result['safe'])


class TestGitignore(unittest.TestCase):
    """Test that .env is properly in .gitignore."""

    def test_env_in_gitignore(self):
        """The .env file should be in .gitignore."""
        gitignore_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            '.gitignore'
        )

        self.assertTrue(os.path.exists(gitignore_path), ".gitignore file should exist")

        with open(gitignore_path, 'r') as f:
            gitignore_content = f.read()

        # Check for .env entries
        self.assertIn('.env', gitignore_content, ".env should be in .gitignore")

    def test_token_files_in_gitignore(self):
        """Token files should be in .gitignore."""
        gitignore_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            '.gitignore'
        )

        with open(gitignore_path, 'r') as f:
            gitignore_content = f.read()

        # Check for token patterns
        self.assertIn('token', gitignore_content.lower(),
                     "Token files should be in .gitignore")


class TestIntegration(unittest.TestCase):
    """Integration tests for the full logging pipeline."""

    def test_full_logging_pipeline(self):
        """Test that secrets are masked through the full logging pipeline."""
        # Capture log output
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setFormatter(SecureFormatter('%(message)s'))
        handler.addFilter(SecretFilter())

        logger = logging.getLogger("test_integration")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        # Log a message with a secret
        logger.info("API key: sk-ant-api03-integrationtest12345678901234")

        log_output = log_capture.getvalue()

        # Verify secret is masked
        self.assertNotIn("integrationtest12345678901234", log_output)
        self.assertIn("***MASKED***", log_output)

        # Cleanup
        logger.removeHandler(handler)

    def test_verbose_logging_does_not_expose_keys(self):
        """Verbose/debug logging should not expose keys."""
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setFormatter(SecureFormatter('%(levelname)s - %(message)s'))
        handler.addFilter(SecretFilter())

        logger = logging.getLogger("test_verbose")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        # Simulate verbose logging with secrets
        logger.debug("Debug: connecting with xoxb-FAKE-VERBOSE-TOKEN")
        logger.debug("Request headers: Authorization: Bearer super_secret_token_abc123")
        logger.info("Using Anthropic key: sk-ant-api03-verbose12345678901234567")

        log_output = log_capture.getvalue()

        # Verify no secrets exposed
        self.assertNotIn("verbose-test-token", log_output)
        self.assertNotIn("super_secret_token", log_output)
        self.assertNotIn("verbose12345678901234567", log_output)

        # Cleanup
        logger.removeHandler(handler)


class TestEnvVarMasking(unittest.TestCase):
    """Test masking of actual environment variable values."""

    def test_env_var_values_masked(self):
        """Actual env var values should be masked when logged."""
        # Set a test env var
        test_key = "test_secret_value_12345678901234567890"
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': test_key}):
            text = f"Using key: {test_key}"
            result = sanitize_string(text)

            # The actual value should be masked
            self.assertNotIn("test_secret_value_12345678901234567890", result)
            self.assertIn("***MASKED***", result)


def run_tests():
    """Run all tests and return results."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestSanitizeString))
    suite.addTests(loader.loadTestsFromTestCase(TestMaskValue))
    suite.addTests(loader.loadTestsFromTestCase(TestSecretFilter))
    suite.addTests(loader.loadTestsFromTestCase(TestSecureFormatter))
    suite.addTests(loader.loadTestsFromTestCase(TestSetupSecureLogging))
    suite.addTests(loader.loadTestsFromTestCase(TestVerifyNoSecrets))
    suite.addTests(loader.loadTestsFromTestCase(TestGitignore))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestEnvVarMasking))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
