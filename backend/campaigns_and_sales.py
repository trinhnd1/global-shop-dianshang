"""Category Launch Campaigns, Seller Order CSV Attribution & Profit Analytics, Morning Briefing Daemon, Chat & Pins."""
import csv
from datetime import datetime
import io
import json
import re
import threading
import time
import urllib.request
import uuid

from . import settings
from .products import INDUSTRIES
from .responses import ApiError, json_object, now, text

CAMPAIGN_PRODUCT_STAGES = {
    "chon_mau": "1. Chọn mẫu tiềm năng",
    "chot_xuong_tq": "2. Chốt nguồn 1688/PDD/Taobao",
    "nhap_test": "3. Nhập test lô nhỏ",
    "dang_ban_quay_video": "4. Đăng sàn & Làm Video/Ads",
    "win_scale_ton_kho": "5. Sản phẩm Win · Scale tồn kho",
}


class CampaignsAndSalesService:
    def __init__(self, connect, secrets, products, shops, telegram_bot=None):
        self.connect = connect
        self.secrets = secrets
        self.products = products
        self.shops = shops
        self.telegram_bot = telegram_bot

    # --- 1. Category & Product Launch Campaigns ------------------------------

    def create_or_update_campaign(self, body: dict, campaign_id: str | None = None) -> dict:
        cid = campaign_id or f"cmp_{uuid.uuid4().hex[:10]}"
        name = text(body.get("name"), "name", 180, required=True)
        ind = str(body.get("industry") or "gia_dung").strip()
        if ind not in INDUSTRIES:
            ind = "gia_dung"
        st = str(body.get("status") or "active").strip()
        if st not in ("planning", "active", "paused", "completed"):
            st = "active"
        target_rev = max(0.0, float(body.get("target_revenue_vnd") or 0.0))
        budget = max(0.0, float(body.get("budget_vnd") or 0.0))
        shop_ids = body.get("shop_ids") if isinstance(body.get("shop_ids"), list) else []
        keywords = body.get("keywords") if isinstance(body.get("keywords"), list) else []
        prod_stages = body.get("products_stage") if isinstance(body.get("products_stage"), dict) else {}
        videos = body.get("videos") if isinstance(body.get("videos"), list) else []
        note = str(body.get("note") or "")[:1000]
        ts = now()

        with self.connect() as conn:
            existing = conn.execute("SELECT * FROM campaigns WHERE campaign_id=?", (cid,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE campaigns
                    SET name=?, industry=?, status=?, target_revenue_vnd=?, budget_vnd=?,
                        shop_ids_json=?, keywords_json=?, products_stage_json=?, videos_json=?, note=?, updated_at=?
                    WHERE campaign_id=?
                    """,
                    (
                        name, ind, st, target_rev, budget,
                        json.dumps(shop_ids, ensure_ascii=False),
                        json.dumps(keywords, ensure_ascii=False),
                        json.dumps(prod_stages, ensure_ascii=False),
                        json.dumps(videos, ensure_ascii=False),
                        note, ts, cid,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO campaigns
                    (campaign_id, name, industry, status, target_revenue_vnd, budget_vnd, daily_brief_enabled, daily_brief_time,
                     shop_ids_json, keywords_json, products_stage_json, videos_json, note, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 1, '08:00', ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cid, name, ind, st, target_rev, budget,
                        json.dumps(shop_ids, ensure_ascii=False),
                        json.dumps(keywords, ensure_ascii=False),
                        json.dumps(prod_stages, ensure_ascii=False),
                        json.dumps(videos, ensure_ascii=False),
                        note, ts, ts,
                    ),
                )
                for default_task in (
                    "Kiểm tra biến động từ khoá & sản phẩm mới của đối thủ",
                    "Đối chiếu tồn kho & giá xưởng 1688/Pinduoduo",
                    "Đăng tối thiểu 2 video sản phẩm lên Shopee Video / TikTok Shop",
                ):
                    conn.execute(
                        "INSERT INTO campaign_tasks (task_id, campaign_id, title, is_recurring, done_dates_json, created_at) VALUES (?, ?, ?, 1, '[]', ?)",
                        (f"tsk_{uuid.uuid4().hex[:8]}", cid, default_task, ts),
                    )
        return self.get_campaign(cid)

    def set_campaign_product_stage(self, campaign_id: str, product_id: int, stage: str) -> dict:
        if stage not in CAMPAIGN_PRODUCT_STAGES and stage != "remove":
            raise ValueError("Giai đoạn sản phẩm không hợp lệ")
        with self.connect() as conn:
            r = conn.execute("SELECT products_stage_json FROM campaigns WHERE campaign_id=?", (campaign_id,)).fetchone()
            if not r:
                raise ApiError("404 Not Found", "Không tìm thấy chiến dịch ngành hàng")
            stages = json.loads(r["products_stage_json"] or "{}")
            if stage == "remove":
                stages.pop(str(product_id), None)
            else:
                stages[str(product_id)] = stage
            conn.execute("UPDATE campaigns SET products_stage_json=?, updated_at=? WHERE campaign_id=?", (json.dumps(stages), now(), campaign_id))
        return self.get_campaign(campaign_id)

    def toggle_task(self, campaign_id: str, task_id: str) -> dict:
        today = datetime.now().strftime("%Y-%m-%d")
        with self.connect() as conn:
            r = conn.execute("SELECT done_dates_json FROM campaign_tasks WHERE task_id=? AND campaign_id=?", (task_id, campaign_id)).fetchone()
            if not r:
                raise ApiError("404 Not Found", "Không tìm thấy công việc")
            dates = set(json.loads(r["done_dates_json"] or "[]"))
            if today in dates:
                dates.remove(today)
            else:
                dates.add(today)
            conn.execute("UPDATE campaign_tasks SET done_dates_json=? WHERE task_id=?", (json.dumps(sorted(dates)), task_id))
        return self.get_campaign(campaign_id)

    def add_task(self, campaign_id: str, title: str) -> dict:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO campaign_tasks (task_id, campaign_id, title, is_recurring, done_dates_json, created_at) VALUES (?, ?, ?, 1, '[]', ?)",
                (f"tsk_{uuid.uuid4().hex[:8]}", campaign_id, text(title, "title", 200, required=True), now()),
            )
        return self.get_campaign(campaign_id)

    def list_campaigns(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT campaign_id FROM campaigns ORDER BY updated_at DESC").fetchall()
        return [self.get_campaign(r["campaign_id"]) for r in rows]

    def get_campaign(self, campaign_id: str) -> dict:
        today = datetime.now().strftime("%Y-%m-%d")
        with self.connect() as conn:
            r = conn.execute("SELECT * FROM campaigns WHERE campaign_id=?", (campaign_id,)).fetchone()
            if not r:
                raise ApiError("404 Not Found", "Không tìm thấy chiến dịch")
            t_rows = conn.execute("SELECT * FROM campaign_tasks WHERE campaign_id=? ORDER BY created_at ASC", (campaign_id,)).fetchall()
            ord_sum = conn.execute(
                """
                SELECT COUNT(*) AS orders_cnt, COALESCE(SUM(quantity), 0) AS units_cnt,
                       COALESCE(SUM(gross_revenue_vnd), 0) AS gmv_vnd, COALESCE(SUM(net_profit_vnd), 0) AS profit_vnd
                FROM seller_orders WHERE campaign_id=? AND order_status != 'cancelled'
                """,
                (campaign_id,),
            ).fetchone()

        stages_map: dict[str, str] = json.loads(r["products_stage_json"] or "{}")
        attached_products = []
        for pid_str, stg in stages_map.items():
            if pid_str.isdigit():
                p = self.products.get_product(int(pid_str))
                if p:
                    attached_products.append({**p, "campaign_stage": stg, "campaign_stage_label": CAMPAIGN_PRODUCT_STAGES.get(stg, stg)})

        tasks = []
        for tr in t_rows:
            dd = json.loads(tr["done_dates_json"] or "[]")
            tasks.append({"task_id": tr["task_id"], "title": tr["title"], "done_today": today in dd})

        return {
            "campaign_id": r["campaign_id"],
            "name": r["name"],
            "industry": r["industry"],
            "industry_label": INDUSTRIES.get(r["industry"], r["industry"]),
            "status": r["status"],
            "target_revenue_vnd": r["target_revenue_vnd"],
            "budget_vnd": r["budget_vnd"],
            "shop_ids": json.loads(r["shop_ids_json"] or "[]"),
            "keywords": json.loads(r["keywords_json"] or "[]"),
            "products_stage": stages_map,
            "products": attached_products,
            "stages_catalog": CAMPAIGN_PRODUCT_STAGES,
            "videos": json.loads(r["videos_json"] or "[]"),
            "tasks": tasks,
            "sales_kpis": {
                "valid_orders": int(ord_sum["orders_cnt"] or 0),
                "units_sold": int(ord_sum["units_cnt"] or 0),
                "gmv_vnd": float(ord_sum["gmv_vnd"] or 0.0),
                "net_profit_vnd": float(ord_sum["profit_vnd"] or 0.0),
            },
            "note": r["note"],
            "updated_at": r["updated_at"],
        }

    def send_morning_briefing(self, campaign_id: str, trigger_kind: str = "manual") -> dict:
        cmp = self.get_campaign(campaign_id)
        local_date = datetime.now().strftime("%Y-%m-%d")
        pending_tasks = [t["title"] for t in cmp["tasks"] if not t["done_today"]]
        by_stage: dict[str, int] = {}
        for p in cmp["products"]:
            lbl = p["campaign_stage_label"]
            by_stage[lbl] = by_stage.get(lbl, 0) + 1
        stage_lines = "\n".join(f"  • {k}: {v} SP" for k, v in by_stage.items()) or "  • Chưa gắn sản phẩm"
        task_lines = "\n".join(f"  ☐ {t}" for t in pending_tasks[:5]) or "  ✅ Đã hoàn thành hết việc hôm nay!"
        kpi = cmp["sales_kpis"]
        msg = (
            f"🌅 BÁO CÁO CHIẾN DỊCH NGÀNH HÀNG ({local_date})\n"
            f"🏷 {cmp['name']} ({cmp['industry_label']})\n"
            f"📦 Tiến độ Phễu Sản phẩm ({len(cmp['products'])} SP):\n{stage_lines}\n"
            f"💰 Doanh số thực tế: {kpi['gmv_vnd']:,.0f}đ ({kpi['valid_orders']} đơn / {kpi['units_sold']} lượt bán) · Lãi ròng: {kpi['net_profit_vnd']:,.0f}đ\n"
            f"📋 Việc cần làm hôm nay:\n{task_lines}"
        )
        if self.telegram_bot:
            msg += f"\n🌐 {self.telegram_bot.remote_url('/chien-dich')}"
            self.telegram_bot.send_text(msg)
        if getattr(self, "history_logs", None) is not None and trigger_kind != "manual":
            self.history_logs.record_event(
                module="campaigns",
                action_type="scheduled_morning_briefing",
                title=f"Báo cáo Chiến dịch buổi sáng: {cmp['name']}",
                status="completed",
                summary=f"Đã gửi báo cáo chiến dịch {cmp['name']} ({len(cmp['products'])} SP · GMV {kpi['gmv_vnd']:,.0f}đ)",
                payload={"campaign_id": campaign_id, "local_date": local_date},
                notify_telegram=True,
            )
        with self.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO campaign_daily_reports (campaign_id, local_date, trigger_kind, summary_text, created_at) VALUES (?, ?, ?, ?, ?)",
                (campaign_id, local_date, trigger_kind, msg[:500], now()),
            )
        return {"sent": True, "campaign_id": campaign_id, "message": msg}

    # --- 2. Seller Orders CSV Import, Expenses & Profit Dashboard ------------

    def import_seller_orders_csv(self, csv_text: str, platform: str = "shopee", shop_id: str = "", campaign_id: str = "") -> dict:
        plat = platform.lower().strip()
        reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
        inserted = 0
        skipped_cancelled = 0
        ts = now()
        cfg = settings.read_settings(self.connect, self.secrets)
        default_fee_pct = (cfg["sourcing"]["tiktok_shop_fee_pct"] if "tiktok" in plat else cfg["sourcing"]["shopee_fee_pct"]) / 100.0

        with self.connect() as conn:
            for idx, row in enumerate(reader, start=1):
                norm = {str(k or "").strip().lower(): str(v or "").strip() for k, v in row.items()}
                oid = norm.get("order_id") or norm.get("mã đơn hàng") or norm.get("order id") or f"ord_{idx}"
                st_raw = (norm.get("status") or norm.get("trạng thái đơn hàng") or norm.get("order status") or "completed").lower()
                if any(tok in st_raw for tok in ("huỷ", "hủy", "cancel")):
                    skipped_cancelled += 1
                    continue
                title = norm.get("product_name") or norm.get("tên sản phẩm") or norm.get("product name") or "Sản phẩm đơn bán"
                qty = max(1, int(float(norm.get("quantity") or norm.get("số lượng") or 1)))
                rev = float(re.sub(r"[^\d.]", "", norm.get("total_amount") or norm.get("tổng giá trị đơn hàng") or norm.get("gross_revenue") or "0") or 0) if "re" in globals() else float((norm.get("gross_revenue") or norm.get("total_amount") or "0").replace(",", "").replace(".", "") or 0)
                cogs = float((norm.get("cogs_vnd") or norm.get("giá vốn") or "0").replace(",", "") or 0)
                fee = round(rev * default_fee_pct, 0)
                net_profit = rev - fee - cogs

                conn.execute(
                    """
                    INSERT INTO seller_orders
                    (platform, order_id, line_id, shop_id, campaign_id, product_id, product_title, quantity,
                     gross_revenue_vnd, platform_fee_vnd, shipping_subsidy_vnd, cogs_vnd, net_payout_vnd, net_profit_vnd,
                     order_status, ordered_at, created_at)
                    VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, 0.0, ?, ?, ?, 'completed', ?, ?)
                    ON CONFLICT(platform, order_id, line_id) DO UPDATE SET
                        gross_revenue_vnd=excluded.gross_revenue_vnd, net_profit_vnd=excluded.net_profit_vnd
                    """,
                    (plat, oid, str(idx), shop_id, campaign_id, title[:240], qty, rev, fee, cogs, rev - fee, net_profit, ts[:10], ts),
                )
                inserted += 1
        return {"imported_orders": inserted, "skipped_cancelled": skipped_cancelled, "summary": f"Đã nhập {inserted} đơn bán {plat} (loại {skipped_cancelled} đơn huỷ)"}

    def add_manual_order_or_expense(self, kind: str, body: dict) -> dict:
        ts = now()
        if kind == "order":
            plat = str(body.get("platform") or "shopee").lower()
            qty = max(1, int(body.get("quantity") or 1))
            rev = max(0.0, float(body.get("gross_revenue_vnd") or 0.0))
            cogs = max(0.0, float(body.get("cogs_vnd") or 0.0))
            fee = max(0.0, float(body.get("platform_fee_vnd") if body.get("platform_fee_vnd") is not None else round(rev * 0.12, 0)))
            profit = rev - fee - cogs
            oid = str(body.get("order_id") or f"ord_{uuid.uuid4().hex[:8]}")
            with self.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO seller_orders
                    (platform, order_id, line_id, shop_id, campaign_id, product_id, product_title, quantity,
                     gross_revenue_vnd, platform_fee_vnd, shipping_subsidy_vnd, cogs_vnd, net_payout_vnd, net_profit_vnd,
                     order_status, ordered_at, created_at)
                    VALUES (?, ?, '1', ?, ?, ?, ?, ?, ?, ?, 0.0, ?, ?, ?, 'completed', ?, ?)
                    """,
                    (
                        plat, oid, str(body.get("shop_id") or ""), str(body.get("campaign_id") or ""),
                        int(body["product_id"]) if body.get("product_id") else None,
                        text(body.get("product_title") or "Đơn hàng bán lẻ", "product_title", 200),
                        qty, rev, fee, cogs, rev - fee, profit, str(body.get("ordered_at") or ts[:10]), ts,
                    ),
                )
            return {"ok": True, "order_id": oid, "summary": f"Đã ghi nhận đơn bán {oid}: Doanh số {rev:,.0f}đ"}

        amt = max(0.0, float(body.get("amount_vnd") or 0.0))
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO seller_expenses (expense_type, platform, shop_id, campaign_id, product_id, amount_vnd, spent_date, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(body.get("expense_type") or "ads"),
                    str(body.get("platform") or "shopee"),
                    str(body.get("shop_id") or ""),
                    str(body.get("campaign_id") or ""),
                    int(body["product_id"]) if body.get("product_id") else None,
                    amt,
                    str(body.get("spent_date") or ts[:10]),
                    str(body.get("note") or "")[:300],
                    ts,
                ),
            )
        return {"ok": True, "summary": f"Đã ghi nhận chi phí {amt:,.0f}đ"}

    def sales_summary(self) -> dict:
        with self.connect() as conn:
            o = conn.execute(
                """
                SELECT COUNT(*) AS orders_count,
                       COALESCE(SUM(quantity), 0) AS units_sold,
                       COALESCE(SUM(gross_revenue_vnd), 0) AS gross_gmv_vnd,
                       COALESCE(SUM(platform_fee_vnd), 0) AS platform_fees_vnd,
                       COALESCE(SUM(cogs_vnd), 0) AS total_cogs_vnd,
                       COALESCE(SUM(net_profit_vnd), 0) AS gross_order_profit_vnd
                FROM seller_orders WHERE order_status != 'cancelled'
                """
            ).fetchone()
            exp_total = float(conn.execute("SELECT COALESCE(SUM(amount_vnd), 0) FROM seller_expenses").fetchone()[0] or 0.0)
            recent_orders = [dict(r) for r in conn.execute("SELECT * FROM seller_orders ORDER BY id DESC LIMIT 30").fetchall()]
            recent_expenses = [dict(r) for r in conn.execute("SELECT * FROM seller_expenses ORDER BY id DESC LIMIT 20").fetchall()]
            vault_stats = conn.execute(
                "SELECT COUNT(*) AS cnt, COALESCE(SUM(sold_count), 0) AS mkt_sold, COALESCE(SUM(gmv_vnd), 0) AS mkt_gmv FROM products WHERE bucket != 'da_loai'"
            ).fetchone()

        gmv = float(o["gross_gmv_vnd"] or 0.0)
        net_after_expenses = float(o["gross_order_profit_vnd"] or 0.0) - exp_total
        margin_pct = round((net_after_expenses / gmv * 100.0), 2) if gmv > 0 else 0.0
        return {
            "seller_kpis": {
                "valid_orders": int(o["orders_count"] or 0),
                "units_sold": int(o["units_sold"] or 0),
                "gross_gmv_vnd": gmv,
                "platform_fees_vnd": float(o["platform_fees_vnd"] or 0.0),
                "total_cogs_vnd": float(o["total_cogs_vnd"] or 0.0),
                "ads_and_ops_expenses_vnd": exp_total,
                "net_profit_vnd": net_after_expenses,
                "net_margin_pct": margin_pct,
            },
            "market_research_kpis": {
                "vault_products": int(vault_stats["cnt"] or 0),
                "observed_market_units_sold": int(vault_stats["mkt_sold"] or 0),
                "observed_market_gmv_vnd": float(vault_stats["mkt_gmv"] or 0.0),
            },
            "recent_orders": recent_orders,
            "recent_expenses": recent_expenses,
        }

    # --- 3. Seller Copywriting / Sourcing Assistant, Pins & Notifs -----------

    def chat_send(self, message: str, product_id: int | None = None) -> dict:
        msg = text(message, "message", 2000, required=True)
        prod = self.products.get_product(int(product_id)) if product_id else None
        cfg = settings.read_settings(self.connect, self.secrets)
        llm_cfg = cfg["llm"]
        reply = ""

        if llm_cfg.get("base_url") and llm_cfg.get("api_key") and llm_cfg.get("model"):
            try:
                sys_prompt = "Bạn là cố vấn nghiên cứu sản phẩm bán chạy, nhập hàng 1688/Pinduoduo/Taobao và vận hành Shopee/TikTok Shop."
                if prod:
                    sys_prompt += f" Sản phẩm đang xét: {prod['title']} (Giá bán: {prod['price_vnd']}đ, Giá vốn: {prod['cost_vnd']}đ, Đã bán: {prod['sold_count']})."
                req = urllib.request.Request(
                    llm_cfg["base_url"].rstrip("/") + "/chat/completions",
                    data=json.dumps({
                        "model": llm_cfg["model"],
                        "messages": [{"role": "system", "content": sys_prompt}, {"role": "user", "content": msg}],
                    }).encode("utf-8"),
                    headers={"Authorization": f"Bearer {llm_cfg['api_key']}", "Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=25) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    reply = data["choices"][0]["message"]["content"]
            except Exception:
                reply = ""

        if not reply:
            pname = prod["title"] if prod else "Sản phẩm mục tiêu"
            reply = (
                f"💡 Đề xuất triển khai bán hàng cho **{pname}**:\n"
                f"1. **Định vị & Combo khác biệt**: Ghép combo 2–3 món hoặc tặng kèm phụ kiện nhỏ để tránh so giá trực tiếp với shop bán lẻ đơn chiếc.\n"
                f"2. **Tối ưu SEO Từ khoá Shopee/TikTok**: Đặt tiêu đề `[Công dụng chính] + {pname} + [Chất liệu/Đặc điểm nổi bật] + [Bảo hành/Đổi trả]`.\n"
                f"3. **Kịch bản Video 15s**:\n"
                f"   • **0–3s (Hook)**: Quay cận cảnh vấn đề gây ức chế nhất và kết quả xử lý tức thì.\n"
                f"   • **3–12s (Body Demo)**: Test độ bền/công năng thực tế dưới ánh sáng tự nhiên.\n"
                f"   • **12–15s (CTA Shop)**: Nhấn mạnh hàng sẵn kho VN giao nhanh & ưu đãi lô đầu."
            )

        ts = now()
        with self.connect() as conn:
            conn.execute("INSERT INTO chat_messages (role, content, created_at) VALUES ('user', ?, ?)", (msg, ts))
            conn.execute("INSERT INTO chat_messages (role, content, created_at) VALUES ('assistant', ?, ?)", (reply, ts))
        return {"reply": reply}

    def dispatch(self, path: str, method: str, env, read_json):
        if path == "/api/campaigns" and method == "GET":
            return "200 OK", {"campaigns": self.list_campaigns(), "stages_catalog": CAMPAIGN_PRODUCT_STAGES}
        if path == "/api/campaigns" and method == "POST":
            body = json_object(read_json, env)
            cmp = self.create_or_update_campaign(body)
            return "200 OK", {"campaign": cmp, "summary": f"Đã tạo Chiến dịch Ngành hàng: {cmp['name']}"}
        if path.startswith("/api/campaigns/"):
            parts = path.strip("/").split("/")
            cid = parts[2]
            if len(parts) == 3 and method == "GET":
                return "200 OK", {"campaign": self.get_campaign(cid)}
            if len(parts) == 3 and method == "PATCH":
                return "200 OK", {"campaign": self.create_or_update_campaign(json_object(read_json, env), campaign_id=cid)}
            if len(parts) == 4 and parts[3] == "product-stage" and method == "POST":
                body = json_object(read_json, env)
                return "200 OK", {"campaign": self.set_campaign_product_stage(cid, int(body["product_id"]), str(body["stage"]))}
            if len(parts) == 4 and parts[3] == "tasks" and method == "POST":
                body = json_object(read_json, env)
                return "200 OK", {"campaign": self.add_task(cid, str(body.get("title") or ""))}
            if len(parts) == 5 and parts[3] == "tasks" and method == "POST":
                return "200 OK", {"campaign": self.toggle_task(cid, parts[4])}
            if len(parts) == 4 and parts[3] == "send-brief" and method == "POST":
                return "200 OK", self.send_morning_briefing(cid, trigger_kind="manual")

        if path == "/api/sales/summary" and method == "GET":
            return "200 OK", self.sales_summary()
        if path == "/api/sales/import-csv" and method == "POST":
            body = json_object(read_json, env, max_bytes=5 * 1024 * 1024)
            return "200 OK", self.import_seller_orders_csv(
                str(body.get("csv_text") or ""),
                platform=str(body.get("platform") or "shopee"),
                shop_id=str(body.get("shop_id") or ""),
                campaign_id=str(body.get("campaign_id") or ""),
            )
        if path == "/api/sales/orders" and method == "POST":
            return "200 OK", self.add_manual_order_or_expense("order", json_object(read_json, env))
        if path == "/api/sales/expenses" and method == "POST":
            return "200 OK", self.add_manual_order_or_expense("expense", json_object(read_json, env))

        if path == "/api/chat/messages" and method == "GET":
            with self.connect() as conn:
                rows = [dict(r) for r in conn.execute("SELECT * FROM chat_messages ORDER BY id ASC LIMIT 80").fetchall()]
            return "200 OK", {"messages": rows}
        if path == "/api/chat/send" and method == "POST":
            body = json_object(read_json, env)
            return "200 OK", self.chat_send(str(body.get("message") or ""), body.get("product_id"))
        if path == "/api/chat/clear" and method == "POST":
            with self.connect() as conn:
                conn.execute("DELETE FROM chat_messages")
            return "200 OK", {"cleared": True}

        if path == "/api/pins" and method == "GET":
            with self.connect() as conn:
                rows = [dict(r) for r in conn.execute("SELECT * FROM pins ORDER BY id DESC LIMIT 100").fetchall()]
            return "200 OK", {"pins": rows}
        if path == "/api/pins" and method == "POST":
            body = json_object(read_json, env)
            with self.connect() as conn:
                conn.execute(
                    "INSERT INTO pins (title, url, kind, note, created_at) VALUES (?, ?, ?, ?, ?)",
                    (text(body.get("title"), "title", 180, required=True), str(body.get("url") or ""), str(body.get("kind") or "competitor"), str(body.get("note") or "")[:500], now()),
                )
            return "200 OK", {"ok": True, "summary": "Đã lưu ghim tham khảo"}
        if path.startswith("/api/pins/") and method == "DELETE":
            pid = int(path.strip("/").split("/")[2])
            with self.connect() as conn:
                conn.execute("DELETE FROM pins WHERE id=?", (pid,))
            return "200 OK", {"deleted": True}
        return None


class DailyBriefingDaemon:
    def __init__(self, service: CampaignsAndSalesService, poll_sec: float = 45.0):
        self.service = service
        self.poll_sec = poll_sec
        self._started = False

    def start(self):
        if self._started:
            return
        self._started = True
        threading.Thread(target=self._loop, name="gs-daily-0800-brief", daemon=True).start()

    def _loop(self):
        while True:
            time.sleep(self.poll_sec)
            try:
                cfg = settings.read_settings(self.service.connect, self.service.secrets)
                if not cfg["notify"].get("daily_brief_enabled", True):
                    continue
                now_dt = datetime.now()
                target_h = int(cfg["notify"].get("daily_brief_hour", 8))
                target_m = int(cfg["notify"].get("daily_brief_minute", 0))
                if (now_dt.hour, now_dt.minute) < (target_h, target_m) or now_dt.hour >= 12:
                    continue
                local_date = now_dt.strftime("%Y-%m-%d")
                with self.service.connect() as conn:
                    active = conn.execute("SELECT campaign_id FROM campaigns WHERE status='active' AND daily_brief_enabled=1").fetchall()
                    for r in active:
                        cid = r["campaign_id"]
                        done = conn.execute(
                            "SELECT 1 FROM campaign_daily_reports WHERE campaign_id=? AND local_date=? AND trigger_kind='scheduled_0800'",
                            (cid, local_date),
                        ).fetchone()
                        if not done:
                            self.service.send_morning_briefing(cid, trigger_kind="scheduled_0800")
            except Exception:
                pass
