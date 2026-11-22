#!/usr/bin/env python3
"""data/stores.json と data/special_hours.json の形式チェック。build.py からも呼ばれる。

    python3 scripts/validate.py
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun", "holiday"]
STATUSES = {"open", "temporarily_closed", "closed", "upcoming"}
TIME = re.compile(r"^([01]\d|2\d|3[0-5]):[0-5]\d$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SEASON_KEYS = ["id", "name", "from", "to", "core_from", "core_to", "show_from", "show_to"]
REQUIRED = ["id", "name", "prefecture", "address", "status", "hours"]


def minutes(t):
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def check_ranges(where, ranges, problems):
    """[["11:00", "15:00"], ...] の形と、時間の順番を確かめる。"""
    prev_end = -1
    for r in ranges:
        if not (isinstance(r, list) and len(r) == 2 and all(isinstance(t, str) and TIME.match(t) for t in r)):
            problems.append(f"{where} の形式が不正 {r}")
            continue
        a, b = minutes(r[0]), minutes(r[1])
        if b <= a or a < prev_end:
            problems.append(f"{where} の時間が逆順・重複 {r}")
        prev_end = b


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
            if ranges is not None:
                check_ranges(f"{sid}: hours.{d}", ranges, problems)
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


def check_special(data, store_ids):
    """data/special_hours.json（年末年始などの特別営業）の形式チェック。"""
    problems = []
    for i, season in enumerate((data or {}).get("seasons") or []):
        sid = season.get("id") or f"season#{i}"
        for k in SEASON_KEYS:
            if not season.get(k):
                problems.append(f"{sid}: {k} がない")
            elif k != "id" and k != "name" and not DATE.match(season[k]):
                problems.append(f"{sid}: {k} は YYYY-MM-DD で書く")
        if season.get("from", "") > season.get("to", "") or season.get("core_from", "") > season.get("core_to", ""):
            problems.append(f"{sid}: 期間の始まりと終わりが逆")
        for store_id, ent in (season.get("stores") or {}).items():
            where = f"{sid}.{store_id}"
            if store_id not in store_ids:
                problems.append(f"{where}: 知らない店")
            for day, v in (ent.get("days") or {}).items():
                if not DATE.match(day):
                    problems.append(f"{where}: 日付 {day} は YYYY-MM-DD で書く")
                if v is None or v == "normal":
                    continue
                if isinstance(v, list):
                    check_ranges(f"{where}.{day}", v, problems)
                else:
                    problems.append(f"{where}.{day} は 時間の配列・[]（休み）・null（要確認）・\"normal\"（ふだんどおり）のどれか")
            if not ((ent.get("source") or {}).get("url") or "").startswith("http"):
                problems.append(f"{where}: source に URL がない")
    return problems


def main():
    stores = json.loads((ROOT / "data" / "stores.json").read_text(encoding="utf-8"))
    problems = check_stores(stores)
    special = ROOT / "data" / "special_hours.json"
    if special.exists():
        problems += check_special(json.loads(special.read_text(encoding="utf-8")), {s["id"] for s in stores})
    for p in problems:
        print(p)
    print(f"{len(stores)} stores, {len(problems)} problems")
    raise SystemExit(1 if problems else 0)


if __name__ == "__main__":
    main()
