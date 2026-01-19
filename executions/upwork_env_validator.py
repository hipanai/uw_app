#!/usr/bin/env python3
"""
Environment variable validator for Upwork Auto-Apply Pipeline.

Usage:
    python executions/upwork_env_validator.py          # Validate all required vars
    python executions/upwork_env_validator.py --check  # Check and print status
    python executions/upwork_env_validator.py --module prefilter  # Validate for specific module

Import in scripts:
    from upwork_env_validator import validate_env, require_env, check_env

Features:
- Validates required environment variables
- Module-specific validation
- Clear error messages with setup instructions
- Non-blocking check mode
"""

import os
import sys
from dataclasses import dataclass
from typing import List, Optional, Dict, Set


@dataclass
class EnvVar:
    """Definition of an environment variable."""
    name: str
    description: str
    required: bool = True
    default: Optional[str] = None
    modules: Optional[Set[str]] = None  # Which modules require this var
    example: Optional[str] = None

    def __post_init__(self):
        if self.modules is None:
            self.modules = set()


# Define all environment variables for the Upwork pipeline
UPWORK_ENV_VARS = [
    # Core AI
    EnvVar(
        name="ANTHROPIC_API_KEY",
        description="Anthropic API key for Claude AI (pre-filter, proposals, video scripts)",
        required=True,
        modules={"prefilter", "deliverable", "video_script", "boost_decider", "pipeline"},
        example="sk-ant-xxx"
    ),

    # HeyGen
    EnvVar(
        name="HEYGEN_API_KEY",
        description="HeyGen API key for video generation",
        required=True,
        modules={"heygen", "deliverable", "pipeline"},
        example="xxx"
    ),
    EnvVar(
        name="HEYGEN_AVATAR_ID",
        description="HeyGen avatar ID for video generation",
        required=True,
        modules={"heygen", "deliverable", "pipeline"},
        example="xxx"
    ),

    # Slack
    EnvVar(
        name="SLACK_BOT_TOKEN",
        description="Slack bot OAuth token (needs chat:write scope)",
        required=True,
        modules={"slack", "pipeline"},
        example="xoxb-xxx"
    ),
    EnvVar(
        name="SLACK_SIGNING_SECRET",
        description="Slack signing secret for webhook verification",
        required=True,
        modules={"slack", "webhook"},
        example="xxx"
    ),
    EnvVar(
        name="SLACK_APPROVAL_CHANNEL",
        description="Slack channel ID for approval messages",
        required=True,
        modules={"slack", "pipeline"},
        example="C0123456789"
    ),
    EnvVar(
        name="SLACK_WEBHOOK_URL",
        description="Slack webhook URL for notifications",
        required=False,
        modules={"webhook"},
        example="https://hooks.slack.com/services/xxx/xxx/xxx"
    ),

    # Google Sheets
    EnvVar(
        name="UPWORK_PIPELINE_SHEET_ID",
        description="Google Sheet ID for pipeline tracking",
        required=True,
        modules={"sheets", "pipeline", "slack"},
        example="xxx"
    ),
    EnvVar(
        name="UPWORK_PROCESSED_IDS_SHEET_ID",
        description="Google Sheet ID for deduplication tracking",
        required=True,
        modules={"sheets", "deduplicator", "pipeline"},
        example="xxx"
    ),
    EnvVar(
        name="GOOGLE_APPLICATION_CREDENTIALS",
        description="Path to Google OAuth credentials file",
        required=True,
        default="config/credentials.json",
        modules={"sheets", "gmail", "pipeline"},
        example="config/credentials.json"
    ),

    # Apify
    EnvVar(
        name="APIFY_API_TOKEN",
        description="Apify API token for job scraping",
        required=True,
        modules={"apify", "pipeline"},
        example="xxx"
    ),

    # Pipeline config
    EnvVar(
        name="PREFILTER_MIN_SCORE",
        description="Minimum pre-filter score (0-100) to proceed",
        required=False,
        default="70",
        modules={"prefilter", "pipeline"},
        example="70"
    ),
    EnvVar(
        name="DEBUG",
        description="Enable debug logging",
        required=False,
        modules=set(),
        example="1"
    ),

    # Playwright
    EnvVar(
        name="PLAYWRIGHT_USER_DATA_DIR",
        description="Path to persistent browser profile for Upwork auth",
        required=False,
        default=".browser_profile",
        modules={"submitter", "deep_extractor"},
        example=".browser_profile"
    ),
]


@dataclass
class ValidationResult:
    """Result of environment validation."""
    valid: bool
    missing: List[str]
    present: List[str]
    warnings: List[str]
    errors: List[str]


def get_env_vars_for_module(module: Optional[str] = None) -> List[EnvVar]:
    """Get environment variables required for a specific module or all."""
    if module is None:
        return UPWORK_ENV_VARS

    return [var for var in UPWORK_ENV_VARS
            if module in var.modules or not var.modules]


