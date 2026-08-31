@echo off
setlocal EnableExtensions

rem This file is intentionally a manual launcher; it creates no background task.
set "WINDOWS_DIRECTORY=%~dp0"
for %%I in ("%WINDOWS_DIRECTORY%..") do set "AGENT_DIRECTORY=%%~fI"
set "VENV_DIRECTORY=%AGENT_DIRECTORY%\.venv"
set "VENV_PYTHON=%VENV_DIRECTORY%\Scripts\python.exe"
set "CONFIG_PATH=%AGENT_DIRECTORY%\config.json"

if not exist "%VENV_PYTHON%" (
    echo ARPHE Remote Agent is not installed. Run setup_windows.ps1 first.
    pause
    exit /b 1
)

if not exist "%CONFIG_PATH%" (
    echo Local config.json is missing. Run setup_windows.ps1 first.
    pause
    exit /b 1
)

call "%VENV_DIRECTORY%\Scripts\activate.bat"
"%VENV_PYTHON%" "%AGENT_DIRECTORY%\start_agent.py" --config "%CONFIG_PATH%"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo ARPHE Remote Agent stopped with exit code %EXIT_CODE%.
    pause
)
exit /b %EXIT_CODE%
