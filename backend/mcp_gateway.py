"""Streamable HTTP (/mcp) + Stdio MCP Gateway exposing Global Shop Dianshang tools to AI agents."""
import hmac
import json
import secrets
import time

from . import PRODUCT_NAME, __version__, settings
from .responses import check_host_and_origin, json_object, now


class McpGatewayService:
    def __init__(self, app, web_port: int = 8999):
        self.app = app
        self.web_port = web_port
        self._sessions: set[str] = set()

    def _tools_catalog(self) -> list[dict]:
        return [
            {
                "name": "gs_system_overview",
                "scope": "system",
                "is_write": False,
                "description": "Tổng quan hệ thống Global Shop Dianshang: số SP trong Kho, Từ khoá/Shop đang theo dõi, Chiến dịch & Nhật ký gần nhất.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "gs_research_keyword",
                "scope": "hunt_keywords",
                "is_write": True,
                "description": "Tra cứu từ khoá Shopee (VN/PH/SG/MY/TH) hoặc TikTokShop (VN/PH/SG/MY/TH): tổng lượng SP, lượt bán, phân bổ giá, tỷ lệ Mall/Nước ngoài & điểm Jev AI.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "keyword": {"type": "string"},
                        "platform": {
                            "type": "string",
                            "enum": [
                                "shopee_vn", "shopee_ph", "shopee_sg", "shopee_my", "shopee_th",
                                "tiktok_shop_vn", "tiktok_shop_ph", "tiktok_shop_sg", "tiktok_shop_my", "tiktok_shop_th",
                                "shopee", "tiktok_shop",
                            ],
                        },
                        "limit": {"type": "integer"},
                        "save_top_to_vault": {"type": "boolean"},
                    },
                    "required": ["keyword"],
                },
            },
            {
                "name": "gs_apify_store_search",
                "scope": "system",
                "is_write": False,
                "description": "Tìm kiếm Actor phù hợp trong Kho API Apify Store đã lưu cục bộ (theo mục tiêu goal hoặc từ khoá).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "q": {"type": "string"},
                        "goal": {"type": "string"},
                        "pay_per_use_only": {"type": "boolean"},
                        "limit": {"type": "integer"},
                    },
                },
            },
            {
                "name": "gs_apify_store_call",
                "scope": "hunt_keywords",
                "is_write": True,
                "description": "Gọi trực tiếp bất kỳ Actor nào trong Kho Apify Store theo slug hoặc theo goal mục tiêu.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "actor_slug": {"type": "string"},
                        "goal": {"type": "string"},
                        "payload": {"type": "object"},
                        "max_charge_usd": {"type": "number"},
                        "save_products_to_vault": {"type": "boolean"},
                    },
                },
            },
            {
                "name": "gs_create_watch",
                "scope": "watches",
                "is_write": True,
                "description": "Tạo theo dõi định kỳ Từ khoá (keyword), Sản phẩm (product) hoặc Shop đối thủ (shop) trên Shopee / TikTok Shop.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "watch_type": {"type": "string", "enum": ["keyword", "product", "shop"]},
                        "platform": {"type": "string", "enum": ["shopee", "tiktok_shop"]},
                        "target_key": {"type": "string"},
                        "title": {"type": "string"},
                        "run_immediately": {"type": "boolean"},
                    },
                    "required": ["watch_type", "platform", "target_key"],
                },
            },
            {
                "name": "gs_check_watch_diff",
                "scope": "watches",
                "is_write": True,
                "description": "Chạy kiểm tra ngay 1 mục theo dõi và đối chiếu xem có bao nhiêu sản phẩm mới xuất hiện / tăng lượt bán.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"watch_id": {"type": "string"}},
                    "required": ["watch_id"],
                },
            },
            {
                "name": "gs_scan_shop_products",
                "scope": "shops",
                "is_write": True,
                "description": "Quét và đánh giá danh mục sản phẩm của 1 Shop trên Shopee hoặc TikTok Shop.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "shop_query": {"type": "string"},
                        "platform": {"type": "string", "enum": ["shopee", "tiktok_shop"]},
                        "limit": {"type": "integer"},
                    },
                    "required": ["shop_query"],
                },
            },
            {
                "name": "gs_list_products",
                "scope": "products",
                "is_write": False,
                "description": "Liệt kê sản phẩm trong Kho Sản phẩm Tiềm năng theo nhóm phân loại và ngành hàng.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "bucket": {"type": "string"},
                        "industry": {"type": "string"},
                        "q": {"type": "string"},
                    },
                },
            },
            {
                "name": "gs_search_china_sourcing",
                "scope": "china_sourcing",
                "is_write": True,
                "description": "Tìm nguồn hàng sỉ trên 1688, Taobao, Pinduoduo hoặc Douyin kèm tính Giá vốn về tay (CNY -> VND).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "platform": {"type": "string", "enum": ["1688", "taobao", "pinduoduo", "douyin"]},
                        "weight_kg": {"type": "number"},
                        "linked_product_id": {"type": "integer"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "gs_list_shops",
                "scope": "shops",
                "is_write": False,
                "description": "Xem danh sách Kho Shop (Shop vận hành của mình & Shop đối thủ mẫu).",
                "inputSchema": {"type": "object", "properties": {"role": {"type": "string"}}},
            },
            {
                "name": "gs_sales_and_campaigns",
                "scope": "campaigns_sales",
                "is_write": False,
                "description": "Xem tổng hợp Chiến dịch Ngành hàng, Lượt bán, Doanh số GMV và Lợi nhuận ròng nhà bán.",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]

    def _check_auth(self, env: dict, cfg_mcp: dict) -> tuple[bool, str]:
        if not cfg_mcp.get("enabled", True):
            return False, "MCP Gateway đang tắt trong Cài đặt"
        blocked = check_host_and_origin(env, allow_tailscale=bool(cfg_mcp.get("allow_tailscale", True)))
        if blocked is not None:
            return False, blocked[1]["detail"]
        if not cfg_mcp.get("auth_required", True):
            return True, ""
        remote = (env.get("REMOTE_ADDR") or "").strip()
        if cfg_mcp.get("allow_loopback_without_token") and remote in ("127.0.0.1", "::1"):
            return True, ""
        auth_hdr = (env.get("HTTP_AUTHORIZATION") or "").strip()
        provided = auth_hdr[7:].strip() if auth_hdr.lower().startswith("bearer ") else (env.get("HTTP_X_MCP_TOKEN") or "").strip()
        expected = self.app.secrets.get("mcp.auth_token")
        if not provided or not expected or not hmac.compare_digest(provided, expected):
            return False, "Thiếu hoặc sai MCP Bearer Token"
        return True, ""

    def _exec_tool(self, name: str, args: dict) -> dict:
        if name == "gs_system_overview":
            return {
                "product": PRODUCT_NAME,
                "version": __version__,
                "vault_products": self.app.products.count_all(),
                "watches_count": len(self.app.watches.list_watches()),
                "shops_count": len(self.app.shops.list_shops()),
                "campaigns_count": len(self.app.campaigns.list_campaigns()),
                "recent_logs": self.app.history_logs.list_logs(limit=5),
            }
        if name == "gs_research_keyword":
            return self.app.keywords.research_keyword(
                keyword=args["keyword"],
                platform=args.get("platform", "shopee"),
                limit=int(args.get("limit") or 15),
                save_top_to_vault=bool(args.get("save_top_to_vault", False)),
            )
        if name == "gs_create_watch":
            return self.app.watches.create_watch(args)
        if name == "gs_check_watch_diff":
            return self.app.watches.run_watch_check(args["watch_id"], trigger_kind="mcp_agent")
        if name == "gs_scan_shop_products":
            return self.app.shops.scan_and_evaluate_shop_products(
                shop_query=args["shop_query"],
                platform=args.get("platform", "shopee"),
                limit=int(args.get("limit") or 15),
            )
        if name == "gs_list_products":
            return self.app.products.list_products(
                bucket=args.get("bucket", "all"),
                industry=args.get("industry", ""),
                q=args.get("q", ""),
                limit=30,
            )
        if name == "gs_search_china_sourcing":
            return self.app.china_sourcing.search_and_save(
                query_or_url=args["query"],
                platform=args.get("platform", "1688"),
                weight_kg=args.get("weight_kg"),
                linked_product_id=args.get("linked_product_id"),
            )
        if name == "gs_list_shops":
            return {"shops": self.app.shops.list_shops(role=args.get("role", ""))}
        if name == "gs_sales_and_campaigns":
            return {
                "campaigns": self.app.campaigns.list_campaigns(),
                "sales": self.app.campaigns.sales_summary(),
            }
        if name == "gs_apify_store_search":
            return self.app.apify_catalog.search_actors(
                q=str(args.get("q") or ""),
                goal=str(args.get("goal") or ""),
                pay_per_use_only=bool(args.get("pay_per_use_only", True)),
                limit=int(args.get("limit") or 15),
            )
        if name == "gs_apify_store_call":
            return self.app.apify_catalog.call_actor_on_demand(
                actor_slug=str(args.get("actor_slug") or ""),
                goal=str(args.get("goal") or ""),
                payload=args.get("payload") if isinstance(args.get("payload"), dict) else {},
                max_charge_usd=float(args.get("max_charge_usd") or 0.06),
                save_products_to_vault=bool(args.get("save_products_to_vault", False)),
            )
        raise ValueError(f"Tool MCP không tồn tại: {name}")

    def handle_http_mcp(self, env: dict, start_response):
        cfg = settings.read_settings(self.app.connect, self.app.secrets)
        mcp_cfg = cfg["mcp"]
        ok, err_msg = self._check_auth(env, mcp_cfg)
        if not ok:
            body = json.dumps({"error": err_msg}, ensure_ascii=False).encode("utf-8")
            start_response("401 Unauthorized", [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(body)))])
            return [body]

        method = (env.get("REQUEST_METHOD") or "GET").upper()
        if method == "GET":
            accept = (env.get("HTTP_ACCEPT") or "").lower()
            if "text/event-stream" in accept and "application/json" not in accept:
                start_response("405 Method Not Allowed", [("Content-Length", "0")])
                return [b""]
            info = json.dumps({"server": PRODUCT_NAME, "version": __version__, "protocol": "2025-03-26"}, ensure_ascii=False).encode("utf-8")
            start_response("200 OK", [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(info)))])
            return [info]

        if method == "DELETE":
            start_response("200 OK", [("Content-Length", "0")])
            return [b""]

        raw_req = self.app.read_json(env, max_bytes=1024 * 1024)
        sess_id = env.get("HTTP_MCP_SESSION_ID") or ("mcp_" + secrets.token_hex(12))
        self._sessions.add(sess_id)

        rpc_id = raw_req.get("id")
        rpc_method = str(raw_req.get("method") or "")
        params = raw_req.get("params") or {}

        if rpc_id is None:
            start_response("202 Accepted", [("Mcp-Session-Id", sess_id), ("Content-Length", "0")])
            return [b""]

        t0 = time.monotonic()
        enabled_scopes = set(mcp_cfg.get("enabled_scopes") or [])
        read_only = mcp_cfg.get("access_mode") == "read_only"

        try:
            if rpc_method == "initialize":
                res_obj = {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "global-shop-dianshang", "version": __version__},
                }
            elif rpc_method == "tools/list":
                visible = [
                    {"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]}
                    for t in self._tools_catalog()
                    if t["scope"] in enabled_scopes and not (read_only and t["is_write"])
                ]
                res_obj = {"tools": visible}
            elif rpc_method == "tools/call":
                tname = str(params.get("name") or "")
                tmeta = next((t for t in self._tools_catalog() if t["name"] == tname), None)
                if not tmeta or tmeta["scope"] not in enabled_scopes:
                    raise PermissionError(f"Tool {tname} bị khoá hoặc ngoài phạm vi cho phép")
                if read_only and tmeta["is_write"]:
                    raise PermissionError(f"Chế độ Read-Only không cho phép gọi {tname}")
                out = self._exec_tool(tname, params.get("arguments") or {})
                res_obj = {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}], "isError": False}
                dur_call_ms = int((time.monotonic() - t0) * 1000)
                if mcp_cfg.get("audit_log_enabled", True):
                    with self.app.connect() as conn:
                        conn.execute(
                            "INSERT INTO mcp_call_logs (session_id, remote_addr, rpc_method, tool_name, scope, is_write, status, duration_ms, error_text, created_at) VALUES (?, ?, ?, ?, ?, ?, 'ok', ?, '', ?)",
                            (sess_id, env.get("REMOTE_ADDR", ""), rpc_method, tname, tmeta["scope"], int(tmeta["is_write"]), dur_call_ms, now()),
                        )
                if getattr(self.app, "history_logs", None) is not None:
                    sum_txt = str(out.get("summary") if isinstance(out, dict) and out.get("summary") else f"Thực thi MCP tool {tname} thành công")[:260]
                    self.app.history_logs.record_event(
                        module="mcp",
                        action_type=f"mcp:{tname}",
                        title=f"MCP Agent gọi tool: {tname}",
                        status="completed",
                        duration_ms=dur_call_ms,
                        summary=sum_txt,
                        payload={"tool": tname, "scope": tmeta["scope"], "is_write": bool(tmeta["is_write"])},
                        notify_telegram=True,
                    )
            elif rpc_method == "ping":
                res_obj = {}
            else:
                raise ValueError(f"Phương thức JSON-RPC chưa hỗ trợ: {rpc_method}")
            resp = {"jsonrpc": "2.0", "id": rpc_id, "result": res_obj}
        except Exception as exc:
            resp = {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32000, "message": str(exc)}}

        body = json.dumps(resp, ensure_ascii=False).encode("utf-8")
        start_response(
            "200 OK",
            [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Mcp-Session-Id", sess_id),
                ("Content-Length", str(len(body))),
            ],
        )
        return [body]

    def dispatch(self, path: str, method: str, env, read_json):
        if path == "/api/mcp/status" and method == "GET":
            cfg = settings.read_settings(self.app.connect, self.app.secrets)
            with self.app.connect() as conn:
                calls = [dict(r) for r in conn.execute("SELECT * FROM mcp_call_logs ORDER BY id DESC LIMIT 20").fetchall()]
            return "200 OK", {
                "enabled": cfg["mcp"]["enabled"],
                "access_mode": cfg["mcp"]["access_mode"],
                "http_endpoint": f"http://127.0.0.1:{self.web_port}/mcp",
                "tailscale_endpoint": self.app.telegram_bot.remote_url("/mcp"),
                "tools_count": len(self._tools_catalog()),
                "recent_calls": calls,
            }
        if path == "/api/mcp/rotate-token" and method == "POST":
            new_tok = "gs_mcp_" + secrets.token_hex(18)
            self.app.secrets.set("mcp.auth_token", new_tok)
            return "200 OK", {"rotated": True, "masked": settings.mask(new_tok), "summary": "Đã xoay mã MCP Bearer Token mới"}
        if path == "/api/mcp/reveal-snippets" and method == "POST":
            body = json_object(read_json, env)
            if not body.get("confirm"):
                raise ValueError("Cần xác nhận confirm=true để hiển thị cấu hình MCP")
            tok = settings.ensure_mcp_token(self.app.secrets)
            return "200 OK", {
                "http_url": f"http://127.0.0.1:{self.web_port}/mcp",
                "tailscale_url": self.app.telegram_bot.remote_url("/mcp"),
                "bearer_token": tok,
            }
        return None
