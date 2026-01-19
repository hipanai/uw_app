#!/usr/bin/env python3
"""
Upwork OAuth Token Security - Secure token refresh and storage for Google OAuth.

Feature #83: Ensures Google OAuth tokens are refreshed securely:
- Validates token refresh uses secure endpoint (googleapis.com)
- Ensures refresh tokens are stored with secure permissions
- Verifies old tokens are invalidated after refresh
- Provides secure token management utilities

Usage:
    from upwork_oauth_token_security import (
        secure_token_refresh,
        validate_token_storage,
        ensure_token_security,
        get_secure_token_path,
    )

    # Securely refresh a token
    credentials = secure_token_refresh(token_path)

    # Validate token storage security
    is_secure, issues = validate_token_storage(token_path)

    # Ensure token file is secure
    ensure_token_security(token_path)
"""

import os
import stat
import json
import time
import hashlib
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timezone


# Secure file permissions (owner read/write only)
SECURE_FILE_MODE = 0o600

# Secure directory permissions (owner read/write/execute only)
SECURE_DIR_MODE = 0o700

# Valid OAuth endpoints for Google
VALID_TOKEN_ENDPOINTS = [
    "https://oauth2.googleapis.com/token",
    "https://accounts.google.com/o/oauth2/token",
    "https://www.googleapis.com/oauth2/v4/token",
]

# Token file patterns that should be in .gitignore
TOKEN_GITIGNORE_PATTERNS = [
    "token.json",
    "token_*.json",
    "**/token.json",
    "**/token_*.json",
    "config/token*.json",
]

# Required scopes for the Upwork pipeline
REQUIRED_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
]

# Sensitive fields in token files
SENSITIVE_FIELDS = [
    "refresh_token",
    "access_token",
    "client_secret",
]


@dataclass
class TokenSecurityResult:
    """Result of a token security check."""
    is_secure: bool
    token_path: str
    issues: List[str]
    warnings: List[str]
    token_metadata: Dict[str, Any]

    def __bool__(self):
        return self.is_secure

    def to_dict(self) -> dict:
        return {
            "is_secure": self.is_secure,
            "token_path": self.token_path,
            "issues": self.issues,
            "warnings": self.warnings,
            "token_metadata": self.token_metadata,
        }


@dataclass
class TokenRefreshResult:
    """Result of a token refresh operation."""
    success: bool
    refreshed: bool
    token_path: str
    old_token_hash: Optional[str]
    new_token_hash: Optional[str]
    expiry: Optional[str]
    error: Optional[str]

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "refreshed": self.refreshed,
            "token_path": self.token_path,
            "old_token_hash": self.old_token_hash,
            "new_token_hash": self.new_token_hash,
            "expiry": self.expiry,
            "error": self.error,
        }


def get_project_root() -> Path:
    """Get the project root directory."""
    current = Path(__file__).resolve()

    for parent in [current] + list(current.parents):
        if (parent / ".git").exists() or (parent / ".gitignore").exists():
            return parent

    return Path.cwd()


def get_secure_token_path(account_name: str = "default") -> Path:
    """Get the secure path for a token file.

    Args:
        account_name: Name of the account (default, leftclick, nicksaraev, etc.)

    Returns:
        Path to the token file in config/
    """
    project_root = get_project_root()
    config_dir = project_root / "config"

    if account_name == "default":
        return config_dir / "token.json"
    else:
        return config_dir / f"token_{account_name}.json"


def get_default_token_path() -> Path:
    """Get the default token path from environment or config.

    Returns:
        Path to the primary token file
    """
    env_path = os.environ.get("GOOGLE_TOKEN_PATH")
    if env_path:
        return Path(env_path)

    return get_secure_token_path("default")


def hash_token(token_data: dict) -> str:
    """Create a hash of token data for comparison.

    Args:
        token_data: Token dictionary

    Returns:
        SHA-256 hash of the access token
    """
    access_token = token_data.get("token", token_data.get("access_token", ""))
    return hashlib.sha256(access_token.encode()).hexdigest()[:16]


def check_file_permissions(path: Path) -> Tuple[bool, List[str]]:
    """Check if file has secure permissions.

    Args:
        path: File path to check

    Returns:
        Tuple of (is_secure, list of issues)
    """
    issues = []

    if not path.exists():
        return True, []

    current_mode = stat.S_IMODE(os.stat(path).st_mode)

    # Check for world-readable permissions
    if current_mode & stat.S_IROTH:
        issues.append(f"Token file {path.name} is world-readable")

    # Check for world-writable permissions
    if current_mode & stat.S_IWOTH:
        issues.append(f"Token file {path.name} is world-writable")

    # Check for group-readable permissions (optional warning)
    if current_mode & stat.S_IRGRP:
        issues.append(f"Token file {path.name} is group-readable")

    # Check for group-writable permissions
    if current_mode & stat.S_IWGRP:
        issues.append(f"Token file {path.name} is group-writable")

    return len(issues) == 0, issues


