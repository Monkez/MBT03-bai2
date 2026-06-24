@echo off
setlocal

cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo Khong tim thay uv. Dang dung python -m venv va pip.
    if not exist ".venv" python -m venv .venv
    if errorlevel 1 exit /b %ERRORLEVEL%
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    exit /b %ERRORLEVEL%
)

if not exist ".venv" uv venv --python 3.11
if errorlevel 1 exit /b %ERRORLEVEL%
uv pip install -r requirements.txt
exit /b %ERRORLEVEL%
