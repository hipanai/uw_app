#!/usr/bin/env python3
"""
Upwork Boost Decider

AI-based decision on whether to boost an Upwork proposal based on job quality signals.
Analyzes client metrics (spending history, hire rate, payment verification) to determine
if boosting is worth the extra cost.

Usage:
    # Analyze a single job
    python executions/upwork_boost_decider.py --job job.json

    # Analyze batch of jobs
    python executions/upwork_boost_decider.py --jobs jobs.json --output decisions.json

    # Test mode (don't call API, use rule-based decisions)
    python executions/upwork_boost_decider.py --jobs jobs.json --test
"""

import os
import sys
import json
import argparse
import asyncio
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Model for boost decisions (Sonnet for cost efficiency)
BOOST_DECISION_MODEL = "claude-sonnet-4-20250514"

# Thresholds for boost recommendations
HIGH_VALUE_SPEND_THRESHOLD = 10000  # Client spent > $10k
MEDIUM_VALUE_SPEND_THRESHOLD = 1000  # Client spent > $1k
MIN_HIRES_FOR_BOOST = 3  # At least 3 previous hires
NEW_CLIENT_SPEND_THRESHOLD = 100  # Less than $100 = new client


@dataclass
class BoostDecision:
    """Result of boost analysis for a job."""
    job_id: str
    boost_decision: bool
    boost_reasoning: str
    confidence: str  # 'high', 'medium', 'low'
    client_quality_score: int  # 0-100

    def to_dict(self) -> Dict:
        return asdict(self)


BOOST_DECISION_PROMPT = """Analyze this Upwork job and decide if boosting the proposal is worth the extra cost.

JOB QUALITY SIGNALS:
- Job Title: {title}
- Budget: {budget_type} - ${budget_min} to ${budget_max}
- Client Total Spent: ${client_spent}
- Client Total Hires: {client_hires}
- Payment Method Verified: {payment_verified}
- Client Country: {client_country}
- Fit Score: {fit_score}

BOOST DECISION CRITERIA:
1. HIGH-VALUE CLIENT (Recommend Boost):
   - client_spent > $10,000 AND payment_verified = true
   - Shows serious buyer with history of paying for work

2. ESTABLISHED CLIENT (Consider Boost):
   - client_spent > $1,000 AND client_hires >= 3
   - Reasonable history, may be worth competing for

3. NEW CLIENT (Don't Boost):
   - client_spent < $100 OR client_hires = 0
   - Unproven client, not worth extra investment

4. RISKY CLIENT (Don't Boost):
   - payment_verified = false
   - Low budget relative to job scope
   - Poor spending/hire ratio

RESPONSE FORMAT (JSON only, no markdown):
{{"boost_decision": true/false, "reasoning": "<2-3 sentences explaining decision>", "confidence": "high/medium/low", "client_quality_score": <0-100>}}

Consider:
- Boost costs extra connects, only worth it for high-probability jobs
- High client_spent indicates willingness to pay
- Multiple hires shows client knows how to work with freelancers
- Unverified payment is a red flag
"""


def create_boost_prompt(job: Dict) -> str:
    """Create the prompt for boost decision."""
    title = job.get('title', 'No title')

    # Budget info
    budget_type = job.get('budget_type', 'unknown')
    budget_min = job.get('budget_min', 0)
    budget_max = job.get('budget_max', 0)

    # Client info
    client_spent = job.get('client_spent', 0)
    client_hires = job.get('client_hires', 0)
    payment_verified = job.get('payment_verified', False)
    client_country = job.get('client_country', 'Unknown')

    # Fit score from pre-filter
    fit_score = job.get('fit_score', 'Not scored')

    return BOOST_DECISION_PROMPT.format(
        title=title,
        budget_type=budget_type,
        budget_min=budget_min or 'Not specified',
        budget_max=budget_max or 'Not specified',
        client_spent=client_spent if client_spent else 0,
        client_hires=client_hires if client_hires else 0,
        payment_verified=payment_verified,
        client_country=client_country,
        fit_score=fit_score
    )


