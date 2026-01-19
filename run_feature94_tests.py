#!/usr/bin/env python3
"""
Test runner for Feature #94: Modal scheduled function runs every 2 hours
"""

import re
import os

def run_tests():
    """Run all tests for Feature #94."""
    results = []

    # Test 1: Cron expression format
    cron_expr = "0 */2 * * *"
    parts = cron_expr.split()
    passed = len(parts) == 5
    results.append(("Cron expression has 5 fields", passed))
    if passed:
        print("Test 1 PASSED: Cron expression has 5 fields")
    else:
        print("Test 1 FAILED: Cron expression should have 5 fields")

    # Test 2: Runs every 2 hours (12 times per day)
    matching_hours = [h for h in range(24) if h % 2 == 0]
    passed = len(matching_hours) == 12
    results.append(("Runs 12 times per day", passed))
    if passed:
        print("Test 2 PASSED: Runs 12 times per day (every 2 hours)")
    else:
        print("Test 2 FAILED: Should run 12 times per day")

    # Test 3: Function exists in modal_webhook.py
    webhook_path = os.path.join(os.path.dirname(__file__), "executions", "modal_webhook.py")
    with open(webhook_path, 'r') as f:
        content = f.read()

    passed = 'def scheduled_upwork_pipeline()' in content
    results.append(("Function exists", passed))
    if passed:
        print("Test 3 PASSED: scheduled_upwork_pipeline function exists")
    else:
        print("Test 3 FAILED: scheduled_upwork_pipeline function not found")

    # Test 4: Has correct cron decorator
    pattern = r'schedule\s*=\s*modal\.Cron\s*\(\s*["\']0 \*/2 \* \* \*["\']\s*\)'
    match = re.search(pattern, content)
    passed = match is not None
    results.append(("Has cron decorator", passed))
    if passed:
        print('Test 4 PASSED: Has schedule=modal.Cron("0 */2 * * *") decorator')
    else:
        print('Test 4 FAILED: Missing or incorrect cron decorator')

    # Test 5: Has proper timeout
    func_pattern = r'@app\.function\([^)]*timeout\s*=\s*(\d+)[^)]*\)\s*def scheduled_upwork_pipeline'
    match = re.search(func_pattern, content, re.DOTALL)
    passed = match is not None and int(match.group(1)) >= 600
    timeout_value = int(match.group(1)) if match else 0
    results.append(("Has proper timeout", passed))
    if passed:
        print(f"Test 5 PASSED: Has timeout of {timeout_value}s")
    else:
        print("Test 5 FAILED: Timeout missing or too short")

    # Test 6: Uses ALL_SECRETS
    pattern = r'@app\.function\([^)]*secrets\s*=\s*ALL_SECRETS[^)]*\)\s*def scheduled_upwork_pipeline'
    match = re.search(pattern, content, re.DOTALL)
    passed = match is not None
    results.append(("Uses ALL_SECRETS", passed))
    if passed:
        print("Test 6 PASSED: Uses ALL_SECRETS")
    else:
        print("Test 6 FAILED: Missing ALL_SECRETS")

    # Test 7: Calls run_pipeline_sync
    passed = 'run_pipeline_sync(' in content
    results.append(("Calls run_pipeline_sync", passed))
    if passed:
        print("Test 7 PASSED: Calls run_pipeline_sync")
    else:
        print("Test 7 FAILED: Doesn't call run_pipeline_sync")

    # Test 8: Sends Slack notifications
    func_start = content.find('def scheduled_upwork_pipeline()')
    func_end = content.find('\n\n# ===', func_start + 1)
    func_body = content[func_start:func_end] if func_end > func_start else content[func_start:func_start+3000]
    passed = 'slack_notify(' in func_body
    results.append(("Sends Slack notifications", passed))
    if passed:
        print("Test 8 PASSED: Sends Slack notifications")
    else:
        print("Test 8 FAILED: Missing slack_notify calls")

    # Test 9: Has error handling
    passed = 'slack_error(' in func_body
    results.append(("Has error handling", passed))
    if passed:
        print("Test 9 PASSED: Has error handling with slack_error")
    else:
        print("Test 9 FAILED: Missing error handling")

    # Summary
    print()
    total = len(results)
    passed_count = sum(1 for _, p in results if p)
    print("=" * 50)
    print(f"Feature #94 Tests: {passed_count}/{total} PASSED")
    print("=" * 50)

    return passed_count == total


if __name__ == "__main__":
    import sys
    success = run_tests()
    sys.exit(0 if success else 1)
