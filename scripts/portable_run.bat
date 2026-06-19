@echo off
REM Purchasing Coach — Portable Launcher
REM
REM Double-click to start the browser chat UI.
REM Requires Python 3.10+ on PATH.
REM
REM Usage:
REM   run.bat                         : browser chat UI (default)
REM   run.bat --backend keyword       : use a specific backend
REM   run.bat --n-ctx 16384           : increase context window
REM   set GUIDELINE=mine.docx & run.bat   : use your own guideline

setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

echo.
echo  ================================================
echo   Purchasing Coach v2.1.0 - Portable Edition
echo  ================================================
echo.

REM Check for Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python 3.10+ not found. Install it from
    echo          https://www.python.org/downloads/
    echo          Make sure to tick "Add Python to PATH" during install.
    pause
    exit /b 1
)

REM Find the .pyz (should be in the same directory as this script)
set "PYZ="
for %%f in ("%~dp0purchasing-coach-embedded.pyz" "%~dp0purchasing-coach.pyz" "%~dp0purchasing-coach*.pyz") do if not defined PYZ if exist "%%~ff" set "PYZ=%%~ff"
if not defined PYZ goto missing_pyz
echo  [INFO] Using: %PYZ%
echo.
goto after_pyz

:missing_pyz
echo  [ERROR] purchasing-coach*.pyz not found next to this script.
pause
endlocal & exit /b 1

:after_pyz

if not defined GUIDELINE set "GUIDELINE=.\samples\XXEON_IT_Procurement_Guideline.docx"
if not defined TEMPLATE  set "TEMPLATE=.\samples\TENDER_TEMPLATE.xlsx"

REM Default to the embedded backend (bundled model) + browser UI.
REM Pass extra flags to override (e.g. run.bat --backend keyword).
if "%~1"=="" goto launch_default
goto launch_args

:launch_default
python "%PYZ%" --backend embedded --guideline "%GUIDELINE%" --template "%TEMPLATE%" --web
goto finish

:launch_args
python "%PYZ%" --guideline "%GUIDELINE%" --template "%TEMPLATE%" %*
goto finish

:finish
set "APP_RC=%ERRORLEVEL%"
pause
endlocal & exit /b %APP_RC%
