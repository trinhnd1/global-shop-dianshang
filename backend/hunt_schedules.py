"""Recurring Hunt & Social Painpoint Autopilot (`⏰ Săn SP & Painpoint Lặp lại Hàng ngày -> 300+desk Tổng hợp -> Jev Chấm điểm & Phân loại`).

Allows scheduling daily fixed-time (e.g. `07:30` every morning) or fixed-interval (`6h`, `12h`, `24h`, `48h`, `168h`) recurring scans across:
- Keywords & Google Trends breakout terms
- Social Painpoint channels (`Facebook`, `FB Ads`, `Threads`, `X`, `Reddit`)
- Specific Pinned Products (URLs or Kho SP IDs) to track daily sales & inventory (`stock`) drops alongside keyword discovery
- SEA Marketplaces (`Shopee VN/PH/SG/MY/TH`, `TikTokShop VN/PH/SG/MY/TH`, `Lazada`) strictly obeying `Apify (#1) -> Treg (#2)`
- `300+desk` (OPi SOCKS5 Fail-Closed) product normalization, CN 1688 keywords, combo/video angles & Daily Executive Synthesis
- `TypeSafe Jev AI` 6-pillar scoring & automatic Vault Bucket / Industry / Shop classification
- Full `GS-XXXX` Work-Log & Telegram Bot `@tc_global1_shop_bot` delivery.
"""
from datetime import datetime, timedelta, timezone
import json
import re
import threading
import time
import uuid

from . import settings
from .hunt import MARKETPLACE_CHANNELS, SOCIAL_PAINPOINT_CHANNELS
from .markets import parse_marketplace_spec
from .products import BUCKETS, parse_ids_from_url
from .responses import ApiError, json_object, now, safe_id_str, text

HHMM_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def normalize_daily_time(raw: str | None, default: str = "07:30") -> str:
    s = str(raw or "").strip()
    m = HHMM_RE.match(s)
    if not m:
        return default
    return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"


def compute_next_run_utc(
    schedule_mode: str,
    daily_time: str = "07:30",
    interval_hours: float = 24.0,
    now_dt: datetime | None = None,
) -> str:
    ref_utc = now_dt.astimezone(timezone.utc) if now_dt else datetime.now(timezone.utc)
    if schedule_mode == "interval_hours":
        hrs = max(1.0, min(168.0, float(interval_hours or 24.0)))
        nxt = ref_utc + timedelta(hours=hrs)
        return nxt.strftime("%Y-%m-%dT%H:%M:%SZ")

    hhmm = normalize_daily_time(daily_time, "07:30")
    hh, mm = [int(x) for x in hhmm.split(":")]
    local_now = ref_utc.astimezone()
    cand_local = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if cand_local <= local_now + timedelta(seconds=30):
        cand_local = cand_local + timedelta(days=1)
    return cand_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_str_list(raw, max_items: int = 12, max_len: int = 240) -> list[str]:
    if isinstance(raw, list):
        parts = [str(x).strip() for x in raw]
    elif isinstance(raw, str):
        parts = [x.strip() for x in re.split(r"[,;\n]+", raw)]
    else:
        parts = []
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        c = p[:max_len].strip()
        if c and c.lower() not in seen:
            seen.add(c.lower())
            out.append(c)
            if len(out) >= max_items:
                break
    return out


def _item_snapshot_key(it: dict) -> str:
    plat = str(it.get("platform") or "shopee").lower()
    mkt = str(it.get("market") or "VN").upper()
    npid = safe_id_str(it.get("native_product_id") or "")
    url = str(it.get("url") or "").strip().lower()
    ident = npid or url or str(it.get("title") or "").strip().lower()[:80]
    return f"{plat}:{mkt}:{ident}"


