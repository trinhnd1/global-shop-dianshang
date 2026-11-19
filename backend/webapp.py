"""Same-origin Web UI + API server for Global Shop Dianshang (Loopback & Tailscale ready on port 8999)."""
import argparse
import json
import mimetypes
from pathlib import Path
import traceback
from urllib.parse import unquote
from wsgiref.simple_server import make_server

from . import PRODUCT_NAME
from .responses import check_host_and_origin
from .server import Application, LocalHTTPServer, LocalRequestHandler

DEFAULT_STATIC = Path(__file__).resolve().parent.parent / "web" / "static"

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' https: data: blob:; media-src 'self' https: data: blob:; "
    "manifest-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
    "frame-ancestors 'self'; form-action 'self'"
)
ROOT_STATIC_ALIASES = {
    "/favicon.ico": "favicon.ico",
    "/favicon.svg": "favicon.svg",
    "/favicon-32x32.png": "favicon-32x32.png",
    "/apple-touch-icon.png": "apple-touch-icon.png",
    "/apple-touch-icon-precomposed.png": "apple-touch-icon.png",
    "/icon-192.png": "icon-192.png",
    "/icon-512.png": "icon-512.png",
    "/site.webmanifest": "site.webmanifest",
    "/manifest.json": "site.webmanifest",
}
EXPLICIT_MIME_TYPES = {
    ".ico": "image/x-icon",
    ".svg": "image/svg+xml; charset=utf-8",
    ".png": "image/png",
    ".webmanifest": "application/manifest+json; charset=utf-8",
}
SECURITY_HEADERS = [
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("X-Frame-Options", "SAMEORIGIN"),
    ("Content-Security-Policy", CSP),
]


class WebApp:
    def __init__(self, api: Application, static_dir: str | Path):
        self.api = api
        self.static = Path(static_dir).resolve()
        self.index = self.static / "index.html"
        if not self.index.is_file():
            raise RuntimeError(f"Không tìm thấy giao diện web tại {self.index}")

    def __call__(self, env, start_response):
        path = env.get("PATH_INFO", "") or "/"
        if path in ("/mcp", "/mcp/"):
            return self.api.mcp_gateway.handle_http_mcp(env, start_response)
        if path == "/api" or path.startswith("/api/"):
            return self.call_api(env, start_response)

        blocked = check_host_and_origin(env, allow_tailscale=self.api.allow_tailscale)
        if blocked is not None:
            return self.json_resp(start_response, blocked[0], blocked[1])

        method = env.get("REQUEST_METHOD", "GET")
        if method not in ("GET", "HEAD"):
            return self.json_resp(start_response, "405 Method Not Allowed", {"detail": "Method not allowed"})

        target = self.resolve(path)
        if target is None:
            return self.json_resp(start_response, "404 Not Found", {"detail": "File not found"})

        body = target.read_bytes()
        ext = target.suffix.lower()
        if ext in EXPLICIT_MIME_TYPES:
            ctype = EXPLICIT_MIME_TYPES[ext]
        else:
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json", "image/svg+xml"):
                ctype += "; charset=utf-8"
        cache_hdr = "public, max-age=86400" if ext in EXPLICIT_MIME_TYPES else "no-cache"
        headers = [("Content-Type", ctype), ("Content-Length", str(len(body))), ("Cache-Control", cache_hdr)]
        start_response("200 OK", headers + SECURITY_HEADERS)
        return [b""] if method == "HEAD" else [body]

    def call_api(self, env, start_response):
        captured = {}

        def capture(status, headers, exc_info=None):
            captured["status"], captured["headers"] = status, headers

        try:
            body = b"".join(self.api(env, capture))
        except Exception:
            traceback.print_exc()
            return self.json_resp(
                start_response,
                "500 Internal Server Error",
                {"detail": "Lỗi nội bộ backend — xem log server", "code": "internal_error"},
            )
        start_response(captured["status"], captured["headers"])
        return [body]

    def resolve(self, path: str) -> Path | None:
        alias_rel = ROOT_STATIC_ALIASES.get(path)
        if alias_rel:
            cand_alias = (self.static / alias_rel).resolve()
            if self.static in cand_alias.parents and cand_alias.is_file():
                return cand_alias
            return None
        if not path.startswith("/static/"):
            return self.index
        rel = unquote(path[len("/static/"):])
        if "\x00" in rel or not rel:
            return None
        cand = (self.static / rel).resolve()
        if self.static not in cand.parents or not cand.is_file():
            return None
        return cand

    @staticmethod
    def json_resp(start_response, status: str, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        start_response(
            status,
            [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Content-Length", str(len(body))),
                ("Cache-Control", "no-store"),
            ],
        )
        return [body]


def main():
    parser = argparse.ArgumentParser(description="Global Shop Dianshang — Same-origin WebApp")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8999)
    parser.add_argument("--static-dir", default=str(DEFAULT_STATIC))
    parser.add_argument("--loopback-only", action="store_true")
    args = parser.parse_args()

    api = Application(args.data_dir, allow_tailscale=not args.loopback_only, web_port=args.port)
    api.watch_scheduler.start()
    api.ecosystem_scheduler.start()
    api.telegram_bot.start()
    api.daily_brief_daemon.start()
    app = WebApp(api, args.static_dir)
    with make_server(args.host, args.port, app, server_class=LocalHTTPServer, handler_class=LocalRequestHandler) as srv:
        print(f"{PRODUCT_NAME} running at http://{args.host}:{args.port}", flush=True)
        srv.serve_forever()


if __name__ == "__main__":
    main()
