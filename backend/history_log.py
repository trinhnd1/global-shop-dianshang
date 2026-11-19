"""Unified Activity & Job History Log with monotonic GS-XXXX codes, full Job hydration, resolved results, CSV export & Telegram sync."""
import csv
import io
import json
import re
from urllib.parse import parse_qs
import uuid

from .responses import ApiError, Raw, json_object, now, safe_csv_cell, text

SENSITIVE_KEY_RE = re.compile(
    r"(?:api_key|apikey|token|secret|password|passwd|cookie|authorization|base64|file_data|treg_key|typesafe_key)",
    re.IGNORECASE,
)
INLINE_SECRET_RE = re.compile(
    r"(?:\b\d{8,12}:[A-Za-z0-9_-]{30,55}\b|\bapify_api_[A-Za-z0-9]{12,}\b|\btreg_[A-Za-z0-9_-]{12,}\b|\bgs_mcp_[a-f0-9]{16,}\b)"
)
LOCAL_PATH_RE = re.compile(r"/Users/[^\s\"',]+")

MODULE_LABELS = {
    "hunt": "🔎 Săn SP & Painpoint",
    "ecosystems": "🎯 Hệ sinh thái & Phụ kiện SP",
    "kalodata": "📊 Kalodata & Global Selling",
    "desk300": "🤖 Xử lý SP 300+desk -> Jev",
    "apify_store": "🧩 Kho API Apify Store",
    "keywords": "🔑 Tra cứu Từ khoá",
    "watches": "🔭 Theo dõi Từ khoá/SP/Shop",
    "shops": "🏪 Shop của tôi & Kho Shop",
    "products": "📦 Kho & Phân loại SP",
    "china_sourcing": "🇨🇳 Nguồn 1688/PDD/Taobao",
    "spy": "🕵️ Soi SP & Fanpage",
    "videos": "🎬 Đánh giá & Clone Video",
    "campaigns": "🚀 Chiến dịch & Doanh số",
    "settings": "⚙️ Cài đặt & Kết nối",
    "mcp": "🔌 Cổng MCP Agent",
    "notify": "🔔 Thông báo Hệ thống",
    "job": "⏱ Tiến trình nền",
    "system": "⚙️ Thao tác Hệ thống",
}

MODULE_ROUTES = {
    "hunt": "/san-sp",
    "ecosystems": "/he-sinh-thai",
    "kalodata": "/he-sinh-thai",
    "desk300": "/luong-300-desk",
    "apify_store": "/apify-store",
    "keywords": "/tu-khoa",
    "watches": "/theo-doi",
    "shops": "/kho-shop",
    "products": "/kho/tat-ca",
    "china_sourcing": "/nguon-hang-tq",
    "spy": "/soi-sp-fanpage",
    "videos": "/clone-video",
    "campaigns": "/chien-dich",
    "settings": "/caidat",
    "mcp": "/caidat",
    "notify": "/nhat-ky",
    "job": "/nhat-ky",
    "system": "/nhat-ky",
}


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
        return s[:1500] if len(s) > 1500 else s
    if isinstance(obj, list):
        return [scrub_for_history(x, depth + 1) for x in obj[:40]]
    if isinstance(obj, dict):
        out = {}
        for k, v in list(obj.items())[:50]:
            ks = str(k)
            if SENSITIVE_KEY_RE.search(ks):
                out[ks] = "[REDACTED]"
            else:
                out[ks] = scrub_for_history(v, depth + 1)
        return out
    return str(obj)[:400]


