/* G9 evidence composition: authorized Foundation GETs and memory-only display. */
(() => {
  "use strict";

  const app = document.getElementById("player-app");
  const workspace = document.getElementById("workspace-content");
  const template = document.getElementById("g9-evidence-template");
  const panel = document.getElementById("panel-document");
  const tab = document.getElementById("tab-document");
  if (!app || !workspace || !template || !panel || !tab || workspace.dataset.g8Shell !== "true") return;

  const API = "/api/foundation/";
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  const KINDS = new Set(["parameter-value", "actor-element-assessment"]);
  const NO_ORIGINAL = "Точное соответствие оригиналу не подтверждено";
  const state = {
    entry: null, focusNode: null, facts: [], fact: null, drilldown: null,
    evidence: null, fragment: null, document: null, requestToken: 0, controller: null,
    pendingHistory: !!history.state?.g9,
  };
  panel.replaceChildren(template.content.cloneNode(true));
  tab.textContent = "Доказательства";
  tab.title = "Связанные факты и точные доказательства";
  tab.setAttribute("aria-disabled", "false");
  const $ = (id) => document.getElementById(id);

  function bdi(value) {
    const node = document.createElement("bdi");
    node.dir = "auto";
    node.textContent = value == null || value === "" ? "—" : String(value);
    return node;
  }

  async function sha256Text(value) {
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
    return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
  }

  async function exactFragmentOrThrow(source) {
    const text = source?.exact_text;
    const start = source?.start_offset;
    const end = source?.end_offset;
    if (!source || source.anchor_status !== "EXACT" || !UUID.test(source.fragment_id || "")
        || !UUID.test(source.content_variant_id || "") || typeof text !== "string"
        || !Number.isSafeInteger(start) || !Number.isSafeInteger(end)
        || start < 0 || end <= start || Array.from(text).length !== end - start
        || !/^[0-9a-f]{64}$/i.test(source.text_sha256 || "")
        || await sha256Text(text) !== source.text_sha256.toLowerCase()) {
      throw new Error("PLAYER_EXACT_FRAGMENT_INVALID");
    }
    return text;
  }

  function exactContext() {
    const projectId = workspace.dataset.caProjectId || "";
    const workspaceId = workspace.dataset.caWorkspaceId || "";
    if (!UUID.test(projectId) || !UUID.test(workspaceId) || app.dataset.workspaceId !== workspaceId) return null;
    return {projectId, workspaceId};
  }

  function requestIdentity(extra = {}) {
    const context = exactContext();
    if (!context || !state.entry) return null;
    return {...context, kind: state.entry.kind, entryId: state.entry.id, ...extra};
  }

  function sameIdentity(left, right) {
    if (!left || !right) return false;
    const keys = Object.keys(left);
    return keys.length === Object.keys(right).length && keys.every(key => left[key] === right[key]);
  }

  function abortRead() {
    state.requestToken += 1;
    if (state.controller) state.controller.abort();
    state.controller = null;
  }

  function clearConfidential(message = "Выберите значение или оценку в рабочей области.", keepEntry = false) {
    abortRead();
    state.facts = [];
    state.fact = null;
    state.drilldown = null;
    state.evidence = null;
    state.fragment = null;
    state.document = null;
    if (!keepEntry) {
      state.entry = null;
      state.focusNode = null;
    }
    $("g9-fact-list").replaceChildren();
    $("g9-evidence-list").replaceChildren();
    $("g9-detail").replaceChildren();
    $("g9-state").textContent = message;
    syncCommands();
  }

  function syncCommands() {
    $("g9-related").disabled = !state.entry;
    $("g9-related").hidden = !state.entry || !!state.fact;
    $("g9-open-fact").disabled = !state.fact;
    $("g9-open-fact").hidden = !state.fact || !!state.drilldown;
    $("g9-open-fragment").disabled = !state.evidence;
    $("g9-open-fragment").hidden = !state.evidence;
    $("g9-open-document").disabled = !state.document;
    $("g9-open-document").hidden = !state.document;
    const original = state.evidence?.original;
    $("g9-show-original").disabled = !original;
    $("g9-show-original").hidden = !state.evidence;
    $("g9-original-reason").textContent = original ? "" : NO_ORIGINAL;
    $("g9-original-reason").hidden = !state.evidence || !!original;
    const external = safeExternalURL(state.document?.canonical_url || state.document?.source?.homepage_url);
    $("g9-open-external").disabled = !external;
    $("g9-open-external").hidden = !external;
  }

  async function read(path, identity) {
    abortRead();
    const token = state.requestToken;
    const controller = new AbortController();
    state.controller = controller;
    const response = await fetch(API + path, {
      method: "GET", credentials: "same-origin", cache: "no-store", redirect: "error",
      headers: {Accept: "application/json"}, signal: controller.signal,
    });
    const payload = await response.json();
    if (token !== state.requestToken || !sameIdentity(identity, requestIdentity(
      identity.factId ? {factId: identity.factId} : {}
    ))) throw new DOMException("Stale evidence response", "AbortError");
    if (!response.ok) {
      const error = new Error("PLAYER_EVIDENCE_UNAVAILABLE");
      error.httpStatus = response.status;
      throw error;
    }
    return payload;
  }

  function selectOption(list, item, value) {
    list.querySelectorAll("[role=option]").forEach(node => node.setAttribute("aria-selected", String(node === item)));
    value();
    syncCommands();
  }

  function option(label, onSelect) {
    const item = document.createElement("li");
    item.setAttribute("role", "option");
    item.setAttribute("aria-selected", "false");
    item.tabIndex = 0;
    item.append(bdi(label));
    const choose = () => selectOption(item.parentElement, item, onSelect);
    item.addEventListener("click", choose);
    item.addEventListener("keydown", event => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); choose(); }
    });
    return item;
  }

  function metadata(rows) {
    const list = document.createElement("dl");
    list.className = "g9-evidence-meta";
    for (const [label, value] of rows) {
      const term = document.createElement("dt"); term.textContent = label;
      const detail = document.createElement("dd"); detail.append(bdi(value));
      list.append(term, detail);
    }
    return list;
  }

  function renderFacts(payload) {
    if (!payload || payload.entry?.kind !== state.entry.kind || payload.entry?.id !== state.entry.id
        || !["ACCESSIBLE_FACTS", "NO_ACCESSIBLE_FACT_EVIDENCE"].includes(payload.code)
        || !Array.isArray(payload.facts)) throw new Error("PLAYER_EVIDENCE_RESPONSE_INVALID");
    state.facts = payload.facts;
    state.fact = null;
    const list = $("g9-fact-list"); list.replaceChildren();
    for (const fact of state.facts) {
      if (!UUID.test(fact.id || "") || !Array.isArray(fact.entry_evidence)) throw new Error("PLAYER_EVIDENCE_RESPONSE_INVALID");
      const item = option(`${fact.code} · ${fact.statement}`, () => {
        abortRead();
        state.fact = fact; state.drilldown = null; state.evidence = null; state.fragment = null; state.document = null;
        $("g9-evidence-list").replaceChildren();
        $("g9-detail").replaceChildren();
        $("g9-state").textContent = "Факт выбран. Нажмите «Открыть факт».";
      });
      item.append(metadata([
        ["Тип факта", fact.fact_type],
        ["Категория", fact.category?.category?.code || "UNCLASSIFIED"],
        ["Классификация", fact.category?.classification_status || "UNCLASSIFIED"],
        ["Роли связи", fact.entry_evidence.map(link => link.role).join(", ")],
      ]));
      list.append(item);
    }
    $("g9-state").textContent = payload.code === "ACCESSIBLE_FACTS"
      ? `Доступных фактов: ${state.facts.length}` : "Доступных связанных фактов нет.";
  }

  function renderEvidence(payload) {
    if (!payload || payload.fact_id !== state.fact.id || !Array.isArray(payload.evidence)) throw new Error("PLAYER_EVIDENCE_RESPONSE_INVALID");
    state.drilldown = payload;
    state.evidence = null;
    state.fragment = null;
    state.document = null;
    const list = $("g9-evidence-list"); list.replaceChildren();
    for (const evidence of payload.evidence) {
      if (!UUID.test(evidence.fact_evidence_id || "")) throw new Error("PLAYER_EVIDENCE_RESPONSE_INVALID");
      const item = option(`${evidence.relation} · ${evidence.fact_evidence_code}`, () => {
        abortRead();
        state.evidence = evidence;
        state.fragment = evidence.project_primary || null;
        state.document = evidence.document || null;
        $("g9-detail").replaceChildren();
        $("g9-state").textContent = "Связь выбрана. Откройте точный фрагмент или документ.";
      });
      item.append(metadata([
        ["Связь", evidence.relation], ["Статус времени", evidence.temporal_status],
        ["Версия документа", evidence.document_version?.code],
        ["Фрагмент", evidence.project_primary?.fragment_code],
      ]));
      list.append(item);
    }
    $("g9-state").textContent = payload.code;
  }

  async function renderFragment(original = false) {
    const source = original ? state.evidence?.original : state.fragment;
    const text = original ? source?.excerpt : await exactFragmentOrThrow(source);
    if (!source || typeof text !== "string") return;
    const detail = $("g9-detail"); detail.replaceChildren();
    const heading = document.createElement("h3"); heading.textContent = original ? "Точный сохранённый оригинал" : "Точный сохранённый фрагмент";
    const quote = document.createElement("blockquote"); quote.className = "g9-fragment"; quote.append(bdi(text));
    detail.append(heading, quote, metadata([
      ["Fragment UUID", source.fragment_id],
      ["Fragment code", source.fragment_code],
      ["Variant UUID", source.variant_id || source.content_variant_id],
      ["Начало, code points", source.start_offset],
      ["Конец, code points", source.end_offset],
      ["SHA-256 точного текста", source.text_sha256],
      ["SHA-256 варианта", source.content_sha256],
      ["Alignment UUID", source.alignment_set_id],
      ["Alignment SHA-256", source.alignment_sha256],
    ]));
  }

  function renderDocument() {
    if (!state.document) return;
    const source = state.document.source || {};
    const detail = $("g9-detail"); detail.replaceChildren();
    const heading = document.createElement("h3"); heading.textContent = "Точная версия документа";
    detail.append(heading, metadata([
      ["Документ", state.document.code], ["UUID", state.document.id],
      ["Версия", state.document.version], ["Вид линии", state.document.lineage_kind],
      ["Источник", source.name || source.code], ["Издатель", source.publisher],
      ["Группа независимости", source.independence_group],
      ["Статус независимости", source.independence_status],
    ]));
  }

  function historyPayload(extra = {}) {
    const identity = requestIdentity(extra);
    return identity ? {g9: identity} : null;
  }

  function recordHistory(extra = {}) {
    const payload = historyPayload(extra);
    if (payload) history.pushState(payload, "", location.pathname + location.search);
  }

  function selectEntry(node) {
    const context = exactContext();
    const kind = node?.dataset.caFocusKind || "";
    const id = node?.dataset.caFocusId || "";
    if (!context || !KINDS.has(kind) || !UUID.test(id)) {
      clearConfidential("Точный объект не выбран.");
      return;
    }
    clearConfidential("Объект выбран. Нажмите «Связанные факты».");
    state.entry = {kind, id};
    state.focusNode = node;
    syncCommands();
    recordHistory();
  }

  async function related(record = true) {
    const identity = requestIdentity();
    if (!identity) return;
    $("g9-state").textContent = "Проверяем доступ к связанным фактам…";
    const segment = identity.kind === "parameter-value" ? `parameter-values/${identity.entryId}` : `assessments/${identity.entryId}`;
    try {
      const payload = await read(`projects/${identity.projectId}/workspaces/${identity.workspaceId}/${segment}/facts/`, identity);
      renderFacts(payload);
      if (record) recordHistory();
    } catch (error) {
      if (error.name !== "AbortError") clearConfidential("Связанные факты недоступны.", true);
    }
  }

  async function openFact(record = true) {
    if (!state.fact) return;
    const identity = requestIdentity({factId: state.fact.id});
    try {
      const payload = await read(`projects/${identity.projectId}/workspaces/${identity.workspaceId}/facts/${identity.factId}/evidence/`, identity);
      renderEvidence(payload);
      if (record) recordHistory({factId: identity.factId});
    } catch (error) {
      if (error.name !== "AbortError") clearConfidential("Доказательства факта недоступны.", true);
    }
  }

  function safeExternalURL(value) {
    try {
      const url = new URL(value);
      return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password ? url : null;
    } catch (_) { return null; }
  }

  function openExternal(value) {
    const url = safeExternalURL(value);
    if (!url || !window.confirm(`Открыть внешний адрес?\n${url.href}`)) return;
    const target = window.open(url.href, "_blank", "noopener,noreferrer");
    if (target) target.opener = null;
  }

  async function restoreHistory(event) {
    state.pendingHistory = false;
    clearConfidential("Повторно проверяем точный исторический контекст.");
    const saved = event.state?.g9;
    const context = exactContext();
    if (!saved || !context || saved.projectId !== context.projectId || saved.workspaceId !== context.workspaceId
        || !KINDS.has(saved.kind) || !UUID.test(saved.entryId || "")) return;
    state.entry = {kind: saved.kind, id: saved.entryId};
    syncCommands();
    await related(false);
    if (saved.factId && UUID.test(saved.factId)) {
      state.fact = state.facts.find(item => item.id === saved.factId) || null;
      if (state.fact) await openFact(false);
    }
  }

  document.addEventListener("click", event => {
    const node = event.target.closest("[data-ca-focus-kind], [data-ca-focus-id]");
    if (node && workspace.contains(node)) selectEntry(node);
  }, true);
  document.addEventListener("keydown", event => {
    if (!(["Enter", " "].includes(event.key))) return;
    const node = event.target.closest("[data-ca-focus-kind], [data-ca-focus-id]");
    if (node && workspace.contains(node)) selectEntry(node);
  }, true);
  $("g9-related").addEventListener("click", related);
  $("g9-open-fact").addEventListener("click", openFact);
  $("g9-open-fragment").addEventListener("click", () => {
    renderFragment(false)
      .then(() => recordHistory({factId: state.fact?.id}))
      .catch(() => clearConfidential("Точный фрагмент недоступен.", true));
  });
  $("g9-open-document").addEventListener("click", () => {renderDocument(); recordHistory({factId: state.fact?.id});});
  $("g9-show-original").addEventListener("click", () => {
    renderFragment(true).catch(() => clearConfidential("Точный оригинал недоступен.", true));
  });
  $("g9-open-external").addEventListener("click", () => openExternal(state.document?.canonical_url || state.document?.source?.homepage_url));
  window.addEventListener("popstate", event => restoreHistory(event).catch(() => clearConfidential("Исторический контекст недоступен.")));
  const observer = new MutationObserver(() => {
    if (!exactContext() || (state.focusNode && !document.contains(state.focusNode))) clearConfidential();
    if (state.pendingHistory && exactContext()) restoreHistory({state: history.state})
      .catch(() => clearConfidential("Исторический контекст недоступен."));
  });
  observer.observe(app, {attributes: true, attributeFilter: ["data-workspace-id", "data-state", "data-authenticated"]});
  observer.observe(workspace, {attributes: true, attributeFilter: ["data-ca-project-id", "data-ca-workspace-id"], childList: true, subtree: true});
  syncCommands();
  if (state.pendingHistory && exactContext()) restoreHistory({state: history.state})
    .catch(() => clearConfidential("Исторический контекст недоступен."));
})();
