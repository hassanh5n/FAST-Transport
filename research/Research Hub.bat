@echo off
title FleetCentric Research Hub
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python is not installed on Windows. Install it from https://www.python.org/downloads/ and try again.
  pause
  exit /b 1
)
python hub\serve.py
if errorlevel 1 pause
