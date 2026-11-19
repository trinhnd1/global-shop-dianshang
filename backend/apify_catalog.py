"""Full Apify Store Catalog Scanner, Local SQLite/JSON Vault & Goal-Based On-Demand Actor Router."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import math
from pathlib import Path
import time
import urllib.parse
import urllib.request
import uuid

from . import settings
from .responses import ApiError, json_object, now

GOAL_TAXONOMY: dict[str, dict] = {
    "shopee": {"label": "🛍 Shopee (VN/PH/SG/MY/TH)", "keywords": ("shopee",)},
    "tiktok_shop": {"label": "🛒 TikTok Shop (VN/PH/SG/MY/TH)", "keywords": ("tiktok shop", "tiktok-shop", "tiktokshop")},
    "tiktok_video": {"label": "🎵 TikTok Video / Creator", "keywords": ("tiktok",)},
    "lazada": {"label": "📦 Lazada SEA", "keywords": ("lazada",)},
    "1688": {"label": "🇨🇳 1688 Nguồn xưởng", "keywords": ("1688",)},
    "taobao": {"label": "🇨🇳 Taobao / Tmall", "keywords": ("taobao", "tmall")},
    "pinduoduo": {"label": "🇨🇳 Pinduoduo / Temu", "keywords": ("pinduoduo", "temu", "yangkeduo")},
    "alibaba_aliexpress": {"label": "🌐 Alibaba / AliExpress", "keywords": ("alibaba", "aliexpress")},
    "amazon": {"label": "🌎 Amazon", "keywords": ("amazon",)},
    "facebook_ads": {"label": "📢 Facebook Ad Library", "keywords": ("facebook ads", "facebook-ads", "ad library", "meta ads")},
    "facebook_posts": {"label": "📘 Facebook Posts / Pages / Groups", "keywords": ("facebook",)},
    "threads": {"label": "🧵 Meta Threads", "keywords": ("threads",)},
    "x_twitter": {"label": "𝕏 X / Twitter", "keywords": ("twitter", "tweet", "x.com")},
    "reddit": {"label": "👽 Reddit Painpoints", "keywords": ("reddit",)},
    "instagram": {"label": "📸 Instagram", "keywords": ("instagram",)},
    "youtube": {"label": "▶️ YouTube", "keywords": ("youtube",)},
    "google_trends": {"label": "📈 Google Trends", "keywords": ("google trends", "google-trends")},
    "google_serp": {"label": "🔎 Google Search / SERP", "keywords": ("google search", "serp", "google-search")},
    "google_maps": {"label": "📍 Google Maps / Leads", "keywords": ("google maps", "google-maps")},
}


def classify_actor_goals(name: str, title: str, description: str, categories: list[str]) -> list[str]:
    hay = f"{name} {title} {description[:280]}".lower()
    tags: list[str] = []
    for goal_key, meta in GOAL_TAXONOMY.items():
        if any(kw in hay for kw in meta["keywords"]):
            # Disambiguate tiktok_video vs tiktok_shop
            if goal_key == "tiktok_video" and "tiktok_shop" in tags and not any(w in hay for w in ("video", "profile", "creator", "hashtag")):
                continue
            tags.append(goal_key)
    if not tags and "ECOMMERCE" in categories:
        tags.append("ecommerce_general")
    return tags


def compute_actor_quality(item: dict) -> tuple[str, float | None, int, int, int, int, float, float, int, float]:
    stats = item.get("stats") or {}
    total_users = int(stats.get("totalUsers") or 0)
    users_30d = int(stats.get("totalUsers30Days") or 0)
    run30 = stats.get("publicActorRunStats30Days") or {}
    succ_30d = int(run30.get("SUCCEEDED") or 0)
    tot_30d = int(run30.get("TOTAL") or 0)
    succ_rate = round((succ_30d / tot_30d) * 100.0, 1) if tot_30d > 0 else 0.0

    rating = float(item.get("actorReviewRating") or stats.get("actorReviewRating") or 0.0)
    reviews = int(item.get("actorReviewCount") or stats.get("actorReviewCount") or 0)

    pricing = item.get("currentPricingInfo") or {}
    p_model = str(pricing.get("pricingModel") or "FREE").strip()
    unit_usd = pricing.get("pricePerUnitUsd")
    if unit_usd is not None:
        try:
            unit_usd = round(float(unit_usd), 6)
        except Exception:
            unit_usd = None

    trial_mins = int(pricing.get("trialMinutes") or 0)
    is_pay_per_use = 1 if (p_model in ("FREE", "PAY_PER_EVENT", "PRICE_PER_DATASET_ITEM") or trial_mins > 0) else 0

    # Composite quality score [0..100]: rewards active 30d users, high run success rate, verified reviews & pay-per-use accessibility
    user_pts = min(45.0, math.log10(max(1, users_30d + 1)) * 13.5)
    succ_pts = (succ_rate / 100.0) * 25.0 if tot_30d >= 10 else (10.0 if tot_30d > 0 else 0.0)
    rev_pts = min(15.0, (rating / 5.0) * 10.0 + min(5.0, math.log10(max(1, reviews + 1)) * 2.5)) if rating > 0 else 0.0
    pay_pts = 15.0 if is_pay_per_use else 2.0
    q_score = round(min(100.0, user_pts + succ_pts + rev_pts + pay_pts), 2)

    return p_model, unit_usd, is_pay_per_use, total_users, users_30d, succ_30d, tot_30d, succ_rate, round(rating, 2), reviews, q_score


class ApifyStoreCatalogService:
    STORE_API_URL = "https://api.apify.com/v2/store"
    ACTS_API_URL = "https://api.apify.com/v2/acts"
    BUILDS_API_URL = "https://api.apify.com/v2/actor-builds"

    def __init__(self, connect, secrets, data_dir: str | Path, apify_client=None, products=None, jobs=None, http_opener=None):
        self.connect = connect
        self.secrets = secrets
        self.root = Path(data_dir)
        self.apify = apify_client
        self.products = products
        self.jobs = jobs
        self._opener = http_opener or urllib.request.urlopen
        self.catalog_json_path = self.root / "apify_store_catalog.json"

    def _fetch_store_page(self, offset: int, limit: int = 1000) -> tuple[int, list[dict]]:
        qs = urllib.parse.urlencode({"limit": limit, "offset": offset})
        req = urllib.request.Request(
            f"{self.STORE_API_URL}?{qs}",
            headers={"User-Agent": "GlobalShopDianshang/1.0", "Accept": "application/json"},
        )
        last_err = None
        for attempt in range(3):
            try:
                with self._opener(req, timeout=28) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    data = body.get("data") or {}
                    return int(data.get("total") or 0), list(data.get("items") or [])
            except Exception as exc:
                last_err = exc
                time.sleep(0.6 * (attempt + 1))
        raise RuntimeError(f"Lỗi tải trang Apify Store offset={offset}: {last_err}")

    def sync_entire_store(self, max_pages: int = 25, page_size: int = 1000, workers: int = 6, log_fn=None) -> dict:
        """Scan 100% of live public actors in `https://api.apify.com/v2/store` and persist to SQLite + JSON vault."""
        t0 = time.time()
        sync_id = f"apsync_{uuid.uuid4().hex[:8]}"
        started_at = now()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO apify_store_sync_runs (sync_id, status, created_at) VALUES (?, 'running', ?)",
                (sync_id, started_at),
            )

        try:
            total_reported, first_items = self._fetch_store_page(0, page_size)
            all_raw: dict[str, dict] = {}
            for it in first_items:
                if isinstance(it, dict) and it.get("id"):
                    all_raw[str(it["id"])] = it
            pages_scanned = 1
            if log_fn:
                log_fn(f"📡 Trang 1 (offset=0): thu được {len(first_items)} actors (Store báo tổng {total_reported})")

            # Probe offsets in parallel batches of `workers` until empty pages are hit
            if first_items and page_size >= 100:
                offset_cursor = page_size
                reached_end = False
                while not reached_end and pages_scanned < max_pages:
                    batch_offsets = [offset_cursor + i * page_size for i in range(workers) if (pages_scanned + i) < max_pages]
                    if not batch_offsets:
                        break
                    offset_cursor += len(batch_offsets) * page_size
                    with ThreadPoolExecutor(max_workers=min(workers, len(batch_offsets))) as pool:
                        futs = {pool.submit(self._fetch_store_page, off, page_size): off for off in batch_offsets}
                        for fut in as_completed(futs):
                            off = futs[fut]
                            _, page_items = fut.result()
                            pages_scanned += 1
                            if not page_items:
                                reached_end = True
                            else:
                                for it in page_items:
                                    if isinstance(it, dict) and it.get("id"):
                                        all_raw[str(it["id"])] = it
                                if log_fn:
                                    log_fn(f"✓ Offset {off}: +{len(page_items)} actors (tích luỹ {len(all_raw)} actors)")

            synced_ts = now()
            rows_to_upsert = []
            compact_export = []

            for aid, it in all_raw.items():
                uname = str(it.get("username") or "").strip()
                aname = str(it.get("name") or "").strip()
                if not uname or not aname:
                    continue
                slug = f"{uname}~{aname}"
                full_name = f"{uname}/{aname}"
                title = str(it.get("title") or full_name).strip()
                desc = str(it.get("description") or "").strip()
                cats = [str(c) for c in (it.get("categories") or []) if c]
                goals = classify_actor_goals(aname, title, desc, cats)
                (
                    p_model,
                    unit_usd,
                    is_ppu,
                    tot_users,
                    u30,
                    succ30,
                    tot30,
                    srate,
                    rating,
                    revs,
                    q_score,
                ) = compute_actor_quality(it)
                store_url = str(it.get("url") or f"https://apify.com/{uname}/{aname}")
                compact_raw = {
                    "id": aid,
                    "slug": slug,
                    "full_name": full_name,
                    "title": title,
                    "categories": cats,
                    "goals": goals,
                    "pricing_model": p_model,
                    "unit_price_usd": unit_usd,
                    "is_pay_per_use": bool(is_ppu),
                    "users_30d": u30,
                    "total_users": tot_users,
                    "success_rate_30d": srate,
                    "rating": rating,
                    "quality_score": q_score,
                    "url": store_url,
                }
                compact_export.append(compact_raw)
                rows_to_upsert.append((
                    aid,
                    slug,
                    full_name,
                    uname,
                    aname,
                    title[:240],
                    desc[:1000],
                    json.dumps(cats, ensure_ascii=False),
                    json.dumps(goals, ensure_ascii=False),
                    p_model,
                    unit_usd,
                    is_ppu,
                    tot_users,
                    u30,
                    succ30,
                    tot30,
                    srate,
                    rating,
                    revs,
                    q_score,
                    store_url,
                    json.dumps(compact_raw, ensure_ascii=False),
                    synced_ts,
                ))

            with self.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.executemany(
                    """
                    INSERT INTO apify_store_actors
                    (actor_id, slug, full_name, username, name, title, description, categories_json, goal_tags_json,
                     pricing_model, unit_price_usd, is_pay_per_use, total_users, users_30d, runs_30d_succeeded,
                     runs_30d_total, success_rate_30d, rating, review_count, quality_score, store_url, raw_json, synced_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(actor_id) DO UPDATE SET
                        slug=excluded.slug,
                        full_name=excluded.full_name,
                        title=excluded.title,
                        description=excluded.description,
                        categories_json=excluded.categories_json,
                        goal_tags_json=excluded.goal_tags_json,
                        pricing_model=excluded.pricing_model,
                        unit_price_usd=excluded.unit_price_usd,
                        is_pay_per_use=excluded.is_pay_per_use,
                        total_users=excluded.total_users,
                        users_30d=excluded.users_30d,
                        runs_30d_succeeded=excluded.runs_30d_succeeded,
                        runs_30d_total=excluded.runs_30d_total,
                        success_rate_30d=excluded.success_rate_30d,
                        rating=excluded.rating,
                        review_count=excluded.review_count,
                        quality_score=excluded.quality_score,
                        store_url=excluded.store_url,
                        raw_json=excluded.raw_json,
                        synced_at=excluded.synced_at
                    """,
                    rows_to_upsert,
                )

            # Save sorted JSON catalog snapshot on disk for instant external/CLI inspection too
            compact_export.sort(key=lambda x: (x["quality_score"], x["users_30d"]), reverse=True)
            self.catalog_json_path.write_text(
                json.dumps(
                    {
                        "synced_at": synced_ts,
                        "total_store_reported": total_reported,
                        "actors_saved": len(compact_export),
                        "goals_taxonomy": {k: v["label"] for k, v in GOAL_TAXONOMY.items()},
                        "actors": compact_export,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            dur_ms = int((time.time() - t0) * 1000)
            done_ts = now()
            with self.connect() as conn:
                conn.execute(
                    """
                    UPDATE apify_store_sync_runs
                    SET status='completed', total_reported=?, actors_saved=?, pages_scanned=?, duration_ms=?,
                        catalog_file=?, completed_at=?
                    WHERE sync_id=?
                    """,
                    (total_reported, len(rows_to_upsert), pages_scanned, dur_ms, str(self.catalog_json_path.name), done_ts, sync_id),
                )
            return {
                "sync_id": sync_id,
                "status": "completed",
                "total_reported": total_reported,
                "actors_saved": len(rows_to_upsert),
                "pages_scanned": pages_scanned,
                "duration_ms": dur_ms,
                "catalog_file": str(self.catalog_json_path),
                "summary": f"Đã quét & lưu thành công {len(rows_to_upsert):,} Actors từ Apify Store ({dur_ms / 1000:.1f}s)!",
            }
        except Exception as exc:
            with self.connect() as conn:
                conn.execute(
                    "UPDATE apify_store_sync_runs SET status='failed', error_text=?, completed_at=? WHERE sync_id=?",
                    (str(exc)[:500], now(), sync_id),
                )
            raise

    def get_stats(self) -> dict:
        with self.connect() as conn:
            total = int(conn.execute("SELECT COUNT(*) FROM apify_store_actors").fetchone()[0])
            ppu = int(conn.execute("SELECT COUNT(*) FROM apify_store_actors WHERE is_pay_per_use=1").fetchone()[0])
            ecomm = int(conn.execute("SELECT COUNT(*) FROM apify_store_actors WHERE categories_json LIKE '%ECOMMERCE%'").fetchone()[0])
            social = int(conn.execute("SELECT COUNT(*) FROM apify_store_actors WHERE categories_json LIKE '%SOCIAL_MEDIA%'").fetchone()[0])
            last_run = conn.execute("SELECT * FROM apify_store_sync_runs ORDER BY created_at DESC LIMIT 1").fetchone()
            goal_counts = {}
            for g in GOAL_TAXONOMY:
                cnt = int(conn.execute("SELECT COUNT(*) FROM apify_store_actors WHERE goal_tags_json LIKE ?", (f'%"{g}"%',)).fetchone()[0])
                goal_counts[g] = cnt
        return {
            "total_actors": total,
            "pay_per_use_actors": ppu,
            "ecommerce_actors": ecomm,
            "social_actors": social,
            "goal_counts": goal_counts,
            "goals_catalog": {k: v["label"] for k, v in GOAL_TAXONOMY.items()},
            "catalog_file": str(self.catalog_json_path),
            "catalog_file_exists": self.catalog_json_path.is_file(),
            "last_sync": dict(last_run) if last_run else None,
        }

    def search_actors(
        self,
        q: str = "",
        goal: str = "",
        category: str = "",
        pay_per_use_only: bool = False,
        sort_by: str = "quality",
        limit: int = 40,
        offset: int = 0,
    ) -> dict:
        clauses = []
        params: list = []
        if q.strip():
            qs = f"%{q.strip()}%"
            clauses.append("(full_name LIKE ? OR title LIKE ? OR description LIKE ?)")
            params.extend([qs, qs, qs])
        if goal.strip():
            clauses.append("goal_tags_json LIKE ?")
            params.append(f'%"{goal.strip()}"%')
        if category.strip():
            clauses.append("categories_json LIKE ?")
            params.append(f'%"{category.strip()}"%')
        if pay_per_use_only:
            clauses.append("is_pay_per_use = 1")

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        order_sql = {
            "quality": "quality_score DESC, users_30d DESC",
            "users": "users_30d DESC, total_users DESC",
            "runs": "runs_30d_succeeded DESC, quality_score DESC",
            "rating": "rating DESC, review_count DESC",
        }.get(sort_by, "quality_score DESC, users_30d DESC")

        lim = max(1, min(200, int(limit)))
        off = max(0, int(offset))
        with self.connect() as conn:
            matched_total = int(conn.execute(f"SELECT COUNT(*) FROM apify_store_actors {where}", tuple(params)).fetchone()[0])
            rows = conn.execute(
                f"SELECT * FROM apify_store_actors {where} ORDER BY {order_sql} LIMIT ? OFFSET ?",
                tuple([*params, lim, off]),
            ).fetchall()

        return {
            "total": matched_total,
            "limit": lim,
            "offset": off,
            "actors": [self._format_actor(r) for r in rows],
        }

    def recommend_for_goal(self, goal: str, limit: int = 6, pay_per_use_only: bool = True) -> list[dict]:
        res = self.search_actors(goal=goal, pay_per_use_only=pay_per_use_only, sort_by="quality", limit=limit)
        return res["actors"]

    def fetch_actor_schema(self, slug_or_name: str, force_refresh: bool = False) -> dict:
        norm_slug = slug_or_name.strip().replace("/", "~")
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM apify_store_actors WHERE slug=? OR full_name=? OR actor_id=?",
                (norm_slug, slug_or_name.strip().replace("~", "/"), slug_or_name.strip()),
            ).fetchone()

        if row and not force_refresh:
            cached = json.loads(row["input_schema_json"] or "{}")
            if cached.get("properties"):
                return {
                    "slug": row["slug"],
                    "full_name": row["full_name"],
                    "title": row["title"],
                    "input_schema": cached,
                    "sample_payload": self._build_sample_payload(cached),
                    "cached": True,
                }

        target_slug = row["slug"] if row else norm_slug
        req_act = urllib.request.Request(f"{self.ACTS_API_URL}/{target_slug}", headers={"User-Agent": "GlobalShopDianshang/1.0"})
        try:
            with self._opener(req_act, timeout=15) as resp:
                act_data = (json.loads(resp.read().decode("utf-8")).get("data") or {})
        except Exception as exc:
            raise ApiError("502 Bad Gateway", f"Không đọc được metadata Actor {target_slug}: {exc}") from None

        build_id = (
            ((act_data.get("taggedBuilds") or {}).get("latest") or {}).get("buildId")
            or (act_data.get("defaultRunOptions") or {}).get("build")
            or ""
        )
        schema_obj = {}
        if build_id and len(str(build_id)) > 8:
            req_b = urllib.request.Request(f"{self.BUILDS_API_URL}/{build_id}", headers={"User-Agent": "GlobalShopDianshang/1.0"})
            try:
                with self._opener(req_b, timeout=15) as rb:
                    b_data = (json.loads(rb.read().decode("utf-8")).get("data") or {})
                    schema_obj = (b_data.get("actorDefinition") or {}).get("input") or {}
            except Exception:
                schema_obj = {}

        if row and schema_obj:
            with self.connect() as conn:
                conn.execute(
                    "UPDATE apify_store_actors SET input_schema_json=? WHERE actor_id=?",
                    (json.dumps(schema_obj, ensure_ascii=False), row["actor_id"]),
                )

        return {
            "slug": target_slug,
            "full_name": target_slug.replace("~", "/"),
            "title": act_data.get("title") or (row["title"] if row else target_slug),
            "input_schema": schema_obj,
            "sample_payload": self._build_sample_payload(schema_obj),
            "cached": False,
        }

    @staticmethod
    def _build_sample_payload(schema_obj: dict) -> dict:
        props = schema_obj.get("properties") or {}
        req_fields = set(schema_obj.get("required") or [])
        sample: dict = {}
        for k, meta in list(props.items())[:14]:
            if not isinstance(meta, dict):
                continue
            if "prefill" in meta:
                sample[k] = meta["prefill"]
            elif "default" in meta:
                sample[k] = meta["default"]
            elif k in req_fields:
                t = meta.get("type")
                sample[k] = [] if t == "array" else ({} if t == "object" else (10 if t == "integer" else ""))
        return sample

    def call_actor_on_demand(
        self,
        actor_slug: str = "",
        goal: str = "",
        payload: dict | None = None,
        max_charge_usd: float = 0.06,
        timeout_sec: int = 60,
        save_products_to_vault: bool = False,
    ) -> dict:
        """Invoke any saved Apify Store actor (or auto-pick top ranked actor for `goal`) on demand."""
        if not self.apify:
            raise ApiError("500 Internal Server Error", "Chưa khởi tạo ApifyClient")
        cfg = settings.read_settings(self.connect, self.secrets)
        tokens = settings.apify_tokens(cfg)
        if not tokens:
            raise ApiError("400 Bad Request", "Chưa cấu hình Apify API Key trong Cài đặt")

        chosen_slug = (actor_slug or "").strip().replace("/", "~")
        if not chosen_slug and goal:
            recs = self.recommend_for_goal(goal, limit=3, pay_per_use_only=True)
            if not recs:
                raise ApiError("404 Not Found", f"Không tìm thấy Actor phù hợp cho mục tiêu '{goal}' trong Kho Apify Store")
            chosen_slug = recs[0]["slug"]
        if not chosen_slug:
            raise ApiError("400 Bad Request", "Cần truyền `actor_slug` hoặc `goal` để gọi Actor")

        items = self.apify.run_sync_items(
            tokens,
            chosen_slug,
            dict(payload or {}),
            max_charge_usd=max(0.015, min(0.50, float(max_charge_usd or 0.06))),
            timeout_sec=max(15, min(120, int(timeout_sec or 60))),
        )

        saved_pids: list[int] = []
        if save_products_to_vault and self.products and items:
            for r in items[:30]:
                if not isinstance(r, dict):
                    continue
                norm = None
                if "shopee" in chosen_slug:
                    norm = self.apify.normalize_shopee_item(r)
                elif "tiktok-shop" in chosen_slug or "tiktok_shop" in chosen_slug:
                    norm = self.apify.normalize_tiktok_shop_item(r)
                elif r.get("title") or r.get("name"):
                    norm = {
                        "platform": "shopee",
                        "market": "VN",
                        "title": str(r.get("title") or r.get("name") or "")[:250],
                        "price_vnd": float(r.get("price_vnd") or r.get("price") or 0.0),
                        "sold_count": int(r.get("sold_count") or r.get("sold") or 0),
                        "url": str(r.get("url") or r.get("productUrl") or ""),
                        "image_url": str(r.get("imageUrl") or r.get("image") or ""),
                    }
                if norm and norm.get("title"):
                    p = self.products.upsert_product(norm, source=f"apify_store:{chosen_slug}")
                    saved_pids.append(p["id"])

        return {
            "actor_slug": chosen_slug,
            "full_name": chosen_slug.replace("~", "/"),
            "items_count": len(items),
            "items": items[:50],
            "saved_product_ids": saved_pids,
            "summary": f"Gọi Actor `{chosen_slug.replace('~', '/')}` thành công: trả về {len(items)} bản ghi"
            + (f" (đã lưu {len(saved_pids)} SP vào Kho)" if saved_pids else ""),
        }

    @staticmethod
    def _format_actor(r) -> dict:
        return {
            "actor_id": r["actor_id"],
            "slug": r["slug"],
            "full_name": r["full_name"],
            "username": r["username"],
            "name": r["name"],
            "title": r["title"],
            "description": r["description"],
            "categories": json.loads(r["categories_json"] or "[]"),
            "goal_tags": json.loads(r["goal_tags_json"] or "[]"),
            "pricing_model": r["pricing_model"],
            "unit_price_usd": r["unit_price_usd"],
            "is_pay_per_use": bool(r["is_pay_per_use"]),
            "total_users": r["total_users"],
            "users_30d": r["users_30d"],
            "runs_30d_succeeded": r["runs_30d_succeeded"],
            "runs_30d_total": r["runs_30d_total"],
            "success_rate_30d": r["success_rate_30d"],
            "rating": r["rating"],
            "review_count": r["review_count"],
            "quality_score": r["quality_score"],
            "store_url": r["store_url"],
            "has_cached_schema": bool(r["input_schema_json"] and r["input_schema_json"] != "{}"),
            "synced_at": r["synced_at"],
        }

    def dispatch(self, path: str, method: str, env, read_json):
        qs = urllib.parse.parse_qs(env.get("QUERY_STRING", ""))
        if path == "/api/apify-store/stats" and method == "GET":
            return "200 OK", self.get_stats()
        if path == "/api/apify-store/search" and method == "GET":
            return "200 OK", self.search_actors(
                q=(qs.get("q") or [""])[0],
                goal=(qs.get("goal") or [""])[0],
                category=(qs.get("category") or [""])[0],
                pay_per_use_only=(qs.get("pay_per_use_only") or [""])[0].lower() in ("1", "true", "yes"),
                sort_by=(qs.get("sort_by") or ["quality"])[0],
                limit=int((qs.get("limit") or ["40"])[0]),
                offset=int((qs.get("offset") or ["0"])[0]),
            )
        if path == "/api/apify-store/recommend" and method == "GET":
            goal = (qs.get("goal") or ["shopee"])[0]
            return "200 OK", {"goal": goal, "actors": self.recommend_for_goal(goal, limit=int((qs.get("limit") or ["8"])[0]))}
        if path == "/api/apify-store/sync" and method == "POST":
            body = json_object(read_json, env)
            max_pages = max(1, min(30, int(body.get("max_pages") or 25)))
            page_size = max(10, min(1000, int(body.get("page_size") or 1000)))
            if bool(body.get("background", False)) and self.jobs is not None:
                job = self.jobs.start_job(
                    kind="apify_store_sync",
                    title="Quét & Lưu toàn bộ danh mục API Apify Store",
                    target_fn=lambda ctx: self.sync_entire_store(max_pages=max_pages, page_size=page_size, log_fn=ctx.log),
                    estimated_cost_usd=0.0,
                    budget_limit_usd=0.10,
                )
                return "200 OK", {"job": job, "summary": "Đã khởi chạy tiến trình quét toàn bộ Apify Store dưới nền!"}
            return "200 OK", self.sync_entire_store(max_pages=max_pages, page_size=page_size)
        if path.startswith("/api/apify-store/actors/") and path.endswith("/schema") and method == "GET":
            slug = urllib.parse.unquote(path[len("/api/apify-store/actors/") : -len("/schema")]).strip("/")
            force = (qs.get("refresh") or [""])[0].lower() in ("1", "true")
            return "200 OK", self.fetch_actor_schema(slug, force_refresh=force)
        if path == "/api/apify-store/call" and method == "POST":
            body = json_object(read_json, env)
            return "200 OK", self.call_actor_on_demand(
                actor_slug=str(body.get("actor_slug") or ""),
                goal=str(body.get("goal") or ""),
                payload=body.get("payload") if isinstance(body.get("payload"), dict) else {},
                max_charge_usd=float(body.get("max_charge_usd") or 0.06),
                timeout_sec=int(body.get("timeout_sec") or 60),
                save_products_to_vault=bool(body.get("save_products_to_vault", False)),
            )
        return None
