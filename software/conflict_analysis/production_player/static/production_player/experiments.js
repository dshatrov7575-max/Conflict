/* G8 browser composition: session/CSRF only, Foundation HTTP only, memory-only state. */
(() => {
  "use strict";
  const app = document.getElementById("player-app"), root = document.getElementById("workspace-content");
  if (!app || !root || root.dataset.g8Shell !== "true") return;
  const API = "/api/foundation/player/", PROFILE = "KZ_ZHANAOZEN_EXPERT_V2_A5_0_1";
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
  const SHA = /^[0-9a-f]{64}$/;
  const state = {experiments: [], selected: null, preview: null, file: null, busy: false, loadedWorkspace: null};
  const $ = (id) => document.getElementById(id);
  const cell = (value) => {const node = document.createElement("td"); node.textContent = value == null ? "—" : String(value); return node;};
  const cookie = () => document.cookie.split(";").map(v => v.trim()).find(v => v.startsWith("csrftoken="))?.slice(10) || "";
  const quoted = (value) => `"${value}"`;
  function fail(code) {throw new Error(code || "PLAYER_OPERATION_FAILED");}
  async function request(path, options = {}) {
    const headers = {Accept: "application/json", ...(options.headers || {})};
    if (options.body) {if (!(options.body instanceof FormData)) headers["Content-Type"] = "application/json"; headers["X-CSRFToken"] = cookie();}
    const response = await fetch(API + path, {...options, credentials: "same-origin", cache: "no-store", headers});
    const raw = await response.text(), expected = response.headers.get("ETag");
    const bytes = new TextEncoder().encode(raw), actual = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), n => n.toString(16).padStart(2, "0")).join("");
    if (expected !== quoted(actual)) fail("PLAYER_RESPONSE_HASH_MISMATCH");
    let body; try {body = JSON.parse(raw);} catch (_) {fail("PLAYER_RESPONSE_JSON_INVALID");}
    if (!response.ok) fail(body?.code); return body;
  }
  const body = (value) => JSON.stringify(value);
  function setBusy(value, message) {
    state.busy = value;
    if (value) {for (const id of ["experiment-plus","g8-freeze","g8-archive","g8-preview","g8-import"]) {if ($(id)) $(id).disabled=true;}}
    else {const draft=state.selected?.status==="DRAFT"; $("experiment-plus").disabled=app.dataset.projectionStatus!=="COMPLETE"; $("g8-freeze").disabled=!draft; $("g8-archive").disabled=!state.selected||!["DRAFT","FROZEN"].includes(state.selected.status); $("g8-preview").disabled=!draft; $("g8-import").disabled=!draft||!state.preview?.commit_allowed;}
    if (message) $("g8-import-state").textContent = message;
  }
  function experimentURL(id) {return `/player/workspaces/${app.dataset.workspaceId}/experiments/${id}/`;}
  function applyWorkspace(item) {
    if (!item || item.id !== app.dataset.workspaceId || item.assessment_projection_status !== "COMPLETE" || !SHA.test(item.definition_manifest_hash || "") || !SHA.test(item.assessment_projection_sha256 || "")) fail("ASSESSMENT_PROJECTION_INTEGRITY_CONFLICT");
    app.dataset.projectionStatus = item.assessment_projection_status; if (app.dataset.projectionStatus !== "COMPLETE") fail("ASSESSMENT_PROJECTION_INTEGRITY_CONFLICT"); app.dataset.state = "ready"; root.hidden = false;
    for (const [id,value] of [["workspace-name",item.name],["workspace-identity",`${item.code} · ${item.id}`],["definition-identity",item.definition_id],["definition-hash",item.definition_manifest_hash],["projection-status",item.assessment_projection_status],["projection-hash",item.assessment_projection_sha256],["projection-badge",item.assessment_projection_status],["status-definition",`Определение: ${item.definition_id}`],["status-state","Готово"]]) {if ($(id)) $(id).textContent=value;}
  }
  async function loadExperiments(force = false) {
    const workspace = app.dataset.workspaceId;
    if (!workspace || (state.busy && !force)) return;
    if (!force && state.loadedWorkspace === workspace) return;
    const result = await request(`workspaces/${workspace}/experiments/`);
    if (!Array.isArray(result.experiments)) fail("PLAYER_RESPONSE_SHAPE_INVALID"); applyWorkspace(result.workspace);
    state.experiments = result.experiments; state.loadedWorkspace = workspace; renderTabs();
    const initial = root.dataset.initialExperimentId;
    if (initial && state.experiments.some(item => item.id === initial)) select(initial);
    await loadComparison(); const plus=$("experiment-plus"); plus.setAttribute("aria-disabled","false"); plus.disabled=false;
  }
  function renderTabs() {
    const tabs = $("experiment-tabs"), plus = $("experiment-plus");
    tabs.querySelectorAll("[data-g8-experiment]").forEach(node => node.remove());
    for (const item of state.experiments) {
      const tab = document.createElement("button"); tab.type = "button"; tab.setAttribute("role", "tab"); tab.dataset.g8Experiment = "true"; tab.dataset.experimentId = item.id; tab.textContent = item.name; tab.addEventListener("click", () => select(item.id)); tabs.insertBefore(tab, plus);
    }
  }
  async function select(id, force = false) {
    if (state.busy && !force) return;
    if (id === "general") {state.selected = null; $("general-panel").hidden = false; $("experiment-panel").hidden = true; return;}
    const item = state.experiments.find(value => value.id === id); if (!item) return;
    state.selected = item; $("general-panel").hidden = true; $("experiment-panel").hidden = false; $("g8-records").tBodies[0].replaceChildren();
    document.querySelectorAll("#experiment-tabs [data-experiment-id]").forEach(tab => tab.setAttribute("aria-selected", String(tab.dataset.experimentId === id)));
    $("experiment-name").textContent = item.name; $("g8-experiment-status").textContent = item.status; $("g8-experiment-status").dataset.status = item.status;
    $("g8-permalink").href = experimentURL(item.id); const metadata = $("experiment-metadata"); metadata.replaceChildren();
    for (const [name, value] of [["Идентификатор",item.id],["Дорожка",item.assessment_set.kind],["Профиль",item.expert_profile.display_name],["Identity key",item.expert_profile.identity_key],["Методика",item.method_version],["ETag",item.etag]]) {const dt=document.createElement("dt"),dd=document.createElement("dd");dt.textContent=name;dd.textContent=value;metadata.append(dt,dd);}
    $("g8-freeze").disabled = item.status !== "DRAFT"; $("g8-archive").disabled = !["DRAFT","FROZEN"].includes(item.status); $("g8-preview").disabled = item.status !== "DRAFT";
    await loadValues();
  }
  async function loadValues() {
    if (!state.selected) return; const result = await request(`experiments/${state.selected.id}/values/`), table=$("g8-records").tBodies[0]; table.replaceChildren();
    for (const item of result.values || []) {const row=document.createElement("tr"), shown=item.status === "UNKNOWN" ? "UNKNOWN" : item.value; row.dataset.focusKind="parameter-value"; row.dataset.focusId=item.id; row.append(cell(item.code),cell(item.parameter_code),cell(shown),cell(item.confidence_category),cell(item.supersedes_id)); table.append(row);}
  }
  async function loadComparison() {
    const workspace=app.dataset.workspaceId; if (!workspace) return; const result=await request(`workspaces/${workspace}/experiment-comparison/`); if (result.aggregation !== null) fail("PLAYER_AGGREGATION_FORBIDDEN");
    const table=$("g8-comparison").tBodies[0]; table.replaceChildren(); for (const item of result.values || []) {const row=document.createElement("tr"); row.dataset.focusKind="parameter-value"; row.dataset.focusId=item.id; row.append(cell(item.experiment_name),cell(item.actor_code),cell(item.element_code),cell(item.parameter_code),cell(item.status === "UNKNOWN" ? "UNKNOWN" : item.value),cell(item.status)); table.append(row);}
  }
  function identity(prefix) {return `${prefix}-${crypto.randomUUID().slice(0,8)}`;}
  async function create(event) {
    event.preventDefault(); const kind=$("g8-kind").value, profileId=crypto.randomUUID(), setId=crypto.randomUUID(), experimentId=crypto.randomUUID(), operationId=crypto.randomUUID(), code=identity("EXP"), profileCode=identity("PROFILE"), setCode=identity("SET");
    const payload={experiment:{id:experimentId,code,version:"1.0.0",name:$("g8-name").value,color:$("g8-color").value||"#255cca",order:state.experiments.length,method_version:$("g8-method").value||"A5-v0.1"},assessment_set:{id:setId,code:setCode,version:"1.0.0",kind,name:`${$("g8-name").value} values`,description:"Independent assessment lane"},expert_profile:{id:profileId,code:profileCode,version:"1.0.0",kind,display_name:$("g8-profile-name").value,identity_key:`${kind}:${profileId}`,provider:$("g8-provider").value,model_name:kind === "AI" ? $("g8-model").value : "",metadata:{contract:"FOUNDATION_PLAYER_EXPERT_PROFILE_V1"}}};
    setBusy(true,"Создаём атомарный эксперимент…"); try {const result=await request(`workspaces/${app.dataset.workspaceId}/experiments/`,{method:"POST",headers:{"Idempotency-Key":operationId,"If-Match":quoted($("definition-hash").textContent)},body:body(payload)}); state.loadedWorkspace=null; await loadExperiments(true); $("g8-create-dialog").close(); const created=result.created_experiment; if (created) await select(created.id,true);} finally {setBusy(false,"Готово.");}
  }
  async function transition(action) {if (!state.selected) return; const current=state.selected; setBusy(true,`${action}…`); try {await request(`experiments/${current.id}/${action}/`,{method:"POST",headers:{"Idempotency-Key":crypto.randomUUID(),"If-Match":quoted(current.etag)},body:body({})}); state.loadedWorkspace=null; await loadExperiments(true); await select(current.id,true);} finally {setBusy(false,"Готово.");}}
  async function readFile() {const file=$("g8-file").files[0]; if (!file) fail("G8_XLSX_FILE_REQUIRED"); state.file=file; return file;}
  function multipart(file,metadata){const form=new FormData();form.append("metadata",JSON.stringify(metadata));form.append("file",file,file.name);return form;}
  async function preview() {if (!state.selected) return; setBusy(true,"Preview: сервер выполняет нулевую запись…"); try {const file=await readFile(), source=$("g8-source-column").selectedIndex===0?"ИИ_Значение":"Эксперт_Значение", metadata={profile_id:PROFILE,sheet:"По_главам",source_column:source}; state.preview=await request(`experiments/${state.selected.id}/xlsx-preview/`,{method:"POST",body:multipart(file,metadata)}); $("g8-preview-result").hidden=false; $("g8-preview-result").textContent=JSON.stringify(state.preview,null,2); $("g8-import").disabled=!state.preview.commit_allowed; $("g8-import-state").textContent=`${state.preview.rows_to_create} значений; 18 METHOD_BLOCKED + 24 RECODING_REQUIRED исключены.`;} finally {state.busy=false; $("g8-preview").disabled=state.selected?.status!=="DRAFT";}}
  async function commitImport() {if (!state.selected || !state.preview || !state.file) return; const operationId=crypto.randomUUID(), preview=state.preview, ticket={contract:"FOUNDATION_PLAYER_XLSX_IMPORT_TICKET_V1",contract_version:"1.0.0",workspace_id:app.dataset.workspaceId,experiment_id:state.selected.id,operation_id:operationId,raw_file_sha256:preview.raw_file_sha256,byte_length:preview.byte_length,profile_id:PROFILE,profile_sha256:preview.profile_sha256,sheet:preview.sheet,source_column:preview.source_column,preview_sha256:preview.preview_sha256,request_plan_sha256:preview.request_plan_sha256}; const metadata={profile_id:PROFILE,sheet:preview.sheet,source_column:preview.source_column,preview_sha256:preview.preview_sha256,excluded_42_acknowledged:true,ticket}; setBusy(true,"Атомарный импорт…"); try {await request(`experiments/${state.selected.id}/xlsx-import/`,{method:"POST",headers:{"Idempotency-Key":operationId,"If-Match":quoted(preview.preview_sha256)},body:multipart(state.file,metadata)}); await loadValues(); await loadComparison(); state.preview=null; $("g8-import").disabled=true;} finally {setBusy(false,"Импорт завершён; квитанция сохранена.");}}
  $("experiment-plus").addEventListener("click",()=>{if (!state.busy && app.dataset.projectionStatus === "COMPLETE") $("g8-create-dialog").showModal();}); $("g8-create-cancel").addEventListener("click",()=>$("g8-create-dialog").close()); $("g8-create-form").addEventListener("submit",event=>create(event).catch(error=>$("g8-create-state").textContent=error.message)); $("g8-freeze").addEventListener("click",()=>transition("freeze").catch(error=>$("g8-import-state").textContent=error.message)); $("g8-archive").addEventListener("click",()=>transition("archive").catch(error=>$("g8-import-state").textContent=error.message)); $("g8-preview").addEventListener("click",()=>preview().catch(error=>{state.busy=false;$("g8-import-state").textContent=error.message;})); $("g8-import").addEventListener("click",()=>commitImport().catch(error=>{state.busy=false;$("g8-import-state").textContent=error.message;})); $("g8-comparison-refresh").addEventListener("click",()=>loadComparison().catch(()=>{})); $("experiment-general").addEventListener("click",()=>select("general"));
  const observer=new MutationObserver(()=>loadExperiments().catch(()=>{})); observer.observe(app,{attributes:true,attributeFilter:["data-state","data-workspace-id","data-projection-status"]}); loadExperiments().catch(()=>{});
})();
