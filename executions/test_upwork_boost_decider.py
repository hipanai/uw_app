#!/usr/bin/env python3
"""
Tests for upwork_boost_decider.py

Tests cover:
- Feature #39: Boost decider can analyze job quality signals
- Feature #40: Boost decider recommends boost for high-value clients
- Feature #41: Boost decider does not recommend boost for new clients
"""

import os
import sys
import json
import unittest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import asdict

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from executions.upwork_boost_decider import (
    BoostDecision,
    create_boost_prompt,
    parse_boost_response,
    rule_based_boost_decision,
    merge_decision_with_job,
    decide_boost_sync,
    HIGH_VALUE_SPEND_THRESHOLD,
    MEDIUM_VALUE_SPEND_THRESHOLD,
    MIN_HIRES_FOR_BOOST,
    NEW_CLIENT_SPEND_THRESHOLD
)


class TestBoostDecision(unittest.TestCase):
    """Test BoostDecision dataclass."""

    def test_boost_decision_creation(self):
        """Test creating a BoostDecision."""
        decision = BoostDecision(
            job_id='test123',
            boost_decision=True,
            boost_reasoning='High-value client',
            confidence='high',
            client_quality_score=85
        )

        self.assertEqual(decision.job_id, 'test123')
        self.assertTrue(decision.boost_decision)
        self.assertEqual(decision.boost_reasoning, 'High-value client')
        self.assertEqual(decision.confidence, 'high')
        self.assertEqual(decision.client_quality_score, 85)

    def test_boost_decision_to_dict(self):
        """Test BoostDecision serialization."""
        decision = BoostDecision(
            job_id='test456',
            boost_decision=False,
            boost_reasoning='New client',
            confidence='medium',
            client_quality_score=30
        )

        d = decision.to_dict()
        self.assertIsInstance(d, dict)
        self.assertEqual(d['job_id'], 'test456')
        self.assertFalse(d['boost_decision'])


class TestCreateBoostPrompt(unittest.TestCase):
    """Test prompt creation."""

    def test_prompt_contains_job_fields(self):
        """Test that prompt includes all relevant job fields."""
        job = {
            'job_id': 'job123',
            'title': 'AI Automation Expert',
            'budget_type': 'fixed',
            'budget_min': 500,
            'budget_max': 1000,
            'client_spent': 15000,
            'client_hires': 12,
            'payment_verified': True,
            'client_country': 'United States',
            'fit_score': 85
        }

        prompt = create_boost_prompt(job)

        self.assertIn('AI Automation Expert', prompt)
        self.assertIn('15000', prompt)
        self.assertIn('12', prompt)
        self.assertIn('True', prompt)
        self.assertIn('United States', prompt)
        self.assertIn('85', prompt)

    def test_prompt_handles_missing_fields(self):
        """Test that prompt handles missing job fields gracefully."""
        job = {'job_id': 'minimal'}

        prompt = create_boost_prompt(job)

        # Should not raise an error
        self.assertIn('No title', prompt)
        self.assertIn('unknown', prompt.lower())


class TestParseBoostResponse(unittest.TestCase):
    """Test response parsing."""

    def test_parse_valid_json(self):
        """Test parsing valid JSON response."""
        response = '{"boost_decision": true, "reasoning": "High value client", "confidence": "high", "client_quality_score": 90}'

        boost, reasoning, confidence, score = parse_boost_response(response)

        self.assertTrue(boost)
        self.assertEqual(reasoning, 'High value client')
        self.assertEqual(confidence, 'high')
        self.assertEqual(score, 90)

    def test_parse_json_with_markdown(self):
        """Test parsing JSON wrapped in markdown code blocks."""
        response = '''```json
{"boost_decision": false, "reasoning": "New client", "confidence": "medium", "client_quality_score": 40}
```'''

        boost, reasoning, confidence, score = parse_boost_response(response)

        self.assertFalse(boost)
        self.assertEqual(reasoning, 'New client')

    def test_parse_invalid_confidence_defaults_to_medium(self):
        """Test that invalid confidence values default to medium."""
        response = '{"boost_decision": true, "reasoning": "Test", "confidence": "invalid", "client_quality_score": 50}'

        boost, reasoning, confidence, score = parse_boost_response(response)

        self.assertEqual(confidence, 'medium')

    def test_parse_score_clamping(self):
        """Test that scores are clamped to 0-100 range."""
        response = '{"boost_decision": true, "reasoning": "Test", "confidence": "high", "client_quality_score": 150}'

        boost, reasoning, confidence, score = parse_boost_response(response)

        self.assertEqual(score, 100)

    def test_parse_fallback_extraction(self):
        """Test fallback regex extraction for malformed responses."""
        response = 'The boost_decision: true because client is good'

        boost, reasoning, confidence, score = parse_boost_response(response)

        self.assertTrue(boost)
        self.assertEqual(confidence, 'low')


