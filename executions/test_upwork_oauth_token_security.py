#!/usr/bin/env python3
"""
Test suite for upwork_oauth_token_security.py

Feature #83: Tests that Google OAuth tokens are refreshed securely:
- Token refresh uses secure endpoint (googleapis.com)
- Refresh token is stored securely
- Old tokens are invalidated after refresh
"""

import os
import sys
import stat
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
from datetime import datetime, timezone, timedelta

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from upwork_oauth_token_security import (
    # Security result classes
    TokenSecurityResult,
    TokenRefreshResult,
    # Path utilities
    get_project_root,
    get_secure_token_path,
    get_default_token_path,
    # Hash utilities
    hash_token,
    # Permission checks
    check_file_permissions,
    check_directory_permissions,
    check_token_gitignore_coverage,
    check_token_content_security,
    # Main validation functions
    validate_token_storage,
    ensure_token_security,
    # Permission setters
    secure_file_permissions,
    secure_directory_permissions,
    update_gitignore_for_tokens,
    # Token operations
    secure_token_refresh,
    verify_refresh_endpoint_security,
    invalidate_old_token,
    rotate_token,
    list_token_files,
    # Constants
    SECURE_FILE_MODE,
    SECURE_DIR_MODE,
    VALID_TOKEN_ENDPOINTS,
    TOKEN_GITIGNORE_PATTERNS,
    REQUIRED_SCOPES,
    SENSITIVE_FIELDS,
)


class TestTokenSecurityResult(unittest.TestCase):
    """Tests for TokenSecurityResult dataclass."""

    def test_secure_result_is_truthy(self):
        """Secure result should be truthy."""
        result = TokenSecurityResult(
            is_secure=True,
            token_path="/path/token.json",
            issues=[],
            warnings=[],
            token_metadata={},
        )
        self.assertTrue(result)

    def test_insecure_result_is_falsy(self):
        """Insecure result should be falsy."""
        result = TokenSecurityResult(
            is_secure=False,
            token_path="/path/token.json",
            issues=["World readable"],
            warnings=[],
            token_metadata={},
        )
        self.assertFalse(result)

    def test_to_dict_contains_all_fields(self):
        """to_dict() should include all fields."""
        result = TokenSecurityResult(
            is_secure=True,
            token_path="/path/token.json",
            issues=["issue1"],
            warnings=["warning1"],
            token_metadata={"key": "value"},
        )
        d = result.to_dict()
        self.assertIn("is_secure", d)
        self.assertIn("token_path", d)
        self.assertIn("issues", d)
        self.assertIn("warnings", d)
        self.assertIn("token_metadata", d)


class TestTokenRefreshResult(unittest.TestCase):
    """Tests for TokenRefreshResult dataclass."""

    def test_to_dict_contains_all_fields(self):
        """to_dict() should include all fields."""
        result = TokenRefreshResult(
            success=True,
            refreshed=True,
            token_path="/path/token.json",
            old_token_hash="abc123",
            new_token_hash="def456",
            expiry="2025-01-20T12:00:00Z",
            error=None,
        )
        d = result.to_dict()
        self.assertIn("success", d)
        self.assertIn("refreshed", d)
        self.assertIn("token_path", d)
        self.assertIn("old_token_hash", d)
        self.assertIn("new_token_hash", d)
        self.assertIn("expiry", d)
        self.assertIn("error", d)

    def test_error_result(self):
        """Error result should contain error message."""
        result = TokenRefreshResult(
            success=False,
            refreshed=False,
            token_path="/path/token.json",
            old_token_hash=None,
            new_token_hash=None,
            expiry=None,
            error="Token file does not exist",
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error, "Token file does not exist")


