import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";

import { launchChromium } from "./cdp_client.mjs";


const EVENT_NAMES = Object.freeze([
  "studio:lifecycle-ready",
  "studio:lifecycle-preview-complete",
  "studio:lifecycle-attempt-prepared",
  "studio:lifecycle-ticket-retained",
  "studio:lifecycle-unknown-outcome",
  "studio:lifecycle-validation-ticket-imported",
  "studio:lifecycle-validation-complete",
  "studio:lifecycle-publication-complete",
  "studio:lifecycle-publication-recovery-complete",
]);
const UUID_V4_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;

const requiredEnvironment = (name) => {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
};

const environment = () => ({
  baseUrl: requiredEnvironment("STUDIO_BASE_URL").replace(/\/$/, ""),
  definitionId: requiredEnvironment("STUDIO_DEFINITION_ID").toLowerCase(),
  predecessorId: (process.env.STUDIO_PREDECESSOR_ID || "").toLowerCase(),
  sessionCookieName: requiredEnvironment("STUDIO_SESSION_COOKIE_NAME"),
  editorSessionCookieValue: requiredEnvironment("STUDIO_EDITOR_SESSION_COOKIE_VALUE"),
  publisherSessionCookieValue: requiredEnvironment("STUDIO_PUBLISHER_SESSION_COOKIE_VALUE"),
  expectedClaimSha256: requiredEnvironment("STUDIO_EXPECTED_CLAIM_SHA256"),
  timeoutMs: Number(process.env.STUDIO_CDP_TIMEOUT_MS || "60000"),
});

const normalizedHeaders = (headers) => Object.fromEntries(
  Object.entries(headers || {}).map(([name, value]) => [name.toLowerCase(), String(value)]),
);

