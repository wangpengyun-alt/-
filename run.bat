@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Image Editor

rem Prefer an installed Python that already has Pillow.
where py >nul 2>nul
if not errorlevel 1 (
    py -c "import PIL" >nul 2>nul
    if not errorlevel 1 (
        set "PY=py"
        goto :run
    )
)

where python >nul 2>nul
if not errorlevel 1 (
    python -c "import PIL" >nul 2>nul
    if not errorlevel 1 (
        set "PY=python"
        goto :run
    )
)

rem Fallback: Python runtime bundled with this workspace tool.
set "BUNDLED=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if exist "%BUNDLED%" (
    "%BUNDLED%" -c "import PIL" >nul 2>nul
    if not errorlevel 1 (
        set "PY=%BUNDLED%"
        goto :run
    )
)

echo.
echo [ERROR] Python with Pillow was not found on this computer.
echo.
echo  1. Install Python 3.10 or newer from https://www.python.org/downloads/
echo  2. During installation, enable "Add python.exe to PATH".
echo  3. Open a terminal in this folder and run:
echo         pip install -r requirements.txt
echo.
echo Then double-click run.bat again.
echo.
pause
exit /b 1

:run
rem If pythonw.exe exists beside Python, start without a console window.
for %%I in ("%PY%") do (
    set "PYDIR=%%~dpI"
    set "PYNAME=%%~nxI"
)
if /I "%PYNAME%"=="python.exe" if exist "%PYDIR%pythonw.exe" (
    start "" "%PYDIR%pythonw.exe" "%~dp0image_editor.py" %*
    exit /b 0
)
if /I "%PY%"=="py" (
    where pyw >nul 2>nul
    if not errorlevel 1 (
        start "" pyw "%~dp0image_editor.py" %*
        exit /b 0
    )
)

"%PY%" "%~dp0image_editor.py" %*
if errorlevel 1 pause
exit /b 0
