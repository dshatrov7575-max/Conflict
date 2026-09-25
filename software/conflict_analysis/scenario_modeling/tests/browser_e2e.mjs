import assert from "node:assert/strict";
import { writeFile } from "node:fs/promises";
import path from "node:path";
import { launchChromium } from "../../production_studio/browser_tests/cdp_client.mjs";

const base = process.env.PR3_BASE_URL;
const weights = JSON.parse(process.env.PR3_WEIGHTS);
const parameter = process.env.PR3_PARAMETER;
const browser = await launchChromium({ timeoutMs: 30_000 });
const failures = [];
const origins = new Set();
let sessionId;
try {
  const client = browser.client;
  const target = await client.send("Target.createTarget", { url: "about:blank" });
  ({ sessionId } = await client.send("Target.attachToTarget", { targetId: target.targetId, flatten: true }));
  await Promise.all(["Page", "Runtime", "Network", "Log"].map(name => client.send(`${name}.enable`, {}, sessionId)));
  client.on("Network.requestWillBeSent", (event, sid) => {
    if (sid === sessionId && /^https?:/.test(event.request.url)) origins.add(new URL(event.request.url).origin);
  });
  client.on("Network.responseReceived", (event, sid) => {
    if (sid === sessionId && event.response.status >= 400 && !event.response.url.endsWith("/favicon.ico")) {
      failures.push(event.response.url);
    }
  });
  client.on("Runtime.exceptionThrown", (event, sid) => { if (sid === sessionId) failures.push(event.exceptionDetails.text); });
  client.on("Log.entryAdded", (event, sid) => {
    if (sid === sessionId && event.entry.source === "security" && event.entry.level === "error") failures.push(event.entry.text);
  });
  const cookie = await client.send("Network.setCookie", {
    name: process.env.PR3_COOKIE_NAME, value: process.env.PR3_COOKIE_VALUE,
    url: `${base}/`, httpOnly: true, sameSite: "Lax",
  }, sessionId);
  assert.equal(cookie.success, true);
  const evaluate = expression => client.evaluate(expression, sessionId);
  const wait = expression => client.waitForExpression(expression, sessionId);
  const click = async selector => {
    await evaluate(`document.querySelector(${JSON.stringify(selector)}).click(); true`);
  };
  await client.send("Page.navigate", { url: base + process.env.PR3_PATH }, sessionId);
  await wait("document.querySelector('input[name=csrfmiddlewaretoken]') !== null");
  await evaluate(`(() => {
    const weights = ${JSON.stringify(weights)};
    for (const group of ['rgu', 'kvptn']) for (const [id, input] of Object.entries(weights[group])) {
      for (const [name, value] of Object.entries(input)) document.getElementsByName(group + '.' + id + '.' + name)[0].value = value ?? '';
    }
    document.querySelector('button[type=submit]').click(); return true;
  })()`);
  await wait("document.querySelector('[data-testid=create-scenario]') !== null");
  const baseline = await evaluate("JSON.parse(document.querySelector('#snapshot-json').value)");
  await click("[data-testid=create-scenario]");
  await wait("document.querySelector('#slider-controls')?.hidden === false");
  assert.equal(await evaluate("document.querySelector('[data-testid=baseline-uno]').textContent"), "100");
  const modelBaseline = await evaluate("JSON.parse(document.querySelector('#model-json').value).baseline");
  assert.deepEqual(modelBaseline, baseline);
  await evaluate(`(() => {
    const select = document.querySelector('#id_parameter'); select.value = ${JSON.stringify(parameter)};
    select.dispatchEvent(new Event('change', { bubbles: true }));
    const number = document.querySelector('#id_value'); number.value = '5';
    number.dispatchEvent(new Event('input', { bubbles: true })); return true;
  })()`);
  assert.equal(await evaluate("document.querySelector('#scenario-slider').value"), "5");
  await click("[data-testid=apply-override]");
  await wait("document.querySelector('[data-testid=scenario-uno]')?.textContent === '50'");
  assert.equal(await evaluate("document.querySelector('[data-testid=delta-uno]').textContent"), "-50");
  await wait("document.querySelector('#slider-controls')?.hidden === false");
  await evaluate(`(() => {
    const slider = document.querySelector('#scenario-slider'); slider.value = '0';
    slider.dispatchEvent(new Event('input', { bubbles: true })); return true;
  })()`);
  assert.equal(await evaluate("document.querySelector('#id_value').value"), "0");
  await click("[data-testid=apply-override]");
  await wait("document.querySelector('[data-testid=scenario-uno]')?.textContent === '0'");
  assert.equal(await evaluate("document.querySelector('[data-testid=delta-uno]').textContent"), "-100");
  const run = await evaluate("document.querySelector('#scenario-run-json').value");
  await evaluate("document.documentElement.dataset.beforeReplay = 'yes'; true");
  await click("[data-testid=recalculate]");
  await wait("document.querySelector('[data-testid=scenario-uno]') && !document.documentElement.dataset.beforeReplay");
  assert.equal(await evaluate("document.querySelector('#scenario-run-json').value"), run);
  assert.deepEqual(await evaluate("JSON.parse(document.querySelector('#model-json').value).baseline"), baseline);
  // Responsive layout and snapshots for visual review.
  for (const [name, width, height] of [["desktop", 1280, 1000], ["mobile", 390, 844]]) {
    await client.send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: name === "mobile" }, sessionId);
    await wait(`window.innerWidth === ${width}`);
    assert.equal(await evaluate("document.documentElement.scrollWidth <= window.innerWidth"), true);
    assert.equal(await evaluate("getComputedStyle(document.querySelector('.scenario-metrics')).display"), "grid");
    const shot = await client.send("Page.captureScreenshot", { format: "png" }, sessionId);
    await writeFile(path.join(process.env.PR3_ARTIFACTS, `${name}.png`), Buffer.from(shot.data, "base64"));
  }
  await click("table[data-testid=changes] button[name=parameter]");
  await wait("document.querySelector('[data-testid=no-changes]') !== null");
  assert.equal(await evaluate("document.querySelector('[data-testid=scenario-uno]').textContent"), "100");
  await wait("document.querySelector('#slider-controls')?.hidden === false");
  await evaluate(`(() => {
    const select = document.querySelector('#id_parameter'); select.value = ${JSON.stringify(parameter)};
    select.dispatchEvent(new Event('change', { bubbles: true }));
    document.querySelector('#id_value').value = '5'; return true;
  })()`);
  await click("[data-testid=apply-override]");
  await wait("document.querySelector('[data-testid=scenario-uno]')?.textContent === '50'");
  await click("[data-testid=reset]");
  await wait("document.querySelector('[data-testid=no-changes]') !== null");
  assert.equal(await evaluate("document.querySelector('[data-testid=scenario-uno]').textContent"), "100");
  assert.deepEqual(await evaluate("[Object.keys(localStorage), Object.keys(sessionStorage)]"), [[], []]);
  assert.deepEqual([...origins], [new URL(base).origin]);
  assert.deepEqual(failures, []);
  console.log(JSON.stringify({ status: "PASS", slider: true, deterministic_replay: true, baseline_preserved: true, responsive: true }));
} finally {
  if (sessionId) await browser.client.send("Target.detachFromTarget", { sessionId }).catch(() => {});
  await browser.close();
}
