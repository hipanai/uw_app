#!/usr/bin/env python3
"""
Unit tests for Upwork Google API Retry Logic

Feature #96: Retry logic with exponential backoff for Google Docs

Test scenarios:
1. Simulate API failure on first attempt
2. Verify retry occurs after 1.5 seconds
3. Verify second retry after 3 seconds
4. Verify max 4 retries
"""

import unittest
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Import the retry module
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from upwork_google_retry import (
    GoogleRetryConfig,
    RetryResult,
    retry_google_api_call,
    retry_google_api_call_with_result,
    with_retry,
    is_retryable_error,
    GoogleAPICallRecorder,
    retry_docs_api,
    retry_drive_api,
    retry_sheets_api,
)


class TestGoogleRetryConfig(unittest.TestCase):
    """Test GoogleRetryConfig class."""

    def test_default_config(self):
        """Test default configuration values."""
        config = GoogleRetryConfig()
        self.assertEqual(config.max_retries, 4)
        self.assertEqual(config.base_delay, 1.5)
        self.assertEqual(config.max_delay, 60.0)

    def test_get_delay_exponential_backoff(self):
        """Test exponential backoff calculation."""
        config = GoogleRetryConfig(base_delay=1.5)

        # Verify exponential delays
        self.assertEqual(config.get_delay(0), 1.5)   # 1.5 * 2^0 = 1.5
        self.assertEqual(config.get_delay(1), 3.0)   # 1.5 * 2^1 = 3.0
        self.assertEqual(config.get_delay(2), 6.0)   # 1.5 * 2^2 = 6.0
        self.assertEqual(config.get_delay(3), 12.0)  # 1.5 * 2^3 = 12.0

    def test_delay_cap(self):
        """Test that delay is capped at max_delay."""
        config = GoogleRetryConfig(base_delay=1.5, max_delay=10.0)

        # Attempt 3 would be 12s but should be capped at 10s
        self.assertEqual(config.get_delay(3), 10.0)

    def test_custom_config(self):
        """Test custom configuration."""
        config = GoogleRetryConfig(max_retries=5, base_delay=2.0, max_delay=30.0)
        self.assertEqual(config.max_retries, 5)
        self.assertEqual(config.base_delay, 2.0)
        self.assertEqual(config.max_delay, 30.0)

    def test_retryable_status_codes(self):
        """Test default retryable status codes."""
        config = GoogleRetryConfig()
        self.assertIn(429, config.retryable_status_codes)
        self.assertIn(500, config.retryable_status_codes)
        self.assertIn(503, config.retryable_status_codes)


class TestIsRetryableError(unittest.TestCase):
    """Test is_retryable_error function."""

    def test_ssl_error_is_retryable(self):
        """Test that SSL errors are retryable."""
        config = GoogleRetryConfig()
        error = Exception("SSL connection reset by peer")
        self.assertTrue(is_retryable_error(error, config))

    def test_timeout_is_retryable(self):
        """Test that timeout errors are retryable."""
        config = GoogleRetryConfig()
        error = Exception("Connection timeout after 30s")
        self.assertTrue(is_retryable_error(error, config))

    def test_rate_limit_is_retryable(self):
        """Test that rate limit errors are retryable."""
        config = GoogleRetryConfig()
        error = Exception("Rate limit exceeded")
        self.assertTrue(is_retryable_error(error, config))

    def test_http_429_is_retryable(self):
        """Test that HTTP 429 (Too Many Requests) is retryable."""
        config = GoogleRetryConfig()

        # Mock Google API error with resp.status
        error = Mock()
        error.resp = Mock()
        error.resp.status = 429
        self.assertTrue(is_retryable_error(error, config))

    def test_http_503_is_retryable(self):
        """Test that HTTP 503 (Service Unavailable) is retryable."""
        config = GoogleRetryConfig()

        error = Mock()
        error.resp = Mock()
        error.resp.status = 503
        self.assertTrue(is_retryable_error(error, config))

    def test_generic_error_not_retryable(self):
        """Test that generic errors without known patterns are not retryable."""
        config = GoogleRetryConfig()
        error = Exception("Invalid document ID")
        self.assertFalse(is_retryable_error(error, config))


