#!/usr/bin/env python3
"""
Upwork Cost Tracker

Tracks API costs per job for the Upwork automation pipeline.
Provides accurate cost calculation based on:
- Anthropic API token usage (pre-filter, proposal generation)
- HeyGen video generation costs

Feature #99: Cost tracking per job is calculated correctly

Usage:
    from upwork_cost_tracker import CostTracker, JobCosts

    # Create tracker
    tracker = CostTracker()

    # Track pre-filter cost
    tracker.track_prefilter(job_id, input_tokens, output_tokens)

    # Track proposal generation cost
    tracker.track_proposal(job_id, input_tokens, output_tokens, thinking_tokens)

    # Track HeyGen video cost
    tracker.track_heygen(job_id, duration_seconds)

    # Get total cost for job
    costs = tracker.get_job_costs(job_id)
    print(f"Total: ${costs.total:.4f}")
"""

import os
import json
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()


# Anthropic API Pricing (as of Jan 2025)
# Claude Sonnet (claude-sonnet-4-*) - used for pre-filter
SONNET_INPUT_COST_PER_1K = 0.003  # $3 per 1M input tokens
SONNET_OUTPUT_COST_PER_1K = 0.015  # $15 per 1M output tokens

# Claude Opus 4.5 (claude-opus-4-5-*) - used for proposal generation
OPUS_INPUT_COST_PER_1K = 0.015  # $15 per 1M input tokens
OPUS_OUTPUT_COST_PER_1K = 0.075  # $75 per 1M output tokens
OPUS_THINKING_COST_PER_1K = 0.075  # Same as output for thinking tokens

# HeyGen Pricing
# Based on typical enterprise pricing: ~$0.10-0.15 per minute of video
HEYGEN_COST_PER_MINUTE = 0.15
HEYGEN_MINIMUM_COST = 0.05  # Minimum cost per video

# Default token estimates (used when actual tokens not available)
DEFAULT_PREFILTER_INPUT_TOKENS = 800  # Prompt + job description
DEFAULT_PREFILTER_OUTPUT_TOKENS = 100  # Score + reasoning
DEFAULT_PROPOSAL_INPUT_TOKENS = 1500  # Prompt + job details
DEFAULT_PROPOSAL_OUTPUT_TOKENS = 500  # Proposal text
DEFAULT_PROPOSAL_THINKING_TOKENS = 5000  # Extended thinking budget

# Default video duration in seconds
DEFAULT_VIDEO_DURATION = 60  # 1 minute average


@dataclass
class CostEntry:
    """Single cost entry for a pipeline stage."""
    stage: str  # 'prefilter', 'proposal', 'heygen', 'deep_extract', etc.
    cost: float
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    thinking_tokens: Optional[int] = None
    duration_seconds: Optional[float] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class JobCosts:
    """Aggregated costs for a single job."""
    job_id: str
    prefilter_cost: float = 0.0
    deep_extract_cost: float = 0.0
    proposal_cost: float = 0.0
    heygen_cost: float = 0.0
    other_costs: float = 0.0
    entries: List[CostEntry] = field(default_factory=list)

    @property
    def total(self) -> float:
        """Calculate total cost."""
        return (
            self.prefilter_cost +
            self.deep_extract_cost +
            self.proposal_cost +
            self.heygen_cost +
            self.other_costs
        )

    @property
    def processing_cost(self) -> float:
        """Cost for full processing (excludes prefilter)."""
        return (
            self.deep_extract_cost +
            self.proposal_cost +
            self.heygen_cost +
            self.other_costs
        )

    def to_dict(self) -> dict:
        result = {
            'job_id': self.job_id,
            'prefilter_cost': self.prefilter_cost,
            'deep_extract_cost': self.deep_extract_cost,
            'proposal_cost': self.proposal_cost,
            'heygen_cost': self.heygen_cost,
            'other_costs': self.other_costs,
            'total': self.total,
            'processing_cost': self.processing_cost,
            'entries': [e.to_dict() for e in self.entries],
        }
        return result

    def summary(self) -> str:
        """Return a formatted summary of costs."""
        lines = [
            f"Job {self.job_id} Cost Breakdown:",
            f"  Pre-filter:     ${self.prefilter_cost:.4f}",
            f"  Deep extract:   ${self.deep_extract_cost:.4f}",
            f"  Proposal:       ${self.proposal_cost:.4f}",
            f"  HeyGen video:   ${self.heygen_cost:.4f}",
            f"  Other:          ${self.other_costs:.4f}",
            f"  ─────────────────────────",
            f"  Total:          ${self.total:.4f}",
        ]
        return '\n'.join(lines)


