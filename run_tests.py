#!/usr/bin/env python3
"""Simple test runner for Upwork pre-filter features #11-14."""

import os
import sys
import time
import asyncio

# Add execution path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from executions.upwork_prefilter import score_job_sync, filter_jobs_by_score, score_jobs_batch_async

def test_feature_13():
    """Feature #13: Pre-filter respects PREFILTER_MIN_SCORE threshold."""
    print("\n" + "="*60)
    print("Testing Feature #13: Pre-filter threshold")
    print("="*60)

    jobs_with_scores = [
        {"job_id": "1", "title": "AI Expert", "fit_score": 92, "fit_reasoning": "Excellent AI skills match"},
        {"job_id": "2", "title": "Automation Pro", "fit_score": 85, "fit_reasoning": "Strong automation fit"},
        {"job_id": "3", "title": "Workflow Builder", "fit_score": 78, "fit_reasoning": "Good workflow experience"},
        {"job_id": "4", "title": "Tech Lead", "fit_score": 72, "fit_reasoning": "Moderate tech skills match"},
        {"job_id": "5", "title": "Assistant Role", "fit_score": 65, "fit_reasoning": "Below threshold - some relevant skills"},
        {"job_id": "6", "title": "Data Entry", "fit_score": 45, "fit_reasoning": "Manual work, poor fit"},
        {"job_id": "7", "title": "Basic Admin", "fit_score": 35, "fit_reasoning": "Not relevant to AI/automation"},
        {"job_id": "8", "title": "Receptionist", "fit_score": 20, "fit_reasoning": "Complete mismatch"},
        {"job_id": "9", "title": "API Developer", "fit_score": 70, "fit_reasoning": "Exactly at threshold"},
        {"job_id": "10", "title": "Entry Level", "fit_score": 55, "fit_reasoning": "Some potential but low score"},
    ]

    min_score = 70
    passing, filtered_out = filter_jobs_by_score(jobs_with_scores, min_score=min_score)

    print(f"Threshold: {min_score}")
    print(f"Passing jobs: {len(passing)}")
    print(f"Filtered out: {len(filtered_out)}")

    # Check results
    expected_passing = 5
    expected_filtered = 5

    assert len(passing) == expected_passing, f"Expected {expected_passing} passing, got {len(passing)}"
    assert len(filtered_out) == expected_filtered, f"Expected {expected_filtered} filtered, got {len(filtered_out)}"

    for job in passing:
        assert job['fit_score'] >= min_score, f"Job {job['job_id']} score {job['fit_score']} should be >= {min_score}"

    for job in filtered_out:
        assert job['fit_score'] < min_score, f"Job {job['job_id']} score {job['fit_score']} should be < {min_score}"
        assert 'fit_reasoning' in job and len(job['fit_reasoning']) > 0

    print("Feature #13: PASSED")
    return True


def test_feature_11():
    """Feature #11: Pre-filter correctly identifies high-relevance AI/automation jobs."""
    print("\n" + "="*60)
    print("Testing Feature #11: High-relevance AI job scoring")
    print("="*60)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY not set, skipping API test")
        return None

    import anthropic

    ai_automation_job = {
        "job_id": "~feature11test",
        "title": "AI Workflow Automation Specialist - Make.com & Zapier Expert",
        "description": """
        We are looking for an experienced AI workflow automation specialist to help us
        streamline our business processes. The ideal candidate will have:

        - Deep experience with Make.com (formerly Integromat)
        - Expertise in Zapier automations
        - Knowledge of n8n and other workflow tools
        - Experience integrating AI/LLM APIs (OpenAI, Claude/Anthropic)
        - Lead generation and CRM automation skills
        - Data pipeline design and implementation

        Project involves:
        - Building automated lead scoring workflows
        - Integrating our CRM with marketing automation tools
        - Creating AI-powered email response systems
        - Setting up data synchronization between platforms

        This is a long-term engagement for the right person. We have a generous budget
        and are committed to working with a true expert.

        Budget: $2,000-5,000
        Duration: Ongoing, starting with 3-month trial
        """,
        "budget_type": "fixed",
        "budget_min": 2000,
        "budget_max": 5000,
        "client_spent": 50000,
        "client_hires": 25,
        "payment_verified": True,
        "source": "apify"
    }

    client = anthropic.Anthropic(api_key=api_key)
    result = score_job_sync(ai_automation_job, client)

    print(f"Score: {result['fit_score']}")
    print(f"Reasoning: {result['fit_reasoning']}")

    # Verify score >= 80 for high-relevance AI job
    assert result['fit_score'] >= 80, f"High-relevance AI job should score >= 80, got {result['fit_score']}"

    # Verify reasoning mentions relevant skills
    reasoning_lower = result['fit_reasoning'].lower()
    skill_keywords = ['skill', 'match', 'fit', 'automation', 'workflow', 'experience', 'make.com', 'zapier', 'ai']
    has_skill_mention = any(kw in reasoning_lower for kw in skill_keywords)
    assert has_skill_mention, f"Reasoning should mention skills match. Got: {result['fit_reasoning']}"

    print("Feature #11: PASSED")
    return True


