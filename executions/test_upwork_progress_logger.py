#!/usr/bin/env python3
"""
Tests for upwork_progress_logger.py

Feature #88: Progress logging is informative but not verbose

Test coverage:
- Default logging level is INFO (not DEBUG)
- Key milestones are logged at INFO
- Per-job details are logged at DEBUG (suppressed by default)
- Verbose mode enables DEBUG output
- Quiet mode suppresses everything except errors/summaries
- Consistent formatting across all log messages
"""

import os
import sys
import io
import logging
import unittest
from unittest.mock import patch, MagicMock
from dataclasses import dataclass

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from upwork_progress_logger import (
    setup_progress_logging,
    get_progress_logger,
    log_pipeline_start,
    log_pipeline_complete,
    log_stage_start,
    log_stage_complete,
    log_job_progress,
    log_error,
    log_warning,
    log_pipeline_summary,
    is_verbose_logging_enabled,
    is_quiet_logging_enabled,
    debug_enabled,
    ProgressLogConfig,
    ProgressFilter,
    ProgressFormatter,
    PROGRESS_LOG_FORMAT,
    STAGE_MARKERS
)


class TestProgressLogConfig(unittest.TestCase):
    """Test ProgressLogConfig dataclass."""

    def test_default_config_values(self):
        """Test default configuration values."""
        config = ProgressLogConfig()
        self.assertEqual(config.level, logging.INFO)
        self.assertFalse(config.verbose)
        self.assertFalse(config.quiet)
        self.assertIsNone(config.log_to_file)

    def test_custom_config_values(self):
        """Test custom configuration values."""
        config = ProgressLogConfig(
            level=logging.DEBUG,
            verbose=True,
            quiet=False,
            log_to_file="/tmp/test.log"
        )
        self.assertEqual(config.level, logging.DEBUG)
        self.assertTrue(config.verbose)
        self.assertFalse(config.quiet)
        self.assertEqual(config.log_to_file, "/tmp/test.log")


class TestProgressFilter(unittest.TestCase):
    """Test ProgressFilter class."""

    def test_filter_allows_info_messages(self):
        """Test that INFO messages pass through by default."""
        filter = ProgressFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Stage complete", args=(), exc_info=None
        )
        self.assertTrue(filter.filter(record))

    def test_filter_suppresses_debug_by_default(self):
        """Test that DEBUG messages are suppressed by default."""
        filter = ProgressFilter(verbose=False)
        record = logging.LogRecord(
            name="test", level=logging.DEBUG, pathname="", lineno=0,
            msg="Debug message", args=(), exc_info=None
        )
        self.assertFalse(filter.filter(record))

    def test_filter_allows_debug_in_verbose_mode(self):
        """Test that DEBUG messages pass in verbose mode."""
        filter = ProgressFilter(verbose=True)
        record = logging.LogRecord(
            name="test", level=logging.DEBUG, pathname="", lineno=0,
            msg="Debug message", args=(), exc_info=None
        )
        self.assertTrue(filter.filter(record))

    def test_filter_quiet_mode_only_errors(self):
        """Test that quiet mode only allows errors and summaries."""
        filter = ProgressFilter(quiet=True)

        # INFO should be filtered in quiet mode
        info_record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Info message", args=(), exc_info=None
        )
        self.assertFalse(filter.filter(info_record))

        # ERROR should pass
        error_record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="", lineno=0,
            msg="Error message", args=(), exc_info=None
        )
        self.assertTrue(filter.filter(error_record))

        # Summary should pass even at INFO level
        summary_record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Pipeline Summary: 10 processed", args=(), exc_info=None
        )
        self.assertTrue(filter.filter(summary_record))

    def test_filter_suppresses_repetitive_messages(self):
        """Test that repetitive per-job messages are suppressed."""
        filter = ProgressFilter(verbose=False)

        # First few messages should pass
        for i in range(3):
            record = logging.LogRecord(
                name="test", level=logging.INFO, pathname="", lineno=0,
                msg=f"Pre-filter job_{i}", args=(), exc_info=None
            )
            self.assertTrue(filter.filter(record))

        # Fourth repetition should be suppressed
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Pre-filter job_3", args=(), exc_info=None
        )
        self.assertFalse(filter.filter(record))

    def test_filter_allows_completion_messages(self):
        """Test that completion messages always pass."""
        filter = ProgressFilter(verbose=False)

        # First exhaust the repetition limit
        for i in range(5):
            record = logging.LogRecord(
                name="test", level=logging.INFO, pathname="", lineno=0,
                msg=f"Pre-filter job_{i}", args=(), exc_info=None
            )
            filter.filter(record)

        # Completion message should still pass
        complete_record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Pre-filter complete: 5 jobs", args=(), exc_info=None
        )
        self.assertTrue(filter.filter(complete_record))

    def test_reset_stage_counts(self):
        """Test that stage counts can be reset."""
        filter = ProgressFilter()
        filter._stage_counts = {"pre-filter": 10}
        filter.reset_stage_counts()
        self.assertEqual(filter._stage_counts, {})


