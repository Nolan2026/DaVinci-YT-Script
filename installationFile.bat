@echo off
setlocal EnableDelayedExpansion
title YouTube ^> DaVinci Resolve - Auto Installer

:: ============================================================
::  Colors via ANSI (requires Windows 10 1903+)
:: ============================================================
for /f %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
set "GREEN=%ESC%[92m"
set "CYAN=%ESC%[96m"
set "YELLOW=%ESC%[93m"
set "RED=%ESC%[91m"
set "BOLD=%ESC%[1m"
set "RESET=%ESC%[0m"

cls
echo.
echo %CYAN%%BOLD%  =================================================%RESET%
echo %CYAN%%BOLD%    YouTube ^>^> DaVinci Resolve  -  Auto Installer  %RESET%
echo %CYAN%%BOLD%  =================================================%RESET%
echo.

:: ============================================================
::  Must run as Administrator
:: ============================================================
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo %RED%  [!] Please right-click this file and choose "Run as administrator".%RESET%
    echo.
    pause
    exit /b 1
)

:: ============================================================
::  STEP 1 — Check Python
:: ============================================================
echo %BOLD%  [1/4] Checking Python...%RESET%
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo %YELLOW%  [~] Python not found. Opening download page...%RESET%
    start https://www.python.org/downloads/
    echo %YELLOW%  [~] Install Python, tick "Add to PATH", then re-run this installer.%RESET%
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo %GREEN%  [OK] %PYVER% found%RESET%
echo.

:: ============================================================
::  STEP 2 — Install / upgrade yt-dlp
:: ============================================================
echo %BOLD%  [2/4] Installing yt-dlp...%RESET%
pip install -U yt-dlp >nul 2>&1
if %errorlevel% neq 0 (
    echo %RED%  [FAIL] Could not install yt-dlp. Check your internet connection.%RESET%
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('yt-dlp --version 2^>^&1') do set YTDLP=%%v
echo %GREEN%  [OK] yt-dlp %YTDLP% installed%RESET%
echo.

:: ============================================================
::  STEP 3 — Install ffmpeg via winget
:: ============================================================
echo %BOLD%  [3/4] Installing ffmpeg...%RESET%
ffmpeg -version >nul 2>&1
if %errorlevel% equ 0 (
    echo %GREEN%  [OK] ffmpeg already installed — skipping%RESET%
) else (
    winget --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo %YELLOW%  [~] winget not available. Skipping ffmpeg.%RESET%
        echo %YELLOW%      Download manually from: https://ffmpeg.org/download.html%RESET%
    ) else (
        echo %CYAN%  Installing ffmpeg via winget (this may take a minute)...%RESET%
        winget install --id Gyan.FFmpeg -e --silent --accept-source-agreements --accept-package-agreements >nul 2>&1
        if %errorlevel% equ 0 (
            echo %GREEN%  [OK] ffmpeg installed successfully%RESET%
        ) else (
            echo %YELLOW%  [~] ffmpeg install may have failed or already exists.%RESET%
            echo %YELLOW%      Try manually: winget install Gyan.FFmpeg%RESET%
        )
    )
)
echo.

:: ============================================================
::  STEP 4 — Install Node.js via winget (optional)
:: ============================================================
echo %BOLD%  [4/4] Installing Node.js (optional, fixes YouTube 403 errors)...%RESET%
node --version >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%v in ('node --version 2^>^&1') do set NODEVER=%%v
    echo %GREEN%  [OK] Node.js %NODEVER% already installed — skipping%RESET%
) else (
    winget --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo %YELLOW%  [~] winget not available. Skipping Node.js.%RESET%
        echo %YELLOW%      Download manually from: https://nodejs.org%RESET%
    ) else (
        echo %CYAN%  Installing Node.js via winget...%RESET%
        winget install --id OpenJS.NodeJS -e --silent --accept-source-agreements --accept-package-agreements >nul 2>&1
        if %errorlevel% equ 0 (
            echo %GREEN%  [OK] Node.js installed successfully%RESET%
        ) else (
            echo %YELLOW%  [~] Node.js install may have failed or already exists.%RESET%
        )
    )
)
echo.

:: ============================================================
::  STEP 5 — Copy script to DaVinci Resolve Utility folder
:: ============================================================
echo %BOLD%  [5/5] Copying YouTubeDownloader.py to DaVinci Resolve...%RESET%

set "RESOLVE_SCRIPTS=%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility"
set "SCRIPT_SRC=%~dp0YouTubeDownloader.py"

:: Check source file exists
if not exist "%SCRIPT_SRC%" (
    echo %RED%  [FAIL] YouTubeDownloader.py not found next to this installer.%RESET%
    echo %RED%         Make sure both files are in the same folder.%RESET%
    echo.
    pause
    exit /b 1
)

:: Create destination folder
if not exist "%RESOLVE_SCRIPTS%" (
    mkdir "%RESOLVE_SCRIPTS%" >nul 2>&1
    echo %CYAN%  Created Resolve Scripts\Utility folder%RESET%
)

:: Copy the file
copy /y "%SCRIPT_SRC%" "%RESOLVE_SCRIPTS%\" >nul 2>&1
if %errorlevel% equ 0 (
    echo %GREEN%  [OK] Copied to:%RESET%
    echo %GREEN%       %RESOLVE_SCRIPTS%%RESET%
) else (
    echo %RED%  [FAIL] Could not copy the script. Is DaVinci Resolve running?%RESET%
    pause
    exit /b 1
)
echo.

:: ============================================================
::  Done
:: ============================================================
echo %GREEN%%BOLD%  =================================================%RESET%
echo %GREEN%%BOLD%    All done! Everything is installed.             %RESET%
echo %GREEN%%BOLD%  =================================================%RESET%
echo.
echo %CYAN%  How to use:%RESET%
echo   1. Open DaVinci Resolve
echo   2. Go to  Workspace ^> Scripts ^> Utility ^> YouTubeDownloader
echo   3. Paste a YouTube URL and click  Download ^& Add
echo.
echo %YELLOW%  NOTE: If ffmpeg or Node.js were just installed, restart%RESET%
echo %YELLOW%  your PC once so they are picked up by the PATH.%RESET%
echo.
pause
