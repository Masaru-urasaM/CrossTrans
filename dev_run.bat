@echo off
title CrossTrans Dev Runner
color 0A

echo ========================================
echo   CrossTrans Dev Runner
echo ========================================
echo.

cd /d "%~dp0"

echo [1/2] Killing running CrossTrans...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and $_.CommandLine -match 'main\.py' } | ForEach-Object { Write-Host ('       Killing PID ' + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force }; Start-Sleep -Seconds 2"
echo        Done.

echo.
echo [2/2] Starting CrossTrans...
echo ========================================
echo.

python main.py

echo.
echo ========================================
echo   CrossTrans exited (code: %errorlevel%)
echo ========================================
pause
