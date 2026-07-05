/* Idle Fantasy Save Viewer – client UI */

let state = {
  data: null,
  snapshots: [],
  timeline: [],
  inventory: { search: "", categories: new Set(), sort: "category", highlightEquipped: false, collapsedGroups: new Set() },
  skills: { search: "", sort: "level", sortAsc: false, advisorKey: null, advisor: null, advisorLoading: false },
  quests: { tab: "story", filter: "all" },
  goals: { filter: "all", collapsedGroups: new Set(), data: { groups: [], ungrouped: [] } },
  goalsOverview: null,
  goalModalItem: null,
  history: { olderId: null, newerId: null, diff: null },
  charts: {},
  inventoryTimeline: null,
  skillTimeline: null,
  combatTimeline: null,
  lastImportChanges: null,
  globalSearch: "",
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
  await Pwa.init();
  setupViewerBanner();
  setupNav();
  setupUpload();
  setupExport();
  setupViewerDbImport();
  setupGlobalSearch();
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
  const exportEl = document.getElementById("export-viewer");
  if (exportEl) exportEl.title = t("viewerDb.exportHint");
}

function setupLanguage() {
  const sel = document.getElementById("locale-select");
  sel.value = I18n.getPreference();
  sel.addEventListener("change", async (e) => {
    await I18n.setPreference(e.target.value);
    applyStaticI18n();
    Pwa.refreshHint();
    resetLocaleDependentPanels();
    if (state.data) renderAll();
    const gs = document.getElementById("global-search");
    if (gs) gs.placeholder = t("search.global");
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

function activateTab(tab) {
  const btn = document.querySelector(`.nav-btn[data-tab="${tab}"]`);
  if (!btn) return;
  document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
  btn.classList.add("active");
  document.getElementById(`tab-${tab}`).classList.add("active");
  if (tab === "history") loadHistoryTab();
  if (tab === "goals") trackEvent("Goals Tab");
  if (tab === "backup") trackEvent("Backup Tab");
}

function setupNav() {
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab;
      activateTab(tab);
      history.replaceState(null, "", `#${tab}`);
    });
  });
  const hash = (location.hash || "#overview").slice(1).split("?")[0] || "overview";
  if (document.querySelector(`.nav-btn[data-tab="${hash}"]`)) activateTab(hash);
}

function setupExport() {
  const el = document.getElementById("export-viewer");
  if (!el) return;
  el.href = `${apiBase()}/export`;
  el.title = t("viewerDb.exportHint");
  el.addEventListener("click", () => trackEvent("Viewer Export"));
}

