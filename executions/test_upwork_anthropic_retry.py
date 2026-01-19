#!/usr/bin/env python3
"""
Unit Tests for Upwork Anthropic API Retry Logic

Tests Feature #97: Pipeline handles Anthropic rate limits gracefully

Test categories:
1. AnthropicRetryConfig - Configuration and delay calculations
2. Error classification - Identifying error types
3. Retryable error detection - Which errors should trigger retry
4. Retry logic - Sync and async retry behavior
5. Rate limit handling - Special rate limit behavior
6. Decorator functionality - @with_anthropic_retry decorator
7. Result tracking - AnthropicRetryResult structure
8. Recorder helper - Test utility class
9. Feature #97 requirements - Explicit requirement tests
"""

import unittest
import asyncio
import time
from unittest.mock import Mock, patch, MagicMock
from dataclasses import asdict

# Import the module under test
from upwork_anthropic_retry import (
    AnthropicRetryConfig,
    AnthropicRetryResult,
    AnthropicErrorType,
    classify_anthropic_error,
    is_retryable_anthropic_error,
    get_retry_after_from_error,
    retry_anthropic_call,
    retry_anthropic_call_async,
    retry_anthropic_call_with_result,
    with_anthropic_retry,
    AnthropicAPICallRecorder,
    retry_prefilter_call,
    retry_proposal_call,
    retry_boost_call,
    create_pipeline_retry_handler,
)


class TestAnthropicRetryConfig(unittest.TestCase):
    """Test AnthropicRetryConfig dataclass and methods."""

    def test_default_values(self):
        """Test default configuration values."""
        config = AnthropicRetryConfig()
        self.assertEqual(config.max_retries, 5)
        self.assertEqual(config.base_delay, 2.0)
        self.assertEqual(config.max_delay, 120.0)
        self.assertEqual(config.jitter_factor, 0.25)
        self.assertTrue(config.respect_retry_after)

    def test_custom_values(self):
        """Test custom configuration values."""
        config = AnthropicRetryConfig(
            max_retries=3,
            base_delay=5.0,
            max_delay=60.0,
            jitter_factor=0.1
        )
        self.assertEqual(config.max_retries, 3)
        self.assertEqual(config.base_delay, 5.0)
        self.assertEqual(config.max_delay, 60.0)
        self.assertEqual(config.jitter_factor, 0.1)

    def test_get_delay_exponential_backoff(self):
        """Test that delays follow exponential backoff pattern."""
        config = AnthropicRetryConfig(
            base_delay=2.0,
            max_delay=120.0,
            jitter_factor=0  # No jitter for predictable testing
        )

        # Attempt 0: 2.0s
        delay0 = config.get_delay(0)
        self.assertEqual(delay0, 2.0)

        # Attempt 1: 4.0s
        delay1 = config.get_delay(1)
        self.assertEqual(delay1, 4.0)

        # Attempt 2: 8.0s
        delay2 = config.get_delay(2)
        self.assertEqual(delay2, 8.0)

        # Attempt 3: 16.0s
        delay3 = config.get_delay(3)
        self.assertEqual(delay3, 16.0)

    def test_get_delay_respects_max(self):
        """Test that delay is capped at max_delay."""
        config = AnthropicRetryConfig(
            base_delay=2.0,
            max_delay=10.0,
            jitter_factor=0
        )

        # Attempt 4: would be 32.0s but capped at 10.0s
        delay = config.get_delay(4)
        self.assertEqual(delay, 10.0)

    def test_get_delay_includes_jitter(self):
        """Test that delays include jitter when factor > 0."""
        config = AnthropicRetryConfig(
            base_delay=2.0,
            jitter_factor=0.25
        )

        delays = [config.get_delay(0) for _ in range(10)]
        # All delays should be >= base (2.0s)
        for delay in delays:
            self.assertGreaterEqual(delay, 2.0)
        # At least some should have jitter (> 2.0s)
        self.assertTrue(any(d > 2.0 for d in delays))
        # Max with 25% jitter: 2.0 + 0.5 = 2.5
        for delay in delays:
            self.assertLessEqual(delay, 2.5)

    def test_get_delay_for_rate_limit(self):
        """Test rate limit specific delay calculation."""
        config = AnthropicRetryConfig(base_delay=2.0)

        # Without retry-after: should use longer default
        delay = config.get_delay_for_rate_limit()
        self.assertGreaterEqual(delay, 10.0)

        # With retry-after: should use that value
        delay = config.get_delay_for_rate_limit(retry_after=30.0)
        self.assertGreaterEqual(delay, 30.0)
        self.assertLess(delay, 32.0)  # Plus small jitter

    def test_retryable_types_default(self):
        """Test default retryable error types."""
        config = AnthropicRetryConfig()
        self.assertIn(AnthropicErrorType.RATE_LIMIT, config.retryable_types)
        self.assertIn(AnthropicErrorType.OVERLOADED, config.retryable_types)
        self.assertIn(AnthropicErrorType.SERVER_ERROR, config.retryable_types)
        self.assertIn(AnthropicErrorType.TIMEOUT, config.retryable_types)
        self.assertIn(AnthropicErrorType.CONNECTION, config.retryable_types)
        # Authentication and invalid request should NOT be retryable by default
        self.assertNotIn(AnthropicErrorType.AUTHENTICATION, config.retryable_types)
        self.assertNotIn(AnthropicErrorType.INVALID_REQUEST, config.retryable_types)


