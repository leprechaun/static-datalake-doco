/* ── State ──────────────────────────────────────────────────────── */
let catalog = null;
let currentTable = null;
let catalogBase = "";

/* ── Boot ───────────────────────────────────────────────────────── */
async function init() {
  try {
    const params = new URLSearchParams(location.search);
    const catalogUrl = params.get("catalog") || "catalog.json";
    const catalogAbsolute = new URL(catalogUrl, location.href);
    catalogBase = catalogAbsolute.href.slice(0, catalogAbsolute.href.lastIndexOf("/") + 1);
    const res = await fetch(catalogAbsolute.href);
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
  const hash = location.hash.replace(/^#/, "");
  if (hash.startsWith("?filter=")) {
    showOverview(decodeURIComponent(hash.slice(8)));
  } else if (hash) {
    showTable(decodeURIComponent(hash));
  } else {
    showOverview();
  }
}

window.addEventListener("hashchange", () => {
  const hash = location.hash.replace(/^#/, "");
  if (hash.startsWith("?filter=")) {
    const filter = decodeURIComponent(hash.slice(8));
    if (currentTable === null) {
      const input = document.getElementById("index-filter");
      if (input) input.value = filter;
      renderIndexRows(filter);
    } else {
      showOverview(filter);
    }
  } else if (hash) {
    showTable(decodeURIComponent(hash));
  } else {
    showOverview();
  }
});

/* ── Overview ───────────────────────────────────────────────────── */
function showOverview(filter = "") {
  currentTable = null;
  document.getElementById("overview").style.display = "block";
  document.getElementById("detail").style.display = "none";
  document.getElementById("breadcrumb").textContent = "";
  document.getElementById("topbar").querySelector("h1").textContent = "Tables";

  const wrap = document.getElementById("overview");

  if (!catalog || catalog.tables.length === 0) {
    wrap.innerHTML = `<div class="empty-state"><h3>No tables found</h3><p>Run <code>datalake-doco generate</code> to scan your datalake.</p></div>`;
    return;
  }

  wrap.innerHTML = `
    <div class="index-filter-wrap">
      <input id="index-filter" type="search" placeholder="Filter tables…" autocomplete="off" value="${esc(filter)}">
    </div>
    <div class="index-table-wrap">
      <table class="index-table">
        <thead>
          <tr>
            <th>Table</th>
            <th class="num-col">Rows</th>
            <th class="num-col">Columns</th>
            <th>Last Refreshed</th>
          </tr>
        </thead>
        <tbody id="index-tbody"></tbody>
      </table>
    </div>
  `;

  renderIndexRows(filter);

  document.getElementById("index-filter").addEventListener("input", e => {
    const val = e.target.value;
    history.replaceState(null, "", val
      ? "#?filter=" + encodeURIComponent(val)
      : location.pathname + location.search
    );
    renderIndexRows(val);
  });
}

function renderIndexRows(filter) {
  const lower = (filter || "").toLowerCase();
  const tables = lower
    ? catalog.tables.filter(t => t.name.toLowerCase().includes(lower))
    : catalog.tables;

  const groups = {};
  for (const t of tables) {
    const parts = t.name.split("/");
    const source = parts[0] || "";
    const layer = parts.length > 2 ? parts.slice(1, -1).join("/") : (parts[1] || "");
    const leaf = parts[parts.length - 1];
    if (!groups[source]) groups[source] = {};
    if (!groups[source][layer]) groups[source][layer] = [];
    groups[source][layer].push({ entry: t, leaf });
  }

  const rows = [];
  for (const source of Object.keys(groups).sort()) {
    rows.push(
      `<tr class="group-source" data-source="${esc(source)}">` +
      `<td colspan="4"><span class="chevron">▾</span>${esc(source)}</td>` +
      `</tr>`
    );
    for (const layer of Object.keys(groups[source]).sort()) {
      rows.push(
        `<tr class="group-layer" data-source="${esc(source)}" data-layer="${esc(layer)}">` +
        `<td colspan="4"><span class="chevron">▾</span>${esc(layer)}</td>` +
        `</tr>`
      );
      for (const { entry, leaf } of groups[source][layer]) {
        const date = entry.generated_at ? entry.generated_at.slice(0, 10) : "—";
        rows.push(
          `<tr class="index-row" data-source="${esc(source)}" data-layer="${esc(layer)}" data-name="${esc(entry.name)}">` +
          `<td class="table-leaf">${esc(leaf)}</td>` +
          `<td class="num-col">${entry.row_count.toLocaleString()}</td>` +
          `<td class="num-col">${entry.column_count}</td>` +
          `<td class="date-col">${esc(date)}</td>` +
          `</tr>`
        );
      }
    }
  }

  const tbody = document.getElementById("index-tbody");
  if (!tbody) return;
  tbody.innerHTML = rows.join("");

  tbody.querySelectorAll(".group-source").forEach(srcRow => {
    srcRow.addEventListener("click", () => {
      const src = srcRow.dataset.source;
      const collapsed = srcRow.classList.toggle("collapsed");
      tbody.querySelectorAll(`.group-layer[data-source="${src}"]`).forEach(lr => {
        lr.hidden = collapsed;
      });
      tbody.querySelectorAll(`.index-row[data-source="${src}"]`).forEach(row => {
        if (collapsed) {
          row.hidden = true;
        } else {
          const lyr = row.dataset.layer;
          const lr = tbody.querySelector(`.group-layer[data-source="${src}"][data-layer="${lyr}"]`);
          row.hidden = lr ? lr.classList.contains("collapsed") : false;
        }
      });
    });
  });

  tbody.querySelectorAll(".group-layer").forEach(lyrRow => {
    lyrRow.addEventListener("click", e => {
      e.stopPropagation();
      const src = lyrRow.dataset.source;
      const lyr = lyrRow.dataset.layer;
      const collapsed = lyrRow.classList.toggle("collapsed");
      tbody.querySelectorAll(`.index-row[data-source="${src}"][data-layer="${lyr}"]`).forEach(row => {
        row.hidden = collapsed;
      });
    });
  });

  tbody.querySelectorAll(".index-row").forEach(row => {
    row.addEventListener("click", () => {
      location.hash = encodeURIComponent(row.dataset.name);
    });
  });
}

/* ── Detail view ────────────────────────────────────────────────── */
async function showTable(name) {
  const entry = catalog && catalog.tables.find(t => t.name === name);
  if (!entry) { showOverview(); return; }

  currentTable = name;
  document.getElementById("overview").style.display = "none";
  document.getElementById("detail").style.display = "block";
  document.getElementById("topbar").querySelector("h1").textContent = name.split("/").pop();
  document.getElementById("breadcrumb").innerHTML =
    `<span onclick="location.hash=''">Tables</span> / ${name}`;

  const detail = document.getElementById("detail");
  detail.innerHTML = `<div class="empty-state"><p>Loading…</p></div>`;

  let doc;
  try {
    const res = await fetch(catalogBase + entry.doc_path);
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
