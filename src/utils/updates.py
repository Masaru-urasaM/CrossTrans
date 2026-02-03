"""
Auto-Update System for CrossTrans.
"""
import os
import sys
import json
import logging
import tempfile
import subprocess
import urllib.request
import time
import re
from typing import Optional, Callable

from packaging import version

from src.constants import VERSION, GITHUB_REPO
from src.core.ssl_pinning import get_ssl_context_for_url


class UpdateError(Exception):
    """Base exception for update-related errors."""
    pass


class DownloadCancelledException(UpdateError):
    """Exception raised when user cancels download."""
    pass


# Update System Constants
UPDATE_CHECK_TIMEOUT = 30  # seconds - GitHub API request timeout
UPDATE_DOWNLOAD_TIMEOUT = 180  # seconds - Download timeout
UPDATE_CHECK_MAX_RETRIES = 3  # Max retry attempts for update check
UPDATE_THREAD_TIMEOUT = 60  # seconds - Thread join timeout
RELEASE_NOTES_MAX_LENGTH = 300  # characters - Truncate release notes
PROGRESS_WINDOW_SIZE = "350x120"  # Progress dialog dimensions
UPDATE_TOAST_DURATION = 5000  # milliseconds - Toast notification duration
STARTUP_UPDATE_DELAY = 3  # seconds - Delay before auto-check on startup
THREAD_NAMES = {
    'check': 'UpdateCheckThread',
    'download': 'DownloadThread',
    'monitor': 'UpdateMonitor',
    'startup': 'StartupUpdateCheck'
}


# Valid error types for telemetry
VALID_ERROR_TYPES = {'network', 'rate_limit', 'ssl', 'parse_error', 'timeout', 'other'}

# Error detection patterns (for classifying error messages)
ERROR_PATTERNS = {
    'network': ['connect', 'connection', 'internet', 'network', 'unreachable', 'dns'],
    'rate_limit': ['rate limit', '403', 'too many requests'],
    'ssl': ['ssl', 'certificate', 'tls', 'secure connection'],
    'parse_error': ['parse', 'invalid json', 'malformed', 'invalid response'],
    'timeout': ['timeout', 'timed out', 'time out'],
}


def classify_error_type(error_message: str) -> str:
    """Classify error type based on error message content.

    Args:
        error_message: The error message to classify

    Returns:
        Error type string from VALID_ERROR_TYPES ('network', 'rate_limit', etc.)
        Returns 'other' if no pattern matches.
    """
    if not error_message:
        return 'other'

    error_lower = error_message.lower()

    for error_type, patterns in ERROR_PATTERNS.items():
        if any(pattern in error_lower for pattern in patterns):
            return error_type

    return 'other'


# User-friendly error messages
ERROR_MESSAGES = {
    'network': (
        "Cannot connect to GitHub.\n\n"
        "Possible solutions:\n"
        "• Check your internet connection\n"
        "• Disable VPN/proxy temporarily\n"
        "• Check firewall settings\n"
        "• Try again in a few moments"
    ),
    'rate_limit': (
        "GitHub rate limit reached.\n\n"
        "Please try again in a few minutes."
    ),
    'ssl': (
        "SSL/Security error.\n\n"
        "Possible solutions:\n"
        "• Update Windows to latest version\n"
        "• Check system date/time is correct\n"
        "• Disable antivirus temporarily\n"
        "• Contact support if issue persists"
    ),
    'parse_error': (
        "Invalid response from GitHub.\n\n"
        "GitHub may be experiencing issues.\n"
        "Please try again later."
    ),
    'timeout': (
        "Update check timed out.\n\n"
        "Your connection may be slow.\n"
        "Please try again."
    )
}


