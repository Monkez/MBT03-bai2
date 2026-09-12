@echo off
setlocal

cd /d "%~dp0"

set "PYTHONPATH=%CD%\assets;%CD%"

set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

"%PYTHON_EXE%" -m compileall -q main.py scoring.py LAB\score_test.py LAB\scoring.py gui assets\server_client assets\OrangePiZero2W
if errorlevel 1 exit /b %ERRORLEVEL%

"%PYTHON_EXE%" -m unittest discover -s tests -p "test_*.py"
exit /b %ERRORLEVEL%
