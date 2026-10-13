/* マイ二郎ログの公開プロフィール（ニックネーム＋合言葉。メールアドレスは使わない）
   同期: この端末の記録と「消した記録の id」を送り、サーバーでほかの端末の分と合わせた結果を受け取る */
(function () {
  "use strict";
  const box = document.querySelector("[data-profile]");
  const API = document.body.dataset.api;
  if (!box || !API) return;
  const { t, log, activeStores, root } = window.JL;
  const KEY = "jirolog.account.v1";
  const $ = (sel) => box.querySelector(sel);
  box.hidden = false;

  const load = () => { try { return JSON.parse(localStorage.getItem(KEY)) || null; } catch (_) { return null; } };
  const store = (a) => { try { if (a) localStorage.setItem(KEY, JSON.stringify(a)); else localStorage.removeItem(KEY); } catch (_) { /* 保存できない環境 */ } };
  let account = load();

  async function call(path, { method = "GET", body, token } = {}) {
    const headers = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (token) headers.Authorization = "Bearer " + token;
    try {
      const r = await fetch(API + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
      let data = null;
      try { data = await r.json(); } catch (_) { /* 中身なし */ }
      return { ok: r.ok, status: r.status, data: data || {} };
    } catch (_) {
      return { ok: false, status: 0, data: { error: "network" } };
    }
  }

  const ERR = {
    handle: t("ID は英小文字・数字・_ の3〜20文字にしてください（使えない言葉が入った ID もあります）", "Use 3–20 lowercase letters, digits or _ for the ID (some words are not allowed)"),
    taken: t("その ID はもう使われています。別の ID にしてください", "That ID is already taken. Try another one"),
    name: t("ニックネームが長すぎるか、使えない言葉が入っています", "The nickname is too long or contains a word that is not allowed"),
    busy: t("混み合っています。時間をおいて試してください", "Too busy right now. Please try again later"),
    network: t("通信できませんでした。電波のよいところで試してください", "Could not connect. Please try again with a better connection"),
  };
  const pageUrl = (h) => new URL(`${root}u/?h=${encodeURIComponent(h)}`, location.href).href;
  const fmtToken = (s) => (String(s).toUpperCase().replace(/[^A-Z0-9]/g, "").match(/.{1,4}/g) || []).join("-");
  const hhmm = () => new Date().toTimeString().slice(0, 5);
  const setStatus = (text) => { $("[data-sync-status]").textContent = text; };

  // 消した記録の id は、端末をつないでいる間だけ覚える（つなぎ直したときに、ほかの端末の記録を消さないため）
  function dropDeleted() {
    const data = log.load();
    if (data.deleted) { delete data.deleted; log.save(data); }
  }
  function forget(note) {
    account = null; store(null); dropDeleted(); render();
    $("[data-register-msg]").textContent = note || "";
  }

  // サーバーで合わせた結果を、この端末の記録に取り込む（送ったあとに足した記録・消した記録も生かす）
  function absorb(srv) {
    const data = log.load();
    const dead = new Set([...(data.deleted || []), ...(srv.deleted || [])]);
    const merged = new Map();
    for (const e of [...(srv.entries || []), ...data.entries]) if (e && e.id && e.store && e.date && !dead.has(e.id)) merged.set(e.id, e);
    const before = new Set(data.entries.map((e) => e.id));
    const entries = [...merged.values()];
    const added = entries.filter((e) => !before.has(e.id)).length;
    const removed = data.entries.length + added - entries.length;
    log.save({ ...data, entries, deleted: [...dead].slice(-5000) });
    if (added || removed) {
      if (window.JLLog) window.JLLog.draw();
      window.JL.render();
    }
    return added;
  }

  // ---- 同期（変えてから少し待ってまとめて送る）
  let timer = null, running = null, again = false, lastSync = 0;
  function schedule(delay = 1500) {
    if (!account) return;
    clearTimeout(timer);
    timer = setTimeout(sync, delay);
    setStatus(t("同期待ち…", "Waiting to sync…"));
  }
  async function sync() {
    if (!account) return -1;
    if (running) { again = true; return running; }
    running = (async () => {
      const data = log.load();
      const r = await call("/api/me/log", { method: "PUT", body: { entries: data.entries, deleted: data.deleted || [] }, token: account.token });
      if (r.ok) {
        lastSync = Date.now();
        const added = absorb(r.data);
        setStatus(t(`同期済み ${hhmm()}`, `Synced ${hhmm()}`));
        return added;
      }
      if (r.status === 429 || r.status === 503) { again = true; return -1; } // 少し待ってもう一度
      if (r.status === 401) {
        forget(t("公開プロフィールが見つかりませんでした（ほかの端末で公開をやめた可能性があります）。このブラウザの記録は残っています。",
          "Your public profile was not found (it may have been removed on another device). The log in this browser is kept."));
        return -1;
      }
      setStatus(t("同期できませんでした。つながったらもう一度送ります", "Could not sync; will retry when you are back online"));
      return -1;
    })();
    const res = await running;
    running = null;
    if (again && account) { again = false; schedule(3500); }
    return res;
  }
  addEventListener("online", () => schedule(500));
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && account && Date.now() - lastSync > 60000) schedule(500);
  });

  function render(newToken) {
    const on = !!account;
    $("[data-profile-off]").hidden = on;
    $("[data-profile-on]").hidden = !on;
    if (!on) return;
    const url = pageUrl(account.handle);
    const link = $("[data-profile-link]");
    link.href = url;
    link.textContent = `${account.name} (@${account.handle})`;
    $("[data-profile-open]").href = url;
    const counts = log.counts();
    const act = activeStores();
    const done = act.filter((s) => counts[s.id]).length;
    const bowls = log.load().entries.length;
    const text = t(`二郎ログでラーメン二郎の記録を公開中！ 直系 ${done}/${act.length} 店・通算 ${bowls} 杯`,
      `My Ramen Jiro log on Jiro Log: ${done}/${act.length} shops, ${bowls} bowls`);
    $("[data-profile-x]").href = "https://x.com/intent/post?" + new URLSearchParams({ text, url, hashtags: t("ラーメン二郎", "RamenJiro") });
    $("[data-show-dates]").checked = !!account.show_dates;
    $("[data-rename]").elements.name.value = account.name;
    $("[data-token]").textContent = account.token;
    if (newToken) {
      $("[data-token-new]").hidden = false;
      $("[data-token-new-value]").textContent = newToken;
    }
  }

  async function copy(text, btn) {
    try { await navigator.clipboard.writeText(text); btn.textContent = t("コピーしました", "Copied"); }
    catch (_) { prompt(t("コピーしてください", "Copy this"), text); }
  }

  // ---- 公開する
  $("[data-register]").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const f = ev.currentTarget.elements;
    const msg = $("[data-register-msg]");
    msg.textContent = t("公開しています…", "Publishing…");
    const r = await call("/api/register", { method: "POST", body: {
      handle: f.handle.value.trim().toLowerCase(), name: f.name.value, show_dates: f.show_dates.checked, website: f.website.value } });
    if (!r.ok) { msg.textContent = ERR[r.data.error] || (r.status === 0 ? ERR.network : t("公開できませんでした", "Could not publish")); return; }
    dropDeleted();
    account = { handle: r.data.handle, name: r.data.name, token: r.data.token, show_dates: !!r.data.show_dates };
    store(account);
    msg.textContent = "";
    render(r.data.token);
    sync();
  });

  // ---- 別の端末から引き継ぐ（この端末の記録とあわせる）
  $("[data-restore]").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const form = ev.currentTarget;
    const msg = $("[data-restore-msg]");
    const token = fmtToken(form.elements.token.value);
    msg.textContent = t("確かめています…", "Checking…");
    const me = await call("/api/me", { token });
    if (!me.ok) { msg.textContent = me.status === 401 ? t("合言葉が違います", "Wrong passphrase") : ERR.network; return; }
    dropDeleted();
    account = { handle: me.data.handle, name: me.data.name, token, show_dates: !!me.data.show_dates };
    store(account);
    msg.textContent = "";
    form.reset();
    render();
    const added = await sync();
    if (added >= 0) setStatus(t(`${added} 件を引き継ぎました（同期済み）`, `Moved ${added} entries here (synced)`));
  });

  // ---- 設定
  $("[data-show-dates]").addEventListener("change", async (ev) => {
    const cb = ev.target;
    const r = await call("/api/me", { method: "PATCH", body: { show_dates: cb.checked }, token: account.token });
    if (r.ok) { account.show_dates = r.data.show_dates; store(account); } else { cb.checked = !cb.checked; alert(ERR.network); }
  });
  $("[data-rename]").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const msg = $("[data-rename-msg]");
    const name = ev.currentTarget.elements.name.value;
    const r = await call("/api/me", { method: "PATCH", body: { name }, token: account.token });
    if (!r.ok) { msg.textContent = ERR[r.data.error] || ERR.network; return; }
    account.name = r.data.name; store(account); render();
    msg.textContent = t("変えました", "Updated");
  });
  $("[data-token-show]").addEventListener("click", () => { $("[data-token]").hidden = !$("[data-token]").hidden; });
  $("[data-token-copy]").addEventListener("click", (ev) => copy(account.token, ev.currentTarget));
  $("[data-token-copy2]").addEventListener("click", (ev) => copy(account.token, ev.currentTarget));
  $("[data-token-done]").addEventListener("click", () => { $("[data-token-new]").hidden = true; });
  $("[data-profile-copy]").addEventListener("click", (ev) => copy(pageUrl(account.handle), ev.currentTarget));
  $("[data-unlink]").addEventListener("click", () => {
    if (!confirm(t("この端末とのつながりを外します。公開ページとサーバーの記録はそのまま残り、合言葉でまたつなげます。このブラウザの記録も残ります。よろしいですか？",
      "Disconnect this device? Your public page and the copy on the server stay, and you can reconnect with your passphrase. The log in this browser stays too."))) return;
    forget();
  });
  $("[data-unpublish]").addEventListener("click", async () => {
    if (!confirm(t("公開をやめて、サーバーの記録とニックネームを消します。このブラウザの記録は残ります。よろしいですか？",
      "This removes your public page, nickname and the copy on the server. The log in this browser stays. Continue?"))) return;
    const r = await call("/api/me", { method: "DELETE", token: account.token });
    if (!r.ok && r.status !== 401) { alert(ERR.network); return; }
    forget();
  });

  window.JLAccount = { changed: () => schedule(), active: () => !!account };
  render();
  if (account) schedule(800);
})();
