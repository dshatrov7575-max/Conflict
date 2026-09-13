import assert from "node:assert/strict";
import { inflateSync } from "node:zlib";

import { launchChromium } from "./cdp_client.mjs";


const bootstrapBindingName = "__studioBootstrapObservation";
const bootstrapEventName = "studio:bootstrap-complete";
const bootstrapDiagnosticLimit = 12;
const bootstrapSelfCheckArgument = "--self-check-observation";

const bootstrapObserverError = (code) => new Error(`bootstrap observer ${code}`);

const normalizeBootstrapIdentity = (value) => (
  typeof value === "string" ? value.toLowerCase() : ""
);

const appendBootstrapDiagnostic = (diagnostics, entry) => {
  if (diagnostics.length < bootstrapDiagnosticLimit) {
    diagnostics.push({ sequence: diagnostics.length + 1, ...entry });
  }
};

const bootstrapObserverFailure = (diagnostics, stage) => {
  appendBootstrapDiagnostic(diagnostics, {
    stage,
    method: "observer",
    contextId: null,
    frameId: null,
    loaderId: null,
    result: "failed",
  });
  return new Error(
    `bootstrap observer failed at ${stage}; safe_diagnostics=${JSON.stringify(diagnostics)}`,
  );
};

const isMainFrame = (frame) => frame?.parentId === undefined || frame?.parentId === null;

const validateBootstrapBinding = ({ expectation, eventSessionId, params }) => {
  if (eventSessionId !== expectation.sessionId) {
    throw bootstrapObserverError("BINDING_SESSION_MISMATCH");
  }
  if (params.name !== bootstrapBindingName) {
    throw bootstrapObserverError("BINDING_NAME_MISMATCH");
  }
  if (params.executionContextId !== expectation.contextId) {
    throw bootstrapObserverError("BINDING_CONTEXT_MISMATCH");
  }
  if (!expectation.contextIsDefault || expectation.contextFrameId !== expectation.frameId) {
    throw bootstrapObserverError("BINDING_FRAME_MISMATCH");
  }

  let payload;
  try {
    payload = JSON.parse(params.payload);
  } catch {
    throw bootstrapObserverError("BINDING_PAYLOAD_INVALID");
  }
  if (payload?.event !== bootstrapEventName || !payload.detail || typeof payload.detail !== "object") {
    throw bootstrapObserverError("BINDING_EVENT_INVALID");
  }

  const detail = payload.detail;
  if (
    normalizeBootstrapIdentity(detail.projectId) !== expectation.projectId ||
    normalizeBootstrapIdentity(detail.definitionId) !== expectation.definitionId ||
    normalizeBootstrapIdentity(detail.operationId) !== expectation.operationId ||
    detail.projectPrimaryLanguage !== expectation.projectPrimaryLanguage
  ) {
    throw bootstrapObserverError("BINDING_IDENTITY_MISMATCH");
  }
  return detail;
};

const validateBootstrapDestinationNavigation = ({ expectation, eventSessionId, params }) => {
  if (eventSessionId !== expectation.sessionId) {
    throw bootstrapObserverError("DESTINATION_SESSION_MISMATCH");
  }
  const frame = params.frame;
  if (!isMainFrame(frame)) return null;
  if (frame?.id !== expectation.frameId) {
    throw bootstrapObserverError("DESTINATION_FRAME_MISMATCH");
  }
  if (new URL(frame.url).href !== expectation.destinationUrl || !frame.loaderId) {
    throw bootstrapObserverError("DESTINATION_MISMATCH");
  }
  return { frameId: frame.id, loaderId: frame.loaderId };
};

const validateBootstrapDestinationLoad = ({ expectation, destination, eventSessionId, params }) => {
  if (params.name !== "load") return false;
  if (eventSessionId !== expectation.sessionId) {
    throw bootstrapObserverError("DESTINATION_LOAD_SESSION_MISMATCH");
  }
  if (params.frameId !== expectation.frameId) return false;
  if (!destination || params.loaderId !== destination.loaderId) {
    throw bootstrapObserverError("DESTINATION_LOAD_MISMATCH");
  }
  return true;
};

const createBootstrapObserver = (expectation, { timeoutMs, diagnostics = [] }) => {
  let bootstrapDetail;
  let destination;
  let pendingDestinationLoad;
  let destinationLoaded = false;
  let settled = false;
  let timer;
  let resolvePromise;
  let rejectPromise;
  const promise = new Promise((resolve, reject) => {
    resolvePromise = resolve;
    rejectPromise = reject;
  });

  const fail = (stage) => {
    if (settled) return;
    settled = true;
    clearTimeout(timer);
    rejectPromise(bootstrapObserverFailure(diagnostics, stage));
  };
  const complete = () => {
    if (settled || !bootstrapDetail || !destinationLoaded) return;
    settled = true;
    clearTimeout(timer);
    resolvePromise({ detail: bootstrapDetail, destination });
  };
  appendBootstrapDiagnostic(diagnostics, {
    stage: "armed",
    method: "Runtime.bindingCalled",
    contextId: expectation.contextId,
    frameId: expectation.frameId,
    loaderId: null,
    result: "waiting",
  });
  const consumeDestinationLoad = () => {
    if (!pendingDestinationLoad) return;
    destinationLoaded = validateBootstrapDestinationLoad({
      expectation,
      destination,
      eventSessionId: pendingDestinationLoad.eventSessionId,
      params: pendingDestinationLoad.params,
    });
    pendingDestinationLoad = undefined;
  };
  timer = setTimeout(() => fail("timeout"), timeoutMs);

  return {
    cancel() {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
    },
    diagnostics,
    promise,
    observeBinding(params, eventSessionId) {
      if (settled || params.name !== bootstrapBindingName) return;
      appendBootstrapDiagnostic(diagnostics, {
        stage: "binding",
        method: "Runtime.bindingCalled",
        contextId: params.executionContextId,
        frameId: expectation.frameId,
        loaderId: null,
        result: "received",
      });
      try {
        bootstrapDetail = validateBootstrapBinding({ expectation, eventSessionId, params });
      } catch {
        fail("binding-rejected");
        return;
      }
      complete();
    },
    observeNavigation(params, eventSessionId) {
      if (settled || !isMainFrame(params.frame)) return;
      appendBootstrapDiagnostic(diagnostics, {
        stage: "navigation",
        method: "Page.frameNavigated",
        contextId: expectation.contextId,
        frameId: params.frame?.id,
        loaderId: params.frame?.loaderId || null,
        result: "received",
      });
      try {
        destination = validateBootstrapDestinationNavigation({ expectation, eventSessionId, params });
        consumeDestinationLoad();
      } catch {
        fail("destination-rejected");
        return;
      }
      complete();
    },
    observeLifecycle(params, eventSessionId) {
      if (settled || params.name !== "load" || params.frameId !== expectation.frameId) return;
      appendBootstrapDiagnostic(diagnostics, {
        stage: "destination-load",
        method: "Page.lifecycleEvent",
        contextId: expectation.contextId,
        frameId: params.frameId,
        loaderId: params.loaderId || null,
        result: "received",
      });
      try {
        if (!destination) {
          if (eventSessionId !== expectation.sessionId) {
            throw bootstrapObserverError("DESTINATION_LOAD_SESSION_MISMATCH");
          }
          pendingDestinationLoad = { eventSessionId, params };
          return;
        }
        destinationLoaded = validateBootstrapDestinationLoad({ expectation, destination, eventSessionId, params });
      } catch {
        fail("destination-load-rejected");
        return;
      }
      complete();
    },
  };
};

const assertSingleBootstrapWrite = (count) => {
  assert.equal(count, 1, "bootstrap was retried or an unexpected bootstrap write occurred");
};

const authoringReadyEventName = "studio:authoring-ready";
const authoringReadyError = (code) => new Error(`authoring-ready barrier ${code}`);
const sha256Pattern = /^[0-9a-f]{64}$/;

const validateDestinationReadyContext = ({ expectation, destination, context }) => {
  if (!destination || context?.id === expectation.entryContextId) {
    throw authoringReadyError("CONTEXT_STALE");
  }
  if (
    context?.sessionId !== expectation.sessionId ||
    context?.isDefault !== true ||
    context?.frameId !== destination.frameId
  ) {
    throw authoringReadyError("CONTEXT_MISMATCH");
  }
  return context;
};

const validateDestinationAuthoringReady = ({ expectation, detail }) => {
  if (!detail || typeof detail !== "object") {
    throw authoringReadyError("EVENT_INVALID");
  }
  if (
    normalizeBootstrapIdentity(detail.definitionId) !== expectation.definitionId ||
    normalizeBootstrapIdentity(detail.projectId) !== expectation.projectId
  ) {
    throw authoringReadyError("EVENT_IDENTITY_MISMATCH");
  }
  if (
    typeof detail.manifestHash !== "string" ||
    !sha256Pattern.test(detail.manifestHash) ||
    detail.etag !== `"${detail.manifestHash}"`
  ) {
    throw authoringReadyError("EVENT_REPRESENTATION_MISMATCH");
  }
  return detail;
};

const validateDestinationIdentity = ({ expectation, destination, detail, identity }) => {
  if (
    !identity ||
    identity.url !== expectation.destinationUrl ||
    identity.bufferPresent !== true ||
    normalizeBootstrapIdentity(identity.definitionId) !== expectation.definitionId ||
    normalizeBootstrapIdentity(identity.projectId) !== expectation.projectId ||
    identity.manifestHash !== detail.manifestHash ||
    identity.etag !== detail.etag ||
    destination?.frameId !== expectation.frameId
  ) {
    throw authoringReadyError("DESTINATION_IDENTITY_MISMATCH");
  }
  return identity;
};

const validateDestinationRepresentation = ({ expectation, detail, representation }) => {
  if (
    !representation ||
    representation.status !== 200 ||
    normalizeBootstrapIdentity(representation.definitionId) !== expectation.definitionId ||
    normalizeBootstrapIdentity(representation.projectId) !== expectation.projectId ||
    typeof representation.manifestHash !== "string" ||
    !sha256Pattern.test(representation.manifestHash) ||
    representation.etag !== `"${representation.manifestHash}"` ||
    detail.manifestHash !== representation.manifestHash ||
    detail.etag !== representation.etag
  ) {
    throw authoringReadyError("REPRESENTATION_MISMATCH");
  }
  return representation;
};

const assertBootstrapPersistenceIsEmpty = ({ localStorageKeys, sessionStorageLength, localStorageValues }) => {
  assert.deepEqual(localStorageKeys, []);
  assert.equal(sessionStorageLength, 0);
  return localStorageValues;
};

