# CrossTrans — Design Decisions

Significant architecture / library / data-model decisions. Prevents re-proposing rejected
approaches. Newest first.

---

### Decision 8 — Furigana everywhere: annotate at render time, structured segments, fail-safe readings

**Date**: 2026-08-04 (addenda: Phase 1 2026-08-05, Phase 4 2026-08-07, Phase 5 2026-08-10)
**Status**: RESOLVED (Phases 0-5 implemented; Phases 6-7 planned)

**Problem**: Furigana had to appear on **every** surface that displays Japanese, not just the
Quick Translate popup's source block. The shipped design could not get there: readings were
generated *inside the translation pipeline* (`translation.py` `do_translation` /
`do_translate_or_fix` / `redo_translation`), hand-carried as a `{kanji|reading}` string in the
5th queue element, and rendered by exactly one method. The main window had **never** shown
furigana at all — `translation_queue`'s only consumer routes solely to the popup — and clicking
"Open Translator" from a furigana popup silently dropped the readings. The queue could not be
extended either: **arity is the discriminator** in `_check_queue`, so a 7th positional field
falls into the `else` branch, raises `ValueError`, and is swallowed by a bare `except` that
aborts the whole drain loop (the user would see no popup at all).

Measurement also showed the existing feature was wrong in several ways: the ruby covered
okurigana (`取り消し` → `{取り消|とりけ}し`), homographs were misread (`今日は` → こんにち),
`kakasi()` was reconstructed on every call (~175 ms vs ~0.3 ms to convert), literal `{a|b}` in
the source was re-parsed as a real ruby pair, and Tk's `Text.get()` **silently deletes**
embedded ruby content (`日本語を勉強しています` reads back as `をしています`).

**Options considered**:
1. **Extend the pipeline per surface** — Pros: no new module. Cons: every surface needs its own
   plumbing; cannot extend the tuple safely; leaves generation coupled to translation, so
   screenshot/OCR, dictionary and freeform paths stay unannotated forever.
2. **Annotate at render time behind a shared widget** — Pros: any surface that adopts the widget
   gains furigana with zero pipeline change; the queue contract is untouched; one place to fix
   rendering. Cons: needs a plain-text shadow model so nothing reads ruby back out of a widget.
3. **Ask the AI model to return furigana** — Pros: no new dependency, context-aware. Cons: costs
   tokens and latency on every translation, does not work offline, unusable for the input-box
   preview (no API call yet), and quality varies across 15 providers.

**Resolution**: **Option 2.** Generation moves to render time behind two modules —
`src/core/furigana.py` (pure logic) and, from Phase 1, `src/ui/ruby_text.py` (the only place ruby
is drawn). Four invariants govern it:

- **I1 — annotation never alters text.** `''.join(seg.base) == source`, asserted at runtime.
  This kills the injection class structurally instead of by careful escaping.
- **I2 — the model owns the string.** Every read goes through `get_plain()`; no `.get()` on a
  ruby-capable widget, ever. Non-negotiable because `Text.get()` drops embedded windows with
  **zero visible trace** (verified: 0 characters contributed, but 1 index consumed each), so a
  Copy would put kanji-stripped text into the user's document.
- **I3 — editable implies plain.** A widget the user types into never holds ruby; `edit_undo()`
  does not restore destroyed embedded windows.
- **I4 — render-time and idempotent.** The queue tuple shapes stay frozen.

Readings come from a **provider chain**: fugashi/UniDic (the Japanese NLP pack already defined
in `nlp_manager.py`) preferred, pykakasi (bundled, verified working in the frozen EXE) as
fallback. The aligner is **fail-safe** — it returns `None` rather than emit a reading it cannot
map deterministically, because for a learner a wrong reading is worse than a blank one: it is
unfalsifiable at the point of use.

Two refinements were added only after measurement, not by assumption:
- **Counters after digits are suppressed.** `2日` is *futsuka*; the digit holds part of the
  reading and cannot take ruby, so カ over 日 alone invites "ni-ka". This also removes genuine
  errors (`2人` is *futari*, not ni-**nin**).
- **All-kanji compounds keep their compound reading.** UniDic splits `日本語` into 日本
  (proper noun, ニッポン) + 語, giving にっぽんご. Where the fallback dictionary holds a single
  all-kanji entry spanning two or more tokens, its compound reading wins.

