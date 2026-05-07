/**
 * OpenBiliClaw — Douyin content script entry.
 *
 * Injected into douyin.com pages (isolated world). Listens for
 * DY_SCOPE_EXECUTE messages from the dispatcher, drives the per-scope
 * scrape — installs the MAIN-world fetch-tap (if not already), waits
 * for it to capture aweme JSON, programmatically scrolls to trigger
 * Douyin's virtual-list pagination, accumulates items into a
 * BootstrapItemSink, and posts DY_SCOPE_RESULT back when the scope is
 * exhausted (cap hit / round budget gone / consecutive stagnant
 * rounds).
 *
 * The MAIN-world fetch-tap is loaded separately via the
 * content_scripts MAIN-world entry in manifest.json
 * (dist/main/dy-fetch-tap.js, runs at document_start). That script
 * postMessages captured items here using a sentinel type
 * OPENBILICLAW_DOUYIN_AWEME_PAGE.
 *
 * Module isolation: zero imports from extension/src/content/xhs/.
 */

import type { DouyinBootstrapItem, DouyinScope } from "../main/dy-fetch-tap.js";

// Dynamic import for the chrome-lifecycle code path so node:test's
// --experimental-strip-types resolver doesn't have to chase the
// `.js → .ts` chain at module-load time. Pure helpers exported from
// this file (isValidScopeExecuteMessage) stay synchronously
// importable for unit tests. esbuild inlines the dynamic import at
// build time, so production runtime sees no extra latency.
async function loadTaskExecutorHelpers(): Promise<{
  BootstrapItemSink: typeof import("./dy/task-executor.js").BootstrapItemSink;
  dyShouldContinueScroll: typeof import("./dy/task-executor.js").dyShouldContinueScroll;
  ingestMainWorldFetchMessage: typeof import("./dy/task-executor.js").ingestMainWorldFetchMessage;
}> {
  return await import("./dy/task-executor.js");
}

interface ScopeExecuteMessage {
  task_id: string;
  scope: DouyinScope;
  max_items_per_scope: number;
  max_scroll_rounds: number;
  max_stagnant_scroll_rounds: number;
}

interface ScopeResultPayload {
  task_id: string;
  scope: DouyinScope;
  items: DouyinBootstrapItem[];
  scope_count: number;
  status: "ok" | "empty" | "failed";
  error?: string;
}

const SCROLL_DELAY_MS = 1_500;
const POST_INSTALL_SETTLE_MS = 800;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function runScope(msg: ScopeExecuteMessage): Promise<ScopeResultPayload> {
  const { BootstrapItemSink, dyShouldContinueScroll, ingestMainWorldFetchMessage } =
    await loadTaskExecutorHelpers();
  const sink = new BootstrapItemSink({ maxItemsPerScope: msg.max_items_per_scope });
  const allItems: DouyinBootstrapItem[] = [];

  // Listen for fetch-tap captures only while this scope is active.
  // We filter by scope on the listener side so cross-scope contamination
  // doesn't happen if a stray /aweme/.../{post,like,...}/ request fires
  // (e.g. preloads from Douyin's own UI).
  const onMessage = (event: MessageEvent): void => {
    const newOnes = ingestMainWorldFetchMessage(event, sink);
    for (const item of newOnes) {
      if (item.scope === msg.scope) allItems.push(item);
    }
  };
  window.addEventListener("message", onMessage);

  try {
    // The MAIN-world fetch-tap auto-installs after waitForDouyinSdk
    // resolves. Give it a beat to settle so any pageload-time
    // /aweme/.../<scope>/ that fires AFTER our install gets captured.
    await sleep(POST_INSTALL_SETTLE_MS);

    let stagnantRounds = 0;
    for (let round = 0; round < msg.max_scroll_rounds; round += 1) {
      const beforeCount = sink.scopeCounts()[msg.scope];

      // Trigger Douyin's virtual-list pagination by scrolling down.
      // Use scrollBy with a large delta so even tall card lists move
      // multiple cards' worth per round.
      window.scrollBy({ top: window.innerHeight * 2, behavior: "auto" });
      await sleep(SCROLL_DELAY_MS);

      const afterCount = sink.scopeCounts()[msg.scope];
      stagnantRounds = afterCount > beforeCount ? 0 : stagnantRounds + 1;

      if (
        !dyShouldContinueScroll({
          currentCount: afterCount,
          maxItemsPerScope: msg.max_items_per_scope,
          round: round + 1,
          maxScrollRounds: msg.max_scroll_rounds,
          stagnantRounds,
          maxStagnantScrollRounds: msg.max_stagnant_scroll_rounds,
        })
      ) {
        break;
      }
    }

    return {
      task_id: msg.task_id,
      scope: msg.scope,
      items: allItems,
      scope_count: sink.scopeCounts()[msg.scope],
      status: allItems.length > 0 ? "ok" : "empty",
    };
  } catch (err) {
    return {
      task_id: msg.task_id,
      scope: msg.scope,
      items: allItems,
      scope_count: sink.scopeCounts()[msg.scope],
      status: "failed",
      error: String(err),
    };
  } finally {
    window.removeEventListener("message", onMessage);
  }
}

export function isValidScopeExecuteMessage(value: unknown): value is ScopeExecuteMessage {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  if (typeof v.task_id !== "string" || !v.task_id) return false;
  const KNOWN: readonly DouyinScope[] = ["dy_post", "dy_collect", "dy_like", "dy_follow"];
  if (!KNOWN.includes(v.scope as DouyinScope)) return false;
  if (typeof v.max_items_per_scope !== "number") return false;
  if (typeof v.max_scroll_rounds !== "number") return false;
  if (typeof v.max_stagnant_scroll_rounds !== "number") return false;
  return true;
}

export function registerDyScopeExecutor(): void {
  if (typeof chrome === "undefined" || !chrome.runtime || !chrome.runtime.onMessage) return;
  chrome.runtime.onMessage.addListener(
    (message: Record<string, unknown>, _sender, sendResponse) => {
      if (message.action !== "DY_SCOPE_EXECUTE") return false;
      const data = message.data;
      if (!isValidScopeExecuteMessage(data)) return false;

      void runScope(data).then((result) => {
        chrome.runtime.sendMessage({ action: "DY_SCOPE_RESULT", data: result }).catch(() => {
          // Service worker may have torn down between scopes; the
          // dispatcher will eventually time out and send status=failed
          // to the backend, so silent here is fine.
        });
      });

      // We don't use sendResponse — return false so the channel closes.
      return false;
    },
  );
}

if (typeof chrome !== "undefined" && chrome.runtime) {
  registerDyScopeExecutor();
  // eslint-disable-next-line no-console
  console.debug("[OpenBiliClaw] dy content script registered (isolated world)");
}
