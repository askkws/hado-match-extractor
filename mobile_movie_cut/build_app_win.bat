@echo off
chcp 65001 >nul 2>&1

pushd "%~dp0"
echo Current directory: %CD%
echo.

echo ========================================
echo  HADO Match Extractor - Build .exe
echo ========================================
echo.

REM --- 1. Python ---
py -3.12 --version
if errorlevel 1 (
    echo.
    echo ERROR: Python 3.12 not found.
    echo Download from: https://www.python.org/ftp/python/3.12.11/python-3.12.11-amd64.exe
    echo Make sure to check "Add python.exe to PATH" during install.
    goto :END
)
echo.

REM --- 2. venv ---
if not exist ".venv\Scripts\pip.exe" (
    echo Creating virtual environment...
    if exist ".venv" rmdir /s /q ".venv"
    py -3.12 -m venv .venv
    if errorlevel 1 goto :END
)

echo Installing dependencies...
.venv\Scripts\pip install -q --no-cache-dir -r requirements.txt
if errorlevel 1 goto :END
echo Done.
echo.

REM --- 3. ffmpeg ---
if not exist "ffmpeg\ffmpeg.exe" (
    echo ERROR: ffmpeg\ffmpeg.exe not found.
    echo See ffmpeg\README.md for download instructions.
    goto :END
)
if not exist "ffmpeg\ffprobe.exe" (
    echo ERROR: ffmpeg\ffprobe.exe not found.
    echo See ffmpeg\README.md for download instructions.
    goto :END
)
echo ffmpeg found in ffmpeg\
echo.

REM --- 4. PyInstaller ---
echo Building .exe ...
.venv\Scripts\pyinstaller --noconfirm --onefile --windowed --name "HADO Match Extractor" --add-data "templates;templates" --add-data "static;static" --add-data "app.py;." --add-data "extractor.py;." --add-data "hado_detector.py;." --add-data "hadoworld_detector.py;." --add-binary "ffmpeg\ffmpeg.exe;ffmpeg" --add-binary "ffmpeg\ffprobe.exe;ffmpeg" --hidden-import uvicorn.logging --hidden-import uvicorn.loops --hidden-import uvicorn.loops.auto --hidden-import uvicorn.protocols --hidden-import uvicorn.protocols.http --hidden-import uvicorn.protocols.http.auto --hidden-import uvicorn.protocols.websockets --hidden-import uvicorn.protocols.websockets.auto --hidden-import uvicorn.lifespan --hidden-import uvicorn.lifespan.on --hidden-import cv2 main.py
if errorlevel 1 (
    echo.
    echo ERROR: Build failed.
    goto :END
)

echo.
echo ========================================
echo  Build complete!
echo.
echo  Output: dist\HADO Match Extractor.exe
echo ========================================

:END
popd
echo.
echo Press any key to close...
pause >nul
