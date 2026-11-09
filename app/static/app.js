"use strict";

const $ = (id) => document.getElementById(id);
const state = { cfg: null, jobs: [], tab: "activas", sort: "score", openId: null, cv: "", src: "", why: {} };

const TABS = [
  ["activas", "Activas"],
  ["interesa", "Me interesa"],
  ["aplicada", "Aplicadas"],
  ["descartada", "Descartadas"],
];

/* ---------- utilidades ---------- */
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, method = "GET", body) {
  const res = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) { showAuth(false); throw new Error("Iniciá sesión"); }
  if (!res.ok) {
    let msg = "El servidor respondió " + res.status;
    try { msg = (await res.json()).error || msg; } catch (e) { /* sin detalle */ }
    throw new Error(msg);
  }
  return res.json();
}

let toastTimer;
function toast(text) {
  const t = $("toast");
  t.textContent = text;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), Math.min(15000, Math.max(4000, text.length * 70)));
}

function ago(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const days = Math.floor((Date.now() - d.getTime()) / 86400000);
  if (days <= 0) return "Hoy";
  if (days === 1) return "Ayer";
  if (days < 30) return `Hace ${days} días`;
  return d.toLocaleDateString("es-AR");
}

function cvHue(k) { let h = 0; for (const ch of String(k)) h = (h * 31 + ch.charCodeAt(0)) % 360; return h; }
const cvColor = (k) => `hsl(${cvHue(k)} 55% 42%)`;
const cvLabel = (k) => state.cfg?.profiles?.[k]?.label || k;
const debounce = (fn, ms = 250) => {
  let t;
  return (...a) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...a), ms);
  };
};

// "Nueva" = publicada en los últimos 2 días (o, sin fecha de publicación, cargada en las últimas 24 h).
const isNew = (j) => {
  if (j.status !== "nueva") return false;
  const t = new Date(j.posted || j.created).getTime();
  return !isNaN(t) && Date.now() - t < (j.posted ? 2 : 1) * 86400000;
};

