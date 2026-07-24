import { QuadViewer } from '/static/viewer-core.js';

const $ = id => document.getElementById(id);
const ui = Object.fromEntries([
  'previewButton','downloadButton','jobJsonButton','bundleButton','jsonFile','hrxFile','templateBadge','jobId','schemaVersion','modelPath','scenarioId','jobMeshEnabled','jobMeshAnalysis','jobMeshTimeout','foundationInterfaceMaterials','scouredInterfaceMaterial','requireCompleted','requireDatabase','minimumResultsBytes','metadataEditor','spanCount','bridgeWidth','meshLength','backfillHeight','backfillHeight2','backfillHeight3','zLevel','slope','inclination','autoWidth','autoOrigins','lanes','addLane','laneWidthTotal','laneCount','spanSummary','pierSummary','abutments','sequence','materials','addMaterial','defaultTolerance','defaultEigenModes','defaultIterations','analyses','addAnalysis','maxLength','nodeTolerance','arcDivisions','arcMode','interfaceNrow','archMaxLength','wallMaxLength','jsonEditor','formToJson','jsonToForm','status','nodeCount','quadCount','pointCount','viewport','message','colorBy','edges','nodes','modelPointToggle','fitView','selectionTitle','selectionText','legend','extrude','thicknessScale','thicknessScaleOut','opacity','opacityOut'
].map(id => [id, $(id)]));

const viewer = new QuadViewer(ui.viewport, {
  extrude: true,
  thicknessScale: 1,
  opacity: 0.94,
  colorBy: 'material',
  edges: true,
  nodes: false,
  modelPoints: true,
});

let state = null;
let previewData = null;
let templateInfo = { name: 'model.hrx', version: '', materials: [] };
let previewTimer = null;

const clone = value => structuredClone(value);
const setStatus = (text, type = '') => {
  ui.status.textContent = text;
  ui.status.className = `status ${type}`;
};
const showMessage = (text, error = false) => {
  ui.message.textContent = text;
  ui.message.classList.toggle('error', error);
  ui.message.classList.remove('hidden');
};
const hideMessage = () => ui.message.classList.add('hidden');
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[character]));
const numberValue = (element, fallback = undefined) => {
  const value = element.value.trim();
  if (value === '') return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};
const setInput = (element, value) => { element.value = value ?? ''; };
const materialCatalog = () => {
  const combined = new Map();
  for (const item of templateInfo.materials ?? []) combined.set(String(item.key), { key: String(item.key), name: item.name ?? `Material ${item.key}` });
  for (const item of state?.Materials ?? []) combined.set(String(item.Key), { key: String(item.Key), name: item.Name ?? `Material ${item.Key}` });
  return [...combined.values()].sort((a,b) => Number(a.key) - Number(b.key));
};
const materialSelectHtml = (selected, className = '') => `<select class="${className}">${materialCatalog().map(item => `<option value="${escapeHtml(item.key)}" ${String(selected)===String(item.key)?'selected':''}>${escapeHtml(item.key)} · ${escapeHtml(item.name)}</option>`).join('')}</select>`;

function ensureStateShape(value) {
  value.schema_version ??= '1.0';
  value.job_id ??= String(value.OutputName ?? 'generated_model').replace(/\.hrx$/i,'');
  value.model ??= { path:'model.hrx' };
  value.model.path ??= 'model.hrx';
  value.mesh ??= { enabled:false, analysis_name:'StartMesh', timeout_seconds:900 };
  value.mesh.enabled ??= false;
  value.mesh.analysis_name ??= 'StartMesh';
  value.mesh.timeout_seconds ??= 900;
  value.scour ??= { foundation_interface_materials:[], scoured_foundation_interface_material:null };
  value.scour.foundation_interface_materials ??= [];
  value.analyses ??= Object.entries(value.Analysis ?? { Modal_0:{} }).map(([name,interfaces]) => ({
    name,
    timeout_seconds:50,
    interfaces:interfaces ?? {},
    outputs:{},
  }));
  value.validation ??= { require_completed_state:true, require_results_database:true, minimum_results_bytes:1 };
  value.metadata ??= {};
  value.AnalysisParameters ??= { Defaults: {}, ByName: {} };
  value.AnalysisParameters.Defaults ??= {};
  value.AnalysisParameters.ByName ??= {};
  value.Geometry ??= {};
  value.Geometry.BridgeDefinition ??= {};
  value.Geometry.Lanes ??= [{ Name:'Backfill', Width:value.Geometry.BridgeDefinition.Width ?? 1, MaterialKey:'19' }];
  value.Geometry.Abutments ??= [
    { AbutmentKind:'Sinistra', b2:400, w2:value.Geometry.BridgeDefinition.Width ?? 1, Kz:.1, Origin:[0,0,0] },
    { AbutmentKind:'Destra', b2:400, w2:value.Geometry.BridgeDefinition.Width ?? 1, Kz:.1, Origin:[0,0,0] },
  ];
  while (value.Geometry.Abutments.length < 2) value.Geometry.Abutments.push(clone(value.Geometry.Abutments.at(-1)));
  value.Geometry.Spans ??= [{ L:1600, W:value.Geometry.BridgeDefinition.Width ?? 1, f:321, Tb:95, Tt:95 }];
  value.Geometry.Piers ??= [];
  value.Geometry.Elevations ??= { Elevations:[{ X:0, H1:500, H2:0, H3:0 }] };
  value.Geometry.Elevations.Elevations ??= [{ X:0, H1:500, H2:0, H3:0 }];
  value.Materials ??= [];
  value.Mesh ??= { NodeTolerance:1e-5, ArcDivisionMode:'observed-even' };
  value.Config ??= {};
  delete value.OutputName;
  delete value.Analysis;
  resizeSequence(value.Geometry.Spans.length, value, false);
  return value;
}

