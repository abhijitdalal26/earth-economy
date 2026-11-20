/* Earth Economy - shared helpers for the interactive pages.
   Load after data.js. Everything works offline, from file://. */

window.T = (function () {
  const D = window.ATLAS_TIME;

  // ---- metrics -----------------------------------------------------------
  const METRICS = {
    r: { key: 'r', label: 'Revenue', unit: 'USD', fmt: (v) => fmtUSD(v) },
    p: { key: 'p', label: 'Profit', unit: 'USD', fmt: (v) => fmtUSD(v) },
    e: { key: 'e', label: 'Employees', unit: 'people', fmt: (v) => fmtInt(v) },
  };

  // ---- formatting --------------------------------------------------------
  // values in the data file are USD millions
  function fmtUSD(v) {
    if (v == null || isNaN(v)) return '—';
    const a = Math.abs(v);
    if (a >= 1e6) return '$' + (v / 1e6).toFixed(2) + 'T';
    if (a >= 1e3) return '$' + (v / 1e3).toFixed(1) + 'B';
    if (a >= 1) return '$' + Math.round(v) + 'M';
    return '$' + v.toFixed(2) + 'M';
  }
  function fmtInt(v) {
    if (v == null || isNaN(v)) return '—';
    const a = Math.abs(v);
    if (a >= 1e9) return (v / 1e9).toFixed(1) + 'B';
    if (a >= 1e6) return (v / 1e6).toFixed(1) + 'M';
    if (a >= 1e3) return (v / 1e3).toFixed(0) + 'K';
    return String(Math.round(v));
  }
  function fmtPct(v, d = 1) { return v == null || isNaN(v) ? '—' : v.toFixed(d) + '%'; }
  function fmtMult(v) { return v == null || isNaN(v) ? '—' : '×' + v.toFixed(v < 10 ? 1 : 0); }
  function fmtSigned(v, d = 1) { return (v > 0 ? '+' : '') + v.toFixed(d); }

  // ---- dom helpers -------------------------------------------------------
  function svg(tag, attrs, kids) {
    const e = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const k in (attrs || {})) {
      if (attrs[k] == null) continue;
      e.setAttribute(k, attrs[k]);
    }
    (kids || []).forEach((k) => e.appendChild(k));
    return e;
  }
  function h(tag, attrs, kids) {
    const e = document.createElement(tag);
    for (const k in (attrs || {})) {
      if (k === 'class') e.className = attrs[k];
      else if (k === 'html') e.innerHTML = attrs[k];
      else if (k === 'text') e.textContent = attrs[k];
      else if (k.startsWith('on')) e.addEventListener(k.slice(2), attrs[k]);
      else if (attrs[k] != null) e.setAttribute(k, attrs[k]);
    }
    (kids || []).forEach((k) => e.appendChild(typeof k === 'string' ? document.createTextNode(k) : k));
    return e;
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); return node; }

  // ---- tooltip -----------------------------------------------------------
  let tip;
  function tipEl() {
    if (!tip) { tip = h('div', { id: 'tip' }); document.body.appendChild(tip); }
    return tip;
  }
  function showTip(html, x, y) {
    const t = tipEl();
    t.innerHTML = html;
    t.style.opacity = '1';
    const r = t.getBoundingClientRect();
    let left = x + 16, top = y + 16;
    if (left + r.width > window.innerWidth - 10) left = x - r.width - 14;
    if (top + r.height > window.innerHeight - 10) top = y - r.height - 14;
    t.style.left = Math.max(6, left) + 'px';
    t.style.top = Math.max(6, top) + 'px';
  }
  function hideTip() { if (tip) tip.style.opacity = '0'; }

  // ---- data access -------------------------------------------------------
  const sectors = D.sectors;
  const colours = D.colours;
  const colour = (si) => colours[si] || '#9AA5B1';
  const sectorName = (si) => sectors[si];

  function val(row, metric, yi) { return row[metric] ? row[metric][yi] : null; }

  // A reported profit above revenue cannot be right; the source list carries a
  // handful of these. They are kept out of rankings so one bad row cannot
  // invent a "biggest mover".
  function plausible(row, metric, yi) {
    const v = val(row, metric, yi);
    if (v == null) return false;
    if (metric === 'p') {
      const rev = val(row, 'r', yi);
      if (rev != null && rev > 0 && v > rev) return false;
    }
    return true;
  }
  function implausibleCount(metric, yi) {
    let n = 0;
    for (const row of D.rows) {
      const v = val(row, metric, yi);
      if (v == null || metric !== 'p') continue;
      const rev = val(row, 'r', yi);
      if (rev != null && rev > 0 && v > rev) n++;
    }
    return n;
  }

  // companies that reported this metric in this year, biggest first
  function ranked(metric, yi) {
    const out = [];
    for (const row of D.rows) {
      const v = val(row, metric, yi);
      if (plausible(row, metric, yi)) out.push({ row: row, v: v, rank: 0 });
    }
    out.sort((a, b) => b.v - a.v);
    out.forEach((r, i) => { r.rank = i + 1; });
    return out;
  }
  function rankMap(metric, yi) {
    const m = new Map();
    for (const r of ranked(metric, yi)) m.set(r.row, r.rank);
    return m;
  }
  function totals(metric, yi) {
    let sum = 0, n = 0;
    for (const row of D.rows) {
      const v = val(row, metric, yi);
      if (v != null) { sum += v; n++; }
    }
    return { sum: sum, n: n };
  }
  // how many firms make up half the year's total (cumulative, biggest first)
  function halfCount(metric, yi) {
    const r = ranked(metric, yi);
    if (!r.length) return 0;
    const half = r.reduce((a, b) => a + b.v, 0) / 2;
    let s = 0, c = 0;
    for (const x of r) { s += x.v; c++; if (s >= half) break; }
    return c;
  }
  function groupBySector(metric, yi) {
    const g = sectors.map(() => ({ rev: 0, n: 0, prof: 0 }));
    let total = 0;
    for (const row of D.rows) {
      const v = val(row, metric, yi);
      if (v == null) continue;
      g[row.s].rev += v; g[row.s].n += 1; total += v;
    }
    return g.map((x, i) => ({ si: i, sector: sectors[i], rev: x.rev, n: x.n, share: total ? 100 * x.rev / total : 0 }));
  }
  function groupByCountry(metric, yi, limit) {
    const map = new Map();
    let total = 0;
    for (const row of D.rows) {
      const v = val(row, metric, yi);
      if (v == null) continue;
      map.set(row.c, (map.get(row.c) || 0) + v);
      total += v;
    }
    const arr = [...map.entries()].map(([c, v]) => ({ c: c, v: v, share: 100 * v / total }))
      .sort((a, b) => b.v - a.v);
    return limit ? arr.slice(0, limit) : arr;
  }

  // ---- shared state ------------------------------------------------------
  const S = { yi: D.years.length - 1, metric: 'r', topN: 25, sector: null, selected: null };
  const listeners = [];
  function onRender(fn) { listeners.push(fn); }
  function set(patch, silent) {
    Object.assign(S, patch);
    if (!silent) listeners.forEach((fn) => fn(S));
  }

  return {
    D, S, METRICS, sectors, colours,
    fmtUSD, fmtInt, fmtPct, fmtMult, fmtSigned,
    svg, h, clear, showTip, hideTip,
    val, plausible, implausibleCount, ranked, rankMap, totals, halfCount, groupBySector, groupByCountry,
    colour, sectorName, onRender, set,
  };
})();