class CostTracker:
    """
    Tracks API costs for the Upwork automation pipeline.

    This tracker can work in two modes:
    1. Actual token tracking: When API responses provide usage info
    2. Estimated tracking: Using default values when actual tokens unavailable
    """

    def __init__(self):
        """Initialize the cost tracker."""
        self._jobs: Dict[str, JobCosts] = {}

    def _get_or_create_job(self, job_id: str) -> JobCosts:
        """Get or create JobCosts for a job_id."""
        if job_id not in self._jobs:
            self._jobs[job_id] = JobCosts(job_id=job_id)
        return self._jobs[job_id]

    def calculate_sonnet_cost(
        self,
        input_tokens: int,
        output_tokens: int
    ) -> float:
        """Calculate cost for Claude Sonnet API call."""
        input_cost = (input_tokens / 1000) * SONNET_INPUT_COST_PER_1K
        output_cost = (output_tokens / 1000) * SONNET_OUTPUT_COST_PER_1K
        return input_cost + output_cost

    def calculate_opus_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        thinking_tokens: int = 0
    ) -> float:
        """Calculate cost for Claude Opus 4.5 API call."""
        input_cost = (input_tokens / 1000) * OPUS_INPUT_COST_PER_1K
        output_cost = (output_tokens / 1000) * OPUS_OUTPUT_COST_PER_1K
        thinking_cost = (thinking_tokens / 1000) * OPUS_THINKING_COST_PER_1K
        return input_cost + output_cost + thinking_cost

    def calculate_heygen_cost(self, duration_seconds: float) -> float:
        """Calculate cost for HeyGen video generation."""
        duration_minutes = duration_seconds / 60
        cost = duration_minutes * HEYGEN_COST_PER_MINUTE
        return max(cost, HEYGEN_MINIMUM_COST)

    def track_prefilter(
        self,
        job_id: str,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None
    ) -> float:
        """
        Track pre-filter API cost.

        Args:
            job_id: Unique job identifier
            input_tokens: Actual input tokens (or None to use default)
            output_tokens: Actual output tokens (or None to use default)

        Returns:
            The calculated cost
        """
        input_tokens = input_tokens or DEFAULT_PREFILTER_INPUT_TOKENS
        output_tokens = output_tokens or DEFAULT_PREFILTER_OUTPUT_TOKENS

        cost = self.calculate_sonnet_cost(input_tokens, output_tokens)

        job = self._get_or_create_job(job_id)
        job.prefilter_cost += cost
        job.entries.append(CostEntry(
            stage='prefilter',
            cost=cost,
            input_tokens=input_tokens,
            output_tokens=output_tokens
        ))

        return cost

    def track_deep_extract(
        self,
        job_id: str,
        cost: float = 0.01
    ) -> float:
        """
        Track deep extraction cost (Playwright + parsing).

        Args:
            job_id: Unique job identifier
            cost: Estimated cost (default $0.01 for compute/bandwidth)

        Returns:
            The cost
        """
        job = self._get_or_create_job(job_id)
        job.deep_extract_cost += cost
        job.entries.append(CostEntry(
            stage='deep_extract',
            cost=cost
        ))

        return cost

    def track_proposal(
        self,
        job_id: str,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        thinking_tokens: Optional[int] = None
    ) -> float:
        """
        Track proposal generation API cost (Opus 4.5 with extended thinking).

        Args:
            job_id: Unique job identifier
            input_tokens: Actual input tokens (or None to use default)
            output_tokens: Actual output tokens (or None to use default)
            thinking_tokens: Actual thinking tokens (or None to use default)

        Returns:
            The calculated cost
        """
        input_tokens = input_tokens or DEFAULT_PROPOSAL_INPUT_TOKENS
        output_tokens = output_tokens or DEFAULT_PROPOSAL_OUTPUT_TOKENS
        thinking_tokens = thinking_tokens or DEFAULT_PROPOSAL_THINKING_TOKENS

        cost = self.calculate_opus_cost(input_tokens, output_tokens, thinking_tokens)

        job = self._get_or_create_job(job_id)
        job.proposal_cost += cost
        job.entries.append(CostEntry(
            stage='proposal',
            cost=cost,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thinking_tokens=thinking_tokens
        ))

        return cost

    def track_heygen(
        self,
        job_id: str,
        duration_seconds: Optional[float] = None
    ) -> float:
        """
        Track HeyGen video generation cost.

        Args:
            job_id: Unique job identifier
            duration_seconds: Video duration in seconds (or None to use default)

        Returns:
            The calculated cost
        """
        duration_seconds = duration_seconds or DEFAULT_VIDEO_DURATION
        cost = self.calculate_heygen_cost(duration_seconds)

        job = self._get_or_create_job(job_id)
        job.heygen_cost += cost
        job.entries.append(CostEntry(
            stage='heygen',
            cost=cost,
            duration_seconds=duration_seconds
        ))

        return cost

    def track_other(
        self,
        job_id: str,
        stage: str,
        cost: float
    ) -> float:
        """
        Track other/miscellaneous costs.

        Args:
            job_id: Unique job identifier
            stage: Name of the stage (e.g., 'pdf_generation')
            cost: The cost amount

        Returns:
            The cost
        """
        job = self._get_or_create_job(job_id)
        job.other_costs += cost
        job.entries.append(CostEntry(
            stage=stage,
            cost=cost
        ))

        return cost

    def get_job_costs(self, job_id: str) -> Optional[JobCosts]:
        """Get costs for a specific job."""
        return self._jobs.get(job_id)

    def get_all_costs(self) -> Dict[str, JobCosts]:
        """Get costs for all tracked jobs."""
        return self._jobs.copy()

    def get_total_cost(self) -> float:
        """Get total cost across all jobs."""
        return sum(job.total for job in self._jobs.values())

    def get_summary(self) -> Dict[str, float]:
        """Get summary of all costs by stage."""
        summary = {
            'total_jobs': len(self._jobs),
            'prefilter_total': sum(j.prefilter_cost for j in self._jobs.values()),
            'deep_extract_total': sum(j.deep_extract_cost for j in self._jobs.values()),
            'proposal_total': sum(j.proposal_cost for j in self._jobs.values()),
            'heygen_total': sum(j.heygen_cost for j in self._jobs.values()),
            'other_total': sum(j.other_costs for j in self._jobs.values()),
            'grand_total': self.get_total_cost(),
        }

        # Add average per job
        if summary['total_jobs'] > 0:
            summary['avg_per_job'] = summary['grand_total'] / summary['total_jobs']
        else:
            summary['avg_per_job'] = 0.0

        return summary

    def reset(self):
        """Clear all tracked costs."""
        self._jobs.clear()

    def to_dict(self) -> dict:
        """Export all data as dictionary."""
        return {
            'jobs': {job_id: job.to_dict() for job_id, job in self._jobs.items()},
            'summary': self.get_summary()
        }

    def to_json(self, filepath: str):
        """Export all data to JSON file."""
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)


