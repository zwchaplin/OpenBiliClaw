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

// TEMP DEBUG: relay content-script events to daemon (see debug-log.ts).
function debugLog(event: string, data?: unknown): void {
  void fetch("http://127.0.0.1:8420/api/sources/_debug/log", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ source: "dy-cs", event, data: data ?? null }),
  }).catch(() => {});
}

/**
 * Re-inject the MAIN-world fetch-tap by appending a <script> element
 * with src pointing at the extension's bundled dy-fetch-tap.js.
 *
 * Why this is needed: chrome.scripting.executeScript runs once at
 * page load. After each click-driven SPA route, Douyin's React app
 * may re-set window.fetch with its own wrapper — replacing our
 * wrap and silently breaking aweme capture (e2e probe 2026-05-08:
 * install_messages_received=3 but aweme_messages_received=0
 * across all 4 scopes). Re-injecting the fetch-tap script after
 * every nav guarantees we're wrapping the latest live fetch.
 *
 * The script element is inserted into documentElement (DOM is
 * shared between isolated and MAIN worlds) and removed after
 * onload to keep the DOM clean. dy-fetch-tap.js is in
 * web_accessible_resources so chrome.runtime.getURL resolves it.
 */
function reinjectFetchTap(): void {
  if (typeof chrome === "undefined" || !chrome.runtime || !chrome.runtime.getURL) return;
  const script = document.createElement("script");
  script.src = chrome.runtime.getURL("dist/main/dy-fetch-tap.js");
  script.onload = () => script.remove();
  script.onerror = () => script.remove();
  (document.head || document.documentElement).appendChild(script);
}

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
  debug_inject_status?: string;
}

interface ScopeResultPayload {
  task_id: string;
  scope: DouyinScope;
  items: DouyinBootstrapItem[];
  scope_count: number;
  status: "ok" | "empty" | "failed";
  error?: string;
  /**
   * Diagnostic counters surfaced through the dispatcher into the
   * /api/sources/dy/task-result partial debug field. Lets us
   * disambiguate "scope returned empty because fetch-tap never
   * installed" from "fetch-tap installed but Douyin returned empty
   * 200s (risk control)" without needing the user's browser console.
   */
  debug?: {
    fetch_tap_install_status: "unknown" | "installed" | "skipped_no_sdk";
    aweme_messages_received: number;
    install_messages_received: number;
    inject_status?: string;
    page_url?: string;
    profile_link_found?: boolean;
    sub_tab_found?: boolean;
  };
}

const SCROLL_DELAY_MS = 1_500;
const POST_INSTALL_SETTLE_MS = 800;

