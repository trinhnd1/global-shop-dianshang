"""Atomic pre-flight cost reservation & settlement ledger."""
import sqlite3
from .responses import now


class CostLedger:
    def __init__(self, connect):
        self.connect = connect

    def reserve(self, idempotency_key: str, estimated_usd: float, job_id: str = "", provider: str = "", operation: str = "") -> bool:
        ts = now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute("SELECT status FROM cost_ledger WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
            if existing:
                return False
            conn.execute(
                """
                INSERT INTO cost_ledger (idempotency_key, job_id, provider, operation, status, estimated_usd, actual_usd, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'reserved', ?, NULL, ?, ?)
                """,
                (idempotency_key, job_id, provider, operation, max(0.0, float(estimated_usd or 0.0)), ts, ts),
            )
        return True

    def settle(self, idempotency_key: str, actual_usd: float | None = None) -> None:
        ts = now()
        status = "settled_actual" if actual_usd is not None else "settled_estimated_only"
        with self.connect() as conn:
            conn.execute(
                "UPDATE cost_ledger SET status = ?, actual_usd = ?, updated_at = ? WHERE idempotency_key = ?",
                (status, float(actual_usd) if actual_usd is not None else None, ts, idempotency_key),
            )

    def release(self, idempotency_key: str) -> None:
        ts = now()
        with self.connect() as conn:
            conn.execute(
                "UPDATE cost_ledger SET status = 'released', updated_at = ? WHERE idempotency_key = ? AND status = 'reserved'",
                (ts, idempotency_key),
            )

    def summary(self) -> dict:
        with self.connect() as conn:
            rows = conn.execute("SELECT status, provider, estimated_usd, actual_usd FROM cost_ledger").fetchall()
        reserved = 0.0
        settled = 0.0
        by_provider: dict[str, float] = {}
        for r in rows:
            st = r["status"]
            est = float(r["estimated_usd"] or 0.0)
            act = r["actual_usd"]
            prov = r["provider"] or "other"
            if st == "reserved":
                reserved += est
            elif st.startswith("settled"):
                val = float(act) if act is not None else est
                settled += val
                by_provider[prov] = round(by_provider.get(prov, 0.0) + val, 6)
        return {
            "reserved_usd": round(reserved, 6),
            "settled_usd": round(settled, 6),
            "committed_total_usd": round(reserved + settled, 6),
            "by_provider_usd": by_provider,
            "entries_count": len(rows),
        }

    def dispatch(self, path: str, method: str, env, read_json):
        if path == "/api/ledger/summary" and method == "GET":
            return "200 OK", self.summary()
        return None
