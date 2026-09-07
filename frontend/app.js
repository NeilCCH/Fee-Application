// 公勝保險 差旅／費用報帳 APP — 表單頁邏輯（開發順序第 1 步：手動填表 -> data.json -> 產檔）
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const state = { mode: null, rowCount: 0, itemCount: 0, routes: [] };

  const modeSection = $("#modeSection");
  const mainForm = $("#mainForm");
  const resultBox = $("#resultBox");
  const errorBox = $("#errorBox");
  const rowsList = $("#rowsList");
  const itemsList = $("#itemsList");
  const rowTemplate = $("#rowTemplate");
  const itemTemplate = $("#itemTemplate");

  // ---------- 記住姓名／部門／職稱 ----------
  const PROFILE_KEY = "gongshen_profile_v1";
  function loadProfile() {
    try {
      const p = JSON.parse(localStorage.getItem(PROFILE_KEY) || "{}");
      if (p.name) $("#f_name").value = p.name;
      if (p.dept) $("#f_dept").value = p.dept;
      if (p.title) $("#f_title").value = p.title;
    } catch (e) { /* ignore */ }
  }
  function saveProfile() {
    try {
      localStorage.setItem(PROFILE_KEY, JSON.stringify({
        name: $("#f_name").value.trim(),
        dept: $("#f_dept").value.trim(),
        title: $("#f_title").value.trim(),
      }));
    } catch (e) { /* ignore */ }
  }

  // ---------- 模式切換 ----------
  $$(".mode-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      await state.routesReady;
      state.mode = btn.dataset.mode;
      $$(".mode-btn").forEach(b => b.classList.toggle("selected", b === btn));
      modeSection.classList.add("hidden");
      mainForm.classList.remove("hidden");
      resultBox.classList.add("hidden");

      const isTrip = state.mode === "trip";
      $$(".tripOnly").forEach(el => el.classList.toggle("hidden", !isTrip));
      $$(".generalOnly").forEach(el => el.classList.toggle("hidden", isTrip));
      $("#generalSummaryWrap").classList.toggle("hidden", isTrip);

      $("#t_startDate").required = isTrip;
      $("#t_endDate").required = isTrip;

      if (isTrip && rowsList.children.length === 0) addRow();
      if (!isTrip && itemsList.children.length === 0) addItem();
    });
  });

  $("#backBtn").addEventListener("click", () => {
    mainForm.classList.add("hidden");
    modeSection.classList.remove("hidden");
    resultBox.classList.add("hidden");
  });

  $("#f_summarySelect")?.addEventListener("change", (e) => {
    $("#summaryCustomWrap").classList.toggle("hidden", e.target.value !== "其他");
  });

  // ---------- 常用路線（供出差明細列的里程試算預設值） ----------
  async function loadRoutes() {
    try {
      const resp = await fetch("/api/routes");
      if (!resp.ok) return;
      const j = await resp.json();
      state.routes = j.routes || [];
    } catch (e) { /* 常用路線非必要，讀取失敗仍可手動填寫 */ }
  }

  function applyRoute(node, route) {
    const noteEl = $(".r_calcNote", node);
    if (!route) {
      noteEl.classList.add("hidden");
      noteEl.textContent = "";
      return;
    }
    const [locFrom, locTo] = (route["名稱"] || "").split("↔");
    if (locFrom) $(".r_locFrom", node).value = locFrom;
    if (locTo) $(".r_locTo", node).value = locTo;
    if (route["油資"] != null) $(".r_fuel", node).value = route["油資"];
    if (route["國道通行費"] != null) $(".r_toll", node).value = route["國道通行費"];
    noteEl.textContent =
      `試算：來回 ${route["來回里程"]} km × 5 元＝${route["油資"]} 元` +
      (route["國道來回里程"] ? `；國道來回約 ${route["國道來回里程"]} km → 通行費 ${route["國道通行費"]} 元` : "（無國道）") +
      "。金額欄位仍可手動修正。";
    noteEl.classList.remove("hidden");
  }

  // ---------- 出差明細列 ----------
  function addRow() {
    state.rowCount += 1;
    const node = rowTemplate.content.firstElementChild.cloneNode(true);
    $(".entry-index", node).textContent = state.rowCount;
    $(".btn-remove", node).addEventListener("click", () => {
      node.remove();
      renumber(rowsList, "row-entry");
    });

    const routeSelect = $(".r_route", node);
    state.routes.forEach((r, i) => {
      const opt = document.createElement("option");
      opt.value = i;
      opt.textContent = r["名稱"] || `路線 ${i + 1}`;
      routeSelect.appendChild(opt);
    });
    routeSelect.addEventListener("change", () => {
      const idx = routeSelect.value;
      applyRoute(node, idx === "" ? null : state.routes[idx]);
    });

    rowsList.appendChild(node);
  }
  $("#addRowBtn").addEventListener("click", addRow);

  // ---------- 一般費用項次 ----------
  function addItem() {
    state.itemCount += 1;
    const node = itemTemplate.content.firstElementChild.cloneNode(true);
    $(".entry-index", node).textContent = state.itemCount;
    $(".btn-remove", node).addEventListener("click", () => {
      node.remove();
      renumber(itemsList, "item-entry");
    });
    itemsList.appendChild(node);
  }
  $("#addItemBtn").addEventListener("click", addItem);

  function renumber(list, cls) {
    $$(`.${cls}`, list).forEach((node, i) => {
      $(".entry-index", node).textContent = i + 1;
    });
  }

  // ---------- 組裝 data.json ----------
  function numOrBlank(v) {
    if (v === "" || v === null || v === undefined) return "";
    const n = Number(v);
    return Number.isFinite(n) ? n : "";
  }

  function buildTripData() {
    const rows = $$(".row-entry", rowsList).map(node => {
      const row = {
        "日期起": $(".r_dateFrom", node).value.trim(),
        "日期迄": $(".r_dateTo", node).value.trim(),
        "地點起": $(".r_locFrom", node).value.trim(),
        "地點迄": $(".r_locTo", node).value.trim(),
        "摘要": $(".r_note", node).value.trim(),
      };
      const amountMap = {
        "火車高鐵": ".r_train", "計程車": ".r_taxi", "自用車油": ".r_fuel",
        "自用車通行": ".r_toll", "飛機": ".r_flight", "交通其他": ".r_otherTransit",
        "住宿費": ".r_hotel", "膳雜費": ".r_meal", "交際費": ".r_social", "其他": ".r_other",
      };
      for (const [key, sel] of Object.entries(amountMap)) {
        const v = numOrBlank($(sel, node).value);
        if (v !== "") row[key] = v;
      }
      return row;
    });

    const locFrom = $("#t_locationFrom").value.trim();
    const locTo = $("#t_locationTo").value.trim();
    const location = locFrom && locTo ? `${locFrom}→${locTo}` : (locFrom || locTo);

    return {
      "出差人姓名": $("#f_name").value.trim(),
      "部門": $("#f_dept").value.trim(),
      "職稱": $("#f_title").value.trim(),
      "申請日期": $("#f_applyDate").value,
      "出差事由": $("#t_reason").value.trim(),
      "出差地點": location,
      "出差起日": $("#t_startDate").value,
      "出差起時": $("#t_startTime").value.trim(),
      "出差迄日": $("#t_endDate").value,
      "出差迄時": $("#t_endTime").value.trim(),
      "共日": numOrBlank($("#t_days").value),
      "共時": numOrBlank($("#t_hours").value),
      "rows": rows,
      "預支旅費": numOrBlank($("#t_advance").value) || 0,
      "備註": $("#t_note").value.trim(),
    };
  }

  function buildGeneralData() {
    const cat = $("#f_summarySelect").value;
    const catName = cat === "其他" ? ($("#f_summaryCustom").value.trim() || "其他") : cat;
    const note = $("#f_summaryNote").value.trim();
    const summary = note ? `${catName}－${note}` : catName;

    const items = $$(".item-entry", itemsList).map(node => ({
      "說明": $(".i_desc", node).value.trim(),
      "金額": numOrBlank($(".i_amount", node).value) || 0,
    })).filter(it => it["說明"] || it["金額"]);

    return {
      "出差人姓名": $("#f_name").value.trim(),
      "部門": $("#f_dept").value.trim(),
      "職稱": $("#f_title").value.trim(),
      "申請日期": $("#f_applyDate").value,
      "交易摘要": summary,
      "請款明細": items,
    };
  }

  // ---------- 送出 ----------
  function showError(msg) {
    errorBox.textContent = msg;
    errorBox.classList.remove("hidden");
    errorBox.scrollIntoView({ behavior: "smooth", block: "center" });
  }
  function clearError() {
    errorBox.classList.add("hidden");
    errorBox.textContent = "";
  }

  mainForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearError();
    resultBox.classList.add("hidden");

    if (!state.mode) return;
    saveProfile();

    const data = state.mode === "trip" ? buildTripData() : buildGeneralData();
    const submitBtn = $("#submitBtn");
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner"></span>產生中…（需轉檔，約數秒）';

    const form = new FormData();
    form.append("payload", JSON.stringify({ mode: state.mode, data }));
    let hasAttachment = false;
    if (state.mode === "trip") {
      const mapFile = $("#t_mapFile")?.files[0];
      const tollFile = $("#t_tollFile")?.files[0];
      if (mapFile) { form.append("map_file", mapFile); hasAttachment = true; }
      if (tollFile) { form.append("toll_file", tollFile); hasAttachment = true; }
    }

    try {
      const resp = await fetch("/api/generate", {
        method: "POST",
        body: form,
      });

      if (!resp.ok) {
        let msg = `產生失敗（${resp.status}）`;
        try {
          const j = await resp.json();
          if (j.detail) msg = j.detail;
        } catch (e) { /* ignore */ }
        showError(msg);
        return;
      }

      const blob = await resp.blob();
      const cd = resp.headers.get("Content-Disposition") || "";
      const m = cd.match(/filename="?([^";]+)"?/);
      const filename = m ? m[1] : "報帳資料.zip";

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 5000);

      const contents = [
        state.mode === "trip" ? "出差旅費報告表_已填.xls" : null,
        "請款單_已填.docx",
        hasAttachment ? "里程證明.pdf（地圖／國道收費合併附件）" : null,
      ].filter(Boolean).join(" ＋ ");
      resultBox.innerHTML = `
        <p class="result-title">✅ 已產出並開始下載</p>
        <p class="result-summary">
          檔名：<b>${filename}</b><br/>
          內含：${contents}<br/>
          送件前請自行附上單據正本。
        </p>`;
      resultBox.classList.remove("hidden");
      resultBox.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      showError("網路或伺服器錯誤，請稍後再試：" + err.message);
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "產生表單並下載";
    }
  });

  // 預設申請日期為今天
  const today = new Date();
  const pad = n => String(n).padStart(2, "0");
  $("#f_applyDate").value = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`;

  loadProfile();
  state.routesReady = loadRoutes();
})();
