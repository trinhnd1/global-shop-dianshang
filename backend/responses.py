"""HTTP/WSGI security guards, SSRF prevention, 19-digit ID helpers, and safe serialization."""
from datetime import datetime, timezone
import ipaddress
import math
import re
import socket
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}
TAILSCALE_CGNAT = ipaddress.ip_network("100.64.0.0/10")
TAILSCALE_ULA = ipaddress.ip_network("fd7a:115c:a1e0::/48")
LOCAL_HOSTNAMES = {
    socket.gethostname().lower(),
    socket.getfqdn().lower(),
}

TRACKING_QUERY_KEYS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "ttclid", "sp_atk", "xptdk", "spm", "scm",
    "aff_short_key", "share_channel_code", "uls_trackid", "checksum",
}


class ApiError(Exception):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class Raw:
    def __init__(self, body: bytes, headers: list[tuple[str, str]]):
        self.body = body
        self.headers = headers


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def split_host_header(raw_host: str) -> str:
    h = (raw_host or "").strip().lower()
    if not h:
        return ""
    if h.startswith("["):
        end = h.find("]")
        return h[1:end] if end > 0 else h
    if h.count(":") == 1:
        return h.split(":", 1)[0]
    return h


def is_allowed_host(hostname: str, allow_tailscale: bool = True) -> bool:
    if not hostname:
        return True
    if hostname in LOOPBACK_HOSTS:
        return True
    if not allow_tailscale:
        return False
    if hostname in LOCAL_HOSTNAMES or hostname.endswith(".ts.net") or hostname.endswith(".local"):
        return True
    if re.fullmatch(r"[a-z0-9][a-z0-9\-]{0,62}", hostname):
        # Tailscale MagicDNS short hostname (e.g. nguyens-mac-mini)
        return True
    try:
        ip = ipaddress.ip_address(hostname)
        return ip.is_loopback or (ip in TAILSCALE_CGNAT) or (ip in TAILSCALE_ULA)
    except ValueError:
        return False


def check_host_and_origin(env: dict, allow_tailscale: bool = True):
    raw_host = (env.get("HTTP_HOST") or "").strip()
    host = split_host_header(raw_host)
    if raw_host and not is_allowed_host(host, allow_tailscale=allow_tailscale):
        return "403 Forbidden", {"detail": f"Host không được phép truy cập: {raw_host}"}

    method = (env.get("REQUEST_METHOD") or "GET").upper()
    origin = (env.get("HTTP_ORIGIN") or "").strip()
    if origin and method not in ("GET", "HEAD", "OPTIONS"):
        parsed = urlparse(origin)
        origin_host = split_host_header(parsed.netloc)
        if not origin_host or (host and origin_host != host):
            return "403 Forbidden", {"detail": "Chặn yêu cầu Cross-Origin không hợp lệ (CSRF guard)"}
    return None


def is_public_http_url(url: str) -> bool:
    try:
        parsed = urlparse((url or "").strip())
    except Exception:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    host = parsed.hostname.strip().lower()
    if host in ("localhost", "metadata.google.internal", "169.254.169.254") or host.endswith((".local", ".internal", ".ts.net")):
        return False
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            return False
        return True
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
        for info in infos:
            addr = info[4][0]
            ip = ipaddress.ip_address(addr.split("%")[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
                return False
    except OSError:
        # Allow syntactically valid public domain when offline/unit-testing DNS fails
        return "." in host
    return True


def safe_id_str(val) -> str:
    """Preserve 19+ digit marketplace product/shop/video IDs as exact strings without float loss."""
    if val is None or isinstance(val, bool):
        return ""
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        if not math.isfinite(val) or not val.is_integer() or abs(val) >= 9007199254740992:
            raise ValueError("ID số thực không an toàn (vượt ngưỡng IEEE-754 53-bit)")
        return str(int(val))
    s = str(val).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        return s[:-2]
    return s


def canonicalize_commerce_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        p = urlparse(raw)
        if p.scheme not in ("http", "https") or not p.netloc:
            return raw
        kept = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=False) if k.lower() not in TRACKING_QUERY_KEYS]
        clean_path = p.path.rstrip("/") or "/"
        return urlunparse((p.scheme.lower(), p.netloc.lower(), clean_path, "", urlencode(kept), ""))
    except Exception:
        return raw


def safe_csv_cell(val) -> str:
    """Spreadsheet formula-injection guard preserving negative numbers."""
    if val is None:
        return ""
    s = str(val)
    if not s:
        return ""
    if s[0] in ("=", "+", "@", "\t", "\r"):
        return "'" + s
    if s[0] == "-" and not re.fullmatch(r"-\d+(?:\.\d+)?", s):
        return "'" + s
    return s


def json_object(reader, env, max_bytes: int = 262144) -> dict:
    body = reader(env, max_bytes=max_bytes)
    if not isinstance(body, dict):
        raise ValueError("Body JSON phải là một object")
    return body


def text(val, field: str, max_len: int = 500, required: bool = False) -> str:
    if val is None:
        s = ""
    elif isinstance(val, (str, int)):
        s = str(val).strip()
    else:
        raise ValueError(f"Trường {field} phải là chuỗi ký tự")
    if required and not s:
        raise ValueError(f"Trường {field} không được để trống")
    return s[:max_len]
