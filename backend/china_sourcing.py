"""China E-Commerce Sourcing (1688 · Taobao/Tmall · Pinduoduo · Douyin) + VN->CN Keyword Helper & Landed Cost Linker."""
import json
from urllib.parse import parse_qs
import uuid

from . import settings
from .responses import ApiError, json_object, now, safe_id_str, text
from .seller_economics import calculate_china_landed_cost, evaluate_seller_economics

VN_TO_CN_COMMERCE_DICT: list[tuple[str, str]] = [
    ("máy xay tỏi ớt", "迷你电动捣蒜器"),
    ("máy xay", "便携式搅拌机"),
    ("kệ nhà tắm", "浴室免打孔置物架"),
    ("kệ để đồ", "多层收纳架"),
    ("hộp đựng đồ", "折叠收纳箱"),
    ("đèn ngủ", "感应小夜灯"),
    ("quạt mini", "手持小风扇"),
    ("bình giữ nhiệt", "不锈钢保温杯"),
    ("ly giữ nhiệt", "车载保温杯"),
    ("máy massage cổ", "颈椎按摩仪"),
    ("máy massage", "筋膜枪按摩器"),
    ("cây lau nhà", "免手洗拖把"),
    ("máy hút bụi mini", "车载无线吸尘器"),
    ("túi xách nữ", "新款女包斜挎包"),
    ("ốp lưng", "新款手机壳"),
    ("tai nghe không dây", "蓝牙耳机"),
    ("sạc dự phòng", "大容量充电宝"),
    ("đồ chơi mèo", "猫咪玩具逗猫棒"),
    ("cát mèo", "豆腐猫砂"),
    ("hạt giống", "阳台蔬菜种子"),
    ("dụng cụ làm vườn", "园艺工具套装"),
    ("móc dán tường", "强力无痕挂钩"),
    ("túi hút chân không", "真空压缩袋"),
    ("khăn lau bếp", "厨房吸油抹布"),
]


def translate_vn_to_cn_keyword(query: str) -> str:
    q = (query or "").strip()
    if not q or q.startswith("http"):
        return q
    # Already contains CJK characters
    if any("\u4e00" <= ch <= "\u9fff" for ch in q):
        return q
    low = q.lower()
    for vn_phrase, cn_kw in VN_TO_CN_COMMERCE_DICT:
        if vn_phrase in low:
            return cn_kw
    return q