def test_feature_12():
    """Feature #12: Pre-filter correctly identifies low-relevance non-AI jobs."""
    print("\n" + "="*60)
    print("Testing Feature #12: Low-relevance non-AI job scoring")
    print("="*60)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY not set, skipping API test")
        return None

    import anthropic

    data_entry_job = {
        "job_id": "~feature12test",
        "title": "Manual Data Entry Clerk - Simple Copy/Paste Work",
        "description": """
        Looking for someone to do manual data entry work. This is a simple task
        that involves copying information from PDF documents into our Excel spreadsheet.

        Requirements:
        - Basic computer skills
        - Attention to detail
        - Ability to type quickly
        - No special technical skills needed

        The work is straightforward - just reading PDFs and typing the information
        into the correct columns. No automation or programming required.

        Budget: $30 flat fee
        Duration: One-time task, about 10 hours

        This is entry-level work suitable for beginners.
        """,
        "budget_type": "fixed",
        "budget_min": 30,
        "budget_max": 30,
        "client_spent": 0,
        "client_hires": 0,
        "payment_verified": False,
        "source": "gmail"
    }

    client = anthropic.Anthropic(api_key=api_key)
    result = score_job_sync(data_entry_job, client)

    print(f"Score: {result['fit_score']}")
    print(f"Reasoning: {result['fit_reasoning']}")

    # Verify score < 50 for low-relevance non-AI job
    assert result['fit_score'] < 50, f"Low-relevance data entry job should score < 50, got {result['fit_score']}"

    # Verify reasoning explains low relevance
    reasoning_lower = result['fit_reasoning'].lower()
    low_relevance_indicators = ['manual', 'data entry', 'not', "doesn't", 'low', 'poor', 'mismatch',
                                'basic', 'simple', 'budget', 'skill', 'lack']
    has_low_relevance_explanation = any(ind in reasoning_lower for ind in low_relevance_indicators)
    assert has_low_relevance_explanation, f"Reasoning should explain low relevance. Got: {result['fit_reasoning']}"

    print("Feature #12: PASSED")
    return True


