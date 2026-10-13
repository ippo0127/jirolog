#!/usr/bin/env python3
"""二郎ログ 静的サイトジェネレータ（Python 標準ライブラリのみ）

    python3 scripts/build.py          # data/ と content/ -> dist/
    python3 -m http.server -d dist    # http://localhost:8000 で確認

日本語ページを dist/ に、英語ページを dist/en/ に、同じ構成で書き出す。
英語の文言は data/en.json（店舗・ニュース・系譜の翻訳）と content/en/（ガイドなど）から取り、
翻訳がない項目は日本語のまま表示する。
"""
import datetime as dt
import html
import json
import pathlib
import re
import shutil
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import validate  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
STATIC = ROOT / "static"
CONTENT = ROOT / "content"
DIST = ROOT / "dist"

LANG = "ja"   # 書き出し中の言語。main() が切り替える
TR = {}       # data/en.json


def L(ja, en):
    """書き出し中の言語の文言を返す。"""
    return en if LANG == "en" else ja


def e(s):
    return html.escape("" if s is None else str(s), quote=True)


def load(name, default=None):
    p = DATA / name
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- 地域・曜日

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun", "holiday"]
DAY_JA = {"mon": "月", "tue": "火", "wed": "水", "thu": "木", "fri": "金", "sat": "土", "sun": "日", "holiday": "祝"}
DAY_EN = {"mon": "Mon", "tue": "Tue", "wed": "Wed", "thu": "Thu", "fri": "Fri", "sat": "Sat", "sun": "Sun", "holiday": "Holidays"}

AREA_ORDER = ["北海道", "宮城県", "福島県", "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京23区", "東京多摩",
              "神奈川県", "新潟県", "長野県", "愛知県", "京都府", "福岡県", "沖縄県"]
AREA_EN = {"北海道": "Hokkaido", "宮城県": "Miyagi", "福島県": "Fukushima", "茨城県": "Ibaraki", "栃木県": "Tochigi",
           "群馬県": "Gunma", "埼玉県": "Saitama", "千葉県": "Chiba", "東京23区": "Tokyo (23 wards)", "東京多摩": "Tokyo (Tama)",
           "東京都": "Tokyo", "神奈川県": "Kanagawa", "新潟県": "Niigata", "長野県": "Nagano", "愛知県": "Aichi",
           "京都府": "Kyoto", "福岡県": "Fukuoka", "沖縄県": "Okinawa"}

STATUS_LABEL = {"open": ("営業", "Open"), "temporarily_closed": ("休業中", "Temporarily closed"),
                "closed": ("閉店", "Closed"), "upcoming": ("開店予定", "Coming soon")}
CLOSED_TYPE = {"close": ("閉店", "Closed"), "move": ("移転", "Moved"), "rename": ("店名変更", "Renamed")}
NEWS_TYPE = {"open": ("開店", "Opened"), "close": ("閉店", "Closed"), "move": ("移転", "Moved"),
             "pause": ("休業", "Paused"), "upcoming": ("予定", "Upcoming"), "resume": ("再開", "Reopened")}

# よくあるメニュー名の英訳（店ごとの訳が data/en.json にあればそちらが優先）
MENU_EN = {
    "小ラーメン": "Small ramen", "大ラーメン": "Large ramen", "小豚ラーメン": "Small ramen + extra pork",
    "大豚ラーメン": "Large ramen + extra pork", "小ぶたラーメン": "Small ramen + extra pork",
    "大ぶたラーメン": "Large ramen + extra pork", "小ブタラーメン": "Small ramen + extra pork",
    "大ブタラーメン": "Large ramen + extra pork", "ラーメン": "Ramen", "豚ラーメン": "Ramen + extra pork",
    "ぶたラーメン": "Ramen + extra pork", "汁なし": "Shiru-nashi (soupless)", "つけ麺": "Tsukemen (dipping noodles)",
    "生卵": "Raw egg", "生たまご": "Raw egg", "うずら": "Quail eggs", "味玉": "Seasoned egg", "紅生姜": "Pickled ginger",
}


def label(pair):
    return pair[1] if LANG == "en" else pair[0]


def area_of(store):
    """東京は23区と多摩で分ける。それ以外は都道府県名（日本語のキー）。"""
    pref = store.get("prefecture") or ""
    if pref == "東京都":
        rest = (store.get("address") or "")[3:]
        return "東京23区" if re.match(r"^[^市町村]{1,4}区", rest) else "東京多摩"
    return pref


def area_label(a):
    return AREA_EN.get(a, a) if LANG == "en" else a


def area_rank(a):
    return (AREA_ORDER.index(a) if a in AREA_ORDER else 99, a)


# ---------------------------------------------------------------- 店舗データの取り出し（言語別）

TODAY = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()


def expired(item):
    """{"text"/"name": ..., "until": "YYYY-MM-DD"} の until を過ぎたら True（期間限定の自動非表示）。"""
    until = item.get("until") if isinstance(item, dict) else None
    try:
        return bool(until) and dt.date.fromisoformat(until) < TODAY
    except ValueError:
        return False


def live_list(store, field):
    """features / rules / hours_notes を期限切れを除いて書き出し中の言語で返す（英訳は同じ順番で並んでいる）。"""
    ja = store.get(field) or []
    en = tr_store(store).get(field) or [] if LANG == "en" else []
    out = []
    for i, item in enumerate(ja):
        if expired(item):
            continue
        if LANG == "en" and i < len(en):
            t = en[i]
            out.append(t.get("text") if isinstance(t, dict) else t)
        else:
            out.append(item.get("text") if isinstance(item, dict) else item)
    return out


def live_menu(store):
    return [m for m in store.get("menu") or [] if m.get("name") and not expired(m)]


def tr_store(store):
    return (TR.get("stores") or {}).get(store["id"], {}) if LANG == "en" else {}


def sv(store, field):
    """店舗の項目を書き出し中の言語で返す。英訳がなければ日本語。"""
    v = tr_store(store).get(field)
    return v if v else store.get(field)


def short_name(store):
    if LANG == "en":
        t = tr_store(store)
        if t.get("short"):
            return t["short"]
        if t.get("name"):
            return re.sub(r"^Ramen Jiro\s*", "", t["name"])
    return re.sub(r"^ラーメン二郎\s*", "", store["name"])


def full_name(store):
    if LANG == "en":
        t = tr_store(store)
        return t.get("name") or f"Ramen Jiro {short_name(store)}"
    return store["name"]


def city_of(store):
    if LANG == "en":
        t = tr_store(store)
        if t.get("city"):
            return t["city"]
        return AREA_EN.get(store.get("prefecture"), store.get("prefecture") or "")
    m = re.match(r"^(東京都|北海道|(?:京都|大阪)府|.{2,3}県)(.+?[市区町村郡])", store.get("address") or "")
    return (m.group(1) + m.group(2)) if m else (store.get("address") or "")


def fmt_time(t):
    h, m = (int(x) for x in t.split(":"))
    if h >= 24:
        return L(f"翌{h - 24}:{m:02d}", f"{h - 24}:{m:02d} (+1)")
    return f"{h}:{m:02d}"


def fmt_ranges(ranges):
    if ranges is None:
        return L("要確認", "Check")
    if not ranges:
        return L("休み", "Closed")
    return " / ".join(f"{fmt_time(a)}{L('〜', '–')}{fmt_time(b)}" for a, b in ranges)


def closed_days(store):
    """定休日の表示。英語は翻訳がなければ営業時間データから組み立てる。"""
    if LANG == "ja":
        return store.get("closed_text") or "要確認"
    t = tr_store(store).get("closed_text")
    if t:
        return t
    hours = store.get("hours") or {}
    if not any(hours.get(k) for k in DAY_KEYS):
        return "Check"
    days = [DAY_EN[k] for k in DAY_KEYS[:7] if hours.get(k) == []]
    hol = hours.get("holiday")
    parts = [", ".join(days)] if days else []
    if hol == []:
        parts.append("public holidays")
    text = " & ".join(parts) if parts else "No regular closing day"
    if hol is None:
        text += " (holidays vary)"
    return text


def yen(price):
    if not isinstance(price, int):
        return e(price or "—")
    return f"¥{price:,}" if LANG == "en" else f"{price:,}円"


def menu_name(store, m):
    if LANG == "ja":
        return m["name"]
    t = (tr_store(store).get("menu") or {}).get(m["name"])
    return t or MENU_EN.get(m["name"]) or m["name"]


def menu_note(store, m):
    note = m.get("note")
    if LANG == "en":
        note = (tr_store(store).get("menu_notes") or {}).get(m["name"]) or (None if note else None)
    return f' <span class="muted small">{e(note)}</span>' if note else ""


def host_label(url):
    host = urllib.parse.urlparse(url).netloc.replace("www.", "")
    names = {"x.com": ("X", "X"), "twitter.com": ("X", "X"), "instagram.com": ("Instagram", "Instagram"),
             "youtube.com": ("YouTube", "YouTube"), "youtu.be": ("YouTube", "YouTube"),
             "ramen-scene.com": ("ラーメンシーン", "Ramen Scene"), "tabelog.com": ("食べログ", "Tabelog"),
             "ramendb.supleks.jp": ("ラーメンデータベース", "Ramen Database")}
    return label(names[host]) if host in names else host


def x_search_url(query):
    return "https://x.com/search?" + urllib.parse.urlencode({"q": query, "f": "live"})


def youtube_id(url):
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([\w-]{11})", url or "")
    return m.group(1) if m else None


def src_link(url):
    return f' <a class="muted small" href="{e(url)}" rel="noopener" target="_blank">{L("出典", "source")}</a>' if url else ""


def date_span(date):
    return f' <span class="date">{e(date)}</span>' if date else ""


def ja_mark():
    """英語ページで日本語のままの外部コンテンツに付ける印。"""
    return ' <span class="tag tag-ja">JA</span>' if LANG == "en" else ""


def ext(url, text, cls=""):
    c = f' class="{cls}"' if cls else ""
    return f'<a{c} href="{e(url)}" rel="noopener" target="_blank">{text}</a>'


# ---------------------------------------------------------------- layout

NAV = [
    ("index", "index.html", ("ホーム", "Home")),
    ("stores", "stores/index.html", ("店舗", "Shops")),
    ("map", "map.html", ("地図", "Map")),
    ("lineage", "lineage.html", ("系譜", "Lineage")),
    ("guide", "guide.html", ("はじめて", "How to order")),
    ("glossary", "glossary.html", ("用語集", "Glossary")),
    ("log", "log.html", ("マイログ", "My log")),
    ("news", "news.html", ("ニュース", "News")),
]

LEAFLET_CSS = ('<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" '
               'integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">')
LEAFLET_JS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
SRI = {LEAFLET_JS: "sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="}


def pretty(path):
    """Cloudflare Pages の URL の形（index.html と .html を付けない）。"""
    return re.sub(r"\.html$", "", re.sub(r"(^|/)index\.html$", r"\1", path))


class Page:
    """1ページ分の書き出し先と、そこからの相対パス。"""

    def __init__(self, path):
        self.path = path                                   # 言語内のパス（例: stores/mita.html）
        depth = path.count("/")
        self.p = "../" * depth                             # 同じ言語のトップへ
        self.a = "../" * (depth + (1 if LANG == "en" else 0))  # dist/ のトップへ（assets はここ）
        self.out = path if LANG == "ja" else "en/" + path
        self.other = self.a + ("en/" + path if LANG == "ja" else path)


def page_url(site, pg):
    return site["base_url"].rstrip("/") + "/" + pretty(pg.out) if site.get("base_url") else ""


def social_meta(site, pg, full_title, desc, og_image):
    """シェアしたときのカード（X・LINE・Facebook など）。"""
    if not site.get("base_url"):
        return ""
    img = site["base_url"].rstrip("/") + "/" + (og_image or L("assets/og/site.png", "assets/og/site-en.png"))
    return (f'<meta property="og:image" content="{e(img)}"><meta property="og:image:width" content="1200">'
            f'<meta property="og:image:height" content="630"><meta property="og:image:alt" content="{e(full_title)}">'
            f'<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{e(full_title)}">'
            f'<meta name="twitter:description" content="{e(desc)}"><meta name="twitter:image" content="{e(img)}">')


def share_bar(site, pg, full_title):
    url = page_url(site, pg)
    if not url:
        return ""
    q = urllib.parse.urlencode
    x = "https://x.com/intent/post?" + q({"text": full_title, "url": url, "hashtags": L("ラーメン二郎", "RamenJiro")})
    line = "https://social-plugins.line.me/lineit/share?" + q({"url": url})
    return f"""<aside class="share-bar" data-share data-url="{e(url)}" data-title="{e(full_title)}" aria-label="{L('このページをシェア', 'Share this page')}">
  <span class="share-label">{L('このページをシェア', 'Share this page')}</span>
  <button class="btn btn-small" type="button" data-share-native hidden>{L('共有…', 'Share…')}</button>
  <a class="btn btn-small" href="{e(x)}" target="_blank" rel="noopener">{L('X でポスト', 'Post on X')}</a>
  <a class="btn btn-small" href="{e(line)}" target="_blank" rel="noopener">{L('LINE で送る', 'Send on LINE')}</a>
  <button class="btn btn-small" type="button" data-copy-url>{L('URL をコピー', 'Copy link')}</button>
</aside>"""


