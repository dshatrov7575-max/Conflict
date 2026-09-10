import assert from "node:assert/strict";
import { launchChromium } from "../../production_studio/browser_tests/cdp_client.mjs";

const required = name => { const value = process.env[name]; if (!value) throw new Error(`${name} is required`); return value; };
const base = required("PLAYER_BASE_URL").replace(/\/$/, "");
const workspace = required("PLAYER_WORKSPACE_ID");
const cookieName = required("PLAYER_SESSION_COOKIE_NAME");
const cookieValue = required("PLAYER_SESSION_COOKIE_VALUE");
const scenario = required("PLAYER_G9_SCENARIO");
const visibleExperiment = required("PLAYER_VISIBLE_EXPERIMENT_ID");
const visibleValue = required("PLAYER_VISIBLE_VALUE_ID");
const visibleAssessment = required("PLAYER_VISIBLE_ASSESSMENT_ID");
const visibleFact = required("PLAYER_VISIBLE_FACT_ID");
const hiddenExperiment = required("PLAYER_HIDDEN_EXPERIMENT_ID");
const hiddenValue = required("PLAYER_HIDDEN_VALUE_ID");
const hiddenFact = required("PLAYER_HIDDEN_FACT_ID");
const fragment = required("PLAYER_FRAGMENT_ID");
const claim = required("PLAYER_EXPECTED_G9_CLAIM_SHA256");
const timeout = Number(process.env.PLAYER_CDP_TIMEOUT_MS || "90000");
const unicodeFixtures = [
  {id: "U01", text: "АБВ", cp: [1, 2], u16: [1, 2], quote: "Б", sha256: "c78364c5d0f27706fe002726c70be55fa7ceeb2537db621cfe54f73e9047c389", split: [0, 1, 0, 2]},
  {id: "U02", text: "А😀БВ", cp: [2, 3], u16: [3, 4], quote: "Б", sha256: "c78364c5d0f27706fe002726c70be55fa7ceeb2537db621cfe54f73e9047c389", split: [1, 0, 1, 1]},
  {id: "U03", text: "А😀Б", cp: [1, 2], u16: [1, 3], quote: "😀", sha256: "f0443a342c5ef54783a111b51ba56c938e474c32324d90c3a60c9c8e3a37e2d9", split: [0, 1, 0, 3]},
  {id: "U04", text: "Ae\u0301Б", cp: [1, 3], u16: [1, 3], quote: "e\u0301", sha256: "bf12767b0f2a56b2190075bae8169f656e3ce8d6357d4aff184bc6c7ea48f9f6", split: [0, 1, 1, 1]},
  {id: "U05", text: "А👩\u200d💻Б", cp: [1, 4], u16: [1, 6], quote: "👩\u200d💻", sha256: "427274538f1f24ef137872891551ffb4263f6edd90c80c533534578e8a5a9893", split: [0, 1, 1, 3]},
  {id: "U06", text: "А\r\nБ", cp: [3, 4], u16: [3, 4], quote: "Б", sha256: "c78364c5d0f27706fe002726c70be55fa7ceeb2537db621cfe54f73e9047c389", split: [1, 1, 1, 2]},
  {id: "U07", text: "А\u2067אב\u2069Б", cp: [2, 4], u16: [2, 4], quote: "אב", sha256: "cf7ad5d93148f62ef46ce18b42b7c2303579d6b508b54f75e1ac445e1d9a9e1b", split: [1, 0, 1, 2]},
  {id: "U08", text: "😀 факт; факт", cp: [8, 12], u16: [9, 13], quote: "факт", sha256: "a5b27a7349d8d0a202e78c5b3c65005665973aa7ea5aeb7bc3179cea064ecdf6", split: [4, 0, 5, 2]},
];
const browser = await launchChromium({timeoutMs: timeout});
let sessionId;
try {
  const client = browser.client;
  const created = await client.send("Target.createTarget", {url: "about:blank"});
  const attached = await client.send("Target.attachToTarget", {targetId: created.targetId, flatten: true});
  sessionId = attached.sessionId;
  await Promise.all([
    client.send("Page.enable", {}, sessionId), client.send("Runtime.enable", {}, sessionId),
    client.send("Network.enable", {}, sessionId), client.send("DOM.enable", {}, sessionId),
  ]);
  const requests = [];
  client.on("Network.requestWillBeSent", (event, sid) => {
    if (sid === sessionId && event.request.url.includes("/api/foundation/")) requests.push(event.request.url);
  });
  const set = await client.send("Network.setCookie", {
    name: cookieName, value: cookieValue, url: base + "/", httpOnly: true, sameSite: "Lax",
  }, sessionId);
  assert.equal(set.success, true);
  await client.send("Page.navigate", {url: `${base}/player/workspaces/${workspace}/`}, sessionId);
  await client.waitForExpression(
    "document.querySelector('#workspace-content')?.dataset.caProjectId && document.querySelector('#tab-document')?.textContent==='Доказательства'",
    sessionId, timeout,
  );
  const evaluate = expression => client.evaluate(expression, sessionId);
  const selectExperiment = async id => {
    await evaluate(`document.querySelector('[data-experiment-id=${JSON.stringify(id)}]')?.click()`);
    await client.waitForExpression(`document.querySelector('[data-ca-focus-id=${JSON.stringify(id === visibleExperiment ? visibleValue : hiddenValue)}]')`, sessionId, timeout);
  };
  const selectFocus = async (kind, id) => {
    await evaluate(`(()=>{const node=document.querySelector('[data-ca-focus-id=${JSON.stringify(id)}]');if(!node)return false;node.dataset.caFocusKind=${JSON.stringify(kind)};node.dataset.caFocusId=${JSON.stringify(id)};node.click();return true})()`);
    await client.waitForExpression("document.querySelector('#g9-related')?.disabled===false", sessionId, timeout);
  };
  const related = async expectedCount => {
    await evaluate("document.querySelector('#tab-document').click();document.querySelector('#g9-related').click();true");
    await client.waitForExpression(expectedCount
      ? `document.querySelectorAll('#g9-fact-list [role=option]').length===${expectedCount}`
      : "document.querySelector('#g9-state')?.textContent==='Доступных связанных фактов нет.'",
    sessionId, timeout);
  };
  const openFirstFact = async () => {
    await evaluate("document.querySelector('#g9-fact-list [role=option]').click();document.querySelector('#g9-open-fact').click();true");
    await client.waitForExpression("document.querySelectorAll('#g9-evidence-list [role=option]').length===1", sessionId, timeout);
  };

  let parameterAndAssessment = false, exactFragment = false, hiddenNeutral = false;
  let lateResponseCleared = false, revokedCleared = false, keyboard = false;
  let historyReauthorized = false, xssInert = false, unicodeExact = false, unicodeRangeCases = 0;
  let fragmentMismatchClosed = false;
  await selectExperiment(visibleExperiment);
  const beforeSelection = requests.filter(url => url.includes("/facts/")).length;
  await selectFocus("parameter-value", visibleValue);
  assert.equal(requests.filter(url => url.includes("/facts/")).length, beforeSelection);
  await related(1);

  if (scenario === "navigation") {
    await openFirstFact();
    await evaluate("document.querySelector('#g9-evidence-list [role=option]').click();document.querySelector('#g9-open-fragment').click();true");
    const exact = await evaluate("document.querySelector('#g9-detail blockquote')?.textContent || ''");
    exactFragment = exact.includes("😀‍🔬") && exact.includes("\r\n") && exact.includes("Повтор. Повтор.");
    assert.equal(await evaluate("document.querySelector('#g9-evidence-list [role=option]').textContent.includes('REFUTES')"), true);
    await selectFocus("actor-element-assessment", visibleAssessment);
    await related(1);
    parameterAndAssessment = true;
  } else if (scenario === "privacy") {
    await selectExperiment(hiddenExperiment);
    await selectFocus("parameter-value", hiddenValue);
    await related(0);
    hiddenNeutral = await evaluate("document.querySelector('#g9-state').textContent==='Доступных связанных фактов нет.' && !document.body.textContent.includes('Скрытое утверждение')");
    await selectExperiment(visibleExperiment);
    await selectFocus("parameter-value", visibleValue);
    await evaluate(`(()=>{const original=window.fetch;window.fetch=(...args)=>String(args[0]).includes(${JSON.stringify(visibleValue)})?new Promise((resolve,reject)=>setTimeout(()=>original(...args).then(resolve,reject),300)):original(...args);document.querySelector('#g9-related').click();return true})()`);
    await selectExperiment(hiddenExperiment);
    await selectFocus("parameter-value", hiddenValue);
    await new Promise(resolve => setTimeout(resolve, 600));
    lateResponseCleared = await evaluate("document.querySelectorAll('#g9-fact-list [role=option]').length===0");
    await client.send("Network.deleteCookies", {name: cookieName, url: base + "/"}, sessionId);
    await evaluate("document.querySelector('#g9-related').click();true");
    await client.waitForExpression("document.querySelector('#g9-state')?.textContent.includes('недоступны')", sessionId, timeout);
    revokedCleared = await evaluate("document.querySelectorAll('#g9-fact-list [role=option],#g9-evidence-list [role=option]').length===0 && !document.querySelector('#g9-detail').textContent");
  } else {
    await evaluate("(()=>{const item=document.querySelector('#g9-fact-list [role=option]');item.focus();item.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));return true})()");
    keyboard = await evaluate("document.querySelector('#g9-open-fact').disabled===false");
    await evaluate("document.querySelector('#g9-open-fact').click();true");
    await client.waitForExpression("document.querySelectorAll('#g9-evidence-list [role=option]').length===1", sessionId, timeout);
    await evaluate("document.querySelector('#g9-evidence-list [role=option]').click();document.querySelector('#g9-open-fragment').click();true");
    const page = await evaluate(`(()=>({
      text:document.querySelector('#g9-detail blockquote')?.textContent||'',
      images:document.querySelectorAll('#g9-evidence img,#g9-detail img').length,
      scripts:document.querySelectorAll('#g9-evidence script,#g9-detail script').length,
      storage:Object.keys(localStorage).sort(),session:Object.keys(sessionStorage),
      claim:document.querySelector('#g9-evidence-template')?.dataset.g9ClaimSha256,
      history:history.length
    }))()`);
    xssInert = page.images === 0 && page.scripts === 0;
    unicodeExact = page.text.includes("😀‍🔬") && page.text.includes("é") && page.text.includes("\u202eabc");
    assert.deepEqual(page.session, []); assert.equal(page.claim, claim);
    const rangeResults = await evaluate(`(async()=>{
      const fixtures=${JSON.stringify(unicodeFixtures)};
      const sha256=async text=>Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",new TextEncoder().encode(text))),byte=>byte.toString(16).padStart(2,"0")).join("");
      const boundary=(root,offset,preferNext)=>{
        if(!Number.isSafeInteger(offset)||offset<0)return null;
        const nodes=Array.from(root.childNodes);let remaining=offset;
        for(let index=0;index<nodes.length;index+=1){
          const codePoints=Array.from(nodes[index].data);
          if(remaining<codePoints.length||(remaining===codePoints.length&&(!preferNext||index===nodes.length-1)))return {node:nodes[index],nodeIndex:index,offset:codePoints.slice(0,remaining).join("").length};
          remaining-=codePoints.length;
        }
        return null;
      };
      const results=[];
      for(const fixture of fixtures){
        for(const mode of ["full","exact","split"]){
          const root=document.createElement("div");
          const points=Array.from(mode==="exact"?fixture.quote:fixture.text);
          const chunks=mode==="split"?Array.from({length:Math.ceil(points.length/2)},(_,i)=>points.slice(i*2,i*2+2).join("")):[points.join("")];
          for(const chunk of chunks)root.append(document.createTextNode(chunk));
          document.body.append(root);
          const cp=mode==="exact"?[0,Array.from(fixture.quote).length]:fixture.cp;
          const start=boundary(root,cp[0],true),end=boundary(root,cp[1],false);
          if(!start||!end)throw new Error(fixture.id+":"+mode+":boundary");
          const range=document.createRange();range.setStart(start.node,start.offset);range.setEnd(end.node,end.offset);
          const actual=range.toString();
          results.push({id:fixture.id,mode,actual,sha256:await sha256(actual),start:[start.nodeIndex,start.offset],end:[end.nodeIndex,end.offset]});
          root.remove();
        }
      }
      return results;
    })()`);
    assert.equal(rangeResults.length, 24);
    for (const result of rangeResults) {
      const fixture = unicodeFixtures.find(item => item.id === result.id);
      assert.equal(result.actual, fixture.quote, `${result.id}:${result.mode}:text`);
      assert.equal(result.sha256, fixture.sha256, `${result.id}:${result.mode}:sha256`);
      if (result.mode === "full") {
        assert.deepEqual(result.start, [0, fixture.u16[0]], `${result.id}:full:start`);
        assert.deepEqual(result.end, [0, fixture.u16[1]], `${result.id}:full:end`);
      } else if (result.mode === "split") {
        assert.deepEqual([...result.start, ...result.end], fixture.split, `${result.id}:split`);
      } else {
        assert.deepEqual(result.start, [0, 0], `${result.id}:exact:start`);
        assert.deepEqual(result.end, [0, fixture.quote.length], `${result.id}:exact:end`);
      }
    }
    unicodeRangeCases = rangeResults.length;
    await evaluate("history.back();true");
    await new Promise(resolve => setTimeout(resolve, 500));
    historyReauthorized = requests.filter(url => url.includes(`/parameter-values/${visibleValue}/facts/`)).length >= 2;
    await selectFocus("parameter-value", visibleValue);
    await related(1);
    await evaluate(`(()=>{const original=window.fetch;window.fetch=async(...args)=>{const response=await original(...args);if(!String(args[0]).includes("/evidence/"))return response;const payload=await response.json();payload.evidence[0].project_primary.text_sha256="0".repeat(64);return new Response(JSON.stringify(payload),{status:response.status,headers:{"Content-Type":"application/json","Cache-Control":"no-store"}})};return true})()`);
    await openFirstFact();
    await evaluate("document.querySelector('#g9-evidence-list [role=option]').click();document.querySelector('#g9-open-fragment').click();true");
    await client.waitForExpression("document.querySelector('#g9-state')?.textContent==='Точный фрагмент недоступен.'", sessionId, timeout);
    fragmentMismatchClosed = await evaluate("document.querySelectorAll('#g9-detail blockquote,#g9-evidence-list [role=option],#g9-fact-list [role=option]').length===0");
  }
  const storage = await evaluate("Object.keys(localStorage).sort()");
  assert.ok(storage.every(key => key === "conflict-analysis-player:layout:v1"));
  assert.equal((await evaluate("document.querySelector('#g9-evidence-template').dataset.g9ClaimSha256")), claim);
  console.log(JSON.stringify({
    browser_result: "PASS", scenario, fact_id: visibleFact, expected_fact_id: visibleFact,
    hidden_fact_id_not_rendered: hiddenFact, fragment_id: fragment,
    parameter_and_assessment: parameterAndAssessment, exact_fragment: exactFragment,
    hidden_neutral: hiddenNeutral, late_response_cleared: lateResponseCleared,
    revoked_cleared: revokedCleared, keyboard, history_reauthorized: historyReauthorized,
    xss_inert: xssInert, unicode_exact: unicodeExact, unicode_range_cases: unicodeRangeCases,
    fragment_mismatch_closed: fragmentMismatchClosed, storage,
  }));
} finally {
  if (sessionId) await browser.client.send("Target.detachFromTarget", {sessionId}).catch(() => {});
  await browser.close();
}
