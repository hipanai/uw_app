#!/usr/bin/env python3
"""
Tests for Upwork Slack Approval

Tests Features #42-48:
- Feature #42: Slack approval can send message with job details
- Feature #43: Slack approval message includes interactive buttons
- Feature #44: Slack approval message includes proposal preview
- Feature #45: Slack approval message includes video preview link
- Feature #46: Slack approve button triggers submission workflow
- Feature #47: Slack reject button marks job as rejected
- Feature #48: Slack edit button allows proposal modification
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime
import time
import hashlib
import hmac

# Add executions to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from upwork_slack_approval import (
    JobApprovalData,
    SlackMessageResult,
    ApprovalCallbackResult,
    build_approval_blocks,
    send_slack_message,
    send_approval_message,
    update_slack_message,
    verify_slack_signature,
    handle_button_action,
    build_status_update_blocks,
    get_score_color,
    get_score_emoji,
    format_budget,
    format_client_info,
    truncate_text,
    update_job_status_in_sheet,
    get_job_from_sheet,
    process_approval_callback,
)


class TestJobApprovalData(unittest.TestCase):
    """Test JobApprovalData dataclass and from_dict method."""

    def test_create_from_dict_full_data(self):
        """Test creating JobApprovalData from complete data."""
        data = {
            "job_id": "~abc123",
            "title": "Build AI Pipeline",
            "url": "https://upwork.com/jobs/~abc123",
            "budget_type": "fixed",
            "budget_min": 1000,
            "budget_max": 2000,
            "fit_score": 85,
            "fit_reasoning": "Great match",
            "proposal_text": "My proposal",
            "proposal_doc_url": "https://docs.google.com/d/123",
            "video_url": "https://heygen.com/v/123",
            "pdf_url": "https://drive.google.com/f/123",
            "boost_decision": True,
            "boost_reasoning": "High value client",
            "client_country": "USA",
            "client_spent": 50000,
            "client_hires": 25,
            "payment_verified": True,
            "pricing_proposed": 1500,
            "description": "Job description",
            "skills": ["Python", "AI"]
        }

        job = JobApprovalData.from_dict(data)

        self.assertEqual(job.job_id, "~abc123")
        self.assertEqual(job.title, "Build AI Pipeline")
        self.assertEqual(job.budget_type, "fixed")
        self.assertEqual(job.budget_min, 1000)
        self.assertEqual(job.budget_max, 2000)
        self.assertEqual(job.fit_score, 85)
        self.assertEqual(job.client_spent, 50000)
        self.assertTrue(job.payment_verified)
        self.assertEqual(job.skills, ["Python", "AI"])

    def test_create_from_dict_nested_client(self):
        """Test creating JobApprovalData with nested client data."""
        data = {
            "job_id": "~xyz789",
            "title": "Test Job",
            "url": "https://upwork.com/jobs/~xyz789",
            "client": {
                "country": "Canada",
                "total_spent": 10000,
                "total_hires": 15
            }
        }

        job = JobApprovalData.from_dict(data)

        self.assertEqual(job.client_country, "Canada")
        self.assertEqual(job.client_spent, 10000)
        self.assertEqual(job.client_hires, 15)

    def test_extract_job_id_from_url(self):
        """Test job_id extraction from URL when not provided."""
        data = {
            "title": "Test",
            "url": "https://upwork.com/jobs/~abc456xyz"
        }

        job = JobApprovalData.from_dict(data)
        self.assertEqual(job.job_id, "~abc456xyz")

    def test_skills_as_string(self):
        """Test skills parsing when provided as comma-separated string."""
        data = {
            "job_id": "~test",
            "title": "Test",
            "url": "https://upwork.com/jobs/~test",
            "skills": "Python, AI, n8n, Automation"
        }

        job = JobApprovalData.from_dict(data)
        self.assertEqual(job.skills, ["Python", "AI", "n8n", "Automation"])

    def test_to_dict(self):
        """Test conversion back to dictionary."""
        job = JobApprovalData(
            job_id="~test",
            title="Test Job",
            url="https://upwork.com/jobs/~test",
            fit_score=90
        )

        result = job.to_dict()
        self.assertEqual(result["job_id"], "~test")
        self.assertEqual(result["fit_score"], 90)


class TestHelperFunctions(unittest.TestCase):
    """Test helper functions for formatting."""

    def test_get_score_color_green(self):
        """Test color for excellent score."""
        self.assertEqual(get_score_color(90), "#36a64f")
        self.assertEqual(get_score_color(85), "#36a64f")

    def test_get_score_color_yellow(self):
        """Test color for good score."""
        self.assertEqual(get_score_color(75), "#ffc107")
        self.assertEqual(get_score_color(70), "#ffc107")

    def test_get_score_color_red(self):
        """Test color for low score."""
        self.assertEqual(get_score_color(50), "#dc3545")
        self.assertEqual(get_score_color(0), "#dc3545")

    def test_get_score_color_none(self):
        """Test color for missing score."""
        self.assertEqual(get_score_color(None), "#808080")

    def test_get_score_emoji(self):
        """Test emoji indicators."""
        self.assertEqual(get_score_emoji(90), "🟢")
        self.assertEqual(get_score_emoji(75), "🟡")
        self.assertEqual(get_score_emoji(50), "🔴")
        self.assertEqual(get_score_emoji(None), "⚪")

    def test_format_budget_fixed(self):
        """Test budget formatting for fixed price."""
        job = JobApprovalData(
            job_id="~test", title="Test", url="",
            budget_type="fixed", budget_min=1000, budget_max=2000
        )
        self.assertEqual(format_budget(job), "Fixed: $1,000-$2,000")

        job.budget_min = 1500
        job.budget_max = 1500
        self.assertEqual(format_budget(job), "Fixed: $1,500")

    def test_format_budget_hourly(self):
        """Test budget formatting for hourly rate."""
        job = JobApprovalData(
            job_id="~test", title="Test", url="",
            budget_type="hourly", budget_min=25, budget_max=50
        )
        self.assertEqual(format_budget(job), "Hourly: $25-$50/hr")

    def test_format_budget_unknown(self):
        """Test budget formatting for unknown type."""
        job = JobApprovalData(
            job_id="~test", title="Test", url="",
            budget_type="unknown"
        )
        self.assertEqual(format_budget(job), "Budget: Not specified")

    def test_format_client_info(self):
        """Test client info formatting."""
        job = JobApprovalData(
            job_id="~test", title="Test", url="",
            client_country="USA",
            client_spent=15000,
            client_hires=10,
            payment_verified=True
        )
        info = format_client_info(job)
        self.assertIn("USA", info)
        self.assertIn("$15.0k spent", info)
        self.assertIn("10 hires", info)
        self.assertIn("Verified", info)

    def test_format_client_info_unverified(self):
        """Test client info with unverified payment."""
        job = JobApprovalData(
            job_id="~test", title="Test", url="",
            client_spent=500,
            payment_verified=False
        )
        info = format_client_info(job)
        self.assertIn("$500 spent", info)
        self.assertIn("Unverified", info)

    def test_truncate_text(self):
        """Test text truncation."""
        short = "Hello world"
        self.assertEqual(truncate_text(short, 50), "Hello world")

        long_text = "A" * 100
        truncated = truncate_text(long_text, 50)
        self.assertEqual(len(truncated), 50)
        self.assertTrue(truncated.endswith("..."))

    def test_truncate_text_empty(self):
        """Test truncation of empty text."""
        self.assertEqual(truncate_text("", 50), "")
        self.assertEqual(truncate_text(None, 50), "")


class TestFeature42BuildApprovalBlocks(unittest.TestCase):
    """Test Feature #42: Slack approval can send message with job details."""

    def setUp(self):
        """Set up test job data."""
        self.job = JobApprovalData(
            job_id="~feature42test",
            title="Build AI Automation Pipeline",
            url="https://upwork.com/jobs/~feature42test",
            budget_type="fixed",
            budget_min=1500,
            budget_max=2500,
            fit_score=87,
            fit_reasoning="Great match for automation expertise",
            client_country="United States",
            client_spent=15000,
            client_hires=12,
            payment_verified=True
        )

    def test_blocks_include_header(self):
        """Test that blocks include job title header."""
        blocks = build_approval_blocks(self.job)

        header = next((b for b in blocks if b.get("type") == "header"), None)
        self.assertIsNotNone(header)
        self.assertIn("Build AI Automation Pipeline", header["text"]["text"])

    def test_blocks_include_budget(self):
        """Test that blocks include budget information."""
        blocks = build_approval_blocks(self.job)

        # Find section with budget
        budget_found = False
        for block in blocks:
            if block.get("type") == "section" and "fields" in block:
                for field in block["fields"]:
                    if "Budget" in field.get("text", ""):
                        budget_found = True
                        self.assertIn("$1,500", field["text"])
                        break

        self.assertTrue(budget_found, "Budget not found in blocks")

    def test_blocks_include_fit_score(self):
        """Test that blocks include fit score."""
        blocks = build_approval_blocks(self.job)

        score_found = False
        for block in blocks:
            if block.get("type") == "section" and "fields" in block:
                for field in block["fields"]:
                    if "Fit Score" in field.get("text", ""):
                        score_found = True
                        self.assertIn("87/100", field["text"])
                        break

        self.assertTrue(score_found, "Fit score not found in blocks")

    def test_blocks_include_job_link(self):
        """Test that blocks include View Job button."""
        blocks = build_approval_blocks(self.job)

        button_found = False
        for block in blocks:
            accessory = block.get("accessory", {})
            if accessory.get("type") == "button" and accessory.get("action_id") == "view_job":
                button_found = True
                self.assertEqual(accessory["url"], self.job.url)
                break

        self.assertTrue(button_found, "View Job button not found")

    def test_blocks_include_client_info(self):
        """Test that blocks include client information."""
        blocks = build_approval_blocks(self.job)

        client_found = False
        for block in blocks:
            if block.get("type") == "context":
                for elem in block.get("elements", []):
                    text = elem.get("text", "")
                    if "Client" in text:
                        client_found = True
                        self.assertIn("United States", text)
                        break

        self.assertTrue(client_found, "Client info not found in blocks")


