import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { writeFile } from "node:fs/promises";

import { launchChromium } from "../../production_studio/browser_tests/cdp_client.mjs";


const required = (name) => {
  const value = process.env[name];
  if (!value) throw new Error(name + " is required");
  return value;
};

const baseUrl = required("PLAYER_BASE_URL").replace(/\/$/, "");
const projectId = required("PLAYER_PROJECT_ID").toLowerCase();
const definitionId = required("PLAYER_DEFINITION_ID").toLowerCase();
const sessionCookieName = required("PLAYER_SESSION_COOKIE_NAME");
const sessionCookieValue = required("PLAYER_SESSION_COOKIE_VALUE");
const unscopedSessionCookieValue = required("PLAYER_UNSCOPED_SESSION_COOKIE_VALUE");
const missingPermissionSessionCookieValue = required("PLAYER_MISSING_PERMISSION_SESSION_COOKIE_VALUE");
const staffSessionCookieValue = required("PLAYER_STAFF_SESSION_COOKIE_VALUE");
const expectedClaimSha256 = required("PLAYER_EXPECTED_CLAIM_SHA256");
const expectedManifestSha256 = required("PLAYER_EXPECTED_MANIFEST_SHA256");
const scenario = required("PLAYER_SCENARIO");
const requestedWorkspaceId = process.env.PLAYER_WORKSPACE_ID?.toLowerCase() || null;
const timeoutMs = Number(process.env.PLAYER_CDP_TIMEOUT_MS || "60000");
const screenshotPath = process.env.PLAYER_SCREENSHOT_PATH || null;
const storageKey = "conflict-analysis-player:layout:v1";
const commandIds = [
  "CMD-WORKSPACE-CREATE",
  "CMD-WORKSPACE-OPEN",
  "CMD-WORKSPACE-SWITCH",
  "CMD-SLICE-CREATE",
  "CMD-SLICE-OPEN",
  "CMD-SLICE-SWITCH",
  "CMD-SLICE-REFRESH",
];
const projectUrl = baseUrl + "/player/projects/" + projectId + "/";
const workspaceUrl = (workspaceId) => baseUrl + "/player/workspaces/" + workspaceId + "/";
const workspaceApi = "/api/foundation/player/projects/" + projectId + "/workspaces/";
const workspaceReadApi = (workspaceId) => "/api/foundation/player/workspaces/" + workspaceId + "/";
const sliceApi = (workspaceId) => "/api/foundation/player/workspaces/" + workspaceId + "/time-slices/";
const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

const normalizedHeaders = (headers) => Object.fromEntries(
  Object.entries(headers || {}).map(([name, value]) => [name.toLowerCase(), String(value)]),
);

const browser = await launchChromium({ timeoutMs });
let client;
let sessionId;
const requests = new Map();
const responses = new Map();
const completedResponses = [];

const pageStateExpression = "(() => {"
  + "const app=document.querySelector('#player-app');"
  + "const toolbar=[...document.querySelectorAll('#player-toolbar [data-command-id]')];"
  + "return {"
  + "page:app?.dataset.playerPage,state:app?.dataset.state,projectId:app?.dataset.projectId,"
  + "workspaceId:app?.dataset.workspaceId||null,projectionStatus:app?.dataset.projectionStatus,"
  + "reloadNotice:app?.dataset.reloadNotice||'',stateMessage:document.querySelector('#player-state-message')?.textContent||'',"
  + "playerStateHidden:document.querySelector('#player-state')?.hidden===true,"
  + "claimSha256:app?.dataset.claimSha256,commandIds:toolbar.map(n=>n.dataset.commandId),"
  + "sliceId:document.querySelector('#slice-select')?.value||null,sliceDate:document.querySelector('#slice-date')?.textContent||null,"
  + "manifestHash:document.querySelector('#definition-hash')?.textContent||null,"
  + "enabledCommands:toolbar.filter(n=>n.getAttribute('aria-disabled')!=='true').map(n=>n.dataset.commandId),"
  + "treeRows:document.querySelectorAll('#structure-tree [role=treeitem],#structure-tree [data-tree-row]').length,"
  + "treeTotal:Number(document.querySelector('#structure-count')?.textContent||'0'),"
  + "domNodes:document.getElementsByTagName('*').length,"
  + "storageKeys:Object.keys(localStorage).sort(),storageRaw:localStorage.getItem("
  + JSON.stringify(storageKey) + "),"
  + "documentReason:document.querySelector('#tab-document')?.getAttribute('title')||document.querySelector('#panel-document [data-boundary=document]')?.textContent,"
  + "chatReason:document.querySelector('#tab-chat')?.getAttribute('title')||document.querySelector('#panel-chat [data-boundary=chat]')?.textContent,"
  + "plusReason:document.querySelector('#experiment-plus')?.getAttribute('title'),"
  + "helpVisible:!document.querySelector('#help-topic')?.hidden,"
  + "helpScope:document.querySelector('#help-identity')?.textContent||'',"
  + "left:Number(document.querySelector('#left-divider')?.getAttribute('aria-valuenow')),"
  + "right:Number(document.querySelector('#right-divider')?.getAttribute('aria-valuenow'))"
  + "};"
  + "})()";