def parse_boost_response(response_text: str) -> Tuple[bool, str, str, int]:
    """
    Parse the AI response to extract boost decision, reasoning, confidence, and quality score.

    Returns:
        Tuple of (boost_decision, reasoning, confidence, client_quality_score)
    """
    try:
        # Try to parse as JSON
        text = response_text.strip()
        if text.startswith('```'):
            # Remove markdown code blocks
            lines = text.split('\n')
            text = '\n'.join(lines[1:-1] if lines[-1] == '```' else lines[1:])

        data = json.loads(text)
        boost_decision = bool(data.get('boost_decision', False))
        reasoning = data.get('reasoning', 'No reasoning provided')
        confidence = data.get('confidence', 'medium')
        client_quality_score = int(data.get('client_quality_score', 50))

        # Validate confidence
        if confidence not in ['high', 'medium', 'low']:
            confidence = 'medium'

        # Clamp score to 0-100
        client_quality_score = max(0, min(100, client_quality_score))

        return boost_decision, reasoning, confidence, client_quality_score
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        # Try to extract decision from text if JSON parsing fails
        import re
        decision_match = re.search(r'"?boost_decision"?\s*[:=]\s*(true|false)', response_text, re.IGNORECASE)
        if decision_match:
            boost = decision_match.group(1).lower() == 'true'
            return boost, f"Extracted from response: {response_text[:200]}", 'low', 50

        print(f"Warning: Could not parse response: {e}")
        return False, f"Parse error: {str(e)}", 'low', 0


