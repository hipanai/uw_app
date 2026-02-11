"""Embed video/PDF links into proposal text for the Apify submitter.

The Apify-based big-brain.io actor only accepts text — it cannot upload
file attachments the way the Playwright submitter can.  This helper appends
cloud-hosted video and PDF URLs to the cover letter so the client can
access them directly.
"""


def embed_attachment_links(
    proposal_text: str,
    video_url: str | None = None,
    pdf_url: str | None = None,
) -> str:
    """Append video and/or PDF links to *proposal_text*.

    Only URLs that start with ``http`` are included — local file paths and
    empty/None values are silently ignored.

    Returns the original text unchanged when no valid URLs are provided.
    """
    links: list[str] = []

    if video_url and isinstance(video_url, str) and video_url.startswith("http"):
        links.append(f"Video introduction: {video_url}")

    if pdf_url and isinstance(pdf_url, str) and pdf_url.startswith("http"):
        links.append(f"Portfolio/resume: {pdf_url}")

    if not links:
        return proposal_text

    separator = "\n\n---\n"
    return proposal_text + separator + "\n".join(links)
