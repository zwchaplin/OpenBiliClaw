/**
 * OpenBiliClaw — Xiaohongshu content script entry.
 *
 * Injected into xiaohongshu.com pages. Wires the generic collector
 * kernel to the xhs-specific adapter. MVP scope: snapshot, click,
 * scroll, search — like/collect/comment are deliberately skipped.
 *
 * Also runs a strictly passive URL collector: when the user scrolls or
 * lands on an xhs page, we extract note URLs that are already visible and
 * forward them to the backend for enrichment. We never scroll ourselves.
 */

import { startCollector } from "./kernel.js";
import { xiaohongshuAdapter } from "../shared/platforms/xiaohongshu.js";
import {
  classifyXhsPageType,
  collectInViewportNoteUrls,
  dedupeObservedUrls,
  type AnchorLike,
  type ViewportRect,
  type XhsUrlObservation,
} from "./xhs/passive.js";
import { registerTaskExecutor } from "./xhs/task-executor.js";

startCollector(xiaohongshuAdapter);
registerTaskExecutor();

const PASSIVE_SCROLL_DEBOUNCE_MS = 500;
const PASSIVE_TOLERANCE_BELOW_PX = 400;
const PASSIVE_MAX_URLS_PER_BATCH = 20;
const PASSIVE_ANCHOR_SELECTOR = [
  'a[href*="/explore/"]',
  'a[href*="/discovery/item/"]',
].join(",");

const reportedUrls = new Set<string>();

function readViewport(): ViewportRect {
  const height = window.innerHeight || document.documentElement.clientHeight || 0;
  return { top: 0, bottom: height, height };
}

function snapshotAnchors(): AnchorLike[] {
  const nodes = document.querySelectorAll<HTMLAnchorElement>(PASSIVE_ANCHOR_SELECTOR);
  const anchors: AnchorLike[] = [];
  nodes.forEach((node) => {
    anchors.push({ href: node.href, rect: node.getBoundingClientRect() });
  });
  return anchors;
}

function runPassiveCollection(): void {
  const anchors = snapshotAnchors();
  const visible = collectInViewportNoteUrls(anchors, readViewport(), {
    baseUrl: window.location.href,
    toleranceBelowPx: PASSIVE_TOLERANCE_BELOW_PX,
  });
  const fresh = dedupeObservedUrls(visible, reportedUrls);
  if (fresh.length === 0) return;

  const observation: XhsUrlObservation = {
    urls: fresh.slice(0, PASSIVE_MAX_URLS_PER_BATCH),
    page_type: classifyXhsPageType(window.location.href),
    observed_at: Date.now(),
  };
  chrome.runtime.sendMessage({ action: "XHS_URLS_OBSERVED", data: observation });
}

let scrollTimer: number | null = null;
window.addEventListener(
  "scroll",
  () => {
    if (scrollTimer !== null) window.clearTimeout(scrollTimer);
    scrollTimer = window.setTimeout(runPassiveCollection, PASSIVE_SCROLL_DEBOUNCE_MS);
  },
  { passive: true },
);

// URL navigation in a SPA resets the "already reported" window so users
// don't miss a note just because they saw another one with the same id in
// a previous page-session.
window.addEventListener("popstate", () => {
  reportedUrls.clear();
  window.setTimeout(runPassiveCollection, PASSIVE_SCROLL_DEBOUNCE_MS);
});

window.setTimeout(runPassiveCollection, PASSIVE_SCROLL_DEBOUNCE_MS);

console.log(
  "[OpenBiliClaw] Xiaohongshu behavior collector initialized on",
  xiaohongshuAdapter.detectPageType(window.location.href),
  "page",
);
