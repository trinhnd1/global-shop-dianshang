"""Dedicated isolated Chromium profile hub (loopback CDP 127.0.0.1:9349) for Shopee, TikTok Seller, Kalodata & 1688/Taobao."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import urllib.request

from .responses import ApiError, json_object, now

DEFAULT_CDP_PORT = 9349

PORTAL_REGISTRY = {
    "shopee": {
        "title": "Shopee VN & Shopee Seller",
        "default_url": "https://banhang.shopee.vn/",
        "allowed_domains": ("shopee.vn", "banhang.shopee.vn"),
    },
    "tiktok_seller": {
        "title": "TikTok Shop Seller & Affiliate Creator",
        "default_url": "https://seller.tiktokshopglobalselling.com/",
        "allowed_domains": ("tiktokshopglobalselling.com", "tiktok.com"),
    },
    "kalodata": {
        "title": "Kalodata Analytics",
        "default_url": "https://www.kalodata.com/product",
        "allowed_domains": ("kalodata.com",),
    },
    "china_1688_taobao": {
        "title": "1688 · Taobao · Pinduoduo Sourcing",
        "default_url": "https://www.1688.com/",
        "allowed_domains": ("1688.com", "taobao.com", "tmall.com", "yangkeduo.com"),
    },
}


def find_chrome_binary() -> str | None:
    env_bin = os.environ.get("GLOBAL_SHOP_BROWSER_BIN", "").strip()
    if env_bin and Path(env_bin).is_file():
        return env_bin
    for cand in (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        shutil.which("google-chrome") or "",
        shutil.which("chromium") or "",
    ):
        if cand and Path(cand).is_file():
            return cand
    return None


class DedicatedChromeHub:
    def __init__(self, data_dir: str | Path, connect=None, cdp_port: int = DEFAULT_CDP_PORT):
        self.root = Path(data_dir)
        self.connect = connect
        self.cdp_port = int(cdp_port)
        self.profile_dir = self.root / "browser_profiles" / "dianshang_dedicated"
        self.state_file = self.profile_dir / ".gs_cdp_state.json"
        self._lock = threading.Lock()
        self.profile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name == "posix":
            self.profile_dir.chmod(0o700)

    def cdp_tabs(self) -> list[dict]:
        url = f"http://127.0.0.1:{self.cdp_port}/json/list"
        try:
            with urllib.request.urlopen(url, timeout=1.8) as resp:
                items = json.loads(resp.read().decode("utf-8"))
                return [x for x in items if isinstance(x, dict) and x.get("type") == "page"]
        except Exception:
            return []

    def is_running(self) -> bool:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.cdp_port}/json/version", timeout=1.5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def status(self) -> dict:
        running = self.is_running()
        tabs = self.cdp_tabs() if running else []
        portals = {}
        for key, meta in PORTAL_REGISTRY.items():
            matched = [
                {"title": t.get("title", ""), "url": t.get("url", "")}
                for t in tabs
                if any(dom in (t.get("url") or "").lower() for dom in meta["allowed_domains"])
            ]
            portals[key] = {
                "portal_key": key,
                "title": meta["title"],
                "default_url": meta["default_url"],
                "tab_open": bool(matched),
                "tabs": matched[:3],
            }
        return {
            "running": running,
            "cdp_host": "127.0.0.1",
            "cdp_port": self.cdp_port,
            "browser_available": bool(find_chrome_binary()),
            "profile_name": "Global Shop Dianshang Dedicated",
            "open_tabs_count": len(tabs),
            "portals": portals,
        }

    def open_portal(self, portal_key: str = "shopee") -> dict:
        if portal_key not in PORTAL_REGISTRY:
            raise ApiError("400 Bad Request", f"Cổng trình duyệt không hợp lệ: {portal_key}")
        target_url = PORTAL_REGISTRY[portal_key]["default_url"]
        chrome_bin = find_chrome_binary()
        if not chrome_bin:
            raise ApiError("503 Service Unavailable", "Không tìm thấy Google Chrome / Chromium trên máy")

        with self._lock:
            if self.is_running():
                try:
                    req = urllib.request.Request(f"http://127.0.0.1:{self.cdp_port}/json/new?{target_url}", method="PUT")
                    urllib.request.urlopen(req, timeout=3).read()
                except Exception:
                    pass
            else:
                proc = subprocess.Popen(
                    [
                        chrome_bin,
                        f"--user-data-dir={self.profile_dir}",
                        "--remote-debugging-address=127.0.0.1",
                        f"--remote-debugging-port={self.cdp_port}",
                        "--no-first-run",
                        "--no-default-browser-check",
                        "--new-window",
                        target_url,
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                self.state_file.write_text(
                    json.dumps({"pid": proc.pid, "port": self.cdp_port, "started_at": now()}),
                    encoding="utf-8",
                )
                if os.name == "posix":
                    self.state_file.chmod(0o600)

        if self.connect is not None:
            with self.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO browser_connections (portal_key, session_state, context_state, market, last_url, updated_at)
                    VALUES (?, 'waiting_for_user', 'unverified', 'VN', ?, ?)
                    ON CONFLICT(portal_key) DO UPDATE SET last_url=excluded.last_url, updated_at=excluded.updated_at
                    """,
                    (portal_key, target_url, now()),
                )
        return {"opened": True, "portal_key": portal_key, "target_url": target_url, **self.status()}

    def dispatch(self, path: str, method: str, env, read_json):
        if path == "/api/connections/browser" and method == "GET":
            return "200 OK", self.status()
        if path == "/api/connections/browser/open" and method == "POST":
            body = json_object(read_json, env)
            pkey = str(body.get("portal_key") or "shopee").strip()
            return "200 OK", self.open_portal(pkey)
        return None
