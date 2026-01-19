#!/usr/bin/env python3
"""
Tests for Feature #85: Slack messages use consistent formatting

Verifies:
- Consistent header format across multiple messages
- Consistent button layout
- Consistent color scheme
- Consistent spacing and dividers
"""

import os
import sys
import json
import unittest
from datetime import datetime

# Add executions to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from upwork_slack_approval import (
    JobApprovalData,
    build_approval_blocks,
    build_status_update_blocks,
    get_score_color,
    get_score_emoji,
    format_budget,
    format_client_info,
    SLACK_MESSAGE_FORMAT,
    validate_message_format,
    send_approval_message,
    SlackMessageResult,
)


class TestSlackMessageFormatConstants(unittest.TestCase):
    """Test that formatting constants are defined and consistent."""

    def test_format_constants_exist(self):
        """Test that SLACK_MESSAGE_FORMAT constants are defined."""
        self.assertIsNotNone(SLACK_MESSAGE_FORMAT)
        self.assertIsInstance(SLACK_MESSAGE_FORMAT, dict)

    def test_format_has_header_config(self):
        """Test that header configuration is defined."""
        self.assertIn("header", SLACK_MESSAGE_FORMAT)
        self.assertIn("emoji", SLACK_MESSAGE_FORMAT["header"])
        self.assertIn("max_length", SLACK_MESSAGE_FORMAT["header"])

    def test_format_has_button_config(self):
        """Test that button configuration is defined."""
        self.assertIn("buttons", SLACK_MESSAGE_FORMAT)
        buttons = SLACK_MESSAGE_FORMAT["buttons"]
        self.assertIn("approve", buttons)
        self.assertIn("edit", buttons)
        self.assertIn("reject", buttons)

    def test_format_has_color_config(self):
        """Test that color configuration is defined."""
        self.assertIn("colors", SLACK_MESSAGE_FORMAT)
        colors = SLACK_MESSAGE_FORMAT["colors"]
        self.assertIn("excellent", colors)  # score >= 85
        self.assertIn("good", colors)       # score >= 70
        self.assertIn("low", colors)        # score < 70
        self.assertIn("unknown", colors)    # score is None

    def test_format_has_section_order(self):
        """Test that section order is defined."""
        self.assertIn("section_order", SLACK_MESSAGE_FORMAT)
        order = SLACK_MESSAGE_FORMAT["section_order"]
        self.assertIsInstance(order, list)
        self.assertIn("header", order)
        self.assertIn("budget_score", order)
        self.assertIn("actions", order)


class TestConsistentHeaderFormat(unittest.TestCase):
    """Test Feature #85: Consistent header format."""

    def setUp(self):
        """Create test jobs with varying data."""
        self.job1 = JobApprovalData(
            job_id="~job1",
            title="Build AI Pipeline for Data Processing",
            url="https://upwork.com/jobs/~job1",
            fit_score=90
        )
        self.job2 = JobApprovalData(
            job_id="~job2",
            title="Create Machine Learning Model",
            url="https://upwork.com/jobs/~job2",
            fit_score=75
        )
        self.job3 = JobApprovalData(
            job_id="~job3",
            title="Simple Python Script",
            url="https://upwork.com/jobs/~job3",
            fit_score=50
        )

    def test_header_has_consistent_emoji(self):
        """Test that all headers use the same emoji prefix."""
        blocks1 = build_approval_blocks(self.job1)
        blocks2 = build_approval_blocks(self.job2)
        blocks3 = build_approval_blocks(self.job3)

        header1 = next(b for b in blocks1 if b.get("type") == "header")
        header2 = next(b for b in blocks2 if b.get("type") == "header")
        header3 = next(b for b in blocks3 if b.get("type") == "header")

        expected_emoji = SLACK_MESSAGE_FORMAT["header"]["emoji"]

        self.assertTrue(header1["text"]["text"].startswith(expected_emoji))
        self.assertTrue(header2["text"]["text"].startswith(expected_emoji))
        self.assertTrue(header3["text"]["text"].startswith(expected_emoji))

    def test_header_has_consistent_type(self):
        """Test that all headers use plain_text type."""
        for job in [self.job1, self.job2, self.job3]:
            blocks = build_approval_blocks(job)
            header = next(b for b in blocks if b.get("type") == "header")

            self.assertEqual(header["text"]["type"], "plain_text")
            self.assertTrue(header["text"].get("emoji", True))

    def test_header_respects_max_length(self):
        """Test that headers respect max length."""
        max_len = SLACK_MESSAGE_FORMAT["header"]["max_length"]

        long_title_job = JobApprovalData(
            job_id="~longtest",
            title="A" * 200,  # Very long title
            url="https://upwork.com/jobs/~longtest"
        )

        blocks = build_approval_blocks(long_title_job)
        header = next(b for b in blocks if b.get("type") == "header")

        # Header text should be truncated
        self.assertLessEqual(len(header["text"]["text"]), max_len + 10)  # Some buffer for emoji/ellipsis

    def test_header_format_includes_job_prefix(self):
        """Test that header includes 'New Job:' prefix consistently."""
        for job in [self.job1, self.job2, self.job3]:
            blocks = build_approval_blocks(job)
            header = next(b for b in blocks if b.get("type") == "header")

            self.assertIn("New Job:", header["text"]["text"])


