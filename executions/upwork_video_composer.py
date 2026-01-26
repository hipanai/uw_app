#!/usr/bin/env python3
"""
Upwork Video Composer - Composites avatar video over scrolling job screenshot.

Creates a professional video cover letter by:
1. Taking a full-page job screenshot and creating a scrolling background
2. Overlaying a circular avatar video in the lower-left corner
3. Producing a final composite video

Requirements:
    - FFmpeg installed and in PATH
    - Full-page screenshot of job listing
    - HeyGen avatar video

Usage:
    python upwork_video_composer.py --screenshot job.png --avatar avatar.mp4 --output final.mp4
    python upwork_video_composer.py --screenshot job.png --avatar avatar.mp4 --duration 30
"""

import argparse
import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import urllib.request

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
DEFAULT_OUTPUT_WIDTH = 1920
DEFAULT_OUTPUT_HEIGHT = 1080
DEFAULT_AVATAR_SIZE = 280  # Diameter of circular avatar
DEFAULT_AVATAR_MARGIN = 40  # Margin from edges
DEFAULT_FPS = 30


@dataclass
class CompositeResult:
    """Result of video composition."""
    success: bool
    output_path: Optional[str] = None
    duration: Optional[float] = None
    error: Optional[str] = None


def check_ffmpeg() -> bool:
    """Check if FFmpeg is available."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def get_video_duration(video_path: str) -> float:
    """Get duration of video in seconds using FFprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path
            ],
            capture_output=True,
            text=True
        )
        return float(result.stdout.strip())
    except Exception as e:
        logger.error(f"Failed to get video duration: {e}")
        return 0.0


