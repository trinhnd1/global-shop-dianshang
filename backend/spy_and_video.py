"""Competitor Product & Fanpage Spy + 4-Frame Video Jev Analyzer (.VTT Hook/Body/CTA) + 15s Video Cloner."""
import base64
import hashlib
import json
import mimetypes
from pathlib import Path
import re
import uuid

from . import settings
from .products import parse_ids_from_url
from .providers.media import download_public_video, extract_4_keyframes, ffmpeg_status, probe_duration_sec, slice_15s_segments
from .responses import ApiError, Raw, json_object, now, text


def split_3part_script(transcript: str) -> dict:
    txt = (transcript or "").strip()
    if not txt:
        return {"hook_0_3s": "", "body_demo": "", "cta_close": ""}
    sentences = [s.strip() for s in re.split(r"[.!?\n]+", txt) if s.strip()]
    if len(sentences) == 1:
        return {"hook_0_3s": sentences[0], "body_demo": "", "cta_close": ""}
    if len(sentences) == 2:
        return {"hook_0_3s": sentences[0], "body_demo": sentences[1], "cta_close": ""}
    return {
        "hook_0_3s": sentences[0],
        "body_demo": " ".join(sentences[1:-1]),
        "cta_close": sentences[-1],
    }


class SpyAndVideoService:
    def __init__(self, connect, secrets, data_dir: Path, products, china_sourcing, apify=None, treg=None, jev=None):
        self.connect = connect
        self.secrets = secrets
        self.root = Path(data_dir)
        self.media_dir = self.root / "media"
        self.clones_dir = self.media_dir / "clones"
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.clones_dir.mkdir(parents=True, exist_ok=True)
        self.products = products
        self.china_sourcing = china_sourcing
        self.apify = apify
        self.treg = treg
        self.jev = jev

    def spy_product_link(self, url: str, save_to_vault: bool = True) -> dict:
        u = text(url, "url", 600, required=True)
        plat, _, pid = parse_ids_from_url(u)
        cfg = settings.read_settings(self.connect, self.secrets)
        apify_toks = settings.apify_tokens(cfg)
        treg_tok = (cfg["providers"].get("treg_key") or "").strip()

        if plat in ("1688", "taobao", "pinduoduo"):
            res = self.china_sourcing.search_and_save(u, platform=plat, limit=3)
            return {
                "kind": "china_source",
                "platform": plat,
                "china_items": res["items"],
                "summary": f"Soi link nguồn hàng {plat.upper()}: bóc tách {len(res['items'])} mẫu",
            }

        item = None
        if plat == "shopee" and apify_toks and self.apify:
            try:
                item = self.apify.scrape_shopee_product(apify_toks, u)
            except Exception:
                item = None
        elif plat == "tiktok_shop" and apify_toks and self.apify:
            try:
                item = self.apify.scrape_tiktok_shop_detail(apify_toks, u)
            except Exception:
                item = None

        if not item and treg_tok and self.treg:
            try:
                ext = self.treg.call(treg_tok, "treg.web.extract", {"url": u}, method="POST")
                item = {
                    "platform": plat or "shopee",
                    "market": "VN",
                    "native_product_id": pid,
                    "title": str(ext.get("title") or u)[:200],
                    "price_vnd": 0.0,
                    "sold_count": 0,
                    "url": u,
                }
            except Exception:
                pass

        if not item:
            item = {
                "platform": plat or "shopee",
                "market": "VN",
                "native_product_id": pid,
                "title": f"Sản phẩm soi từ link ({plat or 'web'}) #{pid or u[-18:]}",
                "price_vnd": 0.0,
                "sold_count": 0,
                "url": u,
            }

        saved = self.products.upsert_product(item, source="spy_link") if save_to_vault else item
        related_videos = []
        if apify_toks and self.apify and item.get("title"):
            try:
                _, vids = self.apify.search_tiktok_videos(apify_toks, item["title"][:60], limit=6)
                for v in vids[:6]:
                    related_videos.append({
                        "url": str(v.get("webVideoUrl") or v.get("url") or ""),
                        "caption": str(v.get("text") or v.get("desc") or "")[:160],
                        "views": int(v.get("playCount") or v.get("views") or 0),
                    })
            except Exception:
                pass

        return {
            "kind": "marketplace_product",
            "product": saved,
            "related_tiktok_videos": related_videos,
            "summary": f"Đã soi sản phẩm: {saved.get('title', '')[:65]} (Đã bán: {saved.get('sold_count', 0)})",
        }

    def spy_fanpage(self, fanpage_query: str) -> dict:
        q = text(fanpage_query, "fanpage_query", 240, required=True)
        cfg = settings.read_settings(self.connect, self.secrets)
        apify_toks = settings.apify_tokens(cfg)
        treg_tok = (cfg["providers"].get("treg_key") or "").strip()

        ads = []
        source_used = "none"
        if apify_toks and self.apify:
            try:
                slug, ads = self.apify.search_facebook_ads(apify_toks, q, limit=12)
                source_used = f"apify:{slug}"
            except Exception:
                ads = []
        if not ads and treg_tok and self.treg:
            try:
                res = self.treg.call(treg_tok, "crawl4ai.meta-ads.library.search", {"query": q, "country": "VN"}, method="POST")
                ads = self.treg._extract_list(res)
                source_used = "treg:meta_ads_library"
            except Exception:
                ads = []

        outbound_links: list[dict] = []
        for ad in ads:
            body_txt = str(ad.get("adText") or ad.get("body") or ad.get("text") or "").strip()
            link = str(ad.get("linkUrl") or ad.get("ctaUrl") or ad.get("url") or "").strip()
            urls_found = re.findall(r"https?://[^\s\"'<>]+", f"{body_txt} {link}")
            for u in urls_found:
                if any(dom in u.lower() for dom in ("shopee.", "tiktok.", "lazada.", "shp.ee")):
                    outbound_links.append({
                        "url": u,
                        "ad_caption": body_txt[:180],
                        "page_name": str(ad.get("pageName") or q),
                    })
        return {
            "fanpage_query": q,
            "source_used": source_used,
            "ads_count": len(ads),
            "outbound_commerce_links": outbound_links[:25],
            "ads_sample": [
                {
                    "page_name": str(a.get("pageName") or q),
                    "text": str(a.get("adText") or a.get("body") or a.get("text") or "")[:240],
                    "link_url": str(a.get("linkUrl") or a.get("ctaUrl") or ""),
                }
                for a in ads[:12]
            ],
            "summary": f"Soi Fanpage / Ads '{q}': {len(ads)} mẫu quảng cáo, {len(outbound_links)} link sàn TMĐT",
        }

    def evaluate_video(self, body: dict) -> dict:
        video_url = str(body.get("video_url") or "").strip()
        upload_b64 = str(body.get("file_base64") or "").strip()
        caption = str(body.get("caption") or "").strip()
        transcript = str(body.get("transcript") or "").strip()
        if not video_url and not upload_b64 and not caption:
            raise ValueError("Vui lòng nhập URL video TikTok/Reels hoặc tải file MP4")

        cfg = settings.read_settings(self.connect, self.secrets)
        apify_toks = settings.apify_tokens(cfg)
        treg_tok = (cfg["providers"].get("treg_key") or "").strip()
        typesafe_key = (cfg["providers"].get("typesafe_key") or "").strip()

        vkey = hashlib.sha256((video_url or caption or uuid.uuid4().hex).encode("utf-8")).hexdigest()[:14]
        local_mp4 = self.media_dir / f"vid_{vkey}.mp4"
        author_handle = ""
        views = 0

        if upload_b64:
            raw_b64 = upload_b64.split(",", 1)[-1]
            data = base64.b64decode(raw_b64)
            if len(data) > 45 * 1024 * 1024:
                raise OverflowError("File video tải lên vượt quá 45MB")
            local_mp4.write_bytes(data)
        elif video_url:
            # STRICT PRIORITY #1: Apify Store API (clockworks~tiktok-video-scraper + transcript)
            if apify_toks and self.apify:
                try:
                    rows = self.apify.run_sync_items(
                        apify_toks,
                        "clockworks~tiktok-video-scraper",
                        {"postURLs": [video_url], "shouldDownloadVideos": True},
                        max_charge_usd=0.04,
                    )
                    if rows:
                        r0 = rows[0]
                        caption = caption or str(r0.get("text") or r0.get("desc") or "")
                        author_handle = str((r0.get("authorMeta") or {}).get("name") or "")
                        views = int(r0.get("playCount") or 0)
                        dl_url = str(r0.get("mediaUrls", [""])[0] if isinstance(r0.get("mediaUrls"), list) and r0.get("mediaUrls") else (r0.get("videoUrl") or ""))
                        if dl_url and dl_url.startswith("http"):
                            download_public_video(dl_url, local_mp4)
                except Exception:
                    pass
                if not transcript:
                    try:
                        tr_rows = self.apify.run_sync_items(
                            apify_toks,
                            "scrape-creators~best-tiktok-transcripts-scraper",
                            {"videos": [video_url]},
                            max_charge_usd=0.03,
                        )
                        if tr_rows and isinstance(tr_rows[0], dict):
                            transcript = str(tr_rows[0].get("transcript") or tr_rows[0].get("text") or "").strip()
                    except Exception:
                        pass

            # STRICT PRIORITY #2: Treg.to Backup ONLY if Apify missed video/transcript
            if treg_tok and self.treg and (not local_mp4.is_file() or not caption or not transcript):
                if not local_mp4.is_file() or not caption:
                    try:
                        det = self.treg.inspect_tiktok_video(treg_tok, video_url)
                        d_data = det.get("data") if isinstance(det.get("data"), dict) else det
                        caption = caption or str(d_data.get("desc") or d_data.get("title") or "")
                        author_handle = author_handle or str((d_data.get("author") or {}).get("unique_id") or "")
                        views = views or int((d_data.get("statistics") or {}).get("play_count") or d_data.get("views") or 0)
                        play_url = str(((d_data.get("video") or {}).get("play_addr") or {}).get("url_list", [""])[0] or "")
                        if play_url and not local_mp4.is_file():
                            download_public_video(play_url, local_mp4)
                    except Exception:
                        pass
                if not transcript:
                    try:
                        tr = self.treg.fetch_tiktok_transcript(treg_tok, video_url)
                        transcript = str(tr.get("transcript") or tr.get("text") or (tr.get("data") or {}).get("transcript") or "").strip()
                    except Exception:
                        pass

        frame_files, frames_b64 = ([], {})
        if local_mp4.is_file():
            frame_files, frames_b64 = extract_4_keyframes(local_mp4, self.media_dir)

        script_3part = split_3part_script(transcript or caption)
        meta = {
            "video_url": video_url,
            "author_handle": author_handle,
            "views": views,
            "caption": caption[:500],
            "transcript": transcript[:1500],
            "script_3part": script_3part,
            "review_mode": "multimodal_4frames" if frames_b64 else ("transcript_and_caption" if transcript else "caption_only"),
        }

        jev_res = None
        if typesafe_key and self.jev:
            jev_res = self.jev.evaluate_video(
                typesafe_key,
                meta,
                frames_b64=frames_b64 or None,
                model=cfg["providers"].get("jev_model") or "jev-1.14.0",
                base_url=cfg["providers"].get("jev_base_url") or "https://api.typesafe.ai/v1/systemone",
            )

        record = {
            **meta,
            "frame_urls": [f"/api/media/{fn}" for fn in frame_files],
            "jev_evaluation": jev_res,
        }
        ts = now()
        score_val = jev_res["overall_10"] if jev_res else None
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO video_reviews
                (video_key, platform, video_url, author_handle, is_important, jev_score, linked_product_ids_json, manual_prompts_json, record, created_at, updated_at)
                VALUES (?, 'tiktok', ?, ?, 0, ?, '[]', '[]', ?, ?, ?)
                ON CONFLICT(video_key) DO UPDATE SET
                    jev_score=COALESCE(excluded.jev_score, video_reviews.jev_score),
                    record=excluded.record,
                    updated_at=excluded.updated_at
                """,
                (vkey, video_url, author_handle, score_val, json.dumps(record, ensure_ascii=False), ts, ts),
            )
        return {
            "video_key": vkey,
            "review": self.get_video_review(vkey),
            "summary": f"Đánh giá Video @{author_handle or 'clip'}: Điểm Jev {score_val if score_val is not None else 'N/A'}/10",
        }

    def list_watchlist(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM video_reviews ORDER BY is_important DESC, updated_at DESC LIMIT 80").fetchall()
        return [self._format_video_row(r) for r in rows]

    def get_video_review(self, video_key: str) -> dict | None:
        with self.connect() as conn:
            r = conn.execute("SELECT * FROM video_reviews WHERE video_key=?", (video_key,)).fetchone()
        return self._format_video_row(r) if r else None

    def update_watchlist_item(self, video_key: str, body: dict) -> dict:
        with self.connect() as conn:
            r = conn.execute("SELECT * FROM video_reviews WHERE video_key=?", (video_key,)).fetchone()
            if not r:
                raise ApiError("404 Not Found", "Không tìm thấy video trong danh sách theo dõi")
            imp = int(bool(body["is_important"])) if "is_important" in body else int(r["is_important"])
            prompts = body.get("manual_prompts") if isinstance(body.get("manual_prompts"), list) else json.loads(r["manual_prompts_json"] or "[]")
            conn.execute(
                "UPDATE video_reviews SET is_important=?, manual_prompts_json=?, updated_at=? WHERE video_key=?",
                (imp, json.dumps(prompts, ensure_ascii=False), now(), video_key),
            )
        return self.get_video_review(video_key)

    @staticmethod
    def _format_video_row(r) -> dict:
        return {
            "id": r["id"],
            "video_key": r["video_key"],
            "video_url": r["video_url"],
            "author_handle": r["author_handle"],
            "is_important": bool(r["is_important"]),
            "jev_score": r["jev_score"],
            "manual_prompts": json.loads(r["manual_prompts_json"] or "[]"),
            "detail": json.loads(r["record"] or "{}"),
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }

    def clone_video_15s(self, body: dict) -> dict:
        source_url = str(body.get("source_url") or "").strip()
        upload_b64 = str(body.get("file_base64") or "").strip()
        clone_mode = str(body.get("clone_mode") or "product_swap").strip()
        target_pid = int(body["target_product_id"]) if body.get("target_product_id") else None
        target_shop_id = str(body.get("target_shop_id") or "").strip()
        custom_product_name = str(body.get("product_name") or "").strip()

        prod = self.products.get_product(target_pid) if target_pid else None
        prod_title = (prod["title"] if prod else custom_product_name) or "Sản phẩm chủ lực của Shop"

        clone_id = f"vcl_{uuid.uuid4().hex[:10]}"
        out_dir = self.clones_dir / clone_id
        out_dir.mkdir(parents=True, exist_ok=True)
        src_mp4 = out_dir / "source.mp4"

        if upload_b64:
            src_mp4.write_bytes(base64.b64decode(upload_b64.split(",", 1)[-1]))
        elif source_url and source_url.startswith("http"):
            try:
                download_public_video(source_url, src_mp4)
            except Exception:
                pass

        if src_mp4.is_file():
            dur = probe_duration_sec(src_mp4)
            raw_segs = slice_15s_segments(src_mp4, out_dir, max_seg_sec=15.0)
        else:
            dur = 15.0
            raw_segs = [{"segment_index": 1, "start_sec": 0.0, "end_sec": 15.0, "duration_sec": 15.0, "clip_file": "", "thumb_file": ""}]

        voice_lock = {
            "speaker_id": "vn_female_shop_host_01",
            "voice_style": "Nữ miền Bắc trẻ trung, nhịp nhanh, rõ chữ, tự nhiên như review thật tại nhà",
            "rule": "Giữ đồng nhất 1 giọng đọc xuyên suốt tất cả phân cảnh B-roll & cận cảnh sản phẩm",
        }

        enriched_segments = []
        for seg in raw_segs:
            image_prompt_json = {
                "engine": "Nano Banana 2.1",
                "aspect_ratio": "9:16",
                "mode": clone_mode,
                "subject_product": prod_title,
                "visual_prompt": (
                    f"Vertical 9:16 commercial smartphone shot showcasing '{prod_title}' in a bright Vietnamese home setting, "
                    f"authentic natural daylight, crisp product texture, clean hands demonstrating usage, ultra-realistic --ar 9:16"
                ),
            }
            video_prompt_json = {
                "engine": "Gemini Omni 1.2 Flash",
                "duration_sec": seg["duration_sec"],
                "resolution": "4K 9:16",
                "voice_identity_lock": voice_lock,
                "shots": [
                    {
                        "time": "0.0s - 3.0s",
                        "role": "HOOK",
                        "camera": "Handheld quick zoom-in close-up",
                        "action": f"Mở đầu trực diện vào vấn đề hàng ngày và đưa '{prod_title}' vào khung hình ngay giây đầu",
                        "voiceover_vi": f"Đừng mua hàng trôi nổi nữa, nhìn cách {prod_title[:45]} xử lý gọn trong ba giây này!",
                    },
                    {
                        "time": f"3.0s - {max(4.0, round(seg['duration_sec'] - 3.0, 1))}s",
                        "role": "DEMO_PROOF",
                        "camera": "Macro detail + real-time action cut",
                        "action": f"Test thực tế công năng, độ bền và chi tiết hoàn thiện của {prod_title}",
                        "voiceover_vi": "Chất liệu dày dặn, cầm chắc tay, dùng cực kỳ tiện cho cả gia đình mỗi ngày.",
                    },
                    {
                        "time": f"{max(4.0, round(seg['duration_sec'] - 3.0, 1))}s - {seg['duration_sec']}s",
                        "role": "CTA_SHOP",
                        "camera": "Clean hero packshot with subtle hand gesture to cart",
                        "action": "Đặt sản phẩm kèm quà tặng/combo của Shop, kêu gọi bấm mua ngay",
                        "voiceover_vi": "Shop đang trợ giá lô mới về kho, bấm vào giỏ hàng đặt ngay kẻo hết ưu đãi nhé!",
                    },
                ],
            }
            enriched_segments.append({
                **seg,
                "clip_url": f"/api/video-cloner/media/{clone_id}/{seg['clip_file']}" if seg["clip_file"] else "",
                "thumb_url": f"/api/video-cloner/media/{clone_id}/{seg['thumb_file']}" if seg["thumb_file"] else "",
                "image_prompt_json": image_prompt_json,
                "video_prompt_json": video_prompt_json,
            })

        rec = {"product_title": prod_title, "voice_identity_lock": voice_lock, "ffmpeg": ffmpeg_status()}
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO video_clones
                (clone_id, source_url, clone_mode, target_product_id, target_shop_id, duration_sec, segments_json, record, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clone_id,
                    source_url,
                    clone_mode,
                    target_pid,
                    target_shop_id,
                    dur,
                    json.dumps(enriched_segments, ensure_ascii=False),
                    json.dumps(rec, ensure_ascii=False),
                    now(),
                ),
            )
        return {
            "clone_id": clone_id,
            "clone": self.get_clone(clone_id),
            "summary": f"Đã tạo kịch bản Clone Video <=15s ({len(enriched_segments)} phân đoạn) cho '{prod_title[:50]}'",
        }

    def list_clones(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM video_clones ORDER BY created_at DESC LIMIT 40").fetchall()
        return [self._format_clone(r) for r in rows]

    def get_clone(self, clone_id: str) -> dict | None:
        with self.connect() as conn:
            r = conn.execute("SELECT * FROM video_clones WHERE clone_id=?", (clone_id,)).fetchone()
        return self._format_clone(r) if r else None

    @staticmethod
    def _format_clone(r) -> dict:
        return {
            "clone_id": r["clone_id"],
            "source_url": r["source_url"],
            "clone_mode": r["clone_mode"],
            "target_product_id": r["target_product_id"],
            "target_shop_id": r["target_shop_id"],
            "duration_sec": r["duration_sec"],
            "segments": json.loads(r["segments_json"] or "[]"),
            "detail": json.loads(r["record"] or "{}"),
            "created_at": r["created_at"],
        }

    def _serve_media(self, base: Path, filename: str):
        if "/" in filename or "\\" in filename or ".." in filename or "\x00" in filename:
            raise ApiError("404 Not Found", "Tên file không hợp lệ")
        target = (base / filename).resolve()
        if base.resolve() not in target.parents or not target.is_file():
            raise ApiError("404 Not Found", "Không tìm thấy file media")
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        data = target.read_bytes()
        return "200 OK", Raw(data, [("Content-Type", ctype), ("Content-Length", str(len(data)))])

    def dispatch(self, path: str, method: str, env, read_json):
        if path == "/api/spy/product" and method == "POST":
            body = json_object(read_json, env)
            return "200 OK", self.spy_product_link(text(body.get("url"), "url", 600, required=True), save_to_vault=bool(body.get("save_to_vault", True)))
        if path == "/api/spy/fanpage" and method == "POST":
            body = json_object(read_json, env)
            return "200 OK", self.spy_fanpage(text(body.get("fanpage_query"), "fanpage_query", 240, required=True))
        if path == "/api/videos/watchlist" and method == "GET":
            return "200 OK", {"videos": self.list_watchlist(), "ffmpeg": ffmpeg_status()}
        if path == "/api/videos/evaluate" and method == "POST":
            body = json_object(read_json, env, max_bytes=50 * 1024 * 1024)
            return "200 OK", self.evaluate_video(body)
        if path.startswith("/api/videos/watchlist/") and method in ("PATCH", "POST"):
            vkey = path.strip("/").split("/")[3]
            return "200 OK", {"video": self.update_watchlist_item(vkey, json_object(read_json, env))}
        if path == "/api/video-cloner" and method == "GET":
            return "200 OK", {"clones": self.list_clones(), "ffmpeg": ffmpeg_status()}
        if path == "/api/video-cloner/clone" and method == "POST":
            body = json_object(read_json, env, max_bytes=50 * 1024 * 1024)
            return "200 OK", self.clone_video_15s(body)
        if path.startswith("/api/media/") and method == "GET":
            return self._serve_media(self.media_dir, path[len("/api/media/"):])
        if path.startswith("/api/video-cloner/media/") and method == "GET":
            parts = path.strip("/").split("/")
            if len(parts) == 5:
                return self._serve_media(self.clones_dir / parts[3], parts[4])
        return None
