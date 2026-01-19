#!/usr/bin/env python3
"""
Upwork Anthropic API Retry Logic

Implements exponential backoff retry logic for Anthropic API calls.
Handles rate limits, overload errors, and transient failures gracefully.

Feature #97: Pipeline handles Anthropic rate limits gracefully

Configuration:
- Default base delay: 2.0 seconds
- Default max retries: 5
- Exponential backoff with jitter: delay = base_delay * (2 ** attempt) + jitter
  - Attempt 0: ~2s
  - Attempt 1: ~4s
  - Attempt 2: ~8s
  - Attempt 3: ~16s
  - Attempt 4: ~32s

Usage:
    from upwork_anthropic_retry import (
        with_anthropic_retry,
        AnthropicRetryConfig,
        retry_anthropic_call
    )

    # Using decorator
    @with_anthropic_retry()
    def generate_proposal(client, prompt):
        return client.messages.create(...)

    # Using wrapper function
    result = retry_anthropic_call(
        lambda: client.messages.create(...)
    )

    # Custom config with longer cooldown
    config = AnthropicRetryConfig(max_retries=7, base_delay=5.0)
    result = retry_anthropic_call(my_func, config=config)

    # Async support
    result = await retry_anthropic_call_async(
        lambda: async_client.messages.create(...)
    )
"""

import time
import asyncio
import random
import functools
import logging
from dataclasses import dataclass, field
from typing import Callable, TypeVar, Optional, List, Any, Union
from enum import Enum

# Configure logging
logger = logging.getLogger(__name__)

# Type variable for generic return type
T = TypeVar('T')


class AnthropicErrorType(Enum):
    """Types of Anthropic API errors."""
    RATE_LIMIT = "rate_limit"
    OVERLOADED = "overloaded"
    SERVER_ERROR = "server_error"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    AUTHENTICATION = "authentication"
    INVALID_REQUEST = "invalid_request"
    UNKNOWN = "unknown"


@dataclass
class AnthropicRetryConfig:
    """Configuration for Anthropic API retry behavior."""
    max_retries: int = 5
    base_delay: float = 2.0  # seconds
    max_delay: float = 120.0  # cap the maximum delay (2 minutes)
    jitter_factor: float = 0.25  # random jitter up to 25% of delay
    # Whether to use Retry-After header if provided
    respect_retry_after: bool = True
    # Specific error types to retry
    retryable_types: List[AnthropicErrorType] = field(default_factory=lambda: [
        AnthropicErrorType.RATE_LIMIT,
        AnthropicErrorType.OVERLOADED,
        AnthropicErrorType.SERVER_ERROR,
        AnthropicErrorType.TIMEOUT,
        AnthropicErrorType.CONNECTION,
    ])

    def get_delay(self, attempt: int) -> float:
        """
        Calculate delay for a given attempt (0-indexed) with jitter.

        Args:
            attempt: The attempt number (0 = first retry)

        Returns:
            Delay in seconds with random jitter added
        """
        base = self.base_delay * (2 ** attempt)
        capped = min(base, self.max_delay)
        # Add random jitter
        jitter = random.uniform(0, capped * self.jitter_factor)
        return capped + jitter

    def get_delay_for_rate_limit(self, retry_after: Optional[float] = None) -> float:
        """
        Get delay specifically for rate limit errors.

        If retry_after is provided (from API header), use that.
        Otherwise use a longer default delay for rate limits.
        """
        if retry_after and self.respect_retry_after:
            return retry_after + random.uniform(0.1, 1.0)  # Small jitter
        # Default rate limit cooldown is longer
        return max(self.base_delay * 5, 10.0) + random.uniform(0, 5.0)


@dataclass
class AnthropicRetryResult:
    """Result of a retry operation."""
    success: bool
    result: Any = None
    error: Optional[Exception] = None
    error_type: Optional[AnthropicErrorType] = None
    attempts: int = 0
    total_delay: float = 0.0
    retry_delays: List[float] = field(default_factory=list)