class TestConsistentButtonLayout(unittest.TestCase):
    """Test Feature #85: Consistent button layout."""

    def setUp(self):
        """Create test jobs."""
        self.job1 = JobApprovalData(
            job_id="~btn1", title="Job 1", url="", fit_score=90
        )
        self.job2 = JobApprovalData(
            job_id="~btn2", title="Job 2", url="", fit_score=50
        )

    def test_buttons_appear_in_consistent_order(self):
        """Test that buttons always appear in the same order: Approve, Edit, Reject."""
        expected_order = ["approve_job", "edit_job", "reject_job"]

        for job in [self.job1, self.job2]:
            blocks = build_approval_blocks(job)
            actions_block = next(b for b in blocks if b.get("type") == "actions")
            elements = actions_block.get("elements", [])

            action_ids = [e.get("action_id") for e in elements]
            self.assertEqual(action_ids, expected_order)

    def test_approve_button_has_consistent_style(self):
        """Test that Approve button always uses primary style."""
        for job in [self.job1, self.job2]:
            blocks = build_approval_blocks(job)
            actions_block = next(b for b in blocks if b.get("type") == "actions")
            approve_btn = next(e for e in actions_block["elements"] if e["action_id"] == "approve_job")

            self.assertEqual(approve_btn.get("style"), "primary")
            self.assertEqual(approve_btn["text"]["text"], SLACK_MESSAGE_FORMAT["buttons"]["approve"]["text"])

    def test_edit_button_has_consistent_style(self):
        """Test that Edit button has no special style (default)."""
        for job in [self.job1, self.job2]:
            blocks = build_approval_blocks(job)
            actions_block = next(b for b in blocks if b.get("type") == "actions")
            edit_btn = next(e for e in actions_block["elements"] if e["action_id"] == "edit_job")

            # Edit button should not have a style (default)
            self.assertNotIn("style", edit_btn)
            self.assertEqual(edit_btn["text"]["text"], SLACK_MESSAGE_FORMAT["buttons"]["edit"]["text"])

    def test_reject_button_has_consistent_style(self):
        """Test that Reject button always uses danger style."""
        for job in [self.job1, self.job2]:
            blocks = build_approval_blocks(job)
            actions_block = next(b for b in blocks if b.get("type") == "actions")
            reject_btn = next(e for e in actions_block["elements"] if e["action_id"] == "reject_job")

            self.assertEqual(reject_btn.get("style"), "danger")
            self.assertEqual(reject_btn["text"]["text"], SLACK_MESSAGE_FORMAT["buttons"]["reject"]["text"])

    def test_button_text_includes_emoji(self):
        """Test that button text includes appropriate emojis."""
        blocks = build_approval_blocks(self.job1)
        actions_block = next(b for b in blocks if b.get("type") == "actions")

        for element in actions_block["elements"]:
            text = element["text"]["text"]
            # All buttons should have emojis
            self.assertTrue(
                any(c for c in text if ord(c) > 127),  # Contains non-ASCII (emoji)
                f"Button '{element['action_id']}' missing emoji"
            )


