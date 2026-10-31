/* HiStrA interactive bridge editor. Dependency-free canvas renderer. */
"use strict";

const S = {
  state: null,
  preview: null,
  materials: {},
  controller: null,
  timer: null,
  drawQueued: false,
  view: { yaw: -0.72, pitch: 0.4, zoom: 1 },
  drag: null,
  options: { fill: true, wire: true, nodes: false, supports: true, colorMode: "material" },
};

const $ = (id) => document.getElementById(id);
const canvas = $("canvas");
const ctx = canvas.getContext("2d");

const GROUPS = [
  "#2dd4bf", "#38bdf8", "#a78bfa", "#f472b6", "#fbbf24",
  "#34d399", "#fb923c", "#60a5fa", "#c084fc", "#f87171",
];

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function number(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function numInput(entity, index, field, label, step = "1") {
  const value = entity[field] ?? 0;
  return `<label>${esc(label)}<input type="number" step="${step}" data-entity="${index.entity}" data-index="${index.index}" data-field="${field}" value="${esc(value)}"></label>`;
}

function baseState(raw) {
  const state = {
    name: raw.name || "InteractiveBridge",
    nl: number(raw.nl, 60),
    strips: (raw.strips || []).map((strip) => ({
      width: number(strip.width, 300),
      height: number(strip.height, 0),
      material_key: number(strip.material_key, 0),
    })),
    spans: (raw.spans || []).map((span) => ({ ...span })),
    piers: (raw.piers || []).map((pier) => ({ ...pier })),
    left_abutment: { ...(raw.left_abutment || {}) },
    right_abutment: { ...(raw.right_abutment || {}) },
    elevation: { ...(raw.elevation || {}) },
  };
  if (!state.strips.length) state.strips.push({ width: 300, height: 0, material_key: 0 });
  if (!state.spans.length) state.spans.push(defaultSpan());
  syncPiers(state);
  return state;
}

function defaultSpan() {
  return { L: 400, f: 100, Tb: 30, Tt: 25, Asx: 36.8699, Adx: 36.8699, S1: 0, S2: 0, Dz: 0 };
}

function defaultPier() {
  return { H: 150, Hf: 60, b2: 70, B1f: 30, B3f: 30, W1f: 20, W3f: 20 };
}

function syncPiers(state = S.state) {
  const needed = Math.max(0, state.spans.length - 1);
  while (state.piers.length < needed) state.piers.push(defaultPier());
  state.piers.length = needed;
}

function totalWidth() {
  return S.state.strips.reduce((sum, strip) => sum + number(strip.width, 0), 0);
}

function payload() {
  return {
    name: S.state.name,
    width: totalWidth(),
    nl: number(S.state.nl, 60),
    strips: S.state.strips,
    spans: S.state.spans,
    piers: S.state.piers,
    left_abutment: S.state.left_abutment,
    right_abutment: S.state.right_abutment,
    elevation: S.state.elevation,
  };
}

/* ---------------------------------------------------------------- render UI */

function renderBridge() {
  document.querySelectorAll("[data-bind]").forEach((input) => {
    const path = input.dataset.bind.split(".");
    let target = S.state;
    for (let i = 0; i < path.length - 1; i += 1) target = target[path[i]];
    input.value = target[path[path.length - 1]];
  });
  $("width-badge").textContent = `${Math.round(totalWidth())} cm`;
  $("pier-count").textContent = String(S.state.piers.length);
}

function renderStrips() {
  const host = $("strips");
  host.innerHTML = S.state.strips.map((strip, index) => `
    <div class="card">
      <div class="card-title"><span>Strip ${index + 1}</span>${S.state.strips.length > 1
        ? `<button class="remove" type="button" data-action="remove-strip" data-index="${index}">remove</button>` : ""}</div>
      <div class="card-grid three">
        ${numInput(strip, { entity: "strip", index }, "width", "Width")}
        ${numInput(strip, { entity: "strip", index }, "height", "Height")}
        ${numInput(strip, { entity: "strip", index }, "material_key", "Material")}
      </div>
    </div>`).join("");
}

function renderSpans() {
  const host = $("spans");
  host.innerHTML = S.state.spans.map((span, index) => `
    <div class="card">
      <div class="card-title"><span>Span ${index + 1}</span>${S.state.spans.length > 1
        ? `<button class="remove" type="button" data-action="remove-span" data-index="${index}">remove</button>` : ""}</div>
      <div class="card-grid">
        ${numInput(span, { entity: "span", index }, "L", "Length L")}
        ${numInput(span, { entity: "span", index }, "f", "Rise f")}
        ${numInput(span, { entity: "span", index }, "Tb", "Thickness Tb")}
        ${numInput(span, { entity: "span", index }, "Tt", "Thickness Tt")}
        ${numInput(span, { entity: "span", index }, "Asx", "Asx")}
        ${numInput(span, { entity: "span", index }, "Adx", "Adx")}
        ${numInput(span, { entity: "span", index }, "S1", "Skew S1")}
        ${numInput(span, { entity: "span", index }, "S2", "Skew S2")}
      </div>
    </div>`).join("");
}

function renderPiers() {
  const host = $("piers");
  host.innerHTML = S.state.piers.length ? S.state.piers.map((pier, index) => `
    <div class="card">
      <div class="card-title"><span>Pier ${index + 1}</span></div>
      <div class="card-grid">
        ${numInput(pier, { entity: "pier", index }, "H", "Height H")}
        ${numInput(pier, { entity: "pier", index }, "Hf", "Foundation Hf")}
        ${numInput(pier, { entity: "pier", index }, "b2", "Shaft b2")}
        ${numInput(pier, { entity: "pier", index }, "B1f", "Footing B1f")}
        ${numInput(pier, { entity: "pier", index }, "B3f", "Footing B3f")}
        ${numInput(pier, { entity: "pier", index }, "W1f", "Wing W1f")}
        ${numInput(pier, { entity: "pier", index }, "W3f", "Wing W3f")}
      </div>
    </div>`).join("") : `<p class="hint">A single-span bridge has no piers.</p>`;
  $("pier-count").textContent = String(S.state.piers.length);
}

function renderAbutments() {
  const host = $("abutments");
  host.innerHTML = ["left", "right"].map((side) => {
    const raw = S.state[`${side}_abutment`];
    return `<div class="card">
      <div class="card-title"><span>${side === "left" ? "Left / Sinistra" : "Right / Destra"}</span></div>
      <div class="card-grid">
        ${numInput(raw, { entity: `${side}_abutment`, index: 0 }, "H", "Height H")}
        ${numInput(raw, { entity: `${side}_abutment`, index: 0 }, "Hf", "Foundation Hf")}
        ${numInput(raw, { entity: `${side}_abutment`, index: 0 }, "b2", "Shaft b2")}
        ${numInput(raw, { entity: `${side}_abutment`, index: 0 }, "B1f", "Footing B1f")}
        ${numInput(raw, { entity: `${side}_abutment`, index: 0 }, "B3f", "Footing B3f")}
        ${numInput(raw, { entity: `${side}_abutment`, index: 0 }, "W1f", "Wing W1f")}
        ${numInput(raw, { entity: `${side}_abutment`, index: 0 }, "W3f", "Wing W3f")}
      </div>
    </div>`;
  }).join("");
}

function renderAll() {
  renderBridge();
  renderStrips();
  renderSpans();
  renderPiers();
  renderAbutments();
}

/* --------------------------------------------------------------- live update */

function schedulePreview(delay = 220) {
  if (!$("auto-update").checked) return;
  clearTimeout(S.timer);
  S.timer = setTimeout(() => requestPreview(), delay);
}

async function requestPreview() {
  clearTimeout(S.timer);
  if (!S.state) return;
  if (S.controller) S.controller.abort();
  const controller = new AbortController();
  S.controller = controller;
  $("busy").classList.remove("hidden");
  $("error").classList.add("hidden");
  try {
    const response = await fetch("/api/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload()),
      signal: controller.signal,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    S.preview = data;
    S.materials = data.materials || {};
    $("empty-state").classList.add("hidden");
    updateStats(data.summary);
    renderLegend(data);
    requestDraw();
  } catch (error) {
    if (error.name === "AbortError") return;
    showError(error.message || String(error));
  } finally {
    if (S.controller === controller) {
      S.controller = null;
      $("busy").classList.add("hidden");
    }
  }
}

function showError(message) {
  const box = $("error");
  box.textContent = message;
  box.classList.remove("hidden");
}

function updateStats(summary) {
  $("stats").innerHTML = [
    ["Spans", summary.spans],
    ["Piers", summary.piers],
    ["Nodes", summary.nodes],
    ["Quads", summary.quads],
    ["GLRs", summary.geometry_line_restraints],
    ["Restraints", summary.restraints],
  ].map(([label, value]) => `<span>${label} <b>${esc(value)}</b></span>`).join("");
  $("selection").textContent =
    `Width ${Math.round(summary.width)} cm · drag to orbit · wheel to zoom`;
}

/* ------------------------------------------------------------------- drawing */

function requestDraw() {
  if (S.drawQueued) return;
  S.drawQueued = true;
  requestAnimationFrame(() => {
    S.drawQueued = false;
    draw();
  });
}

function resizeCanvas() {
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.round(rect.width * dpr));
  const height = Math.max(1, Math.round(rect.height * dpr));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { width: rect.width, height: rect.height };
}

function nativeColor(value) {
  const text = String(value || "#8899aa").trim();
  if (/^#[0-9a-fA-F]{8}$/.test(text)) {
    const a = parseInt(text.slice(1, 3), 16) / 255;
    const r = parseInt(text.slice(3, 5), 16);
    const g = parseInt(text.slice(5, 7), 16);
    const b = parseInt(text.slice(7, 9), 16);
    return `rgba(${r},${g},${b},${a.toFixed(3)})`;
  }
  return text;
}

function alphaColor(value, alpha) {
  const color = nativeColor(value);
  if (color.startsWith("rgba(")) return color;
  if (color.startsWith("#") && color.length === 7) {
    return `rgba(${parseInt(color.slice(1, 3), 16)},${parseInt(color.slice(3, 5), 16)},${parseInt(color.slice(5, 7), 16)},${alpha})`;
  }
  return color;
}

function projectScene(preview, width, height) {
  const nodes = new Map(preview.nodes.map((node) => [node[0], node]));
  const bounds = preview.summary.bounds;
  if (!bounds) return null;
  const lo = bounds.min;
  const hi = bounds.max;
  const cx = (lo[0] + hi[0]) / 2;
  const cy = (lo[1] + hi[1]) / 2;
  const cz = (lo[2] + hi[2]) / 2;
  const { yaw, pitch, zoom } = S.view;

  const cosYaw = Math.cos(yaw);
  const sinYaw = Math.sin(yaw);
  const cosPitch = Math.cos(pitch);
  const sinPitch = Math.sin(pitch);

  function transform(x, y, z) {
    const dx = x - cx;
    const dy = y - cy;
    const dz = z - cz;
    const x1 = cosYaw * dx - sinYaw * dy;
    const y1 = sinYaw * dx + cosYaw * dy;
    const y2 = cosPitch * y1 - sinPitch * dz;
    const z2 = sinPitch * y1 + cosPitch * dz;
    return { x: x1, y: y2, z: z2, depth: y2 };
  }

  let extentX = 1;
  let extentZ = 1;
  for (const x of [lo[0], hi[0]]) {
    for (const y of [lo[1], hi[1]]) {
      for (const z of [lo[2], hi[2]]) {
        const p = transform(x, y, z);
        extentX = Math.max(extentX, Math.abs(p.x));
        extentZ = Math.max(extentZ, Math.abs(p.z));
      }
    }
  }
  const fit = Math.min((width * 0.86) / (2 * extentX), (height * 0.84) / (2 * extentZ));
  const scale = Math.max(0.001, fit * zoom);

  function project(node) {
    const p = transform(node[1], node[2], node[3]);
    return {
      x: width / 2 + p.x * scale,
      y: height / 2 - p.z * scale,
      depth: p.y,
    };
  }
  return { nodes, project, transform, scale };
}

function colorFor(key) {
  const material = S.materials[String(key)];
  return material ? material.color : "#7c8fa4";
}

function quadColor(quad, scene) {
  if (S.options.colorMode === "group") {
    let hash = 0;
    const group = String(quad.group || "");
    for (let i = 0; i < group.length; i += 1) hash = (hash * 31 + group.charCodeAt(i)) | 0;
    return GROUPS[Math.abs(hash) % GROUPS.length];
  }
  if (S.options.colorMode === "depth") {
    const zs = quad.nodes.map((key) => scene.nodes.get(key)?.[3] ?? 0);
    const z = zs.reduce((a, b) => a + b, 0) / Math.max(1, zs.length);
    const bounds = S.preview.summary.bounds;
    const t = bounds ? (z - bounds.min[2]) / Math.max(1e-6, bounds.max[2] - bounds.min[2]) : 0.5;
    return `hsl(${200 - 160 * t} 78% ${38 + 18 * t}%)`;
  }
  return colorFor(quad.material);
}

function draw() {
  const { width, height } = resizeCanvas();
  ctx.clearRect(0, 0, width, height);
  if (!S.preview) return;
  const scene = projectScene(S.preview, width, height);
  if (!scene) return;

  const projected = [];
  for (const quad of S.preview.quads) {
    const points = quad.nodes.map((key) => scene.nodes.get(key)).filter(Boolean);
    if (points.length !== 4) continue;
    const screen = points.map((node) => scene.project(node));
    projected.push({
      quad,
      screen,
      depth: screen.reduce((sum, point) => sum + point.depth, 0) / 4,
      color: quadColor(quad, scene),
    });
  }
  projected.sort((a, b) => a.depth - b.depth);

  ctx.lineJoin = "round";
  for (const item of projected) {
    const { screen, color } = item;
    ctx.beginPath();
    ctx.moveTo(screen[0].x, screen[0].y);
    for (let i = 1; i < screen.length; i += 1) ctx.lineTo(screen[i].x, screen[i].y);
    ctx.closePath();
    if (S.options.fill) {
      ctx.fillStyle = alphaColor(color, 0.6);
      ctx.fill();
    }
    if (S.options.wire) {
      ctx.strokeStyle = alphaColor(color, 0.85);
      ctx.lineWidth = 0.65;
      ctx.stroke();
    }
  }

  if (S.options.supports) drawSupports(scene);
  if (S.options.nodes) drawNodes(scene);
  drawTriad(scene, width, height);
}

function drawSupports(scene) {
  if (!S.preview.glrs) return;
  ctx.save();
  ctx.lineWidth = 2.1;
  ctx.strokeStyle = "rgba(251, 191, 36, 0.78)";
  for (const glr of S.preview.glrs) {
    const a = scene.nodes.get(glr.nodes[0]);
    const b = scene.nodes.get(glr.nodes[1]);
    if (!a || !b) continue;
    const pa = scene.project(a);
    const pb = scene.project(b);
    ctx.beginPath();
    ctx.moveTo(pa.x, pa.y);
    ctx.lineTo(pb.x, pb.y);
    ctx.stroke();
  }
  ctx.fillStyle = "rgba(251, 113, 133, 0.9)";
  for (const restraint of S.preview.restraints || []) {
    const a = scene.nodes.get(restraint.nodes[0]);
    const b = scene.nodes.get(restraint.nodes[1]);
    if (!a || !b) continue;
    const pa = scene.project(a);
    const pb = scene.project(b);
    ctx.beginPath();
    ctx.arc((pa.x + pb.x) / 2, (pa.y + pb.y) / 2, 1.9, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

function drawNodes(scene) {
  ctx.save();
  ctx.fillStyle = "rgba(232, 240, 249, 0.8)";
  for (const node of scene.nodes.values()) {
    const p = scene.project(node);
    ctx.fillRect(p.x - 1, p.y - 1, 2, 2);
  }
  ctx.restore();
}

function drawTriad(scene, width, height) {
  const origin = scene.transform(0, 0, 0);
  const axes = [
    ["X", scene.transform(1, 0, 0), "#fb7185"],
    ["Y", scene.transform(0, 1, 0), "#34d399"],
    ["Z", scene.transform(0, 0, 1), "#38bdf8"],
  ];
  const size = Math.min(width, height) * 0.072;
  const ox = 30;
  const oy = height - 34;
  ctx.save();
  ctx.font = "10px ui-monospace, monospace";
  ctx.lineWidth = 1.4;
  for (const [label, axis, color] of axes) {
    const dx = (axis.x - origin.x) * size;
    const dy = -(axis.z - origin.z) * size;
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(ox, oy);
    ctx.lineTo(ox + dx, oy + dy);
    ctx.stroke();
    ctx.fillText(label, ox + dx * 1.18 - 3, oy + dy * 1.18 + 3);
  }
  ctx.restore();
}

/* ---------------------------------------------------------------- interaction */

canvas.addEventListener("pointerdown", (event) => {
  if (!S.preview) return;
  canvas.setPointerCapture(event.pointerId);
  S.drag = { x: event.clientX, y: event.clientY, yaw: S.view.yaw, pitch: S.view.pitch };
});

canvas.addEventListener("pointermove", (event) => {
  if (!S.drag) return;
  const dx = event.clientX - S.drag.x;
  const dy = event.clientY - S.drag.y;
  S.view.yaw = S.drag.yaw + dx * 0.008;
  S.view.pitch = Math.max(-1.52, Math.min(1.52, S.drag.pitch + dy * 0.006));
  requestDraw();
});

function endDrag(event) {
  if (!S.drag) return;
  S.drag = null;
  if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
}
canvas.addEventListener("pointerup", endDrag);
canvas.addEventListener("pointercancel", endDrag);
canvas.addEventListener("wheel", (event) => {
  if (!S.preview) return;
  event.preventDefault();
  S.view.zoom = Math.max(0.12, Math.min(10, S.view.zoom * Math.exp(-event.deltaY * 0.0012)));
  requestDraw();
}, { passive: false });
canvas.addEventListener("dblclick", () => resetView());

function resetView() {
  S.view = { yaw: -0.72, pitch: 0.4, zoom: 1 };
  requestDraw();
}

/* -------------------------------------------------------------------- events */

document.addEventListener("input", (event) => {
  const input = event.target;
  if (input.matches("[data-bind]")) {
    const path = input.dataset.bind.split(".");
    let target = S.state;
    for (let i = 0; i < path.length - 1; i += 1) target = target[path[i]];
    target[path[path.length - 1]] = number(input.value, 0);
    renderBridge();
    schedulePreview();
    return;
  }
  if (!input.dataset.entity) return;
  const entity = input.dataset.entity;
  const index = Number(input.dataset.index);
  const field = input.dataset.field;
  const value = number(input.value, 0);
  if (entity === "strip") S.state.strips[index][field] = value;
  else if (entity === "span") S.state.spans[index][field] = value;
  else if (entity === "pier") S.state.piers[index][field] = value;
  else if (entity === "left_abutment") S.state.left_abutment[field] = value;
  else if (entity === "right_abutment") S.state.right_abutment[field] = value;
  if (entity === "strip") $("width-badge").textContent = `${Math.round(totalWidth())} cm`;
  schedulePreview();
});

document.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action], button[data-add]");
  if (!button) return;
  if (button.dataset.action === "remove-strip") {
    if (S.state.strips.length <= 1) return;
    S.state.strips.splice(Number(button.dataset.index), 1);
    renderStrips();
    renderBridge();
    requestPreview();
  } else if (button.dataset.action === "remove-span") {
    if (S.state.spans.length <= 1) return;
    S.state.spans.splice(Number(button.dataset.index), 1);
    syncPiers();
    renderAll();
    requestPreview();
  } else if (button.dataset.add === "strip") {
    S.state.strips.push({ width: 50, height: 0, material_key: 0 });
    renderStrips();
    renderBridge();
    requestPreview();
  } else if (button.dataset.add === "span") {
    S.state.spans.push(defaultSpan());
    syncPiers();
    renderAll();
    requestPreview();
  }
});

$("auto-update").addEventListener("change", () => {
  if ($("auto-update").checked) requestPreview();
});

$("rebuild").addEventListener("click", () => requestPreview());
$("view-reset").addEventListener("click", resetView);
$("reset").addEventListener("click", () => load(true));

for (const [id, key] of [
  ["show-fill", "fill"],
  ["show-wire", "wire"],
  ["show-nodes", "nodes"],
  ["show-supports", "supports"],
]) {
  $(id).addEventListener("change", (event) => {
    S.options[key] = event.target.checked;
    requestDraw();
  });
}
$("color-mode").addEventListener("change", (event) => {
  S.options.colorMode = event.target.value;
  renderLegend(S.preview);
  requestDraw();
});

$("export").addEventListener("click", async () => {
  $("error").classList.add("hidden");
  try {
    const response = await fetch("/api/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload()),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || `HTTP ${response.status}`);
    }
    const blob = await response.blob();
    const disposition = response.headers.get("Content-Disposition") || "";
    const match = /filename="([^"]+)"/.exec(disposition);
    const name = match ? match[1] : "bridge.hrx";
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = name;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2500);
  } catch (error) {
    showError(`Export failed: ${error.message || error}`);
  }
});