def validate_env(module: Optional[str] = None, strict: bool = True) -> ValidationResult:
    """
    Validate environment variables.

    Args:
        module: Optional module name to validate for
        strict: If True, treat missing required vars as errors

    Returns:
        ValidationResult with validation status
    """
    vars_to_check = get_env_vars_for_module(module)

    missing = []
    present = []
    warnings = []
    errors = []

    for var in vars_to_check:
        value = os.getenv(var.name)

        if value:
            present.append(var.name)
        elif var.default:
            present.append(f"{var.name} (using default: {var.default})")
        elif var.required:
            missing.append(var.name)
            if strict:
                errors.append(f"Missing required: {var.name} - {var.description}")
        else:
            warnings.append(f"Optional not set: {var.name}")

    return ValidationResult(
        valid=len(errors) == 0,
        missing=missing,
        present=present,
        warnings=warnings,
        errors=errors
    )


def require_env(*var_names: str) -> Dict[str, str]:
    """
    Require specific environment variables, raising error if missing.

    Args:
        *var_names: Names of required environment variables

    Returns:
        Dict of var_name -> value

    Raises:
        EnvironmentError: If any required variable is missing
    """
    result = {}
    missing = []

    for name in var_names:
        value = os.getenv(name)
        if value:
            result[name] = value
        else:
            # Check if there's a default
            var_def = next((v for v in UPWORK_ENV_VARS if v.name == name), None)
            if var_def and var_def.default:
                result[name] = var_def.default
            else:
                missing.append(name)

    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            f"See .env.example for setup instructions."
        )

    return result


def check_env(module: Optional[str] = None) -> bool:
    """
    Check environment variables and print status.
    Non-blocking version that returns True/False.

    Args:
        module: Optional module name to check for

    Returns:
        True if all required vars are present
    """
    result = validate_env(module, strict=False)

    print(f"\n{'='*60}")
    print(f"Environment Variable Check{f' (module: {module})' if module else ''}")
    print(f"{'='*60}\n")

    # Present
    if result.present:
        print("Present:")
        for var in result.present:
            print(f"  [OK] {var}")
        print()

    # Missing required
    if result.missing:
        print("Missing (REQUIRED):")
        for var in result.missing:
            var_def = next((v for v in UPWORK_ENV_VARS if v.name == var), None)
            if var_def:
                print(f"  [X] {var}")
                print(f"      Description: {var_def.description}")
                if var_def.example:
                    print(f"      Example: {var_def.example}")
            else:
                print(f"  [X] {var}")
        print()

    # Warnings
    if result.warnings:
        print("Optional (not set):")
        for warning in result.warnings:
            print(f"  [~] {warning}")
        print()

    # Summary
    print(f"{'='*60}")
    if result.valid:
        print("Status: All required variables present")
    else:
        print(f"Status: MISSING {len(result.missing)} required variable(s)")
        print("Run: cp .env.example .env && edit .env")
    print(f"{'='*60}\n")

    return result.valid


def validate_on_startup(module: Optional[str] = None):
    """
    Validate environment on startup, exiting if invalid.
    Call this at the start of scripts that need env validation.

    Args:
        module: Optional module name to validate for

    Raises:
        SystemExit: If validation fails
    """
    result = validate_env(module, strict=True)

    if not result.valid:
        print("\nEnvironment validation failed!", file=sys.stderr)
        for error in result.errors:
            print(f"  - {error}", file=sys.stderr)
        print("\nSee .env.example for setup instructions.", file=sys.stderr)
        sys.exit(1)


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Validate Upwork pipeline environment variables")
    parser.add_argument(
        "--check", "-c",
        action="store_true",
        help="Check and print status (non-blocking)"
    )
    parser.add_argument(
        "--module", "-m",
        choices=["prefilter", "deliverable", "heygen", "slack", "sheets",
                 "pipeline", "apify", "gmail", "submitter", "deep_extractor",
                 "webhook", "boost_decider", "deduplicator", "video_script"],
        help="Validate for specific module only"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List all environment variables"
    )
    parser.add_argument(
        "--strict", "-s",
        action="store_true",
        help="Exit with error if validation fails"
    )

    args = parser.parse_args()

    if args.list:
        print("\nUpwork Pipeline Environment Variables")
        print("=" * 60)
        for var in UPWORK_ENV_VARS:
            req = "Required" if var.required else "Optional"
            print(f"\n{var.name}")
            print(f"  {var.description}")
            print(f"  Status: {req}")
            if var.default:
                print(f"  Default: {var.default}")
            if var.modules:
                print(f"  Modules: {', '.join(sorted(var.modules))}")
            if var.example:
                print(f"  Example: {var.example}")
        print()
        return

    if args.check or not args.strict:
        valid = check_env(args.module)
        sys.exit(0 if valid else 1)
    else:
        validate_on_startup(args.module)
        print("All required environment variables present.")


if __name__ == "__main__":
    main()
