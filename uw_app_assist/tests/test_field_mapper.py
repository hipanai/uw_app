"""Tests for flash_mage field mapper.

Fixtures use the real flash_mage/upwork actor output schema:
- contractorTier is a string ("INTERMEDIATE", "EXPERT", "ENTRY_LEVEL")
- Skills use prefLabel (not prettyName), split across ontologySkills and additionalSkills
- ontologySkills can be null, with skills only in additionalSkills
- budget.amount is 0 (with currencyCode) for hourly jobs, real amount for fixed
- No buyer/buyerExtra data (flash_mage doesn't return client info)
- info.premium indicates featured status
- Top-level id is an integer index, type is "detail"
"""

import json
from pathlib import Path

import pytest

from uw_app_assist.scraper.field_mapper import format_job


@pytest.fixture
def sample_jobs():
    fixture_path = Path(__file__).parent / "fixtures" / "flash_mage_sample.json"
    with open(fixture_path) as f:
        return json.load(f)


class TestFormatJob:
    def test_hourly_job_mapping(self, sample_jobs):
        """Hourly job with ontologySkills + additionalSkills."""
        result = format_job(sample_jobs[0])

        assert result["id"] == "~01abc123def456"
        assert result["title"] == "Need Python Automation Expert for Web Scraping Project"
        assert "Python developer" in result["description"]
        assert result["url"] == "https://www.upwork.com/jobs/~01abc123def456"
        assert result["budget"] == "$30-$60/hr"
        assert result["budget_type"] == "hourly"
        assert result["budget_min"] == 30
        assert result["budget_max"] == 60
        assert result["experience_level"] == "Intermediate"
        assert result["posted"] == "2025-05-10T14:30:00Z"
        assert result["source"] == "apify"
        assert result["category"] == "Web Development"
        assert result["is_featured"] is False

    def test_hourly_job_skills_from_ontology(self, sample_jobs):
        """When ontologySkills is populated, skills come from there (prefLabel)."""
        result = format_job(sample_jobs[0])
        assert "Python" in result["skills"]
        assert "Web Scraping" in result["skills"]
        assert len(result["skills"]) == 2  # only ontologySkills, not additionalSkills

    def test_hourly_job_client_defaults(self, sample_jobs):
        """flash_mage returns no buyer data, so client fields should be defaults."""
        result = format_job(sample_jobs[0])
        client = result["client"]

        assert client["country"] == ""
        assert client["payment_verified"] is False
        assert client["total_spent"] == 0
        assert client["total_hires"] == 0
        assert client["feedback_score"] == 0

    def test_fixed_job_mapping(self, sample_jobs):
        """Fixed-price job with ontologySkills=null, skills from additionalSkills."""
        result = format_job(sample_jobs[1])

        assert result["id"] == "~02xyz789ghi012"
        assert result["budget"] == "$5000 fixed"
        assert result["budget_type"] == "fixed"
        assert result["budget_min"] == 5000
        assert result["budget_max"] == 5000
        assert result["experience_level"] == "Expert"

    def test_fixed_job_skills_from_additional(self, sample_jobs):
        """When ontologySkills is null, skills come from additionalSkills."""
        result = format_job(sample_jobs[1])
        assert "React" in result["skills"]
        assert "TypeScript" in result["skills"]
        assert "D3.js" in result["skills"]
        assert len(result["skills"]) == 3

    def test_entry_level_mapping(self, sample_jobs):
        """ENTRY_LEVEL string tier maps to 'Entry Level'."""
        result = format_job(sample_jobs[2])

        assert result["experience_level"] == "Entry Level"
        assert result["budget"] == "$100 fixed"
        assert result["budget_type"] == "fixed"
        assert result["category"] == "Administrative Support"

    def test_hourly_budget_amount_zero_ignored(self, sample_jobs):
        """budget.amount=0 for hourly jobs should not produce '$0 fixed'."""
        result = format_job(sample_jobs[0])
        assert "$0" not in result["budget"]

    def test_featured_job(self, sample_jobs):
        """Job with info.premium=true should have is_featured=True."""
        result = format_job(sample_jobs[3])

        assert result["is_featured"] is True
        assert result["id"] == "~04featured999abc"
        assert result["experience_level"] == "Intermediate"
        assert result["category"] == "Digital Marketing"

    def test_hidden_budget_no_range(self, sample_jobs):
        """Hourly job with empty extendedBudgetInfo shows 'Not specified'."""
        result = format_job(sample_jobs[3])
        assert result["budget"] == "Not specified"
        assert result["budget_min"] is None
        assert result["budget_max"] is None

    def test_featured_job_skills_from_ontology_with_additional(self, sample_jobs):
        """When ontologySkills has entries, only those are used (not additionalSkills)."""
        result = format_job(sample_jobs[3])
        assert result["skills"] == ["Google Ads"]

    def test_empty_job_no_crash(self):
        """Mapping an empty dict should not raise."""
        result = format_job({})
        assert result["id"] == ""
        assert result["title"] == ""
        assert result["source"] == "apify"
        assert result["category"] == ""
        assert result["is_featured"] is False

    def test_all_required_keys_present(self, sample_jobs):
        """Every mapped job must have the full set of pipeline-required keys."""
        required_keys = {
            "id", "title", "description", "url", "budget", "budget_raw",
            "category", "experience_level", "skills", "posted",
            "connects_cost", "client", "is_featured", "source",
        }
        client_keys = {
            "country", "timezone", "payment_verified",
            "total_spent", "total_hires", "hire_rate", "feedback_score",
        }

        for job_data in sample_jobs:
            result = format_job(job_data)
            assert required_keys.issubset(result.keys()), f"Missing keys: {required_keys - result.keys()}"
            assert client_keys.issubset(result["client"].keys()), f"Missing client keys: {client_keys - result['client'].keys()}"

    def test_budget_raw_structure(self, sample_jobs):
        """budget_raw should contain type, min, max, and amount."""
        # Hourly job
        r = format_job(sample_jobs[0])
        assert r["budget_raw"]["type"] == "hourly"
        assert r["budget_raw"]["min"] == 30
        assert r["budget_raw"]["max"] == 60
        assert r["budget_raw"]["amount"] == 0  # hourly jobs have amount=0

        # Fixed job
        r2 = format_job(sample_jobs[1])
        assert r2["budget_raw"]["type"] == "fixed"
        assert r2["budget_raw"]["min"] == 5000
        assert r2["budget_raw"]["max"] == 5000
        assert r2["budget_raw"]["amount"] == 5000
