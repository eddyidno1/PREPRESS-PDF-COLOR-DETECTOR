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
echo === Step 1/2: installing dependencies ===
%PY% -m pip install --upgrade pip
%PY% -m pip install --only-binary=:all: -r requirements.txt pyinstaller pyinstaller-hooks-contrib
if errorlevel 1 goto :error

echo.
echo === Step 2/2: building the app (this takes a minute) ===
%PY% build.py
if errorlevel 1 goto :error

echo.
echo ============================================================
echo  Build complete.
echo  Your app is here:
echo      dist\PDF Color Check\PDF Color Check.exe
echo.
echo  To move it to another Windows PC, copy the WHOLE
echo  "dist\PDF Color Check" folder (zip it first), then run
echo  "PDF Color Check.exe" inside it.
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
