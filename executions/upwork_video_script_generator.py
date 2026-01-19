#!/usr/bin/env python3
"""
Upwork Video Script Generator

Generates video cover letter scripts for HeyGen video generation.
Uses Opus 4.5 with extended thinking for high-quality, personalized scripts.

The script follows the template structure:
1. Opening (10-15 sec): Reference job details + relevant results
2. Experience (20-30 sec): 1-2 portfolio examples matching requirements
3. Approach (15-20 sec): How you'd tackle the project with specific tools
4. Closing (10-15 sec): Invite to call, state availability, sign off

Usage:
    python executions/upwork_video_script_generator.py --job job.json --output script.txt
    python executions/upwork_video_script_generator.py --test
"""

import os
import re
import json
import argparse
import asyncio
from typing import Optional
from dataclasses import dataclass, asdict
from dotenv import load_dotenv

load_dotenv()

# Profile information for video scripts
PROFILE = {
    "name": "Clyde",
    "experience_years_ai": 4,
    "experience_years_automation": "many more",
    "tools": [
        "Zapier", "Make.com", "Airtable", "n8n",
        "ChatGPT/OpenAI", "Claude API", "Instantly", "Apollo.io"
    ],
    "availability": "12 noon - 6pm Eastern US time",
    "portfolio_areas": [
        "AI video generation",
        "Automated email outreach",
        "AI voice and chat assistants/chatbots",
        "Automated lead generation",
        "Social media content automation",
        "Data scraping and management",
        "Invoice and proposal automation",
        "Data analysis and visualization"
    ]
}

# Target word counts
MIN_WORDS = 200
MAX_WORDS = 250


@dataclass
class JobAnalysis:
    """Extracted analysis from a job posting."""
    requirements: list[str]
    goals: list[str]
    skills: list[str]
    industry: Optional[str] = None
    budget: Optional[str] = None
    timeline: Optional[str] = None


@dataclass
class VideoScript:
    """Generated video script with metadata."""
    script_text: str
    word_count: int
    has_opening: bool
    has_experience: bool
    has_approach: bool
    has_closing: bool
    mentions_industry: bool
    has_emojis: bool

    def to_dict(self) -> dict:
        return asdict(self)


def count_words(text: str) -> int:
    """Count words in text."""
    return len(text.split())


def has_emojis(text: str) -> bool:
    """Check if text contains emoji characters."""
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U00002702-\U000027B0"  # dingbats
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE
    )
    return bool(emoji_pattern.search(text))


def analyze_job(job: dict) -> JobAnalysis:
    """Extract analysis from job data."""
    # Get description and title
    description = job.get('description', '')
    title = job.get('title', '')

    # Extract skills - handle both list and string formats
    skills = job.get('skills', [])
    if isinstance(skills, str):
        skills = [s.strip() for s in skills.split(',')]

    # Detect industry from description/title
    industry = job.get('industry')
    if not industry:
        # Try to detect from common industry keywords
        industry_keywords = {
            'healthcare': ['healthcare', 'medical', 'hospital', 'clinic', 'patient', 'health'],
            'ecommerce': ['ecommerce', 'e-commerce', 'shopify', 'online store', 'retail'],
            'fintech': ['fintech', 'banking', 'finance', 'payment', 'financial'],
            'saas': ['saas', 'software as a service', 'subscription'],
            'real estate': ['real estate', 'property', 'realtor', 'realty'],
            'legal': ['legal', 'law firm', 'attorney', 'lawyer'],
            'education': ['education', 'learning', 'course', 'training', 'edtech'],
            'marketing': ['marketing agency', 'digital marketing', 'ad agency'],
        }
        text_lower = (description + ' ' + title).lower()
        for ind, keywords in industry_keywords.items():
            if any(kw in text_lower for kw in keywords):
                industry = ind
                break

    # Extract requirements (look for bullet points or numbered items)
    requirements = []
    for line in description.split('\n'):
        line = line.strip()
        if line.startswith(('-', '*', '•')) or re.match(r'^\d+\.', line):
            clean = re.sub(r'^[-*•\d.)\s]+', '', line).strip()
            if clean and len(clean) > 10:
                requirements.append(clean)

    # If no bullet points found, use title + skills as requirements
    if not requirements:
        requirements = [title] + skills[:3]

    # Extract goals (usually in the description)
    goals = []
    goal_indicators = ['looking for', 'need', 'want', 'goal', 'objective', 'seeking']
    for sentence in description.split('.'):
        sentence = sentence.strip()
        if any(ind in sentence.lower() for ind in goal_indicators):
            if 10 < len(sentence) < 200:
                goals.append(sentence)

    if not goals:
        goals = [f"Complete {title.lower()} project successfully"]

    return JobAnalysis(
        requirements=requirements[:5],  # Limit to 5
        goals=goals[:3],  # Limit to 3
        skills=skills[:8],  # Limit to 8
        industry=industry,
        budget=job.get('budget'),
        timeline=job.get('timeline')
    )


