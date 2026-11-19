#!/usr/bin/env bash
set -euo pipefail
BASE="${1:-http://127.0.0.1:8999}"

echo "=== Smoke Test: Global Shop Dianshang ($BASE) ==="
curl -fsS "$BASE/api/health" | python3 -c "import sys,json; sys.path.insert(0,'.'); from backend import __version__; d=json.load(sys.stdin); assert d['status']=='ok' and d['version']==__version__, d; print('1. Health OK:', d['product'], d['version'])"
curl -fsS "$BASE/api/settings" | python3 -c "import sys,re; s=sys.stdin.read(); assert not re.search(r'apify_api_[A-Za-z0-9]{10,}|treg_(?!max_cost_usd|key)[A-Za-z0-9_-]{12,}|\b\d{8,12}:[A-Za-z0-9_-]{30,55}\b', s), 'Secret leaked!'; print('2. Settings masking OK')"
curl -fsS "$BASE/api/my-shops" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'facebook_fanpage' in d['platforms_catalog'] and 'tiktok_shop' in d['platforms_catalog'] and 'shopee' in d['platforms_catalog'], d; print('2b. My Shops API OK')"
curl -fsS "$BASE/api/hunt/painpoints" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'painpoints' in d, d; print('2c. Painpoints & Trends API OK')"
for route in "/" "/shop-cua-toi" "/tu-khoa" "/theo-doi" "/nguon-hang-tq" "/kho-shop" "/chien-dich" "/caidat"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE$route")
  [ "$code" = "200" ] || { echo "SPA route failed: $route ($code)"; exit 1; }
done
echo "3. SPA deep-links OK"
bad_host=$(curl -s -o /dev/null -w "%{http_code}" -H "Host: evil.example.com" "$BASE/api/health")
[ "$bad_host" = "403" ] || [ "$bad_host" = "404" ] || { echo "DNS rebinding guard failed ($bad_host)"; exit 1; }
echo "4. Host & Tailscale security guard OK ($bad_host)"
echo "=== ALL SMOKE CHECKS PASSED ==="
