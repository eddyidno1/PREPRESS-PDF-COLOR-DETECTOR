@echo off
REM ===================================================================
REM  Build the "PDF Color Check" Windows app.
REM  Run this on a Windows PC that has Python 3.10+ installed
REM  (python.org installer, with "Add Python to PATH" checked).
REM  Just double-click this file, or run it from a command prompt.
REM ===================================================================
setlocal
cd /d "%~dp0"

REM Pick the Python launcher: prefer "py", fall back to "python".
where py >nul 2>&1
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")

echo.
echo === Step 1/3: installing dependencies ===
%PY% -m pip install --upgrade pip
%PY% -m pip install --only-binary=:all: -r requirements.txt pyinstaller pyinstaller-hooks-contrib
if errorlevel 1 goto :error

echo.
echo === Step 2/3: building the app (this takes a minute) ===
%PY% build.py
if errorlevel 1 goto :error

echo.
echo === Step 3/3: packaging a release-ready zip ===
powershell -NoProfile -Command "Compress-Archive -Path 'dist\PDF Color Check' -DestinationPath 'dist\PDF-Color-Check-Windows.zip' -Force"
if errorlevel 1 (
    echo WARNING: could not create the zip automatically.
    echo You can still zip the "dist\PDF Color Check" folder manually.
) else (
    echo Created: dist\PDF-Color-Check-Windows.zip
)

echo.
echo ============================================================
echo  Build complete.
echo  Your app is here:
echo      dist\PDF Color Check\PDF Color Check.exe
echo.
echo  Release-ready zip (upload this to a GitHub Release):
echo      dist\PDF-Color-Check-Windows.zip
echo.
echo  To run on another Windows PC, unzip it and launch
echo  "PDF Color Check.exe" inside the folder.
echo ============================================================
echo.
pause
exit /b 0

:error
echo.
echo *** Build failed. Read the messages above for the cause. ***
echo If Python was not found, install it from https://www.python.org/downloads/
echo and re-run this script.
echo.
pause
exit /b 1