def layout(site, pg, *, title, body, page="", description="", scripts=(), head_extra="", ad=False, ja_only=False, og_image=None, share=True, noindex=False):
    """ad: 本文の下に広告枠を置く（日本語ページだけ）。ja_only: 英語版のないページ。"""
    p, a = pg.p, pg.a
    other = pg.a + "en/index.html" if ja_only else pg.other
    name = L(site["name"], site.get("name_en", site["name"]))
    if page == "index":
        full_title = L(f"{name}｜直系ラーメン二郎 全店の営業時間・いま営業中の店", f"{name} | Ramen Jiro hours and what's open now")
    else:
        full_title = f"{title}｜{name}" if LANG == "ja" else f"{title} | {name}"
    desc = description or L(site["description"], site.get("description_en", site["description"]))
    nav = "".join(f'<a href="{p}{href}"{" aria-current=page" if key == page else ""}>{e(label(lab))}</a>'
                  for key, href, lab in NAV)
    script_tags = "".join(
        f'<script src="{s}" integrity="{SRI[s]}" crossorigin="" defer></script>' if s.startswith("http")
        else f'<script src="{a}{s}" defer></script>' for s in scripts)
    head_links = ""
    if site.get("base_url"):
        base = site["base_url"].rstrip("/") + "/"
        head_links = (f'<meta property="og:url" content="{e(base + pretty(pg.out))}">'
                      f'<link rel="canonical" href="{e(base + pretty(pg.out))}">'
                      + ("" if ja_only else
                         f'<link rel="alternate" hreflang="ja" href="{e(base + pretty(pg.path))}">'
                         f'<link rel="alternate" hreflang="en" href="{e(base + pretty("en/" + pg.path))}">'
                         f'<link rel="alternate" hreflang="x-default" href="{e(base + pretty(pg.path))}">'))
    other_lang = (f'<a class="lang-switch" href="{e(other)}" hreflang="en" lang="en">EN</a>' if LANG == "ja"
                  else f'<a class="lang-switch" href="{e(other)}" hreflang="ja" lang="ja">日本語</a>')
    # 広告は日本語ページだけ（英語ページには載せない）
    client = site.get("adsense_client") if LANG == "ja" else ""
    ad_script = (f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={e(client)}" crossorigin="anonymous"></script>'
                 if client else "")
    ad_unit = (f'<aside class="ad-slot" aria-label="広告"><p class="ad-label">広告</p>'
               f'<ins class="adsbygoogle" style="display:block" data-ad-client="{e(client)}" data-ad-slot="{e(site["adsense_slot"])}" '
               f'data-ad-format="auto" data-full-width-responsive="true"></ins>'
               f'<script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script></aside>'
               if client and ad and site.get("adsense_slot") else "")
    return f"""<!doctype html>
<html lang="{LANG}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{'<meta name="robots" content="noindex">' if noindex else ''}
<title>{e(full_title)}</title>
<meta name="description" content="{e(desc)}">
<meta property="og:title" content="{e(full_title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{e(name)}">
<meta property="og:locale" content="{L('ja_JP', 'en_US')}">
<meta name="theme-color" content="#ffd400">
{f'<meta name="google-site-verification" content="{e(site["google_site_verification"])}">' if site.get("google_site_verification") else ""}
{head_links}
{social_meta(site, pg, full_title, desc, og_image)}
<link rel="icon" href="{a}assets/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="{a}assets/apple-touch-icon.png">
<link rel="manifest" href="{a}assets/manifest.webmanifest">
<meta name="apple-mobile-web-app-title" content="{e(name)}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Dela+Gothic+One&family=Noto+Sans+JP:wght@400;500;700;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{a}assets/style.css">
{head_extra}
{ad_script}
<script src="{a}assets/data.js" defer></script>
<script src="{a}assets/app.js" defer></script>
{script_tags}
</head>
<body data-root="{p}" data-assets="{a}"{f' data-views="{e(site["views_endpoint"])}"' if site.get("views_endpoint") else ""}{f' data-api="{e(site["api_base"])}"' if site.get("api_base") else ""}>
<a class="skip" href="#main">{L('本文へ', 'Skip to content')}</a>
<header class="site-head">
  <div class="wrap head-row">
    <a class="brand" href="{p}index.html" aria-label="{e(name)} {L('ホーム', 'home')}"><span class="brand-sign"><em>二郎</em>ログ</span><span class="brand-sub">{L('直系ラーメン二郎 情報', 'Jiro Log · Ramen Jiro guide')}</span></a>
    <nav class="site-nav" aria-label="{L('メイン', 'Main')}">{nav}</nav>
    {other_lang}
  </div>
</header>
<main id="main" class="wrap">
{body}
{ad_unit}
{share_bar(site, pg, full_title) if share else ""}
</main>
<footer class="site-foot">
  <div class="wrap">
    <p>{L(f'<strong>{e(name)}</strong> は直系ラーメン二郎の非公式ファンサイトです。ラーメン二郎各店とは関係ありません。',
           f'<strong>{e(name)}</strong> is an unofficial fan site about the Ramen Jiro shops. It is not affiliated with Ramen Jiro.')}</p>
    <p>{L('営業時間・価格は変わります。お出かけ前に各店の公式アカウントを確認してください。', 'Hours and prices change often. Check each shop’s official account before you go.')} {L('データ更新', 'Data updated')}: {e(site['_updated'])}</p>
    <p class="views" data-views-line hidden>{L('あなたは <b data-visits>–</b> 人目の閲覧者です', 'You are visitor No. <b data-visits>–</b>')}</p>
    <p><a href="{p}report.html?page={e(urllib.parse.quote(pg.out))}">{L('誤りを報告', 'Report a mistake')}</a> · <a href="{p}about.html">{L('このサイトについて・情報源', 'About & sources')}</a> · <a href="{p}stores/closed.html">{L('閉店・移転した店', 'Closed shops')}</a> · <a href="{p}news.html">{L('ニュース', 'News')}</a>{L(f' · <a href="{p}privacy.html">プライバシーポリシー</a>', '')} · <a href="{e(other)}">{L('English', '日本語')}</a></p>
  </div>
</footer>
</body>
</html>
"""


# ---------------------------------------------------------------- 部品

def week_table(store):
    hours = store.get("hours") or {}
    closed = store.get("status") == "closed"
    if closed and not any(hours.get(k) for k in DAY_KEYS):
        return f'<p class="muted">{L("当時の営業時間の記録はありません", "No record of the former hours")}</p>'
    rows = []
    for k in DAY_KEYS:
        r = hours.get(k)
        cls = "off" if r == [] else ("unk" if r is None else "")
        day = DAY_EN[k] if LANG == "en" else DAY_JA[k]
        rows.append(f'<tr data-day="{k}" class="{cls}"><th scope="row">{day}</th><td>{e(fmt_ranges(r))}</td></tr>')
    static = " data-static" if closed else ""  # 閉店した店は「今日」を付けない
    return f'<table class="week" data-week="{e(store["id"])}"{static}><tbody>{"".join(rows)}</tbody></table>'


def store_card(store, p):
    st = store.get("status", "open")
    badge = "" if st == "open" else f'<span class="badge b-{st}">{label(STATUS_LABEL.get(st, (st, st)))}</span>'
    nick = sv(store, "nickname") or ""
    return f"""<li class="store-card" data-id="{e(store['id'])}">
  <a href="{p}stores/{e(store['id'])}.html">
    <span class="sc-top"><span class="sc-area">{e(area_label(area_of(store)))}</span>{badge}<span class="live-badge" data-live="{e(store['id'])}"></span></span>
    <span class="sc-name">{e(short_name(store))}</span>
    <span class="sc-nick">{e(nick if LANG == 'ja' or nick != short_name(store) else '')}</span>
    <span class="sc-today" data-today="{e(store['id'])}">{e(store.get('hours_text') or '') if LANG == 'ja' else ''}</span>
    <span class="sc-closed">{L('定休', 'Closed')}: {e(closed_days(store))}</span>
  </a>
  <span class="sc-visited" data-visited="{e(store['id'])}" hidden>{L('行った', 'Visited')}</span>
</li>"""


def link_list(items):
    return '<ul class="links">' + "".join(items) + "</ul>"


def new_badge(date, ctx):
    """60日以内の発信に NEW を付ける。"""
    try:
        recent = (ctx["today"] - dt.date.fromisoformat(date[:10])).days <= 60
    except (TypeError, ValueError):
        recent = False
    return ' <span class="tag tag-new">NEW</span>' if recent else ""


def video_block(v, ctx=None):
    vid = youtube_id(v.get("url"))
    title = e(v.get("title"))
    date = date_span(v.get("date")) + (new_badge(v.get("date"), ctx) if ctx else "")
    if not vid:
        return f'<li>{ext(v["url"], title)}{date}</li>'
    return f"""<li class="yt">
  <button class="yt-load" data-yt="{e(vid)}" aria-label="{L('動画を再生', 'Play video')}: {title}">
    <img src="https://i.ytimg.com/vi/{e(vid)}/mqdefault.jpg" alt="" loading="lazy" width="320" height="180">
    <span class="yt-play" aria-hidden="true">▶</span>
  </button>
  {ext(v['url'], title)}{ja_mark()}{date}
</li>"""


def post_block(post, ctx=None):
    plat = post.get("platform")
    name = "Instagram" if plat == "instagram" else "X"
    summary = post.get("summary") if LANG == "ja" else None
    sum_html = f'<span class="post-sum">{e(summary)}</span>' if summary else ""
    return f"""<li class="post" data-platform="{e(plat)}">
  {ext(post['url'], f'<span class="tag">{name}</span>{L("投稿を開く", "Open post")}')}{date_span(post.get('date'))}{new_badge(post.get('date'), ctx) if ctx else ''} {sum_html}
  <button class="embed-load" data-embed="{e(post['url'])}" data-platform="{e(plat)}">{L('ここに表示', 'Show here')}</button>
  <div class="embed-slot"></div>
</li>"""


def news_text(n, field):
    if LANG == "en":
        key = f"{n.get('date')}:{n.get('store_id')}:{n.get('type')}"
        t = (TR.get("news") or {}).get(key, {}).get(field)
        if t:
            return t
    return n.get(field)


def news_item(n, ctx, p):
    sid = n.get("store_id")
    link = f' <a href="{p}stores/{e(sid)}.html">{L("店舗ページ", "Shop page")}</a>' if sid in ctx["by_id"] else ""
    src = n.get("source") or {}
    src_html = (" " + ext(src["url"], f'{L("出典", "Source")}: {e(src.get("label") or host_label(src["url"]))}', "muted small")) if src.get("url") else ""
    return f"""<li class="news-item t-{e(n.get('type'))}">
  <span class="date">{e(n.get('date'))}</span><span class="tag">{e(label(NEWS_TYPE.get(n.get('type'), ('', ''))))}</span>
  <strong>{e(news_text(n, 'title'))}</strong>
  <p>{e(news_text(n, 'summary'))}{link}{src_html}</p>
</li>"""


def dm_store_chips(v, ctx, p):
    return "".join(f' <a class="chip" href="{p}stores/{e(sid)}.html">{e(short_name(ctx["by_id"][sid]))}</a>'
                   for sid in v.get("store_ids") or [] if sid in ctx["by_id"])


def store_link(sid, ctx, p, fallback=None):
    s = ctx["by_id"].get(sid)
    if s:
        return f'<a href="{p}stores/{e(sid)}.html">{e(short_name(s))}</a>'
    node = ctx["lineage"][0].get(sid) or {}
    return e(fallback or (node.get("name_en") if LANG == "en" else None) or node.get("name") or sid)


# ---------------------------------------------------------------- 閉店・系譜

def closed_summary(store, ctx, p):
    kind = label(CLOSED_TYPE.get(store.get("closed_type"), CLOSED_TYPE["close"]))
    when = store.get("closed")
    opened = store.get("opened")
    period = f"{e(opened)}{L('〜', '–')}{e(when)}" if opened and when else e(when or L("不明", "unknown"))
    succ = store.get("successor_id")
    succ_html = f" → {store_link(succ, ctx, p)}" if succ else ""
    note = sv(store, "closed_note")
    note_html = f'<span class="small">{e(note)}</span>' if note else ""
    head = L(f"{kind}しました", kind)
    return f'<strong>{head}</strong>{succ_html}<br><span class="small">{L("営業期間", "In business")}: {period}</span><br>{note_html}'


def closed_sorted(stores):
    return sorted([s for s in stores if s.get("status") == "closed"], key=lambda s: s.get("closed") or "", reverse=True)


def closed_rows(closed, ctx, p):
    rows = []
    for s in closed:
        kind = s.get("closed_type") or "close"
        succ = s.get("successor_id")
        note = sv(s, "closed_note")
        sub = e(city_of(s))
        if s.get("opened"):
            sub += f" · {L('営業', 'open')} {e(s['opened'])}{L('〜', '–')}"
        if note:
            sub += f" · {e(note)}"
        rows.append(f"""<li class="closed-item">
  <span class="date">{e(s.get('closed') or L('時期不明', 'date unknown'))}</span>
  <span class="tag t-{e(kind)}">{e(label(CLOSED_TYPE.get(kind, CLOSED_TYPE['close'])))}</span>
  <a class="ci-name" href="{p}stores/{e(s['id'])}.html">{e(short_name(s))}</a>
  {f'<span class="ci-succ">→ {store_link(succ, ctx, p)}</span>' if succ else ''}
  <span class="ci-sub">{sub}</span>
</li>""")
    return "".join(rows)


def closed_block(closed, ctx, p, limit=None):
    closed = closed_sorted(closed)
    shown = closed[:limit] if limit else closed
    more = (f'<p class="small"><a href="{p}stores/closed.html">{L(f"閉店・移転した店をすべて見る（{len(closed)}店）", f"See all {len(closed)} closed shops")} →</a></p>'
            if limit else "")
    return f"""<section class="block closed-block">
  <div class="block-head"><h2>{L('閉店・移転した店', 'Closed & relocated shops')}</h2><span class="small muted">{len(closed)}{L('店', '')}</span></div>
  <ol class="closed-list">{closed_rows(shown, ctx, p) or f'<li class="muted">{L("まだ記録がありません", "None recorded yet")}</li>'}</ol>
  {more}
</section>"""