def get_image_dimensions(image_path: str) -> tuple[int, int]:
    """Get image dimensions using FFprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0",
                image_path
            ],
            capture_output=True,
            text=True
        )
        width, height = result.stdout.strip().split(",")
        return int(width), int(height)
    except Exception as e:
        logger.error(f"Failed to get image dimensions: {e}")
        return 1920, 1080


def download_video(url: str, output_path: str) -> bool:
    """Download video from URL."""
    try:
        logger.info(f"Downloading video from URL...")
        urllib.request.urlretrieve(url, output_path)
        return True
    except Exception as e:
        logger.error(f"Failed to download video: {e}")
        return False


def compose_video(
    screenshot_path: str,
    avatar_video_path: str,
    output_path: str,
    output_width: int = DEFAULT_OUTPUT_WIDTH,
    output_height: int = DEFAULT_OUTPUT_HEIGHT,
    avatar_size: int = DEFAULT_AVATAR_SIZE,
    avatar_margin: int = DEFAULT_AVATAR_MARGIN,
    fps: int = DEFAULT_FPS,
    duration: Optional[float] = None
) -> CompositeResult:
    """
    Compose final video with scrolling screenshot background and circular avatar overlay.

    Args:
        screenshot_path: Path to full-page screenshot
        avatar_video_path: Path to HeyGen avatar video
        output_path: Path for output video
        output_width: Output video width
        output_height: Output video height
        avatar_size: Diameter of circular avatar
        avatar_margin: Margin from screen edges
        fps: Output frame rate
        duration: Override duration (uses avatar video duration if None)

    Returns:
        CompositeResult with success status and output path
    """
    if not check_ffmpeg():
        return CompositeResult(
            success=False,
            error="FFmpeg not found. Please install FFmpeg and ensure it's in PATH."
        )

    # Get avatar video duration
    avatar_duration = get_video_duration(avatar_video_path)
    if avatar_duration <= 0:
        return CompositeResult(
            success=False,
            error="Could not determine avatar video duration"
        )

    video_duration = duration or avatar_duration
    logger.info(f"Video duration: {video_duration:.1f}s")

    # Get screenshot dimensions
    img_width, img_height = get_image_dimensions(screenshot_path)
    logger.info(f"Screenshot dimensions: {img_width}x{img_height}")

    # Calculate scroll parameters
    # Scale image to fit output width while maintaining aspect ratio
    scale_factor = output_width / img_width
    scaled_height = int(img_height * scale_factor)

    # Calculate scroll distance (how much to pan)
    scroll_distance = max(0, scaled_height - output_height)
    scroll_speed = scroll_distance / video_duration if scroll_distance > 0 else 0

    logger.info(f"Scaled height: {scaled_height}, scroll distance: {scroll_distance}")

    # Avatar position (lower-right corner)
    avatar_x = output_width - avatar_size - avatar_margin
    avatar_y = output_height - avatar_size - avatar_margin

    # Build FFmpeg filter complex
    # 1. Scale screenshot to output width and create scrolling crop
    # 2. Scale avatar video and apply circular mask (preserving colors)
    # 3. Add white circular border behind avatar
    # 4. Overlay avatar on scrolling background

    radius = avatar_size // 2
    border_width = 4

    if scroll_distance > 0:
        # Scrolling background - pan from top to bottom
        scroll_expr = f"min({scroll_distance},t*{scroll_speed})"
        bg_filter = (
            f"[0:v]scale={output_width}:{scaled_height},"
            f"crop={output_width}:{output_height}:0:'{scroll_expr}'[bg]"
        )
    else:
        # No scroll needed, just scale and crop to fit
        bg_filter = (
            f"[0:v]scale={output_width}:{scaled_height},"
            f"crop={output_width}:{output_height}:0:0[bg]"
        )

    # Create circular mask for avatar (white circle on black background)
    # This mask will be used with alphamerge to make avatar circular
    mask_filter = (
        f"color=black:s={avatar_size}x{avatar_size}:d={video_duration},"
        f"drawbox=x=0:y=0:w={avatar_size}:h={avatar_size}:c=black:t=fill,"
        f"format=gray,"
        f"geq=lum='if(lte(pow(X-{radius},2)+pow(Y-{radius},2),pow({radius}-{border_width},2)),255,0)'[mask]"
    )

    # Scale avatar and apply circular mask
    avatar_filter = (
        f"[1:v]scale={avatar_size}:{avatar_size},format=rgba[avatar_scaled];"
        f"[avatar_scaled][mask]alphamerge[avatar_circle]"
    )

    # Create white circle border
    border_filter = (
        f"color=white@1:s={avatar_size}x{avatar_size}:d={video_duration},"
        f"format=rgba,"
        f"geq=r='if(lte(pow(X-{radius},2)+pow(Y-{radius},2),pow({radius},2)),255,0)':"
        f"g='if(lte(pow(X-{radius},2)+pow(Y-{radius},2),pow({radius},2)),255,0)':"
        f"b='if(lte(pow(X-{radius},2)+pow(Y-{radius},2),pow({radius},2)),255,0)':"
        f"a='if(lte(pow(X-{radius},2)+pow(Y-{radius},2),pow({radius},2)),if(lte(pow(X-{radius},2)+pow(Y-{radius},2),pow({radius}-{border_width},2)),0,255),0)'[border]"
    )

    # Composite: background + border + avatar
    filter_complex = (
        f"{bg_filter};"
        f"{mask_filter};"
        f"{avatar_filter};"
        f"{border_filter};"
        f"[bg][border]overlay={avatar_x}:{avatar_y}:format=auto[bg_border];"
        f"[bg_border][avatar_circle]overlay={avatar_x}:{avatar_y}:format=auto[out]"
    )

    # Build FFmpeg command
    cmd = [
        "ffmpeg",
        "-y",  # Overwrite output
        "-loop", "1",  # Loop the image
        "-i", screenshot_path,  # Input 0: screenshot
        "-i", avatar_video_path,  # Input 1: avatar video
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-map", "1:a?",  # Include audio from avatar if present
        "-t", str(video_duration),
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        output_path
    ]

    logger.info("Running FFmpeg composition...")
    logger.debug(f"Command: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr}")
            return CompositeResult(
                success=False,
                error=f"FFmpeg failed: {result.stderr[-500:]}"
            )

        logger.info(f"Video composed successfully: {output_path}")
        return CompositeResult(
            success=True,
            output_path=output_path,
            duration=video_duration
        )

    except subprocess.TimeoutExpired:
        return CompositeResult(
            success=False,
            error="FFmpeg timed out after 5 minutes"
        )
    except Exception as e:
        return CompositeResult(
            success=False,
            error=f"FFmpeg error: {str(e)}"
        )


def compose_video_from_urls(
    screenshot_path: str,
    avatar_video_url: str,
    output_path: str,
    **kwargs
) -> CompositeResult:
    """
    Compose video, downloading avatar from URL first.

    Args:
        screenshot_path: Path to local screenshot file
        avatar_video_url: URL to HeyGen avatar video
        output_path: Path for output video
        **kwargs: Additional arguments passed to compose_video

    Returns:
        CompositeResult
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Download avatar video
        avatar_local = os.path.join(tmp_dir, "avatar.mp4")

        if not download_video(avatar_video_url, avatar_local):
            return CompositeResult(
                success=False,
                error="Failed to download avatar video"
            )

        # Compose video
        return compose_video(
            screenshot_path=screenshot_path,
            avatar_video_path=avatar_local,
            output_path=output_path,
            **kwargs
        )


