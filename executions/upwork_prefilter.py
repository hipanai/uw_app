#!/usr/bin/env python3
"""
Upwork Job Pre-Filter

AI-based scoring (0-100) using Claude Sonnet to filter jobs for relevance.
This saves tokens and time by screening out low-fit jobs before expensive processing.

Usage:
    # Score a single job
    python executions/upwork_prefilter.py --job job.json

    # Score batch of jobs
    python executions/upwork_prefilter.py --jobs jobs.json --output scored_jobs.json

    # Filter to high-fit jobs only
    python executions/upwork_prefilter.py --jobs jobs.json --output filtered_jobs.json --min-score 70

    # Test mode (don't call API, use mock scores)
    python executions/upwork_prefilter.py --jobs jobs.json --output filtered_jobs.json --test
"""

import os
import sys
import json
import argparse
import asyncio
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
PREFILTER_MIN_SCORE = int(os.getenv("PREFILTER_MIN_SCORE", "70"))

# Model for pre-filtering (Sonnet for cost efficiency)
PREFILTER_MODEL = "claude-sonnet-4-20250514"

# Profile information for relevance scoring
PROFILE = """
Name: Clyde
Experience: ~4 years AI/automation, many more years overall
Specialties:
- AI workflow automation (Make.com, Zapier, n8n)
- AI agents and chatbots (ChatGPT/OpenAI, Claude, custom)
- Lead generation automation (Apollo.io, Instantly, scraping)
- Data automation and pipelines
- AI video generation
- Email automation and outreach
- Social media automation
- Invoice/proposal automation
- Data analysis and visualization

Tools: Zapier, Make.com, Airtable, n8n, Python, OpenAI/Anthropic APIs,
       Instantly, Apollo.io, HeyGen, Playwright, various APIs

NOT a good fit for:
- Manual data entry
- Basic virtual assistant tasks
- Graphic design (unless AI-powered)
- Non-technical writing
- Customer support roles
- Jobs requiring specific certifications or licenses
- Jobs under $100 budget
"""

SCORING_PROMPT = """Score this Upwork job posting for relevance to the freelancer profile below.

FREELANCER PROFILE:
{profile}

JOB POSTING:
Title: {title}
Description: {description}
Budget: {budget}
Client Info: Spent ${client_spent}, {client_hires} hires, Payment verified: {payment_verified}

SCORING CRITERIA:
- Core skill match (0-40 points): Does the job require skills the freelancer has?
- Project type fit (0-30 points): Is this the type of work the freelancer excels at?
- Budget appropriateness (0-15 points): Is the budget reasonable for the work?
- Client quality (0-15 points): Does the client have good hiring history?

RESPONSE FORMAT (JSON only, no markdown):
{{"score": <0-100>, "reasoning": "<2-3 sentences explaining the score>"}}

Important:
- Score 80+ = Strong fit, proceed with proposal
- Score 60-79 = Moderate fit, may be worth pursuing
- Score 40-59 = Weak fit, likely not worth time
- Score <40 = Poor fit, skip this job
- Be strict: only high scores for genuinely good matches
"""


def create_scoring_prompt(job: Dict) -> str:
    """Create the prompt for scoring a job."""
    title = job.get('title', 'No title')
    description = job.get('description', 'No description')[:2000]  # Limit for token efficiency

    # Format budget
    budget_type = job.get('budget_type', 'unknown')
    budget_min = job.get('budget_min')
    budget_max = job.get('budget_max')

    if budget_type == 'fixed':
        budget = f"Fixed price: ${budget_min or budget_max or 'Not specified'}"
    elif budget_type == 'hourly':
        if budget_min and budget_max:
            budget = f"Hourly: ${budget_min}-${budget_max}/hr"
        else:
            budget = "Hourly: Rate not specified"
    else:
        budget = "Budget not specified"

    # Client info
    client_spent = job.get('client_spent', 'Unknown')
    client_hires = job.get('client_hires', 'Unknown')
    payment_verified = job.get('payment_verified', 'Unknown')

    return SCORING_PROMPT.format(
        profile=PROFILE,
        title=title,
        description=description,
        budget=budget,
        client_spent=client_spent,
        client_hires=client_hires,
        payment_verified=payment_verified
    )


