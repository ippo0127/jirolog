/* 店舗ページ: 小さな地図、YouTube と SNS 投稿のクリック読み込み */
(function () {
  "use strict";

  const GSI = "https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png";
  const GSI_ATTR = '<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank" rel="noopener">地理院タイル</a>';

  function miniMap() {
    const el = document.querySelector(".mini-map");
    if (!el || !window.L) return;
    const lat = parseFloat(el.dataset.lat), lng = parseFloat(el.dataset.lng);
    const map = L.map(el, { scrollWheelZoom: false, attributionControl: true }).setView([lat, lng], 16);
    L.tileLayer(GSI, { attribution: GSI_ATTR, maxZoom: 18 }).addTo(map);
    L.marker([lat, lng], {
      icon: L.divIcon({ className: "", html: '<div class="pin" style="background:#ffd400"></div>', iconSize: [18, 18], iconAnchor: [9, 9] }),
      title: el.dataset.name,
    }).addTo(map);
  }

  // 押されるまで YouTube には接続しない
  document.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".yt-load");
    if (!btn) return;
    const f = document.createElement("iframe");
    f.src = `https://www.youtube-nocookie.com/embed/${encodeURIComponent(btn.dataset.yt)}?autoplay=1`;
    f.allow = "autoplay; encrypted-media; picture-in-picture";
    f.allowFullscreen = true;
    f.title = btn.getAttribute("aria-label") || "YouTube";
    btn.replaceWith(f);
  });

  const loaded = {};
  function loadScript(src) {
    if (!loaded[src]) {
      loaded[src] = new Promise((res, rej) => {
        const s = document.createElement("script");
        s.src = src; s.async = true; s.onload = res; s.onerror = rej;
        document.head.appendChild(s);
      });
    }
    return loaded[src];
  }

  // 公式の埋め込みを、押されたときだけ読み込む
  document.addEventListener("click", async (ev) => {
    const btn = ev.target.closest(".embed-load");
    if (!btn) return;
    const slot = btn.parentElement.querySelector(".embed-slot");
    const url = btn.dataset.embed;
    btn.disabled = true;
    try {
      if (btn.dataset.platform === "instagram") {
        slot.innerHTML = `<blockquote class="instagram-media" data-instgrm-permalink="${window.JL.esc(url)}" data-instgrm-version="14"><a href="${window.JL.esc(url)}">Instagram</a></blockquote>`;
        await loadScript("https://www.instagram.com/embed.js");
        if (window.instgrm) window.instgrm.Embeds.process();
      } else {
        slot.innerHTML = `<blockquote class="twitter-tweet" data-dnt="true" lang="${window.JL.EN ? "en" : "ja"}"><a href="${window.JL.esc(url.replace("x.com", "twitter.com"))}">${window.JL.t("X の投稿", "Post on X")}</a></blockquote>`;
        await loadScript("https://platform.twitter.com/widgets.js");
        if (window.twttr && window.twttr.widgets) window.twttr.widgets.load(slot);
      }
      btn.remove();
    } catch (_) {
      slot.textContent = window.JL.t("読み込めませんでした。リンクから開いてください。", "Could not load it. Open the link instead.");
      btn.disabled = false;
    }
  });

  if (document.readyState === "complete") miniMap(); else document.addEventListener("DOMContentLoaded", miniMap);
})();
