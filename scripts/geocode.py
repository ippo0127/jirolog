#!/usr/bin/env python3
"""店舗住所を国土地理院のジオコーダで緯度経度に変換し data/geo.json に保存する。

住所が変わった店・未取得の店だけ問い合わせる。手で直した座標は "manual": true を付けると上書きしない。

    python3 scripts/geocode.py
"""
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
STORES = ROOT / "data" / "stores.json"
GEO = ROOT / "data" / "geo.json"
API = "https://msearch.gsi.go.jp/address-search/AddressSearch?q="


def clean(address):
    # ビル名・階数は検索の邪魔になるので落とす
    a = re.sub(r"[\s　].*$", "", address.strip())
    return a.translate(str.maketrans("０１２３４５６７８９－ー−", "0123456789---"))


def lookup(address):
    with urllib.request.urlopen(API + urllib.parse.quote(clean(address)), timeout=20) as r:
        hits = json.load(r)
    if not hits:
        return None
    lng, lat = hits[0]["geometry"]["coordinates"]
    return {"lat": round(lat, 6), "lng": round(lng, 6), "matched": hits[0]["properties"]["title"]}


def main():
    stores = json.loads(STORES.read_text(encoding="utf-8"))
    geo = json.loads(GEO.read_text(encoding="utf-8")) if GEO.exists() else {}
    changed = 0
    for s in stores:
        addr = s.get("address")
        cur = geo.get(s["id"])
        if not addr or (cur and (cur.get("manual") or cur.get("address") == addr)):
            continue
        hit = lookup(addr)
        if hit is None:
            print(f"  not found: {s['id']} {addr}")
            continue
        geo[s["id"]] = {"address": addr, **hit}
        changed += 1
        print(f"  {s['id']}: {hit['matched']} ({hit['lat']}, {hit['lng']})")
        time.sleep(0.3)
    GEO.write_text(json.dumps(geo, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{changed} updated, {len(geo)} total -> {GEO}")


if __name__ == "__main__":
    main()
