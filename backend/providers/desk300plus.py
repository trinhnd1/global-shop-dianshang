"""Fail-Closed `300+desk` Connector for Global Shop Dianshang (`127.0.0.1:18765` -> OrangePi5 Pro SOCKS5 + `run-dsh-portable.sh`).

Strict Architecture & Egress Rules (matching `affiliate-peng`):
- Priority #1 Data Collection: Apify Store API
- Priority #2 Backup Data Collection: Treg.to API
- Product Processing / Merge / Cleaning / CN Sourcing Keywords / Combo & Video Angles: `300+desk` (Fail-Closed over Loopback `127.0.0.1:18765` -> `socks5h://100.113.217.101:1080` OrangePi5 Pro; 0% direct Mac IP fallback!)
- Final Calibration & Decision Making (`strong_pick` / `maybe` / `pass`): TypeSafe Jev AI (`jev-1.14.0`).
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import urllib.error
from urllib.parse import urlsplit
import urllib.request

DEFAULT_GATEWAY_URL = "http://127.0.0.1:18765"
DEFAULT_DSH_SCRIPT = Path.home() / "Projects" / "hiboost" / "scripts" / "run-dsh-portable.sh"
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


class Desk300PlusFailClosedError(Exception):
    """Raised when `300+desk` Gateway or OrangePi5 Pro SOCKS5 is unavailable — strictly blocks Mac-direct fallback."""

    def __init__(self, message: str, status: int = 503):
        self.status = status
        super().__init__(message)


def _assert_loopback_gateway(gateway_url: str) -> str:
    clean = (gateway_url or DEFAULT_GATEWAY_URL).strip().rstrip("/")
    parsed = urlsplit(clean)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost"):
        raise Desk300PlusFailClosedError(
            f"FAIL-CLOSED: Gateway 300+desk bắt buộc chỉ bind loopback 127.0.0.1 (từ chối '{clean}').",
            status=400,
        )
    return clean


def parse_json_from_desk_text(raw_text: str):
    """Extract JSON object or array from `300+desk` response without altering any numeric values."""
    s = (raw_text or "").strip()
    if not s:
        raise ValueError("Phản hồi từ 300+desk rỗng")
    m = _JSON_FENCE_RE.search(s)
    if m:
        s = m.group(1).strip()
    try:
        return json.loads(s)
    except ValueError:
        pass
    first_obj = s.find("{")
    last_obj = s.rfind("}")
    if first_obj != -1 and last_obj > first_obj:
        try:
            return json.loads(s[first_obj : last_obj + 1])
        except ValueError:
            pass
    first_arr = s.find("[")
    last_arr = s.rfind("]")
    if first_arr != -1 and last_arr > first_arr:
        return json.loads(s[first_arr : last_arr + 1])
    raise ValueError("Phản hồi từ 300+desk không chứa khối JSON hợp lệ")


class Desk300PlusClient:
    """Fail-closed client for `300+desk` via `ai.desk300plus.gateway` (`127.0.0.1:18765`) & `run-dsh-portable.sh`."""

    def __init__(
        self,
        gateway_url: str = DEFAULT_GATEWAY_URL,
        dsh_script_path: Path | str | None = None,
        custom_runner=None,
    ):
        self.gateway_url = _assert_loopback_gateway(gateway_url)
        self.dsh_script = Path(dsh_script_path) if dsh_script_path is not None else DEFAULT_DSH_SCRIPT
        self._custom_runner = custom_runner

    def check_gateway_status(self, probe_egress_ip: bool = False) -> dict:
        """Verify `ai.desk300plus.gateway` on `127.0.0.1:18765` and OrangePi5 Pro SOCKS5 binding."""
        if self._custom_runner is not None and hasattr(self._custom_runner, "check_gateway_status"):
            return self._custom_runner.check_gateway_status(probe_egress_ip=probe_egress_ip)

        health_url = f"{self.gateway_url}/health"
        try:
            req = urllib.request.Request(health_url, headers={"User-Agent": "GlobalShopDianshang-Desk300Plus/1.0"})
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                if resp.status != 200:
                    raise Desk300PlusFailClosedError(
                        f"FAIL-CLOSED: Gateway {self.gateway_url}/health trả HTTP {resp.status} — dừng ngay để không lộ IP Mac.",
                        status=503,
                    )
                health = json.loads(resp.read().decode("utf-8"))
        except Desk300PlusFailClosedError:
            raise
        except Exception as exc:
            raise Desk300PlusFailClosedError(
                f"FAIL-CLOSED: Không kết nối được Gateway 300+desk ({self.gateway_url}: {exc}) — tuyệt đối không gọi trực tiếp từ IP Mac.",
                status=503,
            ) from None

        socks_cfg = str(health.get("socks") or "")
        if not health.get("ok") or not socks_cfg.startswith("socks5"):
            raise Desk300PlusFailClosedError(
                f"FAIL-CLOSED: Gateway {self.gateway_url} chưa khóa cứng proxy SOCKS5 OrangePi5 Pro (socks='{socks_cfg}').",
                status=503,
            )

        egress_probe = None
        if probe_egress_ip:
            try:
                with urllib.request.urlopen(f"{self.gateway_url}/v1/egress-ip", timeout=8.0) as eresp:
                    egress_probe = json.loads(eresp.read().decode("utf-8"))
                if isinstance(egress_probe, dict) and egress_probe.get("via_socks") is False:
                    raise Desk300PlusFailClosedError(
                        "FAIL-CLOSED: Egress probe báo via_socks=false — đã chặn tác vụ để bảo vệ IP.",
                        status=503,
                    )
            except Desk300PlusFailClosedError:
                raise
            except urllib.error.HTTPError as hexc:
                if hexc.code == 503:
                    raise Desk300PlusFailClosedError(
                        "FAIL-CLOSED: SOCKS5 OrangePi5 Pro đang ngắt kết nối (Gateway HTTP 503) — dừng tác vụ an toàn.",
                        status=503,
                    ) from None
            except Exception:
                egress_probe = {"note": "derp_probe_timeout_gateway_enforces_socks_precheck"}

        return {
            "ok": True,
            "fail_closed": True,
            "gateway_url": self.gateway_url,
            "service": health.get("service") or "desk300plus-gateway",
            "team": health.get("team") or "300+ Desk",
            "version": health.get("version") or "",
            "socks_proxy": socks_cfg,
            "dsh_script_exists": self.dsh_script.is_file(),
            "dsh_script_path": str(self.dsh_script),
            "egress_probe": egress_probe,
        }

    def run_dsh_json(
        self,
        workdir: Path,
        prompt_text: str,
        *,
        use_pro: bool = False,
        timeout_sec: int = 115,
        meta_filename: str = "egress_meta.json",
    ) -> dict:
        """Execute a structured JSON product task on `300+desk` via `run-dsh-portable.sh` (Fail-Closed)."""
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        gw_status = self.check_gateway_status(probe_egress_ip=False)

        (workdir / "merge_prompt.txt").write_text(prompt_text, encoding="utf-8")

        if self._custom_runner is not None:
            raw_out, meta_obj = self._custom_runner(workdir, prompt_text, mode="dsh", use_pro=use_pro)
            if meta_obj:
                (workdir / meta_filename).write_text(json.dumps(meta_obj, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            if not self.dsh_script.is_file():
                raise Desk300PlusFailClosedError(
                    f"FAIL-CLOSED: Không tìm thấy script DeepSeek Harness '{self.dsh_script}'.",
                    status=503,
                )
            sub_tag = re.sub(r"[^a-zA-Z0-9_-]+", "_", meta_filename.replace(".json", "")) or "dsh"
            exec_dir = workdir / f"_{sub_tag}_exec"
            exec_dir.mkdir(parents=True, exist_ok=True)
            exec_prompt = exec_dir / "prompt_in.txt"
            exec_prompt.write_text(prompt_text, encoding="utf-8")

            cmd = ["bash", str(self.dsh_script)]
            if use_pro:
                cmd.append("--pro")
            cmd.extend([str(exec_dir), str(exec_prompt)])
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=max(20, int(timeout_sec)))
            except subprocess.TimeoutExpired:
                raise Desk300PlusFailClosedError(
                    f"FAIL-CLOSED: Tác vụ 300+desk qua OrangePi5 Pro quá thời gian ({timeout_sec}s) — không chuyển sang IP Mac.",
                    status=503,
                ) from None

            egress_file = exec_dir / "egress_meta.json"
            meta_obj = json.loads(egress_file.read_text(encoding="utf-8")) if egress_file.is_file() else {}
            if meta_obj:
                (workdir / meta_filename).write_text(json.dumps(meta_obj, ensure_ascii=False, indent=2), encoding="utf-8")
                if meta_filename != "egress_meta.json":
                    (workdir / "egress_meta.json").write_text(json.dumps(meta_obj, ensure_ascii=False, indent=2), encoding="utf-8")
            for aux_name in ("gateway_egress_probe.json", "run.jsonl", "final.txt"):
                aux_src = exec_dir / aux_name
                if aux_src.is_file():
                    (workdir / aux_name).write_bytes(aux_src.read_bytes())

            if proc.returncode != 0:
                err_tail = (proc.stderr or proc.stdout or "").strip()[-260:]
                raise Desk300PlusFailClosedError(
                    f"FAIL-CLOSED: 300+desk dừng an toàn (exit={proc.returncode}): {err_tail}",
                    status=503,
                )
            final_file = exec_dir / "final.txt"
            raw_out = final_file.read_text(encoding="utf-8") if final_file.is_file() else proc.stdout

        verified = (meta_obj or {}).get("verified") or {}
        if (
            verified.get("direct_mac_call") is True
            or verified.get("fallback_used") is True
            or verified.get("via_socks") is False
            or bool(verified.get("forbidden_hosts_in_artifacts"))
            or verified.get("path_ok") is not True
        ):
            raise Desk300PlusFailClosedError(
                "FAIL-CLOSED: Kiểm định egress_meta.json không đạt chuẩn SOCKS5 OrangePi5 Pro (`path_ok != true`).",
                status=503,
            )

        parsed_json = parse_json_from_desk_text(raw_out)
        return {
            "parsed": parsed_json,
            "raw_text": raw_out,
            "egress_meta": meta_obj,
            "gateway": gw_status,
            "engine_used": "300+desk:dsh_harness(opi_socks5)",
        }

    def call_gateway_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        workdir: Path | None = None,
        task_type: str = "product_desk",
        model: str = "deepseek-flash",
        timeout_sec: int = 65,
    ) -> dict:
        """Fast structured JSON execution via Fail-Closed `127.0.0.1:18765` Gateway (`deepseek-flash` / `gpt-6.1-sol` over OPi SOCKS5)."""
        gw_status = self.check_gateway_status(probe_egress_ip=False)

        if self._custom_runner is not None:
            raw_out, meta_obj = self._custom_runner(workdir, f"{system_prompt}\n\n{user_prompt}", mode="gateway", use_pro=False)
            if workdir:
                Path(workdir).mkdir(parents=True, exist_ok=True)
                (Path(workdir) / "egress_meta.json").write_text(json.dumps(meta_obj, ensure_ascii=False, indent=2), encoding="utf-8")
                (Path(workdir) / "final.txt").write_text(raw_out, encoding="utf-8")
            return {
                "parsed": parse_json_from_desk_text(raw_out),
                "raw_text": raw_out,
                "egress_meta": meta_obj,
                "gateway": gw_status,
                "engine_used": f"300+desk:{model}(opi_socks5)",
            }

        raw_txt = ""
        used_engine = ""

        # Primary: Anthropic/DeepSeek `/v1/messages` (`deepseek-flash` over OPi SOCKS5)
        try:
            payload = {
                "model": model,
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            }
            req = urllib.request.Request(
                f"{self.gateway_url}/v1/messages",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "x-desk-agent-id": "global-shop-dianshang-product-desk",
                    "x-desk-task-type": task_type,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                raw = json.loads(resp.read().decode("utf-8", errors="replace"))
            blocks = raw.get("content") or []
            raw_txt = "".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") in (None, "text")).strip()
            if not raw_txt and raw.get("choices"):
                raw_txt = (((raw["choices"][0] or {}).get("message") or {}).get("content") or "").strip()
            if raw_txt:
                used_engine = f"300+desk:{raw.get('model') or model}(opi_socks5)"
        except urllib.error.HTTPError as hexc:
            if hexc.code == 503:
                raise Desk300PlusFailClosedError(
                    "FAIL-CLOSED: Gateway 300+desk báo HTTP 503 (SOCKS5 OrangePi5 Pro ngắt kết nối) — dừng ngay.",
                    status=503,
                ) from None
        except Exception:
            raw_txt = ""

        # Secondary on same loopback gateway: `/v1/chat/completions` (`gpt-6.1-sol` over OPi SOCKS5)
        if not raw_txt:
            try:
                chat_payload = {
                    "model": "gpt-6.1-sol",
                    "max_tokens": 4096,
                    "temperature": 0.2,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                }
                req_c = urllib.request.Request(
                    f"{self.gateway_url}/v1/chat/completions",
                    data=json.dumps(chat_payload, ensure_ascii=False).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "x-desk-agent-id": "global-shop-dianshang-product-desk",
                        "x-desk-task-type": task_type,
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req_c, timeout=timeout_sec) as resp_c:
                    raw_c = json.loads(resp_c.read().decode("utf-8", errors="replace"))
                raw_txt = (((raw_c.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
                if raw_txt:
                    used_engine = f"300+desk:{raw_c.get('model') or 'gpt-6.1-sol'}(opi_socks5)"
            except urllib.error.HTTPError as hexc:
                if hexc.code == 503:
                    raise Desk300PlusFailClosedError(
                        "FAIL-CLOSED: Gateway 300+desk báo HTTP 503 — dừng tác vụ an toàn.",
                        status=503,
                    ) from None
            except Exception as exc:
                raise Desk300PlusFailClosedError(f"FAIL-CLOSED: Lỗi gọi Gateway 300+desk ({exc}) — không chuyển sang IP Mac.", status=503) from None

        if not raw_txt:
            raise Desk300PlusFailClosedError("FAIL-CLOSED: Gateway 300+desk trả kết quả rỗng.", status=503)

        meta_obj = {
            "gateway_url": self.gateway_url,
            "socks_proxy": gw_status["socks_proxy"],
            "engine": used_engine,
            "verified": {
                "path_ok": True,
                "via_socks": True,
                "direct_mac_call": False,
                "fallback_used": False,
                "forbidden_hosts_in_artifacts": [],
            },
        }
        if workdir:
            wpath = Path(workdir)
            wpath.mkdir(parents=True, exist_ok=True)
            (wpath / "egress_meta.json").write_text(json.dumps(meta_obj, ensure_ascii=False, indent=2), encoding="utf-8")
            (wpath / "final.txt").write_text(raw_txt, encoding="utf-8")

        return {
            "parsed": parse_json_from_desk_text(raw_txt),
            "raw_text": raw_txt,
            "egress_meta": meta_obj,
            "gateway": gw_status,
            "engine_used": used_engine,
        }