**Phase 1 addendum — how ruby height is determined.** A window must be sized before the widget
that fills it exists: the popup is an `overrideredirect` Toplevel whose `geometry()` is set once,
and calling `update_idletasks()` mid-build to measure a realized widget would flash it at the
wrong position first. So height is **derived from font metrics** and a `wrap='char'` simulation
(`ruby row = ruby linespace + base linespace + 2·pad + base descent`, `spacing1 + spacing3`
charged once per *logical* line, not per wrapped row). Predictions match
`Text.count(..., 'ypixels')` exactly on every case measured, which is what exposed the
per-logical-line spacing rule — a per-display-row model over-estimated by 4 px per wrapped row.
Rejected alternative: render off-screen and measure, which doubles the frame construction cost
on the UI thread for content that is already capped at `MAX_ANNOTATE_CHARS`.

**Phase 4 addendum — how the Reading pane learns the text changed.** The pane could have been
refreshed from each site that writes to the input box (the plan named
`_update_translation_with_original` and `_load_history_item`) plus a `<KeyRelease>` binding. A
single debounced `<<Modified>>` binding replaces all of it: Tk raises it for typing, paste of any
kind, drag-and-drop, undo/redo *and* programmatic `insert`/`delete`, so no future write site can
forget to refresh. Its one quirk is that it fires only on a False→True flip, and clearing the flag
inside the handler fires it a second time; the debounce that keeps UI-thread annotation off the
keystroke path also collapses that pair into one render. Measured: focus and caret stay in the
input box across a refresh, and `edit_undo()` still works with the pane following the undo.

The pane is **always present** while furigana is on, rather than appearing when Japanese is
detected (the alternative offered to the user, who chose always-visible): a pane that appears and
disappears moves everything below it and is undiscoverable before the first Japanese input. With
nothing to annotate it shows a dim one-line placeholder — **not** a mirror of the box above, which
would be visual noise *and* would re-insert a pasted 50 000-character document on every edit.

**Phase 5 addendum — annotate the line, then paint the colours.** The dictionary result colour-codes
each looked-up word, and the obvious implementation is to split the line at those words and render
the pieces. It is wrong twice over: the tokenizer then sees isolated fragments (worse readings), and
an **all-kanji fragment cannot be annotated at all** — which is exactly what a looked-up word
usually is (勉強, 東京). So the whole line is annotated in one pass and the colours are painted onto
the resulting segments: a plain run can be split anywhere, and a ruby pair is coloured whole via
`kanji_fg`. The old post-insert `Text.search()` highlighting could not survive this at all — an
embedded window contributes no characters, so an annotated word is unfindable — which is why the
decision moved ahead of insertion into `DictRun`.

The same phase found a **hint that was already in the data**: the result's own
`**Source Language**: Japanese` field. Using it lifts the kanji-only restriction for the fields
written in the source language, and a dictionary lookup is the case where it matters most, since the
looked-up word is typically bare kanji. It is resolved **per `## [Word]` entry** (a multi-word
lookup can mix source languages) and any unrecognized value degrades to no hint. Field 5
(Pronunciation) is excluded from annotation entirely: it holds IPA plus a target-language phonetic,
and hiragana over katakana is redundant and invites misreading — confirmed by the user.

The Phase 0 fail-safe that suppressed ruby for source text containing `\ { } |` was **removed**
in Phase 1: it existed only because the old regex renderer ignored escapes, and `RubyText`
parses through `parse_notation()`, which honors them. Keeping it would have cost every reading
in any sentence containing a pipe.

**Rejected**:
- **Cross-provider disagreement as a wrongness signal** — measured 4/10 sentences disagree, and
  fugashi is *right* in half of those (今日→きょう, 3時→じ) and wrong in the other half. Blanket
  suppression on disagreement would delete ruby from ~40% of sentences for no accuracy gain.
  The all-kanji compound rule is the narrow, targeted version that survives.
- **Ruby inline in the main input box** — would corrupt the three `original_text.get()` reads that
  feed the API (`app.py:955` / `1127` / `1452`: it would receive particle-only text, and
  `find_cached` would then poison history with the stripped key) and the popup-reuse check
  (`app.py:560`: an all-kanji input reads back as `""`, so the popup is destroyed and rebuilt
  empty, losing everything the user typed). Replaced by a read-only Reading pane beneath it
  (implemented in Phase 4); these `get()` calls stay correct precisely because I3 holds there.
- **A "Copy with readings" command** — considered and declined by the user; every Copy/Replace
  emits the plain shadow string only.
