# HADO Match Extractor - Development Guidelines

## Project Structure
- `hado_match_extractor.py` — CLI版スクリプト（スタンドアロン）
- `mobile_movie_cut/` — PyWebView desktop app (FastAPI + WebKit), cross-platform
  - `main.py` — Entry point: PyWebView window + uvicorn daemon thread
  - `app.py` — FastAPI routes (upload, process, download, SSE progress)
  - `extractor.py` — Base class: 共通処理パイプライン
  - `hado_detector.py` — HADO専用検出ロジック
  - `hadoworld_detector.py` — HADO WORLD専用検出ロジック
  - `static/app.js` — Frontend JS
  - `ffmpeg/` — バンドル用 ffmpeg バイナリ（.gitignore で除外）
  - `build_app.sh` — macOS ビルド → HADO Match Extractor.app
  - `build_app_win.bat` — Windows ビルド → dist\HADO Match Extractor\*.exe
  - `start.bat` — Windows 開発用クイック起動

## MANDATORY: Self-Review Before "Done"

After ANY code change, you MUST complete this checklist before saying "完了":

### Step 1: Run syntax check
```bash
bash mobile_movie_cut/check.sh
```

### Step 2: Re-read every changed file top-to-bottom
Verify: all symbols used in each function are actually defined/imported at that point.

### Step 3: Trace one happy path + one error path
- Happy path: user picks file → processing → download → success
- Error path: no matches found → error section shown (no download buttons)

### Step 4: Rebuild if any .py or template was changed
macOS:
```bash
bash mobile_movie_cut/build_app.sh
```
Windows:
```cmd
mobile_movie_cut\build_app_win.bat
```

## Known Pitfalls (past bugs)
- PyWebView: `<a href download>` doesn't work → use `window.pywebview.api.download_file()`
- PyWebView: file dialogs — macOS: `subprocess osascript`、Windows: `tkinter filedialog`
- macOS .app: launcher で bundled ffmpeg → Homebrew → system の順で PATH 設定
- Python: imports must be at module top — except `from app import app` in main() (PyInstaller対応)
- hard link (`os.link`) fails cross-filesystem → fallback to `shutil.copy2`
- PyInstaller: uvicorn に文字列 `"app:app"` は使えない → `from app import app` で直接渡す
- PyInstaller: `sys.frozen` 時に `os.chdir(os.path.dirname(sys.executable))` が必要
- temp_dir: `/tmp` ハードコード不可 → `tempfile.gettempdir()` を使用（Windows対応）
- ffmpeg: `ffmpeg/` ディレクトリにバンドル、`app.py` startup で PATH に追加
- HADO WORLD: スタッツ画面検出は左右分割カラー検出（左=暖色/赤、右=寒色/青）— 全体色%ではなく左右の色分布パターンで判定。ゲームプレイ中は赤青が全体に散在するため左右分割で除外
- HADO WORLD: WIN画面検出は中央ROI色優勢方式 — 中央ROI(25-70%,10-90%)で赤>10%かつ青<5%→RED WIN、青>10%かつ赤<5%→BLUE WIN。スタッツ画面(両方高い)やゲームプレイ(両方低い)を自然に除外。WIN検出失敗時はstats-to-stats境界にフォールバック
- HADO WORLD: 適応閾値は2セグメント以上で採用（1フレーム外れ値対策）— [20, 15, 12, 10, 8]を順に試し、最低閾値のみ1セグメントでも採用
