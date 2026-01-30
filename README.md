# alfred-gdfid-finder

GoogleドライブのファイルIDからFinderでファイルを表示するAlfred Workflow。

## 概要

このワークフローでは以下のことができます:

- GoogleドライブのファイルID文字列を選択
- ローカルのGoogle Drive for Desktopから該当ファイルを検索
- Finderでファイルを表示

## 必要条件

- macOS
- [Alfred](https://www.alfredapp.com/) + Powerpack
- [Google Drive for Desktop](https://www.google.com/drive/download/)
- Python 3.9+（macOS標準の `/usr/bin/python3` で動作）

## インストール

### ユーザー向け

リリースから `.alfredworkflow` ファイルをダウンロードし、ダブルクリックでインストール。

### 開発者向け

```bash
# リポジトリをクローン
git clone https://github.com/hirshim/alfred-gdfid-finder.git
cd alfred-gdfid-finder

# 依存関係をインストール
uv sync --dev

# テスト実行
uv run pytest

# リンター実行
uv run ruff check src/ tests/

# 型チェック
uv run mypy src/
```

## 使い方

### Alfred Workflow

1. GoogleドライブのファイルIDをコピー（例: `1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms`）
2. 設定したホットキーでAlfred Workflowを起動
3. Finderでファイルが表示される

### コマンドライン

```bash
# インストール済みパッケージから実行
gdfid-finder <file_id>

# uvから実行
uv run gdfid-finder <file_id>

# 直接実行
python -m gdfid_finder.main <file_id>
```

## 仕組み

Google Drive for Desktopがファイルに設定する拡張属性（xattr）を利用:

1. **検索パス**: `~/Library/CloudStorage/GoogleDrive-*/` ディレクトリを走査
2. **ファイルID検出**: `ctypes` 経由で macOS `getxattr()` を直接呼び出し、`com.google.drivefs.item-id#S` 拡張属性を高速に読み取り
3. **優先検索**: 「マイドライブ」/「My Drive」ディレクトリを先に検索して高速化
4. **Finder表示**: `open -R` コマンドでFinderにファイルを表示

## プロジェクト構成

```text
alfred-gdfid-finder/
├── src/gdfid_finder/     # メインパッケージ
│   ├── main.py           # CLIエントリーポイント
│   ├── finder.py         # ファイル検索ロジック
│   └── utils.py          # ユーティリティ関数
├── tests/                # テストファイル
├── workflow/             # Alfred Workflow用ファイル
└── pyproject.toml        # プロジェクト設定
```

## 開発

```bash
# コードフォーマット
uv run ruff format src/ tests/

# 全チェック実行
uv run ruff check src/ tests/ && uv run mypy src/ && uv run pytest
```

## ライセンス

MIT