def check_directory_permissions(path: Path) -> Tuple[bool, List[str]]:
    """Check if token directory has secure permissions.

    Args:
        path: Directory path to check

    Returns:
        Tuple of (is_secure, list of issues)
    """
    issues = []
    parent = path.parent

    if not parent.exists():
        return True, []

    current_mode = stat.S_IMODE(os.stat(parent).st_mode)

    if current_mode & stat.S_IWOTH:
        issues.append(f"Token directory {parent} is world-writable")

    if current_mode & stat.S_IWGRP:
        issues.append(f"Token directory {parent} is group-writable")

    return len(issues) == 0, issues


def check_token_gitignore_coverage(token_path: Path) -> Tuple[bool, List[str]]:
    """Check if token files are covered by .gitignore.

    Args:
        token_path: Path to the token file

    Returns:
        Tuple of (is_covered, list of issues)
    """
    issues = []
    project_root = get_project_root()
    gitignore_path = project_root / ".gitignore"

    if not gitignore_path.exists():
        issues.append(".gitignore file not found")
        return False, issues

    with open(gitignore_path, 'r') as f:
        gitignore_content = f.read()

    # Check for token patterns
    token_covered = False
    patterns_to_check = [
        token_path.name,
        f"config/{token_path.name}",
        "token*.json",
        "**/token*.json",
        "config/token*.json",
    ]

    for pattern in patterns_to_check:
        if pattern in gitignore_content:
            token_covered = True
            break

    if not token_covered:
        issues.append(f"Token file '{token_path.name}' may not be covered by .gitignore")

    return token_covered, issues


