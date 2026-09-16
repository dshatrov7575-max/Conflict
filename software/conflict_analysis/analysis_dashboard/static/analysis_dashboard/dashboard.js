(() => {
  "use strict";
  const app = document.getElementById("analysis-app");
  if (!app) return;

  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
  const state = {
    context: null,
    project: app.dataset.projectId,
    workspace: app.dataset.workspaceId,
    series: [],
    selectedValue: null,
  };
  const lanes = Object.fromEntries(
    ["context", "timeline", "matrix", "evidence", "detail"].map((name) => [
      name, {epoch: 0, controller: null, identity: ""},
    ]),
  );
  const $ = (id) => document.getElementById(id);
  const text = (id, value) => {
    const node = $(id);
    if (node) node.textContent = value == null ? "—" : String(value);
  };

  function beginLane(name, identity) {
    const lane = lanes[name];
    lane.controller?.abort();
    lane.epoch += 1;
    lane.controller = new AbortController();
    lane.identity = identity;
    return Object.freeze({
      name,
      epoch: lane.epoch,
      identity,
      signal: lane.controller.signal,
    });
  }
  function current(token) {
    const lane = lanes[token.name];
    return lane.epoch === token.epoch && lane.identity === token.identity && !token.signal.aborted;
  }
  function abortLane(name) {
    const lane = lanes[name];
    lane.controller?.abort();
    lane.epoch += 1;
    lane.identity = "";
    lane.controller = null;
  }
  const isAbort = (error) => error?.name === "AbortError";

  // Preserve exact number tokens. Re-parsing a canonical Python JSON number as
  // a JavaScript Number and re-stringifying it can change exponent notation.
  function parseExact(source) {
    let offset = 0;
    const fail = () => { throw new Error("ANALYSIS_RESPONSE_JSON_INVALID"); };
    const whitespace = () => {
      while (/[\x20\x09\x0a\x0d]/.test(source[offset] || "")) offset += 1;
    };
    const string = () => {
      const start = offset;
      if (source[offset++] !== '"') fail();
      while (offset < source.length) {
        const character = source[offset++];
        if (character === '"') {
          return {kind: "string", value: JSON.parse(source.slice(start, offset))};
        }
        if (character.charCodeAt(0) < 32) fail();
        if (character === "\\") {
          const escaped = source[offset++];
          if (escaped === "u") {
            if (!/^[0-9a-fA-F]{4}$/.test(source.slice(offset, offset+4))) fail();
            offset += 4;
          } else if (!'"\\/bfnrt'.includes(escaped || "\0")) {
            fail();
          }
        }
      }
      return fail();
    };
    const value = () => {
      whitespace();
      if (source[offset] === '"') return string();
      if (source[offset] === "{") {
        offset += 1;
        whitespace();
        const entries = [];
        const seen = new Set();
        if (source[offset] === "}") {
          offset += 1;
          return {kind: "object", entries};
        }
        while (offset < source.length) {
          whitespace();
          const key = string().value;
          if (seen.has(key)) fail();
          seen.add(key);
          whitespace();
          if (source[offset++] !== ":") fail();
          entries.push([key, value()]);
          whitespace();
          const next = source[offset++];
          if (next === "}") return {kind: "object", entries};
          if (next !== ",") fail();
        }
        return fail();
      }
      if (source[offset] === "[") {
        offset += 1;
        whitespace();
        const items = [];
        if (source[offset] === "]") {
          offset += 1;
          return {kind: "array", items};
        }
        while (offset < source.length) {
          items.push(value());
          whitespace();
          const next = source[offset++];
          if (next === "]") return {kind: "array", items};
          if (next !== ",") fail();
        }
        return fail();
      }
      const match = source.slice(offset).match(
        /^(?:true|false|null|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)/,
      );
      if (!match) return fail();
      offset += match[0].length;
      return {kind: "raw", raw: match[0]};
    };
    const syntax = value();
    whitespace();
    if (offset !== source.length) fail();
    return {value: JSON.parse(source), syntax};
  }
  const compareKeys = (a, b) => {
    const left = Array.from(a, (item) => item.codePointAt(0));
    const right = Array.from(b, (item) => item.codePointAt(0));
    for (let index = 0; index < Math.min(left.length, right.length); index += 1) {
      if (left[index] !== right[index]) return left[index] - right[index];
    }
    return left.length - right.length;
  };
  function canonical(node, omitted = null) {
    if (!node) throw new Error("ANALYSIS_RESPONSE_SHAPE_INVALID");
    if (node.kind === "raw") return node.raw;
    if (node.kind === "string") return JSON.stringify(node.value);
    if (node.kind === "array") return `[${node.items.map((item) => canonical(item)).join(",")}]`;
    return `{${node.entries
      .filter(([key]) => !omitted?.has(key))
      .sort(([a], [b]) => compareKeys(a, b))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
      .join(",")}}`;
  }
  const digest = async (source) => Array.from(
    new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(source))),
    (byte) => byte.toString(16).padStart(2, "0"),
  ).join("");

  async function read(path, {verify = true, signal} = {}) {
    const url = new URL(path, location.origin);
    if (url.origin !== location.origin || url.username || url.password || url.hash) {
      throw new Error("ANALYSIS_ENDPOINT_INVALID");
    }
    const response = await fetch(url.pathname+url.search, {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
      redirect: "error",
      headers: {Accept: "application/json"},
      signal,
    });
    const raw = await response.text();
    if (!response.headers.get("Content-Type")?.toLowerCase().startsWith("application/json")) {
      throw new Error("ANALYSIS_RESPONSE_INTEGRITY_CONFLICT");
    }
    const parsed = parseExact(raw);
    const body = parsed.value;
    if (!body || typeof body !== "object" || Array.isArray(body)) {
      throw new Error("ANALYSIS_RESPONSE_INTEGRITY_CONFLICT");
    }
    if (verify) {
      if (response.headers.get("ETag") !== `"${await digest(raw)}"`) {
        throw new Error("ANALYSIS_RESPONSE_INTEGRITY_CONFLICT");
      }
      if (canonical(parsed.syntax) !== raw) {
        throw new Error("ANALYSIS_RESPONSE_NONCANONICAL");
      }
    }
    if (!response.ok) {
      if (
        Object.keys(body).sort().join(",") !== "code,errors"
        || typeof body.code !== "string"
        || !/^[A-Z0-9_]{1,100}$/.test(body.code)
        || !Array.isArray(body.errors)
        || body.errors.length !== 1
        || typeof body.errors[0] !== "string"
      ) {
        throw new Error("ANALYSIS_RESPONSE_ERROR_UNVERIFIED");
      }
      throw new Error(body.code);
    }
    if (verify) {
      if (
        typeof body.response_sha256 !== "string"
        || !/^[0-9a-f]{64}$/.test(body.response_sha256)
        || await digest(canonical(parsed.syntax, new Set(["response_sha256"]))) !== body.response_sha256
      ) {
        throw new Error("ANALYSIS_RESPONSE_INTEGRITY_CONFLICT");
      }
    }
    return body;
  }

  function resolutionClass() {
    const width = window.innerWidth;
    if (width < 900) return "compact-800";
    if (width < 1200) return "compact-1024";
    if (width < 1700) return "standard-1366";
    if (width < 2300) return "fullhd-1920";
    return "large-2560";
  }
  const defaults = Object.freeze({
    version: "ANALYSIS_LAYOUT_V1",
    graph_height: 320,
    list_height: 230,
    sidebar_width: 190,
    font_scale: 1,
    fit_graph_and_list: true,
  });
  const bounds = Object.freeze({
    graph_height: [180, 720],
    list_height: [130, 600],
    sidebar_width: [150, 300],
    font_scale: [0.85, 1.4],
  });
  const layoutKeys = Object.freeze([
    "fit_graph_and_list",
    "font_scale",
    "graph_height",
    "list_height",
    "sidebar_width",
    "version",
  ]);
  const clamp = (value, [minimum, maximum], fallback) => (
    Number.isFinite(value) ? Math.max(minimum, Math.min(maximum, value)) : fallback
  );
  function normalizedLayout(raw) {
    const exactKeys = raw && typeof raw === "object" && !Array.isArray(raw)
      && Object.keys(raw).sort().join("|") === layoutKeys.join("|");
    if (!exactKeys || raw.version !== defaults.version) {
      return {...defaults};
    }
    return {
      version: defaults.version,
      graph_height: clamp(Number(raw.graph_height), bounds.graph_height, defaults.graph_height),
      list_height: clamp(Number(raw.list_height), bounds.list_height, defaults.list_height),
      sidebar_width: clamp(Number(raw.sidebar_width), bounds.sidebar_width, defaults.sidebar_width),
      font_scale: clamp(Number(raw.font_scale), bounds.font_scale, defaults.font_scale),
      fit_graph_and_list: raw.fit_graph_and_list === true,
    };
  }
  let activeResolutionClass = resolutionClass();
  const layoutKey = () => `conflict-analysis:analysis-layout:v1:${activeResolutionClass}`;
  function applyLayout(value) {
    document.documentElement.style.setProperty("--chart-height", `${value.graph_height}px`);
    document.documentElement.style.setProperty("--list-height", `${value.list_height}px`);
    document.documentElement.style.setProperty("--sidebar-width", `${value.sidebar_width}px`);
    document.documentElement.style.setProperty("--font-scale", String(value.font_scale));
  }
  function loadLayout() {
    let value = {...defaults};
    try {
      value = normalizedLayout(JSON.parse(localStorage.getItem(layoutKey()) || "null"));
    } catch (_) {
      value = {...defaults};
    }
    applyLayout(value);
    return value;
  }
  let layout = loadLayout();
  function syncLayoutControls() {
    for (const [id, key, format] of [
      ["chart-height", "graph_height", (value) => `${value}px`],
      ["list-height", "list_height", (value) => `${value}px`],
      ["sidebar-width", "sidebar_width", (value) => `${value}px`],
      ["font-scale", "font_scale", (value) => `${Math.round(value*100)}%`],
    ]) {
      const input = $(id);
      const output = $(`${id}-output`);
      if (!input) continue;
      input.value = key === "font_scale" ? Math.round(layout[key]*100) : layout[key];
      if (output) output.textContent = format(layout[key]);
    }
    if ($("fit-viewport")) $("fit-viewport").checked = layout.fit_graph_and_list;
  }
  function storeLayout() {
    layout = normalizedLayout(layout);
    try {
      localStorage.setItem(layoutKey(), JSON.stringify(layout));
    } catch (_) {
      // Presentation remains usable even when storage is unavailable or full.
    }
    applyLayout(layout);
    syncLayoutControls();
  }
  function fitViewport() {
    if (!layout.fit_graph_and_list) return;
    const available = Math.max(350, window.innerHeight-58-110);
    layout.graph_height = clamp(Math.round(available*0.57), bounds.graph_height, defaults.graph_height);
    layout.list_height = clamp(available-layout.graph_height-7, bounds.list_height, defaults.list_height);
    storeLayout();
  }
  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      const next = resolutionClass();
      if (next !== activeResolutionClass) {
        activeResolutionClass = next;
        layout = loadLayout();
      }
      if (layout.fit_graph_and_list) fitViewport();
    }, 80);
  });

  $("layout-settings")?.addEventListener("click", () => {
    $("layout-dialog").showModal();
    syncLayoutControls();
  });
  for (const [id, key] of [
    ["chart-height", "graph_height"],
    ["list-height", "list_height"],
    ["sidebar-width", "sidebar_width"],
    ["font-scale", "font_scale"],
  ]) {
    $(id)?.addEventListener("input", (event) => {
      layout[key] = key === "font_scale" ? Number(event.target.value)/100 : Number(event.target.value);
      layout.fit_graph_and_list = false;
      storeLayout();
    });
  }
  $("fit-viewport")?.addEventListener("change", (event) => {
    layout.fit_graph_and_list = event.target.checked;
    storeLayout();
    fitViewport();
  });
  $("layout-reset")?.addEventListener("click", () => {
    layout = {...defaults};
    storeLayout();
    fitViewport();
  });
  const splitter = $("horizontal-splitter");
  let drag = null;
  splitter?.addEventListener("pointerdown", (event) => {
    drag = {y: event.clientY, height: layout.graph_height};
    splitter.setPointerCapture(event.pointerId);
  });
  splitter?.addEventListener("pointermove", (event) => {
    if (!drag) return;
    layout.graph_height = clamp(drag.height+event.clientY-drag.y, bounds.graph_height, defaults.graph_height);
    layout.fit_graph_and_list = false;
    storeLayout();
  });
  splitter?.addEventListener("pointerup", () => { drag = null; });
  splitter?.addEventListener("keydown", (event) => {
    if (!["ArrowUp", "ArrowDown"].includes(event.key)) return;
    event.preventDefault();
    layout.graph_height = clamp(
      layout.graph_height+(event.key === "ArrowDown" ? 10 : -10),
      bounds.graph_height,
      defaults.graph_height,
    );
    layout.fit_graph_and_list = false;
    storeLayout();
  });

  function options(id, rows, value, label) {
    const select = $(id);
    select.replaceChildren();
    for (const row of rows) {
      const option = document.createElement("option");
      option.value = value(row);
      option.textContent = label(row);
      select.append(option);
    }
  }
  function endpoint(name, query = "") {
    return `/api/foundation/analysis/v1/projects/${state.project}/workspaces/${state.workspace}/${name}/${query}`;
  }
  function setView(name) {
    document.querySelectorAll("[data-view-panel]").forEach((node) => {
      node.hidden = node.dataset.viewPanel !== name;
    });
    document.querySelectorAll("[data-view]").forEach((node) => {
      node.classList.toggle("active", node.dataset.view === name);
    });
    app.dispatchEvent(new CustomEvent("analysis:view", {detail: {name}}));
  }
  document.querySelectorAll("[data-view]").forEach((node) => {
    node.addEventListener("click", () => setView(node.dataset.view));
  });
  function technical() {
    const root = $("technical-details");
    const context = state.context;
    root.replaceChildren();
    if (!context) return;
    const values = {
      "Project UUID": context.project.id,
      "Workspace UUID": context.workspace.id,
      "Definition UUID": context.workspace.definition_id,
      "Manifest SHA-256": context.workspace.definition_manifest_hash,
      "Projection": context.workspace.assessment_projection_status,
      "Projection SHA-256": context.workspace.assessment_projection_sha256,
      "Общий показатель": context.method_state.project_total_score,
      "Региональный агрегат": context.method_state.regional_aggregate,
    };
    for (const [key, value] of Object.entries(values)) {
      const dt = document.createElement("dt");
      const dd = document.createElement("dd");
      dt.textContent = key;
      dd.textContent = value;
      root.append(dt, dd);
    }
  }

  function clearEvidence() {
    state.selectedValue = null;
    abortLane("evidence");
    abortLane("detail");
    $("fact-list")?.replaceChildren();
    text("evidence-detail", "");
    text("evidence-state", "Выберите сохранённую точку временного ряда или ячейку матрицы.");
  }
  function invalidateSelection() {
    abortLane("timeline");
    abortLane("matrix");
    clearEvidence();
  }

  async function loadContext() {
    const identity = `${state.project}|${state.workspace}`;
    const token = beginLane("context", identity);
    const context = await read(endpoint("context"), {signal: token.signal});
    if (!current(token)) return;
    state.context = context;
    text("project-name", context.project.name);
    text("workspace-name", context.workspace.name);
    options("experiment-one", context.experiments, (row) => row.id, (row) => `${row.kind} · ${row.name}`);
    options("experiment-two", context.experiments, (row) => row.id, (row) => `${row.kind} · ${row.name}`);
    options("matrix-experiment", context.experiments, (row) => row.id, (row) => `${row.kind} · ${row.name}`);
    options("actor-select", context.actors, (row) => row.code, (row) => `${row.code} · ${row.label}`);
    options("element-select", context.analytical_elements, (row) => row.code, (row) => `${row.code} · ${row.label}`);
    options("parameter-select", context.parameters, (row) => row.code, (row) => `${row.code} · ${row.name}`);
    options("matrix-parameter", context.parameters, (row) => row.code, (row) => `${row.code} · ${row.name}`);
    options("matrix-slice", context.time_slices, (row) => row.id, (row) => `${row.cutoff_date} · ${row.code}`);
    if (context.experiments.length > 1) $("experiment-two").selectedIndex = 1;
    technical();
    $("analysis-state").hidden = true;
    if (!context.experiments.length) {
      text("row-summary", "Нет доступных HUMAN/AI экспериментов");
      app.dataset.state = "ready";
      return;
    }
    if (await loadTimeline()) app.dataset.state = "ready";
  }
  function query(entries) {
    const result = new URLSearchParams();
    for (const [key, value] of entries) result.append(key, value);
    return `?${result}`;
  }
  function timelineSelection() {
    const mode = $("mode-select").value;
    return {
      mode,
      experimentOne: $("experiment-one").value,
      experimentTwo: $("experiment-two").value,
      actor: $("actor-select").value,
      element: $("element-select").value,
      parameter: $("parameter-select").value,
    };
  }
  async function loadTimeline() {
    clearEvidence();
    const selection = timelineSelection();
    const identity = JSON.stringify([state.project, state.workspace, selection]);
    const token = beginLane("timeline", identity);
    const common = [
      ["actor_code", selection.actor],
      ["element_code", selection.element],
      ["parameter_code", selection.parameter],
    ];
    let body;
    if (selection.mode === "comparison") {
      body = await read(endpoint("comparison", query([
        ["experiment_id", selection.experimentOne],
        ["experiment_id", selection.experimentTwo],
        ...common,
      ])), {signal: token.signal});
    } else {
      body = await read(endpoint("timeline", query([
        ["experiment_id", selection.experimentOne],
        ...common,
      ])), {signal: token.signal});
    }
    if (!current(token) || identity !== JSON.stringify([state.project, state.workspace, timelineSelection()])) return;
    state.series = selection.mode === "comparison" ? body.series : [body.series];
    return renderTimeline();
  }
  function renderTimeline() {
    const first = state.series[0];
    const parameter = first?.parameter;
    if (!parameter) return;
    text("chart-title", `${parameter.code}: ${first.actor.code} · ${first.actor.label} / ${first.analytical_element.label}`);
    window.AnalysisCharts.render($("chart"), state.series, parameter);
    const legend = $("legend");
    legend.replaceChildren();
    for (const series of state.series) {
      const item = document.createElement("span");
      const swatch = document.createElement("i");
      swatch.style.background = series.experiment.color;
      item.append(swatch, document.createTextNode(`${series.experiment.kind} · ${series.experiment.name}`));
      legend.append(item);
    }
    const rows = state.series.flatMap((series) => series.points.map((point) => ({series, point})))
      .sort((left, right) => left.point.cutoff_date.localeCompare(right.point.cutoff_date));
    const tbody = $("timeline-table").querySelector("tbody");
    tbody.replaceChildren();
    let persisted = 0;
    for (const {series, point} of rows) {
      const tr = document.createElement("tr");
      const status = point.record_state === "NO_RECORD" ? "NO_RECORD" : point.status;
      const display = point.value === null ? "—" : point.value;
      const evidence = point.parameter_value_id ? "Открыть" : "—";
      if (point.parameter_value_id) {
        persisted += 1;
        tr.dataset.valueId = point.parameter_value_id;
        tr.tabIndex = 0;
        tr.addEventListener("click", () => selectValue(tr, point));
        tr.addEventListener("keydown", (event) => {
          if (["Enter", " "].includes(event.key)) {
            event.preventDefault();
            selectValue(tr, point);
          }
        });
      } else {
        tr.classList.add("no-record");
      }
      for (const value of [
        point.cutoff_date,
        `${series.experiment.kind} · ${series.experiment.name}`,
        display,
        status,
        point.confidence_category || "—",
        evidence,
      ]) {
        const td = document.createElement("td");
        td.textContent = String(value ?? "—");
        if (value === status) td.className = `status-${status}`;
        tr.append(td);
      }
      tbody.append(tr);
    }
    text("row-summary", `${persisted} сохранённых точек · ${rows.length-persisted} без записи`);
    return true;
  }
  function selectValue(row, point) {
    if (!point.parameter_value_id) return;
    document.querySelectorAll("#timeline-table tbody tr").forEach((item) => item.setAttribute("aria-selected", "false"));
    row.setAttribute("aria-selected", "true");
    state.selectedValue = point.parameter_value_id;
    setView("evidence");
    loadEvidence(point.parameter_value_id).catch(handleFailure);
  }
  async function loadEvidence(valueId) {
    abortLane("detail");
    const identity = `${state.project}|${state.workspace}|${valueId}`;
    const token = beginLane("evidence", identity);
    $("fact-list").replaceChildren();
    text("evidence-detail", "");
    text("evidence-state", "Проверяем доступ к связанным фактам…");
    const list = await read(
      `/api/foundation/projects/${state.project}/workspaces/${state.workspace}/parameter-values/${valueId}/facts/`,
      {verify: false, signal: token.signal},
    );
    if (!current(token) || state.selectedValue !== valueId) return;
    const root = $("fact-list");
    text("evidence-state", list.facts.length ? `Доступно фактов: ${list.facts.length}` : "Доступные доказательства не найдены.");
    for (const fact of list.facts) {
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `${fact.code} · ${fact.statement}`;
      button.addEventListener("click", () => loadEvidenceDetail(valueId, fact.id).catch(handleFailure));
      li.append(button);
      root.append(li);
    }
  }
  async function loadEvidenceDetail(valueId, factId) {
    const identity = `${state.project}|${state.workspace}|${valueId}|${factId}`;
    const token = beginLane("detail", identity);
    text("evidence-detail", "Проверяем точный источник…");
    const detail = await read(
      `/api/foundation/projects/${state.project}/workspaces/${state.workspace}/facts/${factId}/evidence/`,
      {verify: false, signal: token.signal},
    );
    if (!current(token) || state.selectedValue !== valueId) return;
    $("evidence-detail").textContent = JSON.stringify(detail, null, 2);
  }
  function matrixSelection() {
    return {
      experiment: $("matrix-experiment").value,
      timeSlice: $("matrix-slice").value,
      parameter: $("matrix-parameter").value,
    };
  }
  async function loadMatrix() {
    clearEvidence();
    const selection = matrixSelection();
    const identity = JSON.stringify([state.project, state.workspace, selection]);
    const token = beginLane("matrix", identity);
    const body = await read(endpoint("matrix", query([
      ["experiment_id", selection.experiment],
      ["time_slice_id", selection.timeSlice],
      ["parameter_code", selection.parameter],
    ])), {signal: token.signal});
    if (!current(token) || identity !== JSON.stringify([state.project, state.workspace, matrixSelection()])) return;
    const table = document.createElement("table");
    table.className = "matrix-table";
    const head = document.createElement("thead");
    const headRow = document.createElement("tr");
    const corner = document.createElement("th");
    corner.textContent = "Актор / элемент";
    headRow.append(corner);
    for (const element of body.analytical_elements) {
      const th = document.createElement("th");
      th.textContent = element.code;
      th.title = element.label;
      headRow.append(th);
    }
    head.append(headRow);
    table.append(head);
    const tbody = document.createElement("tbody");
    const byPair = new Map(body.cells.map((cell) => [`${cell.actor_code}|${cell.element_code}`, cell]));
    for (const actor of body.actors) {
      const tr = document.createElement("tr");
      const th = document.createElement("td");
      th.textContent = `${actor.code} · ${actor.label}`;
      tr.append(th);
      for (const element of body.analytical_elements) {
        const cell = byPair.get(`${actor.code}|${element.code}`);
        const td = document.createElement("td");
        const button = document.createElement("button");
        td.className = "matrix-cell";
        td.dataset.status = cell.status || "";
        td.dataset.recordState = cell.record_state;
        button.type = "button";
        button.textContent = cell.record_state === "NO_RECORD" ? "—" : cell.value === null ? cell.status : String(cell.value);
        button.disabled = !cell.parameter_value_id;
        button.addEventListener("click", () => {
          state.selectedValue = cell.parameter_value_id;
          setView("evidence");
          loadEvidence(cell.parameter_value_id).catch(handleFailure);
        });
        td.append(button);
        tr.append(td);
      }
      tbody.append(tr);
    }
    table.append(tbody);
    $("matrix-table").replaceChildren(table);
  }

  $("mode-select")?.addEventListener("change", () => {
    $("experiment-two-label").hidden = $("mode-select").value !== "comparison";
    invalidateSelection();
  });
  for (const id of ["experiment-one", "experiment-two", "actor-select", "element-select", "parameter-select"]) {
    $(id)?.addEventListener("change", invalidateSelection);
  }
  for (const id of ["matrix-experiment", "matrix-slice", "matrix-parameter"]) {
    $(id)?.addEventListener("change", () => {
      abortLane("matrix");
      clearEvidence();
    });
  }
  $("apply-selection")?.addEventListener("click", () => loadTimeline().catch(handleFailure));
  $("load-matrix")?.addEventListener("click", () => loadMatrix().catch(handleFailure));

  function fail(error) {
    app.dataset.state = "error";
    $("analysis-state").hidden = false;
    text("analysis-state", error?.message || "ANALYSIS_UNAVAILABLE");
  }
  function handleFailure(error) {
    if (!isAbort(error)) fail(error);
  }
  function entry() {
    app.dataset.state = "entry";
    $("entry-panel").hidden = false;
    $("entry-form").addEventListener("submit", (event) => {
      event.preventDefault();
      const project = $("entry-project").value.trim();
      const workspace = $("entry-workspace").value.trim();
      if (!UUID.test(project) || !UUID.test(workspace)) {
        $("entry-error").hidden = false;
        return;
      }
      location.assign(`/analysis/projects/${project}/workspaces/${workspace}/`);
    });
  }

  if (app.dataset.authenticated !== "true") {
    app.dataset.state = "unauthorized";
    $("auth-panel").hidden = false;
    return;
  }
  if (!UUID.test(state.project) || !UUID.test(state.workspace)) {
    entry();
    return;
  }
  $("workspace-shell").hidden = false;
  fitViewport();
  loadContext().catch(handleFailure);
})();
