@echo off
rem Windows shim — dispatches to whichever Python launcher is on PATH.
rem Order: py -3 -> python -> python3. Fails loudly if none found.
setlocal enabledelayedexpansion

where py >nul 2>nul
if !errorlevel! equ 0 (
  py -3 "%~dp0omni.py" %*
  exit /b !errorlevel!
)

where python >nul 2>nul
if !errorlevel! equ 0 (
  python "%~dp0omni.py" %*
  exit /b !errorlevel!
)

where python3 >nul 2>nul
if !errorlevel! equ 0 (
  python3 "%~dp0omni.py" %*
  exit /b !errorlevel!
)

echo ERROR: no Python 3 interpreter found on PATH.
echo        tried: py -3, python, python3
echo        install Python 3.9+ from https://www.python.org/downloads/
exit /b 127
