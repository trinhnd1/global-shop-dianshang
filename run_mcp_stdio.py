#!/usr/bin/env python3
"""Stdio-to-HTTP MCP JSON-RPC 2.0 bridge for Global Shop Dianshang."""
import argparse
import json
import os
import sys
import urllib.request


def main():
    parser = argparse.ArgumentParser(description="Global Shop Dianshang MCP Stdio Bridge")
    parser.add_argument("--url", default=os.environ.get("GS_MCP_URL", "http://127.0.0.1:8999/mcp"))
    parser.add_argument("--token", default=os.environ.get("GS_MCP_TOKEN", ""))
    args = parser.parse_args()

    session_id = ""
    for line in sys.stdin:
        s = line.strip()
        if not s:
            continue
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if args.token:
            headers["Authorization"] = f"Bearer {args.token}"
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        req = urllib.request.Request(args.url, data=s.encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                session_id = resp.headers.get("Mcp-Session-Id") or session_id
                if resp.status == 202:
                    continue
                body = resp.read().decode("utf-8").strip()
                if body:
                    sys.stdout.write(body + "\n")
                    sys.stdout.flush()
        except Exception as exc:
            err = {"jsonrpc": "2.0", "id": None, "error": {"code": -32001, "message": str(exc)}}
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