def classify_http_module(path: str) -> tuple[str, str] | None:
    if path.startswith("/api/ecosystems"):
        return ("ecosystems", "Hệ sinh thái & Phụ kiện SP")
    if path.startswith("/api/kalodata") or path.startswith("/api/browser"):
        return ("kalodata", "Kalodata & Affiliate Global Selling")
    if path.startswith("/api/apify-store"):
        return ("apify_store", "Kho API Apify Store")
    if path.startswith("/api/settings") or path.startswith("/api/providers/") or path.startswith("/api/connections/"):
        return ("settings", "Cập nhật cấu hình / kết nối")
    if path.startswith("/api/hunt/") or path.startswith("/api/creators/"):
        return ("hunt", "Săn sản phẩm / Painpoint / Creator")
    if path.startswith("/api/desk300/"):
        return ("desk300", "Luồng xử lý SP 300+desk -> Jev")
    if path.startswith("/api/keywords/"):
        return ("keywords", "Tra cứu từ khoá Shopee / TikTok")
    if path.startswith("/api/watches"):
        return ("watches", "Theo dõi Từ khoá / SP / Shop")
    if path.startswith("/api/shops") or path.startswith("/api/my-shops"):
        return ("shops", "Shop của tôi & Kho Shop")
    if path.startswith("/api/sourcing"):
        return ("china_sourcing", "Nguồn hàng 1688 / Taobao / Pinduoduo")
    if path.startswith("/api/products") or path.startswith("/api/results") or path.startswith("/api/pins"):
        return ("products", "Kho & Phân loại Sản phẩm")
    if path.startswith("/api/spy"):
        return ("spy", "Soi Sản phẩm / Fanpage")
    if path.startswith("/api/videos") or path.startswith("/api/video-cloner"):
        return ("videos", "Đánh giá & Clone Video")
    if path.startswith("/api/campaigns") or path.startswith("/api/sales"):
        return ("campaigns", "Chiến dịch Ngành hàng & Doanh số")
    if path.startswith("/api/mcp/") or path in ("/mcp", "/mcp/"):
        return ("mcp", "Cổng MCP Agent")
    if path.startswith("/api/jobs"):
        return ("job", "Quản lý Tiến trình nền")
    if path.startswith("/api/"):
        return ("system", "Thao tác Hệ thống")
    return None


def describe_http_title(method: str, path: str, req_body, default_label: str) -> str:
    b = req_body if isinstance(req_body, dict) else {}
    if path == "/api/ecosystems/run":
        nm = str(b.get("name") or b.get("seed_keyword") or "").strip()
        return f"Chạy Luồng Hệ sinh thái: {nm}" if nm else "Chạy Luồng Hệ sinh thái & Phụ kiện SP"
    if path.endswith("/check-daily") and path.startswith("/api/ecosystems/"):
        return f"Cào mới & Đối chiếu Index Hàng ngày ({path.split('/')[3]})"
    if path == "/api/apify-store/sync":
        return "Quét & Đồng bộ Danh mục API Apify Store"
    if path == "/api/apify-store/call":
        act_s = str(b.get("actor_slug") or b.get("goal") or "").strip()
        return f"Gọi Actor Apify Store: {act_s}" if act_s else "Gọi Actor Apify Store"
    if path == "/api/kalodata/sync-from-affiliate":
        return "Đồng bộ Tài khoản Kalodata & Profile peng_dedicated"
    if path == "/api/keywords/research":
        kw = str(b.get("keyword") or "").strip()
        pl = str(b.get("platform") or "").strip()
        return f"Tra cứu Từ khoá: {kw} ({pl})" if kw else f"{default_label} ({path})"
    if path == "/api/watches" and method == "POST":
        ttl = str(b.get("title") or b.get("target_key") or "").strip()
        return f"Thêm Theo dõi: {ttl[:90]}" if ttl else f"{default_label} ({path})"
    if path.endswith("/check") and path.startswith("/api/watches/"):
        return f"Kiểm tra Theo dõi ngay ({path.split('/')[3]})"
    if path == "/api/sourcing/search":
        q = str(b.get("query") or "").strip()
        pl = str(b.get("platform") or "").strip()
        return f"Tìm Nguồn hàng TQ ({pl}): {q[:80]}" if q else f"{default_label} ({path})"
    if path == "/api/desk300/run":
        return f"Chạy Luồng Xử lý SP 300+desk -> Jev ({b.get('mode') or 'vault_process'})"
    if path == "/api/hunt/schedules" and method == "POST":
        nm = str(b.get("name") or b.get("keywords") or "").strip()
        return f"Tạo Lịch Săn SP & Painpoint Lặp lại: {nm[:80]}" if nm else "Tạo Lịch Săn SP & Painpoint Lặp lại"
    if path.startswith("/api/hunt/schedules/") and path.endswith("/run"):
        return f"Chạy Phiên Lịch Săn Lặp lại ({path.split('/')[4]})"
    return f"{default_label} ({path})"


