#!/usr/bin/env python3
"""
Test suite for upwork_attachment_scanner.py - Feature #84

Tests covering:
1. File type detection from magic bytes
2. Extension validation
3. Executable content detection
4. PDF script detection
5. Office macro detection
6. Archive security checks
7. File type mismatch detection
8. Scan result structure
9. Batch scanning
10. Integration tests

Feature #84: Job attachments are scanned for malicious content
- Download job attachment
- Run basic security checks
- Verify no executable content
- Verify file type matches extension
"""

import os
import sys
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

# Add executions directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from upwork_attachment_scanner import (
    ScanResult,
    scan_attachment,
    scan_directory,
    scan_attachments_batch,
    filter_safe_attachments,
    validate_attachment_for_processing,
    get_scan_summary,
    get_file_extension,
    compute_file_hash,
    read_file_header,
    detect_file_type,
    detect_office_format,
    check_extension_matches_type,
    check_for_executable_content,
    check_pdf_for_scripts,
    check_office_for_macros,
    check_archive_for_threats,
    check_dangerous_extension,
    check_allowed_extension,
    DANGEROUS_EXTENSIONS,
    ALLOWED_EXTENSIONS,
    FILE_SIGNATURES,
    MAX_FILE_SIZE,
    MAX_DECOMPRESSED_SIZE,
    ARCHIVE_BOMB_RATIO,
)


class TestScanResult(unittest.TestCase):
    """Test ScanResult dataclass."""

    def test_scan_result_creation(self):
        """Test creating a ScanResult."""
        result = ScanResult(
            file_path='/tmp/test.pdf',
            file_name='test.pdf',
            file_size=1024,
            file_extension='pdf',
            detected_type='pdf',
            is_safe=True,
        )
        self.assertEqual(result.file_path, '/tmp/test.pdf')
        self.assertEqual(result.file_name, 'test.pdf')
        self.assertTrue(result.is_safe)
        self.assertEqual(result.issues, [])
        self.assertEqual(result.warnings, [])

    def test_scan_result_to_dict(self):
        """Test ScanResult.to_dict() method."""
        result = ScanResult(
            file_path='/tmp/test.pdf',
            file_name='test.pdf',
            file_size=1024,
            file_extension='pdf',
            detected_type='pdf',
            is_safe=False,
            issues=['Test issue'],
            warnings=['Test warning'],
            file_hash='abc123',
        )
        d = result.to_dict()
        self.assertEqual(d['file_path'], '/tmp/test.pdf')
        self.assertEqual(d['is_safe'], False)
        self.assertEqual(d['issues'], ['Test issue'])
        self.assertEqual(d['warnings'], ['Test warning'])
        self.assertEqual(d['file_hash'], 'abc123')

    def test_scan_result_bool_safe(self):
        """Test ScanResult.__bool__() for safe file."""
        result = ScanResult(
            file_path='/tmp/test.pdf',
            file_name='test.pdf',
            file_size=1024,
            file_extension='pdf',
            detected_type='pdf',
            is_safe=True,
        )
        self.assertTrue(bool(result))
        self.assertTrue(result)

    def test_scan_result_bool_unsafe(self):
        """Test ScanResult.__bool__() for unsafe file."""
        result = ScanResult(
            file_path='/tmp/test.exe',
            file_name='test.exe',
            file_size=1024,
            file_extension='exe',
            detected_type='exe',
            is_safe=False,
            issues=['Executable file'],
        )
        self.assertFalse(bool(result))
        self.assertFalse(result)


class TestFileExtension(unittest.TestCase):
    """Test file extension extraction."""

    def test_get_extension_simple(self):
        """Test simple file extension."""
        self.assertEqual(get_file_extension('test.pdf'), 'pdf')
        self.assertEqual(get_file_extension('test.PDF'), 'pdf')
        self.assertEqual(get_file_extension('test.Pdf'), 'pdf')

    def test_get_extension_double(self):
        """Test double extension."""
        self.assertEqual(get_file_extension('test.tar.gz'), 'gz')
        self.assertEqual(get_file_extension('test.pdf.exe'), 'exe')

    def test_get_extension_none(self):
        """Test file with no extension."""
        self.assertEqual(get_file_extension('test'), '')
        self.assertEqual(get_file_extension('testfile'), '')

    def test_get_extension_path(self):
        """Test with full path."""
        self.assertEqual(get_file_extension('/path/to/test.pdf'), 'pdf')
        self.assertEqual(get_file_extension('/path/to/file.docx'), 'docx')


