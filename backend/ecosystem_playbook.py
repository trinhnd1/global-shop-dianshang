"""Brand & Accessory Ecosystem Research Playbooks (`🎯 Luồng Hệ sinh thái & Phụ kiện SP`).

Supports two complementary real-world Seller Playbooks (and their full combination) in one unified hub:
1. Accessory & Cross-Border CN Expansion Playbook (e.g. `Phụ kiện Xteink X4`):
   - Collects all related products & shops on `Shopee VN` + `TikTokShop VN` (Apify #1 -> Treg #2)
   - Enriches `stock` inventory & ranks by Recent Sales + Inventory-Drop Signal + `TypeSafe Jev AI` score
   - Adds winning/active products to `⭐ Danh sách Theo dõi Đặc biệt` (`is_special=1`) & shops to `🏪 Danh sách Theo dõi Shop`
   - Uses `300+desk` (OPi SOCKS5) to derive Chinese accessory keywords -> searches `Pinduoduo`, `Taobao` (& `1688`) for complementary (`🧩 Bổ sung`), multi-variant (`🎨 Đa dạng mẫu`), and replacement (`🔄 Thay thế`) options
   - Saves everything into a named Tracking Category (`Danh mục Theo dõi`, e.g. `Phụ kiện Xteink X4`).

2. Brand Index + Daily New-Product Crawl + Affiliate Global Selling Creators + Kalodata VN Playbook (e.g. `Phụ kiện Goojodoq`):
   - Captures Baseline Index #1 across `TikTokShop VN` + `Shopee VN`
   - Enables automated Daily Crawl Schedule (`24h`) comparing new runs against Baseline/Previous Index to surface newly listed products & stock/sales surges
   - Queries `TikTok Affiliate Global Selling` + `Kalodata VN` via the shared `peng_dedicated` Chrome profile (`jreed767@cnebw.eu.cc`) to return top-converting Creators & Winning Videos (GPM, Video GMV, Orders, Views).
"""
from datetime import datetime, timedelta, timezone
import json
import re
import threading
import time
import uuid

from . import settings
from .markets import format_platform_market_label, parse_marketplace_spec
from .responses import ApiError, json_object, now, safe_id_str, text

ADDON_CN_KEYWORDS = (
    "保护套", "保护壳", "壳", "皮套", "膜", "类纸膜", "钢化膜", "收纳", "包", "挂绳", "支架",
    "翻页器", "笔尖", "笔套", "键盘", "充电", "转接", "贴纸", "阅读灯", "夹", "配件",
    "case", "cover", "screen", "film", "pouch", "strap", "stand", "holder", "nib", "keyboard",
)
VARIANT_CN_KEYWORDS = (
    "磁吸", "透明", "新款", "多色", "卡通", "硅胶", "亚克力", "真皮", "轻薄", "防摔", "旋转",
    "magnetic", "clear", "leather", "silicone", "colorful",
)

CURATED_ACCESSORY_CN_MAP: dict[str, list[tuple[str, str]]] = {
    "xteink": [
        ("阅星瞳 X4 磁吸保护套 皮套", "Bao da / Ốp lưng từ tính Xteink X4 (阅星瞳 X4)"),
        ("阅星瞳 X4 类纸膜 钢化膜", "Miếng dán màn hình nhám Paperlike / Cường lực Xteink X4"),
        ("迷你墨水屏电子书 蓝牙翻页器 收纳包", "Remote lật trang Bluetooth & Túi chống sốc máy đọc sách mini 4.3 inch"),
        ("Xteink X4 保护壳 挂绳 支架", "Ốp trong suốt + Dây đeo cổ tay + Giá đỡ đọc sách Xteink X4"),
    ],
    "goojodoq": [
        ("Goojodoq 电容笔替换笔尖 收纳盒", "Ngòi bút cảm ứng thay thế & Hộp đựng bút Goojodoq"),
        ("iPad 磁吸键盘保护套 妙控键盘 平替", "Bàn phím từ tính & Bao da iPad mẫu thay thế / nâng cấp Goojodoq"),
        ("高速手持风扇 冰敷小风扇 新款配件", "Quạt cầm tay sò lạnh & Phụ kiện dây đeo / túi đựng Goojodoq"),
    ],
}


def _future_iso(hours: float) -> str:
    dt = datetime.now(timezone.utc) + timedelta(hours=max(1.0, float(hours)))
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def classify_cn_accessory_relation(title: str, query_hint: str = "") -> dict:
    hay = (title or query_hint).lower()
    is_addon = any(w.lower() in hay for w in ADDON_CN_KEYWORDS)
    is_variant = any(w.lower() in hay for w in VARIANT_CN_KEYWORDS)
    if is_addon and is_variant:
        return {"role": "variant_addon", "badge": "🎨 Đa dạng mẫu Phụ kiện", "color": "gold"}
    if is_addon:
        return {"role": "complementary_addon", "badge": "🧩 Phụ kiện bổ sung", "color": "green"}
    if is_variant:
        return {"role": "variant_choice", "badge": "🎨 Đa dạng phân loại", "color": "blue"}
    return {"role": "alternative_product", "badge": "🔄 Sản phẩm thay thế / Đối chiếu", "color": "sky"}


BRAND_ALIAS_MAP: dict[str, tuple[str, ...]] = {
    "xteink": ("xteink", "xt eink", "xt-eink", "阅星瞳"),
    "goojodoq": ("goojodoq",),
}
GENERIC_STOP_TOKENS = {
    "phu", "phụ", "kien", "kiện", "cho", "cua", "của", "va", "và", "chinh", "chính", "hang", "hãng",
    "gia", "giá", "re", "rẻ", "moi", "mới", "pro", "mini", "max", "plus", "shop", "vn",
}


