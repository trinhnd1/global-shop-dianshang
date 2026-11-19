"""Product Vault, Seller Classification, 13-Industry Taxonomy, Enrichment, Comparator & Exports."""
import ast
import csv
import io
import json
import re
from urllib.parse import parse_qs

from . import settings
from .markets import SEA_MARKETS, format_platform_market_label, parse_marketplace_spec
from .responses import ApiError, Raw, canonicalize_commerce_url, json_object, now, safe_csv_cell, safe_id_str, text
from .seller_economics import evaluate_seller_economics

BUCKETS = {
    "cho_danh_gia": "Chờ đánh giá",
    "moi_noi": "Mới nổi · Ít cạnh tranh",
    "viral": "Đang viral / Bán chạy",
    "ben_vung": "Bán bền vững",
    "da_co_nguon_tq": "Đã có nguồn nhập TQ",
    "dang_nhap_ban": "Đang nhập / Test bán",
    "chua_cham": "Chưa chấm Jev",
    "da_loai": "Đã loại",
}

BUCKET_ICONS = {
    "all": "🗂",
    "cho_danh_gia": "📝",
    "moi_noi": "🆕",
    "viral": "🔥",
    "ben_vung": "🌱",
    "da_co_nguon_tq": "🇨🇳",
    "dang_nhap_ban": "🚀",
    "chua_cham": "⏳",
    "da_loai": "⛔",
}

STATUSES = {
    "quan_tam": "⭐ Quan tâm",
    "nhap_test": "🧪 Nhập test",
    "dang_ban": "✅ Đang bán",
    "bo_qua": "⛔ Bỏ qua",
}

INDUSTRIES = {
    "lam_vuon": "Làm vườn & Cây cảnh",
    "gia_dung": "Gia dụng & Tiện ích",
    "nha_cua": "Nhà cửa & Đời sống",
    "lam_dep": "Làm đẹp & Mỹ phẩm",
    "suc_khoe": "Sức khoẻ & Massage",
    "thoi_trang": "Thời trang & Phụ kiện",
    "cong_nghe": "Công nghệ & Điện tử",
    "me_be": "Mẹ & Bé",
    "thu_cung": "Thú cưng",
    "do_an": "Thực phẩm & Ăn vặt",
    "the_thao": "Thể thao & Dã ngoại",
    "oto_xemay": "Ô tô & Xe máy",
    "khac": "Ngành khác",
}

INDUSTRY_ICONS = {
    "lam_vuon": "🌱",
    "gia_dung": "🏠",
    "nha_cua": "🛋",
    "lam_dep": "💄",
    "suc_khoe": "💊",
    "thoi_trang": "👗",
    "cong_nghe": "📱",
    "me_be": "🍼",
    "thu_cung": "🐾",
    "do_an": "🍜",
    "the_thao": "🏃",
    "oto_xemay": "🚗",
    "khac": "📦",
}

INDUSTRY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("lam_vuon", ("hạt giống", "cây trồng", "phân bón", "làm vườn", "chậu cây", "tưới cây", "rau")),
    ("thu_cung", ("chó", "mèo", "thú cưng", "cát vệ sinh", "pate mèo", "chuồng")),
    ("me_be", ("cho bé", "trẻ em", "bỉm", "sữa", "đồ chơi cho bé", "mẹ và bé", "sơ sinh", "wonlex")),
    ("oto_xemay", ("ô tô", "xe hơi", "xe máy", "mũ bảo hiểm", "camera hành trình", "rửa xe")),
    ("cong_nghe", ("đồng hồ thông minh", "smartwatch", "tai nghe", "sạc dự phòng", "cáp sạc", "ốp lưng", "bluetooth", "chuột không dây", "bàn phím", "điện thoại")),
    ("lam_dep", ("son", "kem dưỡng", "serum", "tẩy trang", "chống nắng", "mặt nạ", "trang điểm", "tóc")),
    ("suc_khoe", ("massage", "cổ vai gáy", "ngải cứu", "đai lưng", "nhiệt kế", "sức khỏe", "ngủ ngon")),
    ("thoi_trang", ("áo", "quần", "váy", "đầm", "túi xách", "giày", "dép", "kính mát", "vớ", "tất")),
    ("the_thao", ("tập gym", "yoga", "cầu lông", "chạy bộ", "dã ngoại", "cắm trại", "bình nước thể thao")),
    ("do_an", ("ăn vặt", "bánh", "kẹo", "trà", "cà phê", "hạt dinh dưỡng", "khô gà", "gia vị")),
    ("nha_cua", ("đèn ngủ", "trang trí", "rèm", "thảm", "tủ vải", "hộp đựng", "giường", "chăn ga")),
    ("gia_dung", ("nồi", "máy xay", "nhà bếp", "nhà tắm", "kệ", "cây lau nhà", "hút bụi", "móc treo", "ly giữ nhiệt", "dao", "quạt")),
]


def infer_industry(title: str) -> str:
    low = (title or "").lower()
    for code, kws in INDUSTRY_KEYWORDS:
        if any(k in low for k in kws):
            return code
    return "khac"


