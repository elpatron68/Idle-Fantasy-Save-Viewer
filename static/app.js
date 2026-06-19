/* Idle Fantasy Save Viewer – client UI */

let state = {
  data: null,
  snapshots: [],
  timeline: [],
  inventory: { search: "", categories: new Set(), sort: "category", highlightEquipped: false },
  skills: { search: "", sort: "level", sortAsc: false },
  quests: { tab: "story", filter: "all" },
  history: { olderId: null, newerId: null, diff: null },
  charts: {},
};

const CATEGORY_ORDER = [
  "Currency", "Ores & Mining", "Bars & Smithing", "Wood & Planks", "Runes",
  "Raw Food", "Cooked Food", "Seeds & Farming", "Melee Weapons", "Ranged",
  "Magic", "Armor", "Bones & Hides", "Gems & Jewelry", "Potions & Brews", "Misc",
];

document.addEventListener("DOMContentLoaded", init);

async function init() {
  setupNav();
  setupUpload();
  await loadData();
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
    const res = await fetch("/api/import", { method: "POST", body: fd });
    const result = await res.json();
    if (result.imported || result.snapshot_id) {
      await loadData();
      alert(result.imported ? `Importiert: Snapshot #${result.snapshot_id}` : "Backup bereits vorhanden (Duplikat).");
    } else {
      alert(result.error || "Import fehlgeschlagen");
    }
    e.target.value = "";
  });
}

async function loadData() {
  try {
    const res = await fetch("/api/snapshot/latest");
    if (!res.ok) {
      showEmpty("Kein Save importiert. Starte mit: python app.py fantasyidler_save.json");
      return;
    }
    state.data = await res.json();
    renderAll();
  } catch (err) {
    showEmpty(`Fehler beim Laden: ${err.message}`);
  }
}

function showEmpty(msg) {
  document.getElementById("character-header").innerHTML = `<span class="loading">${esc(msg)}</span>`;
}

function renderAll() {
  const d = state.data;
  if (!d) return;

  renderHeader(d);
  renderOverview(d);
  renderSkills(d);
  renderInventory(d);
  renderEquipment(d);
  renderQuests(d);
  renderCombat(d);
}

function renderHeader(d) {
  const c = d.character;
  const m = d.meta;
  document.getElementById("character-header").innerHTML = `
    <h2>${esc(c.name || "Unbekannt")}</h2>
    <div class="character-meta">
      ${esc(c.race || "")} · ${esc(c.gender || "")} · Export: ${formatTs(m.exported_at)}
    </div>`;

  document.getElementById("kpi-row").innerHTML = `
    <div class="kpi"><div class="kpi-label">Coins</div><div class="kpi-value">${fmt(m.coins)}</div></div>
    <div class="kpi"><div class="kpi-label">Gesamt-Level</div><div class="kpi-value">${m.total_level}</div></div>
    <div class="kpi"><div class="kpi-label">Items</div><div class="kpi-value">${m.item_count}</div></div>
    <div class="kpi"><div class="kpi-label">Stückzahl</div><div class="kpi-value">${fmt(m.total_items)}</div></div>`;
}

function renderOverview(d) {
  const c = d.character;
  const queue = (d.session_queue || []).map((q) =>
    `<li><span>${esc(q.skill_display_name || q.skill_name)}</span><span>${esc(q.activity_key || "—")} · ${q.qty || 0}</span></li>`
  ).join("");

  const slayer = d.combat.slayer_task;
  const slayerHtml = slayer
    ? `<p><strong>${esc(slayer.display_name)}</strong>: ${slayer.kills_completed}/${slayer.target_kills} (${d.combat.slayer_points} Punkte)</p>`
    : "<p class='empty-state'>Kein Slayer-Task aktiv</p>";

  const pets = (d.pets || []).map((p) =>
    `<li><span>${esc(p.id.replace(/_/g, " "))}</span><span>+${p.boost_percent}%</span></li>`
  ).join("");

  const farming = (d.farming || []).map((p) =>
    `<li><span>Feld ${p.patchNumber}</span><span>${esc(p.cropType || "—")}</span></li>`
  ).join("");

  document.getElementById("tab-overview").innerHTML = `
    <div class="grid-2">
      <div class="card">
        <h3>Charakter</h3>
        <ul class="list-compact">
          <li><span>HP</span><span>${c.hp ?? "—"}</span></li>
          <li><span>Aktiver Trank</span><span>${esc(c.active_potion || "—")}</span></li>
          <li><span>Aktiver Zauber</span><span>${esc(c.active_spell || "—")}</span></li>
          <li><span>Waffen-Slot</span><span>${esc(c.active_weapon_slot || "—")}</span></li>
          <li><span>Segen</span><span>${esc(c.active_blessing || "—")}</span></li>
        </ul>
      </div>
      <div class="card">
        <h3>Session-Queue</h3>
        <ul class="list-compact">${queue || "<li><span>Leer</span></li>"}</ul>
      </div>
      <div class="card">
        <h3>Slayer</h3>
        ${slayerHtml}
      </div>
      <div class="card">
        <h3>Pets</h3>
        <ul class="list-compact">${pets || "<li><span>Keine</span></li>"}</ul>
      </div>
      <div class="card">
        <h3>Farming</h3>
        <ul class="list-compact">${farming || "<li><span>Keine Felder</span></li>"}</ul>
      </div>
      <div class="card">
        <h3>Gilden-Ruf</h3>
        <ul class="list-compact">${Object.entries(d.guild_reputation || {}).map(([k, v]) =>
          `<li><span>${esc(k)}</span><span>${fmt(v)}</span></li>`).join("")}</ul>
      </div>
    </div>`;
}

