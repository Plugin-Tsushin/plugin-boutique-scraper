#!/usr/bin/env python3
"""
Plugin Boutique セール情報スクレイピングスクリプト

Plugin Boutiqueのセールページから商品情報を取得し、CSVファイルに出力します。
"""

import csv
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


# 設定
BASE_URL = "https://www.pluginboutique.com"
DEALS_URL = f"{BASE_URL}/deals"
AFFILIATE_ID = "688228cd487ff"
MAX_ITEMS = 50
OUTPUT_DIR = Path("output")
OUTPUT_FILE = OUTPUT_DIR / "plugin_data.csv"

# スクレイピング設定
REQUEST_TIMEOUT = 60000  # 60秒
WAIT_FOR_SELECTOR_TIMEOUT = 30000  # 30秒


def create_affiliate_url(product_url: str) -> str:
    """商品URLにアフィリエイトIDを付与"""
    if not product_url:
        return ""

    # 相対URLを絶対URLに変換
    if product_url.startswith("/"):
        product_url = urljoin(BASE_URL, product_url)

    # アフィリエイトパラメータを追加
    separator = "&" if "?" in product_url else "?"
    return f"{product_url}{separator}a_aid={AFFILIATE_ID}"


def clean_price(price_text: str) -> str:
    """価格テキストをクリーンアップ"""
    if not price_text:
        return ""
    # 余分な空白を削除
    return price_text.strip()


def clean_text(text: str) -> str:
    """テキストをクリーンアップ"""
    if not text:
        return ""
    # 余分な空白・改行を削除
    return " ".join(text.split()).strip()


def scrape_deals() -> list[dict]:
    """Plugin Boutiqueのセール情報をスクレイピング"""
    products = []

    with sync_playwright() as p:
        # ブラウザを起動（ヘッドレスモード）
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="ja-JP"
        )

        page = context.new_page()

        try:
            print(f"ページを読み込み中: {DEALS_URL}")
            page.goto(DEALS_URL, timeout=REQUEST_TIMEOUT, wait_until="networkidle")

            # 商品カードが読み込まれるまで待機
            # 複数のセレクタを試行
            selectors_to_try = [
                "a[href*='/product/']",
                "[data-testid='product-card']",
                ".product-card",
                "[class*='ProductCard']"
            ]

            loaded = False
            for selector in selectors_to_try:
                try:
                    page.wait_for_selector(selector, timeout=WAIT_FOR_SELECTOR_TIMEOUT)
                    print(f"セレクタ '{selector}' で要素を検出")
                    loaded = True
                    break
                except PlaywrightTimeout:
                    continue

            if not loaded:
                print("警告: 商品カードの読み込みを待機中にタイムアウト")
                # それでも続行を試みる
                time.sleep(5)

            # ページ全体をスクロールして遅延読み込みコンテンツを取得（50件以上読み込む）
            print("ページをスクロール中...")
            for i in range(10):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1.5)
                # 現在の商品数をチェック
                current_count = len(page.query_selector_all("a[href*='/product/']"))
                print(f"  スクロール {i+1}/10: {current_count} 件検出")
                if current_count >= 100:  # 十分な数が読み込まれたら終了
                    break
            page.evaluate("window.scrollTo(0, 0)")
            time.sleep(1)

            # 商品リンクを取得
            product_links = page.query_selector_all("a[href*='/product/']")
            print(f"商品リンクを {len(product_links)} 件検出")

            seen_urls = set()

            for link in product_links:
                # フィルタリング前に多めに取得するため、制限を緩める
                if len(products) >= MAX_ITEMS * 3:
                    break

                try:
                    href = link.get_attribute("href")
                    if not href or href in seen_urls:
                        continue

                    # /product/ を含むURLのみ処理
                    if "/product/" not in href:
                        continue

                    seen_urls.add(href)

                    # 親要素（商品カード）を探す
                    # 複数の階層を遡って商品情報を含む要素を探す
                    card = link
                    for _ in range(5):
                        parent = card.evaluate_handle("el => el.parentElement")
                        if parent:
                            card = parent.as_element()
                            if card is None:
                                break
                            # カードらしき要素かチェック
                            class_name = card.get_attribute("class") or ""
                            if any(keyword in class_name.lower() for keyword in ["card", "product", "item", "deal"]):
                                break
                        else:
                            break

                    # テキストコンテンツを取得
                    card_text = card.inner_text() if card else link.inner_text()

                    # 商品情報を抽出
                    product_data = extract_product_info(card_text, href)

                    if product_data.get("plugin_name"):
                        products.append(product_data)
                        print(f"  取得: {product_data['plugin_name']}")

                except Exception as e:
                    print(f"  商品情報の取得中にエラー: {e}")
                    continue

        except PlaywrightTimeout as e:
            print(f"タイムアウトエラー: {e}")
            raise
        except Exception as e:
            print(f"スクレイピング中にエラー: {e}")
            raise
        finally:
            browser.close()

    return products


