/* Global Shop Dianshang v1.0.2 — Expanded Kho Sidebar, Full Vault Visibility & Detailed Job History */
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

  const KHO_BUCKETS_META = {
    all: { ico: "🗂", name: "Tất cả SP" },
    cho_danh_gia: { ico: "📝", name: "Chờ đánh giá" },
    moi_noi: { ico: "🆕", name: "Mới nổi · Ít cạnh tranh" },
    viral: { ico: "🔥", name: "Đang viral / Bán chạy" },
    ben_vung: { ico: "🌱", name: "Bán bền vững" },
    da_co_nguon_tq: { ico: "🇨🇳", name: "Đã có nguồn nhập TQ" },
    dang_nhap_ban: { ico: "🚀", name: "Đang nhập / Test bán" },
    chua_cham: { ico: "⏳", name: "Chưa chấm Jev" },
    da_loai: { ico: "⛔", name: "Đã loại" },
  };

  const INDUSTRY_META = {
    lam_vuon: { ico: "🌱", name: "Làm vườn & Cây cảnh" },
    gia_dung: { ico: "🏠", name: "Gia dụng & Tiện ích" },
    nha_cua: { ico: "🛋", name: "Nhà cửa & Đời sống" },
    lam_dep: { ico: "💄", name: "Làm đẹp & Mỹ phẩm" },
    suc_khoe: { ico: "💊", name: "Sức khoẻ & Massage" },
    thoi_trang: { ico: "👗", name: "Thời trang & Phụ kiện" },
    cong_nghe: { ico: "📱", name: "Công nghệ & Điện tử" },
    me_be: { ico: "🍼", name: "Mẹ & Bé" },
    thu_cung: { ico: "🐾", name: "Thú cưng" },
    do_an: { ico: "🍜", name: "Thực phẩm & Ăn vặt" },
    the_thao: { ico: "🏃", name: "Thể thao & Dã ngoại" },
    oto_xemay: { ico: "🚗", name: "Ô tô & Xe máy" },
    khac: { ico: "📦", name: "Ngành khác" },
  };

  const SUB_FILTERS = {
    all: "Tất cả",
    jev7: "🤖 Điểm Jev ≥ 7.0",
    has_sold: "📦 Đã có lượt bán > 0",
    has_cost: "🇨🇳 Đã có giá vốn TQ",
    quan_tam: "⭐ Quan tâm",
    nhap_test: "🧪 Nhập test",
    dang_ban: "✅ Đang bán",
  };

  const PILLAR_LABELS = {
    suc_cau: "Sức cầu",
    bien_lai: "Biên lãi",
    de_nhap_tq: "Dễ nhập TQ",
    canh_tranh: "Cạnh tranh",
    khac_biet: "Khác biệt",
    de_lam_video: "Video/Ads",
  };

  let CURRENT_TAB = "hunt";
  let CURRENT_BUCKET = "all";
  let CURRENT_SUB = "all";
  let SELECTED_PIDS = new Set();
  let VISIBLE_PRODUCTS = [];
  let BUCKET_COUNTS = {};
  let INDUSTRY_COUNTS = {};
  let ALL_SHOPS = [];
  let ALL_CAMPAIGNS = [];
  let LAST_HIST_DETAIL = null;

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

  function fmtDuration(ms) {
    const n = Number(ms || 0);
    if (n < 1000) return `${n}ms`;
    return `${(n / 1000).toFixed(1)}s`;
  }

  function fmtTime(iso) {
    if (!iso) return "—";
    return String(iso).replace("T", " ").replace("Z", "");
  }

  function statusBadgeHtml(st) {
    const cls = st === "completed" ? "green" : st === "failed" ? "red" : st === "running" ? "gold" : "blue";
    const lbl = { completed: "✅ Hoàn thành", running: "⏳ Đang chạy", failed: "❌ Lỗi", cancelled: "🛑 Đã dừng", interrupted: "⚠️ Gián đoạn" }[st] || st;
    return `<span class="badge ${cls}">${esc(lbl)}</span>`;
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

  // --- SIDEBAR KHO & INDUSTRY EXPANSION (LIKE AFFILIATE-PENG) ----------------
  function renderKhoAndIndustrySidebar() {
    const navKho = document.getElementById("navKho");
    if (navKho) {
      navKho.innerHTML = Object.entries(KHO_BUCKETS_META)
        .map(([k, info]) => {
          const cnt = BUCKET_COUNTS[k] || 0;
          const isAct = CURRENT_TAB === "results" && CURRENT_BUCKET === k ? " active" : "";
          return `<button class="sub-nav-btn${isAct}" data-action="sidebar-bucket" data-bucket="${k}">
            <span>${info.ico} ${esc(info.name)}</span>
            <em class="ncount">${cnt}</em>
          </button>`;
        })
        .join("");
    }

    const navInd = document.getElementById("navIndustries");
    const curInd = document.getElementById("filterIndustry")?.value || "";
    if (navInd) {
      const nonEmpty = Object.entries(INDUSTRY_META).filter(([k]) => (INDUSTRY_COUNTS[k] || 0) > 0 || curInd === k);
      navInd.innerHTML = nonEmpty.length
        ? nonEmpty
            .map(([k, info]) => {
              const cnt = INDUSTRY_COUNTS[k] || 0;
              const isAct = CURRENT_TAB === "results" && curInd === k ? " active" : "";
              return `<button class="sub-nav-btn${isAct}" data-action="sidebar-industry" data-ind="${k}">
                <span>${info.ico} ${esc(info.name)}</span>
                <em class="ncount">${cnt}</em>
              </button>`;
            })
            .join("")
        : `<div style="padding:4px 14px;font-size:11.5px;color:var(--muted)">Chưa có SP theo ngành</div>`;
    }
  }

  async function syncSidebarCountsAndRefs() {
    try {
      const [ov, prodMeta, shData, cmpData] = await Promise.all([
        api("/api/overview"),
        api("/api/products?bucket=all&limit=1"),
        api("/api/shops"),
        api("/api/campaigns"),
      ]);
      BUCKET_COUNTS = prodMeta.bucket_counts || {};
      INDUSTRY_COUNTS = prodMeta.industry_counts || {};
      ALL_SHOPS = shData.shops || [];
      ALL_CAMPAIGNS = cmpData.campaigns || [];

      document.getElementById("kpiVault").textContent = ov.vault_products;
      document.getElementById("topVaultCnt").textContent = ov.vault_products;
      document.getElementById("kpiWatches").textContent = ov.watches_count;
      document.getElementById("kpiShopsSrc").textContent = `${ov.shops_count} shop / ${ov.sourcing_count} mẫu TQ`;
      const sp = ov.sales || {};
      document.getElementById("kpiSalesProfit").textContent = `${vnd(sp.gross_gmv_vnd)} / Lãi ${vnd(sp.net_profit_vnd)}`;
      document.getElementById("cntWatches").textContent = ov.watches_count;
      document.getElementById("cntShops").textContent = ov.shops_count;
      document.getElementById("cntSourcing").textContent = ov.sourcing_count;
      if (ov.recent_logs?.length) {
        document.getElementById("cntHistoryLogs").textContent = ov.recent_logs[0].seq_no || ov.recent_logs.length;
      }

      populateKhoSelectControls();
      renderKhoAndIndustrySidebar();
    } catch (_) {}
  }

  function populateKhoSelectControls() {
    const fInd = document.getElementById("filterIndustry");
    if (fInd) {
      const cur = fInd.value;
      const tot = BUCKET_COUNTS.all || 0;
      fInd.innerHTML =
        `<option value="">🏷️ Tất cả Ngành hàng (${tot})</option>` +
        Object.entries(INDUSTRY_META)
          .map(([k, inf]) => `<option value="${k}">${inf.ico} ${esc(inf.name)} (${INDUSTRY_COUNTS[k] || 0})</option>`)
          .join("");
      fInd.value = cur;
    }

    const bInd = document.getElementById("bulkIndustrySel");
    if (bInd && !bInd.options.length) {
      bInd.innerHTML = Object.entries(INDUSTRY_META)
        .map(([k, inf]) => `<option value="${k}">${inf.ico} ${esc(inf.name)}</option>`)
        .join("");
    }

    const bBuck = document.getElementById("bulkBucketSel");
    if (bBuck && !bBuck.options.length) {
      bBuck.innerHTML = Object.entries(KHO_BUCKETS_META)
        .filter(([k]) => k !== "all" && k !== "chua_cham")
        .map(([k, inf]) => `<option value="${k}">${inf.ico} ${esc(inf.name)}</option>`)
        .join("");
    }

    const cmpInd = document.getElementById("cmpIndustry");
    if (cmpInd && !cmpInd.options.length) {
      cmpInd.innerHTML = Object.entries(INDUSTRY_META)
        .map(([k, inf]) => `<option value="${k}">${inf.ico} ${esc(inf.name)}</option>`)
        .join("");
    }

    const ownShops = ALL_SHOPS.filter((s) => s.role === "own_shop");
    const fShop = document.getElementById("filterShop");
    if (fShop) {
      const cur = fShop.value;
      fShop.innerHTML =
        `<option value="">🏬 Tất cả Shop vận hành</option><option value="__unassigned__">⚠️ Chưa gắn Shop</option>` +
        ownShops.map((s) => `<option value="${esc(s.shop_id)}">🏬 ${esc(s.shop_name)} (${esc(s.platform)})</option>`).join("");
      fShop.value = cur;
    }
    const bShop = document.getElementById("bulkShopSel");
    if (bShop) {
      bShop.innerHTML =
        `<option value="">— Gỡ khỏi Shop —</option>` +
        ownShops.map((s) => `<option value="${esc(s.shop_id)}">🏬 ${esc(s.shop_name)}</option>`).join("");
    }

    const fCmp = document.getElementById("filterCampaign");
    if (fCmp) {
      const cur = fCmp.value;
      fCmp.innerHTML =
        `<option value="">🚀 Tất cả Chiến dịch</option>` +
        ALL_CAMPAIGNS.map((c) => `<option value="${esc(c.campaign_id)}">🚀 ${esc(c.name)}</option>`).join("");
      fCmp.value = cur;
    }
  }

  function showTab(tab, pushUrl = null) {
    CURRENT_TAB = tab;
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    const target = document.getElementById(`view-${tab}`);
    if (target) target.classList.add("active");

    document.querySelectorAll(".nav-btn").forEach((b) => {
      b.classList.toggle("active", b.dataset.tab === tab);
    });
    renderKhoAndIndustrySidebar();
    document.getElementById("sidebar")?.classList.remove("open");

    if (pushUrl) {
      window.history.pushState({ tab, bucket: CURRENT_BUCKET }, "", pushUrl);
    }
    refreshTab(tab);
  }

  async function refreshTab(tab) {
    await syncSidebarCountsAndRefs();
    if (tab === "hunt") await loadHuntRecentRuns();
    else if (tab === "results") await loadProducts();
    else if (tab === "keywords") await loadKeywordHistory();
    else if (tab === "watches") await loadWatches();
    else if (tab === "shopspy") await loadCreatorsAndScans();
    else if (tab === "sourcing") await loadSourcing();
    else if (tab === "shops") await loadShops();
    else if (tab === "videojev") await loadVideoWatchlist();
    else if (tab === "videoclone") await loadVideoClones();
    else if (tab === "campaigns") await loadCampaigns();
    else if (tab === "analytics") await loadAnalytics();
    else if (tab === "history") await loadHistoryAndJobs();
    else if (tab === "chat") await loadChatAndPins();
    else if (tab === "settings") await loadSettings();
  }

  // --- RESOLVED EXECUTION RESULTS RENDERER (SHARED BY HUNT & HISTORY) --------
  function renderResolvedResultsHtml(rr) {
    if (!rr) return "";
    const kpis = rr.kpis || [];
    const prods = rr.products || [];
    const cnItems = rr.china_items || [];
    const creators = rr.creators || [];
    const wdiff = rr.watch_diff;

    const kpiHtml = kpis.length
      ? `<div class="row" style="margin-bottom:10px">${kpis.map((k) => `<span class="badge blue">${esc(k.label)}: <strong>${esc(k.value)}</strong></span>`).join("")}</div>`
      : "";

    const prodsHtml = prods.length
      ? `<div style="margin-top:8px">
          <div style="font-weight:600;margin-bottom:6px;color:#6ee7b7">📦 Danh sách Sản phẩm đã gọi về trong tác vụ này (${prods.length} SP):</div>
          <div style="max-height:320px;overflow:auto;border:1px solid var(--border);border-radius:8px">
            <table class="tbl">
              <thead><tr><th>#</th><th>Sản phẩm</th><th>Sàn</th><th>Giá bán</th><th>Đã bán</th><th>Điểm Jev</th><th>Nhóm Kho hiện tại</th><th>Thao tác</th></tr></thead>
              <tbody>
                ${prods.map((p, idx) => `
                  <tr>
                    <td>${p.id ? `#${p.id}` : idx + 1}</td>
                    <td>
                      <div class="row" style="flex-wrap:nowrap">
                        ${p.image_url ? `<img src="${esc(p.image_url)}" style="width:36px;height:36px;border-radius:6px;object-fit:cover" alt="" />` : ""}
                        <div>
                          <a href="${esc(p.url || "#")}" target="_blank" style="color:#93c5fd;font-weight:600">${esc(p.title)}</a>
                          ${p.native_product_id ? `<div style="font-size:11px;color:var(--muted)">ID: ${esc(p.native_product_id)}</div>` : ""}
                        </div>
                      </div>
                    </td>
                    <td><span class="badge">${esc(p.platform || "")}</span></td>
                    <td>${p.price_vnd > 0 ? vnd(p.price_vnd) : '<span style="color:var(--muted)">Chưa lấy</span>'}</td>
                    <td><strong>${Number(p.sold_count || 0).toLocaleString("vi-VN")}</strong></td>
                    <td>${p.jev_score != null ? `<span class="badge gold">${p.jev_score}/10</span>` : "—"}</td>
                    <td><span class="badge green">${esc(p.bucket_label || "Chờ đánh giá")}</span></td>
                    <td>
                      ${p.id ? `<button class="btn btn-sm btn-pri" data-action="prod-dossier" data-id="${p.id}">📊 Mở &amp; Phân loại</button>` : ""}
                    </td>
                  </tr>`).join("")}
              </tbody>
            </table>
          </div>
        </div>`
      : "";

    const cnHtml = cnItems.length
      ? `<div style="margin-top:8px">
          <div style="font-weight:600;margin-bottom:6px;color:#fcd34d">🇨🇳 Báo giá Nguồn hàng Trung Quốc (${cnItems.length} mẫu):</div>
          <table class="tbl">
            <thead><tr><th>Sàn</th><th>Tên mẫu</th><th>Giá CNY</th><th>Giá vốn về kho VN</th></tr></thead>
            <tbody>${cnItems.map((c) => `<tr><td>${esc(c.platform)}</td><td><a href="${esc(c.item_url || "#")}" target="_blank" style="color:#93c5fd">${esc(c.title)}</a></td><td>¥${c.price_cny}</td><td><strong>${vnd(c.landed_cost_vnd)}</strong></td></tr>`).join("")}</tbody>
          </table>
        </div>`
      : "";

    const crHtml = creators.length
      ? `<div style="margin-top:8px">
          <div style="font-weight:600;margin-bottom:6px">🎥 Creator thu thập (${creators.length} kênh):</div>
          <table class="tbl"><thead><tr><th>@Handle</th><th>Followers</th><th>View TB</th></tr></thead>
          <tbody>${creators.map((c) => `<tr><td>@${esc(c.handle)}</td><td>${c.followers}</td><td>${c.avg_views}</td></tr>`).join("")}</tbody></table>
        </div>`
      : "";

    const diffHtml = wdiff
      ? `<div style="margin-top:8px;padding:8px 10px;background:#081221;border-radius:8px">
          <strong>🔭 Kết quả So sánh (Diff):</strong> Tổng SP: <strong>${wdiff.total_count}</strong> ·
          <span class="badge green">+${wdiff.new_items_count || 0} SP mới</span> ·
          <span class="badge gold">${wdiff.rising_items_count || 0} SP tăng lượt bán</span>
        </div>`
      : "";

    if (!kpiHtml && !prodsHtml && !cnHtml && !crHtml && !diffHtml) return "";
    return `
      <div style="padding:12px;background:#081120;border:1px solid rgba(56,189,248,0.4);border-radius:10px;margin-bottom:12px">
        <div style="font-weight:700;color:#7dd3fc;margin-bottom:6px">📊 Kết quả Thực thi Chi tiết: ${esc(rr.headline || "")}</div>
        ${kpiHtml}${prodsHtml}${cnHtml}${crHtml}${diffHtml}
      </div>`;
  }

  // --- PART 1.1: HUNT & RECENT HUNT RUNS -------------------------------------
  async function pollHuntLogs() {
    try {
      const st = await api("/api/hunt/status");
      const job = st.active_job;
      if (!job) return;
      const box = document.getElementById("huntLogsBox");
      const topSt = document.getElementById("topStatusBadge");
      if (box && job.logs) {
        box.textContent = `[${job.status.toUpperCase()}] ${job.title} (Chi phí: $${Number(job.actual_cost_usd || 0).toFixed(4)})\n` + job.logs.join("\n");
      }
      if (job.status === "running") {
        if (topSt) topSt.textContent = "⏳ Đang quét SP...";
        setTimeout(pollHuntLogs, 2000);
      } else {
        if (topSt) topSt.textContent = "🟢 Sẵn sàng";
        await syncSidebarCountsAndRefs();
        await loadHuntRecentRuns();
      }
    } catch (_) {}
  }

  async function loadHuntRecentRuns() {
    const box = document.getElementById("huntRecentRunsBox");
    if (!box) return;
    const data = await api("/api/history-logs?module=hunt");
    const rows = data.logs || [];
    box.innerHTML = rows.length
      ? `<table class="tbl">
          <thead><tr><th>Mã GS</th><th>Thời gian</th><th>Phiên săn đã chạy</th><th>Trạng thái</th><th>Chi phí</th><th>Kết quả</th><th>Chi tiết</th></tr></thead>
          <tbody>${rows.slice(0, 12).map((r) => `
            <tr>
              <td><strong style="color:#7dd3fc">${esc(r.gs_code)}</strong></td>
              <td>${fmtTime(r.created_at)}</td>
              <td><strong>${esc(r.title)}</strong></td>
              <td>${statusBadgeHtml(r.status)}</td>
              <td>$${Number(r.cost_usd || 0).toFixed(4)}</td>
              <td>${esc(r.summary)}</td>
              <td><button class="btn btn-sm btn-pri" data-action="hunt-open-run" data-id="${esc(r.log_id)}">🔍 Xem Log &amp; SP</button></td>
            </tr>`).join("")}
          </tbody>
        </table>`
      : `<div style="color:var(--muted)">Chưa có phiên săn nào được chạy.</div>`;
  }

  // --- PART 1.2: KEYWORD RESEARCH --------------------------------------------
  function renderKeywordResult(res) {
    const s = res.summary_stats || {};
    const jev = s.jev_evaluation;
    const html = `
      <div class="card">
        <div class="row" style="justify-content:space-between;margin-bottom:8px">
          <h3 style="margin:0">📊 Kết quả Từ khoá: "${esc(res.keyword)}" (${esc(res.platform)})</h3>
          <button class="btn btn-sm btn-pri" data-action="jump-kho-pending">📝 Sang Kho Phân loại (${(res.saved_product_ids || []).length} SP đã lưu)</button>
        </div>
        <div class="kpi-grid">
          <div class="kpi"><div class="lbl">Tổng lượng SP trên từ khoá</div><div class="val">${esc(s.total_products)}</div></div>
          <div class="kpi"><div class="lbl">Tổng lượt bán mẫu trang 1</div><div class="val green">${Number(s.total_sold_sample || 0).toLocaleString("vi-VN")}</div></div>
          <div class="kpi"><div class="lbl">Giá bán Trung bình / Trung vị</div><div class="val">${vnd(s.avg_price_vnd)} / ${vnd(s.median_price_vnd)}</div></div>
          <div class="kpi"><div class="lbl">Tỷ lệ Mall / Top 3 Shop chiếm</div><div class="val gold">${s.mall_share_pct}% / ${s.top3_shop_concentration_pct}%</div></div>
          <div class="kpi"><div class="lbl">Điểm Cơ hội Jev AI</div><div class="val green">${jev ? jev.opportunity_score_10 + " / 10" : "Chưa chấm"}</div></div>
        </div>
        <table class="tbl">
          <thead><tr><th>Tên sản phẩm</th><th>Shop</th><th>Giá bán</th><th>Đã bán</th><th>Doanh số ước tính</th></tr></thead>
          <tbody>
            ${(res.items || []).map((it) => `
              <tr>
                <td><a href="${esc(it.url)}" target="_blank" style="color:#93c5fd">${esc(it.title)}</a> ${it.is_mall ? '<span class="badge red">Mall</span>' : ""}</td>
                <td>${esc(it.shop_name)}</td>
                <td>${vnd(it.price_vnd)}</td>
                <td><strong>${Number(it.sold_count || 0).toLocaleString("vi-VN")}</strong></td>
                <td>${vnd(it.gmv_vnd)}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
    document.getElementById("kwResultBox").innerHTML = html;
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
              <td>${fmtTime(r.created_at)}</td>
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
              <td>${fmtTime(w.last_checked_at)}</td>
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
              <span style="font-size:12px;color:var(--muted)">${fmtTime(r.created_at)}</span>
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
      document.getElementById("shopScanResultBox").innerHTML = renderShopScanHtml(scans[0]);
    }
  }

  function renderShopScanHtml(scan) {
    return `
      <div style="background:#0a1222;padding:10px;border-radius:8px">
        <div class="row" style="justify-content:space-between">
          <strong>🏪 ${esc(scan.shop_name)} (${esc(scan.platform)}) — ${scan.total_products} SP · Đã bán: ${Number(scan.total_sold || 0).toLocaleString("vi-VN")}</strong>
          <button class="btn btn-sm btn-pri" data-action="jump-kho-pending">📝 Phân loại trong Kho SP</button>
        </div>
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

  // --- PART 2.1: EXPANDED KHO & CLASSIFICATION -------------------------------
  function updateBulkBar() {
    const bar = document.getElementById("bulkBar");
    if (!bar) return;
    const n = SELECTED_PIDS.size;
    document.getElementById("selCount").textContent = n;
    bar.style.display = n > 0 ? "block" : "none";
  }

  async function loadProducts() {
    const ind = document.getElementById("filterIndustry")?.value || "";
    const plat = document.getElementById("filterPlatform")?.value || "";
    const shopId = document.getElementById("filterShop")?.value || "";
    const cmpId = document.getElementById("filterCampaign")?.value || "";
    const sort = document.getElementById("filterSort")?.value || "updated";
    const q = document.getElementById("filterSearch")?.value || "";
    const soldMin = Number(document.getElementById("filterSoldMin")?.value || 0);

    const qs = new URLSearchParams({
      bucket: CURRENT_BUCKET,
      industry: ind,
      platform: plat,
      shop_id: shopId,
      campaign_id: cmpId,
      sort,
      q,
    });
    const data = await api(`/api/products?${qs}`);
    BUCKET_COUNTS = data.bucket_counts || {};
    INDUSTRY_COUNTS = data.industry_counts || {};
    populateKhoSelectControls();
    renderKhoAndIndustrySidebar();

    const bMeta = KHO_BUCKETS_META[CURRENT_BUCKET] || KHO_BUCKETS_META.all;
    const indTitle = ind && INDUSTRY_META[ind] ? ` · ${INDUSTRY_META[ind].ico} ${INDUSTRY_META[ind].name}` : "";
    document.getElementById("khoHeading").textContent = `${bMeta.ico} Kho SP: ${bMeta.name}${indTitle}`;

    const baseItems = data.products || [];

    // Render Sub-Filter Status Tabs
    document.getElementById("khoSubTabs").innerHTML = Object.entries(SUB_FILTERS)
      .map(([k, lbl]) => {
        const cnt = baseItems.filter((p) => matchSubFilter(p, k)).length;
        return `<button class="chip ${CURRENT_SUB === k ? "active" : ""}" data-action="set-sub-filter" data-sub="${k}">${esc(lbl)} (${cnt})</button>`;
      })
      .join("");

    // Render Industry Filter Chips
    const activeIndEntries = Object.entries(INDUSTRY_META).filter(([k]) => (INDUSTRY_COUNTS[k] || 0) > 0 || ind === k);
    document.getElementById("industryFilterChips").innerHTML =
      `<button class="chip ${!ind ? "active" : ""}" data-action="chip-industry" data-ind="">🗂 Tất cả ngành (${BUCKET_COUNTS.all || 0})</button>` +
      activeIndEntries
        .map(([k, inf]) => `<button class="chip ${ind === k ? "active" : ""}" data-action="chip-industry" data-ind="${k}">${inf.ico} ${esc(inf.name)} (${INDUSTRY_COUNTS[k] || 0})</button>`)
        .join("");

    let filtered = baseItems.filter((p) => matchSubFilter(p, CURRENT_SUB));
    if (soldMin > 0) {
      filtered = filtered.filter((p) => Number(p.sold_count || 0) >= soldMin);
    }
    VISIBLE_PRODUCTS = filtered;

    const ownShops = ALL_SHOPS.filter((s) => s.role === "own_shop");
    document.getElementById("productsGrid").innerHTML = filtered.length
      ? filtered.map((p) => renderProductCardHtml(p, ownShops)).join("")
      : `<div class="card" style="grid-column:1/-1;color:var(--muted)">
          Chưa có sản phẩm nào khớp bộ lọc hiện tại. Bấm <strong>"🗂 Tất cả SP (${BUCKET_COUNTS.all || 0})"</strong> ở cột trái hoặc chạy Săn SP / Tra cứu Từ khoá!
        </div>`;

    updateBulkBar();
  }

  function matchSubFilter(p, subKey) {
    if (subKey === "all") return true;
    if (subKey === "jev7") return p.jev_score != null && Number(p.jev_score) >= 7.0;
    if (subKey === "has_sold") return Number(p.sold_count || 0) > 0;
    if (subKey === "has_cost") return Number(p.cost_vnd || 0) > 0;
    return p.status === subKey;
  }

  function renderProductCardHtml(p, ownShops) {
    const ec = p.economics || {};
    const pillars = (p.jev_detail || {}).pillars || {};
    const cls = p.jev_score >= 7.2 ? "is-gold" : p.jev_score >= 6.2 ? "is-green" : "";

    const pillarsHtml = Object.keys(pillars).length
      ? `<div class="pillars">${Object.entries(PILLAR_LABELS)
          .map(([k, lbl]) => `<div>${esc(lbl)}<b>${pillars[k] ?? "–"}</b></div>`)
          .join("")}</div>`
      : "";

    return `
      <div class="pcard ${cls}">
        <div class="pcard-top">
          ${p.image_url ? `<img class="pcard-img" src="${esc(p.image_url)}" alt="" loading="lazy" />` : `<div class="pcard-img" style="display:flex;align-items:center;justify-content:center;font-size:26px">${p.industry_icon || "📦"}</div>`}
          <div style="flex:1;min-width:0">
            <div class="row" style="justify-content:space-between">
              <label style="font-size:12px;color:var(--muted);cursor:pointer">
                <input type="checkbox" data-action="toggle-select-pid" data-id="${p.id}" ${SELECTED_PIDS.has(p.id) ? "checked" : ""}/>
                #${p.id} · ${esc(p.platform.toUpperCase())}
              </label>
              <span class="badge ${p.jev_score >= 7 ? "gold" : p.jev_score != null ? "green" : ""}">${p.jev_score != null ? `🤖 Jev ${p.jev_score}/10` : "⏳ Chưa chấm Jev"}</span>
            </div>
            <div style="font-weight:600;margin:4px 0;line-height:1.38">
              <a href="${esc(p.url || "#")}" target="_blank" style="color:var(--txt);text-decoration:none">${esc(p.title)}</a>
            </div>
            <div class="row" style="gap:5px">
              <span class="badge blue">${esc(p.industry_icon)} ${esc(p.industry_label)}</span>
              <span class="badge green">${esc(p.bucket_icon)} ${esc(p.bucket_label)}</span>
              ${p.is_mall ? '<span class="badge red">Mall</span>' : ""}
            </div>
          </div>
        </div>

        <!-- 1-Click Quick Status Classification Row -->
        <div class="status-row">
          <button type="button" class="${p.status === "quan_tam" ? "on" : ""}" data-action="prod-set-status" data-id="${p.id}" data-st="${p.status === "quan_tam" ? "" : "quan_tam"}">⭐ Quan tâm</button>
          <button type="button" class="${p.status === "nhap_test" ? "on" : ""}" data-action="prod-set-status" data-id="${p.id}" data-st="${p.status === "nhap_test" ? "" : "nhap_test"}">🧪 Nhập test</button>
          <button type="button" class="${p.status === "dang_ban" ? "on" : ""}" data-action="prod-set-status" data-id="${p.id}" data-st="${p.status === "dang_ban" ? "" : "dang_ban"}">✅ Đang bán</button>
          <button type="button" class="${p.status === "bo_qua" ? "on-reject" : ""}" data-action="prod-set-status" data-id="${p.id}" data-st="${p.status === "bo_qua" ? "" : "bo_qua"}">⛔ Loại bỏ</button>
        </div>

        <div class="pstats">
          <div>🏷️ Giá bán<strong>${p.price_vnd > 0 ? vnd(p.price_vnd) : '<span style="color:#fcd34d">Chưa lấy</span>'}</strong></div>
          <div>🇨🇳 Giá vốn<strong>${p.cost_vnd > 0 ? vnd(p.cost_vnd) : "Chưa ghép"}</strong></div>
          <div>📦 Lượt bán<strong>${Number(p.sold_count || 0).toLocaleString("vi-VN")}</strong></div>
          <div>💰 Lãi/đơn<strong style="color:${(ec.net_profit_per_order_vnd || 0) > 0 ? "#6ee7b7" : "var(--muted)"}">${p.cost_vnd > 0 && p.price_vnd > 0 ? vnd(ec.net_profit_per_order_vnd) : "—"}</strong></div>
        </div>

        ${pillarsHtml}

        <div style="font-size:11.5px;color:var(--muted);display:flex;justify-content:space-between;flex-wrap:wrap;gap:4px">
          <span>Doanh số ước tính: <strong style="color:var(--txt)">${vnd(p.gmv_vnd)}</strong></span>
          <span>Nguồn: <code>${esc((p.sources || [])[0] || "manual")}</code></span>
        </div>

        <!-- Inline Instant Classification Dropdowns (Industry + Bucket + Own Shop) -->
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;background:#09111f;padding:6px;border-radius:8px;border:1px solid var(--border)">
          <select data-inline-pid="${p.id}" data-inline-field="industry" title="Đổi Ngành hàng" style="padding:4px 6px;font-size:11.8px">
            ${Object.entries(INDUSTRY_META).map(([k, inf]) => `<option value="${k}" ${p.industry === k ? "selected" : ""}>${inf.ico} ${esc(inf.name)}</option>`).join("")}
          </select>
          <select data-inline-pid="${p.id}" data-inline-field="bucket" title="Chuyển Nhóm Phân loại Kho" style="padding:4px 6px;font-size:11.8px">
            ${Object.entries(KHO_BUCKETS_META)
              .filter(([k]) => k !== "all" && k !== "chua_cham")
              .map(([k, inf]) => `<option value="${k}" ${p.bucket === k ? "selected" : ""}>${inf.ico} ${esc(inf.name)}</option>`)
              .join("")}
          </select>
          <select data-inline-pid="${p.id}" data-inline-field="assigned_shop_id" title="Gắn vào Shop vận hành" style="padding:4px 6px;font-size:11.8px">
            <option value="">🏬 Chưa gắn Shop của mình</option>
            ${ownShops.map((s) => `<option value="${esc(s.shop_id)}" ${p.assigned_shop_id === s.shop_id ? "selected" : ""}>🏬 ${esc(s.shop_name)}</option>`).join("")}
          </select>
          <select data-inline-pid="${p.id}" data-inline-field="assigned_campaign_id" title="Gắn vào Chiến dịch Ngành hàng" style="padding:4px 6px;font-size:11.8px">
            <option value="">🚀 Chưa gắn Chiến dịch</option>
            ${ALL_CAMPAIGNS.map((c) => `<option value="${esc(c.campaign_id)}" ${p.assigned_campaign_id === c.campaign_id ? "selected" : ""}>🚀 ${esc(c.name)}</option>`).join("")}
          </select>
        </div>

        <div class="row" style="gap:5px">
          <button class="btn btn-sm" data-action="prod-enrich" data-id="${p.id}" title="Lấy Giá bán, Lượt bán & Ảnh thực tế">🔄 Lấy Giá</button>
          <button class="btn btn-sm btn-pri" data-action="prod-score-jev" data-id="${p.id}">🤖 Chấm Jev</button>
          <button class="btn btn-sm btn-gold" data-action="prod-find-cn" data-id="${p.id}" data-title="${esc(p.title)}">🇨🇳 Nguồn TQ</button>
          <button class="btn btn-sm" data-action="prod-dossier" data-id="${p.id}">📊 Hồ sơ &amp; Lãi</button>
          <button class="btn btn-sm" data-action="prod-watch" data-id="${p.id}" data-plat="${esc(p.platform)}" data-url="${esc(p.url)}" data-title="${esc(p.title)}">🔭</button>
        </div>
      </div>`;
  }

  // --- PART 2.2 & 2.3: SOURCING & SHOPS --------------------------------------
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
              <td><button class="btn btn-sm btn-pri" data-action="sourcing-to-vault" data-id="${esc(it.sourcing_id)}">+ Đưa vào Kho SP</button></td>
            </tr>`).join("")}
          </tbody>
        </table>`
      : `<div style="color:var(--muted)">Chưa có báo giá nguồn hàng 1688 / Pinduoduo / Taobao.</div>`;
  }

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

  // --- PART 4.3: DETAILED ACTIVITY HISTORY (GS-XXXX) & JOBS ------------------
  async function loadHistoryAndJobs() {
    const mod = document.getElementById("histFilterMod")?.value || "all";
    const st = document.getElementById("histFilterStatus")?.value || "all";
    const q = document.getElementById("histSearchQ")?.value || "";
    const qs = new URLSearchParams({ module: mod, status: st, q });

    const [hData, jData] = await Promise.all([api(`/api/history-logs?${qs}`), api("/api/jobs")]);
    const k = hData.kpis || {};
    document.getElementById("histKpiStrip").innerHTML = `
      <div class="kpi"><div class="lbl">Tổng Công việc đã lưu</div><div class="val sky">${k.total || 0}</div></div>
      <div class="kpi"><div class="lbl">Hoàn thành</div><div class="val green">${k.completed || 0}</div></div>
      <div class="kpi"><div class="lbl">Đang chạy / Lỗi</div><div class="val gold">${k.running || 0} / ${k.failed || 0}</div></div>
      <div class="kpi"><div class="lbl">Tổng Chi phí API luỹ kế</div><div class="val">$${Number(k.total_cost_usd || 0).toFixed(4)}</div></div>
    `;

    const logs = hData.logs || [];
    document.getElementById("historyLogsBox").innerHTML = logs.length
      ? `<table class="tbl">
          <thead><tr><th>Mã GS</th><th>Phân hệ</th><th>Công việc / Job đã chạy</th><th>Trạng thái</th><th>Thời lượng &amp; Chi phí</th><th>Tóm tắt kết quả</th><th>Telegram</th><th>Chi tiết</th></tr></thead>
          <tbody>${logs.map((l) => `
            <tr>
              <td><strong style="color:#7dd3fc">${esc(l.gs_code)}</strong></td>
              <td><span class="badge blue">${esc(l.module_label || l.module)}</span></td>
              <td><strong>${esc(l.title)}</strong><div style="font-size:11px;color:var(--muted)">${fmtTime(l.created_at)}</div></td>
              <td>${statusBadgeHtml(l.status)}</td>
              <td>${fmtDuration(l.duration_ms)} · $${Number(l.cost_usd || 0).toFixed(4)}</td>
              <td>${esc(l.summary)}</td>
              <td>${l.telegram_notified_at ? "✅ Đã báo" : "—"}</td>
              <td>
                <button class="btn btn-sm btn-pri" data-action="hist-open-detail" data-id="${esc(l.log_id)}">🔍 Xem Chi tiết</button>
              </td>
            </tr>`).join("")}
          </tbody>
        </table>`
      : `<div style="color:var(--muted)">Không có nhật ký công việc nào khớp bộ lọc.</div>`;

    const jobs = jData.jobs || [];
    document.getElementById("jobsTableBox").innerHTML = jobs.length
      ? `<table class="tbl">
          <thead><tr><th>Mã Job</th><th>Loại</th><th>Tiêu đề Job</th><th>Trạng thái</th><th>Ngân sách / Thực chi</th><th>Số dòng Log</th><th>Tạo lúc</th><th>Thao tác</th></tr></thead>
          <tbody>${jobs.map((j) => `
            <tr>
              <td><code>${esc(j.id)}</code></td>
              <td><span class="badge">${esc(j.kind)}</span></td>
              <td><strong>${esc(j.title)}</strong></td>
              <td>${statusBadgeHtml(j.status)}</td>
              <td>$${Number(j.actual_cost_usd || 0).toFixed(4)} / $${Number(j.budget_limit_usd || 0).toFixed(2)}</td>
              <td>${j.log_count || 0} dòng</td>
              <td>${fmtTime(j.created_at)}</td>
              <td class="row">
                <button class="btn btn-sm btn-pri" data-action="hist-open-detail" data-id="job_${esc(j.id)}">🔍 Xem Log &amp; SP</button>
                ${j.status === "running" ? `<button class="btn btn-sm btn-danger" data-action="job-cancel" data-id="${esc(j.id)}">🛑 Dừng</button>` : ""}
              </td>
            </tr>`).join("")}
          </tbody>
        </table>`
      : `<div style="color:var(--muted)">Chưa có tiến trình nền nào.</div>`;
  }

  async function openHistoryDetail(idOrGs, targetContainerId = "histDetailCard") {
    const d = await api(`/api/history-logs/${encodeURIComponent(idOrGs)}`);
    LAST_HIST_DETAIL = d;
    const logsArr = Array.isArray(d.step_logs) ? d.step_logs : [];
    const resolvedHtml = renderResolvedResultsHtml(d.resolved_results);
    const jt = d.resolved_results?.jump_target;

    const detailHtml = `
      <div class="row" style="justify-content:space-between;padding:10px;background:#08101e;border:1px solid var(--border);border-radius:8px;margin-bottom:10px">
        <div class="row" style="font-size:12.5px">
          <span class="badge blue" style="font-size:13px">${esc(d.gs_code)} (STT #${d.seq_no})</span>
          <span class="badge">${esc(d.module_label || d.module)}</span>
          ${statusBadgeHtml(d.status)}
          <span>🕒 Bắt đầu: <strong>${fmtTime(d.created_at)}</strong></span>
          <span>⏱ Thời lượng: <strong>${fmtDuration(d.duration_ms)}</strong></span>
          <span>💵 Chi phí: <strong>$${Number(d.cost_usd || 0).toFixed(5)}</strong></span>
        </div>
        <div class="row">
          <button class="btn btn-sm" data-action="copy-gs-code" data-code="${esc(d.gs_code)}">📋 Copy ${esc(d.gs_code)}</button>
          <button class="btn btn-sm btn-gold" data-action="copy-bug-report">🐞 Copy gói báo lỗi</button>
          ${jt ? `<button class="btn btn-sm btn-pri" data-action="jump-tab" data-tab="${esc(jt.tab)}">${esc(jt.label)}</button>` : ""}
        </div>
      </div>

      ${d.error_text ? `<div style="margin-bottom:10px;padding:10px;border-radius:8px;background:rgba(239,68,68,0.14);border:1px solid #ef4444;color:#fca5a5"><strong>❌ Chi tiết lỗi:</strong> ${esc(d.error_text)}</div>` : ""}

      ${resolvedHtml}

      <div style="margin-bottom:12px">
        <div style="font-size:12.5px;font-weight:600;margin-bottom:5px;color:#93c5fd">📋 Nhật ký thực thi từng bước của Job (${logsArr.length} dòng):</div>
        <pre class="codebox">${logsArr.length ? esc(logsArr.join("\n")) : "Tác vụ chạy đồng bộ hoàn tất — xem bảng kết quả và JSON chi tiết bên dưới."}</pre>
      </div>

      <div class="row" style="margin-bottom:10px">
        <input type="text" id="histNoteInput" value="${esc(d.note || "")}" placeholder="Ghi chú đánh giá / rút kinh nghiệm cho lần chạy này..." style="flex:1" />
        <button class="btn btn-sm btn-pri" data-action="hist-save-note" data-id="${esc(d.log_id)}">💾 Lưu ghi chú</button>
      </div>

      <details>
        <summary style="cursor:pointer;font-size:12.5px;color:var(--muted);font-weight:600">🔎 Xem dữ liệu JSON gốc (Tham số Đầu vào &amp; Kết quả Đầu ra)</summary>
        <div class="grid2" style="margin-top:8px">
          <div>
            <div style="font-size:11.5px;color:var(--muted);margin-bottom:4px">📥 Tham số Đầu vào (Đã che khoá nhạy cảm):</div>
            <pre class="codebox">${esc(JSON.stringify(d.request_summary || {}, null, 2))}</pre>
          </div>
          <div>
            <div style="font-size:11.5px;color:var(--muted);margin-bottom:4px">📤 Dữ liệu Kết quả Đầu ra:</div>
            <pre class="codebox">${esc(JSON.stringify(d.result_summary || {}, null, 2))}</pre>
          </div>
        </div>
      </details>
    `;

    if (targetContainerId === "huntPastDetailBox") {
      const hbox = document.getElementById("huntPastDetailBox");
      hbox.innerHTML = `<div class="card" style="border-color:var(--sky);background:#0c1628">
        <div class="row" style="justify-content:space-between;margin-bottom:8px">
          <strong style="color:#7dd3fc">📄 Chi tiết Phiên Săn ${esc(d.gs_code)}: ${esc(d.title)}</strong>
          <button class="btn btn-sm" data-action="close-hunt-past">✕ Đóng</button>
        </div>
        ${detailHtml}
      </div>`;
      return;
    }

    const card = document.getElementById("histDetailCard");
    document.getElementById("histDetailTitle").textContent = `📄 Chi tiết Công việc ${d.gs_code}: ${d.title}`;
    document.getElementById("histDetailBody").innerHTML = detailHtml;
    card.style.display = "block";
    card.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  // --- PART 4.4 & 4.5: CHAT/PINS & SETTINGS ----------------------------------
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

  // --- INLINE SELECT CLASSIFICATION HANDLER ----------------------------------
  document.addEventListener("change", async (ev) => {
    const inlineSel = ev.target.closest("[data-inline-pid]");
    if (inlineSel) {
      const pid = Number(inlineSel.dataset.inlinePid);
      const fld = inlineSel.dataset.inlineField;
      try {
        await api(`/api/products/${pid}`, "PATCH", { [fld]: inlineSel.value });
        toast(`Đã phân loại SP #${pid}!`);
        await loadProducts();
      } catch (err) {
        toast(err.message, true);
      }
      return;
    }

    if (["filterIndustry", "filterShop", "filterCampaign", "filterPlatform", "filterSort"].includes(ev.target.id)) {
      loadProducts();
    } else if (["histFilterMod", "histFilterStatus"].includes(ev.target.id)) {
      loadHistoryAndJobs();
    }
  });

  // --- DELEGATED CLICK HANDLER -----------------------------------------------
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
      } else if (act === "jump-kho-all") {
        CURRENT_BUCKET = "all";
        CURRENT_SUB = "all";
        showTab("results", "/kho");
      } else if (act === "jump-kho-pending") {
        CURRENT_BUCKET = "cho_danh_gia";
        CURRENT_SUB = "all";
        showTab("results", "/kho/cho_danh_gia");
      } else if (act === "jump-history") {
        showTab("history", "/nhat-ky");
      } else if (act === "jump-tab") {
        showTab(actEl.dataset.tab);
      } else if (act === "sidebar-bucket") {
        CURRENT_BUCKET = actEl.dataset.bucket;
        CURRENT_SUB = "all";
        showTab("results", CURRENT_BUCKET === "all" ? "/kho" : `/kho/${CURRENT_BUCKET}`);
      } else if (act === "sidebar-industry") {
        const targetInd = actEl.dataset.ind || "";
        const fInd = document.getElementById("filterIndustry");
        if (fInd) {
          fInd.value = CURRENT_TAB === "results" && fInd.value === targetInd ? "" : targetInd;
        }
        if (CURRENT_BUCKET === "da_loai") CURRENT_BUCKET = "all";
        showTab("results", "/kho");
      } else if (act === "chip-industry") {
        document.getElementById("filterIndustry").value = actEl.dataset.ind || "";
        loadProducts();
      } else if (act === "set-sub-filter") {
        CURRENT_SUB = actEl.dataset.sub;
        loadProducts();
      } else if (act === "reset-kho-filters") {
        document.getElementById("filterSearch").value = "";
        document.getElementById("filterIndustry").value = "";
        document.getElementById("filterShop").value = "";
        document.getElementById("filterCampaign").value = "";
        document.getElementById("filterPlatform").value = "";
        document.getElementById("filterSoldMin").value = "";
        CURRENT_SUB = "all";
        loadProducts();
      } else if (act === "select-all-visible") {
        VISIBLE_PRODUCTS.forEach((p) => SELECTED_PIDS.add(p.id));
        loadProducts();
      } else if (act === "clear-selection") {
        SELECTED_PIDS.clear();
        loadProducts();
      } else if (act === "prod-set-status") {
        const pid = Number(actEl.dataset.id);
        await api(`/api/products/${pid}`, "PATCH", { status: actEl.dataset.st });
        toast(`Đã cập nhật trạng thái SP #${pid}`);
        loadProducts();
      } else if (act === "prod-enrich") {
        toast("Đang lấy Giá bán, Lượt bán & Ảnh thực tế...");
        const res = await api(`/api/products/${actEl.dataset.id}/enrich`, "POST", {});
        toast(res.summary);
        loadProducts();
      } else if (act === "enrich-missing-all") {
        toast("Đang làm giàu Giá bán & Lượt bán cho các SP khuyết dữ liệu...");
        const res = await api("/api/products/enrich-batch", "POST", { limit: 12 });
        toast(res.summary);
        loadProducts();
      } else if (act === "score-unscored-all") {
        toast("Đang chấm Jev cho các sản phẩm chưa chấm...");
        const res = await api("/api/products/score-unscored", "POST", {});
        toast(res.summary);
        loadProducts();
      } else if (act === "bulk-apply") {
        const ids = [...SELECTED_PIDS];
        const bact = actEl.dataset.bact;
        const payload = {
          ids,
          action: bact,
          bucket: document.getElementById("bulkBucketSel")?.value,
          industry: document.getElementById("bulkIndustrySel")?.value,
          shop_id: document.getElementById("bulkShopSel")?.value,
        };
        toast(`Đang xử lý hàng loạt ${ids.length} SP...`);
        const res = await api("/api/products/bulk", "POST", payload);
        if (bact === "delete") SELECTED_PIDS.clear();
        toast(res.summary);
        loadProducts();
      } else if (act === "bulk-status") {
        const ids = [...SELECTED_PIDS];
        const res = await api("/api/products/bulk", "POST", { ids, action: "set_status", status: actEl.dataset.st });
        toast(res.summary);
        loadProducts();
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
      } else if (act === "hunt-open-run") {
        await openHistoryDetail(actEl.dataset.id, "huntPastDetailBox");
      } else if (act === "close-hunt-past") {
        document.getElementById("huntPastDetailBox").innerHTML = "";
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
        toast("Đang quét từ khoá, chấm điểm Jev & lưu sản phẩm vào Kho...");
        const res = await api("/api/keywords/research", "POST", {
          keyword: document.getElementById("kwInput").value.trim(),
          platform: document.getElementById("kwPlatform").value,
          limit: Number(document.getElementById("kwLimit").value || 20),
          save_top_to_vault: document.getElementById("kwSaveVault").checked,
        });
        renderKeywordResult(res);
        loadKeywordHistory();
        syncSidebarCountsAndRefs();
        toast(res.summary);
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
        syncSidebarCountsAndRefs();
      } else if (act === "watch-check") {
        toast("Đang kiểm tra & đối chiếu sản phẩm mới...");
        const res = await api(`/api/watches/${actEl.dataset.id}/check`, "POST", {});
        toast(res.summary);
        loadWatches();
        syncSidebarCountsAndRefs();
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
        syncSidebarCountsAndRefs();
      } else if (act === "creator-search") {
        toast("Đang tìm Creator TikTok...");
        const res = await api("/api/creators/search", "POST", { query: document.getElementById("creatorQuery").value.trim() });
        toast(res.summary);
        loadCreatorsAndScans();
      } else if (act === "reload-products") {
        loadProducts();
      } else if (act === "toggle-select-pid") {
        const id = Number(actEl.dataset.id);
        if (actEl.checked) SELECTED_PIDS.add(id);
        else SELECTED_PIDS.delete(id);
        updateBulkBar();
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
        openModal(`📊 Hồ sơ & Phân loại Sản phẩm #${p.id}: ${p.title}`, `
          <div class="kpi-grid">
            <div class="kpi"><div class="lbl">Giá bán lẻ</div><div class="val">${vnd(p.price_vnd)}</div></div>
            <div class="kpi"><div class="lbl">Giá vốn về kho</div><div class="val gold">${vnd(p.cost_vnd)}</div></div>
            <div class="kpi"><div class="lbl">Lãi ròng/đơn (${ec.net_margin_pct || 0}%)</div><div class="val green">${vnd(ec.net_profit_per_order_vnd)}</div></div>
            <div class="kpi"><div class="lbl">ROAS Ads Hoà vốn</div><div class="val">${ec.breakeven_ads_roas || "—"}x</div></div>
          </div>
          <div class="grid3">
            <div class="field"><label>Cập nhật Giá bán (VNĐ)</label><input type="number" id="dosPrice" value="${p.price_vnd}" /></div>
            <div class="field"><label>Cập nhật Giá vốn (VNĐ)</label><input type="number" id="dosCost" value="${p.cost_vnd}" /></div>
            <div class="field"><label>Phân loại Nhóm Kho</label><select id="dosBucket">${Object.entries(KHO_BUCKETS_META).filter(([k]) => k !== "all" && k !== "chua_cham").map(([k, inf]) => `<option value="${k}" ${p.bucket === k ? "selected" : ""}>${inf.ico} ${esc(inf.name)}</option>`).join("")}</select></div>
          </div>
          <div class="grid2">
            <div class="field"><label>Ngành hàng</label><select id="dosIndustry">${Object.entries(INDUSTRY_META).map(([k, inf]) => `<option value="${k}" ${p.industry === k ? "selected" : ""}>${inf.ico} ${esc(inf.name)}</option>`).join("")}</select></div>
            <div class="field"><label>Ghi chú sản phẩm</label><input type="text" id="dosNote" value="${esc(p.note || "")}" /></div>
          </div>
          <button class="btn btn-pri" data-action="dos-save" data-id="${p.id}">💾 Lưu Giá vốn &amp; Phân loại</button>
          <h4 style="margin:14px 0 6px">Lịch sử Biến động Giá &amp; Lượt bán (${(d.metric_history || []).length} mốc)</h4>
          <table class="tbl"><thead><tr><th>Thời điểm</th><th>Nguồn</th><th>Giá bán</th><th>Tổng đã bán</th><th>Doanh số</th></tr></thead>
          <tbody>${(d.metric_history || []).map((h) => `<tr><td>${fmtTime(h.recorded_at)}</td><td>${esc(h.source)}</td><td>${vnd(h.price_vnd)}</td><td>${h.sold_count}</td><td>${vnd(h.gmv_vnd)}</td></tr>`).join("")}</tbody></table>
        `);
      } else if (act === "dos-save") {
        await api(`/api/products/${actEl.dataset.id}`, "PATCH", {
          price_vnd: Number(document.getElementById("dosPrice").value || 0),
          cost_vnd: Number(document.getElementById("dosCost").value || 0),
          bucket: document.getElementById("dosBucket").value,
          industry: document.getElementById("dosIndustry").value,
          note: document.getElementById("dosNote").value,
        });
        closeModal();
        toast("Đã lưu cập nhật sản phẩm!");
        if (CURRENT_TAB === "results") loadProducts();
        else syncSidebarCountsAndRefs();
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
        syncSidebarCountsAndRefs();
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
        syncSidebarCountsAndRefs();
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
        syncSidebarCountsAndRefs();
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
        syncSidebarCountsAndRefs();
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
        syncSidebarCountsAndRefs();
      } else if (act === "sales-add-expense") {
        const res = await api("/api/sales/expenses", "POST", {
          expense_type: document.getElementById("expType").value,
          amount_vnd: Number(document.getElementById("expAmount").value || 0),
          note: document.getElementById("expNote").value,
        });
        toast(res.summary);
        loadAnalytics();
      } else if (act === "hist-refresh" || act === "hist-filter") {
        loadHistoryAndJobs();
      } else if (act === "hist-reset") {
        document.getElementById("histSearchQ").value = "";
        document.getElementById("histFilterMod").value = "all";
        document.getElementById("histFilterStatus").value = "all";
        loadHistoryAndJobs();
      } else if (act === "hist-open-detail") {
        await openHistoryDetail(actEl.dataset.id, "histDetailCard");
      } else if (act === "hist-close-detail") {
        document.getElementById("histDetailCard").style.display = "none";
      } else if (act === "hist-save-note") {
        await api(`/api/history-logs/${encodeURIComponent(actEl.dataset.id)}/note`, "POST", {
          note: document.getElementById("histNoteInput").value,
        });
        toast("Đã lưu ghi chú cho công việc này!");
        loadHistoryAndJobs();
      } else if (act === "copy-gs-code") {
        await navigator.clipboard?.writeText(actEl.dataset.code || "");
        toast(`Đã copy mã ${actEl.dataset.code}!`);
      } else if (act === "copy-bug-report") {
        if (LAST_HIST_DETAIL) {
          await navigator.clipboard?.writeText(LAST_HIST_DETAIL.bug_report_text || "");
          toast("Đã copy gói báo lỗi vào Clipboard!");
        }
      } else if (act === "job-cancel") {
        await api(`/api/jobs/${actEl.dataset.id}/cancel`, "POST", {});
        toast("Đã yêu cầu dừng Job!");
        loadHistoryAndJobs();
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

  async function initRoute() {
    const path = window.location.pathname;
    const urlParams = new URLSearchParams(window.location.search);
    const gsTarget = urlParams.get("gs");

    if (path.startsWith("/kho/")) {
      const b = path.slice(5).trim();
      if (KHO_BUCKETS_META[b]) CURRENT_BUCKET = b;
      showTab("results", null);
      return;
    }
    if (gsTarget) {
      showTab("history", null);
      setTimeout(() => openHistoryDetail(gsTarget, "histDetailCard"), 250);
      return;
    }
    const tab = ROUTE_TO_TAB[path] || (path.startsWith("/kho") ? "results" : "hunt");
    showTab(tab, null);
  }

  window.addEventListener("popstate", initRoute);
  window.addEventListener("DOMContentLoaded", initRoute);
})();
