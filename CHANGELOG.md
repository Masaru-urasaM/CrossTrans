# Changelog

All notable changes to CrossTrans are documented here.

## [Unreleased]

### History window, ruby selection, a way out of a failed popup (2026-09-02)

**Fixed**
- **Translation History works again.** Nothing was wrong with the stored history — the config
  file held its 100 entries throughout. The window was the problem, twice over:
  - It bound the mouse wheel with `bind_all("<MouseWheel>")` and undid that from a `<Destroy>`
    handler on its own toplevel. A child widget's bindtags include its toplevel, so destroying
    **one row** fired the handler: the first search keystroke, the first deleted entry, even
    clicking out of the search box (which restores the placeholder and rebuilds the list)
    unbound the wheel **from the entire application**. The dialog has no scrollbar, so from that
    moment the history could not be scrolled at all — and neither could anything else.
  - `bind_all` also meant that while History was open it took the wheel away from the popup, the
    dictionary window and the main window.
  The wheel is now bound per widget and re-bound on every row as the list is rebuilt.
- **History no longer locks the app.** It called `grab_set()`, which this project forbids
  outright (CLAUDE.md, Known Issues): a modal grab holds every other window hostage behind a
  dialog the user may not even have in front of them, and the Clear All confirmation is itself a
  Toplevel that has to take input while History is up. Replaced with the documented
  topmost + lift + focus_force + drop-topmost pattern.
- **Selecting Japanese now highlights the annotated words too.** Tk's `sel` tag draws straight
  past an embedded window, so dragging across a sentence highlighted everything *except* the
  words carrying a reading — holes exactly where the readings were, which read as "these words
  are not selected" right next to the bug that meant they were not copied either. The frames are
  painted with the widget's own selection colours, readings included (`#80b8ff` on the selection
  background is unreadable). A caller's own colour — the dictionary's per-word highlights — is
  recorded at insert time and restored on deselect.

**Added**
- **"Open Translator" on a failed quick translate**, next to API Settings. A failure is often
  not an API-key problem: the model refused, timed out, or returned nothing useful, and all of
  those are quicker to retry in the main window. It opens with the source text already in the
  input box and an **empty** output — the failure notice is not carried across. `is_error_text()`
  is now a single module-level predicate in `quick_translate.py`, used both by the popup to pick
  its button bar and by `app.py` to decide what crosses over, instead of the string test being
  spelled out twice.

**Not done — measured as impossible**
- Letting a reading that is wider than its kanji **overhang** into the space beside the word, so
  the word does not widen. A Tk `Frame` clips its children: a label wider than its frame is cut
  off, not drawn past the edge (measured — 51px label rendered at 40px). With the reading inside
  the frame that carries the word, its width is a floor on the word's width. Word gets its
  overhang from a layout engine that has no such containment. The alternatives are to spread the
  base characters across the extra width (Word's 均等割り付け — same width, no puddle of space
  around a centred word) or to shrink the reading's font, which cannot close a gap this size
  (べんきょう at 7pt is 47px against 30px of 勉強 — it would need ~4.5pt). Left alone pending a
  decision.

**Tests**: 476 → 510. New `tests/test_history_dialog.py` (13) drives the real dialog: the wheel
scrolls over the canvas and over a row, survives a search and a delete, leaves no
application-wide binding, takes no grab, and two dialogs can coexist. New
`tests/test_error_popup_actions.py` (14) covers the predicate, the error bar's contents and
order, and that a failure notice never reaches the main window's output box.
`TestSelectionHighlight` (7) in `tests/test_ruby_text.py`. Verified as regression tests: against
the previous `history_dialog.py`, 5 of the 13 fail with exactly the reported symptoms.

### Furigana reads like Word — copy, baseline, plate (2026-08-28)

**Fixed**
- **Copying selected text no longer drops the annotated words.** Selecting Japanese in any
  furigana surface and pressing Ctrl+C put only the unannotated characters on the clipboard:
  `これは日本語を勉強しています。` came out as `これはしています。` — 日本語 and 勉強 gone. Tk's
  own `<<Copy>>` exports the selected *characters*, and an embedded window has none. The Copy
  *buttons* were never affected; they already went through `get_plain()`. `RubyText` now handles
  `<<Copy>>` itself and copies the base text only — 日本語, never 日本語(にほんご) — which is
  what was asked for. Partial selections and single annotated words work the same way.
- **Base characters now share one baseline with the text around them.** `window_create`'s
  `align='baseline'` aligns the *bottom of the frame* with the line's baseline, so every word
  carrying a reading sat 6 px higher than the plain kana beside it (measured; all four `align`
  values were tried and none aligns baselines). The plain runs of a ruby-carrying line are now
  raised by the same amount, so the delta is 0 px.

**Changed**
- **The ruby plate is gone.** An annotated word takes the widget's own background instead of
  `#363636`, so it reads as ordinary text with a reading over it rather than a tinted chip —
  the way Word draws ruby. `FURIGANA_RUBY_BG` remains as the fallback and as an opt-in
  (`ruby_bg=`), and the dictionary word chips are unaffected: they carry their own colours.
- **`FURIGANA_RUBY_PAD_X` = 2 → 0.** An annotated word is now exactly as wide as its characters
  unless its reading is wider, so a line of mixed plain and annotated text keeps an even
  rhythm. Measured: frame width 45 px against 45 px of plain characters (was 49).
- **A line carrying ruby got shorter**: 47 px → 42 px. With the plain text lifted, nothing on
  that row hangs below the frame's baseline any more, so the row is the bare frame.
- Readings stay blue (`#80b8ff`) — the last open deferred item, D3, resolved by the user. See
  Decision 9. No code change; the colour the code always asked for was only ever hidden by the
  ttkbootstrap bug F2 fixed.

**Implementation notes**
- The lift is applied per *logical line*, only to lines that actually carry ruby. Lifting every
  plain line instead would have added ~5 px per row to the dictionary result window — most of
  the ~150 px the D1 fix had just removed.
- It is re-applied after every insertion: a Tk tag does not grow into text appended after its
  range, and the dictionary window builds each line one run at a time.
- The line's terminating newline is lifted with it. A newline is a character; left unlifted it
  keeps its full descent and hands 5 px of slack to the last row of the paragraph.
- `layout_rows()` gained a third row kind for plain rows that share a line with ruby, since
  those *are* taller. `RowCounts` and `LayoutModel` grew defaulted trailing fields, so existing
  callers and tests are unaffected.

**Tests**: 460 → 476. `TestCopySelection`, `TestBaselineAlignment` and `TestWordLikeRhythm` in
`tests/test_ruby_text.py`, plus a new `mapped_widget` fixture — the shared `tk_root` is
withdrawn, so embedded frames are never mapped there and report `winfo_y() == 0` forever;
anything measuring where a pair actually landed needs a real Toplevel. Verified as real
regression tests: with the lift and the copy handler disabled, 5 of them fail with exactly the
reported symptoms (33 vs 39 px, clipboard missing the annotated words).

### Deferred cleanup — D1 + D2 (2026-08-28)

**Fixed**
- **Dictionary result window no longer reserves a band of empty space.** `calculate_size()` sized
  it as if it were the quick-translate popup: Segoe UI 11 rows (20 px) against a window that
  renders `DICT_RESULT_FONT` (Consolas 10, 15 px rows), plus the popup's 100 px of chrome and a
  30 px "title bar compensation" on a window whose chrome is 71 px and whose title bar sits
  outside `geometry()` entirely. Measured on the real window: **139 px** of dead space under a
  12-line lookup and **199 px** under a 24-line one — the waste grew with the result, which is
  why `DEFERRED.md` recorded it as a flat "~154 px". Now **15 px** in every case, exactly the one
  spare row `calculate_size()` deliberately adds.
- Dead `Any` import in `src/core/translation.py` (D2), removed while its line was being touched
  for the first time since it was flagged.

