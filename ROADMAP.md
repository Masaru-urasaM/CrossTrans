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
**D6–D9 were closed on 2026-09-07** (Groq had decommissioned every model D6/D7 named — see
Decision 15 — the two pieces of dead code went with them, and the clipboard tests were made
hermetic), **D4, D5 and D10 on 2026-09-08** (a second instance now asks the running one for its window, the
file log is JSON Lines, and the suite runs on `windows-latest` for every push; see Decisions 16
to 18), and closing them surfaced **D11**. `DEFERRED.md` now holds **D11** and **D12**. D11 was
narrowed three times on 2026-09-08: Google's three defaults were dead and were replaced and made
self-maintaining (Decision 19); OpenRouter's two were dead *and* mis-routed to Together
(Decision 20); then keys arrived for Cerebras and SambaNova, whose lists were 6/6 and 11/12 dead.
Five providers checked, not one table clean - eight remain, each needing its own key. **D12** is
the cross-provider model-name clash that surfaced from the same work. None is scheduled; each carries its own trigger condition.
