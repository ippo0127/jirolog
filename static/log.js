/* マイ二郎ログ: 記録の追加・一覧・集計・書き出し */
(function () {
  "use strict";
  const form = document.querySelector("[data-log-form]");
  if (!form) return;
  const { J, EN, t, esc, log, byId, activeStores, root, WD, sname, sarea } = window.JL;
  const F = form.elements;
  const msg = document.querySelector("[data-log-msg]");

  // 店の選択肢（エリアごと）。閉店した店は新しく記録しない（過去の記録は残る）
  const groups = {};
  for (const s of J.stores) {
    if (s.status === "upcoming" || s.status === "closed") continue;
    (groups[sarea(s)] = groups[sarea(s)] || []).push(s);
  }
  F.store.innerHTML = `<option value="">${t("選んでください", "Choose a shop")}</option>` + Object.entries(groups).map(([area, ss]) =>
    `<optgroup label="${esc(area)}">${ss.map((s) => `<option value="${esc(s.id)}">${esc(sname(s))}${s.status === "temporarily_closed" ? t("（休業中）", " (on break)") : ""}</option>`).join("")}</optgroup>`
  ).join("");

  // 店ごとのメニュー（ラーメン類は選択肢、追加券・トッピングはチェック）
  const yen = (p) => (EN ? `¥${p.toLocaleString()}` : `${p.toLocaleString()}円`);
  const mname = (m) => (EN && m.e) || m.n;
  const freeBox = form.querySelector("[data-free]");
  const addonBox = form.querySelector("[data-addons]");
  const addonList = form.querySelector("[data-addon-list]");
  const totalEl = form.querySelector("[data-total]");
  let mains = [], addons = [];

  function fillMenu() {
    const s = byId[F.store.value];
    const menu = (s && s.menu) || [];
    mains = menu.filter((m) => m.k === "main");
    addons = menu.filter((m) => m.k === "add");
    F.pick.innerHTML = mains.map((m, i) => `<option value="${i}">${esc(mname(m))}${m.p != null ? ` ${yen(m.p)}` : ""}</option>`).join("") +
      `<option value="free">${t("その他（自由入力）", "Other (type it in)")}</option>`;
    addonList.innerHTML = addons.map((m, i) =>
      `<label><input type="checkbox" name="addon" value="${i}"> ${esc(mname(m))}${m.p != null ? ` ${yen(m.p)}` : ""}</label>`).join("");
    addonBox.hidden = !addons.length;
    syncMenu();
  }
  function picked() {
    const main = F.pick.value === "free" ? null : mains[Number(F.pick.value)];
    const adds = [...addonList.querySelectorAll("input:checked")].map((c) => addons[Number(c.value)]);
    const items = [main, ...adds].filter(Boolean);
    const priced = items.filter((m) => m.p != null);
    const total = main && priced.length === items.length ? priced.reduce((a, m) => a + m.p, 0) : null;
    return { main, adds, total };
  }
  function syncMenu() {
    freeBox.hidden = F.pick.value !== "free";
    const { total } = picked();
    totalEl.textContent = total != null ? t(`合計 ${yen(total)}（記録時点の価格）`, `Total ${yen(total)} (price at the time)`) : "";
  }
  F.store.addEventListener("change", fillMenu);
  F.pick.addEventListener("change", syncMenu);
  addonList.addEventListener("change", syncMenu);

  const params = new URLSearchParams(location.search);
  if (params.get("store") && groups && byId[params.get("store")] && byId[params.get("store")].status !== "closed") F.store.value = params.get("store");
  fillMenu();
  F.date.value = window.JL.iso(new Date(Date.now() + 9 * 3600e3));

  const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
  const dateLabel = (d) => {
    const w = WD[new Date(d + "T00:00:00Z").getUTCDay()];
    return EN ? `${w} ${d}` : `${d.replace(/-/g, "/")}(${w})`;
  };

  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    if (!F.store.value || !F.date.value) return;
    const data = log.load();
    const { main, adds, total } = picked();
    const menu = main ? [mname(main), ...adds.map(mname)].join(" + ")
      : [F.menu.value.trim(), ...adds.map(mname)].filter(Boolean).join(" + ");
    data.entries.push({
      id: uid(), store: F.store.value, date: F.date.value,
      menu, items: main ? [main.n, ...adds.map((m) => m.n)] : null, price: total,
      call: F.call.value.trim(), rating: F.rating.value ? Number(F.rating.value) : null,
      memo: F.memo.value.trim(), created: new Date().toISOString(),
    });
    if (!log.save(data)) {
      msg.textContent = t("保存できませんでした（プライベートモードでは保存できないことがあります）", "Could not save (private browsing may block storage)");
      return;
    }
    msg.textContent = t(`${sname(byId[F.store.value])} を記録しました`, `Saved: ${sname(byId[F.store.value])}`);
    F.menu.value = F.call.value = F.memo.value = ""; F.rating.value = "";
    addonList.querySelectorAll("input").forEach((c) => { c.checked = false; });
    syncMenu();
    draw();
    window.JL.render();
  });

  function draw() {
    const entries = log.load().entries.slice().sort((a, b) => (b.date + b.created).localeCompare(a.date + a.created));
    const counts = log.counts();
    const act = activeStores();
    const done = act.filter((s) => counts[s.id]);
    const year = String(new Date(Date.now() + 9 * 3600e3).getUTCFullYear());
    const thisYear = entries.filter((e) => e.date.startsWith(year)).length;
    const top = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
    const spent = entries.reduce((a, e) => a + (typeof e.price === "number" ? e.price : 0), 0);

    document.querySelector("[data-stats]").innerHTML = [
      [entries.length, t("通算 杯", "bowls in total")],
      [`${done.length}<small>/${act.length}</small>`, t("訪問 店", "shops visited")],
      [`${act.length ? Math.floor((100 * done.length) / act.length) : 0}%`, t("制覇率", "complete")],
      [thisYear, t(`${year}年 杯`, `bowls in ${year}`)],
      [top && byId[top[0]] ? esc(sname(byId[top[0]])) : "—", top ? t(`最多 ${top[1]} 杯`, `most visited (${top[1]})`) : t("最多訪問", "most visited")],
      [spent ? yen(spent) : "—", t("使った金額（メニューから記録した分）", "spent (from menu picks)")],
    ].map(([v, l], i) => `<div class="stat"><b${i >= 4 ? ' style="font-size:1.1rem"' : ""}>${v}</b><span>${l}</span></div>`).join("");
    document.querySelector("[data-bar]").style.width = (act.length ? (100 * done.length) / act.length : 0) + "%";

    const areas = {};
    for (const s of act) { const a = (areas[sarea(s)] = areas[sarea(s)] || [0, 0]); a[1]++; if (counts[s.id]) a[0]++; }
    document.querySelector("[data-area-progress]").innerHTML = Object.entries(areas).map(([name, [d, n]]) =>
      `<div class="pref-row"><span>${esc(name)}</span><div class="progress"><div class="bar"><span style="width:${(100 * d) / n}%"></span></div></div><span class="small">${d}/${n}</span></div>`
    ).join("");

    document.querySelector("[data-log-count]").textContent = entries.length ? t(`${entries.length} 件`, `${entries.length} entries`) : "";
    document.querySelector("[data-log-list]").innerHTML = entries.map((e) => {
      const s = byId[e.store];
      const name = s ? `<a href="${root}stores/${esc(s.id)}.html">${esc(sname(s))}</a>${s.status === "closed" ? `<span class="small muted">${t("（閉店）", " (closed)")}</span>` : ""}` : esc(e.store);
      const detail = [e.menu && (typeof e.price === "number" ? t(`${e.menu}（${yen(e.price)}）`, `${e.menu} (${yen(e.price)})`) : e.menu), e.call && `${t("コール", "Call")}: ${e.call}`,
        e.rating && "★".repeat(e.rating), e.memo].filter(Boolean).map(esc).join(" · ");
      return `<li class="log-item"><span class="date">${dateLabel(e.date)}</span><span class="li-store">${name}</span>` +
        `<button data-del="${esc(e.id)}" aria-label="${t("この記録を消す", "Delete this entry")}">${t("消す", "Delete")}</button>${detail ? `<span class="li-detail">${detail}</span>` : ""}</li>`;
    }).join("") || `<li class="muted">${t("まだ記録がありません。上のフォームから記録しましょう。", "Nothing logged yet. Use the form above to add your first bowl.")}</li>`;

    document.querySelector("[data-unvisited]").innerHTML = act.filter((s) => !counts[s.id]).map((s) =>
      `<li><a class="chip chip-link" href="${root}stores/${esc(s.id)}.html">${esc(sname(s))}</a></li>`
    ).join("") || `<li class="muted">${t("全店制覇！おめでとうございます。", "You have visited every shop. Congratulations!")}</li>`;
  }

  document.querySelector("[data-log-list]").addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-del]");
    if (!btn || !confirm(t("この記録を消しますか？", "Delete this entry?"))) return;
    const data = log.load();
    data.entries = data.entries.filter((e) => e.id !== btn.dataset.del);
    log.save(data); draw(); window.JL.render();
  });

  document.querySelector("[data-export]").addEventListener("click", () => {
    const blob = new Blob([JSON.stringify(log.load(), null, 1)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `jirolog-${window.JL.iso(new Date())}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  });

  document.querySelector("[data-import]").addEventListener("change", async (ev) => {
    const file = ev.target.files[0];
    if (!file) return;
    try {
      const incoming = JSON.parse(await file.text());
      if (!incoming || !Array.isArray(incoming.entries)) throw new Error("format");
      const data = log.load();
      const ids = new Set(data.entries.map((e) => e.id));
      const fresh = incoming.entries.filter((e) => e && e.id && e.store && e.date && !ids.has(e.id));
      data.entries.push(...fresh);
      log.save(data);
      msg.textContent = t(`${fresh.length} 件を読み込みました`, `Imported ${fresh.length} entries`);
      draw(); window.JL.render();
    } catch (_) {
      msg.textContent = t("読み込めませんでした（二郎ログで書き出した JSON を選んでください）", "Could not import (choose a JSON file exported from Jiro Log)");
    }
    ev.target.value = "";
  });

  document.querySelector("[data-clear]").addEventListener("click", () => {
    if (!confirm(t("すべての記録を消します。元に戻せません。先に書き出しておくことをおすすめします。消しますか？",
      "This deletes your whole log and cannot be undone. Export it first if you want a copy. Delete everything?"))) return;
    log.save({ entries: [] }); draw(); window.JL.render();
  });

  draw();
})();