class TestFeature39QualitySignals(unittest.TestCase):
    """
    Feature #39: Boost decider can analyze job quality signals

    Steps:
    - Provide job with high client_spent and many client_hires
    - Run boost decider
    - Verify boost_decision is returned (true/false)
    - Verify boost_reasoning explains decision
    """

    def test_analyzes_high_client_spent(self):
        """Test that high client_spent is analyzed and affects decision."""
        job = {
            'job_id': 'quality1',
            'title': 'Test Job',
            'client_spent': 15000,
            'client_hires': 20,
            'payment_verified': True
        }

        decision = rule_based_boost_decision(job)

        self.assertIsInstance(decision, BoostDecision)
        self.assertIn('job_id', asdict(decision))
        self.assertIn('boost_decision', asdict(decision))
        self.assertIn('boost_reasoning', asdict(decision))
        # High spend + verified should result in boost
        self.assertTrue(decision.boost_decision)

    def test_analyzes_client_hires(self):
        """Test that client_hires is analyzed and affects decision."""
        job = {
            'job_id': 'quality2',
            'title': 'Test Job',
            'client_spent': 5000,
            'client_hires': 15,
            'payment_verified': True
        }

        decision = rule_based_boost_decision(job)

        # With good spend and many hires, should boost
        self.assertTrue(decision.boost_decision)
        self.assertIn('hires', decision.boost_reasoning.lower())

    def test_analyzes_payment_verified(self):
        """Test that payment_verified is analyzed and affects decision."""
        # Job with good stats but unverified payment
        job = {
            'job_id': 'quality3',
            'title': 'Test Job',
            'client_spent': 8000,
            'client_hires': 10,
            'payment_verified': False
        }

        decision = rule_based_boost_decision(job)

        # Unverified payment should prevent boost recommendation
        self.assertFalse(decision.boost_decision)
        self.assertIn('verif', decision.boost_reasoning.lower())

    def test_returns_boost_decision_boolean(self):
        """Test that boost_decision is always a boolean."""
        jobs = [
            {'job_id': 'bool1', 'client_spent': 20000, 'client_hires': 10, 'payment_verified': True},
            {'job_id': 'bool2', 'client_spent': 0, 'client_hires': 0, 'payment_verified': False},
            {'job_id': 'bool3', 'client_spent': 5000, 'client_hires': 3, 'payment_verified': True}
        ]

        for job in jobs:
            decision = rule_based_boost_decision(job)
            self.assertIsInstance(decision.boost_decision, bool)

    def test_returns_reasoning_string(self):
        """Test that boost_reasoning is always a non-empty string."""
        job = {
            'job_id': 'reason1',
            'client_spent': 1000,
            'client_hires': 5,
            'payment_verified': True
        }

        decision = rule_based_boost_decision(job)

        self.assertIsInstance(decision.boost_reasoning, str)
        self.assertGreater(len(decision.boost_reasoning), 10)

    def test_quality_score_calculated(self):
        """Test that client_quality_score is calculated from signals."""
        # High quality client
        high_job = {
            'job_id': 'score1',
            'client_spent': 50000,
            'client_hires': 30,
            'payment_verified': True
        }

        # Low quality client
        low_job = {
            'job_id': 'score2',
            'client_spent': 50,
            'client_hires': 0,
            'payment_verified': False
        }

        high_decision = rule_based_boost_decision(high_job)
        low_decision = rule_based_boost_decision(low_job)

        self.assertGreater(high_decision.client_quality_score, low_decision.client_quality_score)
        self.assertGreaterEqual(high_decision.client_quality_score, 80)
        self.assertLessEqual(low_decision.client_quality_score, 30)


