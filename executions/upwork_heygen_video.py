#!/usr/bin/env python3
"""
Upwork HeyGen Video Integration

Creates HeyGen AI avatar videos for Upwork job applications.
Features #29-32:
- Create video from script using HeyGen API
- Poll for video completion with timeout protection
- Use correct avatar ID from environment
- Use job snapshot as video background

Usage:
    python upwork_heygen_video.py --script "Your video script..." --output video_result.json
    python upwork_heygen_video.py --script-file script.txt --snapshot-url "https://..."
    python upwork_heygen_video.py --test
"""

import os
import time
import json
import argparse
import asyncio
import httpx
from typing import Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# HeyGen API configuration
HEYGEN_API_BASE = "https://api.heygen.com"
HEYGEN_API_V2 = f"{HEYGEN_API_BASE}/v2"
HEYGEN_API_V1 = f"{HEYGEN_API_BASE}/v1"

# Default settings
DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
DEFAULT_POLL_INTERVAL = 10  # seconds
DEFAULT_MAX_POLL_TIME = 300  # 5 minutes timeout


@dataclass
class VideoGenerationResult:
    """Result of HeyGen video generation."""
    video_id: str
    status: str  # "pending", "processing", "completed", "failed"
    video_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration: Optional[float] = None
    error: Optional[str] = None
    created_at: str = ""
    completed_at: Optional[str] = None
    poll_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class HeyGenClient:
    """Client for HeyGen API interactions."""

    def __init__(self, api_key: Optional[str] = None, avatar_id: Optional[str] = None):
        """
        Initialize HeyGen client.

        Args:
            api_key: HeyGen API key (defaults to HEYGEN_API_KEY env var)
            avatar_id: Default avatar ID (defaults to HEYGEN_AVATAR_ID env var)
        """
        self.api_key = api_key or os.environ.get("HEYGEN_API_KEY")
        self.avatar_id = avatar_id or os.environ.get("HEYGEN_AVATAR_ID")

        if not self.api_key:
            raise ValueError("HEYGEN_API_KEY not found in environment or parameters")

        self.headers = {
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json"
        }

    def _get_headers(self) -> dict:
        """Get API headers (safe for logging - doesn't expose full key)."""
        return self.headers.copy()

    def create_video(
        self,
        script: str,
        avatar_id: Optional[str] = None,
        background_url: Optional[str] = None,
        background_color: str = "#FFFFFF",
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        voice_id: Optional[str] = None
    ) -> VideoGenerationResult:
        """
        Create a HeyGen video from script.

        Args:
            script: The text script for the avatar to speak
            avatar_id: Avatar ID to use (defaults to instance avatar_id)
            background_url: URL of background image (job snapshot)
            background_color: Background color if no image provided
            width: Video width in pixels
            height: Video height in pixels
            voice_id: Optional voice ID (if not using avatar's default)

        Returns:
            VideoGenerationResult with video_id for polling
        """
        import requests

        effective_avatar_id = avatar_id or self.avatar_id
        if not effective_avatar_id:
            raise ValueError("avatar_id must be provided or HEYGEN_AVATAR_ID must be set")

        # Get voice_id from env if not provided
        effective_voice_id = voice_id or os.getenv("HEYGEN_VOICE_ID")
        if not effective_voice_id:
            raise ValueError("voice_id must be provided or HEYGEN_VOICE_ID must be set")

        # Build the video input
        video_input = {
            "character": {
                "type": "avatar",
                "avatar_id": effective_avatar_id,
                "avatar_style": "normal"
            },
            "voice": {
                "type": "text",
                "input_text": script,
                "voice_id": effective_voice_id
            }
        }

        # Add background
        if background_url:
            video_input["background"] = {
                "type": "image",
                "url": background_url
            }
        else:
            video_input["background"] = {
                "type": "color",
                "value": background_color
            }

        # Build request payload
        payload = {
            "video_inputs": [video_input],
            "dimension": {
                "width": width,
                "height": height
            }
        }

        # Make API request
        response = requests.post(
            f"{HEYGEN_API_V2}/video/generate",
            headers=self._get_headers(),
            json=payload,
            timeout=60
        )

        if response.status_code != 200:
            error_msg = f"HeyGen API error: {response.status_code} - {response.text}"
            return VideoGenerationResult(
                video_id="",
                status="failed",
                error=error_msg,
                created_at=datetime.utcnow().isoformat()
            )

        data = response.json()

        # Check for API errors in response
        if data.get("error"):
            return VideoGenerationResult(
                video_id="",
                status="failed",
                error=data.get("error", {}).get("message", "Unknown error"),
                created_at=datetime.utcnow().isoformat()
            )

        video_id = data.get("data", {}).get("video_id", "")

        return VideoGenerationResult(
            video_id=video_id,
            status="pending",
            created_at=datetime.utcnow().isoformat()
        )

    def get_video_status(self, video_id: str) -> VideoGenerationResult:
        """
        Get the status of a video generation.

        Args:
            video_id: The video ID to check

        Returns:
            VideoGenerationResult with current status
        """
        import requests

        response = requests.get(
            f"{HEYGEN_API_V1}/video_status.get",
            headers=self._get_headers(),
            params={"video_id": video_id},
            timeout=30
        )

        if response.status_code != 200:
            return VideoGenerationResult(
                video_id=video_id,
                status="failed",
                error=f"Status check failed: {response.status_code} - {response.text}",
                created_at=""
            )

        data = response.json()
        video_data = data.get("data", {})

        status = video_data.get("status", "unknown")

        # Map HeyGen status to our status
        status_map = {
            "pending": "pending",
            "processing": "processing",
            "completed": "completed",
            "failed": "failed",
            "error": "failed"
        }
        normalized_status = status_map.get(status, status)

        result = VideoGenerationResult(
            video_id=video_id,
            status=normalized_status,
            created_at=""
        )

        if normalized_status == "completed":
            result.video_url = video_data.get("video_url")
            result.thumbnail_url = video_data.get("thumbnail_url")
            result.duration = video_data.get("duration")
            result.completed_at = datetime.utcnow().isoformat()

        if normalized_status == "failed":
            result.error = video_data.get("error", "Video generation failed")

        return result

    def poll_for_completion(
        self,
        video_id: str,
        poll_interval: int = DEFAULT_POLL_INTERVAL,
        max_poll_time: int = DEFAULT_MAX_POLL_TIME
    ) -> VideoGenerationResult:
        """
        Poll for video completion with timeout.

        Args:
            video_id: The video ID to poll
            poll_interval: Seconds between polls
            max_poll_time: Maximum time to wait (timeout protection)

        Returns:
            VideoGenerationResult with final status
        """
        start_time = time.time()
        poll_count = 0

        while True:
            elapsed = time.time() - start_time
            if elapsed > max_poll_time:
                return VideoGenerationResult(
                    video_id=video_id,
                    status="failed",
                    error=f"Timeout after {max_poll_time} seconds ({poll_count} polls)",
                    poll_count=poll_count,
                    created_at=""
                )

            poll_count += 1
            result = self.get_video_status(video_id)
            result.poll_count = poll_count

            if result.status in ("completed", "failed"):
                return result

            time.sleep(poll_interval)

    def create_video_and_wait(
        self,
        script: str,
        avatar_id: Optional[str] = None,
        background_url: Optional[str] = None,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        poll_interval: int = DEFAULT_POLL_INTERVAL,
        max_poll_time: int = DEFAULT_MAX_POLL_TIME
    ) -> VideoGenerationResult:
        """
        Create a video and wait for completion.

        This is a convenience method that combines create_video() and poll_for_completion().

        Args:
            script: The text script for the avatar to speak
            avatar_id: Avatar ID to use
            background_url: URL of background image
            width: Video width
            height: Video height
            poll_interval: Seconds between status polls
            max_poll_time: Maximum wait time (timeout)

        Returns:
            VideoGenerationResult with final status and video URL if successful
        """
        # Create the video
        create_result = self.create_video(
            script=script,
            avatar_id=avatar_id,
            background_url=background_url,
            width=width,
            height=height
        )

        if create_result.status == "failed":
            return create_result

        # Poll for completion
        final_result = self.poll_for_completion(
            video_id=create_result.video_id,
            poll_interval=poll_interval,
            max_poll_time=max_poll_time
        )

        # Preserve creation timestamp
        final_result.created_at = create_result.created_at

        return final_result


