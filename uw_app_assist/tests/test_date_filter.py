"""Tests for date filter."""

from datetime import datetime, timedelta, timezone

import pytest

from uw_app_assist.scraper.date_filter import filter_by_date


def _make_job(posted: str) -> dict:
    return {"id": posted, "title": "test", "posted": posted}


class TestFilterByDate:
    def test_default_days_back(self):
        """Jobs within last 24h should be included by default."""
        now = datetime.now(timezone.utc)
        recent = (now - timedelta(hours=6)).isoformat()
        old = (now - timedelta(days=3)).isoformat()

        jobs = [_make_job(recent), _make_job(old)]
        result = filter_by_date(jobs)

        assert len(result) == 1
        assert result[0]["posted"] == recent

    def test_explicit_from_date(self):
        jobs = [
            _make_job("2025-05-10T12:00:00Z"),
            _make_job("2025-05-08T12:00:00Z"),
            _make_job("2025-05-06T12:00:00Z"),
        ]
        result = filter_by_date(jobs, from_date="2025-05-09")
        posted_dates = [j["posted"] for j in result]
        assert "2025-05-10T12:00:00Z" in posted_dates
        assert "2025-05-06T12:00:00Z" not in posted_dates

    def test_explicit_date_range(self):
        jobs = [
            _make_job("2025-05-10T12:00:00Z"),
            _make_job("2025-05-08T12:00:00Z"),
            _make_job("2025-05-06T12:00:00Z"),
        ]
        result = filter_by_date(jobs, from_date="2025-05-07", to_date="2025-05-09")
        assert len(result) == 1
        assert result[0]["posted"] == "2025-05-08T12:00:00Z"

    def test_days_back_custom(self):
        now = datetime.now(timezone.utc)
        three_days_ago = (now - timedelta(days=2, hours=12)).isoformat()
        week_ago = (now - timedelta(days=7)).isoformat()

        jobs = [_make_job(three_days_ago), _make_job(week_ago)]
        result = filter_by_date(jobs, days_back=3)

        assert len(result) == 1
        assert result[0]["posted"] == three_days_ago

    def test_empty_posted_kept(self):
        """Jobs with no posted date should not be dropped."""
        jobs = [_make_job("")]
        result = filter_by_date(jobs)
        assert len(result) == 1

    def test_unparseable_date_kept(self):
        """Jobs with unparseable dates should not be dropped."""
        jobs = [_make_job("not-a-date")]
        result = filter_by_date(jobs)
        assert len(result) == 1

    def test_empty_list(self):
        assert filter_by_date([]) == []

    def test_future_dates_excluded_by_default(self):
        future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        jobs = [_make_job(future)]
        result = filter_by_date(jobs)
        assert len(result) == 0

    def test_timezone_naive_iso(self):
        """ISO dates without timezone info should still work."""
        now = datetime.now(timezone.utc)
        recent = (now - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%S")
        jobs = [_make_job(recent)]
        result = filter_by_date(jobs)
        assert len(result) == 1
