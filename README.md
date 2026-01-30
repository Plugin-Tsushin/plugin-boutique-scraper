# Plugin Boutique Scraper

Plugin BoutiqueのDTMプラグインセール情報を自動取得するスクレイピングツール。

## 機能

- Plugin Boutiqueのセールページから商品情報を取得
- 最大50件の商品情報をCSV形式で出力
- アフィリエイトID付きURLを自動生成
- GitHub Actionsによる毎日の自動実行

## 出力データ

`output/plugin_data.csv` に以下の情報を出力:

| カラム | 説明 |
|--------|------|
| プラグイン名 | 商品名 |
| セール価格 | 現在の販売価格 |
| 定価 | 通常価格 |
| セール率 | 割引率（例: 50% OFF） |
| 終了日 | セール終了日 |
| 商品URL | アフィリエイトID付きURL |

## セットアップ

### 1. リポジトリの準備

```bash
# GitHubでリポジトリを作成後
git clone https://github.com/YOUR_USERNAME/plugin-boutique-scraper.git
cd plugin-boutique-scraper
```

### 2. ローカル環境でのテスト

```bash
# Python仮想環境を作成（推奨）
python -m venv venv

# 仮想環境を有効化
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

# 依存関係をインストール
pip install -r requirements.txt

# Playwrightのブラウザをインストール
playwright install chromium

# スクリプトを実行
python scrape_plugin_boutique.py
```

### 3. GitHub Actionsの設定

1. リポジトリをGitHubにプッシュ
2. リポジトリの Settings > Actions > General で以下を確認:
   - Actions permissions: "Allow all actions and reusable workflows"
   - Workflow permissions: "Read and write permissions" を選択

```bash
# 初回プッシュ
git add .
git commit -m "Initial commit"
git push -u origin main
```

## 自動実行スケジュール

- **実行時間**: 毎日 UTC 0:00（日本時間 9:00）
- **トリガー**:
  - スケジュール実行（cron）
  - 手動実行（workflow_dispatch）
  - main ブランチへのプッシュ時

### 手動実行

1. GitHubリポジトリの「Actions」タブを開く
2. 「Scrape Plugin Boutique Deals」ワークフローを選択
3. 「Run workflow」ボタンをクリック

## ディレクトリ構成

```
plugin-boutique-scraper/
├── .github/
│   └── workflows/
│       └── scrape.yml      # GitHub Actionsワークフロー
├── output/
│   └── plugin_data.csv     # 出力ファイル（自動生成）
├── scrape_plugin_boutique.py  # メインスクリプト
├── requirements.txt        # 依存関係
└── README.md
```

## カスタマイズ

### アフィリエイトIDの変更

`scrape_plugin_boutique.py` 内の以下の行を編集:

```python
AFFILIATE_ID = "688228cd487ff"  # ここを変更
```

### 取得件数の変更

```python
MAX_ITEMS = 50  # ここを変更
```

### 実行時間の変更

`.github/workflows/scrape.yml` 内の cron 式を編集:

```yaml
schedule:
  - cron: '0 0 * * *'  # UTC 0:00 = JST 9:00
```

cron式の形式: `分 時 日 月 曜日`

例:
- `'0 1 * * *'` - UTC 1:00（JST 10:00）
- `'30 23 * * *'` - UTC 23:30（JST 翌8:30）

## トラブルシューティング

### GitHub Actionsが失敗する場合

1. **Playwright関連エラー**
   - ブラウザのインストールが正しく行われているか確認
   - ワークフローログで詳細なエラーメッセージを確認

2. **コミット権限エラー**
   - Settings > Actions > General で "Read and write permissions" が有効か確認

3. **スクレイピングがタイムアウト**
   - サイト側の変更やアクセス制限の可能性
   - 時間をおいて再実行

### ローカル実行でエラーが出る場合

1. **Playwrightブラウザが見つからない**
   ```bash
   playwright install chromium
   ```

2. **依存関係のエラー**
   ```bash
   pip install --upgrade -r requirements.txt
   ```

## 注意事項

- 過度なアクセスは避けてください
- サイトの利用規約を遵守してください
- スクレイピング対象サイトの構造が変更された場合、セレクタの調整が必要な場合があります

## ライセンス

個人利用目的