/* ---------- empresas de interés ---------- */
const isMyCompany = (name) => {
  const n = norm(name || "");
  return !!n && (state.cfg?.empresas || []).some((e) => norm(e.name) && n.includes(norm(e.name)));
};
const norm = (t) => String(t || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();

const NO_COMPANY = ["", "confidencial", "empresa no indicada", "empresa confidencial"];
function computeHiring(jobs) {
  const by = new Map();
  jobs.forEach((j) => {
    const n = norm(j.company);
    if (NO_COMPANY.includes(n) || j.status === "descartada" || j.score < 15) return;
    const e = by.get(n) || { name: j.company.trim(), count: 0, best: 0 };
    e.count += 1;
    e.best = Math.max(e.best, j.score);
    by.set(n, e);
  });
  return [...by.values()].sort((a, b) => b.count - a.count || b.best - a.best).slice(0, 12);
}

function renderCompanies() {
  const list = state.cfg.empresas || [];
  const hiring = (state.hiring || []).filter((h) => !isMyCompany(h.name));
  const mine = list
    .map((e) => {
      const main = e.url || "https://www.google.com/search?q=" + encodeURIComponent(e.name + " trabajá con nosotros");
      const li = "https://www.linkedin.com/jobs/search/?keywords=" + encodeURIComponent(e.name);
      return `<li class="company"><a href="${esc(main)}" target="_blank" rel="noopener noreferrer" title="${e.url ? "Página de empleos" : "Buscar su página de empleos"}">${esc(e.name)}</a>
        <a class="alt" href="${esc(li)}" target="_blank" rel="noopener noreferrer">LinkedIn</a></li>`;
    })
    .join("");
  const hot = hiring
    .map((h) => `<li class="company"><button type="button" class="co-name" data-co="${esc(h.name)}" title="Ver sus ofertas">${esc(h.name)}</button>
        <span class="co-meta"><span class="co-count">${h.count} ${h.count === 1 ? "oferta" : "ofertas"}</span><button type="button" class="co-follow" data-follow="${esc(h.name)}" title="Sumar a mis empresas">+ Seguir</button></span></li>`)
    .join("");
  $("companies").innerHTML =
    (hot ? `<li class="co-head">Contratando ahora <span class="hint">según tus ofertas</span></li>${hot}` : "") +
    `<li class="co-head">Mis empresas</li>` +
    (mine || `<li class="hint" style="padding:4px 8px">Todavía no hay. Sumalas con “+ Seguir” o en Configuración.</li>`);
}

async function followCompany(name) {
  const cfg = structuredClone(state.cfg);
  if ((cfg.empresas || []).some((e) => norm(e.name) === norm(name))) return;
  cfg.empresas = [...(cfg.empresas || []), { name, url: "" }];
  await api("/api/config", "POST", cfg);
  state.cfg = cfg;
  toast(`${name} sumada a tus empresas.`);
  await loadJobs();
}

/* ---------- carga y filtros ---------- */
function checkAlerts() {
  const key = "maxJobIdSeen";
  const maxId = state.jobs.reduce((m, j) => Math.max(m, j.id), 0);
  let seen = null;
  try { seen = localStorage.getItem(key); } catch (e) { /* sin storage */ }
  try { localStorage.setItem(key, String(Math.max(maxId, Number(seen) || 0))); } catch (e) { /* sin storage */ }
  if (seen === null) return; // primera vez: no avisamos de todo lo que ya había
  const min = ((state.cfg || {}).avisos || {}).puntaje || 80;
  const hot = state.jobs.filter((j) => j.id > Number(seen) && j.score >= min && j.status === "nueva");
  if (!hot.length) return;
  const best = hot.reduce((a, b) => (b.score > a.score ? b : a));
  const text = hot.length === 1 ? `Nueva oferta de ${best.score}/100: ${best.title}` : `${hot.length} ofertas nuevas de ${min}+ puntos. La mejor: ${best.title} (${best.score})`;
  setTimeout(() => toast(text), 4300); // después del aviso de la búsqueda
  if ("Notification" in window && Notification.permission === "granted") new Notification("Búsqueda laboral", { body: text });
}

async function loadJobs() {
  const p = new URLSearchParams({
    q: $("fQ").value.trim(),
    location: $("fLoc").value.trim(),
    cv: state.cv,
    min_score: $("fMin").value,
  });
  state.why = {};
  try {
    state.jobs = await api("/api/jobs?" + p);
  } catch (e) {
    toast("No se pudieron cargar las ofertas. ¿Sigue corriendo run.py?");
    state.jobs = [];
  }
  if (!p.get("q") && !p.get("location") && !state.cv) state.hiring = computeHiring(state.jobs);
  renderCompanies();
  renderSourceFilter();
  render();
  checkAlerts();
}

const isAlert = (name) => name.startsWith("Alerta ");

function matchesSource(j) {
  if (!state.src) return true;
  if (state.src === "__gmail") return j.sources.some((s) => isAlert(s.name));
  return j.sources.some((s) => s.name === state.src);
}

function renderSourceFilter() {
  const names = [...new Set(state.jobs.flatMap((j) => j.sources.map((s) => s.name)))].sort();
  const opts = [["", "Todas"]];
  if (names.some(isAlert)) opts.push(["__gmail", "Todas las alertas de Gmail"]);
  names.forEach((n) => opts.push([n, n]));
  $("fSrc").innerHTML = opts.map(([v, l]) => `<option value="${esc(v)}" ${state.src === v ? "selected" : ""}>${esc(l)}</option>`).join("");
}

function filtersActive() {
  return !!(state.src || $("fOnlyEmp").checked || $("fQ").value.trim() || $("fLoc").value.trim() || state.cv || Number($("fMin").value) !== 15);
}

function renderCvFilter() {
  const opts = [["", "Todos"], ...Object.entries(state.cfg.profiles).map(([k, p]) => [k, p.label])];
  $("fCv").innerHTML = opts
    .map(([v, label]) => `<option value="${esc(v)}" ${state.cv === v ? "selected" : ""}>${esc(label)}</option>`)
    .join("");
}

/* ---------- render ---------- */
const isMobile = () => matchMedia("(max-width: 900px)").matches;

function inTab(j, tab) {
  return tab === "activas" ? j.status !== "descartada" && j.status !== "aplicada" : j.status === tab;
}

function visibleRows() {
  const onlyEmp = $("fOnlyEmp").checked;
  const rows = state.jobs.filter((j) => inTab(j, state.tab) && (!onlyEmp || isMyCompany(j.company)) && matchesSource(j));
  rows.sort((a, b) =>
    state.sort === "recent"
      ? String(b.posted || b.created).localeCompare(String(a.posted || a.created))
      : b.score - a.score
  );
  return rows;
}

function render() {
  $("tabs").innerHTML = TABS.map(([k, label]) => {
    const n = state.jobs.filter((j) => inTab(j, k)).length;
    return `<button class="tab" role="tab" data-tab="${k}" aria-selected="${state.tab === k}">${label}<span class="tab-count">${n}</span></button>`;
  }).join("");

  const rows = visibleRows();
  const ex = $("btnExport");
  ex.hidden = !["aplicada", "interesa"].includes(state.tab);
  ex.href = "/api/export?status=" + state.tab;
  $("count").textContent = rows.length === 1 ? "1 oferta" : `${rows.length} ofertas`;

  if (!rows.length) {
    state.openId = null;
    $("list").innerHTML = `<li>${emptyState()}</li>`;
    $("detail").innerHTML = detailPlaceholder();
    syncDetailMode();
    return;
  }
  if (!rows.some((j) => j.id === state.openId)) state.openId = isMobile() ? null : rows[0].id;

  const due = state.tab === "aplicada" ? rows.filter(needsFollowUp).length : 0;
  const banner = due
    ? `<li><div class="notice"><strong>${due === 1 ? "1 postulación lleva" : due + " postulaciones llevan"} varios días sin novedades.</strong> Escribile a la empresa para preguntar cómo sigue.</div></li>`
    : "";
  const summary = state.tab === "aplicada" ? trackSummaryHtml(rows) : "";
  $("list").innerHTML = summary + banner + rows.map(cardHtml).join("");
  renderDetail();
  syncDetailMode();
}

function syncDetailMode() {
  const open = isMobile() && state.openId != null;
  $("layout").classList.toggle("show-detail", open);
  document.body.classList.toggle("detail-open", open);
}

function emptyState() {
  if (filtersActive()) {
    return `<div class="empty"><h3>Ninguna oferta coincide</h3>
      <p>Probá con menos filtros o bajá el puntaje mínimo.</p>
      <div class="row"><button class="btn" data-act="clear">Limpiar filtros</button></div></div>`;
  }
  if (state.tab === "activas" && !state.jobs.length) {
    return `<div class="empty"><h3>Todavía no hay ofertas</h3>
      <p>Tocá Buscar ofertas, cargá las de ejemplo para ver cómo funciona o agregá un aviso a mano.</p>
      <div class="row">
        <button class="btn btn-primary" data-act="demo">Cargar ofertas de ejemplo</button>
        <button class="btn" data-act="add">Agregar oferta</button>
        <button class="btn" data-act="config">Configurar fuentes</button>
      </div></div>`;
  }
  const msg = {
    activas: "No quedan ofertas por revisar.",
    interesa: "Marcá una oferta con la estrella y aparece acá.",
    aplicada: "Cuando marques una oferta como Aplicada la vas a ver acá.",
    descartada: "No descartaste ninguna oferta.",
  }[state.tab];
  return `<div class="empty"><h3>${esc(msg)}</h3></div>`;
}

function detailPlaceholder() {
  return `<div class="detail-empty"><div><h3>Elegí una oferta</h3><p>Acá vas a ver el detalle, por qué tiene ese puntaje y qué CV conviene usar.</p></div></div>`;
}

function quality(score) {
  return score >= 75 ? ["top", "Muy buena"] : score >= 55 ? ["good", "Buena"] : score >= 35 ? ["mid", "Regular"] : ["low", "Baja"];
}

function avatar(name, big) {
  const n = name && name !== "Confidencial" ? name.trim() : "";
  const ch = (n.match(/[A-Za-zÁÉÍÓÚÑáéíóúñ0-9]/) || ["?"])[0].toUpperCase();
  let h = 0;
  for (const c of n) h = (h * 31 + c.charCodeAt(0)) % 360;
  return `<span class="avatar ${big ? "avatar-lg" : ""}" style="--h:${h}" aria-hidden="true">${esc(ch)}</span>`;
}

const STATUS_LABEL = { interesa: "Me interesa", aplicada: "Aplicada", descartada: "Descartada" };

function daysSince(iso) {
  return iso ? Math.floor((Date.now() - new Date(iso).getTime()) / 86400000) : 0;
}

function needsFollowUp(j) {
  const days = ((state.cfg || {}).avisos || {}).seguimiento_dias || 7;
  if (j.status !== "aplicada" || !j.applied_at) return false;
  if (["entrevista", "oferta", "rechazada"].includes(j.outcome)) return false;  // ya hay novedades
  return daysSince(j.followup_at || j.applied_at) >= days;
}
const OUTCOME_LABEL = { respondieron: "Me respondieron", entrevista: "Entrevista", oferta: "Me ofrecieron el puesto", rechazada: "Rechazada" };

function trackHtml(j) {
  if (j.status !== "aplicada") return "";
  const opts = [["", "Sin novedades"], ...Object.entries(OUTCOME_LABEL)]
    .map(([v, l]) => `<option value="${v}" ${v === (j.outcome || "") ? "selected" : ""}>${l}</option>`).join("");
  const d = daysSince(j.applied_at);
  const last = j.followup_at ? `Último seguimiento hace ${daysSince(j.followup_at)} ${daysSince(j.followup_at) === 1 ? "día" : "días"}.` : "Todavía no hiciste seguimiento.";
  return `<section class="d-sec"><h3>Seguimiento</h3>
    <p class="hint">Te postulaste hace ${d} ${d === 1 ? "día" : "días"}. ${last}</p>
    <div class="track-row">
      <label class="field"><span class="label">¿Cómo va?</span><select class="input" data-outcome>${opts}</select></label>
      <button type="button" class="btn" data-act="followed">Hice seguimiento hoy</button>
    </div></section>`;
}

function trackSummaryHtml(rows) {
  const total = rows.length;
  const by = (o) => rows.filter((j) => (j.outcome || "") === o).length;
  const due = rows.filter(needsFollowUp).length;
  const pill = (n, l, cls = "") => `<span class="ts ${cls}"><b>${n}</b>${l}</span>`;
  return `<li><div class="track-summary">${pill(total, "aplicadas")}${pill(by("") + by("respondieron") - due, "esperando")}${pill(due, "para seguimiento", due ? "warn" : "")}${pill(by("entrevista"), "entrevistas", by("entrevista") ? "ok" : "")}${pill(by("oferta"), "ofertas", by("oferta") ? "ok" : "")}${pill(by("rechazada"), "rechazadas")}</div></li>`;
}

function tagsHtml(j) {
  return [
    `<span class="chip chip-cv" style="background:hsl(${cvHue(j.cv)} 60% 94%);color:${cvColor(j.cv)}">${esc(cvLabel(j.cv))}</span>`,
    STATUS_LABEL[j.status] ? `<span class="chip chip-${esc(j.status)}">${STATUS_LABEL[j.status]}</span>` : "",
    isNew(j) ? `<span class="chip chip-nuevo">Nueva</span>` : "",
    j.status === "aplicada" && OUTCOME_LABEL[j.outcome] ? `<span class="chip chip-${j.outcome === "rechazada" ? "descartada" : "interesa"}">${OUTCOME_LABEL[j.outcome]}</span>` : "",
    needsFollowUp(j) ? `<span class="chip chip-seguimiento" title="Postulaste hace ${daysSince(j.applied_at)} días">Hacer seguimiento</span>` : "",
    isMyCompany(j.company) ? `<span class="chip chip-empresa">Mi empresa</span>` : "",
    j.sources.length > 1 ? `<span class="chip">${j.sources.length} portales</span>` : "",
  ].join("");
}

function cardHtml(j) {
  const sel = state.openId === j.id;
  const [qk, ql] = quality(j.score);
  const sub = [j.company || "Empresa no indicada", j.location || "Lugar no indicado"].join(" · ");
  const star = j.status === "interesa";
  return `<li class="job ${sel ? "selected" : ""}" style="border-left-color:${cvColor(j.cv)}" data-id="${j.id}" data-cv="${esc(j.cv)}" data-status="${esc(j.status)}" data-act="select" tabindex="0" role="button" aria-pressed="${sel}">
    ${avatar(j.company)}
    <div class="job-main">
      <h3 class="job-title">${esc(j.title)}</h3>
      <div class="job-sub">${esc(sub)}</div>
      <div class="job-tags">${tagsHtml(j)}<span class="job-ago">${esc(ago(j.posted))}</span></div>
    </div>
    <div class="job-side">
      <div class="qual q-${qk}" role="img" aria-label="Puntaje ${j.score} de 100, ${ql}"><b>${j.score}</b><small>${ql}</small></div>
      <div class="quick">
        <button class="icon-btn ${star ? "on" : ""}" data-act="status" data-status="${star ? "nueva" : "interesa"}" title="${star ? "Quitar de Me interesa" : "Me interesa"}" aria-label="Me interesa">${star ? "★" : "☆"}</button>
        <button class="icon-btn" data-act="status" data-status="descartada" title="Descartar" aria-label="Descartar">✕</button>
      </div>
    </div>
  </li>`;
}

function whyHtml(data) {
  const li = data.items
    .map((it) => `<li><span class="pts ${it.points >= 0 ? "pos" : "neg"}">${it.points >= 0 ? "+" : "−"}${Math.abs(it.points)}</span><span>${esc(it.label)}</span></li>`)
    .join("");
  return `<ul class="why">${li}</ul><p class="hint">Total: ${data.total}/100 (el puntaje siempre queda entre 0 y 100).</p>`;
}

async function loadWhy(id) {
  const box = $("why");
  if (!box) return;
  if (state.why[id]) {
    box.innerHTML = whyHtml(state.why[id]);
    return;
  }
  try {
    state.why[id] = await api("/api/explain?id=" + id);
    if (state.openId === id && $("why")) $("why").innerHTML = whyHtml(state.why[id]);
  } catch (e) {
    if ($("why")) $("why").innerHTML = `<p class="hint">No se pudo calcular el desglose.</p>`;
  }
}

function descHtml(text) {
  if (!text) return `<p class="hint">Esta oferta no tiene descripción.</p>`;
  const [main, portal] = String(text).split("\n§PORTAL§\n");
  let out = `<p class="job-desc">${esc(main)}</p>`;
  if (portal) {
    const rows = portal.split("\n").map((l) => {
      const i = l.indexOf(":");
      const label = i > 0 ? l.slice(0, i) : "";
      const items = (i > 0 ? l.slice(i + 1) : l).split(",").map((x) => x.trim()).filter(Boolean);
      return `<div class="pt-row"><b>${esc(label)}</b><div class="pt-tags">${items.map((x) => `<span class="pt-tag">${esc(x)}</span>`).join("")}</div></div>`;
    }).join("");
    out += `<div class="portal-box"><div class="portal-badge">Agregado por el portal (no es parte del texto del aviso)</div>${rows}</div>`;
  }
  return out;
}

function renderDetail() {
  const j = state.jobs.find((x) => x.id === state.openId);
  const box = $("detail");
  if (!j) {
    box.innerHTML = detailPlaceholder();
    return;
  }
  const keep = box.dataset.id === String(j.id) ? box.scrollTop : 0;
  box.dataset.id = j.id;
  const [qk, ql] = quality(j.score);
  const bars = Object.entries(j.cv_scores)
    .map(
      ([k, v]) => `<div class="cv-bar ${k === j.cv ? "best" : ""}">
        <span>${esc(cvLabel(k))}</span>
        <div class="cv-bar-track"><div class="cv-bar-fill" style="width:${v}%"></div></div>
        <span>${v}</span></div>`
    )
    .join("");
  const link = (j.sources.find((x) => x.url) || {}).url;
  const sources = j.sources
    .map((x) => `<li>${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">${esc(x.name)}</a>` : esc(x.name)}</li>`)
    .join("");
  const tog = (status, on, off) =>
    j.status === status
      ? `<button class="btn" data-act="status" data-status="nueva">${on}</button>`
      : `<button class="btn" data-act="status" data-status="${status}">${off}</button>`;
  box.innerHTML = `<article class="detail">
    <button class="btn btn-quiet detail-back" data-act="back">← Volver a la lista</button>
    <header class="d-head">
      ${avatar(j.company, true)}
      <div class="d-title">
        <h2>${esc(j.title)}</h2>
        <p>${esc([j.company || "Empresa no indicada", j.location || "Lugar no indicado", ago(j.posted)].filter(Boolean).join(" · "))}</p>
        <div class="job-tags">${tagsHtml(j)}</div>
      </div>
      <div class="qual qual-lg q-${qk}"><b>${j.score}</b><small>${ql}</small></div>
    </header>
    <div class="d-actions">
      <button class="btn btn-primary" data-act="post">Preparar postulación</button>
      ${link ? `<a class="btn" href="${esc(link)}" data-act="open" title="Se abre en una ventana al costado">Abrir oferta</a>` : ""}
      ${tog("interesa", "★ Me interesa", "☆ Me interesa")}
      ${tog("aplicada", "✓ Aplicada", "○ Aplicada")}
      ${j.status === "descartada" ? `<button class="btn" data-act="status" data-status="nueva">Recuperar</button>` : `<button class="btn btn-danger" data-act="status" data-status="descartada">Descartar</button>`}
    </div>
    <section class="d-sec"><h3>Por qué este puntaje</h3><div id="why"><p class="hint">Calculando…</p></div></section>
    <section class="d-sec"><h3>Qué CV conviene usar</h3><div class="cv-bars">${bars}</div></section>
    <section class="d-sec"><h3>Descripción</h3>${descHtml(j.description)}</section>
    ${trackHtml(j)}
    <section class="d-sec"><h3>Dónde está publicada</h3><ul class="sources">${sources}</ul></section>
    <section class="d-sec"><h3>Mis notas</h3>
      <textarea class="input" data-notes rows="3" placeholder="Contacto, fecha de entrevista, lo que quieras recordar">${esc(j.notes)}</textarea></section>
  </article>`;
  box.scrollTop = keep;
  loadWhy(j.id);
}

/* ---------- acciones ---------- */
async function setStatus(id, status) {
  const before = visibleRows();
  const idx = before.findIndex((j) => j.id === id);
  await api("/api/jobs/" + id, "POST", { status });
  const j = state.jobs.find((x) => x.id === id);
  if (j) j.status = status;
  const after = visibleRows();
  if (state.openId === id && !after.some((x) => x.id === id)) {
    // la oferta salió de esta pestaña: pasamos a la siguiente
    const next = before.slice(idx + 1).find((x) => after.some((y) => y.id === x.id)) || before.slice(0, idx).reverse().find((x) => after.some((y) => y.id === x.id));
    state.openId = isMobile() ? null : next ? next.id : null;
    if (isMobile() && history.state && history.state.detail) history.back();
  }
  render();
}

async function runBusy(btn, busyText, fn) {
  const label = btn.textContent;
  btn.disabled = true;
  btn.textContent = busyText;
  try {
    await fn();
  } catch (e) {
    toast("Algo falló: " + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = label;
  }
}

let progTimer = null;
const SEGS = 24;
function stopProgress() {
  clearInterval(progTimer);
  progTimer = null;
  $("searchFloat").hidden = true;
}
function startProgress() {
  const bar = $("sfBar");
  bar.innerHTML = "<i></i>".repeat(SEGS);
  $("sfCount").textContent = "0";
  $("soSteps").innerHTML = "";
  $("searchFloat").classList.remove("min");
  $("searchFloat").hidden = false;
  const icon = { espera: "○", corriendo: "…", listo: "✓", "falló": "✕" };
  progTimer = setInterval(async () => {
    try {
      const p = await api("/api/search/progress");
      const steps = p.steps || [];
      if (!steps.length) return;
      const hechos = steps.filter((x) => x.estado === "listo" || x.estado === "falló").length;
      const llenos = Math.floor((hechos / steps.length) * SEGS);
      [...bar.children].forEach((el, i) => {
        el.className = i < llenos ? "on" : i === llenos ? "run" : "";
      });
      $("sfCount").textContent = p.encontradas || 0;
      $("soSteps").innerHTML = steps.map((x) => `<li class="so-${esc(x.estado === "falló" ? "fail" : x.estado)}"><span>${icon[x.estado] || "○"}</span> ${esc(x.name)}</li>`).join("");
    } catch (e) { /* la próxima consulta lo corrige */ }
  }, 800);
}
$("sfMin").addEventListener("click", () => {
  const f = $("searchFloat");
  f.classList.toggle("min");
  $("sfMin").textContent = f.classList.contains("min") ? "+" : "–";
});

async function doSearch() {
  await runBusy($("btnSearch"), "Buscando…", async () => {
    if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
    startProgress();
    let r;
    try { r = await api("/api/search", "POST"); } finally { stopProgress(); }
    if (r.aviso) {
      toast(r.aviso);
    } else {
      // un solo mensaje por portal que falló, con el motivo
      const porPortal = {};
      (r.portales || []).forEach((x) => {
        const p = (porPortal[x.portal] ||= { total: 0, fallas: 0, motivo: "" });
        p.total += 1;
        if (x.nota) { p.fallas += 1; p.motivo ||= x.nota.replace(/^No se pudo leer: /, ""); }
      });
      const por = Object.entries(porPortal)
        .filter(([, p]) => p.fallas)
        .map(([n, p]) => ` ${n}: ${p.fallas} de ${p.total} búsquedas fallaron (${p.motivo}).`)
        .join("");
      const gfalla = (r.gmail || []).find((x) => x.nota);
      const gm = gfalla ? ` ${gfalla.nota}` : r.gmail?.length ? ` ${r.gmail.length} mail(s) de alertas leídos.` : "";
      const vacias = (r.empresas || []).filter((x) => !x.encontradas);
      const errs = r.errores?.length ? ` ${r.errores.length} feed(s) fallaron.` : "";
      const emp = vacias.length ? ` Sin puestos legibles en: ${vacias.map((x) => x.empresa).join(", ")}; abrilas desde Mis empresas.` : "";
      const det = r.detalles?.leidos ? ` Leí el aviso completo de ${r.detalles.leidos} ofertas de Computrabajo para puntuarlas mejor.` : "";
      toast(`${r.agregadas} ofertas nuevas cargadas.${det}${por}${gm}${errs}${emp}`);
      console.info("Revisión", { empresas: r.empresas, portales: r.portales, gmail: r.gmail, errores: r.errores });
    }
    await loadJobs();
    refreshStatus();
  });
}

async function loadDemo() {
  const r = await api("/api/demo", "POST");
  toast(`${r.agregadas} ofertas de ejemplo cargadas.`);
  await loadJobs();
}

/* ---------- postulación asistida ---------- */
let postJob = null;
function fill(tpl, vars) {
  return String(tpl || "").replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
}
function openPost(id) {
  const j = state.jobs.find((x) => x.id === id);
  if (!j) return;
  postJob = j;
  const post = state.cfg.postulacion || {};
  const tpls = post.plantillas || {};
  const tpl = tpls[j.cv] ?? Object.values(tpls)[0] ?? "Hola, me postulo para el puesto de {puesto}.\n\nSaludos,\n{nombre}";
  const vars = { puesto: j.title, empresa: j.company && j.company !== "Confidencial" ? j.company : "su empresa", cv: cvLabel(j.cv), nombre: post.nombre || "", telefono: post.telefono || "" };
  $("postInfo").textContent = `Usá el ${cvLabel(j.cv)} para esta oferta (puntaje ${j.score}).` + (state.cfg.profiles?.[j.cv]?.cv_file ? ` Archivo: ${state.cfg.profiles[j.cv].cv_file}.` : "") + (post.nombre ? "" : " Completá tu nombre en Configuración → Postulación para que salga en el mensaje.");
  $("pSubject").value = `Postulación: ${j.title}`;
  $("pBody").value = fill(tpl, vars).replace(/\n{3,}/g, "\n\n").trim();
  $("pOpen").disabled = !(j.sources[0] && j.sources[0].url);
  $("dPost").showModal();
}

async function refreshStatus(reload) {
  try {
    const st = await api("/api/status");
    if (!st.last_search) {
      $("lastSearch").textContent = "Todavía no se buscó.";
    } else {
      const mins = Math.round((Date.now() / 1000 - st.last_search) / 60);
      const when = mins < 1 ? "recién" : mins < 60 ? `hace ${mins} min` : mins < 1440 ? `hace ${Math.round(mins / 60)} h` : `hace ${Math.round(mins / 1440)} d`;
      $("lastSearch").textContent = `Última búsqueda ${when}.`;
    }
    if (reload && st.last_search !== state.lastSearch) {
      state.lastSearch = st.last_search;
      if (reload === "changed") await loadJobs();
    }
    state.lastSearch = st.last_search;
  } catch (e) {
    /* sin conexión con el servidor: no mostramos nada */
  }
}

/* ---------- diálogos ---------- */
function openDialog(dlg) {
  dlg.showModal();
}

function linesToObj(text) {
  const out = {};
  text.split("\n").forEach((line) => {
    const i = line.lastIndexOf(":");
    const key = (i === -1 ? line : line.slice(0, i)).trim();
    if (!key) return;
    const n = i === -1 ? NaN : parseFloat(line.slice(i + 1));
    out[key] = Number.isNaN(n) ? 5 : n;
  });
  return out;
}
const objToLines = (o) => Object.entries(o).map(([k, v]) => `${k}: ${v}`).join("\n");
const textToList = (t) => t.split("\n").map((s) => s.trim()).filter(Boolean);

async function refreshJoobleHint() {
  try {
    const st = await api("/api/jooble/status");
    $("jbKeyHint").textContent = st.key_set
      ? "Hay una clave guardada en esta PC. Escribí otra solo si querés cambiarla."
      : "Todavía no hay clave guardada.";
  } catch (e) {
    $("jbKeyHint").textContent = "";
  }
}

async function refreshGmailHint() {
  try {
    const st = await api("/api/gmail/status");
    $("gmPassHint").textContent = st.password_set
      ? "Hay una contraseña guardada en esta PC. Escribí otra solo si querés cambiarla."
      : "Todavía no hay contraseña guardada. Se guarda solo en esta PC, en la carpeta data.";
  } catch (e) {
    $("gmPassHint").textContent = "";
  }
}

function openConfig() {
  const c = state.cfg;
  $("cLocation").value = c.location || "";
  $("cLocs").value = (c.locations_ok || []).join("\n");
  $("cRss").value = (c.rss_feeds || []).join("\n");
  const ct = (c.portales || {}).computrabajo || {};
  $("cCtOn").checked = !!ct.enabled;
  $("cCtRegion").value = ct.region || "buenos-aires-gba";
  $("cCtPages").value = ct.max_pages || 2;
  $("cBusq").value = (c.busquedas || []).join("\n");
  const auto = c.auto || {};
  $("cAutoOn").checked = !!auto.enabled;
  $("cAutoH").value = auto.every_hours || 6;
  const av = c.avisos || {};
  $("cAvScore").value = av.puntaje || 80;
  $("cAvDays").value = av.seguimiento_dias || 7;
  const post = c.postulacion || {};
  $("cPName").value = post.nombre || "";
  $("cPPhone").value = post.telefono || "";
  $("cPTemplates").innerHTML = Object.entries(c.profiles)
    .map(([k, p]) => `<div class="field"><label for="tpl-${esc(k)}">Mensaje para ${esc(p.label)}</label>
      <textarea class="input" id="tpl-${esc(k)}" data-tpl="${esc(k)}" rows="7">${esc((post.plantillas || {})[k] || "")}</textarea></div>`)
    .join("");
  const gm = c.gmail || {};
  $("cGmOn").checked = !!gm.enabled;
  $("cGmEmail").value = gm.email || "";
  $("cGmDays").value = gm.days || 7;
  $("cGmSenders").value = (gm.senders || []).join("\n");
  $("cGmPass").value = "";
  refreshGmailHint();
  const bu = (c.portales || {}).bumeran || {};
  $("cBuOn").checked = !!bu.enabled;
  $("cBuPages").value = bu.max_pages || 2;
  $("cBuZonas").value = (bu.zonas || []).join("\n");
  $("cTaOn").checked = !!((c.portales || {}).talent || {}).enabled;
  $("cPeOn").checked = !!((c.portales || {}).portalempleo || {}).enabled;
  $("cAmOn").checked = !!((c.portales || {}).amia || {}).enabled;
  $("cReOn").checked = !!((c.portales || {}).remoto || {}).enabled;
  $("cLiOn").checked = !!((c.portales || {}).linkedin || {}).enabled;
  $("cJbOn").checked = !!((c.portales || {}).jooble || {}).enabled;
  $("cJbKey").value = "";
  refreshJoobleHint();
  $("cBjOn").checked = !!((c.portales || {}).buscojobs || {}).enabled;
  $("cZjOn").checked = !!((c.portales || {}).zonajobs || {}).enabled;
  $("cEmp").value = (c.empresas || []).map((e) => (e.url ? `${e.name} | ${e.url}` : e.name)).join("\n");
  $("cPen").value = objToLines(c.penalize || {});
  $("cProfiles").innerHTML = Object.entries(c.profiles)
    .map(
      ([k, p]) => `<div class="field">
        <label for="kw-${esc(k)}"><span class="dot" style="display:inline-block;margin-right:6px;background:${cvColor(k)}"></span>${esc(p.label)}</label>
        <textarea class="input" id="kw-${esc(k)}" data-profile="${esc(k)}" data-weights data-default="5" rows="7">${esc(objToLines(p.keywords))}</textarea></div>`
    )
    .join("");
  $("cPEmail").value = (c.perfil || {}).email || "";
  $("cPais").value = (c.perfil || {}).pais || "ar";
  enhanceAll($("dConfig"));
  showPane("perfil");
  openDialog($("dConfig"));
}

async function saveConfig(ev) {
  ev.preventDefault();
  const cfg = structuredClone(state.cfg);
  cfg.busquedas = textToList($("cBusq").value);
  cfg.location = $("cLocation").value.trim();
  cfg.locations_ok = textToList($("cLocs").value);
  cfg.rss_feeds = textToList($("cRss").value);
  cfg.portales = {
    ...(cfg.portales || {}),
    computrabajo: {
      enabled: $("cCtOn").checked,
      region: $("cCtRegion").value.trim() || "buenos-aires-gba",
      max_pages: Math.min(5, Math.max(1, Number($("cCtPages").value) || 2)),
    },
    bumeran: {
      enabled: $("cBuOn").checked,
      max_pages: Math.min(5, Math.max(1, Number($("cBuPages").value) || 2)),
      zonas: textToList($("cBuZonas").value),
    },
  };
  cfg.portales.talent = { ...(cfg.portales.talent || {}), enabled: $("cTaOn").checked };
  cfg.portales.portalempleo = { ...(cfg.portales.portalempleo || {}), enabled: $("cPeOn").checked };
  cfg.portales.amia = { ...(cfg.portales.amia || {}), enabled: $("cAmOn").checked };
  cfg.portales.remoto = { ...(cfg.portales.remoto || {}), enabled: $("cReOn").checked };
  cfg.portales.linkedin = { ...(cfg.portales.linkedin || {}), enabled: $("cLiOn").checked };
  cfg.portales.jooble = { ...(cfg.portales.jooble || {}), enabled: $("cJbOn").checked };
  cfg.portales.buscojobs = { ...(cfg.portales.buscojobs || {}), enabled: $("cBjOn").checked };
  cfg.portales.zonajobs = { ...(cfg.portales.zonajobs || {}), enabled: $("cZjOn").checked };
  cfg.empresas = textToList($("cEmp").value).map((l) => {
    const [name, ...rest] = l.split("|");
    return { name: name.trim(), url: rest.join("|").trim() };
  }).filter((e) => e.name);
  cfg.penalize = linesToObj($("cPen").value);
  cfg.perfil = { ...(cfg.perfil || {}), email: $("cPEmail").value.trim(), pais: $("cPais").value };
  document.querySelectorAll("[data-profile]").forEach((ta) => {
    cfg.profiles[ta.dataset.profile].keywords = linesToObj(ta.value);
  });
  cfg.avisos = { puntaje: Math.min(100, Math.max(30, Number($("cAvScore").value) || 80)), seguimiento_dias: Math.min(60, Math.max(1, Number($("cAvDays").value) || 7)) };
  cfg.auto = { enabled: $("cAutoOn").checked, every_hours: Math.min(48, Math.max(1, Number($("cAutoH").value) || 6)) };
  cfg.postulacion = { ...(cfg.postulacion || {}), nombre: $("cPName").value.trim(), telefono: $("cPPhone").value.trim(), plantillas: { ...((cfg.postulacion || {}).plantillas || {}) } };
  document.querySelectorAll("[data-tpl]").forEach((ta) => { cfg.postulacion.plantillas[ta.dataset.tpl] = ta.value; });
  cfg.gmail = {
    enabled: $("cGmOn").checked,
    email: $("cGmEmail").value.trim(),
    days: Math.min(60, Math.max(1, Number($("cGmDays").value) || 7)),
    senders: textToList($("cGmSenders").value),
  };
  try {
    if ($("cJbKey").value.trim()) await api("/api/jooble/key", "POST", { key: $("cJbKey").value });
    if ($("cGmPass").value.trim()) await api("/api/gmail/password", "POST", { password: $("cGmPass").value });
    $("cGmPass").value = "";
    await api("/api/config", "POST", cfg);
    state.cfg = cfg;
    $("dConfig").close();
    toast("Configuración guardada. Puntajes recalculados.");
    renderCompanies();
    await loadJobs();
  } catch (e) {
    toast("No se pudo guardar: " + e.message);
  }
}

async function saveOffer(ev) {
  ev.preventDefault();
  const body = {
    title: $("aTitle").value.trim(),
    company: $("aCompany").value.trim(),
    location: $("aLocation").value.trim(),
    description: $("aDesc").value.trim(),
    posted: new Date().toISOString(),
    source: "Manual",
    url: $("aUrl").value.trim(),
  };
  if (!body.title) return;
  try {
    const r = await api("/api/jobs", "POST", body);
    $("dAdd").close();
    toast(r.agregadas ? "Oferta guardada." : "Esa oferta ya estaba cargada.");
    await loadJobs();
  } catch (e) {
    toast("No se pudo guardar: " + e.message);
  }
}

function clearFilters() {
  $("fQ").value = "";
  $("fLoc").value = "";
  $("fMin").value = "15";
  $("fOnlyEmp").checked = false;
  state.cv = "";
  state.src = "";
  renderCvFilter();
  loadJobs();
}

/* ---------- eventos ---------- */
function bind() {
  const reload = debounce(loadJobs);
  $("fQ").addEventListener("input", reload);
  $("fLoc").addEventListener("input", reload);
  $("fMin").addEventListener("change", loadJobs);
  $("fSrc").addEventListener("change", (e) => {
    state.src = e.target.value;
    render();
  });
  $("fCv").addEventListener("change", (e) => {
    state.cv = e.target.value;
    loadJobs();
  });
  $("fOnlyEmp").addEventListener("change", render);
  $("companies").addEventListener("click", (e) => {
    const f = e.target.closest("[data-follow]");
    if (f) { followCompany(f.dataset.follow); return; }
    const c = e.target.closest("[data-co]");
    if (c) { $("fQ").value = c.dataset.co; $("empMenu").open = false; loadJobs(); }
  });
  $("fSort").addEventListener("change", (e) => {
    state.sort = e.target.value;
    render();
  });
  $("btnClear").addEventListener("click", clearFilters);
  const fp = $("filters");
  if (matchMedia("(max-width: 900px)").matches) fp.classList.add("collapsed");
  $("btnFilters").addEventListener("click", () => {
    const hidden = fp.classList.toggle("collapsed");
    $("btnFilters").setAttribute("aria-expanded", String(!hidden));
  });
  $("btnSearch").addEventListener("click", doSearch);
  $("btnAdd").addEventListener("click", () => {
    $("formAdd").reset();
    openDialog($("dAdd"));
  });
  $("btnConfig").addEventListener("click", openConfig);
  $("formAdd").addEventListener("submit", saveOffer);
  $("pCopy").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText($("pBody").value); toast("Mensaje copiado."); }
    catch (e) { $("pBody").select(); toast("Seleccioné el texto: copialo con Ctrl+C."); }
  });
  $("pGmail").addEventListener("click", () => {
    const q = new URLSearchParams({ view: "cm", fs: "1", su: $("pSubject").value, body: $("pBody").value });
    window.open("https://mail.google.com/mail/?" + q.toString(), "_blank", "noopener");
  });
  $("pOpen").addEventListener("click", () => {
    const u = postJob?.sources[0]?.url;
    if (u) openSide(postJob.id, u);
  });
  $("pApplied").addEventListener("click", async () => {
    if (!postJob) return;
    await setStatus(postJob.id, "aplicada");
    $("dPost").close();
    toast("Marcada como aplicada.");
  });
  $("formConfig").addEventListener("submit", saveConfig);

  document.querySelectorAll("[data-close]").forEach((b) =>
    b.addEventListener("click", () => b.closest("dialog").close())
  );

  $("btnDemo").addEventListener("click", async () => {
    await loadDemo();
  });
  $("btnRecalc").addEventListener("click", async () => {
    const r = await api("/api/recalc", "POST");
    toast(`${r.recalculadas} ofertas recalculadas.`);
    await loadJobs();
  });
  $("btnWipe").addEventListener("click", async () => {
    if (!confirm("¿Borrar todas las ofertas guardadas? Esto no se puede deshacer.")) return;
    await api("/api/clear", "POST");
    $("dConfig").close();
    toast("Se borraron todas las ofertas.");
    await loadJobs();
  });

  $("tabs").addEventListener("click", (e) => {
    const t = e.target.closest("[data-tab]");
    if (!t) return;
    state.tab = t.dataset.tab;
    state.openId = null;
    render();
  });

  const onAct = (e) => {
    const el = e.target.closest("[data-act]");
    if (!el) return;
    const li = el.closest(".job");
    const id = li ? Number(li.dataset.id) : state.openId;
    switch (el.dataset.act) {
      case "select":
        selectJob(id);
        break;
      case "back":
        closeDetail();
        break;
      case "status":
        e.stopPropagation();
        setStatus(id, el.dataset.status);
        break;
      case "post":
        openPost(id);
        break;
      case "followed": {
        const jb = state.jobs.find((x) => x.id === id);
        if (jb) {
          jb.followup_at = new Date().toISOString();
          api("/api/jobs/" + id, "POST", { followup: true });
          toast("Anotado: seguimiento de hoy.");
          render();
        }
        break;
      }
      case "open": {
        e.preventDefault();
        const jb = state.jobs.find((x) => x.id === id);
        const u = jb?.sources?.[0]?.url;
        if (u) openSide(id, u);
        break;
      }
      case "demo":
        loadDemo();
        break;
      case "add":
        $("btnAdd").click();
        break;
      case "config":
        openConfig();
        break;
      case "clear":
        clearFilters();
        break;
    }
  };
  $("list").addEventListener("click", onAct);
  $("detail").addEventListener("click", onAct);
  $("list").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target.classList.contains("job")) selectJob(Number(e.target.dataset.id));
  });

  // las notas se guardan al salir del campo
  $("detail").addEventListener("focusout", async (e) => {
    if (!e.target.matches("[data-notes]")) return;
    const j = state.jobs.find((x) => x.id === state.openId);
    if (j && j.notes !== e.target.value) {
      j.notes = e.target.value;
      try {
        await api("/api/jobs/" + j.id, "POST", { notes: j.notes });
        toast("Nota guardada.");
      } catch (err) {
        toast("No se pudo guardar la nota.");
      }
    }
  });

  // atajos de teclado (solo en la pantalla principal)
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (document.querySelector("dialog[open]")) return;
    if (e.target.closest("input, textarea, select, [contenteditable]")) return;
    const rows = visibleRows();
    const i = rows.findIndex((j) => j.id === state.openId);
    if (e.key === "ArrowDown" || e.key === "j") {
      e.preventDefault();
      if (rows.length) selectJob(rows[Math.min(rows.length - 1, i + 1)].id, true);
    } else if (e.key === "ArrowUp" || e.key === "k") {
      e.preventDefault();
      if (rows.length) selectJob(rows[Math.max(0, i - 1)].id, true);
    } else if (i >= 0 && ["s", "d", "a"].includes(e.key.toLowerCase())) {
      const want = { s: "interesa", d: "descartada", a: "aplicada" }[e.key.toLowerCase()];
      setStatus(rows[i].id, rows[i].status === want ? "nueva" : want);
    } else if (e.key === "Escape" && isMobile() && state.openId != null) {
      closeDetail();
    }
  });

  // en el celular, el botón "atrás" cierra el detalle
  window.addEventListener("popstate", () => {
    if (state.openId != null && isMobile()) {
      state.openId = null;
      render();
    }
  });
  matchMedia("(max-width: 900px)").addEventListener("change", () => {
    state.openId = null;
    render();
  });

  // el menú "Mis empresas" se cierra al tocar afuera
  document.addEventListener("click", (e) => {
    const m = $("empMenu");
    if (m.open && !m.contains(e.target)) m.open = false;
  });
}

function selectJob(id, scroll) {
  if (id == null) return;
  const wasOpen = state.openId != null;
  state.openId = id;
  if (isMobile() && !wasOpen) history.pushState({ detail: true }, "");
  render();
  if (scroll) document.querySelector(`.job[data-id="${id}"]`)?.scrollIntoView({ block: "nearest" });
  if (isMobile()) $("detail").scrollTop = 0;
}

function closeDetail() {
  if (history.state && history.state.detail) history.back();
  else {
    state.openId = null;
    render();
  }
}

let booted = false;
async function init() {
  let me;
  try {
    me = await (await fetch("/api/me")).json();
  } catch (e) {
    toast("No se pudo conectar. ¿Sigue corriendo run.py?");
    return;
  }
  if (!me.user) { state.mail = !!me.mail; showAuth(me.primera); return; }
  state.user = me.user;
  $("auth").hidden = true;
  $("accName").textContent = (me.user.nombre || me.user.email).split(" ")[0];
  try {
    state.cfg = await api("/api/config");
  } catch (e) {
    toast("No se pudo leer la configuración. ¿Sigue corriendo run.py?");
    return;
  }
  renderCvFilter();
  renderCompanies();
  if (!booted) { bind(); booted = true; setInterval(() => refreshStatus("changed"), 60000); }
  await loadJobs();
  if (!state.cfg.setup_done) openSetup();
  await refreshStatus(true);
}
init();


/* ---------- cuenta: ingreso, registro, salida ---------- */
let authMode = "login";
let resetToken = "";
function setAuthMode(mode) {
  authMode = mode;
  const tabs = mode === "login" || mode === "register";
  document.querySelector(".auth-tabs").hidden = !tabs;
  document.querySelectorAll("[data-auth]").forEach((b) => b.classList.toggle("on", b.dataset.auth === mode));
  // campos visibles por modo
  const show = { login: ["auEmail", "auPass"], register: ["auNombre", "auEmail", "auPass", "auPass2"], forgot: ["auEmail"], reset: ["auPass", "auPass2"] }[mode];
  ["auNombre", "auEmail", "auPass", "auPass2"].forEach((id) => { $(id).closest(".field").hidden = !show.includes(id); });
  document.querySelectorAll("#formAuth p.hint[data-only]").forEach((el) => (el.hidden = !(mode === "register" || mode === "reset")));
  $("auEmail").required = show.includes("auEmail");
  $("auPass").required = show.includes("auPass");
  $("auSubmit").textContent = { login: "Ingresar", register: "Crear mi cuenta", forgot: "Mandarme el link", reset: "Guardar contraseña nueva" }[mode];
  $("auPass").autocomplete = mode === "login" ? "current-password" : "new-password";
  $("auAcceptRow").hidden = mode !== "register";
  $("authLinks").hidden = !(mode === "login" && state.mail);
  $("authBack").hidden = !(mode === "forgot" || mode === "reset");
  $("authFoot").hidden = state.mail;
  $("authErr").hidden = true;
  $("authOk").hidden = true;
}
function authMsg(t) { $("authOk").textContent = t; $("authOk").hidden = false; $("authErr").hidden = true; }
function showAuth(primera) {
  $("auth").hidden = false;
  const h = location.hash;
  if (h.startsWith("#reset=")) {
    resetToken = h.slice(7);
    history.replaceState(null, "", location.pathname);
    setAuthMode("reset");
    return;
  }
  setAuthMode(primera ? "register" : "login");
  if (h === "#verificado" || h === "#verificado-error") {
    history.replaceState(null, "", location.pathname);
    if (h === "#verificado") authMsg("¡Correo confirmado! Ya podés ingresar.");
    else { $("authErr").textContent = "El link de confirmación venció o ya se usó. Pedí uno nuevo."; $("authErr").hidden = false; }
  }
  setTimeout(() => $("auEmail").focus(), 50);
}
async function mailAction(path, email) {
  const res = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email }) });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "No se pudo enviar.");
}
async function submitAuth(ev) {
  ev.preventDefault();
  const err = (t) => { $("authErr").textContent = t; $("authErr").hidden = false; };
  const email = $("auEmail").value.trim(), password = $("auPass").value;
  if (authMode === "register") {
    if (!$("auNombre").value.trim()) return err("Escribí tu nombre.");
    if (!$("auAccept").checked) return err("Para crear la cuenta tenés que aceptar los términos y la política de privacidad.");
  }
  if (authMode === "register" || authMode === "reset") {
    if (password.length < 8) return err("La contraseña debe tener al menos 8 caracteres.");
    if (password !== $("auPass2").value) return err("Las contraseñas no coinciden.");
  }
  $("auSubmit").disabled = true;
  try {
    if (authMode === "forgot") {
      await mailAction("/api/forgot", email);
      return authMsg("Si hay una cuenta con ese correo, te mandamos un link para elegir una contraseña nueva. Revisá también el spam.");
    }
    if (authMode === "reset") {
      const r = await fetch("/api/reset", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token: resetToken, password }) });
      const d = await r.json();
      if (!r.ok) return err(d.error || "No se pudo cambiar la contraseña.");
      setAuthMode("login");
      return authMsg("Contraseña cambiada. Ingresá con la nueva.");
    }
    const res = await fetch("/api/" + authMode, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, nombre: $("auNombre").value.trim(), acepto: authMode === "register" && $("auAccept").checked }),
    });
    const data = await res.json();
    if (!res.ok) return err(data.error || "No se pudo ingresar.");
    if (data.verificar) {
      setAuthMode("login");
      return authMsg(data.enviado ? "Cuenta creada. Te mandamos un correo: tocá el link para confirmarlo y después ingresá." : "Cuenta creada, pero no pudimos enviar el correo. Tocá «Reenviar el correo de confirmación».");
    }
    location.reload();
  } catch (e) {
    err(e.message && e.message !== "Failed to fetch" ? e.message : "No se pudo conectar con el programa.");
  } finally {
    $("auSubmit").disabled = false;
  }
}
function openAccount() {
  $("acNombre").textContent = state.user?.nombre || "Sin nombre";
  $("acEmail").textContent = state.user?.email || "";
  ["acOld", "acNew", "acDelPass"].forEach((i) => ($(i).value = ""));
  openDialog($("dAccount"));
}
async function logout() {
  try { await api("/api/logout", "POST"); } catch (e) { /* igual recargamos */ }
  location.reload();
}
document.querySelectorAll("[data-auth]").forEach((b) => b.addEventListener("click", () => setAuthMode(b.dataset.auth)));
$("formAuth").addEventListener("submit", submitAuth);
$("auForgot").addEventListener("click", (e) => { e.preventDefault(); setAuthMode("forgot"); });
$("auBack").addEventListener("click", (e) => { e.preventDefault(); setAuthMode("login"); });
$("auResend").addEventListener("click", async (e) => {
  e.preventDefault();
  const email = $("auEmail").value.trim();
  if (!email) { $("authErr").textContent = "Escribí tu correo arriba y volvé a tocar."; $("authErr").hidden = false; return; }
  try { await mailAction("/api/resend", email); authMsg("Si la cuenta existe y falta confirmarla, te mandamos el correo de nuevo."); }
  catch (err) { $("authErr").textContent = err.message; $("authErr").hidden = false; }
});
$("auShow").addEventListener("click", () => {
  const show = $("auPass").type === "password";
  $("auPass").type = show ? "text" : "password";
  $("auShow").textContent = show ? "Ocultar" : "Ver";
});
$("btnAccount").addEventListener("click", openAccount);
$("acLogout").addEventListener("click", logout);
$("acProfile").addEventListener("click", () => { $("dAccount").close(); openSetup(); });
$("acChange").addEventListener("click", async () => {
  try {
    await api("/api/account/password", "POST", { old: $("acOld").value, new: $("acNew").value });
    ["acOld", "acNew"].forEach((i) => ($(i).value = ""));
    toast("Contraseña cambiada.");
  } catch (e) { toast(e.message); }
});
$("acDelete").addEventListener("click", async () => {
  if (!$("acDelPass").value) { toast("Escribí tu contraseña para confirmar."); return; }
  if (!confirm("Se borran tu cuenta, tus ofertas y tus CV de esta computadora. ¿Seguro?")) return;
  try { await api("/api/account/delete", "POST", { password: $("acDelPass").value }); location.reload(); }
  catch (e) { toast(e.message); }
});

/* ---------- países ---------- */
const PAISES = { ar: "Argentina", mx: "México", cl: "Chile", pe: "Perú", ec: "Ecuador", pa: "Panamá", co: "Colombia", uy: "Uruguay", cr: "Costa Rica", do: "República Dominicana", gt: "Guatemala", bo: "Bolivia", py: "Paraguay" };
document.querySelectorAll("select[data-pais]").forEach((sel) => {
  sel.innerHTML = Object.entries(PAISES).map(([k, v]) => `<option value="${k}">${v}</option>`).join("");
});
$("wPais").addEventListener("change", () => {
  const ar = $("wPais").value === "ar";
  $("wPaisHint").textContent = ar ? "Cambia los portales que se consultan: algunos solo existen en Argentina." : "Se buscará en Computrabajo" + (["co", "uy", "cr", "do", "gt", "bo", "py"].includes($("wPais").value) ? "." : " y en el portal Bumeran de ese país.") + " Escribí abajo tu localidad y zonas de ese país.";
  if (!ar && $("wZonas").value.includes("CABA")) $("wZonas").value = "";
});

/* ---------- registro inicial / perfil ---------- */
let wzStep = 1;
const WZ_STEPS = 4;
let wzPresets = [];
function wzShow(n) {
  wzStep = Math.max(1, Math.min(WZ_STEPS, n));
  document.querySelectorAll("#formSetup [data-step]").forEach((el) => (el.hidden = Number(el.dataset.step) !== wzStep));
  $("wzStep").textContent = `Paso ${wzStep} de ${WZ_STEPS}`;
  $("wBack").hidden = wzStep === 1;
  $("wNext").hidden = wzStep === WZ_STEPS;
  $("wDone").hidden = wzStep !== WZ_STEPS;
  if (wzStep === WZ_STEPS) wzRenderCvs();
}
function wzRubros() {
  return [...document.querySelectorAll("#setupRubros input:checked")].map((i) => i.value);
}
function wzRenderCvs() {
  const rubros = wzRubros();
  const labels = Object.fromEntries(wzPresets.map((r) => [r.key, r.label]));
  const current = state.cfg.profiles || {};
  $("wCvs").innerHTML = (rubros.length ? rubros : ["general"])
    .map((k) => `<div class="field"><label for="wcv-${esc(k)}">CV de ${esc(labels[k] || "tu perfil")}${current[k]?.cv_file ? ` <span class="hint">(ya cargado: ${esc(current[k].cv_file)})</span>` : ""}</label>
      <input class="input" type="file" id="wcv-${esc(k)}" data-cvkey="${esc(k)}" accept=".pdf,.doc,.docx,.odt,.txt"></div>`)
    .join("");
}
async function openSetup() {
  wzPresets = await api("/api/presets");
  const c = state.cfg, per = c.perfil || {}, post = c.postulacion || {};
  const mine = new Set(Object.keys(c.profiles || {}));
  $("setupRubros").innerHTML = wzPresets
    .map((r) => `<label class="seg-option"><input type="checkbox" value="${esc(r.key)}" ${c.setup_done && mine.has(r.key) ? "checked" : ""}> <span><b>${esc(r.label)}</b><br><span class="hint">${esc(r.queries.slice(0, 3).join(", "))}…</span></span></label>`)
    .join("");
  $("setupExtra").value = "";
  $("wNombre").value = per.nombre || post.nombre || "";
  $("wEmail").value = per.email || "";
  $("wTel").value = per.telefono || post.telefono || "";
  $("wLocalidad").value = per.localidad || "";
  $("wModalidad").value = per.modalidad || "ambos";
  $("wPais").value = per.pais || "ar";
  $("wZonas").value = (per.zonas || ["Buenos Aires", "Capital Federal", "CABA"]).join(", ");
  $("wNivel").value = per.nivel || "sin";
  $("wCancel").hidden = !c.setup_done;
  wzShow(1);
  openDialog($("dSetup"));
}
function fileToBase64(file) {
  return new Promise((ok, fail) => {
    const r = new FileReader();
    r.onload = () => ok(String(r.result).split(",")[1] || "");
    r.onerror = () => fail(new Error("No se pudo leer el archivo"));
    r.readAsDataURL(file);
  });
}
function wzNext() {
  if (wzStep === 1) {
    if (!$("wNombre").value.trim()) { toast("Escribí tu nombre."); return; }
    const em = $("wEmail").value.trim();
    if (em && !/^\S+@\S+\.\S+$/.test(em)) { toast("El correo no parece válido."); return; }
  }
  if (wzStep === 2 && !wzRubros().length && !textToList($("setupExtra").value).length) {
    toast("Elegí al menos un rubro o escribí un puesto.");
    return;
  }
  wzShow(wzStep + 1);
}
async function saveSetup(ev) {
  ev.preventDefault();
  const body = {
    rubros: wzRubros(),
    extra: textToList($("setupExtra").value),
    perfil: {
      nombre: $("wNombre").value.trim(), email: $("wEmail").value.trim(), telefono: $("wTel").value.trim(),
      pais: $("wPais").value, localidad: $("wLocalidad").value.trim(), zonas: $("wZonas").value, nivel: $("wNivel").value, modalidad: $("wModalidad").value,
    },
  };
  try {
    await api("/api/setup", "POST", body);
    const cvMsgs = [];
    for (const input of document.querySelectorAll("#wCvs input[type=file]")) {
      const f = input.files[0];
      if (!f) continue;
      const key = input.dataset.cvkey === "general" ? "general" : input.dataset.cvkey;
      const r = await api("/api/cv", "POST", { profile: key, filename: f.name, data: await fileToBase64(f) });
      cvMsgs.push(r.leido
        ? `Leí tu CV (${f.name}): sumé ${r.agregadas.length} aptitudes${r.agregadas.length ? " (" + r.agregadas.slice(0, 6).join(", ") + ")" : ""} y reforcé ${r.reforzadas.length}.`
        : `Guardé ${f.name}, pero no pude leer su texto. Probá con una versión en Word (.docx) o texto para sumar tus aptitudes.`);
    }
    $("dSetup").close();
    state.cfg = await api("/api/config");
    renderCvFilter();
    await loadJobs();
    toast(cvMsgs.length ? cvMsgs.join(" ") : "Perfil guardado. Apretá Buscar ofertas para traer los primeros avisos.");
  } catch (e) { toast("No se pudo guardar: " + e.message); }
}
$("formSetup").addEventListener("submit", saveSetup);
$("wNext").addEventListener("click", wzNext);
$("wBack").addEventListener("click", () => wzShow(wzStep - 1));
$("btnRubro").addEventListener("click", () => { $("dConfig").close(); openSetup(); });


/* ---------- postulación en ventana lateral ---------- */
let sideWin = null;
let pendingApply = null;
function openSide(id, url) {
  const j = state.jobs.find((x) => x.id === id);
  const w = Math.round(screen.availWidth * (isMobile() ? 1 : 0.55));
  const feat = `popup=yes,width=${w},height=${screen.availHeight},left=${screen.availLeft + screen.availWidth - w},top=${screen.availTop}`;
  const win = window.open("about:blank", "ofertaLateral", feat);
  if (!win) { window.open(url, "_blank", "noopener"); }  // el navegador bloqueó la ventana: se abre como pestaña
  else {
    try { win.opener = null; } catch (e) { /* ya está aislada */ }
    win.location.href = url;
    win.focus();
    sideWin = win;
  }
  pendingApply = { id, title: j?.title || "la oferta", company: j?.company || "" };
  hideApplyAsk();
}
function showApplyAsk() {
  if (!pendingApply) return;
  const box = $("applyAsk");
  $("applyAskText").textContent = `¿Te postulaste a ${pendingApply.title}${pendingApply.company ? " en " + pendingApply.company : ""}?`;
  box.hidden = false;
}
function hideApplyAsk() { $("applyAsk").hidden = true; }
function checkReturn() {
  if (!pendingApply || !$("applyAsk").hidden) return;
  // volvió a la app (o cerró la ventana lateral): preguntamos
  if (document.visibilityState === "visible" && (!sideWin || sideWin.closed || document.hasFocus())) showApplyAsk();
}
window.addEventListener("focus", () => setTimeout(checkReturn, 400));
document.addEventListener("visibilitychange", checkReturn);
setInterval(() => { if (pendingApply && sideWin && sideWin.closed) checkReturn(); }, 1500);
async function answerApply(kind) {
  const p = pendingApply;
  hideApplyAsk();
  pendingApply = null;
  if (!p) return;
  if (kind === "si") { await setStatus(p.id, "aplicada"); toast("Marcada como aplicada. Sigamos con la próxima."); }
  else if (kind === "no-sirve") { await setStatus(p.id, "descartada"); }
  if (sideWin && !sideWin.closed && kind !== "luego") { try { sideWin.close(); } catch (e) { /* nada */ } }
  if (kind === "luego") pendingApply = null;
}
$("applyYes").addEventListener("click", () => answerApply("si"));
$("applyLater").addEventListener("click", () => answerApply("luego"));
$("applyNo").addEventListener("click", () => answerApply("no-sirve"));


/* ---------- Configuración: secciones y campos amigables ---------- */
function showPane(name) {
  document.querySelectorAll("#dConfig .st-pane").forEach((el) => (el.hidden = el.dataset.pane !== name));
  document.querySelectorAll("#stNav button").forEach((b) => b.classList.toggle("on", b.dataset.pane === name));
  const pane = document.querySelector(`#dConfig .st-pane[data-pane="${name}"]`);
  if (pane) pane.scrollIntoView({ block: "start" });
  document.querySelector(".st-content")?.scrollTo(0, 0);
}
document.querySelectorAll("#stNav button").forEach((b) => b.addEventListener("click", () => showPane(b.dataset.pane)));

// Cada textarea con data-chips / data-weights / data-companies se esconde y se reemplaza por un editor;
// el textarea sigue guardando el valor (una línea por elemento), así el resto del código no cambia.
const widgets = new WeakMap();
function enhanceAll(root) {
  root.querySelectorAll("textarea[data-chips], textarea[data-weights], textarea[data-companies]").forEach((ta) => {
    if (!widgets.has(ta)) {
      const host = document.createElement("div");
      host.className = "w-host";
      ta.after(host);
      ta.hidden = true;
      widgets.set(ta, { host, render: null });
      const kind = ta.hasAttribute("data-chips") ? chipsWidget : ta.hasAttribute("data-weights") ? weightsWidget : companiesWidget;
      widgets.get(ta).render = kind(ta, host);
    }
    widgets.get(ta).render();
  });
}
const lines = (ta) => ta.value.split("\n").map((x) => x.trim()).filter(Boolean);

function chipsWidget(ta, host) {
  let items = [];
  const commit = () => { ta.value = items.join("\n"); };
  function render() {
    items = lines(ta);
    host.innerHTML = `<div class="chips">${items.map((t, i) => `<span class="chip-i">${esc(t)}<button type="button" data-i="${i}" aria-label="Quitar ${esc(t)}">×</button></span>`).join("")}<input class="chip-input" placeholder="${esc(ta.dataset.placeholder || "Agregar…")}"></div>`;
    const input = host.querySelector("input");
    const add = () => {
      input.value.split(/[,\n]/).map((x) => x.trim()).filter(Boolean).forEach((v) => { if (!items.some((x) => x.toLowerCase() === v.toLowerCase())) items.push(v); });
      input.value = "";
      commit(); render();
      host.querySelector("input").focus();
    };
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === ",") { e.preventDefault(); if (input.value.trim()) add(); }
      else if (e.key === "Backspace" && !input.value && items.length) { items.pop(); commit(); render(); host.querySelector("input").focus(); }
    });
    input.addEventListener("blur", () => { if (input.value.trim()) add(); });
    host.querySelector(".chips").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-i]");
      if (b) { items.splice(Number(b.dataset.i), 1); commit(); render(); }
      else if (e.target.classList.contains("chips")) input.focus();
    });
  }
  return render;
}

