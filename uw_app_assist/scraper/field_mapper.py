"""Field mapper for flash_mage/upwork actor output.

Transforms the nested flash_mage output into the flat dict format
expected by the existing uw_app pipeline (matching upwork_apify_scraper.format_job).
"""

from typing import Any


def _deep_get(data: dict, *keys, default=None) -> Any:
    """Safely traverse nested dicts."""
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def _format_budget(job: dict) -> str:
    """Build a human-readable budget string."""
    opening = _deep_get(job, "data", "opening") or {}

    # Check extended budget info first (has hourly range)
    ext = opening.get("extendedBudgetInfo") or {}
    hourly_min = ext.get("hourlyBudgetMin")
    hourly_max = ext.get("hourlyBudgetMax")
    if hourly_min is not None or hourly_max is not None:
        h_min = hourly_min or 0
        h_max = hourly_max or h_min
        return f"${h_min}-${h_max}/hr"

    # Fixed budget
    budget_amount = _deep_get(opening, "budget", "amount")
    if budget_amount is not None:
        return f"${budget_amount} fixed"

    return "Not specified"


def _map_experience_level(tier: int | None) -> str:
    """Map contractorTier integer to human-readable level."""
    mapping = {1: "Entry Level", 2: "Intermediate", 3: "Expert"}
    return mapping.get(tier, "")


def format_job(job: dict) -> dict:
    """Transform a single flash_mage result into the uw_app pipeline format.

    Args:
        job: Raw item from the flash_mage/upwork actor dataset

    Returns:
        Dict matching the contract used by upwork_apify_scraper.format_job()
    """
    opening = _deep_get(job, "data", "opening") or {}
    info = opening.get("info") or {}
    buyer = opening.get("buyer") or {}
    buyer_stats = buyer.get("stats") or {}
    buyer_location = buyer.get("location") or {}
    buyer_extra = _deep_get(job, "data", "opening", "buyerExtra") or {}
    ext_budget = opening.get("extendedBudgetInfo") or {}

    # Skills from ontologySkills
    sands = opening.get("sandsData") or {}
    skills_raw = sands.get("ontologySkills") or []
    skills = [s.get("prettyName", "") for s in skills_raw if s.get("prettyName")]

    # Budget type
    job_type = (info.get("type") or "").upper()
    if "HOURLY" in job_type:
        budget_type = "hourly"
    elif "FIXED" in job_type:
        budget_type = "fixed"
    else:
        budget_type = ""

    # Budget min/max
    budget_min = None
    budget_max = None
    if budget_type == "hourly":
        budget_min = ext_budget.get("hourlyBudgetMin")
        budget_max = ext_budget.get("hourlyBudgetMax")
    elif budget_type == "fixed":
        amount = _deep_get(opening, "budget", "amount")
        if amount is not None:
            budget_min = amount
            budget_max = amount

    # Build the flat dict matching existing pipeline contract
    return {
        "id": info.get("ciphertext") or job.get("id", ""),
        "title": info.get("title") or job.get("title", ""),
        "description": opening.get("description", ""),
        "url": job.get("link", ""),
        "budget": _format_budget(job),
        "budget_raw": {
            "type": budget_type,
            "min": budget_min,
            "max": budget_max,
            "amount": _deep_get(opening, "budget", "amount"),
        },
        "budget_type": budget_type,
        "budget_min": budget_min,
        "budget_max": budget_max,
        "category": "",
        "experience_level": _map_experience_level(opening.get("contractorTier")),
        "skills": skills,
        "posted": opening.get("postedOn", ""),
        "connects_cost": 0,
        "client": {
            "country": buyer_location.get("country", ""),
            "timezone": "",
            "payment_verified": buyer_extra.get("isPaymentMethodVerified", False),
            "total_spent": _deep_get(buyer_stats, "totalCharges", "amount") or 0,
            "total_hires": buyer_stats.get("totalAssignments") or 0,
            "hire_rate": 0,
            "feedback_score": buyer_stats.get("score") or 0,
        },
        "is_featured": False,
        "source": "apify",
    }
