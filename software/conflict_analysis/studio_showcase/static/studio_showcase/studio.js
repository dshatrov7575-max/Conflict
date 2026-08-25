(function () {
  "use strict";

  const SESSION_FORMAT = "SHOWCASE_SESSION_V1";
  const SESSION_VERSION = "1.0.0";
  const LAYOUT_KEY = "conflict-analysis-studio:layout:v1";
  const LAYOUT_VERSION = "STUDIO_LAYOUT_V1";
  const DEFAULT_LAYOUT = Object.freeze({ left: 272, right: 360, activeRightTab: "document" });
  const WIDTH_LIMITS = Object.freeze({ left: [220, 420], right: [300, 500] });
  const RIGHT_TABS = new Set(["document", "chat", "help"]);
  const INITIAL_SESSION = JSON.parse(document.getElementById("initial-showcase-session").textContent);

  const HELP_TOPICS = Object.freeze({
    welcome: {
      title: "Начало работы",
      body: "Сначала назовите проект, затем перечислите проблемные темы и группы людей или организаций. Все изменения остаются только в этой вкладке до явного экспорта JSON.",
    },
    project: {
      title: "Карточка проекта",
      body: "Название и описание помогают участникам одинаково понимать границы проекта. Showcase-сессия не создаёт authoritative ProjectDefinitionVersion.",
    },
    actors: {
      title: "Группы людей и организаций",
      body: "Опишите тех, чьи действия, позиции или интересы важны для исследования. Код должен быть уникальным, а название и краткое описание — заполненными.",
    },
    "analytical-elements": {
      title: "Проблемные темы",
      body: "Каждая тема получает устойчивый ID, уникальный код, понятное название и рабочее определение. Порядок меняется перетаскиванием или кнопками со стрелками.",
    },
    validation: {
      title: "Проверка структуры",
      body: "Проверка показывает пустые обязательные поля, повторяющиеся коды и ID, а также ссылки на отсутствующие записи. Она ничего не сохраняет и не исправляет автоматически.",
    },
    preview: {
      title: "Preview структуры",
      body: "Preview показывает размеры и сочетания структуры без оценок и вычислений. Это проверка представления, а не публикация или научная валидация.",
    },
    "publication-limitation": {
      title: "Почему публикация недоступна",
      body: "Production-контракт авторинга, ролей, аудита и первой публикации ещё не принят. Прототип не создаёт обходной publisher и не сообщает об успехе публикации.",
    },
  });

  let session = clone(INITIAL_SESSION);
  let activeView = "welcome";
  let fileIntent = "open";
  let draggedRow = null;
  let layout = loadLayout();

  const elements = {
    shell: document.getElementById("studio-workspace"),
    leftPanel: document.getElementById("project-panel"),
    rightPanel: document.getElementById("context-panel"),
    leftSplitter: document.getElementById("splitter-left"),
    rightSplitter: document.getElementById("splitter-right"),
    summary: document.getElementById("session-summary"),
    elementsCount: document.getElementById("elements-count"),
    actorsCount: document.getElementById("actors-count"),
    elementsBody: document.getElementById("elements-editor-body"),
    actorsBody: document.getElementById("actors-editor-body"),
    elementsEmpty: document.getElementById("elements-empty"),
    actorsEmpty: document.getElementById("actors-empty"),
    projectName: document.getElementById("project-name"),
    projectDescription: document.getElementById("project-description"),
    diagnostics: document.getElementById("diagnostics"),
    validationPanel: document.getElementById("validation-panel"),
    previewPanel: document.getElementById("preview-panel"),
    structurePreview: document.getElementById("structure-preview"),
    helpContent: document.getElementById("help-content"),
    helpTopicList: document.getElementById("help-topic-list"),
    fileInput: document.getElementById("session-file-input"),
    toastRegion: document.getElementById("toast-region"),
    notice: document.getElementById("session-notice"),
    confirmDialog: document.getElementById("confirm-dialog"),
  };

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function safeStorageGet(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (_error) {
      return null;
    }
  }

  function safeStorageSet(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (_error) {
      // Preferences are optional; session content never falls back to storage.
    }
  }

  function safeStorageRemove(key) {
    try {
      window.localStorage.removeItem(key);
    } catch (_error) {
      // Preferences are optional.
    }
  }

  function loadLayout() {
    const raw = safeStorageGet(LAYOUT_KEY);
    if (!raw) return { ...DEFAULT_LAYOUT };
    try {
      const candidate = JSON.parse(raw);
      const leftValid = Number.isFinite(candidate.left) && candidate.left >= WIDTH_LIMITS.left[0] && candidate.left <= WIDTH_LIMITS.left[1];
      const rightValid = Number.isFinite(candidate.right) && candidate.right >= WIDTH_LIMITS.right[0] && candidate.right <= WIDTH_LIMITS.right[1];
      const tabValid = RIGHT_TABS.has(candidate.activeRightTab);
      if (candidate.version !== LAYOUT_VERSION || !leftValid || !rightValid || !tabValid) {
        throw new Error("invalid layout");
      }
      return { left: candidate.left, right: candidate.right, activeRightTab: candidate.activeRightTab };
    } catch (_error) {
      safeStorageRemove(LAYOUT_KEY);
      safeStorageSet(LAYOUT_KEY, JSON.stringify({ version: LAYOUT_VERSION, ...DEFAULT_LAYOUT }));
      return { ...DEFAULT_LAYOUT };
    }
  }

  function persistLayout() {
    safeStorageSet(LAYOUT_KEY, JSON.stringify({ version: LAYOUT_VERSION, ...layout }));
  }

  function applyLayout() {
    const available = Math.max(window.innerWidth, 1024);
    if (layout.left + layout.right + 540 > available) {
      layout = { ...DEFAULT_LAYOUT, activeRightTab: layout.activeRightTab };
    }
    elements.shell.style.setProperty("--left-panel-width", `${layout.left}px`);
    elements.shell.style.setProperty("--right-panel-width", `${layout.right}px`);
    elements.shell.style.gridTemplateColumns = `${layout.left}px 9px minmax(480px, 1fr) 9px ${layout.right}px`;
    elements.leftPanel.style.width = `${layout.left}px`;
    elements.rightPanel.style.width = `${layout.right}px`;
    elements.leftSplitter.setAttribute("aria-valuenow", String(layout.left));
    elements.rightSplitter.setAttribute("aria-valuenow", String(layout.right));
  }

  function resetLayout() {
    layout = { ...DEFAULT_LAYOUT };
    persistLayout();
    applyLayout();
    activateRightTab("document");
    toast("Панели возвращены к безопасной раскладке.");
  }

  function toast(message, tone = "info") {
    const item = document.createElement("div");
    item.className = `toast toast--${tone}`;
    item.textContent = message;
    elements.toastRegion.replaceChildren(item);
    window.setTimeout(() => item.remove(), 3600);
  }

  function stableId(prefix) {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return `${prefix}-${window.crypto.randomUUID()}`;
    }
    return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function render() {
    session.project = session.project || {};
    session.analyticalElements = Array.isArray(session.analyticalElements) ? session.analyticalElements : [];
    session.actors = Array.isArray(session.actors) ? session.actors : [];
    elements.projectName.value = session.project.name || "";
    elements.projectDescription.value = session.project.description || "";
    renderEditor("analyticalElements", elements.elementsBody, elements.elementsEmpty);
    renderEditor("actors", elements.actorsBody, elements.actorsEmpty);
    elements.elementsCount.textContent = String(session.analyticalElements.length);
    elements.actorsCount.textContent = String(session.actors.length);
    elements.summary.textContent = `${session.analyticalElements.length} тем · ${session.actors.length} групп`;
  }

  function renderEditor(collectionName, body, emptyState) {
    const rows = session[collectionName];
    body.replaceChildren();
    emptyState.hidden = rows.length !== 0;
    rows.forEach((row, index) => {
      const detailField = collectionName === "analyticalElements" ? "definition" : "description";
      const detailLabel = collectionName === "analyticalElements" ? "Рабочее определение" : "Краткое описание";
      const tableRow = document.createElement("tr");
      tableRow.draggable = true;
      tableRow.dataset.collection = collectionName;
      tableRow.dataset.index = String(index);
      tableRow.dataset.stableId = row.id || "";
      tableRow.innerHTML = `
        <td class="order-cell">
          <button type="button" class="drag-handle" aria-label="Перетащить запись" title="Перетащить">⋮⋮</button>
          <span>${index + 1}</span>
        </td>
        <td><label class="visually-hidden" for="${collectionName}-code-${index}">Код</label><input id="${collectionName}-code-${index}" data-field="code" value="${escapeHtml(row.code)}" autocomplete="off"></td>
        <td><label class="visually-hidden" for="${collectionName}-name-${index}">Название</label><input id="${collectionName}-name-${index}" data-field="name" value="${escapeHtml(row.name)}" autocomplete="off"></td>
        <td><label class="visually-hidden" for="${collectionName}-detail-${index}">${detailLabel}</label><textarea id="${collectionName}-detail-${index}" data-field="${detailField}" rows="2">${escapeHtml(row[detailField])}</textarea></td>
        <td class="row-actions">
          <button type="button" data-move="up" aria-label="Поднять запись" title="Поднять">↑</button>
          <button type="button" data-move="down" aria-label="Опустить запись" title="Опустить">↓</button>
          <button type="button" data-delete-row aria-label="Удалить запись" title="Удалить">×</button>
        </td>`;
      body.appendChild(tableRow);
    });
  }

  function collectionFromBody(body) {
    return body.dataset.collection;
  }

  function updateRowFromInput(event) {
    const input = event.target.closest("[data-field]");
    if (!input) return;
    const tableRow = input.closest("tr[data-collection]");
    if (!tableRow) return;
    const collection = tableRow.dataset.collection;
    const index = Number(tableRow.dataset.index);
    if (!session[collection] || !session[collection][index]) return;
    session[collection][index][input.dataset.field] = input.value;
  }

  function rowFocusSelector(control) {
    if (!control) return ".drag-handle";
    if (control.matches("[data-field]")) {
      return `[data-field="${CSS.escape(control.dataset.field)}"]`;
    }
    if (control.matches("[data-move]")) {
      return `[data-move="${CSS.escape(control.dataset.move)}"]`;
    }
    if (control.matches("[data-delete-row]")) return "[data-delete-row]";
    return ".drag-handle";
  }

  function restoreRowFocus(collection, stableId, selector) {
    const body = collection === "analyticalElements" ? elements.elementsBody : elements.actorsBody;
    const row = [...body.querySelectorAll("tr[data-stable-id]")]
      .find((candidate) => candidate.dataset.stableId === stableId);
    row?.querySelector(selector)?.focus({ preventScroll: true });
  }

  function moveRow(collection, index, direction, focusControl = null) {
    const target = index + direction;
    if (target < 0 || target >= session[collection].length) return;
    const [row] = session[collection].splice(index, 1);
    session[collection].splice(target, 0, row);
    const focusSelector = rowFocusSelector(focusControl);
    render();
    restoreRowFocus(collection, row.id || "", focusSelector);
  }

  function deleteRow(collection, index) {
    session[collection].splice(index, 1);
    render();
    toast("Запись удалена только из showcase-сессии.");
  }

  function handleRowAction(event) {
    const button = event.target.closest("button");
    if (!button) return;
    const tableRow = button.closest("tr[data-collection]");
    if (!tableRow) return;
    const collection = tableRow.dataset.collection;
    const index = Number(tableRow.dataset.index);
    if (button.hasAttribute("data-delete-row")) {
      deleteRow(collection, index);
    } else if (button.dataset.move === "up") {
      moveRow(collection, index, -1, button);
    } else if (button.dataset.move === "down") {
      moveRow(collection, index, 1, button);
    }
  }

  function nextAvailableCode(collection, prefix) {
    const usedCodes = new Set(
      session[collection].map((row) => String(row.code || "").trim().toLocaleUpperCase("ru")),
    );
    let number = 1;
    let code = "";
    do {
      code = `${prefix}-${String(number).padStart(2, "0")}`;
      number += 1;
    } while (usedCodes.has(code));
    return { code, number: number - 1 };
  }

  function addRow(collection) {
    if (collection === "analyticalElements") {
      const { code, number } = nextAvailableCode(collection, "CI");
      session[collection].push({
        id: stableId("element"),
        code,
        name: `Новая проблемная тема ${number}`,
        definition: "",
        parentId: null,
      });
    } else {
      const { code, number } = nextAvailableCode(collection, "ACT");
      session[collection].push({
        id: stableId("actor"),
        code,
        name: `Новая группа или организация ${number}`,
        description: "",
        parentId: null,
      });
    }
    render();
    const body = collection === "analyticalElements" ? elements.elementsBody : elements.actorsBody;
    body.querySelector("tr:last-child input[data-field='name']")?.focus();
  }

  function setupDrag(body) {
    body.addEventListener("dragstart", (event) => {
      const row = event.target.closest("tr[data-collection]");
      if (!row) return;
      draggedRow = { collection: row.dataset.collection, index: Number(row.dataset.index) };
      row.classList.add("is-dragging");
      event.dataTransfer.effectAllowed = "move";
    });
    body.addEventListener("dragend", (event) => {
      event.target.closest("tr")?.classList.remove("is-dragging");
      draggedRow = null;
    });
    body.addEventListener("dragover", (event) => event.preventDefault());
    body.addEventListener("drop", (event) => {
      event.preventDefault();
      const target = event.target.closest("tr[data-collection]");
      if (!draggedRow || !target || target.dataset.collection !== draggedRow.collection) return;
      const targetIndex = Number(target.dataset.index);
      const [row] = session[draggedRow.collection].splice(draggedRow.index, 1);
      session[draggedRow.collection].splice(targetIndex, 0, row);
      render();
      restoreRowFocus(draggedRow.collection, row.id || "", ".drag-handle");
    });
  }

  function setView(view, focusHeading = true) {
    activeView = view;
    document.querySelectorAll("[data-screen]").forEach((screen) => {
      screen.classList.toggle("is-active", screen.dataset.screen === view);
    });
    document.querySelectorAll("[data-view]").forEach((item) => {
      const active = item.dataset.view === view;
      item.classList.toggle("is-active", active);
      if (active) item.setAttribute("aria-current", "page");
      else item.removeAttribute("aria-current");
    });
    if (focusHeading) {
      const heading = document.querySelector(`[data-screen="${CSS.escape(view)}"] h2`);
      if (heading) {
        heading.tabIndex = -1;
        heading.focus({ preventScroll: true });
      }
    }
  }

  function diagnostic(code, path, message) {
    return { level: "error", code, path, message };
  }

  function validateSession(payload) {
    const diagnostics = [];
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      return [diagnostic("SESSION_NOT_OBJECT", "$", "Файл сессии должен содержать JSON-объект.")];
    }
    if (payload.format !== SESSION_FORMAT) diagnostics.push(diagnostic("FORMAT_MISMATCH", "format", `Ожидается маркировка ${SESSION_FORMAT}.`));
    if (payload.version !== SESSION_VERSION) diagnostics.push(diagnostic("VERSION_MISMATCH", "version", `Поддерживается версия ${SESSION_VERSION}.`));
    if (!payload.project || !String(payload.project.name || "").trim()) diagnostics.push(diagnostic("PROJECT_NAME_BLANK", "project.name", "Укажите название проекта."));

    const allIds = new Map();
    [
      ["analyticalElements", "проблемной темы", "definition"],
      ["actors", "группы или организации", "description"],
    ].forEach(([collection, label, detail]) => {
      const rows = payload[collection];
      if (!Array.isArray(rows)) {
        diagnostics.push(diagnostic("COLLECTION_NOT_ARRAY", collection, "Список должен быть массивом."));
        return;
      }
      const codes = new Set();
      const rowIds = new Set(rows.map((row) => String(row?.id || "")).filter(Boolean));
      rows.forEach((row, index) => {
        const path = `${collection}[${index}]`;
        if (!row || typeof row !== "object" || Array.isArray(row)) {
          diagnostics.push(diagnostic("ROW_NOT_OBJECT", path, "Запись должна быть объектом."));
          return;
        }
        const id = String(row.id || "").trim();
        const code = String(row.code || "").trim();
        if (!id) diagnostics.push(diagnostic("ID_BLANK", `${path}.id`, "У записи отсутствует ID."));
        else if (allIds.has(id)) diagnostics.push(diagnostic("ID_DUPLICATE", `${path}.id`, `ID «${id}» уже используется в ${allIds.get(id)}.`));
        else allIds.set(id, path);
        if (!code) diagnostics.push(diagnostic("CODE_BLANK", `${path}.code`, "Укажите код записи."));
        else if (codes.has(code.toLocaleLowerCase("ru"))) diagnostics.push(diagnostic("CODE_DUPLICATE", `${path}.code`, `Код «${code}» уже используется.`));
        else codes.add(code.toLocaleLowerCase("ru"));
        if (!String(row.name || "").trim()) diagnostics.push(diagnostic("NAME_BLANK", `${path}.name`, `Укажите название ${label}.`));
        if (!String(row[detail] || "").trim()) diagnostics.push(diagnostic(detail === "definition" ? "DEFINITION_BLANK" : "DESCRIPTION_BLANK", `${path}.${detail}`, `Заполните поле «${detail === "definition" ? "Рабочее определение" : "Краткое описание"}».`));
        if (row.parentId && !rowIds.has(String(row.parentId))) diagnostics.push(diagnostic("PARENT_REFERENCE_MISSING", `${path}.parentId`, `Ссылка «${row.parentId}» не найдена.`));
      });
    });
    return diagnostics;
  }

  function renderDiagnostics(diagnostics) {
    elements.validationPanel.hidden = false;
    elements.previewPanel.hidden = true;
    elements.diagnostics.replaceChildren();
    const heading = document.createElement("div");
    heading.className = diagnostics.length ? "diagnostic-summary diagnostic-summary--error" : "diagnostic-summary diagnostic-summary--ok";
    heading.textContent = diagnostics.length ? `Найдено ошибок: ${diagnostics.length}` : "Структура прошла проверку showcase-сессии";
    elements.diagnostics.appendChild(heading);
    if (diagnostics.length) {
      const list = document.createElement("ol");
      list.className = "diagnostic-list";
      diagnostics.forEach((item) => {
        const row = document.createElement("li");
        const code = document.createElement("code");
        code.textContent = `${item.code} · ${item.path}`;
        const text = document.createElement("span");
        text.textContent = item.message;
        row.append(code, text);
        list.appendChild(row);
      });
      elements.diagnostics.appendChild(list);
    } else {
      const note = document.createElement("p");
      note.textContent = "Проверка ничего не сохранила и не публиковала.";
      elements.diagnostics.appendChild(note);
    }
    elements.validationPanel.scrollIntoView({ block: "nearest" });
  }

  function validateAndShow() {
    const diagnostics = validateSession(session);
    renderDiagnostics(diagnostics);
    openHelp("validation", false);
    toast(diagnostics.length ? "Проверка завершена с ошибками." : "Структура прошла локальную проверку.", diagnostics.length ? "error" : "success");
    return diagnostics;
  }

  function showPreview() {
    elements.validationPanel.hidden = true;
    elements.previewPanel.hidden = false;
    const themes = session.analyticalElements;
    const actors = session.actors;
    const table = document.createElement("table");
    table.className = "preview-grid";
    table.innerHTML = `<caption>${themes.length} проблемных тем × ${actors.length} групп или организаций</caption>`;
    const head = document.createElement("thead");
    const headRow = document.createElement("tr");
    const corner = document.createElement("th");
    corner.scope = "col";
    corner.textContent = "Тема / участник";
    headRow.appendChild(corner);
    actors.forEach((actor) => {
      const cell = document.createElement("th");
      cell.scope = "col";
      cell.textContent = actor.code || "—";
      cell.title = actor.name || "";
      headRow.appendChild(cell);
    });
    head.appendChild(headRow);
    const body = document.createElement("tbody");
    themes.forEach((theme) => {
      const row = document.createElement("tr");
      const label = document.createElement("th");
      label.scope = "row";
      label.textContent = theme.code || "—";
      label.title = theme.name || "";
      row.appendChild(label);
      actors.forEach(() => {
        const cell = document.createElement("td");
        cell.textContent = "структура";
        row.appendChild(cell);
      });
      body.appendChild(row);
    });
    table.append(head, body);
    const note = document.createElement("p");
    note.className = "preview-note";
    note.textContent = "Preview показывает только структуру. Оценки, вычисления и публикация в этом срезе отсутствуют.";
    elements.structurePreview.replaceChildren(table, note);
    elements.previewPanel.scrollIntoView({ block: "nearest" });
    openHelp("preview", false);
  }

  function activateRightTab(tabName, persist = true) {
    if (!RIGHT_TABS.has(tabName)) tabName = "document";
    document.querySelectorAll("[data-right-tab]").forEach((tab) => {
      const active = tab.dataset.rightTab === tabName;
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
    });
    document.querySelectorAll("[data-right-panel]").forEach((panel) => {
      const active = panel.dataset.rightPanel === tabName;
      panel.hidden = !active;
      panel.classList.toggle("is-active", active);
    });
    layout.activeRightTab = tabName;
    if (persist) persistLayout();
  }

  function openHelp(topicName, focus = true) {
    const topic = HELP_TOPICS[topicName] || HELP_TOPICS.welcome;
    elements.helpContent.replaceChildren();
    const kicker = document.createElement("p");
    kicker.className = "panel-kicker";
    kicker.textContent = "Раздел";
    const heading = document.createElement("h2");
    heading.textContent = topic.title;
    const body = document.createElement("p");
    body.textContent = topic.body;
    elements.helpContent.append(kicker, heading, body);
    activateRightTab("help");
    if (focus) elements.helpContent.focus();
  }

  function renderHelpList() {
    elements.helpTopicList.replaceChildren();
    Object.entries(HELP_TOPICS).forEach(([key, topic]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.helpTopic = key;
      button.textContent = topic.title;
      elements.helpTopicList.appendChild(button);
    });
  }

  function exportSession(action = "export", triggerDownload = true) {
    const text = `${JSON.stringify(session, null, 2)}\n`;
    if (!triggerDownload) return text;
    const blob = new Blob([text], { type: "application/json;charset=utf-8" });
    const link = document.createElement("a");
    const suffix = action === "save" ? "saved" : "export";
    link.href = URL.createObjectURL(blob);
    link.download = `showcase-session-v1-${suffix}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(link.href);
    toast(`${SESSION_FORMAT} выгружен в JSON.`, "success");
    return text;
  }

  function requestFile(intent) {
    fileIntent = intent;
    elements.fileInput.value = "";
    elements.fileInput.click();
  }

  function loadSession(payload) {
    const diagnostics = validateSession(payload);
    if (diagnostics.length) return diagnostics;
    session = clone(payload);
    render();
    return [];
  }

  async function importFile(file) {
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      toast("Файл превышает безопасный лимит 2 МБ.", "error");
      return;
    }
    try {
      const payload = JSON.parse(await file.text());
      const diagnostics = validateSession(payload);
      if (diagnostics.length) {
        renderDiagnostics(diagnostics);
        toast("JSON прочитан, но структура содержит ошибки.", "error");
        return;
      }
      loadSession(payload);
      setView("project");
      toast(`${fileIntent === "open" ? "Открыта" : "Импортирована"} showcase-сессия ${SESSION_FORMAT}.`, "success");
    } catch (_error) {
      toast("Не удалось прочитать JSON showcase-сессии.", "error");
    }
  }

  async function loadFixture(name) {
    try {
      const response = await fetch(`api/fixtures/${encodeURIComponent(name)}/`, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("fixture request failed");
      session = await response.json();
      render();
      setView("elements");
      toast(`Загружен демонстрационный набор ${name}.`, "success");
    } catch (_error) {
      toast("Не удалось загрузить демонстрационный набор.", "error");
    }
  }

  function newSession() {
    session = {
      format: SESSION_FORMAT,
      version: SESSION_VERSION,
      project: { id: stableId("project"), code: "SHOWCASE-PROJECT", name: "Новый исследовательский проект", description: "" },
      analyticalElements: [],
      actors: [],
      meta: { presentationOnly: true, fixture: "custom" },
    };
    render();
    setView("project");
    toast("Создана пустая локальная showcase-сессия.");
  }

  function confirmNewSession() {
    if (typeof elements.confirmDialog.showModal !== "function") {
      newSession();
      return;
    }
    elements.confirmDialog.showModal();
    elements.confirmDialog.addEventListener("close", () => {
      if (elements.confirmDialog.returnValue === "confirm") newSession();
    }, { once: true });
  }

  function cloneSession() {
    session = clone(session);
    session.project.id = stableId("project");
    session.project.code = `${session.project.code || "SHOWCASE"}-COPY`;
    session.project.name = `${session.project.name || "Проект"} — копия`;
    session.meta = { ...(session.meta || {}), presentationOnly: true, cloned: true };
    render();
    setView("project");
    toast("Создана независимая копия showcase-сессии.", "success");
  }

  function handleCommand(command) {
    switch (command) {
      case "new": confirmNewSession(); break;
      case "open": requestFile("open"); break;
      case "clone": cloneSession(); break;
      case "save": exportSession("save"); break;
      case "validate": validateAndShow(); break;
      case "import": requestFile("import"); break;
      case "export": exportSession("export"); break;
      case "preview": showPreview(); break;
      case "publish": openHelp("publication-limitation"); break;
      default: break;
    }
  }

  function setupSplitter(splitter) {
    const side = splitter.dataset.splitter;
    let dragging = false;
    const resize = (clientX) => {
      const bounds = elements.shell.getBoundingClientRect();
      const raw = side === "left" ? clientX - bounds.left : bounds.right - clientX;
      const [min, max] = WIDTH_LIMITS[side];
      layout[side] = Math.max(min, Math.min(max, Math.round(raw)));
      applyLayout();
    };
    splitter.addEventListener("pointerdown", (event) => {
      dragging = true;
      splitter.setPointerCapture(event.pointerId);
      document.body.classList.add("is-resizing");
    });
    splitter.addEventListener("pointermove", (event) => {
      if (dragging) resize(event.clientX);
    });
    splitter.addEventListener("pointerup", (event) => {
      if (!dragging) return;
      dragging = false;
      splitter.releasePointerCapture(event.pointerId);
      document.body.classList.remove("is-resizing");
      persistLayout();
    });
    splitter.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
      event.preventDefault();
      const delta = event.key === "ArrowRight" ? 12 : -12;
      const signed = side === "left" ? delta : -delta;
      const [min, max] = WIDTH_LIMITS[side];
      layout[side] = Math.max(min, Math.min(max, layout[side] + signed));
      applyLayout();
      splitter.setAttribute("aria-valuenow", String(layout[side]));
      persistLayout();
    });
  }

  function bindEvents() {
    document.addEventListener("click", (event) => {
      const command = event.target.closest("[data-command]")?.dataset.command;
      if (command) handleCommand(command);
      const view = event.target.closest("[data-view]")?.dataset.view || event.target.closest("[data-go-view]")?.dataset.goView;
      if (view) setView(view);
      const help = event.target.closest("[data-help-topic]")?.dataset.helpTopic;
      if (help) openHelp(help);
      const fixtureName = event.target.closest("[data-fixture]")?.dataset.fixture;
      if (fixtureName) loadFixture(fixtureName);
      const add = event.target.closest("[data-add-row]")?.dataset.addRow;
      if (add) addRow(add);
      const tab = event.target.closest("[data-right-tab]")?.dataset.rightTab;
      if (tab) activateRightTab(tab);
      if (event.target.closest("[data-reset-layout]")) resetLayout();
      if (event.target.closest("[data-dismiss-notice]")) elements.notice.hidden = true;
      const close = event.target.closest("[data-close-result]")?.dataset.closeResult;
      if (close === "validation") elements.validationPanel.hidden = true;
      if (close === "preview") elements.previewPanel.hidden = true;
    });
    elements.projectName.addEventListener("input", () => { session.project.name = elements.projectName.value; });
    elements.projectDescription.addEventListener("input", () => { session.project.description = elements.projectDescription.value; });
    [elements.elementsBody, elements.actorsBody].forEach((body) => {
      body.addEventListener("input", updateRowFromInput);
      body.addEventListener("click", handleRowAction);
      body.addEventListener("keydown", (event) => {
        if (!event.altKey || !["ArrowUp", "ArrowDown"].includes(event.key)) return;
        const row = event.target.closest("tr[data-collection]");
        if (!row) return;
        event.preventDefault();
        moveRow(row.dataset.collection, Number(row.dataset.index), event.key === "ArrowUp" ? -1 : 1, event.target);
      });
      setupDrag(body);
    });
    elements.fileInput.addEventListener("change", () => importFile(elements.fileInput.files[0]));
    document.querySelectorAll("[data-right-tab]").forEach((tab) => {
      tab.addEventListener("keydown", (event) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        const tabs = [...document.querySelectorAll("[data-right-tab]")];
        let index = tabs.indexOf(event.currentTarget);
        if (event.key === "Home") index = 0;
        else if (event.key === "End") index = tabs.length - 1;
        else index = (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
        tabs[index].focus();
        activateRightTab(tabs[index].dataset.rightTab);
      });
    });
    document.querySelectorAll("[data-splitter]").forEach(setupSplitter);
    window.addEventListener("resize", applyLayout);
  }

  renderHelpList();
  bindEvents();
  applyLayout();
  activateRightTab(layout.activeRightTab, false);
  render();
  setView(activeView, false);

  window.StudioShowcase = Object.freeze({
    constants: Object.freeze({ SESSION_FORMAT, SESSION_VERSION, LAYOUT_KEY, LAYOUT_VERSION }),
    getSession: () => clone(session),
    loadSession,
    validate: (payload = session) => clone(validateSession(payload)),
    getLayout: () => ({ ...layout }),
    fixture: loadFixture,
    exportSession,
    loadFixture,
    setView,
    showPreview,
    resetLayout,
  });
}());