- **Ruby in toasts and the history list** — explicit non-goals. Toasts are `tk.Label` (no
  embedded widgets possible) and history rows are 60-character truncations where readings do not
  fit; converting those rows would also break click-to-load, since
  `history_dialog.py` walks `winfo_children()` non-recursively.

**References**: `src/core/furigana.py`, `tests/test_furigana_core.py`,
`src/ui/ruby_text.py`, `tests/test_ruby_text.py`,
`src/core/translation.py` (`_is_japanese_text`, `generate_furigana` delegates),
`CrossTrans.spec:15` (pykakasi data payload), `src/core/nlp_manager.py:324-332` (Japanese pack),
CHANGELOG "Phase 0 — Furigana engine" and "Phase F1 — RubyText primitive".

---

### Decision 7 — Storage-identity rename to CrossTrans: clean rename, no data migration

**Date**: 2026-07-02
**Status**: RESOLVED

**Problem**: The app's internal **storage identity** — the `%APPDATA%` config folder, the
model-config cache folder, the Windows auto-start registry **value name**, and the DPAPI
encryption **entropy salt** — still used the app's original pre-rebrand name while the user-facing
product is `CrossTrans`. The user asked to rename it **everywhere, including the DPAPI entropy**,
leaving **zero** occurrences of the old name in the repo (grep-verified). Changing the DPAPI entropy
makes every previously-stored API key undecryptable.

**Options considered**:
1. **A — Clean rename, no migration (zero-token now)** — Rename everything; existing installs
   re-enter API keys (old-entropy blobs cleared on load) and manually remove the stale auto-start
   entry. Pros: repo has literally zero occurrences of the old name (goal met verbatim); simplest;
   no legacy crypto to carry or retire. Cons: existing users lose stored keys + settings; the
   auto-start orphan needs a one-time manual cleanup.
