# CrossTrans — Completed Roadmap Items

> Archive of finished roadmap work. Active/upcoming items live in `ROADMAP.md`.
> Full user-facing details are in `CHANGELOG.md`.

---

## F0–F7 — Furigana Everywhere — ✅ Done (2026-08-04 → 2026-08-17) [1.9.19]

**Goal:** wherever the app displays Japanese, show hiragana readings above the kanji, with the
language detected automatically. Before this, furigana existed only in the Quick Translate
popup's *source* block, and only for text that arrived through the translation pipeline.

**Architecture:** annotate at **render time**, not in the pipeline. The engine
(`src/core/furigana.py`) is pure logic with no Tk; the renderer (`src/ui/ruby_text.py`) is pure
presentation with no engine logic. Callers annotate the text they are about to display, so a new
surface needs no queue plumbing. Four invariants hold everywhere: **I1** annotation never alters
the text it describes, **I2** never `.get()` a ruby widget (use `get_plain()`), **I3** an
editable box stays plain, **I4** rendering is idempotent.

**Delivered, by phase:**

| # | What | Tests |
|---|------|-------|
| F0 | Engine: `RubySegment` contract, invariant I1, fail-safe aligner, fugashi→pykakasi chain | 124 → 208 |
| F1 | `RubyText` primitive — the single place ruby is drawn; `get_plain()`, pixel-accurate sizing | 208 → 257 |
| F2 | Popup output box — translating *into* Japanese finally shows readings | 257 → 286 |
| F3 | Main window output + expanded view — neither had ever shown readings | 286 → 307 |
| F4 | Reading pane under the input box (the box itself stays plain, per I3) | 307 → 331 |
| F5 | Dictionary result window — `dictionary_render.py` run model, monospace columns intact | 331 → 376 |
| F6 | Dictionary word chips and custom-box tags — `RubyRow`, `annotate_tokens()` | 376 → 422 |
| F7 | Hardening — prewarm off-thread, centralized constants, EXE build guard | 422 → 450 |

**The rule the whole feature is built on: blank beats a wrong reading.** An absent reading is
visibly absent; a wrong one is unfalsifiable at the point of use, by a reader who by definition
cannot check it. The aligner returns `None` rather than guess, and a token that cuts through a
reading is left bare.

**Measured decisions** (each one overturned the obvious approach):
- Annotation must be generated over the **largest available context** and then distributed, never
  per fragment. Proven twice: splitting a dictionary line at the looked-up word first makes
  all-kanji words like 勉強 unannotatable (F5), and annotating each chip separately makes 日本
  read にっぽん where the compound is にほん (F6).
- `Text.height` counts **base-font rows** (28 px), but a row carrying ruby is 47 px — so every
  height must be derived from font metrics, not a line count. This bug appeared twice (F1, F6).
- `window_create` defaults to `align='center'`, which puts plain chips 7 px off an annotated
  chip's baseline (F6).
- `Text.get()` returns zero characters for an embedded window while consuming an index, so it
  silently deletes every annotated word from Copy/Replace/re-send paths (F1).
- ttkbootstrap discards explicit colour kwargs on standard `tk` widgets at construction — which
  is why the reading colour never actually shipped before F2. Hence `NO_AUTOSTYLE`.
- `<<Modified>>` covers typing, paste, drag-and-drop, undo **and** programmatic rewrites, so one
  debounced binding replaced the planned per-call-site refresh wiring (F4).
- `prewarm()` had to annotate, not probe: `_refine_compounds()` needs pykakasi on every
  annotation even when fugashi is the active provider (F7).

**Explicit non-goals** (documented, not oversights): toasts and the history *list* (`tk.Label` /
60-char truncations; converting history rows would break click-to-load), `tk.Listbox`,
`ttk.Entry` / `Combobox`, buttons, menus, `messagebox`, OS title bars and the tray menu — Tk
cannot embed widgets in any of these.

**Files:** `src/core/furigana.py`, `src/ui/ruby_text.py`, `src/ui/dictionary_render.py` (new);
`src/ui/quick_translate.py`, `src/app.py`, `src/ui/expanded_window.py`,
`src/ui/dictionary_mode.py`, `src/ui/custom_word_boxes.py`, `src/ui/dictionary_popup.py`,
`src/ui/settings/hotkey_tab.py`, `src/core/translation.py`, `src/constants.py`, `config.py`,
`build_exe.bat`, `tools/verify_furigana_bundle.py`.
**Tests:** `test_furigana_core.py`, `test_ruby_text.py`, `test_popup_ruby.py`,
`test_main_window_ruby.py`, `test_reading_pane.py`, `test_dictionary_ruby.py`,
`test_word_chips_ruby.py`, `test_furigana_hardening.py` — 124 → 450 total, every suite
mutation-checked. See Decision 8.