function renderLegend(preview) {
  if (!preview) return;
  const counts = new Map();
  for (const quad of preview.quads) {
    const key = S.options.colorMode === "material" ? String(quad.material) : String(quad.group || "none");
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  const entries = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 7);
  $("legend").innerHTML = entries.map(([key, count]) => {
    let color = "#7c8fa4";
    let label = `Group ${key}`;
    if (S.options.colorMode === "material") {
      const material = S.materials[key];
      color = material ? material.color : color;
      label = material ? material.name : `Material ${key}`;
    } else if (S.options.colorMode === "group") {
      let hash = 0;
      for (let i = 0; i < key.length; i += 1) hash = (hash * 31 + key.charCodeAt(i)) | 0;
      color = GROUPS[Math.abs(hash) % GROUPS.length];
    }
    return `<div class="legend-item"><span class="swatch" style="background:${esc(nativeColor(color))}"></span>${esc(label)} <b>${count}</b></div>`;
  }).join("");
}

/* ---------------------------------------------------------------- boot / resize */

async function load(reset = false) {
  try {
    if (reset || !S.state) {
      const response = await fetch("/api/default");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      S.state = baseState(data);
      renderAll();
      resetView();
    }
    await requestPreview();
  } catch (error) {
    showError(error.message || String(error));
  }
}

window.addEventListener("resize", requestDraw);
if (typeof ResizeObserver !== "undefined") {
  new ResizeObserver(requestDraw).observe(canvas);
}
load();
