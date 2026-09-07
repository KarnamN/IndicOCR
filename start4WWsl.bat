@echo off
echo =======================================================
echo Starting PDF to EPUB Converter in WSL (Ubuntu)...
echo =======================================================
echo.
wsl --shutdown  && cls && wsl bash -c "cd /mnt/c/Workspace/Antigravity_workspace/Latest_OCR/Myocr_New_08-02-2026 && ./scripts/start.sh"
pause