async function createHarness() {
  const env = environment();
  const browser = await launchChromium({ timeoutMs: env.timeoutMs });
  const { client } = browser;
  const requests = [];
  const responses = [];
  const sessions = new Set();

  client.on("Network.requestWillBeSent", (event, sessionId) => {
    if (!sessions.has(sessionId) || !/^https?:/.test(event.request.url)) return;
    requests.push({
      sessionId,
      method: event.request.method,
      url: event.request.url,
      headers: normalizedHeaders(event.request.headers),
      postData: event.request.postData ?? null,
    });
  });
  client.on("Network.responseReceived", (event, sessionId) => {
    if (!sessions.has(sessionId) || !/^https?:/.test(event.response.url)) return;
    responses.push({
      sessionId,
      status: event.response.status,
      url: event.response.url,
      headers: normalizedHeaders(event.response.headers),
    });
  });

  const setSessionCookie = async (page, value) => {
    const cookie = await client.send("Network.setCookie", {
      name: env.sessionCookieName,
      value,
      url: `${env.baseUrl}/`,
      httpOnly: true,
      sameSite: "Lax",
      secure: env.baseUrl.startsWith("https:"),
    }, page.sessionId);
    assert.equal(cookie.success, true, "pre-issued session cookie was not admitted");
  };

  const createPage = async () => {
    const { targetId } = await client.send("Target.createTarget", { url: "about:blank" });
    const attached = await client.send("Target.attachToTarget", { targetId, flatten: true });
    const sessionId = attached.sessionId;
    sessions.add(sessionId);
    await Promise.all([
      client.send("Page.enable", {}, sessionId),
      client.send("Runtime.enable", {}, sessionId),
      client.send("Network.enable", { maxTotalBufferSize: 50_000_000 }, sessionId),
    ]);
    await client.send("Page.addScriptToEvaluateOnNewDocument", {
      source: `(() => {
        window.__studioLifecycleEvents = [];
        for (const name of ${JSON.stringify(EVENT_NAMES)}) {
          window.addEventListener(name, (event) => {
            let detail = {};
            try { detail = JSON.parse(JSON.stringify(event.detail || {})); }
            catch { detail = { serializationError: true }; }
            window.__studioLifecycleEvents.push({ name, detail });
          });
        }
      })();`,
    }, sessionId);
    client.on("Page.javascriptDialogOpening", (_event, eventSessionId) => {
      if (eventSessionId === sessionId) {
        client.send("Page.handleJavaScriptDialog", { accept: true }, sessionId).catch(() => {});
      }
    });
    return { targetId, sessionId };
  };

  const navigate = async (page, { reload = false } = {}) => {
    const loaded = new Promise((resolve) => {
      const remove = client.on("Page.loadEventFired", (_event, eventSessionId) => {
        if (eventSessionId !== page.sessionId) return;
        remove();
        resolve();
      });
    });
    if (reload) {
      await client.send("Page.reload", { ignoreCache: true }, page.sessionId);
    } else {
      await client.send("Page.navigate", {
        url: `${env.baseUrl}/studio/lifecycle/definitions/${env.definitionId}/`,
      }, page.sessionId);
    }
    await loaded;
    await client.waitForExpression(
      `window.__studioLifecycleEvents?.some((item) => item.name === "studio:lifecycle-ready") ||
        !["", "LOADING"].includes(document.querySelector("#lifecycle-state-code")?.textContent || "")`,
      page.sessionId,
      env.timeoutMs,
    );
    const ready = await lastEvent(page, "studio:lifecycle-ready");
    if (!ready) {
      const failure = await client.evaluate(`({
        code: document.querySelector("#lifecycle-state-code")?.textContent,
        message: document.querySelector("#lifecycle-state-message")?.textContent,
      })`, page.sessionId);
      throw new Error(`Lifecycle bootstrap failed: ${JSON.stringify(failure)}`);
    }
    return ready;
  };

  const lastEvent = (page, name) => client.evaluate(
    `window.__studioLifecycleEvents.filter((item) => item.name === ${JSON.stringify(name)}).at(-1)?.detail`,
    page.sessionId,
  );

  const clearEvents = (page) => client.evaluate(
    "window.__studioLifecycleEvents.length = 0",
    page.sessionId,
  );

  const waitEvent = async (page, name) => {
    await client.waitForExpression(
      `window.__studioLifecycleEvents?.some((item) => item.name === ${JSON.stringify(name)})`,
      page.sessionId,
      env.timeoutMs,
    );
    return lastEvent(page, name);
  };

  const waitPublicationRecovery = async (page) => {
    await client.waitForExpression(
      `window.__studioLifecycleEvents?.some((item) => item.name === "studio:lifecycle-publication-recovery-complete") ||
        document.querySelector("#lifecycle-state-code")?.textContent === "PUBLICATION_RECOVERY_UNVERIFIED"`,
      page.sessionId,
      env.timeoutMs,
    );
    const recovered = await lastEvent(page, "studio:lifecycle-publication-recovery-complete");
    if (recovered) return recovered;
    const failure = await client.evaluate(`({
      code: document.querySelector("#lifecycle-state-code")?.textContent,
      message: document.querySelector("#lifecycle-state-message")?.textContent,
    })`, page.sessionId);
    throw new Error(`Publication recovery failed: ${JSON.stringify(failure)}`);
  };

  const waitValidationCompletion = async (page) => {
    await client.waitForExpression(
      `window.__studioLifecycleEvents?.some((item) => item.name === "studio:lifecycle-validation-complete") ||
        window.__studioLifecycleEvents?.some((item) => item.name === "studio:lifecycle-unknown-outcome")`,
      page.sessionId,
      env.timeoutMs,
    );
    const completed = await lastEvent(page, "studio:lifecycle-validation-complete");
    if (completed) return completed;
    const failure = await client.evaluate(`({
      code: document.querySelector("#lifecycle-state-code")?.textContent,
      message: document.querySelector("#lifecycle-state-message")?.textContent,
    })`, page.sessionId);
    throw new Error(`Validation reconciliation failed: ${JSON.stringify(failure)}`);
  };

  const click = (page, selector) => client.evaluate(
    `document.querySelector(${JSON.stringify(selector)}).click()`,
    page.sessionId,
  );

  const setValue = (page, selector, value) => client.evaluate(
    `(() => {
      const control = document.querySelector(${JSON.stringify(selector)});
      control.value = ${JSON.stringify(value)};
      control.dispatchEvent(new Event("input", { bubbles: true }));
    })()`,
    page.sessionId,
  );

  const inspect = (page) => client.evaluate(`(async () => ({
    state: document.querySelector("#lifecycle-state-code")?.textContent,
    status: document.querySelector("#lifecycle-publication-status")?.textContent,
    isCurrent: document.querySelector("#lifecycle-is-current")?.textContent,
    candidateKind: document.querySelector("#readiness-candidate-kind")?.textContent,
    nextAction: document.querySelector("#readiness-next-action")?.textContent,
    prepareText: document.querySelector("#prepare-lifecycle-attempt")?.textContent,
    prepareDisabled: document.querySelector("#prepare-lifecycle-attempt")?.disabled,
    executeDisabled: document.querySelector("#execute-sealed-attempt")?.disabled,
    operationId: document.querySelector("#attempt-operation-id")?.textContent,
    ticket: document.querySelector("#recovery-ticket")?.value || "",
    unavailableControls: [
      "lifecycle-package-control", "lifecycle-document-control", "lifecycle-chat-control",
      "lifecycle-science-control", "lifecycle-prediction-control", "lifecycle-recommendation-control",
    ].every((id) => document.getElementById(id)?.disabled === true),
    localStorage: Object.fromEntries(Object.entries(localStorage)),
    sessionStorage: Object.fromEntries(Object.entries(sessionStorage)),
    indexedDbNames: typeof indexedDB.databases === "function"
      ? (await indexedDB.databases()).map((item) => item.name).filter(Boolean)
      : [],
    cacheNames: "caches" in window ? await caches.keys() : [],
    serviceWorkers: "serviceWorker" in navigator
      ? (await navigator.serviceWorker.getRegistrations()).length
      : 0,
  }))()`, page.sessionId);

  const failNextResponse = async (page, path) => {
    await client.send("Fetch.enable", {
      patterns: [{ urlPattern: `*${path}*`, requestStage: "Response" }],
    }, page.sessionId);
    let settled = false;
    let resolveIntercepted;
    let rejectIntercepted;
    const intercepted = new Promise((resolve, reject) => {
      resolveIntercepted = resolve;
      rejectIntercepted = reject;
    });
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      remove();
      client.send("Fetch.disable", {}, page.sessionId).catch(() => {});
      rejectIntercepted(new Error(`Response interception timed out for ${path}`));
    }, env.timeoutMs);
    const remove = client.on("Fetch.requestPaused", (event, eventSessionId) => {
      if (settled || eventSessionId !== page.sessionId) return;
      if (new URL(event.request.url).pathname !== path || event.responseStatusCode === undefined) {
        client.send("Fetch.continueRequest", { requestId: event.requestId }, page.sessionId).catch(() => {});
        return;
      }
      settled = true;
      clearTimeout(timer);
      client.send("Fetch.failRequest", {
        requestId: event.requestId,
        errorReason: "Aborted",
      }, page.sessionId).finally(() => {
        client.send("Fetch.disable", {}, page.sessionId).catch(() => {});
        remove();
        resolveIntercepted();
      });
    });
    return Object.freeze({ intercepted });
  };

  const closePage = async (page) => {
    sessions.delete(page.sessionId);
    await client.send("Target.closeTarget", { targetId: page.targetId });
  };

  return {
    browser, client, env, requests, responses,
    createPage, navigate, clearEvents, waitEvent, waitPublicationRecovery, waitValidationCompletion,
    click, setValue, inspect,
    failNextResponse, closePage, setSessionCookie,
  };
}

