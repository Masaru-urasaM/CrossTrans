# TODO - Furigana on every Japanese surface, and a Dictionary that knows its languages

> **Status: 🔨 IN PROGRESS** on branch `feature/japanese-language-identity` (from `main` after
> the merge of `h1-health-review`, `f28a276`). **J0 ✅ and J1 ✅ done 2026-10-15** (§6).
> **J2 ✅, J3 ✅, J4 ✅, J5 ✅ and J6 ✅ done 2026-10-15** (`src/core/lang_id.py`, Decision 24; the dictionary
> result window reads the stated source and both languages of an entry; translation prompts
> state the source or ask the model for a `[[SOURCE: ...]]` line, Decision 25).
> **D13-D15 ✅ done 2026-10-15** at the user's request: one Dictionary mode serves both buttons
> (Decision 23), so every later phase changes it once; a failed lookup shows its message; no
> `grab_set()` in its dialogs. Closing D15 surfaced D16 (`UpdateFailedDialog`, DEFERRED.md).
> The user answered Q1-Q10 on 2026-10-15 (§3, answers table first). **Q1 and Q7 were not
> answered with the recommended option and change the design** - see §3.1, which supersedes
> the "default" parts of §5.1 and the old J4 / J10 / J11.
>
> **Next step:** present §3.1 (how "the model decides, the user settles" works on each surface)
> and J2 to the user; get approval; then run the phases one at a time, each through the
> CLAUDE.md Core Workflow: present → user approves → plan → code → verify → bookkeeping (§11).

## Contents