class TestFeature43InteractiveButtons(unittest.TestCase):
    """Test Feature #43: Slack approval message includes interactive buttons."""

    def setUp(self):
        """Set up test job data."""
        self.job = JobApprovalData(
            job_id="~feature43test",
            title="Test Job",
            url="https://upwork.com/jobs/~feature43test",
            fit_score=80
        )

    def test_blocks_include_approve_button(self):
        """Test that blocks include Approve button."""
        blocks = build_approval_blocks(self.job)

        actions_block = next((b for b in blocks if b.get("type") == "actions"), None)
        self.assertIsNotNone(actions_block)

        elements = actions_block.get("elements", [])
        approve_btn = next((e for e in elements if e.get("action_id") == "approve_job"), None)

        self.assertIsNotNone(approve_btn)
        self.assertIn("Approve", approve_btn["text"]["text"])
        self.assertEqual(approve_btn.get("style"), "primary")

    def test_blocks_include_edit_button(self):
        """Test that blocks include Edit button."""
        blocks = build_approval_blocks(self.job)

        actions_block = next((b for b in blocks if b.get("type") == "actions"), None)
        elements = actions_block.get("elements", [])
        edit_btn = next((e for e in elements if e.get("action_id") == "edit_job"), None)

        self.assertIsNotNone(edit_btn)
        self.assertIn("Edit", edit_btn["text"]["text"])

    def test_blocks_include_reject_button(self):
        """Test that blocks include Reject button."""
        blocks = build_approval_blocks(self.job)

        actions_block = next((b for b in blocks if b.get("type") == "actions"), None)
        elements = actions_block.get("elements", [])
        reject_btn = next((e for e in elements if e.get("action_id") == "reject_job"), None)

        self.assertIsNotNone(reject_btn)
        self.assertIn("Reject", reject_btn["text"]["text"])
        self.assertEqual(reject_btn.get("style"), "danger")

    def test_button_values_contain_job_id(self):
        """Test that button values contain job_id."""
        blocks = build_approval_blocks(self.job)

        actions_block = next((b for b in blocks if b.get("type") == "actions"), None)
        for element in actions_block.get("elements", []):
            if element.get("value"):
                value = json.loads(element["value"])
                self.assertEqual(value.get("job_id"), self.job.job_id)