class TestFileHash(unittest.TestCase):
    """Test file hash computation."""

    def test_hash_computation(self):
        """Test computing file hash."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b'test content')
            temp_path = f.name

        try:
            hash_value = compute_file_hash(temp_path)
            self.assertEqual(len(hash_value), 64)  # SHA256 hex length
            self.assertTrue(all(c in '0123456789abcdef' for c in hash_value))
        finally:
            os.unlink(temp_path)

    def test_hash_nonexistent_file(self):
        """Test hash of nonexistent file."""
        hash_value = compute_file_hash('/nonexistent/file.pdf')
        self.assertEqual(hash_value, '')

    def test_hash_same_content_same_hash(self):
        """Test same content produces same hash."""
        with tempfile.NamedTemporaryFile(delete=False) as f1:
            f1.write(b'identical content')
            path1 = f1.name

        with tempfile.NamedTemporaryFile(delete=False) as f2:
            f2.write(b'identical content')
            path2 = f2.name

        try:
            hash1 = compute_file_hash(path1)
            hash2 = compute_file_hash(path2)
            self.assertEqual(hash1, hash2)
        finally:
            os.unlink(path1)
            os.unlink(path2)


class TestFileTypeDetection(unittest.TestCase):
    """Test file type detection from magic bytes."""

    def test_detect_pdf(self):
        """Test detecting PDF file."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
            f.write(b'%PDF-1.4\n%...')
            temp_path = f.name

        try:
            detected = detect_file_type(temp_path)
            self.assertEqual(detected, 'pdf')
        finally:
            os.unlink(temp_path)

    def test_detect_png(self):
        """Test detecting PNG file."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as f:
            f.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR')
            temp_path = f.name

        try:
            detected = detect_file_type(temp_path)
            self.assertEqual(detected, 'png')
        finally:
            os.unlink(temp_path)

    def test_detect_jpeg(self):
        """Test detecting JPEG file."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as f:
            f.write(b'\xff\xd8\xff\xe0\x00\x10JFIF')
            temp_path = f.name

        try:
            detected = detect_file_type(temp_path)
            self.assertEqual(detected, 'jpg')
        finally:
            os.unlink(temp_path)

    def test_detect_exe(self):
        """Test detecting Windows executable."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.exe') as f:
            f.write(b'MZ\x90\x00\x03\x00\x00\x00')
            temp_path = f.name

        try:
            detected = detect_file_type(temp_path)
            self.assertEqual(detected, 'exe')
        finally:
            os.unlink(temp_path)

    def test_detect_elf(self):
        """Test detecting Linux executable."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.bin') as f:
            f.write(b'\x7fELF\x02\x01\x01\x00')
            temp_path = f.name

        try:
            detected = detect_file_type(temp_path)
            self.assertEqual(detected, 'elf')
        finally:
            os.unlink(temp_path)

    def test_detect_zip(self):
        """Test detecting ZIP file."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as f:
            temp_path = f.name

        try:
            # Create actual zip file
            with zipfile.ZipFile(temp_path, 'w') as zf:
                zf.writestr('test.txt', 'test content')

            detected = detect_file_type(temp_path)
            self.assertEqual(detected, 'zip')
        finally:
            os.unlink(temp_path)

    def test_detect_rtf(self):
        """Test detecting RTF file."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.rtf') as f:
            f.write(b'{\\rtf1\\ansi\\deff0')
            temp_path = f.name

        try:
            detected = detect_file_type(temp_path)
            self.assertEqual(detected, 'rtf')
        finally:
            os.unlink(temp_path)

    def test_detect_unknown(self):
        """Test detecting unknown file type."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xyz') as f:
            f.write(b'\x00\x01\x02\x03\x04\x05')
            temp_path = f.name

        try:
            detected = detect_file_type(temp_path)
            self.assertEqual(detected, 'unknown')
        finally:
            os.unlink(temp_path)


class TestExtensionMatching(unittest.TestCase):
    """Test extension vs detected type matching."""

    def test_exact_match(self):
        """Test exact extension match."""
        matches, reason = check_extension_matches_type('pdf', 'pdf')
        self.assertTrue(matches)

    def test_equivalent_match_jpg_jpeg(self):
        """Test jpg/jpeg equivalence."""
        matches, _ = check_extension_matches_type('jpg', 'jpeg')
        self.assertTrue(matches)

        matches, _ = check_extension_matches_type('jpeg', 'jpg')
        self.assertTrue(matches)

    def test_docx_zip_match(self):
        """Test docx detected as zip is OK."""
        matches, _ = check_extension_matches_type('docx', 'zip')
        self.assertTrue(matches)

    def test_mismatch(self):
        """Test mismatched extension and type."""
        matches, reason = check_extension_matches_type('pdf', 'exe')
        self.assertFalse(matches)
        self.assertIn('does not match', reason)

    def test_unknown_type(self):
        """Test unknown type always matches."""
        matches, _ = check_extension_matches_type('pdf', 'unknown')
        self.assertTrue(matches)


class TestExecutableDetection(unittest.TestCase):
    """Test executable content detection."""

    def test_detect_pe_executable(self):
        """Test detecting PE (Windows) executable."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.exe') as f:
            f.write(b'MZ\x90\x00\x03\x00\x00\x00')
            temp_path = f.name

        try:
            has_exec, issues = check_for_executable_content(temp_path)
            self.assertTrue(has_exec)
            self.assertTrue(any('Windows executable' in i for i in issues))
        finally:
            os.unlink(temp_path)

    def test_detect_elf_executable(self):
        """Test detecting ELF (Linux) executable."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.bin') as f:
            f.write(b'\x7fELF\x02\x01\x01\x00')
            temp_path = f.name

        try:
            has_exec, issues = check_for_executable_content(temp_path)
            self.assertTrue(has_exec)
            self.assertTrue(any('Linux executable' in i for i in issues))
        finally:
            os.unlink(temp_path)

    def test_detect_shell_script(self):
        """Test detecting shell script."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.sh') as f:
            f.write(b'#!/bin/bash\necho "test"')
            temp_path = f.name

        try:
            has_exec, issues = check_for_executable_content(temp_path)
            self.assertTrue(has_exec)
            self.assertTrue(any('shell script' in i for i in issues))
        finally:
            os.unlink(temp_path)

    def test_safe_pdf(self):
        """Test safe PDF has no executable."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
            f.write(b'%PDF-1.4\n%...')
            temp_path = f.name

        try:
            has_exec, issues = check_for_executable_content(temp_path)
            self.assertFalse(has_exec)
            self.assertEqual(issues, [])
        finally:
            os.unlink(temp_path)


class TestPDFScriptDetection(unittest.TestCase):
    """Test PDF JavaScript detection."""

    def test_pdf_with_javascript(self):
        """Test detecting JavaScript in PDF."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
            f.write(b'%PDF-1.4\n/JavaScript (alert("test"))\n%%EOF')
            temp_path = f.name

        try:
            has_scripts, issues = check_pdf_for_scripts(temp_path)
            self.assertTrue(has_scripts)
            self.assertTrue(any('JavaScript' in i for i in issues))
        finally:
            os.unlink(temp_path)

    def test_pdf_with_launch_action(self):
        """Test detecting Launch action in PDF."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
            f.write(b'%PDF-1.4\n/Launch /F (cmd.exe)\n%%EOF')
            temp_path = f.name

        try:
            has_scripts, issues = check_pdf_for_scripts(temp_path)
            self.assertTrue(has_scripts)
            self.assertTrue(any('Launch' in i for i in issues))
        finally:
            os.unlink(temp_path)

    def test_pdf_with_embedded_files(self):
        """Test detecting embedded files in PDF."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
            f.write(b'%PDF-1.4\n/EmbeddedFile /test.exe\n%%EOF')
            temp_path = f.name

        try:
            has_scripts, issues = check_pdf_for_scripts(temp_path)
            self.assertTrue(has_scripts)
            self.assertTrue(any('embedded' in i.lower() for i in issues))
        finally:
            os.unlink(temp_path)

    def test_safe_pdf(self):
        """Test safe PDF without scripts."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
            f.write(b'%PDF-1.4\n/Page 1 0 R\n/Type /Catalog\n%%EOF')
            temp_path = f.name

        try:
            has_scripts, issues = check_pdf_for_scripts(temp_path)
            self.assertFalse(has_scripts)
            self.assertEqual(issues, [])
        finally:
            os.unlink(temp_path)


class TestOfficeMacroDetection(unittest.TestCase):
    """Test Office macro detection."""

    def test_macro_enabled_extension(self):
        """Test detecting macro-enabled extension."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.docm') as f:
            f.write(b'test')
            temp_path = f.name

        try:
            has_macros, issues = check_office_for_macros(temp_path)
            self.assertTrue(has_macros)
            self.assertTrue(any('macro-enabled' in i for i in issues))
        finally:
            os.unlink(temp_path)

    def test_xlsm_macro_extension(self):
        """Test detecting xlsm macro extension."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsm') as f:
            f.write(b'test')
            temp_path = f.name

        try:
            has_macros, issues = check_office_for_macros(temp_path)
            self.assertTrue(has_macros)
        finally:
            os.unlink(temp_path)

    def test_doc_with_vba(self):
        """Test detecting VBA in DOC file."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.doc') as f:
            f.write(b'\xd0\xcf\x11\xe0_VBA_PROJECT_test')
            temp_path = f.name

        try:
            has_macros, issues = check_office_for_macros(temp_path)
            self.assertTrue(has_macros)
            self.assertTrue(any('VBA' in i for i in issues))
        finally:
            os.unlink(temp_path)