def parse_score_response(response_text: str) -> Tuple[int, str]:
    """Parse the AI response to extract score and reasoning."""
    try:
        # Try to parse as JSON
        # Handle potential markdown code blocks
        text = response_text.strip()
        if text.startswith('```'):
            # Remove markdown code blocks
            lines = text.split('\n')
            text = '\n'.join(lines[1:-1] if lines[-1] == '```' else lines[1:])

        data = json.loads(text)
        score = int(data.get('score', 0))
        reasoning = data.get('reasoning', 'No reasoning provided')

        # Clamp score to 0-100
        score = max(0, min(100, score))

        return score, reasoning
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        # Try to extract score from text if JSON parsing fails
        import re
        score_match = re.search(r'"?score"?\s*[:=]\s*(\d+)', response_text, re.IGNORECASE)
        if score_match:
            score = int(score_match.group(1))
            score = max(0, min(100, score))
            return score, f"Extracted from response: {response_text[:200]}"

        print(f"Warning: Could not parse response: {e}")
        return 0, f"Parse error: {str(e)}"


def score_job_sync(job: Dict, client) -> Dict:
    """Score a single job synchronously."""
    prompt = create_scoring_prompt(job)

    try:
        response = client.messages.create(
            model=PREFILTER_MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response.content[0].text
        score, reasoning = parse_score_response(response_text)

        return {
            **job,
            'fit_score': score,
            'fit_reasoning': reasoning
        }
    except Exception as e:
        print(f"Error scoring job {job.get('job_id', 'unknown')}: {e}")
        return {
            **job,
            'fit_score': 0,
            'fit_reasoning': f"Scoring error: {str(e)}"
        }


async def score_job_async(job: Dict, client) -> Dict:
    """Score a single job asynchronously."""
    prompt = create_scoring_prompt(job)

    try:
        response = await client.messages.create(
            model=PREFILTER_MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response.content[0].text
        score, reasoning = parse_score_response(response_text)

        return {
            **job,
            'fit_score': score,
            'fit_reasoning': reasoning
        }
    except Exception as e:
        print(f"Error scoring job {job.get('job_id', 'unknown')}: {e}")
        return {
            **job,
            'fit_score': 0,
            'fit_reasoning': f"Scoring error: {str(e)}"
        }


async def score_jobs_batch_async(
    jobs: List[Dict],
    client,
    max_concurrent: int = 5
) -> List[Dict]:
    """Score multiple jobs in parallel with concurrency limit."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def score_with_semaphore(job: Dict) -> Dict:
        async with semaphore:
            return await score_job_async(job, client)

    tasks = [score_with_semaphore(job) for job in jobs]
    results = await asyncio.gather(*tasks)
    return list(results)


def score_jobs_batch_sync(jobs: List[Dict], client) -> List[Dict]:
    """Score multiple jobs sequentially (fallback for sync mode)."""
    results = []
    for i, job in enumerate(jobs, 1):
        print(f"  Scoring job {i}/{len(jobs)}: {job.get('title', 'Unknown')[:50]}...")
        scored = score_job_sync(job, client)
        results.append(scored)
        print(f"    Score: {scored['fit_score']}")
    return results


def filter_jobs_by_score(
    jobs: List[Dict],
    min_score: int = PREFILTER_MIN_SCORE
) -> Tuple[List[Dict], List[Dict]]:
    """
    Filter jobs by minimum score.

    Returns:
        Tuple of (passing_jobs, filtered_out_jobs)
    """
    passing = []
    filtered_out = []

    for job in jobs:
        if job.get('fit_score', 0) >= min_score:
            passing.append(job)
        else:
            filtered_out.append(job)

    return passing, filtered_out


def mock_score_job(job: Dict) -> Dict:
    """Generate a mock score for testing without API calls."""
    import random

    title = job.get('title', '').lower()
    description = job.get('description', '').lower()

    # Simple keyword-based mock scoring
    ai_keywords = ['ai', 'automation', 'chatbot', 'workflow', 'make.com', 'zapier',
                   'n8n', 'openai', 'gpt', 'claude', 'api', 'scraping', 'data']

    bad_keywords = ['data entry', 'virtual assistant', 'customer support',
                    'graphic design', 'manual', 'receptionist']

    text = f"{title} {description}"

    # Count matches
    ai_matches = sum(1 for kw in ai_keywords if kw in text)
    bad_matches = sum(1 for kw in bad_keywords if kw in text)

    # Calculate base score
    base_score = 50 + (ai_matches * 8) - (bad_matches * 15)

    # Add some randomness
    score = base_score + random.randint(-10, 10)
    score = max(0, min(100, score))

    reasoning = f"Mock score based on keyword matching: {ai_matches} positive keywords, {bad_matches} negative keywords"

    return {
        **job,
        'fit_score': score,
        'fit_reasoning': reasoning
    }


def main():
    parser = argparse.ArgumentParser(
        description="Pre-filter Upwork jobs using AI scoring"
    )

    parser.add_argument(
        "--job",
        help="Path to JSON file with a single job to score"
    )
    parser.add_argument(
        "--jobs",
        help="Path to JSON file with multiple jobs to score"
    )
    parser.add_argument(
        "--output", "-o",
        help="Path to save scored/filtered jobs"
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=PREFILTER_MIN_SCORE,
        help=f"Minimum score to pass filter (default: {PREFILTER_MIN_SCORE})"
    )
    parser.add_argument(
        "--no-filter",
        action="store_true",
        help="Return all scored jobs without filtering"
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=5,
        help="Number of parallel API calls (default: 5)"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Use mock scores instead of API calls (for testing)"
    )
    parser.add_argument(
        "--show-filtered",
        action="store_true",
        help="Also output jobs that were filtered out"
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.job and not args.jobs:
        parser.print_help()
        print("\nError: Must provide either --job or --jobs")
        return 1

    # Check API key (unless in test mode)
    if not args.test and not ANTHROPIC_API_KEY:
        print("Error: ANTHROPIC_API_KEY not set in .env")
        print("Use --test flag to run with mock scores")
        return 1

    # Load job(s)
    if args.job:
        with open(args.job, 'r') as f:
            job = json.load(f)
        jobs = [job]
        print(f"Loaded 1 job from {args.job}")
    else:
        with open(args.jobs, 'r') as f:
            jobs = json.load(f)
        print(f"Loaded {len(jobs)} jobs from {args.jobs}")

    # Score jobs
    if args.test:
        print("Using mock scores (test mode)...")
        scored_jobs = [mock_score_job(job) for job in jobs]
    else:
        import anthropic

        print(f"Scoring {len(jobs)} jobs with {PREFILTER_MODEL}...")

        if len(jobs) > 1:
            # Use async for batch processing
            async_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
            scored_jobs = asyncio.run(
                score_jobs_batch_async(jobs, async_client, max_concurrent=args.parallel)
            )
        else:
            # Use sync for single job
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            scored_jobs = [score_job_sync(jobs[0], client)]

    # Filter if requested
    if args.no_filter:
        passing_jobs = scored_jobs
        filtered_jobs = []
    else:
        passing_jobs, filtered_jobs = filter_jobs_by_score(scored_jobs, args.min_score)

    # Print summary
    print("\n" + "="*60)
    print("SCORING SUMMARY")
    print("="*60)
    print(f"Total jobs scored: {len(scored_jobs)}")

    if scored_jobs:
        scores = [j.get('fit_score', 0) for j in scored_jobs]
        avg_score = sum(scores) / len(scores)
        print(f"Average score: {avg_score:.1f}")
        print(f"Score range: {min(scores)} - {max(scores)}")

    if not args.no_filter:
        print(f"\nFilter threshold: {args.min_score}")
        print(f"Jobs passing filter: {len(passing_jobs)}")
        print(f"Jobs filtered out: {len(filtered_jobs)}")

    # Show top scoring jobs
    if passing_jobs:
        print("\nTop scoring jobs:")
        sorted_jobs = sorted(passing_jobs, key=lambda x: x.get('fit_score', 0), reverse=True)
        for i, job in enumerate(sorted_jobs[:5], 1):
            title = job.get('title', 'Unknown')[:50]
            score = job.get('fit_score', 0)
            print(f"  {i}. [{score}] {title}")

    # Show filtered out jobs if requested
    if args.show_filtered and filtered_jobs:
        print("\nFiltered out jobs:")
        for job in filtered_jobs[:5]:
            title = job.get('title', 'Unknown')[:50]
            score = job.get('fit_score', 0)
            reason = job.get('fit_reasoning', '')[:60]
            print(f"  [{score}] {title}")
            print(f"      Reason: {reason}...")

    # Save output
    if args.output:
        os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else '.', exist_ok=True)

        with open(args.output, 'w') as f:
            json.dump(passing_jobs, f, indent=2)

        print(f"\nSaved {len(passing_jobs)} jobs to {args.output}")

        # Also save filtered out jobs if requested
        if args.show_filtered and filtered_jobs:
            filtered_path = args.output.replace('.json', '_filtered_out.json')
            with open(filtered_path, 'w') as f:
                json.dump(filtered_jobs, f, indent=2)
            print(f"Saved {len(filtered_jobs)} filtered jobs to {filtered_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
