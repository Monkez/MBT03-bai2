@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
if exist "%PYTHON_EXE%" (
    "%PYTHON_EXE%" "%CD%\main.py"
    exit /b %ERRORLEVEL%
)

python "%CD%\main.py"
exit /b %ERRORLEVEL%

