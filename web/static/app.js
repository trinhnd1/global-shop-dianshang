/* Global Shop Dianshang v1.0.8 — Ecosystem & Accessory Playbooks (Xteink X4, Goojodoq) + Kalodata & Affiliate Global Selling (`peng_dedicated`) */
(() => {
  const ROUTE_TO_TAB = {
    "/": "hunt",
    "/san-sp": "hunt",
    "/kalodata-pro": "kalopro",
    "/nhap-kalodata": "kalodata",
    "/kalodata": "kalodata",
    "/he-sinh-thai": "ecosystems",
    "/luong-300-desk": "deskflow",
    "/tu-khoa": "keywords",
    "/theo-doi": "watches",
    "/soi-shop": "shopspy",
    "/creators": "shopspy",
    "/shop-cua-toi": "myshops",
    "/bang-xep-hang-jev": "jevrank",
    "/kho": "results",
    "/nguon-hang-tq": "sourcing",
    "/kho-shop": "shops",
    "/soi-san-pham": "spy",
    "/video-jev": "videojev",
    "/clone-video": "videoclone",
    "/chien-dich": "campaigns",
    "/doanh-so": "analytics",
    "/nhat-ky": "history",
    "/apify-store": "apifystore",
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
    overseas: "✈️ Shop Quốc tế / Nước ngoài",
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

  const DEFAULT_FEES_BY_PLAT = {
    tiktok_shop: 11.5,
    tiktok_shop_vn: 11.5,
    tiktok_shop_ph: 11.0,
    tiktok_shop_sg: 10.5,
    tiktok_shop_my: 11.0,
    tiktok_shop_th: 11.0,
    shopee: 12.5,
    shopee_vn: 12.5,
    shopee_ph: 12.0,
    shopee_sg: 11.5,
    shopee_my: 12.0,
    shopee_th: 12.0,
    facebook_fanpage: 0,
    tiktok_channel: 11.5,
    lazada: 11.0,
    instagram: 0,
    website: 0,
  };

  let APIFY_STORE_GOAL = "";
  let ACTIVE_ECO_ID = "";

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
  let MY_SHOPS_FILTER_PLAT = "";
  let MY_SHOP_SELECTED_CMPS = new Set();
  let GT_HISTORY_RUNS = [];

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

  function fmtPriceDual(item) {
    const pv = Number(item?.price_vnd || 0);
    const np = Number(item?.native_price || 0);
    const ccy = String(item?.native_currency || "VND").toUpperCase();
    if (pv <= 0 && np <= 0) return '<span style="color:#fcd34d">Chưa lấy</span>';
    if (ccy !== "VND" && np > 0) {
      const sym = { PHP: "₱", SGD: "S$", MYR: "RM", THB: "฿" }[ccy] || `${ccy} `;
      return `${sym}${np.toLocaleString("en-US", { maximumFractionDigits: 2 })} <span style="font-size:11px;color:var(--muted)">(${vnd(pv)})</span>`;
    }
    return vnd(pv);
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

      const ownCnt = ov.my_shops_count ?? ALL_SHOPS.filter((s) => s.role === "own_shop").length;
      const compCnt = ov.competitor_shops_count ?? ALL_SHOPS.filter((s) => s.role === "competitor_shop").length;

      document.getElementById("kpiVault").textContent = ov.vault_products;
      document.getElementById("topVaultCnt").textContent = ov.vault_products;
      document.getElementById("kpiWatches").textContent = ov.watches_count;
      document.getElementById("kpiShopsSrc").textContent = `${ownCnt} shop mình / ${ov.sourcing_count} mẫu TQ`;
      const sp = ov.sales || {};
      document.getElementById("kpiSalesProfit").textContent = `${vnd(sp.gross_gmv_vnd)} / Lãi ${vnd(sp.net_profit_vnd)}`;
      document.getElementById("cntWatches").textContent = ov.watches_count;
      const elCntMyShops = document.getElementById("cntMyShops");
      if (elCntMyShops) elCntMyShops.textContent = ownCnt;
      const elTopMyShops = document.getElementById("topMyShopsCnt");
      if (elTopMyShops) elTopMyShops.textContent = ownCnt;
      document.getElementById("cntShops").textContent = compCnt;
      document.getElementById("cntSourcing").textContent = ov.sourcing_count;
      const elDeskCnt = document.getElementById("cntDeskRuns");
      if (elDeskCnt) elDeskCnt.textContent = ov.desk300_runs_count || 0;
      const elApifyCnt = document.getElementById("cntApifyStore");
      if (elApifyCnt) elApifyCnt.textContent = Number(ov.apify_store_count || 0).toLocaleString("en-US");
      const elTopApifyCnt = document.getElementById("topApifyCnt");
      if (elTopApifyCnt) elTopApifyCnt.textContent = Number(ov.apify_store_count || 0).toLocaleString("en-US");
      const elEcoCnt = document.getElementById("cntEcosystems");
      if (elEcoCnt) elEcoCnt.textContent = ov.ecosystems_count || 0;
      const elTopEcoCnt = document.getElementById("topEcoCnt");
      if (elTopEcoCnt) elTopEcoCnt.textContent = ov.ecosystems_count || 0;
      const jevCnt = ov.jev_scored_count ?? Math.max(0, (BUCKET_COUNTS.all || 0) - (BUCKET_COUNTS.chua_cham || 0));
      const elJevCnt = document.getElementById("cntJevScored");
      if (elJevCnt) elJevCnt.textContent = jevCnt;
      const elTopJevCnt = document.getElementById("topJevCnt");
      if (elTopJevCnt) elTopJevCnt.textContent = jevCnt;
      if (ov.recent_logs?.length) {
        document.getElementById("cntHistoryLogs").textContent = ov.recent_logs[0].seq_no || ov.recent_logs.length;
      }

      populateKhoSelectControls();
      renderKhoAndIndustrySidebar();
    } catch (_) {}
  }

  function renderMyShopCampaignPicker() {
    const box = document.getElementById("msCampaignsPicker");
    if (!box) return;
    if (!ALL_CAMPAIGNS.length) {
      box.innerHTML = `<span style="font-size:12px;color:var(--muted)">Chưa có chiến dịch nào (tạo ở mục 🚀 Chiến dịch Ngành hàng).</span>`;
      return;
    }
    box.innerHTML = ALL_CAMPAIGNS.map((c) => {
      const isAct = MY_SHOP_SELECTED_CMPS.has(c.campaign_id) ? " active" : "";
      return `<button type="button" class="chip${isAct}" data-action="ms-toggle-cmp" data-cid="${esc(c.campaign_id)}">🚀 ${esc(c.name)}</button>`;
    }).join("");
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

    const jrInd = document.getElementById("jrIndustry");
    if (jrInd) {
      const curJr = jrInd.value;
      jrInd.innerHTML =
        `<option value="">Mọi ngành</option>` +
        Object.entries(INDUSTRY_META)
          .map(([k, inf]) => `<option value="${k}">${inf.ico} ${esc(inf.name)}</option>`)
          .join("");
      jrInd.value = curJr;
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

    const msInd = document.getElementById("msIndustry");
    if (msInd && !msInd.options.length) {
      msInd.innerHTML = Object.entries(INDUSTRY_META)
        .map(([k, inf]) => `<option value="${k}" ${k === "gia_dung" ? "selected" : ""}>${inf.ico} ${esc(inf.name)}</option>`)
        .join("");
    }
    renderMyShopCampaignPicker();

    const ownShops = ALL_SHOPS.filter((s) => s.role === "own_shop");
    const fShop = document.getElementById("filterShop");
    if (fShop) {
      const cur = fShop.value;
      fShop.innerHTML =
        `<option value="">🏠 Tất cả Shop của tôi</option><option value="__unassigned__">⚠️ Chưa gắn Shop</option>` +
        ownShops.map((s) => `<option value="${esc(s.shop_id)}">${esc(s.platform_icon || "🏠")} ${esc(s.shop_name)} (${esc(s.platform_label || s.platform)})</option>`).join("");
      fShop.value = cur;
    }
    const bShop = document.getElementById("bulkShopSel");
    if (bShop) {
      bShop.innerHTML =
        `<option value="">— Gỡ khỏi Shop —</option>` +
        ownShops.map((s) => `<option value="${esc(s.shop_id)}">${esc(s.platform_icon || "🏠")} ${esc(s.shop_name)}</option>`).join("");
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
    else if (tab === "kalopro") await loadKalodataProTab();
    else if (tab === "kalodata") await loadKalodataImportTab();
    else if (tab === "ecosystems") await loadEcosystemsTab();
    else if (tab === "deskflow") await loadDesk300Tab();
    else if (tab === "myshops") await loadMyShops();
    else if (tab === "jevrank") await loadJevLeaderboard();
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
    else if (tab === "apifystore") await loadApifyStoreTab();
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

  function renderGoogleTrendsResult(run) {
    const box = document.getElementById("gtResultsBox");
    if (!box || !run) return;
    const seeds = run.seed_summaries || [];
    const kws = run.keywords || run.results || [];
    const seedsHtml = seeds.length
      ? `<div class="row" style="margin-bottom:8px;gap:6px">
          ${seeds.map((s) => `<span class="badge blue">📈 <strong>${esc(s.seed_term)}</strong>: Điểm hiện tại ${s.current_interest ?? "—"} · Đà tăng <strong>${s.momentum_pct != null ? (s.momentum_pct >= 0 ? "+" : "") + s.momentum_pct + "%" : "—"}</strong></span>`).join("")}
         </div>`
      : "";

    box.innerHTML = `
      <div style="background:#081222;border:1px solid var(--border);border-radius:8px;padding:10px">
        <div class="row" style="justify-content:space-between;margin-bottom:6px">
          <span style="font-size:12.5px;color:#7dd3fc"><strong>Nguồn dữ liệu:</strong> <code>${esc(run.source_used || run.provider_used || "")}</code> · ${kws.length} từ khoá xu hướng</span>
          <button class="btn btn-sm btn-pri" data-action="gt-push-all-top">🎯 Đẩy Top 4 từ khoá lên ô Săn SP Đa tầng</button>
        </div>
        ${seedsHtml}
        ${
          kws.length
            ? `<table class="tbl">
                <thead><tr><th>Từ khoá Xu hướng / Đột phá</th><th>Loại tín hiệu</th><th>Độ tăng trưởng</th><th>Ngành (Jev)</th><th>Điểm Ý định Mua (Jev)</th><th>Hành động</th></tr></thead>
                <tbody>
                  ${kws.map((k) => `
                    <tr>
                      <td><strong class="gt-kw-item" data-kw="${esc(k.keyword)}">${esc(k.keyword)}</strong></td>
                      <td><span class="badge ${k.kind === "rising" ? "gold" : "blue"}">${k.kind === "rising" ? "🔥 Đột phá / Rising" : k.kind === "seed" ? "🌱 Gốc" : "⭐ Top Search"}</span></td>
                      <td><strong>${esc(k.growth_label || "—")}</strong></td>
                      <td>${esc(k.industry_label || "—")}</td>
                      <td>${k.jev_score_10 != null ? `<span class="badge ${k.jev_score_10 >= 7 ? "green" : "blue"}">🤖 ${k.jev_score_10}/10</span>` : "—"}</td>
                      <td class="row">
                        <button class="btn btn-sm btn-pri" data-action="gt-push-kw" data-kw="${esc(k.keyword)}">+ Đưa vào Săn SP</button>
                        <button class="btn btn-sm btn-gold" data-action="prod-find-cn" data-id="" data-title="${esc(k.keyword)}">🇨🇳 Nguồn 1688</button>
                      </td>
                    </tr>`).join("")}
                </tbody>
              </table>`
            : `<div style="color:var(--muted)">Chưa có từ khoá mở rộng cho truy vấn này.</div>`
        }
      </div>`;
  }

  async function loadGoogleTrendsHistory() {
    try {
      const data = await api("/api/hunt/google-trends/history");
      GT_HISTORY_RUNS = data.runs || [];
      const sel = document.getElementById("gtHistorySelect");
      if (sel) {
        sel.innerHTML =
          `<option value="">🕒 Xem lại lịch sử Google Trends (${GT_HISTORY_RUNS.length})...</option>` +
          GT_HISTORY_RUNS.map((r) => `<option value="${esc(r.run_id)}">${esc((r.seed_terms || []).join(", "))} (${ (r.keywords || []).length } từ khoá · ${fmtTime(r.created_at).slice(5, 16)})</option>`).join("");
      }
    } catch (_) {}
  }

  async function loadPainpoints() {
    const box = document.getElementById("painpointsListBox");
    if (!box) return;
    const data = await api("/api/hunt/painpoints");
    const items = data.painpoints || [];
    const chLabel = {
      facebook_organic: "📘 Facebook",
      facebook_ads: "📢 FB Ads",
      threads: "🧵 Threads",
      x: "𝕏 X",
      reddit: "👽 Reddit",
    };

    box.innerHTML = items.length
      ? items.map((pp) => {
          const pil = (pp.jev_detail || {}).pillars || {};
          const posts = pp.evidence_posts || [];
          const prods = pp.matched_products || [];
          return `
            <div style="border:1px solid rgba(16,185,129,0.35);border-radius:10px;padding:12px;margin-bottom:12px;background:#081220">
              <div class="row" style="justify-content:space-between">
                <div class="row" style="gap:6px">
                  <span class="badge green">🧠 Painpoint</span>
                  <span class="badge blue">${esc(pp.industry_icon)} ${esc(pp.industry_label)}</span>
                  ${(pp.channels || []).map((c) => `<span class="badge">${esc(chLabel[c] || c)}</span>`).join("")}
                  ${pp.jev_pain_score != null ? `<span class="badge gold">🤖 Jev Pain Score: ${pp.jev_pain_score}/10</span>` : ""}
                </div>
                <div class="row">
                  <span style="font-size:11.5px;color:var(--muted)">${fmtTime(pp.created_at)}</span>
                  <button class="btn btn-sm btn-danger" data-action="pp-delete" data-id="${esc(pp.painpoint_id)}">Xoá</button>
                </div>
              </div>

              <div style="font-size:15px;font-weight:700;margin-top:8px;color:#e2e8f0">⚡ ${esc(pp.pain_title)}</div>
              <div style="font-size:12.5px;color:#93c5fd;margin-top:3px">💡 Định hướng giải pháp: <strong>${esc(pp.solution_archetype)}</strong> ${
                pil.pain_severity != null
                  ? ` · Độ bức thiết: <strong>${pil.pain_severity}/10</strong> · Dễ giải bằng SP: <strong>${pil.product_solvability}/10</strong> · Hook Video 3s: <strong>${pil.viral_hook_potential}/10</strong>`
                  : ""
              }</div>

              <div style="margin-top:8px">
                <div style="font-size:12px;color:#6ee7b7;margin-bottom:4px">🎯 Từ khoá Sản phẩm Giải pháp đề xuất (bấm để săn thêm trên Shopee/TikTok hoặc tìm xưởng 1688):</div>
                <div class="row" style="gap:6px">
                  ${(pp.recommended_keywords || []).map((kw) => `
                    <span class="badge green" style="padding:4px 8px;font-size:12px">
                      🔑 ${esc(kw)}
                      <button class="btn btn-sm" style="padding:2px 6px;margin-left:4px" data-action="gt-push-kw" data-kw="${esc(kw)}" title="Đưa lên ô Săn SP">+ Săn SP</button>
                      <button class="btn btn-sm btn-gold" style="padding:2px 6px" data-action="prod-find-cn" data-id="" data-title="${esc(kw)}" title="Tìm xưởng 1688/PDD">🇨🇳 1688</button>
                    </span>
                  `).join("")}
                </div>
              </div>

              ${
                posts.length
                  ? `<details style="margin-top:8px">
                      <summary style="cursor:pointer;font-size:12px;color:var(--muted)">💬 Xem ${posts.length} bài đăng / bình luận thực tế thu thập từ Facebook, Threads, X, Reddit</summary>
                      <div style="margin-top:6px;max-height:190px;overflow:auto;padding:8px;background:#060d18;border-radius:6px">
                        ${posts.map((po) => `
                          <div style="border-bottom:1px solid var(--border);padding:5px 0;font-size:12px">
                            <span class="badge">${esc(chLabel[po.channel] || po.channel)}</span>
                            ${po.author ? `<strong>@${esc(po.author)}:</strong>` : ""}
                            <span>${esc((po.text || "").slice(0, 240))}</span>
                            ${po.url ? `<a href="${esc(po.url)}" target="_blank" style="color:#7dd3fc;margin-left:6px">[Mở bài gốc ↗]</a>` : ""}
                          </div>`).join("")}
                      </div>
                    </details>`
                  : ""
              }

              ${
                prods.length
                  ? `<div style="margin-top:10px;border-top:1px solid var(--border);padding-top:8px">
                      <div class="row" style="justify-content:space-between;margin-bottom:5px">
                        <strong style="font-size:12.5px;color:#fcd34d">🛒 Sản phẩm Giải pháp đã tìm thấy &amp; lưu vào Kho SP (${prods.length} SP):</strong>
                        <button class="btn btn-sm btn-pri" data-action="jump-kho-pending">🗂 Sang Kho Phân loại</button>
                      </div>
                      <table class="tbl">
                        <thead><tr><th>#</th><th>Tên Sản phẩm Giải pháp</th><th>Sàn</th><th>Giá bán</th><th>Đã bán</th><th>Điểm Jev</th><th>Thao tác</th></tr></thead>
                        <tbody>
                          ${prods.map((p) => `
                            <tr>
                              <td>#${p.id}</td>
                              <td><a href="${esc(p.url || "#")}" target="_blank" style="color:#93c5fd">${esc(p.title)}</a></td>
                              <td><span class="badge">${esc(p.platform)}</span></td>
                              <td>${p.price_vnd > 0 ? vnd(p.price_vnd) : "Chưa lấy"}</td>
                              <td><strong>${Number(p.sold_count || 0).toLocaleString("vi-VN")}</strong></td>
                              <td>${p.jev_score != null ? `<span class="badge gold">${p.jev_score}/10</span>` : "—"}</td>
                              <td><button class="btn btn-sm btn-pri" data-action="prod-dossier" data-id="${p.id}">📊 Mở &amp; Phân loại</button></td>
                            </tr>`).join("")}
                        </tbody>
                      </table>
                    </div>`
                  : ""
              }
            </div>`;
        }).join("")
      : `<div style="color:var(--muted);font-size:12.5px">Chưa có Painpoint nào được lưu. Nhập chủ đề (VD: <em>"nhà tắm ẩm mốc mùi hôi"</em> hoặc <em>"đau mỏi cổ vai gáy"</em>) rồi bấm <strong>"🧠 Quét Painpoint &amp; Tìm Sản phẩm Phù hợp"</strong>!</div>`;
  }

  function renderHuntScheduleRunDetail(run, bucketLabels = {}) {
    const box = document.getElementById("huntScheduleRunDetailBox");
    if (!box || !run) return;
    const bb = run.bucket_breakdown || {};
    const bbChips = Object.entries(bb)
      .map(([k, cnt]) => `<span class="badge blue">${esc(bucketLabels[k] || KHO_BUCKETS_META[k]?.name || k)}: <strong>${cnt}</strong></span>`)
      .join(" ");
    const newList = (run.new_items || []).slice(0, 6);
    const risingList = (run.rising_items || []).slice(0, 6);
    const prods = (run.products || []).slice(0, 12);

    box.innerHTML = `
      <div style="padding:12px;background:#071222;border:1px solid rgba(251,191,36,0.55);border-radius:10px">
        <div class="row" style="justify-content:space-between;margin-bottom:8px">
          <div>
            <strong style="color:#fcd34d;font-size:13.5px">📊 Báo cáo Phiên Săn Lặp lại (${esc(run.run_id)} · ${fmtTime(run.created_at)})</strong>
            <div style="font-size:12px;color:var(--muted)">Thu thập <strong>${run.total_sampled}</strong> SP · <span style="color:#6ee7b7">+${run.new_products_count} SP mới</span> · <span style="color:#fcd34d">${run.rising_products_count} SP tăng bán</span> ${run.desk300_nnn ? `· Gói 300+desk <code>#${esc(run.desk300_nnn)}</code>` : ""} · Jev: <strong>${run.strong_pick_count} Strong Pick</strong> / ${run.maybe_count} Maybe</div>
          </div>
          <button class="btn btn-sm" data-action="hsched-close-detail">✕ Đóng</button>
        </div>

        <div style="padding:9px 11px;background:#0d1b30;border-left:3px solid #fbbf24;border-radius:6px;margin-bottom:8px;font-size:12.5px;line-height:1.5">
          <strong style="color:#fde68a">🤖 Tổng hợp Điều hành 300+desk:</strong> ${esc(run.desk_synthesis_text || "—")}
        </div>

        ${bbChips ? `<div class="row" style="gap:6px;margin-bottom:8px"><strong style="font-size:12px;color:var(--muted)">Phân loại Kho tự động:</strong> ${bbChips}</div>` : ""}

        ${
          newList.length
            ? `<div style="margin-bottom:8px;font-size:12px">
                <strong style="color:#6ee7b7">🆕 Sản phẩm mới phát hiện trong phiên này (${run.new_products_count}):</strong>
                <div style="margin-top:4px">${newList.map((n) => `<div>• <a href="${esc(n.url || "#")}" target="_blank" style="color:#93c5fd">${esc(n.title)}</a> — ${vnd(n.price_vnd)} (đã bán ${n.sold_count})</div>`).join("")}</div>
              </div>`
            : ""
        }

        ${
          risingList.length
            ? `<div style="margin-bottom:8px;font-size:12px">
                <strong style="color:#fcd34d">📈 Sản phẩm tăng lượt bán / giảm tồn kho (${run.rising_products_count}):</strong>
                <div style="margin-top:4px">${risingList.map((r) => `<div>• <strong>+${r.delta_sold} đơn</strong>: <a href="${esc(r.url || "#")}" target="_blank" style="color:#93c5fd">${esc(r.title)}</a> (tổng ${r.sold_count})</div>`).join("")}</div>
              </div>`
            : ""
        }

        ${
          prods.length
            ? `<div style="max-height:260px;overflow:auto">
                <table class="tbl">
                  <thead><tr><th>#ID</th><th>Sản phẩm đã xử lý &amp; phân loại</th><th>Sàn</th><th>Giá bán</th><th>Đã bán</th><th>Điểm Jev</th><th>Ngăn Kho tự phân loại</th><th>Mở</th></tr></thead>
                  <tbody>
                    ${prods.map((p) => `
                      <tr>
                        <td>#${p.id}</td>
                        <td><a href="${esc(p.url || "#")}" target="_blank" style="color:#93c5fd">${esc(p.desk300?.seo_title || p.title)}</a>
                          ${p.desk300?.cn_1688_keyword ? `<div style="font-size:11px;color:#fcd34d">1688: <code>${esc(p.desk300.cn_1688_keyword)}</code></div>` : ""}
                        </td>
                        <td><span class="badge">${esc(p.channel_label || p.platform)}</span></td>
                        <td>${vnd(p.price_vnd)}</td>
                        <td><strong>${Number(p.sold_count || 0).toLocaleString("vi-VN")}</strong></td>
                        <td>${p.jev_score != null ? `<span class="badge gold">${p.jev_score}/10</span>` : "—"}</td>
                        <td><span class="badge green">${esc(p.bucket_label || KHO_BUCKETS_META[p.bucket]?.name || p.bucket)}</span></td>
                        <td><button class="btn btn-sm btn-pri" data-action="prod-dossier" data-id="${p.id}">📊 Hồ sơ</button></td>
                      </tr>`).join("")}
                  </tbody>
                </table>
              </div>`
            : ""
        }
      </div>`;
  }

  async function loadHuntSchedules() {
    const box = document.getElementById("huntSchedulesListBox");
    if (!box) return;
    try {
      const data = await api("/api/hunt/schedules");
      const items = data.schedules || [];
      if (!items.length) {
        box.innerHTML = `<div style="color:var(--muted);font-size:12.5px">Chưa có lịch săn lặp lại nào. Nhập từ khoá/chủ đề Painpoint, chọn giờ cố định (VD: <code>07:30</code>) rồi bấm <strong>"⏰ Tạo &amp; Kích hoạt Lịch Săn Lặp lại Tự động"</strong>!</div>`;
        return;
      }
      box.innerHTML = `
        <table class="tbl">
          <thead><tr><th>Lịch Săn Lặp lại</th><th>Mốc thời gian</th><th>Từ khoá &amp; SP ghim</th><th>Trạng thái &amp; Lần kế tiếp</th><th>Tổng hợp 300+desk &amp; Kết quả Jev gần nhất</th><th>Thao tác</th></tr></thead>
          <tbody>
            ${items.map((s) => {
              const ls = s.last_summary || {};
              const active = s.status === "active";
              return `
                <tr>
                  <td>
                    <strong style="color:#fde68a">${esc(s.name)}</strong>
                    <div style="font-size:11px;color:var(--muted)">Đã chạy ${s.runs_count} phiên · Kênh: ${(s.channels || []).length}</div>
                  </td>
                  <td><span class="badge gold">⏰ ${esc(s.cadence_label)}</span></td>
                  <td style="font-size:12px">
                    <div>${(s.keywords || []).map((k) => `<span class="badge blue" style="margin:1px">${esc(k)}</span>`).join(" ") || "—"}</div>
                    ${(s.pinned_products || []).length ? `<div style="font-size:11px;color:#6ee7b7;margin-top:3px">📌 Ghim ${(s.pinned_products || []).length} SP mục tiêu</div>` : ""}
                  </td>
                  <td style="font-size:12px">
                    <div>${active ? `<span class="badge green">🟢 Đang bật</span>` : `<span class="badge">⏸ Tạm dừng</span>`}</div>
                    <div style="font-size:11px;color:var(--muted);margin-top:3px">Kế tiếp: ${s.next_run_at ? fmtTime(s.next_run_at) : "—"}</div>
                  </td>
                  <td style="font-size:12px;max-width:360px">
                    ${
                      ls.headline
                        ? `<div><strong>${esc(ls.headline)}</strong></div>
                           <div style="font-size:11.5px;color:#93c5fd;margin-top:2px">${esc((ls.desk_synthesis || "").slice(0, 145))}${(ls.desk_synthesis || "").length > 145 ? "..." : ""}</div>`
                        : `<span style="color:var(--muted)">Chưa chạy phiên đầu tiên</span>`
                    }
                  </td>
                  <td>
                    <div class="row" style="gap:4px">
                      <button class="btn btn-sm btn-pri" data-action="hsched-run-now" data-id="${esc(s.schedule_id)}">▶️ Quét ngay</button>
                      ${ls.run_id ? `<button class="btn btn-sm btn-gold" data-action="hsched-open-run" data-id="${esc(ls.run_id)}">📊 Báo cáo</button>` : ""}
                      <button class="btn btn-sm" data-action="hsched-open-history" data-id="${esc(s.schedule_id)}">📜 Lịch sử</button>
                      <button class="btn btn-sm" data-action="hsched-toggle-status" data-id="${esc(s.schedule_id)}" data-st="${active ? "pause" : "resume"}">${active ? "⏸" : "▶️"}</button>
                      <button class="btn btn-sm btn-danger" data-action="hsched-delete" data-id="${esc(s.schedule_id)}">🗑</button>
                    </div>
                  </td>
                </tr>`;
            }).join("")}
          </tbody>
        </table>`;
    } catch (_) {}
  }

  async function loadHuntRecentRuns() {
    await Promise.all([loadGoogleTrendsHistory(), loadPainpoints(), loadHuntSchedules(), loadKalodataCategoriesAndHuntHistory()]);
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

  // --- PART 2.0: JEV AI PRODUCT LEADERBOARD (`🏆 BẢNG XẾP HẠNG JEV AI`) -------
  function renderJevPillarBarsHtml(pillars = {}, highlightKey = "") {
    const order = [
      ["suc_cau", "Sức cầu", "#f97316"],
      ["bien_lai", "Biên lãi", "#10b981"],
      ["de_nhap_tq", "Nhập TQ", "#f59e0b"],
      ["canh_tranh", "Cạnh tranh", "#38bdf8"],
      ["khac_biet", "Combo/USP", "#a78bfa"],
      ["de_lam_video", "Làm Video", "#f43f5e"],
    ];
    return `<div style="display:grid;grid-template-columns:repeat(2,minmax(115px,1fr));gap:4px 8px;font-size:11px">
      ${order.map(([k, lbl, col]) => {
        const val = Number(pillars[k] || 0);
        const pct = Math.min(100, Math.max(0, val * 10));
        const isHi = highlightKey === k;
        return `<div>
          <div style="display:flex;justify-content:space-between;color:${isHi ? "#fde047" : "var(--muted)"};font-weight:${isHi ? "700" : "400"}">
            <span>${lbl}</span><span>${val > 0 ? val.toFixed(1) : "—"}</span>
          </div>
          <div style="height:4px;background:#162238;border-radius:3px;overflow:hidden;margin-top:1px">
            <div style="width:${pct}%;height:100%;background:${col}"></div>
          </div>
        </div>`;
      }).join("")}
    </div>`;
  }

  async function loadJevLeaderboard() {
    const rk = document.getElementById("jrRankBy")?.value || "overall_10";
    const tier = document.getElementById("jrTier")?.value || "all";
    const plat = document.getElementById("jrPlatform")?.value || "";
    const ind = document.getElementById("jrIndustry")?.value || "";
    const minSc = document.getElementById("jrMinScore")?.value || "0";
    const q = document.getElementById("jrSearchQ")?.value.trim() || "";

    const expBtn = document.getElementById("jrExportCsvBtn");
    if (expBtn) expBtn.href = `/api/products/jev-leaderboard/export.csv?rank_by=${encodeURIComponent(rk)}`;

    const qs = new URLSearchParams({ rank_by: rk, tier, platform: plat, industry: ind, min_score: minSc, q, limit: "200" });
    const data = await api(`/api/products/jev-leaderboard?${qs}`);
    const k = data.kpis || {};
    const items = data.items || [];
    const top3 = data.podium_top3 || [];
    const indRank = data.industry_ranking || [];

    document.getElementById("jevRankKpiStrip").innerHTML = `
      <div class="kpi"><div class="lbl">Tổng SP đã chấm Jev AI</div><div class="val gold">${k.total_scored || 0} SP</div><div style="font-size:11px;color:var(--muted)">Còn ${k.total_unscored || 0} SP chưa chấm</div></div>
      <div class="kpi"><div class="lbl">🏆 Strong Pick (Nhập test ngay)</div><div class="val green">${k.strong_pick_count || 0} SP</div></div>
      <div class="kpi"><div class="lbl">⚖️ Maybe (Tiềm năng / Test nhỏ)</div><div class="val sky">${k.maybe_count || 0} SP</div></div>
      <div class="kpi"><div class="lbl">Điểm Jev Cao nhất / TB</div><div class="val gold">${k.max_jev_score || 0} / ${k.avg_jev_score || 0}</div></div>
      <div class="kpi"><div class="lbl">% Khuyến nghị Nhập Test TB</div><div class="val green">${k.avg_import_prob_pct || 0}%</div></div>
    `;

    document.getElementById("jevIndustryRankChips").innerHTML =
      `<button class="chip ${!ind ? "active" : ""}" data-action="jr-chip-ind" data-ind="">🗂 Tất cả ngành (${k.total_scored || 0})</button>` +
      indRank
        .map(
          (ir) =>
            `<button class="chip ${ind === ir.industry ? "active" : ""}" data-action="jr-chip-ind" data-ind="${esc(ir.industry)}">${esc(ir.industry_icon)} ${esc(ir.industry_label)}: <strong>${ir.avg_jev_score}/10</strong> (${ir.count} SP)</button>`
        )
        .join("");

    const podiumMedals = [
      { ico: "🥇 HẠNG 1", border: "#fbbf24", bg: "linear-gradient(180deg,#1a170a 0%,#0b1322 100%)", col: "#fde047" },
      { ico: "🥈 HẠNG 2", border: "#94a3b8", bg: "linear-gradient(180deg,#131b29 0%,#0b1322 100%)", col: "#e2e8f0" },
      { ico: "🥉 HẠNG 3", border: "#d97706", bg: "linear-gradient(180deg,#1c130c 0%,#0b1322 100%)", col: "#fdba74" },
    ];
    document.getElementById("jevRankPodiumBox").innerHTML = top3.length
      ? `<div class="grid3">
          ${top3.map((p, idx) => {
            const pm = podiumMedals[idx] || podiumMedals[2];
            const cnKw = p.desk300?.cn_1688_keyword || "";
            return `
              <div class="card" style="margin:0;border:1.5px solid ${pm.border};background:${pm.bg}">
                <div class="row" style="justify-content:space-between;margin-bottom:8px">
                  <span style="font-weight:800;font-size:14px;color:${pm.col}">${pm.ico}</span>
                  <div class="row" style="gap:5px">
                    <span class="badge gold" style="font-size:13px;font-weight:800">🤖 ${p.jev_score}/10</span>
                    <span class="badge ${p.decision_tier === "strong_pick" ? "green" : p.decision_tier === "maybe" ? "blue" : ""}">${p.import_test_prob_pct}% Nhập test</span>
                  </div>
                </div>
                <div style="display:flex;gap:10px;margin-bottom:8px">
                  ${p.image_url ? `<img src="${esc(p.image_url)}" alt="" style="width:64px;height:64px;object-fit:cover;border-radius:8px;border:1px solid var(--border);flex-shrink:0" />` : ""}
                  <div style="min-width:0">
                    <a href="${esc(p.url || "#")}" target="_blank" style="font-weight:700;color:#e2e8f0;text-decoration:none;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">${esc(p.desk300?.seo_title || p.title)}</a>
                    <div style="font-size:11.5px;color:var(--muted);margin-top:3px">${esc(p.platform_market_label)} · Giá <strong style="color:#fde047">${fmtPriceDual(p)}</strong> · Bán <strong>${Number(p.sold_count || 0).toLocaleString("vi-VN")}</strong></div>
                    ${cnKw ? `<div style="font-size:11px;color:#fcd34d;margin-top:2px">🇨🇳 1688: <code>${esc(cnKw)}</code></div>` : ""}
                  </div>
                </div>
                ${renderJevPillarBarsHtml(p.pillars, rk)}
                <div class="row" style="margin-top:10px;justify-content:space-between">
                  <span class="badge">${esc(p.industry_icon)} ${esc(p.industry_label)}</span>
                  <div class="row" style="gap:4px">
                    <button class="btn btn-sm btn-gold" data-action="prod-set-status" data-id="${p.id}" data-st="nhap_test">🚀 Nhập test</button>
                    <button class="btn btn-sm" data-action="prod-find-cn" data-id="${p.id}" data-title="${esc(cnKw || p.title)}">🇨🇳 1688</button>
                    <button class="btn btn-sm btn-pri" data-action="prod-dossier" data-id="${p.id}">📊 Hồ sơ</button>
                  </div>
                </div>
              </div>`;
          }).join("")}
        </div>`
      : "";

    const rankMedals = { 1: "🥇 #1", 2: "🥈 #2", 3: "🥉 #3" };
    const bucketOpts = Object.entries(KHO_BUCKETS_META)
      .filter(([bk]) => bk !== "all" && bk !== "chua_cham")
      .map(([bk, inf]) => [bk, `${inf.ico} ${inf.name}`]);

    document.getElementById("jevRankTableBox").innerHTML = items.length
      ? `<div style="overflow-x:auto">
          <table class="tbl">
            <thead>
              <tr>
                <th style="width:68px">Hạng</th>
                <th style="min-width:260px">Sản phẩm &amp; Từ khoá Nguồn TQ</th>
                <th style="min-width:145px">Điểm Jev &amp; Quyết định</th>
                <th style="min-width:255px">6 Trụ cột Jev AI (/10)</th>
                <th>Giá bán &amp; Lượt bán</th>
                <th>Ngăn Kho hiện tại</th>
                <th>Thao tác nhanh</th>
              </tr>
            </thead>
            <tbody>
              ${items.map((p) => {
                const rBadge = rankMedals[p.rank]
                  ? `<strong style="font-size:14px;color:${p.rank === 1 ? "#fde047" : p.rank === 2 ? "#e2e8f0" : "#fdba74"}">${rankMedals[p.rank]}</strong>`
                  : `<strong style="color:#93c5fd">#${p.rank}</strong>`;
                const tierCls = p.decision_tier === "strong_pick" ? "green" : p.decision_tier === "maybe" ? "blue" : "";
                const cnKw = p.desk300?.cn_1688_keyword || "";
                return `
                  <tr>
                    <td>${rBadge}</td>
                    <td>
                      <div style="display:flex;gap:9px;align-items:flex-start">
                        ${p.image_url ? `<img src="${esc(p.image_url)}" alt="" style="width:48px;height:48px;object-fit:cover;border-radius:6px;border:1px solid var(--border);flex-shrink:0" />` : ""}
                        <div>
                          <a href="${esc(p.url || "#")}" target="_blank" style="font-weight:600;color:#93c5fd">${esc(p.desk300?.seo_title || p.title)}</a>
                          <div style="font-size:11px;color:var(--muted);margin-top:2px">
                            <span class="badge">${esc(p.platform_market_label)}</span>
                            ${p.is_overseas ? '<span class="badge gold">✈️ Quốc tế</span>' : ""}
                            <span>${esc(p.industry_icon)} ${esc(p.industry_label)}</span>
                            ${p.shop_name ? `· Shop: <strong>${esc(p.shop_name)}</strong>` : ""}
                          </div>
                          ${cnKw ? `<div style="font-size:11px;color:#fcd34d;margin-top:2px">🇨🇳 1688: <code>${esc(cnKw)}</code></div>` : ""}
                        </div>
                      </div>
                    </td>
                    <td>
                      <div><span class="badge gold" style="font-size:13.5px;font-weight:800">🤖 ${p.jev_score}/10</span></div>
                      <div style="margin-top:4px"><span class="badge ${tierCls}">${esc(p.decision_label)}</span></div>
                      <div style="font-size:11px;color:#6ee7b7;margin-top:3px">Xác suất nhập test: <strong>${p.import_test_prob_pct}%</strong></div>
                      ${p.strongest_pillar_label ? `<div style="font-size:10.5px;color:var(--muted);margin-top:2px">Mạnh nhất: ${esc(p.strongest_pillar_label)}</div>` : ""}
                    </td>
                    <td>${renderJevPillarBarsHtml(p.pillars, rk)}</td>
                    <td style="font-size:12px">
                      <div><strong>${fmtPriceDual(p)}</strong></div>
                      <div style="margin-top:2px">Đã bán: <strong style="color:#6ee7b7">${Number(p.sold_count || 0).toLocaleString("vi-VN")}</strong></div>
                      ${p.sold_30d > 0 ? `<div style="font-size:11px;color:#fcd34d">30 ngày: ${Number(p.sold_30d).toLocaleString("vi-VN")}</div>` : ""}
                      ${p.stock > 0 ? `<div style="font-size:11px;color:var(--muted)">Tồn kho: ${p.stock}</div>` : ""}
                    </td>
                    <td>
                      <select data-inline-pid="${p.id}" data-inline-field="bucket" style="font-size:11.5px;padding:4px 6px;max-width:155px">
                        ${bucketOpts.map(([bk, bl]) => `<option value="${bk}" ${p.bucket === bk ? "selected" : ""}>${esc(bl)}</option>`).join("")}
                      </select>
                    </td>
                    <td>
                      <div class="row" style="gap:4px">
                        <button class="btn btn-sm btn-gold" data-action="prod-set-status" data-id="${p.id}" data-st="nhap_test" title="Chuyển sang Đang nhập / Test bán">🚀 Nhập test</button>
                        <button class="btn btn-sm" data-action="prod-300desk" data-id="${p.id}" title="Đưa qua 300+desk chuẩn hoá SEO & dịch 1688">🤖 300+desk</button>
                        <button class="btn btn-sm" data-action="prod-find-cn" data-id="${p.id}" data-title="${esc(cnKw || p.title)}" title="Tìm xưởng gốc 1688 / Pinduoduo / Taobao">🇨🇳 Nguồn TQ</button>
                        <button class="btn btn-sm btn-pri" data-action="prod-dossier" data-id="${p.id}">📊 Hồ sơ</button>
                        <button class="btn btn-sm" data-action="jr-rescore-one" data-id="${p.id}" title="Chấm lại điểm Jev AI">🔄</button>
                      </div>
                    </td>
                  </tr>`;
              }).join("")}
            </tbody>
          </table>
        </div>`
      : `<div style="color:var(--muted);padding:12px">Không có sản phẩm nào khớp bộ lọc. Bạn có thể bấm <strong>"🤖 Chấm Jev Top 15 SP bán chạy chưa chấm"</strong> ở góc phải trên để bổ sung điểm Jev!</div>`;
  }

  // --- PART 1.1B: LUỒNG XỬ LÝ SẢN PHẨM 300+DESK (OPi SOCKS5) -> JEV DECISION ---
  function renderDeskGatewayBanner(st) {
    const html = st?.ok
      ? `<div class="row" style="justify-content:space-between">
          <div>
            <span class="badge green">🟢 300+desk SẴN SÀNG (FAIL-CLOSED)</span>
            <strong style="margin-left:6px">${esc(st.service || "desk300plus-gateway")}</strong> ·
            <code>${esc(st.gateway_url)}</code> &rarr; <code>${esc(st.socks_proxy)}</code>
            ${st.dsh_script_exists ? '<span class="badge blue" style="margin-left:6px">DSH Script OK</span>' : ""}
          </div>
          <span style="font-size:12px;color:#6ee7b7">0% gọi trực tiếp từ IP Mac · 0% bịa số liệu</span>
         </div>`
      : `<div>
          <span class="badge red">🔴 FAIL-CLOSED: 300+desk TẠM NGẮT</span>
          <strong style="margin-left:6px;color:#fca5a5">${esc(st?.error || "Gateway 300+desk hoặc SOCKS5 OrangePi5 Pro chưa phản hồi")}</strong>
          <div style="font-size:12px;color:var(--muted);margin-top:4px">Hệ thống tuyệt đối không tự chuyển sang IP Mac trực tiếp để bảo vệ an toàn hạ tầng.</div>
         </div>`;
    const b1 = document.getElementById("desk300GatewayBanner");
    if (b1) b1.innerHTML = html;
    const b2 = document.getElementById("desk300SettingsStatusBox");
    if (b2) b2.innerHTML = html;
  }

  function renderDeskRunDetail(run) {
    const box = document.getElementById("deskActiveRunBox");
    if (!box || !run) return;
    const steps = run.steps || [];
    const results = run.results || [];
    box.innerHTML = `
      <div class="card" style="border-color:rgba(56,189,248,0.5);background:#081222">
        <div class="row" style="justify-content:space-between;margin-bottom:8px">
          <div>
            <span class="badge blue" style="font-size:13px">Lô #${esc(run.nnn_code)}</span>
            <strong style="margin-left:6px">${esc(run.title)}</strong>
            ${statusBadgeHtml(run.status)}
          </div>
          <div class="row">
            <span class="badge gold">🔥 ${run.strong_pick_count} strong_pick</span>
            <span class="badge green">🟡 ${run.maybe_count} maybe</span>
            <span class="badge">⚪ ${run.pass_count} pass</span>
            <button class="btn btn-sm btn-pri" data-action="jump-kho-all">🗂 Xem trong Kho SP</button>
          </div>
        </div>

        <div style="font-size:12px;color:#93c5fd;margin-bottom:8px">
          📂 Gói CSV xuất ra: <code>local-data/exports/300-desk/${esc(run.export_dir)}/</code> (<code>products.csv</code>, <code>jev_decisions.csv</code>, <code>egress_meta.json</code>)
        </div>

        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:6px;margin-bottom:12px">
          ${steps.map((s) => `
            <div style="padding:7px 9px;border-radius:8px;background:#060d18;border:1px solid var(--border);font-size:12px">
              <div><strong>${s.status === "completed" ? "✅" : s.status === "failed" ? "❌" : "⏳"} ${esc(s.label)}</strong></div>
              <div style="color:var(--muted);margin-top:2px;font-size:11.3px">${esc(s.detail || "")}</div>
            </div>`).join("")}
        </div>

        ${
          results.length
            ? `<table class="tbl">
                <thead><tr><th>#</th><th>Quyết định Jev</th><th>Tên chuẩn SEO &amp; Góc Video (300+desk)</th><th>Giá &amp; Đã bán</th><th>Từ khoá Xưởng 1688</th><th>Thao tác</th></tr></thead>
                <tbody>
                  ${results.map((r) => `
                    <tr>
                      <td>#${r.id}</td>
                      <td>
                        <span class="badge ${r.decision_tier === "strong_pick" ? "gold" : r.decision_tier === "maybe" ? "green" : ""}">${esc(r.decision_label)}</span>
                        <div style="font-size:11.5px;margin-top:3px">🎯 Jev: <strong>${r.jev_score ?? "—"}/10</strong></div>
                      </td>
                      <td>
                        <a href="${esc(r.url || "#")}" target="_blank" style="color:#e2e8f0;font-weight:700">${esc(r.seo_title || r.raw_title)}</a>
                        <div style="font-size:11.5px;color:#93c5fd;margin-top:2px">🎁 Combo: ${esc(r.combo_strategy || "")}</div>
                        <div style="font-size:11.3px;color:var(--muted);margin-top:2px">🎬 ${(r.video_angles || []).slice(0, 2).map((a) => esc(a)).join(" · ")}</div>
                      </td>
                      <td>
                        <div><strong>${r.price_vnd > 0 ? vnd(r.price_vnd) : "Chưa lấy"}</strong></div>
                        <div style="font-size:11.5px;color:var(--muted)">Đã bán: ${Number(r.sold_count || 0).toLocaleString("vi-VN")}</div>
                      </td>
                      <td><code style="color:#fcd34d;font-size:13px">${esc(r.cn_1688_keyword)}</code></td>
                      <td class="row">
                        <button class="btn btn-sm btn-gold" data-action="prod-find-cn" data-id="${r.id}" data-title="${esc(r.cn_1688_keyword)}">🇨🇳 Tìm 1688</button>
                        <button class="btn btn-sm btn-pri" data-action="prod-dossier" data-id="${r.id}">📊 Mở</button>
                      </td>
                    </tr>`).join("")}
                </tbody>
              </table>`
            : ""
        }
      </div>`;
  }

  async function loadDesk300Tab() {
    const data = await api("/api/desk300/runs");
    renderDeskGatewayBanner(data.gateway);
    const runs = data.runs || [];
    if (runs.length && !document.getElementById("deskActiveRunBox").innerHTML) {
      renderDeskRunDetail(runs[0]);
    }
    const hbox = document.getElementById("deskRunsHistoryBox");
    if (hbox) {
      hbox.innerHTML = runs.length
        ? `<table class="tbl">
            <thead><tr><th>Mã NNN</th><th>Thời gian</th><th>Lô xử lý 300+desk &rarr; Jev</th><th>Trạng thái</th><th>Kết quả Jev</th><th>Thư mục CSV</th><th>Chi tiết</th></tr></thead>
            <tbody>
              ${runs.map((r) => `
                <tr>
                  <td><strong style="color:#fcd34d">#${esc(r.nnn_code)}</strong></td>
                  <td>${fmtTime(r.created_at)}</td>
                  <td><strong>${esc(r.title)}</strong></td>
                  <td>${statusBadgeHtml(r.status)}</td>
                  <td>🔥 ${r.strong_pick_count} · 🟡 ${r.maybe_count} · ⚪ ${r.pass_count}</td>
                  <td><code>${esc(r.export_dir)}</code></td>
                  <td><button class="btn btn-sm btn-pri" data-action="desk300-open-run" data-id="${esc(r.run_id)}">🔍 Mở bảng</button></td>
                </tr>`).join("")}
            </tbody>
           </table>`
        : `<div style="color:var(--muted)">Chưa có lô xử lý 300+desk nào. Bấm nút <strong>"🚀 Chạy Luồng 300+desk &rarr; Jev cho Kho SP Ngay"</strong> ở trên!</div>`;
    }
  }

  // --- PART 1.2: KEYWORD RESEARCH & SHOPEE SEARCH FILTERS --------------------
  function collectKeywordShopeeFilters() {
    const platVal = document.getElementById("kwPlatform")?.value || "";
    if (!platVal.startsWith("shopee")) return undefined;
    return {
      shipped_from: document.getElementById("kwShippedFrom")?.value || "",
      sort_by: document.getElementById("kwSortBy")?.value || "relevancy",
      min_price: Number(document.getElementById("kwMinPrice")?.value || 0) || undefined,
      max_price: Number(document.getElementById("kwMaxPrice")?.value || 0) || undefined,
      min_rating: Number(document.getElementById("kwMinRating")?.value || 0) || undefined,
      official_shop_only: Boolean(document.getElementById("kwMallOnly")?.checked),
      preferred_seller_only: Boolean(document.getElementById("kwPreferredOnly")?.checked),
      with_video_only: Boolean(document.getElementById("kwVideoOnly")?.checked),
      discounted_only: Boolean(document.getElementById("kwDiscountOnly")?.checked),
      free_shipping_only: Boolean(document.getElementById("kwFreeshipOnly")?.checked),
    };
  }

  function collectHuntShopeeFilters() {
    const sf = {
      shipped_from: document.getElementById("huntShopeeShippedFrom")?.value || "",
      sort_by: document.getElementById("huntShopeeSortBy")?.value || "relevancy",
      official_shop_only: Boolean(document.getElementById("huntShopeeMallOnly")?.checked),
      preferred_seller_only: Boolean(document.getElementById("huntShopeePreferredOnly")?.checked),
      with_video_only: Boolean(document.getElementById("huntShopeeVideoOnly")?.checked),
    };
    const hasActive = sf.shipped_from || sf.sort_by !== "relevancy" || sf.official_shop_only || sf.preferred_seller_only || sf.with_video_only;
    return hasActive ? sf : undefined;
  }

  function collectDeskShopeeFilters() {
    const sf = {
      shipped_from: document.getElementById("deskShopeeShippedFrom")?.value || "",
      sort_by: document.getElementById("deskShopeeSortBy")?.value || "relevancy",
    };
    return sf.shipped_from || sf.sort_by !== "relevancy" ? sf : undefined;
  }

  function formatShopeeFilterChipsHtml(sf) {
    if (!sf || typeof sf !== "object") return "";
    const badges = [];
    if (sf.shipped_from) badges.push(`<span class="badge gold">✈️ Nơi gửi: ${esc(sf.shipped_from)}</span>`);
    if (sf.sort_by && sf.sort_by !== "relevancy") badges.push(`<span class="badge blue">↕️ Sắp xếp: ${esc(sf.sort_by)}</span>`);
    if (sf.min_price || sf.max_price) badges.push(`<span class="badge">🏷️ Giá: ${sf.min_price ? vnd(sf.min_price) : "0đ"} – ${sf.max_price ? vnd(sf.max_price) : "∞"}</span>`);
    if (sf.min_rating) badges.push(`<span class="badge">⭐ ≥ ${sf.min_rating} sao</span>`);
    if (sf.official_shop_only) badges.push(`<span class="badge red">🏬 Shopee Mall</span>`);
    if (sf.preferred_seller_only) badges.push(`<span class="badge gold">⭐ Yêu Thích</span>`);
    if (sf.with_video_only) badges.push(`<span class="badge green">🎬 Có Video</span>`);
    if (sf.discounted_only) badges.push(`<span class="badge">🏷️ Giảm giá</span>`);
    if (sf.free_shipping_only) badges.push(`<span class="badge">🚚 Freeship</span>`);
    return badges.length ? `<div class="row" style="margin-bottom:8px;gap:6px"><strong>Bộ lọc Shopee đã áp dụng:</strong> ${badges.join("")}</div>` : "";
  }

  function renderKeywordResult(res) {
    const s = res.summary_stats || {};
    const jev = s.jev_evaluation;
    const sfHtml = formatShopeeFilterChipsHtml(s.shopee_filters);
    const html = `
      <div class="card">
        <div class="row" style="justify-content:space-between;margin-bottom:8px">
          <h3 style="margin:0">📊 Kết quả Từ khoá: "${esc(res.keyword)}" (${esc(res.channel_label || res.platform)}) · <code>${esc(s.source_used || "")}</code></h3>
          <button class="btn btn-sm btn-pri" data-action="jump-kho-pending">📝 Sang Kho Phân loại (${(res.saved_product_ids || []).length} SP đã lưu)</button>
        </div>
        ${sfHtml}
        <div class="kpi-grid">
          <div class="kpi"><div class="lbl">Tổng lượng SP trên từ khoá</div><div class="val">${esc(s.total_products)}</div></div>
          <div class="kpi"><div class="lbl">Tổng lượt bán mẫu trang 1</div><div class="val green">${Number(s.total_sold_sample || 0).toLocaleString("vi-VN")}</div></div>
          <div class="kpi"><div class="lbl">Giá bán Trung bình / Trung vị</div><div class="val">${vnd(s.avg_price_vnd)} / ${vnd(s.median_price_vnd)}</div></div>
          <div class="kpi"><div class="lbl">✈️ Shop Quốc tế (Nước ngoài)</div><div class="val gold">${s.overseas_share_pct ?? 0}% (${s.overseas_count ?? 0}/${s.sampled_count ?? 0} SP)</div></div>
          <div class="kpi"><div class="lbl">Tỷ lệ Mall / Top 3 Shop chiếm</div><div class="val">${s.mall_share_pct}% / ${s.top3_shop_concentration_pct}%</div></div>
          <div class="kpi"><div class="lbl">Điểm Cơ hội Jev AI</div><div class="val green">${jev ? jev.opportunity_score_10 + " / 10" : "Chưa chấm"}</div></div>
        </div>
        <table class="tbl">
          <thead><tr><th>Tên sản phẩm</th><th>Shop &amp; Nơi vận chuyển</th><th>Giá bán</th><th>Đã bán</th><th>Doanh số ước tính</th></tr></thead>
          <tbody>
            ${(res.items || []).map((it) => `
              <tr>
                <td>
                  <a href="${esc(it.url)}" target="_blank" style="color:#93c5fd">${esc(it.title)}</a>
                  ${it.is_mall ? '<span class="badge red">Mall</span>' : ""}
                  ${it.is_preferred ? '<span class="badge gold">⭐ Yêu thích</span>' : ""}
                </td>
                <td>
                  <div><strong>${esc(it.shop_name || "—")}</strong></div>
                  ${
                    it.is_overseas
                      ? '<span class="badge gold">✈️ Nước ngoài (Shop Quốc tế)</span>'
                      : it.shop_location
                        ? `<span class="badge">📍 ${esc(it.shop_location)}</span>`
                        : ""
                  }
                </td>
                <td>${fmtPriceDual(it)}</td>
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
          <thead><tr><th>Từ khoá &amp; Bộ lọc</th><th>Sàn</th><th>Tổng SP</th><th>Lượt bán mẫu</th><th>✈️ Nước ngoài</th><th>Giá TB</th><th>Mall %</th><th>Điểm Jev</th><th>Thời gian</th></tr></thead>
          <tbody>${rows.map((r) => {
            const st = r.summary_stats || {};
            const sf = st.shopee_filters || {};
            return `
            <tr>
              <td>
                <strong>${esc(r.keyword)}</strong>
                ${sf.shipped_from ? `<span class="badge gold" style="margin-left:4px">✈️ ${esc(sf.shipped_from)}</span>` : ""}
                ${sf.sort_by && sf.sort_by !== "relevancy" ? `<span class="badge blue" style="margin-left:4px">${esc(sf.sort_by)}</span>` : ""}
              </td>
              <td><span class="badge blue">${esc(r.channel_label || r.platform)}</span></td>
              <td>${r.total_products}</td>
              <td>${Number(r.total_sold_sample || 0).toLocaleString("vi-VN")}</td>
              <td>${st.overseas_share_pct != null ? `<strong style="color:#fcd34d">${st.overseas_share_pct}%</strong>` : "—"}</td>
              <td>${vnd(r.avg_price_vnd)}</td>
              <td>${r.mall_share_pct}%</td>
              <td>${r.jev_opportunity_score != null ? `<span class="badge green">${r.jev_opportunity_score}/10</span>` : "—"}</td>
              <td>${fmtTime(r.created_at)}</td>
            </tr>`;
          }).join("")}
          </tbody>
        </table>`
      : `<div style="color:var(--muted)">Chưa có lịch sử tra cứu từ khoá.</div>`;
  }

  // --- PART 1.3: WATCHES & DIFF ----------------------------------------------
  async function loadWatches() {
    const data = await api("/api/watches");
    const ws = data.watches || [];
    const ar = data.auto_rescan || {};
    const barEl = document.getElementById("watchesAutoRescanBar");
    if (barEl) {
      barEl.innerHTML = ar.paused
        ? `<div class="row" style="justify-content:space-between;padding:10px 12px;border-radius:8px;background:rgba(245,158,11,0.12);border:1px solid rgba(245,158,11,0.45)">
            <div>
              <strong style="color:#fcd34d">⏸ ĐANG TẠM DỪNG TOÀN BỘ QUÉT LẠI TỰ ĐỘNG</strong>
              <span style="font-size:12.5px;color:var(--muted);margin-left:8px">(${ar.paused_watches_count || 0} mục đang giữ nguyên, chỉ quét khi bạn bấm tay hoặc báo bật lại)</span>
            </div>
            <button class="btn btn-sm btn-pri" data-action="watch-resume-all">▶️ Bật lại Quét định kỳ</button>
          </div>`
        : `<div class="row" style="justify-content:space-between;padding:10px 12px;border-radius:8px;background:rgba(16,185,129,0.10);border:1px solid rgba(16,185,129,0.35)">
            <div>
              <strong style="color:#6ee7b7">🟢 Đang bật quét định kỳ tự động</strong>
              <span style="font-size:12.5px;color:var(--muted);margin-left:8px">(Đang chạy: ${ar.active_watches_count || 0} mục · Tạm dừng: ${ar.paused_watches_count || 0} mục)</span>
            </div>
            <button class="btn btn-sm btn-danger" data-action="watch-pause-all">⏸ Tạm dừng toàn bộ Quét lại</button>
          </div>`;
    }
    document.getElementById("watchesListBox").innerHTML = ws.length
      ? `<table class="tbl">
          <thead><tr><th>Loại</th><th>Sàn</th><th>Mục tiêu theo dõi</th><th>Trạng thái</th><th>Kết quả lần check gần nhất</th><th>Check lúc</th><th>Thao tác</th></tr></thead>
          <tbody>${ws.map((w) => {
            const sm = w.last_summary || {};
            const wsf = sm.shopee_filters || {};
            const isPaused = w.status === "paused" || ar.paused;
            return `<tr>
              <td>
                <span class="badge ${w.is_special ? "gold" : "blue"}">${w.is_special ? "⭐ ĐẶC BIỆT · " : ""}${esc(w.watch_type.toUpperCase())}</span>
              </td>
              <td><span class="badge blue">${esc(w.channel_label || w.platform)}</span></td>
              <td>
                <strong>${esc(w.title)}</strong>
                ${wsf.shipped_from ? `<span class="badge gold" style="margin-left:4px">✈️ ${esc(wsf.shipped_from)}</span>` : ""}
                <div style="font-size:11.5px;color:var(--muted)">${esc(w.target_key)}</div>
              </td>
              <td>${isPaused ? `<span class="badge gold">⏸ Tạm dừng</span>` : `<span class="badge green">🟢 Định kỳ ${w.interval_hours}h</span>`}</td>
              <td>${esc(sm.headline || "Chưa chạy lần đầu")}</td>
              <td>${fmtTime(w.last_checked_at)}</td>
              <td class="row">
                <button class="btn btn-sm btn-pri" data-action="watch-check" data-id="${esc(w.watch_id)}">🔄 Check &amp; So sánh</button>
                <button class="btn btn-sm" data-action="watch-toggle" data-id="${esc(w.watch_id)}" data-next="${w.status === "paused" ? "resume" : "pause"}">${w.status === "paused" ? "▶️ Bật" : "⏸ Dừng"}</button>
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
    if (subKey === "overseas") return Boolean(p.is_overseas);
    if (subKey === "jev7") return p.jev_score != null && Number(p.jev_score) >= 7.0;
    if (subKey === "has_sold") return Number(p.sold_count || 0) > 0;
    if (subKey === "has_cost") return Number(p.cost_vnd || 0) > 0;
    return p.status === subKey;
  }

  function renderProductCardHtml(p, ownShops) {
    const ec = p.economics || {};
    const d3 = p.desk300 || null;
    const pillars = (p.jev_detail || {}).pillars || {};
    const cls = d3?.decision_tier === "strong_pick" || p.jev_score >= 7.2 ? "is-gold" : p.jev_score >= 6.2 ? "is-green" : "";

    const pillarsHtml = Object.keys(pillars).length
      ? `<div class="pillars">${Object.entries(PILLAR_LABELS)
          .map(([k, lbl]) => `<div>${esc(lbl)}<b>${pillars[k] ?? "–"}</b></div>`)
          .join("")}</div>`
      : "";

    const desk300Html = d3
      ? `<div style="background:#071426;border:1px solid rgba(56,189,248,0.35);border-radius:8px;padding:7px 8px;font-size:11.8px">
          <div class="row" style="justify-content:space-between;margin-bottom:3px">
            <span class="badge ${d3.decision_tier === "strong_pick" ? "gold" : d3.decision_tier === "maybe" ? "green" : ""}">${esc(d3.decision_label || d3.decision_tier)}</span>
            <span style="color:#7dd3fc;font-size:11px">300+desk #${esc(d3.nnn_code || "")}</span>
          </div>
          ${d3.seo_title ? `<div style="color:#e2e8f0;font-weight:600">✨ SEO: ${esc(d3.seo_title)}</div>` : ""}
          ${d3.cn_1688_keyword ? `<div style="color:#fcd34d;margin-top:2px">🇨🇳 Từ khoá 1688: <code>${esc(d3.cn_1688_keyword)}</code></div>` : ""}
          ${d3.combo_strategy ? `<div style="color:#93c5fd;margin-top:2px">🎁 Combo: ${esc(d3.combo_strategy)}</div>` : ""}
         </div>`
      : "";

    return `
      <div class="pcard ${cls}">
        <div class="pcard-top">
          ${p.image_url ? `<img class="pcard-img" src="${esc(p.image_url)}" alt="" loading="lazy" />` : `<div class="pcard-img" style="display:flex;align-items:center;justify-content:center;font-size:26px">${p.industry_icon || "📦"}</div>`}
          <div style="flex:1;min-width:0">
            <div class="row" style="justify-content:space-between">
              <label style="font-size:12px;color:var(--muted);cursor:pointer">
                <input type="checkbox" data-action="toggle-select-pid" data-id="${p.id}" ${SELECTED_PIDS.has(p.id) ? "checked" : ""}/>
                #${p.id} · ${esc(p.platform_market_label || p.platform.toUpperCase())}
              </label>
              <span class="badge ${p.jev_score >= 7 ? "gold" : p.jev_score != null ? "green" : ""}">${p.jev_score != null ? `🎯 Jev ${p.jev_score}/10` : "⏳ Chưa chấm Jev"}</span>
            </div>
            <div style="font-weight:600;margin:4px 0;line-height:1.38">
              <a href="${esc(p.url || "#")}" target="_blank" style="color:var(--txt);text-decoration:none">${esc(p.title)}</a>
            </div>
            <div class="row" style="gap:5px">
              <span class="badge blue">${esc(p.industry_icon)} ${esc(p.industry_label)}</span>
              <span class="badge green">${esc(p.bucket_icon)} ${esc(p.bucket_label)}</span>
              ${p.is_overseas ? '<span class="badge gold">✈️ Nước ngoài</span>' : p.shop_location ? `<span class="badge">📍 ${esc(p.shop_location)}</span>` : ""}
              ${p.is_mall ? '<span class="badge red">Mall</span>' : ""}
              ${p.is_preferred ? '<span class="badge gold">⭐ Yêu thích</span>' : ""}
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
          <div>🏷️ Giá bán<strong>${fmtPriceDual(p)}</strong></div>
          <div>🇨🇳 Giá vốn<strong>${p.cost_vnd > 0 ? vnd(p.cost_vnd) : "Chưa ghép"}</strong></div>
          <div>📦 Lượt bán<strong>${Number(p.sold_count || 0).toLocaleString("vi-VN")}</strong></div>
          <div>💰 Lãi/đơn<strong style="color:${(ec.net_profit_per_order_vnd || 0) > 0 ? "#6ee7b7" : "var(--muted)"}">${p.cost_vnd > 0 && p.price_vnd > 0 ? vnd(ec.net_profit_per_order_vnd) : "—"}</strong></div>
        </div>

        ${pillarsHtml}
        ${desk300Html}

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
          <select data-inline-pid="${p.id}" data-inline-field="assigned_shop_id" title="Gắn vào Shop của tôi" style="padding:4px 6px;font-size:11.8px">
            <option value="">🏠 Chưa gắn Shop của tôi</option>
            ${ownShops.map((s) => `<option value="${esc(s.shop_id)}" ${p.assigned_shop_id === s.shop_id ? "selected" : ""}>${esc(s.platform_icon || "🏠")} ${esc(s.shop_name)}</option>`).join("")}
          </select>
          <select data-inline-pid="${p.id}" data-inline-field="assigned_campaign_id" title="Gắn vào Chiến dịch Ngành hàng" style="padding:4px 6px;font-size:11.8px">
            <option value="">🚀 Chưa gắn Chiến dịch</option>
            ${ALL_CAMPAIGNS.map((c) => `<option value="${esc(c.campaign_id)}" ${p.assigned_campaign_id === c.campaign_id ? "selected" : ""}>🚀 ${esc(c.name)}</option>`).join("")}
          </select>
        </div>

        <div class="row" style="gap:5px">
          <button class="btn btn-sm btn-gold" data-action="prod-300desk" data-id="${p.id}" title="Đưa SP qua 300+desk (OPi SOCKS5) đặt Tên SEO, dịch 1688 & Jev chốt">🤖 300+desk</button>
          <button class="btn btn-sm" data-action="prod-enrich" data-id="${p.id}" title="Lấy Giá bán, Lượt bán (Apify #1 -> Treg #2)">🔄 Lấy Giá</button>
          <button class="btn btn-sm btn-pri" data-action="prod-score-jev" data-id="${p.id}">🎯 Jev</button>
          <button class="btn btn-sm btn-gold" data-action="prod-find-cn" data-id="${p.id}" data-title="${esc(d3?.cn_1688_keyword || p.title)}">🇨🇳 1688</button>
          <button class="btn btn-sm" data-action="prod-dossier" data-id="${p.id}">📊 Lãi</button>
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

  // --- PART 1.5: SHOP CỦA TÔI (MY SHOPS: TIKTOK · SHOPEE · FACEBOOK FANPAGE) ---
  function resetMyShopForm() {
    document.getElementById("msEditId").value = "";
    document.getElementById("msFormHeading").textContent = "➕ Thêm Shop TikTok · Shopee · Facebook Fanpage mới";
    document.getElementById("msUrl").value = "";
    document.getElementById("msPlatform").value = "tiktok_shop_vn";
    document.getElementById("msName").value = "";
    document.getElementById("msStatus").value = "active";
    if (document.getElementById("msIndustry")) document.getElementById("msIndustry").value = "gia_dung";
    document.getElementById("msFee").value = "11.5";
    document.getElementById("msNicheTags").value = "";
    document.getElementById("msNote").value = "";
    document.getElementById("btnSaveMyShop").textContent = "💾 Lưu vào Shop của tôi";
    document.getElementById("btnCancelMyShopEdit").style.display = "none";
    MY_SHOP_SELECTED_CMPS.clear();
    renderMyShopCampaignPicker();
  }

  function editMyShop(shop) {
    document.getElementById("msEditId").value = shop.shop_id;
    document.getElementById("msFormHeading").textContent = `✏️ Đang sửa: ${shop.shop_name}`;
    document.getElementById("msUrl").value = shop.shop_url || shop.handle || "";
    document.getElementById("msPlatform").value = shop.channel_code || shop.platform || "shopee_vn";
    document.getElementById("msName").value = shop.shop_name || "";
    document.getElementById("msStatus").value = shop.status || "active";
    if (document.getElementById("msIndustry")) document.getElementById("msIndustry").value = shop.industry || "gia_dung";
    document.getElementById("msFee").value = shop.platform_fee_pct ?? 0;
    document.getElementById("msNicheTags").value = (shop.niche_tags || []).join(", ");
    document.getElementById("msNote").value = shop.note || "";
    document.getElementById("btnSaveMyShop").textContent = "💾 Lưu cập nhật Shop";
    document.getElementById("btnCancelMyShopEdit").style.display = "inline-flex";
    MY_SHOP_SELECTED_CMPS = new Set(shop.campaign_ids || []);
    renderMyShopCampaignPicker();
    document.getElementById("myShopFormCard")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  async function loadMyShops() {
    const q = document.getElementById("msSearchQ")?.value || "";
    const qs = new URLSearchParams({ platform: MY_SHOPS_FILTER_PLAT, q });
    const data = await api(`/api/my-shops?${qs}`);
    const shops = data.shops || [];
    const cnts = data.counts || {};
    const byPlat = cnts.own_by_platform || {};

    const totalAssigned = ALL_SHOPS
      .filter((s) => s.role === "own_shop")
      .reduce((acc, s) => acc + Number(s.assigned_products_count || 0), 0);

    document.getElementById("myShopsKpiStrip").innerHTML = `
      <div class="kpi"><div class="lbl">🏠 Tổng Shop của tôi</div><div class="val sky">${cnts.own_count || 0}</div></div>
      <div class="kpi"><div class="lbl">🛒 TikTok Shop &amp; Kênh TT</div><div class="val">${(byPlat.tiktok_shop || 0) + (byPlat.tiktok_channel || 0)}</div></div>
      <div class="kpi"><div class="lbl">🛍 Gian hàng Shopee</div><div class="val gold">${byPlat.shopee || 0}</div></div>
      <div class="kpi"><div class="lbl">📘 Facebook Fanpage</div><div class="val green">${byPlat.facebook_fanpage || 0}</div></div>
      <div class="kpi"><div class="lbl">📦 SP đang gắn vào Shop</div><div class="val green">${totalAssigned}</div></div>
    `;

    document.getElementById("msTotalLbl").textContent = shops.length;

    // Highlight active platform filter chip
    document.querySelectorAll("#msPlatFilterChips .chip").forEach((ch) => {
      ch.classList.toggle("active", (ch.dataset.plat || "") === MY_SHOPS_FILTER_PLAT);
    });

    const cmpNameMap = Object.fromEntries(ALL_CAMPAIGNS.map((c) => [c.campaign_id, c.name]));

    document.getElementById("myShopsListBox").innerHTML = shops.length
      ? shops.map((s) => {
          const stBadgeCls = s.status === "active" ? "green" : s.status === "warming" ? "gold" : "";
          const tagsHtml = (s.niche_tags || []).length
            ? `<div class="row" style="gap:4px;margin-top:6px">${s.niche_tags.map((t) => `<span class="badge blue">#${esc(t)}</span>`).join("")}</div>`
            : "";
          const cmpsHtml = (s.campaign_ids || []).length
            ? `<div class="row" style="gap:4px;margin-top:5px">${s.campaign_ids.map((cid) => `<span class="badge gold">🚀 ${esc(cmpNameMap[cid] || cid)}</span>`).join("")}</div>`
            : "";
          return `
            <div style="border:1px solid var(--border);border-radius:10px;padding:12px;margin-bottom:10px;background:#091120">
              <div class="row" style="justify-content:space-between">
                <div class="row" style="gap:6px">
                  <span class="badge blue" style="font-size:12.5px">${esc(s.platform_icon || "🏠")} ${esc(s.platform_label || s.platform)}</span>
                  <span class="badge ${stBadgeCls}">${esc(s.status_label || s.status)}</span>
                  <span class="badge">${esc(s.industry_icon || "📦")} ${esc(s.industry_label)}</span>
                </div>
                <span style="font-size:12px;color:#6ee7b7;font-weight:600">📦 ${s.assigned_products_count || 0} SP đã gắn · Phí: ${s.platform_fee_pct}%</span>
              </div>

              <div style="margin-top:7px;font-size:15px;font-weight:700">${esc(s.shop_name)} ${s.handle ? `<span style="font-size:12px;font-weight:400;color:var(--muted)">(@${esc(s.handle)})</span>` : ""}</div>
              ${s.shop_url ? `<div style="margin-top:3px"><a href="${esc(s.shop_url)}" target="_blank" style="color:#93c5fd;font-size:12.5px">${esc(s.shop_url)}</a></div>` : ""}

              ${tagsHtml}
              ${cmpsHtml}
              ${s.note ? `<div style="margin-top:6px;font-size:12.5px;color:var(--muted)">📝 ${esc(s.note)}</div>` : ""}

              <div class="row" style="margin-top:10px;gap:6px">
                <button class="btn btn-sm btn-pri" data-action="ms-view-products" data-id="${esc(s.shop_id)}">📦 Xem SP của Shop (${s.assigned_products_count || 0})</button>
                <button class="btn btn-sm" data-action="ms-edit" data-id="${esc(s.shop_id)}">✏️ Sửa</button>
                ${
                  s.platform === "facebook_fanpage"
                    ? `<button class="btn btn-sm btn-blue" data-action="ms-spy-fanpage" data-name="${esc(s.shop_name)}">📢 Quét Ads Fanpage</button>`
                    : (s.platform === "shopee" || s.platform === "tiktok_shop") && (s.shop_url || s.handle)
                      ? `<button class="btn btn-sm btn-blue" data-action="shop-watch-from-vault" data-plat="${esc(s.platform)}" data-url="${esc(s.shop_url || s.handle)}" data-name="${esc(s.shop_name)}">🔭 Theo dõi SP</button>`
                      : ""
                }
                <button class="btn btn-sm btn-danger" data-action="ms-delete" data-id="${esc(s.shop_id)}">🗑 Xoá</button>
              </div>
            </div>`;
        }).join("")
      : `<div style="padding:18px;text-align:center;color:var(--muted);border:1px dashed var(--border);border-radius:10px">
          Chưa có <strong>Shop của tôi</strong> nào khớp bộ lọc.<br/>Hãy thêm <strong>TikTok Shop, Shopee hoặc Facebook Fanpage</strong> ở khung bên trái!
        </div>`;
  }

  async function loadShops() {
    const data = await api("/api/shops?role=competitor_shop");
    const compShops = data.shops || [];
    document.getElementById("shopsGridBox").innerHTML = compShops.length
      ? compShops.map((s) => `
          <div class="card">
            <div class="row" style="justify-content:space-between">
              <span class="badge gold">🎯 Shop đối thủ mẫu</span>
              <span class="badge blue">${esc(s.platform_icon || "🏪")} ${esc(s.platform_label || s.platform)}</span>
            </div>
            <h3 style="margin:8px 0 4px">${esc(s.shop_name)}</h3>
            <div style="font-size:12.5px;color:var(--muted)">Ngành: ${esc(s.industry_icon || "")} ${esc(s.industry_label)} ${s.note ? `· ${esc(s.note)}` : ""}</div>
            ${s.shop_url ? `<div style="margin-top:6px"><a href="${esc(s.shop_url)}" target="_blank" style="color:#93c5fd;font-size:12.5px">${esc(s.shop_url)}</a></div>` : ""}
            <div class="row" style="margin-top:10px">
              ${
                s.platform === "facebook_fanpage"
                  ? `<button class="btn btn-sm btn-blue" data-action="ms-spy-fanpage" data-name="${esc(s.shop_name)}">📢 Soi Ads Fanpage</button>`
                  : `<button class="btn btn-sm btn-pri" data-action="comp-shop-scan" data-plat="${esc(s.platform)}" data-url="${esc(s.shop_url || s.handle)}">🔎 Quét SP của Shop</button>
                     <button class="btn btn-sm btn-blue" data-action="shop-watch-from-vault" data-plat="${esc(s.platform)}" data-url="${esc(s.shop_url || s.handle)}" data-name="${esc(s.shop_name)}">🔭 Theo dõi</button>`
              }
              <button class="btn btn-sm btn-danger" data-action="shop-delete" data-id="${esc(s.shop_id)}">Xoá</button>
            </div>
          </div>`).join("")
      : `<div class="card" style="grid-column:1/-1;color:var(--muted)">Chưa có Shop / Fanpage đối thủ nào. Hãy thêm ở trên hoặc quét từ mục <strong>🏪 Quét SP theo Shop</strong>!</div>`;
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
      <div class="kpi"><div class="lbl">Đã gửi qua Telegram Bot</div><div class="val green">${k.telegram_notified || 0} / ${k.total || 0}</div></div>
      <div class="kpi"><div class="lbl">Đang chạy / Lỗi</div><div class="val gold">${k.running || 0} / ${k.failed || 0}</div></div>
      <div class="kpi"><div class="lbl">Tổng Chi phí API luỹ kế</div><div class="val">$${Number(k.total_cost_usd || 0).toFixed(4)}</div></div>
    `;

    const logs = hData.logs || [];
    document.getElementById("historyLogsBox").innerHTML = logs.length
      ? `<table class="tbl">
          <thead><tr><th>Mã GS</th><th>Phân hệ</th><th>Công việc / Job đã chạy</th><th>Trạng thái</th><th>Thời lượng &amp; Chi phí</th><th>Tóm tắt kết quả</th><th>Telegram Bot</th><th>Chi tiết</th></tr></thead>
          <tbody>${logs.map((l) => `
            <tr>
              <td><strong style="color:#7dd3fc">${esc(l.gs_code)}</strong></td>
              <td><span class="badge blue">${esc(l.module_label || l.module)}</span></td>
              <td><strong>${esc(l.title)}</strong><div style="font-size:11px;color:var(--muted)">${fmtTime(l.created_at)}</div></td>
              <td>${statusBadgeHtml(l.status)}</td>
              <td>${fmtDuration(l.duration_ms)} · $${Number(l.cost_usd || 0).toFixed(4)}</td>
              <td>${esc(l.summary)}</td>
              <td>
                <div>${l.telegram_notified_at ? `<span class="badge green">✅ Đã báo${l.telegram_message_id ? " #" + esc(l.telegram_message_id) : ""}</span>` : `<span class="badge gold">⏳ Chờ đẩy</span>`}</div>
                ${l.telegram_last_error ? `<div style="font-size:10px;color:#fca5a5;margin-top:2px">${esc(l.telegram_last_error)}</div>` : ""}
                <button class="btn btn-sm" style="margin-top:4px;padding:2px 6px;font-size:11px" data-action="hist-resend-tg" data-id="${esc(l.log_id)}">📨 Gửi lại</button>
              </td>
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

  // --- PART 1.1A: ECOSYSTEM & ACCESSORY PLAYBOOKS (XTEINK X4 & GOOJODOQ) -----
  function renderEcosystemDetail(col) {
    const box = document.getElementById("ecoActiveDetailBox");
    if (!box) return;
    if (!col) {
      box.innerHTML = `<div class="card" style="color:var(--muted)">Chưa có Danh mục Hệ sinh thái nào — hãy bấm chọn <strong>Mẫu 1 (Phụ kiện Xteink X4)</strong> hoặc <strong>Mẫu 2 (Phụ kiện Goojodoq)</strong> ở trên rồi chạy ngay!</div>`;
      return;
    }
    ACTIVE_ECO_ID = col.collection_id;
    const st = col.index_summary || {};
    const prods = col.products || [];
    const shops = col.tracked_shops || [];
    const cnItems = col.cn_items || [];
    const creators = col.creators || [];
    const videos = col.videos || [];
    const spWatchIds = new Set((col.special_watches || []).map((w) => w.linked_product_id).filter(Boolean));

    box.innerHTML = `
      <div class="card" style="border-color:rgba(16,185,129,0.5)">
        <div class="row" style="justify-content:space-between;margin-bottom:10px">
          <div>
            <h3 style="margin:0;color:#6ee7b7">📂 Danh mục Theo dõi: ${esc(col.name)} <span class="badge blue">Từ khoá gốc: ${esc(col.seed_keyword)}</span></h3>
            <div style="font-size:12px;color:var(--muted);margin-top:3px">
              🎯 Mục tiêu: ${esc(col.target_focus || "—")} · Lần cào gần nhất: <strong>${fmtTime(col.last_run_at)}</strong>
              ${col.daily_schedule_enabled ? ` · <span class="badge green">⏰ Tự động cào mới mỗi ${col.schedule_interval_hours}h (Kế tiếp: ${fmtTime(col.next_run_at)})</span>` : `<span class="badge">⏸ Đang tắt lịch tự động</span>`}
            </div>
          </div>
          <div class="row">
            <button class="btn btn-sm btn-pri" data-action="eco-check-daily" data-id="${esc(col.collection_id)}">🔄 Cào Check SP Mới &amp; Tồn Kho Ngay</button>
            <button class="btn btn-sm" data-action="eco-toggle-sched" data-id="${esc(col.collection_id)}" data-on="${col.daily_schedule_enabled ? "0" : "1"}">${col.daily_schedule_enabled ? "⏸ Tạm dừng lịch ngày" : "▶️ Bật lịch cào hàng ngày"}</button>
            <button class="btn btn-sm btn-danger" data-action="eco-delete" data-id="${esc(col.collection_id)}">🗑 Xoá</button>
          </div>
        </div>

        <div class="kpi-grid">
          <div class="kpi"><div class="lbl">📦 Tổng SP Sàn trong Index</div><div class="val sky">${prods.length}</div></div>
          <div class="kpi"><div class="lbl">⭐ SP Theo dõi Đặc biệt (Có bán / Tồn kho)</div><div class="val gold">${(col.special_watch_ids || []).length}</div></div>
          <div class="kpi"><div class="lbl">🏪 Shop Liên quan đang Theo dõi</div><div class="val green">${shops.length}</div></div>
          <div class="kpi"><div class="lbl">🇨🇳 Mẫu Phụ kiện Bổ sung / Thay thế (PDD·Taobao)</div><div class="val gold">${cnItems.length}</div></div>
          <div class="kpi"><div class="lbl">🎥 Creator &amp; Video Bán Hiệu Quả</div><div class="val green">${creators.length} Creator / ${videos.length} Video</div></div>
          <div class="kpi"><div class="lbl">🆕 SP Mới phát hiện lần check gần nhất</div><div class="val">${st.last_new_products_detected || 0} SP mới</div></div>
        </div>
      </div>

      <!-- 1. RELATED PRODUCTS + JEV SCORE + INVENTORY / RECENT SALES + SPECIAL WATCH -->
      <div class="card">
        <div class="row" style="justify-content:space-between;margin-bottom:8px">
          <h3 style="margin:0">1️⃣ ⭐ Sản phẩm Liên quan trên Shopee VN &amp; TikTokShop VN — Xếp hạng theo Lượt bán gần đây, Tồn kho &amp; Điểm Jev (${prods.length} SP)</h3>
          <button class="btn btn-sm" data-action="jump-tab" data-tab="watches">🔭 Mở Bảng Theo dõi Định kỳ</button>
        </div>
        ${
          prods.length
            ? `<div style="max-height:420px;overflow:auto;border:1px solid var(--border);border-radius:8px">
                <table class="tbl">
                  <thead><tr><th>#</th><th>Sản phẩm &amp; Tín hiệu Ưu tiên</th><th>Sàn &amp; Shop</th><th>Giá bán</th><th>Đã bán &amp; Gần đây</th><th>Tồn kho (Suy lượt bán)</th><th>Điểm Jev</th><th>Theo dõi Đặc biệt</th></tr></thead>
                  <tbody>
                    ${prods.map((p) => {
                      const rk = p.ecosystem_rank || {};
                      const isSp = spWatchIds.has(p.id);
                      return `
                        <tr>
                          <td>#${p.id}</td>
                          <td>
                            <div class="row" style="flex-wrap:nowrap">
                              ${p.image_url ? `<img src="${esc(p.image_url)}" style="width:38px;height:38px;border-radius:6px;object-fit:cover" alt="" />` : ""}
                              <div>
                                <a href="${esc(p.url || "#")}" target="_blank" style="color:#93c5fd;font-weight:700">${esc(p.title)}</a>
                                <div style="font-size:11.3px;color:#6ee7b7;margin-top:2px">📈 ${esc(rk.priority_reason || "")}</div>
                              </div>
                            </div>
                          </td>
                          <td>
                            <div><span class="badge blue">${esc(p.platform_market_label || p.platform)}</span></div>
                            <div style="font-size:11.5px;margin-top:2px">${esc(p.shop_name || "—")}</div>
                          </td>
                          <td><strong>${fmtPriceDual(p)}</strong></td>
                          <td>
                            <div>Tổng: <strong>${Number(p.sold_count || 0).toLocaleString("vi-VN")}</strong></div>
                            ${rk.recent_sold_signal > 0 ? `<span class="badge green">🔥 Gần đây: +${rk.recent_sold_signal}</span>` : ""}
                          </td>
                          <td>
                            ${p.stock > 0 ? `<div>Tồn: <strong>${Number(p.stock).toLocaleString("vi-VN")}</strong></div>` : '<span style="color:var(--muted)">Chưa báo tồn</span>'}
                            ${p.inferred_sold_from_stock > 0 ? `<span class="badge gold">📉 Giảm tồn: +${p.inferred_sold_from_stock} đơn</span>` : ""}
                          </td>
                          <td>${p.jev_score != null ? `<span class="badge ${p.jev_score >= 7 ? "gold" : "green"}">🎯 ${p.jev_score}/10</span>` : `<button class="btn btn-sm" data-action="prod-score-jev" data-id="${p.id}">Chấm Jev</button>`}</td>
                          <td>
                            ${isSp ? '<span class="badge gold">⭐ Đang Theo dõi Đặc biệt</span>' : `<button class="btn btn-sm btn-gold" data-action="prod-watch" data-id="${p.id}" data-plat="${esc(p.platform)}" data-url="${esc(p.url)}" data-title="${esc(p.title)}">+ Theo dõi</button>`}
                            <button class="btn btn-sm" data-action="prod-dossier" data-id="${p.id}">📊</button>
                          </td>
                        </tr>`;
                    }).join("")}
                  </tbody>
                </table>
               </div>`
            : `<div style="color:var(--muted)">Chưa có sản phẩm sàn nào trong danh mục này.</div>`
        }
      </div>

      <!-- 2. TRACKED RELATED SHOPS -->
      <div class="card">
        <h3 style="margin:0 0 8px">2️⃣ 🏪 Danh sách Shop Liên quan đang Bán (Đã đưa vào Kho &amp; Theo dõi SP mới của Shop: ${shops.length} Shop)</h3>
        ${
          shops.length
            ? `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:8px">
                ${shops.map((s) => `
                  <div style="padding:10px;border:1px solid var(--border);border-radius:8px;background:#081222">
                    <div class="row" style="justify-content:space-between">
                      <span class="badge blue">${esc(s.platform_label || s.platform)}</span>
                      <span class="badge gold">🔭 Đang theo dõi Shop</span>
                    </div>
                    <div style="font-weight:700;margin-top:5px">${esc(s.shop_name)}</div>
                    ${s.shop_url ? `<div><a href="${esc(s.shop_url)}" target="_blank" style="font-size:11.5px;color:#93c5fd">${esc(s.shop_url)}</a></div>` : ""}
                    <div class="row" style="margin-top:8px">
                      <button class="btn btn-sm btn-pri" data-action="comp-shop-scan" data-plat="${esc(s.channel_code || s.platform)}" data-url="${esc(s.shop_url || s.handle)}">🔎 Quét toàn bộ SP của Shop</button>
                    </div>
                  </div>`).join("")}
               </div>`
            : `<div style="color:var(--muted)">Chưa tách được danh sách Shop riêng biệt từ kết quả hiện tại.</div>`
        }
      </div>

      <!-- 3. CHINA ACCESSORY EXPANSION: PINDUODUO / TAOBAO / 1688 -->
      <div class="card" style="border-color:rgba(251,191,36,0.4)">
        <div class="row" style="justify-content:space-between;margin-bottom:8px">
          <div>
            <h3 style="margin:0;color:#fcd34d">3️⃣ 🇨🇳 Sản phẩm Thay thế · Phụ kiện Bổ sung · Đa dạng Lựa chọn trên Pinduoduo · Taobao · 1688 (${cnItems.length} mẫu)</h3>
            <div style="font-size:12px;color:var(--muted)">Giúp bạn tìm mẫu bao da, dán màn hình, nút bấm, ngòi bút, giá đỡ, túi đựng... mới lạ chưa ai bán ở VN kèm Giá vốn về tay dự kiến!</div>
          </div>
        </div>
        ${
          cnItems.length
            ? `<div style="max-height:420px;overflow:auto;border:1px solid var(--border);border-radius:8px">
                <table class="tbl">
                  <thead><tr><th>Sàn TQ</th><th>Phân loại Phụ kiện</th><th>Tên mẫu trên Pinduoduo / Taobao / 1688</th><th>Giá gốc (¥ CNY)</th><th>Giá vốn về kho VN (0.25kg)</th><th>Thao tác</th></tr></thead>
                  <tbody>
                    ${cnItems.map((c) => `
                      <tr>
                        <td><span class="badge gold">${esc((c.platform || "").toUpperCase())}</span></td>
                        <td>
                          <span class="badge ${c.relation_color || "green"}">${esc(c.relation_badge || "🧩 Phụ kiện bổ sung")}</span>
                          ${c.vi_accessory_group ? `<div style="font-size:11px;color:var(--muted);margin-top:2px">${esc(c.vi_accessory_group)}</div>` : ""}
                        </td>
                        <td>
                          <div class="row" style="flex-wrap:nowrap">
                            ${c.image_url ? `<img src="${esc(c.image_url)}" style="width:38px;height:38px;border-radius:6px;object-fit:cover" alt="" />` : ""}
                            <div>
                              <a href="${esc(c.item_url || "#")}" target="_blank" style="color:#93c5fd;font-weight:600">${esc(c.title)}</a>
                              <div style="font-size:11px;color:var(--muted)">Từ khoá TQ: <code>${esc(c.cn_query || "")}</code> ${c.sales_volume ? `· Lượt mua: ${esc(c.sales_volume)}` : ""}</div>
                            </div>
                          </div>
                        </td>
                        <td><strong>${c.price_cny > 0 ? "¥" + Number(c.price_cny).toFixed(2) : "Xem link"}</strong></td>
                        <td><strong style="color:#6ee7b7">${c.landed_cost_vnd > 0 ? vnd(c.landed_cost_vnd) : "—"}</strong></td>
                        <td><button class="btn btn-sm btn-pri" data-action="sourcing-to-vault" data-id="${esc(c.sourcing_id)}">+ Đưa vào Kho SP</button></td>
                      </tr>`).join("")}
                  </tbody>
                </table>
               </div>`
            : `<div style="color:var(--muted)">Chưa quét mẫu phụ kiện Pinduoduo / Taobao cho danh mục này (tích chọn Pinduoduo/Taobao ở trên rồi bấm Chạy để bổ sung!).</div>`
        }
      </div>

      <!-- 4. CREATORS & EFFECTIVE VIDEOS FROM AFFILIATE GLOBAL SELLING + KALODATA VN -->
      <div class="card" style="border-color:rgba(56,189,248,0.4)">
        <h3 style="margin:0 0 8px;color:#7dd3fc">4️⃣ 🎥 Creator &amp; Video Bán Hiệu Quả từ <code>TikTok Affiliate Global Selling</code> + <code>Kalodata VN</code> (Profile <code>peng_dedicated</code>)</h3>
        <div class="grid2">
          <div>
            <div style="font-weight:700;margin-bottom:6px;font-size:13px">👤 Top Creator đang bán hiệu quả (${creators.length} kênh):</div>
            ${
              creators.length
                ? `<div style="max-height:330px;overflow:auto;border:1px solid var(--border);border-radius:8px">
                    <table class="tbl">
                      <thead><tr><th>Creator (@handle)</th><th>Nguồn</th><th>Followers</th><th>Doanh số GMV</th><th>Đơn bán / View TB</th></tr></thead>
                      <tbody>
                        ${creators.map((cr) => `
                          <tr>
                            <td>
                              <a href="https://www.tiktok.com/@${esc(cr.handle)}" target="_blank" style="color:#93c5fd;font-weight:700">@${esc(cr.handle)}</a>
                              ${cr.creator_level ? `<span class="badge gold">${esc(cr.creator_level)}</span>` : ""}
                              <div style="font-size:11px;color:var(--muted)">${esc(cr.display_name || "")}</div>
                            </td>
                            <td><span class="badge blue">${esc(cr.source || "")}</span></td>
                            <td>${Number(cr.followers || 0).toLocaleString("en-US")}</td>
                            <td><strong style="color:#6ee7b7">${esc(cr.total_gmv_display || (cr.total_gmv_vnd ? vnd(cr.total_gmv_vnd) : "—"))}</strong></td>
                            <td>${cr.units_sold != null ? `${cr.units_sold} đơn` : ""} ${cr.avg_views ? `· ${Number(cr.avg_views).toLocaleString("en-US")} views` : ""}</td>
                          </tr>`).join("")}
                      </tbody>
                    </table>
                   </div>`
                : `<div style="color:var(--muted);font-size:12.5px">Chưa có danh sách Creator cho danh mục này.</div>`
            }
          </div>
          <div>
            <div style="font-weight:700;margin-bottom:6px;font-size:13px">🎬 Danh sách Video Bán Hàng Hiệu Quả (${videos.length} video — bấm Clone kịch bản 15s):</div>
            ${
              videos.length
                ? `<div style="max-height:330px;overflow:auto;border:1px solid var(--border);border-radius:8px">
                    <table class="tbl">
                      <thead><tr><th>Video &amp; Creator</th><th>GPM / Doanh thu</th><th>Đơn / Lượt xem</th><th>Hành động</th></tr></thead>
                      <tbody>
                        ${videos.map((v) => `
                          <tr>
                            <td>
                              <a href="${esc(v.video_url || "#")}" target="_blank" style="color:#93c5fd;font-weight:600">${esc((v.caption || v.video_id || "Xem Video TikTok").slice(0, 75))}</a>
                              <div style="font-size:11px;color:var(--muted)">@${esc(v.author_handle || "creator")} · <code>${esc(v.source || "")}</code></div>
                            </td>
                            <td>
                              <div style="color:#fcd34d;font-weight:700">GPM: ${esc(v.gpm_display || "—")}</div>
                              <div style="font-size:11px;color:#6ee7b7">GMV: ${esc(v.video_gmv_display || "—")}</div>
                            </td>
                            <td>
                              <div>${v.orders_count != null ? `<strong>${v.orders_count} đơn</strong>` : "—"}</div>
                              <div style="font-size:11px;color:var(--muted)">${Number(v.views_count || 0).toLocaleString("en-US")} views</div>
                            </td>
                            <td>
                              <button class="btn btn-sm btn-gold" data-action="eco-send-to-clone" data-url="${esc(v.video_url || "")}" data-prod="${esc(col.name)}">⚡ Clone</button>
                            </td>
                          </tr>`).join("")}
                      </tbody>
                    </table>
                   </div>`
                : `<div style="color:var(--muted);font-size:12.5px">Chưa có danh sách Video hiệu quả cho danh mục này.</div>`
            }
          </div>
        </div>
      </div>
    `;
  }

  async function loadEcosystemsTab(selectCollectionId = null) {
    const [ecoData, kaloSt] = await Promise.all([
      api("/api/ecosystems"),
      api("/api/kalodata/status").catch(() => null),
    ]);
    const cols = ecoData.collections || [];
    const targetId = selectCollectionId || (cols.some((c) => c.collection_id === ACTIVE_ECO_ID) ? ACTIVE_ECO_ID : (cols[0]?.collection_id || ""));

    if (kaloSt) {
      const mini = document.getElementById("ecoPortalMiniBadge");
      if (mini) {
        mini.innerHTML =
          `Kalodata (<code>${esc(kaloSt.account_email || "chưa cấu hình")}</code>): ` +
          `${kaloSt.kalodata_session?.logged_in ? '<span class="badge green">🟢 Đã đăng nhập</span>' : '<span class="badge">⚪ Chờ mở tab</span>'} · ` +
          `Global Selling: ${kaloSt.affiliate_global_selling_session?.ready ? '<span class="badge green">🟢 Sẵn sàng</span>' : '<span class="badge">⚪ Chờ mở tab</span>'}`;
      }
    }

    const bar = document.getElementById("ecoCollectionsBar");
    if (bar) {
      bar.innerHTML = cols.length
        ? cols
            .map(
              (c) =>
                `<button type="button" class="chip ${c.collection_id === targetId ? "active" : ""}" data-action="eco-open-col" data-id="${esc(c.collection_id)}">📂 ${esc(c.name)} (${(c.product_ids || []).length} SP)</button>`
            )
            .join("")
        : `<span style="font-size:12px;color:var(--muted)">Chưa có danh mục nào</span>`;
    }

    if (targetId) {
      if (ecoData.active_detail && ecoData.active_detail.collection_id === targetId) {
        renderEcosystemDetail(ecoData.active_detail);
      } else {
        const d = await api(`/api/ecosystems/${encodeURIComponent(targetId)}`);
        renderEcosystemDetail(d.collection);
      }
    } else {
      renderEcosystemDetail(null);
    }
  }

  // --- PART 4.3B: APIFY STORE CATALOG & SMART GOAL CALLER --------------------
  async function loadApifyStoreTab() {
    const q = document.getElementById("apifyStoreSearchQ")?.value || "";
    const sortBy = document.getElementById("apifyStoreSort")?.value || "quality";
    const ppuOnly = document.getElementById("apifyStorePpuOnly")?.checked !== false;

    const qs = new URLSearchParams({
      q,
      goal: APIFY_STORE_GOAL,
      sort_by: sortBy,
      pay_per_use_only: ppuOnly ? "1" : "0",
      limit: "40",
    });

    const [stats, srch] = await Promise.all([
      api("/api/apify-store/stats"),
      api(`/api/apify-store/search?${qs}`),
    ]);

    const lastSync = stats.last_sync;
    document.getElementById("apifyStoreKpiStrip").innerHTML = `
      <div class="kpi"><div class="lbl">🧩 Tổng Actors đã lưu cục bộ</div><div class="val sky">${Number(stats.total_actors || 0).toLocaleString("en-US")}</div></div>
      <div class="kpi"><div class="lbl">💳 Trả theo lượt / Free (Dùng ngay)</div><div class="val green">${Number(stats.pay_per_use_actors || 0).toLocaleString("en-US")}</div></div>
      <div class="kpi"><div class="lbl">🛍 Actors Thương mại điện tử</div><div class="val gold">${Number(stats.ecommerce_actors || 0).toLocaleString("en-US")}</div></div>
      <div class="kpi"><div class="lbl">📱 Actors Mạng xã hội / Painpoint</div><div class="val">${Number(stats.social_actors || 0).toLocaleString("en-US")}</div></div>
      <div class="kpi"><div class="lbl">🕒 Đồng bộ gần nhất</div><div class="val" style="font-size:13px">${lastSync ? fmtTime(lastSync.completed_at || lastSync.created_at) : "Chưa quét"}</div></div>
    `;

    const gCounts = stats.goal_counts || {};
    const gCatalog = stats.goals_catalog || {};
    document.getElementById("apifyStoreGoalChips").innerHTML =
      `<button type="button" class="chip ${!APIFY_STORE_GOAL ? "active" : ""}" data-action="apify-goal-chip" data-goal="">🗂 Tất cả mục tiêu (${Number(stats.total_actors || 0).toLocaleString("en-US")})</button>` +
      Object.entries(gCatalog)
        .map(([gk, glbl]) => `<button type="button" class="chip ${APIFY_STORE_GOAL === gk ? "active" : ""}" data-action="apify-goal-chip" data-goal="${esc(gk)}">${esc(glbl)} (${gCounts[gk] || 0})</button>`)
        .join("");

    document.getElementById("apifyStoreMatchedLbl").textContent = Number(srch.total || 0).toLocaleString("en-US");
    const actors = srch.actors || [];
    document.getElementById("apifyStoreTableBox").innerHTML = actors.length
      ? `<table class="tbl">
          <thead><tr><th>Actor (Username/Name)</th><th>Mục tiêu phù hợp</th><th>Cơ chế tính phí</th><th>Người dùng 30d</th><th>Tỷ lệ thành công</th><th>Điểm Chất lượng</th><th>Thao tác</th></tr></thead>
          <tbody>
            ${actors.map((a) => `
              <tr>
                <td>
                  <div><a href="${esc(a.store_url)}" target="_blank" style="color:#93c5fd;font-weight:700">${esc(a.title)}</a></div>
                  <div style="font-size:11.5px;color:#fcd34d"><code>${esc(a.full_name)}</code></div>
                  <div style="font-size:11.5px;color:var(--muted);max-width:410px">${esc((a.description || "").slice(0, 120))}</div>
                </td>
                <td>${(a.goal_tags || []).map((g) => `<span class="badge blue" style="margin:1px">${esc(g)}</span>`).join("") || "—"}</td>
                <td>
                  <span class="badge ${a.is_pay_per_use ? "green" : ""}">${esc(a.pricing_model)}</span>
                  ${a.unit_price_usd != null ? `<div style="font-size:11px;color:var(--muted)">$${a.unit_price_usd}/unit</div>` : ""}
                </td>
                <td><strong>${Number(a.users_30d || 0).toLocaleString("en-US")}</strong> <span style="font-size:11px;color:var(--muted)">/ ${Number(a.total_users || 0).toLocaleString("en-US")}</span></td>
                <td>${a.runs_30d_total > 0 ? `<strong style="color:${a.success_rate_30d >= 85 ? "#6ee7b7" : "#fcd34d"}">${a.success_rate_30d}%</strong>` : "—"}</td>
                <td><span class="badge gold">🏆 ${a.quality_score}</span></td>
                <td>
                  <button class="btn btn-sm btn-pri" data-action="apify-open-actor" data-slug="${esc(a.slug)}">📋 Schema &amp; Gọi Ngay</button>
                </td>
              </tr>`).join("")}
          </tbody>
        </table>`
      : `<div style="padding:18px;text-align:center;color:var(--muted)">Chưa có Actor nào khớp bộ lọc — bấm <strong>"🔄 Quét &amp; Cập nhật Toàn bộ Apify Store"</strong> ở góc phải trên nếu kho đang trống!</div>`;
  }

  async function openApifyActorCallModal(slug) {
    toast(`Đang tải Input Schema chuẩn của Actor ${slug.replace("~", "/")}...`);
    const sc = await api(`/api/apify-store/actors/${encodeURIComponent(slug)}/schema`);
    const props = sc.input_schema?.properties || {};
    const propsHtml = Object.entries(props)
      .slice(0, 16)
      .map(
        ([k, v]) =>
          `<tr><td><code>${esc(k)}</code></td><td>${esc(v.type || "")}</td><td>${v.enum ? `<code>${esc(v.enum.slice(0, 8).join(", "))}</code>` : "—"}</td><td style="font-size:11.5px;color:var(--muted)">${esc((v.description || "").replace(/<[^>]+>/g, "").slice(0, 110))}</td></tr>`
      )
      .join("");

    openModal(`⚡ Gọi Trực tiếp Actor: ${sc.full_name} — ${sc.title}`, `
      <div style="margin-bottom:10px;font-size:12.5px;color:#7dd3fc">
        Slug hệ thống: <code>${esc(sc.slug)}</code> ${sc.cached ? '<span class="badge green">Đã lưu Cache Schema</span>' : '<span class="badge blue">Vừa tải Schema mới</span>'}
      </div>
      ${
        propsHtml
          ? `<div style="max-height:190px;overflow:auto;border:1px solid var(--border);border-radius:8px;margin-bottom:10px">
              <table class="tbl"><thead><tr><th>Tham số</th><th>Kiểu</th><th>Enum hợp lệ</th><th>Mô tả</th></tr></thead><tbody>${propsHtml}</tbody></table>
             </div>`
          : ""
      }
      <div class="field">
        <label>📥 JSON Payload gửi vào Actor (chỉnh sửa theo mục tiêu của bạn)</label>
        <textarea id="mApifyCallPayload" rows="6" style="font-family:monospace;font-size:12.5px">${esc(JSON.stringify(sc.sample_payload || {}, null, 2))}</textarea>
      </div>
      <div class="grid2">
        <div class="field">
          <label>Trần chi phí an toàn cho lần gọi này (USD)</label>
          <input type="number" id="mApifyMaxCharge" value="0.06" min="0.015" max="0.50" step="0.01" />
        </div>
        <div class="row" style="align-items:flex-end">
          <label style="font-size:12.5px;color:#6ee7b7"><input type="checkbox" id="mApifySaveVault" /> 📦 Tự động lưu kết quả SP vào Kho SP</label>
        </div>
      </div>
      <button class="btn btn-pri" data-action="apify-exec-call" data-slug="${esc(sc.slug)}">🚀 Gọi Actor Ngay qua Vòng Key Apify</button>
    `);
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
    const [mv, tg, bh, mcp, d3st, kaloSt, laSt, kaloRots] = await Promise.all([
      api("/api/settings"),
      api("/api/providers/telegram/status"),
      api("/api/connections/browser"),
      api("/api/mcp/status"),
      api("/api/desk300/status").catch(() => ({ ok: false })),
      api("/api/kalodata/status").catch(() => null),
      api("/api/system/launchagent").catch(() => null),
      api("/api/kalodata/rotations").catch(() => null),
    ]);
    renderDeskGatewayBanner(d3st);
    const st = mv.settings || {};
    document.getElementById("setTgToken").value = st.notify?.telegram_token || "";
    document.getElementById("setTgChatId").value = st.notify?.telegram_chat_id || "";
    document.getElementById("setTregKey").value = st.providers?.treg_key || "";
    document.getElementById("setJevKey").value = st.providers?.typesafe_key || "";
    if (document.getElementById("setKaloEmail")) document.getElementById("setKaloEmail").value = st.kalodata?.account_email || "";
    if (document.getElementById("setKaloPassword")) document.getElementById("setKaloPassword").value = st.kalodata?.password || "";
    if (document.getElementById("setKaloMarket")) document.getElementById("setKaloMarket").value = st.kalodata?.market || "VN";
    if (document.getElementById("setKaloCurrency")) document.getElementById("setKaloCurrency").value = st.kalodata?.currency || "VND";
    if (document.getElementById("setKaloWindow")) document.getElementById("setKaloWindow").value = String(st.kalodata?.default_window_days || 7);
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
      `Bot: <strong>@${esc(tg.bot_username)}</strong> · Token: ${tg.token_configured ? "✅ Đã lưu Keychain" : "❌ Chưa lưu"} · Đã gửi Telegram: <strong style="color:#6ee7b7">${tg.logs_notified ?? 0}/${tg.logs_total ?? 0} nhật ký</strong> · Allowed IDs: <code>${esc((tg.allowed_user_ids || []).join(", "))}</code> · Tailscale: <a href="${esc(tg.tailscale_url)}" target="_blank" style="color:#6ee7b7">${esc(tg.tailscale_url)}</a>`;

    const mirrorLine = kaloSt?.mirror_enabled
      ? `<br/>• 🔗 <strong style="color:#6ee7b7">Ánh xạ tự động 2 chiều với affiliate-peng: ĐANG BẬT</strong> (Khi <code>affiliate-peng</code> đổi tài khoản Kalodata, Global Shop tự động cập nhật ngay lập tức · Đồng bộ gần nhất: <code>${esc(fmtTime(kaloSt.mirror?.last_synced_at))}</code>)`
      : "";
    const kLine = kaloSt
      ? `<br/>• Kalodata VN (<code>${esc(kaloSt.account_email)}</code>): ${kaloSt.kalodata_session?.logged_in ? "🟢 Đã đăng nhập" : "⚪ Chờ mở tab"} · Affiliate Global Selling: ${kaloSt.affiliate_global_selling_session?.ready ? "🟢 Sẵn sàng" : "⚪ Chờ mở tab"}${mirrorLine}`
      : "";
    document.getElementById("browserHubBox").innerHTML =
      `Profile: <strong>${esc(bh.profile_name)}</strong> (CDP <code>127.0.0.1:${bh.cdp_port}</code>): <strong>${bh.running ? "🟢 Đang mở (" + bh.open_tabs_count + " tab)" : "⚪ Đang đóng"}</strong> · SecretStore: <code>${esc(mv.secret_backend)}</code>${kLine}`;

    const rotHistEl = document.getElementById("kaloRotationHistoryBox");
    if (rotHistEl && kaloRots?.items?.length) {
      rotHistEl.innerHTML =
        `<strong>🕒 Lịch sử đổi / ánh xạ tài khoản Kalodata (${kaloRots.items.length} lần gần nhất):</strong><br/>` +
        kaloRots.items
          .slice(0, 4)
          .map((r) => `• <code>${esc(fmtTime(r.created_at))}</code>: ${esc(r.old_account_hint || "—")} &rarr; <strong style="color:#6ee7b7">${esc(r.new_account_email)}</strong> (<code>${esc(r.status)}</code>)`)
          .join("<br/>");
    }

    const laHtml = laSt
      ? `<br/>🔄 LaunchAgent tự khởi động (<code>${esc(laSt.label)}</code>): ${laSt.running ? `<strong style="color:#6ee7b7">🟢 Đang chạy tự động (PID ${laSt.pid || "—"} · RunAtLoad + KeepAlive)</strong>` : laSt.installed ? '<span style="color:#fcd34d">🟡 Đã cài đặt</span>' : "⚪ Chưa cài"}`
      : "";
    document.getElementById("mcpStatusBox").innerHTML =
      `🔌 MCP Gateway: <code>${esc(mcp.http_endpoint)}</code> (${mcp.tools_count} tools · chế độ <code>${esc(mcp.access_mode)}</code>)${laHtml}`;
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
    } else if (["jrRankBy", "jrTier", "jrPlatform", "jrIndustry", "jrMinScore"].includes(ev.target.id)) {
      loadJevLeaderboard();
    } else if (["histFilterMod", "histFilterStatus"].includes(ev.target.id)) {
      loadHistoryAndJobs();
    } else if (ev.target.id === "kaloHuntHistorySelect" && ev.target.value) {
      api(`/api/hunt/kalodata-vn/${encodeURIComponent(ev.target.value)}`).then((r) => renderKalodataHuntResult(r)).catch((e) => toast(e.message, true));
    } else if (ev.target.classList.contains("kcap-excl-chk")) {
      const capId = ev.target.dataset.capid;
      const excl = [...document.querySelectorAll(`.kcap-excl-chk[data-capid="${capId}"]:not(:checked)`)].map((c) => Number(c.dataset.ridx));
      api(`/api/kalodata/captures/${encodeURIComponent(capId)}/preview`, "POST", { exclude_row_indices: excl })
        .then((cap) => renderKalodataCapturePreview(cap))
        .catch((e) => toast(e.message, true));
    } else if (ev.target.id === "msPlatform") {
      const p = ev.target.value;
      if (DEFAULT_FEES_BY_PLAT[p] !== undefined && !document.getElementById("msEditId").value) {
        document.getElementById("msFee").value = DEFAULT_FEES_BY_PLAT[p];
      }
    } else if (ev.target.id === "gtHistorySelect") {
      const rid = ev.target.value;
      const found = GT_HISTORY_RUNS.find((r) => r.run_id === rid);
      if (found) renderGoogleTrendsResult(found);
    } else if (ev.target.id === "hsMode") {
      const isDaily = ev.target.value === "daily_time";
      document.getElementById("hsDailyTimeWrap").style.display = isDaily ? "block" : "none";
      document.getElementById("hsIntervalWrap").style.display = isDaily ? "none" : "block";
    }
  });

  document.addEventListener("input", (ev) => {
    if (ev.target.id === "msUrl") {
      const v = ev.target.value.trim().toLowerCase();
      const sel = document.getElementById("msPlatform");
      let detected = "";
      if (v.includes("shopee.ph")) detected = "shopee_ph";
      else if (v.includes("shopee.sg")) detected = "shopee_sg";
      else if (v.includes("shopee.com.my")) detected = "shopee_my";
      else if (v.includes("shopee.co.th")) detected = "shopee_th";
      else if (v.includes("shopee.")) detected = "shopee_vn";
      else if (v.includes("facebook.com") || v.includes("fb.com") || v.includes("fb.watch")) detected = "facebook_fanpage";
      else if (v.includes("tiktok.com") || v.includes("tiktokshop")) {
        if (v.includes("region=ph")) detected = "tiktok_shop_ph";
        else if (v.includes("region=sg")) detected = "tiktok_shop_sg";
        else if (v.includes("region=my")) detected = "tiktok_shop_my";
        else if (v.includes("region=th")) detected = "tiktok_shop_th";
        else detected = "tiktok_shop_vn";
      }
      else if (v.includes("lazada.")) detected = "lazada";
      else if (v.includes("instagram.com")) detected = "instagram";
      if (detected && sel && sel.value !== detected) {
        sel.value = detected;
        if (!document.getElementById("msEditId").value && DEFAULT_FEES_BY_PLAT[detected] !== undefined) {
          document.getElementById("msFee").value = DEFAULT_FEES_BY_PLAT[detected];
        }
      }
    } else if (ev.target.id === "apifyStoreSearchQ") {
      clearTimeout(ev.target._t);
      ev.target._t = setTimeout(() => loadApifyStoreTab(), 260);
    } else if (ev.target.id === "msSearchQ") {
      clearTimeout(ev.target._t);
      ev.target._t = setTimeout(() => loadMyShops(), 220);
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
      } else if (act === "jump-ecosystems") {
        showTab("ecosystems", "/he-sinh-thai");
      } else if (act === "jump-kalopro") {
        showTab("kalopro", "/kalodata-pro");
      } else if (act === "jump-kalodata-import") {
        showTab("kalodata", "/nhap-kalodata");
      } else if (act === "jump-jevrank") {
        showTab("jevrank", "/bang-xep-hang-jev");
      } else if (act === "jump-deskflow") {
        showTab("deskflow", "/luong-300-desk");
      } else if (act === "jump-apifystore") {
        showTab("apifystore", "/apify-store");
      } else if (act === "jump-myshops") {
        showTab("myshops", "/shop-cua-toi");
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
      } else if (act === "desk300-check") {
        toast("Đang kiểm tra Gateway 300+desk (127.0.0.1:18765) & SOCKS5 OrangePi5 Pro...");
        const st = await api("/api/desk300/check", "POST", {});
        renderDeskGatewayBanner(st);
        toast(st.summary || "300+desk SẴN SÀNG!");
      } else if (act === "desk300-refresh") {
        await loadDesk300Tab();
      } else if (act === "desk300-open-run") {
        const d = await api(`/api/desk300/runs/${encodeURIComponent(actEl.dataset.id)}`);
        if (d.run) renderDeskRunDetail(d.run);
      } else if (act === "desk300-run-vault" || act === "kho-run-300desk") {
        const selIds = [...SELECTED_PIDS];
        const lim = Number(document.getElementById("deskVaultLimit")?.value || 8);
        const eng = document.getElementById("deskEngineSel")?.value || "gateway_fast";
        const autoShop = document.getElementById("deskAutoAssignShop")?.checked !== false;
        showTab("deskflow", "/luong-300-desk");
        document.getElementById("deskActiveRunBox").innerHTML = `<div class="card">⏳ Đang chạy luồng 5 bước: <strong>Apify #1 &rarr; Treg #2 &rarr; 300+desk (OPi SOCKS5) &rarr; Jev AI Ra Quyết định</strong>...</div>`;
        const res = await api("/api/desk300/run", "POST", {
          mode: "vault_process",
          product_ids: selIds.length ? selIds : undefined,
          limit: lim,
          exec_engine: eng,
          auto_assign_my_shop: autoShop,
        });
        renderDeskRunDetail(res.run);
        await syncSidebarCountsAndRefs();
        await loadDesk300Tab();
        toast(res.summary);
      } else if (act === "desk300-run-hunt") {
        const kws = (document.getElementById("deskHuntKeywords")?.value || "").split(/[\n,]+/).map((s) => s.trim()).filter(Boolean);
        const chs = [...document.querySelectorAll(".desk-ch:checked")].map((c) => c.value);
        const eng = document.getElementById("deskEngineSel")?.value || "gateway_fast";
        const shopeeFilters = collectDeskShopeeFilters();
        document.getElementById("deskActiveRunBox").innerHTML = `<div class="card">⏳ Đang săn sản phẩm (Apify #1 &rarr; Treg #2) và đưa qua <strong>300+desk (OPi SOCKS5) &rarr; Jev AI</strong>...</div>`;
        const res = await api("/api/desk300/run", "POST", {
          mode: "hunt_and_process",
          keywords: kws,
          channels: chs,
          exec_engine: eng,
          auto_assign_my_shop: true,
          shopee_filters: shopeeFilters,
        });
        renderDeskRunDetail(res.run);
        await syncSidebarCountsAndRefs();
        await loadDesk300Tab();
        toast(res.summary);
      } else if (act === "prod-300desk") {
        toast("Đang đưa SP qua 300+desk (OPi SOCKS5) đặt Tên SEO, dịch 1688 & Jev chốt...");
        const res = await api(`/api/products/${actEl.dataset.id}/process-300desk`, "POST", {});
        toast(res.summary);
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
          budget_limit_usd: Number(document.getElementById("huntBudget").value || 0.35),
          use_300desk: document.getElementById("huntUse300Desk")?.checked !== false,
          auto_score_jev: document.getElementById("huntAutoJev").checked,
          shopee_filters: collectHuntShopeeFilters(),
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
      } else if (act === "add-hunt-sample") {
        const kw = actEl.dataset.kw || "";
        const hk = document.getElementById("huntKeywords");
        const cur = hk.value.split(/[\n,]+/).map((s) => s.trim()).filter(Boolean);
        if (kw && !cur.includes(kw)) {
          cur.push(kw);
          hk.value = cur.join(", ");
        }
        const ppIn = document.getElementById("ppTopicInput");
        if (ppIn && !ppIn.value.trim()) ppIn.value = kw;
      } else if (act === "close-hunt-past") {
        document.getElementById("huntPastDetailBox").innerHTML = "";
      } else if (act === "gt-search") {
        const kw = document.getElementById("gtKeyword").value.trim() || document.getElementById("huntKeywords").value.trim();
        toast("Đang quét từ khoá Đột phá Google Trends VN & chấm điểm Jev AI...");
        const res = await api("/api/hunt/google-trends", "POST", {
          keyword: kw,
          time_range: document.getElementById("gtTimeRange")?.value || "today 3-m",
          category: document.getElementById("gtCategory")?.value || "",
          score_jev: document.getElementById("gtScoreJev")?.checked !== false,
        });
        renderGoogleTrendsResult(res);
        loadGoogleTrendsHistory();
        toast(res.summary);
      } else if (act === "gt-push-kw") {
        const kw = actEl.dataset.kw || "";
        const hk = document.getElementById("huntKeywords");
        const cur = hk.value.split(/[\n,]+/).map((s) => s.trim()).filter(Boolean);
        if (kw && !cur.includes(kw)) cur.push(kw);
        hk.value = cur.join(", ");
        hk.scrollIntoView({ behavior: "smooth", block: "center" });
        toast(`Đã thêm "${kw}" vào ô Săn Sản phẩm!`);
      } else if (act === "gt-push-all-top") {
        const els = [...document.querySelectorAll(".gt-kw-item")].slice(0, 4);
        const hk = document.getElementById("huntKeywords");
        const cur = hk.value.split(/[\n,]+/).map((s) => s.trim()).filter(Boolean);
        els.forEach((el) => {
          const w = el.dataset.kw;
          if (w && !cur.includes(w)) cur.push(w);
        });
        hk.value = cur.join(", ");
        hk.scrollIntoView({ behavior: "smooth", block: "center" });
        toast("Đã đẩy Top 4 từ khoá xu hướng lên ô Săn Sản phẩm!");
      } else if (act === "pp-discover") {
        const topic = document.getElementById("ppTopicInput").value.trim() || document.getElementById("huntKeywords").value.split(/[\n,]+/)[0]?.trim() || "";
        const chs = [...document.querySelectorAll(".pp-ch:checked")].map((c) => c.value);
        toast("Đang quét Painpoint trên Facebook/Threads/X/Reddit, chấm Jev AI & tìm Sản phẩm Giải pháp...");
        const res = await api("/api/hunt/painpoints", "POST", {
          topic_query: topic,
          channels: chs,
          auto_find_products: document.getElementById("ppAutoFindProducts")?.checked !== false,
          shopee_filters: collectHuntShopeeFilters(),
        });
        toast(res.summary);
        await syncSidebarCountsAndRefs();
        await loadPainpoints();
      } else if (act === "pp-refresh") {
        await loadPainpoints();
      } else if (act === "pp-delete") {
        await api(`/api/hunt/painpoints/${encodeURIComponent(actEl.dataset.id)}`, "DELETE");
        await loadPainpoints();
      } else if (act === "kw-preset-overseas-sales") {
        const kwPl = document.getElementById("kwPlatform");
        if (!kwPl.value.startsWith("shopee")) kwPl.value = "shopee_vn";
        document.getElementById("kwShopeeFiltersBox").style.display = "block";
        document.getElementById("kwShippedFrom").value = "overseas";
        document.getElementById("kwSortBy").value = "sales";
        toast("Đã chọn bộ lọc Shopee: ✈️ Shop Quốc tế / Nước ngoài + 🔥 Bán chạy nhất");
      } else if (act === "kw-preset-overseas-new") {
        const kwPl = document.getElementById("kwPlatform");
        if (!kwPl.value.startsWith("shopee")) kwPl.value = "shopee_vn";
        document.getElementById("kwShopeeFiltersBox").style.display = "block";
        document.getElementById("kwShippedFrom").value = "overseas";
        document.getElementById("kwSortBy").value = "latest";
        toast("Đã chọn bộ lọc Shopee: ✈️ Shop Quốc tế / Nước ngoài + 🆕 Mới đăng nhất");
      } else if (act === "kw-preset-domestic") {
        const kwPl = document.getElementById("kwPlatform");
        if (!kwPl.value.startsWith("shopee")) kwPl.value = "shopee_vn";
        document.getElementById("kwShopeeFiltersBox").style.display = "block";
        document.getElementById("kwShippedFrom").value = "domestic";
        document.getElementById("kwSortBy").value = "sales";
        toast("Đã chọn bộ lọc Shopee: 🏠 Chỉ Shop Nội địa + 🔥 Bán chạy");
      } else if (act === "kw-preset-reset") {
        document.getElementById("kwShippedFrom").value = "";
        document.getElementById("kwSortBy").value = "relevancy";
        document.getElementById("kwMinPrice").value = "";
        document.getElementById("kwMaxPrice").value = "";
        document.getElementById("kwMinRating").value = "";
        ["kwMallOnly", "kwPreferredOnly", "kwVideoOnly", "kwDiscountOnly", "kwFreeshipOnly"].forEach((id) => {
          const el = document.getElementById(id);
          if (el) el.checked = false;
        });
        toast("Đã đặt lại bộ lọc Shopee về mặc định");
      } else if (act === "kw-suggest") {
        const kw = document.getElementById("kwInput").value.trim();
        const res = await api("/api/keywords/suggest", "POST", { keyword: kw });
        document.getElementById("kwSuggestChips").innerHTML = (res.suggestions || []).map((s) =>
          `<button class="chip" data-action="pick-kw-chip" data-kw="${esc(s)}">${esc(s)}</button>`
        ).join("");
      } else if (act === "pick-kw-chip") {
        document.getElementById("kwInput").value = actEl.dataset.kw;
      } else if (act === "kw-research") {
        toast("Đang quét từ khoá (áp dụng bộ lọc Shopee nếu chọn), chấm điểm Jev & lưu sản phẩm vào Kho...");
        const res = await api("/api/keywords/research", "POST", {
          keyword: document.getElementById("kwInput").value.trim(),
          platform: document.getElementById("kwPlatform").value,
          limit: Number(document.getElementById("kwLimit").value || 20),
          save_top_to_vault: document.getElementById("kwSaveVault").checked,
          shopee_filters: collectKeywordShopeeFilters(),
        });
        renderKeywordResult(res);
        loadKeywordHistory();
        syncSidebarCountsAndRefs();
        toast(res.summary);
      } else if (act === "kw-watch-create") {
        const kw = document.getElementById("kwInput").value.trim();
        const plat = document.getElementById("kwPlatform").value;
        const sf = collectKeywordShopeeFilters();
        const locSuffix = sf?.shipped_from ? ` [${sf.shipped_from}]` : "";
        await api("/api/watches", "POST", {
          watch_type: "keyword",
          platform: plat,
          target_key: kw,
          title: `Từ khoá: ${kw}${locSuffix}`,
          shopee_filters: sf,
          run_immediately: true,
        });
        toast(`Đã tạo theo dõi định kỳ từ khoá '${kw}${locSuffix}'!`);
        showTab("watches", "/theo-doi");
      } else if (act === "watch-create") {
        const target = document.getElementById("wtTarget").value.trim();
        const wType = document.getElementById("wtType").value;
        const wPlat = document.getElementById("wtPlatform").value;
        const wtLoc = document.getElementById("wtShopeeShippedFrom")?.value || "";
        const wtSort = document.getElementById("wtShopeeSortBy")?.value || "relevancy";
        const wtFilters =
          wType === "keyword" && wPlat.startsWith("shopee") && (wtLoc || wtSort !== "relevancy")
            ? { shipped_from: wtLoc, sort_by: wtSort }
            : undefined;
        await api("/api/watches", "POST", {
          watch_type: wType,
          platform: wPlat,
          interval_hours: Number(document.getElementById("wtInterval").value || 12),
          target_key: target,
          title: document.getElementById("wtTitle").value.trim() || (wtLoc ? `${target} (${wtLoc})` : target),
          shopee_filters: wtFilters,
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
      } else if (act === "watch-pause-all") {
        const res = await api("/api/watches/pause-all", "POST", {});
        toast(res.summary);
        loadWatches();
      } else if (act === "watch-resume-all") {
        const res = await api("/api/watches/resume-all", "POST", { resume_items: true });
        toast(res.summary);
        loadWatches();
      } else if (act === "watch-toggle") {
        const nextAct = actEl.dataset.next === "resume" ? "resume" : "pause";
        await api(`/api/watches/${actEl.dataset.id}/${nextAct}`, "POST", {});
        toast(nextAct === "resume" ? "Đã bật lại theo dõi mục này!" : "Đã tạm dừng theo dõi mục này!");
        loadWatches();
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
      } else if (act === "ms-add-tag") {
        const inp = document.getElementById("msNicheTags");
        const cur = inp.value.split(",").map((s) => s.trim()).filter(Boolean);
        const tag = actEl.dataset.tag;
        if (tag && !cur.some((x) => x.toLowerCase() === tag.toLowerCase())) {
          cur.push(tag);
          inp.value = cur.join(", ");
        }
      } else if (act === "ms-toggle-cmp") {
        const cid = actEl.dataset.cid;
        if (MY_SHOP_SELECTED_CMPS.has(cid)) MY_SHOP_SELECTED_CMPS.delete(cid);
        else MY_SHOP_SELECTED_CMPS.add(cid);
        renderMyShopCampaignPicker();
      } else if (act === "ms-filter-plat") {
        MY_SHOPS_FILTER_PLAT = actEl.dataset.plat || "";
        loadMyShops();
      } else if (act === "myshop-refresh") {
        await syncSidebarCountsAndRefs();
        await loadMyShops();
      } else if (act === "myshop-cancel-edit") {
        resetMyShopForm();
      } else if (act === "myshop-save") {
        const editId = document.getElementById("msEditId").value.trim();
        const payload = {
          role: "own_shop",
          platform: document.getElementById("msPlatform").value,
          shop_url: document.getElementById("msUrl").value.trim(),
          shop_name: document.getElementById("msName").value.trim(),
          status: document.getElementById("msStatus").value,
          industry: document.getElementById("msIndustry").value || "gia_dung",
          platform_fee_pct: Number(document.getElementById("msFee").value || 0),
          niche_tags: document.getElementById("msNicheTags").value,
          campaign_ids: [...MY_SHOP_SELECTED_CMPS],
          note: document.getElementById("msNote").value.trim(),
        };
        const res = editId
          ? await api(`/api/my-shops/${encodeURIComponent(editId)}`, "PATCH", payload)
          : await api("/api/my-shops", "POST", payload);
        toast(res.summary || "Đã lưu vào Shop của tôi!");
        resetMyShopForm();
        await syncSidebarCountsAndRefs();
        await loadMyShops();
      } else if (act === "ms-edit") {
        const sh = ALL_SHOPS.find((x) => x.shop_id === actEl.dataset.id);
        if (sh) editMyShop(sh);
        else {
          const d = await api(`/api/my-shops/${encodeURIComponent(actEl.dataset.id)}`);
          if (d.shop) editMyShop(d.shop);
        }
      } else if (act === "ms-delete") {
        await api(`/api/my-shops/${encodeURIComponent(actEl.dataset.id)}`, "DELETE");
        if (document.getElementById("msEditId").value === actEl.dataset.id) resetMyShopForm();
        toast("Đã xoá Shop khỏi danh sách!");
        await syncSidebarCountsAndRefs();
        await loadMyShops();
      } else if (act === "ms-view-products") {
        CURRENT_BUCKET = "all";
        CURRENT_SUB = "all";
        await syncSidebarCountsAndRefs();
        const fShop = document.getElementById("filterShop");
        if (fShop) fShop.value = actEl.dataset.id;
        showTab("results", "/kho");
      } else if (act === "ms-spy-fanpage") {
        document.getElementById("spyFanpageQuery").value = actEl.dataset.name || "";
        showTab("spy", "/soi-san-pham");
      } else if (act === "myshop-auto-match") {
        const res = await api("/api/shops/auto-match-products", "POST", {});
        toast(res.summary);
        await syncSidebarCountsAndRefs();
        await loadMyShops();
      } else if (act === "comp-shop-scan") {
        document.getElementById("scanShopQuery").value = actEl.dataset.url || "";
        document.getElementById("scanShopPlat").value = actEl.dataset.plat === "tiktok_shop" ? "tiktok_shop" : "shopee";
        showTab("shopspy", "/soi-shop");
      } else if (act === "shop-save") {
        const res = await api("/api/shops", "POST", {
          role: document.getElementById("shRole")?.value || "competitor_shop",
          platform: document.getElementById("shPlatform").value,
          shop_name: document.getElementById("shName").value.trim(),
          shop_url: document.getElementById("shUrl").value.trim(),
          note: document.getElementById("shNote")?.value?.trim() || "",
        });
        toast(res.summary);
        document.getElementById("shName").value = "";
        document.getElementById("shUrl").value = "";
        if (document.getElementById("shNote")) document.getElementById("shNote").value = "";
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
        syncSidebarCountsAndRefs();
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
      } else if (act === "tg-sync-pending") {
        const res = await api("/api/providers/telegram/sync-pending", "POST", {});
        toast(res.summary || "Đã đồng bộ toàn bộ nhật ký chưa báo sang Telegram!");
        if (CURRENT_TAB === "logs") await loadHistoryAndJobs();
        else if (CURRENT_TAB === "settings") await loadSettings();
      } else if (act === "hist-resend-tg") {
        const res = await api(`/api/history-logs/${encodeURIComponent(actEl.dataset.id)}/resend-telegram`, "POST", {});
        toast(`Đã gửi lại nhật ký sang Telegram (Msg #${res.message_id || "OK"})!`);
        await loadHistoryAndJobs();
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
          kalodata: {
            account_email: document.getElementById("setKaloEmail")?.value || "",
            password: document.getElementById("setKaloPassword")?.value || "",
            market: document.getElementById("setKaloMarket")?.value || "VN",
            currency: document.getElementById("setKaloCurrency")?.value || "VND",
            default_window_days: Number(document.getElementById("setKaloWindow")?.value || 7),
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
      } else if (act === "apify-goal-chip") {
        APIFY_STORE_GOAL = actEl.dataset.goal || "";
        await loadApifyStoreTab();
      } else if (act === "apify-store-search" || act === "apify-store-refresh") {
        await loadApifyStoreTab();
      } else if (act === "apify-store-sync") {
        toast("Đang khởi chạy quét & lưu toàn bộ 16,000+ Actors từ Apify Store...");
        const res = await api("/api/apify-store/sync", "POST", { background: true, max_pages: 25, page_size: 1000 });
        toast(res.summary || "Đang đồng bộ Apify Store dưới nền!");
        setTimeout(() => {
          syncSidebarCountsAndRefs();
          if (CURRENT_TAB === "apifystore") loadApifyStoreTab();
        }, 4000);
      } else if (act === "apify-open-actor") {
        await openApifyActorCallModal(actEl.dataset.slug);
      } else if (act === "apify-exec-call") {
        let parsedPayload = {};
        try {
          parsedPayload = JSON.parse(document.getElementById("mApifyCallPayload").value || "{}");
        } catch (_) {
          toast("JSON Payload không hợp lệ — hãy kiểm tra dấu ngoặc kép!", true);
          return;
        }
        const maxChg = Number(document.getElementById("mApifyMaxCharge").value || 0.06);
        const saveVault = Boolean(document.getElementById("mApifySaveVault")?.checked);
        toast(`Đang gọi trực tiếp Actor ${actEl.dataset.slug.replace("~", "/")}...`);
        const res = await api("/api/apify-store/call", "POST", {
          actor_slug: actEl.dataset.slug,
          payload: parsedPayload,
          max_charge_usd: maxChg,
          save_products_to_vault: saveVault,
        });
        closeModal();
        document.getElementById("apifyStoreCallResultBox").innerHTML = `
          <div class="card" style="border-color:rgba(16,185,129,0.5);background:#071422">
            <div class="row" style="justify-content:space-between;margin-bottom:6px">
              <strong style="color:#6ee7b7">✅ ${esc(res.summary)}</strong>
              <button class="btn btn-sm" onclick="this.closest('.card').remove()">✕ Đóng</button>
            </div>
            <pre class="codebox" style="max-height:280px">${esc(JSON.stringify(res.items.slice(0, 10), null, 2))}</pre>
          </div>`;
        toast(res.summary);
        syncSidebarCountsAndRefs();
      } else if (act === "kalo-sync-affiliate") {
        const res = await api("/api/kalodata/sync-from-affiliate", "POST", {});
        toast(res.summary || "Đã đồng bộ tài khoản Kalodata từ affiliate-peng!");
        await loadSettings();
      } else if (act === "eco-check-portals") {
        const st = await api("/api/kalodata/status");
        toast(
          `Profile ${st.profile_name} (CDP ${st.cdp_port || "đóng"}): Kalodata=${st.kalodata_session?.logged_in ? "ĐÃ ĐĂNG NHẬP" : "Chưa mở"} · Global Selling=${st.affiliate_global_selling_session?.ready ? "SẴN SÀNG" : "Chưa mở"}`
        );
        if (CURRENT_TAB === "ecosystems") await loadEcosystemsTab();
        else if (CURRENT_TAB === "settings") await loadSettings();
      } else if (act === "eco-refresh") {
        await loadEcosystemsTab();
      } else if (act === "eco-preset-xteink") {
        document.getElementById("ecoName").value = "Phụ kiện Xteink X4";
        document.getElementById("ecoSeedKw").value = "xteink";
        document.getElementById("ecoExtraKws").value = "xteink x4";
        document.getElementById("ecoTargetFocus").value = "Bán phụ kiện cho máy đọc sách mini Xteink X4: tìm SP & Shop trên Shopee VN + TikTok, ưu tiên lượt bán gần đây & tồn kho, mở rộng phụ kiện thay thế/bổ sung trên Pinduoduo & Taobao";
        document.querySelectorAll(".eco-cn").forEach((el) => { el.checked = true; });
        document.getElementById("ecoDailySched").checked = true;
        toast("Đã nạp cấu hình Mẫu 1: Hệ sinh thái Phụ kiện Xteink X4!");
      } else if (act === "eco-preset-goojodoq") {
        document.getElementById("ecoName").value = "Phụ kiện Goojodoq";
        document.getElementById("ecoSeedKw").value = "goojodoq";
        document.getElementById("ecoExtraKws").value = "phụ kiện goojodoq";
        document.getElementById("ecoTargetFocus").value = "Lập Index lần 1 phụ kiện Goojodoq trên TikTokShop VN & Shopee VN, lên lịch cào mới hàng ngày phát hiện SP mới, kết hợp tìm Creator & Video bán hiệu quả qua Affiliate Global Selling + Kalodata VN";
        document.getElementById("ecoDailySched").checked = true;
        document.getElementById("ecoEnableKalodata").checked = true;
        document.getElementById("ecoEnableGlobalSelling").checked = true;
        toast("Đã nạp cấu hình Mẫu 2: Phụ kiện Goojodoq + Index Hàng ngày + Creator Kalodata/Global Selling!");
      } else if (act === "eco-run") {
        const name = document.getElementById("ecoName").value.trim();
        const seed = document.getElementById("ecoSeedKw").value.trim();
        const extra = document.getElementById("ecoExtraKws").value.trim();
        const focus = document.getElementById("ecoTargetFocus").value.trim();
        const chs = [...document.querySelectorAll(".eco-ch:checked")].map((c) => c.value);
        const cns = [...document.querySelectorAll(".eco-cn:checked")].map((c) => c.value);
        document.getElementById("ecoActiveDetailBox").innerHTML = `<div class="card">⏳ Đang thực thi trọn luồng Hệ sinh thái <strong>"${esc(name || seed)}"</strong> (Quét Shopee VN + TikTokShop VN &rarr; Chấm Jev &amp; Tồn kho &rarr; Theo dõi đặc biệt + Theo dõi Shop &rarr; Nguồn Phụ kiện PDD/Taobao &rarr; Creator Kalodata/Global Selling)...</div>`;
        const res = await api("/api/ecosystems/run", "POST", {
          name: name || `Phụ kiện ${seed}`,
          seed_keyword: seed,
          extra_keywords: extra,
          target_focus: focus,
          channels: chs,
          cn_platforms: cns,
          enable_cn_expansion: cns.length > 0,
          daily_schedule_enabled: document.getElementById("ecoDailySched").checked,
          enable_kalodata: document.getElementById("ecoEnableKalodata").checked,
          enable_global_selling_creators: document.getElementById("ecoEnableGlobalSelling").checked,
        });
        toast(res.summary);
        await syncSidebarCountsAndRefs();
        await loadEcosystemsTab(res.collection?.collection_id);
      } else if (act === "eco-open-col") {
        await loadEcosystemsTab(actEl.dataset.id);
      } else if (act === "eco-check-daily") {
        toast("Đang cào mới & đối chiếu với Index gốc để tìm SP mới lên sàn & biến động tồn kho...");
        const res = await api(`/api/ecosystems/${encodeURIComponent(actEl.dataset.id)}/check-daily`, "POST", {});
        toast(res.summary);
        await syncSidebarCountsAndRefs();
        renderEcosystemDetail(res.collection);
      } else if (act === "eco-toggle-sched") {
        const res = await api(`/api/ecosystems/${encodeURIComponent(actEl.dataset.id)}`, "PATCH", {
          daily_schedule_enabled: actEl.dataset.on === "1",
        });
        toast(res.summary);
        renderEcosystemDetail(res.collection);
      } else if (act === "eco-delete") {
        await api(`/api/ecosystems/${encodeURIComponent(actEl.dataset.id)}`, "DELETE");
        ACTIVE_ECO_ID = "";
        await syncSidebarCountsAndRefs();
        await loadEcosystemsTab();
      } else if (act === "eco-send-to-clone") {
        document.getElementById("vcUrl").value = actEl.dataset.url || "";
        document.getElementById("vcProdName").value = actEl.dataset.prod || "";
        showTab("videoclone", "/clone-video");
      } else if (act === "hunt-prefill-schedule") {
        const kw = document.getElementById("huntKeywords")?.value.trim() || "";
        if (kw) document.getElementById("hsKeywords").value = kw;
        if (!document.getElementById("hsName").value.trim() && kw) {
          document.getElementById("hsName").value = `Săn Hàng ngày: ${kw.slice(0, 48)}`;
        }
        document.getElementById("huntScheduleCard")?.scrollIntoView({ behavior: "smooth", block: "center" });
        toast("Đã nạp từ khoá & kênh chọn vào khung Lịch Săn Lặp lại — chọn giờ rồi bấm Tạo!");
      } else if (act === "pp-prefill-schedule") {
        const tp = document.getElementById("ppTopicInput")?.value.trim() || "";
        if (tp) document.getElementById("hsKeywords").value = tp;
        document.querySelectorAll(".pp-ch:checked").forEach((el) => {
          const hChk = document.querySelector(`.hunt-ch[value="${el.value}"]`);
          if (hChk) hChk.checked = true;
        });
        if (!document.getElementById("hsName").value.trim() && tp) {
          document.getElementById("hsName").value = `Săn Painpoint Hàng ngày: ${tp.slice(0, 42)}`;
        }
        document.getElementById("huntScheduleCard")?.scrollIntoView({ behavior: "smooth", block: "center" });
        toast("Đã đưa chủ đề & kênh MXH lên Lịch Săn Lặp lại!");
      } else if (act === "hsched-refresh") {
        await loadHuntSchedules();
      } else if (act === "hsched-close-detail") {
        document.getElementById("huntScheduleRunDetailBox").innerHTML = "";
      } else if (act === "hsched-create") {
        const kws = document.getElementById("hsKeywords").value.trim() || document.getElementById("huntKeywords").value.trim();
        const pinned = document.getElementById("hsPinnedProducts").value.trim();
        const chs = [...document.querySelectorAll(".hunt-ch:checked")].map((c) => c.value);
        const runNow = document.getElementById("hsRunNow").checked;
        if (runNow) {
          document.getElementById("huntScheduleRunDetailBox").innerHTML = `<div class="card">⏳ Đang tạo lịch &amp; chạy phiên Mốc gốc lần 1 (Quét Từ khoá/Painpoint &rarr; 300+desk Tổng hợp &rarr; Jev Chấm điểm &amp; Phân loại Kho)...</div>`;
        }
        const res = await api("/api/hunt/schedules", "POST", {
          name: document.getElementById("hsName").value.trim(),
          keywords: kws,
          pinned_products: pinned,
          channels: chs,
          shopee_filters: collectHuntShopeeFilters(),
          items_per_channel: Number(document.getElementById("huntLimit")?.value || 8),
          schedule_mode: document.getElementById("hsMode").value,
          daily_time: document.getElementById("hsDailyTime").value || "07:30",
          interval_hours: Number(document.getElementById("hsIntervalHours").value || 24),
          use_300desk: document.getElementById("hsUse300Desk").checked,
          auto_score_jev: document.getElementById("hsAutoJev").checked,
          auto_classify_buckets: document.getElementById("hsAutoJev").checked,
          auto_promote_strong_pick: document.getElementById("hsAutoPromote").checked,
          run_immediately: runNow,
        });
        toast(res.summary);
        if (res.first_run) renderHuntScheduleRunDetail(res.first_run);
        await syncSidebarCountsAndRefs();
        await loadHuntSchedules();
      } else if (act === "hsched-run-now") {
        document.getElementById("huntScheduleRunDetailBox").innerHTML = `<div class="card">⏳ Đang chạy phiên Săn Lặp lại (Quét &amp; So sánh SP mới &rarr; 300+desk Tổng hợp &rarr; Jev Chấm điểm &amp; Phân loại Kho)...</div>`;
        const res = await api(`/api/hunt/schedules/${encodeURIComponent(actEl.dataset.id)}/run`, "POST", {});
        toast(res.summary);
        if (res.run) renderHuntScheduleRunDetail(res.run);
        await syncSidebarCountsAndRefs();
        await loadHuntSchedules();
      } else if (act === "hsched-open-run") {
        const res = await api(`/api/hunt/schedules/runs/${encodeURIComponent(actEl.dataset.id)}`);
        if (res.run) renderHuntScheduleRunDetail(res.run, res.bucket_labels);
      } else if (act === "hsched-open-history") {
        const res = await api(`/api/hunt/schedules/${encodeURIComponent(actEl.dataset.id)}`);
        const s = res.schedule;
        const runs = s?.runs || [];
        openModal(
          `📜 Lịch sử các phiên quét — ${s?.name || ""}`,
          runs.length
            ? `<table class="tbl">
                <thead><tr><th>Thời gian</th><th>Kích hoạt</th><th>Tổng SP</th><th>SP mới</th><th>Tăng bán</th><th>300+desk</th><th>Jev Strong Pick</th><th>Tổng hợp 300+desk</th><th>Xem</th></tr></thead>
                <tbody>
                  ${runs.map((r) => `
                    <tr>
                      <td>${fmtTime(r.created_at)}</td>
                      <td><code>${esc(r.trigger_kind)}</code></td>
                      <td>${r.total_sampled}</td>
                      <td><span class="badge green">+${r.new_products_count}</span></td>
                      <td><span class="badge gold">${r.rising_products_count}</span></td>
                      <td>${r.desk300_nnn ? `#${esc(r.desk300_nnn)}` : "—"}</td>
                      <td><strong>${r.strong_pick_count}</strong></td>
                      <td style="font-size:11.5px;max-width:300px">${esc((r.desk_synthesis_text || "").slice(0, 140))}</td>
                      <td><button class="btn btn-sm btn-pri" onclick="document.getElementById('mainModalBackdrop').classList.remove('open')" data-action="hsched-open-run" data-id="${esc(r.run_id)}">📊 Mở</button></td>
                    </tr>`).join("")}
                </tbody>
              </table>`
            : `<div style="color:var(--muted)">Chưa có phiên chạy nào cho lịch săn này.</div>`
        );
      } else if (act === "hsched-toggle-status") {
        const res = await api(`/api/hunt/schedules/${encodeURIComponent(actEl.dataset.id)}/${actEl.dataset.st}`, "POST", {});
        toast(res.summary);
        await loadHuntSchedules();
      } else if (act === "hsched-delete") {
        await api(`/api/hunt/schedules/${encodeURIComponent(actEl.dataset.id)}`, "DELETE");
        toast("Đã xoá lịch săn lặp lại!");
        await loadHuntSchedules();
      } else if (act === "jr-refresh" || act === "jr-apply-filter") {
        await loadJevLeaderboard();
      } else if (act === "jr-reset-filter") {
        document.getElementById("jrRankBy").value = "overall_10";
        document.getElementById("jrTier").value = "all";
        document.getElementById("jrPlatform").value = "";
        document.getElementById("jrIndustry").value = "";
        document.getElementById("jrMinScore").value = "0";
        document.getElementById("jrSearchQ").value = "";
        await loadJevLeaderboard();
      } else if (act === "jr-chip-ind") {
        document.getElementById("jrIndustry").value = actEl.dataset.ind || "";
        await loadJevLeaderboard();
      } else if (act === "jr-score-top-unscored") {
        const lim = Number(actEl.dataset.limit || 15);
        toast(`Đang dùng TypeSafe Jev AI chấm điểm Top ${lim} SP có lượt bán cao nhất chưa chấm...`);
        const res = await api("/api/products/score-unscored", "POST", { limit: lim });
        toast(res.summary);
        await syncSidebarCountsAndRefs();
        await loadJevLeaderboard();
      } else if (act === "jr-rescore-one") {
        toast(`Đang chấm lại điểm Jev AI cho SP #${actEl.dataset.id}...`);
        const res = await api(`/api/products/${actEl.dataset.id}/score-jev`, "POST", {});
        toast(res.summary);
        await loadJevLeaderboard();
      } else if (act === "kalo-preset-cat") {
        const sel = document.getElementById("kaloHuntCategorySelect");
        if (sel) sel.value = actEl.dataset.cat || "";
        toast("Đã chọn Ngành hàng Kalodata — bấm «Quét Kalodata VN» để chạy!");
      } else if (act === "kalo-preset-kw") {
        const inp = document.getElementById("kaloHuntInput");
        if (inp) inp.value = actEl.dataset.kw || "";
      } else if (act === "kalo-cat-leaderboard") {
        const win = document.getElementById("kaloHuntWindow")?.value || "7d";
        document.getElementById("kalodataHuntResultBox").innerHTML = `<div class="card">⏳ Đang quét BXH Toàn Ngành TikTok Shop VN trên Kalodata ($0.00)...</div>`;
        const res = await api(`/api/hunt/kalodata-vn/category-leaderboard?window_spec=${encodeURIComponent(win)}&limit=25`);
        renderKalodataProResult(res, "kalodataHuntResultBox");
      } else if (act === "kalo-hunt-run") {
        const catId = document.getElementById("kaloHuntCategorySelect")?.value || "";
        const kw = document.getElementById("kaloHuntInput")?.value.trim() || "";
        const win = document.getElementById("kaloHuntWindow")?.value || "7d";
        const lim = Number(document.getElementById("kaloHuntLimitProducts")?.value || 25);
        document.getElementById("kalodataHuntResultBox").innerHTML = `<div class="card">⏳ Đang quét trực tiếp Kalodata VN ($0.00 CDP) &amp; phân loại SP / Video / KOC...</div>`;
        const res = await api("/api/hunt/kalodata-vn", "POST", {
          category_id: catId,
          keywords: kw ? [kw] : [],
          window_spec: win,
          limit_products: lim,
          limit_videos: 15,
          include_videos: document.getElementById("kaloHuntVideosChk")?.checked ?? true,
          auto_ingest_suitable: document.getElementById("kaloHuntAutoIngestChk")?.checked ?? true,
          use_300desk: document.getElementById("kaloHuntDeskChk")?.checked ?? false,
          score_jev: document.getElementById("kaloHuntScoreJevChk")?.checked ?? true,
        });
        renderKalodataHuntResult(res);
        await loadKalodataCategoriesAndHuntHistory();
        await syncSidebarCountsAndRefs();
        toast(`Kalodata VN hoàn tất: ${res.products_count} SP (${res.suitable_products_count} phù hợp) · ${res.videos_count} Video!`);
      } else if (act === "kalopro-reload-history") {
        await loadKalodataProTab(true);
      } else if (act === "kalopro-open-snap") {
        const snap = await api(`/api/hunt/kalodata-pro/snapshot/${encodeURIComponent(actEl.dataset.id)}`);
        renderKalodataProResult(snap, "kaloProDedicatedResultBox");
      } else if (act === "kalopro-act") {
        const mod = actEl.dataset.mod;
        const catId = document.getElementById("kaloProPageCatSelect")?.value || "";
        const kw = document.getElementById("kaloProPageKwInput")?.value.trim() || "";
        const win = document.getElementById("kaloProPageWindow")?.value || "7d";
        const lim = Number(document.getElementById("kaloProPageLimit")?.value || 25);
        document.getElementById("kaloProDedicatedResultBox").innerHTML = `<div style="color:#6ee7b7">⏳ Đang quét trực tiếp phân trang Kalodata Pro (${esc(mod)}) trên Chrome Chuyên Dụng ($0.00)...</div>`;
        let res;
        if (mod === "shops_aff") {
          res = await api("/api/hunt/kalodata-pro/shops", "POST", { keyword: kw, category_id: catId, window_spec: win, preset: "all", limit: lim });
        } else if (mod === "brands") {
          res = await api("/api/hunt/kalodata-pro/brands", "POST", { keyword: kw, category_id: catId, window_spec: win, limit: lim });
        } else if (mod === "creators") {
          res = await api("/api/hunt/kalodata-pro/creators", "POST", { keyword: kw, category_id: catId, window_spec: win, auto_save_vault: true, limit: lim });
        } else if (mod === "livestreams") {
          res = await api("/api/hunt/kalodata-pro/livestreams", "POST", { keyword: kw, category_id: catId, window_spec: win, limit: lim });
        } else if (mod === "category_board") {
          res = await api(`/api/hunt/kalodata-vn/category-leaderboard?window_spec=${encodeURIComponent(win)}&limit=${lim}`);
        } else {
          const fm = mod === "ai_videos" ? "ai_video" : mod === "roas_videos" ? "high_roas_ads" : "low_follower_viral";
          res = await api("/api/hunt/kalodata-pro/videos-advanced", "POST", { keyword: kw, category_id: catId, window_spec: win, filter_mode: fm, limit: lim });
        }
        renderKalodataProResult(res, "kaloProDedicatedResultBox");
        await loadKalodataProTab(false);
        await syncSidebarCountsAndRefs();
        toast(`Đã quét xong ${res.items_count || 0} mục từ Kalodata Pro ($0.00)!`);
      } else if (act === "kalopro-deep-inspect") {
        const tgt = actEl.dataset.target || document.getElementById("kaloProDeepInput")?.value.trim() || "";
        if (!tgt) {
          toast("Hãy nhập ID 19 chữ số hoặc Link Sản phẩm / Video TikTok!", true);
          return;
        }
        if (actEl.dataset.target && document.getElementById("kaloProDeepInput")) {
          document.getElementById("kaloProDeepInput").value = tgt;
          if (CURRENT_TAB !== "kalopro") showTab("kalopro", "/kalodata-pro");
        }
        document.getElementById("kaloProDedicatedResultBox").innerHTML = `<div style="color:#7dd3fc">🔬 Đang mổ xẻ sâu <code>${esc(tgt)}</code> trên Kalodata Pro &amp; trích xuất SKU tồn kho / MP4 không logo ($0.00)...</div>`;
        const res = await api("/api/hunt/kalodata-pro/deep-detail", "POST", { target: tgt, save_to_vault: true });
        renderKalodataProResult(res, "kaloProDedicatedResultBox");
        await loadKalodataProTab(false);
        await syncSidebarCountsAndRefs();
      } else if (act === "kalo-send-sourcing") {
        const q = actEl.dataset.q || "";
        showTab("sourcing", "/nguon-hang-tq");
        const inp = document.getElementById("srcQuery");
        if (inp) inp.value = q;
        toast("Đã chuyển tên SP sang tab Tìm Nguồn 1688 · PDD · Taobao!");
      } else if (act === "kalo-send-videojev") {
        const u = actEl.dataset.url || "";
        showTab("videojev", "/video-jev");
        const inp = document.getElementById("vjUrl");
        if (inp) inp.value = u;
        toast("Đã nạp Link Video sang tab Đánh giá Video Jev AI!");
      } else if (act === "kalo-rotate-account") {
        const box = document.getElementById("kaloRotateLogsBox");
        if (box) box.innerHTML = "⏳ Đang logout phiên Kalodata cũ trên Chrome Chuyên Dụng, đăng nhập tài khoản mới & đồng bộ Telegram...";
        const res = await api("/api/kalodata/rotate-account", "POST", {
          account_email: document.getElementById("setKaloEmail")?.value || "",
          password: document.getElementById("setKaloPassword")?.value || "",
          market: document.getElementById("setKaloMarket")?.value || "VN",
          currency: document.getElementById("setKaloCurrency")?.value || "VND",
          default_window_days: Number(document.getElementById("setKaloWindow")?.value || 7),
        });
        if (box) {
          box.innerHTML = `<pre class="codebox" style="margin:0;max-height:160px">${esc((res.step_logs || []).join("\n"))}</pre>`;
        }
        toast(res.ok ? "✅ Đổi tài khoản Kalodata thành công & đã báo Telegram!" : (res.error_message || res.status), !res.ok);
        await loadSettings();
      } else if (act === "kalo-check-quota") {
        const q = await api("/api/kalodata/quota");
        toast(`${q.plan_label_vi || q.status} (${q.account_email || "—"})`, !q.ok);
      } else if (act === "kimp-fill-sample") {
        document.getElementById("impRawText").value = JSON.stringify(
          [
            {
              product_id: "1729483920192837465",
              product_name: "Quạt cầm tay mini sò lạnh 100 cấp độ gió",
              price: "189000",
              gmv: "245000000",
              video_gmv: "198000000",
              units_sold: "1290",
              commission_pct: "12",
              creators_count: "18",
            },
            {
              product_id: "1729483920192837466",
              product_name: "Kệ góc nhà tắm hút chân không xoay 360",
              price: "115000",
              gmv: "132000000",
              video_gmv: "110000000",
              units_sold: "1140",
              commission_pct: "15",
              creators_count: "11",
            },
          ],
          null,
          2
        );
        toast("Đã điền dữ liệu mẫu Kalodata VN 7d — bấm «1. Xem trước»!");
      } else if (act === "kimp-preview") {
        await runKalodataImportPreview();
      } else if (act === "kimp-commit") {
        if (!CURRENT_KALO_IMPORT_BATCH_ID) return;
        const res = await api(`/api/imports/${encodeURIComponent(CURRENT_KALO_IMPORT_BATCH_ID)}/commit`, "POST", { allow_skip_invalid: true });
        document.getElementById("btnCommitKaloImport").disabled = true;
        toast(`✅ Đã commit lô ${res.batch_id}: +${res.summary?.committed_products || 0} SP, +${res.summary?.committed_creators || 0} KOC, +${res.summary?.committed_videos || 0} Video!`);
        await loadKalodataImportTab();
        await syncSidebarCountsAndRefs();
      } else if (act === "kcap-current" || act === "kcap-bounded") {
        const bounded = act === "kcap-bounded";
        document.getElementById("klCapturePreviewBox").innerHTML = `<div style="color:#7dd3fc">⏳ Đang đọc bảng Kalodata trên Chrome Chuyên Dụng (${bounded ? "Đa trang" : "1 trang"})...</div>`;
        const cap = await api(bounded ? "/api/kalodata/captures/bounded-pages" : "/api/kalodata/captures/current-page", "POST", {
          entity_type: document.getElementById("klCapEntity")?.value || "",
          window_spec: document.getElementById("klCapWindow")?.value || "7d",
          market: document.getElementById("impMarket")?.value || "VN",
          currency: document.getElementById("impCurrency")?.value || "VND",
          max_pages: Number(document.getElementById("klCapMaxPages")?.value || 3),
          max_rows: Number(document.getElementById("klCapMaxRows")?.value || 50),
        });
        renderKalodataCapturePreview(cap);
        await loadKalodataImportTab();
      } else if (act === "kcap-open") {
        const cap = await api(`/api/kalodata/captures/${encodeURIComponent(actEl.dataset.id)}`);
        renderKalodataCapturePreview(cap);
      } else if (act === "kcap-commit") {
        const res = await api(`/api/kalodata/captures/${encodeURIComponent(actEl.dataset.id)}/commit`, "POST", {});
        toast(`✅ Đã nạp bảng chụp vào Kho (Lô ${res.committed_batch_id})!`);
        renderKalodataCapturePreview(res.capture);
        await loadKalodataImportTab();
        await syncSidebarCountsAndRefs();
      }
    } catch (err) {
      toast(err.message || "Có lỗi xảy ra", true);
    }
  });

  // --- KALODATA PRO 9-PAGE, DIRECT HUNTER, IMPORT WIZARD & BROWSER CAPTURE ---
  let KALO_CATS_LOADED = false;
  let CURRENT_KALO_IMPORT_BATCH_ID = "";

  async function loadKalodataCategoriesAndHuntHistory() {
    try {
      const [catRes, histRes] = await Promise.all([
        KALO_CATS_LOADED ? Promise.resolve(null) : api("/api/hunt/kalodata-vn/categories"),
        api("/api/hunt/kalodata-vn/history"),
      ]);
      if (catRes?.items) {
        const opts = catRes.items
          .map((c) => `<option value="${esc(c.id)}">${esc(c.icon)} [${esc(c.level)}] ${esc(c.vi)} (${esc(c.zh)})</option>`)
          .join("");
        const s1 = document.getElementById("kaloHuntCategorySelect");
        if (s1) s1.innerHTML = `<option value="">📂 Tất cả Ngành hàng (Không lọc ngành)</option>` + opts;
        const s2 = document.getElementById("kaloProPageCatSelect");
        if (s2) s2.innerHTML = `<option value="">📂 Tất cả Ngành hàng TikTok Shop VN</option>` + opts;
        KALO_CATS_LOADED = true;
      }
      const hSel = document.getElementById("kaloHuntHistorySelect");
      if (hSel && histRes?.items) {
        hSel.innerHTML =
          `<option value="">🕒 Lịch sử quét Kalodata VN (${histRes.items.length})...</option>` +
          histRes.items
            .map(
              (r) =>
                `<option value="${esc(r.run_id)}">${esc((r.keywords || []).join(", ") || r.category_id)} · ${r.products_total} SP (${r.window_spec})</option>`
            )
            .join("");
      }
    } catch (_) {}
  }

  function renderKalodataHuntResult(r) {
    const box = document.getElementById("kalodataHuntResultBox");
    if (!box || !r) return;
    const prods = r.products || [];
    const vids = r.videos || [];
    const crs = r.creators || [];
    box.innerHTML = `
      <div style="padding:10px;border-radius:8px;background:#081221;border:1px solid var(--border)">
        <div class="row" style="justify-content:space-between;margin-bottom:8px">
          <div class="row">
            <span class="badge green">📊 ${r.products_count || prods.length} SP (${r.suitable_products_count || 0} phù hợp)</span>
            <span class="badge blue">🎬 ${r.videos_count || vids.length} Video GPM/ROAS</span>
            <span class="badge gold">👤 ${r.creators_count || crs.length} KOC</span>
            ${r.desk300_nnn ? `<span class="badge gold">🤖 300+desk #${esc(r.desk300_nnn)}</span>` : ""}
            ${r.jev_scored_count ? `<span class="badge green">🎯 Đã chấm Jev: ${r.jev_scored_count} SP</span>` : ""}
          </div>
          <div class="row">
            ${r.run_id ? `<a class="btn btn-sm btn-gold" href="/api/hunt/kalodata-vn/${encodeURIComponent(r.run_id)}/export.csv">⬇️ Tải CSV Toàn Bộ (${prods.length} SP)</a>` : ""}
            <button class="btn btn-sm btn-pri" data-action="jump-kho-all">🗂 Mở Kho SP (${(r.saved_product_ids || []).length} đã lưu)</button>
          </div>
        </div>
        ${prods.length ? `
          <table class="tbl">
            <thead><tr><th>#</th><th>Sản phẩm TikTok Shop VN</th><th>Giá bán</th><th>GMV (${esc(r.window_spec)})</th><th>Đơn bán</th><th>Video / Live GMV</th><th>HH / KOC</th><th>Phân loại</th><th>Thao tác</th></tr></thead>
            <tbody>
              ${prods.slice(0, 150).map((p) => `
                <tr>
                  <td>${p.rank}</td>
                  <td>
                    <a href="${esc(p.canonical_url)}" target="_blank" style="color:#93c5fd;font-weight:600">${esc(p.product_title)}</a>
                    <div style="font-size:11px;color:var(--muted)">ID: <code>${esc(p.native_product_id)}</code> ${p.gmv_growth_pct != null ? `· Tăng trưởng: <strong>${p.gmv_growth_pct > 0 ? "+" : ""}${p.gmv_growth_pct}%</strong>` : ""}</div>
                  </td>
                  <td>${p.price_vnd ? vnd(p.price_vnd) : "—"}</td>
                  <td><strong style="color:#6ee7b7">${esc(p.gmv_total_display)}</strong></td>
                  <td>${p.units_sold_window ?? "—"}</td>
                  <td style="font-size:11.5px">🎬 ${esc(p.video_gmv_display)}<br/>🔴 ${esc(p.live_gmv_display)}</td>
                  <td style="font-size:11.5px">${p.commission_pct != null ? `${p.commission_pct}%` : "—"} · ${p.active_creators_count ?? "—"} KOC</td>
                  <td style="font-size:11.5px">${esc(p.classification?.suitability_label || "")}</td>
                  <td>
                    <div class="row" style="gap:4px">
                      <button class="btn btn-sm btn-blue" data-action="kalopro-deep-inspect" data-target="${esc(p.native_product_id)}">🔬 Mổ SKU</button>
                      <button class="btn btn-sm" data-action="kalo-send-sourcing" data-q="${esc(p.product_title)}">🇨🇳 1688</button>
                    </div>
                  </td>
                </tr>`).join("")}
            </tbody>
          </table>` : `<div style="color:var(--muted)">Không tìm thấy sản phẩm phù hợp.</div>`}
      </div>`;
  }

  async function loadKalodataProTab(forceRenderLatest = false) {
    await loadKalodataCategoriesAndHuntHistory();
    try {
      const [hist, qSt] = await Promise.all([
        api("/api/hunt/kalodata-pro/history"),
        api("/api/kalodata/status").catch(() => null),
      ]);
      const snaps = hist.items || [];
      const elCnt = document.getElementById("cntKaloProSnaps");
      if (elCnt) elCnt.textContent = snaps.length;
      const badge = document.getElementById("kaloProPlanBadge");
      if (badge && qSt) {
        badge.textContent = qSt.kalodata_session?.logged_in
          ? `✅ Đã kết nối Kalodata (${qSt.account_email || "peng_dedicated"})`
          : `⚪ Chrome peng_dedicated (${qSt.account_email || "bấm Mở Kalodata"})`;
      }
      const pills = document.getElementById("kaloProHistoryPills");
      if (pills) {
        pills.innerHTML = snaps.length
          ? snaps
              .map(
                (s) =>
                  `<button type="button" class="chip" data-action="kalopro-open-snap" data-id="${esc(s.snap_id)}">📌 [${esc(s.module_kind)}] ${esc(s.target_query || "Toàn sàn VN")} (${s.items_count})</button>`
              )
              .join("")
          : `<span style="color:var(--muted);font-size:12px">Chưa có phiên quét nào — hãy bấm chọn 1 phân trang phía trên!</span>`;
      }
      if ((forceRenderLatest || document.getElementById("kaloProDedicatedResultBox")?.children.length <= 1) && hist.latest) {
        renderKalodataProResult(hist.latest, "kaloProDedicatedResultBox");
      }
    } catch (_) {}
  }

  function renderKalodataProResult(data, targetBoxId) {
    const box = document.getElementById(targetBoxId);
    if (!box || !data) return;

    if (data.detail_kind === "video") {
      box.innerHTML = `
        <div>
          <div class="row" style="justify-content:space-between;margin-bottom:10px">
            <h3 style="margin:0;color:#7dd3fc">🔬 Mổ Xẻ Sâu Video Bán Hàng #<code>${esc(data.video_id)}</code> (@${esc(data.author_handle || "_")})</h3>
            <div class="row">
              ${data.mp4_cdn_url ? `<a class="btn btn-sm btn-pri" href="${esc(data.mp4_cdn_url)}" target="_blank">⬇️ Mở / Tải MP4 Không Watermark (0₫)</a>` : ""}
              <button class="btn btn-sm btn-gold" data-action="eco-send-to-clone" data-url="${esc(data.mp4_cdn_url || data.tiktok_url)}" data-prod="${esc(data.caption || "")}">⚡ Đưa sang Clone Video 15s</button>
              <button class="btn btn-sm" data-action="kalo-send-videojev" data-url="${esc(data.mp4_cdn_url || data.tiktok_url)}">🎬 Chấm Video Jev</button>
            </div>
          </div>
          <div class="row" style="margin-bottom:10px">
            <span class="badge green">GMV: ${esc(data.gmv_display)}</span>
            <span class="badge blue">Đơn bán: ${data.units_sold ?? "—"} · Views: ${data.views_count ?? "—"}</span>
            <span class="badge gold">Ads ROAS: ${data.ad_roas ?? "—"} · Chi Ads: ${esc(data.ad_spend_display)} (${data.ad_flight_days || 0} ngày)</span>
          </div>
          <p style="font-size:12.5px;color:#cbd5e1">${esc(data.caption || "")}</p>
          ${(data.linked_products || []).length ? `
            <h4>🛒 Sản phẩm gắn trong Video (${data.linked_products.length})</h4>
            <table class="tbl">
              <thead><tr><th>Mã SP</th><th>Tên sản phẩm</th><th>Giá</th><th>GMV</th><th>Tỷ trọng</th><th>Mổ xẻ</th></tr></thead>
              <tbody>${data.linked_products.map((lp) => `
                <tr>
                  <td><code>${esc(lp.product_id)}</code></td>
                  <td>${esc(lp.title)}</td>
                  <td>${lp.price_vnd ? vnd(lp.price_vnd) : "—"}</td>
                  <td>${esc(lp.gmv_display)}</td>
                  <td>${lp.share_pct != null ? `${lp.share_pct}%` : "—"}</td>
                  <td><button class="btn btn-sm btn-blue" data-action="kalopro-deep-inspect" data-target="${esc(lp.product_id)}">🔬 Mổ SP</button></td>
                </tr>`).join("")}
              </tbody>
            </table>` : ""}
        </div>`;
      return;
    }

    if (data.detail_kind === "product") {
      const cs = data.channel_split || {};
      box.innerHTML = `
        <div>
          <div class="row" style="justify-content:space-between;margin-bottom:10px">
            <h3 style="margin:0;color:#6ee7b7">🔬 Mổ Xẻ Sâu Sản Phẩm #<code>${esc(data.product_id)}</code> — ${esc(data.title)}</h3>
            <div class="row">
              <button class="btn btn-sm btn-pri" data-action="kalo-send-sourcing" data-q="${esc(data.title)}">🇨🇳 Tìm Nguồn 1688 / Taobao</button>
              ${data.vault_product_id ? `<button class="btn btn-sm btn-gold" data-action="jr-rescore-one" data-id="${data.vault_product_id}">🎯 Chấm Jev SP #${data.vault_product_id}</button>` : ""}
              <a class="btn btn-sm" href="${esc(data.tiktok_shop_url)}" target="_blank">🛒 Mở TikTok Shop</a>
            </div>
          </div>
          <div class="row" style="margin-bottom:10px">
            <span class="badge green">GMV 7d: ${esc(data.gmv_7d_display)}</span>
            <span class="badge blue">Giá: ${data.price_vnd ? vnd(data.price_vnd) : "—"} · HH: ${data.commission_pct != null ? `${data.commission_pct}%` : "—"}</span>
            <span class="badge gold">Tỷ trọng: 🎬 Video ${cs.video_pct ?? "—"}% · 🔴 Live ${cs.live_pct ?? "—"}% · 🏬 Thẻ SP ${cs.product_card_pct ?? "—"}%</span>
            ${data.total_sku_stock != null ? `<span class="badge green">📦 Tổng tồn kho SKU: ${Number(data.total_sku_stock).toLocaleString("vi-VN")}</span>` : ""}
          </div>
          ${data.ai_selling_points ? `<div style="padding:8px 10px;border-radius:8px;background:#081221;margin-bottom:10px;font-size:12.5px">💡 <strong>Điểm bán hàng AI (Kalodata):</strong> ${esc(data.ai_selling_points)}</div>` : ""}
          ${(data.skus || []).length ? `
            <h4>📦 Phân tích Biến thể SKU &amp; Tồn kho (${data.skus.length} SKU)</h4>
            <table class="tbl" style="margin-bottom:12px">
              <thead><tr><th>Tên phân loại SKU</th><th>Tỷ trọng bán (%)</th><th>Giá bán</th><th>Tồn kho hiện tại</th></tr></thead>
              <tbody>${data.skus.map((s) => `
                <tr>
                  <td><strong>${esc(s.sku_name)}</strong></td>
                  <td>${s.sales_share_pct != null ? `${s.sales_share_pct}%` : "—"}</td>
                  <td>${s.price_vnd ? vnd(s.price_vnd) : "—"}</td>
                  <td><strong>${s.stock_count != null ? Number(s.stock_count).toLocaleString("vi-VN") : "—"}</strong></td>
                </tr>`).join("")}
              </tbody>
            </table>` : ""}
          ${(data.top_videos || []).length ? `
            <h4>🎬 Top Video kéo đơn của Sản phẩm (${data.top_videos.length})</h4>
            <table class="tbl">
              <thead><tr><th>Video ID</th><th>Nội dung</th><th>GMV</th><th>Đơn bán</th><th>Lượt xem</th><th>Lấy MP4 sạch</th></tr></thead>
              <tbody>${data.top_videos.map((v) => `
                <tr>
                  <td><code>${esc(v.video_id)}</code></td>
                  <td>${esc(v.description)}</td>
                  <td><strong style="color:#6ee7b7">${esc(v.gmv_display)}</strong></td>
                  <td>${v.units_sold ?? "—"}</td>
                  <td>${v.views_count ?? "—"}</td>
                  <td><button class="btn btn-sm btn-blue" data-action="kalopro-deep-inspect" data-target="vid:${esc(v.video_id)}">⬇️ Mổ Video &amp; MP4</button></td>
                </tr>`).join("")}
              </tbody>
            </table>` : ""}
        </div>`;
      return;
    }

    const mod = data.module || data.module_kind || "";
    const items = data.items || [];
    if (mod === "shops") {
      box.innerHTML = `
        <div class="row" style="justify-content:space-between;margin-bottom:8px">
          <h3 style="margin:0;color:#6ee7b7">🏪 BXH Shop Đối Thủ &amp; Mở Affiliate (${items.length} Shop · Đã đồng bộ vào Kho Shop Đối thủ)</h3>
          <button class="btn btn-sm" data-action="jump-tab" data-tab="shops">🎯 Mở Kho Shop Đối thủ</button>
        </div>
        <table class="tbl">
          <thead><tr><th>#</th><th>Tên Gian Hàng</th><th>Loại</th><th>GMV (${esc(data.window_spec || "7d")})</th><th>Đơn bán</th><th>% Affiliate / Video</th><th>Chiến lược</th><th>Link</th></tr></thead>
          <tbody>${items.map((s) => `
            <tr>
              <td>${s.rank}</td>
              <td><strong>${esc(s.shop_name)}</strong> ${s.is_overseas ? '<span class="badge gold">✈️ Quốc tế</span>' : ""}</td>
              <td><code>${esc(s.seller_type)}</code></td>
              <td><strong style="color:#6ee7b7">${esc(s.gmv_display)}</strong> ${s.growth_pct != null ? `<small>(${s.growth_pct > 0 ? "+" : ""}${s.growth_pct}%)</small>` : ""}</td>
              <td>${s.units_sold ?? "—"}</td>
              <td>🤝 ${s.affiliate_share_pct ?? "—"}% · 🎬 ${s.video_share_pct ?? "—"}%</td>
              <td>${esc(s.strategy_label_vi)}</td>
              <td><a href="${esc(s.kalodata_url)}" target="_blank" style="color:#93c5fd">Kalodata &rarr;</a></td>
            </tr>`).join("")}
          </tbody>
        </table>`;
      return;
    }

    if (mod === "brands") {
      box.innerHTML = `
        <h3 style="margin:0 0 8px;color:#7dd3fc">🏷️ BXH Thương Hiệu, Thị Phần &amp; Ngân Sách Ads (${items.length} Brand)</h3>
        <table class="tbl">
          <thead><tr><th>#</th><th>Thương hiệu</th><th>Ngành</th><th>GMV</th><th>Chi tiêu Ads</th><th>Thị phần</th><th>Số KOC / Video</th></tr></thead>
          <tbody>${items.map((b) => `
            <tr>
              <td>${b.rank}</td>
              <td><strong>${esc(b.brand_name)}</strong></td>
              <td style="font-size:11.5px">${esc((b.categories_vi || []).join(", "))}</td>
              <td><strong style="color:#6ee7b7">${esc(b.gmv_display)}</strong></td>
              <td style="color:#fda4af">${esc(b.ad_spend_display)}</td>
              <td>${b.market_share_pct != null ? `${b.market_share_pct}%` : "—"}</td>
              <td>${b.creator_count ?? "—"} KOC · ${b.video_count ?? "—"} Video</td>
            </tr>`).join("")}
          </tbody>
        </table>`;
      return;
    }

    if (mod === "creators") {
      box.innerHTML = `
        <div class="row" style="justify-content:space-between;margin-bottom:8px">
          <h3 style="margin:0;color:#fde68a">👤 Săn KOC/Creator Ra Đơn + Tự Bóc Zalo/SĐT/Email (${items.length} KOC · ${data.with_contact_count || 0} có SĐT/Email)</h3>
          <button class="btn btn-sm" data-action="jump-tab" data-tab="shopspy">👥 Mở Kho Creator Leads</button>
        </div>
        <table class="tbl">
          <thead><tr><th>#</th><th>KOC / Handle</th><th>Follow</th><th>GMV (${esc(data.window_spec || "7d")})</th><th>Đơn bán</th><th>Zalo / SĐT / Email bóc từ Bio</th><th>Bio</th></tr></thead>
          <tbody>${items.map((c) => `
            <tr>
              <td>${c.rank}</td>
              <td><a href="${esc(c.tiktok_url)}" target="_blank" style="color:#93c5fd;font-weight:600">@${esc(c.handle)}</a><div style="font-size:11px;color:var(--muted)">${esc(c.nickname)}</div></td>
              <td>${c.followers_count ? Number(c.followers_count).toLocaleString("vi-VN") : "—"}</td>
              <td><strong style="color:#6ee7b7">${esc(c.gmv_display)}</strong></td>
              <td>${c.units_sold ?? "—"}</td>
              <td>
                ${(c.phones_zalo || []).map((p) => `<span class="badge green">📞 ${esc(p)}</span>`).join(" ")}
                ${(c.emails || []).map((em) => `<span class="badge blue">✉️ ${esc(em)}</span>`).join(" ")}
                ${!c.has_contact ? '<span style="color:var(--muted)">—</span>' : ""}
              </td>
              <td style="font-size:11.5px;max-width:240px">${esc(c.bio_signature)}</td>
            </tr>`).join("")}
          </tbody>
        </table>`;
      return;
    }

    if (mod === "videos_advanced") {
      box.innerHTML = `
        <h3 style="margin:0 0 8px;color:#e9d5ff">🎬 Danh Sách Video Thực Chiến (${esc(data.filter_mode)} · ${items.length} Video · AI=${data.ai_videos_count || 0} · Ads=${data.ad_videos_count || 0})</h3>
        <table class="tbl">
          <thead><tr><th>#</th><th>Video / Kênh</th><th>Nhãn AI / Ads</th><th>GMV</th><th>Đơn / Views</th><th>GPM / ROAS</th><th>Thao tác 1-Click</th></tr></thead>
          <tbody>${items.map((v) => `
            <tr>
              <td>${v.rank}</td>
              <td>
                <a href="${esc(v.tiktok_url)}" target="_blank" style="color:#93c5fd">@${esc(v.handle || "_")}</a> (${v.followers_count ? Number(v.followers_count).toLocaleString("vi-VN") + " fan" : "—"})
                <div style="font-size:11.5px;color:#cbd5e1;max-width:300px">${esc(v.description)}</div>
              </td>
              <td>
                ${v.is_ai_video ? '<span class="badge blue">🤖 AI Video</span> ' : ""}
                ${v.is_ad ? '<span class="badge gold">📣 Ads</span>' : '<span class="badge green">🌿 Organic</span>'}
              </td>
              <td><strong style="color:#6ee7b7">${esc(v.gmv_display)}</strong></td>
              <td>${v.units_sold ?? "—"} đơn<br/><small>${v.views_count ?? "—"} views</small></td>
              <td>GPM: ${esc(v.gpm_display)}<br/>ROAS: <strong>${v.ad_roas ?? "—"}</strong></td>
              <td>
                <div class="row" style="gap:4px">
                  <button class="btn btn-sm btn-blue" data-action="kalopro-deep-inspect" data-target="vid:${esc(v.video_id)}">⬇️ MP4 sạch</button>
                  <button class="btn btn-sm btn-gold" data-action="eco-send-to-clone" data-url="${esc(v.tiktok_url)}" data-prod="${esc(v.description)}">⚡ Clone 15s</button>
                </div>
              </td>
            </tr>`).join("")}
          </tbody>
        </table>`;
      return;
    }

    if (mod === "livestreams") {
      box.innerHTML = `
        <h3 style="margin:0 0 8px;color:#fecaca">🔴 Radar Phòng LIVE Nổ Đơn Mạnh Nhất (${items.length} phòng LIVE)</h3>
        <table class="tbl">
          <thead><tr><th>#</th><th>Phòng LIVE</th><th>Kênh</th><th>GMV</th><th>Đơn bán</th><th>Lượt xem</th><th>GPM</th></tr></thead>
          <tbody>${items.map((rm) => `
            <tr>
              <td>${rm.rank}</td>
              <td><a href="${esc(rm.kalodata_url)}" target="_blank" style="color:#93c5fd">${esc(rm.title)}</a></td>
              <td>@${esc(rm.handle || "—")}</td>
              <td><strong style="color:#6ee7b7">${esc(rm.gmv_display)}</strong></td>
              <td>${rm.units_sold ?? "—"}</td>
              <td>${rm.views_count ?? "—"}</td>
              <td>${esc(rm.gpm_display)}</td>
            </tr>`).join("")}
          </tbody>
        </table>`;
      return;
    }

    if (mod === "category_board" || items[0]?.category_name_vi) {
      box.innerHTML = `
        <h3 style="margin:0 0 8px;color:#bfdbfe">🗺️ Bảng Xếp Hạng Toàn Ngành TikTok Shop VN (${items.length} Ngành · Kỳ ${esc(data.window_spec || "7d")})</h3>
        <table class="tbl">
          <thead><tr><th>#</th><th>Ngành hàng</th><th>GMV Toàn Ngành</th><th>Tăng trưởng</th><th>Số Shop</th><th>% Affiliate</th><th>% Video</th><th>Top 10 Shop</th><th>Quét sâu</th></tr></thead>
          <tbody>${items.map((c) => `
            <tr>
              <td>${c.rank}</td>
              <td><strong>${esc(c.icon)} ${esc(c.category_name_vi)}</strong> <small style="color:var(--muted)">(${esc(c.level)})</small></td>
              <td><strong style="color:#6ee7b7">${esc(c.gmv_total_display)}</strong></td>
              <td>${c.gmv_growth_pct != null ? `${c.gmv_growth_pct > 0 ? "+" : ""}${c.gmv_growth_pct}%` : "—"}</td>
              <td>${c.active_shops_count ?? "—"}</td>
              <td>${c.affiliate_share_pct != null ? `${c.affiliate_share_pct}%` : "—"}</td>
              <td>${c.video_share_pct != null ? `${c.video_share_pct}%` : "—"}</td>
              <td>${c.top10_shops_share_pct != null ? `${c.top10_shops_share_pct}%` : "—"}</td>
              <td><button class="btn btn-sm btn-pri" data-action="kalo-preset-cat" data-cat="${esc(c.category_id)}">🔎 Chọn ngành</button></td>
            </tr>`).join("")}
          </tbody>
        </table>`;
      return;
    }

    box.innerHTML = `<pre class="codebox">${esc(JSON.stringify(data, null, 2))}</pre>`;
  }

  function readFileAsEntry(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      const low = file.name.toLowerCase();
      if (low.endsWith(".xlsx") || low.endsWith(".zip")) {
        reader.onload = () => {
          const b64 = String(reader.result || "").split(",")[1] || "";
          resolve({ name: file.name, base64: b64, isZip: low.endsWith(".zip") });
        };
        reader.onerror = () => reject(new Error(`Không đọc được tệp ${file.name}`));
        reader.readAsDataURL(file);
      } else {
        reader.onload = () => resolve({ name: file.name, content: String(reader.result || ""), isZip: false });
        reader.onerror = () => reject(new Error(`Không đọc được tệp ${file.name}`));
        reader.readAsText(file);
      }
    });
  }

  async function runKalodataImportPreview() {
    const fileInp = document.getElementById("impFiles");
    const rawTxt = document.getElementById("impRawText")?.value.trim() || "";
    const mapTxt = document.getElementById("impMappingJson")?.value.trim() || "";
    let mapping = {};
    if (mapTxt) {
      mapping = JSON.parse(mapTxt);
    }
    const payload = {
      market: document.getElementById("impMarket")?.value || "VN",
      currency: document.getElementById("impCurrency")?.value || "VND",
      window: document.getElementById("impWindow")?.value || "7d",
      entity_type: document.getElementById("impEntityType")?.value || "",
      mapping_profile: mapping,
      files: [],
    };
    if (fileInp?.files?.length) {
      for (const f of fileInp.files) {
        const ent = await readFileAsEntry(f);
        if (ent.isZip) payload.zip_base64 = ent.base64;
        else payload.files.push(ent);
      }
    } else if (rawTxt) {
      payload.content = rawTxt;
      payload.filename = `${payload.entity_type || "products"}.${rawTxt.startsWith("[") || rawTxt.startsWith("{") ? "json" : "csv"}`;
    } else {
      toast("Vui lòng chọn tệp .xlsx/.csv/.json/.zip hoặc dán nội dung vào ô!", true);
      return;
    }

    const res = await api("/api/imports/preview", "POST", payload);
    CURRENT_KALO_IMPORT_BATCH_ID = res.batch_id;
    const s = res.summary || {};
    document.getElementById("btnCommitKaloImport").disabled = !s.can_commit;
    document.getElementById("impPreviewBox").innerHTML = `
      <div style="padding:10px;border-radius:8px;background:#081221;border:1px solid var(--border)">
        <div class="row" style="margin-bottom:6px">
          <span class="badge blue">Lô: ${esc(res.batch_id)}</span>
          <span class="badge green">SP: ${s.products_staged || 0}</span>
          <span class="badge gold">KOC: ${s.creators_staged || 0}</span>
          <span class="badge blue">Video: ${s.videos_staged || 0} · Shop: ${s.shops_staged || 0}</span>
          ${s.errors_count ? `<span class="badge red">Cảnh báo/Lỗi: ${s.errors_count}</span>` : ""}
        </div>
        <div style="font-size:11.5px;color:var(--muted)">SHA-256: <code>${esc((s.bundle_hash || "").slice(0, 24))}...</code> ${s.duplicate_of_committed_batch ? `<strong style="color:#fcd34d">(Trùng với lô đã lưu ${esc(s.duplicate_of_committed_batch)})</strong>` : ""}</div>
        ${(res.errors || []).length ? `<div style="margin-top:6px;color:#fca5a5;font-size:12px">${res.errors.slice(0, 5).map((e) => `• [${esc(e.code)}] Dòng ${e.row}: ${esc(e.message)}`).join("<br/>")}</div>` : ""}
      </div>`;
  }

  function renderKalodataCapturePreview(cap) {
    const box = document.getElementById("klCapturePreviewBox");
    if (!box || !cap) return;
    const exclSet = new Set(cap.excluded_row_indices || []);
    const rows = cap.normalized || [];
    box.innerHTML = `
      <div style="padding:10px;border-radius:8px;background:#081221;border:1px solid var(--border)">
        <div class="row" style="justify-content:space-between;margin-bottom:8px">
          <div class="row">
            <span class="badge blue">${esc(cap.capture_id)} (${esc(cap.entity_type)})</span>
            <span class="badge green">${rows.length} dòng chụp (${rows.length - exclSet.size} dòng giữ lại)</span>
            <span class="badge ${cap.status === "committed" ? "green" : "gold"}">${esc(cap.status)}</span>
          </div>
          <div class="row">
            ${cap.status !== "committed" ? `<button class="btn btn-sm btn-gold" data-action="kcap-commit" data-id="${esc(cap.capture_id)}">✅ Commit Bảng Chụp vào Kho</button>` : `<span class="badge green">Đã lưu (${esc(cap.committed_batch_id)})</span>`}
            <a class="btn btn-sm" href="/api/kalodata/captures/${encodeURIComponent(cap.capture_id)}/download?format=zip">⬇️ Tải .ZIP</a>
            <a class="btn btn-sm" href="/api/kalodata/captures/${encodeURIComponent(cap.capture_id)}/download?format=csv">⬇️ Tải .CSV</a>
          </div>
        </div>
        <table class="tbl">
          <thead><tr><th>Giữ</th><th>#</th><th>Mã ID 19 số</th><th>Tên / Nội dung</th><th>GMV</th><th>Đơn bán</th></tr></thead>
          <tbody>${rows.slice(0, 30).map((r) => `
            <tr>
              <td><input type="checkbox" class="kcap-excl-chk" data-capid="${esc(cap.capture_id)}" data-ridx="${r.row_index}" ${exclSet.has(r.row_index) ? "" : "checked"} /></td>
              <td>${r.row_index + 1}</td>
              <td><code>${esc(r.native_id || "—")}</code></td>
              <td>${esc(r.display_title)} ${r.locked ? '<span class="badge red">🔒 ***</span>' : ""}</td>
              <td>${esc(r.gmv_raw || "—")}</td>
              <td>${r.units_sold ?? "—"}</td>
            </tr>`).join("")}
          </tbody>
        </table>
      </div>`;
  }

  async function loadKalodataImportTab() {
    try {
      const [impRes, capRes] = await Promise.all([api("/api/imports"), api("/api/kalodata/captures")]);
      const batches = impRes.items || [];
      const caps = capRes.items || [];
      const elCnt = document.getElementById("cntKaloImports");
      if (elCnt) elCnt.textContent = batches.length + caps.length;
      const bBox = document.getElementById("impBatchesList");
      if (bBox) {
        bBox.innerHTML = batches.length
          ? `<table class="tbl"><thead><tr><th>Lô Import</th><th>Nguồn</th><th>Phạm vi</th><th>Trạng thái</th><th>SP / KOC / Video</th></tr></thead><tbody>${batches.slice(0, 10).map((b) => `
              <tr>
                <td><code>${esc(b.batch_id)}</code></td>
                <td>${esc(b.source_type)}</td>
                <td>${esc(b.market)} · ${esc(b.window_spec)}</td>
                <td><span class="badge ${b.status === "committed" ? "green" : "gold"}">${esc(b.status)}</span></td>
                <td>${b.summary?.committed_products ?? b.summary?.products_staged ?? 0} SP · ${b.summary?.committed_creators ?? b.summary?.creators_staged ?? 0} KOC · ${b.summary?.committed_videos ?? b.summary?.videos_staged ?? 0} Video</td>
              </tr>`).join("")}</tbody></table>`
          : `Chưa có lô import nào.`;
      }
      const cBox = document.getElementById("klCapturesHistoryBox");
      if (cBox) {
        cBox.innerHTML = caps.length
          ? `<div class="chips">${caps.slice(0, 10).map((c) => `<button type="button" class="chip" data-action="kcap-open" data-id="${esc(c.capture_id)}">📸 ${esc(c.capture_id)} (${esc(c.entity_type)} · ${c.coverage?.rows_captured || 0} dòng · ${esc(c.status)})</button>`).join("")}</div>`
          : "";
      }
    } catch (_) {}
  }

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
    const kwPlatEl = document.getElementById("kwPlatform");
    const kwBoxEl = document.getElementById("kwShopeeFiltersBox");
    if (kwPlatEl && kwBoxEl) {
      kwPlatEl.addEventListener("change", () => {
        kwBoxEl.style.display = kwPlatEl.value.startsWith("shopee") ? "block" : "none";
      });
    }
  }

  window.addEventListener("popstate", initRoute);
  window.addEventListener("DOMContentLoaded", initRoute);
})();
