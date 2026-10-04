/* 二郎ログ 共通スクリプト: 日本時間の営業判定・訪問記録・表示更新（日本語 / 英語） */
(function () {
  "use strict";
  const J = window.JIRO || { stores: [], holidays: {} };
  const EN = document.documentElement.lang === "en";
  const t = (ja, en) => (EN ? en : ja);
  const DAYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];
  const WD = EN ? ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] : ["日", "月", "火", "水", "木", "金", "土"];
  const LOG_KEY = "jirolog.v1";
  const root = document.body ? document.body.dataset.root || "" : "";

  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const toMin = (s) => { const [h, m] = s.split(":").map(Number); return h * 60 + m; };
  const fmt = (min) => {
    const h = Math.floor(min / 60), m = String(min % 60).padStart(2, "0");
    if (h >= 24) return EN ? `${h - 24}:${m} (+1)` : `翌${h - 24}:${m}`;
    return `${h}:${m}`;
  };
  const iso = (d) => d.toISOString().slice(0, 10);
  const shift = (dateStr, n) => { const d = new Date(dateStr + "T00:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return d; };
  const sname = (s) => (EN && s.name_en) || s.name;
  const snick = (s) => (EN ? s.nick_en : s.nick) || "";
  const sarea = (s) => (EN ? s.area_label_en : s.area_label) || s.area;
  const saccess = (s) => (EN && s.access_en && s.access_en.length ? s.access_en : s.access) || [];

  // 日本は夏時間がないので UTC+9 で固定
  function now() {
    const d = new Date(Date.now() + 9 * 3600e3);
    return { date: iso(d), dow: d.getUTCDay(), min: d.getUTCHours() * 60 + d.getUTCMinutes() };
  }

  // その日の営業時間。[] = 休み、null = 要確認
  function rangesOn(store, dateStr, dow) {
    const h = store.hours || {};
    if (J.holidays[dateStr]) return "holiday" in h ? h.holiday : null;
    const r = h[DAYS[dow]];
    return r === undefined ? null : r;
  }

  function nextOpen(store, n) {
    for (let i = 1; i <= 7; i++) {
      const d = shift(n.date, i);
      const r = rangesOn(store, iso(d), d.getUTCDay());
      if (r === null) return null;
      if (r.length) {
        const md = `${d.getUTCMonth() + 1}/${d.getUTCDate()}`;
        const when = i === 1 ? t("明日", "tomorrow") : EN ? `${WD[d.getUTCDay()]} ${md}` : `${md}(${WD[d.getUTCDay()]})`;
        return `${when} ${fmt(toMin(r[0][0]))}${t("〜", "")}`;
      }
    }
    return null;
  }

  function rangesText(r) {
    if (r === null) return t("要確認", "check");
    if (!r.length) return t("休み", "closed");
    return r.map(([a, b]) => `${fmt(toMin(a))}${t("〜", "–")}${fmt(toMin(b))}`).join(" / ");
  }

  /** state: open | soon | closed | off | unk */
  function status(store, n) {
    n = n || now();
    if (store.status === "closed") return { state: "off", short: t("閉店", "Closed"), label: t("閉店しました", "Permanently closed") };
    if (store.status === "temporarily_closed") return { state: "off", short: t("休業中", "On break"), label: t("休業中", "Temporarily closed") };
    if (store.status === "upcoming") return { state: "unk", short: t("開店予定", "Coming soon"), label: t("開店予定", "Opening soon") };

    const today = rangesOn(store, n.date, n.dow);
    const y = shift(n.date, -1);
    const yr = rangesOn(store, iso(y), y.getUTCDay()) || [];
    for (const [, b] of yr) {
      const B = toMin(b) - 1440;
      if (B > 0 && n.min < B) return { state: "open", short: t("営業中", "Open"), label: t(`営業中 · ${fmt(B)}頃まで`, `Open · until about ${fmt(B)}`), today };
    }
    const hol = J.holidays[n.date];
    const nx = () => { const x = nextOpen(store, n); return x ? t(` · 次は${x}`, ` · next: ${x}`) : ""; };
    if (today === null) {
      return { state: "unk", short: t("要確認", "Check"), label: hol ? t(`今日は祝日（${hol}）· 営業は要確認`, "Public holiday today · check the official account") : t("今日の営業は要確認", "Check today’s hours"), today };
    }
    if (!today.length) return { state: "off", short: t("定休", "Closed today"), label: (hol ? t(`祝日（${hol}）は休み`, "Closed on public holidays") : t("今日は定休日", "Closed today")) + nx(), today };
    for (const [a, b] of today) {
      const A = toMin(a), B = toMin(b);
      if (n.min >= A && n.min < B) {
        const soonEnd = B - n.min <= 30;
        const s = soonEnd ? t("まもなく終了", "Closing soon") : t("営業中", "Open");
        return { state: "open", short: s, label: t(`${s} · ${fmt(B)}頃まで`, `${s} · until about ${fmt(B)}`), today };
      }
      if (n.min < A) {
        const soon = A - n.min <= 60;
        return {
          state: soon ? "soon" : "closed",
          short: soon ? t("まもなく", "Soon") : t("時間外", "Closed now"),
          label: soon ? t(`まもなく開店 · ${fmt(A)}〜`, `Opens soon · ${fmt(A)}`) : t(`営業時間外 · ${fmt(A)}〜`, `Closed now · opens ${fmt(A)}`),
          today,
        };
      }
    }
    return { state: "closed", short: t("本日終了", "Done today"), label: t("今日の営業は終了", "Closed for today") + nx(), today };
  }

  // ---- 訪問ログ (localStorage)
  const log = {
    load() {
      try { const v = JSON.parse(localStorage.getItem(LOG_KEY)); return v && Array.isArray(v.entries) ? v : { entries: [] }; }
      catch (_) { return { entries: [] }; }
    },
    save(data) {
      try { localStorage.setItem(LOG_KEY, JSON.stringify(data)); return true; } catch (_) { return false; }
    },
    counts() {
      const c = {};
      for (const e of log.load().entries) c[e.store] = (c[e.store] || 0) + 1;
      return c;
    },
  };

  const activeStores = () => J.stores.filter((s) => s.status === "open" || s.status === "temporarily_closed");
  const byId = Object.fromEntries(J.stores.map((s) => [s.id, s]));

  function cardHTML(s, st) {
    return `<li class="store-card" data-id="${esc(s.id)}"><a href="${root}stores/${esc(s.id)}.html">
      <span class="sc-top"><span class="sc-area">${esc(sarea(s))}</span><span class="live-badge ${st.state}">${esc(st.short)}</span></span>
      <span class="sc-name">${esc(sname(s))}</span><span class="sc-nick">${esc(EN ? "" : snick(s))}</span>
      <span class="sc-today">${esc(st.label)}</span></a>
      <span class="sc-visited" data-visited="${esc(s.id)}" hidden>${t("行った", "Visited")}</span></li>`;
  }

  function render() {
    const n = now();
    const counts = log.counts();
    const hol = J.holidays[n.date];
    document.querySelectorAll("[data-clock]").forEach((el) => {
      el.textContent = EN ? `${fmt(n.min)} (${WD[n.dow]}${hol ? ", holiday" : ""})` : `${fmt(n.min)}（${WD[n.dow]}${hol ? "・祝" : ""}）`;
    });

    const statuses = {};
    for (const s of J.stores) statuses[s.id] = status(s, n);

    document.querySelectorAll("[data-live]").forEach((el) => {
      const st = statuses[el.dataset.live]; if (!st) return;
      el.className = "live-badge " + st.state; el.textContent = st.short;
      const card = el.closest(".store-card"); if (card) card.classList.toggle("is-off", st.state === "off");
    });
    document.querySelectorAll("[data-today]").forEach((el) => {
      const st = statuses[el.dataset.today]; if (!st) return;
      el.textContent = st.today !== undefined ? `${t("今日", "Today")} ${rangesText(st.today)}` : st.label;
    });
    document.querySelectorAll("[data-live-line]").forEach((el) => {
      const st = statuses[el.dataset.liveLine]; if (!st) return;
      el.className = "live-line " + st.state; el.textContent = st.label;
    });
    document.querySelectorAll("table.week:not([data-static])").forEach((tb) => {
      const key = hol ? "holiday" : DAYS[n.dow];
      tb.querySelectorAll("tr").forEach((tr) => tr.classList.toggle("is-today", tr.dataset.day === key));
    });

    const open = J.stores.filter((s) => statuses[s.id].state === "open");
    document.querySelectorAll("[data-open-count]").forEach((el) => { el.textContent = open.length; });
    document.querySelectorAll("[data-open-list]").forEach((ul) => {
      ul.innerHTML = open.map((s) => cardHTML(s, statuses[s.id])).join("");
      const empty = document.querySelector("[data-open-empty]"); if (empty) empty.hidden = open.length > 0;
    });

    document.querySelectorAll("[data-visited]").forEach((el) => { el.hidden = !counts[el.dataset.visited]; });
    document.querySelectorAll("[data-visited-pill]").forEach((el) => {
      const c = counts[el.dataset.visitedPill] || 0; el.hidden = !c; el.textContent = t(`記録 ${c} 杯`, `${c} visit${c === 1 ? "" : "s"} logged`);
    });
    document.querySelectorAll("[data-progress]").forEach((el) => {
      const act = activeStores(), done = act.filter((s) => counts[s.id]).length;
      const total = Object.values(counts).reduce((a, b) => a + b, 0);
      el.querySelector(".bar span").style.width = (act.length ? (100 * done) / act.length : 0) + "%";
      el.querySelector("[data-progress-text]").textContent = total
        ? t(`${act.length} 店中 ${done} 店に行きました（${total} 杯）`, `${done} of ${act.length} shops visited (${total} bowls)`)
        : t("まだ記録がありません", "Nothing logged yet");
    });
    document.dispatchEvent(new CustomEvent("jiro:render", { detail: { now: n, statuses } }));
  }

  window.JL = { J, EN, t, esc, now, status, rangesOn, rangesText, toMin, fmt, iso, log, byId, activeStores, cardHTML, render, root, WD, DAYS, sname, snick, sarea, saccess };

  // 来てくれた人の数: 1回の来訪（タブを閉じるまで）につき1回だけ数える。送るのは「来た」ことだけ
  async function visits() {
    const url = document.body.dataset.views;
    const line = document.querySelector("[data-views-line]");
    if (!url || !line) return;
    let n = null;
    try { n = JSON.parse(sessionStorage.getItem("jl.visits")); } catch (_) { /* 使えないブラウザもある */ }
    if (n == null) {
      try {
        const r = await fetch(url, { method: "POST", body: JSON.stringify({ path: "/" }), headers: { "Content-Type": "text/plain" } });
        if (!r.ok) return;
        n = (await r.json()).total;
        try { sessionStorage.setItem("jl.visits", JSON.stringify(n)); } catch (_) { /* 保存できなくても表示はする */ }
      } catch (_) { return; }
    }
    line.querySelector("[data-visits]").textContent = Number(n).toLocaleString(EN ? "en-US" : "ja-JP");
    line.hidden = false;
  }

  function start() {
    visits();
    render();
    // 分が変わるたびに更新
    const wait = 60000 - (Date.now() % 60000) + 50;
    setTimeout(() => { render(); setInterval(render, 60000); }, wait);
    window.addEventListener("storage", (ev) => { if (ev.key === LOG_KEY) render(); });
  }
  // defer 読み込みの各ページ用スクリプトがリスナーを登録してから最初の描画をする
  if (document.readyState === "complete") start(); else document.addEventListener("DOMContentLoaded", start);
})();
