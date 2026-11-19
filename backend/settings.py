"""Application settings separated strictly into Non-Sensitive SQLite Config + SecretStore secrets."""
import copy
import json
import secrets
import threading
import uuid

from .responses import now
from .secret_store import SecretStore

DEFAULT_NICHES = [
    "Gia dụng thông minh",
    "Nhà cửa & Đời sống",
    "Sức khoẻ & Làm đẹp",
    "Thời trang & Phụ kiện",
    "Phụ kiện Công nghệ & Điện tử",
    "Mẹ & Bé",
    "Làm vườn & Hạt giống",
    "Thú cưng",
    "Đồ ăn vặt & Thực phẩm",
    "Thể thao & Dã ngoại",
]

MARKETS = {
    "VN": "Việt Nam",
    "SEA": "Đông Nam Á",
    "US": "Hoa Kỳ (Global)",
    "CN": "Nội địa Trung Quốc (Nguồn hàng)",
}

ALL_CHANNELS = (
    "shopee",
    "tiktok",
    "tiktok_shop",
    "lazada",
    "1688",
    "taobao",
    "pinduoduo",
    "douyin",
    "facebook_ads",
    "facebook_organic",
    "google_trends",
)

MCP_SCOPES = (
    "system",
    "hunt_keywords",
    "watches",
    "products",
    "china_sourcing",
    "shops",
    "videos",
    "campaigns_sales",
)

NON_SENSITIVE_DEFAULTS = {
    "providers": {
        "treg_max_cost_usd": 0.03,
        "apify_max_charge_usd": 0.06,
        "apify_keys_meta": [],
        "jev_model": "jev-1.14.0",
        "jev_base_url": "https://api.typesafe.ai/v1/systemone",
        "jev_route_policy": "direct",
    },
    "hunt": {
        "country": "VN",
        "language": "vi",
        "channels": ["shopee", "tiktok", "lazada", "facebook_ads"],
        "items_per_channel": 8,
        "score_gate": 7.0,
        "auto_score_jev": True,
        "max_session_cost_usd": 0.30,
        "max_retries": 2,
        "niches": list(DEFAULT_NICHES),
    },
    "sourcing": {
        "cny_to_vnd_rate": 3650.0,
        "cn_shipping_per_kg_vnd": 28000.0,
        "default_weight_kg": 0.4,
        "buying_agent_fee_pct": 2.5,
        "shopee_fee_pct": 12.5,
        "tiktok_shop_fee_pct": 11.5,
        "packaging_cost_vnd": 3500.0,
        "default_return_pct": 6.0,
        "target_net_margin_pct": 22.0,
    },
    "llm": {
        "preset": "custom",
        "base_url": "",
        "model": "",
    },
    "kalodata": {
        "market": "VN",
        "currency": "VND",
        "account_email": "",
        "default_window_days": 7,
    },
    "notify": {
        "telegram_enabled": True,
        "telegram_bot_username": "tc_global1_shop_bot",
        "telegram_chat_id": "5608975895",
        "telegram_allowed_user_ids": "5608975895",
        "notify_on_job_start": True,
        "notify_on_job_finish": True,
        "notify_on_activity_log": True,
        "notify_on_watch_new_items": True,
        "daily_brief_enabled": True,
        "daily_brief_hour": 8,
        "daily_brief_minute": 0,
        "result_base_url": "",
    },
    "mcp": {
        "enabled": True,
        "auth_required": True,
        "allow_loopback_without_token": False,
        "allow_tailscale": True,
        "access_mode": "full_control",
        "audit_log_enabled": True,
        "enabled_scopes": list(MCP_SCOPES),
    },
}

SINGLE_SECRETS = {
    ("providers", "treg_key"): "providers.treg_key",
    ("providers", "typesafe_key"): "providers.typesafe_key",
    ("llm", "api_key"): "llm.api_key",
    ("kalodata", "password"): "kalodata.password",
    ("kalodata", "session_cookie"): "kalodata.session_cookie",
    ("notify", "telegram_token"): "notify.telegram_token",
    ("mcp", "auth_token"): "mcp.auth_token",
}