const createDestinationAuthoringReadyGuard = (expectation, { timeoutMs, diagnostics = [] }) => {
  let destination;
  let entryReplaySeen = false;
  let context;
  let readyDetail;
  let settled = false;
  let timer;
  let resolvePromise;
  let rejectPromise;
  const promise = new Promise((resolve, reject) => {
    resolvePromise = resolve;
    rejectPromise = reject;
  });
  const fail = (stage) => {
    if (settled) return;
    settled = true;
    clearTimeout(timer);
    rejectPromise(bootstrapObserverFailure(diagnostics, `authoring-ready-${stage}`));
  };
  const complete = () => {
    if (settled || !destination || !context || !readyDetail) return;
    settled = true;
    clearTimeout(timer);
    resolvePromise({ destination, context, detail: readyDetail });
  };
  appendBootstrapDiagnostic(diagnostics, {
    stage: "authoring-ready-armed",
    method: "window.__studioContractEvents",
    contextId: null,
    frameId: expectation.frameId,
    loaderId: null,
    result: "waiting",
  });
  timer = setTimeout(() => fail("timeout"), timeoutMs);

  return {
    cancel() {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
    },
    diagnostics,
    get destination() {
      return destination;
    },
    get context() {
      return context;
    },
    get ready() {
      return readyDetail !== undefined;
    },
    promise,
    acceptContext(candidate) {
      appendBootstrapDiagnostic(diagnostics, {
        stage: "authoring-ready-context",
        method: "Runtime.executionContextCreated",
        contextId: candidate?.id ?? null,
        frameId: candidate?.frameId ?? null,
        loaderId: destination?.loaderId ?? null,
        result: "received",
      });
      try {
        context = validateDestinationReadyContext({ expectation, destination, context: candidate });
      } catch {
        fail("context-rejected");
        return false;
      }
      complete();
      return true;
    },
    acceptReady(detail) {
      appendBootstrapDiagnostic(diagnostics, {
        stage: "authoring-ready-event",
        method: "window.__studioContractEvents",
        contextId: context?.id ?? null,
        frameId: destination?.frameId ?? null,
        loaderId: destination?.loaderId ?? null,
        result: "received",
      });
      try {
        readyDetail = validateDestinationAuthoringReady({ expectation, detail });
      } catch {
        fail("event-rejected");
        return false;
      }
      complete();
      return true;
    },
    observeContextDestroyed(params, eventSessionId) {
      if (
        settled ||
        eventSessionId !== expectation.sessionId ||
        !context ||
        params.executionContextId !== context.id
      ) {
        return;
      }
      appendBootstrapDiagnostic(diagnostics, {
        stage: "authoring-ready-context-destroyed",
        method: "Runtime.executionContextDestroyed",
        contextId: context.id,
        frameId: context.frameId,
        loaderId: destination?.loaderId ?? null,
        result: "received",
      });
      fail("context-destroyed");
    },
    observeNavigation(params, eventSessionId) {
      if (settled || !isMainFrame(params.frame)) return;
      const frame = params.frame;
      appendBootstrapDiagnostic(diagnostics, {
        stage: "authoring-ready-navigation",
        method: "Page.frameNavigated",
        contextId: context?.id ?? null,
        frameId: frame?.id ?? null,
        loaderId: frame?.loaderId ?? null,
        result: "received",
      });
      try {
        if (
          eventSessionId !== expectation.sessionId ||
          !expectation.entryUrl ||
          !expectation.entryLoaderId
        ) {
          throw authoringReadyError("UNEXPECTED_NAVIGATION");
        }
        const frameUrl = new URL(frame.url).href;
        if (!destination && frame?.id === expectation.frameId && frameUrl === expectation.entryUrl) {
          if (frame.loaderId !== expectation.entryLoaderId || entryReplaySeen) {
            throw authoringReadyError("UNEXPECTED_NAVIGATION");
          }
          entryReplaySeen = true;
          return;
        }
        if (destination) {
          throw authoringReadyError("UNEXPECTED_NAVIGATION");
        }
        if (
          frame?.id !== expectation.frameId ||
          frameUrl !== expectation.destinationUrl ||
          !frame.loaderId ||
          frame.loaderId === expectation.entryLoaderId
        ) {
          throw authoringReadyError("UNEXPECTED_NAVIGATION");
        }
        if (destination && destination.loaderId !== frame.loaderId) {
          throw authoringReadyError("UNEXPECTED_NAVIGATION");
        }
        destination = { frameId: frame.id, loaderId: frame.loaderId };
      } catch {
        fail("navigation-rejected");
      }
    },
    observeLoadOrReadback() {
      // A load or GET proves neither authoring readiness nor storage cleanup.
    },
  };
};

const documentNavigationError = (stage, code, details = {}) => {
  const error = new Error(
    `document navigation ${stage} ${code}; safe=${JSON.stringify(details)}`,
  );
  error.code = code;
  error.stage = stage;
  return error;
};

const remainingDocumentNavigationBudget = (deadline, stage) => {
  const remaining = deadline - Date.now();
  if (remaining <= 0) throw documentNavigationError(stage, "TIMEOUT");
  return remaining;
};

const withinDocumentNavigationDeadline = async (promise, deadline, stage) => {
  let timer;
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timer = setTimeout(
          () => reject(documentNavigationError(stage, "TIMEOUT")),
          remainingDocumentNavigationBudget(deadline, stage),
        );
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
};

const createDocumentNavigator = ({ client, sessionId, timeoutMs }) => {
  const mainFrameSnapshot = async (deadline, stage) => {
    const tree = await withinDocumentNavigationDeadline(
      client.send("Page.getFrameTree", {}, sessionId),
      deadline,
      `${stage}-frame-tree`,
    );
    const frame = tree.frameTree?.frame;
    if (!frame?.id || !frame?.loaderId || !frame?.url) {
      throw documentNavigationError(stage, "MAIN_FRAME_UNAVAILABLE");
    }
    return Object.freeze({
      frameId: frame.id,
      loaderId: frame.loaderId,
      url: new URL(frame.url).href,
    });
  };

  return async ({
    stage,
    url = null,
    reload = false,
    expectBeforeUnload = false,
    deadline = Date.now() + timeoutMs,
  }) => {
    const before = await mainFrameSnapshot(deadline, stage);
    const destinationUrl = new URL(url || before.url).href;
    let commandResult;
    let acceptedLoaderId;
    let bufferedMainFrame;
    let bufferedMainLoad;
    let frameAccepted = false;
    let loadAccepted = false;
    let dialogAccepted = false;
    let dialogCommand = Promise.resolve();
    let settled = false;
    let resolveBarrier;
    let rejectBarrier;
    let deadlineTimer;
    const removers = [];
    const barrier = new Promise((resolve, reject) => {
      resolveBarrier = resolve;
      rejectBarrier = reject;
    });

    const cleanup = () => {
      clearTimeout(deadlineTimer);
      while (removers.length) removers.pop()();
    };
    const fail = (code, details = {}) => {
      if (settled) return;
      settled = true;
      cleanup();
      rejectBarrier(documentNavigationError(stage, code, details));
    };
    const complete = () => {
      if (
        settled ||
        !frameAccepted ||
        !loadAccepted ||
        (expectBeforeUnload && !dialogAccepted)
      ) {
        return;
      }
      settled = true;
      cleanup();
      resolveBarrier(Object.freeze({
        frameId: before.frameId,
        loaderId: acceptedLoaderId,
        url: destinationUrl,
        beforeLoaderId: before.loaderId,
        dialogAccepted,
      }));
    };
    const acceptLoad = (params) => {
      if (params.name !== "load" || params.frameId !== before.frameId) return;
      if (!params.loaderId) {
        fail("LIFECYCLE_LOADER_MISSING");
        return;
      }
      if (!acceptedLoaderId) {
        if (bufferedMainLoad && bufferedMainLoad.loaderId !== params.loaderId) {
          fail("MULTIPLE_BUFFERED_LOADERS");
          return;
        }
        bufferedMainLoad = params;
        return;
      }
      if (params.loaderId !== acceptedLoaderId) {
        fail("LIFECYCLE_LOADER_MISMATCH", {
          expectedLoaderId: acceptedLoaderId,
          actualLoaderId: params.loaderId,
        });
        return;
      }
      loadAccepted = true;
      complete();
    };
    const acceptFrame = (frame) => {
      if (!frame || !isMainFrame(frame)) return;
      if (frame.id !== before.frameId) {
        fail("MAIN_FRAME_MISMATCH", { frameId: frame.id || null });
        return;
      }
      let frameUrl;
      try {
        frameUrl = new URL(frame.url).href;
      } catch {
        fail("MAIN_FRAME_URL_INVALID");
        return;
      }
      if (frameUrl !== destinationUrl || !frame.loaderId) {
        fail("NAVIGATION_IDENTITY_MISMATCH", {
          frameUrl,
          hasLoader: Boolean(frame.loaderId),
        });
        return;
      }
      if (reload && frame.loaderId === before.loaderId) {
        fail("OLD_LOADER_REUSED");
        return;
      }
      if (!reload && commandResult?.loaderId && frame.loaderId !== commandResult.loaderId) {
        fail("COMMAND_LOADER_MISMATCH", {
          commandLoaderId: commandResult.loaderId,
          frameLoaderId: frame.loaderId,
        });
        return;
      }
      if (acceptedLoaderId && acceptedLoaderId !== frame.loaderId) {
        fail("MULTIPLE_MAIN_LOADERS");
        return;
      }
      acceptedLoaderId = frame.loaderId;
      frameAccepted = true;
      if (bufferedMainLoad) {
        const pendingLoad = bufferedMainLoad;
        bufferedMainLoad = undefined;
        acceptLoad(pendingLoad);
      }
      complete();
    };

    removers.push(client.on("Page.frameNavigated", (params, eventSessionId) => {
      if (!isMainFrame(params.frame)) return;
      if (eventSessionId !== sessionId) {
        fail("FOREIGN_SESSION_FRAME");
        return;
      }
      if (!commandResult && !reload) {
        if (
          bufferedMainFrame &&
          bufferedMainFrame.loaderId !== params.frame?.loaderId
        ) {
          fail("MULTIPLE_BUFFERED_MAIN_FRAMES");
          return;
        }
        bufferedMainFrame = params.frame;
        return;
      }
      acceptFrame(params.frame);
    }));
    removers.push(client.on("Page.lifecycleEvent", (params, eventSessionId) => {
      if (params.name !== "load" || params.frameId !== before.frameId) return;
      if (eventSessionId !== sessionId) {
        fail("FOREIGN_SESSION_LOAD");
        return;
      }
      acceptLoad(params);
    }));
    removers.push(client.on("Page.javascriptDialogOpening", (params, eventSessionId) => {
      if (eventSessionId !== sessionId) {
        fail("FOREIGN_SESSION_DIALOG");
        return;
      }
      if (!expectBeforeUnload || dialogAccepted || params.type !== "beforeunload") {
        fail("UNEXPECTED_DIALOG", {
          type: params.type || null,
          alreadyAccepted: dialogAccepted,
        });
        return;
      }
      dialogAccepted = true;
      dialogCommand = client.send(
        "Page.handleJavaScriptDialog",
        { accept: true },
        sessionId,
      );
      dialogCommand.catch(() => {});
      dialogCommand.catch((error) => {
        fail("DIALOG_COMMAND_REJECTED", { message: String(error) });
      });
      complete();
    }));

    deadlineTimer = setTimeout(() => {
      if (expectBeforeUnload && !dialogAccepted) {
        fail("DIALOG_TIMEOUT");
      } else if (!frameAccepted) {
        fail("NAVIGATION_TIMEOUT");
      } else {
        fail("LIFECYCLE_LOAD_TIMEOUT");
      }
    }, remainingDocumentNavigationBudget(deadline, stage));

    const command = reload
      ? client.send(
          "Page.reload",
          { ignoreCache: true, loaderId: before.loaderId },
          sessionId,
        )
      : client.send("Page.navigate", { url: destinationUrl }, sessionId);
    command.catch(() => {});

    try {
      commandResult = await withinDocumentNavigationDeadline(
        command,
        deadline,
        `${stage}-command`,
      );
    } catch (error) {
      fail("COMMAND_REJECTED", { message: String(error) });
      return barrier;
    }

    if (!reload) {
      if (commandResult.errorText) {
        fail("COMMAND_ERROR_TEXT", { errorText: commandResult.errorText });
      } else if (
        commandResult.frameId !== before.frameId ||
        !commandResult.loaderId
      ) {
        fail("COMMAND_IDENTITY_MISMATCH", {
          frameId: commandResult.frameId || null,
          hasLoader: Boolean(commandResult.loaderId),
        });
      } else {
        acceptedLoaderId = commandResult.loaderId;
        if (bufferedMainFrame) {
          const pendingFrame = bufferedMainFrame;
          bufferedMainFrame = undefined;
          acceptFrame(pendingFrame);
        }
        if (bufferedMainLoad) acceptLoad(bufferedMainLoad);
      }
    }

    try {
      const result = await withinDocumentNavigationDeadline(
        barrier,
        deadline,
        `${stage}-barrier`,
      );
      await withinDocumentNavigationDeadline(
        dialogCommand,
        deadline,
        `${stage}-dialog-command`,
      );
      return result;
    } finally {
      cleanup();
    }
  };
};