1. [Request and definition of done](#1-request-and-definition-of-done)
2. [Before starting](#2-before-starting)
3. [Questions for the user](#3-questions-for-the-user-answer-before-j1)
4. [Findings - measured 2026-10-15](#4-findings---measured-2026-10-15)
5. [Design](#5-design)
6. [Phases J0-J12](#6-phases-j0-j12)
7. [Manual end-to-end checklist](#7-manual-end-to-end-checklist)
8. [Risks](#8-risks)
9. [Non-goals](#9-non-goals-unchanged)
10. [Adjacent findings - not part of this work](#10-adjacent-findings---not-part-of-this-work)
11. [Bookkeeping](#11-bookkeeping-rules-6-8-9-11)
12. [Appendix - how the measurements were made](#appendix---how-the-measurements-were-made)

---

## 1. Request and definition of done

**Request (2026-10-15, restated in English):**

1. Wherever Japanese appears in CrossTrans, show furigana above the kanji. Find every such place
   and fix it - the Dictionary included.
2. The Dictionary prompt does not distinguish languages: a Japanese headword written only in kanji
   is taken for Chinese. Redesign the prompt so it knows which language it translates **from** and
   **into**.
3. Write everything into TODO.md for the next session.

**Definition of done:**

| # | Criterion | Checked by |
|---|-----------|------------|
| DoD1 | The dictionary prompt names the source and the target language and carries the context sentence. In a Japanese session every kanji-only headword is looked up as Japanese. | Unit tests on the prompt builder; wiring tests for **both** dictionary entry points; real-API check (J1): field 2 = `Japanese` for 10/10 eval words on every provider tested |
| DoD2 | The dictionary result shows readings on every Japanese run of a Japanese-source or Japanese-target lookup - headword, synonyms, antonyms, examples - whatever the model writes in field 2. | Regression fixtures A and B (§4 F2, F3) |
| DoD3 | Kanji-only text that is identifiably Japanese (kana, a Japanese-only glyph, Japanese context, or the user's declared default) gets readings on every surface in §5.4. Text carrying a Chinese-only glyph never does, and a kanji-only *sentence* (。，！？) is never resolved by the default. | `tests/test_lang_id.py` fixtures: **0** Chinese strings resolved as Japanese without a default; `這是我的書。` stays non-Japanese even under a Japanese default |
| DoD4 | Japanese containing kana never triggers "Cannot detect language" in Dictionary mode. | The F4 table as regression tests |
| DoD5 | No regression. | Test count monotonic from **676**; invariants I1-I4 hold; Copy/Replace still emit plain text; `tools/check_test_counts.py` OK |

---

## 2. Before starting

- **Read first:** CLAUDE.md → "Furigana System" and "Dictionary Mode"; DESIGN_DECISIONS.md →
  Decision 8 (+ 9, 10); ROADMAP.md; DEFERRED.md; memory `project_furigana_everywhere.md` (the
  user's 2026-08 scope choices - Q5 reopens two of them).
- **Baseline** (2026-10-15, branch `h1-health-review` @ `d3ee844`, Python 3.14):
  `pytest tests/` → **676 passed, 0 failed, 0 skipped** in 39.6 s; `tools/check_test_counts.py`
  on its JUnit XML → OK.
- **Branch state:** `h1-health-review` is 10 commits ahead of `main` (`bca78c3`) and not merged.
  ROADMAP.md says that work "sits on `main`" - it does not. Settle Q10 before branching.
- **Invariants that must survive every phase** (Decision 8): **I1** annotation never alters text;
  **I2** read ruby widgets with `get_plain()`, never `get()`; **I3** an editable box stays plain;
  **I4** annotate at render time, queue tuple shapes stay frozen (Decision 11 for the pattern used
  instead: a value read off the service, e.g. `last_attribution`).
- **"Blank beats a wrong reading"** still governs. Everything here widens *when we know* text is
  Japanese; nothing guesses a reading. The only deliberate relaxation is the user's own declared
  default for ambiguous kanji (Q1), and it must be visible in Settings and in the log.
- **Tooling:** memory `feedback_edit_unicode_escapes` - Edit fails on lines holding `\uXXXX`
  escapes (`furigana.py`, the new `lang_id.py`); use a line-numbered Python heredoc with asserts.
  Import `src.core` before `config` in standalone scripts (memory
  `project_config_core_circular_import`).

---

## 3. Questions for the user (answered 2026-10-15)

**Answers** (user, 2026-10-15; "as recommended" = the first option below):

| # | Answer |
|---|--------|
| Q1 | **Not the recommendation.** Let the AI model decide what language ambiguous kanji-only text is; when it cannot decide, the user chooses in a window. No Settings default. → §3.1 |
| Q2 | Hiragana reading, long vowels shown as hiragana spells them (べんきょう); **no romaji** (and no IPA). Implemented in J1 |
| Q3 | As recommended: the sentences that contain the headword, capped (~600 characters). Implemented in J1 |
| Q4 | Monolingual (国語辞典-style) entry, **with furigana as usual**. Prompt part implemented in J1; the readings come with J3 |
| Q5 | As recommended: History rows **yes** (J9); Replace-preview original **no**; toasts **no** |
| Q6 | As recommended: screenshot source block yes; store the OCR text in History |
| Q7 | **Not the recommendation: yes** - the ordinary translation prompts also learn the source language. → §3.1 (folded into the new J4) |
| Q8 | As recommended: change both Dictionary-mode copies in lockstep; consolidation → `DEFERRED.md` D13. **Superseded the same day:** the user asked for D13 itself - done, one flow (Decision 23) |
| Q9 | As recommended: real API calls allowed. The eval script is committed as `tools/eval_dictionary_prompt.py` (manual, never in CI) so later phases can re-run it |
| Q10 | As recommended: `h1-health-review` merged into `main` (`f28a276`, `--no-ff`, not pushed); branch `feature/japanese-language-identity` |

The question texts below are kept as the record of the options weighed.

### Q1 - What is kanji-only text with no other clue?

"No other clue" = no kana, no Japanese-only or Chinese-only glyph, no Japanese context. Measured:
**22 of 54** kanji-only Japanese words sampled land here (勉強, 手紙, 東京大学, 大丈夫, 株式会社,
電源設定, 時間, 問題, 学生, 先生 ...). Today they stay plain everywhere a caller does not already
know the language - which is why 勉強 selected on its own never gets a reading in the popup.

- **(a) Recommended - a Settings choice:** "Text written only in kanji (no kana) is:
  **Auto** / Japanese / Chinese / Unknown (no readings)", default **Auto**.
  Auto = Japanese when the machine shows a Japanese signal and no Chinese one, Chinese in the
  reverse case, otherwise Unknown. Signals: UI language, user locale, system locale, installed
  keyboard layouts.
  Measured on the developer PC: UI language `0x0409` (English), user locale `0x0409`,
  **system locale `0x0411` (Japanese, ACP 932)**, keyboard layouts `0x0409` / **`0x0411`** /
  `0x042A` → Auto = Japanese. The UI language *alone* would have said "not Japanese", which is why
  Auto must read several signals.
  - Pros: deterministic, offline, overridable; meets "everywhere" for this user.
  - Cons: under a Japanese default, an ambiguous kanji-only Chinese **word** gets Japanese
    readings - only 1 of 19 Traditional samples and 17 of 20 Simplified samples carried a
    distinguishing glyph (F9). Sentences are protected by the punctuation rule in §5.1, and the
    candidate Jōyō/Jinmeiyō gate narrows the rest. The Auto rule is an educated guess and must
    log its inputs.
- **(b) Keep today's rule** (no readings without proof). Pros: never a wrong reading on Chinese.
  Cons: does not meet the request.
- **(c) Always Japanese.** Pros: simplest. Cons: wrong readings on ambiguous Chinese for every
  user; contradicts "blank beats a wrong reading".

### Q2 - Pronunciation (field 5) for a Japanese headword

Today the prompt asks for "/IPA/ plus a target-language phonetic". A model that has taken 勉強 for
Chinese can be expected to answer with pinyin (`/miǎn qiáng/` in Fixture A) - not yet observed on a
real API; J0 measures it.

- **(a) Recommended - hiragana + romaji:** `べんきょう (benkyō)`. Field 5 is never annotated by the
  renderer, so the reading is printed as text - exactly what a learner looks for.
- **(b)** (a) + IPA.
- **(c)** (a) + pitch accent (`べんきょう [0]`). Cons: models are unreliable at pitch accent, and a
  wrong accent is a wrong reading by the project's own rule.

For other sources: Chinese → pinyin with tone marks; Korean → Revised Romanization; everything
else unchanged (IPA + target-language phonetic).

### Q3 - Context sent with a lookup

- **(a) Recommended:** the sentence(s) of the analysed text that contain each headword,
  de-duplicated, capped at ~600 characters (educated guess - measure tokens in J1). Custom-box
  phrases that do not occur in the text get none.
- **(b) None** - rely on the explicit source language only. Cons: the right *sense* still depends
  on the model's guess (結構 has several Japanese senses).
- **(c) The whole analysed text.** Cons: can be thousands of characters per lookup - tokens,
  latency, and trial-mode quota.

### Q4 - Source language = target language (e.g. Japanese text, Win+Alt+J, then Dictionary)

- **(a) Recommended:** a monolingual entry (国語辞典 style): definition in the same language,
  field 1 = a plainer equivalent, examples followed by a simpler paraphrase.
- **(b)** Leave it undefined (today).

### Q5 - Reopen surfaces declined in 2026-08?

The F0-F7 work made toasts and the History list explicit non-goals, with the user's agreement.
"Every place" may now include them:

| Surface | Recommendation | Why |
|---------|----------------|-----|
| History list rows | **Yes**, as its own phase J9 | Japanese is shown there in every entry; feasible with `RubyRow`; needs a measured build-time budget for 100 entries and click-to-load on every part |
| Replace preview, struck-through original | No (optional J10) | It is the text being discarded; needs a per-insert overstrike font on the ruby labels |
| Toasts ("Looking up 2 word(s): 勉強, 手紙") | No (optional J10) | A 2-3 s notice; the same words appear with readings seconds later in the result window |
| Language list (日本語), Combobox, menus, title bars, tray, messageboxes | Stay non-goals | Tk cannot embed widgets there |

### Q6 - Screenshot OCR

- **Recommended: yes** - show the OCR'd Japanese with readings above the translation, like the
  hotkey popup does (only when the OCR text resolves to Japanese).
- Also: store the OCR text in History instead of the literal `"[Screenshot OCR]"`? Recommended
  yes - it makes the entry useful (and J9 can annotate it) - but it changes History content.

### Q7 - Make the *translation* prompts source-aware too ("Translate from Japanese to ...")?

The same ambiguity affects plain translation: 手紙 sent alone could come back with its Chinese
sense ("toilet paper"). Not measured.

- **(a) Recommended - not in this work.** Record it in DEFERRED.md and decide after J1's
  measurements show how much the explicit source language helps the dictionary.
- **(b)** Yes, only when the resolver is certain or the user's default applies. Cons: a wrong
  resolution then misleads the model *actively*; it interacts with the merged translate-or-fix
  decision rule; cached entries made before and after would differ.

### Q8 - Dictionary mode exists twice

`src/ui/dictionary_popup.py` (main window) and `src/ui/quick_translate.py:1298-1680` (popup)
duplicate the detection, the language dialog and the `WordButtonFrame` wiring.

- **(a) Recommended:** change both in lockstep, with tests that drive both paths; record the
  consolidation in DEFERRED.md (surgical, Rule 3).
- **(b)** Consolidate first. Cons: a ~400-line UI refactor before any user-visible change.

### Q9 - May the next session make real API calls for evaluation?

About 10 calls per provider per run (J0 "before", J1 "after"). Recommended: yes, on the user's
configured provider(s) plus the trial proxy - `llama-3.3-70b` is probably the weakest
instruction-follower of the set (an assumption), so it is the useful worst case. Also decide: commit the eval script under `tools/` (manual,
never run in CI) or keep it in the session scratchpad.

### Q10 - Where to branch from

- **(a) Recommended:** merge `h1-health-review` into `main` (676/676 green) and branch
  `feature/japanese-language-identity` from `main`.
- **(b)** Branch from `h1-health-review`'s tip and merge both later.

### 3.1 What the answers change (Q1, Q7) - proposed, needs the user's approval before J4

**Q1 in one line: evidence first, then the model, then the user.** A text's language is
resolved in this order; the first step that answers wins:

1. **known** - the caller is authoritative: a translation's *target* language for its own output;
   a language the user picked in a dialog.
2. **evidence in the text** - kana → Japanese; a Japanese-only glyph → Japanese; a glyph that
   cannot be Japanese → Chinese (§5.1, F9; offline, certain).
3. **evidence in the context** - the larger text the fragment came from, same rules.
4. **the model's verdict** - the language a model call *reported* for this exact text (below).
   Evidence beats it: kana in the text overrides a model that said "Chinese".
5. **unknown** - a surface that *needs* a language asks the user (a window); a passive surface
   (Reading pane, History rows, word chips) never opens a window and stays plain.

This replaces §5.1 step 4 (the user's declared default), the old J4 (Settings control, Windows
signals) and Q1 option (a). **Do not re-propose a Settings default** - the user chose against it.

**Where the model's verdict comes from** (one mechanism per kind of call, no extra calls where a
call is already being made):

| Call | How the model reports the language |
|------|-------------------------------------|
| Dictionary lookup | Already in place (J1): field 2. Unknown source → the prompt asks the model to decide |
| Translation / translate-or-fix (Q7) | Evidence known → the prompt states it ("The text is Japanese"). Ambiguous kanji-only → the prompt asks the model to decide and to begin its answer with one marker line, e.g. `[[SOURCE: Japanese]]` / `Chinese` / `Unknown`; the app strips the line before display, cache and history, and keeps the verdict as `TranslationService.last_source_language` (the `last_attribution` pattern, Decision 11). Other scripts: prompt unchanged |
| Screenshot OCR | The vision prompt gains a `===SOURCE LANGUAGE===` section next to `===ORIGINAL===` |
| Dictionary opened from the main window on untranslated kanji-only input | The verdict of the last translation of that exact text if there is one; otherwise one short identification call ("Japanese, Chinese or Unknown?") - or skip straight to the dialog (user to choose) |

**Where the user's window appears** - only where the app cannot continue without a language:
- **Dictionary mode**, kanji-only text with no evidence and no verdict (or verdict `Unknown`):
  the existing "Select Source Language" dialog, worded for the case ("Kanji-only text - Japanese
  or Chinese?") with those two first.
- **Quick-translate popup**, when the translation reported `Unknown`: a small chooser
  ("Japanese / Chinese?"). On a choice: re-translate with the stated source (one more call) and
  show the source block with readings if Japanese. Alternative to decide in J6: keep the
  translation and only add the readings (no extra call).

**Q7 consequences:** the merged translate-or-fix prompt and the plain translation prompt change
for CJK text only; cached entries made before and after differ (the cache key does not include
the source language - decide in J4 whether to namespace it); `HistoryManager` stores the model's
verdict as `source_lang` when there is one. Marker compliance must be **measured per provider
before shipping** (extend `tools/eval_dictionary_prompt.py` with a translate mode); a missing
marker is treated as "no verdict", never as an error.

**Data the J4/J5 design must face** (J1 eval, 2026-10-15): with a headword alone and no
context, gpt-oss-120b picked the Chinese sense for 4 of the 10 false friends (汽車 工作 結構 床).
"The model decides" cannot recover those from the selection alone - only context or the user can.
So J4's marker must let the model say `Unknown`, and J4 must measure **how often it does** for
these words: if it almost never admits doubt, the user's window will rarely appear and those
words stay wrong; if it often does, the window appears often. Present those numbers to the user
before J5.

**Revised phase list** (details in §6): J2 lang_id core (evidence only, no default) → J3
dictionary result rendering → **J4 model-reported source language (Q1 + Q7, replaces old J4 and
J11)** → J5 one detector + Dictionary opens in the right language + the user's window → J6 popup
→ J7 main window → J8 screenshot → J9 History rows → J12 docs. **J10 dropped** (Q5: no).

---

## 4. Findings - measured 2026-10-15

**No AI model was called in the session that wrote this file.** Everything marked "measured" ran
the project's real code locally; F2 and F3 feed **hand-written** model answers (Fixtures A, B)
through the real renderer. What real models answer to the current prompt is measured in J0.

### F1 - The dictionary prompt is never told the source language, nor the context

- `src/core/translation.py:317` `dictionary_lookup(text, target_language)`. The prompt
  (`:343-376`) carries `**Target Language**` only and asks the model to fill
  `2. **Source Language**: detected language` from the bare word.
- **Both dictionary windows know the language and drop it:**
  - Main window: `src/ui/dictionary_popup.py:345` `_open_with_language(original, language)` even
    titles the window `Dictionary ({language} → {target})` (`:362-368`), but `on_lookup`
    (`:445-449`) and `on_no_selection` (`:451-456`) call `_do_lookup(words, target_language)`
    → `:513` `dictionary_lookup(words, target_lang)`.
  - Popup: `src/ui/quick_translate.py:1516` `_open_dictionary_with_language(text, language, ...)`;
    `on_lookup` (`:1640-1645`) and `on_no_selection` (`:1647-1653`) call
    `self._on_dictionary_lookup(all_words, self._current_target_lang)` →
    `src/app.py:491` `_on_quick_translate_dictionary_lookup(words, target_lang)` → `:511`.
- **No context:** the sentence the words came from is never sent. A kanji-only headword is
  genuinely ambiguous without it, and many are false friends whose meaning differs (the J0/J1
  eval list, §6 J0).
- **No test covers the prompt** - `grep -rn dictionary_lookup tests/*.py` → nothing.

### F2 - A wrong "Source Language" switches the readings off (renderer measured)

`split_dictionary_text()` (`src/ui/dictionary_render.py:241`) takes the source-language hint only
from the model's own field 2 (`source_language_hint()`, `:95-113`). One hand-written 勉強 entry
(Fixture A), rendered twice by the real renderer with only field 2 changed (target English):

| Model's field 2 | `## [勉強]` | Synonyms 学習, 勉学 | Example 勉強会 | Example with kana |
|-----------------|-------------|---------------------|----------------|-------------------|
| `Chinese` | plain | plain | plain | annotated |
| `Japanese` | 勉強[べんきょう] | 学習[がくしゅう], 勉学[べんがく] | 勉強会[べんきょうかい] | annotated |

A model that decides "Chinese" will presumably also write Chinese *content* - pinyin, Chinese
senses, Chinese examples - consistent with the user's report that kanji-only Japanese headwords
are treated as Chinese. Expected, not yet observed on a real API (J0).
→ **Fixture A** (regression test in J3).

### F3 - Kanji-only target-language text on mixed lines is never annotated (renderer measured)

Hand-written English → Japanese entry for "study" (Fixture B), real renderer: fields 1 and 3 get
readings (they are target fields), but
`learn → 学習, research → 研究` (Synonyms), `ignore → 無視` (Antonyms) and
`Study hard → 一生懸命勉強` (Examples) stay **plain**. `_line_policy()` (`:116-131`) gives each line
one hint - the *source* language (English) - while these lines are `source → target` pairs.
→ **Fixture B** (regression test in J3).

### F4 - `nlp_manager.detect_language()` misreads Japanese both ways (measured)

`src/core/nlp_manager.py:1340-1429`. The CJK branch (`:1397-1404`) forces
`Chinese (Simplified)` whenever there is no kana; confidence = largest character count / total.
Callers: `dictionary_popup.py:136` and `quick_translate.py:1319` only. Threshold 0.7.

| Input | Result | Conf. | What the user gets |
|-------|--------|-------|--------------------|
| 勉強, 手紙, 東京大学, 大丈夫, 株式会社, 電源設定 | Chinese (Simplified) | 1.00 | Dictionary opens as Chinese, or "Chinese pack not installed" |
| 経済 (Japanese-only glyphs) | Chinese (Simplified) | 1.00 | same |
| 私は学生です。 | Japanese | 0.63 | "Cannot detect language" dialog |
| 「勉強」という言葉 | Japanese | 0.64 | dialog |
| Pythonで開発する | Japanese | 0.47 | dialog |
| 這是我的書。 (Traditional) | Chinese (Simplified) | 0.83 | wrong variant |
| 友達に手紙を書きました。, 毎日日本語を勉強しています。 | Japanese | 0.70 | opens - but exactly on the threshold |

Kana is proof of Japanese; it must never produce a dialog, and an ordinary sentence must not sit on
the threshold.

### F5 - Three detectors, three answers, three spellings of Chinese

| Detector | Kanji-only text | Used by |
|----------|-----------------|---------|
| `furigana.should_annotate()` (`src/core/furigana.py:90-111`) | not Japanese unless hinted | every ruby surface |
| `nlp_manager.detect_language()` | `Chinese (Simplified)` | Dictionary mode language |
| `HistoryManager._detect_language()` (`src/core/history.py:114-157`) | `Chinese` | History label "source → target" |

`src/constants.py` `LANGUAGES` spells `Chinese Simplified` / `Chinese Traditional` (the names
sent to prompts), nlp_manager `Chinese (Simplified)` / `Chinese (Traditional)`, history `Chinese`.
A kanji-only Japanese entry is labelled "Chinese → ..." in History.

### F6 - Kanji-only Japanese gets no readings wherever no authoritative hint exists

The engine is ready; only the hint is missing (measured):
`generate_notation('勉強')` → `None`; `generate_notation('勉強', 'Japanese')` → `{勉強|べんきょう}`;
`generate_notation('東京大学', 'Japanese')` → `{東京大学|とうきょうだいがく}`.

| Surface | Code | Hint today | Effect |
|---------|------|------------|--------|
| Popup source block | `translation.py:619-624` (`do_translate_or_fix`), `:675-679` (`redo_translation`) | none | `None` → the block is **not shown at all** for kanji-only input |
| Reading pane | `app.py:1428-1431` | none (deliberate comment) | placeholder instead of readings |
| Popup grammar result | `quick_translate.py:847-856` `_ruby_hint()` → `None` for grammar | none | kanji-only output plain |
| Main-window grammar result | `app.py:1184-1192` | none | same |
| Word chips / custom tags | `dictionary_mode.py:355-366`, `custom_word_boxes.py:214-222` | Dictionary mode language | plain whenever F4 misdetects the mode |

### F7 - Screenshot OCR never shows the Japanese it read

`src/ui/screenshot_handler.py:218` calls `on_show_quick_translate(original, translated,
target_lang, trial_info)` without `furigana_text`, so a Japanese screenshot shows only the
translation; the hotkey path shows the source with readings above it. History stores the literal
`"[Screenshot OCR]"` as the original (`:221-222`).

### F8 - Surfaces F0-F7 left plain on purpose

See Q5. The History rows are `ttk.Label`s with a 57-character cut
(`src/ui/history_dialog.py:277-285`), and click-to-load walks `frame.winfo_children()`
non-recursively (`:288-290`) - a `RubyRow` there needs every part bound explicitly.

### F9 - Glyph evidence is real but partial (prototype, measured)

Classifying each kanji by membership in Japanese / Simplified / Traditional character sets, with
the §5.1 rule - Japanese-only = in CP932 but in neither GB2312 nor Big5; Chinese = not in JIS X
0213 (prototype in the Appendix):

| Sample | Resolved | Ambiguous | Wrong |
|--------|----------|-----------|-------|
| 54 kanji-only Japanese words | 32 Japanese by glyph (59%) | 22 | **0** called Chinese |
| 3 Japanese words holding 2010 Jōyō kanji (剝離, 頰骨, 補塡) | 0 | 3 | **0** called Chinese |
| 20 Simplified Chinese words | 17 Chinese | 3 (你好, 没有, 今天天气很好) | **0** called Japanese |
| 19 Traditional Chinese words | 1 Chinese (說話) | 18 | **0** called Japanese |

The ambiguous Chinese items are where a Japanese *default* (Q1) would go wrong. `今天天气很好`
has no sentence punctuation, so the §5.1 sentence rule does not catch it; the Jōyō/Jinmeiyō gate
proposed in §5.1 would, if 气 and 很 are absent from both lists as expected - confirm against the
list in J2.

Japanese-only glyphs are shinjitai and kokuji (気 楽 売 読 図 駅 経 済 発 単 変 関 込 ...);
Chinese-only are simplified forms (们 这 说 习 时 问 电 飞 经 银 ...). Traditional forms are mostly
also Japanese kyūjitai in JIS, which is why Traditional text is mostly ambiguous.

**Character-set traps found while measuring** - do not repeat them:
- **CP932 is the wrong "Japanese set" for Chinese evidence.** 剝 頰 塡 (2010 Jōyō kanji) are
  outside CP932 but inside JIS X 0213 and Big5: a CP932 test would call a Japanese word holding
  them Traditional Chinese. Use JIS X 0213 (`euc_jis_2004`) for "can be Japanese".
- **GBK is the wrong "Chinese set"** - it covers almost every CJK ideograph, Traditional included.
  Use GB2312 for "Simplified" and Big5 for "Traditional".
- Set sizes over the 27,584 BMP code points U+4E00-9FFF and U+3400-4DBF: CP932 6,682; JIS X 0213
  12,724; GB2312 6,763; Big5 13,061. Japanese-only (CP932 minus GB2312 and Big5) **959**;
  not-in-JIS-X-0213 Simplified **2,278**, Traditional **3,618**. Building all sets eagerly takes
  **~90 ms** - never at import time on the UI thread.
- A static scan of `tests/*.py` found exactly one test string with a non-JIS kanji (汉字,
  `test_dictionary_ruby.py:164-165`), and it already expects plain text - the §5.1 guard will not
  break it.
- **Big5 is the wrong Traditional set for "Japanese-only"** (found in J2): Hong Kong's standard
  forms 衆 裏 綫 衞 啓 峯 are outside Big5 and inside CP932, so 12 of 13 Hong Kong strings came out
  Japanese. Exclude Big5-HKSCS (Decision 24) - which costs the Japanese forms HKSCS also carries
  (駅 発 円 県 込).

---

## 5. Design

### 5.1 Language identity - one resolver: `src/core/lang_id.py` (new, pure logic, no Tk)

```python
JAPANESE = "Japanese"
CHINESE_SIMPLIFIED = "Chinese (Simplified)"     # nlp_manager's spelling = canonical
CHINESE_TRADITIONAL = "Chinese (Traditional)"

class Verdict(NamedTuple):
    language: Optional[str]   # canonical name, or None = unknown
    evidence: str             # 'known' | 'kana' | 'jp-glyph' | 'zh-glyph' | 'context' | 'default' | 'none'

def normalize_language(name) -> Optional[str]
def han_evidence(text) -> Optional[str]                 # JAPANESE / CHINESE_* / None
def resolve(text, *, known=None, context=None, default=None) -> Verdict
def ruby_hint(*languages) -> Optional[str]              # the "language set" rule below
def output_hint(source, target) -> Optional[str]
def environment_default() -> Optional[str]              # J4
def user_default(config) -> Optional[str]               # J4: 'auto' resolved through environment_default()
```

**`resolve()` precedence:**

1. `known` - the caller is authoritative (a translation's target language for its output; a
   language the user picked in the Dictionary dialog). Returned normalized.
2. Evidence in `text`:
   - kana (U+3040-30FF, which includes ー and ・) or 々 / 〆 / ヶ → **Japanese**, certain;
   - otherwise per kanji: a Japanese-only glyph → Japanese; a glyph that cannot be Japanese
     (not in JIS X 0213) → Chinese, Simplified when in GB2312, else Traditional;
   - both kinds present, no kana → `None` (conflict).
3. Evidence in `context` (the larger text the fragment came from) - same rules.
4. `default` (Q1) - **only for word-like text**: no sentence punctuation (。，！？；), at most
   ~12 characters (educated guess; tune against the fixtures). A kanji-only sentence is far more
   likely Chinese than Japanese, which almost always carries kana. Acceptance: `這是我的書。`
   never resolves Japanese, even under a Japanese default.
   **Candidate gate, decide in J2 by measurement:** apply the default only when every kanji is a
   Jōyō or Jinmeiyō kanji (2,136 + 863 - verify the current Jinmeiyō count against the source
   chosen). The default is a bet that ambiguous text is everyday
   Japanese, and everyday Japanese written in kanji uses those characters. It should catch
   `今天天气很好` (气, 很) and `我們` (們), which the sentence rule cannot - expected, to be confirmed
   against the list. Cost: Japanese words
   with rarer kanji (林檎, 薔薇, 蜘蛛) lose the default and stay plain - the safe direction, but
   exactly the words a learner may want read. Needs a character list as data: the official
   tables, or KANJIDIC2's grade field (CC BY-SA 4.0 - attribution required); ask the user which.
5. `None`.

**`should_annotate()` guard** (`furigana.py:90-111`): unchanged when the text has kana; without
kana it needs `lang_hint == "Japanese"` **and** no Chinese-only glyph. A Japanese hint never
overrides positive Chinese evidence. (Kana-bearing text with a Chinese-only glyph, such as a
Chinese name inside a Japanese sentence, keeps today's behaviour - kana is the stronger evidence.
What the reading providers emit for such a glyph has not been measured; add a test in J5.)

**Language-set rule** - how a surface showing text in *two* languages picks its hint:

```
ruby_hint(*langs)         = 'Japanese' if Japanese ∈ langs and no Chinese variant ∈ langs, else None
output_hint(source, tgt)  = 'Japanese' if tgt is Japanese, else ruby_hint(source, tgt)
```

The prompts restrict a result to its source and target language; if the only one of the two that
is written in kanji is Japanese, every kanji run in the result is Japanese. A Japanese → Chinese or
Chinese → Japanese pair needs per-part hints instead (§5.3).

**Normalization table** (tests pin it): `Japanese`, `japanese`, `ja`, `日本語`, `nihongo` →
Japanese; `Chinese`, `Chinese Simplified`, `Chinese (Simplified)`, `zh-CN`, `中文简体` → Chinese
(Simplified); `Chinese Traditional`, `Chinese (Traditional)`, `zh-TW`, `中文繁體` → Chinese
(Traditional). Prompts keep the names the user sees.

**Logging (Rule 10):** tag `[LangID]`. DEBUG for every verdict that came from `context` or
`default`; INFO once per process for `environment_default()` with its inputs, e.g.
`ui=0x0409 user=0x0409 system=0x0411 layouts=[0x409,0x411,0x42a] -> Japanese`. A wrong default
must be diagnosable from the log alone.

### 5.2 Dictionary prompt v2 (J1)

**Signature** (keyword defaults keep old callers working):

```python
def build_dictionary_prompt(words, target_language, source_language=None, context=None) -> str  # pure
def dictionary_lookup(self, text, target_language, source_language=None, context=None) -> str
def extract_context(text, words, max_chars=600) -> str                                           # pure
```

**Draft prompt** - the final wording is reviewed with the user in J1:

```text
You are a professional bilingual dictionary.

SOURCE LANGUAGE: {source}
TARGET LANGUAGE: {target}

The headwords below were selected from this {source} text. Use it only to pick the right sense;
do not translate it.
===CONTEXT===
{context}
===END OF CONTEXT===

HEADWORDS (look up each one as a {source} word):
1. 勉強
2. 手紙

LANGUAGE RULES (most important - follow them exactly):
1. Every headword is {source}. A headword written only in kanji/hanzi is still {source}: never
   treat it as Chinese or Japanese because of its script. Give its {source} meaning - the same
   characters can mean something else in another language (Japanese 手紙 means "letter", not the
   Chinese "toilet paper").
2. Only exception: a headword that is clearly another language (for example a Latin-script word
   the user typed). Identify its real language and write that in field 2.
3. Field 2 is exactly "{source}" unless rule 2 applies.
4. Translation, Definition and Word Type are written in {target}, and so is everything after "→".
5. Synonyms, Antonyms and the sentence before "→" in Examples are written in {source}.

OUTPUT FORMAT - one entry per headword, in the order given:

## [headword exactly as given]

1. **Translation**: {target} translation (REQUIRED)
2. **Source Language**: {source}
3. **Definition**: explanation in {target} (REQUIRED)
4. **Word Type**: noun/verb/adjective/adverb/etc., in {target}
5. **Pronunciation**: {pronunciation rule}
6. **Synonyms**: synonym → {target} translation, ... (write "None" if there are none)
7. **Antonyms**: antonym → {target} translation, ... (write "None" if there are none)
8. **Examples**:
   - {source} sentence → {target} translation
   - {source} sentence → {target} translation

---

CRITICAL:
- Start every entry with the "## [headword]" line exactly as shown - it is used to highlight it.
- Fill in every field; never leave a field blank after the colon.
- Provide an entry for all {n} headword(s).
```

**Variants:**

| Case | Change |
|------|--------|
| Pronunciation rule | Japanese: "hiragana reading, then romaji in parentheses - e.g. べんきょう (benkyō)" (Q2). Chinese: "pinyin with tone marks - e.g. xuéxí". Korean: "Revised Romanization". Other: today's "/IPA/, plus a {target} phonetic spelling" with its two examples |
| Source unknown (`None`, no default) | "SOURCE LANGUAGE: not given - decide it for each headword from the context. A headword written only in kanji/hanzi is Japanese when the context is Japanese (it contains kana) and Chinese when the context is Chinese. Write the language you decided in field 2." |
| Source = target (Q4) | Monolingual rules: Definition in {source}; field 1 a plainer {source} equivalent; after "→" in Examples a simpler paraphrase |
| No context (word not in the text, Q3 = b) | The CONTEXT block is omitted entirely |

**Constraints:**
- Keep the eight numbered labels **exactly**. `_align_dictionary_text()`, `FIELD_RE`,
  `TARGET_LANGUAGE_FIELDS = (1, 3)`, `PRONUNCIATION_FIELD = 5` and `SOURCE_LANGUAGE_LABELS`
  depend on them, and `tests/test_dictionary_ruby.py` (50 tests) exercises them.
- If Word Type is written in the target language, add field 4 to `TARGET_LANGUAGE_FIELDS`
  (`dictionary_render.py:46-47`) in J3 and check the existing tests.
- The context is user text inside delimiters, like every other prompt in `translation.py`.
- `extract_context()`: split the analysed text after `。！？!?` and at newlines (and after
  `. ` for Latin text), keep sentences that contain a headword, de-duplicate, keep text order,
  cap at `max_chars`. Pure, unit-tested.
- Log `[Dictionary] lookup n=<words> source=<lang> target=<lang> context_chars=<n>` - counts
  only, no user text.

### 5.3 Dictionary result rendering (J3)

- `split_dictionary_text(display_text, target_lang, looked_up_words, colors, annotate=True,
  source_lang=None)`; `show_dictionary_result(..., source_lang=None)`.
- **The caller's source language wins.** The model's field 2 is the fallback only when the caller
  passes `None` - which keeps today's behaviour, and the existing tests, intact.
- **Common case, no splitting:** when `ruby_hint(source, target) == 'Japanese'` (Japanese paired
  with any non-Chinese language) the whole result takes the Japanese hint.
- **Japanese ↔ Chinese pairs:** fields 6, 7, 8 and example lines are split at "→" - left of an
  arrow takes the source hint, right takes the target hint. In `a → x, b → y` the inner pieces
  split at the **last** ", ". Unparseable lines fall back to the line's own hint.
- Title: `Dictionary - {source} → {target}` when the source is known.
- `overhead_px()` already measures the runs, so the window grows with the new readings - assert
  it in a test rather than change it.

### 5.4 Surface map - where every surface gets its hint (after this work)

| # | Surface | Code today | Hint today | Hint after | Phase |
|---|---------|-----------|------------|------------|-------|
| 1 | Popup source block | `translation.py:619-624`, `:675-679` | none (no block for kanji-only) | `resolve(selection, default=…)` | J6 |
| 2 | Popup translation box | `quick_translate.py:533-537` (height), `:817-819` | target | `output_hint(resolve(original), target)` | J6 |
| 3 | Popup, grammar result | `quick_translate.py:847-856` | none | `resolve(original)` - a fix keeps the language | J6 |
| 4 | Replace preview, translated half | `quick_translate.py:1127-1130`, `:1181-1185` | as 2/3 | as 2/3 | J6 |
| 5 | Replace preview, original half | `quick_translate.py:1125` | plain, struck through | only if Q5 | J10 |
| 6 | Main-window output | `app.py:1230-1232`, `:1322-1323` | target | `output_hint(resolve(input), target)` | J7 |
| 7 | Main-window grammar result | `app.py:1187-1192` | none | `resolve(input)` | J7 |
| 8 | Reading pane | `app.py:1428-1431` | none | `resolve(input, default=…)` | J7 |
| 9 | Expanded view | `expanded_window.py:156-157`, opened from `app.py:1476` | target | `output_hint(source, target)` - pass the source in | J7 |
| 10 | Dictionary word chips | `dictionary_mode.py:355-366` | mode language | mode language, correct once J5 fixes detection | J5 |
| 11 | Custom-box tags | `custom_word_boxes.py:214-222` | mode language | same, plus the §5.1 guard | J5 |
| 12 | Dictionary result window | `dictionary_render.py:241-281` | target / model's field 2 | §5.3 | J3 |
| 13 | Screenshot popup | `screenshot_handler.py:218` | no source block | source block with `resolve(ocr_text)` | J8 |
| 14 | History rows | `history_dialog.py:277-290` | plain labels | `RubyRow`; the entry's own languages | J9 |
| 15 | Toasts | `app.py:506`, `dictionary_popup.py:507` | plain | unchanged unless Q5 | J10 |
| - | Editable boxes, Listbox, Combobox, menus, title bars, tray, messageboxes | - | - | non-goal (§9) | - |

---

## 6. Phases J0-J12

Every phase: **one phase per approval**; tests written with it; full suite green; each new test
**mutation-checked** (revert the production line it guards, confirm the test fails, restore) - the
project's standing practice; CHANGELOG/ROADMAP/MEMORY updated in the same commit (§11).
Line and test counts below are **estimates**.

### J0 - Prerequisites and the "before" measurement (no production code)  ✅ Done (2026-10-15)

> **Result:** answers recorded (§3); `h1-health-review` merged into `main` (`f28a276`); branch
> `feature/japanese-language-identity`; baseline **676 passed, 0 skipped** (38 s,
> `logs/junit_j0_baseline.xml`); `tools/eval_dictionary_prompt.py` committed; "before" written to
> `logs/eval/dictionary_before.jsonl` - **7/10 Japanese on all three providers** (Google
> gemini-2.5-flash, Groq gpt-oss-120b, trial llama-3.3-70b), the same three words read as Chinese
> by all three: 汽車 "car", 工作 "work", 床 "bed". Gemini's free tier rate-limited three calls,
> re-run at a 12 s delay. The trial proxy works (it is not the dead direct-Cerebras model).

1. Get answers to Q1-Q10. Add a ROADMAP.md row pointing at this file (with approval).
2. Settle Q10; create the branch.
3. `pytest tests/ --junitxml=logs/junit_baseline.xml` → expect 676 passed; record any drift.
4. If Q9 = yes - `tools/eval_dictionary_prompt.py` (or a scratchpad script): for each word below,
   call the current `TranslationService.dictionary_lookup([word], 'English')`, parse fields 1, 2,
   5 and write JSONL `{ts, provider, model, word, field2, translation, pronunciation}` to
   `logs/eval/dictionary_before.jsonl` (`logs/` is git-ignored).

**Eval list** - kanji-only headwords whose Japanese and Chinese senses differ:

| Headword | Japanese sense | Chinese sense | Japanese context (used from J1 on) |
|----------|----------------|---------------|------------------------------------|
| 手紙 | letter | toilet paper | 友達に手紙を書きました。 |
| 勉強 | study | reluctantly | 毎日日本語を勉強しています。 |
| 大丈夫 | all right | true man | 体調はもう大丈夫です。 |
| 新聞 | newspaper | news | 毎朝新聞を読みます。 |
| 汽車 | steam train | car | 昔は汽車で旅行しました。 |
| 愛人 | lover (extramarital) | spouse | その小説には主人公の愛人が登場する。 |
| 工作 | handicraft | work, job | 子供と一緒に紙で工作をしました。 |
| 結構 | quite; fine | structure | この料理は結構おいしいです。 |
| 先生 | teacher | Mr.; husband | 田中先生は数学を教えています。 |
| 床 | floor | bed | 床に本を置かないでください。 |

**Size:** small. **Done when:** branch exists, baseline recorded, "before" file written (if Q9).

### J1 - The dictionary prompt knows source → target, with context  *(DoD1)*  ✅ Done (2026-10-15)

> **Result:** prompt moved to the new pure module `src/core/dictionary_prompt.py` (not into
> `translation.py` as planned - it keeps the UI from importing `config`/`keyboard` for a pure
> helper). **Change from the plan:** the Dictionary window's language is stated only when it is
> evidence - the user picked it, or detection proved Japanese (`dictionary_source_language()`);
> an auto-detected Chinese or European language is a guess, so the model decides (Q1's
> principle). "After" (`logs/eval/dictionary_after.jsonl`, Japanese sentence + source stated):
> **10/10 Japanese sense on all three providers**, hiragana readings throughout (one wrong
> reading: the trial model wrote 床 → とこ while translating "floor"). A frequency tie-break in
> the unknown-source wording leaned Chinese (先生 → "Mr." on Groq) and was removed
> (Decision 21). **Headword alone, no source, no context:** Groq 6/10 Japanese with the final
> wording vs 7/10 with the old prompt (one run each, within noise; 汽車 工作 結構 床 answered
> Chinese) - no worse, no better; Gemini's numbers for that case are missing (first key's free
> quota exhausted). Tests 676 → 755; 17 mutations killed. DoD1 met for stated sources; the
> kanji-only-selection case waits for J4/J5.

**Files (4 + 1 new test):** `src/core/translation.py`, `src/ui/dictionary_popup.py`,
`src/ui/quick_translate.py`, `src/app.py`; new `tests/test_dictionary_prompt.py`.

1. `translation.py`: move the prompt into the pure `build_dictionary_prompt()` (§5.2) and add
   `extract_context()`; `dictionary_lookup(text, target_language, source_language=None,
   context=None)` calls them. Log line per §5.2.
2. `dictionary_popup.py` `_open_with_language()`: the `on_lookup` / `on_no_selection` closures
   pass `language` and `original` → `_do_lookup(words, target_language, source_language=language,
   context_text=original)` → `dictionary_lookup(..., source_language=..., context=
   extract_context(...))`.
3. `quick_translate.py` `_open_dictionary_with_language()`: the closures call
   `self._on_dictionary_lookup(all_words, self._current_target_lang, source_lang=language,
   context_text=text_to_analyze)`; update the callback's type hint and docstring (`:266`, `:280`,
   `:292`).
4. `app.py` `_on_quick_translate_dictionary_lookup(words, target_lang, source_lang=None,
   context_text=None)` forwards both.
5. Pass the Dictionary window's `language` (nlp_manager's names: "Japanese",
   "Chinese (Simplified)", ...) through unchanged - normalization arrives in J2.

**Tests (~12):** SOURCE/TARGET lines present; the Japanese rules (kanji-only is still Japanese;
the false-friend sentence); field 2 template = `{source}`; pronunciation rule per source
(Japanese / Chinese / Korean / other); unknown-source variant; source = target variant (Q4);
context between delimiters and capped; `extract_context()` - Japanese sentence split, several
words, word absent, cap; the 8 labels still parse with `dictionary_render.FIELD_RE`; **wiring for
both paths** - build the objects via `__new__` as `test_main_window_ruby.py` does, patch
`threading.Thread` to run inline (or patch `translation_service.dictionary_lookup`) and assert the
call's `source_language` / `context`.

**Verify:** mutation-check by deleting `source_language=` at each call site in turn. If Q9: write
`logs/eval/dictionary_after.jsonl`. Target: field 2 = `Japanese` 10/10 per provider; the Japanese
sense in field 1 for at least 9/10 (educated target - record the actual numbers in CHANGELOG).

**Manual (user):** run `python main.py`; in Notepad select `友達に手紙を書きました。` → Win+Alt+E
→ popup → **Dictionary** → click the 手紙 chip → **Dictionary Lookup**. Expected: field 2 reads
`Japanese`; field 1 means "letter"; examples are Japanese sentences; Pronunciation follows Q2.
(This sentence scores exactly 0.70 in `detect_language()` - on the threshold. If the "Cannot
detect language" dialog appears, pick Japanese; J5 removes it.)

**Size:** ~120-180 production lines.

### J2 - Language identity core: `src/core/lang_id.py`  *(no behaviour change yet)*  ✅ Done (2026-10-15)

> **Result:** `resolve(text, *, known, context, model) -> Verdict(language, evidence)` plus
> `normalize_language`, `han_evidence`, `has_kana`, `has_chinese_glyph`, `ruby_hint`,
> `output_hint`. Glyph classes are cached per character (3,000 kanji ≈ 0.6 ms warm), no sets built
> up front. **A third charset trap:** plain Big5 called 12 of 13 Hong Kong strings Japanese (衆 裏
> 綫 衞 啓 峯 are outside Big5, inside CP932) - "Japanese-only" now also excludes Big5-HKSCS
> (Decision 24), at a measured cost: 959 → 571 Japanese-only glyphs. Fixtures: 311 Japanese, 149
> Simplified, 164 Traditional (incl. Hong Kong forms) - **0 wrong verdicts either way**; settled
> by glyph alone 55 / 80 / 3 (23 of F9's 54, vs 32 with Big5). U+30FB "・" is not kana evidence
> (Chinese uses it in foreign names). Missing codecs switch glyph evidence off with a warning;
> the spec now lists them as hidden imports. Tests 780 → 903; 16 mutations killed.

**Files:** new `src/core/lang_id.py`; new `tests/test_lang_id.py`; fixture lists (inline or
`tests/fixtures/`).

1. Implement §5.1 **minus the default** (Q1 answer, §3.1): `resolve(text, *, known=None,
   context=None, model=None)` - known → evidence in text → evidence in context → the model's
   verdict → None. No `environment_default()` / `user_default()`. Glyph classification lazily per
   character with a cache, or sets built in the existing prewarm thread (`app.py` `run()` →
   `prewarm_background()`).
2. Fixtures: **≥150** kanji-only Japanese words (JLPT N5-N2 nouns, place names, company and
   government terms - include the 54 from F9, and 剝離 / 頰骨 / 補塡 for the CP932 trap), **≥100**
   Simplified and **≥100** Traditional words, plus Chinese sentences with `。，` and Japanese
   sentences holding a Chinese name.

**Tests (~25):** every rule; 剝 頰 塡 are not Chinese evidence; Chinese fixtures → **zero**
Japanese verdicts from evidence (hard assert); evidence beats the model (`model='Chinese'` on kana
text → Japanese; `model='Japanese'` on a Chinese-only glyph → Chinese); a model verdict of
`Unknown` → None; Japanese coverage by glyph logged (≈59% expected from F9); normalization table;
`ruby_hint` / `output_hint` truth tables; performance - classify 3,000 kanji in < 5 ms once warm
(educated guess; measure and record).

~~Decide the Jōyō/Jinmeiyō gate~~ - **no longer needed**: it only narrowed the user's default,
which Q1's answer removed. The sentence-punctuation rule likewise has no job left.

**Size:** ~150-200 lines + tests.

### J3 - Dictionary result: authoritative languages, mixed lines  *(DoD2)*  ✅ Done (2026-10-15)

> **Result:** as planned, with one simplification - there is one Dictionary flow now (D13), so
> the source travels `DictionaryPopup._do_lookup` -> `_show_result` -> `show_dictionary_result(...,
> source_lang=)` once. `side_hints()` gives each entry a (source, target) hint pair; `arrow_parts()`
> cuts `a → x, b → y` lines; `declared_source_language()` reads field 2 for any language (Japanese
> and Chinese by substring). Word Type joined the target fields. Fixture A (field 2 "Chinese",
> source stated Japanese) → 勉強, 学習, 勉学, 勉強会 read; with nothing stated → today's output.
> Fixture B (English → Japanese) → 学習, 研究, 無視, 一生懸命勉強, 名詞 read. Japanese → Chinese and
> Chinese → Japanese entries read only their Japanese side. An unknown source never shares the
> Japanese hint. Tests 903 → 952; 12 mutations killed.

**Files (4):** `src/ui/dictionary_render.py`, `src/ui/quick_translate.py`
(`show_dictionary_result` + title), `src/ui/dictionary_popup.py` (`_show_result`), `src/app.py`
(`_show_quick_translate_dictionary_result`); tests in `tests/test_dictionary_ruby.py`.

1. Implement §5.3, using `lang_id.normalize_language()` and `ruby_hint()`.
2. Thread the source language from J1's closures to the result window on both paths.

**Tests (~8):** Fixture A with caller source `Japanese` while the model says `Chinese` → header,
学習, 勉学, 勉強会 annotated; Fixture A with caller `None` → today's output, unchanged; Fixture B
(English → Japanese) → 学習, 研究, 無視, 一生懸命勉強 annotated; a Japanese → Chinese fixture →
Chinese right-hand sides plain, Japanese left-hand sides annotated; Pronunciation never
annotated; I1 on every fixture; `overhead_px()` grows with the new readings; the title.

**Manual (user):** as J1, then confirm that the result window's `## [手紙]` line, the synonyms
and the examples carry readings. Then Settings → Hotkeys → Furigana OFF → look up again → no
readings anywhere, and the looked-up word is still colour-highlighted.

### J4 - The model reports the source language  *(Q1 + Q7; replaces the old J4 and J11)*  ✅ Done (2026-10-15)

> **Result** (Decision 25): `src/core/source_marker.py` + `TranslationService._call_with_source()`,
> `last_source_language`, `source_verdict(text)`; History's `source_verdict` field. **Measured
> before wiring** (`--mode translate`, ten words alone, target English, Google + Groq second
> keys): marker written **10/10 and 10/10**, never leaked; verdicts Japanese 5 / 4, Chinese 2 / 2
> (汽車, 工作 - confidently wrong), **Unknown 3 / 4** (床, 先生, 結構, 新聞, 愛人). Every Japanese
> verdict came with the Japanese sense, every Chinese one with the Chinese sense. Sense accuracy
> from a word alone is unchanged (within noise) - the model has nothing more to go on. Cache not
> namespaced (step 5: no). Tests 952 → 1011; 20 mutations killed. **For J5/J6:** an Unknown
> verdict is common enough for the chooser to matter; a wrong Chinese verdict is not caught.

The old J4 (a Settings default with Windows-locale inference) was **declined** by the user's Q1
answer - do not build it. Design in §3.1; approve the details below before coding.

**Files (≈3):** `src/core/translation.py` (`translate_text`, `translate_or_fix`, a marker parser,
`last_source_language`), `src/core/history.py` (`add_entry(..., source_lang=None)`,
`find_cached_entry` returning it), `tools/eval_dictionary_prompt.py` (a translate mode).

1. **Measure first:** extend the eval tool to send the merged translate-or-fix prompt with the
   marker instruction for the ten eval words (no context) and record marker compliance and the
   verdict per provider. Present the numbers before wiring anything to them.
2. Prompts, CJK text only (`lang_id.resolve(text)`): evidence known → state it ("The text is
   Japanese."); ambiguous kanji-only → "decide whether it is Japanese or Chinese; begin your
   answer with one line `[[SOURCE: Japanese]]`, `[[SOURCE: Chinese]]` or `[[SOURCE: Unknown]]`";
   any other script → prompt unchanged.
3. Parse and strip the marker (tolerant: first non-empty line, case-insensitive, optional
   brackets); a missing or unparseable marker = no verdict, never an error, never shown.
4. `TranslationService.last_source_language` (set per call, like `last_attribution`; a cache hit
   restores the stored one). History stores the verdict as `source_lang` when there is one.
5. Decide here: should the cache namespace include the verdict, so a pre-J4 entry (no verdict) is
   re-asked once? (Recommendation to present: no - an old entry simply has no verdict.)
6. **Do not tell the model which language is more common.** J1 measured it: a "choose the
   language in which it is more commonly written" tie-break turned gpt-oss-120b's bare 先生 from
   Japanese "teacher" into Chinese "Mr." (Chinese text is simply more abundant). Neutral wording.

**Tests (~12):** prompt variants (kana → stated; Chinese glyph → stated; ambiguous → marker
instruction; Latin → unchanged byte-for-byte); marker parser table; stripped from display, cache
and history; missing marker → no verdict; cache hit restores the verdict; history stores it.

**Manual (user):** select `勉強` alone → Win+Alt+E → the translation is "study" and the log shows
`[LangID] ... model=Japanese`; select `我们在学习中文。` → no marker instruction in the prompt
(evidence) - visible as `evidence=zh-glyph` in the log.

### J5 - One detector: Dictionary mode, History label, the `should_annotate` guard  *(DoD3, DoD4)*  ✅ Done (2026-10-15)

> **Result:** as planned. `detect_language()`: kana → Japanese 1.0, glyph → 0.9, else
> `("Unknown", 0.5)`; every F4 row now has its expected verdict (tests). The Dictionary reuses a
> model's verdict for that exact text, else asks "Kanji-only text: Japanese or Chinese?" -
> **no identification call** (Decision 26: J4 measured 2/10 confidently wrong and 3-4/10 Unknown
> on a word alone). `dictionary_source_language(language, trusted)` states detected Chinese too.
> History: 勉強 → "Unknown". `should_annotate()`: Chinese-only glyph beats a Japanese hint; "・"
> is not kana. Tests 1011 → 1071; 15 of 16 mutations killed, 1 equivalent.

**Files (3):** `src/core/nlp_manager.py` (`detect_language`), `src/core/history.py`
(`_detect_language`), `src/core/furigana.py` (`should_annotate`); tests in a new
`tests/test_language_detection.py` and in `tests/test_furigana_core.py`.

1. `detect_language()`: any kana → `("Japanese", 1.0)`. Kanji-dominant without kana →
   `lang_id.resolve(text)`: glyph evidence → 0.9; ambiguous → `("Unknown", 0.5)`. Traditional
   Chinese is now reported as such. Leave the Vietnamese / Latin / installed-European branches
   untouched.
2. **Dictionary opens in the right language (Q1):** for an ambiguous kanji-only text, both
   Dictionary windows use the model's verdict for that exact text (J4's
   `last_source_language` for the popup's translation; the main window's last translation of the
   same input) → else (main window, untranslated input) one short identification call, or the
   dialog directly - the user decides which in this phase → else **the user's window**: the
   selection dialog worded "Kanji-only text - Japanese or Chinese?" with those two first. A
   language reached this way is `user_chosen=True` / stated to the prompt; J1's
   `dictionary_source_language()` rule can then be simplified.
3. `HistoryManager._detect_language()`: the CJK branch delegates to `lang_id`. Stored entries are
   not migrated - the label is display-only.
4. `should_annotate()`: the §5.1 guard.
5. ~~D15: switch the main-window dialog off `transient` + `grab_set()`~~ - done 2026-10-15 with
   D13; there is one dialog now, in `DictionaryPopup`.

**Tests (~12):** every F4 row → its new expected verdict (the kana rows → Japanese 1.0, 経済 →
Japanese, 勉強 → Unknown 0.5, 我们在学习中文。 → Chinese (Simplified), 這是我的書。 → not
Japanese); the Dictionary open flow - verdict Japanese → opens Japanese, verdict Unknown / none →
the dialog; the History label for 勉強;
`should_annotate('我们', 'Japanese')` is False and `should_annotate('勉強', 'Japanese')` is True;
the existing `test_furigana_core.py` assertions unchanged (`:37-54`).

**Manual (user):** select `勉強` alone → Win+Alt+E → **Dictionary** → the word window opens
directly as Japanese (the translation's verdict) and the 勉強 chip carries べんきょう. Select
`私は学生です。` → **Dictionary** → no "Cannot detect language" dialog.

### J6 - Quick-translate popup surfaces  ✅ Done (2026-10-15)

> **Result:** source block hint = evidence, else the verdict for that text; translation box =
> `output_hint(source, target)`; grammar fix = the original's language; the height budget uses
> the same hint. **Step 3 decided** (Decision 27): the "Kanji-only text - read it as: [Japanese]
> [Chinese]" row re-translates with the stated source - J4 measured unplaced translations with
> the other language's sense, so readings alone would mislead. `SOURCE_CHOOSER_PX = 36`
> (measured). `do_translation()` left alone (§10). Tests 1071 → 1118; 15 mutations killed.

**Files (2):** `src/core/translation.py` (`do_translate_or_fix` `:619-624`, `redo_translation`
`:675-679`), `src/ui/quick_translate.py` (`_ruby_hint`, the height budget at `:533-537`, the
replace preview at `:1127-1130` / `:1181-1185`); tests in `tests/test_popup_ruby.py`.

1. Source block: `generate_furigana(text, lang_hint=resolve(text, model=last_source_language)
   .language)`.
2. `_ruby_hint()` → `output_hint(resolve(original, model=…).language, target)`; for grammar
   results `resolve(original)` (the popup already stores `_current_original`).
3. Verdict `Unknown` → the user's chooser (§3.1): re-translate with the stated source, or only
   add the readings - decide with the user at the start of this phase.
4. The height estimate and the widget must use the **same** hint, or the box clips.
5. Leave `do_translation()` alone (§10) unless the user approves deleting it.

**Tests (~8):** a kanji-only Japanese selection → the source block exists and carries ruby (model
verdict Japanese) / no block (no verdict); the chooser on `Unknown`; a Simplified selection → no
block; a
kanji-only grammar result annotated when the source resolves Japanese; no clipping (the
`fit_height` pattern already in `test_popup_ruby.py`).

**Manual (user):** select `東京大学` → Win+Alt+E → the popup shows 東京大学 with とうきょうだいがく
above the translation; select `我们在学习中文。` → Win+Alt+E → no reading block.

### J7 - Main-window surfaces

**Files (2):** `src/app.py` (`_refresh_reading_pane` `:1407-1436`, `_update_grammar_result`
`:1184-1200`, `_update_translation_with_original` `:1218-1237`, `_create_translation_box`
`:1303-1326`, `_open_expanded_translation` `:1471-1476`), `src/ui/expanded_window.py` (accept a
source hint); tests in `tests/test_reading_pane.py`, `tests/test_main_window_ruby.py`.

1. Reading pane: `resolve(text, model=<verdict of the last translation of this exact text>)`
   instead of no hint - no API call while typing, and never a window from this pane; update the
   comment at `:1428-1429`, which states the old rule.
2. Grammar result: `resolve(input)`. Outputs and expanded view: `output_hint()`.
3. Existing tests asserting "kanji-only stays plain" still hold when there is no verdict -
   update them deliberately only where a verdict now applies; never delete; the count stays
   monotonic.

**Tests (~8):** Reading pane with kanji-only input, with and without a verdict; grammar result;
output and expanded view hints.

**Manual (user):** main window, type `東京大学` → the pane shows its placeholder (no verdict
yet); press Translate → the pane shows とうきょうだいがく (the model's verdict).

### J8 - Screenshot OCR source block  *(Q6)*

**Files (1-2):** `src/ui/screenshot_handler.py` (`:195-224`), possibly a helper on
`TranslationService`; tests: new `tests/test_screenshot_ruby.py`.

1. The vision prompt gains a `===SOURCE LANGUAGE===` section (the model's verdict, §3.1).
2. After parsing `===ORIGINAL===`, when furigana is enabled and the OCR text is not the
   `"[Screenshot]"` fallback: `furigana_text = TranslationService.generate_furigana(original,
   lang_hint=resolve(original, model=<that section>).language)`, passed to
   `on_show_quick_translate(...)`.
3. Q6 approved: store the OCR text instead of `"[Screenshot OCR]"`.

**Tests (~4):** mocked `translate_multimodal` returning Japanese → `furigana_text` passed;
Chinese → `None`; the fallback → `None`; furigana OFF → `None`.

**Manual (user):** Win+Alt+S over Japanese text on screen → the popup shows the OCR'd Japanese with
readings above the translation.

### J9 - History rows  *(Q5)*

**Files (1-2):** `src/ui/history_dialog.py` (`_create_history_item` `:247-295`), possibly a
segment-truncation helper in `src/ui/ruby_text.py`; tests in `tests/test_history_dialog.py`.

1. Original and translated lines become `RubyRow`s. Truncate **by segments** to ≤57 base
   characters plus "...", never splitting a ruby pair.
2. Hints: original → `resolve(original, known=normalize_language(entry['source_lang']))`;
   translation → `output_hint(source, entry['target_lang'])`.
3. Click-to-load on **every** part (`RubyRow.bind_all_parts`) - the current loop
   (`:288-290`) is non-recursive. Wheel bound per widget, never `bind_all` (CLAUDE.md Known
   Issues: the History dialog bug).
4. Measure dialog open time with 100 Japanese entries; budget ≤300 ms (educated guess). Over
   budget → annotate the first N rows, or lazily as rows scroll into view.

**Tests (~8):** clicking a *reading* label loads the entry; the wheel over a reading scrolls;
truncation never splits a pair; I1 per row; search and delete still work; furigana OFF → labels
as today.

### J10 - ~~Optional extras~~ - **dropped** (Q5: the user said no)

Toasts and the Replace preview's struck-through original stay plain - non-goals (§9).

### J11 - ~~Source-aware translation prompts~~ - **folded into J4** (Q7: yes)

### J12 - Docs, memory, release prep

- **CLAUDE.md:** rewrite "Which surfaces annotate, and with what hint"; add a "Language
  identity" subsection (`lang_id.py`, precedence, glyph sets, the CP932/GBK traps, the
  default); update "Dictionary Prompt (8-field output)" (source, target, context, pronunciation by
  source); add `lang_id.py` to Core Modules and the Common Tasks table.
- **DESIGN_DECISIONS.md:** Decision 21 - ambiguous kanji: evidence → context → the user's
  declared default, sentences excluded, glyph sets, language-set rule. Decision 22 - Dictionary
  prompt v2. Record the rejected options from §3 so they are not re-proposed.
- **README.md:** Furigana (`:124-136`) and Dictionary Mode (`:139-143`) sections; the new
  setting.
- **Memory:** update `project_furigana_everywhere.md` (Q5 outcome, Q1 default) and `MEMORY.md`.
- **Release:** ROADMAP already queues an unreleased 1.9.21 (the H1 work) - ask whether this ships
  in 1.9.21 or 1.9.22. CI pins `--min-total 500` (`.github/workflows/tests.yml:58`); raising it to
  track the new count is optional.

---

## 7. Manual end-to-end checklist

Run from source (`python main.py`) or a fresh `build_exe.bat` EXE, Furigana ON, default Auto.
Dictionary rows need language packs (Settings → Dictionary): Japanese for every row, plus English
for row 7 and Chinese (Simplified) for row 8. The file log is JSON Lines (`logs/` from source,
`%APPDATA%\CrossTrans\logs` for the EXE); look for `[LangID]` and `[Dictionary]` lines when
something looks wrong.

| # | Do | Expect |
|---|----|--------|
| 1 | Settings → Hotkeys → Furigana | Toggle ON; "Text written only in kanji" = Auto (Japanese on this PC) |
| 2 | Select `勉強` in Notepad → Win+Alt+E | Popup: 勉強 with べんきょう above the translation |
| 3 | Popup → Dictionary | Opens as Japanese, no dialog; the chip shows べんきょう |
| 4 | Click 勉強 → Dictionary Lookup | `Source Language: Japanese`; `## [勉強]` with its reading; synonyms and examples annotated; Pronunciation per Q2 |
| 5 | Select `友達に手紙を書きました。` → Win+Alt+E → Dictionary → 手紙 | Field 1 means "letter", never "toilet paper" |
| 6 | Select `私は学生です。` → Win+Alt+E → Dictionary | No "Cannot detect language" dialog |
| 7 | Select `study` → Win+Alt+J → Dictionary → study | Translation 勉強 annotated; synonyms 学習, 研究 annotated |
| 8 | Select `我们在学习中文。` → Win+Alt+E | No reading block; Dictionary opens as Chinese (if that pack is installed); no readings anywhere |
| 9 | Main window: type `東京大学` | Reading pane: とうきょうだいがく |
| 10 | Main window: type `勉強` → **Fix Grammar** button | Output 勉強 with its reading (the Win+Alt+G hotkey is off by default) |
| 11 | Win+Alt+S over Japanese text (J8) | OCR'd Japanese with readings above the translation |
| 12 | History (J9) | Rows carry readings; clicking a reading loads the entry |
| 13 | Settings → default "Unknown" | Steps 2, 9, 10 lose their readings again (today's behaviour) |
| 14 | Furigana OFF | No readings anywhere; Copy / Replace paste plain text |
| 15 | Copy from any annotated box (button and Ctrl+C) | Plain base text only, e.g. 勉強 - never 勉強(べんきょう) |

---

## 8. Risks

| # | Risk | Mitigation |
|---|------|------------|
| R1 | A Japanese default puts Japanese readings on an ambiguous kanji-only Chinese **word** (mostly Traditional; 3 of 20 Simplified samples too) | Chinese-glyph guard; sentences never use the default; the candidate Jōyō/Jinmeiyō gate; the user can choose Chinese / Unknown; every default verdict is logged |
| R2 | Weak models (trial `llama-3.3-70b`) still write `Chinese` in field 2 | J3 makes the readings independent of field 2 whenever the caller knows the source; J1 eval measures compliance per provider |
| R3 | Context raises token cost and latency (and trial quota use) | Cap (Q3); log `context_chars`; measure in J1 |
| R4 | The dictionary now sends the sentence to the provider | Not a new exposure - the same text was already sent for translation; mention it in the CHANGELOG |
| R5 | ~~The two Dictionary-mode copies drift~~ | Resolved 2026-10-15: one copy (Decision 23); tests still drive both buttons |
| R6 | Height regressions where windows are sized before the widget exists | Same hint for estimate and render; the existing `fit_height` / `estimate_ruby_overhead_px` tests extended |
| R7 | Cost of glyph sets, History build time | Lazy per-character cache or the prewarm thread; J9 measures against its budget |
| R8 | Tests encoding "kanji-only stays plain" | Update them deliberately (pin the default), never delete; count monotonic |

---

## 9. Non-goals (unchanged)

- Ruby inside Listbox / Combobox / menus / title bars / tray / messageboxes - Tk cannot embed
  widgets there.
- Ruby in any editable box (I3) - the Reading pane covers the input box.
- "Copy with readings" - declined by the user (Decision 8).
- Reading colour - stays `#80b8ff` (Decision 9).
- Asking the AI model for readings - declined (Decision 8, option 3).
- Ruby in exported files (.docx / .srt / .txt output).
- Kanji outside U+4E00-9FFF / U+3400-4DBF (CJK Compatibility, Extension B+: 𠮟, 𩸽) - `KANJI_RE`
  (`furigana.py:33`) ignores them, so they render plain. Rare; record, do not fix here.

---

## 10. Adjacent findings - not part of this work

Mention to the user; change nothing without approval (Rule 3).

- ~~`src/ui/dictionary_popup.py` uses `transient(parent)` + `grab_set()`~~ - fixed 2026-10-15 (D15).
- ~~Dictionary mode is implemented twice (Q8)~~ - consolidated 2026-10-15 (D13, Decision 23).
- `UpdateFailedDialog` makes the same trap on the withdrawn root - DEFERRED D16.
- `TranslationService.do_translation()` (`translation.py:521`) has no live caller -
  `tests/test_callback_wiring.py:68` asserts the hotkey path no longer uses it. J6 changes its two
  siblings; it would silently stay on the old rule.
- ROADMAP.md says the H1 work "sits on `main`"; it is on the unmerged `h1-health-review` (Q10).

---

## 11. Bookkeeping (Rules 6, 8, 9, 11)

After **each** phase, in the same commit as the code:
- `CHANGELOG.md` → `## [Unreleased]` → `### Phase Jn - Title (YYYY-MM-DD)` with Added / Changed /
  Fixed during implementation / Tests (old → new count).
- `ROADMAP.md` status column; this file: mark the phase `✅ Done (YYYY-MM-DD)`.
- `MEMORY.md` (AI memory) status line + implementation log.
- `DESIGN_DECISIONS.md` when a decision was made (Q answers → Decisions 21, 22).
- `DEFERRED.md` for anything left (Q7, Q8 consolidation, J10 items not approved).

When J0-J12 are complete: archive the summary into `ROADMAP_DONE.md`, move leftovers to
`DEFERRED.md`, and delete this file.

---

## Appendix - how the measurements were made

All run from the repo root on 2026-10-15 with the project's Python 3.14. Set
`PYTHONIOENCODING=utf-8` first - the console code page is cp932 and prints of simplified Chinese
otherwise raise `UnicodeEncodeError`.

**F4 - `detect_language()`:**

```python
import logging; logging.disable(logging.CRITICAL)
import src.core                      # before anything that imports config
from src.core.nlp_manager import nlp_manager
for s in ["勉強", "経済", "私は学生です。", "Pythonで開発する", "這是我的書。"]:
    print(s, nlp_manager.detect_language(s))
```

**F9 - glyph-evidence prototype** (the rule the F9 table was measured with):

```python
import src.core                      # same import-order rule as above
from src.core.furigana import KANJI_RE, KANA_RE

def enc(ch, codec):
    try:
        ch.encode(codec); return True
    except UnicodeEncodeError:
        return False

def classify(text):            # prototype only - J2 implements the real rules
    if KANA_RE.search(text) or any(c in text for c in '々〆ヶ'):
        return 'Japanese'
    kanji = [c for c in text if KANJI_RE.match(c)]
    jp = [c for c in kanji if enc(c, 'cp932') and not enc(c, 'gb2312') and not enc(c, 'big5')]
    zh = [c for c in kanji if not enc(c, 'euc_jis_2004')]
    if jp and zh:
        return None                                   # conflict
    if jp:
        return 'Japanese'
    if zh:
        return 'Chinese (Simplified)' if all(enc(c, 'gb2312') for c in zh) else 'Chinese (Traditional)'
    return None                                       # ambiguous
```

An earlier run that tested Chinese evidence against CP932 instead of JIS X 0213 gave 18/20
Simplified resolved - and would have called 剝離 Chinese. That is the trap in F9.

**F2 / F3 - dictionary rendering:** write the entry by hand (Fixture A / B), then with
`split_dictionary_text` from `src.ui.dictionary_render` and `_align_dictionary_text` from
`src.ui.quick_translate`:
`split_dictionary_text(_align_dictionary_text(entry), target, [word], colors=('#f00',))`, and print
each run as `base[ruby]`.

**Q1 - Windows signals:** `ctypes.windll.kernel32.GetUserDefaultUILanguage()`,
`GetUserDefaultLCID()`, `GetSystemDefaultLCID()`, `GetACP()`, and
`ctypes.windll.user32.GetKeyboardLayoutList()` (low word of each HKL).