function setupViewerDbImport() {
  const input = document.getElementById("viewer-db-upload");
  if (!input) return;
  input.addEventListener("change", async (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".db")) {
      alert(t("viewerDb.invalidFile"));
      return;
    }
    if (!confirm(t("viewerDb.importConfirm"))) return;

    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${apiBase()}/import-viewer`, { method: "POST", body: fd });
    const result = await res.json();
    if (!res.ok || result.error) {
      alert(result.error || t("viewerDb.importFailed"));
      return;
    }

    trackEvent("Viewer Import", {
      snapshots: String(result.snapshots || 0),
      goals: String(result.goals || 0),
    });
    state.lastImportChanges = null;
    state.inventoryTimeline = null;
    state.skillTimeline = null;
    state.combatTimeline = null;
    await loadData();
    alert(t("viewerDb.importSuccess", {
      snapshots: result.snapshots || 0,
      goals: result.goals || 0,
    }));
  });
}

function setupGlobalSearch() {
  const input = document.getElementById("global-search");
  if (!input) return;
  input.placeholder = t("search.global");
  input.addEventListener("input", (e) => {
    state.globalSearch = e.target.value;
    renderGlobalSearchResults();
  });
  document.addEventListener("click", (e) => {
    const wrap = document.querySelector(".global-search-wrap");
    const results = document.getElementById("global-search-results");
    if (!wrap || !results || wrap.contains(e.target) || results.contains(e.target)) return;
    results.hidden = true;
  });
}

function collectAllGoals() {
  const data = state.goals.data || { groups: [], ungrouped: [] };
  return [
    ...(data.ungrouped || []),
    ...(data.groups || []).flatMap((g) => g.goals || []),
  ];
}

function collectOpenGoalKeys() {
  const keys = { items: new Set(), skills: new Set() };
  for (const goal of collectAllGoals()) {
    if (goal.completed_at) continue;
    if (goal.goal_type === "skill") keys.skills.add(goal.skill_key || goal.item_key);
    else keys.items.add(goal.item_key);
  }
  return keys;
}

function renderGlobalSearchResults() {
  const el = document.getElementById("global-search-results");
  const q = state.globalSearch.trim().toLowerCase();
  if (!el || !q || !state.data) {
    if (el) el.hidden = true;
    return;
  }

  const hits = [];
  for (const item of state.data.inventory) {
    if (item.name.toLowerCase().includes(q) || item.key.toLowerCase().includes(q)) {
      hits.push({ type: "item", tab: "inventory", key: item.key, name: item.name, sub: fmt(item.qty) });
    }
  }
  for (const sk of state.data.skills) {
    if (sk.name.toLowerCase().includes(q) || sk.key.toLowerCase().includes(q)) {
      hits.push({ type: "skill", tab: "skills", key: sk.key, name: sk.name, sub: `Lv ${sk.level}` });
    }
  }
  for (const goal of collectAllGoals()) {
    if (goal.item_name.toLowerCase().includes(q)) {
      hits.push({
        type: "goal",
        tab: "goals",
        key: String(goal.id),
        name: goal.item_name,
        sub: goal.completed_at ? t("goals.done") : t("goals.open"),
      });
    }
  }

  if (!hits.length) {
    el.hidden = false;
    el.innerHTML = `<p class="global-search-empty">${esc(t("search.noResults"))}</p>`;
    return;
  }

  el.hidden = false;
  el.innerHTML = hits.slice(0, 15).map((hit) => `
    <button type="button" class="global-search-hit" data-tab="${esc(hit.tab)}" data-type="${esc(hit.type)}" data-key="${esc(hit.key)}">
      <span class="global-search-hit-type">${esc(t(`search.type.${hit.type}`))}</span>
      <span class="global-search-hit-name">${esc(hit.name)}</span>
      <span class="global-search-hit-sub">${esc(hit.sub)}</span>
    </button>`).join("");

  el.querySelectorAll(".global-search-hit").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab;
      const type = btn.dataset.type;
      const key = btn.dataset.key;
      activateTab(tab);
      history.replaceState(null, "", `#${tab}`);
      if (type === "item") {
        state.inventory.search = key;
        renderInventory(state.data);
      } else if (type === "skill") {
        state.skills.search = key;
        renderSkills(state.data);
      }
      el.hidden = true;
      document.getElementById("global-search").value = "";
      state.globalSearch = "";
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
      state.lastImportChanges = result.import_changes || null;
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
    const [res, , overviewRes] = await Promise.all([
      fetch(`${apiBase()}/snapshot/latest`),
      loadGoals(),
      fetch(`${apiBase()}/goals/overview`),
    ]);
    state.goalsOverview = overviewRes.ok ? await overviewRes.json() : null;
    if (!res.ok) {
      showEmpty(getViewerId() ? t("empty.noSaveWeb") : t("empty.noSave"));
      renderGoals();
      return;
    }
    state.data = await res.json();
    state.inventoryTimeline = null;
    state.skillTimeline = null;
    state.combatTimeline = null;
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
  bindImportChangesCard();
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
    <div class="kpi"><div class="kpi-label">${esc(t("kpi.totalQty"))}</div><div class="kpi-value">${fmt(m.total_items)}</div></div>
    ${state.goalsOverview ? `<div class="kpi kpi-goals"><div class="kpi-label">${esc(t("kpi.goalsOpen"))}</div><div class="kpi-value">${state.goalsOverview.open}</div></div>` : ""}`;
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
    ${renderImportChangesCard(state.lastImportChanges)}
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

function renderImportChangesCard(changes) {
  if (!changes?.has_previous) return "";
  const invTop = (changes.top_inventory || []).map((i) =>
    `<li><span>${esc(i.name)}</span><span class="${i.delta >= 0 ? "delta-pos" : "delta-neg"}">${i.delta >= 0 ? "+" : ""}${fmt(i.delta)}</span></li>`
  ).join("");
  const skTop = (changes.top_skills || []).map((s) =>
    `<li><span>${esc(s.name)}</span><span class="${s.xp_delta >= 0 ? "delta-pos" : "delta-neg"}">+${fmt(s.xp_delta)} XP</span></li>`
  ).join("");

  return `
    <div class="card import-changes-card" id="import-changes-card">
      <div class="import-report-header">
        <h3>${esc(t("import.changesTitle"))}</h3>
        <button type="button" class="import-report-dismiss" id="import-changes-dismiss" title="${esc(t("actions.dismiss"))}">×</button>
      </div>
      <p class="import-changes-summary">${esc(t("import.changesSummary", {
        coins: `${changes.coins_delta >= 0 ? "+" : ""}${fmt(changes.coins_delta)}`,
        level: `${changes.total_level_delta >= 0 ? "+" : ""}${changes.total_level_delta}`,
        inv: changes.inventory_changes,
        skills: changes.skill_changes,
      }))}</p>
      <ul class="list-compact import-changes-stats">
        ${changes.quests_completed ? `<li><span>${esc(t("import.questsCompleted"))}</span><span>${changes.quests_completed}</span></li>` : ""}
        ${changes.slayer_kills_delta ? `<li><span>${esc(t("import.slayerKills"))}</span><span>+${changes.slayer_kills_delta}</span></li>` : ""}
        ${changes.dungeon_runs_delta ? `<li><span>${esc(t("import.dungeonRuns"))}</span><span>+${changes.dungeon_runs_delta}</span></li>` : ""}
      </ul>
      ${invTop ? `<h4>${esc(t("import.topInventory"))}</h4><ul class="list-compact">${invTop}</ul>` : ""}
      ${skTop ? `<h4>${esc(t("import.topSkills"))}</h4><ul class="list-compact">${skTop}</ul>` : ""}
    </div>`;
}

function bindImportChangesCard() {
  const dismiss = document.getElementById("import-changes-dismiss");
  if (!dismiss) return;
  dismiss.addEventListener("click", () => {
    state.lastImportChanges = null;
    const card = document.getElementById("import-changes-card");
    if (card) card.remove();
  });
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
      <div class="card skill-advisor-card" id="skill-advisor-card">
        <h3 id="skill-advisor-title"></h3>
        <p class="skill-advisor-hint" id="skill-advisor-hint"></p>
        <div id="skill-advisor-body"></div>
      </div>
      <div class="card">
        <table class="skills-table" id="skills-table">
          <thead><tr id="skills-thead-row">
            <th data-sort="name"></th>
            <th data-sort="level"></th>
            <th data-sort="xp">XP</th>
            <th></th>
            <th class="col-actions"></th>
          </tr></thead>
          <tbody id="skill-tbody"></tbody>
        </table>
      </div>`;

    document.getElementById("skill-search").addEventListener("input", (e) => {
      state.skills.search = e.target.value;
      ensureSkillTimeline().then(() => renderSkillsBody(state.data));
    });
    document.getElementById("skill-sort").addEventListener("change", (e) => {
      state.skills.sort = e.target.value;
      ensureSkillTimeline().then(() => renderSkillsBody(state.data));
    });
    panel.querySelectorAll("th[data-sort]").forEach((th) => {
      th.addEventListener("click", () => {
        const key = th.dataset.sort;
        if (state.skills.sort === key) state.skills.sortAsc = !state.skills.sortAsc;
        else { state.skills.sort = key; state.skills.sortAsc = false; }
        ensureSkillTimeline().then(() => renderSkillsBody(state.data));
      });
    });
  }

  const skillsTable = document.getElementById("skills-table");
  if (skillsTable) {
    skillsTable.classList.toggle("has-trend", skillTrendEnabled());
  }
  updateSkillsTrendHeader();

  document.getElementById("skill-search").placeholder = t("skills.search");
  document.getElementById("skill-sort").options[0].textContent = t("skills.sortLevel");
  document.getElementById("skill-sort").options[1].textContent = t("skills.sortXp");
  document.getElementById("skill-sort").options[2].textContent = t("skills.sortName");
  panel.querySelector('th[data-sort="name"]').textContent = t("skills.skill");
  panel.querySelector('th[data-sort="level"]').textContent = t("skills.level");
  panel.querySelectorAll("thead tr th")[3].textContent = t("skills.progress");
  panel.querySelector("thead tr th.col-actions").textContent = t("goals.actions");

  document.getElementById("skill-search").value = s.search;
  document.getElementById("skill-sort").value = s.sort;
  const advisorTitle = document.getElementById("skill-advisor-title");
  if (advisorTitle) advisorTitle.textContent = t("skills.advisorTitle");
  ensureSkillTimeline().then(() => renderSkillsBody(d));
}