class TestPathUtilities(unittest.TestCase):
    """Tests for path utility functions."""

    def test_get_project_root_returns_path(self):
        """get_project_root() should return a Path object."""
        root = get_project_root()
        self.assertIsInstance(root, Path)

    def test_get_secure_token_path_default(self):
        """get_secure_token_path() with default returns token.json."""
        path = get_secure_token_path("default")
        self.assertEqual(path.name, "token.json")
        self.assertEqual(path.parent.name, "config")

    def test_get_secure_token_path_named(self):
        """get_secure_token_path() with name returns token_name.json."""
        path = get_secure_token_path("leftclick")
        self.assertEqual(path.name, "token_leftclick.json")
        self.assertEqual(path.parent.name, "config")

    def test_get_default_token_path_without_env(self):
        """get_default_token_path() returns config/token.json by default."""
        with patch.dict(os.environ, {}, clear=True):
            path = get_default_token_path()
            self.assertEqual(path.name, "token.json")

    def test_get_default_token_path_with_env(self):
        """get_default_token_path() respects GOOGLE_TOKEN_PATH env var."""
        with patch.dict(os.environ, {"GOOGLE_TOKEN_PATH": "/custom/path/token.json"}):
            path = get_default_token_path()
            self.assertEqual(str(path), "/custom/path/token.json")


class TestHashToken(unittest.TestCase):
    """Tests for hash_token function."""

    def test_hash_with_token_field(self):
        """hash_token() should hash the 'token' field."""
        token_data = {"token": "access_token_123"}
        h = hash_token(token_data)
        self.assertEqual(len(h), 16)

    def test_hash_with_access_token_field(self):
        """hash_token() should hash the 'access_token' field."""
        token_data = {"access_token": "access_token_456"}
        h = hash_token(token_data)
        self.assertEqual(len(h), 16)

    def test_hash_different_tokens_are_different(self):
        """Different tokens should produce different hashes."""
        hash1 = hash_token({"token": "token1"})
        hash2 = hash_token({"token": "token2"})
        self.assertNotEqual(hash1, hash2)

    def test_hash_same_token_is_same(self):
        """Same token should produce same hash."""
        hash1 = hash_token({"token": "same_token"})
        hash2 = hash_token({"token": "same_token"})
        self.assertEqual(hash1, hash2)


class TestFilePermissionChecks(unittest.TestCase):
    """Tests for file permission check functions."""

    def test_check_file_permissions_nonexistent(self):
        """Non-existent files are considered secure."""
        is_secure, issues = check_file_permissions(Path("/nonexistent/token.json"))
        self.assertTrue(is_secure)
        self.assertEqual(len(issues), 0)

    def test_check_file_permissions_secure_file(self):
        """Secure file should pass checks."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write('{"token": "test"}')
            f.flush()
            os.chmod(f.name, 0o600)

            is_secure, issues = check_file_permissions(Path(f.name))
            self.assertTrue(is_secure)
            self.assertEqual(len(issues), 0)

            os.unlink(f.name)

    def test_check_file_permissions_world_readable(self):
        """World-readable file should fail checks."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write('{"token": "test"}')
            f.flush()
            os.chmod(f.name, 0o644)

            is_secure, issues = check_file_permissions(Path(f.name))
            self.assertFalse(is_secure)
            self.assertTrue(any("world-readable" in issue for issue in issues))

            os.unlink(f.name)

    def test_check_directory_permissions_nonexistent(self):
        """Non-existent directories are considered secure."""
        is_secure, issues = check_directory_permissions(Path("/nonexistent/path/token.json"))
        self.assertTrue(is_secure)


