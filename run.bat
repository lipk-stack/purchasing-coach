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

setlocal EnableExtensions DisableDelayedExpansion
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

REM Prefer the embedded build (bundles model + llama-cpp-python), then the
REM lightweight standard build. If neither exists, run from source.
set "PYZ=.\dist\purchasing-coach-embedded.pyz"
if exist "%PYZ%" goto found_embedded
set "PYZ=.\dist\purchasing-coach.pyz"
if exist "%PYZ%" goto found_standard
set "PYZ="
echo  [INFO] No portable build found; running from source.
goto after_app_choice

:found_embedded
echo  [INFO] Using embedded build - bundled SLM.
goto after_app_choice

:found_standard
echo  [INFO] Using standard build.

:after_app_choice

if not defined GUIDELINE set "GUIDELINE=.\samples\XXEON_IT_Procurement_Guideline.docx"
if not defined TEMPLATE  set "TEMPLATE=.\samples\TENDER_TEMPLATE.xlsx"

REM Clear stale Python bytecode so an edited source tree is recompiled and
REM nothing cached from a previous run is reused.
for /d /r %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" 2>nul

REM Pre-flight: catch a renamed or wrong-folder file here with a clear message
REM rather than failing deep inside the app. Drop your own files into samples\
REM keeping the same names, or set GUIDELINE / TEMPLATE to point at them.
if not exist "%GUIDELINE%" (
    echo  [ERROR] Guideline file not found:
    echo          %GUIDELINE%
    echo          Put your guideline in the samples\ folder as
    echo          XXEON_IT_Procurement_Guideline.docx ^(.docx/.pdf/.md/.txt^),
    echo          or:  set GUIDELINE=C:\path\to\your-guideline.docx ^& run.bat
    pause
    endlocal ^& exit /b 1
)
if not exist "%TEMPLATE%" (
    echo  [WARN] Template not found: %TEMPLATE%
    echo         Falling back to the built-in checklist layout.
)
echo  Guideline: %GUIDELINE%
echo  Template:  %TEMPLATE%
echo.

REM Default to the browser UI when no extra flags are passed.
if "%~1"=="" goto launch_default
goto launch_args

:launch_default
if defined PYZ goto launch_pyz_default
python -m coach --guideline "%GUIDELINE%" --template "%TEMPLATE%" --web
goto finish

:launch_pyz_default
python "%PYZ%" --guideline "%GUIDELINE%" --template "%TEMPLATE%" --web
goto finish

:launch_args
if defined PYZ goto launch_pyz_args
python -m coach --guideline "%GUIDELINE%" --template "%TEMPLATE%" %*
goto finish

:launch_pyz_args
python "%PYZ%" --guideline "%GUIDELINE%" --template "%TEMPLATE%" %*
goto finish

:finish
set "APP_RC=%ERRORLEVEL%"
pause
endlocal & exit /b %APP_RC%
