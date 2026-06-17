@echo off
REM Purchasing Coach - easy startup for Windows.
REM
REM   run.bat                     : browser chat UI with the bundled samples
REM   run.bat --backend embedded  : any extra flags are forwarded to the app
REM   run.bat --backend ollama    : use a specific backend (see README)
REM   set GUIDELINE=mine.docx & run.bat   : use your own guideline / template
REM
REM With no arguments it launches the local web UI. Pass any CLI flags to
REM override (forwarded verbatim; argparse takes the last value).
REM
REM If purchasing-coach-embedded.pyz exists (built with --with-model), it is
REM preferred because it bundles an on-device SLM — no external server needed.

setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo  ================================================
echo   Purchasing Coach - Starting...
echo  ================================================
echo.

REM Check for Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python 3.10+ not found. Install it from
    echo          https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Prefer the embedded build (bundles model + llama-cpp-python), fall back
REM to the lightweight standard build.
set "PYZ=.\dist\purchasing-coach-embedded.pyz"
if exist "!PYZ!" (
    echo  [INFO] Using embedded build (bundled SLM).
) else (
    set "PYZ=.\dist\purchasing-coach.pyz"
    if not exist "!PYZ!" (
        echo  [ERROR] No build found. Run:
        echo          python scripts\build_portable.py --with-model
        pause
        exit /b 1
    )
    echo  [INFO] Using standard build.
)

if "%GUIDELINE%"=="" set "GUIDELINE=.\samples\XXEON_IT_Procurement_Guideline.docx"
if "%TEMPLATE%"==""  set "TEMPLATE=.\samples\TENDER_TEMPLATE.xlsx"

REM Default to the browser UI when no extra flags are passed.
if "%~1"=="" (
    python "!PYZ!" --guideline "%GUIDELINE%" --template "%TEMPLATE%" --web
) else (
    python "!PYZ!" --guideline "%GUIDELINE%" --template "%TEMPLATE%" %*
)

pause
endlocal
