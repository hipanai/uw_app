#!/usr/bin/env python3
"""Test runner for Feature #96 - Retry logic with exponential backoff."""

import unittest
import sys
import os

# Add executions to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'executions'))

from test_upwork_google_retry import (
    TestGoogleRetryConfig,
    TestIsRetryableError,
    TestRetryGoogleApiCall,
    TestRetryDelays,
    TestSimulateApiFailure,
    TestWithRetryDecorator,
    TestRetryWithResult,
    TestGoogleAPICallRecorder,
    TestConvenienceFunctions,
    TestIntegrationWithDeliverableGenerator,
    TestFeature96Requirements,
)

if __name__ == "__main__":
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestGoogleRetryConfig))
    suite.addTests(loader.loadTestsFromTestCase(TestIsRetryableError))
    suite.addTests(loader.loadTestsFromTestCase(TestRetryGoogleApiCall))
    suite.addTests(loader.loadTestsFromTestCase(TestRetryDelays))
    suite.addTests(loader.loadTestsFromTestCase(TestSimulateApiFailure))
    suite.addTests(loader.loadTestsFromTestCase(TestWithRetryDecorator))
    suite.addTests(loader.loadTestsFromTestCase(TestRetryWithResult))
    suite.addTests(loader.loadTestsFromTestCase(TestGoogleAPICallRecorder))
    suite.addTests(loader.loadTestsFromTestCase(TestConvenienceFunctions))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegrationWithDeliverableGenerator))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature96Requirements))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Summary
    print("\n" + "=" * 70)
    print(f"Feature #96 Tests: {result.testsRun} total")
    print(f"  Passed: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"  Failed: {len(result.failures)}")
    print(f"  Errors: {len(result.errors)}")

    # Exit with appropriate code
    sys.exit(0 if result.wasSuccessful() else 1)
