#!/usr/bin/env python3
"""
Unit tests for upwork_deduplicator.py

Tests Features #3, #4, #5 from feature_list.json:
- Feature #3: Deduplicator can identify new jobs from Apify source
- Feature #4: Deduplicator can identify new jobs from Gmail source
- Feature #5: Deduplicator handles cross-source deduplication correctly

Run with: python executions/test_upwork_deduplicator.py
"""

import sys
import os
import json
import unittest
import tempfile
import shutil

# Add executions to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from upwork_deduplicator import LocalDeduplicator, deduplicate_jobs


class TestFeature3_ApifyDeduplication(unittest.TestCase):
    """Feature #3: Deduplicator can identify new jobs from Apify source"""

    def setUp(self):
        """Create a temporary directory for test files."""
        self.test_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.test_dir, "processed_ids.json")
        self.dedup = LocalDeduplicator(self.test_file)

    def tearDown(self):
        """Clean up temporary files."""
        shutil.rmtree(self.test_dir)

    def test_step1_add_sample_jobs(self):
        """Step 1: Add 5 sample jobs to Processed IDs"""
        # Add 5 existing jobs
        for i in range(5):
            self.dedup.add_processed_id(f"~existing_{i}", "apify")

        processed = self.dedup.get_processed_ids()
        self.assertEqual(len(processed), 5)

    def test_step2_3_identify_new_jobs(self):
        """Steps 2-3: Run deduplicator with 10 jobs, verify only 5 new returned"""
        # Add 5 existing jobs
        for i in range(5):
            self.dedup.add_processed_id(f"~existing_{i}", "apify")

        # Create batch of 10 jobs (5 existing + 5 new)
        jobs = []
        for i in range(5):
            jobs.append({"job_id": f"~existing_{i}", "source": "apify", "title": f"Existing Job {i}"})
        for i in range(5):
            jobs.append({"job_id": f"~new_{i}", "source": "apify", "title": f"New Job {i}"})

        # Deduplicate
        new_jobs, duplicates = deduplicate_jobs(jobs, self.dedup, add_new=True)

        # Verify only 5 new jobs returned
        self.assertEqual(len(new_jobs), 5)
        self.assertEqual(len(duplicates), 5)

        # Verify new jobs are the correct ones
        new_ids = [j['job_id'] for j in new_jobs]
        for i in range(5):
            self.assertIn(f"~new_{i}", new_ids)

    def test_step4_all_jobs_in_processed(self):
        """Step 4: Verify all 10 jobs are now in Processed IDs sheet"""
        # Add 5 existing jobs
        for i in range(5):
            self.dedup.add_processed_id(f"~existing_{i}", "apify")

        # Create batch of 10 jobs
        jobs = []
        for i in range(5):
            jobs.append({"job_id": f"~existing_{i}", "source": "apify"})
        for i in range(5):
            jobs.append({"job_id": f"~new_{i}", "source": "apify"})

        # Deduplicate (adds new jobs)
        deduplicate_jobs(jobs, self.dedup, add_new=True)

        # Verify all 10 are now processed
        processed = self.dedup.get_processed_ids()
        self.assertEqual(len(processed), 10)

        for i in range(5):
            self.assertIn(f"~existing_{i}", processed)
            self.assertIn(f"~new_{i}", processed)