class HistoryLogService:
    def __init__(self, connect):
        self.connect = connect
        self.telegram_sink = None
        self.jobs_service = None
        self.products_service = None

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
        lid = log_id or f"act_{ts.replace(':', '').replace('-', '')}_{module}_{uuid.uuid4().hex[:6]}"
        clean_payload = scrub_for_history(payload or {})
        clean_summary = scrub_for_history(summary or title)
        clean_title = scrub_for_history(title)

        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute("SELECT seq_no FROM activity_history_logs WHERE log_id = ?", (lid,)).fetchone() if log_id else None
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
            payload={"kind": kind, "title": title, "job_id": job_id, **meta},
            log_id=f"job_{job_id}",
            notify_telegram=True,
        )
        return ev.get("gs_code", "")

    def sync_job_finished(self, job_id: str, status: str, duration_ms: int, actual_usd: float, summary: str, payload: dict):
        with self.connect() as conn:
            row = conn.execute("SELECT module, title FROM activity_history_logs WHERE log_id=?", (f"job_{job_id}",)).fetchone()
        mod = (row["module"] if row else None) or payload.get("kind") or "hunt"
        ttl = (row["title"] if row else None) or payload.get("title") or summary or f"Tiến trình {job_id}"
        self.record_event(
            module=mod,
            action_type="job_run",
            title=ttl,
            status=status,
            duration_ms=duration_ms,
            cost_usd=actual_usd,
            summary=summary,
            payload={"job_id": job_id, **payload},
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
            "/api/providers/telegram/sync-pending",
            "/api/hunt/estimate",
            "/api/keywords/suggest",
            "/api/sourcing/calc",
            "/api/products/economics-calc",
            "/api/chat/send",
        ) or path.endswith("/resend-telegram"):
            return
        cls = classify_http_module(path)
        if cls is None:
            return
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
            title=describe_http_title(method, path, req_body, label),
            status=status,
            duration_ms=duration_ms,
            summary=summary,
            payload={"request": req_body, "response": res_body, "http_status": http_status},
            notify_telegram=True,
        )

    def list_logs(
        self,
        module: str = "",
        status: str = "",
        q: str = "",
        date_from: str = "",
        date_to: str = "",
        limit: int = 100,
    ) -> list[dict]:
        clauses = []
        params: list = []
        if module and module != "all":
            clauses.append("module = ?")
            params.append(module)
        if status and status != "all":
            clauses.append("status = ?")
            params.append(status)
        if date_from:
            clauses.append("substr(created_at, 1, 10) >= ?")
            params.append(date_from[:10])
        if date_to:
            clauses.append("substr(created_at, 1, 10) <= ?")
            params.append(date_to[:10])
        if q:
            clauses.append("(title LIKE ? OR summary LIKE ? OR payload_json LIKE ? OR CAST(seq_no AS TEXT) = ?)")
            q_clean = q.upper().replace("GS-", "").replace("#", "").lstrip("0") or q
            params.extend([f"%{q}%", f"%{q}%", f"%{q}%", q_clean])
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(min(250, max(1, int(limit))))
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM activity_history_logs {where} ORDER BY seq_no DESC LIMIT ?",
                tuple(params),
            ).fetchall()
        return [self._format_row(r, include_detail=False) for r in rows]

    def summary_kpis(self) -> dict:
        with self.connect() as conn:
            r = conn.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed,
                       SUM(CASE WHEN status='running' THEN 1 ELSE 0 END) AS running,
                       SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed,
                       SUM(CASE WHEN telegram_notified_at != '' THEN 1 ELSE 0 END) AS telegram_notified,
                       SUM(CASE WHEN telegram_notified_at = '' THEN 1 ELSE 0 END) AS telegram_pending,
                       COALESCE(SUM(cost_usd), 0.0) AS total_cost_usd
                FROM activity_history_logs
                """
            ).fetchone()
        return {
            "total": int(r["total"] or 0),
            "completed": int(r["completed"] or 0),
            "running": int(r["running"] or 0),
            "failed": int(r["failed"] or 0),
            "telegram_notified": int(r["telegram_notified"] or 0),
            "telegram_pending": int(r["telegram_pending"] or 0),
            "total_cost_usd": round(float(r["total_cost_usd"] or 0.0), 5),
        }

    def get_log(self, id_or_gs: str) -> dict | None:
        raw = (id_or_gs or "").strip()
        if not raw:
            return None
        with self.connect() as conn:
            if raw.upper().startswith("GS-") and raw[3:].isdigit():
                row = conn.execute("SELECT * FROM activity_history_logs WHERE seq_no = ?", (int(raw[3:]),)).fetchone()
            elif raw.lstrip("#").isdigit():
                row = conn.execute("SELECT * FROM activity_history_logs WHERE seq_no = ?", (int(raw.lstrip("#")),)).fetchone()
            else:
                row = conn.execute("SELECT * FROM activity_history_logs WHERE log_id = ?", (raw,)).fetchone()
        return self._format_row(row, include_detail=True) if row else None

    def _hydrate_job_and_results(self, row, payload: dict) -> dict:
        lid = str(row["log_id"] or "")
        step_logs: list[str] = []
        error_text = ""
        job_detail = None

        job_id = payload.get("job_id") or (lid[4:] if lid.startswith("job_") else "")
        if job_id and self.jobs_service is not None:
            job_detail = self.jobs_service.get_job(str(job_id))
            if job_detail:
                step_logs = list(job_detail.get("logs") or [])
                error_text = str(job_detail.get("error") or "")

        resp = payload.get("response") if isinstance(payload.get("response"), dict) else {}
        job_res = payload.get("result") if isinstance(payload.get("result"), dict) else ((job_detail or {}).get("meta", {}).get("result") or {})
        if not error_text and str(row["status"]) == "failed":
            error_text = str(resp.get("detail") or row["summary"] or "")

        # Collect touched/discovered product IDs to hydrate live product cards/rows
        pids: list[int] = []
        for cand_list in (
            job_res.get("product_ids"),
            resp.get("product_ids"),
            resp.get("saved_product_ids"),
            (payload.get("request") or {}).get("ids") if isinstance(payload.get("request"), dict) else None,
        ):
            if isinstance(cand_list, list):
                for x in cand_list:
                    if str(x).isdigit() and int(x) not in pids:
                        pids.append(int(x))
        if isinstance(resp.get("product"), dict) and resp["product"].get("id"):
            pid_one = int(resp["product"]["id"])
            if pid_one not in pids:
                pids.append(pid_one)
        if isinstance(resp.get("products"), list):
            for p in resp["products"]:
                if isinstance(p, dict) and p.get("id") and int(p["id"]) not in pids:
                    pids.append(int(p["id"]))

        hydrated_products = self.products_service.get_products_by_ids(pids) if (pids and self.products_service) else []
        # Fallback to inline items if not in pids
        if not hydrated_products and isinstance(resp.get("items"), list) and resp.get("keyword"):
            hydrated_products = [x for x in resp["items"] if isinstance(x, dict) and x.get("title")]
        if not hydrated_products and isinstance(resp.get("items"), list) and resp.get("shop_name"):
            hydrated_products = [x for x in resp["items"] if isinstance(x, dict) and x.get("title")]

        china_items = resp.get("items") if (row["module"] == "china_sourcing" and isinstance(resp.get("items"), list)) else []
        creators = resp.get("creators") if isinstance(resp.get("creators"), list) else []
        watch_diff = resp.get("diff") if isinstance(resp.get("diff"), dict) else None

        kpis = []
        if job_detail:
            kpis.append({"label": "Trạng thái Job", "value": job_detail["status"]})
            kpis.append({"label": "Ngân sách / Thực chi", "value": f"${job_detail['actual_cost_usd']:.4f} / ${job_detail['budget_limit_usd']:.2f}"})
        if hydrated_products:
            kpis.append({"label": "Sản phẩm thu được", "value": f"{len(hydrated_products)} SP"})
        if job_res.get("painpoints_count"):
            kpis.append({"label": "Painpoint MXH phát hiện", "value": f"{job_res['painpoints_count']} nhóm"})
        if isinstance(resp.get("painpoint"), dict):
            kpis.append({"label": "Từ khoá giải pháp", "value": ", ".join((resp["painpoint"].get("recommended_keywords") or [])[:3])})
        if job_res.get("scored_jev_count") is not None:
            kpis.append({"label": "Đã chấm Jev AI", "value": f"{job_res['scored_jev_count']} SP"})
        if payload.get("channels"):
            kpis.append({"label": "Kênh quét", "value": ", ".join(payload["channels"])})
        if watch_diff:
            kpis.append({"label": "Tổng SP / SP Mới", "value": f"{watch_diff.get('total_count', 0)} SP (+{watch_diff.get('new_items_count', 0)} mới)"})

        jump_target = None
        if hydrated_products:
            jump_target = {"tab": "results", "label": f"📦 Mở Kho & Phân loại ({len(hydrated_products)} SP)"}
        elif china_items:
            jump_target = {"tab": "sourcing", "label": "🇨🇳 Mở Kho Nguồn hàng TQ"}
        elif watch_diff:
            jump_target = {"tab": "watches", "label": "🔭 Mở Theo dõi & Diff"}

        request_summary = payload.get("request") if "request" in payload else {k: v for k, v in payload.items() if k not in ("result", "response")}
        result_summary = job_res or resp or {"summary": row["summary"]}

        gs_code = format_gs_code(row["seq_no"])
        bug_report = (
            f"[{gs_code}] {row['title']}\n"
            f"Module: {row['module']} | Status: {row['status']} | Duration: {row['duration_ms']}ms | Cost: ${row['cost_usd']}\n"
            f"Summary: {row['summary']}\n"
            + (f"Error: {error_text}\n" if error_text else "")
            + (f"Logs:\n" + "\n".join(step_logs[-15:]) if step_logs else "")
        )

        return {
            "step_logs": step_logs,
            "error_text": error_text,
            "job": job_detail,
            "request_summary": request_summary,
            "result_summary": result_summary,
            "bug_report_text": bug_report,
            "resolved_results": {
                "headline": row["summary"],
                "kpis": kpis,
                "products": hydrated_products,
                "china_items": china_items,
                "creators": creators,
                "watch_diff": watch_diff,
                "jump_target": jump_target,
            },
        }

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

    def _format_row(self, r, include_detail: bool = False) -> dict:
        mod = r["module"]
        d = {
            "log_id": r["log_id"],
            "seq_no": r["seq_no"],
            "gs_code": format_gs_code(r["seq_no"]),
            "module": mod,
            "module_label": MODULE_LABELS.get(mod, mod),
            "action_type": r["action_type"],
            "title": r["title"],
            "status": r["status"],
            "duration_ms": r["duration_ms"],
            "cost_usd": r["cost_usd"],
            "summary": r["summary"],
            "note": r["note"],
            "telegram_message_id": r["telegram_message_id"],
            "telegram_notified_at": r["telegram_notified_at"],
            "telegram_last_error": r["telegram_last_error"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        if include_detail:
            payload = json.loads(r["payload_json"] or "{}")
            d["payload"] = payload
            d.update(self._hydrate_job_and_results(r, payload))
        return d

    def dispatch(self, path: str, method: str, env, read_json):
        if path == "/api/history-logs" and method == "GET":
            qs = parse_qs(env.get("QUERY_STRING") or "")
            mod = (qs.get("module") or [""])[0]
            st = (qs.get("status") or [""])[0]
            q = (qs.get("q") or [""])[0]
            dfrom = (qs.get("date_from") or [""])[0]
            dto = (qs.get("date_to") or [""])[0]
            return "200 OK", {
                "logs": self.list_logs(module=mod, status=st, q=q, date_from=dfrom, date_to=dto),
                "kpis": self.summary_kpis(),
                "modules": MODULE_LABELS,
            }
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
            if len(parts) == 4 and parts[3] == "resend-telegram" and method == "POST":
                item = self.get_log(parts[2])
                if not item:
                    raise ApiError("404 Not Found", "Không tìm thấy nhật ký này")
                if not self.telegram_sink:
                    raise ApiError("503 Service Unavailable", "Chưa kết nối Telegram Bot")
                sent_res = self.telegram_sink.deliver_log_immediately(item, force=True)
                return "200 OK", {"ok": True, "log": self.get_log(parts[2]), **sent_res}
        return None
