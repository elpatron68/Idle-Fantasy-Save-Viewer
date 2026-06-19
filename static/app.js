/* Idle Fantasy Save Viewer – client UI */

let state = {
  data: null,
  snapshots: [],
  timeline: [],
  inventory: { search: "", categories: new Set(), sort: "category", highlightEquipped: false, collapsedGroups: new Set() },
  skills: { search: "", sort: "level", sortAsc: false },
  quests: { tab: "story", filter: "all" },
  goals: { filter: "all", collapsedGroups: new Set(), data: { groups: [], ungrouped: [] } },
  goalModalItem: null,
  history: { olderId: null, newerId: null, diff: null },
  charts: {},
  inventoryTimeline: null,
};

const CATEGORY_ORDER = [
  "Currency", "Ores & Mining", "Bars & Smithing", "Wood & Planks", "Runes",
  "Raw Food", "Cooked Food", "Seeds & Farming", "Melee Weapons", "Ranged",
  "Magic", "Armor", "Bones & Hides", "Gems & Jewelry", "Potions & Brews", "Misc",
];

const CATEGORY_I18N_KEYS = {
  "Currency": "category.currency",
  "Ores & Mining": "category.ores_mining",
  "Bars & Smithing": "category.bars_smithing",
  "Wood & Planks": "category.wood_planks",
  "Runes": "category.runes",
  "Raw Food": "category.raw_food",
  "Cooked Food": "category.cooked_food",
  "Seeds & Farming": "category.seeds_farming",
  "Melee Weapons": "category.melee_weapons",
  "Ranged": "category.ranged",
  "Magic": "category.magic",
  "Armor": "category.armor",
  "Bones & Hides": "category.bones_hides",
  "Gems & Jewelry": "category.gems_jewelry",
  "Potions & Brews": "category.potions_brews",
  "Misc": "category.misc",
};

document.addEventListener("DOMContentLoaded", init);

function getViewerId() {
  return document.body?.dataset?.viewerId || "";
}

function trackEvent(name, props) {
  if (typeof window.plausible === "function") {
    window.plausible(name, props ? { props } : undefined);
  }
}

function apiBase() {
  const vid = getViewerId();
  return vid ? `/v/${vid}/api` : "/api";
}

function viewerPageUrl() {
  const vid = getViewerId();
  if (!vid) return window.location.href;
  return `${window.location.origin}/v/${vid}/`;
}

async function init() {
  await I18n.init();
  applyStaticI18n();
  setupLanguage();
  setupViewerBanner();
  setupNav();
  setupUpload();
  setupGoalModal();
  await loadData();
}

function setupViewerBanner() {
  const vid = getViewerId();
  if (!vid || vid === "local") return;

  const banner = document.getElementById("viewer-link-banner");
  const urlEl = document.getElementById("viewer-link-url");
  const copyBtn = document.getElementById("viewer-copy-link");
  const url = viewerPageUrl();

  banner.hidden = false;
  urlEl.textContent = url;

  copyBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(url);
      const prev = copyBtn.textContent;
      copyBtn.textContent = t("viewer.copied");
      setTimeout(() => { copyBtn.textContent = prev; }, 2000);
    } catch {
      window.prompt(t("viewer.copyPrompt"), url);
    }
  });
}

function categoryLabel(cat) {
  const key = CATEGORY_I18N_KEYS[cat];
  return key ? t(key) : cat;
}

function applyStaticI18n() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
}

function setupLanguage() {
  const sel = document.getElementById("locale-select");
  sel.value = I18n.getPreference();
  sel.addEventListener("change", async (e) => {
    await I18n.setPreference(e.target.value);
    applyStaticI18n();
    resetLocaleDependentPanels();
    if (state.data) renderAll();
    if (document.getElementById("tab-history").classList.contains("active")) {
      loadHistoryTab();
    }
  });
}

function resetLocaleDependentPanels() {
  ["tab-skills", "tab-inventory"].forEach((id) => {
    document.getElementById(id).innerHTML = "";
  });
}

function setupNav() {
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
      if (btn.dataset.tab === "history") loadHistoryTab();
    });
  });
}