def estimate_full_job_cost(
    prefilter_passed: bool = True,
    video_duration_seconds: float = DEFAULT_VIDEO_DURATION,
    use_extended_thinking: bool = True
) -> Dict[str, float]:
    """
    Estimate the full cost of processing a job through the pipeline.

    Args:
        prefilter_passed: Whether the job passed pre-filter
        video_duration_seconds: Expected video duration
        use_extended_thinking: Whether proposal uses extended thinking

    Returns:
        Dictionary with cost breakdown and total
    """
    tracker = CostTracker()
    job_id = "estimate"

    # Pre-filter always runs
    prefilter_cost = tracker.track_prefilter(job_id)

    costs = {
        'prefilter': prefilter_cost,
        'deep_extract': 0.0,
        'proposal': 0.0,
        'heygen': 0.0,
        'total': prefilter_cost,
    }

    if prefilter_passed:
        # Deep extraction
        costs['deep_extract'] = tracker.track_deep_extract(job_id)

        # Proposal generation
        if use_extended_thinking:
            costs['proposal'] = tracker.track_proposal(job_id)
        else:
            # Without extended thinking
            costs['proposal'] = tracker.track_proposal(
                job_id,
                thinking_tokens=0
            )

        # HeyGen video
        costs['heygen'] = tracker.track_heygen(job_id, video_duration_seconds)

        costs['total'] = tracker.get_job_costs(job_id).total

    return costs