class TestFeature4_GmailDeduplication(unittest.TestCase):
    """Feature #4: Deduplicator can identify new jobs from Gmail source"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.test_dir, "processed_ids.json")
        self.dedup = LocalDeduplicator(self.test_file)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_step1_add_gmail_jobs(self):
        """Step 1: Add 3 sample jobs with source='gmail'"""
        for i in range(3):
            self.dedup.add_processed_id(f"~gmail_existing_{i}", "gmail")

        processed = self.dedup.get_processed_ids()
        self.assertEqual(len(processed), 3)

        # Verify source is gmail
        for job_id, data in processed.items():
            self.assertEqual(data['source'], 'gmail')

    def test_step2_3_identify_new_gmail_jobs(self):
        """Steps 2-3: Run with 6 Gmail jobs, verify only 3 new returned"""
        # Add 3 existing Gmail jobs
        for i in range(3):
            self.dedup.add_processed_id(f"~gmail_existing_{i}", "gmail")

        # Create batch of 6 jobs (3 existing + 3 new)
        jobs = []
        for i in range(3):
            jobs.append({"job_id": f"~gmail_existing_{i}", "source": "gmail"})
        for i in range(3):
            jobs.append({"job_id": f"~gmail_new_{i}", "source": "gmail"})

        new_jobs, duplicates = deduplicate_jobs(jobs, self.dedup, add_new=True)

        self.assertEqual(len(new_jobs), 3)
        self.assertEqual(len(duplicates), 3)

    def test_step4_source_recorded_correctly(self):
        """Step 4: Verify source='gmail' is recorded for new jobs"""
        jobs = [
            {"job_id": "~gmail_job_1", "source": "gmail"},
            {"job_id": "~gmail_job_2", "source": "gmail"},
        ]

        deduplicate_jobs(jobs, self.dedup, add_new=True)

        processed = self.dedup.get_processed_ids()

        self.assertEqual(processed["~gmail_job_1"]['source'], 'gmail')
        self.assertEqual(processed["~gmail_job_2"]['source'], 'gmail')


class TestFeature5_CrossSourceDeduplication(unittest.TestCase):
    """Feature #5: Deduplicator handles cross-source deduplication correctly"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.test_dir, "processed_ids.json")
        self.dedup = LocalDeduplicator(self.test_file)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_step1_add_apify_job(self):
        """Step 1: Add job_id='123' from Apify to Processed IDs"""
        self.dedup.add_processed_id("~123", "apify")

        processed = self.dedup.get_processed_ids()
        self.assertIn("~123", processed)
        self.assertEqual(processed["~123"]['source'], 'apify')

    def test_step2_3_same_job_from_gmail_is_duplicate(self):
        """Steps 2-3: Same job from Gmail is marked as duplicate"""
        # First, add from Apify
        self.dedup.add_processed_id("~123", "apify")

        # Now try to add same job from Gmail
        jobs = [{"job_id": "~123", "source": "gmail"}]

        new_jobs, duplicates = deduplicate_jobs(jobs, self.dedup, add_new=True)

        # Should be marked as duplicate
        self.assertEqual(len(new_jobs), 0)
        self.assertEqual(len(duplicates), 1)

    def test_step4_original_source_preserved(self):
        """Step 4: Original source='apify' is preserved"""
        # Add from Apify first
        self.dedup.add_processed_id("~123", "apify")

        # Try to process same job from Gmail
        jobs = [{"job_id": "~123", "source": "gmail"}]
        deduplicate_jobs(jobs, self.dedup, add_new=True)

        # Source should still be 'apify'
        processed = self.dedup.get_processed_ids()
        self.assertEqual(processed["~123"]['source'], 'apify')


class TestDeduplicatorEdgeCases(unittest.TestCase):
    """Additional edge case tests."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.test_dir, "processed_ids.json")
        self.dedup = LocalDeduplicator(self.test_file)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_empty_job_list(self):
        """Deduplicator handles empty job list."""
        new_jobs, duplicates = deduplicate_jobs([], self.dedup)
        self.assertEqual(len(new_jobs), 0)
        self.assertEqual(len(duplicates), 0)

    def test_job_with_id_field_instead_of_job_id(self):
        """Deduplicator accepts 'id' field as alternative to 'job_id'."""
        jobs = [{"id": "~alt_id_123", "source": "apify"}]

        new_jobs, _ = deduplicate_jobs(jobs, self.dedup, add_new=True)

        self.assertEqual(len(new_jobs), 1)
        self.assertTrue(self.dedup.is_processed("~alt_id_123"))

    def test_batch_processing_no_duplicates_within_batch(self):
        """Same job appearing twice in batch is handled correctly."""
        jobs = [
            {"job_id": "~same_job", "source": "apify"},
            {"job_id": "~same_job", "source": "apify"},  # Duplicate in same batch
        ]

        new_jobs, duplicates = deduplicate_jobs(jobs, self.dedup, add_new=True)

        # First occurrence is new, second is duplicate
        self.assertEqual(len(new_jobs), 1)
        self.assertEqual(len(duplicates), 1)

    def test_clear_and_reprocess(self):
        """After clearing, jobs can be processed again."""
        self.dedup.add_processed_id("~job_to_clear", "apify")
        self.assertTrue(self.dedup.is_processed("~job_to_clear"))

        self.dedup.clear()
        self.assertFalse(self.dedup.is_processed("~job_to_clear"))


def run_tests():
    """Run all tests and return success status."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestFeature3_ApifyDeduplication))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature4_GmailDeduplication))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature5_CrossSourceDeduplication))
    suite.addTests(loader.loadTestsFromTestCase(TestDeduplicatorEdgeCases))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return len(result.failures) == 0 and len(result.errors) == 0


if __name__ == "__main__":
    success = run_tests()

    if success:
        print("\n" + "=" * 60)
        print("ALL DEDUPLICATOR TESTS PASSED!")
        print("=" * 60)
        print("\nFeatures verified:")
        print("  - Feature #3: Apify source deduplication")
        print("  - Feature #4: Gmail source deduplication")
        print("  - Feature #5: Cross-source deduplication")
        sys.exit(0)
    else:
        print("\n" + "=" * 60)
        print("SOME TESTS FAILED")
        print("=" * 60)
        sys.exit(1)
