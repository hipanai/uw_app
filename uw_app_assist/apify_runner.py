"""Generic Apify actor runner.

Starts an actor run, polls for completion, and retrieves dataset items.
Reusable by both scraper and submitter modules.
"""

import logging
from apify_client import ApifyClient

from .config import APIFY_API_TOKEN

logger = logging.getLogger(__name__)


class ActorRunFailed(Exception):
    """Raised when an Apify actor run finishes with a non-success status."""

    def __init__(self, actor_id: str, status: str, run_id: str = ""):
        self.actor_id = actor_id
        self.status = status
        self.run_id = run_id
        super().__init__(f"Actor {actor_id} run {run_id} failed with status: {status}")


class ActorTimeout(Exception):
    """Raised when an Apify actor run exceeds the maximum wait time."""

    def __init__(self, actor_id: str, max_wait: int, run_id: str = ""):
        self.actor_id = actor_id
        self.max_wait = max_wait
        self.run_id = run_id
        super().__init__(
            f"Actor {actor_id} run {run_id} timed out after {max_wait}s"
        )


def run_actor(
    actor_id: str,
    input_data: dict,
    token: str = None,
    max_wait: int = 600,
) -> list[dict]:
    """Start an Apify actor run, wait for completion, and return dataset items.

    Args:
        actor_id: Apify actor identifier (e.g. "flash_mage/upwork")
        input_data: Input payload for the actor
        token: Apify API token (defaults to config value)
        max_wait: Maximum seconds to wait for completion (default 600)

    Returns:
        List of result items from the actor's default dataset

    Raises:
        ActorRunFailed: If the run finishes with a non-success status
        ActorTimeout: If the run exceeds max_wait seconds
    """
    client = ApifyClient(token or APIFY_API_TOKEN)

    logger.info(f"Starting actor {actor_id} with input keys: {list(input_data.keys())}")

    # Start the run and wait for it to finish (apify-client handles polling)
    run = client.actor(actor_id).call(
        run_input=input_data,
        timeout_secs=max_wait,
    )

    if run is None:
        raise ActorTimeout(actor_id, max_wait)

    run_id = run.get("id", "")
    status = run.get("status", "UNKNOWN")

    logger.info(f"Actor {actor_id} run {run_id} finished with status: {status}")

    if status != "SUCCEEDED":
        raise ActorRunFailed(actor_id, status, run_id)

    # Fetch dataset items
    dataset_id = run.get("defaultDatasetId")
    if not dataset_id:
        logger.warning(f"No dataset ID in run {run_id}, returning empty list")
        return []

    items = list(client.dataset(dataset_id).iterate_items())
    logger.info(f"Retrieved {len(items)} items from dataset {dataset_id}")

    return items
