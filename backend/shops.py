"""Shop của tôi (TikTok Shop · Shopee · Facebook Fanpage · Đa kênh) & Kho Shop Đối thủ + Quét SP theo Shop."""
import json
import re
from urllib.parse import parse_qs, urlparse
import uuid

from . import settings
from .markets import detect_market_from_url, format_platform_market_label, parse_marketplace_spec, shopee_domain_for_market
from .products import INDUSTRIES, INDUSTRY_ICONS
from .responses import ApiError, json_object, now, safe_id_str, text

SHOP_PLATFORMS = {
    "tiktok_shop": {"label": "TikTokShop", "icon": "🛒", "default_fee_pct": 11.5},
    "shopee": {"label": "Shopee", "icon": "🛍", "default_fee_pct": 12.5},
    "facebook_fanpage": {"label": "Facebook Fanpage", "icon": "📘", "default_fee_pct": 0.0},
    "tiktok_channel": {"label": "Kênh TikTok (Giỏ hàng)", "icon": "🎵", "default_fee_pct": 11.5},
    "lazada": {"label": "Lazada", "icon": "📦", "default_fee_pct": 11.0},
    "instagram": {"label": "Instagram Shop", "icon": "📸", "default_fee_pct": 0.0},
    "website": {"label": "Website / Landing Page", "icon": "🌐", "default_fee_pct": 0.0},
}

SHOP_STATUSES = {
    "active": "🟢 Đang hoạt động",
    "warming": "🟡 Đang nuôi / Setup",
    "paused": "⏸ Tạm nghỉ",
}

PLATFORM_ALIASES = {
    "tiktok": "tiktok_shop",
    "tiktokshop": "tiktok_shop",
    "facebook": "facebook_fanpage",
    "fanpage": "facebook_fanpage",
    "fb": "facebook_fanpage",
    "fb_fanpage": "facebook_fanpage",
    "ig": "instagram",
    "web": "website",
}


def normalize_shop_platform(raw_plat: str) -> str:
    b_plat, _, _ = parse_marketplace_spec(raw_plat or "shopee")
    return b_plat if b_plat in SHOP_PLATFORMS else "shopee"


def parse_shop_target(raw: str, default_platform: str = "shopee_vn", default_market: str = "VN") -> tuple[str, str, str, str]:
    s = (raw or "").strip()
    low = s.lower()
    norm_def, def_mkt, _ = parse_marketplace_spec(default_platform, default_market)

    if "shopee." in low:
        mkt = detect_market_from_url(s) or def_mkt
        m = re.search(r"shopee\.[^/]+/(?:shop/)?([^/?#]+)", s, re.IGNORECASE)
        handle = m.group(1) if m else s
        return "shopee", mkt, handle, s

    if "tiktok.com" in low or "tiktokshop" in low:
        mkt = detect_market_from_url(s) or def_mkt
        m = re.search(r"tiktok\.com/@?([^/?#]+)", s, re.IGNORECASE)
        handle = m.group(1) if m else s
        plat = "tiktok_channel" if norm_def == "tiktok_channel" else "tiktok_shop"
        return plat, mkt, handle.lstrip("@"), s

    if any(dom in low for dom in ("facebook.com", "fb.com", "fb.watch")):
        parsed = urlparse(s if "://" in s else f"https://{s}")
        qs = parse_qs(parsed.query)
        if "id" in qs and qs["id"]:
            handle = qs["id"][0]
        else:
            segs = [seg for seg in (parsed.path or "").split("/") if seg and seg.lower() not in ("pages", "pg", "p", "profile.php")]
            handle = segs[-1] if segs else s
        url = s if "://" in s else f"https://{s}"
        return "facebook_fanpage", def_mkt, handle, url

    if "lazada." in low:
        mkt = detect_market_from_url(s) or def_mkt
        m = re.search(r"lazada\.[^/]+/shop/([^/?#]+)", s, re.IGNORECASE)
        handle = m.group(1) if m else s
        return "lazada", mkt, handle, s

    if "instagram.com" in low:
        m = re.search(r"instagram\.com/([^/?#]+)", s, re.IGNORECASE)
        handle = m.group(1) if m else s
        return "instagram", def_mkt, handle.lstrip("@"), s

    if s.startswith(("http://", "https://")):
        parsed = urlparse(s)
        return "website", def_mkt, parsed.netloc or s, s

    clean_handle = s.lstrip("@").strip()
    url = ""
    if clean_handle:
        if norm_def == "shopee":
            dom = shopee_domain_for_market(def_mkt)
            url = f"https://{dom}/{clean_handle}"
        elif norm_def in ("tiktok_shop", "tiktok_channel"):
            url = f"https://www.tiktok.com/@{clean_handle}"
        elif norm_def == "facebook_fanpage":
            url = f"https://www.facebook.com/{clean_handle}"
        elif norm_def == "instagram":
            url = f"https://www.instagram.com/{clean_handle}"
        elif norm_def == "lazada":
            url = f"https://www.lazada.vn/shop/{clean_handle}"
    return norm_def, def_mkt, clean_handle, url


