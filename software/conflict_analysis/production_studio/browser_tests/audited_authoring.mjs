import assert from "node:assert/strict";
import { inflateSync } from "node:zlib";

import { launchChromium } from "./cdp_client.mjs";


const requiredEnvironment = (name) => {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
};

const baseUrl = requiredEnvironment("STUDIO_BASE_URL").replace(/\/$/, "");
const definitionId = requiredEnvironment("STUDIO_DEFINITION_ID").toLowerCase();
const sessionCookieName = requiredEnvironment("STUDIO_SESSION_COOKIE_NAME");
const sessionCookieValue = requiredEnvironment("STUDIO_SESSION_COOKIE_VALUE");
const expectedClaimSha256 = requiredEnvironment("STUDIO_EXPECTED_CLAIM_SHA256");
const expectedManifestSha256 = requiredEnvironment("STUDIO_EXPECTED_MANIFEST_SHA256");
const expectedHelpSha256 = requiredEnvironment("STUDIO_EXPECTED_HELP_SHA256");
const remoteSaveBody = inflateSync(
  Buffer.from(requiredEnvironment("STUDIO_REMOTE_SAVE_BODY_ZLIB_B64"), "base64"),
).toString("utf8");
const losslessBigintKey = requiredEnvironment("STUDIO_LOSSLESS_BIGINT_KEY");
const losslessExponentKey = requiredEnvironment("STUDIO_LOSSLESS_EXPONENT_KEY");
const losslessExponentToken = requiredEnvironment("STUDIO_LOSSLESS_EXPONENT_TOKEN");
const timeoutMs = Number(process.env.STUDIO_CDP_TIMEOUT_MS || "60000");
const definitionUrl = `${baseUrl}/studio/drafts/definitions/${definitionId}/`;
const openPath = `/api/foundation/definitions/${definitionId}/`;
const savePath = `${openPath}draft/`;
const previewPath = `${openPath}validation-preview/`;
const storageKey = "conflict-analysis-studio:audited-draft-layout:v1";
const eventNames = [
  "studio:authoring-ready",
  "studio:save-complete",
  "studio:preview-complete",
  "studio:typed-conflict",
];

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
const normalizedHeaders = (headers) => Object.fromEntries(
  Object.entries(headers || {}).map(([name, value]) => [name.toLowerCase(), String(value)]),
);

const browser = await launchChromium({ timeoutMs });
let client;
let sessionId;
const requests = [];
const responses = new Map();