function setupUpload() {
  document.getElementById("file-upload").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${apiBase()}/import`, { method: "POST", body: fd });
    const result = await res.json();
    if (!res.ok || result.error) {
      showImportFailure(result);
      e.target.value = "";
      return;
    }
    trackEvent("JSON Upload", { status: result.imported ? "imported" : result.reason || "ok" });
    if (result.imported) {
      await loadData();
      notifyImportSuccess(result);
      showGoalsCompletedBanner(result);
    } else if (result.reason === "duplicate") {
      alert(t("import.duplicate"));
    }
    e.target.value = "";
  });
}

function showImportFailure(result) {
  const lines = [result.error || t("import.failed")];
  for (const item of result.import_report || []) {
    lines.push(`• ${I18n.translateIssue(item)}`);
  }
  alert(lines.join("\n"));
}

function notifyImportSuccess(result) {
  const summary = result.import_summary || {};
  const warnings = summary.warnings || 0;
  const infos = summary.infos || 0;
  if (warnings || infos) {
    alert(t("import.successWithNotes", {
      id: result.snapshot_id,
      warnings,
      infos,
    }));
  }
}

function renderImportReport(meta) {
  const el = document.getElementById("import-report");
  const report = meta?.import_report || [];
  const visible = report.filter((i) => i.level === "error" || i.level === "warning");
  const infos = report.filter((i) => i.level === "info");

  if (!report.length) {
    el.hidden = true;
    el.innerHTML = "";
    return;
  }

  const errors = report.filter((i) => i.level === "error");
  const warnings = report.filter((i) => i.level === "warning");
  const level = errors.length ? "error" : warnings.length ? "warning" : "info";
  const title = errors.length
    ? t("import.titleError")
    : warnings.length
      ? t("import.titleWarning")
      : t("import.titleInfo");

  el.hidden = false;
  el.className = `import-report import-report-${level}`;
  el.innerHTML = `
    <div class="import-report-header">
      <strong>${esc(title)}</strong>
      <span class="import-report-counts">
        ${errors.length ? t("import.countErrors", { count: errors.length }) : ""}
        ${warnings.length ? t("import.countWarnings", { count: warnings.length }) : ""}
        ${infos.length ? t("import.countInfos", { count: infos.length }) : ""}
      </span>
      <button type="button" class="import-report-dismiss" title="${esc(t("actions.dismiss"))}">×</button>
    </div>
    <ul class="import-report-list">
      ${visible.map((i) => `<li class="import-issue import-issue-${i.level}">${esc(I18n.translateIssue(i))}</li>`).join("")}
      ${infos.length ? `
        <li class="import-issue import-issue-info-collapsed">
          <details>
            <summary>${esc(t("import.newFieldsSummary", { count: infos.length }))}</summary>
            <ul>${infos.map((i) => `<li>${esc(I18n.translateIssue(i))}</li>`).join("")}</ul>
          </details>
        </li>` : ""}
    </ul>`;

  el.querySelector(".import-report-dismiss").addEventListener("click", () => {
    el.hidden = true;
  });
}

async function loadData() {
  try {
    const [res] = await Promise.all([
      fetch(`${apiBase()}/snapshot/latest`),
      loadGoals(),
    ]);
    if (!res.ok) {
      showEmpty(getViewerId() ? t("empty.noSaveWeb") : t("empty.noSave"));
      renderGoals();
      return;
    }
    state.data = await res.json();
    state.inventoryTimeline = null;
    renderAll();
  } catch (err) {
    showEmpty(t("empty.loadError", { message: err.message }));
    renderGoals();
  }
}

function showEmpty(msg) {
  document.getElementById("character-header").innerHTML = `<span class="loading">${esc(msg)}</span>`;
}

function renderAll() {
  const d = state.data;
  if (!d) return;

  renderHeader(d);
  renderImportReport(d.meta);
  renderOverview(d);
  renderSkills(d);
  renderInventory(d);
  renderGoals();
  renderEquipment(d);
  renderQuests(d);
  renderCombat(d);
}

function renderHeader(d) {
  const c = d.character;
  const m = d.meta;
  document.getElementById("character-header").innerHTML = `
    <h2>${esc(c.name || t("empty.unknown"))}</h2>
    <div class="character-meta">
      ${esc(c.race || "")} · ${esc(c.gender || "")} · ${t("meta.export")}: ${formatTs(m.exported_at)}
    </div>`;

  document.getElementById("kpi-row").innerHTML = `
    <div class="kpi"><div class="kpi-label">${esc(t("kpi.coins"))}</div><div class="kpi-value">${fmt(m.coins)}</div></div>
    <div class="kpi"><div class="kpi-label">${esc(t("kpi.totalLevel"))}</div><div class="kpi-value">${m.total_level}</div></div>
    <div class="kpi"><div class="kpi-label">${esc(t("kpi.items"))}</div><div class="kpi-value">${m.item_count}</div></div>
    <div class="kpi"><div class="kpi-label">${esc(t("kpi.totalQty"))}</div><div class="kpi-value">${fmt(m.total_items)}</div></div>`;
}

function renderOverview(d) {
  const c = d.character;
  const queue = (d.session_queue || []).map((q) =>
    `<li><span>${esc(q.skill_display_name || q.skill_name)}</span><span>${esc(q.activity_key || "—")} · ${q.qty || 0}</span></li>`
  ).join("");

  const slayer = d.combat.slayer_task;
  const slayerHtml = slayer
    ? `<p><strong>${esc(slayer.display_name)}</strong>: ${slayer.kills_completed}/${slayer.target_kills} (${d.combat.slayer_points} ${esc(t("meta.points"))})</p>`
    : `<p class='empty-state'>${esc(t("overview.noSlayerTask"))}</p>`;

  const pets = (d.pets || []).map((p) =>
    `<li><span>${esc(p.id.replace(/_/g, " "))}</span><span>+${p.boost_percent}%</span></li>`
  ).join("");

  const farming = (d.farming || []).map((p) =>
    `<li><span>${esc(t("overview.patch", { n: p.patchNumber }))}</span><span>${esc(p.cropType || "—")}</span></li>`
  ).join("");

  document.getElementById("tab-overview").innerHTML = `
    <div class="grid-2">
      <div class="card">
        <h3>${esc(t("overview.character"))}</h3>
        <ul class="list-compact">
          <li><span>${esc(t("overview.hp"))}</span><span>${c.hp ?? "—"}</span></li>
          <li><span>${esc(t("overview.activePotion"))}</span><span>${esc(c.active_potion || "—")}</span></li>
          <li><span>${esc(t("overview.activeSpell"))}</span><span>${esc(c.active_spell || "—")}</span></li>
          <li><span>${esc(t("overview.weaponSlot"))}</span><span>${esc(c.active_weapon_slot || "—")}</span></li>
          <li><span>${esc(t("overview.blessing"))}</span><span>${esc(c.active_blessing || "—")}</span></li>
        </ul>
      </div>
      <div class="card">
        <h3>${esc(t("overview.sessionQueue"))}</h3>
        <ul class="list-compact">${queue || `<li><span>${esc(t("empty.empty"))}</span></li>`}</ul>
      </div>
      <div class="card">
        <h3>${esc(t("overview.slayer"))}</h3>
        ${slayerHtml}
      </div>
      <div class="card">
        <h3>${esc(t("overview.pets"))}</h3>
        <ul class="list-compact">${pets || `<li><span>${esc(t("empty.none"))}</span></li>`}</ul>
      </div>
      <div class="card">
        <h3>${esc(t("overview.farming"))}</h3>
        <ul class="list-compact">${farming || `<li><span>${esc(t("empty.none"))}</span></li>`}</ul>
      </div>
      <div class="card">
        <h3>${esc(t("overview.guildRep"))}</h3>
        <ul class="list-compact">${Object.entries(d.guild_reputation || {}).map(([k, v]) =>
          `<li><span>${esc(k)}</span><span>${fmt(v)}</span></li>`).join("")}</ul>
      </div>
    </div>`;
}

function renderSkills(d) {
  const panel = document.getElementById("tab-skills");
  const s = state.skills;

  if (!panel.querySelector("#skill-search")) {
    panel.innerHTML = `
      <div class="toolbar">
        <input class="search-input" id="skill-search" placeholder="" value="">
        <select class="select-input" id="skill-sort">
          <option value="level"></option>
          <option value="xp"></option>
          <option value="name"></option>
        </select>
      </div>
      <div class="card">
        <table>
          <thead><tr>
            <th data-sort="name"></th>
            <th data-sort="level"></th>
            <th data-sort="xp">XP</th>
            <th></th>
          </tr></thead>
          <tbody id="skill-tbody"></tbody>
        </table>
      </div>`;

    document.getElementById("skill-search").addEventListener("input", (e) => {
      state.skills.search = e.target.value;
      renderSkillsBody(state.data);
    });
    document.getElementById("skill-sort").addEventListener("change", (e) => {
      state.skills.sort = e.target.value;
      renderSkillsBody(state.data);
    });
    panel.querySelectorAll("th[data-sort]").forEach((th) => {
      th.addEventListener("click", () => {
        const key = th.dataset.sort;
        if (state.skills.sort === key) state.skills.sortAsc = !state.skills.sortAsc;
        else { state.skills.sort = key; state.skills.sortAsc = false; }
        renderSkillsBody(state.data);
      });
    });
  }

  document.getElementById("skill-search").placeholder = t("skills.search");
  document.getElementById("skill-sort").options[0].textContent = t("skills.sortLevel");
  document.getElementById("skill-sort").options[1].textContent = t("skills.sortXp");
  document.getElementById("skill-sort").options[2].textContent = t("skills.sortName");
  panel.querySelector('th[data-sort="name"]').textContent = t("skills.skill");
  panel.querySelector('th[data-sort="level"]').textContent = t("skills.level");
  panel.querySelector("thead tr th:last-child").textContent = t("skills.progress");

  document.getElementById("skill-search").value = s.search;
  document.getElementById("skill-sort").value = s.sort;
  renderSkillsBody(d);
}

function renderSkillsBody(d) {
  const s = state.skills;
  let items = [...d.skills];
  if (s.search) {
    const q = s.search.toLowerCase();
    items = items.filter((sk) => sk.name.toLowerCase().includes(q) || sk.key.includes(q));
  }
  items.sort((a, b) => {
    let cmp = 0;
    if (s.sort === "name") cmp = a.name.localeCompare(b.name);
    else if (s.sort === "level") cmp = a.level - b.level;
    else cmp = a.xp - b.xp;
    return s.sortAsc ? cmp : -cmp;
  });

  document.getElementById("skill-tbody").innerHTML = items.map((sk) => `
    <tr>
      <td>${esc(sk.name)}</td>
      <td>${sk.level}</td>
      <td>${fmt(sk.xp)}</td>
      <td style="min-width:140px">
        ${sk.progress_pct}%
        <div class="progress-bar"><div class="progress-fill" style="width:${sk.progress_pct}%"></div></div>
      </td>
    </tr>`).join("");
}

function getFilteredInventoryItems(d, inv) {
  let items = [...d.inventory];
  if (inv.search) {
    const q = inv.search.toLowerCase();
    items = items.filter((i) => i.name.toLowerCase().includes(q) || i.key.includes(q));
  }
  if (inv.categories.size > 0) {
    items = items.filter((i) => inv.categories.has(i.category));
  }
  items.sort((a, b) => {
    if (inv.sort === "qty") return b.qty - a.qty;
    if (inv.sort === "name") return a.name.localeCompare(b.name);
    const ca = CATEGORY_ORDER.indexOf(a.category);
    const cb = CATEGORY_ORDER.indexOf(b.category);
    return ca - cb || a.name.localeCompare(b.name);
  });
  return items;
}

async function ensureInventoryTimeline() {
  if (state.inventoryTimeline) return state.inventoryTimeline;
  try {
    const res = await fetch(`${apiBase()}/inventory/timeline`);
    state.inventoryTimeline = res.ok ? await res.json() : { snapshots: [], series: {} };
  } catch {
    state.inventoryTimeline = { snapshots: [], series: {} };
  }
  return state.inventoryTimeline;
}

function inventoryTrendEnabled() {
  return (state.inventoryTimeline?.snapshots?.length || 0) >= 2;
}

function itemQtySeries(itemKey) {
  const tl = state.inventoryTimeline;
  if (!tl?.series) return null;
  const values = tl.series[itemKey];
  if (!values || values.length < 2) return null;
  return values;
}

function sparklineSvg(values, width = 72, height = 24) {
  const max = Math.max(...values);
  const min = Math.min(...values);
  const range = max - min || 1;
  const points = values.map((v, i) => {
    const x = (i / (values.length - 1)) * width;
    const y = height - ((v - min) / range) * (height - 4) - 2;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return `<svg class="inv-spark-svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" aria-hidden="true"><polyline points="${points}" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}