class TestProgressFormatter(unittest.TestCase):
    """Test ProgressFormatter class."""

    def test_formatter_basic_message(self):
        """Test basic message formatting."""
        formatter = ProgressFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Test message", args=(), exc_info=None
        )
        result = formatter.format(record)
        self.assertIn("INFO", result)
        self.assertIn("Test message", result)

    def test_formatter_adds_stage_start_marker(self):
        """Test that stage start messages get markers."""
        formatter = ProgressFormatter(show_stage_markers=True)
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Stage pre-filter start", args=(), exc_info=None
        )
        result = formatter.format(record)
        self.assertIn(STAGE_MARKERS['start'], result)

    def test_formatter_adds_complete_marker(self):
        """Test that completion messages get markers."""
        formatter = ProgressFormatter(show_stage_markers=True)
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Stage complete: 10 processed", args=(), exc_info=None
        )
        result = formatter.format(record)
        self.assertIn(STAGE_MARKERS['complete'], result)

    def test_formatter_adds_error_marker(self):
        """Test that error messages get markers."""
        formatter = ProgressFormatter(show_stage_markers=True)
        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="", lineno=0,
            msg="Error: failed to process", args=(), exc_info=None
        )
        result = formatter.format(record)
        self.assertIn(STAGE_MARKERS['error'], result)

    def test_formatter_without_markers(self):
        """Test formatting without stage markers."""
        formatter = ProgressFormatter(show_stage_markers=False)
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Stage pre-filter start", args=(), exc_info=None
        )
        result = formatter.format(record)
        self.assertNotIn(STAGE_MARKERS['start'], result)


class TestSetupProgressLogging(unittest.TestCase):
    """Test setup_progress_logging function."""

    def test_setup_returns_logger(self):
        """Test that setup returns a logger."""
        logger = setup_progress_logging()
        self.assertIsInstance(logger, logging.Logger)
        self.assertEqual(logger.name, "upwork.progress")

    def test_setup_default_level_is_info(self):
        """Test that default log level is INFO."""
        with patch.dict(os.environ, {"DEBUG": ""}, clear=False):
            logger = setup_progress_logging()
            self.assertEqual(logger.level, logging.INFO)

    def test_setup_debug_level_with_env(self):
        """Test that DEBUG env enables debug level."""
        with patch.dict(os.environ, {"DEBUG": "1"}):
            logger = setup_progress_logging()
            self.assertEqual(logger.level, logging.DEBUG)

    def test_setup_verbose_mode(self):
        """Test verbose mode configuration."""
        setup_progress_logging(verbose=True)
        self.assertTrue(is_verbose_logging_enabled())

    def test_setup_quiet_mode(self):
        """Test quiet mode configuration."""
        setup_progress_logging(quiet=True)
        self.assertTrue(is_quiet_logging_enabled())

    def test_setup_removes_existing_handlers(self):
        """Test that setup removes existing handlers."""
        logger = setup_progress_logging()
        original_handlers = len(logger.handlers)
        setup_progress_logging()  # Second setup
        self.assertEqual(len(logger.handlers), original_handlers)