class TestConsistentColorScheme(unittest.TestCase):
    """Test Feature #85: Consistent color scheme."""

    def test_color_consistency_for_scores(self):
        """Test that same score always produces same color."""
        colors_config = SLACK_MESSAGE_FORMAT["colors"]

        # Test multiple times to ensure consistency
        for _ in range(3):
            self.assertEqual(get_score_color(90), colors_config["excellent"])
            self.assertEqual(get_score_color(85), colors_config["excellent"])
            self.assertEqual(get_score_color(75), colors_config["good"])
            self.assertEqual(get_score_color(70), colors_config["good"])
            self.assertEqual(get_score_color(50), colors_config["low"])
            self.assertEqual(get_score_color(None), colors_config["unknown"])

    def test_emoji_consistency_for_scores(self):
        """Test that same score always produces same emoji."""
        emojis_config = SLACK_MESSAGE_FORMAT["emojis"]

        for _ in range(3):
            self.assertEqual(get_score_emoji(90), emojis_config["excellent"])
            self.assertEqual(get_score_emoji(85), emojis_config["excellent"])
            self.assertEqual(get_score_emoji(75), emojis_config["good"])
            self.assertEqual(get_score_emoji(70), emojis_config["good"])
            self.assertEqual(get_score_emoji(50), emojis_config["low"])
            self.assertEqual(get_score_emoji(None), emojis_config["unknown"])

    def test_score_thresholds_are_defined(self):
        """Test that score thresholds are clearly defined."""
        thresholds = SLACK_MESSAGE_FORMAT["score_thresholds"]

        self.assertIn("excellent", thresholds)
        self.assertIn("good", thresholds)

        # Excellent should be higher than good
        self.assertGreater(thresholds["excellent"], thresholds["good"])


class TestConsistentSectionOrder(unittest.TestCase):
    """Test that message sections appear in consistent order."""

    def test_dividers_appear_consistently(self):
        """Test that dividers separate content sections consistently."""
        job = JobApprovalData(
            job_id="~test",
            title="Test Job",
            url="https://upwork.com/jobs/~test",
            fit_score=85,
            proposal_text="Test proposal",
            boost_decision=True,
            boost_reasoning="Good client"
        )

        blocks = build_approval_blocks(job)
        block_types = [b.get("type") for b in blocks]

        # Should have at least 2 dividers (before proposal and before actions)
        divider_count = block_types.count("divider")
        self.assertGreaterEqual(divider_count, 2)

    def test_header_comes_first(self):
        """Test that header is always the first block."""
        job = JobApprovalData(
            job_id="~test",
            title="Test Job",
            url=""
        )

        blocks = build_approval_blocks(job)
        self.assertEqual(blocks[0].get("type"), "header")

    def test_actions_come_near_end(self):
        """Test that action buttons appear near the end."""
        job = JobApprovalData(
            job_id="~test",
            title="Test Job",
            url=""
        )

        blocks = build_approval_blocks(job)
        block_types = [b.get("type") for b in blocks]

        actions_index = block_types.index("actions")
        # Actions should be in the last 3 blocks
        self.assertGreaterEqual(actions_index, len(blocks) - 3)

    def test_footer_context_comes_last(self):
        """Test that footer context (job ID, timestamp) comes last."""
        job = JobApprovalData(
            job_id="~test123",
            title="Test Job",
            url=""
        )

        blocks = build_approval_blocks(job)
        last_block = blocks[-1]

        self.assertEqual(last_block.get("type"), "context")
        # Should contain job ID
        text = last_block["elements"][0].get("text", "")
        self.assertIn("~test123", text)


class TestMessageFormatValidation(unittest.TestCase):
    """Test the validate_message_format function."""

    def test_validate_valid_blocks(self):
        """Test that valid blocks pass validation."""
        job = JobApprovalData(
            job_id="~valid",
            title="Valid Job",
            url="https://upwork.com/jobs/~valid",
            fit_score=80
        )

        blocks = build_approval_blocks(job)
        validation_result = validate_message_format(blocks)

        self.assertTrue(validation_result["valid"])
        self.assertEqual(len(validation_result["errors"]), 0)

    def test_validate_checks_header_presence(self):
        """Test that validation fails without header."""
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": "No header"}}
        ]

        validation_result = validate_message_format(blocks)
        self.assertFalse(validation_result["valid"])
        self.assertTrue(any("header" in e.lower() for e in validation_result["errors"]))

    def test_validate_checks_actions_presence(self):
        """Test that validation fails without actions."""
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": "Test"}}
        ]

        validation_result = validate_message_format(blocks)
        self.assertFalse(validation_result["valid"])
        self.assertTrue(any("actions" in e.lower() for e in validation_result["errors"]))

    def test_validate_checks_button_count(self):
        """Test that validation checks for correct number of buttons."""
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": "Test"}},
            {
                "type": "actions",
                "elements": [
                    {"type": "button", "action_id": "approve_job", "text": {"type": "plain_text", "text": "Approve"}}
                    # Missing edit and reject buttons
                ]
            }
        ]

        validation_result = validate_message_format(blocks)
        self.assertFalse(validation_result["valid"])
        self.assertTrue(any("button" in e.lower() for e in validation_result["errors"]))


