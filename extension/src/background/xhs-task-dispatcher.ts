/**
 * xhs task dispatcher — background polling for search / creator tasks.
 *
 * Polls ``GET /api/sources/xhs/next-task`` at intervals. When the backend
 * hands out a task, the dispatcher:
 *   1. Opens a background tab at the appropriate xhs URL.
 *   2. Listens for ``XHS_TASK_RESULT`` from the content script.
 *   3. POSTs the result back to ``/api/sources/xhs/task-result``.
 *   4. Closes the tab.
 *   5. Waits ``task_interval_seconds`` before asking for the next task.
 *
 * Only one task is in flight at a time (mutex). A hard 30s timeout per
 * task protects against hung pages.
 */

const NEXT_TASK_URL = "http://127.0.0.1:8420/api/sources/xhs/next-task";
const TASK_RESULT_URL = "http://127.0.0.1:8420/api/sources/xhs/task-result";
const DEFAULT_POLL_INTERVAL_MS = 45_000;
const TASK_TIMEOUT_MS = 30_000;
const POLL_ALARM_NAME = "openbiliclaw-xhs-task-poll";

export interface XhsTask {
  id: string;
  type: "search" | "creator";
  keyword?: string;
  creator_url?: string;
}

export interface XhsTaskResult {
  task_id: string;
  urls: string[];
  status: "ok" | "empty" | "error";
  error?: string;
}

let taskInFlight = false;
let taskTabId: number | null = null;
let taskTimeoutId: ReturnType<typeof setTimeout> | null = null;
let currentTaskId: string | null = null;
let taskUpdateListener: ((tabId: number, changeInfo: { status?: string }) => void) | null = null;

// ---------------------------------------------------------------------------
// Pure helpers (testable without chrome)
// ---------------------------------------------------------------------------

export function buildTaskUrl(task: XhsTask): string | null {
  if (task.type === "search" && task.keyword) {
    return `https://www.xiaohongshu.com/search_result?keyword=${encodeURIComponent(task.keyword)}`;
  }
  if (task.type === "creator" && task.creator_url) {
    return task.creator_url;
  }
  return null;
}

export function isValidTask(task: unknown): task is XhsTask {
  if (typeof task !== "object" || task === null) return false;
  const t = task as Record<string, unknown>;
  if (typeof t.id !== "string" || !t.id) return false;
  if (t.type !== "search" && t.type !== "creator") return false;
  return true;
}

// ---------------------------------------------------------------------------
// Chrome integration
// ---------------------------------------------------------------------------

async function fetchNextTask(): Promise<XhsTask | null> {
  try {
    const response = await fetch(NEXT_TASK_URL, { method: "GET" });
    if (response.status === 204) return null;
    if (!response.ok) return null;
    const payload = await response.json();
    return isValidTask(payload) ? payload : null;
  } catch {
    return null;
  }
}

async function reportTaskResult(result: XhsTaskResult): Promise<void> {
  try {
    await fetch(TASK_RESULT_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(result),
    });
  } catch {
    // Best-effort — log but don't crash.
  }
}

function cleanupTask(): void {
  if (taskTimeoutId !== null) {
    clearTimeout(taskTimeoutId);
    taskTimeoutId = null;
  }
  if (taskUpdateListener !== null) {
    chrome.tabs.onUpdated.removeListener(taskUpdateListener);
    taskUpdateListener = null;
  }
  if (taskTabId !== null) {
    void chrome.tabs.remove(taskTabId).catch(() => {});
    taskTabId = null;
  }
  currentTaskId = null;
  taskInFlight = false;
}

export async function executeTask(task: XhsTask): Promise<void> {
  if (taskInFlight) return;
  taskInFlight = true;
  currentTaskId = task.id;

  const url = buildTaskUrl(task);
  if (!url) {
    await reportTaskResult({ task_id: task.id, urls: [], status: "error", error: "no_url" });
    cleanupTask();
    return;
  }

  try {
    const tab = await chrome.tabs.create({ url, active: false });
    taskTabId = tab.id ?? null;
  } catch {
    await reportTaskResult({ task_id: task.id, urls: [], status: "error", error: "tab_create_failed" });
    cleanupTask();
    return;
  }

  // Once the tab finishes loading, hand off to the content-script executor.
  // Without this handshake the executor's onMessage listener never fires and
  // every task eventually trips the 30 s hard timeout.
  const listener = (updatedTabId: number, changeInfo: { status?: string }): void => {
    if (updatedTabId !== taskTabId || changeInfo.status !== "complete") return;
    if (currentTaskId !== task.id) return;
    // Detach immediately so intra-page navigations don't re-trigger the handshake.
    chrome.tabs.onUpdated.removeListener(listener);
    if (taskUpdateListener === listener) taskUpdateListener = null;
    chrome.tabs
      .sendMessage(updatedTabId, {
        action: "XHS_TASK_EXECUTE",
        data: { task_id: task.id, type: task.type },
      })
      .catch(() => {
        if (currentTaskId !== task.id) return;
        void reportTaskResult({
          task_id: task.id,
          urls: [],
          status: "error",
          error: "sendMessage_failed",
        });
        cleanupTask();
      });
  };
  taskUpdateListener = listener;
  chrome.tabs.onUpdated.addListener(listener);

  // Hard timeout — forcibly close if content script doesn't respond in time.
  taskTimeoutId = setTimeout(() => {
    if (currentTaskId === task.id) {
      void reportTaskResult({ task_id: task.id, urls: [], status: "error", error: "timeout" });
      cleanupTask();
    }
  }, TASK_TIMEOUT_MS);
}

export function handleTaskResult(result: XhsTaskResult): void {
  if (!taskInFlight || result.task_id !== currentTaskId) return;
  void reportTaskResult(result);
  cleanupTask();
}

async function pollOnce(): Promise<void> {
  if (taskInFlight) return;
  const task = await fetchNextTask();
  if (!task) return;
  await executeTask(task);
}

// ---------------------------------------------------------------------------
// Alarm-driven polling
// ---------------------------------------------------------------------------

export function startXhsTaskPolling(intervalMs: number = DEFAULT_POLL_INTERVAL_MS): void {
  chrome.alarms.create(POLL_ALARM_NAME, {
    periodInMinutes: intervalMs / 60_000,
  });
}

export function handleXhsTaskAlarm(alarmName: string): void {
  if (alarmName !== POLL_ALARM_NAME) return;
  void pollOnce();
}
