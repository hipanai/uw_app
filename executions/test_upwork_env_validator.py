#!/usr/bin/env python3
"""
Unit tests for upwork_env_validator.py

Tests environment variable validation for the Upwork Auto-Apply Pipeline.
"""

import os
import sys
import unittest
from unittest.mock import patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from upwork_env_validator import (
    EnvVar,
    ValidationResult,
    UPWORK_ENV_VARS,
    get_env_vars_for_module,
    validate_env,
    require_env,
    check_env,
)


class TestEnvVarDataclass(unittest.TestCase):
    """Tests for EnvVar dataclass."""

    def test_create_required_env_var(self):
        """Test creating a required environment variable."""
        var = EnvVar(
            name="TEST_VAR",
            description="A test variable",
            required=True
        )
        self.assertEqual(var.name, "TEST_VAR")
        self.assertEqual(var.description, "A test variable")
        self.assertTrue(var.required)
        self.assertIsNone(var.default)

    def test_create_optional_env_var_with_default(self):
        """Test creating an optional env var with default."""
        var = EnvVar(
            name="TEST_VAR",
            description="A test variable",
            required=False,
            default="default_value"
        )
        self.assertFalse(var.required)
        self.assertEqual(var.default, "default_value")

    def test_modules_default_to_empty_set(self):
        """Test that modules defaults to empty set."""
        var = EnvVar(name="TEST", description="Test")
        self.assertEqual(var.modules, set())

    def test_modules_assigned_correctly(self):
        """Test that modules are assigned correctly."""
        var = EnvVar(
            name="TEST",
            description="Test",
            modules={"prefilter", "pipeline"}
        )
        self.assertIn("prefilter", var.modules)
        self.assertIn("pipeline", var.modules)


class TestValidationResultDataclass(unittest.TestCase):
    """Tests for ValidationResult dataclass."""

    def test_valid_result(self):
        """Test creating a valid result."""
        result = ValidationResult(
            valid=True,
            missing=[],
            present=["VAR1", "VAR2"],
            warnings=[],
            errors=[]
        )
        self.assertTrue(result.valid)
        self.assertEqual(len(result.present), 2)
        self.assertEqual(len(result.missing), 0)

    def test_invalid_result(self):
        """Test creating an invalid result."""
        result = ValidationResult(
            valid=False,
            missing=["MISSING_VAR"],
            present=["VAR1"],
            warnings=["Optional not set: OPT_VAR"],
            errors=["Missing required: MISSING_VAR"]
        )
        self.assertFalse(result.valid)
        self.assertEqual(len(result.missing), 1)
        self.assertEqual(len(result.errors), 1)


