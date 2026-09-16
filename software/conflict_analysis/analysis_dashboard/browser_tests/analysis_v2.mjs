import assert from "node:assert/strict";
import { launchChromium } from "../../production_studio/browser_tests/cdp_client.mjs";

const required = (name) => {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
};
const base = required("ANALYSIS_BASE_URL").replace(/\/$/, "");
const project = required("ANALYSIS_PROJECT_ID");
const workspace = required("ANALYSIS_WORKSPACE_ID");
const cookieName = required("ANALYSIS_SESSION_COOKIE_NAME");
const cookieValue = required("ANALYSIS_SESSION_COOKIE_VALUE");
const timeout = Number(process.env.ANALYSIS_CDP_TIMEOUT_MS || "60000");
const viewports = [[1024, 768, 4], [1366, 768, 7], [1920, 1080, 7]];
const browser = await launchChromium({timeoutMs: timeout});
let sessionId;
const origins = new Set();

try {
  const client = browser.client;
  const created = await client.send("Target.createTarget", {url: "about:blank"});
  const attached = await client.send("Target.attachToTarget", {targetId: created.targetId, flatten: true});
  sessionId = attached.sessionId;
  await Promise.all([
    client.send("Page.enable", {}, sessionId),
    client.send("Runtime.enable", {}, sessionId),
    client.send("Network.enable", {}, sessionId),
  ]);
  client.on("Network.requestWillBeSent", (event, sid) => {
    if (sid === sessionId && /^https?:/.test(event.request.url)) {
      origins.add(new URL(event.request.url).origin);
    }
  });
  const set = await client.send("Network.setCookie", {
    name: cookieName,
    value: cookieValue,
    url: `${base}/`,
    httpOnly: true,
    sameSite: "Lax",
  }, sessionId);
  assert.equal(set.success, true);

  for (const [width, height, minimumRows] of viewports) {
    await client.send("Emulation.setDeviceMetricsOverride", {
      width, height, deviceScaleFactor: 1, mobile: false,
    }, sessionId);
    await client.send("Page.navigate", {
      url: `${base}/analysis/projects/${project}/workspaces/${workspace}/`,
    }, sessionId);
    await client.waitForExpression(
      "document.querySelector('#analysis-app')?.dataset.state==='ready'",
      sessionId,
      timeout,
    );
    const result = await client.evaluate(`(() => {
      const chart = document.querySelector('#chart').getBoundingClientRect();
      const rows = [...document.querySelectorAll('#timeline-table tbody tr')];
      const visible = rows.filter(row => {
        const rect = row.getBoundingClientRect();
        return rect.top < innerHeight && rect.bottom > 0;
      }).length;
      return {
        chart: chart.height,
        total: rows.length,
        visible,
        noRecord: rows.filter(row => row.children[3]?.textContent === 'NO_RECORD').length,
        fractionalValues: rows.map(row => row.children[2]?.textContent?.trim()).filter(Boolean),
        title: document.querySelector('#chart-title')?.textContent || '',
        scroll: document.documentElement.scrollWidth > innerWidth,
        storage: Object.keys(localStorage),
      };
    })()` , sessionId);
    assert.ok(result.chart > 120);
    assert.ok(result.total >= minimumRows, `fixture has ${result.total}, expected at least ${minimumRows}`);
    assert.ok(result.visible >= minimumRows, `visible ${result.visible}, expected ${minimumRows}`);
    assert.ok(result.noRecord > 0, "NO_RECORD must remain visible");
    for (const expected of ["0.000001", "1e-7", "-0.000001", "1.25"]) {
      assert.ok(
        result.fractionalValues.includes(expected),
        `fractional canonical response did not render ${expected}: ${result.fractionalValues}`,
      );
    }
    assert.match(result.title, /GU-\d{2}/, "actor identity is missing from chart title");
    assert.equal(result.scroll, false);
    assert.ok(result.storage.every(key => key.startsWith("conflict-analysis:analysis-layout:v1:")));
    assert.equal(result.storage.includes("conflict-analysis-player:layout:v1"), false);
  }

  // Corrupted/stale local preferences must be clamped before use.
  await client.evaluate(`(() => {
    const key = Object.keys(localStorage).find(item => item.startsWith('conflict-analysis:analysis-layout:v1:'));
    localStorage.setItem(key, JSON.stringify({version:'ANALYSIS_LAYOUT_V1',graph_height:99999,list_height:-5,sidebar_width:'bad',font_scale:99,fit_graph_and_list:false,unexpected:true}));
    location.reload();
    return true;
  })()`, sessionId);
  await client.waitForExpression(
    "document.querySelector('#analysis-app')?.dataset.state==='ready'",
    sessionId,
    timeout,
  );
  const clamped = await client.evaluate(`(() => {
    const style = getComputedStyle(document.documentElement);
    return {
      graph: parseFloat(style.getPropertyValue('--chart-height')),
      list: parseFloat(style.getPropertyValue('--list-height')),
      sidebar: parseFloat(style.getPropertyValue('--sidebar-width')),
      font: parseFloat(style.getPropertyValue('--font-scale')),
    };
  })()`, sessionId);
  assert.ok(clamped.graph >= 180 && clamped.graph <= 720);
  assert.ok(clamped.list >= 130 && clamped.list <= 600);
  assert.ok(clamped.sidebar >= 150 && clamped.sidebar <= 300);
  assert.equal(clamped.sidebar, 190, 'unexpected layout keys must reset the profile');
  assert.equal(clamped.font, 1, 'unexpected layout keys must reset the profile');

  // A storage quota/privacy failure must not break live presentation controls.
  const storageFailure = await client.evaluate(`(() => {
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = () => { throw new DOMException('blocked', 'QuotaExceededError'); };
    try {
      const input = document.querySelector('#font-scale');
      input.value = '110';
      input.dispatchEvent(new Event('input', {bubbles:true}));
      return {
        font: parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--font-scale')),
        state: document.querySelector('#analysis-app').dataset.state,
      };
    } finally {
      Storage.prototype.setItem = original;
    }
  })()`, sessionId);
  assert.equal(storageFailure.font, 1.1);
  assert.equal(storageFailure.state, 'ready');

  // Delay the first request, then change actor. A late response must never
  // overwrite the newer visible selection.
  await client.evaluate(`(() => {
    const original = window.fetch.bind(window);
    let delayed = true;
    window.fetch = async (...args) => {
      const url = String(args[0]);
      const response = await original(...args);
      if (delayed && url.includes('/timeline/')) {
        delayed = false;
        await new Promise(resolve => setTimeout(resolve, 650));
      }
      return response;
    };
    const actor = document.querySelector('#actor-select');
    actor.selectedIndex = 0;
    document.querySelector('#apply-selection').click();
    actor.selectedIndex = 1;
    actor.dispatchEvent(new Event('change', {bubbles:true}));
    document.querySelector('#apply-selection').click();
    return actor.value;
  })()`, sessionId);
  await client.waitForExpression(
    "document.querySelector('#chart-title')?.textContent.includes(document.querySelector('#actor-select')?.value)",
    sessionId,
    timeout,
  );
  await new Promise(resolve => setTimeout(resolve, 900));
  const race = await client.evaluate(`(() => ({
    actor: document.querySelector('#actor-select').value,
    title: document.querySelector('#chart-title').textContent,
    state: document.querySelector('#analysis-app').dataset.state,
  }))()`, sessionId);
  assert.ok(race.title.includes(race.actor));
  assert.equal(race.state, "ready");

  // Evidence list and evidence-detail lanes must also reject stale responses.
  const evidenceRace = await client.evaluate(`(async () => {
    const original = window.fetch.bind(window);
    let listCall = 0;
    let detailCall = 0;
    window.fetch = async (...args) => {
      const url = String(args[0]);
      if (url.includes('/parameter-values/') && url.endsWith('/facts/')) {
        listCall += 1;
        const valueId = url.match(/parameter-values\/([^/]+)\/facts\/$/)?.[1] || 'unknown';
        const response = new Response(JSON.stringify({facts:[{
          id: '00000000-0000-4000-8000-00000000000' + listCall,
          code: 'FACT-' + valueId,
          statement: 'value=' + valueId,
        }]}), {status:200, headers:{'Content-Type':'application/json; charset=utf-8'}});
        if (listCall === 1) await new Promise(resolve => setTimeout(resolve, 650));
        return response;
      }
      if (url.includes('/facts/') && url.endsWith('/evidence/')) {
        detailCall += 1;
        const response = new Response(JSON.stringify({marker:'DETAIL-' + detailCall}), {
          status:200, headers:{'Content-Type':'application/json; charset=utf-8'},
        });
        if (detailCall === 1) await new Promise(resolve => setTimeout(resolve, 650));
        return response;
      }
      return original(...args);
    };
    const rows = [...document.querySelectorAll('#timeline-table tbody tr[data-value-id]')];
    if (rows.length < 3) throw new Error('at least three persisted rows are required');
    const first = rows[0].dataset.valueId;
    const second = rows[1].dataset.valueId;
    const third = rows[2].dataset.valueId;
    rows[0].click();
    rows[1].click();
    const deadline = Date.now() + 5000;
    while (!document.querySelector('#fact-list button')?.textContent.includes(second)) {
      if (Date.now() > deadline) throw new Error('second evidence list did not render');
      await new Promise(resolve => setTimeout(resolve, 25));
    }
    await new Promise(resolve => setTimeout(resolve, 900));
    const listText = document.querySelector('#fact-list')?.textContent || '';
    if (!listText.includes(second) || listText.includes(first)) {
      throw new Error('stale evidence list overwrote current selection');
    }
    document.querySelector('#fact-list button').click();
    rows[2].click();
    await new Promise(resolve => setTimeout(resolve, 900));
    const detailText = document.querySelector('#evidence-detail')?.textContent || '';
    const currentList = document.querySelector('#fact-list')?.textContent || '';
    return {first, second, third, listText, currentList, detailText};
  })()`, sessionId);
  assert.ok(evidenceRace.currentList.includes(evidenceRace.third));
  assert.equal(evidenceRace.detailText.includes('DETAIL-1'), false);

  // Remove the session and require an explicit visible access message.
  await client.send("Network.deleteCookies", {name: cookieName, url: `${base}/`}, sessionId);
  await client.send("Page.navigate", {
    url: `${base}/analysis/projects/${project}/workspaces/${workspace}/`,
  }, sessionId);
  await client.waitForExpression(
    "document.querySelector('#analysis-app')?.dataset.state==='unauthorized' && document.querySelector('#auth-panel')?.hidden===false",
    sessionId,
    timeout,
  );

  assert.deepEqual([...origins], [new URL(base).origin]);
  console.log(JSON.stringify({
    browser_result: "PASS",
    viewports,
    off_origin_free: true,
    no_record_visible: true,
    fractional_canonical: true,
    late_response_guard: true,
    layout_clamped: true,
    layout_storage_failure_tolerated: true,
    evidence_late_response_guard: true,
    unauthorized_message: true,
  }));
} finally {
  if (sessionId) {
    await browser.client.send("Target.detachFromTarget", {sessionId}).catch(() => {});
  }
  await browser.close();
}