---

## Rename — Storage Identity Aligned to CrossTrans — ✅ Done (2026-07-02) [1.9.19]

**Goal:** the app's internal **storage identity** still carried the legacy product name, while
the user-facing name in `src/constants.py` was already CrossTrans. Align them.

**Delivered:** the `%APPDATA%` config folder, the model-config cache folder, the Windows
auto-start registry value, and the DPAPI encryption entropy/description all renamed to
`CrossTrans`. A fresh install uses `%APPDATA%\CrossTrans\` throughout.

**⚠️ Breaking for existing installs, by design:**
- **Saved API keys must be re-entered** — the DPAPI entropy changed, so keys stored by an older
  build cannot be decrypted and are cleared on load.
- **Settings and history do not carry over**; the old folder is a harmless leftover.
- **Auto-start needs a one-time manual cleanup** for anyone who had it enabled: the old registry
  entry still launches the app, but the Settings toggle now manages the `CrossTrans` value only,
  so it reads OFF and cannot remove the stale one. Remove it via Task Manager → Startup apps.
- **No migration was implemented — deliberately.** The user chose a total rename (no trace of the
  old name anywhere) and a migration cannot coexist with that requirement. See Decision 7; do not
  re-propose migration.

**Verified:** a full-repo case-insensitive search for the old name returns **zero** matches
outside `.git`. 124 passed / 0 failed, no regressions.

**Files:** `config.py`, `src/core/crypto.py`, `src/core/remote_config.py`, `src/utils/updates.py`,
plus docs. See Decision 7.

---

## G2 — Merged Translate-or-Fix on the Language Hotkeys — ✅ Done (2026-07-01) [1.9.18]

**Goal:** pressing a language hotkey on text *already in that language* produced a pointless
"translation". Make it fix the grammar instead — without a dedicated hotkey, sidestepping the
Xbox Game Bar (`Win+Alt+G`) and Feedback Hub (`Win+Alt+F`) collisions entirely.

**Delivered:**
- `translate_or_fix()` sends **one merged prompt** and lets the model decide: same language →
  correct grammar/spelling/punctuation only, minimal change; otherwise → translate. Covers every
  language hotkey, defaults and custom, because `_on_hotkey_translate`'s normal branch handles
  all non-special language values.
- **Both branches uncensored and meaning-preserving.** The no-censor rule was also added to the
  plain `translate_text` prompts and the screenshot/OCR vision prompt, so offensive words survive
  every translation path, not just the merged one.
- **Separate cache namespace `'merged'`** — `find_cached()` gained a `source_type` param so a
  minimal-change fix is never cross-served as a plain rephrase translation, or vice versa.
- `Win+Alt+G` split from its button: the button stays ON by default, the global hotkey is now
  **OFF** by default (`fix_grammar_hotkey_enabled`).

**Known limits, documented not fixed:** uncensored output is best-effort and model-dependent
(hard content filters may still refuse or mask, and the explicit no-censor line can itself raise
refusals on benign text); the popup's Re-translate button re-runs the plain prompt, not the
merged one.

**Tests:** 100 → 124 (+24 `test_translate_or_fix.py`, +2 wiring guards), 0 regressions.
See Decision 6.

---

## G1 — Fix Grammar — ✅ Done (2026-06-30) [1.9.17]

**Goal:** correct the grammar of selected text **in place** — no translation, no rephrasing, no
censoring. Same text, same language, only grammar/spelling/punctuation changed.

**Delivered:** a `Win+Alt+G` hotkey, a "Fix Grammar" button in the main window, a Settings →
Hotkeys section (toggle + rebindable hotkey with duplicate validation), and a tray entry.
`fix_grammar()` builds a strict correction prompt; results are **not** written to history.
`do_grammar_fix()` queues a 6-tuple with `is_grammar=True`, which makes the popup hide the
translation-only buttons and keep Copy / Replace.

**Known collision, handled not avoided:** `Win+Alt+G` is Xbox Game Bar's "Record that".
Registration fails gracefully (error 1409) if Game Bar holds it, the hotkey is rebindable, and
the button always works. `Win+Alt+F` is the recommended conflict-free alternative. The default
was kept per the original spec.

**Tests:** 87 → 100 (+13 `test_fix_grammar.py`), 0 regressions. See Decision 5.

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
