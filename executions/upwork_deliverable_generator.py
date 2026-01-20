#!/usr/bin/env python3
"""
Upwork Deliverable Generator

Orchestrates the creation of all job application deliverables:
1. Proposal Google Doc (conversational format)
2. Proposal PDF export
3. HeyGen video cover letter

Features #33-36: Deliverable generation pipeline

Usage:
    python executions/upwork_deliverable_generator.py --job job_data.json
    python executions/upwork_deliverable_generator.py --jobs batch.json --parallel 3
"""

import os
import sys
import re
import json
import asyncio
import argparse
import tempfile
import threading
import logging
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Union
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if os.getenv("DEBUG") else logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Try to load dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Semaphore for Google API calls to avoid SSL errors
DOC_CREATION_LOCK = threading.Semaphore(1)

# Constants
TMP_DIR = Path(".tmp")
TMP_DIR.mkdir(exist_ok=True)


@dataclass
class JobData:
    """Standardized job data structure."""
    job_id: str
    title: str
    description: str
    url: str
    skills: List[str] = field(default_factory=list)
    budget_type: str = "unknown"
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    client_country: Optional[str] = None
    client_spent: Optional[float] = None
    client_hires: Optional[int] = None
    payment_verified: bool = False
    attachments: List[Dict] = field(default_factory=list)
    attachment_content: Optional[str] = None
    fit_score: Optional[int] = None
    fit_reasoning: Optional[str] = None
    contact_name: Optional[str] = None
    contact_confidence: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict) -> 'JobData':
        """Create JobData from a dictionary, handling various formats."""
        # Handle job_id from various sources
        job_id = data.get('job_id') or data.get('id') or ''
        if not job_id and data.get('url'):
            # Extract from URL
            import re
            match = re.search(r'~(\w+)', data['url'])
            if match:
                job_id = f"~{match.group(1)}"

        # Handle skills as list or string
        skills = data.get('skills', [])
        if isinstance(skills, str):
            skills = [s.strip() for s in skills.split(',') if s.strip()]

        # Handle client data
        client = data.get('client', {})
        if isinstance(client, dict):
            client_country = client.get('country') or data.get('client_country')
            client_spent = client.get('total_spent') or data.get('client_spent')
            client_hires = client.get('total_hires') or data.get('client_hires')
        else:
            client_country = data.get('client_country')
            client_spent = data.get('client_spent')
            client_hires = data.get('client_hires')

        return cls(
            job_id=job_id,
            title=data.get('title', ''),
            description=data.get('description', ''),
            url=data.get('url', ''),
            skills=skills,
            budget_type=data.get('budget_type', 'unknown'),
            budget_min=data.get('budget_min'),
            budget_max=data.get('budget_max'),
            client_country=client_country,
            client_spent=client_spent,
            client_hires=client_hires,
            payment_verified=data.get('payment_verified', False),
            attachments=data.get('attachments', []),
            attachment_content=data.get('attachment_content'),
            fit_score=data.get('fit_score'),
            fit_reasoning=data.get('fit_reasoning'),
            contact_name=data.get('contact_name'),
            contact_confidence=data.get('contact_confidence'),
        )


@dataclass
class ProposalContent:
    """Generated proposal content."""
    greeting: str
    intro: str
    approach: str
    deliverables: str
    timeline: str
    full_text: str


@dataclass
class DeliverableResult:
    """Result of deliverable generation."""
    job_id: str
    success: bool
    proposal_doc_url: Optional[str] = None
    pdf_url: Optional[str] = None
    video_url: Optional[str] = None
    proposal_text: Optional[str] = None
    cover_letter: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


