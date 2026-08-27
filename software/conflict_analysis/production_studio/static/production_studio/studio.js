(() => {
  "use strict";

  const STORAGE_KEY = "conflict-analysis-studio:read-only-layout:v1";
  const LAYOUT_VERSION = "STUDIO_READ_ONLY_LAYOUT_V1";
  const DEFAULT_LAYOUT = Object.freeze({
    version: LAYOUT_VERSION,
    left: 272,
    right: 360,
    activeRightTab: "document",
  });
  const LEFT_MIN = 220;
  const LEFT_MAX = 420;
  const RIGHT_MIN = 300;
  const RIGHT_MAX = 500;
  const LAYOUT_BYTE_LIMIT = 256;
  const RIGHT_TABS = new Set(["document", "chat", "help"]);
  const WINDOW_SIZE = 100;
  const SHA256_PATTERN = /^[0-9a-f]{64}$/;
  const UUID_PATTERN = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
  const LIFECYCLE = new Set(["DRAFT", "VALIDATED", "PUBLISHED", "RETIRED"]);
  const encoder = new TextEncoder();

  const memory = {
    app: null,
    definition: null,
    manifest: null,
    datasets: { actors: [], "analytical-elements": [] },
    datasetSyntax: { actors: [], "analytical-elements": [] },
    activeDataset: "actors",
    windowOffset: 0,
    layout: { ...DEFAULT_LAYOUT },
    helpBindings: [],
    helpSettled: false,
  };

  function utf8Length(value) {
    return encoder.encode(value).byteLength;
  }

  async function sha256(bytes) {
    const digest = await window.crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest), (item) =>
      item.toString(16).padStart(2, "0"),
    ).join("");
  }

  async function sha256Text(value) {
    return sha256(encoder.encode(value));
  }

  function compareUnicodeCodePoints(left, right) {
    const leftPoints = Array.from(left, (item) => item.codePointAt(0));
    const rightPoints = Array.from(right, (item) => item.codePointAt(0));
    const length = Math.min(leftPoints.length, rightPoints.length);
    for (let index = 0; index < length; index += 1) {
      if (leftPoints[index] !== rightPoints[index]) {
        return leftPoints[index] - rightPoints[index];
      }
    }
    return leftPoints.length - rightPoints.length;
  }

  function parseLosslessJSON(source) {
    if (typeof source !== "string") throw new TypeError("JSON source must be text.");
    let offset = 0;

    const fail = () => {
      throw new SyntaxError(`Invalid JSON at byte-independent offset ${offset}.`);
    };
    const skipWhitespace = () => {
      while (/[\x20\x09\x0a\x0d]/.test(source[offset] || "")) offset += 1;
    };
    const parseString = () => {
      const start = offset;
      if (source[offset] !== '"') fail();
      offset += 1;
      while (offset < source.length) {
        const codeUnit = source.charCodeAt(offset);
        if (codeUnit === 0x22) {
          offset += 1;
          const raw = source.slice(start, offset);
          return { kind: "string", raw, value: JSON.parse(raw) };
        }
        if (codeUnit < 0x20) fail();
        if (codeUnit === 0x5c) {
          offset += 1;
          const escape = source[offset];
          if ('"\\/bfnrt'.includes(escape)) {
            offset += 1;
            continue;
          }
          if (
            escape === "u" &&
            /^[0-9a-fA-F]{4}$/.test(source.slice(offset + 1, offset + 5))
          ) {
            offset += 5;
            continue;
          }
          fail();
        }
        offset += 1;
      }
      fail();
    };
    const parseNumber = () => {
      const match = source
        .slice(offset)
        .match(/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/);
      if (!match) fail();
      offset += match[0].length;
      return { kind: "number", raw: match[0] };
    };
    const parseValue = () => {
      skipWhitespace();
      const character = source[offset];
      if (character === '"') return parseString();
      if (character === "[") {
        offset += 1;
        skipWhitespace();
        const items = [];
        if (source[offset] === "]") {
          offset += 1;
          return { kind: "array", items };
        }
        while (true) {
          items.push(parseValue());
          skipWhitespace();
          if (source[offset] === "]") {
            offset += 1;
            return { kind: "array", items };
          }
          if (source[offset] !== ",") fail();
          offset += 1;
        }
      }
      if (character === "{") {
        offset += 1;
        skipWhitespace();
        const entries = [];
        const keys = new Set();
        if (source[offset] === "}") {
          offset += 1;
          return { kind: "object", entries };
        }
        while (true) {
          skipWhitespace();
          const key = parseString();
          if (keys.has(key.value)) fail();
          keys.add(key.value);
          skipWhitespace();
          if (source[offset] !== ":") fail();
          offset += 1;
          entries.push({ key, value: parseValue() });
          skipWhitespace();
          if (source[offset] === "}") {
            offset += 1;
            return { kind: "object", entries };
          }
          if (source[offset] !== ",") fail();
          offset += 1;
        }
      }
      if (source.startsWith("true", offset)) {
        offset += 4;
        return { kind: "literal", raw: "true" };
      }
      if (source.startsWith("false", offset)) {
        offset += 5;
        return { kind: "literal", raw: "false" };
      }
      if (source.startsWith("null", offset)) {
        offset += 4;
        return { kind: "literal", raw: "null" };
      }
      return parseNumber();
    };

    const syntax = parseValue();
    skipWhitespace();
    if (offset !== source.length) fail();
    return { value: JSON.parse(source), syntax };
  }

  function losslessObjectMember(node, name) {
    if (!node || node.kind !== "object") return null;
    return node.entries.find((entry) => entry.key.value === name)?.value || null;
  }

  function canonicalLosslessJSON(node, omittedRootKeys = null) {
    if (!node || typeof node !== "object") {
      throw new TypeError("A parsed lossless JSON node is required.");
    }
    if (node.kind === "string") return JSON.stringify(node.value);
    if (node.kind === "number" || node.kind === "literal") {
      return node.raw;
    }
    if (node.kind === "array") {
      return `[${node.items.map((item) => canonicalLosslessJSON(item)).join(",")}]`;
    }
    if (node.kind === "object") {
      return `{${node.entries
        .filter((entry) => !omittedRootKeys?.has(entry.key.value))
        .sort((left, right) => compareUnicodeCodePoints(left.key.value, right.key.value))
        .map(
          (entry) =>
            `${JSON.stringify(entry.key.value)}:${canonicalLosslessJSON(entry.value)}`,
        )
        .join(",")}}`;
    }
    throw new TypeError("Value is outside the JSON data model.");
  }

  function canonicalJSON(value) {
    if (value === null || typeof value === "boolean" || typeof value === "string") {
      return JSON.stringify(value);
    }
    if (typeof value === "number") {
      if (!Number.isFinite(value)) {
        throw new TypeError("Non-finite JSON number.");
      }
      return JSON.stringify(value);
    }
    if (Array.isArray(value)) {
      return `[${value.map((item) => canonicalJSON(item)).join(",")}]`;
    }
    if (value && typeof value === "object") {
      return `{${Object.keys(value)
        .sort()
        .map((key) => `${JSON.stringify(key)}:${canonicalJSON(value[key])}`)
        .join(",")}}`;
    }
    throw new TypeError("Value is outside the JSON data model.");
  }

  function exactValue(value, syntax = null, absent = "UNKNOWN_ABSENT") {
    if (value === undefined) return absent;
    if (syntax?.kind === "number") return syntax.raw;
    if (syntax?.kind === "object" || syntax?.kind === "array") {
      return canonicalLosslessJSON(syntax);
    }
    if (value === null) return "null";
    if (typeof value === "object") return canonicalJSON(value);
    return String(value);
  }

  function fixedFetch(url, accept) {
    return window.fetch(url, {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
      redirect: "error",
      referrerPolicy: "same-origin",
      headers: { Accept: accept },
    });
  }

  function setText(id, value) {
    const node = document.getElementById(id);
    if (node) node.textContent = value;
  }

  function setShellState(state, title, message) {
    const app = memory.app;
    if (app) app.dataset.state = state;
    const card = document.getElementById("studio-state");
    if (card) card.dataset.state = state.replaceAll("-", "_").toUpperCase();
    setText("studio-state-title", title);
    setText("studio-state-message", message);
  }

  function clearHelpContent(message = "HELP_UNAVAILABLE: содержимое справки скрыто.") {
    memory.helpBindings = [];
    memory.helpSettled = true;
    const select = document.getElementById("help-binding-select");
    const button = document.getElementById("load-help");
    const topic = document.getElementById("help-topic");
    const frame = document.getElementById("help-content");
    const state = document.getElementById("help-state");
    if (select) {
      select.replaceChildren();
      select.disabled = true;
    }
    if (button) button.disabled = true;
    if (topic) topic.hidden = true;
    if (frame) frame.srcdoc = "";
    setText("help-title", "—");
    setText("help-identity", "—");
    if (state) {
      state.dataset.state = "HELP_UNAVAILABLE";
      state.textContent = message;
    }
  }

  function hideDomainContent() {
    const content = document.getElementById("definition-content");
    if (content) content.hidden = true;
    memory.definition = null;
    memory.manifest = null;
    memory.datasets = { actors: [], "analytical-elements": [] };
    memory.datasetSyntax = { actors: [], "analytical-elements": [] };
    setText("project-id", "—");
    setText("manifest-sha", "—");
    setText("manifest-etag", "—");
    clearHelpContent();
  }

  function failClosed(title, message) {
    hideDomainContent();
    setShellState("fail-closed", title, message);
  }

  function statusFailure(status) {
    hideDomainContent();
    if (status === 401) {
      setShellState(
        "authentication-required",
        "Требуется предварительная аутентификация",
        "Сессия отсутствует или истекла. Studio C0 не выдаёт и не обновляет сессии.",
      );
      return;
    }
    if (status === 403) {
      setShellState(
        "read-denied",
        "Чтение недоступно",
        "Аутентифицированному субъекту не разрешено читать это определение.",
      );
      return;
    }
    if (status === 404) {
      setShellState(
        "not-found-or-inaccessible",
        "Определение не найдено или недоступно",
        "Отсутствующий и находящийся вне доступного проекта UUID не различаются.",
      );
      return;
    }
    failClosed(
      "Foundation не подтвердил чтение",
      "Данные скрыты: получен неподдерживаемый ответ чтения.",
    );
  }

  async function verifyClaimContract(app) {
    const expectedSha = app.dataset.claimSha256 || "";
    const expectedBytes = Number(app.dataset.claimBytes);
    if (!SHA256_PATTERN.test(expectedSha) || expectedBytes !== 2197) return false;
    try {
      const response = await fixedFetch(app.dataset.claimUrl, "application/json");
      if (
        response.status !== 200 ||
        response.headers.get("Content-Type") !== "application/json; charset=utf-8" ||
        response.headers.get("Content-Length") !== String(expectedBytes) ||
        response.headers.get("ETag") !== `"${expectedSha}"`
      ) {
        return false;
      }
      const bytes = new Uint8Array(await response.arrayBuffer());
      if (bytes.byteLength !== expectedBytes || bytes[bytes.length - 1] !== 0x0a) {
        return false;
      }
      if ((await sha256(bytes)) !== expectedSha) return false;
      const decoded = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
      return Boolean(
        decoded &&
          decoded.contract === "STUDIO_READ_ONLY_CLAIM_BOUNDARIES_V1" &&
          decoded.locale === "ru" &&
          decoded.version === "1.0.0" &&
          Array.isArray(decoded.statements) &&
          decoded.statements.length === 9,
      );
    } catch (_error) {
      return false;
    }
  }

  function parseLayout() {
    let raw;
    try {
      raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw === null) return { ...DEFAULT_LAYOUT };
      if (utf8Length(raw) > LAYOUT_BYTE_LIMIT) throw new TypeError("oversized");
      const parsed = parseLosslessJSON(raw).value;
      const keys = Object.keys(parsed || {}).sort();
      if (
        !parsed ||
        typeof parsed !== "object" ||
        Array.isArray(parsed) ||
        keys.join("|") !== "activeRightTab|left|right|version" ||
        parsed.version !== LAYOUT_VERSION ||
        !Number.isInteger(parsed.left) ||
        parsed.left < LEFT_MIN ||
        parsed.left > LEFT_MAX ||
        !Number.isInteger(parsed.right) ||
        parsed.right < RIGHT_MIN ||
        parsed.right > RIGHT_MAX ||
        !RIGHT_TABS.has(parsed.activeRightTab)
      ) {
        throw new TypeError("invalid");
      }
      return {
        version: LAYOUT_VERSION,
        left: parsed.left,
        right: parsed.right,
        activeRightTab: parsed.activeRightTab,
      };
    } catch (_error) {
      try {
        window.localStorage.removeItem(STORAGE_KEY);
      } catch (_storageError) {
        // Storage denial is a safe in-memory default, never an alternate store.
      }
      return { ...DEFAULT_LAYOUT };
    }
  }

  function persistLayout() {
    const exact = {
      version: LAYOUT_VERSION,
      left: memory.layout.left,
      right: memory.layout.right,
      activeRightTab: memory.layout.activeRightTab,
    };
    const serialized = JSON.stringify(exact);
    if (utf8Length(serialized) > LAYOUT_BYTE_LIMIT) return;
    try {
      window.localStorage.setItem(STORAGE_KEY, serialized);
    } catch (_error) {
      // Preferences remain optional and memory-only when browser storage is denied.
    }
  }

  function clampInteger(value, minimum, maximum) {
    return Math.min(maximum, Math.max(minimum, Math.round(value)));
  }

  function applyLayout() {
    document.documentElement.style.setProperty("--left-width", `${memory.layout.left}px`);
    document.documentElement.style.setProperty("--right-width", `${memory.layout.right}px`);
    const left = document.getElementById("left-width-control");
    const right = document.getElementById("right-width-control");
    if (left) left.value = String(memory.layout.left);
    if (right) right.value = String(memory.layout.right);
    setText("left-width-output", String(memory.layout.left));
    setText("right-width-output", String(memory.layout.right));
    const leftDivider = document.getElementById("left-divider");
    const rightDivider = document.getElementById("right-divider");
    if (leftDivider) leftDivider.setAttribute("aria-valuenow", String(memory.layout.left));
    if (rightDivider) rightDivider.setAttribute("aria-valuenow", String(memory.layout.right));
  }

  function selectRightTab(tab, save = true) {
    if (!RIGHT_TABS.has(tab)) tab = "document";
    memory.layout.activeRightTab = tab;
    document.querySelectorAll("[data-right-tab]").forEach((button) => {
      const selected = button.dataset.rightTab === tab;
      button.setAttribute("aria-selected", String(selected));
      button.tabIndex = selected ? 0 : -1;
    });
    document.querySelectorAll("[data-tab-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.tabPanel !== tab;
    });
    if (save) persistLayout();
    if (tab === "help" && memory.manifest && !memory.helpSettled) {
      loadSelectedHelp();
    }
  }

  function bindLayout() {
    memory.layout = parseLayout();
    applyLayout();
    selectRightTab(memory.layout.activeRightTab, false);

    const leftControl = document.getElementById("left-width-control");
    const rightControl = document.getElementById("right-width-control");
    leftControl?.addEventListener("input", () => {
      memory.layout.left = clampInteger(Number(leftControl.value), LEFT_MIN, LEFT_MAX);
      applyLayout();
      persistLayout();
    });
    rightControl?.addEventListener("input", () => {
      memory.layout.right = clampInteger(Number(rightControl.value), RIGHT_MIN, RIGHT_MAX);
      applyLayout();
      persistLayout();
    });
    document.getElementById("layout-reset")?.addEventListener("click", () => {
      memory.layout = { ...DEFAULT_LAYOUT };
      try {
        window.localStorage.removeItem(STORAGE_KEY);
      } catch (_error) {
        // Defaults remain effective in memory.
      }
      applyLayout();
      selectRightTab("document", false);
    });

    document.querySelectorAll("[data-right-tab]").forEach((button) => {
      button.addEventListener("click", () => selectRightTab(button.dataset.rightTab));
      button.addEventListener("keydown", (event) => {
        if (!new Set(["ArrowLeft", "ArrowRight", "Home", "End"]).has(event.key)) return;
        const tabs = ["document", "chat", "help"];
        const current = tabs.indexOf(memory.layout.activeRightTab);
        let next = current;
        if (event.key === "ArrowLeft") next = (current + tabs.length - 1) % tabs.length;
        if (event.key === "ArrowRight") next = (current + 1) % tabs.length;
        if (event.key === "Home") next = 0;
        if (event.key === "End") next = tabs.length - 1;
        event.preventDefault();
        selectRightTab(tabs[next]);
        document.querySelector(`[data-right-tab="${tabs[next]}"]`)?.focus();
      });
    });

    bindDivider("left-divider", "left");
    bindDivider("right-divider", "right");
  }

  function bindDivider(id, side) {
    const divider = document.getElementById(id);
    if (!divider) return;
    divider.addEventListener("keydown", (event) => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      const direction = event.key === "ArrowRight" ? 1 : -1;
      if (side === "left") {
        memory.layout.left = clampInteger(memory.layout.left + direction * 8, LEFT_MIN, LEFT_MAX);
      } else {
        memory.layout.right = clampInteger(memory.layout.right - direction * 8, RIGHT_MIN, RIGHT_MAX);
      }
      event.preventDefault();
      applyLayout();
      persistLayout();
    });
    divider.addEventListener("pointerdown", (event) => {
      const startX = event.clientX;
      const startValue = memory.layout[side];
      divider.setPointerCapture(event.pointerId);
      const move = (moveEvent) => {
        const delta = moveEvent.clientX - startX;
        memory.layout[side] =
          side === "left"
            ? clampInteger(startValue + delta, LEFT_MIN, LEFT_MAX)
            : clampInteger(startValue - delta, RIGHT_MIN, RIGHT_MAX);
        applyLayout();
      };
      const finish = () => {
        divider.removeEventListener("pointermove", move);
        persistLayout();
      };
      divider.addEventListener("pointermove", move);
      divider.addEventListener("pointerup", finish, { once: true });
      divider.addEventListener("pointercancel", finish, { once: true });
    });
  }

  async function readDefinition() {
    const app = memory.app;
    let response;
    try {
      response = await fixedFetch(app.dataset.openUrl, "application/json");
    } catch (_error) {
      failClosed("Foundation недоступен", "Сетевой ответ не получен; устаревшие данные не показаны.");
      return null;
    }
    if (response.status !== 200) {
      statusFailure(response.status);
      return null;
    }
    if (!(response.headers.get("Content-Type") || "").toLowerCase().startsWith("application/json")) {
      failClosed("Неверное представление", "Foundation не вернул ожидаемый JSON DTO.");
      return null;
    }
    let dto;
    let dtoSyntax;
    try {
      const parsed = parseLosslessJSON(await response.text());
      dto = parsed.value;
      dtoSyntax = parsed.syntax;
    } catch (_error) {
      failClosed("Неверное представление", "JSON DTO не может быть безопасно прочитан.");
      return null;
    }
    const etag = response.headers.get("ETag");
    try {
      const expectedId = app.dataset.definitionId.toLowerCase();
      if (
        !dto ||
        typeof dto !== "object" ||
        String(dto.id).toLowerCase() !== expectedId ||
        !UUID_PATTERN.test(String(dto.project_id || "")) ||
        !SHA256_PATTERN.test(String(dto.manifest_hash || "")) ||
        !LIFECYCLE.has(dto.publication_status) ||
        !dto.manifest ||
        typeof dto.manifest !== "object" ||
        dto.manifest.format !== "conflict-analysis-project-definition" ||
        dto.manifest.format_version !== "1.0.0" ||
        String(dto.manifest.project?.id || "").toLowerCase() !== String(dto.project_id).toLowerCase()
      ) {
        throw new TypeError("identity");
      }
      const manifestSyntax = losslessObjectMember(dtoSyntax, "manifest");
      if (!manifestSyntax) throw new TypeError("manifest syntax");
      const actualManifestSha = await sha256Text(canonicalLosslessJSON(manifestSyntax));
      if (actualManifestSha !== dto.manifest_hash || etag !== `"${dto.manifest_hash}"`) {
        throw new TypeError("checksum");
      }
    } catch (_error) {
      failClosed(
        "Идентичность определения не подтверждена",
        "DTO, canonical manifest SHA-256 или quoted ETag не совпали; данные скрыты.",
      );
      return null;
    }
    return { dto, dtoSyntax, etag };
  }

  function renderProject(project, projectSyntax) {
    const root = document.getElementById("project-snapshot");
    if (!root) return;
    root.replaceChildren();
    Object.entries(project).forEach(([key, value]) => {
      const wrapper = document.createElement("div");
      const term = document.createElement("dt");
      const detail = document.createElement("dd");
      term.textContent = key;
      detail.textContent = exactValue(value, losslessObjectMember(projectSyntax, key));
      wrapper.append(term, detail);
      root.append(wrapper);
    });
  }

  function appendStackCell(row, primary, secondary, primarySyntax = null, secondarySyntax = null) {
    const cell = document.createElement("td");
    const stack = document.createElement("span");
    stack.className = "cell-stack";
    const first = document.createElement("span");
    const second = document.createElement("small");
    first.textContent = exactValue(primary, primarySyntax);
    second.textContent = exactValue(secondary, secondarySyntax);
    stack.append(first, second);
    cell.append(stack);
    row.append(cell);
  }

  function renderManifestWindow() {
    const root = document.getElementById("manifest-window");
    if (!root) return;
    root.replaceChildren();
    const items = memory.datasets[memory.activeDataset];
    const start = Math.min(memory.windowOffset, Math.max(0, items.length - 1));
    const end = Math.min(start + WINDOW_SIZE, items.length);
    const itemSyntax = memory.datasetSyntax[memory.activeDataset];
    items.slice(start, end).forEach((item, localIndex) => {
      const syntax = itemSyntax[start + localIndex] || null;
      const row = document.createElement("tr");
      row.dataset.manifestRow = "true";
      appendStackCell(
        row,
        item.order,
        memory.activeDataset === "actors" ? "actor order" : "element order",
        losslessObjectMember(syntax, "order"),
      );
      appendStackCell(
        row,
        item.code,
        item.version,
        losslessObjectMember(syntax, "code"),
        losslessObjectMember(syntax, "version"),
      );
      const typeKey = memory.activeDataset === "actors" ? "actor_type" : "element_type";
      appendStackCell(
        row,
        item.label,
        item[typeKey],
        losslessObjectMember(syntax, "label"),
        losslessObjectMember(syntax, typeKey),
      );
      appendStackCell(
        row,
        item.id,
        item.parent_id,
        losslessObjectMember(syntax, "id"),
        losslessObjectMember(syntax, "parent_id"),
      );
      appendStackCell(
        row,
        item.description,
        memory.activeDataset === "actors" ? "NOT_APPLICABLE" : item.reference_statement,
        losslessObjectMember(syntax, "description"),
        memory.activeDataset === "actors"
          ? null
          : losslessObjectMember(syntax, "reference_statement"),
      );
      root.append(row);
    });
    const first = items.length ? start + 1 : 0;
    setText("window-position", `${first}–${end} из ${items.length}`);
    setText(
      "manifest-window-description",
      `Показано активное окно ${first}–${end} из ${items.length}; в DOM не более ${WINDOW_SIZE} строк.`,
    );
    const previous = document.getElementById("window-previous");
    const next = document.getElementById("window-next");
    if (previous) previous.disabled = start === 0;
    if (next) next.disabled = end >= items.length;
  }

  function switchDataset(dataset) {
    if (!(dataset in memory.datasets)) return;
    memory.activeDataset = dataset;
    memory.windowOffset = 0;
    document.querySelectorAll("[data-manifest-dataset]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.manifestDataset === dataset));
    });
    renderManifestWindow();
  }

  function bindManifestBrowser() {
    document.querySelectorAll("[data-manifest-dataset]").forEach((button) => {
      button.addEventListener("click", () => switchDataset(button.dataset.manifestDataset));
    });
    document.querySelectorAll("[data-show-dataset]").forEach((link) => {
      link.addEventListener("click", () => switchDataset(link.dataset.showDataset));
    });
    document.getElementById("window-previous")?.addEventListener("click", () => {
      memory.windowOffset = Math.max(0, memory.windowOffset - WINDOW_SIZE);
      renderManifestWindow();
    });
    document.getElementById("window-next")?.addEventListener("click", () => {
      const size = memory.datasets[memory.activeDataset].length;
      memory.windowOffset = Math.min(Math.max(0, size - 1), memory.windowOffset + WINDOW_SIZE);
      renderManifestWindow();
    });
    window.addEventListener("hashchange", selectDatasetFromFragment);
  }

  function selectDatasetFromFragment() {
    if (window.location.hash === "#actors") switchDataset("actors");
    if (window.location.hash === "#analytical-elements") switchDataset("analytical-elements");
  }

  function renderDefinition(dto, etag, dtoSyntax) {
    memory.definition = dto;
    memory.manifest = dto.manifest;
    const manifestSyntax = losslessObjectMember(dtoSyntax, "manifest");
    const actorSyntax = losslessObjectMember(manifestSyntax, "actors");
    const elementSyntax = losslessObjectMember(manifestSyntax, "analytical_elements");
    memory.datasets = {
      actors: Array.isArray(dto.manifest.actors) ? dto.manifest.actors : [],
      "analytical-elements": Array.isArray(dto.manifest.analytical_elements)
        ? dto.manifest.analytical_elements
        : [],
    };
    memory.datasetSyntax = {
      actors: actorSyntax?.kind === "array" ? actorSyntax.items : [],
      "analytical-elements": elementSyntax?.kind === "array" ? elementSyntax.items : [],
    };
    setText("project-id", dto.project_id);
    setText("manifest-sha", dto.manifest_hash);
    setText("manifest-etag", etag);
    setText("definition-label", exactValue(dto.manifest.project?.name));
    setText("definition-code", exactValue(dto.code));
    setText("definition-version", exactValue(dto.version));
    setText("definition-schema-version", exactValue(dto.schema_version));
    setText("definition-semantic-version", exactValue(dto.semantic_version));
    setText("definition-construct-version", exactValue(dto.construct_version));
    setText("definition-supersedes", exactValue(dto.supersedes_id));
    setText("publication-status", dto.publication_status);
    setText("actor-count", String(memory.datasets.actors.length));
    setText("element-count", String(memory.datasets["analytical-elements"].length));
    renderProject(
      dto.manifest.project,
      losslessObjectMember(manifestSyntax, "project"),
    );
    selectDatasetFromFragment();
    renderManifestWindow();
    const content = document.getElementById("definition-content");
    if (content) content.hidden = false;
  }

  function firstExactHelpBinding(manifest) {
    if (!Array.isArray(manifest.help_bindings)) return null;
    for (const item of manifest.help_bindings) {
      if (
        item &&
        item.application_scope === "STUDIO" &&
        typeof item.ui_key === "string" &&
        item.ui_key.length > 0 &&
        typeof item.locale === "string" &&
        item.locale.length > 0 &&
        typeof item.topic_stable_key === "string" &&
        item.topic_stable_key.length > 0 &&
        typeof item.topic_version === "string" &&
        item.topic_version.length > 0 &&
        item.version === item.topic_version &&
        typeof item.topic_sha256 === "string" &&
        SHA256_PATTERN.test(item.topic_sha256)
      ) {
        return item;
      }
    }
    return null;
  }

  function prepareHelp(manifest) {
    clearHelpContent();
    const binding = firstExactHelpBinding(manifest);
    memory.helpBindings = binding ? [binding] : [];
    memory.helpSettled = false;
    const select = document.getElementById("help-binding-select");
    const button = document.getElementById("load-help");
    if (!select || !button) return;
    if (binding) {
      const option = document.createElement("option");
      option.value = "0";
      option.textContent = `${binding.ui_key} · ${binding.locale} · ${binding.topic_version}`;
      select.append(option);
    }
    const available = memory.helpBindings.length > 0;
    select.disabled = !available;
    button.disabled = !available;
    if (!available) {
      const state = document.getElementById("help-state");
      if (state) {
        state.dataset.state = "HELP_UNAVAILABLE";
        state.textContent = "HELP_UNAVAILABLE: в manifest нет точной связки STUDIO; локальный fallback не используется.";
      }
      memory.helpSettled = true;
    } else {
      const state = document.getElementById("help-state");
      if (state) {
        state.dataset.state = "HELP_NOT_REQUESTED";
        state.textContent = "Точная связка из manifest готова к проверке Foundation.";
      }
    }
  }

  async function loadSelectedHelp() {
    const select = document.getElementById("help-binding-select");
    const button = document.getElementById("load-help");
    const state = document.getElementById("help-state");
    const topic = document.getElementById("help-topic");
    if (!select || !button || !state || !topic) return "settled";
    if (!memory.helpBindings.length) {
      memory.helpSettled = true;
      return "settled";
    }
    const binding = memory.helpBindings[Number(select.value) || 0];
    state.dataset.state = "HELP_LOADING";
    state.textContent = "Проверяем точную связку справки Foundation…";
    topic.hidden = true;
    button.disabled = true;
    const url = new URL(
      `${memory.app.dataset.helpBaseUrl}${encodeURIComponent(binding.ui_key)}/`,
      window.location.origin,
    );
    url.searchParams.set("application", "STUDIO");
    url.searchParams.set("locale", binding.locale);
    url.searchParams.set("version", binding.topic_version);
    try {
      const response = await fixedFetch(url.toString(), "application/json");
      if (response.status === 401) {
        statusFailure(401);
        return "fatal";
      }
      if (response.status === 404) {
        clearHelpContent(
          "HELP_TOPIC_NOT_FOUND: точная справка недоступна; fallback не используется.",
        );
        return "settled";
      }
      if (response.status !== 200) {
        clearHelpContent(
          "Точная справка недоступна: Foundation не подтвердил связку.",
        );
        return "settled";
      }
      const payload = JSON.parse(await response.text());
      const contentSha = await sha256Text(payload.sanitized_html);
      if (
        payload.stable_key !== binding.topic_stable_key ||
        payload.locale !== binding.locale ||
        payload.version !== binding.topic_version ||
        payload.content_sha256 !== binding.topic_sha256 ||
        contentSha !== binding.topic_sha256 ||
        typeof payload.title !== "string" ||
        typeof payload.sanitized_html !== "string"
      ) {
        throw new TypeError("help identity");
      }
      setText("help-title", payload.title);
      setText(
        "help-identity",
        `${payload.stable_key} · ${payload.locale} · ${payload.version} · SHA-256 ${payload.content_sha256}`,
      );
      document.getElementById("help-content").srcdoc = payload.sanitized_html;
      topic.hidden = false;
      state.dataset.state = "HELP_READY";
      state.textContent = "Точная справка Foundation проверена.";
      memory.helpSettled = true;
      return "settled";
    } catch (_error) {
      clearHelpContent(
        "Точная справка не прошла проверку идентичности; содержимое скрыто.",
      );
      return "settled";
    } finally {
      button.disabled = memory.helpBindings.length === 0;
    }
  }

  function bindHelp() {
    document.getElementById("load-help")?.addEventListener("click", () => loadSelectedHelp());
    document.getElementById("help-binding-select")?.addEventListener("change", () => {
      memory.helpSettled = false;
      const topic = document.getElementById("help-topic");
      if (topic) topic.hidden = true;
    });
  }

  async function exportFoundation() {
    const button = document.getElementById("export-foundation");
    if (!button || !memory.definition) return;
    button.disabled = true;
    setText("export-state", "Получаем и проверяем точные байты Foundation 2.1…");
    try {
      const response = await fixedFetch(memory.app.dataset.exportUrl, "application/json");
      if (response.status === 401) {
        statusFailure(401);
        return;
      }
      if (response.status !== 200) throw new TypeError("status");
      const bytes = new Uint8Array(await response.arrayBuffer());
      if (
        bytes.length < 2 ||
        bytes[bytes.length - 1] !== 0x0a ||
        bytes[bytes.length - 2] === 0x0a ||
        bytes[bytes.length - 2] === 0x0d
      ) {
        throw new TypeError("newline");
      }
      const representationSha = await sha256(bytes);
      if (response.headers.get("ETag") !== `"${representationSha}"`) {
        throw new TypeError("etag");
      }
      const expectedFilename = `foundation-definition-${memory.app.dataset.definitionId}-2.1.json`;
      if (
        response.headers.get("Content-Disposition") !==
        `attachment; filename="${expectedFilename}"`
      ) {
        throw new TypeError("filename");
      }
      const parsedPackage = parseLosslessJSON(
        new TextDecoder("utf-8", { fatal: true }).decode(bytes),
      );
      const packageData = parsedPackage.value;
      const semanticSha = response.headers.get("X-Foundation-Semantic-Payload-SHA256") || "";
      const recomputedSemanticSha = await sha256Text(
        canonicalLosslessJSON(parsedPackage.syntax, new Set(["manifest"])),
      );
      if (
        !SHA256_PATTERN.test(semanticSha) ||
        packageData.format !== "conflict-analysis-foundation" ||
        packageData.format_version !== "2.1.0" ||
        packageData.manifest?.hash_algorithm !== "sha256" ||
        packageData.manifest?.payload_sha256 !== semanticSha ||
        recomputedSemanticSha !== semanticSha ||
        packageData.package_scope !== "PROJECT_DEFINITION" ||
        String(packageData.selected_definition_id).toLowerCase() !==
          memory.app.dataset.definitionId.toLowerCase() ||
        String(packageData.project?.id).toLowerCase() !== memory.definition.project_id.toLowerCase()
      ) {
        throw new TypeError("semantic identity");
      }
      setText("export-representation-sha", representationSha);
      setText("export-semantic-sha", semanticSha);
      const blob = new Blob([bytes], { type: "application/json;charset=utf-8" });
      const href = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = href;
      link.download = expectedFilename;
      link.hidden = true;
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(href);
      setText(
        "export-state",
        "Точные байты проверены и переданы браузеру для выбранного пользователем скачивания.",
      );
    } catch (_error) {
      setText(
        "export-state",
        "Скачивание подавлено: точные байты, filename, ETag или semantic SHA не прошли проверку.",
      );
      setText("export-representation-sha", "—");
      setText("export-semantic-sha", "—");
    } finally {
      button.disabled = !memory.definition;
    }
  }

  function bindExport() {
    document.getElementById("export-foundation")?.addEventListener("click", exportFoundation);
  }

  function announceReady() {
    setShellState(
      "ready",
      "Точное определение открыто только для чтения",
      "Manifest SHA-256 и quoted ETag совпали; показан буквальный lifecycle status без вывода о текущей версии или научной корректности.",
    );
    memory.app.dispatchEvent(new CustomEvent("studio:ready", { bubbles: true }));
  }

  async function bootstrapDefinition() {
    const app = document.getElementById("studio-app");
    if (!app) return;
    memory.app = app;
    bindLayout();
    bindManifestBrowser();
    bindHelp();
    bindExport();

    setShellState("loading", "Проверяем контракт ограничений…", "Foundation ещё не запрошен.");
    if (!(await verifyClaimContract(app))) {
      failClosed(
        "Контракт ограничений не подтверждён",
        "Studio остановлен до отображения любых данных Foundation.",
      );
      return;
    }
    if (app.dataset.authenticated !== "true") {
      statusFailure(401);
      return;
    }
    setShellState("loading", "Проверяем Foundation…", "Запрашивается только точный UUID определения методом GET.");
    const result = await readDefinition();
    if (!result) return;
    renderDefinition(result.dto, result.etag, result.dtoSyntax);
    prepareHelp(result.dto.manifest);
    const helpResult = await loadSelectedHelp();
    if (helpResult === "fatal") return;
    announceReady();
  }

  function bindEntry() {
    const root = document.getElementById("studio-entry");
    const form = document.getElementById("definition-entry-form");
    const input = document.getElementById("definition-entry-id");
    const error = document.getElementById("definition-entry-error");
    if (!root || !form || !input || root.dataset.authenticated !== "true") return;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const identifier = input.value.trim().toLowerCase();
      const valid = UUID_PATTERN.test(identifier);
      input.setAttribute("aria-invalid", String(!valid));
      if (error) error.hidden = valid;
      if (!valid) return;
      window.location.assign(`${root.dataset.definitionBase}${encodeURIComponent(identifier)}/`);
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (document.body.dataset.studioPage === "definition") {
      bootstrapDefinition();
    } else if (document.body.dataset.studioPage === "entry") {
      bindEntry();
    }
  });
})();
