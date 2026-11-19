"""Safe incremental SQLite WAL migrations with pre-migration atomic hot backups."""
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3


MIGRATIONS: list[tuple[int, str, list[str]]] = [
    (
        1,
        "v1_core_global_shop_dianshang_schema",
        [
            """
            CREATE TABLE IF NOT EXISTS settings (
                name TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS cost_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                idempotency_key TEXT NOT NULL UNIQUE,
                job_id TEXT NOT NULL DEFAULT '',
                provider TEXT NOT NULL DEFAULT '',
                operation TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'reserved',
                estimated_usd REAL NOT NULL DEFAULT 0.0,
                actual_usd REAL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                budget_limit_usd REAL NOT NULL DEFAULT 0.30,
                estimated_cost_usd REAL NOT NULL DEFAULT 0.0,
                actual_cost_usd REAL NOT NULL DEFAULT 0.0,
                retries_used INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 2,
                logs TEXT NOT NULL DEFAULT '[]',
                meta TEXT NOT NULL DEFAULT '{}',
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS history_log_sequence (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_seq INTEGER NOT NULL DEFAULT 0
            )
            """,
            "INSERT OR IGNORE INTO history_log_sequence (id, last_seq) VALUES (1, 0)",
            """
            CREATE TABLE IF NOT EXISTS activity_history_logs (
                log_id TEXT PRIMARY KEY,
                seq_no INTEGER UNIQUE,
                module TEXT NOT NULL,
                action_type TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                duration_ms INTEGER NOT NULL DEFAULT 0,
                cost_usd REAL NOT NULL DEFAULT 0.0,
                summary TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL DEFAULT '{}',
                note TEXT NOT NULL DEFAULT '',
                telegram_message_id TEXT NOT NULL DEFAULT '',
                telegram_notified_at TEXT NOT NULL DEFAULT '',
                telegram_sync_hash TEXT NOT NULL DEFAULT '',
                telegram_last_error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_hist_seq ON activity_history_logs(seq_no DESC)",
            "CREATE INDEX IF NOT EXISTS idx_hist_module ON activity_history_logs(module, created_at DESC)",
            """
            CREATE TABLE IF NOT EXISTS notifs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                data TEXT NOT NULL DEFAULT '{}',
                at TEXT NOT NULL,
                read INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL DEFAULT 'shopee',
                market TEXT NOT NULL DEFAULT 'VN',
                native_product_id TEXT NOT NULL DEFAULT '',
                native_shop_id TEXT NOT NULL DEFAULT '',
                canonical_url TEXT NOT NULL DEFAULT '',
                bucket TEXT NOT NULL DEFAULT 'cho_danh_gia',
                status TEXT NOT NULL DEFAULT '',
                industry TEXT NOT NULL DEFAULT 'khac',
                jev_score REAL,
                sold_count INTEGER NOT NULL DEFAULT 0,
                gmv_vnd REAL NOT NULL DEFAULT 0.0,
                price_vnd REAL NOT NULL DEFAULT 0.0,
                cost_vnd REAL NOT NULL DEFAULT 0.0,
                record TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_prod_identity ON products(platform, market, native_product_id)",
            "CREATE INDEX IF NOT EXISTS idx_prod_bucket ON products(bucket, updated_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_prod_industry ON products(industry, updated_at DESC)",
            """
            CREATE TABLE IF NOT EXISTS product_metric_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                source TEXT NOT NULL DEFAULT '',
                price_vnd REAL NOT NULL DEFAULT 0.0,
                sold_count INTEGER NOT NULL DEFAULT 0,
                sold_7d INTEGER,
                sold_30d INTEGER,
                gmv_vnd REAL NOT NULL DEFAULT 0.0,
                gmv_7d_vnd REAL,
                gmv_30d_vnd REAL,
                rating REAL,
                stock INTEGER,
                recorded_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_pmh_prod ON product_metric_history(product_id, recorded_at DESC)",
            """
            CREATE TABLE IF NOT EXISTS shops (
                shop_id TEXT PRIMARY KEY,
                role TEXT NOT NULL DEFAULT 'own_shop' CHECK (role IN ('own_shop', 'competitor_shop')),
                platform TEXT NOT NULL DEFAULT 'shopee',
                market TEXT NOT NULL DEFAULT 'VN',
                native_shop_id TEXT NOT NULL DEFAULT '',
                handle TEXT NOT NULL DEFAULT '',
                shop_name TEXT NOT NULL,
                shop_url TEXT NOT NULL DEFAULT '',
                industry TEXT NOT NULL DEFAULT 'gia_dung',
                niche_tags_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'active',
                platform_fee_pct REAL NOT NULL DEFAULT 12.0,
                stats_json TEXT NOT NULL DEFAULT '{}',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS shop_product_scans (
                scan_id TEXT PRIMARY KEY,
                shop_id TEXT NOT NULL DEFAULT '',
                platform TEXT NOT NULL,
                shop_query TEXT NOT NULL,
                shop_name TEXT NOT NULL DEFAULT '',
                total_products INTEGER NOT NULL DEFAULT 0,
                total_sold INTEGER NOT NULL DEFAULT 0,
                estimated_gmv_vnd REAL NOT NULL DEFAULT 0.0,
                avg_price_vnd REAL NOT NULL DEFAULT 0.0,
                summary_json TEXT NOT NULL DEFAULT '{}',
                items_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS keyword_researches (
                research_id TEXT PRIMARY KEY,
                platform TEXT NOT NULL,
                market TEXT NOT NULL DEFAULT 'VN',
                keyword TEXT NOT NULL,
                total_products INTEGER NOT NULL DEFAULT 0,
                sampled_count INTEGER NOT NULL DEFAULT 0,
                total_sold_sample INTEGER NOT NULL DEFAULT 0,
                avg_price_vnd REAL NOT NULL DEFAULT 0.0,
                min_price_vnd REAL NOT NULL DEFAULT 0.0,
                max_price_vnd REAL NOT NULL DEFAULT 0.0,
                mall_share_pct REAL NOT NULL DEFAULT 0.0,
                jev_opportunity_score REAL,
                suggestions_json TEXT NOT NULL DEFAULT '[]',
                items_json TEXT NOT NULL DEFAULT '[]',
                summary_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_kw_res ON keyword_researches(platform, keyword, created_at DESC)",
            """
            CREATE TABLE IF NOT EXISTS watches (
                watch_id TEXT PRIMARY KEY,
                watch_type TEXT NOT NULL CHECK (watch_type IN ('keyword', 'product', 'shop')),
                platform TEXT NOT NULL,
                market TEXT NOT NULL DEFAULT 'VN',
                target_key TEXT NOT NULL,
                title TEXT NOT NULL,
                target_url TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'archived')),
                interval_hours REAL NOT NULL DEFAULT 12.0,
                linked_product_id INTEGER,
                linked_shop_id TEXT NOT NULL DEFAULT '',
                last_checked_at TEXT NOT NULL DEFAULT '',
                next_check_at TEXT NOT NULL DEFAULT '',
                last_summary_json TEXT NOT NULL DEFAULT '{}',
                baseline_snapshot_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_watches_due ON watches(status, next_check_at)",
            """
            CREATE TABLE IF NOT EXISTS watch_runs (
                run_id TEXT PRIMARY KEY,
                watch_id TEXT NOT NULL REFERENCES watches(watch_id) ON DELETE CASCADE,
                watch_type TEXT NOT NULL,
                platform TEXT NOT NULL,
                trigger_kind TEXT NOT NULL DEFAULT 'manual',
                status TEXT NOT NULL DEFAULT 'completed',
                total_count INTEGER NOT NULL DEFAULT 0,
                prev_total_count INTEGER,
                new_items_count INTEGER NOT NULL DEFAULT 0,
                rising_items_count INTEGER NOT NULL DEFAULT 0,
                dropped_items_count INTEGER NOT NULL DEFAULT 0,
                diff_json TEXT NOT NULL DEFAULT '{}',
                snapshot_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_watch_runs_watch ON watch_runs(watch_id, created_at DESC)",
            """
            CREATE TABLE IF NOT EXISTS china_sourcing_items (
                sourcing_id TEXT PRIMARY KEY,
                platform TEXT NOT NULL CHECK (platform IN ('1688', 'taobao', 'pinduoduo', 'douyin', 'alibaba')),
                native_item_id TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL,
                title_vi TEXT NOT NULL DEFAULT '',
                item_url TEXT NOT NULL DEFAULT '',
                image_url TEXT NOT NULL DEFAULT '',
                price_cny REAL NOT NULL DEFAULT 0.0,
                wholesale_tiers_json TEXT NOT NULL DEFAULT '[]',
                moq INTEGER NOT NULL DEFAULT 1,
                weight_kg REAL NOT NULL DEFAULT 0.4,
                cny_rate REAL NOT NULL DEFAULT 3650.0,
                landed_cost_vnd REAL NOT NULL DEFAULT 0.0,
                supplier_name TEXT NOT NULL DEFAULT '',
                supplier_Badges_json TEXT NOT NULL DEFAULT '[]',
                sales_volume TEXT NOT NULL DEFAULT '',
                linked_product_id INTEGER,
                jev_supplier_score REAL,
                raw_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_cn_sourcing_prod ON china_sourcing_items(linked_product_id, updated_at DESC)",
            """
            CREATE TABLE IF NOT EXISTS campaigns (
                campaign_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                industry TEXT NOT NULL DEFAULT 'gia_dung',
                status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('planning', 'active', 'paused', 'completed')),
                target_revenue_vnd REAL NOT NULL DEFAULT 0.0,
                budget_vnd REAL NOT NULL DEFAULT 0.0,
                daily_brief_enabled INTEGER NOT NULL DEFAULT 1,
                daily_brief_time TEXT NOT NULL DEFAULT '08:00',
                shop_ids_json TEXT NOT NULL DEFAULT '[]',
                keywords_json TEXT NOT NULL DEFAULT '[]',
                products_stage_json TEXT NOT NULL DEFAULT '{}',
                videos_json TEXT NOT NULL DEFAULT '[]',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS campaign_tasks (
                task_id TEXT PRIMARY KEY,
                campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                is_recurring INTEGER NOT NULL DEFAULT 1,
                done_dates_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS campaign_daily_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id TEXT NOT NULL,
                local_date TEXT NOT NULL,
                trigger_kind TEXT NOT NULL DEFAULT 'scheduled_0800',
                summary_text TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(campaign_id, local_date, trigger_kind)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS seller_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                order_id TEXT NOT NULL,
                line_id TEXT NOT NULL DEFAULT '0',
                shop_id TEXT NOT NULL DEFAULT '',
                campaign_id TEXT NOT NULL DEFAULT '',
                product_id INTEGER,
                product_title TEXT NOT NULL DEFAULT '',
                quantity INTEGER NOT NULL DEFAULT 1,
                gross_revenue_vnd REAL NOT NULL DEFAULT 0.0,
                platform_fee_vnd REAL NOT NULL DEFAULT 0.0,
                shipping_subsidy_vnd REAL NOT NULL DEFAULT 0.0,
                cogs_vnd REAL NOT NULL DEFAULT 0.0,
                net_payout_vnd REAL NOT NULL DEFAULT 0.0,
                net_profit_vnd REAL NOT NULL DEFAULT 0.0,
                order_status TEXT NOT NULL DEFAULT 'completed',
                ordered_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(platform, order_id, line_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS seller_expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                expense_type TEXT NOT NULL DEFAULT 'ads',
                platform TEXT NOT NULL DEFAULT 'shopee',
                shop_id TEXT NOT NULL DEFAULT '',
                campaign_id TEXT NOT NULL DEFAULT '',
                product_id INTEGER,
                amount_vnd REAL NOT NULL DEFAULT 0.0,
                spent_date TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS video_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_key TEXT NOT NULL UNIQUE,
                platform TEXT NOT NULL DEFAULT 'tiktok',
                video_url TEXT NOT NULL DEFAULT '',
                author_handle TEXT NOT NULL DEFAULT '',
                is_important INTEGER NOT NULL DEFAULT 0,
                jev_score REAL,
                linked_product_ids_json TEXT NOT NULL DEFAULT '[]',
                manual_prompts_json TEXT NOT NULL DEFAULT '[]',
                record TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS video_clones (
                clone_id TEXT PRIMARY KEY,
                source_url TEXT NOT NULL DEFAULT '',
                clone_mode TEXT NOT NULL DEFAULT 'product_swap',
                target_product_id INTEGER,
                target_shop_id TEXT NOT NULL DEFAULT '',
                duration_sec REAL NOT NULL DEFAULT 0.0,
                segments_json TEXT NOT NULL DEFAULT '[]',
                record TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS creator_leads (
                creator_id TEXT PRIMARY KEY,
                platform TEXT NOT NULL DEFAULT 'tiktok',
                market TEXT NOT NULL DEFAULT 'VN',
                handle TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                followers INTEGER NOT NULL DEFAULT 0,
                industry TEXT NOT NULL DEFAULT 'gia_dung',
                video_gmv_vnd REAL NOT NULL DEFAULT 0.0,
                avg_views INTEGER NOT NULL DEFAULT 0,
                jev_score REAL,
                top_videos_json TEXT NOT NULL DEFAULT '[]',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS pins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT 'competitor',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS browser_connections (
                portal_key TEXT PRIMARY KEY,
                session_state TEXT NOT NULL DEFAULT 'disconnected',
                context_state TEXT NOT NULL DEFAULT 'unverified',
                market TEXT NOT NULL DEFAULT 'VN',
                account_hint TEXT NOT NULL DEFAULT '',
                last_url TEXT NOT NULL DEFAULT '',
                meta_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mcp_call_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL DEFAULT '',
                remote_addr TEXT NOT NULL DEFAULT '',
                rpc_method TEXT NOT NULL DEFAULT '',
                tool_name TEXT NOT NULL DEFAULT '',
                scope TEXT NOT NULL DEFAULT '',
                is_write INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'ok',
                duration_ms INTEGER NOT NULL DEFAULT 0,
                error_text TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """,
        ],
    ),
    (
        2,
        "v2_my_shops_campaigns_and_channels",
        [
            "ALTER TABLE shops ADD COLUMN campaign_ids_json TEXT NOT NULL DEFAULT '[]'",
        ],
    ),
    (
        3,
        "v3_painpoints_and_google_trends_runs",
        [
            """
            CREATE TABLE IF NOT EXISTS google_trends_runs (
                run_id TEXT PRIMARY KEY,
                seed_terms_json TEXT NOT NULL DEFAULT '[]',
                geo TEXT NOT NULL DEFAULT 'VN',
                time_range TEXT NOT NULL DEFAULT 'today 3-m',
                category TEXT NOT NULL DEFAULT '',
                provider_used TEXT NOT NULL DEFAULT '',
                seed_summaries_json TEXT NOT NULL DEFAULT '[]',
                keywords_json TEXT NOT NULL DEFAULT '[]',
                cost_usd REAL NOT NULL DEFAULT 0.0,
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_gt_runs_created ON google_trends_runs(created_at DESC)",
            """
            CREATE TABLE IF NOT EXISTS painpoint_discoveries (
                painpoint_id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL DEFAULT '',
                topic_query TEXT NOT NULL,
                channels_json TEXT NOT NULL DEFAULT '[]',
                industry TEXT NOT NULL DEFAULT 'khac',
                pain_title TEXT NOT NULL,
                pain_summary TEXT NOT NULL DEFAULT '',
                solution_archetype TEXT NOT NULL DEFAULT '',
                recommended_keywords_json TEXT NOT NULL DEFAULT '[]',
                evidence_posts_json TEXT NOT NULL DEFAULT '[]',
                jev_pain_score REAL,
                jev_detail_json TEXT NOT NULL DEFAULT '{}',
                matched_product_ids_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_painpoint_updated ON painpoint_discoveries(updated_at DESC)",
        ],
    ),
    (
        4,
        "v4_desk300_product_pipeline_runs",
        [
            """
            CREATE TABLE IF NOT EXISTS desk300_sequence (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_nnn INTEGER NOT NULL DEFAULT 0
            )
            """,
            "INSERT OR IGNORE INTO desk300_sequence (id, last_nnn) VALUES (1, 0)",
            """
            CREATE TABLE IF NOT EXISTS desk300_runs (
                run_id TEXT PRIMARY KEY,
                nnn_no INTEGER NOT NULL,
                nnn_code TEXT NOT NULL,
                title TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'vault_process',
                exec_engine TEXT NOT NULL DEFAULT 'gateway_fast',
                status TEXT NOT NULL DEFAULT 'running',
                input_product_ids_json TEXT NOT NULL DEFAULT '[]',
                output_product_ids_json TEXT NOT NULL DEFAULT '[]',
                strong_pick_count INTEGER NOT NULL DEFAULT 0,
                maybe_count INTEGER NOT NULL DEFAULT 0,
                pass_count INTEGER NOT NULL DEFAULT 0,
                export_dir TEXT NOT NULL DEFAULT '',
                egress_verified INTEGER NOT NULL DEFAULT 0,
                steps_json TEXT NOT NULL DEFAULT '[]',
                results_json TEXT NOT NULL DEFAULT '[]',
                error_text TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_desk300_runs_nnn ON desk300_runs(nnn_no DESC)",
        ],
    ),
]


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def current_schema_version(db_path: str | Path) -> int:
    p = Path(db_path)
    if not p.is_file():
        return 0
    conn = sqlite3.connect(p, timeout=8)
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        if not row:
            return 0
        ver = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()[0]
        return int(ver or 0)
    finally:
        conn.close()


def create_hot_backup(db_path: Path, backup_dir: Path, label: str) -> Path | None:
    if not db_path.is_file() or db_path.stat().st_size == 0:
        return None
    backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = backup_dir / f"backend.{label}.{_utc_stamp()}.sqlite3"
    src = sqlite3.connect(db_path, timeout=15)
    dst = sqlite3.connect(target, timeout=15)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    if os.name == "posix":
        target.chmod(0o600)
    return target


def run_migrations(data_dir: str | Path) -> dict:
    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    db_path = root / "backend.sqlite3"
    backup_dir = root / "backups"

    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL,
                backup_file TEXT NOT NULL DEFAULT ''
            )
            """
        )
        applied_rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
        applied = {int(r[0]) for r in applied_rows}
    finally:
        conn.close()

    newly_applied = []
    for ver, name, statements in MIGRATIONS:
        if ver in applied:
            continue
        bfile = create_hot_backup(db_path, backup_dir, f"pre_v{ver}")
        c2 = sqlite3.connect(db_path, timeout=30)
        c2.execute("PRAGMA foreign_keys=ON")
        try:
            c2.execute("BEGIN IMMEDIATE")
            for stmt in statements:
                c2.execute(stmt)
            c2.execute(
                "INSERT INTO schema_migrations (version, name, applied_at, backup_file) VALUES (?, ?, ?, ?)",
                (
                    ver,
                    name,
                    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    str(bfile.name) if bfile else "",
                ),
            )
            c2.commit()
            newly_applied.append(ver)
        except Exception:
            c2.rollback()
            raise
        finally:
            c2.close()

    if os.name == "posix" and db_path.exists():
        db_path.chmod(0o600)
    return {
        "schema_version": current_schema_version(db_path),
        "applied_now": newly_applied,
    }
