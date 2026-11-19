/* Global Shop Dianshang v1.0.1 — CSP-clean Vanilla ES2020 SPA */
(() => {
  const ROUTE_TO_TAB = {
    "/": "hunt",
    "/san-sp": "hunt",
    "/tu-khoa": "keywords",
    "/theo-doi": "watches",
    "/soi-shop": "shopspy",
    "/creators": "shopspy",
    "/kho": "results",
    "/nguon-hang-tq": "sourcing",
    "/kho-shop": "shops",
    "/soi-san-pham": "spy",
    "/video-jev": "videojev",
    "/clone-video": "videoclone",
    "/chien-dich": "campaigns",
    "/doanh-so": "analytics",
    "/nhat-ky": "history",
    "/tro-ly": "chat",
    "/caidat": "settings",
  };

  let CURRENT_BUCKET = "all";
  let SELECTED_PIDS = new Set();
  let ALL_SHOPS = [];
  let ALL_CAMPAIGNS = [];
  let INDUSTRIES_MAP = {};
  let BUCKETS_MAP = {};

  function esc(val) {
    return String(val ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function vnd(n) {
    const num = Number(n || 0);
    return Math.round(num).toLocaleString("vi-VN") + "đ";
  }

  function toast(msg, isErr = false) {
    const el = document.getElementById("toast");
    if (!el) return;
    el.textContent = msg;
    el.style.background = isErr ? "#ef4444" : "#10b981";
    el.style.color = isErr ? "#fff" : "#032217";
    el.classList.add("show");
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.remove("show"), 3400);
  }

  async function api(path, method = "GET", body = null) {
    const opts = { method, headers: {} };
    if (body !== null) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const resp = await fetch(path, opts);
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new Error(data.detail || `HTTP ${resp.status}`);
    }
    return data;
  }

  function openModal(title, html) {
    document.getElementById("modalTitle").textContent = title;
    document.getElementById("modalBody").innerHTML = html;
    document.getElementById("mainModalBackdrop").classList.add("open");
  }

  function closeModal() {
    document.getElementById("mainModalBackdrop").classList.remove("open");
  }

  function showTab(tab, pushUrl = null) {
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    const target = document.getElementById(`view-${tab}`);
    if (target) target.classList.add("active");

    document.querySelectorAll(".nav-btn").forEach((b) => {
      b.classList.toggle("active", b.dataset.tab === tab);
    });
    document.getElementById("sidebar")?.classList.remove("open");

    if (pushUrl) {
      window.history.pushState({ tab }, "", pushUrl);
    }
    refreshTab(tab);
  }

  async function loadOverview() {
    try {
      const ov = await api("/api/overview");
      document.getElementById("kpiVault").textContent = ov.vault_products;
      document.getElementById("kpiWatches").textContent = ov.watches_count;
      document.getElementById("kpiShopsSrc").textContent = `${ov.shops_count} shop / ${ov.sourcing_count} mẫu TQ`;
      const sp = ov.sales || {};
      document.getElementById("kpiSalesProfit").textContent = `${vnd(sp.gross_gmv_vnd)} / Lãi ${vnd(sp.net_profit_vnd)}`;
      document.getElementById("cntProducts").textContent = ov.vault_products;
      document.getElementById("cntWatches").textContent = ov.watches_count;
      document.getElementById("cntShops").textContent = ov.shops_count;
    } catch (_) {}
  }

  async function refreshTab(tab) {
    loadOverview();
    if (tab === "results") await loadProducts();
    else if (tab === "keywords") await loadKeywordHistory();
    else if (tab === "watches") await loadWatches();
    else if (tab === "shopspy") await loadCreatorsAndScans();
    else if (tab === "sourcing") await loadSourcing();
    else if (tab === "shops") await loadShops();
    else if (tab === "videojev") await loadVideoWatchlist();
    else if (tab === "videoclone") await loadVideoClones();
    else if (tab === "campaigns") await loadCampaigns();
    else if (tab === "analytics") await loadAnalytics();
    else if (tab === "history") await loadHistory();
    else if (tab === "chat") await loadChatAndPins();
    else if (tab === "settings") await loadSettings();
  }

  // --- PART 1.1: HUNT --------------------------------------------------------
  async function pollHuntLogs() {
    try {
      const st = await api("/api/hunt/status");
      const job = st.active_job;
      if (!job) return;
      const box = document.getElementById("huntLogsBox");
      if (box && job.logs) {
        box.textContent = `[${job.status.toUpperCase()}] ${job.title} (Chi phí: $${Number(job.actual_cost_usd || 0).toFixed(4)})\n` + job.logs.join("\n");
      }
      if (job.status === "running") {
        setTimeout(pollHuntLogs, 2200);
      } else {
        loadOverview();
      }
    } catch (_) {}
  }

  // --- PART 1.2: KEYWORD RESEARCH --------------------------------------------
  function renderKeywordResult(res) {
    const s = res.summary_stats || {};
    const jev = s.jev_evaluation;
    const html = `
      <div class="card">
        <h3>📊 Kết quả Phân tích Từ khoá: "${esc(res.keyword)}" (${esc(res.platform)})</h3>
        <div class="kpi-grid">
          <div class="kpi"><div class="lbl">Tổng lượng SP trên từ khoá</div><div class="val">${esc(s.total_products)}</div></div>
          <div class="kpi"><div class="lbl">Tổng lượt bán mẫu trang 1</div><div class="val green">${Number(s.total_sold_sample || 0).toLocaleString("vi-VN")}</div></div>
          <div class="kpi"><div class="lbl">Giá bán Trung bình / Trung vị</div><div class="val">${vnd(s.avg_price_vnd)} / ${vnd(s.median_price_vnd)}</div></div>
          <div class="kpi"><div class="lbl">Tỷ lệ Mall / Top 3 Shop chiếm</div><div class="val gold">${s.mall_share_pct}% / ${s.top3_shop_concentration_pct}%</div></div>
          <div class="kpi"><div class="lbl">Điểm Cơ hội Jev AI</div><div class="val green">${jev ? jev.opportunity_score_10 + " / 10" : "Chưa chấm"}</div></div>
        </div>
        <table class="tbl">
          <thead><tr><th>Tên sản phẩm</th><th>Shop</th><th>Giá bán</th><th>Đã bán</th><th>Doanh số ước tính</th><th>Thao tác</th></tr></thead>
          <tbody>
            ${(res.items || []).map((it, idx) => `
              <tr>
                <td><a href="${esc(it.url)}" target="_blank" style="color:#93c5fd">${esc(it.title)}</a> ${it.is_mall ? '<span class="badge red">Mall</span>' : ""}</td>
                <td>${esc(it.shop_name)}</td>
                <td>${vnd(it.price_vnd)}</td>
                <td><strong>${Number(it.sold_count || 0).toLocaleString("vi-VN")}</strong></td>
                <td>${vnd(it.gmv_vnd)}</td>
                <td><button class="btn btn-sm btn-pri" data-action="save-kw-item" data-idx="${idx}">+ Lưu Kho</button></td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
    const box = document.getElementById("kwResultBox");
    box.innerHTML = html;
    box._lastItems = res.items || [];
  }

  async function loadKeywordHistory() {
    const data = await api("/api/keywords/history");
    const rows = data.researches || [];
    document.getElementById("kwHistoryBox").innerHTML = rows.length
      ? `<table class="tbl">
          <thead><tr><th>Từ khoá</th><th>Sàn</th><th>Tổng SP</th><th>Lượt bán mẫu</th><th>Giá TB</th><th>Mall %</th><th>Điểm Jev</th><th>Thời gian</th></tr></thead>
          <tbody>${rows.map((r) => `
            <tr>
              <td><strong>${esc(r.keyword)}</strong></td>
              <td><span class="badge blue">${esc(r.platform)}</span></td>
              <td>${r.total_products}</td>
              <td>${Number(r.total_sold_sample || 0).toLocaleString("vi-VN")}</td>
              <td>${vnd(r.avg_price_vnd)}</td>
              <td>${r.mall_share_pct}%</td>
              <td>${r.jev_opportunity_score != null ? `<span class="badge green">${r.jev_opportunity_score}/10</span>` : "—"}</td>
              <td>${esc(r.created_at)}</td>
            </tr>`).join("")}
          </tbody>
        </table>`
      : `<div style="color:var(--muted)">Chưa có lịch sử tra cứu từ khoá.</div>`;
  }

  // --- PART 1.3: WATCHES & DIFF ----------------------------------------------
  async function loadWatches() {
    const data = await api("/api/watches");
    const ws = data.watches || [];
    document.getElementById("watchesListBox").innerHTML = ws.length
      ? `<table class="tbl">
          <thead><tr><th>Loại</th><th>Sàn</th><th>Mục tiêu theo dõi</th><th>Kết quả lần check gần nhất</th><th>Check lúc</th><th>Thao tác</th></tr></thead>
          <tbody>${ws.map((w) => {
            const sm = w.last_summary || {};
            return `<tr>
              <td><span class="badge gold">${esc(w.watch_type.toUpperCase())}</span></td>
              <td><span class="badge blue">${esc(w.platform)}</span></td>
              <td><strong>${esc(w.title)}</strong><div style="font-size:11.5px;color:var(--muted)">${esc(w.target_key)}</div></td>
              <td>${esc(sm.headline || "Chưa chạy lần đầu")}</td>
              <td>${esc(w.last_checked_at || "—")}</td>
              <td class="row">
                <button class="btn btn-sm btn-pri" data-action="watch-check" data-id="${esc(w.watch_id)}">🔄 Check &amp; So sánh</button>
                <button class="btn btn-sm btn-danger" data-action="watch-delete" data-id="${esc(w.watch_id)}">Xoá</button>
              </td>
            </tr>`;
          }).join("")}</tbody>
        </table>`
      : `<div style="color:var(--muted)">Chưa có mục theo dõi nào. Hãy thêm Từ khoá, Sản phẩm hoặc Shop ở trên!</div>`;

    const runs = data.recent_runs || [];
    document.getElementById("watchRunsDiffBox").innerHTML = runs.length
      ? runs.map((r) => {
          const d = r.diff || {};
          const newList = (d.new_items || []).slice(0, 6).map((ni) => `<li>🆕 <strong>${esc(ni.title)}</strong> — ${vnd(ni.price_vnd)} (Đã bán: ${ni.sold_count})</li>`).join("");
          const riseList = (d.rising_items || []).slice(0, 5).map((ri) => `<li>📈 <strong>${esc(ri.title)}</strong> — Tăng <strong>+${ri.delta_sold}</strong> lượt bán (Tổng: ${ri.sold_count})</li>`).join("");
          return `<div style="border-bottom:1px solid var(--border);padding:10px 0">
            <div class="row" style="justify-content:space-between">
              <div><span class="badge blue">${esc(r.watch_type.toUpperCase())} · ${esc(r.platform)}</span>
                Tổng SP: <strong>${r.total_count}</strong> ${r.prev_total_count != null ? `(Trước: ${r.prev_total_count})` : "(Mốc gốc đầu tiên)"} ·
                <span class="badge green">+${r.new_items_count} SP mới</span> ·
                <span class="badge gold">${r.rising_items_count} SP tăng lượt bán</span>
              </div>
              <span style="font-size:12px;color:var(--muted)">${esc(r.created_at)}</span>
            </div>
            ${newList ? `<ul style="margin:6px 0 0 18px;padding:0;font-size:12.5px;color:#6ee7b7">${newList}</ul>` : ""}
            ${riseList ? `<ul style="margin:6px 0 0 18px;padding:0;font-size:12.5px;color:#fcd34d">${riseList}</ul>` : ""}
          </div>`;
        }).join("")
      : `<div style="color:var(--muted)">Chưa có lịch sử đối chiếu.</div>`;
  }

  // --- PART 1.4: SHOP SCANNER & TIKTOK CREATORS ------------------------------
  async function loadCreatorsAndScans() {
    const [crData, shData] = await Promise.all([api("/api/creators"), api("/api/shops/scans")]);
    const crs = crData.creators || [];
    document.getElementById("creatorsListBox").innerHTML = crs.length
      ? crs.map((c) => `
          <div style="border-bottom:1px solid var(--border);padding:8px 0">
            <strong>@${esc(c.handle)}</strong> (${esc(c.display_name)}) · <span class="badge">${esc(c.industry_label)}</span>
            <div style="font-size:12px;color:var(--muted)">Followers: ${Number(c.followers || 0).toLocaleString("vi-VN")} · View TB: ${Number(c.avg_views || 0).toLocaleString("vi-VN")}</div>
          </div>`).join("")
      : `<div style="color:var(--muted)">Nhập từ khoá ngành hàng hoặc @handle để tìm Creator TikTok.</div>`;

    const scans = shData.scans || [];
    if (scans.length && !document.getElementById("shopScanResultBox").innerHTML) {
      const latest = scans[0];
      document.getElementById("shopScanResultBox").innerHTML = renderShopScanHtml(latest);
    }
  }

  function renderShopScanHtml(scan) {
    return `
      <div style="background:#0a1222;padding:10px;border-radius:8px">
        <strong>🏪 ${esc(scan.shop_name)} (${esc(scan.platform)})</strong> — ${scan.total_products} SP · Tổng lượt bán: <strong>${Number(scan.total_sold || 0).toLocaleString("vi-VN")}</strong> · Doanh số ước tính: <strong>${vnd(scan.estimated_gmv_vnd)}</strong>
        <table class="tbl" style="margin-top:8px">
          <thead><tr><th>Vai trò SP</th><th>Tên SP</th><th>Giá bán</th><th>Đã bán</th></tr></thead>
          <tbody>${(scan.items || []).slice(0, 12).map((it) => `
            <tr>
              <td><span class="badge ${it.shop_product_role === "hero_chu_luc" ? "gold" : "blue"}">${it.shop_product_role === "hero_chu_luc" ? "🔥 Chủ lực" : "Kéo traffic"}</span></td>
              <td><a href="${esc(it.url)}" target="_blank" style="color:#93c5fd">${esc(it.title)}</a></td>
              <td>${vnd(it.price_vnd)}</td>
              <td>${Number(it.sold_count || 0).toLocaleString("vi-VN")}</td>
            </tr>`).join("")}
          </tbody>
        </table>
      </div>`;
  }

  // --- PART 2.1: PRODUCT VAULT -----------------------------------------------
  async function loadProducts() {
    const ind = document.getElementById("filterIndustry")?.value || "";
    const plat = document.getElementById("filterPlatform")?.value || "";
    const sort = document.getElementById("filterSort")?.value || "updated";
    const q = document.getElementById("filterSearch")?.value || "";
    const qs = new URLSearchParams({ bucket: CURRENT_BUCKET, industry: ind, platform: plat, sort, q });
    const data = await api(`/api/products?${qs}`);

    BUCKETS_MAP = data.buckets || {};
    INDUSTRIES_MAP = data.industries || {};

    const indSel = document.getElementById("filterIndustry");
    if (indSel && indSel.options.length <= 1) {
      Object.entries(INDUSTRIES_MAP).forEach(([k, lbl]) => {
        const opt = document.createElement("option");
        opt.value = k;
        opt.textContent = lbl;
        indSel.appendChild(opt);
      });
    }
    const cmpInd = document.getElementById("cmpIndustry");
    if (cmpInd && !cmpInd.options.length) {
      Object.entries(INDUSTRIES_MAP).forEach(([k, lbl]) => {
        const opt = document.createElement("option");
        opt.value = k;
        opt.textContent = lbl;
        cmpInd.appendChild(opt);
      });
    }

    const bc = data.bucket_counts || {};
    const allActive = Object.entries(bc).reduce((acc, [k, v]) => (k === "da_loai" ? acc : acc + v), 0);
    const chipEntries = [["all", `Tất cả SP (${allActive})`], ...Object.entries(BUCKETS_MAP).map(([k, lbl]) => [k, `${lbl} (${bc[k] || 0})`])];
    document.getElementById("bucketChips").innerHTML = chipEntries.map(([k, lbl]) =>
      `<button class="chip ${CURRENT_BUCKET === k ? "active" : ""}" data-action="set-bucket-filter" data-bucket="${k}">${esc(lbl)}</button>`
    ).join("");

    const items = data.products || [];
    document.getElementById("productsGrid").innerHTML = items.length
      ? items.map((p) => {
          const ec = p.economics || {};
          const cls = p.jev_score >= 7.2 ? "is-gold" : p.jev_score >= 6.2 ? "is-green" : "";
          return `
            <div class="pcard ${cls}">
              <div class="pcard-top">
                ${p.image_url ? `<img class="pcard-img" src="${esc(p.image_url)}" alt="" loading="lazy" />` : `<div class="pcard-img" style="display:flex;align-items:center;justify-content:center;font-size:24px">📦</div>`}
                <div style="flex:1;min-width:0">
                  <div class="row" style="justify-content:space-between">
                    <label style="font-size:12px;color:var(--muted)"><input type="checkbox" data-action="toggle-select-pid" data-id="${p.id}" ${SELECTED_PIDS.has(p.id) ? "checked" : ""}/> #${p.id} · ${esc(p.platform.toUpperCase())}</label>
                    <span class="badge ${p.jev_score >= 7 ? "gold" : "green"}">${p.jev_score != null ? `🤖 Jev ${p.jev_score}/10` : "Chưa chấm Jev"}</span>
                  </div>
                  <div style="font-weight:600;margin:4px 0"><a href="${esc(p.url || "#")}" target="_blank" style="color:var(--txt);text-decoration:none">${esc(p.title)}</a></div>
                  <div class="row">
                    <span class="badge blue">${esc(p.industry_label)}</span>
                    <span class="badge">${esc(p.bucket_label)}</span>
                    ${p.is_mall ? '<span class="badge red">Mall</span>' : ""}
                  </div>
                </div>
              </div>

              <div class="pstats">
                <div>Giá bán<strong>${vnd(p.price_vnd)}</strong></div>
                <div>Giá vốn về tay<strong>${p.cost_vnd > 0 ? vnd(p.cost_vnd) : "Chưa ghép"}</strong></div>
                <div>Lượt bán<strong>${Number(p.sold_count || 0).toLocaleString("vi-VN")}</strong></div>
                <div>Lãi ròng/đơn<strong style="color:${(ec.net_profit_per_order_vnd || 0) > 0 ? "#6ee7b7" : "var(--muted)"}">${p.cost_vnd > 0 ? vnd(ec.net_profit_per_order_vnd) : "—"}</strong></div>
              </div>

              <div style="font-size:12px;color:var(--muted)">Doanh số ước tính: <strong style="color:var(--txt)">${vnd(p.gmv_vnd)}</strong> · Shop: ${esc(p.shop_name || "—")}</div>

              <div class="row">
                <button class="btn btn-sm btn-pri" data-action="prod-score-jev" data-id="${p.id}">🤖 Chấm Jev</button>
                <button class="btn btn-sm btn-gold" data-action="prod-find-cn" data-id="${p.id}" data-title="${esc(p.title)}">🇨🇳 Tìm nguồn TQ</button>
                <button class="btn btn-sm" data-action="prod-dossier" data-id="${p.id}">📊 Dossier &amp; Giá vốn</button>
                <button class="btn btn-sm" data-action="prod-watch" data-id="${p.id}" data-plat="${esc(p.platform)}" data-url="${esc(p.url)}" data-title="${esc(p.title)}">🔭 Theo dõi</button>
              </div>
            </div>`;
        }).join("")
      : `<div class="card" style="grid-column:1/-1;color:var(--muted)">Kho sản phẩm đang trống ở bộ lọc này. Hãy chạy Săn SP, Tra cứu Từ khoá hoặc Quét Shop đối thủ!</div>`;
  }

  // --- PART 2.2: CHINA SOURCING ----------------------------------------------
  async function loadSourcing() {
    const data = await api("/api/sourcing");
    const items = data.items || [];
    document.getElementById("sourcingListBox").innerHTML = items.length
      ? `<table class="tbl">
          <thead><tr><th>Sàn TQ</th><th>Tên sản phẩm / Xưởng</th><th>Giá sỉ (CNY)</th><th>MOQ</th><th>Giá vốn về kho VN</th><th>SP Kho đã ghép</th><th>Thao tác</th></tr></thead>
          <tbody>${items.map((it) => `
            <tr>
              <td><span class="badge gold">${esc(it.platform.toUpperCase())}</span></td>
              <td><a href="${esc(it.item_url || "#")}" target="_blank" style="color:#93c5fd">${esc(it.title)}</a><div style="font-size:11.5px;color:var(--muted)">Xưởng: ${esc(it.supplier_name || "—")} · Đã bán: ${esc(it.sales_volume || "—")}</div></td>
              <td><strong>¥${Number(it.price_cny || 0).toFixed(2)}</strong></td>
              <td>${it.moq}</td>
              <td><strong style="color:#6ee7b7">${vnd(it.landed_cost_vnd)}</strong></td>
              <td>${it.linked_product_id ? `#${it.linked_product_id}` : "Chưa ghép"}</td>
              <td><button class="btn btn-sm btn-pri" data-action="sourcing-to-vault" data-id="${esc(it.sourcing_id)}">+ Tạo SP Kho từ mẫu này</button></td>
            </tr>`).join("")}
          </tbody>
        </table>`
      : `<div style="color:var(--muted)">Chưa có báo giá nguồn hàng 1688 / Pinduoduo / Taobao.</div>`;
  }

  // --- PART 2.3: SHOPS VAULT -------------------------------------------------
  async function loadShops() {
    const data = await api("/api/shops");
    ALL_SHOPS = data.shops || [];
    document.getElementById("shopsGridBox").innerHTML = ALL_SHOPS.length
      ? ALL_SHOPS.map((s) => `
          <div class="card">
            <div class="row" style="justify-content:space-between">
              <span class="badge ${s.role === "own_shop" ? "green" : "gold"}">${esc(s.role_label)}</span>
              <span class="badge blue">${esc(s.platform.toUpperCase())}</span>
            </div>
            <h3 style="margin:8px 0 4px">${esc(s.shop_name)}</h3>
            <div style="font-size:12.5px;color:var(--muted)">Ngành: ${esc(s.industry_label)} · Phí sàn: ${s.platform_fee_pct}% · SP gắn: <strong>${s.assigned_products_count}</strong></div>
            ${s.shop_url ? `<div style="margin-top:6px"><a href="${esc(s.shop_url)}" target="_blank" style="color:#93c5fd;font-size:12.5px">${esc(s.shop_url)}</a></div>` : ""}
            <div class="row" style="margin-top:10px">
              <button class="btn btn-sm btn-blue" data-action="shop-watch-from-vault" data-plat="${esc(s.platform)}" data-url="${esc(s.shop_url || s.handle)}" data-name="${esc(s.shop_name)}">🔭 Theo dõi Shop này</button>
              <button class="btn btn-sm btn-danger" data-action="shop-delete" data-id="${esc(s.shop_id)}">Xoá</button>
            </div>
          </div>`).join("")
      : `<div class="card" style="grid-column:1/-1;color:var(--muted)">Kho Shop chưa có gian hàng nào. Hãy thêm Shop của bạn và các Shop đối thủ mẫu!</div>`;
  }

  // --- PART 3.2 & 3.3: VIDEO JEV & CLONER ------------------------------------
  async function loadVideoWatchlist() {
    const data = await api("/api/videos/watchlist");
    const vids = data.videos || [];
    document.getElementById("videoWatchlistBox").innerHTML = vids.length
      ? vids.map((v) => {
          const sp = (v.detail || {}).script_3part || {};
          return `<div style="border-bottom:1px solid var(--border);padding:10px 0">
            <div class="row" style="justify-content:space-between">
              <strong>@${esc(v.author_handle || "video")} · Điểm Jev: <span class="badge green">${v.jev_score ?? "N/A"}/10</span></strong>
              <button class="btn btn-sm ${v.is_important ? "btn-gold" : ""}" data-action="video-toggle-star" data-key="${esc(v.video_key)}" data-imp="${v.is_important ? "0" : "1"}">⭐ Quan trọng</button>
            </div>
            <div style="font-size:12.5px;color:var(--muted);margin-top:4px">
              <strong>Hook:</strong> ${esc(sp.hook_0_3s || "—")} | <strong>Body:</strong> ${esc(sp.body_demo || "—")} | <strong>CTA:</strong> ${esc(sp.cta_close || "—")}
            </div>
          </div>`;
        }).join("")
      : `<div style="color:var(--muted)">Chưa có video nào được đánh giá.</div>`;
  }

  async function loadVideoClones() {
    const data = await api("/api/video-cloner");
    const clones = data.clones || [];
    document.getElementById("videoClonesBox").innerHTML = clones.map((c) => `
      <div class="card">
        <h3>⚡ Bản Clone #${esc(c.clone_id)} — Sản phẩm: ${esc((c.detail || {}).product_title || "")} (${c.duration_sec}s)</h3>
        ${(c.segments || []).map((seg) => `
          <div class="grid2" style="margin-top:8px">
            <div>
              <div class="badge gold" style="margin-bottom:4px">Phân đoạn ${seg.segment_index} (${seg.duration_sec}s) · Nano Banana 2.1 (Ảnh 9:16)</div>
              <pre class="codebox">${esc(JSON.stringify(seg.image_prompt_json, null, 2))}</pre>
            </div>
            <div>
              <div class="badge green" style="margin-bottom:4px">Gemini Omni 1.2 Flash (Video 4K + Voice Lock)</div>
              <pre class="codebox">${esc(JSON.stringify(seg.video_prompt_json, null, 2))}</pre>
            </div>
          </div>`).join("")}
      </div>`).join("");
  }

  // --- PART 4.1 & 4.2: CAMPAIGNS & ANALYTICS ---------------------------------
  async function loadCampaigns() {
    const [cmpData, prodData] = await Promise.all([api("/api/campaigns"), api("/api/products?bucket=all")]);
    ALL_CAMPAIGNS = cmpData.campaigns || [];
    const stagesCat = cmpData.stages_catalog || {};
    const allProds = prodData.products || [];

    document.getElementById("campaignsListBox").innerHTML = ALL_CAMPAIGNS.length
      ? ALL_CAMPAIGNS.map((c) => `
          <div class="card">
            <div class="row" style="justify-content:space-between">
              <div>
                <h3 style="margin:0">🚀 ${esc(c.name)} <span class="badge blue">${esc(c.industry_label)}</span></h3>
                <div style="font-size:12.5px;color:var(--muted);margin-top:3px">Mục tiêu: ${vnd(c.target_revenue_vnd)} · Đã bán thực tế: <strong>${vnd(c.sales_kpis.gmv_vnd)}</strong> (Lãi ròng: <strong style="color:#6ee7b7">${vnd(c.sales_kpis.net_profit_vnd)}</strong>)</div>
              </div>
              <button class="btn btn-sm btn-gold" data-action="cmp-send-brief" data-id="${esc(c.campaign_id)}">📨 Gửi Báo cáo Telegram Ngay</button>
            </div>

            <div class="row" style="margin:10px 0">
              <select id="cmpAddProd_${esc(c.campaign_id)}" style="max-width:280px">
                <option value="">-- Chọn SP từ Kho đưa vào Chiến dịch --</option>
                ${allProds.map((p) => `<option value="${p.id}">#${p.id} ${esc(p.title.slice(0, 48))}</option>`).join("")}
              </select>
              <select id="cmpAddStage_${esc(c.campaign_id)}" style="max-width:230px">
                ${Object.entries(stagesCat).map(([k, lbl]) => `<option value="${k}">${esc(lbl)}</option>`).join("")}
              </select>
              <button class="btn btn-sm btn-pri" data-action="cmp-attach-prod" data-id="${esc(c.campaign_id)}">+ Gắn / Đổi Giai đoạn</button>
            </div>

            ${(c.products || []).length ? `<div style="margin-bottom:10px">${c.products.map((p) => `<span class="badge green" style="margin:2px 4px 2px 0">#${p.id} ${esc(p.title.slice(0, 34))} → ${esc(p.campaign_stage_label)}</span>`).join("")}</div>` : ""}

            <div style="background:#0a1222;padding:10px;border-radius:8px">
              <strong style="font-size:12.5px">📋 Checklist Vận hành Hàng ngày:</strong>
              ${(c.tasks || []).map((t) => `
                <div style="margin-top:5px">
                  <label style="cursor:pointer"><input type="checkbox" data-action="cmp-toggle-task" data-cid="${esc(c.campaign_id)}" data-tid="${esc(t.task_id)}" ${t.done_today ? "checked" : ""}/> ${esc(t.title)}</label>
                </div>`).join("")}
            </div>
          </div>`).join("")
      : `<div class="card" style="color:var(--muted)">Chưa có Chiến dịch Ngành hàng nào.</div>`;
  }

  async function loadAnalytics() {
    const data = await api("/api/sales/summary");
    const k = data.seller_kpis || {};
    const m = data.market_research_kpis || {};
    document.getElementById("salesSummaryBox").innerHTML = `
      <div class="kpi-grid">
        <div class="kpi"><div class="lbl">Đơn bán hợp lệ / Lượt bán</div><div class="val">${k.valid_orders} đơn / ${k.units_sold} cái</div></div>
        <div class="kpi"><div class="lbl">Tổng Doanh số Bán hàng (GMV)</div><div class="val gold">${vnd(k.gross_gmv_vnd)}</div></div>
        <div class="kpi"><div class="lbl">Tổng Giá vốn (COGS) + Phí sàn</div><div class="val">${vnd((k.total_cogs_vnd || 0) + (k.platform_fees_vnd || 0))}</div></div>
        <div class="kpi"><div class="lbl">Chi phí Ads &amp; Vận hành</div><div class="val">${vnd(k.ads_and_ops_expenses_vnd)}</div></div>
        <div class="kpi"><div class="lbl">Lợi nhuận Ròng Thực tế</div><div class="val green">${vnd(k.net_profit_vnd)} (${k.net_margin_pct}%)</div></div>
        <div class="kpi"><div class="lbl">Tổng Lượt bán Thị trường trong Kho</div><div class="val">${Number(m.observed_market_units_sold || 0).toLocaleString("vi-VN")}</div></div>
      </div>`;
  }

  // --- PART 4.3, 4.4, 4.5: HISTORY, CHAT/PINS, SETTINGS ----------------------
  async function loadHistory() {
    const data = await api("/api/history-logs");
    const logs = data.logs || [];
    document.getElementById("historyLogsBox").innerHTML = logs.length
      ? `<table class="tbl">
          <thead><tr><th>Mã GS</th><th>Phân hệ</th><th>Tác vụ</th><th>Trạng thái</th><th>Tóm tắt kết quả</th><th>Telegram</th><th>Thời gian</th></tr></thead>
          <tbody>${logs.map((l) => `
            <tr>
              <td><strong>${esc(l.gs_code)}</strong></td>
              <td><span class="badge blue">${esc(l.module)}</span></td>
              <td>${esc(l.title)}</td>
              <td><span class="badge ${l.status === "completed" ? "green" : l.status === "failed" ? "red" : "gold"}">${esc(l.status)}</span></td>
              <td>${esc(l.summary)}</td>
              <td>${l.telegram_notified_at ? "✅ Đã báo" : "—"}</td>
              <td>${esc(l.created_at)}</td>
            </tr>`).join("")}
          </tbody>
        </table>`
      : `<div style="color:var(--muted)">Chưa có nhật ký công việc nào.</div>`;
  }

  async function loadChatAndPins() {
    const [ch, pn] = await Promise.all([api("/api/chat/messages"), api("/api/pins")]);
    document.getElementById("chatMessagesBox").innerHTML = (ch.messages || []).map((m) => `
      <div style="margin-bottom:8px;padding:8px 10px;border-radius:8px;background:${m.role === "user" ? "#1b2945" : "#0a1222"}">
        <strong>${m.role === "user" ? "🧑 Bạn" : "🤖 Cố vấn Shop"}:</strong>
        <div style="white-space:pre-wrap;margin-top:3px">${esc(m.content)}</div>
      </div>`).join("");
    document.getElementById("pinsListBox").innerHTML = (pn.pins || []).map((p) => `
      <div class="row" style="justify-content:space-between;border-bottom:1px solid var(--border);padding:6px 0">
        <a href="${esc(p.url || "#")}" target="_blank" style="color:#93c5fd">${esc(p.title)}</a>
        <button class="btn btn-sm btn-danger" data-action="pin-del" data-id="${p.id}">Xoá</button>
      </div>`).join("");
  }

  async function loadSettings() {
    const [mv, tg, bh, mcp] = await Promise.all([
      api("/api/settings"),
      api("/api/providers/telegram/status"),
      api("/api/connections/browser"),
      api("/api/mcp/status"),
    ]);
    const st = mv.settings || {};
    document.getElementById("setTgToken").value = st.notify?.telegram_token || "";
    document.getElementById("setTgChatId").value = st.notify?.telegram_chat_id || "";
    document.getElementById("setTregKey").value = st.providers?.treg_key || "";
    document.getElementById("setJevKey").value = st.providers?.typesafe_key || "";
    document.getElementById("setCnyRate").value = st.sourcing?.cny_to_vnd_rate ?? 3650;
    document.getElementById("setShipKg").value = st.sourcing?.cn_shipping_per_kg_vnd ?? 28000;
    document.getElementById("setPackVnd").value = st.sourcing?.packaging_cost_vnd ?? 3500;
    document.getElementById("setShopeeFee").value = st.sourcing?.shopee_fee_pct ?? 12.5;
    document.getElementById("setTiktokFee").value = st.sourcing?.tiktok_shop_fee_pct ?? 11.5;
    document.getElementById("setReturnPct").value = st.sourcing?.default_return_pct ?? 6.0;

    document.getElementById("apifyKeysBox").innerHTML = (st.providers?.apify_keys || []).map((k, i) => `
      <div class="row" style="justify-content:space-between;padding:5px 0;border-bottom:1px solid var(--border)">
        <span>#${i + 1} <strong>${esc(k.label)}</strong> <code>${esc(k.masked)}</code></span>
        <div class="row">
          <button class="btn btn-sm" data-action="apify-promote" data-id="${esc(k.id)}">⬆ Ưu tiên #1</button>
          <button class="btn btn-sm btn-danger" data-action="apify-del" data-id="${esc(k.id)}">Xoá</button>
        </div>
      </div>`).join("") || `<div style="color:var(--muted);font-size:12px">Chưa có Apify Key.</div>`;

    document.getElementById("tgStatusBox").innerHTML =
      `Bot: <strong>@${esc(tg.bot_username)}</strong> · Token: ${tg.token_configured ? "✅ Đã lưu Keychain" : "❌ Chưa lưu"} · Allowed IDs: <code>${esc((tg.allowed_user_ids || []).join(", "))}</code> · Tailscale: <a href="${esc(tg.tailscale_url)}" target="_blank" style="color:#6ee7b7">${esc(tg.tailscale_url)}</a>`;

    document.getElementById("browserHubBox").innerHTML =
      `Trạng thái Chrome Độc lập (CDP 127.0.0.1:${bh.cdp_port}): <strong>${bh.running ? "🟢 Đang mở (" + bh.open_tabs_count + " tab)" : "⚪ Đang đóng"}</strong> · SecretStore: <code>${esc(mv.secret_backend)}</code>`;

    document.getElementById("mcpStatusBox").innerHTML =
      `🔌 MCP Gateway: <code>${esc(mcp.http_endpoint)}</code> (${mcp.tools_count} tools · chế độ <code>${esc(mcp.access_mode)}</code>)`;
  }

  // --- DELEGATED ACTIONS -----------------------------------------------------
  document.addEventListener("click", async (ev) => {
    const navBtn = ev.target.closest(".nav-btn");
    if (navBtn) {
      showTab(navBtn.dataset.tab, navBtn.dataset.route);
      return;
    }
    const actEl = ev.target.closest("[data-action]");
    if (!actEl) return;
    const act = actEl.dataset.action;

    try {
      if (act === "toggle-menu") {
        document.getElementById("sidebar")?.classList.toggle("open");
      } else if (act === "close-modal") {
        closeModal();
      } else if (act === "hunt-estimate" || act === "hunt-start") {
        const kws = document.getElementById("huntKeywords").value.split(/[\n,]+/).map((s) => s.trim()).filter(Boolean);
        const chs = [...document.querySelectorAll(".hunt-ch:checked")].map((c) => c.value);
        const payload = {
          keywords: kws,
          channels: chs,
          items_per_channel: Number(document.getElementById("huntLimit").value || 8),
          budget_limit_usd: Number(document.getElementById("huntBudget").value || 0.3),
          auto_score_jev: document.getElementById("huntAutoJev").checked,
        };
        if (act === "hunt-estimate") {
          const est = await api("/api/hunt/estimate", "POST", payload);
          document.getElementById("huntEstimateBox").textContent = `Chi phí dự kiến: $${est.estimated_cost_usd} / Trần $${est.budget_limit_usd} (${est.terms.length} từ khoá × ${est.channels.length} sàn)`;
        } else {
          await api("/api/hunt/start", "POST", payload);
          toast("Đã khởi chạy tiến trình Săn Sản phẩm!");
          pollHuntLogs();
        }
      } else if (act === "hunt-stop") {
        await api("/api/hunt/stop", "POST", {});
        toast("Đã gửi yêu cầu dừng");
      } else if (act === "gt-search") {
        const kw = document.getElementById("gtKeyword").value.trim();
        const res = await api("/api/hunt/google-trends", "POST", { keyword: kw });
        document.getElementById("huntLogsBox").textContent = JSON.stringify(res, null, 2);
        toast(res.summary);
      } else if (act === "kw-suggest") {
        const kw = document.getElementById("kwInput").value.trim();
        const res = await api("/api/keywords/suggest", "POST", { keyword: kw });
        document.getElementById("kwSuggestChips").innerHTML = (res.suggestions || []).map((s) =>
          `<button class="chip" data-action="pick-kw-chip" data-kw="${esc(s)}">${esc(s)}</button>`
        ).join("");
      } else if (act === "pick-kw-chip") {
        document.getElementById("kwInput").value = actEl.dataset.kw;
      } else if (act === "kw-research") {
        toast("Đang quét từ khoá & chấm điểm Jev...");
        const res = await api("/api/keywords/research", "POST", {
          keyword: document.getElementById("kwInput").value.trim(),
          platform: document.getElementById("kwPlatform").value,
          limit: Number(document.getElementById("kwLimit").value || 20),
          save_top_to_vault: document.getElementById("kwSaveVault").checked,
        });
        renderKeywordResult(res);
        loadKeywordHistory();
        loadOverview();
        toast(res.summary);
      } else if (act === "save-kw-item") {
        const items = document.getElementById("kwResultBox")._lastItems || [];
        const it = items[Number(actEl.dataset.idx)];
        if (it) {
          const r = await api("/api/products", "POST", { ...it, source: "keyword_pick" });
          toast(r.summary);
          loadOverview();
        }
      } else if (act === "kw-watch-create") {
        const kw = document.getElementById("kwInput").value.trim();
        const plat = document.getElementById("kwPlatform").value;
        await api("/api/watches", "POST", { watch_type: "keyword", platform: plat, target_key: kw, title: `Từ khoá: ${kw}`, run_immediately: true });
        toast(`Đã tạo theo dõi định kỳ từ khoá '${kw}'!`);
        showTab("watches", "/theo-doi");
      } else if (act === "watch-create") {
        const target = document.getElementById("wtTarget").value.trim();
        await api("/api/watches", "POST", {
          watch_type: document.getElementById("wtType").value,
          platform: document.getElementById("wtPlatform").value,
          interval_hours: Number(document.getElementById("wtInterval").value || 12),
          target_key: target,
          title: document.getElementById("wtTitle").value.trim() || target,
          run_immediately: true,
        });
        toast("Đã tạo theo dõi & chụp mốc dữ liệu đầu tiên!");
        loadWatches();
        loadOverview();
      } else if (act === "watch-check") {
        toast("Đang kiểm tra & đối chiếu sản phẩm mới...");
        const res = await api(`/api/watches/${actEl.dataset.id}/check`, "POST", {});
        toast(res.summary);
        loadWatches();
        loadOverview();
      } else if (act === "watch-delete") {
        await api(`/api/watches/${actEl.dataset.id}`, "DELETE");
        loadWatches();
      } else if (act === "shop-scan-run") {
        toast("Đang quét danh mục sản phẩm của Shop...");
        const res = await api("/api/shops/scan-products", "POST", {
          shop_query: document.getElementById("scanShopQuery").value.trim(),
          platform: document.getElementById("scanShopPlat").value,
          score_top_jev: Number(document.getElementById("scanShopJevN").value || 0),
        });
        document.getElementById("shopScanResultBox").innerHTML = renderShopScanHtml(res);
        toast(res.summary);
        loadOverview();
      } else if (act === "creator-search") {
        toast("Đang tìm Creator TikTok...");
        const res = await api("/api/creators/search", "POST", { query: document.getElementById("creatorQuery").value.trim() });
        toast(res.summary);
        loadCreatorsAndScans();
      } else if (act === "set-bucket-filter") {
        CURRENT_BUCKET = actEl.dataset.bucket;
        loadProducts();
      } else if (act === "reload-products") {
        loadProducts();
      } else if (act === "toggle-select-pid") {
        const id = Number(actEl.dataset.id);
        if (actEl.checked) SELECTED_PIDS.add(id);
        else SELECTED_PIDS.delete(id);
      } else if (act === "open-add-product") {
        openModal("➕ Thêm Sản phẩm Tiềm năng vào Kho", `
          <div class="field"><label>Tên sản phẩm</label><input type="text" id="mProdTitle" /></div>
          <div class="grid3">
            <div class="field"><label>Sàn</label><select id="mProdPlat"><option value="shopee">Shopee</option><option value="tiktok_shop">TikTok Shop</option></select></div>
            <div class="field"><label>Giá bán lẻ (VNĐ)</label><input type="number" id="mProdPrice" value="199000" /></div>
            <div class="field"><label>Giá vốn dự kiến (VNĐ)</label><input type="number" id="mProdCost" value="68000" /></div>
          </div>
          <div class="grid2">
            <div class="field"><label>Tổng lượt bán hiện tại</label><input type="number" id="mProdSold" value="150" /></div>
            <div class="field"><label>URL sản phẩm</label><input type="text" id="mProdUrl" /></div>
          </div>
          <button class="btn btn-pri" data-action="submit-add-product">Lưu vào Kho SP</button>
        `);
      } else if (act === "submit-add-product") {
        await api("/api/products", "POST", {
          title: document.getElementById("mProdTitle").value,
          platform: document.getElementById("mProdPlat").value,
          price_vnd: Number(document.getElementById("mProdPrice").value || 0),
          cost_vnd: Number(document.getElementById("mProdCost").value || 0),
          sold_count: Number(document.getElementById("mProdSold").value || 0),
          url: document.getElementById("mProdUrl").value,
        });
        closeModal();
        toast("Đã thêm sản phẩm vào Kho!");
        loadProducts();
      } else if (act === "compare-selected") {
        const ids = [...SELECTED_PIDS];
        const res = await api("/api/products/compare", "POST", { ids });
        openModal("⚖️ So sánh Sản phẩm Bán hàng", `
          <table class="tbl">
            <thead><tr><th>Sản phẩm</th><th>Sàn</th><th>Giá bán</th><th>Giá vốn</th><th>Lãi ròng/đơn</th><th>Đã bán</th><th>Điểm Jev</th></tr></thead>
            <tbody>${(res.items || []).map((p) => `
              <tr>
                <td><strong>${esc(p.title)}</strong></td>
                <td>${esc(p.platform)}</td>
                <td>${vnd(p.price_vnd)}</td>
                <td>${vnd(p.cost_vnd)}</td>
                <td>${vnd((p.economics || {}).net_profit_per_order_vnd)} (${(p.economics || {}).net_margin_pct || 0}%)</td>
                <td>${p.sold_count}</td>
                <td>${p.jev_score ?? "—"}</td>
              </tr>`).join("")}
            </tbody>
          </table>`);
      } else if (act === "prod-score-jev") {
        toast("Đang chấm 6 trụ cột Seller bằng Jev AI...");
        const res = await api(`/api/products/${actEl.dataset.id}/score-jev`, "POST", {});
        toast(res.summary);
        loadProducts();
      } else if (act === "prod-find-cn") {
        document.getElementById("srcQuery").value = actEl.dataset.title;
        document.getElementById("srcLinkPid").value = actEl.dataset.id;
        showTab("sourcing", "/nguon-hang-tq");
      } else if (act === "prod-watch") {
        await api("/api/watches", "POST", {
          watch_type: "product",
          platform: actEl.dataset.plat === "tiktok_shop" ? "tiktok_shop" : "shopee",
          target_key: actEl.dataset.url || actEl.dataset.title,
          target_url: actEl.dataset.url || "",
          title: actEl.dataset.title,
          linked_product_id: Number(actEl.dataset.id),
          run_immediately: true,
        });
        toast("Đã bật theo dõi biến động giá & lượt bán sản phẩm!");
      } else if (act === "prod-dossier") {
        const d = await api(`/api/products/${actEl.dataset.id}`);
        const p = d.product;
        const ec = p.economics || {};
        openModal(`📊 Dossier Sản phẩm #${p.id}: ${p.title}`, `
          <div class="kpi-grid">
            <div class="kpi"><div class="lbl">Giá bán lẻ</div><div class="val">${vnd(p.price_vnd)}</div></div>
            <div class="kpi"><div class="lbl">Giá vốn về kho</div><div class="val gold">${vnd(p.cost_vnd)}</div></div>
            <div class="kpi"><div class="lbl">Lãi ròng/đơn (${ec.net_margin_pct || 0}%)</div><div class="val green">${vnd(ec.net_profit_per_order_vnd)}</div></div>
            <div class="kpi"><div class="lbl">ROAS Ads Hoà vốn</div><div class="val">${ec.breakeven_ads_roas || "—"}x</div></div>
          </div>
          <div class="grid3">
            <div class="field"><label>Cập nhật Giá bán (VNĐ)</label><input type="number" id="dosPrice" value="${p.price_vnd}" /></div>
            <div class="field"><label>Cập nhật Giá vốn (VNĐ)</label><input type="number" id="dosCost" value="${p.cost_vnd}" /></div>
            <div class="field"><label>Đổi Nhóm Kho</label><select id="dosBucket">${Object.entries(BUCKETS_MAP).map(([k, l]) => `<option value="${k}" ${p.bucket === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></div>
          </div>
          <button class="btn btn-pri" data-action="dos-save" data-id="${p.id}">💾 Cập nhật Giá vốn &amp; Phân loại</button>
          <h4 style="margin:14px 0 6px">Lịch sử Biến động Giá &amp; Lượt bán (${(d.metric_history || []).length} mốc)</h4>
          <table class="tbl"><thead><tr><th>Thời điểm</th><th>Nguồn</th><th>Giá bán</th><th>Tổng đã bán</th><th>Doanh số</th></tr></thead>
          <tbody>${(d.metric_history || []).map((h) => `<tr><td>${esc(h.recorded_at)}</td><td>${esc(h.source)}</td><td>${vnd(h.price_vnd)}</td><td>${h.sold_count}</td><td>${vnd(h.gmv_vnd)}</td></tr>`).join("")}</tbody></table>
        `);
      } else if (act === "dos-save") {
        await api(`/api/products/${actEl.dataset.id}`, "PATCH", {
          price_vnd: Number(document.getElementById("dosPrice").value || 0),
          cost_vnd: Number(document.getElementById("dosCost").value || 0),
          bucket: document.getElementById("dosBucket").value,
        });
        closeModal();
        toast("Đã cập nhật sản phẩm!");
        loadProducts();
      } else if (act === "sourcing-search") {
        toast("Đang tìm nguồn hàng Trung Quốc...");
        const res = await api("/api/sourcing/search", "POST", {
          query: document.getElementById("srcQuery").value.trim(),
          platform: document.getElementById("srcPlatform").value,
          weight_kg: Number(document.getElementById("srcWeight").value || 0.4),
          linked_product_id: document.getElementById("srcLinkPid").value ? Number(document.getElementById("srcLinkPid").value) : null,
        });
        toast(`${res.summary} (Từ khoá TQ: ${res.translated_cn_query})`);
        loadSourcing();
        loadOverview();
      } else if (act === "sourcing-calc") {
        const res = await api("/api/sourcing/calc", "POST", {
          price_cny: Number(document.getElementById("calcCny").value || 0),
          domestic_cn_ship_cny: Number(document.getElementById("calcDomCny").value || 0),
          weight_kg: Number(document.getElementById("calcWeight").value || 0.4),
          sell_price_vnd: Number(document.getElementById("calcSellVnd").value || 0),
          sell_platform: document.getElementById("calcPlat").value,
        });
        const lc = res.landed;
        const se = res.seller_economics;
        document.getElementById("sourcingCalcBox").innerHTML = `
          <div style="background:#0a1222;padding:10px;border-radius:8px;font-size:13px">
            • Giá vốn về kho VN: <strong style="color:#fcd34d">${vnd(lc.landed_cost_vnd)}</strong> (Tiền hàng: ${vnd(lc.goods_base_vnd)} + Cước cân: ${vnd(lc.intl_shipping_vnd)} + Mua hộ: ${vnd(lc.agent_fee_vnd)})<br/>
            • Bán lẻ <strong>${vnd(se.sell_price_vnd)}</strong> → Phí sàn: ${vnd(se.platform_fee_vnd)} → <strong>Lãi ròng/đơn: <span style="color:#6ee7b7">${vnd(se.net_profit_per_order_vnd)} (${se.net_margin_pct}%)</span></strong> · ROAS hoà vốn: <strong>${se.breakeven_ads_roas}x</strong>
          </div>`;
      } else if (act === "sourcing-to-vault") {
        const res = await api(`/api/sourcing/${actEl.dataset.id}/link`, "POST", { create_new_in_vault: true });
        toast(res.summary);
        loadSourcing();
        loadOverview();
      } else if (act === "shop-save") {
        const res = await api("/api/shops", "POST", {
          role: document.getElementById("shRole").value,
          platform: document.getElementById("shPlatform").value,
          platform_fee_pct: Number(document.getElementById("shFee").value || 12.5),
          shop_name: document.getElementById("shName").value.trim(),
          shop_url: document.getElementById("shUrl").value.trim(),
        });
        toast(res.summary);
        loadShops();
        loadOverview();
      } else if (act === "shop-watch-from-vault") {
        await api("/api/watches", "POST", {
          watch_type: "shop",
          platform: actEl.dataset.plat === "tiktok_shop" ? "tiktok_shop" : "shopee",
          target_key: actEl.dataset.url,
          target_url: actEl.dataset.url,
          title: `Shop: ${actEl.dataset.name}`,
          run_immediately: true,
        });
        toast("Đã thêm Shop vào danh sách theo dõi sản phẩm mới!");
        showTab("watches", "/theo-doi");
      } else if (act === "shop-delete") {
        await api(`/api/shops/${actEl.dataset.id}`, "DELETE");
        loadShops();
      } else if (act === "spy-product") {
        toast("Đang soi link sản phẩm...");
        const res = await api("/api/spy/product", "POST", { url: document.getElementById("spyProdUrl").value.trim() });
        document.getElementById("spyProdBox").innerHTML = `<pre class="codebox">${esc(JSON.stringify(res, null, 2))}</pre>`;
        toast(res.summary);
      } else if (act === "spy-fanpage") {
        toast("Đang quét Fanpage & Meta Ad Library...");
        const res = await api("/api/spy/fanpage", "POST", { fanpage_query: document.getElementById("spyFanpageQuery").value.trim() });
        document.getElementById("spyFanpageBox").innerHTML = `<pre class="codebox">${esc(JSON.stringify(res, null, 2))}</pre>`;
        toast(res.summary);
      } else if (act === "video-eval") {
        toast("Đang trích xuất khung hình & chấm điểm Video Jev AI...");
        const res = await api("/api/videos/evaluate", "POST", {
          video_url: document.getElementById("vidUrl").value.trim(),
          caption: document.getElementById("vidCaption").value.trim(),
        });
        document.getElementById("videoEvalResultBox").innerHTML = `<pre class="codebox">${esc(JSON.stringify(res.review, null, 2))}</pre>`;
        toast(res.summary);
        loadVideoWatchlist();
      } else if (act === "video-toggle-star") {
        await api(`/api/videos/watchlist/${actEl.dataset.key}`, "PATCH", { is_important: actEl.dataset.imp === "1" });
        loadVideoWatchlist();
      } else if (act === "video-clone") {
        toast("Đang phân đoạn <=15s & tạo bộ Prompt Clone Video...");
        const res = await api("/api/video-cloner/clone", "POST", {
          source_url: document.getElementById("vcUrl").value.trim(),
          product_name: document.getElementById("vcProdName").value.trim(),
          clone_mode: document.getElementById("vcMode").value,
        });
        toast(res.summary);
        loadVideoClones();
      } else if (act === "campaign-create") {
        const res = await api("/api/campaigns", "POST", {
          name: document.getElementById("cmpName").value.trim(),
          industry: document.getElementById("cmpIndustry").value || "gia_dung",
          target_revenue_vnd: Number(document.getElementById("cmpTargetRev").value || 0),
        });
        toast(res.summary);
        loadCampaigns();
      } else if (act === "cmp-attach-prod") {
        const cid = actEl.dataset.id;
        const pid = Number(document.getElementById(`cmpAddProd_${cid}`).value || 0);
        const stg = document.getElementById(`cmpAddStage_${cid}`).value;
        if (pid) {
          await api(`/api/campaigns/${cid}/product-stage`, "POST", { product_id: pid, stage: stg });
          toast("Đã cập nhật giai đoạn sản phẩm trong Chiến dịch!");
          loadCampaigns();
        }
      } else if (act === "cmp-toggle-task") {
        await api(`/api/campaigns/${actEl.dataset.cid}/tasks/${actEl.dataset.tid}`, "POST", {});
        loadCampaigns();
      } else if (act === "cmp-send-brief") {
        await api(`/api/campaigns/${actEl.dataset.id}/send-brief`, "POST", {});
        toast("Đã gửi Báo cáo Chiến dịch qua Telegram!");
      } else if (act === "sales-import-csv") {
        const res = await api("/api/sales/import-csv", "POST", {
          platform: document.getElementById("csvPlat").value,
          csv_text: document.getElementById("csvText").value,
        });
        toast(res.summary);
        loadAnalytics();
        loadOverview();
      } else if (act === "sales-add-expense") {
        const res = await api("/api/sales/expenses", "POST", {
          expense_type: document.getElementById("expType").value,
          amount_vnd: Number(document.getElementById("expAmount").value || 0),
          note: document.getElementById("expNote").value,
        });
        toast(res.summary);
        loadAnalytics();
      } else if (act === "chat-send") {
        const inp = document.getElementById("chatInput");
        if (!inp.value.trim()) return;
        await api("/api/chat/send", "POST", { message: inp.value.trim() });
        inp.value = "";
        loadChatAndPins();
      } else if (act === "pin-add") {
        await api("/api/pins", "POST", { title: document.getElementById("pinTitle").value, url: document.getElementById("pinUrl").value });
        document.getElementById("pinTitle").value = "";
        document.getElementById("pinUrl").value = "";
        loadChatAndPins();
      } else if (act === "pin-del") {
        await api(`/api/pins/${actEl.dataset.id}`, "DELETE");
        loadChatAndPins();
      } else if (act === "open-browser") {
        const res = await api("/api/connections/browser/open", "POST", { portal_key: actEl.dataset.portal });
        toast(`Đã mở trình duyệt độc lập: ${res.target_url}`);
        loadSettings();
      } else if (act === "tg-check") {
        const res = await api("/api/providers/telegram/check", "POST", { telegram_token: document.getElementById("setTgToken").value });
        toast(`Kết nối OK: @${res.bot.username}`);
        loadSettings();
      } else if (act === "tg-test") {
        await api("/api/providers/telegram/test", "POST", {});
        toast("Đã gửi tin nhắn Test vào Telegram của bạn!");
        loadSettings();
      } else if (act === "apify-add") {
        await api("/api/providers/apify/keys", "POST", {
          label: document.getElementById("newApifyLabel").value,
          token: document.getElementById("newApifyToken").value,
          make_primary: true,
        });
        document.getElementById("newApifyToken").value = "";
        toast("Đã thêm Apify Key vào Keychain!");
        loadSettings();
      } else if (act === "apify-promote") {
        await api(`/api/providers/apify/keys/${actEl.dataset.id}/promote`, "POST", {});
        loadSettings();
      } else if (act === "apify-del") {
        await api(`/api/providers/apify/keys/${actEl.dataset.id}`, "DELETE");
        loadSettings();
      } else if (act === "apify-check") {
        const res = await api("/api/providers/apify/check", "POST", {});
        toast(`Apify Key khả dụng: ${res.usable_keys}/${(res.keys || []).length}`);
      } else if (act === "treg-check") {
        await api("/api/providers/treg/check", "POST", { treg_key: document.getElementById("setTregKey").value });
        toast("Treg.to API hoạt động tốt!");
      } else if (act === "jev-check") {
        const res = await api("/api/providers/jev/check", "POST", { typesafe_key: document.getElementById("setJevKey").value });
        toast(`TypeSafe Jev (${res.model}) hoạt động tốt!`);
      } else if (act === "settings-save") {
        await api("/api/settings", "POST", {
          providers: {
            treg_key: document.getElementById("setTregKey").value,
            typesafe_key: document.getElementById("setJevKey").value,
          },
          notify: {
            telegram_token: document.getElementById("setTgToken").value,
            telegram_chat_id: document.getElementById("setTgChatId").value,
            telegram_allowed_user_ids: document.getElementById("setTgChatId").value,
          },
          sourcing: {
            cny_to_vnd_rate: Number(document.getElementById("setCnyRate").value || 3650),
            cn_shipping_per_kg_vnd: Number(document.getElementById("setShipKg").value || 28000),
            packaging_cost_vnd: Number(document.getElementById("setPackVnd").value || 3500),
            shopee_fee_pct: Number(document.getElementById("setShopeeFee").value || 12.5),
            tiktok_shop_fee_pct: Number(document.getElementById("setTiktokFee").value || 11.5),
            default_return_pct: Number(document.getElementById("setReturnPct").value || 6.0),
          },
        });
        toast("Đã lưu toàn bộ cấu hình vào Keychain & SQLite!");
        loadSettings();
      }
    } catch (err) {
      toast(err.message || "Có lỗi xảy ra", true);
    }
  });

  function initRoute() {
    const path = window.location.pathname;
    const tab = ROUTE_TO_TAB[path] || (path.startsWith("/kho") ? "results" : "hunt");
    showTab(tab, null);
  }

  window.addEventListener("popstate", initRoute);
  window.addEventListener("DOMContentLoaded", initRoute);
})();
