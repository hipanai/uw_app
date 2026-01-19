#!/usr/bin/env python3
"""
Generate personalized Google Slides pitch decks based on research dossiers.
Supports parallel processing with configurable worker count.
"""

import os
import sys
import json
import argparse
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from anthropic import Anthropic
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# Load environment variables
load_dotenv()


def get_credentials():
    """
    Get OAuth2 credentials for Google Slides API.
    Uses token.json if available.

    Returns:
        Credentials object
    """
    scopes = [
        'https://www.googleapis.com/auth/presentations',
        'https://www.googleapis.com/auth/drive'
    ]

    creds = None

    if os.path.exists('config/token.json'):
        try:
            with open('config/token.json', 'r') as token:
                token_data = json.load(token)
                creds = Credentials.from_authorized_user_info(token_data, scopes)
        except Exception as e:
            print(f"Error loading token: {e}")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "config/credentials.json")
            flow = InstalledAppFlow.from_client_secrets_file(creds_file, scopes)
            creds = flow.run_local_server(port=0)

        with open('config/token.json', 'w') as token:
            token.write(creds.to_json())

    return creds


def create_presentation(title):
    """
    Create a new Google Slides presentation.

    Args:
        title: Presentation title

    Returns:
        Tuple of (presentation_id, slides_service)
    """
    try:
        creds = get_credentials()
        service = build('slides', 'v1', credentials=creds)

        presentation = service.presentations().create(body={
            'title': title
        }).execute()

        presentation_id = presentation.get('presentationId')
        print(f"Created presentation: https://docs.google.com/presentation/d/{presentation_id}")

        return presentation_id, service

    except Exception as e:
        print(f"Error creating presentation: {str(e)}", file=sys.stderr)
        return None, None


def generate_slide_content(dossier, slide_type):
    """
    Generate content for a specific slide type using Claude.

    Args:
        dossier: Research dossier dictionary
        slide_type: Type of slide to generate

    Returns:
        Dictionary with slide content
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not found in .env", file=sys.stderr)
        return None

    client = Anthropic(api_key=api_key)

    lead_info = dossier["lead_info"]
    name = lead_info.get("full_name") or lead_info.get("Name") or f"{lead_info.get('first_name', '')} {lead_info.get('last_name', '')}".strip() or "Unknown"
    company = lead_info.get("company_name") or lead_info.get("Company") or "Unknown Company"

    # Get first name
    first_name = lead_info.get("first_name") or (name.split()[0] if name and name != "Unknown" else "there")

    # Get casual company name (remove formal words)
    casual_company = company.replace(' LLC', '').replace(' Inc', '').replace(' Corp', '').replace(' Ltd', '').replace(',', '')

    prompts = {
        "intro": f"""Create a personal intro slide for a pitch deck to {name} at {company}.

Research:
{dossier.get('dossier_summary', '')}

Return JSON with:
{{
  "title": "Hi {first_name} 👋",
  "message": "Write a casual intro (under 200 chars). Template: 'I used to work in mgmt consulting & have seen a fair few [their industry] businesses. Think I can save you a bit of money!'"
}}

Identify their industry from the research. Keep it casual, use contractions. Sentence case. Under 200 characters.""",

        "blunt_opener": f"""Create a direct opener about what you want to give {company}.

Research:
{dossier.get('dossier_summary', '')}

Return JSON with:
{{
  "title": "Here's what I want to give you.",
  "message": "Write 2-3 sentences using this template: 'To make a long story short, your [process] is doing [current state] right now, which is costing you ~$[estimated amount]. I want to solve this with [solution].' Be specific based on research."
}}

