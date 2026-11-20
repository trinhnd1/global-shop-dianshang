#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PYTHONUNBUFFERED="1"
export LANG="en_US.UTF-8"
export LC_ALL="en_US.UTF-8"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${GLOBAL_SHOP_DATA_DIR:-$ROOT_DIR/local-data}"
PORT="${GLOBAL_SHOP_PORT:-8999}"
HOST="${GLOBAL_SHOP_HOST:-127.0.0.1}"

mkdir -p "$DATA_DIR/logs"
chmod 700 "$DATA_DIR" "$DATA_DIR/logs" 2>/dev/null || true

# Ensure Tailscale port proxy is active after reboot (non-blocking & idempotent)
for ts_bin in "/Applications/Tailscale.app/Contents/MacOS/Tailscale" "/opt/homebrew/bin/tailscale" "/usr/local/bin/tailscale"; do
  if [ -x "$ts_bin" ]; then
    if ! "$ts_bin" serve status 2>/dev/null | grep -q ":$PORT"; then
      "$ts_bin" serve --bg --http="$PORT" "http://127.0.0.1:$PORT" >/dev/null 2>&1 || true
    fi
    break
  fi
done

PYTHON_BIN="/opt/homebrew/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

cd "$ROOT_DIR"
exec "$PYTHON_BIN" "$ROOT_DIR/run_webapp.py" --data-dir "$DATA_DIR" --host "$HOST" --port "$PORT"
