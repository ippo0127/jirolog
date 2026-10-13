// 二郎ログの中継（Cloudflare Workers）
//   POST /                 誤りの報告を、非公開リポジトリの GitHub Issue（ラベル: report）にする
//   POST /view             来訪数を1つ増やして返す（D1 を使う。個人の情報は保存しない）
//   /api/...               公開プロフィール（ニックネーム＋合言葉。メールアドレスは預からない）
//     POST   /api/register   {handle, name, show_dates} → {handle, name, token}（合言葉はこのときだけ返す）
//     GET    /api/user?h=    公開ページ用（店・メニュー・コールと、年月か日付。メモ・満足度は返さない）
//     GET    /api/ranking    訪問店数・杯数のランキング
//     GET    /api/me/log     本人の記録（引き継ぎ用。Authorization: Bearer 合言葉）
//     PUT    /api/me/log     {entries, deleted} 端末の記録をサーバーの記録と合わせて保存し、合わせた結果を返す
//     GET    /api/me         本人の設定（ニックネーム・日付を公開するか）
//     PATCH  /api/me         {name, show_dates} ニックネームや設定を変える
//     DELETE /api/me         公開をやめる（サーバーから全部消す）
//
// 設定（Cloudflare のダッシュボード → Workers → この Worker → Settings）
//   GITHUB_REPO      報告用の非公開リポジトリ。例: yourname/jirolog-reports
//   GITHUB_TOKEN     その1リポジトリの Issues: Read and write だけを許可した fine-grained token（Secret として登録）
//   ALLOWED_ORIGINS  例: https://jirolog.pages.dev  （カンマ区切りで複数可）
//   DB               D1 データベースのバインディング（来訪数と公開プロフィール。表は自動で作る）
//
// 運営の操作（D1 の Console で実行）
//   不適切な名前を隠す:   UPDATE users SET hidden = 1 WHERE handle = 'xxx';
//   元に戻す:             UPDATE users SET hidden = 0 WHERE handle = 'xxx';
//   消す:                 DELETE FROM users WHERE handle = 'xxx';

const KINDS = {
  typo: "誤植・表記の誤り", hours: "営業時間・定休日", menu: "メニュー・価格", status: "閉店・移転・休業・再開",
  access: "住所・アクセス・地図", lineage: "系譜", english: "英語の表記", profile: "公開プロフィール（不適切な名前など）", other: "その他",
};

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const origin = req.headers.get("Origin") || "";
    const allowed = (env.ALLOWED_ORIGINS || "").split(",").map((s) => s.trim()).filter(Boolean);
    const cors = {
      "Access-Control-Allow-Origin": allowed.includes(origin) ? origin : allowed[0] || "",
      "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Accept, Authorization",
      "Access-Control-Max-Age": "86400",
      Vary: "Origin",
    };
    const json = (obj, status = 200) => new Response(JSON.stringify(obj), {
      status, headers: { ...cors, "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
    });

    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    if (!allowed.includes(origin)) return json({ error: "origin" }, 403);
    if (url.pathname.startsWith("/api/")) {
      try {
        return await api(req, env, url, json);
      } catch (_) {
        return json({ error: "server" }, 500);
      }
    }
    if (req.method !== "POST") return json({ error: "method" }, 405);
    if (url.pathname === "/view") return countView(req, env, json);
    return report(req, env, json);
  },
};

