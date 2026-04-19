/**
 * Tests for the xhs task dispatcher.
 *
 * Pure helpers (buildTaskUrl, isValidTask) are tested directly. The
 * executeTask handshake is exercised with a hand-rolled chrome mock that
 * captures listeners and records outbound messages — no jsdom needed.
 */

import test from "node:test";
import assert from "node:assert/strict";

import {
  buildTaskUrl,
  executeTask,
  handleTaskResult,
  isValidTask,
  type XhsTask,
} from "../src/background/xhs-task-dispatcher.ts";

test("buildTaskUrl encodes keyword search URL", () => {
  const task: XhsTask = { id: "t1", type: "search", keyword: "机械键盘" };
  const url = buildTaskUrl(task);
  assert.equal(
    url,
    "https://www.xiaohongshu.com/search_result?keyword=%E6%9C%BA%E6%A2%B0%E9%94%AE%E7%9B%98",
  );
});

test("buildTaskUrl returns creator URL directly", () => {
  const task: XhsTask = {
    id: "t2",
    type: "creator",
    creator_url: "https://www.xiaohongshu.com/user/profile/abc",
  };
  assert.equal(
    buildTaskUrl(task),
    "https://www.xiaohongshu.com/user/profile/abc",
  );
});

test("buildTaskUrl returns null for search without keyword", () => {
  const task: XhsTask = { id: "t3", type: "search" };
  assert.equal(buildTaskUrl(task), null);
});

test("buildTaskUrl returns null for creator without url", () => {
  const task: XhsTask = { id: "t4", type: "creator" };
  assert.equal(buildTaskUrl(task), null);
});

test("isValidTask accepts well-formed tasks", () => {
  assert.equal(isValidTask({ id: "t1", type: "search", keyword: "x" }), true);
  assert.equal(
    isValidTask({
      id: "t2",
      type: "creator",
      creator_url: "https://example.com",
    }),
    true,
  );
});

test("isValidTask rejects malformed input", () => {
  assert.equal(isValidTask(null), false);
  assert.equal(isValidTask({}), false);
  assert.equal(isValidTask({ id: "", type: "search" }), false);
  assert.equal(isValidTask({ id: "t1", type: "unknown" }), false);
  assert.equal(isValidTask("string"), false);
});

// ---------------------------------------------------------------------------
// executeTask handshake — regression test for the "all tasks time out" bug.
// ---------------------------------------------------------------------------

interface TabUpdatedListener {
  (tabId: number, changeInfo: { status?: string }): void;
}

interface ChromeMock {
  tabs: {
    create: (opts: { url: string; active?: boolean }) => Promise<{ id: number }>;
    remove: (tabId: number) => Promise<void>;
    sendMessage: (tabId: number, message: unknown) => Promise<void>;
    onUpdated: {
      addListener: (l: TabUpdatedListener) => void;
      removeListener: (l: TabUpdatedListener) => void;
      _listeners: TabUpdatedListener[];
      _emit: (tabId: number, changeInfo: { status?: string }) => void;
    };
  };
  alarms: { create: () => void };
}

interface MockState {
  createdTabs: { url: string; active?: boolean }[];
  sentMessages: { tabId: number; message: unknown }[];
  sendMessageImpl: (tabId: number, message: unknown) => Promise<void>;
  fetchCalls: { url: string; body?: unknown }[];
}

function installChromeMock(): MockState {
  const state: MockState = {
    createdTabs: [],
    sentMessages: [],
    sendMessageImpl: async () => {},
    fetchCalls: [],
  };

  const listeners: TabUpdatedListener[] = [];
  const chromeMock: ChromeMock = {
    tabs: {
      create: async ({ url, active }) => {
        state.createdTabs.push({ url, active });
        return { id: 42 };
      },
      remove: async () => {},
      sendMessage: (tabId, message) => {
        state.sentMessages.push({ tabId, message });
        return state.sendMessageImpl(tabId, message);
      },
      onUpdated: {
        _listeners: listeners,
        addListener: (l) => {
          listeners.push(l);
        },
        removeListener: (l) => {
          const i = listeners.indexOf(l);
          if (i >= 0) listeners.splice(i, 1);
        },
        _emit: (tabId, changeInfo) => {
          for (const l of [...listeners]) l(tabId, changeInfo);
        },
      },
    },
    alarms: { create: () => {} },
  };

  (globalThis as unknown as { chrome: ChromeMock }).chrome = chromeMock;
  (globalThis as unknown as { fetch: typeof fetch }).fetch = (async (
    input: RequestInfo | URL,
    init?: RequestInit,
  ) => {
    state.fetchCalls.push({
      url: String(input),
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    });
    return new Response(null, { status: 204 });
  }) as typeof fetch;

  return state;
}

// A tiny helper that flushes pending microtasks/macrotasks so Promise chains
// triggered inside listener callbacks can settle before we assert.
async function flush(): Promise<void> {
  await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));
}

test("executeTask sends XHS_TASK_EXECUTE once the tab finishes loading", async () => {
  const state = installChromeMock();
  const chrome = (globalThis as unknown as { chrome: ChromeMock }).chrome;

  const task: XhsTask = { id: "t-handshake", type: "search", keyword: "手冲咖啡" };
  await executeTask(task);

  assert.equal(state.createdTabs.length, 1);
  assert.equal(state.sentMessages.length, 0, "no message before the tab is complete");
  assert.equal(chrome.tabs.onUpdated._listeners.length, 1, "listener registered");

  // Intermediate update — should be ignored.
  chrome.tabs.onUpdated._emit(42, { status: "loading" });
  await flush();
  assert.equal(state.sentMessages.length, 0);

  // Wrong tab id — should be ignored.
  chrome.tabs.onUpdated._emit(99, { status: "complete" });
  await flush();
  assert.equal(state.sentMessages.length, 0);

  // Now the page finishes loading — handshake fires once.
  chrome.tabs.onUpdated._emit(42, { status: "complete" });
  await flush();

  assert.equal(state.sentMessages.length, 1);
  assert.deepEqual(state.sentMessages[0], {
    tabId: 42,
    message: {
      action: "XHS_TASK_EXECUTE",
      data: { task_id: "t-handshake", type: "search" },
    },
  });
  assert.equal(chrome.tabs.onUpdated._listeners.length, 0, "listener detached after firing");

  // Subsequent completes (e.g. SPA re-navigations) must not resend.
  chrome.tabs.onUpdated._emit(42, { status: "complete" });
  await flush();
  assert.equal(state.sentMessages.length, 1);

  // Simulate the content script reporting back so module-level state resets.
  handleTaskResult({ task_id: "t-handshake", urls: ["https://example.com/explore/1"], status: "ok" });
  await flush();
});

test("executeTask reports sendMessage_failed when content script is absent", async () => {
  const state = installChromeMock();
  const chrome = (globalThis as unknown as { chrome: ChromeMock }).chrome;
  state.sendMessageImpl = async () => {
    throw new Error("no receiving end");
  };

  const task: XhsTask = { id: "t-no-receiver", type: "search", keyword: "x" };
  await executeTask(task);

  chrome.tabs.onUpdated._emit(42, { status: "complete" });
  await flush();

  const resultPost = state.fetchCalls.find(
    (c) => c.url.endsWith("/task-result") && (c.body as { task_id: string }).task_id === "t-no-receiver",
  );
  assert.ok(resultPost, "expected a task-result POST");
  assert.deepEqual(resultPost!.body, {
    task_id: "t-no-receiver",
    urls: [],
    status: "error",
    error: "sendMessage_failed",
  });
});