try {
  client = browser.client;
  const created = await client.send("Target.createTarget", { url: "about:blank" });
  const attached = await client.send("Target.attachToTarget", {
    targetId: created.targetId,
    flatten: true,
  });
  sessionId = attached.sessionId;
  await Promise.all([
    client.send("Page.enable", {}, sessionId),
    client.send("Runtime.enable", {}, sessionId),
    client.send("Network.enable", { maxTotalBufferSize: 50_000_000 }, sessionId),
  ]);
  await client.send("Browser.setDownloadBehavior", { behavior: "deny" });

  client.on("Network.requestWillBeSent", (event, eventSessionId) => {
    if (eventSessionId !== sessionId || !/^https?:/.test(event.request.url)) return;
    requests.set(event.requestId, {
      requestId: event.requestId,
      method: event.request.method,
      url: event.request.url,
      requestHeaders: normalizedHeaders(event.request.headers),
      postData: event.request.postData || null,
    });
  });
  client.on("Network.responseReceived", (event, eventSessionId) => {
    if (eventSessionId !== sessionId || !/^https?:/.test(event.response.url)) return;
    responses.set(event.requestId, {
      requestId: event.requestId,
      url: event.response.url,
      status: event.response.status,
      responseHeaders: normalizedHeaders(event.response.headers),
    });
  });
  client.on("Network.loadingFinished", (event, eventSessionId) => {
    if (eventSessionId !== sessionId) return;
    const request = requests.get(event.requestId);
    const response = responses.get(event.requestId);
    if (!request || !response) return;
    client.send("Network.getResponseBody", { requestId: event.requestId }, sessionId)
      .then((payload) => completedResponses.push({
        ...request,
        ...response,
        body: Buffer.from(payload.body, payload.base64Encoded ? "base64" : "utf8"),
      }))
      .catch(() => {});
  });

  const setSessionCookie = async (value) => {
    const cookie = await client.send("Network.setCookie", {
      name: sessionCookieName,
      value,
      url: baseUrl + "/",
      httpOnly: true,
      sameSite: "Lax",
      secure: baseUrl.startsWith("https:"),
    }, sessionId);
    assert.equal(cookie.success, true);
  };
  await setSessionCookie(sessionCookieValue);

  const waitForNavigation = async (action) => {
    let remove;
    let timer;
    const loaded = new Promise((resolve, reject) => {
      remove = client.on("Page.loadEventFired", (_event, eventSessionId) => {
        if (eventSessionId !== sessionId) return;
        clearTimeout(timer);
        remove();
        resolve();
      });
      timer = setTimeout(() => {
        remove();
        reject(new Error("navigation did not finish before the CDP timeout"));
      }, timeoutMs);
    });
    try {
      await action();
      await loaded;
    } catch (error) {
      clearTimeout(timer);
      remove?.();
      throw error;
    }
    await client.waitForExpression(
      "document.querySelector('#player-app')?.dataset.state === 'ready'",
      sessionId,
      timeoutMs,
    );
  };
  const navigate = async (url, reload = false) => waitForNavigation(() => (
    reload
      ? client.send("Page.reload", { ignoreCache: true }, sessionId)
      : client.send("Page.navigate", { url }, sessionId)
  ));
  const state = () => client.evaluate(pageStateExpression, sessionId);
  const click = (selector) => client.evaluate(
    "document.querySelector(" + JSON.stringify(selector) + ")?.click()",
    sessionId,
  );
  const pointerClick = async (selector) => {
    const box = await client.evaluate(
      "(() => {const r=document.querySelector(" + JSON.stringify(selector) + ")?.getBoundingClientRect();"
        + "if(!r || !r.width || !r.height)throw new Error('missing clickable control');"
        + "return {x:r.left+r.width/2,y:r.top+r.height/2};})()",
      sessionId,
    );
    await client.send("Input.dispatchMouseEvent", {
      type: "mousePressed", x: box.x, y: box.y, button: "left", buttons: 1, clickCount: 1,
    }, sessionId);
    await client.send("Input.dispatchMouseEvent", {
      type: "mouseReleased", x: box.x, y: box.y, button: "left", buttons: 0, clickCount: 1,
    }, sessionId);
  };
  const clickAndNavigate = async (selector, expectedPath) => {
    const beforeClick = await client.evaluate(
      "(() => {const button=document.querySelector(" + JSON.stringify(selector) + ");"
        + "return {disabled:button?.getAttribute('aria-disabled'),workspace:document.querySelector('#workspace-select')?.value||'',path:location.pathname};})()",
      sessionId,
    );
    assert.equal(beforeClick.disabled, "false", JSON.stringify(beforeClick));
    assert.equal(beforeClick.workspace, expectedPath.split("/")[3], JSON.stringify(beforeClick));
    await pointerClick(selector);
    await client.waitForExpression(
      "location.pathname === " + JSON.stringify(expectedPath)
        + " && document.querySelector('#player-app')?.dataset.state === 'ready'",
      sessionId,
      timeoutMs,
    );
  };
  const fill = (selector, value) => client.evaluate(
    "(() => {const node=document.querySelector(" + JSON.stringify(selector) + ");"
      + "if(!node)throw new Error('missing field');"
      + "node.value=" + JSON.stringify(value) + ";"
      + "node.dispatchEvent(new Event('input',{bubbles:true}));"
      + "node.dispatchEvent(new Event('change',{bubbles:true}));})()",
    sessionId,
  );
  const waitForPost = async (path, expected) => {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const found = completedResponses.filter((entry) => (
        entry.method === "POST" && new URL(entry.url).pathname === path
      ));
      if (found.length >= expected) return found;
      await delay(25);
    }
    throw new Error("missing POST evidence for " + path);
  };
  const postRequests = (path) => [...requests.values()].filter((entry) => (
    entry.method === "POST" && new URL(entry.url).pathname === path
  ));
  const allPostRequestCount = () => [...requests.values()].filter((entry) => entry.method === "POST").length;
  const waitForPostRequest = async (path, expected) => {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const found = postRequests(path);
      if (found.length >= expected) return found;
      await delay(25);
    }
    throw new Error("missing POST request evidence for " + path);
  };
  const waitForCommandEnabled = async (commandId) => {
    const selector = `[data-command-id="${commandId}"]`;
    await client.waitForExpression(
      "document.querySelector(" + JSON.stringify(selector) + ")?.getAttribute('aria-disabled') === 'false'"
        + " && document.querySelector('#player-app')?.dataset.state === 'ready'"
        + " && document.querySelector('#operation-dialog')?.open === false",
      sessionId,
      timeoutMs,
    );
  };
  const assertExactReplay = (fresh, replay) => {
    assert.equal(fresh.status, 201);
    assert.equal(replay.status, 200);
    assert.equal(replay.requestHeaders["idempotency-key"], fresh.requestHeaders["idempotency-key"]);
    assert.equal(replay.requestHeaders["if-match"], fresh.requestHeaders["if-match"]);
    assert.equal(replay.postData, fresh.postData);
    assert.deepEqual(replay.body, fresh.body);
    const receipt = JSON.parse(replay.body.toString("utf8"));
    assert.equal(receipt.operation_id, replay.requestHeaders["idempotency-key"]);
    assert.equal(receipt.manifest_sha256, replay.requestHeaders["if-match"].slice(1, -1));
    return receipt;
  };
  const submitDialog = async ({ code, name, cutoffDate = null }) => {
    await fill("#operation-code", code);
    await fill("#operation-version", "1.0.0");
    await fill("#operation-name", name);
    if (cutoffDate) {
      await fill("#operation-cutoff-date", cutoffDate);
      await fill("#operation-order", "0");
    }
    await click("#operation-submit");
  };
  const pressKey = async (key, {shift = false} = {}) => {
    const options = {
      key,
      code: key,
      modifiers: shift ? 8 : 0,
      windowsVirtualKeyCode: key === "F6" ? 117 : key === "ArrowLeft" ? 37 : 39,
    };
    await client.send("Input.dispatchKeyEvent", {type: "keyDown", ...options}, sessionId);
    await client.send("Input.dispatchKeyEvent", {type: "keyUp", ...options}, sessionId);
  };
  const drag = async (selector, deltaX) => {
    const box = await client.evaluate(
      "(() => {const r=document.querySelector(" + JSON.stringify(selector) + ")?.getBoundingClientRect();"
        + "if(!r)throw new Error('missing splitter');return {x:r.left+r.width/2,y:r.top+r.height/2};})()",
      sessionId,
    );
    await client.send("Input.dispatchMouseEvent", {
      type: "mousePressed", x: box.x, y: box.y, button: "left", buttons: 1, clickCount: 1,
    }, sessionId);
    await client.send("Input.dispatchMouseEvent", {
      type: "mouseMoved", x: box.x + deltaX, y: box.y, button: "left", buttons: 1,
    }, sessionId);
    await client.send("Input.dispatchMouseEvent", {
      type: "mouseReleased", x: box.x + deltaX, y: box.y, button: "left", buttons: 0,
    }, sessionId);
  };
  const assertReloadDisclosure = async (postCountBeforeReload) => {
    const afterReload = await state();
    assert.equal(afterReload.reloadNotice, "true");
    assert.equal(afterReload.playerStateHidden, false);
    assert.match(
      afterReload.stateMessage,
      /^После перезагрузки ключи прежних операций не восстанавливаются/,
    );
    await delay(300);
    assert.equal(allPostRequestCount(), postCountBeforeReload);
    return afterReload;
  };
  const saveScreenshot = async () => {
    if (!screenshotPath) return;
    const image = await client.send("Page.captureScreenshot", { format: "png" }, sessionId);
    await writeFile(screenshotPath, Buffer.from(image.data, "base64"));
  };

  if (scenario === "owner-journey") {
    await navigate(projectUrl);
    let current = await state();
    assert.equal(current.page, "project");
    assert.equal(current.projectId.toLowerCase(), projectId);
    assert.equal(current.claimSha256, expectedClaimSha256);
    assert.deepEqual(current.commandIds, commandIds);
    assert.notEqual(current.reloadNotice, "true");
    assert.ok(!current.enabledCommands.includes("CMD-WORKSPACE-CREATE"));
    assert.equal(current.projectionStatus, "NOT_PROVEN");

    await fill("#definition-select", definitionId);
    await client.waitForExpression(
      "document.querySelector('#definition-select')?.value === " + JSON.stringify(definitionId)
        + " && document.querySelector('[data-command-id=CMD-WORKSPACE-CREATE]')?.getAttribute('aria-disabled') === 'false'",
      sessionId,
      timeoutMs,
    );
    current = await state();
    assert.ok(current.enabledCommands.includes("CMD-WORKSPACE-CREATE"));

    await click('[data-command-id="CMD-WORKSPACE-CREATE"]');
    await client.waitForExpression(
      "document.querySelector('#operation-dialog')?.open === true",
      sessionId,
      timeoutMs,
    );
    await submitDialog({
      code: "PLAYER-WS-" + randomUUID().replaceAll("-", "").slice(0, 12),
      name: "Пространство Chromium",
    });
    await client.waitForExpression(
      "document.querySelector('#player-app')?.dataset.projectionStatus === 'COMPLETE'",
      sessionId,
      timeoutMs,
    );
    current = await state();
    const workspaceId = current.workspaceId?.toLowerCase();
    assert.match(workspaceId || "", /^[0-9a-f-]{36}$/);
    const workspacePosts = await waitForPost(workspaceApi, 1);
    assert.equal(workspacePosts.at(-1).status, 201);
    await client.waitForExpression(
      "document.querySelector('#operation-replay')?.hidden === false",
      sessionId,
      timeoutMs,
    );
    await click("#operation-replay");
    const workspaceReplay = await waitForPost(workspaceApi, 2);
    const workspaceReceipt = assertExactReplay(workspaceReplay.at(-2), workspaceReplay.at(-1));
    assert.equal(workspaceReceipt.workspace_id, workspaceId);
    await waitForCommandEnabled("CMD-WORKSPACE-OPEN");

    await clickAndNavigate(
      '[data-command-id="CMD-WORKSPACE-OPEN"]',
      "/player/workspaces/" + workspaceId + "/",
    );
    current = await state();
    assert.equal(current.page, "workspace");
    assert.equal(current.workspaceId.toLowerCase(), workspaceId);
    assert.equal(current.projectionStatus, "COMPLETE");

    await click('[data-command-id="CMD-SLICE-CREATE"]');
    await client.waitForExpression(
      "document.querySelector('#operation-dialog')?.open === true",
      sessionId,
      timeoutMs,
    );
    await submitDialog({
      code: "PLAYER-SLICE-" + randomUUID().replaceAll("-", "").slice(0, 12),
      name: "Срез Chromium",
      cutoffDate: "2026-01-15",
    });
    const slicePosts = await waitForPost(sliceApi(workspaceId), 1);
    assert.equal(slicePosts.at(-1).status, 201);
    await client.waitForExpression(
      "document.querySelector('#operation-replay')?.hidden === false",
      sessionId,
      timeoutMs,
    );
    await click("#operation-replay");
    const sliceReplay = await waitForPost(sliceApi(workspaceId), 2);
    const sliceReceipt = assertExactReplay(sliceReplay.at(-2), sliceReplay.at(-1));
    const sliceId = String(sliceReceipt.slice_id || sliceReceipt.time_slice_id || "").toLowerCase();
    assert.match(sliceId, /^[0-9a-f-]{36}$/);
    await waitForCommandEnabled("CMD-SLICE-CREATE");

    // A real transport loss must leave one sealed request and no automatic retry.
    await click('[data-command-id="CMD-SLICE-CREATE"]');
    await client.waitForExpression(
      "document.querySelector('#operation-dialog')?.open === true",
      sessionId,
      timeoutMs,
    );
    const transportSliceId = await client.evaluate(
      "document.querySelector('#operation-id')?.value || ''",
      sessionId,
    );
    assert.match(transportSliceId, /^[0-9a-f-]{36}$/);
    await client.send("Network.emulateNetworkConditions", {
      offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0,
    }, sessionId);
    await submitDialog({
      code: "PLAYER-SLICE-LOSS-" + randomUUID().replaceAll("-", "").slice(0, 8),
      name: "Срез после потери транспорта",
      cutoffDate: "2026-01-16",
    });
    await client.waitForExpression(
      "document.querySelector('#operation-replay')?.hidden === false"
        + " && [...document.querySelectorAll('[data-command-id]')].every(node=>node.getAttribute('aria-disabled')==='true')",
      sessionId,
      timeoutMs,
    );
    const lostPosts = await waitForPostRequest(sliceApi(workspaceId), 3);
    const lostSeal = lostPosts.at(-1);
    assert.equal(lostSeal.postData.includes(transportSliceId), true);
    const lostAttemptCount = postRequests(sliceApi(workspaceId)).length;
    await delay(300);
    assert.equal(postRequests(sliceApi(workspaceId)).length, lostAttemptCount);
    await client.send("Network.emulateNetworkConditions", {
      offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1,
    }, sessionId);
    await click("#operation-replay");
    const transportRetry = await waitForPost(sliceApi(workspaceId), 3);
    const recovered = transportRetry.at(-1);
    assert.equal(recovered.status, 201);
    assert.equal(recovered.requestHeaders["idempotency-key"], lostSeal.requestHeaders["idempotency-key"]);
    assert.equal(recovered.requestHeaders["if-match"], lostSeal.requestHeaders["if-match"]);
    assert.equal(recovered.postData, lostSeal.postData);
    const transportReceipt = JSON.parse(recovered.body.toString("utf8"));
    assert.equal(transportReceipt.slice_id, transportSliceId);
    await waitForCommandEnabled("CMD-SLICE-CREATE");

    await navigate(workspaceUrl(workspaceId) + "?slice=" + sliceId);
    current = await state();
    assert.equal(current.workspaceId.toLowerCase(), workspaceId);
    assert.equal(current.projectionStatus, "COMPLETE");
    assert.equal(current.sliceId.toLowerCase(), sliceId);
    assert.equal(current.sliceDate, "2026-01-15");
    const protectedRead = workspaceReadApi(workspaceId);
    const readWithCurrentCookie = () => client.evaluate(
      "fetch(" + JSON.stringify(protectedRead)
        + ",{credentials:'same-origin',headers:{Accept:'application/json'}})"
        + ".then(async r=>({status:r.status,body:await r.text()}))",
      sessionId,
    );
    const anonymous = await client.evaluate(
      "fetch(" + JSON.stringify(protectedRead)
        + ",{credentials:'omit',headers:{Accept:'application/json'}})"
        + ".then(async r=>({status:r.status,body:await r.text()}))",
      sessionId,
    );
    assert.equal(anonymous.status, 401);
    assert.match(anonymous.body, /PLAYER_AUTHENTICATION_REQUIRED/);
    await setSessionCookie(unscopedSessionCookieValue);
    const unscoped = await readWithCurrentCookie();
    assert.equal(unscoped.status, 404);
    assert.match(unscoped.body, /PLAYER_NOT_FOUND/);
    await setSessionCookie(missingPermissionSessionCookieValue);
    const missingPermission = await readWithCurrentCookie();
    assert.equal(missingPermission.status, 403);
    assert.match(missingPermission.body, /PLAYER_PERMISSION_DENIED/);
    await setSessionCookie(staffSessionCookieValue);
    const staff = await readWithCurrentCookie();
    assert.equal(staff.status, 403);
    assert.match(staff.body, /PLAYER_PERMISSION_DENIED/);
    await setSessionCookie(sessionCookieValue);
    console.log(JSON.stringify({
      browser_result: "PASS",
      scenario,
      project_id: projectId,
      definition_id: definitionId,
      workspace_id: workspaceId,
      slice_id: sliceId,
      transport_slice_id: transportSliceId,
      workspace_projection_status: current.projectionStatus,
      slice_cutoff_date: current.sliceDate,
      workspace_receipt_replay_status: workspaceReplay.at(-1).status,
      slice_receipt_replay_status: sliceReplay.at(-1).status,
      transport_retry_status: recovered.status,
      workspace_operation_id: workspaceReceipt.operation_id,
      slice_operation_id: sliceReceipt.operation_id,
      transport_operation_id: transportReceipt.operation_id,
      role_negative_statuses: {
        anonymous: anonymous.status,
        unscoped: unscoped.status,
        missing_permission: missingPermission.status,
        staff: staff.status,
      },
      claim_sha256: expectedClaimSha256,
    }));
  } else if (scenario === "shell-contract") {
    assert.ok(requestedWorkspaceId, "PLAYER_WORKSPACE_ID is required");
    await navigate(workspaceUrl(requestedWorkspaceId));
    let current = await state();
    assert.equal(current.page, "workspace");
    assert.equal(current.workspaceId.toLowerCase(), requestedWorkspaceId);
    assert.equal(current.projectionStatus, "COMPLETE");
    assert.deepEqual(current.commandIds, commandIds);
    assert.equal(current.manifestHash, expectedManifestSha256);
    assert.ok(current.treeTotal > 100);
    assert.equal(current.treeRows, 100);
    assert.ok(current.domNodes < 3000);
    assert.match(current.documentReason, /Доступно после этапа доказательств/);
    assert.match(current.chatReason, /Доступно после этапа чата/);
    assert.equal(current.plusReason, "Доступно после этапа экспериментов");

    const requestCount = requests.size;
    const disabledControls = await client.evaluate(
      "[...document.querySelectorAll('[aria-disabled=\"true\"]')].map(node=>node.id||node.dataset.commandId||node.tagName)",
      sessionId,
    );
    for (const requiredDisabled of ["tab-document", "tab-chat", "experiment-plus", "experiment-create", "structure-mutation"]) {
      assert.ok(disabledControls.includes(requiredDisabled), requiredDisabled);
    }
    await client.evaluate("(() => {for(const node of document.querySelectorAll('[aria-disabled=\"true\"]')){"
      + "node.click();node.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));"
      + "node.dispatchEvent(new KeyboardEvent('keydown',{key:' ',bubbles:true}));}})()", sessionId);
    await delay(300);
    assert.equal(requests.size, requestCount);

    const initialLayout = current;
    await drag("#left-divider", 30);
    current = await state();
    assert.ok(current.left > initialLayout.left);
    await client.evaluate("document.querySelector('#right-divider')?.focus()", sessionId);
    await pressKey("ArrowLeft");
    current = await state();
    assert.ok(current.right > initialLayout.right);
    await client.evaluate("document.querySelector('#left-panel')?.focus()", sessionId);
    await pressKey("F6");
    assert.equal(await client.evaluate("document.activeElement?.id", sessionId), "center-panel");
    await pressKey("F6", {shift: true});
    assert.equal(await client.evaluate("document.activeElement?.id", sessionId), "left-panel");
    const storedLayout = JSON.parse(current.storageRaw);
    assert.deepEqual(Object.keys(storedLayout).sort(), ["activeRightTab", "left", "right", "version"]);
    assert.equal(storedLayout.version, "PLAYER_LAYOUT_V1");
    assert.ok(Number.isInteger(storedLayout.left) && storedLayout.left >= 220 && storedLayout.left <= 420);
    assert.ok(Number.isInteger(storedLayout.right) && storedLayout.right >= 280 && storedLayout.right <= 480);

    await client.evaluate(
      "localStorage.setItem(" + JSON.stringify(storageKey) + ",'{')",
      sessionId,
    );
    const malformedReloadPosts = allPostRequestCount();
    await navigate(workspaceUrl(requestedWorkspaceId), true);
    current = await assertReloadDisclosure(malformedReloadPosts);
    assert.equal(current.storageRaw, null);
    assert.deepEqual(current.storageKeys, []);
    assert.equal(current.left, 272);
    assert.equal(current.right, 320);
    await client.evaluate(
      "localStorage.setItem(" + JSON.stringify(storageKey)
        + ",JSON.stringify({version:'PLAYER_LAYOUT_V1',left:9999,right:-1,activeRightTab:'help'}))",
      sessionId,
    );
    const invalidShapeReloadPosts = allPostRequestCount();
    await navigate(workspaceUrl(requestedWorkspaceId), true);
    current = await assertReloadDisclosure(invalidShapeReloadPosts);
    assert.equal(current.storageRaw, null);
    assert.deepEqual(current.storageKeys, []);
    await click("#context-help");
    await fill("#help-key", "player.workspace");
    await client.waitForExpression(
      "!document.querySelector('#help-topic')?.hidden"
        + " && document.querySelector('#help-identity')?.textContent.includes('PLAYER')",
      sessionId,
      timeoutMs,
    );
    current = await state();
    assert.equal(current.helpVisible, true);
    assert.match(current.helpScope, /PLAYER/);
    const origins = new Set([...requests.values()].map((entry) => new URL(entry.url).origin));
    assert.deepEqual([...origins], [new URL(baseUrl).origin]);
    const structureMutationRequests = [...requests.values()].filter((entry) => (
      entry.method !== "GET" && /(?:actor|element|structure)/i.test(new URL(entry.url).pathname)
    )).length;
    await saveScreenshot();
    console.log(JSON.stringify({
      browser_result: "PASS",
      scenario,
      command_ids: current.commandIds,
      max_tree_rows: current.treeRows,
      tree_total: current.treeTotal,
      storage_key: storageKey,
      storage_shape_validated: true,
      splitter_pointer_and_keyboard_validated: true,
      f6_focus_cycle_validated: true,
      document_network_silent: true,
      chat_network_silent: true,
      off_origin_free: true,
      structure_mutation_requests: structureMutationRequests,
      help_scope: "PLAYER",
    }));
  } else {
    throw new Error("unsupported PLAYER_SCENARIO: " + scenario);
  }
} finally {
  await browser.close();
}
