#!/usr/bin/env python3
"""
Tests for Upwork HeyGen Video Integration

Tests Features #29-32:
- Feature #29: HeyGen integration can create video from script
- Feature #30: HeyGen integration can poll for video completion
- Feature #31: HeyGen video uses correct avatar ID from environment
- Feature #32: HeyGen video uses job snapshot as background

Run:
    python -m pytest executions/test_upwork_heygen_video.py -v
    python executions/test_upwork_heygen_video.py  # Direct execution
"""

import os
import sys
import json
import time
import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from executions.upwork_heygen_video import (
    HeyGenClient,
    AsyncHeyGenClient,
    VideoGenerationResult,
    create_heygen_video,
    create_heygen_video_async,
    DEFAULT_WIDTH,
    DEFAULT_HEIGHT,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_MAX_POLL_TIME,
    HEYGEN_API_V2,
    HEYGEN_API_V1
)


class TestVideoGenerationResult(unittest.TestCase):
    """Tests for VideoGenerationResult dataclass."""

    def test_creation(self):
        """Test basic result creation."""
        result = VideoGenerationResult(
            video_id="test123",
            status="pending",
            created_at="2025-01-18T12:00:00"
        )
        self.assertEqual(result.video_id, "test123")
        self.assertEqual(result.status, "pending")
        self.assertIsNone(result.video_url)
        self.assertIsNone(result.error)

    def test_to_dict(self):
        """Test serialization to dictionary."""
        result = VideoGenerationResult(
            video_id="test123",
            status="completed",
            video_url="https://example.com/video.mp4",
            duration=60.5,
            created_at="2025-01-18T12:00:00"
        )
        data = result.to_dict()
        self.assertEqual(data["video_id"], "test123")
        self.assertEqual(data["status"], "completed")
        self.assertEqual(data["video_url"], "https://example.com/video.mp4")
        self.assertEqual(data["duration"], 60.5)


class TestHeyGenClientInit(unittest.TestCase):
    """Tests for HeyGen client initialization."""

    def test_init_with_params(self):
        """Test initialization with explicit parameters."""
        client = HeyGenClient(api_key="test_key", avatar_id="test_avatar")
        self.assertEqual(client.api_key, "test_key")
        self.assertEqual(client.avatar_id, "test_avatar")

    def test_init_from_env(self):
        """Test initialization from environment variables."""
        with patch.dict(os.environ, {
            "HEYGEN_API_KEY": "env_key",
            "HEYGEN_AVATAR_ID": "env_avatar"
        }):
            client = HeyGenClient()
            self.assertEqual(client.api_key, "env_key")
            self.assertEqual(client.avatar_id, "env_avatar")

    def test_init_missing_api_key(self):
        """Test initialization fails without API key."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("HEYGEN_API_KEY", None)
            with self.assertRaises(ValueError) as context:
                HeyGenClient()
            self.assertIn("HEYGEN_API_KEY", str(context.exception))

    def test_headers_contain_api_key(self):
        """Test that headers include API key."""
        client = HeyGenClient(api_key="test_key", avatar_id="test_avatar")
        headers = client._get_headers()
        self.assertEqual(headers["X-Api-Key"], "test_key")
        self.assertEqual(headers["Content-Type"], "application/json")


class TestFeature29CreateVideo(unittest.TestCase):
    """
    Feature #29: HeyGen integration can create video from script

    Steps:
    - Provide video script text
    - Provide job snapshot URL
    - Call HeyGen API to create video
    - Verify video_id is returned
    """

    def setUp(self):
        self.client = HeyGenClient(api_key="test_key", avatar_id="test_avatar")
        self.sample_script = """Hi there! I noticed you're looking for help with AI automation.

In my experience building AI automation systems, I've delivered similar solutions.

I'd love to discuss your specific needs. Would you be available for a quick call?