function renderSkills(d) {
  const panel = document.getElementById("tab-skills");
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

  panel.innerHTML = `
    <div class="toolbar">
      <input class="search-input" id="skill-search" placeholder="Skill suchen…" value="${esc(s.search)}">
      <select class="select-input" id="skill-sort">
        <option value="level" ${s.sort === "level" ? "selected" : ""}>Nach Level</option>
        <option value="xp" ${s.sort === "xp" ? "selected" : ""}>Nach XP</option>
        <option value="name" ${s.sort === "name" ? "selected" : ""}>Nach Name</option>
      </select>
    </div>
    <div class="card">
      <table>
        <thead><tr>
          <th data-sort="name">Skill</th>
          <th data-sort="level">Level</th>
          <th data-sort="xp">XP</th>
          <th>Fortschritt</th>
        </tr></thead>
        <tbody>${items.map((sk) => `
          <tr>
            <td>${esc(sk.name)}</td>
            <td>${sk.level}</td>
            <td>${fmt(sk.xp)}</td>
            <td style="min-width:140px">
              ${sk.progress_pct}%
              <div class="progress-bar"><div class="progress-fill" style="width:${sk.progress_pct}%"></div></div>
            </td>
          </tr>`).join("")}
        </tbody>
      </table>
    </div>`;

  document.getElementById("skill-search").addEventListener("input", (e) => {
    state.skills.search = e.target.value;
    renderSkills(state.data);
  });
  document.getElementById("skill-sort").addEventListener("change", (e) => {
    state.skills.sort = e.target.value;
    renderSkills(state.data);
  });
  panel.querySelectorAll("th[data-sort]").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (state.skills.sort === key) state.skills.sortAsc = !state.skills.sortAsc;
      else { state.skills.sort = key; state.skills.sortAsc = false; }
      renderSkills(state.data);
    });
  });
}