class TestErrorClassification(unittest.TestCase):
    """Test classify_anthropic_error function."""

    def test_rate_limit_by_class_name(self):
        """Test classification by exception class name."""
        # Create mock exception with RateLimitError name
        error = Exception("Rate limit")
        error.__class__.__name__ = "RateLimitError"
        self.assertEqual(classify_anthropic_error(error), AnthropicErrorType.RATE_LIMIT)

    def test_overloaded_by_class_name(self):
        """Test OverloadedError classification."""
        error = Exception("Overloaded")
        error.__class__.__name__ = "OverloadedError"
        self.assertEqual(classify_anthropic_error(error), AnthropicErrorType.OVERLOADED)

    def test_server_error_by_class_name(self):
        """Test InternalServerError classification."""
        error = Exception("Server error")
        error.__class__.__name__ = "InternalServerError"
        self.assertEqual(classify_anthropic_error(error), AnthropicErrorType.SERVER_ERROR)

    def test_timeout_by_class_name(self):
        """Test APITimeoutError classification."""
        error = Exception("Timeout")
        error.__class__.__name__ = "APITimeoutError"
        self.assertEqual(classify_anthropic_error(error), AnthropicErrorType.TIMEOUT)

    def test_connection_by_class_name(self):
        """Test APIConnectionError classification."""
        error = Exception("Connection error")
        error.__class__.__name__ = "APIConnectionError"
        self.assertEqual(classify_anthropic_error(error), AnthropicErrorType.CONNECTION)

    def test_auth_by_class_name(self):
        """Test AuthenticationError classification."""
        error = Exception("Auth error")
        error.__class__.__name__ = "AuthenticationError"
        self.assertEqual(classify_anthropic_error(error), AnthropicErrorType.AUTHENTICATION)

    def test_bad_request_by_class_name(self):
        """Test BadRequestError classification."""
        error = Exception("Bad request")
        error.__class__.__name__ = "BadRequestError"
        self.assertEqual(classify_anthropic_error(error), AnthropicErrorType.INVALID_REQUEST)

    def test_rate_limit_by_message(self):
        """Test classification by error message."""
        error = Exception("Rate limit exceeded. Please retry.")
        self.assertEqual(classify_anthropic_error(error), AnthropicErrorType.RATE_LIMIT)

    def test_429_by_message(self):
        """Test 429 status code in message."""
        error = Exception("HTTP 429: Too Many Requests")
        self.assertEqual(classify_anthropic_error(error), AnthropicErrorType.RATE_LIMIT)

    def test_overloaded_by_message(self):
        """Test overloaded by message."""
        error = Exception("The API is currently overloaded")
        self.assertEqual(classify_anthropic_error(error), AnthropicErrorType.OVERLOADED)

    def test_529_by_message(self):
        """Test 529 (Anthropic overloaded) status code in message."""
        error = Exception("HTTP 529: API Overloaded")
        self.assertEqual(classify_anthropic_error(error), AnthropicErrorType.OVERLOADED)

    def test_server_error_by_message(self):
        """Test server error by message."""
        error = Exception("HTTP 500 Internal Server Error")
        self.assertEqual(classify_anthropic_error(error), AnthropicErrorType.SERVER_ERROR)

    def test_timeout_by_message(self):
        """Test timeout by message."""
        error = Exception("Request timeout after 30 seconds")
        self.assertEqual(classify_anthropic_error(error), AnthropicErrorType.TIMEOUT)

    def test_connection_by_message(self):
        """Test connection error by message."""
        error = Exception("Connection reset by peer")
        self.assertEqual(classify_anthropic_error(error), AnthropicErrorType.CONNECTION)

    def test_ssl_by_message(self):
        """Test SSL error classified as connection."""
        error = Exception("SSL certificate verify failed")
        self.assertEqual(classify_anthropic_error(error), AnthropicErrorType.CONNECTION)

    def test_unknown_error(self):
        """Test unknown error classification."""
        error = Exception("Some random error")
        self.assertEqual(classify_anthropic_error(error), AnthropicErrorType.UNKNOWN)


