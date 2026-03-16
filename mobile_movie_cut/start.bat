@echo off
REM HADO Match Extractor - 開発用クイック起動
REM .exe を使わず Python から直接起動する場合に使用

pushd "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo 仮想環境が見つかりません。build_app_win.bat を先に実行してください。
    pause
    exit /b 1
)

.venv\Scripts\python main.py
popd
