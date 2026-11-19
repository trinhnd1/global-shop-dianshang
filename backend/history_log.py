"""Unified Activity & Job History Log with monotonic GS-XXXX codes, secret scrubbing, CSV export & Telegram sync."""
import csv
import io
import json
import re
from urllib.parse import parse_qs

from .responses import ApiError, Raw, json_object, now, safe_csv_cell, text

SENSITIVE_KEY_RE = re.compile(
    r"(?:api_key|apikey|token|secret|password|passwd|cookie|authorization|base64|file_data|treg_key|typesafe_key)",
    re.IGNORECASE,
)
INLINE_SECRET_RE = re.compile(
    r"(?:\b\d{8,12}:[A-Za-z0-9_-]{30,55}\b|\bapify_api_[A-Za-z0-9]{12,}\b|\btreg_[A-Za-z0-9_-]{12,}\b|\bgs_mcp_[a-f0-9]{16,}\b)"
)
LOCAL_PATH_RE = re.compile(r"/Users/[^\s\"',]+")


def format_gs_code(seq_no: int | None) -> str:
    if not seq_no:
        return ""
    return f"GS-{int(seq_no):04d}"


def scrub_for_history(obj, depth: int = 0):
    if depth > 7:
        return "[TRUNCATED]"
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):
        s = INLINE_SECRET_RE.sub("[REDACTED_SECRET]", obj)
        s = LOCAL_PATH_RE.sub("[LOCAL_PATH]", s)
        return s[:1200] if len(s) > 1200 else s
    if isinstance(obj, list):
        return [scrub_for_history(x, depth + 1) for x in obj[:30]]
    if isinstance(obj, dict):
        out = {}
        for k, v in list(obj.items())[:45]:
            ks = str(k)
            if SENSITIVE_KEY_RE.search(ks):
                out[ks] = "[REDACTED]"
            else:
                out[ks] = scrub_for_history(v, depth + 1)
        return out
    return str(obj)[:400]


def classify_http_module(path: str) -> tuple[str, str] | None:
    if path.startswith("/api/settings") or path.startswith("/api/providers/") or path.startswith("/api/connections/"):
        return ("settings", "Cập nhật cấu hình / kết nối")
    if path.startswith("/api/hunt/"):
        return ("hunt", "Săn sản phẩm bán chạy")
    if path.startswith("/api/keywords/"):
        return ("keywords", "Tra cứu từ khoá Shopee / TikTok")
    if path.startswith("/api/watches"):
        return ("watches", "Theo dõi Từ khoá / SP / Shop")
    if path.startswith("/api/shops"):
        return ("shops", "Kho Shop & Quét SP theo Shop")
    if path.startswith("/api/sourcing"):
        return ("china_sourcing", "Nguồn hàng 1688 / Taobao / Pinduoduo")
    if path.startswith("/api/products") or path.startswith("/api/results"):
        return ("products", "Kho & Phân loại Sản phẩm")
    if path.startswith("/api/spy"):
        return ("spy", "Soi Sản phẩm / Fanpage")
    if path.startswith("/api/videos") or path.startswith("/api/video-cloner"):
        return ("videos", "Đánh giá & Clone Video")
    if path.startswith("/api/campaigns") or path.startswith("/api/sales"):
        return ("campaigns", "Chiến dịch Ngành hàng & Doanh số")
    if path.startswith("/api/mcp/"):
        return ("mcp", "Cổng MCP Agent")
    return None