function defaultSpan(targetState = state) {
  const source = targetState?.Geometry?.Spans?.at(-1);
  return source ? clone(source) : { L:1600, W:targetState?.Geometry?.BridgeDefinition?.Width ?? 675, f:321, Tb:95, Tt:95, MaterialKey:'18', MaterialPulvinoKey:'22' };
}
function defaultPier(targetState = state) {
  const source = targetState?.Geometry?.Piers?.at(-1);
  return source ? clone(source) : { H:370, b2:320, w2:975, Hf:417, B1f:35, B3f:35, W1f:62.5, W3f:62.5, Kz:.1, Origin:[0,0,0], MaterialKey:'152', MaterialFoundationKey:'141' };
}
function resizeSequence(spanCount, target = state, render = true) {
  const count = Math.max(1, Math.min(20, Math.trunc(Number(spanCount) || 1)));
  const spans = target.Geometry.Spans;
  const piers = target.Geometry.Piers;
  while (spans.length < count) spans.push(defaultSpan(target));
  while (spans.length > count) spans.pop();
  while (piers.length < count - 1) piers.push(defaultPier(target));
  while (piers.length > count - 1) piers.pop();
  if (render && target === state) {
    applyAutomaticDimensions();
    renderGeometry();
    schedulePreview();
  }
}

function applyAutomaticDimensions() {
  if (!state) return;
  const geometry = state.Geometry;
  const laneWidth = geometry.Lanes.reduce((sum, lane) => sum + (Number(lane.Width) || 0), 0);
  if (ui.autoWidth?.checked && laneWidth > 0) geometry.BridgeDefinition.Width = laneWidth;
  const width = Number(geometry.BridgeDefinition.Width) || laneWidth || 1;
  geometry.Spans.forEach(span => { span.W = width; });
  geometry.Abutments.forEach(abutment => { if (!Number(abutment.w2)) abutment.w2 = width; });
  if (ui.autoOrigins?.checked) {
    const left = geometry.Abutments[0];
    const right = geometry.Abutments[1];
    left.AbutmentKind = 'Sinistra';
    right.AbutmentKind = 'Destra';
    left.Origin = [0, 0, 0];
    let cursor = Number(left.b2) || 0;
    geometry.Spans.forEach((span, index) => {
      cursor += Number(span.L) || 0;
      const pier = geometry.Piers[index];
      if (pier) {
        pier.Origin = [cursor + (Number(pier.b2) || 0) / 2, 0, 0];
        cursor += Number(pier.b2) || 0;
      }
    });
    right.Origin = [cursor + (Number(right.b2) || 0), 0, 0];
  }
}

function syncStaticFieldsToState() {
  state.schema_version = '1.0';
  state.job_id = ui.jobId.value.trim() || 'generated_model';
  state.model.path = ui.modelPath.value.trim() || 'model.hrx';
  state.mesh.enabled = ui.jobMeshEnabled.value === 'true';
  state.mesh.analysis_name = ui.jobMeshAnalysis.value.trim() || 'StartMesh';
  state.mesh.timeout_seconds = numberValue(ui.jobMeshTimeout, 900);
  state.scour.foundation_interface_materials = ui.foundationInterfaceMaterials.value.split(',').map(value=>value.trim()).filter(Boolean);
  setOptional(state.scour, 'scoured_foundation_interface_material', ui.scouredInterfaceMaterial.value.trim() || undefined);
  state.validation.require_completed_state = ui.requireCompleted.value === 'true';
  state.validation.require_results_database = ui.requireDatabase.value === 'true';
  state.validation.minimum_results_bytes = numberValue(ui.minimumResultsBytes, 1);
  state.metadata = JSON.parse(ui.metadataEditor.value || '{}');
  state.metadata.scenario_id = ui.scenarioId.value.trim() || state.metadata.scenario_id || state.job_id;

  const definition = state.Geometry.BridgeDefinition;
  definition.Width = numberValue(ui.bridgeWidth, definition.Width);
  definition.Nl = numberValue(ui.meshLength, definition.Nl);
  definition.Zlevel = numberValue(ui.zLevel, definition.Zlevel);
  definition.Slope = numberValue(ui.slope, definition.Slope);
  definition.InclinationAngle = numberValue(ui.inclination, definition.InclinationAngle);
  const elevation = state.Geometry.Elevations.Elevations[0];
  elevation.H1 = numberValue(ui.backfillHeight, elevation.H1);
  elevation.H2 = numberValue(ui.backfillHeight2, elevation.H2 ?? 0);
  elevation.H3 = numberValue(ui.backfillHeight3, elevation.H3 ?? 0);
  const defaults = state.AnalysisParameters.Defaults;
  setOptional(defaults, 'ConvergenceTolerance', numberValue(ui.defaultTolerance));
  setOptional(defaults, 'NumberOfEigenModes', numberValue(ui.defaultEigenModes));
  setOptional(defaults, 'MaxIterations', numberValue(ui.defaultIterations));
  setOptional(state.Mesh, 'MaxLength', numberValue(ui.maxLength));
  state.Mesh.NodeTolerance = numberValue(ui.nodeTolerance, 1e-5);
  state.Mesh.ArcDivisionMode = ui.arcMode.value || 'observed-even';
  setOptional(state.Mesh, 'ArcDivisions', numberValue(ui.arcDivisions));
  setOptional(state.Config, 'InterfaceNrow', numberValue(ui.interfaceNrow));
  setOptional(state.Config, 'ArcoMesherQuadLengthMax', numberValue(ui.archMaxLength));
  setOptional(state.Config, 'WallMesherQuadLengthMax', numberValue(ui.wallMaxLength));
  applyAutomaticDimensions();
}

