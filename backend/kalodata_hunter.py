"""Kalodata VN Direct Hunter & Seller/Video Suitability Classifier for Global Shop Dianshang.

Searches Kalodata VN (`/product`, `/video`, `/category`, `/category/detail`) read-only via the shared
Dedicated Chrome Profile (`peng_dedicated` on `127.0.0.1:9339`, $0.00 API cost), extracts ALL observable fields
(20 product fields + 17 video/ad/GPM fields + niche creators + top shops), classifies suitability for
Global Shop selling & video conversion, and routes items directly into Global Shop's Vault (`products`,
`product_metric_history`, `shops`, `creator_leads`, `video_reviews`) + optional `300+desk` & `Jev AI` scoring.

Hard Security & Data Hygiene Invariants:
- Loopback-only CDP (`127.0.0.1`), strictly read-only DOM/React Fiber inspection.
- Never reads `document.cookie`, `localStorage`, or credential inputs.
- Never bypasses CAPTCHA — halts immediately with HTTP 409 if CAPTCHA appears.
- Missing (`-`, empty, `***`) values stay `None`, NEVER fabricated into `0`.
"""
from __future__ import annotations

import csv
import io
import json
import re
import threading
import time
from urllib.parse import parse_qs, quote, urlsplit
import uuid

from .chrome_profile_hub import _is_temp_test_dir, cdp_ws_eval
from .kalodata_parser import parse_kalodata_display_cell
from .products import infer_industry
from .responses import ApiError, Raw, json_object, now, safe_csv_cell, safe_id_str

KALODATA_PRODUCT_URL = "https://www.kalodata.com/product"
KALODATA_VIDEO_URL = "https://www.kalodata.com/video"
KALODATA_CATEGORY_LIST_URL = "https://www.kalodata.com/category"
KALODATA_CATEGORY_DETAIL_URL = "https://www.kalodata.com/category/detail?id={category_id}"
PRIVATE_ICON_RE = re.compile(r"^[\ue000-\uf8ff\s·•=+]+$")
CTRL_SCRUB_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

# Verified Kalodata VN Official Category Catalog (30 L1 + Featured L2 Categories)
KALODATA_VN_CATEGORIES: list[dict] = [
    {"id": "873352", "parent_id": "604968", "level": "L2", "zh": "花园用品", "vi": "Làm vườn, Hạt giống & Cây cảnh", "icon": "🌱", "industry_key": "lam_vuon", "featured": True, "aliases": ("lam_vuon", "làm vườn", "cây giống", "hạt giống", "cây cảnh", "garden")},
    {"id": "600001", "level": "L1", "zh": "居家日用", "vi": "Gia dụng & Đời sống hàng ngày", "icon": "🏠", "industry_key": "gia_dung", "featured": True, "aliases": ("gia_dung", "gia dụng", "đời sống", "household")},
    {"id": "600024", "level": "L1", "zh": "厨房用品", "vi": "Đồ dùng Nhà bếp & Nấu ăn", "icon": "🍳", "industry_key": "gia_dung", "featured": True, "aliases": ("nhà bếp", "bếp", "kitchen")},
    {"id": "601450", "level": "L1", "zh": "美妆个护", "vi": "Làm đẹp & Chăm sóc cá nhân", "icon": "💄", "industry_key": "lam_dep", "featured": True, "aliases": ("lam_dep", "làm đẹp", "mỹ phẩm", "beauty")},
    {"id": "848776", "parent_id": "601450", "level": "L2", "zh": "美容护肤", "vi": "Chăm sóc da chuyên sâu (Skincare)", "icon": "✨", "industry_key": "lam_dep", "featured": True, "aliases": ("skincare", "chăm sóc da", "dưỡng da")},
    {"id": "700645", "level": "L1", "zh": "保健", "vi": "Sức khoẻ & Thực phẩm chức năng", "icon": "💊", "industry_key": "suc_khoe", "featured": True, "aliases": ("suc_khoe", "sức khoẻ", "sức khỏe", "tpcn", "health")},
    {"id": "700437", "level": "L1", "zh": "食品饮料", "vi": "Thực phẩm, Ăn vặt & Đồ uống", "icon": "🍜", "industry_key": "do_an", "featured": True, "aliases": ("do_an", "thực phẩm", "ăn vặt", "đồ ăn", "đồ uống", "food")},
    {"id": "601739", "level": "L1", "zh": "手机与数码", "vi": "Điện thoại & Phụ kiện số", "icon": "📱", "industry_key": "cong_nghe", "featured": True, "aliases": ("cong_nghe", "điện thoại", "phụ kiện số", "công nghệ", "phone")},
    {"id": "600942", "level": "L1", "zh": "家电", "vi": "Điện gia dụng", "icon": "🔌", "industry_key": "gia_dung", "featured": True, "aliases": ("điện gia dụng", "appliances")},
    {"id": "604968", "level": "L1", "zh": "家装建材", "vi": "Nhà cửa, Sửa chữa & Vật liệu (L1)", "icon": "🏡", "industry_key": "nha_cua", "featured": False, "aliases": ("nhà cửa", "sửa chữa nhà", "home improvement")},
    {"id": "604579", "level": "L1", "zh": "五金工具", "vi": "Dụng cụ cơ khí & Kim khí", "icon": "🔧", "industry_key": "oto_xemay", "featured": False, "aliases": ("dụng cụ", "cơ khí", "kim khí", "tools")},
    {"id": "601152", "level": "L1", "zh": "女装与女士内衣", "vi": "Thời trang Nữ & Đồ lót", "icon": "👗", "industry_key": "thoi_trang", "featured": False, "aliases": ("thoi_trang", "thời trang nữ", "quần áo nữ")},
    {"id": "824328", "level": "L1", "zh": "男装与男士内衣", "vi": "Thời trang Nam & Đồ lót", "icon": "👔", "industry_key": "thoi_trang", "featured": False, "aliases": ("thời trang nam", "quần áo nam")},
    {"id": "605248", "level": "L1", "zh": "时尚配件", "vi": "Phụ kiện Thời trang", "icon": "🕶️", "industry_key": "thoi_trang", "featured": False, "aliases": ("phụ kiện thời trang",)},
    {"id": "601352", "level": "L1", "zh": "鞋靴", "vi": "Giày dép", "icon": "👟", "industry_key": "thoi_trang", "featured": False, "aliases": ("giày dép", "shoes")},
    {"id": "824584", "level": "L1", "zh": "箱包", "vi": "Túi xách, Balo & Vali", "icon": "👜", "industry_key": "thoi_trang", "featured": False, "aliases": ("túi xách", "balo", "vali")},
    {"id": "602284", "level": "L1", "zh": "母婴用品", "vi": "Mẹ & Bé", "icon": "🍼", "industry_key": "me_be", "featured": False, "aliases": ("me_be", "mẹ và bé", "mẹ & bé", "baby")},
    {"id": "802184", "level": "L1", "zh": "儿童时尚", "vi": "Thời trang Trẻ em", "icon": "🧒", "industry_key": "me_be", "featured": False, "aliases": ("thời trang trẻ em",)},
    {"id": "602118", "level": "L1", "zh": "宠物用品", "vi": "Thú cưng (Chó Mèo)", "icon": "🐾", "industry_key": "thu_cung", "featured": False, "aliases": ("thu_cung", "thú cưng", "chó mèo", "pets")},
    {"id": "603014", "level": "L1", "zh": "运动与户外", "vi": "Thể thao & Dã ngoại", "icon": "🏃", "industry_key": "the_thao", "featured": False, "aliases": ("the_thao", "thể thao", "dã ngoại", "sports")},
    {"id": "605196", "level": "L1", "zh": "汽车与摩托车", "vi": "Ô tô & Xe máy", "icon": "🚗", "industry_key": "oto_xemay", "featured": False, "aliases": ("oto_xemay", "ô tô", "xe máy", "auto")},
    {"id": "600154", "level": "L1", "zh": "家纺布艺", "vi": "Chăn ga gối & Vải trang trí", "icon": "🛏️", "industry_key": "nha_cua", "featured": False, "aliases": ("chăn ga gối", "textiles")},
    {"id": "604453", "level": "L1", "zh": "家具", "vi": "Nội thất", "icon": "🪑", "industry_key": "nha_cua", "featured": False, "aliases": ("nội thất", "furniture")},
    {"id": "601755", "level": "L1", "zh": "电脑办公", "vi": "Máy tính & Thiết bị văn phòng", "icon": "💻", "industry_key": "cong_nghe", "featured": False, "aliases": ("máy tính", "văn phòng", "computer")},
    {"id": "801928", "level": "L1", "zh": "图书&杂志&音频", "vi": "Sách, Tạp chí & Văn phòng phẩm", "icon": "📚", "industry_key": "khac", "featured": False, "aliases": ("sách", "văn phòng phẩm", "books")},
    {"id": "604206", "level": "L1", "zh": "玩具和爱好", "vi": "Đồ chơi & Sở thích", "icon": "🧸", "industry_key": "me_be", "featured": False, "aliases": ("đồ chơi", "toys")},
    {"id": "953224", "level": "L1", "zh": "珠宝与衍生品", "vi": "Trang sức & Đá quý", "icon": "💍", "industry_key": "thoi_trang", "featured": False, "aliases": ("trang sức",)},
    {"id": "951432", "level": "L1", "zh": "收藏品", "vi": "Đồ sưu tầm", "icon": "🎨", "industry_key": "khac", "featured": False, "aliases": ("sưu tầm",)},
    {"id": "856720", "level": "L1", "zh": "二手", "vi": "Đồ cũ / Secondhand", "icon": "♻️", "industry_key": "khac", "featured": False, "aliases": ("secondhand", "đồ cũ")},
    {"id": "834312", "level": "L1", "zh": "虚拟商品", "vi": "Sản phẩm số & Voucher", "icon": "🎫", "industry_key": "khac", "featured": False, "aliases": ("voucher",)},
]

_CAT_BY_ID: dict[str, dict] = {c["id"]: c for c in KALODATA_VN_CATEGORIES}
_CAT_BY_ZH: dict[str, dict] = {c["zh"]: c for c in KALODATA_VN_CATEGORIES}

PID_FROM_IMG_RE = re.compile(r"tiktok\.product/(\d{15,22})/")
VID_FROM_IMG_RE = re.compile(r"tiktok\.video/(\d{15,22})/")
CID_FROM_IMG_RE = re.compile(r"tiktok\.creator/(\d{15,22})/")
URL_EXTRACT_RE = re.compile(r'https?://[^\s"\')]+')
HASHTAG_RE = re.compile(r"#([\w\u00C0-\u024F\u1E00-\u1EFF]{2,60})", re.UNICODE)
TRAILING_PRICE_RE = re.compile(
    r"\s+([₫¥￥$][\d.,]+\s*(?:亿|万|[KkMmBb])?)(?:\s*[-~]\s*([₫¥￥$][\d.,]+\s*(?:亿|万|[KkMmBb])?))?\s*$"
)
VIDEO_DURATION_PREFIX_RE = re.compile(r"^(?:(\d+)m\s*)?(?:(\d+)s)\s+", re.IGNORECASE)
VIDEO_AD_PREFIX_RE = re.compile(r"^AD\s+", re.IGNORECASE)
CREATOR_CELL_RE = re.compile(r"@([A-Za-z0-9._-]+)(?:\s+.*?粉丝数[:：]?\s*([^\s]+))?")