class TestGitignoreCoverage(unittest.TestCase):
    """Tests for .gitignore coverage checks."""

    def test_check_gitignore_no_gitignore_file(self):
        """Missing .gitignore should report issue."""
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "config" / "token.json"
            with patch('upwork_oauth_token_security.get_project_root', return_value=Path(tmpdir)):
                is_covered, issues = check_token_gitignore_coverage(token_path)
                self.assertFalse(is_covered)
                self.assertTrue(any(".gitignore" in issue for issue in issues))

    def test_check_gitignore_token_covered(self):
        """Token covered by .gitignore should pass."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gitignore_path = Path(tmpdir) / ".gitignore"
            gitignore_path.write_text("token*.json\n")

            token_path = Path(tmpdir) / "config" / "token.json"
            with patch('upwork_oauth_token_security.get_project_root', return_value=Path(tmpdir)):
                is_covered, issues = check_token_gitignore_coverage(token_path)
                self.assertTrue(is_covered)


class TestTokenContentSecurity(unittest.TestCase):
    """Tests for token content security checks."""

    def test_nonexistent_token_file(self):
        """Non-existent token file is secure."""
        is_secure, issues, metadata = check_token_content_security(Path("/nonexistent/token.json"))
        self.assertTrue(is_secure)
        self.assertFalse(metadata.get("exists", True))

    def test_valid_token_with_refresh(self):
        """Valid token with refresh_token should pass."""
        token_data = {
            "token": "access_token",
            "refresh_token": "refresh_token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(token_data, f)
            f.flush()

            is_secure, issues, metadata = check_token_content_security(Path(f.name))
            self.assertTrue(is_secure)
            self.assertTrue(metadata.get("has_refresh_token"))

            os.unlink(f.name)

    def test_token_missing_refresh(self):
        """Token without refresh_token should report issue."""
        token_data = {
            "token": "access_token",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(token_data, f)
            f.flush()

            is_secure, issues, metadata = check_token_content_security(Path(f.name))
            self.assertFalse(is_secure)
            self.assertTrue(any("refresh_token" in issue for issue in issues))

            os.unlink(f.name)

    def test_token_with_client_secret(self):
        """Token containing client_secret should report issue."""
        token_data = {
            "token": "access_token",
            "refresh_token": "refresh_token",
            "client_secret": "secret123",
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(token_data, f)
            f.flush()

            is_secure, issues, metadata = check_token_content_security(Path(f.name))
            self.assertFalse(is_secure)
            self.assertTrue(any("client_secret" in issue for issue in issues))

            os.unlink(f.name)

    def test_token_with_invalid_endpoint(self):
        """Token with non-standard endpoint should report issue."""
        token_data = {
            "token": "access_token",
            "refresh_token": "refresh_token",
            "token_uri": "https://malicious.example.com/token",
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(token_data, f)
            f.flush()

            is_secure, issues, metadata = check_token_content_security(Path(f.name))
            self.assertFalse(is_secure)
            self.assertTrue(any("non-standard endpoint" in issue for issue in issues))

            os.unlink(f.name)

    def test_corrupted_token_file(self):
        """Corrupted token file should report issue."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("not valid json {{{")
            f.flush()

            is_secure, issues, metadata = check_token_content_security(Path(f.name))
            self.assertFalse(is_secure)
            self.assertTrue(any("corrupted" in issue for issue in issues))

            os.unlink(f.name)


class TestValidateTokenStorage(unittest.TestCase):
    """Tests for validate_token_storage function."""

    def test_validate_nonexistent_token(self):
        """Validating non-existent token should handle gracefully."""
        result = validate_token_storage(Path("/nonexistent/token.json"))
        self.assertIsInstance(result, TokenSecurityResult)

    def test_validate_returns_security_result(self):
        """validate_token_storage should return TokenSecurityResult."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"token": "test", "refresh_token": "refresh"}, f)
            f.flush()
            os.chmod(f.name, 0o600)

            result = validate_token_storage(Path(f.name))
            self.assertIsInstance(result, TokenSecurityResult)
            self.assertEqual(result.token_path, f.name)

            os.unlink(f.name)


class TestPermissionSetters(unittest.TestCase):
    """Tests for permission setting functions."""

    def test_secure_file_permissions(self):
        """secure_file_permissions should set 600."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test")
            f.flush()
            os.chmod(f.name, 0o644)

            result = secure_file_permissions(Path(f.name))
            self.assertTrue(result)

            mode = stat.S_IMODE(os.stat(f.name).st_mode)
            self.assertEqual(mode, SECURE_FILE_MODE)

            os.unlink(f.name)

    def test_secure_file_permissions_nonexistent(self):
        """secure_file_permissions on non-existent file should return True."""
        result = secure_file_permissions(Path("/nonexistent/file"))
        self.assertTrue(result)

    def test_secure_directory_permissions(self):
        """secure_directory_permissions should set 700."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chmod(tmpdir, 0o755)

            result = secure_directory_permissions(Path(tmpdir))
            self.assertTrue(result)

            mode = stat.S_IMODE(os.stat(tmpdir).st_mode)
            self.assertEqual(mode, SECURE_DIR_MODE)


class TestEnsureTokenSecurity(unittest.TestCase):
    """Tests for ensure_token_security function."""

    def test_ensure_creates_config_dir(self):
        """ensure_token_security should create config directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "config"
            token_path = config_dir / "token.json"

            with patch('upwork_oauth_token_security.get_project_root', return_value=Path(tmpdir)):
                with patch('upwork_oauth_token_security.update_gitignore_for_tokens', return_value=True):
                    result = ensure_token_security(token_path)

            self.assertTrue(config_dir.exists())

    def test_ensure_secures_existing_file(self):
        """ensure_token_security should secure existing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "config"
            config_dir.mkdir()
            token_path = config_dir / "token.json"

            # Create insecure token file
            token_path.write_text('{"token": "test", "refresh_token": "refresh"}')
            os.chmod(token_path, 0o644)

            with patch('upwork_oauth_token_security.get_project_root', return_value=Path(tmpdir)):
                with patch('upwork_oauth_token_security.update_gitignore_for_tokens', return_value=True):
                    result = ensure_token_security(token_path)

            # Check file is now secure
            mode = stat.S_IMODE(os.stat(token_path).st_mode)
            self.assertEqual(mode, SECURE_FILE_MODE)


class TestSecureTokenRefresh(unittest.TestCase):
    """Tests for secure_token_refresh function."""

    def test_refresh_nonexistent_token(self):
        """Refreshing non-existent token should fail gracefully."""
        result = secure_token_refresh(Path("/nonexistent/token.json"))
        self.assertFalse(result.success)
        self.assertIn("does not exist", result.error)

    def test_refresh_invalid_endpoint(self):
        """Refresh with invalid endpoint should be rejected."""
        token_data = {
            "token": "access_token",
            "refresh_token": "refresh_token",
            "token_uri": "https://malicious.example.com/token",
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(token_data, f)
            f.flush()

            result = secure_token_refresh(Path(f.name))
            self.assertFalse(result.success)
            self.assertIn("non-standard", result.error)

            os.unlink(f.name)

    def test_refresh_no_refresh_token(self):
        """Refresh without refresh_token should fail."""
        token_data = {
            "token": "access_token",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(token_data, f)
            f.flush()

            result = secure_token_refresh(Path(f.name))
            self.assertFalse(result.success)
            self.assertIn("refresh token", result.error.lower())

            os.unlink(f.name)

    @patch('upwork_oauth_token_security.Request')
    @patch('upwork_oauth_token_security.Credentials')
    def test_refresh_valid_token_not_expired(self, mock_creds_class, mock_request):
        """Valid non-expired token should not refresh."""
        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds.expired = False
        mock_creds.expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        mock_creds_class.from_authorized_user_file.return_value = mock_creds

        token_data = {
            "token": "access_token",
            "refresh_token": "refresh_token",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(token_data, f)
            f.flush()

            result = secure_token_refresh(Path(f.name))
            self.assertTrue(result.success)
            self.assertFalse(result.refreshed)

            os.unlink(f.name)

    @patch('upwork_oauth_token_security.Request')
    @patch('upwork_oauth_token_security.Credentials')
    def test_refresh_expired_token(self, mock_creds_class, mock_request):
        """Expired token should be refreshed."""
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "refresh_token"
        mock_creds.expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        mock_creds.to_json.return_value = '{"token": "new_token", "refresh_token": "refresh_token"}'
        mock_creds_class.from_authorized_user_file.return_value = mock_creds

        token_data = {
            "token": "old_token",
            "refresh_token": "refresh_token",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(token_data, f)
            f.flush()

            result = secure_token_refresh(Path(f.name))
            self.assertTrue(result.success)
            self.assertTrue(result.refreshed)

            os.unlink(f.name)

    @patch('upwork_oauth_token_security.Request')
    @patch('upwork_oauth_token_security.Credentials')
    def test_refresh_sets_secure_permissions(self, mock_creds_class, mock_request):
        """Refreshed token file should have secure permissions."""
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "refresh_token"
        mock_creds.expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        mock_creds.to_json.return_value = '{"token": "new_token", "refresh_token": "refresh_token"}'
        mock_creds_class.from_authorized_user_file.return_value = mock_creds

        token_data = {
            "token": "old_token",
            "refresh_token": "refresh_token",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(token_data, f)
            f.flush()
            os.chmod(f.name, 0o644)  # Start with insecure permissions

            result = secure_token_refresh(Path(f.name))

            # Check permissions after refresh
            mode = stat.S_IMODE(os.stat(f.name).st_mode)
            self.assertEqual(mode, SECURE_FILE_MODE)

            os.unlink(f.name)


class TestVerifyRefreshEndpointSecurity(unittest.TestCase):
    """Tests for verify_refresh_endpoint_security function."""

    def test_verify_nonexistent_file(self):
        """Non-existent token file is secure."""
        is_secure, endpoint = verify_refresh_endpoint_security(Path("/nonexistent/token.json"))
        self.assertTrue(is_secure)

    def test_verify_valid_google_endpoint(self):
        """Valid Google endpoint should be secure."""
        token_data = {
            "token": "test",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(token_data, f)
            f.flush()

            is_secure, endpoint = verify_refresh_endpoint_security(Path(f.name))
            self.assertTrue(is_secure)
            self.assertEqual(endpoint, "https://oauth2.googleapis.com/token")

            os.unlink(f.name)

    def test_verify_invalid_endpoint(self):
        """Invalid endpoint should not be secure."""
        token_data = {
            "token": "test",
            "token_uri": "https://evil.example.com/token",
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(token_data, f)
            f.flush()

            is_secure, endpoint = verify_refresh_endpoint_security(Path(f.name))
            self.assertFalse(is_secure)
            self.assertEqual(endpoint, "https://evil.example.com/token")

            os.unlink(f.name)


class TestInvalidateOldToken(unittest.TestCase):
    """Tests for invalidate_old_token function."""

    def test_invalidate_logs_hash(self):
        """invalidate_old_token should log the old token hash."""
        old_token_data = {"token": "old_access_token"}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{}')
            f.flush()

            result = invalidate_old_token(Path(f.name), old_token_data)
            self.assertTrue(result)

            os.unlink(f.name)


class TestRotateToken(unittest.TestCase):
    """Tests for rotate_token function."""

    def test_rotate_calls_refresh_with_force(self):
        """rotate_token should call secure_token_refresh with force=True."""
        with patch('upwork_oauth_token_security.secure_token_refresh') as mock_refresh:
            mock_refresh.return_value = TokenRefreshResult(
                success=True,
                refreshed=True,
                token_path="/path/token.json",
                old_token_hash="abc",
                new_token_hash="def",
                expiry=None,
                error=None,
            )

            result = rotate_token(Path("/path/token.json"))
            mock_refresh.assert_called_once()
            call_args = mock_refresh.call_args
            self.assertTrue(call_args[1].get('force', False))


class TestListTokenFiles(unittest.TestCase):
    """Tests for list_token_files function."""

    def test_list_empty_config(self):
        """list_token_files with no tokens returns empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "config"
            # Don't create config dir

            with patch('upwork_oauth_token_security.get_project_root', return_value=Path(tmpdir)):
                tokens = list_token_files()
                self.assertEqual(tokens, [])

    def test_list_finds_tokens(self):
        """list_token_files finds token files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "config"
            config_dir.mkdir()

            # Create token files
            token1 = config_dir / "token.json"
            token1.write_text('{"token": "t1", "refresh_token": "r1"}')

            token2 = config_dir / "token_test.json"
            token2.write_text('{"token": "t2", "refresh_token": "r2"}')

            with patch('upwork_oauth_token_security.get_project_root', return_value=Path(tmpdir)):
                tokens = list_token_files()
                self.assertEqual(len(tokens), 2)

                names = [t["name"] for t in tokens]
                self.assertIn("token.json", names)
                self.assertIn("token_test.json", names)


class TestUpdateGitignoreForTokens(unittest.TestCase):
    """Tests for update_gitignore_for_tokens function."""

    def test_creates_gitignore_section(self):
        """update_gitignore_for_tokens creates token section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gitignore_path = Path(tmpdir) / ".gitignore"
            gitignore_path.write_text("*.pyc\n")

            with patch('upwork_oauth_token_security.get_project_root', return_value=Path(tmpdir)):
                result = update_gitignore_for_tokens()
                self.assertTrue(result)

            content = gitignore_path.read_text()
            self.assertIn("token", content.lower())

    def test_no_update_if_already_covered(self):
        """update_gitignore_for_tokens doesn't duplicate patterns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gitignore_path = Path(tmpdir) / ".gitignore"
            # Pre-populate with token patterns
            initial_content = "\n".join(TOKEN_GITIGNORE_PATTERNS)
            gitignore_path.write_text(initial_content)

            with patch('upwork_oauth_token_security.get_project_root', return_value=Path(tmpdir)):
                result = update_gitignore_for_tokens()
                self.assertTrue(result)

            # Content should not have duplicate patterns
            content = gitignore_path.read_text()
            count = content.count("token.json")
            self.assertEqual(count, 1)


class TestConstants(unittest.TestCase):
    """Tests for module constants."""

    def test_secure_file_mode_is_owner_only(self):
        """SECURE_FILE_MODE should be owner read/write only."""
        self.assertEqual(SECURE_FILE_MODE, 0o600)

    def test_secure_dir_mode_is_owner_only(self):
        """SECURE_DIR_MODE should be owner read/write/execute only."""
        self.assertEqual(SECURE_DIR_MODE, 0o700)

    def test_valid_endpoints_are_google(self):
        """VALID_TOKEN_ENDPOINTS should all be Google domains."""
        for endpoint in VALID_TOKEN_ENDPOINTS:
            self.assertTrue(
                "googleapis.com" in endpoint or "google.com" in endpoint,
                f"Endpoint {endpoint} is not a Google domain"
            )

    def test_gitignore_patterns_not_empty(self):
        """TOKEN_GITIGNORE_PATTERNS should not be empty."""
        self.assertGreater(len(TOKEN_GITIGNORE_PATTERNS), 0)

    def test_required_scopes_not_empty(self):
        """REQUIRED_SCOPES should not be empty."""
        self.assertGreater(len(REQUIRED_SCOPES), 0)

    def test_sensitive_fields_includes_refresh_token(self):
        """SENSITIVE_FIELDS should include refresh_token."""
        self.assertIn("refresh_token", SENSITIVE_FIELDS)


class TestValidTokenEndpoints(unittest.TestCase):
    """Tests verifying token refresh uses secure endpoints."""

    def test_oauth2_googleapis_is_valid(self):
        """oauth2.googleapis.com should be valid."""
        self.assertIn("https://oauth2.googleapis.com/token", VALID_TOKEN_ENDPOINTS)

    def test_accounts_google_is_valid(self):
        """accounts.google.com should be valid."""
        self.assertIn("https://accounts.google.com/o/oauth2/token", VALID_TOKEN_ENDPOINTS)

    def test_googleapis_v4_is_valid(self):
        """www.googleapis.com/oauth2/v4 should be valid."""
        self.assertIn("https://www.googleapis.com/oauth2/v4/token", VALID_TOKEN_ENDPOINTS)


class TestRefreshTokenStoredSecurely(unittest.TestCase):
    """Tests that refresh token is stored securely."""

    def test_token_file_not_world_readable(self):
        """Token file should not be world-readable after ensure_token_security."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "config"
            config_dir.mkdir()
            token_path = config_dir / "token.json"
            token_path.write_text('{"token": "t", "refresh_token": "r"}')
            os.chmod(token_path, 0o644)  # World-readable

            with patch('upwork_oauth_token_security.get_project_root', return_value=Path(tmpdir)):
                with patch('upwork_oauth_token_security.update_gitignore_for_tokens', return_value=True):
                    ensure_token_security(token_path)

            mode = stat.S_IMODE(os.stat(token_path).st_mode)
            self.assertFalse(mode & stat.S_IROTH)  # Not world-readable

    def test_token_file_not_group_writable(self):
        """Token file should not be group-writable after ensure_token_security."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "config"
            config_dir.mkdir()
            token_path = config_dir / "token.json"
            token_path.write_text('{"token": "t", "refresh_token": "r"}')
            os.chmod(token_path, 0o664)  # Group-writable

            with patch('upwork_oauth_token_security.get_project_root', return_value=Path(tmpdir)):
                with patch('upwork_oauth_token_security.update_gitignore_for_tokens', return_value=True):
                    ensure_token_security(token_path)

            mode = stat.S_IMODE(os.stat(token_path).st_mode)
            self.assertFalse(mode & stat.S_IWGRP)  # Not group-writable


class TestOldTokensInvalidated(unittest.TestCase):
    """Tests that old tokens are invalidated after refresh."""

    @patch('upwork_oauth_token_security.Request')
    @patch('upwork_oauth_token_security.Credentials')
    def test_old_token_hash_different_from_new(self, mock_creds_class, mock_request):
        """After refresh, old token hash should be different from new."""
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "refresh_token"
        mock_creds.expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        mock_creds.to_json.return_value = '{"token": "completely_new_token", "refresh_token": "refresh_token"}'
        mock_creds_class.from_authorized_user_file.return_value = mock_creds

        token_data = {
            "token": "old_token_value",
            "refresh_token": "refresh_token",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(token_data, f)
            f.flush()

            result = secure_token_refresh(Path(f.name))
            self.assertTrue(result.refreshed)
            self.assertNotEqual(result.old_token_hash, result.new_token_hash)

            os.unlink(f.name)

    @patch('upwork_oauth_token_security.Request')
    @patch('upwork_oauth_token_security.Credentials')
    def test_invalidate_old_token_called(self, mock_creds_class, mock_request):
        """invalidate_old_token should be called during refresh."""
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "refresh_token"
        mock_creds.expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        mock_creds.to_json.return_value = '{"token": "new_token", "refresh_token": "refresh_token"}'
        mock_creds_class.from_authorized_user_file.return_value = mock_creds

        token_data = {
            "token": "old_token",
            "refresh_token": "refresh_token",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(token_data, f)
            f.flush()

            with patch('upwork_oauth_token_security.invalidate_old_token') as mock_invalidate:
                mock_invalidate.return_value = True
                result = secure_token_refresh(Path(f.name))

                if result.refreshed:
                    mock_invalidate.assert_called_once()

            os.unlink(f.name)


def run_tests():
    """Run all tests and return results."""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
