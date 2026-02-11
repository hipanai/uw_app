"""Tests for flash_mage field mapper."""

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
        """Test mapping of an hourly job with full data."""
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
        assert "Python" in result["skills"]
        assert "Web Scraping" in result["skills"]
        assert len(result["skills"]) == 5
        assert result["posted"] == "2025-05-10T14:30:00Z"
        assert result["source"] == "apify"

    def test_hourly_job_client(self, sample_jobs):
        result = format_job(sample_jobs[0])
        client = result["client"]

        assert client["country"] == "United States"
        assert client["payment_verified"] is True
        assert client["total_spent"] == 125000.50
        assert client["total_hires"] == 47
        assert client["feedback_score"] == 4.9

    def test_fixed_job_mapping(self, sample_jobs):
        """Test mapping of a fixed-price job."""
        result = format_job(sample_jobs[1])

        assert result["id"] == "~02xyz789ghi012"
        assert result["budget"] == "$5000 fixed"
        assert result["budget_type"] == "fixed"
        assert result["budget_min"] == 5000
        assert result["budget_max"] == 5000
        assert result["experience_level"] == "Expert"

    def test_entry_level_mapping(self, sample_jobs):
        result = format_job(sample_jobs[2])

        assert result["experience_level"] == "Entry Level"
        assert result["client"]["payment_verified"] is False
        assert result["budget"] == "$100 fixed"

    def test_empty_job_no_crash(self):
        """Mapping an empty dict should not raise."""
        result = format_job({})
        assert result["id"] == ""
        assert result["title"] == ""
        assert result["source"] == "apify"

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
