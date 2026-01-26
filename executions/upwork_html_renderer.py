#!/usr/bin/env python3
"""
Upwork HTML Template Renderer

Renders job data and proposals into HTML templates and captures as images.
Supports two views:
1. Job listing view - shows job details with Upwork header
2. Proposal view - shows the generated proposal

Usage:
    python upwork_html_renderer.py --job job.json --output background.png
    python upwork_html_renderer.py --test
"""

import os
import re
import json
import asyncio
import argparse
import tempfile
import html
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Template paths
ASSETS_DIR = Path(__file__).parent.parent / "assets"
JOB_TEMPLATE_PATH = ASSETS_DIR / "job_template.html"
PROPOSAL_TEMPLATE_PATH = ASSETS_DIR / "proposal_template.html"

# Video settings
VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720
ANIMATION_DURATION_MS = 2000  # Time for animations to complete


@dataclass
class RenderResult:
    """Result of HTML rendering."""
    success: bool
    video_path: Optional[str] = None
    screenshot_path: Optional[str] = None
    job_screenshot_path: Optional[str] = None
    proposal_screenshot_path: Optional[str] = None
    error: Optional[str] = None


def format_budget(job_data: Dict[str, Any]) -> str:
    """Format budget from job data."""
    budget_type = job_data.get("budget_type", "")
    budget_min = job_data.get("budget_min")
    budget_max = job_data.get("budget_max")

    if budget_type == "hourly":
        if budget_min and budget_max:
            return f"${budget_min}-${budget_max}/hr"
        elif budget_min:
            return f"${budget_min}+/hr"
        elif budget_max:
            return f"Up to ${budget_max}/hr"
        return "Hourly"
    elif budget_type == "fixed":
        if budget_min and budget_max:
            return f"${budget_min:,.0f}-${budget_max:,.0f} Fixed"
        elif budget_min:
            return f"${budget_min:,.0f}+ Fixed"
        elif budget_max:
            return f"Up to ${budget_max:,.0f} Fixed"
        return "Fixed Price"
    return "Not specified"


def format_client_spent(spent: float) -> str:
    """Format client total spent."""
    if not spent:
        return "New client"
    if spent >= 1000000:
        return f"${spent/1000000:.1f}M+"
    elif spent >= 1000:
        return f"${spent/1000:.0f}K+"
    return f"${spent:.0f}"


def generate_skills_tags(skills: List[str]) -> str:
    """Generate HTML for skill tags."""
    if not skills:
        return '<span class="skill-tag">Not specified</span>'

    tags = []
    for skill in skills[:8]:  # Max 8 skills
        escaped_skill = html.escape(str(skill))
        tags.append(f'<span class="skill-tag">{escaped_skill}</span>')

    return '\n'.join(tags)


def parse_proposal(proposal_text: str) -> Dict[str, Any]:
    """
    Parse proposal text into structured sections.

    Returns:
        Dict with 'intro', 'approach_steps', 'deliverables', 'timeline'
    """
    if not proposal_text:
        return {
            'intro': '',
            'approach_steps': [],
            'deliverables': [],
            'timeline': 'TBD'
        }

    result = {
        'intro': '',
        'approach_steps': [],
        'deliverables': [],
        'timeline': 'TBD'
    }

    # Extract intro (everything before "My proposed approach")
    intro_match = re.search(r'^(.*?)(?:My proposed approach)', proposal_text, re.DOTALL | re.IGNORECASE)
    if intro_match:
        result['intro'] = intro_match.group(1).strip()

    # Extract approach steps (numbered items) - look after "My proposed approach"
    approach_section = proposal_text
    approach_start = re.search(r'My proposed approach', proposal_text, re.IGNORECASE)
    if approach_start:
        approach_section = proposal_text[approach_start.end():]

    # Match numbered steps - each step ends before the next number or section header
    steps = re.findall(
        r'(\d+)\.\s+(.+?)(?=(?:\n\s*\d+\.)|What you\'ll get|Deliverables|Timeline|$)',
        approach_section,
        re.DOTALL | re.IGNORECASE
    )
    result['approach_steps'] = [(num, text.strip()) for num, text in steps if text.strip()]

    # Extract deliverables (bullet points after "What you'll get" or "Deliverables")
    deliv_match = re.search(r'(?:What you\'ll get|Deliverables)[:\s]*(.*?)(?:Timeline|$)',
                            proposal_text, re.DOTALL | re.IGNORECASE)
    if deliv_match:
        deliv_text = deliv_match.group(1)
        # Find bullet items
        bullets = re.findall(r'[-•*]\s*(.+?)(?=[-•*]|\n\n|$)', deliv_text, re.DOTALL)
        if bullets:
            result['deliverables'] = [b.strip() for b in bullets if b.strip()]
        else:
            # Just use the whole section if no bullets
            clean_text = deliv_text.strip()
            if clean_text:
                result['deliverables'] = [clean_text]

    # Extract timeline
    timeline_match = re.search(r'Timeline[:\s]*(.*?)$', proposal_text, re.DOTALL | re.IGNORECASE)
    if timeline_match:
        timeline_text = timeline_match.group(1).strip()
        # Extract just the time estimate
        time_match = re.search(r'(\d+[-–]\d+\s*(?:days?|weeks?|months?))', timeline_text, re.IGNORECASE)
        if time_match:
            result['timeline'] = time_match.group(1)
        else:
            # Use first sentence or line
            first_line = timeline_text.split('\n')[0].strip()[:50]
            if first_line:
                result['timeline'] = first_line

    return result