function updateSkillsTrendHeader() {
  const row = document.getElementById("skills-thead-row");
  if (!row) return;
  const showTrend = skillTrendEnabled();
  let trendTh = row.querySelector("th.col-trend");
  if (showTrend && !trendTh) {
    trendTh = document.createElement("th");
    trendTh.className = "col-trend";
    trendTh.textContent = t("skills.trend");
    row.insertBefore(trendTh, row.querySelector('th[data-sort="level"]'));
  } else if (!showTrend && trendTh) {
    trendTh.remove();
  } else if (showTrend && trendTh) {
    trendTh.textContent = t("skills.trend");
  }
}

function renderSkillsBody(d) {
  const showTrend = skillTrendEnabled();
  const skillsTable = document.getElementById("skills-table");
  if (skillsTable) skillsTable.classList.toggle("has-trend", showTrend);
  updateSkillsTrendHeader();
  const s = state.skills;
  const openGoals = collectOpenGoalKeys();
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

  document.getElementById("skill-tbody").innerHTML = items.map((sk) => {
    const hasGoal = openGoals.skills.has(sk.key);
    const selected = state.skills.advisorKey === sk.key;
    return `
    <tr class="skill-row ${hasGoal ? "has-goal" : ""} ${selected ? "skill-row-selected" : ""}" data-skill-key="${esc(sk.key)}" tabindex="0" role="button">
      <td>${esc(sk.name)}${hasGoal ? `<span class="goal-mark" title="${esc(t("goals.hasGoal"))}">🎯</span>` : ""}</td>
      ${showTrend ? renderSkillSparkCell(sk) : ""}
      <td>${sk.level}</td>
      <td>${fmt(sk.xp)}</td>
      <td style="min-width:140px">
        ${sk.progress_pct}%
        <div class="progress-bar"><div class="progress-fill" style="width:${sk.progress_pct}%"></div></div>
      </td>
      <td class="col-actions">
        <button type="button" class="goal-add-btn" data-skill-key="${esc(sk.key)}" data-skill-name="${esc(sk.name)}" data-skill-level="${sk.level}" title="${esc(t("skills.addGoalFor", { name: sk.name }))}" aria-label="${esc(t("skills.addGoalFor", { name: sk.name }))}">+</button>
      </td>
    </tr>`;
  }).join("");

  bindSparklines(document.getElementById("skill-tbody"));

  document.getElementById("skill-tbody").querySelectorAll(".goal-add-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      openGoalModal({
        key: btn.dataset.skillKey,
        name: btn.dataset.skillName,
        level: Number(btn.dataset.skillLevel),
        goalType: "skill",
      });
    });
  });

  document.getElementById("skill-tbody").querySelectorAll(".skill-row").forEach((row) => {
    const openAdvisor = () => {
      const key = row.dataset.skillKey;
      if (!key) return;
      state.skills.advisorKey = key;
      loadSkillAdvisor(key).then(() => renderSkillsBody(state.data));
    };
    row.addEventListener("click", (e) => {
      if (e.target.closest(".goal-add-btn, .inv-spark-btn")) return;
      openAdvisor();
    });
    row.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" && e.key !== " ") return;
      e.preventDefault();
      openAdvisor();
    });
  });

  renderSkillAdvisorCard();
}

async function loadSkillAdvisor(skillKey) {
  state.skills.advisorLoading = true;
  renderSkillAdvisorCard();
  try {
    const res = await fetch(`${apiBase()}/advisor/${encodeURIComponent(skillKey)}`);
    state.skills.advisor = res.ok ? await res.json() : { supported: false, error: "load_failed" };
  } catch {
    state.skills.advisor = { supported: false, error: "load_failed" };
  } finally {
    state.skills.advisorLoading = false;
  }
}

function formatAdvisorMaterials(materials) {
  return Object.entries(materials || {})
    .map(([key, qty]) => `${qty}× ${key.replace(/_/g, " ")}`)
    .join(", ");
}

function formatAdvisorMissing(missing) {
  return Object.entries(missing || {})
    .map(([key, qty]) => `${qty}× ${key.replace(/_/g, " ")}`)
    .join(", ");
}