class TestRetryGoogleApiCall(unittest.TestCase):
    """Test retry_google_api_call function."""

    def test_success_on_first_attempt(self):
        """Test successful call on first attempt."""
        func = Mock(return_value="success")
        result = retry_google_api_call(func)

        self.assertEqual(result, "success")
        self.assertEqual(func.call_count, 1)

    def test_retry_on_failure_then_success(self):
        """Test retry after failure, then success."""
        call_count = [0]

        def flaky_func():
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("SSL error")
            return "success"

        # Use minimal delays for testing
        config = GoogleRetryConfig(base_delay=0.01)
        result = retry_google_api_call(flaky_func, config=config)

        self.assertEqual(result, "success")
        self.assertEqual(call_count[0], 3)

    def test_max_retries_exceeded(self):
        """Test that exception is raised after max retries."""
        func = Mock(side_effect=Exception("SSL error"))
        config = GoogleRetryConfig(max_retries=4, base_delay=0.01)

        with self.assertRaises(Exception) as context:
            retry_google_api_call(func, config=config)

        self.assertIn("SSL error", str(context.exception))
        self.assertEqual(func.call_count, 4)

    def test_retry_callback_called(self):
        """Test that on_retry callback is called on each retry."""
        call_count = [0]
        retry_records = []

        def flaky_func():
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("Connection reset")
            return "success"

        def on_retry(attempt, error, delay):
            retry_records.append((attempt, str(error), delay))

        config = GoogleRetryConfig(base_delay=0.01)
        retry_google_api_call(flaky_func, config=config, on_retry=on_retry)

        self.assertEqual(len(retry_records), 2)  # 2 retries before success
        self.assertEqual(retry_records[0][0], 0)  # First retry is attempt 0
        self.assertEqual(retry_records[1][0], 1)  # Second retry is attempt 1


class TestRetryDelays(unittest.TestCase):
    """Test that retry delays follow exponential backoff pattern."""

    def test_first_retry_delay_is_1_5_seconds(self):
        """Verify retry occurs after 1.5 seconds (Feature #96 requirement)."""
        config = GoogleRetryConfig()
        self.assertEqual(config.get_delay(0), 1.5)

    def test_second_retry_delay_is_3_seconds(self):
        """Verify second retry after 3 seconds (Feature #96 requirement)."""
        config = GoogleRetryConfig()
        self.assertEqual(config.get_delay(1), 3.0)

    def test_max_4_retries(self):
        """Verify max 4 retries (Feature #96 requirement)."""
        config = GoogleRetryConfig()
        self.assertEqual(config.max_retries, 4)

    @patch('upwork_google_retry.time.sleep')
    def test_actual_delays_applied(self, mock_sleep):
        """Test that actual delays are applied during retry."""
        call_count = [0]

        def failing_func():
            call_count[0] += 1
            raise Exception("SSL error")

        config = GoogleRetryConfig(max_retries=4, base_delay=1.5)

        with self.assertRaises(Exception):
            retry_google_api_call(failing_func, config=config)

        # Check sleep was called with correct delays
        sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
        self.assertEqual(len(sleep_calls), 3)  # 3 delays (between 4 attempts)
        self.assertEqual(sleep_calls[0], 1.5)  # First delay
        self.assertEqual(sleep_calls[1], 3.0)  # Second delay
        self.assertEqual(sleep_calls[2], 6.0)  # Third delay


class TestSimulateApiFailure(unittest.TestCase):
    """Test simulating API failure on first attempt (Feature #96 requirement)."""

    @patch('upwork_google_retry.time.sleep')
    def test_simulate_first_attempt_failure(self, mock_sleep):
        """Simulate API failure on first attempt and verify retry behavior."""
        attempts = []

        def api_call_with_first_failure():
            attempts.append(datetime.now())
            if len(attempts) == 1:
                raise Exception("SSL connection reset")
            return {"documentId": "doc123"}

        config = GoogleRetryConfig(base_delay=1.5)
        result = retry_google_api_call(api_call_with_first_failure, config=config)

        # Verify success on second attempt
        self.assertEqual(result, {"documentId": "doc123"})
        self.assertEqual(len(attempts), 2)

        # Verify sleep was called with 1.5s delay
        mock_sleep.assert_called_once_with(1.5)


