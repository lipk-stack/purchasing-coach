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

setlocal
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

if "%GUIDELINE%"=="" set "GUIDELINE=.\samples\XXEON_IT_Procurement_Guideline.docx"
if "%TEMPLATE%"==""  set "TEMPLATE=.\samples\TENDER_TEMPLATE.xlsx"

REM Default to the browser UI when no extra flags are passed.
if "%~1"=="" (
    python .\dist\purchasing-coach.pyz --guideline "%GUIDELINE%" --template "%TEMPLATE%" --web
) else (
    python .\dist\purchasing-coach.pyz --guideline "%GUIDELINE%" --template "%TEMPLATE%" %*
)

pause
endlocal
