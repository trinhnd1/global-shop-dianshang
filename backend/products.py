"""Product Vault, Seller Classification, 13-Industry Taxonomy, Sales/GMV Analytics, Comparator & Exports."""
import csv
import io
import json
import re
from urllib.parse import parse_qs

from . import settings
from .responses import ApiError, Raw, canonicalize_commerce_url, json_object, now, safe_csv_cell, safe_id_str, text
from .seller_economics import evaluate_seller_economics

BUCKETS = {
    "cho_danh_gia": "Chờ đánh giá",
    "viral": "Đang bùng nổ (Viral)",
    "moi_noi": "Mới nổi · Ít cạnh tranh",
    "ben_vung": "Bán bền vững",
    "da_co_nguon_tq": "Đã có nguồn nhập TQ",
    "dang_nhap_ban": "Đang nhập / Test bán",
    "chua_cham": "Chưa chấm Jev",
    "da_loai": "Đã loại",
}

INDUSTRIES = {
    "gia_dung": "Gia dụng & Tiện ích",
    "nha_cua": "Nhà cửa & Đời sống",
    "lam_dep": "Làm đẹp & Mỹ phẩm",
    "suc_khoe": "Sức khoẻ & Massage",
    "thoi_trang": "Thời trang & Phụ kiện",
    "cong_nghe": "Phụ kiện Công nghệ",
    "me_be": "Mẹ & Bé",
    "lam_vuon": "Làm vườn & Hạt giống",
    "thu_cung": "Thú cưng",
    "do_an": "Đồ ăn & Thực phẩm",
    "the_thao": "Thể thao & Dã ngoại",
    "oto_xemay": "Ô tô & Xe máy",
    "khac": "Ngành khác",
}

INDUSTRY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("lam_vuon", ("hạt giống", "cây trồng", "phân bón", "làm vườn", "chậu cây", "tưới cây", "rau")),
    ("thu_cung", ("chó", "mèo", "thú cưng", "cát vệ sinh", "pate mèo", "chuồng")),
    ("me_be", ("cho bé", "trẻ em", "bỉm", "sữa", "đồ chơi cho bé", "mẹ và bé", "sơ sinh")),
    ("oto_xemay", ("ô tô", "xe hơi", "xe máy", "mũ bảo hiểm", "camera hành trình", "rửa xe")),
    ("cong_nghe", ("tai nghe", "sạc dự phòng", "cáp sạc", "ốp lưng", "bluetooth", "chuột không dây", "bàn phím", "điện thoại")),
    ("lam_dep", ("son", "kem dưỡng", "serum", "tẩy trang", "chống nắng", "mặt nạ", "trang điểm", "tóc")),
    ("suc_khoe", ("massage", "cổ vai gáy", "ngải cứu", "đai lưng", "nhiệt kế", "sức khỏe", "ngủ ngon")),
    ("thoi_trang", ("áo", "quần", "váy", "đầm", "túi xách", "giày", "dép", "kính mát", "vớ", "tất")),
    ("the_thao", ("ập gym", "yoga", "cầu lông", "chạy bộ", "dã ngoại", "cắm trại", "bình nước thể thao")),
    ("do_an", ("ăn vặt", "bánh", "kẹo", "trà", "cà phê", "hạt dinh dưỡng", "khô gà", "gia vị")),
    ("nha_cua", ("đèn ngủ", "trang trí", "rèm", "thảm", "tủ vải", "hộp đựng", "giường", "chăn ga")),
    ("gia_dung", ("nồi", "máy xay", "nhà bếp", "nhà tắm", "kệ", "cây lau nhà", "hút bụi", "móc treo", "ly giữ nhiệt", "dao")),
]


def infer_industry(title: str) -> str:
    low = (title or "").lower()
    for code, kws in INDUSTRY_KEYWORDS:
        if any(k in low for k in kws):
            return code
    return "khac"