function setOptional(object, key, value) {
  if (value === undefined || value === null || value === '') delete object[key];
  else object[key] = value;
}

function renderAll() {
  renderStaticFields();
  renderGeometry();
  renderMaterials();
  renderAnalyses();
  renderSettings();
  refreshJsonEditor();
}

function renderStaticFields() {
  const definition = state.Geometry.BridgeDefinition;
  setInput(ui.jobId, state.job_id);
  setInput(ui.schemaVersion, state.schema_version);
  setInput(ui.modelPath, state.model.path);
  setInput(ui.scenarioId, state.metadata.scenario_id ?? state.job_id);
  ui.jobMeshEnabled.value = String(Boolean(state.mesh.enabled));
  setInput(ui.jobMeshAnalysis, state.mesh.analysis_name);
  setInput(ui.jobMeshTimeout, state.mesh.timeout_seconds);
  setInput(ui.foundationInterfaceMaterials, (state.scour.foundation_interface_materials ?? []).join(', '));
  setInput(ui.scouredInterfaceMaterial, state.scour.scoured_foundation_interface_material);
  ui.requireCompleted.value = String(Boolean(state.validation.require_completed_state));
  ui.requireDatabase.value = String(Boolean(state.validation.require_results_database));
  setInput(ui.minimumResultsBytes, state.validation.minimum_results_bytes);
  ui.metadataEditor.value = JSON.stringify(state.metadata ?? {}, null, 2);
  setInput(ui.spanCount, state.Geometry.Spans.length);
  setInput(ui.bridgeWidth, definition.Width);
  setInput(ui.meshLength, definition.Nl);
  setInput(ui.backfillHeight, state.Geometry.Elevations.Elevations[0]?.H1);
  setInput(ui.backfillHeight2, state.Geometry.Elevations.Elevations[0]?.H2 ?? 0);
  setInput(ui.backfillHeight3, state.Geometry.Elevations.Elevations[0]?.H3 ?? 0);
  setInput(ui.zLevel, definition.Zlevel);
  setInput(ui.slope, definition.Slope);
  setInput(ui.inclination, definition.InclinationAngle);
}

function renderGeometry() {
  renderLanes();
  renderAbutments();
  renderSequence();
  const laneWidth = state.Geometry.Lanes.reduce((sum,lane)=>sum+(Number(lane.Width)||0),0);
  ui.laneWidthTotal.textContent = Number(laneWidth.toFixed(6)).toLocaleString();
  ui.laneCount.textContent = state.Geometry.Lanes.length.toLocaleString();
  ui.spanSummary.textContent = state.Geometry.Spans.length.toLocaleString();
  ui.pierSummary.textContent = state.Geometry.Piers.length.toLocaleString();
  setInput(ui.bridgeWidth, state.Geometry.BridgeDefinition.Width);
}

function renderLanes() {
  ui.lanes.replaceChildren();
  state.Geometry.Lanes.forEach((lane, index) => {
    const row = document.createElement('div');
    row.className = 'lane-row card';
    row.innerHTML = `<div class="field name"><label>Name</label><input class="lane-name" type="text" value="${escapeHtml(lane.Name)}"></div><div class="field"><label>Width</label><input class="lane-width" type="number" min="0.0001" step="1" value="${lane.Width}"></div><div class="field"><label>Wall height</label><input class="lane-height" type="number" min="0" step="1" value="${lane.Height ?? 0}"></div><div class="field"><label>Material</label>${materialSelectHtml(lane.MaterialKey,'lane-material')}</div><button class="danger remove-lane" title="Remove lane">×</button>`;
    row.querySelector('.lane-name').addEventListener('input', event => { lane.Name = event.target.value; schedulePreview(); });
    row.querySelector('.lane-width').addEventListener('input', event => { lane.Width = Number(event.target.value) || 0; applyAutomaticDimensions(); updateGeometrySummaryOnly(); schedulePreview(); });
    row.querySelector('.lane-height').addEventListener('input', event => { lane.Height = Number(event.target.value) || 0; schedulePreview(); });
    row.querySelector('.lane-material').addEventListener('change', event => { lane.MaterialKey = event.target.value; schedulePreview(); });
    row.querySelector('.remove-lane').addEventListener('click', () => { if (state.Geometry.Lanes.length <= 1) return; state.Geometry.Lanes.splice(index,1); applyAutomaticDimensions(); renderGeometry(); schedulePreview(); });
    ui.lanes.append(row);
  });
}

function updateGeometrySummaryOnly() {
  const laneWidth = state.Geometry.Lanes.reduce((sum,lane)=>sum+(Number(lane.Width)||0),0);
  ui.laneWidthTotal.textContent = Number(laneWidth.toFixed(6)).toLocaleString();
  if (ui.autoWidth.checked) setInput(ui.bridgeWidth, state.Geometry.BridgeDefinition.Width);
}

