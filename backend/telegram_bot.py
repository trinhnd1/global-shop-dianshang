"""Telegram Bot (@tc_global1_shop_bot) notifier, command poller, strict Chat/User ID allowlist & Tailscale link resolver."""
from collections import deque
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request

from . import PRODUCT_NAME, __version__, settings
from .history_log import MODULE_LABELS, MODULE_ROUTES
from .responses import json_object, now

_TG_TOKEN_SCRUB_RE = re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,55}\b")


def scrub_tg_text(s: str) -> str:
    return _TG_TOKEN_SCRUB_RE.sub("[REDACTED_TG_BOT_TOKEN]", s or "")


def parse_allowed_user_ids(cfg_notify: dict) -> set[str]:
    allowed: set[str] = set()
    for field in ("telegram_allowed_user_ids", "telegram_chat_id"):
        raw = str(cfg_notify.get(field) or "")
        for tok in re.split(r"[,;\s]+", raw):
            tok = tok.strip()
            if tok and tok.lstrip("-").isdigit():
                allowed.add(tok)
    return allowed


def _find_tailscale_bin() -> str | None:
    for p in (
        "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
        "/opt/homebrew/bin/tailscale",
        "/usr/local/bin/tailscale",
        shutil.which("tailscale") or "",
    ):
        if p and Path(p).is_file():
            return p
    return None


def detect_tailscale_remote_base_url(web_port: int = 8999, override_url: str = "") -> str:
    if override_url and override_url.strip():
        return override_url.strip().rstrip("/")
    ts_bin = _find_tailscale_bin()
    if not ts_bin:
        return f"http://127.0.0.1:{web_port}"
    try:
        p1 = subprocess.run([ts_bin, "serve", "status", "--json"], capture_output=True, text=True, timeout=4)
        if p1.returncode == 0 and p1.stdout.strip():
            sv = json.loads(p1.stdout)
            web_map = sv.get("Web") or {}
            for host_port, hcfg in web_map.items():
                handlers = (hcfg or {}).get("Handlers") or {}
                proxy = (handlers.get("/") or {}).get("Proxy") or ""
                if f":{web_port}" in proxy:
                    scheme = "https" if ":443" in host_port else "http"
                    clean_hp = host_port.replace(":80", "").replace(":443", "")
                    return f"{scheme}://{clean_hp}"
    except Exception:
        pass
    try:
        p2 = subprocess.run([ts_bin, "status", "--self", "--json"], capture_output=True, text=True, timeout=4)
        if p2.returncode == 0 and p2.stdout.strip():
            st = json.loads(p2.stdout)
            dns = ((st.get("Self") or {}).get("DNSName") or "").rstrip(".")
            if dns:
                return f"http://{dns}:{web_port}"
    except Exception:
        pass
    return f"http://127.0.0.1:{web_port}"


