(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const app = $("analysis-app"), panel = $("view-map"), dialog = $("geo-dialog");
  if (!app || !panel) return;
  const assets = "/static/analysis_dashboard/";
  const project = app.dataset.projectId;
  const api = `/api/foundation/geography/v1/projects/${project}/`;
  let data = null, main = null, editor = null, mainMarker = null, editMarker = null;
  let epoch = 0, controller = null, pending = null, saving = false, layoutKey = null;
  let labelsPromise = null;
  let mainPromise = null;
  const txt = (id, value) => { $(id).textContent = value; };
  const canonical = (value) => value && typeof value === "object"
    ? Array.isArray(value) ? `[${value.map(canonical).join(",")}]`
      : `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`
    : JSON.stringify(value);
  const hash = async (value) => Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value))), byte => byte.toString(16).padStart(2, "0")).join("");
  const csrf = () => document.cookie.split(";").map(item => item.trim()).find(item => item.startsWith("csrftoken="))?.slice(10) || "";

  async function request(path, options = {}) {
    const response = await fetch(api + path, {credentials:"same-origin", cache:"no-store", ...options});
    const raw = await response.text();
    let result;
    try { result = JSON.parse(raw); } catch { throw new Error("Не удалось прочитать ответ Foundation."); }
    if (!response.ok) throw new Error(result.errors?.join(" ") || "Запрос не выполнен.");
    const {response_sha256, ...core} = result;
    if (result.contract !== "FOUNDATION_PROJECT_LOCATION_V1" || result.project_id !== project || canonical(result) !== raw || await hash(canonical(core)) !== response_sha256) {
      throw new Error("Проверка целостности ответа Foundation не пройдена.");
    }
    return result;
  }

  function locationText(row) {
    if (!row) return "Не задана";
    return `≈ ${Number(row.latitude).toFixed(4)}, ${Number(row.longitude).toFixed(4)} · ${row.location_kind} · радиус ${row.uncertainty_radius_m ?? "не указан"} м`;
  }
  function circle(lon, lat, radius) {
    if (!radius) return {type:"FeatureCollection", features:[]};
    const rad = Math.PI / 180, angular = radius / 6371008.8, phi = lat * rad, points = [];
    for (let i = 0; i <= 128; i++) {
      const bearing = i / 128 * 2 * Math.PI;
      const targetLat = Math.asin(Math.sin(phi)*Math.cos(angular) + Math.cos(phi)*Math.sin(angular)*Math.cos(bearing));
      const delta = Math.atan2(Math.sin(bearing)*Math.sin(angular)*Math.cos(phi), Math.cos(angular)-Math.sin(phi)*Math.sin(targetLat));
      points.push([lon + delta/rad, targetLat/rad]);
    }
    return {type:"FeatureCollection",features:[{type:"Feature",properties:{radius_m:radius},geometry:{type:"Polygon",coordinates:[points]}}]};
  }
  function paintCircle(map, row) {
    const source = map?.getSource("location-uncertainty");
    if (source) source.setData(row ? circle(Number(row.longitude), Number(row.latitude), Number(row.uncertainty_radius_m)) : {type:"FeatureCollection",features:[]});
  }

  async function makeMap(container, editing) {
    if (!globalThis.maplibregl) throw new Error("Локальная библиотека карты недоступна.");
    maplibregl.setWorkerUrl(assets + "vendor/maplibre/maplibre-gl-csp-worker.js");
    const map = new maplibregl.Map({container, style:assets+"maps/map_style.json", center:[63,46], zoom:2.65,
      minZoom:1, maxZoom:12, attributionControl:false, renderWorldCopies:false,
      transformRequest:(url) => {
        const resolved = new URL(url, location.href);
        if (resolved.origin !== location.origin) throw new Error("Внешние ресурсы карты запрещены.");
        return {url:resolved.href};
      }});
    map.addControl(new maplibregl.NavigationControl({showCompass:false}), "top-left");
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("Локальная карта не загрузилась.")), 30000);
      map.once("load", () => {clearTimeout(timer); resolve();});
      map.once("error", (event) => {clearTimeout(timer); reject(new Error("Ошибка локального картографического слоя."));});
    });
    map.addSource("location-uncertainty", {type:"geojson",data:{type:"FeatureCollection",features:[]}});
    map.addLayer({id:"uncertainty-fill",type:"fill",source:"location-uncertainty",paint:{"fill-color":"#a43c1f","fill-opacity":0.16}});
    map.addLayer({id:"uncertainty-line",type:"line",source:"location-uncertainty",paint:{"line-color":"#a43c1f","line-width":2,"line-dasharray":[3,2]}});
    labelsPromise ||= fetch(assets+"maps/labels_ru.json", {credentials:"same-origin"}).then(r => {if (!r.ok) throw new Error("Подписи карты недоступны."); return r.json();});
    const labels = (await labelsPromise).labels;
    const markers = labels.map(item => {
      const node = document.createElement("span"); node.className = `geo-label ${item.kind}`;
      node.textContent = item.name_ru || item.canonical_name || item.feature_id;
      node.dataset.featureId = item.feature_id;
      const marker = new maplibregl.Marker({element:node, anchor:"center"}).setLngLat(item.coordinates).addTo(map);
      return {node,marker,item};
    });
    // Stable priority: Zhanaozen and country names win collisions; no glyph or
    // font server is needed. DOM labels use the operating system's local font.
    function placeLabels() {
      const occupied = [];
      const priority=item => item.name_ru==="Жанаозен" ? 0 : item.kind==="region" ? 1 : item.kind==="country" ? 2 : 3;
      markers.sort((a,b) => priority(a.item)-priority(b.item) || a.item.feature_id.localeCompare(b.item.feature_id));
      for (const {node,item} of markers) {
        node.style.visibility = "visible";
        const p = map.project(item.coordinates), width = node.offsetWidth, height = node.offsetHeight;
        const rect = [p.x-width/2-4,p.y-height/2-4,p.x+width/2+4,p.y+height/2+4];
        if (occupied.some(r => rect[0]<r[2] && rect[2]>r[0] && rect[1]<r[3] && rect[3]>r[1])) node.style.visibility="hidden";
        else occupied.push(rect);
      }
    }
    map.on("moveend",placeLabels); map.on("resize",placeLabels); placeLabels();
    if (editing) map.on("click", event => setCoordinates(event.lngLat.lat, event.lngLat.lng, "USER_MAP"));
    map.getCanvas().setAttribute("aria-label", editing ? "Карта: для точного ввода используйте поля широты и долготы" : "Карта локализации; масштабирование кнопками плюс и минус");
    return map;
  }

  function render() {
    const row = data.head, root = $("geo-current"); root.replaceChildren();
    for (const value of row ? [row.label || "Без подписи", locationText(row), row.area?.name_ru || "Территория не выбрана", `Источник: ${row.source_kind} · ${row.source_reference || "—"}`, `Определено: ${row.created_at}`, `Автор: ${row.actor_identifier}`, row.rationale] : ["Локализация не задана. Координаты не определены."]) {
      const p=document.createElement("p"); p.textContent=value; root.append(p);
    }
    $("geo-edit").hidden = !data.can_edit;
    $("geo-edit").textContent = row ? "Изменить точку" : "Указать точку";
    txt("geo-dataset", `Natural Earth 5.1.2 · ${data.map.dataset_code} ${data.map.dataset_version} · ${data.map.boundary_policy_version} · manifest ${data.map.manifest_sha256 || "не установлен"}`);
    $("geo-area").replaceChildren(new Option("Не выбрана", ""), ...data.areas.map(item => new Option(item.name_ru,item.id)));
    if (mainMarker) mainMarker.remove(); mainMarker=null;
    if (row && main) mainMarker = new maplibregl.Marker({color:"#a43c1f"}).setLngLat([Number(row.longitude),Number(row.latitude)]).addTo(main);
    paintCircle(main,row);
  }

  async function load() {
    const token = ++epoch; controller?.abort(); controller = new AbortController();
    panel.dataset.state="loading"; txt("geo-status","Загружаем локализацию и историю…");
    try {
      const [current, history] = await Promise.all([request("location/",{signal:controller.signal}), request("location-history/?limit=50",{signal:controller.signal})]);
      if (token !== epoch) return;
      data=current;
      if (!main) main = await (mainPromise ||= makeMap("geo-map",false).catch(error => {mainPromise=null;throw error;}));
      if (token !== epoch) return;
      render();
      $("geo-history").replaceChildren(...history.revisions.map(row => {
        const li=document.createElement("li"); li.textContent=`${row.created_at} · ${locationText(row)} · ${row.actor_identifier} · ${row.rationale}`;li.dataset.revisionId=row.id;return li;
      }));
      $("geo-history-more").hidden=!history.has_more;
      layoutKey=`conflict-analysis:analysis-map:v1:${data.user_id}:${project}`;
      let preferences={}; try {preferences=JSON.parse(localStorage.getItem(layoutKey) || "{}");} catch {}
      applyLayout(preferences);
      panel.dataset.state="ready"; txt("geo-status",data.head ? "Локализация сохранена. История доступна справа." : "Координаты не определены; на карте показан географический контекст.");
    } catch(error) {
      if (token !== epoch || error.name === "AbortError") return;
      panel.dataset.state="error"; txt("geo-status",error.message);$("geo-edit").hidden=true;
    }
  }
  function applyLayout(value) {
    const clamp=(n,min,max,fallback) => typeof n==="number" && Number.isFinite(n) ? Math.min(max,Math.max(min,n)) : fallback;
    const height=clamp(value.height,280,620,innerWidth<=1100?380:410), width=clamp(value.width,240,360,280);
    panel.style.setProperty("--geo-height",`${height}px`); panel.style.setProperty("--geo-width",`${width}px`);
    $("geo-height").value=height; $("geo-width").value=width; main?.resize();
  }
  for (const id of ["geo-height","geo-width"]) $(id).addEventListener("input",() => {
    const preferences={height:Number($("geo-height").value),width:Number($("geo-width").value)};
    applyLayout(preferences); if (layoutKey) try {localStorage.setItem(layoutKey,JSON.stringify(preferences));} catch {}
  });

  function draft() {
    const number=(id) => $(id).value.trim()==="" ? null : Number($(id).value);
    return {latitude:$("geo-lat").value,longitude:$("geo-lon").value,location_kind:$("geo-kind").value,
      uncertainty_radius_m:number("geo-radius"),area_id:$("geo-area").value || null,label:$("geo-label").value,
      source_kind:$("geo-source").value,source_reference:$("geo-reference").value,rationale:$("geo-rationale").value,
      supersedes_id:data.head?.id || null,boundary_dataset_code:data.map.dataset_code,
      boundary_dataset_version:data.map.dataset_version,boundary_policy_version:data.map.boundary_policy_version};
  }
  function validCoordinates(row) {
    return row.latitude!=="" && row.longitude!=="" && Number.isFinite(Number(row.latitude)) && Number.isFinite(Number(row.longitude)) && Math.abs(Number(row.latitude))<=90 && Math.abs(Number(row.longitude))<=180;
  }
  function sync() {
    if (!data) return;
    const row=draft();
    pending=null;
    $("geo-radius").required=row.location_kind!=="POINT";
    $("geo-radius").min=row.location_kind==="POINT" ? "0" : "1";
    if (editMarker) editMarker.remove(); editMarker=null;
    if (editor && validCoordinates(row)) {
      editMarker=new maplibregl.Marker({color:"#a43c1f",draggable:true}).setLngLat([Number(row.longitude),Number(row.latitude)]).addTo(editor);
      editMarker.on("dragend",() => {const p=editMarker.getLngLat();setCoordinates(p.lat,p.lng,"USER_MAP");});
      paintCircle(editor,row);
    } else paintCircle(editor,null);
    txt("geo-before-after",`Было: ${locationText(data.head)}. Стало: ${validCoordinates(row) ? locationText(row) : "точка не выбрана"}.`);
  }
  function setCoordinates(lat,lon,source) {
    $("geo-lat").value=Math.max(-90,Math.min(90,lat)).toFixed(7);
    $("geo-lon").value=(((lon+180)%360+360)%360-180).toFixed(7);
    $("geo-source").value=source; sync();
  }
  $("geo-edit").addEventListener("click",async () => {
    if (!data?.can_edit) return;
    const row=data.head;
    for (const [id,value] of Object.entries({"geo-lat":row?.latitude ?? "","geo-lon":row?.longitude ?? "","geo-kind":row?.location_kind || "POINT","geo-radius":row?.uncertainty_radius_m ?? "","geo-area":row?.area?.id || "","geo-label":row?.label || "","geo-source":row?.source_kind || "USER_MAP","geo-reference":row?.source_reference || "","geo-rationale":""})) $(id).value=value;
    txt("geo-error","");pending=null;dialog.showModal();
    try {
      if (!editor) editor=await makeMap("geo-editor-map",true);
      editor.resize();
      if (row) editor.jumpTo({center:[Number(row.longitude),Number(row.latitude)],zoom:5});
      sync();$("geo-lat").focus();
    } catch(error) {txt("geo-error",error.message);}
  });
  for (const node of $("geo-form").querySelectorAll("input,select,textarea")) node.addEventListener("input",() => {
    if (["geo-lat","geo-lon"].includes(node.id)) $("geo-source").value="MANUAL_COORDINATES";
    sync();
  });
  $("geo-clear").addEventListener("click",() => {$("geo-lat").value="";$("geo-lon").value="";sync();$("geo-lat").focus();});
  $("geo-cancel").addEventListener("click",() => {if (!saving) dialog.close();});
  dialog.addEventListener("cancel",event => {if (saving) event.preventDefault();});
  $("geo-form").addEventListener("submit",async event => {
    event.preventDefault(); if (saving || !data?.can_edit) return;
    const body=draft();
    if (!validCoordinates(body) || !body.rationale.trim() || !$("geo-form").reportValidity()) return;
    pending ||= {body,operation:crypto.randomUUID(),etag:data.etag_sha256};
    saving=true;$("geo-save").disabled=true;txt("geo-error","Сохраняем новую версию…");
    try {
      await request("location-revisions/",{method:"POST",headers:{"Content-Type":"application/json","X-CSRFToken":csrf(),"If-Match":`"${pending.etag}"`,"X-Operation-ID":pending.operation},body:JSON.stringify(pending.body)});
      pending=null;dialog.close();await load();$("geo-edit").focus();
    } catch(error) {txt("geo-error",`${error.message} Черновик сохранён в открытой форме; отмените и обновите карту для сравнения версий.`);}
    finally {saving=false;$("geo-save").disabled=false;}
  });
  $("geo-refresh").addEventListener("click",load);
  app.addEventListener("analysis:view",event => {
    if (event.detail.name==="map") {
      if (!data || panel.dataset.state!=="ready") load(); else main?.resize();
    } else {epoch++;controller?.abort();}
  });
})();
