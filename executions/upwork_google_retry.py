#!/usr/bin/env python3
"""
Upwork Google API Retry Logic

Implements exponential backoff retry logic for Google API calls (Docs, Drive, Sheets).

Feature #96: Retry logic with exponential backoff for Google Docs

Configuration:
- Default base delay: 1.5 seconds
- Default max retries: 4
- Exponential backoff: delay = base_delay * (2 ** attempt)
  - Attempt 0: 1.5s
  - Attempt 1: 3.0s
  - Attempt 2: 6.0s
  - Attempt 3: 12.0s

Usage:
    from upwork_google_retry import with_retry, GoogleRetryConfig

    # Using decorator
    @with_retry()
    def create_document():
        docs_service.documents().create(...)

    # Using wrapper function
    result = retry_google_api_call(
        lambda: docs_service.documents().create(...).execute()
    )

    # Custom config
    config = GoogleRetryConfig(max_retries=5, base_delay=2.0)
    result = retry_google_api_call(my_func, config=config)
"""

import time
import functools
import logging
from dataclasses import dataclass, field
from typing import Callable, TypeVar, Optional, List, Any

# Configure logging
logger = logging.getLogger(__name__)

# Type variable for generic return type
T = TypeVar('T')


@dataclass
class GoogleRetryConfig:
    """Configuration for Google API retry behavior."""
    max_retries: int = 4
    base_delay: float = 1.5  # seconds
    max_delay: float = 60.0  # cap the maximum delay
    retryable_exceptions: tuple = field(default_factory=lambda: (
        Exception,  # Catch all for Google API errors
    ))
    # Specific HTTP status codes to retry on
    retryable_status_codes: List[int] = field(default_factory=lambda: [
        429,  # Too Many Requests
        500,  # Internal Server Error
        502,  # Bad Gateway
        503,  # Service Unavailable
        504,  # Gateway Timeout
    ])

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for a given attempt (0-indexed)."""
        delay = self.base_delay * (2 ** attempt)
        return min(delay, self.max_delay)


@dataclass
class RetryResult:
    """Result of a retry operation."""
    success: bool
    result: Any = None
    error: Optional[Exception] = None
    attempts: int = 0
    total_delay: float = 0.0
    retry_delays: List[float] = field(default_factory=list)


def is_retryable_error(error: Exception, config: GoogleRetryConfig) -> bool:
    """
    Check if an error should trigger a retry.

    Args:
        error: The exception that occurred
        config: Retry configuration

    Returns:
        True if the error is retryable
    """
    # Check for Google API HTTP errors
    if hasattr(error, 'resp') and hasattr(error.resp, 'status'):
        return error.resp.status in config.retryable_status_codes

    # Check for common retryable error messages
    error_str = str(error).lower()
    retryable_messages = [
        'ssl',
        'connection reset',
        'timeout',
        'rate limit',
        'quota exceeded',
        'service unavailable',
        'internal error',
        'socket',
        'connection aborted',
        'connection refused',
    ]

    for msg in retryable_messages:
        if msg in error_str:
            return True

    return False


def retry_google_api_call(
    func: Callable[[], T],
    config: Optional[GoogleRetryConfig] = None,
    on_retry: Optional[Callable[[int, Exception, float], None]] = None
) -> T:
    """
    Execute a Google API call with exponential backoff retry.

    Args:
        func: The function to call (should be a lambda or callable with no args)
        config: Retry configuration (uses defaults if not provided)
        on_retry: Optional callback called on each retry with (attempt, error, delay)

    Returns:
        The result of the function call

    Raises:
        The last exception if all retries are exhausted
    """
    if config is None:
        config = GoogleRetryConfig()

    last_error = None

    for attempt in range(config.max_retries):
        try:
            return func()
        except Exception as e:
            last_error = e

            # Check if this is the last attempt
            if attempt == config.max_retries - 1:
                logger.error(f"Google API call failed after {config.max_retries} attempts: {e}")
                raise

            # Check if error is retryable
            if not is_retryable_error(e, config):
                logger.warning(f"Non-retryable error, not retrying: {e}")
                raise

            # Calculate and apply delay
            delay = config.get_delay(attempt)
            logger.warning(
                f"Google API call attempt {attempt + 1} failed, "
                f"retrying in {delay:.1f}s: {e}"
            )

            if on_retry:
                on_retry(attempt, e, delay)

            time.sleep(delay)

    # Should not reach here, but just in case
    if last_error:
        raise last_error
    raise RuntimeError("Unexpected state in retry logic")


def with_retry(
    config: Optional[GoogleRetryConfig] = None,
    on_retry: Optional[Callable[[int, Exception, float], None]] = None
):
    """
    Decorator to add retry logic to a function.

    Args:
        config: Retry configuration
        on_retry: Optional callback called on each retry

    Usage:
        @with_retry()
        def create_document():
            return docs_service.documents().create(...).execute()
    """
    if config is None:
        config = GoogleRetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            return retry_google_api_call(
                lambda: func(*args, **kwargs),
                config=config,
                on_retry=on_retry
            )
        return wrapper
    return decorator


def retry_google_api_call_with_result(
    func: Callable[[], T],
    config: Optional[GoogleRetryConfig] = None,
    on_retry: Optional[Callable[[int, Exception, float], None]] = None
) -> RetryResult:
    """
    Execute a Google API call with retry and return detailed result.

    Unlike retry_google_api_call, this doesn't raise exceptions.
    Instead, it returns a RetryResult with success/error information.

    Args:
        func: The function to call
        config: Retry configuration
        on_retry: Optional callback called on each retry

    Returns:
        RetryResult with success, result/error, and retry statistics
    """
    if config is None:
        config = GoogleRetryConfig()

    result = RetryResult(success=False)

    for attempt in range(config.max_retries):
        try:
            result.result = func()
            result.success = True
            result.attempts = attempt + 1
            return result
        except Exception as e:
            result.error = e
            result.attempts = attempt + 1

            # Check if this is the last attempt
            if attempt == config.max_retries - 1:
                logger.error(f"Google API call failed after {config.max_retries} attempts: {e}")
                return result

            # Check if error is retryable
            if not is_retryable_error(e, config):
                logger.warning(f"Non-retryable error, not retrying: {e}")
                return result

            # Calculate and apply delay
            delay = config.get_delay(attempt)
            result.retry_delays.append(delay)
            result.total_delay += delay

            logger.warning(
                f"Google API call attempt {attempt + 1} failed, "
                f"retrying in {delay:.1f}s: {e}"
            )

            if on_retry:
                on_retry(attempt, e, delay)

            time.sleep(delay)

    return result


class GoogleAPICallRecorder:
    """
    Test helper to record API call attempts and delays.

    Usage in tests:
        recorder = GoogleAPICallRecorder()

        @with_retry(on_retry=recorder.record_retry)
        def my_api_call():
            ...

        # Check recorded data
        assert recorder.total_attempts == 3
        assert recorder.delays == [1.5, 3.0]
    """

    def __init__(self):
        self.attempts: List[int] = []
        self.delays: List[float] = []
        self.errors: List[Exception] = []

    def record_retry(self, attempt: int, error: Exception, delay: float):
        """Record a retry attempt."""
        self.attempts.append(attempt)
        self.errors.append(error)
        self.delays.append(delay)

    @property
    def total_retries(self) -> int:
        """Total number of retries (not including initial attempt)."""
        return len(self.attempts)

    def reset(self):
        """Reset all recorded data."""
        self.attempts.clear()
        self.delays.clear()
        self.errors.clear()


# Convenience functions with pre-configured settings

def retry_docs_api(func: Callable[[], T]) -> T:
    """Retry a Google Docs API call with default settings."""
    return retry_google_api_call(func)


def retry_drive_api(func: Callable[[], T]) -> T:
    """Retry a Google Drive API call with default settings."""
    return retry_google_api_call(func)


def retry_sheets_api(func: Callable[[], T]) -> T:
    """Retry a Google Sheets API call with default settings."""
    return retry_google_api_call(func)


if __name__ == "__main__":
    # Demo/test the retry logic
    import random

    config = GoogleRetryConfig()
    print(f"Retry Configuration:")
    print(f"  Max retries: {config.max_retries}")
    print(f"  Base delay: {config.base_delay}s")
    print(f"  Delays: {[config.get_delay(i) for i in range(config.max_retries)]}")

    # Simulate a function that fails a few times then succeeds
    call_count = 0

    def flaky_api_call():
        global call_count
        call_count += 1
        if call_count < 3:
            raise Exception("SSL connection reset")
        return "success!"

    recorder = GoogleAPICallRecorder()
    result = retry_google_api_call(flaky_api_call, on_retry=recorder.record_retry)

    print(f"\nResult: {result}")
    print(f"Total attempts: {call_count}")
    print(f"Retries recorded: {recorder.total_retries}")
    print(f"Retry delays: {recorder.delays}")
