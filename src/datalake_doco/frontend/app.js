/* ── State ──────────────────────────────────────────────────────── */
let catalog = null;
let currentTable = null;

/* ── Boot ───────────────────────────────────────────────────────── */
async function init() {
  try {
    const res = await fetch("catalog.json");
    if (!res.ok) throw new Error(res.statusText);
    catalog = await res.json();
  } catch (e) {
    document.getElementById("loading").innerHTML =
      `<strong>Could not load catalog.json</strong><br>
       Make sure you are serving this directory with a local HTTP server.<br>
       <code>python -m http.server 8000 --directory .</code>`;
    return;
  }

  document.getElementById("loading").style.display = "none";
  buildTree();
  const hash = location.hash.replace(/^#\/?/, "");
  if (hash) {
    showTable(decodeURIComponent(hash));
  } else {
    showOverview();
  }
}

window.addEventListener("hashchange", () => {
  const hash = location.hash.replace(/^#\/?/, "");
  if (hash) showTable(decodeURIComponent(hash));
  else showOverview();
});

/* ── Sidebar tree ───────────────────────────────────────────────── */
function buildTreeStructure(tables) {
  // Each node: { children: { segment: node }, tables: [entry, ...] }
  const root = { children: {}, tables: [] };
  for (const t of tables) {
    const parts = t.name.split("/");
    const folderParts = parts.slice(0, -1);
    let node = root;
    for (const part of folderParts) {
      if (!node.children[part]) node.children[part] = { children: {}, tables: [] };
      node = node.children[part];
    }
    node.tables.push(t);
  }
  return root;
}

function buildTree(filter = "") {
  const tree = document.getElementById("tree");
  tree.innerHTML = "";
  if (!catalog) return;

  const lower = filter.toLowerCase();
  const tables = catalog.tables.filter(
    t => !lower || t.name.toLowerCase().includes(lower)
  );

  tree.appendChild(renderTreeNode(buildTreeStructure(tables), 0));
}

function renderTreeNode(node, depth) {
  const frag = document.createDocumentFragment();
  const indent = 16 + depth * 14;

  for (const key of Object.keys(node.children).sort()) {
    const child = node.children[key];
    const group = document.createElement("div");
    group.className = "tree-group";

    const folderEl = document.createElement("div");
    folderEl.className = "tree-folder";
    folderEl.style.paddingLeft = `${indent}px`;
    folderEl.innerHTML = `<span class="chevron">▾</span>${key}`;
    folderEl.addEventListener("click", () => {
      group.classList.toggle("collapsed");
      folderEl.classList.toggle("collapsed");
    });

    const childrenEl = document.createElement("div");
    childrenEl.className = "tree-children";
    childrenEl.appendChild(renderTreeNode(child, depth + 1));

    group.appendChild(folderEl);
    group.appendChild(childrenEl);
    frag.appendChild(group);
  }

  for (const t of node.tables) {
    frag.appendChild(makeTreeItem(t, depth));
  }

  return frag;
}

function makeTreeItem(entry, depth = 0) {
  const el = document.createElement("div");
  el.className = "tree-item";
  el.dataset.name = entry.name;
  el.style.paddingLeft = `${28 + depth * 14}px`;
  el.textContent = entry.name.split("/").pop();
  el.title = entry.name;
  el.addEventListener("click", () => {
    location.hash = encodeURIComponent(entry.name);
  });
  return el;
}

function setActiveTreeItem(name) {
  document.querySelectorAll(".tree-item").forEach(el => {
    el.classList.toggle("active", el.dataset.name === name);
  });
}

/* ── Overview ───────────────────────────────────────────────────── */
function showOverview() {
  currentTable = null;
  document.getElementById("overview").style.display = "grid";
  document.getElementById("detail").style.display = "none";
  document.getElementById("breadcrumb").textContent = "";
  document.getElementById("topbar").querySelector("h1").textContent = "Tables";
  setActiveTreeItem(null);

  const grid = document.getElementById("overview");
  grid.innerHTML = "";

  if (!catalog || catalog.tables.length === 0) {
    grid.innerHTML = `<div class="empty-state"><h3>No tables found</h3><p>Run <code>datalake-doco generate</code> to scan your datalake.</p></div>`;
    return;
  }

  for (const entry of catalog.tables) {
    const card = document.createElement("div");
    card.className = "table-card";
    card.innerHTML = `
      <div class="card-name" title="${entry.name}">${entry.name}</div>
      <div class="card-meta">
        <span>${entry.row_count.toLocaleString()} rows</span>
        <span>${entry.column_count} columns</span>
        <span class="badge">delta</span>
      </div>
    `;
    card.addEventListener("click", () => {
      location.hash = encodeURIComponent(entry.name);
    });
    grid.appendChild(card);
  }
}

/* ── Detail view ────────────────────────────────────────────────── */
async function showTable(name) {
  const entry = catalog && catalog.tables.find(t => t.name === name);
  if (!entry) { showOverview(); return; }

  currentTable = name;
  setActiveTreeItem(name);
  document.getElementById("overview").style.display = "none";
  document.getElementById("detail").style.display = "block";
  document.getElementById("topbar").querySelector("h1").textContent = name.split("/").pop();
  document.getElementById("breadcrumb").innerHTML =
    `<span onclick="location.hash=''">Tables</span> / ${name}`;

  const detail = document.getElementById("detail");
  detail.innerHTML = `<div class="empty-state"><p>Loading…</p></div>`;

  let doc;
  try {
    const res = await fetch(entry.doc_path);
    if (!res.ok) throw new Error(res.statusText);
    doc = await res.json();
  } catch (e) {
    detail.innerHTML = `<div class="empty-state"><h3>Could not load table data</h3><p>${e.message}</p></div>`;
    return;
  }

  detail.innerHTML = renderDetail(doc);
  activateTab(detail.querySelector(".tab"));
}

function renderDetail(doc) {
  const ts = doc.generated_at;
  const hasSamples = doc.sample_data && doc.sample_data.length > 0;
  const hasHistory = doc.history && doc.history.length > 0;

  return `
    <div class="detail-header">
      <div class="detail-title">${doc.name}</div>
      <div class="detail-meta">
        <span>${doc.row_count.toLocaleString()} rows</span>
        <span>${doc.schema.length} columns</span>
        <span class="badge">${doc.format}</span>
        <span>Generated ${ts}</span>
        <span title="${doc.uri}" style="max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${doc.uri}</span>
      </div>
    </div>

    <div class="tabs">
      <div class="tab" data-panel="schema">Schema</div>
      <div class="tab" data-panel="stats">Statistics</div>
      ${hasSamples ? `<div class="tab" data-panel="sample-data">Sample Data</div>` : ""}
      ${hasHistory ? `<div class="tab" data-panel="history">History</div>` : ""}
    </div>

    <div class="tab-panel" id="panel-schema">${renderSchema(doc)}</div>
    <div class="tab-panel" id="panel-stats">${renderStats(doc)}</div>
    ${hasSamples ? `<div class="tab-panel" id="panel-sample-data">${renderSampleData(doc)}</div>` : ""}
    ${hasHistory ? `<div class="tab-panel" id="panel-history">${renderHistory(doc)}</div>` : ""}
  `;
}

function activateTab(tabEl) {
  if (!tabEl) return;
  const container = tabEl.closest("#detail");
  container.querySelectorAll(".tab").forEach(t => {
    t.classList.remove("active");
    t.addEventListener("click", () => activateTab(t));
  });
  container.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
  tabEl.classList.add("active");
  const panel = container.querySelector(`#panel-${tabEl.dataset.panel}`);
  if (panel) panel.classList.add("active");
}

/* ── Schema tab ─────────────────────────────────────────────────── */
function renderSchema(doc) {
  const rows = doc.schema.map(col => `
    <tr>
      <td>${esc(col.name)}</td>
      <td><span class="type-badge">${esc(col.type)}</span></td>
      <td>${col.nullable ? "" : '<span style="color:#dc3545">✗</span>'}</td>
    </tr>
  `).join("");

  return `<div class="data-table-wrap">
    <table>
      <thead><tr><th>Column</th><th>Type</th><th>Nullable</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  </div>`;
}

/* ── Stats tab ──────────────────────────────────────────────────── */
function renderStats(doc) {
  const cols = doc.schema.map(c => c.name);

  // Determine which stat keys are present across any column
  const numericKeys = ["count","mean","std","min","p25","p50","p75","max"];
  const catKeys = ["count","unique","top","freq"];

  const hasNumeric = cols.some(c => doc.statistics[c]?.mean != null);
  const hasCat = cols.some(c => doc.statistics[c]?.unique != null);

  const headerKeys = hasNumeric
    ? numericKeys
    : (hasCat ? catKeys : ["count"]);

  const headerLabels = {
    count: "count", mean: "mean", std: "std dev",
    min: "min", p25: "25%", p50: "50%", p75: "75%", max: "max",
    unique: "unique", top: "top", freq: "freq"
  };

  const headers = ["column", ...headerKeys].map(k =>
    `<th>${headerLabels[k] ?? k}</th>`
  ).join("");

  const rows = cols.map(col => {
    const s = doc.statistics[col] || {};
    const cells = headerKeys.map(k => {
      const v = s[k];
      if (v === null || v === undefined) return `<td class="null-cell">—</td>`;
      if (typeof v === "number") return `<td>${fmt(v)}</td>`;
      return `<td>${esc(String(v))}</td>`;
    }).join("");
    return `<tr><td><strong>${esc(col)}</strong></td>${cells}</tr>`;
  }).join("");

  return `<div class="data-table-wrap">
    <table>
      <thead><tr>${headers}</tr></thead>
      <tbody>${rows}</tbody>
    </table>
  </div>`;
}

/* ── Sample Data tab ────────────────────────────────────────────── */
function renderSampleData(doc) {
  if (!doc.sample_data || doc.sample_data.length === 0) return "";
  const cols = doc.schema.map(c => c.name);
  const headers = cols.map(c => `<th>${esc(c)}</th>`).join("");
  const rows = doc.sample_data.map(row => {
    const cells = cols.map(c => {
      const v = row[c];
      if (v === null || v === undefined) return `<td class="null-cell">null</td>`;
      return `<td>${esc(String(v))}</td>`;
    }).join("");
    return `<tr>${cells}</tr>`;
  }).join("");

  return `<div class="data-table-wrap">
    <table>
      <thead><tr>${headers}</tr></thead>
      <tbody>${rows}</tbody>
    </table>
  </div>`;
}

/* ── History tab ────────────────────────────────────────────────── */
function renderHistory(doc) {
  if (!doc.history || doc.history.length === 0) return "";

  const rows = doc.history.map(h => {
    const params = Object.keys(h.parameters).length
      ? Object.entries(h.parameters)
          .map(([k, v]) => `<span class="param-key">${esc(k)}</span> ${esc(String(v))}`)
          .join("<br>")
      : "";

    return `<tr>
      <td style="text-align:right">${h.version}</td>
      <td>${esc(h.timestamp)}</td>
      <td><span class="type-badge">${esc(h.operation)}</span></td>
      <td>${h.description ? esc(h.description) : '<span class="null-cell">—</span>'}</td>
      <td style="font-size:12px;color:var(--muted)">${params}</td>
      <td style="font-size:12px;color:var(--muted)">${h.engine_info ? esc(h.engine_info) : ""}</td>
    </tr>`;
  }).join("");

  return `<div class="data-table-wrap">
    <table>
      <thead>
        <tr>
          <th>Version</th>
          <th>Timestamp</th>
          <th>Operation</th>
          <th>Description</th>
          <th>Parameters</th>
          <th>Engine</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  </div>`;
}

/* ── Search ─────────────────────────────────────────────────────── */
document.getElementById("search").addEventListener("input", e => {
  buildTree(e.target.value);
});

/* ── Helpers ────────────────────────────────────────────────────── */
function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fmt(n) {
  if (n === null || n === undefined) return "—";
  if (Number.isInteger(n)) return n.toLocaleString();
  return n.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

init();
