"""Field mapper for neatrat/upwork-job-scraper actor output.

Transforms the flat neatrat output into the dict format
expected by the uw_app pipeline.

Neatrat output fields (from real API responses):
  id, subId, title, description, url, budget (string like "$250.00" or "N/A"),
  relativeDate, absoluteDate (ISO-8601), jobType ("Hourly"/"Fixed"),
  experienceLevel ("Intermediate"/"Expert"/"Entry Level"),
  paymentVerified (true/false/"unknown"), tags (array of strings),
  clientLocation, clientName, clientNameConfidence,
  clientAvgHourlyRate, clientHireRatePercent, clientTotalSpent,
  clientRating, hasHired, allowedApplicantCountries
"""

import re


def _parse_budget_amount(budget_str: str) -> float | None:
    """Extract numeric amount from budget string like '$250.00'."""
    if not budget_str or budget_str == "N/A":
        return None
    match = re.search(r"\$?([\d,]+(?:\.\d+)?)", budget_str)
    if match:
        return float(match.group(1).replace(",", ""))
    return None


def _clean_location(loc: str) -> str:
    """Remove 'Location ' prefix that neatrat sometimes adds."""
    if not loc:
        return ""
    return re.sub(r"^Location\s+", "", loc)


def format_neatrat_job(job: dict) -> dict:
    """Transform a single neatrat result into the uw_app pipeline format."""
    job_type_raw = (job.get("jobType") or "").lower()
    if "hourly" in job_type_raw:
        budget_type = "hourly"
    elif "fixed" in job_type_raw:
        budget_type = "fixed"
    else:
        budget_type = ""

    # Budget string from neatrat (already human-readable or "N/A")
    budget_str = job.get("budget") or "N/A"
    if budget_str == "N/A":
        budget_display = "Not specified"
    elif budget_type == "hourly" and "$" not in budget_str:
        # neatrat returns hourly as "8 - 25"; normalize to "$8-$25/hr"
        budget_display = f"${budget_str.replace(' - ', '-$')}/hr"
    else:
        budget_display = budget_str

    # Budget min/max
    budget_amount = _parse_budget_amount(budget_str)
    budget_min = budget_amount if budget_type == "fixed" else None
    budget_max = budget_amount if budget_type == "fixed" else None

    # Payment verified — can be bool or string "unknown"
    pv = job.get("paymentVerified")
    payment_verified = pv is True

    return {
        "id": job.get("id") or "",
        "title": job.get("title", ""),
        "description": job.get("description", ""),
        "url": job.get("url", ""),
        "budget": budget_display,
        "budget_raw": {
            "type": budget_type,
            "min": budget_min,
            "max": budget_max,
            "amount": budget_amount,
        },
        "budget_type": budget_type,
        "budget_min": budget_min,
        "budget_max": budget_max,
        "category": "",
        "experience_level": job.get("experienceLevel") or "",
        "skills": job.get("tags") or [],
        "posted": job.get("absoluteDate") or "",
        "connects_cost": 0,
        "client": {
            "country": _clean_location(job.get("clientLocation") or ""),
            "timezone": "",
            "payment_verified": payment_verified,
            "total_spent": job.get("clientTotalSpent") or 0,
            "total_hires": 0,
            "hire_rate": job.get("clientHireRatePercent") or 0,
            "feedback_score": job.get("clientRating") or 0,
        },
        "is_featured": False,
        "source": "apify",
    }