class TestIsRetryableError(unittest.TestCase):
    """Test is_retryable_anthropic_error function."""

    def test_rate_limit_is_retryable(self):
        """Test that rate limit errors are retryable."""
        config = AnthropicRetryConfig()
        error = Exception("Rate limit exceeded")
        self.assertTrue(is_retryable_anthropic_error(error, config))

    def test_overloaded_is_retryable(self):
        """Test that overloaded errors are retryable."""
        config = AnthropicRetryConfig()
        error = Exception("API overloaded")
        self.assertTrue(is_retryable_anthropic_error(error, config))

    def test_timeout_is_retryable(self):
        """Test that timeout errors are retryable."""
        config = AnthropicRetryConfig()
        error = Exception("Request timeout")
        self.assertTrue(is_retryable_anthropic_error(error, config))

    def test_auth_not_retryable(self):
        """Test that authentication errors are NOT retryable by default."""
        config = AnthropicRetryConfig()
        error = Exception("Authentication failed")
        error.__class__.__name__ = "AuthenticationError"
        self.assertFalse(is_retryable_anthropic_error(error, config))

    def test_bad_request_not_retryable(self):
        """Test that bad request errors are NOT retryable by default."""
        config = AnthropicRetryConfig()
        error = Exception("Bad request: invalid parameter")
        error.__class__.__name__ = "BadRequestError"
        self.assertFalse(is_retryable_anthropic_error(error, config))

    def test_custom_retryable_types(self):
        """Test with custom retryable types."""
        config = AnthropicRetryConfig(
            retryable_types=[AnthropicErrorType.RATE_LIMIT]
        )
        # Rate limit should be retryable
        rate_error = Exception("Rate limit")
        self.assertTrue(is_retryable_anthropic_error(rate_error, config))
        # Timeout should NOT be retryable with custom config
        timeout_error = Exception("Timeout")
        self.assertFalse(is_retryable_anthropic_error(timeout_error, config))


class TestGetRetryAfter(unittest.TestCase):
    """Test get_retry_after_from_error function."""

    def test_retry_after_header(self):
        """Test extracting retry-after from response headers."""
        error = Exception("Rate limited")
        error.response = Mock()
        error.response.headers = {'retry-after': '60'}

        retry_after = get_retry_after_from_error(error)
        self.assertEqual(retry_after, 60.0)

    def test_retry_after_in_message(self):
        """Test extracting retry-after from error message."""
        error = Exception("Rate limit exceeded. Try again in 30 seconds.")
        retry_after = get_retry_after_from_error(error)
        self.assertEqual(retry_after, 30.0)

    def test_retry_after_wait_pattern(self):
        """Test extracting retry-after from 'wait X seconds' pattern."""
        error = Exception("Please wait 45 seconds before retrying.")
        retry_after = get_retry_after_from_error(error)
        self.assertEqual(retry_after, 45.0)

    def test_no_retry_after(self):
        """Test when no retry-after is available."""
        error = Exception("Generic rate limit error")
        retry_after = get_retry_after_from_error(error)
        self.assertIsNone(retry_after)