PRODUCT_SUITABILITY_LABELS_VI = {
    "strong_video_affiliate": "🔥 Tiềm năng nhập bán cao — Ra đơn mạnh qua Video & mở Affiliate",
    "rising_low_competition": "🚀 Ngách mới nổi — Ít đối thủ, dễ chiếm thị phần Shop",
    "live_heavy_caution": "🔴 Thiên về LIVE — Cần năng lực livestream hoặc cân nhắc kỹ",
    "mall_or_no_affiliate": "🏬 Shop Mall tự bán / Ít đơn Video — Kiểm tra thêm nguồn 1688",
}

VIDEO_SUITABILITY_LABELS_VI = {
    "organic_high_gpm": "💎 Video Organic GPM Cao — Đáng mổ xẻ / Clone 15s cho Shop",
    "winning_ad_roas": "📣 Video Ads ROAS Cao — Tham khảo Hook chạy Ads chuyển đổi",
    "standard_selling_video": "🎬 Video có phát sinh đơn hàng",
}

FX_TO_VND: dict[str, float] = {
    "VND": 1.0,
    "": 1.0,
    "CNY": 3650.0,
    "RMB": 3650.0,
    "USD": 25400.0,
    "SGD": 18900.0,
    "THB": 740.0,
}


def scrub_portal_text(val: str | None, max_len: int = 300) -> str:
    s = CTRL_SCRUB_RE.sub("", str(val or "")).replace("\u200b", "").strip()
    s = re.sub(r"[\uE000-\uF8FF]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:max_len]


def format_vnd_compact(val: float | int | None) -> str:
    if val is None:
        return "—"
    v = float(val)
    if v <= 0:
        return "0₫" if v == 0 else "—"
    if v >= 1_000_000_000:
        return f"{v / 1_000_000_000:.2f} tỷ ₫"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f} tr ₫"
    if v >= 1_000:
        return f"{v:,.0f}₫"
    return f"{v:.0f}₫"


def resolve_kalodata_category(raw_cat: str | None) -> dict | None:
    s = str(raw_cat or "").strip()
    if not s:
        return None
    if s in _CAT_BY_ID:
        return dict(_CAT_BY_ID[s])
    if s in _CAT_BY_ZH:
        return dict(_CAT_BY_ZH[s])
    low = s.lower()
    for c in KALODATA_VN_CATEGORIES:
        if low == c["vi"].lower() or low == c["zh"].lower() or low in c["aliases"]:
            return dict(c)
    for c in KALODATA_VN_CATEGORIES:
        if any(al in low or low in al for al in c["aliases"] if len(al) >= 4) or low in c["vi"].lower():
            return dict(c)
    if re.fullmatch(r"\d{5,9}", s):
        return {"id": s, "level": "", "zh": "", "vi": f"Ngành hàng #{s}", "icon": "📂", "industry_key": "khac", "featured": False, "aliases": ()}
    return None


def build_kalodata_cate_value_query(cat_meta: dict | None) -> str:
    if not cat_meta or not cat_meta.get("id"):
        return ""
    cid = str(cat_meta["id"]).strip()
    pid = str(cat_meta.get("parent_id") or "").strip()
    if pid and pid != cid:
        obj = {pid: [[pid, cid]]}
    elif cat_meta.get("level") == "L1":
        obj = {cid: [[cid]]}
    else:
        return ""
    return quote(json.dumps(obj, separators=(",", ":")))


def parse_kalodata_money_vnd(raw_str: str | int | float | None) -> float | None:
    if isinstance(raw_str, (int, float)):
        return round(float(raw_str), 2)
    s = str(raw_str or "").strip()
    if not s or s in ("-", "--", "N/A", "***"):
        return None
    p = parse_kalodata_display_cell(s, expected_currency="VND", decimal_locale="en", is_estimated_metric=True)
    dec = p.get("value_decimal")
    if dec is None:
        return None
    curr = str(p.get("currency") or "").upper()
    fx = FX_TO_VND.get(curr)
    if fx is None:
        return None
    return round(float(dec) * fx, 2)


def parse_kalodata_count_or_float(raw_str: str | None) -> float | None:
    s = str(raw_str or "").strip().replace("%", "").lstrip("><≈~").strip()
    if not s or s in ("-", "--", "N/A", "***"):
        return None
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", s):
        return float(s)
    p = parse_kalodata_display_cell(s, decimal_locale="en", is_estimated_metric=True)
    dec = p.get("value_decimal")
    return float(dec) if dec is not None else None


def split_kalodata_product_info_cell(raw_cell: str) -> dict:
    s = re.sub(r"\s+", " ", str(raw_cell or "")).strip()
    if not s:
        return {"product_title": "", "price_vnd": None, "price_min_vnd": None, "price_max_vnd": None, "price_raw": ""}
    m = TRAILING_PRICE_RE.search(s)
    if not m:
        return {"product_title": scrub_portal_text(s, 240), "price_vnd": None, "price_min_vnd": None, "price_max_vnd": None, "price_raw": ""}
    title = scrub_portal_text(s[: m.start()].strip(), 240)
    p1_raw = m.group(1) or ""
    p2_raw = m.group(2) or ""
    p1 = parse_kalodata_money_vnd(p1_raw)
    p2 = parse_kalodata_money_vnd(p2_raw) if p2_raw else p1
    p_int = int(round(p1)) if p1 is not None else None
    return {
        "product_title": title,
        "price_vnd": p_int,
        "price_min_vnd": p_int,
        "price_max_vnd": int(round(p2)) if p2 is not None else p_int,
        "price_raw": f"{p1_raw} - {p2_raw}" if p2_raw else p1_raw,
    }


def split_kalodata_video_content_cell(raw_cell: str) -> dict:
    s = re.sub(r"\s+", " ", str(raw_cell or "")).strip()
    is_ad = False
    m_ad_pre = VIDEO_AD_PREFIX_RE.match(s)
    if m_ad_pre:
        is_ad = True
        s = s[m_ad_pre.end():].strip()
    if s.endswith("工具箱") or s.endswith("Toolbox") or s.endswith(" AD"):
        m_suf = re.search(r"\s*(?:(AD)\s+)?(?:工具箱|Toolbox)\s*$", s)
        if m_suf:
            if m_suf.group(1) == "AD":
                is_ad = True
            s = s[: m_suf.start()].strip()

    dur_sec: int | None = None
    dur_lbl = ""
    m_dur = VIDEO_DURATION_PREFIX_RE.match(s)
    if m_dur:
        mins = int(m_dur.group(1) or 0)
        secs = int(m_dur.group(2) or 0)
        dur_sec = mins * 60 + secs
        dur_lbl = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
        s = s[m_dur.end():].strip()

    tags = []
    for ht in HASHTAG_RE.findall(s):
        tok = f"#{ht.lower()}"
        if tok not in tags:
            tags.append(tok)

    return {
        "duration_label": dur_lbl,
        "duration_sec": dur_sec,
        "caption": scrub_portal_text(s, 500),
        "hashtags": tags[:15],
        "is_ad": is_ad,
    }


def classify_kalodata_hunted_product(prod: dict) -> dict:
    source_mode = str(prod.get("source_mode") or "product_search")
    gmv_tot = float(prod.get("gmv_total_vnd") or 0.0)
    has_sku_split = prod.get("video_gmv_vnd") is not None or prod.get("live_gmv_vnd") is not None or prod.get("mall_card_gmv_vnd") is not None
    vid_gmv = float(prod.get("video_gmv_vnd") or 0.0)
    live_gmv = float(prod.get("live_gmv_vnd") or 0.0)
    mall_gmv = float(prod.get("mall_card_gmv_vnd") or 0.0)
    sold = int(prod.get("units_sold_window") or 0)
    comm = prod.get("commission_pct")
    creators = int(prod.get("active_creators_count") or 0)
    cr_conv = prod.get("creator_conversion_rate_pct")
    growth = prod.get("gmv_growth_pct")
    top_vids = prod.get("top_video_ids") or []
    no_linked_video_flag = bool(prod.get("no_linked_videos_explicit"))

    if source_mode == "category_detail" and not has_sku_split:
        cat_vid_share = float(prod.get("category_video_share_pct") or 0.0)
        cat_live_share = float(prod.get("category_live_share_pct") or 0.0)
        cat_mall_share = float(prod.get("category_mall_share_pct") or 0.0)
        cat_aff_share = float(prod.get("category_affiliate_share_pct") or 0.0)
        reasons_cat: list[str] = []
        if sold < 5:
            suit_key = "mall_or_no_affiliate"
            vault_bucket = "cho_danh_gia"
            suitable = False
            reasons_cat.append("Sản lượng đơn trong kỳ còn thấp")
        elif cat_live_share >= 68.0 and cat_vid_share < 25.0 and not top_vids:
            suit_key = "live_heavy_caution"
            vault_bucket = "cho_danh_gia"
            suitable = True
            reasons_cat.append(f"Ngành hàng thiên mạnh về LIVE ({cat_live_share:.1f}%)")
        else:
            suit_key = "strong_video_affiliate"
            vault_bucket = "viral" if (sold >= 500 or gmv_tot >= 50_000_000) else "moi_noi"
            suitable = True
            reasons_cat.append(f"Top Bán Chạy Ngành Hàng ({sold:,} đơn · GMV {format_vnd_compact(gmv_tot)})")
            if top_vids:
                reasons_cat.append(f"Có {len(top_vids)} Top Video kéo đơn")
            if cat_aff_share > 0:
                reasons_cat.append(f"Affiliate chiếm {cat_aff_share:.1f}% toàn ngành")
        return {
            "suitability_key": suit_key,
            "suitability_label": PRODUCT_SUITABILITY_LABELS_VI[suit_key],
            "suitable_for_system": suitable,
            "recommended_vault_bucket": vault_bucket,
            "video_gmv_share_pct": round(cat_vid_share, 1),
            "live_gmv_share_pct": round(cat_live_share, 1),
            "mall_card_share_pct": round(cat_mall_share, 1),
            "reasons": reasons_cat,
        }

    denom = gmv_tot if gmv_tot > 0 else (vid_gmv + live_gmv + mall_gmv)
    vid_share = round((vid_gmv / denom) * 100.0, 1) if denom > 0 else 0.0
    live_share = round((live_gmv / denom) * 100.0, 1) if denom > 0 else 0.0
    mall_share = round((mall_gmv / denom) * 100.0, 1) if denom > 0 else 0.0
    reasons: list[str] = []

    if sold < 5:
        suit_key = "mall_or_no_affiliate"
        vault_bucket = "cho_danh_gia"
        suitable = False
        reasons.append(f"Sản lượng đơn thấp ({sold} đơn)")
    elif vid_share >= 35.0 and sold >= 15 and creators <= 25 and ((growth is not None and growth > 0) or (cr_conv is not None and cr_conv >= 40.0)):
        suit_key = "rising_low_competition"
        vault_bucket = "moi_noi"
        suitable = True
        reasons.append(f"Video chiếm {vid_share}% GMV · Cạnh tranh thấp ({creators} KOC)")
        if growth is not None and growth > 0:
            reasons.append(f"Tăng trưởng +{growth:g}%")
    elif (vid_share >= 35.0 or vid_gmv >= 10_000_000 or sold >= 50) and not no_linked_video_flag:
        suit_key = "strong_video_affiliate"
        vault_bucket = "viral" if (sold >= 500 or gmv_tot >= 50_000_000) else "moi_noi"
        suitable = True
        reasons.append(f"Ra đơn mạnh ({sold:,} đơn · GMV {format_vnd_compact(gmv_tot)} · Video {vid_share}%)")
        if comm is not None:
            reasons.append(f"Hoa hồng KOC {comm:g}% ({creators} creator)")
    elif live_share >= 60.0:
        suit_key = "live_heavy_caution"
        vault_bucket = "cho_danh_gia"
        suitable = True
        reasons.append(f"Doanh thu tập trung LIVE ({live_share}%) · {sold:,} đơn")
    else:
        suit_key = "mall_or_no_affiliate"
        vault_bucket = "cho_danh_gia"
        suitable = sold >= 15
        reasons.append(f"Thẻ SP / Mall chiếm {mall_share}% · {sold:,} đơn")

    return {
        "suitability_key": suit_key,
        "suitability_label": PRODUCT_SUITABILITY_LABELS_VI[suit_key],
        "suitable_for_system": suitable,
        "recommended_vault_bucket": vault_bucket,
        "video_gmv_share_pct": vid_share,
        "live_gmv_share_pct": live_share,
        "mall_card_share_pct": mall_share,
        "reasons": reasons,
    }


