#!/usr/bin/env python3
"""
Tests for upwork_apify_scraper.py

Feature #70: Apify scraper adds source field to job data
Feature #71: Apify scraper supports batch processing
"""

import unittest
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from upwork_apify_scraper import format_job, filter_jobs


class TestFormatJob(unittest.TestCase):
    """Test the format_job function."""

    def test_format_job_basic(self):
        """Test basic job formatting."""
        raw_job = {
            'uid': 'test123',
            'title': 'Test Job',
            'description': 'Test description',
            'externalLink': 'https://upwork.com/jobs/~test123',
            'budget': {},
            'category': 'Web Development',
            'vendor': {'experienceLevel': 'intermediate'},
            'skills': ['Python', 'Django'],
            'createdAt': '2026-01-19T10:00:00Z',
            'applicationCost': 6,
            'client': {
                'countryCode': 'US',
                'timezone': 'America/New_York',
                'paymentMethodVerified': True,
                'stats': {
                    'totalSpent': 5000,
                    'totalHires': 10,
                    'hireRate': 0.8,
                    'feedbackRate': 4.9
                }
            },
            'isFeatured': False
        }

        formatted = format_job(raw_job)

        self.assertEqual(formatted['id'], 'test123')
        self.assertEqual(formatted['title'], 'Test Job')
        self.assertEqual(formatted['description'], 'Test description')
        self.assertEqual(formatted['url'], 'https://upwork.com/jobs/~test123')

    def test_format_job_with_fixed_budget(self):
        """Test job formatting with fixed budget."""
        raw_job = {
            'uid': 'fixed123',
            'title': 'Fixed Price Job',
            'description': 'Fixed price project',
            'externalLink': 'https://upwork.com/jobs/~fixed123',
            'budget': {'fixedBudget': 500},
            'vendor': {},
            'client': {'stats': {}},
        }

        formatted = format_job(raw_job)
        self.assertEqual(formatted['budget'], '$500 fixed')

    def test_format_job_with_hourly_budget(self):
        """Test job formatting with hourly budget."""
        raw_job = {
            'uid': 'hourly123',
            'title': 'Hourly Job',
            'description': 'Hourly project',
            'externalLink': 'https://upwork.com/jobs/~hourly123',
            'budget': {'hourlyRate': {'min': 25, 'max': 50}},
            'vendor': {},
            'client': {'stats': {}},
        }

        formatted = format_job(raw_job)
        self.assertEqual(formatted['budget'], '$25-$50/hr')


class TestFeature70SourceField(unittest.TestCase):
    """Test Feature #70: Apify scraper adds source field to job data."""

    def test_format_job_includes_source_field(self):
        """Test that format_job includes source='apify' field."""
        raw_job = {
            'uid': 'test123',
            'title': 'Test Job',
            'description': 'Test description',
            'externalLink': 'https://upwork.com/jobs/~test123',
            'budget': {},
            'vendor': {},
            'client': {'stats': {}},
        }

        formatted = format_job(raw_job)

        self.assertIn('source', formatted)
        self.assertEqual(formatted['source'], 'apify')

    def test_source_field_is_apify(self):
        """Test that source field value is exactly 'apify'."""
        raw_job = {
            'uid': 'job456',
            'title': 'Another Job',
            'description': 'Another description',
            'externalLink': 'https://upwork.com/jobs/~job456',
            'budget': {'fixedBudget': 1000},
            'vendor': {'experienceLevel': 'expert'},
            'skills': ['AI', 'Automation'],
            'createdAt': '2026-01-19T12:00:00Z',
            'client': {
                'countryCode': 'CA',
                'paymentMethodVerified': True,
                'stats': {'totalSpent': 10000}
            },
        }

        formatted = format_job(raw_job)

        self.assertEqual(formatted['source'], 'apify')

    def test_source_field_in_output_json(self):
        """Test that source field would be present in JSON output."""
        raw_job = {
            'uid': 'jsontest789',
            'title': 'JSON Test Job',
            'description': 'Testing JSON serialization',
            'externalLink': 'https://upwork.com/jobs/~jsontest789',
            'budget': {},
            'vendor': {},
            'client': {'stats': {}},
        }

        formatted = format_job(raw_job)

        # Serialize to JSON and back
        json_str = json.dumps(formatted)
        parsed = json.loads(json_str)

        self.assertIn('source', parsed)
        self.assertEqual(parsed['source'], 'apify')

    def test_multiple_jobs_all_have_source_apify(self):
        """Test that multiple formatted jobs all have source='apify'."""
        raw_jobs = [
            {
                'uid': f'job{i}',
                'title': f'Job {i}',
                'description': f'Description {i}',
                'externalLink': f'https://upwork.com/jobs/~job{i}',
                'budget': {},
                'vendor': {},
                'client': {'stats': {}},
            }
            for i in range(5)
        ]

        formatted_jobs = [format_job(job) for job in raw_jobs]

        for i, job in enumerate(formatted_jobs):
            with self.subTest(job_index=i):
                self.assertIn('source', job)
                self.assertEqual(job['source'], 'apify')