// ---------------------------------------------------------------- 誤りの報告
async function report(req, env, json) {
  let form;
  try { form = await req.formData(); } catch (_) { return json({ error: "format" }, 400); }
  if (form.get("website")) return json({ ok: true }); // ボット除けの隠し欄に入力があれば捨てる

  const get = (k, max) => String(form.get(k) || "").replace(/\r/g, "").slice(0, max).trim();
  const store = get("store", 40).replace(/[^a-z0-9_-]/g, "");
  const kind = KINDS[get("kind", 20)] ? get("kind", 20) : "other";
  const page = get("page", 200);
  const current = get("current", 2000);
  const correct = get("correct", 2000);
  const source = get("source", 500);
  if (!current || !correct) return json({ error: "missing" }, 400);

  // 報告文は外から来た文なので、Markdown として解釈されないようコードブロックに入れる
  const fence = (s) => "```text\n" + (s || "-").replace(/```/g, "ˋˋˋ") + "\n```";
  const body = [
    "<!-- jirolog-report v1 -->",
    `- 店: \`${store || "-"}\``,
    `- ページ: \`${page.replace(/`/g, "") || "-"}\``,
    `- 種類: ${KINDS[kind]} (\`${kind}\`)`,
    "", "**いまの表記**", fence(current),
    "", "**正しい内容**", fence(correct),
    "", "**情報源**", fence(source),
    "", "_サイトの報告フォームから自動で作成。内容は未確認の報告です。_",
  ].join("\n");
  const title = `[報告] ${store || page || "サイト全体"}: ${KINDS[kind]}`.slice(0, 120);

  const res = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/issues`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "jirolog-report-worker",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ title, body, labels: ["report"] }),
  });
  if (!res.ok) return json({ error: "github", status: res.status }, 502);
  return json({ ok: true });
}

// ---------------------------------------------------------------- 来訪数
async function countView(req, env, json) {
  if (!env.DB) return json({ error: "no-db" }, 503);
  let path = "";
  try { path = String((await req.json()).path || ""); } catch (_) { return json({ error: "format" }, 400); }
  path = path.replace(/\/index(\.html)?$/, "/").replace(/\.html$/, "");
  if (!/^\/[A-Za-z0-9_\-\/]{0,120}$/.test(path)) return json({ error: "path" }, 400);
  await env.DB.prepare("CREATE TABLE IF NOT EXISTS views (path TEXT PRIMARY KEY, n INTEGER NOT NULL DEFAULT 0)").run();
  const up = "INSERT INTO views (path, n) VALUES (?1, 1) ON CONFLICT(path) DO UPDATE SET n = n + 1 RETURNING n";
  const [page, total] = await env.DB.batch([env.DB.prepare(up).bind(path), env.DB.prepare(up).bind("*")]);
  return json({ page: page.results[0].n, total: total.results[0].n });
}

// ---------------------------------------------------------------- 公開プロフィール
const MAX_ENTRIES = 5000;
const MAX_DELETED = 5000;
const MAX_BODY = 1500000;
const TOKEN_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"; // 読み間違えやすい I・O・0・1 を使わない
const TOKEN_LEN = 28; // 140 bit
const RESERVED = new Set(["admin", "root", "api", "jirolog", "jiro", "ramenjiro", "official", "staff", "support", "owner",
  "mod", "moderator", "system", "null", "undefined", "me", "u", "ranking", "help", "info", "test"]);
// 名前に使えない言葉（なりすまし・不適切な言葉）。比べるときは小文字・全角半角をそろえ、空白と記号を取り除く
const NG_WORDS = ["死ね", "しね", "氏ね", "殺す", "ころす", "糞", "くそ", "うんこ", "ちんこ", "ちんぽ", "まんこ", "せっくす", "セックス",
  "sex", "fuck", "shit", "bitch", "porn", "nigger", "レイプ", "エロ", "やくざ", "ヤクザ", "在日", "チョン", "ガイジ", "害児",
  "きちがい", "キチガイ", "気違い", "運営", "公式", "管理人", "店主", "総帥", "二郎ログ", "jirolog", "admin"];
const URLISH = /https?:|www\.|\.(com|net|org|jp|io|dev|app|me)\b|@/i;

let schemaReady = false;
async function ensureSchema(env) {
  if (schemaReady) return;
  await env.DB.batch([
    env.DB.prepare(`CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      handle TEXT NOT NULL UNIQUE,
      name TEXT NOT NULL,
      token_hash TEXT NOT NULL UNIQUE,
      created TEXT NOT NULL,
      updated TEXT NOT NULL,
      last_sync INTEGER NOT NULL DEFAULT 0,
      hidden INTEGER NOT NULL DEFAULT 0,
      show_dates INTEGER NOT NULL DEFAULT 0,
      shops INTEGER NOT NULL DEFAULT 0,
      bowls INTEGER NOT NULL DEFAULT 0,
      log TEXT NOT NULL DEFAULT '[]',
      rev INTEGER NOT NULL DEFAULT 0
    )`),
    env.DB.prepare("CREATE INDEX IF NOT EXISTS users_rank ON users (hidden, shops DESC, bowls DESC)"),
  ]);
  schemaReady = true;
}

async function api(req, env, url, json) {
  if (!env.DB) return json({ error: "no-db" }, 503);
  await ensureSchema(env);
  const path = url.pathname, method = req.method;
  if (path === "/api/register" && method === "POST") return register(req, env, json);
  if (path === "/api/user" && method === "GET") return publicUser(url, env, json);
  if (path === "/api/ranking" && method === "GET") return ranking(env, json);
  if (path === "/api/me" || path === "/api/me/log") {
    const me = await auth(req, env);
    if (!me) return json({ error: "auth" }, 401);
    if (path === "/api/me/log" && method === "GET") return getLog(me, env, json);
    if (path === "/api/me/log" && method === "PUT") return putLog(req, me, env, json);
    if (path === "/api/me" && method === "GET") return json({ handle: me.handle, name: me.name, show_dates: !!me.show_dates });
    if (path === "/api/me" && method === "PATCH") return updateMe(req, me, env, json);
    if (path === "/api/me" && method === "DELETE") return removeMe(me, env, json);
  }
  return json({ error: "not-found" }, 404);
}

const nowIso = () => new Date().toISOString();

async function readBody(req) {
  const text = await req.text();
  if (text.length > MAX_BODY) return { error: "too-large" };
  try { return { body: JSON.parse(text) }; } catch (_) { return { error: "format" }; }
}

async function sha256(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function newToken() {
  const bytes = crypto.getRandomValues(new Uint8Array(TOKEN_LEN));
  return [...bytes].map((b) => TOKEN_ALPHABET[b & 31]).join("");
}

const normToken = (s) => String(s || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
const formatToken = (t) => t.match(/.{1,4}/g).join("-");

function normName(s) {
  // 制御文字・幅のない文字・方向制御文字を取り除き、空白を1つにまとめる
  return String(s || "").normalize("NFKC").replace(/[\u0000-\u001f\u007f\u200b-\u200f\u2028-\u202e\u2066-\u2069\ufeff]/g, "").replace(/\s+/g, " ").trim();
}

function badWord(s) {
  const t = String(s).normalize("NFKC").toLowerCase().replace(/[\s_\-・.。、,，!！?？~〜ー]/g, "");
  return NG_WORDS.some((w) => t.includes(w.toLowerCase()));
}

const validHandle = (h) => /^[a-z0-9_]{3,20}$/.test(h) && !RESERVED.has(h) && !badWord(h);
const validName = (n) => n.length > 0 && [...n].length <= 20 && !badWord(n) && !URLISH.test(n);

async function auth(req, env) {
  const m = (req.headers.get("Authorization") || "").match(/^Bearer\s+(.+)$/i);
  if (!m) return null;
  const token = normToken(m[1]);
  if (token.length !== TOKEN_LEN) return null;
  return env.DB.prepare("SELECT id, handle, name, last_sync, show_dates FROM users WHERE token_hash = ?1").bind(await sha256(token)).first();
}

async function register(req, env, json) {
  const { body, error } = await readBody(req);
  if (error || !body || typeof body !== "object") return json({ error: error || "format" }, 400);
  if (body.website) return json({ error: "format" }, 400); // ボット除け
  const handle = String(body.handle || "").trim().toLowerCase();
  const name = normName(body.name);
  if (!validHandle(handle)) return json({ error: "handle" }, 400);
  if (!validName(name)) return json({ error: "name" }, 400);
  // 大量登録よけ：1時間に100件まで
  const recent = await env.DB.prepare("SELECT COUNT(*) AS n FROM users WHERE created > ?1")
    .bind(new Date(Date.now() - 3600e3).toISOString()).first();
  if (recent && recent.n >= 100) return json({ error: "busy" }, 429);
  const token = newToken();
  const now = nowIso();
  const showDates = body.show_dates === true ? 1 : 0;
  try {
    await env.DB.prepare("INSERT INTO users (handle, name, token_hash, created, updated, show_dates) VALUES (?1, ?2, ?3, ?4, ?4, ?5)")
      .bind(handle, name, await sha256(token), now, showDates).run();
  } catch (err) {
    if (String(err && err.message || err).includes("UNIQUE")) return json({ error: "taken" }, 409);
    throw err;
  }
  return json({ handle, name, show_dates: !!showDates, token: formatToken(token) });
}

function cleanEntry(e) {
  if (!e || typeof e !== "object") return null;
  const id = String(e.id || ""), store = String(e.store || ""), date = String(e.date || "");
  if (!/^[A-Za-z0-9_-]{1,40}$/.test(id) || !/^[a-z0-9_]{1,40}$/.test(store) || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return null;
  const str = (v, n) => (typeof v === "string" ? v.slice(0, n) : "");
  const items = Array.isArray(e.items) ? e.items.filter((x) => typeof x === "string").slice(0, 10).map((x) => x.slice(0, 80)) : null;
  return {
    id, store, date,
    menu: str(e.menu, 120),
    items: items && items.length ? items : null,
    price: Number.isInteger(e.price) && e.price >= 0 && e.price < 100000 ? e.price : null,
    call: str(e.call, 80),
    rating: Number.isInteger(e.rating) && e.rating >= 1 && e.rating <= 5 ? e.rating : null,
    memo: str(e.memo, 500),
    created: str(e.created, 40),
  };
}

// 保存の形: {"entries":[...], "deleted":[どこかの端末で消した記録の id]}
function parseLog(text) {
  try {
    const v = JSON.parse(text);
    if (Array.isArray(v)) return { entries: v, deleted: [] };
    if (v && Array.isArray(v.entries)) return { entries: v.entries, deleted: Array.isArray(v.deleted) ? v.deleted : [] };
  } catch (_) { /* 空のまま */ }
  return { entries: [], deleted: [] };
}

const validId = (id) => typeof id === "string" && /^[A-Za-z0-9_-]{1,40}$/.test(id);

// 集計（ランキング・公開ページ）に使うのは、サイトにある店で、日付がありえる記録だけ。
// 店 id の一覧はサイトの /store-ids.json から読み、1時間ごとに読み直す（読めなければ前の一覧、それもなければ確かめない）
let storeCache = { at: 0, ids: null };
async function storeIds(env) {
  if (storeCache.ids && Date.now() - storeCache.at < 3600e3) return storeCache.ids;
  const site = (env.ALLOWED_ORIGINS || "").split(",")[0].trim();
  try {
    const r = await fetch(`${site}/store-ids.json`, { cf: { cacheTtl: 3600 } });
    const v = r.ok ? await r.json() : null;
    if (v && Array.isArray(v.ids) && v.ids.length) storeCache = { at: Date.now(), ids: new Set(v.ids) };
  } catch (_) { /* 前の一覧を使う */ }
  return storeCache.ids;
}
function countable(e, ids) {
  const tomorrow = new Date(Date.now() + 33 * 3600e3).toISOString().slice(0, 10); // 日本時間の明日
  return (!ids || ids.has(e.store)) && e.date >= "1968-01-01" && e.date <= tomorrow;
}
const newestFirst = (a, b) => (b.date + (b.created || "")).localeCompare(a.date + (a.created || ""));

async function putLog(req, me, env, json) {
  if (Date.now() - (me.last_sync || 0) < 3000) return json({ error: "slow-down" }, 429);
  const { body, error } = await readBody(req);
  if (error) return json({ error }, error === "too-large" ? 413 : 400);
  if (!body || !Array.isArray(body.entries)) return json({ error: "format" }, 400);
  const incoming = new Map(); // 同じ id が重なっていたら最初のものを使う
  for (const raw of body.entries.slice(0, MAX_ENTRIES)) {
    const e = cleanEntry(raw);
    if (e && !incoming.has(e.id)) incoming.set(e.id, e);
  }
  const gone = (Array.isArray(body.deleted) ? body.deleted : []).filter(validId).slice(-MAX_DELETED);
  const ids = await storeIds(env);
  // ほかの端末で足した記録は残し、どこかの端末で消した記録は戻さない。
  // 別の端末と同時に書き込んだときは、読み直してからやり直す
  for (let i = 0; i < 3; i++) {
    const row = await env.DB.prepare("SELECT log, rev FROM users WHERE id = ?1").bind(me.id).first();
    if (!row) return json({ error: "auth" }, 401);
    const saved = parseLog(row.log);
    const deleted = [...new Set([...saved.deleted, ...gone])].slice(-MAX_DELETED);
    const merged = new Map(saved.entries.map((e) => [e.id, e]));
    for (const [id, e] of incoming) merged.set(id, e);
    for (const id of deleted) merged.delete(id);
    const entries = [...merged.values()].sort(newestFirst).slice(0, MAX_ENTRIES);
    const counted = entries.filter((e) => countable(e, ids));
    const shops = new Set(counted.map((e) => e.store)).size;
    const res = await env.DB.prepare(
      "UPDATE users SET log = ?1, shops = ?2, bowls = ?3, updated = ?4, last_sync = ?5, rev = rev + 1 WHERE id = ?6 AND rev = ?7")
      .bind(JSON.stringify({ entries, deleted }), shops, counted.length, nowIso(), Date.now(), me.id, row.rev).run();
    if (res.meta && res.meta.changes) return json({ ok: true, count: entries.length, shops, entries, deleted });
  }
  return json({ error: "busy" }, 503);
}

async function getLog(me, env, json) {
  const row = await env.DB.prepare("SELECT log FROM users WHERE id = ?1").bind(me.id).first();
  const { entries, deleted } = parseLog(row && row.log);
  return json({ handle: me.handle, name: me.name, entries, deleted });
}

async function updateMe(req, me, env, json) {
  const { body, error } = await readBody(req);
  if (error || !body) return json({ error: error || "format" }, 400);
  let name = me.name, showDates = me.show_dates ? 1 : 0;
  if (body.name !== undefined) {
    name = normName(body.name);
    if (!validName(name)) return json({ error: "name" }, 400);
  }
  if (body.show_dates !== undefined) showDates = body.show_dates === true ? 1 : 0;
  await env.DB.prepare("UPDATE users SET name = ?1, show_dates = ?2, updated = ?3 WHERE id = ?4").bind(name, showDates, nowIso(), me.id).run();
  return json({ ok: true, name, show_dates: !!showDates });
}

async function removeMe(me, env, json) {
  await env.DB.prepare("DELETE FROM users WHERE id = ?1").bind(me.id).run();
  return json({ ok: true });
}

async function publicUser(url, env, json) {
  const handle = String(url.searchParams.get("h") || "").toLowerCase();
  if (!/^[a-z0-9_]{3,20}$/.test(handle)) return json({ error: "not-found" }, 404);
  const row = await env.DB.prepare("SELECT handle, name, created, shops, bowls, log, show_dates FROM users WHERE handle = ?1 AND hidden = 0")
    .bind(handle).first();
  if (!row) return json({ error: "not-found" }, 404);
  const ids = await storeIds(env);
  const entries = parseLog(row.log).entries.filter((e) => countable(e, ids)).sort(newestFirst);
  // 日付は本人が「日付まで公開する」を選んだときだけ。選んでいなければ年月まで
  const when = (e) => (row.show_dates ? e.date : e.date.slice(0, 7));
  const stores = {};
  for (const e of entries) {
    const month = when(e);
    const s = stores[e.store] || (stores[e.store] = { id: e.store, n: 0, first: month, last: month });
    s.n += 1;
    if (month < s.first) s.first = month;
    if (month > s.last) s.last = month;
  }
  // 公開するのは店・メニュー・コールと、年月か日付だけ（メモ・満足度は出さない）
  const recent = entries.slice(0, 50).map((e) => ({ store: e.store, when: when(e), items: e.items || null, menu: e.items ? "" : e.menu, call: e.call }));
  return json({ handle: row.handle, name: row.name, since: row.created.slice(0, 7), show_dates: !!row.show_dates,
    shops: row.shops, bowls: row.bowls, stores: Object.values(stores), recent });
}

async function ranking(env, json) {
  const { results } = await env.DB.prepare(
    "SELECT handle, name, shops, bowls FROM users WHERE hidden = 0 AND bowls > 0 ORDER BY shops DESC, bowls DESC, created ASC LIMIT 50").all();
  const total = await env.DB.prepare("SELECT COUNT(*) AS n FROM users WHERE hidden = 0 AND bowls > 0").first();
  return json({ users: results, total: total ? total.n : results.length });
}