function renderItemSparkCell(item) {
  const values = itemQtySeries(item.key);
  if (!values) {
    return `<td class="col-trend"><span class="inv-spark-empty">—</span></td>`;
  }
  return `
    <td class="col-trend">
      <button type="button" class="inv-spark-btn" data-item-key="${esc(item.key)}" data-item-name="${esc(item.name)}" title="${esc(t("inventory.trendExpand"))}" aria-label="${esc(t("inventory.trendExpandFor", { name: item.name }))}">
        ${sparklineSvg(values)}
      </button>
    </td>`;
}

function setupInventoryChartModal() {
  if (document.getElementById("inv-chart-modal")) return;

  const modal = document.createElement("div");
  modal.id = "inv-chart-modal";
  modal.className = "inv-chart-modal";
  modal.hidden = true;
  modal.innerHTML = `
    <div class="inv-chart-modal-backdrop" data-close="1"></div>
    <div class="inv-chart-modal-panel card" role="dialog" aria-modal="true" aria-labelledby="inv-chart-modal-title">
      <button type="button" class="inv-chart-modal-close" data-close="1" aria-label="${esc(t("actions.dismiss"))}">×</button>
      <h3 id="inv-chart-modal-title"></h3>
      <div class="chart-wrap chart-wrap-modal"><canvas id="inv-chart-modal-canvas"></canvas></div>
    </div>`;
  document.body.appendChild(modal);

  modal.querySelectorAll("[data-close]").forEach((el) => {
    el.addEventListener("click", closeInventoryChartModal);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !modal.hidden) closeInventoryChartModal();
  });
}

function openInventoryChartModal(itemKey, itemName) {
  const values = itemQtySeries(itemKey);
  const tl = state.inventoryTimeline;
  if (!values || !tl) return;

  setupInventoryChartModal();
  const modal = document.getElementById("inv-chart-modal");
  const title = document.getElementById("inv-chart-modal-title");
  title.textContent = itemName;
  modal.hidden = false;
  document.body.classList.add("inv-chart-modal-open");

  destroyChart("inventoryModal");
  const labels = tl.snapshots.map((s) => formatTs(s.exported_at));
  state.charts.inventoryModal = new Chart(document.getElementById("inv-chart-modal-canvas"), {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: t("inventory.qty"),
        data: values,
        borderColor: "#6c8cff",
        backgroundColor: "rgba(108, 140, 255, 0.12)",
        tension: 0.3,
        fill: true,
      }],
    },
    options: chartOpts(),
  });
}

