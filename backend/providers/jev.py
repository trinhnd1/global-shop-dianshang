"""TypeSafe AI (Jev 1.14.0) client tailored for E-Commerce Product Selling, Keyword Research, China Sourcing & Video Evaluation."""
import json
import math
import time
import urllib.error
import urllib.request

DEFAULT_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-1.14.0"

INDUSTRY_CHOICES = {
    "gia_dung": "Gia dụng & Tiện ích nhà cửa",
    "nha_cua": "Trang trí Nhà cửa & Đời sống",
    "lam_dep": "Làm đẹp & Chăm sóc cá nhân",
    "suc_khoe": "Sức khoẻ & Thiết bị massage",
    "thoi_trang": "Thời trang, Giày dép & Phụ kiện",
    "cong_nghe": "Phụ kiện Điện thoại & Công nghệ",
    "me_be": "Mẹ & Bé, Đồ chơi giáo dục",
    "lam_vuon": "Làm vườn, Cây cảnh & Hạt giống",
    "thu_cung": "Phụ kiện & Thức ăn Thú cưng",
    "do_an": "Đồ ăn vặt & Đặc sản đóng gói",
    "the_thao": "Thể thao, Dã ngoại & Du lịch",
    "oto_xemay": "Phụ kiện Ô tô & Xe máy",
    "khac": "Ngành hàng khác",
}


class JevError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


