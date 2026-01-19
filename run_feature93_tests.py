#!/usr/bin/env python3
"""Test runner for Feature #93: Hedged greeting for medium confidence"""
import sys
sys.path.insert(0, 'executions')
import unittest
from test_upwork_deliverable_generator import TestFeature93HedgedGreetingForMediumConfidence

if __name__ == '__main__':
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestFeature93HedgedGreetingForMediumConfidence)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print('\n' + '='*50)
    print('Tests passed!' if result.wasSuccessful() else 'Tests failed!')
    sys.exit(0 if result.wasSuccessful() else 1)