function supportCardHtml(support, label, index) {
  return `<div class="card"><div class="card-head"><h3>${label}</h3><span class="badge">${escapeHtml(support.AbutmentKind ?? '')}</span></div><div class="grid two">
    <div class="field"><label>Longitudinal length b2</label><input data-key="b2" type="number" step="1" value="${support.b2 ?? ''}"></div>
    <div class="field"><label>Transverse width w2</label><input data-key="w2" type="number" step="1" value="${support.w2 ?? ''}"></div>
    <div class="field"><label>Height H</label><input data-key="H" type="number" step="1" value="${support.H ?? ''}"></div>
    <div class="field"><label>Vertical stiffness Kz</label><input data-key="Kz" type="number" step="0.01" value="${support.Kz ?? ''}"></div>
    <div class="field"><label>Hsp1</label><input data-key="Hsp1" type="number" step="1" value="${support.Hsp1 ?? ''}"></div>
    <div class="field"><label>Hsp2</label><input data-key="Hsp2" type="number" step="1" value="${support.Hsp2 ?? ''}"></div>
    <div class="field"><label>Material</label>${materialSelectHtml(support.MaterialKey ?? '18','support-material')}</div>
    <div class="field"><label>Origin X</label><input class="support-origin" type="number" value="${support.Origin?.[0] ?? ''}" ${ui.autoOrigins.checked?'readonly':''}></div>
  </div></div>`;
}

function renderAbutments() {
  ui.abutments.innerHTML = state.Geometry.Abutments.map((support,index)=>supportCardHtml(support,index===0?'Left abutment':'Right abutment',index)).join('');
  [...ui.abutments.children].forEach((card,index) => {
    const support = state.Geometry.Abutments[index];
    card.querySelectorAll('input[data-key]').forEach(input => input.addEventListener('input', event => { support[event.target.dataset.key] = Number(event.target.value) || 0; applyAutomaticDimensions(); if (ui.autoOrigins.checked) renderAbutments(); schedulePreview(); }));
    card.querySelector('.support-material').addEventListener('change', event => { support.MaterialKey = event.target.value; schedulePreview(); });
    card.querySelector('.support-origin').addEventListener('input', event => { support.Origin = [Number(event.target.value)||0,0,0]; schedulePreview(); });
  });
}

function renderSequence() {
  ui.sequence.replaceChildren();
  state.Geometry.Spans.forEach((span,index) => {
    const spanCard = document.createElement('div');
    spanCard.className = 'card sequence-card span';
    spanCard.innerHTML = `<div class="card-head"><h3>Span ${index+1}</h3><span class="badge">arch</span></div><div class="grid four">
      <div class="field"><label>Clear length L</label><input data-key="L" type="number" min="0.001" step="1" value="${span.L ?? ''}"></div>
      <div class="field"><label>Rise f</label><input data-key="f" type="number" min="0.001" step="1" value="${span.f ?? ''}"></div>
      <div class="field"><label>Ring thickness Tb</label><input data-key="Tb" type="number" min="0.001" step="1" value="${span.Tb ?? ''}"></div>
      <div class="field"><label>Top thickness Tt</label><input data-key="Tt" type="number" min="0.001" step="1" value="${span.Tt ?? ''}"></div>
      <div class="field"><label>Arch material</label>${materialSelectHtml(span.MaterialKey ?? '18','span-material')}</div>
      <div class="field"><label>Pier-cap material</label>${materialSelectHtml(span.MaterialPulvinoKey ?? '22','cap-material')}</div>
      <div class="field"><label>Geometry mode</label><select class="span-circular"><option value="true" ${String(span.Circolare ?? true)==='true'?'selected':''}>Circular L/f</option><option value="false" ${String(span.Circolare)==='false'?'selected':''}>HiStrA non-circular flag</option></select></div>
    </div>`;
    spanCard.querySelectorAll('input[data-key]').forEach(input => input.addEventListener('input', event => { span[event.target.dataset.key] = Number(event.target.value)||0; applyAutomaticDimensions(); schedulePreview(); }));
    spanCard.querySelector('.span-material').addEventListener('change', event => { span.MaterialKey = event.target.value; schedulePreview(); });
    spanCard.querySelector('.cap-material').addEventListener('change', event => { span.MaterialPulvinoKey = event.target.value; schedulePreview(); });
    spanCard.querySelector('.span-circular').addEventListener('change', event => { span.Circolare = event.target.value === 'true'; schedulePreview(); });
    ui.sequence.append(spanCard);

    const pier = state.Geometry.Piers[index];
    if (!pier) return;
    const pierCard = document.createElement('div');
    pierCard.className = 'card sequence-card pier';
    pierCard.innerHTML = `<div class="card-head"><h3>Pier ${index+1}</h3><span class="badge">support</span></div><div class="grid four">
      <div class="field"><label>Height H</label><input data-key="H" type="number" step="1" value="${pier.H ?? ''}"></div>
      <div class="field"><label>Longitudinal width b2</label><input data-key="b2" type="number" step="1" value="${pier.b2 ?? ''}"></div>
      <div class="field"><label>Transverse thickness w2</label><input data-key="w2" type="number" step="1" value="${pier.w2 ?? ''}"></div>
      <div class="field"><label>Longitudinal left variation b1</label><input data-key="b1" type="number" min="0" step="1" value="${pier.b1 ?? 0}"></div>
      <div class="field"><label>Longitudinal right variation b3</label><input data-key="b3" type="number" min="0" step="1" value="${pier.b3 ?? 0}"></div>
      <div class="field"><label>Transverse +Y variation w1</label><input data-key="w1" type="number" min="0" step="1" value="${pier.w1 ?? 0}"></div>
      <div class="field"><label>Transverse −Y variation w3</label><input data-key="w3" type="number" min="0" step="1" value="${pier.w3 ?? 0}"></div>
      <div class="field"><label>Vertical alignment</label><select class="pier-alignment"><option value="Top" ${String(pier.VerticalAllignment ?? 'Top')==='Top'?'selected':''}>Top</option><option value="Center" ${String(pier.VerticalAllignment)==='Center'?'selected':''}>Center</option><option value="Bottom" ${String(pier.VerticalAllignment)==='Bottom'?'selected':''}>Bottom</option></select></div>
      <div class="field"><label>Foundation height Hf</label><input data-key="Hf" type="number" step="1" value="${pier.Hf ?? ''}"></div>
      <div class="field"><label>Foundation left B1f</label><input data-key="B1f" type="number" step="1" value="${pier.B1f ?? ''}"></div>
      <div class="field"><label>Foundation right B3f</label><input data-key="B3f" type="number" step="1" value="${pier.B3f ?? ''}"></div>
      <div class="field"><label>Foundation +Y W1f</label><input data-key="W1f" type="number" step="1" value="${pier.W1f ?? ''}"></div>
      <div class="field"><label>Foundation −Y W3f</label><input data-key="W3f" type="number" step="1" value="${pier.W3f ?? ''}"></div>
      <div class="field"><label>Pier material</label>${materialSelectHtml(pier.MaterialKey ?? '152','pier-material')}</div>
      <div class="field"><label>Foundation material</label>${materialSelectHtml(pier.MaterialFoundationKey ?? '141','foundation-material')}</div>
      <div class="field"><label>Origin X</label><input class="pier-origin" type="number" value="${pier.Origin?.[0] ?? ''}" ${ui.autoOrigins.checked?'readonly':''}></div>
      <div class="field"><label>Kz</label><input data-key="Kz" type="number" step="0.01" value="${pier.Kz ?? ''}"></div>
    </div>`;
    pierCard.querySelectorAll('input[data-key]').forEach(input => input.addEventListener('input', event => { pier[event.target.dataset.key] = Number(event.target.value)||0; applyAutomaticDimensions(); if (ui.autoOrigins.checked && event.target.dataset.key==='b2') renderGeometry(); schedulePreview(); }));
    pierCard.querySelector('.pier-material').addEventListener('change', event => { pier.MaterialKey = event.target.value; schedulePreview(); });
    pierCard.querySelector('.foundation-material').addEventListener('change', event => { pier.MaterialFoundationKey = event.target.value; schedulePreview(); });
    pierCard.querySelector('.pier-alignment').addEventListener('change', event => { pier.VerticalAllignment = event.target.value; schedulePreview(); });
    pierCard.querySelector('.pier-origin').addEventListener('input', event => { pier.Origin = [Number(event.target.value)||0,0,0]; schedulePreview(); });
    ui.sequence.append(pierCard);
  });
}