def classify_kalodata_hunted_video(vid: dict) -> dict:
    is_ad = bool(vid.get("is_ad"))
    ad_share = float(vid.get("ad_views_share_pct") or 0.0)
    roas = float(vid.get("ad_roas") or 0.0)
    gpm = float(vid.get("video_gpm_vnd") or 0.0)
    orders = int(vid.get("video_orders_count") or 0)

    if not is_ad and ad_share == 0.0 and gpm >= 100_000 and orders >= 1:
        vkey = "organic_high_gpm"
        suitable = True
        note = f"100% Organic đạt GPM {format_vnd_compact(gpm)}/1K views ({orders} đơn)"
    elif (is_ad or ad_share > 0) and roas >= 2.0 and orders >= 1:
        vkey = "winning_ad_roas"
        suitable = True
        note = f"Ads ROAS {roas:g}x · GPM {format_vnd_compact(gpm)} ({orders} đơn)"
    else:
        vkey = "standard_selling_video"
        suitable = orders >= 1
        note = f"Đơn: {orders} · GPM: {format_vnd_compact(gpm if gpm > 0 else None)}"

    return {
        "suitability_key": vkey,
        "suitability_label": VIDEO_SUITABILITY_LABELS_VI[vkey],
        "suitable_for_system": suitable,
        "reason": note,
    }


