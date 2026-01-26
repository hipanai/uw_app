#!/usr/bin/env python3
"""
Upwork Job Template Filler

Generates a job listing image by filling in a template with actual job data.
This avoids needing to capture screenshots from Upwork directly.

Usage:
    python upwork_template_filler.py --job job.json --output filled.png
"""

import os
import json
import argparse
import textwrap
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from PIL import Image, ImageDraw, ImageFont

# Template path
TEMPLATE_PATH = Path(__file__).parent.parent / "assets" / "upwork_job_template.png"

# Font settings - try to use system fonts
def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Get a font, falling back to default if needed."""
    font_names = [
        "arial.ttf",
        "Arial.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
        "calibri.ttf",
        "segoeui.ttf",
        "DejaVuSans.ttf",
    ]

    for font_name in font_names:
        try:
            return ImageFont.truetype(font_name, size)
        except (IOError, OSError):
            continue

    # Fallback to default
    return ImageFont.load_default()


# Colors matching Upwork's design
COLORS = {
    "title": "#001e00",  # Dark green/black for titles
    "text": "#001e00",   # Main text
    "secondary": "#5e6d55",  # Secondary/muted text
    "link": "#14a800",   # Green links
    "light": "#9aaa97",  # Light gray text
}

# Field positions (x, y, width, height) - estimated from template
# These may need fine-tuning based on the actual template
FIELDS = {
    "title": {"x": 227, "y": 78, "w": 580, "h": 30, "font_size": 20, "bold": True},
    "posted_time": {"x": 227, "y": 121, "w": 200, "h": 20, "font_size": 14, "color": "secondary"},
    "location": {"x": 350, "y": 121, "w": 150, "h": 20, "font_size": 14, "color": "secondary"},
    "summary": {"x": 227, "y": 195, "w": 580, "h": 80, "font_size": 14, "multiline": True},

    # Rate/Duration row
    "hourly_rate": {"x": 250, "y": 293, "w": 80, "h": 20, "font_size": 14},
    "duration": {"x": 460, "y": 293, "w": 80, "h": 20, "font_size": 14},
    "experience": {"x": 680, "y": 293, "w": 150, "h": 35, "font_size": 12, "multiline": True},

    # Budget row
    "budget": {"x": 250, "y": 355, "w": 80, "h": 20, "font_size": 14},
    "deadline": {"x": 460, "y": 355, "w": 80, "h": 20, "font_size": 14},

    # Project type
    "project_type": {"x": 295, "y": 427, "w": 100, "h": 20, "font_size": 14},

    # Questions
    "questions": {"x": 227, "y": 495, "w": 580, "h": 25, "font_size": 13},

    # Skills
    "skills": {"x": 227, "y": 600, "w": 200, "h": 25, "font_size": 13},
    "tools": {"x": 227, "y": 655, "w": 200, "h": 25, "font_size": 13},

    # Activity
    "proposals": {"x": 295, "y": 720, "w": 60, "h": 20, "font_size": 13},

    # Right sidebar - About the client
    "client_rating": {"x": 905, "y": 238, "w": 50, "h": 20, "font_size": 14},
    "client_reviews": {"x": 870, "y": 255, "w": 120, "h": 20, "font_size": 12, "color": "secondary"},
    "client_location": {"x": 870, "y": 290, "w": 150, "h": 20, "font_size": 14},
    "client_time": {"x": 870, "y": 308, "w": 150, "h": 20, "font_size": 12, "color": "secondary"},
    "client_jobs": {"x": 870, "y": 342, "w": 150, "h": 20, "font_size": 14},
    "client_hire_rate": {"x": 870, "y": 360, "w": 180, "h": 20, "font_size": 12, "color": "secondary"},
    "client_spent": {"x": 870, "y": 392, "w": 150, "h": 20, "font_size": 14},
    "client_hires": {"x": 870, "y": 410, "w": 180, "h": 20, "font_size": 12, "color": "secondary"},
}


@dataclass
class JobTemplateData:
    """Data to fill into the template."""
    title: str
    summary: str
    posted_time: str = "Posted recently"
    location: str = "Worldwide"

    # Rate/Duration
    hourly_rate: Optional[str] = None
    budget: Optional[str] = None
    duration: Optional[str] = None
    experience: str = "Intermediate"
    deadline: Optional[str] = None
    project_type: str = "One-time"

    # Skills
    skills: List[str] = None
    tools: List[str] = None
    questions: Optional[str] = None

    # Activity
    proposals: str = "5 to 10"

    # Client info
    client_rating: str = "5.0"
    client_reviews: str = "5.00 of 21 reviews"
    client_location: str = "United States"
    client_time: str = ""
    client_jobs: str = "10 jobs posted"
    client_hire_rate: str = "90% hire rate"
    client_spent: str = "$10K+ total spent"
    client_hires: str = "15 hires"

    def __post_init__(self):
        if self.skills is None:
            self.skills = []
        if self.tools is None:
            self.tools = []


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    """Wrap text to fit within max_width pixels."""
    words = text.split()
    lines = []
    current_line = []

    for word in words:
        test_line = ' '.join(current_line + [word])
        bbox = font.getbbox(test_line)
        width = bbox[2] - bbox[0]

        if width <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]

    if current_line:
        lines.append(' '.join(current_line))

    return lines


def fill_template(
    data: JobTemplateData,
    template_path: str = None,
    output_path: str = None
) -> Image.Image:
    """
    Fill the Upwork job template with job data.

    Args:
        data: JobTemplateData with field values
        template_path: Path to template image (uses default if None)
        output_path: If provided, saves the image to this path

    Returns:
        PIL Image with filled template
    """
    # Load template
    template = template_path or TEMPLATE_PATH
    img = Image.open(template).convert("RGBA")
    draw = ImageDraw.Draw(img)

    # Fill each field
    field_data = {
        "title": data.title,
        "posted_time": data.posted_time,
        "location": data.location,
        "summary": data.summary,
        "hourly_rate": data.hourly_rate or "",
        "duration": data.duration or "",
        "experience": data.experience,
        "budget": data.budget or "",
        "deadline": data.deadline or "",
        "project_type": data.project_type,
        "questions": data.questions or "",
        "skills": ", ".join(data.skills) if data.skills else "",
        "tools": ", ".join(data.tools) if data.tools else "",
        "proposals": data.proposals,
        "client_rating": data.client_rating,
        "client_reviews": data.client_reviews,
        "client_location": data.client_location,
        "client_time": data.client_time,
        "client_jobs": data.client_jobs,
        "client_hire_rate": data.client_hire_rate,
        "client_spent": data.client_spent,
        "client_hires": data.client_hires,
    }

    for field_name, value in field_data.items():
        if not value or field_name not in FIELDS:
            continue

        field = FIELDS[field_name]
        x, y = field["x"], field["y"]
        w = field.get("w", 200)
        font_size = field.get("font_size", 14)
        bold = field.get("bold", False)
        color_key = field.get("color", "text")
        color = COLORS.get(color_key, COLORS["text"])
        multiline = field.get("multiline", False)

        font = get_font(font_size, bold)

        if multiline:
            lines = wrap_text(value, font, w)
            line_height = font_size + 4
            for i, line in enumerate(lines[:4]):  # Max 4 lines
                draw.text((x, y + i * line_height), line, fill=color, font=font)
        else:
            # Truncate if too long
            while font.getbbox(value)[2] > w and len(value) > 10:
                value = value[:-4] + "..."
            draw.text((x, y), value, fill=color, font=font)

    # Save if output path provided
    if output_path:
        # Ensure directory exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path)

    return img


def create_job_image(
    job_data: Dict[str, Any],
    output_path: str = None
) -> str:
    """
    Create a job listing image from job data dictionary.

    Args:
        job_data: Dictionary with job information
        output_path: Where to save the image (auto-generated if None)

    Returns:
        Path to the saved image
    """
    # Extract and format data
    budget_str = ""
    if job_data.get("budget_type") == "fixed":
        if job_data.get("budget_min") and job_data.get("budget_max"):
            budget_str = f"${job_data['budget_min']}-${job_data['budget_max']}"
        elif job_data.get("budget_min"):
            budget_str = f"${job_data['budget_min']}+"
        elif job_data.get("budget_max"):
            budget_str = f"Up to ${job_data['budget_max']}"

    hourly_str = ""
    if job_data.get("budget_type") == "hourly":
        if job_data.get("budget_min") and job_data.get("budget_max"):
            hourly_str = f"${job_data['budget_min']}-${job_data['budget_max']}/hr"
        elif job_data.get("budget_min"):
            hourly_str = f"${job_data['budget_min']}+/hr"

    # Client spending
    client_spent = job_data.get("client_spent", 0)
    if client_spent:
        if client_spent >= 1000000:
            spent_str = f"${client_spent/1000000:.1f}M total spent"
        elif client_spent >= 1000:
            spent_str = f"${client_spent/1000:.0f}K total spent"
        else:
            spent_str = f"${client_spent:.0f} total spent"
    else:
        spent_str = "New client"

    # Client hires
    hires = job_data.get("client_hires", 0)
    hires_str = f"{hires} hires" if hires else "No hires yet"

    # Create template data
    template_data = JobTemplateData(
        title=job_data.get("title", "Job Title"),
        summary=job_data.get("description", "")[:500],  # Truncate long descriptions
        posted_time="Posted recently",
        location=job_data.get("client_country", "Worldwide"),
        hourly_rate=hourly_str,
        budget=budget_str,
        duration=job_data.get("duration", ""),
        experience=job_data.get("experience_level", "Intermediate"),
        project_type=job_data.get("project_type", "One-time project"),
        skills=job_data.get("skills", [])[:6],  # Max 6 skills
        tools=[],
        proposals=job_data.get("proposals_count", "5 to 10"),
        client_rating="5.0",
        client_reviews=f"5.0 of {job_data.get('client_reviews', 10)} reviews",
        client_location=job_data.get("client_country", "United States"),
        client_jobs=f"{job_data.get('client_jobs_posted', 10)} jobs posted",
        client_hire_rate=f"{job_data.get('client_hire_rate', 90)}% hire rate",
        client_spent=spent_str,
        client_hires=hires_str,
    )

    # Generate output path if not provided
    if not output_path:
        job_id = job_data.get("job_id", "unknown")
        output_dir = Path(".tmp/job_images")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f"job_{job_id}.png")

    # Fill template
    fill_template(template_data, output_path=output_path)

    return output_path


def main():
    parser = argparse.ArgumentParser(description="Fill Upwork job template with data")
    parser.add_argument("--job", "-j", help="JSON file with job data")
    parser.add_argument("--output", "-o", default="filled_template.png", help="Output image path")
    parser.add_argument("--title", "-t", help="Job title")
    parser.add_argument("--summary", "-s", help="Job summary/description")
    parser.add_argument("--test", action="store_true", help="Run with test data")

    args = parser.parse_args()

    if args.test:
        # Test with sample data
        test_data = {
            "job_id": "test123",
            "title": "n8n Automation Expert for Lead Generation Pipeline",
            "description": "We need an experienced n8n developer to build an automated lead generation pipeline. Requirements include scraping leads from multiple sources, enriching with email addresses, and pushing to our CRM.",
            "budget_type": "fixed",
            "budget_min": 500,
            "budget_max": 1000,
            "skills": ["n8n", "Automation", "API Integration", "Web Scraping", "CRM"],
            "client_country": "United States",
            "client_spent": 35000,
            "client_hires": 28,
        }

        output_path = create_job_image(test_data, args.output)
        print(f"Test image created: {output_path}")

    elif args.job:
        with open(args.job) as f:
            job_data = json.load(f)
        output_path = create_job_image(job_data, args.output)
        print(f"Image created: {output_path}")

    elif args.title and args.summary:
        data = JobTemplateData(title=args.title, summary=args.summary)
        fill_template(data, output_path=args.output)
        print(f"Image created: {args.output}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
