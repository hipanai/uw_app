#!/usr/bin/env python3
"""Test Feature #98: Job URL format conversion works correctly.

Steps:
1. Input job URL: https://www.upwork.com/jobs/~123
2. Convert to apply URL
3. Verify output: https://www.upwork.com/nx/proposals/job/~123/apply/
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from executions.upwork_submitter import job_url_to_apply_url, job_id_to_apply_url

def test_feature_98():
    """Test Feature #98: Job URL format conversion."""
    # Step 1: Input job URL
    input_url = "https://www.upwork.com/jobs/~123"

    # Step 2: Convert to apply URL
    apply_url = job_url_to_apply_url(input_url)

    # Step 3: Verify output
    expected = "https://www.upwork.com/nx/proposals/job/~123/apply/"

    print(f"Input URL:    {input_url}")
    print(f"Output URL:   {apply_url}")
    print(f"Expected:     {expected}")
    print(f"Match:        {apply_url == expected}")

    assert apply_url == expected, f"URL conversion failed: {apply_url} != {expected}"
    print("\n✓ Feature #98 test PASSED!")

    # Additional tests
    print("\nAdditional URL conversion tests:")

    # Test with job title in URL
    url_with_title = "https://www.upwork.com/jobs/AI-Automation-Expert_~01abc123"
    result = job_url_to_apply_url(url_with_title)
    expected_title = "https://www.upwork.com/nx/proposals/job/~01abc123/apply/"
    print(f"  URL with title: {url_with_title}")
    print(f"  Result:         {result}")
    print(f"  Expected:       {expected_title}")
    print(f"  Match:          {result == expected_title}")
    assert result == expected_title

    # Test job_id_to_apply_url
    job_id = "~01xyz789"
    result = job_id_to_apply_url(job_id)
    expected_id = "https://www.upwork.com/nx/proposals/job/~01xyz789/apply/"
    print(f"  Job ID:         {job_id}")
    print(f"  Result:         {result}")
    print(f"  Expected:       {expected_id}")
    print(f"  Match:          {result == expected_id}")
    assert result == expected_id

    # Test job_id without tilde
    job_id_no_tilde = "01xyz789"
    result = job_id_to_apply_url(job_id_no_tilde)
    print(f"  Job ID (no ~):  {job_id_no_tilde}")
    print(f"  Result:         {result}")
    print(f"  Expected:       {expected_id}")
    print(f"  Match:          {result == expected_id}")
    assert result == expected_id

    print("\n✓ All Feature #98 tests PASSED!")
    return True

if __name__ == "__main__":
    try:
        success = test_feature_98()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Feature #98 test FAILED: {e}")
        sys.exit(1)
