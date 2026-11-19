"""Durable JobManager with budget caps, bounded retries, cancellation, and GS-XXXX log sync."""
import json
import threading
import time
import uuid

from .ledger import CostLedger
from .responses import ApiError, now


class JobCancelledError(Exception):
    pass


class BudgetExceededError(Exception):
    pass


class JobContext:
    def __init__(self, manager: "JobManager", job_id: str, budget_limit_usd: float, max_retries: int):
        self.manager = manager
        self.job_id = job_id
        self.budget_limit_usd = float(budget_limit_usd)
        self.max_retries = int(max_retries)
        self._cancel_event = threading.Event()
        self.committed_usd = 0.0
        self.actual_usd = 0.0
        self._lock = threading.Lock()

    def cancel(self):
        self._cancel_event.set()

    def check_cancelled(self):
        if self._cancel_event.is_set():
            raise JobCancelledError("Tác vụ đã được người dùng yêu cầu dừng")

    def log(self, message: str):
        self.manager.append_log(self.job_id, message)

    def run_step(self, step_key: str, provider: str, est_usd: float, fn):
        self.check_cancelled()
        with self._lock:
            if self.committed_usd + est_usd > self.budget_limit_usd + 1e-9:
                raise BudgetExceededError(
                    f"Vượt trần ngân sách job (${self.committed_usd + est_usd:.4f} > ${self.budget_limit_usd:.4f})"
                )
            self.committed_usd += est_usd

        idem = f"job:{self.job_id}:{step_key}:{uuid.uuid4().hex[:6]}"
        if self.manager.ledger:
            self.manager.ledger.reserve(idem, est_usd, job_id=self.job_id, provider=provider, operation=step_key)

        attempt = 0
        while True:
            self.check_cancelled()
            attempt += 1
            try:
                res = fn()
                spent = None
                if isinstance(res, dict) and "_cost_usd" in res and res["_cost_usd"] is not None:
                    spent = float(res["_cost_usd"])
                if self.manager.ledger:
                    self.manager.ledger.settle(idem, actual_usd=spent)
                with self._lock:
                    effective = spent if spent is not None else est_usd
                    self.actual_usd += effective
                    self.committed_usd = max(0.0, self.committed_usd - est_usd + effective)
                self.manager.update_costs(self.job_id, self.actual_usd)
                return res
            except Exception as exc:
                status_code = getattr(exc, "status", 0)
                transient = status_code in (429, 500, 502, 503, 504) or "timed out" in str(exc).lower()
                if transient and attempt <= self.max_retries:
                    self.manager.increment_retry(self.job_id)
                    self.log(f"[Thử lại {attempt}/{self.max_retries}] {step_key}: {exc}")
                    time.sleep(0.5 * (2 ** (attempt - 1)))
                    continue
                if self.manager.ledger:
                    self.manager.ledger.release(idem)
                with self._lock:
                    self.committed_usd = max(0.0, self.committed_usd - est_usd)
                raise