const runBootstrapObserverSelfCheck = async () => {
  const expectation = Object.freeze({
    sessionId: "self-check-session",
    contextId: 17,
    contextIsDefault: true,
    contextFrameId: "self-check-main-frame",
    frameId: "self-check-main-frame",
    entryUrl: "https://example.invalid/studio/drafts/",
    entryLoaderId: "self-check-entry-loader",
    destinationUrl: "https://example.invalid/studio/drafts/definitions/22222222-2222-4222-8222-222222222222/",
    projectId: "11111111-1111-4111-8111-111111111111",
    definitionId: "22222222-2222-4222-8222-222222222222",
    operationId: "33333333-3333-4333-8333-333333333333",
    projectPrimaryLanguage: "ru",
  });
  const detail = Object.freeze({
    projectId: expectation.projectId,
    definitionId: expectation.definitionId,
    operationId: expectation.operationId,
    projectPrimaryLanguage: expectation.projectPrimaryLanguage,
  });
  const binding = (overrides = {}) => ({
    name: bootstrapBindingName,
    executionContextId: expectation.contextId,
    payload: JSON.stringify({ event: bootstrapEventName, detail: { ...detail, ...overrides } }),
  });
  const destination = {
    frame: {
      id: expectation.frameId,
      loaderId: "self-check-loader",
      url: expectation.destinationUrl,
    },
  };

  const reordered = createBootstrapObserver(expectation, { timeoutMs: 50 });
  reordered.observeBinding(binding(), expectation.sessionId);
  reordered.observeNavigation(destination, expectation.sessionId);
  reordered.observeLifecycle(
    { name: "load", frameId: expectation.frameId, loaderId: "self-check-loader" },
    expectation.sessionId,
  );
  assert.deepEqual((await reordered.promise).detail, detail);
  assert.ok(reordered.diagnostics.length <= bootstrapDiagnosticLimit);
  assert.deepEqual(
    reordered.diagnostics.map((entry) => entry.sequence),
    [1, 2, 3, 4],
  );
  assert.equal(JSON.stringify(reordered.diagnostics).includes(expectation.operationId), false);

  const lifecycleFirst = createBootstrapObserver(expectation, { timeoutMs: 50 });
  lifecycleFirst.observeLifecycle(
    { name: "load", frameId: expectation.frameId, loaderId: "self-check-loader" },
    expectation.sessionId,
  );
  lifecycleFirst.observeNavigation(destination, expectation.sessionId);
  lifecycleFirst.observeBinding(binding(), expectation.sessionId);
  assert.deepEqual((await lifecycleFirst.promise).detail, detail);

  const foreignContext = createBootstrapObserver(expectation, { timeoutMs: 50 });
  foreignContext.observeBinding(binding({}), expectation.sessionId);
  foreignContext.observeBinding(
    { ...binding(), executionContextId: expectation.contextId + 1 },
    expectation.sessionId,
  );
  await assert.rejects(foreignContext.promise, /binding-rejected/);

  const staleIdentity = createBootstrapObserver(expectation, { timeoutMs: 50 });
  staleIdentity.observeBinding(
    binding({ operationId: "44444444-4444-4444-8444-444444444444" }),
    expectation.sessionId,
  );
  await assert.rejects(staleIdentity.promise, /binding-rejected/);

  const wrongMainFrame = createBootstrapObserver(expectation, { timeoutMs: 50 });
  wrongMainFrame.observeNavigation(
    { frame: { ...destination.frame, id: "self-check-other-main-frame" } },
    expectation.sessionId,
  );
  await assert.rejects(wrongMainFrame.promise, /destination-rejected/);

  const wrongContextFrame = createBootstrapObserver(
    { ...expectation, contextFrameId: "self-check-wrong-context-frame" },
    { timeoutMs: 50 },
  );
  wrongContextFrame.observeBinding(binding(), expectation.sessionId);
  await assert.rejects(wrongContextFrame.promise, /binding-rejected/);

  const readyExpectation = Object.freeze({
    ...expectation,
    entryContextId: expectation.contextId,
  });
  const readyDetail = Object.freeze({
    definitionId: expectation.definitionId,
    projectId: expectation.projectId,
    manifestHash: "a".repeat(64),
    etag: `"${"a".repeat(64)}"`,
  });
  const readyContext = Object.freeze({
    id: expectation.contextId + 1,
    sessionId: expectation.sessionId,
    isDefault: true,
    frameId: expectation.frameId,
  });
  const readyNavigation = { frame: destination.frame };
  const entryReplayNavigation = {
    frame: {
      id: expectation.frameId,
      loaderId: expectation.entryLoaderId,
      url: expectation.entryUrl,
    },
  };

  const exactEntryReplay = createDestinationAuthoringReadyGuard(readyExpectation, { timeoutMs: 50 });
  exactEntryReplay.observeNavigation(entryReplayNavigation, expectation.sessionId);
  assert.equal(exactEntryReplay.destination, undefined);
  exactEntryReplay.observeNavigation(readyNavigation, expectation.sessionId);
  exactEntryReplay.acceptContext(readyContext);
  exactEntryReplay.acceptReady(readyDetail);
  assert.deepEqual((await exactEntryReplay.promise).detail, readyDetail);

  const bufferedReady = createDestinationAuthoringReadyGuard(readyExpectation, { timeoutMs: 50 });
  bufferedReady.observeNavigation(readyNavigation, expectation.sessionId);
  bufferedReady.acceptReady(readyDetail);
  assert.equal(bufferedReady.ready, true);
  bufferedReady.acceptContext(readyContext);
  assert.deepEqual((await bufferedReady.promise).detail, readyDetail);

  const laterReady = createDestinationAuthoringReadyGuard(readyExpectation, { timeoutMs: 50 });
  laterReady.observeNavigation(readyNavigation, expectation.sessionId);
  laterReady.acceptContext(readyContext);
  const afterWaiting = laterReady.promise;
  laterReady.acceptReady(readyDetail);
  assert.deepEqual((await afterWaiting).detail, readyDetail);

  const loadOrGetOnly = createDestinationAuthoringReadyGuard(readyExpectation, { timeoutMs: 50 });
  loadOrGetOnly.observeNavigation(readyNavigation, expectation.sessionId);
  loadOrGetOnly.acceptContext(readyContext);
  loadOrGetOnly.observeLoadOrReadback();
  assert.equal(loadOrGetOnly.ready, false);
  loadOrGetOnly.cancel();

  const staleReady = createDestinationAuthoringReadyGuard(readyExpectation, { timeoutMs: 50 });
  staleReady.observeNavigation(readyNavigation, expectation.sessionId);
  staleReady.acceptContext(readyContext);
  staleReady.acceptReady({ ...readyDetail, definitionId: "55555555-5555-4555-8555-555555555555" });
  await assert.rejects(staleReady.promise, /authoring-ready-event-rejected/);

  const wrongReadyProject = createDestinationAuthoringReadyGuard(readyExpectation, { timeoutMs: 50 });
  wrongReadyProject.observeNavigation(readyNavigation, expectation.sessionId);
  wrongReadyProject.acceptContext(readyContext);
  wrongReadyProject.acceptReady({ ...readyDetail, projectId: "66666666-6666-4666-8666-666666666666" });
  await assert.rejects(wrongReadyProject.promise, /authoring-ready-event-rejected/);

  const wrongReadyContext = createDestinationAuthoringReadyGuard(readyExpectation, { timeoutMs: 50 });
  wrongReadyContext.observeNavigation(readyNavigation, expectation.sessionId);
  wrongReadyContext.acceptContext({ ...readyContext, id: expectation.contextId });
  await assert.rejects(wrongReadyContext.promise, /authoring-ready-context-rejected/);

  const wrongReadyFrame = createDestinationAuthoringReadyGuard(readyExpectation, { timeoutMs: 50 });
  wrongReadyFrame.observeNavigation(
    { frame: { ...entryReplayNavigation.frame, id: "self-check-wrong-ready-frame" } },
    expectation.sessionId,
  );
  await assert.rejects(wrongReadyFrame.promise, /authoring-ready-navigation-rejected/);

  const wrongEntryUrl = createDestinationAuthoringReadyGuard(readyExpectation, { timeoutMs: 50 });
  wrongEntryUrl.observeNavigation(
    { frame: { ...entryReplayNavigation.frame, url: "https://example.invalid/studio/other/" } },
    expectation.sessionId,
  );
  await assert.rejects(wrongEntryUrl.promise, /authoring-ready-navigation-rejected/);

  const wrongEntryLoader = createDestinationAuthoringReadyGuard(readyExpectation, { timeoutMs: 50 });
  wrongEntryLoader.observeNavigation(
    { frame: { ...entryReplayNavigation.frame, loaderId: "self-check-wrong-entry-loader" } },
    expectation.sessionId,
  );
  await assert.rejects(wrongEntryLoader.promise, /authoring-ready-navigation-rejected/);

  const wrongEntrySession = createDestinationAuthoringReadyGuard(readyExpectation, { timeoutMs: 50 });
  wrongEntrySession.observeNavigation(entryReplayNavigation, "self-check-wrong-session");
  await assert.rejects(wrongEntrySession.promise, /authoring-ready-navigation-rejected/);

  const secondEntryReplay = createDestinationAuthoringReadyGuard(readyExpectation, { timeoutMs: 50 });
  secondEntryReplay.observeNavigation(entryReplayNavigation, expectation.sessionId);
  secondEntryReplay.observeNavigation(entryReplayNavigation, expectation.sessionId);
  await assert.rejects(secondEntryReplay.promise, /authoring-ready-navigation-rejected/);

  const entryLoaderAsDestination = createDestinationAuthoringReadyGuard(readyExpectation, { timeoutMs: 50 });
  entryLoaderAsDestination.observeNavigation(
    { frame: { ...destination.frame, loaderId: expectation.entryLoaderId } },
    expectation.sessionId,
  );
  await assert.rejects(entryLoaderAsDestination.promise, /authoring-ready-navigation-rejected/);

  const duplicateDestination = createDestinationAuthoringReadyGuard(readyExpectation, { timeoutMs: 50 });
  duplicateDestination.observeNavigation(readyNavigation, expectation.sessionId);
  duplicateDestination.observeNavigation(readyNavigation, expectation.sessionId);
  await assert.rejects(duplicateDestination.promise, /authoring-ready-navigation-rejected/);

  const unexpectedNavigation = createDestinationAuthoringReadyGuard(readyExpectation, { timeoutMs: 50 });
  unexpectedNavigation.observeNavigation(readyNavigation, expectation.sessionId);
  unexpectedNavigation.acceptContext(readyContext);
  unexpectedNavigation.observeNavigation(
    { frame: { ...destination.frame, loaderId: "self-check-next-loader" } },
    expectation.sessionId,
  );
  await assert.rejects(unexpectedNavigation.promise, /authoring-ready-navigation-rejected/);

  const destroyedContext = createDestinationAuthoringReadyGuard(readyExpectation, { timeoutMs: 50 });
  destroyedContext.observeNavigation(readyNavigation, expectation.sessionId);
  destroyedContext.acceptContext(readyContext);
  destroyedContext.observeContextDestroyed({ executionContextId: readyContext.id }, expectation.sessionId);
  await assert.rejects(destroyedContext.promise, /authoring-ready-context-destroyed/);

  const absentReady = createDestinationAuthoringReadyGuard(readyExpectation, { timeoutMs: 10 });
  absentReady.observeNavigation(readyNavigation, expectation.sessionId);
  absentReady.acceptContext(readyContext);
  await assert.rejects(absentReady.promise, /authoring-ready-timeout/);

  const readyThenPoisonedStorage = createDestinationAuthoringReadyGuard(readyExpectation, { timeoutMs: 50 });
  readyThenPoisonedStorage.observeNavigation(readyNavigation, expectation.sessionId);
  readyThenPoisonedStorage.acceptContext(readyContext);
  readyThenPoisonedStorage.acceptReady(readyDetail);
  await readyThenPoisonedStorage.promise;
  assert.throws(
    () => assertBootstrapPersistenceIsEmpty({
      localStorageKeys: ["conflict-analysis-studio:audited-draft-layout:v1"],
      sessionStorageLength: 0,
      localStorageValues: ["poisoned"],
    }),
  );

  const deferred = () => {
    let resolve;
    let reject;
    const promise = new Promise((resolvePromise, rejectPromise) => {
      resolve = resolvePromise;
      reject = rejectPromise;
    });
    return { promise, resolve, reject };
  };
  const createNavigationSelfCheckClient = ({ frame, onCommand }) => {
    const listeners = new Map();
    const calls = [];
    let removals = 0;
    const selfCheckClient = {
      calls,
      emit(method, params, eventSessionId = expectation.sessionId) {
        for (const listener of [...(listeners.get(method) || [])]) {
          listener(params, eventSessionId);
        }
      },
      listenerCount() {
        return [...listeners.values()].reduce((total, items) => total + items.length, 0);
      },
      get removals() {
        return removals;
      },
      on(method, listener) {
        const items = listeners.get(method) || [];
        items.push(listener);
        listeners.set(method, items);
        let removed = false;
        return () => {
          if (removed) return;
          removed = true;
          removals += 1;
          listeners.set(
            method,
            (listeners.get(method) || []).filter((item) => item !== listener),
          );
        };
      },
      send(method, params = {}, eventSessionId = undefined) {
        calls.push({ method, params, sessionId: eventSessionId });
        if (method === "Page.getFrameTree") {
          return Promise.resolve({ frameTree: { frame: { ...frame } } });
        }
        if (method === "Page.handleJavaScriptDialog") {
          return Promise.resolve({});
        }
        if (method === "Page.navigate" || method === "Page.reload") {
          const command = deferred();
          queueMicrotask(() => onCommand({
            client: selfCheckClient,
            command,
            method,
            params,
          }));
          return command.promise;
        }
        return Promise.reject(new Error(`unexpected self-check CDP method: ${method}`));
      },
    };
    return selfCheckClient;
  };
  const navigationFrame = Object.freeze({
    id: expectation.frameId,
    loaderId: "self-check-old-loader",
    url: "https://example.invalid/start/",
  });
  const navigationUrl = "https://example.invalid/target/";
  const loadedNavigationFrame = Object.freeze({
    id: expectation.frameId,
    loaderId: "self-check-new-loader",
    url: navigationUrl,
  });
  const reloadedNavigationFrame = Object.freeze({
    id: expectation.frameId,
    loaderId: "self-check-reload-loader",
    url: navigationFrame.url,
  });

  const lifecycleBeforeNavigationClient = createNavigationSelfCheckClient({
    frame: navigationFrame,
    onCommand({ client: fake, command }) {
      fake.emit("Page.lifecycleEvent", {
        name: "load",
        frameId: expectation.frameId,
        loaderId: loadedNavigationFrame.loaderId,
      });
      fake.emit("Page.frameNavigated", { frame: loadedNavigationFrame });
      command.resolve({
        frameId: expectation.frameId,
        loaderId: loadedNavigationFrame.loaderId,
      });
    },
  });
  const lifecycleBeforeNavigation = createDocumentNavigator({
    client: lifecycleBeforeNavigationClient,
    sessionId: expectation.sessionId,
    timeoutMs: 50,
  });
  assert.deepEqual(
    await lifecycleBeforeNavigation({
      stage: "self-check-navigation-buffering",
      url: navigationUrl,
    }),
    {
      frameId: expectation.frameId,
      loaderId: loadedNavigationFrame.loaderId,
      url: navigationUrl,
      beforeLoaderId: navigationFrame.loaderId,
      dialogAccepted: false,
    },
  );
  assert.equal(lifecycleBeforeNavigationClient.listenerCount(), 0);
  assert.equal(lifecycleBeforeNavigationClient.removals, 3);

  const foreignSessionClient = createNavigationSelfCheckClient({
    frame: navigationFrame,
    onCommand({ client: fake, command }) {
      fake.emit(
        "Page.frameNavigated",
        { frame: loadedNavigationFrame },
        "self-check-foreign-session",
      );
      command.resolve({
        frameId: expectation.frameId,
        loaderId: loadedNavigationFrame.loaderId,
      });
    },
  });
  await assert.rejects(
    createDocumentNavigator({
      client: foreignSessionClient,
      sessionId: expectation.sessionId,
      timeoutMs: 50,
    })({ stage: "self-check-foreign-session", url: navigationUrl }),
    (error) => error.code === "FOREIGN_SESSION_FRAME",
  );
  assert.equal(foreignSessionClient.listenerCount(), 0);

  const wrongLoaderClient = createNavigationSelfCheckClient({
    frame: navigationFrame,
    onCommand({ client: fake, command }) {
      fake.emit("Page.frameNavigated", {
        frame: { ...loadedNavigationFrame, loaderId: "self-check-wrong-loader" },
      });
      command.resolve({
        frameId: expectation.frameId,
        loaderId: loadedNavigationFrame.loaderId,
      });
    },
  });
  await assert.rejects(
    createDocumentNavigator({
      client: wrongLoaderClient,
      sessionId: expectation.sessionId,
      timeoutMs: 50,
    })({ stage: "self-check-wrong-loader", url: navigationUrl }),
    (error) => error.code === "COMMAND_LOADER_MISMATCH",
  );
  assert.equal(wrongLoaderClient.listenerCount(), 0);

  const missingLoadClient = createNavigationSelfCheckClient({
    frame: navigationFrame,
    onCommand({ client: fake, command }) {
      fake.emit("Page.frameNavigated", { frame: loadedNavigationFrame });
      command.resolve({
        frameId: expectation.frameId,
        loaderId: loadedNavigationFrame.loaderId,
      });
    },
  });
  await assert.rejects(
    createDocumentNavigator({
      client: missingLoadClient,
      sessionId: expectation.sessionId,
      timeoutMs: 15,
    })({ stage: "self-check-missing-load", url: navigationUrl }),
    (error) => error.code === "LIFECYCLE_LOAD_TIMEOUT",
  );
  assert.equal(missingLoadClient.listenerCount(), 0);

  const beforeUnloadClient = createNavigationSelfCheckClient({
    frame: navigationFrame,
    onCommand({ client: fake, command, method, params }) {
      assert.equal(method, "Page.reload");
      assert.deepEqual(params, {
        ignoreCache: true,
        loaderId: navigationFrame.loaderId,
      });
      fake.emit("Page.javascriptDialogOpening", { type: "beforeunload" });
      fake.emit("Page.frameNavigated", { frame: reloadedNavigationFrame });
      fake.emit("Page.lifecycleEvent", {
        name: "load",
        frameId: expectation.frameId,
        loaderId: reloadedNavigationFrame.loaderId,
      });
      command.resolve({});
    },
  });
  const beforeUnloadResult = await createDocumentNavigator({
    client: beforeUnloadClient,
    sessionId: expectation.sessionId,
    timeoutMs: 50,
  })({
    stage: "self-check-beforeunload",
    reload: true,
    expectBeforeUnload: true,
  });
  assert.equal(beforeUnloadResult.dialogAccepted, true);
  assert.deepEqual(
    beforeUnloadClient.calls.filter(
      (item) => item.method === "Page.handleJavaScriptDialog",
    ),
    [{
      method: "Page.handleJavaScriptDialog",
      params: { accept: true },
      sessionId: expectation.sessionId,
    }],
  );
  assert.equal(beforeUnloadClient.listenerCount(), 0);
  assert.equal(beforeUnloadClient.removals, 3);

  const unexpectedDialogClient = createNavigationSelfCheckClient({
    frame: navigationFrame,
    onCommand({ client: fake, command }) {
      fake.emit("Page.javascriptDialogOpening", { type: "alert" });
      command.resolve({});
    },
  });
  await assert.rejects(
    createDocumentNavigator({
      client: unexpectedDialogClient,
      sessionId: expectation.sessionId,
      timeoutMs: 50,
    })({
      stage: "self-check-unexpected-dialog",
      reload: true,
      expectBeforeUnload: true,
    }),
    (error) => error.code === "UNEXPECTED_DIALOG",
  );
  assert.equal(unexpectedDialogClient.listenerCount(), 0);

  const reloadFailure = new Error("synthetic reload failure");
  const rejectedReloadClient = createNavigationSelfCheckClient({
    frame: navigationFrame,
    onCommand({ command }) {
      command.reject(reloadFailure);
    },
  });
  await assert.rejects(
    createDocumentNavigator({
      client: rejectedReloadClient,
      sessionId: expectation.sessionId,
      timeoutMs: 50,
    })({ stage: "self-check-reload-command", reload: true }),
    (error) => (
      error.code === "COMMAND_REJECTED" &&
      error.message.includes(reloadFailure.message)
    ),
  );
  assert.equal(rejectedReloadClient.listenerCount(), 0);

  const oldLoaderClient = createNavigationSelfCheckClient({
    frame: navigationFrame,
    onCommand({ client: fake, command }) {
      fake.emit("Page.frameNavigated", { frame: navigationFrame });
      command.resolve({});
    },
  });
  await assert.rejects(
    createDocumentNavigator({
      client: oldLoaderClient,
      sessionId: expectation.sessionId,
      timeoutMs: 50,
    })({ stage: "self-check-old-loader", reload: true }),
    (error) => error.code === "OLD_LOADER_REUSED",
  );
  assert.equal(oldLoaderClient.listenerCount(), 0);


  const absent = createBootstrapObserver(expectation, { timeoutMs: 10 });
  await assert.rejects(absent.promise, /bootstrap observer failed at timeout/);
  assertSingleBootstrapWrite(1);
  assert.throws(() => assertSingleBootstrapWrite(2), /bootstrap was retried/);
};

