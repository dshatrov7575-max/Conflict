import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const DEFAULT_TIMEOUT_MS = 20_000;
const POLL_INTERVAL_MS = 50;

export function assert(condition, message, details = undefined) {
  if (condition) return;
  const error = new Error(message);
  error.details = details;
  throw error;
}

export function parseArguments(argv, phase) {
  const options = {
    baseUrl: "http://127.0.0.1:8000/",
    browserPath: process.env.STUDIO_BROWSER_PATH || process.env.CHROME_PATH || "",
    phase,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--base-url") options.baseUrl = argv[++index];
    else if (argument === "--browser") options.browserPath = argv[++index];
    else if (argument === "--help") options.help = true;
    else throw new Error(`Unknown argument: ${argument}`);
  }
  options.baseUrl = new URL(options.baseUrl).href;
  return options;
}

export function printUsage(scriptName, phase) {
  process.stdout.write(
    [
      `ConflictAnalysis Studio browser ${phase} gate`,
      "",
      `node ${scriptName} --base-url http://127.0.0.1:8000/ [--browser <path>]`,
      "",
      "The Django showcase server must already be reachable. The browser runs",
      "headlessly with an isolated temporary profile; no native file dialog is used.",
      "",
    ].join("\n"),
  );
}

function browserCandidates(explicitPath) {
  return [
    explicitPath,
    process.env.BROWSER_PATH,
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  ].filter(Boolean);
}

function resolveBrowser(explicitPath) {
  const selected = browserCandidates(explicitPath).find((candidate) => existsSync(candidate));
  if (!selected) {
    throw new Error(
      "No supported Chromium browser found. Pass --browser or STUDIO_BROWSER_PATH.",
    );
  }
  return selected;
}

async function waitFor(predicate, description, timeoutMs = DEFAULT_TIMEOUT_MS) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const value = await predicate();
      if (value) return value;
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
  }
  const suffix = lastError ? ` Last error: ${lastError.message}` : "";
  throw new Error(`Timed out waiting for ${description}.${suffix}`);
}

class CdpConnection {
  constructor(webSocketUrl) {
    this.webSocketUrl = webSocketUrl;
    this.socket = null;
    this.nextId = 1;
    this.pending = new Map();
    this.waiters = [];
  }

  async connect() {
    this.socket = new WebSocket(this.webSocketUrl);
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(
        () => reject(new Error("Timed out connecting to the Chromium DevTools endpoint.")),
        DEFAULT_TIMEOUT_MS,
      );
      this.socket.addEventListener("open", () => {
        clearTimeout(timeout);
        resolve();
      }, { once: true });
      this.socket.addEventListener("error", (event) => {
        clearTimeout(timeout);
        reject(new Error(`DevTools WebSocket error: ${event.message || "connection failed"}`));
      }, { once: true });
    });
    this.socket.addEventListener("message", (event) => this.#handleMessage(event));
    this.socket.addEventListener("close", () => this.#handleClose());
  }

  #handleMessage(event) {
    const message = JSON.parse(typeof event.data === "string" ? event.data : String(event.data));
    if (message.id) {
      const pending = this.pending.get(message.id);
      if (!pending) return;
      clearTimeout(pending.timeout);
      this.pending.delete(message.id);
      if (message.error) {
        pending.reject(new Error(`${pending.method}: ${message.error.message}`));
      } else {
        pending.resolve(message.result || {});
      }
      return;
    }
    if (!message.method) return;
    const remaining = [];
    for (const waiter of this.waiters) {
      const sameMethod = waiter.method === message.method;
      const sameSession = !waiter.sessionId || waiter.sessionId === message.sessionId;
      let matches = sameMethod && sameSession;
      if (matches && waiter.predicate) matches = waiter.predicate(message.params || {});
      if (matches) {
        clearTimeout(waiter.timeout);
        waiter.resolve(message.params || {});
      } else {
        remaining.push(waiter);
      }
    }
    this.waiters = remaining;
  }

  #handleClose() {
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timeout);
      pending.reject(new Error("DevTools connection closed."));
    }
    this.pending.clear();
    for (const waiter of this.waiters) {
      clearTimeout(waiter.timeout);
      waiter.reject(new Error("DevTools connection closed while waiting for an event."));
    }
    this.waiters = [];
  }

  send(method, params = {}, sessionId = undefined, timeoutMs = DEFAULT_TIMEOUT_MS) {
    const id = this.nextId++;
    const request = { id, method, params };
    if (sessionId) request.sessionId = sessionId;
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`${method}: timed out after ${timeoutMs} ms.`));
      }, timeoutMs);
      this.pending.set(id, { resolve, reject, timeout, method });
      this.socket.send(JSON.stringify(request));
    });
  }

  waitForEvent(method, sessionId = undefined, predicate = undefined, timeoutMs = DEFAULT_TIMEOUT_MS) {
    return new Promise((resolve, reject) => {
      const waiter = { method, sessionId, predicate, resolve, reject };
      waiter.timeout = setTimeout(() => {
        this.waiters = this.waiters.filter((candidate) => candidate !== waiter);
        reject(new Error(`${method}: event timed out after ${timeoutMs} ms.`));
      }, timeoutMs);
      this.waiters.push(waiter);
    });
  }

  close() {
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.close();
  }
}

