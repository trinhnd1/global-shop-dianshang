"""Kho Shop (Own & Competitor Shops Vault) + Shop Product Scanner & Evaluator (Shopee & TikTok Shop)."""
import json
import re
from urllib.parse import parse_qs
import uuid

from . import settings
from .products import INDUSTRIES
from .responses import ApiError, json_object, now, safe_id_str, text


def parse_shop_target(raw: str, default_platform: str = "shopee") -> tuple[str, str, str]:
    s = (raw or "").strip()
    low = s.lower()
    if "shopee." in low:
        m = re.search(r"shopee\.[^/]+/(?:shop/)?([^/?#]+)", s)
        handle = m.group(1) if m else s
        return "shopee", handle, s
    if "tiktok.com" in low:
        m = re.search(r"tiktok\.com/@?([^/?#]+)", s)
        handle = m.group(1) if m else s
        return "tiktok_shop", handle, s
    if "lazada." in low:
        return "lazada", s, s
    clean_handle = s.lstrip("@").strip()
    plat = "tiktok_shop" if default_platform in ("tiktok", "tiktok_shop") else default_platform
    url = f"https://shopee.vn/{clean_handle}" if plat == "shopee" and clean_handle else s
    return plat, clean_handle, url


class ShopsService:
    def __init__(self, connect, secrets, products, apify=None, treg=None, jev=None):
        self.connect = connect
        self.secrets = secrets
        self.products = products
        self.apify = apify
        self.treg = treg
        self.jev = jev

    def create_or_update_shop(self, body: dict, shop_id: str | None = None) -> dict:
        role = str(body.get("role") or "own_shop").strip()
        if role not in ("own_shop", "competitor_shop"):
            raise ValueError("Vai trò shop phải là own_shop (Shop của mình) hoặc competitor_shop (Shop đối thủ)")
        raw_input = str(body.get("shop_url") or body.get("handle") or body.get("shop_name") or "").strip()
        plat_in = str(body.get("platform") or "shopee").lower().strip()
        plat, handle, url = parse_shop_target(raw_input, plat_in)
        shop_name = text(body.get("shop_name") or handle, "shop_name", 140, required=True)
        industry = str(body.get("industry") or "gia_dung").strip()
        if industry not in INDUSTRIES:
            industry = "gia_dung"
        tags = body.get("niche_tags") if isinstance(body.get("niche_tags"), list) else []
        fee_pct = float(body.get("platform_fee_pct") or (11.5 if plat == "tiktok_shop" else 12.5))
        note = str(body.get("note") or "")[:800]
        ts = now()

        sid = shop_id or f"shop_{uuid.uuid4().hex[:10]}"
        with self.connect() as conn:
            existing = conn.execute("SELECT * FROM shops WHERE shop_id=?", (sid,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE shops
                    SET role=?, platform=?, handle=?, shop_name=?, shop_url=?, industry=?,
                        niche_tags_json=?, platform_fee_pct=?, note=?, updated_at=?
                    WHERE shop_id=?
                    """,
                    (role, plat, handle, shop_name, url, industry, json.dumps(tags, ensure_ascii=False), fee_pct, note, ts, sid),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO shops
                    (shop_id, role, platform, market, native_shop_id, handle, shop_name, shop_url, industry,
                     niche_tags_json, status, platform_fee_pct, stats_json, note, created_at, updated_at)
                    VALUES (?, ?, ?, 'VN', ?, ?, ?, ?, ?, ?, 'active', ?, '{}', ?, ?, ?)
                    """,
                    (
                        sid,
                        role,
                        plat,
                        safe_id_str(body.get("native_shop_id") or ""),
                        handle,
                        shop_name,
                        url,
                        industry,
                        json.dumps(tags, ensure_ascii=False),
                        fee_pct,
                        note,
                        ts,
                        ts,
                    ),
                )
        return self.get_shop(sid)

    def list_shops(self, role: str = "") -> list[dict]:
        with self.connect() as conn:
            if role in ("own_shop", "competitor_shop"):
                rows = conn.execute("SELECT * FROM shops WHERE role=? ORDER BY updated_at DESC", (role,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM shops ORDER BY role ASC, updated_at DESC").fetchall()
            prod_rows = conn.execute("SELECT id, record FROM products WHERE bucket != 'da_loai'").fetchall()

        assigned_counts: dict[str, int] = {}
        for pr in prod_rows:
            rec = json.loads(pr["record"] or "{}")
            asid = rec.get("assigned_shop_id") or ""
            if asid:
                assigned_counts[asid] = assigned_counts.get(asid, 0) + 1

        return [self._format_shop(r, assigned_counts.get(r["shop_id"], 0)) for r in rows]

    def get_shop(self, shop_id: str) -> dict:
        with self.connect() as conn:
            r = conn.execute("SELECT * FROM shops WHERE shop_id=?", (shop_id,)).fetchone()
        if not r:
            raise ApiError("404 Not Found", "Không tìm thấy Shop này trong Kho Shop")
        return self._format_shop(r, 0)

    def delete_shop(self, shop_id: str) -> dict:
        with self.connect() as conn:
            conn.execute("DELETE FROM shops WHERE shop_id=?", (shop_id,))
        return {"deleted": True, "shop_id": shop_id}

    def scan_and_evaluate_shop_products(
        self,
        shop_query: str,
        platform: str = "shopee",
        limit: int = 20,
        score_top_jev: int = 0,
        save_to_vault: bool = True,
        save_competitor_shop: bool = True,
    ) -> dict:
        """Find & evaluate products sold by a Shopee or TikTok Shop competitor."""
        q = text(shop_query, "shop_query", 240, required=True)
        plat, handle, url = parse_shop_target(q, platform.lower().strip())
        lim = max(4, min(40, int(limit)))

        cfg = settings.read_settings(self.connect, self.secrets)
        apify_toks = settings.apify_tokens(cfg)
        treg_tok = (cfg["providers"].get("treg_key") or "").strip()
        max_chg = float(cfg["providers"].get("apify_max_charge_usd") or 0.06)

        items: list[dict] = []
        source_used = "none"

        if plat == "shopee":
            if apify_toks and self.apify:
                try:
                    slug, items = self.apify.scrape_shopee_shop(apify_toks, url or handle, limit=lim, max_charge_usd=max_chg)
                    source_used = f"apify:{slug}"
                except Exception:
                    items = []
                if not items:
                    try:
                        slug, items = self.apify.search_shopee(apify_toks, handle, limit=lim, max_charge_usd=max_chg)
                        source_used = f"apify:{slug}"
                    except Exception:
                        items = []
        else:
            if apify_toks and self.apify:
                try:
                    slug, items = self.apify.search_tiktok_shop(apify_toks, handle, limit=lim, max_charge_usd=max_chg)
                    source_used = f"apify:{slug}"
                except Exception:
                    items = []
            if not items and treg_tok and self.treg:
                try:
                    ep, items, _ = self.treg.search_tiktok_shop(treg_tok, handle, limit=lim)
                    source_used = f"treg:{ep}"
                except Exception:
                    items = []

        # Sort by GMV / sold_count to identify Hero Bestsellers vs Traffic Builders
        items.sort(key=lambda x: (float(x.get("gmv_vnd") or 0.0), int(x.get("sold_count") or 0)), reverse=True)
        total_sold = sum(int(x.get("sold_count") or 0) for x in items)
        total_gmv = sum(float(x.get("gmv_vnd") or 0.0) for x in items)
        prices = [float(x["price_vnd"]) for x in items if float(x.get("price_vnd") or 0) > 0]
        avg_price = round(sum(prices) / len(prices), 0) if prices else 0.0

        for idx, it in enumerate(items):
            if idx < 3 and int(it.get("sold_count") or 0) > 0:
                it["shop_product_role"] = "hero_chu_luc"
            elif float(it.get("price_vnd") or 0) < avg_price * 0.65 and avg_price > 0:
                it["shop_product_role"] = "sp_moi_keo_traffic"
            else:
                it["shop_product_role"] = "sp_bo_tro"

        saved_products = []
        if save_to_vault and items:
            for it in items:
                if it.get("title"):
                    p = self.products.upsert_product(it, source=f"shop_scan:{plat}:{handle}")
                    saved_products.append(p)

        scored_count = 0
        if score_top_jev > 0 and saved_products and self.products.jev:
            for p in saved_products[: min(6, int(score_top_jev))]:
                try:
                    self.products.score_product_jev(p["id"])
                    scored_count += 1
                except Exception:
                    break

        comp_shop_id = ""
        detected_name = (items[0].get("shop_name") if items else "") or handle
        if save_competitor_shop:
            saved_shop = self.create_or_update_shop({
                "role": "competitor_shop",
                "platform": plat,
                "handle": handle,
                "shop_name": detected_name,
                "shop_url": url,
                "note": f"Quét tự động ({len(items)} SP, tổng bán {total_sold})",
            })
            comp_shop_id = saved_shop["shop_id"]
            with self.connect() as conn:
                conn.execute(
                    "UPDATE shops SET stats_json=?, updated_at=? WHERE shop_id=?",
                    (
                        json.dumps({
                            "sampled_products": len(items),
                            "total_sold": total_sold,
                            "estimated_gmv_vnd": total_gmv,
                            "avg_price_vnd": avg_price,
                        }, ensure_ascii=False),
                        now(),
                        comp_shop_id,
                    ),
                )

        scan_id = f"sps_{uuid.uuid4().hex[:10]}"
        summary_obj = {
            "source_used": source_used,
            "hero_count": sum(1 for x in items if x.get("shop_product_role") == "hero_chu_luc"),
            "scored_jev_count": scored_count,
            "saved_to_vault_count": len(saved_products),
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO shop_product_scans
                (scan_id, shop_id, platform, shop_query, shop_name, total_products, total_sold,
                 estimated_gmv_vnd, avg_price_vnd, summary_json, items_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scan_id,
                    comp_shop_id,
                    plat,
                    q,
                    detected_name,
                    len(items),
                    total_sold,
                    total_gmv,
                    avg_price,
                    json.dumps(summary_obj, ensure_ascii=False),
                    json.dumps(items, ensure_ascii=False),
                    now(),
                ),
            )

        return {
            "scan_id": scan_id,
            "shop_id": comp_shop_id,
            "platform": plat,
            "shop_name": detected_name,
            "total_products": len(items),
            "total_sold": total_sold,
            "estimated_gmv_vnd": total_gmv,
            "avg_price_vnd": avg_price,
            "items": items,
            "summary_stats": summary_obj,
            "summary": f"Quét Shop '{detected_name}' ({plat}): {len(items)} SP, tổng lượt bán {total_sold}",
        }

    def list_scans(self, limit: int = 25) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM shop_product_scans ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [
            {
                "scan_id": r["scan_id"],
                "shop_id": r["shop_id"],
                "platform": r["platform"],
                "shop_query": r["shop_query"],
                "shop_name": r["shop_name"],
                "total_products": r["total_products"],
                "total_sold": r["total_sold"],
                "estimated_gmv_vnd": r["estimated_gmv_vnd"],
                "avg_price_vnd": r["avg_price_vnd"],
                "items": json.loads(r["items_json"] or "[]"),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    @staticmethod
    def _format_shop(r, assigned_products_count: int) -> dict:
        return {
            "shop_id": r["shop_id"],
            "role": r["role"],
            "role_label": "Shop vận hành của mình" if r["role"] == "own_shop" else "Shop đối thủ theo dõi",
            "platform": r["platform"],
            "market": r["market"],
            "native_shop_id": r["native_shop_id"],
            "handle": r["handle"],
            "shop_name": r["shop_name"],
            "shop_url": r["shop_url"],
            "industry": r["industry"],
            "industry_label": INDUSTRIES.get(r["industry"], r["industry"]),
            "niche_tags": json.loads(r["niche_tags_json"] or "[]"),
            "status": r["status"],
            "platform_fee_pct": r["platform_fee_pct"],
            "stats": json.loads(r["stats_json"] or "{}"),
            "assigned_products_count": assigned_products_count,
            "note": r["note"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }

    def dispatch(self, path: str, method: str, env, read_json):
        if path == "/api/shops" and method == "GET":
            qs = parse_qs(env.get("QUERY_STRING") or "")
            role = (qs.get("role") or [""])[0]
            return "200 OK", {"shops": self.list_shops(role=role), "scans": self.list_scans(15)}
        if path == "/api/shops" and method == "POST":
            body = json_object(read_json, env)
            shop = self.create_or_update_shop(body)
            return "200 OK", {"shop": shop, "summary": f"Đã lưu Shop: {shop['shop_name']} ({shop['platform']})"}
        if path == "/api/shops/scan-products" and method == "POST":
            body = json_object(read_json, env)
            return "200 OK", self.scan_and_evaluate_shop_products(
                shop_query=text(body.get("shop_query"), "shop_query", 240, required=True),
                platform=str(body.get("platform") or "shopee"),
                limit=int(body.get("limit") or 20),
                score_top_jev=int(body.get("score_top_jev") or 0),
                save_to_vault=bool(body.get("save_to_vault", True)),
                save_competitor_shop=bool(body.get("save_competitor_shop", True)),
            )
        if path == "/api/shops/scans" and method == "GET":
            return "200 OK", {"scans": self.list_scans(30)}
        if path.startswith("/api/shops/"):
            parts = path.strip("/").split("/")
            if len(parts) == 3:
                sid = parts[2]
                if method == "PATCH":
                    return "200 OK", {"shop": self.create_or_update_shop(json_object(read_json, env), shop_id=sid)}
                if method == "DELETE":
                    return "200 OK", self.delete_shop(sid)
        return None