class HistoryLogService:
    def __init__(self, connect):
        self.connect = connect
        self.telegram_sink = None

    def _next_seq(self, conn) -> int:
        conn.execute("UPDATE history_log_sequence SET last_seq = last_seq + 1 WHERE id = 1")
        return int(conn.execute("SELECT last_seq FROM history_log_sequence WHERE id = 1").fetchone()[0])

    def record_event(
        self,
        module: str,
        action_type: str,
        title: str,
        status: str = "completed",
        duration_ms: int = 0,
        cost_usd: float = 0.0,
        summary: str = "",
        payload: dict | None = None,
        log_id: str | None = None,
        notify_telegram: bool = True,
    ) -> dict:
        ts = now()
        lid = log_id or f"act_{ts.replace(':', '').replace('-', '')}_{module}"
        clean_payload = scrub_for_history(payload or {})
        clean_summary = scrub_for_history(summary or title)
        clean_title = scrub_for_history(title)

        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute("SELECT seq_no FROM activity_history_logs WHERE log_id = ?", (lid,)).fetchone()
            if existing:
                seq = int(existing["seq_no"])
                conn.execute(
                    """
                    UPDATE activity_history_logs
                    SET status=?, duration_ms=?, cost_usd=?, summary=?, payload_json=?, updated_at=?
                    WHERE log_id=?
                    """,
                    (
                        status,
                        int(duration_ms),
                        round(float(cost_usd or 0.0), 6),
                        str(clean_summary)[:500],
                        json.dumps(clean_payload, ensure_ascii=False),
                        ts,
                        lid,
                    ),
                )
            else:
                # Ensure unique lid if rapid synchronous calls happen in same second
                base_lid = lid
                suffix = 1
                while conn.execute("SELECT 1 FROM activity_history_logs WHERE log_id = ?", (lid,)).fetchone():
                    suffix += 1
                    lid = f"{base_lid}_{suffix}"
                seq = self._next_seq(conn)
                conn.execute(
                    """
                    INSERT INTO activity_history_logs
                    (log_id, seq_no, module, action_type, title, status, duration_ms, cost_usd, summary, payload_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        lid,
                        seq,
                        module,
                        action_type,
                        str(clean_title)[:240],
                        status,
                        int(duration_ms),
                        round(float(cost_usd or 0.0), 6),
                        str(clean_summary)[:500],
                        json.dumps(clean_payload, ensure_ascii=False),
                        ts,
                        ts,
                    ),
                )

        item = self.get_log(lid)
        if notify_telegram and self.telegram_sink is not None and item:
            try:
                self.telegram_sink.enqueue_log_notification(item)
            except Exception:
                pass
        return item or {"log_id": lid, "gs_code": format_gs_code(seq)}

    def sync_job_created(self, job_id: str, kind: str, title: str, est_usd: float, meta: dict) -> str:
        ev = self.record_event(
            module=kind,
            action_type="job_run",
            title=title,
            status="running",
            cost_usd=est_usd,
            summary=f"Đang chạy tiến trình ({kind})",
            payload=meta,
            log_id=f"job_{job_id}",
            notify_telegram=True,
        )
        return ev.get("gs_code", "")

    def sync_job_finished(self, job_id: str, status: str, duration_ms: int, actual_usd: float, summary: str, payload: dict):
        self.record_event(
            module=payload.get("kind") or "job",
            action_type="job_run",
            title=payload.get("title") or summary or f"Tiến trình {job_id}",
            status=status,
            duration_ms=duration_ms,
            cost_usd=actual_usd,
            summary=summary,
            payload=payload,
            log_id=f"job_{job_id}",
            notify_telegram=True,
        )

    def record_http_action(
        self,
        method: str,
        path: str,
        query_string: str,
        http_status: str,
        duration_ms: int,
        req_body,
        res_body,
    ):
        if method not in ("POST", "PUT", "PATCH", "DELETE"):
            return
        if path in (
            "/api/providers/telegram/test",
            "/api/providers/telegram/check",
            "/api/hunt/estimate",
            "/api/chat/send",
        ):
            return
        cls = classify_http_module(path)
        if cls is None:
            return
        # Avoid duplicate log row if endpoint already spawned a JobManager job
        if isinstance(res_body, dict) and (str(res_body.get("id", "")).startswith("job_") or res_body.get("job_id")):
            return
        module, label = cls
        ok = http_status.startswith("2")
        status = "completed" if ok else "failed"
        summary = ""
        if isinstance(res_body, dict):
            summary = str(res_body.get("summary") or res_body.get("detail") or "")[:280]
        if not summary:
            summary = f"{method} {path} -> {http_status}"
        self.record_event(
            module=module,
            action_type=f"{method} {path}",
            title=f"{label} ({path})",
            status=status,
            duration_ms=duration_ms,
            summary=summary,
            payload={"request": req_body, "response": res_body, "http_status": http_status},
            notify_telegram=True,
        )

    def list_logs(self, module: str = "", status: str = "", q: str = "", limit: int = 80) -> list[dict]:
        clauses = []
        params: list = []
        if module:
            clauses.append("module = ?")
            params.append(module)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if q:
            clauses.append("(title LIKE ? OR summary LIKE ? OR CAST(seq_no AS TEXT) LIKE ?)")
            q_clean = q.upper().replace("GS-", "").lstrip("0") or q
            params.extend([f"%{q}%", f"%{q}%", f"%{q_clean}%"])
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(min(250, max(1, int(limit))))
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM activity_history_logs {where} ORDER BY seq_no DESC LIMIT ?",
                tuple(params),
            ).fetchall()
        return [self._format_row(r, include_payload=False) for r in rows]

    def get_log(self, id_or_gs: str) -> dict | None:
        raw = (id_or_gs or "").strip()
        if not raw:
            return None
        with self.connect() as conn:
            if raw.upper().startswith("GS-") and raw[3:].isdigit():
                row = conn.execute("SELECT * FROM activity_history_logs WHERE seq_no = ?", (int(raw[3:]),)).fetchone()
            elif raw.isdigit():
                row = conn.execute("SELECT * FROM activity_history_logs WHERE seq_no = ?", (int(raw),)).fetchone()
            else:
                row = conn.execute("SELECT * FROM activity_history_logs WHERE log_id = ?", (raw,)).fetchone()
        return self._format_row(row, include_payload=True) if row else None

    def update_note(self, id_or_gs: str, note: str) -> dict:
        item = self.get_log(id_or_gs)
        if not item:
            raise ApiError("404 Not Found", "Không tìm thấy nhật ký công việc")
        with self.connect() as conn:
            conn.execute(
                "UPDATE activity_history_logs SET note = ?, updated_at = ? WHERE log_id = ?",
                (note[:1000], now(), item["log_id"]),
            )
        return self.get_log(item["log_id"]) or item

    def export_csv(self) -> bytes:
        rows = self.list_logs(limit=250)
        buf = io.StringIO()
        buf.write("\ufeff")
        writer = csv.writer(buf, lineterminator="\r\n")
        writer.writerow(["Mã GS", "Phân hệ", "Tiêu đề", "Trạng thái", "Chi phí USD", "Thời gian (ms)", "Tóm tắt", "Ghi chú", "Tạo lúc"])
        for r in rows:
            writer.writerow([
                safe_csv_cell(r["gs_code"]),
                safe_csv_cell(r["module"]),
                safe_csv_cell(r["title"]),
                safe_csv_cell(r["status"]),
                r["cost_usd"],
                r["duration_ms"],
                safe_csv_cell(r["summary"]),
                safe_csv_cell(r["note"]),
                r["created_at"],
            ])
        return buf.getvalue().encode("utf-8")

    @staticmethod
    def _format_row(r, include_payload: bool = False) -> dict:
        d = {
            "log_id": r["log_id"],
            "seq_no": r["seq_no"],
            "gs_code": format_gs_code(r["seq_no"]),
            "module": r["module"],
            "action_type": r["action_type"],
            "title": r["title"],
            "status": r["status"],
            "duration_ms": r["duration_ms"],
            "cost_usd": r["cost_usd"],
            "summary": r["summary"],
            "note": r["note"],
            "telegram_notified_at": r["telegram_notified_at"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        if include_payload:
            d["payload"] = json.loads(r["payload_json"] or "{}")
        return d

    def dispatch(self, path: str, method: str, env, read_json):
        if path == "/api/history-logs" and method == "GET":
            qs = parse_qs(env.get("QUERY_STRING") or "")
            mod = (qs.get("module") or [""])[0]
            st = (qs.get("status") or [""])[0]
            q = (qs.get("q") or [""])[0]
            return "200 OK", {"logs": self.list_logs(module=mod, status=st, q=q)}
        if path == "/api/history-logs/export.csv" and method == "GET":
            data = self.export_csv()
            return "200 OK", Raw(
                data,
                [
                    ("Content-Type", "text/csv; charset=utf-8"),
                    ("Content-Disposition", 'attachment; filename="global-shop-history.csv"'),
                    ("Content-Length", str(len(data))),
                ],
            )
        if path.startswith("/api/history-logs/"):
            parts = path.strip("/").split("/")
            if len(parts) == 3 and method == "GET":
                item = self.get_log(parts[2])
                if not item:
                    raise ApiError("404 Not Found", "Không tìm thấy nhật ký này")
                return "200 OK", item
            if len(parts) == 4 and parts[3] == "note" and method == "POST":
                body = json_object(read_json, env)
                return "200 OK", self.update_note(parts[2], text(body.get("note"), "note", 1000))
        return None