async def compose_video_async(
    screenshot_path: str,
    avatar_video_path: str,
    output_path: str,
    **kwargs
) -> CompositeResult:
    """Async wrapper for compose_video."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: compose_video(
            screenshot_path=screenshot_path,
            avatar_video_path=avatar_video_path,
            output_path=output_path,
            **kwargs
        )
    )


async def compose_video_from_urls_async(
    screenshot_path: str,
    avatar_video_url: str,
    output_path: str,
    **kwargs
) -> CompositeResult:
    """Async wrapper for compose_video_from_urls."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: compose_video_from_urls(
            screenshot_path=screenshot_path,
            avatar_video_url=avatar_video_url,
            output_path=output_path,
            **kwargs
        )
    )


def compose_video_with_transition(
    job_screenshot_path: str,
    proposal_screenshot_path: str,
    avatar_video_path: str,
    output_path: str,
    transition_time: float = 15.0,
    output_width: int = DEFAULT_OUTPUT_WIDTH,
    output_height: int = DEFAULT_OUTPUT_HEIGHT,
    avatar_size: int = DEFAULT_AVATAR_SIZE,
    avatar_margin: int = DEFAULT_AVATAR_MARGIN,
    fps: int = DEFAULT_FPS,
    duration: Optional[float] = None
) -> CompositeResult:
    """
    Compose video with transition from job listing to proposal view.

    Shows job listing initially, then transitions to proposal view
    when avatar discusses the approach.

    Args:
        job_screenshot_path: Path to job listing screenshot
        proposal_screenshot_path: Path to proposal screenshot
        avatar_video_path: Path to HeyGen avatar video
        output_path: Path for output video
        transition_time: Time (seconds) to transition from job to proposal
        output_width: Output video width
        output_height: Output video height
        avatar_size: Diameter of circular avatar
        avatar_margin: Margin from screen edges
        fps: Output frame rate
        duration: Override duration (uses avatar video duration if None)

    Returns:
        CompositeResult with success status and output path
    """
    if not check_ffmpeg():
        return CompositeResult(
            success=False,
            error="FFmpeg not found. Please install FFmpeg and ensure it's in PATH."
        )

    # Get avatar video duration
    avatar_duration = get_video_duration(avatar_video_path)
    if avatar_duration <= 0:
        return CompositeResult(
            success=False,
            error="Could not determine avatar video duration"
        )

    video_duration = duration or avatar_duration
    logger.info(f"Video duration: {video_duration:.1f}s, transition at: {transition_time:.1f}s")

    # Avatar position (lower-right corner)
    avatar_x = output_width - avatar_size - avatar_margin
    avatar_y = output_height - avatar_size - avatar_margin

    radius = avatar_size // 2
    border_width = 4

    # Transition duration (crossfade)
    fade_duration = 0.8

    # Build FFmpeg filter complex for two backgrounds with crossfade transition
    # Input 0: job screenshot
    # Input 1: proposal screenshot
    # Input 2: avatar video

    # Scale both backgrounds to output size
    bg1_filter = f"[0:v]scale={output_width}:{output_height}:force_original_aspect_ratio=increase,crop={output_width}:{output_height}[bg1]"
    bg2_filter = f"[1:v]scale={output_width}:{output_height}:force_original_aspect_ratio=increase,crop={output_width}:{output_height}[bg2]"

    # Create crossfade transition between backgrounds
    # Show bg1 until transition_time, then fade to bg2
    crossfade_filter = (
        f"[bg1][bg2]xfade=transition=fade:duration={fade_duration}:offset={transition_time}[bg]"
    )

    # Create circular mask for avatar
    mask_filter = (
        f"color=black:s={avatar_size}x{avatar_size}:d={video_duration},"
        f"format=gray,"
        f"geq=lum='if(lte(pow(X-{radius},2)+pow(Y-{radius},2),pow({radius}-{border_width},2)),255,0)'[mask]"
    )

    # Scale avatar and apply circular mask
    avatar_filter = (
        f"[2:v]scale={avatar_size}:{avatar_size},format=rgba[avatar_scaled];"
        f"[avatar_scaled][mask]alphamerge[avatar_circle]"
    )

    # Create white circle border
    border_filter = (
        f"color=white@1:s={avatar_size}x{avatar_size}:d={video_duration},"
        f"format=rgba,"
        f"geq=r='if(lte(pow(X-{radius},2)+pow(Y-{radius},2),pow({radius},2)),255,0)':"
        f"g='if(lte(pow(X-{radius},2)+pow(Y-{radius},2),pow({radius},2)),255,0)':"
        f"b='if(lte(pow(X-{radius},2)+pow(Y-{radius},2),pow({radius},2)),255,0)':"
        f"a='if(lte(pow(X-{radius},2)+pow(Y-{radius},2),pow({radius},2)),if(lte(pow(X-{radius},2)+pow(Y-{radius},2),pow({radius}-{border_width},2)),0,255),0)'[border]"
    )

    # Composite: background + border + avatar
    filter_complex = (
        f"{bg1_filter};"
        f"{bg2_filter};"
        f"{crossfade_filter};"
        f"{mask_filter};"
        f"{avatar_filter};"
        f"{border_filter};"
        f"[bg][border]overlay={avatar_x}:{avatar_y}:format=auto[bg_border];"
        f"[bg_border][avatar_circle]overlay={avatar_x}:{avatar_y}:format=auto[out]"
    )

    # Build FFmpeg command
    cmd = [
        "ffmpeg",
        "-y",
        "-loop", "1", "-t", str(transition_time + fade_duration + 1),
        "-i", job_screenshot_path,
        "-loop", "1", "-t", str(video_duration - transition_time + 1),
        "-i", proposal_screenshot_path,
        "-i", avatar_video_path,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-map", "2:a?",
        "-t", str(video_duration),
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        output_path
    ]

    logger.info("Running FFmpeg composition with transition...")
    logger.debug(f"Command: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr}")
            return CompositeResult(
                success=False,
                error=f"FFmpeg failed: {result.stderr[-500:]}"
            )

        logger.info(f"Video composed successfully: {output_path}")
        return CompositeResult(
            success=True,
            output_path=output_path,
            duration=video_duration
        )

    except subprocess.TimeoutExpired:
        return CompositeResult(success=False, error="FFmpeg timed out")
    except Exception as e:
        return CompositeResult(success=False, error=f"FFmpeg error: {str(e)}")


