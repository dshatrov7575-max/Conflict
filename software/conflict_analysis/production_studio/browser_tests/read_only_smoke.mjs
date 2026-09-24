import assert from "node:assert/strict";
import { createHash } from "node:crypto";

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
const expectedProjectMetadata = requiredEnvironment("STUDIO_EXPECTED_PROJECT_METADATA");
const timeoutMs = Number(process.env.STUDIO_CDP_TIMEOUT_MS || "45000");
const definitionUrl = `${baseUrl}/studio/definitions/${definitionId}/`;
const expectedOpenPath = `/api/foundation/definitions/${definitionId}/`;
const expectedExportPath = `${expectedOpenPath}package/2.1/`;
const storageKey = "conflict-analysis-studio:read-only-layout:v1";

const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");
const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

const normalizedHeaders = (headers) => Object.fromEntries(
  Object.entries(headers || {}).map(([name, value]) => [name.toLowerCase(), String(value)]),
);

const browser = await launchChromium({ timeoutMs });
let client;
let sessionId;
const requests = [];
const responses = new Map();
const exportBodies = [];
const bodyFailures = [];

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

  client.on("Network.requestWillBeSent", (event, eventSessionId) => {
    if (eventSessionId !== sessionId || !/^https?:/.test(event.request.url)) return;
    requests.push({
      requestId: event.requestId,
      method: event.request.method,
      url: event.request.url,
      type: event.type,
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
  client.on("Network.loadingFinished", (event, eventSessionId) => {
    if (eventSessionId !== sessionId) return;
    const response = responses.get(event.requestId);
    if (!response || new URL(response.url).pathname !== expectedExportPath) return;
    client.send("Network.getResponseBody", { requestId: event.requestId }, sessionId)
      .then(({ body, base64Encoded }) => {
        exportBodies.push({
          bytes: Buffer.from(body, base64Encoded ? "base64" : "utf8"),
          ...response,
        });
      })
      .catch((error) => bodyFailures.push(String(error)));
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
    await client.waitForExpression(
      "document.querySelector('#studio-app')?.dataset.state === 'ready'",
      sessionId,
      timeoutMs,
    );
  };

  const inspectPage = () => client.evaluate(`(async () => {
    const app = document.querySelector("#studio-app");
    const rawLayout = localStorage.getItem(${JSON.stringify(storageKey)});
    const projectSnapshot = Object.fromEntries(
      [...document.querySelectorAll("#project-snapshot > div")].map((item) => [
        item.querySelector("dt")?.textContent,
        item.querySelector("dd")?.textContent,
      ]),
    );
    return {
      state: app?.dataset.state,
      definitionId: app?.dataset.definitionId,
      claimSha256: app?.dataset.claimSha256,
      manifestSha256: document.querySelector("#manifest-sha")?.textContent,
      manifestEtag: document.querySelector("#manifest-etag")?.textContent,
      publicationStatus: document.querySelector("#publication-status")?.textContent,
      actorCount: Number(document.querySelector("#actor-count")?.textContent),
      elementCount: Number(document.querySelector("#element-count")?.textContent),
      rowCount: document.querySelectorAll("#manifest-window [data-manifest-row]").length,
      totalDomNodes: document.getElementsByTagName("*").length,
      crossCells: document.querySelectorAll("[data-actor-id][data-element-id]").length,
      permanentClaims: [...document.querySelectorAll("#studio-limitations [data-claim-code]")].map(
        (node) => node.dataset.claimCode,
      ),
      hasBanner: Boolean(document.querySelector("#studio-boundary-banner")),
      hasNoscriptBoundary: Boolean(document.querySelector("noscript")),
      unknownFacts: [...document.querySelectorAll(".unknown-grid dd")].map((node) => node.textContent),
      documentUnavailable: document.querySelector('[data-state="DOCUMENT_UNAVAILABLE"]')?.dataset.explicitUnavailable,
      chatUnavailable: Boolean(document.querySelector('[data-state="CHAT_UNAVAILABLE"]')),
      chatDisabled: Boolean(document.querySelector("#panel-chat button:disabled")),
      helpState: document.querySelector("#help-state")?.dataset.state,
      helpVisible: !document.querySelector("#help-topic")?.hidden,
      helpOptionCount: document.querySelectorAll("#help-binding-select option").length,
      projectMetadata: projectSnapshot.metadata,
      layoutRaw: rawLayout,
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

  await navigateAndWait();
  let page = await inspectPage();
  assert.equal(page.state, "ready");
  assert.equal(page.definitionId.toLowerCase(), definitionId);
  assert.equal(page.claimSha256, expectedClaimSha256);
  assert.equal(page.manifestSha256, expectedManifestSha256);
  assert.equal(page.manifestEtag, `"${expectedManifestSha256}"`);
  assert.match(page.publicationStatus, /^(DRAFT|VALIDATED|PUBLISHED|RETIRED)$/);
  assert.ok(page.actorCount > 500, `actor cardinality was ${page.actorCount}`);
  assert.ok(page.elementCount > 500, `element cardinality was ${page.elementCount}`);
  assert.ok(page.rowCount > 0 && page.rowCount <= 100, `active rows were ${page.rowCount}`);
  assert.ok(page.totalDomNodes < 3_000, `DOM expanded to ${page.totalDomNodes} nodes`);
  assert.equal(page.crossCells, 0, "actor x element cells were allocated");
  assert.deepEqual(page.permanentClaims, [
    "STATUS",
    "AUTHORITY",
    "TRACEABILITY",
    "SCIENTIFIC_STATUS",
    "UNAVAILABLE_FUNCTIONS",
    "EXPORT_STATUS",
    "BASELINE_SEPARATION",
    "DISTINCT_VALUES",
    "NO_PSEUDO_AGGREGATION",
  ]);
  assert.equal(page.hasBanner, true);
  assert.equal(page.hasNoscriptBoundary, true);
  assert.deepEqual(page.unknownFacts, Array(4).fill("UNKNOWN_NOT_EXPOSED_BY_FOUNDATION"));
  assert.equal(page.documentUnavailable, "true");
  assert.equal(page.chatUnavailable, true);
  assert.equal(page.chatDisabled, true);
  assert.equal(page.helpState, "HELP_READY");
  assert.equal(page.helpVisible, true);
  assert.equal(page.helpOptionCount, 1, "Help bindings expanded into an unbounded selector");
  assert.equal(page.projectMetadata, expectedProjectMetadata);

  await client.evaluate(`document.querySelector('[data-manifest-dataset="analytical-elements"]').click()`, sessionId);
  page = await inspectPage();
  assert.ok(page.rowCount > 0 && page.rowCount <= 100);
  assert.ok(page.totalDomNodes < 3_000);
  await client.evaluate(`document.querySelector('#window-next').click()`, sessionId);
  page = await inspectPage();
  assert.equal(page.rowCount, 100);
  assert.ok(page.totalDomNodes < 3_000);

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
    version: "STUDIO_READ_ONLY_LAYOUT_V1",
    left: 300,
    right: 400,
    activeRightTab: "help",
  });
  assert.ok(Buffer.byteLength(page.layoutRaw, "utf8") <= 256);
  assert.equal(page.layoutRaw.includes(definitionId), false);

  for (const invalid of [
    "{",
    "x".repeat(257),
    `{"version":"${definitionId}","version":"STUDIO_READ_ONLY_LAYOUT_V1","left":272,"right":360,"activeRightTab":"document"}`,
    JSON.stringify({
      version: "STUDIO_READ_ONLY_LAYOUT_V1",
      left: 219,
      right: 501,
      activeRightTab: "scientific",
    }),
  ]) {
    await client.evaluate(
      `localStorage.setItem(${JSON.stringify(storageKey)}, ${JSON.stringify(invalid)})`,
      sessionId,
    );
    await navigateAndWait({ reload: true });
    page = await inspectPage();
    assert.equal(page.layoutRaw, null, "invalid layout was not removed");
    assert.deepEqual(page.localStorageKeys, []);
    assert.equal(page.left, 272);
    assert.equal(page.right, 360);
    assert.equal(page.activeRightTab, "document");
  }

  const acceptedLayout = JSON.stringify({
    version: "STUDIO_READ_ONLY_LAYOUT_V1",
    left: 300,
    right: 400,
    activeRightTab: "help",
  });
  await client.evaluate(
    `localStorage.setItem(${JSON.stringify(storageKey)}, ${JSON.stringify(acceptedLayout)})`,
    sessionId,
  );
  await navigateAndWait({ reload: true });
  page = await inspectPage();
  assert.equal(page.layoutRaw, acceptedLayout);
  assert.deepEqual(page.localStorageKeys, [storageKey]);
  assert.equal(page.left, 300);
  assert.equal(page.right, 400);
  assert.equal(page.activeRightTab, "help");
  assert.equal(page.sessionStorageLength, 0);
  assert.deepEqual(page.indexedDbNames, []);
  assert.deepEqual(page.cacheNames, []);
  assert.equal(page.serviceWorkers, 0);

  const clickExportAndWait = async (expectedCount) => {
    await client.evaluate(`document.querySelector("#export-foundation").click()`, sessionId);
    await client.waitForExpression(
      `/^[0-9a-f]{64}$/.test(document.querySelector("#export-representation-sha")?.textContent || "")`,
      sessionId,
      timeoutMs,
    );
    const deadline = Date.now() + timeoutMs;
    while (exportBodies.length < expectedCount && Date.now() < deadline) await delay(25);
    assert.equal(bodyFailures.length, 0, bodyFailures.join("\n"));
    assert.ok(exportBodies.length >= expectedCount, `captured only ${exportBodies.length} export bodies`);
  };
  await clickExportAndWait(1);
  await clickExportAndWait(2);
  const [firstExport, secondExport] = exportBodies.slice(-2);
  assert.deepEqual(secondExport.bytes, firstExport.bytes, "export retry bytes changed");
  assert.equal(firstExport.bytes.at(-1), 0x0a, "export has no terminal LF");
  assert.notEqual(firstExport.bytes.at(-2), 0x0a, "export has more than one terminal LF");
  assert.notEqual(firstExport.bytes.at(-2), 0x0d, "export uses CRLF instead of one terminal LF");
  const representationSha = sha256(firstExport.bytes);
  assert.equal(firstExport.headers.etag, `"${representationSha}"`);
  assert.equal(secondExport.headers.etag, firstExport.headers.etag);
  assert.equal(
    firstExport.headers["content-disposition"],
    `attachment; filename="foundation-definition-${definitionId}-2.1.json"`,
  );
  const packageDocument = JSON.parse(firstExport.bytes.toString("utf8"));
  assert.equal(packageDocument.format, "conflict-analysis-foundation");
  assert.equal(packageDocument.format_version, "2.1.0");
  assert.equal(
    firstExport.headers["x-foundation-semantic-payload-sha256"],
    packageDocument.manifest.payload_sha256,
  );

  const httpRequests = requests.filter((item) => /^https?:/.test(item.url));
  assert.ok(httpRequests.length > 0);
  assert.deepEqual([...new Set(httpRequests.map((item) => item.method))], ["GET"]);
  assert.equal(httpRequests.some((item) => /\/(?:login|logout|signup|password)(?:\/|\?|$)/i.test(item.url)), false);
  const foundationRequests = httpRequests.filter((item) => new URL(item.url).pathname.startsWith("/api/foundation/"));
  assert.ok(foundationRequests.some((item) => new URL(item.url).pathname === expectedOpenPath));
  assert.ok(foundationRequests.filter((item) => new URL(item.url).pathname === expectedExportPath).length >= 2);
  for (const request of foundationRequests) {
    const url = new URL(request.url);
    const allowed =
      url.pathname === expectedOpenPath
      || url.pathname === expectedExportPath
      || url.pathname === "/api/foundation/help/studio.welcome/";
    assert.equal(allowed, true, `unexpected Foundation request ${url}`);
    if (url.pathname === "/api/foundation/help/studio.welcome/") {
      assert.equal(url.search, "?application=STUDIO&locale=ru&version=1.0.0");
    } else {
      assert.equal(url.search, "");
    }
  }
  for (const response of responses.values()) {
    if (/^https?:/.test(response.url)) {
      assert.ok(response.status < 400, `${response.status} ${response.url}`);
    }
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
    foundation_gets: foundationRequests.length,
    methods: [...new Set(httpRequests.map((item) => item.method))],
    max_active_rows: 100,
    observed_actor_count: page.actorCount,
    observed_element_count: page.elementCount,
    observed_help_binding_options: page.helpOptionCount,
    export_representation_sha256: representationSha,
    claim_contract_sha256: expectedClaimSha256,
    storage_key: storageKey,
  }));
} finally {
  await browser.close();
}
