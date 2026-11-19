"""Multi-Channel Seller Product Hunter: Google Trends + Social Painpoints (Facebook, Threads, X, Reddit) -> Product Solution Discovery (Shopee, TikTok Shop, Lazada) + Creator Tool."""
import json
import re
import uuid

from . import settings
from .products import INDUSTRIES, INDUSTRY_ICONS, infer_industry
from .responses import ApiError, json_object, now, text

SOCIAL_PAINPOINT_CHANNELS = ("facebook_organic", "facebook_ads", "threads", "x", "reddit")
MARKETPLACE_CHANNELS = ("shopee", "tiktok_shop", "lazada")

PAINPOINT_LEXICON_MAP: list[tuple[tuple[str, ...], str, list[str]]] = [
    (
        ("ẩm mốc", "mùi hôi", "cống", "nhà tắm", "nhà vệ sinh", "toilet", "thoát sàn"),
        "Nhà tắm / khu vực ẩm bị mùi hôi cống & nấm mốc bám đen khó cọ rửa",
        ["phễu thoát sàn ngăn mùi", "xịt tẩy nấm mốc nhà tắm", "sáp thơm khử mùi toilet", "máy hút ẩm mini"],
    ),
    (
        ("đau lưng", "mỏi cổ", "vai gáy", "văn phòng", "ngồi lâu", "cột sống", "tê tay"),
        "Đau mỏi cổ vai gáy & thắt lưng do ngồi làm việc/lái xe nhiều giờ",
        ["máy massage cổ vai gáy", "đệm tựa lưng công thái học", "gối kê cổ văn phòng", "giá đỡ laptop nhôm"],
    ),
    (
        ("bếp chật", "chai lọ", "bừa bộn", "dầu mỡ", "nhà bếp", "gia vị", "chậu rửa"),
        "Không gian bếp chật, nhiều chai lọ lộn xộn & bám bẩn dầu mỡ",
        ["kệ gia vị xoay 360 độ", "kệ gầm bếp đa năng", "giấy lau bếp đa năng tẩy dầu mỡ", "rổ lọc rác bồn rửa bát"],
    ),
    (
        ("nóng", "mất điện", "phòng trọ", "oi bức", "hầm bí", "mồ hôi"),
        "Phòng ở / di chuyển ngoài trời nóng bức, hầm bí hoặc hay mất điện",
        ["quạt cầm tay mini làm lạnh", "quạt tích điện gấp gọn", "chiếu điều hoà làm mát", "áo điều hoà quạt gió"],
    ),
    (
        ("lông chó", "lông mèo", "thú cưng", "cát mèo", "bám quần áo"),
        "Lông chó mèo rụng bám đầy quần áo/sofa & mùi hôi khay vệ sinh thú cưng",
        ["cây lăn bụi lông thú cưng", "lược chải lông chó mèo tự đẩy", "máy lọc mùi khay cát mèo", "túi tắm mèo chống cào"],
    ),
    (
        ("mất ngủ", "khó ngủ", "tiếng ồn", "ngáy", "ánh sáng"),
        "Khó đi vào giấc ngủ, dễ tỉnh giấc vì tiếng ồn xung quanh & ánh sáng",
        ["nút bịt tai chống ồn ngủ ngon", "bịt mắt ngủ chườm ấm", "máy tạo tiếng ồn trắng mini", "tinh dầu xịt thơm gối"],
    ),
    (
        ("dây điện", "ổ cắm", "bàn làm việc", "sạc rối", "cáp sạc"),
        "Bàn làm việc nhiều dây sạc chằng chịt, ổ điện bừa bộn mất thẩm mỹ",
        ["hộp đựng ổ điện giấu dây", "kẹp giữ dây cáp nam châm", "khay treo ổ điện gầm bàn", "ổ cắm tháp đa năng"],
    ),
    (
        ("pha sữa", "mẹ bỉm", "ăn dặm", "rửa bình", "khóc đêm", "bé"),
        "Mẹ bỉm vất vả dậy pha sữa đêm, tiệt trùng bình & chuẩn bị đồ ăn dặm",
        ["máy hâm sữa tiệt trùng điện tử", "bình đun nước pha sữa giữ nhiệt", "máy xay ăn dặm mini", "cọ rửa bình sữa điện"],
    ),
    (
        ("mụn", "lỗ chân lông", "da dầu", "tẩy trang", "chống nắng", "tóc rụng"),
        "Da đổ dầu bít tắc lỗ chân lông, tóc gãy rụng cần chăm sóc nhanh tại nhà",
        ["máy rửa mặt sóng âm", "lược gội đầu massage silicon", "máy xông hơi mặt mini", "bình xịt khoáng nano"],
    ),
    (
        ("muỗi", "côn trùng", "kiến", "gián", "cắm trại", "dã ngoại"),
        "Muỗi, kiến, gián trong nhà hoặc khi đi dã ngoại gây ngứa & mất vệ sinh",
        ["đèn bắt muỗi thông minh", "vợt muỗi kiêm đèn bắt muỗi", "bẫy gián sinh học an toàn", "xịt chống muỗi thiên nhiên"],
    ),
    (
        ("quần áo nhăn", "tủ quần áo", "giày hôi", "ẩm giày", "du lịch"),
        "Tủ đồ chật cứng, quần áo nhăn khi đi công tác/du lịch & giày ướt hôi mùa mưa",
        ["bàn ủi hơi nước cầm tay gấp gọn", "túi hút chân không đựng quần áo", "máy sấy khử mùi giày", "hộp đựng giày trong suốt"],
    ),
]

