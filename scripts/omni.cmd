@echo off
rem Windows shim — dispatches to whichever Python 3.9+ launcher is on PATH.
rem Order: py -3 -> python -> python3. Every candidate is version-probed
rem first so a broken / missing-Python-3 launcher falls through to the
rem next rather than killing the session with its own failure code.
setlocal enabledelayedexpansion

rem Probe py -3 (must be callable AND map to Python 3.9+)
py -3 -c "import sys;raise SystemExit(0 if sys.version_info>=(3,9) else 1)" >nul 2>nul
if !errorlevel! equ 0 (
  py -3 "%~dp0omni.py" %*
  exit /b !errorlevel!
)

rem Probe python
python -c "import sys;raise SystemExit(0 if sys.version_info>=(3,9) else 1)" >nul 2>nul
if !errorlevel! equ 0 (
  python "%~dp0omni.py" %*
  exit /b !errorlevel!
)

rem Probe python3
python3 -c "import sys;raise SystemExit(0 if sys.version_info>=(3,9) else 1)" >nul 2>nul
if !errorlevel! equ 0 (
  python3 "%~dp0omni.py" %*
  exit /b !errorlevel!
)

echo ERROR: no working Python 3.9+ interpreter found on PATH.
echo        tried: py -3, python, python3
echo        install Python 3.9+ from https://www.python.org/downloads/
exit /b 127