def get_google_services(mock: bool = False):
    """Initialize Google API services."""
    if mock:
        return None, None, None

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        token_path = Path('config/token.json')
        if not token_path.exists():
            logger.error("Google token not found at config/token.json")
            return None, None, None

        with open(token_path, 'r') as f:
            token_data = json.load(f)
        available_scopes = token_data.get('scopes', [])

        creds = Credentials.from_authorized_user_file(str(token_path), available_scopes)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())

        drive_service = build('drive', 'v3', credentials=creds)

        # Check for docs scope
        has_docs_scope = 'https://www.googleapis.com/auth/documents' in available_scopes
        docs_service = build('docs', 'v1', credentials=creds) if has_docs_scope else None

        # Check for sheets scope (for PDF upload tracking)
        has_sheets_scope = any('spreadsheets' in s for s in available_scopes)
        sheets_service = build('sheets', 'v4', credentials=creds) if has_sheets_scope else None

        return drive_service, docs_service, sheets_service

    except Exception as e:
        logger.error(f"Failed to initialize Google services: {e}")
        return None, None, None


# Common name patterns for contact discovery
# Signature patterns like "Thanks, John" or "Best, Sarah"
SIGNATURE_PATTERNS = [
    r'(?:thanks|thank you|regards|best|cheers|sincerely|warm regards|best regards|kind regards),?\s+([A-Z][a-z]+)',
    r'(?:thanks|thank you|regards|best|cheers|sincerely|warm regards|best regards|kind regards)\s*[-–—]\s*([A-Z][a-z]+)',
    r'^([A-Z][a-z]+)$',  # Single name on its own line at end
    r'(?:^|\n)[-–—]?\s*([A-Z][a-z]+)\s*$',  # Name at end of text
]

# Introduction patterns like "My name is John" or "I'm Sarah"
INTRO_PATTERNS = [
    r"(?:my name is|i'm|i am|this is)\s+([A-Z][a-z]+)",
    r"(?:^|\n)hi,?\s+i'm\s+([A-Z][a-z]+)",
]

# Names to exclude (common false positives)
EXCLUDED_NAMES = {
    'Upwork', 'Thanks', 'Thank', 'Regards', 'Best', 'Cheers',
    'Sincerely', 'Please', 'Hello', 'Looking', 'Required',
    'Skills', 'Requirements', 'About', 'Description', 'Budget',
    'Fixed', 'Hourly', 'Experience', 'Project', 'Client'
}


@dataclass
class ContactDiscoveryResult:
    """Result of contact name discovery."""
    contact_name: Optional[str]
    contact_confidence: str  # 'high', 'medium', 'low'
    source: str  # 'signature', 'introduction', 'none'

    def to_dict(self) -> Dict:
        return asdict(self)


def discover_contact_name(description: str) -> ContactDiscoveryResult:
    """
    Discover contact name from job description.

    Looks for:
    1. Signature patterns like "Thanks, John" (high confidence)
    2. Introduction patterns like "My name is John" (high confidence)
    3. Name at end of description (medium confidence)

    Args:
        description: Job description text

    Returns:
        ContactDiscoveryResult with name, confidence level, and source
    """
    if not description:
        return ContactDiscoveryResult(
            contact_name=None,
            contact_confidence='low',
            source='none'
        )

    # Clean the description
    text = description.strip()

    # Try signature patterns first (highest confidence)
    for pattern in SIGNATURE_PATTERNS[:3]:  # First 3 are direct signature patterns
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            name = match.group(1).strip()
            if name and name not in EXCLUDED_NAMES and len(name) >= 2:
                # Capitalize properly
                name = name.capitalize()
                return ContactDiscoveryResult(
                    contact_name=name,
                    contact_confidence='high',
                    source='signature'
                )

    # Try introduction patterns (high confidence)
    for pattern in INTRO_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            if name and name not in EXCLUDED_NAMES and len(name) >= 2:
                name = name.capitalize()
                return ContactDiscoveryResult(
                    contact_name=name,
                    contact_confidence='high',
                    source='introduction'
                )

    # Try name at end of description (medium confidence)
    # Look at the last few lines
    lines = text.strip().split('\n')
    for line in reversed(lines[-5:]):  # Check last 5 lines
        line = line.strip()
        if not line:
            continue
        # Look for a short line that could be just a name
        match = re.match(r'^[-–—]?\s*([A-Z][a-z]+)\s*$', line)
        if match:
            name = match.group(1).strip()
            if name and name not in EXCLUDED_NAMES and len(name) >= 2:
                name = name.capitalize()
                return ContactDiscoveryResult(
                    contact_name=name,
                    contact_confidence='medium',
                    source='signature'
                )

    # No name found
    return ContactDiscoveryResult(
        contact_name=None,
        contact_confidence='low',
        source='none'
    )