def generate_video_script(
    job: dict,
    job_analysis: Optional[JobAnalysis] = None,
    anthropic_client=None,
    mock: bool = False
) -> VideoScript:
    """
    Generate HeyGen video script based on job analysis.

    Args:
        job: Job data dictionary
        job_analysis: Pre-computed job analysis (optional, will compute if not provided)
        anthropic_client: Anthropic client (will create if not provided)
        mock: If True, return a mock script without calling API

    Returns:
        VideoScript with script text and metadata
    """
    if job_analysis is None:
        job_analysis = analyze_job(job)

    if mock:
        # Return mock script for testing
        mock_script = f"""Hi there! I noticed you're looking for help with {job.get('title', 'your project')}, and I'm excited to share how I can help.

In my experience building AI automation systems, I've delivered similar solutions for Fortune 500 companies. For example, I recently built an automated lead generation system that increased conversion rates by 40% using n8n and the Claude API.

For your project, I would approach this by first understanding your current workflow, then designing a custom automation using tools like Make.com and Airtable. This ensures we build something that integrates seamlessly with your existing systems.

I'd love to discuss your specific needs in more detail. Would you be available for a quick 10-minute call? I'm typically available from 12 noon to 6pm Eastern. Looking forward to connecting!

Best regards,
Clyde"""
        return VideoScript(
            script_text=mock_script,
            word_count=count_words(mock_script),
            has_opening=True,
            has_experience=True,
            has_approach=True,
            has_closing=True,
            mentions_industry=job_analysis.industry is not None,
            has_emojis=False
        )

    # Initialize client if not provided
    if anthropic_client is None:
        import anthropic
        anthropic_client = anthropic.Anthropic()

    # Build the prompt
    industry_instruction = ""
    if job_analysis.industry:
        industry_instruction = f"- Industry: {job_analysis.industry} (mention this in your script)"
    else:
        industry_instruction = "- Industry: Not specified (do NOT mention any specific industry)"

    tools_str = ", ".join(PROFILE["tools"])
    portfolio_str = ", ".join(PROFILE["portfolio_areas"])
    requirements_str = "\n".join(f"  - {r}" for r in job_analysis.requirements)
    goals_str = "\n".join(f"  - {g}" for g in job_analysis.goals)
    skills_str = ", ".join(job_analysis.skills) if job_analysis.skills else "Not specified"

    prompt = f"""Generate a 60-90 second video cover letter script for this Upwork job.

JOB ANALYSIS:
- Title: {job.get('title', 'Unknown')}
- Core requirements:
{requirements_str}
- Project goals:
{goals_str}
- Skills mentioned: {skills_str}
{industry_instruction}
- Budget: {job_analysis.budget or 'Not specified'}

PROFILE (speak as this person):
- Name: {PROFILE['name']}
- Experience: ~{PROFILE['experience_years_ai']} years AI, {PROFILE['experience_years_automation']} with automation
- Tools: {tools_str}
- Availability: {PROFILE['availability']}
- Portfolio areas: {portfolio_str}

SCRIPT STRUCTURE (follow this EXACTLY):

1. OPENING (10-15 seconds):
   - Reference their SPECIFIC needs from the job posting
   - Show you understand what they're trying to achieve
   - Include a quantitative result from your experience that mirrors their needs

2. RELEVANT EXPERIENCE (20-30 seconds):
   - Share 1-2 SPECIFIC portfolio examples that directly address their requirements
   - Focus on results and outcomes achieved (use numbers if possible)
   - Only mention portfolio items that genuinely match their needs

3. APPROACH (15-20 seconds):
   - Explain HOW you would approach their project
   - Mention relevant tools you'd use (Zapier, Make.com, n8n, OpenAI, etc.)
   - Keep it practical and specific to their use case

4. CLOSING (10-15 seconds):
   - Invite them to a 10-minute call to discuss further
   - State your availability ({PROFILE['availability']})
   - Sign off warmly as {PROFILE['name']}

CRITICAL RULES:
- {MIN_WORDS}-{MAX_WORDS} words MAXIMUM (this is non-negotiable)
- Professional but conversational tone (like talking to a colleague)
- ABSOLUTELY NO emojis or icons
- First 2 sentences must be the MOST impactful - grab attention immediately
- Only mention industry if the job posting specifies one
- Only include 1-2 portfolio highlights that are MOST closely related
- NO time estimates for project completion
- Use keywords from the job posting naturally throughout
- The script will be read aloud, so use natural speech patterns

Return ONLY the script text, ready to be spoken. No headers, no formatting markers, just the words."""

    # Call Opus 4.5 with extended thinking
    response = anthropic_client.messages.create(
        model="claude-opus-4-5-20251101",
        max_tokens=1500,
        thinking={
            "type": "enabled",
            "budget_tokens": 3000
        },
        messages=[{"role": "user", "content": prompt}]
    )

    # Extract text from response (skip thinking blocks)
    script_text = ""
    for block in response.content:
        if block.type == "text":
            script_text = block.text.strip()
            break

    # Validate and create VideoScript
    word_count = count_words(script_text)
    script_lower = script_text.lower()

    # Check for section indicators
    has_opening = any(phrase in script_lower for phrase in [
        "looking for", "noticed", "i see", "your project", "hi", "hello"
    ])
    has_experience = any(phrase in script_lower for phrase in [
        "built", "created", "delivered", "experience", "worked on", "portfolio"
    ])
    has_approach = any(phrase in script_lower for phrase in [
        "would", "approach", "using", "implement", "my plan", "i'd"
    ])
    has_closing = any(phrase in script_lower for phrase in [
        "call", "discuss", "available", "connect", "looking forward",
        PROFILE['name'].lower(), "regards"
    ])

    # Check if industry is mentioned (only valid if job has industry)
    mentions_industry = False
    if job_analysis.industry:
        mentions_industry = job_analysis.industry.lower() in script_lower

    return VideoScript(
        script_text=script_text,
        word_count=word_count,
        has_opening=has_opening,
        has_experience=has_experience,
        has_approach=has_approach,
        has_closing=has_closing,
        mentions_industry=mentions_industry,
        has_emojis=has_emojis(script_text)
    )