function renderMaterials() {
  ui.materials.replaceChildren();
  state.Materials.forEach((material,index) => {
    const details = document.createElement('details');
    details.className = 'card material-card';
    const properties = Object.entries(material).filter(([key]) => !['Key','Name'].includes(key));
    details.innerHTML = `<summary><div class="material-summary"><strong>${escapeHtml(material.Key)} · ${escapeHtml(material.Name)}</strong><span class="badge">${properties.length} properties</span></div></summary><div class="grid two" style="margin-top:10px"><div class="field"><label>Template key</label>${materialSelectHtml(material.Key,'material-key')}</div><div class="field"><label>Name (verified)</label><input class="material-name" type="text" readonly value="${escapeHtml(material.Name)}"></div></div><div class="properties">${properties.map(([key,value])=>`<div class="field"><label>${escapeHtml(key)}</label><input data-property="${escapeHtml(key)}" type="text" value="${escapeHtml(value)}"></div>`).join('')}</div><div style="display:flex;justify-content:flex-end;margin-top:9px"><button class="danger remove-material" style="width:auto">Remove patch</button></div>`;
    details.querySelector('.material-key').addEventListener('change', event => {
      const catalogItem = materialCatalog().find(item => item.key === event.target.value);
      material.Key = event.target.value;
      if (catalogItem) material.Name = catalogItem.name;
      renderMaterials();
      renderGeometry();
      schedulePreview();
    });
    details.querySelectorAll('[data-property]').forEach(input => input.addEventListener('input', event => { material[event.target.dataset.property] = event.target.value; schedulePreview(); }));
    details.querySelector('.remove-material').addEventListener('click', event => { event.preventDefault(); state.Materials.splice(index,1); renderMaterials(); renderGeometry(); schedulePreview(); });
    ui.materials.append(details);
  });
}