try {
  client = browser.client;
  const { targetId } = await client.send("Target.createTarget", { url: "about:blank" });
  ({ sessionId } = await client.send("Target.attachToTarget", { targetId, flatten: true }));
  await Promise.all([
    client.send("Page.enable", {}, sessionId),
    client.send("Runtime.enable", {}, sessionId),
    client.send("Network.enable", { maxTotalBufferSize: 50_000_000 }, sessionId),
  ]);
  await client.send("Browser.setDownloadBehavior", { behavior: "deny" });
  await client.send(
    "Page.addScriptToEvaluateOnNewDocument",
    {
      source: `(() => {
        window.__studioContractEvents = [];
        for (const name of ${JSON.stringify(eventNames)}) {
          window.addEventListener(name, (event) => {
            let detail = {};
            try {
              detail = JSON.parse(JSON.stringify(event.detail || {}));
            } catch {
              detail = { serializationError: true };
            }
            window.__studioContractEvents.push({ name, detail });
          });
        }
      })();`,
    },
    sessionId,
  );

  client.on("Network.requestWillBeSent", (event, eventSessionId) => {
    if (eventSessionId !== sessionId || !/^https?:/.test(event.request.url)) return;
    requests.push({
      method: event.request.method,
      url: event.request.url,
      headers: normalizedHeaders(event.request.headers),
      postData: event.request.postData || null,
    });
  });
  client.on("Network.responseReceived", (event, eventSessionId) => {
    if (eventSessionId !== sessionId || !/^https?:/.test(event.response.url)) return;
    responses.set(event.requestId, {
      url: event.response.url,
      status: event.response.status,
      headers: normalizedHeaders(event.response.headers),
    });
  });

  const cookie = await client.send(
    "Network.setCookie",
    {
      name: sessionCookieName,
      value: sessionCookieValue,
      url: `${baseUrl}/`,
      httpOnly: true,
      sameSite: "Lax",
      secure: baseUrl.startsWith("https:"),
    },
    sessionId,
  );
  assert.equal(cookie.success, true, "pre-issued session cookie was not admitted");

  const clearEvents = () => client.evaluate(
    "window.__studioContractEvents.length = 0",
    sessionId,
  );
  const waitForEvent = async (name) => {
    await client.waitForExpression(
      `window.__studioContractEvents?.some((item) => item.name === ${JSON.stringify(name)})`,
      sessionId,
      timeoutMs,
    );
    return client.evaluate(
      `window.__studioContractEvents.filter((item) => item.name === ${JSON.stringify(name)}).at(-1).detail`,
      sessionId,
    );
  };
  const navigateAndWait = async ({ reload = false } = {}) => {
    let removeListener;
    const loaded = new Promise((resolve) => {
      removeListener = client.on("Page.loadEventFired", (_event, eventSessionId) => {
        if (eventSessionId !== sessionId) return;
        removeListener();
        resolve();
      });
    });
    if (reload) {
      await client.send("Page.reload", { ignoreCache: true }, sessionId);
    } else {
      await client.send("Page.navigate", { url: definitionUrl }, sessionId);
    }
    await loaded;
    return waitForEvent("studio:authoring-ready");
  };
  const inspectPage = () => client.evaluate(`(async () => {
    const app = document.querySelector("#audited-draft-app");
    const actorRoot = document.querySelector("#authoring-actors");
    const elementRoot = document.querySelector("#authoring-elements");
    const authoringWindow = document.querySelector("#authoring-window");
    const helpFrame = document.querySelector("#help-frame");
    const layoutRaw = localStorage.getItem(${JSON.stringify(storageKey)});
    return {
      definitionId: app?.dataset.definitionId,
      projectId: app?.dataset.projectId,
      manifestHash: app?.dataset.manifestHash,
      etag: app?.dataset.etag,
      actorCount: Number(actorRoot?.dataset.totalCount),
      elementCount: Number(elementRoot?.dataset.totalCount),
      activeRows: authoringWindow?.querySelectorAll("[data-authoring-row][data-item-id]").length || 0,
      totalDomNodes: document.getElementsByTagName("*").length,
      crossCells: document.querySelectorAll("[data-actor-id][data-element-id]").length,
      disabled: [
        "document-control",
        "chat-control",
        "scientific-control",
        "prediction-control",
        "recommendation-control",
      ].every((id) => document.querySelector("#" + id)?.disabled === true),
      boundaryVisible: Boolean(document.querySelector("#audited-draft-boundary-banner")),
      projectName: document.querySelector("#project-name")?.value,
      projectDescription: document.querySelector("#project-description")?.value,
      helpText:
        helpFrame?.getAttribute("srcdoc") ||
        helpFrame?.contentDocument?.body?.textContent ||
        "",
      helpSha256: helpFrame?.dataset.contentSha256 || "",
      layoutRaw,
      localStorageKeys: Object.keys(localStorage).sort(),
      sessionStorageLength: sessionStorage.length,
      indexedDbNames: typeof indexedDB.databases === "function"
        ? (await indexedDB.databases()).map((item) => item.name).filter(Boolean)
        : [],
      cacheNames: "caches" in window ? await caches.keys() : [],
      serviceWorkers: "serviceWorker" in navigator
        ? (await navigator.serviceWorker.getRegistrations()).length
        : 0,
      left: Number(document.querySelector("#left-width-control")?.value),
      right: Number(document.querySelector("#right-width-control")?.value),
      activeRightTab: document.querySelector('[data-right-tab][aria-selected="true"]')?.dataset.rightTab,
    };
  })()`, sessionId);

  {
    let removeListener;
    const loaded = new Promise((resolve) => {
      removeListener = client.on("Page.loadEventFired", (_event, eventSessionId) => {
        if (eventSessionId !== sessionId) return;
        removeListener();
        resolve();
      });
    });
    await client.send(
      "Page.navigate",
      { url: `${baseUrl}/studio/claim-boundaries/audited-draft/v1/` },
      sessionId,
    );
    await loaded;
    const poisonedLayout =
      `{"version":"STUDIO_AUDITED_DRAFT_LAYOUT_V1",` +
      `"left":"${definitionId}","left":300,"right":400,"activeRightTab":"help"}`;
    assert.ok(Buffer.byteLength(poisonedLayout, "utf8") <= 256);
    await client.evaluate(
      `localStorage.setItem(${JSON.stringify(storageKey)}, ${JSON.stringify(poisonedLayout)})`,
      sessionId,
    );
  }

  const ready = await navigateAndWait();
  assert.deepEqual(ready, {
    definitionId,
    projectId: ready.projectId,
    manifestHash: expectedManifestSha256,
    etag: `"${expectedManifestSha256}"`,
  });
  assert.match(ready.projectId, /^[0-9a-f-]{36}$/);

  let page = await inspectPage();
  let maxActiveRows = page.activeRows;
  assert.equal(page.definitionId, definitionId);
  assert.equal(page.manifestHash, expectedManifestSha256);
  assert.equal(page.etag, `"${expectedManifestSha256}"`);
  assert.equal(page.left, 272);
  assert.equal(page.right, 360);
  assert.equal(page.activeRightTab, "help");
  assert.ok(
    page.layoutRaw === null ||
      page.layoutRaw ===
        '{"version":"STUDIO_AUDITED_DRAFT_LAYOUT_V1","left":272,"right":360,"activeRightTab":"help"}',
    `poisoned layout survived as ${page.layoutRaw}`,
  );
  assert.equal(page.layoutRaw?.includes(definitionId) || false, false);
  assert.deepEqual(
    page.localStorageKeys,
    page.layoutRaw === null ? [] : [storageKey],
  );
  assert.ok(page.actorCount > 500, `actor cardinality was ${page.actorCount}`);
  assert.ok(page.elementCount > 500, `element cardinality was ${page.elementCount}`);
  assert.ok(page.activeRows > 0 && page.activeRows <= 100, `actor rows were ${page.activeRows}`);
  await client.evaluate(`document.querySelector("#authoring-elements").click()`, sessionId);
  page = await inspectPage();
  maxActiveRows = Math.max(maxActiveRows, page.activeRows);
  assert.ok(page.activeRows > 0 && page.activeRows <= 100, `element rows were ${page.activeRows}`);
  await client.evaluate(`document.querySelector("#authoring-actors").click()`, sessionId);
  assert.ok(page.totalDomNodes < 5_000, `DOM expanded to ${page.totalDomNodes} nodes`);
  assert.equal(page.crossCells, 0, "actor x element cells were allocated");
  assert.equal(page.disabled, true);
  assert.equal(page.boundaryVisible, true);

  await client.evaluate(`(() => {
    const left = document.querySelector("#left-width-control");
    const right = document.querySelector("#right-width-control");
    left.value = "300";
    left.dispatchEvent(new Event("input", { bubbles: true }));
    right.value = "400";
    right.dispatchEvent(new Event("input", { bubbles: true }));
    document.querySelector('[data-right-tab="help"]').click();
  })()`, sessionId);
  page = await inspectPage();
  assert.deepEqual(page.localStorageKeys, [storageKey]);
  assert.deepEqual(JSON.parse(page.layoutRaw), {
    version: "STUDIO_AUDITED_DRAFT_LAYOUT_V1",
    left: 300,
    right: 400,
    activeRightTab: "help",
  });
  assert.ok(Buffer.byteLength(page.layoutRaw, "utf8") <= 256);
  assert.equal(page.layoutRaw.includes(definitionId), false);

  await client.evaluate(`document.querySelector("#load-help").click()`, sessionId);
  await client.waitForExpression(
    `(document.querySelector("#help-frame")?.getAttribute("srcdoc") || document.querySelector("#help-frame")?.contentDocument?.body?.textContent || "").includes("Точная справка Foundation")`,
    sessionId,
    timeoutMs,
  );
  page = await inspectPage();
  assert.match(page.helpText, /Точная справка Foundation/);
  assert.equal(page.helpSha256, expectedHelpSha256);

  const remoteSave = await client.evaluate(`(async () => {
    const csrf = document.cookie.split(";").map((item) => item.trim()).find((item) => item.startsWith("csrftoken="))?.split("=").slice(1).join("=");
    const opened = await fetch(${JSON.stringify(openPath)}, { credentials: "same-origin", cache: "no-store" });
    const dto = await opened.json();
    const operationId = crypto.randomUUID();
    const response = await fetch(${JSON.stringify(savePath)}, {
      method: "PUT",
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf,
        "Idempotency-Key": operationId,
        "If-Match": dto.manifest_hash ? '"' + dto.manifest_hash + '"' : "",
      },
      body: ${JSON.stringify(remoteSaveBody)},
    });
    return {
      status: response.status,
      body: await response.json(),
      receiptSha256: response.headers.get("X-Foundation-Receipt-SHA256"),
    };
  })()`, sessionId);
  assert.equal(remoteSave.status, 200, JSON.stringify(remoteSave.body));
  assert.match(remoteSave.receiptSha256, /^[0-9a-f]{64}$/);

  await clearEvents();
  await client.evaluate(`(() => {
    const name = document.querySelector("#project-name");
    name.value = "Локально устаревший проект";
    name.dispatchEvent(new Event("input", { bubbles: true }));
    document.querySelector("#save-draft").click();
  })()`, sessionId);
  const conflict = await waitForEvent("studio:typed-conflict");
  assert.deepEqual(conflict, { definitionId, code: "DRAFT_STALE", status: 409 });
  const putsAtConflict = requests.filter(
    (item) => item.method === "PUT" && new URL(item.url).pathname === savePath,
  ).length;
  await delay(500);
  assert.equal(
    requests.filter((item) => item.method === "PUT" && new URL(item.url).pathname === savePath).length,
    putsAtConflict,
    "typed conflict triggered an automatic write retry",
  );

  await navigateAndWait({ reload: true });
  const mutations = await client.evaluate(`(() => {
    const input = (element, value) => {
      element.value = value;
      element.dispatchEvent(new Event("input", { bubbles: true }));
    };
    input(document.querySelector("#project-name"), "Проект C1 после сохранения");
    input(document.querySelector("#project-description"), "Сохранённый и перечитанный Foundation DRAFT.");

    const mutateCollection = (sectionId, addId, label, reference) => {
      document.querySelector(sectionId).click();
      const root = document.querySelector("#authoring-window");
      let rows = [...root.querySelectorAll("[data-authoring-row][data-item-id]")];
      const edited = rows[10];
      const editedId = edited.dataset.itemId;
      const followingId = rows[11].dataset.itemId;
      const initialOrder = Number(edited.querySelector("td")?.textContent);
      input(edited.querySelector('[data-field="label"]'), label);
      const referenceInput = edited.querySelector('[data-field="reference_statement"]');
      if (referenceInput && reference) input(referenceInput, reference);
      edited.querySelector('[data-action="move-down"]').click();
      rows = [...root.querySelectorAll("[data-authoring-row][data-item-id]")];
      const deletedId = rows[12].dataset.itemId;
      rows[12].querySelector('[data-action="delete"]').click();
      document.querySelector(addId).click();
      rows = [...root.querySelectorAll("[data-authoring-row][data-item-id]")];
      const added = rows.at(-1);
      return {
        editedId,
        followingId,
        initialOrder,
        deletedId,
        newId: added.dataset.itemId,
        newCode: added.querySelector("code")?.textContent,
      };
    };
    const actor = mutateCollection("#authoring-actors", "#add-actor", "Переименованный актор C1", null);
    const element = mutateCollection(
      "#authoring-elements",
      "#add-element",
      "Переименованный элемент C1",
      "Проверенное утверждение C1.",
    );
    return { actor, element };
  })()`, sessionId);
  page = await inspectPage();
  maxActiveRows = Math.max(maxActiveRows, page.activeRows);
  assert.equal(page.actorCount, 520);
  assert.equal(page.elementCount, 520);
  assert.ok(page.activeRows > 0 && page.activeRows <= 100);
  assert.ok(page.totalDomNodes < 5_000);

  const serverBeforePreview = await client.evaluate(`fetch(${JSON.stringify(openPath)}, { credentials: "same-origin", cache: "no-store" }).then((response) => response.json())`, sessionId);
  const projectNameBeforeInvalidPreview = await client.evaluate(`(() => {
    const input = document.querySelector("#project-name");
    const value = input.value;
    input.value = "";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    return value;
  })()`, sessionId);
  await clearEvents();
  await client.evaluate(`document.querySelector("#preview-validation").click()`, sessionId);
  const invalidPreview = await waitForEvent("studio:preview-complete");
  assert.equal(invalidPreview.definitionId, definitionId);
  assert.equal(invalidPreview.manifestHash, serverBeforePreview.manifest_hash);
  assert.equal(invalidPreview.valid, false);
  assert.equal(invalidPreview.status, 200);
  const invalidPreviewUi = await client.evaluate(`(() => ({
    stateCode: document.querySelector("#authoring-state-code")?.textContent,
    validationState: document.querySelector("#validation-state")?.textContent,
    diagnosticCodes: [...document.querySelectorAll("#validation-diagnostics [data-code]")]
      .map((item) => item.dataset.code),
  }))()`, sessionId);
  assert.equal(invalidPreviewUi.stateCode, "VALIDATION_PREVIEW_INVALID");
  assert.equal(invalidPreviewUi.validationState, "INVALID");
  assert.ok(invalidPreviewUi.diagnosticCodes.includes("FIELD_BLANK"));
  const serverAfterInvalidPreview = await client.evaluate(`fetch(${JSON.stringify(openPath)}, { credentials: "same-origin", cache: "no-store" }).then((response) => response.json())`, sessionId);
  assert.equal(
    serverAfterInvalidPreview.manifest_hash,
    serverBeforePreview.manifest_hash,
    "invalid preview wrote the DRAFT",
  );
  await client.evaluate(`(() => {
    const input = document.querySelector("#project-name");
    input.value = ${JSON.stringify(projectNameBeforeInvalidPreview)};
    input.dispatchEvent(new Event("input", { bubbles: true }));
  })()`, sessionId);
  await clearEvents();
  await client.evaluate(`document.querySelector("#preview-validation").click()`, sessionId);
  const preview = await waitForEvent("studio:preview-complete");
  assert.equal(preview.definitionId, definitionId);
  assert.equal(preview.manifestHash, serverBeforePreview.manifest_hash);
  assert.equal(preview.valid, true);
  assert.equal(preview.status, 200);
  const serverAfterPreview = await client.evaluate(`fetch(${JSON.stringify(openPath)}, { credentials: "same-origin", cache: "no-store" }).then((response) => response.json())`, sessionId);
  assert.equal(serverAfterPreview.manifest_hash, serverBeforePreview.manifest_hash, "preview wrote the DRAFT");

  await clearEvents();
  await client.evaluate(`document.querySelector("#save-draft").click()`, sessionId);
  const saved = await waitForEvent("studio:save-complete");
  assert.equal(saved.definitionId, definitionId);
  assert.equal(saved.status, 200);
  assert.equal(saved.replayed, false);
  assert.match(
    saved.operationId,
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
  );
  assert.match(saved.receiptSha256, /^[0-9a-f]{64}$/);
  assert.match(saved.manifestHash, /^[0-9a-f]{64}$/);
  assert.equal(saved.etag, `"${saved.manifestHash}"`);

  const finalRepresentation = await client.evaluate(`fetch(${JSON.stringify(openPath)}, { credentials: "same-origin", cache: "no-store" }).then(async (response) => {
    const raw = await response.text();
    return { raw, dto: JSON.parse(raw) };
  })`, sessionId);
  const finalDto = finalRepresentation.dto;
  const exactNumberMember = (raw, key, token) => {
    const escapedKey = key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const escapedToken = token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    assert.match(
      raw,
      new RegExp(`"${escapedKey}"\\s*:\\s*${escapedToken}(?=[,}])`),
    );
  };
  exactNumberMember(finalRepresentation.raw, losslessBigintKey, "9007199254740993");
  exactNumberMember(finalRepresentation.raw, losslessExponentKey, losslessExponentToken);
  assert.equal(finalDto.manifest_hash, saved.manifestHash);
  assert.equal(finalDto.manifest.project.name, "Проект C1 после сохранения");
  assert.ok(finalDto.manifest.actors.some((item) => item.label === "Переименованный актор C1"));
  assert.ok(finalDto.manifest.analytical_elements.some((item) => item.label === "Переименованный элемент C1"));
  const assertMutationPersisted = (collection, mutation, expectedLabel) => {
    const ids = collection.map((item) => item.id);
    const edited = collection.find((item) => item.id === mutation.editedId);
    const added = collection.find((item) => item.id === mutation.newId);
    assert.equal(collection.length, 520);
    assert.equal(edited?.label, expectedLabel, "renamed row was not persisted by exact id");
    assert.notEqual(edited?.order, mutation.initialOrder, "row order did not change");
    assert.equal(ids.includes(mutation.deletedId), false, "deleted row survived save");
    assert.ok(ids.indexOf(mutation.editedId) > ids.indexOf(mutation.followingId), "move-down was not persisted");
    assert.equal(added?.code, mutation.newCode, "new row was not persisted by exact id/code");
  };
  assertMutationPersisted(
    finalDto.manifest.actors,
    mutations.actor,
    "Переименованный актор C1",
  );
  assertMutationPersisted(
    finalDto.manifest.analytical_elements,
    mutations.element,
    "Переименованный элемент C1",
  );

  const reloaded = await navigateAndWait({ reload: true });
  assert.equal(reloaded.manifestHash, saved.manifestHash);
  const reloadedRaw = await client.evaluate(
    `fetch(${JSON.stringify(openPath)}, { credentials: "same-origin", cache: "no-store" }).then((response) => response.text())`,
    sessionId,
  );
  exactNumberMember(reloadedRaw, losslessBigintKey, "9007199254740993");
  exactNumberMember(reloadedRaw, losslessExponentKey, losslessExponentToken);
  page = await inspectPage();
  assert.equal(page.projectName, "Проект C1 после сохранения");
  assert.deepEqual(page.localStorageKeys, [storageKey]);
  assert.equal(page.sessionStorageLength, 0);
  assert.deepEqual(page.indexedDbNames, []);
  assert.deepEqual(page.cacheNames, []);
  assert.equal(page.serviceWorkers, 0);

  const apiRequests = requests.filter((item) => new URL(item.url).pathname.startsWith("/api/"));
  assert.ok(apiRequests.length > 0);
  assert.equal(
    apiRequests.every((item) => new URL(item.url).pathname.startsWith("/api/foundation/")),
    true,
    "a non-Foundation API was called",
  );
  const mutationRequests = apiRequests.filter((item) => !["GET", "HEAD"].includes(item.method));
  assert.equal(
    mutationRequests.every((item) => [savePath, previewPath].includes(new URL(item.url).pathname)),
    true,
    "an unauthorized mutation route was called",
  );
  const saveRequests = mutationRequests.filter((item) => item.method === "PUT");
  assert.equal(saveRequests.length, 3, "save was retried or an unexpected write occurred");
  for (const request of saveRequests) {
    assert.match(
      request.headers["idempotency-key"],
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
    assert.match(request.headers["if-match"], /^"[0-9a-f]{64}"$/);
    assert.ok(request.headers["x-csrftoken"]);
  }
  const previewRequests = mutationRequests.filter((item) => item.method === "POST");
  assert.equal(previewRequests.length, 2);
  for (const request of previewRequests) {
    assert.equal("idempotency-key" in request.headers, false);
    assert.equal("if-match" in request.headers, false);
  }

  const cookies = await client.send("Network.getAllCookies", {}, sessionId);
  assert.ok(cookies.cookies.some((item) => item.name === sessionCookieName));
  assert.ok(
    cookies.cookies.every((item) => [sessionCookieName, "csrftoken"].includes(item.name)),
    `unexpected cookies: ${cookies.cookies.map((item) => item.name).join(",")}`,
  );

  console.log(JSON.stringify({
    browser_result: "PASS",
    browser: browser.version.Browser,
    definition_id: definitionId,
    claim_contract_sha256: expectedClaimSha256,
    final_manifest_sha256: saved.manifestHash,
    receipt_sha256: saved.receiptSha256,
    typed_conflict: conflict.code,
    observed_actor_count: page.actorCount,
    observed_element_count: page.elementCount,
    max_active_rows: maxActiveRows,
    storage_key: storageKey,
    foundation_requests: apiRequests.length,
  }));
} finally {
  await browser.close();
}