def extract_anthropic_usage(response) -> Dict[str, int]:
    """
    Extract token usage from Anthropic API response.

    Args:
        response: Anthropic API response object

    Returns:
        Dictionary with input_tokens, output_tokens, and optional thinking_tokens
    """
    usage = {}

    if hasattr(response, 'usage'):
        usage['input_tokens'] = getattr(response.usage, 'input_tokens', 0)
        usage['output_tokens'] = getattr(response.usage, 'output_tokens', 0)

        # Check for thinking tokens (extended thinking)
        if hasattr(response.usage, 'cache_creation_input_tokens'):
            # Note: Thinking tokens aren't directly exposed, estimate from response
            pass

    return usage


# Global tracker instance for convenience
_global_tracker: Optional[CostTracker] = None


def get_global_tracker() -> CostTracker:
    """Get or create global cost tracker instance."""
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = CostTracker()
    return _global_tracker


def reset_global_tracker():
    """Reset the global cost tracker."""
    global _global_tracker
    _global_tracker = CostTracker()


# CLI for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Upwork Cost Tracker")
    parser.add_argument("--estimate", action="store_true",
                       help="Show estimated cost for a full job")
    parser.add_argument("--video-duration", type=float, default=60,
                       help="Video duration in seconds (default: 60)")
    parser.add_argument("--no-thinking", action="store_true",
                       help="Estimate without extended thinking")

    args = parser.parse_args()

    if args.estimate:
        print("=" * 60)
        print("COST ESTIMATE: Full Job Pipeline")
        print("=" * 60)

        # Job that passes pre-filter
        costs = estimate_full_job_cost(
            prefilter_passed=True,
            video_duration_seconds=args.video_duration,
            use_extended_thinking=not args.no_thinking
        )

        print("\nJob that PASSES pre-filter:")
        print(f"  Pre-filter (Sonnet):      ${costs['prefilter']:.4f}")
        print(f"  Deep extraction:          ${costs['deep_extract']:.4f}")
        print(f"  Proposal (Opus 4.5):      ${costs['proposal']:.4f}")
        print(f"  HeyGen video ({args.video_duration}s):    ${costs['heygen']:.4f}")
        print(f"  ─────────────────────────────────")
        print(f"  TOTAL:                    ${costs['total']:.4f}")

        # Job that fails pre-filter
        costs_filtered = estimate_full_job_cost(prefilter_passed=False)
        print("\nJob that FAILS pre-filter:")
        print(f"  Pre-filter (Sonnet):      ${costs_filtered['prefilter']:.4f}")
        print(f"  TOTAL:                    ${costs_filtered['total']:.4f}")

        # Cost comparison
        print("\n" + "=" * 60)
        print("BATCH COST ANALYSIS (100 jobs, 25% pass rate)")
        print("=" * 60)

        total_jobs = 100
        pass_rate = 0.25
        passed_jobs = int(total_jobs * pass_rate)

        prefilter_total = costs_filtered['total'] * total_jobs
        processing_total = (costs['total'] - costs['prefilter']) * passed_jobs
        with_filter = prefilter_total + processing_total
        without_filter = costs['total'] * total_jobs
        savings = without_filter - with_filter
        savings_pct = (savings / without_filter) * 100

        print(f"\nWith pre-filter ({pass_rate*100:.0f}% pass rate):")
        print(f"  Pre-filter (all {total_jobs} jobs):   ${prefilter_total:.2f}")
        print(f"  Full processing ({passed_jobs} jobs): ${processing_total:.2f}")
        print(f"  TOTAL:                        ${with_filter:.2f}")

        print(f"\nWithout pre-filter:")
        print(f"  Full processing (all {total_jobs} jobs): ${without_filter:.2f}")

        print(f"\nSAVINGS: ${savings:.2f} ({savings_pct:.1f}%)")
    else:
        # Demo usage
        print("Cost Tracker Demo")
        print("-" * 40)

        tracker = CostTracker()

        # Track a sample job
        job_id = "~123456"

        tracker.track_prefilter(job_id, input_tokens=850, output_tokens=120)
        tracker.track_deep_extract(job_id)
        tracker.track_proposal(job_id, input_tokens=1800, output_tokens=600, thinking_tokens=5500)
        tracker.track_heygen(job_id, duration_seconds=75)

        # Print summary
        costs = tracker.get_job_costs(job_id)
        print(costs.summary())

        print("\n" + "=" * 40)
        print("Overall Summary:")
        summary = tracker.get_summary()
        for key, value in summary.items():
            if isinstance(value, float):
                print(f"  {key}: ${value:.4f}")
            else:
                print(f"  {key}: {value}")
