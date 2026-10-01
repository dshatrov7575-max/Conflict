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
  for (const [screen] of Object.entries(fixtures)) {
    await viewport(1280);
    await client.send("Page.navigate", { url: `${base}/${screen}` }, sessionId);
    await client.waitForExpression("Boolean(document.querySelector('.panel-help') && document.querySelector('[data-ui-icon] > .ui-icon'))", sessionId);
    await evaluate(`(() => {
      // Inspect states supplied by the real templates, including initially closed panels.
      for (const node of document.querySelectorAll('[hidden]')) {
        if (!node.closest('#ui-help-dialog') && node.tagName !== 'INPUT') node.hidden = false;
      }
      const app = document.querySelector('#player-app');
      if (app) app.dataset.state = 'ready';
      const studio = document.querySelector('#studio-app');
      if (studio) studio.dataset.state = 'ready';
      const template = document.querySelector('#g9-evidence-template');
      if (template) {
        document.querySelector('#panel-document').removeAttribute('data-panel-help');
        document.querySelector('#panel-document').replaceChildren(template.content.cloneNode(true));
      }
      for (const id of ['workspace-name', 'project-name', 'definition-label']) {
        const node = document.getElementById(id);
        if (node && node.tagName !== 'INPUT') node.textContent = 'Рабочий контекст — ' + 'ДлинноеЗначение'.repeat(5);
      }
      for (const node of document.querySelectorAll('dd, #project-name, #workspace-name')) {
        if (node.tagName !== 'INPUT') node.textContent ||= 'ОченьДлинноеЗначение'.repeat(8);
      }
    })()`);
    await client.waitForExpression("[...document.querySelectorAll('[data-panel-help]')].every(n => n.querySelector(':scope > .panel-help, :scope > summary > .panel-help'))", sessionId);

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

    for (const width of [360, 768, 1280, 1440]) {
      await viewport(width);
      await evaluate("window.scrollTo(0, 0)");
      const layout = await evaluate(`(() => {
        const panels = [...document.querySelectorAll('[data-panel-help]')].filter(n => n.checkVisibility());
        return {
          width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth, x: window.scrollX,
          overflow: [...document.querySelectorAll('body *')].filter(n => n.getBoundingClientRect().right > document.documentElement.clientWidth + 1).slice(0, 12).map(n => [n.tagName, n.id, n.className, n.getBoundingClientRect().width]),
          controls: panels.map(n => {
            const b = n.querySelector(':scope > .panel-help, :scope > summary > .panel-help');
            const r = b.getBoundingClientRect(), p = n.getBoundingClientRect();
            return {topic: n.dataset.panelHelp, width: r.width, height: r.height, right: p.right-r.right, top:r.top-p.top};
          })
        };
      })()`);
      if (layout.scroll > layout.width + 1 && process.env.UI_SCREENSHOT_DIR) {
        mkdirSync(process.env.UI_SCREENSHOT_DIR, { recursive: true });
        const shot = await client.send("Page.captureScreenshot", { format: "png" }, sessionId);
        writeFileSync(path.join(process.env.UI_SCREENSHOT_DIR, "overflow.png"), Buffer.from(shot.data, "base64"));
        console.error(await evaluate(`JSON.stringify([...document.querySelectorAll('body *')].filter(n => n.checkVisibility() && n.scrollWidth > n.clientWidth + 1).map(n => [n.tagName,n.id,n.className,n.clientWidth,n.scrollWidth,getComputedStyle(n).overflowX]))`));
      }
      assert(layout.scroll <= layout.width + 1, `${screen} @${width}: horizontal page overflow ${layout.scroll}/${layout.width}: ${JSON.stringify(layout)}`);
      for (const control of layout.controls) {
        assert(control.width >= 28 && control.height >= 28, `${screen}: help hit area ${JSON.stringify(control)}`);
        assert(control.right >= 0 && control.right < 20 && control.top >= 0 && control.top < 30,
          `${screen} @${width}: help at top-right ${JSON.stringify(control)}`);
      }
      if (process.env.UI_SCREENSHOT_DIR && [360, 1440].includes(width) && /scenario_modeling|workspace|audited_draft_definition/.test(screen)) {
        await evaluate("window.scrollTo(0, 0)");
        mkdirSync(process.env.UI_SCREENSHOT_DIR, { recursive: true });
        const shot = await client.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false }, sessionId);
        writeFileSync(path.join(process.env.UI_SCREENSHOT_DIR, `${screen.replaceAll('/', '-')}-${width}.png`), Buffer.from(shot.data, "base64"));
      }
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
  console.log(JSON.stringify({screens: Object.keys(fixtures).length, viewports:[360,768,1280,1440], panel_help_checks:helpChecks, keyboard_and_accessibility:true}));
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}
