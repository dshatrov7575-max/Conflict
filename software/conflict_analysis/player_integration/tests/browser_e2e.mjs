import assert from "node:assert/strict";
import { launchChromium } from "../../production_studio/browser_tests/cdp_client.mjs";

const base = process.env.PR2_BASE_URL;
const lanes = JSON.parse(process.env.PR2_LANES);
const browser = await launchChromium({ timeoutMs: 30_000 });
const origins = new Set();
const failures = [];
let sessionId;
try {
  const client = browser.client;
  const target = await client.send("Target.createTarget", { url: "about:blank" });
  ({ sessionId } = await client.send("Target.attachToTarget", { targetId: target.targetId, flatten: true }));
  await Promise.all(["Page", "Runtime", "Network"].map(name => client.send(`${name}.enable`, {}, sessionId)));
  client.on("Network.requestWillBeSent", (event, sid) => {
    if (sid === sessionId && /^https?:/.test(event.request.url)) origins.add(new URL(event.request.url).origin);
  });
  client.on("Network.responseReceived", (event, sid) => {
    if (sid === sessionId && event.response.status >= 400 && !event.response.url.endsWith("/favicon.ico")) {
      failures.push({ url: event.response.url, status: event.response.status });
    }
  });
  const cookie = await client.send("Network.setCookie", {
    name: process.env.PR2_SESSION_COOKIE_NAME, value: process.env.PR2_SESSION_COOKIE_VALUE,
    url: `${base}/`, httpOnly: true, sameSite: "Lax",
  }, sessionId);
  assert.equal(cookie.success, true);
  const evaluate = expression => client.evaluate(expression, sessionId);
  const wait = expression => client.waitForExpression(expression, sessionId);
  for (const lane of lanes) {
    await client.send("Page.navigate", { url: `${base}/player/calculations/` }, sessionId);
    await wait("document.querySelector('input[name=experiment_id]') !== null");
    await evaluate(`(() => {
      document.querySelector('input[name=experiment_id]').value = ${JSON.stringify(lane.weights.experiment_id)};
      document.querySelector('button[type=submit]').click();
      return true;
    })()`);
    await wait(`Array.from(document.querySelectorAll('a')).some(a => a.pathname === ${JSON.stringify(lane.path)})`);
    await evaluate(`Array.from(document.querySelectorAll('a')).find(a => a.pathname === ${JSON.stringify(lane.path)}).click(); true`);
    await wait("document.querySelector('input[name=csrfmiddlewaretoken]') !== null");
    // Native form navigation, including the browser's real CSRF cookie and token.
    await evaluate(`(() => {
      const weights = ${JSON.stringify(lane.weights)};
      for (const group of ['rgu', 'kvptn']) {
        for (const [id, input] of Object.entries(weights[group])) {
          for (const [name, value] of Object.entries(input)) {
            document.getElementsByName(group + '.' + id + '.' + name)[0].value = value ?? '';
          }
        }
      }
      document.querySelector('button[type=submit]').click();
      return true;
    })()`);
    await wait("document.querySelector('[data-testid=uno]') !== null");
    const result = await evaluate(`(() => ({
      uno: document.querySelector('[data-testid=uno]').textContent,
      kind: document.querySelector('[data-testid=assessment-kind]').textContent,
      snapshot: JSON.parse(document.querySelector('#snapshot-json').value),
      run: JSON.parse(document.querySelector('#run-json').value),
      local: Object.keys(localStorage), session: Object.keys(sessionStorage),
      styled: getComputedStyle(document.body).margin === '0px',
    }))()`);
    assert.equal(result.uno, lane.expected);
    assert.equal(result.kind, lane.kind);
    assert.equal(result.snapshot.experiment_id, lane.weights.experiment_id);
    assert.equal(result.snapshot.time_slice_id, lane.weights.time_slice_id);
    assert.equal(result.run.snapshot_id, result.snapshot.id);
    assert.equal(result.run.UNO, lane.expected);
    assert.equal(result.styled, true);
    assert.deepEqual(result.local, []);
    assert.deepEqual(result.session, []);
  }
  // Untouched UNKNOWN fields must submit successfully and display missingness.
  await client.send("Page.navigate", { url: base + lanes[0].path }, sessionId);
  await wait("document.querySelector('input[name=csrfmiddlewaretoken]') !== null");
  await evaluate("document.querySelector('button[type=submit]').click(); true");
  await wait("document.querySelector('[data-testid=uno]') !== null");
  assert.equal(await evaluate("document.querySelector('[data-testid=uno]').textContent"), "Недостаточно данных");
  assert.deepEqual([...origins], [new URL(base).origin]);
  assert.deepEqual(failures, []);
  console.log(JSON.stringify({ status: "PASS", lanes: lanes.map(lane => lane.kind), same_origin_only: true }));
} finally {
  if (sessionId) await browser.client.send("Target.detachFromTarget", { sessionId }).catch(() => {});
  await browser.close();
}
