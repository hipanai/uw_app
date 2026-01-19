#!/usr/bin/env python3
"""
Tests for Gmail Push Notification Setup (Feature #95)

Tests that Gmail push notifications are configured correctly:
1. Set up Gmail push notification subscription
2. Verify webhook URL is registered
3. Verify notifications are received
"""

import os
import sys
import json
import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from executions.upwork_gmail_push_setup import (
    GmailPushConfig,
    GmailPushSetup,
    setup_gmail_push,
    stop_gmail_push,
    get_push_status,
    test_push_webhook,
    verify_push_configuration
)


class TestGmailPushConfig(unittest.TestCase):
    """Test Gmail push configuration validation."""

    def test_config_validates_required_fields(self):
        """Test that config validates required environment variables."""
        with patch.dict(os.environ, {
            "GOOGLE_CLOUD_PROJECT": "",
            "GMAIL_PUSH_TOPIC": "",
            "GMAIL_PUSH_WEBHOOK_URL": ""
        }, clear=True):
            config = GmailPushConfig()
            is_valid, errors = config.validate()

            self.assertFalse(is_valid)
            self.assertIn("GOOGLE_CLOUD_PROJECT not set", errors)
            self.assertIn("GMAIL_PUSH_TOPIC not set", errors)
            self.assertIn("GMAIL_PUSH_WEBHOOK_URL not set", errors)

    def test_config_valid_with_all_fields(self):
        """Test that config is valid when all fields are set."""
        with patch.dict(os.environ, {
            "GOOGLE_CLOUD_PROJECT": "my-project",
            "GMAIL_PUSH_TOPIC": "projects/my-project/topics/gmail-push",
            "GMAIL_PUSH_WEBHOOK_URL": "https://example.com/webhook"
        }):
            config = GmailPushConfig()
            is_valid, errors = config.validate()

            self.assertTrue(is_valid)
            self.assertEqual(len(errors), 0)

    def test_config_builds_topic_name(self):
        """Test that config builds full topic name from short name."""
        with patch.dict(os.environ, {
            "GOOGLE_CLOUD_PROJECT": "my-project",
            "GMAIL_PUSH_TOPIC": "gmail-push",  # Short name
            "GMAIL_PUSH_WEBHOOK_URL": "https://example.com/webhook"
        }):
            config = GmailPushConfig()

            self.assertEqual(config.topic_name, "projects/my-project/topics/gmail-push")

    def test_webhook_requires_https(self):
        """Test that webhook URL must use HTTPS."""
        with patch.dict(os.environ, {
            "GOOGLE_CLOUD_PROJECT": "my-project",
            "GMAIL_PUSH_TOPIC": "projects/my-project/topics/gmail-push",
            "GMAIL_PUSH_WEBHOOK_URL": "http://example.com/webhook"  # HTTP, not HTTPS
        }):
            config = GmailPushConfig()
            is_valid, errors = config.validate()

            self.assertFalse(is_valid)
            self.assertTrue(any("HTTPS" in e for e in errors))


