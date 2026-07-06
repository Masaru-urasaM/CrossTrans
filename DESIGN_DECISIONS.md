# CrossTrans — Design Decisions

Significant architecture / library / data-model decisions. Prevents re-proposing rejected
approaches. Newest first.

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
