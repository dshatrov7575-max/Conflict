(function () {
  "use strict";

  const CLAIM_CONTRACT = "STUDIO_LIFECYCLE_PUBLICATION_CLAIM_BOUNDARIES_V1";
  const READINESS_CONTRACT = "FOUNDATION_PUBLICATION_READINESS_V1";
  const HUMAN_TICKET_CONTRACT = "FOUNDATION_HUMAN_WRITE_RECOVERY_TICKET_V1";
  const HUMAN_RECEIPT_CONTRACT = "FOUNDATION_AUDITED_DEFINITION_WRITE_V1";
  const PUBLICATION_RESULT_CONTRACT = "FOUNDATION_PUBLICATION_OPERATION_RESULT_V1";
  const PUBLICATION_REQUEST_CONTRACT = "FOUNDATION_PUBLICATION_OPERATION_REQUEST_V1";
  const MANIFEST_VALIDATION_CONTRACT = "PROJECT_DEFINITION_MANIFEST_VALIDATION_V1";
  const MANIFEST_SCHEMA_ID = "https://conflictology.invalid/schemas/project-definition-manifest-1.0.0.schema.json";
  const JSON_CONTENT_TYPE = "application/json";
  const UUID_PATTERN = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/;
  const UUID_V4_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
  const SHA256_PATTERN = /^[0-9a-f]{64}$/;
  const LOCALE_PATTERN = /^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$/;
  const DEFINITION_STATUSES = Object.freeze(["DRAFT", "VALIDATED", "PUBLISHED", "RETIRED"]);
  const DEFINITION_KEYS = Object.freeze([
    "code",
    "construct_version",
    "id",
    "is_current",
    "manifest",
    "manifest_hash",
    "project_id",
    "publication_status",
    "published_at",
    "published_by",
    "schema_version",
    "semantic_version",
    "supersedes_id",
    "validated_at",
    "validated_by",
    "validation_result",
    "version",
  ]);
  const READINESS_KEYS = Object.freeze([
    "blocker_codes",
    "candidate_kind",
    "contract",
    "contract_version",
    "current_definition_id",
    "current_definition_publication_status",
    "definition_id",
    "initial_publication_receipt_count",
    "manifest_hash",
    "project_id",
    "project_publication_count",
    "project_workspace_count",
    "publication_status",
    "readiness_sha256",
    "required_next_action",
    "snapshot_scope",
    "supersedes_id",
    "validation_result_valid",
  ]);
  const TICKET_KEYS = Object.freeze([
    "body_byte_length",
    "body_sha256",
    "body_utf8",
    "content_type",
    "contract",
    "contract_version",
    "definition_id",
    "if_match",
    "method",
    "operation_id",
    "operation_kind",
    "project_id",
    "route",
    "ticket_sha256",
  ]);
  const HUMAN_RECEIPT_KEYS = Object.freeze([
    "actor_identifier",
    "actor_type",
    "after_definition",
    "audit_action",
    "audit_event_id",
    "before_definition",
    "bootstrap_result",
    "contract",
    "occurred_at",
    "operation",
    "operation_id",
    "original_http_status",
    "project_id",
    "request",
    "source_definition",
    "validation",
    "version",
  ]);
  const HUMAN_REQUEST_KEYS = Object.freeze([
    "contract",
    "if_match",
    "raw_input_byte_length",
    "raw_input_sha256",
    "sha256",
  ]);
  const DEFINITION_RECEIPT_KEYS = Object.freeze([
    "code",
    "construct_version",
    "contract",
    "id",
    "manifest_hash",
    "project_id",
    "publication_status",
    "schema_version",
    "semantic_version",
    "supersedes_id",
    "validated_at",
    "validated_by",
    "validation_result_sha256",
    "version",
  ]);
  const FRESH_VALIDATION_PAYLOAD_KEYS = Object.freeze([
    "code",
    "construct_version",
    "id",
    "manifest",
    "manifest_hash",
    "project_id",
    "publication_status",
    "schema_version",
    "semantic_version",
    "supersedes_id",
    "version",
    "write_receipt",
  ]);
  const PERSISTED_VALIDATION_KEYS = Object.freeze([
    "contract",
    "diagnostics",
    "manifest_sha256",
    "schema_id",
    "schema_version",
    "valid",
  ]);
  const PERSISTED_DIAGNOSTIC_KEYS = Object.freeze([
    "code",
    "level",
    "message",
    "path",
  ]);
  const PUBLICATION_RECEIPT_KEYS = Object.freeze([
    "actor_identifier",
    "contract",
    "contract_version",
    "definition",
    "help_binding_ids",
    "initial_workspace_definition_id",
    "initial_workspace_definition_manifest_hash",
    "initial_workspace_id",
    "locale",
    "operation_id",
    "operation_kind",
    "operation_request_sha256",
    "project_id",
    "publication_id",
    "published_at",
    "result_sha256",
    "validation_result",
  ]);
  const PUBLICATION_DEFINITION_KEYS = Object.freeze([
    "code",
    "construct_version",
    "id",
    "manifest",
    "manifest_hash",
    "project_id",
    "publication_status",
    "schema_version",
    "semantic_version",
    "supersedes_id",
    "version",
  ]);
  const encoder = new TextEncoder();

  const memory = {
    app: null,
    definition: null,
    definitionSyntax: null,
    manifestSyntax: null,
    readiness: null,
    actionKind: "NONE",
    sealedAttempt: null,
    unresolvedWrite: null,
    ticketRetained: false,
    busy: false,
    dirtyInputs: false,
    lastReceipt: null,
  };

  function byId(id) {
    return document.getElementById(id);
  }

  function setText(id, value) {
    const node = byId(id);
    if (node) node.textContent = String(value);
  }

  function emit(name, detail = {}) {
    window.dispatchEvent(new CustomEvent(name, { detail }));
  }

  function utf8Length(value) {
    return encoder.encode(value).byteLength;
  }

  async function sha256Bytes(bytes) {
    const digest = await window.crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest), (item) =>
      item.toString(16).padStart(2, "0"),
    ).join("");
  }

  async function sha256Text(value) {
    return sha256Bytes(encoder.encode(value));
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

  function compareUnicodeCodePoints(left, right) {
    const leftPoints = Array.from(left, (item) => item.codePointAt(0));
    const rightPoints = Array.from(right, (item) => item.codePointAt(0));
    const length = Math.min(leftPoints.length, rightPoints.length);
    for (let index = 0; index < length; index += 1) {
      if (leftPoints[index] !== rightPoints[index]) return leftPoints[index] - rightPoints[index];
    }
    return leftPoints.length - rightPoints.length;
  }

  function parseLosslessJSON(source) {
    if (typeof source !== "string") throw new TypeError("JSON source must be text.");
    let offset = 0;
    const fail = () => { throw new SyntaxError(`Invalid JSON at offset ${offset}.`); };
    const skipWhitespace = () => {
      while (/[\x20\x09\x0a\x0d]/.test(source[offset] || "")) offset += 1;
    };
    const parseString = () => {
      const start = offset;
      if (source[offset] !== '"') fail();
      offset += 1;
      while (offset < source.length) {
        const unit = source.charCodeAt(offset);
        if (unit === 0x22) {
          offset += 1;
          const raw = source.slice(start, offset);
          return { kind: "string", raw, value: JSON.parse(raw) };
        }
        if (unit < 0x20) fail();
        if (unit === 0x5c) {
          offset += 1;
          const escape = source[offset];
          if ('"\\/bfnrt'.includes(escape)) {
            offset += 1;
            continue;
          }
          if (escape === "u" && /^[0-9a-fA-F]{4}$/.test(source.slice(offset + 1, offset + 5))) {
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
      const matched = source.slice(offset).match(/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/);
      if (!matched) fail();
      offset += matched[0].length;
      return { kind: "number", raw: matched[0] };
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
      for (const [token, value] of [["true", true], ["false", false], ["null", null]]) {
        if (source.startsWith(token, offset)) {
          offset += token.length;
          return { kind: "literal", raw: token, value };
        }
      }
      return parseNumber();
    };
    const syntax = parseValue();
    skipWhitespace();
    if (offset !== source.length) fail();
    return { value: JSON.parse(source), syntax };
  }

  function objectMember(node, name) {
    if (!node || node.kind !== "object") return null;
    return node.entries.find((entry) => entry.key.value === name)?.value || null;
  }

  function canonicalLosslessJSON(node, omittedRootKeys = null) {
    if (node.kind === "string") return JSON.stringify(node.value);
    if (node.kind === "number" || node.kind === "literal") return node.raw;
    if (node.kind === "array") {
      return `[${node.items.map((item) => canonicalLosslessJSON(item)).join(",")}]`;
    }
    if (node.kind === "object") {
      return `{${node.entries
        .filter((entry) => !omittedRootKeys?.has(entry.key.value))
        .sort((left, right) => compareUnicodeCodePoints(left.key.value, right.key.value))
        .map((entry) => `${JSON.stringify(entry.key.value)}:${canonicalLosslessJSON(entry.value)}`)
        .join(",")}}`;
    }
    throw new TypeError("Value is outside JSON.");
  }

  function stableJSON(value) {
    if (value === null || typeof value === "boolean" || typeof value === "number") {
      if (typeof value === "number" && !Number.isFinite(value)) throw new TypeError("Non-finite JSON.");
      return JSON.stringify(value);
    }
    if (typeof value === "string") return JSON.stringify(value);
    if (Array.isArray(value)) return `[${value.map(stableJSON).join(",")}]`;
    if (value && typeof value === "object") {
      return `{${Object.keys(value)
        .sort(compareUnicodeCodePoints)
        .map((key) => `${JSON.stringify(key)}:${stableJSON(value[key])}`)
        .join(",")}}`;
    }
    throw new TypeError("Value is outside JSON.");
  }

  function exactKeys(value, keys) {
    return Boolean(
      value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      Object.keys(value).sort().join("|") === [...keys].sort().join("|"),
    );
  }

  function exactNullableTimestamp(value) {
    return value === null || (
      typeof value === "string" &&
      /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(value) &&
      !Number.isNaN(Date.parse(value))
    );
  }

  function exactTimestamp(value) {
    return value !== null && exactNullableTimestamp(value);
  }

  function exactNullableActor(value) {
    return (
      typeof value === "string" &&
      utf8Length(value) <= 512 &&
      !containsLoneUnicodeSurrogate(value)
    );
  }

  function exactBoundedText(value, byteLimit = 512) {
    return (
      typeof value === "string" &&
      value.length > 0 &&
      utf8Length(value) <= byteLimit &&
      !containsLoneUnicodeSurrogate(value)
    );
  }

  function exactHumanActor(value) {
    return exactBoundedText(value, 512) && /^django-user:[1-9][0-9]*$/.test(value);
  }

  function exactPersistedValidation(value, manifestHash) {
    return Boolean(
      exactKeys(value, PERSISTED_VALIDATION_KEYS) &&
      value.contract === MANIFEST_VALIDATION_CONTRACT &&
      value.schema_id === MANIFEST_SCHEMA_ID &&
      value.schema_version === "1.0.0" &&
      value.manifest_sha256 === manifestHash &&
      value.valid === true &&
      Array.isArray(value.diagnostics) &&
      value.diagnostics.length === 0
    );
  }

  function exactLifecycleShape(dto, manifestHash) {
    if (dto.publication_status === "DRAFT") {
      return (
        exactKeys(dto.validation_result, []) &&
        dto.validated_at === null &&
        dto.validated_by === "" &&
        dto.published_at === null &&
        dto.published_by === ""
      );
    }
    if (dto.publication_status === "VALIDATED") {
      return (
        exactPersistedValidation(dto.validation_result, manifestHash) &&
        exactTimestamp(dto.validated_at) &&
        exactHumanActor(dto.validated_by) &&
        dto.published_at === null &&
        dto.published_by === ""
      );
    }
    return (
      exactPersistedValidation(dto.validation_result, manifestHash) &&
      exactTimestamp(dto.validated_at) &&
      exactHumanActor(dto.validated_by) &&
      exactTimestamp(dto.published_at) &&
      exactHumanActor(dto.published_by)
    );
  }

  function csrfToken() {
    const pair = document.cookie
      .split(";")
      .map((item) => item.trim())
      .find((item) => item.startsWith("csrftoken="));
    return pair ? decodeURIComponent(pair.slice("csrftoken=".length)) : null;
  }

  function setState(code, message, kind = "attention") {
    setText("lifecycle-state-code", code);
    setText("lifecycle-state-message", message);
    const node = byId("lifecycle-state");
    if (node) node.dataset.kind = kind;
  }

  function normalizedVary(response) {
    return (response.headers.get("Vary") || "")
      .split(",")
      .map((item) => item.trim().toLowerCase())
      .filter(Boolean)
      .sort()
      .join("|");
  }

  async function responseDocument(response) {
    const text = await response.text();
    const parsed = parseLosslessJSON(text);
    return { ...parsed, text };
  }

  async function verifyClaimContract() {
    const banner = byId("lifecycle-boundary-banner");
    if (!banner) throw new TypeError("Lifecycle claim banner is absent.");
    const expectedHash = banner.dataset.claimSha256 || "";
    const expectedBytes = Number(banner.dataset.claimBytes);
    const url = banner.dataset.claimUrl || "";
    if (
      banner.dataset.claimContract !== CLAIM_CONTRACT ||
      banner.dataset.claimVersion !== "1.0.0" ||
      !SHA256_PATTERN.test(expectedHash) ||
      !Number.isSafeInteger(expectedBytes) ||
      expectedBytes <= 0 ||
      !url.startsWith("/studio/claim-boundaries/lifecycle-publication/v1/")
    ) throw new TypeError("Lifecycle claim identity is invalid.");
    const response = await fetch(url, {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
      redirect: "error",
      headers: { Accept: "application/json" },
    });
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (
      response.status !== 200 ||
      bytes.byteLength !== expectedBytes ||
      response.headers.get("ETag") !== `"${expectedHash}"` ||
      (await sha256Bytes(bytes)) !== expectedHash
    ) throw new TypeError("Lifecycle claim representation is invalid.");
    const contract = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
    if (
      contract.contract !== CLAIM_CONTRACT ||
      contract.version !== "1.0.0" ||
      contract.locale !== "ru" ||
      !Array.isArray(contract.statements) ||
      contract.statements.length !== 15
    ) throw new TypeError("Lifecycle claim envelope is invalid.");
  }

  function definitionIdentity(dto) {
    return {
      definition_id: String(dto.id).toLowerCase(),
      project_id: String(dto.project_id).toLowerCase(),
      manifest_hash: dto.manifest_hash,
      publication_status: dto.publication_status,
      is_current: dto.is_current,
      supersedes_id: dto.supersedes_id === null ? null : String(dto.supersedes_id).toLowerCase(),
      validation_result: dto.validation_result,
      validated_at: dto.validated_at,
      published_at: dto.published_at,
    };
  }

  async function fetchDefinition() {
    const response = await fetch(memory.app.dataset.openUrl, {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
      redirect: "error",
      headers: { Accept: "application/json" },
    });
    if (response.status !== 200) {
      const error = new Error(`FD03_${response.status}`);
      error.response = response;
      throw error;
    }
    const parsed = await responseDocument(response);
    const dto = parsed.value;
    const manifestSyntax = objectMember(parsed.syntax, "manifest");
    const definitionId = memory.app.dataset.definitionId.toLowerCase();
    const projectId = String(dto?.project_id || "").toLowerCase();
    const manifestHash = String(dto?.manifest_hash || "");
    const supersedesId = dto?.supersedes_id;
    if (
      !dto ||
      !exactKeys(dto, DEFINITION_KEYS) ||
      dto.id !== definitionId ||
      !UUID_PATTERN.test(dto.id) ||
      dto.project_id !== projectId ||
      !UUID_PATTERN.test(projectId) ||
      !SHA256_PATTERN.test(manifestHash) ||
      !DEFINITION_STATUSES.includes(dto.publication_status) ||
      !exactLifecycleShape(dto, manifestHash) ||
      typeof dto.is_current !== "boolean" ||
      !exactBoundedText(dto.code, 128) ||
      !exactBoundedText(dto.version, 64) ||
      !exactBoundedText(dto.schema_version, 64) ||
      !exactBoundedText(dto.semantic_version, 64) ||
      !exactBoundedText(dto.construct_version, 64) ||
      (supersedesId !== null && (
        String(supersedesId).toLowerCase() !== supersedesId ||
        !UUID_PATTERN.test(supersedesId)
      )) ||
      (dto.validation_result !== null && (
        typeof dto.validation_result !== "object" ||
        Array.isArray(dto.validation_result)
      )) ||
      !exactNullableTimestamp(dto.validated_at) ||
      !exactNullableTimestamp(dto.published_at) ||
      !exactNullableActor(dto.validated_by) ||
      !exactNullableActor(dto.published_by) ||
      !manifestSyntax ||
      manifestSyntax.kind !== "object" ||
      dto.manifest?.format !== "conflict-analysis-project-definition" ||
      dto.manifest?.format_version !== "1.0.0" ||
      String(dto.manifest?.project?.id || "").toLowerCase() !== projectId ||
      (await sha256Text(canonicalLosslessJSON(manifestSyntax))) !== manifestHash ||
      response.headers.get("ETag") !== `"${manifestHash}"`
    ) throw new TypeError("FD03 definition identity mismatch.");
    return { dto, syntax: parsed.syntax, manifestSyntax, identity: definitionIdentity(dto) };
  }

  async function fetchReadiness(definition) {
    const response = await fetch(memory.app.dataset.readinessUrl, {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
      redirect: "error",
      headers: { Accept: "application/json" },
    });
    if (response.status !== 200) {
      const error = new Error(`FD07_${response.status}`);
      error.response = response;
      throw error;
    }
    const parsed = await responseDocument(response);
    const dto = parsed.value;
    const readinessSha = String(dto?.readiness_sha256 || "");
    const core = { ...dto };
    delete core.readiness_sha256;
    const vary = normalizedVary(response);
    if (
      !exactKeys(dto, READINESS_KEYS) ||
      parsed.text !== `${stableJSON(dto)}\n` ||
      dto.contract !== READINESS_CONTRACT ||
      dto.contract_version !== "1.0.0" ||
      dto.snapshot_scope !== "LIFECYCLE_TOPOLOGY_ONLY" ||
      String(dto.project_id || "").toLowerCase() !== definition.identity.project_id ||
      String(dto.definition_id || "").toLowerCase() !== definition.identity.definition_id ||
      dto.manifest_hash !== definition.identity.manifest_hash ||
      dto.publication_status !== definition.identity.publication_status ||
      (dto.supersedes_id === null ? null : String(dto.supersedes_id).toLowerCase()) !==
        definition.identity.supersedes_id ||
      (dto.supersedes_id !== null && (
        String(dto.supersedes_id).toLowerCase() !== dto.supersedes_id ||
        !UUID_PATTERN.test(dto.supersedes_id)
      )) ||
      ![null, true, false].includes(dto.validation_result_valid) ||
      ![dto.project_publication_count, dto.project_workspace_count, dto.initial_publication_receipt_count]
        .every((value) => Number.isSafeInteger(value) && value >= 0) ||
      (
        dto.current_definition_id === null
          ? dto.current_definition_publication_status !== null
          : (
            String(dto.current_definition_id).toLowerCase() !== dto.current_definition_id ||
            !UUID_PATTERN.test(dto.current_definition_id) ||
            !DEFINITION_STATUSES.includes(dto.current_definition_publication_status)
          )
      ) ||
      !["NONE", "INITIAL", "SUCCESSOR"].includes(dto.candidate_kind) ||
      !["NONE", "PREVIEW_OR_INITIAL_PUBLISH", "VALIDATE", "SUCCESSOR_PUBLISH"].includes(
        dto.required_next_action,
      ) ||
      !Array.isArray(dto.blocker_codes) ||
      !dto.blocker_codes.every((item) => typeof item === "string" && item.length > 0) ||
      !SHA256_PATTERN.test(readinessSha) ||
      (await sha256Text(stableJSON(core))) !== readinessSha ||
      response.headers.get("ETag") !== `"${readinessSha}"` ||
      response.headers.get("Cache-Control") !== "no-store" ||
      vary !== "authorization|cookie"
    ) throw new TypeError("FD07 readiness identity mismatch.");
    return dto;
  }

  function snapshotIdentity(definition, readiness) {
    return stableJSON({
      definition: definition.identity,
      readiness,
    });
  }

  function computeActionKind(definition, readiness) {
    const canValidate = memory.app.dataset.canValidate === "true";
    const canPublish = memory.app.dataset.canPublish === "true";
    if (
      definition.dto.publication_status === "DRAFT" &&
      readiness.candidate_kind === "INITIAL" &&
      readiness.required_next_action === "PREVIEW_OR_INITIAL_PUBLISH" &&
      canValidate &&
      canPublish
    ) return "PUBLISH_INITIAL";
    if (
      definition.dto.publication_status === "DRAFT" &&
      readiness.candidate_kind === "SUCCESSOR" &&
      readiness.required_next_action === "VALIDATE" &&
      canValidate
    ) return "VALIDATE_DEFINITION";
    if (
      definition.dto.publication_status === "VALIDATED" &&
      readiness.validation_result_valid === true &&
      readiness.candidate_kind === "SUCCESSOR" &&
      readiness.required_next_action === "SUCCESSOR_PUBLISH" &&
      canPublish
    ) return "PUBLISH_SUCCESSOR";
    return "NONE";
  }

  function renderSnapshot() {
    const definition = memory.definition?.dto;
    const readiness = memory.readiness;
    if (!definition || !readiness) return;
    setText("lifecycle-project-id", definition.project_id);
    setText("lifecycle-definition-id", definition.id);
    setText("lifecycle-manifest-hash", definition.manifest_hash);
    setText("lifecycle-publication-status", definition.publication_status);
    setText("lifecycle-is-current", definition.is_current ? "true" : "false");
    setText("lifecycle-supersedes-id", definition.supersedes_id ?? "null");
    setText("lifecycle-validated-at", definition.validated_at ?? "null");
    setText("lifecycle-published-at", definition.published_at ?? "null");
    setText("readiness-candidate-kind", readiness.candidate_kind);
    setText("readiness-next-action", readiness.required_next_action);
    setText("readiness-sha256", readiness.readiness_sha256);
    setText("readiness-publication-count", readiness.project_publication_count);
    setText("readiness-workspace-count", readiness.project_workspace_count);
    setText("readiness-current-definition", readiness.current_definition_id ?? "null");
    setText("readiness-blockers", readiness.blocker_codes.length ? readiness.blocker_codes.join(", ") : "NONE");
    const warning = byId("persisted-validation-warning");
    if (warning) warning.hidden = definition.publication_status !== "VALIDATED";
    const initial = byId("initial-workspace-controls");
    if (initial) initial.hidden = memory.actionKind !== "PUBLISH_INITIAL";
  }

  async function readFreshSnapshot({ rejectDrift = false } = {}) {
    const previousIdentity =
      rejectDrift && memory.definition && memory.readiness
        ? snapshotIdentity(memory.definition, memory.readiness)
        : null;
    const definition = await fetchDefinition();
    const readiness = await fetchReadiness(definition);
    const nextIdentity = snapshotIdentity(definition, readiness);
    memory.definition = definition;
    memory.definitionSyntax = definition.syntax;
    memory.manifestSyntax = definition.manifestSyntax;
    memory.readiness = readiness;
    memory.actionKind = computeActionKind(definition, readiness);
    renderSnapshot();
    updateControls();
    if (previousIdentity !== null && previousIdentity !== nextIdentity) {
      discardUnsentAttempt("FRESH_SNAPSHOT_DRIFT", false);
      setState(
        "FRESH_SNAPSHOT_DRIFT",
        "FD03/FD07 изменились. Неподанная подготовка отброшена; POST не выполнен.",
        "attention",
      );
      emit("studio:lifecycle-snapshot-drift", {
        definitionId: definition.identity.definition_id,
        readinessSha256: readiness.readiness_sha256,
      });
      return false;
    }
    return true;
  }

  function actionLabel(kind) {
    return {
      VALIDATE_DEFINITION: "Подготовить валидацию преемника FD05",
      PUBLISH_INITIAL: "Подготовить атомарную первую публикацию FD06",
      PUBLISH_SUCCESSOR: "Подготовить публикацию преемника FD06",
      NONE: "Нет доступного lifecycle-действия",
    }[kind];
  }

  function updateControls() {
    const frozen = Boolean(memory.sealedAttempt || memory.unresolvedWrite);
    const unavailable = memory.busy || frozen;
    const prepare = byId("prepare-lifecycle-attempt");
    const preview = byId("preview-lifecycle");
    const refresh = byId("refresh-lifecycle");
    const cancel = byId("cancel-lifecycle-attempt");
    if (prepare) {
      prepare.textContent = actionLabel(memory.actionKind);
      prepare.disabled = unavailable || memory.actionKind === "NONE";
    }
    if (preview) {
      preview.disabled =
        unavailable ||
        memory.app.dataset.canPreview !== "true" ||
        memory.readiness?.candidate_kind !== "INITIAL" ||
        memory.readiness?.required_next_action !== "PREVIEW_OR_INITIAL_PUBLISH";
    }
    if (refresh) refresh.disabled = unavailable;
    if (cancel) {
      cancel.hidden = !memory.sealedAttempt || Boolean(memory.unresolvedWrite);
      cancel.disabled = memory.busy || !memory.sealedAttempt || Boolean(memory.unresolvedWrite);
    }
    document
      .querySelectorAll("#publication-inputs input, #publication-inputs textarea")
      .forEach((control) => { control.disabled = unavailable; });
    const execute = byId("execute-sealed-attempt");
    if (execute) {
      execute.disabled =
        memory.busy ||
        !memory.sealedAttempt ||
        Boolean(memory.unresolvedWrite) ||
        !memory.ticketRetained;
    }
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
        ([key, item]) => containsLoneUnicodeSurrogate(key) || containsLoneUnicodeSurrogate(item),
      );
    }
    return false;
  }

  function exactAttemptBody(kind) {
    if (kind === "VALIDATE_DEFINITION") return "{}";
    const locale = byId("publication-locale")?.value || "";
    if (!LOCALE_PATTERN.test(locale) || locale.length > 32 || containsLoneUnicodeSurrogate(locale)) {
      throw new TypeError("Publication locale is invalid.");
    }
    if (kind === "PUBLISH_SUCCESSOR") return `{"locale":${JSON.stringify(locale)}}`;
    if (kind !== "PUBLISH_INITIAL") throw new TypeError("Lifecycle action is unavailable.");
    const workspace = {
      id: byId("workspace-id")?.value || "",
      code: byId("workspace-code")?.value || "",
      version: byId("workspace-version")?.value || "",
      name: byId("workspace-name")?.value || "",
    };
    if (
      !UUID_PATTERN.test(workspace.id) ||
      !exactBoundedText(workspace.code, 128) ||
      !exactBoundedText(workspace.version, 64) ||
      !exactBoundedText(workspace.name, 255)
    ) throw new TypeError("Initial workspace fields are invalid.");
    const rawMetadata = byId("workspace-metadata")?.value || "";
    const metadata = parseLosslessJSON(rawMetadata);
    if (
      metadata.syntax.kind !== "object" ||
      utf8Length(rawMetadata) > 8_192 ||
      containsLoneUnicodeSurrogate(metadata.value)
    ) throw new TypeError("Workspace metadata must be a bounded object.");
    return (
      `{"locale":${JSON.stringify(locale)},"workspace":{` +
      `"code":${JSON.stringify(workspace.code)},` +
      `"id":${JSON.stringify(workspace.id)},` +
      `"is_default":true,` +
      `"metadata":${canonicalLosslessJSON(metadata.syntax)},` +
      `"name":${JSON.stringify(workspace.name)},` +
      `"version":${JSON.stringify(workspace.version)}}}`
    );
  }

  function expectedRouteForAction(kind, definitionId = null) {
    const resolved = String(
      definitionId ||
      memory.definition?.identity.definition_id ||
      memory.app?.dataset.definitionId ||
      "",
    ).toLowerCase();
    if (!UUID_PATTERN.test(resolved)) return null;
    return {
      VALIDATE_DEFINITION: `/api/foundation/definitions/${resolved}/validate/`,
      PUBLISH_INITIAL: `/api/foundation/definitions/${resolved}/publish-initial/`,
      PUBLISH_SUCCESSOR: `/api/foundation/definitions/${resolved}/publish-successor/`,
    }[kind] || null;
  }

  function routeForAction(kind) {
    const presented = {
      VALIDATE_DEFINITION: memory.app.dataset.validateUrl,
      PUBLISH_INITIAL: memory.app.dataset.publishInitialUrl,
      PUBLISH_SUCCESSOR: memory.app.dataset.publishSuccessorUrl,
    }[kind] || null;
    const expected = expectedRouteForAction(kind);
    return presented === expected ? expected : null;
  }

  async function buildTicket(attemptCore) {
    const ticketCore = {
      contract: HUMAN_TICKET_CONTRACT,
      contract_version: "1.0.0",
      operation_kind: attemptCore.operationKind,
      operation_id: attemptCore.operationId,
      project_id: attemptCore.projectId,
      definition_id: attemptCore.definitionId,
      method: "POST",
      route: attemptCore.route,
      if_match: attemptCore.ifMatch,
      content_type: JSON_CONTENT_TYPE,
      body_utf8: attemptCore.body,
      body_sha256: attemptCore.bodySha256,
      body_byte_length: attemptCore.bodyByteLength,
    };
    const ticketSha256 = await sha256Text(stableJSON(ticketCore));
    const ticket = Object.freeze({ ...ticketCore, ticket_sha256: ticketSha256 });
    return Object.freeze({ ticket, text: `${stableJSON(ticket)}\n` });
  }

  async function prepareAttempt() {
    if (memory.busy || memory.sealedAttempt || memory.unresolvedWrite || memory.actionKind === "NONE") return;
    memory.busy = true;
    updateControls();
    const selectedAction = memory.actionKind;
    try {
      if (!(await readFreshSnapshot({ rejectDrift: true }))) return;
      if (memory.actionKind !== selectedAction) {
        setState("LIFECYCLE_ACTION_CHANGED", "Доступное действие изменилось; POST не выполнен.", "attention");
        return;
      }
      const route = routeForAction(selectedAction);
      if (!route || route !== expectedRouteForAction(selectedAction)) {
        throw new TypeError("Sealed request route identity is unavailable.");
      }
      const body = exactAttemptBody(selectedAction);
      const operationId = randomUUIDv4();
      const manifestHash = memory.definition.identity.manifest_hash;
      const attemptCore = {
        operationKind: selectedAction,
        operationId,
        projectId: memory.definition.identity.project_id,
        definitionId: memory.definition.identity.definition_id,
        definitionCode: memory.definition.dto.code,
        definitionVersion: memory.definition.dto.version,
        schemaVersion: memory.definition.dto.schema_version,
        semanticVersion: memory.definition.dto.semantic_version,
        constructVersion: memory.definition.dto.construct_version,
        supersedesId: memory.definition.identity.supersedes_id,
        route,
        ifMatch: `"${manifestHash}"`,
        body,
        bodySha256: await sha256Text(body),
        bodyByteLength: utf8Length(body),
        readinessSha256: memory.readiness.readiness_sha256,
      };
      const ticket = await buildTicket(attemptCore);
      memory.sealedAttempt = Object.freeze({
        ...attemptCore,
        ticket: ticket.ticket,
        ticketText: ticket.text,
        imported: false,
      });
      memory.ticketRetained = false;
      renderAttempt(memory.sealedAttempt);
      setState(
        "SEALED_ATTEMPT_PREPARED",
        "Attempt неизменяем. Сохраните HUMAN-ticket; до этого POST заблокирован.",
        "attention",
      );
      emit("studio:lifecycle-attempt-prepared", {
        operationKind: selectedAction,
        operationId,
        projectId: attemptCore.projectId,
        definitionId: attemptCore.definitionId,
        route,
        ifMatch: attemptCore.ifMatch,
        bodySha256: attemptCore.bodySha256,
        bodyByteLength: attemptCore.bodyByteLength,
        ticketSha256: ticket.ticket.ticket_sha256,
      });
    } catch (_error) {
      discardUnsentAttempt("ATTEMPT_PREPARATION_FAILED", false);
      setState(
        "ATTEMPT_PREPARATION_FAILED",
        "Точные route, CSRF, If-Match или видимые параметры не прошли проверку; POST не выполнен.",
        "error",
      );
    } finally {
      memory.busy = false;
      updateControls();
    }
  }

  function renderAttempt(attempt) {
    const panel = byId("sealed-attempt-panel");
    if (panel) panel.hidden = false;
    setText("attempt-kind", attempt.operationKind);
    setText("attempt-operation-id", attempt.operationId);
    setText("attempt-route", attempt.route);
    setText("attempt-if-match", attempt.ifMatch);
    setText("attempt-body-sha256", attempt.bodySha256);
    setText("attempt-body-length", attempt.bodyByteLength);
    const ticket = byId("recovery-ticket");
    if (ticket) ticket.value = attempt.ticketText;
    const proof = byId("ticket-copy-proof");
    if (proof) proof.value = "";
    setText("ticket-retention-state", "POST заблокирован до HUMAN-retention ticket.");
    const unknown = byId("unknown-outcome-panel");
    if (unknown) unknown.hidden = true;
    updateControls();
  }

  function retainTicket(method) {
    if (!memory.sealedAttempt || memory.busy || memory.unresolvedWrite) return;
    memory.ticketRetained = true;
    setText(
      "ticket-retention-state",
      method === "download"
        ? "HUMAN download инициирован; sealed POST разблокирован."
        : "Точное совпадение скопированного ticket подтверждено; sealed POST разблокирован.",
    );
    updateControls();
    emit("studio:lifecycle-ticket-retained", {
      method,
      operationKind: memory.sealedAttempt.operationKind,
      operationId: memory.sealedAttempt.operationId,
      ticketSha256: memory.sealedAttempt.ticket.ticket_sha256,
    });
  }

  function downloadTicket() {
    if (!memory.sealedAttempt || memory.busy || memory.unresolvedWrite) return;
    const blob = new Blob([encoder.encode(memory.sealedAttempt.ticketText)], {
      type: "application/json;charset=utf-8",
    });
    const href = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = href;
    link.download = `foundation-human-write-recovery-${memory.sealedAttempt.operationId}.json`;
    link.hidden = true;
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(href);
    retainTicket("download");
  }

  function acknowledgeExactCopy() {
    if (!memory.sealedAttempt || memory.busy || memory.unresolvedWrite) return;
    if (byId("ticket-copy-proof")?.value !== memory.sealedAttempt.ticketText) {
      setText("ticket-retention-state", "Копия не совпала с точным ticket; POST остаётся заблокирован.");
      return;
    }
    retainTicket("exact-copy");
  }

  function discardUnsentAttempt(reason = "ATTEMPT_CANCELLED", announce = true) {
    const attempt = memory.sealedAttempt;
    if (memory.busy || memory.unresolvedWrite) return false;
    memory.sealedAttempt = null;
    memory.ticketRetained = false;
    const panel = byId("sealed-attempt-panel");
    if (panel) panel.hidden = true;
    const ticket = byId("recovery-ticket");
    const proof = byId("ticket-copy-proof");
    if (ticket) ticket.value = "";
    if (proof) proof.value = "";
    updateControls();
    if (attempt) {
      if (announce) {
        setState(reason, "Неподанный attempt уничтожен. Любая замена получит новый operation UUID и ticket.", "attention");
      }
      emit("studio:lifecycle-attempt-invalidated", {
        reason,
        operationKind: attempt.operationKind,
        operationId: attempt.operationId,
      });
    }
    return Boolean(attempt);
  }

  async function previewInitial() {
    if (
      memory.busy ||
      memory.sealedAttempt ||
      memory.unresolvedWrite ||
      memory.app.dataset.canPreview !== "true" ||
      memory.definition?.identity.publication_status !== "DRAFT" ||
      memory.readiness?.candidate_kind !== "INITIAL" ||
      memory.readiness?.required_next_action !== "PREVIEW_OR_INITIAL_PUBLISH"
    ) return;
    const token = csrfToken();
    if (!token) {
      setState("CSRF_TOKEN_UNAVAILABLE", "Обновите аутентифицированную страницу; preview не выполнен.", "error");
      return;
    }
    const body = `{"manifest":${canonicalLosslessJSON(memory.manifestSyntax)}}`;
    memory.busy = true;
    updateControls();
    try {
      const response = await fetch(memory.app.dataset.previewUrl, {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
        headers: {
          "Content-Type": JSON_CONTENT_TYPE,
          "X-CSRFToken": token,
        },
        body,
      });
      const parsed = await responseDocument(response);
      const reportCore = { ...parsed.value };
      delete reportCore.validation_report_sha256;
      if (
        response.status !== 200 ||
        parsed.text !== `${stableJSON(parsed.value)}\n` ||
        parsed.value?.contract !== "PROJECT_DEFINITION_MANIFEST_VALIDATION_V1" ||
        parsed.value?.contract_version !== "1.0.0" ||
        String(parsed.value?.definition_id || "").toLowerCase() !== memory.definition.identity.definition_id ||
        String(parsed.value?.project_id || "").toLowerCase() !== memory.definition.identity.project_id ||
        parsed.value?.base_manifest_sha256 !== memory.definition.identity.manifest_hash ||
        parsed.value?.request_sha256 !== (await sha256Text(body)) ||
        parsed.value?.request_byte_length !== utf8Length(body) ||
        parsed.value?.candidate_sha256 !== memory.definition.identity.manifest_hash ||
        parsed.value?.manifest_sha256 !== memory.definition.identity.manifest_hash ||
        typeof parsed.value?.valid !== "boolean" ||
        !Array.isArray(parsed.value?.diagnostics) ||
        !SHA256_PATTERN.test(String(parsed.value?.validation_report_sha256 || "")) ||
        parsed.value.validation_report_sha256 !== (await sha256Text(stableJSON(reportCore))) ||
        response.headers.get("ETag") !== `"${await sha256Text(parsed.text)}"` ||
        response.headers.get("Content-Length") !== String(utf8Length(parsed.text)) ||
        response.headers.get("Cache-Control") !== "no-store" ||
        response.headers.get("X-Content-Type-Options") !== "nosniff"
      ) throw new TypeError("FD01 preview identity mismatch.");
      setText(
        "preview-result",
        parsed.value.valid
          ? `VALID · report ${parsed.value.validation_report_sha256}`
          : `INVALID · report ${parsed.value.validation_report_sha256}`,
      );
      setState(
        parsed.value.valid ? "VALIDATION_PREVIEW_VALID" : "VALIDATION_PREVIEW_INVALID",
        "FD01 вернул канонический отчёт без изменения жизненного цикла.",
        parsed.value.valid ? "success" : "attention",
      );
      emit("studio:lifecycle-preview-complete", {
        definitionId: memory.definition.identity.definition_id,
        manifestHash: memory.definition.identity.manifest_hash,
        valid: parsed.value.valid,
        status: response.status,
      });
    } catch (_error) {
      setText("preview-result", "Preview не прошёл точную identity/hash-проверку.");
      setState("VALIDATION_PREVIEW_FAILED", "FD01 preview не принят; lifecycle POST не выполнялся.", "error");
    } finally {
      memory.busy = false;
      updateControls();
    }
  }

  async function verifyValidationReceipt(response, parsed, attempt) {
    const receipt = parsed.value?.write_receipt;
    const receiptSyntax = objectMember(parsed.syntax, "write_receipt");
    const receiptHeader = response.headers.get("X-Foundation-Receipt-SHA256") || "";
    const replayHeader = response.headers.get("X-Foundation-Operation-Replayed");
    const request = receipt?.request;
    const before = receipt?.before_definition;
    const after = receipt?.after_definition;
    const validation = receipt?.validation;
    const replayed = replayHeader === "true";
    const bareIfMatch = attempt.ifMatch.slice(1, -1);
    const receiptSha = receiptSyntax ? await sha256Text(canonicalLosslessJSON(receiptSyntax)) : "";
    const validationSyntax = receiptSyntax ? objectMember(receiptSyntax, "validation") : null;
    const validationSha = validationSyntax
      ? await sha256Text(canonicalLosslessJSON(validationSyntax))
      : "";
    const freshPayload = !replayed;
    const payloadShapeValid = freshPayload
      ? exactKeys(parsed.value, FRESH_VALIDATION_PAYLOAD_KEYS)
      : exactKeys(parsed.value, ["code", "write_receipt"]);
    const expectedRequestSha = exactHumanActor(receipt?.actor_identifier)
      ? await sha256Text(stableJSON({
        contract: "FOUNDATION_HUMAN_WRITE_REQUEST_IDENTITY_V1",
        operation_id: attempt.operationId,
        operation: "VALIDATE_DEFINITION",
        method: "POST",
        normalized_route: attempt.route,
        actor_identifier: receipt.actor_identifier,
        project_id: attempt.projectId,
        source_definition_id: null,
        target_definition_id: attempt.definitionId,
        normalized_content_type: JSON_CONTENT_TYPE,
        raw_input_sha256: attempt.bodySha256,
        raw_input_byte_length: attempt.bodyByteLength,
        if_match: bareIfMatch,
      }))
      : "";
    if (
      !receipt ||
      !receiptSyntax ||
      !exactKeys(receipt, HUMAN_RECEIPT_KEYS) ||
      !exactKeys(request, HUMAN_REQUEST_KEYS) ||
      !exactKeys(before, DEFINITION_RECEIPT_KEYS) ||
      !exactKeys(after, DEFINITION_RECEIPT_KEYS) ||
      !payloadShapeValid ||
      receipt.contract !== HUMAN_RECEIPT_CONTRACT ||
      receipt.version !== "1.0.0" ||
      receipt.operation !== "VALIDATE_DEFINITION" ||
      receipt.operation_id !== attempt.operationId ||
      receipt.audit_event_id !== attempt.operationId ||
      receipt.audit_action !== "VALIDATE" ||
      receipt.actor_type !== "HUMAN" ||
      !exactHumanActor(receipt.actor_identifier) ||
      receipt.project_id !== attempt.projectId ||
      receipt.source_definition !== null ||
      receipt.bootstrap_result !== null ||
      receipt.original_http_status !== 200 ||
      !exactTimestamp(receipt.occurred_at) ||
      request?.contract !== "FOUNDATION_HUMAN_WRITE_REQUEST_IDENTITY_V1" ||
      request?.sha256 !== expectedRequestSha ||
      request?.raw_input_sha256 !== attempt.bodySha256 ||
      request?.raw_input_byte_length !== attempt.bodyByteLength ||
      request?.if_match !== bareIfMatch ||
      before?.contract !== "FOUNDATION_DEFINITION_IDENTITY_V1" ||
      before?.id !== attempt.definitionId ||
      before?.project_id !== attempt.projectId ||
      before?.publication_status !== "DRAFT" ||
      before?.manifest_hash !== bareIfMatch ||
      before?.validated_at !== null ||
      before?.validated_by !== null ||
      before?.validation_result_sha256 !== null ||
      after?.contract !== "FOUNDATION_DEFINITION_IDENTITY_V1" ||
      after?.id !== attempt.definitionId ||
      after?.project_id !== attempt.projectId ||
      after?.manifest_hash !== bareIfMatch ||
      after?.publication_status !== "VALIDATED" ||
      !exactTimestamp(after?.validated_at) ||
      !exactHumanActor(after?.validated_by) ||
      after.validated_by !== receipt.actor_identifier ||
      after.validated_at !== receipt.occurred_at ||
      !exactBoundedText(after?.code, 128) ||
      !exactBoundedText(after?.version, 64) ||
      !exactBoundedText(after?.schema_version, 64) ||
      !exactBoundedText(after?.semantic_version, 64) ||
      !exactBoundedText(after?.construct_version, 64) ||
      !exactKeys(validation, PERSISTED_VALIDATION_KEYS) ||
      validation.contract !== MANIFEST_VALIDATION_CONTRACT ||
      validation.schema_id !== MANIFEST_SCHEMA_ID ||
      validation.schema_version !== "1.0.0" ||
      validation.valid !== true ||
      validation.manifest_sha256 !== bareIfMatch ||
      !Array.isArray(validation.diagnostics) ||
      !validation.diagnostics.every((item) => (
        exactKeys(item, PERSISTED_DIAGNOSTIC_KEYS) &&
        exactBoundedText(item.level, 64) &&
        exactBoundedText(item.code, 128) &&
        typeof item.path === "string" &&
        utf8Length(item.path) <= 4096 &&
        !containsLoneUnicodeSurrogate(item.path) &&
        exactBoundedText(item.message, 4096)
      )) ||
      validation.diagnostics.length !== 0 ||
      after.validation_result_sha256 !== validationSha ||
      before.code !== after.code ||
      before.version !== after.version ||
      before.schema_version !== after.schema_version ||
      before.semantic_version !== after.semantic_version ||
      before.construct_version !== after.construct_version ||
      before.supersedes_id !== after.supersedes_id ||
      (before.supersedes_id !== null && !UUID_PATTERN.test(before.supersedes_id)) ||
      !["true", "false"].includes(String(replayHeader)) ||
      replayHeader !== String(replayed) ||
      !SHA256_PATTERN.test(receiptHeader) ||
      receiptHeader !== receiptSha ||
      response.headers.get("ETag") !== attempt.ifMatch ||
      (response.headers.get("Content-Type") || "").split(";", 1)[0] !== JSON_CONTENT_TYPE ||
      response.status !== 200 ||
      (replayed && parsed.value?.code !== "WRITE_OPERATION_RECONCILED") ||
      (
        freshPayload && (
          parsed.value.id !== attempt.definitionId ||
          parsed.value.project_id !== attempt.projectId ||
          parsed.value.publication_status !== "VALIDATED" ||
          parsed.value.manifest_hash !== bareIfMatch ||
          parsed.value.code !== after.code ||
          parsed.value.version !== after.version ||
          parsed.value.schema_version !== after.schema_version ||
          parsed.value.semantic_version !== after.semantic_version ||
          parsed.value.construct_version !== after.construct_version ||
          parsed.value.supersedes_id !== after.supersedes_id ||
          !objectMember(parsed.syntax, "manifest") ||
          (await sha256Text(canonicalLosslessJSON(objectMember(parsed.syntax, "manifest")))) !== bareIfMatch
        )
      )
    ) throw new TypeError("FD05 receipt identity mismatch.");
    return { receipt, receiptSha, replayed };
  }

  async function verifyPublicationReceipt(response, parsed, attempt) {
    const receipt = parsed.value;
    const definition = receipt?.definition;
    const definitionSyntax = objectMember(parsed.syntax, "definition");
    const manifestSyntax = definitionSyntax ? objectMember(definitionSyntax, "manifest") : null;
    const resultSha = parsed.syntax
      ? await sha256Text(canonicalLosslessJSON(parsed.syntax, new Set(["result_sha256"])))
      : "";
    const expectedKind = attempt.operationKind === "PUBLISH_INITIAL" ? "INITIAL" : "SUCCESSOR";
    const replayHeader = response.headers.get("Idempotency-Replayed");
    const replayed = replayHeader === "true";
    const bareIfMatch = attempt.ifMatch.slice(1, -1);
    const requestPayload = JSON.parse(attempt.body);
    const validation = receipt?.validation_result;
    const workspace = requestPayload?.workspace;
    const expectedBindingIds = Array.isArray(definition?.manifest?.help_bindings)
      ? definition.manifest.help_bindings.map((binding) => binding?.id)
      : null;
    const requestShapeValid = expectedKind === "INITIAL"
      ? (
        exactKeys(requestPayload, ["locale", "workspace"]) &&
        exactKeys(workspace, ["code", "id", "is_default", "metadata", "name", "version"]) &&
        UUID_PATTERN.test(String(workspace.id || "")) &&
        exactBoundedText(workspace.code, 255) &&
        exactBoundedText(workspace.version, 64) &&
        exactBoundedText(workspace.name, 255) &&
        workspace.is_default === true &&
        workspace.metadata &&
        typeof workspace.metadata === "object" &&
        !Array.isArray(workspace.metadata)
      )
      : exactKeys(requestPayload, ["locale"]);
    const expectedRequestSha = exactHumanActor(receipt?.actor_identifier) && requestShapeValid
      ? await sha256Text(stableJSON({
        contract: PUBLICATION_REQUEST_CONTRACT,
        version: "1.0.0",
        operation_kind: expectedKind,
        project_id: attempt.projectId,
        definition_id: attempt.definitionId,
        expected_manifest_hash: bareIfMatch,
        actor_identifier: receipt.actor_identifier,
        locale: requestPayload.locale,
        initial_workspace: expectedKind === "INITIAL" ? workspace : null,
      }))
      : "";
    const receiptVary = normalizedVary(response);
    const initialShapeValid = expectedKind === "INITIAL"
      ? (
        UUID_PATTERN.test(String(receipt?.initial_workspace_id || "")) &&
        receipt.initial_workspace_id === requestPayload.workspace?.id &&
        receipt.initial_workspace_definition_id === attempt.definitionId &&
        receipt.initial_workspace_definition_manifest_hash === bareIfMatch &&
        Array.isArray(expectedBindingIds) &&
        expectedBindingIds.every((item) => UUID_PATTERN.test(String(item || ""))) &&
        stableJSON(receipt.help_binding_ids) === stableJSON(expectedBindingIds)
      )
      : (
        receipt?.initial_workspace_id === null &&
        receipt?.initial_workspace_definition_id === null &&
        receipt?.initial_workspace_definition_manifest_hash === null &&
        Array.isArray(receipt?.help_binding_ids) &&
        receipt.help_binding_ids.length === 0
      );
    if (
      !exactKeys(receipt, PUBLICATION_RECEIPT_KEYS) ||
      !exactKeys(definition, PUBLICATION_DEFINITION_KEYS) ||
      receipt?.contract !== PUBLICATION_RESULT_CONTRACT ||
      parsed.text !== `${canonicalLosslessJSON(parsed.syntax)}\n` ||
      receipt?.contract_version !== "1.0.0" ||
      receipt?.operation_id !== attempt.operationId ||
      receipt?.operation_kind !== expectedKind ||
      receipt?.project_id !== attempt.projectId ||
      definition?.id !== attempt.definitionId ||
      definition?.project_id !== attempt.projectId ||
      definition?.code !== attempt.definitionCode ||
      definition?.version !== attempt.definitionVersion ||
      definition?.schema_version !== attempt.schemaVersion ||
      definition?.semantic_version !== attempt.semanticVersion ||
      definition?.construct_version !== attempt.constructVersion ||
      definition?.manifest_hash !== bareIfMatch ||
      definition?.publication_status !== "PUBLISHED" ||
      !exactBoundedText(definition?.code, 128) ||
      !exactBoundedText(definition?.version, 64) ||
      !exactBoundedText(definition?.schema_version, 64) ||
      !exactBoundedText(definition?.semantic_version, 64) ||
      !exactBoundedText(definition?.construct_version, 64) ||
      definition?.supersedes_id !== attempt.supersedesId ||
      (expectedKind === "INITIAL"
        ? definition?.supersedes_id !== null
        : !UUID_PATTERN.test(String(definition?.supersedes_id || ""))) ||
      !manifestSyntax ||
      (await sha256Text(canonicalLosslessJSON(manifestSyntax))) !== bareIfMatch ||
      !requestShapeValid ||
      receipt?.operation_request_sha256 !== expectedRequestSha ||
      !SHA256_PATTERN.test(String(receipt?.result_sha256 || "")) ||
      receipt.result_sha256 !== resultSha ||
      !UUID_PATTERN.test(String(receipt?.publication_id || "")) ||
      !exactHumanActor(receipt?.actor_identifier) ||
      !exactTimestamp(receipt?.published_at) ||
      receipt?.locale !== requestPayload.locale ||
      !LOCALE_PATTERN.test(String(receipt?.locale || "")) ||
      !exactKeys(validation, PERSISTED_VALIDATION_KEYS) ||
      validation.contract !== MANIFEST_VALIDATION_CONTRACT ||
      validation.schema_id !== MANIFEST_SCHEMA_ID ||
      validation.schema_version !== "1.0.0" ||
      validation.manifest_sha256 !== bareIfMatch ||
      validation.valid !== true ||
      !Array.isArray(validation.diagnostics) ||
      !validation.diagnostics.every((item) => (
        exactKeys(item, PERSISTED_DIAGNOSTIC_KEYS) &&
        exactBoundedText(item.level, 64) &&
        exactBoundedText(item.code, 128) &&
        typeof item.path === "string" &&
        utf8Length(item.path) <= 4096 &&
        !containsLoneUnicodeSurrogate(item.path) &&
        exactBoundedText(item.message, 4096)
      )) ||
      validation.diagnostics.length !== 0 ||
      !initialShapeValid ||
      response.headers.get("ETag") !== `"${await sha256Text(parsed.text)}"` ||
      response.headers.get("Location") !==
        `/api/foundation/projects/${attempt.projectId}/publication-results/${receipt.publication_id}/` ||
      response.headers.get("Cache-Control") !== "no-store" ||
      !["authorization|cookie", "accept|authorization|cookie"].includes(receiptVary) ||
      (response.headers.get("Content-Type") || "").split(";", 1)[0] !== JSON_CONTENT_TYPE ||
      !["true", "false"].includes(String(replayHeader)) ||
      replayHeader !== String(replayed) ||
      (replayed ? response.status !== 200 : response.status !== 201)
    ) throw new TypeError("FD06 receipt identity mismatch.");
    return { receipt, receiptSha: receipt.result_sha256, replayed };
  }

  function renderVerifiedResult(kind, receipt, sha, replayed) {
    const panel = byId("operation-result");
    if (panel) panel.hidden = false;
    setText(
      "operation-result-summary",
      `${kind} · ${replayed ? "RECONCILED" : "COMMITTED"} · SHA-256 ${sha}`,
    );
    setText("operation-result-json", `${stableJSON(receipt)}\n`);
    memory.lastReceipt = receipt;
  }

  function clearResolvedAttempt({ consumeInputs = false } = {}) {
    memory.sealedAttempt = null;
    memory.unresolvedWrite = null;
    memory.ticketRetained = false;
    if (consumeInputs) memory.dirtyInputs = false;
    const sealed = byId("sealed-attempt-panel");
    const unknown = byId("unknown-outcome-panel");
    if (sealed) sealed.hidden = true;
    if (unknown) unknown.hidden = true;
    updateControls();
  }

  async function refreshAfterDefinitiveResult(successCode, successMessage) {
    try {
      await readFreshSnapshot();
      setState(successCode, successMessage, "success");
      return true;
    } catch (_error) {
      memory.actionKind = "NONE";
      updateControls();
      setState(
        `${successCode}_SNAPSHOT_UNAVAILABLE`,
        `${successMessage} Последующий FD03/FD07 readback недоступен; новые действия закрыты.`,
        "attention",
      );
      return false;
    }
  }

  function showUnknownOutcome(attempt) {
    memory.unresolvedWrite = attempt;
    const panel = byId("unknown-outcome-panel");
    const replay = byId("replay-validation-attempt");
    const recover = byId("recover-publication-operation");
    if (panel) panel.hidden = false;
    if (attempt.operationKind === "VALIDATE_DEFINITION") {
      setText(
        "unknown-outcome-message",
        "Исход FD05 неизвестен. Разрешён только явный повтор тех же route, UUID, If-Match и UTF-8 {}.",
      );
      if (replay) {
        replay.hidden = false;
        replay.disabled = false;
      }
      if (recover) {
        recover.hidden = true;
        recover.disabled = true;
      }
    } else {
      setText(
        "unknown-outcome-message",
        "Исход FD06 неизвестен. Повтор POST запрещён; доступен только exact operation-recovery GET.",
      );
      if (replay) {
        replay.hidden = true;
        replay.disabled = true;
      }
      if (recover) {
        recover.hidden = false;
        recover.disabled = false;
      }
    }
    setState("UNKNOWN_TRANSPORT_OUTCOME", "Автоматическая мутация или замена operation key запрещена.", "attention");
    updateControls();
    emit("studio:lifecycle-unknown-outcome", {
      operationKind: attempt.operationKind,
      operationId: attempt.operationId,
    });
  }

  function isAmbiguousWriteResponse(response) {
    return [408, 425, 429].includes(response.status) || response.status >= 500;
  }

  async function handleKnownFailure(response, attempt) {
    let code = `HTTP_${response.status}`;
    try {
      const body = await response.json();
      if (typeof body?.code === "string") code = body.code;
    } catch (_error) {
      // The bounded HTTP status remains sufficient for a fail-closed display.
    }
    clearResolvedAttempt();
    setState(code, "Foundation вернул определённый отказ; attempt не повторяется автоматически.", "error");
    emit("studio:lifecycle-operation-failed", {
      operationKind: attempt.operationKind,
      operationId: attempt.operationId,
      status: response.status,
      code,
    });
  }

  async function performSealedAttempt(attempt, { reconciliation = false } = {}) {
    if (
      memory.busy ||
      memory.sealedAttempt !== attempt ||
      (reconciliation ? memory.unresolvedWrite !== attempt : memory.unresolvedWrite) ||
      (!reconciliation && !memory.ticketRetained)
    ) return;
    memory.busy = true;
    updateControls();
    let response;
    let headers;
    try {
      await readCurrentServerAuthority();
      const currentRoute = routeForAction(attempt.operationKind);
      const expectedRoute = expectedRouteForAction(attempt.operationKind, attempt.definitionId);
      const token = csrfToken();
      if (!token || !currentRoute || currentRoute !== attempt.route || currentRoute !== expectedRoute) {
        throw new TypeError("Fresh transport authority is unavailable or changed.");
      }
      headers = Object.freeze({
        "Content-Type": JSON_CONTENT_TYPE,
        "X-CSRFToken": token,
        "If-Match": attempt.ifMatch,
        "Idempotency-Key": attempt.operationId,
      });
    } catch (_error) {
      memory.busy = false;
      setState(
        "SEALED_ATTEMPT_TRANSPORT_AUTHORITY_CHANGED",
        "Текущие presentation authority, route или CSRF изменились; POST не выполнен.",
        "error",
      );
      updateControls();
      return;
    }
    try {
      response = await fetch(attempt.route, {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
        headers,
        body: attempt.body,
      });
    } catch (_error) {
      memory.busy = false;
      showUnknownOutcome(attempt);
      return;
    }
    if (isAmbiguousWriteResponse(response)) {
      memory.busy = false;
      showUnknownOutcome(attempt);
      return;
    }
    if (response.ok && response.status !== 200 && response.status !== 201) {
      memory.busy = false;
      showUnknownOutcome(attempt);
      return;
    }
    if (response.status !== 200 && response.status !== 201) {
      memory.busy = false;
      await handleKnownFailure(response, attempt);
      return;
    }
    try {
      const parsed = await responseDocument(response);
      if (attempt.operationKind === "VALIDATE_DEFINITION") {
        const verified = await verifyValidationReceipt(response, parsed, attempt);
        renderVerifiedResult("VALIDATE_DEFINITION", verified.receipt, verified.receiptSha, verified.replayed);
        clearResolvedAttempt({ consumeInputs: true });
        await refreshAfterDefinitiveResult(
          verified.replayed ? "VALIDATION_RECONCILED" : "VALIDATION_COMMITTED",
          "Квитанция FD05 проверена; FD03 и FD07 перечитаны. Публикация не выполнялась автоматически.",
        );
        emit("studio:lifecycle-validation-complete", {
          operationId: attempt.operationId,
          receiptSha256: verified.receiptSha,
          replayed: verified.replayed,
          status: response.status,
        });
      } else {
        const verified = await verifyPublicationReceipt(response, parsed, attempt);
        renderVerifiedResult(attempt.operationKind, verified.receipt, verified.receiptSha, verified.replayed);
        clearResolvedAttempt({ consumeInputs: true });
        await refreshAfterDefinitiveResult(
          verified.replayed ? "PUBLICATION_RECONCILED" : "PUBLICATION_COMMITTED",
          "Квитанция FD06 проверена; сохранённая lifecycle-истина перечитана.",
        );
        emit("studio:lifecycle-publication-complete", {
          operationKind: attempt.operationKind,
          operationId: attempt.operationId,
          publicationId: verified.receipt.publication_id,
          resultSha256: verified.receiptSha,
          replayed: verified.replayed,
          status: response.status,
        });
      }
    } catch (_error) {
      memory.busy = false;
      showUnknownOutcome(attempt);
      return;
    } finally {
      memory.busy = false;
      updateControls();
    }
  }

  async function recoverPublication() {
    const attempt = memory.unresolvedWrite;
    if (
      memory.busy ||
      !attempt ||
      attempt.operationKind === "VALIDATE_DEFINITION" ||
      memory.sealedAttempt !== attempt
    ) return;
    const template = memory.app.dataset.publicationOperationTemplate || "";
    const route = template
      .replace("__PROJECT_ID__", attempt.projectId)
      .replace("__OPERATION_ID__", attempt.operationId);
    if (
      !route.startsWith("/api/foundation/projects/") ||
      route.includes("__") ||
      route.includes("?")
    ) {
      setState("PUBLICATION_RECOVERY_ROUTE_INVALID", "Recovery GET не выполнен.", "error");
      return;
    }
    memory.busy = true;
    updateControls();
    try {
      const response = await fetch(route, {
        method: "GET",
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
        headers: { Accept: "application/json" },
      });
      const recoveryVary = normalizedVary(response);
      if (
        response.headers.get("Cache-Control") !== "no-store" ||
        !["authorization|cookie", "accept|authorization|cookie"].includes(recoveryVary)
      ) throw new TypeError("Recovery cache boundary mismatch.");
      if (response.status === 404) {
        setState(
          "PUBLICATION_RECOVERY_NOT_VISIBLE",
          "404 означает только отсутствие видимого результата в этой области; факт commit остаётся неизвестным.",
          "attention",
        );
        emit("studio:lifecycle-publication-recovery-not-visible", {
          operationId: attempt.operationId,
          status: 404,
        });
        return;
      }
      if (response.status !== 200) {
        setState(`PUBLICATION_RECOVERY_HTTP_${response.status}`, "Recovery не разрешил неопределённый исход.", "error");
        return;
      }
      const parsed = await responseDocument(response);
      const verified = await verifyPublicationReceipt(response, parsed, attempt);
      if (!verified.replayed) throw new TypeError("Recovery response is not marked replayed.");
      renderVerifiedResult(attempt.operationKind, verified.receipt, verified.receiptSha, true);
      clearResolvedAttempt({ consumeInputs: true });
      await refreshAfterDefinitiveResult(
        "PUBLICATION_RECOVERED",
        "Exact FD06 operation GET вернул проверенную неизменяемую квитанцию.",
      );
      emit("studio:lifecycle-publication-recovery-complete", {
        operationKind: attempt.operationKind,
        operationId: attempt.operationId,
        publicationId: verified.receipt.publication_id,
        resultSha256: verified.receiptSha,
      });
    } catch (_error) {
      setState("PUBLICATION_RECOVERY_UNVERIFIED", "Recovery-ответ не прошёл identity/hash-проверку; исход остаётся неизвестным.", "error");
    } finally {
      memory.busy = false;
      updateControls();
    }
  }

  async function verifyImportedValidationTicket(text) {
    if (
      typeof text !== "string" ||
      !text.endsWith("\n") ||
      text.endsWith("\n\n") ||
      utf8Length(text) > 16_384
    ) throw new TypeError("Ticket representation is invalid.");
    const parsed = parseLosslessJSON(text);
    const ticket = parsed.value;
    const core = { ...ticket };
    delete core.ticket_sha256;
    if (
      !exactKeys(ticket, TICKET_KEYS) ||
      ticket.contract !== HUMAN_TICKET_CONTRACT ||
      ticket.contract_version !== "1.0.0" ||
      ticket.operation_kind !== "VALIDATE_DEFINITION" ||
      !UUID_V4_PATTERN.test(String(ticket.operation_id || "")) ||
      String(ticket.project_id || "").toLowerCase() !== ticket.project_id ||
      !UUID_PATTERN.test(ticket.project_id) ||
      String(ticket.definition_id || "").toLowerCase() !== ticket.definition_id ||
      !UUID_PATTERN.test(ticket.definition_id) ||
      ticket.definition_id !== memory.app.dataset.definitionId.toLowerCase() ||
      ticket.method !== "POST" ||
      ticket.route !== memory.app.dataset.validateUrl ||
      ticket.route !== `/api/foundation/definitions/${ticket.definition_id}/validate/` ||
      !/^"[0-9a-f]{64}"$/.test(String(ticket.if_match || "")) ||
      ticket.content_type !== JSON_CONTENT_TYPE ||
      ticket.body_utf8 !== "{}" ||
      ticket.body_sha256 !== (await sha256Text("{}")) ||
      ticket.body_byte_length !== 2 ||
      !SHA256_PATTERN.test(String(ticket.ticket_sha256 || "")) ||
      ticket.ticket_sha256 !== (await sha256Text(stableJSON(core))) ||
      text !== `${stableJSON(ticket)}\n`
    ) throw new TypeError("Ticket identity is invalid.");
    return ticket;
  }

  async function readCurrentServerAuthority() {
    const response = await fetch(window.location.pathname, {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
      redirect: "error",
      headers: { Accept: "text/html" },
    });
    if (response.status !== 200) throw new TypeError("Current Studio authority is unavailable.");
    const html = await response.text();
    const documentCopy = new DOMParser().parseFromString(html, "text/html");
    const app = documentCopy.getElementById("lifecycle-publication-app");
    if (
      !app ||
      app.dataset.authenticated !== "true" ||
      app.dataset.canRead !== "true" ||
      app.dataset.canValidate !== "true" ||
      app.dataset.definitionId.toLowerCase() !== memory.app.dataset.definitionId.toLowerCase() ||
      app.dataset.openUrl !== memory.app.dataset.openUrl ||
      app.dataset.readinessUrl !== memory.app.dataset.readinessUrl ||
      app.dataset.validateUrl !== memory.app.dataset.validateUrl ||
      app.dataset.publishInitialUrl !== memory.app.dataset.publishInitialUrl ||
      app.dataset.publishSuccessorUrl !== memory.app.dataset.publishSuccessorUrl ||
      app.dataset.validateUrl !== expectedRouteForAction("VALIDATE_DEFINITION", app.dataset.definitionId) ||
      app.dataset.publishInitialUrl !== expectedRouteForAction("PUBLISH_INITIAL", app.dataset.definitionId) ||
      app.dataset.publishSuccessorUrl !== expectedRouteForAction("PUBLISH_SUCCESSOR", app.dataset.definitionId)
    ) throw new TypeError("Current Studio presentation authority is denied or incoherent.");
    memory.app.dataset.canRead = app.dataset.canRead;
    memory.app.dataset.canPreview = app.dataset.canPreview;
    memory.app.dataset.canValidate = app.dataset.canValidate;
    memory.app.dataset.canPublish = app.dataset.canPublish;
  }

  async function importValidationTicket() {
    if (memory.busy || memory.sealedAttempt || memory.unresolvedWrite) return;
    memory.busy = true;
    updateControls();
    try {
      const ticket = await verifyImportedValidationTicket(byId("import-recovery-ticket")?.value || "");
      await readCurrentServerAuthority();
      await readFreshSnapshot();
      if (
        memory.definition.identity.project_id !== ticket.project_id ||
        memory.definition.identity.definition_id !== ticket.definition_id ||
        memory.definition.identity.manifest_hash !== ticket.if_match.slice(1, -1) ||
        memory.definition.identity.supersedes_id === null
      ) throw new TypeError("Current Foundation identity no longer matches the ticket.");
      const attempt = Object.freeze({
        operationKind: ticket.operation_kind,
        operationId: ticket.operation_id,
        projectId: ticket.project_id,
        definitionId: ticket.definition_id,
        route: ticket.route,
        ifMatch: ticket.if_match,
        body: ticket.body_utf8,
        bodySha256: ticket.body_sha256,
        bodyByteLength: ticket.body_byte_length,
        readinessSha256: memory.readiness.readiness_sha256,
        ticket: Object.freeze({ ...ticket }),
        ticketText: `${stableJSON(ticket)}\n`,
        imported: true,
      });
      memory.sealedAttempt = attempt;
      memory.unresolvedWrite = attempt;
      memory.ticketRetained = true;
      renderAttempt(attempt);
      showUnknownOutcome(attempt);
      setState(
        "VALIDATION_TICKET_RESTORED",
        "Текущие FD03, FD07 и presentation authority перечитаны. Доступен только явный same-request FD05 replay.",
        "attention",
      );
      emit("studio:lifecycle-validation-ticket-imported", {
        operationId: attempt.operationId,
        projectId: attempt.projectId,
        definitionId: attempt.definitionId,
        ticketSha256: attempt.ticket.ticket_sha256,
        persistedStatus: memory.definition.identity.publication_status,
        readinessSha256: memory.readiness.readiness_sha256,
      });
    } catch (_error) {
      memory.sealedAttempt = null;
      memory.unresolvedWrite = null;
      memory.ticketRetained = false;
      setState(
        "VALIDATION_TICKET_REJECTED",
        "Ticket, текущая identity/topology или presentation authority не совпали; POST не выполнен.",
        "error",
      );
    } finally {
      memory.busy = false;
      updateControls();
    }
  }

  async function manualRefresh() {
    if (memory.busy || memory.sealedAttempt || memory.unresolvedWrite) return;
    memory.busy = true;
    updateControls();
    try {
      await readFreshSnapshot();
      setState(
        memory.actionKind === "NONE" ? "LIFECYCLE_READ_ONLY" : "LIFECYCLE_READY",
        memory.actionKind === "NONE"
          ? "Сохранённое состояние показано правдиво; доступного C2A-действия нет."
          : "Свежие FD03 и FD07 совпали. Любой attempt потребует ещё одного readback.",
        memory.actionKind === "NONE" ? "attention" : "success",
      );
      emit("studio:lifecycle-ready", {
        definitionId: memory.definition.identity.definition_id,
        projectId: memory.definition.identity.project_id,
        manifestHash: memory.definition.identity.manifest_hash,
        publicationStatus: memory.definition.identity.publication_status,
        isCurrent: memory.definition.identity.is_current,
        candidateKind: memory.readiness.candidate_kind,
        requiredNextAction: memory.readiness.required_next_action,
        actionKind: memory.actionKind,
        readinessSha256: memory.readiness.readiness_sha256,
      });
    } catch (_error) {
      memory.definition = null;
      memory.definitionSyntax = null;
      memory.manifestSyntax = null;
      memory.readiness = null;
      memory.actionKind = "NONE";
      setText("lifecycle-project-id", "UNKNOWN_UNVERIFIED");
      setText("lifecycle-definition-id", memory.app.dataset.definitionId.toLowerCase());
      setText("lifecycle-manifest-hash", "UNKNOWN_UNVERIFIED");
      setText("lifecycle-publication-status", "UNKNOWN_UNVERIFIED");
      setText("lifecycle-is-current", "UNKNOWN_UNVERIFIED");
      setText("lifecycle-supersedes-id", "UNKNOWN_UNVERIFIED");
      setText("lifecycle-validated-at", "UNKNOWN_UNVERIFIED");
      setText("lifecycle-published-at", "UNKNOWN_UNVERIFIED");
      setText("readiness-candidate-kind", "NONE");
      setText("readiness-next-action", "NONE");
      setText("readiness-sha256", "UNKNOWN_UNVERIFIED");
      setText("readiness-publication-count", "UNKNOWN_UNVERIFIED");
      setText("readiness-workspace-count", "UNKNOWN_UNVERIFIED");
      setText("readiness-current-definition", "UNKNOWN_UNVERIFIED");
      setText("readiness-blockers", "FOUNDATION_SNAPSHOT_UNAVAILABLE");
      setState("FOUNDATION_SNAPSHOT_UNAVAILABLE", "FD03/FD07 не прошли свежую identity/hash-проверку; все действия закрыты.", "error");
    } finally {
      memory.busy = false;
      updateControls();
    }
  }

  function markInputsDirty() {
    memory.dirtyInputs = true;
    if (memory.sealedAttempt && !memory.unresolvedWrite && !memory.busy) {
      discardUnsentAttempt("ATTEMPT_INVALIDATED_BY_EDIT");
    }
  }

  function bindControls() {
    byId("refresh-lifecycle")?.addEventListener("click", manualRefresh);
    byId("preview-lifecycle")?.addEventListener("click", previewInitial);
    byId("prepare-lifecycle-attempt")?.addEventListener("click", prepareAttempt);
    byId("cancel-lifecycle-attempt")?.addEventListener("click", () => discardUnsentAttempt());
    byId("download-recovery-ticket")?.addEventListener("click", downloadTicket);
    byId("acknowledge-ticket-copy")?.addEventListener("click", acknowledgeExactCopy);
    byId("execute-sealed-attempt")?.addEventListener("click", () => {
      if (memory.sealedAttempt) performSealedAttempt(memory.sealedAttempt);
    });
    byId("replay-validation-attempt")?.addEventListener("click", () => {
      if (memory.unresolvedWrite?.operationKind === "VALIDATE_DEFINITION") {
        performSealedAttempt(memory.unresolvedWrite, { reconciliation: true });
      }
    });
    byId("recover-publication-operation")?.addEventListener("click", recoverPublication);
    byId("import-validation-ticket")?.addEventListener("click", importValidationTicket);
    document
      .querySelectorAll("#publication-inputs input, #publication-inputs textarea")
      .forEach((control) => control.addEventListener("input", markInputsDirty));
    window.addEventListener("beforeunload", (event) => {
      if (!memory.dirtyInputs && !memory.busy && !memory.sealedAttempt && !memory.unresolvedWrite) return;
      event.preventDefault();
      event.returnValue = "";
    });
  }

  async function initialise() {
    memory.app = byId("lifecycle-publication-app");
    if (!memory.app || memory.app.dataset.authenticated !== "true") return;
    bindControls();
    const workspaceId = byId("workspace-id");
    if (workspaceId && !workspaceId.value) workspaceId.value = randomUUIDv4();
    try {
      await verifyClaimContract();
      if (
        memory.app.dataset.canRead !== "true" ||
        !UUID_PATTERN.test(memory.app.dataset.definitionId.toLowerCase())
      ) throw new TypeError("Presentation identity is denied.");
      await manualRefresh();
    } catch (_error) {
      memory.actionKind = "NONE";
      setState(
        "LIFECYCLE_CLAIM_CONTRACT_MISMATCH",
        "Точный контракт ограничений не прошёл byte/hash-проверку; Foundation mutation не вызван.",
        "error",
      );
      document.querySelectorAll("button, input, textarea, select").forEach((control) => {
        control.disabled = true;
      });
    }
  }

  window.__productionStudioLifecycleContract = Object.freeze({
    version: "C2A_V1",
    claimContract: CLAIM_CONTRACT,
    readinessContract: READINESS_CONTRACT,
    recoveryTicketContract: HUMAN_TICKET_CONTRACT,
    storagePolicy: "NO_OPERATION_DATA_IN_PERSISTENT_BROWSER_STORAGE",
    events: Object.freeze([
      "studio:lifecycle-ready",
      "studio:lifecycle-preview-complete",
      "studio:lifecycle-attempt-prepared",
      "studio:lifecycle-ticket-retained",
      "studio:lifecycle-unknown-outcome",
      "studio:lifecycle-validation-ticket-imported",
      "studio:lifecycle-validation-complete",
      "studio:lifecycle-publication-complete",
      "studio:lifecycle-publication-recovery-complete",
    ]),
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialise, { once: true });
  } else {
    initialise();
  }
})();