def test_feature_14():
    """Feature #14: Pre-filter handles batch processing efficiently."""
    print("\n" + "="*60)
    print("Testing Feature #14: Batch processing efficiency")
    print("="*60)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY not set, skipping API test")
        return None

    import anthropic

    # Generate 20 sample jobs with variety
    job_templates = [
        # High-relevance AI jobs
        {"title": "AI Automation Expert for Business Workflows",
         "description": "Need expert in Make.com, Zapier, and AI/LLM integration for workflow automation.",
         "budget_type": "fixed", "budget_min": 1000, "budget_max": 2000,
         "client_spent": 25000, "client_hires": 15, "payment_verified": True},
        {"title": "ChatGPT/Claude Integration Developer",
         "description": "Build AI chatbot using OpenAI or Anthropic APIs. Experience with n8n preferred.",
         "budget_type": "hourly", "budget_min": 50, "budget_max": 100,
         "client_spent": 50000, "client_hires": 30, "payment_verified": True},
        {"title": "Lead Generation Automation Specialist",
         "description": "Setup automated lead scraping and enrichment using Apollo.io and Instantly.",
         "budget_type": "fixed", "budget_min": 500, "budget_max": 1500,
         "client_spent": 10000, "client_hires": 8, "payment_verified": True},
        {"title": "Data Pipeline Developer - Python & APIs",
         "description": "Create automated data pipelines connecting various SaaS tools via APIs.",
         "budget_type": "fixed", "budget_min": 800, "budget_max": 1200,
         "client_spent": 15000, "client_hires": 12, "payment_verified": True},
        # Medium-relevance jobs
        {"title": "Web Scraping Project",
         "description": "Need to scrape data from multiple websites and organize in spreadsheet.",
         "budget_type": "fixed", "budget_min": 200, "budget_max": 400,
         "client_spent": 5000, "client_hires": 5, "payment_verified": True},
        {"title": "CRM Integration Help",
         "description": "Connect our CRM to email marketing platform. Some technical knowledge needed.",
         "budget_type": "hourly", "budget_min": 30, "budget_max": 50,
         "client_spent": 8000, "client_hires": 6, "payment_verified": True},
        # Low-relevance jobs
        {"title": "Virtual Assistant Needed",
         "description": "General admin tasks, email management, scheduling. No technical skills needed.",
         "budget_type": "hourly", "budget_min": 10, "budget_max": 20,
         "client_spent": 2000, "client_hires": 3, "payment_verified": True},
        {"title": "Manual Data Entry Work",
         "description": "Copy data from PDFs to Excel. Simple task, attention to detail required.",
         "budget_type": "fixed", "budget_min": 50, "budget_max": 100,
         "client_spent": 0, "client_hires": 0, "payment_verified": False},
        {"title": "Customer Support Representative",
         "description": "Answer customer emails and chat. Basic computer skills required.",
         "budget_type": "hourly", "budget_min": 8, "budget_max": 15,
         "client_spent": 1000, "client_hires": 2, "payment_verified": False},
        {"title": "Social Media Manager",
         "description": "Post content to Facebook and Instagram. No automation experience needed.",
         "budget_type": "fixed", "budget_min": 100, "budget_max": 200,
         "client_spent": 500, "client_hires": 1, "payment_verified": False},
    ]

    # Generate 20 jobs
    jobs = []
    for i in range(20):
        template = job_templates[i % len(job_templates)]
        job = {
            "job_id": f"~batch_test_{i:03d}",
            **template,
            "source": "apify" if i % 2 == 0 else "gmail"
        }
        jobs.append(job)

    print(f"Generated {len(jobs)} sample jobs")

    # Create async client
    async_client = anthropic.AsyncAnthropic(api_key=api_key)

    # Time the batch processing
    start_time = time.time()
    print("Starting batch processing with parallel execution (5 concurrent)...")

    # Run batch processing with parallel execution
    scored_jobs = asyncio.run(
        score_jobs_batch_async(jobs, async_client, max_concurrent=5)
    )

    elapsed_time = time.time() - start_time

    print(f"Batch processing completed in {elapsed_time:.1f}s")

    # Verify all 20 jobs are scored
    assert len(scored_jobs) == 20, f"Expected 20 scored jobs, got {len(scored_jobs)}"

    # Verify each job has fit_score and fit_reasoning
    for i, job in enumerate(scored_jobs):
        assert 'fit_score' in job, f"Job {i} ({job.get('job_id')}) missing fit_score"
        assert 'fit_reasoning' in job, f"Job {i} ({job.get('job_id')}) missing fit_reasoning"
        assert isinstance(job['fit_score'], int), f"Job {i} fit_score should be int"
        assert 0 <= job['fit_score'] <= 100, f"Job {i} fit_score {job['fit_score']} out of range"

    # Verify processing time is reasonable (< 120 seconds)
    max_reasonable_time = 120
    assert elapsed_time < max_reasonable_time, f"Batch processing took {elapsed_time:.1f}s, expected < {max_reasonable_time}s"

    # Verify diversity in scores
    scores = [j['fit_score'] for j in scored_jobs]
    unique_scores = set(scores)
    assert len(unique_scores) > 1, "Expected diverse scores, got all same values"

    # Print results
    print(f"\nResults:")
    print(f"  Jobs processed: {len(scored_jobs)}")
    print(f"  Processing time: {elapsed_time:.1f}s")
    print(f"  Score range: {min(scores)} - {max(scores)}")

    # Score distribution
    buckets = {"80-100 (high)": 0, "60-79 (medium)": 0, "40-59 (low)": 0, "0-39 (poor)": 0}
    for score in scores:
        if score >= 80:
            buckets["80-100 (high)"] += 1
        elif score >= 60:
            buckets["60-79 (medium)"] += 1
        elif score >= 40:
            buckets["40-59 (low)"] += 1
        else:
            buckets["0-39 (poor)"] += 1

    print(f"  Score distribution:")
    for bucket, count in buckets.items():
        print(f"    {bucket}: {count} jobs")

    print("Feature #14: PASSED")
    return True


if __name__ == "__main__":
    results = {}

    # Test Feature #13 (no API needed)
    try:
        results[13] = test_feature_13()
    except Exception as e:
        print(f"Feature #13 FAILED: {e}")
        results[13] = False

    # Test Features #11 and #12 (need API)
    try:
        results[11] = test_feature_11()
    except Exception as e:
        print(f"Feature #11 FAILED: {e}")
        results[11] = False

    try:
        results[12] = test_feature_12()
    except Exception as e:
        print(f"Feature #12 FAILED: {e}")
        results[12] = False

    # Test Feature #14 (batch processing)
    try:
        results[14] = test_feature_14()
    except Exception as e:
        print(f"Feature #14 FAILED: {e}")
        results[14] = False

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for feature, result in results.items():
        status = "PASSED" if result else ("SKIPPED" if result is None else "FAILED")
        print(f"Feature #{feature}: {status}")

    # Exit with appropriate code
    if all(r is None or r for r in results.values()):
        print("\nAll tests passed!")
        sys.exit(0)
    else:
        print("\nSome tests failed!")
        sys.exit(1)