2. **B — Data-preserving migrate-on-launch + one quarantined legacy shim** — A versioned one-time
   startup migration copies the old `%APPDATA%` folder, re-encrypts keys (old entropy → new), and
   fixes the auto-start value. Requires embedding the old entropy salt (DPAPI cannot decrypt without
   the exact original bytes), so the old name survives in ONE clearly-labeled
   `src/core/legacy_migration.py` excluded from the grep lint. Pros: existing users keep everything
   transparently. Cons: the old-name literal still exists (goal re-scoped to "zero outside the
   shim"); a permanent-ish legacy crypto surface; more code + tests.
3. **C — Transitional two-release re-key** — Ship B in vN, delete the shim in vN+1 → literally-clean
   repo one release later. Cons: version-skippers / `.bak` rollbacks that jump straight to vN+1 never
   run the re-key and lose keys silently; a self-updating `--onefile` EXE cannot guarantee universal
   adoption of vN.

**Why the tension is real (not a design choice)**: Windows DPAPI requires the *exact* entropy salt
used to encrypt to also be supplied to decrypt (Microsoft docs). So any key-preserving migration MUST
embed the old salt bytes → the old name would exist in the repo. Obfuscating the salt to pass the grep
was explicitly **rejected** (dishonest, fragile, hides load-bearing crypto; real credential stores
ship plaintext version markers). Data-preservation and a literally zero-old-name repo are mutually
exclusive on the entropy axis.

**Resolution**: Chose **A (clean rename, zero-token)** per the user (2026-07-02). No migration.
Consequences accepted: existing installs re-enter API keys, and the stale auto-start entry is handled
by a documented **manual** step (Task Manager → Startup apps), NOT a code heuristic — an automatic
literal-free auto-start fix (matching by exe directory) was rejected as unsafe (it can silently delete
unrelated third-party Run entries and runs even for users who never enabled auto-start). Do not
re-propose a migration unless the zero-old-name invariant is relaxed first. A full migrate-on-launch
design (three sub-migrations + five adversarially-found fixes) was produced and archived should the
decision ever be revisited.

**References**: `config.py` (`APP_NAME`), `src/core/crypto.py` (`SecureStorage.ENTROPY`/`DESCRIPTION`),
`src/core/remote_config.py` (`CACHE_DIR`), `src/utils/updates.py` (updater batch registry value),
CHANGELOG.md `[Unreleased]`. **Breaking change** — existing users re-enter API keys.

---

### Decision 6 — Merged Translate-or-Fix on language hotkeys (approach B)

**Date**: 2026-07-01
**Status**: RESOLVED

**Problem**: The dedicated `Win+Alt+G` Fix Grammar hotkey collides with Xbox Game Bar
(confirmed error 1409 on the user's machine); the documented alternative `Win+Alt+F` collides
with Feedback Hub. The user asked for a "more automatic" way to reach grammar-fixing that avoids
the crowded `Win+Alt+*` namespace, with a hard requirement that **both translate and grammar-fix
preserve offensive words verbatim** (no censoring).

**Options considered**:
1. **Change modifier** (`Ctrl+Alt+G`) — free + keeps mnemonic, but still a dedicated hotkey.
2. **Detect language locally, route to existing `translate()`/`fix_grammar()`** — preserves the
   validated no-censor prompt, but local CJK/English detection is unreliable.
3. **One merged AI prompt on the existing language hotkeys** ("approach B") — the model auto-decides
   translate-vs-fix; text already in the hotkey's target language is grammar-fixed.

**Resolution**: Chose **#3 (merged prompt, user-selected)**. New `translate_or_fix()` +
`do_translate_or_fix()` (leaving `translate_text`/`do_translation` untouched → low blast radius).
Sub-decisions:
- **LEAN display** over a mode marker: queue the normal 5-tuple (`is_grammar=False`); the output is a
  real language in both branches so the standard popup is coherent. A first-line mode marker was
  rejected (fights the "no meta-text" rule, weak-model omission → fragile parsing).
- **`'merged'` cache namespace** (new `source_type` param on `find_cached`) to prevent a real
  cross-serve bug: a plain same-language "rephrase" must never be served as a minimal-change fix.
- **No-censor everywhere** (user choice): the rule was added to the plain `translate_text` prompts and
  the screenshot prompt too, not only the merged prompt.
- **`Win+Alt+G` retired to opt-in**: split `fix_grammar_enabled` (button) from the new
  `fix_grammar_hotkey_enabled` (global hotkey, default **False**) so a fresh install never fights
  Game Bar; the button + merged language-hotkey behavior always work.

**Honesty caveat**: uncensored output is best-effort and model-dependent (hard content filters may
refuse/mask); the explicit no-censor instruction can itself raise refusals on some models.

**References**: `src/core/translation.py` (`translate_or_fix`, `do_translate_or_fix`),
`src/core/history.py` (`find_cached` `source_type`), `src/app.py` (`_on_hotkey_translate`),
`src/ui/screenshot_handler.py`, `config.py`, `src/ui/settings/hotkey_tab.py`. See Decision 5.

---

### Decision 5 — Fix Grammar: default hotkey + reuse the translation pipeline

**Date**: 2026-06-30
**Status**: RESOLVED

**Problem**: Add a "Fix Grammar" action (hotkey + main-window button) that corrects grammar
in place. Two sub-decisions: (a) the default hotkey, and (b) how to display the result.

**(a) Default hotkey**
- The requested `Win+Alt+G` (mnemonic G=Grammar) is **Xbox Game Bar's default "Record that"**
  shortcut. It only fires if Game Bar + background recording are enabled, and our
  `RegisterHotKey` self-diagnoses conflicts (error 1409), but it is a real out-of-the-box
  collision for some users.
- **Options**: (1) keep `Win+Alt+G` and rely on rebind/button fallback; (2) ship a
  conflict-free default like `Win+Alt+F` (F=Fix).
- **Resolution**: Shipped **`Win+Alt+G`** — the original spec's hard requirement (mnemonic
  G=Grammar). The Game Bar collision is mitigated, not ignored: `register_hotkeys()` fails
  gracefully on error 1409 if Game Bar holds the combo, the hotkey is fully rebindable in
  Settings, and the main-window "Fix Grammar" button always works. (During review the user
  briefly preferred `Win+Alt+F` to sidestep the conflict; `Win+Alt+F` remains the documented
  conflict-free alternative for anyone who hits the collision and is a one-line default
  change.)

**(b) Result display**
- **Options**: (1) reuse the existing `translation_queue` + Quick Translate popup with an
  `is_grammar` flag; (2) build a separate grammar queue + popup class.
- **Resolution**: Chose **reuse (1)**. Copy/Replace (the "fix in place" actions) and the
  focus-preserving `WS_EX_NOACTIVATE` popup already exist, so reuse is minimal and additive.
  The only risk — the popup's *translation-only* buttons (Re-translate / Dictionary /
  Custom Prompt) assume a real target language — is handled by the `is_grammar` flag hiding
  them. The result is queued as a 6-tuple so `_check_queue` routes it without disturbing the
  4-/5-tuple translation paths. Grammar fixes are **not** written to history (like
  `ask_freeform`), and use a **separate cooldown** (`last_grammar_fix_time`) so a recent
  translation doesn't block a grammar fix.