def clean_image_url(raw_img) -> str:
    if not raw_img:
        return ""
    if isinstance(raw_img, dict):
        ulist = raw_img.get("url_list") or raw_img.get("thumb_url_list") or []
        if isinstance(ulist, list) and ulist and str(ulist[0]).startswith("http"):
            return str(ulist[0])
        return str(raw_img.get("url") or "") if str(raw_img.get("url") or "").startswith("http") else ""
    s = str(raw_img).strip()
    if s.startswith("http://") or s.startswith("https://"):
        return s
    if s.startswith("//"):
        return "https:" + s
    if s.startswith("{") and "url_list" in s:
        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, dict):
                ulist = parsed.get("url_list") or parsed.get("thumb_url_list") or []
                if isinstance(ulist, list) and ulist and str(ulist[0]).startswith("http"):
                    return str(ulist[0])
        except Exception:
            m = re.search(r"https?://[^\s'\",\]}]+", s)
            if m:
                return m.group(0)
    return ""


def parse_ids_from_url(url: str) -> tuple[str, str, str]:
    u = (url or "").strip()
    low = u.lower()
    m = re.search(r"shopee\.[^/]+/.*?-i\.(\d+)\.(\d+)", low)
    if m:
        return "shopee", m.group(1), m.group(2)
    m = re.search(r"shopee\.[^/]+/product/(\d+)/(\d+)", low)
    if m:
        return "shopee", m.group(1), m.group(2)
    m = re.search(r"(?:tiktok\.com|tiktokglobalshop\.com).*?(?:product|pdp)/(\d{10,25})", low)
    if m:
        return "tiktok_shop", "", m.group(1)
    m = re.search(r"lazada\.[^/]+/.*?-i(\d+)", low)
    if m:
        return "lazada", "", m.group(1)
    m = re.search(r"1688\.com/offer/(\d+)", low)
    if m:
        return "1688", "", m.group(1)
    m = re.search(r"(?:taobao|tmall)\.com/.*?(?:id=)(\d+)", low)
    if m:
        return "taobao", "", m.group(1)
    m = re.search(r"yangkeduo\.com/.*?goods_id=(\d+)", low)
    if m:
        return "pinduoduo", "", m.group(1)
    return "", "", ""


