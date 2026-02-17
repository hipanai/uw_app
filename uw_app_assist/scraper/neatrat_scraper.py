"""Scraper using neatrat/upwork-job-scraper Apify actor.

Drop-in replacement for flash_mage_scraper.scrape_upwork_jobs().
Returns the same flat dict format expected by the pipeline.
"""

import math
import logging

from ..apify_runner import run_actor
from ..config import APIFY_API_TOKEN, NEATRAT_ACTOR_ID
from .neatrat_field_mapper import format_neatrat_job
from .date_filter import filter_by_date

logger = logging.getLogger(__name__)

# neatrat experience level values (array items)
_EXP_MAP = {
    "entry level": "entry",
    "entry": "entry",
    "intermediate": "intermediate",
    "expert": "expert",
}


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
    """Scrape Upwork jobs using neatrat/upwork-job-scraper Apify actor.

    Same signature as flash_mage_scraper.scrape_upwork_jobs() so it can be
    used as a drop-in replacement.
    """
    # neatrat paginates: perPage (min 10, max 50) * pagesToScrape
    per_page = max(10, min(limit, 50))
    pages = max(1, math.ceil(limit / per_page))

    input_data: dict = {
        "perPage": per_page,
        "pagesToScrape": pages,
        "sort": "relevance" if sort.lower() == "relevance" else "newest",
    }

    # Keywords → query
    if keywords:
        input_data["query"] = " ".join(keywords)

    # Job type filter (array of strings)
    job_types = []
    if min_hourly is not None or max_hourly is not None:
        job_types.append("hourly")
    if min_fixed is not None or max_fixed is not None:
        job_types.append("fixed")
    if job_types:
        input_data["jobType"] = job_types

    # Hourly rate range [min, max] as string array
    if min_hourly is not None or max_hourly is not None:
        input_data["hourlyRateRange"] = [
            str(int(min_hourly or 0)),
            str(int(max_hourly or 999)),
        ]

    # Fixed price range [min, max] as string array
    if min_fixed is not None or max_fixed is not None:
        input_data["fixedPriceRange"] = [
            str(int(min_fixed or 0)),
            str(int(max_fixed or 999999)),
        ]

    # Payment verified
    if payment_verified:
        input_data["paymentVerified"] = True

    # Max job age as object {value, unit}
    if days_back:
        input_data["maxJobAge"] = {"value": days_back * 24, "unit": "hours"}

    # Experience level (array)
    if experience_level:
        mapped = _EXP_MAP.get(experience_level.lower().strip())
        if mapped:
            input_data["experienceLevel"] = [mapped]

    logger.info(
        f"Starting neatrat scraper: limit={limit}, keywords={keywords}, "
        f"days_back={days_back}, input_data={input_data}"
    )

    raw_items = run_actor(
        actor_id=NEATRAT_ACTOR_ID,
        input_data=input_data,
        token=APIFY_API_TOKEN,
    )

    logger.info(f"neatrat returned {len(raw_items)} raw items")

    # Map to pipeline format
    jobs = [format_neatrat_job(item) for item in raw_items]

    # Date filter (neatrat has maxJobAge but we still apply precise filtering)
    jobs = filter_by_date(jobs, from_date=from_date, to_date=to_date, days_back=days_back)
    logger.info(f"{len(jobs)} jobs after date filter")

    # Payment verified filter (also applied server-side, but belt-and-suspenders)
    if payment_verified:
        jobs = [j for j in jobs if j.get("client", {}).get("payment_verified")]

    # Experience level filter (server-side may not be exact)
    if experience_level:
        target = experience_level.lower()
        jobs = [
            j for j in jobs
            if target in j.get("experience_level", "").lower()
        ]

    logger.info(f"{len(jobs)} jobs after all filters")
    return jobs[:limit]