Identify a specific process that's costing them money. Estimate a dollar amount if possible. Sentence case. Under 200 characters.""",

        "problem_1": f"""Identify the FIRST problem {company} faces - frame it in terms of MONEY or TIME they're losing.

Research:
{dossier.get('dossier_summary', '')}

Return JSON with:
{{
  "subtitle": "You're losing [X] on [problem].",
  "description": "2-3 sentences quantifying the cost of this problem. Use specific numbers or estimates. Frame as money/time/opportunity lost. (under 200 chars)"
}}

Example: "You're spending $X/month on ads that don't convert." or "You're leaving $X on the table by not following up."

Be specific and quantifiable. Sentence case.""",

        "problem_2": f"""Identify the SECOND problem {company} faces - frame it in terms of MONEY or TIME they're losing.

Research:
{dossier.get('dossier_summary', '')}

Return JSON with:
{{
  "subtitle": "You're missing out on [X].",
  "description": "2-3 sentences quantifying this opportunity cost. Use specific numbers or estimates. (under 200 chars)"
}}

Focus on opportunity cost - what they COULD be getting but aren't. Sentence case.""",

        "problem_3": f"""Identify the THIRD problem {company} faces - frame it in terms of FRUSTRATION or WASTE.

Research:
{dossier.get('dossier_summary', '')}

Return JSON with:
{{
  "subtitle": "You're stuck doing [X].",
  "description": "2-3 sentences about time/energy being wasted on things that could be automated or outsourced. (under 200 chars)"
}}

Focus on manual work, frustration, or inefficiency they're experiencing. Sentence case.""",

        "solution_1": f"""Describe the FIRST benefit {company} will get - use "You'll get" framing.

Research:
{dossier.get('dossier_summary', '')}

Return JSON with:
{{
  "subtitle": "You'll get [specific benefit].",
  "description": "2-3 sentences explaining the outcome, not the process. Include numbers (leads, revenue, time saved). (under 200 chars)"
}}

Example: "You'll get 50-100 qualified leads delivered to your inbox every month."

Benefits > features. Outcomes > process. Sentence case.""",

        "solution_2": f"""Describe the SECOND benefit {company} will get - use "You won't have to" framing.

Research:
{dossier.get('dossier_summary', '')}

Return JSON with:
{{
  "subtitle": "You won't have to [thing they hate].",
  "description": "2-3 sentences about what they can STOP doing. Frame as relief from burden. (under 200 chars)"
}}

Example: "You won't have to write another cold email or manage another drip sequence."

Focus on removal of pain, not addition of features. Sentence case.""",

        "solution_3": f"""Describe the THIRD benefit {company} will get - focus on ROI or time reclaimed.

Research:
{dossier.get('dossier_summary', '')}

Return JSON with:
{{
  "subtitle": "[X] more revenue or time back.",
  "description": "2-3 sentences projecting ROI or time saved. Be specific with estimates. (under 200 chars)"
}}

Example: "Based on your ACV, that's $50-100k+ in pipeline per month."

Make the math obvious. Show the upside. Sentence case.""",

        "why_this_works": f"""Explain why this specifically works for {casual_company} - focus on THEIR situation, not our features.

Research:
{dossier.get('dossier_summary', '')}

Return JSON with:
{{
  "title": "Why this works for {casual_company}.",
  "reasons": ["3 benefits framed as 'You'll...' or outcomes - EACH under 90 characters, sentence case"]
}}

Example reasons:
- "You'll close more deals without hiring another SDR."
- "You'll get warm intros, not cold spam."
- "You'll scale outreach without scaling headcount."

Casual, direct. Each reason under 90 characters. Sentence case.""",

        "meta": f"""Create a credibility slide showing the depth of research done.

Research summary:
{dossier.get('dossier_summary', '')}

Return JSON with:
{{
  "title": "P.S. This is what I'd do for you.",
  "message": "Under 150 chars: Frame this deck as a sample of the research quality they'll get. 'I put this together in 30 mins. Imagine what we'd find for your prospects.'",
  "examples": ["2 specific things discovered about them - EACH under 80 characters, sentence case"]
}}

Show, don't tell. Demonstrate value through the deck itself. Sentence case.""",

        "next_steps": f"""Create a low-pressure CTA focused on THEIR benefit.

Return JSON with:
{{
  "title": "Want to see this work for you?",
  "message": "Under 100 chars: Offer a quick chat to show them results. No pressure, just curiosity."
}}

Example: "Let's do a quick 15-min call. I'll show you exactly how this would work for {casual_company}."

Casual, benefit-focused. Sentence case. Under 100 characters."""
    }

    prompt = prompts.get(slide_type)
    if not prompt:
        return None

    try:
        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1500,
            messages=[{
                "role": "user",
                "content": prompt + "\n\nIMPORTANT: Return ONLY valid JSON, no other text."
            }]
        )

        response_text = message.content[0].text.strip()

        # Try to extract JSON if there's extra text
        if response_text.startswith('```'):
            # Remove code blocks
            response_text = response_text.split('```')[1]
            if response_text.startswith('json'):
                response_text = response_text[4:]

        content = json.loads(response_text)
        return content

    except Exception as e:
        print(f"Error generating {slide_type} content: {str(e)}", file=sys.stderr)
        return None