const DOWNLOAD_CAPTURE_SOURCE = String.raw`
(() => {
  globalThis.__ownerTestLastDownload = null;
  globalThis.__ownerTestRuntimeErrors = [];
  addEventListener("error", (event) => {
    globalThis.__ownerTestRuntimeErrors.push(String(event.error?.stack || event.message || "error"));
  });
  addEventListener("unhandledrejection", (event) => {
    globalThis.__ownerTestRuntimeErrors.push(String(event.reason?.stack || event.reason || "rejection"));
  });
  const blobs = new Map();
  const createObjectURL = URL.createObjectURL.bind(URL);
  const revokeObjectURL = URL.revokeObjectURL.bind(URL);
  URL.createObjectURL = (blob) => {
    const url = createObjectURL(blob);
    blobs.set(url, blob);
    return url;
  };
  URL.revokeObjectURL = (url) => {
    revokeObjectURL(url);
  };
  const click = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function ownerTestDownloadCapture(...args) {
    const blob = blobs.get(this.href);
    if (this.download && blob) {
      globalThis.__ownerTestLastDownload = { filename: this.download, blob };
      return undefined;
    }
    return click.apply(this, args);
  };
})();
`;

export class StudioPage {
  constructor(connection, targetId, sessionId) {
    this.connection = connection;
    this.targetId = targetId;
    this.sessionId = sessionId;
  }

  async initialize() {
    await Promise.all([
      this.connection.send("Runtime.enable", {}, this.sessionId),
      this.connection.send("Page.enable", {}, this.sessionId),
      this.connection.send("Log.enable", {}, this.sessionId),
    ]);
    await this.connection.send(
      "Page.addScriptToEvaluateOnNewDocument",
      { source: DOWNLOAD_CAPTURE_SOURCE },
      this.sessionId,
    );
  }

  async evaluate(expression, timeoutMs = DEFAULT_TIMEOUT_MS) {
    const response = await this.connection.send(
      "Runtime.evaluate",
      {
        expression,
        awaitPromise: true,
        returnByValue: true,
        userGesture: true,
      },
      this.sessionId,
      timeoutMs,
    );
    if (response.exceptionDetails) {
      const description = response.exceptionDetails.exception?.description
        || response.exceptionDetails.text
        || "Browser evaluation failed.";
      throw new Error(description);
    }
    return response.result?.value;
  }

  async goto(url) {
    const loaded = this.connection.waitForEvent("Page.loadEventFired", this.sessionId);
    const navigation = await this.connection.send("Page.navigate", { url }, this.sessionId);
    assert(!navigation.errorText, `Navigation failed: ${navigation.errorText}`);
    await loaded;
    await this.waitForStudio();
  }

  async waitForStudio() {
    await waitFor(
      async () => this.evaluate(
        "document.readyState === 'complete' && Boolean(window.StudioShowcase)",
      ),
      "window.StudioShowcase",
    );
  }

