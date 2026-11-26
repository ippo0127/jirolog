// 以前のアドレス jirolog.pages.dev に来た人を jirolog.com へ転送する（301。パスとクエリはそのまま）。
// ただし、マイ二郎ログの引き継ぎページ（/bridge）だけは古いアドレスのまま開く。
// 記録はアドレスごとにブラウザに保存されるので、古いアドレスの記録はそこでしか読めないため。
// 古いアドレスのマイログ（/log・/en/log）を開いた人は、引き継ぎページに回す。
// 画像や CSS（/assets/*）は、build.py が書き出す dist/_routes.json の指定でここを通らない。
const OLD = "jirolog.pages.dev";
const NEW = "https://jirolog.com";

export async function onRequest({ request, next }) {
  const url = new URL(request.url);
  if (url.hostname !== OLD) return next();
  const path = url.pathname.replace(/\.html$/, "");
  if (path === "/bridge") return next();
  if (path === "/log" || path === "/en/log") {
    return Response.redirect(`https://${OLD}/bridge?back=${encodeURIComponent(path)}`, 302);
  }
  return Response.redirect(NEW + url.pathname + url.search, 301);
}