class KalodataVnHunterService:
    """Live read-only Kalodata VN Category & Keyword Hunter + Global Shop Vault Router."""

    def __init__(self, connect, secrets, products, chrome_hub, shops=None, desk_pipeline=None, jev=None, custom_scraper=None):
        self.connect = connect
        self.secrets = secrets
        self.products = products
        self.chrome_hub = chrome_hub
        self.shops = shops
        self.desk_pipeline = desk_pipeline
        self.jev = jev
        self.custom_scraper = custom_scraper
        self._cdp_lock = threading.RLock()

    def _lock_ref(self):
        return getattr(self.chrome_hub, "cdp_lock", None) or self._cdp_lock

    @staticmethod
    def list_categories_catalog() -> list[dict]:
        return [
            {
                "id": c["id"],
                "level": c["level"],
                "zh": c["zh"],
                "vi": c["vi"],
                "icon": c["icon"],
                "industry_key": c["industry_key"],
                "featured": c["featured"],
            }
            for c in KALODATA_VN_CATEGORIES
        ]

    @staticmethod
    def _col_idx(ths: list[str], patterns: tuple[str, ...], default_idx: int) -> int:
        for i, h in enumerate(ths):
            hl = h.lower()
            if any(p.lower() in hl for p in patterns):
                return i
        return default_idx

    def _ensure_kalodata_tab(self, target_url: str, *, require_search_input: bool = True) -> tuple[int, str]:
        hub = self.chrome_hub
        if hub is None:
            raise ApiError("503 Service Unavailable", "Chưa khởi tạo Chrome Profile Hub cho Kalodata VN.")
        port = hub.get_live_port()
        if not port:
            if _is_temp_test_dir(hub.root):
                raise ApiError("503 Service Unavailable", "Chrome Profile Hub tắt trong môi trường test tạm thời.")
            ens = hub.ensure_running(want_kalodata=True, want_tiktok_creator=False, kalodata_url=target_url)
            port = ens.get("port")
            time.sleep(2.8)
        if not port:
            raise ApiError("503 Service Unavailable", "Không mở được Chrome Chuyên Dụng `peng_dedicated` — hãy bấm Mở Kalodata ở mục Cài đặt.")

        tab = hub.open_or_focus_tab(port, ("kalodata.com",), target_url, focus=False)
        if not tab or not tab.get("webSocketDebuggerUrl"):
            raise ApiError("503 Service Unavailable", "Không tìm thấy tab Kalodata trên Chrome Chuyên Dụng.")
        tid = tab.get("id")
        ws = tab["webSocketDebuggerUrl"]

        cur_sp = urlsplit(str(tab.get("url") or ""))
        want_sp = urlsplit(target_url)
        want_id = (parse_qs(want_sp.query).get("id") or [""])[0]
        cur_id = (parse_qs(cur_sp.query).get("id") or [""])[0]
        want_cv = (parse_qs(want_sp.query).get("cateValue") or [""])[0]
        cur_cv = (parse_qs(cur_sp.query).get("cateValue") or [""])[0]
        if cur_sp.path.rstrip("/") != want_sp.path.rstrip("/") or want_id != cur_id or want_cv != cur_cv:
            cdp_ws_eval(port, ws, f"location.href = {json.dumps(target_url)}; JSON.stringify({{ok:true}})")
            time.sleep(3.6)
            tabs2 = hub.list_tabs(port)
            tab = next((t for t in tabs2 if t.get("id") == tid), None) or next(
                (t for t in tabs2 if "kalodata.com" in str(t.get("url") or "")),
                tab,
            )
            ws = tab["webSocketDebuggerUrl"]

        deadline = time.time() + 9.0
        state = {}
        while time.time() < deadline:
            state = cdp_ws_eval(
                port,
                ws,
                r"""(() => {
                  const cap = document.querySelector("[class*='captcha'], iframe[src*='captcha'], .geetest_panel");
                  const loginForm = document.querySelector("form#register, input#register_password");
                  const inp = document.querySelector("input[placeholder*='输入'], input[placeholder*='搜索'], input[placeholder*='Search'], input[placeholder*='Enter'], .ant-input-affix-wrapper input.ant-input");
                  const rowCnt = document.querySelectorAll("table tbody tr:not(.ant-table-measure-row)").length;
                  return JSON.stringify({
                    url: location.href,
                    title: document.title,
                    has_captcha: Boolean(cap && cap.offsetParent !== null),
                    login_required: location.pathname.startsWith('/login') || Boolean(loginForm && loginForm.offsetParent !== null),
                    has_input: Boolean(inp),
                    row_cnt: rowCnt,
                  });
                })()""",
            )
            if state.get("has_captcha"):
                raise ApiError("409 Conflict", "Kalodata đang yêu cầu xác minh CAPTCHA — vui lòng xác nhận trực tiếp trên cửa sổ Chrome Chuyên Dụng rồi thử lại.")
            if state.get("login_required"):
                raise ApiError("401 Unauthorized", "Phiên Kalodata VN trên Chrome Chuyên Dụng chưa đăng nhập — vui lòng đăng nhập hoặc bấm Đổi Tài Khoản trong Cài đặt.")
            if require_search_input and state.get("has_input"):
                break
            if not require_search_input and int(state.get("row_cnt") or 0) >= 1:
                break
            time.sleep(0.5)
        if require_search_input and not state.get("has_input"):
            raise ApiError("503 Service Unavailable", "Không tìm thấy ô tìm kiếm trên trang Kalodata VN — vui lòng kiểm tra phiên đăng nhập Chrome Chuyên Dụng.")
        return port, ws

    @staticmethod
    def _select_window_if_needed(port: int, ws: str, window_spec: str) -> None:
        win_patterns = {
            "7d": "过去7天|Last 7 days|7 Days",
            "30d": "过去30天|Last 30 days|30 Days",
            "90d": "过去90天|Last 90 days|90 Days",
        }
        pat = win_patterns.get(window_spec)
        if not pat:
            return
        cur_check = cdp_ws_eval(
            port,
            ws,
            r"""(() => {
              const badges = Array.from(document.querySelectorAll("span[data-slot='badge'], div.cursor-pointer, button"))
                .filter(el => /过去\d+天|Last \d+ days/i.test((el.innerText || "").trim()) && (el.innerText || "").length < 60)
                .map(el => (el.innerText || "").replace(/\s+/g, " ").trim());
              return JSON.stringify({cur: badges.join(" | ")});
            })()""",
        )
        cur_txt = str(cur_check.get("cur") or "")
        if (
            (window_spec == "7d" and ("过去7天" in cur_txt or "Last 7" in cur_txt))
            or (window_spec == "30d" and ("过去30天" in cur_txt or "Last 30" in cur_txt))
            or (window_spec == "90d" and ("过去90天" in cur_txt or "Last 90" in cur_txt))
        ):
            return

        opened = cdp_ws_eval(
            port,
            ws,
            r"""(() => {
              const btn = Array.from(document.querySelectorAll("div.cursor-pointer, button, div"))
                .find(el => el.offsetParent !== null && /过去\d+天\s*\(|Last \d+ days\s*\(/i.test((el.innerText || "").trim()) && (el.innerText || "").length < 55)
                || Array.from(document.querySelectorAll("button, div, span"))
                .find(el => el.offsetParent !== null && el.children.length <= 2 && !/^日期[:：]/.test((el.innerText || "").trim()) && /过去\d+天|Last \d+ days/i.test((el.innerText || "").trim()));
              if (!btn) return JSON.stringify({opened: false});
              btn.click();
              return JSON.stringify({opened: true});
            })()""",
        )
        if not opened.get("opened"):
            return
        time.sleep(0.45)
        cdp_ws_eval(
            port,
            ws,
            f"""(() => {{
              const re = new RegExp({json.dumps(pat)}, "i");
              const opt = Array.from(document.querySelectorAll("div, span, li, button"))
                .find(el => el.offsetParent !== null && el.children.length <= 2 && re.test((el.innerText || "").trim()) && (el.innerText || "").length < 36);
              if (opt) opt.click();
              else document.body.click();
              return "{{}}";
            }})()""",
        )
        time.sleep(0.45)
        sub = cdp_ws_eval(
            port,
            ws,
            r"""(() => {
              const b = Array.from(document.querySelectorAll("button"))
                .find(el => el.offsetParent !== null && !el.disabled && /^(提交|Apply|Submit)$/i.test((el.innerText || "").trim()));
              if (b) { b.click(); return JSON.stringify({submitted: true}); }
              return JSON.stringify({submitted: false});
            })()""",
        )
        time.sleep(2.4 if sub.get("submitted") else 1.8)

    @staticmethod
    def _run_ime_safe_search(port: int, ws: str, keyword: str) -> None:
        pre = cdp_ws_eval(
            port,
            ws,
            r"""(() => {
              const tr = document.querySelector("table tbody tr:not(.ant-table-measure-row)");
              const sig = (tr?.innerText || "").replace(/\s+/g, " ").trim().slice(0, 140);
              return JSON.stringify({sig});
            })()""",
        )
        before_sig = str(pre.get("sig") or "")
        cdp_ws_eval(
            port,
            ws,
            f"""(() => {{
              const inp = document.querySelector("input[placeholder*='输入'], input[placeholder*='搜索'], input[placeholder*='Search'], input[placeholder*='Enter'], .ant-input-affix-wrapper input.ant-input");
              if (!inp) return "{{}}";
              inp.focus();
              const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
              setter.call(inp, {json.dumps(keyword)});
              inp.dispatchEvent(new Event("input", {{bubbles: true}}));
              const rpKey = Object.keys(inp).find(k => k.startsWith("__reactProps"));
              if (rpKey && inp[rpKey]?.onChange) inp[rpKey].onChange({{target: inp, currentTarget: inp}});
              return "{{}}";
            }})()""",
        )
        time.sleep(0.35)
        cdp_ws_eval(
            port,
            ws,
            r"""(() => {
              const inp = document.querySelector("input[placeholder*='输入'], input[placeholder*='搜索'], input[placeholder*='Search'], input[placeholder*='Enter'], .ant-input-affix-wrapper input.ant-input");
              if (!inp) return "{}";
              const rpKey = Object.keys(inp).find(k => k.startsWith("__reactProps"));
              if (rpKey && inp[rpKey]?.onKeyDown) {
                inp[rpKey].onKeyDown({
                  key: "Enter", code: "Enter", keyCode: 13, which: 13,
                  target: inp, currentTarget: inp,
                  nativeEvent: {isComposing: false},
                  preventDefault: () => {}, stopPropagation: () => {}
                });
              }
              const wrap = inp.parentElement?.parentElement || inp.parentElement;
              const sbtn = wrap ? Array.from(wrap.querySelectorAll("button")).find(b => !b.disabled) : null;
              if (sbtn) sbtn.click();
              return "{}";
            })()""",
        )
        time.sleep(1.3)
        dl = time.time() + 14.0
        while time.time() < dl:
            chk = cdp_ws_eval(
                port,
                ws,
                r"""(() => {
                  const loading = Boolean(document.querySelector(".ant-spin-spinning, [class*='animate-spin']"));
                  const bodyTxt = document.querySelector("table")?.innerText || document.body?.innerText || "";
                  const isEmpty = /暂无数据|暂无查询结果|No data|未找到/i.test(bodyTxt);
                  const trs = Array.from(document.querySelectorAll("table tbody tr:not(.ant-table-measure-row)"))
                    .filter(r => r.querySelectorAll("td").length >= 5);
                  const sig = (trs[0]?.innerText || "").replace(/\s+/g, " ").trim().slice(0, 140);
                  const hasHl = Boolean(document.querySelector(".kalo-highlight"));
                  const hasPag = document.querySelectorAll("button[data-slot='pagination-link'], .ant-pagination-item").length > 0;
                  return JSON.stringify({loading, isEmpty, rc: trs.length, sig, hasHl, hasPag});
                })()""",
            )
            if not chk.get("loading"):
                if chk.get("isEmpty"):
                    break
                rc = int(chk.get("rc") or 0)
                sig = str(chk.get("sig") or "")
                if rc >= 1 and (sig != before_sig or chk.get("hasHl")) and (chk.get("hasPag") or rc < 50):
                    break
            time.sleep(0.5)

    @staticmethod
    def _clear_search_box(port: int, ws: str) -> None:
        try:
            cdp_ws_eval(
                port,
                ws,
                r"""(() => {
                  const inp = document.querySelector("input[placeholder*='输入'], input[placeholder*='搜索'], input[placeholder*='Search'], input[placeholder*='Enter'], .ant-input-affix-wrapper input.ant-input");
                  if (inp && inp.value) {
                    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                    setter.call(inp, "");
                    const rpKey = Object.keys(inp).find(k => k.startsWith("__reactProps"));
                    if (rpKey && inp[rpKey]?.onChange) inp[rpKey].onChange({target: inp, currentTarget: inp});
                  }
                  return "{}";
                })()""",
            )
        except Exception:
            pass

    @staticmethod
    def _set_page_size_if_needed(port: int, ws: str, target_limit: int) -> int:
        want_ps = 10 if target_limit <= 10 else (20 if target_limit <= 20 else 50)
        cur_info = cdp_ws_eval(
            port,
            ws,
            r"""(() => {
              const clean = s => (s || "").replace(/[\uE000-\uF8FF]/g, "").replace(/\s+/g, " ").trim();
              const btn = Array.from(document.querySelectorAll("button[data-slot='select-trigger'], div, span, button"))
                .find(e => e.offsetParent !== null && e.children.length <= 3 && /^\d+\s*\/\s*(页|page)$/i.test(clean(e.innerText)));
              if (!btn) return JSON.stringify({cur: 10, found: false});
              const m = clean(btn.innerText).match(/(\d+)/);
              const cur = m ? parseInt(m[1], 10) : 10;
              return JSON.stringify({cur, found: true});
            })()""",
        )
        cur_ps = int(cur_info.get("cur") or 10)
        if not cur_info.get("found") or cur_ps >= want_ps:
            return max(cur_ps, want_ps) if cur_info.get("found") else 10

        cdp_ws_eval(
            port,
            ws,
            r"""(() => {
              const clean = s => (s || "").replace(/[\uE000-\uF8FF]/g, "").replace(/\s+/g, " ").trim();
              const btn = Array.from(document.querySelectorAll("button[data-slot='select-trigger'], div, span, button"))
                .find(e => e.offsetParent !== null && e.children.length <= 3 && /^\d+\s*\/\s*(页|page)$/i.test(clean(e.innerText)));
              if (btn) btn.click();
              return "{}";
            })()""",
        )
        time.sleep(0.45)
        clicked = cdp_ws_eval(
            port,
            ws,
            f"""(() => {{
              const clean = s => (s || "").replace(/[\\uE000-\\uF8FF]/g, "").replace(/\\s+/g, " ").trim();
              const re = /^{want_ps}\\s*\\/\\s*(页|page)$/i;
              const opt = Array.from(document.querySelectorAll("[data-slot='select-item'], div[role='option'], div, span, li"))
                .filter(e => e.offsetParent !== null && e.children.length <= 2 && re.test(clean(e.innerText)))
                .pop();
              if (opt) opt.click();
              else document.body.click();
              return JSON.stringify({{ok: Boolean(opt)}});
            }})()""",
        )
        if clicked.get("ok"):
            time.sleep(2.8)
            return want_ps
        return cur_ps

    @staticmethod
    def _reset_stale_filters_if_no_category(port: int, ws: str) -> None:
        """Clear sticky Kalodata filter pills (e.g. `类目: 花园用品`) from prior sessions when searching across all categories."""
        res = cdp_ws_eval(
            port,
            ws,
            r"""(() => {
              const badges = Array.from(document.querySelectorAll("span[data-slot='badge']"))
                .map(b => (b.innerText || "").trim());
              const hasStale = badges.some(t => t && !/^日期[:：]/.test(t));
              const bodyTxt = (document.body?.innerText || "").slice(0, 2600);
              if (!hasStale && !/(类目[:：]|Category[:：])/i.test(bodyTxt)) return JSON.stringify({reset: false});
              const rst = Array.from(document.querySelectorAll("button, span, div")).find(
                e => e.offsetParent !== null && e.children.length === 0 && /^(重置|Reset)$/i.test((e.innerText || "").trim())
              );
              if (rst) {
                (rst.closest("button") || rst).click();
                return JSON.stringify({reset: true});
              }
              return JSON.stringify({reset: false});
            })()""",
        )
        if res.get("reset"):
            time.sleep(0.5)
            cdp_ws_eval(
                port,
                ws,
                r"""(() => {
                  const b = Array.from(document.querySelectorAll("button"))
                    .find(el => el.offsetParent !== null && !el.disabled && /^(提交|Apply|Submit)$/i.test((el.innerText || "").trim()));
                  if (b) b.click();
                  return "{}";
                })()""",
            )
            time.sleep(2.4)

    @classmethod
    def _collect_paginated_table_rows(cls, port: int, ws: str, limit: int) -> dict:
        target_limit = max(1, min(1000, int(limit)))
        wait_deadline = time.time() + 7.5
        while time.time() < wait_deadline:
            ready = cdp_ws_eval(
                port,
                ws,
                r"""(() => {
                  const bodyTxt = document.querySelector("table")?.innerText || "";
                  const isEmpty = /暂无数据|暂无查询结果|No data|未找到/i.test(document.body?.innerText || bodyTxt);
                  const rc = Array.from(document.querySelectorAll("table tbody tr:not(.ant-table-measure-row)"))
                    .filter(r => r.querySelectorAll("td").length >= 5).length;
                  return JSON.stringify({rc, isEmpty});
                })()""",
            )
            if int(ready.get("rc") or 0) >= 1 or ready.get("isEmpty"):
                break
            time.sleep(0.45)

        eff_ps = cls._set_page_size_if_needed(port, ws, target_limit)
        max_pages = max(1, min(25, (target_limit + eff_ps - 1) // max(1, eff_ps)))

        # Reset pagination to Page 1 if Kalodata persisted a higher page (e.g. rank 51 or 151)
        reset_p1 = cdp_ws_eval(
            port,
            ws,
            r"""(() => {
              const tr = document.querySelector("table tbody tr:not(.ant-table-measure-row)");
              const sig = (tr?.innerText || "").replace(/\s+/g, " ").trim().slice(0, 120);
              const mRank = sig.match(/^(\d+)\b/);
              const rankGt1 = mRank && parseInt(mRank[1], 10) > 1;
              const p1 = Array.from(document.querySelectorAll("button[data-slot='pagination-link']"))
                .find(b => (b.innerText || "").trim() === "1");
              if (!p1) return JSON.stringify({clicked: false, sig});
              const isAct = p1.getAttribute("data-active") === "true" || p1.getAttribute("aria-current") === "page";
              if (isAct && !rankGt1) return JSON.stringify({clicked: false, sig});
              p1.click();
              return JSON.stringify({clicked: true, sig});
            })()""",
        )
        if reset_p1.get("clicked"):
            old_sig = str(reset_p1.get("sig") or "")
            p1_dl = time.time() + 12.0
            while time.time() < p1_dl:
                time.sleep(0.45)
                c1 = cdp_ws_eval(
                    port,
                    ws,
                    r"""(() => {
                      const tr = document.querySelector("table tbody tr:not(.ant-table-measure-row)");
                      return JSON.stringify({sig: (tr?.innerText || "").replace(/\s+/g, " ").trim().slice(0, 120)});
                    })()""",
                )
                if c1.get("sig") and c1.get("sig") != old_sig:
                    break

        ths: list[str] = []
        collected: list[dict] = []
        seen_keys: set[str] = set()

        for page_num in range(1, max_pages + 1):
            snap = cdp_ws_eval(
                port,
                ws,
                r"""(() => {
                  const ths = Array.from(document.querySelectorAll("table thead th")).map(th => (th.innerText || "").replace(/\s+/g, " ").trim());
                  const bodyTxt = document.querySelector("table")?.innerText || "";
                  if (/暂无数据|No data|未找到/i.test(bodyTxt)) return JSON.stringify({ths, rows: [], firstSig: ""});
                  const trs = Array.from(document.querySelectorAll("table tbody tr:not(.ant-table-measure-row)"))
                    .filter(r => r.querySelectorAll("td").length >= 5);
                  const firstSig = (trs[0]?.innerText || "").replace(/\s+/g, " ").trim().slice(0, 120);
                  const rows = trs.map(tr => {
                    const tds = Array.from(tr.querySelectorAll("td")).map(td => (td.innerText || "").replace(/\s+/g, " ").trim());
                    const bgImgs = Array.from(tr.querySelectorAll('*'))
                      .map(el => el.src || el.style?.backgroundImage || getComputedStyle(el).backgroundImage || "")
                      .filter(v => v && v !== "none" && (v.includes("kalocdn") || v.includes("kalowave") || v.includes("tiktok.")));
                    let rowKey = "";
                    let rowOrig = null;
                    try {
                      for (const el of [tr, ...Array.from(tr.querySelectorAll("td, div")).slice(0, 6)]) {
                        const fk = Object.keys(el).find(k => k.startsWith("__reactFiber"));
                        let cur = fk ? el[fk] : null;
                        for (let d = 0; d < 18 && cur; d++) {
                          if (!rowKey && cur.key && /^\d{15,22}$/.test(String(cur.key))) rowKey = String(cur.key);
                          const mp = cur.memoizedProps;
                          const cand = (mp && mp.row && mp.row.original) || (mp && mp.cell && mp.cell.row && mp.cell.row.original);
                          if (cand && typeof cand === "object") {
                            rowOrig = cand;
                            if (!rowKey && cand.id) rowKey = String(cand.id);
                            break;
                          }
                          cur = cur.return;
                        }
                        if (rowOrig) break;
                      }
                    } catch {}
                    return {rowKey, tds, bgImgs, rowOrig};
                  });
                  return JSON.stringify({ths, rows, firstSig});
                })()""",
            )
            if not ths and snap.get("ths"):
                ths = snap["ths"]
            page_rows = snap.get("rows") or []
            if not page_rows:
                break
            first_sig_before = str(snap.get("firstSig") or "")
            added_this_page = 0
            for r in page_rows:
                dedup_k = r.get("rowKey") or ("|".join((r.get("tds") or [])[:3]))
                if dedup_k in seen_keys:
                    continue
                seen_keys.add(dedup_k)
                collected.append(r)
                added_this_page += 1
                if len(collected) >= target_limit:
                    break
            if len(collected) >= target_limit or added_this_page == 0 or page_num >= max_pages:
                break

            next_p = page_num + 1
            # Wait briefly if pagination bar is still mounting on full page
            if len(page_rows) >= eff_ps:
                for _ in range(4):
                    has_pb = cdp_ws_eval(
                        port,
                        ws,
                        "JSON.stringify({n: document.querySelectorAll(\"button[data-slot='pagination-link']\").length})",
                    )
                    if int(has_pb.get("n") or 0) > 0:
                        break
                    time.sleep(0.45)

            moved = cdp_ws_eval(
                port,
                ws,
                f"""(() => {{
                  const isDisabled = b => !b || b.disabled || b.getAttribute("aria-disabled") === "true" || /(^|\\s)pointer-events-none(\\s|$)/.test(b.className || "");
                  const pBtns = Array.from(document.querySelectorAll("button[data-slot='pagination-link']"));
                  let target = pBtns.find(b => (b.innerText || "").trim() === "{next_p}" && !isDisabled(b));
                  if (!target) {{
                    target = document.querySelector("button[aria-label='下一页'], button[aria-label*='Next']");
                    if (isDisabled(target)) target = null;
                  }}
                  if (target) {{
                    try {{ target.scrollIntoView({{block: "center"}}); }} catch {{}}
                    target.click();
                  }}
                  return JSON.stringify({{moved: Boolean(target)}});
                }})()""",
            )
            if not moved.get("moved"):
                break
            dl = time.time() + 16.0
            while time.time() < dl:
                time.sleep(0.55)
                chk = cdp_ws_eval(
                    port,
                    ws,
                    r"""(() => {
                      const loading = Boolean(document.querySelector(".ant-spin-spinning, [class*='animate-spin']"));
                      const tr = document.querySelector("table tbody tr:not(.ant-table-measure-row)");
                      if (!tr) return JSON.stringify({loading, sig: ""});
                      return JSON.stringify({loading, sig: (tr.innerText || "").replace(/\s+/g, " ").trim().slice(0, 120)});
                    })()""",
                )
                if not chk.get("loading") and chk.get("sig") and chk.get("sig") != first_sig_before:
                    break

        return {"ths": ths, "rows": collected[:target_limit]}

    def scrape_kalodata_products(
        self,
        keyword: str = "",
        *,
        category_meta: dict | None = None,
        window_spec: str = "7d",
        limit: int = 20,
    ) -> tuple[list[dict], str]:
        clean_kw = str(keyword or "").strip().lstrip("#").strip()
        cate_q = build_kalodata_cate_value_query(category_meta)
        target_url = f"{KALODATA_PRODUCT_URL}?cateValue={cate_q}" if cate_q else KALODATA_PRODUCT_URL
        port, ws = self._ensure_kalodata_tab(target_url)
        try:
            if not category_meta:
                self._reset_stale_filters_if_no_category(port, ws)
            self._select_window_if_needed(port, ws, window_spec)
            if clean_kw:
                self._run_ime_safe_search(port, ws, clean_kw)
            raw = self._collect_paginated_table_rows(port, ws, limit=max(1, min(1000, int(limit))))
        finally:
            if clean_kw:
                self._clear_search_box(port, ws)

        ths = raw.get("ths") or []
        idx_info = self._col_idx(ths, ("商品信息", "product"), 1)
        idx_gmv = self._col_idx(ths, ("成交金额", "revenue"), 2)
        idx_trend = self._col_idx(ths, ("成交趋势", "revenue trend"), 3)
        idx_growth = self._col_idx(ths, ("增长率", "growth"), 4)
        idx_sold = self._col_idx(ths, ("销量", "items sold"), 5)
        idx_topvid = self._col_idx(ths, ("最高视频", "top video"), 6)
        idx_rating = self._col_idx(ths, ("商品评分", "rating"), 7)
        idx_aov = self._col_idx(ths, ("平均销售价", "unit price", "aov"), 8)
        idx_ship = self._col_idx(ths, ("运费", "shipping"), 9)
        idx_comm = self._col_idx(ths, ("佣金比例", "commission"), 10)
        idx_creators = self._col_idx(ths, ("达人数量", "creators"), 11)
        idx_launch = self._col_idx(ths, ("上架时间", "launch"), 12)
        idx_cr_conv = self._col_idx(ths, ("达人出单率", "conversion"), 13)
        idx_live = self._col_idx(ths, ("直播成交", "live"), 14)
        idx_video = self._col_idx(ths, ("视频成交", "video"), 15)
        idx_mall = self._col_idx(ths, ("商品卡成交", "product card", "mall"), 16)

        trend_hdr = ths[idx_trend] if idx_trend < len(ths) else ""
        m_rng = re.search(r"\(([^)]+)\)", trend_hdr)
        range_label = m_rng.group(1).strip() if m_rng else window_spec

        products_out: list[dict] = []
        for idx, r in enumerate(raw.get("rows") or [], start=1):
            tds = r.get("tds") or []
            img_urls = [m.group(0) for im in (r.get("bgImgs") or []) if (m := URL_EXTRACT_RE.search(str(im)))]
            pid = str(r.get("rowKey") or "").strip()
            cover_url = ""
            top_vids: list[dict] = []
            for u in img_urls:
                mp = PID_FROM_IMG_RE.search(u)
                if mp:
                    pid = pid or mp.group(1)
                    cover_url = cover_url or u
                mv = VID_FROM_IMG_RE.search(u)
                if mv and all(x["video_id"] != mv.group(1) for x in top_vids):
                    top_vids.append({"video_id": mv.group(1), "cover_url": u})
            if not pid:
                continue

            info_parsed = split_kalodata_product_info_cell(tds[idx_info] if idx_info < len(tds) else "")
            gmv_tot = parse_kalodata_money_vnd(tds[idx_gmv] if idx_gmv < len(tds) else "")
            growth_pct = parse_kalodata_count_or_float(tds[idx_growth] if idx_growth < len(tds) else "")
            sold_num = parse_kalodata_count_or_float(tds[idx_sold] if idx_sold < len(tds) else "")
            topvid_txt = tds[idx_topvid] if idx_topvid < len(tds) else ""
            no_vid_explicit = "不存在关联视频" in topvid_txt or "no video" in topvid_txt.lower()
            rating_val = parse_kalodata_count_or_float(tds[idx_rating] if idx_rating < len(tds) else "")
            aov_vnd = parse_kalodata_money_vnd(tds[idx_aov] if idx_aov < len(tds) else "")
            ship_vnd = parse_kalodata_money_vnd(tds[idx_ship] if idx_ship < len(tds) else "")
            comm_pct = parse_kalodata_count_or_float(tds[idx_comm] if idx_comm < len(tds) else "")
            creators_cnt = parse_kalodata_count_or_float(tds[idx_creators] if idx_creators < len(tds) else "")
            launch_raw = (tds[idx_launch] if idx_launch < len(tds) else "").replace("/", "-")
            cr_conv_pct = parse_kalodata_count_or_float(tds[idx_cr_conv] if idx_cr_conv < len(tds) else "")
            live_gmv = parse_kalodata_money_vnd(tds[idx_live] if idx_live < len(tds) else "")
            vid_gmv = parse_kalodata_money_vnd(tds[idx_video] if idx_video < len(tds) else "")
            mall_gmv = parse_kalodata_money_vnd(tds[idx_mall] if idx_mall < len(tds) else "")

            eff_price = info_parsed["price_vnd"] or (int(round(aov_vnd)) if aov_vnd else None)
            p_item = {
                "rank": idx,
                "native_product_id": safe_id_str(pid),
                "product_title": info_parsed["product_title"] or f"TikTok Shop Product #{pid}",
                "price_vnd": eff_price,
                "price_min_vnd": info_parsed["price_min_vnd"],
                "price_max_vnd": info_parsed["price_max_vnd"],
                "price_raw": info_parsed["price_raw"],
                "cover_image_url": cover_url,
                "canonical_url": f"https://shop.tiktok.com/view/product/{pid}?region=VN",
                "kalodata_detail_url": f"https://www.kalodata.com/product/detail?id={pid}",
                "window_spec": window_spec,
                "window_range_label": range_label,
                "gmv_total_vnd": gmv_tot,
                "gmv_total_display": format_vnd_compact(gmv_tot),
                "gmv_growth_pct": round(growth_pct, 1) if growth_pct is not None else None,
                "units_sold_window": int(round(sold_num)) if sold_num is not None else None,
                "rating": round(rating_val, 2) if rating_val is not None else None,
                "aov_vnd": round(aov_vnd, 0) if aov_vnd is not None else None,
                "shipping_fee_vnd": round(ship_vnd, 0) if ship_vnd is not None else None,
                "commission_pct": round(comm_pct, 2) if comm_pct is not None else None,
                "active_creators_count": int(round(creators_cnt)) if creators_cnt is not None else None,
                "launch_date": launch_raw if re.match(r"^\d{4}-\d{2}-\d{2}$", launch_raw) else "",
                "creator_conversion_rate_pct": round(cr_conv_pct, 2) if cr_conv_pct is not None else None,
                "live_gmv_vnd": live_gmv,
                "live_gmv_display": format_vnd_compact(live_gmv),
                "video_gmv_vnd": vid_gmv,
                "video_gmv_display": format_vnd_compact(vid_gmv),
                "mall_card_gmv_vnd": mall_gmv,
                "mall_card_gmv_display": format_vnd_compact(mall_gmv),
                "top_video_ids": [x["video_id"] for x in top_vids],
                "top_videos_preview": top_vids,
                "no_linked_videos_explicit": no_vid_explicit,
                "category_id": category_meta["id"] if category_meta else "",
                "category_label_vi": category_meta["vi"] if category_meta else "",
                "industry_key": category_meta["industry_key"] if category_meta else "",
                "keyword": clean_kw or (category_meta["vi"] if category_meta else ""),
            }
            p_item["classification"] = classify_kalodata_hunted_product(p_item)
            products_out.append(p_item)

        return products_out, range_label

    def scrape_kalodata_videos(
        self,
        keyword: str = "",
        *,
        category_meta: dict | None = None,
        window_spec: str = "7d",
        limit: int = 15,
    ) -> tuple[list[dict], list[dict]]:
        clean_kw = str(keyword or "").strip().lstrip("#").strip()
        cate_q = build_kalodata_cate_value_query(category_meta)
        target_url = f"{KALODATA_VIDEO_URL}?cateValue={cate_q}" if cate_q else KALODATA_VIDEO_URL
        port, ws = self._ensure_kalodata_tab(target_url)
        try:
            if not category_meta:
                self._reset_stale_filters_if_no_category(port, ws)
            self._select_window_if_needed(port, ws, window_spec)
            if clean_kw:
                self._run_ime_safe_search(port, ws, clean_kw)
            raw = self._collect_paginated_table_rows(port, ws, limit=max(1, min(1000, int(limit))))
        finally:
            if clean_kw:
                self._clear_search_box(port, ws)

        ths = raw.get("ths") or []
        idx_content = self._col_idx(ths, ("视频内容", "video"), 1)
        idx_creator = self._col_idx(ths, ("达人信息", "creator"), 2)
        idx_gmv = self._col_idx(ths, ("成交金额", "revenue"), 3)
        idx_sold = self._col_idx(ths, ("销量", "items sold"), 5)
        idx_views = self._col_idx(ths, ("观看次数", "views"), 7)
        idx_gpm = self._col_idx(ths, ("千次观看成交金额", "gpm"), 9)
        idx_cpa = self._col_idx(ths, ("单次成交广告成本", "cpa"), 10)
        idx_ad_share = self._col_idx(ths, ("广告观看占比", "ad view"), 11)
        idx_ad_spend = self._col_idx(ths, ("广告消耗", "ad spend"), 12)
        idx_roas = self._col_idx(ths, ("广告roas", "roas"), 13)
        idx_pub = self._col_idx(ths, ("发布日期", "publish"), 14)

        videos_out: list[dict] = []
        creators_by_h: dict[str, dict] = {}
        for idx, r in enumerate(raw.get("rows") or [], start=1):
            tds = r.get("tds") or []
            img_urls = [m.group(0) for im in (r.get("bgImgs") or []) if (m := URL_EXTRACT_RE.search(str(im)))]
            vid = str(r.get("rowKey") or "").strip()
            v_cover = ""
            cid = ""
            c_avatar = ""
            linked_pid = ""
            for u in img_urls:
                mv = VID_FROM_IMG_RE.search(u)
                if mv:
                    vid = vid or mv.group(1)
                    v_cover = v_cover or u
                mc = CID_FROM_IMG_RE.search(u)
                if mc and not cid:
                    cid = mc.group(1)
                    c_avatar = u
                mp = PID_FROM_IMG_RE.search(u)
                if mp and not linked_pid:
                    linked_pid = mp.group(1)
            if not vid:
                continue

            v_info = split_kalodata_video_content_cell(tds[idx_content] if idx_content < len(tds) else "")
            cr_txt = tds[idx_creator] if idx_creator < len(tds) else ""
            m_cr = CREATOR_CELL_RE.search(cr_txt)
            handle = m_cr.group(1).strip() if m_cr else ""
            flw_val = parse_kalodata_count_or_float(m_cr.group(2)) if (m_cr and m_cr.group(2)) else None
            flw_int = int(round(flw_val)) if flw_val is not None else None

            vgmv = parse_kalodata_money_vnd(tds[idx_gmv] if idx_gmv < len(tds) else "")
            vsold = parse_kalodata_count_or_float(tds[idx_sold] if idx_sold < len(tds) else "")
            vviews = parse_kalodata_count_or_float(tds[idx_views] if idx_views < len(tds) else "")
            vgpm = parse_kalodata_money_vnd(tds[idx_gpm] if idx_gpm < len(tds) else "")
            vcpa = parse_kalodata_money_vnd(tds[idx_cpa] if idx_cpa < len(tds) else "")
            vad_share = parse_kalodata_count_or_float(tds[idx_ad_share] if idx_ad_share < len(tds) else "")
            vad_spend = parse_kalodata_money_vnd(tds[idx_ad_spend] if idx_ad_spend < len(tds) else "")
            vroas = parse_kalodata_count_or_float(tds[idx_roas] if idx_roas < len(tds) else "")
            pub_raw = (tds[idx_pub] if idx_pub < len(tds) else "").replace("/", "-")

            v_url = f"https://www.tiktok.com/@{handle or '_'}/video/{vid}"
            v_item = {
                "rank": idx,
                "native_video_id": safe_id_str(vid),
                "video_url": v_url,
                "kalodata_url": f"https://www.kalodata.com/video/detail?id={vid}",
                "cover_image_url": v_cover,
                "duration_label": v_info["duration_label"],
                "duration_sec": v_info["duration_sec"],
                "caption": v_info["caption"],
                "hashtags": v_info["hashtags"],
                "is_ad": v_info["is_ad"] or bool(vad_share and vad_share > 0),
                "author_handle": handle,
                "native_creator_id": cid,
                "creator_avatar_url": c_avatar,
                "creator_followers_count": flw_int,
                "linked_product_id": linked_pid,
                "window_spec": window_spec,
                "video_gmv_vnd": vgmv,
                "video_gmv_display": format_vnd_compact(vgmv),
                "video_orders_count": int(round(vsold)) if vsold is not None else None,
                "views_count": int(round(vviews)) if vviews is not None else None,
                "video_gpm_vnd": vgpm,
                "video_gpm_display": format_vnd_compact(vgpm),
                "cpa_ad_cost_vnd": vcpa,
                "ad_views_share_pct": round(vad_share, 2) if vad_share is not None else None,
                "ad_spend_vnd": vad_spend,
                "ad_roas": round(vroas, 2) if vroas is not None else None,
                "published_at": pub_raw,
                "keyword": clean_kw or (category_meta["vi"] if category_meta else ""),
            }
            v_item["classification"] = classify_kalodata_hunted_video(v_item)
            videos_out.append(v_item)

            if handle:
                hl = handle.lower()
                c_acc = creators_by_h.setdefault(
                    hl,
                    {
                        "handle": handle,
                        "native_creator_id": cid,
                        "avatar_url": c_avatar,
                        "followers_count": flw_int,
                        "videos_in_niche_count": 0,
                        "sum_video_gmv_vnd": 0.0,
                        "sum_orders_count": 0,
                        "sum_views_count": 0,
                        "keyword": clean_kw or (category_meta["vi"] if category_meta else ""),
                    },
                )
                c_acc["videos_in_niche_count"] += 1
                if vgmv is not None:
                    c_acc["sum_video_gmv_vnd"] += vgmv
                if vsold is not None:
                    c_acc["sum_orders_count"] += int(round(vsold))
                if vviews is not None:
                    c_acc["sum_views_count"] += int(round(vviews))

        creators_out = []
        for c_acc in creators_by_h.values():
            vw = c_acc["sum_views_count"]
            gm = round(c_acc["sum_video_gmv_vnd"], 2)
            agg_gpm = round((gm / vw) * 1000.0, 2) if vw > 0 else None
            creators_out.append(
                {
                    **c_acc,
                    "sum_video_gmv_vnd": gm,
                    "sum_video_gmv_display": format_vnd_compact(gm),
                    "niche_video_gpm_vnd": agg_gpm,
                    "niche_video_gpm_display": format_vnd_compact(agg_gpm),
                }
            )
        creators_out.sort(key=lambda x: x["sum_video_gmv_vnd"], reverse=True)
        return videos_out, creators_out

    def scrape_kalodata_categories_leaderboard(self, *, window_spec: str = "7d", limit: int = 25) -> dict:
        if self.custom_scraper is not None:
            return self.custom_scraper("categories_leaderboard", window_spec=window_spec, limit=limit)
        win = window_spec if window_spec in ("7d", "30d", "90d") else "7d"
        with self._lock_ref():
            port, ws = self._ensure_kalodata_tab(KALODATA_CATEGORY_LIST_URL, require_search_input=False)
            self._select_window_if_needed(port, ws, win)
            raw = cdp_ws_eval(
                port,
                ws,
                f"""(() => {{
                  const ths = Array.from(document.querySelectorAll("table thead th")).map(th => (th.innerText || "").replace(/\\s+/g, " ").trim());
                  const trs = Array.from(document.querySelectorAll("table tbody tr:not(.ant-table-measure-row)"))
                    .filter(r => r.querySelectorAll("td").length >= 8)
                    .slice(0, {max(5, min(50, int(limit)))});
                  const rows = trs.map(tr => {{
                    const fk = Object.keys(tr).find(k => k.startsWith("__reactFiber"));
                    let cur = fk ? tr[fk] : null, rowKey = "";
                    for (let d = 0; d < 14 && cur; d++) {{
                      if (cur.key && /^\\d{{4,12}}$/.test(String(cur.key))) {{ rowKey = String(cur.key); break; }}
                      cur = cur.return;
                    }}
                    const tds = Array.from(tr.querySelectorAll("td")).map(td => (td.innerText || "").replace(/\\s+/g, " ").trim());
                    return {{rowKey, tds}};
                  }});
                  return JSON.stringify({{ths, rows}});
                }})()""",
            )

        ths = raw.get("ths") or []
        idx_name = self._col_idx(ths, ("类目", "category"), 1)
        idx_gmv = self._col_idx(ths, ("成交金额", "revenue"), 2)
        idx_growth = self._col_idx(ths, ("增长率", "growth"), 4)
        idx_trend = self._col_idx(ths, ("成交趋势", "trend"), 5)
        idx_shops = self._col_idx(ths, ("店铺数量", "shops"), 6)
        idx_avg_shop = self._col_idx(ths, ("店均成交", "avg"), 7)
        idx_lvl = self._col_idx(ths, ("类目等级", "level"), 8)
        idx_top3 = self._col_idx(ths, ("top 3", "top3"), 9)
        idx_top10 = self._col_idx(ths, ("top 10", "top10"), 10)
        idx_aff = self._col_idx(ths, ("联盟成交", "affiliate"), 12)
        idx_live = self._col_idx(ths, ("直播成交", "live"), 14)
        idx_vid = self._col_idx(ths, ("视频成交", "video"), 15)

        trend_hdr = ths[idx_trend] if idx_trend < len(ths) else ""
        m_rng = re.search(r"\(([^)]+)\)", trend_hdr)
        range_lbl = m_rng.group(1).strip() if m_rng else win

        items_out: list[dict] = []
        for idx, r in enumerate(raw.get("rows") or [], start=1):
            tds = r.get("tds") or []
            cid = str(r.get("rowKey") or "").strip()
            zh_name = (tds[idx_name] if idx_name < len(tds) else "").strip()
            known = _CAT_BY_ID.get(cid) or _CAT_BY_ZH.get(zh_name)
            gmv_tot = parse_kalodata_money_vnd(tds[idx_gmv] if idx_gmv < len(tds) else "")
            aff_gmv = parse_kalodata_money_vnd(tds[idx_aff] if idx_aff < len(tds) else "")
            vid_gmv = parse_kalodata_money_vnd(tds[idx_vid] if idx_vid < len(tds) else "")
            live_gmv = parse_kalodata_money_vnd(tds[idx_live] if idx_live < len(tds) else "")
            aff_pct = round((aff_gmv / gmv_tot) * 100.0, 1) if (aff_gmv is not None and gmv_tot and gmv_tot > 0) else None
            vid_pct = round((vid_gmv / gmv_tot) * 100.0, 1) if (vid_gmv is not None and gmv_tot and gmv_tot > 0) else None
            items_out.append(
                {
                    "rank": idx,
                    "category_id": cid or (known["id"] if known else ""),
                    "category_name_zh": zh_name,
                    "category_name_vi": known["vi"] if known else zh_name,
                    "icon": known["icon"] if known else "📂",
                    "industry_key": known["industry_key"] if known else "khac",
                    "level": (tds[idx_lvl] if idx_lvl < len(tds) else "") or (known["level"] if known else ""),
                    "gmv_total_vnd": gmv_tot,
                    "gmv_total_display": format_vnd_compact(gmv_tot),
                    "gmv_growth_pct": parse_kalodata_count_or_float(tds[idx_growth] if idx_growth < len(tds) else ""),
                    "active_shops_count": int(round(parse_kalodata_count_or_float(tds[idx_shops] if idx_shops < len(tds) else "") or 0)) or None,
                    "avg_shop_gmv_vnd": parse_kalodata_money_vnd(tds[idx_avg_shop] if idx_avg_shop < len(tds) else ""),
                    "top3_shops_share_pct": parse_kalodata_count_or_float(tds[idx_top3] if idx_top3 < len(tds) else ""),
                    "top10_shops_share_pct": parse_kalodata_count_or_float(tds[idx_top10] if idx_top10 < len(tds) else ""),
                    "affiliate_gmv_vnd": aff_gmv,
                    "affiliate_gmv_display": format_vnd_compact(aff_gmv),
                    "affiliate_share_pct": aff_pct,
                    "live_gmv_vnd": live_gmv,
                    "video_gmv_vnd": vid_gmv,
                    "video_gmv_display": format_vnd_compact(vid_gmv),
                    "video_share_pct": vid_pct,
                }
            )
        return {
            "ok": True,
            "module": "category_board",
            "window_spec": win,
            "window_range_label": range_lbl,
            "items_count": len(items_out),
            "items": items_out,
        }

    def persist_kalodata_to_vault(
        self,
        products: list[dict],
        videos: list[dict],
        creators: list[dict],
        shops_list: list[dict],
        *,
        auto_ingest_suitable: bool = True,
        ingest_all: bool = False,
        use_300desk: bool = False,
        score_jev: bool = True,
        jev_limit: int = 12,
    ) -> dict:
        saved_pids: list[int] = []
        saved_creators = 0
        saved_videos = 0
        saved_shops = 0
        ts = now()

        if auto_ingest_suitable or ingest_all:
            for p in products:
                cls_info = p.get("classification") or {}
                if not ingest_all and not cls_info.get("suitable_for_system", True):
                    continue
                db_item = self.products.upsert_product(
                    {
                        "platform": "tiktok_shop",
                        "market": "VN",
                        "native_product_id": p.get("native_product_id") or "",
                        "title": p.get("product_title") or "",
                        "url": p.get("canonical_url") or "",
                        "image_url": p.get("cover_image_url") or "",
                        "price_vnd": float(p.get("price_vnd") or 0.0),
                        "sold_count": int(p.get("units_sold_window") or 0),
                        "sold_30d": int(p.get("units_sold_window") or 0),
                        "gmv_vnd": float(p.get("gmv_total_vnd") or 0.0),
                        "rating": float(p.get("rating") or 0.0),
                        "industry": p.get("industry_key") or infer_industry(p.get("product_title") or ""),
                        "kalodata": {
                            "window_spec": p.get("window_spec"),
                            "gmv_total_vnd": p.get("gmv_total_vnd"),
                            "video_gmv_vnd": p.get("video_gmv_vnd"),
                            "live_gmv_vnd": p.get("live_gmv_vnd"),
                            "commission_pct": p.get("commission_pct"),
                            "active_creators_count": p.get("active_creators_count"),
                            "gmv_growth_pct": p.get("gmv_growth_pct"),
                            "kalodata_detail_url": p.get("kalodata_detail_url"),
                            "suitability_label": cls_info.get("suitability_label"),
                        },
                    },
                    source=f"kalodata_vn:{p.get('window_spec') or '7d'}:{p.get('keyword') or 'hunt'}",
                )
                db_pid = int(db_item["id"])
                p["vault_product_id"] = db_pid
                if db_pid not in saved_pids:
                    saved_pids.append(db_pid)
                rec_bucket = cls_info.get("recommended_vault_bucket") or ""
                with self.connect() as conn:
                    if rec_bucket in ("viral", "moi_noi") and db_item.get("bucket") == "cho_danh_gia":
                        conn.execute("UPDATE products SET bucket=?, updated_at=? WHERE id=?", (rec_bucket, ts, db_pid))
                    conn.execute(
                        """
                        INSERT INTO product_metric_history
                        (product_id, source, price_vnd, sold_count, sold_7d, gmv_vnd, gmv_7d_vnd, rating, recorded_at)
                        VALUES (?, 'kalodata_vn', ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            db_pid,
                            float(p.get("price_vnd") or 0.0),
                            int(p.get("units_sold_window") or 0),
                            int(p.get("units_sold_window") or 0) if p.get("window_spec") == "7d" else None,
                            float(p.get("gmv_total_vnd") or 0.0),
                            float(p.get("gmv_total_vnd") or 0.0) if p.get("window_spec") == "7d" else None,
                            p.get("rating"),
                            ts,
                        ),
                    )

        with self.connect() as conn:
            for c in creators[:1000]:
                h = str(c.get("handle") or "").strip().lstrip("@")
                if not h:
                    continue
                cid = f"kalo_cr_{h.lower()}"
                conn.execute(
                    """
                    INSERT INTO creator_leads
                    (creator_id, platform, market, handle, display_name, followers, industry, video_gmv_vnd, avg_views, top_videos_json, note, created_at, updated_at)
                    VALUES (?, 'tiktok', 'VN', ?, ?, ?, ?, ?, ?, '[]', ?, ?, ?)
                    ON CONFLICT(creator_id) DO UPDATE SET
                        followers=MAX(creator_leads.followers, excluded.followers),
                        video_gmv_vnd=MAX(creator_leads.video_gmv_vnd, excluded.video_gmv_vnd),
                        avg_views=MAX(creator_leads.avg_views, excluded.avg_views),
                        note=excluded.note,
                        updated_at=excluded.updated_at
                    """,
                    (
                        cid,
                        h,
                        f"@{h}",
                        int(c.get("followers_count") or 0),
                        infer_industry(str(c.get("keyword") or "")),
                        float(c.get("sum_video_gmv_vnd") or c.get("gmv_vnd") or 0.0),
                        int(c.get("sum_views_count") or 0),
                        f"Kalodata VN · GPM {c.get('niche_video_gpm_display') or '—'}",
                        ts,
                        ts,
                    ),
                )
                saved_creators += 1

            for v in videos[:1000]:
                vid = str(v.get("native_video_id") or v.get("video_id") or "").strip()
                if not vid:
                    continue
                vkey = f"tiktok:{vid}"
                conn.execute(
                    """
                    INSERT INTO video_reviews
                    (video_key, platform, video_url, author_handle, is_important, record, created_at, updated_at)
                    VALUES (?, 'tiktok', ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(video_key) DO UPDATE SET
                        video_url=excluded.video_url,
                        author_handle=excluded.author_handle,
                        record=excluded.record,
                        updated_at=excluded.updated_at
                    """,
                    (
                        vkey,
                        str(v.get("video_url") or v.get("tiktok_url") or ""),
                        str(v.get("author_handle") or v.get("handle") or ""),
                        1 if (v.get("classification") or {}).get("suitability_key") in ("organic_high_gpm", "winning_ad_roas") else 0,
                        json.dumps(v, ensure_ascii=False),
                        ts,
                        ts,
                    ),
                )
                saved_videos += 1

            for sh in shops_list[:500]:
                sname = str(sh.get("shop_name") or "").strip()
                nsid = str(sh.get("native_shop_id") or sh.get("shop_id") or "").strip()
                if not sname and not nsid:
                    continue
                sid = f"kalo_shop_{nsid or uuid.uuid5(uuid.NAMESPACE_DNS, sname.lower()).hex[:10]}"
                conn.execute(
                    """
                    INSERT INTO shops
                    (shop_id, role, platform, market, native_shop_id, handle, shop_name, shop_url, industry, status, stats_json, note, created_at, updated_at)
                    VALUES (?, 'competitor_shop', 'tiktok_shop', 'VN', ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
                    ON CONFLICT(shop_id) DO UPDATE SET
                        shop_name=excluded.shop_name,
                        stats_json=excluded.stats_json,
                        note=excluded.note,
                        updated_at=excluded.updated_at
                    """,
                    (
                        sid,
                        nsid,
                        sname[:80],
                        sname[:140],
                        str(sh.get("kalodata_shop_url") or sh.get("kalodata_url") or ""),
                        infer_industry(sname),
                        json.dumps(sh, ensure_ascii=False),
                        f"Kalodata Shop · GMV {sh.get('gmv_total_display') or sh.get('gmv_display') or '—'}",
                        ts,
                        ts,
                    ),
                )
                saved_shops += 1

        desk300_nnn = ""
        jev_scored_cnt = 0
        target_pids = saved_pids[: max(0, min(25, int(jev_limit or 12)))]
        if use_300desk and self.desk_pipeline is not None and target_pids:
            try:
                d_run = self.desk_pipeline.process_single_or_batch_sync(
                    product_ids=target_pids,
                    mode="vault_process",
                    exec_engine="gateway_fast",
                    auto_assign_my_shop=True,
                )
                desk300_nnn = str(d_run.get("nnn_code") or "")
                jev_scored_cnt = len(d_run.get("output_product_ids") or [])
            except Exception:
                use_300desk = False

        if score_jev and not use_300desk and target_pids:
            for db_pid in target_pids:
                try:
                    self.products.score_product_jev(db_pid)
                    jev_scored_cnt += 1
                except Exception:
                    break

        return {
            "saved_product_ids": saved_pids,
            "saved_creators_count": saved_creators,
            "saved_videos_count": saved_videos,
            "saved_shops_count": saved_shops,
            "desk300_nnn": desk300_nnn,
            "jev_scored_count": jev_scored_cnt,
        }

    def run_kalodata_vn_hunt(
        self,
        *,
        keywords: list[str] | None = None,
        category_id: str = "",
        window_spec: str = "7d",
        limit_products: int = 20,
        limit_videos: int = 15,
        fetch_all: bool = False,
        include_videos: bool = True,
        auto_ingest_suitable: bool = True,
        ingest_all: bool = False,
        use_300desk: bool = False,
        score_jev: bool = True,
        jev_limit: int = 12,
    ) -> dict:
        if fetch_all or int(limit_products or 0) >= 500:
            limit_products = 1000 if fetch_all else max(500, int(limit_products or 1000))
            limit_videos = 1000 if fetch_all else max(500, int(limit_videos or 500))
            ingest_all = True
        clean_kws = [str(k).strip() for k in (keywords or []) if str(k).strip()][:8]
        cat_meta = resolve_kalodata_category(category_id) if str(category_id or "").strip() else None
        if not clean_kws and not cat_meta:
            raise ApiError("400 Bad Request", "Vui lòng chọn ít nhất 1 Ngành hàng Kalodata VN hoặc nhập Từ khoá cần quét.")

        win = window_spec if window_spec in ("7d", "30d", "90d") else "7d"
        all_products: list[dict] = []
        all_videos: list[dict] = []
        all_creators: list[dict] = []
        all_shops: list[dict] = []
        range_label = win

        if self.custom_scraper is not None:
            mock_res = self.custom_scraper(
                "hunt",
                keywords=clean_kws,
                category_meta=cat_meta,
                window_spec=win,
                limit_products=limit_products,
                limit_videos=limit_videos,
                include_videos=include_videos,
            )
            all_products = list(mock_res.get("products") or [])
            all_videos = list(mock_res.get("videos") or [])
            all_creators = list(mock_res.get("creators") or [])
            all_shops = list(mock_res.get("shops") or [])
            for p in all_products:
                if "classification" not in p:
                    p["classification"] = classify_kalodata_hunted_product(p)
            for v in all_videos:
                if "classification" not in v:
                    v["classification"] = classify_kalodata_hunted_video(v)
        else:
            with self._lock_ref():
                search_targets = clean_kws if clean_kws else [""]
                for kw in search_targets:
                    prods, rng = self.scrape_kalodata_products(
                        kw,
                        category_meta=cat_meta,
                        window_spec=win,
                        limit=limit_products,
                    )
                    range_label = rng or range_label
                    seen_p = {x["native_product_id"] for x in all_products}
                    for pr in prods:
                        if pr["native_product_id"] not in seen_p:
                            seen_p.add(pr["native_product_id"])
                            all_products.append(pr)
                    if include_videos:
                        vids, crs = self.scrape_kalodata_videos(
                            kw,
                            category_meta=cat_meta,
                            window_spec=win,
                            limit=limit_videos,
                        )
                        seen_v = {x["native_video_id"] for x in all_videos}
                        for vd in vids:
                            if vd["native_video_id"] not in seen_v:
                                seen_v.add(vd["native_video_id"])
                                all_videos.append(vd)
                        seen_c = {x["handle"].lower() for x in all_creators}
                        for cr in crs:
                            if cr["handle"].lower() not in seen_c:
                                seen_c.add(cr["handle"].lower())
                                all_creators.append(cr)

        persisted = self.persist_kalodata_to_vault(
            all_products,
            all_videos,
            all_creators,
            all_shops,
            auto_ingest_suitable=auto_ingest_suitable,
            ingest_all=ingest_all,
            use_300desk=use_300desk,
            score_jev=score_jev,
            jev_limit=jev_limit,
        )

        suitable_cnt = sum(1 for p in all_products if (p.get("classification") or {}).get("suitable_for_system"))
        breakdown: dict[str, int] = {}
        for p in all_products:
            sk = (p.get("classification") or {}).get("suitability_key") or "unknown"
            breakdown[sk] = breakdown.get(sk, 0) + 1

        run_id = f"klh_{uuid.uuid4().hex[:12]}"
        ts = now()
        hunt_mode = "category_and_keyword" if (cat_meta and clean_kws) else ("category_only" if cat_meta else "keyword_only")
        payload = {
            "ok": True,
            "run_id": run_id,
            "hunt_mode": hunt_mode,
            "category_id": cat_meta["id"] if cat_meta else "",
            "category_label_vi": cat_meta["vi"] if cat_meta else "",
            "keywords": clean_kws,
            "display_targets": ([f"{cat_meta['icon']} {cat_meta['vi']}"] if cat_meta else []) + clean_kws,
            "market": "VN",
            "window_spec": win,
            "window_range_label": range_label,
            "products_count": len(all_products),
            "suitable_products_count": suitable_cnt,
            "suitability_breakdown": breakdown,
            "videos_count": len(all_videos),
            "shops_count": len(all_shops),
            "creators_count": len(all_creators),
            "saved_product_ids": persisted["saved_product_ids"],
            "videos_saved_count": persisted["saved_videos_count"],
            "creators_saved_count": persisted["saved_creators_count"],
            "shops_saved_count": persisted["saved_shops_count"],
            "desk300_nnn": persisted["desk300_nnn"],
            "jev_scored": bool(score_jev),
            "jev_scored_count": persisted["jev_scored_count"],
            "cost_usd": 0.0,
            "products": all_products,
            "videos": all_videos,
            "shops": all_shops,
            "creators": all_creators,
            "created_at": ts,
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO kalodata_hunt_runs
                (run_id, keywords_json, category_id, market, window_spec, include_videos,
                 products_total, products_suitable, videos_total, creators_total,
                 saved_product_ids_json, saved_creators_count, jev_scored, desk300_nnn, cost_usd, result_json, created_at)
                VALUES (?, ?, ?, 'VN', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, ?, ?)
                """,
                (
                    run_id,
                    json.dumps(payload["display_targets"], ensure_ascii=False),
                    payload["category_id"],
                    win,
                    1 if include_videos else 0,
                    len(all_products),
                    suitable_cnt,
                    len(all_videos),
                    len(all_creators),
                    json.dumps(persisted["saved_product_ids"]),
                    persisted["saved_creators_count"],
                    persisted["jev_scored_count"],
                    persisted["desk300_nnn"],
                    json.dumps(payload, ensure_ascii=False),
                    ts,
                ),
            )
        return payload

    def list_runs(self, limit: int = 20) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT run_id, keywords_json, category_id, window_spec, products_total, products_suitable, "
                "videos_total, creators_total, jev_scored, desk300_nnn, cost_usd, created_at "
                "FROM kalodata_hunt_runs ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (max(1, min(50, int(limit))),),
            ).fetchall()
        return [
            {
                "run_id": r["run_id"],
                "keywords": json.loads(r["keywords_json"] or "[]"),
                "category_id": r["category_id"],
                "window_spec": r["window_spec"],
                "products_total": r["products_total"],
                "products_suitable": r["products_suitable"],
                "videos_total": r["videos_total"],
                "creators_total": r["creators_total"],
                "jev_scored": r["jev_scored"],
                "desk300_nnn": r["desk300_nnn"],
                "cost_usd": r["cost_usd"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def get_run(self, run_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT result_json FROM kalodata_hunt_runs WHERE run_id=?", (run_id,)).fetchone()
        if not row:
            return None
        return json.loads(row["result_json"] or "{}")

    def export_run_csv(self, run_id: str) -> tuple[str, Raw]:
        run = self.get_run(run_id)
        if not run:
            raise ApiError("404 Not Found", f"Không tìm thấy phiên quét {run_id}")
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([
            "rank", "native_product_id", "product_title", "price_vnd", "gmv_total_vnd", "gmv_total_display",
            "gmv_growth_pct", "units_sold_window", "video_gmv_vnd", "live_gmv_vnd", "mall_card_gmv_vnd",
            "commission_pct", "active_creators_count", "creator_conversion_rate_pct", "rating", "launch_date",
            "suitability_label", "canonical_url", "kalodata_detail_url",
        ])
        for p in run.get("products") or []:
            w.writerow([
                p.get("rank"),
                safe_csv_cell(p.get("native_product_id")),
                safe_csv_cell(p.get("product_title")),
                p.get("price_vnd"),
                p.get("gmv_total_vnd"),
                safe_csv_cell(p.get("gmv_total_display")),
                p.get("gmv_growth_pct"),
                p.get("units_sold_window"),
                p.get("video_gmv_vnd"),
                p.get("live_gmv_vnd"),
                p.get("mall_card_gmv_vnd"),
                p.get("commission_pct"),
                p.get("active_creators_count"),
                p.get("creator_conversion_rate_pct"),
                p.get("rating"),
                safe_csv_cell(p.get("launch_date")),
                safe_csv_cell((p.get("classification") or {}).get("suitability_label")),
                safe_csv_cell(p.get("canonical_url")),
                safe_csv_cell(p.get("kalodata_detail_url")),
            ])
        data = buf.getvalue().encode("utf-8-sig")
        return "200 OK", Raw(data, [("Content-Type", "text/csv; charset=utf-8"), ("Content-Disposition", f'attachment; filename="{run_id}_kalodata_products.csv"')])

    def dispatch(self, path: str, method: str, env, read_json):
        if path == "/api/hunt/kalodata-vn/categories" and method == "GET":
            return "200 OK", {"items": self.list_categories_catalog()}
        if path in ("/api/hunt/kalodata-vn/categories-leaderboard", "/api/hunt/kalodata-vn/category-leaderboard"):
            if method == "GET":
                qs = parse_qs(env.get("QUERY_STRING") or "")
                win = (qs.get("window_spec") or ["7d"])[0]
                lim = int((qs.get("limit") or ["25"])[0])
                return "200 OK", self.scrape_kalodata_categories_leaderboard(window_spec=win, limit=lim)
            if method == "POST":
                b = json_object(read_json, env)
                return "200 OK", self.scrape_kalodata_categories_leaderboard(
                    window_spec=str(b.get("window_spec") or "7d"),
                    limit=int(b.get("limit") or 25),
                )
        if path == "/api/hunt/kalodata-vn" and method == "POST":
            b = json_object(read_json, env)
            raw_kws = b.get("keywords")
            if isinstance(raw_kws, str):
                kws = [s.strip() for s in re.split(r"[\n,;]+", raw_kws) if s.strip()]
            elif isinstance(raw_kws, list):
                kws = [str(s).strip() for s in raw_kws if str(s).strip()]
            else:
                kws = []
            lim_p = int(b.get("limit_products") or 20)
            lim_v = int(b.get("limit_videos") or (lim_p if lim_p >= 100 else 15))
            return "200 OK", self.run_kalodata_vn_hunt(
                keywords=kws,
                category_id=str(b.get("category_id") or ""),
                window_spec=str(b.get("window_spec") or "7d"),
                limit_products=lim_p,
                limit_videos=lim_v,
                fetch_all=bool(b.get("fetch_all", False)),
                include_videos=bool(b.get("include_videos", True)),
                auto_ingest_suitable=bool(b.get("auto_ingest_suitable", True)),
                ingest_all=bool(b.get("ingest_all", False)),
                use_300desk=bool(b.get("use_300desk", False)),
                score_jev=bool(b.get("score_jev", True)),
                jev_limit=int(b.get("jev_limit") or 12),
            )
        if path == "/api/hunt/kalodata-vn/history" and method == "GET":
            return "200 OK", {"items": self.list_runs(limit=25)}
        if path.startswith("/api/hunt/kalodata-vn/") and path.endswith("/export.csv") and method == "GET":
            rid = path.split("/")[4]
            return self.export_run_csv(rid)
        if path.startswith("/api/hunt/kalodata-vn/") and method == "GET":
            rid = path.rsplit("/", 1)[-1].strip()
            if rid and rid not in ("categories", "history", "categories-leaderboard", "category-leaderboard"):
                run = self.get_run(rid)
                if not run:
                    return "404 Not Found", {"detail": "Không tìm thấy phiên quét Kalodata VN"}
                return "200 OK", run
        return None
