@echo off
setlocal
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
  echo [FAIL] V2 Python environment is missing. See README.md.
  pause
  exit /b 1
)
start "" "%~dp0.venv\Scripts\pythonw.exe" -B "%~dp0run_v2.py" --heartbeat --show
