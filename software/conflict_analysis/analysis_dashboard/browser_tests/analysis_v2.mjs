import assert from "node:assert/strict";
import { launchChromium } from "../../production_studio/browser_tests/cdp_client.mjs";

const required=name=>{const value=process.env[name];if(!value)throw new Error(`${name} is required`);return value;};
const base=required("ANALYSIS_BASE_URL").replace(/\/$/,"");
const project=required("ANALYSIS_PROJECT_ID"),workspace=required("ANALYSIS_WORKSPACE_ID");
const cookieName=required("ANALYSIS_SESSION_COOKIE_NAME"),cookieValue=required("ANALYSIS_SESSION_COOKIE_VALUE");
const timeout=Number(process.env.ANALYSIS_CDP_TIMEOUT_MS||"60000");
const viewports=[[1024,768,4],[1366,768,7],[1920,1080,7]];
const browser=await launchChromium({timeoutMs:timeout});let sessionId;const origins=new Set();
try{
 const client=browser.client,created=await client.send("Target.createTarget",{url:"about:blank"}),attached=await client.send("Target.attachToTarget",{targetId:created.targetId,flatten:true});sessionId=attached.sessionId;
 await Promise.all([client.send("Page.enable",{},sessionId),client.send("Runtime.enable",{},sessionId),client.send("Network.enable",{},sessionId)]);
 client.on("Network.requestWillBeSent",(event,sid)=>{if(sid===sessionId&&/^https?:/.test(event.request.url))origins.add(new URL(event.request.url).origin);});
 const set=await client.send("Network.setCookie",{name:cookieName,value:cookieValue,url:base+"/",httpOnly:true,sameSite:"Lax"},sessionId);assert.equal(set.success,true);
 for(const [width,height,minimumRows] of viewports){
  await client.send("Emulation.setDeviceMetricsOverride",{width,height,deviceScaleFactor:1,mobile:false},sessionId);
  await client.send("Page.navigate",{url:`${base}/analysis/projects/${project}/workspaces/${workspace}/`},sessionId);
  await client.waitForExpression("document.querySelector('#analysis-app')?.dataset.state==='ready'",sessionId,timeout);
  const result=await client.evaluate(`(()=>{const chart=document.querySelector('#chart').getBoundingClientRect(),rows=[...document.querySelectorAll('#timeline-table tbody tr')],visible=rows.filter(row=>{const r=row.getBoundingClientRect();return r.top<innerHeight&&r.bottom>0}).length;return {chart:chart.height,total:rows.length,visible,scroll:document.documentElement.scrollWidth>innerWidth,storage:Object.keys(localStorage)}})()`,sessionId);
  assert.ok(result.chart>120);assert.ok(result.visible>=Math.min(minimumRows,result.total));assert.equal(result.scroll,false);assert.ok(result.storage.every(key=>key.startsWith("conflict-analysis:analysis-layout:v1:")));
 }
 assert.deepEqual([...origins],[new URL(base).origin]);
 console.log(JSON.stringify({browser_result:"PASS",viewports,off_origin_free:true}));
}finally{if(sessionId)await browser.client.send("Target.detachFromTarget",{sessionId}).catch(()=>{});await browser.close();}