function renderInventory(d) {
  const panel = document.getElementById("tab-inventory");
  const inv = state.inventory;
  const categories = [...new Set(d.inventory.map((i) => i.category))].sort(
    (a, b) => CATEGORY_ORDER.indexOf(a) - CATEGORY_ORDER.indexOf(b)
  );

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

  const grouped = {};
  for (const item of items) {
    if (!grouped[item.category]) grouped[item.category] = [];
    grouped[item.category].push(item);
  }

  const groupRows = Object.entries(grouped).map(([cat, catItems]) => {
    const totalQty = catItems.reduce((s, i) => s + i.qty, 0);
    const header = `
      <tr class="inv-group-row" data-group="${esc(cat)}">
        <td colspan="3">
          <button type="button" class="inv-group-toggle" data-group="${esc(cat)}" aria-expanded="true">
            <span class="inv-group-title">${esc(cat)}</span>
            <span class="inv-group-meta">${catItems.length} Items · ${fmt(totalQty)} Stück</span>
          </button>
        </td>
      </tr>`;
    const rows = catItems.map((i) => `
      <tr class="inv-item-row ${i.equipped && inv.highlightEquipped ? "item-equipped" : ""}" data-group="${esc(cat)}">
        <td class="col-name">${esc(i.name)}${i.equipped ? '<span class="equipped-mark" title="Ausgerüstet">⚡</span>' : ""}</td>
        <td class="col-qty">${fmt(i.qty)}</td>
        <td class="col-key"><code>${esc(i.key)}</code></td>
      </tr>`).join("");
    return header + rows;
  }).join("");

  const tableHtml = groupRows ? `
    <div class="inv-table-wrap">
      <table class="inv-table">
        <colgroup>
          <col class="col-name">
          <col class="col-qty">
          <col class="col-key">
        </colgroup>
        <thead>
          <tr>
            <th class="col-name">Item</th>
            <th class="col-qty">Menge</th>
            <th class="col-key">ID</th>
          </tr>
        </thead>
        <tbody>${groupRows}</tbody>
      </table>
    </div>` : "<p class='empty-state'>Keine Items gefunden</p>";

  panel.innerHTML = `
    <div class="toolbar">
      <input class="search-input" id="inv-search" placeholder="Item suchen…" value="${esc(inv.search)}">
      <select class="select-input" id="inv-sort">
        <option value="category" ${inv.sort === "category" ? "selected" : ""}>Nach Kategorie</option>
        <option value="name" ${inv.sort === "name" ? "selected" : ""}>Nach Name</option>
        <option value="qty" ${inv.sort === "qty" ? "selected" : ""}>Nach Menge</option>
      </select>
      <label class="toggle-label">
        <input type="checkbox" id="inv-equipped" ${inv.highlightEquipped ? "checked" : ""}>
        Ausgerüstet hervorheben
      </label>
    </div>
    <div class="chip-row" id="inv-chips">
      ${categories.map((c) => `
        <span class="chip ${inv.categories.has(c) ? "active" : ""}" data-cat="${esc(c)}">${esc(c)}</span>`).join("")}
    </div>
    <div class="card inv-card">
      ${tableHtml}
    </div>`;

  document.getElementById("inv-search").addEventListener("input", (e) => {
    state.inventory.search = e.target.value;
    renderInventory(state.data);
  });
  document.getElementById("inv-sort").addEventListener("change", (e) => {
    state.inventory.sort = e.target.value;
    renderInventory(state.data);
  });
  document.getElementById("inv-equipped").addEventListener("change", (e) => {
    state.inventory.highlightEquipped = e.target.checked;
    renderInventory(state.data);
  });
  panel.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const cat = chip.dataset.cat;
      if (state.inventory.categories.has(cat)) state.inventory.categories.delete(cat);
      else state.inventory.categories.add(cat);
      renderInventory(state.data);
    });
  });
  panel.querySelectorAll(".inv-group-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const group = btn.dataset.group;
      const expanded = btn.getAttribute("aria-expanded") === "true";
      btn.setAttribute("aria-expanded", expanded ? "false" : "true");
      panel.querySelectorAll(`.inv-item-row[data-group="${group}"]`).forEach((row) => {
        row.classList.toggle("collapsed", expanded);
      });
    });
  });
}

function renderEquipment(d) {
  document.getElementById("tab-equipment").innerHTML = `
    <div class="card">
      <h3>Ausrüstung</h3>
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
    { key: "story", label: "Story" },
    { key: "daily", label: "Daily" },
    { key: "weekly", label: "Weekly" },
    { key: "guild", label: "Gilde" },
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
      ${tabs.map((t) => `<button class="quest-tab ${q.tab === t.key ? "active" : ""}" data-tab="${t.key}">${t.label}</button>`).join("")}
    </div>
    <div class="toolbar">
      <select class="select-input" id="quest-filter">
        <option value="all" ${q.filter === "all" ? "selected" : ""}>Alle</option>
        <option value="open" ${q.filter === "open" ? "selected" : ""}>Offen</option>
        <option value="done" ${q.filter === "done" ? "selected" : ""}>Abgeschlossen</option>
      </select>
    </div>
    <div class="card">
      <table>
        <thead><tr>
          <th>Quest</th>
          <th>Fortschritt</th>
          <th>Status</th>
        </tr></thead>
        <tbody>${items.map((quest) => {
          const done = isStory ? quest.completed : quest.claimed;
          return `<tr>
            <td>${esc(quest.name)}</td>
            <td>${fmt(quest.progress)}</td>
            <td><span class="badge ${done ? "badge-success" : "badge-warning"}">${done ? "Erledigt" : "Offen"}</span></td>
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
    .map(([k, v]) => `<li><span>${esc(k.replace(/_/g, " "))}</span><span>${fmt(v)} Runs</span></li>`).join("");

  const recent = (d.recent_sessions || [])
    .map((s) => `<li><span>${esc(s.activity_display_name || s.activity_key)}</span><span>${esc(s.skill_name)}</span></li>`).join("");

  const active = (d.sessions || [])
    .map((s) => `<li><span>${esc(s.activity)}</span><span>${esc(s.skill)} · ${s.completed ? "fertig" : "läuft"}</span></li>`).join("");

  document.getElementById("tab-combat").innerHTML = `
    <div class="grid-2">
      <div class="card"><h3>Feind-Kills</h3><ul class="list-compact">${kills || "<li>Keine</li>"}</ul></div>
      <div class="card"><h3>Dungeon-Runs</h3><ul class="list-compact">${dungeons || "<li>Keine</li>"}</ul></div>
      <div class="card"><h3>Letzte Aktivitäten</h3><ul class="list-compact">${recent || "<li>Keine</li>"}</ul></div>
      <div class="card"><h3>Aktive Sessions</h3><ul class="list-compact">${active || "<li>Keine</li>"}</ul></div>
    </div>`;
}