async function assertStorageBoundary(harness, page, forbiddenValues) {
  const state = await harness.inspect(page);
  assert.deepEqual(state.localStorage, {});
  assert.deepEqual(state.sessionStorage, {});
  assert.deepEqual(state.indexedDbNames, []);
  assert.deepEqual(state.cacheNames, []);
  assert.equal(state.serviceWorkers, 0);
  const persistentText = JSON.stringify([state.localStorage, state.sessionStorage]);
  for (const value of forbiddenValues.filter(Boolean)) {
    assert.equal(persistentText.includes(value), false, `persistent storage contains ${value}`);
  }
  assert.equal(state.unavailableControls, true);
}

async function acknowledgeTicket(harness, page) {
  const before = await harness.inspect(page);
  assert.match(before.operationId, UUID_V4_PATTERN);
  assert.ok(before.ticket.endsWith("\n"));
  const ticket = JSON.parse(before.ticket);
  assert.equal(ticket.contract, "FOUNDATION_HUMAN_WRITE_RECOVERY_TICKET_V1");
  assert.equal(ticket.operation_id, before.operationId);
  assert.match(ticket.ticket_sha256, SHA256_PATTERN);
  assert.equal(before.executeDisabled, true);
  await harness.setValue(page, "#ticket-copy-proof", before.ticket);
  await harness.click(page, "#acknowledge-ticket-copy");
  const retained = await harness.waitEvent(page, "studio:lifecycle-ticket-retained");
  assert.equal(retained.method, "exact-copy");
  assert.equal(retained.operationId, before.operationId);
  assert.equal((await harness.inspect(page)).executeDisabled, false);
  return { text: before.ticket, ticket };
}

