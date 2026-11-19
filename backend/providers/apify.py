"""Apify Store v2 client with N-key failover ring, auto-charge clamping, and Shopee/TikTok/China Sourcing actors."""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from ..markets import SEA_MARKETS, convert_local_price_to_vnd, detect_market_from_url, normalize_market_code, shopee_domain_for_market
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
                            req_min = float(m.group(1)) + 0.001
                            if req_min <= max(base_charge * 4.5, 0.25):
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

    # --- Shopee Multi-Market Search (VN · PH · SG · MY · TH + Overseas / Sort / Mall / Price Filters) ---

    @staticmethod
    def normalize_shopee_filters(filters: dict | None, market: str = "VN") -> dict:
        mkt = normalize_market_code(market, "VN")
        mkt_meta = SEA_MARKETS[mkt]
        f = dict(filters or {})
        raw_loc = str(f.get("shipped_from") or f.get("location") or "").strip()
        low_loc = raw_loc.lower()
        if low_loc in ("overseas", "nuoc_ngoai", "nước ngoài", "quoc_te", "shop quốc tế", "mainland china", "ต่างประเทศ"):
            shipped_from = mkt_meta["shopee_overseas_label"]
        elif low_loc in ("domestic", "trong_nuoc", "trong nước", "local", "ภายในประเทศ"):
            shipped_from = "Trong nước" if mkt == "VN" else mkt_meta["shopee_domestic_loc"]
        elif mkt == "VN":
            vn_map = {
                "ha_noi": "Hà Nội",
                "hà nội": "Hà Nội",
                "hcm": "TP. Hồ Chí Minh",
                "tp.hcm": "TP. Hồ Chí Minh",
                "tp. hồ chí minh": "TP. Hồ Chí Minh",
            }
            shipped_from = vn_map.get(low_loc, raw_loc)
        else:
            shipped_from = raw_loc

        raw_sort = str(f.get("sort_by") or f.get("sort") or "relevancy").strip().lower()
        sort_by = raw_sort if raw_sort in ("relevancy", "sales", "latest", "price_asc", "price_desc") else "relevancy"
        min_price = int(f["min_price"]) if f.get("min_price") not in (None, "", 0, "0") and str(f.get("min_price")).isdigit() else None
        max_price = int(f["max_price"]) if f.get("max_price") not in (None, "", 0, "0") and str(f.get("max_price")).isdigit() else None
        min_rating = float(f["min_rating"]) if f.get("min_rating") not in (None, "", 0, "0") else None
        return {
            "market": mkt,
            "shipped_from": shipped_from,
            "sort_by": sort_by,
            "min_price": min_price,
            "max_price": max_price,
            "min_rating": min_rating,
            "official_shop_only": bool(f.get("official_shop_only")),
            "preferred_seller_only": bool(f.get("preferred_seller_only")),
            "free_shipping_only": bool(f.get("free_shipping_only")),
            "discounted_only": bool(f.get("discounted_only")),
            "with_video_only": bool(f.get("with_video_only")),
        }

    @staticmethod
    def build_shopee_search_url(query: str, norm_filters: dict, market: str = "VN") -> str:
        mkt = normalize_market_code(norm_filters.get("market") or market, "VN")
        dom = shopee_domain_for_market(mkt)
        params: dict[str, str] = {"keyword": query}
        sf = norm_filters.get("shipped_from") or ""
        if mkt == "VN" and sf == "Trong nước":
            params["locations"] = "-1"
        elif sf:
            params["locations"] = sf

        sb = norm_filters.get("sort_by") or "relevancy"
        if sb == "sales":
            params["sortBy"] = "sales"
        elif sb == "latest":
            params["sortBy"] = "ctime"
        elif sb == "price_asc":
            params["sortBy"] = "price"
            params["order"] = "asc"
        elif sb == "price_desc":
            params["sortBy"] = "price"
            params["order"] = "desc"

        if norm_filters.get("min_price"):
            params["minPrice"] = str(norm_filters["min_price"])
        if norm_filters.get("max_price"):
            params["maxPrice"] = str(norm_filters["max_price"])
        if norm_filters.get("min_rating"):
            params["ratingFilter"] = str(int(norm_filters["min_rating"]))
        if norm_filters.get("official_shop_only"):
            params["officialShop"] = "1"
        if norm_filters.get("preferred_seller_only"):
            params["shopeeVerified"] = "1"
        if norm_filters.get("with_video_only"):
            params["withVideo"] = "true"
        return f"https://{dom}/search?" + urllib.parse.urlencode(params)

    @classmethod
    def build_shopee_vn_search_url(cls, query: str, norm_filters: dict) -> str:
        return cls.build_shopee_search_url(query, norm_filters, market="VN")

    def search_shopee(
        self,
        tokens: list[str],
        query: str,
        limit: int = 12,
        max_charge_usd: float = 0.08,
        filters: dict | None = None,
        market: str = "VN",
    ) -> tuple[str, list[dict]]:
        lim = max(1, min(40, int(limit)))
        mkt = normalize_market_code(market, "VN")
        nf = self.normalize_shopee_filters(filters, market=mkt)
        search_url = self.build_shopee_search_url(query, nf, market=mkt)

        # Primary #1: `lergassy~shopee-scraper` (native support for VN, PH, SG, MY, TH + `shippedFrom`, `sortBy`, `officialShopOnly`, etc.)
        lergassy_payload: dict = {
            "mode": "search",
            "country": mkt,
            "maxItems": lim,
            "includeShopAndReviews": True,
            "sortBy": nf["sort_by"],
        }
        if mkt == "VN" and nf["shipped_from"] == "Trong nước":
            lergassy_payload["startUrls"] = [search_url]
        else:
            lergassy_payload["searchTerms"] = [query]
            if nf["shipped_from"]:
                lergassy_payload["shippedFrom"] = nf["shipped_from"]

        if nf["min_price"] is not None:
            lergassy_payload["minPrice"] = nf["min_price"]
        if nf["max_price"] is not None:
            lergassy_payload["maxPrice"] = nf["max_price"]
        if nf["min_rating"] is not None:
            lergassy_payload["minRating"] = nf["min_rating"]
        if nf["official_shop_only"]:
            lergassy_payload["officialShopOnly"] = True
        if nf["preferred_seller_only"]:
            lergassy_payload["preferredSellerOnly"] = True
        if nf["free_shipping_only"]:
            lergassy_payload["freeShippingOnly"] = True
        if nf["discounted_only"]:
            lergassy_payload["discountedOnly"] = True
        if nf["with_video_only"]:
            lergassy_payload["withVideoOnly"] = True

        # Failover #2: `memo23~shopee-scraper` & Failover #3: `webdata_labs~shopee-scraper`
        memo_payload: dict = {"startUrls": [search_url], "country": mkt, "maxItems": lim, "sortBy": nf["sort_by"]}
        if nf["min_price"] is not None:
            memo_payload["minPrice"] = nf["min_price"]
        if nf["max_price"] is not None:
            memo_payload["maxPrice"] = nf["max_price"]

        webdata_payload: dict = {"startUrls": [search_url], "country": mkt.lower(), "maxItemsPerSource": lim, "sort": nf["sort_by"]}
        if nf["official_shop_only"]:
            webdata_payload["mallOnly"] = True

        candidates = [
            ("lergassy~shopee-scraper", lergassy_payload),
            ("memo23~shopee-scraper", memo_payload),
            ("webdata_labs~shopee-scraper", webdata_payload),
        ]
        slug, rows = self._run_actor_ring(tokens, candidates, max_charge_usd=max_charge_usd)
        normalized = [self.normalize_shopee_item(r, default_market=mkt) for r in rows if isinstance(r, dict) and r.get("type") != "notice"]

        overseas_target = SEA_MARKETS[mkt]["shopee_overseas_label"]
        if nf["shipped_from"] == overseas_target:
            overseas_only = [x for x in normalized if x.get("is_overseas")]
            if overseas_only:
                normalized = overseas_only
        elif nf["shipped_from"] in ("Trong nước", "Local", "Singapore", "ภายในประเทศ"):
            normalized = [x for x in normalized if not x.get("is_overseas")]

        return slug, normalized[:lim]

    def scrape_shopee_shop(
        self,
        tokens: list[str],
        shop_url_or_name: str,
        limit: int = 20,
        max_charge_usd: float = 0.06,
        market: str = "VN",
    ) -> tuple[str, list[dict]]:
        lim = max(1, min(50, int(limit)))
        s = shop_url_or_name.strip()
        mkt = normalize_market_code(detect_market_from_url(s) or market, "VN")
        dom = shopee_domain_for_market(mkt)
        url = s if s.startswith("http") else f"https://{dom}/{s.lstrip('@/')}"
        candidates = [
            ("lergassy~shopee-scraper", {"mode": "shop", "country": mkt, "startUrls": [url], "maxItems": lim}),
            ("memo23~shopee-scraper", {"country": mkt, "startUrls": [url], "maxItems": lim}),
        ]
        slug, rows = self._run_actor_ring(tokens, candidates, max_charge_usd=max_charge_usd)
        return slug, [self.normalize_shopee_item(r, default_market=mkt) for r in rows[:lim] if isinstance(r, dict) and r.get("type") != "notice"]

    def scrape_shopee_product(self, tokens: list[str], product_url: str, max_charge_usd: float = 0.05, market: str = "VN") -> dict | None:
        mkt = normalize_market_code(detect_market_from_url(product_url) or market, "VN")
        candidates = [
            ("lergassy~shopee-scraper", {"mode": "product", "country": mkt, "startUrls": [product_url], "maxItems": 1}),
            ("memo23~shopee-scraper", {"country": mkt, "startUrls": [product_url], "maxItems": 1}),
            ("zen-studio~shopee-product-detail-scraper", {"urls": [product_url]}),
        ]
        _, rows = self._run_actor_ring(tokens, candidates, max_charge_usd=max_charge_usd)
        return self.normalize_shopee_item(rows[0], default_market=mkt) if rows else None

    @staticmethod
    def normalize_shopee_item(r: dict, default_market: str = "VN") -> dict:
        raw_url = str(r.get("productUrl") or r.get("url") or r.get("link") or "").strip()
        mkt = normalize_market_code(
            str(r.get("country") or "").upper() or detect_market_from_url(raw_url) or default_market,
            "VN",
        )
        ccy = SEA_MARKETS[mkt]["currency"]
        dom = shopee_domain_for_market(mkt)

        item_id = safe_id_str(r.get("itemId") or r.get("itemid") or r.get("item_id") or r.get("productId") or r.get("id"))
        shop_id = safe_id_str(r.get("shopId") or r.get("shopid") or r.get("shop_id"))
        title = str(r.get("title") or r.get("name") or r.get("item_name") or "").strip()
        raw_price = r.get("price_display") or r.get("formattedPrice") or r.get("price") or r.get("priceMin") or r.get("price_min") or 0
        native_price = parse_vnd_price(raw_price, ccy)
        price_vnd, _, _ = convert_local_price_to_vnd(native_price, mkt)

        sold_all = parse_int_metric(
            r.get("historical_sold")
            or r.get("historicalSold")
            or r.get("soldTotal")
            or r.get("sold_count")
            or r.get("soldCount")
            or r.get("global_sold_count")
            or r.get("sold")
            or 0
        )
        sold_30d = parse_int_metric(
            r.get("soldRecent")
            or r.get("sold")
            or r.get("monthly_sold")
            or r.get("monthlySold")
            or 0
        )
        rating_count = parse_int_metric(r.get("ratingCount") or r.get("reviewCount") or r.get("cmt_count") or r.get("review_count") or 0)
        eff_sold = max(sold_all, sold_30d) if max(sold_all, sold_30d) > 0 else (rating_count * 3 if rating_count > 0 else 0)

        top_stock = parse_int_metric(r.get("stock") or r.get("inventory") or r.get("totalStock") or 0)
        if top_stock <= 0 and isinstance(r.get("variants"), list):
            top_stock = sum(
                parse_int_metric(v.get("stock") or v.get("inventory") or v.get("normal_stock") or 0)
                for v in r["variants"]
                if isinstance(v, dict)
            )

        url = raw_url
        if not url and shop_id and item_id:
            url = f"https://{dom}/product/{shop_id}/{item_id}"
        img = str(r.get("imageUrl") or r.get("image") or r.get("thumbnail") or r.get("cover") or "").strip()
        if img and not img.startswith("http"):
            img = f"https://down-{mkt.lower()}.img.susercontent.com/file/{img}"
        rating = float(r.get("item_rating", {}).get("rating_star") if isinstance(r.get("item_rating"), dict) else (r.get("rating") or r.get("rating_star") or 0.0))

        shop_location = str(r.get("location") or r.get("shop_location") or r.get("shopLocation") or "").strip()
        loc_low = shop_location.lower()
        is_overseas = bool(
            r.get("is_overseas")
            or r.get("isOverseas")
            or r.get("cb_option") == 1
            or any(k in loc_low for k in ("nước ngoài", "overseas", "mainland china", "quốc tế", "china", "trung quốc", "hàn quốc", "ต่างประเทศ"))
        )
        labels_raw = [str(x).lower() for x in (r.get("labels") or [])] if isinstance(r.get("labels"), list) else []
        is_mall = bool(r.get("is_official_shop") or r.get("isOfficialShop") or r.get("isMall") or r.get("officialShop") or any("mall" in lb for lb in labels_raw))
        is_preferred = bool(r.get("shopee_verified") or r.get("isPreferred") or any("preferred" in lb or "yêu thích" in lb for lb in labels_raw))
        seller_obj = r.get("seller") if isinstance(r.get("seller"), dict) else {}
        shop_nm = str(
            r.get("shopName")
            or r.get("shop_name")
            or r.get("shopUsername")
            or r.get("seller_name")
            or seller_obj.get("name")
            or seller_obj.get("username")
            or ""
        )

        return {
            "platform": "shopee",
            "market": mkt,
            "native_product_id": item_id,
            "native_shop_id": shop_id,
            "shop_name": shop_nm,
            "shop_location": shop_location,
            "is_overseas": is_overseas,
            "is_mall": is_mall,
            "is_preferred": is_preferred,
            "title": title,
            "native_price": native_price,
            "native_currency": ccy,
            "price_vnd": price_vnd,
            "sold_count": eff_sold,
            "sold_30d": sold_30d,
            "rating_count": rating_count,
            "gmv_vnd": round(price_vnd * eff_sold, 0),
            "rating": round(rating, 2) if 0 < rating <= 5 else 0.0,
            "discount_pct": parse_int_metric(r.get("discountPercent") or 0),
            "stock": top_stock,
            "total_available_hint": parse_int_metric(r.get("total_count") or r.get("totalCount") or 0),
            "url": url,
            "image_url": img,
        }

    # --- TikTokShop Multi-Market (VN · PH · SG · MY · TH) & TikTok Creator ---

    def search_tiktok_shop(
        self,
        tokens: list[str],
        query: str,
        limit: int = 12,
        max_charge_usd: float = 0.06,
        market: str = "VN",
    ) -> tuple[str, list[dict]]:
        lim = max(1, min(40, int(limit)))
        mkt = normalize_market_code(market, "VN")
        candidates = [
            ("harshmaur~tiktok-shop-scraper", {"searchQueries": [query], "market": mkt.lower(), "maxProductsPerSource": lim}),
            ("pratikdani~tiktok-shop-search-scraper", {"keyword": query, "country_code": mkt, "limit": lim}),
            ("clockworks~tiktok-shop-scraper", {"searchQueries": [query], "resultsPerPage": lim}),
        ]
        slug, rows = self._run_actor_ring(tokens, candidates, max_charge_usd=max_charge_usd)
        return slug, [self.normalize_tiktok_shop_item(r, default_market=mkt) for r in rows[:lim] if isinstance(r, dict)]

    def scrape_tiktok_shop_detail(self, tokens: list[str], product_url_or_id: str, max_charge_usd: float = 0.05, market: str = "VN") -> dict | None:
        s = product_url_or_id.strip()
        mkt = normalize_market_code(detect_market_from_url(s) or market, "VN")
        url = s if s.startswith("http") else f"https://shop.tiktok.com/view/product/{s}?region={mkt}"
        candidates = [
            ("cunning_soil~tiktok-shop-product-scraper-mobile-api", {"urls": [url], "outputMode": "full_readable"}),
            ("jungle_synthesizer~tiktok-shop-product-detail-scraper", {"productUrls": [url]}),
            ("harshmaur~tiktok-shop-scraper", {"startUrls": [url], "market": mkt.lower()}),
        ]
        _, rows = self._run_actor_ring(tokens, candidates, max_charge_usd=max_charge_usd)
        return self.normalize_tiktok_shop_item(rows[0], default_market=mkt) if rows else None

    @staticmethod
    def normalize_tiktok_shop_item(r: dict, default_market: str = "VN") -> dict:
        raw_url = str(r.get("url") or r.get("product_url") or r.get("productUrl") or "").strip()
        mkt = normalize_market_code(
            str(r.get("market") or r.get("region") or r.get("country") or "").upper() or detect_market_from_url(raw_url) or default_market,
            "VN",
        )
        ccy = SEA_MARKETS[mkt]["currency"]
        pid = safe_id_str(r.get("product_id") or r.get("productId") or r.get("id"))
        sid = safe_id_str(r.get("seller_id") or r.get("shop_id") or r.get("shopId"))
        title = str(r.get("title") or r.get("product_name") or r.get("name") or "").strip()
        disp_price = r.get("priceDisplay") or r.get("formattedPrice") or r.get("sale_price_format") or r.get("price")
        native_price = parse_vnd_price(disp_price, ccy)
        if mkt == "VN" and 0 < native_price < 1000 and r.get("price_str"):
            native_price = parse_vnd_price(r.get("price_str"), "VND")
        price_vnd, _, _ = convert_local_price_to_vnd(native_price, mkt)
        sold = parse_int_metric(r.get("sold_count") or r.get("soldCount") or r.get("sales") or r.get("volume") or 0)
        url = raw_url or (f"https://shop.tiktok.com/view/product/{pid}?region={mkt}" if pid else "")
        img = ""
        raw_img = r.get("cover") or r.get("image") or r.get("thumbnail") or r.get("images")
        if isinstance(raw_img, dict):
            ulist = raw_img.get("url_list") or raw_img.get("thumb_url_list") or []
            img = str(ulist[0] if isinstance(ulist, list) and ulist else (raw_img.get("url") or ""))
        elif isinstance(raw_img, list) and raw_img:
            first_im = raw_img[0]
            if isinstance(first_im, dict):
                ulist = first_im.get("url_list") or first_im.get("thumb_url_list") or []
                img = str(ulist[0] if isinstance(ulist, list) and ulist else (first_im.get("url") or ""))
            else:
                img = str(first_im)
        elif isinstance(raw_img, str) and raw_img.startswith("http"):
            img = raw_img
        rating = float(r.get("rating") or r.get("star") or 0.0)
        return {
            "platform": "tiktok_shop",
            "market": mkt,
            "native_product_id": pid,
            "native_shop_id": sid,
            "shop_name": str(r.get("seller_name") or r.get("shop_name") or r.get("shopName") or ""),
            "is_mall": bool(r.get("is_mall") or r.get("isMall")),
            "title": title,
            "native_price": native_price,
            "native_currency": ccy,
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
                    ("zen-studio~1688-wholesale-scraper", {"offerIds": [query_or_url], "maxResults": 3}),
                ]
            else:
                candidates = [
                    ("parsebird~1688-wholesale-scraper", {"keywords": [query_or_url], "maxResults": lim}),
                    ("zen-studio~1688-wholesale-scraper", {"keywords": [query_or_url], "maxResults": lim}),
                    ("memo23~taobao-scraper", {"searchQueries": [query_or_url], "maxProductsPerKeyword": max(5, lim)}),
                ]
        elif plat == "taobao":
            if is_url:
                candidates = [
                    ("zen-studio~taobao-detail-scraper", {"urls": [query_or_url]}),
                    ("memo23~taobao-scraper", {"startUrls": [query_or_url]}),
                    ("scrapesage~taobao-scraper", {"mode": "detail", "itemUrls": [query_or_url]}),
                ]
            else:
                candidates = [
                    ("memo23~taobao-scraper", {"searchQueries": [query_or_url], "maxProductsPerKeyword": max(5, lim)}),
                    ("zen-studio~taobao-search-scraper", {"keyword": query_or_url, "maxItems": max(10, lim), "enrichWithDetails": False}),
                    ("scrapesage~taobao-scraper", {"mode": "search", "keywords": [query_or_url], "maxItems": max(10, lim), "scrapeDetails": False}),
                ]
        elif plat == "pinduoduo":
            candidates = [
                ("parsebird~1688-wholesale-scraper", {"keywords": [query_or_url], "maxResults": lim}),
                ("memo23~taobao-scraper", {"searchQueries": [query_or_url], "maxProductsPerKeyword": max(5, lim)}),
            ]
        else:
            candidates = [
                ("zen-studio~alibaba-scraper", {"keyword": query_or_url, "maxItems": lim}),
            ]

        last_err: Exception | None = None
        for slug, payload in candidates:
            try:
                rows = self.run_sync_items(tokens, slug, payload, max_charge_usd=max_charge_usd)
                valid_norm = []
                for r in rows:
                    if not isinstance(r, dict) or r.get("retry_later") or r.get("error"):
                        continue
                    norm_c = self.normalize_china_item(r, plat)
                    if not norm_c["title"] or norm_c["title"] in ("拼多多商城", "淘宝网", "阿里巴巴", "1688.com"):
                        continue
                    valid_norm.append(norm_c)
                if valid_norm:
                    return slug, valid_norm[:lim]
            except Exception as exc:
                last_err = exc
                continue
        if last_err:
            raise last_err
        return candidates[0][0], []

    @staticmethod
    def normalize_china_item(r: dict, platform: str) -> dict:
        iid = safe_id_str(r.get("offerId") or r.get("item_id") or r.get("itemId") or r.get("num_iid") or r.get("goods_id") or r.get("id"))
        title = str(r.get("subject") or r.get("title") or r.get("goods_name") or r.get("name") or "").strip()
        raw_price = r.get("price") or r.get("wholesalePrice") or r.get("minPrice") or r.get("group_price") or 0
        if isinstance(raw_price, dict):
            raw_price = raw_price.get("min") or raw_price.get("price") or raw_price.get("max") or 0
        if not raw_price and isinstance(r.get("quantityPrices"), list) and r["quantityPrices"]:
            qp0 = r["quantityPrices"][0]
            if isinstance(qp0, dict):
                raw_price = qp0.get("price") or 0
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
        imgs = r.get("images") if isinstance(r.get("images"), list) else []
        img = str(r.get("imageUrl") or r.get("mainImageUrl") or r.get("pic_url") or r.get("image") or r.get("thumb_url") or (imgs[0] if imgs else "") or "").strip()
        if img.startswith("//"):
            img = "https:" + img
        seller_obj = r.get("seller") if isinstance(r.get("seller"), dict) else (r.get("supplier") if isinstance(r.get("supplier"), dict) else {})
        sup_name = str(
            r.get("companyName")
            or r.get("shopName")
            or r.get("shopTitle")
            or r.get("seller_nick")
            or r.get("sellerNick")
            or r.get("mall_name")
            or seller_obj.get("companyName")
            or seller_obj.get("shopName")
            or seller_obj.get("nick")
            or ""
        )
        return {
            "platform": platform,
            "native_item_id": iid,
            "title": title,
            "price_cny": price_cny,
            "moq": moq,
            "supplier_name": sup_name,
            "sales_volume": str(r.get("saleInfo") or r.get("bookedCount") or r.get("sold") or r.get("sales") or r.get("deal_cnt") or ""),
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

    def explore_google_trends(
        self,
        tokens: list[str],
        seed_terms: list[str],
        geo: str = "VN",
        time_range: str = "today 3-m",
        category: str = "",
        max_keywords: int = 16,
        max_charge_usd: float = 0.05,
    ) -> dict:
        """Explore Google Trends interest timeline, Rising/Breakout queries & Top related queries via Apify (#1 Priority)."""
        seeds = []
        for s in seed_terms or []:
            cleaned = str(s or "").strip().lstrip("#").strip()
            if cleaned and cleaned.lower() not in {x.lower() for x in seeds}:
                seeds.append(cleaned[:120])
        if not seeds:
            raise ApifyError("Vui lòng nhập ít nhất 1 từ khoá gốc để quét Google Trends", status=400)
        seeds = seeds[:5]
        cc = (geo or "VN").strip().upper()
        tr_map = {
            "7d": "now 7-d",
            "30d": "today 1-m",
            "90d": "today 3-m",
            "12m": "",
            "now 7-d": "now 7-d",
            "today 1-m": "today 1-m",
            "today 3-m": "today 3-m",
            "today 12-m": "",
        }
        apify_tr = tr_map.get(str(time_range or "today 3-m").strip(), "today 3-m")
        cat_clean = str(category or "").strip()

        p1: dict = {"searchTerms": seeds, "geo": cc, "viewedFrom": cc.lower(), "timeRange": apify_tr, "maxItems": max(1, len(seeds))}
        if cat_clean and cat_clean != "0":
            p1["category"] = cat_clean
        p2: dict = {
            "keywords": seeds,
            "geo": cc,
            "timeframe": apify_tr or "today 12-m",
            "category": int(cat_clean) if cat_clean.isdigit() else 0,
            "dataTypes": ["interest_over_time", "related_queries"],
            "maxResults": 100,
        }
        slug, raw_items = self._run_actor_ring(tokens, [("apify~google-trends-scraper", p1), ("khadinakbar~google-trends-scraper", p2)], max_charge_usd=max_charge_usd, timeout_sec=58)

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
                if growth_pct is not None and (ex.get("growth_pct") is None or growth_pct > ex["growth_pct"]):
                    ex["growth_pct"] = growth_pct
                if interest_score is not None and (ex.get("interest_value") is None or interest_score > ex["interest_value"]):
                    ex["interest_value"] = interest_score
                return
            kw_map[k_low] = {
                "keyword": t_clean,
                "kind": kind,
                "seed_term": seed_parent,
                "growth_label": growth_label,
                "growth_pct": growth_pct,
                "interest_value": interest_score,
                "source": f"apify:{slug}",
            }

        for row in raw_items:
            if not isinstance(row, dict):
                continue
            if "interestOverTime_timelineData" in row or "relatedQueries_rising" in row:
                sterm = str(row.get("searchTerm") or row.get("inputUrlOrTerm") or seeds[0]).strip()
                vals: list[float] = []
                for pt in (row.get("interestOverTime_timelineData") or []):
                    if isinstance(pt, dict):
                        v_arr = pt.get("value")
                        v0 = v_arr[0] if isinstance(v_arr, list) and v_arr else pt.get("value")
                        if isinstance(v0, (int, float)):
                            vals.append(float(v0))
                cur_v = round(vals[-1], 1) if vals else None
                avg_v = round(sum(vals) / len(vals), 1) if vals else None
                peak_v = round(max(vals), 1) if vals else None
                mom = 0.0
                if len(vals) >= 6:
                    sp_idx = max(2, len(vals) // 4)
                    rec_avg = sum(vals[-sp_idx:]) / sp_idx
                    pri_avg = sum(vals[:-sp_idx]) / max(1, len(vals[:-sp_idx]))
                    mom = round(((rec_avg - pri_avg) / max(pri_avg, 5.0)) * 100.0, 1)
                seed_summaries.append({
                    "seed_term": sterm,
                    "current_interest": cur_v,
                    "avg_interest": avg_v,
                    "peak_interest": peak_v,
                    "momentum_pct": mom,
                })
                _upsert_kw(sterm, "seed", sterm, f"{'+' if mom >= 0 else ''}{mom}%", mom, cur_v)
                for rq in (row.get("relatedQueries_rising") or [])[:12]:
                    if isinstance(rq, dict) and rq.get("query"):
                        rv = rq.get("value")
                        fv = str(rq.get("formattedValue") or "").strip()
                        is_bo = "breakout" in fv.lower() or "đột phá" in fv.lower() or (isinstance(rv, (int, float)) and rv >= 5000)
                        gp = float(rv) if isinstance(rv, (int, float)) else (5000.0 if is_bo else None)
                        lbl = "Đột phá (Breakout)" if is_bo and not fv.startswith("+") else (fv or (f"+{int(gp)}%" if gp else "Rising"))
                        _upsert_kw(rq["query"], "rising", sterm, lbl, gp, None)
                for tq in (row.get("relatedQueries_top") or [])[:10]:
                    if isinstance(tq, dict) and tq.get("query"):
                        vt = float(tq["value"]) if isinstance(tq.get("value"), (int, float)) else None
                        _upsert_kw(tq["query"], "top", sterm, f"Top {int(vt)}/100" if vt is not None else "Top Search", None, vt)
            else:
                q_txt = str(row.get("query") or row.get("term") or row.get("keyword") or "").strip()
                if q_txt:
                    rtype = str(row.get("type") or row.get("sub_type") or "").lower()
                    kind = "rising" if "rising" in rtype else "top"
                    vn = float(row["value"]) if isinstance(row.get("value"), (int, float)) else None
                    _upsert_kw(q_txt, kind, seeds[0], str(row.get("formatted_value") or ""), vn if kind == "rising" else None, vn if kind == "top" else None)

        ordered = sorted(
            kw_map.values(),
            key=lambda x: (2 if x["kind"] == "rising" else (1 if x["kind"] == "seed" else 0), float(x["growth_pct"] or 0.0), float(x["interest_value"] or 0.0)),
            reverse=True,
        )[: max(3, min(int(max_keywords or 16), 30))]

        return {
            "provider": "apify",
            "actor_or_endpoint": slug,
            "geo": cc,
            "time_range": apify_tr or "today 12-m",
            "seed_summaries": seed_summaries,
            "keywords": ordered,
            "cost_usd": round(0.012 * max(1, len(seeds)), 4),
        }

    # --- Social Painpoint Discovery (Facebook · Threads · X · Reddit) --------

    def search_social_painpoints(
        self,
        tokens: list[str],
        channel: str,
        query: str,
        limit: int = 8,
        max_charge_usd: float = 0.05,
    ) -> tuple[str, list[dict]]:
        ch = channel.lower().strip()
        lim = max(1, min(20, int(limit)))
        if ch in ("facebook", "facebook_organic"):
            candidates = [
                ("scraper_one~facebook-posts-search", {"query": query, "resultsCount": lim}),
                ("apify~facebook-search-scraper", {"categories": [query], "searchType": "posts", "resultsLimit": lim}),
            ]
        elif ch == "facebook_ads":
            candidates = [
                ("automation-lab~facebook-ads-library", {"searchTerms": [query], "country": "VN", "maxItems": lim}),
                ("apify~facebook-ads-scraper", {"searchQuery": query, "country": "VN", "maxItems": lim}),
            ]
        elif ch == "threads":
            candidates = [
                ("futurizerush~meta-threads-scraper", {"mode": "search", "keywords": [query], "max_posts": lim}),
                ("watcher.data~search-threads-by-keywords", {"keywords": [query], "maxItemsPerKeyword": lim}),
                ("igview-owner~threads-search-scraper", {"searchQuery": query, "sort": "top"}),
            ]
        elif ch in ("x", "twitter"):
            candidates = [
                ("apidojo~tweet-scraper", {"searchTerms": [query], "maxItems": lim}),
            ]
        elif ch == "reddit":
            candidates = [
                ("trudax~reddit-scraper-lite", {"searches": [query], "maxItems": lim}),
            ]
        else:
            raise ApifyError(f"Kênh MXH chưa hỗ trợ: {channel}", status=400)

        slug, rows = self._run_actor_ring(tokens, candidates, max_charge_usd=max_charge_usd, timeout_sec=52)
        out = []
        for r in rows[:lim]:
            if not isinstance(r, dict):
                continue
            txt = str(
                r.get("text")
                or r.get("fullText")
                or r.get("body")
                or r.get("selftext")
                or r.get("adText")
                or r.get("caption")
                or r.get("description")
                or r.get("title")
                or ""
            ).strip()
            title_h = str(r.get("title") or "").strip()
            if title_h and title_h not in txt:
                txt = f"{title_h} — {txt}".strip(" —")
            if not txt:
                continue
            author_obj = r.get("author") if isinstance(r.get("author"), dict) else (r.get("user") if isinstance(r.get("user"), dict) else {})
            author = str(
                author_obj.get("userName")
                or author_obj.get("username")
                or author_obj.get("name")
                or r.get("username")
                or r.get("authorName")
                or r.get("pageName")
                or r.get("communityName")
                or ""
            ).strip()
            url = str(
                r.get("url")
                or r.get("postUrl")
                or r.get("twitterUrl")
                or r.get("linkUrl")
                or r.get("permalink")
                or ""
            ).strip()
            out.append({
                "channel": "facebook_organic" if ch == "facebook" else ("x" if ch == "twitter" else ch),
                "author": author,
                "text": txt[:900],
                "url": url,
                "likes": parse_int_metric(r.get("likes") or r.get("likeCount") or r.get("upVotes") or r.get("reactionsCount") or 0),
                "comments": parse_int_metric(r.get("comments") or r.get("replyCount") or r.get("numberOfComments") or r.get("commentsCount") or 0),
                "shares": parse_int_metric(r.get("shares") or r.get("retweetCount") or r.get("repostCount") or 0),
                "source": f"apify:{slug}",
            })
        return slug, out
