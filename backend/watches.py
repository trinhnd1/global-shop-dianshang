"""Keyword, Product & Shop Periodic Watcher with Snapshot Diffing (detecting new products, sales surges & price changes)."""
from datetime import datetime, timedelta, timezone
import json
import threading
import time
import uuid

from . import settings
from .markets import format_platform_market_label, parse_marketplace_spec
from .responses import ApiError, canonicalize_commerce_url, json_object, now, safe_id_str, text


def _future_iso(hours: float) -> str:
    dt = datetime.now(timezone.utc) + timedelta(hours=max(0.5, float(hours)))
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _item_key(it: dict) -> str:
    pid = safe_id_str(it.get("native_product_id") or "")
    if pid:
        return f"{it.get('platform', 'sp')}:{pid}"
    u = canonicalize_commerce_url(str(it.get("url") or ""))
    if u:
        return u
    return str(it.get("title") or "").strip().lower()[:120]


def compute_catalog_diff(prev_snapshot: dict, cur_items: list[dict], cur_total_count: int) -> dict:
    """Compare current check against previous check for Keyword Watches & Shop Watches."""
    prev_map: dict[str, dict] = prev_snapshot.get("items_by_key") or {}
    prev_total = prev_snapshot.get("total_count")
    is_baseline = not bool(prev_snapshot.get("initialized"))

    cur_map: dict[str, dict] = {}
    for rank, it in enumerate(cur_items, start=1):
        k = _item_key(it)
        if not k:
            continue
        cur_map[k] = {
            "key": k,
            "rank": rank,
            "platform": it.get("platform") or "",
            "native_product_id": safe_id_str(it.get("native_product_id") or ""),
            "title": str(it.get("title") or ""),
            "shop_name": str(it.get("shop_name") or ""),
            "price_vnd": float(it.get("price_vnd") or 0.0),
            "sold_count": int(it.get("sold_count") or 0),
            "gmv_vnd": float(it.get("gmv_vnd") or 0.0),
            "url": str(it.get("url") or ""),
            "image_url": str(it.get("image_url") or ""),
        }

    new_items = []
    rising_items = []
    price_changed_items = []
    dropped_items = []

    if not is_baseline:
        for k, cur in cur_map.items():
            if k not in prev_map:
                new_items.append(cur)
            else:
                old = prev_map[k]
                delta_sold = cur["sold_count"] - int(old.get("sold_count") or 0)
                delta_price = cur["price_vnd"] - float(old.get("price_vnd") or 0.0)
                if delta_sold > 0:
                    rising_items.append({
                        **cur,
                        "prev_sold_count": int(old.get("sold_count") or 0),
                        "delta_sold": delta_sold,
                        "delta_gmv_vnd": round(delta_sold * cur["price_vnd"], 0),
                    })
                if abs(delta_price) >= 500:
                    price_changed_items.append({
                        **cur,
                        "prev_price_vnd": float(old.get("price_vnd") or 0.0),
                        "delta_price_vnd": delta_price,
                    })
        for k, old in prev_map.items():
            if k not in cur_map:
                dropped_items.append(old)

    rising_items.sort(key=lambda x: x["delta_sold"], reverse=True)
    effective_total = max(int(cur_total_count or 0), len(cur_map))
    total_delta = (effective_total - int(prev_total)) if (prev_total is not None and not is_baseline) else 0

    return {
        "is_initial_baseline": is_baseline,
        "total_count": effective_total,
        "prev_total_count": int(prev_total) if prev_total is not None else None,
        "total_count_delta": total_delta,
        "sampled_count": len(cur_map),
        "new_items_count": len(new_items),
        "rising_items_count": len(rising_items),
        "dropped_items_count": len(dropped_items),
        "price_changed_count": len(price_changed_items),
        "new_items": new_items[:25],
        "rising_items": rising_items[:20],
        "price_changed_items": price_changed_items[:20],
        "dropped_items": dropped_items[:15],
        "next_snapshot": {
            "initialized": True,
            "captured_at": now(),
            "total_count": effective_total,
            "items_by_key": cur_map,
        },
    }