def enrich_job_with_contact(job: 'JobData') -> 'JobData':
    """
    Enrich a JobData instance with contact discovery.

    If contact_name is not already set, attempts to discover it from the description.
    """
    if job.contact_name:
        # Already has contact info
        return job

    result = discover_contact_name(job.description)
    job.contact_name = result.contact_name
    job.contact_confidence = result.contact_confidence
    return job


def format_greeting(contact_name: Optional[str], contact_confidence: Optional[str]) -> str:
    """Format the greeting based on contact discovery results."""
    if not contact_name:
        return "Hey"

    if contact_confidence in ['medium', 'low']:
        return f"Hey {contact_name} (if I have the right person)"
    return f"Hey {contact_name}"


def generate_proposal_content(
    job: JobData,
    anthropic_client=None,
    mock: bool = False
) -> ProposalContent:
    """Generate proposal content using Opus 4.5 with extended thinking."""

    greeting = format_greeting(job.contact_name, job.contact_confidence)

    if mock:
        # Return mock content for testing
        return ProposalContent(
            greeting=greeting,
            intro=f"I spent ~15 minutes putting this together for you. In short, it's how I would create your {job.title[:30]} end to end.",
            approach="1. First, I would analyze your requirements...\n2. Then build the core automation...\n3. Test thoroughly...\n4. Deploy and document.",
            deliverables="- Working automation system\n- Documentation\n- Training session",
            timeline="I can typically deliver this within 1-2 weeks.",
            full_text=f"{greeting}.\n\nI spent ~15 minutes putting this together for you...\n\nMy proposed approach\n\n1. First step...\n\nWhat you'll get\n\n- Deliverable 1\n\nTimeline\n\nRealistic timeline here."
        )

    if not anthropic_client:
        import anthropic
        anthropic_client = anthropic.Anthropic()

    # Build context from job data
    skills_str = ', '.join(job.skills[:10]) if job.skills else 'Not specified'
    budget_str = f"${job.budget_min}-${job.budget_max}" if job.budget_min else "Not specified"

    # Include attachment content if available
    attachment_context = ""
    if job.attachment_content:
        attachment_context = f"""
ATTACHMENT CONTENT (additional requirements):
{job.attachment_content[:2000]}
"""

    prompt = f"""Write a personalized project proposal for this Upwork job. Write as Nick - first person, conversational, direct.

JOB DETAILS:
Title: {job.title}
Description: {job.description[:1500]}
Skills Required: {skills_str}
Budget: {budget_str}
{attachment_context}

PROPOSAL FORMAT:

{greeting}.

I spent ~15 minutes putting this together for you. In short, it's how I would create your [2-4 word paraphrase of their system/need] end to end.

I've worked with $MM companies like Anthropic (yes--that Anthropic) and I have a lot of experience designing/building similar workflows.

Here's a step-by-step, along with my reasoning at every point:

My proposed approach

[Provide 4-6 detailed numbered steps. For each step:
- Start with what you'd do
- Explain WHY this approach (the reasoning)
- Mention specific tools/tech where relevant (n8n, Claude API, Zapier, Make, GPT, etc.)
- Keep it conversational, like you're explaining to a smart person]

What you'll get

[2-3 concrete deliverables, be specific]

Timeline

[Realistic estimate, conversational tone]

TONE RULES:
- First person ("I would...", "Here's how I'd...")
- Direct and confident, not salesy
- Like you're talking to a peer, not pitching
- Specific technical details, no fluff
- Use plain text with clear section headers (no markdown symbols like ** or #)
- Total ~300-400 words

Return ONLY the proposal text."""

    response = anthropic_client.messages.create(
        model="claude-opus-4-5-20251101",
        max_tokens=10000,
        messages=[{"role": "user", "content": prompt}]
    )

    # Extract text from response
    full_text = ""
    for block in response.content:
        if block.type == "text":
            full_text = block.text.strip()
            break

    # Parse sections (best effort)
    approach = ""
    deliverables = ""
    timeline = ""

    if "My proposed approach" in full_text:
        parts = full_text.split("My proposed approach")
        if len(parts) > 1:
            rest = parts[1]
            if "What you'll get" in rest:
                approach = rest.split("What you'll get")[0].strip()
                rest = rest.split("What you'll get")[1]
                if "Timeline" in rest:
                    deliverables = rest.split("Timeline")[0].strip()
                    timeline = rest.split("Timeline")[1].strip()

    return ProposalContent(
        greeting=greeting,
        intro=full_text.split("My proposed approach")[0].strip() if "My proposed approach" in full_text else "",
        approach=approach,
        deliverables=deliverables,
        timeline=timeline,
        full_text=full_text
    )


