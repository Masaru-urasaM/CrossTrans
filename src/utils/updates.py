"""
Update checker and installer for CrossTrans.
"""
import os
import sys
import json
import logging
import tempfile
import subprocess
import urllib.request
from typing import Dict, Any, Optional, Callable

from packaging import version

from src.constants import VERSION, GITHUB_REPO
from src.core.ssl_pinning import get_ssl_context_for_url


def check_for_updates() -> Dict[str, Any]:
    """Check GitHub for newer releases."""
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        req = urllib.request.Request(url, headers={
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'CrossTrans'
        })
        ssl_context = get_ssl_context_for_url(url)
        with urllib.request.urlopen(req, timeout=10, context=ssl_context) as resp:
            data = json.loads(resp.read().decode())

        latest_version = data['tag_name'].lstrip('v')
        if version.parse(latest_version) > version.parse(VERSION):
            exe_url = None
            for asset in data.get('assets', []):
                if asset['name'].lower().endswith('.exe'):
                    exe_url = asset['browser_download_url']
                    break

            return {
                'available': True,
                'version': latest_version,
                'url': data['html_url'],
                'exe_url': exe_url,
                'notes': data.get('body', '')
            }
    except Exception as e:
        logging.warning(f"Update check failed: {e}")

    return {'available': False}


def download_and_install_update(exe_url: str, new_version: str,
                                progress_callback: Optional[Callable[[int, int, int], None]] = None) -> Dict[str, Any]:
    """
    Download new exe and prepare update script.
    Returns dict with 'success', 'error', or 'script_path'.
    """
    try:
        if getattr(sys, 'frozen', False):
            current_exe = sys.executable
        else:
            return {'success': False, 'error': 'Auto-update only works with exe version. Please download manually.'}

        temp_dir = tempfile.mkdtemp(prefix='ai_translator_update_')
        new_exe_path = os.path.join(temp_dir, f'CrossTrans_v{new_version}.exe')

        req = urllib.request.Request(exe_url, headers={'User-Agent': 'CrossTrans'})
        ssl_context = get_ssl_context_for_url(exe_url)

        with urllib.request.urlopen(req, timeout=60, context=ssl_context) as response:
            total_size = int(response.headers.get('Content-Length', 0))
            downloaded = 0
            chunk_size = 8192

            with open(new_exe_path, 'wb') as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    if progress_callback and total_size > 0:
                        percent = int(downloaded * 100 / total_size)
                        progress_callback(percent, downloaded, total_size)

        batch_path = os.path.join(temp_dir, 'update.bat')
        batch_content = f'''@echo off
echo Updating CrossTrans to v{new_version}...
echo.

REM Wait for the application to close
:waitloop
tasklist /FI "PID eq %1" 2>NUL | find /I "%1" >NUL
if not errorlevel 1 (
    timeout /t 1 /nobreak >NUL
    goto waitloop
)

REM Small delay to ensure file handles are released
timeout /t 2 /nobreak >NUL

REM Backup old exe
if exist "{current_exe}.backup" del "{current_exe}.backup"
move "{current_exe}" "{current_exe}.backup"

REM Copy new exe
copy "{new_exe_path}" "{current_exe}"

REM Start new version
start "" "{current_exe}"

REM Clean up
timeout /t 3 /nobreak >NUL
del "{new_exe_path}"
rmdir "{temp_dir}" 2>NUL

REM Delete this batch file
del "%~f0"
'''
        with open(batch_path, 'w') as f:
            f.write(batch_content)

        return {
            'success': True,
            'script_path': batch_path,
            'new_exe_path': new_exe_path
        }

    except Exception as e:
        logging.error(f"Update download failed: {e}")
        return {'success': False, 'error': str(e)}


def execute_update(script_path: str):
    """Execute the update script and exit the application."""
    pid = os.getpid()
    subprocess.Popen(
        ['cmd', '/c', script_path, str(pid)],
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
        close_fds=True
    )
