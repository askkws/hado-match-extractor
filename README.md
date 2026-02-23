# Hado Match Extractor

波動の試合動画から個別の試合クリップを自動抽出するツールです。

## 機能

- スタッツ画面を画像解析で自動検出
- 各試合のクリップ範囲を自動計算
- 個別の試合動画を抽出
- 全試合を1本の動画に結合（オプション）

## セットアップ手順（初めての方向け）

### 1. 前提条件の確認

以下がインストールされている必要があります：

| ツール | 確認コマンド | 用途 |
|--------|-------------|------|
| Python 3.7+ | `python3 --version` | スクリプト実行 |
| pip | `pip3 --version` | Pythonパッケージ管理 |
| FFmpeg | `ffmpeg -version` | 動画の処理・エンコード |
| Homebrew | `brew --version` | macOSパッケージ管理（FFmpegインストール用） |

### 2. Homebrewのインストール（未インストールの場合）

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 3. FFmpegのインストール（未インストールの場合）

```bash
brew install ffmpeg
```

### 4. Pythonパッケージのインストール

```bash
cd /Users/kawase/Work/Work/SIde_Work/dev/movie_cut
pip3 install -r requirements.txt
```

### 5. 動作確認

```bash
python3 hado_match_extractor.py --help
```

ヘルプが表示されれば準備完了です。

### 6. 実行

動画ファイルをこのディレクトリにコピーするか、パスを指定して実行：

```bash
# 試合を個別動画として抽出
python3 hado_match_extractor.py /path/to/動画.MOV

# 全試合を1本の動画にまとめる
python3 hado_match_extractor.py /path/to/動画.MOV --merge

# 出力先を指定して1本にまとめる
python3 hado_match_extractor.py /path/to/動画.MOV -o ./output --merge
```

### Claude Codeスキルとして使う場合

Claude Codeがインストールされている環境では、以下のコマンドでも実行できます：

```
/extract-hado-matches video=/path/to/動画.MOV
/extract-hado-matches video=/path/to/動画.MOV merge=true
/extract-hado-matches video=/path/to/動画.MOV output=./output merge=true preset=fast
```

### 処理時間の目安

| 動画の長さ | フレーム抽出 | 検出 | 動画抽出 | 合計 |
|-----------|------------|------|---------|------|
| 1時間 | 約1分 | 約2分 | 約10分 | 約13分 |
| 2時間 | 約2分 | 約4分 | 約20分 | 約26分 |

※ `--preset ultrafast`（デフォルト）の場合。`--preset medium` はさらに時間がかかります。

---

## 使い方

### 基本的な使い方

```bash
python hado_match_extractor.py video.MOV
```

これで以下が生成されます：
- `match_01.mp4`, `match_02.mp4`, ... - 個別の試合動画
- `clips_data.json` - 各試合のタイムスタンプ情報

### オプション

```bash
# 出力ディレクトリを指定
python hado_match_extractor.py video.MOV -o ./output

# 全試合を1本の動画に結合
python hado_match_extractor.py video.MOV --merge

# 高品質でエンコード（処理時間が長くなります）
python hado_match_extractor.py video.MOV --preset medium

# 一時ファイルを残す（デバッグ用）
python hado_match_extractor.py video.MOV --no-cleanup

# すべてのオプションを組み合わせ
python hado_match_extractor.py video.MOV -o ./output --merge --preset fast
```

### オプション一覧

- `-o, --output DIR` - 出力ディレクトリ（デフォルト: カレントディレクトリ）
- `-t, --temp DIR` - 一時ファイルのディレクトリ（デフォルト: /tmp/hado_extraction）
- `--no-cleanup` - 一時ファイルを削除しない
- `--merge` - 全試合を1本の動画に結合（`all_matches_combined.mp4`）
- `--preset PRESET` - FFmpegエンコードプリセット
  - `ultrafast` - 最速（デフォルト、ファイルサイズ大）
  - `fast` - 高速
  - `medium` - バランス
  - `slow` - 高品質（処理時間長）

## 処理の流れ

1. **フレーム抽出** - 動画から0.5fps（2秒に1フレーム）で画像を抽出
2. **スタッツ画面検出** - 赤・オレンジ・シアンの色分布で試合開始画面を検出
3. **スコア表示検出** - 左右に赤/青が分かれた画面を検出して試合終了を判定
4. **クリップ範囲計算** - スタッツ開始〜スコア表示終了の区間を計算
5. **動画抽出** - FFmpegで各試合の動画を個別に抽出
6. **結合（オプション）** - 全試合を1本の動画にマージ

## 検出アルゴリズム

### スタッツ画面（試合開始）
以下の色パターンで検出：
- **赤**: R>150, G<120, B<120
- **オレンジ**: R>180, 100<G<180, B<100
- **シアン**: R<120, G>150, B>150
- **閾値**: 上記の色のピクセルが15%以上で検出

### スコア表示画面（試合終了）
以下の特徴で検出：
- **左半分**: 赤ピクセル > 10%（R > 120, R > G + 30）
- **右半分**: 青ピクセル > 10%（B > 120, B > R + 30）
- **左右差**: 6%以内（左右のバランスが取れている）
- 試合開始80秒後から検索開始
- スコア表示検出後、**2.5秒後にカット**（HADOロゴが出る前）

## 出力ファイル

- `match_01.mp4` 〜 `match_XX.mp4` - 個別の試合動画（各約2分）
- `clips_data.json` - タイムスタンプとメタデータ
- `all_matches_combined.mp4` - 全試合結合動画（`--merge`使用時）

## トラブルシューティング

### スタッツ画面が検出されない

検出閾値を調整してください。スクリプトの以下の部分を編集：

```python
self.combined_threshold = 15.0  # 値を下げると検出しやすくなる（例: 10.0）
```

### 処理が遅い

- `--preset ultrafast` を使用（デフォルト）
- 一時ディレクトリを高速なディスク（SSD）に変更: `-t /path/to/fast/disk`

### メモリ不足

フレーム抽出のfpsを下げてください（スクリプト内の`extract_frames`メソッドの`fps=0.5`を`fps=0.25`など）

## ライセンス

MIT License

## 作成履歴

- 2026-02-17: 初版作成（スタッツ画面検出 + 固定120秒カット）
- 2026-02-17: v1.1 スコア表示検出を追加（スタッツ〜スコア表示+2.5秒の正確なカット）
