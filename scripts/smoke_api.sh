#!/usr/bin/env bash
set -euo pipefail
BASE="${1:-http://127.0.0.1:8999}"

echo "=== Smoke Test: Global Shop Dianshang ($BASE) ==="
curl -fsS "$BASE/api/health" | python3 -c "import sys,json; sys.path.insert(0,'.'); from backend import __version__; d=json.load(sys.stdin); assert d['status']=='ok' and d['version']==__version__, d; print('1. Health OK:', d['product'], d['version'])"
curl -fsS "$BASE/api/settings" | python3 -c "import sys,re; s=sys.stdin.read(); assert not re.search(r'apify_api_[A-Za-z0-9]{10,}|treg_(?!max_cost_usd|key)[A-Za-z0-9_-]{12,}|\b\d{8,12}:[A-Za-z0-9_-]{30,55}\b', s), 'Secret leaked!'; print('2. Settings masking OK')"
curl -fsS "$BASE/api/my-shops" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'facebook_fanpage' in d['platforms_catalog'] and 'tiktok_shop' in d['platforms_catalog'] and 'shopee' in d['platforms_catalog'], d; print('2b. My Shops API OK')"
curl -fsS "$BASE/api/hunt/painpoints" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'painpoints' in d, d; print('2c. Painpoints & Trends API OK')"
curl -fsS "$BASE/api/desk300/status" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('fail_closed') is True, d; print('2d. 300+desk Fail-Closed Gateway Status:', 'READY -> ' + str(d.get('socks_proxy')) if d.get('ok') else 'OFFLINE_GUARDED')"
curl -fsS "$BASE/api/apify-store/stats" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'total_actors' in d and 'goals_catalog' in d, d; print('2e. Apify Store Local Catalog OK:', d['total_actors'], 'actors')"
curl -fsS "$BASE/api/ecosystems" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'collections' in d, d; print('2f. Ecosystem Playbooks Hub OK:', d.get('total', len(d['collections'])), 'collections')"
curl -fsS "$BASE/api/kalodata/status" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'account_email' in d and 'profile_name' in d, d; print('2g. Kalodata & Global Selling Bridge OK:', d['profile_name'], d['account_email'])"
curl -fsS "$BASE/api/hunt/schedules" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'schedules' in d and 'recent_runs' in d, d; print('2h. Recurring Hunt Autopilot Schedules OK:', len(d['schedules']), 'schedules')"
curl -fsS "$BASE/api/products/jev-leaderboard" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'kpis' in d and 'podium_top3' in d and 'items' in d, d; print('2i. Jev AI Product Leaderboard OK:', d['kpis']['total_scored'], 'scored products')"
curl -fsS "$BASE/api/system/launchagent" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['label']=='com.peng.global-shop-dianshang', d; print('2j. LaunchAgent Status Endpoint OK: installed=' + str(d['installed']) + ', running=' + str(d['running']) + ', pid=' + str(d['pid']))"
curl -fsS "$BASE/api/hunt/kalodata-vn/categories" | python3 -c "import sys,json; d=json.load(sys.stdin); assert len(d['items'])>=30, d; print('2k. Kalodata Pro 9-Page & VN Hunter Catalog OK:', len(d['items']), 'categories')"
curl -fsS "$BASE/api/kalodata/capabilities" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['capabilities']['kalodata_pro_9_pages_cdp'] is True and d['capabilities']['import_xlsx_csv_json_zip'] is True, d; print('2l. Kalodata Import Wizard & Browser Capture Capabilities OK')"
curl -fsS "$BASE/api/kalodata/mirror-status" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['mirror_enabled'] is True and d['account_email'], d; print('2m. Kalodata Auto-Mirror with affiliate-peng OK:', d['account_email'], 'last_synced=' + str(d['last_synced_at']))"
for route in "/" "/kalodata-pro" "/nhap-kalodata" "/bang-xep-hang-jev" "/he-sinh-thai" "/luong-300-desk" "/apify-store" "/shop-cua-toi" "/tu-khoa" "/theo-doi" "/nguon-hang-tq" "/kho-shop" "/chien-dich" "/caidat"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE$route")
  [ "$code" = "200" ] || { echo "SPA route failed: $route ($code)"; exit 1; }
done
echo "3. SPA deep-links OK"
for icon_route in "/favicon.ico" "/favicon.svg" "/favicon-32x32.png" "/apple-touch-icon.png" "/icon-192.png" "/icon-512.png" "/site.webmanifest"; do
  ct=$(curl -fsS -o /dev/null -w "%{content_type}" "$BASE$icon_route")
  echo "$ct" | grep -qv "text/html" || { echo "Icon route returned HTML instead of icon: $icon_route ($ct)"; exit 1; }
done
echo "3b. Custom Favicon, Apple Touch Icon & WebManifest OK"
bad_host=$(curl -s -o /dev/null -w "%{http_code}" -H "Host: evil.example.com" "$BASE/api/health")
[ "$bad_host" = "403" ] || [ "$bad_host" = "404" ] || { echo "DNS rebinding guard failed ($bad_host)"; exit 1; }
echo "4. Host & Tailscale security guard OK ($bad_host)"
echo "=== ALL SMOKE CHECKS PASSED ==="
