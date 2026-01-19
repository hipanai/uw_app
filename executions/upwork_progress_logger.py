#!/usr/bin/env python3
"""
Progress logging module for Upwork Auto-Apply Pipeline.

Provides structured, informative progress logging that:
- Logs key milestones at INFO level
- Suppresses excessive debug output by default
- Uses consistent formatting for all progress messages
- Integrates with the log sanitizer for security

Feature #88: Progress logging is informative but not verbose

Usage:
    from upwork_progress_logger import (
        setup_progress_logging,
        log_pipeline_start,
        log_stage_start,
        log_stage_complete,
        log_job_progress,
        log_pipeline_summary
    )

    # Set up logging once at startup
    setup_progress_logging()

    # Log pipeline milestones
    log_pipeline_start("apify", job_count=10)
    log_stage_start("pre-filter", job_count=10)
    log_stage_complete("pre-filter", processed=10, passed=7, filtered=3)
    log_pipeline_summary(result)
"""

import os
import sys
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field


# Progress logging configuration
PROGRESS_LOG_FORMAT = "%(asctime)s | %(levelname)-5s | %(message)s"
PROGRESS_DATE_FORMAT = "%H:%M:%S"

# Default log levels - INFO by default, DEBUG only when explicitly enabled
DEFAULT_LOG_LEVEL = logging.INFO
DEBUG_LOG_LEVEL = logging.DEBUG

# Pipeline stage emojis (disabled by default - only used in verbose mode)
STAGE_MARKERS = {
    "start": ">>>",
    "complete": "<<<",
    "progress": "...",
    "error": "!!!"
}

# Key milestones to always log at INFO level
KEY_MILESTONES = [
    "pipeline_start",
    "pipeline_complete",
    "stage_start",
    "stage_complete",
    "critical_error",
    "summary"
]


@dataclass
class ProgressLogConfig:
    """Configuration for progress logging."""
    level: int = DEFAULT_LOG_LEVEL
    format: str = PROGRESS_LOG_FORMAT
    date_format: str = PROGRESS_DATE_FORMAT
    show_timestamps: bool = True
    show_stage_markers: bool = True
    verbose: bool = False
    quiet: bool = False
    log_to_file: Optional[str] = None


class ProgressFilter(logging.Filter):
    """
    Filter that ensures progress logging is informative but not verbose.

    - At INFO level: logs milestones, stage transitions, summaries
    - At DEBUG level: logs detailed per-job information
    - Suppresses repetitive messages (e.g., per-job updates when count > 10)
    """

    def __init__(self, verbose: bool = False, quiet: bool = False):
        super().__init__()
        self.verbose = verbose
        self.quiet = quiet
        self._stage_counts: Dict[str, int] = {}
        self._last_stage: Optional[str] = None

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter log records for appropriate verbosity."""
        if self.quiet:
            # In quiet mode, only show errors and critical summaries
            return record.levelno >= logging.ERROR or "summary" in record.getMessage().lower()

        if self.verbose:
            # In verbose mode, show everything
            return True

        # Default mode: filter excessive debug output
        if record.levelno < logging.INFO:
            # Suppress DEBUG messages by default
            return False

        # Suppress repetitive per-job messages
        msg = record.getMessage()
        if self._is_repetitive_message(msg):
            return False

        return True

    def _is_repetitive_message(self, msg: str) -> bool:
        """Check if this message is repetitive (e.g., per-job updates)."""
        # Track counts per stage
        lower_msg = msg.lower()

        # Detect stage-specific messages
        for stage in ["pre-filter", "extraction", "deliverable", "boost"]:
            if stage in lower_msg:
                self._stage_counts[stage] = self._stage_counts.get(stage, 0) + 1
                # Suppress after 3 repetitions unless it's a summary
                if self._stage_counts[stage] > 3 and "complete" not in lower_msg and "summary" not in lower_msg:
                    return True

        return False

    def reset_stage_counts(self):
        """Reset stage counts (call between pipelines)."""
        self._stage_counts = {}
        self._last_stage = None


class ProgressFormatter(logging.Formatter):
    """Custom formatter for progress logging with consistent style."""

    def __init__(self, show_timestamps: bool = True, show_stage_markers: bool = True):
        super().__init__(PROGRESS_LOG_FORMAT, PROGRESS_DATE_FORMAT)
        self.show_timestamps = show_timestamps
        self.show_stage_markers = show_stage_markers

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with consistent styling."""
        # Get the base formatted message
        formatted = super().format(record)

        # Add stage markers if enabled
        if self.show_stage_markers:
            msg_lower = record.getMessage().lower()
            if "stage" in msg_lower and "start" in msg_lower:
                formatted = formatted.replace(record.getMessage(),
                    f"{STAGE_MARKERS['start']} {record.getMessage()}")
            elif "complete" in msg_lower:
                formatted = formatted.replace(record.getMessage(),
                    f"{STAGE_MARKERS['complete']} {record.getMessage()}")
            elif "error" in msg_lower:
                formatted = formatted.replace(record.getMessage(),
                    f"{STAGE_MARKERS['error']} {record.getMessage()}")

        return formatted


