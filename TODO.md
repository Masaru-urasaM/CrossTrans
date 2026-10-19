# TODO - The quick-translate popup: sized by measuring, laid out for reading (B + C)

> **Status: 🔨 IN PROGRESS** on branch `feature/popup-sizing` (from `main` @ `53fee8e`). Approach
> B + C chosen by the user on 2026-10-19 (§1); every §3 question answered "as recommended" the
> same day, and **all of this work ships in 1.9.21** - the release waits for it. Decision 34
> records the choice.
>
> **P0 ✅ done 2026-10-19**: the corpus, the gallery tool and its `before` run; suite 1525 → 1547.
> **Next:** P1-P4 in one pass - the user, 2026-10-19: "no need to test after every small step;
> do it all from start to end, then test once".

## Contents

1. [Request and definition of done](#1-request-and-definition-of-done)
2. [Before starting](#2-before-starting)
3. [Questions for the user](#3-questions-for-the-user)
4. [Findings - measured 2026-10-19](#4-findings---measured-2026-10-19)
5. [Design](#5-design)
6. [Phases P0-P5](#6-phases-p0-p5)
7. [Manual end-to-end checklist](#7-manual-end-to-end-checklist)
8. [Risks](#8-risks)
9. [Non-goals](#9-non-goals)
10. [Adjacent findings - not part of this work](#10-adjacent-findings---not-part-of-this-work)
11. [Bookkeeping](#11-bookkeeping-rules-6-8-9-11)
12. [Appendix - how the measurements were made](#appendix---how-the-measurements-were-made)

---

## 1. Request and definition of done

**Request (2026-10-19, restated in English):** "In the quick-translate box, the way the box expands
with the length of the translation and of the original does not seem well optimised. Is there a
better idea - upgrade it, or change the way the box size is decided altogether? The end goal is an
interface that is much easier to read and to operate than now."

Three options were presented with the measurements in §4: **A** patch today's estimator, **B**
size the popup by measuring its real layout and size it for reading, **C** lay the popup out
again. The user: **"Do B + C, write it into TODO.md."**

- **B - size by measuring.** The popup is built invisible (alpha 0), Tk lays it out, the real
  heights are read, and only then is it given its size, its place, and made visible. Width follows
  readability (characters per line); height is capped, with a visible scrollbar beyond the cap;
  the translation has priority over the original; the popup never covers the cursor.
- **C - a layout that does not need 735 px.** A header with the model credit and an
  always-visible close button; a compact action bar; a collapsible original block; optionally a
  resizable popup that remembers its size.

**Definition of done:**

| # | Criterion | Checked by |
|---|-----------|------------|
| DoD1 | The close button is visible, inside the popup and clickable in every popup state, at every width. | `tests/test_popup_geometry.py` over the corpus (§4) × states: result, grammar, error, trial, chooser row, replace preview, custom prompt |
| DoD2 | Every text box is exactly as tall as its content up to its cap: blank ≤ 2 px; content beyond the cap is reachable through a **visible** scrollbar. | Same file: `given - needed` per box; scrollbar mapped ⇔ capped |
| DoD3 | Lines are readable: ≤ 75 characters per display line for Latin text, ≤ 40 for CJK ([WCAG 1.4.8](https://www.w3.org/WAI/WCAG22/Understanding/visual-presentation): at most 80 / 40) - except where one unbreakable token (a URL) is longer. | Same file: characters per display line on the corpus |
| DoD4 | Short results get a small popup: width = the text's natural width or the action bar's natural width, whichever is larger. With the bar chosen in Q1, a one-word result is ≤ 420 px wide (estimate for Q1 (c): ~390 px - confirmed in P3). | Same file, cases A, E, L |
| DoD5 | The popup is never taller than the cap (default 60% of the monitor's work area, Q4) and never covers the cursor point - unless the larger side has less room than the popup's minimum height. | Pure tests on `popup_layout.place()` (4 corners, multi-monitor coordinates) + the corpus |
| DoD6 | The popup appears once, already at its final size and place: transparent until measured (no flash, no jump), and visible even if measuring fails. | Two-step tests: alpha 0 before step 2, 1 after; a failing step 2 and a lost `sync` callback still show it |
| DoD7 | No regression. Test count monotonic from **1525**; every existing popup test passes - updated, never deleted, where it asserts a removed constant; step 2 ≤ 10 ms for text ≤ 1000 characters, ≤ 150 ms at the 3000-character annotation cap (this machine). | Full suite; `tools/check_test_counts.py`; a loose timing test |

---

## 2. Before starting

- **Read first:** CLAUDE.md → "Model credit on the quick-translate popup", "Replace Button (Copy &
  Replace)", "Furigana System" → "Renderer", Known Issues (ttkbootstrap discards colours →
  `autostyle=False`; never `grab_set()`; `bind_all()`); DESIGN_DECISIONS 3, 8 (Phase 1 addendum),
  10 (option 4), 11, 27, 29, 32, **34**; §4 here.
- **Baseline:** `main` @ `53fee8e`, 1525 tests (local: 1524 passed, 1 skipped). P0 re-runs it.
- **Must survive every phase:**
  - `WS_EX_NOACTIVATE` - the popup never takes the focus from the user's app (Custom Prompt drops
    it on purpose, to type).
  - No `grab_set()`, no `transient()` (CLAUDE.md Known Issues).
  - Furigana invariants: read every box with `get_plain()` (I2); an editable box holds no ruby (I3).
  - The attribute names the app and the tests use: `popup`, `popup_text`, `popup_furigana`,
    `popup_attribution`, `popup_source_chooser`, `popup_copy_btn`, `popup_replace_btn`,
    `popup_retranslate_btn`, `popup_dict_btn`, `popup_open_btn`, `popup_custom_prompt_btn`,
    `_btn_frame`, `_main_frame`.
  - The public API: `show()`, `show_loading()`, `close()`, `is_open`, `set_copy_button_text()`,
    `set_replace_button_text()`, `capture_mouse_position()`, `configure_callbacks()`,
    `stop_dictionary_animation()`, `show_dictionary_result()`. `calculate_size()` stays: the
    dictionary result window uses it (§9).
- **Tests stay quiet** (Decision 32): Tk windows on the private desktop only, never on the user's
  screen, no API call. Tests that need a laid-out window get one there.
- **The corpus has no Vietnamese** - the project rule forbids it in code. French with accents
  stands in for Latin text with diacritics; Vietnamese is covered by the user's manual check (§7).
- **Tooling:** Edit cannot match lines holding `\uXXXX` escapes, and `quick_translate.py` has
  several (`"✕"`, `"⚙"`) - memory `feedback_edit_unicode_escapes`. Import `src.core`
  before `config` in standalone scripts.

---

## 3. Questions for the user

| # | Question | Options | Recommended | Needed before |
|---|----------|---------|-------------|---------------|
| Q1 | Action bar style | (a) icons with tooltips; (b) Copy + Replace + a "⋯" menu for the rest; (c) hybrid: Copy and Replace (+⚙) as text, Re-translate / Dictionary / Open Translator / Custom Prompt as icons with tooltips; (d) today's text buttons, wrapping to a second row when narrow | (c) - the two most used actions stay words, the rest stay one click away. Decided on P0's images | P3 |
| Q2 | Colours | keep one colour per action (today); or one accent for Copy, neutral icons with a coloured hover | Copy blue and Replace purple kept (habit), icons neutral | P3 |
| Q3 | Reading width | 70 characters per line for Latin text, 36 for CJK (WCAG 1.4.8: at most 80 / 40); or narrower / wider | as proposed | P2 |
| Q4 | Height cap | 60% of the monitor's work area, then a scrollbar; or another share | as proposed | P2 |
| Q5 | Original block (Japanese with readings) | (a) collapsed to 3 rows with "Show all"; (b) always open within its 40% share | (a) - the translation is what was asked for | P3 |
| Q6 | Resizable popup that remembers its size | yes / no | yes (P4) | P4 |
| Q7 | Settings presets (Compact / Comfortable / Wide; height cap) | yes / no | only if Q6 is not enough | P4 |
| Q8 | P1 (close button always visible) | into 1.9.21 before the release (a rebuild, and your EXE test again); or the next version | into 1.9.21: it is a visible bug in the most common case | P1 |
| Q9 | Loading indicator | unchanged, but placed by the same rules, so it never spills off the screen and the result opens at the same anchor | as proposed | P2 |

**Answered 2026-10-19 - every question as recommended.** The user (restated in English): "Follow
the recommendation on every question. Everything in this session goes into 1.9.21." So: **Q1**
(c), the hybrid bar - decided without P0's prototype images; **Q2** Copy blue and Replace purple,
neutral icons with a coloured hover; **Q3** 70 / 36 characters per line; **Q4** a 60% cap;
**Q5** (a), the original collapsed to 3 rows with "Show all"; **Q6** yes, resizable and
remembered; **Q7** no presets; **Q8** P1 into 1.9.21 - and so is every other phase; **Q9** as
proposed.

---

## 4. Findings - measured 2026-10-19

**Setup:** `main` @ `53fee8e`, Python 3.14.0, Tk 8.6.15, ttkbootstrap `darkly`, 1920×1080 at 96 DPI
(100%), system-DPI-aware like `main.py`. The real `QuickTranslateManager.show()` on a private
desktop (Decision 32), fixed texts (no API call), the cursor at (960, 360). Screenshots taken with
`PrintWindow` (they work off-screen - see the Appendix). The cases are in the Appendix.

| Case | Popup | Translation box: given / needed px | Blank | Hidden | Lines | Chars per line (worst paragraph) | × shown |
|------|-------|------------------------------------|------:|-------:|------:|---------------:|:-------:|
| A one word ("Bonjour") | 670×161 | 48 / 20 | 28 | 0 | 1 | 7 | **no** |
| B one sentence | 670×161 | 48 / 20 | 28 | 0 | 1 | 83 | **no** |
| C paragraph (French, 520 chars) | 800×261 | 148 / 120 | 28 | 0 | 6 | **99** | yes |
| D four paragraphs | 800×681 | 568 / 540 | 28 | 0 | 27 | **99** | yes |
| E Japanese sentence + readings | 670×220 | 22 / 20; original 56 / 42 | 2; 14 | 0 | 1 | 27 | **no** |
| F Japanese paragraph + readings | 800×328 | 74 / 60; original 112 / 110 | 14; 2 | 0 | 3 | **111** | yes |
| G long Japanese + readings | **800×1012** | 366 / 360; original 504 / 660 | 6 | **156** (original) | 18 | **111** | yes |
| H English → Japanese (readings in the box) | 752×200 | 87 / 55 | 32 | 0 | 2 | 26 | yes |
| I 10-line list | 670×341 | 228 / 200 | 28 | 0 | 10 | 18 | **no** |
| J long URL | 800×181 | 68 / 60 | 8 | 0 | 3 | 46 | yes |
| K error | 670×180 | 97 / 60 | 37 | 0 | 3 | 67 | yes |
| L kanji term, trial line + chooser row | 670×232 | 46 / 20 | 26 | 0 | 1 | 3 | **no** |
| M English → Chinese paragraph | 800×201 | 88 / 60 | 28 | 0 | 3 | **49** (CJK) | yes |

### S1 - The close button is not drawn on any short result (bug)

The action bar - Copy, Replace, ⚙, Re-translate, Dictionary, Open Translator, Custom Prompt, ✕ -
needs **735 px**; `MIN_WIDTH` is **670** (Decision 3, set when the bar had fewer buttons). The ✕ is
packed last, so it is the one squeezed out: cases A, B, E, I, L - every result shorter than a
line. "Custom Prompt", next to it, is clipped at the edge.

### S2 - "Get Free API Key" is cut at every width

The trial line's link is a `width=14` button holding a 16-character label: Tk gives it 14
characters, whatever the popup's width (case L). Found by the gallery tool's check, after the
first screenshots had been read as the popup's edge cutting it.

### S2b - With the ✕ gone, a short result is hard to close

Copy does not close the popup (`app._on_quick_translate_copy` copies and shows a toast). Esc never
reaches it: the popup is `WS_EX_NOACTIVATE` and never has the keyboard focus. What is left:
Replace, Open Translator, or the next translation.

### S3 - Short results sit in a large, mostly empty box

The bar holds the width at 670 px or more, whatever the text. The text covers **1.0%** of the
popup for one word (A: 52 px of a 628 px line), **0.3%** for a kanji term with the trial line
(L: "Car"), **9.7%** for a 10-line list (I: 111 of 628 px used), **10%** for a one-line sentence.

### S4 - A blank band under every text

28 px on every Latin case, 32 on H, 37 on the error: the "+1 line" buffer plus a
`VERTICAL_PADDING` of 100 px that does not match the real chrome.

### S5 - Lines too long to read comfortably

At the 800 px maximum, Latin text runs **99-111 characters per line** (C 99, D 99, F 111, G 111),
and a sentence that does not wrap is set as one 83-character line (B).
WCAG 1.4.8 asks for at most 80 (40 for CJK); typography's long-standing range is 45-75, 66 ideal
(Bringhurst, *The Elements of Typographic Style*, 2.1.2). English → Chinese runs 49 CJK
characters per line.

### S6 - Long results fill the screen and cover the selection

G is **1012 px tall on a 1080 px screen**, placed at y = 10. D (681 px) is pinned at y = 341,
across the cursor at y = 360 - over the very text the user selected. G's original block hides
156 px that only the mouse wheel can reach: there is no scrollbar and nothing says more is there.
[Fluent 2's popover guidance](https://fluent2.microsoft.design/components/web/react/core/popover/usage):
size a popover so it does not hide important UI, and keep hidden content reachable by scrolling
along one axis.

### S7 - Chrome outweighs short results

113 px of chrome (credit line, paddings, the bar) under a 20 px result; **186 px** with the trial
line and the chooser row, around a 3-letter translation.

### S8 - Root cause: the size is estimated before the layout, from constants

- `MIN_WIDTH = 670`, `VERTICAL_PADDING = 100` (twice: `calculate_size()` and `show()`), a "+1 line"
  buffer, and `ceil(paragraph width / available width)` standing in for word wrap. Every widget
  change since has drifted them silently - S1 is exactly that.
- `MAX_HEIGHT` is applied **before** the credit, trial, chooser and furigana heights are added, so
  the cap can be exceeded.
- The original block and the translation box are both packed `expand=True`, so whatever height is
  left over or missing is split between them by the packer, not given to the box that needs it.
  Even with an exact total, E came out −14 / +14 px and G +156 / −156 px (§S9, two-step test).

### S9 - What measuring needs (spike, same day)

| Question | Result |
|----------|--------|
| Does a **withdrawn** (never shown) Toplevel lay out its children? | **No.** The box stays 1 px wide; `count -update -ypixels` returned 10180 px for a paragraph that needs 160 px. Tk's packer only arranges the slaves of a mapped master. |
| Are **requested** sizes known before showing? | **Yes.** A replica of the action bar requested 737 px (767 with the frame's padding) both before and after mapping; its actual width was 1 px until shown, then 737 px. |
| Does a window mapped at **alpha 0** give real heights? | **Yes**, once the event loop has run: after resizing to the measured total, residue 0 px in every single-box case. |
| Is there a precise moment to measure? | **Yes.** Tk 8.6.15 has `text sync -command` ([TIP 438](https://core.tcl-lang.org/tips/doc/trunk/tip/438.md)): `<Configure>` with the real width arrived first, then the sync callback with current line heights. No `update()` needed. |
| What does the measuring step cost? | 2-8 ms on 11 of 13 cases; 17 ms on F; **114 ms** on G (~800 ruby frames at the 3000-character cap), whose whole `show()` already takes 278 ms. Nothing is built twice. |
| Would a pure word-wrap model do instead? | **Not exactly:** it matched Tk on 61 of 65 (width, text) pairs, and missed on mixed Latin + kanji and at some widths. |

### S10 - Screenshots without a screen

`PrintWindow(PW_RENDERFULLCONTENT)` captures a popup on the private desktop: a gallery of every
case and state can be produced, and compared before and after, with nothing on the user's screen.

---

## 5. Design

### 5.1 Principles

- **Measure, never estimate widget geometry.** Sizes come from Tk: `winfo_reqwidth/height()` of the
  real widgets and `count -ypixels` of the real boxes after layout. Constants are kept only for
  *policy* (characters per line, the height cap) - never for how tall a widget is.
- **The translation first.** It is what the user asked for; the original and the chrome yield.
- **Never cover what the user selected.**
- **One engine for every popup state.**

### 5.2 The two-step show (B)

**Step 1** - inside `show()`, same turn as today:
1. Decide the width (§5.3) from text metrics and the requested widths of the header and the bar
   (known before mapping, §S9).
2. Build every widget; set `-alpha 0`; place the popup at its anchor with a provisional height.
3. On the translation box's first `<Configure>` at the intended width, register
   `text sync -command step2`. Stamp the popup with a generation number.

**Step 2** - from the event loop, when the line heights are current:
1. If the popup was closed or replaced since (generation mismatch): do nothing.
2. Read each box's needed height (`count -update -ypixels`). When a cheap estimate is already
   far above the box's cap (> 1.5×), skip the exact count: the box is capped either way (this keeps
   the 3000-character case fast).
3. Allocate heights (§5.4) and give each box an exact pixel height - its own frame with
   `pack_propagate(False)`, or a grid row with a fixed size - so no two boxes share leftovers.
4. Popup height = the chrome's requested height + the boxes. Place it (§5.5), set the geometry,
   then `-alpha 1`.

**Safety:** an exception in step 2 is logged and the popup is shown with step 1's geometry; a
watchdog (`after(250)`) shows it if step 2 never ran. A popup is never left invisible.

**Every state goes through it:** result, grammar fix, error, trial line, chooser row, the replace
preview (re-measured after its content swap), Custom Prompt (keeps its measured size and scrolls
while typing; Cancel re-shows), and the loading indicator (placed by §5.5's rules).

### 5.3 Width

- `avg` = the text's own average glyph width in the box font (`font.measure(text) / len(text)`);
  for ruby text, the ruby model's widths.
- `readable` = target characters × `avg`: 70 for Latin text, 36 for CJK (Q3), interpolated by
  the share of CJK characters in the text.
- `natural` = the widest logical line.
- `minimum` = the requested width of the header and of the action bar - measured, never a constant.
- **width = clamp(natural, minimum, readable)** + the paddings (+ the scrollbar's width when
  capped), and never more than 90% of the work area.
- Stretch goal (P2, kept only if the gallery shows it helps): balanced lines for 2-3-line results
  - the narrowest width that keeps the line count, so no short last line.

### 5.4 Height

- `cap` = 60% of the work area's height (Q4); `room` = `cap` − the chrome.
- If the translation and the original both fit in `room`: both get exactly what they need.
- Otherwise the original gets at most its share - 40% of `room`, never less than 3 rows, or its
  collapsed 3 rows (Q5) - and the translation gets the rest, never less than 3 rows. A capped box
  shows its scrollbar.

### 5.5 Position

- The anchor is the cursor at hotkey time (`capture_mouse_position()`, as today), on the monitor
  that holds it (`get_monitor_work_area()`, as today).
- Try below-right, above-right, below-left, above-left of the anchor (today's 15 / 20 px offsets);
  the first that fits entirely in the work area wins.
- If none fits, take the vertical side with more room and lower the cap to that room: the popup
  scrolls rather than covering the anchor.

### 5.6 Layout (C)

```
┌───────────────────────────────────────────────────┐
│ Translated with gemini-2.5-flash (Google)       ✕ │  header: drag handle; ✕ always shown
│ Trial Mode (15/20 left) · Get Free API Key        │  trial only
│ ▾ Original (Japanese)                             │  collapsible (Q5)
│   きょう   にほんご   べんきょう                    │
│   今日は日本語を勉強しています。                    │
│ ───────────────────────────────────────────────── │
│ Today I am studying Japanese.                   ▐ │  scrollbar only when capped
│ Kanji-only text - read as Chinese. [Read as …]    │  chooser row, when shown
│ [Copy] [Replace ⚙]   ↻   📖   ↗   ✎              │  action bar - style per Q1 / Q2
└───────────────────────────────────────────────────┘
```

- **Header:** the credit (left, elided with "…" if the popup is narrow) and ✕ (right). The header
  and the background stay drag handles.
- **Action bar** per Q1 and Q2. Tooltips open after 500 ms and are `WS_EX_NOACTIVATE` too. Icon
  font: Segoe Fluent Icons (Windows 11) → Segoe MDL2 Assets (Windows 10) → Segoe UI Symbol; all
  three are on this machine.
- **Feedback:** `set_copy_button_text("Copied!")` keeps working; on an icon it shows ✓ for a second.
- **Error popup:** header with ✕, the message, [API Settings] [Open Translator]. **Grammar fix:**
  the same bar without the translation-only actions. **Replace preview:** [Agree] [Cancel].
  **Custom Prompt:** [Send] [Cancel].

### 5.7 What stays

The colours of the text (white, errors `#ff6b6b`), the fonts (Segoe UI 11; Yu Gothic for the
readings), the dark background, `WS_EX_NOACTIVATE`, topmost-then-not, dragging to move, and the
dictionary result window (separate; keeps `calculate_size()`).

---

## 6. Phases P0-P5

Every phase: tests first where a bug is reproduced; the full suite after; CHANGELOG, ROADMAP and
memory in the same commit (§11); a step-by-step manual check for the user.

### P0 - Baseline, the gallery tool, the bar prototypes  *(no production code)*  ✅ Done (2026-10-19)

- `tests/popup_cases.py`: the corpus (A-M, §Appendix) plus the states - grammar fix, error,
  replace preview, Custom Prompt - shared by the tool and the tests. Not a test module.
- `tools/popup_gallery.py --label NAME`: renders every case and state on a private desktop
  (refuses without one), writes `logs/popup_gallery/NAME/*.png` and `NAME.json` with the §4
  metrics. Run once as `--label before`.
- ~~Prototype images of Q1's four bar styles~~ - dropped: Q1 and Q2 were answered as recommended
  without them (§3).
- The full suite, to confirm the baseline.
- **Tests:** the tool refuses to run without a private desktop; the corpus is well formed (and
  holds no Vietnamese, §2).
- **Manual check:** open the `before` images.
- **Estimate:** Small-Medium.

### P1 - The close button always visible  *(S1, S2; DoD1)*

- In today's layout: the minimum width comes from the bar's and the trial line's requested width
  (read off the widgets before the geometry is set, §S9) instead of 670.
- The trial line's "Get Free API Key" button loses its `width=14`, so it is as wide as its label
  (S2).
- **Tests first** (they fail today on A, B, E, I, L): `test_close_button_is_inside_the_popup` for
  every case and state; no control clipped (`popup_gallery.clipped_controls`), which also fails
  on L's link.
- Ships on its own (Q8): P3 moves the ✕ to the header later, but users get the fix now.
- **Manual check:** select one word, translate, see ✕ and click it; in trial mode, read the whole
  "Get Free API Key".
- **Estimate:** Small.

### P2 - The sizing engine (B)  *(DoD2, DoD3, DoD5, DoD6, DoD7)*

- **P2a - `src/ui/popup_layout.py`, pure** (no Tk): `choose_width()`, `allocate_heights()`,
  `place()`, the reading-width policy (§5.3-5.5). **Tests:** `tests/test_popup_layout.py` - short,
  long, Latin, CJK, mixed; both boxes overflowing; the original collapsed; the four corners; a
  monitor at negative coordinates; a work area too small for either side.
- **P2b - the two-step show** (§5.2) in `quick_translate.py`: alpha 0, `<Configure>` → `sync`,
  exact per-box heights, scrollbars only when capped, the generation number, the fallback and the
  watchdog. **Tests:** `tests/test_popup_geometry.py` over the corpus - blank ≤ 2 px, hidden only
  with a visible scrollbar, height ≤ cap, characters per line, alpha 0 until step 2, closing
  during step 1, a failing step 2, a lost sync callback; a loose timing test.
- **P2c - every state and the loading indicator:** replace preview, Custom Prompt (enter, Send,
  Cancel), error, grammar, chooser row, trial line; `show_loading()` placed by `place()`.
- Existing tests that assert `ATTRIBUTION_PX`, `SOURCE_CHOOSER_PX`, `HORIZONTAL_PADDING` or
  `FURIGANA_SEPARATOR_PX` are rewritten to assert the measured behaviour if the constants go -
  never deleted (monotonic count).
- **Manual check:** one word, a paragraph, a long article, Japanese with readings, a corner of the
  screen, the replace preview, Custom Prompt (§7 steps 2-4, 8-11).
- **Estimate:** Medium-Large, hence three steps.

### P3 - The layout (C)  *(DoD1, DoD4)*

- **P3a:** the header with ✕; the action bar per Q1 / Q2; tooltips; the icon font chain; ✓
  feedback; the trial line. **Tests:** ✕ in the header in every state; the bar's natural width;
  tooltips open and close, `NOACTIVATE`; the font chain picks a font from the families list (pure);
  `set_copy_button_text()` on an icon; the attribute names of §2 still exist.
- **P3b:** the collapsible original block (Q5). **Tests:** collapsed shows 3 rows; "Show all"
  opens it within its share; Re-translate keeps the state.
- Decision 3 marked superseded (done when Decision 34 was written); Decision 34 completed.
- **Manual check:** §7 steps 2, 5-7, 13; the four kinds of popup side by side with the P0 images.
- **Estimate:** Medium.

### P4 - Size the user controls  *(Q6: yes; Q7: no presets)*

- A resize grip; the width and the cap the user sets are remembered (`config.py` getters and
  setters, `%APPDATA%\CrossTrans\config.json`) and become the next popup's reading width and cap.
- **Tests:** config round trip; the grip resizes and saves; the next popup uses the saved size.
- **Estimate:** Small-Medium.

### P5 - Final check and archive

- The full suite; `tools/mutation_check.py` on `popup_layout.py`; `tools/popup_gallery.py --label
  after` beside `before`.
- CLAUDE.md: a "Quick-translate popup layout" section (the two-step show, the policy values, what
  not to bring back: estimating before layout, the single wide bar); DESIGN_DECISIONS 34 final;
  ROADMAP → ROADMAP_DONE ("P"); CHANGELOG; memory.
- The manual end-to-end checklist (§7). This file is deleted on completion; docs then cite it by
  commit, as `git show 5cc8736:TODO.md` is cited for J.

---

## 7. Manual end-to-end checklist

For the user, after P3 (and the relevant steps after each phase). Close the running CrossTrans
first - a second instance only brings the first one forward.

1. Start the new build (or `python main.py`).
2. In Notepad, type `Hello`, select it, press your translate hotkey (e.g. Win+Alt+V). The popup is
   small, beside the cursor; ✕ is at the top right; no empty band under the text. Click ✕.
3. Select a paragraph of about five lines. Lines are about 70 characters; the box ends where the
   text ends.
4. Select a long article (two screens or more). The popup is at most about 60% of the screen
   high, shows a scrollbar, and does not cover the cursor or the selected text.
5. Japanese text: the original block (with readings) is above the translation; collapse and
   expand it.
6. A kanji-only word such as 汽車: the chooser row appears; the popup grows by that row only.
7. Trial mode: the trial line is fully readable.
8. Replace: the preview fits; Agree pastes into Notepad.
9. Custom Prompt: the box becomes editable, keeps its size and scrolls; Send works; Cancel
   restores the translation.
10. An error (an invalid key): the error popup shows ✕, API Settings and Open Translator.
11. Move the cursor to the bottom-right corner of the screen and translate: the popup flips to stay
    on screen and does not cover the cursor.
12. A second monitor, if there is one: the popup opens on the monitor holding the cursor.
13. Copy: the feedback shows; the popup stays open; ✕ closes it.
14. Translate into and from Vietnamese (not in the automated corpus, §2): lines and heights look
    right with the diacritics.

---

## 8. Risks

| Risk | Mitigation |
|------|------------|
| A layered (alpha) window behaves differently with `WS_EX_NOACTIVATE` and topmost on some setups (Remote Desktop, old drivers) | Step 2's fallback and watchdog; a test that forces both |
| Step 2 runs after the popup was closed or replaced | The generation number; tests that close and re-show during step 1 |
| `sync -command` fires before the box has its real width | Step 2 checks the width it was meant for and re-arms once; measured order on 8.6.15: `<Configure>`, then sync |
| Step 2 at the 3000-character cap (114 ms measured) | Skip the exact count when the estimate is far above the cap; the timing test |
| Windows 10 lacks Segoe Fluent Icons | The font chain (MDL2 Assets, then Segoe UI Symbol); a pure test of the choice |
| CI (windows-latest, on screen) has other fonts and DPI | Tests assert relations - ✕ inside, blank ≤ 2 px, height ≤ cap - not absolute pixels |
| Icons are less discoverable than words (why Decision 3 kept text) | Tooltips; Q1 decided on images, with words kept for the two most used actions in (c) |
| A constant removed in P2 is asserted by an existing test | Rewritten to assert the measured behaviour - the count never drops |

---

## 9. Non-goals

- **The dictionary result window** - a separate window with monospace columns; it keeps
  `calculate_size()`. It could use `popup_layout` later.
- **The main window, the expanded view, History.**
- **Esc to close.** Esc never reaches the popup (`WS_EX_NOACTIVATE`). Catching it would need
  `RegisterHotKey` for Esc - taking Esc away from the user's app while a popup is open - or a
  low-level keyboard hook, which `hotkey.py` avoids on purpose. The always-visible ✕ is the fix.
- **Per-monitor DPI awareness.** The app is system-DPI-aware (`main.py`); on a second monitor
  with another scale the popup is bitmap-scaled. A separate topic.
- **Animations and fades** - Tk has no gradients; a fade needs a canvas overlay.

---

## 10. Adjacent findings - not part of this work

- `show_loading()` places the loading indicator at the cursor + (15, 20) with no screen-edge check:
  near the bottom-right corner it can spill off the screen. Folded into P2c (Q9).
- `_show_replace_preview()` derives a row count from the same `VERTICAL_PADDING = 100`. Replaced in
  P2c.
- The dictionary result window shares `calculate_size()` (§9).

---

## 11. Bookkeeping (Rules 6, 8, 9, 11)

- Per phase, in the same commit: a CHANGELOG entry (tests old → new); the ROADMAP row's status;
  memory `project_popup_sizing.md`; Decision 34 updated with what was measured.
- Anything deferred goes to DEFERRED.md with its trigger. A question answered "no" (Q6, Q7) is a
  non-goal, not a deferral.
- On completion: a "P" section in ROADMAP_DONE.md with the manual checks; this file deleted, cited
  by commit.

---

## Appendix - how the measurements were made

- **Scripts** (scratchpad of the 2026-10-19 session; P0 promotes the first into
  `tools/popup_gallery.py`): `popup_measure.py` (the 13 cases, the metrics, the screenshots),
  `measure_experiment.py` (withdrawn vs alpha 0), `measure_experiment2.py` (the two-step show and
  the word-wrap model), `sync_probe.py` (TIP 438), `reqwidth_probe.py` (requested widths before
  mapping). All run under `tests/quiet_session.py` on a private desktop, with `APPDATA` pointed at
  a scratch folder - nothing on the screen, no network, no API call, the user's settings untouched.
- **Metrics:** "given" = the box's height less its border, highlight and padding; "needed" =
  `count -update -ypixels 1.0 end`; "chars per line" = each paragraph's characters over the
  display lines Tk wrapped it into (an unwrapped line counts whole), the largest of them - first
  measured as all characters over all display lines, which counted the blank lines between
  paragraphs (D read 88); "text covers" = the widest line × the shown text height ÷ the popup's
  area. `tools/popup_gallery.py` computes all of them (P0).
- **Cases** (credit line "gemini-2.5-flash (Google)" on all but K):
  A `Hello` → `Bonjour`; B one English sentence → French; C an English paragraph on machine
  translation → French (520 characters); D C four times; E 私は毎日日本語を勉強しています。 →
  English, with readings; F a Japanese paragraph (a day in Kyoto, 120 characters) → English; G F
  plus a work email, three times; H an English request → 添付の資料をご確認の上、… (readings in the
  box); I a 10-line shopping list → French; J a sentence holding a 110-character URL; K an error
  notice ("Error: All API keys failed. …", three lines); L 汽車 → `Car`, placed as Chinese, trial
  mode (15/20 left); M C → Simplified Chinese.
- **References:** [WCAG 2.2 Understanding 1.4.8 Visual
  Presentation](https://www.w3.org/WAI/WCAG22/Understanding/visual-presentation) (at most 80
  characters, 40 for CJK); Robert Bringhurst, *The Elements of Typographic Style*, §2.1.2 (45-75
  characters, 66 ideal); [Fluent 2 - Popover
  usage](https://fluent2.microsoft.design/components/web/react/core/popover/usage); [TIP 155 -
  the text `count` subcommand](https://www.tcl-lang.org/cgi-bin/tct/tip/155.html) (`-update` for
  `-ypixels`); [TIP 438 - Ensure line metrics are
  up-to-date](https://core.tcl-lang.org/tips/doc/trunk/tip/438.md) (`sync`, `pendingsync`).
