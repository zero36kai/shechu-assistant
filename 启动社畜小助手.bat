@echo off
setlocal
if exist "%~dp0ShechuAssistant.exe" (
  start "" "%~dp0ShechuAssistant.exe"
  exit /b 0
)
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
  echo [FAIL] V2 Python environment is missing. See README.md.
  pause
  exit /b 1
)
start "" "%~dp0.venv\Scripts\pythonw.exe" -B "%~dp0run_v2.py" --heartbeat --show