function renderSkillAdvisorCard() {
  const hint = document.getElementById("skill-advisor-hint");
  const body = document.getElementById("skill-advisor-body");
  if (!hint || !body) return;

  const adv = state.skills.advisor;
  const key = state.skills.advisorKey;

  if (!key) {
    hint.hidden = false;
    hint.textContent = t("skills.advisorHint");
    body.innerHTML = "";
    return;
  }

  if (state.skills.advisorLoading) {
    hint.hidden = true;
    body.innerHTML = `<p class="loading">${esc(t("skills.advisorLoading"))}</p>`;
    return;
  }

  if (!adv || !adv.supported) {
    hint.hidden = false;
    hint.textContent = adv?.error === "unsupported_skill"
      ? t("skills.advisorUnsupported")
      : t("skills.advisorUnavailable");
    body.innerHTML = "";
    return;
  }

  hint.hidden = true;
  const xpRemain = adv.xp_remaining_in_level ?? 0;
  const summary = t("skills.advisorSummary", {
    name: adv.skill_name,
    level: adv.skill_level,
    xp: fmt(xpRemain),
  });

  if (!adv.recommendations?.length) {
    body.innerHTML = `<p class="skill-advisor-summary">${esc(summary)}</p><p class="empty-state">${esc(t("skills.advisorNoRecipes"))}</p>`;
    return;
  }

  const rows = adv.recommendations.map((rec) => {
    const mats = rec.can_craft
      ? formatAdvisorMaterials(rec.materials)
      : t("skills.advisorMissing", { items: formatAdvisorMissing(rec.missing_materials) });
    const eta = rec.eta_minutes_to_level > 0
      ? t("skills.advisorEta", { minutes: fmt(rec.eta_minutes_to_level) })
      : "—";
    const crafts = rec.crafts_to_next_level ?? 0;
    const goalLabel = t("skills.advisorAdoptGoalFor", { name: rec.display_name, count: fmt(crafts) });
    const goalCell = crafts > 0
      ? `<button type="button" class="goal-add-btn skill-advisor-goal-btn" data-activity-key="${esc(rec.activity_key)}" data-crafts="${crafts}" title="${esc(goalLabel)}" aria-label="${esc(goalLabel)}">+</button>`
      : `<span class="inv-spark-empty">—</span>`;
    return `<tr>
      <td>${esc(rec.display_name)}</td>
      <td class="num">${rec.xp_per_minute.toFixed(1)}</td>
      <td>${rec.level_required}</td>
      <td class="skill-advisor-mats">${esc(mats)}</td>
      <td class="num">${esc(eta)}</td>
      <td class="col-actions">
        ${goalCell}
      </td>
    </tr>`;
  }).join("");

  const skillGoalLabel = t("skills.advisorAdoptSkillGoal", { level: adv.skill_level + 1 });
  body.innerHTML = `
    <div class="skill-advisor-summary-row">
      <p class="skill-advisor-summary">${esc(summary)}</p>
      <button type="button" class="btn-secondary skill-advisor-skill-goal-btn">${esc(skillGoalLabel)}</button>
    </div>
    <div class="table-wrap">
      <table class="skill-advisor-table">
        <thead><tr>
          <th>${esc(t("skills.advisorActivity"))}</th>
          <th>${esc(t("skills.advisorXpMin"))}</th>
          <th>${esc(t("skills.advisorReqLevel"))}</th>
          <th>${esc(t("skills.advisorMaterials"))}</th>
          <th>${esc(t("skills.advisorEtaCol"))}</th>
          <th class="col-actions">${esc(t("goals.actions"))}</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;

  body.querySelector(".skill-advisor-skill-goal-btn")?.addEventListener("click", () => {
    adoptAdvisorSkillGoal();
  });
  body.querySelectorAll(".skill-advisor-goal-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      adoptAdvisorItemGoal(btn.dataset.activityKey, Number(btn.dataset.crafts));
    });
  });
}

async function adoptAdvisorSkillGoal() {
  const adv = state.skills.advisor;
  if (!adv?.supported || !adv.skill_key) return;
  const targetLevel = adv.skill_level + 1;
  const res = await fetch(`${apiBase()}/goals`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      goal_type: "skill",
      skill_key: adv.skill_key,
      target_level: targetLevel,
      mode: "absolute",
    }),
  });
  const result = await res.json();
  if (!res.ok) {
    alert(result.error || t("goals.createFailed"));
    return;
  }
  trackEvent("Goal Create", { source: "advisor", type: "skill", mode: "absolute" });
  await refreshGoalsAfterCreate();
  alert(t("skills.advisorGoalCreated", { name: adv.skill_name, target: targetLevel }));
}

async function adoptAdvisorItemGoal(activityKey, crafts) {
  const adv = state.skills.advisor;
  if (!adv?.supported || !activityKey) return;
  const rec = adv.recommendations?.find((r) => r.activity_key === activityKey);
  const name = rec?.display_name || activityKey.replace(/_/g, " ");
  const count = Number(crafts);
  if (!count || count <= 0) return;
  const res = await fetch(`${apiBase()}/goals`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      item_key: activityKey,
      target_qty: count,
      mode: "relative",
    }),
  });
  const result = await res.json();
  if (!res.ok) {
    alert(result.error || t("goals.createFailed"));
    return;
  }
  trackEvent("Goal Create", { source: "advisor", type: "item", mode: "relative" });
  await refreshGoalsAfterCreate();
  alert(t("skills.advisorItemGoalCreated", { name, count: fmt(count) }));
}

async function refreshGoalsAfterCreate() {
  await loadGoals();
  const overviewRes = await fetch(`${apiBase()}/goals/overview`);
  if (overviewRes.ok) state.goalsOverview = await overviewRes.json();
  renderGoals();
  if (state.data) {
    renderHeader(state.data);
    renderSkills(state.data);
    renderInventory(state.data);
  }
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

function skillTrendEnabled() {
  return (state.skillTimeline?.snapshots?.length || 0) >= 2;
}

function skillLevelSeries(skillKey) {
  const tl = state.skillTimeline;
  if (!tl?.series) return null;
  const values = tl.series[skillKey];
  if (!values || values.length < 2) return null;
  if (values.filter((v) => v > 0).length < 2) return null;
  return values;
}

async function ensureCombatTimeline() {
  if (state.combatTimeline) return state.combatTimeline;
  try {
    const res = await fetch(`${apiBase()}/combat/timeline`);
    state.combatTimeline = res.ok
      ? await res.json()
      : { snapshots: [], enemy_kills: {}, dungeon_runs: {} };
  } catch {
    state.combatTimeline = { snapshots: [], enemy_kills: {}, dungeon_runs: {} };
  }
  return state.combatTimeline;
}

function combatTrendEnabled() {
  return (state.combatTimeline?.snapshots?.length || 0) >= 2;
}

function combatSeries(combatType, key) {
  const tl = state.combatTimeline;
  if (!tl) return null;
  const bucket = combatType === "dungeon" ? tl.dungeon_runs : tl.enemy_kills;
  const values = bucket?.[key];
  if (!values || values.length < 2) return null;
  if (values.filter((v) => v > 0).length < 2) return null;
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

function renderSkillSparkCell(skill) {
  const values = skillLevelSeries(skill.key);
  if (!values) {
    return `<td class="col-trend"><span class="inv-spark-empty">—</span></td>`;
  }
  return `
    <td class="col-trend">
      <button type="button" class="inv-spark-btn" data-skill-key="${esc(skill.key)}" data-skill-name="${esc(skill.name)}" title="${esc(t("skills.trendExpand"))}" aria-label="${esc(t("skills.trendExpandFor", { name: skill.name }))}">
        ${sparklineSvg(values)}
      </button>
    </td>`;
}

function renderCombatSparkCell(combatKey, combatType, displayName) {
  const values = combatSeries(combatType, combatKey);
  if (!values) {
    return `<td class="col-trend"><span class="inv-spark-empty">—</span></td>`;
  }
  const expandKey = combatType === "dungeon" ? "trendExpandRunsFor" : "trendExpandKillsFor";
  return `
    <td class="col-trend">
      <button type="button" class="inv-spark-btn" data-combat-key="${esc(combatKey)}" data-combat-type="${esc(combatType)}" data-combat-name="${esc(displayName)}" title="${esc(t("combat.trendExpand"))}" aria-label="${esc(t(`combat.${expandKey}`, { name: displayName }))}">
        ${sparklineSvg(values)}
      </button>
    </td>`;
}

function setupTrendChartModal() {
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
    el.addEventListener("click", closeTrendChartModal);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !modal.hidden) closeTrendChartModal();
  });
}

function openTrendChartModal(title, snapshots, values, datasetLabel, color = "#4ade80", skillSeries = false) {
  setupTrendChartModal();
  const modal = document.getElementById("inv-chart-modal");
  document.getElementById("inv-chart-modal-title").textContent = title;
  modal.hidden = false;
  document.body.classList.add("inv-chart-modal-open");

  destroyChart("trendModal");
  const bgMap = {
    "#6c8cff": "rgba(108, 140, 255, 0.12)",
    "#4ade80": "rgba(74, 222, 128, 0.12)",
    "#f87171": "rgba(248, 113, 113, 0.12)",
    "#fb923c": "rgba(251, 146, 60, 0.12)",
  };
  const bg = bgMap[color] || "rgba(74, 222, 128, 0.12)";
  const points = skillSeries
    ? skillTimelineChartPoints(snapshots, values)
    : timelineChartPoints(snapshots, values);
  state.charts.trendModal = new Chart(document.getElementById("inv-chart-modal-canvas"), {
    type: "line",
    data: {
      datasets: [{
        label: datasetLabel,
        data: points,
        borderColor: color,
        backgroundColor: bg,
        tension: skillSeries ? 0 : 0.3,
        fill: true,
        spanGaps: false,
      }],
    },
    options: chartOptsTime(snapshots),
  });
}

function openInventoryChartModal(itemKey, itemName) {
  const values = itemQtySeries(itemKey);
  const tl = state.inventoryTimeline;
  if (!values || !tl) return;
  openTrendChartModal(itemName, tl.snapshots, values, t("inventory.qty"), "#6c8cff");
}

function openSkillChartModal(skillKey, skillName) {
  const values = skillLevelSeries(skillKey);
  const tl = state.skillTimeline;
  if (!values || !tl) return;
  openTrendChartModal(skillName, tl.snapshots, values, t("skills.level"), "#4ade80", true);
}

function openCombatChartModal(combatType, combatKey, combatName) {
  const values = combatSeries(combatType, combatKey);
  const tl = state.combatTimeline;
  if (!values || !tl) return;
  const isDungeon = combatType === "dungeon";
  const label = isDungeon ? t("combat.runsLabel") : t("combat.kills");
  const color = isDungeon ? "#fb923c" : "#f87171";
  openTrendChartModal(combatName, tl.snapshots, values, label, color);
}

function closeTrendChartModal() {
  const modal = document.getElementById("inv-chart-modal");
  if (!modal || modal.hidden) return;
  modal.hidden = true;
  document.body.classList.remove("inv-chart-modal-open");
  destroyChart("trendModal");
}

function bindSparklines(container) {
  if (!container) return;
  container.querySelectorAll(".inv-spark-btn[data-item-key]").forEach((btn) => {
    btn.addEventListener("click", () => {
      openInventoryChartModal(btn.dataset.itemKey, btn.dataset.itemName);
    });
  });
  container.querySelectorAll(".inv-spark-btn[data-skill-key]").forEach((btn) => {
    btn.addEventListener("click", () => {
      openSkillChartModal(btn.dataset.skillKey, btn.dataset.skillName);
    });
  });
  container.querySelectorAll(".inv-spark-btn[data-combat-key]").forEach((btn) => {
    btn.addEventListener("click", () => {
      openCombatChartModal(btn.dataset.combatType, btn.dataset.combatKey, btn.dataset.combatName);
    });
  });
}

function renderInventoryTable(d, inv) {
  const items = getFilteredInventoryItems(d, inv);
  const showTrend = inventoryTrendEnabled();
  const colSpan = showTrend ? 5 : 4;
  const openGoals = collectOpenGoalKeys();
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
    const rows = catItems.map((i) => {
      const hasGoal = openGoals.items.has(i.key);
      return `
      <tr class="inv-item-row ${i.equipped && inv.highlightEquipped ? "item-equipped" : ""} ${hasGoal ? "has-goal" : ""} ${expanded ? "" : "collapsed"}" data-group="${esc(cat)}">
        <td class="col-name">${esc(i.name)}${i.equipped ? `<span class="equipped-mark" title="${esc(t("inventory.equipped"))}">⚡</span>` : ""}${hasGoal ? `<span class="goal-mark" title="${esc(t("goals.hasGoal"))}">🎯</span>` : ""}</td>
        ${showTrend ? renderItemSparkCell(i) : ""}
        <td class="col-qty">${fmt(i.qty)}</td>
        <td class="col-key"><code>${esc(i.key)}</code></td>
        <td class="col-actions">
          <button type="button" class="goal-add-btn" data-item-key="${esc(i.key)}" data-item-name="${esc(i.name)}" data-item-qty="${i.qty}" title="${esc(t("inventory.addGoalFor", { name: i.name }))}" aria-label="${esc(t("inventory.addGoalFor", { name: i.name }))}">+</button>
        </td>
      </tr>`;
    }).join("");
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
        goalType: "item",
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
  bindSparklines(results);
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
  const isSkill = goal.goal_type === "skill";
  const modeHint = goal.mode === "relative"
    ? `<span class="goal-mode-badge" title="${esc(t("goals.modeRelativeHint"))}">+${isSkill ? goal.target_qty : fmt(goal.target_qty)}</span>`
    : "";
  const typeBadge = isSkill ? `<span class="goal-type-badge">${esc(t("goals.typeSkill"))}</span> ` : "";
  const progressText = isSkill
    ? `${goal.current_qty} / ${goal.target_display}`
    : `${fmt(goal.current_qty)} / ${fmt(goal.target_display)}`;
  const eta = !done && goal.eta_snapshots
    ? `<div class="goal-eta">${esc(t("goals.etaSnapshots", { n: goal.eta_snapshots }))}</div>`
    : "";
  const missing = !done && goal.missing_qty > 0
    ? `<div class="goal-missing">${esc(t("goals.missing", { qty: isSkill ? goal.missing_qty : fmt(goal.missing_qty) }))}</div>`
    : "";
  const deleteBtn = `<button type="button" class="goal-delete-btn" data-goal-id="${goal.id}">${esc(t("goals.delete"))}</button>`;
  return `<tr>
    <td>${typeBadge}${esc(goal.item_name)}</td>
    <td>
      <div class="goal-progress-text">${progressText} ${modeHint}</div>
      <div class="progress-bar"><div class="progress-fill" style="width:${goal.progress_pct}%"></div></div>
      ${missing}${eta}
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
      if (res.ok) {
        trackEvent("Goal Delete");
        await loadGoals();
        const overviewRes = await fetch(`${apiBase()}/goals/overview`);
        if (overviewRes.ok) state.goalsOverview = await overviewRes.json();
      }
      renderGoals();
      if (state.data) {
        renderHeader(state.data);
        renderSkills(state.data);
        renderInventory(state.data);
      }
    });
  });

  panel.querySelectorAll(".goal-group-rename").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const name = prompt(t("goals.renameGroupPrompt"), btn.dataset.groupName);
      if (!name || !name.trim() || name.trim() === btn.dataset.groupName) return;
      const res = await fetch(`${apiBase()}/goal-groups/${btn.dataset.groupId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim() }),
      });
      if (res.ok) {
        trackEvent("Goal Group Rename");
        await loadGoals();
        const overviewRes = await fetch(`${apiBase()}/goals/overview`);
        if (overviewRes.ok) state.goalsOverview = await overviewRes.json();
      }
      renderGoals();
      if (state.data) renderHeader(state.data);
    });
  });

  panel.querySelectorAll(".goal-group-delete").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const name = btn.dataset.groupName;
      if (!confirm(t("goals.deleteGroupConfirm", { name }))) return;
      const res = await fetch(`${apiBase()}/goal-groups/${btn.dataset.groupId}`, { method: "DELETE" });
      if (res.ok) {
        trackEvent("Goal Group Delete");
        await loadGoals();
      }
      renderGoals();
    });
  });

  panel.querySelectorAll(".goal-clear-completed").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const ids = (btn.dataset.goalIds || "").split(",").filter(Boolean);
      for (const id of ids) {
        await fetch(`${apiBase()}/goals/${id}`, { method: "DELETE" });
      }
      if (ids.length) {
        trackEvent("Goals Clear Completed", { count: String(ids.length) });
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
    const missingGoals = goals.filter((goal) => !goal.completed_at && goal.missing_qty > 0);
    const missingSummary = missingGoals.length
      ? `<div class="goal-missing-summary">${missingGoals.map((goal) => {
          const qty = goal.goal_type === "skill" ? goal.missing_qty : fmt(goal.missing_qty);
          return `<span>${esc(goal.item_name)}: ${esc(t("goals.missingShort", { qty }))}</span>`;
        }).join(" · ")}</div>`
      : "";
    const headerActions = `
      ${completedIds.length ? `<button type="button" class="goal-clear-completed" data-goal-ids="${completedIds.join(",")}">${esc(t("goals.clearCompleted"))}</button>` : ""}
      <button type="button" class="goal-group-rename" data-group-id="${group.id}" data-group-name="${esc(group.name)}">${esc(t("goals.renameGroup"))}</button>
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
                ${missingSummary}
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

  const overview = state.goalsOverview;
  const overviewHtml = overview ? `
    <div class="goals-overview-kpi">
      <span class="goals-kpi-item"><strong>${overview.open}</strong> ${esc(t("goals.filterOpen"))}</span>
      <span class="goals-kpi-item"><strong>${overview.completed}</strong> ${esc(t("goals.filterDone"))}</span>
      <span class="goals-kpi-item"><strong>${overview.total}</strong> ${esc(t("goals.total"))}</span>
    </div>` : "";

  panel.innerHTML = `
    <div class="toolbar goals-toolbar">
      ${overviewHtml}
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
    trackEvent("Goal Group Create", { source: "goals_tab" });
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
  const item = state.goalModalItem;
  const isSkill = item?.goalType === "skill";
  document.getElementById("goal-modal-title").textContent = isSkill ? t("goals.modalTitleSkill") : t("goals.modalTitle");
  document.getElementById("goal-modal-mode-label").textContent = t("goals.mode");
  document.getElementById("goal-modal-mode").options[0].textContent = t("goals.modeAbsolute");
  document.getElementById("goal-modal-mode").options[1].textContent = t("goals.modeRelative");
  document.getElementById("goal-modal-qty-label").textContent = isSkill ? t("goals.targetLevel") : t("goals.targetQty");
  document.getElementById("goal-modal-group-label").textContent = t("goals.selectGroup");
  document.getElementById("goal-modal-new-group-label").textContent = t("goals.newGroupName");
  document.getElementById("goal-modal-cancel").textContent = t("goals.cancel");
  document.getElementById("goal-modal-submit").textContent = isSkill ? t("skills.addGoal") : t("inventory.addGoal");
}

async function openGoalModal(item) {
  state.goalModalItem = item;
  applyGoalModalI18n();
  const modal = document.getElementById("goal-modal");
  const errEl = document.getElementById("goal-modal-error");
  errEl.hidden = true;
  errEl.textContent = "";

  const isSkill = item.goalType === "skill";
  const currentVal = isSkill ? item.level : item.qty;
  const currentLabel = isSkill
    ? t("goals.currentLevel", { level: currentVal })
    : t("goals.currentQty", { qty: fmt(currentVal) });
  document.getElementById("goal-modal-item").textContent = `${item.name} — ${currentLabel}`;
  document.getElementById("goal-modal-qty").value = Math.max(currentVal + 1, 1);
  document.getElementById("goal-modal-mode").value = "absolute";
  document.getElementById("goal-modal-new-group").value = "";
  document.getElementById("goal-modal-new-group-wrap").hidden = true;

  const groups = await fetchGoalGroups();
  const sel = document.getElementById("goal-modal-group");
  sel.innerHTML = `
    <option value="">${esc(t("goals.noGroup"))}</option>
    ${groups.map((g) => `<option value="${g.id}">${esc(g.name)}</option>`).join("")}
    <option value="new">${esc(t("goals.newGroup"))}</option>`;

  modal.hidden = false;
  trackEvent("Goal Modal Open");
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
  const mode = document.getElementById("goal-modal-mode").value;
  const isSkill = item.goalType === "skill";
  if (!targetQty || targetQty <= 0) {
    errEl.textContent = t("goals.createFailed");
    errEl.hidden = false;
    return;
  }

  let groupId = null;
  let newGroupFromModal = false;
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
    newGroupFromModal = true;
  } else if (groupVal) {
    groupId = parseInt(groupVal, 10);
  }

  const body = isSkill
    ? { goal_type: "skill", skill_key: item.key, target_level: targetQty, group_id: groupId, mode }
    : { item_key: item.key, target_qty: targetQty, group_id: groupId, mode };

  const res = await fetch(`${apiBase()}/goals`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const result = await res.json();
  if (!res.ok) {
    errEl.textContent = result.error || t("goals.createFailed");
    errEl.hidden = false;
    return;
  }

  if (newGroupFromModal) {
    trackEvent("Goal Group Create", { source: "modal" });
  }
  trackEvent("Goal Create", {
    source: isSkill ? "skills" : "inventory",
    type: isSkill ? "skill" : "item",
    mode,
    group: newGroupFromModal ? "new" : groupId ? "existing" : "none",
    immediate: result.completed_at ? "true" : "false",
  });

  closeGoalModal();
  await loadGoals();
  const overviewRes = await fetch(`${apiBase()}/goals/overview`);
  if (overviewRes.ok) state.goalsOverview = await overviewRes.json();
  renderGoals();
  if (state.data) {
    renderHeader(state.data);
    renderSkills(state.data);
    renderInventory(state.data);
  }
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

  trackEvent("Goals Reached", {
    goals: String(completed.length),
    groups: String(groupsDone.length),
  });

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
  const recent = (d.recent_sessions || [])
    .map((s) => `<li><span>${esc(s.activity_display_name || s.activity_key)}</span><span>${esc(s.skill_name)}</span></li>`).join("");

  const active = (d.sessions || [])
    .map((s) => `<li><span>${esc(s.activity)}</span><span>${esc(s.skill)} · ${esc(s.completed ? t("combat.sessionDone") : t("combat.sessionRunning"))}</span></li>`).join("");

  const none = `<li>${esc(t("empty.none"))}</li>`;
  document.getElementById("tab-combat").innerHTML = `
    <div class="grid-2">
      <div class="card">
        <h3>${esc(t("combat.enemyKills"))}</h3>
        <div class="table-wrap" id="combat-kills-wrap">
          <table class="combat-table" id="combat-kills-table">
            <thead><tr>
              <th>${esc(t("combat.entry"))}</th>
              <th class="col-trend combat-trend-col" hidden>${esc(t("combat.trend"))}</th>
              <th>${esc(t("combat.kills"))}</th>
            </tr></thead>
            <tbody id="combat-kills-tbody"></tbody>
          </table>
        </div>
      </div>
      <div class="card">
        <h3>${esc(t("combat.dungeonRuns"))}</h3>
        <div class="table-wrap" id="combat-dungeons-wrap">
          <table class="combat-table" id="combat-dungeons-table">
            <thead><tr>
              <th>${esc(t("combat.entry"))}</th>
              <th class="col-trend combat-trend-col" hidden>${esc(t("combat.trend"))}</th>
              <th>${esc(t("combat.runsLabel"))}</th>
            </tr></thead>
            <tbody id="combat-dungeons-tbody"></tbody>
          </table>
        </div>
      </div>
      <div class="card"><h3>${esc(t("combat.recentActivity"))}</h3><ul class="list-compact">${recent || none}</ul></div>
      <div class="card"><h3>${esc(t("combat.activeSessions"))}</h3><ul class="list-compact">${active || none}</ul></div>
    </div>`;

  ensureCombatTimeline().then(() => renderCombatBody(d));
}

function renderCombatBody(d) {
  const showTrend = combatTrendEnabled();
  document.querySelectorAll("#tab-combat .combat-trend-col").forEach((el) => {
    el.hidden = !showTrend;
  });

  const kills = Object.entries(d.combat.enemy_kills || {})
    .sort((a, b) => b[1] - a[1]);
  const dungeons = Object.entries(d.combat.dungeon_runs || {})
    .sort((a, b) => b[1] - a[1]);

  const killsTbody = document.getElementById("combat-kills-tbody");
  if (killsTbody) {
    killsTbody.innerHTML = kills.length
      ? kills.map(([k, v]) => {
        const name = k.replace(/_/g, " ");
        return `<tr>
          <td>${esc(name)}</td>
          ${showTrend ? renderCombatSparkCell(k, "enemy", name) : ""}
          <td>${fmt(v)}</td>
        </tr>`;
      }).join("")
      : `<tr><td colspan="${showTrend ? 3 : 2}">${esc(t("empty.none"))}</td></tr>`;
    bindSparklines(killsTbody);
  }

  const dungeonsTbody = document.getElementById("combat-dungeons-tbody");
  if (dungeonsTbody) {
    dungeonsTbody.innerHTML = dungeons.length
      ? dungeons.map(([k, v]) => {
        const name = k.replace(/_/g, " ");
        return `<tr>
          <td>${esc(name)}</td>
          ${showTrend ? renderCombatSparkCell(k, "dungeon", name) : ""}
          <td>${esc(t("combat.runs", { count: fmt(v) }))}</td>
        </tr>`;
      }).join("")
      : `<tr><td colspan="${showTrend ? 3 : 2}">${esc(t("empty.none"))}</td></tr>`;
    bindSparklines(dungeonsTbody);
  }
}

async function ensureSkillTimeline() {
  if (state.skillTimeline) return state.skillTimeline;
  try {
    const res = await fetch(`${apiBase()}/skills/timeline`);
    state.skillTimeline = res.ok ? await res.json() : { snapshots: [], series: {} };
  } catch {
    state.skillTimeline = { snapshots: [], series: {} };
  }
  return state.skillTimeline;
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
  await ensureSkillTimeline();

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
      <h3>${esc(t("history.skillLevelChart"))}</h3>
      <div class="chart-wrap"><canvas id="chart-skills"></canvas></div>
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
          <th>${esc(t("goals.actions"))}</th>
        </tr></thead>
        <tbody>${state.snapshots.map((s) => `
          <tr>
            <td>${s.id}</td>
            <td>${esc(s.character_name || "—")}</td>
            <td>${fmt(s.coins)}</td>
            <td>${s.total_level}</td>
            <td>${formatTs(s.exported_at)}</td>
            <td>${esc(s.source_file)}</td>
            <td>
              <button type="button" class="snapshot-delete-btn" data-snapshot-id="${s.id}" ${state.snapshots.length <= 1 ? "disabled" : ""} title="${esc(t("history.deleteSnapshot"))}">${esc(t("history.delete"))}</button>
            </td>
          </tr>`).join("")}
        </tbody>
      </table>
    </div>`;

  renderTimelineCharts();
  document.getElementById("diff-older").addEventListener("change", (e) => { h.olderId = +e.target.value; });
  document.getElementById("diff-newer").addEventListener("change", (e) => { h.newerId = +e.target.value; });
  document.getElementById("diff-run").addEventListener("click", runDiff);
  panel.querySelectorAll(".snapshot-delete-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm(t("history.deleteSnapshotConfirm"))) return;
      const res = await fetch(`${apiBase()}/snapshots/${btn.dataset.snapshotId}`, { method: "DELETE" });
      if (!res.ok) {
        alert(t("history.deleteSnapshotFailed"));
        return;
      }
      trackEvent("Snapshot Delete");
      state.inventoryTimeline = null;
      state.skillTimeline = null;
      state.combatTimeline = null;
      await loadData();
      loadHistoryTab();
    });
  });
  if (h.olderId && h.newerId && h.olderId !== h.newerId) runDiff();
}