FULL_MASK_SECRETS = {
    ("kalodata", "password"),
    ("kalodata", "session_cookie"),
}

_save_lock = threading.Lock()
MASK = "•" * 8


def clean_secret_input(raw: str) -> str:
    s = (raw or "").strip()
    for prefix in ("卡号：", "卡号:", "密码：", "密码:", "Token:", "token:"):
        if s.startswith(prefix):
            s = s[len(prefix):].strip()
    return s


def clean_account_input(raw: str) -> str:
    s = (raw or "").strip()
    for prefix in ("账号：", "账号:", "帳號：", "帳號:", "Email:", "email:"):
        if s.startswith(prefix):
            s = s[len(prefix):].strip()
    return s


def mask(value: str, reveal_last4: bool = True) -> str:
    if not isinstance(value, str) or not value:
        return ""
    if not reveal_last4:
        return MASK
    return MASK + value[-4:] if len(value) >= 12 else MASK


def is_masked(value) -> bool:
    return isinstance(value, str) and value.startswith(MASK)


def resolve_secret(incoming, stored: str, label: str, reveal_last4: bool = True) -> str:
    if incoming is None:
        return ""
    if incoming == "" or (is_masked(incoming) and incoming == mask(stored or "", reveal_last4=reveal_last4)):
        return stored if isinstance(stored, str) else ""
    if is_masked(incoming):
        raise ValueError(f"{label} đang ở dạng che và không khớp khoá đã lưu — vui lòng nhập lại khoá mới")
    if not isinstance(incoming, str):
        raise ValueError(f"{label} phải là chuỗi ký tự")
    return clean_secret_input(incoming)


def resolve_incoming_secret(incoming, stored: str, label: str = "API Key") -> str:
    val = resolve_secret(incoming, stored, label)
    if not val:
        raise ValueError(f"Chưa cấu hình {label}")
    return val


def ensure_mcp_token(secret_store: SecretStore) -> str:
    cur = secret_store.get("mcp.auth_token")
    if cur:
        return cur
    tok = "gs_mcp_" + secrets.token_hex(18)
    secret_store.set("mcp.auth_token", tok)
    return tok


def _read_non_sensitive(connect) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE name='application'").fetchone()
    result = copy.deepcopy(NON_SENSITIVE_DEFAULTS)
    if row:
        saved = json.loads(row["value"])
        for grp, vals in saved.items():
            if grp in result and isinstance(vals, dict):
                for k, v in vals.items():
                    if k in result[grp]:
                        result[grp][k] = v
    return result


def read_settings(connect, secret_store: SecretStore) -> dict:
    ensure_mcp_token(secret_store)
    cfg = _read_non_sensitive(connect)
    for (grp, fld), skey in SINGLE_SECRETS.items():
        cfg[grp][fld] = secret_store.get(skey)
    apify_list = []
    for item in cfg["providers"].get("apify_keys_meta") or []:
        if isinstance(item, dict) and item.get("id"):
            tok = secret_store.get(f"apify.key.{item['id']}")
            apify_list.append({**item, "token": tok})
    cfg["providers"]["apify_keys"] = apify_list
    return cfg


def apify_tokens_with_meta(cfg: dict) -> list[dict]:
    out = []
    seen = set()
    for item in cfg.get("providers", {}).get("apify_keys") or []:
        tok = (item.get("token") or "").strip()
        if item.get("enabled", True) and tok and tok not in seen:
            seen.add(tok)
            out.append({"id": item["id"], "label": item.get("label") or item["id"], "token": tok})
    return out


def apify_tokens(cfg: dict) -> list[str]:
    return [x["token"] for x in apify_tokens_with_meta(cfg)]


