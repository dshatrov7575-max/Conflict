import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";


const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

const withTimeout = async (promise, milliseconds, label) => {
  let timer;
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error(`${label} timed out after ${milliseconds} ms`)), milliseconds);
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
};

const freePort = () => new Promise((resolve, reject) => {
  const server = net.createServer();
  server.once("error", reject);
  server.listen(0, "127.0.0.1", () => {
    const address = server.address();
    server.close((error) => {
      if (error) {
        reject(error);
      } else {
        resolve(address.port);
      }
    });
  });
});

const executableCandidates = () => {
  const environment = [
    process.env.STUDIO_CHROME_BIN,
    process.env.CHROME_BIN,
    process.env.CHROMIUM_BIN,
  ].filter(Boolean);
  if (process.platform === "win32") {
    return [
      ...environment,
      "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
      "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
      "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
      "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    ];
  }
  return [
    ...environment,
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
  ];
};

export const findChromium = () => {
  const executable = executableCandidates().find((candidate) => existsSync(candidate));
  if (!executable) {
    throw new Error("No Chrome/Chromium executable found; set STUDIO_CHROME_BIN");
  }
  return executable;
};

export class CDPClient {
  constructor(socket, timeoutMs) {
    this.socket = socket;
    this.timeoutMs = timeoutMs;
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Map();
    socket.addEventListener("message", (event) => this.#receive(event.data));
    socket.addEventListener("close", () => {
      for (const { reject } of this.pending.values()) {
        reject(new Error("CDP socket closed"));
      }
      this.pending.clear();
    });
  }

  static async connect(url, timeoutMs = 30_000) {
    const socket = new WebSocket(url);
    await withTimeout(
      new Promise((resolve, reject) => {
        socket.addEventListener("open", resolve, { once: true });
        socket.addEventListener("error", () => reject(new Error("CDP WebSocket failed")), { once: true });
      }),
      timeoutMs,
      "CDP connection",
    );
    return new CDPClient(socket, timeoutMs);
  }

  #receive(raw) {
    const message = JSON.parse(raw);
    if (message.id) {
      const pending = this.pending.get(message.id);
      if (!pending) return;
      this.pending.delete(message.id);
      if (message.error) {
        pending.reject(new Error(`${pending.method}: ${message.error.message}`));
      } else {
        pending.resolve(message.result ?? {});
      }
      return;
    }
    const listeners = this.listeners.get(message.method) ?? [];
    for (const listener of listeners) {
      listener(message.params ?? {}, message.sessionId);
    }
  }

  on(method, listener) {
    const listeners = this.listeners.get(method) ?? [];
    listeners.push(listener);
    this.listeners.set(method, listeners);
    return () => {
      this.listeners.set(method, (this.listeners.get(method) ?? []).filter((item) => item !== listener));
    };
  }

  send(method, params = {}, sessionId = undefined) {
    const id = this.nextId++;
    const payload = { id, method, params };
    if (sessionId) payload.sessionId = sessionId;
    const pending = new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject, method });
      this.socket.send(JSON.stringify(payload));
    });
    return withTimeout(pending, this.timeoutMs, method);
  }

  async evaluate(expression, sessionId, { awaitPromise = true, returnByValue = true } = {}) {
    const result = await this.send(
      "Runtime.evaluate",
      { expression, awaitPromise, returnByValue, userGesture: true },
      sessionId,
    );
    if (result.exceptionDetails) {
      const description = result.exceptionDetails.exception?.description
        ?? result.exceptionDetails.text
        ?? "Runtime.evaluate failed";
      throw new Error(description);
    }
    return result.result?.value;
  }

  async waitForExpression(expression, sessionId, timeoutMs = this.timeoutMs) {
    const deadline = Date.now() + timeoutMs;
    let last;
    while (Date.now() < deadline) {
      try {
        last = await this.evaluate(expression, sessionId);
        if (last) return last;
      } catch (error) {
        last = String(error);
      }
      await delay(50);
    }
    throw new Error(`Expression did not become truthy: ${expression}; last=${String(last)}`);
  }

  close() {
    this.socket.close();
  }
}

export const launchChromium = async ({ timeoutMs = 30_000 } = {}) => {
  const executable = findChromium();
  const port = await freePort();
  const userDataDir = mkdtempSync(path.join(os.tmpdir(), "studio-c0-chrome-"));
  const processHandle = spawn(
    executable,
    [
      `--remote-debugging-port=${port}`,
      `--user-data-dir=${userDataDir}`,
      "--remote-allow-origins=*",
      "--headless=new",
      "--disable-gpu",
      "--disable-dev-shm-usage",
      "--no-first-run",
      "--no-default-browser-check",
      "--no-sandbox",
      "about:blank",
    ],
    { stdio: ["ignore", "pipe", "pipe"], windowsHide: true },
  );
  let stderr = "";
  processHandle.stderr.on("data", (chunk) => {
    stderr = (stderr + chunk.toString("utf8")).slice(-16_384);
  });

  const endpoint = `http://127.0.0.1:${port}/json/version`;
  const deadline = Date.now() + timeoutMs;
  let version;
  while (Date.now() < deadline) {
    if (processHandle.exitCode !== null) {
      throw new Error(`Chromium exited before CDP was ready (${processHandle.exitCode}): ${stderr}`);
    }
    try {
      const response = await fetch(endpoint, { cache: "no-store" });
      if (response.ok) {
        version = await response.json();
        break;
      }
    } catch {
      // The local debugging socket is expected to refuse connections briefly.
    }
    await delay(50);
  }
  if (!version?.webSocketDebuggerUrl) {
    processHandle.kill();
    rmSync(userDataDir, { recursive: true, force: true });
    throw new Error(`Chromium CDP endpoint was unavailable: ${stderr}`);
  }

  const client = await CDPClient.connect(version.webSocketDebuggerUrl, timeoutMs);
  return {
    client,
    executable,
    version,
    async close() {
      try {
        await client.send("Browser.close");
      } catch {
        // The browser may close its debugging socket before acknowledging shutdown.
      }
      client.close();
      if (processHandle.exitCode === null) {
        await Promise.race([
          new Promise((resolve) => processHandle.once("exit", resolve)),
          delay(2_000),
        ]);
      }
      if (processHandle.exitCode === null) {
        processHandle.kill();
        await Promise.race([
          new Promise((resolve) => processHandle.once("exit", resolve)),
          delay(2_000),
        ]);
      }
      try {
        rmSync(userDataDir, {
          recursive: true,
          force: true,
          maxRetries: 10,
          retryDelay: 100,
        });
      } catch (error) {
        if (process.platform !== "win32" || error?.code !== "EPERM") throw error;
        // Windows Chromium helpers can retain the disposable profile briefly.
      }
    },
  };
};
