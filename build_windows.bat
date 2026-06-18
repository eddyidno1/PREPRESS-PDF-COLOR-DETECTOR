@echo off
REM ===================================================================
REM  Build the "PDF Color Check" Windows app.
REM  Run this on a Windows PC that has 64-bit Python 3.10-3.13 installed
REM  (python.org installer, with "Add Python to PATH" checked).
REM  Just double-click this file, or run it from a command prompt.
REM
REM  NOTE: the PDF libraries (pikepdf, PyMuPDF) only ship 64-bit wheels
REM  for Python 3.10-3.13. Python 3.14+ or 32-bit Python will NOT work.
REM ===================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM --- Find a usable interpreter: 64-bit, Python 3.10-3.13 ---
set "PY="
call :try_python py -3.12
call :try_python py -3.13
call :try_python py -3.11
call :try_python py -3.10
call :try_python python
call :try_python py -3
if not defined PY goto :nopython

echo Using interpreter: %PY%
%PY% -c "import sys;print('Python',sys.version)"

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

REM --- subroutine: if %* is 64-bit Python 3.10-3.13, set PY (first match wins) ---
:try_python
if defined PY goto :eof
%* -c "import sys,struct;sys.exit(0 if (3,10)<=sys.version_info[:2]<(3,14) and struct.calcsize('P')==8 else 1)" >nul 2>&1
if %errorlevel%==0 set "PY=%*"
goto :eof

:nopython
echo.
echo *** No compatible Python found. ***
echo.
echo This app needs 64-bit Python 3.10, 3.11, 3.12, or 3.13.
echo (pikepdf / PyMuPDF have no wheels for Python 3.14+ or 32-bit Python.)
echo.
echo Fix: install the "Windows installer (64-bit)" of Python 3.12 from
echo      https://www.python.org/downloads/release/python-3129/
echo      and tick "Add Python to PATH", then re-run this script.
echo.
pause
exit /b 1

:error
echo.
echo *** Build failed. Read the messages above for the cause. ***
echo If it mentions pikepdf/pymupdf wheels, your Python is likely
echo 32-bit or version 3.14+; install 64-bit Python 3.12 (see python.org).
echo.
pause
exit /b 1
