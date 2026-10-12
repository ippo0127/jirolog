#!/usr/bin/env python3
"""IndexNow（Bing・Yandex・Naver など）に、更新したページを知らせる。Google は対象外（Google は sitemap と Search Console）。

    python3 scripts/indexnow.py          # 公開中の sitemap.xml のうち、8日以内に更新されたページを送る
    python3 scripts/indexnow.py --all    # 全ページを送る（最初の1回や大きな変更のあと）

公開中のサイトの sitemap.xml を読むので、デプロイが終わってから実行する。
確認用ファイル（<key>.txt）は build.py がサイトの根に書き出している。
"""
import datetime as dt
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def main():
    site = json.loads((ROOT / "data" / "site.json").read_text(encoding="utf-8"))
    key, base = site.get("indexnow_key"), (site.get("base_url") or "").rstrip("/")
    if not key or not base:
        sys.exit("data/site.json に indexnow_key と base_url が必要")
    host = urllib.parse.urlparse(base).netloc

    # Python の既定の User-Agent は Cloudflare にはじかれるので名乗る
    req = urllib.request.Request(f"{base}/sitemap.xml", headers={"User-Agent": "jirolog-indexnow/1.0 (+https://jirolog.pages.dev/)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        root = ET.fromstring(r.read())
    since = dt.date.today() - dt.timedelta(days=8)
    urls = []
    for u in root.findall("s:url", NS):
        loc = u.findtext("s:loc", namespaces=NS)
        mod = u.findtext("s:lastmod", namespaces=NS)
        if "--all" in sys.argv or not mod or dt.date.fromisoformat(mod[:10]) >= since:
            urls.append(loc)
    if not urls:
        print("送るページなし")
        return

    body = json.dumps({"host": host, "key": key, "keyLocation": f"{base}/{key}.txt", "urlList": urls[:10000]}).encode()
    req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body,
                                 headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "jirolog-indexnow/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"{len(urls)} pages submitted: HTTP {r.status}")
    except urllib.error.HTTPError as ex:
        sys.exit(f"IndexNow error: HTTP {ex.code} {ex.read()[:200]!r}")


if __name__ == "__main__":
    main()
