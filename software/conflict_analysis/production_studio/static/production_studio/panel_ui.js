/* Shared presentation only: no Foundation requests, writes or browser storage. */
(() => {
  "use strict";
  const dialog = document.getElementById("ui-help-dialog");
  if (!dialog) return;
  const topics = [...dialog.querySelectorAll("[data-help-topic]")];
  const index = document.getElementById("ui-help-index");
  const heading = document.getElementById("ui-help-title");
  let opener = null;
  let returnHash = "";
  const helpPrefix = "#ui-help-topic-";
  const icons = {
    open: "M3 7h7l2 3h9l-3 10H3z M3 7V4h7l2 3h7v3",
    plus: "M12 5v14 M5 12h14",
    refresh: "M20 4v6h-6 M4 20v-6h6 M5 9a7 7 0 0 1 12-4l3 5 M4 14l3 5a7 7 0 0 0 12-4",
    save: "M4 3h13l4 4v14H3V3z M7 3v6h10V3 M7 21v-8h10v8",
    download: "M12 3v12 M7 10l5 5 5-5 M4 16v5h16v-5",
    upload: "M12 16V4 M7 9l5-5 5 5 M4 16v5h16v-5",
    check: "M4 12l5 5L20 6",
    close: "M6 6l12 12 M6 18L18 6",
    trash: "M3 6h18 M9 6V3h6v3 M5 6l1 15h12l1-15 M10 10v7 M14 10v7",
    edit: "M4 16L16 4l4 4L8 20H4z M13 7l4 4",
    up: "M12 20V4 M5 11l7-7 7 7",
    down: "M12 4v16 M5 13l7 7 7-7",
    left: "M20 12H4 M11 5l-7 7 7 7",
    right: "M4 12h16 M13 5l7 7-7 7",
    copy: "M8 8h13v13H8z M16 8V3H3v13h5",
    lock: "M5 10h14v11H5z M8 10V7a4 4 0 0 1 8 0v3 M12 14v3",
    archive: "M3 3h18v5H3z M5 8v13h14V8 M9 12h6",
    external: "M14 3h7v7 M21 3L10 14 M10 3H3v18h18v-7",
    link: "M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-2 2 M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l2-2",
    document: "M5 3h10l4 4v14H5z M14 3v5h5 M8 12h8 M8 16h8",
    help: "M9 8a3 3 0 1 1 5 3c-2 1-2 2-2 4 M12 18v1",
    send: "M3 3l18 9-18 9 4-9z M7 12h14",
    switch: "M4 7h15l-4-4 M20 17H5l4 4 M19 7l-4 4 M5 17l4-4",
    quote: "M4 5h6v7H7c0 3-1 5-3 6 M14 5h6v7h-3c0 3-1 5-3 6",
    book: "M12 5v16 M12 5C9 3 6 3 3 4v15c3-1 6-1 9 2 M12 5c3-2 6-2 9-1v15c-3-1-6-1-9 2",
  };

  function decorateAction(node) {
    if (node.querySelector(":scope > .ui-icon")) return;
    // Original labels stay in the accessible name, including labels updated by the app.
    const label = (node.textContent.trim() || node.getAttribute("aria-label") || node.title).replace(/\s+/g, " ");
    if (!label) return;
    node.setAttribute("aria-label", label);
    if (!node.title || node.title === node.dataset.uiActionName) node.title = label;
    node.dataset.uiActionName = label;
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.classList.add("ui-icon");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    const path = document.createElementNS(svg.namespaceURI, "path");
    path.setAttribute("d", icons[node.dataset.uiIcon] || icons.open);
    svg.append(path);
    const text = document.createElement("span");
    text.className = node.dataset.uiKind === "primary" ? "ui-action-label" : "ui-sr-only";
    text.textContent = node.dataset.uiLabel || label;
    node.replaceChildren(svg, text);
  }

  const fullValueSelector = ".ui-title, .ui-result-main h1, .ui-truncate, .identity-grid dd, .identity-list dd, .ui-data dd, .context-title > span, .projection-badge, .g8-status, .tree-label, .experiment-tabs [data-experiment-id], #workspace-name, #experiment-name, #project-name:not(input), #definition-label, #authoring-operation-key, #last-receipt-sha, #help-identity";
  function exposeFullValues(root) {
    const nodes = root.matches?.(fullValueSelector) ? [root] : [];
    const parent = root.closest?.(fullValueSelector);
    if (parent && parent !== root) nodes.push(parent);
    nodes.push(...root.querySelectorAll(fullValueSelector));
    for (const node of nodes) {
      const value = node.textContent.trim();
      if (value) { node.title = value; node.dataset.fullValue = value; }
    }
  }

  function enhance(root) {
    exposeFullValues(root);
    const candidates = root.matches?.("[data-ui-icon], [data-panel-help]") ? [root] : [];
    candidates.push(...root.querySelectorAll("[data-ui-icon], [data-panel-help]"));
    for (const node of candidates) {
      if (node.dataset.uiIcon) decorateAction(node);
      if (!node.dataset.panelHelp || node.querySelector(":scope > .panel-help, :scope > summary > .panel-help")) continue;
      const topic = topics.find(item => item.dataset.helpTopic === node.dataset.panelHelp);
      if (!topic) continue;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "panel-help";
      button.textContent = "?";
      button.dataset.helpOpen = node.dataset.panelHelp;
      button.title = `Справка: ${topic.dataset.helpTitle}`;
      button.setAttribute("aria-label", button.title);
      button.setAttribute("aria-haspopup", "dialog");
      button.setAttribute("aria-controls", dialog.id);
      // Keep help visible when details is collapsed, without replacing its summary.
      (node.tagName === "DETAILS" ? node.querySelector(":scope > summary") : node).append(button);
    }
  }

  function showHelp(id, source) {
    const topic = topics.find(item => item.dataset.helpTopic === id);
    if (id !== "all" && !topic) return;
    if (!dialog.open) {
      opener = source || document.activeElement;
      returnHash = location.hash.startsWith(helpPrefix) ? "" : location.hash;
    }
    heading.textContent = topic ? topic.dataset.helpTitle : "Справка интерфейса";
    index.hidden = Boolean(topic);
    for (const item of topics) item.hidden = item !== topic;
    dialog.querySelector(".ui-help-detail")?.remove();
    const detail = source?.closest("[data-panel-help]")?.querySelector(":scope > template.ui-panel-detail");
    if (detail && topic) {
      const content = document.createElement("div");
      content.className = "ui-help-detail";
      content.append(detail.content.cloneNode(true));
      topic.append(content);
    }
    const values = source?.closest("[data-panel-help]")?.querySelectorAll("[data-full-value]");
    if (topic && values?.length) {
      const content = dialog.querySelector(".ui-help-detail") || document.createElement("div");
      content.className = "ui-help-detail";
      const title = document.createElement("h3");
      title.textContent = "Полные значения";
      content.append(title);
      for (const value of new Set([...values].map(node => node.dataset.fullValue))) {
        const row = document.createElement("p");
        row.textContent = value;
        content.append(row);
      }
      topic.append(content);
    }
    document.getElementById("ui-help-all").hidden = !topic;
    if (!dialog.open) dialog.showModal();
    dialog.scrollTop = 0;
    // replaceState keeps repeated contextual help out of the work navigation history.
    history.replaceState(history.state, "", `${helpPrefix}${id}`);
    document.getElementById("ui-help-close").focus();
  }

  for (const topic of [...topics].sort((a, b) => a.dataset.helpTitle.localeCompare(b.dataset.helpTitle, "ru"))) {
    const link = document.createElement("a");
    link.href = `#${topic.id}`;
    link.dataset.helpOpen = topic.dataset.helpTopic;
    link.textContent = topic.dataset.helpTitle;
    index.append(link);
  }
  document.addEventListener("click", event => {
    const control = event.target.closest("[data-help-open]");
    if (!control) return;
    event.preventDefault();
    showHelp(control.dataset.helpOpen, control);
  });
  function closeHelp() {
    dialog.close();
    history.replaceState(history.state, "", `${location.pathname}${location.search}${returnHash}`);
    if (opener?.isConnected) opener.focus();
  }
  document.getElementById("ui-help-close").addEventListener("click", closeHelp);
  // Native modal dialogs trap focus; restore it synchronously on Escape as well.
  dialog.addEventListener("cancel", event => {
    event.preventDefault();
    closeHelp();
  });
  const openHash = () => {
    if (location.hash.startsWith(helpPrefix)) showHelp(location.hash.slice(helpPrefix.length));
  };
  window.addEventListener("hashchange", openHash);
  enhance(document);
  // Evidence panels and record actions are inserted/replaced after Foundation reads.
  new MutationObserver(records => {
    for (const record of records) {
      if (record.target.closest?.("#ui-help-dialog")) continue;
      exposeFullValues(record.target);
      if (record.target.matches?.("[data-ui-icon]")) decorateAction(record.target);
      if (record.target.matches?.("[data-panel-help]")) enhance(record.target);
      for (const node of record.addedNodes) if (node.nodeType === Node.ELEMENT_NODE) enhance(node);
    }
  }).observe(document.body, { childList: true, subtree: true });
  // Loading/reloading a work page never opens Help or takes keyboard focus.
  // Help links still resolve through the click/hashchange handlers above.
})();
