/* 地図ページ */
(function () {
  "use strict";
  const el = document.getElementById("map");
  if (!el || !window.L) return;
  const { J, esc, root, t, sname, sarea, saccess } = window.JL;
  const COLORS = { open: "#1f9d55", soon: "#e69500", closed: "#9b968a", off: "#9b968a", unk: "#7a80c0" };
  const stores = J.stores.filter((s) => s.lat && s.status !== "closed");

  const map = L.map(el, { zoomControl: true }).setView([35.69, 139.6], 10);
  L.tileLayer("https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png", {
    attribution: '<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank" rel="noopener">地理院タイル</a>',
    maxZoom: 18,
  }).addTo(map);

  const list = document.querySelector("[data-map-list]");
  const onlyOpen = document.querySelector("[data-map-open]");
  const markers = {};
  let here = null;
  let statuses = {};

  const icon = (state) => L.divIcon({ className: "", html: `<div class="pin" style="background:${COLORS[state] || COLORS.unk}"></div>`, iconSize: [18, 18], iconAnchor: [9, 9], popupAnchor: [0, -8] });

  function km(a, b) {
    const R = 6371, rad = Math.PI / 180;
    const dLat = (b.lat - a.lat) * rad, dLng = (b.lng - a.lng) * rad;
    const x = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLng / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(x));
  }

  function popup(s, st) {
    return `<strong><a href="${root}stores/${esc(s.id)}.html">${esc(sname(s))}</a></strong><br>${esc(st.label)}<br><span style="color:#6d685c">${esc(saccess(s)[0] || "")}</span>`;
  }

  function draw() {
    let items = stores.map((s) => ({ s, st: statuses[s.id] || window.JL.status(s), d: here ? km(here, s) : null }));
    if (onlyOpen.checked) items = items.filter((x) => x.st.state === "open");
    if (here) items.sort((a, b) => a.d - b.d);
    const visible = new Set(items.map((x) => x.s.id));
    for (const s of stores) {
      const st = statuses[s.id] || window.JL.status(s);
      if (!markers[s.id]) {
        markers[s.id] = L.marker([s.lat, s.lng], { title: sname(s) }).bindPopup("");
      }
      markers[s.id].setIcon(icon(st.state)).setPopupContent(popup(s, st));
      if (visible.has(s.id)) markers[s.id].addTo(map); else markers[s.id].remove();
    }
    list.innerHTML = items.map(({ s, st, d }) =>
      `<li data-id="${esc(s.id)}" tabindex="0"><i class="dot" style="background:${COLORS[st.state] || COLORS.unk}"></i><span class="ml-name">${esc(sname(s))}</span>` +
      `${d != null ? ` <span class="small muted">${d < 10 ? d.toFixed(1) : Math.round(d)}km</span>` : ""}<span class="ml-sub">${esc(sarea(s))} · ${esc(st.label)}</span></li>`
    ).join("") || `<li class="muted">${t("該当する店はありません", "No matching shops")}</li>`;
  }

  function focus(id) {
    const m = markers[id];
    if (!m) return;
    map.flyTo(m.getLatLng(), Math.max(map.getZoom(), 14), { duration: 0.6 });
    m.openPopup();
    if (window.matchMedia("(max-width: 820px)").matches) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  list.addEventListener("click", (ev) => { const li = ev.target.closest("li[data-id]"); if (li) focus(li.dataset.id); });
  list.addEventListener("keydown", (ev) => { if (ev.key === "Enter") { const li = ev.target.closest("li[data-id]"); if (li) focus(li.dataset.id); } });
  onlyOpen.addEventListener("change", draw);

  document.querySelector("[data-locate]").addEventListener("click", (ev) => {
    const btn = ev.currentTarget;
    if (!navigator.geolocation) { btn.textContent = t("位置情報が使えません", "Location unavailable"); return; }
    btn.textContent = t("現在地を取得中…", "Finding you…");
    navigator.geolocation.getCurrentPosition((pos) => {
      here = { lat: pos.coords.latitude, lng: pos.coords.longitude };
      L.circleMarker([here.lat, here.lng], { radius: 7, color: "#c4161c", fillOpacity: 0.9 }).addTo(map).bindTooltip(t("現在地", "You are here"));
      btn.textContent = t("現在地から近い順", "Sort by distance from me");
      draw();
      const nearest = list.querySelector("li[data-id]");
      if (nearest) map.fitBounds(L.latLngBounds([[here.lat, here.lng], markers[nearest.dataset.id].getLatLng()]).pad(0.4));
    }, () => { btn.textContent = t("現在地を取得できませんでした", "Could not get your location"); }, { enableHighAccuracy: false, timeout: 10000 });
  });

  document.addEventListener("jiro:render", (ev) => { statuses = ev.detail.statuses; draw(); });
})();
