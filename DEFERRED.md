# CrossTrans — Deferred Items

> Work that was identified, deliberately not done, and should not be lost. Review at milestone
> starts: flag anything whose trigger condition is now met, and delete an entry once it ships.
>
> Nothing here is a bug report from a user — these are findings from implementation work that were
> left alone on purpose, mostly under the "touch only what the task requires" rule.

---

### D4 — Signal the running instance instead of scolding the second one

**Found**: 2026-09-07, while fixing the hung "already running" notice (Decision 12).
**Effort**: Medium.

The lock socket on `127.0.0.1:47823` is already `listen()`ing and nobody ever accepts. A second
instance could connect, and the running one could raise its main window — which is what a user
double-clicking the icon actually wants, instead of a dialog telling them to look in the tray.

**Dependency**: an accept loop in `TranslatorApp`'s lifecycle, and a decision about what "show
yourself" should do while a popup is open. **Revisit** when the app's startup path is touched
again for another reason.

---

### D5 — Structured (JSONL) logging with rotation

**Found**: 2026-09-07, while moving the frozen app's log out of the PyInstaller temp directory.
**Effort**: Medium.

Global Rule 10 asks for `{"ts","level","tag","msg"}` JSON Lines with ring-buffer rotation. The log
is still `%(asctime)s [%(levelname)s] %(message)s`, one file per day, now pruned after 14 days
(Decision 13). Changing the format touches every call site's readability and every existing log
file anyone still has.

**Trigger**: the first time a log has to be parsed by a tool rather than read by a person.

---

### D6 — Trial proxy still admits reasoning and agentic models

**Found**: 2026-07-01 review, re-verified 2026-09-07.
**Effort**: Small (worker-side only).

`cloudflare_worker.js` does not exclude qwen3 / gpt-oss / deepseek-r1 / `groq/compound*` from the
trial pool, and `callOpenAIAPI` sends no `reasoning_format`. Exposure is small — Groq is
`FALLBACK_ORDER` #3 and `getProviderModels()` now puts the curated defaults first — and the app
strips `<think>` blocks on every path as of 2026-09-07, so a leak is cosmetic at worst. The
agentic `compound` models can still exceed the 15 s timeout.

**Trigger**: a trial translation comes back visibly wrong or times out.

---

### D7 — `src/constants.py` Groq fallback list is stale

**Found**: 2026-09-07 (compared against the live config).
**Effort**: Small.

17 hardcoded models, 10 of which no longer exist on Groq — including
`distil-whisper-large-v3-en`, a speech model that was never a translation candidate. Only reached
in tier-3 fallback (remote config unreachable *and* no local cache), where it offers the user
models that will fail.

**Trigger**: bundle it with the next change to `constants.py`.

---

### D8 — Dead code: `progress_dialog.py`, `_is_dictionary_query()`

**Found**: 2026-09-07 (0 % coverage, zero references).
**Effort**: Small.

`src/ui/progress_dialog.py` (196 lines) has no importer anywhere in `src/`, `tests/` or
`main.py`. `TranslationService._is_dictionary_query()` has been unused since auto-dictionary
detection was removed. Neither is deleted here because neither was in the way — see the
"touch only what the task requires" rule.

**Trigger**: a cleanup pass, or the next change that lands in either file.

---

### D9 — `test_a_partial_selection_copies_only_that_part` is not hermetic

**Found**: 2026-09-07 — failed once in six full-suite runs, passes in isolation.
**Effort**: Small.

`TestCopySelection` drives a real `<<Copy>>` and reads the **Windows clipboard**, which is a
global resource any other process can take mid-test. The production code is not implicated; the
test is.

**Trigger**: the next time it fails. Fix by retrying on `TclError` or faking the clipboard.

---

### D10 — No CI

**Found**: 2026-09-07. `.github/` holds only `copilot-instructions.md`.
**Effort**: Medium.

593 tests only ever run on one machine, by hand. A `windows-latest` workflow could run them on
every push; the widget tests need a desktop session, and the ones that pop a real dialog
(`TestItReallyExits`) would need checking there.

**Trigger**: a second contributor, or the first regression that reaches a release.