class TestRetryAnthropicCall(unittest.TestCase):
    """Test retry_anthropic_call function."""

    def test_success_first_try(self):
        """Test successful call on first attempt."""
        result = retry_anthropic_call(lambda: "success")
        self.assertEqual(result, "success")

    def test_retry_on_rate_limit(self):
        """Test retry on rate limit error."""
        config = AnthropicRetryConfig(
            max_retries=3,
            base_delay=0.01,  # Fast for testing
            jitter_factor=0
        )

        call_count = [0]

        def flaky_call():
            call_count[0] += 1
            if call_count[0] < 2:
                raise Exception("Rate limit exceeded")
            return "success"

        result = retry_anthropic_call(flaky_call, config=config)
        self.assertEqual(result, "success")
        self.assertEqual(call_count[0], 2)

    def test_max_retries_exceeded(self):
        """Test that exception is raised after max retries."""
        config = AnthropicRetryConfig(
            max_retries=3,
            base_delay=0.01,
            jitter_factor=0
        )

        call_count = [0]

        def always_fails():
            call_count[0] += 1
            raise Exception("Rate limit exceeded")

        with self.assertRaises(Exception) as context:
            retry_anthropic_call(always_fails, config=config)

        self.assertIn("Rate limit", str(context.exception))
        self.assertEqual(call_count[0], 3)

    def test_non_retryable_error_not_retried(self):
        """Test that non-retryable errors are not retried."""
        config = AnthropicRetryConfig(
            max_retries=5,
            base_delay=0.01
        )

        call_count = [0]

        def auth_error():
            call_count[0] += 1
            error = Exception("Authentication failed")
            error.__class__.__name__ = "AuthenticationError"
            raise error

        with self.assertRaises(Exception):
            retry_anthropic_call(auth_error, config=config)

        # Should only be called once (no retries for auth errors)
        self.assertEqual(call_count[0], 1)

    def test_on_retry_callback(self):
        """Test that on_retry callback is called on each retry."""
        config = AnthropicRetryConfig(
            max_retries=3,
            base_delay=0.01,
            jitter_factor=0
        )

        retries = []

        def on_retry(attempt, error, delay):
            retries.append((attempt, str(error), delay))

        call_count = [0]

        def flaky_call():
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("Rate limit exceeded")
            return "success"

        result = retry_anthropic_call(flaky_call, config=config, on_retry=on_retry)
        self.assertEqual(result, "success")
        self.assertEqual(len(retries), 2)  # 2 retries before success


class TestRetryAnthropicCallAsync(unittest.TestCase):
    """Test retry_anthropic_call_async function."""

    def test_async_success(self):
        """Test successful async call."""
        async def success():
            return "async success"

        result = asyncio.run(retry_anthropic_call_async(success))
        self.assertEqual(result, "async success")

    def test_async_retry(self):
        """Test async retry on failure."""
        config = AnthropicRetryConfig(
            max_retries=3,
            base_delay=0.01,
            jitter_factor=0
        )

        call_count = [0]

        async def flaky_async():
            call_count[0] += 1
            if call_count[0] < 2:
                raise Exception("Rate limit")
            return "success"

        result = asyncio.run(retry_anthropic_call_async(flaky_async, config=config))
        self.assertEqual(result, "success")
        self.assertEqual(call_count[0], 2)


class TestWithAnthropicRetry(unittest.TestCase):
    """Test @with_anthropic_retry decorator."""

    def test_decorator_basic(self):
        """Test basic decorator usage."""
        @with_anthropic_retry(AnthropicRetryConfig(base_delay=0.01, jitter_factor=0))
        def simple_call():
            return "decorated result"

        result = simple_call()
        self.assertEqual(result, "decorated result")

    def test_decorator_with_args(self):
        """Test decorator preserves function arguments."""
        @with_anthropic_retry(AnthropicRetryConfig(base_delay=0.01, jitter_factor=0))
        def call_with_args(x, y, z=None):
            return f"{x}-{y}-{z}"

        result = call_with_args(1, 2, z=3)
        self.assertEqual(result, "1-2-3")

    def test_decorator_retries(self):
        """Test decorator applies retry logic."""
        config = AnthropicRetryConfig(max_retries=3, base_delay=0.01, jitter_factor=0)
        call_count = [0]

        @with_anthropic_retry(config)
        def flaky_decorated():
            call_count[0] += 1
            if call_count[0] < 2:
                raise Exception("Rate limit")
            return "success"

        result = flaky_decorated()
        self.assertEqual(result, "success")
        self.assertEqual(call_count[0], 2)

    def test_decorator_on_async_function(self):
        """Test decorator works on async functions."""
        config = AnthropicRetryConfig(max_retries=3, base_delay=0.01, jitter_factor=0)

        @with_anthropic_retry(config)
        async def async_func():
            return "async decorated"

        result = asyncio.run(async_func())
        self.assertEqual(result, "async decorated")