class TestStatusUpdateConsistency(unittest.TestCase):
    """Test consistent formatting for status update messages."""

    def test_approved_status_has_consistent_format(self):
        """Test approved status message format."""
        job = JobApprovalData(
            job_id="~test",
            title="Test Job",
            url="https://upwork.com/jobs/~test"
        )

        blocks = build_status_update_blocks(job, "approved", "U12345")

        header = next(b for b in blocks if b.get("type") == "header")
        self.assertIn("APPROVED", header["text"]["text"])
        self.assertIn(SLACK_MESSAGE_FORMAT["status_emojis"]["approved"], header["text"]["text"])

    def test_rejected_status_has_consistent_format(self):
        """Test rejected status message format."""
        job = JobApprovalData(
            job_id="~test",
            title="Test Job",
            url="https://upwork.com/jobs/~test"
        )

        blocks = build_status_update_blocks(job, "rejected", "U12345")

        header = next(b for b in blocks if b.get("type") == "header")
        self.assertIn("REJECTED", header["text"]["text"])
        self.assertIn(SLACK_MESSAGE_FORMAT["status_emojis"]["rejected"], header["text"]["text"])

    def test_status_updates_include_user_attribution(self):
        """Test that status updates attribute the action to the user."""
        job = JobApprovalData(
            job_id="~test",
            title="Test Job",
            url=""
        )

        for status in ["approved", "rejected"]:
            blocks = build_status_update_blocks(job, status, "U12345")

            # Find section with user attribution
            user_found = False
            for block in blocks:
                if block.get("type") == "section":
                    text = block.get("text", {}).get("text", "")
                    if "<@U12345>" in text:
                        user_found = True
                        break

            self.assertTrue(user_found, f"User attribution not found for {status} status")


class TestMultipleMessagesConsistency(unittest.TestCase):
    """Test that multiple messages generated simultaneously are consistent."""

    def test_batch_messages_have_identical_structure(self):
        """Test that messages generated in batch have identical structure."""
        jobs = [
            JobApprovalData(
                job_id=f"~batch{i}",
                title=f"Batch Job {i}",
                url=f"https://upwork.com/jobs/~batch{i}",
                fit_score=70 + i * 5
            )
            for i in range(5)
        ]

        # Generate all blocks
        all_blocks = [build_approval_blocks(job) for job in jobs]

        # Extract structure (just types)
        structures = [[b.get("type") for b in blocks] for blocks in all_blocks]

        # All structures should be identical (same sections in same order)
        for structure in structures[1:]:
            self.assertEqual(structure, structures[0])

    def test_batch_messages_have_consistent_action_ids(self):
        """Test that action IDs follow consistent pattern."""
        jobs = [
            JobApprovalData(
                job_id=f"~id{i}",
                title=f"Job {i}",
                url=""
            )
            for i in range(3)
        ]

        for job in jobs:
            blocks = build_approval_blocks(job)
            actions_block = next(b for b in blocks if b.get("type") == "actions")

            # block_id should include job_id for uniqueness
            self.assertIn(job.job_id, actions_block.get("block_id", ""))


class TestClientInfoFormatting(unittest.TestCase):
    """Test consistent client info formatting."""

    def test_client_info_separator_is_consistent(self):
        """Test that client info uses consistent separator."""
        job = JobApprovalData(
            job_id="~test",
            title="Test",
            url="",
            client_country="USA",
            client_spent=10000,
            client_hires=5,
            payment_verified=True
        )

        info = format_client_info(job)
        # Should use pipe separator consistently
        self.assertIn(" | ", info)

    def test_client_info_order_is_consistent(self):
        """Test that client info fields appear in consistent order."""
        job = JobApprovalData(
            job_id="~test",
            title="Test",
            url="",
            client_country="USA",
            client_spent=10000,
            client_hires=5,
            payment_verified=True
        )

        info = format_client_info(job)
        parts = info.split(" | ")

        # Order: country, spent, hires, verification
        self.assertIn("USA", parts[0])  # Country first
        self.assertIn("spent", parts[1].lower())  # Spent second
        self.assertIn("hires", parts[2].lower())  # Hires third
        self.assertIn("erified", parts[3])  # Verified last


