#!/usr/bin/env python3
"""手元で dist/ を確認するためのサーバー（Cloudflare Pages と同じ URL の形で動く）。

    python3 scripts/serve.py          # http://localhost:8000
    python3 scripts/serve.py 8026

/stores/mita → stores/mita.html、/stores/ → stores/index.html、見つからなければ 404.html を返す。
"""
import functools
import http.server
import pathlib
import sys
import urllib.parse

DIST = pathlib.Path(__file__).resolve().parent.parent / "dist"


class Handler(http.server.SimpleHTTPRequestHandler):
    def _resolve(self):
        path = urllib.parse.urlparse(self.path).path
        local = DIST / urllib.parse.unquote(path).lstrip("/")
        if local.is_dir() and (local / "index.html").exists():
            return path
        if local.is_file():
            return path
        if local.with_suffix(".html").is_file() if local.name else False:
            return path + ".html"
        return None

    def send_head(self):
        resolved = self._resolve()
        if resolved is None:
            lang404 = DIST / "en" / "404.html" if self.path.startswith("/en/") else DIST / "404.html"
            body = lang404.read_bytes() if lang404.exists() else b"Not found"
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return None
        query = urllib.parse.urlparse(self.path).query
        self.path = resolved + (f"?{query}" if query else "")
        return super().send_head()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    handler = functools.partial(Handler, directory=str(DIST))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        print(f"http://localhost:{port}  ({DIST})")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
