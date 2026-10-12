#!/usr/bin/env python3
"""シェア用の画像（1200×630）とホーム画面用のアイコンを、手元の Google Chrome で作る。

    python3 scripts/make_og.py            # 足りない画像だけ作る
    python3 scripts/make_og.py --force    # 全部作り直す

出力は static/og/（サイト全体用 site.png・各店 stores/<id>.png）と static/icon-*.png。
画像は店名など変わりにくい内容だけなので、店が増えたときに実行して、できた画像をコミットする。
（Cloudflare Pages のビルドでは Chrome が使えないため、ビルド時には作らない）
"""
import html
import json
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
FONTS = '<link href="https://fonts.googleapis.com/css2?family=Dela+Gothic+One&family=Noto+Sans+JP:wght@700;900&display=block" rel="stylesheet">'

BASE_CSS = """
* { box-sizing: border-box; margin: 0; }
html, body { width: %(w)dpx; height: %(h)dpx; overflow: hidden; }
body { background: #ffd400; color: #161513; font-family: "Noto Sans JP", sans-serif; font-weight: 900; }
.frame { position: absolute; inset: 22px; border: 10px solid #161513; border-radius: 28px; box-shadow: 14px 14px 0 #d40011; background: #ffd400; }
.brand { position: absolute; left: 56px; top: 44px; font-family: "Dela Gothic One"; font-size: 46px; }
.brand em { font-style: normal; color: #d40011; }
.url { position: absolute; right: 60px; bottom: 50px; font-size: 26px; letter-spacing: .02em; }
"""


def esc(s):
    return html.escape(s or "", quote=True)


def shoot(markup, out, w, h):
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        src = pathlib.Path(tmp) / "card.html"
        src.write_text(f"<!doctype html><meta charset=utf-8>{FONTS}<style>{BASE_CSS % {'w': w, 'h': h}}</style>{markup}", encoding="utf-8")
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                        f"--window-size={w},{h}", "--virtual-time-budget=8000", f"--screenshot={out}", src.as_uri()],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)


def site_card(lang):
    if lang == "ja":
        title, sub, en = "二郎ログ", "直系ラーメン二郎 全店の<br>営業時間・いま営業中の店", "Jiro Log — Ramen Jiro hours & what's open now"
    else:
        title, sub, en = "Jiro Log", "Every official Ramen Jiro shop:<br>hours & what's open now", "二郎ログ — 直系ラーメン二郎の情報サイト"
    return f"""<div class="frame"></div>
<div style="position:absolute;left:90px;top:120px;font-family:'Dela Gothic One';font-size:150px;line-height:1">
  {'<span style="color:#d40011">二郎</span>ログ' if lang == 'ja' else 'Jiro <span style="color:#d40011">Log</span>'}</div>
<div style="position:absolute;left:96px;top:320px;font-size:50px;line-height:1.35">{sub}</div>
<div style="position:absolute;left:96px;bottom:56px;font-size:26px;font-weight:700">{esc(en)}</div>
<div class="url" style="bottom:56px">jirolog.pages.dev</div>"""


def store_card(name_ja, name_en, alias):
    # 看板を1行に収める（「ラーメン」は0.55倍の大きさで4文字、「二郎」2文字、間あき、枠の内側の余白を差し引く）
    size = min(112, int(948 / (4.2 + len(name_ja))))
    alias_html = f'<div style="font-size:40px;margin-top:18px">{esc(alias)}</div>' if alias else ""
    return f"""<div class="frame"></div>
<div class="brand"><em>二郎</em>ログ</div>
<div style="position:absolute;left:80px;right:80px;top:150px">
  <div style="display:inline-block;white-space:nowrap;border:9px solid #161513;border-radius:18px;padding:6px 34px 14px;box-shadow:10px 10px 0 #d40011;background:#fff6c2">
    <span style="font-family:'Dela Gothic One';font-size:{int(size*0.55)}px;color:#d40011">ラーメン</span><span style="font-family:'Dela Gothic One';font-size:{size}px">二郎</span><span style="font-family:'Dela Gothic One';font-size:{size}px;margin-left:24px">{esc(name_ja)}</span>
  </div>
  {alias_html}
  <div style="font-size:36px;margin-top:14px">営業時間・定休日・メニュー</div>
</div>
<div style="position:absolute;left:84px;bottom:52px;font-size:28px;font-weight:700">{esc(name_en)}</div>
<div class="url">jirolog.pages.dev</div>"""


def icon(size):
    return f"""<div style="position:absolute;inset:0;background:#ffd400"></div>
<div style="position:absolute;inset:{size*0.06}px;border:{max(3, int(size*0.05))}px solid #161513;border-radius:{size*0.16}px"></div>
<div style="position:absolute;inset:0;display:grid;place-items:center;font-family:'Dela Gothic One';font-size:{int(size*0.42)}px;line-height:1">
  <div style="text-align:center"><span>二郎</span><div style="font-size:{int(size*0.2)}px;color:#d40011;margin-top:{size*0.03}px">ログ</div></div></div>"""


def main():
    force = "--force" in sys.argv
    stores = json.loads((ROOT / "data" / "stores.json").read_text(encoding="utf-8"))
    en = (json.loads((ROOT / "data" / "en.json").read_text(encoding="utf-8")).get("stores") or {})
    jobs = [(STATIC / "og" / "site.png", site_card("ja"), 1200, 630),
            (STATIC / "og" / "site-en.png", site_card("en"), 1200, 630),
            (STATIC / "icon-512.png", icon(512), 512, 512)]
    for s in stores:
        if s.get("status") not in ("open", "temporarily_closed", "upcoming"):
            continue
        short = re.sub(r"^ラーメン二郎\s*", "", s["name"])
        nick = s.get("nickname") or ""
        alias = nick if (nick.endswith("二郎") or re.fullmatch(r"[ァ-ヶー]+", nick)) else (nick + "二郎" if nick else "")
        name_en = (en.get(s["id"]) or {}).get("name") or ""
        jobs.append((STATIC / "og" / "stores" / f"{s['id']}.png", store_card(short, name_en, f"通称 {alias}" if alias else ""), 1200, 630))
    made = 0
    for out, markup, w, h in jobs:
        if out.exists() and not force:
            continue
        shoot(markup, out, w, h)
        made += 1
        print("  made", out.relative_to(ROOT))
    # 小さいアイコンは 512 から縮めて作る（Chrome は小さすぎる画面幅では崩れるため）
    for size, name in ((192, "icon-192.png"), (180, "apple-touch-icon.png")):
        out = STATIC / name
        if force or not out.exists():
            subprocess.run(["sips", "-z", str(size), str(size), str(STATIC / "icon-512.png"), "--out", str(out)],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            made += 1
            print("  made", out.relative_to(ROOT))
    print(f"{made} images made, {len(jobs) + 2} total")


if __name__ == "__main__":
    main()