class TestArchiveSecurity(unittest.TestCase):
    """Test archive security checks."""

    def test_safe_zip(self):
        """Test scanning safe ZIP file."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as f:
            temp_path = f.name

        try:
            with zipfile.ZipFile(temp_path, 'w') as zf:
                zf.writestr('document.txt', 'Hello world')
                zf.writestr('readme.md', 'Some readme')

            has_threats, issues = check_archive_for_threats(temp_path)
            self.assertFalse(has_threats)
            self.assertEqual(issues, [])
        finally:
            os.unlink(temp_path)

    def test_zip_with_executable(self):
        """Test detecting executable inside ZIP."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as f:
            temp_path = f.name

        try:
            with zipfile.ZipFile(temp_path, 'w') as zf:
                zf.writestr('malware.exe', 'MZ\x90\x00')
                zf.writestr('readme.txt', 'This is malware')

            has_threats, issues = check_archive_for_threats(temp_path)
            self.assertTrue(has_threats)
            self.assertTrue(any('dangerous file type' in i for i in issues))
        finally:
            os.unlink(temp_path)

    def test_zip_with_path_traversal(self):
        """Test detecting path traversal in ZIP."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as f:
            temp_path = f.name

        try:
            with zipfile.ZipFile(temp_path, 'w') as zf:
                zf.writestr('../../../etc/passwd', 'root:x:0:0:')

            has_threats, issues = check_archive_for_threats(temp_path)
            self.assertTrue(has_threats)
            self.assertTrue(any('path traversal' in i for i in issues))
        finally:
            os.unlink(temp_path)

    def test_invalid_zip(self):
        """Test handling invalid ZIP file."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as f:
            f.write(b'This is not a zip file')
            temp_path = f.name

        try:
            has_threats, issues = check_archive_for_threats(temp_path)
            self.assertTrue(has_threats)
            self.assertTrue(any('Invalid' in i or 'corrupted' in i for i in issues))
        finally:
            os.unlink(temp_path)


