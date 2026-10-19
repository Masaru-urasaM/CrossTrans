# CrossTrans — Completed Roadmap Items

> Archive of finished roadmap work. Active/upcoming items live in `ROADMAP.md`.
> Full user-facing details are in `CHANGELOG.md`.

---

## P — The quick-translate popup: sized by measuring, laid out for reading — ✅ Done (2026-10-19) [on `main`, for 1.9.21]

**Goal (user, 2026-10-19, restated in English):** the quick-translate box "does not size itself
well - a better way, or a new way of deciding its size; the end goal is an interface much easier to
read and to operate". Measured on 13 cases and presented as three options; the user chose **B + C**
- measure the real layout, size for reading, and lay the popup out again - every open question as
recommended, all of it for 1.9.21, and P1-P4 "in one pass, tested once at the end". The plan, with
the findings: `git show 57d739f:TODO.md`. Decision 34.

| Phase | What | Commit | Tests |
|---|---|---|---|
| Plan | Findings S1-S10 measured on 13 cases, design, phases; Decision 34 (Decision 3 superseded) | `87faae7` | 1525 |
| P0 | The corpus (`tests/popup_cases.py`) and the gallery tool (`tools/popup_gallery.py`); the `before` gallery | `57d739f` | 1547 |
| P1 | The close button always drawn: the minimum width read off the rows (`packed_row_width`); "Get Free API Key" sized to its label | this entry | |
| P2 | The two-step show (alpha 0, laid out, measured, placed, shown); boxes in holders with exact heights; scrollbars only when capped; the 60% cap; placement beside the cursor (`src/ui/popup_layout.py`); the loading indicator by the same rules | this entry | |
| P3 | The header with the credit and the close button in every state; Copy and Replace as words, four icons with tooltips; the original named and collapsed to three rows | this entry | |
| P4 | The resize grip; the size remembered (`config.get/set_quick_popup_size`); a double-click returns to automatic | this entry | 1711 |
| Fix | "Show all" on a small screen (CI) | `51435a3` | 1714 |
| Fix | The grip drags an outline; the popup follows when the drag pauses (the user found the drag laggy; Decision 35) | `7a0a79d` | 1723 |
| Fix | On top from when it appears (found under a maximized VS Code); every edge and corner resizes; one row a box at least, out to the screen under the pointer; the popup's timers on the root (Decision 35, "Then, the same day") | this entry | 1780 |

| Same 17 popups | Before | After |
|---|---|---|
| Close button drawn | 12 of 17 | 17 of 17 |
| Blank band under the text | 2-37 px (28 typical) | 0 px in every case |
| Characters per line, Latin, worst paragraph | 99-111 | 66 |
| One word | 670×161 | 395×136 |
| Kanji term, trial line + chooser row | 670×232, "Get Free API Key" cut | 395×209, nothing cut |
| Long Japanese with readings | 800×1012 across the cursor's line, 156 px hidden, no scrollbar | 521×619, below the cursor's line, scrollbars |

**Checked, not assumed**: the gallery (`tools/popup_gallery.py --label after`) - every case and
state with its close button inside, no blank pixels, nothing clipped, nothing over the cursor; the
full suite on the private desktop (1711 passed, 1 skipped); 19 mutations, all killed. **Found**: DEFERRED D20 - the popup's `WS_EX_NOACTIVATE` has
never been in effect; left for the user (it decides whether Ctrl+C on a selection in the popup
keeps working).

**Since**: merged and pushed (`b64cd92`, then the fixes `51435a3`, `4f926b4`, `f4781dc` - Decision
35), rebuilt as `dist\CrossTrans_v1.9.21_edges_2026-10-19.exe`, and the manual checks below passed
on it - the user, 2026-10-19: "a complete success". **Still the user's**: the tag and the release.

The manual checks, with the running CrossTrans closed first (a second instance only brings the
first one forward):
1. In Notepad select `Hello` and press your translate hotkey: a small popup beside the cursor, the
   close button at the top right, no empty band under the text; the close button closes it.
2. A paragraph of about five lines: about 70 characters a line, the box ending where the text ends.
3. A long article: at most about 60% of the screen high, a scrollbar, the cursor's line not covered.
4. Japanese text: "Original (Japanese)" above the translation, collapsed to three rows; "Show all"
   opens it, "Show less" closes it.
5. A kanji-only word such as 汽車: the chooser row; the popup grows by that row only.
6. Trial mode: "Get Free API Key" fully readable.
7. Replace: the preview fits, Agree pastes; Custom Prompt: the box keeps its size and scrolls,
   Send and Cancel work.