class TestAnthropicRetryResult(unittest.TestCase):
    """Test AnthropicRetryResult dataclass."""

    def test_default_values(self):
        """Test default result values."""
        result = AnthropicRetryResult(success=False)
        self.assertFalse(result.success)
        self.assertIsNone(result.result)
        self.assertIsNone(result.error)
        self.assertIsNone(result.error_type)
        self.assertEqual(result.attempts, 0)
        self.assertEqual(result.total_delay, 0.0)
        self.assertEqual(result.retry_delays, [])

    def test_success_result(self):
        """Test successful result."""
        result = AnthropicRetryResult(
            success=True,
            result="data",
            attempts=1,
            total_delay=0.0
        )
        self.assertTrue(result.success)
        self.assertEqual(result.result, "data")
        self.assertEqual(result.attempts, 1)

    def test_failure_result(self):
        """Test failure result."""
        error = Exception("Failed")
        result = AnthropicRetryResult(
            success=False,
            error=error,
            error_type=AnthropicErrorType.RATE_LIMIT,
            attempts=3,
            total_delay=6.0,
            retry_delays=[2.0, 4.0]
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error, error)
        self.assertEqual(result.error_type, AnthropicErrorType.RATE_LIMIT)
        self.assertEqual(result.attempts, 3)


class TestRetryCallWithResult(unittest.TestCase):
    """Test retry_anthropic_call_with_result function."""

    def test_success_returns_result(self):
        """Test successful call returns proper result."""
        config = AnthropicRetryConfig(base_delay=0.01)
        result = retry_anthropic_call_with_result(
            lambda: "success",
            config=config
        )
        self.assertTrue(result.success)
        self.assertEqual(result.result, "success")
        self.assertEqual(result.attempts, 1)

    def test_failure_returns_error_info(self):
        """Test failed call returns error information."""
        config = AnthropicRetryConfig(max_retries=2, base_delay=0.01, jitter_factor=0)

        result = retry_anthropic_call_with_result(
            lambda: (_ for _ in ()).throw(Exception("Rate limit")),
            config=config
        )
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(len(result.retry_delays), 1)

    def test_retry_tracking(self):
        """Test that retries are properly tracked in result."""
        config = AnthropicRetryConfig(max_retries=4, base_delay=0.01, jitter_factor=0)
        call_count = [0]

        def flaky():
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("Rate limit")
            return "success"

        result = retry_anthropic_call_with_result(flaky, config=config)
        self.assertTrue(result.success)
        self.assertEqual(result.attempts, 3)
        self.assertEqual(len(result.retry_delays), 2)


class TestAnthropicAPICallRecorder(unittest.TestCase):
    """Test AnthropicAPICallRecorder helper class."""

    def test_record_retry(self):
        """Test recording retries."""
        recorder = AnthropicAPICallRecorder()
        error = Exception("Rate limit")

        recorder.record_retry(0, error, 2.0)
        recorder.record_retry(1, error, 4.0)

        self.assertEqual(recorder.total_retries, 2)
        self.assertEqual(recorder.delays, [2.0, 4.0])
        self.assertEqual(recorder.total_delay, 6.0)
        self.assertEqual(len(recorder.errors), 2)

    def test_had_rate_limit(self):
        """Test rate limit detection in recordings."""
        recorder = AnthropicAPICallRecorder()
        rate_error = Exception("Rate limit exceeded")

        recorder.record_retry(0, rate_error, 2.0)

        self.assertTrue(recorder.had_rate_limit)

    def test_reset(self):
        """Test reset clears all recorded data."""
        recorder = AnthropicAPICallRecorder()
        recorder.record_retry(0, Exception("Error"), 1.0)

        recorder.reset()

        self.assertEqual(recorder.total_retries, 0)
        self.assertEqual(recorder.delays, [])
        self.assertEqual(recorder.errors, [])

    def test_integration_with_retry(self):
        """Test recorder works with retry function."""
        config = AnthropicRetryConfig(max_retries=3, base_delay=0.01, jitter_factor=0)
        recorder = AnthropicAPICallRecorder()

        call_count = [0]

        def flaky():
            call_count[0] += 1
            if call_count[0] < 2:
                raise Exception("Rate limit")
            return "success"

        result = retry_anthropic_call(
            flaky,
            config=config,
            on_retry=recorder.record_retry
        )

        self.assertEqual(result, "success")
        self.assertEqual(recorder.total_retries, 1)
        self.assertTrue(recorder.had_rate_limit)


