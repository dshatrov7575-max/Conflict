(function () {
  "use strict";

  const STORAGE_KEY = "conflict-analysis-studio:audited-draft-layout:v1";
  const LAYOUT_VERSION = "STUDIO_AUDITED_DRAFT_LAYOUT_V1";
  const CLAIM_CONTRACT = "STUDIO_AUDITED_DRAFT_CLAIM_BOUNDARIES_V1";
  const DEFAULT_LAYOUT = Object.freeze({
    version: LAYOUT_VERSION,
    left: 272,
    right: 360,
    activeRightTab: "help",
  });
  const LEFT_MIN = 220;
  const LEFT_MAX = 420;
  const RIGHT_MIN = 300;
  const RIGHT_MAX = 500;
  const LAYOUT_BYTE_LIMIT = 256;
  const WINDOW_SIZE = 100;
  const PREVIEW_DOM_LIMIT = 100;
  const HELP_OPTION_LIMIT = 100;
  const RAW_JSON_BYTE_LIMIT = 2_097_152;
  const UUID_PATTERN = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/;
  const UUID_V4_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
  const SHA256_PATTERN = /^[0-9a-f]{64}$/;
  const CODE_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/;
  const encoder = new TextEncoder();

  const memory = {
    app: null,
    definition: null,
    manifest: null,
    manifestSyntax: null,
    manifestHash: null,
    etag: null,
    activeSection: "actors",
    windowOffset: 0,
    dirty: false,
    busy: false,
    canEditStructure: false,
    unresolvedWrite: null,
    layout: { ...DEFAULT_LAYOUT },
  };

  function byId(id) {
    return document.getElementById(id);
  }

  function setText(id, value) {
    const node = byId(id);
    if (node) node.textContent = String(value);
  }

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

  function emit(name, detail) {
    window.dispatchEvent(new CustomEvent(name, { detail }));
  }

  function hasExactKeys(value, expected) {
    return (
      value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      Object.keys(value).sort().join("|") === [...expected].sort().join("|")
    );
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
      throw new SyntaxError(`Invalid JSON at offset ${offset}.`);
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

  function objectMemberEntry(node, name) {
    if (!node || node.kind !== "object") return null;
    return node.entries.find((entry) => entry.key.value === name) || null;
  }

  function objectMember(node, name) {
    return objectMemberEntry(node, name)?.value || null;
  }

  function canonicalLosslessJSON(node, omittedRootKeys = null) {
    if (!node || typeof node !== "object") throw new TypeError("JSON syntax required.");
    if (node.kind === "string") return JSON.stringify(node.value);
    if (node.kind === "number" || node.kind === "literal") return node.raw;
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

  function syntaxFromValue(value) {
    return parseLosslessJSON(JSON.stringify(value)).syntax;
  }

  function setObjectMember(node, name, value) {
    const entry = objectMemberEntry(node, name);
    if (!entry) throw new TypeError(`Required manifest member ${name} is absent.`);
    entry.value = syntaxFromValue(value);
  }

  function containsLoneUnicodeSurrogate(value) {
    if (typeof value === "string") {
      for (let index = 0; index < value.length; index += 1) {
        const unit = value.charCodeAt(index);
        if (unit < 0xd800 || unit > 0xdfff) continue;
        if (
          unit <= 0xdbff &&
          index + 1 < value.length &&
          value.charCodeAt(index + 1) >= 0xdc00 &&
          value.charCodeAt(index + 1) <= 0xdfff
        ) {
          index += 1;
          continue;
        }
        return true;
      }
      return false;
    }
    if (Array.isArray(value)) return value.some(containsLoneUnicodeSurrogate);
    if (value && typeof value === "object") {
      return Object.entries(value).some(
        ([key, item]) =>
          containsLoneUnicodeSurrogate(key) || containsLoneUnicodeSurrogate(item),
      );
    }
    return false;
  }

  function randomUUIDv4() {
    if (typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID().toLowerCase();
    }
    const bytes = new Uint8Array(16);
    window.crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (item) => item.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }

  function csrfToken() {
    const pair = document.cookie
      .split(";")
      .map((item) => item.trim())
      .find((item) => item.startsWith("csrftoken="));
    return pair ? decodeURIComponent(pair.slice("csrftoken=".length)) : null;
  }

  function setState(prefix, code, message, kind = "attention") {
    setText(`${prefix}-state-code`, code);
    setText(`${prefix}-state-message`, message);
    const node = byId(`${prefix}-state`);
    if (node) node.dataset.kind = kind;
  }

  async function verifyClaimContract() {
    const banner = byId("audited-draft-boundary-banner");
    if (!banner) throw new TypeError("Authoring claim banner is absent.");
    const expectedHash = banner.dataset.claimSha256 || "";
    const expectedBytes = Number(banner.dataset.claimBytes);
    const expectedUrl = banner.dataset.claimUrl || "";
    if (
      banner.dataset.claimContract !== CLAIM_CONTRACT ||
      banner.dataset.claimVersion !== "1.0.0" ||
      !SHA256_PATTERN.test(expectedHash) ||
      !Number.isSafeInteger(expectedBytes) ||
      expectedBytes <= 0 ||
      !expectedUrl.startsWith("/studio/claim-boundaries/audited-draft/v1/")
    ) {
      throw new TypeError("Authoring claim identity is invalid.");
    }
    const response = await fetch(expectedUrl, {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (
      response.status !== 200 ||
      bytes.byteLength !== expectedBytes ||
      response.headers.get("ETag") !== `"${expectedHash}"` ||
      (await sha256(bytes)) !== expectedHash
    ) {
      throw new TypeError("Authoring claim representation is invalid.");
    }
    const contract = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
    if (
      contract.contract !== CLAIM_CONTRACT ||
      contract.locale !== "ru" ||
      contract.version !== "1.0.0" ||
      !Array.isArray(contract.statements) ||
      contract.statements.length !== 11
    ) {
      throw new TypeError("Authoring claim envelope is invalid.");
    }
  }

  function parseLayout() {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw === null) return { ...DEFAULT_LAYOUT };
      if (utf8Length(raw) > LAYOUT_BYTE_LIMIT) throw new TypeError("oversize");
      const lossless = parseLosslessJSON(raw);
      const parsed = lossless.value;
      if (
        !parsed ||
        typeof parsed !== "object" ||
        Array.isArray(parsed) ||
        lossless.syntax.kind !== "object" ||
        lossless.syntax.entries.length !== 4 ||
        Object.keys(parsed).sort().join("|") !==
          "activeRightTab|left|right|version" ||
        parsed.version !== LAYOUT_VERSION ||
        !Number.isInteger(parsed.left) ||
        parsed.left < LEFT_MIN ||
        parsed.left > LEFT_MAX ||
        !Number.isInteger(parsed.right) ||
        parsed.right < RIGHT_MIN ||
        parsed.right > RIGHT_MAX ||
        parsed.activeRightTab !== "help"
      ) {
        throw new TypeError("invalid layout");
      }
      return parsed;
    } catch (_error) {
      try {
        window.localStorage.removeItem(STORAGE_KEY);
      } catch (_storageError) {
        // A denied optional preference store leaves the in-memory default intact.
      }
      return { ...DEFAULT_LAYOUT };
    }
  }

  function persistLayout() {
    const exact = {
      version: LAYOUT_VERSION,
      left: memory.layout.left,
      right: memory.layout.right,
      activeRightTab: "help",
    };
    const serialized = JSON.stringify(exact);
    if (utf8Length(serialized) > LAYOUT_BYTE_LIMIT) return;
    try {
      window.localStorage.setItem(STORAGE_KEY, serialized);
    } catch (_error) {
      // Layout remains usable in memory; no alternate storage is introduced.
    }
  }

  function clampInteger(value, minimum, maximum) {
    return Math.min(maximum, Math.max(minimum, Math.round(value)));
  }

  function applyLayout() {
    document.documentElement.style.setProperty(
      "--authoring-left-width",
      `${memory.layout.left}px`,
    );
    document.documentElement.style.setProperty(
      "--authoring-right-width",
      `${memory.layout.right}px`,
    );
    const left = byId("left-width-control");
    const right = byId("right-width-control");
    if (left) left.value = String(memory.layout.left);
    if (right) right.value = String(memory.layout.right);
    setText("left-width-output", memory.layout.left);
    setText("right-width-output", memory.layout.right);
    byId("authoring-left-resizer")?.setAttribute("aria-valuenow", String(memory.layout.left));
    byId("authoring-right-resizer")?.setAttribute("aria-valuenow", String(memory.layout.right));
  }

  function bindResizer(id, side) {
    const divider = byId(id);
    if (!divider) return;
    divider.addEventListener("keydown", (event) => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      const direction = event.key === "ArrowRight" ? 1 : -1;
      memory.layout[side] =
        side === "left"
          ? clampInteger(memory.layout[side] + direction * 8, LEFT_MIN, LEFT_MAX)
          : clampInteger(memory.layout[side] - direction * 8, RIGHT_MIN, RIGHT_MAX);
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

  function bindLayout() {
    memory.layout = parseLayout();
    applyLayout();
    const left = byId("left-width-control");
    const right = byId("right-width-control");
    left?.addEventListener("input", () => {
      memory.layout.left = clampInteger(Number(left.value), LEFT_MIN, LEFT_MAX);
      applyLayout();
      persistLayout();
    });
    right?.addEventListener("input", () => {
      memory.layout.right = clampInteger(Number(right.value), RIGHT_MIN, RIGHT_MAX);
      applyLayout();
      persistLayout();
    });
    bindResizer("authoring-left-resizer", "left");
    bindResizer("authoring-right-resizer", "right");
  }

  function typedMessage(status, code) {
    const messages = {
      AUTHENTICATION_REQUIRED: "Сессия отсутствует или истекла; автоматический повтор запрещён.",
      STUDIO_CAPABILITY_DENIED: "Для точного действия нет разрешения Foundation.",
      CSRF_FAILED: "Проверка безопасности сессии не пройдена; обновите страницу.",
      STUDIO_RESOURCE_NOT_FOUND: "Объект отсутствует или недоступен.",
      AUTHORING_ENVELOPE_INVALID: "Foundation отклонил точный конверт авторской операции.",
      RAW_JSON_INVALID: "Foundation отклонил точное JSON-представление.",
      RAW_JSON_UNICODE_SCALAR_INVALID: "Строка содержит недопустимую Unicode-последовательность.",
      IF_MATCH_REQUIRED: "Для сохранения требуется точный ETag.",
      IF_MATCH_INVALID: "If-Match не является точным strong ETag.",
      DRAFT_STALE: "Черновик изменился: перезагрузите и сравните, принудительная запись запрещена.",
      DEFINITION_NOT_DRAFT: "Это определение больше не является DRAFT.",
      DEFINITION_VALIDATION_FAILED: "Каноническая проверка Foundation отклонила черновик.",
      WRITE_OPERATION_KEY_REUSED: "Ключ операции уже принадлежит другому неизменяемому запросу.",
      PROJECT_ID_CONFLICT: "UUID проекта уже занят другой идентичностью.",
      PROJECT_CODE_VERSION_CONFLICT: "Код и версия проекта уже заняты другой идентичностью.",
      DEFINITION_ID_CONFLICT: "UUID определения уже занят другой идентичностью.",
      DEFINITION_CODE_VERSION_CONFLICT: "Код и версия определения уже заняты другой идентичностью.",
    };
    return messages[code] || `Foundation завершил запрос фиксированным состоянием HTTP ${status}.`;
  }

  async function parseJSONResponse(response) {
    const contentType = (response.headers.get("Content-Type") || "").toLowerCase();
    if (!contentType.startsWith("application/json")) {
      throw new TypeError("Expected an application/json response.");
    }
    const text = await response.text();
    return { ...parseLosslessJSON(text), text };
  }

  async function handleTypedFailure(response, definitionId, prefix) {
    let code = "FOUNDATION_REQUEST_FAILED";
    let payload = null;
    try {
      payload = (await parseJSONResponse(response)).value;
      if (payload && typeof payload.code === "string" && payload.code.length <= 128) {
        code = payload.code;
      }
    } catch (_error) {
      if (response.status === 403) code = "CSRF_FAILED";
    }
    if (response.status === 401) code = "AUTHENTICATION_REQUIRED";
    if (response.status === 404) code = "STUDIO_RESOURCE_NOT_FOUND";
    if (response.status === 403 && code === "FOUNDATION_REQUEST_FAILED") {
      code = "STUDIO_CAPABILITY_DENIED";
    }
    setState(prefix, code, typedMessage(response.status, code), "error");
    if (response.status === 409) {
      emit("studio:typed-conflict", {
        definitionId,
        code,
        status: response.status,
      });
    }
    return { code, payload };
  }

  function isAmbiguousWriteResponse(response) {
    return response.status === 408 || response.status === 425 || response.status === 429 || response.status >= 500;
  }

  async function verifyWriteReceipt({
    parsed,
    response,
    operation,
    operationId,
    definitionId,
    projectId,
    body,
    ifMatch,
    originalStatus,
  }) {
    const payload = parsed.value;
    const receipt = payload?.write_receipt;
    const receiptSyntax = objectMember(parsed.syntax, "write_receipt");
    if (!receipt || !receiptSyntax || typeof receipt !== "object") {
      throw new TypeError("Immutable write receipt is absent.");
    }
    const replayHeader = response.headers.get("X-Foundation-Operation-Replayed");
    const replayed = replayHeader === "true";
    const receiptHeader = response.headers.get("X-Foundation-Receipt-SHA256") || "";
    const etag = response.headers.get("ETag") || "";
    const after = receipt.after_definition;
    const requestIdentity = receipt.request;
    const bodySha = await sha256Text(body);
    const receiptSha = await sha256Text(canonicalLosslessJSON(receiptSyntax));
    const exactReceiptKeys = [
      "contract",
      "version",
      "operation",
      "operation_id",
      "audit_event_id",
      "audit_action",
      "actor_type",
      "actor_identifier",
      "project_id",
      "source_definition",
      "before_definition",
      "after_definition",
      "bootstrap_result",
      "validation",
      "request",
      "occurred_at",
      "original_http_status",
    ];
    const exactDefinitionKeys = [
      "contract",
      "id",
      "project_id",
      "code",
      "version",
      "publication_status",
      "manifest_hash",
      "schema_version",
      "semantic_version",
      "construct_version",
      "supersedes_id",
      "validated_at",
      "validated_by",
      "validation_result_sha256",
    ];
    const expectedAction = operation === "BOOTSTRAP_DRAFT" ? "CREATE" : "UPDATE";
    const bootstrap = receipt.bootstrap_result;
    const expectedGroup = `studio-project:${projectId}`;
    const operationShapeValid =
      operation === "BOOTSTRAP_DRAFT"
        ? receipt.before_definition === null &&
          bootstrap?.project?.id === projectId &&
          bootstrap?.object_scope_group?.name === expectedGroup &&
          bootstrap?.membership?.group === expectedGroup &&
          bootstrap?.membership?.actor_identifier === receipt.actor_identifier
        : receipt.before_definition &&
          hasExactKeys(receipt.before_definition, exactDefinitionKeys) &&
          String(receipt.before_definition.id).toLowerCase() === definitionId &&
          String(receipt.before_definition.project_id).toLowerCase() === projectId &&
          receipt.before_definition.manifest_hash === ifMatch &&
          bootstrap === null;
    const payloadShapeValid = replayed
      ? hasExactKeys(payload, ["code", "write_receipt"])
      : operation === "BOOTSTRAP_DRAFT"
        ? hasExactKeys(payload, [
            "project",
            "definition",
            "object_scope_group",
            "audit_event_id",
            "write_receipt",
          ])
        : hasExactKeys(payload, [
            "id",
            "project_id",
            "code",
            "version",
            "publication_status",
            "manifest",
            "manifest_hash",
            "schema_version",
            "semantic_version",
            "construct_version",
            "supersedes_id",
            "write_receipt",
          ]);
    if (
      !hasExactKeys(receipt, exactReceiptKeys) ||
      !hasExactKeys(after, exactDefinitionKeys) ||
      !hasExactKeys(requestIdentity, [
        "contract",
        "sha256",
        "raw_input_sha256",
        "raw_input_byte_length",
        "if_match",
      ]) ||
      receipt.contract !== "FOUNDATION_AUDITED_DEFINITION_WRITE_V1" ||
      receipt.version !== "1.0.0" ||
      receipt.operation !== operation ||
      receipt.operation_id !== operationId ||
      receipt.audit_event_id !== operationId ||
      receipt.actor_type !== "HUMAN" ||
      typeof receipt.actor_identifier !== "string" ||
      receipt.actor_identifier.length === 0 ||
      receipt.audit_action !== expectedAction ||
      receipt.project_id !== projectId ||
      receipt.original_http_status !== originalStatus ||
      !after ||
      after.contract !== "FOUNDATION_DEFINITION_IDENTITY_V1" ||
      String(after.id).toLowerCase() !== definitionId ||
      String(after.project_id).toLowerCase() !== projectId ||
      after.publication_status !== "DRAFT" ||
      !SHA256_PATTERN.test(String(after.manifest_hash || "")) ||
      !requestIdentity ||
      requestIdentity.contract !== "FOUNDATION_HUMAN_WRITE_REQUEST_IDENTITY_V1" ||
      requestIdentity.raw_input_sha256 !== bodySha ||
      requestIdentity.raw_input_byte_length !== utf8Length(body) ||
      requestIdentity.if_match !== ifMatch ||
      receipt.source_definition !== null ||
      receipt.validation !== null ||
      !operationShapeValid ||
      !payloadShapeValid ||
      !["true", "false"].includes(replayHeader) ||
      replayHeader !== String(replayed) ||
      !SHA256_PATTERN.test(receiptHeader) ||
      receiptHeader !== receiptSha ||
      etag !== `"${after.manifest_hash}"` ||
      (replayed && response.status !== 200)
    ) {
      throw new TypeError("Immutable write receipt identity is invalid.");
    }
    return {
      after,
      etag,
      manifestHash: after.manifest_hash,
      receipt,
      receiptSha,
      replayed,
    };
  }

  function exactBootstrapEnvelope() {
    const projectId = (byId("bootstrap-project-id")?.value || "").trim().toLowerCase();
    const definitionId = (byId("bootstrap-definition-id")?.value || "").trim().toLowerCase();
    const projectCode = (byId("bootstrap-project-code")?.value || "").trim();
    const projectVersion = (byId("bootstrap-project-version")?.value || "").trim();
    const projectName = (byId("bootstrap-project-name")?.value || "").trim();
    const projectDescription = byId("bootstrap-project-description")?.value || "";
    const definitionCode = (byId("bootstrap-definition-code")?.value || "").trim();
    const definitionVersion = (byId("bootstrap-definition-version")?.value || "").trim();
    const semanticVersion = (byId("bootstrap-semantic-version")?.value || "").trim();
    const constructVersion = (byId("bootstrap-construct-version")?.value || "").trim();
    if (
      !UUID_PATTERN.test(projectId) ||
      !UUID_PATTERN.test(definitionId) ||
      !CODE_PATTERN.test(projectCode) ||
      !CODE_PATTERN.test(definitionCode) ||
      !projectVersion ||
      projectVersion.length > 64 ||
      !definitionVersion ||
      definitionVersion.length > 64 ||
      !semanticVersion ||
      semanticVersion.length > 64 ||
      !constructVersion ||
      constructVersion.length > 64 ||
      !projectName ||
      projectName.length > 255
    ) {
      throw new TypeError("AUTHORING_ENVELOPE_INVALID");
    }
    const project = {
      id: projectId,
      code: projectCode,
      version: projectVersion,
      name: projectName,
      description: projectDescription,
      metadata: { studio_contract: CLAIM_CONTRACT },
    };
    const manifest = {
      $schema: "https://conflictology.invalid/schemas/project-definition-manifest-1.0.0.schema.json",
      format: "conflict-analysis-project-definition",
      format_version: "1.0.0",
      project: {
        ...project,
        default_locale: "ru",
      },
      policies: {
        structure_lock: {
          is_structure_locked: false,
          ordinary_user_can_edit_structure: false,
          studio_can_edit_structure: true,
          reason: "Audited DRAFT authoring",
        },
      },
      actors: [],
      analytical_elements: [],
      actor_element_roles: [],
      parameter_definitions: [],
      help_bindings: [],
    };
    const envelope = {
      project,
      definition: {
        id: definitionId,
        code: definitionCode,
        version: definitionVersion,
        manifest,
        semantic_version: semanticVersion,
        construct_version: constructVersion,
      },
    };
    if (containsLoneUnicodeSurrogate(envelope)) {
      throw new TypeError("AUTHORING_ENVELOPE_INVALID");
    }
    return { envelope, projectId, definitionId };
  }

  function setEntryBusy(busy) {
    memory.busy = busy;
    document
      .querySelectorAll("#bootstrap-draft-form input, #bootstrap-draft-form textarea")
      .forEach((control) => {
        control.disabled = busy || Boolean(memory.unresolvedWrite);
      });
    const submit = byId("bootstrap-draft");
    if (submit) submit.disabled = busy || Boolean(memory.unresolvedWrite);
    const manual = byId("bootstrap-manual-reconcile");
    if (manual) {
      manual.hidden = !memory.unresolvedWrite;
      manual.disabled = busy || !memory.unresolvedWrite;
    }
  }

  function markUnknownBootstrap(attempt) {
    memory.unresolvedWrite = attempt;
    setEntryBusy(false);
    setState(
      "entry",
      "UNKNOWN_TRANSPORT_OUTCOME",
      "Результат записи неизвестен. Автоматический повтор запрещён; доступна только ручная сверка тем же запросом.",
      "attention",
    );
  }

  async function performBootstrap(attempt) {
    const reconciling = memory.unresolvedWrite === attempt;
    setEntryBusy(true);
    let response;
    try {
      response = await fetch(attempt.url, attempt.options);
    } catch (_error) {
      markUnknownBootstrap(attempt);
      return;
    }
    if (isAmbiguousWriteResponse(response)) {
      markUnknownBootstrap(attempt);
      return;
    }
    if (response.status !== 201 && response.status !== 200) {
      memory.unresolvedWrite = reconciling ? attempt : null;
      setEntryBusy(false);
      await handleTypedFailure(response, attempt.definitionId, "entry");
      if (!reconciling) {
        const nextKey = randomUUIDv4();
        if (byId("bootstrap-operation-key")) byId("bootstrap-operation-key").value = nextKey;
      }
      return;
    }
    try {
      const parsed = await parseJSONResponse(response);
      const verified = await verifyWriteReceipt({
        parsed,
        response,
        operation: "BOOTSTRAP_DRAFT",
        operationId: attempt.operationId,
        definitionId: attempt.definitionId,
        projectId: attempt.projectId,
        body: attempt.body,
        ifMatch: null,
        originalStatus: 201,
      });
      if (
        (!verified.replayed && response.status !== 201) ||
        (!verified.replayed &&
          (String(parsed.value.definition?.id).toLowerCase() !== attempt.definitionId ||
            String(parsed.value.project?.id).toLowerCase() !== attempt.projectId))
      ) {
        throw new TypeError("Fresh bootstrap identity is invalid.");
      }
      memory.unresolvedWrite = null;
      setEntryBusy(false);
      setState(
        "entry",
        verified.replayed ? "WRITE_OPERATION_RECONCILED" : "BOOTSTRAP_DRAFT_CREATED",
        verified.replayed
          ? "Foundation подтвердил исходную операцию по неизменяемой квитанции."
          : "Проект и первый DRAFT созданы атомарно и подтверждены квитанцией.",
        "success",
      );
      emit("studio:bootstrap-complete", {
        projectId: attempt.projectId,
        definitionId: attempt.definitionId,
        operationId: attempt.operationId,
        receiptSha256: verified.receiptSha,
        replayed: verified.replayed,
        status: response.status,
      });
      const destination = `${memory.app.dataset.definitionBase}${attempt.definitionId}/`;
      window.setTimeout(() => window.location.assign(destination), 0);
    } catch (_error) {
      memory.unresolvedWrite = attempt;
      setEntryBusy(false);
      setState(
        "entry",
        "WRITE_RECEIPT_IDENTITY_MISMATCH",
        "Успешный ответ не прошёл проверку квитанции. Поля заморожены; разрешена только ручная сверка тем же запросом.",
        "error",
      );
    }
  }

  function bindEntry() {
    const projectId = randomUUIDv4();
    const definitionId = randomUUIDv4();
    const operationId = randomUUIDv4();
    byId("bootstrap-project-id").value = projectId;
    byId("bootstrap-definition-id").value = definitionId;
    byId("bootstrap-operation-key").value = operationId;
    byId("bootstrap-draft-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      if (memory.busy || memory.unresolvedWrite) return;
      const key = (byId("bootstrap-operation-key")?.value || "").trim().toLowerCase();
      const token = csrfToken();
      try {
        if (!UUID_V4_PATTERN.test(key) || !token) {
          throw new TypeError("AUTHORING_ENVELOPE_INVALID");
        }
        const exact = exactBootstrapEnvelope();
        const body = JSON.stringify(exact.envelope);
        if (utf8Length(body) > RAW_JSON_BYTE_LIMIT) {
          throw new TypeError("AUTHORING_ENVELOPE_INVALID");
        }
        const attempt = Object.freeze({
          url: memory.app.dataset.bootstrapUrl,
          operationId: key,
          projectId: exact.projectId,
          definitionId: exact.definitionId,
          body,
          options: Object.freeze({
            method: "POST",
            credentials: "same-origin",
            cache: "no-store",
            headers: Object.freeze({
              "Content-Type": "application/json",
              "X-CSRFToken": token,
              "Idempotency-Key": key,
            }),
            body,
          }),
        });
        performBootstrap(attempt);
      } catch (_error) {
        setState(
          "entry",
          "AUTHORING_ENVELOPE_INVALID",
          "Проверьте точные UUID, коды, версии, название и безопасность Unicode.",
          "error",
        );
      }
    });
    byId("bootstrap-manual-reconcile")?.addEventListener("click", () => {
      if (!memory.busy && memory.unresolvedWrite) {
        performBootstrap(memory.unresolvedWrite);
      }
    });
    byId("open-existing-draft-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      const identifier = (byId("existing-definition-id")?.value || "").trim().toLowerCase();
      if (!UUID_PATTERN.test(identifier)) {
        setState("entry", "DEFINITION_ID_INVALID", "Укажите точный UUID определения.", "error");
        return;
      }
      window.location.assign(`${memory.app.dataset.definitionBase}${identifier}/`);
    });
  }

  function manifestArray(name) {
    const value = memory.manifest?.[name];
    const syntax = objectMember(memory.manifestSyntax, name);
    if (!Array.isArray(value) || syntax?.kind !== "array" || value.length !== syntax.items.length) {
      throw new TypeError(`Manifest array ${name} is unavailable.`);
    }
    return { value, syntax };
  }

  function definitionEditable() {
    return (
      memory.definition?.publication_status === "DRAFT" &&
      !memory.busy &&
      !memory.unresolvedWrite
    );
  }

  function updateDefinitionControls() {
    const editable = definitionEditable();
    const structural = editable && memory.canEditStructure;
    const save = byId("save-draft");
    const preview = byId("preview-validation");
    const manual = byId("manual-reconcile");
    if (save) save.disabled = !editable || !memory.dirty;
    if (preview) preview.disabled = !editable;
    if (manual) {
      manual.hidden = !memory.unresolvedWrite;
      manual.disabled = memory.busy || !memory.unresolvedWrite;
    }
    ["project-name", "project-description"].forEach((id) => {
      const control = byId(id);
      if (control) control.disabled = !editable;
    });
    ["authoring-actors", "authoring-elements"].forEach((id) => {
      const control = byId(id);
      if (control) control.disabled = !editable;
    });
    const addActor = byId("add-actor");
    const addElement = byId("add-element");
    if (addActor) addActor.disabled = !structural;
    if (addElement) addElement.disabled = !structural;
  }

  function markDirty() {
    memory.dirty = true;
    setState(
      "authoring",
      "DRAFT_IN_MEMORY",
      "Изменения существуют только в памяти вкладки до явного сохранения.",
      "attention",
    );
    updateDefinitionControls();
  }

  function renderProject() {
    const project = memory.manifest.project;
    setText("project-id", project.id);
    setText("project-code", project.code);
    setText("project-version", project.version);
    setText("definition-id", memory.definition.id);
    setText("definition-status", memory.definition.publication_status);
    setText("definition-etag", memory.etag);
    const name = byId("project-name");
    const description = byId("project-description");
    if (name) name.value = project.name;
    if (description) description.value = project.description;
  }

  function rowButton(action, label, disabled) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.action = action;
    button.textContent = label;
    button.disabled = disabled;
    return button;
  }

  function sameParent(left, right) {
    return String(left?.parent_id || "").toLowerCase() === String(right?.parent_id || "").toLowerCase();
  }

  function siblingIndex(items, index, direction) {
    for (
      let candidate = index + direction;
      candidate >= 0 && candidate < items.length;
      candidate += direction
    ) {
      if (sameParent(items[index], items[candidate])) return candidate;
    }
    return -1;
  }

  function exactNonNegativeInteger(raw) {
    const match = raw.match(/^(\d+)(?:\.(\d+))?(?:[eE]([+-]?\d+))?$/);
    if (!match) return null;
    const fraction = match[2] || "";
    const exponent = Number(match[3] || "0");
    if (!Number.isSafeInteger(exponent) || Math.abs(exponent) > 10000) return null;
    let digits = `${match[1]}${fraction}`.replace(/^0+(?=\d)/, "");
    const scale = fraction.length - exponent;
    if (scale > 0) {
      if (scale > digits.length) return null;
      const removed = digits.slice(digits.length - scale);
      if (!/^0*$/.test(removed)) return null;
      digits = digits.slice(0, digits.length - scale) || "0";
    } else if (scale < 0) {
      digits += "0".repeat(-scale);
    }
    return BigInt(digits || "0");
  }

  function exactOrderRaw(syntaxItem) {
    const order = objectMember(syntaxItem, "order");
    if (
      !order ||
      order.kind !== "number" ||
      exactNonNegativeInteger(order.raw) === null
    ) {
      throw new TypeError("Manifest order must be an exact non-negative integer.");
    }
    return order.raw;
  }

  function renderRows() {
    const section = manifestArray(memory.activeSection);
    const total = section.value.length;
    const actorButton = byId("authoring-actors");
    const elementButton = byId("authoring-elements");
    if (actorButton) actorButton.dataset.totalCount = String(memory.manifest.actors.length);
    if (elementButton) {
      elementButton.dataset.totalCount = String(memory.manifest.analytical_elements.length);
    }
    setText("actor-count", memory.manifest.actors.length);
    setText("element-count", memory.manifest.analytical_elements.length);
    if (memory.windowOffset >= total) {
      memory.windowOffset = total === 0 ? 0 : Math.floor((total - 1) / WINDOW_SIZE) * WINDOW_SIZE;
    }
    const end = Math.min(total, memory.windowOffset + WINDOW_SIZE);
    const windowItems = section.value.slice(memory.windowOffset, end);
    setText("structure-title", memory.activeSection === "actors" ? "Акторы" : "Аналитические элементы");
    setText(
      "authoring-window-summary",
      total === 0 ? "Строки 0–0 из 0" : `Строки ${memory.windowOffset + 1}–${end} из ${total}`,
    );
    const pages = total === 0 ? 0 : Math.ceil(total / WINDOW_SIZE);
    const page = total === 0 ? 0 : Math.floor(memory.windowOffset / WINDOW_SIZE) + 1;
    setText("authoring-window-page", `Окно ${page} из ${pages}`);
    const previous = byId("authoring-window-prev");
    const next = byId("authoring-window-next");
    if (previous) previous.disabled = memory.busy || memory.windowOffset === 0;
    if (next) next.disabled = memory.busy || end >= total;
    const addActor = byId("add-actor");
    const addElement = byId("add-element");
    if (addActor) addActor.hidden = memory.activeSection !== "actors";
    if (addElement) addElement.hidden = memory.activeSection !== "analytical_elements";
    actorButton?.setAttribute("aria-pressed", String(memory.activeSection === "actors"));
    elementButton?.setAttribute(
      "aria-pressed",
      String(memory.activeSection === "analytical_elements"),
    );

    const body = byId("authoring-window");
    if (!body) return;
    body.replaceChildren();
    const disabled = !definitionEditable() || !memory.canEditStructure;
    windowItems.forEach((item, localIndex) => {
      const absoluteIndex = memory.windowOffset + localIndex;
      const row = document.createElement("tr");
      row.setAttribute("data-authoring-row", "true");
      row.dataset.itemId = String(item.id).toLowerCase();
      row.dataset.section = memory.activeSection;

      const order = document.createElement("td");
      order.textContent = exactOrderRaw(section.syntax.items[absoluteIndex]);
      const identity = document.createElement("td");
      const identityStack = document.createElement("span");
      identityStack.className = "row-identity";
      const code = document.createElement("code");
      code.textContent = item.code;
      const type = document.createElement("small");
      type.textContent = item.actor_type || item.element_type;
      identityStack.append(code, type);
      identity.append(identityStack);

      const labelCell = document.createElement("td");
      const label = document.createElement("input");
      label.type = "text";
      label.maxLength = 4096;
      label.value = item.label;
      label.dataset.field = "label";
      label.setAttribute("aria-label", `Название ${item.code}`);
      label.disabled = disabled;
      labelCell.append(label);

      const detailCell = document.createElement("td");
      const description = document.createElement("textarea");
      description.rows = 2;
      description.maxLength = 65536;
      description.value = item.description;
      description.dataset.field = "description";
      description.setAttribute("aria-label", `Описание ${item.code}`);
      description.disabled = disabled;
      detailCell.append(description);
      if (memory.activeSection === "analytical_elements") {
        const reference = document.createElement("textarea");
        reference.rows = 2;
        reference.maxLength = 65536;
        reference.value = item.reference_statement;
        reference.dataset.field = "reference_statement";
        reference.setAttribute("aria-label", `Reference statement ${item.code}`);
        reference.disabled = disabled;
        detailCell.append(reference);
      }

      const actions = document.createElement("td");
      actions.className = "row-actions";
      actions.append(
        rowButton("rename", "Переименовать", disabled),
        rowButton(
          "move-up",
          "Выше",
          disabled || siblingIndex(section.value, absoluteIndex, -1) < 0,
        ),
        rowButton(
          "move-down",
          "Ниже",
          disabled || siblingIndex(section.value, absoluteIndex, 1) < 0,
        ),
        rowButton("delete", "Удалить", disabled),
      );
      row.append(order, identity, labelCell, detailCell, actions);
      body.append(row);
    });
    updateDefinitionControls();
  }

  function updateManifestField(sectionName, itemId, field, value) {
    const section = manifestArray(sectionName);
    const index = section.value.findIndex(
      (item) => String(item.id).toLowerCase() === itemId,
    );
    if (index < 0) return;
    section.value[index][field] = value;
    setObjectMember(section.syntax.items[index], field, value);
    markDirty();
  }

  function filterParallel(sectionName, predicate) {
    const section = manifestArray(sectionName);
    for (let index = section.value.length - 1; index >= 0; index -= 1) {
      if (predicate(section.value[index])) {
        section.value.splice(index, 1);
        section.syntax.items.splice(index, 1);
      }
    }
  }

  function removeReferences(sectionName, itemId) {
    const roleIds = [];
    filterParallel("actor_element_roles", (role) => {
      const matches =
        (sectionName === "actors" && String(role.actor_id).toLowerCase() === itemId) ||
        (sectionName === "analytical_elements" &&
          String(role.element_id).toLowerCase() === itemId);
      if (matches) roleIds.push(String(role.id).toLowerCase());
      return matches;
    });
    const section = manifestArray(sectionName);
    let maximumRootOrder = -1n;
    section.value.forEach((item, index) => {
      if (item.parent_id === null) {
        const exact = exactNonNegativeInteger(exactOrderRaw(section.syntax.items[index]));
        if (exact === null) throw new TypeError("Exact root order is invalid.");
        if (exact > maximumRootOrder) maximumRootOrder = exact;
      }
    });
    section.value.forEach((item, index) => {
      if (String(item.parent_id || "").toLowerCase() === itemId) {
        item.parent_id = null;
        setObjectMember(section.syntax.items[index], "parent_id", null);
        maximumRootOrder += 1n;
        setExactOrder(section, index, String(maximumRootOrder));
      }
    });
    const parameters = manifestArray("parameter_definitions");
    parameters.value.forEach((parameter, parameterIndex) => {
      const applicability = parameter.applicability;
      const applicabilitySyntax = objectMember(
        parameters.syntax.items[parameterIndex],
        "applicability",
      );
      const filters = [
        [sectionName === "actors" ? "actor_ids" : "analytical_element_ids", new Set([itemId])],
        ["actor_element_role_ids", new Set(roleIds)],
      ];
      filters.forEach(([name, removed]) => {
        const values = applicability?.[name];
        const syntax = objectMember(applicabilitySyntax, name);
        if (!Array.isArray(values) || syntax?.kind !== "array") return;
        for (let index = values.length - 1; index >= 0; index -= 1) {
          if (removed.has(String(values[index]).toLowerCase())) {
            values.splice(index, 1);
            syntax.items.splice(index, 1);
          }
        }
      });
    });
  }

  function deleteItem(sectionName, itemId) {
    const section = manifestArray(sectionName);
    const index = section.value.findIndex(
      (item) => String(item.id).toLowerCase() === itemId,
    );
    if (index < 0) return;
    section.value.splice(index, 1);
    section.syntax.items.splice(index, 1);
    removeReferences(sectionName, itemId);
    markDirty();
    renderRows();
  }

  function setExactOrder(section, index, raw) {
    const entry = objectMemberEntry(section.syntax.items[index], "order");
    if (!entry || exactNonNegativeInteger(raw) === null) {
      throw new TypeError("Exact order syntax is unavailable.");
    }
    entry.value = { kind: "number", raw };
    const asNumber = Number(raw);
    section.value[index].order = Number.isSafeInteger(asNumber) ? asNumber : raw;
  }

  function moveItem(sectionName, itemId, direction) {
    const section = manifestArray(sectionName);
    const index = section.value.findIndex(
      (item) => String(item.id).toLowerCase() === itemId,
    );
    if (index < 0) return;
    const target = siblingIndex(section.value, index, direction);
    if (target < 0) return;
    const currentOrder = exactOrderRaw(section.syntax.items[index]);
    const targetOrder = exactOrderRaw(section.syntax.items[target]);
    [section.value[index], section.value[target]] = [section.value[target], section.value[index]];
    [section.syntax.items[index], section.syntax.items[target]] = [
      section.syntax.items[target],
      section.syntax.items[index],
    ];
    setExactOrder(section, index, currentOrder);
    setExactOrder(section, target, targetOrder);
    memory.windowOffset = Math.floor(target / WINDOW_SIZE) * WINDOW_SIZE;
    markDirty();
    renderRows();
  }

  function addItem(sectionName) {
    const section = manifestArray(sectionName);
    const id = randomUUIDv4();
    const suffix = id.replaceAll("-", "").slice(0, 12).toUpperCase();
    let maximumRootOrder = -1n;
    section.value.forEach((existing, index) => {
      if (existing.parent_id === null) {
        const exact = exactNonNegativeInteger(
          exactOrderRaw(section.syntax.items[index]),
        );
        if (exact === null) throw new TypeError("Exact root order is invalid.");
        if (exact > maximumRootOrder) maximumRootOrder = exact;
      }
    });
    const nextOrderRaw = String(maximumRootOrder + 1n);
    const nextOrderNumber = Number(nextOrderRaw);
    const item =
      sectionName === "actors"
        ? {
            id,
            code: `ACTOR-${suffix}`,
            version: "1.0.0",
            label: "Новый актор",
            description: "",
            actor_type: "OTHER",
            order: Number.isSafeInteger(nextOrderNumber) ? nextOrderNumber : nextOrderRaw,
            parent_id: null,
          }
        : {
            id,
            code: `ELEMENT-${suffix}`,
            version: "1.0.0",
            label: "Новый аналитический элемент",
            description: "",
            element_type: "CONFLICT_ISSUE",
            reference_statement: "Требуется проверяемое исходное утверждение.",
            order: Number.isSafeInteger(nextOrderNumber) ? nextOrderNumber : nextOrderRaw,
            parent_id: null,
          };
    section.value.push(item);
    const itemSyntax = syntaxFromValue(item);
    setExactOrder({ value: [item], syntax: { items: [itemSyntax] } }, 0, nextOrderRaw);
    section.syntax.items.push(itemSyntax);
    memory.windowOffset = Math.floor((section.value.length - 1) / WINDOW_SIZE) * WINDOW_SIZE;
    markDirty();
    renderRows();
  }

  function isExactHelpBinding(binding) {
    return Boolean(
      binding &&
        UUID_PATTERN.test(String(binding.id || "").toLowerCase()) &&
        CODE_PATTERN.test(String(binding.code || "")) &&
        typeof binding.version === "string" &&
        binding.version.length > 0 &&
        binding.version.length <= 64 &&
        binding.application_scope === "STUDIO" &&
        CODE_PATTERN.test(String(binding.ui_key || "")) &&
        typeof binding.locale === "string" &&
        binding.locale.length <= 32 &&
        /^[a-z]{2,3}(?:-[A-Z]{2})?$/.test(binding.locale) &&
        CODE_PATTERN.test(String(binding.topic_stable_key || "")) &&
        typeof binding.topic_version === "string" &&
        binding.topic_version.length > 0 &&
        binding.topic_version.length <= 64 &&
        SHA256_PATTERN.test(String(binding.topic_sha256 || "")),
    );
  }

  function prepareHelpBindings() {
    const select = byId("help-binding-select");
    const load = byId("load-help");
    if (!select || !load) return;
    select.replaceChildren();
    const bindings = Array.isArray(memory.manifest.help_bindings)
      ? memory.manifest.help_bindings
      : [];
    let validCount = 0;
    bindings.forEach((binding, index) => {
      if (!isExactHelpBinding(binding)) return;
      validCount += 1;
      if (validCount > HELP_OPTION_LIMIT) return;
      const option = document.createElement("option");
      option.value = String(index);
      option.textContent = `${binding.ui_key} · ${binding.locale} · ${binding.topic_version}`;
      select.append(option);
    });
    select.dataset.totalCount = String(validCount);
    select.disabled = validCount === 0;
    load.disabled = validCount === 0;
    setText(
      "help-state",
      validCount === 0
        ? "Точная привязка Help отсутствует; локального fallback нет."
        : validCount > HELP_OPTION_LIMIT
          ? `Доступны первые ${HELP_OPTION_LIMIT} из ${validCount} точных привязок.`
          : `Доступно точных привязок: ${validCount}.`,
    );
  }

  async function openDefinition() {
    let response;
    try {
      response = await fetch(memory.app.dataset.openUrl, {
        method: "GET",
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
    } catch (_error) {
      setState("authoring", "FOUNDATION_UNAVAILABLE", "Сетевой ответ не получен; данные не показаны.", "error");
      return false;
    }
    if (response.status !== 200) {
      await handleTypedFailure(response, memory.app.dataset.definitionId, "authoring");
      return false;
    }
    try {
      const parsed = await parseJSONResponse(response);
      const dto = parsed.value;
      const manifestSyntax = objectMember(parsed.syntax, "manifest");
      const definitionId = memory.app.dataset.definitionId.toLowerCase();
      const projectId = String(dto.project_id || "").toLowerCase();
      const etag = response.headers.get("ETag") || "";
      if (
        !dto ||
        String(dto.id || "").toLowerCase() !== definitionId ||
        !UUID_PATTERN.test(projectId) ||
        !SHA256_PATTERN.test(String(dto.manifest_hash || "")) ||
        !["DRAFT", "VALIDATED", "PUBLISHED", "RETIRED"].includes(dto.publication_status) ||
        !manifestSyntax ||
        manifestSyntax.kind !== "object" ||
        !dto.manifest ||
        dto.manifest.format !== "conflict-analysis-project-definition" ||
        dto.manifest.format_version !== "1.0.0" ||
        String(dto.manifest.project?.id || "").toLowerCase() !== projectId ||
        containsLoneUnicodeSurrogate(dto.manifest) ||
        (await sha256Text(canonicalLosslessJSON(manifestSyntax))) !== dto.manifest_hash ||
        etag !== `"${dto.manifest_hash}"`
      ) {
        throw new TypeError("Definition identity mismatch.");
      }
      memory.definition = dto;
      memory.manifest = dto.manifest;
      memory.manifestSyntax = manifestSyntax;
      memory.manifestHash = dto.manifest_hash;
      memory.etag = etag;
      const lock = dto.manifest.policies?.structure_lock;
      memory.canEditStructure = Boolean(
        lock && lock.studio_can_edit_structure === true && lock.is_structure_locked === false,
      );
      memory.app.dataset.projectId = projectId;
      memory.app.dataset.manifestHash = dto.manifest_hash;
      memory.app.dataset.etag = etag;
      renderProject();
      renderRows();
      prepareHelpBindings();
      if (dto.publication_status !== "DRAFT") {
        setState(
          "authoring",
          "DEFINITION_NOT_DRAFT",
          "Определение показано для точной идентификации, но C1 изменяет только DRAFT.",
          "attention",
        );
      } else {
        setState(
          "authoring",
          "AUTHORING_READY",
          "Точный DRAFT загружен; изменения будут храниться только в памяти до сохранения.",
          "success",
        );
      }
      updateDefinitionControls();
      emit("studio:authoring-ready", {
        definitionId,
        projectId,
        manifestHash: dto.manifest_hash,
        etag,
      });
      return true;
    } catch (_error) {
      setState(
        "authoring",
        "DEFINITION_IDENTITY_MISMATCH",
        "DTO, canonical manifest SHA-256 или quoted ETag не совпали; редактирование запрещено.",
        "error",
      );
      return false;
    }
  }

  function exactManifestBody() {
    if (!memory.manifest || !memory.manifestSyntax || containsLoneUnicodeSurrogate(memory.manifest)) {
      throw new TypeError("AUTHORING_ENVELOPE_INVALID");
    }
    const body = `{"manifest":${canonicalLosslessJSON(memory.manifestSyntax)}}`;
    if (utf8Length(body) > RAW_JSON_BYTE_LIMIT) {
      throw new TypeError("AUTHORING_ENVELOPE_INVALID");
    }
    return body;
  }

  function setDefinitionBusy(busy) {
    memory.busy = busy;
    updateDefinitionControls();
    if (memory.manifest) renderRows();
  }

  function markUnknownSave(attempt, identityMismatch = false) {
    memory.unresolvedWrite = attempt;
    setDefinitionBusy(false);
    setState(
      "authoring",
      identityMismatch
        ? "WRITE_RECEIPT_IDENTITY_MISMATCH"
        : "UNKNOWN_TRANSPORT_OUTCOME",
      identityMismatch
        ? "Успешный ответ не прошёл проверку квитанции. Черновик заморожен; разрешена только ручная сверка тем же запросом."
        : "Результат записи неизвестен. Автоматический повтор запрещён; разрешена только ручная сверка тем же телом, ключом и If-Match.",
      identityMismatch ? "error" : "attention",
    );
  }

  async function performSave(attempt) {
    const reconciling = memory.unresolvedWrite === attempt;
    setDefinitionBusy(true);
    let response;
    try {
      response = await fetch(attempt.url, attempt.options);
    } catch (_error) {
      markUnknownSave(attempt);
      return;
    }
    if (isAmbiguousWriteResponse(response)) {
      markUnknownSave(attempt);
      return;
    }
    if (response.status !== 200) {
      memory.unresolvedWrite = reconciling ? attempt : null;
      setDefinitionBusy(false);
      await handleTypedFailure(
        response,
        attempt.definitionId,
        "authoring",
      );
      return;
    }
    try {
      const parsed = await parseJSONResponse(response);
      const verified = await verifyWriteReceipt({
        parsed,
        response,
        operation: "SAVE_DRAFT",
        operationId: attempt.operationId,
        definitionId: attempt.definitionId,
        projectId: attempt.projectId,
        body: attempt.body,
        ifMatch: attempt.ifMatch,
        originalStatus: 200,
      });
      if (verified.manifestHash !== attempt.candidateHash) {
        throw new TypeError("Saved manifest hash differs from submitted candidate.");
      }
      if (!verified.replayed) {
        const manifestSyntax = objectMember(parsed.syntax, "manifest");
        if (
          String(parsed.value.id || "").toLowerCase() !== attempt.definitionId ||
          parsed.value.manifest_hash !== verified.manifestHash ||
          !manifestSyntax ||
          (await sha256Text(canonicalLosslessJSON(manifestSyntax))) !==
            verified.manifestHash
        ) {
          throw new TypeError("Fresh save representation is invalid.");
        }
        memory.definition = parsed.value;
        memory.manifest = parsed.value.manifest;
        memory.manifestSyntax = manifestSyntax;
      } else {
        memory.definition.manifest = memory.manifest;
        memory.definition.manifest_hash = verified.manifestHash;
      }
      memory.manifestHash = verified.manifestHash;
      memory.etag = verified.etag;
      memory.dirty = false;
      memory.unresolvedWrite = null;
      memory.app.dataset.manifestHash = verified.manifestHash;
      memory.app.dataset.etag = verified.etag;
      setText("last-receipt-sha", verified.receiptSha);
      setDefinitionBusy(false);
      renderProject();
      prepareHelpBindings();
      setState(
        "authoring",
        verified.replayed ? "WRITE_OPERATION_RECONCILED" : "DRAFT_SAVED",
        verified.replayed
          ? "Foundation подтвердил исходную запись по неизменяемой квитанции."
          : "DRAFT сохранён с точным ETag и неизменяемой HUMAN-квитанцией.",
        "success",
      );
      emit("studio:save-complete", {
        definitionId: attempt.definitionId,
        manifestHash: verified.manifestHash,
        etag: verified.etag,
        operationId: attempt.operationId,
        receiptSha256: verified.receiptSha,
        replayed: verified.replayed,
        status: response.status,
      });
    } catch (_error) {
      markUnknownSave(attempt, true);
    }
  }

  async function beginSave() {
    if (!definitionEditable() || !memory.dirty) return;
    const token = csrfToken();
    if (!token) {
      setState("authoring", "CSRF_TOKEN_UNAVAILABLE", "Обновите аутентифицированную страницу.", "error");
      return;
    }
    try {
      const body = exactManifestBody();
      const operationId = randomUUIDv4();
      const ifMatch = memory.manifestHash;
      const candidateHash = await sha256Text(canonicalLosslessJSON(memory.manifestSyntax));
      const attempt = Object.freeze({
        url: memory.app.dataset.saveUrl,
        definitionId: memory.app.dataset.definitionId.toLowerCase(),
        projectId: memory.app.dataset.projectId.toLowerCase(),
        operationId,
        ifMatch,
        candidateHash,
        body,
        options: Object.freeze({
          method: "PUT",
          credentials: "same-origin",
          cache: "no-store",
          headers: Object.freeze({
            "Content-Type": "application/json",
            "X-CSRFToken": token,
            "If-Match": `"${ifMatch}"`,
            "Idempotency-Key": operationId,
          }),
          body,
        }),
      });
      setText("authoring-operation-key", operationId);
      await performSave(attempt);
    } catch (_error) {
      setState(
        "authoring",
        "AUTHORING_ENVELOPE_INVALID",
        "Черновик содержит небезопасное или непредставимое JSON-значение; запрос не отправлен.",
        "error",
      );
    }
  }

  function renderValidation(report) {
    const root = byId("validation-summary");
    const list = byId("validation-diagnostics");
    if (!root || !list || !report || typeof report !== "object") return;
    const diagnostics = Array.isArray(report.diagnostics) ? report.diagnostics : [];
    const rendered = diagnostics.slice(0, PREVIEW_DOM_LIMIT);
    root.hidden = false;
    root.dataset.totalCount = String(report.diagnostics_total);
    root.dataset.returnedCount = String(report.diagnostics_returned);
    root.dataset.renderedCount = String(rendered.length);
    root.dataset.validationReportSha256 = String(report.validation_report_sha256 || "");
    setText("validation-state", report.valid ? "VALID" : "INVALID");
    setText("validation-total", report.diagnostics_total);
    setText("validation-rendered", rendered.length);
    setText("validation-report-sha", report.validation_report_sha256);
    list.replaceChildren();
    rendered.forEach((diagnostic) => {
      const item = document.createElement("li");
      item.dataset.ordinal = String(diagnostic.ordinal);
      item.dataset.code = String(diagnostic.code);
      const code = document.createElement("code");
      code.textContent = diagnostic.code;
      const text = document.createElement("span");
      text.textContent = ` ${diagnostic.path} — ${diagnostic.message}`;
      item.append(code, text);
      list.append(item);
    });
  }

  async function verifyValidationReport(parsed, response, body, candidateHash) {
    const report = parsed.value;
    const diagnostics = report?.diagnostics;
    const manifestIdentityIsValid =
      SHA256_PATTERN.test(String(report?.manifest_sha256 || "")) ||
      (report?.manifest_sha256 === "" && report?.valid === false);
    const representationHash = await sha256Text(parsed.text);
    const reportCoreHash = await sha256Text(
      canonicalLosslessJSON(parsed.syntax, new Set(["validation_report_sha256"])),
    );
    if (
      report.contract !== "PROJECT_DEFINITION_MANIFEST_VALIDATION_V1" ||
      report.contract_version !== "1.0.0" ||
      report.schema_id !==
        "https://conflictology.invalid/schemas/project-definition-manifest-1.0.0.schema.json" ||
      report.schema_version !== "1.0.0" ||
      String(report.definition_id).toLowerCase() !== memory.app.dataset.definitionId.toLowerCase() ||
      String(report.project_id).toLowerCase() !== memory.app.dataset.projectId.toLowerCase() ||
      report.base_manifest_sha256 !== memory.manifestHash ||
      report.request_sha256 !== (await sha256Text(body)) ||
      report.request_byte_length !== utf8Length(body) ||
      report.candidate_sha256 !== candidateHash ||
      !manifestIdentityIsValid ||
      typeof report.valid !== "boolean" ||
      !Array.isArray(diagnostics) ||
      diagnostics.length !== report.diagnostics_returned ||
      diagnostics.length > 1000 ||
      !Number.isSafeInteger(report.diagnostics_total) ||
      !Number.isSafeInteger(report.diagnostics_returned) ||
      report.diagnostics_total < diagnostics.length ||
      report.diagnostics_truncated !== (report.diagnostics_total > diagnostics.length) ||
      !SHA256_PATTERN.test(String(report.diagnostics_sha256 || "")) ||
      report.validation_report_sha256 !== reportCoreHash ||
      response.headers.get("ETag") !== `"${representationHash}"`
    ) {
      throw new TypeError("Validation report identity is invalid.");
    }
    for (let index = 0; index < diagnostics.length; index += 1) {
      const diagnostic = diagnostics[index];
      if (
        diagnostic.ordinal !== index ||
        !Number.isSafeInteger(diagnostic.ordinal) ||
        !["ERROR", "WARNING", "INFO"].includes(diagnostic.level) ||
        typeof diagnostic.code !== "string" ||
        diagnostic.code.length === 0 ||
        diagnostic.code.length > 128 ||
        typeof diagnostic.path !== "string" ||
        typeof diagnostic.message !== "string" ||
        utf8Length(diagnostic.path) > 512 ||
        utf8Length(diagnostic.message) > 512 ||
        !SHA256_PATTERN.test(String(diagnostic.path_sha256 || "")) ||
        !SHA256_PATTERN.test(String(diagnostic.message_sha256 || "")) ||
        (diagnostic.path !== "<TRUNCATED>" &&
          diagnostic.path_sha256 !== (await sha256Text(diagnostic.path))) ||
        (diagnostic.message !== "<TRUNCATED>" &&
          diagnostic.message_sha256 !== (await sha256Text(diagnostic.message)))
      ) {
        throw new TypeError("Validation diagnostic identity is invalid.");
      }
    }
    if (
      !report.diagnostics_truncated &&
      diagnostics.every(
        (item) => item.path !== "<TRUNCATED>" && item.message !== "<TRUNCATED>",
      )
    ) {
      const completeDiagnostics = diagnostics.map((item) => ({
        level: item.level,
        code: item.code,
        path: item.path,
        message: item.message,
      }));
      const diagnosticsHash = await sha256Text(
        canonicalLosslessJSON(syntaxFromValue(completeDiagnostics)),
      );
      if (diagnosticsHash !== report.diagnostics_sha256) {
        throw new TypeError("Complete diagnostic identity is invalid.");
      }
    }
    return report;
  }

  async function previewValidation() {
    if (!definitionEditable()) return;
    const token = csrfToken();
    if (!token) {
      setState("authoring", "CSRF_TOKEN_UNAVAILABLE", "Обновите аутентифицированную страницу.", "error");
      return;
    }
    let body;
    let candidateHash;
    try {
      body = exactManifestBody();
      candidateHash = await sha256Text(canonicalLosslessJSON(memory.manifestSyntax));
    } catch (_error) {
      setState("authoring", "AUTHORING_ENVELOPE_INVALID", "Unicode/JSON admission не пройдена.", "error");
      return;
    }
    setDefinitionBusy(true);
    let response;
    try {
      response = await fetch(memory.app.dataset.previewUrl, {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": token,
        },
        body,
      });
    } catch (_error) {
      setDefinitionBusy(false);
      setState("authoring", "FOUNDATION_UNAVAILABLE", "Предварительная проверка не получила ответа.", "error");
      return;
    }
    if (response.status !== 200) {
      setDefinitionBusy(false);
      await handleTypedFailure(response, memory.app.dataset.definitionId.toLowerCase(), "authoring");
      return;
    }
    try {
      const parsed = await parseJSONResponse(response);
      const report = await verifyValidationReport(parsed, response, body, candidateHash);
      renderValidation(report);
      setDefinitionBusy(false);
      setState(
        "authoring",
        report.valid ? "VALIDATION_PREVIEW_VALID" : "VALIDATION_PREVIEW_INVALID",
        report.valid
          ? "Канонический отчёт Foundation не содержит ошибок. Запись не выполнялась."
          : "Foundation вернул канонические диагностические данные. Запись не выполнялась.",
        report.valid ? "success" : "attention",
      );
      emit("studio:preview-complete", {
        definitionId: memory.app.dataset.definitionId.toLowerCase(),
        manifestHash: memory.manifestHash,
        valid: Boolean(report.valid),
        status: response.status,
      });
    } catch (_error) {
      setDefinitionBusy(false);
      setState(
        "authoring",
        "VALIDATION_REPORT_IDENTITY_MISMATCH",
        "Отчёт Foundation не прошёл проверку identity/hash и не показан.",
        "error",
      );
    }
  }

  async function loadSelectedHelp() {
    const select = byId("help-binding-select");
    const frame = byId("help-frame");
    const index = Number(select?.value);
    const binding = memory.manifest?.help_bindings?.[index];
    if (
      !select ||
      !frame ||
      !Number.isSafeInteger(index) ||
      !isExactHelpBinding(binding)
    ) {
      setText("help-state", "Точная привязка Help недоступна; запрос не выполнен.");
      return;
    }
    const query = new URLSearchParams({
      application: "STUDIO",
      locale: binding.locale,
      version: binding.topic_version,
    });
    const url = `${memory.app.dataset.helpBase}${encodeURIComponent(binding.ui_key)}/?${query.toString()}`;
    setText("help-state", "Загружается точная версия Foundation Help…");
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (response.status !== 200) {
        setText("help-state", "Точная Foundation Help недоступна; локального fallback нет.");
        frame.hidden = true;
        delete frame.dataset.contentSha256;
        return;
      }
      const parsed = await parseJSONResponse(response);
      const topic = parsed.value;
      if (
        topic.stable_key !== binding.topic_stable_key ||
        topic.version !== binding.topic_version ||
        topic.locale !== binding.locale ||
        topic.content_sha256 !== binding.topic_sha256 ||
        typeof topic.title !== "string" ||
        typeof topic.sanitized_html !== "string" ||
        (await sha256Text(topic.sanitized_html)) !== topic.content_sha256
      ) {
        throw new TypeError("Help identity mismatch.");
      }
      frame.srcdoc = topic.sanitized_html;
      frame.dataset.contentSha256 = topic.content_sha256;
      frame.hidden = false;
      setText("help-state", `${topic.title} · SHA-256 ${topic.content_sha256}`);
    } catch (_error) {
      frame.hidden = true;
      delete frame.dataset.contentSha256;
      setText("help-state", "Ответ Help не прошёл проверку точной tuple/hash; fallback запрещён.");
    }
  }

  function bindDefinitionControls() {
    byId("project-name")?.addEventListener("input", (event) => {
      if (!definitionEditable()) return;
      memory.manifest.project.name = event.target.value;
      setObjectMember(objectMember(memory.manifestSyntax, "project"), "name", event.target.value);
      markDirty();
    });
    byId("project-description")?.addEventListener("input", (event) => {
      if (!definitionEditable()) return;
      memory.manifest.project.description = event.target.value;
      setObjectMember(
        objectMember(memory.manifestSyntax, "project"),
        "description",
        event.target.value,
      );
      markDirty();
    });
    byId("authoring-actors")?.addEventListener("click", () => {
      memory.activeSection = "actors";
      memory.windowOffset = 0;
      renderRows();
    });
    byId("authoring-elements")?.addEventListener("click", () => {
      memory.activeSection = "analytical_elements";
      memory.windowOffset = 0;
      renderRows();
    });
    byId("authoring-window")?.addEventListener("input", (event) => {
      const field = event.target.dataset.field;
      const row = event.target.closest("[data-authoring-row]");
      if (!row || !["label", "description", "reference_statement"].includes(field)) return;
      updateManifestField(row.dataset.section, row.dataset.itemId, field, event.target.value);
    });
    byId("authoring-window")?.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-action]");
      const row = button?.closest("[data-authoring-row]");
      if (!button || !row || button.disabled) return;
      if (button.dataset.action === "rename") {
        row.querySelector('[data-field="label"]')?.focus();
        row.querySelector('[data-field="label"]')?.select();
      } else if (button.dataset.action === "delete") {
        deleteItem(row.dataset.section, row.dataset.itemId);
      } else if (button.dataset.action === "move-up") {
        moveItem(row.dataset.section, row.dataset.itemId, -1);
      } else if (button.dataset.action === "move-down") {
        moveItem(row.dataset.section, row.dataset.itemId, 1);
      }
    });
    byId("add-actor")?.addEventListener("click", () => addItem("actors"));
    byId("add-element")?.addEventListener("click", () => addItem("analytical_elements"));
    byId("authoring-window-prev")?.addEventListener("click", () => {
      memory.windowOffset = Math.max(0, memory.windowOffset - WINDOW_SIZE);
      renderRows();
    });
    byId("authoring-window-next")?.addEventListener("click", () => {
      memory.windowOffset += WINDOW_SIZE;
      renderRows();
    });
    byId("save-draft")?.addEventListener("click", beginSave);
    byId("preview-validation")?.addEventListener("click", previewValidation);
    byId("manual-reconcile")?.addEventListener("click", () => {
      if (!memory.busy && memory.unresolvedWrite) performSave(memory.unresolvedWrite);
    });
    byId("load-help")?.addEventListener("click", loadSelectedHelp);
  }

  async function initialise() {
    const entry = byId("audited-draft-entry");
    const definition = byId("audited-draft-app");
    memory.app = entry || definition;
    if (!memory.app || memory.app.dataset.authenticated !== "true") return;
    const prefix = entry ? "entry" : "authoring";
    try {
      await verifyClaimContract();
    } catch (_error) {
      setState(
        prefix,
        "AUTHORING_CLAIM_CONTRACT_MISMATCH",
        "Точный контракт ограничений не прошёл byte/hash-проверку; Foundation не вызван.",
        "error",
      );
      document.querySelectorAll("button, input, select, textarea").forEach((control) => {
        control.disabled = true;
      });
      return;
    }
    if (entry) {
      bindEntry();
      setEntryBusy(false);
      setState("entry", "READY", "Контракт проверен: доступен точный bootstrap или открытие UUID.", "success");
      return;
    }
    bindLayout();
    bindDefinitionControls();
    await openDefinition();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialise, { once: true });
  } else {
    initialise();
  }
})();
