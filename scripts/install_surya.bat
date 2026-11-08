@echo off
REM Installs Surya OCR into this project's shared WSL venv (~/venvs/ocr-common).
REM Run this from a normal Windows cmd prompt. Every step is printed AND saved
REM to a log file in scripts\logs\, so it can be shared/inspected afterwards.

set LOGDIR=%~dp0logs
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

for /f "tokens=1-3 delims=/:. " %%a in ("%date% %time%") do set STAMP=%%a%%b%%c
set LOGFILE=%LOGDIR%\install_surya_%STAMP%.log

echo Log file: %LOGFILE%
echo(

wsl -e bash -lc "bash /mnt/c/Workspace/Antigravity_workspace/Latest_OCR/IndicOCR_21-09-2026/scripts/install_surya.sh 2>&1 | tee /mnt/c/Workspace/Antigravity_workspace/Latest_OCR/IndicOCR_21-09-2026/scripts/logs/install_surya_%STAMP%.log"

echo(
echo ============================================================
echo Full log saved to: %LOGFILE%
echo Send that file back if anything looks wrong.
echo ============================================================
pause