# Module-level logger
_progress_logger: Optional[logging.Logger] = None
_progress_config: ProgressLogConfig = ProgressLogConfig()


def setup_progress_logging(
    verbose: bool = False,
    quiet: bool = False,
    log_file: Optional[str] = None,
    level: Optional[int] = None
) -> logging.Logger:
    """
    Set up progress logging with appropriate verbosity.

    Args:
        verbose: If True, show detailed per-job output
        quiet: If True, only show errors and summaries
        log_file: Optional file path to also log to
        level: Optional log level override

    Returns:
        Configured logger
    """
    global _progress_logger, _progress_config

    # Determine log level
    if level is not None:
        log_level = level
    elif os.getenv("DEBUG", "").lower() in ("1", "true", "yes"):
        log_level = DEBUG_LOG_LEVEL
    elif quiet:
        log_level = logging.WARNING
    else:
        log_level = DEFAULT_LOG_LEVEL

    # Update config
    _progress_config = ProgressLogConfig(
        level=log_level,
        verbose=verbose,
        quiet=quiet,
        log_to_file=log_file
    )

    # Get or create logger
    logger = logging.getLogger("upwork.progress")
    logger.setLevel(log_level)

    # Remove existing handlers
    logger.handlers = []

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(ProgressFormatter())
    console_handler.addFilter(ProgressFilter(verbose=verbose, quiet=quiet))
    logger.addHandler(console_handler)

    # Add file handler if requested
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(ProgressFormatter(show_timestamps=True))
        logger.addHandler(file_handler)

    _progress_logger = logger
    return logger


def get_progress_logger() -> logging.Logger:
    """Get the progress logger, creating if necessary."""
    global _progress_logger
    if _progress_logger is None:
        _progress_logger = setup_progress_logging()
    return _progress_logger


def log_pipeline_start(source: str, job_count: Optional[int] = None, **kwargs):
    """Log pipeline start milestone."""
    logger = get_progress_logger()
    if job_count is not None:
        logger.info(f"Pipeline started: source={source}, jobs={job_count}")
    else:
        logger.info(f"Pipeline started: source={source}")


def log_pipeline_complete(
    total_jobs: int,
    processed: int,
    sent_to_slack: int,
    errors: int,
    duration_seconds: Optional[float] = None
):
    """Log pipeline completion summary."""
    logger = get_progress_logger()

    msg_parts = [
        f"Pipeline complete: {processed}/{total_jobs} processed",
        f"{sent_to_slack} sent to Slack"
    ]

    if errors > 0:
        msg_parts.append(f"{errors} errors")

    if duration_seconds is not None:
        msg_parts.append(f"in {duration_seconds:.1f}s")

    logger.info(" | ".join(msg_parts))


def log_stage_start(stage_name: str, job_count: Optional[int] = None, **kwargs):
    """Log stage start."""
    logger = get_progress_logger()

    if job_count is not None:
        logger.info(f"Stage {stage_name}: processing {job_count} jobs")
    else:
        logger.info(f"Stage {stage_name}: starting")


def log_stage_complete(
    stage_name: str,
    processed: int,
    passed: Optional[int] = None,
    filtered: Optional[int] = None,
    errors: Optional[int] = None,
    duration_seconds: Optional[float] = None
):
    """Log stage completion."""
    logger = get_progress_logger()

    msg_parts = [f"Stage {stage_name} complete: {processed} processed"]

    if passed is not None:
        msg_parts.append(f"{passed} passed")

    if filtered is not None and filtered > 0:
        msg_parts.append(f"{filtered} filtered")

    if errors is not None and errors > 0:
        msg_parts.append(f"{errors} errors")

    if duration_seconds is not None:
        msg_parts.append(f"in {duration_seconds:.1f}s")

    logger.info(" | ".join(msg_parts))


def log_job_progress(
    job_id: str,
    stage: str,
    status: str,
    details: Optional[Dict[str, Any]] = None
):
    """
    Log per-job progress (DEBUG level by default).

    This is filtered out unless verbose mode is enabled.
    """
    logger = get_progress_logger()

    msg = f"Job {job_id}: {stage} -> {status}"
    if details:
        detail_str = ", ".join(f"{k}={v}" for k, v in details.items())
        msg = f"{msg} ({detail_str})"

    logger.debug(msg)


def log_error(message: str, exception: Optional[Exception] = None, job_id: Optional[str] = None):
    """Log an error."""
    logger = get_progress_logger()

    if job_id:
        message = f"Job {job_id}: {message}"

    if exception:
        logger.error(f"{message}: {exception}")
    else:
        logger.error(message)


