"""Apify Store v2 client with N-key failover ring, auto-charge clamping, and Shopee/TikTok/China Sourcing actors."""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from ..responses import safe_id_str


class ApifyError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def parse_vnd_price(raw, currency: str = "VND") -> float:
    """Parse marketplace prices while guarding against VN dot-thousands truncation (<1000 VND)."""
    if raw is None or isinstance(raw, bool):
        return 0.0
    if isinstance(raw, (int, float)):
        val = float(raw)
        if currency.upper() == "VND" and 0 < val < 1000:
            # Common Shopee/TikTok raw micros or dot-thousands truncation
            return round(val * 1000.0, 0)
        if currency.upper() == "VND" and val >= 100_000_000_000:
            # Shopee 100,000x price integers (e.g. 19900000000 -> 199,000)
            return round(val / 100000.0, 0)
        return round(val, 2)
    s = str(raw).strip()
    if not s:
        return 0.0
    # Range: take first number
    if "-" in s or "~" in s:
        s = re.split(r"[-~]", s)[0].strip()
    digits_only = re.sub(r"[^\d.,]", "", s)
    if not digits_only:
        return 0.0
    if currency.upper() == "VND":
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", digits_only):
            return float(digits_only.replace(".", ""))
        if re.fullmatch(r"\d{1,3}(?:,\d{3})+", digits_only):
            return float(digits_only.replace(",", ""))
        cleaned = re.sub(r"[^\d]", "", digits_only)
        val = float(cleaned) if cleaned else 0.0
        if 0 < val < 1000:
            val *= 1000.0
        return val
    cleaned_cny = digits_only.replace(",", "")
    try:
        return round(float(cleaned_cny), 2)
    except ValueError:
        return 0.0


def parse_int_metric(raw) -> int:
    if raw is None or isinstance(raw, bool):
        return 0
    if isinstance(raw, (int, float)):
        return max(0, int(raw))
    s = str(raw).strip().lower().replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(k|nghìn|nghin|tr|triệu|trieu|w|万|\+)?", s)
    if not m:
        return 0
    num = float(m.group(1))
    unit = m.group(2) or ""
    if unit in ("k", "nghìn", "nghin"):
        num *= 1_000
    elif unit in ("w", "万"):
        num *= 10_000
    elif unit in ("tr", "triệu", "trieu"):
        num *= 1_000_000
    return max(0, int(round(num)))