class TestDangerousExtensions(unittest.TestCase):
    """Test dangerous extension detection."""

    def test_exe_is_dangerous(self):
        """Test .exe is flagged as dangerous."""
        is_dangerous, issues = check_dangerous_extension('/tmp/test.exe')
        self.assertTrue(is_dangerous)

    def test_bat_is_dangerous(self):
        """Test .bat is flagged as dangerous."""
        is_dangerous, issues = check_dangerous_extension('/tmp/test.bat')
        self.assertTrue(is_dangerous)

    def test_ps1_is_dangerous(self):
        """Test .ps1 is flagged as dangerous."""
        is_dangerous, issues = check_dangerous_extension('/tmp/script.ps1')
        self.assertTrue(is_dangerous)

    def test_pdf_is_not_dangerous(self):
        """Test .pdf is not flagged as dangerous."""
        is_dangerous, issues = check_dangerous_extension('/tmp/test.pdf')
        self.assertFalse(is_dangerous)

    def test_double_extension_suspicious(self):
        """Test double extension detection."""
        is_dangerous, issues = check_dangerous_extension('/tmp/document.pdf.exe')
        self.assertTrue(is_dangerous)


class TestAllowedExtensions(unittest.TestCase):
    """Test allowed extension checking."""

    def test_pdf_allowed(self):
        """Test PDF is allowed."""
        is_allowed, _ = check_allowed_extension('/tmp/test.pdf')
        self.assertTrue(is_allowed)

    def test_docx_allowed(self):
        """Test DOCX is allowed."""
        is_allowed, _ = check_allowed_extension('/tmp/test.docx')
        self.assertTrue(is_allowed)

    def test_jpg_allowed(self):
        """Test JPG is allowed."""
        is_allowed, _ = check_allowed_extension('/tmp/image.jpg')
        self.assertTrue(is_allowed)

    def test_exe_not_allowed(self):
        """Test EXE is not allowed."""
        is_allowed, warnings = check_allowed_extension('/tmp/test.exe')
        self.assertFalse(is_allowed)

    def test_no_extension_not_allowed(self):
        """Test file without extension."""
        is_allowed, warnings = check_allowed_extension('/tmp/testfile')
        self.assertFalse(is_allowed)