def generate_job_html(job_data: Dict[str, Any]) -> str:
    """Generate HTML for job listing view."""
    with open(JOB_TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # Prepare field values (escape HTML to prevent injection)
    title = html.escape(job_data.get("title", "Job Title")[:80])
    summary = html.escape(job_data.get("description", "")[:500])
    budget = html.escape(format_budget(job_data))
    duration = html.escape(job_data.get("duration", "Not specified"))
    experience = html.escape(job_data.get("experience_level", "Intermediate"))
    project_type = html.escape(job_data.get("project_type", "One-time project"))

    skills = job_data.get("skills", [])
    if isinstance(skills, str):
        skills = [s.strip() for s in skills.split(',') if s.strip()]
    skills_tags = generate_skills_tags(skills)

    client_location = html.escape(job_data.get("client_country", "United States"))
    payment_verified = "Verified" if job_data.get("payment_verified", True) else "Not verified"
    client_spent = format_client_spent(job_data.get("client_spent", 0))
    client_hires = f"{job_data.get('client_hires', 0)} hires"

    # Replace placeholders
    replacements = {
        "{{TITLE}}": title,
        "{{SUMMARY}}": summary,
        "{{BUDGET}}": budget,
        "{{DURATION}}": duration,
        "{{EXPERIENCE}}": experience,
        "{{PROJECT_TYPE}}": project_type,
        "{{SKILLS_TAGS}}": skills_tags,
        "{{SKILLS}}": ", ".join(skills[:8]) if skills else "Not specified",
        "{{CLIENT_LOCATION}}": client_location,
        "{{PAYMENT_VERIFIED}}": payment_verified,
        "{{CLIENT_SPENT}}": client_spent,
        "{{CLIENT_HIRES}}": client_hires,
    }

    for placeholder, value in replacements.items():
        html_content = html_content.replace(placeholder, value)

    return html_content


def generate_proposal_html(job_data: Dict[str, Any], proposal_text: str) -> str:
    """Generate HTML for proposal view."""
    with open(PROPOSAL_TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # Parse proposal
    parsed = parse_proposal(proposal_text)

    # Generate approach steps HTML
    steps_html = ""
    for num, text in parsed['approach_steps'][:5]:  # Max 5 steps to fit
        escaped_text = html.escape(text[:150])  # Truncate long steps
        steps_html += f'''
          <div class="step">
            <div class="step-number">{num}</div>
            <div class="step-text">{escaped_text}</div>
          </div>
        '''

    # Generate deliverables HTML
    deliverables_html = ""
    for item in parsed['deliverables'][:4]:  # Max 4 deliverables
        escaped_item = html.escape(item[:60])
        deliverables_html += f'<div class="deliverable-item">{escaped_item}</div>\n'

    # Prepare values
    title = html.escape(job_data.get("title", "Job Title")[:60])
    intro = html.escape(parsed['intro'][:300]) if parsed['intro'] else "Here's my proposed approach for your project."
    timeline = html.escape(parsed['timeline'])

    # Replace placeholders
    replacements = {
        "{{TITLE}}": title,
        "{{INTRO}}": intro,
        "{{APPROACH_STEPS}}": steps_html,
        "{{DELIVERABLES}}": deliverables_html,
        "{{TIMELINE}}": timeline,
    }

    for placeholder, value in replacements.items():
        html_content = html_content.replace(placeholder, value)

    return html_content


async def render_html_to_image(
    html_content: str,
    output_path: str,
    wait_ms: int = ANIMATION_DURATION_MS
) -> bool:
    """Render HTML content to an image using Playwright."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("Playwright not installed")
        return False

    # Create temp file for HTML
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
        f.write(html_content)
        html_path = f.name

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": VIDEO_WIDTH, "height": VIDEO_HEIGHT}
            )
            page = await context.new_page()

            # Navigate to HTML file
            await page.goto(f"file:///{html_path.replace(os.sep, '/')}")

            # Wait for animations
            await page.wait_for_timeout(wait_ms)

            # Capture screenshot
            await page.screenshot(path=output_path)

            await context.close()
            await browser.close()

        return True

    except Exception as e:
        logger.error(f"Rendering failed: {e}")
        return False

    finally:
        try:
            os.unlink(html_path)
        except:
            pass


async def render_job_and_proposal(
    job_data: Dict[str, Any],
    proposal_text: str = None,
    output_path: str = None
) -> RenderResult:
    """
    Render both job listing and proposal views.

    Args:
        job_data: Dictionary with job information
        proposal_text: Generated proposal text
        output_path: Base path for output files (without extension)

    Returns:
        RenderResult with paths to both screenshots
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return RenderResult(
            success=False,
            error="Playwright not installed. Run: pip install playwright && playwright install chromium"
        )

    # Setup output paths
    job_id = job_data.get("job_id", "unknown")
    if not output_path:
        output_dir = Path(".tmp/rendered_jobs")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f"job_{job_id}")

    job_screenshot_path = f"{output_path}_job.png"
    proposal_screenshot_path = f"{output_path}_proposal.png" if proposal_text else None

    try:
        # Generate and render job HTML
        job_html = generate_job_html(job_data)
        success = await render_html_to_image(job_html, job_screenshot_path)

        if not success:
            return RenderResult(success=False, error="Failed to render job listing")

        logger.info(f"Job screenshot saved: {job_screenshot_path}")

        # Generate and render proposal HTML if provided
        if proposal_text:
            proposal_html = generate_proposal_html(job_data, proposal_text)
            success = await render_html_to_image(proposal_html, proposal_screenshot_path)

            if success:
                logger.info(f"Proposal screenshot saved: {proposal_screenshot_path}")
            else:
                logger.warning("Failed to render proposal, continuing with job only")
                proposal_screenshot_path = None

        return RenderResult(
            success=True,
            screenshot_path=job_screenshot_path,  # For backward compatibility
            job_screenshot_path=job_screenshot_path,
            proposal_screenshot_path=proposal_screenshot_path
        )

    except Exception as e:
        logger.error(f"Rendering failed: {e}")
        return RenderResult(success=False, error=str(e))


async def render_job_video(
    job_data: Dict[str, Any],
    output_path: str = None,
    capture_screenshot: bool = True,
    record_video: bool = True,
    hold_duration_ms: int = 3000
) -> RenderResult:
    """
    Render job data as HTML and record as video.

    Args:
        job_data: Dictionary with job information
        output_path: Base path for output files (without extension)
        capture_screenshot: Whether to save a screenshot
        record_video: Whether to record video
        hold_duration_ms: How long to hold the final frame

    Returns:
        RenderResult with paths to generated files
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return RenderResult(
            success=False,
            error="Playwright not installed. Run: pip install playwright && playwright install chromium"
        )

    # Generate HTML
    html_content = generate_job_html(job_data)

    # Create temp file for HTML
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
        f.write(html_content)
        html_path = f.name

    # Setup output paths
    job_id = job_data.get("job_id", "unknown")
    if not output_path:
        output_dir = Path(".tmp/rendered_jobs")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f"job_{job_id}")

    video_path = f"{output_path}.webm" if record_video else None
    screenshot_path = f"{output_path}.png" if capture_screenshot else None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            context_options = {
                "viewport": {"width": VIDEO_WIDTH, "height": VIDEO_HEIGHT},
            }

            if record_video:
                video_dir = Path(output_path).parent / "video_tmp"
                video_dir.mkdir(parents=True, exist_ok=True)
                context_options["record_video_dir"] = str(video_dir)
                context_options["record_video_size"] = {
                    "width": VIDEO_WIDTH,
                    "height": VIDEO_HEIGHT
                }

            context = await browser.new_context(**context_options)
            page = await context.new_page()

            await page.goto(f"file:///{html_path.replace(os.sep, '/')}")
            await page.wait_for_timeout(ANIMATION_DURATION_MS)

            if capture_screenshot:
                await page.screenshot(path=screenshot_path)
                logger.info(f"Screenshot saved: {screenshot_path}")

            if record_video:
                await page.wait_for_timeout(hold_duration_ms)

            await context.close()
            await browser.close()

            if record_video:
                import shutil
                video_files = list(video_dir.glob("*.webm"))
                if video_files:
                    shutil.move(str(video_files[0]), video_path)
                    logger.info(f"Video saved: {video_path}")
                    shutil.rmtree(video_dir, ignore_errors=True)
                else:
                    video_path = None

        return RenderResult(
            success=True,
            video_path=video_path,
            screenshot_path=screenshot_path,
            job_screenshot_path=screenshot_path
        )

    except Exception as e:
        logger.error(f"Rendering failed: {e}")
        return RenderResult(success=False, error=str(e))

    finally:
        try:
            os.unlink(html_path)
        except:
            pass


def render_job_video_sync(job_data: Dict[str, Any], output_path: str = None, **kwargs) -> RenderResult:
    """Synchronous wrapper for render_job_video."""
    return asyncio.run(render_job_video(job_data, output_path, **kwargs))


async def render_job_screenshot(job_data: Dict[str, Any], output_path: str = None) -> RenderResult:
    """Render job data as HTML and capture screenshot only (faster than video)."""
    return await render_job_video(
        job_data,
        output_path=output_path,
        capture_screenshot=True,
        record_video=False
    )


def render_job_screenshot_sync(job_data: Dict[str, Any], output_path: str = None) -> RenderResult:
    """Synchronous wrapper for render_job_screenshot."""
    return asyncio.run(render_job_screenshot(job_data, output_path))


def render_both_views_sync(
    job_data: Dict[str, Any],
    proposal_text: str = None,
    output_path: str = None
) -> RenderResult:
    """Synchronous wrapper for render_job_and_proposal."""
    return asyncio.run(render_job_and_proposal(job_data, proposal_text, output_path))


def main():
    parser = argparse.ArgumentParser(description="Render Upwork job as HTML")
    parser.add_argument("--job", "-j", help="JSON file with job data")
    parser.add_argument("--proposal", "-p", help="Proposal text file")
    parser.add_argument("--output", "-o", help="Output path (without extension)")
    parser.add_argument("--both", "-b", action="store_true", help="Render both job and proposal views")
    parser.add_argument("--test", action="store_true", help="Run with test data")

    args = parser.parse_args()

    if args.test:
        test_job = {
            "job_id": "html_test",
            "title": "n8n Automation Expert for Lead Generation Pipeline",
            "description": """We need an experienced n8n developer to build an automated lead generation pipeline.

Requirements:
- Scrape leads from multiple sources (LinkedIn, Google Maps, websites)
- Enrich leads with email addresses and company info
- Push qualified leads to our CRM (HubSpot)
- Set up automated email sequences via Instantly
- Create dashboard for tracking pipeline metrics

The ideal candidate has experience with API integrations, data processing, and workflow automation.""",
            "budget_type": "fixed",
            "budget_min": 500,
            "budget_max": 1000,
            "skills": ["n8n", "Automation", "API Integration", "Web Scraping", "CRM", "HubSpot"],
            "client_country": "United States",
            "client_spent": 35000,
            "client_hires": 28,
            "payment_verified": True,
            "experience_level": "Intermediate",
            "project_type": "One-time project",
            "duration": "1-3 months",
        }

        test_proposal = """Hey.

I spent ~15 minutes putting this together for you. In short, it's how I would create your automated lead gen pipeline end to end.

I've worked with $MM companies like Anthropic and I have a lot of experience designing/building similar workflows.

My proposed approach

1. Set up n8n as the central orchestration hub - it's perfect for this because it handles complex multi-step workflows with excellent error handling.

2. Build scrapers for each data source (LinkedIn via Sales Navigator API, Google Maps via Places API, website contacts via custom scraping).

3. Create a data enrichment pipeline using tools like Hunter.io and Clearbit for email verification and company data.

4. Implement HubSpot integration with custom properties to track lead sources and qualification scores.

5. Set up Instantly campaigns with automated sequences based on lead segments.

What you'll get

- Complete n8n workflow with documentation
- HubSpot integration configured
- Instantly email sequences ready to go
- Training session on managing the pipeline

Timeline

I can have this running within 10-14 days, with the first leads flowing within week one."""

        result = render_both_views_sync(test_job, test_proposal, args.output)

        if result.success:
            print("Rendering complete!")
            if result.job_screenshot_path:
                print(f"  Job screenshot: {result.job_screenshot_path}")
            if result.proposal_screenshot_path:
                print(f"  Proposal screenshot: {result.proposal_screenshot_path}")
        else:
            print(f"Rendering failed: {result.error}")

    elif args.job:
        with open(args.job) as f:
            job_data = json.load(f)

        proposal_text = None
        if args.proposal:
            with open(args.proposal) as f:
                proposal_text = f.read()

        if args.both or proposal_text:
            result = render_both_views_sync(job_data, proposal_text, args.output)
        else:
            result = render_job_screenshot_sync(job_data, args.output)

        if result.success:
            print("Rendering complete!")
            if result.job_screenshot_path:
                print(f"  Job screenshot: {result.job_screenshot_path}")
            if result.proposal_screenshot_path:
                print(f"  Proposal screenshot: {result.proposal_screenshot_path}")
        else:
            print(f"Rendering failed: {result.error}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
