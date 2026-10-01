/* 誤りの報告: 入力から決まった書式の報告文を作り、コピーまたは送信する */
(function () {
  "use strict";
  const form = document.querySelector("[data-report-form]");
  if (!form) return;
  const { t, byId, sname } = window.JL;
  const F = form.elements;
  const preview = document.querySelector("[data-report-preview]");
  const msg = document.querySelector("[data-report-msg]");
  const endpoint = form.dataset.endpoint;

  const params = new URLSearchParams(location.search);
  if (params.get("store") && byId[params.get("store")]) F.store.value = params.get("store");
  if (params.get("page")) F.page.value = params.get("page");

  const kindLabel = () => F.kind.options[F.kind.selectedIndex].text;

  // この書式は README の「誤りの報告フォーマット」と同じ
  function text() {
    const s = byId[F.store.value];
    return [
      t("【二郎ログ 誤りの報告】", "[Jiro Log: mistake report]"),
      `${t("店", "Shop")}: ${s ? `${sname(s)} (${s.id})` : "-"}`,
      `${t("ページ", "Page")}: ${F.page.value.trim() || "-"}`,
      `${t("種類", "Type")}: ${kindLabel()}`,
      `${t("いまの表記", "Now says")}: ${F.current.value.trim() || "-"}`,
      `${t("正しい内容", "Should say")}: ${F.correct.value.trim() || "-"}`,
      `${t("情報源", "Source")}: ${F.source.value.trim() || "-"}`,
    ].join("\n");
  }
  const update = () => { preview.textContent = text(); };
  form.addEventListener("input", update);
  update();

  document.querySelector("[data-copy]").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(text());
      msg.textContent = t("コピーしました", "Copied");
    } catch (_) {
      const r = document.createRange(); r.selectNodeContents(preview);
      const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r);
      msg.textContent = t("選択しました。コピーしてください", "Selected — copy it now");
    }
  });

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (!endpoint) return;
    const data = new FormData(form);
    data.append("report", text());
    data.append("_subject", t("二郎ログ 誤りの報告", "Jiro Log mistake report"));
    msg.textContent = t("送信中…", "Sending…");
    try {
      const r = await fetch(endpoint, { method: "POST", body: data, headers: { Accept: "application/json" } });
      if (!r.ok) throw new Error(r.status);
      msg.textContent = t("送信しました。ありがとうございます！", "Sent. Thank you!");
      F.current.value = F.correct.value = F.source.value = "";
      update();
    } catch (_) {
      msg.textContent = t("送信できませんでした。報告文をコピーして送ってください", "Could not send. Please copy the report instead");
    }
  });
})();