class TestScanAttachment(unittest.TestCase):
    """Test the main scan_attachment function."""

    def test_scan_safe_pdf(self):
        """Test scanning safe PDF."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
            f.write(b'%PDF-1.4\n/Catalog 1 0 R\n%%EOF')
            temp_path = f.name

        try:
            result = scan_attachment(temp_path)
            self.assertTrue(result.is_safe)
            self.assertEqual(result.detected_type, 'pdf')
            self.assertEqual(result.file_extension, 'pdf')
            self.assertEqual(len(result.issues), 0)
        finally:
            os.unlink(temp_path)

    def test_scan_executable(self):
        """Test scanning executable file."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.exe') as f:
            f.write(b'MZ\x90\x00\x03\x00\x00\x00')
            temp_path = f.name

        try:
            result = scan_attachment(temp_path)
            self.assertFalse(result.is_safe)
            self.assertTrue(len(result.issues) > 0)
        finally:
            os.unlink(temp_path)

    def test_scan_type_mismatch(self):
        """Test scanning file with type mismatch."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
            # Write EXE signature but name it .pdf
            f.write(b'MZ\x90\x00\x03\x00\x00\x00')
            temp_path = f.name

        try:
            result = scan_attachment(temp_path)
            self.assertFalse(result.is_safe)
            self.assertTrue(any('mismatch' in i.lower() or 'executable' in i.lower()
                                for i in result.issues))
        finally:
            os.unlink(temp_path)

    def test_scan_nonexistent_file(self):
        """Test scanning nonexistent file."""
        result = scan_attachment('/nonexistent/file.pdf')
        self.assertFalse(result.is_safe)
        self.assertTrue(any('not exist' in i for i in result.issues))

    def test_scan_has_file_hash(self):
        """Test scan result includes file hash."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as f:
            f.write(b'test content')
            temp_path = f.name

        try:
            result = scan_attachment(temp_path)
            self.assertTrue(len(result.file_hash) > 0)
            self.assertEqual(len(result.file_hash), 64)
        finally:
            os.unlink(temp_path)


