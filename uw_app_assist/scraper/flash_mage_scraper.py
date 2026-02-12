"""Scraper using flash_mage/upwork Apify actor.

Drop-in replacement for upwork_apify_scraper.scrape_upwork_jobs().
Returns the same flat dict format expected by the pipeline.
"""

import logging

from ..apify_runner import run_actor
from ..config import APIFY_API_TOKEN, FLASH_MAGE_ACTOR_ID
from .field_mapper import format_job
from .date_filter import filter_by_date

logger = logging.getLogger(__name__)

# flash_mage fixed-price bucket strings
_FIXED_BUCKETS = ["100-499", "500-999", "1000-4999", "5000-"]
_FIXED_THRESHOLDS = [(100, 499), (500, 999), (1000, 4999), (5000, float("inf"))]


def _fixed_price_buckets(min_fixed: float | None, max_fixed: float | None) -> list[str]:
    """Map min/max fixed price to flash_mage bucket strings."""
    if min_fixed is None and max_fixed is None:
        return []
    buckets = []
    for bucket_str, (lo, hi) in zip(_FIXED_BUCKETS, _FIXED_THRESHOLDS):
        # Include bucket if its range overlaps with the requested range
        if (min_fixed is None or hi >= min_fixed) and (max_fixed is None or lo <= max_fixed):
            buckets.append(bucket_str)
    return buckets


def scrape_upwork_jobs(
    limit: int = 50,
    from_date: str = None,
    to_date: str = None,
    keywords: list[str] = None,
    min_fixed: float = None,
    max_fixed: float = None,
    min_hourly: float = None,
    max_hourly: float = None,
    payment_verified: bool = False,
    days_back: int = 1,
    sort: str = "newest",
    experience_level: str = None,
) -> list[dict]:
    """Scrape Upwork jobs using flash_mage/upwork Apify actor.

    Signature matches the existing scrape_upwork_jobs() so it can be
    used as a drop-in replacement.

    Args:
        limit: Maximum number of jobs to fetch
        from_date: Jobs posted after this date (YYYY-MM-DD)
        to_date: Jobs posted before this date (YYYY-MM-DD)
        keywords: Keywords to search for
        min_fixed: Minimum fixed price budget
        max_fixed: Maximum fixed price budget
        min_hourly: Minimum hourly rate
        max_hourly: Maximum hourly rate
        payment_verified: Only include clients with verified payment
        days_back: Default days to look back if no from_date (default 1)
        sort: Sort order (default "newest")
        experience_level: Filter by experience level

    Returns:
        List of formatted job dicts matching the pipeline contract
    """
    # Build actor input using the correct flash_mage schema
    input_data = {
        "limit": limit,
        "sort": sort,
        "hourly": True,
        "fixed": True,
        "update_boolean": False,
        "authentication": "no_authentication",
    }

    # Keywords → query (array of strings)
    if keywords:
        input_data["query"] = keywords

    # Hourly rate bounds (server-side)
    if min_hourly is not None:
        input_data["hourly_min_price"] = int(min_hourly)
    if max_hourly is not None:
        input_data["hourly_max_price"] = int(max_hourly)

    # Fixed price buckets (server-side)
    buckets = _fixed_price_buckets(min_fixed, max_fixed)
    if buckets:
        input_data["fixed_prices"] = buckets

    logger.info(
        f"Starting flash_mage scraper: limit={limit}, keywords={keywords}, "
        f"days_back={days_back}, input_data={input_data}"
    )

    # Run the actor
    raw_items = run_actor(
        actor_id=FLASH_MAGE_ACTOR_ID,
        input_data=input_data,
        token=APIFY_API_TOKEN,
    )

    logger.info(f"flash_mage returned {len(raw_items)} raw items")

    # Map to pipeline format
    jobs = [format_job(item) for item in raw_items]

    # Date filter (flash_mage has no server-side date params)
    jobs = filter_by_date(jobs, from_date=from_date, to_date=to_date, days_back=days_back)
    logger.info(f"{len(jobs)} jobs after date filter")

    # Payment verified filter
    if payment_verified:
        jobs = [j for j in jobs if j.get("client", {}).get("payment_verified")]

    # Experience level filter
    if experience_level:
        target = experience_level.lower()
        jobs = [
            j for j in jobs
            if target in j.get("experience_level", "").lower()
        ]

    logger.info(f"{len(jobs)} jobs after all filters")
    return jobs[:limit]
