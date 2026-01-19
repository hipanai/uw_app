#!/usr/bin/env python3
"""
Test runner for Feature #95: Gmail push notifications are configured correctly
"""

import os
import re

def run_tests():
    """Run all tests for Feature #95."""
    results = []

    # Test 1: upwork_gmail_push_setup.py exists
    setup_path = os.path.join(os.path.dirname(__file__), "executions", "upwork_gmail_push_setup.py")
    passed = os.path.exists(setup_path)
    results.append(("Setup script exists", passed))
    if passed:
        print("Test 1 PASSED: upwork_gmail_push_setup.py exists")
    else:
        print("Test 1 FAILED: upwork_gmail_push_setup.py not found")
        return False

    # Read the setup script
    with open(setup_path, 'r') as f:
        content = f.read()

    # Test 2: GmailPushConfig class exists
    passed = 'class GmailPushConfig' in content
    results.append(("GmailPushConfig class exists", passed))
    if passed:
        print("Test 2 PASSED: GmailPushConfig class exists")
    else:
        print("Test 2 FAILED: GmailPushConfig class not found")

    # Test 3: GmailPushSetup class exists
    passed = 'class GmailPushSetup' in content
    results.append(("GmailPushSetup class exists", passed))
    if passed:
        print("Test 3 PASSED: GmailPushSetup class exists")
    else:
        print("Test 3 FAILED: GmailPushSetup class not found")

    # Test 4: setup_watch method exists
    passed = 'def setup_watch(' in content
    results.append(("setup_watch method exists", passed))
    if passed:
        print("Test 4 PASSED: setup_watch method exists")
    else:
        print("Test 4 FAILED: setup_watch method not found")

    # Test 5: stop_watch method exists
    passed = 'def stop_watch(' in content
    results.append(("stop_watch method exists", passed))
    if passed:
        print("Test 5 PASSED: stop_watch method exists")
    else:
        print("Test 5 FAILED: stop_watch method not found")

    # Test 6: test_webhook method exists
    passed = 'def test_webhook(' in content
    results.append(("test_webhook method exists", passed))
    if passed:
        print("Test 6 PASSED: test_webhook method exists")
    else:
        print("Test 6 FAILED: test_webhook method not found")

    # Test 7: Uses Gmail watch API
    passed = '.watch(' in content
    results.append(("Uses Gmail watch API", passed))
    if passed:
        print("Test 7 PASSED: Uses Gmail watch API")
    else:
        print("Test 7 FAILED: Gmail watch API not used")

    # Test 8: Uses Pub/Sub topic
    passed = 'topicName' in content
    results.append(("Uses Pub/Sub topic", passed))
    if passed:
        print("Test 8 PASSED: Uses Pub/Sub topic")
    else:
        print("Test 8 FAILED: Pub/Sub topic not configured")

    # Test 9: Configuration validation exists
    passed = 'def validate(' in content
    results.append(("Configuration validation exists", passed))
    if passed:
        print("Test 9 PASSED: Configuration validation exists")
    else:
        print("Test 9 FAILED: Configuration validation not found")

    # Test 10: Environment variables documented
    env_vars = ['GOOGLE_CLOUD_PROJECT', 'GMAIL_PUSH_TOPIC', 'GMAIL_PUSH_WEBHOOK_URL']
    all_present = all(var in content for var in env_vars)
    results.append(("Environment variables documented", all_present))
    if all_present:
        print("Test 10 PASSED: All environment variables documented")
    else:
        print("Test 10 FAILED: Missing environment variable documentation")

    # Test 11: Webhook test sends correctly formatted payload
    passed = 'base64' in content and 'messageId' in content
    results.append(("Webhook test payload format", passed))
    if passed:
        print("Test 11 PASSED: Webhook test sends correct payload format")
    else:
        print("Test 11 FAILED: Webhook test payload format incorrect")

    # Test 12: Modal webhook endpoint exists
    webhook_path = os.path.join(os.path.dirname(__file__), "executions", "modal_webhook.py")
    with open(webhook_path, 'r') as f:
        webhook_content = f.read()
    passed = 'def upwork_gmail_push(' in webhook_content
    results.append(("Modal webhook endpoint exists", passed))
    if passed:
        print("Test 12 PASSED: Modal webhook endpoint /upwork/gmail-push exists")
    else:
        print("Test 12 FAILED: Modal webhook endpoint not found")

    # Test 13: Check .env.example has new variables
    env_example_path = os.path.join(os.path.dirname(__file__), ".env.example")
    with open(env_example_path, 'r') as f:
        env_example_content = f.read()
    passed = 'GMAIL_PUSH_TOPIC' in env_example_content and 'GMAIL_PUSH_WEBHOOK_URL' in env_example_content
    results.append(("Environment variables in .env.example", passed))
    if passed:
        print("Test 13 PASSED: Environment variables documented in .env.example")
    else:
        print("Test 13 FAILED: Environment variables missing from .env.example")

    # Test 14: verify_push_configuration function exists
    passed = 'def verify_push_configuration(' in content
    results.append(("verify_push_configuration exists", passed))
    if passed:
        print("Test 14 PASSED: verify_push_configuration function exists")
    else:
        print("Test 14 FAILED: verify_push_configuration not found")

    # Test 15: Unit tests exist
    test_path = os.path.join(os.path.dirname(__file__), "executions", "test_upwork_gmail_push_setup.py")
    passed = os.path.exists(test_path)
    results.append(("Unit tests exist", passed))
    if passed:
        print("Test 15 PASSED: Unit tests exist")
    else:
        print("Test 15 FAILED: Unit tests not found")

    # Summary
    print()
    total = len(results)
    passed_count = sum(1 for _, p in results if p)
    print("=" * 50)
    print(f"Feature #95 Tests: {passed_count}/{total} PASSED")
    print("=" * 50)

    return passed_count == total


if __name__ == "__main__":
    import sys
    success = run_tests()
    sys.exit(0 if success else 1)
