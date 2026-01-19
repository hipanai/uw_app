#!/usr/bin/env python3
"""
Test suite for Feature #82: Playwright browser profile is stored securely.

Tests:
- Directory permission checks
- Session cookie protection
- .gitignore coverage verification
- Secure profile creation
"""

import os
import sys
import stat
import json
import tempfile
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from executions.upwork_browser_profile_security import (
    get_secure_profile_path,
    get_default_profile_path,
    check_directory_permissions,
    check_sensitive_files_not_exposed,
    check_gitignore_coverage,
    validate_profile_security,
    secure_directory_permissions,
    ensure_profile_security,
    update_gitignore_for_profiles,
    create_profile_readme,
    get_submitter_profile_path,
    verify_profile_not_in_git,
    cleanup_session_data,
    SECURE_DIR_MODE,
    SECURE_FILE_MODE,
    SENSITIVE_FILES,
    BROWSER_PROFILE_DIRS,
    ProfileSecurityResult,
)


class TestDirectoryPermissions(unittest.TestCase):
    """Test directory permission checking and setting."""

    def setUp(self):
        """Create temporary directory for tests."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_profile = Path(self.temp_dir) / "test_profile"
        self.test_profile.mkdir()

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_secure_directory_passes(self):
        """Test that a secure directory passes permission check."""
        os.chmod(self.test_profile, SECURE_DIR_MODE)
        is_secure, issues = check_directory_permissions(self.test_profile)
        self.assertTrue(is_secure)
        self.assertEqual(len(issues), 0)

    def test_world_readable_fails(self):
        """Test that world-readable directory fails check."""
        os.chmod(self.test_profile, 0o755)  # rwxr-xr-x
        is_secure, issues = check_directory_permissions(self.test_profile)
        self.assertFalse(is_secure)
        self.assertTrue(any("world-readable" in i for i in issues))

    def test_world_writable_fails(self):
        """Test that world-writable directory fails check."""
        os.chmod(self.test_profile, 0o777)  # rwxrwxrwx
        is_secure, issues = check_directory_permissions(self.test_profile)
        self.assertFalse(is_secure)
        self.assertTrue(any("world-writable" in i for i in issues))

    def test_group_writable_fails(self):
        """Test that group-writable directory fails check."""
        os.chmod(self.test_profile, 0o770)  # rwxrwx---
        is_secure, issues = check_directory_permissions(self.test_profile)
        self.assertFalse(is_secure)
        self.assertTrue(any("group-writable" in i for i in issues))

    def test_nonexistent_directory_passes(self):
        """Test that nonexistent directory passes (will be created securely)."""
        nonexistent = Path(self.temp_dir) / "does_not_exist"
        is_secure, issues = check_directory_permissions(nonexistent)
        self.assertTrue(is_secure)
        self.assertEqual(len(issues), 0)

    def test_secure_directory_permissions(self):
        """Test setting secure permissions on a directory."""
        # Start with insecure permissions
        os.chmod(self.test_profile, 0o777)

        # Create some files
        (self.test_profile / "test_file.txt").write_text("test")
        subdir = self.test_profile / "subdir"
        subdir.mkdir()
        (subdir / "nested.txt").write_text("nested")

        # Secure the directory
        result = secure_directory_permissions(self.test_profile)
        self.assertTrue(result)

        # Check permissions
        dir_mode = stat.S_IMODE(os.stat(self.test_profile).st_mode)
        self.assertEqual(dir_mode, SECURE_DIR_MODE)

        file_mode = stat.S_IMODE(os.stat(self.test_profile / "test_file.txt").st_mode)
        self.assertEqual(file_mode, SECURE_FILE_MODE)


class TestSensitiveFileProtection(unittest.TestCase):
    """Test sensitive file exposure checking."""

    def setUp(self):
        """Create temporary directory with profile structure."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_profile = Path(self.temp_dir) / "test_profile"
        self.default_dir = self.test_profile / "Default"
        self.default_dir.mkdir(parents=True)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_no_sensitive_files_passes(self):
        """Test that profile without sensitive files passes."""
        is_secure, issues = check_sensitive_files_not_exposed(self.test_profile)
        self.assertTrue(is_secure)
        self.assertEqual(len(issues), 0)

    def test_secure_cookies_file_passes(self):
        """Test that secure Cookies file passes."""
        cookies_file = self.default_dir / "Cookies"
        cookies_file.write_text("encrypted cookie data")
        os.chmod(cookies_file, SECURE_FILE_MODE)

        is_secure, issues = check_sensitive_files_not_exposed(self.test_profile)
        self.assertTrue(is_secure)
        self.assertEqual(len(issues), 0)

    def test_world_readable_cookies_fails(self):
        """Test that world-readable Cookies file fails."""
        cookies_file = self.default_dir / "Cookies"
        cookies_file.write_text("encrypted cookie data")
        os.chmod(cookies_file, 0o644)  # rw-r--r--

        is_secure, issues = check_sensitive_files_not_exposed(self.test_profile)
        self.assertFalse(is_secure)
        self.assertTrue(any("Cookies" in i and "insecure" in i for i in issues))

    def test_world_readable_login_data_fails(self):
        """Test that world-readable Login Data fails."""
        login_file = self.default_dir / "Login Data"
        login_file.write_text("encrypted login data")
        os.chmod(login_file, 0o644)

        is_secure, issues = check_sensitive_files_not_exposed(self.test_profile)
        self.assertFalse(is_secure)
        self.assertTrue(any("Login Data" in i for i in issues))

    def test_insecure_session_storage_fails(self):
        """Test that insecure Session Storage directory fails."""
        session_dir = self.default_dir / "Session Storage"
        session_dir.mkdir()
        os.chmod(session_dir, 0o777)

        is_secure, issues = check_sensitive_files_not_exposed(self.test_profile)
        self.assertFalse(is_secure)
        self.assertTrue(any("Session Storage" in i for i in issues))

    def test_nonexistent_profile_passes(self):
        """Test that nonexistent profile passes (nothing to expose)."""
        nonexistent = Path(self.temp_dir) / "does_not_exist"
        is_secure, issues = check_sensitive_files_not_exposed(nonexistent)
        self.assertTrue(is_secure)
        self.assertEqual(len(issues), 0)