PRODUCT_NOUN_RE = re.compile(
    r"\b((?:máy|kệ|hộp|dụng cụ|bình|quạt|đèn|túi|gối|đệm|lược|xịt|miếng dán|giá đỡ|cây lăn|nút bịt|bàn ủi|ổ cắm)\s+[a-zA-ZÀ-ỹ0-9\s]{3,28})",
    re.IGNORECASE,
)

PAIN_SIGNAL_WORDS = (
    "bị", "đau", "mỏi", "hỏng", "hôi", "ẩm", "mốc", "nóng", "chật", "bừa", "ồn", "khó",
    "cứu", "tìm mua", "loại nào tốt", "recommend", "review", "bất tiện", "tốn thời gian",
    "mệt", "phiền", "rối", "struggling", "annoying", "problem", "fix", "best", "help",
)


def derive_painpoint_and_product_keywords(topic_query: str, posts: list[dict], jev_eval: dict | None = None) -> tuple[str, str, list[str]]:
    """Analyze social posts around a topic to synthesize a clear painpoint statement and concrete product search keywords."""
    combined_text = (topic_query + " " + " ".join(p.get("text", "") for p in posts[:12])).lower()
    pain_title = ""
    candidate_kws: list[str] = []

    for triggers, title_tpl, prod_kws in PAINPOINT_LEXICON_MAP:
        if any(t in combined_text for t in triggers):
            if not pain_title:
                pain_title = title_tpl
            for pk in prod_kws:
                if pk not in candidate_kws:
                    candidate_kws.append(pk)

    # Also mine concrete product noun phrases mentioned by commenters/users as solutions
    for p in posts[:12]:
        for m in PRODUCT_NOUN_RE.finditer(p.get("text") or ""):
            phrase = re.sub(r"\s+", " ", m.group(1)).strip(" ,.;:!?-\n\t")
            words = phrase.split()
            if 2 <= len(words) <= 6 and phrase.lower() not in {x.lower() for x in candidate_kws}:
                candidate_kws.append(phrase)

    # Fallback based on Jev solution archetype or cleaned topic query
    clean_topic = topic_query.strip().lstrip("#")
    if not candidate_kws:
        arch = (jev_eval or {}).get("solution_archetype") or ""
        arch_prefix = {
            "dung_cu_tien_ich_thong_minh": f"dụng cụ {clean_topic} thông minh",
            "thiet_bi_dien_tu_mini": f"máy {clean_topic} mini",
            "luu_tru_sap_xep_gon": f"kệ {clean_topic} đa năng",
            "ve_sinh_khu_mui_diet_khuan": f"xịt vệ sinh {clean_topic}",
            "cham_soc_suc_khoe_giam_dau": f"máy massage {clean_topic}",
        }.get(arch, "")
        if arch_prefix:
            candidate_kws.append(arch_prefix)
        candidate_kws.append(clean_topic)

    if not pain_title:
        pain_title = f"Nhu cầu & nỗi đau thực tế của người dùng xoay quanh '{clean_topic}'"

    # Summarize top complaint snippets
    pain_snippets = []
    for p in posts[:5]:
        txt = re.sub(r"\s+", " ", p.get("text") or "").strip()
        if txt:
            pain_snippets.append(f"[{p.get('channel', 'social').upper()}] {txt[:140]}")
    pain_summary = " · ".join(pain_snippets[:3]) if pain_snippets else f"Tổng hợp tín hiệu tìm kiếm giải pháp cho '{clean_topic}'."

    return pain_title[:200], pain_summary[:600], candidate_kws[:6]