class HuntScheduleService:
    def __init__(
        self,
        connect,
        secrets,
        products,
        hunt_service,
        desk_pipeline=None,
        desk300=None,
        apify=None,
        treg=None,
        jev=None,
        history_logs=None,
        telegram_bot=None,
    ):
        self.connect = connect
        self.secrets = secrets
        self.products = products
        self.hunt = hunt_service
        self.desk_pipeline = desk_pipeline
        self.desk300 = desk300
        self.apify = apify
        self.treg = treg
        self.jev = jev
        self.history_logs = history_logs
        self.telegram_bot = telegram_bot
        self._run_locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _lock_for(self, schedule_id: str) -> threading.Lock:
        with self._guard:
            if schedule_id not in self._run_locks:
                self._run_locks[schedule_id] = threading.Lock()
            return self._run_locks[schedule_id]

    def create_schedule(self, body: dict) -> dict:
        keywords = _parse_str_list(body.get("keywords") or body.get("keyword") or body.get("topic_query"), max_items=10, max_len=140)
        pinned_products = _parse_str_list(body.get("pinned_products"), max_items=15, max_len=300)
        if not keywords and not pinned_products:
            raise ValueError("Vui lòng nhập ít nhất 1 Từ khoá / Chủ đề Painpoint hoặc Link/ID sản phẩm cần săn lặp lại")

        raw_name = str(body.get("name") or "").strip()
        if not raw_name:
            lead = ", ".join(keywords[:2]) if keywords else f"{len(pinned_products)} SP ghim"
            raw_name = f"Săn lặp lại: {lead}"
        name = text(raw_name, "name", 160, required=True)

        schedule_mode = str(body.get("schedule_mode") or "daily_time").strip().lower()
        if schedule_mode not in ("daily_time", "interval_hours"):
            raise ValueError("Chế độ lặp lại phải là daily_time (Giờ cố định hàng ngày) hoặc interval_hours (Chu kỳ giờ)")
        daily_time = normalize_daily_time(body.get("daily_time"), "07:30")
        interval_hours = max(1.0, min(168.0, float(body.get("interval_hours") or 24.0)))

        cfg = settings.read_settings(self.connect, self.secrets)
        raw_chs = body.get("channels") if isinstance(body.get("channels"), list) and body.get("channels") else cfg["hunt"]["channels"]
        valid_chs = [
            str(c).strip()
            for c in raw_chs
            if str(c).strip() in ("google_trends", *SOCIAL_PAINPOINT_CHANNELS, *MARKETPLACE_CHANNELS)
        ]
        if not valid_chs:
            valid_chs = ["google_trends", "shopee_vn", "tiktok_shop_vn"]

        shopee_filters = body.get("shopee_filters") if isinstance(body.get("shopee_filters"), dict) else {}
        items_per_ch = max(3, min(30, int(body.get("items_per_channel") or 8)))
        use_300desk = 1 if bool(body.get("use_300desk", True)) else 0
        auto_score_jev = 1 if bool(body.get("auto_score_jev", True)) else 0
        auto_classify = 1 if bool(body.get("auto_classify_buckets", True)) else 0
        auto_promote = 1 if bool(body.get("auto_promote_strong_pick", True)) else 0

        sid = f"hsch_{uuid.uuid4().hex[:10]}"
        ts = now()
        nxt = compute_next_run_utc(schedule_mode, daily_time, interval_hours)

        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO hunt_schedules
                (schedule_id, name, status, schedule_mode, daily_time, interval_hours,
                 keywords_json, pinned_products_json, channels_json, shopee_filters_json,
                 items_per_channel, use_300desk, auto_score_jev, auto_classify_buckets, auto_promote_strong_pick,
                 runs_count, last_run_at, next_run_at, baseline_snapshot_json, last_summary_json, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, '', ?, '{}', '{}', ?, ?)
                """,
                (
                    sid,
                    name,
                    schedule_mode,
                    daily_time,
                    interval_hours,
                    json.dumps(keywords, ensure_ascii=False),
                    json.dumps(pinned_products, ensure_ascii=False),
                    json.dumps(valid_chs, ensure_ascii=False),
                    json.dumps(shopee_filters, ensure_ascii=False),
                    items_per_ch,
                    use_300desk,
                    auto_score_jev,
                    auto_classify,
                    auto_promote,
                    nxt,
                    ts,
                    ts,
                ),
            )

        if bool(body.get("run_immediately", False)):
            first_run = self.execute_schedule_run(sid, trigger_kind="initial_create")
            return {
                "schedule": self.get_schedule(sid),
                "first_run": first_run["run"],
                "highlights": first_run.get("highlights") or [],
                "summary": first_run["summary"],
            }

        sched_obj = self.get_schedule(sid)
        when_lbl = f"hàng ngày lúc {daily_time}" if schedule_mode == "daily_time" else f"mỗi {interval_hours:g} giờ"
        return {
            "schedule": sched_obj,
            "summary": f"Đã tạo lịch săn lặp lại '{name}' ({when_lbl} -> 300+desk tổng hợp -> Jev chấm & phân loại)",
        }

    def update_schedule(self, schedule_id: str, patch: dict) -> dict:
        cur = self.get_schedule(schedule_id)
        if not cur:
            raise ApiError("404 Not Found", "Không tìm thấy lịch săn lặp lại này")

        name = text(patch.get("name") or cur["name"], "name", 160, required=True)
        status = str(patch.get("status") or cur["status"]).strip().lower()
        if status not in ("active", "paused", "archived"):
            raise ValueError("Trạng thái lịch săn không hợp lệ")
        schedule_mode = str(patch.get("schedule_mode") or cur["schedule_mode"]).strip().lower()
        if schedule_mode not in ("daily_time", "interval_hours"):
            raise ValueError("Chế độ lịch không hợp lệ")
        daily_time = normalize_daily_time(patch.get("daily_time") if "daily_time" in patch else cur["daily_time"], cur["daily_time"])
        interval_hours = max(1.0, min(168.0, float(patch.get("interval_hours") if "interval_hours" in patch else cur["interval_hours"])))
        keywords = _parse_str_list(patch["keywords"], 10, 140) if "keywords" in patch else cur["keywords"]
        pinned = _parse_str_list(patch["pinned_products"], 15, 300) if "pinned_products" in patch else cur["pinned_products"]
        channels = patch["channels"] if isinstance(patch.get("channels"), list) and patch["channels"] else cur["channels"]
        use_300desk = 1 if bool(patch.get("use_300desk", cur["use_300desk"])) else 0
        auto_jev = 1 if bool(patch.get("auto_score_jev", cur["auto_score_jev"])) else 0
        auto_cls = 1 if bool(patch.get("auto_classify_buckets", cur["auto_classify_buckets"])) else 0
        auto_prm = 1 if bool(patch.get("auto_promote_strong_pick", cur["auto_promote_strong_pick"])) else 0

        nxt = compute_next_run_utc(schedule_mode, daily_time, interval_hours) if status == "active" else ""
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE hunt_schedules
                SET name=?, status=?, schedule_mode=?, daily_time=?, interval_hours=?,
                    keywords_json=?, pinned_products_json=?, channels_json=?,
                    use_300desk=?, auto_score_jev=?, auto_classify_buckets=?, auto_promote_strong_pick=?,
                    next_run_at=?, updated_at=?
                WHERE schedule_id=?
                """,
                (
                    name,
                    status,
                    schedule_mode,
                    daily_time,
                    interval_hours,
                    json.dumps(keywords, ensure_ascii=False),
                    json.dumps(pinned, ensure_ascii=False),
                    json.dumps(channels, ensure_ascii=False),
                    use_300desk,
                    auto_jev,
                    auto_cls,
                    auto_prm,
                    nxt,
                    now(),
                    schedule_id,
                ),
            )
        updated = self.get_schedule(schedule_id)
        return {"schedule": updated, "summary": f"Đã cập nhật lịch săn '{name}' (trạng thái: {status})"}

    def delete_schedule(self, schedule_id: str) -> dict:
        with self.connect() as conn:
            conn.execute("DELETE FROM hunt_schedules WHERE schedule_id=?", (schedule_id,))
        return {"deleted": True, "schedule_id": schedule_id, "summary": f"Đã xoá lịch săn lặp lại {schedule_id}"}

    def _refresh_pinned_products(self, pinned_specs: list[str], apify_toks: list[str], treg_tok: str) -> list[dict]:
        refreshed_items: list[dict] = []
        for spec in pinned_specs[:12]:
            s = str(spec or "").strip()
            if not s:
                continue
            # Case A: Numeric Kho SP ID (e.g. "12" or "#12")
            clean_id = s.lstrip("#")
            if clean_id.isdigit():
                try:
                    p = self.products.enrich_product(int(clean_id))
                    if p:
                        refreshed_items.append(p)
                        continue
                except Exception:
                    pass
            # Case B: Product URL (Shopee / TikTokShop)
            if s.startswith("http"):
                plat, _, pid = parse_ids_from_url(s)
                fetched = None
                if plat == "shopee" and apify_toks and self.apify:
                    try:
                        fetched = self.apify.scrape_shopee_product(apify_toks, s)
                    except Exception:
                        fetched = None
                elif plat == "tiktok_shop":
                    if apify_toks and self.apify:
                        try:
                            fetched = self.apify.scrape_tiktok_shop_detail(apify_toks, s)
                        except Exception:
                            fetched = None
                    if not fetched and treg_tok and self.treg and pid:
                        try:
                            fetched = self.treg.fetch_tiktok_shop_product_detail(treg_tok, pid)
                        except Exception:
                            fetched = None
                if fetched and fetched.get("title"):
                    saved_p = self.products.upsert_product(fetched, source="scheduled_hunt_pinned")
                    refreshed_items.append(saved_p)
        return refreshed_items

    def _synthesize_daily_digest(
        self,
        sched_name: str,
        keywords: list[str],
        total_sampled: int,
        new_items: list[dict],
        rising_items: list[dict],
        painpoints: list[dict],
        top_scored: list[dict],
        use_300desk: bool,
    ) -> str:
        fallback_parts = [
            f"Quét định kỳ '{sched_name}': thu thập {total_sampled} SP trên các sàn"
            + (f", phát hiện +{len(new_items)} SP mới lên sàn" if new_items else ", chưa có SP mới ngoài mốc gốc")
            + (f", {len(rising_items)} SP tăng lượt bán/giảm tồn kho" if rising_items else "")
            + (f", {len(painpoints)} cụm Painpoint khách hàng." if painpoints else "."),
        ]
        if top_scored:
            top1 = top_scored[0]
            fallback_parts.append(
                f"Đề xuất dẫn đầu Jev AI: '{str(top1.get('title') or '')[:65]}' "
                f"(Jev {top1.get('jev_score')}/10 · Đã bán {top1.get('sold_count')} · Nhóm {BUCKETS.get(top1.get('bucket') or '', top1.get('bucket') or '')})."
            )
        fallback_text = " ".join(fallback_parts)

        if not use_300desk or self.desk300 is None or not hasattr(self.desk300, "call_gateway_json"):
            return fallback_text

        try:
            gw = self.desk300.check_gateway_status(probe_egress_ip=False)
            if not gw.get("ok"):
                return fallback_text
            digest_input = {
                "schedule_name": sched_name,
                "keywords": keywords[:6],
                "total_sampled": total_sampled,
                "new_products_count": len(new_items),
                "new_products_sample": [
                    {"title": x.get("title"), "price_vnd": x.get("price_vnd"), "sold_count": x.get("sold_count"), "platform": x.get("platform")}
                    for x in new_items[:5]
                ],
                "rising_products_sample": [
                    {"title": x.get("title"), "delta_sold": x.get("delta_sold"), "sold_count": x.get("sold_count")}
                    for x in rising_items[:5]
                ],
                "painpoints": [
                    {"title": p.get("painpoint_title"), "keywords": p.get("recommended_keywords")}
                    for p in painpoints[:3]
                ],
                "top_jev_products": [
                    {"title": p.get("title"), "jev_score": p.get("jev_score"), "bucket": p.get("bucket"), "price_vnd": p.get("price_vnd"), "sold_count": p.get("sold_count")}
                    for p in top_scored[:5]
                ],
            }
            sys_p = (
                "Bạn là chuyên gia phân tích sản phẩm `300+desk` của Global Shop Dianshang. "
                "CHỈ trả về DUY NHẤT 1 JSON object hợp lệ, TUYỆT ĐỐI KHÔNG tự bịa bất kỳ con số nào ngoài dữ liệu đầu vào."
            )
            usr_p = (
                "Tổng hợp báo cáo ngắn gọn (3-4 câu súc tích bằng tiếng Việt) cho phiên quét lặp lại hôm nay: "
                "nêu rõ biến động SP mới / SP tăng bán, nhu cầu Painpoint nổi bật (nếu có), và khuyến nghị nhập test / làm video hôm nay:\n"
                + json.dumps(digest_input, ensure_ascii=False)
                + '\nTrả về JSON: {"daily_synthesis": "<3-4 câu tổng hợp điều hành rõ ràng>"}'
            )
            res = self.desk300.call_gateway_json(sys_p, usr_p, task_type="daily_hunt_synthesis", timeout_sec=35)
            syn = str((res.get("parsed") or {}).get("daily_synthesis") or "").strip()
            return syn[:900] if syn else fallback_text
        except Exception:
            return fallback_text

    def execute_schedule_run(self, schedule_id: str, trigger_kind: str = "manual") -> dict:
        lock = self._lock_for(schedule_id)
        if not lock.acquire(blocking=False):
            raise ApiError("409 Conflict", "Lịch săn này đang chạy một phiên khác, vui lòng đợi hoàn tất")

        t0 = time.monotonic()
        try:
            with self.connect() as conn:
                row = conn.execute("SELECT * FROM hunt_schedules WHERE schedule_id=?", (schedule_id,)).fetchone()
            if not row:
                raise ApiError("404 Not Found", "Không tìm thấy lịch săn lặp lại")

            sched = self._format_schedule_row(row)
            prev_snap = json.loads(row["baseline_snapshot_json"] or "{}")
            prev_map: dict[str, dict] = prev_snap.get("items_by_key") or {}
            is_baseline = not bool(prev_snap.get("initialized"))

            cfg = settings.read_settings(self.connect, self.secrets)
            apify_toks = settings.apify_tokens(cfg)
            treg_tok = (cfg["providers"].get("treg_key") or "").strip()
            jev_key = (cfg["providers"].get("typesafe_key") or "").strip()

            keywords = sched["keywords"]
            pinned_specs = sched["pinned_products"]
            channels = sched["channels"]
            shopee_filters = sched["shopee_filters"] or None
            items_per_ch = int(sched["items_per_channel"] or 8)

            collected_raw: list[dict] = []
            discovered_pids: list[int] = []
            painpoints_objs: list[dict] = []
            painpoint_ids: list[str] = []

            # --- STEP 1: REFRESH PINNED / SPECIFIC PRODUCTS ---
            if pinned_specs:
                pinned_refreshed = self._refresh_pinned_products(pinned_specs, apify_toks, treg_tok)
                for pp_it in pinned_refreshed:
                    collected_raw.append(pp_it)
                    if pp_it["id"] not in discovered_pids:
                        discovered_pids.append(pp_it["id"])

            search_terms: list[tuple[str, str]] = [(kw, "seed") for kw in keywords]

            # --- STEP 2A: GOOGLE TRENDS BREAKOUT EXPANSION ---
            if "google_trends" in channels and keywords:
                try:
                    gt_res = self.hunt.google_trends_explore_multi(
                        seed_terms=keywords[:4],
                        geo="VN",
                        time_range="now 7-d",
                        score_jev=bool(jev_key and sched["auto_score_jev"]),
                    )
                    for k_obj in (gt_res.get("keywords") or []):
                        if k_obj.get("kind") in ("rising", "top"):
                            rk = str(k_obj.get("keyword") or "").strip()
                            if rk and rk.lower() not in {x[0].lower() for x in search_terms}:
                                search_terms.append((rk, "google_trends"))
                                if len(search_terms) >= len(keywords) + 3:
                                    break
                except Exception:
                    pass

            # --- STEP 2B: SOCIAL PAINPOINT DISCOVERY (FB · THREADS · X · REDDIT) ---
            social_chs = [c for c in channels if c in SOCIAL_PAINPOINT_CHANNELS]
            if social_chs and keywords:
                for term in keywords[:3]:
                    try:
                        pp_res = self.hunt.discover_painpoints(
                            topic_query=term,
                            channels=social_chs,
                            limit_per_channel=min(6, items_per_ch),
                            auto_find_products=False,
                        )
                        pp = pp_res["painpoint"]
                        painpoints_objs.append(pp)
                        painpoint_ids.append(pp["painpoint_id"])
                        for rec_kw in (pp.get("recommended_keywords") or [])[:2]:
                            if rec_kw.lower() not in {x[0].lower() for x in search_terms}:
                                search_terms.append((rec_kw, f"painpoint:{pp['painpoint_id']}"))
                    except Exception:
                        pass

            # --- STEP 3: MARKETPLACE CRAWL (APIFY #1 -> TREG #2) & SNAPSHOT DELTA DIFF ---
            mkt_chs = [c for c in channels if c in MARKETPLACE_CHANNELS]
            if not mkt_chs and (keywords or social_chs):
                mkt_chs = ["shopee_vn", "tiktok_shop_vn"]

            for s_term, origin_tag in search_terms[:7]:
                for ch in mkt_chs:
                    b_plat, b_mkt, ch_code = parse_marketplace_spec(ch)
                    rows_ch: list[dict] = []
                    # STRICT PRIORITY #1: APIFY
                    if apify_toks and self.apify:
                        try:
                            if b_plat == "shopee":
                                _, rows_ch = self.apify.search_shopee(
                                    apify_toks, s_term, limit=items_per_ch, filters=shopee_filters, market=b_mkt
                                )
                            elif b_plat == "tiktok_shop":
                                _, rows_ch = self.apify.search_tiktok_shop(
                                    apify_toks, s_term, limit=items_per_ch, market=b_mkt
                                )
                            elif b_plat == "lazada":
                                _, rows_ch = self.apify.search_lazada(apify_toks, s_term, limit=items_per_ch)
                        except Exception:
                            rows_ch = []
                    # STRICT PRIORITY #2: TREG BACKUP ONLY WHEN APIFY EMPTY
                    if not rows_ch and treg_tok and self.treg and b_plat == "tiktok_shop":
                        try:
                            _, rows_ch, _ = self.treg.search_tiktok_shop(treg_tok, s_term, limit=items_per_ch, market=b_mkt)
                        except Exception:
                            rows_ch = []

                    for r_it in rows_ch:
                        if r_it.get("title"):
                            if origin_tag.startswith("painpoint:"):
                                r_it["note"] = f"Giải pháp Painpoint ({s_term})"
                            collected_raw.append({**r_it, "_origin": f"{ch_code}:{origin_tag}:{s_term}"})

            # Build Current Snapshot & Diff vs Previous Run
            cur_map: dict[str, dict] = {}
            new_items: list[dict] = []
            rising_items: list[dict] = []
            priority_pids: list[int] = []

            for raw_it in collected_raw:
                skey = _item_snapshot_key(raw_it)
                if skey in cur_map:
                    continue
                cur_sold = int(raw_it.get("sold_count") or 0)
                cur_stock = int(raw_it.get("stock") or 0)
                cur_price = float(raw_it.get("price_vnd") or 0.0)
                cur_entry = {
                    "key": skey,
                    "platform": raw_it.get("platform") or "shopee",
                    "market": raw_it.get("market") or "VN",
                    "native_product_id": safe_id_str(raw_it.get("native_product_id") or ""),
                    "title": str(raw_it.get("title") or "")[:160],
                    "price_vnd": cur_price,
                    "sold_count": cur_sold,
                    "stock": cur_stock,
                    "url": str(raw_it.get("url") or ""),
                }
                cur_map[skey] = cur_entry

                saved_p = (
                    raw_it
                    if raw_it.get("id")
                    else self.products.upsert_product(raw_it, source=f"hunt_sched:{schedule_id}:{raw_it.get('_origin', 'kw')}")
                )
                pid = int(saved_p["id"])
                if pid not in discovered_pids:
                    discovered_pids.append(pid)

                if not is_baseline:
                    old = prev_map.get(skey)
                    if old is None:
                        new_items.append({**cur_entry, "product_id": pid})
                        if pid not in priority_pids:
                            priority_pids.append(pid)
                    else:
                        prev_sold = int(old.get("sold_count") or 0)
                        prev_stock = int(old.get("stock") or 0)
                        raw_d_sold = max(0, cur_sold - prev_sold)
                        stk_drop = max(0, prev_stock - cur_stock) if (prev_stock > 0 and cur_stock > 0 and cur_stock < prev_stock) else 0
                        eff_delta = max(raw_d_sold, stk_drop)
                        if eff_delta > 0:
                            rising_items.append({
                                **cur_entry,
                                "product_id": pid,
                                "prev_sold_count": prev_sold,
                                "delta_sold": eff_delta,
                                "stock_drop_inferred_sold": stk_drop,
                            })
                            if pid not in priority_pids:
                                priority_pids.append(pid)

            rising_items.sort(key=lambda x: x["delta_sold"], reverse=True)

            # Fill priority batch up to 12 products (New + Rising + Top Sales) for 300+desk & Jev AI!
            all_vault = self.products.get_products_by_ids(discovered_pids)
            all_vault.sort(key=lambda x: (int(x.get("sold_30d") or 0), int(x.get("sold_count") or 0)), reverse=True)
            for vp in all_vault:
                if len(priority_pids) >= 12:
                    break
                if vp["id"] not in priority_pids:
                    priority_pids.append(vp["id"])

            # --- STEP 4: 300+DESK PROCESSING + JEV SCORING ---
            desk300_nnn = ""
            strong_pick_cnt = 0
            maybe_cnt = 0
            pass_cnt = 0

            ran_desk_pipeline = False
            if sched["use_300desk"] and priority_pids and self.desk_pipeline is not None:
                try:
                    d_run = self.desk_pipeline.process_single_or_batch_sync(
                        product_ids=priority_pids[:12],
                        mode="vault_process",
                        exec_engine="gateway_fast",
                        auto_assign_my_shop=True,
                    )
                    desk300_nnn = d_run.get("nnn_code") or ""
                    strong_pick_cnt = int(d_run.get("strong_pick_count") or 0)
                    maybe_cnt = int(d_run.get("maybe_count") or 0)
                    pass_cnt = int(d_run.get("pass_count") or 0)
                    ran_desk_pipeline = True
                except Exception:
                    ran_desk_pipeline = False

            if not ran_desk_pipeline and sched["auto_score_jev"] and priority_pids and self.products.jev:
                for pid in priority_pids[:10]:
                    try:
                        p_sc = self.products.score_product_jev(pid)
                        sc = float(p_sc.get("jev_score") or 0.0)
                        if sc >= 7.6:
                            strong_pick_cnt += 1
                        elif sc >= 6.0:
                            maybe_cnt += 1
                        else:
                            pass_cnt += 1
                    except Exception:
                        break

            # --- STEP 5: AUTOMATIC BUCKET, STATUS & INDUSTRY CLASSIFICATION ---
            refreshed_all = self.products.get_products_by_ids(discovered_pids)
            bucket_breakdown: dict[str, int] = {}
            if sched["auto_classify_buckets"]:
                for p in refreshed_all:
                    j_sc = p.get("jev_score")
                    d3_meta = p.get("desk300") or {}
                    d_tier = d3_meta.get("decision_tier") or ""
                    target_bucket = p["bucket"]
                    target_status = p["status"]

                    if (d_tier == "strong_pick" or (j_sc is not None and float(j_sc) >= 7.8)) and sched["auto_promote_strong_pick"]:
                        if p["status"] not in ("dang_ban", "bo_qua"):
                            target_bucket = "dang_nhap_ban"
                            target_status = "nhap_test"
                    elif j_sc is not None and p["status"] != "bo_qua" and p["bucket"] in ("cho_danh_gia", "chua_cham"):
                        sc_f = float(j_sc)
                        if sc_f < 4.2 and int(p.get("sold_count") or 0) <= 0:
                            target_bucket = "da_loai"
                        else:
                            target_bucket = self.products.auto_bucket_from_seller_metrics(
                                sc_f, int(p.get("sold_count") or 0), float(p.get("cost_vnd") or 0.0), bool(p.get("is_mall"))
                            )

                    if target_bucket != p["bucket"] or target_status != p["status"]:
                        try:
                            updated_p = self.products.update_product(
                                p["id"], {"bucket": target_bucket, "status": target_status}
                            )
                            p["bucket"] = updated_p["bucket"]
                            p["status"] = updated_p["status"]
                        except Exception:
                            pass
                    bucket_breakdown[p["bucket"]] = bucket_breakdown.get(p["bucket"], 0) + 1
            else:
                for p in refreshed_all:
                    bucket_breakdown[p["bucket"]] = bucket_breakdown.get(p["bucket"], 0) + 1

            scored_sorted = sorted(
                [p for p in refreshed_all if p.get("jev_score") is not None],
                key=lambda x: float(x.get("jev_score") or 0.0),
                reverse=True,
            )

            # Synthesize Executive Daily Digest via 300+desk (or deterministic metrics fallback)
            desk_synthesis = self._synthesize_daily_digest(
                sched_name=sched["name"],
                keywords=keywords,
                total_sampled=len(cur_map),
                new_items=new_items,
                rising_items=rising_items,
                painpoints=painpoints_objs,
                top_scored=scored_sorted,
                use_300desk=bool(sched["use_300desk"]),
            )

            # --- STEP 6: PERSIST RUN, ADVANCE NEXT SCHEDULE & EMIT TELEGRAM + GS-XXXX LOG ---
            dur_ms = int((time.monotonic() - t0) * 1000)
            ts_done = now()
            nxt_utc = (
                compute_next_run_utc(sched["schedule_mode"], sched["daily_time"], sched["interval_hours"])
                if sched["status"] == "active"
                else ""
            )
            next_snapshot = {
                "initialized": True,
                "captured_at": ts_done,
                "total_sampled": len(cur_map),
                "items_by_key": cur_map,
            }

            headline = (
                f"Khởi tạo mốc gốc '{sched['name']}': {len(cur_map)} SP · "
                + (f"300+desk #{desk300_nnn} · " if desk300_nnn else "")
                + f"Jev chọn {strong_pick_cnt} Strong Pick, {maybe_cnt} Maybe"
                if is_baseline
                else f"Phiên lặp lại '{sched['name']}': {len(cur_map)} SP (+{len(new_items)} SP mới · {len(rising_items)} SP tăng bán) · "
                + (f"300+desk #{desk300_nnn} · " if desk300_nnn else "")
                + f"Jev chốt {strong_pick_cnt} Strong Pick"
            )

            run_id = f"hsrun_{uuid.uuid4().hex[:10]}"
            last_summary = {
                "run_id": run_id,
                "is_initial_baseline": is_baseline,
                "total_sampled": len(cur_map),
                "new_products_count": len(new_items),
                "rising_products_count": len(rising_items),
                "painpoints_count": len(painpoint_ids),
                "desk300_nnn": desk300_nnn,
                "strong_pick_count": strong_pick_cnt,
                "maybe_count": maybe_cnt,
                "pass_count": pass_cnt,
                "bucket_breakdown": bucket_breakdown,
                "desk_synthesis": desk_synthesis,
                "headline": headline,
            }

            with self.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO hunt_schedule_runs
                    (run_id, schedule_id, trigger_kind, status, total_sampled, new_products_count,
                     rising_products_count, painpoints_count, desk300_nnn, strong_pick_count, maybe_count, pass_count,
                     desk_synthesis_text, bucket_breakdown_json, product_ids_json, new_items_json,
                     rising_items_json, painpoint_ids_json, duration_ms, created_at)
                    VALUES (?, ?, ?, 'completed', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        schedule_id,
                        trigger_kind,
                        len(cur_map),
                        len(new_items),
                        len(rising_items),
                        len(painpoint_ids),
                        desk300_nnn,
                        strong_pick_cnt,
                        maybe_cnt,
                        pass_cnt,
                        desk_synthesis,
                        json.dumps(bucket_breakdown, ensure_ascii=False),
                        json.dumps(discovered_pids[:60]),
                        json.dumps(new_items[:25], ensure_ascii=False),
                        json.dumps(rising_items[:25], ensure_ascii=False),
                        json.dumps(painpoint_ids, ensure_ascii=False),
                        dur_ms,
                        ts_done,
                    ),
                )
                conn.execute(
                    """
                    UPDATE hunt_schedules
                    SET runs_count = runs_count + 1, last_run_at=?, next_run_at=?,
                        baseline_snapshot_json=?, last_summary_json=?, updated_at=?
                    WHERE schedule_id=?
                    """,
                    (
                        ts_done,
                        nxt_utc,
                        json.dumps(next_snapshot, ensure_ascii=False),
                        json.dumps(last_summary, ensure_ascii=False),
                        ts_done,
                        schedule_id,
                    ),
                )

            highlights: list[str] = [f"Tổng hợp 300+desk: {desk_synthesis[:180]}"]
            for ni in new_items[:3]:
                highlights.append(f"🆕 SP mới: {ni['title'][:65]} ({ni['price_vnd']:,.0f}đ · bán {ni['sold_count']})")
            for ri in rising_items[:2]:
                highlights.append(f"📈 Tăng bán +{ri['delta_sold']}: {ri['title'][:65]}")
            for sp in scored_sorted[:2]:
                highlights.append(
                    f"🏆 Jev {sp.get('jev_score')}/10 [{BUCKETS.get(sp['bucket'], sp['bucket'])}]: {sp['title'][:60]}"
                )

            if self.history_logs is not None and trigger_kind == "scheduled":
                self.history_logs.record_event(
                    module="hunt",
                    action_type="scheduled_hunt_autopilot",
                    title=f"⏰ Lịch săn lặp lại: {sched['name']}",
                    status="completed",
                    duration_ms=dur_ms,
                    summary=headline,
                    payload={"schedule_id": schedule_id, "run_id": run_id, "highlights": highlights, **last_summary},
                    notify_telegram=True,
                )

            return {
                "run": self.get_run(run_id),
                "schedule": self.get_schedule(schedule_id),
                "highlights": highlights,
                "summary": headline,
            }
        finally:
            lock.release()

    def run_due_schedules(self) -> int:
        ts = now()
        with self.connect() as conn:
            due = conn.execute(
                "SELECT schedule_id FROM hunt_schedules WHERE status='active' AND next_run_at != '' AND next_run_at <= ? ORDER BY next_run_at ASC LIMIT 2",
                (ts,),
            ).fetchall()
        cnt = 0
        for r in due:
            sid = r["schedule_id"]
            try:
                self.execute_schedule_run(sid, trigger_kind="scheduled")
                cnt += 1
            except Exception as exc:
                retry_at = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
                with self.connect() as conn:
                    conn.execute("UPDATE hunt_schedules SET next_run_at=?, updated_at=? WHERE schedule_id=?", (retry_at, now(), sid))
                if self.history_logs is not None:
                    self.history_logs.record_event(
                        module="hunt",
                        action_type="scheduled_hunt_autopilot",
                        title=f"⏰ Lỗi Lịch săn lặp lại ({sid})",
                        status="failed",
                        summary=str(exc)[:260],
                        payload={"schedule_id": sid},
                        notify_telegram=True,
                    )
        return cnt

    def list_schedules(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM hunt_schedules WHERE status != 'archived' ORDER BY updated_at DESC"
            ).fetchall()
        return [self._format_schedule_row(r) for r in rows]

    def get_schedule(self, schedule_id: str, include_runs: bool = False) -> dict | None:
        with self.connect() as conn:
            r = conn.execute("SELECT * FROM hunt_schedules WHERE schedule_id=?", (schedule_id,)).fetchone()
        if not r:
            return None
        d = self._format_schedule_row(r)
        if include_runs:
            d["runs"] = self.list_runs(schedule_id=schedule_id, limit=25)
        return d

    def get_run(self, run_id: str) -> dict | None:
        with self.connect() as conn:
            r = conn.execute("SELECT * FROM hunt_schedule_runs WHERE run_id=?", (run_id,)).fetchone()
        return self._format_run_row(r, include_products=True) if r else None

    def list_runs(self, schedule_id: str = "", limit: int = 20) -> list[dict]:
        with self.connect() as conn:
            if schedule_id:
                rows = conn.execute(
                    "SELECT * FROM hunt_schedule_runs WHERE schedule_id=? ORDER BY created_at DESC, rowid DESC LIMIT ?",
                    (schedule_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM hunt_schedule_runs ORDER BY created_at DESC, rowid DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._format_run_row(r, include_products=False) for r in rows]

    @staticmethod
    def _format_schedule_row(r) -> dict:
        mode = r["schedule_mode"]
        dtime = r["daily_time"]
        ihrs = float(r["interval_hours"] or 24.0)
        cadence_label = f"Hàng ngày lúc {dtime}" if mode == "daily_time" else f"Lặp lại mỗi {ihrs:g} giờ"
        return {
            "schedule_id": r["schedule_id"],
            "name": r["name"],
            "status": r["status"],
            "schedule_mode": mode,
            "daily_time": dtime,
            "interval_hours": ihrs,
            "cadence_label": cadence_label,
            "keywords": json.loads(r["keywords_json"] or "[]"),
            "pinned_products": json.loads(r["pinned_products_json"] or "[]"),
            "channels": json.loads(r["channels_json"] or "[]"),
            "shopee_filters": json.loads(r["shopee_filters_json"] or "{}"),
            "items_per_channel": r["items_per_channel"],
            "use_300desk": bool(r["use_300desk"]),
            "auto_score_jev": bool(r["auto_score_jev"]),
            "auto_classify_buckets": bool(r["auto_classify_buckets"]),
            "auto_promote_strong_pick": bool(r["auto_promote_strong_pick"]),
            "runs_count": r["runs_count"],
            "last_run_at": r["last_run_at"],
            "next_run_at": r["next_run_at"],
            "last_summary": json.loads(r["last_summary_json"] or "{}"),
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }

    def _format_run_row(self, r, include_products: bool = False) -> dict:
        pids = json.loads(r["product_ids_json"] or "[]")
        d = {
            "run_id": r["run_id"],
            "schedule_id": r["schedule_id"],
            "trigger_kind": r["trigger_kind"],
            "status": r["status"],
            "total_sampled": r["total_sampled"],
            "new_products_count": r["new_products_count"],
            "rising_products_count": r["rising_products_count"],
            "painpoints_count": r["painpoints_count"],
            "desk300_nnn": r["desk300_nnn"],
            "strong_pick_count": r["strong_pick_count"],
            "maybe_count": r["maybe_count"],
            "pass_count": r["pass_count"],
            "desk_synthesis_text": r["desk_synthesis_text"],
            "bucket_breakdown": json.loads(r["bucket_breakdown_json"] or "{}"),
            "product_ids": pids,
            "new_items": json.loads(r["new_items_json"] or "[]"),
            "rising_items": json.loads(r["rising_items_json"] or "[]"),
            "painpoint_ids": json.loads(r["painpoint_ids_json"] or "[]"),
            "duration_ms": r["duration_ms"],
            "created_at": r["created_at"],
        }
        if include_products and pids:
            d["products"] = self.products.get_products_by_ids(pids[:30])
        return d

    def dispatch(self, path: str, method: str, env, read_json):
        if path == "/api/hunt/schedules" and method == "GET":
            return "200 OK", {
                "schedules": self.list_schedules(),
                "recent_runs": self.list_runs(limit=15),
                "bucket_labels": BUCKETS,
            }
        if path == "/api/hunt/schedules" and method == "POST":
            return "200 OK", self.create_schedule(json_object(read_json, env))
        if path.startswith("/api/hunt/schedules/"):
            parts = path.strip("/").split("/")
            sid = parts[3] if len(parts) >= 4 else ""
            if len(parts) == 4 and method == "GET":
                if sid == "runs" and len(parts) >= 5:
                    pass
                sched = self.get_schedule(sid, include_runs=True)
                if not sched:
                    raise ApiError("404 Not Found", "Không tìm thấy lịch săn lặp lại")
                return "200 OK", {"schedule": sched, "bucket_labels": BUCKETS}
            if len(parts) == 5 and parts[3] == "runs" and method == "GET":
                run_obj = self.get_run(parts[4])
                if not run_obj:
                    raise ApiError("404 Not Found", "Không tìm thấy phiên chạy này")
                return "200 OK", {"run": run_obj, "bucket_labels": BUCKETS}
            if len(parts) == 4 and method == "PATCH":
                return "200 OK", self.update_schedule(sid, json_object(read_json, env))
            if len(parts) == 4 and method == "DELETE":
                return "200 OK", self.delete_schedule(sid)
            if len(parts) == 5 and parts[4] == "run" and method == "POST":
                return "200 OK", self.execute_schedule_run(sid, trigger_kind="manual")
            if len(parts) == 5 and parts[4] in ("pause", "resume") and method == "POST":
                new_st = "paused" if parts[4] == "pause" else "active"
                return "200 OK", self.update_schedule(sid, {"status": new_st})
        return None


class HuntSchedulerDaemon:
    def __init__(self, schedule_service: HuntScheduleService, poll_sec: float = 30.0):
        self.schedules = schedule_service
        self.poll_sec = poll_sec
        self._started = False

    def start(self):
        if self._started:
            return
        self._started = True
        threading.Thread(target=self._loop, name="gs-hunt-autopilot-scheduler", daemon=True).start()

    def _loop(self):
        while True:
            time.sleep(self.poll_sec)
            try:
                self.schedules.run_due_schedules()
            except Exception:
                pass