def classify_anthropic_error(error: Exception) -> AnthropicErrorType:
    """
    Classify an Anthropic API error by type.

    Args:
        error: The exception that occurred

    Returns:
        The error type classification
    """
    error_name = type(error).__name__
    error_str = str(error).lower()

    # Check for specific Anthropic exception types
    if 'RateLimitError' in error_name:
        return AnthropicErrorType.RATE_LIMIT
    elif 'OverloadedError' in error_name:
        return AnthropicErrorType.OVERLOADED
    elif 'InternalServerError' in error_name:
        return AnthropicErrorType.SERVER_ERROR
    elif 'APITimeoutError' in error_name:
        return AnthropicErrorType.TIMEOUT
    elif 'APIConnectionError' in error_name:
        return AnthropicErrorType.CONNECTION
    elif 'AuthenticationError' in error_name:
        return AnthropicErrorType.AUTHENTICATION
    elif 'BadRequestError' in error_name or 'InvalidRequestError' in error_name:
        return AnthropicErrorType.INVALID_REQUEST

    # Check error message for common patterns
    if 'rate limit' in error_str or '429' in error_str:
        return AnthropicErrorType.RATE_LIMIT
    elif 'overloaded' in error_str or '529' in error_str:
        return AnthropicErrorType.OVERLOADED
    elif any(x in error_str for x in ['500', '502', '503', '504', 'server error']):
        return AnthropicErrorType.SERVER_ERROR
    elif 'timeout' in error_str:
        return AnthropicErrorType.TIMEOUT
    elif any(x in error_str for x in ['connection', 'network', 'socket', 'ssl']):
        return AnthropicErrorType.CONNECTION
    elif 'authentication' in error_str or 'unauthorized' in error_str or '401' in error_str:
        return AnthropicErrorType.AUTHENTICATION
    elif 'invalid' in error_str or 'bad request' in error_str or '400' in error_str:
        return AnthropicErrorType.INVALID_REQUEST

    return AnthropicErrorType.UNKNOWN


def is_retryable_anthropic_error(error: Exception, config: AnthropicRetryConfig) -> bool:
    """
    Check if an Anthropic API error should trigger a retry.

    Args:
        error: The exception that occurred
        config: Retry configuration

    Returns:
        True if the error is retryable
    """
    error_type = classify_anthropic_error(error)
    return error_type in config.retryable_types


