#!/usr/bin/env python3
"""Open the isolated Dedicated Chrome Profile for Global Shop Dianshang."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.chrome_profile_hub import DedicatedChromeHub  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="./local-data")
    parser.add_argument("--portal", default="shopee", choices=["shopee", "tiktok_seller", "kalodata", "china_1688_taobao"])
    args = parser.parse_args()
    hub = DedicatedChromeHub(args.data_dir)
    print(json.dumps(hub.open_portal(args.portal), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