function closeInventoryChartModal() {
  const modal = document.getElementById("inv-chart-modal");
  if (!modal || modal.hidden) return;
  modal.hidden = true;
  document.body.classList.remove("inv-chart-modal-open");
  destroyChart("inventoryModal");
}

function bindInventorySparklines(container) {
  container.querySelectorAll(".inv-spark-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      openInventoryChartModal(btn.dataset.itemKey, btn.dataset.itemName);
    });
  });
}

function renderInventoryTable(d, inv) {
  const items = getFilteredInventoryItems(d, inv);
  const showTrend = inventoryTrendEnabled();
  const colSpan = showTrend ? 5 : 4;
  const grouped = {};
  for (const item of items) {
    if (!grouped[item.category]) grouped[item.category] = [];
    grouped[item.category].push(item);
  }

  const groupRows = Object.entries(grouped).map(([cat, catItems]) => {
    const totalQty = catItems.reduce((s, i) => s + i.qty, 0);
    const expanded = !inv.collapsedGroups.has(cat);
    const catLabel = categoryLabel(cat);
    const header = `
      <tr class="inv-group-row" data-group="${esc(cat)}">
        <td colspan="${colSpan}">
          <button type="button" class="inv-group-toggle" data-group="${esc(cat)}" aria-expanded="${expanded}">
            <span class="inv-group-title">${esc(catLabel)}</span>
            <span class="inv-group-meta">${esc(t("inventory.groupMeta", { count: catItems.length, qty: fmt(totalQty) }))}</span>
          </button>
        </td>
      </tr>`;
    const rows = catItems.map((i) => `
      <tr class="inv-item-row ${i.equipped && inv.highlightEquipped ? "item-equipped" : ""} ${expanded ? "" : "collapsed"}" data-group="${esc(cat)}">
        <td class="col-name">${esc(i.name)}${i.equipped ? `<span class="equipped-mark" title="${esc(t("inventory.equipped"))}">⚡</span>` : ""}</td>
        ${showTrend ? renderItemSparkCell(i) : ""}
        <td class="col-qty">${fmt(i.qty)}</td>
        <td class="col-key"><code>${esc(i.key)}</code></td>
        <td class="col-actions">
          <button type="button" class="goal-add-btn" data-item-key="${esc(i.key)}" data-item-name="${esc(i.name)}" data-item-qty="${i.qty}" title="${esc(t("inventory.addGoalFor", { name: i.name }))}" aria-label="${esc(t("inventory.addGoalFor", { name: i.name }))}">+</button>
        </td>
      </tr>`).join("");
    return header + rows;
  }).join("");

  const results = document.getElementById("inv-results");
  if (!groupRows) {
    results.innerHTML = `<p class='empty-state'>${esc(t("empty.noItems"))}</p>`;
    return;
  }

  const trendCol = showTrend
    ? `<col class="col-trend">`
    : "";
  const trendHeader = showTrend
    ? `<th class="col-trend">${esc(t("inventory.trend"))}</th>`
    : "";

  results.innerHTML = `
    <div class="inv-table-wrap">
      <table class="inv-table ${showTrend ? "has-trend" : ""}">
        <colgroup>
          <col class="col-name">
          ${trendCol}
          <col class="col-qty">
          <col class="col-key">
          <col class="col-actions">
        </colgroup>
        <thead>
          <tr>
            <th class="col-name">${esc(t("inventory.item"))}</th>
            ${trendHeader}
            <th class="col-qty">${esc(t("inventory.qty"))}</th>
            <th class="col-key">${esc(t("inventory.id"))}</th>
            <th class="col-actions">${esc(t("goals.actions"))}</th>
          </tr>
        </thead>
        <tbody>${groupRows}</tbody>
      </table>
    </div>`;

  results.querySelectorAll(".goal-add-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      openGoalModal({
        key: btn.dataset.itemKey,
        name: btn.dataset.itemName,
        qty: Number(btn.dataset.itemQty),
      });
    });
  });

  results.querySelectorAll(".inv-group-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const group = btn.dataset.group;
      const expanded = btn.getAttribute("aria-expanded") === "true";
      btn.setAttribute("aria-expanded", expanded ? "false" : "true");
      if (expanded) inv.collapsedGroups.add(group);
      else inv.collapsedGroups.delete(group);
      results.querySelectorAll(`.inv-item-row[data-group="${group}"]`).forEach((row) => {
        row.classList.toggle("collapsed", expanded);
      });
    });
  });
  bindInventorySparklines(results);
}

function renderInventoryChips(d, inv) {
  const categories = [...new Set(d.inventory.map((i) => i.category))].sort(
    (a, b) => CATEGORY_ORDER.indexOf(a) - CATEGORY_ORDER.indexOf(b)
  );
  const chips = document.getElementById("inv-chips");
  chips.innerHTML = categories.map((c) => `
    <span class="chip ${inv.categories.has(c) ? "active" : ""}" data-cat="${esc(c)}">${esc(categoryLabel(c))}</span>`).join("");
  chips.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const cat = chip.dataset.cat;
      if (inv.categories.has(cat)) inv.categories.delete(cat);
      else inv.categories.add(cat);
      renderInventoryChips(d, inv);
      ensureInventoryTimeline().then(() => renderInventoryTable(d, inv));
    });
  });
}

function renderInventory(d) {
  const panel = document.getElementById("tab-inventory");
  const inv = state.inventory;

  if (!panel.querySelector("#inv-search")) {
    panel.innerHTML = `
      <div class="toolbar">
        <input class="search-input" id="inv-search" placeholder="" value="">
        <select class="select-input" id="inv-sort">
          <option value="category"></option>
          <option value="name"></option>
          <option value="qty"></option>
        </select>
        <label class="toggle-label">
          <input type="checkbox" id="inv-equipped">
          <span id="inv-equipped-label"></span>
        </label>
      </div>
      <div class="chip-row" id="inv-chips"></div>
      <div class="card inv-card" id="inv-results"></div>`;

    document.getElementById("inv-search").addEventListener("input", (e) => {
      state.inventory.search = e.target.value;
      ensureInventoryTimeline().then(() => renderInventoryTable(state.data, state.inventory));
    });
    document.getElementById("inv-sort").addEventListener("change", (e) => {
      state.inventory.sort = e.target.value;
      ensureInventoryTimeline().then(() => renderInventoryTable(state.data, state.inventory));
    });
    document.getElementById("inv-equipped").addEventListener("change", (e) => {
      state.inventory.highlightEquipped = e.target.checked;
      ensureInventoryTimeline().then(() => renderInventoryTable(state.data, state.inventory));
    });
  }

  document.getElementById("inv-search").placeholder = t("inventory.search");
  document.getElementById("inv-sort").options[0].textContent = t("inventory.sortCategory");
  document.getElementById("inv-sort").options[1].textContent = t("inventory.sortName");
  document.getElementById("inv-sort").options[2].textContent = t("inventory.sortQty");
  document.getElementById("inv-equipped-label").textContent = t("inventory.highlightEquipped");

  document.getElementById("inv-search").value = inv.search;
  document.getElementById("inv-sort").value = inv.sort;
  document.getElementById("inv-equipped").checked = inv.highlightEquipped;
  renderInventoryChips(d, inv);
  ensureInventoryTimeline().then(() => renderInventoryTable(d, inv));
}

