"""Comprehensive Unit & Live HTTP E2E tests for Global Shop Dianshang v1.0.1."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from wsgiref.simple_server import make_server

from backend import __version__, settings
from backend.china_sourcing import translate_vn_to_cn_keyword
from backend.secret_store import create_secret_store
from backend.seller_economics import calculate_china_landed_cost, evaluate_seller_economics
from backend.server import Application, LocalHTTPServer, LocalRequestHandler
from backend.webapp import DEFAULT_STATIC, WebApp


class FakeTelegramHttp:
    def __init__(self):
        self.sent_messages = []

    def __call__(self, token: str, method: str, payload: dict | None = None, timeout: int = 10) -> dict:
        if method == "getMe":
            return {"ok": True, "result": {"id": 9212861764, "username": "tc_global1_shop_bot", "first_name": "Global Shop Bot"}}
        if method == "sendMessage":
            self.sent_messages.append(dict(payload or {}))
            return {"ok": True, "result": {"message_id": len(self.sent_messages)}}
        if method == "getUpdates":
            return {"ok": True, "result": []}
        return {"ok": True, "result": {}}


class FakeJev:
    def test_connection(self, api_key: str, model: str = "", base_url: str = "") -> dict:
        return {"ok": True, "model": model or "jev-1.14.0", "probe_answer": 0.96}

    def score_seller_product(self, api_key: str, product: dict, model: str = "", base_url: str = "") -> dict:
        return {
            "overall_10": 8.15,
            "pillars": {"suc_cau": 8.5, "bien_lai": 8.2, "de_nhap_tq": 8.0, "canh_tranh": 7.8, "khac_biet": 8.0, "de_lam_video": 8.2},
            "industry": "gia_dung",
            "import_test_prob": 0.88,
            "jev_model": "jev-1.14.0",
            "_cost_usd": 0.0006,
        }

    def score_keyword_opportunity(self, api_key: str, kw_summary: dict, model: str = "", base_url: str = "") -> dict:
        return {
            "opportunity_score_10": 7.9,
            "pillars": {"intent": 8.4, "gap": 7.5, "margin": 7.8},
            "worth_entering_prob": 0.84,
            "jev_model": "jev-1.14.0",
            "_cost_usd": 0.0006,
        }

    def evaluate_video(self, api_key: str, video_meta: dict, frames_b64=None, model: str = "", base_url: str = "") -> dict:
        return {
            "overall_10": 8.3,
            "pillars": {"hook_3s": 8.5, "demo_sp": 8.4, "nhip_dieu": 8.0, "cta_chot_don": 8.2},
            "clone_worth_prob": 0.91,
            "degraded_image_transport": False,
            "jev_model": "jev-1.14.0",
            "_cost_usd": 0.0006,
        }

    def score_google_trend_keyword(self, api_key: str, kw_item: dict, model: str = "", base_url: str = "") -> dict:
        return {
            "jev_score_10": 8.4,
            "buyer_intent": 8.6,
            "trend_durability": 8.1,
            "industry": "gia_dung",
            "worth_hunting_prob": 0.9,
            "jev_model": "jev-1.14.0",
            "_cost_usd": 0.0006,
        }

    def evaluate_social_painpoint(self, api_key: str, pain_context: dict, model: str = "", base_url: str = "") -> dict:
        return {
            "overall_pain_score_10": 8.75,
            "pillars": {"pain_severity": 9.0, "product_solvability": 8.8, "viral_hook_potential": 8.3},
            "industry": "gia_dung",
            "solution_archetype": "ve_sinh_khu_mui_diet_khuan",
            "solution_archetype_label": "Chế phẩm / Dụng cụ vệ sinh, khử mùi, chống ẩm mốc",
            "worth_sourcing_prob": 0.92,
            "jev_model": "jev-1.14.0",
            "_cost_usd": 0.0006,
        }


class GlobalShopDianshangE2ETest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fake_tg = FakeTelegramHttp()
        secrets = create_secret_store(self.tmp.name, prefer_keychain=False)
        self.api = Application(
            self.tmp.name,
            allow_tailscale=True,
            secret_store=secrets,
            prefer_keychain=False,
            telegram_http_runner=self.fake_tg,
            web_port=8999,
        )
        fake_jev = FakeJev()
        self.api.jev = fake_jev
        self.api.products.jev = fake_jev
        self.api.keywords.jev = fake_jev
        self.api.spy_video.jev = fake_jev
        self.api.hunt.jev = fake_jev
        self.api.china_sourcing.jev = fake_jev
        self.api.ecosystems.jev = fake_jev
        class FakeDesk300:
            def check_gateway_status(self, probe_egress_ip=False):
                return {"ok": False, "fail_closed": True, "gateway_url": "http://127.0.0.1:18765"}

            def generate_json(self, *args, **kwargs):
                return {"queries": [{"cn_query": "阅星瞳 X4 磁吸保护套", "vn_label": "Bao da từ tính Xteink X4"}]}, {}

        fake_desk = FakeDesk300()
        self.api.desk300 = fake_desk
        self.api.china_sourcing.desk300 = fake_desk
        self.api.ecosystems.desk300 = fake_desk
        self.api.hunt.desk300 = fake_desk

        self.webapp = WebApp(self.api, DEFAULT_STATIC)
        self.httpd = make_server("127.0.0.1", 0, self.webapp, server_class=LocalHTTPServer, handler_class=LocalRequestHandler)
        self.port = self.httpd.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def req(self, method: str, path: str, body: dict | None = None, headers: dict | None = None) -> tuple[int, dict]:
        raw = json.dumps(body).encode("utf-8") if body is not None else None
        hdrs = dict(headers or {})
        if raw is not None:
            hdrs["Content-Type"] = "application/json"
        r = urllib.request.Request(self.base_url + path, data=raw, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read().decode("utf-8"))
            finally:
                exc.close()

    def test_01_security_version_masking_and_tailscale_guards(self):
        st, health = self.req("GET", "/api/health")
        self.assertEqual(st, 200)
        self.assertEqual(health["version"], "1.0.8")
        self.assertEqual(__version__, "1.0.8")
        self.assertEqual(health["schema_version"], 6)

        # Tailscale MagicDNS & CGNAT allowed
        st_ts, _ = self.req("GET", "/api/health", headers={"Host": "nguyens-mac-mini.tail213fd3.ts.net:8999"})
        self.assertEqual(st_ts, 200)

        # Untrusted external Host blocked (DNS rebinding guard)
        st_bad, _ = self.req("GET", "/api/health", headers={"Host": "evil.attacker.org"})
        self.assertEqual(st_bad, 403)

        # Cross-origin POST blocked (CSRF guard)
        st_csrf, _ = self.req("POST", "/api/pins", {"title": "x"}, headers={"Origin": "https://evil.attacker.org"})
        self.assertEqual(st_csrf, 403)

        # Secret masking & Keychain/Vault isolation
        st_save, saved = self.req("POST", "/api/settings", {
            "providers": {
                "treg_key": "卡号：treg_secret_token_9999",
                "typesafe_key": "apikey_jev_secret_8888",
            },
            "notify": {
                "telegram_token": "1234567890:AAFakeSampleTokenForUnitTestOnly12345",
                "telegram_chat_id": "5608975895",
                "telegram_allowed_user_ids": "5608975895",
            },
        })
        self.assertEqual(st_save, 200)
        self.assertEqual(saved["settings"]["providers"]["treg_key"], "••••••••9999")
        self.assertNotIn("treg_secret_token_9999", json.dumps(saved))

        # Telegram strict allowlist: unauthorized user ID rejected
        self.api.telegram_bot._handle_update(
            {"update_id": 1, "message": {"text": "/status", "chat": {"id": 9999999}, "from": {"id": 9999999}}},
            settings.read_settings(self.api.connect, self.api.secrets)["notify"],
            "1234567890:AAFakeSampleTokenForUnitTestOnly12345",
        )
        self.assertEqual(self.api.telegram_bot._rejected_count, 1)

        # Authorized user 5608975895 succeeds
        self.api.telegram_bot._handle_update(
            {"update_id": 2, "message": {"text": "/status", "chat": {"id": 5608975895}, "from": {"id": 5608975895}}},
            settings.read_settings(self.api.connect, self.api.secrets)["notify"],
            "1234567890:AAFakeSampleTokenForUnitTestOnly12345",
        )
        self.assertTrue(any("Global Shop Dianshang" in m.get("text", "") for m in self.fake_tg.sent_messages))

    def test_02_keyword_watch_diff_new_products_and_rising_sales(self):
        # Create a Shopee keyword watch
        st, created = self.req("POST", "/api/watches", {
            "watch_type": "keyword",
            "platform": "shopee",
            "target_key": "máy xay tỏi ớt",
            "title": "Từ khoá: máy xay tỏi ớt",
        })
        self.assertEqual(st, 200)
        wid = created["watch"]["watch_id"]

        # Check #1 (Baseline): 2 products, total 1,200 products on keyword
        run1 = self.api.watches.run_watch_check(
            wid,
            injected_items=[
                {"platform": "shopee", "native_product_id": "1729000000000000001", "title": "Máy xay tỏi ớt mini 250ml", "price_vnd": 89000, "sold_count": 420, "url": "https://shopee.vn/product/11/1729000000000000001"},
                {"platform": "shopee", "native_product_id": "1729000000000000002", "title": "Máy xay đa năng Inox 304", "price_vnd": 159000, "sold_count": 180, "url": "https://shopee.vn/product/11/1729000000000000002"},
            ],
            injected_total_count=1200,
        )
        self.assertTrue(run1["diff"]["is_initial_baseline"])
        self.assertEqual(run1["diff"]["new_items_count"], 0)

        # Check #2: 1 brand-new product appears + Product #2 jumps from 180 -> 265 sold + total count grows to 1,245!
        run2 = self.api.watches.run_watch_check(
            wid,
            injected_items=[
                {"platform": "shopee", "native_product_id": "1729000000000000001", "title": "Máy xay tỏi ớt mini 250ml", "price_vnd": 85000, "sold_count": 420, "url": "https://shopee.vn/product/11/1729000000000000001"},
                {"platform": "shopee", "native_product_id": "1729000000000000002", "title": "Máy xay đa năng Inox 304", "price_vnd": 159000, "sold_count": 265, "url": "https://shopee.vn/product/11/1729000000000000002"},
                {"platform": "shopee", "native_product_id": "1729000000000000099", "title": "Máy xay tỏi ớt sạc Type-C mẫu mới 2026", "price_vnd": 129000, "sold_count": 35, "url": "https://shopee.vn/product/22/1729000000000000099"},
            ],
            injected_total_count=1245,
        )
        diff2 = run2["diff"]
        self.assertFalse(diff2["is_initial_baseline"])
        self.assertEqual(diff2["total_count"], 1245)
        self.assertEqual(diff2["total_count_delta"], 45)
        self.assertEqual(diff2["new_items_count"], 1)
        self.assertEqual(diff2["new_items"][0]["native_product_id"], "1729000000000000099")
        self.assertEqual(diff2["rising_items_count"], 1)
        self.assertEqual(diff2["rising_items"][0]["delta_sold"], 85)
        self.assertEqual(diff2["price_changed_count"], 1)

        # New product was automatically staged into Product Vault with 19-digit ID intact!
        st_v, vault = self.req("GET", "/api/products?q=1729000000000000099")
        self.assertEqual(st_v, 200)
        self.assertEqual(len(vault["products"]), 1)
        self.assertEqual(vault["products"][0]["native_product_id"], "1729000000000000099")

    def test_03_china_sourcing_landed_cost_shops_campaigns_sales_and_mcp(self):
        # VN -> CN commerce translation helper
        self.assertEqual(translate_vn_to_cn_keyword("máy xay tỏi ớt mini"), "迷你电动捣蒜器")

        # Decimal China Landed Cost & Seller Margin math
        lc = calculate_china_landed_cost(price_cny=12.0, cny_rate=3650, domestic_cn_ship_cny=2.0, weight_kg=0.4, cn_vn_ship_per_kg_vnd=28000, buying_agent_fee_pct=2.5)
        self.assertGreater(lc["landed_cost_vnd"], 60000)
        econ = evaluate_seller_economics({"platform": "shopee", "sell_price_vnd": 169000, "cost_vnd": lc["landed_cost_vnd"]})
        self.assertGreater(econ["net_profit_per_order_vnd"], 50000)
        self.assertEqual(econ["verdict"], "loi_nhuan_tot_nen_nhap")

        # Save manual 1688 sourcing quote & link to a new Vault Product
        _, src_saved = self.req("POST", "/api/sourcing/manual", {
            "platform": "1688",
            "native_item_id": "889911223344",
            "title": "新款厨房置物架免打孔",
            "title_vi": "Kệ nhà tắm dán tường chịu lực",
            "price_cny": 9.5,
            "moq": 20,
            "weight_kg": 0.5,
            "supplier_name": "Yiwu Home Factory",
        })
        sid = src_saved["item"]["sourcing_id"]
        _, linked = self.req("POST", f"/api/sourcing/{sid}/link", {"create_new_in_vault": True, "target_sell_price_vnd": 149000})
        pid = linked["product"]["id"]
        self.assertEqual(linked["product"]["bucket"], "da_co_nguon_tq")

        # Score Seller Product with Jev AI
        self.req("POST", "/api/settings", {"providers": {"typesafe_key": "apikey_test_jev_123456"}})
        st_j, scored = self.req("POST", f"/api/products/{pid}/score-jev", {})
        self.assertEqual(st_j, 200)
        self.assertEqual(scored["product"]["jev_score"], 8.15)

        # Category Campaign + 5-Stage Funnel + Seller CSV Order Attribution
        _, cmp_res = self.req("POST", "/api/campaigns", {
            "name": "Chiến dịch Gia dụng Nhà tắm Q4",
            "industry": "gia_dung",
            "target_revenue_vnd": 80000000,
        })
        cid = cmp_res["campaign"]["campaign_id"]

        # Shop của tôi: Shopee + TikTok Shop + Facebook Fanpage + Edit + Auto-match SP
        _, sh_res = self.req("POST", "/api/my-shops", {
            "platform": "shopee",
            "shop_name": "Peng Home Shopee",
            "shop_url": "https://shopee.vn/penghome",
            "industry": "gia_dung",
            "niche_tags": "kệ nhà tắm, gia dụng nhà bếp",
            "campaign_ids": [cid],
        })
        self.assertEqual(sh_res["shop"]["role"], "own_shop")
        self.assertEqual(sh_res["shop"]["platform"], "shopee")
        self.assertEqual(sh_res["shop"]["campaign_ids"], [cid])

        _, tt_res = self.req("POST", "/api/my-shops", {
            "shop_name": "Peng TikTok Shop",
            "shop_url": "https://www.tiktok.com/@peng_tiktok_shop",
            "industry": "cong_nghe",
            "niche_tags": ["đồng hồ thông minh", "tai nghe"],
        })
        self.assertEqual(tt_res["shop"]["platform"], "tiktok_shop")
        self.assertEqual(tt_res["shop"]["handle"], "peng_tiktok_shop")

        _, fb_res = self.req("POST", "/api/my-shops", {
            "shop_name": "Fanpage Gia Dụng Thông Minh Peng",
            "shop_url": "https://www.facebook.com/fanpage.giadung.peng",
            "industry": "gia_dung",
            "status": "warming",
            "note": "Chuyên chạy Ads chuyển đổi",
        })
        self.assertEqual(fb_res["shop"]["platform"], "facebook_fanpage")
        self.assertEqual(fb_res["shop"]["platform_fee_pct"], 0.0)
        fb_sid = fb_res["shop"]["shop_id"]

        _, fb_upd = self.req("PATCH", f"/api/my-shops/{fb_sid}", {"status": "active", "niche_tags": "đèn decor, kệ dán tường"})
        self.assertEqual(fb_upd["shop"]["status"], "active")
        self.assertIn("đèn decor", fb_upd["shop"]["niche_tags"])

        _, my_list = self.req("GET", "/api/my-shops")
        self.assertEqual(my_list["counts"]["own_count"], 3)
        self.assertEqual(my_list["counts"]["own_by_platform"]["facebook_fanpage"], 1)

        _, auto_m = self.req("POST", "/api/shops/auto-match-products", {"ids": [pid]})
        self.assertEqual(auto_m["matched_count"], 1)

        _, stg_res = self.req("POST", f"/api/campaigns/{cid}/product-stage", {"product_id": pid, "stage": "nhap_test"})
        self.assertEqual(len(stg_res["campaign"]["products"]), 1)

        csv_payload = (
            "order_id,product_name,quantity,gross_revenue,cogs_vnd,status\n"
            "SP1001,Kệ nhà tắm dán tường,2,298000,105000,completed\n"
            "SP1002,Kệ nhà tắm dán tường,1,149000,52500,cancelled\n"
        )
        _, imp_res = self.req("POST", "/api/sales/import-csv", {"platform": "shopee", "campaign_id": cid, "csv_text": csv_payload})
        self.assertEqual(imp_res["imported_orders"], 1)
        self.assertEqual(imp_res["skipped_cancelled"], 1)

        _, sales = self.req("GET", "/api/sales/summary")
        self.assertEqual(sales["seller_kpis"]["valid_orders"], 1)
        self.assertEqual(sales["seller_kpis"]["units_sold"], 2)
        self.assertGreater(sales["seller_kpis"]["net_profit_vnd"], 100000)

        # Video Cloner <=15s
        _, clone_res = self.req("POST", "/api/video-cloner/clone", {
            "product_name": "Kệ nhà tắm dán tường",
            "target_product_id": pid,
            "clone_mode": "product_swap",
        })
        self.assertEqual(clone_res["clone"]["segments"][0]["image_prompt_json"]["engine"], "Nano Banana 2.1")
        self.assertEqual(clone_res["clone"]["segments"][0]["video_prompt_json"]["engine"], "Gemini Omni 1.2 Flash")

        # Activity History Logs GS-0001+ & Full Job Detail Hydration
        def _sample_job(ctx):
            ctx.log("Bước 1: Đã quét 2 sản phẩm thử nghiệm")
            return {"discovered_count": 1, "product_ids": [pid], "summary": "Hoàn tất job mẫu"}

        j_started = self.api.jobs.start_job("hunt", "Job Săn Mẫu Kiểm Thử", _sample_job, estimated_cost_usd=0.01, budget_limit_usd=0.2)
        import time
        for _ in range(20):
            j_cur = self.api.jobs.get_job(j_started["id"])
            if j_cur and j_cur["status"] == "completed":
                break
            time.sleep(0.05)

        st_jd, job_hist = self.req("GET", f"/api/history-logs/job_{j_started['id']}")
        self.assertEqual(st_jd, 200)
        self.assertTrue(any("Bước 1" in line for line in job_hist["step_logs"]))
        self.assertEqual(len(job_hist["resolved_results"]["products"]), 1)
        self.assertEqual(job_hist["resolved_results"]["products"][0]["id"], pid)

        # Verify low Jev score NEVER hides newly fetched products into da_loai automatically
        class LowScoreJev(FakeJev):
            def score_seller_product(self, api_key: str, product: dict, model: str = "", base_url: str = "") -> dict:
                res = super().score_seller_product(api_key, product, model, base_url)
                res["overall_10"] = 3.6
                return res

        self.api.products.jev = LowScoreJev()
        _, p_low = self.req("POST", "/api/products", {"title": "Đồng hồ thông minh test hiển thị", "platform": "tiktok_shop", "price_vnd": 0, "sold_count": 0})
        low_id = p_low["product"]["id"]
        _, p_low_scored = self.req("POST", f"/api/products/{low_id}/score-jev", {})
        self.assertEqual(p_low_scored["product"]["bucket"], "cho_danh_gia")
        _, all_kho = self.req("GET", "/api/products?bucket=all")
        self.assertTrue(any(x["id"] == low_id for x in all_kho["products"]))

        # Explicit user rejection moves to da_loai
        _, p_rej = self.req("PATCH", f"/api/products/{low_id}", {"status": "bo_qua"})
        self.assertEqual(p_rej["bucket"], "da_loai")

        _, hist = self.req("GET", "/api/history-logs")
        self.assertTrue(len(hist["logs"]) >= 5)
        self.assertTrue(hist["logs"][0]["gs_code"].startswith("GS-"))

        # MCP Streamable HTTP Gateway (/mcp)
        mcp_tok = self.api.secrets.get("mcp.auth_token")
        st_unauth, _ = self.req("POST", "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertEqual(st_unauth, 401)
        st_mcp, mcp_res = self.req(
            "POST",
            "/mcp",
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "gs_system_overview", "arguments": {}}},
            headers={"Authorization": f"Bearer {mcp_tok}"},
        )
        self.assertEqual(st_mcp, 200)
        overview_txt = mcp_res["result"]["content"][0]["text"]
        self.assertIn("Global Shop Dianshang", overview_txt)

    def test_04_google_trends_and_social_painpoint_to_product_discovery(self):
        self.req("POST", "/api/settings", {"providers": {"typesafe_key": "apikey_test_jev_painpoint"}})

        # 1) Google Trends multi-seed + Jev Buyer Intent scoring + history
        st_gt, gt = self.req("POST", "/api/hunt/google-trends", {
            "seed_terms": ["quạt cầm tay", "máy hút ẩm"],
            "time_range": "today 3-m",
            "score_jev": True,
        })
        self.assertEqual(st_gt, 200)
        self.assertGreaterEqual(len(gt["keywords"]), 2)
        self.assertEqual(gt["keywords"][0]["jev_score_10"], 8.4)

        _, gt_hist = self.req("GET", "/api/hunt/google-trends/history")
        self.assertEqual(len(gt_hist["runs"]), 1)

        # 2) Social Painpoint Discovery (Facebook, Threads, X, Reddit) -> Jev Diagnosis -> Solution Products in Kho
        pp_res = self.api.hunt.discover_painpoints(
            topic_query="nhà tắm ẩm mốc mùi hôi cống",
            channels=["facebook_organic", "threads", "x", "reddit"],
            auto_find_products=True,
            injected_posts=[
                {"channel": "facebook_organic", "author": "nhadep_group", "text": "Cứu em với nhà tắm mùa nồm mùi hôi cống bốc lên và tường bị nấm mốc đen, dùng phễu thoát sàn ngăn mùi loại nào tốt ạ?", "comments": 45, "likes": 120},
                {"channel": "threads", "author": "minh_anh", "text": "Ở chung cư hay bị mùi thoát sàn toilet cực kỳ khó chịu, xịt tẩy nấm mốc nhà tắm xong đỡ hẳn", "comments": 18, "likes": 64},
                {"channel": "reddit", "author": "r/CleaningTips", "text": "Bathroom drain smell and mold problem — silicone backflow drain trap fixed it", "comments": 32, "likes": 210},
                {"channel": "x", "author": "decor_vn", "text": "Đặt máy hút ẩm mini trong phòng tắm khô thoáng hẳn", "comments": 5, "likes": 29},
            ],
            injected_products=[
                {"platform": "shopee", "native_product_id": "25500000111", "title": "Phễu thoát sàn ngăn mùi hôi cống Inox 304 tự đóng mở", "price_vnd": 65000, "sold_count": 3200, "url": "https://shopee.vn/product/1/25500000111"},
                {"platform": "tiktok_shop", "native_product_id": "1730000000000000888", "title": "Bình xịt tẩy nấm mốc nhà tắm công nghệ Nhật 500ml", "price_vnd": 89000, "sold_count": 1450, "url": "https://shop.tiktok.com/view/product/1730000000000000888?region=VN"},
            ],
        )
        pp = pp_res["painpoint"]
        self.assertEqual(pp["jev_pain_score"], 8.75)
        self.assertIn("phễu thoát sàn ngăn mùi", pp["recommended_keywords"])
        self.assertEqual(len(pp["matched_products"]), 2)

        st_pp_list, pp_list = self.req("GET", "/api/hunt/painpoints")
        self.assertEqual(st_pp_list, 200)
        self.assertEqual(len(pp_list["painpoints"]), 1)
        self.assertEqual(len(pp_list["painpoints"][0]["evidence_posts"]), 4)

    def test_05_strict_apify_first_and_300desk_fail_closed_product_pipeline(self):
        from backend.providers.desk300plus import Desk300PlusClient, Desk300PlusFailClosedError

        # Non-loopback gateway URL is strictly rejected (Fail-Closed)
        with self.assertRaises(Desk300PlusFailClosedError):
            Desk300PlusClient(gateway_url="https://api.deepseek.com")

        # Verify strict Apify #1 BEFORE Treg #2 order on product enrichment
        call_order = []

        class OrderApify:
            def scrape_tiktok_shop_detail(self, tokens, url_or_id, max_charge_usd=0.05):
                call_order.append("apify")
                return {"price_vnd": 249000, "sold_count": 980, "title": "Máy massage cổ vai gáy 6 đầu xung điện"}

        class OrderTreg:
            def fetch_tiktok_shop_product_detail(self, token, pid, region="VN"):
                call_order.append("treg")
                return {"price_vnd": 249000, "sold_count": 980}

        self.req("POST", "/api/providers/apify/keys", {"label": "Primary", "token": "apify_api_fake_for_order_test_1234", "make_primary": True})
        self.req("POST", "/api/settings", {"providers": {"treg_key": "treg_fake_for_order_test_1234", "typesafe_key": "jev_fake_1234"}})
        self.api.products.apify = OrderApify()
        self.api.products.treg = OrderTreg()

        _, created_p = self.req("POST", "/api/products", {
            "platform": "tiktok_shop",
            "native_product_id": "1731112223334445556",
            "title": "Máy massage cổ vai gáy raw",
            "price_vnd": 0,
            "sold_count": 0,
        })
        pid = created_p["product"]["id"]
        _, enr_res = self.req("POST", f"/api/products/{pid}/enrich", {})
        self.assertEqual(call_order, ["apify"])  # Apify #1 succeeded -> Treg #2 was NOT called!
        self.assertEqual(enr_res["product"]["price_vnd"], 249000)

        # Configure healthy Fail-Closed 300+desk stub (OPi SOCKS5 verified)
        class HealthyDeskRunner:
            def check_gateway_status(self, probe_egress_ip=False):
                return {
                    "ok": True,
                    "fail_closed": True,
                    "gateway_url": "http://127.0.0.1:18765",
                    "service": "desk300plus-gateway",
                    "socks_proxy": "socks5h://100.113.217.101:1080",
                    "dsh_script_exists": True,
                }

            def __call__(self, workdir, prompt_text, mode="gateway", use_pro=False):
                payload = {
                    "items": [
                        {
                            "id": pid,
                            "keep": True,
                            "seo_title": "Máy Massage Cổ Vai Gáy 6 Đầu Chườm Ấm Hồng Ngoại Giảm Đau Mỏi Dân Văn Phòng",
                            "cn_1688_keyword": "颈椎按摩器热敷脉冲",
                            "combo_strategy": "Tặng kèm 2 miếng dán điện cực + túi vải đựng chống sốc",
                            "video_angles": ["Hook 3s: Dân văn phòng ngồi 8 tiếng cứng đờ cổ vai gáy", "Test chế độ chườm ấm 42 độ", "Chốt combo tặng kèm túi đựng"],
                        }
                    ]
                }
                meta = {
                    "verified": {"path_ok": True, "via_socks": True, "direct_mac_call": False, "fallback_used": False, "forbidden_hosts_in_artifacts": []}
                }
                return json.dumps(payload, ensure_ascii=False), meta

        healthy_client = Desk300PlusClient(custom_runner=HealthyDeskRunner())
        self.api.desk_pipeline.desk300 = healthy_client

        st_d, d_res = self.req("POST", "/api/desk300/run", {"mode": "vault_process", "product_ids": [pid]})
        self.assertEqual(st_d, 200)
        self.assertEqual(d_res["run"]["nnn_code"], "001")
        self.assertEqual(d_res["run"]["strong_pick_count"], 1)
        self.assertEqual(d_res["run"]["results"][0]["cn_1688_keyword"], "颈椎按摩器热敷脉冲")
        self.assertEqual(d_res["run"]["results"][0]["decision_tier"], "strong_pick")

        # Verify Kho SP product record received `desk300` metadata + CSV bundle written
        _, prod_dos = self.req("GET", f"/api/products/{pid}")
        self.assertEqual(prod_dos["product"]["desk300"]["cn_1688_keyword"], "颈椎按摩器热敷脉冲")
        exp_dir = Path(self.tmp.name) / "exports" / "300-desk" / d_res["run"]["export_dir"]
        self.assertTrue((exp_dir / "products.csv").is_file())
        self.assertTrue((exp_dir / "jev_decisions.csv").is_file())

        # Verify Fail-Closed 503 when OrangePi5 Pro SOCKS5 is down (0% Mac IP fallback!)
        class OfflineDeskRunner:
            def check_gateway_status(self, probe_egress_ip=False):
                raise Desk300PlusFailClosedError("FAIL-CLOSED: SOCKS5 OrangePi5 Pro offline", status=503)

        self.api.desk_pipeline.desk300 = Desk300PlusClient(custom_runner=OfflineDeskRunner())
        st_fail, fail_res = self.req("POST", "/api/desk300/run", {"mode": "vault_process", "product_ids": [pid]})
        self.assertEqual(st_fail, 503)
        self.assertIn("FAIL-CLOSED", fail_res["detail"])

    def test_06_shopee_keyword_filters_overseas_and_vault_badges(self):
        from backend.providers.apify import ApifyClient

        # 1) Verify filter normalization & Shopee VN URL builder
        nf = ApifyClient.normalize_shopee_filters({
            "shipped_from": "overseas",
            "sort_by": "sales",
            "min_price": 50000,
            "max_price": 350000,
            "min_rating": 4.5,
            "preferred_seller_only": True,
            "with_video_only": True,
        })
        self.assertEqual(nf["shipped_from"], "Nước ngoài")
        self.assertEqual(nf["sort_by"], "sales")
        self.assertTrue(nf["preferred_seller_only"])
        self.assertTrue(nf["with_video_only"])

        search_url = ApifyClient.build_shopee_vn_search_url("kệ nhà tắm", nf)
        self.assertIn("locations=N%C6%B0%E1%BB%9Bc+ngo%C3%A0i", search_url)
        self.assertIn("sortBy=sales", search_url)
        self.assertIn("shopeeVerified=1", search_url)
        self.assertIn("withVideo=true", search_url)

        nf_dom = ApifyClient.normalize_shopee_filters({"shipped_from": "Trong nước"})
        dom_url = ApifyClient.build_shopee_vn_search_url("kệ nhà tắm", nf_dom)
        self.assertIn("locations=-1", dom_url)

        # 2) Verify `lergassy~shopee-scraper` camelCase item normalization (Overseas + Preferred + RatingCount)
        norm_it = ApifyClient.normalize_shopee_item({
            "itemId": "47408137087",
            "shopId": "1480793884",
            "shopName": "liao1990.vn",
            "location": "Nước ngoài",
            "name": "[Hàng Quốc Tế] Kệ nhà tắm hút chân không siêu chắc",
            "price": 156658,
            "rating": 4.9,
            "ratingCount": 120,
            "discountPercent": 42,
            "labels": ["Yêu thích"],
            "imageUrl": "https://down-vn.img.susercontent.com/file/cn-11134207-820l4-demo",
            "productUrl": "https://shopee.vn/product/1480793884/47408137087",
        })
        self.assertEqual(norm_it["native_product_id"], "47408137087")
        self.assertEqual(norm_it["native_shop_id"], "1480793884")
        self.assertEqual(norm_it["shop_location"], "Nước ngoài")
        self.assertTrue(norm_it["is_overseas"])
        self.assertTrue(norm_it["is_preferred"])
        self.assertEqual(norm_it["sold_count"], 360)  # conservative floor from 120 verified buyer ratings

        # 3) Verify live `POST /api/keywords/research` passes `shippedFrom="Nước ngoài"` to Apify & persists `is_overseas` in Kho SP
        captured_payloads = []

        def fake_opener(req, timeout=60):
            body_obj = json.loads(req.data.decode("utf-8"))
            captured_payloads.append((req.full_url, body_obj))

            class _Resp:
                def __enter__(self_r):
                    return self_r

                def __exit__(self_r, *args):
                    pass

                def read(self_r):
                    return json.dumps([
                        {
                            "itemId": "47408137087",
                            "shopId": "1480793884",
                            "shopName": "liao1990.vn",
                            "location": "Nước ngoài",
                            "name": "Kệ nhà tắm hút chân không Quốc tế",
                            "price": 156000,
                            "rating": 4.9,
                            "ratingCount": 80,
                            "labels": ["Yêu thích"],
                            "imageUrl": "https://down-vn.img.susercontent.com/file/cn-11134207-820l4-demo",
                            "productUrl": "https://shopee.vn/product/1480793884/47408137087",
                        }
                    ]).encode("utf-8")

            return _Resp()

        self.req("POST", "/api/providers/apify/keys", {"label": "TestKey", "token": "apify_api_test_overseas_key_1234"})
        self.api.keywords.apify = ApifyClient(http_opener=fake_opener)

        st_kw, kw_res = self.req("POST", "/api/keywords/research", {
            "keyword": "kệ nhà tắm",
            "platform": "shopee",
            "limit": 10,
            "score_jev": False,
            "save_top_to_vault": True,
            "shopee_filters": {
                "shipped_from": "Nước ngoài",
                "sort_by": "sales",
                "preferred_seller_only": True,
            },
        })
        self.assertEqual(st_kw, 200)
        self.assertEqual(len(captured_payloads), 1)
        self.assertIn("lergassy~shopee-scraper", captured_payloads[0][0])
        self.assertEqual(captured_payloads[0][1]["shippedFrom"], "Nước ngoài")
        self.assertEqual(captured_payloads[0][1]["sortBy"], "sales")
        self.assertTrue(captured_payloads[0][1]["preferredSellerOnly"])

        self.assertEqual(kw_res["summary_stats"]["overseas_count"], 1)
        self.assertEqual(kw_res["summary_stats"]["overseas_share_pct"], 100.0)
        self.assertEqual(len(kw_res["saved_product_ids"]), 1)

        saved_pid = kw_res["saved_product_ids"][0]
        _, vault_prod = self.req("GET", f"/api/products/{saved_pid}")
        self.assertTrue(vault_prod["product"]["is_overseas"])
        self.assertEqual(vault_prod["product"]["shop_location"], "Nước ngoài")
        self.assertTrue(vault_prod["product"]["is_preferred"])

    def test_07_multi_market_sea_shopee_tiktokshop_and_apify_store_catalog(self):
        from backend.apify_catalog import ApifyStoreCatalogService
        from backend.markets import parse_marketplace_spec
        from backend.providers.apify import ApifyClient

        # 1) Verify all 10 explicit SEA marketplaces (VN, PH, SG, MY, TH for Shopee & TikTokShop)
        for mkt, dom in (("VN", "shopee.vn"), ("PH", "shopee.ph"), ("SG", "shopee.sg"), ("MY", "shopee.com.my"), ("TH", "shopee.co.th")):
            plat, m_out, ch_code = parse_marketplace_spec(f"shopee_{mkt.lower()}")
            self.assertEqual((plat, m_out, ch_code), ("shopee", mkt, f"shopee_{mkt.lower()}"))
            nf = ApifyClient.normalize_shopee_filters({"shipped_from": "overseas"}, market=mkt)
            u = ApifyClient.build_shopee_search_url("organizer", nf, market=mkt)
            self.assertIn(f"https://{dom}/search?", u)

            t_plat, t_mkt, t_code = parse_marketplace_spec(f"tiktokshop_{mkt.lower()}")
            self.assertEqual((t_plat, t_mkt, t_code), ("tiktok_shop", mkt, f"tiktok_shop_{mkt.lower()}"))

        # 2) Verify Keyword Research on `shopee_ph` (PHP -> VND + Mainland China overseas) and `tiktok_shop_sg` (SGD -> VND + market="sg")
        captured_calls = []

        def fake_multi_opener(req, timeout=60):
            body_obj = json.loads(req.data.decode("utf-8")) if req.data else {}
            captured_calls.append((req.full_url, body_obj))

            class _Resp:
                def __enter__(self_r):
                    return self_r

                def __exit__(self_r, *args):
                    pass

                def read(self_r):
                    if "shopee-scraper" in req.full_url:
                        return json.dumps([
                            {
                                "itemId": "9988776655",
                                "shopId": "11223344",
                                "shopName": "manila_crossborder.ph",
                                "location": "Mainland China",
                                "name": "Portable Mini Fan Rechargeable PH",
                                "price": 299,
                                "rating": 4.8,
                                "soldCount": 520,
                                "productUrl": "https://shopee.ph/product/11223344/9988776655",
                            }
                        ]).encode("utf-8")
                    return json.dumps([
                        {
                            "productId": "1739998887776665554",
                            "shopName": "SG Smart Home",
                            "title": "Kitchen Sink Rack Organizer SG",
                            "price": 19.90,
                            "soldCount": 310,
                            "url": "https://shop.tiktok.com/view/product/1739998887776665554?region=SG",
                        }
                    ]).encode("utf-8")

            return _Resp()

        self.req("POST", "/api/providers/apify/keys", {"label": "MultiMktKey", "token": "apify_api_test_multimarket_key_5678"})
        fake_apify = ApifyClient(http_opener=fake_multi_opener)
        self.api.keywords.apify = fake_apify
        self.api.apify_catalog.apify = fake_apify

        st_ph, ph_res = self.req("POST", "/api/keywords/research", {
            "keyword": "mini fan",
            "platform": "shopee_ph",
            "limit": 8,
            "score_jev": False,
            "save_top_to_vault": True,
            "shopee_filters": {"shipped_from": "overseas", "sort_by": "sales"},
        })
        self.assertEqual(st_ph, 200)
        self.assertEqual(ph_res["market"], "PH")
        self.assertIn("Shopee PH", ph_res["channel_label"])
        self.assertEqual(captured_calls[0][1]["country"], "PH")
        self.assertEqual(captured_calls[0][1]["shippedFrom"], "Mainland China")
        self.assertEqual(ph_res["items"][0]["native_currency"], "PHP")
        self.assertEqual(ph_res["items"][0]["native_price"], 299.0)
        self.assertGreater(ph_res["items"][0]["price_vnd"], 100000.0)

        st_sg, sg_res = self.req("POST", "/api/keywords/research", {
            "keyword": "sink rack",
            "platform": "tiktok_shop_sg",
            "limit": 8,
            "score_jev": False,
            "save_top_to_vault": True,
        })
        self.assertEqual(st_sg, 200)
        self.assertEqual(sg_res["market"], "SG")
        self.assertIn("TikTokShop SG", sg_res["channel_label"])
        self.assertEqual(captured_calls[1][1]["market"], "sg")
        self.assertEqual(sg_res["items"][0]["native_currency"], "SGD")

        # Filter Kho SP explicitly by `shopee_ph` vs `tiktok_shop_sg`
        _, list_ph = self.req("GET", "/api/products?platform=shopee_ph")
        self.assertEqual(len(list_ph["products"]), 1)
        self.assertEqual(list_ph["products"][0]["market"], "PH")
        _, list_sg = self.req("GET", "/api/products?platform=tiktok_shop_sg")
        self.assertEqual(len(list_sg["products"]), 1)
        self.assertEqual(list_sg["products"][0]["market"], "SG")

        # 3) Verify Full Apify Store Catalog Sync, Goal Search, Schema Inspector & On-Demand Call
        def fake_store_opener(req, timeout=25):
            u = req.full_url

            class _StoreResp:
                def __enter__(self_r):
                    return self_r

                def __exit__(self_r, *args):
                    pass

                def read(self_r):
                    if "/v2/store?" in u and "offset=0" in u:
                        return json.dumps({
                            "data": {
                                "total": 2,
                                "items": [
                                    {
                                        "id": "act_shopee_1",
                                        "username": "lergassy",
                                        "name": "shopee-scraper",
                                        "title": "Shopee Scraper (Products, Search, Shops)",
                                        "description": "Scrape Shopee VN, PH, SG, MY, TH products and shops.",
                                        "categories": ["ECOMMERCE"],
                                        "currentPricingInfo": {"pricingModel": "PAY_PER_EVENT", "pricePerUnitUsd": 0.002},
                                        "stats": {"totalUsers": 2500, "totalUsers30Days": 1192, "publicActorRunStats30Days": {"SUCCEEDED": 950, "TOTAL": 1000}},
                                        "actorReviewRating": 4.9,
                                        "actorReviewCount": 32,
                                    },
                                    {
                                        "id": "act_tts_1",
                                        "username": "harshmaur",
                                        "name": "tiktok-shop-scraper",
                                        "title": "TikTok Shop Scraper (VN, PH, SG, MY, TH)",
                                        "description": "Extract TikTok Shop products across Southeast Asia.",
                                        "categories": ["ECOMMERCE"],
                                        "currentPricingInfo": {"pricingModel": "PRICE_PER_DATASET_ITEM", "pricePerUnitUsd": 0.003},
                                        "stats": {"totalUsers": 900, "totalUsers30Days": 340, "publicActorRunStats30Days": {"SUCCEEDED": 480, "TOTAL": 500}},
                                        "actorReviewRating": 4.7,
                                        "actorReviewCount": 14,
                                    },
                                ],
                            }
                        }).encode("utf-8")
                    if "/v2/store?" in u:
                        return json.dumps({"data": {"total": 2, "items": []}}).encode("utf-8")
                    if "/v2/acts/" in u:
                        return json.dumps({"data": {"title": "Shopee Scraper", "taggedBuilds": {"latest": {"buildId": "bld_123456789"}}}}).encode("utf-8")
                    if "/v2/actor-builds/" in u:
                        return json.dumps({
                            "data": {
                                "actorDefinition": {
                                    "input": {
                                        "properties": {
                                            "country": {"type": "string", "default": "VN", "enum": ["VN", "PH", "SG", "MY", "TH"]},
                                            "searchTerms": {"type": "array", "prefill": ["fan"]},
                                        }
                                    }
                                }
                            }
                        }).encode("utf-8")
                    return b"{}"

            return _StoreResp()

        old_catalog = self.api.apify_catalog
        cat_idx = self.api.handlers.index(old_catalog)
        self.api.apify_catalog = ApifyStoreCatalogService(
            self.api.connect,
            self.api.secrets,
            self.tmp.name,
            apify_client=fake_apify,
            products=self.api.products,
            jobs=self.api.jobs,
            http_opener=fake_store_opener,
        )
        self.api.handlers[cat_idx] = self.api.apify_catalog

        st_sync, sync_res = self.req("POST", "/api/apify-store/sync", {"max_pages": 2, "page_size": 100})
        self.assertEqual(st_sync, 200)
        self.assertEqual(sync_res["actors_saved"], 2)
        self.assertTrue((Path(self.tmp.name) / "apify_store_catalog.json").is_file())

        st_srch, srch_res = self.req("GET", "/api/apify-store/search?goal=shopee&pay_per_use_only=1")
        self.assertEqual(st_srch, 200)
        self.assertEqual(srch_res["total"], 1)
        self.assertEqual(srch_res["actors"][0]["slug"], "lergassy~shopee-scraper")

        st_sch, sch_res = self.req("GET", "/api/apify-store/actors/lergassy~shopee-scraper/schema")
        self.assertEqual(st_sch, 200)
        self.assertIn("country", sch_res["input_schema"]["properties"])

        # Call on-demand by `goal="shopee"` -> automatically selects `lergassy~shopee-scraper` and executes!
        st_call, call_res = self.req("POST", "/api/apify-store/call", {
            "goal": "shopee",
            "payload": {"mode": "search", "country": "PH", "searchTerms": ["fan"]},
            "save_products_to_vault": True,
        })
        self.assertEqual(st_call, 200)
        self.assertEqual(call_res["actor_slug"], "lergassy~shopee-scraper")
        self.assertEqual(call_res["items_count"], 1)

    def test_08_ecosystem_playbooks_xteink_goojodoq_inventory_watch_and_kalodata_bridge(self):
        settings.add_apify_key(self.api.connect, self.api.secrets, "Eco Test", "apify_api_test_eco_key_0001")
        self.req("POST", "/api/settings", {
            "providers": {
                "typesafe_key": "apikey_jev_eco_0001",
            },
            "kalodata": {
                "account_email": "jreed767@cnebw.eu.cc",
                "market": "VN",
                "currency": "VND",
                "default_window_days": 7,
            },
        })

        # 1) Test Inventory-Delta Sales Inference on Special Product Watch (`prev_stock=50 -> cur_stock=42 => inferred_sold=8`)
        _, created_sp = self.req("POST", "/api/products", {
            "platform": "shopee",
            "market": "VN",
            "native_product_id": "29998888777",
            "title": "Bao da từ tính máy đọc sách mini Xteink X4",
            "price_vnd": 135000,
            "sold_count": 20,
            "stock": 50,
            "shop_name": "Xteink Official Store VN",
            "native_shop_id": "99887766",
            "url": "https://shopee.vn/product/99887766/29998888777",
        })
        sp_id = created_sp["product"]["id"]

        class StockDropApify:
            def __init__(self):
                self.prod_calls = 0

            def scrape_shopee_product(self, tokens, url_or_id, max_charge_usd=0.05, market="VN"):
                self.prod_calls += 1
                return {
                    "platform": "shopee",
                    "native_product_id": "29998888777",
                    "title": "Bao da từ tính máy đọc sách mini Xteink X4",
                    "price_vnd": 135000,
                    "sold_count": 20,  # Shopee hides exact sold increment here, so stock drop reveals 8 real sales!
                    "stock": 50 if self.prod_calls == 1 else 42,
                    "url": "https://shopee.vn/product/99887766/29998888777",
                }

            def search_shopee(self, tokens, kw, limit=30, max_charge_usd=0.08, filters=None, market="VN"):
                if "goojodoq" in kw.lower():
                    items = [
                        {
                            "platform": "shopee",
                            "market": "VN",
                            "native_product_id": "555000111",
                            "native_shop_id": "770011",
                            "shop_name": "Goojodoq Flagship VN",
                            "title": "Ngòi bút cảm ứng thay thế Goojodoq GD13 Pro",
                            "price_vnd": 69000,
                            "sold_count": 1450,
                            "stock": 320,
                            "rating": 4.9,
                            "url": "https://shopee.vn/product/770011/555000111",
                        }
                    ]
                    if getattr(self, "day_two", False):
                        items.append({
                            "platform": "shopee",
                            "market": "VN",
                            "native_product_id": "555000999",
                            "native_shop_id": "770011",
                            "shop_name": "Goojodoq Flagship VN",
                            "title": "[MỚI] Bàn phím Magic Keyboard Goojodoq 2026 Siêu Nhẹ",
                            "price_vnd": 890000,
                            "sold_count": 35,
                            "stock": 88,
                            "rating": 5.0,
                            "url": "https://shopee.vn/product/770011/555000999",
                        })
                    return "lergassy~shopee-scraper", items
                return "lergassy~shopee-scraper", [
                    {
                        "platform": "shopee",
                        "market": "VN",
                        "native_product_id": "29998888777",
                        "native_shop_id": "99887766",
                        "shop_name": "Xteink Official Store VN",
                        "title": "Bao da từ tính máy đọc sách mini Xteink X4",
                        "price_vnd": 135000,
                        "sold_count": 28,
                        "stock": 42,
                        "rating": 4.9,
                        "url": "https://shopee.vn/product/99887766/29998888777",
                    }
                ]

            def search_tiktok_shop(self, tokens, kw, limit=30, max_charge_usd=0.06, market="VN"):
                if "goojodoq" in kw.lower():
                    return "harshmaur~tiktok-shop-scraper", [
                        {
                            "platform": "tiktok_shop",
                            "market": "VN",
                            "native_product_id": "172999000111222333",
                            "shop_name": "GOOJODOQ Việt Nam",
                            "shop_handle": "goojodoq_vn",
                            "title": "Quạt cầm tay sò lạnh Goojodoq GFS001 100 cấp độ",
                            "price_vnd": 359000,
                            "sold_count": 8200,
                            "sold_30d": 1250,
                            "stock": 180,
                            "rating": 4.8,
                            "url": "https://shop.tiktok.com/view/product/172999000111222333",
                        }
                    ]
                return "harshmaur~tiktok-shop-scraper", [
                    {
                        "platform": "tiktok_shop",
                        "market": "VN",
                        "native_product_id": "172888111222333444",
                        "shop_name": "Phụ Kiện E-Reader Mini",
                        "shop_handle": "ereader_mini_vn",
                        "title": "Miếng dán màn hình nhám Paperlike Xteink X4 chống chói",
                        "price_vnd": 49000,
                        "sold_count": 95,
                        "sold_30d": 40,
                        "stock": 65,
                        "rating": 4.9,
                        "url": "https://shop.tiktok.com/view/product/172888111222333444",
                    }
                ]

            def search_tiktok_videos(self, tokens, kw, limit=10):
                return "clockworks~tiktok-scraper", []

            def search_china_sourcing(self, tokens, platform, query, limit=20, max_charge_usd=0.06):
                return f"scrapesage~{platform}-scraper", [
                    {
                        "native_item_id": f"{platform}_xteink_case_01",
                        "title": f"阅星瞳 X4 磁吸保护套 超薄防摔皮套 ({query})",
                        "price_cny": 12.8,
                        "moq": 2,
                        "sold_count": 600,
                        "supplier_name": "深圳墨水屏配件源头厂",
                        "item_url": f"https://mobile.yangkeduo.com/goods.html?goods_id={platform}_01",
                    },
                    {
                        "native_item_id": f"{platform}_xteink_alt_02",
                        "title": "4.3寸迷你墨水屏电子书阅读器 便携口袋书",
                        "price_cny": 198.0,
                        "moq": 1,
                        "sold_count": 320,
                        "supplier_name": "广州数码专营店",
                        "item_url": f"https://item.taobao.com/item.htm?id={platform}_02",
                    },
                ]

        fake_eco_apify = StockDropApify()
        self.api.watches.apify = fake_eco_apify
        self.api.keywords.apify = fake_eco_apify
        self.api.china_sourcing.apify = fake_eco_apify
        self.api.products.apify = fake_eco_apify
        self.api.ecosystems.apify = fake_eco_apify

        st_w, w_created = self.req("POST", "/api/watches", {
            "watch_type": "product",
            "platform": "shopee_vn",
            "target_key": "https://shopee.vn/product/99887766/29998888777",
            "title": "⭐ [Phụ kiện Xteink X4] Bao da Xteink X4",
            "linked_product_id": sp_id,
            "is_special": True,
            "collection_id": "phu-kien-xteink-x4",
            "run_immediately": True,
        })
        self.assertEqual(st_w, 200)
        wid_sp = w_created["watch"]["watch_id"]
        self.assertTrue(w_created["watch"]["is_special"])

        # Second check sees stock drop 50 -> 42 => inferred 8 recent sales!
        st_w2, w_check2 = self.req("POST", f"/api/watches/{wid_sp}/check", {})
        self.assertEqual(st_w2, 200)
        self.assertEqual(w_check2["diff"]["prev_stock"], 50)
        self.assertEqual(w_check2["diff"]["stock"], 42)
        self.assertEqual(w_check2["diff"]["stock_drop_inferred_sold"], 8)
        self.assertEqual(w_check2["diff"]["delta_sold"], 8)

        # 2) Run Playbook #1: `Phụ kiện Xteink X4`
        st_x4, res_x4 = self.req("POST", "/api/ecosystems/run", {
            "name": "Phụ kiện Xteink X4",
            "seed_keyword": "xteink",
            "extra_keywords": ["xteink x4"],
            "channels": ["shopee_vn", "tiktok_shop_vn"],
            "cn_platforms": ["pinduoduo", "taobao"],
            "enable_cn_expansion": True,
            "enable_kalodata": False,
            "enable_global_selling_creators": False,
            "daily_schedule_enabled": True,
        })
        self.assertEqual(st_x4, 200)
        col_x4 = res_x4["collection"]
        self.assertEqual(col_x4["name"], "Phụ kiện Xteink X4")
        self.assertGreaterEqual(len(col_x4["products"]), 2)
        self.assertGreaterEqual(len(col_x4["tracked_shops"]), 2)
        self.assertGreaterEqual(len(col_x4["special_watches"]), 2)
        self.assertGreaterEqual(len(col_x4["cn_items"]), 2)
        cn_roles = {it["relation_role"] for it in col_x4["cn_items"]}
        self.assertIn("variant_addon", cn_roles)
        self.assertIn("alternative_product", cn_roles)

        # 3) Run Playbook #2: `Phụ kiện Goojodoq` with Kalodata + Affiliate Global Selling Creators + Daily Crawl Diff
        class FakeKalodataBridge:
            def search_kalodata_keyword(self, keyword, window_spec="7d", limit=15):
                return {
                    "ok": True,
                    "products": [
                        {
                            "native_product_id": "172999000111222333",
                            "title": "Quạt cầm tay sò lạnh Goojodoq GFS001",
                            "price_vnd": 359000,
                            "units_sold_recent": 1480,
                            "gmv_recent_vnd": 520_000_000,
                            "gmv_recent_display": "520.0 tr ₫",
                        }
                    ],
                    "videos": [
                        {
                            "source": "kalodata",
                            "video_id": "7491122334455667788",
                            "caption": "Test quạt sò lạnh Goojodoq đi nắng 40 độ mát lạnh tức thì",
                            "author_handle": "reviewcongnghe_vn",
                            "views_count": 450000,
                            "orders_count": 620,
                            "video_gmv_vnd": 218_000_000,
                            "video_gmv_display": "218.0 tr ₫",
                            "gpm_vnd": 484000,
                            "gpm_display": "484,000₫",
                            "video_url": "https://www.tiktok.com/@reviewcongnghe_vn/video/7491122334455667788",
                        }
                    ],
                    "creators": [
                        {
                            "handle": "reviewcongnghe_vn",
                            "source": "kalodata",
                            "winning_video_count": 2,
                            "total_gmv_vnd": 218_000_000,
                            "total_gmv_display": "218.0 tr ₫",
                            "total_orders": 620,
                            "profile_url": "https://www.tiktok.com/@reviewcongnghe_vn",
                        }
                    ],
                }

            def search_affiliate_global_selling_creators(self, keyword, max_results=20):
                return [
                    {
                        "handle": "unbox_phu_kien_xin",
                        "display_name": "Unbox Phụ Kiện Xịn",
                        "category": "Điện thoại & Điện tử",
                        "followers": 185000,
                        "total_gmv_vnd": 890_000_000,
                        "total_gmv_display": "890.0 tr ₫",
                        "items_sold": 2650,
                        "avg_views": 54000,
                        "engagement_rate": 6.4,
                        "source": "affiliate_global_selling",
                        "profile_url": "https://www.tiktok.com/@unbox_phu_kien_xin",
                        "top_videos": [],
                    }
                ]

        self.api.ecosystems.kalodata_bridge = FakeKalodataBridge()

        st_gj, res_gj = self.req("POST", "/api/ecosystems/run", {
            "name": "Phụ kiện Goojodoq",
            "seed_keyword": "goojodoq",
            "extra_keywords": ["phụ kiện goojodoq"],
            "channels": ["tiktok_shop_vn", "shopee_vn"],
            "enable_cn_expansion": False,
            "enable_kalodata": True,
            "enable_global_selling_creators": True,
            "daily_schedule_enabled": True,
        })
        self.assertEqual(st_gj, 200)
        col_gj = res_gj["collection"]
        self.assertEqual(len(col_gj["keyword_watches"]), 2)
        self.assertGreaterEqual(len(col_gj["creators"]), 2)
        self.assertEqual(len(col_gj["videos"]), 1)
        self.assertTrue(col_gj["daily_schedule_enabled"])

        # Simulate Day 2 Crawl -> detects 1 brand-new Goojodoq Magic Keyboard product!
        fake_eco_apify.day_two = True
        st_day2, res_day2 = self.req("POST", f"/api/ecosystems/{col_gj['collection_id']}/check-daily", {})
        self.assertEqual(st_day2, 200)
        self.assertEqual(len(res_day2["new_products"]), 1)
        self.assertEqual(res_day2["new_products"][0]["native_product_id"], "555000999")
        self.assertEqual(res_day2["collection"]["index_summary"]["last_new_products_detected"], 1)


if __name__ == "__main__":
    unittest.main()