class TestGetProgressLogger(unittest.TestCase):
    """Test get_progress_logger function."""

    def test_get_logger_returns_same_instance(self):
        """Test that get_logger returns consistent instance."""
        logger1 = get_progress_logger()
        logger2 = get_progress_logger()
        self.assertIs(logger1, logger2)


class TestLogPipelineStart(unittest.TestCase):
    """Test log_pipeline_start function."""

    def test_log_pipeline_start_with_job_count(self):
        """Test logging pipeline start with job count."""
        setup_progress_logging()
        logger = get_progress_logger()

        with patch.object(logger, 'info') as mock_info:
            log_pipeline_start("apify", job_count=10)
            mock_info.assert_called_once()
            call_args = mock_info.call_args[0][0]
            self.assertIn("apify", call_args)
            self.assertIn("10", call_args)

    def test_log_pipeline_start_without_job_count(self):
        """Test logging pipeline start without job count."""
        setup_progress_logging()
        logger = get_progress_logger()

        with patch.object(logger, 'info') as mock_info:
            log_pipeline_start("gmail")
            mock_info.assert_called_once()
            call_args = mock_info.call_args[0][0]
            self.assertIn("gmail", call_args)


class TestLogPipelineComplete(unittest.TestCase):
    """Test log_pipeline_complete function."""

    def test_log_complete_basic(self):
        """Test basic completion logging."""
        setup_progress_logging()
        logger = get_progress_logger()

        with patch.object(logger, 'info') as mock_info:
            log_pipeline_complete(
                total_jobs=10, processed=8,
                sent_to_slack=5, errors=2
            )
            mock_info.assert_called_once()
            call_args = mock_info.call_args[0][0]
            self.assertIn("8/10", call_args)
            self.assertIn("5", call_args)
            self.assertIn("2 errors", call_args)

    def test_log_complete_with_duration(self):
        """Test completion logging with duration."""
        setup_progress_logging()
        logger = get_progress_logger()

        with patch.object(logger, 'info') as mock_info:
            log_pipeline_complete(
                total_jobs=10, processed=8,
                sent_to_slack=5, errors=0,
                duration_seconds=45.5
            )
            call_args = mock_info.call_args[0][0]
            self.assertIn("45.5s", call_args)


class TestLogStageStartComplete(unittest.TestCase):
    """Test log_stage_start and log_stage_complete functions."""

    def test_log_stage_start_with_job_count(self):
        """Test stage start logging with job count."""
        setup_progress_logging()
        logger = get_progress_logger()

        with patch.object(logger, 'info') as mock_info:
            log_stage_start("pre-filter", job_count=15)
            call_args = mock_info.call_args[0][0]
            self.assertIn("pre-filter", call_args)
            self.assertIn("15", call_args)

    def test_log_stage_complete_with_all_fields(self):
        """Test stage completion with all fields."""
        setup_progress_logging()
        logger = get_progress_logger()

        with patch.object(logger, 'info') as mock_info:
            log_stage_complete(
                "pre-filter",
                processed=10, passed=7, filtered=3,
                errors=1, duration_seconds=2.5
            )
            call_args = mock_info.call_args[0][0]
            self.assertIn("pre-filter", call_args)
            self.assertIn("10", call_args)
            self.assertIn("7 passed", call_args)
            self.assertIn("3 filtered", call_args)
            self.assertIn("1 errors", call_args)
            self.assertIn("2.5s", call_args)


