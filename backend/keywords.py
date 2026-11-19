"""Shopee & TikTok Keyword Research Tool: suggestions, listing volume, price/sales distribution, Mall saturation & Jev Opportunity Score."""
import json
import statistics
import urllib.parse
import urllib.request
import uuid

from . import settings
from .responses import ApiError, json_object, now, text


class KeywordResearchService:
    def __init__(self, connect, secrets, products, apify=None, treg=None, jev=None):
        self.connect = connect
        self.secrets = secrets
        self.products = products
        self.apify = apify
        self.treg = treg
        self.jev = jev

    def fetch_shopee_suggestions(self, keyword: str) -> list[str]:
        """Query public Shopee VN search autocomplete hints + curated modifier suffixes."""
        kw = keyword.strip()
        if not kw:
            return []
        suggestions: list[str] = []
        try:
            qs = urllib.parse.urlencode({"prefix": kw, "limit": 10, " country": "vn"})
            req = urllib.request.Request(
                f"https://shopee.vn/api/v4/search/search_hint?{qs}",
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for h in (data.get("data") or {}).get("hints") or []:
                    s = str(h.get("keyword") or "").strip()
                    if s and s not in suggestions:
                        suggestions.append(s)
        except Exception:
            pass
        # Deterministic high-intent buyer modifiers in Vietnamese e-commerce
        for mod in ("cao cấp", "mini", "đa năng", "chính hãng", "thông minh", "giá rẻ", "combo"):
            cand = f"{kw} {mod}"
            if cand not in suggestions and len(suggestions) < 12:
                suggestions.append(cand)
        return suggestions[:12]

    def research_keyword(
        self,
        keyword: str,
        platform: str = "shopee",
        limit: int = 20,
        score_jev: bool = True,
        save_top_to_vault: bool = True,
    ) -> dict:
        kw = text(keyword, "keyword", 120, required=True)
        plat = platform.lower().strip()
        if plat not in ("shopee", "tiktok", "tiktok_shop"):
            raise ValueError("Nền tảng tra cứu từ khoá phải là shopee hoặc tiktok")
        norm_plat = "tiktok_shop" if plat in ("tiktok", "tiktok_shop") else "shopee"
        lim = max(5, min(40, int(limit)))

        cfg = settings.read_settings(self.connect, self.secrets)
        apify_toks = settings.apify_tokens(cfg)
        treg_tok = (cfg["providers"].get("treg_key") or "").strip()
        max_chg = float(cfg["providers"].get("apify_max_charge_usd") or 0.06)

        items: list[dict] = []
        source_used = "none"

        if norm_plat == "shopee":
            if apify_toks and self.apify:
                try:
                    slug, items = self.apify.search_shopee(apify_toks, kw, limit=lim, max_charge_usd=max_chg)
                    source_used = f"apify:{slug}"
                except Exception:
                    items = []
            if not items and treg_tok and self.treg:
                try:
                    res = self.treg.call(treg_tok, "treg.google.serp.organic", {"q": f"site:shopee.vn {kw}", "num": lim})
                    for idx, r in enumerate(self.treg._extract_list(res)[:lim], start=1):
                        u = str(r.get("link") or r.get("url") or "")
                        items.append({
                            "platform": "shopee",
                            "market": "VN",
                            "native_product_id": f"serp_{idx}_{ abs(hash(u)) % 10000000 }",
                            "native_shop_id": "",
                            "shop_name": "Shopee Seller",
                            "is_mall": "mall" in str(r.get("title") or "").lower(),
                            "title": str(r.get("title") or "").replace(" | Shopee Việt Nam", "").strip(),
                            "price_vnd": 0.0,
                            "sold_count": 0,
                            "gmv_vnd": 0.0,
                            "rating": 0.0,
                            "url": u,
                            "image_url": "",
                        })
                    source_used = "treg:google_serp_shopee"
                except Exception:
                    pass
        else:
            if apify_toks and self.apify:
                try:
                    slug, items = self.apify.search_tiktok_shop(apify_toks, kw, limit=lim, max_charge_usd=max_chg)
                    source_used = f"apify:{slug}"
                except Exception:
                    items = []
            if not items and treg_tok and self.treg:
                try:
                    ep, items, _ = self.treg.search_tiktok_shop(treg_tok, kw, limit=lim)
                    source_used = f"treg:{ep}"
                except Exception:
                    pass

        suggestions = self.fetch_shopee_suggestions(kw)
        prices = [float(x["price_vnd"]) for x in items if float(x.get("price_vnd") or 0) > 0]
        total_sold = sum(int(x.get("sold_count") or 0) for x in items)
        total_gmv = sum(float(x.get("gmv_vnd") or 0.0) for x in items)
        mall_cnt = sum(1 for x in items if x.get("is_mall"))
        hints = [int(x.get("total_available_hint") or 0) for x in items if int(x.get("total_available_hint") or 0) > 0]
        total_products_est = max(hints) if hints else len(items)

        shop_sales: dict[str, int] = {}
        for x in items:
            sn = x.get("shop_name") or x.get("native_shop_id") or "unknown"
            shop_sales[sn] = shop_sales.get(sn, 0) + int(x.get("sold_count") or 0)
        sorted_shops = sorted(shop_sales.items(), key=lambda kv: kv[1], reverse=True)
        top3_sold = sum(v for _, v in sorted_shops[:3])
        top3_concentration_pct = round((top3_sold / total_sold * 100.0), 1) if total_sold > 0 else 0.0

        summary = {
            "keyword": kw,
            "platform": norm_plat,
            "source_used": source_used,
            "total_products": total_products_est,
            "sampled_count": len(items),
            "total_sold_sample": total_sold,
            "total_gmv_sample_vnd": round(total_gmv, 0),
            "avg_price_vnd": round(statistics.mean(prices), 0) if prices else 0.0,
            "median_price_vnd": round(statistics.median(prices), 0) if prices else 0.0,
            "min_price_vnd": round(min(prices), 0) if prices else 0.0,
            "max_price_vnd": round(max(prices), 0) if prices else 0.0,
            "mall_share_pct": round((mall_cnt / len(items) * 100.0), 1) if items else 0.0,
            "top3_shop_concentration_pct": top3_concentration_pct,
            "top_shops": [{"shop_name": k, "sold_count": v} for k, v in sorted_shops[:5]],
        }

        jev_eval = None
        typesafe_key = (cfg["providers"].get("typesafe_key") or "").strip()
        if score_jev and typesafe_key and self.jev and items:
            try:
                jev_eval = self.jev.score_keyword_opportunity(
                    typesafe_key,
                    summary,
                    model=cfg["providers"].get("jev_model") or "jev-1.14.0",
                    base_url=cfg["providers"].get("jev_base_url") or "https://api.typesafe.ai/v1/systemone",
                )
                summary["jev_evaluation"] = jev_eval
            except Exception as exc:
                summary["jev_error"] = str(exc)[:160]

        saved_ids = []
        if save_top_to_vault and items:
            for it in items:
                if it.get("title"):
                    p = self.products.upsert_product(it, source=f"keyword:{norm_plat}:{kw}")
                    saved_ids.append(p["id"])

        rid = f"kwr_{uuid.uuid4().hex[:10]}"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO keyword_researches
                (research_id, platform, market, keyword, total_products, sampled_count, total_sold_sample,
                 avg_price_vnd, min_price_vnd, max_price_vnd, mall_share_pct, jev_opportunity_score,
                 suggestions_json, items_json, summary_json, created_at)
                VALUES (?, ?, 'VN', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rid,
                    norm_plat,
                    kw,
                    total_products_est,
                    len(items),
                    total_sold,
                    summary["avg_price_vnd"],
                    summary["min_price_vnd"],
                    summary["max_price_vnd"],
                    summary["mall_share_pct"],
                    jev_eval["opportunity_score_10"] if jev_eval else None,
                    json.dumps(suggestions, ensure_ascii=False),
                    json.dumps(items, ensure_ascii=False),
                    json.dumps(summary, ensure_ascii=False),
                    now(),
                ),
            )

        return {
            "research_id": rid,
            "keyword": kw,
            "platform": norm_plat,
            "summary_stats": summary,
            "suggestions": suggestions,
            "items": items,
            "saved_product_ids": saved_ids,
            "summary": f"Từ khoá '{kw}' ({norm_plat}): {total_products_est} SP, mẫu {len(items)} SP, tổng bán {total_sold}",
        }

    def list_history(self, limit: int = 30) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM keyword_researches ORDER BY created_at DESC LIMIT ?",
                (min(100, max(1, int(limit))),),
            ).fetchall()
        return [
            {
                "research_id": r["research_id"],
                "platform": r["platform"],
                "keyword": r["keyword"],
                "total_products": r["total_products"],
                "sampled_count": r["sampled_count"],
                "total_sold_sample": r["total_sold_sample"],
                "avg_price_vnd": r["avg_price_vnd"],
                "mall_share_pct": r["mall_share_pct"],
                "jev_opportunity_score": r["jev_opportunity_score"],
                "suggestions": json.loads(r["suggestions_json"] or "[]"),
                "summary_stats": json.loads(r["summary_json"] or "{}"),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def get_detail(self, research_id: str) -> dict:
        with self.connect() as conn:
            r = conn.execute("SELECT * FROM keyword_researches WHERE research_id=?", (research_id,)).fetchone()
        if not r:
            raise ApiError("404 Not Found", "Không tìm thấy kết quả tra cứu từ khoá")
        return {
            "research_id": r["research_id"],
            "platform": r["platform"],
            "keyword": r["keyword"],
            "summary_stats": json.loads(r["summary_json"] or "{}"),
            "suggestions": json.loads(r["suggestions_json"] or "[]"),
            "items": json.loads(r["items_json"] or "[]"),
            "created_at": r["created_at"],
        }

    def dispatch(self, path: str, method: str, env, read_json):
        if path == "/api/keywords/history" and method == "GET":
            return "200 OK", {"researches": self.list_history()}
        if path == "/api/keywords/suggest" and method == "POST":
            body = json_object(read_json, env)
            kw = text(body.get("keyword"), "keyword", 120, required=True)
            return "200 OK", {"keyword": kw, "suggestions": self.fetch_shopee_suggestions(kw)}
        if path == "/api/keywords/research" and method == "POST":
            body = json_object(read_json, env)
            return "200 OK", self.research_keyword(
                keyword=text(body.get("keyword"), "keyword", 120, required=True),
                platform=str(body.get("platform") or "shopee"),
                limit=int(body.get("limit") or 20),
                score_jev=bool(body.get("score_jev", True)),
                save_top_to_vault=bool(body.get("save_top_to_vault", False)),
            )
        if path.startswith("/api/keywords/history/") and method == "GET":
            rid = path.strip("/").split("/")[3]
            return "200 OK", self.get_detail(rid)
        return None