if (process.argv.includes(bootstrapSelfCheckArgument)) {
  await runBootstrapObserverSelfCheck();
  console.log("F1_CHROMIUM_R3_BOOTSTRAP_OBSERVER_SELF_CHECK=PASS");
  process.exit(0);
}


const requiredEnvironment = (name) => {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
};

const baseUrl = requiredEnvironment("STUDIO_BASE_URL").replace(/\/$/, "");
const definitionId = requiredEnvironment("STUDIO_DEFINITION_ID").toLowerCase();
const sessionCookieName = requiredEnvironment("STUDIO_SESSION_COOKIE_NAME");
const sessionCookieValue = requiredEnvironment("STUDIO_SESSION_COOKIE_VALUE");
const expectedClaimSha256 = requiredEnvironment("STUDIO_EXPECTED_CLAIM_SHA256");
const expectedManifestSha256 = requiredEnvironment("STUDIO_EXPECTED_MANIFEST_SHA256");
const expectedHelpSha256 = requiredEnvironment("STUDIO_EXPECTED_HELP_SHA256");
const remoteSaveBody = inflateSync(
  Buffer.from(requiredEnvironment("STUDIO_REMOTE_SAVE_BODY_ZLIB_B64"), "base64"),
).toString("utf8");
const losslessBigintKey = requiredEnvironment("STUDIO_LOSSLESS_BIGINT_KEY");
const losslessExponentKey = requiredEnvironment("STUDIO_LOSSLESS_EXPONENT_KEY");
const losslessExponentToken = requiredEnvironment("STUDIO_LOSSLESS_EXPONENT_TOKEN");
const timeoutMs = Number(process.env.STUDIO_CDP_TIMEOUT_MS || "60000");
const definitionUrl = `${baseUrl}/studio/drafts/definitions/${definitionId}/`;
const entryUrl = `${baseUrl}/studio/drafts/`;
const bootstrapPath = "/api/foundation/projects/bootstrap-first-draft/";
const openPath = `/api/foundation/definitions/${definitionId}/`;
const savePath = `${openPath}draft/`;
const previewPath = `${openPath}validation-preview/`;
const storageKey = "conflict-analysis-studio:audited-draft-layout:v1";
const eventNames = [
  "studio:bootstrap-complete",
  "studio:authoring-ready",
  "studio:save-complete",
  "studio:preview-complete",
  "studio:typed-conflict",
];

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
const normalizedHeaders = (headers) => Object.fromEntries(
  Object.entries(headers || {}).map(([name, value]) => [name.toLowerCase(), String(value)]),
);