class TestBudgetFormatting(unittest.TestCase):
    """Test consistent budget formatting."""

    def test_fixed_budget_format_consistent(self):
        """Test that fixed budget uses consistent format."""
        job = JobApprovalData(
            job_id="~test",
            title="Test",
            url="",
            budget_type="fixed",
            budget_min=1000,
            budget_max=2000
        )

        budget = format_budget(job)
        self.assertTrue(budget.startswith("Fixed:"))
        self.assertIn("$", budget)

    def test_hourly_budget_format_consistent(self):
        """Test that hourly budget uses consistent format."""
        job = JobApprovalData(
            job_id="~test",
            title="Test",
            url="",
            budget_type="hourly",
            budget_min=25,
            budget_max=50
        )

        budget = format_budget(job)
        self.assertTrue(budget.startswith("Hourly:"))
        self.assertIn("/hr", budget)


class TestFeature86FitScoreColorCoding(unittest.TestCase):
    """Test Feature #86: Slack messages display fit score with color coding.

    Verifies:
    1. Messages with score 90 get green color indicator
    2. Messages with score 72 get yellow color indicator
    3. Messages with score 50 get red color indicator
    4. Messages with no score get gray color indicator
    """

    def test_score_90_gets_green_color(self):
        """Test that a fit score of 90 produces green color."""
        score_color = get_score_color(90)
        expected_green = SLACK_MESSAGE_FORMAT["colors"]["excellent"]

        self.assertEqual(score_color, expected_green)
        self.assertEqual(score_color, "#36a64f")  # Explicit hex verification

    def test_score_85_gets_green_color(self):
        """Test that a fit score of 85 (threshold) produces green color."""
        score_color = get_score_color(85)
        expected_green = SLACK_MESSAGE_FORMAT["colors"]["excellent"]

        self.assertEqual(score_color, expected_green)

    def test_score_72_gets_yellow_color(self):
        """Test that a fit score of 72 produces yellow/amber color."""
        score_color = get_score_color(72)
        expected_yellow = SLACK_MESSAGE_FORMAT["colors"]["good"]

        self.assertEqual(score_color, expected_yellow)
        self.assertEqual(score_color, "#ffc107")  # Explicit hex verification

    def test_score_70_gets_yellow_color(self):
        """Test that a fit score of 70 (threshold) produces yellow/amber color."""
        score_color = get_score_color(70)
        expected_yellow = SLACK_MESSAGE_FORMAT["colors"]["good"]

        self.assertEqual(score_color, expected_yellow)

    def test_score_50_gets_red_color(self):
        """Test that a fit score of 50 produces red color."""
        score_color = get_score_color(50)
        expected_red = SLACK_MESSAGE_FORMAT["colors"]["low"]

        self.assertEqual(score_color, expected_red)
        self.assertEqual(score_color, "#dc3545")  # Explicit hex verification

    def test_score_none_gets_gray_color(self):
        """Test that no fit score produces gray color."""
        score_color = get_score_color(None)
        expected_gray = SLACK_MESSAGE_FORMAT["colors"]["unknown"]

        self.assertEqual(score_color, expected_gray)
        self.assertEqual(score_color, "#808080")  # Explicit hex verification

    def test_score_0_gets_red_color(self):
        """Test that a fit score of 0 produces red color."""
        score_color = get_score_color(0)
        expected_red = SLACK_MESSAGE_FORMAT["colors"]["low"]

        self.assertEqual(score_color, expected_red)

    def test_score_100_gets_green_color(self):
        """Test that a fit score of 100 produces green color."""
        score_color = get_score_color(100)
        expected_green = SLACK_MESSAGE_FORMAT["colors"]["excellent"]

        self.assertEqual(score_color, expected_green)

    def test_score_69_gets_red_color(self):
        """Test that a fit score of 69 (just below good threshold) produces red color."""
        score_color = get_score_color(69)
        expected_red = SLACK_MESSAGE_FORMAT["colors"]["low"]

        self.assertEqual(score_color, expected_red)

    def test_score_84_gets_yellow_color(self):
        """Test that a fit score of 84 (just below excellent threshold) produces yellow color."""
        score_color = get_score_color(84)
        expected_yellow = SLACK_MESSAGE_FORMAT["colors"]["good"]

        self.assertEqual(score_color, expected_yellow)

    def test_color_constants_are_valid_hex(self):
        """Test that all color constants are valid hex color codes."""
        colors = SLACK_MESSAGE_FORMAT["colors"]

        for name, color in colors.items():
            self.assertTrue(
                color.startswith("#"),
                f"Color '{name}' should start with #"
            )
            self.assertEqual(
                len(color), 7,
                f"Color '{name}' should be 7 characters (including #)"
            )
            # Verify it's valid hex
            try:
                int(color[1:], 16)
            except ValueError:
                self.fail(f"Color '{name}' ({color}) is not valid hex")