# Template constants (EMU = English Metric Units, 914400 EMU = 1 inch)
SLIDE_WIDTH = 9144000
SLIDE_HEIGHT = 5143500
PADDING = 200000
RECT_WIDTH = SLIDE_WIDTH - (2 * PADDING)
RECT_HEIGHT = SLIDE_HEIGHT - (2 * PADDING)

# Colors (0-1 range for Google Slides API)
ORANGE = {'red': 0.878, 'green': 0.478, 'blue': 0.302}  # #E07A4D
WHITE = {'red': 1.0, 'green': 1.0, 'blue': 1.0}
LIGHT_GRAY = {'red': 0.85, 'green': 0.85, 'blue': 0.85}


def create_template_base_requests(slide_id, unique_suffix):
    """
    Create the base template elements: white background, orange rounded rectangle, top line.

    Args:
        slide_id: The slide object ID
        unique_suffix: Unique string to append to element IDs (e.g., slide index)

    Returns:
        List of API requests and the rect_id for positioning calculations
    """
    rect_id = f'orange_rect_{unique_suffix}'

    requests = []

    # 1. Set white background
    requests.append({
        'updatePageProperties': {
            'objectId': slide_id,
            'pageProperties': {
                'pageBackgroundFill': {
                    'solidFill': {'color': {'rgbColor': WHITE}}
                }
            },
            'fields': 'pageBackgroundFill'
        }
    })

    # 2. Create orange rounded rectangle with gray border
    requests.append({
        'createShape': {
            'objectId': rect_id,
            'shapeType': 'ROUND_RECTANGLE',
            'elementProperties': {
                'pageObjectId': slide_id,
                'size': {
                    'width': {'magnitude': RECT_WIDTH, 'unit': 'EMU'},
                    'height': {'magnitude': RECT_HEIGHT, 'unit': 'EMU'}
                },
                'transform': {
                    'scaleX': 1, 'scaleY': 1,
                    'translateX': PADDING, 'translateY': PADDING,
                    'unit': 'EMU'
                }
            }
        }
    })

    requests.append({
        'updateShapeProperties': {
            'objectId': rect_id,
            'shapeProperties': {
                'shapeBackgroundFill': {
                    'solidFill': {'color': {'rgbColor': ORANGE}}
                },
                'outline': {
                    'outlineFill': {'solidFill': {'color': {'rgbColor': LIGHT_GRAY}}},
                    'weight': {'magnitude': 2, 'unit': 'PT'},
                    'dashStyle': 'SOLID'
                }
            },
            'fields': 'shapeBackgroundFill,outline'
        }
    })

    return requests


