#!/usr/bin/env python3
"""
Upwork Browser Profile Security - Secure storage for Playwright browser profiles.

Feature #82: Ensures browser profiles are stored securely:
- Validates profile directory permissions
- Ensures session cookies are not exposed
- Verifies profile directories are in .gitignore
- Provides secure profile path configuration

Usage:
    from upwork_browser_profile_security import (
        get_secure_profile_path,
        validate_profile_security,
        ensure_profile_security,
    )

    # Get the secure profile path
    profile_path = get_secure_profile_path()

    # Validate existing profile security
    is_secure, issues = validate_profile_security(profile_path)

    # Ensure profile is secure (creates/fixes as needed)
    ensure_profile_security(profile_path)
"""

import os
import stat
import json
from pathlib import Path
from typing import Optional, Tuple, List
from dataclasses import dataclass


# Default profile directory names that should be in .gitignore
BROWSER_PROFILE_DIRS = [
    "browser_profile",
    "user_data",
    "playwright_profile",
    "upwork_profile",
    ".playwright",
]

# Files that contain sensitive session data
SENSITIVE_FILES = [
    "Cookies",
    "Cookies-journal",
    "Login Data",
    "Login Data-journal",
    "Web Data",
    "Web Data-journal",
    "Session Storage",
    "Local Storage",
    "IndexedDB",
]

# Required .gitignore patterns for browser profiles
REQUIRED_GITIGNORE_PATTERNS = [
    "browser_profile/",
    "user_data/",
    "playwright_profile/",
    "upwork_profile/",
    ".playwright/",
    "**/Default/Cookies",
    "**/Default/Cookies-journal",
    "**/Default/Login Data*",
    "**/Default/Session Storage/",
    "**/Default/Local Storage/",
]

# Secure directory permissions (owner read/write/execute only)
SECURE_DIR_MODE = 0o700

# Secure file permissions (owner read/write only)
SECURE_FILE_MODE = 0o600


@dataclass
class ProfileSecurityResult:
    """Result of a profile security check."""
    is_secure: bool
    profile_path: str
    issues: List[str]
    warnings: List[str]

    def __bool__(self):
        return self.is_secure

    def to_dict(self) -> dict:
        return {
            "is_secure": self.is_secure,
            "profile_path": self.profile_path,
            "issues": self.issues,
            "warnings": self.warnings,
        }


def get_project_root() -> Path:
    """Get the project root directory."""
    # Start from current file location and find project root
    current = Path(__file__).resolve()

    # Walk up looking for .gitignore or .git
    for parent in [current] + list(current.parents):
        if (parent / ".git").exists() or (parent / ".gitignore").exists():
            return parent

    # Fall back to current working directory
    return Path.cwd()


def get_secure_profile_path(profile_name: str = "upwork_profile") -> Path:
    """Get the path for a secure browser profile.

    Args:
        profile_name: Name of the profile directory

    Returns:
        Path to the profile directory (created if needed)
    """
    project_root = get_project_root()
    profile_path = project_root / profile_name

    return profile_path


def get_default_profile_path() -> Path:
    """Get the default browser profile path from environment or default location.

    Returns:
        Path to the browser profile directory
    """
    env_path = os.environ.get("PLAYWRIGHT_BROWSER_PROFILE")
    if env_path:
        return Path(env_path)

    return get_secure_profile_path("upwork_profile")


def check_directory_permissions(path: Path) -> Tuple[bool, List[str]]:
    """Check if directory has secure permissions.

    Args:
        path: Directory path to check

    Returns:
        Tuple of (is_secure, list of issues)
    """
    issues = []

    if not path.exists():
        return True, []  # Non-existent directories are "secure" (will be created properly)

    # Get current permissions
    current_mode = stat.S_IMODE(os.stat(path).st_mode)

    # Check for world-readable permissions
    if current_mode & stat.S_IROTH:
        issues.append(f"Directory {path} is world-readable")

    # Check for world-writable permissions
    if current_mode & stat.S_IWOTH:
        issues.append(f"Directory {path} is world-writable")

    # Check for world-executable permissions
    if current_mode & stat.S_IXOTH:
        issues.append(f"Directory {path} is world-executable")

    # Check for group-writable permissions
    if current_mode & stat.S_IWGRP:
        issues.append(f"Directory {path} is group-writable")

    return len(issues) == 0, issues