export async function test_chromium_draft_preview_atomic_initial_publish_recover_and_reload() {
  const harness = await createHarness();
  let page;
  try {
    page = await harness.createPage();
    await harness.setSessionCookie(page, harness.env.editorSessionCookieValue);
    const editorReady = await harness.navigate(page);
    assert.equal(editorReady.definitionId, harness.env.definitionId);
    assert.equal(editorReady.publicationStatus, "DRAFT");
    assert.equal(editorReady.candidateKind, "INITIAL");
    assert.equal(editorReady.requiredNextAction, "PREVIEW_OR_INITIAL_PUBLISH");
    assert.equal(editorReady.actionKind, "NONE");
    await harness.clearEvents(page);
    await harness.click(page, "#preview-lifecycle");
    const preview = await harness.waitEvent(page, "studio:lifecycle-preview-complete");
    assert.equal(preview.status, 200);
    assert.equal(preview.definitionId, harness.env.definitionId);

    await harness.setSessionCookie(page, harness.env.publisherSessionCookieValue);
    await harness.clearEvents(page);
    const ready = await harness.navigate(page);
    assert.equal(ready.definitionId, harness.env.definitionId);
    assert.equal(ready.publicationStatus, "DRAFT");
    assert.equal(ready.candidateKind, "INITIAL");
    assert.equal(ready.requiredNextAction, "PREVIEW_OR_INITIAL_PUBLISH");
    assert.equal(ready.actionKind, "PUBLISH_INITIAL");
    assert.equal(ready.readinessSha256.length, 64);

    await harness.clearEvents(page);
    await harness.click(page, "#prepare-lifecycle-attempt");
    const prepared = await harness.waitEvent(page, "studio:lifecycle-attempt-prepared");
    assert.equal(prepared.operationKind, "PUBLISH_INITIAL");
    const retained = await acknowledgeTicket(harness, page);
    await harness.clearEvents(page);
    const publishPath = `/api/foundation/definitions/${harness.env.definitionId}/publish-initial/`;
    const responseFailure = await harness.failNextResponse(page, publishPath);
    await harness.click(page, "#execute-sealed-attempt");
    await responseFailure.intercepted;
    const unknown = await harness.waitEvent(page, "studio:lifecycle-unknown-outcome");
    assert.equal(unknown.operationKind, "PUBLISH_INITIAL");

    await harness.clearEvents(page);
    await harness.click(page, "#recover-publication-operation");
    const recovered = await harness.waitPublicationRecovery(page);
    assert.equal(recovered.operationId, retained.ticket.operation_id);
    assert.match(recovered.resultSha256, SHA256_PATTERN);

    await harness.clearEvents(page);
    const reloaded = await harness.navigate(page, { reload: true });
    assert.equal(reloaded.publicationStatus, "PUBLISHED");
    assert.equal(reloaded.isCurrent, true);
    assert.equal(reloaded.actionKind, "NONE");
    const finalPage = await harness.inspect(page);
    assert.equal(finalPage.status, "PUBLISHED");
    assert.equal(finalPage.isCurrent, "true");
    await assertStorageBoundary(harness, page, [
      harness.env.definitionId,
      ready.projectId,
      ready.manifestHash,
      retained.ticket.operation_id,
      retained.text,
    ]);

    const mutationRequests = harness.requests.filter((item) => !["GET", "HEAD"].includes(item.method));
    assert.equal(mutationRequests.filter((item) => item.method === "POST" && new URL(item.url).pathname === publishPath).length, 1);
    assert.equal(mutationRequests.filter((item) => new URL(item.url).pathname.endsWith("/validation-preview/")).length, 1);
    console.log(JSON.stringify({
      browser_result: "PASS",
      scenario: "test_chromium_draft_preview_atomic_initial_publish_recover_and_reload",
      browser: harness.browser.version.Browser,
      definition_id: harness.env.definitionId,
      operation_id: retained.ticket.operation_id,
      result_sha256: recovered.resultSha256,
      claim_contract_sha256: harness.env.expectedClaimSha256,
    }));
  } finally {
    await harness.browser.close();
  }
}