def create_text_box_requests(slide_id, text_id, text, x, y, width, height, font_size, bold=False, italic=False):
    """
    Create a text box with white Inter text.

    Args:
        slide_id: The slide object ID
        text_id: Unique ID for the text box
        text: Text content
        x, y: Position in EMU
        width, height: Size in EMU
        font_size: Font size in PT
        bold: Whether to bold the text
        italic: Whether to italicize the text

    Returns:
        List of API requests
    """
    requests = []

    # Create text box
    requests.append({
        'createShape': {
            'objectId': text_id,
            'shapeType': 'TEXT_BOX',
            'elementProperties': {
                'pageObjectId': slide_id,
                'size': {
                    'width': {'magnitude': width, 'unit': 'EMU'},
                    'height': {'magnitude': height, 'unit': 'EMU'}
                },
                'transform': {
                    'scaleX': 1, 'scaleY': 1,
                    'translateX': x, 'translateY': y,
                    'unit': 'EMU'
                }
            }
        }
    })

    # Insert text
    requests.append({
        'insertText': {
            'objectId': text_id,
            'text': text,
            'insertionIndex': 0
        }
    })

    # Style text
    requests.append({
        'updateTextStyle': {
            'objectId': text_id,
            'style': {
                'foregroundColor': {'opaqueColor': {'rgbColor': WHITE}},
                'fontSize': {'magnitude': font_size, 'unit': 'PT'},
                'fontFamily': 'Inter',
                'bold': bold,
                'italic': italic
            },
            'textRange': {'type': 'ALL'},
            'fields': 'foregroundColor,fontSize,fontFamily,bold,italic'
        }
    })

    return requests


def add_slide_with_content(service, presentation_id, slide_content, slide_type, slide_index=0):
    """
    Add a slide to the presentation with the orange template design.

    Args:
        service: Google Slides API service
        presentation_id: Presentation ID
        slide_content: Content dictionary from generate_slide_content
        slide_type: Type of slide
        slide_index: Index of the slide (for unique IDs)

    Returns:
        Slide ID
    """
    try:
        # Create a blank slide
        create_response = service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={'requests': [{
                'createSlide': {
                    'slideLayoutReference': {
                        'predefinedLayout': 'BLANK'
                    }
                }
            }]}
        ).execute()

        slide_id = create_response['replies'][0]['createSlide']['objectId']
        unique_suffix = f'{slide_index}_{slide_id[:8]}'

        # Start building requests with template base
        requests = create_template_base_requests(slide_id, unique_suffix)

        # Get content
        title_text = slide_content.get('title', '')

        # Add content based on slide type
        if slide_type == 'intro':
            # Title slide: large bold title, message below
            requests.extend(create_text_box_requests(
                slide_id, f'title_{unique_suffix}',
                title_text,
                PADDING + 300000, PADDING + 1200000,
                RECT_WIDTH - 600000, 1500000,
                56, bold=True, italic=False
            ))

            # Subtitle message
            message = slide_content.get('message', '')
            if message:
                requests.extend(create_text_box_requests(
                    slide_id, f'message_{unique_suffix}',
                    message,
                    PADDING + 300000, PADDING + 2400000,
                    RECT_WIDTH - 600000, 1200000,
                    18, bold=False, italic=False
                ))

        elif slide_type in ['blunt_opener', 'next_steps']:
            # Message slide: bold title, message below
            requests.extend(create_text_box_requests(
                slide_id, f'title_{unique_suffix}',
                title_text,
                PADDING + 300000, PADDING + 500000,
                RECT_WIDTH - 600000, 1200000,
                36, bold=True, italic=False
            ))

            message = slide_content.get('message', '')
            if message:
                requests.extend(create_text_box_requests(
                    slide_id, f'body_{unique_suffix}',
                    message,
                    PADDING + 300000, PADDING + 1800000,
                    RECT_WIDTH - 600000, 2000000,
                    18, bold=False, italic=False
                ))
                # Add line spacing
                requests.append({
                    'updateParagraphStyle': {
                        'objectId': f'body_{unique_suffix}',
                        'style': {
                            'lineSpacing': 150,
                            'spaceAbove': {'magnitude': 10, 'unit': 'PT'}
                        },
                        'textRange': {'type': 'ALL'},
                        'fields': 'lineSpacing,spaceAbove'
                    }
                })

        elif slide_type.startswith('problem_') or slide_type.startswith('solution_'):
            # Individual problem/solution slide: just subtitle + description (no pre-title)
            subtitle = slide_content.get('subtitle', '')
            if subtitle:
                requests.extend(create_text_box_requests(
                    slide_id, f'subtitle_{unique_suffix}',
                    subtitle,
                    PADDING + 300000, PADDING + 500000,
                    RECT_WIDTH - 600000, 1800000,
                    32, bold=True, italic=False
                ))

            # Description (positioned below subtitle)
            description = slide_content.get('description', '')
            if description:
                requests.extend(create_text_box_requests(
                    slide_id, f'body_{unique_suffix}',
                    description,
                    PADDING + 300000, PADDING + 2000000,
                    RECT_WIDTH - 600000, 1500000,
                    16, bold=False, italic=False
                ))
                requests.append({
                    'updateParagraphStyle': {
                        'objectId': f'body_{unique_suffix}',
                        'style': {
                            'lineSpacing': 150,
                            'spaceAbove': {'magnitude': 10, 'unit': 'PT'}
                        },
                        'textRange': {'type': 'ALL'},
                        'fields': 'lineSpacing,spaceAbove'
                    }
                })

        elif slide_type == 'why_this_works':
            # Why this works slide: title + bullet points
            requests.extend(create_text_box_requests(
                slide_id, f'title_{unique_suffix}',
                title_text,
                PADDING + 300000, PADDING + 500000,
                RECT_WIDTH - 600000, 600000,
                36, bold=True, italic=False
            ))

            items = slide_content.get('reasons', [])
            body_text = '\n'.join(f'• {r}' for r in items)

            if body_text:
                requests.extend(create_text_box_requests(
                    slide_id, f'body_{unique_suffix}',
                    body_text,
                    PADDING + 300000, PADDING + 1200000,
                    RECT_WIDTH - 600000, 2500000,
                    18, bold=False, italic=False
                ))
                requests.append({
                    'updateParagraphStyle': {
                        'objectId': f'body_{unique_suffix}',
                        'style': {
                            'lineSpacing': 180,
                            'spaceAbove': {'magnitude': 14, 'unit': 'PT'}
                        },
                        'textRange': {'type': 'ALL'},
                        'fields': 'lineSpacing,spaceAbove'
                    }
                })

        elif slide_type == 'meta':
            # Meta slide: title, message, examples
            requests.extend(create_text_box_requests(
                slide_id, f'title_{unique_suffix}',
                title_text,
                PADDING + 300000, PADDING + 700000,
                RECT_WIDTH - 600000, 800000,
                36, bold=True, italic=False
            ))

            message = slide_content.get('message', '')
            examples = slide_content.get('examples', [])
            body_text = message
            if examples:
                body_text += '\n\n' + '\n'.join(f'• {ex}' for ex in examples)

            if body_text:
                requests.extend(create_text_box_requests(
                    slide_id, f'body_{unique_suffix}',
                    body_text,
                    PADDING + 300000, PADDING + 1600000,
                    RECT_WIDTH - 600000, 2500000,
                    16, bold=False, italic=False
                ))
                requests.append({
                    'updateParagraphStyle': {
                        'objectId': f'body_{unique_suffix}',
                        'style': {
                            'lineSpacing': 160,
                            'spaceAbove': {'magnitude': 10, 'unit': 'PT'}
                        },
                        'textRange': {'type': 'ALL'},
                        'fields': 'lineSpacing,spaceAbove'
                    }
                })

        # Execute all requests
        service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={'requests': requests}
        ).execute()

        return slide_id

    except Exception as e:
        print(f"Error adding slide: {str(e)}", file=sys.stderr)
        return None