class TestUpworkEnvVarsDefinitions(unittest.TestCase):
    """Tests for the UPWORK_ENV_VARS definitions."""

    def test_anthropic_api_key_defined(self):
        """Test ANTHROPIC_API_KEY is defined."""
        var = next((v for v in UPWORK_ENV_VARS if v.name == "ANTHROPIC_API_KEY"), None)
        self.assertIsNotNone(var)
        self.assertTrue(var.required)
        self.assertIn("prefilter", var.modules)

    def test_heygen_api_key_defined(self):
        """Test HEYGEN_API_KEY is defined."""
        var = next((v for v in UPWORK_ENV_VARS if v.name == "HEYGEN_API_KEY"), None)
        self.assertIsNotNone(var)
        self.assertTrue(var.required)
        self.assertIn("heygen", var.modules)

    def test_heygen_avatar_id_defined(self):
        """Test HEYGEN_AVATAR_ID is defined."""
        var = next((v for v in UPWORK_ENV_VARS if v.name == "HEYGEN_AVATAR_ID"), None)
        self.assertIsNotNone(var)
        self.assertTrue(var.required)

    def test_slack_bot_token_defined(self):
        """Test SLACK_BOT_TOKEN is defined."""
        var = next((v for v in UPWORK_ENV_VARS if v.name == "SLACK_BOT_TOKEN"), None)
        self.assertIsNotNone(var)
        self.assertTrue(var.required)
        self.assertIn("slack", var.modules)

    def test_slack_signing_secret_defined(self):
        """Test SLACK_SIGNING_SECRET is defined."""
        var = next((v for v in UPWORK_ENV_VARS if v.name == "SLACK_SIGNING_SECRET"), None)
        self.assertIsNotNone(var)
        self.assertTrue(var.required)

    def test_slack_approval_channel_defined(self):
        """Test SLACK_APPROVAL_CHANNEL is defined."""
        var = next((v for v in UPWORK_ENV_VARS if v.name == "SLACK_APPROVAL_CHANNEL"), None)
        self.assertIsNotNone(var)
        self.assertTrue(var.required)

    def test_slack_webhook_url_is_optional(self):
        """Test SLACK_WEBHOOK_URL is optional."""
        var = next((v for v in UPWORK_ENV_VARS if v.name == "SLACK_WEBHOOK_URL"), None)
        self.assertIsNotNone(var)
        self.assertFalse(var.required)

    def test_upwork_pipeline_sheet_id_defined(self):
        """Test UPWORK_PIPELINE_SHEET_ID is defined."""
        var = next((v for v in UPWORK_ENV_VARS if v.name == "UPWORK_PIPELINE_SHEET_ID"), None)
        self.assertIsNotNone(var)
        self.assertTrue(var.required)

    def test_upwork_processed_ids_sheet_id_defined(self):
        """Test UPWORK_PROCESSED_IDS_SHEET_ID is defined."""
        var = next((v for v in UPWORK_ENV_VARS if v.name == "UPWORK_PROCESSED_IDS_SHEET_ID"), None)
        self.assertIsNotNone(var)
        self.assertTrue(var.required)

    def test_apify_api_token_defined(self):
        """Test APIFY_API_TOKEN is defined."""
        var = next((v for v in UPWORK_ENV_VARS if v.name == "APIFY_API_TOKEN"), None)
        self.assertIsNotNone(var)
        self.assertTrue(var.required)

    def test_prefilter_min_score_has_default(self):
        """Test PREFILTER_MIN_SCORE has default value."""
        var = next((v for v in UPWORK_ENV_VARS if v.name == "PREFILTER_MIN_SCORE"), None)
        self.assertIsNotNone(var)
        self.assertFalse(var.required)
        self.assertEqual(var.default, "70")

    def test_google_application_credentials_has_default(self):
        """Test GOOGLE_APPLICATION_CREDENTIALS has default."""
        var = next((v for v in UPWORK_ENV_VARS if v.name == "GOOGLE_APPLICATION_CREDENTIALS"), None)
        self.assertIsNotNone(var)
        self.assertEqual(var.default, "config/credentials.json")

    def test_all_vars_have_descriptions(self):
        """Test all variables have descriptions."""
        for var in UPWORK_ENV_VARS:
            self.assertTrue(len(var.description) > 0, f"{var.name} missing description")


class TestGetEnvVarsForModule(unittest.TestCase):
    """Tests for get_env_vars_for_module function."""

    def test_get_all_vars_when_no_module(self):
        """Test getting all vars when no module specified."""
        vars = get_env_vars_for_module(None)
        self.assertEqual(vars, UPWORK_ENV_VARS)

    def test_get_prefilter_module_vars(self):
        """Test getting vars for prefilter module."""
        vars = get_env_vars_for_module("prefilter")
        names = [v.name for v in vars]
        self.assertIn("ANTHROPIC_API_KEY", names)
        self.assertIn("PREFILTER_MIN_SCORE", names)

    def test_get_slack_module_vars(self):
        """Test getting vars for slack module."""
        vars = get_env_vars_for_module("slack")
        names = [v.name for v in vars]
        self.assertIn("SLACK_BOT_TOKEN", names)
        self.assertIn("SLACK_APPROVAL_CHANNEL", names)

    def test_get_heygen_module_vars(self):
        """Test getting vars for heygen module."""
        vars = get_env_vars_for_module("heygen")
        names = [v.name for v in vars]
        self.assertIn("HEYGEN_API_KEY", names)
        self.assertIn("HEYGEN_AVATAR_ID", names)

    def test_get_pipeline_module_vars(self):
        """Test getting vars for pipeline module."""
        vars = get_env_vars_for_module("pipeline")
        names = [v.name for v in vars]
        self.assertIn("ANTHROPIC_API_KEY", names)
        self.assertIn("SLACK_BOT_TOKEN", names)
        self.assertIn("UPWORK_PIPELINE_SHEET_ID", names)


