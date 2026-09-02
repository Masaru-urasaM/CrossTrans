@echo off
title Build CrossTrans EXE
cd /d "%~dp0"

:: Get version from Python code
for /f "delims=" %%i in ('python -c "from src.constants import VERSION; print(VERSION)"') do set APP_VERSION=%%i

echo ========================================================
echo Building CrossTrans v%APP_VERSION%...
echo ========================================================
echo.

:: Clean previous builds
echo [1/6] Cleaning previous builds...
if exist "build" rmdir /s /q "build" 2>nul
if exist "dist" rmdir /s /q "dist" 2>nul

:: Ensure ICO file exists
echo [2/6] Checking icon file...
if not exist "CrossTrans.ico" (
    echo Creating CrossTrans.ico from PNG...
    python -c "from PIL import Image; img = Image.open('CrossTrans.png'); img.save('CrossTrans.ico', format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
)

:: Verify the furigana reading dictionary is available to bundle.
:: Without kanwadict4.db the app still runs and still translates - it just stops
:: showing readings, silently. Cheaper to fail here than to ship that.
echo [3/6] Verifying furigana data files...
python tools\verify_furigana_bundle.py --source
if errorlevel 1 (
    echo.
    echo ========================================================
    echo ERROR: furigana reading dictionary missing. Build aborted.
    echo ========================================================
    pause
    exit /b 1
)

:: Build EXE
echo [4/6] Building EXE with PyInstaller...
python -m PyInstaller CrossTrans.spec --clean --noconfirm

:: Check build result and rename
echo [5/6] Finalizing...
if not exist "dist\CrossTrans.exe" goto :build_failed

:: Clear the way for the rename. `ren` fails with "a duplicate file name exists"
:: when the target is already there - usually a previously released EXE of the
:: same version that step 1 could not remove because it was still running.
if exist "dist\CrossTrans_v%APP_VERSION%.exe" del /f /q "dist\CrossTrans_v%APP_VERSION%.exe" 2>nul
if exist "dist\CrossTrans_v%APP_VERSION%.exe" goto :rename_blocked

ren "dist\CrossTrans.exe" "CrossTrans_v%APP_VERSION%.exe"

:: Verify the rename actually happened. Without this the script printed SUCCESS
:: for a file it had not created, and then ran the furigana check against that
:: stale EXE - so a build could be signed off on the strength of the previous
:: one. Measured on 2026-09-02.
if exist "dist\CrossTrans.exe" goto :rename_blocked
if not exist "dist\CrossTrans_v%APP_VERSION%.exe" goto :rename_blocked

echo.
echo ========================================================
echo SUCCESS! Created: dist\CrossTrans_v%APP_VERSION%.exe
echo ========================================================
for %%A in ("dist\CrossTrans_v%APP_VERSION%.exe") do echo File size: %%~zA bytes
echo.

:: Confirm the reading dictionary reached the archive - warns last so it is not buried
echo [6/6] Verifying bundled furigana data...
python tools\verify_furigana_bundle.py --exe "dist\CrossTrans_v%APP_VERSION%.exe"
if errorlevel 1 call :furigana_missing
echo.

:: Cleanup build folder
echo Cleaning up build folder...
rmdir /s /q "build" 2>nul

pause
exit /b 0

:build_failed
echo.
echo ========================================================
echo ERROR: Build failed! Check the output above for errors.
echo ========================================================
pause
exit /b 1

:rename_blocked
echo.
echo ========================================================
echo ERROR: could not name the build CrossTrans_v%APP_VERSION%.exe
echo A file of that name is already in dist\ and cannot be replaced -
echo it is most likely still running, or open in another program.
echo The build itself succeeded and is waiting as dist\CrossTrans.exe
echo Close or delete the old EXE, then run this script again.
echo ========================================================
pause
exit /b 1

:furigana_missing
echo.
echo ========================================================
echo WARNING: the EXE was built WITHOUT the reading dictionary.
echo Furigana will not work in this build. Do not release it.
echo ========================================================
exit /b