function option(s, selected) {
  const label = `#${s.id} · ${s.character_name || "?"} · ${formatTs(s.exported_at)}`;
  return `<option value="${s.id}" ${s.id === selected ? "selected" : ""}>${esc(label)}</option>`;
}

function renderTimelineCharts() {
  const tl = state.timeline;
  if (!tl.length) return;

  destroyChart("coins");
  destroyChart("level");
  destroyChart("skills");

  state.charts.coins = new Chart(document.getElementById("chart-coins"), {
    type: "line",
    data: {
      datasets: [{
        label: t("kpi.coins"),
        data: timelineChartPoints(tl, tl.map((s) => s.coins)),
        borderColor: "#6c8cff",
        tension: 0.3,
        fill: false,
      }],
    },
    options: chartOptsTime(tl),
  });
  state.charts.level = new Chart(document.getElementById("chart-level"), {
    type: "line",
    data: {
      datasets: [{
        label: t("kpi.totalLevel"),
        data: timelineChartPoints(tl, tl.map((s) => s.total_level)),
        borderColor: "#4ade80",
        tension: 0.3,
        fill: false,
      }],
    },
    options: chartOptsTime(tl),
  });

  const skillTl = state.skillTimeline;
  const skillCanvas = document.getElementById("chart-skills");
  if (!skillCanvas || !skillTl?.snapshots?.length) return;

  const skillEntries = pickTopSkillEntries(skillTl.series, 5);

  const colors = ["#6c8cff", "#4ade80", "#fbbf24", "#f87171", "#a78bfa"];
  const dashPatterns = [[], [6, 4], [2, 3], [8, 4, 2, 4], [4, 2]];
  const skillName = (key) => {
    const sk = state.data?.skills?.find((s) => s.key === key);
    return sk?.name || key.replace(/_/g, " ");
  };

  state.charts.skills = new Chart(skillCanvas, {
    type: "line",
    data: {
      datasets: skillEntries.map((entry, idx) => ({
        label: skillName(entry.key),
        data: skillTimelineChartPoints(skillTl.snapshots, entry.values),
        borderColor: colors[idx % colors.length],
        borderWidth: 2,
        borderDash: dashPatterns[idx % dashPatterns.length],
        pointRadius: 4,
        pointHoverRadius: 6,
        tension: 0,
        fill: false,
        spanGaps: false,
      })),
    },
    options: chartOptsTime(skillTl.snapshots),
  });
}