class TestFeature40HighValueClients(unittest.TestCase):
    """
    Feature #40: Boost decider recommends boost for high-value clients

    Steps:
    - Provide job with client_spent > $10000
    - Provide job with payment_verified = true
    - Run boost decider
    - Verify boost_decision = true
    """

    def test_recommends_boost_for_high_spend_verified(self):
        """Test boost recommendation for client_spent > $10000 AND payment_verified."""
        job = {
            'job_id': 'highvalue1',
            'title': 'Enterprise AI Project',
            'client_spent': 15000,
            'client_hires': 8,
            'payment_verified': True
        }

        decision = rule_based_boost_decision(job)

        self.assertTrue(decision.boost_decision)
        self.assertEqual(decision.confidence, 'high')

    def test_recommends_boost_for_very_high_spender(self):
        """Test boost recommendation for very high spender ($50k+)."""
        job = {
            'job_id': 'highvalue2',
            'title': 'Major Automation Project',
            'client_spent': 75000,
            'client_hires': 25,
            'payment_verified': True
        }

        decision = rule_based_boost_decision(job)

        self.assertTrue(decision.boost_decision)
        self.assertGreaterEqual(decision.client_quality_score, 90)

    def test_high_spend_unverified_no_boost(self):
        """Test that high spend WITHOUT verified payment doesn't get boost."""
        job = {
            'job_id': 'highvalue3',
            'title': 'Big Project',
            'client_spent': 20000,
            'client_hires': 15,
            'payment_verified': False  # Not verified!
        }

        decision = rule_based_boost_decision(job)

        # Should not boost unverified client even with high spend
        self.assertFalse(decision.boost_decision)

    def test_threshold_exact_value(self):
        """Test behavior at exactly $10000 threshold."""
        job = {
            'job_id': 'threshold1',
            'title': 'Threshold Test',
            'client_spent': 10000,  # Exactly at threshold
            'client_hires': 5,
            'payment_verified': True
        }

        decision = rule_based_boost_decision(job)

        # At threshold, should boost (>= 10000)
        self.assertTrue(decision.boost_decision)

    def test_just_below_threshold(self):
        """Test behavior just below $10000 threshold."""
        job = {
            'job_id': 'threshold2',
            'title': 'Below Threshold Test',
            'client_spent': 9999,  # Just below threshold
            'client_hires': 5,
            'payment_verified': True
        }

        decision = rule_based_boost_decision(job)

        # Just below threshold may or may not boost based on other factors
        # but should have medium confidence at most
        self.assertIn(decision.confidence, ['medium', 'low'])


class TestFeature41NewClients(unittest.TestCase):
    """
    Feature #41: Boost decider does not recommend boost for new clients

    Steps:
    - Provide job with client_spent = $0
    - Provide job with client_hires = 0
    - Run boost decider
    - Verify boost_decision = false or qualified
    """

    def test_no_boost_for_zero_spend_zero_hires(self):
        """Test no boost for brand new client ($0 spent, 0 hires)."""
        job = {
            'job_id': 'newclient1',
            'title': 'First Project',
            'client_spent': 0,
            'client_hires': 0,
            'payment_verified': True
        }

        decision = rule_based_boost_decision(job)

        self.assertFalse(decision.boost_decision)
        self.assertEqual(decision.confidence, 'high')
        self.assertIn('new', decision.boost_reasoning.lower())

    def test_no_boost_for_very_low_spend(self):
        """Test no boost for client with very low spend (< $100)."""
        job = {
            'job_id': 'newclient2',
            'title': 'Small Project',
            'client_spent': 50,
            'client_hires': 0,
            'payment_verified': True
        }

        decision = rule_based_boost_decision(job)

        self.assertFalse(decision.boost_decision)

    def test_new_client_with_unverified_payment(self):
        """Test handling of new client with unverified payment (double negative)."""
        job = {
            'job_id': 'newclient3',
            'title': 'Risky Project',
            'client_spent': 0,
            'client_hires': 0,
            'payment_verified': False
        }

        decision = rule_based_boost_decision(job)

        self.assertFalse(decision.boost_decision)
        self.assertEqual(decision.confidence, 'high')
        self.assertLessEqual(decision.client_quality_score, 20)

    def test_low_quality_score_for_new_clients(self):
        """Test that new clients get low quality scores."""
        job = {
            'job_id': 'newclient4',
            'title': 'Unknown Client Project',
            'client_spent': 0,
            'client_hires': 0,
            'payment_verified': True
        }

        decision = rule_based_boost_decision(job)

        # Even with verified payment, new client should have low score
        self.assertLessEqual(decision.client_quality_score, 50)

    def test_reasoning_explains_new_client(self):
        """Test that reasoning explains why new client doesn't get boost."""
        job = {
            'job_id': 'newclient5',
            'title': 'New Client Test',
            'client_spent': 0,
            'client_hires': 0,
            'payment_verified': True
        }

        decision = rule_based_boost_decision(job)

        # Reasoning should mention new/unproven/history
        reasoning_lower = decision.boost_reasoning.lower()
        self.assertTrue(
            any(word in reasoning_lower for word in ['new', 'unproven', 'history', 'no spending']),
            f"Reasoning should explain new client status: {decision.boost_reasoning}"
        )


