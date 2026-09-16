import assert from "node:assert/strict";
import {spawn} from "node:child_process";
import {mkdtempSync, mkdirSync, writeFileSync, rmSync} from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import {CDPClient, findChromium} from "../../production_studio/browser_tests/cdp_client.mjs";

const base=process.env.ANALYSIS_BASE_URL, project=process.env.ANALYSIS_PROJECT_ID, workspace=process.env.ANALYSIS_WORKSPACE_ID;
assert.ok(base && project && workspace);
const evidence=process.env.GEOGRAPHY_EVIDENCE_DIR || process.env.RUNNER_TEMP;
if(evidence) mkdirSync(evidence,{recursive:true});
const port=await new Promise(resolve=>{const s=net.createServer();s.listen(0,"127.0.0.1",()=>{const p=s.address().port;s.close(()=>resolve(p));});});
const profile=mkdtempSync(path.join(os.tmpdir(),"geography-r1-chromium-"));
const proc=spawn(findChromium(),[`--remote-debugging-port=${port}`,`--user-data-dir=${profile}`,"--headless=new","--no-sandbox","--no-first-run","--no-default-browser-check","--disable-background-networking","--disable-component-update","--disable-sync","--use-angle=swiftshader","--enable-unsafe-swiftshader","--disable-dev-shm-usage","about:blank"],{stdio:["ignore","ignore","pipe"],windowsHide:true});
let stderr="",client,sid;proc.stderr.on("data",b=>{stderr=(stderr+b.toString()).slice(-12000);});
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const oracles=new Set(),origins=new Set(),errors=[],workers=[];
try {
  let endpoint;
  for(let i=0;i<200;i++) {try {const r=await fetch(`http://127.0.0.1:${port}/json/version`);endpoint=await r.json();break;}catch{await wait(50);}}
  assert.ok(endpoint,stderr);client=await CDPClient.connect(endpoint.webSocketDebuggerUrl,60000);
  const target=await client.send("Target.createTarget",{url:"about:blank"});
  sid=(await client.send("Target.attachToTarget",{targetId:target.targetId,flatten:true})).sessionId;
  await Promise.all(["Page.enable","Runtime.enable","Network.enable","Log.enable"].map(name=>client.send(name,{},sid)));
  client.on("Network.requestWillBeSent",event=>{if(/^https?:/.test(event.request.url))origins.add(new URL(event.request.url).origin);});
  client.on("Runtime.exceptionThrown",event=>errors.push(event.exceptionDetails.text));
  client.on("Log.entryAdded",event=>{if(event.entry.source==="security")errors.push(event.entry.text);});
  client.on("Target.attachedToTarget",async event=>{
    if(event.targetInfo.type==="worker") {workers.push(event.targetInfo.url);await client.send("Network.enable",{},event.sessionId);}
  });
  await client.send("Target.setAutoAttach",{autoAttach:true,waitForDebuggerOnStart:false,flatten:true},sid);
  const evaluate=expression=>client.evaluate(expression,sid);
  const ready=expression=>client.waitForExpression(expression,sid,60000);
  const cookie=async value=>assert.equal((await client.send("Network.setCookie",{name:process.env.ANALYSIS_SESSION_COOKIE_NAME,value,url:base+"/",httpOnly:true,sameSite:"Lax"},sid)).success,true);
  const click=async selector=>{
    const box=await evaluate(`(()=>{const r=document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()`);
    await client.send("Input.dispatchMouseEvent",{type:"mousePressed",button:"left",clickCount:1,...box},sid);
    await client.send("Input.dispatchMouseEvent",{type:"mouseReleased",button:"left",clickCount:1,...box},sid);
  };
  const fill=async(id,value)=>evaluate(`(()=>{const e=document.getElementById(${JSON.stringify(id)});e.value=${JSON.stringify(String(value))};e.dispatchEvent(new Event('input',{bubbles:true}));return e.value;})()`);
  const screen=async name=>{if(evidence){const image=await client.send("Page.captureScreenshot",{format:"png",captureBeyondViewport:false},sid);writeFileSync(path.join(evidence,name+".png"),Buffer.from(image.data,"base64"));}};
  await cookie(process.env.ANALYSIS_SESSION_COOKIE_VALUE);
  for(const [width,height] of [[1024,768],[1366,768]]) {
    await client.send("Emulation.setDeviceMetricsOverride",{width,height,deviceScaleFactor:1,mobile:false},sid);
    await client.send("Page.navigate",{url:`${base}/analysis/projects/${project}/workspaces/${workspace}/`},sid);
    await ready("document.querySelector('#analysis-app')?.dataset.state==='ready'");
    // Instrument only the test page; inspect actual rendered MapLibre layers.
    await evaluate(`(()=>{const M=maplibregl.Map,K=maplibregl.Marker;window.__geoMaps=[];window.__geoMarkers=[];maplibregl.Map=class extends M{constructor(o){super(o);window.__geoMaps.push(this);}};maplibregl.Marker=class extends K{constructor(o){super(o);window.__geoMarkers.push(this);}};return true;})()`);
    await click('[data-view="map"]');
    await ready("document.querySelector('#view-map').dataset.state==='ready'");
    await ready("window.__geoMaps[0].loaded()");
    const state=await evaluate(`(()=>{const m=__geoMaps[0],r=document.querySelector('#geo-map').getBoundingClientRect();return {label:[...document.querySelectorAll('#geo-map .geo-label')].some(n=>n.textContent==='Казахстан'),borders:m.queryRenderedFeatures({layers:['admin0-boundaries']}).length,disputed:m.getPaintProperty('disputed-boundaries','line-dasharray'),width:r.width,height:r.height,visible:r.top>=0&&r.bottom<=innerHeight,history:document.querySelector('#geo-history').getBoundingClientRect().top<innerHeight,scroll:document.documentElement.scrollWidth>innerWidth};})()`);
    assert.equal(state.label,true);oracles.add("GEO-23");assert.ok(state.borders>0);assert.deepEqual(state.disputed,[2,2]);oracles.add("GEO-24");
    assert.equal(state.scroll,false);assert.ok(state.width>250&&state.height>=280&&state.visible);assert.equal(state.history,true);
    oracles.add(width===1024?"GEO-33":"GEO-34");await screen(`map-${width}`);
    await click('#geo-edit');await ready("document.querySelector('#geo-dialog').open && window.__geoMaps.length===2 && window.__geoMaps[1].loaded()");
    const mapBox=await evaluate("(()=>{const r=document.querySelector('#geo-editor-map').getBoundingClientRect();return {x:r.x+r.width*.45,y:r.y+r.height*.55};})()");
    await client.send("Input.dispatchMouseEvent",{type:"mousePressed",button:"left",clickCount:1,...mapBox},sid);
    await client.send("Input.dispatchMouseEvent",{type:"mouseReleased",button:"left",clickCount:1,...mapBox},sid);
    await ready("document.querySelector('#geo-lat').value!==''");oracles.add("GEO-25");
    await fill('geo-lat',43.337);await fill('geo-lon',52.8619);
    const marker=await evaluate("(()=>{const p=__geoMarkers.at(-1).getLngLat(),r=__geoMarkers.at(-1).getElement().getBoundingClientRect();return {lat:p.lat,lon:p.lng,visible:r.width>0&&r.height>0};})()");
    assert.equal(marker.lat,43.337);assert.equal(marker.lon,52.8619);assert.equal(marker.visible,true);oracles.add("GEO-26");
    const drag=await evaluate("(()=>{const r=__geoMarkers.at(-1).getElement().getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()");
    await client.send("Input.dispatchMouseEvent",{type:"mousePressed",button:"left",buttons:1,clickCount:1,...drag},sid);
    for(let offset=5;offset<=30;offset+=5) await client.send("Input.dispatchMouseEvent",{type:"mouseMoved",button:"left",buttons:1,x:drag.x+offset,y:drag.y-10},sid);
    await client.send("Input.dispatchMouseEvent",{type:"mouseReleased",button:"left",buttons:0,clickCount:1,x:drag.x+30,y:drag.y-10},sid);
    assert.notEqual(await evaluate("document.querySelector('#geo-lon').value"),"52.8619");
    assert.equal(await evaluate("document.querySelector('#geo-source').value"),"USER_MAP");
    await fill('geo-lat',43.337);await fill('geo-lon',52.8619);
    await fill('geo-kind','REGION');await fill('geo-radius',45000);
    const circle=await evaluate("__geoMaps[1].getSource('location-uncertainty').serialize().data.features[0]");
    assert.equal(circle.properties.radius_m,45000);assert.equal(circle.geometry.coordinates[0].length,129);oracles.add("GEO-27");
    await fill('geo-rationale',`Chromium R1 ${width}: примерная локализация`);
    const editor=await evaluate("(()=>{const r=document.querySelector('#geo-dialog').getBoundingClientRect();return {visible:r.top>=0&&r.bottom<=innerHeight,scroll:document.documentElement.scrollWidth>innerWidth};})()");
    assert.equal(editor.visible,true);assert.equal(editor.scroll,false);await screen(`editor-${width}`);
    const before=await evaluate("[...document.querySelectorAll('#geo-history li')].map(n=>n.dataset.revisionId)");
    await click('#geo-save');await ready("!document.querySelector('#geo-dialog').open && document.querySelector('#view-map').dataset.state==='ready'");
    const after=await evaluate("[...document.querySelectorAll('#geo-history li')].map(n=>n.dataset.revisionId)");
    assert.equal(after.length,before.length+1);assert.deepEqual(after.slice(1),before);oracles.add("GEO-28");oracles.add("GEO-29");
    await screen(`saved-${width}`);
    await click('#geo-edit');await ready("document.querySelector('#geo-dialog').open");
    await click('#geo-clear');assert.equal(await evaluate("document.querySelector('#geo-lat').value"),"");
    await client.send("Input.dispatchKeyEvent",{type:"keyDown",key:"Escape",code:"Escape",windowsVirtualKeyCode:27},sid);
    await client.send("Input.dispatchKeyEvent",{type:"keyUp",key:"Escape",code:"Escape",windowsVirtualKeyCode:27},sid);
    assert.equal(await evaluate("document.querySelector('#geo-dialog').open"),false);
  }
  // Map layout is per user/project and must never write Player preferences.
  const beforeStorage=await evaluate("localStorage.getItem('conflict-analysis-player:layout:v1')");
  await fill('geo-height',430);
  assert.equal(await evaluate("localStorage.getItem('conflict-analysis-player:layout:v1')"),beforeStorage);
  assert.equal(await evaluate("Object.keys(localStorage).filter(k=>k.startsWith('conflict-analysis:analysis-map:v1:')).length"),1);oracles.add("GEO-32");
  // Late requests cannot repaint a different view. Abort the geography lane.
  await evaluate(`(()=>{const real=window.fetch;window.__releaseGeo=null;window.fetch=(url,options)=>{
    if(String(url).endsWith('/location/')) {window.fetch=real;return new Promise(resolve=>{window.__releaseGeo=()=>real(url,{...options,signal:undefined}).then(resolve);});}
    return real(url,options);
  };document.querySelector('#geo-refresh').click();return true;})()`);
  await ready("typeof window.__releaseGeo==='function'");
  await click('[data-view="timeline"]');
  await evaluate("window.__releaseGeo();true");await wait(250);
  assert.equal(await evaluate("document.querySelector('#view-map').hidden"),true);
  await click('[data-view="map"]');await ready("document.querySelector('#view-map').dataset.state==='ready'");
  await cookie(process.env.GEOGRAPHY_READER_COOKIE_VALUE);
  await client.send("Page.navigate",{url:`${base}/analysis/projects/${project}/workspaces/${workspace}/`},sid);
  await ready("document.querySelector('#analysis-app')?.dataset.state==='ready'");
  await click('[data-view="map"]');await ready("document.querySelector('#view-map').dataset.state==='ready'");
  assert.equal(await evaluate("document.querySelector('#geo-edit').hidden"),true);oracles.add("GEO-18");oracles.add("GEO-19");
  const csp=await evaluate(`fetch(location.href).then(r=>r.headers.get('Content-Security-Policy'))`);
  assert.ok(csp.includes("worker-src 'self'"));assert.ok(!csp.includes('blob:'));
  assert.ok(workers.some(url=>url.startsWith(base+'/static/analysis_dashboard/vendor/maplibre/')));oracles.add("GEO-31");
  assert.deepEqual([...origins],[new URL(base).origin]);oracles.add("GEO-30");assert.deepEqual(errors,[]);
  const result={result:"PASS",oracles:[...oracles].sort(),viewports:[[1024,768],[1366,768]],off_origin_requests:0,worker_same_origin:true,keyboard_escape:true,reader_read_only:true};
  if(evidence)writeFileSync(path.join(evidence,'geography-browser.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify(result));
} catch(error) {console.error(stderr);throw error;}
finally {
  if(client){await client.send('Browser.close').catch(()=>{});client.close();}
  if(proc.exitCode===null){await Promise.race([new Promise(resolve=>proc.once('exit',resolve)),wait(2500)]);}
  if(proc.exitCode===null)proc.kill();
  // Only the mkdtemp-created, task-owned profile is eligible for cleanup.
  assert.equal(path.dirname(profile),path.resolve(os.tmpdir()));assert.ok(path.basename(profile).startsWith('geography-r1-chromium-'));
  try{rmSync(profile,{recursive:true,force:true,maxRetries:10,retryDelay:100});}catch(error){if(error.code!=='EPERM')throw error;}
}