Best regards,
Clyde"""

    @patch('executions.upwork_heygen_video.requests.post')
    def test_create_video_success(self, mock_post):
        """Test successful video creation returns video_id."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "video_id": "abc123xyz"
            }
        }
        mock_post.return_value = mock_response

        result = self.client.create_video(
            script=self.sample_script,
            background_url="https://example.com/snapshot.png"
        )

        # Verify video_id is returned (Feature #29 requirement)
        self.assertEqual(result.video_id, "abc123xyz")
        self.assertEqual(result.status, "pending")
        self.assertIsNone(result.error)

    @patch('executions.upwork_heygen_video.requests.post')
    def test_create_video_api_call_format(self, mock_post):
        """Test API call is made with correct parameters."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"video_id": "test123"}}
        mock_post.return_value = mock_response

        self.client.create_video(
            script=self.sample_script,
            background_url="https://example.com/job.png"
        )

        # Verify API was called
        mock_post.assert_called_once()
        call_args = mock_post.call_args

        # Verify endpoint
        self.assertIn("/v2/video/generate", call_args[0][0])

        # Verify headers include API key
        headers = call_args[1]["headers"]
        self.assertEqual(headers["X-Api-Key"], "test_key")

        # Verify payload structure
        payload = call_args[1]["json"]
        self.assertIn("video_inputs", payload)
        self.assertIn("dimension", payload)

    @patch('executions.upwork_heygen_video.requests.post')
    def test_create_video_handles_api_error(self, mock_post):
        """Test handling of API errors."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"
        mock_post.return_value = mock_response

        result = self.client.create_video(script=self.sample_script)

        self.assertEqual(result.status, "failed")
        self.assertIn("400", result.error)
        self.assertEqual(result.video_id, "")

    @patch('executions.upwork_heygen_video.requests.post')
    def test_create_video_handles_api_error_in_response(self, mock_post):
        """Test handling of errors in API response body."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "error": {
                "message": "Invalid avatar ID"
            }
        }
        mock_post.return_value = mock_response

        result = self.client.create_video(script=self.sample_script)

        self.assertEqual(result.status, "failed")
        self.assertIn("Invalid avatar ID", result.error)


class TestFeature30PollCompletion(unittest.TestCase):
    """
    Feature #30: HeyGen integration can poll for video completion

    Steps:
    - Start video generation
    - Poll status endpoint until completion
    - Verify final status is 'completed'
    - Verify video_url is returned
    """

    def setUp(self):
        self.client = HeyGenClient(api_key="test_key", avatar_id="test_avatar")

    @patch('executions.upwork_heygen_video.requests.get')
    def test_get_video_status_completed(self, mock_get):
        """Test getting status of completed video."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "status": "completed",
                "video_url": "https://heygen.com/videos/abc123.mp4",
                "thumbnail_url": "https://heygen.com/thumbs/abc123.jpg",
                "duration": 65.5
            }
        }
        mock_get.return_value = mock_response

        result = self.client.get_video_status("abc123")

        # Verify completed status and video_url (Feature #30 requirements)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.video_url, "https://heygen.com/videos/abc123.mp4")
        self.assertIsNotNone(result.thumbnail_url)
        self.assertEqual(result.duration, 65.5)

    @patch('executions.upwork_heygen_video.requests.get')
    def test_get_video_status_processing(self, mock_get):
        """Test getting status of processing video."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "status": "processing"
            }
        }
        mock_get.return_value = mock_response

        result = self.client.get_video_status("abc123")

        self.assertEqual(result.status, "processing")
        self.assertIsNone(result.video_url)

    @patch('executions.upwork_heygen_video.requests.get')
    @patch('executions.upwork_heygen_video.time.sleep')
    def test_poll_for_completion_success(self, mock_sleep, mock_get):
        """Test polling until completion."""
        # First call: processing, second call: completed
        mock_response_processing = Mock()
        mock_response_processing.status_code = 200
        mock_response_processing.json.return_value = {"data": {"status": "processing"}}

        mock_response_completed = Mock()
        mock_response_completed.status_code = 200
        mock_response_completed.json.return_value = {
            "data": {
                "status": "completed",
                "video_url": "https://heygen.com/video.mp4"
            }
        }

        mock_get.side_effect = [mock_response_processing, mock_response_completed]

        result = self.client.poll_for_completion(
            video_id="abc123",
            poll_interval=1,
            max_poll_time=60
        )

        # Verify final status is completed and video_url returned
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.video_url, "https://heygen.com/video.mp4")
        self.assertEqual(result.poll_count, 2)

        # Verify sleep was called
        mock_sleep.assert_called_once_with(1)

    @patch('executions.upwork_heygen_video.requests.get')
    @patch('executions.upwork_heygen_video.time.sleep')
    @patch('executions.upwork_heygen_video.time.time')
    def test_poll_for_completion_timeout(self, mock_time, mock_sleep, mock_get):
        """Test polling timeout protection."""
        # Always return processing
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"status": "processing"}}
        mock_get.return_value = mock_response

        # Simulate time passing beyond timeout
        mock_time.side_effect = [0, 10, 20, 35]  # Exceeds 30 second timeout

        result = self.client.poll_for_completion(
            video_id="abc123",
            poll_interval=10,
            max_poll_time=30
        )

        # Verify timeout with error message
        self.assertEqual(result.status, "failed")
        self.assertIn("Timeout", result.error)

    @patch('executions.upwork_heygen_video.requests.get')
    def test_poll_for_completion_failure(self, mock_get):
        """Test handling of failed video generation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "status": "failed",
                "error": "Generation failed"
            }
        }
        mock_get.return_value = mock_response

        result = self.client.poll_for_completion(video_id="abc123")

        self.assertEqual(result.status, "failed")