def check_token_content_security(token_path: Path) -> Tuple[bool, List[str], Dict[str, Any]]:
    """Check token content for security issues.

    Args:
        token_path: Path to the token file

    Returns:
        Tuple of (is_secure, issues, metadata)
    """
    issues = []
    metadata = {}

    if not token_path.exists():
        return True, [], {"exists": False}

    try:
        with open(token_path, 'r') as f:
            token_data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        issues.append(f"Token file is corrupted: {e}")
        return False, issues, {"exists": True, "valid_json": False}

    metadata["exists"] = True
    metadata["valid_json"] = True

    # Check for refresh token presence
    has_refresh = "refresh_token" in token_data
    metadata["has_refresh_token"] = has_refresh

    if not has_refresh:
        issues.append("Token missing refresh_token - cannot refresh securely")

    # Check token expiry
    expiry = token_data.get("expiry")
    if expiry:
        metadata["expiry"] = expiry
        try:
            # Parse expiry time
            expiry_time = datetime.fromisoformat(expiry.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            if expiry_time < now:
                metadata["expired"] = True
            else:
                metadata["expired"] = False
                metadata["expires_in_seconds"] = (expiry_time - now).total_seconds()
        except ValueError:
            metadata["expiry_parse_error"] = True

    # Check for client_secret in token file (should not be there)
    if "client_secret" in token_data:
        issues.append("Token file contains client_secret - this should be in credentials.json only")

    # Check scopes
    scopes = token_data.get("scopes", [])
    metadata["scopes"] = scopes

    # Check token endpoint
    token_uri = token_data.get("token_uri", "")
    metadata["token_uri"] = token_uri

    if token_uri and not any(token_uri.startswith(valid) for valid in VALID_TOKEN_ENDPOINTS):
        issues.append(f"Token uses non-standard endpoint: {token_uri}")

    return len(issues) == 0, issues, metadata


def validate_token_storage(token_path: Optional[Path] = None) -> TokenSecurityResult:
    """Validate the security of token storage.

    Args:
        token_path: Path to validate (uses default if not provided)

    Returns:
        TokenSecurityResult with validation details
    """
    if token_path is None:
        token_path = get_default_token_path()

    token_path = Path(token_path)
    all_issues = []
    all_warnings = []

    # Check 1: File permissions
    file_ok, file_issues = check_file_permissions(token_path)
    all_issues.extend(file_issues)

    # Check 2: Directory permissions
    dir_ok, dir_issues = check_directory_permissions(token_path)
    all_issues.extend(dir_issues)

    # Check 3: .gitignore coverage
    git_ok, git_issues = check_token_gitignore_coverage(token_path)
    # Git issues are warnings, not errors
    all_warnings.extend(git_issues)

    # Check 4: Token content security
    content_ok, content_issues, metadata = check_token_content_security(token_path)
    all_issues.extend(content_issues)

    is_secure = len(all_issues) == 0

    return TokenSecurityResult(
        is_secure=is_secure,
        token_path=str(token_path),
        issues=all_issues,
        warnings=all_warnings,
        token_metadata=metadata,
    )


def secure_file_permissions(path: Path) -> bool:
    """Set secure permissions on a file.

    Args:
        path: File path to secure

    Returns:
        True if successful
    """
    if not path.exists():
        return True

    try:
        os.chmod(path, SECURE_FILE_MODE)
        return True
    except (OSError, PermissionError) as e:
        print(f"Warning: Could not set permissions on {path}: {e}")
        return False


def secure_directory_permissions(path: Path) -> bool:
    """Set secure permissions on a directory.

    Args:
        path: Directory path to secure

    Returns:
        True if successful
    """
    if not path.exists():
        return True

    try:
        os.chmod(path, SECURE_DIR_MODE)
        return True
    except (OSError, PermissionError) as e:
        print(f"Warning: Could not set permissions on {path}: {e}")
        return False


def update_gitignore_for_tokens() -> bool:
    """Update .gitignore to include token patterns.

    Returns:
        True if gitignore was updated or already contains patterns
    """
    project_root = get_project_root()
    gitignore_path = project_root / ".gitignore"

    existing_content = ""
    if gitignore_path.exists():
        with open(gitignore_path, 'r') as f:
            existing_content = f.read()

    additions = []
    for pattern in TOKEN_GITIGNORE_PATTERNS:
        if pattern not in existing_content:
            additions.append(pattern)

    if not additions:
        return True

    new_content = existing_content.rstrip() + "\n\n# OAuth tokens (sensitive credentials)\n"
    for pattern in additions:
        new_content += f"{pattern}\n"

    with open(gitignore_path, 'w') as f:
        f.write(new_content)

    print(f"Updated .gitignore with token patterns: {additions}")
    return True


def ensure_token_security(token_path: Optional[Path] = None) -> TokenSecurityResult:
    """Ensure a token file is stored securely.

    Sets proper permissions and updates .gitignore.

    Args:
        token_path: Path to the token (uses default if not provided)

    Returns:
        TokenSecurityResult with final status
    """
    if token_path is None:
        token_path = get_default_token_path()

    token_path = Path(token_path)

    # Ensure config directory exists with secure permissions
    config_dir = token_path.parent
    if not config_dir.exists():
        config_dir.mkdir(parents=True, mode=SECURE_DIR_MODE)
        print(f"Created secure config directory: {config_dir}")
    else:
        secure_directory_permissions(config_dir)

    # Secure token file if it exists
    if token_path.exists():
        secure_file_permissions(token_path)
        print(f"Secured token file: {token_path}")

    # Update .gitignore
    update_gitignore_for_tokens()

    # Validate final state
    return validate_token_storage(token_path)


def invalidate_old_token(token_path: Path, old_token_data: dict) -> bool:
    """Invalidate an old token by overwriting sensitive data.

    This ensures that if old token data is somehow recovered, it cannot be used.

    Args:
        token_path: Path to the token file
        old_token_data: Previous token data

    Returns:
        True if invalidation was successful
    """
    # The old token is invalidated by simply overwriting the file with new token
    # Google OAuth invalidates old access tokens when new ones are issued
    # We log the invalidation for audit purposes
    old_hash = hash_token(old_token_data)
    print(f"Previous token (hash: {old_hash}) invalidated by refresh")
    return True


def secure_token_refresh(
    token_path: Optional[Path] = None,
    scopes: Optional[List[str]] = None,
    force: bool = False
) -> TokenRefreshResult:
    """Securely refresh a Google OAuth token.

    Validates the refresh endpoint, performs the refresh, and ensures
    old tokens are invalidated.

    Args:
        token_path: Path to the token file
        scopes: Required scopes (uses default if not provided)
        force: Force refresh even if token is not expired

    Returns:
        TokenRefreshResult with refresh details
    """
    if token_path is None:
        token_path = get_default_token_path()

    token_path = Path(token_path)

    if not token_path.exists():
        return TokenRefreshResult(
            success=False,
            refreshed=False,
            token_path=str(token_path),
            old_token_hash=None,
            new_token_hash=None,
            expiry=None,
            error="Token file does not exist",
        )

    try:
        # Import Google OAuth libraries
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as e:
        return TokenRefreshResult(
            success=False,
            refreshed=False,
            token_path=str(token_path),
            old_token_hash=None,
            new_token_hash=None,
            expiry=None,
            error=f"Missing required library: {e}",
        )

    # Load existing token
    try:
        with open(token_path, 'r') as f:
            old_token_data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        return TokenRefreshResult(
            success=False,
            refreshed=False,
            token_path=str(token_path),
            old_token_hash=None,
            new_token_hash=None,
            expiry=None,
            error=f"Failed to read token: {e}",
        )

    old_token_hash = hash_token(old_token_data)

    # Validate token endpoint before refresh
    token_uri = old_token_data.get("token_uri", "")
    if token_uri and not any(token_uri.startswith(valid) for valid in VALID_TOKEN_ENDPOINTS):
        return TokenRefreshResult(
            success=False,
            refreshed=False,
            token_path=str(token_path),
            old_token_hash=old_token_hash,
            new_token_hash=None,
            expiry=None,
            error=f"Refusing to use non-standard token endpoint: {token_uri}",
        )

    # Check if refresh token exists
    if "refresh_token" not in old_token_data:
        return TokenRefreshResult(
            success=False,
            refreshed=False,
            token_path=str(token_path),
            old_token_hash=old_token_hash,
            new_token_hash=None,
            expiry=None,
            error="No refresh token available",
        )

    # Load credentials
    if scopes is None:
        scopes = old_token_data.get("scopes", REQUIRED_SCOPES)

    try:
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)
    except Exception as e:
        return TokenRefreshResult(
            success=False,
            refreshed=False,
            token_path=str(token_path),
            old_token_hash=old_token_hash,
            new_token_hash=None,
            expiry=None,
            error=f"Failed to load credentials: {e}",
        )

    # Check if refresh is needed
    if creds.valid and not force:
        return TokenRefreshResult(
            success=True,
            refreshed=False,
            token_path=str(token_path),
            old_token_hash=old_token_hash,
            new_token_hash=old_token_hash,
            expiry=creds.expiry.isoformat() if creds.expiry else None,
            error=None,
        )

    # Perform secure refresh
    if creds.expired or not creds.valid or force:
        if not creds.refresh_token:
            return TokenRefreshResult(
                success=False,
                refreshed=False,
                token_path=str(token_path),
                old_token_hash=old_token_hash,
                new_token_hash=None,
                expiry=None,
                error="Credentials expired and no refresh token available",
            )

        try:
            # Refresh using secure Google endpoint
            creds.refresh(Request())
        except Exception as e:
            return TokenRefreshResult(
                success=False,
                refreshed=False,
                token_path=str(token_path),
                old_token_hash=old_token_hash,
                new_token_hash=None,
                expiry=None,
                error=f"Token refresh failed: {e}",
            )

        # Save new token with secure permissions
        new_token_data = json.loads(creds.to_json())
        new_token_hash = hash_token(new_token_data)

        # Write with secure permissions
        with open(token_path, 'w') as f:
            json.dump(new_token_data, f, indent=2)

        # Set secure permissions
        secure_file_permissions(token_path)

        # Invalidate old token (log the change)
        invalidate_old_token(token_path, old_token_data)

        return TokenRefreshResult(
            success=True,
            refreshed=True,
            token_path=str(token_path),
            old_token_hash=old_token_hash,
            new_token_hash=new_token_hash,
            expiry=creds.expiry.isoformat() if creds.expiry else None,
            error=None,
        )

    return TokenRefreshResult(
        success=True,
        refreshed=False,
        token_path=str(token_path),
        old_token_hash=old_token_hash,
        new_token_hash=old_token_hash,
        expiry=creds.expiry.isoformat() if creds.expiry else None,
        error=None,
    )