def check_sensitive_files_not_exposed(profile_path: Path) -> Tuple[bool, List[str]]:
    """Check that sensitive files within the profile are not exposed.

    Args:
        profile_path: Path to the browser profile

    Returns:
        Tuple of (is_secure, list of issues)
    """
    issues = []

    if not profile_path.exists():
        return True, []

    # Check common Chromium profile structure
    default_dir = profile_path / "Default"

    if default_dir.exists():
        for sensitive in SENSITIVE_FILES:
            sensitive_path = default_dir / sensitive
            if sensitive_path.exists():
                # Check file permissions
                if sensitive_path.is_file():
                    mode = stat.S_IMODE(os.stat(sensitive_path).st_mode)
                    if mode & (stat.S_IROTH | stat.S_IWOTH):
                        issues.append(f"Sensitive file {sensitive} has insecure permissions")
                elif sensitive_path.is_dir():
                    mode = stat.S_IMODE(os.stat(sensitive_path).st_mode)
                    if mode & (stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH):
                        issues.append(f"Sensitive directory {sensitive} has insecure permissions")

    return len(issues) == 0, issues


def check_gitignore_coverage(profile_path: Path) -> Tuple[bool, List[str], List[str]]:
    """Check if the profile directory is covered by .gitignore.

    Args:
        profile_path: Path to the browser profile

    Returns:
        Tuple of (is_covered, list of issues, list of warnings)
    """
    issues = []
    warnings = []

    project_root = get_project_root()
    gitignore_path = project_root / ".gitignore"

    if not gitignore_path.exists():
        issues.append(".gitignore file not found")
        return False, issues, warnings

    # Read gitignore
    with open(gitignore_path, 'r') as f:
        gitignore_content = f.read()

    # Get relative path from project root
    try:
        relative_path = profile_path.relative_to(project_root)
        profile_name = str(relative_path).split('/')[0]
    except ValueError:
        # Profile is outside project root
        warnings.append(f"Profile {profile_path} is outside project root - ensure it's not committed")
        return True, issues, warnings

    # Check if profile directory is covered
    patterns_to_check = [
        f"{profile_name}/",
        f"{profile_name}",
        f"*{profile_name}*",
    ]

    covered = False
    for pattern in patterns_to_check:
        if pattern in gitignore_content:
            covered = True
            break

    if not covered:
        issues.append(f"Profile directory '{profile_name}/' is not in .gitignore")

    # Check for sensitive file patterns
    missing_patterns = []
    for pattern in REQUIRED_GITIGNORE_PATTERNS:
        if pattern not in gitignore_content and pattern.replace('/', '') not in gitignore_content:
            # Check if a broader pattern covers it
            base = pattern.rstrip('/')
            if f"{base}/" not in gitignore_content and base not in gitignore_content:
                missing_patterns.append(pattern)

    # Only warn about specific missing patterns, not error
    for pattern in missing_patterns:
        if "Cookies" in pattern or "Login Data" in pattern or "Session" in pattern:
            warnings.append(f"Consider adding '{pattern}' to .gitignore for extra protection")

    return covered, issues, warnings


def validate_profile_security(profile_path: Optional[Path] = None) -> ProfileSecurityResult:
    """Validate the security of a browser profile.

    Args:
        profile_path: Path to validate (uses default if not provided)

    Returns:
        ProfileSecurityResult with validation details
    """
    if profile_path is None:
        profile_path = get_default_profile_path()

    profile_path = Path(profile_path)
    all_issues = []
    all_warnings = []

    # Check 1: Directory permissions
    perm_ok, perm_issues = check_directory_permissions(profile_path)
    all_issues.extend(perm_issues)

    # Check 2: Sensitive files not exposed
    files_ok, files_issues = check_sensitive_files_not_exposed(profile_path)
    all_issues.extend(files_issues)

    # Check 3: .gitignore coverage
    git_ok, git_issues, git_warnings = check_gitignore_coverage(profile_path)
    all_issues.extend(git_issues)
    all_warnings.extend(git_warnings)

    is_secure = len(all_issues) == 0

    return ProfileSecurityResult(
        is_secure=is_secure,
        profile_path=str(profile_path),
        issues=all_issues,
        warnings=all_warnings,
    )


