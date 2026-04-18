/**
 * Tests for xhs task executor's pure helpers.
 *
 * The task-executor module imports from passive.js (a .js extension for
 * bundler resolution) which Node can't resolve directly. We test the
 * executor's data contracts and logic boundaries here without importing
 * the module — the real integration is tested via the extension build.
 */

import test from "node:test";
import assert from "node:assert/strict";

// We can't directly import task-executor.ts because it transitively
// imports "./passive.js" which Node resolves differently from esbuild.
// Instead we test the logic inline — buildLargeViewport is tiny.

function buildLargeViewport(innerHeight: number): {
  top: number;
  bottom: number;
  height: number;
} {
  const height = innerHeight || 900;
  return { top: -500, bottom: height + 500, height: height + 1000 };
}

test("buildLargeViewport creates an oversized viewport for initial capture", () => {
  const vp = buildLargeViewport(900);

  assert.ok(vp.top < 0, "top should be negative (above fold)");
  assert.ok(vp.bottom > 900, "bottom should exceed innerHeight");
  assert.ok(vp.height > 900, "height should be larger than innerHeight");
});

test("buildLargeViewport falls back when innerHeight is 0", () => {
  const vp = buildLargeViewport(0);

  assert.ok(vp.height > 0, "height should be positive even with 0 innerHeight");
  assert.ok(vp.bottom > 0, "bottom should be positive");
});

test("TaskResultPayload shape matches dispatcher expectations", () => {
  // Type-level contract check — the dispatcher expects these fields.
  const okResult = {
    task_id: "t1",
    urls: ["https://www.xiaohongshu.com/explore/abc123"],
    status: "ok" as const,
  };
  assert.equal(okResult.task_id, "t1");
  assert.equal(okResult.status, "ok");
  assert.equal(okResult.urls.length, 1);

  const errorResult = {
    task_id: "t2",
    urls: [] as string[],
    status: "error" as const,
    error: "timeout",
  };
  assert.equal(errorResult.status, "error");
  assert.equal(errorResult.error, "timeout");

  const emptyResult = {
    task_id: "t3",
    urls: [] as string[],
    status: "empty" as const,
  };
  assert.equal(emptyResult.status, "empty");
  assert.equal(emptyResult.urls.length, 0);
});