def pretty_href(url):
    """サイト内リンクを Cloudflare Pages の URL の形にする（index.html と .html を外す）。転送を挟まないため。"""
    if re.match(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//|#)", url):
        return url
    path, tail = re.match(r"^([^?#]*)(.*)$", url).groups()
    if path.endswith("index.html"):
        path = path[: -len("index.html")] or "./"
    elif path.endswith(".html"):
        path = path[:-5]
    return path + tail


def prettify_links(html_text):
    return re.sub(r'(<a\b[^>]*?\shref=")([^"]*)(")', lambda m: m.group(1) + pretty_href(m.group(2)) + m.group(3), html_text)


class AbsPage:
    """404 ページ用。どの深さの URL で出ても崩れないよう、サイトの根からの絶対パスを使う。"""

    def __init__(self):
        self.path = "404.html"
        self.p = "/" if LANG == "ja" else "/en/"
        self.a = "/"
        self.out = "404.html" if LANG == "ja" else "en/404.html"
        self.other = "/en/" if LANG == "ja" else "/"


def page_404(site, stores, ctx):
    pg = AbsPage()
    p = pg.p
    body = f"""
<h1 class="page-title">{L('ページが見つかりません', 'Page not found')}</h1>
<p>{L('お探しのページは見つかりませんでした。URL が変わったか、ページがなくなった可能性があります。', 'We could not find that page. It may have moved or no longer exists.')}</p>
<div class="actions">
  <a class="btn btn-primary" href="{p}index.html">{L('トップへ', 'Home')}</a>
  <a class="btn" href="{p}stores/index.html">{L('店舗一覧', 'All shops')}</a>
  <a class="btn" href="{p}map.html">{L('地図で探す', 'Map')}</a>
</div>"""
    html_text = layout(dict(site, base_url=""), pg, title=L("ページが見つかりません", "Page not found"), body=body, page="", share=False)
    return html_text.replace('<meta name="viewport"', '<meta name="robots" content="noindex">\n<meta name="viewport"', 1)


def lineage_index(lin, stores):
    nodes = {n["id"]: n for n in lin.get("nodes", [])}
    order = {s["id"]: i for i, s in enumerate(stores)}
    children = {}
    for n in nodes.values():
        if n.get("parent") in nodes and n["id"] != n.get("parent"):
            children.setdefault(n["parent"], []).append(n)
    for kids in children.values():
        kids.sort(key=lambda n: (order.get(n["id"], 999), n["id"]))
    return nodes, children


def lineage_chain(sid, nodes):
    chain, seen = [], set()
    cur = nodes.get(sid)
    while cur and cur["id"] not in seen:
        seen.add(cur["id"])
        chain.append(cur)
        cur = nodes.get(cur.get("parent"))
    return list(reversed(chain))


def node_name(n, ctx):
    s = ctx["by_id"].get(n["id"])
    if s:
        return short_name(s)
    if LANG == "en":
        return (TR.get("lineage") or {}).get(n["id"], {}).get("name") or n.get("name") or n["id"]
    return n.get("name") or n["id"]


def node_note(n):
    if LANG == "en":
        return (TR.get("lineage") or {}).get(n["id"], {}).get("note")
    return n.get("note")


def lineage_section(sid, ctx, p):
    nodes, children = ctx["lineage"]
    node = nodes.get(sid)
    if not node:
        return ""
    kids = children.get(sid, [])
    parts = []
    if sid == "mita":
        parts.append(f"<p>{L('すべての直系の本家です。', 'The original shop that every Ramen Jiro branch traces back to.')}</p>")
    elif node.get("parent") in nodes:
        chain = lineage_chain(sid, nodes)
        path = " › ".join(f"<strong>{e(node_name(n, ctx))}</strong>" if n["id"] == sid else store_link(n["id"], ctx, p, node_name(n, ctx))
                          for n in chain)
        conf = "" if node.get("confidence") == "high" else f' <span class="conf-low">{L("要出典", "weakly sourced")}</span>'
        parts.append(f'<p class="lineage-path">{path}{conf}</p>')
        also = node.get("also_trained_at") or []
        if also:
            parts.append(f'<p class="small">{L("ほかの修業先", "Also trained at")}: ' + ", ".join(store_link(x, ctx, p) for x in also) + "</p>")
    else:
        parts.append(f'<p class="muted">{L("修業先は確認できていません。", "We could not confirm where the owner trained.")}</p>')
    note = node_note(node)
    if note:
        parts.append(f'<p class="small">{e(note)}</p>')
    if kids:
        parts.append(f'<p class="small"><strong>{L(f"この店で修業した店（{len(kids)}）", f"Shops whose owners trained here ({len(kids)})")}:</strong></p><div class="chips">' +
                     "".join(f'<span class="chip">{store_link(k["id"], ctx, p, node_name(k, ctx))}</span>' for k in kids) + "</div>")
    srcs = [x for x in node.get("sources") or [] if x.get("url")]
    if srcs:
        parts.append(f'<p class="muted small">{L("出典", "Sources")}: ' + " · ".join(ext(x["url"], e(x.get("label") or host_label(x["url"]))) for x in srcs) + "</p>")
    parts.append(f'<p class="small"><a href="{p}lineage.html#n-{e(sid)}">{L("樹形図で見る", "See the family tree")} →</a></p>')
    return f'<section class="block"><h2>{L("系譜", "Lineage")}</h2>{"".join(parts)}</section>'


def descendants(nid, children):
    return sum(1 + descendants(k["id"], children) for k in children.get(nid, []))


def tree_node(n, ctx, p):
    nid = n["id"]
    s = ctx["by_id"].get(nid)
    status = (s or n).get("status") or "open"
    cls = ["node", f"conf-{n.get('confidence') or 'unknown'}"]
    if status == "closed":
        cls.append("is-closed")
    name = e(node_name(n, ctx))
    link = f'<a href="{p}stores/{e(nid)}.html">{name}</a>' if s else name
    year = (n.get("opened") or (s or {}).get("opened") or "")[:4]
    meta = [e(year)] if year else []
    if status == "closed":
        meta.append(label(CLOSED_TYPE["move"] if (s or n).get("successor_id") else CLOSED_TYPE["close"]))
    elif status == "upcoming":
        meta.append(label(STATUS_LABEL["upcoming"]))
    meta_html = f'<span class="n-meta">{" · ".join(meta)}</span>' if meta else ""
    q = f'<span class="n-q" title="{L("出典が少ない", "weakly sourced")}">?</span>' if n.get("confidence") == "low" else ""
    return f'<span class="{" ".join(cls)}" title="{e(node_note(n) or "")}">{link}{q}{meta_html}</span>'


def tree_html(n, ctx, p, depth=0):
    _, children = ctx["lineage"]
    kids = children.get(n["id"], [])
    branches = [k for k in kids if children.get(k["id"])]
    leaves = [k for k in kids if not children.get(k["id"])]
    inner = "".join(tree_html(k, ctx, p, depth + 1) for k in branches)
    if leaves:
        lab = f'<span class="leaves-label">{L("ほかに直接修業した店", "Other shops trained here directly")}</span>' if branches else ""
        inner += f'<li class="leaves">{lab}' + "".join(f'<span id="n-{e(k["id"])}">{tree_node(k, ctx, p)}</span>' for k in leaves) + "</li>"
    sub = f"<ul>{inner}</ul>" if inner else ""
    count = descendants(n["id"], children)
    cnt = f'<span class="n-count">{count}{L("店", " shops")}</span>' if count and depth > 0 else ""
    return f'<li id="n-{e(n["id"])}">{tree_node(n, ctx, p)}{cnt}{sub}</li>'


# ---------------------------------------------------------------- ページ

def store_tips(sid, ctx):
    """直系二郎大好きマンが話している、その店ならではのコツ（3店以下に関するものだけ。連食ルートの話は除く）。"""
    tips = (ctx["daisukiman"].get("tips") or [])
    en = ((TR.get("daisukiman") or {}).get("tips") or []) if LANG == "en" else []
    out = []
    for i, t in enumerate(tips):
        ids = t.get("store_ids") or []
        if sid in ids and len(ids) <= 3:
            text = en[i]["text"] if LANG == "en" and i < len(en) and en[i].get("text") else t["text"]
            out.append((text, t.get("source")))
    return out


def near_block(sid, ctx, p):
    near = ctx["near"].get(sid) or []
    if not near:
        return ""
    items = "".join(f'<li><a class="chip chip-link" href="{p}stores/{e(n)}.html">{e(short_name(ctx["by_id"][n]))} '
                    f'<b>{L("約", "")}{km:.1f}km</b></a></li>' if km < 10 else
                    f'<li><a class="chip chip-link" href="{p}stores/{e(n)}.html">{e(short_name(ctx["by_id"][n]))} '
                    f'<b>{L("約", "")}{km:.0f}km</b></a></li>' for n, km in near)
    return f'<section class="block"><h2>{L("近くの直系ラーメン二郎", "Nearby Ramen Jiro shops")}</h2><ul class="chips">{items}</ul></section>'


def nearest(stores, geo, k=3):
    """各店から近い営業中の直系 k 店（直線距離）。"""
    import math
    def km(a, b):
        r = math.pi / 180
        x = math.sin((b["lat"] - a["lat"]) * r / 2) ** 2 + math.cos(a["lat"] * r) * math.cos(b["lat"] * r) * math.sin((b["lng"] - a["lng"]) * r / 2) ** 2
        return 2 * 6371 * math.asin(math.sqrt(x))
    cands = [s["id"] for s in stores if s.get("status") in ("open", "temporarily_closed") and geo.get(s["id"], {}).get("lat")]
    out = {}
    for s in stores:
        g = geo.get(s["id"]) or {}
        if not g.get("lat"):
            continue
        ds = sorted((km(g, geo[c]), c) for c in cands if c != s["id"])
        out[s["id"]] = [(c, d) for d, c in ds[:k]]
    return out


def search_alias(store):
    """ファンが検索で使う呼び名。地名の通称は「〇〇二郎」（三田 → 三田二郎）、スモジのような呼び名はそのまま。"""
    nick = store.get("nickname") or ""
    if not nick:
        return ""
    if nick.endswith("二郎") or re.fullmatch(r"[ァ-ヶー]+", nick):
        return nick
    return nick + "二郎"


def hours_summary(hours):
    """曜日ごとの営業時間を「月〜金 11:00〜14:30、土 11:00〜15:00」の形にまとめる（休みの曜日は除く）。"""
    lab = DAY_EN if LANG == "en" else DAY_JA
    groups = []
    for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]:
        r = (hours or {}).get(d)
        if not r:
            groups.append(None)
        elif groups and groups[-1] and groups[-1][2] == r:
            groups[-1][1] = d
        else:
            groups.append([d, d, r])
    parts = [f"{lab[a] if a == b else lab[a] + L('〜', '–') + lab[b]} {fmt_ranges(r)}" for a, b, r in (g for g in groups if g)]
    return L("、", "; ").join(parts)


def main_price(store):
    mains = [m for m in live_menu(store) if isinstance(m.get("price"), int) and menu_kind(m["name"], m["price"]) == "main"]
    small = [m for m in mains if m["name"].startswith("小") or "小ラーメン" in m["name"]]
    return (small or mains or [None])[0]


MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def date_text(d):
    """"1968" → 1968年 / 1968、"2003-12" → 2003年12月 / December 2003、"2025-03-02" → 2025年3月2日 / March 2, 2025"""
    parts = [int(x) for x in str(d).split("-") if x.isdigit()]
    if len(parts) == 3:
        return L(f"{parts[0]}年{parts[1]}月{parts[2]}日", f"{MONTHS_EN[parts[1] - 1]} {parts[2]}, {parts[0]}")
    if len(parts) == 2:
        return L(f"{parts[0]}年{parts[1]}月", f"{MONTHS_EN[parts[1] - 1]} {parts[0]}")
    return L(f"{parts[0]}年", f"{parts[0]}") if parts else str(d)


def store_intro(store, ctx):
    """店の紹介文（データから自動で作る）。検索結果の説明文にも使う。"""
    st = store.get("status", "open")
    name, city, opened = full_name(store), city_of(store), store.get("opened")
    alias = search_alias(store) if LANG == "ja" else ""
    who = f"{name}（{alias}）" if alias else name
    if st == "upcoming":
        return L(f"{who}は、{city}に開店予定の直系ラーメン二郎の店です。開店日や営業時間は分かりしだい載せます。",
                 f"{name} is an upcoming official Ramen Jiro shop in {city}. Opening date and hours will be added once announced.")
    if st == "closed":
        kind = store.get("closed_type") or "close"
        when = store.get("closed")
        succ = ctx["by_id"].get(store.get("successor_id"))
        ja = f"{who}は、{city}にあった直系ラーメン二郎の店です。" + (f"{date_text(opened)}に開店し、" if opened else "")
        ja += f"{date_text(when)}に{ {'move': '移転', 'rename': '店名を変更'}.get(kind, '閉店') }しました。" if when else ""
        ja += f"移転先は{short_name(succ)}です。" if succ and LANG == "ja" else ""
        en = f"{name} was an official Ramen Jiro shop in {city}." + (f" Opened {date_text(opened)}." if opened else "")
        en += f" {({'move': 'Moved', 'rename': 'Renamed'}).get(kind, 'Closed')} {date_text(when)}." if when else ""
        en += f" It continues as {short_name(succ)}." if succ and LANG == "en" else ""
        return L(ja, en)
    summary = hours_summary(store.get("hours"))
    access = ((sv(store, "access") or [None])[0] or "").rstrip("。. ")
    price = main_price(store)
    since = L("創業", "Founded in") if store["id"] == "mita" else L("開店", "Opened in")
    paused = st == "temporarily_closed"
    if LANG == "ja":
        t = f"{who}は、{city}にある直系ラーメン二郎の店です。" + (f"{date_text(opened)}{since}。" if opened else "")
        t += "現在は一時休業中です。" if paused else ""
        t += f"営業時間の目安は{summary}、" if summary and not paused else ""
        t += (f"定休日は{closed_days(store)}。" if not paused else "") + (f"アクセスは{access}。" if access else "")
        if price:
            t += f"{price['name']}は{price['price']:,}円" + (f"（{store['menu_checked']}時点）" if store.get("menu_checked") else "") + "。"
        return t
    t = f"{name} is an official Ramen Jiro shop in {city}." + (f" {since} {date_text(opened)}." if opened else "")
    t += " Currently closed temporarily." if paused else ""
    t += f" Hours (approx.): {summary}." if summary and not paused else ""
    t += (f" Closed: {closed_days(store)}." if not paused else "") + (f" Access: {access}." if access else "")
    if price:
        t += f" {menu_name(store, price)}: ¥{price['price']:,}" + (f" (as of {store['menu_checked']})" if store.get("menu_checked") else "") + "."
    return t


def clip(text, n):
    return text if len(text) <= n else text[: n - 1].rstrip("、。,. ") + "…"


