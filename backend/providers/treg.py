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

    @staticmethod
    def _parse_tiktok_price_obj(p_obj) -> float:
        if p_obj is None:
            return 0.0
        if isinstance(p_obj, dict):
            for k in (
                "sale_price_format",
                "real_price",
                "sale_price_decimal",
                "price_str",
                "formatted_price",
                "origin_price_format",
                "sale_price",
                "price",
            ):
                val = p_obj.get(k)
                if val is not None and str(val).strip() not in ("", "0", "1"):
                    parsed = parse_vnd_price(val, "VND")
                    if parsed >= 1000:
                        return parsed
            return 0.0
        return parse_vnd_price(p_obj, "VND")

    @staticmethod
    def _parse_tiktok_img(r: dict) -> str:
        for k in ("image", "cover", "thumbnail", "main_image", "images"):
            raw = r.get(k)
            if isinstance(raw, dict):
                ulist = raw.get("url_list") or raw.get("thumb_url_list") or []
                if isinstance(ulist, list) and ulist and str(ulist[0]).startswith("http"):
                    return str(ulist[0])
                if isinstance(raw.get("url"), str) and raw["url"].startswith("http"):
                    return raw["url"]
            elif isinstance(raw, list) and raw:
                f0 = raw[0]
                if isinstance(f0, dict):
                    ulist = f0.get("url_list") or f0.get("thumb_url_list") or []
                    if isinstance(ulist, list) and ulist and str(ulist[0]).startswith("http"):
                        return str(ulist[0])
                    if isinstance(f0.get("url"), str) and f0["url"].startswith("http"):
                        return f0["url"]
                elif isinstance(f0, str) and f0.startswith("http"):
                    return f0
            elif isinstance(raw, str) and raw.startswith("http"):
                return raw
        return ""

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
                        p = self._parse_tiktok_price_obj(r.get("product_price_info") or r.get("price") or r.get("sale_price_format"))
                        sold_info = r.get("sold_info") if isinstance(r.get("sold_info"), dict) else (r.get("sales") if isinstance(r.get("sales"), dict) else {})
                        sold = parse_int_metric(
                            r.get("sold_count")
                            if r.get("sold_count") is not None
                            else (sold_info.get("sold_count") or r.get("sales_count") or r.get("volume") or 0)
                        )
                        seller_obj = r.get("seller") if isinstance(r.get("seller"), dict) else {}
                        shop_name = str(r.get("seller_name") or r.get("shop_name") or seller_obj.get("name") or "")
                        shop_id = safe_id_str(r.get("seller_id") or r.get("shop_id") or seller_obj.get("seller_id"))
                        rating_val = r.get("product_rating") if r.get("product_rating") is not None else (r.get("rating") or 0.0)
                        out.append({
                            "platform": "tiktok_shop",
                            "market": "VN",
                            "native_product_id": pid,
                            "native_shop_id": shop_id,
                            "shop_name": shop_name,
                            "is_mall": bool(r.get("is_mall") or seller_obj.get("is_mall")),
                            "title": str(r.get("title") or r.get("name") or "").strip(),
                            "price_vnd": p,
                            "sold_count": sold,
                            "gmv_vnd": round(p * sold, 0),
                            "rating": float(rating_val or 0.0) if isinstance(rating_val, (int, float, str)) and str(rating_val).replace(".", "", 1).isdigit() else 0.0,
                            "url": str(r.get("url") or (f"https://shop.tiktok.com/view/product/{pid}?region=VN" if pid else "")),
                            "image_url": self._parse_tiktok_img(r),
                        })
                    return ep, out, res.get("_cost_usd")
            except Exception as exc:
                last_err = exc
        if last_err:
            raise last_err
        return "treg", [], 0.0

    def fetch_tiktok_shop_product_detail(self, token: str, product_id: str, region: str = "VN", max_cost_usd: float = 0.008) -> dict | None:
        pid = safe_id_str(product_id)
        if not pid:
            return None
        res = None
        for ep in ("tikhub.x.tiktok-shop-web-fetch-product-detail-v3", "tikhub.x.tiktok-shop-web-fetch-product-detail"):
            try:
                res = self.call(token, ep, {"product_id": pid, "region": region}, method="GET", max_cost_usd=max_cost_usd, timeout=24)
                break
            except Exception:
                continue
        if not res:
            return None
        outer = (res.get("data") or {}).get("data") if isinstance(res.get("data"), dict) else {}
        if not isinstance(outer, dict):
            outer = {}
        p_data = outer.get("product_data") if isinstance(outer.get("product_data"), dict) else {}
        p_cfg = p_data.get("page_config") if isinstance(p_data.get("page_config"), dict) else {}
        inner = outer.get("data") if isinstance(outer.get("data"), dict) else {}
        comps = p_cfg.get("components_map") if isinstance(p_cfg.get("components_map"), list) else (inner.get("components_map") if isinstance(inner.get("components_map"), list) else [])

        title = ""
        price_vnd = 0.0
        sold_count = 0
        rating = 0.0
        shop_name = ""
        shop_id = ""
        image_url = ""
        for comp in comps:
            cd = comp.get("component_data") if isinstance(comp, dict) else None
            if not isinstance(cd, dict):
                continue
            p_info = cd.get("product_info") if isinstance(cd.get("product_info"), dict) else cd
            if p_info.get("title") or p_info.get("product_title") or p_info.get("name"):
                title = str(p_info.get("title") or p_info.get("product_title") or p_info.get("name") or title).strip()
            if price_vnd <= 0 and p_info.get("price"):
                price_vnd = self._parse_tiktok_price_obj(p_info.get("price"))
            if price_vnd <= 0 and isinstance(p_info.get("skus"), list):
                sku_ps = [self._parse_tiktok_price_obj(sk.get("price")) for sk in p_info["skus"] if isinstance(sk, dict) and sk.get("price")]
                sku_ps = [x for x in sku_ps if x > 0]
                if sku_ps:
                    price_vnd = min(sku_ps)
            if sold_count <= 0 and p_info.get("sold_count") is not None:
                sold_count = parse_int_metric(p_info.get("sold_count"))
            if rating <= 0:
                rc = p_info.get("rating") or (p_info.get("review") or {}).get("product_rating")
                if rc:
                    try:
                        rating = round(float(rc), 2)
                    except Exception:
                        pass
            seller_obj = p_info.get("seller") if isinstance(p_info.get("seller"), dict) else (cd.get("seller_info") if isinstance(cd.get("seller_info"), dict) else {})
            if seller_obj:
                shop_name = shop_name or str(seller_obj.get("name") or seller_obj.get("shop_name") or "")
                shop_id = shop_id or safe_id_str(seller_obj.get("seller_id") or "")
            if not image_url:
                image_url = self._parse_tiktok_img(p_info)
        if not title and price_vnd <= 0 and sold_count <= 0:
            return None
        return {
            "platform": "tiktok_shop",
            "market": region,
            "native_product_id": pid,
            "native_shop_id": shop_id,
            "shop_name": shop_name,
            "title": title,
            "price_vnd": price_vnd,
            "sold_count": sold_count,
            "gmv_vnd": round(price_vnd * sold_count, 0),
            "rating": rating,
            "image_url": image_url,
            "url": f"https://shop.tiktok.com/view/product/{pid}?region={region}",
            "_cost_usd": res.get("_cost_usd"),
        }

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

    def explore_google_trends(
        self,
        token: str,
        seed_terms: list[str],
        geo: str = "VN",
        time_range: str = "today 3-m",
        max_keywords: int = 16,
        max_cost_usd: float = 0.025,
    ) -> dict:
        """Backup Google Trends & Buyer-Intent Keyword Explorer via Treg (`treg.google.keywords.trends` + `ideas` + `serpapi.x.google-trends`)."""
        seeds = [str(s).strip().lstrip("#").strip()[:120] for s in (seed_terms or []) if str(s or "").strip()][:5]
        if not seeds:
            raise TregError("Vui lòng nhập ít nhất 1 từ khoá gốc", status=400)
        cc = (geo or "VN").strip().upper()
        lang = "vi" if cc == "VN" else "en"
        total_cost = 0.0
        endpoints_used: list[str] = []
        seed_summaries: list[dict] = []
        kw_map: dict[str, dict] = {}

        def _upsert_kw(term_txt: str, kind: str, seed_parent: str, growth_label: str = "", growth_pct: float | None = None, interest_score: float | None = None):
            t_clean = str(term_txt or "").strip()
            if not t_clean:
                return
            k_low = t_clean.lower()
            rank_order = {"rising": 3, "seed": 2, "top": 1}
            ex = kw_map.get(k_low)
            if ex:
                if rank_order.get(kind, 0) > rank_order.get(ex["kind"], 0):
                    ex["kind"] = kind
                if growth_label and not ex.get("growth_label"):
                    ex["growth_label"] = growth_label
                return
            kw_map[k_low] = {
                "keyword": t_clean,
                "kind": kind,
                "seed_term": seed_parent,
                "growth_label": growth_label,
                "growth_pct": growth_pct,
                "interest_value": interest_score,
                "source": "treg:google_trends",
            }

        try:
            r_tr = self.call(token, "treg.google.keywords.trends", {"keywords": seeds, "country": cc.lower()}, method="POST", max_cost_usd=max_cost_usd)
            total_cost += float(r_tr.get("_cost_usd") or 0.0)
            endpoints_used.append(str(r_tr.get("_served_by") or "treg.google.keywords.trends"))
            series_list = ((r_tr.get("output") or {}).get("series") if isinstance(r_tr.get("output"), dict) else None) or []
            for s_obj in series_list:
                if not isinstance(s_obj, dict):
                    continue
                kws_s = s_obj.get("keywords") if isinstance(s_obj.get("keywords"), list) else seeds
                pts = s_obj.get("data") if isinstance(s_obj.get("data"), list) else []
                for idx_kw, kw_name in enumerate(kws_s):
                    vals = []
                    for pt in pts:
                        if isinstance(pt, dict):
                            v_arr = pt.get("values") if isinstance(pt.get("values"), list) else [pt.get("value")]
                            vi = v_arr[idx_kw] if idx_kw < len(v_arr) else (v_arr[0] if v_arr else None)
                            if isinstance(vi, (int, float)):
                                vals.append(float(vi))
                    cur_v = round(vals[-1], 1) if vals else None
                    avg_v = round(sum(vals) / len(vals), 1) if vals else None
                    peak_v = round(max(vals), 1) if vals else None
                    mom = 0.0
                    if len(vals) >= 6:
                        sp_idx = max(2, len(vals) // 4)
                        rec_avg = sum(vals[-sp_idx:]) / sp_idx
                        pri_avg = sum(vals[:-sp_idx]) / max(1, len(vals[:-sp_idx]))
                        mom = round(((rec_avg - pri_avg) / max(pri_avg, 5.0)) * 100.0, 1)
                    seed_summaries.append({"seed_term": str(kw_name), "current_interest": cur_v, "avg_interest": avg_v, "peak_interest": peak_v, "momentum_pct": mom})
                    _upsert_kw(str(kw_name), "seed", str(kw_name), f"{'+' if mom >= 0 else ''}{mom}%", mom, cur_v)
        except Exception:
            pass

        for s in seeds[:3]:
            got = 0
            try:
                r_id = self.call(token, "treg.google.keywords.ideas", {"keyword": s, "country": cc.lower(), "language": lang, "limit": 12}, method="POST", max_cost_usd=max_cost_usd)
                total_cost += float(r_id.get("_cost_usd") or 0.0)
                endpoints_used.append(str(r_id.get("_served_by") or "treg.google.keywords.ideas"))
                kw_rows = (((r_id.get("output") or {}).get("keywords")) if isinstance(r_id.get("output"), dict) else None) or self._extract_list(r_id)
                for idx_r, kr in enumerate(kw_rows[:12]):
                    val_str = str(kr.get("value") or kr.get("keyword") or kr.get("query") or "").strip() if isinstance(kr, dict) else str(kr).strip()
                    if not val_str:
                        continue
                    vol = kr.get("search_volume") or kr.get("volume") if isinstance(kr, dict) else None
                    _upsert_kw(val_str, "top", s, f"Vol {int(vol):,}" if isinstance(vol, (int, float)) and vol > 0 else f"Gợi ý #{idx_r + 1}", None, float(max(20, 100 - idx_r * 6)))
                    got += 1
            except Exception:
                pass
            if got == 0:
                try:
                    r_sp = self.call(token, "serpapi.x.google-trends", {"engine": "google_trends", "q": s, "data_type": "RELATED_QUERIES", "geo": cc}, method="GET", max_cost_usd=max_cost_usd)
                    total_cost += float(r_sp.get("_cost_usd") or 0.0)
                    endpoints_used.append("serpapi.x.google-trends")
                    rq_wrap = r_sp.get("related_queries") or ((r_sp.get("output") or {}).get("related_queries") if isinstance(r_sp.get("output"), dict) else {}) or {}
                    for rq in (rq_wrap.get("rising") or [])[:8]:
                        if isinstance(rq, dict) and rq.get("query"):
                            ev = rq.get("extracted_value")
                            _upsert_kw(rq["query"], "rising", s, str(rq.get("value") or "Rising"), float(ev) if isinstance(ev, (int, float)) else None, None)
                    for tq in (rq_wrap.get("top") or [])[:8]:
                        if isinstance(tq, dict) and tq.get("query"):
                            ev = tq.get("extracted_value")
                            _upsert_kw(tq["query"], "top", s, f"Top {ev}/100" if ev is not None else "Top Search", None, float(ev) if isinstance(ev, (int, float)) else None)
                except Exception:
                    pass

        for s in seeds:
            if s.lower() not in kw_map:
                _upsert_kw(s, "seed", s)

        ordered = sorted(
            kw_map.values(),
            key=lambda x: (2 if x["kind"] == "rising" else (1 if x["kind"] == "seed" else 0), float(x["growth_pct"] or 0.0), float(x["interest_value"] or 0.0)),
            reverse=True,
        )[: max(3, min(int(max_keywords or 16), 30))]
        return {
            "provider": "treg",
            "actor_or_endpoint": " + ".join(dict.fromkeys(endpoints_used)) or "treg.google.keywords",
            "geo": cc,
            "time_range": time_range or "today 3-m",
            "seed_summaries": seed_summaries,
            "keywords": ordered,
            "cost_usd": round(total_cost, 5),
        }

    # --- Social Painpoint Discovery Backup (Facebook · Threads · X · Reddit) -

    def search_social_painpoints(
        self,
        token: str,
        channel: str,
        query: str,
        limit: int = 8,
        max_cost_usd: float = 0.03,
    ) -> tuple[str, list[dict], float | None]:
        ch = channel.lower().strip()
        lim = max(1, min(20, int(limit)))

        if ch in ("facebook", "facebook_organic"):
            serp_q = f'site:facebook.com "{query}" (posts OR reel OR videos OR groups)'
            res = self.call(token, "treg.google.serp.organic", {"q": serp_q, "country": "vn", "language": "vi", "limit": lim}, method="POST", max_cost_usd=min(0.012, max_cost_usd))
            rows = (((res.get("output") or {}).get("results")) if isinstance(res.get("output"), dict) else None) or self._extract_list(res)
            out = []
            for r in rows[:lim]:
                if not isinstance(r, dict):
                    continue
                u = str(r.get("url") or r.get("link") or "").strip()
                txt = f"{r.get('title') or ''} — {r.get('snippet') or ''}".strip(" —")
                if txt and "ads/library" not in u.lower():
                    out.append({
                        "channel": "facebook_organic",
                        "author": "Facebook",
                        "text": txt[:900],
                        "url": u,
                        "likes": 0,
                        "comments": 0,
                        "shares": 0,
                        "source": "treg:google.serp.facebook",
                    })
            return "treg.google.serp.organic", out, res.get("_cost_usd")

        if ch == "facebook_ads":
            res = self.call(token, "crawl4ai.meta-ads.library.search", {"query": query, "country": "VN", "active_status": "active", "limit": lim}, method="POST", max_cost_usd=max_cost_usd)
            rows = (((res.get("output") or {}).get("ads")) if isinstance(res.get("output"), dict) else None) or self._extract_list(res)
            out = []
            for r in rows[:lim]:
                if not isinstance(r, dict):
                    continue
                txt = str(r.get("body") or r.get("ad_creative_body") or r.get("text") or r.get("title") or "").strip()
                if txt:
                    out.append({
                        "channel": "facebook_ads",
                        "author": str(r.get("page_name") or r.get("advertiser") or "FB Ads"),
                        "text": txt[:900],
                        "url": str(r.get("cta_url") or r.get("link_url") or r.get("snapshot_url") or ""),
                        "likes": 0,
                        "comments": 0,
                        "shares": 0,
                        "source": "treg:meta-ads",
                    })
            return "crawl4ai.meta-ads.library.search", out, res.get("_cost_usd")

        if ch == "threads":
            res = self.call(token, "scrapecreators.x.v1-threads-search", {"query": query}, method="GET", max_cost_usd=max_cost_usd)
            rows = res.get("posts") if isinstance(res.get("posts"), list) else (res.get("threads") if isinstance(res.get("threads"), list) else self._extract_list(res))
            out = []
            for r in rows[:lim]:
                if not isinstance(r, dict):
                    continue
                txt = str(r.get("text") or r.get("caption") or ((r.get("caption") or {}).get("text") if isinstance(r.get("caption"), dict) else "") or "").strip()
                user_obj = r.get("user") if isinstance(r.get("user"), dict) else {}
                uname = str(user_obj.get("username") or r.get("username") or "").strip()
                code = str(r.get("code") or "").strip()
                url = str(r.get("url") or (f"https://www.threads.net/@{uname}/post/{code}" if uname and code else ""))
                if txt:
                    out.append({
                        "channel": "threads",
                        "author": uname,
                        "text": txt[:900],
                        "url": url,
                        "likes": parse_int_metric(r.get("like_count") or r.get("likes") or 0),
                        "comments": parse_int_metric(r.get("reply_count") or r.get("direct_reply_count") or 0),
                        "shares": parse_int_metric(r.get("repost_count") or 0),
                        "source": "treg:threads",
                    })
            return "scrapecreators.x.v1-threads-search", out, res.get("_cost_usd")

        if ch in ("x", "twitter"):
            res = self.call(token, "anyapi.x.search.posts", {"query": query, "limit": lim}, method="POST", max_cost_usd=max_cost_usd)
            rows = (((res.get("output") or {}).get("tweets") or (res.get("output") or {}).get("posts")) if isinstance(res.get("output"), dict) else None) or self._extract_list(res)
            out = []
            for r in rows[:lim]:
                if not isinstance(r, dict):
                    continue
                txt = str(r.get("text") or r.get("full_text") or r.get("content") or "").strip()
                author_obj = r.get("author") if isinstance(r.get("author"), dict) else {}
                uname = str(author_obj.get("userName") or author_obj.get("screen_name") or r.get("username") or "").strip()
                if txt:
                    out.append({
                        "channel": "x",
                        "author": uname,
                        "text": txt[:900],
                        "url": str(r.get("url") or ""),
                        "likes": parse_int_metric(r.get("likes") or r.get("favorite_count") or 0),
                        "comments": parse_int_metric(r.get("replies") or r.get("reply_count") or 0),
                        "shares": parse_int_metric(r.get("retweets") or r.get("retweet_count") or 0),
                        "source": "treg:x",
                    })
            return "anyapi.x.search.posts", out, res.get("_cost_usd")

        if ch == "reddit":
            res = self.call(token, "crawl4ai.reddit.search.posts", {"query": query, "limit": lim}, method="POST", max_cost_usd=max_cost_usd)
            rows = (((res.get("output") or {}).get("posts") or (res.get("output") or {}).get("rows")) if isinstance(res.get("output"), dict) else None) or self._extract_list(res)
            out = []
            for r in rows[:lim]:
                if not isinstance(r, dict):
                    continue
                t_head = str(r.get("title") or "").strip()
                t_body = str(r.get("selftext") or r.get("text") or r.get("body") or "").strip()
                txt = f"{t_head} — {t_body}".strip(" —")
                if txt:
                    out.append({
                        "channel": "reddit",
                        "author": str(r.get("subreddit") or r.get("author") or "reddit"),
                        "text": txt[:900],
                        "url": str(r.get("url") or r.get("permalink") or ""),
                        "likes": parse_int_metric(r.get("score") or r.get("ups") or r.get("upvotes") or 0),
                        "comments": parse_int_metric(r.get("num_comments") or r.get("comments") or 0),
                        "shares": 0,
                        "source": "treg:reddit",
                    })
            return "crawl4ai.reddit.search.posts", out, res.get("_cost_usd")

        raise TregError(f"Kênh MXH chưa hỗ trợ trên Treg: {channel}", status=400)
