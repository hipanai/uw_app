"""Scraper package - dispatches to active Apify actor based on config."""

from ..config import ACTIVE_SCRAPER

if ACTIVE_SCRAPER == "flash_mage":
    from .flash_mage_scraper import scrape_upwork_jobs
else:
    from .neatrat_scraper import scrape_upwork_jobs

__all__ = ["scrape_upwork_jobs"]
