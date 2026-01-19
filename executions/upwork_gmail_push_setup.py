#!/usr/bin/env python3
"""
Gmail Push Notification Setup for Upwork Alerts

Sets up Gmail API push notifications via Google Cloud Pub/Sub.
When new emails arrive, Gmail sends notifications to a webhook endpoint.

Prerequisites:
1. Google Cloud Project with Pub/Sub API enabled
2. Gmail API enabled
3. Service account or OAuth credentials with appropriate scopes
4. Pub/Sub topic configured to allow Gmail to publish

Usage:
    # Set up push notifications
    python executions/upwork_gmail_push_setup.py --setup

    # Check current watch status
    python executions/upwork_gmail_push_setup.py --status

    # Stop watching (unsubscribe)
    python executions/upwork_gmail_push_setup.py --stop

    # Test webhook endpoint
    python executions/upwork_gmail_push_setup.py --test-webhook

Environment Variables:
    GOOGLE_CLOUD_PROJECT - Google Cloud project ID
    GMAIL_PUSH_TOPIC - Pub/Sub topic name (e.g., projects/my-project/topics/gmail-push)
    GMAIL_PUSH_WEBHOOK_URL - Webhook URL for notifications
    GOOGLE_TOKEN_JSON - JSON string of Google OAuth token (optional)
"""

import os
import sys
import json
import argparse
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Gmail API imports
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    print("ERROR: Google API libraries not installed.")
    print("Run: pip install google-auth google-auth-oauthlib google-api-python-client")
    sys.exit(1)

# Scopes needed for push notifications
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify"
]

# Default configuration
DEFAULT_LABEL_IDS = ["INBOX"]  # Watch only inbox by default


class GmailPushConfig:
    """Configuration for Gmail push notifications."""

    def __init__(self):
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "")
        self.topic_name = os.getenv("GMAIL_PUSH_TOPIC", "")
        self.webhook_url = os.getenv("GMAIL_PUSH_WEBHOOK_URL", "")

        # Build topic name if not fully qualified
        if self.topic_name and not self.topic_name.startswith("projects/"):
            if self.project_id:
                self.topic_name = f"projects/{self.project_id}/topics/{self.topic_name}"

    def validate(self) -> Tuple[bool, list]:
        """Validate configuration. Returns (is_valid, list of errors)."""
        errors = []

        if not self.project_id:
            errors.append("GOOGLE_CLOUD_PROJECT not set")

        if not self.topic_name:
            errors.append("GMAIL_PUSH_TOPIC not set")
        elif not self.topic_name.startswith("projects/"):
            errors.append(f"Invalid topic name format: {self.topic_name}")

        if not self.webhook_url:
            errors.append("GMAIL_PUSH_WEBHOOK_URL not set")
        elif not self.webhook_url.startswith("https://"):
            errors.append("Webhook URL must use HTTPS")

        return len(errors) == 0, errors