**Changed**
- `QuickTranslateManager.calculate_size(text, base_font=('Segoe UI', 11), vertical_padding=100)`
  — the two things it had hard-coded are now parameters. The defaults are the popup's own values,
  so both existing callers are unchanged byte-for-byte (a test asserts the equality). A caller
  that renders in another font must now say so.
- New `DICT_RESULT_CHROME_PX = 71` next to `DICT_RESULT_FONT`. Both halves of
  `show_dictionary_result()` — the window height and the row count derived from it — subtract the
  same constant; a source-level test asserts they cannot drift apart again.

**Tests**: 450 → 458. New `TestWindowFitsItsContent` in `tests/test_dictionary_ruby.py`: the
empty band is non-negative (nothing clipped) and under three rows, for short/long results ×
furigana on/off; the band does not grow with the result; the popup default is untouched. Verified
as real regression tests — 6 of the 8 fail against the previous sizing code.

**Note on the fix's durability**: 71 px is measured on this machine's theme and DPI, like the 100
it replaces. If it under-estimates on another setup the box is slightly short rather than
over-tall, and `RubyText` binds the mouse wheel, so the text stays reachable — this window has no
scrollbar. An exact alternative (build the widget hidden, measure `ypixels`, then set the
geometry) was considered and rejected as too large a change for a cosmetic bug: it reorders window
creation and makes `overhead_px()` redundant at this call site.

## [1.9.19] - Furigana everywhere (2026-08-18)

Japanese text now shows **hiragana readings above its kanji on every surface that can display
it** — the quick-translate popup (both the source block and the translation), the main window,
the expanded view, a new Reading pane under the input box, the dictionary result window, and the
dictionary word chips and custom lookup tags. Detection is automatic; the toggle is
Settings → Hotkeys → "Enable Furigana".

Readings are generated **offline** — no API call, no extra latency, no quota. Accuracy comes from
fugashi/UniDic when the Japanese language pack is installed, and from the bundled pykakasi
otherwise. When a reading cannot be mapped onto its kanji with certainty it is **left blank
rather than guessed**: an absent reading is visibly absent, a wrong one is not.

Also in this release: the storage identity rename to CrossTrans (see its section below —
**it is a breaking change for existing installs**).

Built as eight phases, F0–F7, documented below.

> **Release history note** — 1.9.16 was the last version published to GitHub. **1.9.17 and 1.9.18
> were never publicly released**: they exist in this changelog and in the code, but no user ever
> received them. 1.9.19 is therefore the first public release since 1.9.16 and delivers all three
> versions' features at once, which is why its release notes cover Fix Grammar and Merged
> Translate-or-Fix as well as furigana. Do not assume a changelog entry here implies a shipped
> release.

**Release verification**: `CrossTrans_v1.9.19.exe` built from this tree (65,877,976 bytes) with
the new build guard confirming `pykakasi/data/kanwadict4.db` is present in the packaged archive —
the reading dictionary a fresh install depends on, and whose absence would have degraded furigana
to plain text without any error. Suite: 450 passed / 0 failed.

Published as tag `v1.9.19` on 2026-08-18 with the EXE attached. The auto-update endpoint was
checked against the live release rather than assumed: `tag_name` `v1.9.19` parses to `1.9.19` and
the `.exe` asset resolves, so 1.9.16 installs will be offered the update.

### Phase F7 — Furigana hardening (2026-08-17)

Final phase of "furigana everywhere". No new surface and no visible change — this one is about
the three ways the feature could degrade without anybody noticing: a startup stutter, a tuning
value that exists in two places, and an EXE that ships without the reading dictionary.

**Added**
- `src/constants.py` — a `FURIGANA` section holding every tuning knob: the two cost caps, the
  prewarm sample, the fonts and palette, and the Reading pane's debounce and row cap.
  `furigana.py`, `ruby_text.py` and `app.py` alias them to their existing local names, so no
  call site anywhere else changed.
- `tools/verify_furigana_bundle.py` — build guard. `--source` checks the environment can supply
  `kanwadict4.db` before PyInstaller runs; `--exe PATH` reads the built archive's own TOC (via
  `CArchiveReader`, not a byte search) to confirm it actually got in.
- `build_exe.bat` — runs both checks. A failed pre-flight **aborts** the build; a failed
  post-build check prints a "do not release it" warning as the last thing on screen.
- `tests/test_furigana_hardening.py` (28 tests), all mutation-checked — 21/21 mutations caught,
  including four planted in `build_exe.bat` itself.

**Changed**
- `furigana.prewarm()` now annotates a sample instead of probing availability, and `app.run()`
  actually calls it (on the existing background thread, gated on the Settings toggle).
- `FugashiProvider.tokens()` / `KakasiProvider.tokens()` serialize on the existing module lock.

**Fixed during implementation**
- **`prewarm()` was dead code** — defined in Phase F0, never called by anything. The whole
  dictionary load has been happening on the UI thread at the first Japanese render since then.
- **Probing availability would not have fixed it.** `active_provider_name()` stops at the first
  available provider, but `_refine_compounds()` calls pykakasi on *every* annotation even when
  fugashi is active — so the ~215 ms `kakasi()` construction stayed on the UI thread regardless.
  Measured over four fresh processes: first UI-thread annotation **217.7 ms → 0.6 ms**, with the
  cost moved to a background thread that finishes long before the user can press a hotkey.
- **Concurrent annotation was unsynchronized.** `annotate()` is reached from the UI thread at
  render time and from the translation worker via `generate_furigana()`; a MeCab tagger is not
  documented thread-safe, and prewarm added a third caller. The providers now serialize on the
  lock their constructors already used (~0.3 ms per tokenize, so no measurable cost).
- **`prewarm()`'s try/except was unreachable** — `annotate()` already swallows everything and
  falls back to plain text. Removed; the test now guards that contract instead.
- **`build_exe.bat` verified nothing.** A missing `kanwadict4.db` does not crash anything: the
  provider logs the `FileNotFoundError` and renders plain text, so an EXE with no furigana at
  all looks like a successful build. It is also the *only* provider a fresh install has —
  fugashi/UniDic arrives later, if the user installs the Japanese pack.
- **cmd.exe cannot parse a `::` comment as the last line of a parenthesised block** — it dies
  with "`)` was unexpected at this time" and the build never runs. Hit while writing this phase;
  there is now a test asserting no such line exists in the script.

**Tests**: 422 → 450 (+28). No regressions. Both build-script paths and the pre-flight abort
were run end-to-end against a real 94 MB EXE and a deliberately broken one.

### Phase F6 — Dictionary word chips and custom-box tags (2026-08-10)

Seventh phase of "furigana everywhere". The clickable word chips in Dictionary mode and the
orange tags in Custom lookup now carry readings. These are embedded widgets with their own
click, hover, selection and right-click-drag behaviour, so most of the work was keeping that
behaviour intact around a chip that is suddenly two rows tall.

**Added**
- `src/core/furigana.py` `annotate_tokens(tokens, text, lang_hint)` — readings for a
  tokenization, generated from the **whole line** and then handed to the tokens. Each token's
  segments concatenate back to that token (I1, per token).
- `src/ui/ruby_text.py` `RubyRow` — a standalone two-row ruby chip (grid: readings above, bases
  below) for surfaces that are not a `Text` widget. Used by the chips, the tags and both drag
  ghosts. `NO_AUTOSTYLE` is now public so every module uses the same ttkbootstrap workaround.
- `WordButtonFrame(..., furigana_enabled=)` and `CustomWordBoxesFrame(..., language=,
  furigana_enabled=)`; both dictionary-mode call sites pass the Settings toggle.
- `WordTag.set_dimmed()` — the drag-dim now covers the reading, which the caller poking at
  `tag.frame/label/close_btn` could not.
- `tests/test_word_chips_ruby.py` (36 tests) + `TestAnnotateTokens` in `tests/test_furigana_core.py`
  (11 tests). All mutation-checked, including the drag paths.