  async close() {
    await this.connection.send("Target.closeTarget", { targetId: this.targetId });
  }
}

export async function openStudioBrowser(options) {
  const healthUrl = new URL("health/", options.baseUrl);
  const healthResponse = await fetch(healthUrl, { signal: AbortSignal.timeout(DEFAULT_TIMEOUT_MS) });
  assert(healthResponse.ok, `Studio health endpoint returned HTTP ${healthResponse.status}.`);
  const health = await healthResponse.json();
  assert(health.status === "ok", "Studio health endpoint did not return status=ok.", health);

  const browserPath = resolveBrowser(options.browserPath);
  const profileDirectory = await mkdtemp(join(tmpdir(), "conflict-studio-browser-"));
  const browserArguments = [
    "--headless=new",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-dev-shm-usage",
    "--disable-extensions",
    "--disable-gpu",
    "--disable-sync",
    "--metrics-recording-only",
    "--mute-audio",
    "--no-default-browser-check",
    "--no-first-run",
    "--remote-debugging-port=0",
    `--user-data-dir=${profileDirectory}`,
    "--window-size=1440,900",
    "about:blank",
  ];
  const browserProcess = spawn(browserPath, browserArguments, {
    stdio: ["ignore", "ignore", "pipe"],
    windowsHide: true,
  });
  const diagnostics = [];
  browserProcess.stderr.setEncoding("utf8");
  browserProcess.stderr.on("data", (chunk) => {
    diagnostics.push(chunk);
    if (diagnostics.length > 20) diagnostics.shift();
  });

  let connection;
  let page;
  try {
    const activePortPath = join(profileDirectory, "DevToolsActivePort");
    const activePort = await waitFor(async () => {
      if (!existsSync(activePortPath)) return null;
      const [port, socketPath] = (await readFile(activePortPath, "utf8")).trim().split(/\r?\n/);
      return port && socketPath ? { port, socketPath } : null;
    }, "Chromium DevToolsActivePort");
    connection = new CdpConnection(`ws://127.0.0.1:${activePort.port}${activePort.socketPath}`);
    await connection.connect();
    const { targetId } = await connection.send("Target.createTarget", { url: "about:blank" });
    const attached = await connection.send("Target.attachToTarget", { targetId, flatten: true });
    page = new StudioPage(connection, targetId, attached.sessionId);
    await page.initialize();
    await page.goto(options.baseUrl);
  } catch (error) {
    error.browserDiagnostics = diagnostics.join("").trim();
    try { await connection?.send("Browser.close"); } catch {}
    connection?.close();
    if (!browserProcess.killed) browserProcess.kill();
    await rm(profileDirectory, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
    throw error;
  }

  return {
    browserPath,
    health,
    page,
    async close() {
      try { await page.close(); } catch {}
      try { await connection.send("Browser.close"); } catch {}
      connection.close();
      if (!browserProcess.killed) browserProcess.kill();
      await new Promise((resolve) => {
        if (browserProcess.exitCode !== null) resolve();
        else {
          browserProcess.once("exit", resolve);
          setTimeout(resolve, 2_000);
        }
      });
      await rm(profileDirectory, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
    },
  };
}

export async function runBrowserGate(options, execute) {
  const startedAt = new Date().toISOString();
  let browser;
  try {
    browser = await openStudioBrowser(options);
    const evidence = await execute(browser.page);
    const report = {
      status: "PASS",
      phase: options.phase,
      startedAt,
      finishedAt: new Date().toISOString(),
      baseUrl: options.baseUrl,
      browser: browser.browserPath,
      health: browser.health,
      evidence,
    };
    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  } catch (error) {
    const report = {
      status: "FAIL",
      phase: options.phase,
      startedAt,
      finishedAt: new Date().toISOString(),
      baseUrl: options.baseUrl,
      error: error.stack || error.message,
      details: error.details,
      browserDiagnostics: error.browserDiagnostics,
    };
    process.stderr.write(`${JSON.stringify(report, null, 2)}\n`);
    process.exitCode = 1;
  } finally {
    await browser?.close();
  }
}
