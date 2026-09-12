@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo Khong tim thay .venv. Hay chay setup.bat truoc.
    exit /b 1
)

if "%~1"=="" (
    echo Cach dung: deploy-board.bat DIA_CHI_IP [--trust-new-host]
    echo Vi du lan dau: deploy-board.bat 10.207.242.220 --trust-new-host
    exit /b 2
)

"%PYTHON_EXE%" assets\OrangePiZero2W\deploy.py %*
exit /b %ERRORLEVEL%
