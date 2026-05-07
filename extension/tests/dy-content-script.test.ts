/**
 * Tests for the Douyin content-script entry's pure helpers.
 *
 * Task 4 completion (the gap I missed in the original commit). The
 * runScope orchestration touches window.scrollBy / setTimeout /
 * postMessage and isn't unit-testable here without elaborate DOM
 * mocks; the chrome-devtools MCP real-extension probe covers that
 * surface end-to-end.
 *
 * Module isolation: zero imports from extension/src/content/xhs/.
 */

import test from "node:test";
import assert from "node:assert/strict";

import { isValidScopeExecuteMessage } from "../src/content/douyin.ts";

test("isValidScopeExecuteMessage accepts a well-formed scope payload", () => {
  assert.equal(
    isValidScopeExecuteMessage({
      task_id: "t1",
      scope: "dy_post",
      max_items_per_scope: 300,
      max_scroll_rounds: 15,
      max_stagnant_scroll_rounds: 5,
    }),
    true,
  );
});

test("isValidScopeExecuteMessage rejects malformed input", () => {
  assert.equal(isValidScopeExecuteMessage(null), false);
  assert.equal(isValidScopeExecuteMessage("string"), false);
  assert.equal(isValidScopeExecuteMessage({}), false);
  // Missing task_id
  assert.equal(
    isValidScopeExecuteMessage({
      scope: "dy_post",
      max_items_per_scope: 300,
      max_scroll_rounds: 15,
      max_stagnant_scroll_rounds: 5,
    }),
    false,
  );
  // Unknown scope
  assert.equal(
    isValidScopeExecuteMessage({
      task_id: "t",
      scope: "unknown",
      max_items_per_scope: 300,
      max_scroll_rounds: 15,
      max_stagnant_scroll_rounds: 5,
    }),
    false,
  );
  // Wrong type for numeric field
  assert.equal(
    isValidScopeExecuteMessage({
      task_id: "t",
      scope: "dy_collect",
      max_items_per_scope: "300",
      max_scroll_rounds: 15,
      max_stagnant_scroll_rounds: 5,
    }),
    false,
  );
});

test("isValidScopeExecuteMessage accepts all four scopes", () => {
  for (const scope of ["dy_post", "dy_collect", "dy_like", "dy_follow"] as const) {
    assert.equal(
      isValidScopeExecuteMessage({
        task_id: "t",
        scope,
        max_items_per_scope: 1,
        max_scroll_rounds: 0,
        max_stagnant_scroll_rounds: 0,
      }),
      true,
      `expected scope=${scope} to validate`,
    );
  }
});
