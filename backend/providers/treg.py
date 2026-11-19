"""Treg.to multi-provider routing client (Priority #2 failover + JustOneAPI 1688/Taobao/Douyin/TikTok Shop)."""
import json
import urllib.error
import urllib.parse
import urllib.request

from ..responses import safe_id_str
from .apify import parse_int_metric, parse_vnd_price


class TregError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


class TregClient:
    BASE_URL = "https://treg.to"

    def __init__(self, http_opener=None):
        self._opener = http_opener or urllib.request.urlopen

    def check_account(self, token: str) -> dict:
        tok = (token or "").strip()
        if not tok:
            raise TregError("Chưa cấu hình Treg API Key", status=400)
        # Try MCP balance endpoint first
        try:
            init_req = urllib.request.Request(
                f"{self.BASE_URL}/mcp/",
                data=json.dumps({
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "global-shop-dianshang", "version": "1.0.1"},
                    },
                }).encode("utf-8"),
                headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
                method="POST",
            )
            with self._opener(init_req, timeout=12) as r1:
                sess_id = r1.headers.get("Mcp-Session-Id") or ""
            bal_headers = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
            if sess_id:
                bal_headers["Mcp-Session-Id"] = sess_id
            bal_req = urllib.request.Request(
                f"{self.BASE_URL}/mcp/",
                data=json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "balance", "arguments": {}}}).encode("utf-8"),
                headers=bal_headers,
                method="POST",
            )
            with self._opener(bal_req, timeout=12) as r2:
                raw_txt = r2.read().decode("utf-8", errors="replace")
                for line in raw_txt.splitlines():
                    s = line.removeprefix("data:").strip()
                    if s.startswith("{"):
                        obj = json.loads(s)
                        content = ((obj.get("result") or {}).get("content") or [{}])[0].get("text") or "{}"
                        info = json.loads(content) if content.strip().startswith("{") else {"raw": content}
                        return {"ok": True, "balance": info}
        except Exception:
            pass
        cat = self.catalog_search(tok, "tiktok", limit=1)
        return {"ok": True, "catalog_total": cat.get("total", 0)}

    def catalog_search(self, token: str, query: str, limit: int = 10) -> dict:
        tok = (token or "").strip()
        if not tok:
            raise TregError("Chưa cấu hình Treg API Key", status=400)
        qs = urllib.parse.urlencode({"q": query, "limit": max(1, min(25, int(limit)))})
        req = urllib.request.Request(
            f"{self.BASE_URL}/catalog/search?{qs}",
            headers={"X-Treg-Token": tok, "User-Agent": "GlobalShopDianshang/1.0"},
        )
        try:
            with self._opener(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise TregError(f"Treg HTTP {exc.code}", status=exc.code) from None
        except Exception as exc:
            raise TregError(f"Lỗi mạng Treg: {exc}") from None

    def call(
        self,
        token: str,
        endpoint_id: str,
        payload: dict | None = None,
        method: str = "POST",
        max_cost_usd: float = 0.03,
        timeout: int = 42,
    ) -> dict:
        tok = (token or "").strip()
        if not tok:
            raise TregError("Chưa cấu hình Treg API Key", status=400)
        cap = max(0.001, min(0.50, float(max_cost_usd)))
        url = f"{self.BASE_URL}/call/{endpoint_id}"
        headers = {
            "X-Treg-Token": tok,
            "X-Treg-Route-Max-Cost": f"{cap:.4f}",
            "User-Agent": "GlobalShopDianshang/1.0",
        }
        data = None
        if method.upper() == "GET":
            if payload:
                url += "?" + urllib.parse.urlencode({k: v for k, v in payload.items() if v is not None})
        else:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload or {}).encode("utf-8")

        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with self._opener(req, timeout=timeout) as resp:
                cost_micro = resp.headers.get("x-treg-cost-micro")
                cost_usd = (float(cost_micro) / 1_000_000.0) if (cost_micro and cost_micro.isdigit()) else None
                body = json.loads(resp.read().decode("utf-8"))
                if isinstance(body, dict):
                    body["_cost_usd"] = cost_usd
                    body["_served_by"] = resp.headers.get("x-treg-served-by") or endpoint_id
                    return body
                return {"items": body, "_cost_usd": cost_usd, "_served_by": endpoint_id}
        except urllib.error.HTTPError as exc:
            err_txt = exc.read().decode("utf-8", errors="replace")[:200]
            raise TregError(f"Treg {endpoint_id} HTTP {exc.code}: {err_txt}", status=exc.code) from None
        except Exception as exc:
            raise TregError(f"Treg {endpoint_id} lỗi mạng: {exc}") from None

    @staticmethod
    def _extract_list(res: dict) -> list[dict]:
        for k in ("items", "results", "products", "data", "list", "videos"):
            v = res.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
            if isinstance(v, dict):
                for sk in ("items", "products", "list", "goods_list", "item_list", "videos"):
                    sv = v.get(sk)
                    if isinstance(sv, list):
                        return [x for x in sv if isinstance(x, dict)]
        return []

    # --- TikTok Shop & Videos Failover ---------------------------------------

    def search_tiktok_shop(self, token: str, query: str, limit: int = 12, max_cost_usd: float = 0.03) -> tuple[str, list[dict], float | None]:
        endpoints = [
            ("scrapecreators.x.v1-tiktok-shop-search", {"query": query, "region": "VN"}, "GET"),
            ("justoneapi.x.tiktok-shop-search-products-v1", {"keyword": query, "country": "VN"}, "GET"),
        ]
        last_err = None
        for ep, params, mth in endpoints:
            try:
                res = self.call(token, ep, params, method=mth, max_cost_usd=max_cost_usd)
                rows = self._extract_list(res)
                if rows:
                    out = []
                    for r in rows[:limit]:
                        pid = safe_id_str(r.get("product_id") or r.get("id"))
                        p = parse_vnd_price(r.get("sale_price_format") or r.get("price") or 0, "VND")
                        sold = parse_int_metric(r.get("sold_count") or r.get("sales") or 0)
                        out.append({
                            "platform": "tiktok_shop",
                            "market": "VN",
                            "native_product_id": pid,
                            "native_shop_id": safe_id_str(r.get("seller_id") or r.get("shop_id")),
                            "shop_name": str(r.get("seller_name") or r.get("shop_name") or ""),
                            "is_mall": bool(r.get("is_mall")),
                            "title": str(r.get("title") or r.get("name") or "").strip(),
                            "price_vnd": p,
                            "sold_count": sold,
                            "gmv_vnd": round(p * sold, 0),
                            "rating": float(r.get("rating") or 0.0),
                            "url": str(r.get("url") or (f"https://shop.tiktok.com/view/product/{pid}?region=VN" if pid else "")),
                            "image_url": str(r.get("cover") or r.get("image") or ""),
                        })
                    return ep, out, res.get("_cost_usd")
            except Exception as exc:
                last_err = exc
        if last_err:
            raise last_err
        return "treg", [], 0.0

    def search_china_sourcing(
        self,
        token: str,
        platform: str,
        query_or_url: str,
        limit: int = 10,
        max_cost_usd: float = 0.03,
    ) -> tuple[str, list[dict], float | None]:
        plat = platform.lower().strip()
        is_url = query_or_url.strip().startswith("http")
        if is_url:
            res = self.call(token, "treg.web.extract", {"url": query_or_url}, method="POST", max_cost_usd=max_cost_usd)
            title = str(res.get("title") or query_or_url)[:200]
            return "treg.web.extract", [{
                "platform": plat,
                "native_item_id": "",
                "title": title,
                "price_cny": 0.0,
                "moq": 1,
                "supplier_name": "",
                "sales_volume": "",
                "item_url": query_or_url,
                "image_url": "",
            }], res.get("_cost_usd")

        ep_map = {
            "1688": ("justoneapi.x.1688-search-item-list-v1", {"keyword": query_or_url, "page": 1}, "GET"),
            "taobao": ("justoneapi.x.taobao-search-item-list-v1", {"keyword": query_or_url, "page": 1}, "GET"),
            "douyin": ("justoneapi.x.douyin-ec-search-item-list-v1", {"keyword": query_or_url, "page": 1}, "GET"),
        }
        if plat in ep_map:
            ep, params, mth = ep_map[plat]
            res = self.call(token, ep, params, method=mth, max_cost_usd=max_cost_usd)
            rows = self._extract_list(res)
            out = []
            for r in rows[:limit]:
                iid = safe_id_str(r.get("item_id") or r.get("offerId") or r.get("num_iid") or r.get("product_id") or r.get("id"))
                price_cny = parse_vnd_price(r.get("price") or r.get("promotion_price") or r.get("wholesale_price") or 0, "CNY")
                url = str(r.get("detail_url") or r.get("item_url") or r.get("url") or "").strip()
                if url.startswith("//"):
                    url = "https:" + url
                if not url and iid:
                    url = f"https://detail.1688.com/offer/{iid}.html" if plat == "1688" else f"https://item.taobao.com/item.htm?id={iid}"
                img = str(r.get("pic_url") or r.get("img") or r.get("image") or "").strip()
                if img.startswith("//"):
                    img = "https:" + img
                out.append({
                    "platform": plat,
                    "native_item_id": iid,
                    "title": str(r.get("title") or r.get("subject") or r.get("name") or "").strip(),
                    "price_cny": price_cny,
                    "moq": max(1, parse_int_metric(r.get("moq") or r.get("begin_amount") or 1)),
                    "supplier_name": str(r.get("seller_nick") or r.get("shop_title") or r.get("company_name") or ""),
                    "sales_volume": str(r.get("sales") or r.get("deal_cnt") or r.get("volume") or ""),
                    "item_url": url,
                    "image_url": img,
                })
            return ep, out, res.get("_cost_usd")

        # Pinduoduo / generic SERP fallback
        serp_q = f"site:yangkeduo.com {query_or_url}" if plat == "pinduoduo" else f"{plat} {query_or_url}"
        res = self.call(token, "treg.google.serp.organic", {"q": serp_q, "num": limit}, method="POST", max_cost_usd=max_cost_usd)
        rows = self._extract_list(res)
        out = [
            {
                "platform": plat,
                "native_item_id": "",
                "title": str(r.get("title") or "").strip(),
                "price_cny": 0.0,
                "moq": 1,
                "supplier_name": plat.upper(),
                "sales_volume": str(r.get("snippet") or "")[:80],
                "item_url": str(r.get("link") or r.get("url") or ""),
                "image_url": "",
            }
            for r in rows[:limit]
            if r.get("title")
        ]
        return "treg.google.serp.organic", out, res.get("_cost_usd")

    def inspect_tiktok_video(self, token: str, video_url: str, max_cost_usd: float = 0.025) -> dict:
        return self.call(token, "treg.tiktok.video.detail", {"url": video_url}, method="POST", max_cost_usd=max_cost_usd)

    def fetch_tiktok_transcript(self, token: str, video_url: str, max_cost_usd: float = 0.02) -> dict:
        return self.call(token, "scrapecreators.x.v1-tiktok-video-transcript", {"url": video_url}, method="GET", max_cost_usd=max_cost_usd)

    def fetch_google_trends(self, token: str, keyword: str, geo: str = "VN", max_cost_usd: float = 0.025) -> dict:
        return self.call(token, "treg.google.keywords.ideas", {"keyword": keyword, "country": geo}, method="POST", max_cost_usd=max_cost_usd)
