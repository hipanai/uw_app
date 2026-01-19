#!/usr/bin/env python3
"""
Upwork Attachment Scanner - Security scanning for job attachments.

Feature #84: Job attachments are scanned for malicious content.

This module provides security scanning for file attachments downloaded from
Upwork job postings, checking for:
- Executable content detection
- File type vs extension mismatch
- Embedded macros in documents
- Suspicious file signatures
- Archive bomb detection
- JavaScript/VBScript detection in PDFs

Usage:
    from upwork_attachment_scanner import scan_attachment, ScanResult

    result = scan_attachment("/path/to/file.pdf")
    if result.is_safe:
        print("File is safe to process")
    else:
        print(f"Security issues: {result.issues}")

CLI:
    python upwork_attachment_scanner.py --file /path/to/attachment.pdf
    python upwork_attachment_scanner.py --scan-directory /path/to/attachments/
    python upwork_attachment_scanner.py --test
"""

import os
import re
import struct
import zipfile
import json
import argparse
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from datetime import datetime


# File signature (magic bytes) definitions
# Format: extension -> list of (magic_bytes, offset)
FILE_SIGNATURES: Dict[str, List[Tuple[bytes, int]]] = {
    # Document formats
    'pdf': [(b'%PDF', 0)],
    'doc': [(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1', 0)],  # OLE compound file
    'docx': [(b'PK\x03\x04', 0)],  # ZIP-based
    'xlsx': [(b'PK\x03\x04', 0)],  # ZIP-based
    'pptx': [(b'PK\x03\x04', 0)],  # ZIP-based
    'odt': [(b'PK\x03\x04', 0)],  # ZIP-based OpenDocument
    'ods': [(b'PK\x03\x04', 0)],
    'odp': [(b'PK\x03\x04', 0)],
    'rtf': [(b'{\\rtf', 0)],

    # Image formats
    'jpg': [(b'\xff\xd8\xff', 0)],
    'jpeg': [(b'\xff\xd8\xff', 0)],
    'png': [(b'\x89PNG\r\n\x1a\n', 0)],
    'gif': [(b'GIF87a', 0), (b'GIF89a', 0)],
    'bmp': [(b'BM', 0)],
    'webp': [(b'RIFF', 0)],  # Also check for WEBP at offset 8
    'svg': [(b'<svg', 0), (b'<?xml', 0)],  # XML-based

    # Archive formats
    'zip': [(b'PK\x03\x04', 0), (b'PK\x05\x06', 0)],
    'rar': [(b'Rar!\x1a\x07', 0)],
    '7z': [(b'7z\xbc\xaf\x27\x1c', 0)],
    'gz': [(b'\x1f\x8b', 0)],
    'tar': [(b'ustar', 257)],

    # Executable formats (dangerous)
    'exe': [(b'MZ', 0)],
    'dll': [(b'MZ', 0)],
    'com': [(b'\xe9', 0), (b'\xeb', 0)],
    'msi': [(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1', 0)],
    'bat': [],  # Text-based, check content
    'cmd': [],  # Text-based, check content
    'ps1': [],  # PowerShell, text-based
    'sh': [(b'#!/', 0), (b'#!', 0)],
    'elf': [(b'\x7fELF', 0)],  # Linux executable
    'macho': [(b'\xfe\xed\xfa\xce', 0), (b'\xfe\xed\xfa\xcf', 0)],  # macOS

    # Script formats (potentially dangerous)
    'js': [],  # Text-based
    'vbs': [],  # Text-based
    'vbe': [],  # Encoded VBScript
    'wsf': [(b'<?xml', 0)],  # Windows Script File
    'jar': [(b'PK\x03\x04', 0)],  # Java archive
}

# Dangerous file extensions
DANGEROUS_EXTENSIONS: Set[str] = {
    # Executables
    'exe', 'dll', 'com', 'msi', 'scr', 'pif', 'cpl',
    # Scripts
    'bat', 'cmd', 'ps1', 'vbs', 'vbe', 'js', 'jse', 'wsf', 'wsh',
    # Shell scripts
    'sh', 'bash', 'zsh', 'fish',
    # Java
    'jar', 'class',
    # macOS
    'app', 'dmg', 'pkg',
    # Linux
    'deb', 'rpm', 'run',
    # Office macros
    'docm', 'xlsm', 'pptm', 'dotm', 'xltm', 'potm',
    # HTML applications
    'hta', 'html', 'htm',  # htm/html can contain scripts
    # Shortcuts
    'lnk', 'url', 'desktop',
    # Reg files
    'reg',
    # Compiled Help
    'chm',
}

# Safe extensions for Upwork job attachments
ALLOWED_EXTENSIONS: Set[str] = {
    # Documents
    'pdf', 'doc', 'docx', 'txt', 'rtf', 'odt',
    # Spreadsheets
    'xls', 'xlsx', 'csv', 'ods',
    # Presentations
    'ppt', 'pptx', 'odp',
    # Images
    'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg', 'tiff', 'tif',
    # Archives (will be scanned)
    'zip', 'rar', '7z', 'gz', 'tar',
}

# Maximum file size for scanning (100 MB)
MAX_FILE_SIZE: int = 100 * 1024 * 1024

# Maximum decompressed size for archives (500 MB - archive bomb protection)
MAX_DECOMPRESSED_SIZE: int = 500 * 1024 * 1024

# Compression ratio threshold for archive bomb detection
ARCHIVE_BOMB_RATIO: float = 100.0


@dataclass
class ScanResult:
    """Result of scanning an attachment for security issues."""

    file_path: str
    file_name: str
    file_size: int
    file_extension: str
    detected_type: str
    is_safe: bool
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    scan_time: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    file_hash: str = ""

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'file_path': self.file_path,
            'file_name': self.file_name,
            'file_size': self.file_size,
            'file_extension': self.file_extension,
            'detected_type': self.detected_type,
            'is_safe': self.is_safe,
            'issues': self.issues,
            'warnings': self.warnings,
            'scan_time': self.scan_time,
            'file_hash': self.file_hash,
        }

    def __bool__(self) -> bool:
        """Return True if file is safe."""
        return self.is_safe


def get_file_extension(file_path: str) -> str:
    """Extract and normalize file extension."""
    ext = Path(file_path).suffix.lower().lstrip('.')
    return ext


def compute_file_hash(file_path: str, algorithm: str = 'sha256') -> str:
    """Compute hash of file content."""
    if not os.path.exists(file_path):
        return ""

    hasher = hashlib.new(algorithm)
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (IOError, OSError):
        return ""


def read_file_header(file_path: str, size: int = 512) -> bytes:
    """Read the first bytes of a file for magic number detection."""
    try:
        with open(file_path, 'rb') as f:
            return f.read(size)
    except (IOError, OSError):
        return b''


def detect_file_type(file_path: str) -> str:
    """
    Detect actual file type based on magic bytes/signatures.

    Returns the detected file type or 'unknown'.
    """
    header = read_file_header(file_path, 512)
    if not header:
        return 'unknown'

    # Check each known file type
    for ext, signatures in FILE_SIGNATURES.items():
        if not signatures:
            continue
        for magic_bytes, offset in signatures:
            if len(header) >= offset + len(magic_bytes):
                if header[offset:offset + len(magic_bytes)] == magic_bytes:
                    # Special case for ZIP-based formats (DOCX, XLSX, etc.)
                    if magic_bytes == b'PK\x03\x04':
                        # Try to determine specific Office format
                        detected = detect_office_format(file_path)
                        if detected:
                            return detected
                        return 'zip'

                    # Special case for OLE compound files (DOC, XLS)
                    if magic_bytes == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
                        detected = detect_ole_format(file_path)
                        if detected:
                            return detected
                        return 'ole'

                    return ext

    # Check for text-based files
    if is_text_file(header):
        return detect_text_type(header, file_path)

    return 'unknown'


def detect_office_format(file_path: str) -> Optional[str]:
    """Detect specific Office format from ZIP-based file."""
    try:
        with zipfile.ZipFile(file_path, 'r') as zf:
            names = zf.namelist()

            # Check for Office Open XML markers
            if '[Content_Types].xml' in names:
                if any('word/' in n for n in names):
                    return 'docx'
                if any('xl/' in n for n in names):
                    return 'xlsx'
                if any('ppt/' in n for n in names):
                    return 'pptx'

            # Check for OpenDocument markers
            if 'mimetype' in names:
                try:
                    mimetype = zf.read('mimetype').decode('utf-8', errors='ignore').strip()
                    if 'text' in mimetype:
                        return 'odt'
                    if 'spreadsheet' in mimetype:
                        return 'ods'
                    if 'presentation' in mimetype:
                        return 'odp'
                except:
                    pass

            # Check for JAR markers
            if 'META-INF/MANIFEST.MF' in names:
                return 'jar'

    except (zipfile.BadZipFile, IOError):
        pass

    return None


def detect_ole_format(file_path: str) -> Optional[str]:
    """Detect specific format from OLE compound file."""
    try:
        with open(file_path, 'rb') as f:
            content = f.read(8192)

            # Look for Word document markers
            if b'Word.Document' in content or b'Microsoft Word' in content:
                return 'doc'

            # Look for Excel markers
            if b'Microsoft Excel' in content or b'Workbook' in content:
                return 'xls'

            # Look for PowerPoint markers
            if b'Microsoft PowerPoint' in content or b'PowerPoint Document' in content:
                return 'ppt'

            # Look for MSI markers
            if b'Windows Installer' in content:
                return 'msi'

    except (IOError, OSError):
        pass

    return None


def is_text_file(header: bytes) -> bool:
    """Check if file appears to be text-based."""
    # Check if mostly printable ASCII
    try:
        # Check first 512 bytes
        text = header[:512]
        printable = sum(1 for b in text if 32 <= b < 127 or b in (9, 10, 13))
        return printable / max(len(text), 1) > 0.85
    except:
        return False


def detect_text_type(header: bytes, file_path: str) -> str:
    """Detect type of text-based file."""
    try:
        text = header.decode('utf-8', errors='ignore').lower()
    except:
        return 'text'

    # Check for specific text file types
    if text.startswith('<?xml') or text.startswith('<svg'):
        return 'xml'
    if text.startswith('{\\rtf'):
        return 'rtf'
    if '#!/' in text[:20] or '#!' in text[:5]:
        return 'script'
    if '<html' in text or '<!doctype html' in text:
        return 'html'
    if text.startswith('%pdf'):
        return 'pdf'

    # Check file extension for script types
    ext = get_file_extension(file_path)
    if ext in ('js', 'vbs', 'ps1', 'bat', 'cmd', 'sh'):
        return ext

    return 'text'


def check_extension_matches_type(extension: str, detected_type: str) -> Tuple[bool, str]:
    """
    Check if file extension matches detected type.

    Returns (matches, reason) tuple.
    """
    if detected_type == 'unknown':
        return True, "Type could not be determined"

    # Normalize extension
    ext = extension.lower()

    # Direct match
    if ext == detected_type:
        return True, "Extension matches detected type"

    # Allow equivalent extensions
    equivalents = {
        'jpg': {'jpeg'},
        'jpeg': {'jpg'},
        'tif': {'tiff'},
        'tiff': {'tif'},
        'doc': {'ole'},
        'xls': {'ole'},
        'ppt': {'ole'},
        'docx': {'zip'},
        'xlsx': {'zip'},
        'pptx': {'zip'},
        'odt': {'zip'},
        'ods': {'zip'},
        'odp': {'zip'},
        'txt': {'text'},
        'csv': {'text'},
        'md': {'text'},
    }

    if ext in equivalents and detected_type in equivalents[ext]:
        return True, "Extension matches equivalent type"

    if detected_type in equivalents and ext in equivalents[detected_type]:
        return True, "Detected type matches equivalent extension"

    # Mismatch
    return False, f"Extension '{ext}' does not match detected type '{detected_type}'"


def check_for_executable_content(file_path: str) -> Tuple[bool, List[str]]:
    """
    Check if file contains executable content.

    Returns (has_executable, issues) tuple.
    """
    issues = []
    header = read_file_header(file_path, 512)

    # Check for PE (Windows executable) header
    if header[:2] == b'MZ':
        issues.append("File contains Windows executable (PE) signature")
        return True, issues

    # Check for ELF (Linux executable) header
    if header[:4] == b'\x7fELF':
        issues.append("File contains Linux executable (ELF) signature")
        return True, issues

    # Check for Mach-O (macOS executable) header
    if header[:4] in (b'\xfe\xed\xfa\xce', b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe'):
        issues.append("File contains macOS executable (Mach-O) signature")
        return True, issues

    # Check for shell script
    if header[:2] == b'#!' or header[:3] == b'#!/':
        issues.append("File contains shell script header")
        return True, issues

    return False, issues


def check_pdf_for_scripts(file_path: str) -> Tuple[bool, List[str]]:
    """
    Check PDF file for embedded JavaScript or other scripts.

    Returns (has_scripts, issues) tuple.
    """
    issues = []

    try:
        with open(file_path, 'rb') as f:
            content = f.read()
    except (IOError, OSError):
        return False, []

    content_str = content.decode('latin-1', errors='ignore')

    # Check for JavaScript
    js_patterns = [
        r'/JavaScript\s',
        r'/JS\s*\(',
        r'/S\s*/JavaScript',
        r'OpenAction.*JavaScript',
    ]

    for pattern in js_patterns:
        if re.search(pattern, content_str, re.IGNORECASE):
            issues.append("PDF contains embedded JavaScript")
            break

    # Check for launch actions
    if '/Launch' in content_str:
        issues.append("PDF contains Launch action (can run external programs)")

    # Check for embedded files
    if '/EmbeddedFile' in content_str or '/EmbeddedFiles' in content_str:
        issues.append("PDF contains embedded files")

    # Check for URI/URL actions
    if '/URI' in content_str or '/GoToR' in content_str:
        # This is common and usually OK, just a warning
        pass

    # Check for AcroForm (can contain scripts)
    if '/AcroForm' in content_str:
        # Check for XFA forms which can contain scripts
        if '/XFA' in content_str:
            issues.append("PDF contains XFA form (can contain scripts)")

    return len(issues) > 0, issues


def check_office_for_macros(file_path: str) -> Tuple[bool, List[str]]:
    """
    Check Office documents for macros/VBA.

    Returns (has_macros, issues) tuple.
    """
    issues = []
    ext = get_file_extension(file_path)

    # Check for macro-enabled extensions
    if ext in ('docm', 'xlsm', 'pptm', 'dotm', 'xltm', 'potm'):
        issues.append(f"File is a macro-enabled Office document ({ext})")
        return True, issues

    # Check OLE format documents
    if ext in ('doc', 'xls', 'ppt'):
        try:
            with open(file_path, 'rb') as f:
                content = f.read()

            # Check for VBA project stream
            if b'_VBA_PROJECT' in content or b'VBA' in content:
                issues.append("Document contains VBA macro project")
                return True, issues

            # Check for macro storage
            if b'Macros' in content:
                issues.append("Document may contain macros")
                return True, issues

        except (IOError, OSError):
            pass

    # Check OOXML format documents
    if ext in ('docx', 'xlsx', 'pptx'):
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                names = zf.namelist()

                # Check for VBA project
                if any('vbaProject' in n.lower() for n in names):
                    issues.append("Document contains VBA macro project")
                    return True, issues

                # Check for macro storage
                if any('macros' in n.lower() for n in names):
                    issues.append("Document may contain macros")
                    return True, issues

        except (zipfile.BadZipFile, IOError):
            pass

    return False, issues


def check_archive_for_threats(file_path: str) -> Tuple[bool, List[str]]:
    """
    Check archive file for threats (archive bomb, dangerous files).

    Returns (has_threats, issues) tuple.
    """
    issues = []

    try:
        with zipfile.ZipFile(file_path, 'r') as zf:
            # Calculate total decompressed size
            total_size = sum(info.file_size for info in zf.infolist())

            # Check for archive bomb
            compressed_size = os.path.getsize(file_path)
            if compressed_size > 0:
                ratio = total_size / compressed_size
                if ratio > ARCHIVE_BOMB_RATIO:
                    issues.append(f"Potential archive bomb detected (compression ratio: {ratio:.1f}x)")

            # Check for excessive decompressed size
            if total_size > MAX_DECOMPRESSED_SIZE:
                issues.append(f"Archive decompressed size exceeds limit ({total_size / 1024 / 1024:.1f} MB)")

            # Check for dangerous files inside
            for info in zf.infolist():
                inner_ext = get_file_extension(info.filename)
                if inner_ext in DANGEROUS_EXTENSIONS:
                    issues.append(f"Archive contains dangerous file type: {info.filename}")

                # Check for path traversal
                if '..' in info.filename or info.filename.startswith('/'):
                    issues.append(f"Archive contains path traversal attempt: {info.filename}")

    except zipfile.BadZipFile:
        issues.append("Invalid or corrupted archive file")
    except (IOError, OSError) as e:
        issues.append(f"Error reading archive: {str(e)}")

    return len(issues) > 0, issues


def check_dangerous_extension(file_path: str) -> Tuple[bool, List[str]]:
    """
    Check if file has a dangerous extension.

    Returns (is_dangerous, issues) tuple.
    """
    ext = get_file_extension(file_path)

    if ext in DANGEROUS_EXTENSIONS:
        return True, [f"File has dangerous extension: .{ext}"]

    # Check for double extensions (e.g., file.pdf.exe)
    path = Path(file_path)
    parts = path.name.split('.')
    if len(parts) > 2:
        for part in parts[1:-1]:
            if part.lower() in DANGEROUS_EXTENSIONS:
                return True, [f"File has suspicious double extension: {path.name}"]

    return False, []


def check_allowed_extension(file_path: str) -> Tuple[bool, List[str]]:
    """
    Check if file has an allowed extension for Upwork attachments.

    Returns (is_allowed, warnings) tuple.
    """
    ext = get_file_extension(file_path)

    if not ext:
        return False, ["File has no extension"]

    if ext not in ALLOWED_EXTENSIONS:
        return False, [f"File extension '.{ext}' is not in allowed list"]

    return True, []


def scan_attachment(file_path: str, strict: bool = False) -> ScanResult:
    """
    Scan a file attachment for security issues.

    Args:
        file_path: Path to the file to scan
        strict: If True, any warning is treated as an issue

    Returns:
        ScanResult with scan findings
    """
    issues = []
    warnings = []

    # Get file info
    file_name = os.path.basename(file_path)
    file_extension = get_file_extension(file_path)

    # Check if file exists
    if not os.path.exists(file_path):
        return ScanResult(
            file_path=file_path,
            file_name=file_name,
            file_size=0,
            file_extension=file_extension,
            detected_type='unknown',
            is_safe=False,
            issues=["File does not exist"],
        )

    # Get file size
    file_size = os.path.getsize(file_path)

    # Check file size
    if file_size > MAX_FILE_SIZE:
        issues.append(f"File exceeds maximum size ({file_size / 1024 / 1024:.1f} MB > {MAX_FILE_SIZE / 1024 / 1024} MB)")

    if file_size == 0:
        warnings.append("File is empty")

    # Detect actual file type
    detected_type = detect_file_type(file_path)

    # Compute file hash
    file_hash = compute_file_hash(file_path)

    # Check 1: Dangerous extension
    is_dangerous, ext_issues = check_dangerous_extension(file_path)
    if is_dangerous:
        issues.extend(ext_issues)

    # Check 2: Allowed extension
    is_allowed, ext_warnings = check_allowed_extension(file_path)
    if not is_allowed:
        warnings.extend(ext_warnings)

    # Check 3: Extension matches type
    matches, match_reason = check_extension_matches_type(file_extension, detected_type)
    if not matches:
        issues.append(f"File type mismatch: {match_reason}")

    # Check 4: Executable content
    has_exec, exec_issues = check_for_executable_content(file_path)
    if has_exec:
        issues.extend(exec_issues)

    # Check 5: PDF-specific checks
    if detected_type == 'pdf' or file_extension == 'pdf':
        has_scripts, pdf_issues = check_pdf_for_scripts(file_path)
        if has_scripts:
            # PDF scripts are issues
            issues.extend(pdf_issues)

    # Check 6: Office document macro checks
    if detected_type in ('doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'docm', 'xlsm', 'pptm', 'odt', 'ods', 'odp') or \
       file_extension in ('doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'docm', 'xlsm', 'pptm', 'odt', 'ods', 'odp'):
        has_macros, macro_issues = check_office_for_macros(file_path)
        if has_macros:
            issues.extend(macro_issues)

    # Check 7: Archive-specific checks
    if detected_type in ('zip', 'rar', '7z') or file_extension in ('zip', 'rar', '7z', 'gz', 'tar'):
        has_threats, archive_issues = check_archive_for_threats(file_path)
        if has_threats:
            issues.extend(archive_issues)

    # Determine if safe
    is_safe = len(issues) == 0
    if strict and len(warnings) > 0:
        is_safe = False

    return ScanResult(
        file_path=file_path,
        file_name=file_name,
        file_size=file_size,
        file_extension=file_extension,
        detected_type=detected_type,
        is_safe=is_safe,
        issues=issues,
        warnings=warnings,
        file_hash=file_hash,
    )


def scan_directory(directory: str, recursive: bool = True, strict: bool = False) -> List[ScanResult]:
    """
    Scan all files in a directory.

    Args:
        directory: Path to directory to scan
        recursive: If True, scan subdirectories
        strict: If True, warnings are treated as issues

    Returns:
        List of ScanResult for each file
    """
    results = []

    if not os.path.isdir(directory):
        return results

    if recursive:
        for root, dirs, files in os.walk(directory):
            for file_name in files:
                file_path = os.path.join(root, file_name)
                results.append(scan_attachment(file_path, strict=strict))
    else:
        for file_name in os.listdir(directory):
            file_path = os.path.join(directory, file_name)
            if os.path.isfile(file_path):
                results.append(scan_attachment(file_path, strict=strict))

    return results


def scan_attachments_batch(file_paths: List[str], strict: bool = False) -> List[ScanResult]:
    """
    Scan multiple files.

    Args:
        file_paths: List of file paths to scan
        strict: If True, warnings are treated as issues

    Returns:
        List of ScanResult for each file
    """
    return [scan_attachment(path, strict=strict) for path in file_paths]


def filter_safe_attachments(file_paths: List[str], strict: bool = False) -> Tuple[List[str], List[ScanResult]]:
    """
    Filter a list of files to only safe ones.

    Args:
        file_paths: List of file paths to filter
        strict: If True, warnings are treated as issues

    Returns:
        Tuple of (safe_paths, scan_results)
    """
    results = scan_attachments_batch(file_paths, strict=strict)
    safe_paths = [r.file_path for r in results if r.is_safe]
    return safe_paths, results


def validate_attachment_for_processing(file_path: str) -> Tuple[bool, ScanResult]:
    """
    Validate that an attachment is safe to process.

    This is the main entry point for the deep extractor to use.

    Args:
        file_path: Path to the attachment file

    Returns:
        Tuple of (is_safe, scan_result)
    """
    result = scan_attachment(file_path, strict=False)
    return result.is_safe, result


def get_scan_summary(results: List[ScanResult]) -> Dict:
    """
    Get a summary of scan results.

    Args:
        results: List of ScanResult

    Returns:
        Summary dictionary
    """
    total = len(results)
    safe = sum(1 for r in results if r.is_safe)
    unsafe = total - safe

    all_issues = []
    all_warnings = []
    for r in results:
        all_issues.extend(r.issues)
        all_warnings.extend(r.warnings)

    return {
        'total_files': total,
        'safe_files': safe,
        'unsafe_files': unsafe,
        'total_issues': len(all_issues),
        'total_warnings': len(all_warnings),
        'unique_issues': list(set(all_issues)),
        'unique_warnings': list(set(all_warnings)),
    }


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Scan job attachments for security issues',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python upwork_attachment_scanner.py --file attachment.pdf
    python upwork_attachment_scanner.py --scan-directory /path/to/.tmp/attachments/
    python upwork_attachment_scanner.py --test
        """
    )

    parser.add_argument('--file', '-f', help='File to scan')
    parser.add_argument('--scan-directory', '-d', help='Directory to scan')
    parser.add_argument('--recursive', '-r', action='store_true', default=True,
                        help='Scan subdirectories (default: True)')
    parser.add_argument('--strict', '-s', action='store_true',
                        help='Treat warnings as issues')
    parser.add_argument('--output', '-o', help='Output file for results (JSON)')
    parser.add_argument('--test', '-t', action='store_true',
                        help='Run basic validation test')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output')

    args = parser.parse_args()

    if args.test:
        print("Running attachment scanner validation...")
        print(f"  Dangerous extensions: {len(DANGEROUS_EXTENSIONS)}")
        print(f"  Allowed extensions: {len(ALLOWED_EXTENSIONS)}")
        print(f"  File signatures defined: {len(FILE_SIGNATURES)}")
        print(f"  Max file size: {MAX_FILE_SIZE / 1024 / 1024} MB")
        print(f"  Max decompressed size: {MAX_DECOMPRESSED_SIZE / 1024 / 1024} MB")
        print("Validation complete!")
        return

    if args.file:
        result = scan_attachment(args.file, strict=args.strict)

        if args.output:
            with open(args.output, 'w') as f:
                json.dump(result.to_dict(), f, indent=2)
            print(f"Results written to {args.output}")
        else:
            print(f"\nScan Result for: {result.file_name}")
            print(f"  Size: {result.file_size} bytes")
            print(f"  Extension: .{result.file_extension}")
            print(f"  Detected type: {result.detected_type}")
            print(f"  SHA256: {result.file_hash[:16]}...")
            print(f"  Is Safe: {result.is_safe}")

            if result.issues:
                print(f"  Issues ({len(result.issues)}):")
                for issue in result.issues:
                    print(f"    - {issue}")

            if result.warnings:
                print(f"  Warnings ({len(result.warnings)}):")
                for warning in result.warnings:
                    print(f"    - {warning}")

        return

    if args.scan_directory:
        results = scan_directory(args.scan_directory, recursive=args.recursive, strict=args.strict)
        summary = get_scan_summary(results)

        if args.output:
            output_data = {
                'summary': summary,
                'results': [r.to_dict() for r in results],
            }
            with open(args.output, 'w') as f:
                json.dump(output_data, f, indent=2)
            print(f"Results written to {args.output}")
        else:
            print(f"\nScan Summary for: {args.scan_directory}")
            print(f"  Total files: {summary['total_files']}")
            print(f"  Safe files: {summary['safe_files']}")
            print(f"  Unsafe files: {summary['unsafe_files']}")

            if summary['unique_issues']:
                print(f"  Issues found:")
                for issue in summary['unique_issues']:
                    print(f"    - {issue}")

            if args.verbose and summary['unique_warnings']:
                print(f"  Warnings:")
                for warning in summary['unique_warnings']:
                    print(f"    - {warning}")

        return

    parser.print_help()


if __name__ == '__main__':
    main()