def get_retry_after_from_error(error: Exception) -> Optional[float]:
    """
    Extract retry-after value from an Anthropic error if available.

    Args:
        error: The exception to check

    Returns:
        Retry-after value in seconds, or None if not available
    """
    # Check for response headers
    if hasattr(error, 'response') and hasattr(error.response, 'headers'):
        headers = error.response.headers
        if 'retry-after' in headers:
            try:
                return float(headers['retry-after'])
            except (ValueError, TypeError):
                pass

    # Check error message for retry time hints
    error_str = str(error)
    import re

    # Look for patterns like "try again in 60 seconds"
    patterns = [
        r'try again in (\d+(?:\.\d+)?)\s*(?:second|sec|s)',
        r'retry.after.(\d+(?:\.\d+)?)',
        r'wait\s+(\d+(?:\.\d+)?)\s*(?:second|sec|s)',
        r'cooldown.*?(\d+(?:\.\d+)?)\s*(?:second|sec|s)',
    ]

    for pattern in patterns:
        match = re.search(pattern, error_str, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except (ValueError, TypeError):
                pass

    return None


def retry_anthropic_call(
    func: Callable[[], T],
    config: Optional[AnthropicRetryConfig] = None,
    on_retry: Optional[Callable[[int, Exception, float], None]] = None,
    on_backoff: Optional[Callable[[float], None]] = None
) -> T:
    """
    Execute an Anthropic API call with exponential backoff retry.

    Args:
        func: The function to call (should be a lambda or callable with no args)
        config: Retry configuration (uses defaults if not provided)
        on_retry: Optional callback called on each retry with (attempt, error, delay)
        on_backoff: Optional callback called when backoff starts with (delay)

    Returns:
        The result of the function call

    Raises:
        The last exception if all retries are exhausted
    """
    if config is None:
        config = AnthropicRetryConfig()

    last_error = None
    total_delay = 0.0

    for attempt in range(config.max_retries):
        try:
            return func()
        except Exception as e:
            last_error = e
            error_type = classify_anthropic_error(e)

            # Check if this is the last attempt
            if attempt == config.max_retries - 1:
                logger.error(
                    f"Anthropic API call failed after {config.max_retries} attempts "
                    f"(error type: {error_type.value}): {e}"
                )
                raise

            # Check if error is retryable
            if not is_retryable_anthropic_error(e, config):
                logger.warning(f"Non-retryable error (type: {error_type.value}), not retrying: {e}")
                raise

            # Calculate delay - special handling for rate limits
            if error_type == AnthropicErrorType.RATE_LIMIT:
                retry_after = get_retry_after_from_error(e)
                delay = config.get_delay_for_rate_limit(retry_after)
            else:
                delay = config.get_delay(attempt)

            total_delay += delay

            logger.warning(
                f"Anthropic API call attempt {attempt + 1} failed ({error_type.value}), "
                f"retrying in {delay:.1f}s: {e}"
            )

            if on_retry:
                on_retry(attempt, e, delay)

            if on_backoff:
                on_backoff(delay)

            time.sleep(delay)

    # Should not reach here, but just in case
    if last_error:
        raise last_error
    raise RuntimeError("Unexpected state in retry logic")


async def retry_anthropic_call_async(
    func: Callable[[], T],
    config: Optional[AnthropicRetryConfig] = None,
    on_retry: Optional[Callable[[int, Exception, float], None]] = None,
    on_backoff: Optional[Callable[[float], None]] = None
) -> T:
    """
    Execute an Anthropic API call with exponential backoff retry (async version).

    Args:
        func: The async function to call
        config: Retry configuration (uses defaults if not provided)
        on_retry: Optional callback called on each retry with (attempt, error, delay)
        on_backoff: Optional callback called when backoff starts with (delay)

    Returns:
        The result of the function call

    Raises:
        The last exception if all retries are exhausted
    """
    if config is None:
        config = AnthropicRetryConfig()

    last_error = None

    for attempt in range(config.max_retries):
        try:
            result = func()
            # Handle both coroutines and regular values
            if asyncio.iscoroutine(result):
                return await result
            return result
        except Exception as e:
            last_error = e
            error_type = classify_anthropic_error(e)

            # Check if this is the last attempt
            if attempt == config.max_retries - 1:
                logger.error(
                    f"Anthropic API call failed after {config.max_retries} attempts "
                    f"(error type: {error_type.value}): {e}"
                )
                raise

            # Check if error is retryable
            if not is_retryable_anthropic_error(e, config):
                logger.warning(f"Non-retryable error (type: {error_type.value}), not retrying: {e}")
                raise

            # Calculate delay
            if error_type == AnthropicErrorType.RATE_LIMIT:
                retry_after = get_retry_after_from_error(e)
                delay = config.get_delay_for_rate_limit(retry_after)
            else:
                delay = config.get_delay(attempt)

            logger.warning(
                f"Anthropic API call attempt {attempt + 1} failed ({error_type.value}), "
                f"retrying in {delay:.1f}s: {e}"
            )

            if on_retry:
                on_retry(attempt, e, delay)

            if on_backoff:
                on_backoff(delay)

            await asyncio.sleep(delay)

    if last_error:
        raise last_error
    raise RuntimeError("Unexpected state in retry logic")


def with_anthropic_retry(
    config: Optional[AnthropicRetryConfig] = None,
    on_retry: Optional[Callable[[int, Exception, float], None]] = None
):
    """
    Decorator to add Anthropic API retry logic to a function.

    Args:
        config: Retry configuration
        on_retry: Optional callback called on each retry

    Usage:
        @with_anthropic_retry()
        def generate_proposal(client, prompt):
            return client.messages.create(...)

        @with_anthropic_retry(AnthropicRetryConfig(max_retries=3))
        async def score_job(client, job):
            return await client.messages.create(...)
    """
    if config is None:
        config = AnthropicRetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            return retry_anthropic_call(
                lambda: func(*args, **kwargs),
                config=config,
                on_retry=on_retry
            )

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            return await retry_anthropic_call_async(
                lambda: func(*args, **kwargs),
                config=config,
                on_retry=on_retry
            )

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper
    return decorator


def retry_anthropic_call_with_result(
    func: Callable[[], T],
    config: Optional[AnthropicRetryConfig] = None,
    on_retry: Optional[Callable[[int, Exception, float], None]] = None
) -> AnthropicRetryResult:
    """
    Execute an Anthropic API call with retry and return detailed result.

    Unlike retry_anthropic_call, this doesn't raise exceptions.
    Instead, it returns an AnthropicRetryResult with success/error information.

    Args:
        func: The function to call
        config: Retry configuration
        on_retry: Optional callback called on each retry

    Returns:
        AnthropicRetryResult with success, result/error, and retry statistics
    """
    if config is None:
        config = AnthropicRetryConfig()

    result = AnthropicRetryResult(success=False)

    for attempt in range(config.max_retries):
        try:
            result.result = func()
            result.success = True
            result.attempts = attempt + 1
            return result
        except Exception as e:
            result.error = e
            result.error_type = classify_anthropic_error(e)
            result.attempts = attempt + 1

            # Check if this is the last attempt
            if attempt == config.max_retries - 1:
                logger.error(
                    f"Anthropic API call failed after {config.max_retries} attempts: {e}"
                )
                return result

            # Check if error is retryable
            if not is_retryable_anthropic_error(e, config):
                logger.warning(f"Non-retryable error, not retrying: {e}")
                return result

            # Calculate delay
            if result.error_type == AnthropicErrorType.RATE_LIMIT:
                retry_after = get_retry_after_from_error(e)
                delay = config.get_delay_for_rate_limit(retry_after)
            else:
                delay = config.get_delay(attempt)

            result.retry_delays.append(delay)
            result.total_delay += delay

            logger.warning(
                f"Anthropic API call attempt {attempt + 1} failed, "
                f"retrying in {delay:.1f}s: {e}"
            )

            if on_retry:
                on_retry(attempt, e, delay)

            time.sleep(delay)

    return result


class AnthropicAPICallRecorder:
    """
    Test helper to record Anthropic API call attempts and delays.

    Usage in tests:
        recorder = AnthropicAPICallRecorder()

        @with_anthropic_retry(on_retry=recorder.record_retry)
        def my_api_call():
            ...

        # Check recorded data
        assert recorder.total_retries == 3
        assert recorder.delays[0] >= 2.0  # First retry delay
    """

    def __init__(self):
        self.attempts: List[int] = []
        self.delays: List[float] = []
        self.errors: List[Exception] = []
        self.error_types: List[AnthropicErrorType] = []

    def record_retry(self, attempt: int, error: Exception, delay: float):
        """Record a retry attempt."""
        self.attempts.append(attempt)
        self.errors.append(error)
        self.delays.append(delay)
        self.error_types.append(classify_anthropic_error(error))

    @property
    def total_retries(self) -> int:
        """Total number of retries (not including initial attempt)."""
        return len(self.attempts)

    @property
    def total_delay(self) -> float:
        """Total delay across all retries."""
        return sum(self.delays)

    @property
    def had_rate_limit(self) -> bool:
        """Whether any retry was due to rate limiting."""
        return AnthropicErrorType.RATE_LIMIT in self.error_types

    def reset(self):
        """Reset all recorded data."""
        self.attempts.clear()
        self.delays.clear()
        self.errors.clear()
        self.error_types.clear()


# Convenience functions with pre-configured settings

def retry_prefilter_call(func: Callable[[], T]) -> T:
    """
    Retry an Anthropic API call for pre-filter scoring.
    Uses moderate retry settings since these are frequent calls.
    """
    config = AnthropicRetryConfig(max_retries=4, base_delay=2.0)
    return retry_anthropic_call(func, config)


def retry_proposal_call(func: Callable[[], T]) -> T:
    """
    Retry an Anthropic API call for proposal generation.
    Uses more aggressive retry since these are expensive operations.
    """
    config = AnthropicRetryConfig(max_retries=5, base_delay=3.0, max_delay=180.0)
    return retry_anthropic_call(func, config)


def retry_boost_call(func: Callable[[], T]) -> T:
    """
    Retry an Anthropic API call for boost decision.
    Uses standard settings.
    """
    config = AnthropicRetryConfig(max_retries=4, base_delay=2.0)
    return retry_anthropic_call(func, config)


async def retry_prefilter_call_async(func: Callable[[], T]) -> T:
    """Async version of retry_prefilter_call."""
    config = AnthropicRetryConfig(max_retries=4, base_delay=2.0)
    return await retry_anthropic_call_async(func, config)


async def retry_proposal_call_async(func: Callable[[], T]) -> T:
    """Async version of retry_proposal_call."""
    config = AnthropicRetryConfig(max_retries=5, base_delay=3.0, max_delay=180.0)
    return await retry_anthropic_call_async(func, config)


# Pipeline integration helpers

def create_pipeline_retry_handler(
    on_rate_limit: Optional[Callable[[float], None]] = None,
    on_backoff_start: Optional[Callable[[], None]] = None,
    on_backoff_end: Optional[Callable[[], None]] = None
) -> AnthropicRetryConfig:
    """
    Create a retry configuration suitable for pipeline use with callbacks.

    Args:
        on_rate_limit: Called when rate limit is hit with cooldown time
        on_backoff_start: Called when backoff period starts
        on_backoff_end: Called when backoff period ends

    Returns:
        Configured AnthropicRetryConfig
    """
    return AnthropicRetryConfig(
        max_retries=5,
        base_delay=2.0,
        max_delay=120.0,
        respect_retry_after=True
    )


if __name__ == "__main__":
    # Demo/test the retry logic
    config = AnthropicRetryConfig()
    print("Anthropic Retry Configuration:")
    print(f"  Max retries: {config.max_retries}")
    print(f"  Base delay: {config.base_delay}s")
    print(f"  Max delay: {config.max_delay}s")
    print(f"  Jitter factor: {config.jitter_factor}")
    print(f"\nDelay progression (without jitter):")
    for i in range(config.max_retries):
        base = config.base_delay * (2 ** i)
        capped = min(base, config.max_delay)
        print(f"  Attempt {i}: {capped:.1f}s")

    print(f"\nRetryable error types:")
    for error_type in config.retryable_types:
        print(f"  - {error_type.value}")

    # Simulate a function that fails with rate limit then succeeds
    call_count = 0

    class MockRateLimitError(Exception):
        pass

    def flaky_api_call():
        global call_count
        call_count += 1
        if call_count < 3:
            raise MockRateLimitError("Rate limit exceeded. Try again in 60 seconds.")
        return "success!"

    print("\n" + "="*50)
    print("Simulating flaky API call...")

    recorder = AnthropicAPICallRecorder()
    # Temporarily make MockRateLimitError retryable
    test_config = AnthropicRetryConfig(
        max_retries=5,
        base_delay=0.1,  # Fast for demo
        retryable_types=[AnthropicErrorType.RATE_LIMIT, AnthropicErrorType.UNKNOWN]
    )

    try:
        result = retry_anthropic_call(
            flaky_api_call,
            config=test_config,
            on_retry=recorder.record_retry
        )
        print(f"\nResult: {result}")
        print(f"Total attempts: {call_count}")
        print(f"Retries recorded: {recorder.total_retries}")
        print(f"Retry delays: {[f'{d:.2f}s' for d in recorder.delays]}")
    except Exception as e:
        print(f"Failed: {e}")
