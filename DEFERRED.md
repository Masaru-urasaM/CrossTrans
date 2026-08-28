# CrossTrans — Deferred Items

> Work that was identified, deliberately not done, and should not be lost. Review at milestone
> starts: flag anything whose trigger condition is now met, and delete an entry once it ships.
>
> Nothing here is a bug report from a user — these are findings from implementation work that were
> left alone on purpose, mostly under the "touch only what the task requires" rule.

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