def page_store(site, store, ctx):
    pg = Page(f"stores/{store['id']}.html")
    p = pg.p
    sid = store["id"]
    intro = store_intro(store, ctx)
    st = store.get("status", "open")
    name = short_name(store)
    nick = sv(store, "nickname")
    opened_label = L("創業", "Founded") if sid == "mita" else L("開店", "Opened")
    alias_ja = search_alias(store)
    meta = [(f"通称「{e(alias_ja)}」" if alias_ja else "") if LANG == "ja" else (f"a.k.a. “{e(nick)}”" if nick and nick != name else ""),
            e(city_of(store)), f"{opened_label} {e(store['opened'])}" if store.get("opened") else ""]
    meta = " · ".join(m for m in meta if m)

    status_note = ""
    if st == "closed":
        status_note = f'<div class="status-note b-closed">{closed_summary(store, ctx, p)}</div>'
    elif st != "open":
        status_note = f'<p class="status-note b-{st}">{label(STATUS_LABEL[st])}: {L("最新情報は公式アカウントで確認してください。", "check the official account for the latest.")}</p>'
    for x in ctx["stores"]:
        if x.get("successor_id") == sid:
            kind = label(CLOSED_TYPE.get(x.get("closed_type"), CLOSED_TYPE["move"]))
            status_note += f'<p class="small">{L("前身", "Previously")}: <a href="{p}stores/{e(x["id"])}.html">{e(short_name(x))}</a>（{e(x.get("closed") or "")} {e(kind)}）</p>'

    geo = ctx["geo"].get(sid) or {}
    if st == "closed" and not re.search(r"[0-9０-９]", store.get("address") or ""):
        geo = {}  # 番地まで分からない旧店舗は地図を出さない（市役所などに立ってしまうため）
    maps = "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(store["name"] + " " + (store.get("address") or ""))

    access = "".join(f"<li>{e(x)}</li>" for x in sv(store, "access") or [])
    notes = "".join(f"<li>{e(x)}</li>" for x in live_list(store, "hours_notes"))

    menu = live_menu(store)
    menu_html = f"<p class=muted>{L('情報なし', 'No information')}</p>"
    if menu:
        rows = "".join(f"<tr><th scope=row>{e(menu_name(store, m))}{menu_note(store, m)}</th>"
                       f"<td>{yen(m.get('price'))}{'〜' if m.get('price_from') else ''}</td></tr>" for m in menu)
        checked = f'<p class="muted small">{L("価格の確認時期", "Prices checked")}: {e(store["menu_checked"])}</p>' if store.get("menu_checked") else ""
        menu_html = f'<table class="menu"><tbody>{rows}</tbody></table>{checked}'

    rules = live_list(store, "rules")
    common = f'<a href="{p}guide.html">{L("はじめての二郎", "How to order")}</a>'
    rules_html = ("<ul class=rules>" + "".join(f"<li>{e(r)}</li>" for r in rules) + "</ul>"
                  + f'<p class="muted small">{L("代表待ちの禁止など、どの店でも共通のマナーは", "Manners common to every shop (no saving places in line, etc.) are in ")}{common}{L("へ。", ".")}</p>'
                  if rules else
                  f'<p class=muted>{L("特記事項なし。どの店でも共通の流れとマナーは", "Nothing specific to this shop. For the usual routine and manners, see ")}{common}{L("へ。", ".")}</p>')
    feats_html = "".join(f'<span class="chip">{e(f)}</span>' for f in live_list(store, "features"))

    sns = store.get("sns") or {}
    sns_items = []
    if sns.get("x"):
        note = f' <span class="muted small">（{e(sns["x_note"])}）</span>' if sns.get("x_note") and LANG == "ja" else ""
        sns_items.append(f'<li>{ext(sns["x"], "<span class=tag>X</span>" + e(sns["x"].rstrip("/").split("/")[-1]))}{note}</li>')
    if sns.get("instagram"):
        sns_items.append(f'<li>{ext(sns["instagram"], "<span class=tag>Instagram</span>" + e(sns["instagram"].rstrip("/").split("/")[-1]))}</li>')
    if sns.get("web"):
        sns_items.append(f'<li>{ext(sns["web"], "<span class=tag>Web</span>" + e(host_label(sns["web"])))}</li>')
    sns_html = link_list(sns_items) if sns_items else f'<p class=muted>{L("公式アカウントは確認できていません", "No official account found")}</p>'

    rs = [x for x in ctx["articles"] if x.get("store_id") == sid or sid in (x.get("covers_store_ids") or [])]
    rs.sort(key=lambda x: x.get("date") or "", reverse=True)
    rs_html = (link_list([f'<li>{ext(x["url"], e(x["title"]))}{ja_mark()}{date_span(x.get("date"))}</li>' for x in rs]) if rs
               else f'<p class=muted>{L("この店の記事はまだありません", "No articles yet")}</p>')

    dm = ctx["daisukiman"]
    # 直系二郎大好きマンの発信は新しいものを優先して見せる
    vids = sorted((v for v in ctx["videos"] if sid in (v.get("store_ids") or [])), key=lambda v: v.get("date") or "", reverse=True)
    posts = sorted((x for x in dm.get("posts", []) if sid in (x.get("store_ids") or [])), key=lambda x: x.get("date") or "", reverse=True)
    q = store.get("nickname") or re.sub(r"^ラーメン二郎\s*", "", store["name"]).replace("店", "")
    dm_x = ((dm.get("profile") or {}).get("links") or {}).get("x") or "https://x.com/delicious2626"
    dm_x = dm_x.rstrip("/").split("/")[-1]
    dm_parts = []
    tips = store_tips(sid, ctx)
    if tips:
        dm_parts.append(f'<h3>{L("この店のコツ", "Tips for this shop")}</h3><ul class="tips">' + "".join(
            f'<li>{e(text)}{src_link(src)}</li>' for text, src in tips) + "</ul>")
    latest = max([x.get("date") or "" for x in vids + posts] + [""])
    if latest:
        dm_parts.append(f'<p class="small">{L("この店についての直近の発信", "Most recent coverage of this shop")}: <strong>{e(latest)}</strong>{new_badge(latest, ctx)}</p>')
    if vids:
        more = (f'<details class="more"><summary>{L(f"以前の動画（{len(vids) - 4}本）", f"Older videos ({len(vids) - 4})")}</summary><ul class="videos">' +
                "".join(video_block(v, ctx) for v in vids[4:]) + "</ul></details>") if len(vids) > 4 else ""
        dm_parts.append(f'<h3>{L("動画", "Videos")}</h3><ul class="videos">' + "".join(video_block(v, ctx) for v in vids[:4]) + "</ul>" + more)
    if posts:
        more = (f'<details class="more"><summary>{L(f"以前の投稿（{len(posts) - 3}件）", f"Older posts ({len(posts) - 3})")}</summary><ul class="posts">' +
                "".join(post_block(x, ctx) for x in posts[3:]) + "</ul></details>") if len(posts) > 3 else ""
        dm_parts.append(f'<h3>{L("投稿", "Posts")}</h3><ul class="posts">' + "".join(post_block(x, ctx) for x in posts[:3]) + "</ul>" + more)
    if not vids and not posts:
        dm_parts.append(f'<p class="muted">{L("この店の動画・投稿はまだ収録していません", "No videos or posts indexed for this shop yet")}</p>')
    dm_parts.append(f'<p class="small">{ext(x_search_url(f"from:{dm_x} {q}"), L(f"X で「{e(q)}」の投稿を検索", f"Search their X posts about this shop"))}'
                    f'　<span class="muted">{L("（X のログインが必要な場合があります）", "(may require an X login; posts are in Japanese)")}</span></p>')

    news = [n for n in ctx["news"] if n.get("store_id") == sid]
    news_html = (f'<section class="block"><h2>{L("この店のニュース", "News")}</h2><ul class="news-list">' +
                 "".join(news_item(n, ctx, p) for n in news) + "</ul></section>") if news else ""

    src_html = "".join(f'<li>{ext(x["url"], e(x.get("label") or host_label(x["url"])))}{date_span(x.get("date"))}</li>'
                       for x in store.get("sources") or [] if x.get("url"))
    conflicts = sv(store, "conflicts") or []
    conf_html = ""
    if conflicts and (LANG == "ja" or tr_store(store).get("conflicts")):
        conf_html = (f'<details class="conflicts"><summary>{L("情報源によって食い違う点", "Where sources disagree")}（{len(conflicts)}）</summary><ul>' +
                     "".join(f"<li>{e(c)}</li>" for c in conflicts) + "</ul></details>")

    if st == "closed":
        crumb_tail = f'<a href="{p}stores/closed.html">{L("閉店・移転した店", "Closed shops")}</a>'
    else:
        a = area_of(store)
        crumb_tail = f'<a href="{p}stores/index.html#area={e(urllib.parse.quote(a))}">{e(area_label(a))}</a>'

    addr_en = tr_store(store).get("address") if LANG == "en" else None
    addr_html = f'<p class="addr">{e(addr_en)}</p><p class="small muted" lang="ja">{e(store.get("address") or "")}</p>' if addr_en else \
        f'<p class="addr"{"" if LANG == "ja" else " lang=ja"}>{e(store.get("address") or L("住所未確認", "Address unknown"))}</p>'

    body = f"""
<nav class="crumb" aria-label="{L('パンくず', 'Breadcrumb')}"><a href="{p}index.html">{L('ホーム', 'Home')}</a> › <a href="{p}stores/index.html">{L('店舗', 'Shops')}</a> › {crumb_tail}</nav>
<article class="store" data-store-page="{e(sid)}">
  <header class="store-head">
    <h1 class="signboard"><span class="sb-ramen">{L('ラーメン', 'Ramen')}</span><span class="sb-jiro">{L('二郎', ' Jiro')}</span> <span class="sb-shop">{e(name)}</span></h1>
    {'' if LANG == 'ja' else f'<p class="small muted" lang="ja">{e(store["name"])}</p>'}
    <p class="store-meta">{meta}</p>
    <p class="store-intro">{e(intro)}</p>
    {status_note}
    {'' if st == 'closed' else f'<p class="live-line" data-live-line="{e(sid)}">{L("営業状況を計算中…", "Checking hours…")}</p>'}
    <div class="actions">
      {'' if st == 'closed' else f'<a class="btn btn-primary" href="{p}log.html?store={e(sid)}">{L("この店をログに記録", "Log a visit")}</a>'}
      {ext(maps, L('地図アプリで開く', 'Open in Google Maps'), 'btn')}
      <span class="visited-pill" data-visited-pill="{e(sid)}" hidden></span>
    </div>
  </header>

  <div class="grid-2">
    <section class="block">
      <h2>{L('当時の営業時間', 'Former hours') if st == 'closed' else L('営業時間', 'Hours')} <span class="muted small">{L('目安', 'approx.')}</span></h2>
      {week_table(store)}
      {'' if st == 'closed' else f"<p class=small><strong>{L('定休日', 'Closed')}:</strong> {e(closed_days(store))}</p>"}
      {f'<ul class="notes small">{notes}</ul>' if notes else ''}
    </section>
    <section class="block">
      <h2>{L('場所', 'Location')}</h2>
      {addr_html}
      {f'<ul class="access small">{access}</ul>' if access else ''}
      {f'<div class="mini-map" data-lat="{geo["lat"]}" data-lng="{geo["lng"]}" data-name="{e(name)}"></div>' if geo.get('lat') else ''}
    </section>
    <section class="block">
      <h2>{L('メニュー', 'Menu')}</h2>
      {menu_html}
    </section>
    <section class="block">
      <h2>{L('この店ならではのルール', 'House rules')}</h2>
      {rules_html}
      {f'<div class="chips">{feats_html}</div>' if feats_html else ''}
    </section>
  </div>

  <section class="block dm-block">
    <h2>{L('直系二郎大好きマンの最新情報', 'Latest from Chokkei Jiro Daisuki Man')}</h2>
    {''.join(dm_parts)}
  </section>

  {near_block(sid, ctx, p)}

  {lineage_section(sid, ctx, p)}

  <section class="block">
    <h2>{L('公式アカウント', 'Official accounts')}</h2>
    {sns_html}
  </section>

  <section class="block">
    <h2>{L('ラーメンシーンの記事', 'Ramen Scene articles')}</h2>
    {rs_html}
  </section>

  {news_html}

  <section class="block sources">
    <h2>{L('情報源', 'Sources')}</h2>
    <ul class="links small">{src_html}</ul>
    {conf_html}
    <p class="muted small">{L('最終確認', 'Last checked')}: {e(store.get('checked') or '—')}</p>
    <p class="small"><a class="btn btn-small" href="{p}report.html?store={e(sid)}&amp;page={e(urllib.parse.quote(pg.out))}">{L('この店の情報の誤りを報告', 'Report a mistake on this page')}</a></p>
  </section>
</article>"""
    head_extra, scripts = "", ["assets/store.js"]
    if geo.get("lat"):
        head_extra, scripts = LEAFLET_CSS, [LEAFLET_JS] + scripts
    alias = search_alias(store)
    if st == "closed":
        title = L(f"ラーメン二郎 {name}（閉店・移転）", f"Ramen Jiro {name} (closed)")
    elif st == "upcoming":
        title = L(f"ラーメン二郎 {name}（開店予定）", f"Ramen Jiro {name} (coming soon)")
    else:
        title = L(f"ラーメン二郎 {name}（{alias}）営業時間・定休日・メニュー" if alias else f"ラーメン二郎 {name} 営業時間・定休日・メニュー",
                  f"Ramen Jiro {name}: hours, closing days and menu")
    head_extra += store_jsonld(site, store, pg, geo) + breadcrumb_jsonld(site, store)
    desc = clip(intro, L(120, 160))
    og = f"assets/og/stores/{sid}.png" if (STATIC / "og" / "stores" / f"{sid}.png").exists() else None
    return pg, layout(site, pg, title=title, body=body, page="stores", description=desc, scripts=scripts, head_extra=head_extra, ad=True, og_image=og)


SCHEMA_DAYS = {"mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday", "fri": "Friday", "sat": "Saturday", "sun": "Sunday"}


def jsonld(obj):
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False).replace("</", "<\\/") + "</script>"


def store_jsonld(site, store, pg, geo):
    """検索エンジン向けの店舗情報（schema.org の Restaurant）。営業中・休業中の店だけ。"""
    if store.get("status") not in ("open", "temporarily_closed") or not site.get("base_url"):
        return ""
    url = site["base_url"].rstrip("/") + "/" + pretty(pg.out)
    hours = []
    for k, day in SCHEMA_DAYS.items():
        for a, b in (store.get("hours") or {}).get(k) or []:
            hb = int(b[:2])
            hours.append({"@type": "OpeningHoursSpecification", "dayOfWeek": f"https://schema.org/{day}",
                          "opens": a, "closes": f"{hb - 24:02d}{b[2:]}" if hb >= 24 else b})
    prices = [m["price"] for m in live_menu(store) if isinstance(m.get("price"), int) and menu_kind(m["name"], m["price"]) == "main"]
    sns = store.get("sns") or {}
    obj = {"@context": "https://schema.org", "@type": "Restaurant", "name": full_name(store), "url": url,
           "servesCuisine": L("ラーメン", "Ramen"),
           "address": {"@type": "PostalAddress", "streetAddress": store.get("address"), "addressRegion": store.get("prefecture"), "addressCountry": "JP"}}
    if LANG == "en":
        obj["alternateName"] = store["name"]
    if geo.get("lat"):
        obj["geo"] = {"@type": "GeoCoordinates", "latitude": geo["lat"], "longitude": geo["lng"]}
    if hours and store.get("status") == "open":
        obj["openingHoursSpecification"] = hours
    if prices:
        obj["priceRange"] = f"¥{min(prices):,}–{max(prices):,}"
    same = [u for u in (sns.get("x"), sns.get("instagram"), sns.get("web")) if u]
    if same:
        obj["sameAs"] = same
    return jsonld(obj)


def breadcrumb_jsonld(site, store):
    if not site.get("base_url"):
        return ""
    base = site["base_url"].rstrip("/") + "/" + ("en/" if LANG == "en" else "")
    items = [(L("ホーム", "Home"), base), (L("店舗", "Shops"), base + "stores/")]
    if store.get("status") == "closed":
        items.append((L("閉店・移転した店", "Closed shops"), base + "stores/closed"))
    items.append((full_name(store), base + f"stores/{store['id']}"))
    return jsonld({"@context": "https://schema.org", "@type": "BreadcrumbList",
                   "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": u} for i, (n, u) in enumerate(items)]})