class TestValidateEnv(unittest.TestCase):
    """Tests for validate_env function."""

    def test_validate_with_all_vars_present(self):
        """Test validation when all required vars are present."""
        test_env = {
            "ANTHROPIC_API_KEY": "test_key",
            "HEYGEN_API_KEY": "test_key",
            "HEYGEN_AVATAR_ID": "test_id",
            "SLACK_BOT_TOKEN": "xoxb-test",
            "SLACK_SIGNING_SECRET": "test_secret",
            "SLACK_APPROVAL_CHANNEL": "C12345",
            "UPWORK_PIPELINE_SHEET_ID": "sheet1",
            "UPWORK_PROCESSED_IDS_SHEET_ID": "sheet2",
            "GOOGLE_APPLICATION_CREDENTIALS": "config/creds.json",
            "APIFY_API_TOKEN": "apify_token",
        }

        with patch.dict(os.environ, test_env, clear=True):
            result = validate_env()
            self.assertTrue(result.valid)
            self.assertEqual(len(result.errors), 0)

    def test_validate_with_missing_required_vars(self):
        """Test validation when required vars are missing."""
        with patch.dict(os.environ, {}, clear=True):
            result = validate_env(strict=True)
            self.assertFalse(result.valid)
            self.assertTrue(len(result.missing) > 0)
            self.assertTrue(len(result.errors) > 0)

    def test_validate_uses_defaults(self):
        """Test that validation uses default values."""
        test_env = {
            "ANTHROPIC_API_KEY": "test_key",
            "HEYGEN_API_KEY": "test_key",
            "HEYGEN_AVATAR_ID": "test_id",
            "SLACK_BOT_TOKEN": "xoxb-test",
            "SLACK_SIGNING_SECRET": "test_secret",
            "SLACK_APPROVAL_CHANNEL": "C12345",
            "UPWORK_PIPELINE_SHEET_ID": "sheet1",
            "UPWORK_PROCESSED_IDS_SHEET_ID": "sheet2",
            "APIFY_API_TOKEN": "apify_token",
            # GOOGLE_APPLICATION_CREDENTIALS not set - should use default
            # PREFILTER_MIN_SCORE not set - should use default
        }

        with patch.dict(os.environ, test_env, clear=True):
            result = validate_env()
            # Should be valid because defaults are used
            present_with_defaults = [p for p in result.present if "default" in p.lower()]
            self.assertTrue(len(present_with_defaults) > 0)

    def test_validate_specific_module(self):
        """Test validation for a specific module."""
        test_env = {
            "HEYGEN_API_KEY": "test_key",
            "HEYGEN_AVATAR_ID": "test_id",
        }

        with patch.dict(os.environ, test_env, clear=True):
            result = validate_env(module="heygen")
            self.assertTrue(result.valid)


class TestRequireEnv(unittest.TestCase):
    """Tests for require_env function."""

    def test_require_env_returns_values(self):
        """Test that require_env returns the values."""
        with patch.dict(os.environ, {"VAR1": "value1", "VAR2": "value2"}):
            result = require_env("VAR1", "VAR2")
            self.assertEqual(result["VAR1"], "value1")
            self.assertEqual(result["VAR2"], "value2")

    def test_require_env_raises_on_missing(self):
        """Test that require_env raises error on missing vars."""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(EnvironmentError) as context:
                require_env("MISSING_VAR")
            self.assertIn("MISSING_VAR", str(context.exception))

    def test_require_env_uses_defaults(self):
        """Test that require_env uses defaults from UPWORK_ENV_VARS."""
        with patch.dict(os.environ, {}, clear=True):
            result = require_env("PREFILTER_MIN_SCORE")
            self.assertEqual(result["PREFILTER_MIN_SCORE"], "70")

    def test_require_env_with_mixed_present_missing(self):
        """Test require_env with some present and some missing."""
        with patch.dict(os.environ, {"VAR1": "value1"}, clear=True):
            with self.assertRaises(EnvironmentError):
                require_env("VAR1", "MISSING_VAR")


