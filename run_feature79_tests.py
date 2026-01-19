#!/usr/bin/env python3
"""Run Feature #79 batch update tests."""

import sys
sys.path.insert(0, 'executions')

import unittest
from test_upwork_pipeline_orchestrator import TestFeature79BatchUpdates

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestFeature79BatchUpdates)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