8. An invalid key: the error popup with API Settings, Open Translator and the close button.
9. The cursor at the bottom-right corner of the screen: the popup opens above and to the left.
10. Hover each icon: its name appears; each icon does what its name says.
11. Drag the grip at the bottom right: a blue outline follows the mouse smoothly, even on a long
    text; hold still for a moment and the popup takes the outline's size; let go and it keeps it.
    The next popup uses that width and height; a double-click on the grip returns to automatic
    sizing. Every edge and corner works the same way - the cursor changes over the outer few
    pixels - and the rest of the border still moves the popup. It shrinks to a row of text, grows to
    the screen's edge, and can be stretched onto a second monitor.
12. Translate into and from Vietnamese (not in the automated corpus): lines and heights look right
    with the diacritics.
13. With two monitors: select text in a maximized window (VS Code) on the second monitor and press
    the hotkey - the popup shows above it, beside the cursor, every time.

---

## K — Follow-ups to the language-identity work, then quiet tests — ✅ Done (2026-10-16) [on `main`, for 1.9.21]

**Goal (user, 2026-10-16):** do all fifteen items proposed after J12 - the suite on a clean machine,
the EXE and D16 before a release (items 1-3), the new feature's gaps (4-8), History and the old
deferred items (9-11), AGENTS.md (12), tooling (13-15). Midway the user reported that the test runs
threw windows over the screen and interrupted other work, and that the translation quota was used
up: K12.

| Phase | What | Commit | Tests |
|---|---|---|---|
| K1 | The suite on a clean venv (requirements only): 5 word-chip failures fixed; D19 found | `c00d284` | 1183 -> 1184 |
| K2 | D16: the failed-update dialog no longer freezes the app | `ffea35b` | 1202 |
| K3 | The Dictionary keeps the user's "Japanese or Chinese?" answer (Decision 28) | `2429741` | 1232 |
| K4 | A term a model placed can be read as the other language (Decision 29) | `6927a23` | 1264 |
| K5 | The main window's own Japanese / Chinese row | `41aeeac` | 1279 |
| K6 | A Chinese sentence is known by its function words (Decision 30) | `2ee5ee4` | 1315 |
| K7 | History: lines cut to the row in pixels, the first rows at once (D17) | `f4c178a` | 1331 |
| K8 | D18 removed; D12 fixed - the key decides (Decision 31); D11 desk-checked | `efbc60b` | 1360 |
| K9 | The mutation runner in tools/, the CI floor at 1350, eval repeats and phrases | `4eac224` | 1392 |
| K10 | Real models: the trial model, phrases, screenshots (52 real calls) | `b5f6f92` | 1413 |
| K11 | The EXE, built by hand (dist/ kept) and checked, the glyph codecs included | `e853854` | 1421 |
| K12 | Quiet tests: a private desktop; no network, clipboard or keystrokes; the eval tools ask for the count (Decision 32) | `d6235cc` | 1502 |
| K13 | Final check on a fresh clone, AGENTS.md regenerated, archive | this entry | 1502 |

Items to phases: 1 -> K1 and K13, 2 -> K11, 3 -> K2, 4 -> K4, 5 -> K3, 6 -> K5, 7 -> K6, 8 -> K10,
9 and 10 -> K7, 11 -> K8, 12 -> K13, 13-15 -> K9.

**Checked, not assumed**: 110 mutations across K2-K12, all killed (`tools/mutation_check.py`). K12:
no window of the test process on the user's desktop and no focus taken, in four full runs and every
mutation run. K13: a fresh clone on a requirements-only venv - 1491 passed, 11 skipped (nine need
fugashi + UniDic, one a built EXE, one the real clipboard), 0 failed.

**Made without the user, then approved**: Decisions 28-32. The user asked for every item at once,
and K12's options were built before the user chose between them; the user approved all five on
2026-10-16.

**Since**: merged into `main` and pushed, the version chosen (1.9.21) - all 2026-10-16; D19 decided
(a download, K14); the Worker deployed (2026-10-19). **Still the user's**: the tag, keys for D11's
eight providers, and the manual checks (item 7's EXE is now
`dist\CrossTrans_v1.9.21_edges_2026-10-19.exe`):
1. Popup, a term a model places: select 汽車 and press Win+Alt+E - a row "Kanji-only text - read as
   Chinese. [Read as Japanese]"; the button re-translates it as Japanese, with readings.
2. Popup, a Chinese sentence: 這是我的書。 - no row (its grammar settles it), translated as Chinese.
3. Main window: type 汽車, Translate - the same row beside "Original:"; an answer re-translates, and
   the Reading pane reads it once it is Japanese.