class TestWithRetryDecorator(unittest.TestCase):
    """Test the @with_retry decorator."""

    def test_decorator_success(self):
        """Test decorator with successful function."""
        @with_retry()
        def successful_func():
            return "success"

        result = successful_func()
        self.assertEqual(result, "success")

    def test_decorator_retry_on_failure(self):
        """Test decorator retries on failure."""
        call_count = [0]

        @with_retry(config=GoogleRetryConfig(base_delay=0.01))
        def flaky_func():
            call_count[0] += 1
            if call_count[0] < 2:
                raise Exception("Temporary error")
            return "success"

        result = flaky_func()
        self.assertEqual(result, "success")
        self.assertEqual(call_count[0], 2)

    def test_decorator_preserves_function_metadata(self):
        """Test that decorator preserves function name and docstring."""
        @with_retry()
        def my_function():
            """My docstring."""
            return "result"

        self.assertEqual(my_function.__name__, "my_function")
        self.assertEqual(my_function.__doc__, "My docstring.")


class TestRetryWithResult(unittest.TestCase):
    """Test retry_google_api_call_with_result function."""

    def test_success_result(self):
        """Test successful result structure."""
        func = Mock(return_value="data")
        result = retry_google_api_call_with_result(func)

        self.assertTrue(result.success)
        self.assertEqual(result.result, "data")
        self.assertIsNone(result.error)
        self.assertEqual(result.attempts, 1)

    def test_failure_result(self):
        """Test failure result structure."""
        func = Mock(side_effect=Exception("API error"))
        config = GoogleRetryConfig(max_retries=2, base_delay=0.01)
        result = retry_google_api_call_with_result(func, config=config)

        self.assertFalse(result.success)
        self.assertIsNone(result.result)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.attempts, 2)

    def test_retry_delays_recorded(self):
        """Test that retry delays are recorded in result."""
        call_count = [0]

        def failing_twice():
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("SSL error")
            return "success"

        config = GoogleRetryConfig(base_delay=0.01)
        result = retry_google_api_call_with_result(failing_twice, config=config)

        self.assertTrue(result.success)
        self.assertEqual(len(result.retry_delays), 2)
        self.assertEqual(result.attempts, 3)


class TestGoogleAPICallRecorder(unittest.TestCase):
    """Test the GoogleAPICallRecorder helper class."""

    def test_recorder_captures_retries(self):
        """Test that recorder captures retry information."""
        recorder = GoogleAPICallRecorder()
        call_count = [0]

        def flaky_func():
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("Error")
            return "success"

        config = GoogleRetryConfig(base_delay=0.01)
        retry_google_api_call(flaky_func, config=config, on_retry=recorder.record_retry)

        self.assertEqual(recorder.total_retries, 2)
        self.assertEqual(len(recorder.delays), 2)
        self.assertEqual(len(recorder.errors), 2)

    def test_recorder_reset(self):
        """Test recorder reset functionality."""
        recorder = GoogleAPICallRecorder()
        recorder.record_retry(0, Exception("test"), 1.5)
        recorder.reset()

        self.assertEqual(recorder.total_retries, 0)
        self.assertEqual(len(recorder.delays), 0)


class TestConvenienceFunctions(unittest.TestCase):
    """Test convenience functions for specific Google APIs."""

    def test_retry_docs_api(self):
        """Test retry_docs_api function."""
        func = Mock(return_value="doc_result")
        result = retry_docs_api(func)
        self.assertEqual(result, "doc_result")

    def test_retry_drive_api(self):
        """Test retry_drive_api function."""
        func = Mock(return_value="drive_result")
        result = retry_drive_api(func)
        self.assertEqual(result, "drive_result")

    def test_retry_sheets_api(self):
        """Test retry_sheets_api function."""
        func = Mock(return_value="sheets_result")
        result = retry_sheets_api(func)
        self.assertEqual(result, "sheets_result")


