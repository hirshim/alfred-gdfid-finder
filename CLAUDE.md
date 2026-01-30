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
│       ├── finder.py     # ファイル検索ロジック（xattr走査）
│       ├── db_finder.py  # DB検索ロジック（SQLite）
│       └── utils.py      # ユーティリティ関数
├── tests/                # テストコード
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
# 固定サイズバッファで1回の getxattr 呼び出し（サイズ問い合わせ不要）
_xattr_buf = ctypes.create_string_buffer(256)
size = _libc.getxattr(path_bytes, attr_bytes, _xattr_buf, 256, 0, 0)
file_id = _xattr_buf.raw[:size].decode("utf-8")  # .value ではなく .raw[:size] を使用
```

パフォーマンス最適化:

- `ctypes` で `getxattr()` を直接呼び出し（`subprocess` より約100倍高速）
- 固定サイズバッファの再利用でシステムコールを2→1回に削減
- `.raw[:size]` でバッファ再利用時の古いデータ混入を防止（`.value` は null バイトまで読むため不可）
- `os.scandir()` でディレクトリ走査（`DirEntry` が `readdir` の `d_type` をキャッシュし `stat()` 不要）
- `path.resolve()` はシンボリックリンクの場合のみ実行

検索順序:

1. **DB検索（高速パス）**: DriveFS内部SQLiteデータベース（`~/Library/Application Support/Google/DriveFS/<account>/metadata_sqlite_db`）から再帰CTEでパスを復元（~0.5ms）
2. **xattr走査（フォールバック）**: DB検索失敗時、`~/Library/CloudStorage/GoogleDrive-*/` 配下を走査
3. 優先ディレクトリ（マイドライブ, My Drive, 共有ドライブ, Shared drives）を先に検索
4. 隠しファイル（`.`で始まるもの）はスキップ
5. イテレーティブ探索（スタック使用）でスタックオーバーフローを回避
6. 解決済みパスのセットでシンボリックリンクループを検出

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