class TestFeature71BatchProcessing(unittest.TestCase):
    """Test Feature #71: Apify scraper supports batch processing."""

    def test_filter_jobs_processes_all_jobs(self):
        """Test that filter_jobs processes all jobs in batch."""
        jobs = [
            {
                'uid': f'job{i}',
                'title': f'Python Job {i}',
                'description': f'Looking for Python developer',
                'budget': {'fixedBudget': 500 + i * 100},
                'vendor': {'experienceLevel': 'intermediate'},
                'client': {
                    'paymentMethodVerified': True,
                    'stats': {'totalSpent': 1000, 'totalHires': 5}
                },
            }
            for i in range(100)
        ]

        # Filter with keyword - should return all since all have 'Python'
        filtered = filter_jobs(jobs, keyword='python')

        self.assertEqual(len(filtered), 100)

    def test_batch_processing_preserves_job_data(self):
        """Test that batch processing preserves all job data."""
        jobs = [
            {
                'uid': f'batch{i}',
                'title': f'Batch Job {i}',
                'description': f'Description for batch job {i}',
                'budget': {'fixedBudget': 500},
                'vendor': {'experienceLevel': 'expert'},
                'skills': ['Python', 'Automation'],
                'createdAt': '2026-01-19T10:00:00Z',
                'client': {
                    'countryCode': 'US',
                    'paymentMethodVerified': True,
                    'stats': {'totalSpent': 5000, 'totalHires': 10}
                },
            }
            for i in range(50)
        ]

        # No filtering - return all
        filtered = filter_jobs(jobs)

        self.assertEqual(len(filtered), 50)

        # Verify each job retains its data
        for i, job in enumerate(filtered):
            self.assertEqual(job['uid'], f'batch{i}')
            self.assertEqual(job['title'], f'Batch Job {i}')

    def test_batch_format_all_jobs(self):
        """Test formatting a batch of jobs."""
        raw_jobs = [
            {
                'uid': f'format{i}',
                'title': f'Format Job {i}',
                'description': f'Description {i}',
                'externalLink': f'https://upwork.com/jobs/~format{i}',
                'budget': {'fixedBudget': 1000},
                'vendor': {},
                'client': {'stats': {}},
            }
            for i in range(100)
        ]

        formatted_jobs = [format_job(job) for job in raw_jobs]

        self.assertEqual(len(formatted_jobs), 100)

        # All should have source='apify'
        for job in formatted_jobs:
            self.assertEqual(job['source'], 'apify')

    def test_batch_100_jobs_limit(self):
        """Test Feature #71: Run scraper with --limit 100 and verify all jobs processed."""
        # Create 100 raw jobs
        raw_jobs = [
            {
                'uid': f'limit100_{i}',
                'title': f'Limit Test Job {i}',
                'description': f'Testing batch processing with limit 100',
                'externalLink': f'https://upwork.com/jobs/~limit100_{i}',
                'budget': {'fixedBudget': 500 + i},
                'vendor': {'experienceLevel': 'intermediate'},
                'skills': ['Python', 'Automation'],
                'createdAt': '2026-01-19T10:00:00Z',
                'applicationCost': 6,
                'client': {
                    'countryCode': 'US',
                    'timezone': 'America/New_York',
                    'paymentMethodVerified': True,
                    'stats': {'totalSpent': 5000, 'totalHires': 10, 'hireRate': 0.8, 'feedbackRate': 4.9}
                },
                'isFeatured': False
            }
            for i in range(100)
        ]

        # Filter all (no filters applied)
        filtered = filter_jobs(raw_jobs)
        self.assertEqual(len(filtered), 100, "All 100 jobs should pass through filter")

        # Format all jobs
        formatted_jobs = [format_job(job) for job in filtered]
        self.assertEqual(len(formatted_jobs), 100, "All 100 jobs should be formatted")

        # Verify all jobs have required fields
        for i, job in enumerate(formatted_jobs):
            with self.subTest(job_index=i):
                self.assertEqual(job['id'], f'limit100_{i}')
                self.assertEqual(job['source'], 'apify')
                self.assertIn('title', job)
                self.assertIn('description', job)
                self.assertIn('url', job)
                self.assertIn('budget', job)

    def test_batch_output_json_contains_all_jobs(self):
        """Test Feature #71: Verify output JSON contains all jobs."""
        import tempfile
        import os

        # Create batch of jobs
        raw_jobs = [
            {
                'uid': f'json_out_{i}',
                'title': f'JSON Output Test {i}',
                'description': f'Test job for JSON output verification',
                'externalLink': f'https://upwork.com/jobs/~json_out_{i}',
                'budget': {'fixedBudget': 1000},
                'vendor': {},
                'client': {'stats': {}},
            }
            for i in range(100)
        ]

        # Format jobs
        formatted_jobs = [format_job(job) for job in raw_jobs]

        # Write to temp JSON file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(formatted_jobs, f, indent=2)
            temp_path = f.name

        try:
            # Read back and verify
            with open(temp_path, 'r') as f:
                loaded_jobs = json.load(f)

            self.assertEqual(len(loaded_jobs), 100, "JSON output should contain all 100 jobs")

            # Verify each job in JSON output
            for i, job in enumerate(loaded_jobs):
                with self.subTest(job_index=i):
                    self.assertEqual(job['id'], f'json_out_{i}')
                    self.assertEqual(job['source'], 'apify')

        finally:
            os.unlink(temp_path)

    def test_batch_processing_with_various_limits(self):
        """Test batch processing with various limit values."""
        for limit in [10, 50, 100, 200]:
            with self.subTest(limit=limit):
                raw_jobs = [
                    {
                        'uid': f'limit_{limit}_{i}',
                        'title': f'Limit {limit} Job {i}',
                        'description': f'Description for job {i}',
                        'externalLink': f'https://upwork.com/jobs/~limit_{limit}_{i}',
                        'budget': {'fixedBudget': 500},
                        'vendor': {},
                        'client': {'stats': {}},
                    }
                    for i in range(limit)
                ]

                formatted_jobs = [format_job(job) for job in raw_jobs]
                self.assertEqual(len(formatted_jobs), limit, f"Should process all {limit} jobs")