function renderAnalyses() {
  const defaults = state.AnalysisParameters.Defaults;
  setInput(ui.defaultTolerance, defaults.ConvergenceTolerance);
  setInput(ui.defaultEigenModes, defaults.NumberOfEigenModes);
  setInput(ui.defaultIterations, defaults.MaxIterations);
  ui.analyses.replaceChildren();
  state.analyses.forEach((analysis,index) => {
    analysis.interfaces ??= {};
    analysis.outputs ??= {};
    analysis.timeout_seconds ??= 50;
    const card = document.createElement('details');
    card.className = 'card analysis-card';
    card.open = index === 0;
    card.innerHTML = `<summary><div class="material-summary"><strong>${escapeHtml(analysis.name)}</strong><span class="badge">queued</span></div></summary>
      <div class="analysis-row"><div class="field name"><label>Analysis name</label><input class="analysis-name" type="text" value="${escapeHtml(analysis.name)}"></div><div class="field"><label>Timeout (s)</label><input class="analysis-timeout" type="number" min="1" step="1" value="${analysis.timeout_seconds}"></div><div class="field"><label>Tolerance</label><input class="analysis-tolerance" type="number" min="0.0000001" step="0.001" value="${analysis.ConvergenceTolerance ?? ''}"></div><button class="danger remove-analysis">×</button></div>
      <div class="grid two" style="margin-top:8px"><div class="field"><label>Eigen modes</label><input class="analysis-modes" type="number" min="1" step="1" value="${analysis.NumberOfEigenModes ?? ''}"></div><div></div></div>
      <div class="field" style="margin-top:8px"><label>Interface deletion payload</label><textarea class="interfaces-editor scenario-editor" spellcheck="false">${escapeHtml(JSON.stringify(analysis.interfaces,null,2))}</textarea></div>
      <div class="field" style="margin-top:8px"><label>Requested outputs</label><textarea class="outputs-editor scenario-editor" spellcheck="false">${escapeHtml(JSON.stringify(analysis.outputs,null,2))}</textarea></div>`;
    card.querySelector('.analysis-name').addEventListener('change', event => {
      const newName = event.target.value.trim();
      if (!newName || state.analyses.some((item,i)=>i!==index && item.name===newName)) { setStatus(`Analysis name ${newName || '(empty)'} is invalid or duplicated.`,'bad'); renderAnalyses(); return; }
      analysis.name = newName; schedulePreview();
    });
    card.querySelector('.analysis-timeout').addEventListener('input', event => { analysis.timeout_seconds = numberValue(event.target,50); schedulePreview(); });
    card.querySelector('.analysis-tolerance').addEventListener('input', event => { setOptional(analysis,'ConvergenceTolerance',numberValue(event.target)); schedulePreview(); });
    card.querySelector('.analysis-modes').addEventListener('input', event => { setOptional(analysis,'NumberOfEigenModes',numberValue(event.target)); schedulePreview(); });
    card.querySelector('.interfaces-editor').addEventListener('change', event => { try { analysis.interfaces = JSON.parse(event.target.value || '{}'); setStatus(`Interfaces for ${analysis.name} are valid JSON.`,'good'); schedulePreview(); } catch(error) { setStatus(`Interfaces for ${analysis.name}: ${error.message}`,'bad'); } });
    card.querySelector('.outputs-editor').addEventListener('change', event => { try { analysis.outputs = JSON.parse(event.target.value || '{}'); setStatus(`Outputs for ${analysis.name} are valid JSON.`,'good'); schedulePreview(); } catch(error) { setStatus(`Outputs for ${analysis.name}: ${error.message}`,'bad'); } });
    card.querySelector('.remove-analysis').addEventListener('click', event => { event.preventDefault(); if (state.analyses.length <= 1) return; state.analyses.splice(index,1); renderAnalyses(); schedulePreview(); });
    ui.analyses.append(card);
  });
}

function renderSettings() {
  setInput(ui.maxLength,state.Mesh.MaxLength);
  setInput(ui.nodeTolerance,state.Mesh.NodeTolerance ?? 1e-5);
  setInput(ui.arcDivisions,state.Mesh.ArcDivisions);
  ui.arcMode.value=state.Mesh.ArcDivisionMode ?? 'observed-even';
  setInput(ui.interfaceNrow,state.Config.InterfaceNrow);
  setInput(ui.archMaxLength,state.Config.ArcoMesherQuadLengthMax);
  setInput(ui.wallMaxLength,state.Config.WallMesherQuadLengthMax);
}

function refreshJsonEditor() {
  if (!state) return;
  syncStaticFieldsToState();
  ui.jsonEditor.value = JSON.stringify(state,null,2);
}

function validateClientRequest(request) {
  const errors = [];
  const geometry = request.Geometry;
  if (geometry.Spans.length !== geometry.Piers.length + 1) errors.push('The number of spans must equal the number of piers plus one.');
  if (geometry.Abutments.length !== 2) errors.push('Exactly two abutments are required.');
  const laneWidth = geometry.Lanes.reduce((sum,lane)=>sum+(Number(lane.Width)||0),0);
  if (Math.abs(laneWidth - Number(geometry.BridgeDefinition.Width)) > 1e-5) errors.push(`Lane widths total ${laneWidth}, but bridge width is ${geometry.BridgeDefinition.Width}.`);
  if (!request.analyses?.length) errors.push('At least one analysis is required.');
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(request.job_id || '')) errors.push('Job ID contains invalid characters.');
  if (request.analyses && new Set(request.analyses.map(item=>item.name)).size !== request.analyses.length) errors.push('Analysis names must be unique.');
  if (errors.length) throw new Error(errors.join('\n'));
}

function getRequestFromForm() {
  syncStaticFieldsToState();
  const request = clone(state);
  validateClientRequest(request);
  return request;
}

async function api(path, body) {
  const response = await fetch(path,{ method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) });
  if (!response.ok) {
    let payload;
    try { payload = await response.json(); } catch { payload = { detail: await response.text() }; }
    const detail = payload.detail;
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail ?? payload,null,2));
  }
  return response;
}

async function apiUpload(path, file) {
  const form = new FormData();
  form.append('file', file, file.name);
  const response = await fetch(path,{ method:'POST', body:form });
  if (!response.ok) {
    let payload;
    try { payload = await response.json(); } catch { payload = { detail: await response.text() }; }
    const detail = payload.detail;
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail ?? payload,null,2));
  }
  return response;
}

