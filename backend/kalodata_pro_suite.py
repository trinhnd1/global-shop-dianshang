"""Kalodata Pro Full-Suite Intelligence Service for Global Shop Dianshang (`$0.00` via Dedicated Chrome CDP).

Unlocks ALL 9 authenticated pages of a paid Kalodata account over `peng_dedicated` (`127.0.0.1:9339`):
1. `/shop` — Competitor Shop Leaderboard & Affiliate-Friendly Shop Hunter (`scrape_shops`) -> syncs to `shops`
2. `/brand` — Brand Market Share, Ad Spend & Concentration Radar (`scrape_brands`)
3. `/creator` — Direct KOC/Creator Hunter with Bio Phone/Zalo/Email Extraction (`scrape_creators`) -> syncs to `creator_leads`
4. `/livestream` — High-Converting Livestream Room Radar (`scrape_livestreams`)
5. `/video` — AI-Video (`ai_video`), High-ROAS Ads & Low-Follower Viral Video Hunter (`scrape_videos_advanced`) -> syncs to `video_reviews`
6. `/category` — Full VN Category Leaderboard (via `hunter.scrape_kalodata_categories_leaderboard`)
7. `/product/detail?id=...` — Deep Product Dossier (Channel Split %, AI Selling Points, SKU Stock, Top 10 Creators & Top Videos)
8. `/video/detail?id=...` — Deep Video & Ad Dossier + Direct Zero-Watermark CDN `.mp4` (`live.kalocdn.com/video/<id>.mp4`) for `$0.00` Clone!
9. `/creator/detail?id=...` — Deep Creator Dossier (Video vs Live Share %, AI Video Usage, Top Products & Shops)
"""
from __future__ import annotations

import json
import re
import time
from typing import Any
from urllib.parse import quote
import uuid

from .chrome_profile_hub import cdp_ws_eval
from .kalodata_hunter import (
    KALODATA_VN_CATEGORIES,
    build_kalodata_cate_value_query,
    format_vnd_compact,
    parse_kalodata_count_or_float,
    parse_kalodata_money_vnd,
    resolve_kalodata_category,
)
from .products import infer_industry
from .responses import ApiError, json_object, now, safe_id_str

KALODATA_SHOP_URL = "https://www.kalodata.com/shop"
KALODATA_BRAND_URL = "https://www.kalodata.com/brand"
KALODATA_CREATOR_URL = "https://www.kalodata.com/creator"
KALODATA_VIDEO_URL = "https://www.kalodata.com/video"
KALODATA_LIVESTREAM_URL = "https://www.kalodata.com/livestream"
KALODATA_PRODUCT_DETAIL_URL = "https://www.kalodata.com/product/detail?id={id}"
KALODATA_VIDEO_DETAIL_URL = "https://www.kalodata.com/video/detail?id={id}"

_VN_PHONE_RE = re.compile(r"(?:\+?84|0)(?:\d[\s.-]?){8,9}\d")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_DIGIT_ID_RE = re.compile(r"\b(\d{15,22})\b")
_DURATION_SEC_RE = re.compile(r"(?:(\d+)\s*m\s*)?(\d+(?:\.\d+)?)\s*s", re.IGNORECASE)


def extract_contacts_from_bio(signature: str) -> dict[str, Any]:
    """Extract Vietnamese phone/Zalo numbers and emails from a Creator's TikTok bio (`signature`)."""
    txt = str(signature or "")
    phones: list[str] = []
    for m in _VN_PHONE_RE.finditer(txt):
        digits = re.sub(r"[^\d+]", "", m.group(0))
        if digits.startswith("+84"):
            digits = "0" + digits[3:]
        if 10 <= len(digits) <= 11 and digits not in phones:
            phones.append(digits)
    emails: list[str] = []
    for em in _EMAIL_RE.finditer(txt):
        v = em.group(0).lower().lstrip(".-_+:")
        if v and "@" in v and v not in emails:
            emails.append(v)
    return {
        "phones_zalo": phones[:3],
        "emails": emails[:2],
        "has_contact": bool(phones or emails),
    }


def _parse_pct(val: Any) -> float | None:
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        f = float(val)
        return round(f * 100.0 if (0 < abs(f) <= 1.0) else f, 2)
    s = str(val).strip()
    if not s or s in ("-", "--", "***"):
        return None
    return parse_kalodata_count_or_float(s)


def _parse_int_or_count(val: Any) -> int | None:
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return int(round(float(val)))
    f = parse_kalodata_count_or_float(str(val))
    return int(round(f)) if f is not None else None


def _parse_dur_sec(val: Any) -> float:
    if isinstance(val, (int, float)):
        return round(float(val), 1)
    s = str(val or "").strip()
    m = _DURATION_SEC_RE.search(s)
    if m:
        mins = float(m.group(1) or 0.0)
        secs = float(m.group(2) or 0.0)
        return round(mins * 60.0 + secs, 1)
    try:
        return round(float(s), 1)
    except ValueError:
        return 0.0


def _decode_main_categories_vi(raw_cat: Any) -> list[str]:
    cat_by_id = {c["id"]: f"{c['icon']} {c['vi']}" for c in KALODATA_VN_CATEGORIES}
    cat_by_zh = {c["zh"]: f"{c['icon']} {c['vi']}" for c in KALODATA_VN_CATEGORIES}
    out: list[str] = []
    if isinstance(raw_cat, str):
        s = raw_cat.strip()
        if s in cat_by_zh:
            return [cat_by_zh[s]]
        if s.startswith("{"):
            try:
                obj = json.loads(s)
                for cid in (obj.get("pri_main_category") or []):
                    lbl = cat_by_id.get(str(cid), f"Ngành #{cid}")
                    if lbl not in out:
                        out.append(lbl)
                return out
            except ValueError:
                pass
        if s in cat_by_id:
            return [cat_by_id[s]]
        return [s] if s else []
    if isinstance(raw_cat, list):
        for item in raw_cat:
            parts = str(item).split("-")
            top_id = parts[0].strip()
            lbl = cat_by_id.get(top_id, str(item))
            if lbl and lbl not in out:
                out.append(lbl)
    return out