class TestFeature31AvatarID(unittest.TestCase):
    """
    Feature #31: HeyGen video uses correct avatar ID from environment

    Steps:
    - Set HEYGEN_AVATAR_ID in environment
    - Run video generation
    - Verify API request includes correct avatar_id
    """

    @patch('executions.upwork_heygen_video.requests.post')
    def test_uses_avatar_from_env(self, mock_post):
        """Test avatar ID is read from environment."""
        with patch.dict(os.environ, {
            "HEYGEN_API_KEY": "test_key",
            "HEYGEN_AVATAR_ID": "env_avatar_123"
        }):
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": {"video_id": "test"}}
            mock_post.return_value = mock_response

            client = HeyGenClient()
            client.create_video(script="Test script")

            # Verify avatar_id from environment is in the request
            call_args = mock_post.call_args
            payload = call_args[1]["json"]
            avatar_id = payload["video_inputs"][0]["character"]["avatar_id"]
            self.assertEqual(avatar_id, "env_avatar_123")

    @patch('executions.upwork_heygen_video.requests.post')
    def test_avatar_param_overrides_env(self, mock_post):
        """Test explicit avatar_id parameter overrides environment."""
        with patch.dict(os.environ, {
            "HEYGEN_API_KEY": "test_key",
            "HEYGEN_AVATAR_ID": "env_avatar"
        }):
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": {"video_id": "test"}}
            mock_post.return_value = mock_response

            client = HeyGenClient()
            client.create_video(script="Test script", avatar_id="override_avatar")

            # Verify override avatar_id is used
            call_args = mock_post.call_args
            payload = call_args[1]["json"]
            avatar_id = payload["video_inputs"][0]["character"]["avatar_id"]
            self.assertEqual(avatar_id, "override_avatar")

    def test_raises_without_avatar_id(self):
        """Test error raised when no avatar_id available."""
        with patch.dict(os.environ, {"HEYGEN_API_KEY": "test_key"}, clear=True):
            os.environ.pop("HEYGEN_AVATAR_ID", None)
            client = HeyGenClient()

            with self.assertRaises(ValueError) as context:
                client.create_video(script="Test script")
            self.assertIn("avatar_id", str(context.exception))