function normalizeTimeMs(ts) {
  const n = Number(ts);
  if (!Number.isFinite(n) || n <= 0) return null;
  return n < 1e12 ? n * 1000 : n;
}

function snapshotTimeMs(snapshot) {
  if (!snapshot) return null;
  const exported = normalizeTimeMs(snapshot.exported_at);
  if (exported != null) return exported;
  if (snapshot.imported_at) {
    const imported = Date.parse(snapshot.imported_at);
    if (Number.isFinite(imported)) return imported;
  }
  return null;
}

function skillLevelDelta(values) {
  const valid = values.filter((v) => v > 0);
  if (valid.length < 2) return 0;
  return Math.max(...valid) - Math.min(...valid);
}

function pickTopSkillEntries(series, limit = 5) {
  const ranked = Object.entries(series || {})
    .map(([key, values]) => ({
      key,
      values,
      latest: values[values.length - 1] || 0,
      delta: skillLevelDelta(values),
    }))
    .filter((e) => e.delta > 0)
    .sort((a, b) => b.delta - a.delta || b.latest - a.latest);

  const seen = new Set();
  const picked = [];
  for (const entry of ranked) {
    const sig = entry.values.join(",");
    if (seen.has(sig)) continue;
    seen.add(sig);
    picked.push(entry);
    if (picked.length >= limit) break;
  }
  return picked;
}

