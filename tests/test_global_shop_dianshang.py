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
        self.api.desk_pipeline.jev = fake_jev
        self.api.hunt_schedules.jev = fake_jev
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
        self.api.desk_pipeline.desk300 = fake_desk
        self.api.hunt_schedules.desk300 = fake_desk

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
        self.assertEqual(health["version"], "1.0.18")
        self.assertEqual(__version__, "1.0.18")
        self.assertEqual(health["schema_version"], 8)

        st_la, la_info = self.req("GET", "/api/system/launchagent")
        self.assertEqual(st_la, 200)
        self.assertEqual(la_info["label"], "com.peng.global-shop-dianshang")

        # Custom Favicon, Apple Touch Icon & WebManifest over Tailscale Host
        for icon_path, expected_ct in (
            ("/favicon.ico", "image/x-icon"),
            ("/favicon.svg", "image/svg+xml"),
            ("/apple-touch-icon.png", "image/png"),
            ("/site.webmanifest", "application/manifest+json"),
        ):
            r_ico = urllib.request.Request(
                self.base_url + icon_path,
                headers={"Host": "nguyens-mac-mini.tail213fd3.ts.net:8999"},
                method="GET",
            )
            with urllib.request.urlopen(r_ico, timeout=5) as resp_ico:
                self.assertEqual(resp_ico.status, 200)
                self.assertIn(expected_ct, resp_ico.headers.get("Content-Type", ""))
                self.assertGreater(len(resp_ico.read()), 200)

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
        from backend.ecosystem_playbook import is_item_relevant_to_ecosystem
        from backend.providers.apify import ApifyClient

        # Verify strict brand/seed relevance filter drops fuzzy noise & keeps real e-reader items
        self.assertFalse(is_item_relevant_to_ecosystem("VÍ đựng đồ cá nhân SHINE TORE ST-274", "Shop Ví", "xteink", ["xteink x4"]))
        self.assertTrue(is_item_relevant_to_ecosystem("Máy đọc sách Xt eink X4 Classic Mini", "TechReader.vn", "xteink", ["xteink x4"]))
        self.assertTrue(is_item_relevant_to_ecosystem("Cao cấp TPU mềm Hộp đựng máy đọc sách điện tử 4.3\" Vỏ bảo vệ", "", "xteink", ["xteink x4"]))

        # Verify Shopee `soldRecent` + `variants` stock & 1688 dict-price normalization
        norm_sp = ApifyClient.normalize_shopee_item({
            "itemId": "52804400175",
            "shopId": "5524067",
            "title": "Máy đọc sách Xteink X4 Classic",
            "price": 1450000,
            "soldTotal": 1341,
            "soldRecent": 185,
            "variants": [{"name": "Đen", "stock": 12}, {"name": "Trắng", "stock": 9}],
        })
        self.assertEqual(norm_sp["sold_count"], 1341)
        self.assertEqual(norm_sp["sold_30d"], 185)
        self.assertEqual(norm_sp["stock"], 21)

        norm_cn = ApifyClient.normalize_china_item({
            "offerId": "627414195890",
            "title": "适用阅星瞳x4 Classic保护套Xteink X4 V2保护壳",
            "price": {"min": 8.8, "max": 12.0, "currency": "CNY"},
        }, "1688")
        self.assertEqual(norm_cn["price_cny"], 8.8)

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

    def test_09_universal_telegram_notifications_and_work_logs_sync(self):
        from backend.history_log import classify_http_module

        # 1) Every new & core endpoint maps to a classified module (never None!)
        for p_check, expected_mod in (
            ("/api/ecosystems/run", "ecosystems"),
            ("/api/apify-store/sync", "apify_store"),
            ("/api/kalodata/sync-from-affiliate", "kalodata"),
            ("/api/desk300/run", "desk300"),
            ("/api/watches/wt_123/check", "watches"),
            ("/api/future-unknown-endpoint", "system"),
        ):
            cls = classify_http_module(p_check)
            self.assertIsNotNone(cls)
            self.assertEqual(cls[0], expected_mod)

        # 2) Enable Telegram Bot with fake runner and trigger HTTP + Scheduled Daemon + Manual Resend
        self.req("POST", "/api/settings", {
            "notify": {
                "telegram_enabled": True,
                "telegram_token": "1234567890:AAFakeSampleTokenForUnitTestOnly12345",
                "telegram_chat_id": "5608975895",
                "telegram_allowed_user_ids": "5608975895",
            }
        })
        self.fake_tg.sent_messages.clear()

        # Mutating API action creates GS-XXXX log
        self.req("POST", "/api/products", {
            "platform": "shopee_vn",
            "native_product_id": "8899001122",
            "title": "Ốp từ tính Xteink X4 Test Telegram",
            "price_vnd": 125000,
            "sold_count": 45,
            "stock": 30,
        })

        # Scheduled Watch check (background daemon trigger) also creates GS-XXXX log!
        _, w_res = self.req("POST", "/api/watches", {
            "watch_type": "product",
            "platform": "shopee_vn",
            "target_key": "https://shopee.vn/product/1/8899001122",
            "title": "⭐ Theo dõi Ốp Xteink X4",
        })
        wid = w_res["watch"]["watch_id"]
        self.api.watches.run_watch_check(wid, trigger_kind="scheduled")

        # Sync all pending logs to Telegram via Outbox Sweep (`POST /api/providers/telegram/sync-pending`)
        st_sync, sync_res = self.req("POST", "/api/providers/telegram/sync-pending", {})
        self.assertEqual(st_sync, 200)
        self.assertGreaterEqual(sync_res["synced"], 3)  # settings + product + watch create + scheduled watch

        _, hist_res = self.req("GET", "/api/history-logs")
        self.assertEqual(hist_res["kpis"]["telegram_pending"], 0)
        self.assertEqual(hist_res["kpis"]["telegram_notified"], hist_res["kpis"]["total"])
        self.assertGreaterEqual(len(self.fake_tg.sent_messages), hist_res["kpis"]["total"])
        self.assertTrue(any("[GS-" in m.get("text", "") and "Theo dõi định kỳ" in m.get("text", "") for m in self.fake_tg.sent_messages))

        # Manual 1-click resend of a specific GS-XXXX log
        first_lid = hist_res["logs"][0]["log_id"]
        prev_tg_cnt = len(self.fake_tg.sent_messages)
        st_rs, rs_res = self.req("POST", f"/api/history-logs/{first_lid}/resend-telegram", {})
        self.assertEqual(st_rs, 200)
        self.assertTrue(rs_res["delivered"])
        self.assertEqual(len(self.fake_tg.sent_messages), prev_tg_cnt + 1)

    def test_10_recurring_hunt_painpoint_autopilot_300desk_jev_classify_and_telegram(self):
        from backend.providers.desk300plus import Desk300PlusClient

        settings.add_apify_key(self.api.connect, self.api.secrets, "Sched Test", "apify_api_test_sched_key_0001")
        self.req("POST", "/api/settings", {
            "providers": {"typesafe_key": "apikey_jev_sched_0001"},
            "notify": {
                "telegram_enabled": True,
                "telegram_token": "1234567890:AAFakeSampleTokenForUnitTestOnly12345",
                "telegram_chat_id": "5608975895",
                "telegram_allowed_user_ids": "5608975895",
            },
        })

        class SchedApify:
            def __init__(self):
                self.day = 1

            def scrape_shopee_product(self, tokens, url, max_charge_usd=0.05, market="VN"):
                return {
                    "platform": "shopee",
                    "market": "VN",
                    "native_product_id": "1110001",
                    "shop_name": "Gia Dụng Thông Minh VN",
                    "title": "Phễu thoát sàn ngăn mùi hôi cống Inox 304",
                    "price_vnd": 69000,
                    "sold_count": 420,
                    "stock": 40 if self.day == 1 else 31,  # Day 2 stock drops by 9 => +9 inferred sales!
                    "url": "https://shopee.vn/product/99/1110001",
                }

            def search_social_painpoints(self, tokens, channel, query, limit=6):
                return "apify~threads-scraper", [
                    {
                        "channel": channel,
                        "text": "Nhà tắm cứ mưa là bốc mùi hôi cống với ẩm mốc khó chịu quá mọi người tìm mua phễu loại nào tốt?",
                        "likes": 85,
                        "comments": 32,
                    }
                ]

            def search_shopee(self, tokens, kw, limit=8, max_charge_usd=0.08, filters=None, market="VN"):
                items = [
                    {
                        "platform": "shopee",
                        "market": "VN",
                        "native_product_id": "2220001",
                        "shop_name": "HomeClean Official",
                        "title": "Xịt tẩy nấm mốc nhà tắm công nghệ sinh học 500ml",
                        "price_vnd": 89000,
                        "sold_count": 650,
                        "stock": 120,
                        "url": "https://shopee.vn/product/88/2220001",
                    }
                ]
                if self.day >= 2:
                    items.append({
                        "platform": "shopee",
                        "market": "VN",
                        "native_product_id": "2220999",
                        "shop_name": "HomeClean Official",
                        "title": "[MỚI 2026] Máy hút ẩm khử mùi nhà vệ sinh Mini Ion Âm",
                        "price_vnd": 345000,
                        "sold_count": 58,
                        "stock": 95,
                        "url": "https://shopee.vn/product/88/2220999",
                    })
                return "lergassy~shopee-scraper", items

            def search_tiktok_shop(self, tokens, kw, limit=8, max_charge_usd=0.06, market="VN"):
                return "harshmaur~tiktok-shop-scraper", []

        sched_apify = SchedApify()
        self.api.hunt.apify = sched_apify
        self.api.hunt_schedules.apify = sched_apify
        self.api.products.apify = sched_apify

        class SchedDeskRunner:
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
                meta = {"verified": {"path_ok": True, "via_socks": True, "direct_mac_call": False, "fallback_used": False, "forbidden_hosts_in_artifacts": []}}
                if "daily_synthesis" in prompt_text:
                    return json.dumps({
                        "daily_synthesis": "Thị trường giải pháp khử mùi & chống ẩm nhà tắm tăng trưởng tốt: phát hiện mẫu Máy hút ẩm Mini Ion Âm mới lên sàn, Phễu thoát sàn giảm tồn kho 9 cái. Khuyến nghị nhập test 20 bộ combo Phễu + Xịt nấm mốc."
                    }, ensure_ascii=False), meta
                # Parse product IDs from prompt
                ids_found = [int(m) for m in __import__("re").findall(r'"id":\s*(\d+)', prompt_text)]
                return json.dumps({
                    "items": [
                        {
                            "id": pid,
                            "keep": True,
                            "seo_title": f"[Chuẩn SEO] Giải pháp Khử Mùi Nhà Tắm #{pid}",
                            "cn_1688_keyword": "防臭地漏芯 304不锈钢",
                            "combo_strategy": "Combo 2 phễu + tặng lưới lọc tóc",
                            "video_angles": ["Hook 3s: Mùi hôi cống bốc lên mỗi ngày", "Test xả nước tốc độ cao", "Chốt combo 2 cái miễn ship"],
                        }
                        for pid in ids_found
                    ]
                }, ensure_ascii=False), meta

        live_desk = Desk300PlusClient(custom_runner=SchedDeskRunner())
        self.api.desk_pipeline.desk300 = live_desk
        self.api.hunt_schedules.desk300 = live_desk

        # 1) Create recurring daily schedule at 07:30 & run Day 1 baseline immediately
        st_cr, cr_res = self.req("POST", "/api/hunt/schedules", {
            "name": "Săn 07:30: Khử mùi & Chống mốc nhà tắm",
            "keywords": ["nhà tắm mùi hôi"],
            "pinned_products": ["https://shopee.vn/product/99/1110001"],
            "channels": ["threads", "shopee_vn"],
            "schedule_mode": "daily_time",
            "daily_time": "07:30",
            "use_300desk": True,
            "auto_score_jev": True,
            "auto_classify_buckets": True,
            "auto_promote_strong_pick": True,
            "run_immediately": True,
        })
        self.assertEqual(st_cr, 200)
        sid = cr_res["schedule"]["schedule_id"]
        self.assertEqual(cr_res["schedule"]["cadence_label"], "Hàng ngày lúc 07:30")
        self.assertGreaterEqual(cr_res["first_run"]["strong_pick_count"], 2)
        self.assertIn("Máy hút ẩm", cr_res["first_run"]["desk_synthesis_text"])

        # Verify Jev + auto_promote_strong_pick automatically classified products into `dang_nhap_ban`!
        self.assertGreaterEqual(cr_res["first_run"]["bucket_breakdown"].get("dang_nhap_ban", 0), 2)

        # 2) Simulate Day 2 Scheduled Cron Execution (`run_due_schedules`) -> detects +1 NEW product & +9 stock-drop sales!
        sched_apify.day = 2
        with self.api.connect() as conn:
            conn.execute("UPDATE hunt_schedules SET next_run_at='2020-01-01T00:00:00Z' WHERE schedule_id=?", (sid,))
        self.fake_tg.sent_messages.clear()
        ran_cnt = self.api.hunt_schedules.run_due_schedules()
        self.assertEqual(ran_cnt, 1)

        # Flush outbox to Telegram and verify full Day 2 report arrived on Telegram!
        self.req("POST", "/api/providers/telegram/sync-pending", {})
        self.assertTrue(any("Lịch săn lặp lại" in m.get("text", "") and "SP mới" in m.get("text", "") for m in self.fake_tg.sent_messages))

        _, det_s = self.req("GET", f"/api/hunt/schedules/{sid}")
        latest_run = det_s["schedule"]["runs"][0]
        self.assertEqual(latest_run["new_products_count"], 1)
        self.assertEqual(latest_run["rising_products_count"], 1)
        self.assertEqual(latest_run["rising_items"][0]["delta_sold"], 9)

    def test_11_jev_product_leaderboard_ranking_pillars_csv_and_telegram_bxh(self):
        self.req("POST", "/api/settings", {
            "providers": {"typesafe_key": "apikey_jev_rank_0001"},
        })

        class CustomRankJev:
            def score_seller_product(self, api_key, product, model="", base_url=""):
                t = product.get("title") or ""
                if "Alpha" in t:
                    return {
                        "overall_10": 8.65,
                        "pillars": {"suc_cau": 9.2, "bien_lai": 8.4, "de_nhap_tq": 8.9, "canh_tranh": 8.0, "khac_biet": 8.3, "de_lam_video": 7.5},
                        "industry": "cong_nghe",
                        "import_test_prob": 0.91,
                        "jev_model": "jev-1.14.0",
                        "_cost_usd": 0.0006,
                    }
                return {
                    "overall_10": 6.45,
                    "pillars": {"suc_cau": 6.8, "bien_lai": 6.0, "de_nhap_tq": 6.5, "canh_tranh": 5.9, "khac_biet": 6.2, "de_lam_video": 9.4},
                    "industry": "gia_dung",
                    "import_test_prob": 0.62,
                    "jev_model": "jev-1.14.0",
                    "_cost_usd": 0.0006,
                }

        self.api.products.jev = CustomRankJev()

        self.req("POST", "/api/products", {
            "platform": "shopee_vn",
            "native_product_id": "90001",
            "title": "Alpha Bao da từ tính Xteink X4 Pro",
            "price_vnd": 185000,
            "sold_count": 1200,
        })
        self.req("POST", "/api/products", {
            "platform": "tiktok_shop_vn",
            "native_product_id": "90002",
            "title": "Beta Quạt cầm tay đèn LED đổi màu",
            "price_vnd": 95000,
            "sold_count": 450,
        })

        # Batch score unscored products prioritized by sales!
        st_sc, sc_res = self.req("POST", "/api/products/score-unscored", {"limit": 10})
        self.assertEqual(st_sc, 200)
        self.assertEqual(sc_res["scored_count"], 2)

        # 1) Default rank by overall_10 -> Alpha (#1, 8.65) > Beta (#2, 6.45)
        st_lb, lb = self.req("GET", "/api/products/jev-leaderboard?rank_by=overall_10")
        self.assertEqual(st_lb, 200)
        self.assertEqual(lb["kpis"]["total_scored"], 2)
        self.assertEqual(lb["kpis"]["strong_pick_count"], 1)
        self.assertEqual(lb["kpis"]["maybe_count"], 1)
        self.assertEqual(lb["items"][0]["rank"], 1)
        self.assertIn("Alpha", lb["items"][0]["title"])
        self.assertEqual(lb["items"][0]["import_test_prob_pct"], 91.0)

        # 2) Rank by `de_lam_video` pillar -> Beta (#1, 9.4) > Alpha (#2, 7.5)!
        _, lb_vid = self.req("GET", "/api/products/jev-leaderboard?rank_by=de_lam_video")
        self.assertIn("Beta", lb_vid["items"][0]["title"])
        self.assertEqual(lb_vid["items"][0]["pillars"]["de_lam_video"], 9.4)

        # 3) Filter `tier=strong_pick` -> only Alpha!
        _, lb_sp = self.req("GET", "/api/products/jev-leaderboard?tier=strong_pick")
        self.assertEqual(len(lb_sp["items"]), 1)
        self.assertIn("Alpha", lb_sp["items"][0]["title"])

        # 4) CSV export & Telegram `/topjev` command
        with urllib.request.urlopen(self.base_url + "/api/products/jev-leaderboard/export.csv", timeout=5) as r_csv:
            csv_txt = r_csv.read().decode("utf-8-sig")
            self.assertIn("#1", csv_txt)
            self.assertIn("Alpha Bao da", csv_txt)

        tg_reply = self.api.telegram_bot._build_command_reply("/topjev", "")
        self.assertIn("🥇 Jev 8.65/10", tg_reply)

    def test_12_full_kalodata_pro_hunter_import_capture_and_account_rotation(self):
        from backend.kalodata_parser import parse_kalodata_display_cell, parse_xlsx_bytes

        # 1) Parser invariants: missing/locked NEVER become 0; upper_bound & range preserved
        self.assertIsNone(parse_kalodata_display_cell("---", expected_currency="VND")["value_decimal"])
        self.assertEqual(parse_kalodata_display_cell("***")["value_state"], "locked")
        self.assertIsNone(parse_kalodata_display_cell("***")["value_decimal"])
        ub = parse_kalodata_display_cell("< 100")
        self.assertEqual(ub["qualifier"], "upper_bound")
        self.assertIsNone(ub["value_decimal"])
        self.assertEqual(ub["max_decimal"], "100")
        rng = parse_kalodata_display_cell("150K - 250K")
        self.assertEqual(rng["qualifier"], "range")
        self.assertEqual(rng["min_decimal"], "150000")
        self.assertEqual(rng["max_decimal"], "250000")
        with self.assertRaises(ValueError):
            parse_xlsx_bytes(b"id,name\n1,fake_csv_renamed_as_xlsx")

        # 2) Kalodata VN Categories Catalog & Direct Hunter ($0.00) -> Vault + Jev
        self.req("POST", "/api/settings", {
            "providers": {"typesafe_key": "apikey_jev_kalo_001"},
            "notify": {
                "telegram_enabled": True,
                "telegram_token": "1234567890:AAFakeSampleTokenForUnitTestOnly12345",
                "telegram_chat_id": "5608975895",
                "telegram_allowed_user_ids": "5608975895",
            },
        })
        st_cat, cats = self.req("GET", "/api/hunt/kalodata-vn/categories")
        self.assertEqual(st_cat, 200)
        self.assertGreaterEqual(len(cats["items"]), 30)

        def fake_hunter_scraper(kind, **kwargs):
            if kind == "categories_leaderboard":
                return {
                    "ok": True,
                    "module": "category_board",
                    "window_spec": "7d",
                    "items_count": 1,
                    "items": [{"rank": 1, "category_id": "600001", "category_name_vi": "Gia dụng & Đời sống hàng ngày", "icon": "🏠", "level": "L1", "gmv_total_vnd": 15000000000, "gmv_total_display": "15.00 tỷ ₫", "affiliate_share_pct": 42.5, "video_share_pct": 58.0}],
                }
            return {
                "products": [
                    {
                        "rank": 1,
                        "native_product_id": "1738990011223344556",
                        "product_title": "Máy hút ẩm nhà tắm mini khử mùi thông minh",
                        "price_vnd": 265000,
                        "canonical_url": "https://shop.tiktok.com/view/product/1738990011223344556?region=VN",
                        "window_spec": "7d",
                        "gmv_total_vnd": 185000000,
                        "gmv_total_display": "185.0 tr ₫",
                        "gmv_growth_pct": 38.5,
                        "units_sold_window": 698,
                        "commission_pct": 12.0,
                        "active_creators_count": 14,
                        "video_gmv_vnd": 148000000,
                        "video_gmv_display": "148.0 tr ₫",
                        "live_gmv_vnd": 25000000,
                        "live_gmv_display": "25.0 tr ₫",
                        "keyword": "máy hút ẩm mini",
                    }
                ],
                "videos": [
                    {
                        "rank": 1,
                        "native_video_id": "7412345678901234567",
                        "video_url": "https://www.tiktok.com/@koc_giadung/video/7412345678901234567",
                        "caption": "Đặt máy này trong nhà tắm hết sạch ẩm mốc",
                        "author_handle": "koc_giadung",
                        "video_gmv_vnd": 64000000,
                        "video_gmv_display": "64.0 tr ₫",
                        "video_orders_count": 240,
                        "views_count": 320000,
                        "video_gpm_vnd": 200000,
                        "video_gpm_display": "200,000₫",
                        "is_ad": False,
                    }
                ],
                "creators": [
                    {
                        "handle": "koc_giadung",
                        "followers_count": 48000,
                        "sum_video_gmv_vnd": 64000000,
                        "sum_views_count": 320000,
                        "niche_video_gpm_display": "200,000₫",
                    }
                ],
                "shops": [],
            }

        self.api.kalodata_hunter.custom_scraper = fake_hunter_scraper
        st_kh, kh_res = self.req("POST", "/api/hunt/kalodata-vn", {
            "category_id": "600001",
            "keywords": ["máy hút ẩm mini"],
            "window_spec": "7d",
            "auto_ingest_suitable": True,
            "score_jev": True,
        })
        self.assertEqual(st_kh, 200)
        self.assertEqual(kh_res["products_count"], 1)
        self.assertEqual(kh_res["suitable_products_count"], 1)
        self.assertEqual(len(kh_res["saved_product_ids"]), 1)
        self.assertEqual(kh_res["jev_scored_count"], 1)

        # 3) Kalodata Pro 9-Page Suite: Shops, Creators (+ Bio Zalo/Email), AI Videos & Deep Detail (+ Clean MP4 & SKU Stock)
        def fake_pro_scraper(mod, **kwargs):
            if mod == "shops":
                return {
                    "rows": [
                        {
                            "rowKey": "7495001122334455667",
                            "rowOrig": {
                                "id": "7495001122334455667",
                                "name": "Gia Dụng Thông Minh VN Official",
                                "seller_type": "BRAND",
                                "revenue": "₫320000000",
                                "affiliate_revenue": "₫160000000",
                                "video_revenue": "₫140000000",
                                "sale": 1450,
                            },
                        }
                    ]
                }
            if mod == "creators":
                return {
                    "rows": [
                        {
                            "rowKey": "6800112233445566778",
                            "rowOrig": {
                                "id": "6800112233445566778",
                                "handle": "review_nhadep_vn",
                                "nickname": "Review Nhà Đẹp",
                                "signature": "Booking Zalo: 0912.345.678 - Email: booking@nhadep.vn",
                                "revenue": "₫95000000",
                                "sale": 410,
                                "followers": 52000,
                                "views_trend": [120000, 180000],
                            },
                        }
                    ]
                }
            if mod == "videos_advanced":
                return {
                    "rows": [
                        {
                            "rowKey": "7422334455667788990",
                            "rowOrig": {
                                "id": "7422334455667788990",
                                "handle": "ai_shop_creator",
                                "description": "Video AI bán kệ nhà tắm cực nhạy",
                                "ai_video": True,
                                "ad": True,
                                "ad2Roas": "2.65",
                                "revenue": "₫48000000",
                                "gpm": "₫185000",
                                "views": 260000,
                                "sale": 310,
                                "follower_count": 29000,
                            },
                        }
                    ]
                }
            if mod == "video_detail":
                return {
                    "title": "Video test máy hút ẩm 越南 TikTok Data",
                    "vids": ["https://live.kalocdn.com/video/7422334455667788990.mp4"],
                    "prodImgs": ["https://img.kalocdn.com/tiktok.product/1738990011223344556/cover.jpg"],
                    "body": "ai_shop_creator 2.9万 粉丝数 发布日期：2026-11-18 投广时间：5 天 观看次数 26万 销量 310 成交金额 ₫4800万 广告ROAS 2.65",
                    "rowsOrig": [],
                }
            if mod == "product_detail":
                return {
                    "title": "Máy hút ẩm nhà tắm mini - 商品详情",
                    "body": "数据最早收录时间：2026-10-01 价格：₫26.5万 佣金比例：12% 评分：4.9 销售策略 成交金额 ₫1.85亿 = 直播 ₫2500万 13.5% + 视频 ₫1.48亿 80.0% + 商品卡 6.5% 卖点 Khử ẩm nhanh, êm ái 属性 Nhựa ABS cao cấp SKU分析",
                    "rowsOrig": [
                        {"ro": {"sku_name": "Bản Trắng 1000ml", "sale_ratio": 0.72, "price": 265000, "stock": 430}, "tds": []},
                        {"ro": {"sku_name": "Bản Đen Kèm Ống Xả", "sale_ratio": 0.28, "price": 299000, "stock": 185}, "tds": []},
                    ],
                }
            return {"rows": []}

        self.api.kalodata_pro.custom_scraper = fake_pro_scraper

        st_ps, ps_res = self.req("POST", "/api/hunt/kalodata-pro/shops", {"keyword": "gia dụng", "window_spec": "7d"})
        self.assertEqual(st_ps, 200)
        self.assertEqual(ps_res["items_count"], 1)
        self.assertEqual(ps_res["saved_to_vault_count"], 1)

        st_pc, pc_res = self.req("POST", "/api/hunt/kalodata-pro/creators", {"keyword": "nhà đẹp"})
        self.assertEqual(st_pc, 200)
        self.assertEqual(pc_res["with_contact_count"], 1)
        self.assertIn("0912345678", pc_res["items"][0]["phones_zalo"])
        self.assertIn("booking@nhadep.vn", pc_res["items"][0]["emails"])

        st_pv, pv_res = self.req("POST", "/api/hunt/kalodata-pro/videos-advanced", {"filter_mode": "ai_video"})
        self.assertEqual(st_pv, 200)
        self.assertEqual(pv_res["ai_videos_count"], 1)

        st_dv, dv_res = self.req("POST", "/api/hunt/kalodata-pro/deep-detail", {"target": "vid:7422334455667788990"})
        self.assertEqual(st_dv, 200)
        self.assertTrue(dv_res["has_watermark_free_mp4"])
        self.assertIn("kalocdn.com/video/7422334455667788990.mp4", dv_res["mp4_cdn_url"])

        st_dp, dp_res = self.req("POST", "/api/hunt/kalodata-pro/deep-detail", {"target": "1738990011223344556"})
        self.assertEqual(st_dp, 200)
        self.assertEqual(dp_res["total_sku_stock"], 615)
        self.assertEqual(len(dp_res["skus"]), 2)

        # 4) Kalodata Import Wizard (19-digit ID safety + cross-market guard) & Bounded Browser Capture + ZIP download
        st_prev, prev_res = self.req("POST", "/api/imports/preview", {
            "market": "VN",
            "currency": "VND",
            "window": "7d",
            "filename": "products.json",
            "content": json.dumps([
                {"product_id": "1729998887776665554", "product_name": "Đèn cảm biến cầu thang thông minh", "price": "89000", "gmv": "125000000", "units_sold": "1400", "market": "VN"},
                {"product_id": "1729998887776665559", "product_name": "SP Thái Lan trộn nhầm", "price": "199", "gmv": "50000", "market": "TH"},
            ]),
        })
        self.assertEqual(st_prev, 200)
        self.assertEqual(prev_res["summary"]["products_staged"], 1)
        self.assertEqual(prev_res["summary"]["errors_count"], 1)
        self.assertEqual(prev_res["errors"][0]["code"], "market_mismatch_blocked")

        # Strict commit refuses cross-market rows unless allow_skip_invalid=True
        st_blk, _ = self.req("POST", f"/api/imports/{prev_res['batch_id']}/commit", {"allow_skip_invalid": False})
        self.assertEqual(st_blk, 409)
        st_cm, cm_res = self.req("POST", f"/api/imports/{prev_res['batch_id']}/commit", {"allow_skip_invalid": True})
        self.assertEqual(st_cm, 200)
        self.assertEqual(cm_res["summary"]["committed_products"], 1)

        self.api.kalodata_import.custom_capture_driver = lambda max_pages=1, max_rows=100: {
            "url": "https://www.kalodata.com/product",
            "headers": ["商品信息", "成交金额", "销量"],
            "rows": [
                {"id": "1729111222333444555", "商品信息": "Bình giữ nhiệt inox 316", "成交金额": "₫98000000", "销量": "620"},
                {"id": "1729111222333444556", "商品信息": "Dòng nhiễu cần loại bỏ", "成交金额": "***", "销量": "***"},
            ],
            "pages_read": 1,
        }
        st_cap, cap = self.req("POST", "/api/kalodata/captures/current-page", {"market": "VN", "currency": "VND", "window_spec": "7d"})
        self.assertEqual(st_cap, 200)
        cap_id = cap["capture_id"]
        self.req("POST", f"/api/kalodata/captures/{cap_id}/preview", {"exclude_row_indices": [1]})
        st_cc, cc_res = self.req("POST", f"/api/kalodata/captures/{cap_id}/commit", {})
        self.assertEqual(st_cc, 200)
        self.assertEqual(cc_res["summary"]["committed_products"], 1)

        with urllib.request.urlopen(self.base_url + f"/api/kalodata/captures/{cap_id}/download?format=zip", timeout=5) as r_zip:
            self.assertEqual(r_zip.headers.get("Content-Type"), "application/zip")
            self.assertTrue(r_zip.read().startswith(b"PK\x03\x04"))

        # 5) Kalodata Account Rotation + Telegram `/kalodata` bot command
        self.api.kalodata_bridge.custom_rotation_driver = lambda email, pw, mkt, log_cb: (
            log_cb("Mock Chrome: đã xoá cookie kalodata.com cũ & đăng nhập tài khoản mới"),
            {"status": "completed", "kalodata_after": {"status": "ok_full", "plan_label_vi": "Gói Kalodata Pro Trả phí đầy đủ"}},
        )[1]
        st_rot, rot_res = self.req("POST", "/api/kalodata/rotate-account", {
            "account_email": "pro_kalo_vn@peng.vn",
            "password": "SuperSecretKaloPass_DoNotLeak",
            "market": "VN",
            "currency": "VND",
        })
        self.assertEqual(st_rot, 200)
        self.assertTrue(rot_res["ok"])
        self.assertTrue(rot_res["telegram_sent"])

        # Verify password is NEVER leaked in `/api/settings` or `/api/kalodata/rotations`
        _, st_masked = self.req("GET", "/api/settings")
        self.assertNotIn("SuperSecretKaloPass_DoNotLeak", json.dumps(st_masked))
        _, rots = self.req("GET", "/api/kalodata/rotations")
        self.assertNotIn("SuperSecretKaloPass_DoNotLeak", json.dumps(rots))

        tg_kalo = self.api.telegram_bot._build_command_reply("/kalodata", "")
        self.assertIn("Kalodata Pro (9 Trang · 0₫)", tg_kalo)
        self.assertIn("pro_kalo_vn@peng.vn", tg_kalo)

    def test_13_live_kalodata_account_mirroring_from_affiliate_peng(self):
        import os
        import sqlite3
        from pathlib import Path

        self.req("POST", "/api/settings", {
            "notify": {
                "telegram_enabled": True,
                "telegram_token": "1234567890:AAFakeSampleTokenForUnitTestOnly12345",
                "telegram_chat_id": "5608975895",
                "telegram_allowed_user_ids": "5608975895",
            },
        })

        # Create a mock `affiliate-peng/local-data` with SQLite + mock secret store
        aff_dir = Path(self.tmp.name) / "mock_affiliate_peng"
        aff_dir.mkdir(parents=True, exist_ok=True)
        aff_db = aff_dir / "backend.sqlite3"
        aff_secrets = create_secret_store(aff_dir, prefer_keychain=False)

        conn = sqlite3.connect(aff_db)
        with conn:
            conn.execute("CREATE TABLE settings (name TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.execute(
                """
                CREATE TABLE kalodata_account_rotations (
                    rotation_id TEXT PRIMARY KEY,
                    old_account_hint TEXT NOT NULL DEFAULT '',
                    new_account_email TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'completed',
                    kalodata_status_after TEXT NOT NULL DEFAULT '',
                    step_logs_json TEXT NOT NULL DEFAULT '[]',
                    kalodata_after_json TEXT NOT NULL DEFAULT '{}',
                    telegram_sent INTEGER NOT NULL DEFAULT 0,
                    telegram_message_id TEXT NOT NULL DEFAULT '',
                    error_message TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT INTO settings (name, value) VALUES ('application', ?)",
                (json.dumps({"kalodata": {"account_email": "18613938760", "market": "VN", "currency": "VND", "default_window_days": 7}}),),
            )
            conn.execute(
                "INSERT INTO kalodata_account_rotations (rotation_id, old_account_hint, new_account_email, status, created_at) VALUES (?, ?, ?, 'completed', '2026-11-21T01:54:30Z')",
                ("klrot_step1", "jreed767@cnebw.eu.cc", "18613938760"),
            )
        conn.close()
        aff_secrets.set("kalodata.password", "AffPass_Step1_Secret")

        # Attach live mirror to Global Shop's Kalodata bridge
        self.api.kalodata_bridge.affiliate_peng_root = aff_dir
        self.api.kalodata_bridge.affiliate_peng_secret_store = aff_secrets
        self.api.kalodata_bridge.mirror_enabled = True
        self.api.kalodata_bridge._last_stat_sig = None

        # 1) Initial sync pulls `18613938760` + password + rotation row automatically
        _, st1 = self.req("GET", "/api/kalodata/status")
        self.assertEqual(st1["account_email"], "18613938760")
        self.assertEqual(self.api.secrets.get("kalodata.password"), "AffPass_Step1_Secret")

        # 2) Simulate `affiliate-peng` rotating account to `13251340633` + new password
        conn2 = sqlite3.connect(aff_db)
        with conn2:
            conn2.execute(
                "UPDATE settings SET value=? WHERE name='application'",
                (json.dumps({"kalodata": {"account_email": "13251340633", "market": "VN", "currency": "VND", "default_window_days": 30}}),),
            )
            conn2.execute(
                "INSERT INTO kalodata_account_rotations (rotation_id, old_account_hint, new_account_email, status, created_at) VALUES (?, ?, ?, 'completed', '2026-11-23T03:36:11Z')",
                ("klrot_step2", "18613938760", "13251340633"),
            )
        conn2.close()
        aff_secrets.set("kalodata.password", "AffPass_Step2_Updated")
        os.utime(aff_db, None)
        self.api.kalodata_bridge._last_check_mono = 0.0

        # Without clicking any manual sync button, `GET /api/settings` & `/api/kalodata/rotations` reflect `13251340633` immediately!
        _, gs_set = self.req("GET", "/api/settings")
        self.assertEqual(gs_set["settings"]["kalodata"]["account_email"], "13251340633")
        self.assertEqual(gs_set["settings"]["kalodata"]["default_window_days"], 30)
        self.assertEqual(self.api.secrets.get("kalodata.password"), "AffPass_Step2_Updated")

        _, gs_rots = self.req("GET", "/api/kalodata/rotations")
        rot_ids = [r["rotation_id"] for r in gs_rots["items"]]
        self.assertIn("klrot_step1", rot_ids)
        self.assertIn("klrot_step2", rot_ids)

        # Verify GS-XXXX auto-mirror work log was recorded & pushed to Telegram!
        self.req("POST", "/api/providers/telegram/sync-pending", {})
        self.assertTrue(any("13251340633" in m.get("text", "") and "ánh xạ" in m.get("text", "").lower() for m in self.fake_tg.sent_messages))

        # 3) Bidirectional sync: updating Kalodata in Global Shop also updates `affiliate-peng`!
        self.req("POST", "/api/settings", {
            "kalodata": {"account_email": "bidir_sync@peng.vn", "password": "BidirNewPass_777", "market": "VN", "currency": "VND", "default_window_days": 7}
        })
        conn3 = sqlite3.connect(aff_db)
        up_after = json.loads(conn3.execute("SELECT value FROM settings WHERE name='application'").fetchone()[0])
        conn3.close()
        self.assertEqual(up_after["kalodata"]["account_email"], "bidir_sync@peng.vn")
        self.assertEqual(aff_secrets.get("kalodata.password"), "BidirNewPass_777")


if __name__ == "__main__":
    unittest.main()
