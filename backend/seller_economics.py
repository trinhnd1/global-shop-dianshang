"""Decimal-accurate Seller Unit Economics & China Landed Cost (CNY -> VND) Calculator."""
from decimal import Decimal, ROUND_HALF_UP


def _d(val, default: str = "0") -> Decimal:
    if val is None or val == "" or isinstance(val, bool):
        return Decimal(default)
    return Decimal(str(val))


def _q0(val: Decimal) -> float:
    return float(val.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _q2(val: Decimal) -> float:
    return float(val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def calculate_china_landed_cost(
    price_cny,
    cny_rate=3650,
    domestic_cn_ship_cny=0,
    weight_kg=0.4,
    cn_vn_ship_per_kg_vnd=28000,
    buying_agent_fee_pct=2.5,
    extra_import_cost_vnd=0,
) -> dict:
    """Compute exact VND landed cost per unit imported from 1688 / Taobao / Pinduoduo."""
    p_cny = max(Decimal("0"), _d(price_cny))
    rate = max(Decimal("1"), _d(cny_rate, "3650"))
    dom_cny = max(Decimal("0"), _d(domestic_cn_ship_cny))
    w_kg = max(Decimal("0"), _d(weight_kg, "0.4"))
    ship_kg = max(Decimal("0"), _d(cn_vn_ship_per_kg_vnd, "28000"))
    agent_pct = max(Decimal("0"), _d(buying_agent_fee_pct, "2.5")) / Decimal("100")
    extra_vnd = max(Decimal("0"), _d(extra_import_cost_vnd))

    goods_vnd = (p_cny + dom_cny) * rate
    agent_fee_vnd = goods_vnd * agent_pct
    intl_shipping_vnd = w_kg * ship_kg
    landed_vnd = goods_vnd + agent_fee_vnd + intl_shipping_vnd + extra_vnd

    return {
        "price_cny": _q2(p_cny),
        "domestic_cn_ship_cny": _q2(dom_cny),
        "cny_to_vnd_rate": _q0(rate),
        "goods_base_vnd": _q0(goods_vnd),
        "agent_fee_vnd": _q0(agent_fee_vnd),
        "intl_shipping_vnd": _q0(intl_shipping_vnd),
        "extra_import_cost_vnd": _q0(extra_vnd),
        "landed_cost_vnd": _q0(landed_vnd),
        "recommended_retail_min_vnd": _q0(landed_vnd * Decimal("2.2")),
        "recommended_retail_ideal_vnd": _q0(landed_vnd * Decimal("2.8")),
    }


def evaluate_seller_economics(params: dict, defaults: dict | None = None) -> dict:
    """Evaluate unit profit, net margin %, ROI on COGS, and break-even Ads ROAS for Shopee / TikTok Shop sellers."""
    dflt = defaults or {}
    platform = str(params.get("platform") or "shopee").lower()
    default_fee = dflt.get("tiktok_shop_fee_pct", 11.5) if "tiktok" in platform else dflt.get("shopee_fee_pct", 12.5)

    sell_price = max(Decimal("0"), _d(params.get("sell_price_vnd") or params.get("price_vnd"), "0"))
    if params.get("price_cny") is not None and not params.get("cost_vnd"):
        lc = calculate_china_landed_cost(
            price_cny=params.get("price_cny"),
            cny_rate=params.get("cny_to_vnd_rate") or dflt.get("cny_to_vnd_rate", 3650),
            domestic_cn_ship_cny=params.get("domestic_cn_ship_cny", 0),
            weight_kg=params.get("weight_kg") or dflt.get("default_weight_kg", 0.4),
            cn_vn_ship_per_kg_vnd=params.get("cn_shipping_per_kg_vnd") or dflt.get("cn_shipping_per_kg_vnd", 28000),
            buying_agent_fee_pct=params.get("buying_agent_fee_pct") or dflt.get("buying_agent_fee_pct", 2.5),
        )
        cogs_vnd = _d(lc["landed_cost_vnd"])
    else:
        lc = None
        cogs_vnd = max(Decimal("0"), _d(params.get("cost_vnd"), "0"))

    platform_fee_pct = max(Decimal("0"), _d(params.get("platform_fee_pct"), str(default_fee))) / Decimal("100")
    packaging_vnd = max(Decimal("0"), _d(params.get("packaging_cost_vnd"), str(dflt.get("packaging_cost_vnd", 3500))))
    ads_cost_per_order = max(Decimal("0"), _d(params.get("ads_cost_per_order_vnd"), "0"))
    return_pct = min(Decimal("0.95"), max(Decimal("0"), _d(params.get("return_pct"), str(dflt.get("default_return_pct", 6.0))) / Decimal("100")))

    effective_revenue = sell_price * (Decimal("1") - return_pct)
    platform_fee_vnd = effective_revenue * platform_fee_pct
    return_loss_vnd = (packaging_vnd + Decimal("15000")) * return_pct

    gross_profit_before_ads = effective_revenue - cogs_vnd - platform_fee_vnd - packaging_vnd - return_loss_vnd
    net_profit_vnd = gross_profit_before_ads - ads_cost_per_order

    net_margin_pct = (net_profit_vnd / sell_price * Decimal("100")) if sell_price > 0 else Decimal("0")
    roi_on_cogs_pct = (net_profit_vnd / cogs_vnd * Decimal("100")) if cogs_vnd > 0 else Decimal("0")
    breakeven_roas = (sell_price / gross_profit_before_ads) if gross_profit_before_ads > 0 else Decimal("99.99")

    scenarios = []
    for orders_mo in (100, 500, 2000):
        qty = Decimal(str(orders_mo))
        scenarios.append({
            "monthly_orders": orders_mo,
            "working_capital_cogs_vnd": _q0(cogs_vnd * qty),
            "monthly_gmv_vnd": _q0(sell_price * qty),
            "monthly_net_profit_vnd": _q0(net_profit_vnd * qty),
        })

    verdict = "chua_du_gia_von"
    if sell_price > 0 and cogs_vnd > 0:
        if net_margin_pct >= Decimal("22"):
            verdict = "loi_nhuan_tot_nen_nhap"
        elif net_margin_pct >= Decimal("12"):
            verdict = "bien_mong_can_toi_uu_gia_xuong"
        else:
            verdict = "lo_hoac_bien_qua_thap"

    return {
        "platform": platform,
        "sell_price_vnd": _q0(sell_price),
        "cogs_vnd": _q0(cogs_vnd),
        "effective_revenue_vnd": _q0(effective_revenue),
        "platform_fee_vnd": _q0(platform_fee_vnd),
        "packaging_cost_vnd": _q0(packaging_vnd),
        "return_loss_vnd": _q0(return_loss_vnd),
        "ads_cost_per_order_vnd": _q0(ads_cost_per_order),
        "gross_profit_before_ads_vnd": _q0(gross_profit_before_ads),
        "net_profit_per_order_vnd": _q0(net_profit_vnd),
        "net_margin_pct": _q2(net_margin_pct),
        "roi_on_cogs_pct": _q2(roi_on_cogs_pct),
        "max_ads_cpa_breakeven_vnd": _q0(max(Decimal("0"), gross_profit_before_ads)),
        "breakeven_ads_roas": _q2(breakeven_roas),
        "verdict": verdict,
        "china_landed_breakdown": lc,
        "monthly_scenarios": scenarios,
    }