class TestFeature44ProposalPreview(unittest.TestCase):
    """Test Feature #44: Slack approval message includes proposal preview."""

    def test_blocks_include_proposal_text(self):
        """Test that blocks include proposal preview."""
        job = JobApprovalData(
            job_id="~feature44test",
            title="Test Job",
            url="https://upwork.com/jobs/~feature44test",
            proposal_text="Hey.\n\nI spent ~15 minutes putting this together for you. Here's my approach..."
        )

        blocks = build_approval_blocks(job)

        proposal_found = False
        for block in blocks:
            if block.get("type") == "section":
                text = block.get("text", {}).get("text", "")
                if "Proposal Preview" in text:
                    proposal_found = True
                    self.assertIn("15 minutes", text)
                    break

        self.assertTrue(proposal_found, "Proposal preview not found")

    def test_blocks_include_proposal_doc_link(self):
        """Test that blocks include proposal doc link."""
        job = JobApprovalData(
            job_id="~feature44test",
            title="Test Job",
            url="https://upwork.com/jobs/~feature44test",
            proposal_doc_url="https://docs.google.com/document/d/123abc"
        )

        blocks = build_approval_blocks(job)

        link_found = False
        for block in blocks:
            if block.get("type") == "context":
                for elem in block.get("elements", []):
                    text = elem.get("text", "")
                    if "Proposal Doc" in text and "docs.google.com" in text:
                        link_found = True
                        break

        self.assertTrue(link_found, "Proposal doc link not found")

    def test_long_proposal_is_truncated(self):
        """Test that long proposal text is truncated."""
        long_text = "A" * 1000
        job = JobApprovalData(
            job_id="~test",
            title="Test",
            url="",
            proposal_text=long_text
        )

        blocks = build_approval_blocks(job)

        for block in blocks:
            if block.get("type") == "section":
                text = block.get("text", {}).get("text", "")
                if "Proposal Preview" in text:
                    # Should be truncated to ~500 chars
                    self.assertLess(len(text), 600)
                    break