**Fixed during implementation**
- **A wrong reading on split compounds, found by measurement.** The dictionary tokenizer splits
  日本語 into 日本 + 語, and 日本 annotated on its own reads **にっぽん** where the compound is
  にほん. Per-chip annotation would therefore print a wrong reading on exactly the words a
  learner is looking up. Readings now come from the line, and a token that cuts through a
  reading is left bare — the chips for 日本 and 語 show nothing rather than something wrong.
  A plain run *is* clipped to the token (splitting text with no reading cannot make it wrong),
  which is what lets 会い keep 会[あ].
- **Chips were 7 px out of alignment** (measured): `window_create` defaults to `align='center'`,
  so a taller annotated chip lifted the plain chips off its baseline. Both the chips and the tags
  now insert with `align='baseline'`.
- **The custom box clipped its own tags.** `height=1` counts rows of the *base* font, and a tag
  with a reading is taller than one — the F1 height-unit bug again. The box now derives the row
  count from real font metrics, growing when a reading appears and shrinking when it goes.
- **The wheel was dead over every chip** (pre-existing): an embedded widget swallows
  `<MouseWheel>`, and chips cover nearly all of the word area, so a long text could not be
  scrolled at all. Bound on the area and on every chip part.
- **`_show_drop_line` could raise inside a live motion handler**: an unmapped box reports height
  1, making the geometry string `3x-3+...`, which is a `TclError`. Clamped.

**Design notes**
- A word with no reading keeps the **single-label chip it always had**, so non-Japanese
  Dictionary mode is unchanged.
- A tag is annotated **on its own**, unlike a chip: a tag is one lookup phrase the user typed or
  composed, and there is no larger context to read it in.
- Readings switch to white on the orange selection/highlight — `#80b8ff` on `#fd7e14` is
  unreadable.
- Ghosts are built from the same segments as the chip, never from a concatenated reading string:
  取り消し would otherwise preview as the nonsense とけ.

**Tests**: 376 → 422 passed / 0 failed (+46).

### Phase F5 — Dictionary result window (2026-08-10)

Sixth phase of "furigana everywhere". The dictionary result window now shows readings on the
Japanese it displays — the entry headers, definitions, synonyms and example sentences — while the
aligned label columns and the colour-coded lookup words are preserved exactly.

