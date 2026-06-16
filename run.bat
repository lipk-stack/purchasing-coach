@echo off

echo.
echo  ================================================
echo   Purchasing Coach - Starting...
echo  ================================================
echo.

REM Check for Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Please install Python 3.8+
    echo  Download from: https://www.python.org/downloads/
    pause
    exit /b 1
)

python .\dist\purchasing-coach.pyz --guideline .\samples\XXEON_IT_Procurement_Guideline.docx --template .\samples\TENDER_TEMPLATE.xlsx --web

pause
