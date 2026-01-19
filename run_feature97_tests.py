#!/usr/bin/env python3
"""Test runner for Feature #97: Pipeline handles Anthropic rate limits gracefully."""

import sys
import os
import unittest

# Add executions to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'executions'))

# Import all test classes
from test_upwork_anthropic_retry import (
    TestAnthropicRetryConfig,
    TestErrorClassification,
    TestIsRetryableError,
    TestGetRetryAfter,
    TestRetryAnthropicCall,
    TestRetryAnthropicCallAsync,
    TestWithAnthropicRetry,
    TestAnthropicRetryResult,
    TestRetryCallWithResult,
    TestAnthropicAPICallRecorder,
    TestConvenienceFunctions,
    TestFeature97Requirements,
    TestEdgeCases,
    TestIntegrationWithPrefilter,
)

if __name__ == '__main__':
    # Create a test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    test_classes = [
        TestAnthropicRetryConfig,
        TestErrorClassification,
        TestIsRetryableError,
        TestGetRetryAfter,
        TestRetryAnthropicCall,
        TestRetryAnthropicCallAsync,
        TestWithAnthropicRetry,
        TestAnthropicRetryResult,
        TestRetryCallWithResult,
        TestAnthropicAPICallRecorder,
        TestConvenienceFunctions,
        TestFeature97Requirements,
        TestEdgeCases,
        TestIntegrationWithPrefilter,
    ]

    for test_class in test_classes:
        tests = loader.loadTestsFromTestCase(test_class)
        suite.addTests(tests)

    # Run with verbosity
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Print summary
    print("\n" + "="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")
    print("="*70)

    if result.wasSuccessful():
        print("Feature #97 tests: ALL PASSED")
    else:
        print("Feature #97 tests: SOME FAILED")
        for failure in result.failures:
            print(f"\nFAILED: {failure[0]}")
            print(failure[1])
        for error in result.errors:
            print(f"\nERROR: {error[0]}")
            print(error[1])

    sys.exit(0 if result.wasSuccessful() else 1)
