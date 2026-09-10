/* G8 browser composition: session/CSRF only, Foundation HTTP only, memory-only state. */
(() => {
  "use strict";

  const app = document.getElementById("player-app");
  const root = document.getElementById("workspace-content");
  if (!app || !root || root.dataset.g8Shell !== "true") return;

  const API = "/api/foundation/player/";
  const PROFILE = "KZ_ZHANAOZEN_EXPERT_V2_A5_0_1";
  const SOURCE_BY_LANE = {"AI":"ИИ_Значение","HUMAN":"Эксперт_Значение"};
  const SHA = /^[0-9a-f]{64}$/;
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  const FOCUS_KINDS = new Set(["parameter-value", "actor-element-assessment"]);
  const state = {
    experiments: [], selected: null, preview: null, file: null, busy: false,
    loadedWorkspace: null, manualTargets: null, values: [], correcting: null,
    ticket: null, ticketText: "", ticketRetained: false,
  };
  const $ = (id) => document.getElementById(id);
  const quoted = (value) => `"${value}"`;
  const cell = (value) => {
    const node = document.createElement("td");
    node.textContent = value == null ? "—" : String(value);
    return node;
  };
  const cookie = () => document.cookie.split(";").map(value => value.trim())
    .find(value => value.startsWith("csrftoken="))?.slice(10) || "";

  function fail(code) { throw new Error(code || "PLAYER_OPERATION_FAILED"); }

  function bindFocus(node, focus) {
    node.removeAttribute("data-ca-focus-kind");
    node.removeAttribute("data-ca-focus-id");
    if (focus == null) return;
    if (!FOCUS_KINDS.has(focus.kind) || !UUID.test(focus.id || "")) {
      fail("PLAYER_FOCUS_IDENTITY_INVALID");
    }
    node.dataset.caFocusKind = focus.kind;
    node.dataset.caFocusId = focus.id;
  }

  function clearWorkspaceView() {
    delete root.dataset.caProjectId;
    delete root.dataset.caWorkspaceId;
    root.querySelectorAll("[data-ca-focus-kind], [data-ca-focus-id]").forEach(node => {
      node.removeAttribute("data-ca-focus-kind");
      node.removeAttribute("data-ca-focus-id");
    });
    $("g8-records")?.tBodies[0]?.replaceChildren();
    $("g8-comparison")?.tBodies[0]?.replaceChildren();
    state.loadedWorkspace = null;
    state.selected = null;
    state.values = [];
    root.hidden = true;
  }

  function canonical(value) {
    if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
    if (value && typeof value === "object") {
      return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
    }
    return JSON.stringify(value);
  }

  async function request(path, options = {}) {
    const method = String(options.method || "GET").toUpperCase();
    const headers = {Accept: "application/json", ...(options.headers || {})};
    if (["POST", "PUT"].includes(method)) headers["X-CSRFToken"] = cookie();
    if (options.body && !(options.body instanceof FormData)) headers["Content-Type"] = "application/json";
    const response = await fetch(API + path, {
      ...options, method, credentials: "same-origin", cache: "no-store", headers,
    });
    const raw = await response.text();
    const expected = response.headers.get("ETag");
    const bytes = new TextEncoder().encode(raw);
    const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
    const actual = Array.from(digest, number => number.toString(16).padStart(2, "0")).join("");
    if (expected !== quoted(actual)) fail("PLAYER_RESPONSE_HASH_MISMATCH");
    let result;
    try { result = JSON.parse(raw); } catch (_) { fail("PLAYER_RESPONSE_JSON_INVALID"); }
    if (!response.ok) fail(result?.code);
    return result;
  }

  function importReady() {
    return state.selected?.status === "DRAFT" && state.preview?.commit_allowed === true
      && state.ticketRetained && $("g8-ticket-ack").checked;
  }

  function syncControls() {
    const draft = state.selected?.status === "DRAFT";
    $("experiment-plus").disabled = state.busy || app.dataset.projectionStatus !== "COMPLETE";
    $("experiment-plus").setAttribute("aria-disabled", String($("experiment-plus").disabled));
    $("g8-freeze").disabled = state.busy || !draft;
    $("g8-archive").disabled = state.busy || !state.selected
      || !["DRAFT", "FROZEN"].includes(state.selected.status);
    $("g8-preview").disabled = state.busy || !draft;
    $("g8-import").disabled = state.busy || !importReady();
    for (const field of $("g8-manual-form").elements) {
      field.disabled = state.busy || !draft
        || (field.id === "g8-manual-number" && $("g8-manual-status").value === "UNKNOWN");
    }
    $("g8-manual-cancel").hidden = !state.correcting;
  }

  function setBusy(value, message) {
    state.busy = value;
    syncControls();
    if (message) $("g8-import-state").textContent = message;
  }

  function invalidatePreview(message = "Preview и сохранённый ticket отменены; выполните preview заново.") {
    state.preview = null;
    state.ticket = null;
    state.ticketText = "";
    state.ticketRetained = false;
    $("g8-ticket-ack").checked = false;
    $("g8-ticket-ack").disabled = true;
    $("g8-ticket-panel").hidden = true;
    $("g8-ticket").textContent = "";
    $("g8-preview-result").hidden = true;
    syncControls();
    if (message) $("g8-import-state").textContent = message;
  }

  function experimentURL(id) {
    return `/player/workspaces/${app.dataset.workspaceId}/experiments/${id}/`;
  }

  function applyWorkspace(item) {
    if (!item || item.id !== app.dataset.workspaceId
        || !UUID.test(item.id || "") || !UUID.test(item.project_id || "")
        || item.assessment_projection_status !== "COMPLETE"
        || !SHA.test(item.definition_manifest_hash || "")
        || !SHA.test(item.assessment_projection_sha256 || "")) {
      fail("ASSESSMENT_PROJECTION_INTEGRITY_CONFLICT");
    }
    app.dataset.projectionStatus = item.assessment_projection_status;
    root.dataset.caProjectId = item.project_id;
    root.dataset.caWorkspaceId = item.id;
    app.dataset.state = "ready";
    root.hidden = false;
    for (const [id, value] of [
      ["workspace-name", item.name], ["workspace-identity", `${item.code} · ${item.id}`],
      ["definition-identity", item.definition_id], ["definition-hash", item.definition_manifest_hash],
      ["projection-status", item.assessment_projection_status],
      ["projection-hash", item.assessment_projection_sha256],
      ["projection-badge", item.assessment_projection_status],
      ["status-definition", `Определение: ${item.definition_id}`], ["status-state", "Готово"],
    ]) if ($(id)) $(id).textContent = value;
  }

  function fillManualTargets(targets) {
    const time = $("g8-manual-time");
    const role = $("g8-manual-role");
    const parameter = $("g8-manual-parameter");
    time.replaceChildren(); role.replaceChildren(); parameter.replaceChildren();
    for (const item of targets?.time_slices || []) {
      const option = document.createElement("option");
      option.value = item.id; option.textContent = `${item.code} · ${item.cutoff_date}`;
      time.append(option);
    }
    for (const item of targets?.actor_element_roles || []) {
      const option = document.createElement("option");
      option.value = `${item.actor_code}|${item.element_code}`;
      option.dataset.actorCode = item.actor_code;
      option.dataset.elementCode = item.element_code;
      option.textContent = `${item.actor_code} × ${item.element_code} · ${item.role_code}`;
      role.append(option);
    }
    for (const code of targets?.parameter_codes || []) {
      const option = document.createElement("option"); option.value = code; option.textContent = code;
      parameter.append(option);
    }
  }

  async function loadExperiments(force = false) {
    const workspace = app.dataset.workspaceId;
    if (!workspace) { clearWorkspaceView(); return; }
    if (state.loadedWorkspace && state.loadedWorkspace !== workspace) clearWorkspaceView();
    if ((state.busy && !force) || (!force && state.loadedWorkspace === workspace)) return;
    const result = await request(`workspaces/${workspace}/experiments/`);
    if (!Array.isArray(result.experiments) || !result.manual_targets) fail("PLAYER_RESPONSE_SHAPE_INVALID");
    applyWorkspace(result.workspace);
    state.experiments = result.experiments;
    state.manualTargets = result.manual_targets;
    state.loadedWorkspace = workspace;
    fillManualTargets(result.manual_targets);
    renderTabs();
    const initial = root.dataset.initialExperimentId;
    if (initial && state.experiments.some(item => item.id === initial)) await select(initial);
    await loadComparison();
    syncControls();
  }

  function renderTabs() {
    const tabs = $("experiment-tabs");
    const plus = $("experiment-plus");
    tabs.querySelectorAll("[data-g8-experiment]").forEach(node => node.remove());
    for (const item of state.experiments) {
      const tab = document.createElement("button");
      tab.type = "button"; tab.setAttribute("role", "tab");
      tab.dataset.g8Experiment = "true"; tab.dataset.experimentId = item.id;
      tab.textContent = `Эксперимент ${item.name}`;
      tab.addEventListener("click", () => select(item.id));
      tabs.insertBefore(tab, plus);
    }
  }

  function cancelCorrection(message = "Ручная запись доступна в DRAFT.") {
    state.correcting = null;
    $("g8-manual-form").reset();
    $("g8-manual-submit").textContent = "Добавить первое значение";
    $("g8-manual-cancel").hidden = true;
    $("g8-manual-state").textContent = message;
    syncControls();
  }

  async function select(id, force = false) {
    if (state.busy && !force) return;
    invalidatePreview(id === "general" ? "Готово." : "Файл не выбран.");
    $("g8-recovery-operation").value = "";
    $("g8-recovery-result").textContent = "";
    $("g8-recovery-result").hidden = true;
    cancelCorrection();
    if (id === "general") {
      state.selected = null;
      $("general-panel").hidden = false;
      $("experiment-panel").hidden = true;
      syncControls();
      return;
    }
    const item = state.experiments.find(value => value.id === id);
    if (!item) return;
    state.selected = item;
    $("general-panel").hidden = true;
    $("experiment-panel").hidden = false;
    document.querySelectorAll("#experiment-tabs [data-experiment-id]").forEach(tab => {
      tab.setAttribute("aria-selected", String(tab.dataset.experimentId === id));
    });
    $("experiment-name").textContent = item.name;
    $("g8-experiment-status").textContent = item.status;
    $("g8-experiment-status").dataset.status = item.status;
    $("g8-permalink").href = experimentURL(item.id);
    const metadata = $("experiment-metadata"); metadata.replaceChildren();
    for (const [name, value] of [
      ["Идентификатор", item.id], ["Дорожка", item.assessment_set.kind],
      ["Профиль", item.expert_profile.display_name], ["Identity key", item.expert_profile.identity_key],
      ["Методика", item.method_version], ["ETag", item.etag],
    ]) {
      const dt = document.createElement("dt"), dd = document.createElement("dd");
      dt.textContent = name; dd.textContent = value; metadata.append(dt, dd);
    }
    $("g8-source-column").selectedIndex = item.assessment_set.kind === "AI" ? 0 : 1;
    await loadValues();
    syncControls();
  }

  function beginCorrection(item) {
    if (state.selected?.status !== "DRAFT") return;
    state.correcting = item;
    $("g8-manual-time").value = item.time_slice_id;
    $("g8-manual-role").value = `${item.actor_code}|${item.element_code}`;
    $("g8-manual-parameter").value = item.parameter_code;
    $("g8-manual-status").value = item.status === "UNKNOWN" ? "UNKNOWN" : "PROVISIONAL";
    $("g8-manual-number").value = item.value == null ? "" : item.value;
    $("g8-manual-confidence").value = item.confidence_category;
    $("g8-manual-rationale").value = item.rationale;
    $("g8-manual-note").value = item.note;
    $("g8-manual-submit").textContent = "Создать неизменяемого преемника";
    $("g8-manual-cancel").hidden = false;
    $("g8-manual-state").textContent = `Коррекция ${item.code}; исходная строка не изменяется.`;
    syncControls();
  }

  async function loadValues() {
    if (!state.selected) return;
    const result = await request(`experiments/${state.selected.id}/values/`);
    state.values = result.values || [];
    const successors = new Set(state.values.map(item => item.supersedes_id).filter(Boolean));
    const table = $("g8-records").tBodies[0]; table.replaceChildren();
    for (const item of state.values) {
      const row = document.createElement("tr");
      bindFocus(row, item.focus);
      const action = document.createElement("td");
      const button = document.createElement("button"); button.type = "button";
      bindFocus(button, item.focus);
      button.textContent = "Создать преемника";
      button.disabled = state.selected.status !== "DRAFT" || successors.has(item.id);
      button.title = state.selected.status !== "DRAFT"
        ? "FROZEN и ARCHIVED не принимают значения."
        : successors.has(item.id) ? "Преемник уже существует." : "Исправить без изменения истории.";
      button.addEventListener("click", () => beginCorrection(item)); action.append(button);
      row.append(cell(item.code), cell(item.parameter_code),
        cell(item.status === "UNKNOWN" ? "UNKNOWN" : item.value),
        cell(item.confidence_category), cell(item.review_flag),
        cell(item.supersedes_id), action);
      table.append(row);
    }
  }

  async function loadComparison() {
    const workspace = app.dataset.workspaceId;
    if (!workspace) return;
    const result = await request(`workspaces/${workspace}/experiment-comparison/`);
    if (result.aggregation !== null) fail("PLAYER_AGGREGATION_FORBIDDEN");
    if (result.project_id !== root.dataset.caProjectId
        || result.workspace_id !== root.dataset.caWorkspaceId) fail("PLAYER_OBJECT_SCOPE_MISMATCH");
    const table = $("g8-comparison").tBodies[0]; table.replaceChildren();
    for (const item of result.values || []) {
      const row = document.createElement("tr");
      bindFocus(row, item.focus);
      row.append(cell(item.experiment_name), cell(item.actor_code), cell(item.element_code),
        cell(item.parameter_code), cell(item.status === "UNKNOWN" ? "UNKNOWN" : item.value),
        cell(item.status), cell(item.confidence_category), cell(item.review_flag));
      table.append(row);
    }
  }

  function identity(prefix) { return `${prefix}-${crypto.randomUUID().slice(0, 8)}`; }

  async function create(event) {
    event.preventDefault();
    const kind = $("g8-kind").value;
    const profileId = crypto.randomUUID(), setId = crypto.randomUUID();
    const experimentId = crypto.randomUUID(), operationId = crypto.randomUUID();
    const payload = {
      experiment: {id: experimentId, code: identity("EXP"), version: "1.0.0",
        name: $("g8-name").value, color: $("g8-color").value || "#255cca",
        order: state.experiments.length, method_version: $("g8-method").value || "A5-v0.1"},
      assessment_set: {id: setId, code: identity("SET"), version: "1.0.0", kind,
        name: `${$("g8-name").value} values`, description: "Independent assessment lane"},
      expert_profile: {id: profileId, code: identity("PROFILE"), version: "1.0.0", kind,
        display_name: $("g8-profile-name").value, identity_key: `${kind}:${profileId}`,
        provider: $("g8-provider").value,
        model_name: kind === "AI" ? $("g8-model").value : "",
        metadata: {contract: "FOUNDATION_PLAYER_EXPERT_PROFILE_V1"}},
    };
    setBusy(true, "Создаём атомарный эксперимент…");
    try {
      const result = await request(`workspaces/${app.dataset.workspaceId}/experiments/`, {
        method: "POST", headers: {"Idempotency-Key": operationId,
          "If-Match": quoted($("definition-hash").textContent)}, body: JSON.stringify(payload),
      });
      state.loadedWorkspace = null; await loadExperiments(true); $("g8-create-dialog").close();
      if (result.created_experiment) await select(result.created_experiment.id, true);
    } finally { setBusy(false, "Готово."); }
  }

  async function transition(action) {
    if (!state.selected) return;
    const current = state.selected; setBusy(true, `${action}…`);
    try {
      await request(`experiments/${current.id}/${action}/`, {
        method: "POST", headers: {"Idempotency-Key": crypto.randomUUID(),
          "If-Match": quoted(current.etag)}, body: JSON.stringify({}),
      });
      state.loadedWorkspace = null; await loadExperiments(true); await select(current.id, true);
    } finally { setBusy(false, "Готово."); }
  }

  function nextVersion(version) {
    const parts = String(version).split(".").map(Number);
    return parts.length === 3 && parts.every(Number.isInteger)
      ? `${parts[0]}.${parts[1]}.${parts[2] + 1}` : "1.0.1";
  }

  async function submitManual(event) {
    event.preventDefault();
    if (!state.selected || state.selected.status !== "DRAFT") return;
    const role = $("g8-manual-role").selectedOptions[0];
    const status = $("g8-manual-status").value;
    const rawValue = $("g8-manual-number").value;
    const value = status === "UNKNOWN" ? null : Number(rawValue);
    if (!role || (status === "PROVISIONAL" && (!rawValue || !Number.isInteger(value)))) {
      fail("PLAYER_REQUEST_INVALID");
    }
    const predecessor = state.correcting;
    const payload = {
      id: crypto.randomUUID(), code: identity("G8-VALUE"),
      version: predecessor ? nextVersion(predecessor.version) : "1.0.0",
      assessment_id: crypto.randomUUID(), assessment_code: identity("G8-ASSESS"),
      time_slice_id: $("g8-manual-time").value,
      actor_code: role.dataset.actorCode, element_code: role.dataset.elementCode,
      parameter_code: $("g8-manual-parameter").value, status, value,
      temporal_status: "UNKNOWN", confidence_category: $("g8-manual-confidence").value,
      rationale: $("g8-manual-rationale").value, note: $("g8-manual-note").value,
      supersedes_id: predecessor?.id || null,
    };
    const etag = predecessor?.etag || state.selected.etag;
    setBusy(true, predecessor ? "Создаём неизменяемого преемника…" : "Создаём первое значение…");
    try {
      await request(`experiments/${state.selected.id}/values/`, {
        method: "POST", headers: {"Idempotency-Key": crypto.randomUUID(),
          "If-Match": quoted(etag)}, body: JSON.stringify(payload),
      });
      cancelCorrection("Значение сохранено через Foundation HTTP.");
      await loadValues(); await loadComparison();
    } finally { setBusy(false); }
  }

  async function readFile() {
    const file = $("g8-file").files[0];
    if (!file) fail("G8_XLSX_FILE_REQUIRED");
    state.file = file; return file;
  }

  function multipart(file, metadata) {
    const form = new FormData();
    form.append("metadata", JSON.stringify(metadata)); form.append("file", file, file.name);
    return form;
  }

  async function deterministicOperationId(seed) {
    const digest = new Uint8Array(await crypto.subtle.digest(
      "SHA-256", new TextEncoder().encode(canonical(seed)),
    ));
    digest[6] = (digest[6] & 15) | 64; digest[8] = (digest[8] & 63) | 128;
    const hex = Array.from(digest.slice(0, 16), number => number.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
  }

  async function issueTicket(previewResult) {
    const seed = {
      workspace_id: app.dataset.workspaceId, experiment_id: state.selected.id,
      raw_file_sha256: previewResult.raw_file_sha256, byte_length: previewResult.byte_length,
      profile_id: PROFILE, profile_sha256: previewResult.profile_sha256, sheet: previewResult.sheet,
      source_column: previewResult.source_column,
      crosswalk_lineage: previewResult.crosswalk_lineage,
      preview_sha256: previewResult.preview_sha256,
      request_plan_sha256: previewResult.request_plan_sha256,
    };
    state.ticket = {contract: "FOUNDATION_PLAYER_XLSX_IMPORT_TICKET_V1",
      contract_version: "1.0.0", ...seed,
      operation_id: await deterministicOperationId(seed)};
    state.ticketText = canonical(state.ticket);
    state.ticketRetained = false;
    $("g8-ticket").textContent = state.ticketText;
    $("g8-ticket-panel").hidden = false;
    $("g8-ticket-ack").checked = false; $("g8-ticket-ack").disabled = true;
  }

  async function preview() {
    if (!state.selected) return;
    invalidatePreview(""); setBusy(true, "Preview: сервер выполняет нулевую запись…");
    try {
      const file = await readFile();
      const metadata = {profile_id: $("g8-import-profile").value,
        sheet: $("g8-sheet").value,
        source_column: $("g8-source-column").selectedIndex === 0
          ? SOURCE_BY_LANE.AI : SOURCE_BY_LANE.HUMAN};
      state.preview = await request(`experiments/${state.selected.id}/xlsx-preview/`, {
        method: "POST", body: multipart(file, metadata),
      });
      $("g8-preview-result").hidden = false;
      $("g8-preview-result").textContent = JSON.stringify(state.preview, null, 2);
      await issueTicket(state.preview);
      $("g8-import-state").textContent = `${state.preview.rows_to_create} значений; 18 METHOD_BLOCKED + 24 RECODING_REQUIRED исключены. Сохраните точный ticket.`;
    } finally { setBusy(false); }
  }

  async function retainTicket(method) {
    if (!state.ticket || !state.ticketText) return;
    if (method === "copy") {
      await navigator.clipboard.writeText(state.ticketText);
    } else {
      const link = document.createElement("a");
      const location = URL.createObjectURL(new Blob([state.ticketText], {type: "application/json"}));
      link.href = location; link.download = `g8-import-ticket-${state.ticket.operation_id}.json`;
      link.click(); URL.revokeObjectURL(location);
    }
    state.ticketRetained = true;
    $("g8-ticket-ack").disabled = false;
    $("g8-import-state").textContent = "Точная квитанция выдана; подтвердите её сохранение и 42 исключения.";
    syncControls();
  }

  async function commitImport() {
    if (!state.selected || !state.preview || !state.file || !importReady()) {
      fail("G8_IMPORT_ACK_REQUIRED");
    }
    const previewResult = state.preview, ticket = state.ticket;
    const metadata = {profile_id: PROFILE, sheet: previewResult.sheet,
      source_column: previewResult.source_column,
      preview_sha256: previewResult.preview_sha256,
      excluded_42_acknowledged: true, ticket};
    setBusy(true, "Атомарный импорт…");
    try {
      await request(`experiments/${state.selected.id}/xlsx-import/`, {
        method: "POST", headers: {"Idempotency-Key": ticket.operation_id,
          "If-Match": quoted(previewResult.preview_sha256)}, body: multipart(state.file, metadata),
      });
      await loadValues(); await loadComparison(); invalidatePreview("");
    } finally { setBusy(false, "Импорт завершён; квитанция сохранена."); }
  }

  async function recoverTicket() {
    if (!state.selected) fail("PLAYER_NOT_FOUND");
    const operationId = $("g8-recovery-operation").value.trim();
    if (!UUID.test(operationId)) fail("PLAYER_REQUEST_INVALID");
    setBusy(true, "Восстанавливаем сохранённую квитанцию…");
    try {
      const receipt = await request(
        `experiments/${state.selected.id}/imports/${operationId}/`,
      );
      const output = $("g8-recovery-result");
      output.textContent = canonical(receipt);
      output.hidden = false;
    } finally { setBusy(false, "Сохранённая квитанция восстановлена."); }
  }

  $("experiment-plus").addEventListener("click", () => {
    if (!state.busy && app.dataset.projectionStatus === "COMPLETE") $("g8-create-dialog").showModal();
  });
  $("g8-create-cancel").addEventListener("click", () => $("g8-create-dialog").close());
  $("g8-create-form").addEventListener("submit", event => create(event)
    .catch(error => $("g8-create-state").textContent = error.message));
  $("g8-freeze").addEventListener("click", () => transition("freeze")
    .catch(error => $("g8-import-state").textContent = error.message));
  $("g8-archive").addEventListener("click", () => transition("archive")
    .catch(error => $("g8-import-state").textContent = error.message));
  $("g8-preview").addEventListener("click", () => preview()
    .catch(error => { state.busy = false; syncControls(); $("g8-import-state").textContent = error.message; }));
  $("g8-import").addEventListener("click", () => commitImport()
    .catch(error => { state.busy = false; syncControls(); $("g8-import-state").textContent = error.message; }));
  $("g8-ticket-copy").addEventListener("click", () => retainTicket("copy")
    .catch(error => $("g8-import-state").textContent = error.message));
  $("g8-ticket-download").addEventListener("click", () => retainTicket("download")
    .catch(error => $("g8-import-state").textContent = error.message));
  $("g8-recover-ticket").addEventListener("click", () => recoverTicket()
    .catch(error => { state.busy = false; syncControls(); $("g8-import-state").textContent = error.message; }));
  $("g8-ticket-ack").addEventListener("change", syncControls);
  $("g8-manual-form").addEventListener("submit", event => submitManual(event)
    .catch(error => { state.busy = false; syncControls(); $("g8-manual-state").textContent = error.message; }));
  $("g8-manual-cancel").addEventListener("click", () => cancelCorrection());
  $("g8-comparison-refresh").addEventListener("click", () => loadComparison().catch(() => {}));
  $("experiment-general").addEventListener("click", () => select("general"));
  for (const id of ["g8-file", "g8-import-profile", "g8-sheet", "g8-source-column"]) {
    $(id).addEventListener("change", () => {
      if (id === "g8-file") state.file = null;
      invalidatePreview();
    });
  }
  $("g8-manual-status").addEventListener("change", () => {
    const unknown = $("g8-manual-status").value === "UNKNOWN";
    $("g8-manual-number").disabled = state.busy || state.selected?.status !== "DRAFT" || unknown;
    if (unknown) $("g8-manual-number").value = "";
  });

  const loadOrClear = () => loadExperiments().catch(() => clearWorkspaceView());
  const observer = new MutationObserver(loadOrClear);
  observer.observe(app, {attributes: true,
    attributeFilter: ["data-state", "data-workspace-id", "data-projection-status"]});
  loadOrClear();
})();