def create_google_doc(
    title: str,
    content: str,
    drive_service,
    docs_service,
    max_retries: int = 4,
    base_delay: float = 1.5
) -> Optional[str]:
    """Create a Google Doc with proposal content and return the URL."""

    if not docs_service or not drive_service:
        logger.warning("Google services not available")
        return None

    import time

    def _create():
        # Create the document
        doc = docs_service.documents().create(body={
            'title': f"Proposal: {title[:50]}"
        }).execute()

        doc_id = doc.get('documentId')

        # Build formatting requests
        requests = []
        current_index = 1

        # Section headers to make bold
        headers = ['My proposed approach', "What you'll get", 'Timeline',
                   'Project Understanding', 'Proposed Approach', 'Deliverables',
                   'Timeline & Investment', 'Investment', 'Why Me']

        lines = content.split('\n')

        for line in lines:
            if not line.strip():
                requests.append({
                    'insertText': {
                        'location': {'index': current_index},
                        'text': '\n'
                    }
                })
                current_index += 1
                continue

            is_header = any(line.strip().startswith(h) or line.strip() == h for h in headers)
            is_bullet = line.strip().startswith('- ') or line.strip().startswith('* ')

            if is_bullet:
                clean_line = line.strip()[2:].strip()
                text_to_insert = f"* {clean_line}\n"
            else:
                text_to_insert = f"{line.strip()}\n"

            requests.append({
                'insertText': {
                    'location': {'index': current_index},
                    'text': text_to_insert
                }
            })

            if is_header:
                requests.append({
                    'updateTextStyle': {
                        'range': {
                            'startIndex': current_index,
                            'endIndex': current_index + len(text_to_insert) - 1
                        },
                        'textStyle': {
                            'bold': True,
                            'fontSize': {'magnitude': 12, 'unit': 'PT'}
                        },
                        'fields': 'bold,fontSize'
                    }
                })

            current_index += len(text_to_insert)

        # Execute all requests
        if requests:
            docs_service.documents().batchUpdate(
                documentId=doc_id,
                body={'requests': requests}
            ).execute()

        # Make publicly viewable with link
        drive_service.permissions().create(
            fileId=doc_id,
            body={'type': 'anyone', 'role': 'reader'},
            fields='id'
        ).execute()

        return f"https://docs.google.com/document/d/{doc_id}"

    # Retry with exponential backoff
    for attempt in range(max_retries):
        try:
            with DOC_CREATION_LOCK:
                return _create()
        except Exception as e:
            if attempt == max_retries - 1:
                logger.error(f"Failed to create doc after {max_retries} attempts: {e}")
                raise
            delay = base_delay * (2 ** attempt)
            logger.warning(f"Doc creation attempt {attempt + 1} failed, retrying in {delay}s: {e}")
            time.sleep(delay)

    return None


def export_doc_to_pdf(doc_id: str, drive_service, output_path: Optional[Path] = None) -> Optional[Path]:
    """Export a Google Doc to PDF."""

    if not drive_service:
        return None

    try:
        # Export as PDF
        pdf_content = drive_service.files().export(
            fileId=doc_id,
            mimeType='application/pdf'
        ).execute()

        # Save to file
        if output_path is None:
            output_path = TMP_DIR / f"proposal_{doc_id}.pdf"

        with open(output_path, 'wb') as f:
            f.write(pdf_content)

        return output_path

    except Exception as e:
        logger.error(f"Failed to export PDF: {e}")
        return None


