#!/usr/bin/env python3
"""内閣府の祝日CSVを取得して data/holidays.json に保存する。

    python3 scripts/fetch_holidays.py
"""
import csv
import io
import json
import pathlib
import urllib.request

URL = "https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv"
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "holidays.json"
FROM_YEAR = 2024


def main():
    raw = urllib.request.urlopen(URL, timeout=30).read().decode("shift_jis")
    holidays = {}
    for row in list(csv.reader(io.StringIO(raw)))[1:]:
        if len(row) < 2:
            continue
        y, m, d = (int(x) for x in row[0].split("/"))
        if y >= FROM_YEAR:
            holidays[f"{y:04d}-{m:02d}-{d:02d}"] = row[1]
    OUT.write_text(json.dumps(holidays, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(holidays)} holidays -> {OUT}")


if __name__ == "__main__":
    main()
