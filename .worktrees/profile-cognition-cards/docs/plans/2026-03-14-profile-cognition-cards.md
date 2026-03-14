# Profile Cognition Cards Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade popup profile cognition updates from one-line strings into expandable cards that explain what changed, how it affects the portrait, and why the system thinks so.

**Architecture:** Extend the cognition update data model in the soul layer to emit structured fields (`summary`, `impact`, `reasoning`, `evidence`, `source`, `created_at`), expose them through `/api/profile-summary`, and render them as expandable cards in the popup profile tab. Keep backward compatibility for existing stored updates that only have `summary`.

**Tech Stack:** Python 3.14, FastAPI, vanilla JS popup UI, Node test runner, pytest

---

### Task 1: Define the structured cognition card contract

**Files:**
- Modify: `src/openbiliclaw/api/models.py`
- Modify: `src/openbiliclaw/api/app.py`
- Test: `tests/test_api_app.py`

**Step 1: Write the failing test**

Add an API test that expects `/api/profile-summary` to return `recent_cognition_updates` as structured items with `summary`, `impact`, `reasoning`, `evidence`, `source`, and `created_at`, while still accepting legacy memory entries with only `summary`.

**Step 2: Run test to verify it fails**

Run: `/Users/white/workspace/OpenBiliClaw/.venv/bin/pytest tests/test_api_app.py -q`
Expected: FAIL because `recent_cognition_updates` currently returns `list[str]`.

**Step 3: Write minimal implementation**

Add a `CognitionUpdateSummary` response model and update `profile_summary()` to map stored memory entries into that structured form, with graceful fallback for legacy records.

**Step 4: Run test to verify it passes**

Run: `/Users/white/workspace/OpenBiliClaw/.venv/bin/pytest tests/test_api_app.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/openbiliclaw/api/models.py src/openbiliclaw/api/app.py tests/test_api_app.py
git commit -m "feat: return structured profile cognition cards"
```

### Task 2: Generate structured cognition cards in the soul layer

**Files:**
- Modify: `src/openbiliclaw/soul/engine.py`
- Test: `tests/test_soul_engine.py`

**Step 1: Write the failing test**

Add focused tests for:

- immediate `comment` feedback cognition card
- immediate `dislike` feedback cognition card
- immediate dialogue cognition card
- batch refresh cognition card

Each test should assert `summary`, `impact`, `reasoning`, and `evidence` contents, not just presence.

**Step 2: Run test to verify it fails**

Run: `/Users/white/workspace/OpenBiliClaw/.venv/bin/pytest tests/test_soul_engine.py -q`
Expected: FAIL because cognition updates only store `summary`.

**Step 3: Write minimal implementation**

Extend the update builders in `SoulEngine` so both immediate and batch cognition paths emit the new fields with conservative wording and source-specific evidence.

**Step 4: Run test to verify it passes**

Run: `/Users/white/workspace/OpenBiliClaw/.venv/bin/pytest tests/test_soul_engine.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/openbiliclaw/soul/engine.py tests/test_soul_engine.py
git commit -m "feat: enrich cognition updates with impact and reasoning"
```

### Task 3: Normalize structured and legacy cognition cards in popup helpers

**Files:**
- Modify: `extension/popup/popup-helpers.js`
- Test: `extension/tests/popup-helpers.test.ts`

**Step 1: Write the failing test**

Add helper tests covering:

- structured cognition card normalization
- legacy string/summary-only fallback
- empty optional fields being omitted cleanly

**Step 2: Run test to verify it fails**

Run: `npm test -- --test-name-pattern "cognition"`
Expected: FAIL because popup helpers only accept `list[str]`.

**Step 3: Write minimal implementation**

Add a popup helper that normalizes cognition cards into one stable frontend shape:

- `summary`
- `impact`
- `reasoning`
- `evidence`
- `source`
- `created_at`
- `expandable`

**Step 4: Run test to verify it passes**

Run: `npm test -- --test-name-pattern "cognition"`
Expected: PASS

**Step 5: Commit**

```bash
git add extension/popup/popup-helpers.js extension/tests/popup-helpers.test.ts
git commit -m "feat: normalize popup cognition cards"
```

### Task 4: Render expandable cognition cards in the popup profile tab

**Files:**
- Modify: `extension/popup/popup.js`
- Modify: `extension/popup/popup.html`
- Test: `extension/tests/popup-helpers.test.ts`
- Test: `extension/tests/popup-copy.test.ts`

**Step 1: Write the failing test**

Add tests that describe the expected popup behavior:

- cognition cards render collapsed by default
- clicking one expands its detail sections
- opening a new card collapses the previous one
- legacy summary-only card still renders without expand details

**Step 2: Run test to verify it fails**

Run: `npm test`
Expected: FAIL because the profile tab still renders cognition updates as chips.

**Step 3: Write minimal implementation**

Replace the chip-list rendering for `profileRecentMemory` with expandable card rendering and add the corresponding markup/CSS hooks in `popup.html`.

**Step 4: Run test to verify it passes**

Run: `npm test`
Expected: PASS

**Step 5: Commit**

```bash
git add extension/popup/popup.js extension/popup/popup.html extension/tests/popup-helpers.test.ts extension/tests/popup-copy.test.ts
git commit -m "feat: render expandable profile cognition cards"
```

### Task 5: Update docs and run final verification

**Files:**
- Modify: `docs/modules/soul.md`
- Modify: `docs/modules/extension.md`
- Modify: `docs/changelog.md`

**Step 1: Update docs**

Document the new cognition card structure, API/UI behavior, and legacy fallback behavior.

**Step 2: Run backend verification**

Run: `/Users/white/workspace/OpenBiliClaw/.venv/bin/pytest tests/test_api_app.py tests/test_soul_engine.py tests/test_memory_manager.py -q`
Expected: PASS

**Step 3: Run extension verification**

Run: `npm test`
Expected: PASS

Run: `npm run build`
Expected: PASS

**Step 4: Commit**

```bash
git add docs/modules/soul.md docs/modules/extension.md docs/changelog.md
git commit -m "docs: record expandable profile cognition cards"
```