class JobManager:
    def __init__(self, connect, ledger: CostLedger | None = None):
        self.connect = connect
        self.ledger = ledger
        self.history_sink = None
        self._active: dict[str, JobContext] = {}
        self._lock = threading.Lock()
        self._recover_interrupted()

    def _recover_interrupted(self):
        ts = now()
        with self.connect() as conn:
            conn.execute(
                "UPDATE jobs SET status='interrupted', error='Server khởi động lại khi đang chạy', updated_at=? WHERE status='running'",
                (ts,),
            )

    def start_job(
        self,
        kind: str,
        title: str,
        target_fn,
        estimated_cost_usd: float = 0.0,
        budget_limit_usd: float = 0.30,
        max_retries: int = 2,
        single_active_kind: bool = False,
        meta: dict | None = None,
    ) -> dict:
        if estimated_cost_usd > budget_limit_usd + 1e-9:
            raise ApiError(
                "400 Bad Request",
                f"Chi phí ước tính (${estimated_cost_usd:.4f}) vượt trần ngân sách (${budget_limit_usd:.4f})",
            )
        with self._lock:
            if single_active_kind:
                for ctx in self._active.values():
                    row = self.get_job(ctx.job_id)
                    if row and row.get("kind") == kind and row.get("status") == "running":
                        raise ApiError("409 Conflict", f"Đang có tiến trình {kind} chạy, vui lòng đợi hoặc bấm dừng")
            jid = f"job_{uuid.uuid4().hex[:10]}"
            ctx = JobContext(self, jid, budget_limit_usd=budget_limit_usd, max_retries=max_retries)
            self._active[jid] = ctx

        ts = now()
        meta_obj = dict(meta or {})
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (id, kind, title, status, budget_limit_usd, estimated_cost_usd, actual_cost_usd,
                                  retries_used, max_retries, logs, meta, error, created_at, updated_at)
                VALUES (?, ?, ?, 'running', ?, ?, 0.0, 0, ?, '[]', ?, '', ?, ?)
                """,
                (
                    jid,
                    kind,
                    title,
                    float(budget_limit_usd),
                    float(estimated_cost_usd),
                    int(max_retries),
                    json.dumps(meta_obj, ensure_ascii=False),
                    ts,
                    ts,
                ),
            )

        gs_code = ""
        if self.history_sink is not None:
            gs_code = self.history_sink.sync_job_created(jid, kind, title, estimated_cost_usd, meta_obj)

        def _runner():
            t0 = time.monotonic()
            try:
                result = target_fn(ctx)
                dur_ms = int((time.monotonic() - t0) * 1000)
                if isinstance(result, dict):
                    meta_obj["result"] = result
                with self.connect() as conn:
                    conn.execute(
                        "UPDATE jobs SET status='completed', meta=?, updated_at=? WHERE id=?",
                        (json.dumps(meta_obj, ensure_ascii=False), now(), jid),
                    )
                if self.history_sink is not None:
                    self.history_sink.sync_job_finished(
                        jid, "completed", dur_ms, ctx.actual_usd, summary=self._summarize(meta_obj), payload=meta_obj
                    )
            except JobCancelledError as exc:
                dur_ms = int((time.monotonic() - t0) * 1000)
                with self.connect() as conn:
                    conn.execute("UPDATE jobs SET status='cancelled', error=?, updated_at=? WHERE id=?", (str(exc), now(), jid))
                if self.history_sink is not None:
                    self.history_sink.sync_job_finished(jid, "cancelled", dur_ms, ctx.actual_usd, summary=str(exc), payload=meta_obj)
            except Exception as exc:
                dur_ms = int((time.monotonic() - t0) * 1000)
                with self.connect() as conn:
                    conn.execute("UPDATE jobs SET status='failed', error=?, updated_at=? WHERE id=?", (str(exc)[:500], now(), jid))
                if self.history_sink is not None:
                    self.history_sink.sync_job_finished(jid, "failed", dur_ms, ctx.actual_usd, summary=str(exc)[:300], payload=meta_obj)
            finally:
                with self._lock:
                    self._active.pop(jid, None)

        th = threading.Thread(target=_runner, name=f"gs-job-{jid}", daemon=True)
        th.start()
        out = self.get_job(jid) or {"id": jid, "status": "running"}
        if gs_code:
            out["gs_code"] = gs_code
        return out

    @staticmethod
    def _summarize(meta_obj: dict) -> str:
        res = meta_obj.get("result")
        if isinstance(res, dict) and res.get("summary"):
            return str(res["summary"])[:300]
        return "Hoàn thành tiến trình"

    def append_log(self, job_id: str, line: str):
        ts = now()
        entry = f"[{ts[11:19]}] {line}"
        with self.connect() as conn:
            row = conn.execute("SELECT logs FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                return
            logs = json.loads(row["logs"] or "[]")
            logs.append(entry)
            if len(logs) > 500:
                logs = logs[-500:]
            conn.execute("UPDATE jobs SET logs=?, updated_at=? WHERE id=?", (json.dumps(logs, ensure_ascii=False), ts, job_id))

    def update_costs(self, job_id: str, actual_usd: float):
        with self.connect() as conn:
            conn.execute("UPDATE jobs SET actual_cost_usd=?, updated_at=? WHERE id=?", (round(float(actual_usd), 6), now(), job_id))

    def increment_retry(self, job_id: str):
        with self.connect() as conn:
            conn.execute("UPDATE jobs SET retries_used = retries_used + 1, updated_at=? WHERE id=?", (now(), job_id))

    def cancel_job(self, job_id: str) -> dict:
        with self._lock:
            ctx = self._active.get(job_id)
            if ctx:
                ctx.cancel()
        with self.connect() as conn:
            row = conn.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                raise ApiError("404 Not Found", "Không tìm thấy tiến trình")
            if row["status"] == "running" and not ctx:
                conn.execute("UPDATE jobs SET status='cancelled', updated_at=? WHERE id=?", (now(), job_id))
        return self.get_job(job_id) or {"id": job_id}

    def get_job(self, job_id: str) -> dict | None:
        with self.connect() as conn:
            r = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not r:
            return None
        return self._format_row(r, include_logs=True)

    def list_jobs(self, limit: int = 40) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (min(100, max(1, limit)),)).fetchall()
        return [self._format_row(r, include_logs=False) for r in rows]

    @staticmethod
    def _format_row(r, include_logs: bool = False) -> dict:
        logs = json.loads(r["logs"] or "[]")
        d = {
            "id": r["id"],
            "kind": r["kind"],
            "title": r["title"],
            "status": r["status"],
            "budget_limit_usd": r["budget_limit_usd"],
            "estimated_cost_usd": r["estimated_cost_usd"],
            "actual_cost_usd": r["actual_cost_usd"],
            "retries_used": r["retries_used"],
            "max_retries": r["max_retries"],
            "log_count": len(logs),
            "meta": json.loads(r["meta"] or "{}"),
            "error": r["error"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        if include_logs:
            d["logs"] = logs
        return d

    def dispatch(self, path: str, method: str, env, read_json):
        if path == "/api/jobs" and method == "GET":
            return "200 OK", {"jobs": self.list_jobs(), "ledger": self.ledger.summary() if self.ledger else {}}
        if path.startswith("/api/jobs/"):
            parts = path.strip("/").split("/")
            if len(parts) == 3 and method == "GET":
                job = self.get_job(parts[2])
                if not job:
                    raise ApiError("404 Not Found", "Không tìm thấy tiến trình")
                return "200 OK", job
            if len(parts) == 4 and parts[3] == "cancel" and method == "POST":
                return "200 OK", self.cancel_job(parts[2])
        return None