def decide_boost_sync(job: Dict, client) -> BoostDecision:
    """Make boost decision for a single job synchronously."""
    job_id = job.get('job_id', 'unknown')
    prompt = create_boost_prompt(job)

    try:
        response = client.messages.create(
            model=BOOST_DECISION_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response.content[0].text
        boost_decision, reasoning, confidence, quality_score = parse_boost_response(response_text)

        return BoostDecision(
            job_id=job_id,
            boost_decision=boost_decision,
            boost_reasoning=reasoning,
            confidence=confidence,
            client_quality_score=quality_score
        )
    except Exception as e:
        print(f"Error deciding boost for job {job_id}: {e}")
        return BoostDecision(
            job_id=job_id,
            boost_decision=False,
            boost_reasoning=f"Decision error: {str(e)}",
            confidence='low',
            client_quality_score=0
        )


async def decide_boost_async(job: Dict, client) -> BoostDecision:
    """Make boost decision for a single job asynchronously."""
    job_id = job.get('job_id', 'unknown')
    prompt = create_boost_prompt(job)

    try:
        response = await client.messages.create(
            model=BOOST_DECISION_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response.content[0].text
        boost_decision, reasoning, confidence, quality_score = parse_boost_response(response_text)

        return BoostDecision(
            job_id=job_id,
            boost_decision=boost_decision,
            boost_reasoning=reasoning,
            confidence=confidence,
            client_quality_score=quality_score
        )
    except Exception as e:
        print(f"Error deciding boost for job {job_id}: {e}")
        return BoostDecision(
            job_id=job_id,
            boost_decision=False,
            boost_reasoning=f"Decision error: {str(e)}",
            confidence='low',
            client_quality_score=0
        )


async def decide_boost_batch_async(
    jobs: List[Dict],
    client,
    max_concurrent: int = 5
) -> List[BoostDecision]:
    """Make boost decisions for multiple jobs in parallel with concurrency limit."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def decide_with_semaphore(job: Dict) -> BoostDecision:
        async with semaphore:
            return await decide_boost_async(job, client)

    tasks = [decide_with_semaphore(job) for job in jobs]
    results = await asyncio.gather(*tasks)
    return list(results)


def decide_boost_batch_sync(jobs: List[Dict], client) -> List[BoostDecision]:
    """Make boost decisions for multiple jobs sequentially (fallback for sync mode)."""
    results = []
    for i, job in enumerate(jobs, 1):
        print(f"  Analyzing job {i}/{len(jobs)}: {job.get('title', 'Unknown')[:50]}...")
        decision = decide_boost_sync(job, client)
        results.append(decision)
        print(f"    Boost: {decision.boost_decision} ({decision.confidence} confidence)")
    return results


def rule_based_boost_decision(job: Dict) -> BoostDecision:
    """
    Make a rule-based boost decision without AI (for testing or fallback).

    This implements the core logic from Features #39-41:
    - Feature #39: Analyze job quality signals
    - Feature #40: Recommend boost for high-value clients
    - Feature #41: Don't recommend boost for new clients
    """
    job_id = job.get('job_id', 'unknown')

    # Extract signals
    client_spent = job.get('client_spent', 0)
    if isinstance(client_spent, str):
        # Parse string like "$5,000" or "5000"
        client_spent = float(client_spent.replace('$', '').replace(',', '').replace('+', '') or 0)

    client_hires = job.get('client_hires', 0)
    if isinstance(client_hires, str):
        client_hires = int(client_hires.replace('+', '') or 0)

    payment_verified = job.get('payment_verified', False)
    if isinstance(payment_verified, str):
        payment_verified = payment_verified.lower() in ['true', 'yes', 'verified']

    budget_min = job.get('budget_min', 0) or 0
    budget_max = job.get('budget_max', 0) or 0
    fit_score = job.get('fit_score', 50)

    # Calculate client quality score (0-100)
    quality_score = 50  # Start at neutral

    # Spending history impact (+/- up to 30 points)
    if client_spent >= HIGH_VALUE_SPEND_THRESHOLD:
        quality_score += 30
    elif client_spent >= MEDIUM_VALUE_SPEND_THRESHOLD:
        quality_score += 20
    elif client_spent >= 500:
        quality_score += 10
    elif client_spent < NEW_CLIENT_SPEND_THRESHOLD:
        quality_score -= 20

    # Hire history impact (+/- up to 20 points)
    if client_hires >= 10:
        quality_score += 20
    elif client_hires >= MIN_HIRES_FOR_BOOST:
        quality_score += 10
    elif client_hires == 0:
        quality_score -= 20

    # Payment verification impact (+/- 15 points)
    if payment_verified:
        quality_score += 15
    else:
        quality_score -= 15

    # Clamp to 0-100
    quality_score = max(0, min(100, quality_score))

    # Make decision based on rules
    boost_decision = False
    confidence = 'medium'
    reasoning_parts = []

    # Feature #41: New client - don't boost
    if client_spent < NEW_CLIENT_SPEND_THRESHOLD and client_hires == 0:
        boost_decision = False
        confidence = 'high'
        reasoning_parts.append("New client with no spending history or hires")
        reasoning_parts.append("Not worth extra connect investment for unproven client")

    # Feature #40: High-value client - recommend boost
    elif client_spent >= HIGH_VALUE_SPEND_THRESHOLD and payment_verified:
        boost_decision = True
        confidence = 'high'
        reasoning_parts.append(f"High-value client with ${client_spent:,.0f} spent and verified payment")
        reasoning_parts.append("Strong track record indicates serious buyer worth competing for")

    # Established client - consider boost
    elif client_spent >= MEDIUM_VALUE_SPEND_THRESHOLD and client_hires >= MIN_HIRES_FOR_BOOST:
        boost_decision = True
        confidence = 'medium'
        reasoning_parts.append(f"Established client with ${client_spent:,.0f} spent and {client_hires} hires")
        reasoning_parts.append("Reasonable history suggests good probability of hire")

    # Unverified payment - don't boost
    elif not payment_verified:
        boost_decision = False
        confidence = 'high'
        reasoning_parts.append("Payment method not verified")
        reasoning_parts.append("Risk too high for extra connect investment")

    # Moderate client - don't boost by default
    else:
        boost_decision = False
        confidence = 'low'
        reasoning_parts.append(f"Moderate client profile: ${client_spent:,.0f} spent, {client_hires} hires")
        reasoning_parts.append("Not enough positive signals to justify boost cost")

    reasoning = ". ".join(reasoning_parts) + "."

    return BoostDecision(
        job_id=job_id,
        boost_decision=boost_decision,
        boost_reasoning=reasoning,
        confidence=confidence,
        client_quality_score=quality_score
    )


def merge_decision_with_job(job: Dict, decision: BoostDecision) -> Dict:
    """Merge boost decision fields into job data."""
    return {
        **job,
        'boost_decision': decision.boost_decision,
        'boost_reasoning': decision.boost_reasoning,
        'boost_confidence': decision.confidence,
        'client_quality_score': decision.client_quality_score
    }


def main():
    parser = argparse.ArgumentParser(
        description="Decide whether to boost Upwork proposals based on job quality signals"
    )

    parser.add_argument(
        "--job",
        help="Path to JSON file with a single job to analyze"
    )
    parser.add_argument(
        "--jobs",
        help="Path to JSON file with multiple jobs to analyze"
    )
    parser.add_argument(
        "--output", "-o",
        help="Path to save jobs with boost decisions"
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
        help="Use rule-based decisions instead of AI (for testing)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed decision reasoning"
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
        print("Use --test flag to run with rule-based decisions")
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

    # Make decisions
    if args.test:
        print("Using rule-based decisions (test mode)...")
        decisions = [rule_based_boost_decision(job) for job in jobs]
    else:
        import anthropic

        print(f"Analyzing {len(jobs)} jobs with {BOOST_DECISION_MODEL}...")

        if len(jobs) > 1:
            # Use async for batch processing
            async_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
            decisions = asyncio.run(
                decide_boost_batch_async(jobs, async_client, max_concurrent=args.parallel)
            )
        else:
            # Use sync for single job
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            decisions = [decide_boost_sync(jobs[0], client)]

    # Merge decisions with jobs
    jobs_with_decisions = [
        merge_decision_with_job(job, decision)
        for job, decision in zip(jobs, decisions)
    ]

    # Print summary
    print("\n" + "="*60)
    print("BOOST DECISION SUMMARY")
    print("="*60)

    boost_count = sum(1 for d in decisions if d.boost_decision)
    no_boost_count = len(decisions) - boost_count

    print(f"Total jobs analyzed: {len(decisions)}")
    print(f"Recommend boost: {boost_count}")
    print(f"Don't boost: {no_boost_count}")

    if decisions:
        quality_scores = [d.client_quality_score for d in decisions]
        avg_quality = sum(quality_scores) / len(quality_scores)
        print(f"Average client quality score: {avg_quality:.1f}")

    # Show detailed decisions
    if args.verbose:
        print("\nDetailed decisions:")
        for job, decision in zip(jobs, decisions):
            title = job.get('title', 'Unknown')[:50]
            client_spent = job.get('client_spent', 0)
            print(f"\n  Job: {title}")
            print(f"    Client spent: ${client_spent}")
            print(f"    Boost: {'YES' if decision.boost_decision else 'NO'} ({decision.confidence} confidence)")
            print(f"    Quality score: {decision.client_quality_score}")
            print(f"    Reasoning: {decision.boost_reasoning[:100]}...")
    else:
        # Show summary of boost recommendations
        print("\nBoost recommendations:")
        for job, decision in zip(jobs, decisions):
            if decision.boost_decision:
                title = job.get('title', 'Unknown')[:50]
                print(f"  [BOOST] {title} (quality: {decision.client_quality_score})")

    # Save output
    if args.output:
        os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else '.', exist_ok=True)

        with open(args.output, 'w') as f:
            json.dump(jobs_with_decisions, f, indent=2)

        print(f"\nSaved {len(jobs_with_decisions)} jobs with decisions to {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
