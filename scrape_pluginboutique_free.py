#!/usr/bin/env python3
"""
Plugin Boutique 永続Free プラグイン情報スクレイピングスクリプト

Plugin Boutiqueの ?free=true&sort=published フィルタページから永続無料プラグイン情報を取得し、
履歴と最新差分をCSVファイルに出力します。

取得対象：
- Effects (?free=true)
- Instruments (?free=true)
- Studio Tools (?free=true)
- Free Bundles (カテゴリ141)
"""

import csv
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# 設定
BASE_URL = "https://www.pluginboutique.com"
AFFILIATE_ID = "688228cd487ff"

# 取得対象カテゴリページ（公開日新しい順で取得）
TARGET_URLS = [
    f"{BASE_URL}/categories/2-Effects?free=true&sort=published",
    f"{BASE_URL}/categories/1-Instruments?free=true&sort=published",
    f"{BASE_URL}/categories/3-Studio-Tools?free=true&sort=published",
    f"{BASE_URL}/categories/141-Free-Bundles?sort=published",
]

# 出力
OUTPUT_DIR = Path("output")
HISTORY_FILE = OUTPUT_DIR / "free_pluginboutique_history.csv"
LATEST_FILE = OUTPUT_DIR / "free_pluginboutique_latest.csv"

# CSVカラム
FIELDNAMES = [
    "プラグイン名",
    "配布元",
    "カテゴリ",
    "種別",
    "商品URL",
    "サムネイルURL",
    "評価",
    "取得日時",
]

# スクレイピング設定
REQUEST_TIMEOUT = 60000
PAGE_WAIT_TIME = 2.5
SCROLL_ITERATIONS = 5


def create_affiliate_url(product_url: str) -> str:
    """商品URLにアフィリエイトIDを付与"""
    if not product_url:
        return ""
    if product_url.startswith("/"):
        product_url = urljoin(BASE_URL, product_url)
    separator = "&" if "?" in product_url else "?"
    return f"{product_url}{separator}a_aid={AFFILIATE_ID}"


def parse_tile_text(text: str) -> dict:
    """
    タイル内のテキストから情報を抽出
    典型的な構造:
        Free
        プラグイン名
        カテゴリ
        by
        配布元
        FREE
        評価値
    """
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    result = {
        "name": "",
        "category": "",
        "maker": "",
        "rating": "",
        "is_free": False,
    }

    if not lines:
        return result

    # FREEバッジ確認
    if any(line.upper() == "FREE" for line in lines):
        result["is_free"] = True

    # "by" の位置を探す
    by_idx = None
    for i, line in enumerate(lines):
        if line.lower() == "by":
            by_idx = i
            break

    if by_idx is not None:
        if by_idx >= 2:
            name_idx = by_idx - 2
            cat_idx = by_idx - 1
            result["name"] = lines[name_idx]
            result["category"] = lines[cat_idx]
        if by_idx + 1 < len(lines):
            result["maker"] = lines[by_idx + 1]

    # 評価値（数字.数字 形式の最後の出現）
    for line in reversed(lines):
        if re.match(r"^\d+\.\d+$", line):
            result["rating"] = line
            break

    return result