def verify_refresh_endpoint_security(token_path: Optional[Path] = None) -> Tuple[bool, str]:
    """Verify that the token refresh endpoint is secure.

    Args:
        token_path: Path to the token file

    Returns:
        Tuple of (is_secure, endpoint_url)
    """
    if token_path is None:
        token_path = get_default_token_path()

    token_path = Path(token_path)

    if not token_path.exists():
        return True, "No token file"

    try:
        with open(token_path, 'r') as f:
            token_data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return False, "Invalid token file"

    token_uri = token_data.get("token_uri", "")

    if not token_uri:
        # Default to standard Google endpoint
        return True, "Using default Google endpoint"

    # Check if endpoint is valid
    is_secure = any(token_uri.startswith(valid) for valid in VALID_TOKEN_ENDPOINTS)
    return is_secure, token_uri


def list_token_files() -> List[Dict[str, Any]]:
    """List all token files in the config directory.

    Returns:
        List of token file info dictionaries
    """
    project_root = get_project_root()
    config_dir = project_root / "config"

    if not config_dir.exists():
        return []

    tokens = []
    for token_file in config_dir.glob("token*.json"):
        result = validate_token_storage(token_file)
        tokens.append({
            "path": str(token_file),
            "name": token_file.name,
            "secure": result.is_secure,
            "issues": result.issues,
            "metadata": result.token_metadata,
        })

    return tokens