class TestFeature84SecurityChecks(unittest.TestCase):
    """Tests specifically for Feature #84 requirements."""

    def test_feature84_download_and_scan(self):
        """Test: Download job attachment and run basic security checks."""
        # Simulate downloaded attachment
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
            f.write(b'%PDF-1.4\n/Page 1\n%%EOF')
            temp_path = f.name

        try:
            result = scan_attachment(temp_path)
            self.assertIsInstance(result, ScanResult)
            self.assertIn('file_path', result.to_dict())
            self.assertIn('is_safe', result.to_dict())
            self.assertIn('issues', result.to_dict())
        finally:
            os.unlink(temp_path)

    def test_feature84_verify_no_executable(self):
        """Test: Verify no executable content in safe files."""
        # Create safe document
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
            f.write(b'%PDF-1.4\nThis is a safe document\n%%EOF')
            temp_path = f.name

        try:
            result = scan_attachment(temp_path)
            # Should be safe (no executable)
            self.assertTrue(result.is_safe)
            self.assertFalse(any('executable' in i.lower() for i in result.issues))
        finally:
            os.unlink(temp_path)

    def test_feature84_detect_executable_content(self):
        """Test: Verify executable content is detected and rejected."""
        # Create file with executable content
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
            f.write(b'MZ\x90\x00\x03\x00PE header')
            temp_path = f.name

        try:
            result = scan_attachment(temp_path)
            # Should not be safe (has executable signature)
            self.assertFalse(result.is_safe)
            self.assertTrue(
                any('executable' in i.lower() or 'mismatch' in i.lower()
                    for i in result.issues)
            )
        finally:
            os.unlink(temp_path)

    def test_feature84_file_type_matches_extension(self):
        """Test: Verify file type matches extension - matching case."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as f:
            f.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR')
            temp_path = f.name

        try:
            result = scan_attachment(temp_path)
            self.assertTrue(result.is_safe)
            self.assertEqual(result.detected_type, 'png')
            self.assertEqual(result.file_extension, 'png')
        finally:
            os.unlink(temp_path)

    def test_feature84_file_type_mismatch_detected(self):
        """Test: Verify file type mismatch is detected."""
        # Create PNG file but name it .pdf
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
            f.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR')
            temp_path = f.name

        try:
            result = scan_attachment(temp_path)
            self.assertFalse(result.is_safe)
            self.assertTrue(any('mismatch' in i.lower() for i in result.issues))
        finally:
            os.unlink(temp_path)

    def test_feature84_validate_for_processing(self):
        """Test: validate_attachment_for_processing returns correct tuple."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
            f.write(b'%PDF-1.4\n%%EOF')
            temp_path = f.name

        try:
            is_safe, result = validate_attachment_for_processing(temp_path)
            self.assertIsInstance(is_safe, bool)
            self.assertIsInstance(result, ScanResult)
            self.assertEqual(is_safe, result.is_safe)
        finally:
            os.unlink(temp_path)