class TestGmailPushSetup(unittest.TestCase):
    """Test Gmail push notification setup."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_service = Mock()
        self.mock_credentials = Mock()
        self.mock_credentials.valid = True
        self.mock_credentials.expired = False

    @patch.dict(os.environ, {
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "GMAIL_PUSH_TOPIC": "projects/test-project/topics/gmail-push",
        "GMAIL_PUSH_WEBHOOK_URL": "https://modal.example.com/upwork/gmail-push"
    })
    @patch('executions.upwork_gmail_push_setup.build')
    @patch('executions.upwork_gmail_push_setup.Credentials')
    def test_setup_watch_success(self, mock_creds_class, mock_build):
        """Test successful watch setup."""
        # Mock credentials
        mock_creds = Mock()
        mock_creds.valid = True
        mock_creds.expired = False
        mock_creds_class.from_authorized_user_file.return_value = mock_creds

        # Mock Gmail service
        mock_service = Mock()
        mock_build.return_value = mock_service

        # Mock watch response
        expiration_ms = int((datetime.now().timestamp() + 86400) * 1000)  # 1 day from now
        mock_service.users.return_value.watch.return_value.execute.return_value = {
            "historyId": "123456",
            "expiration": str(expiration_ms)
        }

        # Create setup with existing token
        with patch('os.path.exists', return_value=True):
            setup = GmailPushSetup(token_path="config/token.json")
            result = setup.setup_watch()

        self.assertEqual(result["status"], "success")
        self.assertIn("historyId", result)
        self.assertIn("expiration", result)
        self.assertEqual(result["topic"], "projects/test-project/topics/gmail-push")

    @patch.dict(os.environ, {
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "GMAIL_PUSH_TOPIC": "projects/test-project/topics/gmail-push",
        "GMAIL_PUSH_WEBHOOK_URL": "https://modal.example.com/upwork/gmail-push"
    })
    @patch('executions.upwork_gmail_push_setup.build')
    @patch('executions.upwork_gmail_push_setup.Credentials')
    def test_stop_watch_success(self, mock_creds_class, mock_build):
        """Test successful watch stop."""
        # Mock credentials
        mock_creds = Mock()
        mock_creds.valid = True
        mock_creds.expired = False
        mock_creds_class.from_authorized_user_file.return_value = mock_creds

        # Mock Gmail service
        mock_service = Mock()
        mock_build.return_value = mock_service
        mock_service.users.return_value.stop.return_value.execute.return_value = {}

        with patch('os.path.exists', return_value=True):
            setup = GmailPushSetup(token_path="config/token.json")
            result = setup.stop_watch()

        self.assertEqual(result["status"], "success")
        self.assertIn("message", result)

    @patch.dict(os.environ, {
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "GMAIL_PUSH_TOPIC": "projects/test-project/topics/gmail-push",
        "GMAIL_PUSH_WEBHOOK_URL": "https://modal.example.com/upwork/gmail-push"
    })
    @patch('executions.upwork_gmail_push_setup.build')
    @patch('executions.upwork_gmail_push_setup.Credentials')
    def test_get_status_success(self, mock_creds_class, mock_build):
        """Test getting watch status."""
        # Mock credentials
        mock_creds = Mock()
        mock_creds.valid = True
        mock_creds.expired = False
        mock_creds_class.from_authorized_user_file.return_value = mock_creds

        # Mock Gmail service
        mock_service = Mock()
        mock_build.return_value = mock_service
        mock_service.users.return_value.getProfile.return_value.execute.return_value = {
            "emailAddress": "test@example.com",
            "messagesTotal": 1000,
            "threadsTotal": 500,
            "historyId": "789"
        }

        with patch('os.path.exists', return_value=True):
            setup = GmailPushSetup(token_path="config/token.json")
            result = setup.get_watch_status()

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["email"], "test@example.com")
        self.assertEqual(result["history_id"], "789")
        self.assertIn("config", result)

    @patch.dict(os.environ, {
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "GMAIL_PUSH_TOPIC": "projects/test-project/topics/gmail-push",
        "GMAIL_PUSH_WEBHOOK_URL": "https://modal.example.com/upwork/gmail-push"
    })
    @patch('executions.upwork_gmail_push_setup.requests.post')
    def test_webhook_test_success(self, mock_post):
        """Test webhook endpoint testing."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"status": "ok"}'
        mock_post.return_value = mock_response

        setup = GmailPushSetup()
        result = setup.test_webhook()

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["response_status"], 200)

        # Verify the request was made to the correct URL
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        self.assertEqual(call_args[0][0], "https://modal.example.com/upwork/gmail-push")

    @patch.dict(os.environ, {
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "GMAIL_PUSH_TOPIC": "projects/test-project/topics/gmail-push",
        "GMAIL_PUSH_WEBHOOK_URL": "https://modal.example.com/upwork/gmail-push"
    })
    @patch('executions.upwork_gmail_push_setup.requests.post')
    def test_webhook_test_verifies_payload_format(self, mock_post):
        """Test that webhook test sends correctly formatted payload."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"status": "ok"}'
        mock_post.return_value = mock_response

        setup = GmailPushSetup()
        setup.test_webhook()

        # Get the JSON payload sent
        call_args = mock_post.call_args
        payload = call_args[1]["json"]

        # Verify payload structure matches Gmail Pub/Sub format
        self.assertIn("message", payload)
        self.assertIn("data", payload["message"])
        self.assertIn("messageId", payload["message"])
        self.assertIn("publishTime", payload["message"])
        self.assertIn("subscription", payload)

    def test_setup_fails_without_credentials(self):
        """Test that setup fails without valid credentials."""
        with patch.dict(os.environ, {
            "GOOGLE_CLOUD_PROJECT": "test-project",
            "GMAIL_PUSH_TOPIC": "projects/test-project/topics/gmail-push",
            "GMAIL_PUSH_WEBHOOK_URL": "https://modal.example.com/webhook"
        }):
            with patch('os.path.exists', return_value=False):
                setup = GmailPushSetup(token_path="/nonexistent/token.json")
                result = setup.setup_watch()

                self.assertIn("error", result)


class TestVerifyConfiguration(unittest.TestCase):
    """Test configuration verification."""

    @patch.dict(os.environ, {
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "GMAIL_PUSH_TOPIC": "projects/test-project/topics/gmail-push",
        "GMAIL_PUSH_WEBHOOK_URL": "https://modal.example.com/upwork/gmail-push"
    })
    @patch('executions.upwork_gmail_push_setup.requests.post')
    @patch('executions.upwork_gmail_push_setup.build')
    @patch('executions.upwork_gmail_push_setup.Credentials')
    def test_verify_complete_configuration(self, mock_creds_class, mock_build, mock_post):
        """Test that verify_push_configuration checks all components."""
        # Mock credentials
        mock_creds = Mock()
        mock_creds.valid = True
        mock_creds.expired = False
        mock_creds_class.from_authorized_user_file.return_value = mock_creds

        # Mock Gmail service
        mock_service = Mock()
        mock_build.return_value = mock_service

        # Mock webhook response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"status": "ok"}'
        mock_post.return_value = mock_response

        with patch('os.path.exists', return_value=True):
            result = verify_push_configuration()

        # Check all components are verified
        self.assertIn("config", result)
        self.assertIn("auth", result)
        self.assertIn("webhook", result)
        self.assertIn("overall", result)

        # With all mocks returning success, overall should be True
        self.assertTrue(result["config"]["valid"])
        self.assertTrue(result["auth"]["authenticated"])
        self.assertTrue(result["webhook"]["success"])
        self.assertTrue(result["overall"])


class TestConvenienceFunctions(unittest.TestCase):
    """Test convenience functions for programmatic use."""

    @patch.dict(os.environ, {
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "GMAIL_PUSH_TOPIC": "projects/test-project/topics/gmail-push",
        "GMAIL_PUSH_WEBHOOK_URL": "https://modal.example.com/upwork/gmail-push"
    })
    @patch('executions.upwork_gmail_push_setup.GmailPushSetup')
    def test_setup_gmail_push_function(self, mock_setup_class):
        """Test setup_gmail_push convenience function."""
        mock_instance = Mock()
        mock_instance.setup_watch.return_value = {"status": "success"}
        mock_setup_class.return_value = mock_instance

        result = setup_gmail_push()

        mock_instance.setup_watch.assert_called_once()
        self.assertEqual(result["status"], "success")

    @patch.dict(os.environ, {
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "GMAIL_PUSH_TOPIC": "projects/test-project/topics/gmail-push",
        "GMAIL_PUSH_WEBHOOK_URL": "https://modal.example.com/upwork/gmail-push"
    })
    @patch('executions.upwork_gmail_push_setup.GmailPushSetup')
    def test_stop_gmail_push_function(self, mock_setup_class):
        """Test stop_gmail_push convenience function."""
        mock_instance = Mock()
        mock_instance.stop_watch.return_value = {"status": "success"}
        mock_setup_class.return_value = mock_instance

        result = stop_gmail_push()

        mock_instance.stop_watch.assert_called_once()
        self.assertEqual(result["status"], "success")

    @patch.dict(os.environ, {
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "GMAIL_PUSH_TOPIC": "projects/test-project/topics/gmail-push",
        "GMAIL_PUSH_WEBHOOK_URL": "https://modal.example.com/upwork/gmail-push"
    })
    @patch('executions.upwork_gmail_push_setup.GmailPushSetup')
    def test_get_push_status_function(self, mock_setup_class):
        """Test get_push_status convenience function."""
        mock_instance = Mock()
        mock_instance.get_watch_status.return_value = {"status": "success"}
        mock_setup_class.return_value = mock_instance

        result = get_push_status()

        mock_instance.get_watch_status.assert_called_once()
        self.assertEqual(result["status"], "success")

    @patch.dict(os.environ, {
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "GMAIL_PUSH_TOPIC": "projects/test-project/topics/gmail-push",
        "GMAIL_PUSH_WEBHOOK_URL": "https://modal.example.com/upwork/gmail-push"
    })
    @patch('executions.upwork_gmail_push_setup.GmailPushSetup')
    def test_test_push_webhook_function(self, mock_setup_class):
        """Test test_push_webhook convenience function."""
        mock_instance = Mock()
        mock_instance.test_webhook.return_value = {"status": "success"}
        mock_setup_class.return_value = mock_instance

        result = test_push_webhook()

        mock_instance.test_webhook.assert_called_once()
        self.assertEqual(result["status"], "success")


class TestLabelFiltering(unittest.TestCase):
    """Test label filtering for watch subscription."""

    @patch.dict(os.environ, {
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "GMAIL_PUSH_TOPIC": "projects/test-project/topics/gmail-push",
        "GMAIL_PUSH_WEBHOOK_URL": "https://modal.example.com/upwork/gmail-push"
    })
    @patch('executions.upwork_gmail_push_setup.build')
    @patch('executions.upwork_gmail_push_setup.Credentials')
    def test_custom_label_ids(self, mock_creds_class, mock_build):
        """Test that custom label IDs can be specified."""
        # Mock credentials
        mock_creds = Mock()
        mock_creds.valid = True
        mock_creds.expired = False
        mock_creds_class.from_authorized_user_file.return_value = mock_creds

        # Mock Gmail service
        mock_service = Mock()
        mock_build.return_value = mock_service

        expiration_ms = int((datetime.now().timestamp() + 86400) * 1000)
        mock_service.users.return_value.watch.return_value.execute.return_value = {
            "historyId": "123456",
            "expiration": str(expiration_ms)
        }

        with patch('os.path.exists', return_value=True):
            setup = GmailPushSetup(token_path="config/token.json")
            result = setup.setup_watch(label_ids=["INBOX", "IMPORTANT"])

        # Verify the watch was called with correct label IDs
        watch_call = mock_service.users.return_value.watch.return_value.execute
        self.assertEqual(result["label_ids"], ["INBOX", "IMPORTANT"])


def run_tests():
    """Run all tests and return results."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestGmailPushConfig))
    suite.addTests(loader.loadTestsFromTestCase(TestGmailPushSetup))
    suite.addTests(loader.loadTestsFromTestCase(TestVerifyConfiguration))
    suite.addTests(loader.loadTestsFromTestCase(TestConvenienceFunctions))
    suite.addTests(loader.loadTestsFromTestCase(TestLabelFiltering))

    # Run with verbosity
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
