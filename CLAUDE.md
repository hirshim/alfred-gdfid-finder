# alfred-gdfid-finder プロジェクトガイド

## プロジェクト概要

- **名前**: alfred-gdfid-finder
- **種類**: Alfred Workflow用のPythonスクリプト
- **目的**:
  - 選択した文字列をGoogleドライブのファイルIDとして解釈し、Finder上で該当するファイルを選択状態にする
  - Obsidian上にあるGoogleドライブのファイルデータベースから、該当するファイルに簡単にアクセスする

## 技術スタック

| 項目 | 技術 |
|------|------|
| Workflow | Alfred Workflow |
| 言語 | Python 3.9+（macOS標準 `/usr/bin/python3` 対応） |
| パッケージ管理 | uv |
| テスト | pytest |
| リンター | ruff |
| 型チェック | mypy |

## コーディング規約

- **docstring**: Google style
- **型ヒント**: 必須（全ての関数・メソッドに付与）
- **Python 3.9互換**: `typing`モジュールを使用（`List`, `Optional`, `Dict`等）
- **テストカバレッジ**: 80%以上を目標
- **インポート順序**: 標準ライブラリ → サードパーティ → ローカル（ruffで自動整列）

## ディレクトリ構成

```text
alfred-gdfid-finder/
├── src/
│   └── gdfid_finder/     # メインパッケージ
│       ├── __init__.py
│       ├── main.py       # エントリーポイント
│       ├── finder.py     # ファイル検索ロジック
│       └── utils.py      # ユーティリティ関数
├── tests/                # テストコード
├── doc/                  # ドキュメント
├── workflow/             # Alfred Workflow用ファイル
├── pyproject.toml        # プロジェクト設定
├── CLAUDE.md             # このファイル
└── .cursorrules          # Cursor IDE設定
```

## 実装詳細

### ファイルID検索

Google Drive for Desktopは各ファイルに拡張属性（xattr）としてファイルIDを保存:

```bash
# ファイルIDの確認方法（手動確認用）
xattr -p "com.google.drivefs.item-id#S" /path/to/file
```

プログラムからは `ctypes` 経由で macOS の C ライブラリ `getxattr()` を直接呼び出す:

```python
# macOS getxattr(path, name, value, size, position, options)
size = _libc.getxattr(path_bytes, attr_bytes, None, 0, 0, 0)
buf = ctypes.create_string_buffer(size)
_libc.getxattr(path_bytes, attr_bytes, buf, size, 0, 0)
```

- `subprocess.run(["xattr", ...])` ではなく `ctypes` を使用（1ファイルあたり約100倍高速）
- 外部依存なし（`ctypes` は標準ライブラリ）

検索順序:

1. `~/Library/CloudStorage/GoogleDrive-*/` 配下を走査
2. 優先ディレクトリ（マイドライブ, My Drive, 共有ドライブ, Shared drives）を先に検索
3. 隠しファイル（`.`で始まるもの）はスキップ

### ファイル選択方法

macOSのFinderでファイルを選択するには `open -R` コマンドを使用:

```bash
open -R "/path/to/file"
```

※ AppleScriptではなく`open -R`を使用することで、パス名に特殊文字が含まれる場合のinjection脆弱性を回避

## 開発プロセス

### 基本ルール

1. レビュー（変更無し、Ultrathink）→ リファクタ → レビュー のサイクルを繰り返す
2. 開発ステップごとにプロジェクト全体のレビューを実施

### コマンド

```bash
# 依存関係インストール
uv sync

# テスト実行
uv run pytest

# リンター実行
uv run ruff check src/ tests/

# 型チェック
uv run mypy src/

# フォーマット
uv run ruff format src/ tests/
```

### Alfred Workflow

- 開発: リポジトリからシンボリックリンクで使用
- 配布: `.alfredworkflow`形式でエクスポート

## 関連ドキュメント

| ファイル | 役割 |
|----------|------|
| `project-bootstrap-prompt.md` | プロジェクトの初期設定要件 |
| `.cursorrules` | Cursor IDEの設定ファイル |

## ドキュメント管理ルール

- CLAUDE.md は 200 行以内を保つ
- 200 行を超える場合は `docs/CLAUDE-**.md` 形式で分割
