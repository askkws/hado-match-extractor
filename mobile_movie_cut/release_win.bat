@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM Build and package Windows release ZIP for HADO Match Extractor
REM Usage: release_win.bat <version>
REM Example: release_win.bat 1.0.0

set "VERSION=%~1"
if "%VERSION%"=="" (
    echo Usage: release_win.bat ^<version^>
    echo Example: release_win.bat 1.0.0
    goto :END
)

pushd "%~dp0"

set "PROJECT_ROOT=%CD%\.."
set "RELEASE_DIR=%PROJECT_ROOT%\releases"
set "ZIP_NAME=HADO-Match-Extractor-v%VERSION%-Windows.zip"

echo ========================================
echo  HADO Match Extractor - Windows Release
echo  Version: %VERSION%
echo ========================================
echo.

REM --- 1. Build .exe ---
echo [1/2] Building .exe ...
call build_app_win.bat
if errorlevel 1 (
    echo ERROR: Build failed.
    goto :END
)
echo.

REM --- 2. Create ZIP ---
echo [2/2] Creating ZIP ...
if not exist "%RELEASE_DIR%" mkdir "%RELEASE_DIR%"

REM Use PowerShell to create ZIP (single exe only)
powershell -NoProfile -Command "Compress-Archive -Path 'dist\HADO Match Extractor.exe' -DestinationPath '%RELEASE_DIR%\%ZIP_NAME%' -Force"
if errorlevel 1 (
    echo ERROR: ZIP creation failed.
    goto :END
)

echo.
echo ========================================
echo  Release ZIP created!
echo.
echo  %RELEASE_DIR%\%ZIP_NAME%
echo.
echo  To publish:
echo  gh release create v%VERSION% ^
echo    "%RELEASE_DIR%\%ZIP_NAME%" ^
echo    --title "v%VERSION%" --notes "Release v%VERSION%"
echo ========================================

:END
popd
echo.
echo Press any key to close...
pause >nul
