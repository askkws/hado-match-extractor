# HADO Match Extractor - Development Guidelines

## Project Structure
- `hado_match_extractor.py` — CLI版スクリプト（スタンドアロン）
- `mobile_movie_cut/` — PyWebView desktop app (FastAPI + WebKit)
  - `main.py` — Entry point: PyWebView window + uvicorn daemon thread
  - `app.py` — FastAPI routes (upload, process, download, SSE progress)
  - `extractor.py` — Base class: 共通処理パイプライン
  - `hado_detector.py` — HADO専用検出ロジック
  - `hadoworld_detector.py` — HADO WORLD専用検出ロジック
  - `static/app.js` — Frontend JS
  - `build_app.sh` — Builds HADO Match Extractor.app bundle

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
```bash
bash mobile_movie_cut/build_app.sh
```

## Known Pitfalls (past bugs)
- PyWebView: `<a href download>` doesn't work → use `window.pywebview.api.download_file()`
- PyWebView: file dialogs must NOT run on macOS main thread → use `subprocess osascript`
- macOS .app: PATH lacks Homebrew → launcher script sets it explicitly
- Python: imports must be at module top — never inside functions
- hard link (`os.link`) fails cross-filesystem → fallback to `shutil.copy2`
- HADO WORLD: BLUE WIN閾値は13%以上（8%だとゲームプレイ中の青UIで誤検出）