def masked_view(connect, secret_store: SecretStore) -> dict:
    raw = read_settings(connect, secret_store)
    out = copy.deepcopy(NON_SENSITIVE_DEFAULTS)
    for grp in out:
        for k in out[grp]:
            out[grp][k] = copy.deepcopy(raw[grp][k])
    for (grp, fld), _ in SINGLE_SECRETS.items():
        out[grp][fld] = mask(raw[grp].get(fld, ""), reveal_last4=(grp, fld) not in FULL_MASK_SECRETS)

    public_keys = []
    for item in raw["providers"].get("apify_keys") or []:
        tok = item.get("token") or ""
        public_keys.append(
            {
                "id": item["id"],
                "label": item.get("label") or "Apify Key",
                "enabled": bool(item.get("enabled", True)),
                "created": item.get("created") or "",
                "masked": mask(tok),
                "set": bool(tok),
            }
        )
    out["providers"].pop("apify_keys_meta", None)
    out["providers"]["apify_keys"] = public_keys

    secrets_info = {
        skey: {
            "set": bool(raw[grp].get(fld)),
            "last4": raw[grp][fld][-4:] if ((grp, fld) not in FULL_MASK_SECRETS and len(raw[grp].get(fld) or "") >= 12) else "",
        }
        for (grp, fld), skey in SINGLE_SECRETS.items()
    }
    return {
        "settings": out,
        "secrets": secrets_info,
        "secret_backend": secret_store.backend_name,
        "markets": MARKETS,
        "channels": list(ALL_CHANNELS),
    }