**Added**
- `src/ui/dictionary_render.py` — the render model for this window. `split_dictionary_text()`
  returns `DictRun(base, ruby, color)` items covering the text exactly once, so
  `''.join(run.base)` is the input string (the engine's I1 guarantee, extended to the renderer).
  Plus `field_policy()`, `source_language_hint()`, `runs_to_segments()`, `overhead_px()`.
- `tests/test_dictionary_ruby.py` — 45 tests (headless run model + the real window), every one
  mutation-checked.

**Changed**
- The result widget is a `RubyText` with `base_font=('Consolas', 10)` — monospace is load-bearing,
  `_align_dictionary_text()` aligns the value column with space padding. Verified: all 12 value
  columns still start at exactly the same pixel.
- Its manual `<MouseWheel>` binding is gone; `RubyText` binds the wheel itself, which also removes
  the dead zone over a ruby frame.
- `DICT_RESULT_FONT` replaces the three separate `('Consolas', 10)` literals.

**Fixed during implementation**
- **Word highlighting would have broken silently.** Colours were applied *after* insertion with
  `Text.search()`, and an annotated word contributes no characters, so every looked-up word would
  have lost its colour precisely where a reading appeared. Highlighting is now decided before
  insertion and travels on the run, so a word is coloured *and* annotated.
- **Highlight-first splitting destroyed the readings** (caught by a test, then by inspection): if
  the line is cut at the looked-up word before annotating, the tokenizer receives isolated
  fragments and an all-kanji fragment — which is exactly what a looked-up word usually is (勉強,
  東京) — cannot be annotated at all. The order is now annotate the whole line, then paint the
  colours onto the segments: plain runs split at colour boundaries, a ruby pair is coloured whole.

**Design notes**
- **Pronunciation (field 5) is never annotated.** It holds IPA plus a target-language phonetic
  (`/həˈloʊ/, /ハロー/`); hiragana above katakana is redundant and invites reading it as a
  different word. Matched by label *and* by number, because models renumber.
- **The result declares its own source language**, so `**Source Language**: Japanese` is used as
  the annotation hint for the source-language fields. This closes the kanji-only gap where it
  matters most: a dictionary lookup is usually a bare kanji word (犬, 東京, 勉強), which has no kana
  and is otherwise indistinguishable from Chinese. Resolved **per `## [Word]` entry**, since a
  multi-word lookup can mix source languages. An unrecognized value degrades to no hint.
- **Target-language fields** (Translation, Definition) use the target language as hint, so a
  kanji-only translation such as 犬 gets a reading too.

**Pre-existing, not changed** (reported, per Rule 3): the window has ~154 px of unused height
whether or not furigana is on, because `calculate_size()` measures with Segoe UI 11 while this
window renders Consolas 10 and adds a one-line buffer. The furigana budget itself is exact —
measured 51 px added against 51 px of real extra content.

**Tests**: 331 → 376 passed / 0 failed (+45).

### Phase F4 — Reading pane under the input box (2026-08-07)

Fifth phase of "furigana everywhere". The main window's **input box** now has a read-only
Reading pane beneath it that shows what you typed with hiragana above the kanji. The box itself
stays plain: an embedded ruby frame cannot survive `edit_undo()`, and a caret moving between
embedded windows behaves unpredictably, so the readings live in a separate widget instead of
inline (invariant I3 — editable implies plain).

**Added**
- `src/app.py` `_create_reading_pane()`, `_refresh_reading_pane()`, `_apply_reading_pane_state()`,
  `_toggle_reading_pane()`, `_on_input_modified()`, `_reading_pane_alive()`, plus the
  `READING_PANE_*` constants. The input box and its pane share one container frame, so the gap
  before the language selector is the same whether the pane is showing or collapsed.
- `config.py` `get/set_furigana_reading_pane()` (default `True`) — remembers a manual collapse.
  It is a collapse state, not a second feature switch: the pane exists whenever furigana is on.
- `tests/test_reading_pane.py` — 24 tests: construction, content rules, refresh wiring, the
  collapse toggle, and that the input box is never a `RubyText`.

**Changed**
- `src/ui/settings/hotkey_tab.py` — the Furigana toggle's description said "shows original
  Japanese text with furigana readings + translation", which described the old pipeline-only
  behaviour. It now names the surfaces the toggle actually governs.

**Design notes**
- **Always present, not shown-on-detection.** The pane's position never shifts and the feature is
  discoverable before any Japanese is typed. When there is nothing to annotate it shows a dim
  one-line placeholder rather than mirroring the box above, which would be noise — and would
  also mean re-inserting a pasted 50 000-character document on every edit.
- **One `<<Modified>>` binding, not per-call-site refreshes.** It fires for typing, paste,
  drag-and-drop, undo/redo *and* the programmatic rewrites in
  `_update_translation_with_original()` / `_load_history_item()`, so those call sites needed no
  changes (the plan had them patched individually). Tk only re-fires after the flag is cleared,
  and clearing it fires the event a second time; a 350 ms debounce collapses the pair into one
  render, which also keeps UI-thread annotation off the keystroke path.
- **No `lang_hint`.** The source language is unknown here, so kanji-only input stays plain rather
  than being guessed at — the same rule as the popup's source block.

**Verified empirically**: focus and caret stay in the input box across a refresh, `edit_undo()`
still works (and the pane follows the undo), and the pane's predicted height matches
`Text.count(..., 'ypixels')`.

**Tests**: 307 → 331 passed / 0 failed (+24). Each new test was mutation-checked: breaking the
annotation, the sizing, the `<<Modified>>` binding, the collapse persistence, the collapse state
or the placeholder all make the suite fail.

### Phase F3 — Main window and expanded view (2026-08-07)

Fourth phase of "furigana everywhere". The **main translator window's output box** and the
**expanded fullscreen view** now render furigana. The main window had never shown readings at
all — `translation_queue`'s only consumer routes to the popup — so "Open Translator" from an
annotated popup used to drop them silently. It no longer can: annotation happens where the text
is drawn, so anything that reaches the box is annotated.

**Added**
- `src/ui/ruby_text.py` `insert_output(widget, index, text, lang_hint, enabled, ...)` — the one
  place every surface routes result text through, so the Settings toggle behaves identically
  everywhere and no call site repeats the branch. `enabled` stays the caller's decision: only it
  knows whether the widget is showing a result, an error, or something about to be edited.
- `src/app.py` `_create_translation_box()` — extracted from `show_popup()` so the output box can
  be built and asserted on without starting the application (which registers global hotkeys,
  builds a tray icon and takes the single-instance lock).
- `tests/test_main_window_ruby.py` — 20 tests covering the main-window box, its update paths and
  the expanded window.

**Fixed during implementation**
- **Measurements ignored the widget's real line spacing.** `LayoutModel` hard-coded this
  module's own `spacing1 + spacing3`, but the popup and main-window boxes are built with
  spacing 0, so every logical line was mis-measured by 8 px. The model now reads the widget's
  actual values; a test asserts pixel-exact predictions for spacing 0, 6/2 and the popup's real
  configuration.
- **Copy and Expand from the main window would have handed over kanji-stripped text**
  (`app.py` `_copy_translation` / `_open_expanded_translation` read the box with `.get()`), as
  would the expanded window's own Copy button and its character counter. All now use
  `get_plain()`.

**Changed**
- The expanded view's text box is **read-only**. It was editable "for selection/copy", but a
  disabled `tk.Text` still supports mouse selection and Ctrl+C (verified empirically), so
  nothing is lost — and read-only is what lets it hold ruby without violating I3. Nothing
  consumed its edits. The now-pointless `<KeyRelease>` status refresh is gone with it.
- `ExpandedTranslationWindow.__init__` takes `config` so it can read the furigana toggle.
- `_update_translation_with_original()` and `_update_grammar_result()` replace their
  delete/insert pairs with `clear()` + `insert_output()`; `RubyText` restores the disabled state
  itself, so the manual state juggling is gone.

**Known limitation** (unchanged from F0): the *source* text still cannot be annotated when it is
kanji-only, because the source language is auto-detected and kanji-only strings are
indistinguishable from Chinese. Output text has no such problem — the target language is known.

**Tests**: 286 → 307 passed / 0 failed (+21).

### Phase F2 — Readings on the translation itself, not just the source (2026-08-06)

Third phase of "furigana everywhere". The Quick Translate popup's **output** box is now a
`RubyText`, so a Japanese translation carries readings — previously only the Japanese *source*
block did, which meant translating **into** Japanese (Win+Alt+J, the main use for a learner)
produced no readings at all. Screenshot/OCR, grammar-fix and merged translate-or-fix results
inherit this for free, because they all render through the same popup.

**Added**
- `src/ui/ruby_text.py`
  - `estimate_ruby_overhead_px()` — the extra pixels annotation needs beyond plain text, so a
    caller that already sized its window for plain text adds room instead of re-deriving the
    whole height with a different wrap model.
  - `set_plain()` — flatten a widget before handing it to the user for typing (I3).
  - `fit_height(min_rows=...)` — the popup measures **word** wrap while this class simulates
    **character** wrap, so its row count is a floor, not a replacement.
  - `insert_ruby(..., kanji_fg=...)` — base-character colour per insertion, for callers whose
    own tag carries a foreground (the replace preview's teal).
- `tests/test_popup_ruby.py` — 29 integration tests driving the real `show()`.

**Fixed during implementation**
- **Custom Prompt sent the model a kanji-stripped prompt.** `_handle_custom_prompt_send()` read
  the box with `.get()`, which returns nothing for an embedded ruby frame: measured **8 of 14
  characters** on a normal Japanese sentence. Now `get_plain()`. Entering edit mode also
  flattens the box first, per I3.
- **Phase 0's kanji-only gap is closed for output text.** `東京都` had no kana, so it was
  indistinguishable from Chinese and stayed plain. The popup knows the *target* language, which
  is authoritative for a translation, so kanji-only Japanese output annotates again — while a
  kanji-only result with a Chinese target still, correctly, does not.
- **ttkbootstrap was discarding the ruby colours.** It re-themes standard `tk` widgets at
  construction and drops explicit colour kwargs unless `autostyle=False` (measured: a
  `tk.Label` asked for `fg='#80b8ff'` comes back `#ffffff`, `bg='#363636'` comes back
  `#222222`). So the blue reading colour that has been in the code and the docs all along
  **never actually shipped** — readings rendered white. This predates this work; the old
  renderer had the same problem. ⚠️ **Visible change**: readings are now blue (`#80b8ff`) on a
  `#363636` plate. The `RubyText` widget itself deliberately stays themed so it keeps matching
  the frame around it. (This also means the "pixel-identical" screenshot in Phase F1 was taken
  under plain Tk, where colours are not overridden: the geometry parity it proved holds, the
  colours in it were the intended ones rather than the shipped ones.)
- **`config.get_furigana_enabled()` fell back to `False`** while `DEFAULT_CONFIG` documents
  `True`, so any config file written before the key existed had the feature silently off. Was
  scheduled for F4; fixed here because it gates everything this phase adds.
- **Error text was annotated but not budgeted for.** The height calculation excluded error
  messages while the insertion did not, so a provider error containing Japanese could overflow
  the box. Found by a test written for this phase.

**Changed**
- The Settings → Hotkeys "Enable Furigana" toggle now governs **render-time annotation**, not
  just whether the pipeline generates a notation string. One switch, every surface.
- Replace preview: the translated half is annotated in the matching teal; the struck-through
  original stays plain, because Tk cannot strike through an embedded frame and the text is
  being discarded anyway.

**Verified**
- Screenshots of the popup and the replace preview; ruby label colours asserted numerically
  (base and reading foreground per frame), not judged by eye.
- Audited every read of a ruby-capable widget: no `.get()` remains (I2). Copy and Replace take
  `app.current_translated`, a plain string, so they were never affected.

**Tests**: 257 → 286 passed / 0 failed (+29).

### Phase F1 — RubyText primitive: one renderer, correct sizing (2026-08-05)

Second phase of "furigana everywhere". The ruby drawing code moves out of the Quick Translate
popup into a reusable widget, so the later phases add surfaces instead of copying a renderer.
**The popup renders pixel-for-pixel identically** (verified with a side-by-side screenshot of
the old and new renderers) — every change below is either a bug fix or new capability.

**Added**
- **`src/ui/ruby_text.py`** — `RubyText`, a `tk.Text` subclass that owns ruby rendering.
  - `insert_ruby(index, text, lang_hint)` annotates on the way in; `insert_notation()` consumes
    the legacy `{kanji|reading}` string; `insert_plain()` skips annotation. All three work while
    the widget is `state='disabled'`, so read-only surfaces need no state juggling.
  - **`get_plain()`** — the readback that Copy / Replace / re-send paths need. `Text.get()`
    contributes **zero characters** for an embedded window while still consuming one index, so
    reading an annotated widget with `get()` silently deletes every annotated word. Measured on
    the popup's own sample: `get()` returns 8 of 14 characters, `get_plain()` all 14.
  - `LayoutModel` / `layout_rows()` / `measure_px()` — a `wrap='char'` simulation that predicts
    the pixel height of annotated content. Row heights are **derived from font metrics**, not
    guessed: `frame = ruby linespace + base linespace + 2·pad`, `ruby row = frame + base
    descent`, plus `spacing1 + spacing3` once per logical line. Predictions match
    `Text.count(..., 'ypixels')` **exactly** on every case tested (47 / 86 / 122 / 28 px).
  - `estimate_notation_px()` — lets a caller size its window *before* creating the widget,
    which the popup must do because an `overrideredirect` Toplevel gets its geometry once.
  - `MAX_ANNOTATE_CHARS` (3000) — above this, text is inserted plain. Annotation and frame
    construction run on the UI thread, so a pasted document cannot freeze it.
- **`tests/test_ruby_text.py`** — 49 tests. The wrap arithmetic runs headless through an
  injected `LayoutModel`; the widget tests use a new session-scoped `tk_root` fixture in
  `tests/conftest.py` that skips itself when no display is available.

**Fixed during implementation**
- **Insertion order was reversed** (found by a render probe, not by reading the code): feeding
  runs one at a time to a fixed index put each run *before* the previous one, so
  `私は日本語を勉強しています。` rendered as `しています。勉強を日本語は私`. Insertion now walks
  a right-gravity mark. This bug did not exist in the old renderer (it always appended to
  `END`) — it was introduced and killed inside this phase, and is now covered by two tests.
- **Height unit bug — multi-line ruby was clipped.** The `height` option counts rows of the
  *base* font (28 px measured), but a row carrying ruby is 47 px. The old renderer asked for
  one unit per logical line, so it under-allocated 19 px for every annotated row: fine for one
  line, clipped from the second onwards. Height is now converted from the real pixel
  requirement.
- **Popup height estimate replaced.** `paragraphs * 38 + 30` ignored wrapping entirely; a
  Japanese paragraph that wraps to two ruby rows was budgeted 68 px and needed 103 px. The
  estimate now measures at the actual wrap width.
- **Scroll dead zone over ruby.** An embedded frame swallows `<MouseWheel>`, so the wheel did
  nothing precisely where the annotated text is. Measured: over a ruby label the old renderer
  leaves `yview` at `0.0000`, `RubyText` scrolls to `0.1615`. Every frame and label created is
  now bound to the same handler.
- **Text containing `{`, `|` or `\` lost all its readings.** `generate_notation()` suppressed
  ruby for those strings because the old regex renderer would have turned a literal `{A|B}`
  into a fake pair. `RubyText` parses through `parse_notation()`, which honors the escapes, so
  the guard is gone: `設定{A|B}テストを保存` now shows readings and reads back byte-identical.
- Dead `<Shift-MouseWheel>` binding removed — `wrap='char'` has no horizontal view, so
  `xview_scroll` could never do anything.
- `ROADMAP.md` and the Phase 0 entry said "124 → 204 tests"; the real Phase 0 total was **208**.

**Changed**
- `src/ui/quick_translate.py` — `_render_furigana()` is now a five-line delegate and takes the
  wrap width. `HORIZONTAL_PADDING` moved to module scope so `calculate_size()` and the furigana
  estimate cannot drift apart; added `FURIGANA_SEPARATOR_PX`. New `popup_furigana` attribute
  (reset in `close()`) exposes the widget to the later phases.

**Verified**
- Visual parity: old and new renderers drawn in one window and screenshotted — identical
  glyph positions, colours, plate backgrounds and baselines.
- `get_plain()` round-trips text holding `{`, `|` and `\` through the real popup path.
- No circular imports: `src.ui.ruby_text` pulls in `src.core.furigana` only.

**Tests**: 208 → 257 passed / 0 failed (+49). One Phase 0 test was rewritten
(`test_generate_notation_suppresses_text_holding_delimiters` →
`test_generate_notation_escapes_delimiters_in_the_source`) because the behaviour it pinned was
the guard removed above.

### Phase 0 — Furigana engine: structured segments, accurate readings (2026-08-04)

First phase of "furigana everywhere". **Pure logic only — no UI file was touched**, so the
Quick Translate popup looks and behaves exactly as before except that its readings are now
correct. Groundwork for rendering ruby on every surface in later phases.

**Added**
- **`src/core/furigana.py`** — the furigana engine.
  - `RubySegment(base, ruby)` — a structured segment model replacing the fragile
    `{kanji|reading}` string as the internal contract.
  - **Invariant I1**: `''.join(seg.base for seg in annotate(text)) == text`, asserted at
    runtime and in tests. Annotation can no longer alter the text it describes.
  - `should_annotate(text, lang_hint)` — requires kanji **plus** kana evidence, or an
    explicit language hint. Chinese hanzi no longer qualifies for Japanese readings, while
    kanji-only Japanese (`東京都`, `電源設定`) still annotates when the caller passes a hint.
  - `align(surface, reading)` — maps a whole-token reading onto the kanji runs inside it by
    anchoring on the kana already present. **Fail-safe**: returns `None` rather than guess,
    so no wrong reading is ever drawn.
  - Provider chain `FugashiProvider` → `KakasiProvider`, each built **once** and reused.
  - `_refine_compounds()` — restores whole-compound readings that morphological splitting
    destroys, restricted to all-kanji spans.
  - `to_notation()` / `parse_notation()` with backslash escaping for `\ { } |`.
- **`tests/test_furigana_core.py`** — 80 tests: detection matrix, aligner (incl. every
  fail-safe branch), I1 over a 19-case corpus, notation escaping round-trip, whitespace
  preservation, the pair cap, and the reading-quality regressions below.

**Fixed**
- **Okurigana covered by ruby** — `取り消し` produced `{取り消|とりけ}し`, the ruby spanning
  the り, because the old code stripped only a *trailing* kana suffix. Now
  `{取|と}り{消|け}し`. Same class fixed for `話し合い`, `申し込み`, `生き物`.
- **Wrong homograph readings** — `今日は雨` gave こんにち; now きょう (morphological context).
- **`kakasi()` rebuilt on every call** — measured ~175 ms to construct versus ~0.3 ms to
  convert. Now a lock-guarded singleton, plus a 256-entry `lru_cache` on annotation.
- **Notation injection** — source text containing a literal `{a|b}` was parsed back as a
  real ruby pair and rendered as "a" with the reading "b". The segment model makes this
  structurally impossible; until the renderer consumes segments (Phase 1), the legacy wire
  format additionally suppresses ruby for any text holding `\ { } |`.
- **Multi-line text lost all ruby** — tokenizers normalize whitespace away, which broke the
  round-trip check. Annotation now runs on whitespace-free chunks and re-inserts separators
  verbatim, so newlines, CRLF, tabs and blank lines survive.
- **Misleading counter readings** — `2日` is *futsuka*: the digit carries part of the reading
  and cannot take ruby, so drawing カ over 日 alone invited "ni-ka". Counters following a
  digit are now suppressed, which also removes real errors (`2人` is *futari*, not ni-**nin**;
  standalone `1月` reported ツキ instead of ガツ).
- **Compound readings broken by splitting** — UniDic tags 日本 as a proper noun reading
  ニッポン, so `日本語` came out にっぽんご and `日本人` にっぽんにん. Both correct now, and
  `東京駅` → とうきょうえき, `中国語` → ちゅうごくご.
- **Chinese text was given Japanese readings** — the pipeline gate matches U+4E00-U+9FFF, so
  hanzi qualified. `你好世界` produced `{你|}{世界|せかい}` — note the **empty** reading on 你,
  which would have rendered a blank ruby label. Both are gone.
- **Misleading log message** — the old `"pykakasi not installed"` warning did not fire when
  the package imported but its bundled dictionary data was missing, which is the likely
  packaging regression. Provider failures now log the actual exception.

**⚠️ One behaviour change: kanji-only source text no longer gets furigana from the hotkey path.**
Ruby now requires kanji **plus** kana evidence, or an explicit language hint. A sentence
(`今日は雨が降る`) is unaffected — it has kana. But a kanji-only selection (`電源設定`, `東京都`,
`翻訳`) used to be annotated and now is not, because the pipeline calls
`generate_furigana(selected_text)` with no hint and **cannot tell Japanese kanji from Chinese
hanzi**: the same permissive check that annotated `東京都` is what annotated `你好世界`.
This is the deliberate "blank beats a wrong reading" trade — a lost reading is visibly absent,
whereas a wrong one is unfalsifiable at the point of use. Phase 2 closes the gap by threading
the real source language from the surfaces that already know it (the popup, and the dictionary's
`_open_with_language`), at which point kanji-only Japanese annotates again *without* also
re-annotating Chinese.

**Changed**
- `src/core/translation.py` — `_is_japanese_text()` and `generate_furigana()` are now
  two-line delegates onto the new module. `generate_furigana()` gained an optional
  `lang_hint`. The queue tuple shapes are **unchanged** (arity is the discriminator in
  `app.py:_check_queue`, so extending it positionally would abort the drain loop).

**Verified**
- Packaging: `collect_data_files('pykakasi')` at `CrossTrans.spec:15` is load-bearing and
  sufficient — proven with two minimal one-file probe EXEs (with data: readings work in the
  frozen EXE; without: `FileNotFoundError` on `kanwadict4.db`, swallowed into a silent
  no-furigana state). No new packaging risk from this phase.

**Tests**: 124 → 208 passed / 0 failed. No regressions; the pre-existing tuple-shape
assertions in `test_translate_or_fix.py`, `test_fix_grammar.py` and `test_freeform_prompt.py`
all still hold.

### Storage identity renamed to CrossTrans (2026-07-01)

The app's internal **storage identity** — the `%APPDATA%` config folder, the model-config cache folder, the Windows auto-start registry value, and the DPAPI encryption entropy/description — was renamed from the legacy product name to **`CrossTrans`**, matching the user-facing name already in `src/constants.py`. A fresh install now uses `%APPDATA%\CrossTrans\` throughout.

### ⚠️ Breaking change (existing installs)
- **Saved API keys must be re-entered.** Keys are DPAPI-encrypted with an app-specific entropy that changed as part of the rename, so keys stored by an older build can no longer be decrypted and are cleared on load.
- **Settings/history do not carry over.** The new build reads `%APPDATA%\CrossTrans\config.json`; the old build's folder is no longer consulted.
- The old `%APPDATA%` config folder is a harmless leftover — delete it manually if you want the disk space back.
- **Auto-start needs a one-time manual cleanup for anyone who had it enabled.** The old auto-start registry entry (under the previous name) still launches the app, but the Settings toggle now manages the `CrossTrans` entry only — so the toggle reads **OFF** and cannot remove the old entry. To actually stop auto-start, disable it via **Task Manager → Startup apps**, or delete the stale value under `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` once. (On a manual reinstall the stale entry may still point at the *old* exe, so the previous version could keep launching — masked by the single-instance lock — until removed.)
- **No automatic migration was implemented — deliberately**, to keep the rename total (no trace of the old name remains in the project) per explicit request. A migration (old-folder copy + key re-encryption) is a clean future option, but cannot coexist with a "no old-name anywhere" requirement.

### Changed
- `config.py` — `APP_NAME` is now `"CrossTrans"` (drives the config dir and the auto-start registry value name); docstring updated.
- `src/core/crypto.py` — `SecureStorage.ENTROPY` (the DPAPI salt) and `DESCRIPTION` (cosmetic) now use the `CrossTrans` identity.
- `src/core/remote_config.py` — model-config `CACHE_DIR` is now `%APPDATA%\CrossTrans\`.
- `src/utils/updates.py` — the auto-updater batch script now reads/writes the `CrossTrans` auto-start registry value.
- Docs — `CLAUDE.md`, `.github/copilot-instructions.md`, and `OPS_GUIDE.md` path/registry references updated; removed a stale deprecated `.spec` entry from `.gitignore` (the real, tracked build spec is `CrossTrans.spec`).

**Tests**: 124 passed / 0 failed — no regressions. Verified a full-repo case-insensitive search for the old name returns **zero** matches (excluding `.git`).

## [1.9.18] - Merged Translate-or-Fix on the language hotkeys (2026-07-01)

Pressing a **language hotkey** (Win+Alt+V/E/J/C — and any custom language hotkey) on text that is **already in that hotkey's target language** now **fixes its grammar in place** instead of pointlessly "translating" it. One merged AI prompt lets the model auto-decide translate-vs-fix. This makes grammar-fixing reachable without a dedicated hotkey — sidestepping the Xbox Game Bar (`Win+Alt+G`) and Feedback Hub (`Win+Alt+F`) collisions entirely.

### Added
- **`TranslationService.translate_or_fix(text, target_language, skip_cache=False)`** — Sends ONE merged prompt: if the text is already in `target_language` the model corrects only grammar/spelling/punctuation (minimal changes, same language); otherwise it translates. BOTH branches are uncensored and meaning-preserving (offensive words survive — faithful equivalent when translating, verbatim when fixing). Cached/stored under `source_type='merged'`.
- **`TranslationService.do_translate_or_fix(target_language)`** — Language-hotkey orchestrator (mirrors `do_translation`): captures the selection, shares the `last_translation_time` cooldown, generates furigana for Japanese source, queues the same 5-tuple as a translation (`is_grammar=False` — the output is a real language in both branches).
- **Merged cache namespace** — `HistoryManager.find_cached(original, target_lang, source_type='text')` gained a `source_type` param; the merged path reads/writes under `'merged'` so a minimal-change fix is never cross-served as a plain 'rephrase' translation (and vice versa).
- **Config**: `fix_grammar_hotkey_enabled` (default **False**) with `get/set_fix_grammar_hotkey_enabled` — a separate flag registering the global `Win+Alt+G` hotkey.

### Changed
- **`app._on_hotkey_translate()`** — The normal language branch now calls `do_translate_or_fix(language)` instead of `do_translation(language)`. Covers every language hotkey (defaults + custom) since this branch handles all non-special `language` values.
- **No-censor everywhere** — The no-censor rule was added to the plain `translate_text` prompts (both variants) and the screenshot/OCR vision prompt, per user request, so offensive words survive all translations (not just the merged path).
- **`Win+Alt+G` hotkey now OFF by default** — split from the button: `fix_grammar_enabled` (default True) controls only the main-window **button**; the new `fix_grammar_hotkey_enabled` (default **False**) gates the global hotkey registration + tray hint. `hotkey.py`, `tray.py`, `app.py` guard, and the Settings → Hotkeys section (new "Enable global Win+Alt+G hotkey" checkbox) updated accordingly. The button and the merged language-hotkey behavior always work.

### Notes
- **Uncensored output is best-effort and model-dependent** — the prompt can only *request* it; some of the 15 providers/180+ models and the trial proxy enforce hard content filters that may still refuse/mask. Additionally, adding an explicit no-censor instruction to *all* translations can itself increase refusals on some models for otherwise-benign text (accepted tradeoff). Confirm behavior against the configured model.
- **LEAN display consequences** (documented, not blockers): the popup shows the language (not "Grammar") for a same-language fix, and the popup **Re-translate** button re-runs the plain `translate_text` (rephrase), not the merged prompt.

**Tests**: +24 (`tests/test_translate_or_fix.py`) covering the merged prompt content (tie-break + both-branch no-censor + verbatim token via a neutral placeholder, never a real slur), `'merged'` cache namespace isolation (no cross-serve), `do_translate_or_fix` routing/tuple/cooldown/trial/no-selection/history, and no-censor presence in the plain prompts; +2 wiring guards (`tests/test_callback_wiring.py`); updated `tests/test_fix_grammar.py` for the split hotkey flag. Suite: **100 → 124 passed / 0 failed** (0 regressions).

## [1.9.17] - Fix Grammar (2026-06-30)

A new **Fix Grammar** action that corrects the grammar of selected text *in place* — no translation, no rephrasing, no censoring. The output is always the same text in the same language with only grammar/spelling/punctuation fixed.

### Added
- **Fix Grammar hotkey** (default **Win+Alt+G**) — Select text anywhere, press the hotkey, and a popup shows the grammar-corrected text with **Copy** / **Replace** to apply it back into the source app. ⚠️ `Win+Alt+G` is also Xbox Game Bar's "Record that" default; registration fails gracefully (error 1409) if Game Bar holds it, the hotkey is fully rebindable, and the button always works. `Win+Alt+F` is the recommended conflict-free alternative.
- **"Fix Grammar" button** in the main translate window (next to Translate) — Corrects the input box text and writes the result into the output box.
- **Settings → Hotkeys → Fix Grammar section** — "Enable Fix Grammar" toggle (default **ON**) + rebindable hotkey row (mirrors the Screenshot hotkey row), with duplicate-hotkey validation.
- **Tray menu entry** — `Win+Alt+G → Fix Grammar` listed with the other hotkeys (shown only when the feature is enabled).
- **`TranslationService.fix_grammar(text)`** — Builds a strict correction prompt (fix grammar/spelling/punctuation only; never translate, paraphrase, change meaning/tone, or censor — including offensive words; return unchanged if already correct), calls the API, strips thinking tags. Not written to history.
- **`TranslationService.do_grammar_fix()`** — Hotkey entry point: captures the live selection (Ctrl+C), honors a dedicated cooldown (`last_grammar_fix_time`), surfaces trial info, and queues a 6-tuple `(original, corrected, "Grammar", trial_info, None, True)`.
- **Config**: `FIX_GRAMMAR_HOTKEY_DEFAULT="win+alt+g"`, `fix_grammar_hotkey` + `fix_grammar_enabled` (default `True`) in `DEFAULT_CONFIG`, with `get/set_fix_grammar_hotkey` and `get/set_fix_grammar_enabled`.

### Changed
- **`HotkeyManager.register_hotkeys()`** — Registers a `__fix_grammar__` hotkey (gated by `fix_grammar_enabled`, so disabling frees the combo); fails gracefully on conflict like the other hotkeys.
- **`app._on_hotkey_translate()`** — Added a guarded `__fix_grammar__` dispatch branch (additive; the translation path is untouched). Source-window HWND is captured first so Replace works.
- **Quick Translate popup** — `show(..., is_grammar=False)` hides the translation-only buttons (Re-translate, Dictionary, Custom Prompt) for grammar results, keeping Copy / Replace / Open Translator. `show_loading(..., loading_text=...)` shows "Fixing grammar…" instead of "Translating to …".
- **`_check_queue()`** — Now also handles the 6-tuple grammar result and routes it with `is_grammar=True` (4- and 5-tuple translation paths unchanged).

### Notes
- **No prompt fully guarantees uncensored output across all 15 providers/180+ models** — some have hard content filters that may refuse or soften sensitive input (the trial proxy may too). The prompt is engineered to preserve text verbatim; behavior should be confirmed against the actually-configured model.

**Tests**: +13 (`tests/test_fix_grammar.py`) — `fix_grammar` prompt content (never-translate / no-censor / same-language / verbatim token preservation) + empty guard + thinking-tag strip; `do_grammar_fix` 6-tuple/`is_grammar` flag + cooldown + error path + no-history; config defaults/fallbacks; hotkey registration wiring. Suite: **87 → 100 passed / 0 failed** (0 regressions).

## [1.9.16] - Translation Cache, Re-translate & Custom Prompt

### R1 — Translation Cache + Re-translate Button
- **History-backed translation cache** — Identical source text with the same target language is served from the existing 100-entry history instead of calling the AI API again (saves quota/cost/latency, consistent output). Applies to plain translations only; custom-prompt requests are never cached.
- **`HistoryManager.find_cached(original, target_lang)`** — Exact-match lookup, most-recent-wins, skips `"Error:"` results
- **`translate_text(..., skip_cache=False)`** — Cache lookup before the API call; early return on hit without re-adding to history (no duplicate entries)
- **"Re-translate" button** (orange) in the Quick Translate popup — Forces a fresh API call (`skip_cache=True`), bypassing the cache so a bad/garbled result is never stuck. Runs off the UI thread (no Tk freeze); no cooldown, no clipboard re-capture
- **`TranslationService.redo_translation(text, target_lang)`** — Forced-refresh path that reuses already-known text and pushes a fresh result to the translation queue
- **Cache-poisoning guard** — `find_cached` only serves `source_type == 'text'` entries, and custom-prompt translations are stored as `source_type == 'custom'`. Prevents a main-window custom-prompt result (or a screenshot/multimodal entry) from being served as a plain-translation cache hit — honors the "custom prompts are never written as a cache match" decision while keeping them visible in the history viewer
- **Decision:** the optional cache on/off toggle from the roadmap was intentionally omitted — the Re-translate button is the escape hatch; cache is also implicitly inert when history is disabled
- **Tests**: +13 (`tests/test_translation_cache.py`) — `find_cached` semantics + `translate_text` hit/miss/skip_cache/custom-prompt-bypass

### R2 — Custom Prompt in Quick Translate Popup
- **"Custom Prompt" button** (teal) in the popup — Makes the translation box editable (keeping the current translation as a starting point) and swaps the button bar to [Send] [Cancel]. The user edits freely and the entire box content is sent verbatim as the prompt, so besides translating they can quickly ask the AI anything about the text
- **`TranslationService.ask_freeform(raw_prompt, target_lang)`** — Raw path that sends the prompt verbatim (no translate wrapper); result pushed to the queue and rendered as a normal popup. Freeform asks are one-offs: never written to history and never served from / written to the R1 cache
- **Edit-mode focus** — Temporarily clears `WS_EX_NOACTIVATE` and force-focuses the box so typing works despite the no-activate popup style; restored to normal on the result popup
- **Single wide button bar** — Popup minimum width widened (560→670px) so all 7 actions + close fit in one row (developer-selected layout)
- **R2-bug fix** — `translate_text()` custom_prompt branch now embeds the source text via `===TEXT TO TRANSLATE===` delimiters. Previously the source text was omitted, so the main-window "additional instructions" feature sent instructions to the API with nothing to translate
- **Tests**: +7 (`tests/test_freeform_prompt.py`) — custom_prompt embeds source text + bypasses cache; `ask_freeform` verbatim/no-history/queue/empty/strip-thinking

### Test suite repair & wiring guard
- **Fixed 20 outdated `test_api_manager.py` tests** — Provider identification now returns Title-Case names (`'Google'`, `'OpenAI'`, …); the 15 provider-id assertions were updated from the old lowercase contract. The 5 Google tests were rewritten from the removed `genai` SDK to the current Gemini REST path (mock `urllib.request.urlopen`)
- **Added `tests/test_callback_wiring.py`** (+5) — Static integration guard that the popup callback signature, the app handlers, and the service methods stay name-consistent (catches wiring typos unit tests miss)
- **Suite: 39 passed / 20 failed → 84 passed / 0 failed** (+25 new tests, 20 repaired, 0 regressions)

## [1.9.15] - Dictionary Improvements & NLP Install Hardening

### Custom Word Boxes Improvements
- **Smart CJK joining** — Custom box tags join without space for CJK characters (`[無礼][講]` → `"無礼講"`), with space for Latin (`[ice][cream]` → `"ice cream"`)
- **Right-click drag reorder** — Drag tags within/between custom boxes to reorder (move semantics, not copy)
- **Drag visual feedback** — Ghost label follows cursor, source tag dims, cyan drop line shows exact insertion point
- **Precise word insertion** — Dragging words from tokenized area inserts at cursor position, not end of box
- **Text selection fix** — Left-click text selection now works properly in custom boxes
- **Surrogate character filter** — Tkinter embedded window placeholders no longer leak into lookup text

### NLP Install Graceful Degradation
- **No more scary errors** — Whitespace-separated languages (Vietnamese, European) gracefully fall back to basic tokenization instead of showing error dialog
- **Basic mode indicator** — UI shows info-blue "ℹ Installed with basic tokenization" for basic-mode languages
- **`whitespace_separated` field** — `LanguagePack` now tracks whether simple tokenize gives usable Dictionary results
- **`nlp_basic_mode` config** — Persists basic tokenization state across sessions

### Auto-Retry NLP Install
- **Multi-Python discovery** — When post-install verification fails, discovers all Python interpreters via `py -0p` and common install paths
- **Automatic retry** — Cleans custom packages dir and retries pip install with each discovered Python
- **Cached Python path** — Successful Python interpreter path cached in config for future installs

## [1.9.14] - Custom Word Boxes & NLP Install Fix

### Custom Word Boxes
- **Manual phrase composition** — New input boxes in Dictionary popup for composing custom lookup phrases when NLP tokenization doesn't detect the desired word/phrase
- **Typed text to tags** — Type text and press Enter to convert into orange tags (same visual as selected dictionary words)
- **Right-click drag from word area** — Drag tokenized words into custom boxes
- **Dynamic boxes** — Add (+) / remove (-) boxes, up to 5 per lookup
- **Combined lookup** — "Dictionary Lookup" button combines selected words from word area + all box content

### NLP Language Pack Install Fix
- **Post-install verification** — `install()` now verifies packages are actually importable after pip succeeds, instead of trusting pip exit code
- **EXE subprocess fallback** — When bundled Python can't import C extensions (version mismatch), falls back to subprocess tokenization via system Python
- **C extension detection** — `is_installed()` detects `.pyd`/`.so` files in custom packages directory
- **Module cache clearing** — Clears parent modules from `sys.modules` for dotted names (e.g., `ufal.udpipe`) to prevent stale cache

## [1.9.13] - Furigana Reading Guides for Japanese

### Furigana Feature
- **Japanese reading guides** — When translating Japanese text, original text is displayed with furigana (hiragana readings above kanji) to help learn pronunciation
- **Offline generation** — Uses pykakasi library for local kanji-to-hiragana conversion (no extra API call)
- **Embedded frame rendering** — Each kanji+reading pair is an inline frame with `align='baseline'` for perfect vertical alignment with surrounding text
- **Word wrap support** — Long furigana lines wrap naturally using `wrap=tk.CHAR` (CJK-friendly)
- **Toggle in Settings** — Enable/disable in Settings → Hotkeys → "Enable Furigana" checkbox
- **Config key**: `furigana_enabled` (boolean, default `True`)

### Dev Runner
- **`dev_run.bat`** — Development script that kills running CrossTrans instance and restarts with console output for debugging
- Uses PowerShell `Get-CimInstance` to find and kill python processes by command line match

## [1.9.12] - Rename & Documentation Overhaul

### Codebase Rename: Tooltip → Quick Translate
- **Renamed `tooltip.py` → `quick_translate.py`** — Feature now consistently called "Quick Translate" everywhere
- **`TooltipManager` → `QuickTranslateManager`** — Class, variables, methods, callbacks all renamed
- **User-facing text** — All UI strings now say "popup" instead of "tooltip"
- **Documentation updated** — README, CHANGELOG, CLAUDE.md, copilot instructions all consistent

### README Overhaul
- **"Translate Anywhere" highlighted as core advantage** — Works in any app, no plugin needed
- **Two translation methods explained** — Text selection + hotkey, or screenshot OCR for non-selectable text
- **Cross-platform workflow focus** — Browsers, IDEs, chat apps, games, images, videos
- **All screenshots added** — 10 screenshots now included in the repository

### Guide Tab Improvements
- **Hotkeys section moved to top** — First thing users see after Getting Started
- **Hotkey intro line added** — Explains that hotkeys activate Quick Translate

## [1.9.11] - Public Release Hardening

- **Cleaned .gitignore** — Ensured no sensitive or dev-only files leak into the repository
- **Standardized API Settings buttons** — All error dialogs now consistently show "Open API Key Settings" button that navigates directly to Settings > API Key tab
- **Fixed trial dialogs bug** — "Open Settings" button in Trial Exhausted and Trial Feature dialogs now renders correctly
- **DPI awareness** — App respects system scaling on high-DPI displays
- **SmartScreen documentation** — Added first-run guidance for unsigned EXE

## [1.9.10] - Replace in Source App & Dictionary Improvements

### Replace in Source App
- **Replace button** — One-click replace selected text with translation directly in the source app
- **Manual Replace mode** (default) — Preview with strikethrough original and translated text, then Agree/Cancel
- **Quick Replace mode** — Immediate paste without preview for faster workflow
- **Gear icon (⚙)** — Dropdown menu next to Replace button for quick access to settings
- **Replace Mode toggle** — Configurable in Settings → Hotkeys → Replace Mode section
- **WS_EX_NOACTIVATE popup** — Popup doesn't steal focus from source app, keeping text selection alive

### Dictionary Mode Improvements
- **Synonyms & Antonyms** — Dictionary now shows synonyms and antonyms with translations (8-field output)
- **Smart word filtering** — Punctuation, symbols, and pure numbers no longer appear as clickable word buttons
- **Unicode letter detection** — Filter works across all languages (Latin, CJK, Cyrillic, Arabic, Thai, Korean)
- **Dedicated mode only** — Dictionary lookup only through the Dictionary button, no auto-detection on short text

### Generic API Guidance
- Removed provider-specific API key links and pricing from all UI dialogs
- Guide tab now shows generic instructions for any supported provider

## [1.9.9] - Dynamic Remote Config & Auto-Update Overhaul

### Dynamic Remote Model Configuration
- **Models updated without rebuilding EXE** — Provider list, model names, and API URLs fetched from Cloudflare KV
- **3-tier fallback** — Remote → Local cache (24h) → Hardcoded defaults; app never blocks on network
- **15 AI providers, 180+ models** — Updated dynamically without app update

### Auto-Update System Overhaul
- **Versioned EXE rename** — New EXE saved as `CrossTrans_v{version}.exe`, old renamed to `.bak`
- **Registry auto-start sync** — Auto-start path updated automatically after update
- **First-launch retry** — Handles Windows Defender scanning delay on new EXE

## [1.9.8.x] - Performance, Dictionary & Stability

### Performance (v1.9.8.1)
- **Settings window opens instantly** — Lazy loading for heavy tabs (API, Dictionary, Guide)
- **NLP pre-warming** — Dictionary tab loads faster on subsequent opens

### Dictionary Mode (v1.9.8.2)
- **Hyphenated words preserved** — Words like "auto-update" stay as single tokens
- **Better sentence detection** — Expanded punctuation detection (55 characters)

### Stability (v1.9.8)
- **Trial mode auto-recheck** — Automatically re-validates API keys every 24h
- **Version upgrade detection** — Clears cache when upgrading to new version
- **Settings refactored** — Split into modular package structure

## [1.9.7] - Screenshot Translation

- **Screenshot Translation** — Win+Alt+S captures screen region for OCR translation
- **Multi-monitor support** — Works across all connected displays
- **Double-click to Preview** — Open attached files with system default app
- **Auto-check updates** — Non-intrusive toast notification on startup

## [1.9.6] - Dictionary Language Pack Fix

- Critical bug fix for Dictionary Language Pack in EXE builds
- Auto-detects system Python when running from EXE

## [1.9.5] - API Key Fix & Google REST API

- Fixed API Key saving position issue
- Animated "Installing..." text for Dictionary Language Pack
- Google provider now uses REST API (EXE 30MB smaller)

## [1.9.4] - HuggingFace Provider

- HuggingFace provider added (14 AI providers total)
- Test button now saves API key even on test failure

## [1.9.2–1.9.3] - Dictionary Mode & Trial Security

- Dictionary Mode with interactive word selection
- Enhanced Trial mode security
- 180+ models from 14 providers

## [1.7.0–1.9.0] - Trial Mode, Windows Hello & Provider Fallback

- **Trial Mode** — Free daily translations without API key
- **Windows Hello Authentication** — Secure API key protection
- **Smart Provider Fallback** — Auto-switch to backup API on failure
- **Scanned PDF OCR** support
- **Toast notifications** and **Search History**
