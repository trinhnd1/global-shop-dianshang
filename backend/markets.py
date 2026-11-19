"""Explicit Multi-Market Catalog & Currency / URL Helpers for Shopee & TikTokShop (VN, PH, SG, MY, TH) + Global Channels."""
import re
from urllib.parse import parse_qs, urlparse

SEA_MARKETS: dict[str, dict] = {
    "VN": {
        "code": "VN",
        "flag": "🇻🇳",
        "name": "Việt Nam",
        "currency": "VND",
        "symbol": "₫",
        "fx_to_vnd": 1.0,
        "shopee_domain": "shopee.vn",
        "shopee_overseas_label": "Nước ngoài",
        "shopee_domestic_loc": "-1",
        "tiktok_region": "VN",
        "tiktok_market": "vn",
    },
    "PH": {
        "code": "PH",
        "flag": "🇵🇭",
        "name": "Philippines",
        "currency": "PHP",
        "symbol": "₱",
        "fx_to_vnd": 440.0,
        "shopee_domain": "shopee.ph",
        "shopee_overseas_label": "Mainland China",
        "shopee_domestic_loc": "Local",
        "tiktok_region": "PH",
        "tiktok_market": "ph",
    },
    "SG": {
        "code": "SG",
        "flag": "🇸🇬",
        "name": "Singapore",
        "currency": "SGD",
        "symbol": "S$",
        "fx_to_vnd": 18900.0,
        "shopee_domain": "shopee.sg",
        "shopee_overseas_label": "Mainland China",
        "shopee_domestic_loc": "Singapore",
        "tiktok_region": "SG",
        "tiktok_market": "sg",
    },
    "MY": {
        "code": "MY",
        "flag": "🇲🇾",
        "name": "Malaysia",
        "currency": "MYR",
        "symbol": "RM",
        "fx_to_vnd": 5700.0,
        "shopee_domain": "shopee.com.my",
        "shopee_overseas_label": "Mainland China",
        "shopee_domestic_loc": "Local",
        "tiktok_region": "MY",
        "tiktok_market": "my",
    },
    "TH": {
        "code": "TH",
        "flag": "🇹🇭",
        "name": "Thái Lan",
        "currency": "THB",
        "symbol": "฿",
        "fx_to_vnd": 740.0,
        "shopee_domain": "shopee.co.th",
        "shopee_overseas_label": "ต่างประเทศ",
        "shopee_domestic_loc": "ภายในประเทศ",
        "tiktok_region": "TH",
        "tiktok_market": "th",
    },
}

EXPLICIT_MARKETPLACE_CHANNELS: dict[str, dict] = {
    # Shopee 5 markets
    "shopee_vn": {"platform": "shopee", "market": "VN", "label": "Shopee VN", "full_label": "🇻🇳 Shopee VN", "icon": "🛍", "default_fee_pct": 12.5},
    "shopee_ph": {"platform": "shopee", "market": "PH", "label": "Shopee PH", "full_label": "🇵🇭 Shopee PH", "icon": "🛍", "default_fee_pct": 12.0},
    "shopee_sg": {"platform": "shopee", "market": "SG", "label": "Shopee SG", "full_label": "🇸🇬 Shopee SG", "icon": "🛍", "default_fee_pct": 11.5},
    "shopee_my": {"platform": "shopee", "market": "MY", "label": "Shopee MY", "full_label": "🇲🇾 Shopee MY", "icon": "🛍", "default_fee_pct": 12.0},
    "shopee_th": {"platform": "shopee", "market": "TH", "label": "Shopee TH", "full_label": "🇹🇭 Shopee TH", "icon": "🛍", "default_fee_pct": 12.0},
    # TikTokShop 5 markets
    "tiktok_shop_vn": {"platform": "tiktok_shop", "market": "VN", "label": "TikTokShop VN", "full_label": "🇻🇳 TikTokShop VN", "icon": "🛒", "default_fee_pct": 11.5},
    "tiktok_shop_ph": {"platform": "tiktok_shop", "market": "PH", "label": "TikTokShop PH", "full_label": "🇵🇭 TikTokShop PH", "icon": "🛒", "default_fee_pct": 11.0},
    "tiktok_shop_sg": {"platform": "tiktok_shop", "market": "SG", "label": "TikTokShop SG", "full_label": "🇸🇬 TikTokShop SG", "icon": "🛒", "default_fee_pct": 10.5},
    "tiktok_shop_my": {"platform": "tiktok_shop", "market": "MY", "label": "TikTokShop MY", "full_label": "🇲🇾 TikTokShop MY", "icon": "🛒", "default_fee_pct": 11.0},
    "tiktok_shop_th": {"platform": "tiktok_shop", "market": "TH", "label": "TikTokShop TH", "full_label": "🇹🇭 TikTokShop TH", "icon": "🛒", "default_fee_pct": 11.0},
    # Other channels
    "lazada": {"platform": "lazada", "market": "VN", "label": "Lazada VN", "full_label": "📦 Lazada VN", "icon": "📦", "default_fee_pct": 11.0},
}