function loadRequestState(payload, sourceName) {
  state = ensureStateShape(payload);
  const imported = Boolean(state.model?.imported);
  ui.autoWidth.checked = !imported;
  ui.autoOrigins.checked = !imported;
  if (!imported) applyAutomaticDimensions();
  renderAll();
  previewData = null;
  ui.downloadButton.disabled = true;
  ui.jobJsonButton.disabled = true;
  ui.bundleButton.disabled = true;
  showMessage(imported
    ? 'The imported HiStrA geometry will be preserved until a geometry or mesh field is edited.'
    : 'Generate a server preview to inspect the imported request.');
  setStatus(`Loaded ${sourceName}.`,'good');
}

async function generatePreview({ automatic = false } = {}) {
  if (!state) return;
  try {
    if (!automatic) ui.previewButton.disabled = true;
    setStatus(automatic ? 'Updating server preview…' : 'Generating mesh on the Python server…');
    const request = getRequestFromForm();
    const response = await api('/api/jobs/preview',request);
    previewData = await response.json();
    viewer.loadPreview(previewData.mesh,{ name:request.job_id || 'Server preview', modelPoints:previewData.model_points });
    hideMessage();
    ui.downloadButton.disabled = false;
    ui.jobJsonButton.disabled = false;
    ui.bundleButton.disabled = false;
    ui.nodeCount.textContent = previewData.mesh.nodes.length.toLocaleString();
    ui.quadCount.textContent = previewData.mesh.quads.length.toLocaleString();
    ui.pointCount.textContent = previewData.model_points.length.toLocaleString();
    const warnings = previewData.warnings?.length ? `\n${previewData.warnings.join('\n')}` : '';
    setStatus(`Preview generated successfully.${warnings}`,'good');
    refreshJsonEditor();
  } catch(error) {
    if (!automatic) showMessage(error instanceof Error ? error.message : String(error),true);
    setStatus(error instanceof Error ? error.message : String(error),'bad');
    ui.downloadButton.disabled = true;
    ui.jobJsonButton.disabled = true;
    ui.bundleButton.disabled = true;
  } finally {
    ui.previewButton.disabled = false;
  }
}

function schedulePreview() {
  if (!previewData) return;
  clearTimeout(previewTimer);
  previewTimer = setTimeout(() => generatePreview({ automatic:true }),650);
}

async function downloadArtifact(path, fallbackName, statusLabel) {
  const request = getRequestFromForm();
  const response = await api(path,request);
  const blob = await response.blob();
  const disposition = response.headers.get('Content-Disposition') ?? '';
  const match = disposition.match(/filename\*=UTF-8''([^;]+)/);
  const name = match ? decodeURIComponent(match[1]) : fallbackName;
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url),1000);
  setStatus(`${statusLabel}: ${name}`,'good');
}

async function downloadHrx() {
  try {
    ui.downloadButton.disabled = true;
    setStatus('Building and validating the complete HRX on the Python server…');
    await downloadArtifact('/api/jobs/generate/hrx',`${state.job_id}.hrx`,'HRX generated and validated');
  } catch(error) { setStatus(error instanceof Error ? error.message : String(error),'bad'); }
  finally { ui.downloadButton.disabled = false; }
}

async function downloadJobJson() {
  try {
    ui.jobJsonButton.disabled = true;
    setStatus('Generating the runner-ready work-job JSON…');
    await downloadArtifact('/api/jobs/generate/json',`${state.job_id}.json`,'Work job generated');
  } catch(error) { setStatus(error instanceof Error ? error.message : String(error),'bad'); }
  finally { ui.jobJsonButton.disabled = false; }
}

async function downloadBundle() {
  try {
    ui.bundleButton.disabled = true;
    setStatus('Generating HRX, work-job JSON and validation report…');
    await downloadArtifact('/api/jobs/generate/bundle',`${state.job_id}.zip`,'Work-job bundle generated');
  } catch(error) { setStatus(error instanceof Error ? error.message : String(error),'bad'); }
  finally { ui.bundleButton.disabled = false; }
}

