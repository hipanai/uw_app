"""Configuration loader for uw_app_assist.

Loads from uw_app/.env (parent directory) and validates required credentials.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from uw_app root (parent of uw_app_assist)
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


def _require(var: str) -> str:
    """Get a required environment variable or raise."""
    val = os.getenv(var)
    if not val:
        raise ValueError(f"Missing required environment variable: {var}")
    return val


def _optional(var: str, default: str = "") -> str:
    return os.getenv(var, default)


# Apify
APIFY_API_TOKEN = _require("APIFY_API_TOKEN")

# Upwork credentials (for big-brain.io submitter)
UPWORK_USERNAME = _optional("UPWORK_USERNAME")
UPWORK_PASSWORD = _optional("UPWORK_PASSWORD")
UPWORK_FREELANCER_NAME = _optional("UPWORK_FREELANCER_NAME")
UPWORK_DEFAULT_ANSWER = _optional("UPWORK_DEFAULT_ANSWER")
UPWORK_PROXY_GROUP = _optional("UPWORK_PROXY_GROUP", "StaticUS3")

# Actor IDs
FLASH_MAGE_ACTOR_ID = "flash_mage/upwork"
NEATRAT_ACTOR_ID = "neatrat/upwork-job-scraper"
BIGBRAIN_ACTOR_ID = "big-brain.io/upwork-application"

# Active scraper: "neatrat" or "flash_mage"
ACTIVE_SCRAPER = _optional("APIFY_SCRAPER", "neatrat")
