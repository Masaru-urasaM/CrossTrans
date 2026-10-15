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

**Unreleased work on `main`**: the H1 health-review fixes (2026-09-07/08) — archived in
`ROADMAP_DONE.md`, detailed in `CHANGELOG.md` → Unreleased, reasoned in Decisions 12–20. They sat
on the unmerged branch `h1-health-review` until **2026-10-15**, when it was merged into `main`
(`f28a276`, `--no-ff`, not pushed). Suite 551 → 676. **Not yet released**: no version bump, no
tag, no build.

**In progress** (2026-10-15): Japanese language identity — furigana on every Japanese surface and
a Dictionary that knows which language it looks up. Plan and status in `TODO.md`; branch
`feature/japanese-language-identity`.

---

## Active / Upcoming

| Item | Status | Notes |
|------|--------|-------|
| Cut 1.9.21 | 📋 Planned | Bump `VERSION`, run `build_exe.bat`, tag, write release notes. The work it would ship is already on `main` and tested |
| Japanese language identity (`TODO.md`, phases J0–J12) | 🔨 In progress | **J0 ✅ J1 ✅ (2026-10-15)**: dictionary prompt states source → target and sends the context (Decision 21). **D13–D15 ✅ (2026-10-15)**: one Dictionary mode for both buttons (Decision 23), a failed lookup shows its message, no `grab_set()` in its dialogs. **J2 ✅ (2026-10-15)**: `src/core/lang_id.py`, evidence-only language identity (Decision 24: Big5-HKSCS). **J3 ✅ (2026-10-15)**: the dictionary result reads the stated source and both languages of an entry. **J4 ✅ (2026-10-15)**: translation prompts state the source or ask the model for a `[[SOURCE: ...]]` line - 10/10 compliance on Google and Groq (Decision 25). **J5 ✅ (2026-10-15)**: one Japanese/Chinese rule for detection, History and furigana; the Dictionary opens in the model's language or asks (Decision 26). **J6 ✅ (2026-10-15)**: the popup reads kanji-only Japanese the model placed, and asks "Japanese or Chinese?" when nobody did - the answer re-translates (Decision 27). Next: J7 main-window surfaces (Q1: the model decides, the user settles — Decision 22). Whether it ships in 1.9.21 or 1.9.22 is open |

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
the cross-provider model-name clash that surfaced from the same work. **D13–D15** came out of the
language-identity work on 2026-10-15 (Dictionary mode implemented twice, a failed lookup's toast
that raised `NameError`, the main-window dialogs' `grab_set()`) and were **closed the same day**.
Closing D15 surfaced **D16**: `UpdateFailedDialog` is a `grab_set()` + `transient()` +
`wait_window()` dialog on the withdrawn root - the documented freeze trap, on the failed-update
path. None is scheduled; each carries its own trigger condition.
