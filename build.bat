@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 exit /b 1

set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo Khong tim thay .venv. Hay chay setup.bat truoc.
    exit /b 1
)

"%PYTHON_EXE%" "%CD%\scripts\build_release.py" %*
exit /b %ERRORLEVEL%