const browser = await launchChromium({ timeoutMs });
let client;
let sessionId;
const requests = [];
const responses = new Map();

try {
  client = browser.client;
  const { targetId } = await client.send("Target.createTarget", { url: "about:blank" });
  ({ sessionId } = await client.send("Target.attachToTarget", { targetId, flatten: true }));
  await Promise.all([
    client.send("Page.enable", {}, sessionId),
    client.send("Runtime.enable", {}, sessionId),
    client.send("Network.enable", { maxTotalBufferSize: 50_000_000 }, sessionId),
  ]);
  await client.send("Page.setLifecycleEventsEnabled", { enabled: true }, sessionId);
  const executionContexts = new Map();
  client.on("Runtime.executionContextCreated", (event, eventSessionId) => {
    if (eventSessionId !== sessionId || !event.context?.auxData?.frameId) return;
    executionContexts.set(event.context.id, {
      id: event.context.id,
      sessionId: eventSessionId,
      frameId: event.context.auxData.frameId,
      isDefault: event.context.auxData.isDefault === true,
    });
  });
  client.on("Runtime.executionContextDestroyed", (event, eventSessionId) => {
    if (eventSessionId === sessionId) executionContexts.delete(event.executionContextId);
  });
  client.on("Runtime.executionContextsCleared", (_event, eventSessionId) => {
    if (eventSessionId === sessionId) executionContexts.clear();
  });
  await client.send("Browser.setDownloadBehavior", { behavior: "deny" });
  await client.send("Runtime.addBinding", { name: bootstrapBindingName }, sessionId);
  await client.send(
    "Page.addScriptToEvaluateOnNewDocument",
    {
      source: `(() => {
        window.__studioContractEvents = [];
        for (const name of ${JSON.stringify(eventNames)}) {
          window.addEventListener(name, (event) => {
            let detail = {};
            try {
              detail = JSON.parse(JSON.stringify(event.detail || {}));
            } catch {
              detail = { serializationError: true };
            }
            window.__studioContractEvents.push({ name, detail });
          });
        }
        const bootstrapBinding = globalThis[${JSON.stringify(bootstrapBindingName)}];
        if (typeof bootstrapBinding === "function") {
          window.addEventListener(${JSON.stringify(bootstrapEventName)}, (event) => {
            const detail = event.detail || {};
            bootstrapBinding(JSON.stringify({
              event: ${JSON.stringify(bootstrapEventName)},
              detail: {
                projectId: detail.projectId,
                definitionId: detail.definitionId,
                operationId: detail.operationId,
                receiptSha256: detail.receiptSha256,
                projectPrimaryLanguage: detail.projectPrimaryLanguage,
                projectPrimaryLanguageAssignment: detail.projectPrimaryLanguageAssignment,
                replayed: detail.replayed,
                status: detail.status,
              },
            }));
          });
        }
      })();`,
    },
    sessionId,
  );

  client.on("Network.requestWillBeSent", (event, eventSessionId) => {
    if (eventSessionId !== sessionId || !/^https?:/.test(event.request.url)) return;
    requests.push({
      method: event.request.method,
      url: event.request.url,
      headers: normalizedHeaders(event.request.headers),
      postData: event.request.postData || null,
    });
  });
  client.on("Network.responseReceived", (event, eventSessionId) => {
    if (eventSessionId !== sessionId || !/^https?:/.test(event.response.url)) return;
    responses.set(event.requestId, {
      url: event.response.url,
      status: event.response.status,
      headers: normalizedHeaders(event.response.headers),
    });
  });

  const cookie = await client.send(
    "Network.setCookie",
    {
      name: sessionCookieName,
      value: sessionCookieValue,
      url: `${baseUrl}/`,
      httpOnly: true,
      sameSite: "Lax",
      secure: baseUrl.startsWith("https:"),
    },
    sessionId,
  );
  assert.equal(cookie.success, true, "pre-issued session cookie was not admitted");

  const navigateDocument = createDocumentNavigator({ client, sessionId, timeoutMs });
  const clearEvents = () => client.evaluate(
    "window.__studioContractEvents.length = 0",
    sessionId,
  );
  const waitForEvent = async (name, deadline = Date.now() + timeoutMs) => {
    const stage = `event-${name}`;
    await client.waitForExpression(
      `window.__studioContractEvents?.some((item) => item.name === ${JSON.stringify(name)})`,
      sessionId,
      remainingDocumentNavigationBudget(deadline, stage),
    );
    return withinDocumentNavigationDeadline(
      client.evaluate(
        `window.__studioContractEvents.filter((item) => item.name === ${JSON.stringify(name)}).at(-1).detail`,
        sessionId,
      ),
      deadline,
      `${stage}-readback`,
    );
  };
  const mainExecutionContext = (frameId) => [...executionContexts.values()]
    .filter((context) => context.frameId === frameId && context.isDefault)
    .at(-1);
  const evaluateInExecutionContext = async (expression, contextId) => {
    const result = await client.send(
      "Runtime.evaluate",
      { expression, contextId, awaitPromise: true, returnByValue: true, userGesture: true },
      sessionId,
    );
    if (result.exceptionDetails) {
      throw authoringReadyError("DESTINATION_EVALUATION_FAILED");
    }
    return result.result?.value;
  };
  const waitForMainExecutionContext = async (frameId) => {
    const existing = mainExecutionContext(frameId);
    if (existing) return existing;
    return new Promise((resolve, reject) => {
      let timer;
      const removeListener = client.on("Runtime.executionContextCreated", (_event, eventSessionId) => {
        if (eventSessionId !== sessionId) return;
        const created = mainExecutionContext(frameId);
        if (!created) return;
        clearTimeout(timer);
        removeListener();
        resolve(created);
      });
      timer = setTimeout(() => {
        removeListener();
        reject(bootstrapObserverError("ENTRY_CONTEXT_TIMEOUT"));
      }, timeoutMs);
    });
  };
  const navigateAndWait = async ({
    reload = false,
    expectBeforeUnload = false,
  } = {}) => {
    const deadline = Date.now() + timeoutMs;
    await navigateDocument({
      stage: reload ? "definition-reload" : "definition-navigation",
      url: definitionUrl,
      reload,
      expectBeforeUnload,
      deadline,
    });
    return waitForEvent("studio:authoring-ready", deadline);
  };
  const inspectPage = () => client.evaluate(`(async () => {
    const app = document.querySelector("#audited-draft-app");
    const actorRoot = document.querySelector("#authoring-actors");
    const elementRoot = document.querySelector("#authoring-elements");
    const authoringWindow = document.querySelector("#authoring-window");
    const helpFrame = document.querySelector("#help-frame");
    const layoutRaw = localStorage.getItem(${JSON.stringify(storageKey)});
    return {
      definitionId: app?.dataset.definitionId,
      projectId: app?.dataset.projectId,
      manifestHash: app?.dataset.manifestHash,
      etag: app?.dataset.etag,
      actorCount: Number(actorRoot?.dataset.totalCount),
      elementCount: Number(elementRoot?.dataset.totalCount),
      activeRows: authoringWindow?.querySelectorAll("[data-authoring-row][data-item-id]").length || 0,
      totalDomNodes: document.getElementsByTagName("*").length,
      crossCells: document.querySelectorAll("[data-actor-id][data-element-id]").length,
      disabled: [
        "document-control",
        "chat-control",
        "scientific-control",
        "prediction-control",
        "recommendation-control",
      ].every((id) => document.querySelector("#" + id)?.disabled === true),
      boundaryVisible: Boolean(document.querySelector("#audited-draft-boundary-banner")),
      projectName: document.querySelector("#project-name")?.value,
      projectDescription: document.querySelector("#project-description")?.value,
      helpText:
        helpFrame?.getAttribute("srcdoc") ||
        helpFrame?.contentDocument?.body?.textContent ||
        "",
      helpSha256: helpFrame?.dataset.contentSha256 || "",
      layoutRaw,
      localStorageKeys: Object.keys(localStorage).sort(),
      sessionStorageLength: sessionStorage.length,
      indexedDbNames: typeof indexedDB.databases === "function"
        ? (await indexedDB.databases()).map((item) => item.name).filter(Boolean)
        : [],
      cacheNames: "caches" in window ? await caches.keys() : [],
      serviceWorkers: "serviceWorker" in navigator
        ? (await navigator.serviceWorker.getRegistrations()).length
        : 0,
      left: Number(document.querySelector("#left-width-control")?.value),
      right: Number(document.querySelector("#right-width-control")?.value),
      activeRightTab: document.querySelector('[data-right-tab][aria-selected="true"]')?.dataset.rightTab,
    };
  })()`, sessionId);

  {
    await navigateDocument({
      stage: "claim-navigation",
      url: `${baseUrl}/studio/claim-boundaries/audited-draft/v1/`,
      deadline: Date.now() + timeoutMs,
    });
    const poisonedLayout =
      `{"version":"STUDIO_AUDITED_DRAFT_LAYOUT_V1",` +
      `"left":"${definitionId}","left":300,"right":400,"activeRightTab":"help"}`;
    assert.ok(Buffer.byteLength(poisonedLayout, "utf8") <= 256);
    await client.evaluate(
      `localStorage.setItem(${JSON.stringify(storageKey)}, ${JSON.stringify(poisonedLayout)})`,
      sessionId,
    );
  }

  await navigateDocument({
    stage: "entry-navigation",
    url: entryUrl,
    deadline: Date.now() + timeoutMs,
  });
  await client.waitForExpression(
    `document.querySelector("#entry-state-code")?.textContent === "READY" && !document.querySelector("#bootstrap-draft")?.disabled`,
    sessionId,
    timeoutMs,
  );
  const entryFrameTree = await client.send("Page.getFrameTree", {}, sessionId);
  const entryFrame = entryFrameTree.frameTree?.frame;
  assert.ok(entryFrame, "bootstrap entry main frame is unavailable");
  assert.equal(new URL(entryFrame.url).href, new URL(entryUrl).href);
  assert.ok(entryFrame.loaderId, "bootstrap entry main-frame loader is unavailable");
  const entryContext = await waitForMainExecutionContext(entryFrame.id);
  assert.equal(entryContext.frameId, entryFrame.id);
  assert.equal(entryContext.isDefault, true);

  const bootstrapRequestOffset = requests.length;
  const bootstrapAttempt = await client.evaluate(`(() => {
    const language = document.querySelector("#bootstrap-project-primary-language");
    const form = document.querySelector("#bootstrap-draft-form");
    if (!language || !form) {
      throw new Error("bootstrap form is unavailable");
    }
    return {
      projectId: document.querySelector("#bootstrap-project-id").value,
      definitionId: document.querySelector("#bootstrap-definition-id").value,
      operationId: document.querySelector("#bootstrap-operation-key").value,
    };
  })()`, sessionId);
  const bootstrapExpectation = Object.freeze({
    sessionId,
    contextId: entryContext.id,
    entryContextId: entryContext.id,
    contextIsDefault: entryContext.isDefault,
    contextFrameId: entryContext.frameId,
    frameId: entryFrame.id,
    entryUrl: new URL(entryFrame.url).href,
    entryLoaderId: entryFrame.loaderId,
    destinationUrl: new URL(
      `${baseUrl}/studio/drafts/definitions/${bootstrapAttempt.definitionId}/`,
    ).href,
    projectId: normalizeBootstrapIdentity(bootstrapAttempt.projectId),
    definitionId: normalizeBootstrapIdentity(bootstrapAttempt.definitionId),
    operationId: normalizeBootstrapIdentity(bootstrapAttempt.operationId),
    projectPrimaryLanguage: "ru",
  });
  const bootstrapDeadline = Date.now() + timeoutMs;
  const remainingBootstrapBudget = async (promise, stage) => {
    const remaining = bootstrapDeadline - Date.now();
    if (remaining <= 0) throw authoringReadyError(`${stage}_TIMEOUT`);
    let timer;
    try {
      return await Promise.race([
        promise,
        new Promise((_, reject) => {
          timer = setTimeout(() => reject(authoringReadyError(`${stage}_TIMEOUT`)), remaining);
        }),
      ]);
    } finally {
      clearTimeout(timer);
    }
  };
  const bootstrapObserver = createBootstrapObserver(bootstrapExpectation, {
    timeoutMs: Math.max(1, bootstrapDeadline - Date.now()),
  });
  const bootstrapReadyGuard = createDestinationAuthoringReadyGuard(bootstrapExpectation, {
    timeoutMs: Math.max(1, bootstrapDeadline - Date.now()),
  });
  const removeBootstrapBinding = client.on(
    "Runtime.bindingCalled",
    (event, eventSessionId) => bootstrapObserver.observeBinding(event, eventSessionId),
  );
  const removeBootstrapNavigation = client.on(
    "Page.frameNavigated",
    (event, eventSessionId) => bootstrapObserver.observeNavigation(event, eventSessionId),
  );
  const removeBootstrapLifecycle = client.on(
    "Page.lifecycleEvent",
    (event, eventSessionId) => bootstrapObserver.observeLifecycle(event, eventSessionId),
  );
  const removeBootstrapReadyNavigation = client.on(
    "Page.frameNavigated",
    (event, eventSessionId) => bootstrapReadyGuard.observeNavigation(event, eventSessionId),
  );
  const removeBootstrapReadyContextDestroyed = client.on(
    "Runtime.executionContextDestroyed",
    (event, eventSessionId) => bootstrapReadyGuard.observeContextDestroyed(event, eventSessionId),
  );
  let bootstrap;
  let bootstrapReady;
  let bootstrapRepresentation;
  let bootstrapPersistence;
  try {
    await client.evaluate(`(() => {
    const language = document.querySelector("#bootstrap-project-primary-language");
    const form = document.querySelector("#bootstrap-draft-form");
    if (!language || !form) {
      throw new Error("bootstrap form is unavailable");
    }
    language.value = "ru";
    language.dispatchEvent(new Event("input", { bubbles: true }));
    form.requestSubmit();
  })()`, sessionId);
    const observedBootstrap = await remainingBootstrapBudget(bootstrapObserver.promise, "BOOTSTRAP");
    bootstrap = observedBootstrap.detail;
    assert.equal(observedBootstrap.destination.frameId, entryFrame.id);
    assert.ok(observedBootstrap.destination.loaderId);
    assert.deepEqual(bootstrapReadyGuard.destination, observedBootstrap.destination);

    const destinationFrameTree = await remainingBootstrapBudget(
      client.send("Page.getFrameTree", {}, sessionId),
      "DESTINATION_FRAME",
    );
    const destinationFrame = destinationFrameTree.frameTree?.frame;
    if (
      !destinationFrame ||
      destinationFrame.id !== observedBootstrap.destination.frameId ||
      destinationFrame.loaderId !== observedBootstrap.destination.loaderId ||
      new URL(destinationFrame.url).href !== bootstrapExpectation.destinationUrl
    ) {
      throw authoringReadyError("DESTINATION_FRAME_MISMATCH");
    }

    const waitForDestinationContext = async () => {
      const acceptExisting = () => {
        const candidate = mainExecutionContext(observedBootstrap.destination.frameId);
        if (!candidate || candidate.id === entryContext.id) return null;
        return bootstrapReadyGuard.acceptContext(candidate) ? candidate : null;
      };
      const existing = acceptExisting();
      if (existing) return existing;
      let removeContextListener;
      const contextPromise = new Promise((resolve, reject) => {
        removeContextListener = client.on(
          "Runtime.executionContextCreated",
          (event, eventSessionId) => {
            if (eventSessionId !== sessionId) return;
            const candidate = executionContexts.get(event.context?.id);
            if (
              !candidate ||
              candidate.id === entryContext.id ||
              candidate.frameId !== observedBootstrap.destination.frameId ||
              candidate.isDefault !== true
            ) {
              return;
            }
            if (bootstrapReadyGuard.acceptContext(candidate)) {
              resolve(candidate);
            } else {
              reject(authoringReadyError("DESTINATION_CONTEXT_REJECTED"));
            }
          },
        );
      });
      try {
        return await remainingBootstrapBudget(
          Promise.race([contextPromise, bootstrapReadyGuard.promise]),
          "DESTINATION_CONTEXT",
        );
      } finally {
        removeContextListener?.();
      }
    };
    const destinationContext = await waitForDestinationContext();
    if (!destinationContext || destinationContext.id !== bootstrapReadyGuard.context?.id) {
      throw authoringReadyError("DESTINATION_CONTEXT_MISMATCH");
    }

    const bufferedReady = evaluateInExecutionContext(`(() => {
      const events = window.__studioContractEvents;
      if (!Array.isArray(events)) throw new Error("authoring-ready event buffer is unavailable");
      const buffered = events.find((item) => item?.name === ${JSON.stringify(authoringReadyEventName)});
      if (buffered) return buffered.detail || null;
      return new Promise((resolve) => {
        window.addEventListener(${JSON.stringify(authoringReadyEventName)}, (event) => {
          let detail = null;
          try {
            detail = JSON.parse(JSON.stringify(event.detail || null));
          } catch {
            detail = null;
          }
          resolve(detail);
        }, { once: true });
      });
    })()`, destinationContext.id);
    bufferedReady.catch(() => {});
    const destinationReadyDetail = await remainingBootstrapBudget(
      Promise.race([bufferedReady, bootstrapReadyGuard.promise]),
      "AUTHORING_READY",
    );
    if (!bootstrapReadyGuard.acceptReady(destinationReadyDetail)) {
      await bootstrapReadyGuard.promise;
    }
    bootstrapReady = await remainingBootstrapBudget(
      bootstrapReadyGuard.promise,
      "AUTHORING_READY",
    );

    const destinationIdentity = await remainingBootstrapBudget(
      evaluateInExecutionContext(`({
        url: location.href,
        bufferPresent: Array.isArray(window.__studioContractEvents),
        definitionId: document.querySelector("#audited-draft-app")?.dataset.definitionId || "",
        projectId: document.querySelector("#audited-draft-app")?.dataset.projectId || "",
        manifestHash: document.querySelector("#audited-draft-app")?.dataset.manifestHash || "",
        etag: document.querySelector("#audited-draft-app")?.dataset.etag || "",
      })`, destinationContext.id),
      "AUTHORING_IDENTITY",
    );
    validateDestinationIdentity({
      expectation: bootstrapExpectation,
      destination: bootstrapReady.destination,
      detail: bootstrapReady.detail,
      identity: destinationIdentity,
    });

    bootstrapRepresentation = await remainingBootstrapBudget(
      evaluateInExecutionContext(`fetch(${JSON.stringify("/api/foundation/definitions/")} + ${JSON.stringify(bootstrap.definitionId)} + "/", {
        credentials: "same-origin",
        cache: "no-store",
      }).then(async (response) => {
        const dto = await response.json();
        return {
          status: response.status,
          definitionId: dto?.id || "",
          projectId: dto?.project_id || "",
          manifestHash: dto?.manifest_hash || "",
          etag: response.headers.get("ETag") || "",
          projectPrimaryLanguage: dto?.manifest?.project?.default_locale || "",
        };
      })`, destinationContext.id),
      "AUTHORING_REPRESENTATION",
    );
    validateDestinationRepresentation({
      expectation: bootstrapExpectation,
      detail: bootstrapReady.detail,
      representation: bootstrapRepresentation,
    });

    bootstrapPersistence = await remainingBootstrapBudget(
      evaluateInExecutionContext(`({
        localStorageKeys: Object.keys(localStorage).sort(),
        localStorageValues: Object.values(localStorage),
        sessionStorageLength: sessionStorage.length,
      })`, destinationContext.id),
      "AUTHORING_PERSISTENCE",
    );
    assertBootstrapPersistenceIsEmpty(bootstrapPersistence);
  } finally {
    removeBootstrapBinding();
    removeBootstrapNavigation();
    removeBootstrapLifecycle();
    removeBootstrapReadyNavigation();
    removeBootstrapReadyContextDestroyed();
    bootstrapObserver.cancel();
    bootstrapReadyGuard.cancel();
  }
  assert.equal(normalizeBootstrapIdentity(bootstrap.projectId), bootstrapExpectation.projectId);
  assert.equal(normalizeBootstrapIdentity(bootstrap.definitionId), bootstrapExpectation.definitionId);
  assert.equal(normalizeBootstrapIdentity(bootstrap.operationId), bootstrapExpectation.operationId);
  assert.equal(bootstrap.status, 201);
  assert.equal(bootstrap.replayed, false);
  assert.equal(bootstrap.projectPrimaryLanguage, "ru");
  assert.equal(bootstrap.projectPrimaryLanguageAssignment, "EXPLICIT");
  assert.match(bootstrap.projectId, /^[0-9a-f-]{36}$/);
  assert.match(bootstrap.definitionId, /^[0-9a-f-]{36}$/);
  assert.match(
    bootstrap.operationId,
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
  );
  assert.match(bootstrap.receiptSha256, /^[0-9a-f]{64}$/);
  const bootstrapRequests = requests.slice(bootstrapRequestOffset).filter(
    (item) => item.method === "POST" && new URL(item.url).pathname === bootstrapPath,
  );
  assertSingleBootstrapWrite(bootstrapRequests.length);
  const [bootstrapRequest] = bootstrapRequests;
  assert.ok(bootstrapRequest, "real audited-draft bootstrap request was not observed");
  assert.equal(JSON.parse(bootstrapRequest.postData).project_primary_language, "ru");
  assert.equal(bootstrapRequest.headers["idempotency-key"], bootstrap.operationId);
  assert.ok(bootstrapRequest.headers["x-csrftoken"]);
  assert.equal(bootstrapRepresentation.definitionId, bootstrap.definitionId);
  assert.equal(bootstrapRepresentation.projectId, bootstrap.projectId);
  assert.equal(bootstrapRepresentation.projectPrimaryLanguage, "ru");
  assert.equal(
    bootstrapPersistence.localStorageValues.some(
      (value) => value.includes("ru") || value.includes(bootstrap.receiptSha256),
    ),
    false,
    "language or receipt was persisted by the browser",
  );

  const ready = await navigateAndWait();
  assert.deepEqual(ready, {
    definitionId,
    projectId: ready.projectId,
    manifestHash: expectedManifestSha256,
    etag: `"${expectedManifestSha256}"`,
  });
  assert.match(ready.projectId, /^[0-9a-f-]{36}$/);

  let page = await inspectPage();
  let maxActiveRows = page.activeRows;
  assert.equal(page.definitionId, definitionId);
  assert.equal(page.manifestHash, expectedManifestSha256);
  assert.equal(page.etag, `"${expectedManifestSha256}"`);
  assert.equal(page.left, 272);
  assert.equal(page.right, 360);
  assert.equal(page.activeRightTab, "help");
  assert.ok(
    page.layoutRaw === null ||
      page.layoutRaw ===
        '{"version":"STUDIO_AUDITED_DRAFT_LAYOUT_V1","left":272,"right":360,"activeRightTab":"help"}',
    `poisoned layout survived as ${page.layoutRaw}`,
  );
  assert.equal(page.layoutRaw?.includes(definitionId) || false, false);
  assert.deepEqual(
    page.localStorageKeys,
    page.layoutRaw === null ? [] : [storageKey],
  );
  assert.ok(page.actorCount > 500, `actor cardinality was ${page.actorCount}`);
  assert.ok(page.elementCount > 500, `element cardinality was ${page.elementCount}`);
  assert.ok(page.activeRows > 0 && page.activeRows <= 100, `actor rows were ${page.activeRows}`);
  await client.evaluate(`document.querySelector("#authoring-elements").click()`, sessionId);
  page = await inspectPage();
  maxActiveRows = Math.max(maxActiveRows, page.activeRows);
  assert.ok(page.activeRows > 0 && page.activeRows <= 100, `element rows were ${page.activeRows}`);
  await client.evaluate(`document.querySelector("#authoring-actors").click()`, sessionId);
  assert.ok(page.totalDomNodes < 5_000, `DOM expanded to ${page.totalDomNodes} nodes`);
  assert.equal(page.crossCells, 0, "actor x element cells were allocated");
  assert.equal(page.disabled, true);
  assert.equal(page.boundaryVisible, true);

  await client.evaluate(`(() => {
    const left = document.querySelector("#left-width-control");
    const right = document.querySelector("#right-width-control");
    left.value = "300";
    left.dispatchEvent(new Event("input", { bubbles: true }));
    right.value = "400";
    right.dispatchEvent(new Event("input", { bubbles: true }));
    document.querySelector('[data-right-tab="help"]').click();
  })()`, sessionId);
  page = await inspectPage();
  assert.deepEqual(page.localStorageKeys, [storageKey]);
  assert.deepEqual(JSON.parse(page.layoutRaw), {
    version: "STUDIO_AUDITED_DRAFT_LAYOUT_V1",
    left: 300,
    right: 400,
    activeRightTab: "help",
  });
  assert.ok(Buffer.byteLength(page.layoutRaw, "utf8") <= 256);
  assert.equal(page.layoutRaw.includes(definitionId), false);

  await client.evaluate(`document.querySelector("#load-help").click()`, sessionId);
  await client.waitForExpression(
    `(document.querySelector("#help-frame")?.getAttribute("srcdoc") || document.querySelector("#help-frame")?.contentDocument?.body?.textContent || "").includes("Точная справка Foundation")`,
    sessionId,
    timeoutMs,
  );
  page = await inspectPage();
  assert.match(page.helpText, /Точная справка Foundation/);
  assert.equal(page.helpSha256, expectedHelpSha256);

  const remoteSave = await client.evaluate(`(async () => {
    const csrf = document.cookie.split(";").map((item) => item.trim()).find((item) => item.startsWith("csrftoken="))?.split("=").slice(1).join("=");
    const opened = await fetch(${JSON.stringify(openPath)}, { credentials: "same-origin", cache: "no-store" });
    const dto = await opened.json();
    const operationId = crypto.randomUUID();
    const response = await fetch(${JSON.stringify(savePath)}, {
      method: "PUT",
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf,
        "Idempotency-Key": operationId,
        "If-Match": dto.manifest_hash ? '"' + dto.manifest_hash + '"' : "",
      },
      body: ${JSON.stringify(remoteSaveBody)},
    });
    return {
      status: response.status,
      body: await response.json(),
      receiptSha256: response.headers.get("X-Foundation-Receipt-SHA256"),
    };
  })()`, sessionId);
  assert.equal(remoteSave.status, 200, JSON.stringify(remoteSave.body));
  assert.match(remoteSave.receiptSha256, /^[0-9a-f]{64}$/);

  await clearEvents();
  await client.evaluate(`(() => {
    const name = document.querySelector("#project-name");
    name.value = "Локально устаревший проект";
    name.dispatchEvent(new Event("input", { bubbles: true }));
    document.querySelector("#save-draft").click();
  })()`, sessionId);
  const conflict = await waitForEvent("studio:typed-conflict");
  assert.deepEqual(conflict, { definitionId, code: "DRAFT_STALE", status: 409 });
  const putsAtConflict = requests.filter(
    (item) => item.method === "PUT" && new URL(item.url).pathname === savePath,
  ).length;
  await delay(500);
  assert.equal(
    requests.filter((item) => item.method === "PUT" && new URL(item.url).pathname === savePath).length,
    putsAtConflict,
    "typed conflict triggered an automatic write retry",
  );

  await navigateAndWait({ reload: true, expectBeforeUnload: true });
  const mutations = await client.evaluate(`(() => {
    const input = (element, value) => {
      element.value = value;
      element.dispatchEvent(new Event("input", { bubbles: true }));
    };
    input(document.querySelector("#project-name"), "Проект C1 после сохранения");
    input(document.querySelector("#project-description"), "Сохранённый и перечитанный Foundation DRAFT.");

    const mutateCollection = (sectionId, addId, label, reference) => {
      document.querySelector(sectionId).click();
      const root = document.querySelector("#authoring-window");
      let rows = [...root.querySelectorAll("[data-authoring-row][data-item-id]")];
      const edited = rows[10];
      const editedId = edited.dataset.itemId;
      const followingId = rows[11].dataset.itemId;
      const initialOrder = Number(edited.querySelector("td")?.textContent);
      input(edited.querySelector('[data-field="label"]'), label);
      const referenceInput = edited.querySelector('[data-field="reference_statement"]');
      if (referenceInput && reference) input(referenceInput, reference);
      edited.querySelector('[data-action="move-down"]').click();
      rows = [...root.querySelectorAll("[data-authoring-row][data-item-id]")];
      const deletedId = rows[12].dataset.itemId;
      rows[12].querySelector('[data-action="delete"]').click();
      document.querySelector(addId).click();
      rows = [...root.querySelectorAll("[data-authoring-row][data-item-id]")];
      const added = rows.at(-1);
      return {
        editedId,
        followingId,
        initialOrder,
        deletedId,
        newId: added.dataset.itemId,
        newCode: added.querySelector("code")?.textContent,
      };
    };
    const actor = mutateCollection("#authoring-actors", "#add-actor", "Переименованный актор C1", null);
    const element = mutateCollection(
      "#authoring-elements",
      "#add-element",
      "Переименованный элемент C1",
      "Проверенное утверждение C1.",
    );
    return { actor, element };
  })()`, sessionId);
  page = await inspectPage();
  maxActiveRows = Math.max(maxActiveRows, page.activeRows);
  assert.equal(page.actorCount, 520);
  assert.equal(page.elementCount, 520);
  assert.ok(page.activeRows > 0 && page.activeRows <= 100);
  assert.ok(page.totalDomNodes < 5_000);

  const serverBeforePreview = await client.evaluate(`fetch(${JSON.stringify(openPath)}, { credentials: "same-origin", cache: "no-store" }).then((response) => response.json())`, sessionId);
  const projectNameBeforeInvalidPreview = await client.evaluate(`(() => {
    const input = document.querySelector("#project-name");
    const value = input.value;
    input.value = "";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    return value;
  })()`, sessionId);
  await clearEvents();
  await client.evaluate(`document.querySelector("#preview-validation").click()`, sessionId);
  const invalidPreview = await waitForEvent("studio:preview-complete");
  assert.equal(invalidPreview.definitionId, definitionId);
  assert.equal(invalidPreview.manifestHash, serverBeforePreview.manifest_hash);
  assert.equal(invalidPreview.valid, false);
  assert.equal(invalidPreview.status, 200);
  const invalidPreviewUi = await client.evaluate(`(() => ({
    stateCode: document.querySelector("#authoring-state-code")?.textContent,
    validationState: document.querySelector("#validation-state")?.textContent,
    diagnosticCodes: [...document.querySelectorAll("#validation-diagnostics [data-code]")]
      .map((item) => item.dataset.code),
  }))()`, sessionId);
  assert.equal(invalidPreviewUi.stateCode, "VALIDATION_PREVIEW_INVALID");
  assert.equal(invalidPreviewUi.validationState, "INVALID");
  assert.ok(invalidPreviewUi.diagnosticCodes.includes("FIELD_BLANK"));
  const serverAfterInvalidPreview = await client.evaluate(`fetch(${JSON.stringify(openPath)}, { credentials: "same-origin", cache: "no-store" }).then((response) => response.json())`, sessionId);
  assert.equal(
    serverAfterInvalidPreview.manifest_hash,
    serverBeforePreview.manifest_hash,
    "invalid preview wrote the DRAFT",
  );
  await client.evaluate(`(() => {
    const input = document.querySelector("#project-name");
    input.value = ${JSON.stringify(projectNameBeforeInvalidPreview)};
    input.dispatchEvent(new Event("input", { bubbles: true }));
  })()`, sessionId);
  await clearEvents();
  await client.evaluate(`document.querySelector("#preview-validation").click()`, sessionId);
  const preview = await waitForEvent("studio:preview-complete");
  assert.equal(preview.definitionId, definitionId);
  assert.equal(preview.manifestHash, serverBeforePreview.manifest_hash);
  assert.equal(preview.valid, true);
  assert.equal(preview.status, 200);
  const serverAfterPreview = await client.evaluate(`fetch(${JSON.stringify(openPath)}, { credentials: "same-origin", cache: "no-store" }).then((response) => response.json())`, sessionId);
  assert.equal(serverAfterPreview.manifest_hash, serverBeforePreview.manifest_hash, "preview wrote the DRAFT");

  await clearEvents();
  await client.evaluate(`document.querySelector("#save-draft").click()`, sessionId);
  const saved = await waitForEvent("studio:save-complete");
  assert.equal(saved.definitionId, definitionId);
  assert.equal(saved.status, 200);
  assert.equal(saved.replayed, false);
  assert.match(
    saved.operationId,
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
  );
  assert.match(saved.receiptSha256, /^[0-9a-f]{64}$/);
  assert.match(saved.manifestHash, /^[0-9a-f]{64}$/);
  assert.equal(saved.etag, `"${saved.manifestHash}"`);

  const finalRepresentation = await client.evaluate(`fetch(${JSON.stringify(openPath)}, { credentials: "same-origin", cache: "no-store" }).then(async (response) => {
    const raw = await response.text();
    return { raw, dto: JSON.parse(raw) };
  })`, sessionId);
  const finalDto = finalRepresentation.dto;
  const exactNumberMember = (raw, key, token) => {
    const escapedKey = key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const escapedToken = token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    assert.match(
      raw,
      new RegExp(`"${escapedKey}"\\s*:\\s*${escapedToken}(?=[,}])`),
    );
  };
  exactNumberMember(finalRepresentation.raw, losslessBigintKey, "9007199254740993");
  exactNumberMember(finalRepresentation.raw, losslessExponentKey, losslessExponentToken);
  assert.equal(finalDto.manifest_hash, saved.manifestHash);
  assert.equal(finalDto.manifest.project.name, "Проект C1 после сохранения");
  assert.ok(finalDto.manifest.actors.some((item) => item.label === "Переименованный актор C1"));
  assert.ok(finalDto.manifest.analytical_elements.some((item) => item.label === "Переименованный элемент C1"));
  const assertMutationPersisted = (collection, mutation, expectedLabel) => {
    const ids = collection.map((item) => item.id);
    const edited = collection.find((item) => item.id === mutation.editedId);
    const added = collection.find((item) => item.id === mutation.newId);
    assert.equal(collection.length, 520);
    assert.equal(edited?.label, expectedLabel, "renamed row was not persisted by exact id");
    assert.notEqual(edited?.order, mutation.initialOrder, "row order did not change");
    assert.equal(ids.includes(mutation.deletedId), false, "deleted row survived save");
    assert.ok(ids.indexOf(mutation.editedId) > ids.indexOf(mutation.followingId), "move-down was not persisted");
    assert.equal(added?.code, mutation.newCode, "new row was not persisted by exact id/code");
  };
  assertMutationPersisted(
    finalDto.manifest.actors,
    mutations.actor,
    "Переименованный актор C1",
  );
  assertMutationPersisted(
    finalDto.manifest.analytical_elements,
    mutations.element,
    "Переименованный элемент C1",
  );

  const reloaded = await navigateAndWait({ reload: true });
  assert.equal(reloaded.manifestHash, saved.manifestHash);
  const reloadedRaw = await client.evaluate(
    `fetch(${JSON.stringify(openPath)}, { credentials: "same-origin", cache: "no-store" }).then((response) => response.text())`,
    sessionId,
  );
  exactNumberMember(reloadedRaw, losslessBigintKey, "9007199254740993");
  exactNumberMember(reloadedRaw, losslessExponentKey, losslessExponentToken);
  page = await inspectPage();
  assert.equal(page.projectName, "Проект C1 после сохранения");
  assert.deepEqual(page.localStorageKeys, [storageKey]);
  assert.equal(page.sessionStorageLength, 0);
  assert.deepEqual(page.indexedDbNames, []);
  assert.deepEqual(page.cacheNames, []);
  assert.equal(page.serviceWorkers, 0);

  const apiRequests = requests.filter((item) => new URL(item.url).pathname.startsWith("/api/"));
  assert.ok(apiRequests.length > 0);
  assert.equal(
    apiRequests.every((item) => new URL(item.url).pathname.startsWith("/api/foundation/")),
    true,
    "a non-Foundation API was called",
  );
  const mutationRequests = apiRequests.filter((item) => !["GET", "HEAD"].includes(item.method));
  assert.equal(
    mutationRequests.every((item) =>
      [bootstrapPath, savePath, previewPath].includes(new URL(item.url).pathname)),
    true,
    "an unauthorized mutation route was called",
  );
  const allBootstrapRequests = mutationRequests.filter(
    (item) => item.method === "POST" && new URL(item.url).pathname === bootstrapPath,
  );
  assertSingleBootstrapWrite(allBootstrapRequests.length);
  const saveRequests = mutationRequests.filter((item) => item.method === "PUT");
  assert.equal(saveRequests.length, 3, "save was retried or an unexpected write occurred");
  for (const request of saveRequests) {
    assert.match(
      request.headers["idempotency-key"],
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
    assert.match(request.headers["if-match"], /^"[0-9a-f]{64}"$/);
    assert.ok(request.headers["x-csrftoken"]);
  }
  const previewRequests = mutationRequests.filter(
    (item) => item.method === "POST" && new URL(item.url).pathname === previewPath,
  );
  assert.equal(previewRequests.length, 2);
  for (const request of previewRequests) {
    assert.equal("idempotency-key" in request.headers, false);
    assert.equal("if-match" in request.headers, false);
  }

  const cookies = await client.send("Network.getAllCookies", {}, sessionId);
  assert.ok(cookies.cookies.some((item) => item.name === sessionCookieName));
  assert.ok(
    cookies.cookies.every((item) => [sessionCookieName, "csrftoken"].includes(item.name)),
    `unexpected cookies: ${cookies.cookies.map((item) => item.name).join(",")}`,
  );

  console.log(JSON.stringify({
    browser_result: "PASS",
    browser: browser.version.Browser,
    definition_id: definitionId,
    bootstrap_project_id: bootstrap.projectId,
    bootstrap_definition_id: bootstrap.definitionId,
    bootstrap_primary_language: bootstrap.projectPrimaryLanguage,
    bootstrap_primary_language_assignment: bootstrap.projectPrimaryLanguageAssignment,
    bootstrap_receipt_sha256: bootstrap.receiptSha256,
    claim_contract_sha256: expectedClaimSha256,
    final_manifest_sha256: saved.manifestHash,
    receipt_sha256: saved.receiptSha256,
    typed_conflict: conflict.code,
    observed_actor_count: page.actorCount,
    observed_element_count: page.elementCount,
    max_active_rows: maxActiveRows,
    storage_key: storageKey,
    foundation_requests: apiRequests.length,
  }));
} finally {
  await browser.close();
}