class ApifyClient:
    BASE_URL = "https://api.apify.com/v2"

    def __init__(self, http_opener=None):
        self._opener = http_opener or urllib.request.urlopen

    def _get_json(self, path: str, token: str, timeout: int = 15) -> dict:
        req = urllib.request.Request(
            f"{self.BASE_URL}{path}",
            headers={"Authorization": f"Bearer {token}", "User-Agent": "GlobalShopDianshang/1.0"},
        )
        try:
            with self._opener(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:220]
            raise ApifyError(f"Apify HTTP {exc.code}: {body}", status=exc.code) from None
        except Exception as exc:
            raise ApifyError(f"Lỗi kết nối Apify: {exc}") from None

    def check_key_ring(self, entries: list[dict]) -> dict:
        results = []
        usable_count = 0
        for idx, item in enumerate(entries):
            tok = (item.get("token") or "").strip()
            if not tok:
                continue
            try:
                me = (self._get_json("/users/me", tok).get("data") or {})
                lim = (self._get_json("/users/me/limits", tok).get("data") or {})
                cur_lim = lim.get("limits") or {}
                cur_use = lim.get("current") or {}
                max_usd = cur_lim.get("maxMonthlyUsageUsd")
                used_usd = cur_use.get("monthlyUsageUsd")
                rem_usd = round(float(max_usd) - float(used_usd or 0.0), 4) if max_usd is not None else None
                usable = rem_usd is None or rem_usd > 0.015
                if usable and item.get("enabled", True):
                    usable_count += 1
                results.append({
                    "id": item.get("id"),
                    "label": item.get("label"),
                    "slot": f"priority_{idx + 1}",
                    "enabled": bool(item.get("enabled", True)),
                    "ok": True,
                    "usable": usable,
                    "username": me.get("username") or "",
                    "plan": (me.get("plan") or {}).get("id") or "FREE",
                    "remaining_usd": rem_usd,
                })
            except ApifyError as exc:
                results.append({
                    "id": item.get("id"),
                    "label": item.get("label"),
                    "slot": f"priority_{idx + 1}",
                    "enabled": bool(item.get("enabled", True)),
                    "ok": False,
                    "usable": False,
                    "error": str(exc),
                })
        return {"ok": usable_count > 0, "usable_keys": usable_count, "keys": results}

    def run_sync_items(
        self,
        tokens: list[str],
        actor_slug: str,
        payload: dict,
        max_charge_usd: float = 0.06,
        timeout_sec: int = 55,
    ) -> list[dict]:
        clean_tokens = [t.strip() for t in (tokens or []) if t and t.strip()]
        if not clean_tokens:
            raise ApifyError("Chưa cấu hình Apify API Key", status=400)
        t_sec = max(15, min(120, int(timeout_sec)))
        base_charge = max(0.015, min(1.0, float(max_charge_usd)))
        slug = actor_slug.replace("/", "~")
        last_err: ApifyError | None = None

        for tok in clean_tokens:
            cur_charge = base_charge
            for _adapt in range(2):
                qs = urllib.parse.urlencode({"timeout": t_sec, "maxTotalChargeUsd": f"{cur_charge:.4f}"})
                url = f"{self.BASE_URL}/acts/{slug}/run-sync-get-dataset-items?{qs}"
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {tok}",
                        "Content-Type": "application/json",
                        "User-Agent": "GlobalShopDianshang/1.0",
                    },
                    method="POST",
                )
                try:
                    with self._opener(req, timeout=t_sec + 12) as resp:
                        raw = json.loads(resp.read().decode("utf-8"))
                        if isinstance(raw, list):
                            return [r for r in raw if isinstance(r, dict) and not r.get("_warning")]
                        if isinstance(raw, dict) and isinstance(raw.get("items"), list):
                            return [r for r in raw["items"] if isinstance(r, dict)]
                        return []
                except urllib.error.HTTPError as exc:
                    body_txt = exc.read().decode("utf-8", errors="replace")
                    if exc.code == 400 and "max-total-charge-usd-below-minimum" in body_txt:
                        m = re.search(r"minimum of \$([0-9.]+)", body_txt)
                        if m:
                            req_min = float(m.group(1)) + 0.0005
                            if req_min <= max(base_charge * 2.2, 0.08):
                                cur_charge = req_min
                                continue
                    if exc.code == 402 and "remaining usage of $" in body_txt:
                        m = re.search(r"remaining usage of \$([0-9.]+)", body_txt)
                        if m:
                            rem = float(m.group(1)) - 0.0005
                            if 0.010 <= rem < cur_charge:
                                cur_charge = rem
                                continue
                    last_err = ApifyError(f"Apify {slug} HTTP {exc.code}: {body_txt[:180]}", status=exc.code)
                    if exc.code in (401, 402, 403, 429):
                        break
                    raise last_err
                except Exception as exc:
                    last_err = ApifyError(f"Apify {slug} lỗi mạng: {exc}")
                    break
        raise last_err or ApifyError(f"Không chạy được actor {slug}")

    def _run_actor_ring(
        self,
        tokens: list[str],
        candidates: list[tuple[str, dict]],
        max_charge_usd: float = 0.06,
        timeout_sec: int = 50,
    ) -> tuple[str, list[dict]]:
        last_exc: Exception | None = None
        for slug, payload in candidates:
            try:
                items = self.run_sync_items(tokens, slug, payload, max_charge_usd=max_charge_usd, timeout_sec=timeout_sec)
                if items:
                    return slug, items
            except Exception as exc:
                last_exc = exc
                continue
        if last_exc:
            raise last_exc
        return (candidates[0][0] if candidates else ""), []

    # --- Shopee VN Search / Product / Shop -----------------------------------

    def search_shopee(self, tokens: list[str], query: str, limit: int = 12, max_charge_usd: float = 0.06) -> tuple[str, list[dict]]:
        lim = max(1, min(40, int(limit)))
        search_url = f"https://shopee.vn/search?keyword={urllib.parse.quote(query)}"
        candidates = [
            ("xtracto~shopee-search", {"keyword": query, "country": "VN", "maxItems": lim}),
            ("lergassy~shopee-scraper", {"search": query, "country": "vn", "maxItems": lim}),
            ("gio21~shopee-scraper", {"startUrls": [{"url": search_url}], "maxItems": lim}),
        ]
        slug, rows = self._run_actor_ring(tokens, candidates, max_charge_usd=max_charge_usd)
        return slug, [self.normalize_shopee_item(r) for r in rows[:lim]]

    def scrape_shopee_shop(self, tokens: list[str], shop_url_or_name: str, limit: int = 20, max_charge_usd: float = 0.06) -> tuple[str, list[dict]]:
        lim = max(1, min(50, int(limit)))
        s = shop_url_or_name.strip()
        url = s if s.startswith("http") else f"https://shopee.vn/{s.lstrip('@/')}"
        candidates = [
            ("memo23~shopee-scraper", {"startUrls": [url], "maxItems": lim}),
            ("lergassy~shopee-scraper", {"startUrls": [{"url": url}], "maxItems": lim}),
            ("xtracto~shopee-scraper", {"urls": [url], "maxItems": lim}),
        ]
        slug, rows = self._run_actor_ring(tokens, candidates, max_charge_usd=max_charge_usd)
        return slug, [self.normalize_shopee_item(r) for r in rows[:lim]]

    def scrape_shopee_product(self, tokens: list[str], product_url: str, max_charge_usd: float = 0.05) -> dict | None:
        candidates = [
            ("xtracto~shopee-product-detail", {"urls": [product_url]}),
            ("zen-studio~shopee-product-detail-scraper", {"urls": [product_url]}),
            ("lergassy~shopee-scraper", {"startUrls": [{"url": product_url}], "maxItems": 1}),
        ]
        _, rows = self._run_actor_ring(tokens, candidates, max_charge_usd=max_charge_usd)
        return self.normalize_shopee_item(rows[0]) if rows else None

    @staticmethod
    def normalize_shopee_item(r: dict) -> dict:
        item_id = safe_id_str(r.get("itemid") or r.get("item_id") or r.get("id") or r.get("productId"))
        shop_id = safe_id_str(r.get("shopid") or r.get("shop_id") or r.get("shopId"))
        title = str(r.get("name") or r.get("title") or r.get("item_name") or "").strip()
        raw_price = r.get("price_display") or r.get("formattedPrice") or r.get("price") or r.get("price_min") or 0
        price_vnd = parse_vnd_price(raw_price, "VND")
        sold_all = parse_int_metric(r.get("historical_sold") or r.get("sold_count") or r.get("global_sold_count") or r.get("sold") or 0)
        sold_30d = parse_int_metric(r.get("sold") or r.get("monthly_sold") or 0)
        url = str(r.get("url") or r.get("link") or "").strip()
        if not url and shop_id and item_id:
            url = f"https://shopee.vn/product/{shop_id}/{item_id}"
        img = str(r.get("image") or r.get("thumbnail") or r.get("cover") or "").strip()
        if img and not img.startswith("http"):
            img = f"https://down-vn.img.susercontent.com/file/{img}"
        rating = float(r.get("item_rating", {}).get("rating_star") if isinstance(r.get("item_rating"), dict) else (r.get("rating") or r.get("rating_star") or 0.0))
        return {
            "platform": "shopee",
            "market": "VN",
            "native_product_id": item_id,
            "native_shop_id": shop_id,
            "shop_name": str(r.get("shop_name") or r.get("shopName") or r.get("seller_name") or ""),
            "is_mall": bool(r.get("is_official_shop") or r.get("shopee_verified") or r.get("isMall")),
            "title": title,
            "price_vnd": price_vnd,
            "sold_count": max(sold_all, sold_30d),
            "sold_30d": sold_30d,
            "gmv_vnd": round(price_vnd * max(sold_all, sold_30d), 0),
            "rating": round(rating, 2) if 0 < rating <= 5 else 0.0,
            "stock": parse_int_metric(r.get("stock") or 0),
            "total_available_hint": parse_int_metric(r.get("total_count") or r.get("totalCount") or 0),
            "url": url,
            "image_url": img,
        }

    # --- TikTok Shop & TikTok Video / Creator --------------------------------

    def search_tiktok_shop(self, tokens: list[str], query: str, limit: int = 12, max_charge_usd: float = 0.06) -> tuple[str, list[dict]]:
        lim = max(1, min(40, int(limit)))
        candidates = [
            ("harshmaur~tiktok-shop-scraper", {"keyword": query, "region": "VN", "maxItems": lim}),
            ("pratikdani~tiktok-shop-search-scraper", {"query": query, "country": "VN", "maxResults": lim}),
            ("clockworks~tiktok-shop-scraper", {"searchQueries": [query], "resultsPerPage": lim}),
        ]
        slug, rows = self._run_actor_ring(tokens, candidates, max_charge_usd=max_charge_usd)
        return slug, [self.normalize_tiktok_shop_item(r) for r in rows[:lim]]

    def scrape_tiktok_shop_detail(self, tokens: list[str], product_url_or_id: str, max_charge_usd: float = 0.05) -> dict | None:
        s = product_url_or_id.strip()
        url = s if s.startswith("http") else f"https://shop.tiktok.com/view/product/{s}?region=VN"
        candidates = [
            ("cunning_soil~tiktok-shop-product-scraper-mobile-api", {"urls": [url], "outputMode": "full_readable"}),
            ("jungle_synthesizer~tiktok-shop-product-detail-scraper", {"productUrls": [url]}),
            ("harshmaur~tiktok-shop-scraper", {"productUrls": [url]}),
        ]
        _, rows = self._run_actor_ring(tokens, candidates, max_charge_usd=max_charge_usd)
        return self.normalize_tiktok_shop_item(rows[0]) if rows else None

    @staticmethod
    def normalize_tiktok_shop_item(r: dict) -> dict:
        pid = safe_id_str(r.get("product_id") or r.get("productId") or r.get("id"))
        sid = safe_id_str(r.get("seller_id") or r.get("shop_id") or r.get("shopId"))
        title = str(r.get("title") or r.get("product_name") or r.get("name") or "").strip()
        disp_price = r.get("priceDisplay") or r.get("formattedPrice") or r.get("sale_price_format") or r.get("price")
        price_vnd = parse_vnd_price(disp_price, "VND")
        if 0 < price_vnd < 1000 and r.get("price_str"):
            price_vnd = parse_vnd_price(r.get("price_str"), "VND")
        sold = parse_int_metric(r.get("sold_count") or r.get("soldCount") or r.get("sales") or r.get("volume") or 0)
        url = str(r.get("url") or r.get("product_url") or "").strip()
        if not url and pid:
            url = f"https://shop.tiktok.com/view/product/{pid}?region=VN"
        img = ""
        raw_img = r.get("cover") or r.get("image") or r.get("thumbnail") or r.get("images")
        if isinstance(raw_img, list) and raw_img:
            img = str(raw_img[0] if isinstance(raw_img[0], str) else raw_img[0].get("url", ""))
        elif isinstance(raw_img, str):
            img = raw_img
        rating = float(r.get("rating") or r.get("star") or 0.0)
        return {
            "platform": "tiktok_shop",
            "market": "VN",
            "native_product_id": pid,
            "native_shop_id": sid,
            "shop_name": str(r.get("seller_name") or r.get("shop_name") or r.get("shopName") or ""),
            "is_mall": bool(r.get("is_mall") or r.get("isMall")),
            "title": title,
            "price_vnd": price_vnd,
            "sold_count": sold,
            "sold_30d": parse_int_metric(r.get("sold_30d") or 0),
            "gmv_vnd": round(price_vnd * sold, 0),
            "rating": round(rating, 2) if 0 < rating <= 5 else 0.0,
            "stock": parse_int_metric(r.get("stock") or 0),
            "url": url,
            "image_url": img,
        }

    def search_tiktok_videos(self, tokens: list[str], query: str, limit: int = 10, max_charge_usd: float = 0.05) -> tuple[str, list[dict]]:
        lim = max(1, min(30, int(limit)))
        candidates = [
            ("clockworks~tiktok-scraper", {"searchQueries": [query], "resultsPerPage": lim}),
            ("clockworks~free-tiktok-scraper", {"searchQueries": [query], "resultsPerPage": lim}),
        ]
        return self._run_actor_ring(tokens, candidates, max_charge_usd=max_charge_usd)

    def fetch_tiktok_creator_videos(self, tokens: list[str], handle: str, limit: int = 12, max_charge_usd: float = 0.05) -> tuple[str, list[dict]]:
        clean = handle.strip().lstrip("@")
        candidates = [
            ("clockworks~tiktok-scraper", {"profiles": [clean], "resultsPerPage": limit}),
            ("clockworks~free-tiktok-scraper", {"profiles": [clean], "resultsPerPage": limit}),
        ]
        return self._run_actor_ring(tokens, candidates, max_charge_usd=max_charge_usd)

    # --- China E-Commerce Sourcing (1688 · Taobao/Tmall · Pinduoduo) ---------

    def search_china_sourcing(
        self,
        tokens: list[str],
        platform: str,
        query_or_url: str,
        limit: int = 10,
        max_charge_usd: float = 0.06,
    ) -> tuple[str, list[dict]]:
        plat = platform.lower().strip()
        lim = max(1, min(30, int(limit)))
        is_url = query_or_url.strip().startswith("http")

        if plat == "1688":
            if is_url:
                candidates = [
                    ("blueskyscraper~1688-product-details-scraper", {"urls": [query_or_url]}),
                    ("zen-studio~1688-wholesale-scraper", {"startUrls": [{"url": query_or_url}], "maxItems": 3}),
                ]
            else:
                candidates = [
                    ("zen-studio~1688-wholesale-scraper", {"keyword": query_or_url, "maxItems": lim}),
                    ("parsebird~1688-wholesale-scraper", {"searchKeyword": query_or_url, "maxItems": lim}),
                    ("scrapewise~alibaba-1688-scraper", {"keyword": query_or_url, "maxItems": lim}),
                ]
        elif plat == "taobao":
            if is_url:
                candidates = [
                    ("zen-studio~taobao-detail-scraper", {"urls": [query_or_url]}),
                    ("pizani~taobao-product-scraper", {"startUrls": [{"url": query_or_url}]}),
                ]
            else:
                candidates = [
                    ("zen-studio~taobao-search-scraper", {"keyword": query_or_url, "maxItems": lim}),
                    ("scrapesage~taobao-scraper", {"search": query_or_url, "maxItems": lim}),
                    ("memo23~taobao-scraper", {"keywords": [query_or_url], "maxItems": lim}),
                ]
        elif plat == "pinduoduo":
            candidates = [
                ("trusted_tech_spot~pinduoduo-temu-wholesale-bestsellers-scraper", {"keyword": query_or_url, "maxItems": lim}),
                ("kayhermes~125-pinduoduo-price-promotion-monitor", {"search": query_or_url, "maxItems": lim}),
            ]
        else:
            candidates = [
                ("zen-studio~alibaba-scraper", {"keyword": query_or_url, "maxItems": lim}),
            ]

        slug, rows = self._run_actor_ring(tokens, candidates, max_charge_usd=max_charge_usd)
        return slug, [self.normalize_china_item(r, plat) for r in rows[:lim]]

    @staticmethod
    def normalize_china_item(r: dict, platform: str) -> dict:
        iid = safe_id_str(r.get("offerId") or r.get("item_id") or r.get("itemId") or r.get("num_iid") or r.get("goods_id") or r.get("id"))
        title = str(r.get("subject") or r.get("title") or r.get("goods_name") or r.get("name") or "").strip()
        raw_price = r.get("price") or r.get("wholesalePrice") or r.get("minPrice") or r.get("group_price") or 0
        price_cny = parse_vnd_price(raw_price, "CNY")
        moq = max(1, parse_int_metric(r.get("moq") or r.get("minOrderQuantity") or r.get("beginAmount") or 1))
        url = str(r.get("detailUrl") or r.get("url") or r.get("item_url") or "").strip()
        if not url and iid:
            if platform == "1688":
                url = f"https://detail.1688.com/offer/{iid}.html"
            elif platform == "taobao":
                url = f"https://item.taobao.com/item.htm?id={iid}"
            elif platform == "pinduoduo":
                url = f"https://mobile.yangkeduo.com/goods.html?goods_id={iid}"
        img = str(r.get("imageUrl") or r.get("pic_url") or r.get("image") or r.get("thumb_url") or "").strip()
        if img.startswith("//"):
            img = "https:" + img
        return {
            "platform": platform,
            "native_item_id": iid,
            "title": title,
            "price_cny": price_cny,
            "moq": moq,
            "supplier_name": str(r.get("companyName") or r.get("shopName") or r.get("seller_nick") or r.get("mall_name") or ""),
            "sales_volume": str(r.get("saleInfo") or r.get("bookedCount") or r.get("sales") or r.get("deal_cnt") or ""),
            "item_url": url,
            "image_url": img,
        }

    # --- Lazada / Facebook Ads / Google Trends -------------------------------

    def search_lazada(self, tokens: list[str], query: str, limit: int = 10, max_charge_usd: float = 0.05) -> tuple[str, list[dict]]:
        candidates = [("lergassy~lazada-scraper", {"search": query, "country": "vn", "maxItems": limit})]
        slug, rows = self._run_actor_ring(tokens, candidates, max_charge_usd=max_charge_usd)
        out = []
        for r in rows[:limit]:
            p = parse_vnd_price(r.get("price") or r.get("salePrice") or 0, "VND")
            sold = parse_int_metric(r.get("sold") or r.get("itemSoldCntShow") or 0)
            out.append({
                "platform": "lazada",
                "market": "VN",
                "native_product_id": safe_id_str(r.get("itemId") or r.get("id")),
                "native_shop_id": safe_id_str(r.get("sellerId") or ""),
                "shop_name": str(r.get("sellerName") or ""),
                "is_mall": bool(r.get("isMall")),
                "title": str(r.get("name") or r.get("title") or "").strip(),
                "price_vnd": p,
                "sold_count": sold,
                "gmv_vnd": round(p * sold, 0),
                "rating": float(r.get("ratingScore") or 0.0),
                "url": str(r.get("itemUrl") or r.get("url") or "").strip(),
                "image_url": str(r.get("image") or "").strip(),
            })
        return slug, out

    def search_facebook_ads(self, tokens: list[str], query: str, limit: int = 8, max_charge_usd: float = 0.05) -> tuple[str, list[dict]]:
        candidates = [
            ("automation-lab~facebook-ads-library", {"searchTerms": [query], "country": "VN", "maxItems": limit}),
            ("apify~facebook-ads-scraper", {"searchQuery": query, "country": "VN", "maxItems": limit}),
        ]
        return self._run_actor_ring(tokens, candidates, max_charge_usd=max_charge_usd)

    def fetch_google_trends(self, tokens: list[str], keyword: str, geo: str = "VN", max_charge_usd: float = 0.05) -> tuple[str, list[dict]]:
        candidates = [
            ("apify~google-trends-scraper", {"searchTerms": [keyword], "geo": geo, "timeRange": "today 3-m"}),
            ("khadinakbar~google-trends-scraper", {"keywords": [keyword], "geo": geo}),
        ]
        return self._run_actor_ring(tokens, candidates, max_charge_usd=max_charge_usd)
