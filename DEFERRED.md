# CrossTrans — Deferred Items

> Work that was identified, deliberately not done, and should not be lost. Review at milestone
> starts: flag anything whose trigger condition is now met, and delete an entry once it ships.
>
> Nothing here is a bug report from a user — these are findings from implementation work that were
> left alone on purpose, mostly under the "touch only what the task requires" rule.

---

## D1 — Dictionary result window over-estimates its height by ~154 px

**Deferred**: 2026-08-10 (found during Phase F5)
**Effort**: Small
**Dependencies**: none

**What**: the Dictionary result popup reserves roughly 154 px more height than its content needs,
so the window has a band of empty space at the bottom.

**Why it happens**: `QuickTranslateManager.calculate_size()` measures the text using the popup's
normal font (Segoe UI 11), but `show_dictionary_result()` renders this particular window in
`DICT_RESULT_FONT` (Consolas 10). The measurement and the rendering disagree about the font, so
the estimate is wrong. The furigana part of the same budget (`overhead_px()`) is exact — this is
the pre-existing half.

**Why it was deferred**: it predates the furigana work entirely and is cosmetic. Fixing it means
changing how `calculate_size()` is called or parameterizing it by font, which touches the sizing
path for every popup — well outside the scope of the phase that found it.

**Revisit when**: anyone next works on popup sizing, or if a user reports the empty band.

**References**: `src/ui/quick_translate.py` (`calculate_size`, `show_dictionary_result`,
`DICT_RESULT_FONT`); CHANGELOG Phase F5; CLAUDE.md "Dictionary result window (F5)".

---

## D2 — Dead import: `Any` in `src/core/translation.py`

**Deferred**: 2026-08-04 (found during Phase F0)
**Effort**: Trivial
**Dependencies**: none

**What**: `from typing import Optional, Callable, Tuple, Any, Dict` — `Any` is imported and never
used anywhere in the file.

**Why it was deferred**: pre-existing dead code, unrelated to any change made. The project rule is
to remove only orphans your own change created, and to mention rather than delete pre-existing
dead code.

**Revisit when**: someone edits that import line for another reason — remove it then, in the same
change, rather than as a standalone commit.

**References**: `src/core/translation.py:9`.

---

## D3 — Furigana reading colour not confirmed

**Deferred**: 2026-08-06 (raised during Phase F2, offered to the user, never answered)
**Effort**: Trivial — one constant
**Dependencies**: a decision from the user; do not change it unilaterally

**What**: readings currently render in blue, `FURIGANA_RUBY_FG = '#80b8ff'`. Before Phase F2 they
rendered **white**, but not by choice: ttkbootstrap was silently discarding the explicit colour
kwarg at widget construction, so the intended blue never actually reached the screen. F2 fixed the
mechanism (`NO_AUTOSTYLE`), which made the blue appear for the first time.

So this is not "should we change the colour" but "which of the two was ever intended" — the white
users saw was an artefact, and the blue is what the code always asked for.

**Revisit when**: the user says. Ask before changing it in either direction.

**References**: `src/constants.py` (`FURIGANA_RUBY_FG`); CLAUDE.md Known Issues (the ttkbootstrap
entry); `src/ui/ruby_text.py` (`NO_AUTOSTYLE`).