class KalodataProSuiteService:
    """High-speed TanStack Fiber + DOM Intelligence Extractor across all Kalodata Pro routes (`$0.00`)."""

    def __init__(self, connect, hunter, products=None, shops=None, custom_scraper=None):
        self.connect = connect
        self.hunter = hunter
        self.products = products
        self.shops = shops
        self.custom_scraper = custom_scraper

    def _save_snapshot(self, module_kind: str, target_query: str, window_spec: str, items_count: int, payload: dict) -> str:
        sid = f"kps_{uuid.uuid4().hex[:12]}"
        ts = now()
        payload["snapshot_id"] = sid
        payload["created_at"] = ts
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO kalodata_pro_snapshots
                (snap_id, module_kind, target_query, window_spec, items_count, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (sid, module_kind, str(target_query or "")[:160], str(window_spec or "7d"), int(items_count or 0), json.dumps(payload, ensure_ascii=False), ts),
            )
        return sid

    def _scrape_tanstack_route(
        self,
        base_url: str,
        *,
        keyword: str = "",
        category_id: str = "",
        window_spec: str = "7d",
        limit: int = 20,
        require_search_input: bool = False,
    ) -> dict[str, Any]:
        cat_meta = resolve_kalodata_category(category_id) if str(category_id or "").strip() else None
        cate_q = build_kalodata_cate_value_query(cat_meta) if cat_meta else ""
        target_url = f"{base_url}?cateValue={cate_q}" if cate_q else base_url
        clean_kw = str(keyword or "").strip().lstrip("#").strip()

        with self.hunter._lock_ref():
            port, ws = self.hunter._ensure_kalodata_tab(target_url, require_search_input=bool(clean_kw or require_search_input))
            try:
                if not cat_meta:
                    self.hunter._reset_stale_filters_if_no_category(port, ws)
                self.hunter._select_window_if_needed(port, ws, window_spec if window_spec in ("7d", "30d", "90d") else "7d")
                if clean_kw:
                    self.hunter._run_ime_safe_search(port, ws, clean_kw)
                else:
                    self.hunter._clear_search_box(port, ws, submit_reload=True)
                raw = self.hunter._collect_paginated_table_rows(port, ws, limit=max(1, min(2000, int(limit or 20))))
            finally:
                if clean_kw:
                    self.hunter._clear_search_box(port, ws)
        raw["category_meta"] = cat_meta
        return raw

    # 1. `/shop` — Competitor Shop & Affiliate-Friendly Shop Hunter
    def scrape_shops(
        self,
        *,
        keyword: str = "",
        category_id: str = "",
        window_spec: str = "7d",
        preset: str = "all",
        auto_save_vault: bool = True,
        limit: int = 25,
    ) -> dict[str, Any]:
        if self.custom_scraper is not None:
            raw = self.custom_scraper("shops", keyword=keyword, category_id=category_id, window_spec=window_spec, limit=limit)
        else:
            fetch_lim = min(1000, max(int(limit or 25), int(limit or 25) * 2 if preset != "all" else int(limit or 25)))
            raw = self._scrape_tanstack_route(
                KALODATA_SHOP_URL,
                keyword=keyword,
                category_id=category_id,
                window_spec=window_spec,
                limit=fetch_lim,
            )

        shops_out: list[dict[str, Any]] = []
        for idx, r in enumerate(raw.get("rows") or [], start=1):
            orig = r.get("rowOrig") if isinstance(r.get("rowOrig"), dict) else {}
            tds = r.get("tds") or []
            shop_id = safe_id_str(orig.get("id") or r.get("rowKey") or "")
            name = str(orig.get("name") or (tds[1] if len(tds) > 1 else "")).strip()
            seller_type = str(orig.get("seller_type") or ("BRAND" if "品牌" in (tds[1] if len(tds) > 1 else "") else "LOCAL")).upper()
            gmv = parse_kalodata_money_vnd(orig.get("revenue") if "revenue" in orig else (tds[2] if len(tds) > 2 else ""))
            aff_gmv = parse_kalodata_money_vnd(orig.get("affiliate_revenue"))
            self_gmv = parse_kalodata_money_vnd(orig.get("self_promotion_revenue"))
            vid_gmv = parse_kalodata_money_vnd(orig.get("video_revenue"))
            live_gmv = parse_kalodata_money_vnd(orig.get("live_revenue"))
            mall_gmv = parse_kalodata_money_vnd(orig.get("shopping_mall_revenue"))
            card_gmv = parse_kalodata_money_vnd(orig.get("showcase_revenue"))
            growth = _parse_pct(orig.get("revenue_grouping_rate"))
            sold = _parse_int_or_count(orig.get("sale"))
            aov = parse_kalodata_money_vnd(orig.get("unit_price"))
            aff_pct = round((aff_gmv / gmv) * 100.0, 1) if (gmv and gmv > 0 and aff_gmv is not None) else None
            vid_pct = round((vid_gmv / gmv) * 100.0, 1) if (gmv and gmv > 0 and vid_gmv is not None) else None
            trend = [round(float(x), 1) for x in (orig.get("revenue_trend") or [])[:30] if isinstance(x, (int, float))]

            if (aff_pct or 0) >= 35.0 and (vid_pct or 0) >= 20.0:
                strategy_tag = "💎 Mở Affiliate & Đẩy Video mạnh"
                strategy_key = "affiliate_video_heavy"
            elif (aff_pct or 0) >= 40.0:
                strategy_tag = "🤝 Mở Hoa Hồng Affiliate cao"
                strategy_key = "affiliate_open"
            elif (live_gmv or 0) > (vid_gmv or 0) * 2 and (gmv or 0) > 0:
                strategy_tag = "🔴 Shop thiên tự LIVE / KOC LIVE"
                strategy_key = "live_heavy"
            else:
                strategy_tag = "🏬 Shop Mall / Thẻ sản phẩm"
                strategy_key = "mall_self"

            if preset == "affiliate_video_heavy" and strategy_key not in ("affiliate_video_heavy", "affiliate_open"):
                continue
            if preset == "brand_shop" and seller_type != "BRAND":
                continue
            if preset == "surging" and (growth or 0.0) < 25.0:
                continue

            shops_out.append(
                {
                    "rank": int(orig.get("rank") or idx),
                    "shop_id": shop_id,
                    "shop_name": name,
                    "seller_type": seller_type,
                    "is_overseas": bool(orig.get("is_overseas")),
                    "categories_vi": _decode_main_categories_vi(orig.get("main_category")),
                    "gmv_vnd": gmv,
                    "gmv_display": format_vnd_compact(gmv) if gmv is not None else "—",
                    "growth_pct": growth,
                    "units_sold": sold,
                    "aov_vnd": aov,
                    "affiliate_gmv_vnd": aff_gmv,
                    "self_gmv_vnd": self_gmv,
                    "video_gmv_vnd": vid_gmv,
                    "live_gmv_vnd": live_gmv,
                    "mall_gmv_vnd": mall_gmv,
                    "showcase_gmv_vnd": card_gmv,
                    "affiliate_share_pct": aff_pct,
                    "video_share_pct": vid_pct,
                    "strategy_key": strategy_key,
                    "strategy_label_vi": strategy_tag,
                    "kalodata_url": f"https://www.kalodata.com/shop/detail?id={shop_id}" if shop_id else KALODATA_SHOP_URL,
                    "revenue_trend_30d": trend,
                }
            )
            if len(shops_out) >= int(limit or 25):
                break

        saved_shops = 0
        if auto_save_vault and shops_out:
            ts = now()
            with self.connect() as conn:
                for sh in shops_out:
                    sid_key = f"kalo_shop_{sh['shop_id'] or uuid.uuid5(uuid.NAMESPACE_DNS, (sh['shop_name'] or 'shop').lower()).hex[:10]}"
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
                            sid_key,
                            sh["shop_id"],
                            (sh["shop_name"] or "")[:80],
                            (sh["shop_name"] or f"Shop #{sh['shop_id']}")[:140],
                            sh["kalodata_url"],
                            infer_industry(sh["shop_name"] or keyword),
                            json.dumps(sh, ensure_ascii=False),
                            f"Kalodata Pro ({window_spec}) · GMV {sh['gmv_display']} · {sh['strategy_label_vi']}",
                            ts,
                            ts,
                        ),
                    )
                    saved_shops += 1

        payload = {
            "ok": True,
            "module": "shops",
            "keyword": keyword,
            "category_id": category_id,
            "window_spec": window_spec,
            "preset": preset,
            "items_count": len(shops_out),
            "saved_to_vault_count": saved_shops,
            "affiliate_friendly_count": sum(1 for s in shops_out if s["strategy_key"] in ("affiliate_video_heavy", "affiliate_open")),
            "items": shops_out,
        }
        self._save_snapshot("shops", keyword or category_id or preset, window_spec, len(shops_out), payload)
        return payload

    # 2. `/brand` — Brand Leaderboard, Market Share & Ad Spend
    def scrape_brands(
        self,
        *,
        keyword: str = "",
        category_id: str = "",
        window_spec: str = "7d",
        limit: int = 25,
    ) -> dict[str, Any]:
        if self.custom_scraper is not None:
            raw = self.custom_scraper("brands", keyword=keyword, category_id=category_id, window_spec=window_spec, limit=limit)
        else:
            raw = self._scrape_tanstack_route(
                KALODATA_BRAND_URL,
                keyword=keyword,
                category_id=category_id,
                window_spec=window_spec,
                limit=limit,
            )
        brands: list[dict[str, Any]] = []
        for idx, r in enumerate(raw.get("rows") or [], start=1):
            orig = r.get("rowOrig") if isinstance(r.get("rowOrig"), dict) else {}
            bid = safe_id_str(orig.get("brand_id") or orig.get("id") or r.get("rowKey") or "")
            bname = str(orig.get("brand_name") or ((r.get("tds") or ["", ""])[1] if len(r.get("tds") or []) > 1 else "")).strip()
            gmv = parse_kalodata_money_vnd(orig.get("revenue"))
            ad_spend = parse_kalodata_money_vnd(orig.get("ad_spend"))
            aov = parse_kalodata_money_vnd(orig.get("avg_unit_price"))
            brands.append(
                {
                    "rank": int(orig.get("rank") or idx),
                    "brand_id": bid,
                    "brand_name": bname,
                    "logo_url": str(orig.get("brand_logo") or ""),
                    "categories_vi": _decode_main_categories_vi(orig.get("main_pri_cate_id")),
                    "gmv_vnd": gmv,
                    "gmv_display": format_vnd_compact(gmv) if gmv is not None else "—",
                    "growth_pct": _parse_pct(orig.get("revenue_growth_rate")),
                    "market_share_pct": _parse_pct(orig.get("market_share")),
                    "ad_spend_vnd": ad_spend,
                    "ad_spend_display": format_vnd_compact(ad_spend) if ad_spend is not None else "—",
                    "units_sold": _parse_int_or_count(orig.get("item_sold")),
                    "aov_vnd": aov,
                    "creator_count": _parse_int_or_count(orig.get("creator_count")),
                    "video_count": _parse_int_or_count(orig.get("video_count")),
                    "top3_creator_ratio_pct": _parse_pct(orig.get("top3_creator_ratio")),
                    "top3_product_ratio_pct": _parse_pct(orig.get("top3_product_ratio")),
                    "top3_video_ratio_pct": _parse_pct(orig.get("top3_video_ratio")),
                    "kalodata_url": f"https://www.kalodata.com/brand/detail?id={bid}" if bid else KALODATA_BRAND_URL,
                }
            )
        payload = {
            "ok": True,
            "module": "brands",
            "keyword": keyword,
            "category_id": category_id,
            "window_spec": window_spec,
            "items_count": len(brands),
            "items": brands,
        }
        self._save_snapshot("brands", keyword or category_id or "top_brands", window_spec, len(brands), payload)
        return payload

    # 3. `/creator` — Direct KOC/Creator Hunter + Bio Contact Extractor
    def scrape_creators(
        self,
        *,
        keyword: str = "",
        category_id: str = "",
        window_spec: str = "7d",
        only_with_contact: bool = False,
        auto_save_vault: bool = True,
        limit: int = 25,
    ) -> dict[str, Any]:
        if self.custom_scraper is not None:
            raw = self.custom_scraper("creators", keyword=keyword, category_id=category_id, window_spec=window_spec, limit=limit)
        else:
            fetch_lim = min(100, int(limit or 25) * 2 if only_with_contact else int(limit or 25))
            raw = self._scrape_tanstack_route(
                KALODATA_CREATOR_URL,
                keyword=keyword,
                category_id=category_id,
                window_spec=window_spec,
                limit=fetch_lim,
            )
        creators: list[dict[str, Any]] = []
        for idx, r in enumerate(raw.get("rows") or [], start=1):
            orig = r.get("rowOrig") if isinstance(r.get("rowOrig"), dict) else {}
            handle = str(orig.get("handle") or "").strip().lstrip("@")
            if not handle:
                continue
            bio = str(orig.get("signature") or "").strip()
            contacts = extract_contacts_from_bio(bio)
            if only_with_contact and not contacts["has_contact"]:
                continue
            gmv = parse_kalodata_money_vnd(orig.get("revenue"))
            sold = _parse_int_or_count(orig.get("sale"))
            followers = _parse_int_or_count(orig.get("followers"))
            new_followers = _parse_int_or_count(orig.get("new_followers"))
            views_arr = [float(x) for x in (orig.get("views_trend") or []) if isinstance(x, (int, float))]
            total_views = int(round(sum(views_arr))) if views_arr else None
            est_gpm = round((gmv / total_views) * 1000.0, 2) if (gmv and total_views and total_views >= 1000) else None
            cid = safe_id_str(orig.get("id") or orig.get("creator_uid") or r.get("rowKey") or "")

            creators.append(
                {
                    "rank": int(orig.get("rank") or idx),
                    "creator_id": cid,
                    "handle": handle,
                    "nickname": str(orig.get("nickname") or handle).strip(),
                    "bio_signature": bio[:260],
                    "phones_zalo": contacts["phones_zalo"],
                    "emails": contacts["emails"],
                    "has_contact": contacts["has_contact"],
                    "categories_vi": _decode_main_categories_vi(orig.get("main_category")),
                    "gmv_vnd": gmv,
                    "gmv_display": format_vnd_compact(gmv) if gmv is not None else "—",
                    "units_sold": sold,
                    "followers_count": followers,
                    "new_followers_count": new_followers,
                    "total_views_window": total_views,
                    "estimated_gpm_vnd": est_gpm,
                    "aov_vnd": parse_kalodata_money_vnd(orig.get("unit_price")),
                    "engagement_rate_pct": _parse_pct(orig.get("video_engagement_rate")),
                    "debut_date": str(orig.get("creatorDebut") or ""),
                    "tiktok_url": f"https://www.tiktok.com/@{handle}",
                    "kalodata_url": f"https://www.kalodata.com/creator/detail?id={cid}" if cid else KALODATA_CREATOR_URL,
                }
            )
            if len(creators) >= int(limit or 25):
                break

        saved_cnt = 0
        if auto_save_vault and creators:
            ts = now()
            with self.connect() as conn:
                for cr in creators:
                    h = cr["handle"]
                    db_cid = f"kalo_cr_{h.lower()}"
                    contact_str = " · ".join((["Zalo/SĐT: " + ", ".join(cr["phones_zalo"])] if cr["phones_zalo"] else []) + (["Email: " + ", ".join(cr["emails"])] if cr["emails"] else []))
                    disp_name = cr.get("nickname") or f"@{h}"
                    if cr["phones_zalo"]:
                        disp_name = f"{disp_name} ({cr['phones_zalo'][0]})"[:120]
                    note_txt = f"Kalodata Pro ({window_spec}) · GMV {cr['gmv_display']}"
                    if contact_str:
                        note_txt += f" · {contact_str}"
                    conn.execute(
                        """
                        INSERT INTO creator_leads
                        (creator_id, platform, market, handle, display_name, followers, industry, video_gmv_vnd, avg_views, top_videos_json, note, created_at, updated_at)
                        VALUES (?, 'tiktok', 'VN', ?, ?, ?, ?, ?, ?, '[]', ?, ?, ?)
                        ON CONFLICT(creator_id) DO UPDATE SET
                            display_name=excluded.display_name,
                            followers=MAX(creator_leads.followers, excluded.followers),
                            video_gmv_vnd=MAX(creator_leads.video_gmv_vnd, excluded.video_gmv_vnd),
                            avg_views=MAX(creator_leads.avg_views, excluded.avg_views),
                            note=excluded.note,
                            updated_at=excluded.updated_at
                        """,
                        (
                            db_cid,
                            h,
                            disp_name,
                            int(cr.get("followers_count") or 0),
                            infer_industry(keyword or ", ".join(cr.get("categories_vi") or [])),
                            float(cr.get("gmv_vnd") or 0.0),
                            int(cr.get("total_views_window") or 0),
                            note_txt[:300],
                            ts,
                            ts,
                        ),
                    )
                    saved_cnt += 1

        payload = {
            "ok": True,
            "module": "creators",
            "keyword": keyword,
            "category_id": category_id,
            "window_spec": window_spec,
            "only_with_contact": only_with_contact,
            "items_count": len(creators),
            "with_contact_count": sum(1 for c in creators if c["has_contact"]),
            "saved_to_vault_count": saved_cnt,
            "items": creators,
        }
        self._save_snapshot("creators", keyword or category_id or "top_creators", window_spec, len(creators), payload)
        return payload

    # 4. `/livestream` — Winning Livestream Room Radar
    def scrape_livestreams(
        self,
        *,
        keyword: str = "",
        category_id: str = "",
        window_spec: str = "7d",
        limit: int = 25,
    ) -> dict[str, Any]:
        if self.custom_scraper is not None:
            raw = self.custom_scraper("livestreams", keyword=keyword, category_id=category_id, window_spec=window_spec, limit=limit)
        else:
            raw = self._scrape_tanstack_route(
                KALODATA_LIVESTREAM_URL,
                keyword=keyword,
                category_id=category_id,
                window_spec=window_spec,
                limit=limit,
            )
        rooms: list[dict[str, Any]] = []
        for idx, r in enumerate(raw.get("rows") or [], start=1):
            orig = r.get("rowOrig") if isinstance(r.get("rowOrig"), dict) else {}
            tds = r.get("tds") or []
            rid = safe_id_str(orig.get("id") or r.get("rowKey") or "")
            gmv = parse_kalodata_money_vnd(orig.get("revenue"))
            views = _parse_int_or_count(orig.get("views"))
            gpm = parse_kalodata_money_vnd(orig.get("gpm"))
            if gpm is None and gmv and views and views >= 500:
                gpm = round((gmv / views) * 1000.0, 2)
            handle = str(orig.get("handle") or orig.get("creator_handle") or "").strip().lstrip("@")
            title = str(orig.get("title") or orig.get("room_title") or (tds[0] if tds else "")).strip()
            rooms.append(
                {
                    "rank": int(orig.get("rank") or idx),
                    "room_id": rid,
                    "title": title[:180],
                    "handle": handle,
                    "categories_vi": _decode_main_categories_vi(orig.get("main_category")),
                    "gmv_vnd": gmv,
                    "gmv_display": format_vnd_compact(gmv) if gmv is not None else "—",
                    "units_sold": _parse_int_or_count(orig.get("sale")),
                    "views_count": views,
                    "gpm_vnd": gpm,
                    "gpm_display": format_vnd_compact(gpm) if gpm is not None else "—",
                    "start_time": str(orig.get("begin_time") or orig.get("live_time") or (tds[3] if len(tds) > 3 else "")),
                    "kalodata_url": f"https://www.kalodata.com/livestream/detail?id={rid}" if rid else KALODATA_LIVESTREAM_URL,
                }
            )
        payload = {
            "ok": True,
            "module": "livestreams",
            "keyword": keyword,
            "category_id": category_id,
            "window_spec": window_spec,
            "items_count": len(rooms),
            "items": rooms,
        }
        self._save_snapshot("livestreams", keyword or category_id or "top_live", window_spec, len(rooms), payload)
        return payload

    # 5. `/video` TanStack Pro — AI-Video, High-ROAS Ads & Low-Follower Viral Hunter
    def scrape_videos_advanced(
        self,
        *,
        keyword: str = "",
        category_id: str = "",
        window_spec: str = "7d",
        filter_mode: str = "all",
        auto_save_vault: bool = True,
        limit: int = 25,
    ) -> dict[str, Any]:
        if self.custom_scraper is not None:
            raw = self.custom_scraper("videos_advanced", keyword=keyword, category_id=category_id, window_spec=window_spec, filter_mode=filter_mode, limit=limit)
        else:
            fetch_lim = min(100, int(limit or 25) * 3 if filter_mode != "all" else int(limit or 25))
            raw = self._scrape_tanstack_route(
                KALODATA_VIDEO_URL,
                keyword=keyword,
                category_id=category_id,
                window_spec=window_spec,
                limit=fetch_lim,
            )
        videos: list[dict[str, Any]] = []
        for idx, r in enumerate(raw.get("rows") or [], start=1):
            orig = r.get("rowOrig") if isinstance(r.get("rowOrig"), dict) else {}
            vid = safe_id_str(orig.get("id") or r.get("rowKey") or "")
            if not vid:
                continue
            handle = str(orig.get("handle") or "").strip().lstrip("@")
            is_ad = bool(orig.get("ad"))
            is_ai = bool(orig.get("ai_video"))
            followers = _parse_int_or_count(orig.get("follower_count"))
            gmv = parse_kalodata_money_vnd(orig.get("revenue"))
            gpm = parse_kalodata_money_vnd(orig.get("gpm"))
            ad_spend = parse_kalodata_money_vnd(orig.get("ad2Cost"))
            ad_cpa = parse_kalodata_money_vnd(orig.get("ad_cpa"))
            roas = parse_kalodata_count_or_float(str(orig.get("ad2Roas") or ""))
            ad_view_pct = _parse_pct(orig.get("ad_view_ratio"))
            ad_rev_pct = _parse_pct(orig.get("ad_revenue_ratio"))
            views = _parse_int_or_count(orig.get("views"))
            sold = _parse_int_or_count(orig.get("sale"))
            dur_s = _parse_dur_sec(orig.get("original_duration") or orig.get("duration"))

            if filter_mode == "ai_video" and not is_ai:
                continue
            if filter_mode == "high_roas_ads" and not (is_ad and (roas or 0.0) >= 1.8):
                continue
            if filter_mode == "organic_top" and (is_ad and (ad_view_pct or 0.0) > 25.0):
                continue
            if filter_mode == "low_follower_viral" and (followers is not None and followers > 60000):
                continue

            linked_pid = ""
            for bg in r.get("bgImgs") or []:
                m_p = re.search(r"tiktok\.product/(\d{15,22})/", str(bg))
                if m_p:
                    linked_pid = m_p.group(1)
                    break

            tiktok_url = f"https://www.tiktok.com/@{handle or '_'}/video/{vid}"
            videos.append(
                {
                    "rank": int(orig.get("rank") or idx),
                    "video_id": vid,
                    "tiktok_url": tiktok_url,
                    "kalodata_url": f"https://www.kalodata.com/video/detail?id={vid}",
                    "description": str(orig.get("description") or "").strip()[:320],
                    "handle": handle,
                    "followers_count": followers,
                    "duration_sec": dur_s,
                    "is_ad": is_ad,
                    "is_ai_video": is_ai,
                    "gmv_vnd": gmv,
                    "gmv_display": format_vnd_compact(gmv) if gmv is not None else "—",
                    "units_sold": sold,
                    "views_count": views,
                    "gpm_vnd": gpm,
                    "gpm_display": format_vnd_compact(gpm) if gpm is not None else "—",
                    "ad_cpa_vnd": ad_cpa,
                    "ad_view_ratio_pct": ad_view_pct,
                    "ad_revenue_ratio_pct": ad_rev_pct,
                    "ad_spend_vnd": ad_spend,
                    "ad_spend_display": format_vnd_compact(ad_spend) if ad_spend is not None else "—",
                    "ad_roas": roas,
                    "published_at": str(orig.get("publish_date") or ""),
                    "linked_product_id": linked_pid,
                }
            )
            if len(videos) >= int(limit or 25):
                break

        saved_vids = 0
        if auto_save_vault and videos:
            ts = now()
            with self.connect() as conn:
                for v in videos:
                    vkey = f"tiktok:{v['video_id']}"
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
                            v["tiktok_url"],
                            v["handle"],
                            1 if (v["is_ai_video"] or (v["ad_roas"] or 0.0) >= 1.8) else 0,
                            json.dumps(v, ensure_ascii=False),
                            ts,
                            ts,
                        ),
                    )
                    saved_vids += 1

        payload = {
            "ok": True,
            "module": "videos_advanced",
            "keyword": keyword,
            "category_id": category_id,
            "window_spec": window_spec,
            "filter_mode": filter_mode,
            "items_count": len(videos),
            "saved_to_vault_count": saved_vids,
            "ai_videos_count": sum(1 for v in videos if v["is_ai_video"]),
            "ad_videos_count": sum(1 for v in videos if v["is_ad"]),
            "items": videos,
        }
        self._save_snapshot("videos_advanced", f"{filter_mode}:{keyword or category_id}", window_spec, len(videos), payload)
        return payload

    # 6. Deep Product (`/product/detail`) & Deep Video (`/video/detail` + 0₫ MP4 CDN)
    def inspect_deep_detail(self, target: str, *, save_to_vault: bool = True) -> dict[str, Any]:
        raw_t = str(target or "").strip()
        if not raw_t:
            raise ApiError("400 Bad Request", "Vui lòng nhập ID hoặc Link Sản phẩm / Video TikTok cần mổ xẻ sâu trên Kalodata.")

        is_vid = bool(
            "/video/" in raw_t.lower()
            or "vt.tiktok.com" in raw_t.lower()
            or "vm.tiktok.com" in raw_t.lower()
            or raw_t.lower().startswith("vid:")
        )
        is_prod = bool("/product/" in raw_t.lower() or "/pdp/" in raw_t.lower() or "shop.tiktok.com" in raw_t.lower() or raw_t.lower().startswith("pid:"))
        m_id = _DIGIT_ID_RE.search(raw_t)
        entity_id = m_id.group(1) if m_id else ""
        if not entity_id:
            raise ApiError("400 Bad Request", "Vui lòng truyền ID số 15–22 chữ số hoặc link đầy đủ chứa ID Video / Sản phẩm TikTok.")

        if not is_vid and not is_prod:
            is_prod = entity_id.startswith("17")
            is_vid = not is_prod

        if is_vid:
            return self.inspect_video_detail(entity_id, save_to_vault=save_to_vault)
        return self.inspect_product_detail(entity_id, save_to_vault=save_to_vault)

    def inspect_video_detail(self, video_id: str, *, save_to_vault: bool = True) -> dict[str, Any]:
        vid = safe_id_str(video_id)
        url = KALODATA_VIDEO_DETAIL_URL.format(id=quote(vid))
        if self.custom_scraper is not None:
            info = self.custom_scraper("video_detail", video_id=vid)
        else:
            with self.hunter._lock_ref():
                port, ws = self.hunter._ensure_kalodata_tab(url, require_search_input=False)
                time.sleep(2.4)
                info = cdp_ws_eval(
                    port,
                    ws,
                    r"""(() => {
                      const vids = Array.from(document.querySelectorAll("video, source"))
                        .map(v => v.src || v.currentSrc || "")
                        .filter(u => u && u.startsWith("http"));
                      const body = (document.body.innerText || "").replace(/\s+/g, " ").trim();
                      const prodImgs = Array.from(document.querySelectorAll("*"))
                        .map(el => el.src || el.style?.backgroundImage || getComputedStyle(el).backgroundImage || "")
                        .filter(s => s && s.includes("tiktok.product/"));
                      const simVids = [];
                      for (const tr of Array.from(document.querySelectorAll("tbody tr")).slice(0, 8)) {
                        let ro = null;
                        for (const el of [tr, ...Array.from(tr.querySelectorAll("td, div")).slice(0, 5)]) {
                          const fk = Object.keys(el).find(k => k.startsWith("__reactFiber"));
                          let c = fk ? el[fk] : null;
                          for (let d = 0; d < 16 && c; d++) {
                            const mp = c.memoizedProps;
                            if (mp?.row?.original) { ro = mp.row.original; break; }
                            if (mp?.cell?.row?.original) { ro = mp.cell.row.original; break; }
                            c = c.return;
                          }
                          if (ro) break;
                        }
                        if (ro && (ro.id || ro.product_title || ro.description)) simVids.push(ro);
                      }
                      return JSON.stringify({url: location.href, title: document.title, vids, prodImgs: prodImgs.slice(0, 10), body: body.slice(0, 4000), rowsOrig: simVids});
                    })()""",
                )

        body = str(info.get("body") or "")
        mp4_cdn_url = next((u for u in (info.get("vids") or []) if ".mp4" in u or "kalocdn.com/video" in u), "")
        m_ad_days = re.search(r"投广时间[:：]\s*(\d+)\s*天", body)
        m_ad_range = re.search(r"投广时间[:：]\s*(\d{4}-\d{2}-\d{2}\s*-\s*\d{4}-\d{2}-\d{2})", body)
        m_pub = re.search(r"发布日期[:：]\s*([^\s]+)", body)
        m_views = re.search(r"观看次数[^\d]*([\d.,]+\s*(?:亿|万|[KkMmBb])?)", body)
        m_sales = re.search(r"销量[^\d]*([\d.,]+\s*(?:亿|万|[KkMmBb])?)", body)
        m_gmv = re.search(r"成交金额[^₫¥￥$]*([₫¥￥$][\d.,]+\s*(?:亿|万|[KkMmBb])?)", body)
        m_ad_view = re.search(r"广告观看占比[^\d]*([\d.]+%)", body)
        m_ad_gmv = re.search(r"广告成交占比[^\d]*([\d.]+%)", body)
        m_ad_spend = re.search(r"广告消耗[^₫¥￥$]*([₫¥￥$][\d.,]+\s*(?:亿|万|[KkMmBb])?)", body)
        m_roas = re.search(r"广告ROAS[^\d]*([\d.]+)", body)
        m_handle = re.search(r"\b([A-Za-z0-9._-]{3,36})\s+[\d.,]+(?:万|[KkMm])?\s*粉丝数", body)

        linked_pids: list[str] = []
        for pi in info.get("prodImgs") or []:
            mp = re.search(r"tiktok\.product/(\d{15,22})/", str(pi))
            if mp and mp.group(1) not in linked_pids:
                linked_pids.append(mp.group(1))

        linked_products: list[dict[str, Any]] = []
        similar_videos: list[dict[str, Any]] = []
        for ro in info.get("rowsOrig") or []:
            if not isinstance(ro, dict):
                continue
            if ro.get("product_title") or (str(ro.get("id") or "").startswith("17")):
                gmv_p = parse_kalodata_money_vnd(ro.get("revenue"))
                linked_products.append(
                    {
                        "product_id": safe_id_str(ro.get("id") or ""),
                        "title": str(ro.get("product_title") or ro.get("title") or "")[:180],
                        "price_vnd": parse_kalodata_money_vnd(ro.get("unit_price") or ro.get("price")),
                        "gmv_vnd": gmv_p,
                        "gmv_display": format_vnd_compact(gmv_p) if gmv_p is not None else "—",
                        "share_pct": _parse_pct(ro.get("ratio") or ro.get("revenue_ratio")),
                    }
                )
            elif ro.get("description") or str(ro.get("id") or "").startswith("7"):
                sv_id = safe_id_str(ro.get("id") or "")
                sv_h = str(ro.get("handle") or "").lstrip("@")
                gmv_v = parse_kalodata_money_vnd(ro.get("revenue"))
                similar_videos.append(
                    {
                        "video_id": sv_id,
                        "handle": sv_h,
                        "description": str(ro.get("description") or "")[:180],
                        "duration_sec": _parse_dur_sec(ro.get("duration")),
                        "is_ad": bool(ro.get("ad")),
                        "gmv_vnd": gmv_v,
                        "gmv_display": format_vnd_compact(gmv_v) if gmv_v is not None else "—",
                        "tiktok_url": f"https://www.tiktok.com/@{sv_h or '_'}/video/{sv_id}" if sv_id else "",
                    }
                )

        handle_str = m_handle.group(1) if m_handle else ""
        gmv_val = parse_kalodata_money_vnd(m_gmv.group(1)) if m_gmv else None
        ad_spend_val = parse_kalodata_money_vnd(m_ad_spend.group(1)) if m_ad_spend else None
        payload = {
            "ok": True,
            "detail_kind": "video",
            "video_id": vid,
            "tiktok_url": f"https://www.tiktok.com/@{handle_str or '_'}/video/{vid}",
            "kalodata_url": url,
            "mp4_cdn_url": mp4_cdn_url,
            "has_watermark_free_mp4": bool(mp4_cdn_url),
            "author_handle": handle_str,
            "caption": str(info.get("title") or "").replace("越南 TikTok Data", "").strip()[:500],
            "published_at": m_pub.group(1) if m_pub else "",
            "ad_flight_days": int(m_ad_days.group(1)) if m_ad_days else 0,
            "ad_date_range": m_ad_range.group(1) if m_ad_range else "",
            "views_count": _parse_int_or_count(m_views.group(1)) if m_views else None,
            "units_sold": _parse_int_or_count(m_sales.group(1)) if m_sales else None,
            "gmv_vnd": gmv_val,
            "gmv_display": format_vnd_compact(gmv_val) if gmv_val is not None else "—",
            "ad_view_share_pct": _parse_pct(m_ad_view.group(1)) if m_ad_view else None,
            "ad_gmv_share_pct": _parse_pct(m_ad_gmv.group(1)) if m_ad_gmv else None,
            "ad_spend_vnd": ad_spend_val,
            "ad_spend_display": format_vnd_compact(ad_spend_val) if ad_spend_val is not None else "—",
            "ad_roas": float(m_roas.group(1)) if m_roas else None,
            "linked_product_ids": linked_pids,
            "linked_products": linked_products,
            "similar_videos": similar_videos,
        }
        if save_to_vault:
            ts = now()
            with self.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO video_reviews
                    (video_key, platform, video_url, author_handle, is_important, record, created_at, updated_at)
                    VALUES (?, 'tiktok', ?, ?, 1, ?, ?, ?)
                    ON CONFLICT(video_key) DO UPDATE SET
                        video_url=excluded.video_url,
                        author_handle=excluded.author_handle,
                        record=excluded.record,
                        updated_at=excluded.updated_at
                    """,
                    (f"tiktok:{vid}", payload["mp4_cdn_url"] or payload["tiktok_url"], handle_str, json.dumps(payload, ensure_ascii=False), ts, ts),
                )
        self._save_snapshot("video_detail", vid, "7d", 1, payload)
        return payload

    def inspect_product_detail(self, product_id: str, *, save_to_vault: bool = True) -> dict[str, Any]:
        pid = safe_id_str(product_id)
        url = KALODATA_PRODUCT_DETAIL_URL.format(id=quote(pid))
        if self.custom_scraper is not None:
            info = self.custom_scraper("product_detail", product_id=pid)
        else:
            with self.hunter._lock_ref():
                port, ws = self.hunter._ensure_kalodata_tab(url, require_search_input=False)
                time.sleep(2.5)
                info = cdp_ws_eval(
                    port,
                    ws,
                    r"""(() => {
                      const body = (document.body.innerText || "").replace(/\s+/g, " ").trim();
                      const rowsOrig = [];
                      for (const tr of Array.from(document.querySelectorAll("tbody tr")).slice(0, 25)) {
                        let ro = null;
                        for (const el of [tr, ...Array.from(tr.querySelectorAll("td, div")).slice(0, 5)]) {
                          const fk = Object.keys(el).find(k => k.startsWith("__reactFiber"));
                          let c = fk ? el[fk] : null;
                          for (let d = 0; d < 16 && c; d++) {
                            const mp = c.memoizedProps;
                            if (mp?.row?.original) { ro = mp.row.original; break; }
                            if (mp?.cell?.row?.original) { ro = mp.cell.row.original; break; }
                            c = c.return;
                          }
                          if (ro) break;
                        }
                        const tds = Array.from(tr.querySelectorAll("td")).map(x => (x.innerText||"").replace(/\s+/g," ").trim());
                        rowsOrig.push({ro, tds});
                      }
                      return JSON.stringify({url: location.href, title: document.title, body: body.slice(0, 4800), rowsOrig});
                    })()""",
                )

        body = str(info.get("body") or "")
        m_first_dt = re.search(r"数据最早收录时间[:：]\s*(\d{4}[/-]\d{1,2}[/-]\d{1,2})", body)
        first_recorded_date = m_first_dt.group(1).replace("/", "-") if m_first_dt else ""
        m_comm = re.search(r"佣金比例[:：]\s*([\d.]+%)", body)
        m_rating = re.search(r"评分[:：]\s*([\d.]+)", body)
        m_price = re.search(r"价格[:：]\s*([₫¥￥$][\d.,]+\s*(?:亿|万|[KkMmBb])?)", body)
        m_conv = re.search(r"达人出单率[^\d]*([\d.]+%)", body)
        m_conc = re.search(r"近30天达销集中度[^\d]*([\d.]+%)", body)
        m_strat = re.search(
            r"销售策略\s*成交金额[^₫¥￥$\d]*([₫¥￥$][\d.,]+(?:亿|万)?)\s*=\s*直播[^₫¥￥$\d]*[₫¥￥$][\d.,]+(?:亿|万)?\s*([\d.]+%)\s*\+\s*视频[^₫¥￥$\d]*[₫¥￥$][\d.,]+(?:亿|万)?\s*([\d.]+%)\s*\+\s*商品卡[^0-9]*([\d.]+%)",
            body,
        )
        m_sell_pts = re.search(r"卖点\s+(.+?)\s+属性\s+(.+?)\s+SKU分析", body)

        skus: list[dict[str, Any]] = []
        top_creators: list[dict[str, Any]] = []
        top_videos: list[dict[str, Any]] = []

        for item in info.get("rowsOrig") or []:
            ro = item.get("ro") if isinstance(item.get("ro"), dict) else {}
            tds = item.get("tds") or []
            if ro.get("sku_name") or (len(tds) == 5 and "%" in (tds[1] if len(tds) > 1 else "")):
                skus.append(
                    {
                        "sku_name": str(ro.get("sku_name") or (tds[0] if tds else ""))[:120],
                        "sales_share_pct": _parse_pct(ro.get("sale_ratio") or (tds[1] if len(tds) > 1 else "")),
                        "price_vnd": parse_kalodata_money_vnd(ro.get("price") or (tds[2] if len(tds) > 2 else "")),
                        "stock_count": _parse_int_or_count(ro.get("stock") or (tds[3] if len(tds) > 3 else "")),
                    }
                )
            elif ro.get("handle") and not ro.get("description"):
                gmv_c = parse_kalodata_money_vnd(ro.get("revenue"))
                top_creators.append(
                    {
                        "handle": str(ro.get("handle") or "").lstrip("@"),
                        "followers_count": _parse_int_or_count(ro.get("followers") or ro.get("follower_count")),
                        "gmv_vnd": gmv_c,
                        "gmv_display": format_vnd_compact(gmv_c) if gmv_c is not None else "—",
                        "units_sold": _parse_int_or_count(ro.get("sale")),
                        "video_gmv_vnd": parse_kalodata_money_vnd(ro.get("video_revenue")),
                        "live_gmv_vnd": parse_kalodata_money_vnd(ro.get("live_revenue")),
                    }
                )
            elif ro.get("description") or (tds and re.match(r"^\d+\s+\d+s\s+", " ".join(tds[:2]))):
                vid_id = safe_id_str(ro.get("id") or "")
                gmv_v = parse_kalodata_money_vnd(ro.get("revenue"))
                top_videos.append(
                    {
                        "video_id": vid_id,
                        "description": str(ro.get("description") or (tds[1] if len(tds) > 1 else ""))[:180],
                        "gmv_vnd": gmv_v,
                        "gmv_display": format_vnd_compact(gmv_v) if gmv_v is not None else "—",
                        "views_count": _parse_int_or_count(ro.get("views")),
                        "units_sold": _parse_int_or_count(ro.get("sale")),
                        "published_at": str(ro.get("publish_date") or (tds[-1] if tds else "")),
                        "tiktok_url": f"https://www.tiktok.com/@_/video/{vid_id}" if vid_id else "",
                    }
                )

        gmv_7d = parse_kalodata_money_vnd(m_strat.group(1)) if m_strat else None
        total_stock = sum(int(s.get("stock_count") or 0) for s in skus if s.get("stock_count") is not None)
        title_clean = str(info.get("title") or "").replace("商品详情", "").replace("越南 TikTok Data", "").strip(" -")[:240] or f"TikTok Shop Product #{pid}"
        price_val = parse_kalodata_money_vnd(m_price.group(1)) if m_price else (skus[0]["price_vnd"] if skus and skus[0].get("price_vnd") else None)

        vault_pid = None
        if save_to_vault and self.products is not None:
            saved = self.products.upsert_product(
                {
                    "platform": "tiktok_shop",
                    "market": "VN",
                    "native_product_id": pid,
                    "title": title_clean,
                    "url": f"https://shop.tiktok.com/view/product/{pid}?region=VN",
                    "price_vnd": float(price_val or 0.0),
                    "gmv_vnd": float(gmv_7d or 0.0),
                    "rating": float(m_rating.group(1)) if m_rating else 0.0,
                    "stock": total_stock if skus else None,
                    "variants": skus[:15],
                    "kalodata_deep_dossier": {
                        "first_recorded_date": first_recorded_date,
                        "commission_pct": _parse_pct(m_comm.group(1)) if m_comm else None,
                        "ai_selling_points": m_sell_pts.group(1).strip() if m_sell_pts else "",
                        "product_attributes": m_sell_pts.group(2).strip() if m_sell_pts else "",
                        "total_sku_stock": total_stock,
                    },
                },
                source="kalodata_pro:product_detail",
            )
            vault_pid = int(saved["id"])

        payload = {
            "ok": True,
            "detail_kind": "product",
            "product_id": pid,
            "vault_product_id": vault_pid,
            "tiktok_shop_url": f"https://shop.tiktok.com/view/product/{pid}?region=VN&locale=vi-VN",
            "kalodata_url": url,
            "title": title_clean,
            "first_recorded_date": first_recorded_date,
            "price_vnd": price_val,
            "commission_pct": _parse_pct(m_comm.group(1)) if m_comm else None,
            "rating": float(m_rating.group(1)) if m_rating else None,
            "creator_conversion_rate_pct": _parse_pct(m_conv.group(1)) if m_conv else None,
            "top_creator_concentration_30d_pct": _parse_pct(m_conc.group(1)) if m_conc else None,
            "gmv_7d_vnd": gmv_7d,
            "gmv_7d_display": format_vnd_compact(gmv_7d) if gmv_7d is not None else "—",
            "channel_split": {
                "live_pct": _parse_pct(m_strat.group(2)) if m_strat else None,
                "video_pct": _parse_pct(m_strat.group(3)) if m_strat else None,
                "product_card_pct": _parse_pct(m_strat.group(4)) if m_strat else None,
            },
            "video_creators_in_top10": sum(1 for c in top_creators if (c.get("video_gmv_vnd") or 0.0) > 0),
            "ai_selling_points": m_sell_pts.group(1).strip() if m_sell_pts else "",
            "product_attributes": m_sell_pts.group(2).strip() if m_sell_pts else "",
            "total_sku_stock": total_stock if skus else None,
            "skus": skus[:15],
            "top_creators": top_creators[:10],
            "top_videos": top_videos[:10],
        }
        self._save_snapshot("product_detail", pid, "7d", 1, payload)
        return payload

    def list_recent_snapshots(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT snap_id, module_kind, target_query, window_spec, items_count, created_at "
                "FROM kalodata_pro_snapshots ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (max(1, min(50, int(limit or 20))),),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_snapshot(self, snap_id: str) -> dict[str, Any] | None:
        sid = str(snap_id or "").strip()
        if not sid:
            return None
        with self.connect() as conn:
            row = conn.execute(
                "SELECT snap_id, module_kind, target_query, window_spec, items_count, payload_json, created_at "
                "FROM kalodata_pro_snapshots WHERE snap_id = ?",
                (sid,),
            ).fetchone()
        if not row:
            return None
        payload = json.loads(row["payload_json"] or "{}")
        if isinstance(payload, dict):
            payload.setdefault("snapshot_id", row["snap_id"])
            payload.setdefault("created_at", row["created_at"])
        return payload

    def dispatch(self, path: str, method: str, env: dict, read_json):
        norm_path = path.replace("/api/kalodata-pro/", "/api/hunt/kalodata-pro/") if path.startswith("/api/kalodata-pro/") else path
        if norm_path == "/api/hunt/kalodata-pro/shops" and method == "POST":
            b = json_object(read_json, env)
            return "200 OK", self.scrape_shops(
                keyword=str(b.get("keyword") or ""),
                category_id=str(b.get("category_id") or ""),
                window_spec=str(b.get("window_spec") or "7d"),
                preset=str(b.get("preset") or "all"),
                auto_save_vault=bool(b.get("auto_save_vault", True)),
                limit=int(b.get("limit") or 25),
            )
        if norm_path == "/api/hunt/kalodata-pro/brands" and method == "POST":
            b = json_object(read_json, env)
            return "200 OK", self.scrape_brands(
                keyword=str(b.get("keyword") or ""),
                category_id=str(b.get("category_id") or ""),
                window_spec=str(b.get("window_spec") or "7d"),
                limit=int(b.get("limit") or 25),
            )
        if norm_path == "/api/hunt/kalodata-pro/creators" and method == "POST":
            b = json_object(read_json, env)
            return "200 OK", self.scrape_creators(
                keyword=str(b.get("keyword") or ""),
                category_id=str(b.get("category_id") or ""),
                window_spec=str(b.get("window_spec") or "7d"),
                only_with_contact=bool(b.get("only_with_contact", False)),
                auto_save_vault=bool(b.get("auto_save_vault", True)),
                limit=int(b.get("limit") or 25),
            )
        if norm_path == "/api/hunt/kalodata-pro/livestreams" and method == "POST":
            b = json_object(read_json, env)
            return "200 OK", self.scrape_livestreams(
                keyword=str(b.get("keyword") or ""),
                category_id=str(b.get("category_id") or ""),
                window_spec=str(b.get("window_spec") or "7d"),
                limit=int(b.get("limit") or 25),
            )
        if norm_path == "/api/hunt/kalodata-pro/videos-advanced" and method == "POST":
            b = json_object(read_json, env)
            return "200 OK", self.scrape_videos_advanced(
                keyword=str(b.get("keyword") or ""),
                category_id=str(b.get("category_id") or ""),
                window_spec=str(b.get("window_spec") or "7d"),
                filter_mode=str(b.get("filter_mode") or "all"),
                auto_save_vault=bool(b.get("auto_save_vault", True)),
                limit=int(b.get("limit") or 25),
            )
        if norm_path == "/api/hunt/kalodata-pro/deep-detail" and method == "POST":
            b = json_object(read_json, env)
            return "200 OK", self.inspect_deep_detail(
                str(b.get("target") or ""),
                save_to_vault=bool(b.get("save_to_vault", True)),
            )
        if norm_path == "/api/hunt/kalodata-pro/history" and method == "GET":
            snaps = self.list_recent_snapshots(limit=20)
            latest_payload = self.get_snapshot(snaps[0]["snap_id"]) if snaps else None
            return "200 OK", {"items": snaps, "latest": latest_payload}
        if norm_path.startswith("/api/hunt/kalodata-pro/snapshot/") and method == "GET":
            sid = norm_path.rsplit("/", 1)[-1].strip()
            snap = self.get_snapshot(sid)
            if not snap:
                return "404 Not Found", {"detail": "Không tìm thấy phiên quét Kalodata Pro"}
            return "200 OK", snap
        return None