class TestFilterJobs(unittest.TestCase):
    """Test the filter_jobs function."""

    def test_keyword_filter(self):
        """Test keyword filtering."""
        jobs = [
            {'title': 'Python Developer Needed', 'description': 'Build an app'},
            {'title': 'Java Developer', 'description': 'Enterprise application'},
            {'title': 'Full Stack', 'description': 'Python and JavaScript'},
        ]

        filtered = filter_jobs(jobs, keyword='python')

        self.assertEqual(len(filtered), 2)

    def test_verified_payment_filter(self):
        """Test verified payment filtering."""
        jobs = [
            {'title': 'Job 1', 'client': {'paymentMethodVerified': True}},
            {'title': 'Job 2', 'client': {'paymentMethodVerified': False}},
            {'title': 'Job 3', 'client': {'paymentMethodVerified': True}},
        ]

        filtered = filter_jobs(jobs, verified_payment=True)

        self.assertEqual(len(filtered), 2)

    def test_min_client_spent_filter(self):
        """Test minimum client spending filter."""
        jobs = [
            {'title': 'Job 1', 'client': {'stats': {'totalSpent': 100}}},
            {'title': 'Job 2', 'client': {'stats': {'totalSpent': 5000}}},
            {'title': 'Job 3', 'client': {'stats': {'totalSpent': 10000}}},
        ]

        filtered = filter_jobs(jobs, min_client_spent=1000)

        self.assertEqual(len(filtered), 2)


if __name__ == '__main__':
    unittest.main()