class WatchesService:
    def __init__(self, connect, secrets, products, keywords, shops, apify=None, treg=None, telegram_bot=None, history_logs=None):
        self.connect = connect
        self.secrets = secrets
        self.products = products
        self.keywords = keywords
        self.shops = shops
        self.apify = apify
        self.treg = treg
        self.telegram_bot = telegram_bot
        self.history_logs = history_logs

    def create_watch(self, body: dict) -> dict:
        wtype = str(body.get("watch_type") or "keyword").lower().strip()
        if wtype not in ("keyword", "product", "shop"):
            raise ValueError("Loại theo dõi phải là keyword (Từ khoá), product (Sản phẩm), hoặc shop (Shop)")
        target_key = text(body.get("target_key") or body.get("target_query") or body.get("keyword") or body.get("target_url"), "target_key", 300, required=True)
        target_url = str(body.get("target_url") or (target_key if target_key.startswith("http") else "")).strip()
        plat, mkt, _ = parse_marketplace_spec(str(body.get("platform") or "shopee_vn"), body.get("market"), url=target_url or target_key)
        if plat not in ("shopee", "tiktok_shop"):
            raise ValueError("Nền tảng theo dõi phải thuộc hệ Shopee (VN/PH/SG/MY/TH) hoặc TikTokShop (VN/PH/SG/MY/TH)")
        title = text(body.get("title") or body.get("target_label") or target_key, "title", 180, required=True)
        interval_hours = max(1.0, min(168.0, float(body.get("interval_hours") or 12.0)))
        shopee_filters = body.get("shopee_filters") if isinstance(body.get("shopee_filters"), dict) else {}
        is_special = 1 if bool(body.get("is_special", False)) else 0
        collection_id = str(body.get("collection_id") or "").strip()
        linked_pid = body.get("linked_product_id") or body.get("product_id")
        linked_sid = body.get("linked_shop_id") or body.get("shop_id") or ""
        init_snap = {"shopee_filters": shopee_filters} if shopee_filters else {}
        init_summary = {"shopee_filters": shopee_filters} if shopee_filters else {}
        wid = f"wt_{uuid.uuid4().hex[:10]}"
        ts = now()

        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO watches
                (watch_id, watch_type, platform, market, target_key, title, target_url, status, interval_hours,
                 linked_product_id, linked_shop_id, is_special, collection_id, last_checked_at, next_check_at,
                 last_summary_json, baseline_snapshot_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, '', ?, ?, ?, ?, ?)
                """,
                (
                    wid,
                    wtype,
                    plat,
                    mkt,
                    target_key,
                    title,
                    target_url,
                    interval_hours,
                    int(linked_pid) if linked_pid else None,
                    str(linked_sid),
                    is_special,
                    collection_id,
                    _future_iso(interval_hours),
                    json.dumps(init_summary, ensure_ascii=False),
                    json.dumps(init_snap, ensure_ascii=False),
                    ts,
                    ts,
                ),
            )

        if bool(body.get("run_immediately", False)):
            return self.run_watch_check(wid, trigger_kind="initial_create")
        return self.get_watch(wid)

    def run_watch_check(
        self,
        watch_id: str,
        trigger_kind: str = "manual",
        injected_items: list[dict] | None = None,
        injected_total_count: int | None = None,
        auto_save_new_to_vault: bool = True,
    ) -> dict:
        w = self.get_watch(watch_id, include_raw_snapshot=True)
        if not w:
            raise ApiError("404 Not Found", "Không tìm thấy mục theo dõi này")

        wtype = w["watch_type"]
        plat = w["platform"]
        mkt = w.get("market") or "VN"
        ch_code = f"{plat}_{mkt.lower()}"
        prev_snap = w.get("_snapshot") or {}

        if wtype == "keyword":
            saved_sf = (prev_snap.get("shopee_filters") or (w.get("last_summary") or {}).get("shopee_filters") or None)
            if injected_items is not None:
                items = injected_items
                tot_cnt = injected_total_count if injected_total_count is not None else len(items)
            else:
                res = self.keywords.research_keyword(
                    keyword=w["target_key"],
                    platform=ch_code,
                    market=mkt,
                    limit=20,
                    score_jev=False,
                    save_top_to_vault=False,
                    shopee_filters=saved_sf if isinstance(saved_sf, dict) and saved_sf else None,
                )
                items = res["items"]
                tot_cnt = res["summary_stats"]["total_products"]

            diff = compute_catalog_diff(prev_snap, items, tot_cnt)
            if auto_save_new_to_vault and diff["new_items"]:
                for ni in diff["new_items"][:15]:
                    if ni.get("title"):
                        ni_copy = {**ni, "market": mkt}
                        self.products.upsert_product(ni_copy, source=f"watch_keyword_new:{ch_code}:{w['target_key']}")
            next_snap = diff.pop("next_snapshot")
            if saved_sf:
                next_snap["shopee_filters"] = saved_sf
            summary = {
                "watch_type": "keyword",
                "shopee_filters": saved_sf or {},
                "total_count": diff["total_count"],
                "prev_total_count": diff["prev_total_count"],
                "total_count_delta": diff["total_count_delta"],
                "new_items_count": diff["new_items_count"],
                "rising_items_count": diff["rising_items_count"],
                "dropped_items_count": diff["dropped_items_count"],
                "headline": (
                    f"Khởi tạo mốc gốc: {diff['total_count']} SP ({diff['sampled_count']} SP đầu)"
                    if diff["is_initial_baseline"]
                    else f"Tổng {diff['total_count']} SP ({diff['total_count_delta']:+d}) · +{diff['new_items_count']} SP mới · {diff['rising_items_count']} SP tăng lượt bán"
                ),
            }

        elif wtype == "shop":
            if injected_items is not None:
                items = injected_items
                tot_cnt = injected_total_count if injected_total_count is not None else len(items)
            else:
                scan = self.shops.scan_and_evaluate_shop_products(
                    shop_query=w["target_url"] or w["target_key"],
                    platform=plat,
                    limit=24,
                    save_to_vault=False,
                    save_competitor_shop=False,
                )
                items = scan["items"]
                tot_cnt = scan["total_products"]

            diff = compute_catalog_diff(prev_snap, items, tot_cnt)
            if auto_save_new_to_vault and diff["new_items"]:
                for ni in diff["new_items"][:15]:
                    if ni.get("title"):
                        self.products.upsert_product(ni, source=f"watch_shop_new:{plat}:{w['title']}")
            next_snap = diff.pop("next_snapshot")
            summary = {
                "watch_type": "shop",
                "total_count": diff["total_count"],
                "prev_total_count": diff["prev_total_count"],
                "new_items_count": diff["new_items_count"],
                "rising_items_count": diff["rising_items_count"],
                "headline": (
                    f"Mốc gốc Shop: {diff['total_count']} SP"
                    if diff["is_initial_baseline"]
                    else f"Shop có +{diff['new_items_count']} SP mới đăng · {diff['rising_items_count']} SP tăng doanh số"
                ),
            }

        else:
            # Product Watch (Shopee / TikTok Shop)
            prod_data = None
            if injected_items:
                prod_data = injected_items[0]
            else:
                cfg = settings.read_settings(self.connect, self.secrets)
                apify_toks = settings.apify_tokens(cfg)
                treg_tok = (cfg["providers"].get("treg_key") or "").strip()
                target = w["target_url"] or w["target_key"]
                # STRICT PRIORITY #1: Apify
                if apify_toks and self.apify:
                    try:
                        if plat == "shopee":
                            prod_data = self.apify.scrape_shopee_product(apify_toks, target)
                        else:
                            prod_data = self.apify.scrape_tiktok_shop_detail(apify_toks, target)
                    except Exception:
                        prod_data = None
                # STRICT PRIORITY #2: Treg Backup
                if not prod_data and treg_tok and self.treg and plat == "tiktok_shop":
                    try:
                        prod_data = self.treg.fetch_tiktok_shop_product_detail(treg_tok, target)
                    except Exception:
                        prod_data = None
                if not prod_data and w.get("linked_product_id"):
                    prod_data = self.products.get_product(int(w["linked_product_id"]))

            cur_price = float((prod_data or {}).get("price_vnd") or 0.0)
            cur_sold = int((prod_data or {}).get("sold_count") or 0)
            cur_stock = int((prod_data or {}).get("stock") or 0)
            cur_rating = float((prod_data or {}).get("rating") or 0.0)
            is_base = not bool(prev_snap.get("initialized"))
            prev_sold = int(prev_snap.get("sold_count") or 0)
            prev_price = float(prev_snap.get("price_vnd") or 0.0)
            prev_stock = int(prev_snap.get("stock") or 0)
            raw_delta_sold = 0 if is_base else max(0, cur_sold - prev_sold)
            stock_drop = 0 if is_base else (max(0, prev_stock - cur_stock) if (prev_stock > 0 and cur_stock > 0 and cur_stock < prev_stock) else 0)
            delta_sold = max(raw_delta_sold, stock_drop)
            delta_price = 0.0 if is_base else (cur_price - prev_price)

            if prod_data and prod_data.get("title"):
                saved_p = self.products.upsert_product(prod_data, source=f"watch_product:{plat}")
                if not w.get("linked_product_id"):
                    with self.connect() as conn:
                        conn.execute("UPDATE watches SET linked_product_id=? WHERE watch_id=?", (saved_p["id"], watch_id))

            diff = {
                "is_initial_baseline": is_base,
                "total_count": 1,
                "prev_total_count": 1 if not is_base else None,
                "new_items_count": 0,
                "rising_items_count": 1 if delta_sold > 0 else 0,
                "dropped_items_count": 0,
                "price_vnd": cur_price,
                "prev_price_vnd": prev_price if not is_base else None,
                "delta_price_vnd": delta_price,
                "sold_count": cur_sold,
                "prev_sold_count": prev_sold if not is_base else None,
                "delta_sold": delta_sold,
                "stock": cur_stock,
                "prev_stock": prev_stock if not is_base else None,
                "stock_drop_inferred_sold": stock_drop,
                "estimated_gmv_delta_vnd": round(delta_sold * cur_price, 0),
                "rating": cur_rating,
            }
            next_snap = {
                "initialized": True,
                "captured_at": now(),
                "price_vnd": cur_price,
                "sold_count": cur_sold,
                "stock": cur_stock,
                "rating": cur_rating,
            }
            stk_note = f" · Tồn kho {cur_stock}" if cur_stock > 0 else ""
            stk_drop_note = f" (suy từ giảm tồn kho -{stock_drop})" if (stock_drop > raw_delta_sold and stock_drop > 0) else ""
            summary = {
                "watch_type": "product",
                "price_vnd": cur_price,
                "sold_count": cur_sold,
                "stock": cur_stock,
                "delta_sold": delta_sold,
                "stock_drop_inferred_sold": stock_drop,
                "delta_price_vnd": delta_price,
                "new_items_count": 0,
                "rising_items_count": 1 if delta_sold > 0 else 0,
                "headline": (
                    f"Mốc gốc SP: Giá {cur_price:,.0f}đ · Đã bán {cur_sold}{stk_note}"
                    if is_base
                    else f"Đã bán {cur_sold} (+{delta_sold} lượt bán gần đây{stk_drop_note}){stk_note} · Giá {cur_price:,.0f}đ ({delta_price:+,.0f}đ)"
                ),
            }

        run_id = f"wrun_{uuid.uuid4().hex[:10]}"
        ts = now()
        nxt = _future_iso(w["interval_hours"])
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO watch_runs
                (run_id, watch_id, watch_type, platform, trigger_kind, status, total_count, prev_total_count,
                 new_items_count, rising_items_count, dropped_items_count, diff_json, snapshot_json, created_at)
                VALUES (?, ?, ?, ?, ?, 'completed', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    watch_id,
                    wtype,
                    plat,
                    trigger_kind,
                    int(diff.get("total_count") or 0),
                    diff.get("prev_total_count"),
                    int(diff.get("new_items_count") or 0),
                    int(diff.get("rising_items_count") or 0),
                    int(diff.get("dropped_items_count") or 0),
                    json.dumps(diff, ensure_ascii=False),
                    json.dumps(next_snap, ensure_ascii=False),
                    ts,
                ),
            )
            conn.execute(
                """
                UPDATE watches
                SET last_checked_at=?, next_check_at=?, last_summary_json=?, baseline_snapshot_json=?, updated_at=?
                WHERE watch_id=?
                """,
                (ts, nxt, json.dumps(summary, ensure_ascii=False), json.dumps(next_snap, ensure_ascii=False), ts, watch_id),
            )

        stock_inferred = int(diff.get("stock_drop_inferred_sold") or 0)
        delta_sold_prod = int(diff.get("delta_sold") or 0) if wtype == "product" else 0
        has_new = int(diff.get("new_items_count") or 0) > 0
        has_stock_or_sales_surge = (wtype == "product" and (stock_inferred > 0 or delta_sold_prod > 0))

        # Record scheduled background checks directly in GS-XXXX History Log -> auto-pushed to Telegram Bot!
        if self.history_logs is not None and trigger_kind == "scheduled":
            hl_lines = [f"+ {x['title'][:70]}" for x in (diff.get("new_items") or [])[:4]]
            if stock_inferred > 0:
                hl_lines.append(f"Tồn kho giảm {diff.get('prev_stock')} -> {diff.get('stock')} (suy ra +{stock_inferred} đơn bán)")
            self.history_logs.record_event(
                module="watches",
                action_type="scheduled_watch_check",
                title=f"Theo dõi định kỳ: {w['title'][:110]}",
                status="completed",
                summary=summary["headline"],
                payload={"watch_id": watch_id, "watch_type": wtype, "diff": diff, "highlights": hl_lines},
                notify_telegram=True,
            )

        if self.telegram_bot and (has_new or has_stock_or_sales_surge) and trigger_kind != "scheduled":
            try:
                cfg = settings.read_settings(self.connect, self.secrets)
                if cfg["notify"].get("telegram_enabled", True) and cfg["notify"].get("telegram_token"):
                    if has_new:
                        top_titles = "\n".join(f"  + {x['title'][:65]}" for x in (diff.get("new_items") or [])[:4])
                        self.telegram_bot.send_text(
                            f"🔔 Phát hiện +{diff['new_items_count']} sản phẩm mới!\n"
                            f"• Theo dõi [{wtype.upper()} · {plat}]: {w['title']}\n"
                            f"• {summary['headline']}\n"
                            f"{top_titles}\n"
                            f"🌐 {self.telegram_bot.remote_url('/theo-doi')}"
                        )
                    elif has_stock_or_sales_surge:
                        self.telegram_bot.send_text(
                            f"📦 Biến động Lượt bán / Tồn kho Sản phẩm Theo dõi Đặc biệt!\n"
                            f"• SP: {w['title']}\n"
                            f"• {summary['headline']}\n"
                            f"🌐 {self.telegram_bot.remote_url('/theo-doi')}"
                        )
            except Exception:
                pass

        return {
            "run_id": run_id,
            "watch": self.get_watch(watch_id),
            "diff": diff,
            "summary": f"[{wtype.upper()} · {plat}] {w['title']}: {summary['headline']}",
        }

    def list_watches(self, watch_type: str = "") -> list[dict]:
        with self.connect() as conn:
            if watch_type in ("keyword", "product", "shop"):
                rows = conn.execute("SELECT * FROM watches WHERE status != 'archived' AND watch_type=? ORDER BY updated_at DESC", (watch_type,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM watches WHERE status != 'archived' ORDER BY updated_at DESC").fetchall()
        return [self._format_watch(r) for r in rows]

    def get_watch(self, watch_id: str, include_raw_snapshot: bool = False) -> dict | None:
        with self.connect() as conn:
            r = conn.execute("SELECT * FROM watches WHERE watch_id=?", (watch_id,)).fetchone()
        if not r:
            return None
        d = self._format_watch(r)
        if include_raw_snapshot:
            d["_snapshot"] = json.loads(r["baseline_snapshot_json"] or "{}")
        return d

    def list_runs(self, watch_id: str = "", limit: int = 25) -> list[dict]:
        with self.connect() as conn:
            if watch_id:
                rows = conn.execute("SELECT * FROM watch_runs WHERE watch_id=? ORDER BY created_at DESC LIMIT ?", (watch_id, limit)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM watch_runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [
            {
                "run_id": r["run_id"],
                "watch_id": r["watch_id"],
                "watch_type": r["watch_type"],
                "platform": r["platform"],
                "trigger_kind": r["trigger_kind"],
                "total_count": r["total_count"],
                "prev_total_count": r["prev_total_count"],
                "new_items_count": r["new_items_count"],
                "rising_items_count": r["rising_items_count"],
                "dropped_items_count": r["dropped_items_count"],
                "diff": json.loads(r["diff_json"] or "{}"),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def set_status(self, watch_id: str, status: str) -> dict:
        if status not in ("active", "paused", "archived"):
            raise ValueError("Trạng thái theo dõi không hợp lệ")
        with self.connect() as conn:
            conn.execute("UPDATE watches SET status=?, updated_at=? WHERE watch_id=?", (status, now(), watch_id))
        return self.get_watch(watch_id) or {"watch_id": watch_id, "status": status}

    def run_due_watches(self) -> int:
        ts = now()
        with self.connect() as conn:
            due = conn.execute(
                "SELECT watch_id FROM watches WHERE status='active' AND next_check_at != '' AND next_check_at <= ? LIMIT 4",
                (ts,),
            ).fetchall()
        count = 0
        for r in due:
            try:
                self.run_watch_check(r["watch_id"], trigger_kind="scheduled")
                count += 1
            except Exception:
                with self.connect() as conn:
                    conn.execute("UPDATE watches SET next_check_at=? WHERE watch_id=?", (_future_iso(4.0), r["watch_id"]))
        return count

    @staticmethod
    def _format_watch(r) -> dict:
        mkt = r["market"] or "VN"
        return {
            "watch_id": r["watch_id"],
            "watch_type": r["watch_type"],
            "platform": r["platform"],
            "market": mkt,
            "channel_label": format_platform_market_label(r["platform"], mkt),
            "target_key": r["target_key"],
            "title": r["title"],
            "target_url": r["target_url"],
            "status": r["status"],
            "interval_hours": r["interval_hours"],
            "linked_product_id": r["linked_product_id"],
            "linked_shop_id": r["linked_shop_id"],
            "is_special": bool(r["is_special"]) if "is_special" in r.keys() else False,
            "collection_id": r["collection_id"] if "collection_id" in r.keys() else "",
            "last_checked_at": r["last_checked_at"],
            "next_check_at": r["next_check_at"],
            "last_summary": json.loads(r["last_summary_json"] or "{}"),
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }

    def dispatch(self, path: str, method: str, env, read_json):
        if path == "/api/watches" and method == "GET":
            return "200 OK", {"watches": self.list_watches(), "recent_runs": self.list_runs(limit=20)}
        if path == "/api/watches" and method == "POST":
            body = json_object(read_json, env)
            res = self.create_watch(body)
            return "200 OK", res if "run_id" in res else {"watch": res, "summary": f"Đã tạo theo dõi: {res['title']}"}
        if path.startswith("/api/watches/"):
            parts = path.strip("/").split("/")
            wid = parts[2]
            if len(parts) == 3 and method == "GET":
                w = self.get_watch(wid)
                if not w:
                    raise ApiError("404 Not Found", "Không tìm thấy mục theo dõi")
                return "200 OK", {"watch": w, "runs": self.list_runs(wid, limit=20)}
            if len(parts) == 3 and method == "DELETE":
                return "200 OK", self.set_status(wid, "archived")
            if len(parts) == 4 and parts[3] == "check" and method == "POST":
                return "200 OK", self.run_watch_check(wid, trigger_kind="manual")
            if len(parts) == 4 and parts[3] in ("pause", "resume") and method == "POST":
                return "200 OK", {"watch": self.set_status(wid, "paused" if parts[3] == "pause" else "active")}
        return None


class WatchSchedulerDaemon:
    def __init__(self, watches_service: WatchesService, poll_sec: float = 30.0):
        self.watches = watches_service
        self.poll_sec = poll_sec
        self._started = False

    def start(self):
        if self._started:
            return
        self._started = True
        threading.Thread(target=self._loop, name="gs-watch-scheduler", daemon=True).start()

    def _loop(self):
        while True:
            time.sleep(self.poll_sec)
            try:
                self.watches.run_due_watches()
            except Exception:
                pass