def generate_pitch_deck(dossier_file):
    """
    Generate a complete pitch deck from a dossier.

    Args:
        dossier_file: Path to dossier JSON file

    Returns:
        Presentation URL
    """
    # Load dossier
    try:
        with open(dossier_file, 'r') as f:
            dossier = json.load(f)
    except Exception as e:
        print(f"Error loading dossier: {str(e)}", file=sys.stderr)
        return None

    lead_info = dossier["lead_info"]
    name = lead_info.get("full_name") or lead_info.get("Name") or f"{lead_info.get('first_name', '')} {lead_info.get('last_name', '')}".strip() or "Unknown"
    company = lead_info.get("company_name") or lead_info.get("Company") or "Unknown Company"

    print(f"\nGenerating pitch deck for {name} at {company}...")

    # Create presentation
    title = f"Cold Email Lead Gen for {company}"
    presentation_id, service = create_presentation(title)

    if not presentation_id:
        return None

    # Define slide sequence
    slide_types = [
        'intro',
        'blunt_opener',
        'problem_1',
        'problem_2',
        'problem_3',
        'solution_1',
        'solution_2',
        'solution_3',
        'why_this_works',
        'next_steps'
    ]

    # Delete the default blank slide that comes with new presentations
    presentation = service.presentations().get(
        presentationId=presentation_id
    ).execute()

    if presentation.get('slides'):
        default_slide_id = presentation['slides'][0]['objectId']
        service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={'requests': [{
                'deleteObject': {
                    'objectId': default_slide_id
                }
            }]}
        ).execute()

    # Generate and add each slide
    for idx, slide_type in enumerate(slide_types):
        print(f"  Generating {slide_type} slide...")

        content = generate_slide_content(dossier, slide_type)
        if content:
            print(f"    Content generated, adding slide...")
            slide_id = add_slide_with_content(service, presentation_id, content, slide_type, slide_index=idx)
            if slide_id:
                print(f"    ✓ Slide added successfully (ID: {slide_id})")
            else:
                print(f"    ✗ Failed to add slide")
        else:
            print(f"    ✗ Failed to generate content")

    presentation_url = f"https://docs.google.com/presentation/d/{presentation_id}"
    print(f"\n  Deck created: {presentation_url}")

    return presentation_url