class TestMergeDecisionWithJob(unittest.TestCase):
    """Test merging decision with job data."""

    def test_merge_adds_all_fields(self):
        """Test that merge adds all boost decision fields."""
        job = {
            'job_id': 'merge1',
            'title': 'Test Job',
            'client_spent': 10000
        }

        decision = BoostDecision(
            job_id='merge1',
            boost_decision=True,
            boost_reasoning='Good client',
            confidence='high',
            client_quality_score=85
        )

        merged = merge_decision_with_job(job, decision)

        self.assertEqual(merged['job_id'], 'merge1')
        self.assertEqual(merged['title'], 'Test Job')
        self.assertEqual(merged['client_spent'], 10000)
        self.assertTrue(merged['boost_decision'])
        self.assertEqual(merged['boost_reasoning'], 'Good client')
        self.assertEqual(merged['boost_confidence'], 'high')
        self.assertEqual(merged['client_quality_score'], 85)

    def test_merge_preserves_original_job_fields(self):
        """Test that merge preserves all original job fields."""
        job = {
            'job_id': 'merge2',
            'title': 'Test Job',
            'description': 'Long description here',
            'budget_type': 'fixed',
            'budget_min': 500,
            'extra_field': 'should be preserved'
        }

        decision = BoostDecision(
            job_id='merge2',
            boost_decision=False,
            boost_reasoning='Test',
            confidence='medium',
            client_quality_score=50
        )

        merged = merge_decision_with_job(job, decision)

        self.assertEqual(merged['extra_field'], 'should be preserved')
        self.assertEqual(merged['budget_type'], 'fixed')


class TestStringParsing(unittest.TestCase):
    """Test handling of string values for client metrics."""

    def test_parse_string_client_spent(self):
        """Test parsing client_spent as string with formatting."""
        job = {
            'job_id': 'string1',
            'client_spent': '$15,000',  # String with $ and comma
            'client_hires': 10,
            'payment_verified': True
        }

        decision = rule_based_boost_decision(job)

        # Should recognize as high-value client
        self.assertTrue(decision.boost_decision)

    def test_parse_string_client_hires(self):
        """Test parsing client_hires as string."""
        job = {
            'job_id': 'string2',
            'client_spent': 15000,
            'client_hires': '10+',  # String with plus
            'payment_verified': True
        }

        decision = rule_based_boost_decision(job)

        self.assertTrue(decision.boost_decision)

    def test_parse_string_payment_verified(self):
        """Test parsing payment_verified as string."""
        job = {
            'job_id': 'string3',
            'client_spent': 15000,
            'client_hires': 10,
            'payment_verified': 'Yes'  # String instead of bool
        }

        decision = rule_based_boost_decision(job)

        self.assertTrue(decision.boost_decision)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions."""

    def test_empty_job(self):
        """Test handling of job with minimal data."""
        job = {'job_id': 'empty1'}

        decision = rule_based_boost_decision(job)

        self.assertIsInstance(decision, BoostDecision)
        self.assertFalse(decision.boost_decision)

    def test_none_values(self):
        """Test handling of None values in job fields."""
        job = {
            'job_id': 'none1',
            'client_spent': None,
            'client_hires': None,
            'payment_verified': None
        }

        decision = rule_based_boost_decision(job)

        # Should handle gracefully, treating None as 0/False
        self.assertFalse(decision.boost_decision)

    def test_negative_values(self):
        """Test handling of negative values (shouldn't happen but be safe)."""
        job = {
            'job_id': 'negative1',
            'client_spent': -1000,  # Invalid
            'client_hires': -5,  # Invalid
            'payment_verified': True
        }

        decision = rule_based_boost_decision(job)

        # Should handle gracefully
        self.assertIsInstance(decision.boost_decision, bool)


class TestAPIIntegration(unittest.TestCase):
    """Test API integration with mocked client."""

    @patch('executions.upwork_boost_decider.BOOST_DECISION_MODEL', 'claude-sonnet-4-20250514')
    def test_decide_boost_sync_calls_api(self):
        """Test that decide_boost_sync makes correct API call."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.content = [Mock(text='{"boost_decision": true, "reasoning": "Test", "confidence": "high", "client_quality_score": 80}')]
        mock_client.messages.create.return_value = mock_response

        job = {
            'job_id': 'api1',
            'title': 'Test Job',
            'client_spent': 15000,
            'client_hires': 10,
            'payment_verified': True
        }

        decision = decide_boost_sync(job, mock_client)

        # Verify API was called
        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args[1]
        self.assertEqual(call_kwargs['model'], 'claude-sonnet-4-20250514')
        self.assertIn('messages', call_kwargs)

        # Verify decision
        self.assertTrue(decision.boost_decision)
        self.assertEqual(decision.confidence, 'high')

    def test_decide_boost_sync_handles_api_error(self):
        """Test that decide_boost_sync handles API errors gracefully."""
        mock_client = Mock()
        mock_client.messages.create.side_effect = Exception("API Error")

        job = {'job_id': 'api_error1', 'title': 'Test'}

        decision = decide_boost_sync(job, mock_client)

        # Should return a safe default
        self.assertFalse(decision.boost_decision)
        self.assertIn('error', decision.boost_reasoning.lower())


if __name__ == '__main__':
    unittest.main()