function weightsWidget(ta, host) {
  let rows = [];
  const commit = () => { ta.value = rows.map((r) => `${r.w}: ${r.n}`).join("\n"); };
  const def = Number(ta.dataset.default || 5);
  function render() {
    rows = lines(ta).map((l) => { const i = l.lastIndexOf(":"); return { w: (i === -1 ? l : l.slice(0, i)).trim(), n: Number(i === -1 ? def : l.slice(i + 1)) || def }; });
    host.innerHTML = `<div class="weights">${rows.map((r, i) => `<span class="w-chip ${r.n < 0 ? "neg" : ""}"><span class="w-word">${esc(r.w)}</span><input type="number" value="${r.n}" data-i="${i}" aria-label="Peso de ${esc(r.w)}"><button type="button" data-i="${i}" aria-label="Quitar ${esc(r.w)}">×</button></span>`).join("")}</div>
      <div class="w-add"><input class="input w-new" placeholder="Agregar palabra…"><input class="input w-num" type="number" value="${def}" aria-label="Peso"><button type="button" class="btn btn-sm">Agregar</button></div>`;
    host.querySelectorAll(".w-chip input").forEach((inp) => inp.addEventListener("change", () => { rows[Number(inp.dataset.i)].n = Number(inp.value) || 0; commit(); render(); }));
    host.querySelectorAll(".w-chip button").forEach((b) => b.addEventListener("click", () => { rows.splice(Number(b.dataset.i), 1); commit(); render(); }));
    const add = () => {
      const w = host.querySelector(".w-new").value.trim();
      if (!w) return;
      const n = Number(host.querySelector(".w-num").value) || def;
      const ex = rows.find((r) => r.w.toLowerCase() === w.toLowerCase());
      if (ex) ex.n = n; else rows.push({ w, n });
      commit(); render();
      host.querySelector(".w-new").focus();
    };
    host.querySelector(".w-add button").addEventListener("click", add);
    host.querySelector(".w-new").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); add(); } });
  }
  return render;
}