function bindStaticEvents() {
  ui.previewButton.addEventListener('click',()=>generatePreview());
  ui.downloadButton.addEventListener('click',downloadHrx);
  ui.jobJsonButton.addEventListener('click',downloadJobJson);
  ui.bundleButton.addEventListener('click',downloadBundle);
  ui.spanCount.addEventListener('change',()=>resizeSequence(numberValue(ui.spanCount,1)));
  for (const control of [ui.jobId,ui.modelPath,ui.scenarioId,ui.jobMeshEnabled,ui.jobMeshAnalysis,ui.jobMeshTimeout,ui.foundationInterfaceMaterials,ui.scouredInterfaceMaterial,ui.requireCompleted,ui.requireDatabase,ui.minimumResultsBytes,ui.metadataEditor,ui.bridgeWidth,ui.meshLength,ui.backfillHeight,ui.zLevel,ui.slope,ui.inclination,ui.defaultTolerance,ui.defaultEigenModes,ui.defaultIterations,ui.maxLength,ui.nodeTolerance,ui.arcDivisions,ui.arcMode,ui.interfaceNrow,ui.archMaxLength,ui.wallMaxLength]) control.addEventListener('change',schedulePreview);
  ui.autoWidth.addEventListener('change',()=>{applyAutomaticDimensions();renderGeometry();schedulePreview()});
  ui.autoOrigins.addEventListener('change',()=>{applyAutomaticDimensions();renderGeometry();schedulePreview()});
  ui.addLane.addEventListener('click',()=>{state.Geometry.Lanes.push({Name:`Lane_${state.Geometry.Lanes.length+1}`,Width:100,Height:0,MaterialKey:'19'});applyAutomaticDimensions();renderGeometry();schedulePreview()});
  ui.addMaterial.addEventListener('click',()=>{
    const used = new Set(state.Materials.map(item=>String(item.Key)));
    const item = materialCatalog().find(entry=>!used.has(entry.key)) ?? materialCatalog()[0];
    if (!item) return;
    state.Materials.push({Key:item.key,Name:item.name});renderMaterials();renderGeometry();schedulePreview();
  });
  ui.addAnalysis.addEventListener('click',()=>{let index=1,name=`Analysis_${index}`;while(state.analyses.some(item=>item.name===name))name=`Analysis_${++index}`;state.analyses.push({name,timeout_seconds:50,interfaces:{},outputs:{}});renderAnalyses();schedulePreview()});
  ui.formToJson.addEventListener('click',refreshJsonEditor);
  ui.jsonToForm.addEventListener('click',()=>{try{state=ensureStateShape(JSON.parse(ui.jsonEditor.value));applyAutomaticDimensions();renderAll();setStatus('Advanced JSON applied to the form.','good');schedulePreview()}catch(error){setStatus(error.message,'bad')}});
  ui.jsonFile.addEventListener('change',async()=>{const file=ui.jsonFile.files?.[0];if(!file)return;try{loadRequestState(JSON.parse(await file.text()),file.name)}catch(error){setStatus(error.message,'bad')}});
  ui.hrxFile.addEventListener('change',async()=>{
    const file=ui.hrxFile.files?.[0];
    if(!file)return;
    try {
      setStatus(`Importing ${file.name} and extracting WizardData…`);
      const response=await apiUpload('/api/jobs/import',file);
      loadRequestState(await response.json(),file.name);
      await generatePreview();
    } catch(error) {
      setStatus(error instanceof Error?error.message:String(error),'bad');
    } finally {
      ui.hrxFile.value='';
    }
  });
  document.querySelectorAll('[data-tab]').forEach(button=>button.addEventListener('click',()=>{
    document.querySelectorAll('[data-tab]').forEach(item=>item.classList.toggle('active',item===button));
    document.querySelectorAll('.tab-panel').forEach(panel=>panel.classList.toggle('active',panel.id===`tab-${button.dataset.tab}`));
    if (button.dataset.tab==='json') refreshJsonEditor();
  }));
  document.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>viewer.setView(button.dataset.view)));
  ui.fitView.addEventListener('click',()=>viewer.fit());
  ui.colorBy.addEventListener('change',()=>viewer.setOptions({colorBy:ui.colorBy.value}));
  ui.edges.addEventListener('change',()=>viewer.setOptions({edges:ui.edges.checked},{rebuild:false}));
  ui.nodes.addEventListener('change',()=>viewer.setOptions({nodes:ui.nodes.checked},{rebuild:false}));
  ui.modelPointToggle.addEventListener('change',()=>viewer.setOptions({modelPoints:ui.modelPointToggle.checked},{rebuild:false}));
  ui.extrude.addEventListener('change',()=>viewer.setOptions({extrude:ui.extrude.checked}));
  ui.thicknessScale.addEventListener('input',()=>{ui.thicknessScaleOut.value=Number(ui.thicknessScale.value).toFixed(2);viewer.setOptions({thicknessScale:Number(ui.thicknessScale.value)})});
  ui.opacity.addEventListener('input',()=>{ui.opacityOut.value=Number(ui.opacity.value).toFixed(2);viewer.setOptions({opacity:Number(ui.opacity.value)},{rebuild:false})});
}

viewer.on('selection',selection=>{
  if (!selection) { ui.selectionTitle.textContent='Viewer'; ui.selectionText.textContent='Orbit, pan and zoom use the same interaction model as the standalone quad viewer.'; return; }
  const q=selection.quad;
  ui.selectionTitle.textContent=`Quad ${q.key}`;
  ui.selectionText.textContent=`${q.group} · material ${q.material} · lane ${q.lane} · thickness ${Number(q.thicknesses[0]).toFixed(3)} · nodes ${q.nodeKeys.join(', ')}`;
});
viewer.on('legend',entries=>{
  ui.legend.replaceChildren();
  for (const entry of entries.slice(0,50)) {
    const row=document.createElement('div');row.className='legend-row';row.innerHTML=`<i style="background:${entry.color}"></i><span title="${escapeHtml(entry.label)}">${escapeHtml(entry.label)}</span>`;ui.legend.append(row);
  }
  ui.legend.hidden = !entries.length;
});

async function initialize() {
  bindStaticEvents();
  try {
    const [exampleResponse,templateResponse] = await Promise.all([fetch('/static/example_input.json'),fetch('/api/template')]);
    if (!exampleResponse.ok || !templateResponse.ok) throw new Error('Could not load initial server data.');
    state = ensureStateShape(await exampleResponse.json());
    templateInfo = await templateResponse.json();
    ui.templateBadge.textContent = `${templateInfo.name} · ${templateInfo.version}`;
    applyAutomaticDimensions();
    renderAll();
    setStatus('Example request loaded. Generate the preview when ready.');
  } catch(error) {
    setStatus(error instanceof Error ? error.message : String(error),'bad');
  }
}

initialize();