class ChinaSourcingService:
    def __init__(self, connect, secrets, products, apify=None, treg=None, jev=None):
        self.connect = connect
        self.secrets = secrets
        self.products = products
        self.apify = apify
        self.treg = treg
        self.jev = jev

    def search_and_save(
        self,
        query_or_url: str,
        platform: str = "1688",
        limit: int = 10,
        weight_kg: float | None = None,
        linked_product_id: int | None = None,
    ) -> dict:
        raw_q = text(query_or_url, "query", 400, required=True)
        plat = platform.lower().strip()
        if plat not in ("1688", "taobao", "pinduoduo", "douyin", "alibaba"):
            raise ValueError("Sàn nguồn hàng Trung Quốc phải là 1688, taobao, pinduoduo, douyin hoặc alibaba")

        effective_query = translate_vn_to_cn_keyword(raw_q)
        # Prefer pre-computed `300+desk` Chinese 1688 keyword on linked product, or ask `300+desk` when online!
        if linked_product_id and self.products:
            lp = self.products.get_product(int(linked_product_id))
            desk_cn = ((lp or {}).get("desk300") or {}).get("cn_1688_keyword")
            if desk_cn and effective_query == raw_q:
                effective_query = str(desk_cn).strip()
        if effective_query == raw_q and not raw_q.startswith("http") and getattr(self, "desk300", None) is not None:
            try:
                d_res = self.desk300.call_gateway_json(
                    "Bạn là trợ lý `300+desk` chuyên dịch tên sản phẩm Việt Nam sang từ khoá tiếng Trung tìm xưởng gốc trên 1688/Pinduoduo. Chỉ trả về JSON.",
                    f'Dịch cụm sản phẩm sau sang từ khoá tiếng Trung (中文) ngắn gọn dùng trên 1688: "{raw_q}"\nTrả về JSON: {{"cn_keyword": "<tiếng Trung>"}}',
                    task_type="cn_sourcing_kw",
                    timeout_sec=18,
                )
                cand_cn = str((d_res.get("parsed") or {}).get("cn_keyword") or "").strip()
                if cand_cn:
                    effective_query = cand_cn[:60]
            except Exception:
                pass
        cfg = settings.read_settings(self.connect, self.secrets)
        src_cfg = cfg["sourcing"]
        eff_weight = float(weight_kg if weight_kg is not None else src_cfg.get("default_weight_kg", 0.4))
        cny_rate = float(src_cfg.get("cny_to_vnd_rate", 3650.0))

        apify_toks = settings.apify_tokens(cfg)
        treg_tok = (cfg["providers"].get("treg_key") or "").strip()
        max_chg = float(cfg["providers"].get("apify_max_charge_usd") or 0.06)

        rows: list[dict] = []
        source_used = "none"

        if apify_toks and self.apify and plat in ("1688", "taobao", "pinduoduo", "alibaba"):
            try:
                slug, rows = self.apify.search_china_sourcing(
                    apify_toks, plat, effective_query, limit=limit, max_charge_usd=max_chg
                )
                source_used = f"apify:{slug}"
            except Exception:
                rows = []

        if not rows and treg_tok and self.treg:
            try:
                ep, rows, _ = self.treg.search_china_sourcing(treg_tok, plat, effective_query, limit=limit)
                source_used = f"treg:{ep}"
            except Exception:
                rows = []

        saved_items = []
        for r in rows[:limit]:
            saved_items.append(
                self.save_sourcing_item(
                    {
                        **r,
                        "platform": plat,
                        "title_vi": raw_q if raw_q != effective_query else "",
                        "weight_kg": eff_weight,
                        "linked_product_id": linked_product_id,
                    }
                )
            )

        return {
            "platform": plat,
            "input_query": raw_q,
            "translated_cn_query": effective_query,
            "source_used": source_used,
            "cny_to_vnd_rate": cny_rate,
            "items": saved_items,
            "summary": f"Nguồn hàng {plat.upper()} ('{effective_query}'): thu được {len(saved_items)} mẫu báo giá",
        }

    def save_sourcing_item(self, body: dict) -> dict:
        plat = str(body.get("platform") or "1688").lower().strip()
        if plat not in ("1688", "taobao", "pinduoduo", "douyin", "alibaba"):
            plat = "1688"
        title = text(body.get("title"), "title", 300, required=True)
        price_cny = max(0.0, float(body.get("price_cny") or 0.0))
        moq = max(1, int(body.get("moq") or 1))
        cfg = settings.read_settings(self.connect, self.secrets)
        src_cfg = cfg["sourcing"]
        weight_kg = max(0.01, float(body.get("weight_kg") or src_cfg.get("default_weight_kg", 0.4)))
        cny_rate = float(body.get("cny_rate") or src_cfg.get("cny_to_vnd_rate", 3650.0))

        lc = calculate_china_landed_cost(
            price_cny=price_cny,
            cny_rate=cny_rate,
            domestic_cn_ship_cny=body.get("domestic_cn_ship_cny") or 0,
            weight_kg=weight_kg,
            cn_vn_ship_per_kg_vnd=src_cfg.get("cn_shipping_per_kg_vnd", 28000),
            buying_agent_fee_pct=src_cfg.get("buying_agent_fee_pct", 2.5),
        )
        landed_vnd = lc["landed_cost_vnd"]
        linked_pid = int(body["linked_product_id"]) if body.get("linked_product_id") else None

        sid = str(body.get("sourcing_id") or f"cns_{uuid.uuid4().hex[:10]}")
        ts = now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO china_sourcing_items
                (sourcing_id, platform, native_item_id, title, title_vi, item_url, image_url, price_cny,
                 wholesale_tiers_json, moq, weight_kg, cny_rate, landed_cost_vnd, supplier_name,
                 supplier_Badges_json, sales_volume, linked_product_id, jev_supplier_score, raw_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, ?, ?, ?, ?, '[]', ?, ?, NULL, ?, ?, ?)
                ON CONFLICT(sourcing_id) DO UPDATE SET
                    price_cny=excluded.price_cny, weight_kg=excluded.weight_kg, landed_cost_vnd=excluded.landed_cost_vnd,
                    linked_product_id=excluded.linked_product_id, updated_at=excluded.updated_at
                """,
                (
                    sid,
                    plat,
                    safe_id_str(body.get("native_item_id") or ""),
                    title,
                    str(body.get("title_vi") or "")[:200],
                    str(body.get("item_url") or ""),
                    str(body.get("image_url") or ""),
                    price_cny,
                    moq,
                    weight_kg,
                    cny_rate,
                    landed_vnd,
                    str(body.get("supplier_name") or ""),
                    str(body.get("sales_volume") or ""),
                    linked_pid,
                    json.dumps(lc, ensure_ascii=False),
                    ts,
                    ts,
                ),
            )

        if linked_pid and landed_vnd > 0:
            try:
                self.products.update_product(linked_pid, {"cost_vnd": landed_vnd, "bucket": "da_co_nguon_tq"})
            except Exception:
                pass
        return self.get_item(sid)

    def link_to_product(self, sourcing_id: str, product_id: int | None = None, create_new_in_vault: bool = False, target_sell_price_vnd: float = 0.0) -> dict:
        item = self.get_item(sourcing_id)
        if not item:
            raise ApiError("404 Not Found", "Không tìm thấy mẫu nguồn hàng Trung Quốc này")

        if create_new_in_vault or not product_id:
            sell_p = target_sell_price_vnd if target_sell_price_vnd > 0 else round(item["landed_cost_vnd"] * 2.5, -3)
            prod = self.products.upsert_product(
                {
                    "platform": item["platform"],
                    "market": "VN",
                    "native_product_id": item["native_item_id"],
                    "title": item["title_vi"] or item["title"],
                    "price_vnd": sell_p,
                    "cost_vnd": item["landed_cost_vnd"],
                    "url": item["item_url"],
                    "image_url": item["image_url"],
                    "shop_name": item["supplier_name"] or item["platform"].upper(),
                    "bucket": "da_co_nguon_tq",
                },
                source=f"china_sourcing:{item['platform']}",
            )
            pid = prod["id"]
        else:
            pid = int(product_id)
            prod = self.products.update_product(pid, {"cost_vnd": item["landed_cost_vnd"], "bucket": "da_co_nguon_tq"})

        with self.connect() as conn:
            conn.execute("UPDATE china_sourcing_items SET linked_product_id=?, updated_at=? WHERE sourcing_id=?", (pid, now(), sourcing_id))
        return {
            "sourcing_item": self.get_item(sourcing_id),
            "product": prod,
            "summary": f"Đã ghép nguồn {item['platform'].upper()} (Giá vốn {item['landed_cost_vnd']:,.0f}đ) vào SP #{pid}",
        }

    def list_items(self, platform: str = "", linked_product_id: int | None = None, limit: int = 60) -> list[dict]:
        clauses = []
        params: list = []
        if platform:
            clauses.append("platform = ?")
            params.append(platform)
        if linked_product_id is not None:
            clauses.append("linked_product_id = ?")
            params.append(int(linked_product_id))
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(min(200, max(1, int(limit))))
        with self.connect() as conn:
            rows = conn.execute(f"SELECT * FROM china_sourcing_items {where} ORDER BY updated_at DESC LIMIT ?", tuple(params)).fetchall()
        return [self._format_row(r) for r in rows]

    def get_item(self, sourcing_id: str) -> dict | None:
        with self.connect() as conn:
            r = conn.execute("SELECT * FROM china_sourcing_items WHERE sourcing_id=?", (sourcing_id,)).fetchone()
        return self._format_row(r) if r else None

    @staticmethod
    def _format_row(r) -> dict:
        return {
            "sourcing_id": r["sourcing_id"],
            "platform": r["platform"],
            "native_item_id": r["native_item_id"],
            "title": r["title"],
            "title_vi": r["title_vi"],
            "item_url": r["item_url"],
            "image_url": r["image_url"],
            "price_cny": r["price_cny"],
            "moq": r["moq"],
            "weight_kg": r["weight_kg"],
            "cny_rate": r["cny_rate"],
            "landed_cost_vnd": r["landed_cost_vnd"],
            "supplier_name": r["supplier_name"],
            "sales_volume": r["sales_volume"],
            "linked_product_id": r["linked_product_id"],
            "breakdown": json.loads(r["raw_json"] or "{}"),
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }

    def dispatch(self, path: str, method: str, env, read_json):
        if path == "/api/sourcing" and method == "GET":
            qs = parse_qs(env.get("QUERY_STRING") or "")
            plat = (qs.get("platform") or [""])[0]
            lpid = int(qs["product_id"][0]) if qs.get("product_id") and qs["product_id"][0].isdigit() else None
            return "200 OK", {"items": self.list_items(platform=plat, linked_product_id=lpid), "vn_cn_hints": dict(VN_TO_CN_COMMERCE_DICT[:15])}
        if path == "/api/sourcing/search" and method == "POST":
            body = json_object(read_json, env)
            return "200 OK", self.search_and_save(
                query_or_url=text(body.get("query"), "query", 400, required=True),
                platform=str(body.get("platform") or "1688"),
                limit=int(body.get("limit") or 10),
                weight_kg=float(body["weight_kg"]) if body.get("weight_kg") else None,
                linked_product_id=int(body["linked_product_id"]) if body.get("linked_product_id") else None,
            )
        if path == "/api/sourcing/manual" and method == "POST":
            body = json_object(read_json, env)
            saved = self.save_sourcing_item(body)
            return "200 OK", {"item": saved, "summary": f"Đã lưu báo giá {saved['platform'].upper()}: ¥{saved['price_cny']} -> {saved['landed_cost_vnd']:,.0f}đ"}
        if path == "/api/sourcing/calc" and method == "POST":
            body = json_object(read_json, env)
            cfg = settings.read_settings(self.connect, self.secrets)
            lc = calculate_china_landed_cost(
                price_cny=body.get("price_cny") or 0,
                cny_rate=body.get("cny_to_vnd_rate") or cfg["sourcing"]["cny_to_vnd_rate"],
                domestic_cn_ship_cny=body.get("domestic_cn_ship_cny") or 0,
                weight_kg=body.get("weight_kg") or cfg["sourcing"]["default_weight_kg"],
                cn_vn_ship_per_kg_vnd=body.get("cn_shipping_per_kg_vnd") or cfg["sourcing"]["cn_shipping_per_kg_vnd"],
                buying_agent_fee_pct=body.get("buying_agent_fee_pct") or cfg["sourcing"]["buying_agent_fee_pct"],
            )
            econ = evaluate_seller_economics(
                {"platform": body.get("sell_platform") or "shopee", "sell_price_vnd": body.get("sell_price_vnd") or lc["recommended_retail_ideal_vnd"], "cost_vnd": lc["landed_cost_vnd"]},
                defaults=cfg["sourcing"],
            )
            return "200 OK", {"landed": lc, "seller_economics": econ}
        if path.startswith("/api/sourcing/") and path.endswith("/link") and method == "POST":
            sid = path.strip("/").split("/")[2]
            body = json_object(read_json, env)
            return "200 OK", self.link_to_product(
                sid,
                product_id=int(body["product_id"]) if body.get("product_id") else None,
                create_new_in_vault=bool(body.get("create_new_in_vault", False)),
                target_sell_price_vnd=float(body.get("target_sell_price_vnd") or 0.0),
            )
        return None
