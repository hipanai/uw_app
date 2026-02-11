"""Post-retrieval date/time filtering for scraped jobs.

flash_mage/upwork has no date range input params, so we over-fetch
with sort: "newest" and filter client-side.
"""

from datetime import datetime, timedelta, timezone


def _parse_iso(date_str: str) -> datetime | None:
    """Parse an ISO-8601 date string to a timezone-aware datetime."""
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def filter_by_date(
    jobs: list[dict],
    from_date: str | None = None,
    to_date: str | None = None,
    days_back: int = 1,
) -> list[dict]:
    """Filter jobs by their posted date.

    Args:
        jobs: List of formatted job dicts (must have 'posted' field)
        from_date: Include jobs posted on or after this date (YYYY-MM-DD)
        to_date: Include jobs posted on or before this date (YYYY-MM-DD)
        days_back: If no from_date, look back this many days (default 1)

    Returns:
        Filtered list of jobs
    """
    now = datetime.now(timezone.utc)

    # Determine cutoff dates
    if from_date:
        cutoff_start = _parse_iso(from_date) or _parse_iso(from_date + "T00:00:00Z")
    else:
        cutoff_start = now - timedelta(days=days_back)

    if to_date:
        cutoff_end = _parse_iso(to_date) or _parse_iso(to_date + "T23:59:59Z")
    else:
        cutoff_end = now

    if cutoff_start is None:
        cutoff_start = now - timedelta(days=days_back)
    if cutoff_end is None:
        cutoff_end = now

    filtered = []
    for job in jobs:
        posted = _parse_iso(job.get("posted", ""))
        if posted is None:
            # Keep jobs with unparseable dates (don't silently drop)
            filtered.append(job)
            continue
        if cutoff_start <= posted <= cutoff_end:
            filtered.append(job)

    return filtered
