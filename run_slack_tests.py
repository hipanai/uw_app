#!/usr/bin/env python3
"""Run Slack approval tests for Features 46-48."""
import sys
sys.path.insert(0, 'executions')

import unittest
from test_upwork_slack_approval import (
    TestFeature46ApproveTriggersSubmission,
    TestFeature47RejectMarksRejected,
    TestFeature48EditAllowsModification,
    TestUpdateJobStatusInSheet,
    TestGetJobFromSheet,
    TestApprovalCallbackResult,
    TestProcessApprovalCallbackErrors,
)

if __name__ == '__main__':
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add test classes
    test_classes = [
        TestFeature46ApproveTriggersSubmission,
        TestFeature47RejectMarksRejected,
        TestFeature48EditAllowsModification,
        TestUpdateJobStatusInSheet,
        TestGetJobFromSheet,
        TestApprovalCallbackResult,
        TestProcessApprovalCallbackErrors,
    ]

    for test_class in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(test_class))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print(f'\n\nTests run: {result.testsRun}')
    print(f'Failures: {len(result.failures)}')
    print(f'Errors: {len(result.errors)}')

    sys.exit(0 if result.wasSuccessful() else 1)