def upload_pdf_to_drive(pdf_path: Path, drive_service) -> Optional[str]:
    """Upload PDF to Google Drive and return public URL."""

    if not drive_service or not pdf_path.exists():
        return None

    try:
        from googleapiclient.http import MediaFileUpload

        file_metadata = {
            'name': pdf_path.name,
            'mimeType': 'application/pdf'
        }

        media = MediaFileUpload(str(pdf_path), mimetype='application/pdf')

        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,webViewLink'
        ).execute()

        file_id = file.get('id')

        # Make publicly viewable
        drive_service.permissions().create(
            fileId=file_id,
            body={'type': 'anyone', 'role': 'reader'},
            fields='id'
        ).execute()

        return file.get('webViewLink') or f"https://drive.google.com/file/d/{file_id}/view"

    except Exception as e:
        logger.error(f"Failed to upload PDF: {e}")
        return None


def generate_cover_letter(
    job: JobData,
    proposal_doc_url: Optional[str],
    anthropic_client=None,
    mock: bool = False
) -> str:
    """Generate a short cover letter (~35 words) that fits above the fold."""

    if mock:
        if proposal_doc_url:
            return f"Hi. I work with automation workflows daily & just built a lead gen system. Free walkthrough: {proposal_doc_url}"
        return "Hi. I work with automation workflows daily & just built a lead gen system. Happy to walk you through my approach."

    if not anthropic_client:
        import anthropic
        anthropic_client = anthropic.Anthropic()

    skills_str = ', '.join(job.skills[:5]) if job.skills else job.title

    if proposal_doc_url:
        prompt = f"""Generate a short, personalized Upwork cover letter for this job.

JOB DETAILS:
Title: {job.title}
Skills: {skills_str}

COVER LETTER FORMAT (follow EXACTLY - must fit above the fold):
"Hi. I work with [2-4 word paraphrase] daily & just built a [2-5 word thing]. Free walkthrough: [LINK]"

EXAMPLES of good paraphrases:
- "n8n automations" not "n8n workflow automation pipelines"
- "AI agents" not "AI-powered autonomous agent systems"
- "Zapier workflows" not "Zapier integration and automation workflows"

RULES:
- Total must be under 35 words (critical - must stay above the fold)
- [2-4 word paraphrase] = very short description of their need
- [2-5 word thing] = specific relevant thing you built
- End with: Free walkthrough: [LINK]
- No "I'm excited", "I'd love to", or any filler

Return ONLY the cover letter text, nothing else. The [LINK] placeholder will be replaced."""
    else:
        prompt = f"""Generate a short, personalized Upwork cover letter for this job.

JOB DETAILS:
Title: {job.title}
Skills: {skills_str}

FORMAT (follow EXACTLY - must fit above the fold):
"Hi. I work with [2-4 word paraphrase] daily & just built a [2-5 word thing]. Happy to walk you through my approach."

RULES:
- Total must be under 35 words
- No "I'm excited", "I'd love to", or any filler
- End with offer to explain approach

Return ONLY the cover letter text."""

    response = anthropic_client.messages.create(
        model="claude-opus-4-5-20251101",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    for block in response.content:
        if block.type == "text":
            text = block.text.strip()
            if proposal_doc_url:
                text = text.replace('[LINK]', proposal_doc_url)
                text = text.replace('[link]', proposal_doc_url)
            return text

    return ""


async def generate_heygen_video_async(
    job: JobData,
    screenshot_url: Optional[str] = None,
    mock: bool = False
) -> Optional[str]:
    """Generate HeyGen video cover letter."""

    if mock:
        return f"https://heygen.com/videos/mock_{job.job_id}"

    try:
        # Import the HeyGen module
        from upwork_heygen_video import create_heygen_video_async
        from upwork_video_script_generator import generate_video_script_async, analyze_job

        # First generate the video script
        job_dict = {
            'title': job.title,
            'description': job.description,
            'skills': job.skills,
            'budget_type': job.budget_type,
            'budget_min': job.budget_min,
            'budget_max': job.budget_max,
        }

        job_analysis = analyze_job(job_dict)
        script_result = await generate_video_script_async(job_dict, job_analysis)

        if not script_result or not script_result.script_text:
            logger.error("Failed to generate video script")
            return None

        # Generate the video
        result = await create_heygen_video_async(
            script=script_result.script_text,
            job_snapshot_url=screenshot_url
        )

        return result.video_url if result and result.success else None

    except ImportError as e:
        logger.warning(f"HeyGen module not available: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to generate HeyGen video: {e}")
        return None


def generate_deliverables(
    job: JobData,
    generate_doc: bool = True,
    generate_pdf: bool = True,
    generate_video: bool = True,
    screenshot_url: Optional[str] = None,
    mock: bool = False
) -> DeliverableResult:
    """
    Generate all deliverables for a job application.

    Args:
        job: Job data
        generate_doc: Whether to create Google Doc
        generate_pdf: Whether to export PDF
        generate_video: Whether to create HeyGen video
        screenshot_url: URL of job screenshot for video background
        mock: Use mock mode for testing

    Returns:
        DeliverableResult with URLs and content
    """

    result = DeliverableResult(job_id=job.job_id, success=False)

    try:
        # Initialize services
        drive_service, docs_service, _ = get_google_services(mock=mock)

        # Initialize Anthropic client
        anthropic_client = None
        if not mock:
            import anthropic
            anthropic_client = anthropic.Anthropic()

        # Step 1: Generate proposal content
        logger.info(f"Generating proposal for job {job.job_id}: {job.title[:40]}...")
        proposal = generate_proposal_content(job, anthropic_client, mock=mock)
        result.proposal_text = proposal.full_text

        # Step 2: Create Google Doc
        doc_url = None
        if generate_doc and (docs_service or mock):
            logger.info("Creating Google Doc...")
            if mock:
                doc_url = f"https://docs.google.com/document/d/mock_{job.job_id}"
            else:
                doc_url = create_google_doc(
                    title=job.title,
                    content=proposal.full_text,
                    drive_service=drive_service,
                    docs_service=docs_service
                )
            result.proposal_doc_url = doc_url
            logger.info(f"Doc created: {doc_url}")

        # Step 3: Export PDF
        if generate_pdf and doc_url and (drive_service or mock):
            logger.info("Exporting PDF...")
            if mock:
                result.pdf_url = f"https://drive.google.com/file/d/mock_pdf_{job.job_id}/view"
            else:
                # Extract doc ID from URL
                doc_id = doc_url.split('/d/')[1].split('/')[0] if '/d/' in doc_url else None
                if doc_id:
                    pdf_path = export_doc_to_pdf(doc_id, drive_service)
                    if pdf_path:
                        result.pdf_url = upload_pdf_to_drive(pdf_path, drive_service)
                        # Clean up local file
                        pdf_path.unlink(missing_ok=True)
            logger.info(f"PDF created: {result.pdf_url}")

        # Step 4: Generate HeyGen video
        if generate_video:
            logger.info("Generating HeyGen video...")
            video_url = asyncio.run(generate_heygen_video_async(
                job=job,
                screenshot_url=screenshot_url,
                mock=mock
            ))
            result.video_url = video_url
            if video_url:
                logger.info(f"Video created: {video_url}")

        # Step 5: Generate cover letter
        logger.info("Generating cover letter...")
        result.cover_letter = generate_cover_letter(
            job=job,
            proposal_doc_url=doc_url,
            anthropic_client=anthropic_client,
            mock=mock
        )

        result.success = True
        logger.info(f"Deliverables generated successfully for job {job.job_id}")

    except Exception as e:
        logger.error(f"Failed to generate deliverables: {e}")
        result.error = str(e)

    return result


async def generate_deliverables_async(
    job: JobData,
    generate_doc: bool = True,
    generate_pdf: bool = True,
    generate_video: bool = True,
    screenshot_url: Optional[str] = None,
    mock: bool = False
) -> DeliverableResult:
    """Async version of generate_deliverables."""

    # For now, wrap the sync version
    # In production, this would be fully async
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: generate_deliverables(
            job=job,
            generate_doc=generate_doc,
            generate_pdf=generate_pdf,
            generate_video=generate_video,
            screenshot_url=screenshot_url,
            mock=mock
        )
    )