**References**: `config.py`, `src/core/hotkey.py`, `src/core/translation.py`
(`fix_grammar`, `do_grammar_fix`), `src/app.py` (`_on_hotkey_translate`, `_do_fix_grammar`),
`src/ui/quick_translate.py` (`show` `is_grammar`), `src/ui/settings/hotkey_tab.py`,
`src/ui/tray.py`.

---

### Decision 4 — Custom-prompt results must not poison the plain-translation cache

**Date**: 2026-06-29
**Status**: RESOLVED

**Problem**: `translate_text()` writes every successful result to history, and the R1 cache
(`find_cached`) keys only on `(original, target_lang)`. A main-window custom-prompt
translation would therefore be served as a plain-translation cache hit for the same text —
violating the R1 decision that custom prompts are "never written as a cache match".

**Options considered**:
1. **A — Skip the history write for custom prompts** — Pros: one line. Cons: custom-prompt
   translations vanish from the history viewer (a regression vs. current behavior).
2. **B — Tag + filter by `source_type`** — Store custom-prompt results as
   `source_type='custom'`; `find_cached` only returns `source_type == 'text'`
   (missing → treated as 'text' for legacy entries). Pros: preserves the history viewer,
   fixes the cache, and future-proofs against screenshot/multimodal entries ever being
   served as plain hits. Cons: marginally more code.

**Resolution**: Chose **B**. It strictly dominates A (no history regression). Implemented in
`history.py find_cached()` (filter) and `translation.py translate_text()` (tag). Covered by
`tests/test_translation_cache.py` (`test_ignores_non_text_source_types`,
`test_custom_prompt_result_not_cached_as_plain`). Developer can switch to A later if custom
asks should be excluded from history entirely.

**References**: `src/core/history.py`, `src/core/translation.py`, ROADMAP_DONE.md (R1/R2).

---

### Decision 3 — Quick Translate button bar: single wide row

**Date**: 2026-06-29
**Status**: RESOLVED

**Problem**: R1 + R2 add two buttons (Re-translate, Custom Prompt) to an already 5-element
bar, making 7 actions + close — crowded.

**Options considered**:
1. **Single wide bar** — widen popup minimum 560→670px. Simple, all actions visible.
2. **Two-row bar** — keep width, wrap to a second row. Adds height.
3. **"⋯" overflow menu** — keep narrow, hide less-used actions. More code, less discoverable.

**Resolution**: Developer chose **single wide bar** ("Một hàng, nới rộng") — simplest, lowest
risk. `MIN_WIDTH = 670` in `quick_translate.py`.

**References**: `src/ui/quick_translate.py`.

---

### Decision 2 — Custom Prompt uses a raw freeform path, not the translate wrapper

**Date**: 2026-06-29
**Status**: RESOLVED

**Problem**: The popup "Custom Prompt" mode must send the editable-box content as the prompt.
Should it reuse `translate_text(custom_prompt=...)` or a separate raw path?

**Resolution**: Added `TranslationService.ask_freeform(raw_prompt, target_lang)` — sends the
box content verbatim (no translate wrapper), so it does not depend on the custom_prompt
branch. Freeform asks are one-offs: never written to history, never served from / written to
the R1 cache. The separate R2-bug fix repairs the main-window custom_prompt branch (embeds
source text) independently.

**References**: `src/core/translation.py`, `src/ui/quick_translate.py`, `src/app.py`.

---

### Decision 1 — R1 cache reuses the translation history (no new store)

**Date**: 2026-06-29
**Status**: RESOLVED

**Problem**: Where to store the translation cache for "skip API on 100% identical input"?

**Options considered**:
1. **Dedicated `TranslationCache`** — Pros: clean keying incl. model/provider. Cons: new
   store, new persistence, more surface.
2. **Reuse the existing 100-entry history** — Pros: zero new storage, persists across
   restarts, bounded. Cons: keyed only on `(original, target_lang)` (model ignored, since
   history stores `model_used='Auto'`).

**Resolution**: Chose **#2**. `HistoryManager.find_cached(original, target_lang)`. The
optional cache on/off toggle was intentionally omitted — the "Re-translate" button is the
manual escape hatch; the cache is also inert when history is disabled.

**References**: `src/core/history.py`, `src/core/translation.py`.
