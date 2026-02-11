"""Submitter package - big-brain.io/upwork-application Apify actor integration."""

from .bigbrain_submitter import submit_application
from .attachment_links import embed_attachment_links

__all__ = ["submit_application", "embed_attachment_links"]