async def generate_deliverables_batch_async(
    jobs: List[Union[JobData, Dict]],
    max_concurrent: int = 3,
    **kwargs
) -> List[DeliverableResult]:
    """Generate deliverables for multiple jobs with concurrency control.

    Args:
        jobs: List of JobData objects or dicts (dicts will be converted to JobData)
        max_concurrent: Maximum concurrent workers
        **kwargs: Additional arguments passed to generate_deliverables_async
    """
    # Convert dicts to JobData if needed
    job_data_list = []
    for job in jobs:
        if isinstance(job, dict):
            job_data_list.append(JobData.from_dict(job))
        else:
            job_data_list.append(job)

    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_with_semaphore(job: JobData) -> DeliverableResult:
        async with semaphore:
            return await generate_deliverables_async(job, **kwargs)

    tasks = [process_with_semaphore(job) for job in job_data_list]
    return await asyncio.gather(*tasks)


def main():
    parser = argparse.ArgumentParser(description="Generate Upwork application deliverables")
    parser.add_argument("--job", "-j", help="JSON file with single job data")
    parser.add_argument("--jobs", help="JSON file with multiple jobs")
    parser.add_argument("--output", "-o", help="Output JSON file")
    parser.add_argument("--parallel", "-p", type=int, default=3, help="Max parallel workers")
    parser.add_argument("--no-doc", action="store_true", help="Skip Google Doc creation")
    parser.add_argument("--no-pdf", action="store_true", help="Skip PDF export")
    parser.add_argument("--no-video", action="store_true", help="Skip HeyGen video")
    parser.add_argument("--mock", action="store_true", help="Mock mode for testing")
    parser.add_argument("--test", action="store_true", help="Run with test data")

    args = parser.parse_args()

    # Handle test mode
    if args.test:
        test_job = JobData(
            job_id="~test123",
            title="Build AI Automation Pipeline",
            description="We need an automation expert to build an AI-powered pipeline for processing customer inquiries. Must have experience with n8n, Claude API, and Zapier.",
            url="https://www.upwork.com/jobs/~test123",
            skills=["n8n", "AI", "Zapier", "Python"],
            budget_type="fixed",
            budget_min=1000,
            budget_max=2000,
            client_country="US",
            client_spent=50000,
            client_hires=25,
            payment_verified=True
        )

        result = generate_deliverables(
            job=test_job,
            generate_doc=not args.no_doc,
            generate_pdf=not args.no_pdf,
            generate_video=not args.no_video,
            mock=args.mock or True  # Always mock in test mode
        )

        print(json.dumps(result.to_dict(), indent=2))
        return

    # Load job(s)
    if args.job:
        with open(args.job) as f:
            job_data = json.load(f)
        jobs = [JobData.from_dict(job_data)]
    elif args.jobs:
        with open(args.jobs) as f:
            jobs_data = json.load(f)
        jobs = [JobData.from_dict(j) for j in jobs_data]
    else:
        print("Error: Must provide --job or --jobs")
        sys.exit(1)

    # Generate deliverables
    if len(jobs) == 1:
        results = [generate_deliverables(
            job=jobs[0],
            generate_doc=not args.no_doc,
            generate_pdf=not args.no_pdf,
            generate_video=not args.no_video,
            mock=args.mock
        )]
    else:
        results = asyncio.run(generate_deliverables_batch_async(
            jobs=jobs,
            max_concurrent=args.parallel,
            generate_doc=not args.no_doc,
            generate_pdf=not args.no_pdf,
            generate_video=not args.no_video,
            mock=args.mock
        ))

    # Output results
    output = [r.to_dict() for r in results]

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(output, f, indent=2)
        print(f"Results saved to {args.output}")
    else:
        print(json.dumps(output, indent=2))

    # Summary
    success_count = sum(1 for r in results if r.success)
    print(f"\nProcessed {len(results)} jobs: {success_count} successful, {len(results) - success_count} failed")


if __name__ == "__main__":
    main()
