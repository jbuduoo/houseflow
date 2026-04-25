@echo off
title AI Chrome Launcher
echo ------------------------------------------------------------
echo   AI Chrome Launcher v3.0
echo ------------------------------------------------------------
echo   1. Closing any existing Chrome processes...
taskkill /F /IM chrome.exe /T >nul 2>&1

echo   2. Searching for Chrome Path...
set "USER_DIR=%~dp0temp_chrome_session"
set "ARGS=--remote-debugging-port=9222 --user-data-dir="%USER_DIR%""

if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" %ARGS%
) else if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    start "" "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" %ARGS%
) else (
    start chrome.exe %ARGS%
)

echo   3. Launching Chrome (Remote Debugging Port: 9222)...
echo.
echo   SUCCESS! Please LOGIN to HouseFlow in the new Chrome window.
echo   Then run: python houseflow_detail_enricher.py
echo ------------------------------------------------------------
pause