class AsyncHeyGenClient:
    """Async client for HeyGen API interactions."""

    def __init__(self, api_key: Optional[str] = None, avatar_id: Optional[str] = None):
        """Initialize async HeyGen client."""
        self.api_key = api_key or os.environ.get("HEYGEN_API_KEY")
        self.avatar_id = avatar_id or os.environ.get("HEYGEN_AVATAR_ID")

        if not self.api_key:
            raise ValueError("HEYGEN_API_KEY not found in environment or parameters")

        self.headers = {
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json"
        }

    async def create_video(
        self,
        script: str,
        avatar_id: Optional[str] = None,
        background_url: Optional[str] = None,
        background_color: str = "#FFFFFF",
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        voice_id: Optional[str] = None
    ) -> VideoGenerationResult:
        """Create a HeyGen video asynchronously."""
        effective_avatar_id = avatar_id or self.avatar_id
        if not effective_avatar_id:
            raise ValueError("avatar_id must be provided or HEYGEN_AVATAR_ID must be set")

        # Get voice_id from env if not provided
        effective_voice_id = voice_id or os.getenv("HEYGEN_VOICE_ID")
        if not effective_voice_id:
            raise ValueError("voice_id must be provided or HEYGEN_VOICE_ID must be set")

        video_input = {
            "character": {
                "type": "avatar",
                "avatar_id": effective_avatar_id,
                "avatar_style": "normal"
            },
            "voice": {
                "type": "text",
                "input_text": script,
                "voice_id": effective_voice_id
            }
        }

        if background_url:
            video_input["background"] = {
                "type": "image",
                "url": background_url
            }
        else:
            video_input["background"] = {
                "type": "color",
                "value": background_color
            }

        payload = {
            "video_inputs": [video_input],
            "dimension": {"width": width, "height": height}
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{HEYGEN_API_V2}/video/generate",
                headers=self.headers,
                json=payload
            )
            if response.status_code != 200:
                return VideoGenerationResult(
                    video_id="",
                    status="failed",
                    error=f"HeyGen API error: {response.status_code} - {response.text}",
                    created_at=datetime.utcnow().isoformat()
                )

            data = response.json()

            if data.get("error"):
                return VideoGenerationResult(
                    video_id="",
                    status="failed",
                    error=data.get("error", {}).get("message", "Unknown error"),
                    created_at=datetime.utcnow().isoformat()
                )

            video_id = data.get("data", {}).get("video_id", "")
            return VideoGenerationResult(
                video_id=video_id,
                status="pending",
                created_at=datetime.utcnow().isoformat()
            )

    async def get_video_status(self, video_id: str) -> VideoGenerationResult:
        """Get video status asynchronously."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{HEYGEN_API_V1}/video_status.get",
                headers=self.headers,
                params={"video_id": video_id}
            )
            if response.status_code != 200:
                return VideoGenerationResult(
                    video_id=video_id,
                    status="failed",
                    error=f"Status check failed: {response.status_code} - {response.text}",
                    created_at=""
                )

            data = response.json()
            video_data = data.get("data", {})
            status = video_data.get("status", "unknown")

            status_map = {
                "pending": "pending",
                "processing": "processing",
                "completed": "completed",
                "failed": "failed",
                "error": "failed"
            }
            normalized_status = status_map.get(status, status)

            result = VideoGenerationResult(
                video_id=video_id,
                status=normalized_status,
                created_at=""
            )

            if normalized_status == "completed":
                result.video_url = video_data.get("video_url")
                result.thumbnail_url = video_data.get("thumbnail_url")
                result.duration = video_data.get("duration")
                result.completed_at = datetime.utcnow().isoformat()

            if normalized_status == "failed":
                result.error = video_data.get("error", "Video generation failed")

            return result

    async def poll_for_completion(
        self,
        video_id: str,
        poll_interval: int = DEFAULT_POLL_INTERVAL,
        max_poll_time: int = DEFAULT_MAX_POLL_TIME
    ) -> VideoGenerationResult:
        """Poll for video completion asynchronously."""
        start_time = time.time()
        poll_count = 0

        while True:
            elapsed = time.time() - start_time
            if elapsed > max_poll_time:
                return VideoGenerationResult(
                    video_id=video_id,
                    status="failed",
                    error=f"Timeout after {max_poll_time} seconds ({poll_count} polls)",
                    poll_count=poll_count,
                    created_at=""
                )

            poll_count += 1
            result = await self.get_video_status(video_id)
            result.poll_count = poll_count

            if result.status in ("completed", "failed"):
                return result

            await asyncio.sleep(poll_interval)

    async def create_video_and_wait(
        self,
        script: str,
        avatar_id: Optional[str] = None,
        background_url: Optional[str] = None,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        poll_interval: int = DEFAULT_POLL_INTERVAL,
        max_poll_time: int = DEFAULT_MAX_POLL_TIME
    ) -> VideoGenerationResult:
        """Create video and wait for completion asynchronously."""
        create_result = await self.create_video(
            script=script,
            avatar_id=avatar_id,
            background_url=background_url,
            width=width,
            height=height
        )

        if create_result.status == "failed":
            return create_result

        final_result = await self.poll_for_completion(
            video_id=create_result.video_id,
            poll_interval=poll_interval,
            max_poll_time=max_poll_time
        )

        final_result.created_at = create_result.created_at
        return final_result


# Convenience functions for direct use
def create_heygen_video(
    script: str,
    job_snapshot_url: Optional[str] = None,
    avatar_id: Optional[str] = None,
    wait_for_completion: bool = True,
    max_wait_time: int = DEFAULT_MAX_POLL_TIME
) -> VideoGenerationResult:
    """
    Create a HeyGen video from script.

    This is the main function to call for video generation.

    Args:
        script: Video script text
        job_snapshot_url: URL of job screenshot for background
        avatar_id: Avatar ID (defaults to HEYGEN_AVATAR_ID env var)
        wait_for_completion: If True, poll until complete or timeout
        max_wait_time: Maximum seconds to wait for completion

    Returns:
        VideoGenerationResult with video_url if successful
    """
    client = HeyGenClient(avatar_id=avatar_id)

    if wait_for_completion:
        return client.create_video_and_wait(
            script=script,
            background_url=job_snapshot_url,
            max_poll_time=max_wait_time
        )
    else:
        return client.create_video(
            script=script,
            background_url=job_snapshot_url
        )


async def create_heygen_video_async(
    script: str,
    job_snapshot_url: Optional[str] = None,
    avatar_id: Optional[str] = None,
    wait_for_completion: bool = True,
    max_wait_time: int = DEFAULT_MAX_POLL_TIME
) -> VideoGenerationResult:
    """
    Create a HeyGen video asynchronously.

    Args:
        script: Video script text
        job_snapshot_url: URL of job screenshot for background
        avatar_id: Avatar ID (defaults to HEYGEN_AVATAR_ID env var)
        wait_for_completion: If True, poll until complete or timeout
        max_wait_time: Maximum seconds to wait for completion

    Returns:
        VideoGenerationResult with video_url if successful
    """
    client = AsyncHeyGenClient(avatar_id=avatar_id)

    if wait_for_completion:
        return await client.create_video_and_wait(
            script=script,
            background_url=job_snapshot_url,
            max_poll_time=max_wait_time
        )
    else:
        return await client.create_video(
            script=script,
            background_url=job_snapshot_url
        )


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Create HeyGen videos for Upwork applications")
    parser.add_argument("--script", "-s", help="Video script text")
    parser.add_argument("--script-file", "-f", help="File containing video script")
    parser.add_argument("--snapshot-url", "-b", help="URL of job snapshot for background")
    parser.add_argument("--avatar-id", "-a", help="HeyGen avatar ID (overrides env var)")
    parser.add_argument("--output", "-o", help="Output JSON file for result")
    parser.add_argument("--no-wait", action="store_true", help="Don't wait for completion")
    parser.add_argument("--max-wait", type=int, default=DEFAULT_MAX_POLL_TIME,
                        help=f"Max wait time in seconds (default: {DEFAULT_MAX_POLL_TIME})")
    parser.add_argument("--test", action="store_true", help="Run with test data (mock mode)")

    args = parser.parse_args()

    # Get script content
    if args.test:
        script = """Hi there! I noticed you're looking for help with AI automation, and I'm excited to share how I can help.