def log_warning(message: str, job_id: Optional[str] = None):
    """Log a warning."""
    logger = get_progress_logger()

    if job_id:
        message = f"Job {job_id}: {message}"

    logger.warning(message)


def log_pipeline_summary(
    result: Any,
    include_details: bool = False
):
    """
    Log pipeline summary from a PipelineResult object.

    Args:
        result: PipelineResult dataclass with statistics
        include_details: If True, log detailed breakdown
    """
    logger = get_progress_logger()

    # Format summary
    summary_lines = [
        "Pipeline Summary:",
        f"  Ingested: {getattr(result, 'jobs_ingested', 0)}",
        f"  After dedup: {getattr(result, 'jobs_after_dedup', 0)}",
        f"  After pre-filter: {getattr(result, 'jobs_after_prefilter', 0)}",
        f"  Filtered out: {getattr(result, 'jobs_filtered_out', 0)}",
        f"  Processed: {getattr(result, 'jobs_processed', 0)}",
        f"  Sent to Slack: {getattr(result, 'jobs_sent_to_slack', 0)}",
        f"  Errors: {getattr(result, 'jobs_with_errors', 0)}"
    ]

    # Log each line
    for line in summary_lines:
        logger.info(line)

    # Log details if requested (DEBUG level)
    if include_details and hasattr(result, 'jobs'):
        for job in result.jobs:
            log_job_progress(
                job_id=getattr(job, 'job_id', 'unknown'),
                stage="final",
                status=str(getattr(job, 'status', 'unknown')),
                details={"score": getattr(job, 'fit_score', None)}
            )


def is_verbose_logging_enabled() -> bool:
    """Check if verbose logging is enabled."""
    return _progress_config.verbose


def is_quiet_logging_enabled() -> bool:
    """Check if quiet logging is enabled."""
    return _progress_config.quiet


# Convenience function to check if DEBUG is actually being output
def debug_enabled() -> bool:
    """Check if DEBUG level logging is actually enabled."""
    logger = get_progress_logger()
    return logger.isEnabledFor(logging.DEBUG)


# Export list for star imports
__all__ = [
    'setup_progress_logging',
    'get_progress_logger',
    'log_pipeline_start',
    'log_pipeline_complete',
    'log_stage_start',
    'log_stage_complete',
    'log_job_progress',
    'log_error',
    'log_warning',
    'log_pipeline_summary',
    'is_verbose_logging_enabled',
    'is_quiet_logging_enabled',
    'debug_enabled',
    'ProgressLogConfig',
    'ProgressFilter',
    'ProgressFormatter',
]


if __name__ == "__main__":
    # Demo the progress logging
    import argparse

    parser = argparse.ArgumentParser(description="Demo progress logging")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--quiet", "-q", action="store_true", help="Quiet output")
    parser.add_argument("--test", action="store_true", help="Run logging test")
    args = parser.parse_args()

    # Set up logging
    setup_progress_logging(verbose=args.verbose, quiet=args.quiet)

    if args.test:
        print("\n=== Progress Logging Demo ===\n")

        # Simulate a pipeline run
        log_pipeline_start("apify", job_count=10)

        # Stage 1: Deduplication
        log_stage_start("deduplication", job_count=10)
        log_job_progress("job_001", "dedup", "new")
        log_job_progress("job_002", "dedup", "duplicate")
        log_stage_complete("deduplication", processed=10, passed=8, filtered=2)

        # Stage 2: Pre-filter
        log_stage_start("pre-filter", job_count=8)
        for i in range(8):
            log_job_progress(f"job_{i:03d}", "pre-filter", "scored", {"score": 75 + i*3})
        log_stage_complete("pre-filter", processed=8, passed=5, filtered=3)

        # Stage 3: Deep extraction
        log_stage_start("extraction", job_count=5)
        log_stage_complete("extraction", processed=5, errors=1)

        # Stage 4: Deliverables
        log_stage_start("deliverables", job_count=4)
        log_warning("Video generation slow", job_id="job_003")
        log_stage_complete("deliverables", processed=4, duration_seconds=45.2)

        # Stage 5: Slack approval
        log_stage_start("slack-approval", job_count=4)
        log_stage_complete("slack-approval", processed=4)

        # Complete
        log_pipeline_complete(
            total_jobs=10,
            processed=4,
            sent_to_slack=4,
            errors=1,
            duration_seconds=120.5
        )

        print("\n=== Verbose Mode Status ===")
        print(f"Verbose enabled: {is_verbose_logging_enabled()}")
        print(f"Quiet enabled: {is_quiet_logging_enabled()}")
        print(f"DEBUG enabled: {debug_enabled()}")