class TestLogJobProgress(unittest.TestCase):
    """Test log_job_progress function."""

    def test_log_job_progress_at_debug_level(self):
        """Test that job progress is logged at DEBUG level."""
        setup_progress_logging()
        logger = get_progress_logger()

        with patch.object(logger, 'debug') as mock_debug:
            log_job_progress("job_001", "pre-filter", "scored", {"score": 85})
            mock_debug.assert_called_once()
            call_args = mock_debug.call_args[0][0]
            self.assertIn("job_001", call_args)
            self.assertIn("pre-filter", call_args)
            self.assertIn("score=85", call_args)

    def test_log_job_progress_suppressed_by_default(self):
        """Test that job progress is suppressed by default (no verbose)."""
        # Set up with default (non-verbose) mode
        setup_progress_logging(verbose=False)

        # Job progress should be at DEBUG level, which is suppressed
        self.assertFalse(debug_enabled())


class TestLogErrorWarning(unittest.TestCase):
    """Test log_error and log_warning functions."""

    def test_log_error_basic(self):
        """Test basic error logging."""
        setup_progress_logging()
        logger = get_progress_logger()

        with patch.object(logger, 'error') as mock_error:
            log_error("Something went wrong")
            mock_error.assert_called_once_with("Something went wrong")

    def test_log_error_with_exception(self):
        """Test error logging with exception."""
        setup_progress_logging()
        logger = get_progress_logger()

        with patch.object(logger, 'error') as mock_error:
            log_error("Failed", exception=ValueError("test"))
            call_args = mock_error.call_args[0][0]
            self.assertIn("Failed", call_args)
            self.assertIn("test", call_args)

    def test_log_error_with_job_id(self):
        """Test error logging with job ID."""
        setup_progress_logging()
        logger = get_progress_logger()

        with patch.object(logger, 'error') as mock_error:
            log_error("API failed", job_id="job_001")
            call_args = mock_error.call_args[0][0]
            self.assertIn("job_001", call_args)

    def test_log_warning(self):
        """Test warning logging."""
        setup_progress_logging()
        logger = get_progress_logger()

        with patch.object(logger, 'warning') as mock_warning:
            log_warning("Rate limit approaching", job_id="job_002")
            call_args = mock_warning.call_args[0][0]
            self.assertIn("Rate limit", call_args)
            self.assertIn("job_002", call_args)


class TestLogPipelineSummary(unittest.TestCase):
    """Test log_pipeline_summary function."""

    def test_log_summary(self):
        """Test pipeline summary logging."""
        setup_progress_logging()
        logger = get_progress_logger()

        @dataclass
        class MockResult:
            jobs_ingested: int = 10
            jobs_after_dedup: int = 8
            jobs_after_prefilter: int = 5
            jobs_filtered_out: int = 3
            jobs_processed: int = 5
            jobs_sent_to_slack: int = 5
            jobs_with_errors: int = 0

        with patch.object(logger, 'info') as mock_info:
            log_pipeline_summary(MockResult())
            # Should log multiple lines
            self.assertTrue(mock_info.call_count >= 8)


class TestFeature88DefaultLoggingLevel(unittest.TestCase):
    """Test Feature #88: Default logging level is INFO, not DEBUG."""

    def test_default_level_is_info(self):
        """Verify default log level is INFO."""
        with patch.dict(os.environ, {"DEBUG": ""}, clear=False):
            logger = setup_progress_logging()
            self.assertEqual(logger.level, logging.INFO)

    def test_debug_messages_not_shown_by_default(self):
        """Verify DEBUG messages are not output by default."""
        with patch.dict(os.environ, {"DEBUG": ""}, clear=False):
            setup_progress_logging(verbose=False)
            self.assertFalse(debug_enabled())


class TestFeature88KeyMilestonesLogged(unittest.TestCase):
    """Test Feature #88: Key milestones are logged at INFO level."""

    def test_pipeline_start_is_info_level(self):
        """Verify pipeline start is logged at INFO."""
        setup_progress_logging()
        logger = get_progress_logger()

        with patch.object(logger, 'info') as mock_info:
            log_pipeline_start("apify", job_count=10)
            mock_info.assert_called()

    def test_stage_start_is_info_level(self):
        """Verify stage start is logged at INFO."""
        setup_progress_logging()
        logger = get_progress_logger()

        with patch.object(logger, 'info') as mock_info:
            log_stage_start("pre-filter", job_count=10)
            mock_info.assert_called()

    def test_stage_complete_is_info_level(self):
        """Verify stage complete is logged at INFO."""
        setup_progress_logging()
        logger = get_progress_logger()

        with patch.object(logger, 'info') as mock_info:
            log_stage_complete("pre-filter", processed=10, passed=7)
            mock_info.assert_called()

    def test_pipeline_complete_is_info_level(self):
        """Verify pipeline complete is logged at INFO."""
        setup_progress_logging()
        logger = get_progress_logger()

        with patch.object(logger, 'info') as mock_info:
            log_pipeline_complete(10, 8, 5, 0)
            mock_info.assert_called()