async function loadHistoryTab() {
  const panel = document.getElementById("tab-history");
  panel.innerHTML = "<p class='loading'>Lade Verlauf…</p>";

  const [snapRes, tlRes] = await Promise.all([
    fetch("/api/snapshots"),
    fetch("/api/timeline"),
  ]);
  state.snapshots = await snapRes.json();
  state.timeline = await tlRes.json();

  if (state.snapshots.length === 0) {
    panel.innerHTML = "<p class='empty-state'>Noch keine Snapshots. Importiere ein Backup.</p>";
    return;
  }

  const h = state.history;
  if (!h.newerId) h.newerId = state.snapshots[0].id;
  if (!h.olderId && state.snapshots.length > 1) h.olderId = state.snapshots[1].id;

  panel.innerHTML = `
    <div class="grid-2">
      <div class="card">
        <h3>Coins-Verlauf</h3>
        <div class="chart-wrap"><canvas id="chart-coins"></canvas></div>
      </div>
      <div class="card">
        <h3>Gesamt-Level-Verlauf</h3>
        <div class="chart-wrap"><canvas id="chart-level"></canvas></div>
      </div>
    </div>
    <div class="card">
      <h3>Snapshot-Vergleich</h3>
      <div class="toolbar">
        <select class="select-input" id="diff-older">
          ${state.snapshots.map((s) => option(s, h.olderId)).join("")}
        </select>
        <span>→</span>
        <select class="select-input" id="diff-newer">
          ${state.snapshots.map((s) => option(s, h.newerId)).join("")}
        </select>
        <button class="select-input" id="diff-run" style="background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600">Vergleichen</button>
      </div>
      <div id="diff-result"></div>
    </div>
    <div class="card">
      <h3>Alle Snapshots</h3>
      <table>
        <thead><tr><th>ID</th><th>Charakter</th><th>Coins</th><th>Level</th><th>Export</th><th>Datei</th></tr></thead>
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
    data: { labels, datasets: [{ label: "Coins", data: coins, borderColor: "#6c8cff", tension: 0.3, fill: false }] },
    options: chartOpts(),
  });
  state.charts.level = new Chart(document.getElementById("chart-level"), {
    type: "line",
    data: { labels, datasets: [{ label: "Gesamt-Level", data: levels, borderColor: "#4ade80", tension: 0.3, fill: false }] },
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
    el.innerHTML = "<p class='empty-state'>Wähle zwei verschiedene Snapshots.</p>";
    return;
  }
  const older = Math.min(h.olderId, h.newerId);
  const newer = Math.max(h.olderId, h.newerId);
  const res = await fetch(`/api/snapshots/${older}/diff/${newer}`);
  const diff = await res.json();
  if (diff.error) {
    el.innerHTML = `<p class='empty-state'>${esc(diff.error)}</p>`;
    return;
  }

  const coinDelta = diff.summary.coins_delta;
  const coinCls = coinDelta >= 0 ? "delta-pos" : "delta-neg";

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

  el.innerHTML = `
    <p>Coins: <span class="${coinCls}">${coinDelta >= 0 ? "+" : ""}${fmt(coinDelta)}</span>
       · Gesamt-Level: ${diff.summary.total_level_delta >= 0 ? "+" : ""}${diff.summary.total_level_delta}</p>
    <h4 style="margin-top:16px">Inventar-Änderungen (${diff.inventory_changes.length})</h4>
    <table><thead><tr><th>Item</th><th>Menge</th><th>Delta</th></tr></thead>
    <tbody>${invRows || "<tr><td colspan='3'>Keine Änderungen</td></tr>"}</tbody></table>
    <h4 style="margin-top:16px">Skill-Änderungen (${diff.skill_changes.length})</h4>
    <table><thead><tr><th>Skill</th><th>Level</th><th>XP-Delta</th></tr></thead>
    <tbody>${skRows || "<tr><td colspan='3'>Keine Änderungen</td></tr>"}</tbody></table>`;
}

function fmt(n) {
  if (n == null) return "—";
  return Number(n).toLocaleString("de-DE");
}

function formatTs(ts) {
  if (!ts) return "—";
  const d = new Date(Number(ts));
  return d.toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" });
}

function esc(s) {
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
