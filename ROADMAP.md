# CrossTrans — Roadmap

> Active and upcoming work only. Completed items are archived in `ROADMAP_DONE.md`
> and summarized for users in `CHANGELOG.md`. Deferred findings live in `DEFERRED.md`.
> Status legend: 📋 Planned (design pending) · 🔨 In progress · ✅ Done (archived)

---

## Where things stand

**Current release: 1.9.19** — tag `v1.9.19`, published 2026-08-18 with
`CrossTrans_v1.9.19.exe` attached. It is the first public release since 1.9.16 (1.9.17 and
1.9.18 were never published), so it ships Fix Grammar, Merged Translate-or-Fix and furigana
everywhere in one go. Suite at that commit: 450 passed / 0 failed.

Every roadmap item up to and including 1.9.19 is complete and archived — nothing is
half-finished, and there is no work in progress.

---

## Active / Upcoming

_No active items._ The next task has not been chosen yet.

---

## Backlog — identified, not scheduled

Reviewed at this milestone start (post-1.9.19). Full context for each item is in `DEFERRED.md`;
this table exists so nothing is silently forgotten when picking the next task.

| ID | Item | Effort | Status |
|----|------|--------|--------|
| D1 | Dictionary result window reserves ~154 px more height than its content (cosmetic, pre-dates furigana) | Small | 📋 Revisit when popup sizing is touched |
| D2 | Dead import `Any` in `src/core/translation.py` | Trivial | 📋 Fold into the next edit of that import line |
| D3 | Furigana reading colour — blue `#80b8ff` (what the code always asked for) vs the white users actually saw before F2 fixed the ttkbootstrap bug | Trivial | ⏸ **Blocked on a decision from the user** — do not change in either direction unilaterally |
