"""Kalodata Import Wizard (`.xlsx`/`.csv`/`.json`/`.zip` Preview -> Atomic Commit) & Bounded Browser Table Capture.

Ports the full Import Wizard, Assisted Capture (`capture_manifest.json`), and Live Browser Table Capture
(`current-page` & `bounded-pages` + `.zip`/`.csv`/`.json` bundle download) from `affiliate-peng` into
Global Shop Dianshang (`products`, `product_metric_history`, `shops`, `creator_leads`, `video_reviews`).
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
from pathlib import PurePosixPath
import re
from urllib.parse import parse_qs
import uuid
import zipfile

from . import settings
from .chrome_profile_hub import cdp_ws_eval
from .kalodata_hunter import format_vnd_compact, parse_kalodata_count_or_float, parse_kalodata_money_vnd, scrub_portal_text
from .kalodata_parser import parse_kalodata_display_cell, parse_xlsx_bytes
from .products import infer_industry
from .responses import ApiError, Raw, json_object, now, safe_csv_cell, safe_id_str

MAX_IMPORT_BYTES = 15 * 1024 * 1024
MAX_ZIP_ENTRIES = 40
MAX_BOUNDED_PAGES = 25
MAX_BOUNDED_ROWS = 500

SENSITIVE_KEY_SCRUB_RE = re.compile(r"(?:cookie|token|password|passwd|secret|authorization|session_id)", re.IGNORECASE)

DEFAULT_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "product_id": ("product_id", "id", "item_id", "sp_id", "mã sp", "ma sp", "商品id", "product id"),
    "product_name": ("product_name", "title", "name", "product_title", "tên sản phẩm", "ten san pham", "tên sp", "商品名称", "商品信息", "product"),
    "price": ("price", "unit_price", "avg_price", "giá", "gia", "giá bán", "价格", "平均销售价"),
    "gmv": ("gmv", "revenue", "doanh thu", "doanh số", "成交金额", "total_gmv", "gmv 7 ngày"),
    "video_gmv": ("video_gmv", "video_revenue", "doanh thu video", "视频成交", "video revenue"),
    "live_gmv": ("live_gmv", "live_revenue", "doanh thu live", "直播成交", "live revenue"),
    "units_sold": ("units_sold", "items_sold", "sold", "sales", "sale", "lượt bán", "đã bán", "số lượng bán", "销量"),
    "commission_pct": ("commission_pct", "commission", "commission_rate", "hoa hồng", "tỷ lệ hoa hồng", "佣金比例"),
    "creators_count": ("creators_count", "creator_count", "active_creators", "số creator", "达人数量", "creators"),
    "shop_id": ("shop_id", "seller_id", "mã shop", "店铺id"),
    "shop_name": ("shop_name", "seller_name", "tên shop", "gian hàng", "店铺名称", "店铺信息", "shop"),
    "creator_id": ("creator_id", "creator_uid", "达人id"),
    "handle": ("handle", "creator_handle", "username", "author_handle", "tài khoản", "kênh", "达人号", "达人信息", "creator"),
    "followers": ("followers", "follower_count", "followers_count", "người theo dõi", "follow", "粉丝数"),
    "video_id": ("video_id", "aweme_id", "mã video", "视频id"),
    "video_url": ("video_url", "tiktok_url", "url", "link", "link video"),
    "caption": ("caption", "description", "video_title", "mô tả", "nội dung", "视频内容", "标题"),
    "views": ("views", "play_count", "views_count", "lượt xem", "观看", "观看次数"),
    "gpm": ("gpm", "千次观看成交", "千次观看成交金额"),
    "ad_roas": ("ad_roas", "roas", "ad2roas", "广告roas"),
    "market": ("market", "country", "region", "quốc gia", "thị trường", "站点"),
}

HALTING_SESSION_STATES = ("login_required", "expired", "captcha_required", "permission_limited")


def scrub_sensitive_dict(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if SENSITIVE_KEY_SCRUB_RE.search(str(k)):
                continue
            out[k] = scrub_sensitive_dict(v)
        return out
    if isinstance(obj, list):
        return [scrub_sensitive_dict(x) for x in obj]
    return obj


def validate_safe_relpath(filename: str) -> str:
    s = str(filename or "").strip().replace("\\", "/")
    if not s or "\x00" in s or s.startswith("/") or ":" in s:
        raise ValueError(f"Tên tệp không an toàn: {filename!r}")
    p = PurePosixPath(s)
    if any(part in ("..", "") for part in p.parts if part != p.name):
        if ".." in p.parts:
            raise ValueError(f"Từ chối đường dẫn chứa '..': {filename!r}")
    return p.name


def infer_entity_from_filename(name: str, explicit_entity: str = "") -> str:
    if explicit_entity and explicit_entity in (
        "products",
        "affiliates",
        "videos",
        "product_competition",
        "creators",
        "creator_videos",
        "shops",
        "summary",
    ):
        return explicit_entity
    low = (name or "").lower()
    if low.endswith(".md") or "summary" in low:
        return "summary"
    if "creator_video" in low:
        return "creator_videos"
    if "affiliate" in low or "creator" in low or "达人" in low:
        return "creators"
    if "video" in low or "视频" in low:
        return "videos"
    if "shop" in low or "店铺" in low:
        return "shops"
    if "competition" in low:
        return "product_competition"
    return "products"


def _resolve_col_value(row: dict, canonical_key: str, custom_map: dict | None = None) -> str:
    if not isinstance(row, dict):
        return ""
    norm_row = {str(k).strip().lower(): v for k, v in row.items()}
    if custom_map and canonical_key in custom_map:
        mapped_col = str(custom_map[canonical_key]).strip().lower()
        if mapped_col in norm_row and norm_row[mapped_col] is not None:
            return str(norm_row[mapped_col]).strip()
    for alias in DEFAULT_COLUMN_ALIASES.get(canonical_key, (canonical_key,)):
        al = alias.lower()
        if al in norm_row and norm_row[al] is not None:
            return str(norm_row[al]).strip()
    for k_low, val in norm_row.items():
        if any(al in k_low for al in DEFAULT_COLUMN_ALIASES.get(canonical_key, ()) if len(al) >= 3):
            if val is not None:
                return str(val).strip()
    return ""


def _parse_text_or_bytes_table(name: str, raw_bytes: bytes | None, text_content: str | None) -> list[dict]:
    low = name.lower()
    if low.endswith(".xlsx"):
        if raw_bytes is None:
            raise ValueError("Tệp .xlsx yêu cầu dữ liệu nhị phân base64")
        return parse_xlsx_bytes(raw_bytes)
    txt = text_content if text_content is not None else (raw_bytes.decode("utf-8-sig", errors="replace") if raw_bytes else "")
    txt = txt.strip()
    if not txt:
        return []
    if low.endswith(".md"):
        return [{"summary_markdown": txt}]
    if low.endswith(".json") or txt.startswith("[") or txt.startswith("{"):
        parsed = json.loads(txt)
        if isinstance(parsed, list):
            return [scrub_sensitive_dict(x) for x in parsed if isinstance(x, dict)]
        if isinstance(parsed, dict):
            for k in ("items", "rows", "data", "products", "videos", "creators", "shops"):
                if isinstance(parsed.get(k), list):
                    return [scrub_sensitive_dict(x) for x in parsed[k] if isinstance(x, dict)]
            return [scrub_sensitive_dict(parsed)]
        return []
    reader = csv.DictReader(io.StringIO(txt))
    return [scrub_sensitive_dict(dict(r)) for r in reader]


class KalodataImportAndCaptureService:
    """Handles `.xlsx`/`.csv`/`.json`/`.zip` Kalodata Import Wizard, Assisted Capture & Live Browser Table Capture."""

    def __init__(self, connect, secrets, products, chrome_hub, shops=None, custom_capture_driver=None):
        self.connect = connect
        self.secrets = secrets
        self.products = products
        self.chrome_hub = chrome_hub
        self.shops = shops
        self.custom_capture_driver = custom_capture_driver

    def get_capabilities(self) -> dict:
        if getattr(self, "kalodata_bridge", None) is not None:
            self.kalodata_bridge.sync_from_affiliate_peng_if_changed(force=False, notify_on_change=True)
        cfg = settings.read_settings(self.connect, self.secrets)
        kcfg = cfg.get("kalodata") or {}
        has_email = bool((kcfg.get("account_email") or "").strip())
        has_pw = bool(self.secrets.get("kalodata.password"))
        has_cookie = bool(self.secrets.get("kalodata.session_cookie"))
        live_port = self.chrome_hub.get_live_port() if self.chrome_hub else None
        session_state = "session_attached" if (live_port or has_cookie) else ("credentials_saved" if (has_email and has_pw) else "login_required")
        return {
            "provider": "kalodata",
            "session_state": session_state,
            "account_email": kcfg.get("account_email") or "",
            "market": kcfg.get("market") or "VN",
            "currency": kcfg.get("currency") or "VND",
            "default_window_days": int(kcfg.get("default_window_days") or 7),
            "cdp_live_port": live_port,
            "capabilities": {
                "kalodata_pro_9_pages_cdp": True,
                "kalodata_vn_direct_hunter": True,
                "import_xlsx_csv_json_zip": True,
                "browser_table_capture_bounded": True,
                "assisted_browser_capture": True,
                "account_rotation_chrome": True,
                "official_public_api": False,
            },
        }

    def unpack_bundle_inputs(self, body: dict) -> list[dict]:
        entries: list[dict] = []
        explicit_entity = str(body.get("entity_type") or "").strip()

        if body.get("zip_base64"):
            raw_z = base64.b64decode(str(body["zip_base64"]))
            if len(raw_z) > MAX_IMPORT_BYTES:
                raise ApiError("413 Payload Too Large", "Gói .zip vượt quá giới hạn 15MB")
            with zipfile.ZipFile(io.BytesIO(raw_z), "r") as zf:
                infos = [i for i in zf.infolist() if not i.is_dir()]
                if len(infos) > MAX_ZIP_ENTRIES:
                    raise ApiError("400 Bad Request", f"Gói .zip chứa quá {MAX_ZIP_ENTRIES} tệp")
                for inf in infos:
                    safe_name = validate_safe_relpath(inf.filename)
                    if safe_name.startswith(".") or safe_name == "capture_manifest.json":
                        continue
                    b_data = zf.read(inf.filename)
                    rows = _parse_text_or_bytes_table(safe_name, b_data, None)
                    entries.append({
                        "filename": safe_name,
                        "entity_type": infer_entity_from_filename(safe_name, explicit_entity),
                        "rows": rows,
                        "sha256": hashlib.sha256(b_data).hexdigest(),
                    })

        for f_obj in (body.get("files") or []):
            if not isinstance(f_obj, dict):
                continue
            fname = validate_safe_relpath(str(f_obj.get("name") or f_obj.get("filename") or "kalodata.json"))
            if fname == "capture_manifest.json":
                continue
            ent = infer_entity_from_filename(fname, str(f_obj.get("entity_type") or explicit_entity))
            if f_obj.get("base64"):
                b_data = base64.b64decode(str(f_obj["base64"]))
                if len(b_data) > MAX_IMPORT_BYTES:
                    raise ApiError("413 Payload Too Large", f"Tệp {fname} vượt quá 15MB")
                rows = _parse_text_or_bytes_table(fname, b_data, None)
                h_hex = hashlib.sha256(b_data).hexdigest()
            else:
                txt = str(f_obj.get("content") or "")
                b_utf8 = txt.encode("utf-8")
                rows = _parse_text_or_bytes_table(fname, None, txt)
                h_hex = hashlib.sha256(b_utf8).hexdigest()
            entries.append({"filename": fname, "entity_type": ent, "rows": rows, "sha256": h_hex})

        if not entries and body.get("content"):
            fname = validate_safe_relpath(str(body.get("filename") or f"{explicit_entity or 'products'}.json"))
            txt = str(body.get("content") or "")
            rows = _parse_text_or_bytes_table(fname, None, txt)
            entries.append({
                "filename": fname,
                "entity_type": infer_entity_from_filename(fname, explicit_entity),
                "rows": rows,
                "sha256": hashlib.sha256(txt.encode("utf-8")).hexdigest(),
            })

        if not entries:
            raise ApiError("400 Bad Request", "Không có tệp hoặc dữ liệu CSV/JSON/XLSX/ZIP nào để kiểm tra.")
        return entries

    def preview_import(self, body: dict, *, source_type: str = "kalodata_wizard") -> dict:
        market = str(body.get("market") or "VN").strip().upper()
        currency = str(body.get("currency") or "VND").strip().upper()
        window_spec = str(body.get("window") or body.get("window_spec") or "7d").strip()
        custom_map = body.get("mapping_profile") if isinstance(body.get("mapping_profile"), dict) else {}
        entries = self.unpack_bundle_inputs(body)

        hasher = hashlib.sha256(f"{market}|{currency}|{window_spec}".encode("utf-8"))
        for e in sorted(entries, key=lambda x: x["filename"]):
            hasher.update(e["sha256"].encode("ascii"))
        bundle_hash = hasher.hexdigest()

        staged_products: list[dict] = []
        staged_videos: list[dict] = []
        staged_creators: list[dict] = []
        staged_shops: list[dict] = []
        summary_notes: list[str] = []
        errors: list[dict] = []

        for entry in entries:
            ent = entry["entity_type"]
            fname = entry["filename"]
            for r_idx, row in enumerate(entry["rows"], start=1):
                row_mkt = _resolve_col_value(row, "market", custom_map).upper()
                if row_mkt and row_mkt not in (market, ""):
                    errors.append({
                        "file": fname,
                        "row": r_idx,
                        "code": "market_mismatch_blocked",
                        "message": f"Dòng #{r_idx} thuộc thị trường '{row_mkt}' khác với phạm vi '{market}' đã chọn.",
                    })
                    continue

                if ent == "summary":
                    md = str(row.get("summary_markdown") or "").strip()
                    if md:
                        summary_notes.append(md[:2000])
                    continue

                if ent in ("products", "product_competition"):
                    pid = safe_id_str(_resolve_col_value(row, "product_id", custom_map))
                    pname = scrub_portal_text(_resolve_col_value(row, "product_name", custom_map), 240)
                    if not pid and not pname:
                        errors.append({"file": fname, "row": r_idx, "code": "missing_product_identity", "message": "Thiếu cả Mã SP và Tên SP"})
                        continue
                    pr_cell = parse_kalodata_display_cell(_resolve_col_value(row, "price", custom_map), expected_currency=currency)
                    gmv_cell = parse_kalodata_display_cell(_resolve_col_value(row, "gmv", custom_map), expected_currency=currency)
                    vgmv_cell = parse_kalodata_display_cell(_resolve_col_value(row, "video_gmv", custom_map), expected_currency=currency)
                    lgmv_cell = parse_kalodata_display_cell(_resolve_col_value(row, "live_gmv", custom_map), expected_currency=currency)
                    sold_cell = parse_kalodata_display_cell(_resolve_col_value(row, "units_sold", custom_map))
                    comm_cell = parse_kalodata_display_cell(_resolve_col_value(row, "commission_pct", custom_map))
                    cr_cell = parse_kalodata_display_cell(_resolve_col_value(row, "creators_count", custom_map))

                    staged_products.append({
                        "native_product_id": pid,
                        "title": pname or f"Kalodata Product #{pid}",
                        "market": market,
                        "currency": currency,
                        "window_spec": window_spec,
                        "price": float(pr_cell["value_decimal"]) if pr_cell["value_decimal"] is not None else None,
                        "gmv": float(gmv_cell["value_decimal"]) if gmv_cell["value_decimal"] is not None else None,
                        "video_gmv": float(vgmv_cell["value_decimal"]) if vgmv_cell["value_decimal"] is not None else None,
                        "live_gmv": float(lgmv_cell["value_decimal"]) if lgmv_cell["value_decimal"] is not None else None,
                        "units_sold": int(round(float(sold_cell["value_decimal"]))) if sold_cell["value_decimal"] is not None else None,
                        "commission_pct": float(comm_cell["value_decimal"]) if comm_cell["value_decimal"] is not None else None,
                        "creators_count": int(round(float(cr_cell["value_decimal"]))) if cr_cell["value_decimal"] is not None else None,
                        "locked_fields": [k for k, c in (("gmv", gmv_cell), ("units_sold", sold_cell)) if c["value_state"] == "locked"],
                    })
                elif ent in ("creators", "affiliates"):
                    handle = _resolve_col_value(row, "handle", custom_map).lstrip("@").strip()
                    cid = safe_id_str(_resolve_col_value(row, "creator_id", custom_map))
                    if not handle and not cid:
                        errors.append({"file": fname, "row": r_idx, "code": "missing_creator_handle", "message": "Thiếu handle KOC/Creator"})
                        continue
                    flw_c = parse_kalodata_display_cell(_resolve_col_value(row, "followers", custom_map))
                    gmv_c = parse_kalodata_display_cell(_resolve_col_value(row, "gmv", custom_map), expected_currency=currency)
                    staged_creators.append({
                        "creator_id": cid,
                        "handle": handle or f"creator_{cid}",
                        "followers": int(round(float(flw_c["value_decimal"]))) if flw_c["value_decimal"] is not None else 0,
                        "gmv": float(gmv_c["value_decimal"]) if gmv_c["value_decimal"] is not None else 0.0,
                    })
                elif ent in ("videos", "creator_videos"):
                    vid = safe_id_str(_resolve_col_value(row, "video_id", custom_map))
                    vurl = _resolve_col_value(row, "video_url", custom_map)
                    if not vid and vurl:
                        m_v = re.search(r"/video/(\d{15,22})", vurl)
                        if m_v:
                            vid = m_v.group(1)
                    if not vid and not vurl:
                        errors.append({"file": fname, "row": r_idx, "code": "missing_video_id", "message": "Thiếu video_id / link video"})
                        continue
                    handle = _resolve_col_value(row, "handle", custom_map).lstrip("@").strip()
                    cap = scrub_portal_text(_resolve_col_value(row, "caption", custom_map), 320)
                    gmv_v = parse_kalodata_display_cell(_resolve_col_value(row, "gmv", custom_map), expected_currency=currency)
                    views_v = parse_kalodata_display_cell(_resolve_col_value(row, "views", custom_map))
                    gpm_v = parse_kalodata_display_cell(_resolve_col_value(row, "gpm", custom_map), expected_currency=currency)
                    roas_v = parse_kalodata_display_cell(_resolve_col_value(row, "ad_roas", custom_map))
                    staged_videos.append({
                        "video_id": vid or uuid.uuid5(uuid.NAMESPACE_URL, vurl).hex[:14],
                        "video_url": vurl or f"https://www.tiktok.com/@{handle or '_'}/video/{vid}",
                        "handle": handle,
                        "caption": cap,
                        "gmv": float(gmv_v["value_decimal"]) if gmv_v["value_decimal"] is not None else None,
                        "views": int(round(float(views_v["value_decimal"]))) if views_v["value_decimal"] is not None else None,
                        "gpm": float(gpm_v["value_decimal"]) if gpm_v["value_decimal"] is not None else None,
                        "ad_roas": float(roas_v["value_decimal"]) if roas_v["value_decimal"] is not None else None,
                    })
                elif ent == "shops":
                    sid = safe_id_str(_resolve_col_value(row, "shop_id", custom_map))
                    sname = scrub_portal_text(_resolve_col_value(row, "shop_name", custom_map), 140)
                    if not sid and not sname:
                        errors.append({"file": fname, "row": r_idx, "code": "missing_shop_name", "message": "Thiếu tên/mã Shop"})
                        continue
                    gmv_s = parse_kalodata_display_cell(_resolve_col_value(row, "gmv", custom_map), expected_currency=currency)
                    staged_shops.append({
                        "shop_id": sid,
                        "shop_name": sname or f"Shop #{sid}",
                        "gmv": float(gmv_s["value_decimal"]) if gmv_s["value_decimal"] is not None else None,
                    })

        batch_id = f"kimp_{uuid.uuid4().hex[:12]}"
        ts = now()
        summary = {
            "files_count": len(entries),
            "market": market,
            "currency": currency,
            "window_spec": window_spec,
            "bundle_hash": bundle_hash,
            "products_staged": len(staged_products),
            "creators_staged": len(staged_creators),
            "videos_staged": len(staged_videos),
            "shops_staged": len(staged_shops),
            "errors_count": len(errors),
            "can_commit": len(staged_products) + len(staged_creators) + len(staged_videos) + len(staged_shops) > 0,
            "sample_products": staged_products[:5],
        }
        staging_payload = {
            "products": staged_products,
            "creators": staged_creators,
            "videos": staged_videos,
            "shops": staged_shops,
            "summary_notes": summary_notes,
        }
        with self.connect() as conn:
            dup_row = conn.execute(
                "SELECT batch_id FROM kalodata_import_batches WHERE bundle_hash=? AND status='committed' LIMIT 1",
                (bundle_hash,),
            ).fetchone()
            summary["duplicate_of_committed_batch"] = dup_row["batch_id"] if dup_row else ""
            conn.execute(
                """
                INSERT INTO kalodata_import_batches
                (batch_id, source_type, market, currency, window_spec, bundle_hash, status, staging_json, summary_json, errors_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'preview', ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    source_type,
                    market,
                    currency,
                    window_spec,
                    bundle_hash,
                    json.dumps(staging_payload, ensure_ascii=False),
                    json.dumps(summary, ensure_ascii=False),
                    json.dumps(errors, ensure_ascii=False),
                    ts,
                ),
            )
        return {"batch_id": batch_id, "status": "preview", "summary": summary, "errors": errors}

    def commit_import(self, batch_id: str, *, allow_skip_invalid: bool = True) -> dict:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM kalodata_import_batches WHERE batch_id=?", (batch_id,)).fetchone()
        if not row:
            raise ApiError("404 Not Found", f"Không tìm thấy lô import {batch_id}")
        if row["status"] == "committed":
            return {
                "ok": True,
                "idempotent_replay": True,
                "batch_id": batch_id,
                "summary": json.loads(row["summary_json"] or "{}"),
            }

        errors = json.loads(row["errors_json"] or "[]")
        blocking = [e for e in errors if e.get("code") == "market_mismatch_blocked"]
        if blocking and not allow_skip_invalid:
            raise ApiError("409 Conflict", f"Có {len(blocking)} dòng sai lệch thị trường bị chặn — bật cho phép bỏ qua dòng lỗi hoặc kiểm tra lại file.")

        staging = json.loads(row["staging_json"] or "{}")
        market = row["market"]
        win = row["window_spec"]
        ts = now()

        saved_pids: list[int] = []
        for p in staging.get("products") or []:
            pid = p.get("native_product_id") or ""
            db_item = self.products.upsert_product(
                {
                    "platform": "tiktok_shop",
                    "market": market,
                    "native_product_id": pid,
                    "title": p["title"],
                    "url": f"https://shop.tiktok.com/view/product/{pid}?region={market}" if pid else "",
                    "price_vnd": float(p.get("price") or 0.0),
                    "sold_count": int(p.get("units_sold") or 0),
                    "gmv_vnd": float(p.get("gmv") or 0.0),
                    "kalodata_import": {
                        "batch_id": batch_id,
                        "window_spec": win,
                        "video_gmv": p.get("video_gmv"),
                        "live_gmv": p.get("live_gmv"),
                        "commission_pct": p.get("commission_pct"),
                        "creators_count": p.get("creators_count"),
                    },
                },
                source=f"kalodata_import:{batch_id}",
            )
            saved_pids.append(int(db_item["id"]))

        saved_creators = 0
        saved_videos = 0
        saved_shops = 0
        with self.connect() as conn:
            for db_pid, p in zip(saved_pids, staging.get("products") or []):
                conn.execute(
                    """
                    INSERT INTO product_metric_history
                    (product_id, source, price_vnd, sold_count, sold_7d, gmv_vnd, gmv_7d_vnd, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        db_pid,
                        f"kalodata_import:{win}",
                        float(p.get("price") or 0.0),
                        int(p.get("units_sold") or 0),
                        int(p.get("units_sold") or 0) if win == "7d" else None,
                        float(p.get("gmv") or 0.0),
                        float(p.get("gmv") or 0.0) if win == "7d" else None,
                        ts,
                    ),
                )

            for c in staging.get("creators") or []:
                h = c["handle"]
                conn.execute(
                    """
                    INSERT INTO creator_leads
                    (creator_id, platform, market, handle, display_name, followers, industry, video_gmv_vnd, avg_views, top_videos_json, note, created_at, updated_at)
                    VALUES (?, 'tiktok', ?, ?, ?, ?, 'khac', ?, 0, '[]', ?, ?, ?)
                    ON CONFLICT(creator_id) DO UPDATE SET
                        followers=MAX(creator_leads.followers, excluded.followers),
                        video_gmv_vnd=MAX(creator_leads.video_gmv_vnd, excluded.video_gmv_vnd),
                        updated_at=excluded.updated_at
                    """,
                    (f"kalo_cr_{h.lower()}", market, h, f"@{h}", int(c.get("followers") or 0), float(c.get("gmv") or 0.0), f"Import Kalodata ({batch_id})", ts, ts),
                )
                saved_creators += 1

            for v in staging.get("videos") or []:
                conn.execute(
                    """
                    INSERT INTO video_reviews
                    (video_key, platform, video_url, author_handle, is_important, record, created_at, updated_at)
                    VALUES (?, 'tiktok', ?, ?, 0, ?, ?, ?)
                    ON CONFLICT(video_key) DO UPDATE SET
                        video_url=excluded.video_url,
                        record=excluded.record,
                        updated_at=excluded.updated_at
                    """,
                    (f"tiktok:{v['video_id']}", v["video_url"], v["handle"], json.dumps(v, ensure_ascii=False), ts, ts),
                )
                saved_videos += 1

            for s in staging.get("shops") or []:
                sid_k = f"kalo_shop_{s['shop_id'] or uuid.uuid5(uuid.NAMESPACE_DNS, s['shop_name'].lower()).hex[:10]}"
                conn.execute(
                    """
                    INSERT INTO shops
                    (shop_id, role, platform, market, native_shop_id, handle, shop_name, shop_url, industry, status, stats_json, note, created_at, updated_at)
                    VALUES (?, 'competitor_shop', 'tiktok_shop', ?, ?, ?, ?, '', ?, 'active', ?, ?, ?, ?)
                    ON CONFLICT(shop_id) DO UPDATE SET
                        shop_name=excluded.shop_name,
                        stats_json=excluded.stats_json,
                        updated_at=excluded.updated_at
                    """,
                    (sid_k, market, s["shop_id"], s["shop_name"][:80], s["shop_name"], infer_industry(s["shop_name"]), json.dumps(s, ensure_ascii=False), f"Import Kalodata ({batch_id})", ts, ts),
                )
                saved_shops += 1

            summary = json.loads(row["summary_json"] or "{}")
            summary.update({
                "committed_products": len(saved_pids),
                "committed_product_ids": saved_pids,
                "committed_creators": saved_creators,
                "committed_videos": saved_videos,
                "committed_shops": saved_shops,
                "committed_at": ts,
            })
            conn.execute(
                "UPDATE kalodata_import_batches SET status='committed', summary_json=?, committed_at=? WHERE batch_id=?",
                (json.dumps(summary, ensure_ascii=False), ts, batch_id),
            )

        return {"ok": True, "idempotent_replay": False, "batch_id": batch_id, "summary": summary}

    def list_batches(self, limit: int = 25) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT batch_id, source_type, market, currency, window_spec, status, summary_json, created_at, committed_at "
                "FROM kalodata_import_batches ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (max(1, min(50, int(limit))),),
            ).fetchall()
        return [
            {
                "batch_id": r["batch_id"],
                "source_type": r["source_type"],
                "market": r["market"],
                "currency": r["currency"],
                "window_spec": r["window_spec"],
                "status": r["status"],
                "summary": json.loads(r["summary_json"] or "{}"),
                "created_at": r["created_at"],
                "committed_at": r["committed_at"],
            }
            for r in rows
        ]

    def get_batch_errors(self, batch_id: str) -> dict:
        with self.connect() as conn:
            row = conn.execute("SELECT batch_id, status, errors_json, summary_json FROM kalodata_import_batches WHERE batch_id=?", (batch_id,)).fetchone()
        if not row:
            raise ApiError("404 Not Found", f"Không tìm thấy lô import {batch_id}")
        return {
            "batch_id": row["batch_id"],
            "status": row["status"],
            "errors": json.loads(row["errors_json"] or "[]"),
            "summary": json.loads(row["summary_json"] or "{}"),
        }

    def import_assisted_capture(self, body: dict) -> dict:
        manifest = body.get("capture_manifest")
        if isinstance(manifest, str):
            manifest = json.loads(manifest)
        if not isinstance(manifest, dict):
            raise ApiError("400 Bad Request", "Thiếu capture_manifest hợp lệ")
        manifest = scrub_sensitive_dict(manifest)
        s_state = str(manifest.get("session_state") or "").strip().lower()
        if s_state in HALTING_SESSION_STATES:
            return {
                "ok": False,
                "committed": False,
                "session_state": s_state,
                "demo_fallback_used": False,
                "detail": f"Từ chối nạp gói chụp trình duyệt do session_state='{s_state}' (không dùng dữ liệu giả thay thế).",
            }
        for req_k in ("market", "currency", "window", "captured_at"):
            if not manifest.get(req_k):
                raise ApiError("400 Bad Request", f"capture_manifest thiếu trường bắt buộc: {req_k}")

        merged_body = {
            **body,
            "market": manifest["market"],
            "currency": manifest["currency"],
            "window": manifest["window"],
        }
        prev = self.preview_import(merged_body, source_type="assisted_browser_capture")
        comm = self.commit_import(prev["batch_id"], allow_skip_invalid=False)
        return {
            "ok": True,
            "committed": True,
            "session_state": s_state or "authenticated",
            "demo_fallback_used": False,
            "batch_id": prev["batch_id"],
            "summary": comm["summary"],
            "errors": prev["errors"],
        }

    # ------------------------------------------------------------------
    # Live Bounded Browser DOM Table Capture (`current-page` & `bounded-pages`)
    # ------------------------------------------------------------------
    def _extract_current_browser_table(self, max_pages: int = 1, max_rows: int = 100) -> dict:
        if self.custom_capture_driver is not None:
            return self.custom_capture_driver(max_pages=max_pages, max_rows=max_rows)
        port = self.chrome_hub.get_live_port() if self.chrome_hub else None
        if not port:
            raise ApiError("503 Service Unavailable", "Chrome Chuyên Dụng `peng_dedicated` chưa mở — hãy mở Kalodata trong Cài đặt.")
        tabs = self.chrome_hub.list_tabs(port)
        tab = next((t for t in tabs if "kalodata.com" in str(t.get("url") or "").lower()), None)
        if not tab or not tab.get("webSocketDebuggerUrl"):
            raise ApiError("409 Conflict", "Chưa có tab Kalodata nào đang mở trên Chrome Chuyên Dụng.")
        ws = tab["webSocketDebuggerUrl"]

        headers: list[str] = []
        collected: list[dict] = []
        seen: set[str] = set()
        page_url = ""
        pages_read = 0

        for p_idx in range(1, max(1, min(MAX_BOUNDED_PAGES, int(max_pages))) + 1):
            snap = cdp_ws_eval(
                port,
                ws,
                r"""(() => {
                  const cap = document.querySelector("[class*='captcha'], iframe[src*='captcha'], .geetest_panel");
                  if (cap && cap.offsetParent !== null) return JSON.stringify({error: "captcha_required", url: location.href});
                  if (location.pathname.startsWith("/login")) return JSON.stringify({error: "login_required", url: location.href});
                  const ths = Array.from(document.querySelectorAll("table thead th")).map(th => (th.innerText || "").replace(/\s+/g, " ").trim());
                  const trs = Array.from(document.querySelectorAll("table tbody tr:not(.ant-table-measure-row)")).filter(r => r.querySelectorAll("td").length >= 4);
                  const rows = trs.map(tr => {
                    const tds = Array.from(tr.querySelectorAll("td")).map(td => (td.innerText || "").replace(/\s+/g, " ").trim());
                    let rowKey = "";
                    try {
                      const fk = Object.keys(tr).find(k => k.startsWith("__reactFiber"));
                      let cur = fk ? tr[fk] : null;
                      for (let d = 0; d < 16 && cur; d++) {
                        if (cur.key && /^\d{10,22}$/.test(String(cur.key))) { rowKey = String(cur.key); break; }
                        if (cur.memoizedProps?.row?.original?.id) { rowKey = String(cur.memoizedProps.row.original.id); break; }
                        cur = cur.return;
                      }
                    } catch {}
                    return {rowKey, tds};
                  });
                  return JSON.stringify({url: location.href, path: location.pathname, ths, rows});
                })()""",
            )
            if snap.get("error") == "captcha_required":
                raise ApiError("409 Conflict", "Kalodata đang hiện CAPTCHA — vui lòng xác minh trực tiếp trên Chrome Chuyên Dụng.")
            if snap.get("error") == "login_required":
                raise ApiError("401 Unauthorized", "Phiên Kalodata chưa đăng nhập trên Chrome Chuyên Dụng.")

            page_url = str(snap.get("url") or page_url)
            if not headers and snap.get("ths"):
                headers = snap["ths"]
            rows = snap.get("rows") or []
            if not rows:
                break
            pages_read += 1
            for r in rows:
                dk = r.get("rowKey") or "|".join((r.get("tds") or [])[:3])
                if dk in seen:
                    continue
                seen.add(dk)
                row_dict = {"id": r.get("rowKey") or ""}
                for i, h in enumerate(headers):
                    col_name = h or f"col_{i + 1}"
                    row_dict[col_name] = (r.get("tds") or [])[i] if i < len(r.get("tds") or []) else ""
                collected.append(row_dict)
                if len(collected) >= max_rows:
                    break
            if len(collected) >= max_rows or p_idx >= max_pages:
                break
            moved = cdp_ws_eval(
                port,
                ws,
                f"""(() => {{
                  const nextP = "{p_idx + 1}";
                  const pBtns = Array.from(document.querySelectorAll("button[data-slot='pagination-link'], li.ant-pagination-item"));
                  const btn = pBtns.find(b => (b.innerText || "").trim() === nextP && !b.disabled);
                  if (btn) {{ btn.click(); return JSON.stringify({{moved: true}}); }}
                  return JSON.stringify({{moved: false}});
                }})()""",
            )
            if not moved.get("moved"):
                break
            import time as _t
            _t.sleep(1.8)

        return {"url": page_url, "headers": headers, "rows": collected[:max_rows], "pages_read": pages_read}

    def run_browser_capture(self, body: dict, *, bounded: bool = False) -> dict:
        max_pages = int(body.get("max_pages") or (3 if bounded else 1))
        max_rows = int(body.get("max_rows") or (50 if bounded else 100))
        max_pages = max(1, min(MAX_BOUNDED_PAGES, max_pages))
        max_rows = max(1, min(MAX_BOUNDED_ROWS, max_rows))

        market = str(body.get("market") or "VN").strip().upper()
        currency = str(body.get("currency") or "VND").strip().upper()
        window_spec = str(body.get("window_spec") or body.get("window") or "7d").strip()
        entity_type = str(body.get("entity_type") or "").strip()

        extracted = self._extract_current_browser_table(max_pages=max_pages if bounded else 1, max_rows=max_rows)
        page_url = str(extracted.get("url") or "")
        if not entity_type:
            if "/video" in page_url:
                entity_type = "videos"
            elif "/creator" in page_url:
                entity_type = "creators"
            elif "/shop" in page_url:
                entity_type = "shops"
            else:
                entity_type = "products"

        raw_rows = extracted.get("rows") or []
        normalized: list[dict] = []
        for idx, r in enumerate(raw_rows):
            rid = safe_id_str(_resolve_col_value(r, "product_id") if entity_type == "products" else (_resolve_col_value(r, "video_id") or r.get("id") or ""))
            title = scrub_portal_text(
                _resolve_col_value(r, "product_name")
                or _resolve_col_value(r, "caption")
                or _resolve_col_value(r, "handle")
                or _resolve_col_value(r, "shop_name")
                or "",
                200,
            )
            gmv_raw = _resolve_col_value(r, "gmv")
            sold_raw = _resolve_col_value(r, "units_sold")
            normalized.append({
                "row_index": idx,
                "native_id": rid,
                "display_title": title,
                "gmv_raw": gmv_raw,
                "gmv_vnd": parse_kalodata_money_vnd(gmv_raw),
                "units_sold": int(round(parse_kalodata_count_or_float(sold_raw) or 0)) if parse_kalodata_count_or_float(sold_raw) is not None else None,
                "locked": "***" in json.dumps(r, ensure_ascii=False),
            })

        cap_id = f"kcap_{uuid.uuid4().hex[:12]}"
        ts = now()
        manifest = {
            "capture_id": cap_id,
            "capture_mode": "bounded_pages" if bounded else "current_page",
            "entity_type": entity_type,
            "market": market,
            "currency": currency,
            "window": window_spec,
            "page_url": page_url,
            "captured_at": ts,
            "session_state": "authenticated",
        }
        coverage = {
            "pages_read": extracted.get("pages_read", 1),
            "rows_captured": len(raw_rows),
            "locked_rows": sum(1 for x in normalized if x["locked"]),
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO kalodata_capture_runs
                (capture_id, capture_mode, entity_type, market, currency, window_spec, page_url, status,
                 manifest_json, raw_rows_json, normalized_json, excluded_row_indices_json, coverage_json, errors_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'staged_preview', ?, ?, ?, '[]', ?, '[]', ?, ?)
                """,
                (
                    cap_id,
                    manifest["capture_mode"],
                    entity_type,
                    market,
                    currency,
                    window_spec,
                    page_url,
                    json.dumps(manifest, ensure_ascii=False),
                    json.dumps(raw_rows, ensure_ascii=False),
                    json.dumps(normalized, ensure_ascii=False),
                    json.dumps(coverage, ensure_ascii=False),
                    ts,
                    ts,
                ),
            )
        return self.get_capture(cap_id)

    def get_capture(self, capture_id: str) -> dict:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM kalodata_capture_runs WHERE capture_id=?", (capture_id,)).fetchone()
        if not row:
            raise ApiError("404 Not Found", f"Không tìm thấy phiên chụp {capture_id}")
        return {
            "capture_id": row["capture_id"],
            "capture_mode": row["capture_mode"],
            "entity_type": row["entity_type"],
            "market": row["market"],
            "currency": row["currency"],
            "window_spec": row["window_spec"],
            "page_url": row["page_url"],
            "status": row["status"],
            "manifest": json.loads(row["manifest_json"] or "{}"),
            "raw_rows": json.loads(row["raw_rows_json"] or "[]"),
            "normalized": json.loads(row["normalized_json"] or "[]"),
            "excluded_row_indices": json.loads(row["excluded_row_indices_json"] or "[]"),
            "coverage": json.loads(row["coverage_json"] or "{}"),
            "committed_batch_id": row["committed_batch_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_captures(self, limit: int = 20) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT capture_id, capture_mode, entity_type, market, window_spec, page_url, status, coverage_json, committed_batch_id, created_at "
                "FROM kalodata_capture_runs ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (max(1, min(50, int(limit))),),
            ).fetchall()
        return [
            {
                "capture_id": r["capture_id"],
                "capture_mode": r["capture_mode"],
                "entity_type": r["entity_type"],
                "market": r["market"],
                "window_spec": r["window_spec"],
                "page_url": r["page_url"],
                "status": r["status"],
                "coverage": json.loads(r["coverage_json"] or "{}"),
                "committed_batch_id": r["committed_batch_id"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def update_capture_exclusions(self, capture_id: str, exclude_indices: list[int]) -> dict:
        cap = self.get_capture(capture_id)
        clean_idx = sorted({int(i) for i in (exclude_indices or []) if int(i) >= 0})
        with self.connect() as conn:
            conn.execute(
                "UPDATE kalodata_capture_runs SET excluded_row_indices_json=?, updated_at=? WHERE capture_id=?",
                (json.dumps(clean_idx), now(), cap["capture_id"]),
            )
        return self.get_capture(capture_id)

    def commit_capture(self, capture_id: str) -> dict:
        cap = self.get_capture(capture_id)
        if cap["status"] == "committed" and cap["committed_batch_id"]:
            return {"ok": True, "idempotent_replay": True, "committed_batch_id": cap["committed_batch_id"], "capture": cap}
        excl = set(cap["excluded_row_indices"])
        kept_rows = [r for i, r in enumerate(cap["raw_rows"]) if i not in excl]
        if not kept_rows:
            raise ApiError("400 Bad Request", "Không còn dòng dữ liệu nào sau khi loại trừ để commit.")
        prev = self.preview_import(
            {
                "market": cap["market"],
                "currency": cap["currency"],
                "window": cap["window_spec"],
                "entity_type": cap["entity_type"],
                "filename": f"{cap['entity_type']}.json",
                "content": json.dumps(kept_rows, ensure_ascii=False),
            },
            source_type="browser_table_capture",
        )
        comm = self.commit_import(prev["batch_id"], allow_skip_invalid=True)
        with self.connect() as conn:
            conn.execute(
                "UPDATE kalodata_capture_runs SET status='committed', committed_batch_id=?, updated_at=? WHERE capture_id=?",
                (prev["batch_id"], now(), capture_id),
            )
        return {
            "ok": True,
            "idempotent_replay": False,
            "committed_batch_id": prev["batch_id"],
            "summary": comm["summary"],
            "capture": self.get_capture(capture_id),
        }

    def export_capture_bundle(self, capture_id: str, fmt: str = "zip") -> tuple[str, Raw]:
        cap = self.get_capture(capture_id)
        f_low = (fmt or "zip").lower()
        if f_low == "json":
            data = json.dumps(cap, ensure_ascii=False, indent=2).encode("utf-8")
            return "200 OK", Raw(data, [("Content-Type", "application/json; charset=utf-8"), ("Content-Disposition", f'attachment; filename="{capture_id}.json"')])
        if f_low == "csv":
            buf = io.StringIO()
            rows = cap["raw_rows"]
            if rows:
                cols = list(rows[0].keys())
                w = csv.writer(buf)
                w.writerow(cols)
                for r in rows:
                    w.writerow([safe_csv_cell(r.get(c, "")) for c in cols])
            data = buf.getvalue().encode("utf-8-sig")
            return "200 OK", Raw(data, [("Content-Type", "text/csv; charset=utf-8"), ("Content-Disposition", f'attachment; filename="{capture_id}.csv"')])

        zbuf = io.BytesIO()
        with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(cap["manifest"], ensure_ascii=False, indent=2))
            zf.writestr("raw_rows.json", json.dumps(cap["raw_rows"], ensure_ascii=False, indent=2))
            zf.writestr("normalized.json", json.dumps(cap["normalized"], ensure_ascii=False, indent=2))
            zf.writestr("coverage.json", json.dumps(cap["coverage"], ensure_ascii=False, indent=2))
            cbuf = io.StringIO()
            if cap["raw_rows"]:
                cols = list(cap["raw_rows"][0].keys())
                w = csv.writer(cbuf)
                w.writerow(cols)
                for r in cap["raw_rows"]:
                    w.writerow([safe_csv_cell(r.get(c, "")) for c in cols])
            zf.writestr("data.csv", cbuf.getvalue())
        return "200 OK", Raw(zbuf.getvalue(), [("Content-Type", "application/zip"), ("Content-Disposition", f'attachment; filename="{capture_id}_bundle.zip"')])

    def dispatch(self, path: str, method: str, env, read_json):
        if path == "/api/imports" and method == "GET":
            return "200 OK", {"items": self.list_batches(limit=25)}
        if path == "/api/imports/preview" and method == "POST":
            return "200 OK", self.preview_import(json_object(read_json, env, max_bytes=MAX_IMPORT_BYTES + 2 * 1024 * 1024))
        if path.startswith("/api/imports/") and path.endswith("/errors") and method == "GET":
            bid = path.split("/")[3]
            return "200 OK", self.get_batch_errors(bid)
        if path.startswith("/api/imports/") and path.endswith("/commit") and method == "POST":
            bid = path.split("/")[3]
            b = json_object(read_json, env)
            return "200 OK", self.commit_import(bid, allow_skip_invalid=bool(b.get("allow_skip_invalid", True)))
        if path == "/api/kalodata/capabilities" and method == "GET":
            return "200 OK", self.get_capabilities()
        if path == "/api/kalodata/imports" and method == "POST":
            return "200 OK", self.import_assisted_capture(json_object(read_json, env, max_bytes=MAX_IMPORT_BYTES))
        if path == "/api/kalodata/captures" and method == "GET":
            return "200 OK", {"items": self.list_captures(limit=25)}
        if path == "/api/kalodata/captures/current-page" and method == "POST":
            return "200 OK", self.run_browser_capture(json_object(read_json, env), bounded=False)
        if path == "/api/kalodata/captures/bounded-pages" and method == "POST":
            return "200 OK", self.run_browser_capture(json_object(read_json, env), bounded=True)
        if path.startswith("/api/kalodata/captures/"):
            parts = [p for p in path.split("/") if p]
            if len(parts) == 4 and method == "GET":
                return "200 OK", self.get_capture(parts[3])
            if len(parts) == 5 and parts[4] == "preview" and method == "POST":
                b = json_object(read_json, env)
                return "200 OK", self.update_capture_exclusions(parts[3], b.get("exclude_row_indices") or [])
            if len(parts) == 5 and parts[4] == "commit" and method == "POST":
                return "200 OK", self.commit_capture(parts[3])
            if len(parts) == 5 and parts[4] == "download" and method == "GET":
                qs = parse_qs(env.get("QUERY_STRING") or "")
                fmt = (qs.get("format") or ["zip"])[0]
                return self.export_capture_bundle(parts[3], fmt=fmt)
        return None