class TestCheckEnv(unittest.TestCase):
    """Tests for check_env function."""

    def test_check_env_returns_true_when_valid(self):
        """Test check_env returns True when all required vars present."""
        test_env = {
            "ANTHROPIC_API_KEY": "test_key",
            "HEYGEN_API_KEY": "test_key",
            "HEYGEN_AVATAR_ID": "test_id",
            "SLACK_BOT_TOKEN": "xoxb-test",
            "SLACK_SIGNING_SECRET": "test_secret",
            "SLACK_APPROVAL_CHANNEL": "C12345",
            "UPWORK_PIPELINE_SHEET_ID": "sheet1",
            "UPWORK_PROCESSED_IDS_SHEET_ID": "sheet2",
            "GOOGLE_APPLICATION_CREDENTIALS": "config/creds.json",
            "APIFY_API_TOKEN": "apify_token",
        }

        with patch.dict(os.environ, test_env, clear=True):
            # Capture stdout to suppress output
            from io import StringIO
            with patch('sys.stdout', new_callable=StringIO):
                result = check_env()
            self.assertTrue(result)

    def test_check_env_returns_false_when_invalid(self):
        """Test check_env returns False when required vars missing."""
        with patch.dict(os.environ, {}, clear=True):
            from io import StringIO
            with patch('sys.stdout', new_callable=StringIO):
                result = check_env()
            self.assertFalse(result)

    def test_check_env_for_module(self):
        """Test check_env for specific module."""
        test_env = {
            "ANTHROPIC_API_KEY": "test_key",
        }

        with patch.dict(os.environ, test_env, clear=True):
            from io import StringIO
            with patch('sys.stdout', new_callable=StringIO):
                result = check_env("prefilter")
            self.assertTrue(result)


class TestEnvExampleDocumentation(unittest.TestCase):
    """Tests to verify .env.example is properly documented."""

    def test_env_example_exists(self):
        """Test that .env.example file exists."""
        env_example_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            ".env.example"
        )
        self.assertTrue(os.path.exists(env_example_path))

    def test_env_example_contains_all_required_vars(self):
        """Test that .env.example contains all required vars."""
        env_example_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            ".env.example"
        )

        with open(env_example_path, "r") as f:
            content = f.read()

        for var in UPWORK_ENV_VARS:
            if var.required:
                self.assertIn(
                    var.name,
                    content,
                    f"Required var {var.name} not in .env.example"
                )

    def test_env_example_documents_heygen_vars(self):
        """Test HEYGEN vars are documented in .env.example."""
        env_example_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            ".env.example"
        )

        with open(env_example_path, "r") as f:
            content = f.read()

        self.assertIn("HEYGEN_API_KEY", content)
        self.assertIn("HEYGEN_AVATAR_ID", content)

    def test_env_example_documents_slack_vars(self):
        """Test SLACK vars are documented in .env.example."""
        env_example_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            ".env.example"
        )

        with open(env_example_path, "r") as f:
            content = f.read()

        self.assertIn("SLACK_BOT_TOKEN", content)
        self.assertIn("SLACK_SIGNING_SECRET", content)
        self.assertIn("SLACK_APPROVAL_CHANNEL", content)


class TestValidationIntegration(unittest.TestCase):
    """Integration tests for validation workflow."""

    def test_validate_env_strict_mode(self):
        """Test strict mode behavior."""
        with patch.dict(os.environ, {}, clear=True):
            result = validate_env(strict=True)
            self.assertFalse(result.valid)
            self.assertTrue(len(result.errors) > 0)

    def test_validate_env_non_strict_mode(self):
        """Test non-strict mode behavior."""
        with patch.dict(os.environ, {}, clear=True):
            result = validate_env(strict=False)
            # Still tracks missing but doesn't add to errors
            self.assertTrue(len(result.missing) > 0)


if __name__ == "__main__":
    unittest.main()
