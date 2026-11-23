"""Kalodata VN + TikTok Affiliate Global Selling Bridge over shared `peng_dedicated` Chrome Profile (`127.0.0.1:9339`).

Also handles 1-click / automatic Kalodata account migration from `affiliate-peng` (SQLite `account_email` + Keychain `kalodata.password`).
Strictly read-only DOM/Fiber inspection on loopback CDP; NEVER bypasses CAPTCHAs and NEVER reads cookies or password inputs.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import threading
import time
import uuid

from . import settings
from .chrome_profile_hub import (
    KALODATA_PRODUCT_URL,
    KALODATA_VIDEO_URL,
    TIKTOK_CREATOR_FIND_URL,
    _is_temp_test_dir,
    cdp_ws_call,
    cdp_ws_eval,
)
from .responses import ApiError, json_object, now, safe_id_str

AFFILIATE_PENG_ROOT = Path("/Users/trinh/.gemini/antigravity/scratch/affiliate-peng/local-data")
AFFILIATE_PENG_KEYCHAIN_SERVICE = "com.peng.affiliate-by-peng"

PID_FROM_IMG_RE = re.compile(r"tiktok\.product/(\d{15,22})/")
VID_FROM_IMG_RE = re.compile(r"tiktok\.video/(\d{15,22})/")
CID_FROM_IMG_RE = re.compile(r"tiktok\.creator/(\d{15,22})/")
URL_EXTRACT_RE = re.compile(r'https?://[^\s"\')]+')
CREATOR_CELL_RE = re.compile(r"@([A-Za-z0-9._-]+)(?:\s+.*?粉丝数[:：]?\s*([^\s]+))?")
TRAILING_PRICE_RE = re.compile(r"\s+(₫[\d.,]+\s*(?:亿|万|[KkMmBb])?)(?:\s*-\s*(₫[\d.,]+\s*(?:亿|万|[KkMmBb])?))?\s*$")
VIDEO_DURATION_PREFIX_RE = re.compile(r"^(?:(\d+)m\s*)?(?:(\d+)s)\s+", re.IGNORECASE)
VIDEO_TOOLBOX_SUFFIX_RE = re.compile(r"\s*(?:(AD)\s+)?工具箱\s*$")


def parse_kalo_number(raw_str: str | None) -> float | None:
    s = str(raw_str or "").strip()
    if not s or s in ("-", "--", "—", "N/A", "***"):
        return None
    clean = s.replace("₫", "").replace("VNĐ", "").replace("VND", "").replace("%", "").replace(",", "").strip()
    mult = Decimal("1")
    for sfx, factor in (("亿", Decimal("100000000")), ("万", Decimal("10000")), ("tỷ", Decimal("1000000000")), ("tr", Decimal("1000000")), ("m", Decimal("1000000")), ("k", Decimal("1000")), ("w", Decimal("10000"))):
        if clean.lower().endswith(sfx) and len(clean) > len(sfx):
            mult = factor
            clean = clean[: -len(sfx)].strip()
            break
    if "-" in clean[1:]:
        clean = clean.split("-", 1)[0].strip()
    try:
        val = float(Decimal(clean) * mult)
        return round(val, 2)
    except (InvalidOperation, ValueError):
        return None


def fmt_vnd_short(val: float | None) -> str:
    if val is None or val <= 0:
        return "—"
    if val >= 1_000_000_000:
        return f"{val / 1_000_000_000:.2f} tỷ ₫"
    if val >= 1_000_000:
        return f"{val / 1_000_000:.1f} tr ₫"
    return f"{val:,.0f}₫"


EXTRACT_GLOBAL_SELLING_CREATORS_JS = r"""
(() => {
  const unwrap = (v) => {
    let cur = v;
    for (let i = 0; i < 4 && cur && typeof cur === "object" && "value" in cur; i++) cur = cur.value;
    return cur;
  };
  const numOrNull = (v) => {
    const raw = unwrap(v);
    if (raw === undefined || raw === null || raw === "") return null;
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
  };
  const fmtMoney = (v) => {
    if (v && typeof v === "object") {
      if (v.format) return String(v.format).trim();
      if (v.value && typeof v.value === "object" && v.value.format) return String(v.value.format).trim();
    }
    return "";
  };
  const trs = Array.from(document.querySelectorAll("table tbody tr")).filter((r) => r.offsetParent !== null);
  const out = [];
  for (let idx = 0; idx < trs.length; idx++) {
    const tr = trs[idx];
    const tds = Array.from(tr.querySelectorAll("td")).map((td) => String(td.innerText || "").replace(/\s+/g, " ").trim());
    if (tds.length < 4) continue;
    let rec = null;
    try {
      const fk = Object.keys(tr).find((k) => k.startsWith("__reactFiber") || k.startsWith("__reactProps"));
      let cur = fk ? tr[fk] : null;
      for (let d = 0; d < 12 && cur; d++) {
        const p = cur.memoizedProps || {};
        if (p.record) { rec = p.record; break; }
        cur = cur.return;
      }
    } catch {}
    const cid = String(unwrap(rec?.creator_oecuid) || unwrap(rec?.oec_id) || "").trim();
    const handle = String(unwrap(rec?.handle) || (tds[1] ? tds[1].split(" ")[0] : "")).trim();
    const nickname = String(unwrap(rec?.nickname) || tds[1] || "").trim();
    const lvRaw = unwrap(rec?.creator_level);
    const levelLabel = (lvRaw !== undefined && lvRaw !== null && lvRaw !== "") ? `Lv. ${lvRaw}` : ((tds[1].match(/Lv\.\s*\d+/) || [""])[0]);
    const followers = numOrNull(rec?.follower_cnt) || 0;
    const totalGmv = numOrNull(rec?.med_gmv_revenue);
    const videoGmv = numOrNull(rec?.video_gmv);
    const unitsSold = numOrNull(rec?.units_sold);
    const avgViews = numOrNull(rec?.ec_video_avg_view_cnt) || numOrNull(rec?.video_avg_view_cnt) || 0;
    const topVidRaw = unwrap(rec?.top_video_data);
    const topVideos = Array.isArray(topVidRaw)
      ? topVidRaw.slice(0, 4).map((tv) => ({
          video_id: String(unwrap(tv?.item_id) || tv?.video_id || "").trim(),
          caption: String(unwrap(tv?.name) || "").trim(),
          views: numOrNull(tv?.play_cnt) || 0,
          likes: numOrNull(tv?.like_cnt) || 0,
          video_url: handle && unwrap(tv?.item_id) ? `https://www.tiktok.com/@${handle}/video/${unwrap(tv?.item_id)}` : "",
        })).filter((x) => x.video_id)
      : [];
    if (handle) {
      out.push({
        source: "affiliate_global_selling",
        native_creator_id: cid,
        handle: handle.replace(/^@/, ""),
        display_name: nickname,
        creator_level: levelLabel,
        followers: followers,
        total_gmv_vnd: totalGmv,
        total_gmv_display: fmtMoney(rec?.med_gmv_revenue) || tds[3] || "",
        video_gmv_vnd: videoGmv,
        units_sold: unitsSold ? Math.round(unitsSold) : null,
        items_sold_display: tds[4] || "",
        avg_views: avgViews ? Math.round(avgViews) : 0,
        avg_views_display: tds[5] || "",
        top_videos: topVideos,
      });
    }
  }
  return JSON.stringify({ rows: out, page_url: location.href });
})()
"""


class KalodataAndGlobalSellingService:
    def __init__(self, connect, secrets, data_dir: str | Path, chrome_hub, custom_scraper=None, telegram_bot=None):
        self.connect = connect
        self.secrets = secrets
        self.root = Path(data_dir)
        self.chrome_hub = chrome_hub
        self.custom_scraper = custom_scraper
        self.telegram_bot = telegram_bot
        self.custom_rotation_driver = None
        self._cdp_lock = threading.Lock()
        if not _is_temp_test_dir(self.root):
            try:
                self.ensure_affiliate_peng_kalodata_migrated()
            except Exception:
                pass

    def ensure_affiliate_peng_kalodata_migrated(self, force: bool = False) -> dict:
        """Copy Kalodata account (`account_email`, `market`, `currency`, `default_window_days`) + Keychain `kalodata.password` from `affiliate-peng`."""
        cur_cfg = settings.read_settings(self.connect, self.secrets)
        already_email = (cur_cfg.get("kalodata") or {}).get("account_email", "").strip()
        already_pw = bool(self.secrets.get("kalodata.password"))
        if already_email and already_pw and not force:
            return {
                "migrated": False,
                "already_configured": True,
                "account_email": already_email,
                "has_password_in_keychain": True,
                "shared_profile": self.chrome_hub.using_shared_peng_profile,
            }

        aff_db = AFFILIATE_PENG_ROOT / "backend.sqlite3"
        migrated_email = already_email
        kalo_patch: dict = {}
        if aff_db.is_file():
            conn = sqlite3.connect(aff_db, timeout=5)
            try:
                row = conn.execute("SELECT value FROM settings WHERE name='application'").fetchone()
                if row:
                    aff_app = json.loads(row[0])
                    aff_kalo = aff_app.get("kalodata") or {}
                    if aff_kalo.get("account_email"):
                        migrated_email = str(aff_kalo["account_email"]).strip()
                        kalo_patch = {
                            "market": str(aff_kalo.get("market") or "VN"),
                            "currency": str(aff_kalo.get("currency") or "VND"),
                            "account_email": migrated_email,
                            "default_window_days": int(aff_kalo.get("default_window_days") or 7),
                        }
            finally:
                conn.close()

        copied_secrets = []
        if Path("/usr/bin/security").is_file() and not _is_temp_test_dir(self.root):
            for skey in ("kalodata.password", "kalodata.session_cookie"):
                proc = subprocess.run(
                    ["/usr/bin/security", "find-generic-password", "-s", AFFILIATE_PENG_KEYCHAIN_SERVICE, "-a", skey, "-w"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                val = proc.stdout.rstrip("\r\n") if proc.returncode == 0 else ""
                if val:
                    self.secrets.set(skey, val)
                    copied_secrets.append(skey)

        if kalo_patch:
            settings.save_settings_masked(self.connect, self.secrets, {"kalodata": kalo_patch})

        return {
            "migrated": bool(kalo_patch or copied_secrets),
            "account_email": migrated_email,
            "copied_secret_keys": copied_secrets,
            "has_password_in_keychain": bool(self.secrets.get("kalodata.password")),
            "shared_profile": self.chrome_hub.using_shared_peng_profile,
            "summary": f"Đã đồng bộ tài khoản Kalodata ({migrated_email}) & Profile chuyên dụng `peng_dedicated` từ affiliate-peng!",
        }

    def check_portal_sessions(self) -> dict:
        cfg = settings.read_settings(self.connect, self.secrets)
        kalo_cfg = cfg.get("kalodata") or {}
        hub_st = self.chrome_hub.status()
        port = self.chrome_hub.get_live_port()
        kalo_session = {"logged_in": False, "url": "", "note": "Chưa mở tab Kalodata"}
        ags_session = {"ready": False, "url": "", "note": "Chưa mở tab Affiliate Global Selling"}

        if port:
            for t in self.chrome_hub.list_tabs(port):
                u = str(t.get("url") or "")
                ws = str(t.get("webSocketDebuggerUrl") or "")
                if "kalodata.com" in u and ws:
                    try:
                        obs = cdp_ws_eval(
                            port,
                            ws,
                            "JSON.stringify({url: location.href, logged_in: !location.pathname.startsWith('/login'), has_captcha: Boolean(document.querySelector(\"[class*='captcha'], .geetest_panel\"))})",
                        )
                        kalo_session = {
                            "logged_in": bool(obs.get("logged_in")) and not bool(obs.get("has_captcha")),
                            "has_captcha": bool(obs.get("has_captcha")),
                            "url": obs.get("url") or u,
                            "note": "Đã đăng nhập sẵn trên Profile peng_dedicated" if obs.get("logged_in") else "Cần đăng nhập trên Chrome chuyên dụng",
                        }
                    except Exception as exc:
                        kalo_session = {"logged_in": False, "url": u, "note": str(exc)[:120]}
                elif "tiktokshopglobalselling.com" in u and ws:
                    try:
                        obs = cdp_ws_eval(
                            port,
                            ws,
                            "JSON.stringify({url: location.href, ready: location.pathname.includes('/affiliate/creator') && !location.pathname.startsWith('/account/login')})",
                        )
                        ags_session = {
                            "ready": bool(obs.get("ready")),
                            "url": obs.get("url") or u,
                            "note": "Đã kết nối cổng Affiliate Global Selling (Find Creators)" if obs.get("ready") else "Đang ở trang khác trên Global Selling",
                        }
                    except Exception as exc:
                        ags_session = {"ready": False, "url": u, "note": str(exc)[:120]}

        return {
            "account_email": kalo_cfg.get("account_email") or "",
            "market": kalo_cfg.get("market") or "VN",
            "currency": kalo_cfg.get("currency") or "VND",
            "default_window_days": kalo_cfg.get("default_window_days") or 7,
            "has_password": bool(self.secrets.get("kalodata.password")),
            "cdp_port": port,
            "using_shared_peng_profile": hub_st["using_shared_peng_profile"],
            "profile_name": hub_st["profile_name"],
            "kalodata_session": kalo_session,
            "affiliate_global_selling_session": ags_session,
        }

    @staticmethod
    def _col_idx(ths: list[str], patterns: tuple[str, ...], default_idx: int) -> int:
        for i, h in enumerate(ths):
            hl = h.lower()
            if any(p.lower() in hl for p in patterns):
                return i
        return default_idx

    @staticmethod
    def _ime_search_kalodata(port: int, ws: str, keyword: str) -> None:
        cdp_ws_eval(
            port,
            ws,
            f"""(() => {{
              const inp = document.querySelector("input[placeholder*='输入'], input[placeholder*='搜索'], input[placeholder*='Search'], input[placeholder*='Enter'], .ant-input-affix-wrapper input.ant-input");
              if (!inp) return "{{}}";
              inp.focus();
              const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
              setter.call(inp, {json.dumps(keyword)});
              inp.dispatchEvent(new Event("input", {{bubbles: true}}));
              const rpKey = Object.keys(inp).find(k => k.startsWith("__reactProps"));
              if (rpKey && inp[rpKey]?.onChange) inp[rpKey].onChange({{target: inp, currentTarget: inp}});
              return "{{}}";
            }})()""",
        )
        time.sleep(0.4)
        cdp_ws_eval(
            port,
            ws,
            r"""(() => {
              const inp = document.querySelector("input[placeholder*='输入'], input[placeholder*='搜索'], input[placeholder*='Search'], input[placeholder*='Enter'], .ant-input-affix-wrapper input.ant-input");
              const rpKey = inp && Object.keys(inp).find(k => k.startsWith("__reactProps"));
              if (rpKey && inp[rpKey]?.onKeyDown) {
                inp[rpKey].onKeyDown({
                  key: "Enter", code: "Enter", keyCode: 13, which: 13,
                  target: inp, currentTarget: inp,
                  nativeEvent: {isComposing: false},
                  preventDefault: () => {}, stopPropagation: () => {}
                });
              }
              return "{}";
            })()""",
        )
        time.sleep(3.2)

    def search_kalodata_keyword(self, keyword: str, window_spec: str = "7d", limit: int = 12) -> dict:
        """Read-only search on Kalodata VN (`/product` + `/video`) over `peng_dedicated` CDP."""
        if self.custom_scraper is not None:
            return self.custom_scraper("kalodata", keyword, window_spec=window_spec, limit=limit)

        clean_kw = keyword.strip().lstrip("#").strip()
        port = self.chrome_hub.get_live_port()
        if not port:
            raise ApiError("503 Service Unavailable", "Chrome chuyên dụng `peng_dedicated` chưa chạy — bấm mở Kalodata trong Cài đặt.")

        with self._cdp_lock:
            tab = self.chrome_hub.open_or_focus_tab(port, ("kalodata.com",), KALODATA_PRODUCT_URL, focus=False)
            if not tab or not tab.get("webSocketDebuggerUrl"):
                raise ApiError("503 Service Unavailable", "Không mở được tab Kalodata trên Chrome chuyên dụng.")
            ws = tab["webSocketDebuggerUrl"]

            # 1) Navigate to `/product` and search
            cur = cdp_ws_eval(port, ws, "JSON.stringify({path: location.pathname, cap: Boolean(document.querySelector(\"[class*='captcha'], .geetest_panel\"))})")
            if cur.get("cap"):
                raise ApiError("409 Conflict", "Kalodata đang hiện CAPTCHA — vui lòng xác minh trực tiếp trên cửa sổ Chrome chuyên dụng.")
            if "/product" not in str(cur.get("path") or ""):
                cdp_ws_eval(port, ws, f"location.href = {json.dumps(KALODATA_PRODUCT_URL)}; '{{}}'")
                time.sleep(3.5)
                t2 = next((x for x in self.chrome_hub.list_tabs(port) if "kalodata.com" in str(x.get("url") or "")), tab)
                ws = t2["webSocketDebuggerUrl"]

            self._ime_search_kalodata(port, ws, clean_kw)
            raw_prod = cdp_ws_eval(
                port,
                ws,
                f"""(() => {{
                  const ths = Array.from(document.querySelectorAll("table thead th")).map(th => (th.innerText || "").replace(/\\s+/g, " ").trim());
                  const bodyTxt = document.querySelector("table")?.innerText || "";
                  if (/暂无数据|No data|未找到/i.test(bodyTxt)) return JSON.stringify({{ths, rows: []}});
                  const trs = Array.from(document.querySelectorAll("table tbody tr:not(.ant-table-measure-row)"))
                    .filter(r => r.querySelectorAll("td").length >= 8)
                    .slice(0, {max(1, min(25, int(limit)))});
                  const rows = trs.map(tr => {{
                    const tds = Array.from(tr.querySelectorAll("td")).map(td => (td.innerText || "").replace(/\\s+/g, " ").trim());
                    const bgImgs = Array.from(tr.querySelectorAll('[style*="background-image"], img')).map(el => el.src || el.style.backgroundImage || "").filter(Boolean);
                    let rowKey = "";
                    try {{
                      const fk = Object.keys(tr).find(k => k.startsWith("__reactFiber"));
                      let cur = fk ? tr[fk] : null;
                      for (let d = 0; d < 14 && cur; d++) {{
                        if (cur.key && /^\\d{{15,22}}$/.test(String(cur.key))) {{ rowKey = String(cur.key); break; }}
                        cur = cur.return;
                      }}
                    }} catch {{}}
                    return {{rowKey, tds, bgImgs}};
                  }});
                  return JSON.stringify({{ths, rows}});
                }})()""",
            )

            p_ths = raw_prod.get("ths") or []
            i_info = self._col_idx(p_ths, ("商品信息", "product"), 1)
            i_gmv = self._col_idx(p_ths, ("成交金额", "revenue"), 2)
            i_sold = self._col_idx(p_ths, ("销量", "items sold"), 5)
            i_aov = self._col_idx(p_ths, ("平均销售价", "unit price", "aov"), 8)
            i_comm = self._col_idx(p_ths, ("佣金比例", "commission"), 10)
            i_cr = self._col_idx(p_ths, ("达人数量", "creators"), 11)
            i_vid = self._col_idx(p_ths, ("视频成交", "video"), 15)

            kalo_products = []
            for r in raw_prod.get("rows") or []:
                tds = r.get("tds") or []
                imgs = [m.group(0) for im in (r.get("bgImgs") or []) if (m := URL_EXTRACT_RE.search(str(im)))]
                pid = str(r.get("rowKey") or "").strip()
                cover = ""
                for u in imgs:
                    mp = PID_FROM_IMG_RE.search(u)
                    if mp:
                        pid = pid or mp.group(1)
                        cover = cover or u
                raw_info = tds[i_info] if i_info < len(tds) else ""
                m_pr = TRAILING_PRICE_RE.search(raw_info)
                title = (raw_info[: m_pr.start()] if m_pr else raw_info).strip()
                p_val = parse_kalo_number(m_pr.group(1)) if m_pr else parse_kalo_number(tds[i_aov] if i_aov < len(tds) else "")
                gmv_v = parse_kalo_number(tds[i_gmv] if i_gmv < len(tds) else "")
                sold_v = parse_kalo_number(tds[i_sold] if i_sold < len(tds) else "")
                vid_gmv = parse_kalo_number(tds[i_vid] if i_vid < len(tds) else "")
                cr_cnt = parse_kalo_number(tds[i_cr] if i_cr < len(tds) else "")
                comm_v = parse_kalo_number(tds[i_comm] if i_comm < len(tds) else "")
                if title or pid:
                    kalo_products.append({
                        "native_product_id": safe_id_str(pid),
                        "title": title[:240],
                        "price_vnd": round(float(p_val or 0.0), 0),
                        "units_sold_recent": int(round(sold_v or 0)),
                        "gmv_recent_vnd": round(float(gmv_v or 0.0), 0),
                        "gmv_recent_display": fmt_vnd_short(gmv_v),
                        "video_gmv_vnd": round(float(vid_gmv or 0.0), 0),
                        "active_creators_count": int(round(cr_cnt or 0)),
                        "commission_pct": comm_v,
                        "image_url": cover,
                        "url": f"https://shop.tiktok.com/view/product/{pid}?region=VN" if pid else "",
                        "kalodata_url": f"https://www.kalodata.com/product/detail?id={pid}" if pid else KALODATA_PRODUCT_URL,
                    })

            # 2) Navigate to `/video` and search effective selling videos & creators
            cdp_ws_eval(port, ws, f"location.href = {json.dumps(KALODATA_VIDEO_URL)}; '{{}}'")
            time.sleep(3.5)
            t3 = next((x for x in self.chrome_hub.list_tabs(port) if "kalodata.com" in str(x.get("url") or "")), tab)
            ws_v = t3["webSocketDebuggerUrl"]
            self._ime_search_kalodata(port, ws_v, clean_kw)

            raw_vid = cdp_ws_eval(
                port,
                ws_v,
                f"""(() => {{
                  const ths = Array.from(document.querySelectorAll("table thead th")).map(th => (th.innerText || "").replace(/\\s+/g, " ").trim());
                  const bodyTxt = document.querySelector("table")?.innerText || "";
                  if (/暂无数据|No data|未找到/i.test(bodyTxt)) return JSON.stringify({{ths, rows: []}});
                  const trs = Array.from(document.querySelectorAll("table tbody tr:not(.ant-table-measure-row)"))
                    .filter(r => r.querySelectorAll("td").length >= 8)
                    .slice(0, {max(1, min(20, int(limit)))});
                  const rows = trs.map(tr => {{
                    const tds = Array.from(tr.querySelectorAll("td")).map(td => (td.innerText || "").replace(/\\s+/g, " ").trim());
                    const bgImgs = Array.from(tr.querySelectorAll('[style*="background-image"], img')).map(el => el.src || el.style.backgroundImage || "").filter(Boolean);
                    let rowKey = "";
                    try {{
                      const fk = Object.keys(tr).find(k => k.startsWith("__reactFiber"));
                      let cur = fk ? tr[fk] : null;
                      for (let d = 0; d < 14 && cur; d++) {{
                        if (cur.key && /^\\d{{15,22}}$/.test(String(cur.key))) {{ rowKey = String(cur.key); break; }}
                        cur = cur.return;
                      }}
                    }} catch {{}}
                    return {{rowKey, tds, bgImgs}};
                  }});
                  return JSON.stringify({{ths, rows}});
                }})()""",
            )

            v_ths = raw_vid.get("ths") or []
            iv_cnt = self._col_idx(v_ths, ("视频内容", "video"), 1)
            iv_cr = self._col_idx(v_ths, ("达人信息", "creator"), 2)
            iv_gmv = self._col_idx(v_ths, ("成交金额", "revenue"), 3)
            iv_sold = self._col_idx(v_ths, ("销量", "items sold"), 5)
            iv_views = self._col_idx(v_ths, ("观看次数", "views"), 7)
            iv_gpm = self._col_idx(v_ths, ("千次观看成交金额", "gpm"), 9)
            iv_roas = self._col_idx(v_ths, ("广告roas", "roas"), 13)
            iv_pub = self._col_idx(v_ths, ("发布日期", "publish"), 14)

            kalo_videos = []
            kalo_creators_map: dict[str, dict] = {}
            for r in raw_vid.get("rows") or []:
                tds = r.get("tds") or []
                imgs = [m.group(0) for im in (r.get("bgImgs") or []) if (m := URL_EXTRACT_RE.search(str(im)))]
                vid = str(r.get("rowKey") or "").strip()
                v_cover = ""
                for u in imgs:
                    mv = VID_FROM_IMG_RE.search(u)
                    if mv:
                        vid = vid or mv.group(1)
                        v_cover = v_cover or u
                raw_cap = tds[iv_cnt] if iv_cnt < len(tds) else ""
                raw_cap = VIDEO_TOOLBOX_SUFFIX_RE.sub("", raw_cap).strip()
                raw_cap = VIDEO_DURATION_PREFIX_RE.sub("", raw_cap).strip()

                cr_cell = tds[iv_cr] if iv_cr < len(tds) else ""
                m_cr = CREATOR_CELL_RE.search(cr_cell)
                handle = m_cr.group(1).strip() if m_cr else ""
                flw = parse_kalo_number(m_cr.group(2)) if (m_cr and m_cr.group(2)) else None

                vgmv = parse_kalo_number(tds[iv_gmv] if iv_gmv < len(tds) else "")
                vsold = parse_kalo_number(tds[iv_sold] if iv_sold < len(tds) else "")
                vviews = parse_kalo_number(tds[iv_views] if iv_views < len(tds) else "")
                vgpm = parse_kalo_number(tds[iv_gpm] if iv_gpm < len(tds) else "")
                vroas = parse_kalo_number(tds[iv_roas] if iv_roas < len(tds) else "")
                pub = tds[iv_pub] if iv_pub < len(tds) else ""

                v_url = f"https://www.tiktok.com/@{handle}/video/{vid}" if (handle and vid) else (f"https://www.tiktok.com/@_/video/{vid}" if vid else "")
                v_obj = {
                    "source": "kalodata_vn",
                    "video_id": safe_id_str(vid),
                    "video_url": v_url,
                    "cover_url": v_cover,
                    "caption": raw_cap[:260],
                    "author_handle": handle,
                    "followers": int(round(flw or 0)),
                    "video_gmv_vnd": round(float(vgmv or 0.0), 0),
                    "video_gmv_display": fmt_vnd_short(vgmv),
                    "orders_count": int(round(vsold or 0)),
                    "views_count": int(round(vviews or 0)),
                    "gpm_vnd": round(float(vgpm or 0.0), 0),
                    "gpm_display": fmt_vnd_short(vgpm),
                    "ad_roas": vroas,
                    "published_at": pub,
                }
                kalo_videos.append(v_obj)

                if handle:
                    hk = handle.lower()
                    agg = kalo_creators_map.setdefault(hk, {
                        "source": "kalodata_vn",
                        "handle": handle,
                        "display_name": f"@{handle}",
                        "followers": int(round(flw or 0)),
                        "total_gmv_vnd": 0.0,
                        "video_gmv_vnd": 0.0,
                        "units_sold": 0,
                        "avg_views": 0,
                        "top_gpm_vnd": 0.0,
                        "winning_videos_count": 0,
                        "top_videos": [],
                    })
                    agg["total_gmv_vnd"] += float(vgmv or 0.0)
                    agg["video_gmv_vnd"] += float(vgmv or 0.0)
                    agg["units_sold"] += int(round(vsold or 0))
                    agg["avg_views"] = max(agg["avg_views"], int(round(vviews or 0)))
                    agg["top_gpm_vnd"] = max(agg["top_gpm_vnd"], float(vgpm or 0.0))
                    agg["winning_videos_count"] += 1
                    agg["top_videos"].append(v_obj)

        creators_list = sorted(kalo_creators_map.values(), key=lambda x: (x["video_gmv_vnd"], x["units_sold"]), reverse=True)
        for c in creators_list:
            c["total_gmv_display"] = fmt_vnd_short(c["total_gmv_vnd"])
        return {
            "keyword": clean_kw,
            "window_spec": window_spec,
            "products": kalo_products,
            "videos": kalo_videos,
            "creators": creators_list,
        }

    def search_affiliate_global_selling_creators(self, keyword: str, max_results: int = 20) -> list[dict]:
        """Read-only search on `affiliate.tiktokshopglobalselling.com/affiliate/creator` via `peng_dedicated` CDP."""
        if self.custom_scraper is not None:
            return self.custom_scraper("affiliate_global_selling", keyword, limit=max_results)

        port = self.chrome_hub.get_live_port()
        if not port:
            raise ApiError("503 Service Unavailable", "Chrome chuyên dụng `peng_dedicated` chưa mở.")

        clean_q = keyword.strip()
        with self._cdp_lock:
            tab = self.chrome_hub.open_or_focus_tab(
                port,
                ("affiliate.tiktokshopglobalselling.com", "seller.tiktokshopglobalselling.com"),
                TIKTOK_CREATOR_FIND_URL,
                focus=False,
            )
            if not tab or not tab.get("webSocketDebuggerUrl"):
                raise ApiError("503 Service Unavailable", "Không mở được tab Affiliate Global Selling.")
            ws = tab["webSocketDebuggerUrl"]

            st = cdp_ws_eval(
                port,
                ws,
                "JSON.stringify({path: location.pathname, login: location.pathname.startsWith('/account/login'), cap: Boolean(document.querySelector(\".secsdk-captcha-wrapper, iframe[src*='captcha']\"))})",
            )
            if st.get("cap"):
                raise ApiError("409 Conflict", "Cổng Affiliate Global Selling đang hiện CAPTCHA — vui lòng xác minh trên cửa sổ Chrome.")
            if st.get("login"):
                raise ApiError("401 Unauthorized", "Cổng Affiliate Global Selling chưa đăng nhập.")

            if "/affiliate/creator" not in str(st.get("path") or "") or "/rankings" in str(st.get("path") or ""):
                cdp_ws_eval(port, ws, f"location.href = {json.dumps(TIKTOK_CREATOR_FIND_URL)}; '{{}}'")
                time.sleep(4.0)
                t2 = next((x for x in self.chrome_hub.list_tabs(port) if "tiktokshopglobalselling.com" in str(x.get("url") or "")), tab)
                ws = t2["webSocketDebuggerUrl"]

            # Reset stale filters and search keyword
            cdp_ws_eval(
                port,
                ws,
                """(() => {
                  const rst = Array.from(document.querySelectorAll("button")).find(
                    b => b.offsetParent !== null && (b.innerText || "").trim() === "Reset" && !b.disabled
                  );
                  if (rst) rst.click();
                  return "{}";
                })()""",
            )
            time.sleep(0.6)
            cdp_ws_eval(
                port,
                ws,
                f"""(() => {{
                  const inp = document.querySelector("input[data-tid='m4b_input_search'], input[placeholder*='Search names']");
                  if (!inp) return "{{}}";
                  const desc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
                  inp.focus();
                  desc.set.call(inp, {json.dumps(clean_q)});
                  inp.dispatchEvent(new Event("input", {{bubbles:true}}));
                  inp.dispatchEvent(new Event("change", {{bubbles:true}}));
                  inp.dispatchEvent(new KeyboardEvent("keydown", {{key:"Enter", code:"Enter", keyCode:13, which:13, bubbles:true}}));
                  const sfx = inp.parentElement?.querySelector(".core-input-group-suffix, .arco-icon-search");
                  if (sfx) ["mousedown", "mouseup", "click"].forEach(ev => sfx.dispatchEvent(new MouseEvent(ev, {{bubbles:true, cancelable:true, view:window}})));
                  return "{{}}";
                }})()""",
            )
            time.sleep(3.6)
            extracted = cdp_ws_eval(port, ws, EXTRACT_GLOBAL_SELLING_CREATORS_JS)
            rows = extracted.get("rows") or []
            return rows[: max(1, min(40, int(max_results)))]

    def inspect_kalodata_quota(self) -> dict:
        cfg = settings.read_settings(self.connect, self.secrets)
        kcfg = cfg.get("kalodata") or {}
        email = str(kcfg.get("account_email") or "").strip()
        port = self.chrome_hub.get_live_port() if self.chrome_hub else None
        if not port:
            return {
                "ok": False,
                "status": "browser_closed",
                "plan_kind": "unauthenticated",
                "plan_label_vi": "Chrome Chuyên Dụng chưa mở",
                "account_email": email,
                "has_limitation": True,
                "limitations": ["Bấm Mở Kalodata để khởi tạo phiên trên Chrome Chuyên Dụng."],
            }
        tab = self.chrome_hub.open_or_focus_tab(port, ("kalodata.com",), KALODATA_PRODUCT_URL, focus=False)
        if not tab or not tab.get("webSocketDebuggerUrl"):
            return {
                "ok": False,
                "status": "no_tab",
                "plan_kind": "unauthenticated",
                "plan_label_vi": "Chưa mở tab Kalodata",
                "account_email": email,
                "has_limitation": True,
                "limitations": ["Không mở được tab Kalodata trên Chrome Chuyên Dụng."],
            }
        ws = tab["webSocketDebuggerUrl"]
        obs = cdp_ws_eval(
            port,
            ws,
            r"""(() => {
              const body = (document.body?.innerText || "").replace(/\s+/g, " ").trim().slice(0, 4000);
              const cap = document.querySelector("[class*='captcha'], iframe[src*='captcha'], .geetest_panel");
              const onLogin = location.pathname.startsWith("/login") || Boolean(document.querySelector("form#register, input#register_password"));
              const trs = Array.from(document.querySelectorAll("tbody tr:not(.ant-table-measure-row)"));
              let stars = 0;
              trs.forEach(tr => { if ((tr.innerText || "").includes("***")) stars += 1; });
              const isTrial = /试用版|Free\s*Trial/i.test(body) || (body.includes("更多页") && body.includes("立即升级"));
              return JSON.stringify({url: location.href, onLogin, hasCaptcha: Boolean(cap && cap.offsetParent !== null), rows: trs.length, stars, isTrial, body});
            })()""",
        )
        if obs.get("hasCaptcha"):
            return {
                "ok": False,
                "status": "captcha_required",
                "plan_kind": "captcha",
                "plan_label_vi": "Đang chờ xác minh CAPTCHA trên Chrome",
                "account_email": email,
                "has_limitation": True,
                "limitations": ["Vui lòng xác minh CAPTCHA trực tiếp trên cửa sổ Chrome Chuyên Dụng."],
            }
        if obs.get("onLogin"):
            return {
                "ok": False,
                "status": "login_required",
                "plan_kind": "unauthenticated",
                "plan_label_vi": "Chưa đăng nhập / Hết hạn phiên",
                "account_email": email,
                "has_limitation": True,
                "limitations": ["Phiên Kalodata đã hết hạn — bấm Cập nhật & Đổi Tài khoản để đăng nhập lại."],
            }
        stars = int(obs.get("stars") or 0)
        is_trial = bool(obs.get("isTrial"))
        if is_trial or stars > 0:
            return {
                "ok": False,
                "status": "limited_regular_or_trial",
                "plan_kind": "trial_or_regular",
                "plan_label_vi": "Tài khoản Thường / Dùng thử (Giới hạn dòng & phân trang)",
                "account_email": email,
                "visible_rows": int(obs.get("rows") or 0),
                "masked_stars_count": stars,
                "has_limitation": True,
                "limitations": ["Tài khoản hiện tại bị giới hạn gói dùng thử hoặc che '***'."],
            }
        return {
            "ok": True,
            "status": "ok_full",
            "plan_kind": "paid_full",
            "plan_label_vi": "Tài khoản Kalodata Pro Trả phí đầy đủ (0₫ API · Không khoá dòng)",
            "account_email": email,
            "visible_rows": int(obs.get("rows") or 0),
            "masked_stars_count": 0,
            "has_limitation": False,
            "limitations": [],
        }

    def rotate_kalodata_account(self, body: dict) -> dict:
        """Save new Kalodata credentials -> Logout ONLY `kalodata.com` on Dedicated Chrome -> Login new -> Notify Telegram."""
        step_logs: list[str] = []

        def log_step(msg: str) -> None:
            clk = datetime.now().strftime("%H:%M:%S")
            step_logs.append(f"[{clk}] {msg}")

        cur_cfg = settings.read_settings(self.connect, self.secrets)
        kalo_saved = cur_cfg.get("kalodata") or {}
        old_email = str(kalo_saved.get("account_email") or "").strip()

        raw_email = body.get("account_email")
        new_email = settings.clean_account_input(str(raw_email if raw_email is not None else old_email))
        if not new_email:
            raise ApiError("400 Bad Request", "Vui lòng nhập Email hoặc SĐT tài khoản Kalodata cần đăng nhập!")

        new_password = settings.resolve_secret(
            body.get("password") if "password" in body else "",
            kalo_saved.get("password", ""),
            "Mật khẩu Kalodata",
            reveal_last4=False,
        )
        if not new_password:
            raise ApiError("400 Bad Request", "Vui lòng nhập Mật khẩu của tài khoản Kalodata!")

        market = str(body.get("market") or body.get("station") or kalo_saved.get("market") or "VN").strip().upper()
        currency = str(body.get("currency") or kalo_saved.get("currency") or "VND").strip().upper()
        win_days = int(body.get("default_window_days") or kalo_saved.get("default_window_days") or 7)
        suppress_tg = bool(body.get("suppress_telegram", False))

        log_step(f"Bước 1/4: Lưu tài khoản Kalodata ({new_email}) & mật khẩu vào {self.secrets.backend_name}...")
        settings.save_settings_masked(
            self.connect,
            self.secrets,
            {
                "kalodata": {
                    "account_email": new_email,
                    "password": new_password,
                    "market": market,
                    "currency": currency,
                    "default_window_days": win_days,
                }
            },
        )

        rotation_id = f"klrot_{uuid.uuid4().hex[:12]}"
        rot_status = "failed"
        kalo_after: dict = {}
        err_msg = ""
        tg_sent = False

        with self._cdp_lock:
            try:
                if self.custom_rotation_driver is not None:
                    drv_res = self.custom_rotation_driver(new_email, new_password, market, log_step)
                    rot_status = str(drv_res.get("status") or "completed")
                    kalo_after = drv_res.get("kalodata_after") or {"status": "ok_full", "plan_label_vi": "Gói Kalodata Pro Trả phí đầy đủ"}
                    err_msg = str(drv_res.get("error_message") or "")
                else:
                    log_step("Bước 2/4: Mở / kết nối Chrome Chuyên Dụng `peng_dedicated`...")
                    ens = self.chrome_hub.ensure_running(want_kalodata=True, want_tiktok_creator=False, focus_domain="kalodata")
                    if not ens.get("ok") or not ens.get("port"):
                        raise RuntimeError(ens.get("error_message") or "Không mở được Chrome Chuyên Dụng.")
                    port = int(ens["port"])
                    tab = self.chrome_hub.open_or_focus_tab(port, ("kalodata.com",), KALODATA_PRODUCT_URL, focus=True)
                    if not tab or not tab.get("webSocketDebuggerUrl"):
                        raise RuntimeError("Không tìm thấy tab Kalodata trên Chrome Chuyên Dụng.")
                    ws = tab["webSocketDebuggerUrl"]

                    # Clear ONLY `kalodata.com` cookies + tab storage (preserving TikTok Seller / Global Selling!)
                    ck_res = cdp_ws_call(port, ws, "Network.getAllCookies", {}, timeout=8.0)
                    cookies = [
                        c for c in (ck_res.get("cookies") or [])
                        if isinstance(c, dict) and "kalodata.com" in str(c.get("domain") or "").lower()
                    ]
                    for ck in cookies:
                        cdp_ws_call(
                            port,
                            ws,
                            "Network.deleteCookies",
                            {"name": ck.get("name") or "", "domain": ck.get("domain") or ".kalodata.com", "path": ck.get("path") or "/"},
                            timeout=5.0,
                        )
                    cdp_ws_eval(
                        port,
                        ws,
                        r"""(() => {
                          try { localStorage.clear(); } catch {}
                          try { sessionStorage.clear(); } catch {}
                          location.href = "https://www.kalodata.com/login";
                          return JSON.stringify({ok: true});
                        })()""",
                    )
                    time.sleep(2.8)
                    t_login = next((t for t in self.chrome_hub.list_tabs(port) if "kalodata.com" in str(t.get("url") or "")), tab)
                    ws = t_login["webSocketDebuggerUrl"]
                    log_step(f"Bước 3/4: Đã logout phiên cũ (xoá {len(cookies)} cookie kalodata.com, giữ nguyên TikTok Global Selling) & mở trang /login...")

                    is_email = "@" in new_email
                    if is_email:
                        cdp_ws_eval(
                            port,
                            ws,
                            r"""(() => {
                              const emailBtn = Array.from(document.querySelectorAll("div.tiktok_btn, div, span, button")).find(
                                e => e.children.length === 0 && /^(Email|邮箱|邮箱登录)$/i.test((e.innerText || "").trim())
                              );
                              if (emailBtn) emailBtn.click();
                              return "{}";
                            })()""",
                        )
                        time.sleep(0.5)
                    cdp_ws_eval(
                        port,
                        ws,
                        r"""(() => {
                          if (!document.querySelector("input#register_password")) {
                            const pwBtn = document.querySelector(".Component_ChangeLoginMode .right-text")
                              || Array.from(document.querySelectorAll("div, span, a")).find(e => e.children.length === 0 && /(password|密码)/i.test(e.innerText || "") && !/forgot|忘记/i.test(e.innerText || ""));
                            if (pwBtn) pwBtn.click();
                          }
                          return "{}";
                        })()""",
                    )
                    time.sleep(0.5)

                    filled = cdp_ws_eval(
                        port,
                        ws,
                        f"""(() => {{
                          const setInp = (el, v) => {{
                            if (!el) return false;
                            el.focus();
                            const st = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
                            if (st) st.call(el, v); else el.value = v;
                            el.dispatchEvent(new Event("input", {{bubbles: true}}));
                            el.dispatchEvent(new Event("change", {{bubbles: true}}));
                            return true;
                          }};
                          const acc = document.querySelector({json.dumps("input#register_email" if is_email else "input#register_phone")})
                            || document.querySelector("input#register_email, input#register_phone");
                          const pw = document.querySelector("input#register_password");
                          if (!acc || !pw) return JSON.stringify({{ok: false}});
                          setInp(acc, {json.dumps(new_email)});
                          setInp(pw, {json.dumps(new_password)});
                          const chk = document.querySelector("input.ant-checkbox-input, input[type='checkbox']");
                          if (chk && !chk.checked) chk.click();
                          const sub = document.querySelector("button.submit-btn[type='submit'], button[type='submit']");
                          if (sub) sub.click();
                          return JSON.stringify({{ok: Boolean(sub)}});
                        }})()""",
                    )
                    if not filled.get("ok"):
                        raise RuntimeError("Không tìm thấy ô nhập Email/Mật khẩu trên trang /login của Kalodata.")

                    deadline = time.monotonic() + 10.5
                    while time.monotonic() < deadline:
                        time.sleep(0.9)
                        t_cur = next((t for t in self.chrome_hub.list_tabs(port) if "kalodata.com" in str(t.get("url") or "")), t_login)
                        ws = t_cur["webSocketDebuggerUrl"]
                        pr = cdp_ws_eval(
                            port,
                            ws,
                            r"""(() => {
                              const cap = document.querySelector("[class*='captcha'], iframe[src*='captcha'], .geetest_panel");
                              const err = document.querySelector(".ant-message-error, .ant-form-item-explain-error");
                              return JSON.stringify({
                                onLogin: location.pathname.startsWith("/login"),
                                hasCaptcha: Boolean(cap && cap.offsetParent !== null),
                                errText: err ? (err.innerText || "").trim() : ""
                              });
                            })()""",
                        )
                        if pr.get("hasCaptcha"):
                            rot_status = "verification_required"
                            err_msg = "Kalodata yêu cầu xác minh CAPTCHA trên cửa sổ Chrome Chuyên Dụng — hệ thống dừng an toàn (0% tự vượt CAPTCHA) để bạn xác nhận trực tiếp."
                            log_step(f"⏸ {err_msg}")
                            break
                        if not pr.get("onLogin"):
                            rot_status = "completed"
                            break
                        if pr.get("errText"):
                            err_msg = str(pr["errText"])[:180]

                    if rot_status == "completed":
                        kalo_after = self.inspect_kalodata_quota()
                        log_step(f"Bước 4/4: ✅ Đăng nhập Kalodata mới thành công! {kalo_after.get('plan_label_vi') or ''}")
                    elif rot_status != "verification_required" and not err_msg:
                        err_msg = "Chưa chuyển hướng khỏi trang /login sau 10 giây — vui lòng kiểm tra mật khẩu hoặc cửa sổ Chrome."
                        log_step(f"❌ {err_msg}")
            except Exception as exc:
                rot_status = "failed"
                err_msg = str(exc)[:220]
                log_step(f"❌ Lỗi đổi tài khoản Kalodata: {err_msg}")

        if self.telegram_bot is not None and not suppress_tg:
            try:
                tg_msg = (
                    f"{'✅ ĐỔI TÀI KHOẢN KALODATA THÀNH CÔNG' if rot_status == 'completed' else '⚠️ CẬP NHẬT TÀI KHOẢN KALODATA: ' + rot_status.upper()}\n"
                    f"• Tài khoản cũ: {old_email or '—'}\n"
                    f"• Tài khoản mới: {new_email} ({market}/{currency})\n"
                    f"• Trạng thái gói: {kalo_after.get('plan_label_vi') or err_msg or rot_status}"
                )
                sent = self.telegram_bot.send_text(tg_msg)
                tg_sent = bool(sent)
            except Exception:
                pass

        ts = now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO kalodata_account_rotations
                (rotation_id, old_account_hint, new_account_email, status, kalodata_status_after,
                 step_logs_json, kalodata_after_json, telegram_sent, telegram_message_id, error_message, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?)
                """,
                (
                    rotation_id,
                    old_email[:120],
                    new_email[:120],
                    rot_status,
                    str(kalo_after.get("status") or ""),
                    json.dumps(step_logs, ensure_ascii=False),
                    json.dumps(kalo_after, ensure_ascii=False),
                    1 if tg_sent else 0,
                    err_msg,
                    ts,
                ),
            )
        return {
            "ok": rot_status == "completed",
            "rotation_id": rotation_id,
            "status": rot_status,
            "old_account_hint": old_email,
            "new_account_email": new_email,
            "market": market,
            "currency": currency,
            "kalodata_after": kalo_after,
            "step_logs": step_logs,
            "telegram_sent": tg_sent,
            "error_message": err_msg,
            "created_at": ts,
        }

    def list_account_rotations(self, limit: int = 15) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM kalodata_account_rotations ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (max(1, min(30, int(limit))),),
            ).fetchall()
        return [
            {
                "rotation_id": r["rotation_id"],
                "old_account_hint": r["old_account_hint"],
                "new_account_email": r["new_account_email"],
                "status": r["status"],
                "kalodata_status_after": r["kalodata_status_after"],
                "step_logs": json.loads(r["step_logs_json"] or "[]"),
                "kalodata_after": json.loads(r["kalodata_after_json"] or "{}"),
                "telegram_sent": bool(r["telegram_sent"]),
                "error_message": r["error_message"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def dispatch(self, path: str, method: str, env, read_json):
        if path == "/api/kalodata/status" and method == "GET":
            st = self.check_portal_sessions()
            return "200 OK", st
        if path in ("/api/kalodata/quota", "/api/providers/kalodata/check") and method in ("GET", "POST"):
            return "200 OK", self.inspect_kalodata_quota()
        if path == "/api/kalodata/sync-from-affiliate" and method == "POST":
            return "200 OK", self.ensure_affiliate_peng_kalodata_migrated(force=True)
        if path in ("/api/kalodata/rotate-account", "/api/providers/kalodata/rotate-account") and method == "POST":
            return "200 OK", self.rotate_kalodata_account(json_object(read_json, env))
        if path in ("/api/kalodata/rotations", "/api/providers/kalodata/rotations") and method == "GET":
            return "200 OK", {"items": self.list_account_rotations(limit=15)}
        if path == "/api/kalodata/search" and method == "POST":
            body = json_object(read_json, env)
            kw = str(body.get("keyword") or "").strip()
            if not kw:
                raise ValueError("Từ khoá Kalodata không được để trống")
            return "200 OK", self.search_kalodata_keyword(kw, window_spec=str(body.get("window_spec") or "7d"), limit=int(body.get("limit") or 12))
        if path == "/api/global-selling/creators" and method == "POST":
            body = json_object(read_json, env)
            kw = str(body.get("keyword") or "").strip()
            if not kw:
                raise ValueError("Từ khoá Affiliate Global Selling không được để trống")
            rows = self.search_affiliate_global_selling_creators(kw, max_results=int(body.get("limit") or 20))
            return "200 OK", {"keyword": kw, "creators": rows, "count": len(rows)}
        return None
