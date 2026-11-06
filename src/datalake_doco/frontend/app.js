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
    const { table, tab } = parseHash(hash);
    showTable(table, tab);
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
    const { table, tab } = parseHash(hash);
    showTable(table, tab);
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

  const totalRows = catalog.tables.reduce((s, t) => s + (t.rowCount || 0), 0);
  const totalCols = catalog.tables.reduce((s, t) => s + (t.columnCount || 0), 0);
  const generatedAt = catalog.generatedAt ? fmtDateTime(catalog.generatedAt) : "";
  const summary = [
    catalog.tables.length.toLocaleString() + " tables",
    totalRows.toLocaleString() + " rows",
    totalCols.toLocaleString() + " columns",
    generatedAt ? "Last refreshed " + generatedAt : "",
  ].filter(Boolean).join(" · ");

  wrap.innerHTML = `
    <div class="index-filter-wrap">
      <input id="index-filter" type="search" placeholder="Filter tables…" autocomplete="off" value="${esc(filter)}">
      <span class="catalog-generated-at">${summary}</span>
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
    ? catalog.tables.filter(t =>
        t.fullyQualifiedName.toLowerCase().includes(lower) ||
        (t.description || "").toLowerCase().includes(lower))
    : catalog.tables;

  const groups = {};
  for (const t of tables) {
    const parts = t.fullyQualifiedName.split(".");
    const source = parts[0] || "";
    const layer = parts.length > 2 ? parts.slice(1, -1).join(".") : (parts[1] || "");
    const leaf = parts[parts.length - 1];
    if (!groups[source]) groups[source] = {};
    if (!groups[source][layer]) groups[source][layer] = [];
    groups[source][layer].push({ entry: t, leaf });
  }

  const rows = [];
  for (const source of Object.keys(groups).sort()) {
    const srcEntries = Object.values(groups[source]).flat();
    const { rows: srcRows, cols: srcCols, maxDate: srcMax } = groupStats(srcEntries);
    rows.push(
      `<tr class="group-source" data-source="${esc(source)}">` +
      `<td><span class="chevron">▾</span>${esc(source)}</td>` +
      `<td class="num-col">${srcRows.toLocaleString()}</td>` +
      `<td class="num-col">${srcCols.toLocaleString()}</td>` +
      `<td class="date-col">${srcMax ? fmtDateTime(srcMax) : "—"}</td>` +
      `</tr>`
    );
    for (const layer of Object.keys(groups[source]).sort()) {
      const lyrEntries = groups[source][layer];
      const { rows: lyrRows, cols: lyrCols, maxDate: lyrMax } = groupStats(lyrEntries);
      rows.push(
        `<tr class="group-layer" data-source="${esc(source)}" data-layer="${esc(layer)}">` +
        `<td><span class="chevron">▾</span>${esc(layer)}</td>` +
        `<td class="num-col">${lyrRows.toLocaleString()}</td>` +
        `<td class="num-col">${lyrCols.toLocaleString()}</td>` +
        `<td class="date-col">${lyrMax ? fmtDateTime(lyrMax) : "—"}</td>` +
        `</tr>`
      );
      for (const { entry, leaf } of lyrEntries) {
        const date = entry.updatedAt ? fmtDateTime(entry.updatedAt) : "—";
        rows.push(
          `<tr class="index-row" data-source="${esc(source)}" data-layer="${esc(layer)}" data-name="${esc(entry.fullyQualifiedName)}">` +
          `<td class="table-leaf">${esc(leaf)}${entry.description ? `<div class="table-description" title="${esc(entry.description)}">${esc(entry.description)}</div>` : ""}</td>` +
          `<td class="num-col">${entry.rowCount.toLocaleString()}</td>` +
          `<td class="num-col">${entry.columnCount}</td>` +
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
async function showTable(name, tab = null) {
  const entry = catalog && catalog.tables.find(t => t.fullyQualifiedName === name);
  if (!entry) { showOverview(); return; }

  currentTable = name;
  document.getElementById("overview").style.display = "none";
  document.getElementById("detail").style.display = "block";
  document.getElementById("topbar").querySelector("h1").textContent = name.split(".").pop();
  document.getElementById("breadcrumb").innerHTML =
    `<span onclick="location.hash=''">Tables</span> / ${name}`;

  const detail = document.getElementById("detail");
  detail.innerHTML = `<div class="empty-state"><p>Loading…</p></div>`;

  let doc;
  try {
    const res = await fetch(catalogBase + entry.docPath);
    if (!res.ok) throw new Error(res.statusText);
    doc = await res.json();
  } catch (e) {
    detail.innerHTML = `<div class="empty-state"><h3>Could not load table data</h3><p>${e.message}</p></div>`;
    return;
  }

  detail.innerHTML = renderDetail(doc);
  const tabEl = (tab && detail.querySelector(`.tab[data-panel="${tab}"]`)) || detail.querySelector(".tab");
  activateTab(tabEl);
}

function renderDetail(doc) {
  const ts = doc.updatedAt;
  const rowCount = doc.tableProfile?.rowCount;
  const colCount = doc.columns?.length ?? 0;
  const hasSamples = doc.sampleData?.rows?.length > 0;
  const hasHistory = doc.extension?.deltaHistory?.length > 0;
  const hasTime = (doc.tableProfile?.columnProfile || []).some(p => p.distribution);

  return `
    <div class="detail-header">
      <div class="detail-title">${doc.fullyQualifiedName ?? doc.name}</div>
      ${doc.description ? `<div class="detail-description">${esc(doc.description)}</div>` : ""}
      <div class="detail-meta">
        ${rowCount != null ? `<span>${rowCount.toLocaleString()} rows</span>` : ""}
        <span>${colCount} columns</span>
        ${doc.commitCount != null ? `<span>${doc.commitCount.toLocaleString()} commits</span>` : ""}
        <span>Updated ${ts}</span>
        ${freshnessText(doc.freshness) ? `<span>${freshnessText(doc.freshness)}</span>` : ""}
        ${doc.uri ? `<span title="${doc.uri}" style="max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${doc.uri}</span>` : ""}
      </div>
    </div>

    <div class="tabs">
      <div class="tab" data-panel="schema">Schema</div>
      <div class="tab" data-panel="stats">Statistics</div>
      ${hasTime ? `<div class="tab" data-panel="time">Time</div>` : ""}
      ${hasSamples ? `<div class="tab" data-panel="sample-data">Sample Data</div>` : ""}
      ${hasHistory ? `<div class="tab" data-panel="history">History</div>` : ""}
    </div>

    <div class="tab-panel" id="panel-schema">${renderSchema(doc)}</div>
    <div class="tab-panel" id="panel-stats">${renderStats(doc)}</div>
    ${hasTime ? `<div class="tab-panel" id="panel-time">${renderTime(doc)}</div>` : ""}
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
  history.replaceState(null, "", `#${encodeURIComponent(currentTable)}/${tabEl.dataset.panel}`);
}

