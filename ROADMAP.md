# CrossTrans — Roadmap

> Active and upcoming work only. Completed items are archived in `ROADMAP_DONE.md`
> and summarized for users in `CHANGELOG.md`. Deferred findings live in `DEFERRED.md`.
> Status legend: 📋 Planned (design pending) · 🔨 In progress · ✅ Done (archived)

---

## Where things stand

**Current release: 1.9.20** — tag `v1.9.20`, published 2026-09-02 with
`CrossTrans_v1.9.20.exe` attached. It carries the Word-like furigana work (copy the bases, one
shared baseline, no plate, 均等割り付け), the History window fix, "Open Translator" on a failed
quick translate, the dictionary window's empty band, the build script's false SUCCESS, and the
popup's model credit. Suite at that commit: 551 passed / 0 failed.

The previous public release was 1.9.19 (2026-08-18, furigana everywhere).

Every roadmap item up to and including 1.9.20 is complete and archived — nothing is
half-finished, and there is no work in progress.

**Unreleased work sits on `main`** (2026-09-07): the H1 health-review fixes — archived in
`ROADMAP_DONE.md`, detailed in `CHANGELOG.md` → Unreleased, reasoned in Decisions 12–14. Suite
551 → 593. **Not yet released**: no version bump, no tag, no build. That is the only thing
outstanding.

---

## Active / Upcoming

| Item | Status | Notes |
|------|--------|-------|
| Cut 1.9.21 | 📋 Planned | Bump `VERSION`, run `build_exe.bat`, tag, write release notes. The work it would ship is already on `main` and tested |

---

## Backlog — identified, not scheduled

D1–D3 were closed on 2026-08-28. The 2026-09-07 health review reopened the file with D4–D10;
**D6–D9 were closed the same day** (Groq had decommissioned every model D6/D7 named — see
Decision 15 — the two pieces of dead code went with them, and the clipboard tests were made
hermetic), and closing them surfaced **D11**. `DEFERRED.md` now holds **D4, D5, D10, D11** —
signalling the running instance instead of scolding the second one, JSONL logging, the absence
of CI, and the other providers' unverified default models. None is scheduled; each carries its own trigger condition.