def compose_video_with_transition_from_urls(
    job_screenshot_path: str,
    proposal_screenshot_path: str,
    avatar_video_url: str,
    output_path: str,
    **kwargs
) -> CompositeResult:
    """
    Compose video with transition, downloading avatar from URL first.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        avatar_local = os.path.join(tmp_dir, "avatar.mp4")

        if not download_video(avatar_video_url, avatar_local):
            return CompositeResult(
                success=False,
                error="Failed to download avatar video"
            )

        return compose_video_with_transition(
            job_screenshot_path=job_screenshot_path,
            proposal_screenshot_path=proposal_screenshot_path,
            avatar_video_path=avatar_local,
            output_path=output_path,
            **kwargs
        )


async def compose_video_with_transition_async(
    job_screenshot_path: str,
    proposal_screenshot_path: str,
    avatar_video_url: str,
    output_path: str,
    **kwargs
) -> CompositeResult:
    """Async wrapper for compose_video_with_transition_from_urls."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: compose_video_with_transition_from_urls(
            job_screenshot_path=job_screenshot_path,
            proposal_screenshot_path=proposal_screenshot_path,
            avatar_video_url=avatar_video_url,
            output_path=output_path,
            **kwargs
        )
    )


def main():
    parser = argparse.ArgumentParser(
        description="Compose video with scrolling screenshot and avatar overlay"
    )
    parser.add_argument(
        "--screenshot", "-s",
        required=True,
        help="Path to full-page job screenshot"
    )
    parser.add_argument(
        "--avatar", "-a",
        required=True,
        help="Path or URL to HeyGen avatar video"
    )
    parser.add_argument(
        "--output", "-o",
        default="composed_video.mp4",
        help="Output video path"
    )
    parser.add_argument(
        "--width",
        type=int,
        default=DEFAULT_OUTPUT_WIDTH,
        help=f"Output width (default: {DEFAULT_OUTPUT_WIDTH})"
    )
    parser.add_argument(
        "--height",
        type=int,
        default=DEFAULT_OUTPUT_HEIGHT,
        help=f"Output height (default: {DEFAULT_OUTPUT_HEIGHT})"
    )
    parser.add_argument(
        "--avatar-size",
        type=int,
        default=DEFAULT_AVATAR_SIZE,
        help=f"Avatar circle diameter (default: {DEFAULT_AVATAR_SIZE})"
    )
    parser.add_argument(
        "--margin",
        type=int,
        default=DEFAULT_AVATAR_MARGIN,
        help=f"Avatar margin from edges (default: {DEFAULT_AVATAR_MARGIN})"
    )
    parser.add_argument(
        "--duration",
        type=float,
        help="Override video duration (uses avatar duration by default)"
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=DEFAULT_FPS,
        help=f"Output frame rate (default: {DEFAULT_FPS})"
    )

    args = parser.parse_args()

    # Check if avatar is URL or file
    if args.avatar.startswith("http"):
        result = compose_video_from_urls(
            screenshot_path=args.screenshot,
            avatar_video_url=args.avatar,
            output_path=args.output,
            output_width=args.width,
            output_height=args.height,
            avatar_size=args.avatar_size,
            avatar_margin=args.margin,
            duration=args.duration,
            fps=args.fps
        )
    else:
        result = compose_video(
            screenshot_path=args.screenshot,
            avatar_video_path=args.avatar,
            output_path=args.output,
            output_width=args.width,
            output_height=args.height,
            avatar_size=args.avatar_size,
            avatar_margin=args.margin,
            duration=args.duration,
            fps=args.fps
        )

    if result.success:
        print(f"Video composed successfully!")
        print(f"  Output: {result.output_path}")
        print(f"  Duration: {result.duration:.1f}s")
    else:
        print(f"Composition failed: {result.error}")
        exit(1)


if __name__ == "__main__":
    main()