// Module-level: track the last fetch-tap install ping. The MAIN-world
// dy-fetch-tap.js posts one of:
//   { type: "OPENBILICLAW_DOUYIN_FETCH_TAP_INSTALL", status: "installed" }
//   { type: "OPENBILICLAW_DOUYIN_FETCH_TAP_INSTALL", status: "skipped_no_sdk" }
// at install resolve. We capture it here so runScope can include the
// status in the result payload's debug field — that's how dispatcher
// diagnostic logs see whether the MAIN-world script actually wrapped
// fetch in this tab.
let _lastFetchTapInstallStatus: "unknown" | "installed" | "skipped_no_sdk" = "unknown";
let _installMessagesReceived = 0;
if (typeof window !== "undefined") {
  window.addEventListener("message", (event: MessageEvent) => {
    const data = event?.data as { type?: unknown; status?: unknown } | null;
    if (!data || typeof data !== "object") return;
    if (data.type === "OPENBILICLAW_DOUYIN_FETCH_TAP_INSTALL") {
      _installMessagesReceived += 1;
      const s = String(data.status ?? "");
      if (s === "installed" || s === "skipped_no_sdk") {
        _lastFetchTapInstallStatus = s;
      }
      return;
    }
    // TEMP DIAGNOSTIC (2026-05-08): relay every /aweme*/ URL the
    // MAIN-world tap sees back to the daemon log so we can diagnose
    // why aweme_messages_received stays at 0.
    if (data.type === "OPENBILICLAW_DOUYIN_URL_PROBE") {
      const probe = data as { transport?: unknown; url?: unknown; classified?: unknown };
      debugLog("url_probe", {
        transport: String(probe.transport ?? ""),
        url: String(probe.url ?? ""),
        classified: probe.classified ?? null,
      });
    }
  });
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Find the homepage's "我" / profile link. Tries multiple selectors
 * because Douyin's UI structure shifts across releases.
 *
 * Returns the element to click, or null if no candidate found.
 */
function findProfileLink(): HTMLElement | null {
  // Most direct: anchor whose href points at /user/self or any
  // /user/<sec_uid> pattern. CRITICAL: skip anchors whose href
  // includes "?showTab=" — Douyin's leftnav has direct shortcuts
  // to "喜欢" / "收藏" / "关注" sub-tabs (e.g.
  // <a href="/user/self?showTab=like">), and matching one of those
  // sends us to the wrong tab. e2e probe 2026-05-08 caught this.
  const candidates = Array.from(
    document.querySelectorAll<HTMLAnchorElement>(
      'a[href="/user/self"], a[href^="/user/MS4w"], a[href*="/user/self"], a[href*="/user/"]',
    ),
  );
  for (const anchor of candidates) {
    const href = anchor.getAttribute("href") ?? "";
    if (href.includes("?showTab=")) continue; // skip sub-tab shortcuts
    return anchor;
  }
  // Data-attribute selectors (e2e test selectors Douyin sometimes ships).
  const dataSelectors = [
    '[data-e2e="profile-icon"]',
    '[data-e2e="user-tab-self"]',
    '[data-e2e="user-info"]',
    '[data-e2e="my-tab"]',
  ];
  for (const sel of dataSelectors) {
    const el = document.querySelector(sel);
    if (el && "click" in el) return el as HTMLElement;
  }
  // Last resort: anchor / button / clickable div whose visible text
  // is the leftnav profile entry. Douyin's left sidebar has been
  // observed shipping this as either "我" or "我的" (and "我的"
  // occasionally as part of a longer label like "我的关注"). Match
  // exactly to avoid clicking an unrelated string-containing element.
  const profileLabels = ["我", "我的", "个人主页"];
  const textCandidates = Array.from(
    document.querySelectorAll<HTMLElement>(
      'a, button, [role="link"], [role="button"], [data-e2e]',
    ),
  );
  for (const el of textCandidates) {
    const text = el.textContent?.trim() ?? "";
    if (profileLabels.includes(text)) return el;
  }
  return null;
}

/**
 * Find the sub-tab element on the user profile page for a given scope.
 * Returns null for dy_post (which is the default visible tab — no
 * click needed to land on it).
 */
function findScopeSubTab(scope: DouyinScope): HTMLElement | null {
  if (scope === "dy_post") return null;
  const dataSelectors: Record<DouyinScope, string[]> = {
    dy_post: [],
    dy_collect: [
      '[data-e2e="user-favorite-tab"]',
      '[data-e2e="user-tab-favorite_collection"]',
      'a[href*="favorite_collection"]',
    ],
    dy_like: [
      '[data-e2e="user-like-tab"]',
      '[data-e2e="user-tab-like"]',
      'a[href*="showTab=like"]',
    ],
    dy_follow: [
      '[data-e2e="user-following-tab"]',
      '[data-e2e="user-tab-following"]',
      'a[href*="showTab=following"]',
    ],
  };
  for (const sel of dataSelectors[scope]) {
    const el = document.querySelector(sel);
    if (el && "click" in el) return el as HTMLElement;
  }
  // Text fallback. Douyin sub-tab labels:
  //   dy_collect → 收藏
  //   dy_like    → 喜欢
  //   dy_follow  → 关注
  const labelMap: Record<DouyinScope, string> = {
    dy_post: "作品",
    dy_collect: "收藏",
    dy_like: "喜欢",
    dy_follow: "关注",
  };
  const label = labelMap[scope];
  const candidates = Array.from(
    document.querySelectorAll<HTMLElement>('a, button, [role="tab"], [class*="tab"]'),
  );
  for (const el of candidates) {
    if (el.textContent?.trim() === label) return el;
  }
  return null;
}

/**
 * Drive the page from wherever it currently is to the requested
 * scope's view, using **clicks**, not URL writes. This makes the
 * navigation look like user behaviour to Douyin's risk control —
 * direct chrome.tabs.update jumps to /user/self trip the captcha
 * intermediate page (verified 2026-05-08 e2e).
 *
 * Flow per scope:
 *   1. If we're on the homepage (anywhere outside /user/), click
 *      the profile link to land on /user/<sec_uid>. SPA-route, no
 *      document commit, fetch-tap stays.
 *   2. If the requested scope isn't dy_post (which is the default
 *      visible tab), click the sub-tab element. Again SPA-route.
 *
 * Returns true on best-effort success (click(s) attempted), false if
 * we couldn't find any candidate elements — caller can still proceed
 * to scroll loop, just won't have items.
 */
interface ClickToScopeReport {
  page_url: string;
  profile_link_found: boolean;
  sub_tab_found: boolean;
}

async function clickToScope(scope: DouyinScope): Promise<ClickToScopeReport> {
  const report: ClickToScopeReport = {
    page_url: location.href,
    profile_link_found: false,
    sub_tab_found: false,
  };
  // Step 1: get to /user/self if we're still on the homepage.
  // Click is preferred (mirrors user behaviour, avoids risk-control
  // friction); pushState fallback if no profile link found.
  const onProfile = location.pathname.startsWith("/user/");
  if (!onProfile) {
    const profileLink = findProfileLink();
    report.profile_link_found = profileLink !== null;
    if (profileLink) {
      profileLink.click();
    } else {
      window.history.pushState({}, "", "/user/self");
      window.dispatchEvent(new PopStateEvent("popstate"));
    }
    await sleep(2_500);
    report.page_url = location.href;
  }

  // Step 2: navigate to the target scope tab via pushState. Verified
  // empirically (2026-05-08 e2e + url_probe) that clicking
  // [data-e2e="user-<scope>-tab"] elements is a no-op when Douyin's
  // React Router thinks we're already on the same route — the URL
  // doesn't change and no /aweme/v1/web/aweme/<scope>/ request fires.
  // pushState + popstate forces React Router to detect the route
  // change and re-mount the scope tab, which DOES trigger the data
  // fetch.
  //
  // Bounce through a neutral URL first when the current URL already
  // points at the target tab (e.g. landing page from previous run was
  // ?showTab=like and scope=dy_like). Without the bounce, pushing the
  // same URL is a true no-op.
  const queryMap: Record<DouyinScope, string> = {
    dy_post: "",
    dy_collect: "?showTab=favorite_collection",
    dy_like: "?showTab=like",
    dy_follow: "?showTab=following",
  };
  const targetUrl = "/user/self" + queryMap[scope];
  const currentRelative = location.pathname + location.search;
  if (currentRelative === targetUrl) {
    // Same — bounce off a sentinel query to force re-route.
    window.history.pushState({}, "", "/user/self?_obc=" + Date.now());
    window.dispatchEvent(new PopStateEvent("popstate"));
    await sleep(400);
  }
  window.history.pushState({}, "", targetUrl);
  window.dispatchEvent(new PopStateEvent("popstate"));
  report.sub_tab_found = true; // pushState always succeeds
  await sleep(2_500); // allow React Router to refetch + render
  report.page_url = location.href;
  return report;
}

async function runScope(msg: ScopeExecuteMessage): Promise<ScopeResultPayload> {
  debugLog("runScope:start", {
    scope: msg.scope,
    page_url: location.href,
    inject_status: msg.debug_inject_status,
  });
  const { BootstrapItemSink, dyShouldContinueScroll, ingestMainWorldFetchMessage } =
    await loadTaskExecutorHelpers();
  const sink = new BootstrapItemSink({ maxItemsPerScope: msg.max_items_per_scope });
  const allItems: DouyinBootstrapItem[] = [];
  // Per-scope counter: how many OPENBILICLAW_DOUYIN_AWEME_PAGE messages
  // the MAIN-world fetch-tap pushed into this scope's listener window.
  // Distinguished from items count: a message can carry items the sink
  // dedups away or items for the wrong scope, so a non-zero
  // aweme_messages_received with zero items is its own signature.
  let awemeMessagesReceived = 0;

  const onMessage = (event: MessageEvent): void => {
    const data = event?.data as { type?: unknown } | null;
    if (data && typeof data === "object" && data.type === "OPENBILICLAW_DOUYIN_AWEME_PAGE") {
      awemeMessagesReceived += 1;
    }
    const newOnes = ingestMainWorldFetchMessage(event, sink);
    for (const item of newOnes) {
      if (item.scope === msg.scope) allItems.push(item);
    }
  };
  window.addEventListener("message", onMessage);

  let clickReport: ClickToScopeReport = {
    page_url: location.href,
    profile_link_found: false,
    sub_tab_found: false,
  };
  try {
    // Navigate via UI clicks (more natural to Douyin risk control
    // than chrome.tabs.update URL jumps). clickToScope handles both
    // the homepage→profile transition and the sub-tab switch.
    clickReport = await clickToScope(msg.scope);
    debugLog("runScope:clickToScope_done", { scope: msg.scope, clickReport });

    // Re-inject MAIN-world fetch-tap after the click-driven SPA route.
    // Douyin's React app sometimes re-sets window.fetch on URL change,
    // which would silently bypass our wrap. Reinjecting guarantees
    // the latest live fetch is wrapped.
    reinjectFetchTap();
    debugLog("runScope:reinjected_fetch_tap");

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
      debug: {
        fetch_tap_install_status: _lastFetchTapInstallStatus,
        aweme_messages_received: awemeMessagesReceived,
        install_messages_received: _installMessagesReceived,
        inject_status: msg.debug_inject_status,
        page_url: clickReport.page_url,
        profile_link_found: clickReport.profile_link_found,
        sub_tab_found: clickReport.sub_tab_found,
      },
    };
  } catch (err) {
    return {
      task_id: msg.task_id,
      scope: msg.scope,
      items: allItems,
      scope_count: sink.scopeCounts()[msg.scope],
      status: "failed",
      error: String(err),
      debug: {
        fetch_tap_install_status: _lastFetchTapInstallStatus,
        aweme_messages_received: awemeMessagesReceived,
        install_messages_received: _installMessagesReceived,
        inject_status: msg.debug_inject_status,
        page_url: clickReport.page_url,
        profile_link_found: clickReport.profile_link_found,
        sub_tab_found: clickReport.sub_tab_found,
      },
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
      if (!isValidScopeExecuteMessage(data)) {
        debugLog("listener:invalid_scope_execute", { message });
        return false;
      }
      debugLog("listener:DY_SCOPE_EXECUTE_received", {
        scope: (data as { scope: string }).scope,
        page_url: location.href,
      });

      void runScope(data).then((result) => {
        debugLog("runScope:returning", {
          scope: result.scope,
          status: result.status,
          items_count: result.items.length,
        });
        chrome.runtime.sendMessage({ action: "DY_SCOPE_RESULT", data: result }).catch((err) => {
          debugLog("listener:DY_SCOPE_RESULT_send_failed", { error: String(err) });
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