4. Dictionary memory: main window, 手紙, Dictionary, answer "Japanese", close; Dictionary again -
   no question.
5. History: a long Japanese line ends in "..." at the row's edge; with 100 entries the window
   opens at once.
6. The failed-update dialog (D16): create `%TEMP%\crosstrans_update_error.txt` holding any text and
   start the app - about a second later the "Update Failed" dialog appears in front, answers clicks,
   and closes; the app is not frozen.
7. The EXE (`dist\CrossTrans_v1.9.20_branch_2026-10-16.exe`): translate 東京大学, then
   `%APPDATA%\CrossTrans\logs` holds no "[LangID] glyph evidence disabled".

---

## J — Japanese Language Identity: furigana on every Japanese surface, a Dictionary that knows its languages — ✅ Done (2026-10-15) [on `main`, for 1.9.21]

**Goal (user, 2026-10-15):** show furigana wherever Japanese appears, the Dictionary included,
and stop the Dictionary taking a Japanese word written only in kanji for Chinese - its prompt
must know the language it translates *from* and *into*. Planned in `TODO.md` (deleted on
completion; last version: `git show 5cc8736:TODO.md`).

**The user's answers that shaped it** (Q1-Q10): the AI model decides what ambiguous kanji-only
text is, the user settles what it cannot - **no Settings default** (Decision 22); translation
prompts learn the source too (Q7); Japanese pronunciation in hiragana only, no romaji; the
sentence is sent with a lookup (≤ 600 characters); Japanese -> Japanese is a monolingual entry
with furigana; History rows in scope, toasts and the Replace preview's original not; screenshot
OCR shown and stored; real API evaluation allowed; `h1-health-review` merged into `main` first.
The two Dictionary-mode copies were then consolidated at the user's request (D13).

| Phase | What | Commit | Tests |
|---|---|---|---|
| J0-J1 | Eval tool; the dictionary prompt states source -> target and sends the sentence | `7ce1034` | 676 -> 755 |
| D13-D15 | One Dictionary mode for both buttons; failed lookups show their message; no `grab_set()` | `023a6b2` | 780 |
| J2 | `lang_id`: Japanese vs Chinese from evidence only (Big5-HKSCS trap) | `bd95d96` | 903 |
| J3 | The dictionary result reads the stated source and both languages of an entry | `4f2f84b` | 952 |
| J4 | Translation prompts state the source or ask for a `[[SOURCE: ...]]` line | `e097658` | 1011 |
| J5 | One detector; the Dictionary opens in the model's language or asks | `8c432b1` | 1071 |
| J6 | Popup: source block, hints, "Japanese or Chinese?" row that re-translates | `b77c032` | 1118 |
| J7 | Main window: Reading pane, output, grammar result, expanded view | `9710341` | 1132 |
| J8 | Screenshot OCR shown with readings; History keeps the OCR text | `b76917a` | 1154 |
| J9 | History rows carry readings (one canvas per line) | `5cc8736` | 1173 |
| J12 | Final check (a stray marker reached the popup), docs, archive | this entry | 1183 |

Every phase's tests were mutation-checked (revert the guarded line, see the suite fail,
restore): 145 mutations (17 in J1, 128 since), all killed but one equivalent (J5). The final check re-ran every suite
after finding that the runner could reuse a previous mutant's bytecode (same size, same second);
the corrected runner deletes the module's `.pyc` and writes none.

**Measured on real models** (Google gemini-2.5-flash, Groq gpt-oss-120b, trial llama-3.3-70b):
Dictionary with the sentence and the source stated **10/10 Japanese** on all three (7/10 before);
the translation marker **10/10** on Google and Groq, never leaked, Unknown 3-4 in ten. **Not
measured live:** the screenshot section (needs a real capture) - unit-tested only.