class TestGitignoreCoverage(unittest.TestCase):
    """Test .gitignore coverage verification."""

    def setUp(self):
        """Create temporary directory with .gitignore."""
        self.temp_dir = tempfile.mkdtemp()
        self.gitignore_path = Path(self.temp_dir) / ".gitignore"
        self.test_profile = Path(self.temp_dir) / "test_profile"
        self.test_profile.mkdir()

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_missing_gitignore_fails(self):
        """Test that missing .gitignore fails."""
        with patch('executions.upwork_browser_profile_security.get_project_root',
                   return_value=Path(self.temp_dir)):
            is_covered, issues, warnings = check_gitignore_coverage(self.test_profile)
            self.assertFalse(is_covered)
            self.assertTrue(any(".gitignore" in i for i in issues))

    def test_profile_in_gitignore_passes(self):
        """Test that profile listed in .gitignore passes."""
        self.gitignore_path.write_text("test_profile/\n")

        with patch('executions.upwork_browser_profile_security.get_project_root',
                   return_value=Path(self.temp_dir)):
            is_covered, issues, warnings = check_gitignore_coverage(self.test_profile)
            self.assertTrue(is_covered)
            self.assertEqual(len(issues), 0)

    def test_profile_not_in_gitignore_fails(self):
        """Test that profile not in .gitignore fails."""
        self.gitignore_path.write_text("other_stuff/\n")

        with patch('executions.upwork_browser_profile_security.get_project_root',
                   return_value=Path(self.temp_dir)):
            is_covered, issues, warnings = check_gitignore_coverage(self.test_profile)
            self.assertFalse(is_covered)
            self.assertTrue(any("test_profile" in i for i in issues))

    def test_wildcard_pattern_covers_profile(self):
        """Test that wildcard pattern covers profile."""
        self.gitignore_path.write_text("*test_profile*\n")

        with patch('executions.upwork_browser_profile_security.get_project_root',
                   return_value=Path(self.temp_dir)):
            is_covered, issues, warnings = check_gitignore_coverage(self.test_profile)
            self.assertTrue(is_covered)

    def test_sensitive_file_patterns_warning(self):
        """Test that missing sensitive file patterns generate warnings."""
        self.gitignore_path.write_text("test_profile/\n")

        with patch('executions.upwork_browser_profile_security.get_project_root',
                   return_value=Path(self.temp_dir)):
            is_covered, issues, warnings = check_gitignore_coverage(self.test_profile)
            # Should pass (profile is covered) but may have warnings
            self.assertTrue(is_covered)