SHOPEE_DOMAIN_TO_MARKET = {
    "shopee.vn": "VN",
    "shopee.ph": "PH",
    "shopee.sg": "SG",
    "shopee.com.my": "MY",
    "shopee.co.th": "TH",
}


def normalize_market_code(raw_market: str | None, default: str = "VN") -> str:
    m = (raw_market or "").strip().upper()
    return m if m in SEA_MARKETS else default


def detect_market_from_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    low = u.lower()
    for dom, mkt in SHOPEE_DOMAIN_TO_MARKET.items():
        if dom in low:
            return mkt
    if "lazada.com.ph" in low:
        return "PH"
    if "lazada.sg" in low:
        return "SG"
    if "lazada.com.my" in low:
        return "MY"
    if "lazada.co.th" in low:
        return "TH"
    try:
        parsed = urlparse(u if "://" in u else f"https://{u}")
        qs = parse_qs(parsed.query)
        reg = (qs.get("region") or qs.get("country") or [""])[0].strip().upper()
        if reg in SEA_MARKETS:
            return reg
    except Exception:
        pass
    return ""


def parse_marketplace_spec(raw_channel: str | None, raw_market: str | None = None, url: str = "") -> tuple[str, str, str]:
    """Normalize any channel/platform string + optional market/URL into `(base_platform, market, channel_code)`.

    Examples:
      - `("shopee", None)` -> `("shopee", "VN", "shopee_vn")`
      - `("shopee_ph", None)` -> `("shopee", "PH", "shopee_ph")`
      - `("tiktokshop_sg", None)` -> `("tiktok_shop", "SG", "tiktok_shop_sg")`
      - `("tiktok_shop", "TH")` -> `("tiktok_shop", "TH", "tiktok_shop_th")`
    """
    ch = (raw_channel or "").strip().lower().replace("-", "_").replace(" ", "_")
    url_mkt = detect_market_from_url(url)
    explicit_mkt = (raw_market or "").strip().upper()

    # Check suffix _vn, _ph, _sg, _my, _th
    suffix_mkt = ""
    for mcode in ("vn", "ph", "sg", "my", "th"):
        if ch.endswith(f"_{mcode}"):
            suffix_mkt = mcode.upper()
            ch = ch[: -(len(mcode) + 1)]
            break

    if ch in ("tiktok", "tiktokshop", "tiktok_shop", "tts"):
        base_plat = "tiktok_shop"
    elif ch in ("shopee",):
        base_plat = "shopee"
    elif ch in ("lazada",):
        base_plat = "lazada"
    elif ch in ("facebook", "fanpage", "fb", "fb_fanpage", "facebook_fanpage"):
        base_plat = "facebook_fanpage"
    elif ch in ("tiktok_channel",):
        base_plat = "tiktok_channel"
    elif ch in ("instagram", "ig"):
        base_plat = "instagram"
    elif ch in ("website", "web"):
        base_plat = "website"
    elif ch in ("1688", "pinduoduo", "taobao"):
        return ch, "CN", ch
    else:
        base_plat = ch or "shopee"

    mkt = suffix_mkt or (explicit_mkt if explicit_mkt in SEA_MARKETS else "") or url_mkt or "VN"
    if base_plat in ("shopee", "tiktok_shop"):
        return base_plat, mkt, f"{base_plat}_{mkt.lower()}"
    return base_plat, mkt, base_plat


def format_platform_market_label(platform: str, market: str = "VN") -> str:
    p = (platform or "").strip().lower()
    m = (market or "VN").strip().upper()
    info = SEA_MARKETS.get(m, SEA_MARKETS["VN"])
    if p == "shopee":
        return f"{info['flag']} Shopee {m}"
    if p == "tiktok_shop":
        return f"{info['flag']} TikTokShop {m}"
    if p == "tiktok_channel":
        return f"{info['flag']} Kênh TikTok {m}"
    if p == "facebook_fanpage":
        return "📘 Facebook Fanpage"
    if p == "lazada":
        return f"📦 Lazada {m}"
    if p in ("1688", "pinduoduo", "taobao"):
        return f"🇨🇳 {p.upper()}"
    return f"{p.upper()} ({m})"


def shopee_domain_for_market(market: str) -> str:
    m = normalize_market_code(market, "VN")
    return SEA_MARKETS[m]["shopee_domain"]


def convert_local_price_to_vnd(local_price: float, market: str, custom_rates: dict | None = None) -> tuple[float, str, float]:
    """Return `(price_vnd, currency_code, fx_rate)` for a given SEA market."""
    m = normalize_market_code(market, "VN")
    info = SEA_MARKETS[m]
    ccy = info["currency"]
    rate = float((custom_rates or {}).get(f"{ccy.lower()}_to_vnd") or info["fx_to_vnd"])
    if m == "VN":
        return round(float(local_price or 0.0), 0), "VND", 1.0
    return round(float(local_price or 0.0) * rate, 0), ccy, rate
