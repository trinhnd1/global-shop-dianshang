#!/usr/bin/env bash
set -euo pipefail

LABEL="com.peng.global-shop-dianshang"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${GLOBAL_SHOP_DATA_DIR:-$ROOT_DIR/local-data}"
LOG_DIR="$DATA_DIR/logs"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"
START_SCRIPT="$ROOT_DIR/scripts/start_launchagent.sh"
PORT="${GLOBAL_SHOP_PORT:-8999}"
UID_NUM="$(id -u)"
DOMAIN="gui/$UID_NUM"

ACTION="${1:-status}"

write_plist() {
  mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"
  chmod 700 "$DATA_DIR" "$LOG_DIR" 2>/dev/null || true
  chmod +x "$START_SCRIPT"

  cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${START_SCRIPT}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${ROOT_DIR}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>5</integer>
  <key>ProcessType</key>
  <string>Interactive</string>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/launchd.err.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>PYTHONUNBUFFERED</key>
    <string>1</string>
    <key>GLOBAL_SHOP_DATA_DIR</key>
    <string>${DATA_DIR}</string>
    <key>GLOBAL_SHOP_PORT</key>
    <string>${PORT}</string>
  </dict>
</dict>
</plist>
EOF
  chmod 644 "$PLIST_PATH"
  plutil -lint "$PLIST_PATH"
}

wait_healthy() {
  for _ in $(seq 1 20); do
    if curl -fsS "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then
      echo "✅ ${LABEL} đang chạy ổn định tại http://127.0.0.1:${PORT}"
      return 0
    fi
    sleep 0.5
  done
  echo "⚠️ Chưa phản hồi tại cổng ${PORT}, kiểm tra log tại ${LOG_DIR}/launchd.err.log" >&2
  return 1
}

case "$ACTION" in
  install)
    write_plist
    launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
    launchctl bootstrap "$DOMAIN" "$PLIST_PATH"
    launchctl enable "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
    launchctl kickstart -k "$DOMAIN/$LABEL"
    wait_healthy
    ;;
  restart)
    if [ ! -f "$PLIST_PATH" ]; then
      write_plist
      launchctl bootstrap "$DOMAIN" "$PLIST_PATH"
    else
      launchctl kickstart -k "$DOMAIN/$LABEL" || {
        launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
        launchctl bootstrap "$DOMAIN" "$PLIST_PATH"
      }
    fi
    wait_healthy
    ;;
  stop)
    launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
    echo "🛑 Đã tạm dừng LaunchAgent ${LABEL}"
    ;;
  uninstall)
    launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
    rm -f "$PLIST_PATH"
    echo "🗑 Đã gỡ LaunchAgent ${LABEL}"
    ;;
  logs)
    tail -n 50 "$LOG_DIR/launchd.out.log" "$LOG_DIR/launchd.err.log" 2>/dev/null || true
    ;;
  status|*)
    echo "=== LaunchAgent: ${LABEL} ==="
    echo "Plist: ${PLIST_PATH} ($([ -f "$PLIST_PATH" ] && echo 'ĐÃ CÀI' || echo 'CHƯA CÀI'))"
    launchctl print "$DOMAIN/$LABEL" 2>/dev/null | grep -E "state =|pid =|runs =|last exit code =" || echo "Trạng thái: chưa nạp vào launchd"
    curl -fsS "http://127.0.0.1:${PORT}/api/health" && echo "" || echo "HTTP health: offline"
    ;;
esac
