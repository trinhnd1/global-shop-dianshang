"""Multi-Channel Seller Product Hunter (Shopee, TikTok Shop, Lazada, FB Ads, Google Trends) + TikTok Creator Product Tool."""
import json
import uuid

from . import settings
from .products import INDUSTRIES, infer_industry
from .responses import json_object, now, text


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

        per_call = 0.035
        channel_calls = max(1, len(terms)) * max(1, len(channels))
        jev_est = (len(terms) * 4 * 0.0006) if auto_jev else 0.0
        est_usd = round(channel_calls * per_call + jev_est, 4)
        return {
            "terms": terms,
            "channels": channels,
            "auto_score_jev": auto_jev,
            "estimated_cost_usd": est_usd,
            "budget_limit_usd": float(body.get("budget_limit_usd") or cfg["hunt"]["max_session_cost_usd"]),
        }

    def start_hunt(self, body: dict) -> dict:
        est = self.estimate_hunt(body)
        cfg = settings.read_settings(self.connect, self.secrets)
        apify_toks = settings.apify_tokens(cfg)
        treg_tok = (cfg["providers"].get("treg_key") or "").strip()
        items_per_ch = max(3, min(30, int(body.get("items_per_channel") or cfg["hunt"]["items_per_channel"])))

        def _worker(ctx):
            discovered_ids: list[int] = []
            for term in est["terms"]:
                ctx.check_cancelled()
                ctx.log(f"🔎 Đang quét từ khoá/ngách: '{term}' trên {', '.join(est['channels'])}")
                for ch in est["channels"]:
                    ctx.check_cancelled()
                    found_rows: list[dict] = []
                    if ch == "shopee" and apify_toks and self.apify:
                        try:
                            _, found_rows = ctx.run_step(
                                f"shopee:{term}",
                                "apify",
                                0.035,
                                lambda t=term: self.apify.search_shopee(apify_toks, t, limit=items_per_ch),
                            )
                        except Exception as exc:
                            ctx.log(f"⚠️ Shopee '{term}': {exc}")
                    elif ch in ("tiktok", "tiktok_shop"):
                        if apify_toks and self.apify:
                            try:
                                _, found_rows = ctx.run_step(
                                    f"tiktok_shop:{term}",
                                    "apify",
                                    0.035,
                                    lambda t=term: self.apify.search_tiktok_shop(apify_toks, t, limit=items_per_ch),
                                )
                            except Exception as exc:
                                ctx.log(f"⚠️ Apify TikTok Shop '{term}': {exc}")
                        if not found_rows and treg_tok and self.treg:
                            try:
                                _, found_rows, _ = ctx.run_step(
                                    f"treg_tiktok:{term}",
                                    "treg",
                                    0.025,
                                    lambda t=term: self.treg.search_tiktok_shop(treg_tok, t, limit=items_per_ch),
                                )
                            except Exception as exc:
                                ctx.log(f"⚠️ Treg TikTok Shop '{term}': {exc}")
                    elif ch == "lazada" and apify_toks and self.apify:
                        try:
                            _, found_rows = ctx.run_step(
                                f"lazada:{term}",
                                "apify",
                                0.035,
                                lambda t=term: self.apify.search_lazada(apify_toks, t, limit=items_per_ch),
                            )
                        except Exception as exc:
                            ctx.log(f"⚠️ Lazada '{term}': {exc}")
                    elif ch == "facebook_ads" and apify_toks and self.apify:
                        try:
                            _, ads = ctx.run_step(
                                f"fb_ads:{term}",
                                "apify",
                                0.035,
                                lambda t=term: self.apify.search_facebook_ads(apify_toks, t, limit=6),
                            )
                            for ad in ads:
                                title = str(ad.get("adText") or ad.get("body") or ad.get("pageName") or "").strip()[:160]
                                link = str(ad.get("linkUrl") or ad.get("ctaUrl") or "").strip()
                                if title and link:
                                    found_rows.append({
                                        "platform": "facebook_ads",
                                        "market": "VN",
                                        "title": title,
                                        "url": link,
                                        "shop_name": str(ad.get("pageName") or ""),
                                        "price_vnd": 0.0,
                                        "sold_count": 0,
                                    })
                        except Exception as exc:
                            ctx.log(f"⚠️ FB Ads '{term}': {exc}")

                    for r in found_rows:
                        if r.get("title"):
                            saved = self.products.upsert_product(r, source=f"hunt:{ch}:{term}")
                            if saved["id"] not in discovered_ids:
                                discovered_ids.append(saved["id"])
                    ctx.log(f"✓ Kênh {ch} ('{term}'): thu thập {len(found_rows)} mẫu")

            scored = 0
            if est["auto_score_jev"] and discovered_ids:
                for pid in discovered_ids[:8]:
                    ctx.check_cancelled()
                    try:
                        self.products.score_product_jev(pid)
                        scored += 1
                    except Exception as exc:
                        ctx.log(f"⚠️ Chấm Jev SP #{pid}: {exc}")
                        break
            summary = f"Săn hoàn tất: lưu/cập nhật {len(discovered_ids)} SP vào Kho, đã chấm Jev {scored} SP"
            ctx.log(f"🏁 {summary}")
            return {"discovered_count": len(discovered_ids), "scored_jev_count": scored, "product_ids": discovered_ids, "summary": summary}

        job = self.jobs.start_job(
            kind="hunt",
            title=f"Săn SP bán chạy: {', '.join(est['terms'][:3])}",
            target_fn=_worker,
            estimated_cost_usd=est["estimated_cost_usd"],
            budget_limit_usd=est["budget_limit_usd"],
            max_retries=int(cfg["hunt"]["max_retries"]),
            single_active_kind=True,
            meta={"terms": est["terms"], "channels": est["channels"]},
        )
        self._last_job_id = job["id"]
        return job

    def google_trends_explore(self, keyword: str) -> dict:
        kw = text(keyword, "keyword", 120, required=True)
        cfg = settings.read_settings(self.connect, self.secrets)
        apify_toks = settings.apify_tokens(cfg)
        treg_tok = (cfg["providers"].get("treg_key") or "").strip()
        rows = []
        source = "none"
        if apify_toks and self.apify:
            try:
                slug, rows = self.apify.fetch_google_trends(apify_toks, kw)
                source = f"apify:{slug}"
            except Exception:
                rows = []
        if not rows and treg_tok and self.treg:
            try:
                res = self.treg.fetch_google_trends(treg_tok, kw)
                rows = self.treg._extract_list(res)
                source = "treg:google_keywords_ideas"
            except Exception:
                rows = []
        return {
            "keyword": kw,
            "source_used": source,
            "results": rows[:20],
            "summary": f"Google Trends '{kw}': {len(rows[:20])} tín hiệu xu hướng",
        }

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
            return "200 OK", self.google_trends_explore(text(body.get("keyword"), "keyword", 120, required=True))
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