class TestBatchScanning(unittest.TestCase):
    """Test batch scanning functionality."""

    def test_scan_directory(self):
        """Test scanning a directory of files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            pdf_path = os.path.join(tmpdir, 'doc.pdf')
            txt_path = os.path.join(tmpdir, 'note.txt')

            with open(pdf_path, 'wb') as f:
                f.write(b'%PDF-1.4\n%%EOF')
            with open(txt_path, 'w') as f:
                f.write('Hello world')

            results = scan_directory(tmpdir)
            self.assertEqual(len(results), 2)
            self.assertTrue(all(isinstance(r, ScanResult) for r in results))

    def test_scan_batch(self):
        """Test batch scanning files."""
        paths = []
        try:
            for i in range(3):
                with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as f:
                    f.write(f'Content {i}'.encode())
                    paths.append(f.name)

            results = scan_attachments_batch(paths)
            self.assertEqual(len(results), 3)
        finally:
            for p in paths:
                os.unlink(p)

    def test_filter_safe_attachments(self):
        """Test filtering safe attachments."""
        paths = []
        try:
            # Create safe file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
                f.write(b'%PDF-1.4\n%%EOF')
                paths.append(f.name)

            # Create unsafe file (exe signature with pdf extension)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
                f.write(b'MZ\x90\x00PE header')
                paths.append(f.name)

            safe_paths, results = filter_safe_attachments(paths)

            # Only one should be safe
            self.assertEqual(len(safe_paths), 1)
            self.assertEqual(len(results), 2)
        finally:
            for p in paths:
                os.unlink(p)


class TestScanSummary(unittest.TestCase):
    """Test scan summary generation."""

    def test_get_summary(self):
        """Test getting scan summary."""
        results = [
            ScanResult(
                file_path='/tmp/a.pdf', file_name='a.pdf', file_size=100,
                file_extension='pdf', detected_type='pdf', is_safe=True
            ),
            ScanResult(
                file_path='/tmp/b.exe', file_name='b.exe', file_size=200,
                file_extension='exe', detected_type='exe', is_safe=False,
                issues=['Executable file']
            ),
            ScanResult(
                file_path='/tmp/c.txt', file_name='c.txt', file_size=50,
                file_extension='txt', detected_type='text', is_safe=True,
                warnings=['No extension match']
            ),
        ]

        summary = get_scan_summary(results)

        self.assertEqual(summary['total_files'], 3)
        self.assertEqual(summary['safe_files'], 2)
        self.assertEqual(summary['unsafe_files'], 1)
        self.assertEqual(summary['total_issues'], 1)
        self.assertEqual(summary['total_warnings'], 1)


class TestConstants(unittest.TestCase):
    """Test module constants."""

    def test_dangerous_extensions_not_empty(self):
        """Test dangerous extensions set is populated."""
        self.assertGreater(len(DANGEROUS_EXTENSIONS), 0)
        self.assertIn('exe', DANGEROUS_EXTENSIONS)
        self.assertIn('bat', DANGEROUS_EXTENSIONS)

    def test_allowed_extensions_not_empty(self):
        """Test allowed extensions set is populated."""
        self.assertGreater(len(ALLOWED_EXTENSIONS), 0)
        self.assertIn('pdf', ALLOWED_EXTENSIONS)
        self.assertIn('docx', ALLOWED_EXTENSIONS)

    def test_file_signatures_not_empty(self):
        """Test file signatures dict is populated."""
        self.assertGreater(len(FILE_SIGNATURES), 0)
        self.assertIn('pdf', FILE_SIGNATURES)
        self.assertIn('exe', FILE_SIGNATURES)

    def test_max_file_size_reasonable(self):
        """Test max file size is reasonable."""
        self.assertGreater(MAX_FILE_SIZE, 0)
        self.assertEqual(MAX_FILE_SIZE, 100 * 1024 * 1024)  # 100 MB

    def test_archive_bomb_ratio_reasonable(self):
        """Test archive bomb ratio is reasonable."""
        self.assertGreater(ARCHIVE_BOMB_RATIO, 10)
        self.assertLess(ARCHIVE_BOMB_RATIO, 1000)


class TestIntegration(unittest.TestCase):
    """Integration tests for attachment scanning."""

    def test_full_scan_workflow(self):
        """Test complete scan workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create various test files
            files = {}

            # Safe PDF
            files['safe.pdf'] = b'%PDF-1.4\n%%EOF'

            # Safe text
            files['readme.txt'] = b'This is a readme file'

            # Dangerous executable
            files['malware.exe'] = b'MZ\x90\x00PE'

            # Create files
            paths = []
            for name, content in files.items():
                path = os.path.join(tmpdir, name)
                with open(path, 'wb') as f:
                    f.write(content)
                paths.append(path)

            # Scan directory
            results = scan_directory(tmpdir)

            # Verify results
            self.assertEqual(len(results), 3)

            # Check safe files
            safe_count = sum(1 for r in results if r.is_safe)
            self.assertGreaterEqual(safe_count, 1)

            # Check unsafe files
            unsafe_count = sum(1 for r in results if not r.is_safe)
            self.assertGreaterEqual(unsafe_count, 1)

    def test_deep_extractor_integration(self):
        """Test integration with deep extractor pattern."""
        # Simulate what deep extractor would do
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
            f.write(b'%PDF-1.4\nSafe document content\n%%EOF')
            attachment_path = f.name

        try:
            # Deep extractor would call this
            is_safe, scan_result = validate_attachment_for_processing(attachment_path)

            if is_safe:
                # Proceed with text extraction
                self.assertTrue(scan_result.is_safe)
            else:
                # Skip this attachment
                self.assertFalse(scan_result.is_safe)
                self.assertGreater(len(scan_result.issues), 0)
        finally:
            os.unlink(attachment_path)


if __name__ == '__main__':
    unittest.main()