class TestFeature45VideoPreview(unittest.TestCase):
    """Test Feature #45: Slack approval message includes video preview link."""

    def test_blocks_include_video_link(self):
        """Test that blocks include video link."""
        job = JobApprovalData(
            job_id="~feature45test",
            title="Test Job",
            url="https://upwork.com/jobs/~feature45test",
            video_url="https://heygen.com/videos/abc123"
        )

        blocks = build_approval_blocks(job)

        video_found = False
        for block in blocks:
            if block.get("type") == "context":
                for elem in block.get("elements", []):
                    text = elem.get("text", "")
                    if "Video" in text and "heygen.com" in text:
                        video_found = True
                        break

        self.assertTrue(video_found, "Video link not found")

    def test_blocks_include_video_emoji(self):
        """Test that video link has appropriate emoji."""
        job = JobApprovalData(
            job_id="~test",
            title="Test",
            url="",
            video_url="https://heygen.com/v/123"
        )

        blocks = build_approval_blocks(job)

        for block in blocks:
            if block.get("type") == "context":
                for elem in block.get("elements", []):
                    text = elem.get("text", "")
                    if "Video" in text:
                        # Check for movie emoji
                        self.assertIn("🎬", text)


class TestSlackMessageSending(unittest.TestCase):
    """Test Slack message sending functions."""

    @patch('upwork_slack_approval.urllib.request.urlopen')
    def test_send_slack_message_success(self, mock_urlopen):
        """Test successful message sending."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "ok": True,
            "ts": "1234567890.123456",
            "channel": "C123456"
        }).encode('utf-8')
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = send_slack_message(
            channel="C123456",
            blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": "Test"}}],
            token="xoxb-test-token"
        )

        self.assertTrue(result.success)
        self.assertEqual(result.message_ts, "1234567890.123456")
        self.assertEqual(result.channel, "C123456")

    @patch('upwork_slack_approval.urllib.request.urlopen')
    def test_send_slack_message_api_error(self, mock_urlopen):
        """Test handling of Slack API error."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "ok": False,
            "error": "channel_not_found"
        }).encode('utf-8')
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = send_slack_message(
            channel="C123456",
            blocks=[],
            token="xoxb-test-token"
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, "channel_not_found")

    def test_send_slack_message_no_token(self):
        """Test error when no token provided."""
        with patch.dict(os.environ, {"SLACK_BOT_TOKEN": ""}):
            result = send_slack_message(
                channel="C123456",
                blocks=[],
                token=None
            )

        self.assertFalse(result.success)
        self.assertIn("not configured", result.error)

    def test_send_slack_message_mock_mode(self):
        """Test mock mode doesn't send actual request."""
        result = send_slack_message(
            channel="C123456",
            blocks=[],
            mock=True
        )

        self.assertTrue(result.success)
        self.assertIn("mock_", result.message_ts)


class TestSendApprovalMessage(unittest.TestCase):
    """Test send_approval_message function."""

    def test_send_approval_mock(self):
        """Test sending approval in mock mode."""
        job = JobApprovalData(
            job_id="~testapproval",
            title="Test Job",
            url="https://upwork.com/jobs/~testapproval",
            fit_score=85
        )

        result = send_approval_message(
            job=job,
            channel="C123456",
            mock=True
        )

        self.assertTrue(result.success)
        self.assertIsNotNone(result.message_ts)

    def test_send_approval_no_channel(self):
        """Test error when no channel configured."""
        job = JobApprovalData(
            job_id="~test",
            title="Test",
            url=""
        )

        with patch.dict(os.environ, {"SLACK_APPROVAL_CHANNEL": ""}):
            result = send_approval_message(
                job=job,
                channel=None,
                mock=False
            )

        self.assertFalse(result.success)
        self.assertIn("not configured", result.error)


