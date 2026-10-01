#!/usr/bin/env python3
"""ラーメンシーンと直系二郎大好きマン（YouTube）の新着を公式フィード（RSS/Atom）から取り込み、data/feeds.json に保存する。

    python3 scripts/fetch_feeds.py

- 取得に失敗したフィードは前回の内容を残す（YouTube のフィードはときどき一時的に 404 を返す）
- タイトルに店名・通称が入っていれば store_ids に店の id を付ける
- 記事や動画の本文は保存しない（タイトル・URL・日付だけ）
"""
import datetime as dt
import json
import pathlib
import re
import time
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "feeds.json"
STORES = ROOT / "data" / "stores.json"
SITE = ROOT / "data" / "site.json"
JST = dt.timezone(dt.timedelta(hours=9))
KEEP = 60  # フィードごとに残す件数
UA = "Mozilla/5.0 (compatible; jirolog-feed/1.0; +https://github.com/)"

FEEDS = {
    "ramenscene": "https://ramen-scene.com/category/jiro/feed",
    "youtube": "https://www.youtube.com/feeds/videos.xml?channel_id=UCnblzHDvdCnrvx2hgaq8bpw",
}
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as ex:  # noqa: BLE001
            last = ex
            time.sleep(2 * (i + 1))
    raise last


def matcher():
    """タイトルから店を探す。長い名前から順に当てる。通称は「二郎」を含むタイトルでだけ使う。"""
    stores = json.loads(STORES.read_text(encoding="utf-8"))
    names, nicks = [], []
    for s in stores:
        short = re.sub(r"^ラーメン二郎\s*", "", s["name"]).replace(" ", "")
        names += [(short, s["id"]), (short.rstrip("店"), s["id"])]
        if s.get("nickname") and len(s["nickname"]) >= 2:
            nicks.append((s["nickname"], s["id"]))
    names.sort(key=lambda x: -len(x[0]))
    nicks.sort(key=lambda x: -len(x[0]))

    def find(title):
        t = re.sub(r"[\s　]", "", title)
        found = []
        for key, sid in names:
            if len(key) >= 2 and key in t and sid not in found:
                found.append(sid)
                t = t.replace(key, "")
        if not found and "二郎" in t:
            for key, sid in nicks:
                if key in t and sid not in found:
                    found.append(sid)
                    t = t.replace(key, "")
        return found
    return find


def parse_rss(xml, find):
    items = []
    for it in ET.fromstring(xml).iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = it.findtext("pubDate")
        date = None
        if pub:
            try:
                date = dt.datetime.strptime(pub.strip(), "%a, %d %b %Y %H:%M:%S %z").astimezone(JST).date().isoformat()
            except ValueError:
                pass
        if link:
            items.append({"url": link, "title": title, "date": date, "store_ids": find(title)})
    return items


def parse_atom(xml, find):
    items = []
    for en in ET.fromstring(xml).findall("a:entry", NS):
        title = (en.findtext("a:title", default="", namespaces=NS)).strip()
        vid = en.findtext("yt:videoId", default="", namespaces=NS)
        pub = en.findtext("a:published", default="", namespaces=NS)
        date = None
        if pub:
            try:
                date = dt.datetime.fromisoformat(pub.replace("Z", "+00:00")).astimezone(JST).date().isoformat()
            except ValueError:
                pass
        if vid:
            items.append({"url": f"https://www.youtube.com/watch?v={vid}", "title": title, "date": date, "store_ids": find(title)})
    return items


def main():
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    find = matcher()
    # 二郎の店にとって悪い話題のタイトルは取り込まない（data/site.json の feed_exclude）
    exclude = json.loads(SITE.read_text(encoding="utf-8")).get("feed_exclude") or []
    ok = lambda it: not any(w in it["title"] for w in exclude)
    out = {"fetched": dt.datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")}
    for key, url in FEEDS.items():
        prev = old.get(key, [])
        try:
            raw = get(url)
            fresh = parse_rss(raw, find) if key == "ramenscene" else parse_atom(raw, find)
            print(f"  {key}: {len(fresh)} items")
        except Exception as ex:  # noqa: BLE001
            print(f"  {key}: 取得失敗（前回の {len(prev)} 件を残す）: {ex}")
            fresh = []
        seen, merged = set(), []
        for it in fresh + prev:
            if it["url"] not in seen and ok(it):
                seen.add(it["url"])
                merged.append(it)
        merged.sort(key=lambda x: x.get("date") or "", reverse=True)
        out[key] = merged[:KEEP]
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
