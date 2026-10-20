# CrossTrans - Completed Roadmap Items

Completed work only. Active tasks: [ROADMAP.md](ROADMAP.md).
Implementation rules: [CLAUDE.md](CLAUDE.md) and [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md).

## v1.9.21 asset refresh - Update offers (2026-10-20)

Repaired automatic notifications; added daily checks, persisted Later/Skip, Settings/tray
entries, UI-thread delivery and explicit idle restart. EXE digest verification uses GitHub
asset metadata. Decision 43 records the policy; the user requested the same-version refresh.
Verification: 1989 passed, one intentional clipboard skip; 43 focused update tests and
seven mutation checks passed. Live read-only GitHub metadata matched the v1.9.21 EXE/hash.
The CI collection floor is now 1950.
Delivery: refreshed `CrossTrans_v1.9.21.exe` and `SHA256SUMS.txt` in the existing release;
71 packaged project modules match source, with the furigana dictionary/codecs bundled.

## v1.9.21 - Completed and user-accepted (2026-10-20)

| Task | Delivered |
|---|---|
| L - Linked reading | Optional sentence links across popup, main window, cache and History; shared toggles, subtle highlights, safe ruby offsets and conservative legacy maps. |
| L - Follow-ups | Source always visible; both panes expand; Open Translator at far right; whole-word source wrapping; incomplete results rejected; 20-second deadline, cancellation and stale-result protection; Groq low reasoning and explicit output budget. |
| P - Popup layout | Measured sizing, readable width, scrollbars, on-top reveal, remembered geometry and smooth resizing from every edge. |
| K - Follow-ups | Source choices, batched History, optional accurate-reading download, provider defaults and isolated Windows tests. |
| J - Language identity | Evidence-based Japanese/Chinese detection and source verdicts across translation, OCR, Dictionary and furigana surfaces. |
| H1 - Reliability | Second-instance show requests, persistent JSONL logs, hidden-root dialog fixes, provider routing and CI guards. |

**Verification:** 1946 passed, one intentional clipboard skip; 1947 collected.
Native layout/hover/cancellation checks, phase mutation checks and bundle/code
verification passed. The user approved the final word-wrap EXE for release.
CI requires at least 1900 tests. Decisions 12-42 preserve the technical rationale.
Linked reading stays experimental/default OFF; remaining evidence gaps are D22.
See [the concise evaluation](docs/linked_reading_evaluation.md) for limits and measurements.

## Earlier completed work

| Task | Version/date | Delivered |
|---|---|---|
| F0-F7 - Furigana Everywhere | 1.9.19, 2026-08-04 to 2026-08-17 | Readings at render time across Japanese surfaces; canonical Copy/selection; settings and packaged fallback dictionary. |
| Rename - Storage identity | 1.9.19, 2026-07-02 | CrossTrans config/cache, startup registry identity and secure-storage naming. |
| G2 - Translate-or-Fix | 1.9.18, 2026-07-01 | Language hotkeys translate or minimally fix grammar through one prompt and a separate cache namespace. |
| G1 - Fix Grammar | 1.9.17, 2026-06-30 | Main-window action, optional hotkey and settings; preserve source language/meaning. |
| R1 - Translation cache | 1.9.16 | Exact-match History cache and deliberate Re-translate. |
| R2 - Custom Prompt | 1.9.16 | Editable popup/freeform request path; preserve source content in main-window custom prompts (R2-bug). |

Historical phase details remain available through Git history and older changelog entries.