class TestFeature86SendApprovalMessageColor(unittest.TestCase):
    """Test that send_approval_message includes color in result."""

    def test_send_approval_message_returns_color_for_score_90(self):
        """Test that sending a message for score 90 returns green color."""
        try:
            from upwork_slack_approval import send_approval_message
        except ImportError:
            self.skipTest("send_approval_message not available")

        job = JobApprovalData(
            job_id="~test90",
            title="High Score Job",
            url="https://upwork.com/jobs/~test90",
            fit_score=90
        )

        result = send_approval_message(
            job=job,
            channel="C0123456789",
            mock=True
        )

        self.assertTrue(result.success)
        self.assertIsNotNone(result.color)
        self.assertEqual(result.color, SLACK_MESSAGE_FORMAT["colors"]["excellent"])
        self.assertEqual(result.color, "#36a64f")

    def test_send_approval_message_returns_color_for_score_72(self):
        """Test that sending a message for score 72 returns yellow color."""
        try:
            from upwork_slack_approval import send_approval_message
        except ImportError:
            self.skipTest("send_approval_message not available")

        job = JobApprovalData(
            job_id="~test72",
            title="Medium Score Job",
            url="https://upwork.com/jobs/~test72",
            fit_score=72
        )

        result = send_approval_message(
            job=job,
            channel="C0123456789",
            mock=True
        )

        self.assertTrue(result.success)
        self.assertIsNotNone(result.color)
        self.assertEqual(result.color, SLACK_MESSAGE_FORMAT["colors"]["good"])
        self.assertEqual(result.color, "#ffc107")

    def test_send_approval_message_returns_color_for_score_50(self):
        """Test that sending a message for score 50 returns red color."""
        try:
            from upwork_slack_approval import send_approval_message
        except ImportError:
            self.skipTest("send_approval_message not available")

        job = JobApprovalData(
            job_id="~test50",
            title="Low Score Job",
            url="https://upwork.com/jobs/~test50",
            fit_score=50
        )

        result = send_approval_message(
            job=job,
            channel="C0123456789",
            mock=True
        )

        self.assertTrue(result.success)
        self.assertIsNotNone(result.color)
        self.assertEqual(result.color, SLACK_MESSAGE_FORMAT["colors"]["low"])
        self.assertEqual(result.color, "#dc3545")

    def test_send_approval_message_returns_color_for_no_score(self):
        """Test that sending a message without score returns gray color."""
        try:
            from upwork_slack_approval import send_approval_message
        except ImportError:
            self.skipTest("send_approval_message not available")

        job = JobApprovalData(
            job_id="~testnone",
            title="No Score Job",
            url="https://upwork.com/jobs/~testnone",
            fit_score=None
        )

        result = send_approval_message(
            job=job,
            channel="C0123456789",
            mock=True
        )

        self.assertTrue(result.success)
        self.assertIsNotNone(result.color)
        self.assertEqual(result.color, SLACK_MESSAGE_FORMAT["colors"]["unknown"])
        self.assertEqual(result.color, "#808080")


