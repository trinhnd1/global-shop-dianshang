"""Global Shop Dianshang by Peng — E-Commerce Product Research, China Sourcing & Shop Operations."""
from pathlib import Path
import subprocess

PRODUCT_NAME = "Global Shop Dianshang"
__version__ = "1.0.14"
BASELINE_TAG = "v1.0.1"

_BUILD_CACHE: dict | None = None


def get_build_info() -> dict:
    global _BUILD_CACHE
    if _BUILD_CACHE is not None:
        return dict(_BUILD_CACHE)
    root = Path(__file__).resolve().parent.parent
    commit = "unknown"
    branch = "main"
    try:
        p1 = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=3,
        )
        if p1.returncode == 0 and p1.stdout.strip():
            commit = p1.stdout.strip()
        p2 = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=3,
        )
        if p2.returncode == 0 and p2.stdout.strip():
            branch = p2.stdout.strip()
    except Exception:
        pass
    _BUILD_CACHE = {
        "version": __version__,
        "baseline_tag": BASELINE_TAG,
        "git_commit": commit,
        "git_branch": branch,
    }
    return dict(_BUILD_CACHE)