def _parse_tags(raw_tags) -> list[str]:
    if isinstance(raw_tags, list):
        items = [str(x).strip() for x in raw_tags]
    elif isinstance(raw_tags, str):
        items = [x.strip() for x in re.split(r"[,;\n]+", raw_tags)]
    else:
        items = []
    seen = set()
    out = []
    for t in items:
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t[:60])
    return out[:20]


class ShopsService:
    def __init__(self, connect, secrets, products, apify=None, treg=None, jev=None):
        self.connect = connect
        self.secrets = secrets
        self.products = products
        self.apify = apify
        self.treg = treg
        self.jev = jev

    def create_or_update_shop(self, body: dict, shop_id: str | None = None) -> dict:
        with self.connect() as conn:
            existing = conn.execute("SELECT * FROM shops WHERE shop_id=?", (shop_id,)).fetchone() if shop_id else None

        role = str(body.get("role") or (existing["role"] if existing else "own_shop")).strip()
        if role not in ("own_shop", "competitor_shop"):
            raise ValueError("Vai trò shop phải là own_shop (Shop của tôi) hoặc competitor_shop (Shop đối thủ)")

        raw_plat_str = str(body.get("platform") or (f"{existing['platform']}_{existing['market'].lower()}" if existing and existing["platform"] in ("shopee", "tiktok_shop") else (existing["platform"] if existing else "shopee_vn")))
        plat_in, mkt_in, _ = parse_marketplace_spec(raw_plat_str, body.get("market") or (existing["market"] if existing else "VN"))
        raw_target = str(
            body.get("shop_url")
            if body.get("shop_url") is not None
            else (body.get("handle") if body.get("handle") is not None else (existing["shop_url"] or existing["handle"] if existing else ""))
        ).strip()

        if raw_target:
            plat, mkt, handle, url = parse_shop_target(raw_target, raw_plat_str, mkt_in)
            if body.get("platform") and normalize_shop_platform(str(body.get("platform"))) == "tiktok_channel" and "tiktok" in plat:
                plat = "tiktok_channel"
            # If user explicitly picked a country channel (e.g. tiktok_shop_ph) and URL didn't override domain, preserve mkt_in
            if not detect_market_from_url(raw_target):
                mkt = mkt_in
        else:
            plat = plat_in
            mkt = mkt_in
            handle = str(body.get("handle") or (existing["handle"] if existing else "")).strip().lstrip("@")
            url = str(existing["shop_url"] if existing else "")

        raw_name = body.get("shop_name") if body.get("shop_name") is not None else (existing["shop_name"] if existing else handle)
        shop_name = text(raw_name or handle, "shop_name", 140, required=True)
        if not handle:
            handle = re.sub(r"\s+", "", shop_name.lower())[:50]

        industry = str(body.get("industry") or (existing["industry"] if existing else "gia_dung")).strip()
        if industry not in INDUSTRIES:
            industry = "gia_dung"

        if "niche_tags" in body:
            tags = _parse_tags(body.get("niche_tags"))
        elif existing:
            tags = json.loads(existing["niche_tags_json"] or "[]")
        else:
            tags = []

        if "campaign_ids" in body and isinstance(body.get("campaign_ids"), list):
            campaign_ids = [str(c).strip() for c in body["campaign_ids"] if str(c).strip()][:25]
        elif existing and "campaign_ids_json" in existing.keys():
            campaign_ids = json.loads(existing["campaign_ids_json"] or "[]")
        else:
            campaign_ids = []

        status = str(body.get("status") or (existing["status"] if existing else "active")).strip()
        if status not in SHOP_STATUSES:
            status = "active"

        default_fee = SHOP_PLATFORMS.get(plat, {}).get("default_fee_pct", 12.0)
        if body.get("platform_fee_pct") is not None and str(body.get("platform_fee_pct")).strip() != "":
            fee_pct = max(0.0, min(60.0, float(body.get("platform_fee_pct"))))
        elif existing is not None:
            fee_pct = float(existing["platform_fee_pct"])
        else:
            fee_pct = float(default_fee)

        note = str(body.get("note") if body.get("note") is not None else (existing["note"] if existing else ""))[:1000]
        native_sid = safe_id_str(body.get("native_shop_id") or (existing["native_shop_id"] if existing else ""))
        ts = now()

        sid = shop_id or f"shop_{uuid.uuid4().hex[:10]}"
        with self.connect() as conn:
            if existing:
                conn.execute(
                    """
                    UPDATE shops
                    SET role=?, platform=?, market=?, native_shop_id=?, handle=?, shop_name=?, shop_url=?, industry=?,
                        niche_tags_json=?, campaign_ids_json=?, status=?, platform_fee_pct=?, note=?, updated_at=?
                    WHERE shop_id=?
                    """,
                    (
                        role,
                        plat,
                        mkt,
                        native_sid,
                        handle,
                        shop_name,
                        url,
                        industry,
                        json.dumps(tags, ensure_ascii=False),
                        json.dumps(campaign_ids, ensure_ascii=False),
                        status,
                        fee_pct,
                        note,
                        ts,
                        sid,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO shops
                    (shop_id, role, platform, market, native_shop_id, handle, shop_name, shop_url, industry,
                     niche_tags_json, campaign_ids_json, status, platform_fee_pct, stats_json, note, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', ?, ?, ?)
                    """,
                    (
                        sid,
                        role,
                        plat,
                        mkt,
                        native_sid,
                        handle,
                        shop_name,
                        url,
                        industry,
                        json.dumps(tags, ensure_ascii=False),
                        json.dumps(campaign_ids, ensure_ascii=False),
                        status,
                        fee_pct,
                        note,
                        ts,
                        ts,
                    ),
                )
        return self.get_shop(sid)

    def _assigned_counts_map(self, conn) -> dict[str, int]:
        prod_rows = conn.execute("SELECT id, record FROM products WHERE bucket != 'da_loai'").fetchall()
        assigned_counts: dict[str, int] = {}
        for pr in prod_rows:
            rec = json.loads(pr["record"] or "{}")
            asid = rec.get("assigned_shop_id") or ""
            if asid:
                assigned_counts[asid] = assigned_counts.get(asid, 0) + 1
        return assigned_counts

    def list_shops(self, role: str = "", platform: str = "", q: str = "") -> list[dict]:
        clauses = []
        params = []
        if role in ("own_shop", "competitor_shop"):
            clauses.append("role=?")
            params.append(role)
        if platform:
            p_low = platform.strip().lower()
            if any(p_low.endswith(f"_{m}") for m in ("vn", "ph", "sg", "my", "th")):
                b_plat, b_mkt, _ = parse_marketplace_spec(p_low)
                clauses.append("platform=? AND market=?")
                params.extend([b_plat, b_mkt])
            else:
                norm_p = normalize_shop_platform(platform)
                clauses.append("platform=?")
                params.append(norm_p)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        with self.connect() as conn:
            rows = conn.execute(f"SELECT * FROM shops {where} ORDER BY role ASC, updated_at DESC", tuple(params)).fetchall()
            assigned_counts = self._assigned_counts_map(conn)

        items = [self._format_shop(r, assigned_counts.get(r["shop_id"], 0)) for r in rows]
        if q.strip():
            ql = q.strip().lower()
            items = [
                s for s in items
                if ql in s["shop_name"].lower()
                or ql in s["handle"].lower()
                or ql in s["shop_url"].lower()
                or ql in s["industry_label"].lower()
                or ql in s["note"].lower()
                or any(ql in t.lower() for t in (s["niche_tags"] or []))
            ]
        return items

    def summary_counts(self) -> dict:
        with self.connect() as conn:
            rows = conn.execute("SELECT role, platform, COUNT(*) AS cnt FROM shops GROUP BY role, platform").fetchall()
        own_total = 0
        comp_total = 0
        own_by_platform: dict[str, int] = {k: 0 for k in SHOP_PLATFORMS}
        for r in rows:
            cnt = int(r["cnt"])
            if r["role"] == "own_shop":
                own_total += cnt
                own_by_platform[r["platform"]] = own_by_platform.get(r["platform"], 0) + cnt
            else:
                comp_total += cnt
        return {
            "own_count": own_total,
            "competitor_count": comp_total,
            "total_count": own_total + comp_total,
            "own_by_platform": own_by_platform,
        }

    def get_shop(self, shop_id: str) -> dict:
        with self.connect() as conn:
            r = conn.execute("SELECT * FROM shops WHERE shop_id=?", (shop_id,)).fetchone()
            assigned_counts = self._assigned_counts_map(conn) if r else {}
        if not r:
            raise ApiError("404 Not Found", "Không tìm thấy Shop này trong danh sách")
        return self._format_shop(r, assigned_counts.get(shop_id, 0))

    def delete_shop(self, shop_id: str) -> dict:
        with self.connect() as conn:
            conn.execute("DELETE FROM shops WHERE shop_id=?", (shop_id,))
        return {"deleted": True, "shop_id": shop_id}

    def auto_assign_shop_for_products(self, product_ids: list[int] | None = None) -> dict:
        """Automatically match Vault products to the best active 'Shop của tôi' based on Industry, Niche Tags & Platform."""
        own_shops = [s for s in self.list_shops(role="own_shop") if s["status"] != "paused"]
        if not own_shops:
            raise ApiError("400 Bad Request", "Bạn chưa có 'Shop của tôi' nào đang hoạt động — hãy thêm Shop TikTok, Shopee hoặc Fanpage trước!")

        if product_ids:
            prods = self.products.get_products_by_ids(product_ids)
        else:
            prods = [p for p in self.products.list_products(bucket="all", limit=200)["products"] if not p.get("assigned_shop_id")]

        matched = 0
        for p in prods:
            best_shop = None
            best_score = -1.0
            title_low = (p.get("title") or "").lower()
            p_ind = p.get("industry") or "khac"
            p_plat = p.get("platform") or ""

            for sh in own_shops:
                sc = 0.0
                if sh["industry"] == p_ind and p_ind != "khac":
                    sc += 5.0
                for tag in (sh.get("niche_tags") or []):
                    tl = tag.lower().strip()
                    if tl and tl in title_low:
                        sc += 3.5
                if sh["platform"] == p_plat or (sh["platform"] == "tiktok_channel" and p_plat == "tiktok_shop"):
                    sc += 2.0
                elif sh["platform"] == "facebook_fanpage":
                    sc += 1.0  # Fanpage Ads can sell cross-platform products
                if sh["status"] == "active":
                    sc += 0.5
                if sc > best_score:
                    best_score = sc
                    best_shop = sh

            if best_shop and best_score >= 1.0:
                self.products.update_product(p["id"], {"assigned_shop_id": best_shop["shop_id"]})
                matched += 1

        return {
            "matched_count": matched,
            "evaluated_count": len(prods),
            "summary": f"Đã tự động phân bổ {matched}/{len(prods)} sản phẩm vào Shop của tôi phù hợp nhất!",
        }

    def scan_and_evaluate_shop_products(
        self,
        shop_query: str,
        platform: str = "shopee",
        limit: int = 20,
        score_top_jev: int = 0,
        save_to_vault: bool = True,
        save_competitor_shop: bool = True,
    ) -> dict:
        """Find & evaluate products sold by a Shopee or TikTok Shop."""
        q = text(shop_query, "shop_query", 240, required=True)
        plat, mkt, handle, url = parse_shop_target(q, platform.lower().strip())
        ch_code = f"{plat}_{mkt.lower()}" if plat in ("shopee", "tiktok_shop") else plat
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
                    slug, items = self.apify.scrape_shopee_shop(apify_toks, url or handle, limit=lim, max_charge_usd=max_chg, market=mkt)
                    source_used = f"apify:{slug}"
                except Exception:
                    items = []
                if not items:
                    try:
                        slug, items = self.apify.search_shopee(apify_toks, handle, limit=lim, max_charge_usd=max_chg, market=mkt)
                        source_used = f"apify:{slug}"
                    except Exception:
                        items = []
        else:
            if apify_toks and self.apify:
                try:
                    slug, items = self.apify.search_tiktok_shop(apify_toks, handle, limit=lim, max_charge_usd=max_chg, market=mkt)
                    source_used = f"apify:{slug}"
                except Exception:
                    items = []
            if not items and treg_tok and self.treg:
                try:
                    ep, items, _ = self.treg.search_tiktok_shop(treg_tok, handle, limit=lim, market=mkt)
                    source_used = f"treg:{ep}"
                except Exception:
                    items = []

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
                "platform": ch_code,
                "market": mkt,
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
        plat = r["platform"]
        mkt = r["market"] or "VN"
        pmeta = SHOP_PLATFORMS.get(plat, {"label": plat.upper(), "icon": "🏬", "default_fee_pct": 12.0})
        ch_code = f"{plat}_{mkt.lower()}" if plat in ("shopee", "tiktok_shop") else plat
        plat_lbl = format_platform_market_label(plat, mkt) if plat in ("shopee", "tiktok_shop", "tiktok_channel", "lazada") else pmeta["label"]
        ind = r["industry"] if r["industry"] in INDUSTRIES else "gia_dung"
        camp_ids = json.loads(r["campaign_ids_json"] or "[]") if "campaign_ids_json" in r.keys() else []
        st = r["status"] if r["status"] in SHOP_STATUSES else "active"
        return {
            "shop_id": r["shop_id"],
            "role": r["role"],
            "role_label": "Shop của tôi" if r["role"] == "own_shop" else "Shop đối thủ theo dõi",
            "platform": plat,
            "channel_code": ch_code,
            "platform_label": plat_lbl,
            "platform_icon": pmeta["icon"],
            "market": mkt,
            "native_shop_id": r["native_shop_id"],
            "handle": r["handle"],
            "shop_name": r["shop_name"],
            "shop_url": r["shop_url"],
            "industry": ind,
            "industry_label": INDUSTRIES.get(ind, ind),
            "industry_icon": INDUSTRY_ICONS.get(ind, "📦"),
            "niche_tags": json.loads(r["niche_tags_json"] or "[]"),
            "campaign_ids": camp_ids,
            "status": st,
            "status_label": SHOP_STATUSES.get(st, st),
            "platform_fee_pct": r["platform_fee_pct"],
            "stats": json.loads(r["stats_json"] or "{}"),
            "assigned_products_count": assigned_products_count,
            "note": r["note"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }

    def dispatch(self, path: str, method: str, env, read_json):
        if path in ("/api/shops", "/api/my-shops") and method == "GET":
            qs = parse_qs(env.get("QUERY_STRING") or "")
            default_role = "own_shop" if path == "/api/my-shops" else ""
            role = (qs.get("role") or [default_role])[0]
            platform = (qs.get("platform") or [""])[0]
            q = (qs.get("q") or [""])[0]
            return "200 OK", {
                "shops": self.list_shops(role=role, platform=platform, q=q),
                "counts": self.summary_counts(),
                "platforms_catalog": SHOP_PLATFORMS,
                "statuses_catalog": SHOP_STATUSES,
                "scans": self.list_scans(15),
            }
        if path in ("/api/shops", "/api/my-shops") and method == "POST":
            body = json_object(read_json, env)
            if path == "/api/my-shops" and not body.get("role"):
                body["role"] = "own_shop"
            shop = self.create_or_update_shop(body)
            return "200 OK", {
                "shop": shop,
                "summary": f"Đã lưu {shop['role_label']}: {shop['shop_name']} ({shop['platform_label']})",
            }
        if path == "/api/shops/auto-match-products" and method == "POST":
            body = json_object(read_json, env)
            ids = [int(x) for x in (body.get("ids") or []) if str(x).isdigit()] or None
            return "200 OK", self.auto_assign_shop_for_products(product_ids=ids)
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
        if path.startswith(("/api/shops/", "/api/my-shops/")):
            parts = path.strip("/").split("/")
            if len(parts) == 3:
                sid = parts[2]
                if method == "GET":
                    return "200 OK", {"shop": self.get_shop(sid)}
                if method in ("PATCH", "PUT"):
                    return "200 OK", {
                        "shop": self.create_or_update_shop(json_object(read_json, env), shop_id=sid),
                        "summary": "Đã cập nhật thông tin Shop!",
                    }
                if method == "DELETE":
                    return "200 OK", self.delete_shop(sid)
        return None
