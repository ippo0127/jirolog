/* 公開プロフィール（u/?h=ID）とランキングのページ */
(function () {
  "use strict";
  const API = document.body.dataset.api;
  const { EN, t, esc, byId, activeStores, root, WD, sname, sarea } = window.JL;

  async function get(path) {
    try {
      const r = await fetch(API + path);
      let data = {};
      try { data = await r.json(); } catch (_) { /* 中身なし */ }
      return { ok: r.ok, status: r.status, data };
    } catch (_) {
      return { ok: false, status: 0, data: {} };
    }
  }

  // ---- ほかの人が書いた文は、決まった言葉でできているときだけ出す
  // メニュー: その店のメニューか、記録フォームの候補にある名前だけ
  const PRESET_PAIRS = [["小ラーメン", "Small ramen"], ["小豚ラーメン", "Small ramen + extra pork"], ["大ラーメン", "Large ramen"],
    ["大豚ラーメン", "Large ramen + extra pork"], ["小ラーメン 麺少なめ", "Small ramen, less noodles"], ["汁なし", "Shiru-nashi"], ["つけ麺", "Tsukemen"]];
  const PRESETS = new Map(PRESET_PAIRS.flatMap(([ja, en]) => [[ja, t(ja, en)], [en, t(ja, en)]]));
  function menuText(x) {
    const s = byId[x.store];
    const names = new Map();
    for (const m of (s && s.menu) || []) {
      const shown = EN ? m.e || m.n : m.n;
      names.set(m.n, shown);
      if (m.e) names.set(m.e, shown);
    }
    const parts = Array.isArray(x.items) && x.items.length ? x.items : String(x.menu || "").split(" + ");
    if (!x.items && PRESETS.has(String(x.menu || "").trim())) return PRESETS.get(String(x.menu).trim());
    return parts.map((n) => String(n).trim()).map((n) => names.get(n) || PRESETS.get(n) || "").filter(Boolean).join(" + ");
  }

  // コール: ヤサイ・ニンニク・アブラ・カラメ・マシ などの組み合わせだけ
  const CALL_WORDS = [
    "ヤサイ", "野菜", "ニンニク", "大蒜", "アブラ", "脂", "油", "カラメ", "辛目", "マシ", "増シ", "増", "スコシ", "少シ", "少ナメ", "少量", "少", "スクナメ",
    "チョイ", "チョット", "ヌキ", "抜キ", "ナシ", "無シ", "無", "イラナイ", "全部", "ゼンブ", "全", "ゼン", "ソノママ", "普通", "フツウ", "フツー",
    "オオメ", "多メ", "多", "デ", "ト", "オ願イシマス", "オネガイシマス", "オ願イ", "オネガイ", "ショウガ", "ショーガ", "生姜", "唐辛子", "トウガラシ", "一味", "七味",
    "魚粉", "ギョフン", "ネギ", "玉ネギ", "タマネギ", "ニラ", "生卵", "卵", "タマゴ", "チーズ", "粉チーズ", "マヨ", "マヨネーズ", "ラー油", "辛", "カラ",
    "麺", "メン", "カタメ", "硬メ", "固メ", "ヤワメ", "柔ラカメ", "半分", "ハンブン", "汁", "ツユ", "ダブル", "ダブ",
    "yasai", "ninniku", "abura", "karame", "mashi", "sukoshi", "sukuname", "nuki", "nashi", "zenbu", "zen", "sonomama", "de", "to", "onegaishimasu",
    "futsu", "futsuu", "oome", "katame", "yawame", "men", "hanbun", "garlic", "vegetables", "vegetable", "veggies", "veg", "backfat", "fat", "back",
    "extra", "more", "less", "little", "alittle", "a", "no", "none", "normal", "all", "everything", "asis", "sauce", "soysauce", "soy", "with", "and",
    "please", "plain", "noodles", "noodle", "half", "firm", "soft", "ginger", "egg", "cheese", "mayo", "spicy", "chili", "double",
  ].map((w) => w.normalize("NFKC").toLowerCase());
  const kata = (s) => s.replace(/[ぁ-ゖ]/g, (c) => String.fromCharCode(c.charCodeAt(0) + 0x60));
  function callText(call) {
    const raw = String(call || "").trim();
    const s = kata(raw.normalize("NFKC").toLowerCase()).replace(/[\s、。・,.\/+&!?！？~〜（）()-]/g, "");
    if (!s || raw.length > 40) return "";
    // 頭から順に、どこまで決まった言葉だけで区切れるかを調べる
    const ok = new Array(s.length + 1).fill(false);
    ok[0] = true;
    for (let i = 0; i < s.length; i++) if (ok[i]) for (const w of CALL_WORDS) if (s.startsWith(w, i)) ok[i + w.length] = true;
    return ok[s.length] ? raw : "";
  }

  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function whenText(w) {
    const [y, m, d] = String(w).split("-");
    if (!d) return EN ? `${MONTHS[Number(m) - 1]} ${y}` : `${y}年${Number(m)}月`;
    const wd = WD[new Date(`${w}T00:00:00Z`).getUTCDay()];
    return EN ? `${wd} ${w}` : `${y}/${m}/${d}(${wd})`;
  }
  const storeLink = (s) => `<a href="${root}stores/${esc(s.id)}">${esc(sname(s))}</a>${s.status === "closed" ? `<span class="small muted">${t("（閉店）", " (closed)")}</span>` : ""}`;

  // ---------------------------------------------------------------- 公開プロフィール
  async function profilePage(page) {
    const status = page.querySelector("[data-user-status]");
    const h = String(new URLSearchParams(location.search).get("h") || "").toLowerCase();
    // シェアボタンが、このページ（?h= 付き）を共有するように
    const bar = document.querySelector("[data-share]");
    const retarget = (text) => {
      if (!bar || !/^[a-z0-9_]{3,20}$/.test(h)) return;
      const url = new URL(`${root}u/?h=${h}`, location.href).href;
      bar.dataset.url = url;
      for (const a of bar.querySelectorAll("a[href]")) {
        const x = new URL(a.href);
        if (!x.searchParams.has("url")) continue;
        x.searchParams.set("url", url);
        if (text && x.searchParams.has("text")) x.searchParams.set("text", text);
        a.href = x.href;
      }
    };
    retarget();
    if (!/^[a-z0-9_]{3,20}$/.test(h)) { status.textContent = t("ページが見つかりませんでした。", "Page not found."); return; }
    const r = await get(`/api/user?h=${encodeURIComponent(h)}`);
    if (!r.ok) {
      status.textContent = r.status === 404 ? t("このページは見つかりませんでした（公開をやめた可能性があります）。", "This page was not found (it may have been unpublished).")
        : t("読み込めませんでした。時間をおいて開き直してください。", "Could not load. Please try again later.");
      return;
    }
    const u = r.data;
    document.title = t(`${u.name} さんの二郎ログ`, `${u.name}'s Jiro log`) + " | " + t("二郎ログ", "Jiro Log");
    if (bar) bar.dataset.title = document.title;
    retarget(t(`${u.name} さんのラーメン二郎の記録（直系 ${Number(u.shops) || 0} 店・${Number(u.bowls) || 0} 杯）`, `${u.name}'s Ramen Jiro log (${Number(u.shops) || 0} shops, ${Number(u.bowls) || 0} bowls)`));
    page.querySelector("[data-user-name]").textContent = t(`${u.name} さんの二郎ログ`, `${u.name}'s Jiro log`);
    page.querySelector("[data-user-handle]").textContent = `@${u.handle}`;
    page.querySelector("[data-user-since]").textContent = [
      t(`${whenText(u.since)}から公開`, `Public since ${whenText(u.since)}`),
      u.show_dates ? "" : t("記録は年月まで公開", "Only the month of each visit is shown"),
    ].filter(Boolean).join(" · ");

    const visited = (u.stores || []).filter((x) => byId[x.id]);
    const counts = Object.fromEntries(visited.map((x) => [x.id, x.n]));
    const act = activeStores();
    const done = act.filter((s) => counts[s.id]).length;
    page.querySelector("[data-user-stats]").innerHTML = [
      [`${done}<small>/${act.length}</small>`, t("訪問 店", "shops visited")],
      [`${act.length ? Math.floor((100 * done) / act.length) : 0}%`, t("制覇率", "complete")],
      [visited.length, t("閉店した店も含めた訪問 店", "shops incl. closed ones")],
      [Number(u.bowls) || 0, t("通算 杯", "bowls in total")],
    ].map(([v, l]) => `<div class="stat"><b>${v}</b><span>${l}</span></div>`).join("");
    page.querySelector("[data-user-bar]").style.width = (act.length ? (100 * done) / act.length : 0) + "%";

    const areas = {};
    for (const s of act) { const a = (areas[sarea(s)] = areas[sarea(s)] || [0, 0]); a[1]++; if (counts[s.id]) a[0]++; }
    page.querySelector("[data-user-areas]").innerHTML = Object.entries(areas).map(([name, [d, n]]) =>
      `<div class="pref-row"><span>${esc(name)}</span><div class="progress"><div class="bar"><span style="width:${(100 * d) / n}%"></span></div></div><span class="small">${d}/${n}</span></div>`
    ).join("");

    page.querySelector("[data-user-stores]").innerHTML = visited.slice().sort((a, b) => b.n - a.n || a.first.localeCompare(b.first)).map((x) => {
      const s = byId[x.id];
      return `<li><a class="chip chip-link${s.status === "closed" ? " chip-closed" : ""}" href="${root}stores/${esc(s.id)}">${esc(sname(s))}${s.status === "closed" ? t("（閉店）", " (closed)") : ""}<b>${Number(x.n) || 0}</b></a></li>`;
    }).join("") || `<li class="muted">${t("まだ記録がありません。", "Nothing logged yet.")}</li>`;

    page.querySelector("[data-user-recent]").innerHTML = (u.recent || []).filter((x) => byId[x.store]).map((x) => {
      const detail = [menuText(x), callText(x.call) && `${t("コール", "Call")}: ${callText(x.call)}`].filter(Boolean).map(esc).join(" · ");
      return `<li class="log-item"><span class="date">${esc(whenText(x.when))}</span><span class="li-store">${storeLink(byId[x.store])}</span>` +
        `${detail ? `<span class="li-detail">${detail}</span>` : ""}</li>`;
    }).join("") || `<li class="muted">${t("まだ記録がありません。", "Nothing logged yet.")}</li>`;

    page.querySelector("[data-user-report]").href = `${root}report?` + new URLSearchParams({ page: `u/?h=${u.handle}`, kind: "profile" });
    status.hidden = true;
    page.querySelector("[data-user-body]").hidden = false;
  }

  // ---------------------------------------------------------------- ランキング
  async function rankingPage(tbody) {
    const r = await get("/api/ranking");
    if (!r.ok) {
      tbody.innerHTML = `<tr><td colspan="4" class="muted">${t("読み込めませんでした。時間をおいて開き直してください。", "Could not load. Please try again later.")}</td></tr>`;
      return;
    }
    const users = r.data.users || [];
    let rank = 0, prev = null;
    tbody.innerHTML = users.map((u, i) => {
      const key = `${u.shops}/${u.bowls}`;
      if (key !== prev) { rank = i + 1; prev = key; } // 同じ数なら同じ順位
      return `<tr${rank <= 3 ? ` class="top${rank}"` : ""}><td>${rank}</td><th><a href="${root}u/?h=${esc(u.handle)}">${esc(u.name)}</a> <span class="small muted">@${esc(u.handle)}</span></th>` +
        `<td>${Number(u.shops) || 0}</td><td>${Number(u.bowls) || 0}</td></tr>`;
    }).join("") || `<tr><td colspan="4" class="muted">${t("まだ参加者がいません。最初の1人になりませんか？", "No one has joined yet. Be the first!")}</td></tr>`;
    const total = document.querySelector("[data-ranking-total]");
    if (total && r.data.total) total.textContent = t(`参加者 ${r.data.total} 人`, `${r.data.total} ${r.data.total === 1 ? "person" : "people"} taking part`);
  }

  const page = document.querySelector("[data-user-page]");
  const tbody = document.querySelector("[data-ranking]");
  if (!API) {
    if (page) page.querySelector("[data-user-status]").textContent = t("いまは表示できません。", "Not available right now.");
    return;
  }
  if (page) profilePage(page);
  if (tbody) rankingPage(tbody);
})();