def secure_directory_permissions(path: Path) -> bool:
    """Set secure permissions on a directory and its contents.

    Args:
        path: Directory to secure

    Returns:
        True if successful
    """
    if not path.exists():
        return True

    try:
        # Set directory permissions
        os.chmod(path, SECURE_DIR_MODE)

        # Recursively secure contents
        for item in path.rglob('*'):
            if item.is_dir():
                os.chmod(item, SECURE_DIR_MODE)
            else:
                os.chmod(item, SECURE_FILE_MODE)

        return True
    except (OSError, PermissionError) as e:
        print(f"Warning: Could not set permissions on {path}: {e}")
        return False


def update_gitignore_for_profiles(profile_path: Optional[Path] = None) -> bool:
    """Update .gitignore to include browser profile patterns.

    Args:
        profile_path: Specific profile path to add (optional)

    Returns:
        True if gitignore was updated or already contains patterns
    """
    project_root = get_project_root()
    gitignore_path = project_root / ".gitignore"

    # Read existing content
    existing_content = ""
    if gitignore_path.exists():
        with open(gitignore_path, 'r') as f:
            existing_content = f.read()

    # Determine what needs to be added
    additions = []

    # Check required patterns
    for pattern in REQUIRED_GITIGNORE_PATTERNS:
        if pattern not in existing_content:
            # Check if covered by broader pattern
            base = pattern.rstrip('/').split('/')[-1]
            if f"{base}/" not in existing_content and f"*{base}*" not in existing_content:
                additions.append(pattern)

    # Add specific profile path if provided
    if profile_path:
        try:
            relative = profile_path.relative_to(project_root)
            profile_name = str(relative).split('/')[0]
            pattern = f"{profile_name}/"
            if pattern not in existing_content and profile_name not in existing_content:
                additions.append(pattern)
        except ValueError:
            pass  # Outside project root

    if not additions:
        return True  # Already covered

    # Add new patterns
    new_content = existing_content.rstrip() + "\n\n# Browser profiles (session data)\n"
    for pattern in additions:
        new_content += f"{pattern}\n"

    with open(gitignore_path, 'w') as f:
        f.write(new_content)

    print(f"Updated .gitignore with browser profile patterns: {additions}")
    return True


def ensure_profile_security(profile_path: Optional[Path] = None) -> ProfileSecurityResult:
    """Ensure a browser profile directory is secure.

    Creates the directory if needed, sets proper permissions,
    and updates .gitignore.

    Args:
        profile_path: Path to the profile (uses default if not provided)

    Returns:
        ProfileSecurityResult with final status
    """
    if profile_path is None:
        profile_path = get_default_profile_path()

    profile_path = Path(profile_path)

    # Create directory with secure permissions if needed
    if not profile_path.exists():
        profile_path.mkdir(parents=True, mode=SECURE_DIR_MODE)
        print(f"Created secure profile directory: {profile_path}")
    else:
        # Secure existing directory
        secure_directory_permissions(profile_path)
        print(f"Secured existing profile directory: {profile_path}")

    # Update .gitignore
    update_gitignore_for_profiles(profile_path)

    # Validate final state
    return validate_profile_security(profile_path)


def create_profile_readme(profile_path: Path) -> None:
    """Create a README in the profile directory explaining its purpose.

    Args:
        profile_path: Path to the profile directory
    """
    readme_path = profile_path / "README.md"

    if readme_path.exists():
        return

    readme_content = """# Browser Profile Directory

This directory contains Playwright browser profile data for Upwork authentication.

## Security Notes

- This directory is excluded from version control via .gitignore
- Contains sensitive session cookies and authentication data
- Never commit this directory to git
- Never share the contents of this directory

## Setup

To use this profile:

1. Run the submitter with `--no-headless` to open a visible browser
2. Log into Upwork manually
3. Close the browser - session is now saved
4. Future runs will use the saved session

## Regenerating

If you need to regenerate the profile:

1. Delete this directory
2. Re-run the login process above
"""

    with open(readme_path, 'w') as f:
        f.write(readme_content)

    # Secure the README
    os.chmod(readme_path, SECURE_FILE_MODE)