AREA_SLUG = {"北海道": "hokkaido", "宮城県": "miyagi", "福島県": "fukushima", "茨城県": "ibaraki", "栃木県": "tochigi",
             "群馬県": "gunma", "埼玉県": "saitama", "千葉県": "chiba", "東京23区": "tokyo-23ku", "東京多摩": "tokyo-tama",
             "神奈川県": "kanagawa", "新潟県": "niigata", "長野県": "nagano", "愛知県": "aichi", "京都府": "kyoto",
             "福岡県": "fukuoka", "沖縄県": "okinawa"}
AREA_PAGE_MIN = 3  # これ以上の店があるエリアだけ専用ページを作る


def area_pages(stores):
    counts = {}
    for s in stores:
        if s.get("status") in ("open", "temporarily_closed"):
            counts[area_of(s)] = counts.get(area_of(s), 0) + 1
    return {a: AREA_SLUG[a] for a in sorted(counts, key=area_rank) if a in AREA_SLUG and counts[a] >= AREA_PAGE_MIN}


def area_href(a, p, ctx):
    slug = ctx["area_pages"].get(a)
    return f"{p}areas/{slug}.html" if slug else f"{p}stores/index.html#area={urllib.parse.quote(a)}"


def area_row(s, p):
    alias = search_alias(s) if LANG == "ja" else ""
    alias_html = f' <span class="muted small">{e(alias)}</span>' if alias else ""
    access = (sv(s, "access") or [""])[0]
    hours = hours_summary(s.get("hours")) or L("要確認", "Check")
    closed = closed_days(s) if s.get("status") == "open" else label(STATUS_LABEL.get(s.get("status"), ("", "")))
    return (f'<tr><th scope="row"><a href="{p}stores/{e(s["id"])}.html">{e(short_name(s))}</a>{alias_html}</th>'
            f'<td>{e(hours)}</td><td>{e(closed)}</td><td>{e(access)}</td></tr>')


def page_area(site, stores, ctx, a, slug):
    pg = Page(f"areas/{slug}.html")
    p = pg.p
    items = [s for s in stores if area_of(s) == a and s.get("status") in ("open", "temporarily_closed")]
    n, name = len(items), area_label(a)
    intro = L(f"{name}にある直系ラーメン二郎は {n} 店です。各店の営業時間の目安・定休日・アクセスを一覧にしました。いま営業中かどうかは、上のカードで確かめられます。店名を押すと、メニューや店ごとのルールも見られます。",
              f"There are {n} official Ramen Jiro shops in {name}. Here are their approximate hours, closing days and access. The cards show which are open right now; open a shop for its menu and house rules.")
    others = "".join(f'<a class="chip chip-link" href="{p}areas/{sl}.html">{e(area_label(ar))}</a>' for ar, sl in ctx["area_pages"].items() if ar != a)
    body = f"""
<nav class="crumb" aria-label="{L('パンくず', 'Breadcrumb')}"><a href="{p}index.html">{L('ホーム', 'Home')}</a> › <a href="{p}stores/index.html">{L('店舗', 'Shops')}</a> › {e(name)}</nav>
<h1 class="page-title">{L(f'{name}の直系ラーメン二郎', f'Ramen Jiro in {name}')}</h1>
<p>{e(intro)}</p>
<ul class="store-grid">{''.join(store_card(s, p) for s in items)}</ul>
<section class="block" style="margin-top:20px">
  <h2>{L('営業時間・定休日の一覧', 'Hours and closing days')}</h2>
  <div class="table-scroll"><table class="area-table">
    <thead><tr><th>{L('店', 'Shop')}</th><th>{L('営業時間（目安）', 'Hours (approx.)')}</th><th>{L('定休日', 'Closed')}</th><th>{L('アクセス', 'Access')}</th></tr></thead>
    <tbody>{''.join(area_row(s, p) for s in items)}</tbody>
  </table></div>
  <p class="muted small">{L('営業時間は目安です。麺切れ・臨時休業はよくあるので、公式アカウントを確認してから行きましょう。', 'Hours are approximate. Check the official account before you go.')}</p>
</section>
<section class="block">
  <h2>{L('ほかのエリア・条件で探す', 'Other areas and lists')}</h2>
  <div class="chips">{others}{list_links(p)}<a class="chip chip-link" href="{p}stores/index.html">{L('全店舗', 'All shops')}</a></div>
</section>"""
    crumbs = ""
    if site.get("base_url"):
        base = site["base_url"].rstrip("/") + "/" + ("en/" if LANG == "en" else "")
        crumbs = jsonld({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": L("ホーム", "Home"), "item": base},
            {"@type": "ListItem", "position": 2, "name": L("店舗", "Shops"), "item": base + "stores/"},
            {"@type": "ListItem", "position": 3, "name": name, "item": base + f"areas/{slug}"}]})
    title = L(f"ラーメン二郎 {name}の直系{n}店 営業時間・定休日一覧", f"Ramen Jiro shops in {name} ({n}): hours and closing days")
    return pg, layout(site, pg, title=title, body=body, page="stores", description=clip(intro, L(120, 160)), head_extra=crumbs, ad=True)


def first_open(hours, d):
    r = (hours or {}).get(d) or []
    return toMin(r[0][0]) if r else None


def last_close(hours, d):
    r = (hours or {}).get(d) or []
    return toMin(r[-1][1]) if r else None


def toMin(t):
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def fmt_min(n):
    return fmt_time(f"{n // 60:02d}:{n % 60:02d}")


def day_groups(values):
    """{曜日: 値} を、同じ値が続く曜日でまとめる → [(月〜金, 値), ...]"""
    lab = DAY_EN if LANG == "en" else DAY_JA
    out = []
    for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]:
        v = values.get(d)
        if v is None:
            out.append(None)
        elif out and out[-1] and out[-1][2] == v:
            out[-1][1] = d
        else:
            out.append([d, d, v])
    return [(lab[a] if a == b else lab[a] + L("〜", "–") + lab[b], v) for a, b, v in (g for g in out if g)]


def list_sunday(s):
    r = (s.get("hours") or {}).get("sun")
    return (L("日", "Sun") + " " + fmt_ranges(r), 0) if r else None


def list_morning(s):
    vals = {d: first_open(s.get("hours"), d) for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}
    vals = {d: v for d, v in vals.items() if v is not None and v < 11 * 60}
    if not vals:
        return None
    text = L("、", "; ").join(f"{days} {fmt_min(v)}{L('〜', '–')}" for days, v in day_groups(vals))
    return text, min(vals.values())


def list_late(s):
    vals = {d: last_close(s.get("hours"), d) for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}
    vals = {d: v for d, v in vals.items() if v is not None and v > 20 * 60}
    if not vals:
        return None
    text = L("、", "; ").join(f"{days} {L('〜', '–')}{fmt_min(v)}" for days, v in day_groups(vals))
    return text, -max(vals.values())


LISTS = {
    "sunday": (list_sunday, ("日曜に営業しているラーメン二郎", "Ramen Jiro shops open on Sundays"), ("日曜の営業時間", "Sunday hours"),
               ("日曜に営業している直系ラーメン二郎の一覧です。日曜の営業時間（目安）と定休日を載せています。", "Official Ramen Jiro shops that open on Sundays, with their Sunday hours (approx.) and closing days.")),
    "morning": (list_morning, ("朝から食べられるラーメン二郎（11時前に開店）", "Ramen Jiro shops that open before 11:00"), ("朝の開店時刻", "Morning opening"),
                ("11時より前に開店する直系ラーメン二郎の一覧です。開店の早い順に並べています。", "Official Ramen Jiro shops that open before 11:00, earliest first.")),
    "late": (list_late, ("夜遅くまで営業しているラーメン二郎（20時以降も営業）", "Ramen Jiro shops open after 20:00"), ("閉店時刻（遅い日）", "Latest closing"),
             ("20時を過ぎても営業している直系ラーメン二郎の一覧です。閉店の遅い順に並べています。", "Official Ramen Jiro shops still open after 20:00, latest first.")),
}


def list_links(p, skip=None):
    return "".join(f'<a class="chip chip-link" href="{p}lists/{k}.html">{e(label(v[1]))}</a>' for k, v in LISTS.items() if k != skip)


def page_list(site, stores, ctx, key):
    fn, (title_ja, title_en), (col_ja, col_en), (intro_ja, intro_en) = LISTS[key]
    pg = Page(f"lists/{key}.html")
    p = pg.p
    hits = []
    for i, s in enumerate(stores):
        if s.get("status") != "open":
            continue
        r = fn(s)
        if r:
            hits.append((r[1], area_rank(area_of(s)), i, s, r[0]))
    hits.sort(key=lambda x: (x[0], x[1], x[2]))
    n = len(hits)
    title = L(f"{title_ja} 直系{n}店", f"{title_en} ({n})")
    rows = "".join(f'<tr><th scope="row"><a href="{p}stores/{e(s["id"])}.html">{e(short_name(s))}</a></th><td>{e(detail)}</td>'
                   f'<td>{e(closed_days(s))}</td><td><a href="{e(area_href(area_of(s), p, ctx))}">{e(area_label(area_of(s)))}</a></td></tr>'
                   for _, _, _, s, detail in hits)
    body = f"""
<nav class="crumb" aria-label="{L('パンくず', 'Breadcrumb')}"><a href="{p}index.html">{L('ホーム', 'Home')}</a> › <a href="{p}stores/index.html">{L('店舗', 'Shops')}</a> › {e(L(title_ja, title_en))}</nav>
<h1 class="page-title">{e(L(title_ja, title_en))}</h1>
<p>{e(L(intro_ja, intro_en))} {L('営業時間は目安です。出かける前に各店の公式アカウントを確認してください。', 'Hours are approximate; check the official account before you go.')}</p>
<section class="block">
  <div class="table-scroll"><table class="area-table">
    <thead><tr><th>{L('店', 'Shop')}</th><th>{e(L(col_ja, col_en))}</th><th>{L('定休日', 'Closed')}</th><th>{L('エリア', 'Area')}</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
</section>
<ul class="store-grid">{''.join(store_card(s, p) for _, _, _, s, _ in hits)}</ul>
<section class="block" style="margin-top:20px">
  <h2>{L('ほかの条件・エリアで探す', 'More ways to browse')}</h2>
  <div class="chips">{list_links(p, key)}{''.join(f'<a class="chip chip-link" href="{p}areas/{sl}.html">{e(area_label(ar))}</a>' for ar, sl in ctx["area_pages"].items())}<a class="chip chip-link" href="{p}stores/index.html">{L('全店舗', 'All shops')}</a></div>
</section>"""
    return pg, layout(site, pg, title=title, body=body, page="stores", description=clip(L(intro_ja, intro_en), L(120, 160)), ad=True)


def page_index(site, stores, ctx):
    pg = Page("index.html")
    p = pg.p
    active = [s for s in stores if s.get("status") in ("open", "temporarily_closed")]
    paused = sum(1 for s in active if s.get("status") == "temporarily_closed")
    paused_ja = f"（うち休業中 {paused} 店）" if paused else ""
    paused_en = f" ({paused} temporarily closed)" if paused else ""
    news = ctx["news"][:5]
    news_html = ('<ul class="news-list">' + "".join(news_item(n, ctx, p) for n in news) + "</ul>") if news else f"<p class=muted>{L('ニュースはまだありません', 'No news yet')}</p>"
    areas = {}
    for s in stores:
        if s.get("status") in ("open", "temporarily_closed"):
            areas[area_of(s)] = areas.get(area_of(s), 0) + 1
    area_html = "".join(f'<a class="chip chip-link" href="{e(area_href(a, p, ctx))}">{e(area_label(a))} <b>{areas[a]}</b></a>'
                        for a in sorted(areas, key=area_rank))
    # 全店舗へのリンク（トップから直接たどれるように）
    all_rows = []
    for a in sorted(areas, key=area_rank):
        links = " · ".join(f'<a href="{p}stores/{e(s["id"])}.html">{e(short_name(s))}</a>'
                           for s in stores if area_of(s) == a and s.get("status") in ("open", "temporarily_closed"))
        all_rows.append(f'<p class="all-row"><a class="all-area" href="{e(area_href(a, p, ctx))}">{e(area_label(a))}</a>{links}</p>')
    all_html = "".join(all_rows)
    n_closed = sum(1 for s in stores if s.get("status") == "closed")
    if n_closed:
        area_html += f'<a class="chip chip-link chip-closed" href="{p}stores/closed.html">{L("閉店・移転した店", "Closed shops")} <b>{n_closed}</b></a>'
    upcoming = [s for s in stores if s.get("status") == "upcoming"]
    up_html = ""
    if upcoming:
        up_html = f'<p class="small">{L("開店予定", "Coming soon")}: ' + ", ".join(f'<a href="{p}stores/{e(s["id"])}.html">{e(short_name(s))}</a>' for s in upcoming) + "</p>"
    rs = ctx["ramenscene"].get("site", {})
    dml = (ctx["daisukiman"].get("profile") or {}).get("links") or {}
    rs_about = rs.get("about") if LANG == "ja" else TR.get("ramenscene_about")
    hero_h1 = L('<span class="hero-brand">二郎ログ</span>いま開いてる<em>二郎</em>は<span class="hero-count" data-open-count>—</span>店',
                '<span class="hero-brand">Jiro Log</span><span class="hero-count" data-open-count>—</span> <em>Jiro</em> shops are open now')
    body = f"""
<section class="hero">
  <div class="hero-text">
    <p class="kicker">{L('直系ラーメン二郎 専門', 'All about the real Ramen Jiro')}</p>
    <h1>{hero_h1}</h1>
    <p class="hero-sub">{L(f'<strong>二郎ログ</strong>は、全国 <strong>{len(active)}</strong> 店{paused_ja}の直系ラーメン二郎の営業時間・定休日・ルール・系譜をまとめた非公式の情報サイトです。時刻は日本時間 <span data-clock>--:--</span> で計算。',
                            f'<strong>Jiro Log</strong> is an unofficial guide to all <strong>{len(active)}</strong> official Ramen Jiro shops in Japan{paused_en}: hours, closing days, house rules and lineage. Now in Japan: <span data-clock>--:--</span>.')}</p>
    <div class="actions">
      <a class="btn btn-primary" href="{p}stores/index.html#open=1">{L('営業中の店を見る', 'Shops open now')}</a>
      <a class="btn" href="{p}map.html">{L('地図で探す', 'Map')}</a>
      <a class="btn" href="{p}guide.html">{L('はじめての二郎', 'How to order')}</a>
    </div>
    {up_html}
  </div>
</section>

<section class="block">
  <div class="block-head"><h2>{L('いま営業中', 'Open now')}</h2><a class="small" href="{p}stores/index.html#open=1">{L('一覧で見る', 'See list')} →</a></div>
  <ul class="store-grid" data-open-list></ul>
  <p class="muted small" data-open-empty hidden>{L('いま営業中の直系はありません（または営業時間が要確認です）。', 'No shops are open right now (or their hours need checking).')}<a href="{p}stores/index.html">{L('今日の営業を一覧で見る', 'See today’s hours')}</a></p>
  <noscript><p>{L('営業中の判定には JavaScript が必要です。', 'JavaScript is needed to show what is open.')}<a href="{p}stores/index.html">{L('店舗一覧', 'Shop list')}</a></p></noscript>
</section>


<section class="block">
  <h2>{L('エリアから探す', 'Browse by area')}</h2>
  <div class="chips">{area_html}</div>
  <h3>{L('条件で探す', 'Browse by time')}</h3>
  <div class="chips">{list_links(p)}</div>
</section>

<div class="grid-2">
  <section class="block">
    <div class="block-head"><h2>{L('ニュース', 'News')}</h2><a class="small" href="{p}news.html">{L('すべて', 'All')} →</a></div>
    {news_html}
  </section>
  <section class="block">
    <h2>{L('マイ二郎ログ', 'My Jiro log')}</h2>
    <p>{L('行った店と食べた一杯を記録して、全店制覇までの進み具合を見られます。記録はこのブラウザだけに保存されます。', 'Record the shops you visit and track your progress toward visiting them all. Your log stays in this browser.')}</p>
    <div class="progress" data-progress><div class="bar"><span style="width:0%"></span></div><p class="small" data-progress-text></p></div>
    <div class="actions"><a class="btn" href="{p}log.html">{L('マイログを開く', 'Open my log')}</a><a class="btn" href="{p}ranking.html">{L('ランキング', 'Ranking')}</a></div>
  </section>
</div>


<section class="block">
  <div class="block-head"><h2>{L('全店舗', 'All shops')}</h2><a class="small" href="{p}stores/index.html">{L('一覧で見る', 'See list')} →</a></div>
  {all_html}
</section>

<section class="block credits">
  <h2>{L('参考にしている発信', 'Sources we follow')}</h2>
  <div class="grid-2">
    <div>
      <h3>{ext(rs.get('url', 'https://ramen-scene.com'), L('ラーメンシーン', 'Ramen Scene'))}{ja_mark()}</h3>
      <p class="small">{e(rs_about or L('二郎を中心にしたラーメン情報サイト。', 'A Japanese blog covering every Ramen Jiro shop.'))} {L('各店ページから記事にリンクしています。', 'Each shop page links to its articles.')}</p>
    </div>
    <div>
      <h3>{L('直系二郎大好きマン', 'Chokkei Jiro Daisuki Man')}{ja_mark()}</h3>
      <p class="small">{L('直系二郎を食べ続けている発信者。各店ページから動画・投稿にリンクしています。', 'A Japanese creator who has eaten at Ramen Jiro thousands of times. Shop pages link to their videos and posts.')}</p>
      <p class="small">{' · '.join(ext(u, e(host_label(u))) for u in dml.values() if u)}</p>
    </div>
  </div>
</section>"""
    site_ld = ""
    if site.get("base_url") and LANG == "ja":
        # 検索結果のサイト名に使われる（サイトの根のトップページにだけ置く）
        root_url = site["base_url"].rstrip("/") + "/"
        site_ld = jsonld({"@context": "https://schema.org", "@type": "Organization", "name": site["name"], "alternateName": site.get("name_en", ""),
                          "url": root_url, "logo": root_url + "assets/icon-512.png"})
        site_ld += jsonld({"@context": "https://schema.org", "@type": "WebSite", "name": site["name"],
                          "alternateName": [site.get("name_en", ""), "jirolog"], "url": site["base_url"].rstrip("/") + "/",
                          "inLanguage": "ja"})
    return pg, layout(site, pg, title=L("ホーム", "Home"), body=body, page="index", head_extra=site_ld)


