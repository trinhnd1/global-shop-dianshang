#!/usr/bin/env python3
"""Direct launcher for Global Shop Dianshang Web + API server."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backend.webapp import main  # noqa: E402

if __name__ == "__main__":
    main()
