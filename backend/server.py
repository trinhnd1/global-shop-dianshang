"""Main WSGI API application and bounded multi-threaded HTTP server for Global Shop Dianshang."""
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
from socketserver import ThreadingMixIn
import sqlite3
import threading
import time
from urllib.parse import parse_qs
from wsgiref.simple_server import ServerHandler, WSGIRequestHandler, WSGIServer

from . import PRODUCT_NAME, get_build_info, settings
from .campaigns_and_sales import CampaignsAndSalesService, DailyBriefingDaemon
from .china_sourcing import ChinaSourcingService
from .chrome_profile_hub import DedicatedChromeHub
from .desk_pipeline import DeskProductWorkflowService
from .history_log import HistoryLogService
from .hunt import HuntAndCreatorsService
from .jobs import JobManager
from .keywords import KeywordResearchService
from .ledger import CostLedger
from .mcp_gateway import McpGatewayService
from .migrations import current_schema_version, run_migrations
from .products import ProductsService
from .providers.apify import ApifyClient, ApifyError
from .providers.desk300plus import Desk300PlusClient
from .providers.jev import JevClient, JevError
from .providers.treg import TregClient, TregError
from .responses import ApiError, Raw, check_host_and_origin, json_object, text
from .secret_store import SecretStore, create_secret_store
from .shops import ShopsService
from .spy_and_video import SpyAndVideoService
from .telegram_bot import TelegramBotService
from .watches import WatchSchedulerDaemon, WatchesService


class LocalHTTPServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True
    block_on_close = False
    request_queue_size = 24

    def __init__(self, *args, **kwargs):
        self.request_slots = threading.BoundedSemaphore(24)
        super().__init__(*args, **kwargs)

    def get_request(self):
        sock, address = super().get_request()
        sock.settimeout(240)
        return sock, address

    def process_request(self, request, client_address):
        if not self.request_slots.acquire(blocking=False):
            try:
                request.sendall(b"HTTP/1.0 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.request_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.request_slots.release()


class LocalRequestHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        pass

    def handle(self):
        self.raw_requestline = self.rfile.readline(65537)
        if len(self.raw_requestline) > 65536:
            self.requestline = self.request_version = self.command = ""
            self.send_error(414)
            return
        if not self.parse_request():
            return
        handler = ServerHandler(self.rfile, self.wfile, self.get_stderr(), self.get_environ(), multithread=True)
        handler.request_handler = self
        handler.run(self.server.get_app())


class Application:
    def __init__(
        self,
        data_dir: str | Path,
        allow_tailscale: bool = True,
        secret_store: SecretStore | None = None,
        prefer_keychain: bool = True,
        telegram_http_runner=None,
        web_port: int = 8999,
    ):
        self.root = Path(data_dir)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.allow_tailscale = allow_tailscale
        self.web_port = web_port
        self.db = self.root / "backend.sqlite3"
        self.migration_state = run_migrations(self.root)
        if os.name == "posix" and self.db.exists():
            self.db.chmod(0o600)

        self.secrets = secret_store or create_secret_store(self.root, prefer_keychain=prefer_keychain)
        settings.ensure_mcp_token(self.secrets)

        self.apify = ApifyClient()
        self.treg = TregClient()
        self.jev = JevClient()
        self.desk300 = Desk300PlusClient()
        self.ledger = CostLedger(self.connect)
        self.jobs = JobManager(self.connect, ledger=self.ledger)
        self.history_logs = HistoryLogService(self.connect)
        self.jobs.history_sink = self.history_logs

        self.telegram_bot = TelegramBotService(
            self.connect,
            self.secrets,
            self.history_logs,
            web_port=web_port,
            http_runner=telegram_http_runner,
        )
        self.history_logs.telegram_sink = self.telegram_bot

        self.chrome_hub = DedicatedChromeHub(self.root, connect=self.connect)
        self.products = ProductsService(
            self.connect,
            self.secrets,
            jev_client=self.jev,
            jobs=self.jobs,
            ledger=self.ledger,
            apify=self.apify,
            treg=self.treg,
        )
        self.history_logs.jobs_service = self.jobs
        self.history_logs.products_service = self.products
        self.keywords = KeywordResearchService(self.connect, self.secrets, self.products, apify=self.apify, treg=self.treg, jev=self.jev)
        self.shops = ShopsService(self.connect, self.secrets, self.products, apify=self.apify, treg=self.treg, jev=self.jev)
        self.products.shops_service = self.shops
        self.watches = WatchesService(
            self.connect,
            self.secrets,
            self.products,
            self.keywords,
            self.shops,
            apify=self.apify,
            treg=self.treg,
            telegram_bot=self.telegram_bot,
        )
        self.watch_scheduler = WatchSchedulerDaemon(self.watches)
        self.china_sourcing = ChinaSourcingService(self.connect, self.secrets, self.products, apify=self.apify, treg=self.treg, jev=self.jev)
        self.china_sourcing.desk300 = self.desk300
        self.desk_pipeline = DeskProductWorkflowService(
            self.connect,
            self.secrets,
            self.root,
            self.products,
            shops=self.shops,
            jobs=self.jobs,
            apify=self.apify,
            treg=self.treg,
            jev=self.jev,
            desk300=self.desk300,
        )
        self.products.desk_pipeline = self.desk_pipeline
        self.hunt = HuntAndCreatorsService(self.connect, self.secrets, self.products, self.jobs, apify=self.apify, treg=self.treg, jev=self.jev)
        self.hunt.desk300 = self.desk300
        self.hunt.desk_pipeline = self.desk_pipeline
        self.spy_video = SpyAndVideoService(
            self.connect,
            self.secrets,
            self.root,
            self.products,
            self.china_sourcing,
            apify=self.apify,
            treg=self.treg,
            jev=self.jev,
        )
        self.campaigns = CampaignsAndSalesService(self.connect, self.secrets, self.products, self.shops, telegram_bot=self.telegram_bot)
        self.products.campaigns_service = self.campaigns
        self.daily_brief_daemon = DailyBriefingDaemon(self.campaigns)
        self.mcp_gateway = McpGatewayService(self, web_port=web_port)

        self.telegram_bot.products_service = self.products
        self.telegram_bot.watches_service = self.watches

        self.handlers = [
            self.mcp_gateway,
            self.desk_pipeline,
            self.products,
            self.keywords,
            self.shops,
            self.watches,
            self.china_sourcing,
            self.hunt,
            self.spy_video,
            self.campaigns,
            self.chrome_hub,
            self.jobs,
            self.ledger,
            self.history_logs,
        ]

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def read_json(env, max_bytes: int = 262144):
        try:
            size = int(env.get("CONTENT_LENGTH") or 0)
        except ValueError:
            raise ValueError("Content-Length không hợp lệ") from None
        if size < 0 or size > max_bytes:
            raise OverflowError()
        raw = env["wsgi.input"].read(size) if size > 0 else b"{}"

        def reject_constant(_val):
            raise ValueError("Số JSON không hợp lệ")

        def finite_float(val):
            res = float(val)
            if not math.isfinite(res):
                raise ValueError("Số JSON không hữu hạn")
            return res

        try:
            parsed = json.loads(raw, parse_constant=reject_constant, parse_float=finite_float)
            env["_gs_parsed_json"] = parsed
            return parsed
        except (ValueError, UnicodeError, RecursionError):
            raise ValueError("Body JSON không hợp lệ") from None

    def __call__(self, env, start_response):
        path = env.get("PATH_INFO", "") or "/"
        if path in ("/mcp", "/mcp/"):
            return self.mcp_gateway.handle_http_mcp(env, start_response)
        try:
            status, result = self.dispatch(env)
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
                raise
            status, result = "503 Service Unavailable", {"detail": "Cơ sở dữ liệu đang bận, thử lại sau giây lát"}
        if isinstance(result, Raw):
            start_response(status, result.headers)
            return [result.body]
        body = json.dumps(result, ensure_ascii=False).encode("utf-8")
        start_response(
            status,
            [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Content-Length", str(len(body))),
                ("Cache-Control", "no-store"),
            ],
        )
        return [body]

    def _handle_providers(self, path: str, method: str, env):
        cur = settings.read_settings(self.connect, self.secrets)
        prov = cur["providers"]

        if path.startswith("/api/providers/telegram/"):
            return self.telegram_bot.dispatch(path, method, env, self.read_json)

        if path == "/api/providers/treg/check" and method == "POST":
            body = json_object(self.read_json, env)
            tok = settings.resolve_incoming_secret(body.get("treg_key") or "", prov.get("treg_key", ""), "Treg API Key")
            try:
                return "200 OK", self.treg.check_account(tok)
            except TregError as exc:
                return "502 Bad Gateway", {"detail": str(exc)}

        if path == "/api/providers/treg/catalog" and method == "GET":
            qs = parse_qs(env.get("QUERY_STRING") or "")
            q = (qs.get("q") or ["1688"])[0][:120]
            try:
                return "200 OK", self.treg.catalog_search(prov.get("treg_key", ""), q, limit=12)
            except TregError as exc:
                return "502 Bad Gateway", {"detail": str(exc)}

        if path == "/api/providers/apify/keys" and method == "POST":
            body = json_object(self.read_json, env)
            lbl = text(body.get("label") or "Apify Key", "label", 80)
            tok = text(body.get("token"), "token", 300, required=True)
            return "200 OK", settings.add_apify_key(self.connect, self.secrets, lbl, tok, make_primary=bool(body.get("make_primary", False)))

        if path.startswith("/api/providers/apify/keys/"):
            parts = path.split("/")
            kid = parts[5] if len(parts) >= 6 else ""
            try:
                if len(parts) == 6 and method == "DELETE":
                    return "200 OK", settings.update_apify_key(self.connect, self.secrets, kid, "delete")
                if len(parts) == 7 and method == "POST" and parts[6] in ("promote", "toggle"):
                    return "200 OK", settings.update_apify_key(self.connect, self.secrets, kid, parts[6])
            except KeyError as exc:
                raise ApiError("404 Not Found", str(exc)) from None

        if path == "/api/providers/apify/check" and method == "POST":
            entries = prov.get("apify_keys") or []
            if not entries:
                raise ApiError("400 Bad Request", "Chưa có Apify Key nào — hãy thêm key trước")
            try:
                return "200 OK", self.apify.check_key_ring(entries)
            except ApifyError as exc:
                return "502 Bad Gateway", {"detail": str(exc)}

        if path == "/api/providers/jev/check" and method == "POST":
            body = json_object(self.read_json, env)
            key = settings.resolve_incoming_secret(body.get("typesafe_key") or "", prov.get("typesafe_key", ""), "TypeSafe Jev API Key")
            model = (body.get("jev_model") or prov.get("jev_model") or "jev-1.14.0").strip()
            base_url = (body.get("jev_base_url") or prov.get("jev_base_url") or "").strip()
            try:
                return "200 OK", self.jev.test_connection(key, model=model, base_url=base_url)
            except JevError as exc:
                return "502 Bad Gateway", {"detail": str(exc)}
        return None

    def dispatch(self, env):
        blocked = check_host_and_origin(env, allow_tailscale=self.allow_tailscale)
        if blocked is not None:
            return blocked

        t0 = time.monotonic()
        status, result = self._dispatch_inner(env)
        dur_ms = int((time.monotonic() - t0) * 1000)
        try:
            self.history_logs.record_http_action(
                method=env.get("REQUEST_METHOD", "GET"),
                path=env.get("PATH_INFO", "") or "/",
                query_string=env.get("QUERY_STRING", "") or "",
                http_status=status,
                duration_ms=dur_ms,
                req_body=env.get("_gs_parsed_json"),
                res_body=result,
            )
        except Exception:
            pass
        return status, result

    def _dispatch_inner(self, env):
        path = env.get("PATH_INFO", "") or "/"
        method = env.get("REQUEST_METHOD", "GET")

        try:
            if path == "/api/health" and method == "GET":
                return "200 OK", {
                    "status": "ok",
                    "product": PRODUCT_NAME,
                    **get_build_info(),
                    "schema_version": current_schema_version(self.db),
                    "secret_backend": self.secrets.backend_name,
                    "tailscale_url": self.telegram_bot.remote_url(),
                }
            if path == "/api/version" and method == "GET":
                return "200 OK", {
                    **get_build_info(),
                    "product": PRODUCT_NAME,
                    "schema_version": current_schema_version(self.db),
                }
            if path == "/api/overview" and method == "GET":
                sc = self.shops.summary_counts()
                return "200 OK", {
                    "vault_products": self.products.count_all(),
                    "watches_count": len(self.watches.list_watches()),
                    "shops_count": sc["total_count"],
                    "my_shops_count": sc["own_count"],
                    "competitor_shops_count": sc["competitor_count"],
                    "sourcing_count": len(self.china_sourcing.list_items(limit=200)),
                    "desk300_runs_count": len(self.desk_pipeline.list_runs(limit=100)),
                    "campaigns_count": len(self.campaigns.list_campaigns()),
                    "sales": self.campaigns.sales_summary()["seller_kpis"],
                    "recent_logs": self.history_logs.list_logs(limit=6),
                }
            if path == "/api/settings":
                if method == "GET":
                    return "200 OK", settings.masked_view(self.connect, self.secrets)
                if method == "POST":
                    return "200 OK", settings.save_settings_masked(self.connect, self.secrets, self.read_json(env))
                return "405 Method Not Allowed", {"detail": "Phương thức không hợp lệ"}

            if path.startswith("/api/providers/"):
                res = self._handle_providers(path, method, env)
                if res is not None:
                    return res

            for handler in self.handlers:
                routed = handler.dispatch(path, method, env, self.read_json)
                if routed is not None:
                    return routed

            return "501 Not Implemented", {"detail": f"Chưa hỗ trợ endpoint: {method} {path}"}
        except ApiError as exc:
            return exc.status, {"detail": exc.message}
        except OverflowError:
            return "413 Payload Too Large", {"detail": "Dung lượng dữ liệu gửi lên quá lớn"}
        except ValueError as exc:
            return "400 Bad Request", {"detail": str(exc) or "Yêu cầu không hợp lệ"}