class JevClient:
    def __init__(self, http_opener=None):
        self._opener = http_opener or urllib.request.urlopen

    def ask_atomic(
        self,
        api_key: str,
        state,
        questions: dict,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_ENDPOINT,
        assets: dict | None = None,
        timeout: int = 38,
    ) -> dict:
        key = (api_key or "").strip()
        if not key:
            raise JevError("Chưa cấu hình TypeSafe Jev API Key", status=400)
        endpoint = (base_url or DEFAULT_ENDPOINT).strip()

        wire_questions = {}
        for qid, qspec in (questions or {}).items():
            clean_q = {k: v for k, v in qspec.items() if k != "question"}
            if "question" in qspec and "instructions" not in clean_q:
                clean_q["instructions"] = qspec["question"]
            wire_questions[qid] = clean_q

        has_assets = bool(assets)
        attempts = 3 if has_assets else 2
        last_err: Exception | None = None

        for attempt in range(attempts):
            cur_assets = assets
            cur_state = dict(state) if isinstance(state, dict) else state
            if has_assets and attempt == 1 and isinstance(assets, dict) and len(assets) > 2:
                keys = list(assets.keys())
                cur_assets = {keys[0]: assets[keys[0]], keys[-1]: assets[keys[-1]]}
            elif has_assets and attempt == 2:
                cur_assets = None
                if isinstance(cur_state, dict):
                    cur_state["review_mode"] = "transcript_and_caption_fallback"

            payload: dict = {"model": model or DEFAULT_MODEL, "state": cur_state, "questions": wire_questions}
            if cur_assets:
                payload["assets"] = cur_assets

            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Connection": "close",
                "User-Agent": "GlobalShopDianshang/1.0",
            }
            if cur_assets:
                headers["TypeSafe-Danger-Zone-Images"] = "true"

            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            try:
                eff_timeout = max(timeout, 70) if cur_assets else timeout
                with self._opener(req, timeout=eff_timeout) as resp:
                    raw = json.loads(resp.read().decode("utf-8"))
                    answers = self._validate_answers(raw, wire_questions)
                    return {
                        "answers": answers,
                        "model": raw.get("model") or model or DEFAULT_MODEL,
                        "degraded_image_transport": bool(has_assets and cur_assets is None),
                        "_cost_usd": 0.0012 if cur_assets else 0.0006,
                    }
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")[:220]
                last_err = JevError(f"Jev HTTP {exc.code}: {body}", status=exc.code)
                if exc.code in (413, 502, 503, 504) and attempt + 1 < attempts:
                    time.sleep(0.6)
                    continue
                raise last_err from None
            except JevError:
                raise
            except Exception as exc:
                last_err = JevError(f"Lỗi kết nối Jev: {exc}")
                if attempt + 1 < attempts:
                    time.sleep(0.6)
                    continue
                raise last_err from None
        raise last_err or JevError("Không gọi được Jev AI")

    @staticmethod
    def _validate_answers(raw: dict, wire_questions: dict) -> dict:
        ans_map = raw.get("answers") if isinstance(raw, dict) else None
        if not isinstance(ans_map, dict):
            raise JevError("Phản hồi Jev thiếu trường answers")
        validated = {}
        for qid, qspec in wire_questions.items():
            qtype = qspec["type"]
            entry = ans_map.get(qid)
            if not isinstance(entry, dict):
                raise JevError(f"Jev trả thiếu câu trả lời cho {qid}")
            if qtype == "score":
                val = entry.get("score")
                if val is None or isinstance(val, bool):
                    raise JevError(f"Jev thiếu score cho {qid}")
                max_idx = max(1, len(qspec.get("criteria") or [0, 1, 2, 3]) - 1)
                num = float(val)
                if not math.isfinite(num) or num < -1e-9 or num > max_idx + 1e-9:
                    raise JevError(f"Điểm Jev {qid} nằm ngoài biên: {val}")
                validated[qid] = round(1.0 + (max(0.0, min(float(max_idx), num)) / max_idx) * 9.0, 2)
            elif qtype == "noul":
                val = entry.get("noul")
                if val is None or isinstance(val, bool):
                    raise JevError(f"Jev thiếu noul cho {qid}")
                num = float(val)
                if not math.isfinite(num) or num < -1e-9 or num > 1.0 + 1e-9:
                    raise JevError(f"Xác suất Jev {qid} nằm ngoài [0..1]: {val}")
                validated[qid] = round(max(0.0, min(1.0, num)), 4)
            elif qtype == "choice":
                sval = entry.get("choice")
                if not isinstance(sval, str) or sval not in (qspec.get("criteria") or {}):
                    raise JevError(f"Lựa chọn Jev {qid} không hợp lệ: {sval}")
                validated[qid] = sval
        return validated

    def test_connection(self, api_key: str, model: str = DEFAULT_MODEL, base_url: str = DEFAULT_ENDPOINT) -> dict:
        res = self.ask_atomic(
            api_key,
            state="Đánh giá sản phẩm bán lẻ tại Việt Nam: Máy xay tỏi ớt mini không dây Inox 304 giá 129.000đ trên Shopee, 3.800 lượt bán.",
            questions={
                "ready": {
                    "type": "noul",
                    "instructions": "Sản phẩm này có tiềm năng tốt để nhà bán nhập sỉ về kinh doanh trên Shopee và TikTok Shop Việt Nam không?",
                }
            },
            model=model,
            base_url=base_url,
            timeout=22,
        )
        return {"ok": True, "model": res["model"], "probe_answer": res["answers"]["ready"]}

    def score_seller_product(self, api_key: str, product: dict, model: str = DEFAULT_MODEL, base_url: str = DEFAULT_ENDPOINT) -> dict:
        """6-pillar Seller Evaluation (buying/importing to sell on Shopee/TikTok Shop, NOT affiliate)."""
        scale_4 = [
            "Yếu / rủi ro cao",
            "Trung bình / cần cân nhắc",
            "Khá tốt / có lợi thế rõ",
            "Xuất sắc / cơ hội vàng để nhập bán",
        ]
        questions = {
            "suc_cau": {"type": "score", "instructions": "Sức mua thực tế và tốc độ tiêu thụ của sản phẩm này trên Shopee / TikTok Shop?", "criteria": scale_4},
            "bien_lai": {"type": "score", "instructions": "Khả năng đạt biên lợi nhuận ròng >=20% khi nhập sỉ từ 1688/Pinduoduo/xưởng về bán lẻ?", "criteria": scale_4},
            "de_nhap_tq": {"type": "score", "instructions": "Độ thuận lợi khi nhập hàng & vận chuyển (gọn nhẹ, ít vỡ hỏng, ít rủi ro pháp lý/bảo hành)?", "criteria": scale_4},
            "canh_tranh": {"type": "score", "instructions": "Dư địa cạnh tranh cho shop mới (chưa bị độc quyền bởi thương hiệu lớn/Mall phá giá)?", "criteria": scale_4},
            "khac_biet": {"type": "score", "instructions": "Khả năng làm combo, tặng kèm, nâng cấp bao bì hoặc định vị giá cao hơn đối thủ?", "criteria": scale_4},
            "de_lam_video": {"type": "score", "instructions": "Độ dễ quay video demo công dụng trực quan để chốt đơn tự nhiên và chạy Ads?", "criteria": scale_4},
            "nganh_hang": {"type": "choice", "instructions": "Sản phẩm này thuộc ngành hàng chính nào?", "criteria": INDUSTRY_CHOICES},
            "dang_nhap_ban": {"type": "noul", "instructions": "Xác suất nhà bán nên nhập test lô nhỏ để bán thương mại ngay trong 14 ngày tới?"},
        }
        state = {
            "goal": "Evaluate product potential for an e-commerce merchant importing inventory to sell on Shopee & TikTok Shop",
            "title": product.get("title") or "",
            "platform": product.get("platform") or "",
            "price_vnd": product.get("price_vnd") or 0,
            "landed_cost_vnd": product.get("cost_vnd") or 0,
            "sold_count": product.get("sold_count") or 0,
            "sold_30d": product.get("sold_30d") or 0,
            "gmv_vnd": product.get("gmv_vnd") or 0,
            "rating": product.get("rating") or 0,
            "is_mall": bool(product.get("is_mall")),
            "shop_name": product.get("shop_name") or "",
        }
        res = self.ask_atomic(api_key, state, questions, model=model, base_url=base_url)
        a = res["answers"]
        overall = round(
            a["suc_cau"] * 0.24
            + a["bien_lai"] * 0.20
            + a["de_nhap_tq"] * 0.16
            + a["canh_tranh"] * 0.15
            + a["khac_biet"] * 0.13
            + a["de_lam_video"] * 0.12,
            2,
        )
        return {
            "overall_10": overall,
            "pillars": {
                "suc_cau": a["suc_cau"],
                "bien_lai": a["bien_lai"],
                "de_nhap_tq": a["de_nhap_tq"],
                "canh_tranh": a["canh_tranh"],
                "khac_biet": a["khac_biet"],
                "de_lam_video": a["de_lam_video"],
            },
            "industry": a["nganh_hang"],
            "import_test_prob": a["dang_nhap_ban"],
            "jev_model": res["model"],
            "_cost_usd": res["_cost_usd"],
        }

    def score_keyword_opportunity(self, api_key: str, kw_summary: dict, model: str = DEFAULT_MODEL, base_url: str = DEFAULT_ENDPOINT) -> dict:
        scale_4 = ["Kém", "Trung bình", "Tốt", "Rất tiềm năng"]
        questions = {
            "intent": {"type": "score", "instructions": "Ý định mua hàng trực tiếp của người tìm từ khoá này cao đến mức nào?", "criteria": scale_4},
            "gap": {"type": "score", "instructions": "Cơ hội lọt trang 1 cho shop mới (dựa trên tổng lượng sản phẩm, tỷ lệ Mall và phân bổ lượt bán)?", "criteria": scale_4},
            "margin": {"type": "score", "instructions": "Mặt bằng giá bán hiện tại của từ khoá có đủ biên lợi nhuận nhập hàng bán lẻ không?", "criteria": scale_4},
            "worth_entering": {"type": "noul", "instructions": "Xác suất nên chọn từ khoá ngách này để tìm nguồn hàng 1688/Pinduoduo nhập về bán?"},
        }
        res = self.ask_atomic(api_key, kw_summary, questions, model=model, base_url=base_url)
        a = res["answers"]
        score_10 = round(a["intent"] * 0.40 + a["gap"] * 0.35 + a["margin"] * 0.25, 2)
        return {
            "opportunity_score_10": score_10,
            "pillars": {"intent": a["intent"], "gap": a["gap"], "margin": a["margin"]},
            "worth_entering_prob": a["worth_entering"],
            "jev_model": res["model"],
            "_cost_usd": res["_cost_usd"],
        }

    def evaluate_video(
        self,
        api_key: str,
        video_meta: dict,
        frames_b64: dict | None = None,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_ENDPOINT,
    ) -> dict:
        scale_4 = ["Yếu", "Đạt mức cơ bản", "Tốt", "Rất sắc bén"]
        questions = {
            "hook_3s": {"type": "score", "instructions": "Sức hút 3 giây đầu (nỗi đau / kết quả thị giác giữ chân người mua)?", "criteria": scale_4},
            "demo_sp": {"type": "score", "instructions": "Mức độ chứng minh công dụng thực tế & chất lượng sản phẩm trên khung hình?", "criteria": scale_4},
            "nhip_dieu": {"type": "score", "instructions": "Nhịp dựng và bố cục thuyết phục người xem đặt mua?", "criteria": scale_4},
            "cta_chot_don": {"type": "score", "instructions": "Độ rõ ràng của ưu đãi / lời kêu gọi mua hàng cho Shop?", "criteria": scale_4},
            "dang_nhan_ban": {"type": "noul", "instructions": "Xác suất Shop nên nhân bản (clone) cấu trúc kịch bản video này để bán hàng?"},
        }
        res = self.ask_atomic(api_key, video_meta, questions, model=model, base_url=base_url, assets=frames_b64)
        a = res["answers"]
        overall = round(a["hook_3s"] * 0.30 + a["demo_sp"] * 0.30 + a["nhip_dieu"] * 0.20 + a["cta_chot_don"] * 0.20, 2)
        return {
            "overall_10": overall,
            "pillars": {
                "hook_3s": a["hook_3s"],
                "demo_sp": a["demo_sp"],
                "nhip_dieu": a["nhip_dieu"],
                "cta_chot_don": a["cta_chot_don"],
            },
            "clone_worth_prob": a["dang_nhan_ban"],
            "degraded_image_transport": res["degraded_image_transport"],
            "jev_model": res["model"],
            "_cost_usd": res["_cost_usd"],
        }
