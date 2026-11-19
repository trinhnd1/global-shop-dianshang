"""Dedicated Chromium Profile Hub sharing `affiliate-peng`'s `peng_dedicated` profile (CDP 127.0.0.1:9339) for Kalodata & TikTok Affiliate Global Selling."""
import base64
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import time
from urllib.parse import quote, urlsplit
import urllib.request

from .responses import ApiError, json_object, now

AFFILIATE_PENG_SHARED_PROFILE = Path("/Users/trinh/.gemini/antigravity/scratch/affiliate-peng/local-data/browser_profiles/peng_dedicated")
PREFERRED_SHARED_CDP_PORT = 9339
FALLBACK_LOCAL_CDP_PORT = 9349

TIKTOK_CREATOR_FIND_URL = "https://affiliate.tiktokshopglobalselling.com/affiliate/creator?shop_region=VN&shop_id=8647628568244356830"
KALODATA_PRODUCT_URL = "https://www.kalodata.com/product"
KALODATA_VIDEO_URL = "https://www.kalodata.com/video"

PORTAL_REGISTRY = {
    "kalodata": {
        "title": "Kalodata VN Analytics (peng_dedicated)",
        "default_url": KALODATA_PRODUCT_URL,
        "allowed_domains": ("kalodata.com",),
    },
    "affiliate_global_selling": {
        "title": "TikTok Affiliate Global Selling — Find Creators",
        "default_url": TIKTOK_CREATOR_FIND_URL,
        "allowed_domains": ("affiliate.tiktokshopglobalselling.com", "seller.tiktokshopglobalselling.com"),
    },
    "tiktok_seller": {
        "title": "TikTok Shop Seller & Affiliate Creator",
        "default_url": TIKTOK_CREATOR_FIND_URL,
        "allowed_domains": ("tiktokshopglobalselling.com", "tiktok.com"),
    },
    "shopee": {
        "title": "Shopee VN & Shopee Seller",
        "default_url": "https://banhang.shopee.vn/",
        "allowed_domains": ("shopee.vn", "banhang.shopee.vn"),
    },
    "china_1688_taobao": {
        "title": "1688 · Taobao · Pinduoduo Sourcing",
        "default_url": "https://www.1688.com/",
        "allowed_domains": ("1688.com", "taobao.com", "tmall.com", "yangkeduo.com"),
    },
    "facebook_fanpage": {
        "title": "Facebook Fanpage & Meta Business Suite",
        "default_url": "https://business.facebook.com/",
        "allowed_domains": ("facebook.com", "fb.com", "business.facebook.com"),
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


def cdp_ws_eval(port: int, ws_url: str, expression: str, timeout: float = 9.0) -> dict:
    """Pure-stdlib loopback-only (`127.0.0.1`) CDP WebSocket `Runtime.evaluate` helper."""
    parsed = urlsplit(ws_url)
    ws_path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    sock = socket.create_connection(("127.0.0.1", int(port)), timeout=timeout)
    try:
        sock.settimeout(timeout)
        ws_key = base64.b64encode(os.urandom(16)).decode("ascii")
        handshake = (
            f"GET {ws_path} HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {ws_key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(handshake.encode("ascii"))
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                raise RuntimeError("Kết nối CDP đóng trước khi hoàn tất handshake")
            buf += chunk
        header_part, leftover = buf.split(b"\r\n\r\n", 1)
        if not header_part.split(b"\r\n", 1)[0].startswith(b"HTTP/1.1 101 "):
            raise RuntimeError("CDP từ chối nâng cấp WebSocket")

        msg_bytes = json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {"expression": expression, "returnByValue": True, "awaitPromise": False},
        }).encode("utf-8")
        mask_key = os.urandom(4)
        plen = len(msg_bytes)
        frame = bytearray([0x81])
        if plen < 126:
            frame.append(0x80 | plen)
        elif plen < 65536:
            frame.append(0x80 | 126)
            frame.extend(struct.pack("!H", plen))
        else:
            frame.append(0x80 | 127)
            frame.extend(struct.pack("!Q", plen))
        frame.extend(mask_key)
        frame.extend(bytes(b ^ mask_key[i % 4] for i, b in enumerate(msg_bytes)))
        sock.sendall(bytes(frame))

        stream_buf = bytearray(leftover)

        def _read_exact(n: int) -> bytes:
            while len(stream_buf) < n:
                ch = sock.recv(4096)
                if not ch:
                    raise RuntimeError("Luồng CDP kết thúc bất ngờ")
                stream_buf.extend(ch)
            out_b = bytes(stream_buf[:n])
            del stream_buf[:n]
            return out_b

        for _ in range(10):
            b0, b1 = _read_exact(2)
            opcode = b0 & 0x0F
            is_masked = bool(b1 & 0x80)
            length = b1 & 0x7F
            if length == 126:
                length = struct.unpack("!H", _read_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", _read_exact(8))[0]
            mkey = _read_exact(4) if is_masked else b""
            payload = _read_exact(length)
            if is_masked:
                payload = bytes(b ^ mkey[i % 4] for i, b in enumerate(payload))
            if opcode == 0x1:
                rpc = json.loads(payload.decode("utf-8"))
                if rpc.get("id") == 1:
                    val_str = ((rpc.get("result") or {}).get("result") or {}).get("value")
                    return json.loads(val_str) if isinstance(val_str, str) else {}
            elif opcode == 0x8:
                break
        raise RuntimeError("Không nhận được kết quả đánh giá DOM từ CDP")
    finally:
        try:
            sock.close()
        except OSError:
            pass


def _is_temp_test_dir(p: Path) -> bool:
    s = str(p.resolve())
    tmp_root = str(Path(tempfile.gettempdir()).resolve())
    return s.startswith(tmp_root) or "/var/folders/" in s or s.startswith("/tmp/")


class DedicatedChromeHub:
    def __init__(self, data_dir: str | Path, connect=None, cdp_port: int | None = None, shared_profile_dir: Path | None = None):
        self.root = Path(data_dir)
        self.connect = connect
        self._lock = threading.Lock()

        cand_shared = shared_profile_dir or AFFILIATE_PENG_SHARED_PROFILE
        if not _is_temp_test_dir(self.root) and cand_shared.is_dir():
            self.using_shared_peng_profile = True
            self.profile_dir = cand_shared
            self.state_file = self.profile_dir / ".peng_cdp_state.json"
            self.cdp_port = int(cdp_port or PREFERRED_SHARED_CDP_PORT)
            self.profile_display_name = "Peng - Kalodata & TikTok Creator (Dùng chung affiliate-peng)"
        else:
            self.using_shared_peng_profile = False
            self.profile_dir = self.root / "browser_profiles" / "dianshang_dedicated"
            self.state_file = self.profile_dir / ".gs_cdp_state.json"
            self.cdp_port = int(cdp_port or FALLBACK_LOCAL_CDP_PORT)
            self.profile_display_name = "Global Shop Dianshang Dedicated"
            self.profile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            if os.name == "posix":
                self.profile_dir.chmod(0o700)

    @staticmethod
    def _probe_port_alive(port: int | None) -> bool:
        if not port or port <= 0 or port > 65535:
            return False
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{int(port)}/json/version", timeout=1.2) as resp:
                if resp.status != 200:
                    return False
                data = json.loads(resp.read().decode("utf-8"))
                return isinstance(data, dict) and "webSocketDebuggerUrl" in data
        except Exception:
            return False

    def get_live_port(self) -> int | None:
        if self.state_file.is_file():
            try:
                st = json.loads(self.state_file.read_text(encoding="utf-8"))
                p = int(st.get("port") or 0)
                if self._probe_port_alive(p):
                    return p
            except Exception:
                pass
        dt_file = self.profile_dir / "DevToolsActivePort"
        if dt_file.is_file():
            try:
                lines = dt_file.read_text(encoding="utf-8").splitlines()
                if lines and self._probe_port_alive(int(lines[0].strip())):
                    return int(lines[0].strip())
            except Exception:
                pass
        if self._probe_port_alive(self.cdp_port):
            return self.cdp_port
        return None

    def is_running(self) -> bool:
        return self.get_live_port() is not None

    def list_tabs(self, port: int | None = None) -> list[dict]:
        live_p = port or self.get_live_port()
        if not live_p:
            return []
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{live_p}/json/list", timeout=2.0) as resp:
                items = json.loads(resp.read().decode("utf-8"))
                return [x for x in items if isinstance(x, dict) and x.get("type") == "page"]
        except Exception:
            return []

    def cdp_tabs(self) -> list[dict]:
        return self.list_tabs()

    def open_or_focus_tab(self, port: int, domains: tuple[str, ...], target_url: str, focus: bool = False) -> dict | None:
        tabs = self.list_tabs(port)
        matched = next((t for t in tabs if any(d in str(t.get("url") or "").lower() for d in domains)), None)
        if matched:
            if focus and matched.get("id"):
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/json/activate/{matched['id']}", timeout=2).read()
                except Exception:
                    pass
            return matched
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/json/new?{quote(target_url, safe=':/?&=%#+-_.~')}", method="PUT")
            with urllib.request.urlopen(req, timeout=4) as resp:
                created = json.loads(resp.read().decode("utf-8"))
            time.sleep(2.2)
            return created
        except Exception:
            return None

    def status(self) -> dict:
        live_p = self.get_live_port()
        running = live_p is not None
        tabs = self.list_tabs(live_p) if running else []
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
            "cdp_port": live_p or self.cdp_port,
            "using_shared_peng_profile": self.using_shared_peng_profile,
            "profile_path_label": "affiliate-peng/peng_dedicated" if self.using_shared_peng_profile else "dianshang_dedicated",
            "browser_available": bool(find_chrome_binary()),
            "profile_name": self.profile_display_name,
            "open_tabs_count": len(tabs),
            "portals": portals,
        }

    def open_portal(self, portal_key: str = "kalodata") -> dict:
        if portal_key not in PORTAL_REGISTRY:
            raise ApiError("400 Bad Request", f"Cổng trình duyệt không hợp lệ: {portal_key}")
        meta = PORTAL_REGISTRY[portal_key]
        target_url = meta["default_url"]
        chrome_bin = find_chrome_binary()
        if not chrome_bin:
            raise ApiError("503 Service Unavailable", "Không tìm thấy Google Chrome / Chromium trên máy")

        with self._lock:
            live_p = self.get_live_port()
            if live_p:
                self.open_or_focus_tab(live_p, meta["allowed_domains"], target_url, focus=True)
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
                    json.dumps({"pid": proc.pid, "port": self.cdp_port, "profile_name": self.profile_display_name, "started_at": now()}),
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
        return self.status()

    def dispatch(self, path: str, method: str, env, read_json):
        if path == "/api/connections/browser" and method == "GET":
            return "200 OK", self.status()
        if path == "/api/connections/browser/open" and method == "POST":
            body = json_object(read_json, env)
            portal = str(body.get("portal") or "kalodata")
            return "200 OK", self.open_portal(portal)
        return None