def page_stores(site, stores, ctx):
    pg = Page("stores/index.html")
    p = pg.p
    closed = [s for s in stores if s.get("status") == "closed"]
    active = [s for s in stores if s.get("status") != "closed"]
    areas = sorted({area_of(s) for s in active}, key=area_rank)
    opts = "".join(f'<option value="{e(a)}">{e(area_label(a))}</option>' for a in areas)
    groups = []
    for a in areas:
        items = [s for s in active if area_of(s) == a]
        head = f'<a href="{e(area_href(a, p, ctx))}">{e(area_label(a))}</a>' if a in ctx["area_pages"] else e(area_label(a))
        groups.append(f'<section class="area-group" data-area="{e(a)}"><h2>{head} <span class="muted small">{len(items)}</span></h2>'
                      f'<ul class="store-grid">{"".join(store_card(s, p) for s in items)}</ul></section>')
    body = f"""
<h1 class="page-title">{L('直系店舗一覧', 'Ramen Jiro shops')}</h1>
<p>{L(f'直系ラーメン二郎の全 {len([s for s in active if s.get("status") != "upcoming"])} 店（休業中を含む）の営業時間・定休日・アクセスの一覧です。いま営業中・日曜営業・朝営業などで絞り込めます。店名を押すと、メニューや店ごとのルール、近くの直系も見られます。',
         f'All {len([s for s in active if s.get("status") != "upcoming"])} official Ramen Jiro shops with hours, closing days and access. Filter by open now, Sunday hours, morning or late opening, then open a shop for its menu and house rules.')}</p>
<p class="small">{L('条件別の一覧', 'Lists')}: {" · ".join(f'<a href="{p}lists/{k}.html">{e(label(v[1]))}</a>' for k, v in LISTS.items())}</p>
<form class="filters" data-filters onsubmit="return false">
  <label class="f-search"><span class="sr">{L('店名で探す', 'Search')}</span><input type="search" name="q" placeholder="{L('店名・通称・駅で探す', 'Search by shop or station')}" autocomplete="off"></label>
  <label><span class="sr">{L('エリア', 'Area')}</span><select name="area"><option value="">{L('すべてのエリア', 'All areas')}</option>{opts}</select></label>
  <fieldset class="toggles"><legend class="sr">{L('条件', 'Filters')}</legend>
    <label><input type="checkbox" name="open"> {L('いま営業中', 'Open now')}</label>
    <label><input type="checkbox" name="today"> {L('今日営業', 'Open today')}</label>
    <label><input type="checkbox" name="sun"> {L('日曜営業', 'Open Sundays')}</label>
    <label><input type="checkbox" name="morning"> {L('朝（10時台までに開店）', 'Opens before 11:00')}</label>
    <label><input type="checkbox" name="night"> {L('夜（20時以降も営業）', 'Open after 20:00')}</label>
    <label><input type="checkbox" name="unvisited"> {L('未訪問', 'Not visited')}</label>
  </fieldset>
  <p class="small muted" data-result-count></p>
</form>
{''.join(groups)}
<p class="muted small">{L('営業時間は目安です。麺切れ・臨時休業はよくあるので、公式アカウントを確認してから行きましょう。', 'Hours are approximate. Shops often close early when noodles run out, or close for the day without notice — check the official account first.')}</p>
{closed_block(closed, ctx, p, limit=8) if closed else ''}"""
    return pg, layout(site, pg, title=L("ラーメン二郎 直系全店舗一覧（営業時間・定休日）", "All Ramen Jiro shops: hours and closing days"), body=body, page="stores",
                      description=L("直系ラーメン二郎の全店舗一覧。いま営業中・日曜営業・朝営業などで絞り込めます。",
                                    "Every official Ramen Jiro shop, filterable by open now, Sunday hours, morning or late opening."),
                      scripts=["assets/stores.js"])


def page_closed(site, stores, ctx):
    pg = Page("stores/closed.html")
    p = pg.p
    closed = closed_sorted(stores)
    moves = sum(1 for s in closed if s.get("closed_type") in ("move", "rename"))
    intro = L(f"これまでに閉店・移転・店名変更した直系ラーメン二郎の記録です（{len(closed)}店。うち移転・店名変更 {moves}店）。新しい順に並べています。確かな出典がある店だけを載せています。",
              f"Ramen Jiro shops that have closed, moved or been renamed ({len(closed)} shops, {moves} of them moved or renamed), newest first. Only shops with reliable sources are listed.")
    body = f"""
<nav class="crumb" aria-label="{L('パンくず', 'Breadcrumb')}"><a href="{p}index.html">{L('ホーム', 'Home')}</a> › <a href="{p}stores/index.html">{L('店舗', 'Shops')}</a> › {L('閉店・移転した店', 'Closed shops')}</nav>
<h1 class="page-title">{L('閉店・移転した店', 'Closed & relocated shops')}</h1>
<p>{intro}</p>
<p class="muted small">{L('店名を押すと、当時の場所や営業時間、出典が見られます。', 'Open a shop to see where it was, its former hours and sources.')}</p>
{closed_block(closed, ctx, p)}"""
    return pg, layout(site, pg, title=L("閉店・移転した店", "Closed shops"), body=body, page="stores",
                      description=L("閉店・移転・店名変更した直系ラーメン二郎の一覧。営業期間と移転先。",
                                    "Ramen Jiro shops that have closed or moved: when they operated and where they went."))


def page_lineage(site, stores, ctx):
    pg = Page("lineage.html")
    p = pg.p
    nodes, children = ctx["lineage"]
    root = nodes.get("mita")
    title = L("系譜", "Lineage")
    if not root:
        body = f'<h1 class="page-title">{title}</h1><p class="muted">{L("系譜データはまだありません。", "No lineage data yet.")}</p>'
        return pg, layout(site, pg, title=title, body=body, page="lineage")
    known = [n for n in nodes.values() if n["id"] != "mita" and n.get("parent") in nodes]
    unknown = [n for n in nodes.values() if n["id"] != "mita" and n.get("parent") not in nodes]
    order = {s["id"]: i for i, s in enumerate(stores)}
    unknown.sort(key=lambda n: order.get(n["id"], 999))
    direct = len(children.get("mita", []))
    depth = max((len(lineage_chain(n["id"], nodes)) - 1 for n in known), default=0)
    sub_roots = [n for n in unknown if children.get(n["id"])]
    lone = [n for n in unknown if not children.get(n["id"])]
    unk_html = ""
    if sub_roots:
        unk_html += (f'<section class="block tree-wrap"><h2>{L("三田本店までたどれない系統", "Branches we cannot trace back to Mita")}</h2>'
                     f'<p class="small muted">{L("いちばん上の店の修業先が分からないため、別の木として描いています。", "The top shop’s training origin is unknown, so each branch is drawn as its own tree.")}</p>' +
                     "".join(f'<ul class="tree tree-sub">{tree_html(n, ctx, p)}</ul>' for n in sub_roots) + "</section>")
    if lone:
        unk_html += (f'<section class="block"><h2>{L("修業先が分からない店", "Training shop unknown")}</h2>'
                     f'<p class="small muted">{L("確かな出典が見つからなかった店です。", "We found no reliable source for these shops.")}</p><div class="chips">' +
                     "".join(f'<span id="n-{e(n["id"])}">{tree_node(n, ctx, p)}</span>' for n in lone) + "</div></section>")
    body = f"""
<h1 class="page-title">{title}</h1>
<div class="tree-legend small"><span class="node conf-high">{L('出典あり', 'Sourced')}</span><span class="node conf-low">{L('出典が少ない', 'Weakly sourced')}<span class="n-q">?</span></span><span class="node is-closed conf-high">{L('閉店・移転', 'Closed / moved')}</span></div>
<section class="block tree-wrap">
  <ul class="tree">{tree_html(root, ctx, p)}</ul>
</section>
{unk_html}
<p class="muted small">{L('修業先は店や報道、記事で公表されている範囲でまとめています。店と店の関係だけを載せ、個人名は載せていません。出典は各店のページの「系譜」にあります。',
                         'Compiled from what shops, news reports and articles have made public. We record links between shops only, not people’s names. Sources are on each shop page.')}</p>"""
    return pg, layout(site, pg, title=title, body=body, page="lineage",
                      description=L("直系ラーメン二郎の系譜。各店の店主がどの店で修業したかを三田本店からたどる樹形図。",
                                    "The Ramen Jiro family tree: which shop each owner trained at, traced back to the original Mita shop."))


def page_map(site, stores, ctx):
    pg = Page("map.html")
    body = f"""
<h1 class="page-title">{L('地図で探す', 'Map')}</h1>
<div class="map-tools small">
  <label><input type="checkbox" data-map-open> {L('いま営業中だけ', 'Open now only')}</label>
  <button class="btn btn-small" data-locate>{L('現在地から近い順', 'Sort by distance from me')}</button>
  <span class="legend"><i class="dot d-open"></i>{L('営業中', 'Open')} <i class="dot d-soon"></i>{L('まもなく', 'Opening soon')} <i class="dot d-closed"></i>{L('営業時間外', 'Closed now')} <i class="dot d-unk"></i>{L('要確認', 'Check')}</span>
</div>
<div class="map-layout">
  <div id="map" class="map" role="region" aria-label="{L('店舗の地図', 'Map of shops')}"></div>
  <ol class="map-list" data-map-list></ol>
</div>
<p class="muted small">{L('地図: 国土地理院（地理院タイル）。現在地は端末内で距離の計算にだけ使い、どこにも送りません。', 'Map tiles: Geospatial Information Authority of Japan. Your location is used only on your device to sort by distance and is never sent anywhere.')}</p>"""
    return pg, layout(site, pg, title=L("地図", "Map"), body=body, page="map", head_extra=LEAFLET_CSS,
                      description=L("直系ラーメン二郎の地図。営業中の店や現在地から近い店を探せます。", "Map of Ramen Jiro shops — find what is open and what is near you."),
                      scripts=[LEAFLET_JS, "assets/map.js"])