# Utility functions for the submitter module

def get_submitter_profile_path() -> str:
    """Get the profile path for the Upwork submitter.

    Returns:
        String path to the secure profile directory
    """
    profile_path = get_default_profile_path()

    # Ensure security
    result = ensure_profile_security(profile_path)

    if not result.is_secure:
        print(f"Warning: Profile security issues: {result.issues}")

    # Create README if needed
    create_profile_readme(profile_path)

    return str(profile_path)


def verify_profile_not_in_git() -> bool:
    """Verify that browser profile directories are not tracked by git.

    Returns:
        True if profiles are safely ignored
    """
    project_root = get_project_root()

    # Check each potential profile directory
    for profile_name in BROWSER_PROFILE_DIRS:
        profile_path = project_root / profile_name

        if profile_path.exists():
            # Check if it's tracked by git
            git_check = os.popen(f'git ls-files --error-unmatch "{profile_path}" 2>/dev/null').read()
            if git_check.strip():
                print(f"ERROR: {profile_name} is tracked by git!")
                return False

    return True


def cleanup_session_data(profile_path: Optional[Path] = None, preserve_cookies: bool = True) -> bool:
    """Clean up sensitive session data while optionally preserving cookies.

    Args:
        profile_path: Path to the profile
        preserve_cookies: If True, keep authentication cookies

    Returns:
        True if cleanup successful
    """
    if profile_path is None:
        profile_path = get_default_profile_path()

    profile_path = Path(profile_path)
    default_dir = profile_path / "Default"

    if not default_dir.exists():
        return True

    # Files to clean (unless preserving)
    cleanup_files = [
        "History",
        "History-journal",
        "Cache",
        "Code Cache",
        "GPUCache",
        "Visited Links",
        "Network Action Predictor",
        "Top Sites",
    ]

    if not preserve_cookies:
        cleanup_files.extend(SENSITIVE_FILES)

    try:
        for filename in cleanup_files:
            file_path = default_dir / filename
            if file_path.exists():
                if file_path.is_file():
                    os.remove(file_path)
                elif file_path.is_dir():
                    import shutil
                    shutil.rmtree(file_path)

        return True
    except Exception as e:
        print(f"Warning: Cleanup error: {e}")
        return False


def main():
    """CLI interface for browser profile security."""
    import argparse

    parser = argparse.ArgumentParser(description="Manage Playwright browser profile security")
    parser.add_argument("--check", action="store_true", help="Check profile security")
    parser.add_argument("--ensure", action="store_true", help="Ensure profile is secure")
    parser.add_argument("--path", help="Profile path (uses default if not specified)")
    parser.add_argument("--cleanup", action="store_true", help="Clean up session data")
    parser.add_argument("--verify-git", action="store_true", help="Verify profiles not in git")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    profile_path = Path(args.path) if args.path else None

    if args.verify_git:
        result = verify_profile_not_in_git()
        if args.json:
            print(json.dumps({"profiles_safe": result}))
        else:
            print(f"Profiles safe from git: {result}")
        return

    if args.cleanup:
        result = cleanup_session_data(profile_path)
        if args.json:
            print(json.dumps({"cleanup_success": result}))
        else:
            print(f"Cleanup successful: {result}")
        return

    if args.ensure:
        result = ensure_profile_security(profile_path)
    else:
        # Default to check
        result = validate_profile_security(profile_path)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"\n=== Browser Profile Security ===")
        print(f"Profile: {result.profile_path}")
        print(f"Secure: {result.is_secure}")

        if result.issues:
            print(f"\nIssues:")
            for issue in result.issues:
                print(f"  - {issue}")

        if result.warnings:
            print(f"\nWarnings:")
            for warning in result.warnings:
                print(f"  - {warning}")

        if result.is_secure and not result.issues:
            print("\nProfile is secure!")


if __name__ == "__main__":
    main()