class TestFeature86SlackMessageResultColor(unittest.TestCase):
    """Test SlackMessageResult includes color field."""

    def test_slack_message_result_has_color_field(self):
        """Test that SlackMessageResult dataclass has color field."""
        try:
            from upwork_slack_approval import SlackMessageResult
        except ImportError:
            self.skipTest("SlackMessageResult not available")

        result = SlackMessageResult(
            success=True,
            message_ts="1234567890.123456",
            channel="C0123456789",
            color="#36a64f"
        )

        self.assertEqual(result.color, "#36a64f")

    def test_slack_message_result_to_dict_includes_color(self):
        """Test that to_dict includes color in output."""
        try:
            from upwork_slack_approval import SlackMessageResult
        except ImportError:
            self.skipTest("SlackMessageResult not available")

        result = SlackMessageResult(
            success=True,
            message_ts="1234567890.123456",
            channel="C0123456789",
            color="#ffc107"
        )

        result_dict = result.to_dict()

        self.assertIn("color", result_dict)
        self.assertEqual(result_dict["color"], "#ffc107")

    def test_slack_message_result_color_is_optional(self):
        """Test that color field is optional (defaults to None)."""
        try:
            from upwork_slack_approval import SlackMessageResult
        except ImportError:
            self.skipTest("SlackMessageResult not available")

        result = SlackMessageResult(
            success=True,
            message_ts="1234567890.123456",
            channel="C0123456789"
        )

        self.assertIsNone(result.color)


class TestFeature86EmojiIndicators(unittest.TestCase):
    """Test emoji indicators match color coding."""

    def test_score_90_gets_green_emoji(self):
        """Test that a fit score of 90 produces green emoji."""
        score_emoji = get_score_emoji(90)
        expected_emoji = SLACK_MESSAGE_FORMAT["emojis"]["excellent"]

        self.assertEqual(score_emoji, expected_emoji)
        self.assertEqual(score_emoji, "🟢")

    def test_score_72_gets_yellow_emoji(self):
        """Test that a fit score of 72 produces yellow emoji."""
        score_emoji = get_score_emoji(72)
        expected_emoji = SLACK_MESSAGE_FORMAT["emojis"]["good"]

        self.assertEqual(score_emoji, expected_emoji)
        self.assertEqual(score_emoji, "🟡")

    def test_score_50_gets_red_emoji(self):
        """Test that a fit score of 50 produces red emoji."""
        score_emoji = get_score_emoji(50)
        expected_emoji = SLACK_MESSAGE_FORMAT["emojis"]["low"]

        self.assertEqual(score_emoji, expected_emoji)
        self.assertEqual(score_emoji, "🔴")

    def test_score_none_gets_white_emoji(self):
        """Test that no fit score produces white/gray emoji."""
        score_emoji = get_score_emoji(None)
        expected_emoji = SLACK_MESSAGE_FORMAT["emojis"]["unknown"]

        self.assertEqual(score_emoji, expected_emoji)
        self.assertEqual(score_emoji, "⚪")


class TestFeature86MessageBlocksIncludeScoreEmoji(unittest.TestCase):
    """Test that message blocks include score emoji display."""

    def test_blocks_include_score_with_emoji(self):
        """Test that build_approval_blocks includes score with emoji."""
        job = JobApprovalData(
            job_id="~test",
            title="Test Job",
            url="https://upwork.com/jobs/~test",
            fit_score=90
        )

        blocks = build_approval_blocks(job)

        # Find the score section
        score_found = False
        for block in blocks:
            if block.get("type") == "section" and "fields" in block:
                for field in block.get("fields", []):
                    text = field.get("text", "")
                    if "Fit Score" in text and "90" in text:
                        # Should have green emoji
                        self.assertIn("🟢", text)
                        score_found = True

        self.assertTrue(score_found, "Score with emoji not found in blocks")

    def test_blocks_show_low_score_with_red_emoji(self):
        """Test that low score shows red emoji in blocks."""
        job = JobApprovalData(
            job_id="~test",
            title="Test Job",
            url="https://upwork.com/jobs/~test",
            fit_score=50
        )

        blocks = build_approval_blocks(job)

        # Find the score section
        score_found = False
        for block in blocks:
            if block.get("type") == "section" and "fields" in block:
                for field in block.get("fields", []):
                    text = field.get("text", "")
                    if "Fit Score" in text and "50" in text:
                        # Should have red emoji
                        self.assertIn("🔴", text)
                        score_found = True

        self.assertTrue(score_found, "Score with emoji not found in blocks")


if __name__ == "__main__":
    unittest.main(verbosity=2)