def profile_section(p, a):
    """マイログの「公開プロフィール」（ニックネーム＋合言葉。メールアドレスは使わない）。"""
    return f"""<section class="block" id="profile" data-profile hidden>
  <div class="block-head"><h2>{L('公開プロフィール', 'Public profile')}</h2><a class="small" href="{p}ranking.html">{L('ランキング', 'Ranking')} →</a></div>
  <div data-profile-off>
    <p>{L('ニックネームを決めると、記録を自分の公開ページで見せられます。ランキングにも載り、合言葉で別の端末に引き継げます。メールアドレスは要りません。',
          'Pick a nickname to show your log on your own public page, appear in the ranking, and move your log to other devices with a passphrase. No email needed.')}</p>
    <form class="log-form" data-register>
      <label>{L('ニックネーム（20文字まで）', 'Nickname (up to 20 characters)')}<input name="name" maxlength="20" required placeholder="{L('例: 野猿の民', 'e.g. Jiro Fan')}"></label>
      <label>{L('ID（URL に使う。英小文字・数字・_ で3〜20文字）', 'ID for your page URL (3–20 of a–z, 0–9, _)')}<input name="handle" maxlength="20" required pattern="[A-Za-z0-9_]{{3,20}}" title="{L('英字・数字・_ で3〜20文字', '3–20 letters, digits or _')}" placeholder="{L('例: yaen_tami', 'e.g. jirofan')}" autocapitalize="off" autocomplete="off" spellcheck="false"></label>
      <label class="full check"><input type="checkbox" name="show_dates"> {L('日付まで公開する（オフのときは年月だけ）', 'Show exact dates (otherwise only the month is shown)')}</label>
      <label class="hp" aria-hidden="true">website<input type="text" name="website" tabindex="-1" autocomplete="off"></label>
      <p class="full small muted">{L('公開されるのは、ニックネーム・ID・行った店・年月（または日付）・メニュー・コールです。メモと満足度は公開されません。', 'Public: nickname, ID, shops, month (or date), menu and call. Your notes and ratings stay private.')} <a href="{a}privacy.html">{L('プライバシーポリシー', 'Privacy policy (in Japanese)')}</a></p>
      <div class="full actions"><button class="btn btn-primary" type="submit">{L('公開する', 'Publish')}</button><span class="small muted" data-register-msg></span></div>
    </form>
    <details class="restore">
      <summary>{L('別の端末で公開した記録を引き継ぐ', 'Move a published log to this device')}</summary>
      <form class="log-form" data-restore>
        <label class="full">{L('合言葉', 'Passphrase')}<input name="token" required placeholder="XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX" autocapitalize="characters" autocomplete="off"></label>
        <div class="full actions"><button class="btn" type="submit">{L('引き継ぐ', 'Move here')}</button><span class="small muted" data-restore-msg></span></div>
      </form>
    </details>
  </div>
  <div data-profile-on hidden>
    <div class="token-box" data-token-new hidden>
      <p><strong>{L('合言葉', 'Your passphrase')}</strong>: <code data-token-new-value></code></p>
      <p class="small">{L('別のスマホやパソコンで記録を引き継ぐときに使います。メールアドレスを預かっていないので、なくすと再発行できません。スクリーンショットやメモで必ず控えてください。',
                          'You need this to move your log to another device. We do not keep your email, so it cannot be reissued if lost. Save it now (screenshot or note).')}</p>
      <div class="actions"><button class="btn btn-small" type="button" data-token-copy>{L('コピー', 'Copy')}</button><button class="btn btn-small btn-primary" type="button" data-token-done>{L('控えた', 'Saved it')}</button></div>
    </div>
    <p>{L('公開中', 'Published')}: <a data-profile-link href="#"></a> <span class="small muted" data-sync-status></span></p>
    <div class="actions">
      <a class="btn btn-small" data-profile-open href="#">{L('公開ページを見る', 'View my page')}</a>
      <button class="btn btn-small" type="button" data-profile-copy>{L('リンクをコピー', 'Copy link')}</button>
      <a class="btn btn-small" data-profile-x href="#" target="_blank" rel="noopener">{L('X でシェア', 'Share on X')}</a>
    </div>
    <label class="check"><input type="checkbox" data-show-dates> {L('日付まで公開する（オフのときは年月だけ）', 'Show exact dates (otherwise only the month)')}</label>
    <details class="profile-settings">
      <summary>{L('合言葉・ニックネーム・公開をやめる', 'Passphrase, nickname, unpublish')}</summary>
      <p class="small">{L('合言葉', 'Passphrase')}: <code data-token hidden></code> <button class="btn btn-small" type="button" data-token-show>{L('表示', 'Show')}</button> <button class="btn btn-small" type="button" data-token-copy2>{L('コピー', 'Copy')}</button></p>
      <form class="actions" data-rename><input name="name" maxlength="20" aria-label="{L('ニックネーム', 'Nickname')}"><button class="btn btn-small" type="submit">{L('ニックネームを変える', 'Change nickname')}</button><span class="small muted" data-rename-msg></span></form>
      <div class="actions"><button class="btn btn-small" type="button" data-unlink>{L('この端末とのつながりを外す', 'Disconnect this device')}</button>
        <button class="btn btn-small btn-danger" type="button" data-unpublish>{L('公開をやめる（サーバーから削除）', 'Unpublish (delete from server)')}</button></div>
      <p class="small muted">{L('「つながりを外す」は共用のパソコンなどで使います。公開ページはそのまま残り、合言葉でまたつなげます。どちらを選んでも、このブラウザの記録は残ります。',
                                'Use “Disconnect” on a shared computer: your public page stays and you can reconnect with your passphrase. Either way, the log in this browser stays.')}</p>
    </details>
  </div>
</section>"""


def page_profile(site, stores, ctx):
    pg = Page("u/index.html")
    p = pg.p
    body = f"""
<div data-user-page>
  <p class="muted" data-user-status>{L('読み込み中…', 'Loading…')}</p>
  <div data-user-body hidden>
    <h1 class="page-title"><span data-user-name></span> <span class="muted small" data-user-handle></span></h1>
    <p class="small muted" data-user-since></p>
    <section class="block">
      <h2>{L('制覇状況', 'Progress')}</h2>
      <div class="stats" data-user-stats></div>
      <div class="progress"><div class="bar"><span data-user-bar style="width:0%"></span></div></div>
      <details class="pref-progress"><summary>{L('エリア別', 'By area')}</summary><div data-user-areas></div></details>
    </section>
    <section class="block">
      <h2>{L('行った店', 'Shops visited')}</h2>
      <ul class="chips" data-user-stores></ul>
    </section>
    <section class="block">
      <h2>{L('最近の記録', 'Recent bowls')}</h2>
      <ol class="log-list" data-user-recent></ol>
    </section>
    <p class="small"><a href="{p}log.html#profile">{L('自分の記録も公開する', 'Publish your own log')}</a> · <a href="{p}ranking.html">{L('ランキング', 'Ranking')}</a> · <a data-user-report href="{p}report.html">{L('このページを報告', 'Report this page')}</a></p>
  </div>
</div>"""
    return pg, layout(site, pg, title=L("公開プロフィール", "Public profile"), body=body, page="log", scripts=["assets/profile.js"], noindex=True)


def page_ranking(site, stores, ctx):
    pg = Page("ranking.html")
    p = pg.p
    body = f"""
<h1 class="page-title">{L('二郎ログ ランキング', 'Jiro Log ranking')}</h1>
<p>{L('マイ二郎ログを公開している人の、訪問した直系の店の数と通算杯数のランキングです（上位50人）。店の数には閉店した店も含みます。', 'Ranking of people who publish their Jiro log, by number of shops visited and total bowls (top 50). Closed shops count too.')}</p>
<section class="block">
  <div class="table-scroll"><table class="area-table rank-table">
    <thead><tr><th>{L('順位', 'Rank')}</th><th>{L('ニックネーム', 'Nickname')}</th><th>{L('訪問した店', 'Shops')}</th><th>{L('通算', 'Bowls')}</th></tr></thead>
    <tbody data-ranking><tr><td colspan="4" class="muted">{L('読み込み中…', 'Loading…')}</td></tr></tbody>
  </table></div>
  <p class="small muted" data-ranking-total></p>
</section>
<p><a class="btn btn-primary" href="{p}log.html#profile">{L('自分の記録を公開してランキングに参加する', 'Publish your log and join')}</a></p>"""
    return pg, layout(site, pg, title=L("ランキング", "Ranking"), body=body, page="log", scripts=["assets/profile.js"], noindex=True)


def page_log(site, stores, ctx):
    pg = Page("log.html")
    presets = L(["小ラーメン", "小豚ラーメン", "大ラーメン", "大豚ラーメン", "小ラーメン 麺少なめ", "汁なし", "つけ麺"],
                ["Small ramen", "Small ramen + extra pork", "Large ramen", "Large ramen + extra pork", "Small ramen, less noodles", "Shiru-nashi", "Tsukemen"])
    p = pg.p
    body = f"""
<h1 class="page-title">{L('マイ二郎ログ', 'My Jiro log')}</h1>
<p>{L('食べた一杯を記録します。記録はこのブラウザに保存されます。下の「公開プロフィール」を使うと、記録を公開ページで見せたり、ランキングに参加したり、別の端末に引き継いだりできます。',
       'Keep a record of every bowl. Your log is saved in this browser. With a public profile (below) you can show it on your own page, join the ranking and move it to another device.')}</p>

<section class="block">
  <h2>{L('制覇状況', 'Progress')}</h2>
  <div class="stats" data-stats></div>
  <div class="progress"><div class="bar"><span data-bar style="width:0%"></span></div></div>
  <details class="pref-progress"><summary>{L('エリア別', 'By area')}</summary><div data-area-progress></div></details>
</section>

<section class="block">
  <h2>{L('記録する', 'Add a visit')}</h2>
  <form class="log-form" data-log-form>
    <label>{L('店', 'Shop')}<select name="store" required></select></label>
    <label>{L('日付', 'Date')}<input type="date" name="date" required></label>
    <label>{L('メニュー', 'What you ordered')}<select name="pick"></select></label>
    <label data-free hidden>{L('メニュー（自由入力）', 'Your order')}<input type="text" name="menu" placeholder="{e(presets[0])}" list="menu-presets"></label>
    <datalist id="menu-presets">{''.join(f'<option value="{e(x)}">' for x in presets)}</datalist>
    <fieldset class="full addons" data-addons hidden><legend>{L('追加・トッピング', 'Add-ons & toppings')}</legend><div class="toggles" data-addon-list></div></fieldset>
    <p class="full small muted" data-total></p>
    <label>{L('コール', 'Call (toppings)')}<input type="text" name="call" placeholder="{L('ヤサイニンニクアブラ', 'yasai ninniku abura')}"></label>
    <label>{L('満足度', 'Rating')}<select name="rating"><option value="">—</option><option>5</option><option>4</option><option>3</option><option>2</option><option>1</option></select></label>
    <label class="full">{L('メモ', 'Notes')}<textarea name="memo" rows="2" placeholder="{L('乳化具合、豚、並び時間など', 'Soup, pork, how long you queued…')}"></textarea></label>
    <div class="full actions"><button class="btn btn-primary" type="submit">{L('記録する', 'Save')}</button><span class="small muted" data-log-msg></span></div>
  </form>
</section>

<section class="block">
  <div class="block-head"><h2>{L('記録一覧', 'Your visits')}</h2><span class="small muted" data-log-count></span></div>
  <ol class="log-list" data-log-list></ol>
</section>

<section class="block">
  <h2>{L('未訪問の店', 'Not visited yet')}</h2>
  <ul class="chips" data-unvisited></ul>
</section>

{profile_section(p, pg.a)}

<section class="block">
  <h2>{L('バックアップ', 'Backup')}</h2>
  <div class="actions">
    <button class="btn" data-export>{L('JSON で書き出す', 'Export JSON')}</button>
    <label class="btn">{L('JSON を読み込む', 'Import JSON')}<input type="file" accept="application/json" data-import hidden></label>
    <button class="btn btn-danger" data-clear>{L('すべて消す', 'Delete all')}</button>
  </div>
  <p class="muted small">{L('日本語版と英語版で同じ記録を使います。', 'The Japanese and English pages share the same log.')}</p>
</section>"""
    return pg, layout(site, pg, title=L("マイ二郎ログ", "My Jiro log"), body=body, page="log", scripts=["assets/log.js", "assets/account.js"],
                      description=L("食べた直系ラーメン二郎を記録して全店制覇を目指すログ。", "Log your Ramen Jiro visits and work toward visiting every shop."))


def page_news(site, stores, ctx):
    pg = Page("news.html")
    p = pg.p
    items = ctx["news"]
    news_html = ('<ul class="news-list">' + "".join(news_item(n, ctx, p) for n in items) + "</ul>") if items else f"<p class=muted>{L('まだありません', 'Nothing yet')}</p>"
    body = f"""
<h1 class="page-title">{L('ニュース', 'News')}</h1>
<p class="muted small">{L('直系二郎の開店・閉店・移転・休業のできごと。日付と出典が確かなものだけ載せています。', 'Openings, closings, moves and long breaks. Only items with a firm date and source are listed.')}</p>
<div class="block">{news_html}</div>"""
    return pg, layout(site, pg, title=L("ニュース", "News"), body=body, page="news",
                      description=L("直系ラーメン二郎の開店・閉店・移転・休業ニュース。", "Ramen Jiro openings, closings and moves."))


def content_file(name):
    if LANG == "en" and (CONTENT / "en" / name).exists():
        return (CONTENT / "en" / name).read_text(encoding="utf-8")
    return (CONTENT / name).read_text(encoding="utf-8")


def page_md(site, stores, ctx, key, title, desc, md_name, ja_only=False):
    pg = Page(f"{key}.html")
    return pg, layout(site, pg, title=title, body=f'<article class="prose">{markdown(content_file(md_name))}</article>', page=key, description=desc,
                      ja_only=ja_only)


REPORT_KINDS = [("typo", "誤植・表記の誤り", "Typo or wording"), ("hours", "営業時間・定休日", "Hours or closing days"),
                ("menu", "メニュー・価格", "Menu or prices"), ("status", "閉店・移転・休業・再開", "Closed, moved, paused or reopened"),
                ("access", "住所・アクセス・地図", "Address, access or map"), ("lineage", "系譜", "Lineage"),
                ("english", "英語の表記", "English wording"),
                ("profile", "公開プロフィール（不適切な名前など）", "Public profile (e.g. offensive name)"), ("other", "その他", "Other")]