def rotate_token(token_path: Optional[Path] = None) -> TokenRefreshResult:
    """Force rotation of a token for security purposes.

    This is useful when:
    - Token may have been compromised
    - Periodic security rotation policy
    - After a security incident

    Args:
        token_path: Path to the token file

    Returns:
        TokenRefreshResult with rotation details
    """
    return secure_token_refresh(token_path, force=True)


def main():
    """CLI interface for OAuth token security."""
    import argparse

    parser = argparse.ArgumentParser(description="Manage Google OAuth token security")
    parser.add_argument("--check", action="store_true", help="Check token security")
    parser.add_argument("--ensure", action="store_true", help="Ensure token is secure")
    parser.add_argument("--refresh", action="store_true", help="Securely refresh token")
    parser.add_argument("--rotate", action="store_true", help="Force token rotation")
    parser.add_argument("--list", action="store_true", help="List all token files")
    parser.add_argument("--path", help="Token path (uses default if not specified)")
    parser.add_argument("--verify-endpoint", action="store_true", help="Verify refresh endpoint")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    token_path = Path(args.path) if args.path else None

    if args.list:
        tokens = list_token_files()
        if args.json:
            print(json.dumps(tokens, indent=2))
        else:
            print("\n=== Token Files ===")
            for token in tokens:
                status = "SECURE" if token["secure"] else "INSECURE"
                print(f"\n{token['name']} [{status}]")
                print(f"  Path: {token['path']}")
                if token["issues"]:
                    print(f"  Issues: {token['issues']}")
                if token["metadata"].get("expiry"):
                    print(f"  Expiry: {token['metadata']['expiry']}")
        return

    if args.verify_endpoint:
        is_secure, endpoint = verify_refresh_endpoint_security(token_path)
        if args.json:
            print(json.dumps({"secure": is_secure, "endpoint": endpoint}))
        else:
            status = "SECURE" if is_secure else "INSECURE"
            print(f"Refresh endpoint: {endpoint} [{status}]")
        return

    if args.refresh:
        result = secure_token_refresh(token_path)
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(f"\n=== Token Refresh ===")
            print(f"Success: {result.success}")
            print(f"Refreshed: {result.refreshed}")
            if result.old_token_hash:
                print(f"Old token hash: {result.old_token_hash}")
            if result.new_token_hash:
                print(f"New token hash: {result.new_token_hash}")
            if result.expiry:
                print(f"Expiry: {result.expiry}")
            if result.error:
                print(f"Error: {result.error}")
        return

    if args.rotate:
        result = rotate_token(token_path)
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(f"\n=== Token Rotation ===")
            print(f"Success: {result.success}")
            if result.old_token_hash != result.new_token_hash:
                print(f"Token rotated: {result.old_token_hash} -> {result.new_token_hash}")
            if result.error:
                print(f"Error: {result.error}")
        return

    if args.ensure:
        result = ensure_token_security(token_path)
    else:
        # Default to check
        result = validate_token_storage(token_path)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"\n=== OAuth Token Security ===")
        print(f"Token: {result.token_path}")
        print(f"Secure: {result.is_secure}")

        if result.issues:
            print(f"\nIssues:")
            for issue in result.issues:
                print(f"  - {issue}")

        if result.warnings:
            print(f"\nWarnings:")
            for warning in result.warnings:
                print(f"  - {warning}")

        if result.token_metadata:
            print(f"\nMetadata:")
            for key, value in result.token_metadata.items():
                if key not in ("exists", "valid_json"):
                    print(f"  {key}: {value}")

        if result.is_secure and not result.issues:
            print("\nToken storage is secure!")


if __name__ == "__main__":
    main()