def _validate_non_sensitive(cfg: dict):
    hunt = cfg["hunt"]
    if hunt.get("country") not in MARKETS:
        raise ValueError("Thị trường không hợp lệ")
    if not isinstance(hunt.get("channels"), list) or any(c not in ALL_CHANNELS for c in hunt["channels"]):
        raise ValueError("Danh sách kênh quét không hợp lệ")
    ipc = hunt.get("items_per_channel", 8)
    if isinstance(ipc, bool) or not isinstance(ipc, int) or not (1 <= ipc <= 50):
        raise ValueError("Số lượng kết quả mỗi kênh phải từ 1 đến 50")
    gate = hunt.get("score_gate", 7.0)
    if isinstance(gate, bool) or not isinstance(gate, (int, float)) or not (1 <= float(gate) <= 10):
        raise ValueError("Điểm chuẩn (score_gate) phải từ 1 đến 10")

    src = cfg["sourcing"]
    for k, lo, hi in (
        ("cny_to_vnd_rate", 100.0, 20000.0),
        ("cn_shipping_per_kg_vnd", 0.0, 500000.0),
        ("default_weight_kg", 0.01, 200.0),
        ("buying_agent_fee_pct", 0.0, 30.0),
        ("shopee_fee_pct", 0.0, 45.0),
        ("tiktok_shop_fee_pct", 0.0, 45.0),
        ("packaging_cost_vnd", 0.0, 500000.0),
        ("default_return_pct", 0.0, 80.0),
        ("target_net_margin_pct", 0.0, 90.0),
    ):
        v = src.get(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not (lo <= float(v) <= hi):
            raise ValueError(f"Thông số nguồn hàng {k} không hợp lệ ({lo}..{hi})")
        src[k] = round(float(v), 3)

    prov = cfg["providers"]
    jurl = str(prov.get("jev_base_url") or "https://api.typesafe.ai/v1/systemone").strip()
    if not jurl.startswith(("https://", "http://127.0.0.1", "http://localhost")):
        raise ValueError("jev_base_url phải dùng HTTPS hoặc loopback gateway hợp lệ")
    prov["jev_base_url"] = jurl

    kalo = cfg["kalodata"]
    kalo["account_email"] = clean_account_input(str(kalo.get("account_email") or ""))[:180]

    ntf = cfg["notify"]
    ntf["telegram_enabled"] = bool(ntf.get("telegram_enabled", True))
    ntf["telegram_chat_id"] = str(ntf.get("telegram_chat_id") or "").strip()[:80]
    ntf["telegram_allowed_user_ids"] = str(ntf.get("telegram_allowed_user_ids") or "").strip()[:240]
    rbase = str(ntf.get("result_base_url") or "").strip().rstrip("/")
    if rbase and not rbase.startswith(("http://", "https://")):
        raise ValueError("result_base_url phải bắt đầu bằng http:// hoặc https://")
    ntf["result_base_url"] = rbase[:200]

    mcp_cfg = cfg["mcp"]
    amode = str(mcp_cfg.get("access_mode") or "full_control").strip()
    if amode not in ("read_only", "full_control"):
        raise ValueError("access_mode của MCP phải là read_only hoặc full_control")
    mcp_cfg["access_mode"] = amode
    raw_scopes = mcp_cfg.get("enabled_scopes")
    if not isinstance(raw_scopes, list) or any(s not in MCP_SCOPES for s in raw_scopes):
        raise ValueError("Danh sách enabled_scopes của MCP không hợp lệ")
    mcp_cfg["enabled_scopes"] = list(dict.fromkeys(raw_scopes))


def save_settings_masked(connect, secret_store: SecretStore, body: dict) -> dict:
    if not isinstance(body, dict):
        raise ValueError("Cấu hình phải là JSON object")
    with _save_lock:
        current_non_sens = _read_non_sensitive(connect)
        for (grp, fld), skey in SINGLE_SECRETS.items():
            if isinstance(body.get(grp), dict) and fld in body[grp]:
                incoming = body[grp][fld]
                stored = secret_store.get(skey)
                resolved = resolve_secret(incoming, stored, skey, reveal_last4=(grp, fld) not in FULL_MASK_SECRETS)
                secret_store.set(skey, resolved)

        merged = copy.deepcopy(current_non_sens)
        for grp, values in body.items():
            if grp not in NON_SENSITIVE_DEFAULTS or not isinstance(values, dict):
                raise ValueError(f"Nhóm cấu hình không hợp lệ: {grp}")
            for fld, fval in values.items():
                if (grp, fld) in SINGLE_SECRETS or fld in ("apify_keys", "apify_keys_meta"):
                    continue
                if fld not in NON_SENSITIVE_DEFAULTS[grp]:
                    raise ValueError(f"Trường cấu hình không hợp lệ: {grp}.{fld}")
                merged[grp][fld] = fval

        _validate_non_sensitive(merged)
        with connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO settings VALUES ('application', ?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",
                (json.dumps(merged, ensure_ascii=False),),
            )
        return masked_view(connect, secret_store)


def add_apify_key(connect, secret_store: SecretStore, label: str, raw_token: str, make_primary: bool = False, key_id: str | None = None) -> dict:
    tok = clean_secret_input(raw_token)
    if not tok or is_masked(tok):
        raise ValueError("Vui lòng nhập Apify API Token hợp lệ")
    lbl = (label or "Apify Key").strip()[:80] or "Apify Key"
    with _save_lock:
        cfg = _read_non_sensitive(connect)
        meta_list = list(cfg["providers"].get("apify_keys_meta") or [])
        kid = key_id or uuid.uuid4().hex[:8]
        meta_list = [x for x in meta_list if x.get("id") != kid]
        secret_store.set(f"apify.key.{kid}", tok)
        entry = {"id": kid, "label": lbl, "enabled": True, "created": now()}
        if make_primary:
            meta_list.insert(0, entry)
        else:
            meta_list.append(entry)
        cfg["providers"]["apify_keys_meta"] = meta_list
        with connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO settings VALUES ('application', ?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",
                (json.dumps(cfg, ensure_ascii=False),),
            )
        return masked_view(connect, secret_store)


def update_apify_key(connect, secret_store: SecretStore, key_id: str, action: str) -> dict:
    with _save_lock:
        cfg = _read_non_sensitive(connect)
        meta_list = list(cfg["providers"].get("apify_keys_meta") or [])
        idx = next((i for i, x in enumerate(meta_list) if x.get("id") == key_id), -1)
        if idx < 0:
            raise KeyError("Không tìm thấy Apify Key này")
        if action == "delete":
            meta_list.pop(idx)
            secret_store.delete(f"apify.key.{key_id}")
        elif action == "promote":
            entry = meta_list.pop(idx)
            entry["enabled"] = True
            meta_list.insert(0, entry)
        elif action == "toggle":
            meta_list[idx]["enabled"] = not bool(meta_list[idx].get("enabled", True))
        else:
            raise ValueError("Hành động không hợp lệ")
        cfg["providers"]["apify_keys_meta"] = meta_list
        with connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO settings VALUES ('application', ?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",
                (json.dumps(cfg, ensure_ascii=False),),
            )
        return masked_view(connect, secret_store)