/* ── Schema tab ─────────────────────────────────────────────────── */
function renderSchema(doc) {
  const columns = doc.columns || [];
  const documented = columns.some(col => col.description || Object.keys(col.tags || {}).length);
  const rows = columns.map(col => `
    <tr>
      <td>${esc(col.name)}</td>
      <td><span class="type-badge">${esc(col.dataType)}</span></td>
      <td>${col.nullable ? "" : '<span style="color:#dc3545">✗</span>'}</td>
      ${documented ? `<td class="column-description">${columnDescription(col)}</td>` : ""}
    </tr>
  `).join("");

  return `<div class="data-table-wrap">
    <table>
      <thead><tr><th>Column</th><th>Type</th><th>Nullable</th>${documented ? "<th>Description</th>" : ""}</tr></thead>
      <tbody>${rows}</tbody>
    </table>
  </div>`;
}

function columnDescription(col) {
  const tags = Object.entries(col.tags || {}).map(([k, v]) =>
    `<span class="column-tag">${esc(k)}: ${esc(typeof v === "string" ? v : JSON.stringify(v))}</span>`).join("");
  return (col.description ? `<span>${esc(col.description)}</span>` : "") + tags;
}

/* ── Stats tab ──────────────────────────────────────────────────── */
function renderStats(doc) {
  const cols = (doc.columns || []).map(c => c.name);
  const profileByName = {};
  for (const p of (doc.tableProfile?.columnProfile || [])) {
    profileByName[p.name] = p;
  }

  const numericKeys = ["valuesCount", "mean", "stddev", "min", "firstQuartile", "median", "thirdQuartile", "max"];
  const catKeys = ["valuesCount", "uniqueCount", "top", "freq"];

  const hasNumeric = cols.some(c => profileByName[c]?.mean != null);
  const hasCat = cols.some(c => profileByName[c]?.uniqueCount != null);

  const headerKeys = hasNumeric
    ? numericKeys
    : (hasCat ? catKeys : ["valuesCount"]);

  const headerLabels = {
    valuesCount: "count", mean: "mean", stddev: "std dev",
    min: "min", firstQuartile: "25%", median: "50%", thirdQuartile: "75%", max: "max",
    uniqueCount: "unique", top: "top", freq: "freq",
  };

  const headers = ["column", ...headerKeys].map(k =>
    `<th>${headerLabels[k] ?? k}</th>`
  ).join("");

  const rows = cols.map(col => {
    const s = profileByName[col] || {};
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

/* ── Time tab ───────────────────────────────────────────────────── */
const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAY_MS = 86400000;

function renderTime(doc) {
  const byName = {};
  for (const p of (doc.tableProfile?.columnProfile || [])) byName[p.name] = p;
  return (doc.columns || [])
    .filter(c => byName[c.name]?.distribution)
    .map(c => renderDistribution(c.name, byName[c.name].distribution))
    .join("");
}

const BUCKETING = { naive: "Naive timestamps, bucketed as stored", date: "Dates, bucketed as stored" };

function renderDistribution(column, dist) {
  if (dist.sameAs) {
    const relation = dist.sameAs.relation === "derived" ? "Same per-day counts as" : "Identical per-day counts to";
    const suffix = dist.sameAs.relation === "derived" ? " (derived)" : "";
    return `<section class="time-section">
      <h3>${esc(column)}</h3>
      <p class="time-summary">${relation} <code>${esc(dist.sameAs.column)}</code>${suffix}.</p>
    </section>`;
  }

  const monthly = dist.grain === "monthly";
  const unit = monthly ? "month" : "day";
  const missing = (dist.gaps || []).reduce((n, g) => n + g.count, 0);
  const days = Object.keys(dist.day);
  const months = Object.keys(dist.month);
  const summary = [
    dist.bucketing ? (BUCKETING[dist.bucketing] || `Bucketed in ${esc(dist.bucketing)}`) : null,
    monthly
      ? `${plural(months.length, "month")} with data, ${months[0]} to ${months[months.length - 1]}`
      : `${plural(days.length, "day")} with data, ${days[0]} to ${days[days.length - 1]}`,
    `${plural(missing, `missing ${unit}`)}${dist.gaps?.length ? ` in ${plural(dist.gaps.length, "gap")}` : ""}`,
    dist.rowsPerDay ? `median ${fmt(dist.rowsPerDay.median)} rows per day` : null,
  ].filter(Boolean).join(" · ");

  const hours = dist.hour
    ? `<div class="time-chart"><div class="time-chart-title">Rows by hour of day</div>
        ${renderBars(Object.entries(dist.hour).sort(([a], [b]) => a.localeCompare(b)), { labelEvery: 3 })}</div>`
    : "";
  const partialNote = dist.partialMonth in dist.month
    ? `<div class="time-note">Faded: ${dist.partialMonth} was still in progress when profiled.</div>`
    : "";

  return `<section class="time-section">
    <h3>${esc(column)} <span class="type-badge">${esc(dist.grain || "daily")}</span></h3>
    <p class="time-summary">${summary}.</p>
    ${monthly ? "" : `<div class="time-chart">
      <div class="time-chart-title">Rows per day</div>
      ${renderCalendar(dist.day, dist.partialDay)}
    </div>`}
    <div class="time-chart">
      <div class="time-chart-title">Rows per month</div>
      ${renderBars(monthSeries(dist.month), { labelFn: monthTick, partial: dist.partialMonth })}
      ${partialNote}
    </div>
    ${monthly ? "" : `<div class="time-row">
      <div class="time-chart"><div class="time-chart-title">Rows by weekday</div>
        ${renderBars(Object.entries(dist.weekday), { labelEvery: 1 })}</div>
      ${hours}
    </div>`}
  </section>`;
}

function plural(n, unit) {
  return `${fmt(n)} ${unit}${n === 1 ? "" : "s"}`;
}

/* Every month from the first to the last with data, empty months as 0. */
function monthSeries(months) {
  const keys = Object.keys(months).sort();
  if (!keys.length) return [];
  let [y, m] = keys[0].split("-").map(Number);
  const [lastY, lastM] = keys[keys.length - 1].split("-").map(Number);
  const out = [];
  while (y < lastY || (y === lastY && m <= lastM)) {
    const key = `${y}-${String(m).padStart(2, "0")}`;
    out.push([key, months[key] || 0]);
    if (++m > 12) { m = 1; y++; }
  }
  return out;
}

function monthTick(key, i) {
  const [y, m] = key.split("-");
  const initial = MONTH_NAMES[Number(m) - 1][0];
  return m === "01" || i === 0 ? `${initial}<br>${y}` : initial;
}

function renderBars(entries, { labelEvery = 0, labelFn = null, partial = null } = {}) {
  const max = Math.max(1, ...entries.map(([, v]) => v));
  const bars = entries.map(([label, v], i) => {
    const tick = labelFn ? labelFn(label, i) : (labelEvery && i % labelEvery === 0 ? label : "");
    const isPartial = label === partial;
    return `<div class="bar-slot" title="${esc(label)}: ${fmt(v)} rows${isPartial ? " (partial)" : ""}">
      <div class="bar${isPartial ? " bar-partial" : ""}" style="height:${v ? Math.max(2, (v / max) * 100) : 0}%"></div>
      <div class="bar-tick">${labelFn ? tick : esc(tick)}</div>
    </div>`;
  }).join("");
  return `<div class="bar-chart">
    <div class="bar-max">${fmt(max)}</div>
    <div class="bar-plot">${bars}</div>
  </div>`;
}

/* GitHub-style calendar: one strip per year, trimmed to the weeks in range, Mon–Sun as rows. */
function renderCalendar(days, partialDay) {
  const keys = Object.keys(days).sort();
  if (!keys.length) return "";
  const first = parseDay(keys[0]), last = parseDay(keys[keys.length - 1]);
  const max = Math.max(...Object.values(days));
  const weekday = t => (new Date(t).getUTCDay() + 6) % 7;  // Monday = 0

  const years = [];
  for (let year = new Date(first).getUTCFullYear(); year <= new Date(last).getUTCFullYear(); year++) {
    const start = Math.max(Date.UTC(year, 0, 1), first);
    const end = Math.min(Date.UTC(year, 11, 31), last);
    const offset = weekday(start);
    const column = t => Math.floor((offset + (t - start) / DAY_MS) / 7) + 1;
    const cells = Array.from({ length: offset }, () => `<div class="cal-cell cal-out"></div>`);
    const monthLabels = [];
    if (new Date(start).getUTCDate() <= 18) {
      monthLabels.push(`<span style="grid-column:1">${MONTH_NAMES[new Date(start).getUTCMonth()]}</span>`);
    }
    for (let t = start; t <= end; t += DAY_MS) {
      const d = new Date(t);
      const key = d.toISOString().slice(0, 10);
      if (d.getUTCDate() === 1 && t !== start) {
        monthLabels.push(`<span style="grid-column:${column(t)}">${MONTH_NAMES[d.getUTCMonth()]}</span>`);
      }
      if (days[key]) {
        const level = Math.min(4, Math.max(1, Math.ceil((days[key] / max) * 4)));
        const partial = key === partialDay ? " (partial)" : "";
        cells.push(`<div class="cal-cell cal-l${level}" title="${key}: ${fmt(days[key])} rows${partial}"></div>`);
      } else {
        cells.push(`<div class="cal-cell cal-missing" title="${key}: no rows"></div>`);
      }
    }
    years.push(`<div class="cal-year">
      <div class="cal-year-label">${year}</div>
      <div>
        <div class="cal-months">${monthLabels.join("")}</div>
        <div class="cal-grid">${cells.join("")}</div>
      </div>
    </div>`);
  }

  return `<div class="cal-wrap">${years.join("")}</div>
    <div class="cal-legend">
      <span>Fewer rows</span>
      ${[1, 2, 3, 4].map(l => `<div class="cal-cell cal-l${l}"></div>`).join("")}
      <span>More (max ${fmt(max)})</span>
      <div class="cal-cell cal-missing"></div><span>No rows</span>
    </div>`;
}

function parseDay(key) {
  const [y, m, d] = key.split("-").map(Number);
  return Date.UTC(y, m - 1, d);
}

/* ── Sample Data tab ────────────────────────────────────────────── */
function renderSampleData(doc) {
  if (!doc.sampleData?.rows?.length) return "";
  const { columns, rows } = doc.sampleData;
  const headers = columns.map(c => `<th>${esc(c)}</th>`).join("");
  const bodyRows = rows.map(row => {
    const cells = row.map(v => {
      if (v === null || v === undefined) return `<td class="null-cell">null</td>`;
      return `<td>${esc(String(v))}</td>`;
    }).join("");
    return `<tr>${cells}</tr>`;
  }).join("");

  return `<div class="data-table-wrap">
    <table>
      <thead><tr>${headers}</tr></thead>
      <tbody>${bodyRows}</tbody>
    </table>
  </div>`;
}

/* ── History tab ────────────────────────────────────────────────── */
function renderHistory(doc) {
  const history = doc.extension?.deltaHistory;
  if (!history?.length) return "";

  const rows = history.map(h => {
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

  const shown = doc.commitCount != null
    ? `<p class="time-summary">Latest ${history.length.toLocaleString()} of ${doc.commitCount.toLocaleString()} commits.</p>`
    : "";

  return `${shown}<div class="data-table-wrap">
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
function parseHash(raw) {
  const slash = raw.indexOf("/");
  if (slash === -1) return { table: decodeURIComponent(raw), tab: null };
  return { table: decodeURIComponent(raw.slice(0, slash)), tab: raw.slice(slash + 1) };
}

function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function groupStats(entries) {
  let rows = 0, cols = 0, maxDate = "";
  for (const { entry } of entries) {
    rows += entry.rowCount || 0;
    cols += entry.columnCount || 0;
    if (entry.updatedAt && entry.updatedAt > maxDate) maxDate = entry.updatedAt;
  }
  return { rows, cols, maxDate };
}

function fmtDateTime(iso) {
  const d = new Date(iso);
  const pad = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function fmtDuration(seconds) {
  for (const [unit, size] of [["days", 86400], ["h", 3600], ["min", 60]]) {
    if (seconds >= 2 * size) {
      const v = seconds / size;
      return `${v >= 10 ? Math.round(v).toLocaleString() : v.toFixed(1)} ${unit}`;
    }
  }
  return seconds >= 10 ? `${Math.round(seconds)} s` : `${+seconds.toFixed(1)} s`;
}

function freshnessText(f) {
  if (!f) return "";
  let text = `Last write ${fmtDuration(f.secondsSinceLastWrite)} before profiling`;
  if (f.typicalIntervalSeconds != null) {
    text += `, typically every ${fmtDuration(f.typicalIntervalSeconds)}`;
    if (f.ratio != null) text += ` (${f.ratio >= 10 ? Math.round(f.ratio) : f.ratio.toFixed(1)}×)`;
  }
  return text;
}

function fmt(n) {
  if (n === null || n === undefined) return "—";
  if (Number.isInteger(n)) return n.toLocaleString();
  return n.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

init();
