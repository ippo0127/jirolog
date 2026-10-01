/* 店舗一覧の絞り込み。条件は URL の # に保存する（例: #area=東京23区&open=1） */
(function () {
  "use strict";
  const form = document.querySelector("[data-filters]");
  if (!form) return;
  const { J, byId, rangesOn, toMin, log, t } = window.JL;
  const CHECKS = ["open", "today", "sun", "morning", "night", "unvisited"];
  const F = form.elements;
  let statuses = {};

  function readHash() {
    const p = new URLSearchParams(location.hash.slice(1));
    F.q.value = p.get("q") || "";
    F.area.value = p.get("area") || "";
    for (const k of CHECKS) F[k].checked = p.get(k) === "1";
  }
  function writeHash() {
    const p = new URLSearchParams();
    if (F.q.value.trim()) p.set("q", F.q.value.trim());
    if (F.area.value) p.set("area", F.area.value);
    for (const k of CHECKS) if (F[k].checked) p.set(k, "1");
    const h = p.toString();
    history.replaceState(null, "", h ? "#" + h : location.pathname + location.search);
  }

  const allRanges = (s) => Object.entries(s.hours || {}).filter(([k]) => k !== "holiday").flatMap(([, r]) => r || []);

  function matches(s, n, visited) {
    const st = statuses[s.id];
    if (F.area.value && s.area !== F.area.value) return false;
    const q = F.q.value.trim().toLowerCase();
    if (q && ![s.name, s.name_en, s.nick, s.nick_en, s.area_label, s.area_label_en, s.pref, ...(s.access || []), ...(s.access_en || [])].join(" ").toLowerCase().includes(q)) return false;
    if (F.open.checked && (!st || st.state !== "open")) return false;
    if (F.today.checked) {
      const r = rangesOn(s, n.date, n.dow);
      if (s.status !== "open" || !r || !r.length) return false;
    }
    if (F.sun.checked && !((s.hours || {}).sun || []).length) return false;
    if (F.morning.checked && !allRanges(s).some(([a]) => toMin(a) < 11 * 60)) return false;
    if (F.night.checked && !allRanges(s).some(([, b]) => toMin(b) > 20 * 60)) return false;
    if (F.unvisited.checked && visited[s.id]) return false;
    return true;
  }

  function apply() {
    const n = window.JL.now();
    const visited = log.counts();
    let shown = 0;
    document.querySelectorAll(".store-card[data-id]").forEach((li) => {
      const s = byId[li.dataset.id];
      const ok = s && matches(s, n, visited);
      li.hidden = !ok;
      if (ok) shown++;
    });
    document.querySelectorAll(".area-group").forEach((g) => {
      g.hidden = !g.querySelector(".store-card:not([hidden])");
    });
    const total = J.stores.filter((s) => s.status !== "closed").length;
    form.querySelector("[data-result-count]").textContent = t(`${total} 店中 ${shown} 店を表示`, `Showing ${shown} of ${total} shops`);
  }

  document.addEventListener("jiro:render", (ev) => { statuses = ev.detail.statuses; apply(); });
  form.addEventListener("input", () => { writeHash(); apply(); });
  window.addEventListener("hashchange", () => { readHash(); apply(); });
  readHash();
})();
