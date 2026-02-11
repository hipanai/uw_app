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
    used as a drop-in replacement. Parameters that flash_mage doesn't
    support server-side are applied as post-retrieval filters.

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
    # Build flash_mage actor input
    input_data = {
        "maxItems": limit,
        "sort": sort,
    }

    if keywords:
        # flash_mage accepts a search query string
        input_data["search"] = " ".join(keywords)

    logger.info(
        f"Starting flash_mage scraper: limit={limit}, keywords={keywords}, "
        f"days_back={days_back}"
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

    # Client-side budget filter
    if min_fixed is not None or max_fixed is not None:
        jobs = [
            j for j in jobs
            if j.get("budget_type") == "fixed"
            and (min_fixed is None or (j.get("budget_max") or 0) >= min_fixed)
            and (max_fixed is None or (j.get("budget_min") or 0) <= max_fixed)
        ]

    if min_hourly is not None or max_hourly is not None:
        jobs = [
            j for j in jobs
            if j.get("budget_type") == "hourly"
            and (min_hourly is None or (j.get("budget_max") or 0) >= min_hourly)
            and (max_hourly is None or (j.get("budget_min") or 0) <= max_hourly)
        ]

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
    return jobs