def parse_ids_from_url(url: str) -> tuple[str, str, str]:
    """Return (platform, shop_id, product_id) from Shopee / TikTok / Lazada / 1688 / Taobao / PDD URLs."""
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
    def __init__(self, connect, secrets, jev_client=None, jobs=None, ledger=None):
        self.connect = connect
        self.secrets = secrets
        self.jev = jev_client
        self.jobs = jobs
        self.ledger = ledger

    def count_all(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM products").fetchone()[0])

    def upsert_product(self, item: dict, source: str = "manual") -> dict:
        url = canonicalize_commerce_url(str(item.get("url") or item.get("link_goc") or ""))
        u_plat, u_shop, u_pid = parse_ids_from_url(url)
        platform = str(item.get("platform") or item.get("kenh") or u_plat or "shopee").lower().strip()
        market = str(item.get("market") or "VN").upper().strip()
        native_pid = safe_id_str(item.get("native_product_id") or u_pid)
        native_sid = safe_id_str(item.get("native_shop_id") or u_shop)
        title = str(item.get("title") or item.get("ten_sp") or "").strip()
        if not title:
            raise ValueError("Tên sản phẩm không được để trống")

        price_vnd = max(0.0, float(item.get("price_vnd") or item.get("gia_vnd") or 0.0))
        cost_vnd = max(0.0, float(item.get("cost_vnd") or item.get("gia_von_vnd") or 0.0))
        sold_count = max(0, int(item.get("sold_count") or item.get("da_ban") or 0))
        sold_30d = max(0, int(item.get("sold_30d") or 0))
        gmv_vnd = max(0.0, float(item.get("gmv_vnd") or (price_vnd * sold_count)))
        rating = float(item.get("rating") or 0.0)
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
                rec.update({
                    "title": title or rec.get("title", ""),
                    "shop_name": item.get("shop_name") or rec.get("shop_name", ""),
                    "is_mall": bool(item.get("is_mall") or rec.get("is_mall", False)),
                    "image_url": item.get("image_url") or rec.get("image_url", ""),
                    "rating": rating if rating > 0 else rec.get("rating", 0.0),
                    "sold_30d": sold_30d if sold_30d > 0 else rec.get("sold_30d", 0),
                    "delta_sold_last": delta_sold,
                    "sources": sources,
                    "sightings": int(rec.get("sightings") or 1) + 1,
                    "economics": econ,
                })
                if item.get("assigned_shop_id") is not None:
                    rec["assigned_shop_id"] = str(item.get("assigned_shop_id") or "")
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
                if bucket not in BUCKETS:
                    bucket = "cho_danh_gia"
                rec = {
                    "title": title,
                    "shop_name": str(item.get("shop_name") or ""),
                    "is_mall": bool(item.get("is_mall")),
                    "image_url": str(item.get("image_url") or ""),
                    "rating": round(rating, 2),
                    "sold_30d": sold_30d,
                    "delta_sold_last": 0,
                    "sources": [source] if source else [],
                    "sightings": 1,
                    "assigned_shop_id": str(item.get("assigned_shop_id") or ""),
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
        if score_10 is None:
            return "da_co_nguon_tq" if cost_vnd > 0 else "chua_cham"
        if score_10 < 5.0:
            return "da_loai"
        if cost_vnd > 0 and score_10 >= 6.8:
            return "da_co_nguon_tq"
        if score_10 >= 7.5 and sold_count >= 300:
            return "viral"
        if score_10 >= 6.8 and sold_count < 300 and not is_mall:
            return "moi_noi"
        if score_10 >= 6.5 and sold_count >= 100:
            return "ben_vung"
        return "cho_danh_gia"

    def score_product_jev(self, product_id: int) -> dict:
        prod = self.get_product(product_id)
        if not prod:
            raise ApiError("404 Not Found", "Không tìm thấy sản phẩm")
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
            if new_bucket in ("cho_danh_gia", "chua_cham"):
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
            if status == "dang_nhap":
                bucket = "dang_nhap_ban"
            elif status == "bo_qua":
                bucket = "da_loai"
            industry = str(patch.get("industry") if patch.get("industry") is not None else row["industry"])
            if industry not in INDUSTRIES:
                industry = row["industry"]
            price_vnd = float(patch.get("price_vnd") if patch.get("price_vnd") is not None else row["price_vnd"])
            cost_vnd = float(patch.get("cost_vnd") if patch.get("cost_vnd") is not None else row["cost_vnd"])
            if "assigned_shop_id" in patch:
                rec["assigned_shop_id"] = str(patch.get("assigned_shop_id") or "")
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
        q: str = "",
        sort_by: str = "updated",
        limit: int = 200,
    ) -> dict:
        clauses = []
        params: list = []
        if bucket and bucket != "all":
            clauses.append("bucket = ?")
            params.append(bucket)
        elif bucket == "all":
            clauses.append("bucket != 'da_loai'")
        if industry:
            clauses.append("industry = ?")
            params.append(industry)
        if platform:
            clauses.append("platform = ?")
            params.append(platform)
        if q:
            clauses.append("(record LIKE ? OR native_product_id LIKE ?)")
            params.extend([f"%{q}%", f"%{q}%"])

        order_sql = {
            "gmv": "gmv_vnd DESC, sold_count DESC",
            "sold": "sold_count DESC, gmv_vnd DESC",
            "jev": "COALESCE(jev_score, -1) DESC, sold_count DESC",
            "price_asc": "price_vnd ASC",
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
            industry_counts = {
                r[0]: int(r[1])
                for r in conn.execute("SELECT industry, COUNT(*) FROM products WHERE bucket != 'da_loai' GROUP BY industry").fetchall()
            }

        items = [self._format_row(r) for r in rows]
        if shop_id:
            items = [x for x in items if x.get("assigned_shop_id") == shop_id]
        return {
            "products": items,
            "bucket_counts": bucket_counts,
            "industry_counts": industry_counts,
            "buckets": BUCKETS,
            "industries": INDUSTRIES,
        }

    def get_product(self, product_id: int) -> dict | None:
        with self.connect() as conn:
            r = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        return self._format_row(r) if r else None

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
            "ID", "Sàn", "Mã SP Gốc", "Tên Sản phẩm", "Ngành hàng", "Phân loại",
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
        return {
            "id": r["id"],
            "platform": r["platform"],
            "market": r["market"],
            "native_product_id": r["native_product_id"],
            "native_shop_id": r["native_shop_id"],
            "url": r["canonical_url"],
            "bucket": r["bucket"],
            "bucket_label": BUCKETS.get(r["bucket"], r["bucket"]),
            "status": r["status"],
            "industry": r["industry"],
            "industry_label": INDUSTRIES.get(r["industry"], r["industry"]),
            "title": rec.get("title", ""),
            "shop_name": rec.get("shop_name", ""),
            "is_mall": bool(rec.get("is_mall")),
            "image_url": rec.get("image_url", ""),
            "rating": rec.get("rating", 0.0),
            "price_vnd": r["price_vnd"],
            "cost_vnd": r["cost_vnd"],
            "sold_count": r["sold_count"],
            "sold_30d": rec.get("sold_30d", 0),
            "delta_sold_last": rec.get("delta_sold_last", 0),
            "gmv_vnd": r["gmv_vnd"],
            "jev_score": r["jev_score"],
            "jev_detail": rec.get("jev_detail"),
            "economics": rec.get("economics") or {},
            "sourcing_summary": rec.get("sourcing_summary"),
            "assigned_shop_id": rec.get("assigned_shop_id", ""),
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
            ids = [int(x) for x in (body.get("ids") or [])][:100]
            action = text(body.get("action"), "action", 40, required=True)
            updated = 0
            for pid in ids:
                if action == "delete":
                    self.delete_product(pid)
                elif action == "score_jev":
                    self.score_product_jev(pid)
                elif action == "set_bucket":
                    self.update_product(pid, {"bucket": body.get("bucket")})
                elif action == "set_industry":
                    self.update_product(pid, {"industry": body.get("industry")})
                elif action == "assign_shop":
                    self.update_product(pid, {"assigned_shop_id": body.get("shop_id")})
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
        return None
