#!/usr/bin/env python3
"""
Run tests for Feature #100: Pipeline respects 20-30% throughput after pre-filter.

This script runs all tests related to Feature #100 and reports results.
"""

import os
import sys
import unittest

# Ensure we're in the right directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, 'executions')

def run_tests():
    """Run Feature #100 tests."""
    print("=" * 60)
    print("Feature #100: Pipeline respects 20-30% throughput after pre-filter")
    print("=" * 60)

    # Import test module
    from test_upwork_pipeline_throughput import create_test_suite

    # Create and run test suite
    suite = create_test_suite()
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Summary
    print(f"\n{'='*60}")
    print("Feature #100 Test Results")
    print(f"{'='*60}")
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")

    if result.wasSuccessful():
        print("\n[PASSED] Feature #100 tests passed!")
        return True
    else:
        print("\n[FAILED] Feature #100 tests failed!")
        if result.failures:
            print("\nFailures:")
            for test, traceback in result.failures:
                print(f"  - {test}: {traceback}")
        if result.errors:
            print("\nErrors:")
            for test, traceback in result.errors:
                print(f"  - {test}: {traceback}")
        return False


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