class AutoUpdater:
    """Handles checking, downloading and installing updates from GitHub releases.

    Provides comprehensive update functionality with:
    - GitHub API integration for checking latest releases
    - Automatic download with progress tracking
    - SHA256 integrity verification
    - Batch script-based installation with rollback support
    - Comprehensive error handling and logging
    """

    def __init__(self, test_mode: bool = False, mock_response: Optional[dict] = None):
        """Initialize AutoUpdater.

        Args:
            test_mode: If True, uses mock_response instead of real GitHub API calls.
                       Useful for testing without network access.
            mock_response: Mock response dict to return in test mode.
                           Should have same structure as check_update() return value.
        """
        self.latest_version: Optional[str] = None
        self.exe_url: Optional[str] = None
        self.release_notes: str = ""
        self.download_path: Optional[str] = None
        self.expected_sha256: Optional[str] = None
        self.test_mode = test_mode
        self.mock_response = mock_response

    def check_update(self, max_retries: int = 3) -> dict:
        """Check GitHub for newer version with retry logic and comprehensive logging.

        Args:
            max_retries: Maximum number of retry attempts (default: 3)

        Returns:
            dict with keys:
            - has_update: bool
            - version: str (new version if available)
            - notes: str (release notes)
            - error: str (error message if failed)
        """
        # Test mode support
        if self.test_mode and self.mock_response:
            logging.info("TEST MODE: Using mock response")
            return self.mock_response

        logging.info("=" * 60)
        logging.info("UPDATE CHECK STARTED")
        logging.info(f"Current version: {VERSION}")
        logging.info(f"GitHub repo: {GITHUB_REPO}")

        for attempt in range(max_retries):
            try:
                logging.info(f"Update check attempt {attempt + 1}/{max_retries}")

                url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
                logging.info(f"Fetching: {url}")

                # Create request with headers
                req = urllib.request.Request(url, headers={
                    'Accept': 'application/vnd.github.v3+json',
                    'User-Agent': 'CrossTrans'
                })
                logging.debug(f"Request headers: {dict(req.headers)}")

                # Create SSL context with error handling
                try:
                    ctx = get_ssl_context_for_url(url)
                    logging.info("SSL context created successfully")
                except Exception as ssl_err:
                    logging.error(f"SSL context creation failed: {ssl_err}", exc_info=True)
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        logging.warning(f"Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    return {
                        'has_update': False,
                        'error': ERROR_MESSAGES['ssl']
                    }

                # Make API request
                logging.info("Sending GitHub API request...")
                with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                    logging.info(f"Response status: {resp.status}")
                    logging.debug(f"Response headers: {dict(resp.headers)}")

                    data = json.loads(resp.read().decode())
                    logging.debug(f"Response data keys: {list(data.keys())}")

                # Validate and parse response
                latest = data.get('tag_name', '').lstrip('v')
                logging.info(f"Latest version from GitHub: {latest}")

                if not latest:
                    logging.error("No tag_name in GitHub response")
                    return {
                        'has_update': False,
                        'error': ERROR_MESSAGES['parse_error']
                    }

                # Version comparison
                try:
                    current_ver = version.parse(VERSION)
                    latest_ver = version.parse(latest)
                    logging.info(f"Version comparison: {VERSION} ({current_ver}) vs {latest} ({latest_ver})")

                    if latest_ver > current_ver:
                        logging.info(f"New version available: {latest}")

                        # Find exe asset
                        for asset in data.get('assets', []):
                            if asset['name'].lower().endswith('.exe'):
                                self.exe_url = asset['browser_download_url']
                                logging.info(f"Found EXE asset: {self.exe_url}")
                                break

                        if not self.exe_url:
                            logging.warning("No .exe asset found in release")
                            return {
                                'has_update': False,
                                'error': 'No executable file found in the release'
                            }

                        self.latest_version = latest
                        self.release_notes = data.get('body', '')

                        # Try to extract SHA256 from release notes
                        sha256_match = re.search(r'SHA256:?\s*([0-9a-fA-F]{64})', self.release_notes, re.IGNORECASE)
                        if sha256_match:
                            self.expected_sha256 = sha256_match.group(1)
                            logging.info(f"Found SHA256 checksum in release notes: {self.expected_sha256}")
                        else:
                            logging.warning("No SHA256 checksum found in release notes")
                            self.expected_sha256 = None

                        logging.info("Update check completed successfully - update available")
                        return {
                            'has_update': True,
                            'version': latest,
                            'notes': self.release_notes
                        }
                    else:
                        logging.info(f"No update available. Current version ({VERSION}) is up to date.")
                        return {'has_update': False, 'version': VERSION}

                except version.InvalidVersion as e:
                    logging.error(f"Invalid version format: {e}")
                    return {
                        'has_update': False,
                        'error': f'Version parsing error: {e}'
                    }

            except urllib.error.HTTPError as e:
                error_body = self._read_error_response(e)
                logging.error(f"HTTP {e.code}: {error_body}")

                if e.code == 403:
                    # GitHub rate limit
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        logging.warning(f"GitHub rate limit (403), retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        logging.error("GitHub rate limit exceeded after all retries")
                        return {
                            'has_update': False,
                            'error': ERROR_MESSAGES['rate_limit']
                        }

                elif e.code == 404:
                    # Repo not found - don't retry
                    logging.error("GitHub repository not found (404)")
                    return {
                        'has_update': False,
                        'error': 'Update service not available (repository not found)'
                    }

                elif e.code >= 500:
                    # Server error - retry
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        logging.warning(f"GitHub server error {e.code}, retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        logging.error(f"GitHub server error {e.code} persisted after all retries")
                        return {
                            'has_update': False,
                            'error': f'GitHub server error: HTTP {e.code}'
                        }

                # Other HTTP errors - don't retry
                logging.error(f"HTTP error {e.code}: {error_body}")
                return {
                    'has_update': False,
                    'error': f'GitHub API error: HTTP {e.code}'
                }

            except urllib.error.URLError as e:
                logging.error(f"Network error: {e.reason}")

                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logging.warning(f"Network error, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    logging.error("Network error persisted after all retries")
                    return {
                        'has_update': False,
                        'error': ERROR_MESSAGES['network']
                    }

            except Exception as e:
                logging.error(f"Unexpected error in update check: {e}", exc_info=True)
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logging.warning(f"Unexpected error, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    return {
                        'has_update': False,
                        'error': f'Update check failed: {str(e)}'
                    }

        logging.error("Update check failed after all retry attempts")
        return {
            'has_update': False,
            'error': 'Update check failed after all retry attempts'
        }

    def _read_error_response(self, http_error) -> str:
        """Helper to safely read error response body."""
        try:
            return http_error.read().decode('utf-8')
        except Exception:
            return "(could not read error details)"

    def download(self, progress_callback: Optional[Callable[[int], None]] = None) -> dict:
        """Download the new version with SHA256 integrity verification.

        Args:
            progress_callback: Called with progress percentage (0-100)

        Returns:
            dict with keys:
            - success: bool
            - error: str (if failed)
        """
        if not self.exe_url or not self.latest_version:
            logging.error("Download attempted without update URL or version")
            return {'success': False, 'error': 'No update available'}

        if not getattr(sys, 'frozen', False):
            logging.warning("Download attempted from source (not frozen EXE)")
            return {'success': False, 'error': 'Auto-update only works with exe version'}

        try:
            # Create temp directory
            temp_dir = tempfile.mkdtemp(prefix='crosstrans_update_')
            self.download_path = os.path.join(temp_dir, f'CrossTrans_v{self.latest_version}.exe')
            logging.info(f"Download path: {self.download_path}")

            req = urllib.request.Request(self.exe_url, headers={'User-Agent': 'CrossTrans'})
            ctx = get_ssl_context_for_url(self.exe_url)

            logging.info(f"Starting download from: {self.exe_url}")
            with urllib.request.urlopen(req, timeout=180, context=ctx) as response:
                total = int(response.headers.get('Content-Length', 0))
                downloaded = 0
                logging.info(f"File size: {total} bytes ({total / 1024 / 1024:.1f} MB)")

                with open(self.download_path, 'wb') as f:
                    while True:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)

                        if progress_callback and total > 0:
                            progress_callback(int(downloaded * 100 / total))

            logging.info(f"Download completed: {downloaded} bytes")

            # Verify SHA256 checksum if available
            if hasattr(self, 'expected_sha256') and self.expected_sha256:
                logging.info("Verifying download integrity with SHA256...")
                actual_sha256 = self._calculate_sha256(self.download_path)
                logging.info(f"Expected SHA256: {self.expected_sha256}")
                logging.info(f"Actual SHA256:   {actual_sha256}")

                if actual_sha256.lower() != self.expected_sha256.lower():
                    logging.error("SHA256 mismatch! Download may be corrupted.")
                    try:
                        os.unlink(self.download_path)
                        logging.info("Deleted corrupted download")
                    except Exception as del_err:
                        logging.warning(f"Could not delete corrupted file: {del_err}")

                    return {
                        'success': False,
                        'error': 'Downloaded file integrity check failed. Please try again.'
                    }

                logging.info("✓ Download integrity verified successfully!")
            else:
                logging.warning("No checksum available - skipping integrity verification")

            return {'success': True}

        except Exception as e:
            logging.error(f"Download failed: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def _calculate_sha256(self, file_path: str) -> str:
        """Calculate SHA256 hash of a file.

        Args:
            file_path: Path to the file

        Returns:
            SHA256 hash as hex string
        """
        import hashlib

        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def install_and_restart(self) -> dict:
        """Install the update and restart app with comprehensive error handling.

        Enhanced with:
        - 30-second timeout for process exit
        - 5 retry attempts for file operations
        - File size verification after copy
        - Status files for startup verification
        - Pending file path for MoveFileEx fallback

        Returns:
            dict with keys:
            - success: bool
            - error: str (if failed)
        """
        if not self.download_path or not os.path.exists(self.download_path):
            logging.error("Install attempted without valid download path")
            return {'success': False, 'error': 'No downloaded update found'}

        try:
            current_exe = sys.executable
            current_dir = os.path.dirname(current_exe)
            temp_dir = os.path.dirname(self.download_path)

            # Determine new EXE path with version in filename
            new_exe_name = f"CrossTrans_v{self.latest_version}.exe"
            new_exe_path = os.path.join(current_dir, new_exe_name)

            logging.info(f"Installing update from: {self.download_path}")
            logging.info(f"Current EXE: {current_exe}")
            logging.info(f"New EXE path: {new_exe_path}")
            logging.info(f"Target version: {self.latest_version}")

            # Create enhanced update batch script with timeout, retries, and verification
            batch_path = os.path.join(temp_dir, 'update.bat')
            batch_content = f'''@echo off
setlocal enabledelayedexpansion

:: Log file and status files
set LOGFILE="%TEMP%\\crosstrans_update.log"
set ERRORFILE="%TEMP%\\crosstrans_update_error.txt"
set SUCCESSFILE="%TEMP%\\crosstrans_update_success.txt"
set EXPECTEDFILE="%TEMP%\\crosstrans_update_expected.txt"
set PENDINGFILE="%TEMP%\\crosstrans_update_pending.txt"

:: Clean up old status files
del /F /Q %ERRORFILE% >NUL 2>&1
del /F /Q %SUCCESSFILE% >NUL 2>&1
del /F /Q %EXPECTEDFILE% >NUL 2>&1
del /F /Q %PENDINGFILE% >NUL 2>&1

echo ============================================== > %LOGFILE%
echo Update started at %DATE% %TIME% >> %LOGFILE%
echo Target version: {self.latest_version} >> %LOGFILE%
echo Source: {self.download_path} >> %LOGFILE%
echo Old EXE: {current_exe} >> %LOGFILE%
echo New EXE: {new_exe_path} >> %LOGFILE%
echo ============================================== >> %LOGFILE%

:: Wait for app to close with 30-second timeout
echo Waiting for CrossTrans to close (max 30 seconds)... >> %LOGFILE%
set /a MAX_WAIT=30
set /a WAITED=0

:wait
tasklist /FI "PID eq %1" 2>NUL | find /I "%1" >NUL
if not errorlevel 1 (
    if !WAITED! GEQ !MAX_WAIT! (
        echo TIMEOUT: Process did not close within 30 seconds >> %LOGFILE%
        echo Update failed: Application did not close in time > %ERRORFILE%
        echo {self.download_path} > %PENDINGFILE%
        goto launch_old
    )
    timeout /t 1 /nobreak >NUL
    set /a WAITED+=1
    echo Waiting... !WAITED!/!MAX_WAIT! >> %LOGFILE%
    goto wait
)

echo Process closed after !WAITED! seconds >> %LOGFILE%

:: Additional wait for file handle release
echo Waiting for file handles to release... >> %LOGFILE%
timeout /t 3 /nobreak >NUL

:: Copy new version to new path with 5 retries
echo Installing new version as {new_exe_name} (max 5 attempts)... >> %LOGFILE%
set /a RETRY=0

:copy_retry
copy /Y "{self.download_path}" "{new_exe_path}" >NUL 2>&1
if errorlevel 1 (
    set /a RETRY+=1
    echo Copy attempt !RETRY! failed >> %LOGFILE%
    if !RETRY! GEQ 5 (
        echo FATAL: Cannot copy new version after 5 attempts >> %LOGFILE%
        echo Update failed: Could not install new version > %ERRORFILE%
        echo {self.download_path} > %PENDINGFILE%
        goto launch_old
    )
    timeout /t 2 /nobreak >NUL
    goto copy_retry
)

:: Verify the new file exists
if not exist "{new_exe_path}" (
    echo FATAL: New version file not found after copy >> %LOGFILE%
    echo Update failed: Installation incomplete > %ERRORFILE%
    echo {self.download_path} > %PENDINGFILE%
    goto launch_old
)

:: Verify file size matches source
echo Verifying file integrity... >> %LOGFILE%
for %%I in ("{self.download_path}") do set SOURCE_SIZE=%%~zI
for %%I in ("{new_exe_path}") do set DEST_SIZE=%%~zI
echo Source size: !SOURCE_SIZE! bytes >> %LOGFILE%
echo Dest size: !DEST_SIZE! bytes >> %LOGFILE%

if not "!SOURCE_SIZE!"=="!DEST_SIZE!" (
    echo ERROR: File size mismatch - copy may be corrupted >> %LOGFILE%
    del /F /Q "{new_exe_path}" >NUL 2>&1
    echo Update failed: File copy incomplete - size mismatch > %ERRORFILE%
    echo {self.download_path} > %PENDINGFILE%
    goto launch_old
)

echo File integrity verified successfully >> %LOGFILE%

:: Backup old EXE (rename to .bak)
echo Backing up old EXE... >> %LOGFILE%
del /F /Q "{current_exe}.bak" >NUL 2>&1
move /Y "{current_exe}" "{current_exe}.bak" >NUL 2>&1
if errorlevel 1 (
    echo WARNING: Could not backup old EXE, it may still exist >> %LOGFILE%
)

echo Installation successful >> %LOGFILE%

:: Update Registry auto-start path if enabled
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "AITranslator" >NUL 2>&1
if not errorlevel 1 (
    reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "AITranslator" /t REG_SZ /d "{new_exe_path}" /f >NUL 2>&1
    echo Registry auto-start updated to {new_exe_name} >> %LOGFILE%
)

:: Write expected version for verification on next launch
echo {self.latest_version} > %EXPECTEDFILE%
echo Update completed successfully > %SUCCESSFILE%

:: Start new version
echo Starting new version: {new_exe_name} >> %LOGFILE%
:: Delay to allow Windows Defender to finish scanning new EXE
timeout /t 2 /nobreak >NUL
start "" "{new_exe_path}"

:: Wait and verify the process started
timeout /t 5 /nobreak >NUL
tasklist /FI "IMAGENAME eq {new_exe_name}" 2>NUL | find /I "{new_exe_name}" >NUL
if errorlevel 1 (
    echo First launch failed, retrying... >> %LOGFILE%
    timeout /t 3 /nobreak >NUL
    start "" "{new_exe_path}"
    timeout /t 3 /nobreak >NUL
)

echo Cleaning up temp files... >> %LOGFILE%
rmdir /S /Q "{temp_dir}" >NUL 2>&1

echo ============================================== >> %LOGFILE%
echo Update completed successfully at %DATE% %TIME% >> %LOGFILE%
echo ============================================== >> %LOGFILE%
goto end

:launch_old
:: Launch the old version (backup was restored or never moved)
echo Launching old version due to update failure... >> %LOGFILE%
if exist "{current_exe}" (
    start "" "{current_exe}"
) else if exist "{current_exe}.bak" (
    move /Y "{current_exe}.bak" "{current_exe}" >NUL 2>&1
    start "" "{current_exe}"
)
goto end

:end
echo Cleaning up update script... >> %LOGFILE%
del /F /Q "%~f0" >NUL 2>&1
'''
            with open(batch_path, 'w') as f:
                f.write(batch_content)

            logging.info(f"Created update batch script: {batch_path}")

            # Execute update script
            subprocess.Popen(
                ['cmd', '/c', batch_path, str(os.getpid())],
                creationflags=subprocess.CREATE_NO_WINDOW,
                close_fds=True
            )

            logging.info(f"Update script launched (PID: {os.getpid()}), force-exiting application...")
            import time
            time.sleep(0.5)  # Ensure log flush before exit
            # Use os._exit() instead of sys.exit() because sys.exit() raises SystemExit
            # which gets swallowed by Tkinter's after() callback handler, preventing process death.
            # The batch script waits for this PID to die before proceeding with the update.
            os._exit(0)

        except Exception as e:
            logging.error(f"Install failed: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def schedule_update_on_reboot(self, source_path: str, dest_path: str) -> dict:
        """Schedule file replacement on next Windows restart using MoveFileEx API.

        This is guaranteed to work as Windows handles it at boot time before
        any user applications start. Uses the Windows PendingFileRenameOperations
        registry key.

        Args:
            source_path: Path to the new version EXE (in temp folder)
            dest_path: Path to the current EXE to be replaced

        Returns:
            dict with keys:
            - success: bool
            - message: str (success message or error description)
        """
        import ctypes
        from ctypes import wintypes

        MOVEFILE_DELAY_UNTIL_REBOOT = 0x4
        MOVEFILE_REPLACE_EXISTING = 0x1

        try:
            kernel32 = ctypes.windll.kernel32

            # Set up function signature
            kernel32.MoveFileExW.argtypes = [
                wintypes.LPCWSTR,  # lpExistingFileName
                wintypes.LPCWSTR,  # lpNewFileName
                wintypes.DWORD    # dwFlags
            ]
            kernel32.MoveFileExW.restype = wintypes.BOOL

            # First, schedule deletion of the destination on reboot
            # This ensures the old file is removed before the new one is moved
            logging.info(f"Scheduling deletion of {dest_path} on reboot")
            kernel32.MoveFileExW(dest_path, None, MOVEFILE_DELAY_UNTIL_REBOOT)

            # Then schedule the move from source to destination
            logging.info(f"Scheduling move: {source_path} -> {dest_path}")
            result = kernel32.MoveFileExW(
                source_path,
                dest_path,
                MOVEFILE_DELAY_UNTIL_REBOOT | MOVEFILE_REPLACE_EXISTING
            )

            if result:
                logging.info("MoveFileEx succeeded - update scheduled for next restart")
                return {
                    'success': True,
                    'message': 'Update scheduled. The update will be applied when you restart Windows.'
                }
            else:
                error_code = ctypes.get_last_error()
                error_msg = f'MoveFileEx failed with error code {error_code}'
                logging.error(error_msg)

                # Common error codes
                if error_code == 5:
                    error_msg = 'Access denied. Try running as administrator.'
                elif error_code == 2:
                    error_msg = 'Source file not found.'
                elif error_code == 3:
                    error_msg = 'Path not found.'

                return {'success': False, 'message': error_msg}

        except Exception as e:
            logging.error(f"schedule_update_on_reboot failed: {e}", exc_info=True)
            return {'success': False, 'message': str(e)}