async function loadGoals() {
  try {
    const res = await fetch(`${apiBase()}/goals`);
    state.goals.data = res.ok ? await res.json() : { groups: [], ungrouped: [] };
  } catch {
    state.goals.data = { groups: [], ungrouped: [] };
  }
}

function goalMatchesFilter(goal, filter) {
  if (filter === "open") return !goal.completed_at;
  if (filter === "done") return !!goal.completed_at;
  return true;
}

function renderGoalRow(goal) {
  const done = !!goal.completed_at;
  const deleteBtn = done
    ? `<button type="button" class="goal-delete-btn" data-goal-id="${goal.id}">${esc(t("goals.delete"))}</button>`
    : "";
  return `<tr>
    <td>${esc(goal.item_name)}</td>
    <td>
      <div class="goal-progress-text">${fmt(goal.current_qty)} / ${fmt(goal.target_qty)}</div>
      <div class="progress-bar"><div class="progress-fill" style="width:${goal.progress_pct}%"></div></div>
    </td>
    <td><span class="badge ${done ? "badge-success" : "badge-warning"}">${esc(done ? t("goals.done") : t("goals.open"))}</span></td>
    <td class="goal-actions-cell">${deleteBtn}</td>
  </tr>`;
}

function renderGoalsTableBody(goals) {
  if (!goals.length) {
    return `<tr><td colspan="4" class="empty-state">${esc(t("goals.empty"))}</td></tr>`;
  }
  return goals.map(renderGoalRow).join("");
}

function bindGoalActions(panel) {
  panel.querySelectorAll(".goal-delete-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm(t("goals.deleteConfirm"))) return;
      const res = await fetch(`${apiBase()}/goals/${btn.dataset.goalId}`, { method: "DELETE" });
      if (res.ok) await loadGoals();
      renderGoals();
    });
  });

  panel.querySelectorAll(".goal-group-delete").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const name = btn.dataset.groupName;
      if (!confirm(t("goals.deleteGroupConfirm", { name }))) return;
      const res = await fetch(`${apiBase()}/goal-groups/${btn.dataset.groupId}`, { method: "DELETE" });
      if (res.ok) await loadGoals();
      renderGoals();
    });
  });

  panel.querySelectorAll(".goal-clear-completed").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const ids = (btn.dataset.goalIds || "").split(",").filter(Boolean);
      for (const id of ids) {
        await fetch(`${apiBase()}/goals/${id}`, { method: "DELETE" });
      }
      await loadGoals();
      renderGoals();
    });
  });

  panel.querySelectorAll(".goal-group-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const group = btn.dataset.group;
      const expanded = btn.getAttribute("aria-expanded") === "true";
      btn.setAttribute("aria-expanded", expanded ? "false" : "true");
      if (expanded) state.goals.collapsedGroups.add(group);
      else state.goals.collapsedGroups.delete(group);
      panel.querySelectorAll(`.goal-item-row[data-group="${group}"]`).forEach((row) => {
        row.classList.toggle("collapsed", expanded);
      });
    });
  });
}

function renderGoals() {
  const panel = document.getElementById("tab-goals");
  const g = state.goals;
  const filter = g.filter;
  const data = g.data || { groups: [], ungrouped: [] };

  const groupSections = data.groups.map((group) => {
    const goals = (group.goals || []).filter((goal) => goalMatchesFilter(goal, filter));
    if (!goals.length && filter !== "all") return "";
    const completed = goals.filter((goal) => goal.completed_at).length;
    const total = goals.length;
    const sectionKey = `group-${group.id}`;
    const expanded = !g.collapsedGroups.has(sectionKey);
    const completedIds = goals.filter((goal) => goal.completed_at).map((goal) => goal.id);
    const headerActions = `
      ${completedIds.length ? `<button type="button" class="goal-clear-completed" data-goal-ids="${completedIds.join(",")}">${esc(t("goals.clearCompleted"))}</button>` : ""}
      <button type="button" class="goal-group-delete" data-group-id="${group.id}" data-group-name="${esc(group.name)}">${esc(t("goals.deleteGroup"))}</button>`;
    const rows = goals.length
      ? goals.map((goal) => {
          const row = renderGoalRow(goal);
          return row.replace("<tr>", `<tr class="goal-item-row ${expanded ? "" : "collapsed"}" data-group="${sectionKey}">`);
        }).join("")
      : `<tr class="goal-item-row ${expanded ? "" : "collapsed"}" data-group="${sectionKey}"><td colspan="4" class="empty-state">${esc(t("goals.empty"))}</td></tr>`;

    return `
      <div class="card goals-group-card">
        <table class="goals-table">
          <tbody>
            <tr class="inv-group-row goal-group-header">
              <td colspan="4">
                <button type="button" class="inv-group-toggle goal-group-toggle" data-group="${sectionKey}" aria-expanded="${expanded}">
                  <span class="inv-group-title">${esc(group.name)}</span>
                  <span class="inv-group-meta">${esc(t("goals.groupProgress", { completed, total }))}</span>
                </button>
                <span class="goal-group-actions">${headerActions}</span>
              </td>
            </tr>
            ${rows}
          </tbody>
        </table>
      </div>`;
  }).join("");

  const ungrouped = (data.ungrouped || []).filter((goal) => goalMatchesFilter(goal, filter));
  const ungroupedSection = (filter === "all" || ungrouped.length) ? `
    <div class="card goals-group-card">
      <h3 class="goals-ungrouped-title">${esc(t("goals.ungrouped"))}</h3>
      <table class="goals-table">
        <thead>
          <tr>
            <th>${esc(t("goals.item"))}</th>
            <th>${esc(t("goals.progress"))}</th>
            <th>${esc(t("goals.status"))}</th>
            <th>${esc(t("goals.actions"))}</th>
          </tr>
        </thead>
        <tbody>${renderGoalsTableBody(ungrouped)}</tbody>
      </table>
    </div>` : "";

  const hasAny = groupSections || ungrouped.length || filter === "all";

  panel.innerHTML = `
    <div class="toolbar goals-toolbar">
      <select class="select-input" id="goals-filter">
        <option value="all" ${filter === "all" ? "selected" : ""}>${esc(t("goals.filterAll"))}</option>
        <option value="open" ${filter === "open" ? "selected" : ""}>${esc(t("goals.filterOpen"))}</option>
        <option value="done" ${filter === "done" ? "selected" : ""}>${esc(t("goals.filterDone"))}</option>
      </select>
      <button type="button" class="upload-btn" id="goals-create-group">${esc(t("goals.createGroup"))}</button>
    </div>
    ${hasAny ? groupSections + ungroupedSection : `<div class="card"><p class="empty-state">${esc(t("goals.empty"))}</p></div>`}`;

  document.getElementById("goals-filter").addEventListener("change", (e) => {
    state.goals.filter = e.target.value;
    renderGoals();
  });

  document.getElementById("goals-create-group").addEventListener("click", async () => {
    const name = prompt(t("goals.createGroupPrompt"));
    if (!name || !name.trim()) return;
    const res = await fetch(`${apiBase()}/goal-groups`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name.trim() }),
    });
    if (!res.ok) {
      alert(t("goals.groupCreateFailed"));
      return;
    }
    await loadGoals();
    renderGoals();
  });

  bindGoalActions(panel);
}