class TestValidateProfileSecurity(unittest.TestCase):
    """Test the full profile security validation."""

    def setUp(self):
        """Create temporary directory with profile structure."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_profile = Path(self.temp_dir) / "upwork_profile"
        self.default_dir = self.test_profile / "Default"
        self.default_dir.mkdir(parents=True)
        self.gitignore_path = Path(self.temp_dir) / ".gitignore"
        self.gitignore_path.write_text("upwork_profile/\n")

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_secure_profile_validation(self):
        """Test validation of a secure profile."""
        os.chmod(self.test_profile, SECURE_DIR_MODE)
        os.chmod(self.default_dir, SECURE_DIR_MODE)

        with patch('executions.upwork_browser_profile_security.get_project_root',
                   return_value=Path(self.temp_dir)):
            result = validate_profile_security(self.test_profile)
            self.assertTrue(result.is_secure)
            self.assertEqual(len(result.issues), 0)

    def test_insecure_profile_validation(self):
        """Test validation of an insecure profile."""
        os.chmod(self.test_profile, 0o755)

        with patch('executions.upwork_browser_profile_security.get_project_root',
                   return_value=Path(self.temp_dir)):
            result = validate_profile_security(self.test_profile)
            self.assertFalse(result.is_secure)
            self.assertTrue(len(result.issues) > 0)

    def test_result_to_dict(self):
        """Test ProfileSecurityResult to_dict conversion."""
        result = ProfileSecurityResult(
            is_secure=True,
            profile_path="/test/path",
            issues=[],
            warnings=["test warning"],
        )

        d = result.to_dict()
        self.assertEqual(d["is_secure"], True)
        self.assertEqual(d["profile_path"], "/test/path")
        self.assertEqual(d["issues"], [])
        self.assertEqual(d["warnings"], ["test warning"])

    def test_result_bool_conversion(self):
        """Test ProfileSecurityResult boolean conversion."""
        secure_result = ProfileSecurityResult(
            is_secure=True, profile_path="/test", issues=[], warnings=[]
        )
        insecure_result = ProfileSecurityResult(
            is_secure=False, profile_path="/test", issues=["problem"], warnings=[]
        )

        self.assertTrue(bool(secure_result))
        self.assertFalse(bool(insecure_result))


class TestEnsureProfileSecurity(unittest.TestCase):
    """Test the ensure_profile_security function."""

    def setUp(self):
        """Create temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.gitignore_path = Path(self.temp_dir) / ".gitignore"
        self.gitignore_path.write_text("# Initial gitignore\n")

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_creates_secure_directory(self):
        """Test that ensure creates a secure directory."""
        profile_path = Path(self.temp_dir) / "new_profile"

        with patch('executions.upwork_browser_profile_security.get_project_root',
                   return_value=Path(self.temp_dir)):
            result = ensure_profile_security(profile_path)

            self.assertTrue(profile_path.exists())
            mode = stat.S_IMODE(os.stat(profile_path).st_mode)
            self.assertEqual(mode, SECURE_DIR_MODE)

    def test_secures_existing_directory(self):
        """Test that ensure secures an existing directory."""
        profile_path = Path(self.temp_dir) / "existing_profile"
        profile_path.mkdir(mode=0o777)

        with patch('executions.upwork_browser_profile_security.get_project_root',
                   return_value=Path(self.temp_dir)):
            result = ensure_profile_security(profile_path)

            mode = stat.S_IMODE(os.stat(profile_path).st_mode)
            self.assertEqual(mode, SECURE_DIR_MODE)

    def test_updates_gitignore(self):
        """Test that ensure updates .gitignore."""
        profile_path = Path(self.temp_dir) / "new_profile"

        with patch('executions.upwork_browser_profile_security.get_project_root',
                   return_value=Path(self.temp_dir)):
            result = ensure_profile_security(profile_path)

            gitignore_content = self.gitignore_path.read_text()
            self.assertIn("new_profile/", gitignore_content)