class TelegramBotService:
    def __init__(
        self,
        connect,
        secrets,
        history_logs,
        web_port: int = 8999,
        http_runner=None,
    ):
        self.connect = connect
        self.secrets = secrets
        self.history_logs = history_logs
        self.watches_service = None
        self.products_service = None
        self.ecosystems_service = None
        self.web_port = web_port
        self._http_runner = http_runner or self._default_http_runner
        self._queue = deque(maxlen=500)
        self._lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._stop = threading.Event()
        self._started = False
        self._last_error = ""
        self._bot_info: dict = {}
        self._rejected_count = 0
        self._sent_count = 0

    @staticmethod
    def _default_http_runner(token: str, method: str, payload: dict | None = None, timeout: int = 16) -> dict:
        url = f"https://api.telegram.org/bot{token}/{method}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if data is not None else {}
        last_exc: Exception | None = None
        for attempt in range(3):
            req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                raw = exc.read().decode("utf-8", errors="replace")
                if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(0.8 * (attempt + 1))
                    last_exc = RuntimeError(f"Telegram HTTP {exc.code}: {scrub_tg_text(raw)[:200]}")
                    continue
                raise RuntimeError(f"Telegram HTTP {exc.code}: {scrub_tg_text(raw)[:200]}") from None
            except Exception as exc:
                last_exc = exc
                if attempt < 2:
                    time.sleep(0.7 * (attempt + 1))
                    continue
        # Fallback via OPi SOCKS5 only if direct connection to api.telegram.org experienced TCP/TLS reset
        curl_bin = shutil.which("curl")
        if curl_bin:
            try:
                cmd = [curl_bin, "-fsS", "-m", str(max(10, timeout)), "--socks5-hostname", "100.113.217.101:1080"]
                if data is not None:
                    cmd.extend(["-X", "POST", "-H", "Content-Type: application/json", "-d", data.decode("utf-8")])
                cmd.append(url)
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=max(12, timeout + 4))
                if p.returncode == 0 and p.stdout.strip():
                    return json.loads(p.stdout)
            except Exception:
                pass
        raise RuntimeError(scrub_tg_text(str(last_exc or "Telegram network error"))[:220]) from None

    def start(self):
        if self._started:
            return
        self._started = True
        threading.Thread(target=self._notifier_loop, name="gs-telegram-notifier", daemon=True).start()
        threading.Thread(target=self._poller_loop, name="gs-telegram-poller", daemon=True).start()

    def remote_url(self, subpath: str = "") -> str:
        cfg = settings.read_settings(self.connect, self.secrets)
        base = detect_tailscale_remote_base_url(self.web_port, cfg["notify"].get("result_base_url", ""))
        return base + (subpath if subpath.startswith("/") or not subpath else f"/{subpath}")

    def send_text(self, text_msg: str, chat_id: str | None = None, token_override: str | None = None) -> dict:
        cfg = settings.read_settings(self.connect, self.secrets)
        ntf = cfg["notify"]
        tok = (token_override or ntf.get("telegram_token") or "").strip()
        target_chat = str(chat_id or ntf.get("telegram_chat_id") or "").strip()
        allowed = parse_allowed_user_ids(ntf)
        if not tok:
            raise ValueError("Chưa cấu hình Telegram Bot Token")
        if not target_chat:
            raise ValueError("Chưa cấu hình Telegram Chat ID")
        if allowed and target_chat not in allowed:
            self._rejected_count += 1
            raise PermissionError(f"Chat ID {target_chat} không nằm trong danh sách cho phép")
        safe_body = scrub_tg_text(text_msg)[:3950]
        res = self._http_runner(tok, "sendMessage", {"chat_id": target_chat, "text": safe_body, "disable_web_page_preview": True})
        if not res.get("ok"):
            raise RuntimeError(f"Telegram từ chối gửi: {scrub_tg_text(str(res))[:180]}")
        self._sent_count += 1
        return res.get("result") or {}

    def check_bot(self, token_override: str = "") -> dict:
        cfg = settings.read_settings(self.connect, self.secrets)
        tok = settings.resolve_incoming_secret(token_override, cfg["notify"].get("telegram_token", ""), "Telegram Bot Token")
        res = self._http_runner(tok, "getMe", None, timeout=12)
        if not res.get("ok"):
            raise RuntimeError("Token Telegram không hợp lệ")
        self._bot_info = res.get("result") or {}
        return {
            "ok": True,
            "bot": {
                "id": self._bot_info.get("id"),
                "username": self._bot_info.get("username"),
                "first_name": self._bot_info.get("first_name"),
            },
            "allowed_ids": sorted(parse_allowed_user_ids(cfg["notify"])),
            "tailscale_url": self.remote_url(),
        }

    def enqueue_log_notification(self, log_item: dict):
        with self._lock:
            self._queue.append(dict(log_item))

    def _notifier_loop(self):
        last_sweep = 0.0
        while not self._stop.is_set():
            item = None
            with self._lock:
                if self._queue:
                    item = self._queue.popleft()
            if item is not None:
                try:
                    self._deliver_log_item(item)
                except Exception as exc:
                    self._last_error = scrub_tg_text(str(exc))[:240]
                time.sleep(0.25)
                continue

            # Durable Outbox Sweep every 10s so 100% of GS-XXXX logs & notifications are guaranteed delivered!
            now_mono = time.monotonic()
            if now_mono - last_sweep >= 10.0:
                last_sweep = now_mono
                try:
                    self.sync_pending_logs(limit=15)
                except Exception as exc:
                    self._last_error = scrub_tg_text(str(exc))[:240]
            time.sleep(1.0)

    def sync_pending_logs(self, limit: int = 25) -> dict:
        cfg = settings.read_settings(self.connect, self.secrets)
        ntf = cfg["notify"]
        if not ntf.get("telegram_enabled") or not ntf.get("telegram_token") or not ntf.get("telegram_chat_id"):
            return {"synced": 0, "skipped_disabled": True}
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT log_id, status, summary, telegram_sync_hash
                FROM activity_history_logs
                ORDER BY seq_no ASC
                """
            ).fetchall()
        pending_ids: list[str] = []
        for r in rows:
            sig = hashlib.sha256(f"{r['log_id']}|{r['status']}|{r['summary']}".encode("utf-8")).hexdigest()[:24]
            if r["telegram_sync_hash"] != sig:
                pending_ids.append(r["log_id"])
                if len(pending_ids) >= limit:
                    break
        sent_n = 0
        for lid in pending_ids:
            full_item = self.history_logs.get_log(lid)
            if full_item:
                res = self.deliver_log_immediately(full_item, force=False)
                if res.get("delivered"):
                    sent_n += 1
                time.sleep(0.2)
        return {"synced": sent_n, "checked_pending": len(pending_ids)}

    def _format_log_message(self, item: dict) -> str:
        st = item.get("status") or "completed"
        icon = {"running": "⏳", "completed": "✅", "failed": "❌", "cancelled": "🛑", "info": "🔔"}.get(st, "📌")
        st_vi = {
            "running": "Đang chạy",
            "completed": "Hoàn thành",
            "failed": "Thất bại",
            "cancelled": "Đã dừng",
            "info": "Thông báo",
        }.get(st, st)
        gs_code = item.get("gs_code") or ""
        mod = item.get("module") or "system"
        mod_lbl = MODULE_LABELS.get(mod, item.get("module_label") or mod)
        dur_ms = int(item.get("duration_ms") or 0)
        dur_str = f"{dur_ms / 1000.0:.1f}s" if dur_ms >= 1000 else f"{dur_ms}ms"
        cost_val = float(item.get("cost_usd") or 0.0)

        lines = [
            f"{icon} [{gs_code}] {item.get('title')}",
            f"• Phân hệ: {mod_lbl} | Trạng thái: {st_vi}",
            f"• Kết quả: {item.get('summary') or '—'}",
            f"• Thời lượng: {dur_str} | Chi phí API: ${cost_val:.4f}",
        ]

        # Include rich highlights from payload / job step logs when available
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        extra_lines = payload.get("highlights") if isinstance(payload.get("highlights"), list) else []
        for hl in extra_lines[:6]:
            if hl:
                lines.append(f"  ◦ {str(hl)[:140]}")

        step_logs = item.get("step_logs") if isinstance(item.get("step_logs"), list) else []
        if step_logs and st in ("completed", "failed"):
            lines.append("• Nhật ký bước chạy gần nhất:")
            for sl in step_logs[-3:]:
                lines.append(f"  » {str(sl)[:130]}")

        mod_route = MODULE_ROUTES.get(mod, "/nhat-ky")
        remote_log = self.remote_url(f"/nhat-ky?gs={gs_code}")
        remote_tab = self.remote_url(mod_route)
        lines.append(f"🔗 Chi tiết Nhật ký: {remote_log}")
        if mod_route != "/nhat-ky":
            lines.append(f"🌐 Mở phân hệ: {remote_tab}")
        return "\n".join(lines)

    def deliver_log_immediately(self, item: dict, force: bool = False) -> dict:
        cfg = settings.read_settings(self.connect, self.secrets)
        ntf = cfg["notify"]
        if not ntf.get("telegram_enabled") or not ntf.get("telegram_token") or not ntf.get("telegram_chat_id"):
            return {"delivered": False, "reason": "disabled_or_unconfigured"}
        st = item.get("status") or "completed"
        sync_sig = hashlib.sha256(f"{item.get('log_id')}|{st}|{item.get('summary')}".encode("utf-8")).hexdigest()[:24]
        if not force:
            with self.connect() as conn:
                row = conn.execute(
                    "SELECT telegram_sync_hash FROM activity_history_logs WHERE log_id=?",
                    (item.get("log_id"),),
                ).fetchone()
                if row and row["telegram_sync_hash"] == sync_sig:
                    return {"delivered": False, "reason": "already_synced"}

        msg = self._format_log_message(item)
        with self._send_lock:
            try:
                sent = self.send_text(msg)
                msg_id = str(sent.get("message_id") or "")
                self._last_error = ""
                with self.connect() as conn:
                    conn.execute(
                        """
                        UPDATE activity_history_logs
                        SET telegram_message_id=?, telegram_notified_at=?, telegram_sync_hash=?, telegram_last_error=''
                        WHERE log_id=?
                        """,
                        (msg_id, now(), sync_sig, item.get("log_id")),
                    )
                return {"delivered": True, "message_id": msg_id}
            except Exception as exc:
                err_txt = scrub_tg_text(str(exc))[:240]
                self._last_error = err_txt
                with self.connect() as conn:
                    conn.execute(
                        "UPDATE activity_history_logs SET telegram_last_error=? WHERE log_id=?",
                        (err_txt, item.get("log_id")),
                    )
                raise

    def _deliver_log_item(self, item: dict):
        full_item = self.history_logs.get_log(item.get("log_id") or "") or item
        self.deliver_log_immediately(full_item, force=False)

    def _poller_loop(self):
        offset = 0
        drained = False
        while not self._stop.is_set():
            cfg = settings.read_settings(self.connect, self.secrets)
            ntf = cfg["notify"]
            tok = (ntf.get("telegram_token") or "").strip()
            if not ntf.get("telegram_enabled") or not tok:
                time.sleep(5.0)
                continue
            try:
                if not drained:
                    init_res = self._http_runner(tok, "getUpdates", {"offset": -1, "timeout": 1}, timeout=8)
                    for u in init_res.get("result") or []:
                        offset = max(offset, int(u.get("update_id", 0)) + 1)
                    drained = True
                res = self._http_runner(tok, "getUpdates", {"offset": offset, "timeout": 10}, timeout=16)
                for upd in res.get("result") or []:
                    offset = max(offset, int(upd.get("update_id", 0)) + 1)
                    self._handle_update(upd, ntf, tok)
            except Exception as exc:
                self._last_error = scrub_tg_text(str(exc))[:240]
                time.sleep(4.0)

    def _handle_update(self, upd: dict, ntf: dict, tok: str):
        msg = upd.get("message") or {}
        txt = (msg.get("text") or "").strip()
        if not txt:
            return
        chat_id = str((msg.get("chat") or {}).get("id") or "")
        user_id = str((msg.get("from") or {}).get("id") or "")
        allowed = parse_allowed_user_ids(ntf)
        if not allowed or (user_id not in allowed and chat_id not in allowed):
            self._rejected_count += 1
            try:
                self._http_runner(
                    tok,
                    "sendMessage",
                    {"chat_id": chat_id, "text": "⛔ Từ chối truy cập: ID của bạn không nằm trong danh sách được phép của Global Shop Dianshang."},
                    timeout=8,
                )
            except Exception:
                pass
            return

        cmd = txt.split()[0].lower().split("@")[0]
        arg = txt[len(txt.split()[0]):].strip()
        reply = self._build_command_reply(cmd, arg)
        self.send_text(reply, chat_id=chat_id, token_override=tok)

    def _build_command_reply(self, cmd: str, arg: str) -> str:
        rem = self.remote_url()
        loc = f"http://127.0.0.1:{self.web_port}"
        if cmd in ("/start", "/help"):
            return (
                f"🏬 {PRODUCT_NAME} v{__version__}\n"
                f"Toàn bộ thông báo & nhật ký công việc (GS-XXXX) đang được đồng bộ tự động qua Bot này.\n\n"
                f"Các lệnh hỗ trợ:\n"
                f"• /status — Tổng quan Kho SP, Hệ sinh thái, Theo dõi & Nhật ký\n"
                f"• /last (hoặc /logs) — 8 tác vụ GS-XXXX gần nhất\n"
                f"• /eco — Danh mục Hệ sinh thái & Phụ kiện SP đang theo dõi\n"
                f"• /watches — Danh sách Từ khoá / SP / Shop đang theo dõi\n"
                f"• /gs GS-0001 — Xem chi tiết 1 mã công việc\n\n"
                f"🌐 Tailscale: {rem}\n"
                f"🖥 Local: {loc}"
            )
        if cmd == "/status":
            prod_cnt = self.products_service.count_all() if self.products_service else 0
            watch_cnt = len(self.watches_service.list_watches()) if self.watches_service else 0
            eco_cnt = len(self.ecosystems_service.list_collections()) if self.ecosystems_service else 0
            kpis = self.history_logs.summary_kpis()
            logs = self.history_logs.list_logs(limit=3)
            return (
                f"📊 Trạng thái {PRODUCT_NAME} v{__version__}\n"
                f"• Sản phẩm trong Kho: {prod_cnt}\n"
                f"• Danh mục Hệ sinh thái SP: {eco_cnt}\n"
                f"• Mục đang theo dõi (Từ khoá/SP/Shop): {watch_cnt}\n"
                f"• Nhật ký GS-XXXX: {kpis['total']} (Đã báo Telegram: {kpis['telegram_notified']}/{kpis['total']})\n"
                f"• Tác vụ gần nhất: {logs[0]['gs_code'] + ' - ' + logs[0]['title'] if logs else 'Chưa có'}\n"
                f"🌐 Tailscale: {rem}"
            )
        if cmd in ("/eco", "/ecosystems") and self.ecosystems_service:
            cols = self.ecosystems_service.list_collections()[:8]
            if not cols:
                return f"Chưa có danh mục Hệ sinh thái nào. Mở tại: {self.remote_url('/he-sinh-thai')}"
            lines = ["🎯 Danh mục Hệ sinh thái & Phụ kiện SP:"]
            for c in cols:
                hl = (c.get("index_summary") or {}).get("headline") or c["name"]
                sched = "⏰ Cào 24h" if c.get("daily_schedule_enabled") else "⏸ Thủ công"
                lines.append(f"• {hl} [{sched}]")
            lines.append(f"🌐 Mở Hệ sinh thái: {self.remote_url('/he-sinh-thai')}")
            return "\n".join(lines)
        if cmd in ("/last", "/jobs", "/logs"):
            logs = self.history_logs.list_logs(limit=8)
            if not logs:
                return "Chưa có nhật ký công việc nào."
            lines = [f"🧾 8 nhật ký gần nhất ({PRODUCT_NAME}):"]
            for it in logs:
                lines.append(f"• [{it['gs_code']}] ({it['status']}) {it['title']} — {it['summary'][:90]}")
            lines.append(f"🌐 Xem đầy đủ: {self.remote_url('/nhat-ky')}")
            return "\n".join(lines)
        if cmd == "/watches" and self.watches_service:
            ws = self.watches_service.list_watches()[:8]
            if not ws:
                return f"Chưa có mục theo dõi nào. Thêm tại: {self.remote_url('/theo-doi')}"
            lines = ["🔭 Đang theo dõi Từ khoá / SP / Shop:"]
            for w in ws:
                sm = w.get("last_summary") or {}
                new_c = sm.get("new_items_count", 0)
                lines.append(f"• [{w['watch_type'].upper()} · {w['platform']}] {w['title']} (Mới: +{new_c})")
            return "\n".join(lines)
        if cmd == "/gs" or cmd.upper().startswith("GS-"):
            target = arg if cmd == "/gs" else cmd
            item = self.history_logs.get_log(target)
            if not item:
                return f"Không tìm thấy mã công việc: {target}"
            return (
                f"📌 [{item['gs_code']}] {item['title']}\n"
                f"• Phân hệ: {item['module']} | Trạng thái: {item['status']}\n"
                f"• Tóm tắt: {item['summary']}\n"
                f"• Chi phí: ${float(item['cost_usd'] or 0.0):.4f} | Thời lượng: {item['duration_ms']}ms\n"
                f"🔗 {self.remote_url('/nhat-ky?gs=' + item['gs_code'])}"
            )
        return "Lệnh không hợp lệ — gõ /help để xem danh sách lệnh."

    def status_view(self) -> dict:
        cfg = settings.read_settings(self.connect, self.secrets)
        ntf = cfg["notify"]
        kpis = self.history_logs.summary_kpis() if self.history_logs else {}
        return {
            "enabled": bool(ntf.get("telegram_enabled")),
            "token_configured": bool(ntf.get("telegram_token")),
            "bot_username": self._bot_info.get("username") or ntf.get("telegram_bot_username") or "tc_global1_shop_bot",
            "chat_id": ntf.get("telegram_chat_id") or "",
            "allowed_user_ids": sorted(parse_allowed_user_ids(ntf)),
            "sent_count": self._sent_count,
            "logs_total": kpis.get("total", 0),
            "logs_notified": kpis.get("telegram_notified", 0),
            "logs_pending": kpis.get("telegram_pending", 0),
            "rejected_count": self._rejected_count,
            "last_error": self._last_error,
            "tailscale_url": self.remote_url(),
        }

    def dispatch(self, path: str, method: str, env, read_json):
        if path == "/api/providers/telegram/status" and method == "GET":
            return "200 OK", self.status_view()
        if path == "/api/providers/telegram/sync-pending" and method == "POST":
            res = self.sync_pending_logs(limit=50)
            return "200 OK", {
                "ok": True,
                **res,
                "summary": f"Đã đồng bộ {res['synced']} nhật ký chưa gửi sang Telegram Bot!",
            }
        if path == "/api/providers/telegram/check" and method == "POST":
            body = json_object(read_json, env)
            return "200 OK", self.check_bot(str(body.get("telegram_token") or ""))
        if path == "/api/providers/telegram/test" and method == "POST":
            body = json_object(read_json, env)
            custom_msg = str(body.get("message") or "").strip()
            msg = custom_msg or (
                f"✅ Kết nối Telegram Bot @{self.status_view()['bot_username']} thành công!\n"
                f"Hệ thống: {PRODUCT_NAME} v{__version__}\n"
                f"🌐 Truy cập Tailscale: {self.remote_url()}\n"
                f"🖥 Truy cập Local: http://127.0.0.1:{self.web_port}"
            )
            sent = self.send_text(msg)
            return "200 OK", {"ok": True, "message_id": sent.get("message_id"), "tailscale_url": self.remote_url()}
        return None