async function fetchGoalGroups() {
  const res = await fetch(`${apiBase()}/goal-groups`);
  return res.ok ? await res.json() : [];
}

function setupGoalModal() {
  document.getElementById("goal-modal-cancel").addEventListener("click", closeGoalModal);
  document.getElementById("goal-modal-backdrop").addEventListener("click", closeGoalModal);
  document.getElementById("goal-modal-group").addEventListener("change", (e) => {
    document.getElementById("goal-modal-new-group-wrap").hidden = e.target.value !== "new";
  });
  document.getElementById("goal-modal-submit").addEventListener("click", submitGoalModal);
}

function applyGoalModalI18n() {
  document.getElementById("goal-modal-title").textContent = t("goals.modalTitle");
  document.getElementById("goal-modal-qty-label").textContent = t("goals.targetQty");
  document.getElementById("goal-modal-group-label").textContent = t("goals.selectGroup");
  document.getElementById("goal-modal-new-group-label").textContent = t("goals.newGroupName");
  document.getElementById("goal-modal-cancel").textContent = t("goals.cancel");
  document.getElementById("goal-modal-submit").textContent = t("inventory.addGoal");
}

async function openGoalModal(item) {
  state.goalModalItem = item;
  applyGoalModalI18n();
  const modal = document.getElementById("goal-modal");
  const errEl = document.getElementById("goal-modal-error");
  errEl.hidden = true;
  errEl.textContent = "";

  document.getElementById("goal-modal-item").textContent = `${item.name} — ${t("goals.currentQty", { qty: fmt(item.qty) })}`;
  document.getElementById("goal-modal-qty").value = Math.max(item.qty + 1, 1);
  document.getElementById("goal-modal-new-group").value = "";
  document.getElementById("goal-modal-new-group-wrap").hidden = true;

  const groups = await fetchGoalGroups();
  const sel = document.getElementById("goal-modal-group");
  sel.innerHTML = `
    <option value="">${esc(t("goals.noGroup"))}</option>
    ${groups.map((g) => `<option value="${g.id}">${esc(g.name)}</option>`).join("")}
    <option value="new">${esc(t("goals.newGroup"))}</option>`;

  modal.hidden = false;
}

function closeGoalModal() {
  document.getElementById("goal-modal").hidden = true;
  state.goalModalItem = null;
}

async function submitGoalModal() {
  const item = state.goalModalItem;
  if (!item) return;
  const errEl = document.getElementById("goal-modal-error");
  errEl.hidden = true;

  const targetQty = parseInt(document.getElementById("goal-modal-qty").value, 10);
  if (!targetQty || targetQty <= 0) {
    errEl.textContent = t("goals.createFailed");
    errEl.hidden = false;
    return;
  }

  let groupId = null;
  const groupVal = document.getElementById("goal-modal-group").value;
  if (groupVal === "new") {
    const name = document.getElementById("goal-modal-new-group").value.trim();
    if (!name) {
      errEl.textContent = t("goals.groupCreateFailed");
      errEl.hidden = false;
      return;
    }
    const gRes = await fetch(`${apiBase()}/goal-groups`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (!gRes.ok) {
      errEl.textContent = t("goals.groupCreateFailed");
      errEl.hidden = false;
      return;
    }
    const gData = await gRes.json();
    groupId = gData.id;
  } else if (groupVal) {
    groupId = parseInt(groupVal, 10);
  }

  const res = await fetch(`${apiBase()}/goals`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ item_key: item.key, target_qty: targetQty, group_id: groupId }),
  });
  const result = await res.json();
  if (!res.ok) {
    errEl.textContent = result.error || t("goals.createFailed");
    errEl.hidden = false;
    return;
  }

  closeGoalModal();
  await loadGoals();
  renderGoals();
}

function showGoalsCompletedBanner(result) {
  const el = document.getElementById("goals-completed-banner");
  const completed = result.goals_completed || [];
  const groupsDone = result.groups_completed || [];
  if (!completed.length && !groupsDone.length) {
    el.hidden = true;
    el.innerHTML = "";
    return;
  }

  const items = completed.map((goal) => {
    const groupPrefix = goal.group_name
      ? t("goals.completedItemGroup", { name: goal.group_name })
      : "";
    return `<li>${esc(t("goals.completedItem", {
      group: groupPrefix,
      name: goal.item_name,
      current: fmt(goal.current_qty),
      target: fmt(goal.target_qty),
    }))}</li>`;
  }).join("");

  const groupLines = groupsDone.map((g) =>
    `<li class="goal-group-completed-line">${esc(t("goals.groupCompleted", { name: g.name }))}</li>`
  ).join("");

  el.hidden = false;
  el.className = "goals-completed-banner import-report import-report-info";
  el.innerHTML = `
    <div class="import-report-header">
      <strong>${esc(t("goals.completedBannerTitle"))}</strong>
      <button type="button" class="import-report-dismiss" title="${esc(t("actions.dismiss"))}">×</button>
    </div>
    <ul class="import-report-list">${items}${groupLines}</ul>`;

  el.querySelector(".import-report-dismiss").addEventListener("click", () => {
    el.hidden = true;
  });
}