def scrape_category(page, url: str, seen_urls: set) -> list[dict]:
    """単一カテゴリページから永続Freeプラグインを取得"""
    products = []
    print(f"\nページを読み込み中: {url}")

    try:
        page.goto(url, timeout=REQUEST_TIMEOUT, wait_until="networkidle")
        time.sleep(2)

        # スクロールで遅延読み込みを促す
        for _ in range(SCROLL_ITERATIONS):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1.2)
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(0.5)

        # メイングリッド内のタイルだけ取得（おすすめ枠は除外）
        tiles = page.query_selector_all(
            "#search-results-list div[id^='product-tile-']"
        )
        print(f"  タイル数: {len(tiles)}")

        now_iso = datetime.now(timezone.utc).isoformat()

        for tile in tiles:
            try:
                link = tile.query_selector("a[href*='/product/']")
                if not link:
                    continue
                href = link.get_attribute("href")
                if not href or "/product/" not in href:
                    continue
                if href in seen_urls:
                    continue
                seen_urls.add(href)

                text = tile.inner_text()
                parsed = parse_tile_text(text)

                # FREEバッジが無いものはスキップ（保険）
                if not parsed["is_free"]:
                    continue

                img = tile.query_selector("img")
                img_src = img.get_attribute("src") if img else ""

                product = {
                    "プラグイン名": parsed["name"],
                    "配布元": parsed["maker"],
                    "カテゴリ": parsed["category"],
                    "種別": "FREE",
                    "商品URL": create_affiliate_url(href),
                    "サムネイルURL": img_src or "",
                    "評価": parsed["rating"],
                    "取得日時": now_iso,
                }
                products.append(product)

            except Exception as e:
                print(f"  タイル処理エラー: {e}")
                continue

        print(f"  取得: {len(products)} 件（重複除外後）")

    except PlaywrightTimeout as e:
        print(f"  タイムアウト: {e}")
    except Exception as e:
        print(f"  エラー: {e}")

    return products


def scrape_all() -> list[dict]:
    """全カテゴリをスクレイピング"""
    all_products = []
    seen_urls = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="ja-JP",
        )
        page = context.new_page()

        try:
            for i, url in enumerate(TARGET_URLS):
                if i > 0:
                    print(f"\n--- 待機中 ({PAGE_WAIT_TIME}秒) ---")
                    time.sleep(PAGE_WAIT_TIME)
                print(f"\n[{i+1}/{len(TARGET_URLS)}] カテゴリ処理中...")
                products = scrape_category(page, url, seen_urls)
                all_products.extend(products)
                print(f"  累計: {len(all_products)} 件")
        finally:
            browser.close()

    return all_products


def load_history() -> tuple[list[dict], set[str]]:
    """既存履歴CSVを読み込み、URLセットを返す"""
    if not HISTORY_FILE.exists():
        return [], set()
    with open(HISTORY_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        records = list(reader)
    urls = {r.get("商品URL", "") for r in records if r.get("商品URL")}
    return records, urls


def save_csv(records: list[dict], path: Path) -> None:
    """レコードをCSVに保存"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for r in records:
            writer.writerow({k: r.get(k, "") for k in FIELDNAMES})
    print(f"保存: {path} ({len(records)} 件)")


def main() -> int:
    print("=" * 60)
    print("Plugin Boutique 永続Free プラグインスクレイパー")
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    try:
        # 1. スクレイピング
        current = scrape_all()
        print(f"\n{'='*60}")
        print(f"全カテゴリ取得完了: {len(current)} 件")

        if not current:
            print("警告: 商品情報を取得できませんでした")
            save_csv([], LATEST_FILE)
            return 0

        # 2. 履歴読み込み
        history_records, known_urls = load_history()
        print(f"既存履歴: {len(history_records)} 件")

        # 3. 履歴未登録分を抽出（公開日順なので新着を優先で発見）
        new_entries = [
            r for r in current
            if r["商品URL"] and r["商品URL"] not in known_urls
        ]
        print(f"履歴未登録: {len(new_entries)} 件（新着または初回未取得分）")

        # 4. latest CSV（履歴未登録分のみ）
        save_csv(new_entries, LATEST_FILE)

        # 5. history CSV（累積、最新の取得日時で既存レコードも更新）
        merged_map = {r["商品URL"]: r for r in history_records}
        for r in current:
            merged_map[r["商品URL"]] = r
        merged = list(merged_map.values())
        merged.sort(key=lambda r: (r.get("配布元", ""), r.get("プラグイン名", "")))
        save_csv(merged, HISTORY_FILE)

        print("\n完了")
        return 0

    except Exception as e:
        print(f"\nエラー: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