class ProductsService:
    def __init__(self, connect, secrets, jev_client=None, jobs=None, ledger=None, apify=None, treg=None):
        self.connect = connect
        self.secrets = secrets
        self.jev = jev_client
        self.jobs = jobs
        self.ledger = ledger
        self.apify = apify
        self.treg = treg
        self.campaigns_service = None
        self.repair_and_backfill_vault()

    def repair_and_backfill_vault(self):
        """Restore any auto-hidden products (status=='') to cho_danh_gia, clean dict-string image_urls & backfill unsaved scans."""
        ts = now()
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM products").fetchall()
            for r in rows:
                rec = json.loads(r["record"] or "{}")
                changed = False
                bucket = r["bucket"]
                # Products never manually rejected by user (status != 'bo_qua') must NOT be hidden in da_loai
                if bucket == "da_loai" and r["status"] != "bo_qua":
                    bucket = "cho_danh_gia"
                    changed = True
                raw_im = rec.get("image_url") or ""
                clean_im = clean_image_url(raw_im)
                if clean_im != raw_im:
                    rec["image_url"] = clean_im
                    changed = True
                new_ind = infer_industry(rec.get("title") or "")
                ind = r["industry"]
                if ind == "khac" and new_ind != "khac":
                    ind = new_ind
                    changed = True
                if changed:
                    conn.execute(
                        "UPDATE products SET bucket=?, industry=?, record=?, updated_at=? WHERE id=?",
                        (bucket, ind, json.dumps(rec, ensure_ascii=False), ts, r["id"]),
                    )

            kw_rows = conn.execute("SELECT platform, keyword, items_json FROM keyword_researches").fetchall() if not rows else []
            scan_rows = conn.execute("SELECT platform, shop_name, items_json FROM shop_product_scans").fetchall() if not rows else []

        for kr in kw_rows:
            for it in json.loads(kr["items_json"] or "[]"):
                if isinstance(it, dict) and it.get("title"):
                    try:
                        self.upsert_product(it, source=f"keyword:{kr['platform']}:{kr['keyword']}")
                    except Exception:
                        pass
        for sr in scan_rows:
            for it in json.loads(sr["items_json"] or "[]"):
                if isinstance(it, dict) and it.get("title"):
                    try:
                        self.upsert_product(it, source=f"shop_scan:{sr['platform']}:{sr['shop_name']}")
                    except Exception:
                        pass

    def count_all(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM products WHERE bucket != 'da_loai'").fetchone()[0])

    def upsert_product(self, item: dict, source: str = "manual") -> dict:
        url = canonicalize_commerce_url(str(item.get("url") or item.get("link_goc") or ""))
        u_plat, u_shop, u_pid = parse_ids_from_url(url)
        raw_plat = str(item.get("platform") or item.get("kenh") or u_plat or "shopee").strip()
        platform, market, _ = parse_marketplace_spec(raw_plat, item.get("market"), url=url)
        native_pid = safe_id_str(item.get("native_product_id") or u_pid)
        native_sid = safe_id_str(item.get("native_shop_id") or u_shop)
        title = str(item.get("title") or item.get("ten_sp") or "").strip()
        if not title:
            raise ValueError("Tên sản phẩm không được để trống")

        price_vnd = max(0.0, float(item.get("price_vnd") or item.get("gia_vnd") or 0.0))
        native_price = float(item.get("native_price") or (price_vnd if market == "VN" else 0.0))
        native_currency = str(item.get("native_currency") or SEA_MARKETS.get(market, SEA_MARKETS["VN"])["currency"])
        cost_vnd = max(0.0, float(item.get("cost_vnd") or item.get("gia_von_vnd") or 0.0))
        sold_count = max(0, int(item.get("sold_count") or item.get("da_ban") or 0))
        sold_30d = max(0, int(item.get("sold_30d") or 0))
        gmv_vnd = max(0.0, float(item.get("gmv_vnd") or (price_vnd * sold_count)))
        rating = float(item.get("rating") or 0.0)
        image_url = clean_image_url(item.get("image_url"))
        industry = str(item.get("industry") or "").strip()
        if industry not in INDUSTRIES or industry == "khac":
            industry = infer_industry(title)

        cfg = settings.read_settings(self.connect, self.secrets)
        econ = evaluate_seller_economics(
            {"platform": platform, "sell_price_vnd": price_vnd, "cost_vnd": cost_vnd},
            defaults=cfg["sourcing"],
        )

        ts = now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = None
            if native_pid:
                existing = conn.execute(
                    "SELECT * FROM products WHERE platform=? AND market=? AND native_product_id=?",
                    (platform, market, native_pid),
                ).fetchone()
            if not existing and url:
                existing = conn.execute(
                    "SELECT * FROM products WHERE market=? AND canonical_url=?",
                    (market, url),
                ).fetchone()

            if existing:
                pid = int(existing["id"])
                rec = json.loads(existing["record"] or "{}")
                eff_price = price_vnd if price_vnd > 0 else float(existing["price_vnd"] or 0.0)
                eff_cost = cost_vnd if cost_vnd > 0 else float(existing["cost_vnd"] or 0.0)
                eff_sold = max(sold_count, int(existing["sold_count"] or 0))
                eff_gmv = max(gmv_vnd, eff_price * eff_sold, float(existing["gmv_vnd"] or 0.0))
                prev_sold = int(existing["sold_count"] or 0)
                delta_sold = max(0, eff_sold - prev_sold)

                sources = list(rec.get("sources") or [])
                if source and source not in sources:
                    sources.append(source)

                econ = evaluate_seller_economics(
                    {"platform": platform, "sell_price_vnd": eff_price, "cost_vnd": eff_cost},
                    defaults=cfg["sourcing"],
                )
                prev_stock = int(rec.get("stock") or 0)
                cur_stock = int(item["stock"]) if item.get("stock") is not None and int(item.get("stock") or 0) > 0 else prev_stock
                stock_drop = max(0, prev_stock - cur_stock) if (prev_stock > 0 and cur_stock > 0 and cur_stock < prev_stock) else 0
                inferred_from_stock = int(rec.get("inferred_sold_from_stock") or 0) + stock_drop
                rec.update({
                    "title": title or rec.get("title", ""),
                    "shop_name": item.get("shop_name") or rec.get("shop_name", ""),
                    "native_price": native_price if native_price > 0 else rec.get("native_price", eff_price),
                    "native_currency": native_currency or rec.get("native_currency", "VND"),
                    "is_mall": bool(item.get("is_mall") or rec.get("is_mall", False)),
                    "is_preferred": bool(item.get("is_preferred") or rec.get("is_preferred", False)),
                    "shop_location": str(item.get("shop_location") or rec.get("shop_location") or "").strip(),
                    "is_overseas": bool(
                        item.get("is_overseas")
                        or rec.get("is_overseas", False)
                        or "nước ngoài" in str(item.get("shop_location") or rec.get("shop_location") or "").lower()
                    ),
                    "rating_count": max(int(item.get("rating_count") or 0), int(rec.get("rating_count") or 0)),
                    "stock": cur_stock,
                    "initial_stock": int(rec.get("initial_stock") or cur_stock or 0),
                    "inferred_sold_from_stock": inferred_from_stock,
                    "image_url": image_url or clean_image_url(rec.get("image_url", "")),
                    "rating": rating if rating > 0 else rec.get("rating", 0.0),
                    "sold_30d": sold_30d if sold_30d > 0 else rec.get("sold_30d", 0),
                    "delta_sold_last": max(delta_sold, stock_drop),
                    "sources": sources,
                    "sightings": int(rec.get("sightings") or 1) + 1,
                    "economics": econ,
                })
                if item.get("assigned_shop_id") is not None:
                    rec["assigned_shop_id"] = str(item.get("assigned_shop_id") or "")
                if item.get("assigned_campaign_id") is not None:
                    rec["assigned_campaign_id"] = str(item.get("assigned_campaign_id") or "")
                if item.get("note") is not None:
                    rec["note"] = str(item.get("note") or "")[:1000]

                bucket = existing["bucket"]
                if eff_cost > 0 and bucket in ("cho_danh_gia", "chua_cham"):
                    bucket = "da_co_nguon_tq"

                conn.execute(
                    """
                    UPDATE products
                    SET native_product_id=?, native_shop_id=?, canonical_url=?, industry=?,
                        bucket=?, sold_count=?, gmv_vnd=?, price_vnd=?, cost_vnd=?, record=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        native_pid or existing["native_product_id"],
                        native_sid or existing["native_shop_id"],
                        url or existing["canonical_url"],
                        industry if existing["industry"] == "khac" else existing["industry"],
                        bucket,
                        eff_sold,
                        eff_gmv,
                        eff_price,
                        eff_cost,
                        json.dumps(rec, ensure_ascii=False),
                        ts,
                        pid,
                    ),
                )
            else:
                bucket = str(item.get("bucket") or ("da_co_nguon_tq" if cost_vnd > 0 else "cho_danh_gia"))
                if bucket not in BUCKETS or bucket == "da_loai":
                    bucket = "cho_danh_gia"
                init_stk = max(0, int(item.get("stock") or 0))
                rec = {
                    "title": title,
                    "shop_name": str(item.get("shop_name") or ""),
                    "native_price": native_price,
                    "native_currency": native_currency,
                    "is_mall": bool(item.get("is_mall")),
                    "is_preferred": bool(item.get("is_preferred")),
                    "shop_location": str(item.get("shop_location") or "").strip(),
                    "is_overseas": bool(
                        item.get("is_overseas")
                        or "nước ngoài" in str(item.get("shop_location") or "").lower()
                    ),
                    "rating_count": int(item.get("rating_count") or 0),
                    "stock": init_stk,
                    "initial_stock": init_stk,
                    "inferred_sold_from_stock": 0,
                    "image_url": image_url,
                    "rating": round(rating, 2),
                    "sold_30d": sold_30d,
                    "delta_sold_last": 0,
                    "sources": [source] if source else [],
                    "sightings": 1,
                    "assigned_shop_id": str(item.get("assigned_shop_id") or ""),
                    "assigned_campaign_id": str(item.get("assigned_campaign_id") or ""),
                    "sourcing_summary": item.get("sourcing_summary") or None,
                    "jev_detail": None,
                    "note": str(item.get("note") or "")[:1000],
                    "economics": econ,
                }
                cur = conn.execute(
                    """
                    INSERT INTO products
                    (platform, market, native_product_id, native_shop_id, canonical_url, bucket, status, industry,
                     jev_score, sold_count, gmv_vnd, price_vnd, cost_vnd, record, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, '', ?, NULL, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        platform,
                        market,
                        native_pid,
                        native_sid,
                        url,
                        bucket,
                        industry,
                        sold_count,
                        gmv_vnd,
                        price_vnd,
                        cost_vnd,
                        json.dumps(rec, ensure_ascii=False),
                        ts,
                        ts,
                    ),
                )
                pid = int(cur.lastrowid)

            conn.execute(
                """
                INSERT INTO product_metric_history
                (product_id, source, price_vnd, sold_count, sold_30d, gmv_vnd, rating, stock, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pid,
                    source,
                    price_vnd,
                    sold_count,
                    sold_30d or None,
                    gmv_vnd,
                    rating or None,
                    int(item.get("stock") or 0) or None,
                    ts,
                ),
            )
        return self.get_product(pid)

    @staticmethod
    def auto_bucket_from_seller_metrics(score_10: float | None, sold_count: int, cost_vnd: float, is_mall: bool) -> str:
        """Suggest bucket WITHOUT ever hiding products into da_loai automatically."""
        if score_10 is None:
            return "da_co_nguon_tq" if cost_vnd > 0 else "cho_danh_gia"
        if cost_vnd > 0 and score_10 >= 6.8:
            return "da_co_nguon_tq"
        if score_10 >= 7.5 and sold_count >= 300:
            return "viral"
        if score_10 >= 6.8 and sold_count > 0 and sold_count < 300 and not is_mall:
            return "moi_noi"
        if score_10 >= 6.5 and sold_count >= 100:
            return "ben_vung"
        return "cho_danh_gia"

    def enrich_product(self, product_id: int) -> dict:
        """Fetch live price, sold_count, shop_name & clean image_url via Apify (#1) -> Treg (#2)."""
        prod = self.get_product(product_id)
        if not prod:
            raise ApiError("404 Not Found", "Không tìm thấy sản phẩm")
        cfg = settings.read_settings(self.connect, self.secrets)
        apify_toks = settings.apify_tokens(cfg)
        treg_tok = (cfg["providers"].get("treg_key") or "").strip()

        fetched = None
        plat = prod["platform"]
        npid = prod["native_product_id"]
        url = prod["url"]

        mkt_kw = {"market": prod["market"]} if prod.get("market") and prod["market"] != "VN" else {}
        if plat == "tiktok_shop":
            # STRICT PRIORITY #1: Apify Store API
            if apify_toks and self.apify and (url or npid):
                try:
                    fetched = self.apify.scrape_tiktok_shop_detail(apify_toks, url or npid, **mkt_kw)
                except Exception:
                    fetched = None
            # STRICT PRIORITY #2: Treg.to Backup ONLY if Apify returned empty or missing price
            if (not fetched or float(fetched.get("price_vnd") or 0) <= 0) and treg_tok and self.treg and npid:
                try:
                    t_det = self.treg.fetch_tiktok_shop_product_detail(treg_tok, npid, region=prod["market"])
                    if t_det:
                        fetched = {**(fetched or {}), **{k: v for k, v in t_det.items() if v}}
                except Exception:
                    pass
        elif plat == "shopee":
            # STRICT PRIORITY #1: Apify Store API
            if apify_toks and self.apify and url:
                try:
                    fetched = self.apify.scrape_shopee_product(apify_toks, url, **mkt_kw)
                except Exception:
                    fetched = None
            # STRICT PRIORITY #2: Treg.to Backup
            if not fetched and treg_tok and self.treg and url:
                try:
                    ext = self.treg.call(treg_tok, "treg.web.extract", {"url": url}, method="POST")
                    if ext.get("title"):
                        fetched = {"title": str(ext["title"])[:200]}
                except Exception:
                    pass

        if fetched and (fetched.get("price_vnd") or fetched.get("sold_count") or fetched.get("sold_30d") or fetched.get("stock") or fetched.get("image_url")):
            return self.upsert_product({**prod, **{k: v for k, v in fetched.items() if v}}, source="enrich_detail")
        return prod

    def enrich_batch(self, product_ids: list[int] | None = None, limit: int = 12) -> dict:
        if product_ids:
            targets = [int(x) for x in product_ids[:limit]]
        else:
            with self.connect() as conn:
                rows = conn.execute(
                    "SELECT id FROM products WHERE bucket != 'da_loai' AND (price_vnd <= 0 OR sold_count <= 0) ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            targets = [int(r["id"]) for r in rows]

        updated = 0
        for pid in targets:
            try:
                res = self.enrich_product(pid)
                if res and (res.get("price_vnd", 0) > 0 or res.get("sold_count", 0) > 0):
                    updated += 1
            except Exception:
                continue
        return {
            "checked_count": len(targets),
            "enriched_count": updated,
            "summary": f"Đã làm giàu dữ liệu Giá & Lượt bán cho {updated}/{len(targets)} sản phẩm",
        }

    def score_product_jev(self, product_id: int) -> dict:
        prod = self.get_product(product_id)
        if not prod:
            raise ApiError("404 Not Found", "Không tìm thấy sản phẩm")
        # Enrich first if price and sold_count are both 0 so Jev has real market metrics!
        if float(prod.get("price_vnd") or 0) <= 0 and int(prod.get("sold_count") or 0) <= 0:
            try:
                prod = self.enrich_product(product_id) or prod
            except Exception:
                pass
        if not self.jev:
            raise ApiError("503 Service Unavailable", "Chưa khởi tạo Jev Client")
        cfg = settings.read_settings(self.connect, self.secrets)
        tkey = (cfg["providers"].get("typesafe_key") or "").strip()
        if not tkey:
            raise ApiError("400 Bad Request", "Chưa cấu hình TypeSafe Jev API Key trong Cài đặt")

        res = self.jev.score_seller_product(
            tkey,
            prod,
            model=cfg["providers"].get("jev_model") or "jev-1.14.0",
            base_url=cfg["providers"].get("jev_base_url") or "https://api.typesafe.ai/v1/systemone",
        )
        ts = now()
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
            rec = json.loads(row["record"] or "{}")
            rec["jev_detail"] = res
            new_ind = res.get("industry") if res.get("industry") in INDUSTRIES else row["industry"]
            new_bucket = row["bucket"]
            if new_bucket in ("cho_danh_gia", "chua_cham") and row["status"] != "bo_qua":
                new_bucket = self.auto_bucket_from_seller_metrics(
                    res["overall_10"], int(row["sold_count"] or 0), float(row["cost_vnd"] or 0.0), bool(rec.get("is_mall"))
                )
            conn.execute(
                "UPDATE products SET jev_score=?, industry=?, bucket=?, record=?, updated_at=? WHERE id=?",
                (res["overall_10"], new_ind, new_bucket, json.dumps(rec, ensure_ascii=False), ts, product_id),
            )
        return self.get_product(product_id)

    def update_product(self, product_id: int, patch: dict) -> dict:
        cfg = settings.read_settings(self.connect, self.secrets)
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
            if not row:
                raise ApiError("404 Not Found", "Không tìm thấy sản phẩm")
            rec = json.loads(row["record"] or "{}")
            bucket = str(patch.get("bucket") if patch.get("bucket") is not None else row["bucket"])
            if bucket not in BUCKETS:
                raise ValueError("Nhóm phân loại không hợp lệ")
            status = str(patch.get("status") if patch.get("status") is not None else row["status"])
            if "status" in patch:
                if status in ("nhap_test", "dang_nhap"):
                    status = "nhap_test"
                    bucket = "dang_nhap_ban"
                elif status == "bo_qua":
                    bucket = "da_loai"
                elif status in ("quan_tam", "dang_ban") and bucket == "da_loai":
                    bucket = "cho_danh_gia"
            if "bucket" in patch and patch["bucket"] != "da_loai" and status == "bo_qua":
                status = ""

            industry = str(patch.get("industry") if patch.get("industry") is not None else row["industry"])
            if industry not in INDUSTRIES:
                industry = row["industry"]
            price_vnd = float(patch.get("price_vnd") if patch.get("price_vnd") is not None else row["price_vnd"])
            cost_vnd = float(patch.get("cost_vnd") if patch.get("cost_vnd") is not None else row["cost_vnd"])
            if "assigned_shop_id" in patch:
                rec["assigned_shop_id"] = str(patch.get("assigned_shop_id") or "")
            if "assigned_campaign_id" in patch:
                rec["assigned_campaign_id"] = str(patch.get("assigned_campaign_id") or "")
            if "note" in patch:
                rec["note"] = str(patch.get("note") or "")[:1000]
            if "title" in patch and str(patch["title"]).strip():
                rec["title"] = str(patch["title"]).strip()[:300]
            rec["economics"] = evaluate_seller_economics(
                {"platform": row["platform"], "sell_price_vnd": price_vnd, "cost_vnd": cost_vnd},
                defaults=cfg["sourcing"],
            )
            conn.execute(
                "UPDATE products SET bucket=?, status=?, industry=?, price_vnd=?, cost_vnd=?, record=?, updated_at=? WHERE id=?",
                (bucket, status, industry, price_vnd, cost_vnd, json.dumps(rec, ensure_ascii=False), now(), product_id),
            )

        if "assigned_campaign_id" in patch and self.campaigns_service is not None:
            cid = str(patch.get("assigned_campaign_id") or "")
            if cid:
                try:
                    self.campaigns_service.set_campaign_product_stage(cid, product_id, "chon_mau")
                except Exception:
                    pass
        return self.get_product(product_id)

    def delete_product(self, product_id: int) -> dict:
        with self.connect() as conn:
            conn.execute("DELETE FROM products WHERE id=?", (product_id,))
        return {"deleted": True, "id": product_id}

    def list_products(
        self,
        bucket: str = "",
        industry: str = "",
        platform: str = "",
        shop_id: str = "",
        campaign_id: str = "",
        status: str = "",
        q: str = "",
        sort_by: str = "updated",
        limit: int = 300,
    ) -> dict:
        clauses = []
        params: list = []
        if bucket == "chua_cham":
            clauses.append("jev_score IS NULL AND bucket != 'da_loai'")
        elif bucket and bucket != "all":
            clauses.append("bucket = ?")
            params.append(bucket)
        elif bucket == "all":
            clauses.append("bucket != 'da_loai'")
        if industry:
            clauses.append("industry = ?")
            params.append(industry)
        if platform:
            p_low = platform.strip().lower()
            has_mkt_suffix = any(p_low.endswith(f"_{m}") for m in ("vn", "ph", "sg", "my", "th"))
            if has_mkt_suffix:
                b_plat, b_mkt, _ = parse_marketplace_spec(p_low)
                clauses.append("platform = ? AND market = ?")
                params.extend([b_plat, b_mkt])
            else:
                clauses.append("platform = ?")
                params.append(p_low)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if q:
            clauses.append("(record LIKE ? OR native_product_id LIKE ?)")
            params.extend([f"%{q}%", f"%{q}%"])

        order_sql = {
            "gmv": "gmv_vnd DESC, sold_count DESC",
            "sold": "sold_count DESC, gmv_vnd DESC",
            "jev": "COALESCE(jev_score, -1) DESC, sold_count DESC",
            "price_asc": "price_vnd ASC",
            "price_desc": "price_vnd DESC",
            "updated": "updated_at DESC, id DESC",
        }.get(sort_by, "updated_at DESC, id DESC")

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(min(500, max(1, int(limit))))
        with self.connect() as conn:
            rows = conn.execute(f"SELECT * FROM products {where} ORDER BY {order_sql} LIMIT ?", tuple(params)).fetchall()
            bucket_counts = {
                r[0]: int(r[1])
                for r in conn.execute("SELECT bucket, COUNT(*) FROM products GROUP BY bucket").fetchall()
            }
            unscored_cnt = int(conn.execute("SELECT COUNT(*) FROM products WHERE jev_score IS NULL AND bucket != 'da_loai'").fetchone()[0])
            bucket_counts["chua_cham"] = unscored_cnt
            all_non_rejected = int(conn.execute("SELECT COUNT(*) FROM products WHERE bucket != 'da_loai'").fetchone()[0])
            bucket_counts["all"] = all_non_rejected
            industry_counts = {
                r[0]: int(r[1])
                for r in conn.execute("SELECT industry, COUNT(*) FROM products WHERE bucket != 'da_loai' GROUP BY industry").fetchall()
            }

        items = [self._format_row(r) for r in rows]
        if shop_id == "__unassigned__":
            items = [x for x in items if not x.get("assigned_shop_id")]
        elif shop_id:
            items = [x for x in items if x.get("assigned_shop_id") == shop_id]
        if campaign_id:
            items = [x for x in items if x.get("assigned_campaign_id") == campaign_id]
        return {
            "products": items,
            "bucket_counts": bucket_counts,
            "industry_counts": industry_counts,
            "buckets": BUCKETS,
            "bucket_icons": BUCKET_ICONS,
            "industries": INDUSTRIES,
            "industry_icons": INDUSTRY_ICONS,
            "statuses": STATUSES,
        }

    def get_product(self, product_id: int) -> dict | None:
        with self.connect() as conn:
            r = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        return self._format_row(r) if r else None

    def get_products_by_ids(self, ids: list[int]) -> list[dict]:
        clean = [int(x) for x in ids if str(x).isdigit()]
        if not clean:
            return []
        placeholders = ",".join("?" for _ in clean)
        with self.connect() as conn:
            rows = conn.execute(f"SELECT * FROM products WHERE id IN ({placeholders}) ORDER BY id DESC", tuple(clean)).fetchall()
        return [self._format_row(r) for r in rows]

    def get_dossier(self, product_id: int) -> dict:
        prod = self.get_product(product_id)
        if not prod:
            raise ApiError("404 Not Found", "Không tìm thấy sản phẩm")
        with self.connect() as conn:
            hist = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM product_metric_history WHERE product_id=? ORDER BY recorded_at DESC LIMIT 30",
                    (product_id,),
                ).fetchall()
            ]
            sourcing = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM china_sourcing_items WHERE linked_product_id=? ORDER BY updated_at DESC",
                    (product_id,),
                ).fetchall()
            ]
            watches = [
                dict(r)
                for r in conn.execute(
                    "SELECT watch_id, watch_type, platform, title, status, last_checked_at FROM watches WHERE linked_product_id=?",
                    (product_id,),
                ).fetchall()
            ]
        return {
            "product": prod,
            "metric_history": hist,
            "china_sourcing_quotes": sourcing,
            "watches": watches,
        }

    def compare_products(self, ids: list[int]) -> dict:
        if not (2 <= len(ids) <= 5):
            raise ValueError("Vui lòng chọn từ 2 đến 5 sản phẩm để so sánh")
        items = [self.get_product(int(i)) for i in ids]
        items = [x for x in items if x]
        markets = {x["market"] for x in items}
        return {
            "comparable": len(markets) == 1,
            "markets": sorted(markets),
            "items": items,
        }

    def export_csv(self) -> bytes:
        res = self.list_products(bucket="", limit=500)
        buf = io.StringIO()
        buf.write("\ufeff")
        w = csv.writer(buf, lineterminator="\r\n")
        w.writerow([
            "ID", "Sàn", "Mã SP Gốc", "Tên Sản phẩm", "Ngành hàng", "Phân loại", "Trạng thái",
            "Giá bán (VND)", "Giá vốn về tay (VND)", "Lãi ròng/đơn (VND)", "Biên ròng (%)",
            "Tổng đã bán", "Doanh số ước tính (VND)", "Điểm Jev (10)", "Shop gốc", "URL",
        ])
        for p in res["products"]:
            ec = p.get("economics") or {}
            w.writerow([
                p["id"],
                p["platform"],
                safe_csv_cell(p["native_product_id"]),
                safe_csv_cell(p["title"]),
                INDUSTRIES.get(p["industry"], p["industry"]),
                BUCKETS.get(p["bucket"], p["bucket"]),
                STATUSES.get(p["status"], p["status"]),
                p["price_vnd"],
                p["cost_vnd"],
                ec.get("net_profit_per_order_vnd", 0),
                ec.get("net_margin_pct", 0),
                p["sold_count"],
                p["gmv_vnd"],
                p["jev_score"] if p["jev_score"] is not None else "",
                safe_csv_cell(p.get("shop_name", "")),
                safe_csv_cell(p["url"]),
            ])
        return buf.getvalue().encode("utf-8")

    @staticmethod
    def _format_row(r) -> dict:
        rec = json.loads(r["record"] or "{}")
        ind = r["industry"] if r["industry"] in INDUSTRIES else "khac"
        mkt = r["market"] or "VN"
        plat = r["platform"]
        ch_code = f"{plat}_{mkt.lower()}" if plat in ("shopee", "tiktok_shop") else plat
        return {
            "id": r["id"],
            "platform": plat,
            "market": mkt,
            "channel_code": ch_code,
            "platform_market_label": format_platform_market_label(plat, mkt),
            "native_price": rec.get("native_price", r["price_vnd"]),
            "native_currency": rec.get("native_currency") or SEA_MARKETS.get(mkt, SEA_MARKETS["VN"])["currency"],
            "native_product_id": r["native_product_id"],
            "native_shop_id": r["native_shop_id"],
            "url": r["canonical_url"],
            "bucket": r["bucket"],
            "bucket_label": BUCKETS.get(r["bucket"], r["bucket"]),
            "bucket_icon": BUCKET_ICONS.get(r["bucket"], "📦"),
            "status": r["status"],
            "status_label": STATUSES.get(r["status"], ""),
            "industry": ind,
            "industry_label": INDUSTRIES.get(ind, ind),
            "industry_icon": INDUSTRY_ICONS.get(ind, "📦"),
            "title": rec.get("title", ""),
            "shop_name": rec.get("shop_name", ""),
            "shop_location": rec.get("shop_location", ""),
            "is_overseas": bool(rec.get("is_overseas") or "nước ngoài" in str(rec.get("shop_location") or "").lower()),
            "is_preferred": bool(rec.get("is_preferred")),
            "rating_count": int(rec.get("rating_count") or 0),
            "is_mall": bool(rec.get("is_mall")),
            "image_url": clean_image_url(rec.get("image_url", "")),
            "rating": rec.get("rating", 0.0),
            "price_vnd": r["price_vnd"],
            "cost_vnd": r["cost_vnd"],
            "sold_count": r["sold_count"],
            "sold_30d": rec.get("sold_30d", 0),
            "stock": int(rec.get("stock") or 0),
            "initial_stock": int(rec.get("initial_stock") or 0),
            "inferred_sold_from_stock": int(rec.get("inferred_sold_from_stock") or 0),
            "delta_sold_last": rec.get("delta_sold_last", 0),
            "gmv_vnd": r["gmv_vnd"],
            "jev_score": r["jev_score"],
            "jev_detail": rec.get("jev_detail"),
            "desk300": rec.get("desk300"),
            "economics": rec.get("economics") or {},
            "sourcing_summary": rec.get("sourcing_summary"),
            "assigned_shop_id": rec.get("assigned_shop_id", ""),
            "assigned_campaign_id": rec.get("assigned_campaign_id", ""),
            "sources": rec.get("sources") or [],
            "sightings": rec.get("sightings", 1),
            "note": rec.get("note", ""),
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }

    def dispatch(self, path: str, method: str, env, read_json):
        if path in ("/api/products", "/api/results") and method == "GET":
            qs = parse_qs(env.get("QUERY_STRING") or "")
            return "200 OK", self.list_products(
                bucket=(qs.get("bucket") or ["all"])[0],
                industry=(qs.get("industry") or [""])[0],
                platform=(qs.get("platform") or [""])[0],
                shop_id=(qs.get("shop_id") or [""])[0],
                campaign_id=(qs.get("campaign_id") or [""])[0],
                status=(qs.get("status") or [""])[0],
                q=(qs.get("q") or [""])[0],
                sort_by=(qs.get("sort") or ["updated"])[0],
            )
        if path in ("/api/products", "/api/results/import") and method == "POST":
            body = json_object(read_json, env, max_bytes=2 * 1024 * 1024)
            if isinstance(body.get("products"), list):
                saved = [self.upsert_product(it, source=str(body.get("source") or "batch_import")) for it in body["products"][:100]]
                return "200 OK", {"saved_count": len(saved), "products": saved, "summary": f"Đã lưu {len(saved)} sản phẩm vào Kho"}
            saved_one = self.upsert_product(body, source=str(body.get("source") or "manual"))
            return "200 OK", {"product": saved_one, "summary": f"Đã lưu SP: {saved_one['title'][:60]}"}
        if path == "/api/products/enrich-batch" and method == "POST":
            body = json_object(read_json, env)
            ids = [int(x) for x in (body.get("ids") or []) if str(x).isdigit()] or None
            return "200 OK", self.enrich_batch(product_ids=ids, limit=int(body.get("limit") or 12))
        if path == "/api/products/score-unscored" and method == "POST":
            with self.connect() as conn:
                rows = conn.execute("SELECT id FROM products WHERE jev_score IS NULL AND bucket != 'da_loai' ORDER BY id DESC LIMIT 10").fetchall()
            scored = 0
            for r in rows:
                try:
                    self.score_product_jev(int(r["id"]))
                    scored += 1
                except Exception:
                    break
            return "200 OK", {"scored_count": scored, "summary": f"Đã chấm điểm Jev cho {scored} sản phẩm chưa chấm"}
        if path == "/api/products/export.csv" and method == "GET":
            data = self.export_csv()
            return "200 OK", Raw(
                data,
                [
                    ("Content-Type", "text/csv; charset=utf-8"),
                    ("Content-Disposition", 'attachment; filename="kho-san-pham-dianshang.csv"'),
                    ("Content-Length", str(len(data))),
                ],
            )
        if path == "/api/products/compare" and method == "POST":
            body = json_object(read_json, env)
            return "200 OK", self.compare_products([int(x) for x in (body.get("ids") or [])])
        if path == "/api/products/economics-calc" and method == "POST":
            body = json_object(read_json, env)
            cfg = settings.read_settings(self.connect, self.secrets)
            return "200 OK", evaluate_seller_economics(body, defaults=cfg["sourcing"])
        if path == "/api/products/bulk" and method == "POST":
            body = json_object(read_json, env)
            ids = [int(x) for x in (body.get("ids") or [])][:150]
            action = text(body.get("action"), "action", 40, required=True)
            if action == "auto_assign_shop" and getattr(self, "shops_service", None) is not None:
                return "200 OK", self.shops_service.auto_assign_shop_for_products(product_ids=ids)
            if action == "process_300desk" and getattr(self, "desk_pipeline", None) is not None:
                run_out = self.desk_pipeline.process_single_or_batch_sync(product_ids=ids, mode="vault_process")
                return "200 OK", {"run": run_out, "updated": len(run_out["output_product_ids"]), "summary": run_out["summary"]}
            updated = 0
            for pid in ids:
                if action == "delete":
                    self.delete_product(pid)
                elif action == "score_jev":
                    self.score_product_jev(pid)
                elif action == "enrich":
                    self.enrich_product(pid)
                elif action == "set_bucket":
                    self.update_product(pid, {"bucket": body.get("bucket")})
                elif action == "set_status":
                    self.update_product(pid, {"status": body.get("status")})
                elif action == "set_industry":
                    self.update_product(pid, {"industry": body.get("industry")})
                elif action == "auto_industry":
                    p = self.get_product(pid)
                    if p:
                        self.update_product(pid, {"industry": infer_industry(p["title"])})
                elif action == "assign_shop":
                    self.update_product(pid, {"assigned_shop_id": body.get("shop_id")})
                elif action == "assign_campaign":
                    self.update_product(pid, {"assigned_campaign_id": body.get("campaign_id")})
                updated += 1
            return "200 OK", {"updated": updated, "action": action, "summary": f"Đã xử lý hàng loạt {updated} SP ({action})"}

        if path.startswith("/api/products/"):
            parts = path.strip("/").split("/")
            if len(parts) >= 3 and parts[2].isdigit():
                pid = int(parts[2])
                if len(parts) == 3 and method == "GET":
                    return "200 OK", self.get_dossier(pid)
                if len(parts) == 3 and method in ("PATCH", "POST"):
                    return "200 OK", self.update_product(pid, json_object(read_json, env))
                if len(parts) == 3 and method == "DELETE":
                    return "200 OK", self.delete_product(pid)
                if len(parts) == 4 and parts[3] == "score-jev" and method == "POST":
                    scored = self.score_product_jev(pid)
                    return "200 OK", {"product": scored, "summary": f"Jev chấm {scored['title'][:50]}: {scored['jev_score']}/10"}
                if len(parts) == 4 and parts[3] == "enrich" and method == "POST":
                    enriched = self.enrich_product(pid)
                    return "200 OK", {"product": enriched, "summary": f"Đã cập nhật SP #{pid}: Giá {enriched['price_vnd']:,.0f}đ · Đã bán {enriched['sold_count']}"}
                if len(parts) == 4 and parts[3] == "process-300desk" and method == "POST":
                    if getattr(self, "desk_pipeline", None) is None:
                        raise ApiError("503 Service Unavailable", "Chưa khởi tạo luồng 300+desk")
                    run_out = self.desk_pipeline.process_single_or_batch_sync(product_ids=[pid], mode="vault_process")
                    return "200 OK", {"run": run_out, "product": self.get_product(pid), "summary": run_out["summary"]}
        return None