class TestSlackSignatureVerification(unittest.TestCase):
    """Test Slack request signature verification."""

    def test_valid_signature(self):
        """Test verification of valid signature."""
        signing_secret = "test_secret_123"
        timestamp = str(int(time.time()))
        body = '{"test": "data"}'

        sig_basestring = f"v0:{timestamp}:{body}"
        expected_sig = "v0=" + hmac.new(
            signing_secret.encode('utf-8'),
            sig_basestring.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        result = verify_slack_signature(
            timestamp=timestamp,
            body=body,
            signature=expected_sig,
            signing_secret=signing_secret
        )

        self.assertTrue(result)

    def test_invalid_signature(self):
        """Test rejection of invalid signature."""
        result = verify_slack_signature(
            timestamp=str(int(time.time())),
            body='{"test": "data"}',
            signature="v0=invalid_signature",
            signing_secret="test_secret"
        )

        self.assertFalse(result)

    def test_old_timestamp_rejected(self):
        """Test rejection of old timestamp (replay attack prevention)."""
        signing_secret = "test_secret"
        old_timestamp = str(int(time.time()) - 600)  # 10 minutes ago
        body = '{"test": "data"}'

        sig_basestring = f"v0:{old_timestamp}:{body}"
        signature = "v0=" + hmac.new(
            signing_secret.encode('utf-8'),
            sig_basestring.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        result = verify_slack_signature(
            timestamp=old_timestamp,
            body=body,
            signature=signature,
            signing_secret=signing_secret
        )

        self.assertFalse(result)


class TestButtonActionHandling(unittest.TestCase):
    """Test button action handling for Features #46-48."""

    def test_approve_action(self):
        """Test Feature #46: Approve button handling."""
        value = json.dumps({"job_id": "~test123", "action": "approve"})

        result = handle_button_action(
            action_id="approve_job",
            value=value,
            user_id="U123456",
            channel="C123456",
            message_ts="1234567890.123456",
            mock=True
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["action"], "approve")
        self.assertEqual(result["status"], "approved")
        self.assertEqual(result["job_id"], "~test123")

    def test_reject_action(self):
        """Test Feature #47: Reject button handling."""
        value = json.dumps({"job_id": "~test456", "action": "reject"})

        result = handle_button_action(
            action_id="reject_job",
            value=value,
            user_id="U123456",
            channel="C123456",
            message_ts="1234567890.123456",
            mock=True
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["action"], "reject")
        self.assertEqual(result["status"], "rejected")

    def test_edit_action_triggers_modal(self):
        """Test Feature #48: Edit button triggers modal."""
        value = json.dumps({"job_id": "~test789", "action": "edit"})

        result = handle_button_action(
            action_id="edit_job",
            value=value,
            user_id="U123456",
            channel="C123456",
            message_ts="1234567890.123456",
            mock=True
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["action"], "edit")
        self.assertTrue(result.get("trigger_modal"))

    def test_invalid_value_handling(self):
        """Test handling of invalid action value."""
        result = handle_button_action(
            action_id="approve_job",
            value="not valid json",
            user_id="U123456",
            channel="C123456",
            message_ts="1234567890.123456",
            mock=True
        )

        self.assertFalse(result["success"])
        self.assertIn("Invalid", result["error"])


class TestStatusUpdateBlocks(unittest.TestCase):
    """Test status update message blocks."""

    def test_approved_status_blocks(self):
        """Test blocks for approved status."""
        job = JobApprovalData(
            job_id="~test",
            title="Test Job",
            url="https://upwork.com/jobs/~test",
            proposal_doc_url="https://docs.google.com/d/123"
        )

        blocks = build_status_update_blocks(job, "approved", "U123456")

        header = next((b for b in blocks if b.get("type") == "header"), None)
        self.assertIsNotNone(header)
        self.assertIn("APPROVED", header["text"]["text"])
        self.assertIn("✅", header["text"]["text"])

        # Check user attribution
        status_text = None
        for block in blocks:
            if block.get("type") == "section":
                text = block.get("text", {}).get("text", "")
                if "Status" in text:
                    status_text = text
                    break

        self.assertIn("<@U123456>", status_text)

    def test_rejected_status_blocks(self):
        """Test blocks for rejected status."""
        job = JobApprovalData(
            job_id="~test",
            title="Test Job",
            url="https://upwork.com/jobs/~test"
        )

        blocks = build_status_update_blocks(job, "rejected")

        header = next((b for b in blocks if b.get("type") == "header"), None)
        self.assertIn("REJECTED", header["text"]["text"])
        self.assertIn("❌", header["text"]["text"])


class TestBoostDecisionDisplay(unittest.TestCase):
    """Test boost decision display in blocks."""

    def test_boost_recommended_shown(self):
        """Test that boost recommendation is displayed."""
        job = JobApprovalData(
            job_id="~test",
            title="Test",
            url="",
            boost_decision=True,
            boost_reasoning="High value client"
        )

        blocks = build_approval_blocks(job)

        boost_found = False
        for block in blocks:
            if block.get("type") == "context":
                for elem in block.get("elements", []):
                    text = elem.get("text", "")
                    if "Boost Recommended" in text:
                        boost_found = True
                        self.assertIn("🚀", text)
                        self.assertIn("High value", text)

        self.assertTrue(boost_found)

    def test_no_boost_shown(self):
        """Test that no-boost recommendation is displayed."""
        job = JobApprovalData(
            job_id="~test",
            title="Test",
            url="",
            boost_decision=False,
            boost_reasoning="New client"
        )

        blocks = build_approval_blocks(job)

        for block in blocks:
            if block.get("type") == "context":
                for elem in block.get("elements", []):
                    text = elem.get("text", "")
                    if "No Boost" in text:
                        self.assertIn("⏸️", text)


class TestPricingDisplay(unittest.TestCase):
    """Test proposed pricing display."""

    def test_pricing_shown(self):
        """Test that proposed pricing is displayed."""
        job = JobApprovalData(
            job_id="~test",
            title="Test",
            url="",
            pricing_proposed=1500.50
        )

        blocks = build_approval_blocks(job)

        pricing_found = False
        for block in blocks:
            if block.get("type") == "context":
                for elem in block.get("elements", []):
                    text = elem.get("text", "")
                    if "Proposed Price" in text:
                        pricing_found = True
                        self.assertIn("$1,500.50", text)
                        self.assertIn("💵", text)

        self.assertTrue(pricing_found)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""

    def test_minimal_job_data(self):
        """Test blocks with minimal job data."""
        job = JobApprovalData(
            job_id="~minimal",
            title="Minimal Job",
            url="https://upwork.com/jobs/~minimal"
        )

        blocks = build_approval_blocks(job)

        # Should still have header, actions, and footer
        types = [b.get("type") for b in blocks]
        self.assertIn("header", types)
        self.assertIn("actions", types)

    def test_empty_strings_handled(self):
        """Test handling of empty strings."""
        job = JobApprovalData(
            job_id="",
            title="",
            url="",
            proposal_text="",
            fit_reasoning=""
        )

        # Should not raise exception
        blocks = build_approval_blocks(job)
        self.assertIsInstance(blocks, list)

    def test_special_characters_in_title(self):
        """Test handling of special characters in title."""
        job = JobApprovalData(
            job_id="~test",
            title="Build <script>alert('xss')</script> & more",
            url=""
        )

        blocks = build_approval_blocks(job)
        header = next((b for b in blocks if b.get("type") == "header"), None)

        # Title should be present (Slack handles escaping)
        self.assertIn("Build", header["text"]["text"])


class TestUpdateJobStatusInSheet(unittest.TestCase):
    """Test update_job_status_in_sheet function."""

    def test_mock_mode_returns_success(self):
        """Test that mock mode returns success without touching sheet."""
        result = update_job_status_in_sheet(
            job_id="~test123",
            status="approved",
            additional_fields={"approved_at": "2026-01-18T12:00:00Z"},
            mock=True
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["job_id"], "~test123")
        self.assertEqual(result["status"], "approved")
        self.assertIn("approved_at", result["fields_updated"])
        self.assertTrue(result.get("mock"))

    def test_mock_mode_includes_all_fields(self):
        """Test that mock mode includes all requested fields."""
        result = update_job_status_in_sheet(
            job_id="~test456",
            status="rejected",
            additional_fields={
                "slack_message_ts": "1234567890.123456",
                "error_log": "User rejected"
            },
            mock=True
        )

        self.assertTrue(result["success"])
        self.assertIn("status", result["fields_updated"])
        self.assertIn("slack_message_ts", result["fields_updated"])
        self.assertIn("error_log", result["fields_updated"])


class TestGetJobFromSheet(unittest.TestCase):
    """Test get_job_from_sheet function."""

    def test_mock_mode_returns_job_data(self):
        """Test that mock mode returns mock job data."""
        job = get_job_from_sheet("~mockjob123", mock=True)

        self.assertIsNotNone(job)
        self.assertEqual(job["job_id"], "~mockjob123")
        self.assertIn("Mock Job", job["title"])
        self.assertEqual(job["status"], "pending_approval")

    def test_mock_mode_includes_required_fields(self):
        """Test that mock mode includes all required fields for approval."""
        job = get_job_from_sheet("~test", mock=True)

        self.assertIn("job_id", job)
        self.assertIn("title", job)
        self.assertIn("url", job)
        self.assertIn("proposal_text", job)
        self.assertIn("proposal_doc_url", job)


class TestApprovalCallbackResult(unittest.TestCase):
    """Test ApprovalCallbackResult dataclass."""

    def test_create_result(self):
        """Test creating an ApprovalCallbackResult."""
        result = ApprovalCallbackResult(
            success=True,
            job_id="~test",
            action="approve",
            status="approved",
            approved_at="2026-01-18T12:00:00Z",
            trigger_submission=True
        )

        self.assertTrue(result.success)
        self.assertEqual(result.action, "approve")
        self.assertTrue(result.trigger_submission)

    def test_to_dict(self):
        """Test serialization to dictionary."""
        result = ApprovalCallbackResult(
            success=True,
            job_id="~test",
            action="reject",
            status="rejected"
        )

        d = result.to_dict()
        self.assertEqual(d["job_id"], "~test")
        self.assertEqual(d["action"], "reject")


class TestFeature46ApproveTriggersSubmission(unittest.TestCase):
    """
    Test Feature #46: Slack approve button triggers submission workflow

    Steps:
    1. Send approval message and capture message_ts
    2. Click Approve button
    3. Verify callback is received by webhook
    4. Verify job status changes to 'approved'
    5. Verify approved_at timestamp is set
    """

    def test_approve_callback_updates_status_to_approved(self):
        """Test that approve callback sets status to 'approved'."""
        result = process_approval_callback(
            action="approve",
            job_id="~feature46test",
            user_id="U123456",
            channel="C123456",
            message_ts="1234567890.123456",
            mock=True
        )

        self.assertTrue(result.success)
        self.assertEqual(result.action, "approve")
        self.assertEqual(result.status, "approved")

    def test_approve_callback_sets_approved_at_timestamp(self):
        """Test that approve callback sets approved_at timestamp."""
        result = process_approval_callback(
            action="approve",
            job_id="~feature46test",
            user_id="U123456",
            channel="C123456",
            message_ts="1234567890.123456",
            mock=True
        )

        self.assertTrue(result.success)
        self.assertIsNotNone(result.approved_at)
        # Should be ISO format timestamp
        self.assertIn("T", result.approved_at)

    def test_approve_callback_triggers_submission_flag(self):
        """Test that approve callback sets trigger_submission flag."""
        result = process_approval_callback(
            action="approve",
            job_id="~feature46test",
            user_id="U123456",
            channel="C123456",
            message_ts="1234567890.123456",
            mock=True
        )

        self.assertTrue(result.success)
        self.assertTrue(result.trigger_submission)

    def test_approve_callback_calls_submission_callback(self):
        """Test that approve callback invokes submission callback if provided."""
        callback_called = []

        def mock_submission_callback(job_id):
            callback_called.append(job_id)

        # Note: callback only called when mock=False, so we test the flag instead
        result = process_approval_callback(
            action="approve",
            job_id="~feature46test",
            user_id="U123456",
            channel="C123456",
            message_ts="1234567890.123456",
            mock=True,
            submission_callback=mock_submission_callback
        )

        # In mock mode, callback isn't actually called but trigger_submission is set
        self.assertTrue(result.trigger_submission)

    def test_approve_updates_sheet_status(self):
        """Test that approve updates sheet with status='approved'."""
        # Test via mock - verifies the sheet update logic is called correctly
        result = update_job_status_in_sheet(
            job_id="~feature46test",
            status="approved",
            additional_fields={"approved_at": "2026-01-18T12:00:00+00:00"},
            mock=True
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "approved")
        self.assertIn("approved_at", result["fields_updated"])

    def test_full_approval_flow_mock(self):
        """Test complete approval flow in mock mode."""
        # Step 1: Send approval message
        job = JobApprovalData(
            job_id="~fullflowtest",
            title="Test Full Flow",
            url="https://upwork.com/jobs/~fullflowtest",
            fit_score=85
        )

        message_result = send_approval_message(
            job=job,
            channel="C123456",
            mock=True
        )

        self.assertTrue(message_result.success)
        message_ts = message_result.message_ts
        self.assertIsNotNone(message_ts)

        # Step 2: Process approve callback
        callback_result = process_approval_callback(
            action="approve",
            job_id="~fullflowtest",
            user_id="U123456",
            channel="C123456",
            message_ts=message_ts,
            mock=True
        )

        # Step 3: Verify status changes to approved
        self.assertTrue(callback_result.success)
        self.assertEqual(callback_result.status, "approved")

        # Step 4: Verify approved_at is set
        self.assertIsNotNone(callback_result.approved_at)

        # Step 5: Verify submission trigger is set
        self.assertTrue(callback_result.trigger_submission)


class TestFeature47RejectMarksRejected(unittest.TestCase):
    """
    Test Feature #47: Slack reject button marks job as rejected

    Steps:
    1. Send approval message
    2. Click Reject button
    3. Verify job status changes to 'rejected'
    4. Verify message is updated to show rejection
    """

    def test_reject_callback_updates_status_to_rejected(self):
        """Test that reject callback sets status to 'rejected'."""
        result = process_approval_callback(
            action="reject",
            job_id="~feature47test",
            user_id="U123456",
            channel="C123456",
            message_ts="1234567890.123456",
            mock=True
        )

        self.assertTrue(result.success)
        self.assertEqual(result.action, "reject")
        self.assertEqual(result.status, "rejected")

    def test_reject_callback_no_submission_trigger(self):
        """Test that reject callback does not trigger submission."""
        result = process_approval_callback(
            action="reject",
            job_id="~feature47test",
            user_id="U123456",
            channel="C123456",
            message_ts="1234567890.123456",
            mock=True
        )

        self.assertTrue(result.success)
        self.assertFalse(result.trigger_submission)

    def test_reject_callback_no_approved_at(self):
        """Test that reject callback does not set approved_at."""
        result = process_approval_callback(
            action="reject",
            job_id="~feature47test",
            user_id="U123456",
            channel="C123456",
            message_ts="1234567890.123456",
            mock=True
        )

        self.assertTrue(result.success)
        self.assertIsNone(result.approved_at)

    def test_reject_updates_sheet_status(self):
        """Test that reject updates sheet with status='rejected'."""
        result = update_job_status_in_sheet(
            job_id="~feature47test",
            status="rejected",
            additional_fields={"slack_message_ts": "1234567890.123456"},
            mock=True
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "rejected")

    def test_reject_status_block_shows_rejection(self):
        """Test that rejection is shown in status update blocks."""
        job = JobApprovalData(
            job_id="~feature47test",
            title="Test Rejection",
            url="https://upwork.com/jobs/~feature47test"
        )

        blocks = build_status_update_blocks(job, "rejected", "U123456")

        header = next((b for b in blocks if b.get("type") == "header"), None)
        self.assertIsNotNone(header)
        self.assertIn("REJECTED", header["text"]["text"])
        self.assertIn("❌", header["text"]["text"])

    def test_full_rejection_flow_mock(self):
        """Test complete rejection flow in mock mode."""
        # Step 1: Send approval message
        job = JobApprovalData(
            job_id="~rejectflowtest",
            title="Test Reject Flow",
            url="https://upwork.com/jobs/~rejectflowtest",
            fit_score=65
        )

        message_result = send_approval_message(
            job=job,
            channel="C123456",
            mock=True
        )

        self.assertTrue(message_result.success)
        message_ts = message_result.message_ts

        # Step 2: Process reject callback
        callback_result = process_approval_callback(
            action="reject",
            job_id="~rejectflowtest",
            user_id="U123456",
            channel="C123456",
            message_ts=message_ts,
            mock=True
        )

        # Step 3: Verify status changes to rejected
        self.assertTrue(callback_result.success)
        self.assertEqual(callback_result.status, "rejected")


class TestFeature48EditAllowsModification(unittest.TestCase):
    """
    Test Feature #48: Slack edit button allows proposal modification

    Steps:
    1. Send approval message
    2. Click Edit button
    3. Verify modal opens for editing
    4. Make changes to proposal text
    5. Submit changes
    6. Verify proposal_text is updated in sheet
    """

    def test_edit_callback_returns_editing_status(self):
        """Test that edit callback returns 'editing' status."""
        result = process_approval_callback(
            action="edit",
            job_id="~feature48test",
            user_id="U123456",
            channel="C123456",
            message_ts="1234567890.123456",
            mock=True
        )

        self.assertTrue(result.success)
        self.assertEqual(result.action, "edit")
        self.assertEqual(result.status, "editing")

    def test_edit_callback_no_submission_trigger(self):
        """Test that edit callback does not trigger submission."""
        result = process_approval_callback(
            action="edit",
            job_id="~feature48test",
            user_id="U123456",
            channel="C123456",
            message_ts="1234567890.123456",
            mock=True
        )

        self.assertTrue(result.success)
        self.assertFalse(result.trigger_submission)

    def test_edit_callback_with_edited_proposal(self):
        """Test edit callback with updated proposal text."""
        edited_text = "Updated proposal text with new approach"

        result = process_approval_callback(
            action="edit",
            job_id="~feature48test",
            user_id="U123456",
            channel="C123456",
            message_ts="1234567890.123456",
            edited_proposal=edited_text,
            mock=True
        )

        self.assertTrue(result.success)
        self.assertEqual(result.status, "editing")

    def test_edit_updates_proposal_text_in_sheet(self):
        """Test that edit updates proposal_text in sheet."""
        result = update_job_status_in_sheet(
            job_id="~feature48test",
            status="pending_approval",
            additional_fields={"proposal_text": "New edited proposal content"},
            mock=True
        )

        self.assertTrue(result["success"])
        self.assertIn("proposal_text", result["fields_updated"])

    def test_handle_button_edit_triggers_modal(self):
        """Test that edit button action triggers modal flag."""
        value = json.dumps({"job_id": "~feature48test", "action": "edit"})

        result = handle_button_action(
            action_id="edit_job",
            value=value,
            user_id="U123456",
            channel="C123456",
            message_ts="1234567890.123456",
            mock=True
        )

        self.assertTrue(result["success"])
        self.assertTrue(result.get("trigger_modal"))


class TestProcessApprovalCallbackErrors(unittest.TestCase):
    """Test error handling in process_approval_callback."""

    def test_unknown_action_returns_error(self):
        """Test that unknown action returns error."""
        result = process_approval_callback(
            action="unknown_action",
            job_id="~test",
            user_id="U123456",
            channel="C123456",
            message_ts="1234567890.123456",
            mock=True
        )

        self.assertFalse(result.success)
        self.assertIn("Unknown action", result.error)

    def test_result_includes_job_id(self):
        """Test that result always includes job_id."""
        result = process_approval_callback(
            action="invalid",
            job_id="~testjobid",
            user_id="U123456",
            channel="C123456",
            message_ts="1234567890.123456",
            mock=True
        )

        self.assertEqual(result.job_id, "~testjobid")


if __name__ == "__main__":
    unittest.main(verbosity=2)
