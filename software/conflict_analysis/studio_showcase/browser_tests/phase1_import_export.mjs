#!/usr/bin/env node

import {
  assert,
  parseArguments,
  printUsage,
  runBrowserGate,
} from "./cdp_client.mjs";

const PHASE = "PHASE_1_IMPORT_EXPORT";
const options = parseArguments(process.argv.slice(2), PHASE);

if (options.help) {
  printUsage("studio_showcase/browser_tests/phase1_import_export.mjs", PHASE);
  process.exit(0);
}

async function executePhase1(page) {
  const evidence = await page.evaluate(String.raw`
(async () => {
  const waitUntil = async (predicate, description, timeoutMs = 10000) => {
    const deadline = performance.now() + timeoutMs;
    while (performance.now() < deadline) {
      if (predicate()) return;
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    throw new Error("Timed out waiting for " + description);
  };
  const canonicalJson = (value) => {
    const normalize = (candidate) => {
      if (Array.isArray(candidate)) return candidate.map(normalize);
      if (candidate && typeof candidate === "object") {
        return Object.fromEntries(
          Object.keys(candidate).sort().map((key) => [key, normalize(candidate[key])]),
        );
      }
      return candidate;
    };
    return JSON.stringify(normalize(value));
  };
  const sha256 = async (text) => {
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  };
  const dispatchFile = (text, filename) => {
    const file = new File([text], filename, { type: "application/json;charset=utf-8" });
    const transfer = new DataTransfer();
    transfer.items.add(file);
    const input = document.getElementById("session-file-input");
    input.files = transfer.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
    return { filename: file.name, bytes: file.size, type: file.type, fileCount: input.files.length };
  };

  const fixtureResponse = await fetch(new URL("api/fixtures/3x4/", location.href));
  if (!fixtureResponse.ok) throw new Error("Cannot load the 3x4 fixture for the import gate");
  const validPayload = await fixtureResponse.json();
  validPayload.project.name = "OWNER-TEST valid File import";
  validPayload.project.description = "Programmatic File + DataTransfer + change event";
  const validText = JSON.stringify(validPayload, null, 2) + "\n";
  const validFile = dispatchFile(validText, "owner-test-valid-session.json");
  await waitUntil(
    () => window.StudioShowcase.getSession().project.name === validPayload.project.name,
    "valid File import",
  );
  const importedSession = window.StudioShowcase.getSession();
  const importedCanonical = canonicalJson(importedSession);
  const importedCanonicalSha256 = await sha256(importedCanonical);

  const invalidPayload = structuredClone(importedSession);
  invalidPayload.project.name = "";
  const beforeInvalidCanonical = canonicalJson(window.StudioShowcase.getSession());
  const beforeInvalidSha256 = await sha256(beforeInvalidCanonical);
  document.getElementById("diagnostics").replaceChildren();
  const invalidFile = dispatchFile(
    JSON.stringify(invalidPayload, null, 2) + "\n",
    "owner-test-invalid-session.json",
  );
  await waitUntil(
    () => document.getElementById("diagnostics").textContent.includes("PROJECT_NAME_BLANK"),
    "invalid import diagnostics",
  );
  const afterInvalidCanonical = canonicalJson(window.StudioShowcase.getSession());
  const afterInvalidSha256 = await sha256(afterInvalidCanonical);

  globalThis.__ownerTestLastDownload = null;
  document.querySelector('[data-command="export"]').click();
  await waitUntil(() => Boolean(globalThis.__ownerTestLastDownload), "export Blob capture");
  const download = globalThis.__ownerTestLastDownload;
  const exportedBuffer = await download.blob.arrayBuffer();
  const exportedBytes = new Uint8Array(exportedBuffer);
  const exportedText = new TextDecoder("utf-8", { fatal: true }).decode(exportedBytes);
  const exportedSha256 = await sha256(exportedText);
  const exportedPayload = JSON.parse(exportedText);
  const exportedCanonical = canonicalJson(exportedPayload);

  await window.StudioShowcase.fixture("6x8");
  await waitUntil(
    () => window.StudioShowcase.getSession().analyticalElements.length === 6
      && window.StudioShowcase.getSession().actors.length === 8,
    "6x8 mutation before exact re-import",
  );
  const reimportFile = dispatchFile(exportedText, download.filename);
  await waitUntil(
    () => canonicalJson(window.StudioShowcase.getSession()) === exportedCanonical,
    "exact exported JSON re-import",
  );
  const roundTripCanonical = canonicalJson(window.StudioShowcase.getSession());
  const roundTripCanonicalSha256 = await sha256(roundTripCanonical);

  return {
    apiFormat: window.StudioShowcase.constants.SESSION_FORMAT,
    validImport: {
      file: validFile,
      projectName: importedSession.project.name,
      analyticalElements: importedSession.analyticalElements.length,
      actors: importedSession.actors.length,
      canonicalSha256: importedCanonicalSha256,
    },
    invalidImport: {
      file: invalidFile,
      diagnostic: "PROJECT_NAME_BLANK",
      beforeCanonicalSha256: beforeInvalidSha256,
      afterCanonicalSha256: afterInvalidSha256,
      nonMutating: beforeInvalidCanonical === afterInvalidCanonical,
    },
    export: {
      filename: download.filename,
      mimeType: download.blob.type,
      bytes: exportedBytes.byteLength,
      terminalNewline: exportedBytes.at(-1) === 10,
      sha256: exportedSha256,
      contentMatchesImportedSession: exportedCanonical === importedCanonical,
    },
    exactReimport: {
      file: reimportFile,
      canonicalSha256: roundTripCanonicalSha256,
      equalsExportedSession: roundTripCanonical === exportedCanonical,
    },
    runtimeErrors: globalThis.__ownerTestRuntimeErrors,
  };
})()
`, 30_000);

  assert(evidence.apiFormat === "SHOWCASE_SESSION_V1", "Unexpected showcase session format.", evidence);
  assert(evidence.validImport.file.fileCount === 1, "Programmatic File was not assigned to the input.", evidence);
  assert(evidence.validImport.analyticalElements === 3, "Valid import lost 3x4 analytical elements.", evidence);
  assert(evidence.validImport.actors === 4, "Valid import lost 3x4 actors.", evidence);
  assert(evidence.invalidImport.nonMutating, "Invalid File import mutated the prior session.", evidence);
  assert(
    evidence.invalidImport.beforeCanonicalSha256 === evidence.invalidImport.afterCanonicalSha256,
    "Invalid File import changed the canonical session SHA-256.",
    evidence,
  );
  assert(
    evidence.export.filename === "showcase-session-v1-export.json",
    "Export filename does not match the SHOWCASE_SESSION_V1 contract.",
    evidence,
  );
  assert(evidence.export.terminalNewline, "Exported JSON is missing its terminal newline.", evidence);
  assert(evidence.export.contentMatchesImportedSession, "Exported JSON content differs from the imported session.", evidence);
  assert(evidence.exactReimport.equalsExportedSession, "Exported bytes did not re-import exactly.", evidence);
  assert(
    evidence.exactReimport.canonicalSha256 === evidence.validImport.canonicalSha256,
    "Re-imported session canonical SHA-256 differs from the valid import.",
    evidence,
  );
  assert(evidence.runtimeErrors.length === 0, "Browser runtime errors were observed.", evidence.runtimeErrors);
  return evidence;
}

await runBrowserGate(options, executePhase1);