class TestFeature32JobSnapshot(unittest.TestCase):
    """
    Feature #32: HeyGen video uses job snapshot as background

    Steps:
    - Generate job snapshot screenshot
    - Upload to cloud storage
    - Create HeyGen video with background parameter
    - Verify background.url matches uploaded screenshot
    """

    @patch('executions.upwork_heygen_video.requests.post')
    def test_background_url_in_request(self, mock_post):
        """Test job snapshot URL is included as background."""
        client = HeyGenClient(api_key="test_key", avatar_id="test_avatar")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"video_id": "test"}}
        mock_post.return_value = mock_response

        snapshot_url = "https://storage.example.com/snapshots/job_123.png"
        client.create_video(
            script="Test script",
            background_url=snapshot_url
        )

        # Verify background parameter in request
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        background = payload["video_inputs"][0]["background"]

        self.assertEqual(background["type"], "image")
        self.assertEqual(background["url"], snapshot_url)

    @patch('executions.upwork_heygen_video.requests.post')
    def test_default_background_without_snapshot(self, mock_post):
        """Test default background when no snapshot provided."""
        client = HeyGenClient(api_key="test_key", avatar_id="test_avatar")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"video_id": "test"}}
        mock_post.return_value = mock_response

        client.create_video(script="Test script")

        # Verify default color background
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        background = payload["video_inputs"][0]["background"]

        self.assertEqual(background["type"], "color")
        self.assertIn("value", background)


