/**
 * xhs no-scroll task executor — content-script side.
 *
 * When the background dispatcher opens a tab with a search or creator
 * page, this module waits for note cards to render (MutationObserver,
 * 5 s hard cap), extracts up to 20 note URLs from the initial viewport
 * plus immediately adjacent DOM, and emits `XHS_TASK_RESULT` back to
 * the service worker.
 *
 * **Never scrolls** — reading only what the page initially renders is
 * the safest posture against xhs risk control. The user's real browser
 * provides logged-in cookies; we're just a fast reader.
 */

import {
  collectInViewportNoteUrls,
  type AnchorLike,
  type ViewportRect,
} from "./passive.js";

const MAX_URLS = 20;
const RENDER_WAIT_MS = 5_000;
const CHECK_INTERVAL_MS = 300;
const ANCHOR_SELECTOR = 'a[href*="/explore/"], a[href*="/discovery/item/"]';

export interface TaskExecuteMessage {
  task_id: string;
  type: "search" | "creator";
}

export interface TaskResultPayload {
  task_id: string;
  urls: string[];
  status: "ok" | "empty" | "error";
  error?: string;
}

// ---------------------------------------------------------------------------
// Pure helpers (testable)
// ---------------------------------------------------------------------------

export function snapshotAllAnchors(root: Document): AnchorLike[] {
  const nodes = root.querySelectorAll<HTMLAnchorElement>(ANCHOR_SELECTOR);
  const out: AnchorLike[] = [];
  nodes.forEach((node) => {
    out.push({ href: node.href, rect: node.getBoundingClientRect() });
  });
  return out;
}

export function buildLargeViewport(win: Window): ViewportRect {
  // Use a very tall viewport so we capture cards beyond the fold too —
  // the page just loaded so everything rendered is fair game.
  const height = win.innerHeight || 900;
  return { top: -500, bottom: height + 500, height: height + 1000 };
}

// ---------------------------------------------------------------------------
// Chrome integration
// ---------------------------------------------------------------------------

function waitForCards(doc: Document): Promise<boolean> {
  return new Promise((resolve) => {
    // Quick check — cards may already be present.
    if (doc.querySelectorAll(ANCHOR_SELECTOR).length > 0) {
      resolve(true);
      return;
    }

    let settled = false;
    const observer = new MutationObserver(() => {
      if (doc.querySelectorAll(ANCHOR_SELECTOR).length > 0) {
        settled = true;
        observer.disconnect();
        resolve(true);
      }
    });
    observer.observe(doc.body ?? doc.documentElement, {
      childList: true,
      subtree: true,
    });

    // Fallback polling for frameworks that batch mutations.
    const interval = setInterval(() => {
      if (settled) {
        clearInterval(interval);
        return;
      }
      if (doc.querySelectorAll(ANCHOR_SELECTOR).length > 0) {
        settled = true;
        observer.disconnect();
        clearInterval(interval);
        resolve(true);
      }
    }, CHECK_INTERVAL_MS);

    // Hard cap — give up after RENDER_WAIT_MS.
    setTimeout(() => {
      if (!settled) {
        settled = true;
        observer.disconnect();
        clearInterval(interval);
        resolve(doc.querySelectorAll(ANCHOR_SELECTOR).length > 0);
      }
    }, RENDER_WAIT_MS);
  });
}

async function executeTaskInPage(
  msg: TaskExecuteMessage,
  win: Window,
  doc: Document,
): Promise<TaskResultPayload> {
  try {
    const found = await waitForCards(doc);
    if (!found) {
      return { task_id: msg.task_id, urls: [], status: "empty" };
    }

    const anchors = snapshotAllAnchors(doc);
    const viewport = buildLargeViewport(win);
    const urls = collectInViewportNoteUrls(anchors, viewport, {
      baseUrl: win.location.href,
      toleranceBelowPx: 500,
      toleranceAbovePx: 500,
    });

    if (urls.length === 0) {
      return { task_id: msg.task_id, urls: [], status: "empty" };
    }

    return { task_id: msg.task_id, urls: urls.slice(0, MAX_URLS), status: "ok" };
  } catch (err) {
    return {
      task_id: msg.task_id,
      urls: [],
      status: "error",
      error: String(err),
    };
  }
}

/**
 * Register the message listener that the background dispatcher uses to
 * trigger task execution. Call once from the xhs content-script entry.
 */
export function registerTaskExecutor(): void {
  chrome.runtime.onMessage.addListener(
    (message: Record<string, unknown>, _sender, sendResponse) => {
      if (message.action !== "XHS_TASK_EXECUTE") return false;

      const data = message.data as TaskExecuteMessage | undefined;
      if (!data?.task_id) return false;

      // Run async, then post result back via runtime message (not sendResponse)
      // because the dispatcher listens via onMessage, not via callback.
      void executeTaskInPage(data, window, document).then((result) => {
        chrome.runtime.sendMessage({
          action: "XHS_TASK_RESULT",
          data: result,
        });
      });

      // Return false — we don't use sendResponse.
      return false;
    },
  );
}
