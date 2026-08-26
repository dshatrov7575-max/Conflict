#!/usr/bin/env node

import {
  assert,
  parseArguments,
  printUsage,
  runBrowserGate,
} from "./cdp_client.mjs";

const PHASE = "PHASE_3_DOM_SAFETY";
const options = parseArguments(process.argv.slice(2), PHASE);

if (options.help) {
  printUsage("studio_showcase/browser_tests/phase3_dom_safety.mjs", PHASE);
  process.exit(0);
}

async function executePhase3(page) {
  const interactionEvidence = await page.evaluate(String.raw`
(async () => {
  const waitUntil = async (predicate, description, timeoutMs = 10000) => {
    const deadline = performance.now() + timeoutMs;
    while (performance.now() < deadline) {
      if (predicate()) return;
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    throw new Error("Timed out waiting for " + description);
  };
  const fixtureCardinality = () => ({
    analyticalElements: window.StudioShowcase.getSession().analyticalElements.length,
    actors: window.StudioShowcase.getSession().actors.length,
    renderedElementRows: document.querySelectorAll("#elements-editor-body tr").length,
    renderedActorRows: document.querySelectorAll("#actors-editor-body tr").length,
  });
  const dispatchFile = (text, filename) => {
    const file = new File([text], filename, { type: "application/json;charset=utf-8" });
    const transfer = new DataTransfer();
    transfer.items.add(file);
    const input = document.getElementById("session-file-input");
    input.files = transfer.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
    return { filename: file.name, bytes: file.size, fileCount: input.files.length };
  };

  await window.StudioShowcase.fixture("6x8");
  await waitUntil(() => window.StudioShowcase.getSession().actors.length === 8, "6x8 fixture");
  const fixture6x8 = fixtureCardinality();
  await window.StudioShowcase.fixture("3x4");
  await waitUntil(() => window.StudioShowcase.getSession().actors.length === 4, "3x4 fixture");
  const fixture3x4 = fixtureCardinality();

  window.StudioShowcase.setView("elements", false);
  const beforeOrder = window.StudioShowcase.getSession().analyticalElements.map((row) => row.id);
  const firstNameInput = document.querySelector(
    '#elements-editor-body tr[data-index="0"] input[data-field="name"]',
  );
  firstNameInput.focus();
  firstNameInput.dispatchEvent(new KeyboardEvent("keydown", {
    key: "ArrowDown",
    altKey: true,
    bubbles: true,
    cancelable: true,
  }));
  await waitUntil(
    () => window.StudioShowcase.getSession().analyticalElements[1].id === beforeOrder[0],
    "Alt+ArrowDown row reorder",
  );
  const afterOrder = window.StudioShowcase.getSession().analyticalElements.map((row) => row.id);
  const focusedRow = document.activeElement.closest("tr[data-stable-id]");
  const keyboardReorder = {
    movedFromZeroToOne: afterOrder[1] === beforeOrder[0] && afterOrder[0] === beforeOrder[1],
    focusPreservedOnMovedStableId: focusedRow?.dataset.stableId === beforeOrder[0],
    focusedField: document.activeElement.dataset.field || null,
  };

  const evidenceKinds = [...document.querySelectorAll(".evidence-trace .trace-kind")]
    .map((element) => element.textContent.trim());
  const documentTab = document.getElementById("tab-document");
  documentTab.click();
  documentTab.focus();
  documentTab.dispatchEvent(new KeyboardEvent("keydown", {
    key: "ArrowRight", bubbles: true, cancelable: true,
  }));
  const chatAfterArrow = {
    selected: document.getElementById("tab-chat").getAttribute("aria-selected") === "true",
    panelVisible: !document.getElementById("panel-chat").hidden,
    disabledControl: Boolean(document.querySelector("#panel-chat button[disabled]")),
    providerRagBoundary: document.getElementById("panel-chat").textContent.includes("provider/RAG gate"),
  };
  document.getElementById("tab-chat").dispatchEvent(new KeyboardEvent("keydown", {
    key: "ArrowRight", bubbles: true, cancelable: true,
  }));
  const helpAfterArrow = {
    selected: document.getElementById("tab-help").getAttribute("aria-selected") === "true",
    panelVisible: !document.getElementById("panel-help").hidden,
    version: document.querySelector("#panel-help .help-version code").textContent.trim(),
  };
  document.querySelector('[data-help-topic="validation"]').click();
  const helpTopic = {
    selected: document.getElementById("tab-help").getAttribute("aria-selected") === "true",
    hasHeading: Boolean(document.querySelector("#help-content h2")),
    hasBody: Boolean(document.querySelector("#help-content p")),
  };

  globalThis.__ownerTestXssExecuted = 0;
  const xssPayload = structuredClone(window.StudioShowcase.getSession());
  const projectXss = '<img src=x onerror="globalThis.__ownerTestXssExecuted += 1">';
  const nameXss = '</input><script>globalThis.__ownerTestXssExecuted += 10</script>';
  const detailXss = '<svg onload="globalThis.__ownerTestXssExecuted += 100">XSS-shaped text</svg>';
  xssPayload.project.name = projectXss;
  xssPayload.analyticalElements[0].name = nameXss;
  xssPayload.analyticalElements[0].definition = detailXss;
  xssPayload.actors[0].name = '<iframe srcdoc="<script>parent.__ownerTestXssExecuted += 1000</script>"></iframe>';
  xssPayload.actors[0].description = '<object data="javascript:globalThis.__ownerTestXssExecuted += 10000"></object>';
  const xssFile = dispatchFile(JSON.stringify(xssPayload, null, 2) + "\n", "xss-shaped-session.json");
  await waitUntil(
    () => window.StudioShowcase.getSession().project.name === projectXss,
    "XSS-shaped File import",
  );
  await new Promise((resolve) => setTimeout(resolve, 100));
  const xssSafety = {
    file: xssFile,
    sentinel: globalThis.__ownerTestXssExecuted,
    projectValuePreserved: document.getElementById("project-name").value === projectXss,
    nameValuePreserved: document.querySelector(
      '#elements-editor-body tr[data-index="0"] input[data-field="name"]',
    ).value === nameXss,
    detailValuePreserved: document.querySelector(
      '#elements-editor-body tr[data-index="0"] textarea[data-field="definition"]',
    ).value === detailXss,
    executableNodesInEditors: document.querySelectorAll(
      "#elements-editor-body script, #elements-editor-body img, #elements-editor-body svg, "
      + "#actors-editor-body script, #actors-editor-body iframe, #actors-editor-body object",
    ).length,
  };

  window.StudioShowcase.resetLayout();
  const splitter = document.getElementById("splitter-left");
  const layoutBefore = window.StudioShowcase.getLayout();
  splitter.focus();
  splitter.dispatchEvent(new KeyboardEvent("keydown", {
    key: "ArrowRight", bubbles: true, cancelable: true,
  }));
  const layoutAfterKeyboard = window.StudioShowcase.getLayout();
  const storedLayout = JSON.parse(localStorage.getItem(
    window.StudioShowcase.constants.LAYOUT_KEY,
  ));

  return {
    fixtures: { "6x8": fixture6x8, "3x4": fixture3x4 },
    keyboardReorder,
    evidenceKinds,
    rightPanelBoundaries: { chatAfterArrow, helpAfterArrow, helpTopic },
    xssSafety,
    layoutMutation: {
      before: layoutBefore,
      after: layoutAfterKeyboard,
      ariaNow: Number(splitter.getAttribute("aria-valuenow")),
      stored: storedLayout,
    },
    runtimeErrors: globalThis.__ownerTestRuntimeErrors,
  };
})()
`, 30_000);

  assert(
    JSON.stringify(interactionEvidence.fixtures["6x8"]) === JSON.stringify({
      analyticalElements: 6, actors: 8, renderedElementRows: 6, renderedActorRows: 8,
    }),
    "The 6x8 fixture does not render exact cardinalities.",
    interactionEvidence,
  );
  assert(
    JSON.stringify(interactionEvidence.fixtures["3x4"]) === JSON.stringify({
      analyticalElements: 3, actors: 4, renderedElementRows: 3, renderedActorRows: 4,
    }),
    "The 3x4 fixture does not render exact cardinalities.",
    interactionEvidence,
  );
  assert(interactionEvidence.keyboardReorder.movedFromZeroToOne, "Keyboard reorder failed.", interactionEvidence);
  assert(interactionEvidence.keyboardReorder.focusPreservedOnMovedStableId, "Keyboard reorder lost focus.", interactionEvidence);
  assert(interactionEvidence.keyboardReorder.focusedField === "name", "Keyboard reorder changed the focused field.", interactionEvidence);
  assert(
    JSON.stringify(interactionEvidence.evidenceKinds)
      === JSON.stringify(["Assessment", "Fact", "Fragment", "DocumentVersion", "Source"]),
    "Evidence trace boundary changed.",
    interactionEvidence,
  );
  const boundaries = interactionEvidence.rightPanelBoundaries;
  assert(boundaries.chatAfterArrow.selected && boundaries.chatAfterArrow.panelVisible, "Chat tab keyboard navigation failed.", boundaries);
  assert(boundaries.chatAfterArrow.disabledControl && boundaries.chatAfterArrow.providerRagBoundary, "Disabled chat boundary changed.", boundaries);
  assert(boundaries.helpAfterArrow.selected && boundaries.helpAfterArrow.panelVisible, "Help tab keyboard navigation failed.", boundaries);
  assert(boundaries.helpAfterArrow.version === "HELP_LOCAL_V1", "Local Help version changed.", boundaries);
  assert(boundaries.helpTopic.selected && boundaries.helpTopic.hasHeading && boundaries.helpTopic.hasBody, "Context help did not open.", boundaries);
  assert(interactionEvidence.xssSafety.sentinel === 0, "XSS-shaped imported text executed.", interactionEvidence.xssSafety);
  assert(interactionEvidence.xssSafety.projectValuePreserved, "XSS-shaped project name was not preserved as text.", interactionEvidence.xssSafety);
  assert(interactionEvidence.xssSafety.nameValuePreserved, "XSS-shaped row name was not preserved as text.", interactionEvidence.xssSafety);
  assert(interactionEvidence.xssSafety.detailValuePreserved, "XSS-shaped detail was not preserved as text.", interactionEvidence.xssSafety);
  assert(interactionEvidence.xssSafety.executableNodesInEditors === 0, "XSS-shaped import created executable editor nodes.", interactionEvidence.xssSafety);
  assert(interactionEvidence.layoutMutation.after.left === interactionEvidence.layoutMutation.before.left + 12, "Keyboard splitter increment failed.", interactionEvidence.layoutMutation);
  assert(interactionEvidence.layoutMutation.ariaNow === interactionEvidence.layoutMutation.after.left, "Splitter ARIA value diverged.", interactionEvidence.layoutMutation);
  assert(interactionEvidence.layoutMutation.stored.left === interactionEvidence.layoutMutation.after.left, "Splitter layout was not persisted.", interactionEvidence.layoutMutation);
  assert(interactionEvidence.runtimeErrors.length === 0, "Browser runtime errors were observed before reload.", interactionEvidence.runtimeErrors);

  await page.goto(options.baseUrl);
  const layoutEvidence = await page.evaluate(String.raw`
(() => {
  const restored = window.StudioShowcase.getLayout();
  const restoredAria = Number(document.getElementById("splitter-left").getAttribute("aria-valuenow"));
  const storageBeforeReset = JSON.parse(localStorage.getItem(window.StudioShowcase.constants.LAYOUT_KEY));
  window.StudioShowcase.resetLayout();
  const reset = window.StudioShowcase.getLayout();
  const resetAria = Number(document.getElementById("splitter-left").getAttribute("aria-valuenow"));
  const storageAfterReset = JSON.parse(localStorage.getItem(window.StudioShowcase.constants.LAYOUT_KEY));
  return { restored, restoredAria, storageBeforeReset, reset, resetAria, storageAfterReset };
})()
`);
  assert(layoutEvidence.restored.left === interactionEvidence.layoutMutation.after.left, "Layout did not restore after a real page reload.", layoutEvidence);
  assert(layoutEvidence.restoredAria === layoutEvidence.restored.left, "Restored splitter ARIA value diverged.", layoutEvidence);
  assert(layoutEvidence.storageBeforeReset.left === layoutEvidence.restored.left, "Stored layout diverged after reload.", layoutEvidence);
  assert(layoutEvidence.reset.left === interactionEvidence.layoutMutation.before.left, "Layout reset did not restore the default left width.", layoutEvidence);
  assert(layoutEvidence.resetAria === layoutEvidence.reset.left, "Reset splitter ARIA value diverged.", layoutEvidence);
  assert(layoutEvidence.storageAfterReset.left === layoutEvidence.reset.left, "Reset layout was not persisted.", layoutEvidence);

  const resourceEvidence = await page.evaluate(String.raw`
(async () => {
  const waitUntil = async (predicate, description, timeoutMs = 20000) => {
    const deadline = performance.now() + timeoutMs;
    while (performance.now() < deadline) {
      if (predicate()) return;
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    throw new Error("Timed out waiting for " + description);
  };
  await window.StudioShowcase.fixture("3x4");
  await waitUntil(() => window.StudioShowcase.getSession().actors.length === 4, "3x4 resource fixture");
  const addElement = document.querySelector('[data-add-row="analyticalElements"]');
  const addActor = document.querySelector('[data-add-row="actors"]');
  while (window.StudioShowcase.getSession().analyticalElements.length < 101) addElement.click();
  while (window.StudioShowcase.getSession().actors.length < 100) addActor.click();
  const payload = window.StudioShowcase.getSession();
  const payloadBytes = new TextEncoder().encode(JSON.stringify(payload)).byteLength;
  const preview = document.getElementById("structure-preview");
  preview.replaceChildren();
  let matrixCellAllocations = 0;
  let matrixCellMutations = 0;
  const originalCreateElement = document.createElement.bind(document);
  document.createElement = (name, options) => {
    if (String(name).toLowerCase() === "td") matrixCellAllocations += 1;
    return originalCreateElement(name, options);
  };
  const observer = new MutationObserver((records) => {
    for (const record of records) {
      for (const node of record.addedNodes) {
        if (node.nodeType !== Node.ELEMENT_NODE) continue;
        if (node.matches?.(".preview-grid td")) matrixCellMutations += 1;
        matrixCellMutations += node.querySelectorAll?.(".preview-grid td").length || 0;
      }
    }
  });
  observer.observe(preview, { childList: true, subtree: true });
  let previewResult;
  try {
    previewResult = window.StudioShowcase.showPreview();
  } finally {
    document.createElement = originalCreateElement;
    observer.disconnect();
  }
  const diagnosticsText = document.getElementById("diagnostics").textContent;
  return {
    analyticalElements: payload.analyticalElements.length,
    actors: payload.actors.length,
    prospectiveCells: payload.analyticalElements.length * payload.actors.length,
    payloadBytes,
    belowTwoMegabytes: payloadBytes < 2 * 1024 * 1024,
    previewResult,
    diagnostic: diagnosticsText.includes("PREVIEW_CELL_BUDGET_EXCEEDED"),
    matrixCellAllocations,
    matrixCellMutations,
    matrixCellsInDom: preview.querySelectorAll(".preview-grid td").length,
    previewTableInDom: Boolean(preview.querySelector(".preview-grid")),
    runtimeErrors: globalThis.__ownerTestRuntimeErrors,
  };
})()
`, 60_000);

  assert(resourceEvidence.analyticalElements === 101 && resourceEvidence.actors === 100, "Oversized browser fixture cardinality is wrong.", resourceEvidence);
  assert(resourceEvidence.prospectiveCells === 10_100, "Oversized preview is not exactly 10,100 prospective cells.", resourceEvidence);
  assert(resourceEvidence.belowTwoMegabytes, "Oversized browser payload exceeded the 2 MB input boundary.", resourceEvidence);
  assert(resourceEvidence.previewResult === false, "Oversized preview was not refused.", resourceEvidence);
  assert(resourceEvidence.diagnostic, "Preview budget diagnostic was not rendered.", resourceEvidence);
  assert(resourceEvidence.matrixCellAllocations === 0, "Preview allocated matrix td cells before refusal.", resourceEvidence);
  assert(resourceEvidence.matrixCellMutations === 0, "Preview inserted matrix cells before refusal.", resourceEvidence);
  assert(resourceEvidence.matrixCellsInDom === 0 && !resourceEvidence.previewTableInDom, "Preview matrix remained in the DOM after refusal.", resourceEvidence);
  assert(resourceEvidence.runtimeErrors.length === 0, "Browser runtime errors were observed in the resource gate.", resourceEvidence.runtimeErrors);

  return {
    ...interactionEvidence,
    layoutRestoreReset: layoutEvidence,
    resourceBudget: resourceEvidence,
  };
}

await runBrowserGate(options, executePhase3);