def is_item_relevant_to_ecosystem(title: str, shop_name: str, seed_kw: str, extra_kws: list[str] | None = None) -> bool:
    hay = f"{title or ''} {shop_name or ''}".lower()
    if not hay.strip():
        return False
    seed_l = (seed_kw or "").strip().lower()
    if not seed_l:
        return True
    if seed_l in hay or seed_l.replace(" ", "") in hay.replace(" ", ""):
        return True
    for k_root, aliases in BRAND_ALIAS_MAP.items():
        if k_root in seed_l:
            if any(a in hay for a in aliases):
                return True
            # Specific 4.3" mini e-reader case / film match for Xteink X4
            if k_root == "xteink" and ("máy đọc sách" in hay or "đọc sách điện tử" in hay or "e-ink" in hay or "ereader" in hay) and ("4.3" in hay or "x4" in hay or "x3" in hay):
                return True
    tokens = [
        t for t in re.split(r"[^0-9a-zA-ZÀ-ỹ\u4e00-\u9fff]+", " ".join([seed_l] + [str(x).lower() for x in (extra_kws or [])]))
        if len(t) >= 3 and t not in GENERIC_STOP_TOKENS
    ]
    if tokens:
        return any(tok in hay for tok in tokens)
    return True


def compute_product_priority_rank(p: dict, kalo_map: dict[str, dict] | None = None) -> dict:
    npid = safe_id_str(p.get("native_product_id") or "")
    kalo_hit = (kalo_map or {}).get(npid) or {}
    recent_7d = int(kalo_hit.get("units_sold_recent") or 0)
    sold_30d = int(p.get("sold_30d") or 0)
    delta_last = int(p.get("delta_sold_last") or 0)
    stock_inferred = int(p.get("inferred_sold_from_stock") or 0)
    total_sold = int(p.get("sold_count") or 0)
    stock = int(p.get("stock") or 0)
    jev = float(p.get("jev_score") or 0.0)

    recent_signal = max(recent_7d, sold_30d, delta_last, stock_inferred)
    priority_pts = (
        (min(40.0, recent_signal * 1.2) if recent_signal > 0 else 0.0)
        + (min(25.0, total_sold * 0.15) if total_sold > 0 else 0.0)
        + (8.0 if stock > 0 else 0.0)
        + (jev * 3.0)
    )
    qualifies_special_watch = bool(recent_signal > 0 or total_sold > 0 or stock > 0 or jev >= 6.8)
    reason_parts = []
    if recent_7d > 0:
        reason_parts.append(f"Bán 7 ngày gần nhất: {recent_7d} đơn (Kalodata)")
    elif sold_30d > 0:
        reason_parts.append(f"Bán 30 ngày gần đây: {sold_30d}")
    if stock_inferred > 0:
        reason_parts.append(f"Suy từ giảm tồn kho: +{stock_inferred} đơn")
    if total_sold > 0:
        reason_parts.append(f"Tổng đã bán: {total_sold}")
    if stock > 0:
        reason_parts.append(f"Đang theo dõi tồn kho: {stock} cái")
    if jev > 0:
        reason_parts.append(f"Jev {jev}/10")

    reason_txt = " · ".join(reason_parts) if reason_parts else "Mốc theo dõi mới (chờ biến động tồn kho / lượt bán)"
    return {
        "priority_points": round(priority_pts, 2),
        "recent_sold_signal": recent_signal,
        "kalodata_7d_sold": recent_7d,
        "kalodata_7d_gmv_vnd": float(kalo_hit.get("gmv_recent_vnd") or 0.0),
        "qualifies_special_watch": qualifies_special_watch,
        "priority_reason": reason_txt,
        "reason": reason_txt,
    }


