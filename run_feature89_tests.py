#!/usr/bin/env python3
"""Run Feature #89 tests for cover letter above-the-fold format."""

import sys
import os

# Add executions to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'executions'))

import unittest
from test_upwork_deliverable_generator import TestFeature89CoverLetterAboveTheFold

if __name__ == '__main__':
    # Run the tests
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestFeature89CoverLetterAboveTheFold)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Summary
    print()
    print('='*60)
    print(f'Feature #89 Tests')
    print(f'Tests run: {result.testsRun}')
    print(f'Failures: {len(result.failures)}')
    print(f'Errors: {len(result.errors)}')
    print(f'Status: {"PASS" if result.wasSuccessful() else "FAIL"}')

    sys.exit(0 if result.wasSuccessful() else 1)
