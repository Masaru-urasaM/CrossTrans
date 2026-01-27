@echo off
title Build CrossTrans EXE
cd /d "%~dp0"

:: Get version from Python code
for /f "delims=" %%i in ('python -c "from src.constants import VERSION; print(VERSION)"') do set APP_VERSION=%%i

echo ========================================================
echo Building CrossTrans v%APP_VERSION%...
echo Please wait, this process takes approximately 1-2 minutes.
echo ========================================================
echo.

python -m PyInstaller CrossTrans.spec --clean --noconfirm

:: Rename output file with version
if exist "dist\CrossTrans.exe" (
    if exist "dist\CrossTrans_v%APP_VERSION%.exe" del "dist\CrossTrans_v%APP_VERSION%.exe"
    ren "dist\CrossTrans.exe" "CrossTrans_v%APP_VERSION%.exe"
)

echo.
echo ========================================================
echo DONE! Created: dist\CrossTrans_v%APP_VERSION%.exe
pause