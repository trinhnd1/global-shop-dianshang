"""`300+desk` Seller Product Processing & `Jev` Decision Orchestrator (modeled after `affiliate-peng` workflows).

Strict Division of Labor:
1. Data Collection: Apify (#1 Priority) -> Treg.to (#2 Automatic Failover)
2. Product Processing, Deduplication, SEO Title, CN 1688 Keyword, Combo & Video Angles: `300+desk` (Fail-Closed `127.0.0.1:18765` -> OPi SOCKS5 `100.113.217.101:1080`)
3. Final Decision Making (`strong_pick` / `maybe` / `pass`): TypeSafe Jev AI (`jev-1.14.0`).
"""
from __future__ import annotations

import csv
from pathlib import Path
import json
import re
import uuid

from . import settings
from .china_sourcing import translate_vn_to_cn_keyword
from .providers.desk300plus import Desk300PlusClient, Desk300PlusFailClosedError
from .responses import ApiError, json_object, now, safe_csv_cell, text

SLUG_RE = re.compile(r"[^a-z0-9._-]+")

PIPELINE_STEPS_SPEC = (
    (1, "collect_apify_first", "1. Thu thập & Làm giàu SP (Ưu tiên #1 Apify -> #2 Treg)"),
    (2, "verify_opi_socks5", "2. Kiểm định Fail-Closed 300+desk & SOCKS5 OrangePi5 Pro"),
    (3, "desk300_process_products", "3. 300+desk Xử lý SP (Lọc trùng · Tên SEO · Từ khoá 1688 · Combo & Góc Video)"),
    (4, "jev_final_decision", "4. TypeSafe Jev AI Ra Quyết định (strong_pick · maybe · pass)"),
    (5, "vault_sync_and_export", "5. Xuất gói CSV NNN & Cập nhật Kho SP + Khớp Shop của tôi"),
)


def _write_csv(path: Path, headers: list[str], rows: list[list]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, lineterminator="\r\n")
        w.writerow(headers)
        for r in rows:
            w.writerow([safe_csv_cell(c) if isinstance(c, str) else c for c in r])


def classify_jev_decision_tier(jev_score: float | None, import_prob: float | None) -> str:
    if jev_score is None:
        return "maybe"
    sc = float(jev_score)
    pr = float(import_prob if import_prob is not None else 0.5)
    if sc >= 7.5 or (sc >= 7.0 and pr >= 0.62):
        return "strong_pick"
    if sc >= 5.8 or pr >= 0.45:
        return "maybe"
    return "pass"


DECISION_LABELS = {
    "strong_pick": "🔥 STRONG PICK (Nên nhập Test)",
    "maybe": "🟡 MAYBE (Soi thêm xưởng 1688)",
    "pass": "⚪ PASS (Theo dõi thêm)",
}