def page_report(site, stores, ctx):
    pg = Page("report.html")
    endpoint = site.get("report_endpoint") or ""
    opts = "".join(f'<option value="{e(s["id"])}">{e(short_name(s))}{L("（閉店）", " (closed)") if s.get("status") == "closed" else ""}</option>' for s in stores)
    kinds = "".join(f'<option value="{k}">{e(L(ja, en))}</option>' for k, ja, en in REPORT_KINDS)
    send = (f'<button class="btn btn-primary" type="submit">{L("送信する", "Send")}</button>' if endpoint else "")
    how = (L("「送信する」でサイト運営者に届きます。", "Press Send and it goes to the site owner.") if endpoint else
           L("下の「報告文」をコピーして、サイト運営者に送ってください。", "Copy the report below and send it to the site owner."))
    body = f"""
<h1 class="page-title">{L('誤りを報告', 'Report a mistake')}</h1>
<p>{L('誤植や、営業時間・価格などの情報の誤りを見つけたら教えてください。分かる範囲で大丈夫です。', 'Found a typo or wrong information (hours, prices…)? Let us know — fill in whatever you can.')} {how}</p>
<section class="block">
  <form class="log-form report-form" data-report-form data-endpoint="{e(endpoint)}">
    <label>{L('店', 'Shop')}<select name="store"><option value="">{L('（店以外のページ）', '(not about a shop)')}</option>{opts}</select></label>
    <label>{L('種類', 'Type')}<select name="kind" required>{kinds}</select></label>
    <label class="full">{L('ページ', 'Page')}<input type="text" name="page" placeholder="stores/mita.html"></label>
    <label class="full">{L('いまの表記（間違っているところ）', 'What it says now')}<textarea name="current" rows="2" required></textarea></label>
    <label class="full">{L('正しい内容', 'What it should say')}<textarea name="correct" rows="2" required></textarea></label>
    <label class="hp" aria-hidden="true">website<input type="text" name="website" tabindex="-1" autocomplete="off"></label>
    <label class="full">{L('情報源（URL・日付）', 'Source (URL and date)')}<input type="text" name="source" placeholder="{L('例: 公式X 2026-10-01 の告知', 'e.g. official X post, 2026-10-01')}"></label>
    <div class="full actions">{send}<button class="btn" type="button" data-copy>{L('報告文をコピー', 'Copy report')}</button><span class="small muted" data-report-msg></span></div>
  </form>
</section>
<section class="block">
  <h2>{L('報告文', 'Report')}</h2>
  <pre class="report-preview" data-report-preview></pre>
</section>"""
    return pg, layout(site, pg, title=L("誤りを報告", "Report a mistake"), body=body, page="report", scripts=["assets/report.js"],
                      description=L("二郎ログの誤植・情報の誤りを報告するフォーム。", "Report a typo or wrong information on Jiro Log."))


def page_about(site, stores, ctx):
    pg = Page("about.html")
    dm = ctx["daisukiman"]
    prof = dm.get("profile") or {}
    if LANG == "en":
        facts_src = (TR.get("daisukiman") or {}).get("facts") or []
        tips_src = (TR.get("daisukiman") or {}).get("tips") or []
    else:
        facts_src, tips_src = prof.get("facts") or [], dm.get("tips") or []
    facts = "".join(f"<li>{e(f['text'])}{src_link(f.get('source'))}{date_span(f.get('date'))}</li>" for f in facts_src)
    tips = "".join(f"<li>{e(t['text'])}{src_link(t.get('source'))}</li>" for t in tips_src)
    n_articles = sum(1 for a in ctx["articles"] if a.get("store_id"))
    counts = L(f"収録: ラーメンシーンの記事 {n_articles} 本、直系二郎大好きマンの動画 {len(ctx['videos'])} 本・投稿 {len(dm.get('posts', []))} 件へのリンク。",
               f"Indexed: {n_articles} Ramen Scene articles, {len(ctx['videos'])} videos and {len(dm.get('posts', []))} posts by Chokkei Jiro Daisuki Man.")
    extra = f"""
<h2>{L('直系二郎大好きマンについて（公開プロフィールより）', 'About Chokkei Jiro Daisuki Man (from their public profile)')}</h2>
<ul>{facts or f'<li class=muted>{L("未収録", "Not yet added")}</li>'}</ul>
{f'<h3>{L("本人が語っている楽しみ方", "Their tips")}</h3><ul>{tips}</ul>' if tips else ''}
<p class="small">{counts}</p>"""
    return pg, layout(site, pg, title=L("このサイトについて", "About"),
                      body=f'<article class="prose">{markdown(content_file("about.md"))}{extra}</article>', page="about",
                      description=L("二郎ログの情報源・方針・免責事項。", "Sources, policies and disclaimer for Jiro Log."))


# ---------------------------------------------------------------- 簡易 Markdown

def inline(s):
    s = e(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    s = re.sub(r"\[(.+?)\]\((.+?)\)", lambda m: f'<a href="{m.group(2)}"' + (' rel="noopener" target="_blank"' if m.group(2).startswith("http") else "") + f">{m.group(1)}</a>", s)
    return s


def term_id(term):
    return re.sub(r"[\s*（）()？?]+", "", term.split(" / ")[0])


def markdown(src):
    """見出し・段落・箇条書き・番号リスト・定義リスト（「用語 :: 説明」）・引用だけ対応。"""
    out, para, lst = [], [], None

    def end_para():
        nonlocal para
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>")
            para = []

    def flush():
        nonlocal lst
        end_para()
        if lst:
            tag, items = lst
            if tag == "dl":
                out.append('<dl class="terms">' + "".join(f'<div id="{e(term_id(k))}"><dt>{inline(k)}</dt><dd>{inline(v)}</dd></div>' for k, v in items) + "</dl>")
            else:
                out.append(f"<{tag}>" + "".join(f"<li>{inline(i)}</li>" for i in items) + f"</{tag}>")
            lst = None

    for line in src.splitlines():
        s = line.rstrip()
        if not s.strip():
            flush()
            continue
        m = re.match(r"^(#{1,3})\s+(.*)$", s)
        if m:
            flush()
            lvl, text = len(m.group(1)), m.group(2)
            anchor = re.sub(r"\s+", "-", text)
            out.append(f'<h{lvl} id="{e(anchor)}">{inline(text)}</h{lvl}>')
            continue
        m = re.match(r"^\s*[-*]\s+(.*)$", s)
        n = re.match(r"^\s*\d+\.\s+(.*)$", s)
        d = re.match(r"^(.+?)\s::\s(.+)$", s)
        kind, val = (("ul", m.group(1)) if m else ("ol", n.group(1)) if n else ("dl", (d.group(1), d.group(2))) if d else (None, None))
        if kind:
            end_para()
            if not lst or lst[0] != kind:
                flush()
                lst = (kind, [])
            lst[1].append(val)
            continue
        if s.startswith("> "):
            flush()
            out.append('<p class="callout">' + inline(s[2:]) + "</p>")
            continue
        if lst:
            flush()
        para.append(s.strip())
    flush()
    return "\n".join(out)


# ---------------------------------------------------------------- フィード（scripts/fetch_feeds.py が作る data/feeds.json）

def merge_feeds(ctx, feeds):
    """フィードの新着を、手作業の索引（ramenscene.json / daisukiman.json）に足す。URL が同じものは索引を優先。"""
    exclude = ctx.get("feed_exclude") or []
    feeds = {k: [x for x in v if not any(w in x.get("title", "") for w in exclude)] if isinstance(v, list) else v
             for k, v in feeds.items()}
    known = {a["url"].rstrip("/") for a in ctx["articles"]}
    for it in feeds.get("ramenscene", []):
        if it["url"].rstrip("/") not in known:
            ctx["articles"].append({"url": it["url"], "title": it["title"], "date": it.get("date"),
                                    "store_id": (it.get("store_ids") or [None])[0], "kind": "jiro" if it.get("store_ids") else "other"})
    known_v = {youtube_id(v["url"]) for v in ctx["videos"]}
    for it in feeds.get("youtube", []):
        if youtube_id(it["url"]) not in known_v:
            ctx["videos"].append({"url": it["url"], "title": it["title"], "date": it.get("date"), "store_ids": it.get("store_ids") or []})
    feed = ([dict(x, kind="article", source=L("ラーメンシーン", "Ramen Scene")) for x in feeds.get("ramenscene", [])] +
            [dict(x, kind="video", source="YouTube") for x in feeds.get("youtube", [])])
    feed.sort(key=lambda x: x.get("date") or "", reverse=True)
    return feed


# ---------------------------------------------------------------- 書き出し

TAKEOUT_RE = re.compile(r"持ち帰り|テイクアウト|お土産|豚一本")
ADDON_RE = re.compile(r"変更|追加|増し|増券|トッピング|たまご|玉子|卵|味玉|うずら|ネギ|ねぎ|キムチ|生姜|しょうが|ショウガ|チーズ|マヨ|ニラ|海苔|のり|ライス|ドリンク|飲料")


def menu_kind(name, price):
    """記録フォーム用の分類: main（ラーメン類）/ add（追加券・トッピング）/ take（持ち帰り）"""
    if TAKEOUT_RE.search(name):
        return "take"
    if "変更" in name or "追加" in name:
        return "add"
    if "ラーメン" in name or "つけ麺" in name or "汁なし" in name or "そば" in name or re.match(r"^(小|大|少なめ|ミニ|麺)", name):
        return "main"
    if ADDON_RE.search(name):
        return "add"
    return "add" if isinstance(price, int) and price < 300 else "main"


def js_store(s, geo):
    global LANG
    g = geo.get(s["id"]) or {}
    out = {"id": s["id"], "pref": s.get("prefecture"), "area": area_of(s), "status": s.get("status", "open"),
           "hours": s.get("hours") or {}, "lat": g.get("lat"), "lng": g.get("lng")}
    menu = live_menu(s)
    out["menu"] = [{"n": m["name"], "p": m.get("price") if isinstance(m.get("price"), int) else None,
                    "k": menu_kind(m["name"], m.get("price"))} for m in menu]
    for lang in ("ja", "en"):
        LANG = lang
        sfx = "" if lang == "ja" else "_en"
        if lang == "en":
            for item, m in zip(out["menu"], menu):
                item["e"] = menu_name(s, m)
        out["name" + sfx] = short_name(s)
        out["nick" + sfx] = sv(s, "nickname")
        out["area_label" + sfx] = area_label(area_of(s))
        out["access" + sfx] = (sv(s, "access") or [])[:1]
        out["closed_text" + sfx] = closed_days(s)
    LANG = "ja"
    return out


def main():
    global LANG, TR
    stores = load("stores.json", [])
    problems = validate.check_stores(stores)
    for msg in problems:
        print("  warn:", msg)
    TR = load("en.json", {}) or {}
    missing_en = [s["id"] for s in stores if s["id"] not in (TR.get("stores") or {})]
    if missing_en:
        print(f"  note: 英訳のない店 {len(missing_en)} 件（日本語で表示）: {' '.join(missing_en[:10])}{' …' if len(missing_en) > 10 else ''}")

    geo = load("geo.json", {})
    holidays = load("holidays.json", {})
    feeds = load("feeds.json", {}) or {}
    rs = load("ramenscene.json", {"articles": []})
    dm = load("daisukiman.json", {}) or {}
    ctx = {
        "geo": geo,
        "news": sorted(load("news.json", []), key=lambda n: n.get("date") or "", reverse=True),
        "ramenscene": rs,
        "daisukiman": dm,
        "articles": list(rs.get("articles", [])),
        "videos": list(dm.get("videos", [])),
        "stores": stores,
        "by_id": {s["id"]: s for s in stores},
        "lineage": lineage_index(load("lineage.json", {}) or {}, stores),
        "feed_fetched": feeds.get("fetched"),
        "today": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date(),
        "near": nearest(stores, geo),
        "area_pages": area_pages(stores),
    }
    site = load("site.json")
    ctx["feed_exclude"] = site.get("feed_exclude") or []
    site["_updated"] = max([s.get("checked") or "" for s in stores] + [""]) or dt.date.today().isoformat()

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    shutil.copytree(STATIC, DIST / "assets")
    payload = {"stores": [js_store(s, geo) for s in stores], "holidays": holidays, "updated": site["_updated"]}
    (DIST / "assets" / "data.js").write_text(
        "window.JIRO=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")

    written = []
    lastmod = {}
    for lang in ("ja", "en"):
        LANG = lang
        # 店舗ページなどで使う索引にもフィード分を足す（言語に依存しない）
        base = dict(ctx)
        base["articles"], base["videos"] = list(ctx["articles"]), list(ctx["videos"])
        merge_feeds(base, feeds)
        jobs = [(page_index,), (page_stores,), (page_closed,), (page_lineage,), (page_map,), (page_log,), (page_news,), (page_about,), (page_report,),
                (page_profile,), (page_ranking,),
                (page_md, "guide", L("はじめての二郎", "How to order at Ramen Jiro"),
                 L("初めて直系ラーメン二郎に行く人向けの、食券からコール、食べ終わりまでの流れ。", "A step-by-step guide to your first Ramen Jiro: tickets, the topping call, and etiquette."), "guide.md"),
                (page_md, "glossary", L("二郎用語集", "Jiro glossary"),
                 L("ニンニク・ヤサイ・アブラ・カラメ、ロット、宣告など二郎でよく使う言葉。", "What ninniku, yasai, abura, karame, lot and other Jiro words mean."), "glossary.md")]
        if lang == "ja":   # プライバシーポリシーは日本語版だけ
            jobs.append((page_md, "privacy", "プライバシーポリシー", "二郎ログの広告・Cookie・外部サービスへの送信・お問い合わせについて。", "privacy.md", True))
        pages = [fn(site, stores, base, *args) for fn, *args in jobs]
        pages += [page_store(site, s, base) for s in stores]
        pages += [page_area(site, stores, base, a, slug) for a, slug in base["area_pages"].items()]
        pages += [page_list(site, stores, base, key) for key in LISTS]
        for pg, text in pages:
            out = DIST / pg.out
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(prettify_links(text), encoding="utf-8")
            written.append(pg.out)
            lastmod[pg.out] = next((s.get("checked") for s in stores if pg.path == f"stores/{s['id']}.html" and s.get("checked")), None)
        out404 = DIST / ("404.html" if lang == "ja" else "en/404.html")
        out404.write_text(prettify_links(page_404(site, stores, base)), encoding="utf-8")
    LANG = "ja"

    # 公開プロフィールの集計で使う店 id の一覧（report-worker が読む。閉店した店も含む）
    (DIST / "store-ids.json").write_text(json.dumps({"ids": [s["id"] for s in stores]}, separators=(",", ":")), encoding="utf-8")

    if site.get("indexnow_key"):
        # IndexNow（Bing など）に更新を知らせるときの確認用ファイル
        (DIST / f"{site['indexnow_key']}.txt").write_text(site["indexnow_key"], encoding="utf-8")

    if site.get("base_url"):
        b = site["base_url"].rstrip("/")
        today = TODAY.isoformat()
        noindex = {"u/index.html", "ranking.html", "en/u/index.html", "en/ranking.html"}
        urls = "".join(f"<url><loc>{e(b + '/' + pretty(path))}</loc><lastmod>{lastmod.get(path) or today}</lastmod></url>" for path in written if path not in noindex)
        (DIST / "sitemap.xml").write_text(
            f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n', encoding="utf-8")
        (DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {b}/sitemap.xml\n", encoding="utf-8")
    if site.get("adsense_client"):
        pub = site["adsense_client"].removeprefix("ca-")
        (DIST / "ads.txt").write_text(f"google.com, {pub}, DIRECT, f08c47fec0942fa0\n", encoding="utf-8")

    print(f"built {len(written)} pages ({len(stores)} stores × ja/en), {len(problems)} warnings -> {DIST}")


if __name__ == "__main__":
    main()