function renderEquipment(d) {
  document.getElementById("tab-equipment").innerHTML = `
    <div class="card">
      <h3>${esc(t("equipment.title"))}</h3>
      <div class="equip-grid">
        ${d.equipment.map((eq) => `
          <div class="equip-slot ${eq.key ? "" : "empty"}">
            <div class="slot-name">${esc(eq.slot_name)}</div>
            <div class="item-name">${eq.name ? esc(eq.name) : "—"}</div>
          </div>`).join("")}
      </div>
    </div>`;
}

function renderQuests(d) {
  const panel = document.getElementById("tab-quests");
  const q = state.quests;
  const tabs = [
    { key: "story", label: t("quests.story") },
    { key: "daily", label: t("quests.daily") },
    { key: "weekly", label: t("quests.weekly") },
    { key: "guild", label: t("quests.guild") },
  ];

  let items = d.quests[q.tab] || [];
  if (q.tab === "story") {
    if (q.filter === "open") items = items.filter((x) => !x.completed);
    if (q.filter === "done") items = items.filter((x) => x.completed);
  } else {
    if (q.filter === "open") items = items.filter((x) => !x.claimed);
    if (q.filter === "done") items = items.filter((x) => x.claimed);
  }

  const isStory = q.tab === "story";
  panel.innerHTML = `
    <div class="quest-tabs">
      ${tabs.map((tab) => `<button class="quest-tab ${q.tab === tab.key ? "active" : ""}" data-tab="${tab.key}">${esc(tab.label)}</button>`).join("")}
    </div>
    <div class="toolbar">
      <select class="select-input" id="quest-filter">
        <option value="all" ${q.filter === "all" ? "selected" : ""}>${esc(t("quests.filterAll"))}</option>
        <option value="open" ${q.filter === "open" ? "selected" : ""}>${esc(t("quests.filterOpen"))}</option>
        <option value="done" ${q.filter === "done" ? "selected" : ""}>${esc(t("quests.filterDone"))}</option>
      </select>
    </div>
    <div class="card">
      <table>
        <thead><tr>
          <th>${esc(t("quests.quest"))}</th>
          <th>${esc(t("quests.progress"))}</th>
          <th>${esc(t("quests.status"))}</th>
        </tr></thead>
        <tbody>${items.map((quest) => {
          const done = isStory ? quest.completed : quest.claimed;
          return `<tr>
            <td>${esc(quest.name)}</td>
            <td>${fmt(quest.progress)}</td>
            <td><span class="badge ${done ? "badge-success" : "badge-warning"}">${esc(done ? t("quests.done") : t("quests.open"))}</span></td>
          </tr>`;
        }).join("")}</tbody>
      </table>
    </div>`;

  panel.querySelectorAll(".quest-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.quests.tab = btn.dataset.tab;
      renderQuests(state.data);
    });
  });
  document.getElementById("quest-filter").addEventListener("change", (e) => {
    state.quests.filter = e.target.value;
    renderQuests(state.data);
  });
}

function renderCombat(d) {
  const kills = Object.entries(d.combat.enemy_kills || {})
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => `<li><span>${esc(k.replace(/_/g, " "))}</span><span>${fmt(v)}</span></li>`).join("");

  const dungeons = Object.entries(d.combat.dungeon_runs || {})
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => `<li><span>${esc(k.replace(/_/g, " "))}</span><span>${esc(t("combat.runs", { count: fmt(v) }))}</span></li>`).join("");

  const recent = (d.recent_sessions || [])
    .map((s) => `<li><span>${esc(s.activity_display_name || s.activity_key)}</span><span>${esc(s.skill_name)}</span></li>`).join("");

  const active = (d.sessions || [])
    .map((s) => `<li><span>${esc(s.activity)}</span><span>${esc(s.skill)} · ${esc(s.completed ? t("combat.sessionDone") : t("combat.sessionRunning"))}</span></li>`).join("");

  const none = `<li>${esc(t("empty.none"))}</li>`;
  document.getElementById("tab-combat").innerHTML = `
    <div class="grid-2">
      <div class="card"><h3>${esc(t("combat.enemyKills"))}</h3><ul class="list-compact">${kills || none}</ul></div>
      <div class="card"><h3>${esc(t("combat.dungeonRuns"))}</h3><ul class="list-compact">${dungeons || none}</ul></div>
      <div class="card"><h3>${esc(t("combat.recentActivity"))}</h3><ul class="list-compact">${recent || none}</ul></div>
      <div class="card"><h3>${esc(t("combat.activeSessions"))}</h3><ul class="list-compact">${active || none}</ul></div>
    </div>`;
}