class TestConvenienceFunctions(unittest.TestCase):
    """Test convenience functions for specific use cases."""

    def test_retry_prefilter_call(self):
        """Test retry_prefilter_call has appropriate config."""
        # Test it works (uses default config internally)
        result = retry_prefilter_call(lambda: "prefilter result")
        self.assertEqual(result, "prefilter result")

    def test_retry_proposal_call(self):
        """Test retry_proposal_call has appropriate config."""
        result = retry_proposal_call(lambda: "proposal result")
        self.assertEqual(result, "proposal result")

    def test_retry_boost_call(self):
        """Test retry_boost_call has appropriate config."""
        result = retry_boost_call(lambda: "boost result")
        self.assertEqual(result, "boost result")

    def test_create_pipeline_retry_handler(self):
        """Test create_pipeline_retry_handler returns config."""
        config = create_pipeline_retry_handler()
        self.assertIsInstance(config, AnthropicRetryConfig)
        self.assertEqual(config.max_retries, 5)
        self.assertTrue(config.respect_retry_after)


class TestFeature97Requirements(unittest.TestCase):
    """
    Explicit tests for Feature #97 requirements.

    Feature #97: Pipeline handles Anthropic rate limits gracefully
    Steps:
    1. Trigger rate limit condition
    2. Verify backoff is applied
    3. Verify processing resumes after cooldown
    """

    def test_rate_limit_triggers_backoff(self):
        """Step 1 & 2: Rate limit triggers backoff."""
        config = AnthropicRetryConfig(
            max_retries=3,
            base_delay=0.01,  # Fast for testing
            jitter_factor=0
        )
        recorder = AnthropicAPICallRecorder()

        call_count = [0]

        def rate_limited_call():
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Rate limit exceeded. Try again in 60 seconds.")
            return "success after rate limit"

        result = retry_anthropic_call(
            rate_limited_call,
            config=config,
            on_retry=recorder.record_retry
        )

        # Verify rate limit was detected
        self.assertTrue(recorder.had_rate_limit)
        # Verify backoff was applied (delay > 0)
        self.assertGreater(recorder.total_delay, 0)

    def test_processing_resumes_after_cooldown(self):
        """Step 3: Processing resumes after cooldown."""
        config = AnthropicRetryConfig(
            max_retries=5,
            base_delay=0.01,
            jitter_factor=0
        )

        call_count = [0]

        def recovers_after_cooldown():
            call_count[0] += 1
            # Fail first 3 times, succeed on 4th
            if call_count[0] < 4:
                raise Exception("Rate limit")
            return "recovered"

        result = retry_anthropic_call(recovers_after_cooldown, config=config)

        # Verify processing eventually succeeded
        self.assertEqual(result, "recovered")
        self.assertEqual(call_count[0], 4)

    def test_exponential_backoff_pattern(self):
        """Verify exponential backoff is used."""
        config = AnthropicRetryConfig(
            base_delay=1.0,
            max_delay=120.0,
            jitter_factor=0  # No jitter for predictable testing
        )

        # Get delays for attempts 0-4
        delays = [config.get_delay(i) for i in range(5)]

        # Verify exponential pattern: 1, 2, 4, 8, 16
        self.assertEqual(delays[0], 1.0)
        self.assertEqual(delays[1], 2.0)
        self.assertEqual(delays[2], 4.0)
        self.assertEqual(delays[3], 8.0)
        self.assertEqual(delays[4], 16.0)

    def test_rate_limit_gets_longer_delay(self):
        """Verify rate limits get appropriate longer cooldown."""
        config = AnthropicRetryConfig(base_delay=2.0)

        # Regular delay for attempt 0
        regular_delay = config.get_delay(0)

        # Rate limit delay should be longer
        rate_limit_delay = config.get_delay_for_rate_limit()

        self.assertGreater(rate_limit_delay, regular_delay)
        self.assertGreaterEqual(rate_limit_delay, 10.0)

    def test_429_http_error_is_handled(self):
        """Test HTTP 429 status code is properly handled."""
        error = Exception("HTTP 429: Too Many Requests")
        error_type = classify_anthropic_error(error)

        self.assertEqual(error_type, AnthropicErrorType.RATE_LIMIT)

        config = AnthropicRetryConfig()
        self.assertTrue(is_retryable_anthropic_error(error, config))

    def test_overloaded_529_is_handled(self):
        """Test HTTP 529 (Anthropic overloaded) is properly handled."""
        error = Exception("HTTP 529: API is temporarily overloaded")
        error_type = classify_anthropic_error(error)

        self.assertEqual(error_type, AnthropicErrorType.OVERLOADED)

        config = AnthropicRetryConfig()
        self.assertTrue(is_retryable_anthropic_error(error, config))

    def test_retry_after_header_respected(self):
        """Test that Retry-After header is respected when present."""
        error = Exception("Rate limited")
        error.response = Mock()
        error.response.headers = {'retry-after': '30'}

        retry_after = get_retry_after_from_error(error)

        # Should use the 30 second value from header
        self.assertEqual(retry_after, 30.0)

    def test_pipeline_continues_after_rate_limit(self):
        """Test that pipeline-style batch processing continues after rate limit."""
        config = AnthropicRetryConfig(max_retries=3, base_delay=0.01, jitter_factor=0)

        # Simulate batch processing with rate limit on second item
        results = []
        for i in range(3):
            call_count = [0]
            item_id = i

            def process_item(item=item_id):
                call_count[0] += 1
                if item == 1 and call_count[0] == 1:
                    raise Exception("Rate limit")
                return f"processed_{item}"

            result = retry_anthropic_call(process_item, config=config)
            results.append(result)

        # All items should be processed
        self.assertEqual(results, ["processed_0", "processed_1", "processed_2"])

    def test_async_rate_limit_handling(self):
        """Test async API calls handle rate limits properly."""
        config = AnthropicRetryConfig(max_retries=3, base_delay=0.01, jitter_factor=0)

        call_count = [0]

        async def async_rate_limited():
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Rate limit exceeded")
            return "async success"

        result = asyncio.run(retry_anthropic_call_async(async_rate_limited, config=config))

        self.assertEqual(result, "async success")
        self.assertEqual(call_count[0], 2)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""

    def test_zero_max_retries(self):
        """Test with zero max retries (effectively disabled)."""
        config = AnthropicRetryConfig(max_retries=1)  # Only one attempt

        def always_fails():
            raise Exception("Rate limit")

        with self.assertRaises(Exception):
            retry_anthropic_call(always_fails, config=config)

    def test_very_long_error_message(self):
        """Test handling of very long error messages."""
        long_message = "Error: " + "x" * 10000
        error = Exception(long_message)

        error_type = classify_anthropic_error(error)
        # Should still classify without error
        self.assertEqual(error_type, AnthropicErrorType.UNKNOWN)

    def test_unicode_in_error_message(self):
        """Test handling of unicode in error messages."""
        error = Exception("Rate limit exceeded \u26a0\ufe0f")
        error_type = classify_anthropic_error(error)
        self.assertEqual(error_type, AnthropicErrorType.RATE_LIMIT)

    def test_none_values_in_retry_after(self):
        """Test handling of None values in retry-after extraction."""
        error = Exception("No retry info")
        retry_after = get_retry_after_from_error(error)
        self.assertIsNone(retry_after)

    def test_empty_retryable_types(self):
        """Test with empty retryable types list."""
        config = AnthropicRetryConfig(retryable_types=[])

        error = Exception("Rate limit")
        self.assertFalse(is_retryable_anthropic_error(error, config))


class TestIntegrationWithPrefilter(unittest.TestCase):
    """Test integration pattern with pre-filter module."""

    def test_prefilter_retry_pattern(self):
        """Test retry pattern as it would be used in pre-filter."""
        config = AnthropicRetryConfig(max_retries=4, base_delay=0.01, jitter_factor=0)

        # Simulate what pre-filter scoring would do
        mock_response = {
            'score': 85,
            'reasoning': 'Good match for AI automation'
        }

        call_count = [0]

        def score_job_with_api():
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Rate limit exceeded")
            return mock_response

        result = retry_anthropic_call(score_job_with_api, config=config)

        self.assertEqual(result['score'], 85)
        self.assertEqual(call_count[0], 2)


if __name__ == "__main__":
    unittest.main()
