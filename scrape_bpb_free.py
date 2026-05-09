#!/usr/bin/env python3
"""
Bedroom Producers Blog (BPB) FREE プラグイン情報スクレイピングスクリプト

BPBのRSSフィードから "Free Software" カテゴリの記事を取得し、
履歴と最新差分をCSVファイルに出力します。
"""

import csv
import html
import re
from datetime import datetime, timezone
from pathlib import Path

import feedparser

# 設定
FEED_URL = "https://bedroomproducersblog.com/feed/"
FREE_CATEGORY = "Free Software"
LIMITED_KEYWORDS = ["limited time", "limited-time", "for a limited", "限定"]

OUTPUT_DIR = Path("output")
HISTORY_FILE = OUTPUT_DIR / "free_bpb_history.csv"
LATEST_FILE = OUTPUT_DIR / "free_bpb_latest.csv"

# CSVカラム
FIELDNAMES = [
    "プラグイン名",
    "配布元",
    "種別",
    "公開日",
    "記事URL",
    "サムネイルURL",
    "概要",
    "取得日時",
]


def extract_thumbnail(summary: str) -> str:
    """summary HTMLから最初のimg srcを抽出"""
    if not summary:
        return ""
    match = re.search(r'<img[^>]+src="([^"]+)"', summary)
    return match.group(1) if match else ""


def extract_excerpt(summary: str, max_len: int = 200) -> str:
    """summary HTMLからプレーンテキストの抜粋を生成"""
    if not summary:
        return ""
    text = re.sub(r"<[^>]+>", "", summary)
    text = html.unescape(text)
    text = " ".join(text.split())
    if len(text) > max_len:
        text = text[:max_len] + "..."
    return text


def extract_plugin_name(title: str) -> str:
    """
    記事タイトルからプラグイン名を抽出
    例: "Goodhertz releases LA-210, a FREE compressor..." -> "LA-210"
    例: "Pulsar Audio Smasher is FREE for a limited time again" -> "Pulsar Audio Smasher"
    """
    if not title:
        return ""

    # パターン1: "[Maker] releases [Plugin], ..." or "[Maker] releases [Plugin] for ..."
    m = re.match(
        r"^[^,]+?\s+releases?\s+(.+?)(?:,|\s+for\s+|$)",
        title,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()

    # パターン2: "[Plugin] is a FREE ..." -> "[Plugin]"
    m = re.match(r"^(.+?)\s+is\s+a\s+FREE", title, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # パターン3: "[Plugin] is FREE ..." -> "[Plugin]"
    m = re.match(r"^(.+?)\s+is\s+FREE", title, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # パターン4: "[Plugin] FREE plugin ..." (Mannix Squared FREE plugin bundle...)
    m = re.match(r"^(.+?)\s+FREE\s+", title)
    if m:
        return m.group(1).strip()

    # フォールバック: タイトル先頭60字
    return title.strip()[:60]


def extract_maker(title: str) -> str:
    """
    記事タイトルから配布元（メーカー名）を抽出
    例: "Goodhertz releases LA-210, ..." -> "Goodhertz"
    """
    if not title:
        return ""

    # パターン1: "[Maker] releases ..."
    m = re.match(r"^(.+?)\s+releases?\s+", title, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # パターン2: "From developer [Maker] comes [Plugin]..."
    m = re.match(r"^From\s+developer\s+(.+?)\s+comes", title, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # それ以外は空（誤判定を避ける）
    return ""


def determine_type(title: str, summary: str) -> str:
    """
    "FREE"（常時無料）か "LIMITED"（期間限定無料）かを判定
    """
    text = f"{title} {summary}".lower()
    for kw in LIMITED_KEYWORDS:
        if kw in text:
            return "LIMITED"
    return "FREE"


def parse_pub_date(published: str) -> str:
    """RFC822形式の日付をYYYY-MM-DDに変換"""
    if not published:
        return ""
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(published)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return published


def fetch_free_entries() -> list[dict]:
    """RSSを取得し、Free Softwareカテゴリの記事を抽出"""
    print(f"Fetching feed: {FEED_URL}")
    feed = feedparser.parse(FEED_URL)

    if feed.bozo:
        print(f"WARN: Feed parse warning: {feed.bozo_exception}")

    print(f"  Total entries: {len(feed.entries)}")

    free_entries = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for entry in feed.entries:
        # Free Softwareカテゴリチェック
        tags = [t.term for t in entry.get("tags", [])]
        if FREE_CATEGORY not in tags:
            continue

        title = entry.get("title", "")
        summary = entry.get("summary", "")
        link = entry.get("link", "")

        record = {
            "プラグイン名": extract_plugin_name(title),
            "配布元": extract_maker(title),
            "種別": determine_type(title, summary),
            "公開日": parse_pub_date(entry.get("published", "")),
            "記事URL": link,
            "サムネイルURL": extract_thumbnail(summary),
            "概要": extract_excerpt(summary),
            "取得日時": now_iso,
        }
        free_entries.append(record)

    print(f"  Free Software entries: {len(free_entries)}")
    return free_entries


def load_history() -> tuple[list[dict], set[str]]:
    """既存の履歴CSVを読み込み、URLセットを返す"""
    if not HISTORY_FILE.exists():
        return [], set()

    with open(HISTORY_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        records = list(reader)

    urls = {r.get("記事URL", "") for r in records if r.get("記事URL")}
    return records, urls


def save_csv(records: list[dict], path: Path) -> None:
    """レコードをCSVに保存"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for r in records:
            writer.writerow({k: r.get(k, "") for k in FIELDNAMES})
    print(f"Saved: {path} ({len(records)} rows)")


def main() -> int:
    print("=" * 60)
    print("BPB FREE Plugin Scraper")
    print(f"Run at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    try:
        # 1. RSSから現在のFREE記事を取得
        current_entries = fetch_free_entries()

        if not current_entries:
            print("\nWARN: No FREE entries found. Saving empty latest CSV.")
            save_csv([], LATEST_FILE)
            return 0

        # 2. 履歴CSVを読み込み（既存URLセット）
        history_records, known_urls = load_history()
        print(f"\nHistory: {len(history_records)} existing records")

        # 3. 新規分（既存履歴にないURL）を抽出
        new_entries = [
            r for r in current_entries
            if r["記事URL"] and r["記事URL"] not in known_urls
        ]
        print(f"New entries: {len(new_entries)}")

        # 4. latest CSVに今回取得分の新規分を保存（差分用）
        save_csv(new_entries, LATEST_FILE)

        # 5. 履歴に新規分を追加して保存（公開日降順）
        merged = history_records + new_entries
        merged.sort(key=lambda r: r.get("公開日", ""), reverse=True)
        save_csv(merged, HISTORY_FILE)

        print("\nDone.")
        return 0

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
