"""Cross-platform SecretStore with macOS Keychain priority and chmod 0600 file vault fallback.

Secrets NEVER reside in SQLite, git, logs, or HTTP responses.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading

KEYCHAIN_SERVICE = "com.peng.global-shop-dianshang"


class SecretStore:
    backend_name: str = "base"

    def get(self, name: str) -> str:
        raise NotImplementedError

    def set(self, name: str, value: str) -> None:
        raise NotImplementedError

    def delete(self, name: str) -> None:
        raise NotImplementedError


class FileSecretStore(SecretStore):
    backend_name = "file_vault_0600"

    def __init__(self, vault_path: str | Path):
        self.path = Path(vault_path)
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not self.path.exists():
            self._write_all({})

    def _read_all(self) -> dict[str, str]:
        if not self.path.is_file():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}
        except (ValueError, OSError):
            return {}

    def _write_all(self, data: dict[str, str]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        if os.name == "posix":
            tmp.chmod(0o600)
        tmp.replace(self.path)
        if os.name == "posix":
            self.path.chmod(0o600)

    def get(self, name: str) -> str:
        with self._lock:
            return self._read_all().get(name, "")

    def set(self, name: str, value: str) -> None:
        if not value:
            self.delete(name)
            return
        with self._lock:
            data = self._read_all()
            data[name] = value
            self._write_all(data)

    def delete(self, name: str) -> None:
        with self._lock:
            data = self._read_all()
            if name in data:
                del data[name]
                self._write_all(data)


class MacOSKeychainStore(SecretStore):
    backend_name = "macos_keychain"

    def __init__(self, service: str = KEYCHAIN_SERVICE, security_bin: str = "/usr/bin/security"):
        self.service = service
        self.security_bin = security_bin

    def is_available(self) -> bool:
        if sys.platform != "darwin" or not Path(self.security_bin).is_file():
            return False
        probe_acct = "__availability_probe__"
        proc = subprocess.run(
            [self.security_bin, "add-generic-password", "-U", "-s", self.service, "-a", probe_acct, "-w", "ok"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode != 0:
            return False
        subprocess.run(
            [self.security_bin, "delete-generic-password", "-s", self.service, "-a", probe_acct],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return True

    def get(self, name: str) -> str:
        proc = subprocess.run(
            [self.security_bin, "find-generic-password", "-s", self.service, "-a", name, "-w"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode != 0:
            return ""
        return proc.stdout.rstrip("\r\n")

    def set(self, name: str, value: str) -> None:
        if not value:
            self.delete(name)
            return
        proc = subprocess.run(
            [self.security_bin, "add-generic-password", "-U", "-s", self.service, "-a", name, "-w", value],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode != 0:
            raise RuntimeError("Không ghi được secret vào macOS Keychain")

    def delete(self, name: str) -> None:
        subprocess.run(
            [self.security_bin, "delete-generic-password", "-s", self.service, "-a", name],
            capture_output=True,
            text=True,
            timeout=5,
        )


def create_secret_store(data_dir: str | Path, prefer_keychain: bool = True, service: str = KEYCHAIN_SERVICE) -> SecretStore:
    root = Path(data_dir)
    fallback = FileSecretStore(root / ".secrets.vault.json")
    if prefer_keychain and sys.platform == "darwin" and shutil.which("security"):
        kc = MacOSKeychainStore(service=service)
        try:
            if kc.is_available():
                return kc
        except Exception:
            pass
    return fallback