class TestCreateVideoAndWait(unittest.TestCase):
    """Tests for combined create and wait functionality."""

    def setUp(self):
        self.client = HeyGenClient(api_key="test_key", avatar_id="test_avatar")

    @patch('executions.upwork_heygen_video.requests.get')
    @patch('executions.upwork_heygen_video.requests.post')
    @patch('executions.upwork_heygen_video.time.sleep')
    def test_create_and_wait_success(self, mock_sleep, mock_post, mock_get):
        """Test full create and wait workflow."""
        # Create response
        mock_post_response = Mock()
        mock_post_response.status_code = 200
        mock_post_response.json.return_value = {"data": {"video_id": "abc123"}}
        mock_post.return_value = mock_post_response

        # Status response
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            "data": {
                "status": "completed",
                "video_url": "https://heygen.com/video.mp4"
            }
        }
        mock_get.return_value = mock_get_response

        result = self.client.create_video_and_wait(
            script="Test script",
            background_url="https://example.com/snapshot.png"
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.video_url, "https://heygen.com/video.mp4")

    @patch('executions.upwork_heygen_video.requests.post')
    def test_create_failure_no_wait(self, mock_post):
        """Test early exit when create fails."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Server error"
        mock_post.return_value = mock_response

        result = self.client.create_video_and_wait(script="Test")

        self.assertEqual(result.status, "failed")
        self.assertIn("500", result.error)


class TestConvenienceFunctions(unittest.TestCase):
    """Tests for module-level convenience functions."""

    @patch('executions.upwork_heygen_video.HeyGenClient')
    def test_create_heygen_video_function(self, mock_client_class):
        """Test create_heygen_video convenience function."""
        mock_client = Mock()
        mock_client.create_video_and_wait.return_value = VideoGenerationResult(
            video_id="test",
            status="completed",
            video_url="https://example.com/video.mp4",
            created_at=""
        )
        mock_client_class.return_value = mock_client

        with patch.dict(os.environ, {
            "HEYGEN_API_KEY": "test_key",
            "HEYGEN_AVATAR_ID": "test_avatar"
        }):
            result = create_heygen_video(
                script="Test script",
                job_snapshot_url="https://example.com/snapshot.png"
            )

            self.assertEqual(result.status, "completed")
            self.assertEqual(result.video_url, "https://example.com/video.mp4")


class TestAsyncClient(unittest.TestCase):
    """Tests for async HeyGen client."""

    def test_async_client_init(self):
        """Test async client initialization."""
        with patch.dict(os.environ, {
            "HEYGEN_API_KEY": "test_key",
            "HEYGEN_AVATAR_ID": "test_avatar"
        }):
            client = AsyncHeyGenClient()
            self.assertEqual(client.api_key, "test_key")
            self.assertEqual(client.avatar_id, "test_avatar")


class TestFeature78TimeoutProtection(unittest.TestCase):
    """
    Feature #78: HeyGen video polling has timeout protection

    Steps:
    - Start video generation
    - Set max poll timeout to 5 minutes
    - Simulate slow video generation
    - Verify timeout is triggered after limit
    """

    def test_default_max_poll_time_is_5_minutes(self):
        """Test that DEFAULT_MAX_POLL_TIME is 5 minutes (300 seconds)."""
        self.assertEqual(DEFAULT_MAX_POLL_TIME, 300)
        # 300 seconds = 5 minutes
        self.assertEqual(DEFAULT_MAX_POLL_TIME / 60, 5)

    @patch('executions.upwork_heygen_video.requests.get')
    @patch('executions.upwork_heygen_video.time.sleep')
    @patch('executions.upwork_heygen_video.time.time')
    def test_timeout_triggered_after_max_poll_time(self, mock_time, mock_sleep, mock_get):
        """Test that timeout is triggered after max_poll_time elapsed."""
        client = HeyGenClient(api_key="test_key", avatar_id="test_avatar")

        # Always return processing status (slow video generation)
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"status": "processing"}}
        mock_get.return_value = mock_response

        # Simulate time passing: start=0, then 100, 200, 310 (exceeds 300)
        mock_time.side_effect = [0, 100, 200, 310]

        result = client.poll_for_completion(
            video_id="slow_video_123",
            poll_interval=100,
            max_poll_time=300  # 5 minutes
        )

        # Verify timeout is triggered
        self.assertEqual(result.status, "failed")
        self.assertIn("Timeout", result.error)
        self.assertIn("300", result.error)  # Should mention the timeout value

    @patch('executions.upwork_heygen_video.requests.get')
    @patch('executions.upwork_heygen_video.time.sleep')
    @patch('executions.upwork_heygen_video.time.time')
    def test_timeout_includes_poll_count_in_error(self, mock_time, mock_sleep, mock_get):
        """Test that timeout error includes poll count."""
        client = HeyGenClient(api_key="test_key", avatar_id="test_avatar")

        # Always return processing
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"status": "processing"}}
        mock_get.return_value = mock_response

        # Simulate 3 polls before timeout (0, 10, 20, 35 exceeds 30)
        mock_time.side_effect = [0, 10, 20, 35]

        result = client.poll_for_completion(
            video_id="test_video",
            poll_interval=10,
            max_poll_time=30
        )

        # Verify poll count is in result and error message
        self.assertEqual(result.poll_count, 3)
        self.assertIn("3 polls", result.error)

    @patch('executions.upwork_heygen_video.requests.get')
    @patch('executions.upwork_heygen_video.time.sleep')
    @patch('executions.upwork_heygen_video.time.time')
    def test_timeout_result_has_correct_structure(self, mock_time, mock_sleep, mock_get):
        """Test that timeout result has correct VideoGenerationResult structure."""
        client = HeyGenClient(api_key="test_key", avatar_id="test_avatar")

        # Always return processing
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"status": "processing"}}
        mock_get.return_value = mock_response

        # Timeout immediately
        mock_time.side_effect = [0, 100]

        result = client.poll_for_completion(
            video_id="timeout_test",
            poll_interval=10,
            max_poll_time=50
        )

        # Verify result structure
        self.assertIsInstance(result, VideoGenerationResult)
        self.assertEqual(result.video_id, "timeout_test")
        self.assertEqual(result.status, "failed")
        self.assertIsNotNone(result.error)
        self.assertIsNone(result.video_url)
        self.assertGreater(result.poll_count, 0)

    @patch('executions.upwork_heygen_video.requests.get')
    @patch('executions.upwork_heygen_video.time.sleep')
    @patch('executions.upwork_heygen_video.time.time')
    def test_completion_before_timeout(self, mock_time, mock_sleep, mock_get):
        """Test that completion before timeout returns success, not timeout."""
        client = HeyGenClient(api_key="test_key", avatar_id="test_avatar")

        # First call processing, second call completed
        mock_response_processing = Mock()
        mock_response_processing.status_code = 200
        mock_response_processing.json.return_value = {"data": {"status": "processing"}}

        mock_response_completed = Mock()
        mock_response_completed.status_code = 200
        mock_response_completed.json.return_value = {
            "data": {
                "status": "completed",
                "video_url": "https://heygen.com/video.mp4"
            }
        }

        mock_get.side_effect = [mock_response_processing, mock_response_completed]

        # Time is still within limit when completed
        mock_time.side_effect = [0, 50, 100]  # All within 300 second timeout

        result = client.poll_for_completion(
            video_id="test_video",
            poll_interval=50,
            max_poll_time=300
        )

        # Verify success, not timeout
        self.assertEqual(result.status, "completed")
        self.assertIsNone(result.error)
        self.assertEqual(result.video_url, "https://heygen.com/video.mp4")

    def test_max_poll_time_parameter_passed_to_create_video_and_wait(self):
        """Test that max_poll_time can be customized in create_video_and_wait."""
        client = HeyGenClient(api_key="test_key", avatar_id="test_avatar")

        # Verify the method signature accepts max_poll_time
        import inspect
        sig = inspect.signature(client.create_video_and_wait)
        params = sig.parameters

        self.assertIn('max_poll_time', params)
        # Verify default is DEFAULT_MAX_POLL_TIME
        self.assertEqual(params['max_poll_time'].default, DEFAULT_MAX_POLL_TIME)


class TestVideoDimensions(unittest.TestCase):
    """Tests for video dimension settings."""

    @patch('executions.upwork_heygen_video.requests.post')
    def test_default_dimensions(self, mock_post):
        """Test default 1920x1080 dimensions."""
        client = HeyGenClient(api_key="test_key", avatar_id="test_avatar")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"video_id": "test"}}
        mock_post.return_value = mock_response

        client.create_video(script="Test")

        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        dimension = payload["dimension"]

        self.assertEqual(dimension["width"], DEFAULT_WIDTH)
        self.assertEqual(dimension["height"], DEFAULT_HEIGHT)

    @patch('executions.upwork_heygen_video.requests.post')
    def test_custom_dimensions(self, mock_post):
        """Test custom video dimensions."""
        client = HeyGenClient(api_key="test_key", avatar_id="test_avatar")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"video_id": "test"}}
        mock_post.return_value = mock_response

        client.create_video(script="Test", width=1280, height=720)

        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        dimension = payload["dimension"]

        self.assertEqual(dimension["width"], 1280)
        self.assertEqual(dimension["height"], 720)


def run_tests():
    """Run all tests and print summary."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestVideoGenerationResult))
    suite.addTests(loader.loadTestsFromTestCase(TestHeyGenClientInit))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature29CreateVideo))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature30PollCompletion))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature31AvatarID))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature32JobSnapshot))
    suite.addTests(loader.loadTestsFromTestCase(TestCreateVideoAndWait))
    suite.addTests(loader.loadTestsFromTestCase(TestConvenienceFunctions))
    suite.addTests(loader.loadTestsFromTestCase(TestAsyncClient))
    suite.addTests(loader.loadTestsFromTestCase(TestFeature78TimeoutProtection))
    suite.addTests(loader.loadTestsFromTestCase(TestVideoDimensions))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Print summary
    print("\n" + "="*60)
    print("FEATURE TEST SUMMARY")
    print("="*60)

    features = {
        29: "HeyGen integration can create video from script",
        30: "HeyGen integration can poll for video completion",
        31: "HeyGen video uses correct avatar ID from environment",
        32: "HeyGen video uses job snapshot as background",
        78: "HeyGen video polling has timeout protection"
    }

    feature_tests = {
        29: TestFeature29CreateVideo,
        30: TestFeature30PollCompletion,
        31: TestFeature31AvatarID,
        32: TestFeature32JobSnapshot,
        78: TestFeature78TimeoutProtection
    }

    all_passed = True
    for feature_id, description in features.items():
        test_class = feature_tests[feature_id]
        test_names = [name for name in dir(test_class) if name.startswith('test_')]
        failures = [f for f in result.failures + result.errors
                   if f[0].__class__ == test_class]
        passed = len(failures) == 0 and len(test_names) > 0

        status = "PASS" if passed else "FAIL"
        print(f"Feature #{feature_id}: {status}")
        print(f"  {description}")
        print(f"  Tests: {len(test_names)}, Failures: {len(failures)}")

        if not passed:
            all_passed = False

    print("="*60)
    print(f"Overall: {'ALL FEATURES PASS' if all_passed else 'SOME FEATURES FAILED'}")
    print("="*60)

    return all_passed


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
