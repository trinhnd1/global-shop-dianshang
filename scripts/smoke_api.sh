#!/usr/bin/env bash
set -euo pipefail
BASE="${1:-http://127.0.0.1:8999}"

echo "=== Smoke Test: Global Shop Dianshang ($BASE) ==="
curl -fsS "$BASE/api/health" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['status']=='ok' and d['version']=='1.0.1', d; print('1. Health OK:', d['product'], d['version'])"
curl -fsS "$BASE/api/settings" | python3 -c "import sys,json; s=sys.stdin.read(); assert 'apify_api_' not in s and 'treg_' not in s, 'Secret leaked!'; print('2. Settings masking OK')"
for route in "/" "/tu-khoa" "/theo-doi" "/nguon-hang-tq" "/kho-shop" "/chien-dich" "/caidat"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE$route")
  [ "$code" = "200" ] || { echo "SPA route failed: $route ($code)"; exit 1; }
done
echo "3. SPA deep-links OK"
bad_host=$(curl -s -o /dev/null -w "%{http_code}" -H "Host: evil.example.com" "$BASE/api/health")
[ "$bad_host" = "403" ] || [ "$bad_host" = "404" ] || { echo "DNS rebinding guard failed ($bad_host)"; exit 1; }
echo "4. Host & Tailscale security guard OK ($bad_host)"
echo "=== ALL SMOKE CHECKS PASSED ==="