class GmailPushSetup:
    """Set up and manage Gmail push notifications."""

    def __init__(self, token_path: str = None, token_json: str = None):
        self.token_path = token_path or self._find_token_path()
        self.token_json = token_json or os.getenv("GOOGLE_TOKEN_JSON", "")
        self._service = None
        self._credentials = None
        self.config = GmailPushConfig()

    def _find_token_path(self) -> str:
        """Find existing token file."""
        paths = [
            "config/token.json",
            "configuration/token.json",
            os.path.expanduser("~/.config/gmail/token.json")
        ]
        for path in paths:
            if os.path.exists(path):
                return path
        return "config/token.json"

    def _get_credentials(self) -> Optional[Credentials]:
        """Get Gmail credentials."""
        if self._credentials and self._credentials.valid:
            return self._credentials

        creds = None

        # Try token JSON from environment first (for Modal deployment)
        if self.token_json:
            try:
                token_data = json.loads(self.token_json)
                creds = Credentials.from_authorized_user_info(token_data, SCOPES)
            except Exception as e:
                print(f"Warning: Could not load token from GOOGLE_TOKEN_JSON: {e}")

        # Try token file
        if not creds and os.path.exists(self.token_path):
            try:
                creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
            except Exception as e:
                print(f"Warning: Could not load token from {self.token_path}: {e}")

        # Refresh if needed
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                # Save refreshed token
                if os.path.exists(self.token_path):
                    with open(self.token_path, 'w') as f:
                        f.write(creds.to_json())
            except Exception as e:
                print(f"Warning: Token refresh failed: {e}")
                creds = None

        self._credentials = creds
        return creds

    def get_service(self):
        """Get Gmail API service."""
        if self._service is None:
            creds = self._get_credentials()
            if creds:
                self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def setup_watch(self, label_ids: list = None) -> Dict[str, Any]:
        """
        Set up Gmail push notification watch.

        Args:
            label_ids: List of label IDs to watch (default: INBOX)

        Returns:
            Watch response with historyId and expiration
        """
        service = self.get_service()
        if not service:
            return {"error": "Could not authenticate with Gmail"}

        # Validate config
        is_valid, errors = self.config.validate()
        if not is_valid:
            return {"error": f"Configuration errors: {', '.join(errors)}"}

        label_ids = label_ids or DEFAULT_LABEL_IDS

        watch_request = {
            "topicName": self.config.topic_name,
            "labelIds": label_ids,
            "labelFilterAction": "include"
        }

        try:
            response = service.users().watch(
                userId="me",
                body=watch_request
            ).execute()

            # Parse expiration
            expiration_ms = int(response.get("expiration", 0))
            expiration_dt = datetime.fromtimestamp(expiration_ms / 1000)

            return {
                "status": "success",
                "historyId": response.get("historyId"),
                "expiration": response.get("expiration"),
                "expiration_readable": expiration_dt.isoformat(),
                "topic": self.config.topic_name,
                "label_ids": label_ids
            }

        except HttpError as e:
            error_content = e.content.decode("utf-8") if hasattr(e, "content") else str(e)
            return {
                "status": "error",
                "error": f"Gmail API error: {error_content}",
                "error_code": e.resp.status if hasattr(e, "resp") else None
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

    def stop_watch(self) -> Dict[str, Any]:
        """Stop Gmail push notification watch."""
        service = self.get_service()
        if not service:
            return {"error": "Could not authenticate with Gmail"}

        try:
            service.users().stop(userId="me").execute()
            return {
                "status": "success",
                "message": "Watch stopped successfully"
            }
        except HttpError as e:
            error_content = e.content.decode("utf-8") if hasattr(e, "content") else str(e)
            return {
                "status": "error",
                "error": f"Gmail API error: {error_content}"
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

    def get_watch_status(self) -> Dict[str, Any]:
        """
        Get current watch status.

        Note: Gmail API doesn't have a direct 'get watch status' endpoint.
        We attempt to get the profile and check if watch is active.
        """
        service = self.get_service()
        if not service:
            return {"error": "Could not authenticate with Gmail"}

        try:
            # Get user profile
            profile = service.users().getProfile(userId="me").execute()

            return {
                "status": "success",
                "email": profile.get("emailAddress"),
                "messages_total": profile.get("messagesTotal"),
                "threads_total": profile.get("threadsTotal"),
                "history_id": profile.get("historyId"),
                "config": {
                    "project_id": self.config.project_id,
                    "topic_name": self.config.topic_name,
                    "webhook_url": self.config.webhook_url
                }
            }
        except HttpError as e:
            error_content = e.content.decode("utf-8") if hasattr(e, "content") else str(e)
            return {
                "status": "error",
                "error": f"Gmail API error: {error_content}"
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

    def test_webhook(self) -> Dict[str, Any]:
        """
        Test webhook endpoint by sending a sample notification.

        Returns test result.
        """
        if not self.config.webhook_url:
            return {"error": "GMAIL_PUSH_WEBHOOK_URL not configured"}

        # Create sample notification matching Gmail Pub/Sub format
        import base64

        sample_data = {
            "emailAddress": "test@example.com",
            "historyId": "12345"
        }

        encoded_data = base64.b64encode(
            json.dumps(sample_data).encode("utf-8")
        ).decode("utf-8")

        sample_notification = {
            "message": {
                "data": encoded_data,
                "messageId": f"test-{datetime.now().timestamp()}",
                "publishTime": datetime.utcnow().isoformat() + "Z"
            },
            "subscription": f"projects/{self.config.project_id}/subscriptions/gmail-push-test"
        }

        try:
            response = requests.post(
                self.config.webhook_url,
                json=sample_notification,
                headers={"Content-Type": "application/json"},
                timeout=30
            )

            return {
                "status": "success" if response.status_code == 200 else "warning",
                "webhook_url": self.config.webhook_url,
                "response_status": response.status_code,
                "response_body": response.text[:500] if response.text else None
            }

        except requests.exceptions.Timeout:
            return {
                "status": "error",
                "error": "Webhook request timed out"
            }
        except requests.exceptions.ConnectionError as e:
            return {
                "status": "error",
                "error": f"Could not connect to webhook: {e}"
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }


def setup_gmail_push(label_ids: list = None) -> Dict[str, Any]:
    """
    Set up Gmail push notifications.

    Convenience function for programmatic use.
    """
    setup = GmailPushSetup()
    return setup.setup_watch(label_ids=label_ids)


def stop_gmail_push() -> Dict[str, Any]:
    """Stop Gmail push notifications."""
    setup = GmailPushSetup()
    return setup.stop_watch()


def get_push_status() -> Dict[str, Any]:
    """Get Gmail push notification status."""
    setup = GmailPushSetup()
    return setup.get_watch_status()


def test_push_webhook() -> Dict[str, Any]:
    """Test the push notification webhook."""
    setup = GmailPushSetup()
    return setup.test_webhook()


def verify_push_configuration() -> Dict[str, Any]:
    """
    Verify the Gmail push notification configuration is complete.

    Returns:
        Dict with verification results for each component
    """
    results = {
        "config": {},
        "auth": {},
        "webhook": {},
        "overall": False
    }

    # Check configuration
    config = GmailPushConfig()
    is_valid, errors = config.validate()
    results["config"] = {
        "valid": is_valid,
        "errors": errors,
        "project_id": config.project_id,
        "topic_name": config.topic_name,
        "webhook_url": config.webhook_url[:50] + "..." if config.webhook_url and len(config.webhook_url) > 50 else config.webhook_url
    }

    # Check authentication
    setup = GmailPushSetup()
    service = setup.get_service()
    results["auth"] = {
        "authenticated": service is not None,
        "token_path": setup.token_path,
        "has_token_json": bool(setup.token_json)
    }

    # Test webhook (if configured)
    if config.webhook_url:
        webhook_result = setup.test_webhook()
        results["webhook"] = {
            "tested": True,
            "success": webhook_result.get("status") == "success",
            "details": webhook_result
        }
    else:
        results["webhook"] = {
            "tested": False,
            "reason": "No webhook URL configured"
        }

    # Overall status
    results["overall"] = (
        results["config"]["valid"] and
        results["auth"]["authenticated"] and
        results["webhook"].get("success", False)
    )

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Set up Gmail push notifications for Upwork alerts"
    )

    parser.add_argument(
        "--setup",
        action="store_true",
        help="Set up Gmail push notification watch"
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="Stop Gmail push notification watch"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check current watch status"
    )
    parser.add_argument(
        "--test-webhook",
        action="store_true",
        help="Test the webhook endpoint"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify complete push notification configuration"
    )
    parser.add_argument(
        "--token-path",
        help="Path to token.json file"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )

    args = parser.parse_args()

    # Initialize setup with custom token path if provided
    token_path = args.token_path if args.token_path else None

    result = None

    if args.setup:
        print("Setting up Gmail push notifications...")
        setup = GmailPushSetup(token_path=token_path)
        result = setup.setup_watch()

        if result.get("status") == "success":
            print(f"✓ Watch set up successfully")
            print(f"  History ID: {result.get('historyId')}")
            print(f"  Expires: {result.get('expiration_readable')}")
            print(f"  Topic: {result.get('topic')}")
        else:
            print(f"✗ Setup failed: {result.get('error')}")
            return 1

    elif args.stop:
        print("Stopping Gmail push notifications...")
        setup = GmailPushSetup(token_path=token_path)
        result = setup.stop_watch()

        if result.get("status") == "success":
            print("✓ Watch stopped successfully")
        else:
            print(f"✗ Stop failed: {result.get('error')}")
            return 1

    elif args.status:
        print("Checking Gmail push notification status...")
        setup = GmailPushSetup(token_path=token_path)
        result = setup.get_watch_status()

        if result.get("status") == "success":
            print(f"✓ Connected to Gmail")
            print(f"  Email: {result.get('email')}")
            print(f"  History ID: {result.get('history_id')}")
            print(f"  Config:")
            config = result.get("config", {})
            print(f"    Project: {config.get('project_id')}")
            print(f"    Topic: {config.get('topic_name')}")
            print(f"    Webhook: {config.get('webhook_url', 'Not set')}")
        else:
            print(f"✗ Status check failed: {result.get('error')}")
            return 1

    elif args.test_webhook:
        print("Testing webhook endpoint...")
        setup = GmailPushSetup(token_path=token_path)
        result = setup.test_webhook()

        if result.get("status") == "success":
            print(f"✓ Webhook test successful")
            print(f"  URL: {result.get('webhook_url')}")
            print(f"  Response: {result.get('response_status')}")
        else:
            print(f"✗ Webhook test failed: {result.get('error')}")
            return 1

    elif args.verify:
        print("Verifying Gmail push notification configuration...\n")
        result = verify_push_configuration()

        # Config check
        config = result.get("config", {})
        if config.get("valid"):
            print("✓ Configuration valid")
        else:
            print("✗ Configuration invalid")
            for error in config.get("errors", []):
                print(f"    - {error}")

        # Auth check
        auth = result.get("auth", {})
        if auth.get("authenticated"):
            print("✓ Authentication successful")
        else:
            print("✗ Authentication failed")

        # Webhook check
        webhook = result.get("webhook", {})
        if webhook.get("success"):
            print("✓ Webhook test passed")
        elif not webhook.get("tested"):
            print(f"- Webhook not tested: {webhook.get('reason')}")
        else:
            print(f"✗ Webhook test failed")

        print(f"\nOverall: {'✓ READY' if result.get('overall') else '✗ NOT READY'}")

        if not result.get("overall"):
            return 1

    else:
        parser.print_help()
        return 1

    # JSON output
    if args.json and result:
        print("\n" + json.dumps(result, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
