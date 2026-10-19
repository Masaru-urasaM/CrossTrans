# CrossTrans — Roadmap

> Active and upcoming work only. Completed items are archived in `ROADMAP_DONE.md`
> and summarized for users in `CHANGELOG.md`. Deferred findings live in `DEFERRED.md`.
> Status legend: 📋 Planned (design pending) · 🔨 In progress · ✅ Done (archived)

---

## Where things stand

**Current release: 1.9.20** — tag `v1.9.20`, published 2026-09-02 with
`CrossTrans_v1.9.20.exe` attached: the Word-like furigana work, the History window fix, "Open
Translator" on a failed quick translate, the dictionary window's empty band, the build script's
false SUCCESS, and the popup's model credit.

**Next: 1.9.21** — the number the user chose on 2026-10-16; `VERSION` says so. Everything for it is
on `main`, pushed, CI green (1780 tests: 1770 passed, 10 skipped by design). Not tagged, not
released. What it carries, each archived in `ROADMAP_DONE.md` and detailed in `CHANGELOG.md` →
Unreleased:

| Work | ROADMAP_DONE | Decisions |
|---|---|---|
| Health review: the "already running" notice, the JSON Lines log, CI | H1 | 12–20 |
| Japanese language identity: furigana on every Japanese surface, a Dictionary that knows its languages | J | 21–27 |
| Follow-ups and quiet tests; accurate furigana as a download (D19) | K | 28–33 |
| D11's default models, deployed to the Worker (2026-10-19) | — (CHANGELOG "Worker deploy") | 19, 20, 31 |
| The quick-translate popup: sized by measuring, laid out for reading; the grip, every edge, on top when shown | P | 34, 35 |

**Current build**: `dist\CrossTrans_v1.9.21_edges_2026-10-19.exe`, from `f4781dc`. The user tested
the popup work on it on 2026-10-19 - "a complete success".

---

## Active / Upcoming

| Item | Status | Notes |
|------|--------|-------|
| Release 1.9.21 | 📋 Waiting for the user | Tag `v1.9.21`, write the release notes, publish the GitHub release with the EXE. The user, 2026-10-19: not yet - commit only. A release reaches every user through the auto-updater, so it goes out only on the user's word. |

---

## Backlog — identified, not scheduled

Open in `DEFERRED.md`, each with its trigger:
- **D11** - the default models of eight providers are listed from the providers' own docs and
  deployed, but not yet called (each needs its own key); a possible `'AIza'` key prefix for Google
  is the user's call.
- **D20** - the popup's `WS_EX_NOACTIVATE` has never been in effect; making it effective would send
  Ctrl+C on a selection in the popup to the user's app. The user's call (recommended: leave it).
- **D21** - `estimate_notation_px()` and `estimate_ruby_overhead_px()` in `ruby_text.py` are
  called only by their tests since Decision 34.

Closed, with the details in `CHANGELOG.md` and the decisions: D1–D3 (2026-08-28); D4–D10
(2026-09-07/08, Decisions 15–18); D12–D19 (2026-10-15/16 - the key decides between providers,
one Dictionary mode, a failed lookup's message, no `grab_set()` dialogs, History in batches, dead
code, UniDic as a download).
