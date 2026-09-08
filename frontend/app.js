// 公勝保險 差旅／費用報帳 APP — 表單頁邏輯
// 流程：個別記錄出差明細／費用草稿（存後端）-> 挑選 -> 填共同資訊 -> 預覽 -> 產出單一 PDF
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const state = {
    routes: [],
    tripLegs: [],       // 目前伺服器上的出差明細草稿
    expenseItems: [],    // 目前伺服器上的費用項次草稿
    selectedLegIds: new Set(),
    selectedItemIds: new Set(),
    seenLegIds: new Set(),
    seenItemIds: new Set(),
  };

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

  function ownerName() { return $("#f_name").value.trim(); }

  // ---------- 常用路線 ----------
  async function loadRoutes() {
    try {
      const resp = await fetch("/api/routes");
      if (!resp.ok) return;
      const j = await resp.json();
      state.routes = j.routes || [];
      const sel = $("#leg_route");
      state.routes.forEach((r, i) => {
        const opt = document.createElement("option");
        opt.value = i;
        opt.textContent = r["名稱"] || `路線 ${i + 1}`;
        sel.appendChild(opt);
      });
    } catch (e) { /* 常用路線非必要 */ }
  }

  $("#leg_route").addEventListener("change", (e) => {
    const idx = e.target.value;
    const noteEl = $("#leg_calcNote");
    const route = idx === "" ? null : state.routes[idx];
    if (!route) {
      noteEl.classList.add("hidden");
      noteEl.textContent = "";
      return;
    }
    const [locFrom, locTo] = (route["名稱"] || "").split("↔");
    if (locFrom) $("#leg_locFrom").value = locFrom;
    if (locTo) $("#leg_locTo").value = locTo;
    if (route["油資"] != null) $("#leg_fuel").value = route["油資"];
    if (route["國道通行費"] != null) $("#leg_toll").value = route["國道通行費"];
    noteEl.textContent =
      `試算：來回 ${route["來回里程"]} km × 5 元＝${route["油資"]} 元` +
      (route["國道來回里程"] ? `；國道來回約 ${route["國道來回里程"]} km → 通行費 ${route["國道通行費"]} 元` : "（無國道）") +
      "。金額欄位仍可手動修正。";
    noteEl.classList.remove("hidden");
  });

  function numOrBlank(v) {
    if (v === "" || v === null || v === undefined) return "";
    const n = Number(v);
    return Number.isFinite(n) ? n : "";
  }

  // ---------- 新增出差明細草稿 ----------
  function showFieldError(el, msg) {
    el.textContent = msg;
    el.classList.toggle("hidden", !msg);
  }

  $("#addLegBtn").addEventListener("click", async () => {
    showFieldError($("#legError"), "");
    const owner = ownerName();
    if (!owner) { showFieldError($("#legError"), "請先在上面填姓名"); return; }
    const dateFrom = $("#leg_dateFrom").value.trim();
    const dateTo = $("#leg_dateTo").value.trim();
    const locFrom = $("#leg_locFrom").value.trim();
    const locTo = $("#leg_locTo").value.trim();
    if (!dateFrom || !locFrom) { showFieldError($("#legError"), "至少要填日期起與地點起"); return; }

    const amounts = {};
    for (const [key, id] of Object.entries(ROW_CATEGORY_FIELD)) {
      const v = numOrBlank($("#" + id).value);
      if (v !== "") amounts[key] = v;
    }
    const body = {
      owner_name: owner, "日期起": dateFrom, "日期迄": dateTo,
      "地點起": locFrom, "地點迄": locTo, amounts,
      "摘要": $("#leg_note").value.trim(),
    };
    const btn = $("#addLegBtn");
    btn.disabled = true;
    try {
      const resp = await fetch("/api/drafts/trip-leg", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const j = await resp.json().catch(() => null);
        throw new Error((j && j.detail) || `存檔失敗（${resp.status}）`);
      }
      $$("#addLegBtn").forEach(() => {});
      ["leg_dateFrom", "leg_dateTo", "leg_locFrom", "leg_locTo", "leg_note"].forEach(id => $("#" + id).value = "");
      Object.values(ROW_CATEGORY_FIELD).forEach(id => $("#" + id).value = "");
      $("#leg_route").value = "";
      $("#leg_calcNote").classList.add("hidden");
      await refreshDrafts();
    } catch (err) {
      showFieldError($("#legError"), err.message);
    } finally {
      btn.disabled = false;
    }
  });

  // ---------- 新增費用項次草稿 ----------
  $("#addItemBtn").addEventListener("click", async () => {
    showFieldError($("#itemError"), "");
    const owner = ownerName();
    if (!owner) { showFieldError($("#itemError"), "請先在上面填姓名"); return; }
    const desc = $("#item_desc").value.trim();
    const amount = numOrBlank($("#item_amount").value);
    if (!desc || amount === "") { showFieldError($("#itemError"), "說明與金額都要填"); return; }

    const body = {
      owner_name: owner,
      "類別": $("#item_category").value,
      "日期": $("#item_date").value.trim(),
      "說明": desc,
      "金額": amount,
    };
    const btn = $("#addItemBtn");
    btn.disabled = true;
    try {
      const resp = await fetch("/api/drafts/expense-item", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const j = await resp.json().catch(() => null);
        throw new Error((j && j.detail) || `存檔失敗（${resp.status}）`);
      }
      ["item_date", "item_desc", "item_amount"].forEach(id => $("#" + id).value = "");
      $("#item_category").value = "交際費";
      await refreshDrafts();
    } catch (err) {
      showFieldError($("#itemError"), err.message);
    } finally {
      btn.disabled = false;
    }
  });

  // ---------- 草稿清單 ----------
  async function refreshDrafts() {
    const owner = ownerName();
    const box = $("#draftListBox");
    if (!owner) {
      box.innerHTML = '<p class="hint" id="draftEmptyHint">先填姓名，草稿清單就會出現在這裡。</p>';
      return;
    }
    let data;
    try {
      const resp = await fetch("/api/drafts?owner_name=" + encodeURIComponent(owner));
      if (!resp.ok) throw new Error("讀取草稿失敗");
      data = await resp.json();
    } catch (e) {
      box.innerHTML = `<p class="error">讀取草稿清單失敗：${e.message}</p>`;
      return;
    }
    state.tripLegs = data.trip_legs || [];
    state.expenseItems = data.expense_items || [];

    // 新出現的草稿預設勾選；已看過的保留原本勾選狀態
    state.tripLegs.forEach(leg => {
      if (!state.seenLegIds.has(leg.id)) { state.seenLegIds.add(leg.id); state.selectedLegIds.add(leg.id); }
    });
    state.expenseItems.forEach(it => {
      if (!state.seenItemIds.has(it.id)) { state.seenItemIds.add(it.id); state.selectedItemIds.add(it.id); }
    });
    // 清掉已經被刪除、不存在的 id
    const legIdSet = new Set(state.tripLegs.map(l => l.id));
    const itemIdSet = new Set(state.expenseItems.map(i => i.id));
    Array.from(state.selectedLegIds).forEach(id => { if (!legIdSet.has(id)) state.selectedLegIds.delete(id); });
    Array.from(state.selectedItemIds).forEach(id => { if (!itemIdSet.has(id)) state.selectedItemIds.delete(id); });

    renderDraftList();
    updateTripDependentUI();
  }

  function legLabel(leg) {
    const rng = leg.date_to && leg.date_to !== leg.date_from ? `${leg.date_from}→${leg.date_to}` : leg.date_from;
    return `${rng || "（無日期）"} ${leg.loc_from || ""}→${leg.loc_to || ""}`.trim();
  }
  function legAmount(leg) {
    return Object.values(leg.amounts || {}).reduce((s, v) => s + (Number(v) || 0), 0);
  }
  function itemLabel(item) {
    return `${item.category || ""} ${item.item_date || ""} ${item.description || ""}`.replace(/\s+/g, " ").trim();
  }

  function renderDraftList() {
    const box = $("#draftListBox");
    box.innerHTML = "";
    if (state.tripLegs.length === 0 && state.expenseItems.length === 0) {
      box.innerHTML = '<p class="hint">目前沒有草稿，先在上面新增一筆出差明細或費用項次。</p>';
      return;
    }
    if (state.tripLegs.length) {
      const h = document.createElement("p");
      h.className = "draft-group-title";
      h.textContent = "出差明細";
      box.appendChild(h);
      state.tripLegs.forEach(leg => box.appendChild(buildDraftRow(
        legLabel(leg), legAmount(leg), state.selectedLegIds.has(leg.id),
        (checked) => checked ? state.selectedLegIds.add(leg.id) : state.selectedLegIds.delete(leg.id),
        async () => { await fetch(`/api/drafts/trip-leg/${leg.id}`, { method: "DELETE" }); await refreshDrafts(); },
      )));
    }
    if (state.expenseItems.length) {
      const h = document.createElement("p");
      h.className = "draft-group-title";
      h.textContent = "費用項次";
      box.appendChild(h);
      state.expenseItems.forEach(item => box.appendChild(buildDraftRow(
        itemLabel(item), Number(item.amount) || 0, state.selectedItemIds.has(item.id),
        (checked) => checked ? state.selectedItemIds.add(item.id) : state.selectedItemIds.delete(item.id),
        async () => { await fetch(`/api/drafts/expense-item/${item.id}`, { method: "DELETE" }); await refreshDrafts(); },
      )));
    }
  }

  const draftTemplate = $("#draftLegTemplate");
  function buildDraftRow(label, amount, checked, onToggle, onDelete) {
    const node = draftTemplate.content.firstElementChild.cloneNode(true);
    const check = $(".draft-check", node);
    check.checked = checked;
    check.addEventListener("change", () => { onToggle(check.checked); updateTripDependentUI(); });
    $(".draft-label", node).textContent = label;
    $(".draft-amount", node).textContent = amount ? `$${amount.toLocaleString()}` : "";
    $(".draft-del", node).addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); onDelete(); });
    return node;
  }

  function updateTripDependentUI() {
    const hasTrip = state.selectedLegIds.size > 0;
    $("#c_reasonWrap").classList.toggle("hidden", !hasTrip);
    $("#attachWrap").classList.toggle("hidden", !hasTrip);
    $(".req_summary").classList.toggle("hidden", hasTrip);
    $("#previewBox").classList.add("hidden");
    $("#generateBtn").classList.add("hidden");
  }

  $("#refreshDraftsBtn").addEventListener("click", refreshDrafts);
  $("#f_name").addEventListener("change", () => { saveProfile(); refreshDrafts(); });

  // ---------- 共同資訊組裝 ----------
  function buildCommon() {
    return {
      "出差人姓名": ownerName(),
      "部門": $("#f_dept").value.trim(),
      "職稱": $("#f_title").value.trim(),
      "申請日期": $("#c_applyDate").value,
      "出差事由": $("#c_reason").value.trim(),
      "交易摘要": $("#c_summary").value.trim(),
      "預支旅費": numOrBlank($("#c_advance").value) || 0,
      "備註": $("#c_note").value.trim(),
    };
  }

  function selectionPayload() {
    return {
      common: buildCommon(),
      trip_leg_ids: Array.from(state.selectedLegIds),
      expense_item_ids: Array.from(state.selectedItemIds),
    };
  }

  // ---------- 預覽 / 產出 ----------
  function showError(msg) {
    const el = $("#errorBox");
    el.textContent = msg;
    el.classList.toggle("hidden", !msg);
    if (msg) el.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  $("#previewBtn").addEventListener("click", async () => {
    showError("");
    saveProfile();
    const btn = $("#previewBtn");
    btn.disabled = true;
    btn.textContent = "計算中…";
    try {
      const resp = await fetch("/api/preview", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(selectionPayload()),
      });
      const j = await resp.json();
      if (!resp.ok) throw new Error(j.detail || `預覽失敗（${resp.status}）`);
      renderPreview(j);
      $("#generateBtn").classList.remove("hidden");
    } catch (err) {
      showError(err.message);
      $("#previewBox").classList.add("hidden");
      $("#generateBtn").classList.add("hidden");
    } finally {
      btn.disabled = false;
      btn.textContent = "預覽這次要送出的內容";
    }
  });

  function renderPreview(p) {
    const lines = p["項次"].map(it => `<div class="line"><span>${it["說明"]}</span><span>${it["金額"].toLocaleString()}</span></div>`).join("");
    $("#previewBox").innerHTML = `
      <div class="preview-box">
        ${lines}
        <div class="line total"><span>總計（${p["總計大寫"]}）</span><span>$${p["總計"].toLocaleString()}</span></div>
      </div>`;
    $("#previewBox").classList.remove("hidden");
  }

  $("#generateBtn").addEventListener("click", async () => {
    showError("");
    const form = new FormData();
    form.append("payload", JSON.stringify(selectionPayload()));
    const mapFile = $("#c_mapFile").files[0];
    const tollFile = $("#c_tollFile").files[0];
    let hasAttachment = false;
    if (mapFile) { form.append("map_file", mapFile); hasAttachment = true; }
    if (tollFile) { form.append("toll_file", tollFile); hasAttachment = true; }

    const btn = $("#generateBtn");
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>產生中…（需轉檔，約數秒）';

    try {
      const resp = await fetch("/api/generate", { method: "POST", body: form });
      if (!resp.ok) {
        let msg = `產生失敗（${resp.status}）`;
        try { const j = await resp.json(); if (j.detail) msg = j.detail; } catch (e) { /* ignore */ }
        showError(msg);
        return;
      }
      const blob = await resp.blob();
      const cd = resp.headers.get("Content-Disposition") || "";
      const m = cd.match(/filename="?([^";]+)"?/);
      const filename = m ? m[1] : "報帳資料.pdf";

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = filename;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 5000);

      $("#resultBox").innerHTML = `
        <p class="result-title">✅ 已產出並開始下載</p>
        <p class="result-summary">
          檔名：<b>${filename}</b>${hasAttachment ? "（含里程地圖／國道收費附件）" : ""}<br/>
          已用的草稿已自動清除。送件前請自行附上單據正本。
        </p>`;
      $("#resultBox").classList.remove("hidden");
      $("#resultBox").scrollIntoView({ behavior: "smooth", block: "start" });

      $("#previewBox").classList.add("hidden");
      $("#generateBtn").classList.add("hidden");
      await refreshDrafts();
    } catch (err) {
      showError("網路或伺服器錯誤，請稍後再試：" + err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "確認無誤，產生 PDF";
    }
  });

  // ---------- 初始化 ----------
  const today = new Date();
  const pad = n => String(n).padStart(2, "0");
  $("#c_applyDate").value = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`;

  loadProfile();
  loadRoutes();
  refreshDrafts();
  updateTripDependentUI();
})();