In my experience building AI automation systems, I've delivered similar solutions that increased efficiency by 40% using n8n and the Claude API.

For your project, I would approach this by first understanding your current workflow, then designing a custom automation using tools like Make.com and Airtable.

I'd love to discuss your specific needs. Would you be available for a quick 10-minute call? I'm typically available from 12 noon to 6pm Eastern.

Best regards,
Clyde"""
        print("Running in test mode with sample script...")
    elif args.script:
        script = args.script
    elif args.script_file:
        with open(args.script_file, 'r') as f:
            script = f.read()
    else:
        parser.error("Either --script, --script-file, or --test is required")
        return

    # Check environment
    api_key = os.environ.get("HEYGEN_API_KEY")
    avatar_id = args.avatar_id or os.environ.get("HEYGEN_AVATAR_ID")

    print(f"\nConfiguration:")
    print(f"  API Key: {'*' * 20}... (set)" if api_key else "  API Key: NOT SET")
    print(f"  Avatar ID: {avatar_id or 'NOT SET'}")
    print(f"  Background URL: {args.snapshot_url or 'None (using default)'}")
    print(f"  Script length: {len(script)} characters")
    print(f"  Wait for completion: {not args.no_wait}")
    if not args.no_wait:
        print(f"  Max wait time: {args.max_wait} seconds")

    if args.test:
        # Mock mode - don't actually call API
        print("\n[TEST MODE - Not calling API]")
        result = VideoGenerationResult(
            video_id="test_video_123",
            status="completed",
            video_url="https://example.com/test_video.mp4",
            thumbnail_url="https://example.com/test_thumb.jpg",
            duration=65.5,
            created_at=datetime.utcnow().isoformat(),
            completed_at=datetime.utcnow().isoformat(),
            poll_count=3
        )
    else:
        if not api_key:
            print("\nError: HEYGEN_API_KEY not set in environment")
            return

        if not avatar_id:
            print("\nError: HEYGEN_AVATAR_ID not set in environment or --avatar-id not provided")
            return

        print("\nCreating video...")
        result = create_heygen_video(
            script=script,
            job_snapshot_url=args.snapshot_url,
            avatar_id=avatar_id,
            wait_for_completion=not args.no_wait,
            max_wait_time=args.max_wait
        )

    # Print result
    print(f"\n{'='*60}")
    print("RESULT:")
    print(f"{'='*60}")
    print(f"  Video ID: {result.video_id}")
    print(f"  Status: {result.status}")
    if result.video_url:
        print(f"  Video URL: {result.video_url}")
    if result.thumbnail_url:
        print(f"  Thumbnail: {result.thumbnail_url}")
    if result.duration:
        print(f"  Duration: {result.duration:.1f} seconds")
    if result.error:
        print(f"  Error: {result.error}")
    print(f"  Created at: {result.created_at}")
    if result.completed_at:
        print(f"  Completed at: {result.completed_at}")
    print(f"  Poll count: {result.poll_count}")

    # Save output
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(result.to_dict(), f, indent=2)
        print(f"\nSaved result to {args.output}")

    return result


if __name__ == "__main__":
    main()
