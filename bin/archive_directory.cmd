@echo off
set "SCRIPT_DIR=%~dp0"
"%SCRIPT_DIR%..\venv\Scripts\python.exe" "%SCRIPT_DIR%..\archive_directory.py" %*