function skillTimelineChartPoints(snapshots, values) {
  return snapshots.map((snapshot, i) => {
    const x = snapshotTimeMs(snapshot);
    if (x == null) return null;
    const y = values[i];
    if (y == null || y <= 0) return null;
    return { x, y };
  }).filter(Boolean);
}

function timelineChartPoints(snapshots, values) {
  return snapshots.map((snapshot, i) => {
    const x = snapshotTimeMs(snapshot);
    if (x == null) return null;
    return { x, y: values[i] };
  }).filter(Boolean);
}

function chartTimeRange(snapshots) {
  const times = snapshots.map(snapshotTimeMs).filter((t) => t != null);
  if (!times.length) return {};
  const min = Math.min(...times);
  const max = Math.max(...times);
  if (min === max) {
    const pad = 60 * 60 * 1000;
    return { min: min - pad, max: max + pad };
  }
  return { min, max };
}

function formatChartAxisTs(ms, spanMs = 0) {
  if (!ms || !Number.isFinite(ms)) return "";
  const d = new Date(ms);
  const dayMs = 86400000;
  if (spanMs > 14 * dayMs) {
    return d.toLocaleString(I18n.localeTag(), { dateStyle: "short" });
  }
  if (spanMs > 2 * dayMs) {
    return d.toLocaleString(I18n.localeTag(), { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleString(I18n.localeTag(), { dateStyle: "short", timeStyle: "short" });
}

function chartOptsTime(snapshots) {
  const range = chartTimeRange(snapshots);
  const spanMs = (range.max ?? 0) - (range.min ?? 0);
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { labels: { color: "#8b92a8" } },
      tooltip: {
        callbacks: {
          title: (items) => {
            const x = items[0]?.parsed?.x;
            return x != null ? formatTs(x) : "";
          },
        },
      },
    },
    scales: {
      x: {
        type: "linear",
        ...range,
        ticks: {
          color: "#8b92a8",
          maxTicksLimit: 8,
          callback: (v) => formatChartAxisTs(v, spanMs),
        },
        grid: { color: "#2d3348" },
      },
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
    .sort((a, b) => {
      const aUp = a.new_level > a.old_level ? 1 : 0;
      const bUp = b.new_level > b.old_level ? 1 : 0;
      if (aUp !== bUp) return bUp - aUp;
      return b.xp_delta - a.xp_delta;
    })
    .slice(0, 20)
    .map((s) => {
      const levelUp = s.new_level > s.old_level;
      const levelDelta = s.new_level - s.old_level;
      const levelCell = levelUp
        ? `${s.old_level} → <span class="skill-level-up-level">${s.new_level}</span> <span class="skill-level-up-badge" title="${esc(t("history.levelUp"))}">+${levelDelta}</span>`
        : `${s.old_level} → ${s.new_level}`;
      return `
    <tr class="${levelUp ? "skill-change-level-up" : ""}">
      <td>${esc(s.name)}${levelUp ? ` <span class="skill-level-up-mark" title="${esc(t("history.levelUp"))}">⬆</span>` : ""}</td>
      <td class="skill-level-cell">${levelCell}</td>
      <td class="${s.xp_delta >= 0 ? "delta-pos" : "delta-neg"}">${s.xp_delta >= 0 ? "+" : ""}${fmt(s.xp_delta)} XP</td>
    </tr>`;
    }).join("");

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
  const ms = normalizeTimeMs(ts);
  if (ms == null) return "—";
  const d = new Date(ms);
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
