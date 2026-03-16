# HADO Match Extractor

HADOの試合動画から個別の試合クリップを自動抽出するツールです。

## ダウンロード（デスクトップアプリ）

[Releases ページ](https://github.com/askkws/hado-match-extractor/releases) から最新版をダウンロードしてください。

| OS | ファイル | サイズ目安 |
|----|---------|-----------|
| macOS (Apple Silicon) | `HADO-Match-Extractor-vX.X.X-macOS.zip` | 約5MB |
| Windows | `HADO-Match-Extractor-vX.X.X-Windows.zip` | 約50MB |

### macOS

1. ZIP をダウンロード → 解凍
2. `HADO Match Extractor` フォルダ内の `HADO Match Extractor.app` をダブルクリック
3. **初回のみ**: 「開発元が未確認」と表示されたら、右クリック →「開く」→「開く」で起動
4. 初回起動時に Python venv と依存パッケージを自動セットアップ（1〜2分）

> **必要条件**: Python 3.10 以上がインストールされていること（[python.org](https://www.python.org/) または `brew install python`）

### Windows

1. ZIP をダウンロード → 解凍
2. `HADO Match Extractor` フォルダ内の `HADO Match Extractor.exe` をダブルクリック
3. 初回起動時に「WindowsによってPCが保護されました」と表示されたら「詳細情報」→「実行」

> Windows版は Python 不要です（バイナリに同梱済み）

### 使い方

1. 「動画を選択」ボタンをクリック
2. ゲームタイプを選択（HADO / HADO WORLD）
3. 「処理開始」ボタンをクリック
4. 進捗バーで処理状況を確認
5. 完了後、ダウンロードボタンで保存

---

## 2つのバージョン

このプロジェクトは2つの独立したツールを提供しています：

| バージョン | 用途 | UI | 対応ゲーム |
|-----------|------|----|----|
| **デスクトップアプリ版**<br>`mobile_movie_cut/` | エンドユーザー向け<br>GUI操作 | ブラウザ風UI<br>（PyWebView） | HADO（通常）<br>HADO WORLD |
| **CLI版**<br>`hado_match_extractor.py` | スクリプト組み込み<br>バッチ処理<br>サーバー環境 | コマンドライン | HADO（通常）のみ |

### プロジェクト構造

```
hado-match-extractor/
├── mobile_movie_cut/             # デスクトップアプリ版
│   ├── main.py                   # アプリエントリーポイント
│   ├── app.py                    # FastAPI サーバー
│   ├── extractor.py              # 基底クラス（共通処理）
│   ├── hado_detector.py          # HADO（通常）検出器
│   ├── hadoworld_detector.py     # HADO WORLD検出器
│   ├── build_app.sh              # macOSアプリビルド
│   ├── build_app_win.bat         # Windowsアプリビルド
│   ├── release_mac.sh            # macOSリリースZIP作成
│   ├── release_win.bat           # WindowsリリースZIP作成
│   ├── static/                   # フロントエンド（JS/CSS）
│   └── templates/                # HTML テンプレート
├── hado_match_extractor.py       # CLI版スクリプト（PIL使用）
├── requirements.txt              # CLI版依存パッケージ
└── README.md                     # このファイル
```

### 処理性能

デスクトップアプリ版はOpenCV直接読み込み + numpy高速化により、**CLI版の約10倍高速**です。

| 処理 | CLI版（PIL） | デスクトップ版（OpenCV） |
|------|------------|----------------------|
| HADO（通常） | 約300秒 | **約35秒**（88%削減） |
| HADO WORLD | - | 約40秒 |

---

## 開発者向け

### デスクトップアプリのビルド

#### macOS

```bash
cd mobile_movie_cut
bash build_app.sh
```

`HADO Match Extractor.app` が生成されます。

#### Windows

```cmd
cd mobile_movie_cut
build_app_win.bat
```

`dist\HADO Match Extractor\HADO Match Extractor.exe` が生成されます。

### リリース作成

```bash
# macOS
bash mobile_movie_cut/release_mac.sh 1.0.0

# Windows
cd mobile_movie_cut
release_win.bat 1.0.0

# GitHub Release 作成
gh release create v1.0.0 \
  releases/HADO-Match-Extractor-v1.0.0-macOS.zip \
  releases/HADO-Match-Extractor-v1.0.0-Windows.zip \
  --title "v1.0.0" --notes "初回リリース"
```

### ffmpeg バイナリ

ビルド前に `mobile_movie_cut/ffmpeg/` にバイナリを配置してください。詳細は `mobile_movie_cut/ffmpeg/README.md` を参照。

---

## CLI版

> **注意**: CLI版はHADO（通常）のみ対応。HADO WORLDはデスクトップアプリ版を使用してください。

### セットアップ

```bash
# 前提: Python 3.7+, FFmpeg がインストール済み
pip3 install -r requirements.txt
```

### 使い方

```bash
# 試合を個別動画として抽出
python3 hado_match_extractor.py /path/to/動画.MOV

# 全試合を1本の動画にまとめる
python3 hado_match_extractor.py /path/to/動画.MOV --merge

# 出力先を指定
python3 hado_match_extractor.py /path/to/動画.MOV -o ./output --merge
```

### オプション一覧

- `-o, --output DIR` - 出力ディレクトリ（デフォルト: カレントディレクトリ）
- `-t, --temp DIR` - 一時ファイルのディレクトリ
- `--no-cleanup` - 一時ファイルを削除しない
- `--merge` - 全試合を1本の動画に結合
- `--preset PRESET` - FFmpegエンコードプリセット（ultrafast/fast/medium/slow）

### Claude Codeスキルとして使う場合

```
/extract-hado-matches video=/path/to/動画.MOV
/extract-hado-matches video=/path/to/動画.MOV merge=true
```

---

## ライセンス

MIT License