class DeskProductWorkflowService:
    def __init__(
        self,
        connect,
        secrets,
        data_dir: Path,
        products,
        shops=None,
        jobs=None,
        apify=None,
        treg=None,
        jev=None,
        desk300: Desk300PlusClient | None = None,
    ):
        self.connect = connect
        self.secrets = secrets
        self.root = Path(data_dir)
        self.exports_root = self.root / "exports" / "300-desk"
        self.exports_root.mkdir(parents=True, exist_ok=True)
        self.products = products
        self.shops = shops
        self.jobs = jobs
        self.apify = apify
        self.treg = treg
        self.jev = jev
        self.desk300 = desk300 or Desk300PlusClient()

    def _next_nnn(self) -> tuple[int, str]:
        with self.connect() as conn:
            conn.execute("UPDATE desk300_sequence SET last_nnn = last_nnn + 1 WHERE id = 1")
            num = int(conn.execute("SELECT last_nnn FROM desk300_sequence WHERE id = 1").fetchone()[0])
        return num, f"{num:03d}"

    def gateway_status_safe(self, probe_egress: bool = False) -> dict:
        try:
            return self.desk300.check_gateway_status(probe_egress_ip=probe_egress)
        except Desk300PlusFailClosedError as exc:
            return {
                "ok": False,
                "fail_closed": True,
                "gateway_url": self.desk300.gateway_url,
                "error": str(exc),
                "status_code": exc.status,
            }

    def process_single_or_batch_sync(
        self,
        product_ids: list[int] | None = None,
        mode: str = "vault_process",
        keywords: list[str] | None = None,
        channels: list[str] | None = None,
        exec_engine: str = "gateway_fast",
        auto_assign_my_shop: bool = True,
        limit: int = 12,
        log_fn=None,
    ) -> dict:
        """Run the full 5-step `Apify (#1) -> Treg (#2) -> 300+desk (OPi SOCKS5) -> Jev Decision` workflow."""
        nnn_no, nnn_code = self._next_nnn()
        run_id = f"d300_{nnn_code}_{uuid.uuid4().hex[:6]}"
        slug_hint = SLUG_RE.sub("-", ((keywords[0] if keywords else mode) or "batch").lower()).strip("-")[:32] or "batch"
        run_dir = self.exports_root / f"{nnn_code}-{slug_hint}"
        run_dir.mkdir(parents=True, exist_ok=True)

        steps_state = [
            {"step": num, "key": key, "label": lbl, "status": "pending", "detail": ""}
            for num, key, lbl in PIPELINE_STEPS_SPEC
        ]

        def _save_run_state(status_str: str, in_ids: list[int], out_ids: list[int], results_arr: list[dict], err_txt: str = "", egress_ok: bool = False):
            sp_cnt = sum(1 for x in results_arr if x.get("decision_tier") == "strong_pick")
            mb_cnt = sum(1 for x in results_arr if x.get("decision_tier") == "maybe")
            ps_cnt = sum(1 for x in results_arr if x.get("decision_tier") == "pass")
            ts_now = now()
            with self.connect() as conn:
                ex = conn.execute("SELECT run_id FROM desk300_runs WHERE run_id=?", (run_id,)).fetchone()
                if ex:
                    conn.execute(
                        """
                        UPDATE desk300_runs
                        SET status=?, input_product_ids_json=?, output_product_ids_json=?,
                            strong_pick_count=?, maybe_count=?, pass_count=?, egress_verified=?,
                            steps_json=?, results_json=?, error_text=?, updated_at=?
                        WHERE run_id=?
                        """,
                        (
                            status_str,
                            json.dumps(in_ids),
                            json.dumps(out_ids),
                            sp_cnt,
                            mb_cnt,
                            ps_cnt,
                            1 if egress_ok else 0,
                            json.dumps(steps_state, ensure_ascii=False),
                            json.dumps(results_arr, ensure_ascii=False),
                            err_txt[:800],
                            ts_now,
                            run_id,
                        ),
                    )
                else:
                    title_str = (
                        f"Luồng {nnn_code} · Săn & Xử lý 300+desk: {', '.join((keywords or [])[:2])}"
                        if mode == "hunt_and_process" and keywords
                        else f"Luồng {nnn_code} · Xử lý {len(in_ids) or limit} SP trong Kho qua 300+desk -> Jev"
                    )
                    conn.execute(
                        """
                        INSERT INTO desk300_runs
                        (run_id, nnn_no, nnn_code, title, mode, exec_engine, status,
                         input_product_ids_json, output_product_ids_json, strong_pick_count, maybe_count, pass_count,
                         export_dir, egress_verified, steps_json, results_json, error_text, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, '[]', 0, 0, 0, ?, 0, ?, '[]', '', ?, ?)
                        """,
                        (
                            run_id,
                            nnn_no,
                            nnn_code,
                            title_str[:180],
                            mode,
                            exec_engine,
                            status_str,
                            json.dumps(in_ids),
                            str(run_dir.name),
                            json.dumps(steps_state, ensure_ascii=False),
                            ts_now,
                            ts_now,
                        ),
                    )

        def _mark_step(step_num: int, st: str, detail: str = ""):
            for s in steps_state:
                if s["step"] == step_num:
                    s["status"] = st
                    if detail:
                        s["detail"] = detail
            if log_fn and detail:
                log_fn(f"[Bước {step_num}/5] {detail}")

        input_pids: list[int] = [int(x) for x in (product_ids or []) if str(x).isdigit()]
        _save_run_state("running", input_pids, [], [])

        cfg = settings.read_settings(self.connect, self.secrets)
        apify_toks = settings.apify_tokens(cfg)
        treg_tok = (cfg["providers"].get("treg_key") or "").strip()
        jev_key = (cfg["providers"].get("typesafe_key") or "").strip()

        try:
            # --- STEP 1: COLLECT & ENRICH VIA APIFY (#1 PRIORITY) -> TREG (#2 BACKUP) ---
            _mark_step(1, "running", "Đang thu thập & làm giàu số liệu gốc (Ưu tiên #1 Apify -> #2 Treg dự phòng)...")
            if mode == "hunt_and_process" and keywords:
                mkt_chs = [c for c in (channels or ["shopee", "tiktok_shop"]) if c in ("shopee", "tiktok_shop", "lazada")]
                for kw in keywords[:4]:
                    for ch in mkt_chs:
                        rows_found: list[dict] = []
                        src_tag = ""
                        # STRICT PRIORITY #1: APIFY
                        if apify_toks and self.apify:
                            try:
                                if ch == "shopee":
                                    slug, rows_found = self.apify.search_shopee(apify_toks, kw, limit=max(3, min(12, limit)))
                                elif ch == "tiktok_shop":
                                    slug, rows_found = self.apify.search_tiktok_shop(apify_toks, kw, limit=max(3, min(12, limit)))
                                else:
                                    slug, rows_found = self.apify.search_lazada(apify_toks, kw, limit=max(3, min(12, limit)))
                                src_tag = f"apify:{slug}"
                            except Exception:
                                rows_found = []
                        # STRICT PRIORITY #2: TREG BACKUP ONLY IF APIFY EMPTY
                        if not rows_found and treg_tok and self.treg and ch == "tiktok_shop":
                            try:
                                ep, rows_found, _ = self.treg.search_tiktok_shop(treg_tok, kw, limit=max(3, min(12, limit)))
                                src_tag = f"treg_backup:{ep}"
                            except Exception:
                                rows_found = []
                        for r in rows_found:
                            if r.get("title"):
                                saved = self.products.upsert_product(r, source=f"desk300_hunt:{src_tag}:{kw}")
                                if saved["id"] not in input_pids:
                                    input_pids.append(saved["id"])

            if not input_pids:
                with self.connect() as conn:
                    rows = conn.execute(
                        "SELECT id FROM products WHERE bucket != 'da_loai' ORDER BY CASE WHEN bucket='cho_danh_gia' THEN 0 ELSE 1 END, id DESC LIMIT ?",
                        (max(1, min(30, int(limit))),),
                    ).fetchall()
                input_pids = [int(r["id"]) for r in rows]

            if not input_pids:
                raise ApiError("400 Bad Request", "Chưa có sản phẩm nào để xử lý — hãy chạy Săn SP hoặc nhập từ khoá!")

            # Enrich products missing price/sold_count (strictly Apify #1 -> Treg #2 inside enrich_product)
            candidates = self.products.get_products_by_ids(input_pids[:20])
            enriched_cnt = 0
            for idx_c, cp in enumerate(candidates):
                if float(cp.get("price_vnd") or 0) <= 0 and int(cp.get("sold_count") or 0) <= 0:
                    try:
                        after_p = self.products.enrich_product(cp["id"])
                        if after_p:
                            candidates[idx_c] = after_p
                            if after_p.get("price_vnd", 0) > 0 or after_p.get("sold_count", 0) > 0:
                                enriched_cnt += 1
                    except Exception:
                        pass
            _mark_step(1, "completed", f"Chuẩn bị xong {len(candidates)} SP (đã làm giàu giá/lượt bán {enriched_cnt} SP qua Apify #1 -> Treg #2).")
            _save_run_state("running", input_pids, [], [])

            # --- STEP 2: FAIL-CLOSED 300+DESK & ORANGEPI5 PRO SOCKS5 PRECHECK ---
            _mark_step(2, "running", "Đang kiểm tra Gateway 300+desk (127.0.0.1:18765) & khóa cứng SOCKS5 OrangePi5 Pro...")
            gw_info = self.desk300.check_gateway_status(probe_egress_ip=False)
            _mark_step(2, "completed", f"300+desk SẴN SÀNG ({gw_info['service']} -> {gw_info['socks_proxy']} Fail-Closed).")
            _save_run_state("running", input_pids, [], [], egress_ok=True)

            # --- STEP 3: 300+DESK PRODUCT MERGE, FILTER, SEO, CN 1688 KEYWORD & VIDEO ANGLES ---
            _mark_step(3, "running", f"300+desk đang chuẩn hoá {len(candidates)} sản phẩm qua SOCKS5 OrangePi5 Pro ({exec_engine})...")
            desk_input = [
                {
                    "id": p["id"],
                    "platform": p["platform"],
                    "native_product_id": p["native_product_id"],
                    "raw_title": p["title"],
                    "price_vnd": p["price_vnd"],
                    "sold_count": p["sold_count"],
                    "industry": p["industry"],
                    "note": p.get("note") or "",
                }
                for p in candidates
            ]
            sys_prompt = (
                "Bạn là bộ xử lý sản phẩm `300+desk` trong hệ thống thương mại điện tử Global Shop Dianshang (nhập hàng bán trên Shopee, TikTok Shop & Facebook Fanpage). "
                "KHÔNG gọi bất kỳ công cụ (bash/read/write) nào — trả lời trực tiếp DUY NHẤT 1 JSON object hợp lệ. "
                "TUYỆT ĐỐI KHÔNG tự bịa hay sửa đổi các con số `price_vnd` và `sold_count`."
            )
            usr_prompt = (
                "Hãy xử lý, lọc trùng, đặt lại tên chuẩn SEO bán lẻ tại Việt Nam, tạo từ khoá tiếng Trung (中文) chuẩn xác để tìm xưởng gốc trên 1688/Pinduoduo, "
                "đề xuất phương án làm Combo/Quà tặng tăng biên lãi và 3 góc quay Video 15s chốt đơn cho từng sản phẩm sau:\n"
                + json.dumps({"products": desk_input}, ensure_ascii=False)
                + "\n\nTrả về DUY NHẤT JSON theo đúng cấu trúc:\n"
                '{"items": [{"id": <số id>, "keep": true, "duplicate_of_id": null, '
                '"seo_title": "<Tên SP chuẩn SEO Shopee/TikTok dễ hiểu, 45-95 ký tự>", '
                '"cn_1688_keyword": "<Từ khoá tiếng Trung ngắn gọn đúng tên hàng trên 1688>", '
                '"combo_strategy": "<1 câu gợi ý đóng combo / quà tặng kèm để bán giá cao>", '
                '"video_angles": ["<Góc 1: Hook 3s giải quyết nỗi đau>", "<Góc 2: Test độ bền/công năng thực tế>", "<Góc 3: So sánh Before/After & chốt ưu đãi>"]}]}'
            )

            if exec_engine == "dsh_harness":
                dsh_res = self.desk300.run_dsh_json(run_dir, f"{sys_prompt}\n\n{usr_prompt}", use_pro=False, timeout_sec=115)
            else:
                dsh_res = self.desk300.call_gateway_json(sys_prompt, usr_prompt, workdir=run_dir, task_type="seller_product_desk", timeout_sec=70)

            parsed_obj = dsh_res["parsed"]
            raw_desk_items = parsed_obj.get("items") if isinstance(parsed_obj, dict) else (parsed_obj if isinstance(parsed_obj, list) else [])
            desk_by_id: dict[int, dict] = {}
            for ditem in raw_desk_items or []:
                if isinstance(ditem, dict) and str(ditem.get("id", "")).isdigit():
                    desk_by_id[int(ditem["id"])] = ditem

            kept_products: list[tuple[dict, dict]] = []
            for p in candidates:
                d_info = desk_by_id.get(p["id"]) or {}
                if d_info.get("keep") is False or d_info.get("duplicate_of_id"):
                    continue
                seo_t = str(d_info.get("seo_title") or p["title"]).strip()[:140]
                cn_kw = str(d_info.get("cn_1688_keyword") or translate_vn_to_cn_keyword(p["title"])).strip()[:80]
                combo_s = str(d_info.get("combo_strategy") or "Đóng gói hộp cứng + tặng phụ kiện nhỏ tăng giá trị đơn").strip()[:220]
                angles = [str(a).strip()[:180] for a in (d_info.get("video_angles") or []) if str(a).strip()][:5]
                if not angles:
                    angles = [
                        f"Hook 3s: Xoáy trực diện bất tiện hàng ngày & giải quyết gọn bằng {seo_t[:45]}",
                        "Cận cảnh chất liệu & test thực tế công năng liên tục 5 giây",
                        "Chốt đơn theo Combo tiết kiệm của Shop kèm bảo hành đổi mới",
                    ]
                kept_products.append((
                    p,
                    {
                        "nnn_code": nnn_code,
                        "seo_title": seo_t,
                        "cn_1688_keyword": cn_kw,
                        "combo_strategy": combo_s,
                        "video_angles": angles,
                        "engine_used": dsh_res["engine_used"],
                        "processed_at": now(),
                    },
                ))

            _mark_step(3, "completed", f"300+desk giữ lại & chuẩn hoá {len(kept_products)}/{len(candidates)} SP (0 con số tự bịa).")
            _save_run_state("running", input_pids, [p["id"] for p, _ in kept_products], [], egress_ok=True)

            # --- STEP 4: JEV 1.14.0 FINAL CALIBRATED DECISION MAKING ---
            _mark_step(4, "running", f"TypeSafe Jev AI đang chấm 6 trụ cột Seller & ra quyết định cho {len(kept_products)} SP...")
            final_results: list[dict] = []
            for p, desk_meta in kept_products:
                scored_p = p
                if jev_key and self.jev:
                    try:
                        scored_p = self.products.score_product_jev(p["id"])
                    except Exception:
                        scored_p = self.products.get_product(p["id"]) or p
                j_score = scored_p.get("jev_score")
                j_det = scored_p.get("jev_detail") or {}
                imp_prob = j_det.get("import_test_prob")
                tier = classify_jev_decision_tier(j_score, imp_prob)
                desk_meta["decision_tier"] = tier
                desk_meta["decision_label"] = DECISION_LABELS[tier]

                # Persist `desk300` processing + Jev decision tier into `products.record`
                with self.connect() as conn:
                    r_db = conn.execute("SELECT record FROM products WHERE id=?", (p["id"],)).fetchone()
                    if r_db:
                        rec_obj = json.loads(r_db["record"] or "{}")
                        rec_obj["desk300"] = desk_meta
                        conn.execute(
                            "UPDATE products SET record=?, updated_at=? WHERE id=?",
                            (json.dumps(rec_obj, ensure_ascii=False), now(), p["id"]),
                        )

                refreshed = self.products.get_product(p["id"]) or scored_p
                final_results.append({
                    "id": refreshed["id"],
                    "platform": refreshed["platform"],
                    "native_product_id": refreshed["native_product_id"],
                    "raw_title": refreshed["title"],
                    "seo_title": desk_meta["seo_title"],
                    "cn_1688_keyword": desk_meta["cn_1688_keyword"],
                    "combo_strategy": desk_meta["combo_strategy"],
                    "video_angles": desk_meta["video_angles"],
                    "price_vnd": refreshed["price_vnd"],
                    "sold_count": refreshed["sold_count"],
                    "gmv_vnd": refreshed["gmv_vnd"],
                    "jev_score": refreshed["jev_score"],
                    "import_test_prob": imp_prob,
                    "decision_tier": tier,
                    "decision_label": DECISION_LABELS[tier],
                    "industry_label": refreshed["industry_label"],
                    "url": refreshed["url"],
                    "image_url": refreshed["image_url"],
                })

            # Strict tiered ordering just like `affiliate-peng`: strong_pick -> maybe -> pass, then by Jev score desc
            tier_rank = {"strong_pick": 3, "maybe": 2, "pass": 1}
            final_results.sort(key=lambda x: (tier_rank.get(x["decision_tier"], 0), float(x.get("jev_score") or 0.0)), reverse=True)
            _mark_step(
                4,
                "completed",
                f"Jev AI chốt quyết định: {sum(1 for x in final_results if x['decision_tier']=='strong_pick')} strong_pick · "
                f"{sum(1 for x in final_results if x['decision_tier']=='maybe')} maybe · "
                f"{sum(1 for x in final_results if x['decision_tier']=='pass')} pass.",
            )

            # --- STEP 5: WRITE NNN CSV BUNDLE & AUTO-MATCH MY SHOPS ---
            _mark_step(5, "running", f"Đang ghi gói CSV vào exports/300-desk/{run_dir.name}/ & khớp Shop của tôi...")
            _write_csv(
                run_dir / "products.csv",
                ["id", "platform", "native_product_id", "raw_title", "seo_title", "price_vnd", "sold_count", "gmv_vnd", "cn_1688_keyword", "combo_strategy", "url"],
                [
                    [
                        r["id"], r["platform"], r["native_product_id"], r["raw_title"], r["seo_title"],
                        r["price_vnd"], r["sold_count"], r["gmv_vnd"], r["cn_1688_keyword"], r["combo_strategy"], r["url"],
                    ]
                    for r in final_results
                ],
            )
            _write_csv(
                run_dir / "jev_decisions.csv",
                ["id", "decision_tier", "jev_score", "import_test_prob", "seo_title", "cn_1688_keyword", "video_angle_1", "video_angle_2", "video_angle_3"],
                [
                    [
                        r["id"], r["decision_tier"], r["jev_score"], r["import_test_prob"],
                        r["seo_title"], r["cn_1688_keyword"],
                        (r["video_angles"] + ["", "", ""])[0],
                        (r["video_angles"] + ["", "", ""])[1],
                        (r["video_angles"] + ["", "", ""])[2],
                    ]
                    for r in final_results
                ],
            )

            if auto_assign_my_shop and self.shops is not None:
                pick_ids = [r["id"] for r in final_results if r["decision_tier"] in ("strong_pick", "maybe")]
                if pick_ids:
                    try:
                        self.shops.auto_assign_shop_for_products(product_ids=pick_ids)
                    except Exception:
                        pass

            out_ids = [r["id"] for r in final_results]
            _mark_step(5, "completed", f"Hoàn tất gói 300+desk #{nnn_code} ({run_dir.name}) — đã đồng bộ về Kho SP!")
            _save_run_state("completed", input_pids, out_ids, final_results, egress_ok=True)
            return self.get_run(run_id)

        except Desk300PlusFailClosedError as exc:
            for s in steps_state:
                if s["status"] == "running":
                    s["status"] = "failed"
                    s["detail"] = str(exc)
            _save_run_state("failed", input_pids, [], [], err_txt=str(exc), egress_ok=False)
            raise ApiError("503 Service Unavailable", str(exc)) from None
        except ApiError as exc:
            _save_run_state("failed", input_pids, [], [], err_txt=exc.message, egress_ok=False)
            raise
        except Exception as exc:
            _save_run_state("failed", input_pids, [], [], err_txt=str(exc), egress_ok=False)
            raise ApiError("500 Internal Server Error", f"Lỗi luồng 300+desk: {exc}") from None

    def get_run(self, run_id: str) -> dict:
        with self.connect() as conn:
            r = conn.execute("SELECT * FROM desk300_runs WHERE run_id=? OR nnn_code=?", (run_id, run_id)).fetchone()
        if not r:
            raise ApiError("404 Not Found", "Không tìm thấy phiên xử lý 300+desk này")
        return self._format_run(r, include_results=True)

    def list_runs(self, limit: int = 25) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM desk300_runs ORDER BY nnn_no DESC LIMIT ?", (limit,)).fetchall()
        return [self._format_run(r, include_results=True) for r in rows]

    @staticmethod
    def _format_run(r, include_results: bool = True) -> dict:
        out = {
            "run_id": r["run_id"],
            "nnn_no": r["nnn_no"],
            "nnn_code": r["nnn_code"],
            "title": r["title"],
            "mode": r["mode"],
            "exec_engine": r["exec_engine"],
            "status": r["status"],
            "input_product_ids": json.loads(r["input_product_ids_json"] or "[]"),
            "output_product_ids": json.loads(r["output_product_ids_json"] or "[]"),
            "strong_pick_count": r["strong_pick_count"],
            "maybe_count": r["maybe_count"],
            "pass_count": r["pass_count"],
            "export_dir": r["export_dir"],
            "egress_verified": bool(r["egress_verified"]),
            "steps": json.loads(r["steps_json"] or "[]"),
            "error_text": r["error_text"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        if include_results:
            out["results"] = json.loads(r["results_json"] or "[]")
        out["summary"] = (
            f"Luồng 300+desk #{r['nnn_code']}: {r['strong_pick_count']} strong_pick · "
            f"{r['maybe_count']} maybe · {r['pass_count']} pass ({r['export_dir']})"
        )
        return out

    def dispatch(self, path: str, method: str, env, read_json):
        if path == "/api/desk300/status" and method == "GET":
            return "200 OK", self.gateway_status_safe(probe_egress=False)
        if path == "/api/desk300/check" and method == "POST":
            st = self.gateway_status_safe(probe_egress=True)
            if not st.get("ok"):
                return "503 Service Unavailable", {"detail": st.get("error") or "300+desk offline", **st}
            return "200 OK", {**st, "summary": f"300+desk READY ({st.get('service')} -> {st.get('socks_proxy')})"}
        if path == "/api/desk300/runs" and method == "GET":
            return "200 OK", {"runs": self.list_runs(25), "gateway": self.gateway_status_safe(probe_egress=False)}
        if path == "/api/desk300/run" and method == "POST":
            body = json_object(read_json, env)
            pids = [int(x) for x in (body.get("product_ids") or []) if str(x).isdigit()]
            kws = body.get("keywords") if isinstance(body.get("keywords"), list) else []
            if not kws and body.get("keyword"):
                kws = [s.strip() for s in re.split(r"[,;\n]+", str(body["keyword"])) if s.strip()]
            mode = str(body.get("mode") or ("hunt_and_process" if kws else "vault_process")).strip()
            engine = str(body.get("exec_engine") or "gateway_fast").strip()
            run_out = self.process_single_or_batch_sync(
                product_ids=pids or None,
                mode=mode,
                keywords=kws or None,
                channels=body.get("channels") if isinstance(body.get("channels"), list) else None,
                exec_engine=engine,
                auto_assign_my_shop=bool(body.get("auto_assign_my_shop", True)),
                limit=int(body.get("limit") or 12),
            )
            return "200 OK", {"run": run_out, "product_ids": run_out["output_product_ids"], "summary": run_out["summary"]}
        if path.startswith("/api/desk300/runs/") and method == "GET":
            rid = path.strip("/").split("/")[3]
            return "200 OK", {"run": self.get_run(rid)}
        return None