class HuntAndCreatorsService:
    def __init__(self, connect, secrets, products, jobs, apify=None, treg=None, jev=None):
        self.connect = connect
        self.secrets = secrets
        self.products = products
        self.jobs = jobs
        self.apify = apify
        self.treg = treg
        self.jev = jev
        self._last_job_id = ""

    def estimate_hunt(self, body: dict) -> dict:
        cfg = settings.read_settings(self.connect, self.secrets)
        channels = body.get("channels") or cfg["hunt"]["channels"]
        terms = [t.strip() for t in (body.get("keywords") or []) if str(t).strip()]
        if not terms and body.get("keyword"):
            terms = [str(body["keyword"]).strip()]
        if not terms:
            terms = cfg["hunt"]["niches"][:2]
        auto_jev = bool(body.get("auto_score_jev", cfg["hunt"]["auto_score_jev"]))

        gt_cost = 0.015 * len(terms) if "google_trends" in channels else 0.0
        social_chs = [c for c in channels if c in SOCIAL_PAINPOINT_CHANNELS]
        mkt_chs = [c for c in channels if c in MARKETPLACE_CHANNELS or c == "tiktok"]
        social_cost = len(terms) * len(social_chs) * 0.022
        mkt_cost = max(1, len(terms)) * max(1, len(mkt_chs)) * 0.032 if mkt_chs else 0.0
        jev_est = (len(terms) * 5 * 0.0006) if auto_jev else 0.0
        est_usd = round(gt_cost + social_cost + mkt_cost + jev_est, 4)
        return {
            "terms": terms,
            "channels": channels,
            "social_painpoint_channels": social_chs,
            "marketplace_channels": mkt_chs,
            "use_google_trends": "google_trends" in channels,
            "auto_score_jev": auto_jev,
            "estimated_cost_usd": est_usd,
            "budget_limit_usd": float(body.get("budget_limit_usd") or cfg["hunt"]["max_session_cost_usd"]),
        }

    def _search_marketplace_products(self, ctx, channel: str, term: str, limit: int, apify_toks: list[str], treg_tok: str) -> list[dict]:
        found_rows: list[dict] = []
        if channel == "shopee" and apify_toks and self.apify:
            try:
                _, found_rows = ctx.run_step(
                    f"shopee:{term}",
                    "apify",
                    0.035,
                    lambda t=term: self.apify.search_shopee(apify_toks, t, limit=limit),
                )
            except Exception as exc:
                ctx.log(f"⚠️ Shopee '{term}': {exc}")
        elif channel in ("tiktok", "tiktok_shop"):
            if apify_toks and self.apify:
                try:
                    _, found_rows = ctx.run_step(
                        f"tiktok_shop:{term}",
                        "apify",
                        0.035,
                        lambda t=term: self.apify.search_tiktok_shop(apify_toks, t, limit=limit),
                    )
                except Exception as exc:
                    ctx.log(f"⚠️ Apify TikTok Shop '{term}': {exc}")
            if not found_rows and treg_tok and self.treg:
                try:
                    _, found_rows, _ = ctx.run_step(
                        f"treg_tiktok:{term}",
                        "treg",
                        0.025,
                        lambda t=term: self.treg.search_tiktok_shop(treg_tok, t, limit=limit),
                    )
                except Exception as exc:
                    ctx.log(f"⚠️ Treg TikTok Shop '{term}': {exc}")
        elif channel == "lazada" and apify_toks and self.apify:
            try:
                _, found_rows = ctx.run_step(
                    f"lazada:{term}",
                    "apify",
                    0.035,
                    lambda t=term: self.apify.search_lazada(apify_toks, t, limit=limit),
                )
            except Exception as exc:
                ctx.log(f"⚠️ Lazada '{term}': {exc}")
        return found_rows

    def _collect_social_posts_for_term(self, term: str, channels: list[str], limit_per_ch: int, apify_toks: list[str], treg_tok: str, log_fn=None) -> list[dict]:
        posts: list[dict] = []
        for ch in channels:
            ch_posts: list[dict] = []
            # Build painpoint-focused query for Reddit / X / FB / Threads
            q_social = term
            if ch == "reddit" and not any(w in term.lower() for w in ("recommend", "best", "loại nào", "review")):
                q_social = f"{term} review OR recommend OR loại nào tốt"

            if apify_toks and self.apify:
                try:
                    slug, ch_posts = self.apify.search_social_painpoints(apify_toks, ch, q_social, limit=limit_per_ch)
                    if log_fn:
                        log_fn(f"✓ Apify {ch} ({slug}): {len(ch_posts)} bài thảo luận")
                except Exception as exc:
                    if log_fn:
                        log_fn(f"⚠️ Apify {ch} '{term}' chuyển sang Treg dự phòng ({exc})")
                    ch_posts = []

            if not ch_posts and treg_tok and self.treg:
                try:
                    ep, ch_posts, _ = self.treg.search_social_painpoints(treg_tok, ch, term, limit=limit_per_ch)
                    if log_fn:
                        log_fn(f"✓ Treg {ch} ({ep}): {len(ch_posts)} bài thảo luận")
                except Exception as exc:
                    if log_fn:
                        log_fn(f"⚠️ Treg {ch} '{term}': {exc}")
                    ch_posts = []

            posts.extend(ch_posts)

        # Rank posts that contain explicit painpoint / buyer-intent signals higher
        def _pain_rank(p: dict) -> tuple[int, int]:
            tl = (p.get("text") or "").lower()
            hits = sum(1 for w in PAIN_SIGNAL_WORDS if w in tl)
            eng = int(p.get("likes") or 0) + int(p.get("comments") or 0) * 3 + int(p.get("shares") or 0) * 2
            return (hits, eng)

        posts.sort(key=_pain_rank, reverse=True)
        return posts

    def start_hunt(self, body: dict) -> dict:
        est = self.estimate_hunt(body)
        cfg = settings.read_settings(self.connect, self.secrets)
        apify_toks = settings.apify_tokens(cfg)
        treg_tok = (cfg["providers"].get("treg_key") or "").strip()
        jev_key = (cfg["providers"].get("typesafe_key") or "").strip()
        items_per_ch = max(3, min(30, int(body.get("items_per_channel") or cfg["hunt"]["items_per_channel"])))

        def _worker(ctx):
            discovered_ids: list[int] = []
            painpoint_ids: list[str] = []
            product_search_terms: list[tuple[str, str]] = [(t, "seed") for t in est["terms"]]

            # --- STAGE 1: GOOGLE TRENDS BREAKOUT EXPANSION ---
            if est["use_google_trends"]:
                ctx.check_cancelled()
                ctx.log(f"📈 [Bước 1] Quét từ khoá Đột phá Google Trends VN cho: {', '.join(est['terms'][:4])}")
                try:
                    gt_res = self.google_trends_explore_multi(
                        seed_terms=est["terms"][:4],
                        geo="VN",
                        time_range=str(body.get("time_range") or "today 3-m"),
                        score_jev=bool(jev_key and est["auto_score_jev"]),
                    )
                    rising_kws = [
                        k["keyword"]
                        for k in (gt_res.get("keywords") or [])
                        if k.get("kind") in ("rising", "top") and (k.get("jev_score_10") is None or float(k.get("jev_score_10") or 0) >= 5.5)
                    ][:3]
                    for rk in rising_kws:
                        if rk.lower() not in {x[0].lower() for x in product_search_terms}:
                            product_search_terms.append((rk, "google_trends"))
                    ctx.log(f"✓ Google Trends ({gt_res.get('provider')}): mở rộng thêm {len(rising_kws)} từ khoá xu hướng -> {rising_kws}")
                except Exception as exc:
                    ctx.log(f"⚠️ Google Trends bỏ qua lỗi nhẹ: {exc}")

            # --- STAGE 2: SOCIAL PAINPOINT MINING (FACEBOOK · THREADS · X · REDDIT) ---
            social_chs = est["social_painpoint_channels"]
            painpoint_kw_links: dict[str, str] = {}
            if social_chs:
                for term in est["terms"]:
                    ctx.check_cancelled()
                    ctx.log(f"🧠 [Bước 2] Săn Painpoint khách hàng cho '{term}' trên {', '.join(social_chs)}")
                    pp_res = self.discover_painpoints(
                        topic_query=term,
                        channels=social_chs,
                        limit_per_channel=min(8, items_per_ch),
                        auto_find_products=False,
                        job_id=ctx.job_id,
                        log_fn=ctx.log,
                    )
                    pp = pp_res["painpoint"]
                    painpoint_ids.append(pp["painpoint_id"])
                    for rec_kw in (pp.get("recommended_keywords") or [])[:2]:
                        if rec_kw.lower() not in {x[0].lower() for x in product_search_terms}:
                            product_search_terms.append((rec_kw, f"painpoint:{pp['painpoint_id']}"))
                        painpoint_kw_links[rec_kw.lower()] = pp["painpoint_id"]

            # --- STAGE 3: MARKETPLACE PRODUCT HUNTING (SHOPEE · TIKTOK SHOP · LAZADA) ---
            mkt_chs = est["marketplace_channels"]
            if not mkt_chs and social_chs:
                # Automatically hunt matching products on TikTok Shop & Shopee when user hunts painpoints!
                mkt_chs = ["shopee", "tiktok_shop"]
                ctx.log("🛒 Tự động kích hoạt tìm Sản phẩm Giải pháp trên Shopee & TikTok Shop từ các Painpoint vừa phát hiện!")

            matched_by_pp: dict[str, list[int]] = {}
            for search_term, origin_tag in product_search_terms[:8]:
                ctx.check_cancelled()
                ctx.log(f"🔎 [Bước 3] Tìm sản phẩm trên {', '.join(mkt_chs)} cho từ khoá: '{search_term}' (nguồn: {origin_tag})")
                for ch in mkt_chs:
                    ctx.check_cancelled()
                    found_rows = self._search_marketplace_products(ctx, ch, search_term, items_per_ch, apify_toks, treg_tok)
                    for r in found_rows:
                        if r.get("title"):
                            if origin_tag.startswith("painpoint:"):
                                r["note"] = f"Giải pháp cho Painpoint ({search_term})"
                            saved = self.products.upsert_product(r, source=f"hunt:{ch}:{origin_tag}:{search_term}")
                            if saved["id"] not in discovered_ids:
                                discovered_ids.append(saved["id"])
                            pp_id = painpoint_kw_links.get(search_term.lower()) or (origin_tag.split(":", 1)[1] if origin_tag.startswith("painpoint:") else "")
                            if pp_id:
                                matched_by_pp.setdefault(pp_id, [])
                                if saved["id"] not in matched_by_pp[pp_id]:
                                    matched_by_pp[pp_id].append(saved["id"])
                    ctx.log(f"✓ Kênh {ch} ('{search_term}'): thu thập {len(found_rows)} sản phẩm")

            # Link discovered products back to their originating Painpoints
            if matched_by_pp:
                with self.connect() as conn:
                    for pp_id, pids in matched_by_pp.items():
                        conn.execute(
                            "UPDATE painpoint_discoveries SET matched_product_ids_json=?, updated_at=? WHERE painpoint_id=?",
                            (json.dumps(pids[:25]), now(), pp_id),
                        )

            # --- STAGE 4: 300+DESK PRODUCT PROCESSING (IF ENABLED) + JEV FINAL DECISION ---
            enriched = 0
            scored = 0
            desk300_nnn = ""
            use_desk = bool(body.get("use_300desk", False)) and getattr(self, "desk_pipeline", None) is not None

            if use_desk and discovered_ids:
                ctx.check_cancelled()
                ctx.log(f"🤖 [Bước 4] Đưa {len(discovered_ids[:12])} SP vào luồng xử lý 300+desk (OPi SOCKS5) -> Jev AI ra quyết định...")
                try:
                    d_run = self.desk_pipeline.process_single_or_batch_sync(
                        product_ids=discovered_ids[:12],
                        mode="vault_process",
                        exec_engine="gateway_fast",
                        auto_assign_my_shop=True,
                        log_fn=ctx.log,
                    )
                    desk300_nnn = d_run["nnn_code"]
                    scored = len(d_run["output_product_ids"])
                except Exception as exc:
                    ctx.log(f"⚠️ 300+desk dừng an toàn ({exc}) — chuyển sang làm giàu & Jev trực tiếp")
                    use_desk = False

            if not use_desk:
                for pid in discovered_ids[:8]:
                    ctx.check_cancelled()
                    p_cur = self.products.get_product(pid)
                    if p_cur and float(p_cur.get("price_vnd") or 0) <= 0 and int(p_cur.get("sold_count") or 0) <= 0:
                        try:
                            p_after = self.products.enrich_product(pid)
                            if p_after and (p_after.get("price_vnd", 0) > 0 or p_after.get("sold_count", 0) > 0):
                                enriched += 1
                        except Exception:
                            pass

                if est["auto_score_jev"] and discovered_ids:
                    for pid in discovered_ids[:8]:
                        ctx.check_cancelled()
                        try:
                            self.products.score_product_jev(pid)
                            scored += 1
                        except Exception as exc:
                            ctx.log(f"⚠️ Chấm Jev SP #{pid}: {exc}")
                            break

            summary = (
                f"Săn đa tầng hoàn tất: {len(painpoint_ids)} Painpoint MXH · "
                f"lưu {len(discovered_ids)} SP vào Kho (Chờ đánh giá)"
                + (f" · xử lý 300+desk #{desk300_nnn}" if desk300_nnn else f" · làm giàu {enriched} SP")
                + f" · Jev quyết định {scored} SP"
            )
            ctx.log(f"🏁 {summary}")
            return {
                "discovered_count": len(discovered_ids),
                "painpoints_count": len(painpoint_ids),
                "painpoint_ids": painpoint_ids,
                "desk300_nnn": desk300_nnn,
                "scored_jev_count": scored,
                "product_ids": discovered_ids,
                "summary": summary,
            }

        job = self.jobs.start_job(
            kind="hunt",
            title=f"Săn SP & Painpoint: {', '.join(est['terms'][:3])}",
            target_fn=_worker,
            estimated_cost_usd=est["estimated_cost_usd"],
            budget_limit_usd=est["budget_limit_usd"],
            max_retries=int(cfg["hunt"]["max_retries"]),
            single_active_kind=True,
            meta={"terms": est["terms"], "channels": est["channels"]},
        )
        self._last_job_id = job["id"]
        return job

    # --- GOOGLE TRENDS BREAKOUT EXPLORER (+JEV SCORING & HISTORY) ------------

    def google_trends_explore_multi(
        self,
        seed_terms: list[str],
        geo: str = "VN",
        time_range: str = "today 3-m",
        category: str = "",
        score_jev: bool = True,
    ) -> dict:
        seeds = [str(s).strip() for s in (seed_terms or []) if str(s or "").strip()][:5]
        if not seeds:
            raise ValueError("Vui lòng nhập ít nhất 1 từ khoá gốc để quét Google Trends")

        cfg = settings.read_settings(self.connect, self.secrets)
        apify_toks = settings.apify_tokens(cfg)
        treg_tok = (cfg["providers"].get("treg_key") or "").strip()
        jev_key = (cfg["providers"].get("typesafe_key") or "").strip()

        res_data = None
        if apify_toks and self.apify:
            try:
                res_data = self.apify.explore_google_trends(apify_toks, seeds, geo=geo, time_range=time_range, category=category)
            except Exception:
                res_data = None
        if not res_data and treg_tok and self.treg:
            try:
                res_data = self.treg.explore_google_trends(treg_tok, seeds, geo=geo, time_range=time_range)
            except Exception:
                res_data = None

        if not res_data:
            res_data = {
                "provider": "local_seed",
                "actor_or_endpoint": "seed_expansion",
                "geo": geo,
                "time_range": time_range,
                "seed_summaries": [{"seed_term": s, "current_interest": None, "avg_interest": None, "peak_interest": None, "momentum_pct": None} for s in seeds],
                "keywords": [{"keyword": s, "kind": "seed", "seed_term": s, "growth_label": "Seed", "growth_pct": None, "interest_value": None, "source": "seed"} for s in seeds],
                "cost_usd": 0.0,
            }

        keywords = res_data.get("keywords") or []
        total_cost = float(res_data.get("cost_usd") or 0.0)
        if score_jev and jev_key and self.jev and keywords:
            for kw_obj in keywords[:8]:
                try:
                    j_res = self.jev.score_google_trend_keyword(
                        jev_key,
                        kw_obj,
                        model=cfg["providers"].get("jev_model") or "jev-1.14.0",
                        base_url=cfg["providers"].get("jev_base_url") or "",
                    )
                    kw_obj["jev_score_10"] = j_res["jev_score_10"]
                    kw_obj["buyer_intent"] = j_res["buyer_intent"]
                    kw_obj["industry"] = j_res["industry"]
                    kw_obj["industry_label"] = INDUSTRIES.get(j_res["industry"], j_res["industry"])
                    kw_obj["worth_hunting_prob"] = j_res["worth_hunting_prob"]
                    total_cost += float(j_res.get("_cost_usd") or 0.0006)
                except Exception:
                    break

        run_id = f"gt_{uuid.uuid4().hex[:10]}"
        ts = now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO google_trends_runs
                (run_id, seed_terms_json, geo, time_range, category, provider_used, seed_summaries_json, keywords_json, cost_usd, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    json.dumps(seeds, ensure_ascii=False),
                    geo,
                    time_range,
                    category,
                    f"{res_data['provider']}:{res_data['actor_or_endpoint']}",
                    json.dumps(res_data.get("seed_summaries") or [], ensure_ascii=False),
                    json.dumps(keywords, ensure_ascii=False),
                    round(total_cost, 5),
                    ts,
                ),
            )

        return {
            "run_id": run_id,
            "seed_terms": seeds,
            "provider": res_data["provider"],
            "source_used": f"{res_data['provider']}:{res_data['actor_or_endpoint']}",
            "geo": geo,
            "time_range": time_range,
            "seed_summaries": res_data.get("seed_summaries") or [],
            "keywords": keywords,
            "results": keywords,
            "cost_usd": round(total_cost, 5),
            "summary": f"Google Trends ({', '.join(seeds)}): phát hiện {len(keywords)} từ khoá xu hướng / đột phá",
        }

    def list_google_trends_runs(self, limit: int = 15) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM google_trends_runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [
            {
                "run_id": r["run_id"],
                "seed_terms": json.loads(r["seed_terms_json"] or "[]"),
                "geo": r["geo"],
                "time_range": r["time_range"],
                "provider_used": r["provider_used"],
                "seed_summaries": json.loads(r["seed_summaries_json"] or "[]"),
                "keywords": json.loads(r["keywords_json"] or "[]"),
                "cost_usd": r["cost_usd"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    # --- SOCIAL PAINPOINT DISCOVERY -> AUTOMATIC PRODUCT MATCHING ------------

    def discover_painpoints(
        self,
        topic_query: str,
        channels: list[str] | None = None,
        limit_per_channel: int = 6,
        auto_find_products: bool = True,
        marketplace_channels: list[str] | None = None,
        job_id: str = "",
        log_fn=None,
        injected_posts: list[dict] | None = None,
        injected_products: list[dict] | None = None,
    ) -> dict:
        """Mine real customer painpoints from Facebook, Threads, X, Reddit -> Jev AI Diagnosis -> Find Solution Products."""
        q = text(topic_query, "topic_query", 180, required=True)
        chs = [c for c in (channels or ["facebook_organic", "threads", "x", "reddit"]) if c in SOCIAL_PAINPOINT_CHANNELS]
        if not chs:
            chs = ["facebook_organic", "threads", "reddit"]

        cfg = settings.read_settings(self.connect, self.secrets)
        apify_toks = settings.apify_tokens(cfg)
        treg_tok = (cfg["providers"].get("treg_key") or "").strip()
        jev_key = (cfg["providers"].get("typesafe_key") or "").strip()

        if injected_posts is not None:
            posts = list(injected_posts)
        else:
            posts = self._collect_social_posts_for_term(q, chs, max(2, min(15, int(limit_per_channel))), apify_toks, treg_tok, log_fn=log_fn)

        # 1) Preliminary painpoint synthesis (+ optional `300+desk` synthesis over OPi SOCKS5 when posts present!)
        pain_title, pain_summary, rec_keywords = derive_painpoint_and_product_keywords(q, posts, None)
        if posts and getattr(self, "desk300", None) is not None and injected_posts is None:
            try:
                d_pp = self.desk300.call_gateway_json(
                    "Bạn là trợ lý `300+desk` chuyên đọc bài đăng mạng xã hội để trích xuất nỗi đau khách hàng (Painpoint) và từ khoá sản phẩm giải pháp bán trên Shopee/TikTok. Chỉ trả về JSON.",
                    "Chủ đề: " + q + "\nBài đăng MXH:\n" + json.dumps([p.get("text", "")[:220] for p in posts[:8]], ensure_ascii=False)
                    + '\nTrả về JSON: {"pain_title": "<1 câu tóm tắt nỗi đau>", "product_keywords": ["<từ khoá SP 1>", "<từ khoá SP 2>", "<từ khoá SP 3>"]}',
                    task_type="painpoint_synthesis",
                    timeout_sec=25,
                )
                dp_obj = d_pp.get("parsed") if isinstance(d_pp.get("parsed"), dict) else {}
                if dp_obj.get("pain_title"):
                    pain_title = str(dp_obj["pain_title"]).strip()[:200]
                for dkw in dp_obj.get("product_keywords") or []:
                    dkw_s = str(dkw).strip()
                    if dkw_s and dkw_s.lower() not in {x.lower() for x in rec_keywords}:
                        rec_keywords.insert(0, dkw_s)
                rec_keywords = rec_keywords[:6]
            except Exception:
                pass
        ind = infer_industry(q + " " + " ".join(rec_keywords))

        # 2) Score & classify Painpoint with TypeSafe Jev AI
        jev_eval = None
        if jev_key and self.jev:
            try:
                jev_eval = self.jev.evaluate_social_painpoint(
                    jev_key,
                    {
                        "topic_query": q,
                        "channels_scanned": chs,
                        "preliminary_painpoint": pain_title,
                        "candidate_product_keywords": rec_keywords,
                        "sample_social_posts": [
                            {"channel": p.get("channel"), "text": (p.get("text") or "")[:240], "comments": p.get("comments", 0)}
                            for p in posts[:8]
                        ],
                    },
                    model=cfg["providers"].get("jev_model") or "jev-1.14.0",
                    base_url=cfg["providers"].get("jev_base_url") or "",
                )
                if jev_eval.get("industry") in INDUSTRIES:
                    ind = jev_eval["industry"]
                pain_title, pain_summary, rec_keywords = derive_painpoint_and_product_keywords(q, posts, jev_eval)
            except Exception as exc:
                if log_fn:
                    log_fn(f"⚠️ Jev Painpoint '{q}': {exc}")

        # 3) Optionally find matching Solution Products right away on Shopee & TikTok Shop
        matched_pids: list[int] = []
        matched_products: list[dict] = []
        if auto_find_products:
            if injected_products is not None:
                for it in injected_products:
                    if it.get("title"):
                        it_copy = dict(it)
                        it_copy.setdefault("note", f"Giải pháp cho Painpoint: {pain_title[:90]}")
                        saved = self.products.upsert_product(it_copy, source=f"painpoint_match:{q}")
                        if saved["id"] not in matched_pids:
                            matched_pids.append(saved["id"])
                            matched_products.append(saved)
            else:
                mkt_targets = [c for c in (marketplace_channels or ["shopee", "tiktok_shop"]) if c in MARKETPLACE_CHANNELS]
                for kw_sol in rec_keywords[:2]:
                    for mch in mkt_targets:
                        rows_found: list[dict] = []
                        if mch == "shopee" and apify_toks and self.apify:
                            try:
                                _, rows_found = self.apify.search_shopee(apify_toks, kw_sol, limit=5)
                            except Exception:
                                rows_found = []
                        elif mch == "tiktok_shop":
                            if apify_toks and self.apify:
                                try:
                                    _, rows_found = self.apify.search_tiktok_shop(apify_toks, kw_sol, limit=5)
                                except Exception:
                                    rows_found = []
                            if not rows_found and treg_tok and self.treg:
                                try:
                                    _, rows_found, _ = self.treg.search_tiktok_shop(treg_tok, kw_sol, limit=5)
                                except Exception:
                                    rows_found = []
                        for r in rows_found:
                            if r.get("title"):
                                r["note"] = f"Giải pháp cho Painpoint: {pain_title[:90]}"
                                saved = self.products.upsert_product(r, source=f"painpoint:{kw_sol}")
                                if saved["id"] not in matched_pids:
                                    matched_pids.append(saved["id"])
                                    matched_products.append(saved)

        pp_id = f"pp_{uuid.uuid4().hex[:10]}"
        ts = now()
        solution_arch = (jev_eval or {}).get("solution_archetype_label") or "Sản phẩm giải quyết vấn đề trực tiếp"
        jev_score = (jev_eval or {}).get("overall_pain_score_10")

        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO painpoint_discoveries
                (painpoint_id, job_id, topic_query, channels_json, industry, pain_title, pain_summary,
                 solution_archetype, recommended_keywords_json, evidence_posts_json, jev_pain_score,
                 jev_detail_json, matched_product_ids_json, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (
                    pp_id,
                    job_id,
                    q,
                    json.dumps(chs, ensure_ascii=False),
                    ind,
                    pain_title,
                    pain_summary,
                    solution_arch,
                    json.dumps(rec_keywords, ensure_ascii=False),
                    json.dumps(posts[:15], ensure_ascii=False),
                    jev_score,
                    json.dumps(jev_eval or {}, ensure_ascii=False),
                    json.dumps(matched_pids, ensure_ascii=False),
                    ts,
                    ts,
                ),
            )

        formatted = self.get_painpoint(pp_id)
        return {
            "painpoint": formatted,
            "matched_products": matched_products,
            "product_ids": matched_pids,
            "summary": (
                f"Painpoint '{q}' ({len(posts)} bài từ {', '.join(chs)}): "
                f"đề xuất {len(rec_keywords)} từ khoá giải pháp, lưu {len(matched_pids)} SP vào Kho!"
            ),
        }

    def get_painpoint(self, painpoint_id: str) -> dict:
        with self.connect() as conn:
            r = conn.execute("SELECT * FROM painpoint_discoveries WHERE painpoint_id=?", (painpoint_id,)).fetchone()
        if not r:
            raise ApiError("404 Not Found", "Không tìm thấy Painpoint này")
        return self._format_painpoint_row(r)

    def list_painpoints(self, limit: int = 30) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM painpoint_discoveries ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._format_painpoint_row(r) for r in rows]

    def delete_painpoint(self, painpoint_id: str) -> dict:
        with self.connect() as conn:
            conn.execute("DELETE FROM painpoint_discoveries WHERE painpoint_id=?", (painpoint_id,))
        return {"deleted": True, "painpoint_id": painpoint_id}

    def _format_painpoint_row(self, r) -> dict:
        ind = r["industry"] if r["industry"] in INDUSTRIES else "khac"
        pids = json.loads(r["matched_product_ids_json"] or "[]")
        matched_prods = self.products.get_products_by_ids(pids[:12]) if pids else []
        return {
            "painpoint_id": r["painpoint_id"],
            "job_id": r["job_id"],
            "topic_query": r["topic_query"],
            "channels": json.loads(r["channels_json"] or "[]"),
            "industry": ind,
            "industry_label": INDUSTRIES.get(ind, ind),
            "industry_icon": INDUSTRY_ICONS.get(ind, "📦"),
            "pain_title": r["pain_title"],
            "pain_summary": r["pain_summary"],
            "solution_archetype": r["solution_archetype"],
            "recommended_keywords": json.loads(r["recommended_keywords_json"] or "[]"),
            "evidence_posts": json.loads(r["evidence_posts_json"] or "[]"),
            "jev_pain_score": r["jev_pain_score"],
            "jev_detail": json.loads(r["jev_detail_json"] or "{}"),
            "matched_product_ids": pids,
            "matched_products": matched_prods,
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }

    # --- TIKTOK CREATOR RESEARCH ---------------------------------------------

    def search_tiktok_creators(self, query_or_handle: str, limit: int = 12, save_leads: bool = True) -> dict:
        q = text(query_or_handle, "query", 140, required=True)
        cfg = settings.read_settings(self.connect, self.secrets)
        apify_toks = settings.apify_tokens(cfg)
        treg_tok = (cfg["providers"].get("treg_key") or "").strip()

        raw_videos: list[dict] = []
        source_used = "none"
        is_handle = q.startswith("@") or (" " not in q and len(q) >= 3 and "." in q)

        if apify_toks and self.apify:
            try:
                if is_handle:
                    slug, raw_videos = self.apify.fetch_tiktok_creator_videos(apify_toks, q, limit=limit)
                else:
                    slug, raw_videos = self.apify.search_tiktok_videos(apify_toks, q, limit=limit)
                source_used = f"apify:{slug}"
            except Exception:
                raw_videos = []

        if not raw_videos and treg_tok and self.treg:
            try:
                res = self.treg.call(treg_tok, "treg.tiktok.search.videos", {"query": q.lstrip("@"), "count": limit})
                raw_videos = self.treg._extract_list(res)
                source_used = "treg:tiktok.search.videos"
            except Exception:
                raw_videos = []

        by_creator: dict[str, dict] = {}
        for v in raw_videos:
            author = v.get("authorMeta") or v.get("author") or {}
            handle = str(author.get("name") or author.get("uniqueId") or author.get("unique_id") or v.get("author_name") or "").strip().lstrip("@")
            if not handle:
                continue
            views = int(v.get("playCount") or v.get("play_count") or v.get("views") or 0)
            followers = int(author.get("fans") or author.get("followerCount") or author.get("follower_count") or 0)
            v_url = str(v.get("webVideoUrl") or v.get("url") or f"https://www.tiktok.com/@{handle}").strip()
            desc = str(v.get("text") or v.get("desc") or v.get("title") or "").strip()

            entry = by_creator.setdefault(handle, {
                "handle": handle,
                "display_name": str(author.get("nickName") or author.get("nickname") or handle),
                "followers": followers,
                "videos": [],
                "total_views": 0,
            })
            entry["followers"] = max(entry["followers"], followers)
            entry["total_views"] += views
            entry["videos"].append({"url": v_url, "caption": desc[:180], "views": views})

        creators_out = []
        ts = now()
        for handle, info in by_creator.items():
            avg_v = int(info["total_views"] / max(1, len(info["videos"])))
            ind = infer_industry(" ".join(x["caption"] for x in info["videos"]))
            cid = f"cr_{handle.lower()[:40]}"
            item = {
                "creator_id": cid,
                "platform": "tiktok",
                "handle": handle,
                "display_name": info["display_name"],
                "followers": info["followers"],
                "industry": ind,
                "industry_label": INDUSTRIES.get(ind, ind),
                "avg_views": avg_v,
                "top_videos": info["videos"][:6],
            }
            creators_out.append(item)
            if save_leads:
                with self.connect() as conn:
                    conn.execute(
                        """
                        INSERT INTO creator_leads
                        (creator_id, platform, market, handle, display_name, followers, industry, video_gmv_vnd, avg_views, jev_score, top_videos_json, note, created_at, updated_at)
                        VALUES (?, 'tiktok', 'VN', ?, ?, ?, ?, 0.0, ?, NULL, ?, '', ?, ?)
                        ON CONFLICT(creator_id) DO UPDATE SET
                            followers=MAX(creator_leads.followers, excluded.followers),
                            avg_views=excluded.avg_views,
                            top_videos_json=excluded.top_videos_json,
                            updated_at=excluded.updated_at
                        """,
                        (cid, handle, info["display_name"], info["followers"], ind, avg_v, json.dumps(info["videos"][:6], ensure_ascii=False), ts, ts),
                    )

        creators_out.sort(key=lambda x: x["avg_views"], reverse=True)
        return {
            "query": q,
            "source_used": source_used,
            "creators": creators_out,
            "summary": f"Creator TikTok ('{q}'): tìm thấy {len(creators_out)} kênh bán hàng / review",
        }

    def list_saved_creators(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM creator_leads ORDER BY updated_at DESC LIMIT 80").fetchall()
        return [
            {
                "creator_id": r["creator_id"],
                "handle": r["handle"],
                "display_name": r["display_name"],
                "followers": r["followers"],
                "industry": r["industry"],
                "industry_label": INDUSTRIES.get(r["industry"], r["industry"]),
                "avg_views": r["avg_views"],
                "top_videos": json.loads(r["top_videos_json"] or "[]"),
                "note": r["note"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]

    def dispatch(self, path: str, method: str, env, read_json):
        if path == "/api/hunt/estimate" and method == "POST":
            return "200 OK", self.estimate_hunt(json_object(read_json, env))
        if path == "/api/hunt/start" and method == "POST":
            return "200 OK", self.start_hunt(json_object(read_json, env))
        if path == "/api/hunt/status" and method == "GET":
            job = self.jobs.get_job(self._last_job_id) if self._last_job_id else None
            return "200 OK", {"active_job": job}
        if path == "/api/hunt/stop" and method == "POST":
            if self._last_job_id:
                return "200 OK", self.jobs.cancel_job(self._last_job_id)
            return "200 OK", {"status": "idle"}
        if path == "/api/hunt/google-trends" and method == "POST":
            body = json_object(read_json, env)
            seeds = body.get("seed_terms") if isinstance(body.get("seed_terms"), list) else []
            if not seeds and body.get("keyword"):
                seeds = [s.strip() for s in re.split(r"[,;\n]+", str(body["keyword"])) if s.strip()]
            return "200 OK", self.google_trends_explore_multi(
                seed_terms=seeds,
                geo=str(body.get("geo") or "VN"),
                time_range=str(body.get("time_range") or "today 3-m"),
                category=str(body.get("category") or ""),
                score_jev=bool(body.get("score_jev", True)),
            )
        if path == "/api/hunt/google-trends/history" and method == "GET":
            return "200 OK", {"runs": self.list_google_trends_runs(20)}
        if path == "/api/hunt/painpoints" and method == "GET":
            return "200 OK", {"painpoints": self.list_painpoints(30)}
        if path == "/api/hunt/painpoints" and method == "POST":
            body = json_object(read_json, env)
            return "200 OK", self.discover_painpoints(
                topic_query=text(body.get("topic_query") or body.get("keyword"), "topic_query", 180, required=True),
                channels=body.get("channels") if isinstance(body.get("channels"), list) else None,
                limit_per_channel=int(body.get("limit_per_channel") or 6),
                auto_find_products=bool(body.get("auto_find_products", True)),
                marketplace_channels=body.get("marketplace_channels") if isinstance(body.get("marketplace_channels"), list) else None,
            )
        if path.startswith("/api/hunt/painpoints/") and method == "DELETE":
            pp_id = path.strip("/").split("/")[3]
            return "200 OK", self.delete_painpoint(pp_id)
        if path == "/api/creators" and method == "GET":
            return "200 OK", {"creators": self.list_saved_creators()}
        if path == "/api/creators/search" and method == "POST":
            body = json_object(read_json, env)
            return "200 OK", self.search_tiktok_creators(
                query_or_handle=text(body.get("query"), "query", 140, required=True),
                limit=int(body.get("limit") or 12),
                save_leads=bool(body.get("save_leads", True)),
            )
        return None