function companiesWidget(ta, host) {
  let rows = [];
  const commit = () => { ta.value = rows.filter((r) => r.name.trim()).map((r) => (r.url.trim() ? `${r.name.trim()} | ${r.url.trim()}` : r.name.trim())).join("\n"); };
  function render(keep) {
    if (keep !== true) rows = lines(ta).map((l) => { const [n, ...u] = l.split("|"); return { name: n.trim(), url: u.join("|").trim() }; });
    host.innerHTML = `<div class="co-list">${rows.map((r, i) => `<div class="co-row"><input class="input" data-k="name" data-i="${i}" value="${esc(r.name)}" placeholder="Empresa" aria-label="Empresa"><input class="input" data-k="url" data-i="${i}" value="${esc(r.url)}" placeholder="Link de su página de empleos (opcional)" aria-label="Link"><button type="button" class="btn btn-quiet" data-i="${i}" aria-label="Quitar">×</button></div>`).join("")}</div><button type="button" class="btn btn-sm co-add">+ Agregar empresa</button>`;
    host.querySelectorAll(".co-row input").forEach((inp) => inp.addEventListener("input", () => { rows[Number(inp.dataset.i)][inp.dataset.k] = inp.value; commit(); }));
    host.querySelectorAll(".co-row button").forEach((b) => b.addEventListener("click", () => { rows.splice(Number(b.dataset.i), 1); commit(); render(true); }));
    host.querySelector(".co-add").addEventListener("click", () => { rows.push({ name: "", url: "" }); render(true); const ins = host.querySelectorAll('.co-row input[data-k="name"]'); ins[ins.length - 1].focus(); });
  }
  return render;
}


document.addEventListener("change", async (e) => {
  if (!e.target.matches("[data-outcome]")) return;
  const j = state.jobs.find((x) => x.id === state.openId);
  if (!j) return;
  j.outcome = e.target.value;
  try { await api("/api/jobs/" + j.id, "POST", { outcome: j.outcome }); } catch (err) { toast("No se pudo guardar: " + err.message); }
  render();
});