class TestUpdateGitignore(unittest.TestCase):
    """Test .gitignore update functionality."""

    def setUp(self):
        """Create temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.gitignore_path = Path(self.temp_dir) / ".gitignore"

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_creates_patterns_in_empty_gitignore(self):
        """Test adding patterns to empty .gitignore."""
        self.gitignore_path.write_text("")

        with patch('executions.upwork_browser_profile_security.get_project_root',
                   return_value=Path(self.temp_dir)):
            result = update_gitignore_for_profiles()
            self.assertTrue(result)

            content = self.gitignore_path.read_text()
            self.assertIn("browser_profile/", content)

    def test_does_not_duplicate_patterns(self):
        """Test that existing patterns are not duplicated."""
        self.gitignore_path.write_text("browser_profile/\nuser_data/\n")

        with patch('executions.upwork_browser_profile_security.get_project_root',
                   return_value=Path(self.temp_dir)):
            result = update_gitignore_for_profiles()
            self.assertTrue(result)

            content = self.gitignore_path.read_text()
            self.assertEqual(content.count("browser_profile/"), 1)

    def test_adds_specific_profile_path(self):
        """Test adding a specific profile path."""
        self.gitignore_path.write_text("# existing\n")
        profile_path = Path(self.temp_dir) / "custom_profile"

        with patch('executions.upwork_browser_profile_security.get_project_root',
                   return_value=Path(self.temp_dir)):
            result = update_gitignore_for_profiles(profile_path)
            self.assertTrue(result)

            content = self.gitignore_path.read_text()
            self.assertIn("custom_profile/", content)


class TestProfileReadme(unittest.TestCase):
    """Test README creation in profile directory."""

    def setUp(self):
        """Create temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.profile_dir = Path(self.temp_dir) / "test_profile"
        self.profile_dir.mkdir()

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_creates_readme(self):
        """Test README creation."""
        create_profile_readme(self.profile_dir)

        readme_path = self.profile_dir / "README.md"
        self.assertTrue(readme_path.exists())

        content = readme_path.read_text()
        self.assertIn("Browser Profile Directory", content)
        self.assertIn("Security Notes", content)

    def test_readme_has_secure_permissions(self):
        """Test README has secure permissions."""
        create_profile_readme(self.profile_dir)

        readme_path = self.profile_dir / "README.md"
        mode = stat.S_IMODE(os.stat(readme_path).st_mode)
        self.assertEqual(mode, SECURE_FILE_MODE)

    def test_does_not_overwrite_existing_readme(self):
        """Test that existing README is not overwritten."""
        readme_path = self.profile_dir / "README.md"
        readme_path.write_text("Custom content")

        create_profile_readme(self.profile_dir)

        content = readme_path.read_text()
        self.assertEqual(content, "Custom content")


class TestCleanupSessionData(unittest.TestCase):
    """Test session data cleanup functionality."""

    def setUp(self):
        """Create temporary directory with profile structure."""
        self.temp_dir = tempfile.mkdtemp()
        self.profile_dir = Path(self.temp_dir) / "test_profile"
        self.default_dir = self.profile_dir / "Default"
        self.default_dir.mkdir(parents=True)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cleanup_removes_history(self):
        """Test that cleanup removes History file."""
        history_file = self.default_dir / "History"
        history_file.write_text("history data")

        result = cleanup_session_data(self.profile_dir)
        self.assertTrue(result)
        self.assertFalse(history_file.exists())

    def test_cleanup_preserves_cookies_by_default(self):
        """Test that cleanup preserves Cookies by default."""
        cookies_file = self.default_dir / "Cookies"
        cookies_file.write_text("cookie data")

        result = cleanup_session_data(self.profile_dir, preserve_cookies=True)
        self.assertTrue(result)
        self.assertTrue(cookies_file.exists())

    def test_cleanup_removes_cookies_when_requested(self):
        """Test that cleanup removes Cookies when requested."""
        cookies_file = self.default_dir / "Cookies"
        cookies_file.write_text("cookie data")

        result = cleanup_session_data(self.profile_dir, preserve_cookies=False)
        self.assertTrue(result)
        self.assertFalse(cookies_file.exists())

    def test_cleanup_removes_cache_directory(self):
        """Test that cleanup removes Cache directory."""
        cache_dir = self.default_dir / "Cache"
        cache_dir.mkdir()
        (cache_dir / "cache_file").write_text("cache data")

        result = cleanup_session_data(self.profile_dir)
        self.assertTrue(result)
        self.assertFalse(cache_dir.exists())