class TestIntegrationWithDeliverableGenerator(unittest.TestCase):
    """Test integration with upwork_deliverable_generator.py patterns."""

    @patch('upwork_google_retry.time.sleep')
    def test_google_docs_create_pattern(self, mock_sleep):
        """Test retry pattern used in create_google_doc function."""
        # Mock the Docs service
        mock_docs_service = Mock()
        mock_doc = {"documentId": "test_doc_123"}

        call_count = [0]

        def mock_create():
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("SSL connection reset by peer")
            return mock_doc

        mock_docs_service.documents().create().execute = mock_create

        # Use retry logic
        config = GoogleRetryConfig(max_retries=4, base_delay=1.5)
        result = retry_google_api_call(
            lambda: mock_docs_service.documents().create().execute(),
            config=config
        )

        self.assertEqual(result, mock_doc)
        self.assertEqual(call_count[0], 2)
        mock_sleep.assert_called_once_with(1.5)


class TestFeature96Requirements(unittest.TestCase):
    """
    Explicit tests for Feature #96 requirements:
    1. Simulate API failure on first attempt
    2. Verify retry occurs after 1.5 seconds
    3. Verify second retry after 3 seconds
    4. Verify max 4 retries
    """

    @patch('upwork_google_retry.time.sleep')
    def test_requirement_1_simulate_api_failure_first_attempt(self, mock_sleep):
        """Feature #96 Step 1: Simulate API failure on first attempt."""
        attempts = []

        def api_call():
            attempts.append(len(attempts) + 1)
            if len(attempts) == 1:
                raise Exception("Simulated API failure")
            return "success"

        config = GoogleRetryConfig()
        result = retry_google_api_call(api_call, config=config)

        # First attempt failed
        self.assertEqual(attempts[0], 1)
        # Second attempt succeeded
        self.assertEqual(result, "success")
        self.assertEqual(len(attempts), 2)

    def test_requirement_2_retry_after_1_5_seconds(self):
        """Feature #96 Step 2: Verify retry occurs after 1.5 seconds."""
        config = GoogleRetryConfig()
        first_retry_delay = config.get_delay(0)
        self.assertEqual(first_retry_delay, 1.5)

    def test_requirement_3_second_retry_after_3_seconds(self):
        """Feature #96 Step 3: Verify second retry after 3 seconds."""
        config = GoogleRetryConfig()
        second_retry_delay = config.get_delay(1)
        self.assertEqual(second_retry_delay, 3.0)

    def test_requirement_4_max_4_retries(self):
        """Feature #96 Step 4: Verify max 4 retries."""
        config = GoogleRetryConfig()
        self.assertEqual(config.max_retries, 4)

        # Also verify that exactly 4 attempts are made
        call_count = [0]

        def always_fails():
            call_count[0] += 1
            raise Exception("Persistent error")

        config_fast = GoogleRetryConfig(max_retries=4, base_delay=0.001)

        with self.assertRaises(Exception):
            retry_google_api_call(always_fails, config=config_fast)

        self.assertEqual(call_count[0], 4)

    @patch('upwork_google_retry.time.sleep')
    def test_full_retry_sequence(self, mock_sleep):
        """Test complete retry sequence with all delays."""
        call_count = [0]

        def always_fails():
            call_count[0] += 1
            raise Exception("SSL error")

        config = GoogleRetryConfig(max_retries=4, base_delay=1.5)

        with self.assertRaises(Exception):
            retry_google_api_call(always_fails, config=config)

        # Verify all delays in sequence
        expected_delays = [1.5, 3.0, 6.0]  # 3 delays between 4 attempts
        actual_delays = [call.args[0] for call in mock_sleep.call_args_list]

        self.assertEqual(actual_delays, expected_delays)
        self.assertEqual(call_count[0], 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
