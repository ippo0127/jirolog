#!/usr/bin/env python3
"""data/stores.json の形式チェック。build.py からも呼ばれる。

    python3 scripts/validate.py
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun", "holiday"]
STATUSES = {"open", "temporarily_closed", "closed", "upcoming"}
TIME = re.compile(r"^([01]\d|2\d|3[0-5]):[0-5]\d$")
REQUIRED = ["id", "name", "prefecture", "address", "status", "hours"]


def minutes(t):
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def check_stores(stores):
    problems = []
    seen = set()
    for i, s in enumerate(stores):
        sid = s.get("id") or f"#{i}"
        for k in REQUIRED:
            if s.get(k) in (None, "") and not (k == "address" and s.get("status") == "upcoming"):
                problems.append(f"{sid}: {k} がない")
        if sid in seen:
            problems.append(f"{sid}: id が重複")
        seen.add(sid)
        if not re.match(r"^[a-z0-9_-]+$", sid):
            problems.append(f"{sid}: id は半角英小文字・数字・_・- のみ")
        if s.get("status") not in STATUSES:
            problems.append(f"{sid}: status が不正 ({s.get('status')})")
        hours = s.get("hours") or {}
        for d in hours:
            if d not in DAYS:
                problems.append(f"{sid}: hours に不明なキー {d}")
        for d in DAYS:
            ranges = hours.get(d)
            if ranges is None:
                continue
            prev_end = -1
            for r in ranges:
                if not (isinstance(r, list) and len(r) == 2 and all(isinstance(t, str) and TIME.match(t) for t in r)):
                    problems.append(f"{sid}: hours.{d} の形式が不正 {r}")
                    continue
                a, b = minutes(r[0]), minutes(r[1])
                if b <= a or a < prev_end:
                    problems.append(f"{sid}: hours.{d} の時間が逆順・重複 {r}")
                prev_end = b
        for key in ("x", "instagram", "web"):
            url = (s.get("sns") or {}).get(key)
            if url and not url.startswith("https://"):
                problems.append(f"{sid}: sns.{key} は https:// で始める")
        for key in ("features", "rules", "hours_notes"):
            for item in s.get(key) or []:
                if isinstance(item, dict) and not (item.get("text") and item.get("until")):
                    problems.append(f"{sid}: {key} の期間限定項目は text と until が必要")
        for src in s.get("sources") or []:
            if not (src.get("url") or "").startswith("http"):
                problems.append(f"{sid}: sources に URL のないものがある")
    return problems


def main():
    stores = json.loads((ROOT / "data" / "stores.json").read_text(encoding="utf-8"))
    problems = check_stores(stores)
    for p in problems:
        print(p)
    print(f"{len(stores)} stores, {len(problems)} problems")
    raise SystemExit(1 if problems else 0)


if __name__ == "__main__":
    main()