async def generate_video_script_async(
    job: dict,
    job_analysis: Optional[JobAnalysis] = None,
    anthropic_client=None,
    mock: bool = False
) -> VideoScript:
    """Async wrapper for generate_video_script."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        generate_video_script,
        job,
        job_analysis,
        anthropic_client,
        mock
    )


async def generate_scripts_batch_async(
    jobs: list[dict],
    anthropic_client=None,
    max_concurrent: int = 3,
    mock: bool = False
) -> list[VideoScript]:
    """
    Generate video scripts for multiple jobs in parallel.

    Args:
        jobs: List of job dictionaries
        anthropic_client: Anthropic client (will create if not provided)
        max_concurrent: Maximum concurrent API calls
        mock: If True, return mock scripts without calling API

    Returns:
        List of VideoScript objects
    """
    if anthropic_client is None and not mock:
        import anthropic
        anthropic_client = anthropic.Anthropic()

    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_job(job: dict) -> VideoScript:
        async with semaphore:
            analysis = analyze_job(job)
            return await generate_video_script_async(
                job, analysis, anthropic_client, mock
            )

    tasks = [process_job(job) for job in jobs]
    return await asyncio.gather(*tasks)


def validate_script(script: VideoScript) -> dict:
    """
    Validate a generated script against requirements.

    Returns dict with validation results:
    - is_valid: bool
    - issues: list of issues found
    """
    issues = []

    # Check word count
    if script.word_count < MIN_WORDS:
        issues.append(f"Word count too low: {script.word_count} < {MIN_WORDS}")
    if script.word_count > MAX_WORDS:
        issues.append(f"Word count too high: {script.word_count} > {MAX_WORDS}")

    # Check for emojis
    if script.has_emojis:
        issues.append("Script contains emojis (not allowed)")

    # Check for required sections
    if not script.has_opening:
        issues.append("Missing opening section")
    if not script.has_experience:
        issues.append("Missing experience section")
    if not script.has_approach:
        issues.append("Missing approach section")
    if not script.has_closing:
        issues.append("Missing closing section")

    return {
        "is_valid": len(issues) == 0,
        "issues": issues
    }


def main():
    parser = argparse.ArgumentParser(description="Generate video cover letter scripts")
    parser.add_argument("--job", "-j", help="Job JSON file or inline JSON")
    parser.add_argument("--output", "-o", help="Output file for script")
    parser.add_argument("--test", action="store_true", help="Run with mock data")
    parser.add_argument("--mock", action="store_true", help="Use mock responses (no API calls)")
    parser.add_argument("--validate", action="store_true", help="Validate the generated script")

    args = parser.parse_args()

    # Load job data
    if args.test:
        job = {
            "title": "AI Workflow Automation Specialist Needed",
            "description": """
            We're looking for an experienced AI automation developer to help us build
            automated lead generation workflows for our marketing agency.

            Requirements:
            - Experience with n8n or Make.com
            - Knowledge of AI/LLM APIs (OpenAI, Claude)
            - Ability to integrate with CRM systems
            - Strong communication skills

            We need someone who can:
            - Design the workflow architecture
            - Build and test the automations
            - Provide documentation

            Budget: $1,500-2,000
            Timeline: 2-3 weeks
            """,
            "skills": ["n8n", "Make.com", "AI Automation", "API Integration"],
            "budget": "$1,500-2,000",
            "industry": "marketing"
        }
        print("Running test with sample job data...")
    elif args.job:
        if args.job.endswith('.json'):
            with open(args.job) as f:
                job = json.load(f)
        else:
            job = json.loads(args.job)
    else:
        parser.error("Either --job or --test is required")
        return

    # Analyze job
    analysis = analyze_job(job)
    print(f"\nJob Analysis:")
    print(f"  Requirements: {len(analysis.requirements)} items")
    print(f"  Goals: {len(analysis.goals)} items")
    print(f"  Skills: {analysis.skills}")
    print(f"  Industry: {analysis.industry or 'Not specified'}")

    # Generate script
    print("\nGenerating video script...")
    script = generate_video_script(job, analysis, mock=args.mock or args.test)

    print(f"\n{'='*60}")
    print("GENERATED SCRIPT:")
    print(f"{'='*60}")
    print(script.script_text)
    print(f"{'='*60}")

    print(f"\nMetadata:")
    print(f"  Word count: {script.word_count}")
    print(f"  Has opening: {script.has_opening}")
    print(f"  Has experience: {script.has_experience}")
    print(f"  Has approach: {script.has_approach}")
    print(f"  Has closing: {script.has_closing}")
    print(f"  Mentions industry: {script.mentions_industry}")
    print(f"  Has emojis: {script.has_emojis}")

    # Validate if requested
    if args.validate:
        validation = validate_script(script)
        print(f"\nValidation: {'PASSED' if validation['is_valid'] else 'FAILED'}")
        if validation['issues']:
            for issue in validation['issues']:
                print(f"  - {issue}")

    # Save output
    if args.output:
        with open(args.output, 'w') as f:
            if args.output.endswith('.json'):
                json.dump(script.to_dict(), f, indent=2)
            else:
                f.write(script.script_text)
        print(f"\nSaved to {args.output}")

    return script


if __name__ == "__main__":
    main()
