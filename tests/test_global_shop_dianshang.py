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
        self.assertEqual(health["version"], "1.0.3")
        self.assertEqual(__version__, "1.0.3")
        self.assertEqual(health["schema_version"], 2)

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


if __name__ == "__main__":
    unittest.main()
