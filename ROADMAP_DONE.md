# CrossTrans — Completed Roadmap Items

> Archive of finished roadmap work. Active/upcoming items live in `ROADMAP.md`.
> Full user-facing details are in `CHANGELOG.md`.

---

## R1 — Translation Result Cache + Re-translate Button — ✅ Done (1.9.16)

**Goal:** When the same source text is translated again with the same settings, return the
stored result instead of calling the AI API (saves quota/cost/latency, consistent output).
Provide a manual **"Re-translate"** button to force a fresh API call (bypass cache) so a
bad/garbled result is never "stuck".

**Delivered:**
- Reuse the existing 100-entry **history** as the lookup source — no new store.
  `HistoryManager.find_cached(original, target_lang)` scans most-recent-first, exact match,
  skips `"Error:"` results.
- `translate_text(..., skip_cache=False)` checks the cache before the API call (plain
  translations only — custom prompts bypass it) and returns early on a hit without re-adding
  to history.
- **"Re-translate"** button (orange) → `TranslationService.redo_translation()` forces a fresh
  API call (`skip_cache=True`), no COOLDOWN, no clipboard re-capture, runs off the UI thread.
- Button label is English **"Re-translate"** (no Vietnamese in code rule).
- **Omitted intentionally:** the optional cache on/off toggle — the Re-translate button is the
  escape hatch; cache is also inert when history is disabled.

**Files:** `src/core/history.py`, `src/core/translation.py`, `src/app.py`,
`src/ui/quick_translate.py`. **Tests:** `tests/test_translation_cache.py` (+13).

---

## R2 — Custom Prompt Button in Quick Translate Popup — ✅ Done (1.9.16)

**Goal:** A **"Custom Prompt"** button that turns the translation box editable; on submit the
box content is sent as the prompt (not the fixed translate instruction) — so besides
translating, the user can quickly ask something about the selected text.

**Delivered:**
- **"Custom Prompt"** button (teal) → makes the box editable (keeps current translation),
  swaps the bar to **[Send] [Cancel]**.
- On **Send**, the entire box content is sent verbatim via
  `TranslationService.ask_freeform(raw_prompt, target_lang)` — a raw path with no translate
  wrapper. Result rendered as a normal popup. Freeform asks are never written to history and
  never served from / written to the R1 cache.
- Edit-mode focus: temporarily clears `WS_EX_NOACTIVATE` + force-focus so typing works;
  restored on the result popup.
- **Layout decision (developer-selected):** single wide button bar, popup minimum width
  560→670px so all 7 actions + close fit one row.

**Files:** `src/ui/quick_translate.py`, `src/app.py`, `src/core/translation.py`.
**Tests:** `tests/test_freeform_prompt.py` (+7).

---

## R2-bug — custom_prompt Omits Source Text — ✅ Done (1.9.16)

**Found while scoping R2.** `translate_text()` custom_prompt branch did not include `{text}`,
so the main-window "additional instructions" feature sent instructions to the API with
nothing to translate.

**Fix:** the custom_prompt branch now embeds the source text via
`===TEXT TO TRANSLATE=== … ===END OF TEXT===` delimiters (same as the plain branch).
Covered by `tests/test_freeform_prompt.py::TestCustomPromptEmbedsText`.