class EcosystemPlaybookService:
    def __init__(
        self,
        connect,
        secrets,
        products,
        shops,
        watches,
        keywords,
        china_sourcing,
        kalodata_bridge=None,
        desk300=None,
        apify=None,
        treg=None,
        jev=None,
        jobs=None,
        telegram_bot=None,
    ):
        self.connect = connect
        self.secrets = secrets
        self.products = products
        self.shops = shops
        self.watches = watches
        self.keywords = keywords
        self.china_sourcing = china_sourcing
        self.kalodata_bridge = kalodata_bridge
        self.desk300 = desk300
        self.apify = apify
        self.treg = treg
        self.jev = jev
        self.jobs = jobs
        self.telegram_bot = telegram_bot

    def _derive_cn_accessory_queries(self, seed_keyword: str, target_focus: str, vn_titles: list[str]) -> list[tuple[str, str]]:
        low = f"{seed_keyword} {target_focus}".lower()
        queries: list[tuple[str, str]] = []
        for k_prefix, pairs in CURATED_ACCESSORY_CN_MAP.items():
            if k_prefix in low:
                queries.extend(pairs)

        if self.desk300 is not None and len(queries) < 4:
            try:
                d_res = self.desk300.call_gateway_json(
                    "Bạn là chuyên gia tìm nguồn phụ kiện Trung Quốc (`Pinduoduo`, `Taobao`, `1688`) qua `300+desk`. Chỉ trả về JSON hợp lệ.",
                    f"Sản phẩm gốc: {seed_keyword}\nMục tiêu bán: {target_focus or 'Tìm phụ kiện bổ sung, thay thế, đa dạng mẫu mã'}\n"
                    f"Các mẫu đang bán tại VN: {json.dumps(vn_titles[:6], ensure_ascii=False)}\n"
                    'Hãy đề xuất 4 từ khoá tiếng Trung (中文) ngắn gọn để tìm phụ kiện bổ sung / thay thế / đa dạng lựa chọn trên Pinduoduo & Taobao.\n'
                    'Trả về JSON: {"queries": [{"cn": "<từ khoá tiếng Trung>", "vi_note": "<mô tả phụ kiện tiếng Việt>"}]}',
                    task_type="ecosystem_cn_accessories",
                    timeout_sec=22,
                )
                parsed = d_res.get("parsed") if isinstance(d_res.get("parsed"), dict) else {}
                for q_obj in (parsed.get("queries") or [])[:4]:
                    if isinstance(q_obj, dict) and q_obj.get("cn"):
                        cn_s = str(q_obj["cn"]).strip()
                        vi_s = str(q_obj.get("vi_note") or cn_s).strip()
                        if cn_s and all(cn_s != ex[0] for ex in queries):
                            queries.append((cn_s, vi_s))
            except Exception:
                pass

        if not queries:
            queries = [
                (f"{seed_keyword} 保护套 配件", f"Ốp bảo vệ & Phụ kiện cho {seed_keyword}"),
                (f"{seed_keyword} 收纳包 贴膜 支架", f"Túi đựng, dán màn & giá đỡ cho {seed_keyword}"),
            ]
        return queries[:4]

    def run_ecosystem_playbook(self, body: dict, log_fn=None) -> dict:
        seed_kw = text(body.get("seed_keyword") or body.get("keyword"), "seed_keyword", 120, required=True)
        col_name = text(body.get("name") or f"Phụ kiện {seed_kw.title()}", "name", 160, required=True)
        raw_extra = body.get("extra_keywords")
        if isinstance(raw_extra, list):
            extra_kws = [str(x).strip() for x in raw_extra if str(x).strip()]
        elif isinstance(raw_extra, str):
            extra_kws = [s.strip() for s in re.split(r"[,;\n]+", raw_extra) if s.strip()]
        else:
            extra_kws = []

        target_focus = str(body.get("target_focus") or f"Nghiên cứu SP & Phụ kiện cho {seed_kw}").strip()[:300]
        playbook_mode = str(body.get("playbook_mode") or "full_hybrid").strip()
        channels = body.get("channels") if isinstance(body.get("channels"), list) and body.get("channels") else ["shopee_vn", "tiktok_shop_vn"]
        cn_platforms = body.get("cn_platforms") if isinstance(body.get("cn_platforms"), list) else ["pinduoduo", "taobao"]
        enable_cn = bool(body.get("enable_cn_expansion", bool(cn_platforms)))
        enable_kalodata = bool(body.get("enable_kalodata", playbook_mode in ("daily_index_creator_kalodata", "full_hybrid")))
        enable_global_selling = bool(body.get("enable_global_selling_creators", playbook_mode in ("daily_index_creator_kalodata", "full_hybrid")))
        daily_sched = bool(body.get("daily_schedule_enabled", True))
        sched_hours = max(1.0, min(168.0, float(body.get("schedule_interval_hours") or 24.0)))
        per_channel_limit = max(6, min(30, int(body.get("limit_per_channel") or 15)))
        score_jev_limit = max(0, min(12, int(body.get("score_jev_limit") if body.get("score_jev_limit") is not None else 6)))

        # Reuse existing collection if matching `collection_id` or exact `name`
        existing_col = None
        req_cid = str(body.get("collection_id") or "").strip()
        with self.connect() as conn:
            if req_cid:
                existing_col = conn.execute("SELECT * FROM ecosystem_collections WHERE collection_id=?", (req_cid,)).fetchone()
            if not existing_col:
                existing_col = conn.execute("SELECT * FROM ecosystem_collections WHERE LOWER(name)=LOWER(?)", (col_name,)).fetchone()

        cid = existing_col["collection_id"] if existing_col else f"eco_{uuid.uuid4().hex[:10]}"

        def _log(msg: str):
            if log_fn:
                log_fn(msg)

        cfg = settings.read_settings(self.connect, self.secrets)
        apify_toks = settings.apify_tokens(cfg)
        treg_tok = (cfg["providers"].get("treg_key") or "").strip()

        search_terms = [seed_kw] + [k for k in extra_kws if k.lower() != seed_kw.lower()]
        prev_pids = json.loads(existing_col["product_ids_json"] or "[]") if existing_col else []
        discovered_pids: list[int] = [
            p["id"]
            for p in self.products.get_products_by_ids(prev_pids)
            if is_item_relevant_to_ecosystem(p.get("title") or "", p.get("shop_name") or "", seed_kw, extra_kws)
        ]
        raw_items_collected: list[dict] = []

        # --- STEP 1: COLLECT ALL RELATED PRODUCTS & SHOPS ON SHOPEE VN + TIKTOKSHOP VN ---
        _log(f"🔎 [Bước 1] Quét tất cả SP & Shop liên quan cho {search_terms} trên {', '.join(channels)}...")
        for term in search_terms[:3]:
            for ch in channels:
                b_plat, b_mkt, ch_code = parse_marketplace_spec(ch)
                if b_plat not in ("shopee", "tiktok_shop"):
                    continue
                try:
                    kw_res = self.keywords.research_keyword(
                        keyword=term,
                        platform=ch_code,
                        market=b_mkt,
                        limit=per_channel_limit,
                        score_jev=False,
                        save_top_to_vault=False,
                        shopee_filters={"sort_by": "sales"} if b_plat == "shopee" else None,
                    )
                    rel_items = [
                        it for it in (kw_res.get("items") or [])
                        if is_item_relevant_to_ecosystem(it.get("title") or "", it.get("shop_name") or "", seed_kw, extra_kws)
                    ]
                    for it in rel_items:
                        if it.get("title"):
                            saved_it = self.products.upsert_product(it, source=f"ecosystem:{ch_code}:{term}")
                            if saved_it["id"] not in discovered_pids:
                                discovered_pids.append(saved_it["id"])
                    raw_items_collected.extend(rel_items)
                    _log(f"  ✓ {format_platform_market_label(b_plat, b_mkt)} ('{term}'): {len(rel_items)}/{len(kw_res.get('items') or [])} SP liên quan chuẩn")
                except Exception as exc:
                    _log(f"  ⚠️ Lỗi quét {ch_code} ('{term}'): {exc}")

        # --- STEP 2: KALODATA VN + AFFILIATE GLOBAL SELLING CREATOR & VIDEO RESEARCH ---
        kalo_products: list[dict] = []
        effective_videos: list[dict] = []
        effective_creators: list[dict] = []

        if enable_kalodata and self.kalodata_bridge is not None:
            _log(f"📊 [Bước 2A] Quét Kalodata VN (qua Profile `peng_dedicated`) tìm SP bán chạy 7 ngày & Video GPM cao cho '{seed_kw}'...")
            try:
                k_res = self.kalodata_bridge.search_kalodata_keyword(seed_kw, window_spec="7d", limit=15)
                kalo_products = [
                    kp for kp in (k_res.get("products") or [])
                    if is_item_relevant_to_ecosystem(kp.get("title") or "", "", seed_kw, extra_kws)
                ]
                rel_k_vids = [
                    kv for kv in (k_res.get("videos") or [])
                    if is_item_relevant_to_ecosystem(kv.get("caption") or "", kv.get("author_handle") or "", seed_kw, extra_kws)
                ]
                effective_videos.extend(rel_k_vids)
                rel_k_handles = {(kv.get("author_handle") or "").lower() for kv in rel_k_vids if kv.get("author_handle")}
                effective_creators.extend([
                    kc for kc in (k_res.get("creators") or [])
                    if (kc.get("handle") or "").lower() in rel_k_handles or is_item_relevant_to_ecosystem(kc.get("handle") or "", "", seed_kw, extra_kws)
                ])
                # Upsert Kalodata products into Vault too so recent 7d TikTok products are indexed!
                for kp in kalo_products:
                    if kp.get("title"):
                        saved_kp = self.products.upsert_product(
                            {
                                "platform": "tiktok_shop",
                                "market": "VN",
                                "native_product_id": kp.get("native_product_id") or "",
                                "title": kp["title"],
                                "price_vnd": kp.get("price_vnd") or 0.0,
                                "sold_count": kp.get("units_sold_recent") or 0,
                                "sold_30d": kp.get("units_sold_recent") or 0,
                                "image_url": kp.get("image_url") or "",
                                "url": kp.get("url") or "",
                                "note": f"Kalodata 7d: {kp.get('units_sold_recent', 0)} đơn · GMV {kp.get('gmv_recent_display', '')}",
                            },
                            source=f"kalodata_7d:{seed_kw}",
                        )
                        if saved_kp["id"] not in discovered_pids:
                            discovered_pids.append(saved_kp["id"])
                _log(f"  ✓ Kalodata VN: {len(kalo_products)} SP bán chạy 7d · {len(rel_k_vids)} Video liên quan · {len(effective_creators)} Creator")
            except Exception as exc:
                _log(f"  ⚠️ Kalodata VN bỏ qua nhẹ: {exc}")

        if enable_global_selling and self.kalodata_bridge is not None:
            _log(f"🎥 [Bước 2B] Quét Creator trên TikTok Affiliate Global Selling (`peng_dedicated`) cho '{seed_kw}'...")
            try:
                ags_creators = self.kalodata_bridge.search_affiliate_global_selling_creators(seed_kw, max_results=20)
                seen_handles = {c["handle"].lower() for c in effective_creators if c.get("handle")}
                for ac in ags_creators:
                    hl = (ac.get("handle") or "").lower()
                    if hl and hl not in seen_handles:
                        seen_handles.add(hl)
                        effective_creators.append(ac)
                    for tv in ac.get("top_videos") or []:
                        if tv.get("video_url") and all(v.get("video_url") != tv["video_url"] for v in effective_videos):
                            effective_videos.append({
                                "source": "affiliate_global_selling",
                                "video_id": tv.get("video_id") or "",
                                "video_url": tv["video_url"],
                                "caption": tv.get("caption") or "",
                                "author_handle": ac.get("handle") or "",
                                "followers": ac.get("followers") or 0,
                                "views_count": tv.get("views") or 0,
                                "orders_count": None,
                                "video_gmv_display": ac.get("total_gmv_display") or "—",
                                "gpm_display": "—",
                            })
                _log(f"  ✓ Affiliate Global Selling: +{len(ags_creators)} Creator khớp truy vấn")
            except Exception as exc:
                _log(f"  ⚠️ Affiliate Global Selling bỏ qua nhẹ: {exc}")

        # Supplement creators/videos via Apify #1 -> Treg #2 if user requested creator intel & we want rich video coverage
        if (enable_global_selling or enable_kalodata) and len(effective_videos) < 5 and apify_toks and self.apify:
            try:
                _, tt_vids = self.apify.search_tiktok_videos(apify_toks, seed_kw, limit=10)
                seen_handles = {c["handle"].lower() for c in effective_creators if c.get("handle")}
                for rv in tt_vids:
                    am = rv.get("authorMeta") if isinstance(rv.get("authorMeta"), dict) else {}
                    hdl = str(am.get("name") or rv.get("author") or "").strip().lstrip("@")
                    cap_txt = str(rv.get("text") or rv.get("desc") or "")[:240]
                    if not is_item_relevant_to_ecosystem(cap_txt, hdl, seed_kw, extra_kws):
                        continue
                    vid_id = safe_id_str(rv.get("id") or rv.get("video_id"))
                    v_url = str(rv.get("webVideoUrl") or (f"https://www.tiktok.com/@{hdl}/video/{vid_id}" if (hdl and vid_id) else ""))
                    plays = int(rv.get("playCount") or rv.get("views") or 0)
                    diggs = int(rv.get("diggCount") or rv.get("likes") or 0)
                    flw = int(am.get("fans") or 0)
                    if v_url and all(v.get("video_url") != v_url for v in effective_videos):
                        effective_videos.append({
                            "source": "apify_tiktok",
                            "video_id": vid_id,
                            "video_url": v_url,
                            "caption": cap_txt,
                            "author_handle": hdl,
                            "followers": flw,
                            "views_count": plays,
                            "likes_count": diggs,
                            "orders_count": None,
                            "video_gmv_display": "—",
                            "gpm_display": "—",
                        })
                    if hdl and hdl.lower() not in seen_handles:
                        seen_handles.add(hdl.lower())
                        effective_creators.append({
                            "source": "apify_tiktok",
                            "handle": hdl,
                            "display_name": str(am.get("nickName") or f"@{hdl}"),
                            "followers": flw,
                            "total_gmv_vnd": None,
                            "total_gmv_display": "Video Organic",
                            "units_sold": None,
                            "avg_views": plays,
                            "top_videos": [{"video_id": vid_id, "video_url": v_url, "views": plays}],
                        })
            except Exception:
                pass

        # --- STEP 3: ENRICH INVENTORY STOCK FOR TOP PRODUCTS & SCORE WITH JEV AI ---
        vault_prods = self.products.get_products_by_ids(discovered_pids)
        # Enrich up to 5 top products that lack `stock` or `price_vnd` so inventory tracking baseline is populated!
        need_stock = [p for p in vault_prods if int(p.get("stock") or 0) <= 0 and p.get("url")][:4]
        for p_st in need_stock:
            try:
                self.products.enrich_product(p_st["id"])
            except Exception:
                pass

        # Score top unscored products with TypeSafe Jev AI
        vault_prods = self.products.get_products_by_ids(discovered_pids)
        vault_prods.sort(key=lambda x: (int(x.get("sold_30d") or 0), int(x.get("sold_count") or 0), float(x.get("price_vnd") or 0)), reverse=True)
        scored_cnt = 0
        if score_jev_limit > 0 and self.products.jev:
            for p_cand in vault_prods:
                if scored_cnt >= score_jev_limit:
                    break
                if p_cand.get("jev_score") is None:
                    try:
                        self.products.score_product_jev(p_cand["id"])
                        scored_cnt += 1
                    except Exception:
                        break

        vault_prods = self.products.get_products_by_ids(discovered_pids)
        kalo_by_pid = {kp["native_product_id"]: kp for kp in kalo_products if kp.get("native_product_id")}
        for vp in vault_prods:
            vp["ecosystem_rank"] = compute_product_priority_rank(vp, kalo_by_pid)
        vault_prods.sort(
            key=lambda x: (
                x["ecosystem_rank"]["priority_points"],
                int(x.get("sold_count") or 0),
                float(x.get("jev_score") or 0.0),
            ),
            reverse=True,
        )

        # --- STEP 4: REGISTER SPECIAL PRODUCT WATCHES, SHOP WATCHES & DAILY KEYWORD INDEX WATCHES ---
        _log("⭐ [Bước 4] Thiết lập Danh sách Theo dõi Đặc biệt (SP có lượt bán/tồn kho), Theo dõi Shop & Lịch Index Hàng ngày...")
        existing_watches = self.watches.list_watches()
        existing_prod_watch_pids = {int(w["linked_product_id"]) for w in existing_watches if w.get("linked_product_id")}
        existing_shop_watch_keys = {(w["platform"], w["target_key"].lower()) for w in existing_watches if w["watch_type"] == "shop"}
        existing_kw_watch_keys = {(w["platform"], w["market"], w["target_key"].lower()) for w in existing_watches if w["watch_type"] == "keyword"}

        special_watch_ids: list[str] = []
        shop_watch_ids: list[str] = []
        kw_watch_ids: list[str] = json.loads(existing_col["keyword_watch_ids_json"] or "[]") if existing_col else []
        saved_shop_ids: list[str] = []

        # 4A) Special Product Watches (top 12 qualifying products with sales/stock/Jev)
        for vp in vault_prods[:12]:
            if not vp["ecosystem_rank"]["qualifies_special_watch"]:
                continue
            if vp["id"] in existing_prod_watch_pids:
                for w in existing_watches:
                    if w.get("linked_product_id") == vp["id"] and w["watch_id"] not in special_watch_ids:
                        special_watch_ids.append(w["watch_id"])
                continue
            t_key = vp.get("url") or vp.get("native_product_id") or vp["title"]
            created_pw = self.watches.create_watch({
                "watch_type": "product",
                "platform": vp.get("channel_code") or vp["platform"],
                "market": vp.get("market") or "VN",
                "target_key": t_key,
                "target_url": vp.get("url") or "",
                "title": f"⭐ [{col_name}] {vp['title'][:95]}",
                "linked_product_id": vp["id"],
                "interval_hours": 12.0,
                "is_special": True,
                "collection_id": cid,
                "run_immediately": False,
            })
            w_obj = created_pw.get("watch") or created_pw
            wid = w_obj["watch_id"]
            # Seed initial snapshot immediately from `vp` (price + sold_count + stock!) without extra API spend
            self.watches.run_watch_check(wid, trigger_kind="ecosystem_baseline", injected_items=[vp], auto_save_new_to_vault=False)
            special_watch_ids.append(wid)

        # 4B) Related Competitor Shops -> Save to `Kho Shop Đối thủ` + Add to `Shop Watch`
        seen_shops: set[tuple[str, str]] = set()
        for vp in vault_prods:
            sname = (vp.get("shop_name") or "").strip()
            nsid = (vp.get("native_shop_id") or "").strip()
            if not sname and not nsid:
                continue
            plat = vp["platform"]
            mkt = vp.get("market") or "VN"
            s_key = (plat, (sname or nsid).lower())
            if s_key in seen_shops or len(seen_shops) >= 10:
                continue
            seen_shops.add(s_key)
            s_url = f"https://shopee.vn/shop/{nsid}" if (plat == "shopee" and nsid) else ""
            try:
                saved_sh = self.shops.create_or_update_shop({
                    "role": "competitor_shop",
                    "platform": f"{plat}_{mkt.lower()}",
                    "market": mkt,
                    "native_shop_id": nsid,
                    "handle": sname or nsid,
                    "shop_name": sname or f"Shop {nsid}",
                    "shop_url": s_url,
                    "niche_tags": [seed_kw, col_name],
                    "note": f"Thuộc hệ sinh thái: {col_name}",
                })
                if saved_sh["shop_id"] not in saved_shop_ids:
                    saved_shop_ids.append(saved_sh["shop_id"])
                target_s = s_url or sname or nsid
                if (plat, target_s.lower()) not in existing_shop_watch_keys:
                    sw = self.watches.create_watch({
                        "watch_type": "shop",
                        "platform": f"{plat}_{mkt.lower()}",
                        "market": mkt,
                        "target_key": target_s,
                        "target_url": s_url,
                        "title": f"🏪 [{col_name}] Shop: {sname or nsid}",
                        "linked_shop_id": saved_sh["shop_id"],
                        "interval_hours": sched_hours,
                        "is_special": True,
                        "collection_id": cid,
                        "run_immediately": False,
                    })
                    sw_id = (sw.get("watch") or sw)["watch_id"]
                    shop_items = [x for x in vault_prods if (x.get("shop_name") or x.get("native_shop_id")) == (sname or nsid)]
                    self.watches.run_watch_check(sw_id, trigger_kind="ecosystem_baseline", injected_items=shop_items, injected_total_count=len(shop_items), auto_save_new_to_vault=False)
                    shop_watch_ids.append(sw_id)
            except Exception:
                pass

        # 4C) Daily Keyword Index Watches (for daily new-product detection!)
        for ch in channels:
            b_plat, b_mkt, ch_code = parse_marketplace_spec(ch)
            if b_plat not in ("shopee", "tiktok_shop"):
                continue
            if (b_plat, b_mkt, seed_kw.lower()) not in existing_kw_watch_keys:
                kw_w = self.watches.create_watch({
                    "watch_type": "keyword",
                    "platform": ch_code,
                    "market": b_mkt,
                    "target_key": seed_kw,
                    "title": f"🔑 [{col_name}] Index hàng ngày: {seed_kw} ({format_platform_market_label(b_plat, b_mkt)})",
                    "interval_hours": sched_hours,
                    "is_special": True,
                    "collection_id": cid,
                    "run_immediately": False,
                })
                kw_wid = (kw_w.get("watch") or kw_w)["watch_id"]
                ch_items = [it for it in raw_items_collected if it.get("platform") == b_plat and (it.get("market") or "VN") == b_mkt]
                self.watches.run_watch_check(
                    kw_wid,
                    trigger_kind="ecosystem_baseline_index",
                    injected_items=ch_items,
                    injected_total_count=len(ch_items),
                    auto_save_new_to_vault=False,
                )
                kw_watch_ids.append(kw_wid)

        # --- STEP 5: CHINA ACCESSORY EXPANSION ON PINDUODUO, TAOBAO (& 1688) ---
        cn_sourcing_ids: list[str] = json.loads(existing_col["cn_sourcing_ids_json"] or "[]") if existing_col else []
        cn_items_enriched: list[dict] = json.loads(existing_col["cn_items_json"] or "[]") if existing_col else []

        if enable_cn and cn_platforms and self.china_sourcing:
            vn_titles = [p["title"] for p in vault_prods[:8]]
            cn_queries = self._derive_cn_accessory_queries(seed_kw, target_focus, vn_titles)
            _log(f"🇨🇳 [Bước 5] Tìm Phụ kiện Thay thế / Bổ sung / Đa dạng mẫu trên {', '.join(cn_platforms)} với {len(cn_queries)} hướng từ khoá: {[q[0] for q in cn_queries]}...")
            seen_cn_urls = {it.get("item_url") for it in cn_items_enriched if it.get("item_url")}
            for cn_q, vi_desc in cn_queries:
                for cplat in cn_platforms:
                    if cplat not in ("pinduoduo", "taobao", "1688"):
                        continue
                    try:
                        s_res = self.china_sourcing.search_and_save(query_or_url=cn_q, platform=cplat, limit=6, weight_kg=0.25)
                        for sit in s_res.get("items") or []:
                            u_cn = sit.get("item_url") or sit["sourcing_id"]
                            if u_cn in seen_cn_urls:
                                continue
                            seen_cn_urls.add(u_cn)
                            rel = classify_cn_accessory_relation(sit.get("title") or "", cn_q)
                            sit_rich = {
                                **sit,
                                "cn_query": cn_q,
                                "vi_accessory_group": vi_desc,
                                "relation_role": rel["role"],
                                "relation_badge": rel["badge"],
                                "relation_color": rel["color"],
                            }
                            cn_items_enriched.append(sit_rich)
                            if sit["sourcing_id"] not in cn_sourcing_ids:
                                cn_sourcing_ids.append(sit["sourcing_id"])
                    except Exception as exc:
                        _log(f"  ⚠️ Nguồn TQ {cplat} ('{cn_q}'): {exc}")

        # --- STEP 6: SAVE UNIFIED ECOSYSTEM COLLECTION (`Danh mục Theo dõi`) ---
        ts_now = now()
        next_ts = _future_iso(sched_hours) if daily_sched else ""
        summary_stats = {
            "total_vn_products": len(vault_prods),
            "products_with_sales_or_stock": sum(1 for p in vault_prods if p["ecosystem_rank"]["qualifies_special_watch"]),
            "scored_jev_count": sum(1 for p in vault_prods if p.get("jev_score") is not None),
            "special_watches_count": len(special_watch_ids),
            "tracked_shops_count": len(saved_shop_ids),
            "cn_accessory_options_count": len(cn_items_enriched),
            "effective_creators_count": len(effective_creators),
            "effective_videos_count": len(effective_videos),
            "kalodata_7d_products_count": len(kalo_products),
            "baseline_captured_at": (json.loads(existing_col["index_summary_json"] or "{}").get("baseline_captured_at") if existing_col else "") or ts_now,
            "last_new_products_detected": 0,
            "headline": (
                f"Danh mục '{col_name}': {len(vault_prods)} SP sàn · {len(saved_shop_ids)} Shop theo dõi · "
                f"{len(special_watch_ids)} Theo dõi đặc biệt · {len(cn_items_enriched)} mẫu phụ kiện TQ · "
                f"{len(effective_creators)} Creator & {len(effective_videos)} Video hiệu quả"
            ),
        }

        with self.connect() as conn:
            if existing_col:
                conn.execute(
                    """
                    UPDATE ecosystem_collections
                    SET name=?, seed_keyword=?, extra_keywords_json=?, playbook_mode=?, target_focus=?,
                        channels_json=?, cn_platforms_json=?, daily_schedule_enabled=?, schedule_interval_hours=?,
                        last_run_at=?, next_run_at=?, product_ids_json=?, special_watch_ids_json=?,
                        shop_watch_ids_json=?, keyword_watch_ids_json=?, shop_ids_json=?, cn_sourcing_ids_json=?,
                        cn_items_json=?, creators_json=?, videos_json=?, kalodata_products_json=?,
                        index_summary_json=?, updated_at=?
                    WHERE collection_id=?
                    """,
                    (
                        col_name,
                        seed_kw,
                        json.dumps(extra_kws, ensure_ascii=False),
                        playbook_mode,
                        target_focus,
                        json.dumps(channels, ensure_ascii=False),
                        json.dumps(cn_platforms, ensure_ascii=False),
                        1 if daily_sched else 0,
                        sched_hours,
                        ts_now,
                        next_ts,
                        json.dumps([p["id"] for p in vault_prods], ensure_ascii=False),
                        json.dumps(special_watch_ids, ensure_ascii=False),
                        json.dumps(shop_watch_ids, ensure_ascii=False),
                        json.dumps(kw_watch_ids, ensure_ascii=False),
                        json.dumps(saved_shop_ids, ensure_ascii=False),
                        json.dumps(cn_sourcing_ids, ensure_ascii=False),
                        json.dumps(cn_items_enriched[:80], ensure_ascii=False),
                        json.dumps(effective_creators[:40], ensure_ascii=False),
                        json.dumps(effective_videos[:50], ensure_ascii=False),
                        json.dumps(kalo_products[:30], ensure_ascii=False),
                        json.dumps(summary_stats, ensure_ascii=False),
                        ts_now,
                        cid,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO ecosystem_collections
                    (collection_id, name, seed_keyword, extra_keywords_json, playbook_mode, target_focus,
                     channels_json, cn_platforms_json, daily_schedule_enabled, schedule_interval_hours,
                     last_run_at, next_run_at, product_ids_json, special_watch_ids_json, shop_watch_ids_json,
                     keyword_watch_ids_json, shop_ids_json, cn_sourcing_ids_json, cn_items_json, creators_json,
                     videos_json, kalodata_products_json, index_summary_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cid,
                        col_name,
                        seed_kw,
                        json.dumps(extra_kws, ensure_ascii=False),
                        playbook_mode,
                        target_focus,
                        json.dumps(channels, ensure_ascii=False),
                        json.dumps(cn_platforms, ensure_ascii=False),
                        1 if daily_sched else 0,
                        sched_hours,
                        ts_now,
                        next_ts,
                        json.dumps([p["id"] for p in vault_prods], ensure_ascii=False),
                        json.dumps(special_watch_ids, ensure_ascii=False),
                        json.dumps(shop_watch_ids, ensure_ascii=False),
                        json.dumps(kw_watch_ids, ensure_ascii=False),
                        json.dumps(saved_shop_ids, ensure_ascii=False),
                        json.dumps(cn_sourcing_ids, ensure_ascii=False),
                        json.dumps(cn_items_enriched[:80], ensure_ascii=False),
                        json.dumps(effective_creators[:40], ensure_ascii=False),
                        json.dumps(effective_videos[:50], ensure_ascii=False),
                        json.dumps(kalo_products[:30], ensure_ascii=False),
                        json.dumps(summary_stats, ensure_ascii=False),
                        ts_now,
                        ts_now,
                    ),
                )

        detail = self.get_collection(cid)
        return {"collection": detail, "summary": summary_stats["headline"]}

    def run_daily_index_check(self, collection_id: str, trigger: str = "manual") -> dict:
        """Re-crawl Keyword Watches + Special Product Inventory Watches for a Collection to detect NEW products & sales/stock surges."""
        col = self.get_collection(collection_id)
        kw_wids = col.get("keyword_watch_ids") or []
        sp_wids = (col.get("special_watch_ids") or [])[:8]

        new_products_found: list[dict] = []
        rising_products_found: list[dict] = []
        stock_drop_events: list[dict] = []

        for wid in kw_wids:
            try:
                res = self.watches.run_watch_check(wid, trigger_kind=f"ecosystem_{trigger}", auto_save_new_to_vault=True)
                diff = res.get("diff") or {}
                new_products_found.extend(diff.get("new_items") or [])
                rising_products_found.extend(diff.get("rising_items") or [])
            except Exception:
                pass

        for wid in sp_wids:
            try:
                res = self.watches.run_watch_check(wid, trigger_kind=f"ecosystem_stock_{trigger}")
                diff = res.get("diff") or {}
                if int(diff.get("delta_sold") or 0) > 0:
                    stock_drop_events.append({
                        "watch_id": wid,
                        "title": (res.get("watch") or {}).get("title") or "",
                        "delta_sold": diff.get("delta_sold"),
                        "stock_drop_inferred_sold": diff.get("stock_drop_inferred_sold"),
                        "cur_stock": diff.get("stock"),
                    })
            except Exception:
                pass

        # Attach any newly saved products into `product_ids_json`
        cur_pids = list(col.get("product_ids") or [])
        for ni in new_products_found:
            if ni.get("title"):
                p_saved = self.products.upsert_product(ni, source=f"ecosystem_daily_new:{col['seed_keyword']}")
                if p_saved["id"] not in cur_pids:
                    cur_pids.insert(0, p_saved["id"])

        ts_now = now()
        nxt = _future_iso(col["schedule_interval_hours"]) if col["daily_schedule_enabled"] else ""
        idx_sum = dict(col.get("index_summary") or {})
        idx_sum["last_daily_check_at"] = ts_now
        idx_sum["last_new_products_detected"] = len(new_products_found)
        idx_sum["last_rising_count"] = len(rising_products_found) + len(stock_drop_events)
        idx_sum["total_vn_products"] = len(cur_pids)

        with self.connect() as conn:
            conn.execute(
                """
                UPDATE ecosystem_collections
                SET product_ids_json=?, index_summary_json=?, last_run_at=?, next_run_at=?, updated_at=?
                WHERE collection_id=?
                """,
                (json.dumps(cur_pids), json.dumps(idx_sum, ensure_ascii=False), ts_now, nxt, ts_now, collection_id),
            )

        msg = (
            f"Cào Index hàng ngày '{col['name']}': phát hiện +{len(new_products_found)} SP mới · "
            f"{len(rising_products_found) + len(stock_drop_events)} SP tăng lượt bán / giảm tồn kho!"
        )
        return {
            "collection": self.get_collection(collection_id),
            "new_products": new_products_found,
            "rising_products": rising_products_found,
            "stock_drop_events": stock_drop_events,
            "summary": msg,
        }

    def list_collections(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM ecosystem_collections ORDER BY updated_at DESC").fetchall()
        return [self._format_collection(r, full_detail=False) for r in rows]

    def get_collection(self, collection_id: str) -> dict:
        with self.connect() as conn:
            r = conn.execute("SELECT * FROM ecosystem_collections WHERE collection_id=?", (collection_id,)).fetchone()
        if not r:
            raise ApiError("404 Not Found", "Không tìm thấy Danh mục Hệ sinh thái này")
        return self._format_collection(r, full_detail=True)

    def update_collection_schedule(self, collection_id: str, patch: dict) -> dict:
        col = self.get_collection(collection_id)
        enabled = bool(patch.get("daily_schedule_enabled", col["daily_schedule_enabled"]))
        hours = max(1.0, min(168.0, float(patch.get("schedule_interval_hours") or col["schedule_interval_hours"] or 24.0)))
        nxt = _future_iso(hours) if enabled else ""
        with self.connect() as conn:
            conn.execute(
                "UPDATE ecosystem_collections SET daily_schedule_enabled=?, schedule_interval_hours=?, next_run_at=?, updated_at=? WHERE collection_id=?",
                (1 if enabled else 0, hours, nxt, now(), collection_id),
            )
        return self.get_collection(collection_id)

    def delete_collection(self, collection_id: str) -> dict:
        with self.connect() as conn:
            conn.execute("DELETE FROM ecosystem_collections WHERE collection_id=?", (collection_id,))
        return {"deleted": True, "collection_id": collection_id}

    def run_due_daily_collections(self) -> int:
        ts = now()
        with self.connect() as conn:
            due = conn.execute(
                "SELECT collection_id FROM ecosystem_collections WHERE daily_schedule_enabled=1 AND next_run_at != '' AND next_run_at <= ? LIMIT 2",
                (ts,),
            ).fetchall()
        cnt = 0
        for r in due:
            try:
                self.run_daily_index_check(r["collection_id"], trigger="scheduled_daily")
                cnt += 1
            except Exception:
                with self.connect() as conn:
                    conn.execute("UPDATE ecosystem_collections SET next_run_at=? WHERE collection_id=?", (_future_iso(6.0), r["collection_id"]))
        return cnt

    def _format_collection(self, r, full_detail: bool = False) -> dict:
        pids = json.loads(r["product_ids_json"] or "[]")
        sp_wids = json.loads(r["special_watch_ids_json"] or "[]")
        sh_wids = json.loads(r["shop_watch_ids_json"] or "[]")
        kw_wids = json.loads(r["keyword_watch_ids_json"] or "[]")
        shop_ids = json.loads(r["shop_ids_json"] or "[]")
        kalo_prods = json.loads(r["kalodata_products_json"] or "[]")
        out = {
            "collection_id": r["collection_id"],
            "name": r["name"],
            "seed_keyword": r["seed_keyword"],
            "extra_keywords": json.loads(r["extra_keywords_json"] or "[]"),
            "playbook_mode": r["playbook_mode"],
            "target_focus": r["target_focus"],
            "channels": json.loads(r["channels_json"] or "[]"),
            "cn_platforms": json.loads(r["cn_platforms_json"] or "[]"),
            "daily_schedule_enabled": bool(r["daily_schedule_enabled"]),
            "schedule_interval_hours": r["schedule_interval_hours"],
            "last_run_at": r["last_run_at"],
            "next_run_at": r["next_run_at"],
            "product_ids": pids,
            "special_watch_ids": sp_wids,
            "shop_watch_ids": sh_wids,
            "keyword_watch_ids": kw_wids,
            "shop_ids": shop_ids,
            "index_summary": json.loads(r["index_summary_json"] or "{}"),
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        if full_detail:
            prods = self.products.get_products_by_ids(pids[:80])
            kalo_by_pid = {kp.get("native_product_id"): kp for kp in kalo_prods if kp.get("native_product_id")}
            for p in prods:
                p["ecosystem_rank"] = compute_product_priority_rank(p, kalo_by_pid)
            prods.sort(
                key=lambda x: (
                    x["ecosystem_rank"]["priority_points"],
                    int(x.get("sold_count") or 0),
                    float(x.get("jev_score") or 0.0),
                ),
                reverse=True,
            )
            all_shops = self.shops.list_shops()
            shop_map = {s["shop_id"]: s for s in all_shops}
            all_watches = self.watches.list_watches()
            watch_map = {w["watch_id"]: w for w in all_watches}

            out["products"] = prods
            out["tracked_shops"] = [shop_map[sid] for sid in shop_ids if sid in shop_map]
            out["special_watches"] = [watch_map[wid] for wid in sp_wids if wid in watch_map]
            out["shop_watches"] = [watch_map[wid] for wid in sh_wids if wid in watch_map]
            out["keyword_watches"] = [watch_map[wid] for wid in kw_wids if wid in watch_map]
            out["cn_items"] = json.loads(r["cn_items_json"] or "[]")
            out["creators"] = json.loads(r["creators_json"] or "[]")
            out["videos"] = json.loads(r["videos_json"] or "[]")
            out["kalodata_products"] = kalo_prods
        return out

    def dispatch(self, path: str, method: str, env, read_json):
        if path == "/api/ecosystems" and method == "GET":
            cols = self.list_collections()
            first_detail = self.get_collection(cols[0]["collection_id"]) if cols else None
            return "200 OK", {"collections": cols, "active_detail": first_detail}
        if path == "/api/ecosystems/run" and method == "POST":
            body = json_object(read_json, env)
            return "200 OK", self.run_ecosystem_playbook(body)
        if path.startswith("/api/ecosystems/"):
            parts = path.strip("/").split("/")
            cid = parts[2]
            if len(parts) == 3 and method == "GET":
                return "200 OK", {"collection": self.get_collection(cid)}
            if len(parts) == 3 and method == "PATCH":
                return "200 OK", {"collection": self.update_collection_schedule(cid, json_object(read_json, env)), "summary": "Đã cập nhật lịch cào tự động hàng ngày!"}
            if len(parts) == 3 and method == "DELETE":
                return "200 OK", self.delete_collection(cid)
            if len(parts) == 4 and parts[3] == "check-daily" and method == "POST":
                return "200 OK", self.run_daily_index_check(cid, trigger="manual_button")
        return None


class EcosystemDailySchedulerDaemon:
    def __init__(self, ecosystem_service: EcosystemPlaybookService, poll_sec: float = 60.0):
        self.ecosystems = ecosystem_service
        self.poll_sec = poll_sec
        self._started = False

    def start(self):
        if self._started:
            return
        self._started = True
        threading.Thread(target=self._loop, name="gs-ecosystem-daily-scheduler", daemon=True).start()

    def _loop(self):
        while True:
            time.sleep(self.poll_sec)
            try:
                self.ecosystems.run_due_daily_collections()
            except Exception:
                pass
