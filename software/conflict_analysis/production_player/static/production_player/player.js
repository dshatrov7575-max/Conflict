/* G7 composes verified Foundation HTTP only. No domain persistence or repair. */
(() => {
  "use strict";
  const app = document.getElementById("player-app");
  if (!app) return;
  const API = "/api/foundation/player/";
  const STORAGE_KEY = "conflict-analysis-player:layout:v1";
  const LAYOUT_VERSION = "PLAYER_LAYOUT_V1";
  const DEFAULT_LAYOUT = Object.freeze({version: LAYOUT_VERSION, left: 272, right: 320, activeRightTab: "help"});
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
  const SHA = /^[0-9a-f]{64}$/;
  const WINDOW_SIZE = 100;
  const encoder = new TextEncoder();
  const memory = {project: null, definition: null, workspace: null, definitions: [], workspaces: [], slices: [], experiments: [], layout: {...DEFAULT_LAYOUT}, treeKind: "actors", treeRows: [], treeOffset: 0, treeSelection: 0, focus: "workspace", slice: null, operation: null, operationKind: null, helpEpoch: 0, loading: false};
  const $ = (id) => document.getElementById(id);
  const text = (id, value) => {const node = $(id); if (node) node.textContent = value == null ? "—" : String(value);};
  const visible = (id, show) => {const node = $(id); if (node) node.hidden = !show;};
  const blocked = () => memory.operation && ["busy", "unknown"].includes(memory.operation.state);
  const complete = () => memory.workspace?.assessment_projection_status === "COMPLETE" && SHA.test(memory.workspace?.assessment_projection_sha256 || "") && !!memory.definition;
  const uuid = (value) => {if (!UUID.test(value || "")) throw new Error("PLAYER_IDENTITY_INVALID"); return value;};
  const hash = async (source) => Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", encoder.encode(source))), (x) => x.toString(16).padStart(2, "0")).join("");
  const compareKeys = (a, b) => {const x = Array.from(a, c => c.codePointAt(0)), y = Array.from(b, c => c.codePointAt(0)); for (let i = 0; i < Math.min(x.length, y.length); i += 1) {if (x[i] !== y[i]) return x[i] - y[i];} return x.length - y.length;};

  // Preserve number tokens for checksum verification: binary JS numbers must not
  // round an arbitrary manifest decimal or reinterpret a persisted receipt.
  function parseExact(source) {
    let offset = 0;
    const fail = () => {throw new Error("PLAYER_RESPONSE_JSON_INVALID");};
    const whitespace = () => {while (/[\x20\x09\x0a\x0d]/.test(source[offset] || "")) offset += 1;};
    const string = () => {
      const start = offset;
      if (source[offset++] !== '"') fail();
      while (offset < source.length) {
        const character = source[offset++];
        if (character === '"') return {kind: "string", value: JSON.parse(source.slice(start, offset))};
        if (character.charCodeAt(0) < 32) fail();
        if (character === "\\") {
          const escaped = source[offset++];
          if (escaped === "u") {if (!/^[0-9a-fA-F]{4}$/.test(source.slice(offset, offset + 4))) fail(); offset += 4;}
          else if (!'"\\/bfnrt'.includes(escaped || "\0")) fail();
        }
      }
      return fail();
    };
    const value = () => {
      whitespace();
      if (source[offset] === '"') return string();
      if (source[offset] === "{") {
        offset += 1; whitespace(); const entries = [], seen = new Set();
        if (source[offset] === "}") {offset += 1; return {kind: "object", entries};}
        while (offset < source.length) {
          whitespace(); const key = string().value;
          if (seen.has(key)) fail(); seen.add(key); whitespace(); if (source[offset++] !== ":") fail();
          entries.push([key, value()]); whitespace(); const next = source[offset++];
          if (next === "}") return {kind: "object", entries}; if (next !== ",") fail();
        }
        return fail();
      }
      if (source[offset] === "[") {
        offset += 1; whitespace(); const items = [];
        if (source[offset] === "]") {offset += 1; return {kind: "array", items};}
        while (offset < source.length) {items.push(value()); whitespace(); const next = source[offset++]; if (next === "]") return {kind: "array", items}; if (next !== ",") fail();}
        return fail();
      }
      const match = source.slice(offset).match(/^(?:true|false|null|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)/);
      if (!match) return fail(); offset += match[0].length; return {kind: "raw", raw: match[0]};
    };
    const syntax = value(); whitespace(); if (offset !== source.length) fail();
    return {value: JSON.parse(source), syntax};
  }
  function canonical(node, omitted = null) {
    if (!node) throw new Error("PLAYER_RESPONSE_SHAPE_INVALID");
    if (node.kind === "raw") return node.raw;
    if (node.kind === "string") return JSON.stringify(node.value);
    if (node.kind === "array") return `[${node.items.map(item => canonical(item)).join(",")}]`;
    return `{${node.entries.filter(([key]) => !omitted?.has(key)).sort(([a], [b]) => compareKeys(a, b)).map(([key, value]) => `${JSON.stringify(key)}:${canonical(value)}`).join(",")}}`;
  }
  const member = (node, key) => node?.kind === "object" ? node.entries.find(([name]) => name === key)?.[1] : null;
  const canonicalBody = (body) => canonical(parseExact(JSON.stringify(body)).syntax);
  function localURL(path) {
    const url = new URL(path, location.origin);
    if (url.origin !== location.origin || !url.pathname.startsWith(API) || url.username || url.password || url.hash) throw new Error("PLAYER_ENDPOINT_INVALID");
    return url.pathname + url.search;
  }
  function failClosed(error) {
    app.dataset.state = "error";
    text("player-state-message", error?.message || "PLAYER_UNAVAILABLE");
    text("status-state", "Недоступно");
    visible("workspace-content", false); visible("project-overview", false);
    $("structure-tree").replaceChildren(); visible("help-topic", false);
    $("help-content").removeAttribute("srcdoc");
    memory.helpEpoch += 1;
    memory.project = null; memory.definition = null; memory.workspace = null;
    memory.definitions = []; memory.workspaces = []; memory.slices = []; memory.experiments = [];
    memory.slice = null; memory.treeRows = [];
    app.dataset.projectId = ""; app.dataset.workspaceId = ""; app.dataset.projectionStatus = "NOT_PROVEN";
    for (const id of ["project-label", "project-name", "workspace-label", "workspace-name", "workspace-identity", "definition-identity", "definition-hash", "definition-current", "definition-status", "projection-status", "projection-hash", "projection-badge", "slice-identity", "slice-date", "slice-immutability", "help-title", "help-identity", "experiment-name", "status-definition", "status-slice"]) text(id, "—");
    for (const id of ["definition-select", "workspace-select", "slice-select"]) setOptions(id, [], null, () => "", "Недоступно");
    $("experiment-metadata")?.replaceChildren();
    $("experiment-tabs")?.querySelectorAll("[data-dynamic-experiment]").forEach(node => node.remove());
    text("structure-count", "0"); text("structure-window", "0–0");
    updateCommands();
  }
  async function responsePayload(response, digestKey = "response_sha256") {
    const raw = await response.text();
    if (!response.headers.get("Content-Type")?.toLowerCase().startsWith("application/json") || response.headers.get("ETag") !== `"${await hash(raw)}"`) throw new Error("PLAYER_RESPONSE_INTEGRITY_CONFLICT");
    const parsed = parseExact(raw), dto = parsed.value;
    if (!dto || typeof dto !== "object" || Array.isArray(dto) || canonical(parsed.syntax) !== raw.replace(/\n$/, "")) throw new Error("PLAYER_RESPONSE_NONCANONICAL");
    if (!response.ok) {
      if (Object.keys(dto).sort().join(",") !== "code,errors" || typeof dto.code !== "string" || !/^[A-Z0-9_]{1,100}$/.test(dto.code) || !Array.isArray(dto.errors) || dto.errors.length !== 1 || typeof dto.errors[0] !== "string" || dto.errors[0].length > 1024) throw new Error("PLAYER_RESPONSE_ERROR_UNVERIFIED");
      // Only canonical, representation-verified Foundation errors can settle a
      // rejection. Broken transport/HTML/malformed errors leave outcome unknown.
      const error = new Error(dto.code); error.httpStatus = response.status; throw error;
    }
    if (!SHA.test(dto[digestKey] || "") || await hash(canonical(parsed.syntax, new Set([digestKey]))) !== dto[digestKey]) throw new Error("PLAYER_RESPONSE_INTEGRITY_CONFLICT");
    return {dto, syntax: parsed.syntax, raw};
  }
  async function read(path) {
    return responsePayload(await fetch(localURL(path), {method: "GET", credentials: "same-origin", cache: "no-store", redirect: "error", headers: {Accept: "application/json"}}));
  }
  async function verifiedDefinition(dto, syntax, expectedId, projectId) {
    if (!dto || dto.id !== expectedId || dto.project_id !== projectId || dto.publication_status !== "PUBLISHED" || !SHA.test(dto.manifest_hash || "") || !dto.manifest || await hash(canonical(member(syntax, "manifest"))) !== dto.manifest_hash) throw new Error("PLAYER_DEFINITION_INTEGRITY_CONFLICT");
    return dto;
  }
  function projectIdentity(dto, expected) {
    if (!dto || dto.id !== expected) throw new Error("PLAYER_PROJECT_IDENTITY_CONFLICT");
    memory.project = dto; app.dataset.projectId = expected;
    text("project-label", dto.name || dto.code || expected); text("project-name", dto.name || dto.code || expected);
  }
  function setOptions(id, rows, selected, label, empty) {
    const select = $(id); select.replaceChildren(); const placeholder = document.createElement("option"); placeholder.value = ""; placeholder.textContent = empty; select.append(placeholder);
    for (const row of rows) {const option = document.createElement("option"); option.value = uuid(row.id); option.textContent = label(row); select.append(option);}
    select.value = selected || "";
  }
  async function loadProject(projectId, selectedDefinition = null) {
    uuid(projectId);
    const [definitions, workspaces] = await Promise.all([read(`${API}projects/${projectId}/definitions/`), read(`${API}projects/${projectId}/workspaces/`)]);
    projectIdentity(definitions.dto.project, projectId);
    if (workspaces.dto.project?.id !== projectId || !Array.isArray(definitions.dto.definitions) || !Array.isArray(workspaces.dto.workspaces)) throw new Error("PLAYER_RESPONSE_SHAPE_INVALID");
    if (definitions.dto.definitions.some(item => item.project_id !== projectId || item.publication_status !== "PUBLISHED") || workspaces.dto.workspaces.some(item => item.project_id !== projectId)) throw new Error("PLAYER_SCOPE_INTEGRITY_CONFLICT");
    memory.definitions = definitions.dto.definitions; memory.workspaces = workspaces.dto.workspaces;
    setOptions("definition-select", memory.definitions, selectedDefinition, item => `${item.code} · ${item.version}${item.is_current ? " · текущая" : ""}`, "Выберите версию");
    setOptions("workspace-select", memory.workspaces, memory.workspace?.id, item => `${item.name} · ${item.version}`, "Выберите пространство");
    visible("project-overview", true);
    if (selectedDefinition) await openDefinition(selectedDefinition);
  }
  async function openDefinition(definitionId) {
    uuid(definitionId);
    if (!memory.definitions.some(item => item.id === definitionId)) throw new Error("PLAYER_DEFINITION_NOT_IN_LIST");
    const result = await read(`${API}definitions/${definitionId}/`);
    if (result.dto.project?.id !== memory.project.id) throw new Error("PLAYER_SCOPE_INTEGRITY_CONFLICT");
    memory.definition = await verifiedDefinition(result.dto.definition, member(result.syntax, "definition"), definitionId, memory.project.id);
    text("definition-identity", `${memory.definition.code} · ${memory.definition.version} · ${definitionId}`);
    text("definition-status", memory.definition.publication_status); text("definition-hash", memory.definition.manifest_hash);
    text("definition-current", memory.definition.is_current === true ? "Да" : "Нет"); text("status-definition", `Определение: ${memory.definition.code} · ${memory.definition.version}`);
    rebuildTree(); updateCommands();
  }
  function verifyProjection(workspace) {
    const status = workspace.assessment_projection_status;
    if (!["COMPLETE", "NOT_PROVEN", "INTEGRITY_CONFLICT"].includes(status) || (status === "COMPLETE" ? !SHA.test(workspace.assessment_projection_sha256 || "") : workspace.assessment_projection_sha256 !== null)) throw new Error("PLAYER_PROJECTION_STATUS_INVALID");
  }
  async function loadWorkspace(workspaceId, loadLists = true) {
    const result = await read(`${API}workspaces/${uuid(workspaceId)}/`), dto = result.dto;
    if (dto.workspace?.id !== workspaceId || !UUID.test(dto.workspace.project_id || "")) throw new Error("PLAYER_WORKSPACE_IDENTITY_CONFLICT");
    projectIdentity(dto.project, dto.workspace.project_id); verifyProjection(dto.workspace);
    memory.workspace = dto.workspace; memory.definition = null;
    if (dto.definition !== null) {
      memory.definition = await verifiedDefinition(dto.definition, member(result.syntax, "definition"), dto.workspace.definition_id, dto.workspace.project_id);
      if (dto.workspace.definition_manifest_hash !== memory.definition.manifest_hash) throw new Error("PLAYER_MANIFEST_PIN_CONFLICT");
    }
    if (dto.workspace.assessment_projection_status === "COMPLETE" && !memory.definition) throw new Error("PLAYER_PROJECTION_STATUS_INVALID");
    app.dataset.workspaceId = workspaceId; app.dataset.projectionStatus = dto.workspace.assessment_projection_status;
    text("workspace-label", dto.workspace.name); text("workspace-name", dto.workspace.name); text("workspace-identity", `${dto.workspace.code} · ${dto.workspace.version} · ${workspaceId}`);
    text("definition-identity", memory.definition ? `${memory.definition.code} · ${memory.definition.version} · ${memory.definition.id}` : "INTEGRITY_CONFLICT");
    text("definition-hash", dto.workspace.definition_manifest_hash); text("projection-status", dto.workspace.assessment_projection_status); text("projection-hash", dto.workspace.assessment_projection_sha256);
    text("projection-badge", dto.workspace.assessment_projection_status); if ($("projection-badge")) $("projection-badge").dataset.status = dto.workspace.assessment_projection_status;
    text("status-definition", `Определение: ${memory.definition?.code || dto.workspace.definition_id} · ${memory.definition?.version || "—"}`);
    if (loadLists) {
      const list = await read(`${API}projects/${dto.workspace.project_id}/workspaces/`);
      if (list.dto.project?.id !== dto.workspace.project_id || !Array.isArray(list.dto.workspaces)) throw new Error("PLAYER_SCOPE_INTEGRITY_CONFLICT");
      memory.workspaces = list.dto.workspaces;
      setOptions("workspace-select", memory.workspaces, workspaceId, item => `${item.name} · ${item.version}`, "Выберите пространство");
      setOptions("definition-select", memory.definition ? [memory.definition] : [], memory.definition?.id, item => `${item.code} · ${item.version}`, "Определение недоступно");
    }
    rebuildTree();
    memory.slices = []; memory.experiments = [];
    if (complete()) await loadWorkspaceChildren();
    else {setOptions("slice-select", [], null, () => "", "Проекция не подтверждена"); renderExperiments(); text("status-state", dto.workspace.assessment_projection_status);}
    visible("workspace-content", true); updateCommands();
  }
  async function loadWorkspaceChildren() {
    const id = uuid(memory.workspace.id);
    const [slices, experiments] = await Promise.all([read(`${API}workspaces/${id}/time-slices/`), read(`${API}workspaces/${id}/experiments/`)]);
    if (slices.dto.workspace_id !== id || experiments.dto.workspace_id !== id || !Array.isArray(slices.dto.time_slices) || !Array.isArray(experiments.dto.experiments)) throw new Error("PLAYER_SCOPE_INTEGRITY_CONFLICT");
    if (slices.dto.time_slices.some(item => item.workspace_id !== id || item.project_id !== memory.project.id)) throw new Error("PLAYER_SCOPE_INTEGRITY_CONFLICT");
    memory.slices = slices.dto.time_slices; memory.experiments = experiments.dto.experiments;
    setOptions("slice-select", memory.slices, memory.slice?.id, item => `${item.cutoff_date} · ${item.name}`, "Выберите срез");
    renderExperiments();
    const exactSlice = new URL(location.href).searchParams.get("slice");
    if (exactSlice && !memory.slice) selectSlice(exactSlice, false);
    else if (memory.slice) selectSlice(memory.slice.id, false);
  }
  function selectSlice(sliceId, updateURL = true) {
    if (blocked() || !complete()) return;
    const slice = memory.slices.find(item => item.id === uuid(sliceId));
    if (!slice) throw new Error("PLAYER_TIME_SLICE_NOT_IN_LIST");
    memory.slice = slice; $("slice-select").value = sliceId;
    text("slice-identity", `${slice.name} · ${slice.code} · ${slice.version} · ${slice.id}`); text("slice-date", slice.cutoff_date); text("slice-immutability", "Сохранён · неизменяем"); text("status-slice", `Срез: ${slice.cutoff_date}`);
    if (updateURL) {const url = new URL(location.href); url.searchParams.set("slice", sliceId); history.replaceState(null, "", url.pathname + url.search);}
    updateCommands();
  }
  function rebuildTree() {
    const source = memory.definition?.manifest?.[memory.treeKind] || [];
    if (!Array.isArray(source)) throw new Error("PLAYER_STRUCTURE_INVALID");
    const children = new Map(), ids = new Set(source.map(item => uuid(item.id)));
    if (ids.size !== source.length) throw new Error("PLAYER_STRUCTURE_INVALID");
    for (const item of source) {const parent = item.parent_id || null; if (parent && !ids.has(parent)) throw new Error("PLAYER_STRUCTURE_INVALID"); if (!children.has(parent)) children.set(parent, []); children.get(parent).push(item);}
    for (const items of children.values()) items.sort((a, b) => a.order - b.order || compareKeys(a.id, b.id));
    const rows = [], seen = new Set(), stack = (children.get(null) || []).slice().reverse().map(item => ({item, depth: 0}));
    while (stack.length) {const row = stack.pop(); if (seen.has(row.item.id)) throw new Error("PLAYER_STRUCTURE_INVALID"); seen.add(row.item.id); rows.push(row); for (const child of (children.get(row.item.id) || []).slice().reverse()) stack.push({item: child, depth: row.depth + 1});}
    if (rows.length !== source.length) throw new Error("PLAYER_STRUCTURE_INVALID");
    memory.treeRows = rows; memory.treeOffset = 0; memory.treeSelection = 0; renderTree();
  }
  function renderTree() {
    const tree = $("structure-tree"), rows = memory.treeRows; tree.replaceChildren();
    const end = Math.min(rows.length, memory.treeOffset + WINDOW_SIZE);
    for (let index = memory.treeOffset; index < end; index += 1) {
      const {item, depth} = rows[index], row = document.createElement("div");
      row.id = `structure-row-${index}`; row.className = `tree-row tree-depth-${Math.min(depth, 8)}`; row.setAttribute("role", "treeitem"); row.setAttribute("aria-level", String(depth + 1)); row.setAttribute("aria-selected", String(index === memory.treeSelection)); row.setAttribute("aria-posinset", String(index + 1)); row.setAttribute("aria-setsize", String(rows.length)); row.dataset.entityId = item.id;
      const label = document.createElement("span"); label.className = "tree-label"; label.textContent = item.label || item.name || item.code || item.id; row.append(label); row.title = `${item.code} · ${item.version}\n${item.id}\n${item.description || ""}`;
      row.addEventListener("click", () => {memory.treeSelection = index; renderTree(); tree.focus();}); tree.append(row);
    }
    tree.setAttribute("aria-activedescendant", rows.length ? `structure-row-${memory.treeSelection}` : ""); text("structure-count", rows.length); text("structure-window", `${rows.length ? memory.treeOffset + 1 : 0}–${end} / ${rows.length} · Page Up / Page Down`);
  }
  function renderExperiments() {
    const tabs = $("experiment-tabs"); if (!tabs) return;
    tabs.querySelectorAll("[data-dynamic-experiment]").forEach(node => node.remove());
    for (const item of memory.experiments) {
      uuid(item.id); const tab = document.createElement("button"); tab.type = "button"; tab.role = "tab"; tab.dataset.dynamicExperiment = "true"; tab.dataset.experimentId = item.id; tab.id = `experiment-${item.id}`; tab.setAttribute("aria-selected", "false"); tab.tabIndex = -1; tab.textContent = item.name; tab.addEventListener("click", () => activateExperiment(item.id)); tabs.insertBefore(tab, $("experiment-plus"));
    }
    activateExperiment("general");
  }
  function activateExperiment(id) {
    if (blocked()) return;
    const tabs = $("experiment-tabs"); if (!tabs) return;
    const item = memory.experiments.find(row => row.id === id);
    if (id !== "general" && !item) return;
    tabs.querySelectorAll("[data-experiment-id]").forEach(tab => {const selected = tab.dataset.experimentId === id; tab.setAttribute("aria-selected", String(selected)); tab.tabIndex = selected ? 0 : -1;});
    visible("general-panel", id === "general"); visible("experiment-panel", id !== "general");
    if (item) {text("experiment-name", item.name); const metadata = $("experiment-metadata"); metadata.replaceChildren(); for (const [label, value] of [["Статус", item.status], ["Порядок", item.order], ["Цвет (метаданные)", item.color], ["Профиль эксперта", item.expert_profile ? `${item.expert_profile.name || item.expert_profile.code} · ${item.expert_profile.version}` : "—"], ["Набор оценок", item.assessment_set ? `${item.assessment_set.code} · ${item.assessment_set.version}` : "—"]]) {const term = document.createElement("dt"), detail = document.createElement("dd"); term.textContent = label; detail.textContent = value == null ? "—" : String(value); metadata.append(term, detail);}}
  }
  function updateCommands() {
    const ready = app.dataset.state === "ready" && !memory.loading && !blocked();
    const enabled = {"CMD-WORKSPACE-CREATE": ready && !!memory.definition && !!memory.project && app.dataset.playerPage !== "workspace", "CMD-WORKSPACE-OPEN": ready && !!$("workspace-select").value, "CMD-WORKSPACE-SWITCH": ready && memory.workspaces.length > 0, "CMD-SLICE-CREATE": ready && complete(), "CMD-SLICE-OPEN": ready && complete() && !!$("slice-select").value, "CMD-SLICE-SWITCH": ready && complete() && memory.slices.length > 0, "CMD-SLICE-REFRESH": ready && complete() && !!memory.slice};
    document.querySelectorAll("[data-command-id]").forEach(button => button.setAttribute("aria-disabled", String(!enabled[button.dataset.commandId])));
    const workspaceLabel = document.querySelector('[data-command-id="CMD-WORKSPACE-CREATE"] .primary-label');
    const sliceLabel = document.querySelector('[data-command-id="CMD-SLICE-CREATE"] .primary-label');
    workspaceLabel.hidden = !!memory.workspace;
    sliceLabel.hidden = !complete() || memory.slices.length > 0;
    $("definition-select").disabled = blocked() || memory.loading || app.dataset.playerPage === "workspace";
    $("workspace-select").disabled = blocked() || memory.loading;
    $("slice-select").disabled = blocked() || memory.loading || !complete();
    const replay = memory.operation && ["unknown", "complete"].includes(memory.operation.state);
    visible("operation-replay", !!replay); $("operation-replay").setAttribute("aria-disabled", String(memory.operation?.state === "busy"));
  }
  function ready() {
    app.dataset.state = "ready"; memory.loading = false;
    text("status-state", memory.workspace && !complete() ? memory.workspace.assessment_projection_status : "Готово");
    if (app.dataset.reloadNotice === "true") {
      text("player-state-message", "После перезагрузки ключи прежних операций не восстанавливаются. Если результат был неизвестен, не создавайте запись повторно до независимой проверки Foundation.");
    }
    updateCommands();
  }
  async function runRead(action) {if (blocked()) return; memory.loading = true; updateCommands(); try {await action(); ready();} catch (error) {memory.loading = false; failClosed(error);}}
  function navigate(path) {if (blocked()) {text("player-state-message", "Результат операции неизвестен. Сначала явно проверьте тем же запросом."); return;} const url = new URL(path, location.origin); if (url.origin === location.origin && url.pathname.startsWith("/player/")) location.assign(url.pathname + url.search);}
  function csrfToken() {const match = document.cookie.split(";").map(item => item.trim()).find(item => item.startsWith("csrftoken=")); if (!match) throw new Error("PLAYER_CSRF_UNAVAILABLE"); return decodeURIComponent(match.slice("csrftoken=".length));}
  function openOperation(kind) {
    if (blocked()) return;
    if (kind === "slice" ? !complete() : !memory.definition) return;
    memory.operation = null; memory.operationKind = kind;
    $("operation-form").reset(); $("operation-id").value = crypto.randomUUID(); $("operation-version").value = "1.0.0"; $("operation-order").value = "0";
    visible("slice-fields", kind === "slice"); $("operation-cutoff-date").required = kind === "slice";
    $("operation-form").querySelectorAll("input,button").forEach(node => {node.disabled = false;});
    text("operation-title", kind === "slice" ? "Новый временной срез" : "Новое рабочее пространство");
    text("operation-intent", kind === "slice" ? "Сохранённый временной срез неизменяем." : `Точная версия: ${memory.definition.code} · ${memory.definition.version}. Не пространство по умолчанию.`);
    text("operation-state", "Запрос ещё не отправлен."); $("operation-dialog").showModal(); $("operation-code").focus(); updateCommands();
  }
  async function sealAndSend(event) {
    event.preventDefault(); if (blocked() || memory.operation || !$("operation-form").reportValidity()) return;
    try {
      const kind = memory.operationKind, id = uuid($("operation-id").value), body = {id, code: $("operation-code").value, version: $("operation-version").value, name: $("operation-name").value, metadata: {}};
      let path;
      if (kind === "workspace") {body.definition_id = memory.definition.id; body.definition_manifest_hash = memory.definition.manifest_hash; body.is_default = false; path = `${API}projects/${uuid(memory.project.id)}/workspaces/`;}
      else {if (!complete()) throw new Error("ASSESSMENT_PROJECTION_NOT_PROVEN"); body.cutoff_date = $("operation-cutoff-date").value; body.order = Number($("operation-order").value); if (!Number.isSafeInteger(body.order) || body.order < 0) throw new Error("PLAYER_TIME_SLICE_INVALID"); path = `${API}workspaces/${uuid(memory.workspace.id)}/time-slices/`;}
      // Only this explicit submit creates a seal. A retry never generates IDs,
      // reserializes a form, changes the If-Match or follows a new context.
      const parentHash = kind === "slice" ? memory.workspace.definition_manifest_hash : memory.definition.manifest_hash;
      const seal = Object.freeze({kind, id, path: localURL(path), body: canonicalBody(body), key: crypto.randomUUID(), ifMatch: `"${parentHash}"`, projectId: memory.project.id, workspaceId: memory.workspace?.id || null, definitionId: memory.definition.id, pageURL: location.pathname + location.search});
      csrfToken(); memory.operation = {seal, state: "sealed", receipt: null, receiptBytes: null}; await sendSealed();
    } catch (error) {text("operation-state", error.message);}
  }
  async function sendSealed() {
    const operation = memory.operation; if (!operation || operation.state === "busy") return;
    const seal = operation.seal; operation.state = "busy"; updateCommands();
    $("operation-form").querySelectorAll("input,button").forEach(node => {node.disabled = true;}); text("operation-state", "Ожидаем квитанцию Foundation…"); text("status-state", "Операция выполняется");
    try {
      const response = await fetch(seal.path, {method: "POST", credentials: "same-origin", cache: "no-store", redirect: "error", headers: {Accept: "application/json", "Content-Type": "application/json", "X-CSRFToken": csrfToken(), "Idempotency-Key": seal.key, "If-Match": seal.ifMatch}, body: seal.body});
      const result = await responsePayload(response, "receipt_sha256"), receipt = result.dto;
      const expectedContract = seal.kind === "workspace" ? "FOUNDATION_PLAYER_WORKSPACE_CREATE_V1" : "FOUNDATION_PLAYER_TIME_SLICE_CREATE_V1";
      if (![200, 201].includes(response.status) || receipt.contract !== expectedContract || receipt.version !== "1.0.0" || receipt.original_http_status !== 201 || receipt.operation_id !== seal.key || receipt.audit_event_id !== seal.key || receipt.project_id !== seal.projectId || receipt.definition_id !== seal.definitionId || receipt.manifest_sha256 !== seal.ifMatch.slice(1, -1) || (seal.kind === "workspace" ? receipt.workspace_id !== seal.id : receipt.workspace_id !== seal.workspaceId || receipt.slice_id !== seal.id) || (operation.receiptBytes !== null && operation.receiptBytes !== result.raw)) throw new Error("PLAYER_RECEIPT_INTEGRITY_CONFLICT");
      operation.receipt = Object.freeze(receipt); operation.receiptBytes = result.raw; operation.state = "complete";
      text("operation-state", `Квитанция подтверждена: ${receipt.receipt_sha256}`); text("status-state", response.status === 200 ? "Точное повторение подтверждено" : "Сохранено Foundation");
      $("operation-dialog").close();
      if (seal.kind === "workspace") {
        await loadWorkspace(seal.id); $("workspace-select").value = seal.id;
      } else {await loadWorkspaceChildren(); selectSlice(seal.id);}
      ready();
    } catch (error) {
      if (error.httpStatus && [400, 401, 403, 404, 409, 412, 422, 428].includes(error.httpStatus)) {
        operation.state = "rejected"; text("operation-state", error.message); text("status-state", error.message);
        $("operation-cancel").disabled = false;
        if ([401, 403, 404].includes(error.httpStatus)) failClosed(error);
      } else if (operation.state === "complete") {
        // A verified committed receipt is still known if subsequent GET fails.
        failClosed(error); text("operation-state", "Операция сохранена; повторное чтение недоступно.");
      } else {
        operation.state = "unknown"; text("operation-state", "Результат неизвестен. Разрешено только явное повторение запечатанного запроса."); text("status-state", "Результат неизвестен · проверьте тем же запросом"); $("operation-dialog").close();
      }
    } finally {updateCommands();}
  }
  function saveLayout() {try {const raw = JSON.stringify(memory.layout); if (encoder.encode(raw).length <= 256) localStorage.setItem(STORAGE_KEY, raw);} catch (_) { /* layout persistence is optional, never domain storage */ }}
  function applyLayout() {document.documentElement.style.setProperty("--left-width", `${memory.layout.left}px`); document.documentElement.style.setProperty("--right-width", `${memory.layout.right}px`); $("left-divider").setAttribute("aria-valuenow", String(memory.layout.left)); $("right-divider").setAttribute("aria-valuenow", String(memory.layout.right));}
  function loadLayout() {
    try {const raw = localStorage.getItem(STORAGE_KEY); if (raw !== null) {if (encoder.encode(raw).length > 256) throw new Error("layout"); const value = JSON.parse(raw); if (!value || Object.keys(value).sort().join(",") !== "activeRightTab,left,right,version" || value.version !== LAYOUT_VERSION || !Number.isInteger(value.left) || value.left < 220 || value.left > 420 || !Number.isInteger(value.right) || value.right < 280 || value.right > 480 || !["document", "chat", "help"].includes(value.activeRightTab)) throw new Error("layout"); memory.layout = {...value};}}
    catch (_) {memory.layout = {...DEFAULT_LAYOUT}; try {localStorage.removeItem(STORAGE_KEY);} catch (_) { /* Storage may be unavailable; never touch another key. */ }}
    applyLayout(); selectRightTab(memory.layout.activeRightTab, false);
  }
  function selectRightTab(name, persist = true) {
    if (!["document", "chat", "help"].includes(name)) return;
    memory.layout.activeRightTab = name;
    document.querySelectorAll("[data-right-tab]").forEach(tab => {const selected = tab.dataset.rightTab === name; tab.setAttribute("aria-selected", String(selected)); tab.tabIndex = selected ? 0 : -1; visible(`panel-${tab.dataset.rightTab}`, selected);});
    if (persist) saveLayout();
    // Document/Chat only disclose their exact local disabled reasons; no fetch.
  }
  async function loadHelp() {
    const epoch = ++memory.helpEpoch, key = $("help-key").value;
    visible("help-topic", false); $("help-content").removeAttribute("srcdoc");
    if (!memory.workspace) {visible("local-help", true); text("help-state", "Локальное пояснение · полные термины"); return;}
    const workspaceId = uuid(memory.workspace.id); visible("local-help", false); text("help-state", "Проверяем точную справку Foundation…");
    try {
      const result = await read(`${API}workspaces/${workspaceId}/help/${encodeURIComponent(key)}/?locale=ru&version=1.0.0`), dto = result.dto, topic = dto.help_topic;
      if (epoch !== memory.helpEpoch || memory.workspace?.id !== workspaceId) return;
      if (dto.workspace_id !== workspaceId || dto.ui_key !== key || dto.locale !== "ru" || !topic || topic.version !== "1.0.0" || topic.locale !== "ru" || typeof topic.sanitized_html !== "string" || !SHA.test(topic.content_sha256 || "") || await hash(topic.sanitized_html) !== topic.content_sha256) throw new Error("PLAYER_HELP_INTEGRITY_CONFLICT");
      text("help-title", topic.title); text("help-identity", `PLAYER · ${topic.stable_key} · ru · ${topic.version} · ${topic.content_sha256}`); $("help-content").srcdoc = topic.sanitized_html; visible("help-topic", true); text("help-state", "Точная версия подтверждена");
    } catch (error) {if (epoch === memory.helpEpoch) {visible("help-topic", false); text("help-state", error.message);}}
  }
  function splitters() {
    for (const [side, min, max] of [["left", 220, 420], ["right", 280, 480]]) {
      const divider = $(`${side}-divider`), update = value => {memory.layout[side] = Math.max(min, Math.min(max, Math.round(value))); applyLayout(); saveLayout();};
      let drag = null;
      divider.addEventListener("pointerdown", event => {if (event.button !== 0) return; drag = {x: event.clientX, width: memory.layout[side]}; divider.setPointerCapture(event.pointerId); divider.classList.add("is-dragging"); divider.focus();});
      divider.addEventListener("pointermove", event => {if (drag) update(drag.width + (event.clientX - drag.x) * (side === "left" ? 1 : -1));});
      const release = () => {drag = null; divider.classList.remove("is-dragging");}; divider.addEventListener("pointerup", release); divider.addEventListener("pointercancel", release); divider.addEventListener("lostpointercapture", release);
      divider.addEventListener("keydown", event => {if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return; event.preventDefault(); const delta = (event.shiftKey ? 20 : 10) * (side === "left" ? 1 : -1); update(event.key === "Home" ? min : event.key === "End" ? max : memory.layout[side] + (event.key === "ArrowRight" ? delta : -delta));});
    }
  }
  function events() {
    $("project-entry-form")?.addEventListener("submit", event => {event.preventDefault(); try {navigate(`/player/projects/${uuid($("project-entry-id").value.trim())}/`);} catch (error) {failClosed(error);}});
    $("definition-select").addEventListener("change", () => {if (!blocked() && $("definition-select").value) runRead(async () => {await openDefinition($("definition-select").value); const url = new URL(location.href); url.searchParams.set("definition", memory.definition.id); history.replaceState(null, "", url.pathname + url.search);});});
    $("workspace-select").addEventListener("change", updateCommands); $("slice-select").addEventListener("change", updateCommands);
    document.querySelectorAll("[data-command-id]").forEach(button => button.addEventListener("click", () => {
      if (button.getAttribute("aria-disabled") === "true" || blocked()) return;
      switch (button.dataset.commandId) {
        case "CMD-WORKSPACE-CREATE": openOperation("workspace"); break;
        case "CMD-WORKSPACE-OPEN": navigate(`/player/workspaces/${uuid($("workspace-select").value)}/`); break;
        case "CMD-WORKSPACE-SWITCH": $("workspace-select").focus(); break;
        case "CMD-SLICE-CREATE": openOperation("slice"); break;
        case "CMD-SLICE-OPEN": try {selectSlice($("slice-select").value);} catch (error) {failClosed(error);} break;
        case "CMD-SLICE-SWITCH": $("slice-select").focus(); break;
        case "CMD-SLICE-REFRESH": runRead(async () => {await loadWorkspace(memory.workspace.id);}); break;
        default: break;
      }
    }));
    $("operation-form").addEventListener("submit", sealAndSend); $("operation-replay").addEventListener("click", () => {if (["unknown", "complete"].includes(memory.operation?.state)) sendSealed();});
    $("operation-cancel").addEventListener("click", () => {if (!blocked()) $("operation-dialog").close();}); $("operation-dialog").addEventListener("cancel", event => {if (blocked()) event.preventDefault();});
    document.addEventListener("click", event => {if (blocked() && event.target.closest("a")) event.preventDefault();}, true);
    window.addEventListener("beforeunload", event => {if (blocked()) {event.preventDefault(); event.returnValue = "";}});
    window.addEventListener("popstate", () => {if (blocked()) {history.pushState(null, "", memory.operation.seal.pageURL); text("status-state", "Результат неизвестен · сначала точное повторение");}});
    document.querySelectorAll("[data-focus-context]").forEach(panel => panel.addEventListener("focusin", () => {memory.focus = panel.dataset.focusContext; $("player-toolbar").dataset.focusContext = memory.focus; const label = {structure: "структура", workspace: "пространство", help: "справка"}[memory.focus] || "пространство"; text("toolbar-context", `Контекст: ${label}`); text("status-focus", `Фокус: ${label}`);}));
    document.addEventListener("keydown", event => {if (event.key !== "F6" || event.ctrlKey || event.altKey || event.metaKey || $("operation-dialog").open) return; event.preventDefault(); const panels = [$("left-panel"), $("center-panel"), $("right-panel")]; const index = panels.findIndex(panel => panel.contains(document.activeElement)); panels[(index + (event.shiftKey ? 2 : 1) + 3) % 3].focus();});
    document.querySelectorAll("[data-tree-kind]").forEach(tab => tab.addEventListener("click", () => {memory.treeKind = tab.dataset.treeKind; document.querySelectorAll("[data-tree-kind]").forEach(other => {other.setAttribute("aria-selected", String(other === tab)); other.tabIndex = other === tab ? 0 : -1;}); rebuildTree();}));
    $("structure-tree").addEventListener("keydown", event => {const count = memory.treeRows.length; if (!count || !["ArrowDown", "ArrowUp", "PageDown", "PageUp", "Home", "End"].includes(event.key)) return; event.preventDefault(); const delta = {ArrowDown: 1, ArrowUp: -1, PageDown: WINDOW_SIZE, PageUp: -WINDOW_SIZE}[event.key] || 0; memory.treeSelection = event.key === "Home" ? 0 : event.key === "End" ? count - 1 : Math.max(0, Math.min(count - 1, memory.treeSelection + delta)); memory.treeOffset = Math.floor(memory.treeSelection / WINDOW_SIZE) * WINDOW_SIZE; renderTree(); $("structure-tree").scrollTop = event.key === "End" ? $("structure-tree").scrollHeight : 0;});
    $("structure-tree").addEventListener("wheel", event => {const tree = $("structure-tree"); if (event.deltaY > 0 && tree.scrollTop + tree.clientHeight >= tree.scrollHeight - 2 && memory.treeOffset + WINDOW_SIZE < memory.treeRows.length) {event.preventDefault(); memory.treeOffset += WINDOW_SIZE; memory.treeSelection = memory.treeOffset; renderTree(); tree.scrollTop = 0;} else if (event.deltaY < 0 && tree.scrollTop <= 0 && memory.treeOffset > 0) {event.preventDefault(); memory.treeOffset -= WINDOW_SIZE; memory.treeSelection = memory.treeOffset; renderTree(); tree.scrollTop = tree.scrollHeight;}}, {passive: false});
    document.querySelectorAll("[data-right-tab]").forEach(tab => tab.addEventListener("click", () => selectRightTab(tab.dataset.rightTab)));
    $("context-help").addEventListener("click", () => {selectRightTab("help"); $("help-key").value = memory.focus === "structure" ? "player.published_definition" : "player.workspace"; loadHelp();}); $("help-key").addEventListener("change", loadHelp);
    $("experiment-general")?.addEventListener("click", () => activateExperiment("general"));
    document.querySelectorAll("[role=tablist]").forEach(list => list.addEventListener("keydown", event => {if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return; const tabs = Array.from(list.querySelectorAll("[role=tab]")); const index = tabs.indexOf(document.activeElement); if (index < 0) return; event.preventDefault(); const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length; tabs[next].focus();}));
    splitters();
  }
  async function boot() {
    // Navigation metadata contains no operation identity. This neutral notice
    // does not assert that an earlier operation existed and never reconstructs
    // a lost key, sealed body or receipt. A normal fresh visit stays dense.
    app.dataset.reloadNotice = String(performance.getEntriesByType("navigation")[0]?.type === "reload");
    loadLayout(); events();
    if (app.dataset.authenticated !== "true") {failClosed(new Error("PLAYER_SESSION_REQUIRED")); return;}
    try {
      if (app.dataset.playerPage === "project") await loadProject(uuid(app.dataset.projectId), new URL(location.href).searchParams.get("definition"));
      else if (app.dataset.playerPage === "workspace") await loadWorkspace(uuid(app.dataset.workspaceId));
      ready();
    } catch (error) {failClosed(error);}
  }
  boot();
})();