def extract_name_from_url(href: str) -> str:
    """URLから製品名を抽出"""
    # /product/カテゴリ/サブカテゴリ/ID-製品名 の形式
    match = re.search(r'/product/[^/]+/[^/]+/\d+-(.+?)(?:\?|$)', href)
    if match:
        name = match.group(1)
        # ハイフンをスペースに変換し、タイトルケースに
        name = name.replace('-', ' ')
        return name
    return ""


def extract_product_info(text: str, href: str) -> dict:
    """テキストから商品情報を抽出"""
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    product_data = {
        "plugin_name": "",
        "sale_price": "",
        "original_price": "",
        "discount_rate": "",
        "end_date": "",
        "product_url": create_affiliate_url(href)
    }

    # URLから製品名を抽出（最も信頼性が高い）
    product_data["plugin_name"] = extract_name_from_url(href)

    # テキストからも製品名を探す（URLから取れない場合のフォールバック）
    if not product_data["plugin_name"]:
        skip_words = {"hot!", "free", "new", "sale", "off", "ends", "best seller"}
        for line in lines:
            line_lower = line.lower()
            # 価格やセール情報でない行を探す
            if not re.match(r'^[\$\€\£\¥]', line) and "%" not in line:
                if len(line) > 2 and line_lower not in skip_words:
                    product_data["plugin_name"] = clean_text(line)
                    break

    # 価格情報を探す - 全行をまとめて処理
    all_text = " ".join(lines)

    # 全ての価格を抽出
    all_prices = re.findall(r'[\$\€\£\¥][\d,]+(?:\.\d{2})?', all_text)
    if all_prices:
        # 価格を数値に変換してソート
        price_values = []
        for p in all_prices:
            try:
                val = float(re.sub(r'[^\d.]', '', p.replace(",", "")))
                price_values.append((val, p))
            except ValueError:
                continue

        if len(price_values) >= 2:
            # ソートして最大と最小を取得
            price_values.sort(key=lambda x: x[0], reverse=True)
            product_data["original_price"] = price_values[0][1]  # 最大 = 定価
            product_data["sale_price"] = price_values[-1][1]     # 最小 = セール価格
        elif len(price_values) == 1:
            product_data["sale_price"] = price_values[0][1]

    # 割引率
    discount_match = re.search(r'(\d+)%?\s*off', all_text, re.IGNORECASE)
    if discount_match:
        product_data["discount_rate"] = f"{discount_match.group(1)}% OFF"
    else:
        # "XX%" のパターンも探す
        percent_match = re.search(r'(\d+)%', all_text)
        if percent_match:
            product_data["discount_rate"] = f"{percent_match.group(1)}% OFF"

    # 終了日
    end_match = re.search(r'[Ee]nd[s]?\s+(\d{1,2}\s+\w{3}(?:\s+\d{4})?)', all_text)
    if end_match:
        product_data["end_date"] = end_match.group(1)

    return product_data


def save_to_csv(products: list[dict], output_file: Path) -> None:
    """商品情報をCSVファイルに保存"""
    # 出力ディレクトリを作成
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # CSVヘッダー
    fieldnames = [
        "プラグイン名",
        "セール価格",
        "定価",
        "セール率",
        "終了日",
        "商品URL"
    ]

    # CSVに書き込み
    with open(output_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for product in products:
            writer.writerow({
                "プラグイン名": product.get("plugin_name", ""),
                "セール価格": product.get("sale_price", ""),
                "定価": product.get("original_price", ""),
                "セール率": product.get("discount_rate", ""),
                "終了日": product.get("end_date", ""),
                "商品URL": product.get("product_url", "")
            })

    print(f"\nCSVファイルを保存しました: {output_file}")


def main():
    """メイン処理"""
    print("=" * 60)
    print("Plugin Boutique セール情報スクレイピング")
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    try:
        # スクレイピング実行
        products = scrape_deals()

        if not products:
            print("\n警告: 商品情報を取得できませんでした")
            # 空のCSVを作成（GitHub Actionsでのエラー防止）
            save_to_csv([], OUTPUT_FILE)
            return 1

        # 重複を排除（商品URLベース）
        seen_urls = set()
        unique_products = []
        for product in products:
            url = product.get("product_url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_products.append(product)

        print(f"\n取得件数: {len(unique_products)} 件（重複排除後）")

        # セール品のみフィルタリング（セール率と定価が両方あるもの）
        sale_products = [
            p for p in unique_products
            if p.get("discount_rate") and p.get("original_price")
        ]
        print(f"セール品: {len(sale_products)} 件（フィルタリング後）")

        # CSVに保存
        save_to_csv(sale_products[:MAX_ITEMS], OUTPUT_FILE)

        print("\n処理が完了しました")
        return 0

    except Exception as e:
        print(f"\nエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
