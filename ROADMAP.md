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

**Unreleased work on branch `feature/japanese-language-identity`** (2026-10-15): Japanese
language identity — furigana on every Japanese surface and a Dictionary that knows which
language it looks up, plus one Dictionary mode for both buttons (D13–D15). Archived in
`ROADMAP_DONE.md` ("J"), detailed in `CHANGELOG.md` → Unreleased, reasoned in Decisions 21–27.
Branched from `main` after the H1 merge; **not merged into `main`, not pushed**. Suite 676 → 1183.

**Follow-ups on the same branch (2026-10-16, phases K1–K13)**: the fifteen items proposed after
J12, which the user asked for in full - the suite on a clean machine, the EXE, D16, the verdict
gaps of the new feature, History, the old deferred items, AGENTS.md, tooling and measurements -
and quiet tests (K12), after the user reported that test runs threw windows over the screen and
the measurements used up the translation quota. Archived in `ROADMAP_DONE.md` ("K"), detailed in
`CHANGELOG.md` → Unreleased, reasoned in Decisions 28–32. Suite 1183 → 1502. **Not merged into
`main`, not pushed.**

---

## Active / Upcoming

| Item | Status | Notes |
|------|--------|-------|
| Cut 1.9.21 | 🔨 In progress | Chosen by the user on 2026-10-16: `VERSION` bumped, the branch merged into `main` and pushed (CI green), and built by hand as `dist\CrossTrans_v1.9.21.exe` (`build_exe.bat` deletes `dist\` first, released EXEs included). The quick-translate popup work (ROADMAP_DONE "P", Decision 34) - the user, 2026-10-19: everything in that session goes into 1.9.21 - is merged (`b64cd92`, then the "Show all" fix `51435a3`) and pushed, and 1.9.21 rebuilt as `dist\CrossTrans_v1.9.21_popup_2026-10-19.exe` (the earlier file was in use). Then the user found the grip drag laggy: it now drags an outline (Decision 35, merged `4f926b4`, pushed), rebuilt as `dist\CrossTrans_v1.9.21_grip_2026-10-19.exe`. Still to do: the user's manual checks on that EXE (ROADMAP_DONE "P" and "K"; test first, then release), then tag, write release notes. The H1 work is on `main` and tested; the language-identity work is on its branch - merge it first if it ships in 1.9.21 rather than 1.9.22 (the user's call) |

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
Five providers checked, not one table clean - eight remain, each needing its own key (desk-checked
against the providers' own deprecation pages on 2026-10-16, K8: Anthropic, xAI and DeepSeek are
entirely gone, Together and OpenAI going this month; **replaced the same day from the providers'
docs**, K15 - listed, not yet called; **deployed to the Worker on 2026-10-19**, together with the
September Cerebras, SambaNova and OpenRouter fixes that had never reached it). **D12** is the cross-provider model-name clash
that surfaced from the same work (**closed 2026-10-16**, K8: the key decides). **D13–D15** came out of the
language-identity work on 2026-10-15 (Dictionary mode implemented twice, a failed lookup's toast
that raised `NameError`, the main-window dialogs' `grab_set()`) and were **closed the same day**.
Closing D15 surfaced **D16**: `UpdateFailedDialog` is a `grab_set()` + `transient()` +
`wait_window()` dialog on the withdrawn root - the documented freeze trap, on the failed-update
path (**closed 2026-10-16**, K2). The language-identity work then added **D17** (the History dialog takes ~1 s to open with
100 entries, before any readings; **closed 2026-10-16**, K7) and **D18** (two pieces of dead code; **removed 2026-10-16**, K8). None is scheduled; each
carries its own trigger condition. **D19** (2026-10-16, K1): pykakasi - the one reading provider
every install has - reads a word differently from fugashi in 30% of real sentences (**closed
2026-10-16**, K14: the user chose a download over bundling - the Japanese pack in Settings ->
Dictionary now applies to furigana at once, and the tab says which reader is in use). **D20** (2026-10-19, found in the popup work): the
quick-translate popup's `WS_EX_NOACTIVATE` has never been in effect - set before Tk creates the
window that would carry it; left for the user, since making it effective would send Ctrl+C on a
selection in the popup to the user's app.
