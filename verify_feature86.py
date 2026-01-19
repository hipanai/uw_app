#!/usr/bin/env python3
"""
Quick verification script for Feature #86: Slack messages display fit score with color coding
"""
import sys
sys.path.insert(0, '/workspaces/uw_app/executions')

from upwork_slack_approval import (
    get_score_color,
    get_score_emoji,
    send_approval_message,
    JobApprovalData,
    SlackMessageResult,
    SLACK_MESSAGE_FORMAT,
)

# Test 1: Score 90 should get green color
color_90 = get_score_color(90)
expected_green = "#36a64f"
assert color_90 == expected_green, f"Score 90: Expected {expected_green}, got {color_90}"
print(f"[PASS] Score 90 -> green color: {color_90}")

# Test 2: Score 72 should get yellow color
color_72 = get_score_color(72)
expected_yellow = "#ffc107"
assert color_72 == expected_yellow, f"Score 72: Expected {expected_yellow}, got {color_72}"
print(f"[PASS] Score 72 -> yellow color: {color_72}")

# Test 3: Score 50 should get red color
color_50 = get_score_color(50)
expected_red = "#dc3545"
assert color_50 == expected_red, f"Score 50: Expected {expected_red}, got {color_50}"
print(f"[PASS] Score 50 -> red color: {color_50}")

# Test 4: No score should get gray color
color_none = get_score_color(None)
expected_gray = "#808080"
assert color_none == expected_gray, f"Score None: Expected {expected_gray}, got {color_none}"
print(f"[PASS] Score None -> gray color: {color_none}")

# Test 5: Emoji for score 90
emoji_90 = get_score_emoji(90)
assert emoji_90 == "🟢", f"Score 90 emoji: Expected 🟢, got {emoji_90}"
print(f"[PASS] Score 90 -> green emoji: {emoji_90}")

# Test 6: Emoji for score 72
emoji_72 = get_score_emoji(72)
assert emoji_72 == "🟡", f"Score 72 emoji: Expected 🟡, got {emoji_72}"
print(f"[PASS] Score 72 -> yellow emoji: {emoji_72}")

# Test 7: send_approval_message returns color in result
job = JobApprovalData(
    job_id="~test",
    title="Test Job",
    url="https://upwork.com/jobs/~test",
    fit_score=90
)
result = send_approval_message(job=job, channel="C0123456789", mock=True)
assert result.success, f"send_approval_message failed: {result.error}"
assert result.color == expected_green, f"Result color: Expected {expected_green}, got {result.color}"
print(f"[PASS] send_approval_message returns color for score 90: {result.color}")

# Test 8: SlackMessageResult has color field
result_with_color = SlackMessageResult(
    success=True,
    message_ts="123.456",
    channel="C0123456789",
    color="#ffc107"
)
assert result_with_color.color == "#ffc107", "SlackMessageResult color field not working"
print(f"[PASS] SlackMessageResult has color field: {result_with_color.color}")

# Test 9: to_dict includes color
result_dict = result_with_color.to_dict()
assert "color" in result_dict, "color not in to_dict output"
assert result_dict["color"] == "#ffc107", f"to_dict color: Expected #ffc107, got {result_dict['color']}"
print(f"[PASS] to_dict includes color: {result_dict['color']}")

print("\n=== ALL TESTS PASSED ===")
print("Feature #86: Slack messages display fit score with color coding - VERIFIED")