async function loadHistoryTab() {
  const panel = document.getElementById("tab-history");
  panel.innerHTML = `<p class='loading'>${esc(t("history.loading"))}</p>`;

  const [snapRes, tlRes] = await Promise.all([
    fetch(`${apiBase()}/snapshots`),
    fetch(`${apiBase()}/timeline`),
  ]);
  state.snapshots = await snapRes.json();
  state.timeline = await tlRes.json();

  if (state.snapshots.length === 0) {
    panel.innerHTML = `<p class='empty-state'>${esc(t("empty.noSnapshots"))}</p>`;
    return;
  }

  const h = state.history;
  if (!h.newerId) h.newerId = state.snapshots[0].id;
  if (!h.olderId && state.snapshots.length > 1) h.olderId = state.snapshots[1].id;

  panel.innerHTML = `
    <div class="grid-2">
      <div class="card">
        <h3>${esc(t("history.coinsChart"))}</h3>
        <div class="chart-wrap"><canvas id="chart-coins"></canvas></div>
      </div>
      <div class="card">
        <h3>${esc(t("history.levelChart"))}</h3>
        <div class="chart-wrap"><canvas id="chart-level"></canvas></div>
      </div>
    </div>
    <div class="card">
      <h3>${esc(t("history.snapshotCompare"))}</h3>
      <div class="toolbar">
        <select class="select-input" id="diff-older">
          ${state.snapshots.map((s) => option(s, h.olderId)).join("")}
        </select>
        <span>→</span>
        <select class="select-input" id="diff-newer">
          ${state.snapshots.map((s) => option(s, h.newerId)).join("")}
        </select>
        <button class="select-input" id="diff-run" style="background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600">${esc(t("actions.compare"))}</button>
      </div>
      <div id="diff-result"></div>
    </div>
    <div class="card">
      <h3>${esc(t("history.allSnapshots"))}</h3>
      <table>
        <thead><tr>
          <th>ID</th>
          <th>${esc(t("history.character"))}</th>
          <th>${esc(t("kpi.coins"))}</th>
          <th>${esc(t("kpi.totalLevel"))}</th>
          <th>${esc(t("meta.export"))}</th>
          <th>${esc(t("history.file"))}</th>
        </tr></thead>
        <tbody>${state.snapshots.map((s) => `
          <tr>
            <td>${s.id}</td>
            <td>${esc(s.character_name || "—")}</td>
            <td>${fmt(s.coins)}</td>
            <td>${s.total_level}</td>
            <td>${formatTs(s.exported_at)}</td>
            <td>${esc(s.source_file)}</td>
          </tr>`).join("")}
        </tbody>
      </table>
    </div>`;

  renderTimelineCharts();
  document.getElementById("diff-older").addEventListener("change", (e) => { h.olderId = +e.target.value; });
  document.getElementById("diff-newer").addEventListener("change", (e) => { h.newerId = +e.target.value; });
  document.getElementById("diff-run").addEventListener("click", runDiff);
  if (h.olderId && h.newerId && h.olderId !== h.newerId) runDiff();
}

function option(s, selected) {
  const label = `#${s.id} · ${s.character_name || "?"} · ${formatTs(s.exported_at)}`;
  return `<option value="${s.id}" ${s.id === selected ? "selected" : ""}>${esc(label)}</option>`;
}

function renderTimelineCharts() {
  const tl = state.timeline;
  if (!tl.length) return;

  const labels = tl.map((s) => formatTs(s.exported_at));
  const coins = tl.map((s) => s.coins);
  const levels = tl.map((s) => s.total_level);

  destroyChart("coins");
  destroyChart("level");

  state.charts.coins = new Chart(document.getElementById("chart-coins"), {
    type: "line",
    data: { labels, datasets: [{ label: t("kpi.coins"), data: coins, borderColor: "#6c8cff", tension: 0.3, fill: false }] },
    options: chartOpts(),
  });
  state.charts.level = new Chart(document.getElementById("chart-level"), {
    type: "line",
    data: { labels, datasets: [{ label: t("kpi.totalLevel"), data: levels, borderColor: "#4ade80", tension: 0.3, fill: false }] },
    options: chartOpts(),
  });
}

function chartOpts() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { labels: { color: "#8b92a8" } } },
    scales: {
      x: { ticks: { color: "#8b92a8" }, grid: { color: "#2d3348" } },
      y: { ticks: { color: "#8b92a8" }, grid: { color: "#2d3348" } },
    },
  };
}

function destroyChart(key) {
  if (state.charts[key]) {
    state.charts[key].destroy();
    delete state.charts[key];
  }
}

async function runDiff() {
  const h = state.history;
  const el = document.getElementById("diff-result");
  if (!h.olderId || !h.newerId || h.olderId === h.newerId) {
    el.innerHTML = `<p class='empty-state'>${esc(t("empty.pickTwoSnapshots"))}</p>`;
    return;
  }
  const older = Math.min(h.olderId, h.newerId);
  const newer = Math.max(h.olderId, h.newerId);
  const res = await fetch(`${apiBase()}/snapshots/${older}/diff/${newer}`);
  const diff = await res.json();
  if (diff.error) {
    el.innerHTML = `<p class='empty-state'>${esc(diff.error)}</p>`;
    return;
  }

  const coinDelta = diff.summary.coins_delta;
  const coinCls = coinDelta >= 0 ? "delta-pos" : "delta-neg";
  const levelDelta = diff.summary.total_level_delta;

  const invRows = diff.inventory_changes.slice(0, 50).map((i) => `
    <tr>
      <td>${esc(i.name)}</td>
      <td>${fmt(i.old_qty)} → ${fmt(i.new_qty)}</td>
      <td class="${i.delta >= 0 ? "delta-pos" : "delta-neg"}">${i.delta >= 0 ? "+" : ""}${fmt(i.delta)}</td>
    </tr>`).join("");

  const skRows = diff.skill_changes
    .sort((a, b) => b.xp_delta - a.xp_delta)
    .slice(0, 20)
    .map((s) => `
    <tr>
      <td>${esc(s.name)}</td>
      <td>${s.old_level} → ${s.new_level}</td>
      <td class="${s.xp_delta >= 0 ? "delta-pos" : "delta-neg"}">${s.xp_delta >= 0 ? "+" : ""}${fmt(s.xp_delta)} XP</td>
    </tr>`).join("");

  const noChanges = `<tr><td colspan='3'>${esc(t("empty.noChanges"))}</td></tr>`;
  el.innerHTML = `
    <p>${esc(t("history.coinsSummary", {
      delta: `${coinDelta >= 0 ? "+" : ""}${fmt(coinDelta)}`,
      levelDelta: `${levelDelta >= 0 ? "+" : ""}${levelDelta}`,
    }))}</p>
    <h4 style="margin-top:16px">${esc(t("history.inventoryChanges", { count: diff.inventory_changes.length }))}</h4>
    <table><thead><tr>
      <th>${esc(t("inventory.item"))}</th>
      <th>${esc(t("inventory.qty"))}</th>
      <th>${esc(t("history.delta"))}</th>
    </tr></thead>
    <tbody>${invRows || noChanges}</tbody></table>
    <h4 style="margin-top:16px">${esc(t("history.skillChanges", { count: diff.skill_changes.length }))}</h4>
    <table><thead><tr>
      <th>${esc(t("skills.skill"))}</th>
      <th>${esc(t("skills.level"))}</th>
      <th>${esc(t("history.xpDelta"))}</th>
    </tr></thead>
    <tbody>${skRows || noChanges}</tbody></table>`;
}

function fmt(n) {
  if (n == null) return "—";
  return Number(n).toLocaleString(I18n.localeTag());
}

function formatTs(ts) {
  if (!ts) return "—";
  const d = new Date(Number(ts));
  return d.toLocaleString(I18n.localeTag(), { dateStyle: "short", timeStyle: "short" });
}

function esc(s) {
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