def process_single_dossier(dossier_file, index, total):
    """
    Process a single dossier and return the result.
    Thread-safe wrapper for generate_pitch_deck.
    """
    print(f"\n[{index}/{total}] Starting: {os.path.basename(dossier_file)}")

    try:
        url = generate_pitch_deck(dossier_file)
        if url:
            print(f"  ✅ [{index}/{total}] Completed: {os.path.basename(dossier_file)}")
            return {
                "dossier": dossier_file,
                "deck_url": url,
                "status": "success",
                "generated_at": datetime.now().isoformat()
            }
        else:
            return {
                "dossier": dossier_file,
                "error": "No URL returned",
                "status": "error"
            }
    except Exception as e:
        print(f"  ❌ [{index}/{total}] Error: {os.path.basename(dossier_file)}: {str(e)}", file=sys.stderr)
        return {
            "dossier": dossier_file,
            "error": str(e),
            "status": "error"
        }


def main():
    parser = argparse.ArgumentParser(description="Generate personalized pitch decks")
    parser.add_argument("--dossier", help="Single dossier file to process")
    parser.add_argument("--dossier_dir", help="Directory of dossier files to process")
    parser.add_argument("--output", default=".tmp/pitch_decks.json", help="Output file for deck URLs")
    parser.add_argument("--workers", type=int, default=5, help="Number of parallel workers (default: 5)")

    args = parser.parse_args()

    dossier_files = []

    if args.dossier:
        dossier_files = [args.dossier]
    elif args.dossier_dir:
        import glob
        dossier_files = glob.glob(f"{args.dossier_dir}/*_dossier.json")
    else:
        print("Error: Specify --dossier or --dossier_dir", file=sys.stderr)
        return 1

    total = len(dossier_files)
    print(f"Processing {total} dossiers with {args.workers} parallel workers...")
    start_time = time.time()

    results = []

    # Use ThreadPoolExecutor for parallel processing
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        # Submit all tasks
        future_to_dossier = {
            executor.submit(process_single_dossier, dossier_file, i, total): dossier_file
            for i, dossier_file in enumerate(dossier_files, 1)
        }

        # Collect results as they complete
        for future in as_completed(future_to_dossier):
            result = future.result()
            results.append(result)

    # Save results
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(results, f, indent=2)

    elapsed = time.time() - start_time
    successful = sum(1 for r in results if r['status'] == 'success')

    print(f"\n\nPitch deck generation complete!")
    print(f"  Total: {len(results)}")
    print(f"  Successful: {successful}")
    print(f"  Failed: {len(results) - successful}")
    print(f"  Time: {elapsed:.1f}s ({elapsed/len(results):.1f}s per deck)")
    print(f"  Results saved to: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