**Decisions:** 21 (state the source only when it is evidence; send the sentence), 22 (evidence,
then the model, then the user), 23 (one Dictionary mode), 24 (Big5-HKSCS), 25 (the marker; cache
not namespaced), 26 (no identification call - ask), 27 (the popup's answer re-translates).
**26, 27 and 25's cache choice were made without the user** (asked to finish in one go) - each
records why, and what to revisit.

**Left over:** D16 (`UpdateFailedDialog` on the withdrawn root - the documented freeze trap),
D17 (the History dialog takes ~1 s to open with 100 entries, before any readings), D18 (dead code).

**Manual acceptance checklist** (run from source, Furigana ON; Dictionary rows need the Japanese
language pack, row 8 also Chinese (Simplified)):

| # | Do | Expect |
|---|----|--------|
| 1 | Select `勉強` in Notepad → Win+Alt+E | "Study" with 勉強[べんきょう] above it - or, when the model was unsure, a row "Kanji-only text - read it as: Japanese / Chinese": click Japanese → re-translated, readings shown |
| 2 | Popup → Dictionary | Opens as Japanese, no dialog; the 勉強 chip shows べんきょう |
| 3 | 勉強 → Dictionary Lookup | Title "Dictionary - Japanese → English"; `## [勉強]`, synonyms and examples with readings; Pronunciation in hiragana |
| 4 | `友達に手紙を書きました。` → Win+Alt+E → Dictionary → 手紙 | "letter", never "toilet paper" |
| 5 | `私は学生です。` → Win+Alt+E → Dictionary | No "Cannot detect language" dialog |
| 6 | `study` → Win+Alt+J → Dictionary → study | 勉強 annotated; synonyms 学習, 研究 annotated |
| 7 | `我们在学习中文。` → Win+Alt+E | No reading block, no chooser; Dictionary opens as Chinese |
| 8 | Main window: type `東京大学` | Reading pane: placeholder. Press Translate → とうきょうだいがく (when the model said Japanese) |
| 9 | Main window: type `大丈夫` → Dictionary without translating | "Kanji-only text: Japanese or Chinese?" with Japanese first |
| 10 | Win+Alt+S over Japanese text | The OCR'd Japanese with readings above the translation; History shows the OCR text |
| 11 | History | Japanese rows carry readings; clicking a reading loads the entry |
| 12 | Settings → Furigana OFF | No readings anywhere; History rows plain |
| 13 | Copy (button and Ctrl+C) from any annotated box | Plain text only |
| 14 | `logs/translator_YYYYMMDD.log` | `[LangID]` and `[Dictionary]` lines carry counts and language names, never the text |

---

## H1 — Health Review: the notice, the log, the vision strip — ✅ Done (2026-09-07) [on `main`, for 1.9.21]

**Goal:** answer "is the project in good shape?" with measurements rather than documents, and fix
whatever the measuring turned up. The suite, the tags, the release and the worker were all
healthy; three defects were not visible from the docs at all, because each one only shows itself
in the *shipped* app or in a state the tests never entered.

**Delivered:**

| # | What | Evidence it was real |
|---|------|----------------------|
| H1.1 | The "already running" notice no longer hangs the process | py-spy on a live hang: `wait_window` ← ttkbootstrap `Dialog.show()` ← `main.py:46`; a process resident since 2026-08-19, 19 days, no visible window |
| H1.2 | The frozen app logs to `%APPDATA%/CrossTrans/logs`, pruned after 14 days | six orphaned `_MEI*` directories (202 MB), each holding a `logs/translator_*.log` PyInstaller had been deleting on exit |
| H1.3 | `<think>` blocks stripped on the vision paths too | three callers (`app.py`, `screenshot_handler.py`, `pdf_ocr.py`) reached the API manager directly, past the only code that cleaned |

**The mechanism behind H1.1, which is the part worth keeping:** ttkbootstrap builds its dialog
with `transient=<the master>`, and **Tk withdraws a transient window whose master is withdrawn**.
`main.py` withdraws its root, so the dialog was never mapped and `show()` waited for a click on a
window that did not exist — invisible, unkillable except through Task Manager. The stdlib
messagebox is a native Windows dialog (class `#32770`) that a withdrawn owner cannot hide;
verified by enumerating window handles for both. A daemon watchdog calling `os._exit(0)` now
backs it, so no future dialog can strand that path either.

**Two general rules came out of it**, both now in CLAUDE.md → Known Issues: a withdrawn root
breaks *any* transient dialog, not only ones that call `grab_set()`; and the frozen app must
never derive a path from `__file__`, because under onefile it lands in the temp directory that is
deleted on exit.

**Tests:** 551 → 593. `test_single_instance_notice.py` (11, including an end-to-end test that
holds the lock port and asserts a second instance really terminates), `test_logging_setup.py`
(14), `test_vision_cleanup.py` (17). Each verified by reverting the production change: the
end-to-end test hangs 45 s and fails, the log-path revert fails 3, removing the pruning call
fails 1, unwrapping the two dispatch sites fails 5.

**Decisions:** 12 (native dialog + watchdog), 13 (`%APPDATA%` + retention, JSONL deferred),
14 (strip at the dispatch point, not at the callers). Findings left alone on purpose became
**D4–D10** in `DEFERRED.md`.

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