class TestFeature88NoExcessiveDebugOutput(unittest.TestCase):
    """Test Feature #88: No excessive debug output by default."""

    def test_job_progress_at_debug_level(self):
        """Verify per-job progress is at DEBUG level (suppressed by default)."""
        setup_progress_logging()
        logger = get_progress_logger()

        with patch.object(logger, 'debug') as mock_debug:
            log_job_progress("job_001", "stage", "status")
            mock_debug.assert_called()

    def test_repetitive_messages_suppressed(self):
        """Verify repetitive messages are filtered after threshold."""
        filter = ProgressFilter(verbose=False)

        # Simulate repetitive messages
        for i in range(10):
            record = logging.LogRecord(
                name="test", level=logging.INFO, pathname="", lineno=0,
                msg=f"Pre-filter processing job_{i}", args=(), exc_info=None
            )
            result = filter.filter(record)
            if i >= 3:
                # After 3 repetitions, should be suppressed
                self.assertFalse(result, f"Message {i} should be suppressed")


class TestFeature88ConsistentFormatting(unittest.TestCase):
    """Test Feature #88: Consistent logging format."""

    def test_format_includes_timestamp(self):
        """Verify format includes timestamp."""
        self.assertIn("asctime", PROGRESS_LOG_FORMAT)

    def test_format_includes_level(self):
        """Verify format includes log level."""
        self.assertIn("levelname", PROGRESS_LOG_FORMAT)

    def test_format_includes_message(self):
        """Verify format includes message."""
        self.assertIn("message", PROGRESS_LOG_FORMAT)

    def test_stage_markers_defined(self):
        """Verify stage markers are defined consistently."""
        self.assertIn("start", STAGE_MARKERS)
        self.assertIn("complete", STAGE_MARKERS)
        self.assertIn("error", STAGE_MARKERS)


class TestIntegration(unittest.TestCase):
    """Integration tests for the full logging flow."""

    def test_full_pipeline_logging_flow(self):
        """Test a complete pipeline logging flow."""
        # Capture log output
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        handler.setLevel(logging.INFO)

        logger = setup_progress_logging()
        logger.addHandler(handler)

        # Simulate pipeline
        log_pipeline_start("apify", job_count=10)
        log_stage_start("deduplication", job_count=10)
        log_stage_complete("deduplication", processed=10, passed=8)
        log_stage_start("pre-filter", job_count=8)
        log_stage_complete("pre-filter", processed=8, passed=5, filtered=3)
        log_pipeline_complete(10, 5, 5, 0, duration_seconds=30.0)

        # Check output
        log_output = output.getvalue()
        self.assertIn("apify", log_output)
        self.assertIn("deduplication", log_output)
        self.assertIn("pre-filter", log_output)
        self.assertIn("complete", log_output.lower())

    def test_verbose_mode_shows_debug(self):
        """Test that verbose mode shows DEBUG messages."""
        setup_progress_logging(verbose=True)
        self.assertTrue(is_verbose_logging_enabled())

        # In verbose mode, debug should be enabled through the filter
        # (even if logger level is INFO, filter allows DEBUG)

    def test_quiet_mode_suppresses_info(self):
        """Test that quiet mode suppresses INFO messages."""
        setup_progress_logging(quiet=True)
        self.assertTrue(is_quiet_logging_enabled())


if __name__ == "__main__":
    unittest.main()