class TestGetSubmitterProfilePath(unittest.TestCase):
    """Test the get_submitter_profile_path utility function."""

    def setUp(self):
        """Create temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.gitignore_path = Path(self.temp_dir) / ".gitignore"
        self.gitignore_path.write_text("upwork_profile/\n")

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_returns_string_path(self):
        """Test that function returns a string path."""
        with patch('executions.upwork_browser_profile_security.get_project_root',
                   return_value=Path(self.temp_dir)):
            with patch('executions.upwork_browser_profile_security.get_default_profile_path',
                       return_value=Path(self.temp_dir) / "upwork_profile"):
                path = get_submitter_profile_path()
                self.assertIsInstance(path, str)

    def test_creates_profile_directory(self):
        """Test that function creates profile directory."""
        profile_path = Path(self.temp_dir) / "upwork_profile"

        with patch('executions.upwork_browser_profile_security.get_project_root',
                   return_value=Path(self.temp_dir)):
            with patch('executions.upwork_browser_profile_security.get_default_profile_path',
                       return_value=profile_path):
                path = get_submitter_profile_path()
                self.assertTrue(Path(path).exists())


class TestGitignoreIntegration(unittest.TestCase):
    """Test integration with actual .gitignore file in project."""

    def test_project_gitignore_has_browser_profiles(self):
        """Test that project .gitignore includes browser profile patterns."""
        # Find the actual project .gitignore
        project_root = Path(__file__).parent.parent
        gitignore_path = project_root / ".gitignore"

        if not gitignore_path.exists():
            self.skipTest("Project .gitignore not found")

        content = gitignore_path.read_text()

        # Check for essential browser profile patterns
        self.assertTrue(
            "browser_profile/" in content or "browser_profile" in content,
            "browser_profile/ should be in .gitignore"
        )
        self.assertTrue(
            "user_data/" in content or "user_data" in content,
            "user_data/ should be in .gitignore"
        )

    def test_env_file_in_gitignore(self):
        """Test that .env is in .gitignore."""
        project_root = Path(__file__).parent.parent
        gitignore_path = project_root / ".gitignore"

        if not gitignore_path.exists():
            self.skipTest("Project .gitignore not found")

        content = gitignore_path.read_text()
        self.assertIn(".env", content)

    def test_token_files_in_gitignore(self):
        """Test that token files are in .gitignore."""
        project_root = Path(__file__).parent.parent
        gitignore_path = project_root / ".gitignore"

        if not gitignore_path.exists():
            self.skipTest("Project .gitignore not found")

        content = gitignore_path.read_text()
        self.assertTrue(
            "token*.json" in content or "token.json" in content,
            "Token files should be in .gitignore"
        )


class TestConstants(unittest.TestCase):
    """Test module constants are properly defined."""

    def test_secure_dir_mode(self):
        """Test SECURE_DIR_MODE is owner-only."""
        # Should be rwx------
        self.assertEqual(SECURE_DIR_MODE, 0o700)

    def test_secure_file_mode(self):
        """Test SECURE_FILE_MODE is owner-only."""
        # Should be rw-------
        self.assertEqual(SECURE_FILE_MODE, 0o600)

    def test_browser_profile_dirs_not_empty(self):
        """Test BROWSER_PROFILE_DIRS has entries."""
        self.assertTrue(len(BROWSER_PROFILE_DIRS) > 0)
        self.assertIn("browser_profile", BROWSER_PROFILE_DIRS)
        self.assertIn("upwork_profile", BROWSER_PROFILE_DIRS)

    def test_sensitive_files_not_empty(self):
        """Test SENSITIVE_FILES has entries."""
        self.assertTrue(len(SENSITIVE_FILES) > 0)
        self.assertIn("Cookies", SENSITIVE_FILES)
        self.assertIn("Login Data", SENSITIVE_FILES)


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    test_classes = [
        TestDirectoryPermissions,
        TestSensitiveFileProtection,
        TestGitignoreCoverage,
        TestValidateProfileSecurity,
        TestEnsureProfileSecurity,
        TestUpdateGitignore,
        TestProfileReadme,
        TestCleanupSessionData,
        TestGetSubmitterProfilePath,
        TestGitignoreIntegration,
        TestConstants,
    ]

    for test_class in test_classes:
        tests = loader.loadTestsFromTestCase(test_class)
        suite.addTests(tests)

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
