// 二郎ログ 誤りの報告の中継（Cloudflare Workers）
// サイトの報告フォームから受け取った内容を、GitHub の Issue（ラベル: report）にする。
//
// 設定（Cloudflare のダッシュボード → Workers → この Worker → Settings → Variables）
//   GITHUB_REPO      報告用の非公開リポジトリ。例: yourname/jirolog-reports
//   GITHUB_TOKEN     その1リポジトリの Issues: Read and write だけを許可した fine-grained token（Secret として登録）
//   ALLOWED_ORIGINS  例: https://jirolog.pages.dev  （カンマ区切りで複数可）

const KINDS = {
  typo: "誤植・表記の誤り", hours: "営業時間・定休日", menu: "メニュー・価格", status: "閉店・移転・休業・再開",
  access: "住所・アクセス・地図", lineage: "系譜", english: "英語の表記", other: "その他",
};

export default {
  async fetch(req, env) {
    const origin = req.headers.get("Origin") || "";
    const allowed = (env.ALLOWED_ORIGINS || "").split(",").map((s) => s.trim()).filter(Boolean);
    const cors = {
      "Access-Control-Allow-Origin": allowed.includes(origin) ? origin : allowed[0] || "",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Accept",
      Vary: "Origin",
    };
    const json = (obj, status = 200) => new Response(JSON.stringify(obj), { status, headers: { ...cors, "Content-Type": "application/json" } });

    if (req.method === "OPTIONS") return new Response(null, { headers: cors });
    if (req.method !== "POST") return json({ error: "method" }, 405);
    if (!allowed.includes(origin)) return json({ error: "origin" }, 403);

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
  },
};