export async function test_chromium_successor_validate_publish_lost_response_recovery_and_predecessor_noncurrent() {
  const harness = await createHarness();
  assert.match(harness.env.predecessorId, /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/);
  let page;
  try {
    page = await harness.createPage();
    await harness.setSessionCookie(page, harness.env.publisherSessionCookieValue);
    const ready = await harness.navigate(page);
    assert.equal(ready.publicationStatus, "DRAFT");
    assert.equal(ready.candidateKind, "SUCCESSOR");
    assert.equal(ready.requiredNextAction, "VALIDATE");
    assert.equal(ready.actionKind, "VALIDATE_DEFINITION");

    await harness.clearEvents(page);
    await harness.click(page, "#prepare-lifecycle-attempt");
    const validationPrepared = await harness.waitEvent(page, "studio:lifecycle-attempt-prepared");
    assert.equal(validationPrepared.operationKind, "VALIDATE_DEFINITION");
    const validationTicket = await acknowledgeTicket(harness, page);
    assert.equal(validationTicket.ticket.body_utf8, "{}");
    assert.equal(validationTicket.ticket.body_byte_length, 2);

    await harness.clearEvents(page);
    const validatePath = `/api/foundation/definitions/${harness.env.definitionId}/validate/`;
    const validationResponseFailure = await harness.failNextResponse(page, validatePath);
    await harness.click(page, "#execute-sealed-attempt");
    await validationResponseFailure.intercepted;
    const validationUnknown = await harness.waitEvent(page, "studio:lifecycle-unknown-outcome");
    assert.equal(validationUnknown.operationKind, "VALIDATE_DEFINITION");

    await harness.closePage(page);
    page = await harness.createPage();
    const afterLoss = await harness.navigate(page);
    assert.equal(afterLoss.publicationStatus, "VALIDATED");
    assert.equal(afterLoss.actionKind, "PUBLISH_SUCCESSOR");
    await harness.clearEvents(page);
    await harness.setValue(page, "#import-recovery-ticket", validationTicket.text);
    await harness.click(page, "#import-validation-ticket");
    const imported = await harness.waitEvent(page, "studio:lifecycle-validation-ticket-imported");
    assert.equal(imported.operationId, validationTicket.ticket.operation_id);
    assert.equal(imported.persistedStatus, "VALIDATED");

    await harness.clearEvents(page);
    await harness.click(page, "#replay-validation-attempt");
    const reconciled = await harness.waitValidationCompletion(page);
    assert.equal(reconciled.operationId, validationTicket.ticket.operation_id);
    assert.equal(reconciled.replayed, true);
    assert.match(reconciled.receiptSha256, SHA256_PATTERN);

    await harness.clearEvents(page);
    await harness.click(page, "#prepare-lifecycle-attempt");
    const publicationPrepared = await harness.waitEvent(page, "studio:lifecycle-attempt-prepared");
    assert.equal(publicationPrepared.operationKind, "PUBLISH_SUCCESSOR");
    const publicationTicket = await acknowledgeTicket(harness, page);
    assert.notEqual(publicationTicket.ticket.operation_id, validationTicket.ticket.operation_id);

    await harness.clearEvents(page);
    const publishPath = `/api/foundation/definitions/${harness.env.definitionId}/publish-successor/`;
    const publicationResponseFailure = await harness.failNextResponse(page, publishPath);
    await harness.click(page, "#execute-sealed-attempt");
    await publicationResponseFailure.intercepted;
    const publicationUnknown = await harness.waitEvent(page, "studio:lifecycle-unknown-outcome");
    assert.equal(publicationUnknown.operationKind, "PUBLISH_SUCCESSOR");
    await harness.clearEvents(page);
    await harness.click(page, "#recover-publication-operation");
    const publicationRecovered = await harness.waitPublicationRecovery(page);
    assert.equal(publicationRecovered.operationId, publicationTicket.ticket.operation_id);

    const persisted = await harness.client.evaluate(`Promise.all([
      ${JSON.stringify(`/api/foundation/definitions/${harness.env.predecessorId}/`)},
      ${JSON.stringify(`/api/foundation/definitions/${harness.env.definitionId}/`)},
    ].map(async (url) => {
      const response = await fetch(url, {
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
      });
      return { status: response.status, url: response.url, body: await response.json() };
    }))`, page.sessionId);
    assert.equal(persisted[0].status, 200, JSON.stringify(persisted[0]));
    assert.equal(persisted[1].status, 200, JSON.stringify(persisted[1]));
    assert.equal(persisted[0].body.publication_status, "PUBLISHED");
    assert.equal(persisted[0].body.is_current, false);
    assert.equal(persisted[1].body.publication_status, "PUBLISHED");
    assert.equal(persisted[1].body.is_current, true);
    await assertStorageBoundary(harness, page, [
      harness.env.definitionId,
      harness.env.predecessorId,
      ready.projectId,
      validationTicket.ticket.operation_id,
      publicationTicket.ticket.operation_id,
      validationTicket.text,
      publicationTicket.text,
    ]);

    const validationRequests = harness.requests.filter(
      (item) => item.method === "POST" && new URL(item.url).pathname === validatePath,
    );
    assert.equal(validationRequests.length, 2);
    assert.deepEqual(validationRequests[1].headers["idempotency-key"], validationRequests[0].headers["idempotency-key"]);
    assert.deepEqual(validationRequests[1].headers["if-match"], validationRequests[0].headers["if-match"]);
    assert.deepEqual(validationRequests[1].postData, validationRequests[0].postData);
    assert.equal(validationRequests[0].postData, "{}");
    assert.equal(harness.requests.filter(
      (item) => item.method === "POST" && new URL(item.url).pathname === publishPath,
    ).length, 1);
    console.log(JSON.stringify({
      browser_result: "PASS",
      scenario: "test_chromium_successor_validate_publish_lost_response_recovery_and_predecessor_noncurrent",
      browser: harness.browser.version.Browser,
      definition_id: harness.env.definitionId,
      predecessor_id: harness.env.predecessorId,
      validation_operation_id: validationTicket.ticket.operation_id,
      publication_operation_id: publicationTicket.ticket.operation_id,
      claim_contract_sha256: harness.env.expectedClaimSha256,
    }));
  } finally {
    await harness.browser.close();
  }
}

const scenarios = Object.freeze({
  test_chromium_draft_preview_atomic_initial_publish_recover_and_reload,
  test_chromium_successor_validate_publish_lost_response_recovery_and_predecessor_noncurrent,
});

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const scenario = requiredEnvironment("STUDIO_C2A_SCENARIO");
  if (!(scenario in scenarios)) throw new Error(`Unknown STUDIO_C2A_SCENARIO: ${scenario}`);
  await scenarios[scenario]();
}
