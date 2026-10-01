import assert from "node:assert/strict";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { launchChromium } from "./cdp_client.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const fixtures = JSON.parse(readFileSync(process.argv[2], "utf8"));
// Presentation fixtures intentionally omit application requests. Existing live-server
// suites execute the unmodified Foundation/calculation workflows with real sessions.
const server = http.createServer((request, response) => {
  const pathname = new URL(request.url, "http://localhost").pathname;
  if (pathname.startsWith("/static/")) {
    const relative = pathname.slice(8);
    const app = relative.split("/")[0];
    const target = path.resolve(root, app, "static", relative);
    if (!target.startsWith(path.join(root, app, "static") + path.sep)) {
      response.writeHead(403).end(); return;
    }
    try {
      response.setHeader("Content-Type", target.endsWith(".css") ? "text/css" : "application/javascript");
      response.end(readFileSync(target));
    } catch { response.writeHead(404).end(); }
    return;
  }
  const source = fixtures[pathname.slice(1)];
  if (!source) { response.writeHead(404).end(); return; }
  response.setHeader("Content-Type", "text/html; charset=utf-8");
  response.end(source.replace(/<script\b[^>]*src="([^"]+)"[^>]*><\/script>/g,
    (tag, src) => /panel_ui\.js|scenario\.js/.test(src) ? tag : ""));
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await launchChromium();
const { client } = browser;
let helpChecks = 0;
const layoutChecks = [];
const errors = [];
try {
  const { targetId } = await client.send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await client.send("Target.attachToTarget", { targetId, flatten: true });
  await client.send("Page.enable", {}, sessionId);
  await client.send("Runtime.enable", {}, sessionId);
  await client.send("Page.bringToFront", {}, sessionId);
  client.on("Runtime.exceptionThrown", event => errors.push(event.exceptionDetails.text));
  const evaluate = expression => client.evaluate(expression, sessionId);
  const key = async (name, code, modifiers = 0) => {
    const fields = { key: name, code: name === " " ? "Space" : name, windowsVirtualKeyCode: code, modifiers };
    await client.send("Input.dispatchKeyEvent", { type: "keyDown", ...fields, text: name === "Enter" ? "\r" : name === " " ? " " : "" }, sessionId);
    await client.send("Input.dispatchKeyEvent", { type: "keyUp", ...fields }, sessionId);
  };
  const viewport = async width => client.send("Emulation.setDeviceMetricsOverride", { width, height: 900, deviceScaleFactor: 1, mobile: false }, sessionId);
  const checkLayout = async (screen, width) => {
    const layout = await evaluate(`(() => {
      const panels = [...document.querySelectorAll('[data-panel-help]')].filter(n => n.checkVisibility());
      return {
        width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth,
        overflow: [...document.querySelectorAll('body *')].filter(n => n.checkVisibility() && n.getBoundingClientRect().right > document.documentElement.clientWidth).slice(0, 15).map(n => [n.tagName,n.id,n.className,n.getBoundingClientRect().width]),
        controls: panels.map(n => {
          const b = n.querySelector(':scope > .panel-help, :scope > summary > .panel-help');
          const r = b.getBoundingClientRect(), p = n.getBoundingClientRect(), hit = getComputedStyle(b, '::after');
          return {topic:n.dataset.panelHelp, width:r.width, height:r.height, hitWidth:parseFloat(hit.width), hitHeight:parseFloat(hit.height), right:p.left+n.clientLeft+n.clientWidth-r.right, top:r.top-p.top - (n.tagName === 'FIELDSET' ? n.querySelector('legend').getBoundingClientRect().height : 0)};
        })
      };
    })()`);
    assert.equal(layout.scroll, layout.width, `${screen} @${width}: page overflow ${JSON.stringify(layout)}`);
    layoutChecks.push({screen, viewport:width, clientWidth:layout.width, scrollWidth:layout.scroll});
    for (const control of layout.controls) {
      assert(control.width >= 22 && control.width <= 24 && control.height >= 22 && control.height <= 24, `${screen}: visible ? ${JSON.stringify(control)}`);
      assert(control.hitWidth >= 32 && control.hitHeight >= 32, `${screen}: help hit target ${JSON.stringify(control)}`);
      assert(control.right >= 4 && control.right < 20 && control.top >= 4 && control.top < 30, `${screen}: top-right ? ${JSON.stringify(control)}`);
    }
  };
  for (const [screen] of Object.entries(fixtures)) {
    await viewport(1280);
    await client.send("Page.navigate", { url: `${base}/${screen}#ui-help-topic-workspace` }, sessionId);
    await client.waitForExpression("Boolean(document.querySelector('.panel-help') && document.querySelector('[data-ui-icon] > .ui-icon'))", sessionId);
    const initial = await evaluate(`({
      helpOpen: document.querySelector('#ui-help-dialog').open,
      helpSelected: Boolean(document.querySelector('[data-right-tab="help"][aria-selected="true"]')),
      helpVisible: [...document.querySelectorAll('#panel-help, #help-panel')].some(n => n.checkVisibility()),
      helpFocused: document.activeElement.matches('[data-help-open], .panel-help'),
    })`);
    assert.deepEqual(initial, {helpOpen:false, helpSelected:false, helpVisible:false, helpFocused:false}, `${screen}: initial Help state`);
    // A normal ready workspace; never reveal unrelated tabs, errors or navigation guards.
    await evaluate(`(() => {
      const app = document.querySelector('#player-app');
      if (app) app.dataset.state = 'ready';
      const workspace = document.querySelector('#workspace-content');
      if (workspace) workspace.hidden = false;
      const template = document.querySelector('#g9-evidence-template');
      if (template) {
        document.querySelector('#panel-document').removeAttribute('data-panel-help');
        document.querySelector('#panel-document').replaceChildren(template.content.cloneNode(true));
      }
      for (const id of ['workspace-name', 'project-name', 'definition-label']) {
        const node = document.getElementById(id);
        if (node && node.tagName !== 'INPUT') node.textContent = 'Рабочий контекст — ' + 'ДлинноеЗначение'.repeat(8);
      }
      for (const node of document.querySelectorAll('#workspace-identity, #definition-identity, #definition-hash, #projection-hash, #project-id, #definition-id, #definition-etag')) {
        node.textContent = '11111111-1111-4111-8111-111111111111' + 'abcdef'.repeat(8);
      }
      const state = document.querySelector('#authoring-state-code');
      if (state) { state.textContent = 'Черновик открыт'; document.querySelector('#authoring-state-message').textContent = ''; }
    })()`);
    await client.waitForExpression("[...document.querySelectorAll('[data-panel-help]')].every(n => n.querySelector(':scope > .panel-help, :scope > summary > .panel-help'))", sessionId);
    for (const width of [320, 360, 768, 1440]) {
      await viewport(width);
      await evaluate("document.activeElement.blur(); window.scrollTo(0, 0)");
      await checkLayout(screen, width);
      assert(await evaluate(`(() => {
        const b = [...document.querySelectorAll('.panel-help')].find(n => n.checkVisibility());
        b.scrollIntoView({block:'center'});
        const r = b.getBoundingClientRect();
        return document.elementFromPoint(r.left - 3, r.top + r.height / 2) === b;
      })()`), `${screen}: invisible hit area is clickable`);
      await evaluate("window.scrollTo(0, 0)");
      const titles = await evaluate(`([...document.querySelectorAll('.ui-title, .ui-result-main h1, #workspace-name, #experiment-name')].filter(n => n.checkVisibility() && n.textContent.trim()).map(n => ({
        text:n.textContent.trim(), title:n.title, height:n.getBoundingClientRect().height,
        line:parseFloat(getComputedStyle(n).lineHeight), clamp:getComputedStyle(n).webkitLineClamp,
      })))`);
      for (const title of titles) {
        assert.equal(title.title, title.text, `${screen}: full title accessible`);
        assert.equal(title.clamp, '2');
        assert(title.height <= 2 * title.line + 1, `${screen}: title exceeds two lines`);
      }
      assert(await evaluate("[...document.querySelectorAll('.identity-grid dd, .identity-list dd')].filter(n => n.checkVisibility() && n.textContent.trim()).every(n => n.title === n.textContent.trim() && getComputedStyle(n).textOverflow === 'ellipsis' && getComputedStyle(n).whiteSpace === 'nowrap')"), `${screen}: full identifiers with single-line ellipsis`);
      assert(await evaluate("!document.activeElement.matches('[data-help-open], .panel-help')"), `${screen}: screenshots have no help focus`);
      if (process.env.UI_SCREENSHOT_DIR && [360, 1440].includes(width) && /scenario_modeling|workspace|audited_draft_definition/.test(screen)) {
        mkdirSync(process.env.UI_SCREENSHOT_DIR, { recursive: true });
        const shot = await client.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false }, sessionId);
        writeFileSync(path.join(process.env.UI_SCREENSHOT_DIR, `${screen.replaceAll('/', '-')}-${width}.png`), Buffer.from(shot.data, "base64"));
      }
      if (screen.includes('audited_draft_definition')) {
        for (const dirty of [false, true]) {
          await evaluate(`document.querySelector('#lifecycle-navigation-guard').hidden = ${!dirty}`);
          const saves = await evaluate("[...document.querySelectorAll('[data-ui-kind=primary][data-ui-icon=save]')].filter(n => n.checkVisibility()).map(n => n.id)");
          assert.deepEqual(saves, [dirty ? 'lifecycle-save-before-navigation' : 'save-draft'], 'Exactly one visible primary Save per state');
          await checkLayout(screen, width);
        }
        await evaluate("document.querySelector('#authoring-state').dataset.state = 'SAVE_ERROR'");
        assert(await evaluate("document.querySelector('#authoring-state').checkVisibility()"), 'Save errors remain visible during the navigation guard');
        await evaluate("document.querySelector('#lifecycle-navigation-guard').hidden = true");
      }
    }
    // Separately stress every hidden state. These are not acceptance screenshots.
    await viewport(1440);
    await evaluate(`(() => {
      for (const node of document.querySelectorAll('[hidden]')) {
        if (!node.closest('#ui-help-dialog') && node.tagName !== 'INPUT') node.hidden = false;
      }
      const studio = document.querySelector('#studio-app');
      if (studio) studio.dataset.state = 'ready';
      for (const node of document.querySelectorAll('details:not(.ui-layout-settings)')) node.open = true;
      for (const node of document.querySelectorAll('.projection-badge, .g8-status')) node.textContent = 'LONG_STATUS_'.repeat(12);
      for (const body of document.querySelectorAll('table tbody:empty')) {
        const row = body.insertRow();
        for (const _heading of body.closest('table').querySelectorAll('thead th')) row.insertCell().textContent = 'ДлинноеИмя'.repeat(12);
      }
    })()`);
    // Every rendered panel resolves its own content and gives the help control a name.
    const panels = await evaluate(`([...document.querySelectorAll('[data-panel-help]')].map((node, index) => ({
      index, topic: node.dataset.panelHelp, visible: node.checkVisibility(),
      named: Boolean(node.querySelector(':scope > .panel-help, :scope > summary > .panel-help')?.getAttribute('aria-label'))
    })))`);
    for (const panel of panels) {
      assert(panel.named, `${screen}: panel has no accessible help name: ${panel.topic}`);
      if (!panel.visible) continue;
      const reachable = await evaluate(`(() => {
        const panel = document.querySelectorAll('[data-panel-help]')[${panel.index}];
        const button = panel.querySelector(':scope > .panel-help, :scope > summary > .panel-help');
        button.scrollIntoView({block:'center'});
        const r = button.getBoundingClientRect();
        return document.elementFromPoint(r.left + r.width/2, r.top + r.height/2) === button;
      })()`);
      assert(reachable, `${screen}: help control is obscured: ${panel.topic}`);
      await evaluate(`(() => {
        const panel = document.querySelectorAll('[data-panel-help]')[${panel.index}];
        const button = panel.querySelector(':scope > .panel-help, :scope > summary > .panel-help');
        button.focus(); button.click();
      })()`);
      const opened = await evaluate(`(() => {
        const dialog = document.querySelector('#ui-help-dialog');
        return {open: dialog.open, topics: [...dialog.querySelectorAll('[data-help-topic]:not([hidden])')].map(n => n.dataset.helpTopic),
          focused: dialog.contains(document.activeElement), hash: location.hash,
          content: dialog.innerText};
      })()`);
      assert(opened.open && opened.focused, `${screen}: help must open and receive focus`);
      assert.deepEqual(opened.topics, [panel.topic]);
      assert.equal(opened.hash, `#ui-help-topic-${panel.topic}`);
      assert.match(opened.content, /Назначение[\s\S]*Поля и состояния[\s\S]*Действия и ограничения/);
      const values = await evaluate(`[...document.querySelectorAll('[data-panel-help]')[${panel.index}].querySelectorAll('[data-full-value]')].map(n => n.dataset.fullValue)`);
      for (const value of values) assert(opened.content.includes(value), `${screen}: full value retained in contextual Help`);
      await key("Escape", 27);
      assert(await evaluate("!document.querySelector('#ui-help-dialog').open && document.activeElement.classList.contains('panel-help')"), `${screen}: Escape/focus restoration`);
      helpChecks++;
    }
    // Native keyboard activation, modal focus containment and direct anchors.
    await evaluate("history.replaceState({g9: {focus: 'retained'}}, '', location.href)");
    await evaluate("document.querySelector('.panel-help').focus()");
    await key("Enter", 13);
    assert(await evaluate("document.querySelector('#ui-help-dialog').open"), `${screen}: Enter opens help`);
    await key("Tab", 9, 8);
    assert(await evaluate("document.activeElement.closest('#ui-help-dialog') !== null"), `${screen}: focus trapped`);
    await key("Escape", 27);
    assert.equal(await evaluate("history.state?.g9?.focus"), "retained", `${screen}: help preserves work navigation state`);
    await evaluate("document.querySelector('.ui-help-launch').focus()");
    await key(" ", 32);
    assert(await evaluate("document.querySelector('#ui-help-dialog').open && !document.querySelector('#ui-help-index').hidden"), `${screen}: Space opens general Help`);
    await key("Escape", 27);
    await evaluate("location.hash = '#ui-help-topic-warnings'");
    await client.waitForExpression("document.querySelector('#ui-help-dialog').open", sessionId);
    assert(await evaluate("!document.querySelector('#ui-help-topic-warnings').hidden"));
    await key("Escape", 27);

    // Accessibility and visible-label contracts. Tabs and dataset choices retain names.
    const actions = await evaluate(`([...document.querySelectorAll('[data-ui-icon]')].map(node => ({
      id: node.id, kind: node.dataset.uiKind,
      label: node.getAttribute('aria-label'), title: node.title,
      icon: Boolean(node.querySelector(':scope > svg[aria-hidden="true"]')),
      text: node.querySelector(':scope > span')?.className,
      visible: node.checkVisibility(),
      width: node.getBoundingClientRect().width, height: node.getBoundingClientRect().height,
    })))`);
    for (const action of actions) {
      assert(action.label && action.title && action.icon, `${screen}: accessible icon action ${JSON.stringify(action)}`);
      assert.equal(action.text, action.kind === "primary" ? "ui-action-label" : "ui-sr-only");
      if (action.visible) assert(action.width >= 32 && action.height >= 32, `${screen}: action hit area ${JSON.stringify(action)}`);
    }
    await evaluate("document.querySelector('.panel-help').focus()");
    assert(await evaluate("parseFloat(getComputedStyle(document.activeElement).outlineWidth) >= 2"), `${screen}: visible focus`);
    const tree = await client.send("Accessibility.getFullAXTree", {}, sessionId);
    assert(tree.nodes.some(node => node.role?.value === "button" && node.name?.value?.startsWith("Справка:")), `${screen}: named help in accessibility tree`);

    for (const width of [320, 360, 768, 1440]) {
      await viewport(width);
      await evaluate("document.activeElement.blur(); window.scrollTo(0, 0)");
      await checkLayout(screen + ' expanded states', width);
    }
  }
  // Replacing a dynamic button label/panel must retain accessibility without changing its action.
  await evaluate(`(() => {
    const button = document.querySelector('[data-ui-kind="primary"]');
    button.textContent = 'Сохранить коррекцию';
    document.querySelector('[data-panel-help]').append(Object.assign(document.createElement('button'), {textContent:'Переименовать'}));
    const dynamic = document.querySelector('[data-panel-help] button:last-child');
    dynamic.dataset.uiIcon = 'edit'; dynamic.dataset.uiKind = 'utility';
    dynamic.replaceWith(dynamic.cloneNode(true));
  })()`);
  await client.waitForExpression("document.querySelector('[data-ui-kind=primary]').getAttribute('aria-label') === 'Сохранить коррекцию'", sessionId);
  await evaluate(`(() => {
    const button = document.createElement('button');
    button.id = 'keyboard-utility'; button.type = 'button'; button.textContent = 'Обновить';
    button.dataset.uiIcon = 'refresh'; button.dataset.uiKind = 'utility'; button.dataset.activations = '0';
    button.addEventListener('click', () => button.dataset.activations = String(Number(button.dataset.activations) + 1));
    const panel = document.querySelector('[data-panel-help]');
    panel.replaceChildren(button);
  })()`);
  await client.waitForExpression("Boolean(document.querySelector('#keyboard-utility > .ui-icon') && document.querySelector('[data-panel-help] > .panel-help'))", sessionId);
  await evaluate("document.querySelector('#keyboard-utility').focus()");
  await key(" ", 32);
  await key("Enter", 13);
  assert.equal(await evaluate("document.querySelector('#keyboard-utility').dataset.activations"), "2", "Utility supports Space and Enter");
  assert(await evaluate("parseFloat(getComputedStyle(document.activeElement).outlineWidth) >= 2"), "Utility has visible keyboard focus");
  assert.deepEqual(errors, [], "No UI JavaScript errors");
  const report = {screens: Object.keys(fixtures).length, viewports:[320,360,768,1440], panel_help_checks:helpChecks, keyboard_and_accessibility:true, layout_checks:layoutChecks};
  if (process.env.UI_REPORT_PATH) writeFileSync(process.env.UI_REPORT_PATH, JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report));
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}
