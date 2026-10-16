# Changelog

All notable changes to CrossTrans are documented here.

## [Unreleased]

### Phase K1 — The suite on a clean machine (2026-10-16)

The first of the follow-ups proposed after J12: run the suite the way CI will - a fresh venv
with `requirements.txt` and nothing else - instead of on the development PC, which also has the
Japanese NLP pack (fugashi + UniDic). `.github/workflows/tests.yml` is among the commits on
`main` that were never pushed, so CI has **never run**; this is what its first run would have
found.

**Fixed**
- **Five word-chip tests failed without the Japanese NLP pack** (`tests/test_word_chips_ruby.py`,
  since F6). Dictionary mode tokenizes Japanese with the pack; without it the word area splits
  on whitespace, so the test sentence came back as one chip and `chip(frame, "勉強")` found
  nothing. The tests are about the chips, not the tokenizer: the pack's split of the two test
  sentences is now recorded in the file and pinned at the `nlp_manager` boundary, and a new test
  checks the record against the real pack wherever the pack is installed.
- **One of them asserted fugashi's reading**: 今日 -> きょう in 今日は日本語を勉強します。. With
  pykakasi alone the line reads 今日 as こんにち (its greeting entry 今日は -> こんにちは), though
  今日 alone is きょう. The test is about where a chip's reading comes from - the line, not the
  chip - so it now compares the chip with what the line reads. Which reading is right stays with
  the engine's fugashi-only tests (`TestReadingQuality`), which already assert きょう.
- The J12 entry below quoted the Vietnamese test data it removed; reworded without the quotes.

**Found - DEFERRED D19**: pykakasi, the only reading provider a fresh install has, reads at least
one word differently from fugashi in **898 of 3000** random Tatoeba sentences (30%) - 彼の as
かの, 君 as くん, 人 as にん among the most frequent. Not fixed: the options trade the EXE's size
against reading quality, which is the user's call.

**Tests**: 1183 -> 1184 (+1, the record check). Clean venv (Python 3.14.0, pykakasi 2.3.0, no
fugashi): **1169 passed / 5 failed / 9 skipped** before, **1175 passed / 0 failed / 9 skipped**
after - the compound test that skipped there now runs, and the record check skips. The nine
skips are the tests that need the Japanese pack, inside the CI guard's ceiling of ten.

### Phase J12 — Final check, docs and archive (2026-10-15)

The last phase of the Japanese language-identity work: an end-to-end check of the whole flow,
the documentation, and the archive. The work is complete on its branch; nothing was released.

**Fixed**
- **A stray `[[SOURCE: ...]]` line could reach the popup.** An end-to-end smoke run (real
  widgets, a scripted model) chose "Japanese" in the popup's chooser; the re-translation was
  told the language, the model wrote a marker anyway, and nothing removed it - the answer's
  first line was `[[SOURCE: Unknown]]`. `source_marker.strip_stray_markers()` now removes the
  double-bracket form from every answer `_call_with_source()` returns, whether the prompt asked
  or not; a bare `SOURCE: ...` line is left alone when nothing asked, since it could be the text.
- **Vietnamese test data** (a greeting, a language name and a noun in four new test files) broke
  the project's no-Vietnamese rule: replaced by French, Korean and Russian samples, the two
  Vietnamese-only detection cases by Cyrillic ones, so the count holds.
- **The mutation runner could test the wrong mutant**: two same-size mutants written within one
  second shared the `.pyc`'s (mtime, size) key, so the second run executed the first. Found by a
  result that flipped between runs. The runner now deletes the module's bytecode before each
  mutant and writes none; **every suite was re-run** - all mutations still killed (three
  patterns had to follow later refactors), the one equivalent mutant still equivalent.

**Docs**
- README: Furigana and Dictionary Mode describe kanji-only text, the chooser and a Dictionary
  that knows its languages.
- CLAUDE.md: a **Language Identity** section (the order, where verdicts come from and where they
  are kept, the measurements, the traps) and two Common Tasks rows.
- ROADMAP_DONE.md: the "J" entry - the user's answers, every phase with its commit and test
  count, the decisions, the leftovers and a 14-row **manual acceptance checklist**.
  ROADMAP.md: the branch's status. DEFERRED.md: **D18** (dead code). `TODO.md` deleted, as its
  own bookkeeping section asked once the phases were done - its last version is
  `git show 5cc8736:TODO.md`.

**Tests**: 1173 -> 1183 (+10 in `test_source_marker.py`), 0 failed, 0 skipped. Four mutations
on the fix - stray markers kept, the bare form stripped too, either path unstripped - killed.

**Not done, by design - the user's call**: no version bump, no build, no tag, no merge into
`main`, no push. Whether this ships in 1.9.21 or 1.9.22 is open (ROADMAP.md).

### Phase J9 — History rows carry readings (2026-10-15)

The History list showed Japanese in every entry and read none of it - its rows were plain
labels, a non-goal in 2026-08 that the user brought into scope (TODO.md Q5).

**Added**
- **Readings on the rows**: the original by its own evidence, else the verdict a model gave for
  it (J4's `source_verdict` - never the entry's `source_lang`, which has always been a guess from
  the characters); the translation by `lang_id.output_hint`. A line is still cut at 57
  characters plus "...", now by segments (`ruby_text.truncate_segments()`): a plain run may be
  cut, a ruby pair is kept whole or dropped - half of 東京 under とうきょう would be a wrong reading.
  Readings are generated for the first 120 characters, so a word that straddles the cut is read
  in context. Furigana OFF keeps exactly the labels the rows always had.
- **`ruby_text.RubyLine`**: one canvas per annotated line, text and readings drawn as canvas
  items. Each ruby pair takes a slot as wide as the wider of base and reading, so とうきょう never
  runs into its neighbour. Fonts and character widths are shared across lines.
- Clicking anywhere on an annotated line - the reading row included - loads the entry; the wheel
  scrolls over it (it is bound per widget, as the 2026-09 fix requires, never `bind_all`).
- `HistoryDialog(..., furigana_enabled=)`, passed by the app from the Settings toggle.

**Fixed during implementation**
- **A frame and two labels per segment made the dialog take 4.1 s** to open with 100 Japanese
  entries (~4,500 widgets; on Windows every Tk widget is a native window). Drawing each line on
  one canvas brought it to 3.3 s - and **a Font object per line was 1.9 s of that**: Tk searched
  for a CJK fallback font afresh on every measure (0.7 ms a call). Shared fonts and per-character
  widths: **1.27-1.30 s, against 0.93-0.95 s for the same dialog without readings.** That
  baseline is the dialog's own and is over the 300 ms the plan budgeted - recorded as
  `DEFERRED.md` **D17**, not changed here.

**Tests**: 1154 -> 1173 (+19 in `tests/test_history_dialog.py`: truncation by segments, each
hint, the old label never trusted, click and wheel over a reading, search, a wide reading
never overlapping, shared fonts, the app passing the setting, and 100 Japanese rows within a
generous time bound), 0 failed, 0 skipped. Ten mutations - a pair split or a plain run dropped
by the cut, the setting ignored, the label trusted, the translation hinted by its target only,
the click unbound, readings overlapping, a Font per line, the app not passing the setting, long
lines uncut - each made the suite fail and was restored.

### Phase J8 — A Japanese screenshot shows what it read, with readings (2026-10-15)

Win+Alt+S showed only the translation - the hotkey popup shows the selection with its readings
above it - and History stored the literal `[Screenshot OCR]` as the original (TODO.md F7, Q6).

**Changed**
- **The vision prompt asks for the text's language** too (`ocr_prompt()`): a
  `===SOURCE LANGUAGE===` section between `===ORIGINAL===` and `===TRANSLATION===` - neutral
  wording, Unknown allowed (Decision 22, the J4 principle for images). `parse_ocr_result()` reads
  the sections in any order and keeps the old fallback when the answer lost them.
- **The OCR'd text is shown with readings** above the translation when it is Japanese: kana or a
  Japanese-only glyph, else the section's verdict - a Chinese-only glyph beats a "Japanese"
  verdict. Furigana off, or no sections, shows no block.
- **The verdict is recorded** for the OCR text before the popup opens, so the popup's hint, its
  Dictionary (J5) and its "Japanese or Chinese?" row (J6) all know it. Logged as
  `[LangID] screenshot verdict=.. chars=..`.
- **History keeps the OCR text** as the entry's original (Q6), with its verdict; the
  `[Screenshot OCR]` placeholder only when the answer lost its sections. Screenshot entries keep
  their own `source_type`, so they are still never served as a text-translation cache hit.

**Tests**: 1132 -> 1154 (+22 in the new `tests/test_screenshot_ruby.py`), 0 failed, 0 skipped.
Ten mutations - the section never asked for, the verdict not normalized, an answer without a
translation accepted, the verdict not recorded or ignored, every OCR text read as Japanese, the
setting ignored, History keeping the placeholder or dropping the verdict, the block never reaching
the popup - each made the suite fail and was restored. (One run had first "killed" every mutation
through a broken test file; the runner now reports a collection error as an error, not a kill.)

### Phase J7 — The main window reads what a translation placed (2026-10-15)

The Reading pane under the input box had no hint at all - its comment said so: kanji-only input
"stays plain rather than being guessed at" - so 東京大学 typed into the main window never got a
reading, even after a translation had settled that it is Japanese. The output box, the grammar
result and the expanded view took only the target language.

**Changed**
- **One question for the main window**: `TranslatorApp._input_source()` asks
  `TranslationService.source_language(text)` (new, public; J6's `_source_hint` builds on it):
  the input's own evidence, else the verdict a model or the popup's chooser gave for exactly that
  text - looked up stripped, as translations store it. No request while typing; the pane never
  opens a window.
- **Reading pane**: reads kanji-only Japanese once it is placed, and a finished translation
  schedules a refresh, since that is when the verdict arrives. Type 東京大学 → placeholder; press
  Translate (the model says Japanese) → とうきょうだいがく.
- **Output box** and **expanded view**: `lang_id.output_hint(source, target)` - Japanese quoted
  in an English translation of Japanese is read. `ExpandedTranslationWindow.show(...,
  source_language=)`.
- **Grammar result**: read when the input's language is settled as Japanese.

**Tests**: 1118 -> 1132 (+6 in `test_reading_pane.py`, +8 in `test_main_window_ruby.py`; both
fixtures now carry a real service and an input box - the tests that say "kanji-only stays plain"
still pass unchanged, because nothing placed their text), 0 failed, 0 skipped. Ten mutations -
the pane ignoring the settled language or rendering without it, the verdict looked up unstripped
or ignored, the update, the new box, the expanded view or the grammar result back on their old
hints, the expanded view not told the source, no refresh after a translation - each made the
suite fail and was restored (the last only after the test was made to drain the refreshes
already queued at construction).

### Phase J6 — The popup reads kanji-only Japanese, and asks when nobody knows (2026-10-15)

A kanji-only selection - 勉強, 東京大学 - never got the popup's source block: without kana there
was no hint, and the block needs one. A grammar fix of kanji-only text stayed plain, and Japanese
quoted inside an English translation (`The word 東京 means Tokyo.`) too.

**Changed**
- **The source block** takes its hint from the text's evidence, else the verdict the model gave
  for exactly that text (J4): 勉強 called Japanese gets 勉強[べんきょう] above the translation;
  called Chinese or Unknown, no block. (`TranslationService._source_hint()`, used by
  `do_translate_or_fix()` and `redo_translation()`.)
- **The translation box** uses `lang_id.output_hint(source, target)`: the target as before, plus
  Japanese runs in a translation *of* Japanese into a non-Chinese language. A **grammar fix**
  keeps its source's language: read when the original's characters or verdict say Japanese.
  The height budget and the box use the same hint, so nothing clips.
- `TranslatorApp.show_quick_translate(..., source_lang=)` defaults to
  `translation_service.source_verdict(original)` - read on arrival, like the model credit, not
  carried through the queue (Decision 11's pattern).

**Added**
- **"Kanji-only text - read it as: [Japanese] [Chinese]"** - a row above the popup's buttons,
  shown when a translation of kanji that prove nothing came back without a verdict (Unknown, a
  missing marker, or a cache entry from before J4). Answering **re-translates with that source
  stated** (`redo_translation(text, target, source_language=)`) and records it as the text's
  verdict, so the Dictionary (J5) and History see it too. Decision 27: J4 measured that an
  unplaced translation can carry the other language's sense (先生 → "Mr."), so adding readings
  alone would put べんきょう-style readings above a Chinese meaning. One more request, only when the
  user asks for it. A row, not a dialog: nothing is blocked while the question stands.
  `SOURCE_CHOOSER_PX = 36` (measured: 28 px row + 8 px gap) joins the height budget only then.
- `source_marker.stated_clause()` and `translate_text(..., source_language=)`.
- `tests/test_popup_source_language.py` (47 tests).

**Tests**: 1071 -> 1118 (+47), 0 failed, 0 skipped. Fifteen mutations - the verdict ignored by
the source hint, either block built without a hint, the user's source ignored, the stated clause
naming the variant, the grammar fix or the translation box back to their old hints, the chooser
ignoring a verdict, never built, out of the height budget or with its answers swapped, the app
forgetting the verdict or re-translating without the answer, custom-prompt cancel and the
replace preview dropping the verdict - each made the suite fail and was restored.

### Phase J5 — The Dictionary opens in the right language; one rule for Japanese vs Chinese (2026-10-15)

Three detectors gave three answers (TODO.md F5). `nlp_manager.detect_language()` called every
kanji-only text "Chinese (Simplified)" - so 勉強 selected alone opened the Dictionary as Chinese,
its chips without readings - and scored ordinary Japanese sentences at 0.63-0.70 against a 0.7
threshold, so 「私は学生です。」 got "Cannot detect language" (F4). History labelled 勉強
"Chinese". And a caller's Japanese hint could put Japanese readings on 我们.

**Changed**
- **`detect_language()`** asks `lang_id` for Japanese vs Chinese: any kana -> Japanese 1.0; a
  kanji only one of them writes -> that language 0.9 (Traditional reported as such); kanji that
  prove nothing -> `("Unknown", AMBIGUOUS_CJK_CONFIDENCE)` = 0.5. Re-measured F4 table: 勉強,
  手紙, 東京大学 -> Unknown; 経済 -> Japanese; 私は学生です。, 「勉強」という言葉, Pythonで開発する,
  友達に手紙を書きました。 -> Japanese 1.0; 我们在学习中文。 -> Chinese (Simplified); 說話 -> Chinese
  (Traditional); 這是我的書。 -> Unknown (it was "Chinese (Simplified)", the wrong variant). The
  Vietnamese, Latin and other-script branches are untouched.
- **The Dictionary opens in the right language** (Q1, Decision 26). Kanji that prove nothing open
  in the language a model reported for that exact text - the popup's translation always has one
  (J4), the main window's input once the user pressed Translate - logged as
  `[Dictionary] open language=.. via=model-verdict`. Without a verdict the selection dialog asks
  **"Kanji-only text: Japanese or Chinese?"**, with Japanese and the Chinese packs listed first.
  A Chinese verdict falls back to the other Chinese pack when only that one is installed; a
  verdict whose pack is missing offers to install it. **No identification call**: untranslated
  input goes straight to the user, because a word alone came back confidently wrong 2 times in
  10 and unsure 3-4 times in J4's measurements, and one click costs nothing.
- **What the lookup prompt is told** (`dictionary_source_language(language, trusted)`, renamed
  from `user_chosen`): a detected Chinese is stated now too - detection says it only from a glyph
  Japanese cannot write - as is a model's verdict or the user's pick.
- **History's label** follows the same evidence: 勉強 is "Unknown" (shown as "→ English"), 経済
  Japanese, 我们 Chinese (Simplified); stored entries are not migrated. A model's verdict, when
  there is one, is the label already (J4).
- **`furigana.should_annotate()`**: a Japanese hint no longer overrides a kanji Japanese cannot
  write (我们, 说话 stay plain), and "・" alone no longer counts as kana - Chinese writes it between
  the parts of a foreign name (列夫・托尔斯泰 used to be annotated).

**Tests**: 1011 -> 1071 (+50 in the new `tests/test_language_detection.py`, +10 in
`test_dictionary_flow.py`); 0 failed, 0 skipped. Nine tests updated on purpose - their premise
was the old rule ("a detected Chinese is a guess", the `user_chosen` name). Sixteen mutations,
fifteen killed; the sixteenth is equivalent - a model's verdict opened with `trusted=False` is
still stated, because a verdict is always Japanese or Chinese, which are stated anyway.

### Phase J4 — Translations learn the source language, and the model says what it decided (2026-10-15)

The user's answers to TODO.md Q1 and Q7: the AI model decides what ambiguous kanji-only text is,
and the ordinary translation prompts learn the source language too. This phase makes the model
*say* what it decided; J5-J8 use the answer. Nothing visible changes yet, except that a translation
of Japanese or Chinese text is now told which one it is when the characters prove it.

**Measured first** - `tools/eval_dictionary_prompt.py --mode translate` (new), the ten kanji-only
false friends sent alone through `translate_or_fix()` as a language hotkey would, target English,
real API calls on the user's second key of each provider:

| | gemini-2.5-flash | gpt-oss-120b (Groq) |
|---|---|---|
| Before - Japanese sense / Chinese sense | 6 (+ 結構 "Fine") / 3 | 5 (+ 結構 "Fine") / 4 |
| After - wrote the `[[SOURCE: ...]]` line | **10/10** | **10/10** |
| After - the line leaked into the translation | 0 | 0 |
| After - said Japanese / Chinese / Unknown | 5 / 2 / 3 | 4 / 2 / 4 |

Every "Japanese" came with the Japanese sense (9/9), every "Chinese" with the Chinese sense (汽車
"car", 工作 "work" - both models, confidently wrong). The models admit doubt on 3-4 words in ten
(床, 先生, 結構, 新聞, 愛人), which is where J6's chooser will ask the user. The sense itself is no
better or worse from a word alone - one run each, within noise - because the word alone is all the
model has; the gain is that the app now knows what the model assumed. A sanity run on sentences:
kana and Chinese-glyph text are stated, not asked, and translate correctly; English text is sent
unchanged. With a Chinese *target*, a merged prompt still sometimes leaves 勉強 as it is - with the
old prompt too (it once even "fixed" it to 勉强, the Chinese "reluctantly"); not a J4 regression.

**Added**
- `src/core/source_marker.py` (pure): `source_clause(text)` - mostly-CJK text (kanji + kana at
  least half of its letters, no Hangul) whose characters prove its language gets
  `SOURCE LANGUAGE: the text above is Japanese.` (or Chinese); kanji that prove nothing make the
  prompt ask for one first line, `[[SOURCE: Japanese]]` / `[[SOURCE: Chinese]]` /
  `[[SOURCE: Unknown]]`; any other text gets nothing, so its prompt is byte-for-byte what it was.
  `parse_source_marker(answer)` reads and removes the line (double brackets anywhere; a bare
  `SOURCE: x` only as the first line), and a missing or garbled one is simply no verdict.
- `TranslationService.last_source_language` (per call, like `last_attribution`; a cache hit
  restores the stored one) and `source_verdict(text)` - the model's verdict for exactly that
  text, from this session (bounded, 64 texts) or from History.
- `HistoryManager`: entries record `source_verdict` when a model gave one, and
  `find_source_verdict()` reads it. `source_lang` (the History label) takes the verdict too.
- `tools/eval_dictionary_prompt.py`: `--mode translate`, and `--key N` to measure each provider's
  N-th key (the first Google key's free quota was spent).
- `tests/test_source_marker.py` (59 tests).

**Changed**
- `translate_or_fix()` (the language hotkeys) and `translate_text()` (the main window, Re-translate)
  append the clause. A custom prompt is sent exactly as the user wrote it. Logged as
  `[LangID] translation verdict=.. marker=found|missing chars=..` - never the text.

**Decided** (Decision 25): the marker goes last in the prompt; the wording names no favourite
language and its example (娘) is not one of the measured words; the cache is **not** namespaced
by verdict - an entry from before J4 simply has no verdict, and Re-translate gets one; the
verdict lives in its own `source_verdict` field, because `source_lang` has always held a guess
from the characters ("Chinese" for every kanji-only text).

**Tests**: 952 -> 1011 (+59), 0 failed, 0 skipped. Twenty mutations - mixed text or Hangul
counted as CJK, evidence ignored, a "more common" tie-break added, the example swapped for an
eval word, Unknown read as a language, the marker left in the answer, the bare form read anywhere
or nowhere, the service not parsing or not appending, the verdict not stored, a cache hit or a
failure leaving the wrong verdict, the memory unbounded, History ignored, the clause added to a
custom prompt, History storing an empty verdict or the oldest one, the text in the log - each made
the suite fail and was restored. `config.json` was hashed before and after every real-API run:
unchanged.

### Phase J3 — The dictionary result reads the language it was asked in (2026-10-15)

The result window took its reading hint from one place only: the model's own **Source Language**
field. A model that decided 勉強 was Chinese therefore switched off every reading in the entry -
headword, synonyms, examples - even when the lookup had told it the word was Japanese (TODO.md
F2). And an English -> Japanese entry left `learn → 学習` plain, because each line had one hint:
the source language, English (F3).

**Changed**
- **The stated source wins.** `show_dictionary_result(..., source_lang=)` receives the language
  the prompt was told (J1's `dictionary_source_language()`); each entry's field 2 decides only
  when nothing was stated - today's behaviour, kept for that case. The title names the pair:
  `Dictionary - Japanese → English`.
- **Both languages of an entry are read** (`dictionary_render.side_hints()`). Japanese paired
  with a language that is not Chinese makes every kanji run Japanese - the prompt keeps an entry
  to its two languages - so synonyms, antonyms and examples are read on both sides of the arrow.
  A Japanese/Chinese pair is cut at its arrows (`arrow_parts()`): the Japanese side is read, the
  Chinese side is left alone. In a Japanese -> Chinese entry the Chinese half of a Japanese
  example line used to get Japanese readings, because the whole line carried kana.
- Field 2 is read for any language (`declared_source_language()`), not only Japanese.
- **Word Type is a target-language field** (fields 1, 3, 4), as the J1 prompt asks for it.

**Measured on the fixtures** (`tests/test_dictionary_ruby.py`): Fixture A with the source stated
→ 勉強[べんきょう], 学習[がくしゅう], 勉学[べんがく], 勉強会[べんきょうかい]; Fixture B → 学習, 研究, 無視,
一生懸命, 勉強, 名詞 all read; a Japanese -> Chinese entry → 学習, 勉学, 怠惰 read and 学习, 勤学,
懒惰 plain; the mirror image likewise. `overhead_px()` already measured whatever it was given, so
the window grows with the new readings unchanged - a test asserts it.

**Tests**: 903 -> 952 (+46 in `tests/test_dictionary_ruby.py`, +3 in `test_dictionary_flow.py`;
one flow assertion updated on purpose - the result window now also receives `source_lang`), 0
failed, 0 skipped. Twelve mutations - the shared Japanese rule removed or extended to an unknown
source, the stated source ignored, no arrow cut, the first separator instead of the last, the
sides swapped, Word Type back to a source field, Traditional unrecognised, the title or the
window or the lookup dropping the source - each made the suite fail and was restored.

### Phase J2 — Language identity from evidence: `src/core/lang_id.py` (2026-10-15)

The core the remaining language-identity phases build on. **No behaviour changes yet** - nothing
calls it until J3.

**Added**
- `src/core/lang_id.py` (pure logic): `resolve(text, *, known, context, model)` answers what
  language a CJK text is, in Decision 22's order - what the caller knows, then evidence in the
  text, then evidence in its context, then the language a model call reported - and returns
  `Verdict(language, evidence)` saying which step answered. Evidence beats the model: kana in the
  text wins over a model that said Chinese. Also `normalize_language()` (every spelling the app
  meets - the hotkey list's "Chinese Simplified", nlp_manager's "Chinese (Simplified)", codes,
  native names, what a model writes, "Unknown" -> None), `han_evidence()`, `has_kana()`,
  `has_chinese_glyph()`, and the ruby hints `ruby_hint()` / `output_hint()` (TODO.md §5.1).
- `tests/test_lang_id.py` (123 tests): 311 kanji-only Japanese words, 149 Simplified and 164
  Traditional Chinese words, Chinese sentences, Japanese sentences with Chinese names.
- `CrossTrans.spec`: the four codecs the glyph sets come from as hidden imports - they are looked
  up by name at run time, where PyInstaller cannot see them. If one is still missing, glyph
  evidence switches itself off with a `[LangID]` warning instead of misreading every kanji.

**Evidence rules, measured on the fixtures**
- Kana is Japanese - but not U+30FB "・", which Chinese writes between the parts of a foreign
  name (列夫・托尔斯泰).
- A kanji only Japanese writes is Japanese; one Japanese cannot write (outside JIS X 0213) is
  Chinese, Simplified when GB2312 has it. Both kinds together prove nothing.
- Result: **0** Japanese words called Chinese, **0** Chinese strings called Japanese. Settled by
  glyph alone: Japanese 55/311 (23 of the 54 F9 words), Simplified 80/149, Traditional 3/164 -
  the rest is ambiguous by nature and waits for context, a model's verdict or the user.
- `han_evidence()` on 3,000 kanji: about 0.6 ms warm (budget 5 ms).

**Fixed during implementation**
- **Plain Big5 was the wrong Traditional set** - a third character-set trap, next to TODO.md
  F9's CP932 and GBK. Hong Kong's standard forms 衆 裏 綫 衞 啓 峯 are outside Big5 but inside
  CP932, so the first version called 12 of 13 Hong Kong strings (這裏, 公衆, 路綫, 衞生 ...)
  Japanese - Japanese readings on Chinese text. "Japanese-only" now excludes Big5-HKSCS too
  (Decision 24). The cost, measured: Japanese-only glyphs 959 -> 571, because HKSCS also carries
  Japanese forms (駅 発 円 県 込); 22 of the 311 Japanese words lose their glyph evidence and
  become ambiguous - unknown, never Chinese.

**Tests**: 780 -> 903 (+123 in `tests/test_lang_id.py`), 0 failed, 0 skipped. Sixteen mutations -
the middle dot counted as kana, plain Big5, CP932 for "can be Japanese", a conflict counted as
Japanese, the Chinese variant flipped, the model or the context put before the text's own
evidence, the context ignored, `known` ignored, each hint rule, "Unknown" read as a language, a
missing codec undetected, the log line dropped - each made the suite fail and was restored.
Coverage is written to `logs/lang_id_coverage.json` on every run.

### Phase D13-D15 — One Dictionary mode, and the two bugs its copies shared (2026-10-15)

Dictionary mode was written twice: once for the main window's Dictionary button
(`dictionary_popup.py`) and once more inside the quick-translate popup (`quick_translate.py`,
~400 lines). Every change had to be made twice, and the copies had already drifted. The user asked
for the duplication and its two bugs to be fixed before the remaining language-identity phases,
all three of which (J3, J5, J6) would otherwise have been written twice again.

**Changed**
- **One implementation** (`DictionaryPopup`, Decision 23). The popup's Dictionary button now
  hands its text, its target language and itself to `DictionaryPopup.open_from_text(text,
  target_language=..., anchor=...)` through one new callback, `on_open_dictionary`. Removed from
  `QuickTranslateManager`: `_show_nlp_required_message`, `_show_language_selection_dialog`,
  `_open_dictionary_with_language`, `_try_open_dictionary_tab`, the `on_dictionary_lookup` and
  `on_open_settings_dictionary_tab` callbacks and the popup's own `ToastManager`, which only that
  code used. Removed from `app.py`: `_on_quick_translate_dictionary_lookup` and
  `_show_quick_translate_dictionary_result` (the popup's copy of the lookup) and
  `_show_settings_dictionary_tab` (identical to `_show_settings_tab("Dictionary")`).
- **Where the windows go** is now two pure functions: `word_window_geometry()` - beside the popup
  when opened from it (below, else above, else pinned to the bottom of the work area), centred on
  the work area under the mouse otherwise - and `dialog_geometry()` - a dialog centred on the
  pointer, inside the work area. The word window is 700x350 (1000x700 expanded) from both buttons;
  the popup's copy used 650x350 (900x600). The main window's dialogs now open next to the pointer
  instead of in the middle of the screen, as the popup's always did.
- The word window's title reads the trial quota live from the service, from both buttons (the
  popup's copy showed the count from when the translation arrived).
- An NLP pack is checked live when the button is pressed. The main window used to trust the
  button's state from when it was drawn, so a pack installed since then still got "No Language
  Pack Installed".

**Fixed**
- **D14 - a failed lookup showed nothing.** Both copies ended in
  `after(0, lambda: toast.show_error(f"Lookup failed: {e}"))`; Python unbinds `e` when the
  `except` block ends, so Tk ran a lambda that raised `NameError` and the user saw no message. The
  message is now bound before the callback, logged as `[Dictionary] Lookup failed: ...`, and the
  Lookup button's "Looking up..." animation is stopped (the main window's copy never stopped it on
  a failure; neither copy stopped it when every selected word filtered out as punctuation).
- **D15 - the main window's two Dictionary dialogs used `transient()` + `grab_set()`**, the
  pattern CLAUDE.md forbids. Both now use topmost + `lift()` + `focus_force()` +
  `after(100, topmost off)`, built once in `_new_dialog()`.
- **`DESIGN_DECISIONS.md`**: Decision 3 quoted the developer's choice in Vietnamese; it is now
  English ("One row, widened"), per the project rule.

**Found, not fixed** - recorded as `DEFERRED.md` **D16**: `UpdateFailedDialog` (shown at startup
after a failed update) makes a `grab_set()` + `transient(root)` + `wait_window()` dialog on the
*withdrawn* root - the exact trap in CLAUDE.md's Known Issues, which leaves an invisible modal
window and a frozen app. Three more dialogs call `grab_set()` without `transient()`.
`app.py` `_open_settings_dictionary_tab()` has no caller (pre-existing; left alone).

**Tests**: 755 -> 780. The eleven wiring tests moved from `test_dictionary_prompt.py` to the new
`tests/test_dictionary_flow.py` (36 tests): both buttons down to `dictionary_lookup()` - the popup
path now through the real `TranslatorApp` callback and the shared flow - plus placement, the
lookup's result and failure paths, and the dialogs. Fifteen mutations - the D14 lambda put back,
`grab_set()` put back, topmost never released, the popup's target, anchor or text dropped, the
dialog forgetting either, each geometry rule, the settings link - each made the suite fail and was
restored. The real flow was also opened from both buttons with the real word chips and NLP
(window 700x350 centred from the main window; directly under a 180 px popup from the popup).

### Phase J0-J1 — The dictionary knows which language it looks up (2026-10-15)

First two phases of the Japanese language-identity work (`TODO.md`): furigana wherever Japanese
appears, and a Dictionary that no longer takes a Japanese word written only in kanji for Chinese.
The user's answers to the plan's ten questions are recorded in `TODO.md` §3; Q1 (the AI model
decides what ambiguous kanji-only text is, the user settles what it cannot) is Decision 22.

**Measured before changing anything** - `tools/eval_dictionary_prompt.py`, real API calls, ten
kanji-only words whose Japanese and Chinese senses differ (手紙 letter / toilet paper, 汽車 steam
train / car, 床 floor / bed ...), target English. "Japanese" = field 2 said Japanese and field 1
gave the Japanese sense:

| | gemini-2.5-flash | gpt-oss-120b (Groq) | llama-3.3-70b (trial) |
|---|---|---|---|
| Old prompt - the headword alone | 7/10 | 7/10 | 7/10 |
| New prompt - Japanese sentence sent, source stated | **10/10** | **10/10** | **10/10** |

The old prompt failed on the same three words for all three models: 汽車 "car", 工作 "work",
床 "bed". With the new prompt all thirty answers give the Japanese sense and a hiragana reading.

**What it does not fix yet - a headword alone**, with no source stated and no context (the user
selected 結構 by itself, and detection called it Chinese): gpt-oss-120b gave the Japanese sense
6/10 with the new prompt against 7/10 with the old one - one run each, within noise, and no
better, as expected: there is nothing new for the model to decide from. Gemini's numbers for this
case are missing (its free quota on the first key ran out). That case belongs to J4/J5.

**Added**
- `src/core/dictionary_prompt.py` (pure logic): `build_dictionary_prompt()`,
  `extract_context()`, `dictionary_source_language()`, `DICTIONARY_CONTEXT_MAX_CHARS = 600`.
- `tools/eval_dictionary_prompt.py` - manual measurement of real models (never run in CI). Uses
  the real `dictionary_lookup()`, one key per provider, no health manager and no rotation, so the
  provider measured is the one that answers; never writes `config.json` (verified by hash
  before/after every run). `trial` is opt-in because it spends the daily trial quota. Each row
  carries a `prompt_version` hash so different wordings are never pooled.
- `tests/test_dictionary_prompt.py`.

**Changed**
- **The dictionary prompt states the source and target language** and, for a Japanese source,
  that a kanji-only headword is still Japanese (手紙 is "letter", not the Chinese "toilet
  paper"). Field 2 is fixed to the stated source.
- **It sends the context**: the sentences of the analysed text that contain a headword,
  de-duplicated, capped at 600 characters. A phrase typed into a custom box gets none, and a
  context that is only the headword is dropped. The text was already sent for translation, so
  this is not new exposure - but the dictionary call now carries it too.
- **Pronunciation follows the source**: Japanese = the reading in hiragana only, no romaji, no
  IPA (the user's choice); Chinese = pinyin with tone marks; Korean = Revised Romanization;
  others keep /IPA/ + a target-language phonetic.
- **Source = target gives a monolingual entry** (国語辞典-style): definition and examples in the
  same language, field 1 a simpler equivalent. Word Type is now written in the target language.
- **Which language is stated** - `dictionary_source_language()`: a language the user picked in
  the selection dialog, or an auto-detected Japanese (detection needs kana to say it). Any other
  detection is a guess - every kanji-only text comes back "Chinese (Simplified)", every Latin
  text the first installed European pack - so the prompt says "not given" and the model decides
  and names its decision in field 2.
- Both Dictionary windows pass the language and the text: `dictionary_popup.py`
  (`_open_with_language(..., user_chosen)`, `_do_lookup(..., source_language, context_text)`),
  the popup's copy in `quick_translate.py` (`_open_dictionary_with_language(..., user_chosen)`,
  the lookup callback's new keywords) and `app.py` (`_on_quick_translate_dictionary_lookup`).
- Log line `[Dictionary] lookup n=.. source=.. target=.. context_chars=..` - counts, never text.

**Fixed during implementation**
- **A tie-break that leaned Chinese.** The first wording of the "source not given" rule told the
  model, without context, to "choose the language in which it is more commonly written exactly
  as given". gpt-oss-120b then turned 先生 alone from Japanese "teacher" (old prompt) into
  Chinese "Mr."; with the sentence removed it answered "teacher" again. One run each, so weak
  evidence - but the bias is built in: Chinese text is more abundant, so "more common" means
  Chinese for every shared spelling. The model now decides from the headword itself, and a test
  keeps the tie-break out (Decision 21).

**Repository**: `h1-health-review` was merged into `main` (`f28a276`, `--no-ff`, not pushed) and
this work branches from it as `feature/japanese-language-identity`.

**Known limits until later phases**
- A kanji-only selection (勉強 alone) still opens the Dictionary window as "Chinese (Simplified)"
  and its chips stay plain - J5. The lookup itself is left to the model, which without context
  still reads 汽車, 工作 and 床 (and on the last run 結構) as Chinese.
- The result window still takes its reading hint from the model's field 2 - J3.

**Tests**: 676 -> 755 (+79 in `test_dictionary_prompt.py`), 0 failed, 0 skipped. Seventeen
mutations - each call site's language or text dropped, the dialogs forgetting the choice was the
user's, the trust rule trusting every detection, the context filter, the kanji rule, the
hiragana rule, the monolingual check, the tie-break put back - each made the suite fail and was
restored.

### Cerebras and SambaNova, and a correction (2026-09-08)

Keys were supplied for Cerebras, Groq and SambaNova, so three more rows of D11 could be checked
against the real APIs.

**Fixed**
- **Cerebras: all six models in the dropdown and both defaults were dead.** `llama-3.3-70b` and
  `llama3.1-70b` answered `404 Model does not exist` to a real request. Cerebras now serves
  exactly three models. Defaults are `gpt-oss-120b`, `qwen-3.8-27b`.
- **SambaNova: eleven of twelve dropdown models and one of two defaults were gone** - every
  DeepSeek-R1 variant, the whole Llama 3.1/3.2 line, all three Qwen entries.
  `Meta-Llama-3.3-70B-Instruct` survived and stays first; `gemma-4-31B-it` replaces the dead
  `Meta-Llama-3.1-70B-Instruct`.
- **A Cerebras key was being read as Google.** `csk-` was missing from `API_KEY_PATTERNS`, and
  `_detect_provider_from_key()` falls back to Google, so a Cerebras user with Provider on 'Auto'
  and a blank model field was handed `gemini-2.5-flash` and sent it to `api.cerebras.ai`. Silent,
  and indistinguishable from a dead model. SambaNova cannot be fixed the same way - its keys are
  bare UUIDs with no prefix to match.

**Confirmed working** - Groq's defaults, by real translation: `openai/gpt-oss-120b` 0.7 s and
`openai/gpt-oss-20b` 0.6 s, both returning clean Japanese with their reasoning in a *separate*
`reasoning` field rather than inline in the content.

**Corrected**: earlier entries said reasoning models risk truncation because `api_manager` sends
`max_tokens: 1024`. That is wrong - `_call_generic_openai_style` sends **no** `max_tokens`, and
the 1024 cap belongs to `_call_anthropic` alone. The measurements and the conclusion are
unchanged (qwen3.6-27b really does take 509 completion tokens and 1.3 s against gpt-oss's 134 and
0.7 s, with `<think>` inline in content); only the mechanism was misstated. The real hard limit
on that path is `timeout=10`.

**Evidence quality, stated per provider** - the point of D11 is not to guess twice:
- *Cerebras* - strong. It validates the model **before** it checks billing, so `404` and `402` are
  a real distinction: 404 proves gone, 402 proves the model exists. The account has no credit, so
  the three live models could not be translated with.
- *SambaNova* - weak, and marked as such. It returns `402` **before** validating the model - even
  for a model absent from its own catalogue - so the listing is the only evidence and no model
  was called.
- *Groq* - strong. Real translations, end to end.

**Tests**: 674 -> 676.

### OpenRouter's defaults were dead too, and pointed at the wrong provider (2026-09-08)

**Fixed** (narrows D11 further)
- **Both OpenRouter defaults were gone.** `google/gemini-2.0-flash-exp:free` and
  `meta-llama/llama-3.3-70b-instruct:free` are absent from OpenRouter's live 428-model catalogue
  **and** have zero routable endpoints. This one needed no API key: both signals are public, and
  they agreed on all twenty IDs checked. Now `google/gemma-4-31b-it:free` and
  `nvidia/nemotron-3.5-lightning:free` - free tier kept by explicit choice (Decision 20), on two
  different upstreams so they fail independently.
- **A default that identifies as the wrong provider.** `_identify_provider()` matches
  `model_provider_map` first and then falls through to prefix rules, in which `google/` means
  **Together**. At tier 3 the new default `google/gemma-4-31b-it:free` identified as Together, so
  under `provider='Auto'` an `sk-or-v1-` key would have been sent to Together's endpoint - and
  **both dead defaults did exactly this too**, so that path was mis-routed as well as retired.
  Every default is now listed in `MODEL_PROVIDER_MAP` for its own provider.
- **Nine of the twenty IDs in the OpenRouter dropdown were dead**: `o1-mini`,
  `claude-3.5-sonnet`, `claude-3-opus`, `gemini-2.0-flash-exp`, `gemini-pro`, `gemini-flash-1.5`,
  `llama-3.1-405b-instruct`, `mixtral-8x7b-instruct`, `qwq-32b-preview`. This is tier-3 only - the
  Worker rebuilds the list from the live catalogue on every cron - but tier 3 is a fresh install
  with no network, which is where a dead entry is least recoverable.

**Added**
- `tests/test_default_model_routing.py` (32 tests): every default model, for all thirteen
  providers, must identify as its own provider with only `constants.py` available. Probed by
  reintroducing the bug and confirming the suite fails.

**Not verified, and said plainly**: no OpenRouter key was available, so the two new defaults are
confirmed *routable* but not confirmed to translate well. The risk to test when a key appears is
**latency**: `_call_generic_openai_style` sends no `max_tokens` but does use `timeout=10`, and
both of these lean reasoning/agentic - on Groq the comparable model took 1.3 s against gpt-oss's
0.7 s.

**A shortcut that does not work**: OpenRouter's `/endpoints` resource names the upstreams serving
each model, which looked like a free way to verify other providers' native IDs. It lists Groq as
serving `llama-3.3-70b-instruct` while Groq's own catalogue has no llama-3.3 at all - it describes
OpenRouter's routing, not what a user's key can call.

**Tests**: 642 -> 674.

### Google's default models were dead too (2026-09-08)

**Fixed** (narrows D11)
- **All three of Google's auto-pick models answered 404.** `gemini-2.0-flash`,
  `gemini-1.5-flash` and `gemini-1.5-pro` are retired. This is the app's **primary** provider and
  `default_models_by_provider` is not a fallback - it is what auto-detection and
  `_try_model_rotation()` read whenever the model field is left blank, so a user with a Gemini key
  and no model chosen got three silent failures and nothing else. Now
  `gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemini-flash-latest`: the old intent (a mid-tier
  flash model), a faster one to rotate to when the first is busy, and an alias that cannot rot.
- **Six of the eight models in the Google dropdown were dead** as well - the whole 2.0 line,
  `gemini-3-flash` (the live name is `gemini-3-flash-preview`) and
  `gemini-2.5-flash-preview-image`. Replaced with twelve verified IDs.

**Added**
- **`fetchGeminiModels()` in the Worker**, mirroring `fetchGroqModels()`: Google's catalogue now
  comes from Google (Step 5.6) instead of from OpenRouter, which lags it badly - on 2026-09-08
  OpenRouter still listed `gemini-2.0-flash`. `supportedGenerationMethods` alone cannot be the
  filter, because the same endpoint serves tts, image, transcribe, robotics, computer-use, lyria
  (music), nano-banana (image) and the agentic deep-research / antigravity families, so
  `GEMINI_NON_CHAT_PATTERNS` subtracts them: 22 of 40 excluded, 18 general chat models kept.
  `gemini_source` is reported beside `groq_source`.

**Rejected, after simulating it** (Decision 19): filtering the curated defaults against
`model_provider_map`, which is what D11 suggested and what `getProviderModels()` does for the
trial pool. Run across all thirteen providers it would have *kept* `gemini-2.0-flash`, because
the map comes from OpenRouter and OpenRouter still lists it; for the nine OpenRouter-derived
providers the catalogue is exactly as stale as the thing it would check. It would have looked
like a safeguard and removed nothing - the same false-green failure Decision 18 guards against,
one layer down.

**Worth writing down: presence in a listing is not usability.** `gemini-2.5-pro` appears in
Google's own `/models` output and answers `404 no longer available to new users`. Every model
named here was checked with a real translation request, reading the reply code rather than
counting it - `404` is dead, `503` is busy, `429` is out of quota, and two models that looked
dead at first were neither.

**Still open**: nine providers whose defaults have never been checked, because each needs its own
API key - see DEFERRED D11, which now carries the table of what is verified and what is not.

**Tests**: 642 -> 642 (no test asserted these tables). Verified by hand instead: every new Google
ID routes to Google at tier 3, all three tiers agree, and the shipped `fetchGeminiModels` was run
under Node against Google's real payload - 18 models kept, and all four failure paths return null
so the static list survives.

### The suite runs somewhere other than one desk (2026-09-08)

**Added** (closes D10)
- **`.github/workflows/tests.yml`** - the full suite on `windows-latest` for every push and pull
  request, plus manual dispatch. Windows only: the app registers global hotkeys, reads the
  registry and clipboard through pywin32, and draws Tk widgets, so a Linux job would test nothing
  the app does.
- **`tools/check_test_counts.py`, and it is the point of the change.** `conftest.py`'s `tk_root`
  fixture skips when Tk cannot open a display, and **312 of the 630 tests need one** - so a runner
  without a desktop session would skip half the suite, pytest would exit 0, and the badge would be
  green over an untested half. That is worse than no CI: no CI is a known gap, a false green is a
  believed one. The guard reads the JUnit XML and fails the build when more tests were skipped
  than a healthy run explains, or when barely anything was collected. It runs with `if: always()`
  so the counts are reported even when pytest itself failed. See Decision 18.

**Tests**: 630 -> 642. `tests/test_ci_guard.py` (12) pins the guard itself, including the headless
scenario fed as a synthetic report with 312 skips - a check that quietly stops working is exactly
what is being guarded against. The workflow's own commands were run locally end to end:
`pytest --junitxml --cov` then the guard, 642 passed, guard OK.

**Not verified**: whether the GitHub runner has a usable Tk display. That needs a push to find
out. Both outcomes are handled - a diagnostic step reports Tk's availability, and the guard turns
the bad one into a clear failure instead of a quiet pass.

### The log file became machine-readable (2026-09-08)

**Changed** (closes D5)
- **The file log is JSON Lines**, one `{"ts","level","tag","msg"}` object per line, as global
  Rule 10 asks. **The console is not** - `python main.py` prints to a terminal with a human in
  front of it.
- **Not one of the ~458 logging calls changed.** D5 was deferred because the format "touches
  every call site"; it does not, if the tag is derived from the record. 55 messages already open
  with a bracketed tag - `[ModelRotation]`, `[Trial]`, `[TOKENIZE]` - and those are better tags
  than any file name, so the formatter lifts them into `tag` and drops them from `msg`. Everything
  else gets `record.module`, and `mod` is added only when it differs. Writing
  `logging.info("[Thing] ...")` remains the way to set a tag. See Decision 17.
- **The log rotates by size as well as by age.** Retention bounds a quiet app but not one runaway
  loop inside a single day, so today's file is now capped at `LOG_MAX_BYTES` with
  `LOG_BACKUP_COUNT` siblings.

**Fixed**
- **Rotation would have leaked past retention.** `prune_old_logs` globbed `translator_*.log` and
  matched a regex anchored on `.log`, so the `translator_20260908.log.1` files the new handler
  creates were neither found nor eligible - unbounded growth *within* a day would simply have
  become unbounded growth *across* days. Both patterns widened; `.bak`, `.logged` and
  `translator_2026.log.1` are still spared, and a test says so.

**Deliberately not done**: buffered writes, which Rule 10 also suggests. Every ending this app
has skips cleanup - the updater's `os._exit(0)`, the crash hook, the already-running watchdog -
so a buffer would drop exactly the lines worth having. `delay=True` is used instead, which also
stops a run that never logs from leaving an empty file behind.

**Tests**: 610 -> 630. Five probes were run rather than assumed: removing the tag extraction fails
3, `ensure_ascii=True` fails the Japanese-legibility test, `delay=False` fails the empty-file
test, restoring the old prune regex fails the rotated-sibling test, and dropping `.astimezone()`
fails the timestamp test. The Japanese test was tightened first - it originally asserted a round
trip, which `json.loads` satisfies either way, and so proved nothing.

### Launching CrossTrans twice now shows you CrossTrans (2026-09-08)

**Changed** (closes D4)
- **A second instance asks the running one for its window instead of pointing at the tray.**
  The lock socket on `127.0.0.1:47823` had been `listen()`ing since single-instance detection was
  written and nobody ever accepted; all a second launch could do was fail to bind and show a
  dialog telling the user to go hunting in the system tray. It now sends a show request, and the
  running instance raises its window - which is what double-clicking the icon means - plus a
  two-second toast, "CrossTrans is already running", so nobody wonders whether a second copy
  started.
- **What "show yourself" means was not a new decision.** D4 listed it as an open question;
  `app.show_main_window()` has answered it since the tray menu was written. It already marshals
  itself onto the UI thread, and already raises an open popup rather than building a second one.
  The accept loop reuses it. That is what took D4 from Medium to Small.

**Added**
- `single_instance.signal_running_instance()` and `serve_show_requests()`.
- `TranslatorApp.on_second_instance()` / `_raise_for_second_instance()`.

**The acknowledgement is the load-bearing part** (Decision 16). Connecting proves nothing:
`listen()` predates the accept loop, so a connection against *any* older build succeeds and then
rots in the backlog. Seen for real on 2026-09-08 while writing the tests - `netstat` showed the
suite's connection sitting in `CLOSE_WAIT` against the running 1.9.20. Without waiting for a
reply, a user who upgraded and double-clicked the icon would get a second process that exits
silently having done nothing at all - no window, and not even the old dialog. The notice and its
Decision 12 watchdog therefore stay, as the fallback for exactly that case.

**Tests**: 594 -> 610. New `tests/test_second_instance_signal.py` (15). Three probes were run
rather than assumed: trusting a bare connection instead of the ACK fails the older-build test;
dropping the token check lets any stray local connect raise the window and fails another; and
calling the handler straight off the socket thread - a cross-thread Tk call - fails two more.
`TestMainTakesTheNoticePath` was split in two and both halves now stub
`signal_running_instance`: unstubbed it reached the real socket, so whether the notice path ran
depended on whether a CrossTrans happened to be running on the machine.

### The clipboard tests stop borrowing a global (2026-09-07)

**Fixed** (closes D9)
- **`TestCopySelection` no longer reads the Windows clipboard.** Its `_copy()` helper wrote a
  sentinel, fired `<<Copy>>`, then read the value back with `clipboard_get()` - and the clipboard
  is a global any other process can take between those two steps. It cost one failure in six
  full-suite runs, always passing in isolation; the production code was never implicated. The
  helper now captures what the handler writes, by intercepting the widget's own
  `clipboard_clear` / `clipboard_append` for the duration of the call. The event still fires, the
  binding still resolves and `RubyText._on_copy` still runs - only the round trip through a
  shared OS resource is gone. D9 named one test; **five** shared that helper.

**Added**
- `test_it_really_reaches_the_windows_clipboard` - one deliberate round trip, kept so something
  still proves Tk hands the text to Windows. It **skips** on `TclError` instead of failing, so a
  stolen clipboard can never redden the suite again.

**Verified as regression tests** (both probes run, not assumed):
- Making `_on_copy` call `get()` instead of `get_plain()` - the original bug, annotated words
  dropping out of the copy - fails **4** tests, three of them the hermetic ones.
- Removing `return 'break'` fails **2**. Notably it does *not* fail the hermetic ones, and the
  helper's docstring says so: `tk_textCopy` writes through the Tcl `clipboard` command, not
  through the widget's Python methods, so an interception at that level cannot see the default
  binding overwrite anything. That contract is pinned directly by
  `test_the_handler_stops_tk_from_overwriting_it`, which asserts the return value itself.

**Tests**: 593 -> 594.

### Dead code removed (2026-09-07)

**Removed** (closes D8)
- **`src/ui/progress_dialog.py`** (196 lines). A modal progress dialog for long file
  translations that was never wired to anything: no importer in `src/`, `tests/`, `main.py`,
  `src/ui/__init__.py` or the spec file's `hiddenimports`, and no dynamic import reaches it
  either - the only `importlib` in the project loads NLP language packs. The only references to
  `ProgressDialog` were inside the file: its own class statement, its docstring example, and a
  `show_quick_progress()` helper nothing called.
- **`TranslationService._is_dictionary_query()`** (35 lines), unused since auto-dictionary
  detection was taken out - `translate()` stopped switching to dictionary mode for short text,
  and lookup has gone through the Dictionary button ever since.
- **`SENTENCE_PUNCTUATION`** (20 lines) went with it. The removed method was its only reader, so
  leaving it would have replaced one orphan with another.

Both were listed as deliberately-not-done under the "touch only what the task requires" rule;
this is the cleanup pass their trigger asked for. `CLAUDE.md` now records the deletion rather
than describing `_is_dictionary_query()` as present-but-unused, so it is not reintroduced later
to "restore" behaviour that was removed on purpose.

**Tests**: 593 -> 593, no regressions - nothing referenced either symbol. Verified beyond the
suite: `pyflakes` reports no orphaned import left in `translation.py`, the module still compiles,
and an import smoke test loads `src.app`, `src.ui`, `src.ui.quick_translate`,
`src.ui.dictionary_popup` and `src.ui.settings` with the UI module gone.

### Every Groq model the app knew about was gone (2026-09-07)

**Fixed**
- **Groq's whole Llama line is decommissioned, and every list in the project still named it.**
  Checked against Groq's own `/models` endpoint on 2026-09-07: of the 17 IDs hardcoded in
  `constants.py`, **15 return nothing**, and the 2 survivors were `whisper-large-v3` and
  `whisper-large-v3-turbo` - speech-to-text models that were never translation candidates. The
  usable count was zero. Gone with them: `mixtral-8x7b-32768`, `gemma-7b-it`, `gemma2-9b-it`,
  every `llama-3.2-*-preview`, `llama3-70b-8192`, and `distil-whisper-large-v3-en`, which had
  been sitting in the model dropdown as something to translate with. What Groq still serves that
  is a general chat model is four IDs: `openai/gpt-oss-120b`, `openai/gpt-oss-20b`,
  `qwen/qwen3.6-27b`, `qwen/qwen3.8-27b`.
- **Auto-pick was choosing a dead model, and this was live, not a fallback.** The list behind
  auto-detection and `_try_model_rotation()` is `default_models_by_provider`, served from KV -
  and KV takes it from a table hardcoded in the Worker, which the 12-hourly cron never
  regenerates. Its Groq entry was `['llama-3.3-70b-versatile', 'llama-3.1-8b-instant']`. A user
  with a Groq key and a blank model field had both attempts fail before the app gave up. The
  same three-dead-models bug sat in `api_manager.DEFAULT_MODELS_BY_PROVIDER` for the tier-3 path.
- **Screenshot translation could never pick a Groq model.** `VISION_MODELS['groq']` matched
  `llama-3.2-*-vision-*`, `llava-*` and `meta-llama/llama-4-*` - three patterns that now match
  nothing Groq serves. Measured by POSTing a 2x2 PNG to each live model: **`qwen/qwen3.6-27b`
  accepts images**; `openai/gpt-oss-*`, `groq/compound*` and `allam-2-7b` answer
  `400 content must be a string`. The pattern is now `qwen/qwen3*`.
- **The trial proxy's Groq pool started with a 4k-context Arabic specialist.** `getProviderModels()`
  carried a "curated defaults first" safeguard, but it selects with `models.includes(m)` against
  the live catalog - and both curated names were decommissioned, so the filter matched nothing,
  the branch never ran, and the trial fell through to the raw list sorted alphabetically:
  `allam-2-7b` first, then the two agentic `groq/compound*` systems. The safeguard now fires
  because the names in it exist.
- **Reasoning and agentic models are kept out of the trial pool** (closes D6). New
  `TRIAL_MODEL_DENY_PATTERNS` filters `*compound*` (agentic - plans and calls tools, routinely
  outlives the 15 s proxy timeout), `*qwen3*`, `*deepseek-r1*`, `*-r1` (measured: qwen3.6 spent
  239 completion tokens on "Good morning", nearly all inside `<think>`; under a smaller
  `max_tokens` it truncates before reaching the answer, which then arrives empty once the block
  is stripped) and `*allam*`. **`openai/gpt-oss-*` is deliberately not filtered** even though D6
  named it - measured at 46-84 tokens in ~0.8 s with no reasoning preamble, and excluding it
  would leave Groq's trial pool empty. The filter fails open: if it would empty a pool, the
  unfiltered list is kept.
- **`reasoning_format: 'hidden'` is now sent to Groq**, so a reasoning model's monologue is
  suppressed server-side rather than stripped after the fact. It rides on a new per-provider
  `extraBody`, spread into the request body, so Cerebras and SambaNova - which share
  `callOpenAIAPI` - never receive a non-OpenAI-standard field.

**Changed**
- `src/constants.py` - `MODEL_PROVIDER_MAP['Groq']` (17 -> 4), `VISION_MODELS['groq']`.
- `src/core/api_manager.py` - `DEFAULT_MODELS_BY_PROVIDER['Groq']` (3 dead -> the 2 measured to
  answer directly). qwen3 is offered in the dropdown but kept out of auto-pick: it spends ~4x the
  completion tokens inside `<think>`. *(Corrected 2026-09-08: this originally said qwen3 exhausts
  a 1024-token `max_tokens` budget. That path sends no `max_tokens` - the cap is Anthropic-only.
  The token measurements and the conclusion are unchanged.)*
- `cloudflare_worker.js` - `PROVIDERS.groq.defaultModels`, `STATIC_DEFAULT_MODELS_BY_PROVIDER`,
  `STATIC_PROVIDER_MODELS['Groq']`, `STATIC_VISION_PATTERNS['groq']`, and nine dead Groq entries
  in `PROVIDER_MODEL_OVERRIDES` (the `llama-3.2-90b-vision` entry went entirely - Groq was its
  only mapping). Deployed; the KV `models_config` was patched with the two fields the cron
  derives from those tables so the fix applied immediately instead of at the next 12-hourly run,
  and the cron reproduces exactly those values.
- `docs/models_config_template.json` - the same three Groq lists.

**Tests**: 593 -> 593, no regressions. No test asserted the contents of these tables; the three
Groq assertions in `test_api_manager.py` route through `_identify_provider`'s suffix patterns
(`-8192`, `-32768`, `gemma-`), not the model map, so they are unaffected. Verified by hand
instead, against tier-3 (hardcoded) config: all four live IDs now resolve to Groq, where before
the change `openai/gpt-oss-120b` fell through to `OpenAI` (step 5, `'gpt' in name`) and
`qwen/qwen3.6-27b` to `SiliconFlow` (step 10, `'qwen' in name`) whenever no API key was passed.
The Worker's shipped `getProviderModels`, `globMatch` and deny list were executed under Node
against the real live catalog: Groq's trial order is now `gpt-oss-120b, gpt-oss-20b`, Cerebras is
untouched, and a fully-blocked pool falls open rather than empty.

### A second instance that leaves, a log that survives, clean vision output (2026-09-07)

**Fixed**
- **A second CrossTrans no longer hangs forever, invisibly.** Launching the app while it was
  already running left a process resident with no window at all: on the machine this was found,
  one had been sitting there since 2026-08-19 - nineteen days - holding 30 MB and its own
  PyInstaller temp directory. The notice is built by ttkbootstrap's `Messagebox`, which parents
  its dialog with `transient=<the root>`, and `main.py` withdraws that root; Tk withdraws a
  transient window whose master is withdrawn, so the dialog was never mapped and `show()` sat in
  `wait_window()` waiting for a click nobody could give it. Confirmed with py-spy against a live
  hang, and it is the same family as the `grab_set()` trap already in CLAUDE.md's Known Issues.
  The notice is now the stdlib messagebox - a native Windows dialog (class `#32770`), which a
  withdrawn root cannot hide - and a daemon watchdog force-exits the process after
  `ALREADY_RUNNING_TIMEOUT_S`, so no future dialog trouble can strand one either.
- **The EXE writes its log somewhere it can be read.** `setup_logging()` derived the directory
  from `__file__`, which under a onefile build resolves inside the temporary `_MEIxxxxx`
  extraction directory - the one PyInstaller deletes on exit. Every log the shipped app ever
  wrote was thrown away, which is precisely the log anyone asks for after a crash. Measured
  2026-09-07: six orphaned `_MEI*` directories (202 MB), each holding a `logs/translator_*.log`
  nobody could have found. The frozen app now logs to `%APPDATA%/CrossTrans/logs`, beside the
  config file support already asks for; running from source is unchanged.
- **Reasoning tags no longer reach screenshot, image and PDF results.** `<think>...</think>` was
  stripped on all five text paths but on none of the vision ones - `app.py` (image and file
  translation), `screenshot_handler.py` (Win+Alt+S) and `pdf_ocr.py` all call the API manager
  directly, without passing through `TranslationService`. A reasoning model, which the user can
  select and which rotation can substitute on its own, would have printed its whole monologue
  over the screenshot, or fed it into the text a scanned PDF is translated from. The cleanup now
  sits in `_generate_content` / `_generate_content_multimodal` - the two dispatch points every
  call in the class funnels through, the same place the model credit is recorded and for the
  same reason: one site instead of eight return statements.

**Added**
- `src/core/text_cleanup.py` - `strip_thinking_tags()`, the single implementation.
- `logging_setup.resolve_log_dir()` / `is_frozen()` / `prune_old_logs()`. The move to `%APPDATA%`
  creates growth nothing cleans up, so daily logs older than `LOG_RETENTION_DAYS` (14) are
  deleted at startup. Only files matching the exact `translator_YYYYMMDD.log` name are eligible,
  and one that cannot be deleted - another instance holding it open - is skipped, not fatal.

**Changed**
- `main.py` no longer imports ttkbootstrap at all; the already-running branch is one call to
  `_warn_already_running()`.
- `TranslationService._strip_thinking_tags()` delegates to the shared function. It stays because
  the trial proxy does not go through the API manager. Its `import re` went with the old body.

**Tests**: 551 -> 593. New `tests/test_single_instance_notice.py` (11): the notice is the stdlib
messagebox and never ttkbootstrap, the watchdog is armed as a daemon before the dialog and
disarmed after it - including when the dialog raises - and it force-exits with `os._exit`; plus
an end-to-end test that holds the lock port and asserts a second instance really terminates.
`tests/test_logging_setup.py` (14): the frozen path is under `%APPDATA%` and never under
`_MEI*`, source builds are unchanged, and retention deletes only what this module wrote.
`tests/test_vision_cleanup.py` (17): both dispatch points strip while still recording the
credit, `translate_image` / `translate_multimodal` / `_dispatch_call` (the rotation route) all
return clean text, and an unclosed tag is left alone rather than swallowing the answer.
Verified as regression tests: restoring the ttkbootstrap dialog fails the end-to-end test after
a 45 s hang, restoring the `__file__` log path fails 3, removing the pruning call fails 1, and
unwrapping the two dispatch sites fails 5.

---

## [1.9.20] - Model credit, History fixed, ruby like Word (2026-09-02)

### Build guard, and the popup names its model (2026-09-02)

**Added**
- **The quick-translate popup says which model produced the result.** A small dim line at the
  very top: `Translated with gemini-2.5-flash (Google)` — `Fixed with ...` for a grammar fix.
  It matters more here than it looks: the configured model is not necessarily the one that
  answered. Auto-detection picks a model when the field is left blank, and model rotation
  substitutes another when the first one fails, both silently, so comparing two translations of
  the same text gave no way to tell whether you were comparing models or comparing runs.
  - The credit is recorded where the call actually succeeds — `AIAPIManager._generate_content`
    and `_generate_content_multimodal`, which every text and vision request funnels through —
    so it names the model that answered rather than the one in Settings, in one place instead
    of at eight return sites.
  - A **failed** call credits nobody: the value is only written on success, so a note never
    describes a result that does not exist. Failure popups carry no note at all.
  - A **cache hit** credits whoever produced the stored entry (`gemini-2.0-flash (Google),
    cached`), which is why `model_used` is now actually written to history instead of always
    being the placeholder `'Auto'`. Entries stored before this get **no note** rather than a
    made-up one — crediting the model that merely ran most recently would be a quiet lie.
  - Trial mode names its proxy model (`llama-3.3-70b (Trial mode)`).

**Fixed**
- **`build_exe.bat` no longer reports a success it did not achieve.** `ren` fails with
  "Access is denied. A duplicate file name exists" when a file of the target name is already in
  `dist\` — the ordinary case, since the previous release of the same version sits there and
  step 1 cannot delete it while it is running. The script never checked, so it printed
  `SUCCESS! Created: dist\CrossTrans_v1.9.19.exe` for a file it had not created, then ran the
  furigana guard **against that stale EXE** and reported it as verified; the build that had
  actually just been made was left behind as `dist\CrossTrans.exe`. Measured on 2026-09-02: the
  guard passed on the old file's 1156 archive entries while the real build had 1157. The rename
  is now verified by hand (`ren` sets no usable errorlevel), a blocked one exits 1 with an
  explanation, and the parenthesised `if` blocks were replaced with labels — which also removes
  the two cmd.exe parsing traps documented in CLAUDE.md from the finalize step.

**Changed**
- `VERSION` 1.9.19 → **1.9.20** (`src/constants.py`, README badge, CLAUDE.md header).
- `HistoryManager.find_cached_entry()` returns the whole matched entry; `find_cached()` is now a
  thin text reader over it. The entry carries `model_used`, which the note needs.
- The five copies of "trial client if trial mode, else the API manager" in `translation.py` are
  one `_call_model()`, which is also the single place the credit is recorded.

**Tests**: 518 → 551. New `tests/test_attribution.py` (27): the API manager credits the model
that answered and not the configured one, a failed call leaves the previous credit alone,
multimodal counts, trial mode names its proxy, a cache hit reuses the stored credit and an
uncreditable entry gets no note, the credit reaches history so the *next* hit can use it, and on
the popup the note is the top line, is absent on failures, says "Fixed" for grammar, and grows
the window by exactly `ATTRIBUTION_PX` so the text box loses no row. Six more in
`tests/test_furigana_hardening.py` pin the build script: the rename is verified before SUCCESS is
announced and before the furigana guard runs, both failure labels exit 1, and every `goto` has a
label. Verified as regression tests: reverting each of the four production changes in turn fails
1–2 of them, and removing the rename check fails the build-script test.


### History window, ruby selection, a way out of a failed popup (2026-09-02)

**Fixed**
- **Translation History works again.** Nothing was wrong with the stored history — the config
  file held its 100 entries throughout. The window was the problem, twice over:
  - It bound the mouse wheel with `bind_all("<MouseWheel>")` and undid that from a `<Destroy>`
    handler on its own toplevel. A child widget's bindtags include its toplevel, so destroying
    **one row** fired the handler: the first search keystroke, the first deleted entry, even
    clicking out of the search box (which restores the placeholder and rebuilds the list)
    unbound the wheel **from the entire application**. The dialog has no scrollbar, so from that
    moment the history could not be scrolled at all — and neither could anything else.
  - `bind_all` also meant that while History was open it took the wheel away from the popup, the
    dictionary window and the main window.
  The wheel is now bound per widget and re-bound on every row as the list is rebuilt.
- **History no longer locks the app.** It called `grab_set()`, which this project forbids
  outright (CLAUDE.md, Known Issues): a modal grab holds every other window hostage behind a
  dialog the user may not even have in front of them, and the Clear All confirmation is itself a
  Toplevel that has to take input while History is up. Replaced with the documented
  topmost + lift + focus_force + drop-topmost pattern.
- **Selecting Japanese now highlights the annotated words too.** Tk's `sel` tag draws straight
  past an embedded window, so dragging across a sentence highlighted everything *except* the
  words carrying a reading — holes exactly where the readings were, which read as "these words
  are not selected" right next to the bug that meant they were not copied either. The frames are
  painted with the widget's own selection colours, readings included (`#80b8ff` on the selection
  background is unreadable). A caller's own colour — the dictionary's per-word highlights — is
  recorded at insert time and restored on deselect.

**Added**
- **"Open Translator" on a failed quick translate**, next to API Settings. A failure is often
  not an API-key problem: the model refused, timed out, or returned nothing useful, and all of
  those are quicker to retry in the main window. It opens with the source text already in the
  input box and an **empty** output — the failure notice is not carried across. `is_error_text()`
  is now a single module-level predicate in `quick_translate.py`, used both by the popup to pick
  its button bar and by `app.py` to decide what crosses over, instead of the string test being
  spelled out twice.

**Changed**
- **A reading wider than its kanji now spreads them instead of huddling them.** 勉強 under
  べんきょう used to sit centred with a gap on each side, which broke the rhythm of the line.
  Each character gets its own equally weighted grid column, so Tk hands them the same share of
  the surplus and centres each one — landing on the same 1:2:…:2:1 rhythm as Word's
  均等割り付け: half a gap at each edge, a full gap between characters. Measured on 勉強 at
  45 px: left 3, gap 8, right 4. Words whose reading is *narrower* keep a single label and are
  untouched, and a one-character base is never split — there is nothing inside it to spread.

  This is what could be done instead of the **overhang** originally asked for, which was
  measured as impossible: a Tk `Frame` clips its children (a 51 px label in a 40 px frame renders
  at 40 px), so with the reading inside the word's frame its width is a hard floor on the word's
  width — Word gets its overhang from a layout engine with no such containment. Shrinking the
  reading's font cannot close a gap this size either (べんきょう at 7 pt is 45 px against 30 px
  of 勉強 — it would need about 4.5 pt).
- `RubyText.pair_labels()` / `pair_base_text()` replace reading `frame.winfo_children()`: a pair
  now holds one label per character when it is spread, so the old two-label assumption is gone.

**Tests**: 476 → 518. New `tests/test_history_dialog.py` (13) drives the real dialog: the wheel
scrolls over the canvas and over a row, survives a search and a delete, leaves no
application-wide binding, takes no grab, and two dialogs can coexist. New
`tests/test_error_popup_actions.py` (14) covers the predicate, the error bar's contents and
order, and that a failure notice never reaches the main window's output box.
`TestSelectionHighlight` (7) and `TestEvenDistribution` (8) in `tests/test_ruby_text.py` — the latter pins the JIS rhythm, that a narrow reading changes nothing, and that a spread word still reads back whole. Verified as regression tests: against
the previous `history_dialog.py`, 5 of the 13 fail with exactly the reported symptoms.

### Furigana reads like Word — copy, baseline, plate (2026-08-28)

**Fixed**
- **Copying selected text no longer drops the annotated words.** Selecting Japanese in any
  furigana surface and pressing Ctrl+C put only the unannotated characters on the clipboard:
  `これは日本語を勉強しています。` came out as `これはしています。` — 日本語 and 勉強 gone. Tk's
  own `<<Copy>>` exports the selected *characters*, and an embedded window has none. The Copy
  *buttons* were never affected; they already went through `get_plain()`. `RubyText` now handles
  `<<Copy>>` itself and copies the base text only — 日本語, never 日本語(にほんご) — which is
  what was asked for. Partial selections and single annotated words work the same way.
- **Base characters now share one baseline with the text around them.** `window_create`'s
  `align='baseline'` aligns the *bottom of the frame* with the line's baseline, so every word
  carrying a reading sat 6 px higher than the plain kana beside it (measured; all four `align`
  values were tried and none aligns baselines). The plain runs of a ruby-carrying line are now
  raised by the same amount, so the delta is 0 px.

**Changed**
- **The ruby plate is gone.** An annotated word takes the widget's own background instead of
  `#363636`, so it reads as ordinary text with a reading over it rather than a tinted chip —
  the way Word draws ruby. `FURIGANA_RUBY_BG` remains as the fallback and as an opt-in
  (`ruby_bg=`), and the dictionary word chips are unaffected: they carry their own colours.
- **`FURIGANA_RUBY_PAD_X` = 2 → 0.** An annotated word is now exactly as wide as its characters
  unless its reading is wider, so a line of mixed plain and annotated text keeps an even
  rhythm. Measured: frame width 45 px against 45 px of plain characters (was 49).
- **A line carrying ruby got shorter**: 47 px → 42 px. With the plain text lifted, nothing on
  that row hangs below the frame's baseline any more, so the row is the bare frame.
- Readings stay blue (`#80b8ff`) — the last open deferred item, D3, resolved by the user. See
  Decision 9. No code change; the colour the code always asked for was only ever hidden by the
  ttkbootstrap bug F2 fixed.

**Implementation notes**
- The lift is applied per *logical line*, only to lines that actually carry ruby. Lifting every
  plain line instead would have added ~5 px per row to the dictionary result window — most of
  the ~150 px the D1 fix had just removed.
- It is re-applied after every insertion: a Tk tag does not grow into text appended after its
  range, and the dictionary window builds each line one run at a time.
- The line's terminating newline is lifted with it. A newline is a character; left unlifted it
  keeps its full descent and hands 5 px of slack to the last row of the paragraph.
- `layout_rows()` gained a third row kind for plain rows that share a line with ruby, since
  those *are* taller. `RowCounts` and `LayoutModel` grew defaulted trailing fields, so existing
  callers and tests are unaffected.

**Tests**: 460 → 476. `TestCopySelection`, `TestBaselineAlignment` and `TestWordLikeRhythm` in
`tests/test_ruby_text.py`, plus a new `mapped_widget` fixture — the shared `tk_root` is
withdrawn, so embedded frames are never mapped there and report `winfo_y() == 0` forever;
anything measuring where a pair actually landed needs a real Toplevel. Verified as real
regression tests: with the lift and the copy handler disabled, 5 of them fail with exactly the
reported symptoms (33 vs 39 px, clipboard missing the annotated words).

### Deferred cleanup — D1 + D2 (2026-08-28)

**Fixed**
- **Dictionary result window no longer reserves a band of empty space.** `calculate_size()` sized
  it as if it were the quick-translate popup: Segoe UI 11 rows (20 px) against a window that
  renders `DICT_RESULT_FONT` (Consolas 10, 15 px rows), plus the popup's 100 px of chrome and a
  30 px "title bar compensation" on a window whose chrome is 71 px and whose title bar sits
  outside `geometry()` entirely. Measured on the real window: **139 px** of dead space under a
  12-line lookup and **199 px** under a 24-line one — the waste grew with the result, which is
  why `DEFERRED.md` recorded it as a flat "~154 px". Now **15 px** in every case, exactly the one
  spare row `calculate_size()` deliberately adds.
- Dead `Any` import in `src/core/translation.py` (D2), removed while its line was being touched
  for the first time since it was flagged.

**Changed**
- `QuickTranslateManager.calculate_size(text, base_font=('Segoe UI', 11), vertical_padding=100)`
  — the two things it had hard-coded are now parameters. The defaults are the popup's own values,
  so both existing callers are unchanged byte-for-byte (a test asserts the equality). A caller
  that renders in another font must now say so.
- New `DICT_RESULT_CHROME_PX = 71` next to `DICT_RESULT_FONT`. Both halves of
  `show_dictionary_result()` — the window height and the row count derived from it — subtract the
  same constant; a source-level test asserts they cannot drift apart again.

**Tests**: 450 → 458. New `TestWindowFitsItsContent` in `tests/test_dictionary_ruby.py`: the
empty band is non-negative (nothing clipped) and under three rows, for short/long results ×
furigana on/off; the band does not grow with the result; the popup default is untouched. Verified
as real regression tests — 6 of the 8 fail against the previous sizing code.

**Note on the fix's durability**: 71 px is measured on this machine's theme and DPI, like the 100
it replaces. If it under-estimates on another setup the box is slightly short rather than
over-tall, and `RubyText` binds the mouse wheel, so the text stays reachable — this window has no
scrollbar. An exact alternative (build the widget hidden, measure `ypixels`, then set the
geometry) was considered and rejected as too large a change for a cosmetic bug: it reorders window
creation and makes `overhead_px()` redundant at this call site.

## [1.9.19] - Furigana everywhere (2026-08-18)

Japanese text now shows **hiragana readings above its kanji on every surface that can display
it** — the quick-translate popup (both the source block and the translation), the main window,
the expanded view, a new Reading pane under the input box, the dictionary result window, and the
dictionary word chips and custom lookup tags. Detection is automatic; the toggle is
Settings → Hotkeys → "Enable Furigana".

Readings are generated **offline** — no API call, no extra latency, no quota. Accuracy comes from
fugashi/UniDic when the Japanese language pack is installed, and from the bundled pykakasi
otherwise. When a reading cannot be mapped onto its kanji with certainty it is **left blank
rather than guessed**: an absent reading is visibly absent, a wrong one is not.

Also in this release: the storage identity rename to CrossTrans (see its section below —
**it is a breaking change for existing installs**).

Built as eight phases, F0–F7, documented below.

> **Release history note** — 1.9.16 was the last version published to GitHub. **1.9.17 and 1.9.18
> were never publicly released**: they exist in this changelog and in the code, but no user ever
> received them. 1.9.19 is therefore the first public release since 1.9.16 and delivers all three
> versions' features at once, which is why its release notes cover Fix Grammar and Merged
> Translate-or-Fix as well as furigana. Do not assume a changelog entry here implies a shipped
> release.

**Release verification**: `CrossTrans_v1.9.19.exe` built from this tree (65,877,976 bytes) with
the new build guard confirming `pykakasi/data/kanwadict4.db` is present in the packaged archive —
the reading dictionary a fresh install depends on, and whose absence would have degraded furigana
to plain text without any error. Suite: 450 passed / 0 failed.

Published as tag `v1.9.19` on 2026-08-18 with the EXE attached. The auto-update endpoint was
checked against the live release rather than assumed: `tag_name` `v1.9.19` parses to `1.9.19` and
the `.exe` asset resolves, so 1.9.16 installs will be offered the update.

### Phase F7 — Furigana hardening (2026-08-17)

Final phase of "furigana everywhere". No new surface and no visible change — this one is about
the three ways the feature could degrade without anybody noticing: a startup stutter, a tuning
value that exists in two places, and an EXE that ships without the reading dictionary.

**Added**
- `src/constants.py` — a `FURIGANA` section holding every tuning knob: the two cost caps, the
  prewarm sample, the fonts and palette, and the Reading pane's debounce and row cap.
  `furigana.py`, `ruby_text.py` and `app.py` alias them to their existing local names, so no
  call site anywhere else changed.
- `tools/verify_furigana_bundle.py` — build guard. `--source` checks the environment can supply
  `kanwadict4.db` before PyInstaller runs; `--exe PATH` reads the built archive's own TOC (via
  `CArchiveReader`, not a byte search) to confirm it actually got in.
- `build_exe.bat` — runs both checks. A failed pre-flight **aborts** the build; a failed
  post-build check prints a "do not release it" warning as the last thing on screen.
- `tests/test_furigana_hardening.py` (28 tests), all mutation-checked — 21/21 mutations caught,
  including four planted in `build_exe.bat` itself.

**Changed**
- `furigana.prewarm()` now annotates a sample instead of probing availability, and `app.run()`
  actually calls it (on the existing background thread, gated on the Settings toggle).
- `FugashiProvider.tokens()` / `KakasiProvider.tokens()` serialize on the existing module lock.

**Fixed during implementation**
- **`prewarm()` was dead code** — defined in Phase F0, never called by anything. The whole
  dictionary load has been happening on the UI thread at the first Japanese render since then.
- **Probing availability would not have fixed it.** `active_provider_name()` stops at the first
  available provider, but `_refine_compounds()` calls pykakasi on *every* annotation even when
  fugashi is active — so the ~215 ms `kakasi()` construction stayed on the UI thread regardless.
  Measured over four fresh processes: first UI-thread annotation **217.7 ms → 0.6 ms**, with the
  cost moved to a background thread that finishes long before the user can press a hotkey.
- **Concurrent annotation was unsynchronized.** `annotate()` is reached from the UI thread at
  render time and from the translation worker via `generate_furigana()`; a MeCab tagger is not
  documented thread-safe, and prewarm added a third caller. The providers now serialize on the
  lock their constructors already used (~0.3 ms per tokenize, so no measurable cost).
- **`prewarm()`'s try/except was unreachable** — `annotate()` already swallows everything and
  falls back to plain text. Removed; the test now guards that contract instead.
- **`build_exe.bat` verified nothing.** A missing `kanwadict4.db` does not crash anything: the
  provider logs the `FileNotFoundError` and renders plain text, so an EXE with no furigana at
  all looks like a successful build. It is also the *only* provider a fresh install has —
  fugashi/UniDic arrives later, if the user installs the Japanese pack.
- **cmd.exe cannot parse a `::` comment as the last line of a parenthesised block** — it dies
  with "`)` was unexpected at this time" and the build never runs. Hit while writing this phase;
  there is now a test asserting no such line exists in the script.

**Tests**: 422 → 450 (+28). No regressions. Both build-script paths and the pre-flight abort
were run end-to-end against a real 94 MB EXE and a deliberately broken one.

### Phase F6 — Dictionary word chips and custom-box tags (2026-08-10)

Seventh phase of "furigana everywhere". The clickable word chips in Dictionary mode and the
orange tags in Custom lookup now carry readings. These are embedded widgets with their own
click, hover, selection and right-click-drag behaviour, so most of the work was keeping that
behaviour intact around a chip that is suddenly two rows tall.

**Added**
- `src/core/furigana.py` `annotate_tokens(tokens, text, lang_hint)` — readings for a
  tokenization, generated from the **whole line** and then handed to the tokens. Each token's
  segments concatenate back to that token (I1, per token).
- `src/ui/ruby_text.py` `RubyRow` — a standalone two-row ruby chip (grid: readings above, bases
  below) for surfaces that are not a `Text` widget. Used by the chips, the tags and both drag
  ghosts. `NO_AUTOSTYLE` is now public so every module uses the same ttkbootstrap workaround.
- `WordButtonFrame(..., furigana_enabled=)` and `CustomWordBoxesFrame(..., language=,
  furigana_enabled=)`; both dictionary-mode call sites pass the Settings toggle.
- `WordTag.set_dimmed()` — the drag-dim now covers the reading, which the caller poking at
  `tag.frame/label/close_btn` could not.
- `tests/test_word_chips_ruby.py` (36 tests) + `TestAnnotateTokens` in `tests/test_furigana_core.py`
  (11 tests). All mutation-checked, including the drag paths.

**Fixed during implementation**
- **A wrong reading on split compounds, found by measurement.** The dictionary tokenizer splits
  日本語 into 日本 + 語, and 日本 annotated on its own reads **にっぽん** where the compound is
  にほん. Per-chip annotation would therefore print a wrong reading on exactly the words a
  learner is looking up. Readings now come from the line, and a token that cuts through a
  reading is left bare — the chips for 日本 and 語 show nothing rather than something wrong.
  A plain run *is* clipped to the token (splitting text with no reading cannot make it wrong),
  which is what lets 会い keep 会[あ].
- **Chips were 7 px out of alignment** (measured): `window_create` defaults to `align='center'`,
  so a taller annotated chip lifted the plain chips off its baseline. Both the chips and the tags
  now insert with `align='baseline'`.
- **The custom box clipped its own tags.** `height=1` counts rows of the *base* font, and a tag
  with a reading is taller than one — the F1 height-unit bug again. The box now derives the row
  count from real font metrics, growing when a reading appears and shrinking when it goes.
- **The wheel was dead over every chip** (pre-existing): an embedded widget swallows
  `<MouseWheel>`, and chips cover nearly all of the word area, so a long text could not be
  scrolled at all. Bound on the area and on every chip part.
- **`_show_drop_line` could raise inside a live motion handler**: an unmapped box reports height
  1, making the geometry string `3x-3+...`, which is a `TclError`. Clamped.

**Design notes**
- A word with no reading keeps the **single-label chip it always had**, so non-Japanese
  Dictionary mode is unchanged.
- A tag is annotated **on its own**, unlike a chip: a tag is one lookup phrase the user typed or
  composed, and there is no larger context to read it in.
- Readings switch to white on the orange selection/highlight — `#80b8ff` on `#fd7e14` is
  unreadable.
- Ghosts are built from the same segments as the chip, never from a concatenated reading string:
  取り消し would otherwise preview as the nonsense とけ.

**Tests**: 376 → 422 passed / 0 failed (+46).

### Phase F5 — Dictionary result window (2026-08-10)

Sixth phase of "furigana everywhere". The dictionary result window now shows readings on the
Japanese it displays — the entry headers, definitions, synonyms and example sentences — while the
aligned label columns and the colour-coded lookup words are preserved exactly.

**Added**
- `src/ui/dictionary_render.py` — the render model for this window. `split_dictionary_text()`
  returns `DictRun(base, ruby, color)` items covering the text exactly once, so
  `''.join(run.base)` is the input string (the engine's I1 guarantee, extended to the renderer).
  Plus `field_policy()`, `source_language_hint()`, `runs_to_segments()`, `overhead_px()`.
- `tests/test_dictionary_ruby.py` — 45 tests (headless run model + the real window), every one
  mutation-checked.

**Changed**
- The result widget is a `RubyText` with `base_font=('Consolas', 10)` — monospace is load-bearing,
  `_align_dictionary_text()` aligns the value column with space padding. Verified: all 12 value
  columns still start at exactly the same pixel.
- Its manual `<MouseWheel>` binding is gone; `RubyText` binds the wheel itself, which also removes
  the dead zone over a ruby frame.
- `DICT_RESULT_FONT` replaces the three separate `('Consolas', 10)` literals.

**Fixed during implementation**
- **Word highlighting would have broken silently.** Colours were applied *after* insertion with
  `Text.search()`, and an annotated word contributes no characters, so every looked-up word would
  have lost its colour precisely where a reading appeared. Highlighting is now decided before
  insertion and travels on the run, so a word is coloured *and* annotated.
- **Highlight-first splitting destroyed the readings** (caught by a test, then by inspection): if
  the line is cut at the looked-up word before annotating, the tokenizer receives isolated
  fragments and an all-kanji fragment — which is exactly what a looked-up word usually is (勉強,
  東京) — cannot be annotated at all. The order is now annotate the whole line, then paint the
  colours onto the segments: plain runs split at colour boundaries, a ruby pair is coloured whole.

**Design notes**
- **Pronunciation (field 5) is never annotated.** It holds IPA plus a target-language phonetic
  (`/həˈloʊ/, /ハロー/`); hiragana above katakana is redundant and invites reading it as a
  different word. Matched by label *and* by number, because models renumber.
- **The result declares its own source language**, so `**Source Language**: Japanese` is used as
  the annotation hint for the source-language fields. This closes the kanji-only gap where it
  matters most: a dictionary lookup is usually a bare kanji word (犬, 東京, 勉強), which has no kana
  and is otherwise indistinguishable from Chinese. Resolved **per `## [Word]` entry**, since a
  multi-word lookup can mix source languages. An unrecognized value degrades to no hint.
- **Target-language fields** (Translation, Definition) use the target language as hint, so a
  kanji-only translation such as 犬 gets a reading too.

**Pre-existing, not changed** (reported, per Rule 3): the window has ~154 px of unused height
whether or not furigana is on, because `calculate_size()` measures with Segoe UI 11 while this
window renders Consolas 10 and adds a one-line buffer. The furigana budget itself is exact —
measured 51 px added against 51 px of real extra content.

**Tests**: 331 → 376 passed / 0 failed (+45).

### Phase F4 — Reading pane under the input box (2026-08-07)

Fifth phase of "furigana everywhere". The main window's **input box** now has a read-only
Reading pane beneath it that shows what you typed with hiragana above the kanji. The box itself
stays plain: an embedded ruby frame cannot survive `edit_undo()`, and a caret moving between
embedded windows behaves unpredictably, so the readings live in a separate widget instead of
inline (invariant I3 — editable implies plain).

**Added**
- `src/app.py` `_create_reading_pane()`, `_refresh_reading_pane()`, `_apply_reading_pane_state()`,
  `_toggle_reading_pane()`, `_on_input_modified()`, `_reading_pane_alive()`, plus the
  `READING_PANE_*` constants. The input box and its pane share one container frame, so the gap
  before the language selector is the same whether the pane is showing or collapsed.
- `config.py` `get/set_furigana_reading_pane()` (default `True`) — remembers a manual collapse.
  It is a collapse state, not a second feature switch: the pane exists whenever furigana is on.
- `tests/test_reading_pane.py` — 24 tests: construction, content rules, refresh wiring, the
  collapse toggle, and that the input box is never a `RubyText`.

**Changed**
- `src/ui/settings/hotkey_tab.py` — the Furigana toggle's description said "shows original
  Japanese text with furigana readings + translation", which described the old pipeline-only
  behaviour. It now names the surfaces the toggle actually governs.

**Design notes**
- **Always present, not shown-on-detection.** The pane's position never shifts and the feature is
  discoverable before any Japanese is typed. When there is nothing to annotate it shows a dim
  one-line placeholder rather than mirroring the box above, which would be noise — and would
  also mean re-inserting a pasted 50 000-character document on every edit.
- **One `<<Modified>>` binding, not per-call-site refreshes.** It fires for typing, paste,
  drag-and-drop, undo/redo *and* the programmatic rewrites in
  `_update_translation_with_original()` / `_load_history_item()`, so those call sites needed no
  changes (the plan had them patched individually). Tk only re-fires after the flag is cleared,
  and clearing it fires the event a second time; a 350 ms debounce collapses the pair into one
  render, which also keeps UI-thread annotation off the keystroke path.
- **No `lang_hint`.** The source language is unknown here, so kanji-only input stays plain rather
  than being guessed at — the same rule as the popup's source block.

**Verified empirically**: focus and caret stay in the input box across a refresh, `edit_undo()`
still works (and the pane follows the undo), and the pane's predicted height matches
`Text.count(..., 'ypixels')`.

**Tests**: 307 → 331 passed / 0 failed (+24). Each new test was mutation-checked: breaking the
annotation, the sizing, the `<<Modified>>` binding, the collapse persistence, the collapse state
or the placeholder all make the suite fail.

### Phase F3 — Main window and expanded view (2026-08-07)

Fourth phase of "furigana everywhere". The **main translator window's output box** and the
**expanded fullscreen view** now render furigana. The main window had never shown readings at
all — `translation_queue`'s only consumer routes to the popup — so "Open Translator" from an
annotated popup used to drop them silently. It no longer can: annotation happens where the text
is drawn, so anything that reaches the box is annotated.

**Added**
- `src/ui/ruby_text.py` `insert_output(widget, index, text, lang_hint, enabled, ...)` — the one
  place every surface routes result text through, so the Settings toggle behaves identically
  everywhere and no call site repeats the branch. `enabled` stays the caller's decision: only it
  knows whether the widget is showing a result, an error, or something about to be edited.
- `src/app.py` `_create_translation_box()` — extracted from `show_popup()` so the output box can
  be built and asserted on without starting the application (which registers global hotkeys,
  builds a tray icon and takes the single-instance lock).
- `tests/test_main_window_ruby.py` — 20 tests covering the main-window box, its update paths and
  the expanded window.

**Fixed during implementation**
- **Measurements ignored the widget's real line spacing.** `LayoutModel` hard-coded this
  module's own `spacing1 + spacing3`, but the popup and main-window boxes are built with
  spacing 0, so every logical line was mis-measured by 8 px. The model now reads the widget's
  actual values; a test asserts pixel-exact predictions for spacing 0, 6/2 and the popup's real
  configuration.
- **Copy and Expand from the main window would have handed over kanji-stripped text**
  (`app.py` `_copy_translation` / `_open_expanded_translation` read the box with `.get()`), as
  would the expanded window's own Copy button and its character counter. All now use
  `get_plain()`.

**Changed**
- The expanded view's text box is **read-only**. It was editable "for selection/copy", but a
  disabled `tk.Text` still supports mouse selection and Ctrl+C (verified empirically), so
  nothing is lost — and read-only is what lets it hold ruby without violating I3. Nothing
  consumed its edits. The now-pointless `<KeyRelease>` status refresh is gone with it.
- `ExpandedTranslationWindow.__init__` takes `config` so it can read the furigana toggle.
- `_update_translation_with_original()` and `_update_grammar_result()` replace their
  delete/insert pairs with `clear()` + `insert_output()`; `RubyText` restores the disabled state
  itself, so the manual state juggling is gone.

**Known limitation** (unchanged from F0): the *source* text still cannot be annotated when it is
kanji-only, because the source language is auto-detected and kanji-only strings are
indistinguishable from Chinese. Output text has no such problem — the target language is known.

**Tests**: 286 → 307 passed / 0 failed (+21).

### Phase F2 — Readings on the translation itself, not just the source (2026-08-06)

Third phase of "furigana everywhere". The Quick Translate popup's **output** box is now a
`RubyText`, so a Japanese translation carries readings — previously only the Japanese *source*
block did, which meant translating **into** Japanese (Win+Alt+J, the main use for a learner)
produced no readings at all. Screenshot/OCR, grammar-fix and merged translate-or-fix results
inherit this for free, because they all render through the same popup.

**Added**
- `src/ui/ruby_text.py`
  - `estimate_ruby_overhead_px()` — the extra pixels annotation needs beyond plain text, so a
    caller that already sized its window for plain text adds room instead of re-deriving the
    whole height with a different wrap model.
  - `set_plain()` — flatten a widget before handing it to the user for typing (I3).
  - `fit_height(min_rows=...)` — the popup measures **word** wrap while this class simulates
    **character** wrap, so its row count is a floor, not a replacement.
  - `insert_ruby(..., kanji_fg=...)` — base-character colour per insertion, for callers whose
    own tag carries a foreground (the replace preview's teal).
- `tests/test_popup_ruby.py` — 29 integration tests driving the real `show()`.

**Fixed during implementation**
- **Custom Prompt sent the model a kanji-stripped prompt.** `_handle_custom_prompt_send()` read
  the box with `.get()`, which returns nothing for an embedded ruby frame: measured **8 of 14
  characters** on a normal Japanese sentence. Now `get_plain()`. Entering edit mode also
  flattens the box first, per I3.
- **Phase 0's kanji-only gap is closed for output text.** `東京都` had no kana, so it was
  indistinguishable from Chinese and stayed plain. The popup knows the *target* language, which
  is authoritative for a translation, so kanji-only Japanese output annotates again — while a
  kanji-only result with a Chinese target still, correctly, does not.
- **ttkbootstrap was discarding the ruby colours.** It re-themes standard `tk` widgets at
  construction and drops explicit colour kwargs unless `autostyle=False` (measured: a
  `tk.Label` asked for `fg='#80b8ff'` comes back `#ffffff`, `bg='#363636'` comes back
  `#222222`). So the blue reading colour that has been in the code and the docs all along
  **never actually shipped** — readings rendered white. This predates this work; the old
  renderer had the same problem. ⚠️ **Visible change**: readings are now blue (`#80b8ff`) on a
  `#363636` plate. The `RubyText` widget itself deliberately stays themed so it keeps matching
  the frame around it. (This also means the "pixel-identical" screenshot in Phase F1 was taken
  under plain Tk, where colours are not overridden: the geometry parity it proved holds, the
  colours in it were the intended ones rather than the shipped ones.)
- **`config.get_furigana_enabled()` fell back to `False`** while `DEFAULT_CONFIG` documents
  `True`, so any config file written before the key existed had the feature silently off. Was
  scheduled for F4; fixed here because it gates everything this phase adds.
- **Error text was annotated but not budgeted for.** The height calculation excluded error
  messages while the insertion did not, so a provider error containing Japanese could overflow
  the box. Found by a test written for this phase.

**Changed**
- The Settings → Hotkeys "Enable Furigana" toggle now governs **render-time annotation**, not
  just whether the pipeline generates a notation string. One switch, every surface.
- Replace preview: the translated half is annotated in the matching teal; the struck-through
  original stays plain, because Tk cannot strike through an embedded frame and the text is
  being discarded anyway.

**Verified**
- Screenshots of the popup and the replace preview; ruby label colours asserted numerically
  (base and reading foreground per frame), not judged by eye.
- Audited every read of a ruby-capable widget: no `.get()` remains (I2). Copy and Replace take
  `app.current_translated`, a plain string, so they were never affected.

**Tests**: 257 → 286 passed / 0 failed (+29).

### Phase F1 — RubyText primitive: one renderer, correct sizing (2026-08-05)

Second phase of "furigana everywhere". The ruby drawing code moves out of the Quick Translate
popup into a reusable widget, so the later phases add surfaces instead of copying a renderer.
**The popup renders pixel-for-pixel identically** (verified with a side-by-side screenshot of
the old and new renderers) — every change below is either a bug fix or new capability.

**Added**
- **`src/ui/ruby_text.py`** — `RubyText`, a `tk.Text` subclass that owns ruby rendering.
  - `insert_ruby(index, text, lang_hint)` annotates on the way in; `insert_notation()` consumes
    the legacy `{kanji|reading}` string; `insert_plain()` skips annotation. All three work while
    the widget is `state='disabled'`, so read-only surfaces need no state juggling.
  - **`get_plain()`** — the readback that Copy / Replace / re-send paths need. `Text.get()`
    contributes **zero characters** for an embedded window while still consuming one index, so
    reading an annotated widget with `get()` silently deletes every annotated word. Measured on
    the popup's own sample: `get()` returns 8 of 14 characters, `get_plain()` all 14.
  - `LayoutModel` / `layout_rows()` / `measure_px()` — a `wrap='char'` simulation that predicts
    the pixel height of annotated content. Row heights are **derived from font metrics**, not
    guessed: `frame = ruby linespace + base linespace + 2·pad`, `ruby row = frame + base
    descent`, plus `spacing1 + spacing3` once per logical line. Predictions match
    `Text.count(..., 'ypixels')` **exactly** on every case tested (47 / 86 / 122 / 28 px).
  - `estimate_notation_px()` — lets a caller size its window *before* creating the widget,
    which the popup must do because an `overrideredirect` Toplevel gets its geometry once.
  - `MAX_ANNOTATE_CHARS` (3000) — above this, text is inserted plain. Annotation and frame
    construction run on the UI thread, so a pasted document cannot freeze it.
- **`tests/test_ruby_text.py`** — 49 tests. The wrap arithmetic runs headless through an
  injected `LayoutModel`; the widget tests use a new session-scoped `tk_root` fixture in
  `tests/conftest.py` that skips itself when no display is available.

**Fixed during implementation**
- **Insertion order was reversed** (found by a render probe, not by reading the code): feeding
  runs one at a time to a fixed index put each run *before* the previous one, so
  `私は日本語を勉強しています。` rendered as `しています。勉強を日本語は私`. Insertion now walks
  a right-gravity mark. This bug did not exist in the old renderer (it always appended to
  `END`) — it was introduced and killed inside this phase, and is now covered by two tests.
- **Height unit bug — multi-line ruby was clipped.** The `height` option counts rows of the
  *base* font (28 px measured), but a row carrying ruby is 47 px. The old renderer asked for
  one unit per logical line, so it under-allocated 19 px for every annotated row: fine for one
  line, clipped from the second onwards. Height is now converted from the real pixel
  requirement.
- **Popup height estimate replaced.** `paragraphs * 38 + 30` ignored wrapping entirely; a
  Japanese paragraph that wraps to two ruby rows was budgeted 68 px and needed 103 px. The
  estimate now measures at the actual wrap width.
- **Scroll dead zone over ruby.** An embedded frame swallows `<MouseWheel>`, so the wheel did
  nothing precisely where the annotated text is. Measured: over a ruby label the old renderer
  leaves `yview` at `0.0000`, `RubyText` scrolls to `0.1615`. Every frame and label created is
  now bound to the same handler.
- **Text containing `{`, `|` or `\` lost all its readings.** `generate_notation()` suppressed
  ruby for those strings because the old regex renderer would have turned a literal `{A|B}`
  into a fake pair. `RubyText` parses through `parse_notation()`, which honors the escapes, so
  the guard is gone: `設定{A|B}テストを保存` now shows readings and reads back byte-identical.
- Dead `<Shift-MouseWheel>` binding removed — `wrap='char'` has no horizontal view, so
  `xview_scroll` could never do anything.
- `ROADMAP.md` and the Phase 0 entry said "124 → 204 tests"; the real Phase 0 total was **208**.

**Changed**
- `src/ui/quick_translate.py` — `_render_furigana()` is now a five-line delegate and takes the
  wrap width. `HORIZONTAL_PADDING` moved to module scope so `calculate_size()` and the furigana
  estimate cannot drift apart; added `FURIGANA_SEPARATOR_PX`. New `popup_furigana` attribute
  (reset in `close()`) exposes the widget to the later phases.

**Verified**
- Visual parity: old and new renderers drawn in one window and screenshotted — identical
  glyph positions, colours, plate backgrounds and baselines.
- `get_plain()` round-trips text holding `{`, `|` and `\` through the real popup path.
- No circular imports: `src.ui.ruby_text` pulls in `src.core.furigana` only.

**Tests**: 208 → 257 passed / 0 failed (+49). One Phase 0 test was rewritten
(`test_generate_notation_suppresses_text_holding_delimiters` →
`test_generate_notation_escapes_delimiters_in_the_source`) because the behaviour it pinned was
the guard removed above.

### Phase 0 — Furigana engine: structured segments, accurate readings (2026-08-04)

First phase of "furigana everywhere". **Pure logic only — no UI file was touched**, so the
Quick Translate popup looks and behaves exactly as before except that its readings are now
correct. Groundwork for rendering ruby on every surface in later phases.

**Added**
- **`src/core/furigana.py`** — the furigana engine.
  - `RubySegment(base, ruby)` — a structured segment model replacing the fragile
    `{kanji|reading}` string as the internal contract.
  - **Invariant I1**: `''.join(seg.base for seg in annotate(text)) == text`, asserted at
    runtime and in tests. Annotation can no longer alter the text it describes.
  - `should_annotate(text, lang_hint)` — requires kanji **plus** kana evidence, or an
    explicit language hint. Chinese hanzi no longer qualifies for Japanese readings, while
    kanji-only Japanese (`東京都`, `電源設定`) still annotates when the caller passes a hint.
  - `align(surface, reading)` — maps a whole-token reading onto the kanji runs inside it by
    anchoring on the kana already present. **Fail-safe**: returns `None` rather than guess,
    so no wrong reading is ever drawn.
  - Provider chain `FugashiProvider` → `KakasiProvider`, each built **once** and reused.
  - `_refine_compounds()` — restores whole-compound readings that morphological splitting
    destroys, restricted to all-kanji spans.
  - `to_notation()` / `parse_notation()` with backslash escaping for `\ { } |`.
- **`tests/test_furigana_core.py`** — 80 tests: detection matrix, aligner (incl. every
  fail-safe branch), I1 over a 19-case corpus, notation escaping round-trip, whitespace
  preservation, the pair cap, and the reading-quality regressions below.

**Fixed**
- **Okurigana covered by ruby** — `取り消し` produced `{取り消|とりけ}し`, the ruby spanning
  the り, because the old code stripped only a *trailing* kana suffix. Now
  `{取|と}り{消|け}し`. Same class fixed for `話し合い`, `申し込み`, `生き物`.
- **Wrong homograph readings** — `今日は雨` gave こんにち; now きょう (morphological context).
- **`kakasi()` rebuilt on every call** — measured ~175 ms to construct versus ~0.3 ms to
  convert. Now a lock-guarded singleton, plus a 256-entry `lru_cache` on annotation.
- **Notation injection** — source text containing a literal `{a|b}` was parsed back as a
  real ruby pair and rendered as "a" with the reading "b". The segment model makes this
  structurally impossible; until the renderer consumes segments (Phase 1), the legacy wire
  format additionally suppresses ruby for any text holding `\ { } |`.
- **Multi-line text lost all ruby** — tokenizers normalize whitespace away, which broke the
  round-trip check. Annotation now runs on whitespace-free chunks and re-inserts separators
  verbatim, so newlines, CRLF, tabs and blank lines survive.
- **Misleading counter readings** — `2日` is *futsuka*: the digit carries part of the reading
  and cannot take ruby, so drawing カ over 日 alone invited "ni-ka". Counters following a
  digit are now suppressed, which also removes real errors (`2人` is *futari*, not ni-**nin**;
  standalone `1月` reported ツキ instead of ガツ).
- **Compound readings broken by splitting** — UniDic tags 日本 as a proper noun reading
  ニッポン, so `日本語` came out にっぽんご and `日本人` にっぽんにん. Both correct now, and
  `東京駅` → とうきょうえき, `中国語` → ちゅうごくご.
- **Chinese text was given Japanese readings** — the pipeline gate matches U+4E00-U+9FFF, so
  hanzi qualified. `你好世界` produced `{你|}{世界|せかい}` — note the **empty** reading on 你,
  which would have rendered a blank ruby label. Both are gone.
- **Misleading log message** — the old `"pykakasi not installed"` warning did not fire when
  the package imported but its bundled dictionary data was missing, which is the likely
  packaging regression. Provider failures now log the actual exception.

**⚠️ One behaviour change: kanji-only source text no longer gets furigana from the hotkey path.**
Ruby now requires kanji **plus** kana evidence, or an explicit language hint. A sentence
(`今日は雨が降る`) is unaffected — it has kana. But a kanji-only selection (`電源設定`, `東京都`,
`翻訳`) used to be annotated and now is not, because the pipeline calls
`generate_furigana(selected_text)` with no hint and **cannot tell Japanese kanji from Chinese
hanzi**: the same permissive check that annotated `東京都` is what annotated `你好世界`.
This is the deliberate "blank beats a wrong reading" trade — a lost reading is visibly absent,
whereas a wrong one is unfalsifiable at the point of use. Phase 2 closes the gap by threading
the real source language from the surfaces that already know it (the popup, and the dictionary's
`_open_with_language`), at which point kanji-only Japanese annotates again *without* also
re-annotating Chinese.

**Changed**
- `src/core/translation.py` — `_is_japanese_text()` and `generate_furigana()` are now
  two-line delegates onto the new module. `generate_furigana()` gained an optional
  `lang_hint`. The queue tuple shapes are **unchanged** (arity is the discriminator in
  `app.py:_check_queue`, so extending it positionally would abort the drain loop).

**Verified**
- Packaging: `collect_data_files('pykakasi')` at `CrossTrans.spec:15` is load-bearing and
  sufficient — proven with two minimal one-file probe EXEs (with data: readings work in the
  frozen EXE; without: `FileNotFoundError` on `kanwadict4.db`, swallowed into a silent
  no-furigana state). No new packaging risk from this phase.

**Tests**: 124 → 208 passed / 0 failed. No regressions; the pre-existing tuple-shape
assertions in `test_translate_or_fix.py`, `test_fix_grammar.py` and `test_freeform_prompt.py`
all still hold.

### Storage identity renamed to CrossTrans (2026-07-01)

The app's internal **storage identity** — the `%APPDATA%` config folder, the model-config cache folder, the Windows auto-start registry value, and the DPAPI encryption entropy/description — was renamed from the legacy product name to **`CrossTrans`**, matching the user-facing name already in `src/constants.py`. A fresh install now uses `%APPDATA%\CrossTrans\` throughout.

### ⚠️ Breaking change (existing installs)
- **Saved API keys must be re-entered.** Keys are DPAPI-encrypted with an app-specific entropy that changed as part of the rename, so keys stored by an older build can no longer be decrypted and are cleared on load.
- **Settings/history do not carry over.** The new build reads `%APPDATA%\CrossTrans\config.json`; the old build's folder is no longer consulted.
- The old `%APPDATA%` config folder is a harmless leftover — delete it manually if you want the disk space back.
- **Auto-start needs a one-time manual cleanup for anyone who had it enabled.** The old auto-start registry entry (under the previous name) still launches the app, but the Settings toggle now manages the `CrossTrans` entry only — so the toggle reads **OFF** and cannot remove the old entry. To actually stop auto-start, disable it via **Task Manager → Startup apps**, or delete the stale value under `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` once. (On a manual reinstall the stale entry may still point at the *old* exe, so the previous version could keep launching — masked by the single-instance lock — until removed.)
- **No automatic migration was implemented — deliberately**, to keep the rename total (no trace of the old name remains in the project) per explicit request. A migration (old-folder copy + key re-encryption) is a clean future option, but cannot coexist with a "no old-name anywhere" requirement.

### Changed
- `config.py` — `APP_NAME` is now `"CrossTrans"` (drives the config dir and the auto-start registry value name); docstring updated.
- `src/core/crypto.py` — `SecureStorage.ENTROPY` (the DPAPI salt) and `DESCRIPTION` (cosmetic) now use the `CrossTrans` identity.
- `src/core/remote_config.py` — model-config `CACHE_DIR` is now `%APPDATA%\CrossTrans\`.
- `src/utils/updates.py` — the auto-updater batch script now reads/writes the `CrossTrans` auto-start registry value.
- Docs — `CLAUDE.md`, `.github/copilot-instructions.md`, and `OPS_GUIDE.md` path/registry references updated; removed a stale deprecated `.spec` entry from `.gitignore` (the real, tracked build spec is `CrossTrans.spec`).

**Tests**: 124 passed / 0 failed — no regressions. Verified a full-repo case-insensitive search for the old name returns **zero** matches (excluding `.git`).

## [1.9.18] - Merged Translate-or-Fix on the language hotkeys (2026-07-01)

Pressing a **language hotkey** (Win+Alt+V/E/J/C — and any custom language hotkey) on text that is **already in that hotkey's target language** now **fixes its grammar in place** instead of pointlessly "translating" it. One merged AI prompt lets the model auto-decide translate-vs-fix. This makes grammar-fixing reachable without a dedicated hotkey — sidestepping the Xbox Game Bar (`Win+Alt+G`) and Feedback Hub (`Win+Alt+F`) collisions entirely.

### Added
- **`TranslationService.translate_or_fix(text, target_language, skip_cache=False)`** — Sends ONE merged prompt: if the text is already in `target_language` the model corrects only grammar/spelling/punctuation (minimal changes, same language); otherwise it translates. BOTH branches are uncensored and meaning-preserving (offensive words survive — faithful equivalent when translating, verbatim when fixing). Cached/stored under `source_type='merged'`.
- **`TranslationService.do_translate_or_fix(target_language)`** — Language-hotkey orchestrator (mirrors `do_translation`): captures the selection, shares the `last_translation_time` cooldown, generates furigana for Japanese source, queues the same 5-tuple as a translation (`is_grammar=False` — the output is a real language in both branches).
- **Merged cache namespace** — `HistoryManager.find_cached(original, target_lang, source_type='text')` gained a `source_type` param; the merged path reads/writes under `'merged'` so a minimal-change fix is never cross-served as a plain 'rephrase' translation (and vice versa).
- **Config**: `fix_grammar_hotkey_enabled` (default **False**) with `get/set_fix_grammar_hotkey_enabled` — a separate flag registering the global `Win+Alt+G` hotkey.

### Changed
- **`app._on_hotkey_translate()`** — The normal language branch now calls `do_translate_or_fix(language)` instead of `do_translation(language)`. Covers every language hotkey (defaults + custom) since this branch handles all non-special `language` values.
- **No-censor everywhere** — The no-censor rule was added to the plain `translate_text` prompts (both variants) and the screenshot/OCR vision prompt, per user request, so offensive words survive all translations (not just the merged path).
- **`Win+Alt+G` hotkey now OFF by default** — split from the button: `fix_grammar_enabled` (default True) controls only the main-window **button**; the new `fix_grammar_hotkey_enabled` (default **False**) gates the global hotkey registration + tray hint. `hotkey.py`, `tray.py`, `app.py` guard, and the Settings → Hotkeys section (new "Enable global Win+Alt+G hotkey" checkbox) updated accordingly. The button and the merged language-hotkey behavior always work.

### Notes
- **Uncensored output is best-effort and model-dependent** — the prompt can only *request* it; some of the 15 providers/180+ models and the trial proxy enforce hard content filters that may still refuse/mask. Additionally, adding an explicit no-censor instruction to *all* translations can itself increase refusals on some models for otherwise-benign text (accepted tradeoff). Confirm behavior against the configured model.
- **LEAN display consequences** (documented, not blockers): the popup shows the language (not "Grammar") for a same-language fix, and the popup **Re-translate** button re-runs the plain `translate_text` (rephrase), not the merged prompt.

**Tests**: +24 (`tests/test_translate_or_fix.py`) covering the merged prompt content (tie-break + both-branch no-censor + verbatim token via a neutral placeholder, never a real slur), `'merged'` cache namespace isolation (no cross-serve), `do_translate_or_fix` routing/tuple/cooldown/trial/no-selection/history, and no-censor presence in the plain prompts; +2 wiring guards (`tests/test_callback_wiring.py`); updated `tests/test_fix_grammar.py` for the split hotkey flag. Suite: **100 → 124 passed / 0 failed** (0 regressions).

## [1.9.17] - Fix Grammar (2026-06-30)

A new **Fix Grammar** action that corrects the grammar of selected text *in place* — no translation, no rephrasing, no censoring. The output is always the same text in the same language with only grammar/spelling/punctuation fixed.

### Added
- **Fix Grammar hotkey** (default **Win+Alt+G**) — Select text anywhere, press the hotkey, and a popup shows the grammar-corrected text with **Copy** / **Replace** to apply it back into the source app. ⚠️ `Win+Alt+G` is also Xbox Game Bar's "Record that" default; registration fails gracefully (error 1409) if Game Bar holds it, the hotkey is fully rebindable, and the button always works. `Win+Alt+F` is the recommended conflict-free alternative.
- **"Fix Grammar" button** in the main translate window (next to Translate) — Corrects the input box text and writes the result into the output box.
- **Settings → Hotkeys → Fix Grammar section** — "Enable Fix Grammar" toggle (default **ON**) + rebindable hotkey row (mirrors the Screenshot hotkey row), with duplicate-hotkey validation.
- **Tray menu entry** — `Win+Alt+G → Fix Grammar` listed with the other hotkeys (shown only when the feature is enabled).
- **`TranslationService.fix_grammar(text)`** — Builds a strict correction prompt (fix grammar/spelling/punctuation only; never translate, paraphrase, change meaning/tone, or censor — including offensive words; return unchanged if already correct), calls the API, strips thinking tags. Not written to history.
- **`TranslationService.do_grammar_fix()`** — Hotkey entry point: captures the live selection (Ctrl+C), honors a dedicated cooldown (`last_grammar_fix_time`), surfaces trial info, and queues a 6-tuple `(original, corrected, "Grammar", trial_info, None, True)`.
- **Config**: `FIX_GRAMMAR_HOTKEY_DEFAULT="win+alt+g"`, `fix_grammar_hotkey` + `fix_grammar_enabled` (default `True`) in `DEFAULT_CONFIG`, with `get/set_fix_grammar_hotkey` and `get/set_fix_grammar_enabled`.

### Changed
- **`HotkeyManager.register_hotkeys()`** — Registers a `__fix_grammar__` hotkey (gated by `fix_grammar_enabled`, so disabling frees the combo); fails gracefully on conflict like the other hotkeys.
- **`app._on_hotkey_translate()`** — Added a guarded `__fix_grammar__` dispatch branch (additive; the translation path is untouched). Source-window HWND is captured first so Replace works.
- **Quick Translate popup** — `show(..., is_grammar=False)` hides the translation-only buttons (Re-translate, Dictionary, Custom Prompt) for grammar results, keeping Copy / Replace / Open Translator. `show_loading(..., loading_text=...)` shows "Fixing grammar…" instead of "Translating to …".
- **`_check_queue()`** — Now also handles the 6-tuple grammar result and routes it with `is_grammar=True` (4- and 5-tuple translation paths unchanged).

### Notes
- **No prompt fully guarantees uncensored output across all 15 providers/180+ models** — some have hard content filters that may refuse or soften sensitive input (the trial proxy may too). The prompt is engineered to preserve text verbatim; behavior should be confirmed against the actually-configured model.

**Tests**: +13 (`tests/test_fix_grammar.py`) — `fix_grammar` prompt content (never-translate / no-censor / same-language / verbatim token preservation) + empty guard + thinking-tag strip; `do_grammar_fix` 6-tuple/`is_grammar` flag + cooldown + error path + no-history; config defaults/fallbacks; hotkey registration wiring. Suite: **87 → 100 passed / 0 failed** (0 regressions).

## [1.9.16] - Translation Cache, Re-translate & Custom Prompt

### R1 — Translation Cache + Re-translate Button
- **History-backed translation cache** — Identical source text with the same target language is served from the existing 100-entry history instead of calling the AI API again (saves quota/cost/latency, consistent output). Applies to plain translations only; custom-prompt requests are never cached.
- **`HistoryManager.find_cached(original, target_lang)`** — Exact-match lookup, most-recent-wins, skips `"Error:"` results
- **`translate_text(..., skip_cache=False)`** — Cache lookup before the API call; early return on hit without re-adding to history (no duplicate entries)
- **"Re-translate" button** (orange) in the Quick Translate popup — Forces a fresh API call (`skip_cache=True`), bypassing the cache so a bad/garbled result is never stuck. Runs off the UI thread (no Tk freeze); no cooldown, no clipboard re-capture
- **`TranslationService.redo_translation(text, target_lang)`** — Forced-refresh path that reuses already-known text and pushes a fresh result to the translation queue
- **Cache-poisoning guard** — `find_cached` only serves `source_type == 'text'` entries, and custom-prompt translations are stored as `source_type == 'custom'`. Prevents a main-window custom-prompt result (or a screenshot/multimodal entry) from being served as a plain-translation cache hit — honors the "custom prompts are never written as a cache match" decision while keeping them visible in the history viewer
- **Decision:** the optional cache on/off toggle from the roadmap was intentionally omitted — the Re-translate button is the escape hatch; cache is also implicitly inert when history is disabled
- **Tests**: +13 (`tests/test_translation_cache.py`) — `find_cached` semantics + `translate_text` hit/miss/skip_cache/custom-prompt-bypass

### R2 — Custom Prompt in Quick Translate Popup
- **"Custom Prompt" button** (teal) in the popup — Makes the translation box editable (keeping the current translation as a starting point) and swaps the button bar to [Send] [Cancel]. The user edits freely and the entire box content is sent verbatim as the prompt, so besides translating they can quickly ask the AI anything about the text
- **`TranslationService.ask_freeform(raw_prompt, target_lang)`** — Raw path that sends the prompt verbatim (no translate wrapper); result pushed to the queue and rendered as a normal popup. Freeform asks are one-offs: never written to history and never served from / written to the R1 cache
- **Edit-mode focus** — Temporarily clears `WS_EX_NOACTIVATE` and force-focuses the box so typing works despite the no-activate popup style; restored to normal on the result popup
- **Single wide button bar** — Popup minimum width widened (560→670px) so all 7 actions + close fit in one row (developer-selected layout)
- **R2-bug fix** — `translate_text()` custom_prompt branch now embeds the source text via `===TEXT TO TRANSLATE===` delimiters. Previously the source text was omitted, so the main-window "additional instructions" feature sent instructions to the API with nothing to translate
- **Tests**: +7 (`tests/test_freeform_prompt.py`) — custom_prompt embeds source text + bypasses cache; `ask_freeform` verbatim/no-history/queue/empty/strip-thinking

### Test suite repair & wiring guard
- **Fixed 20 outdated `test_api_manager.py` tests** — Provider identification now returns Title-Case names (`'Google'`, `'OpenAI'`, …); the 15 provider-id assertions were updated from the old lowercase contract. The 5 Google tests were rewritten from the removed `genai` SDK to the current Gemini REST path (mock `urllib.request.urlopen`)
- **Added `tests/test_callback_wiring.py`** (+5) — Static integration guard that the popup callback signature, the app handlers, and the service methods stay name-consistent (catches wiring typos unit tests miss)
- **Suite: 39 passed / 20 failed → 84 passed / 0 failed** (+25 new tests, 20 repaired, 0 regressions)

## [1.9.15] - Dictionary Improvements & NLP Install Hardening

### Custom Word Boxes Improvements
- **Smart CJK joining** — Custom box tags join without space for CJK characters (`[無礼][講]` → `"無礼講"`), with space for Latin (`[ice][cream]` → `"ice cream"`)
- **Right-click drag reorder** — Drag tags within/between custom boxes to reorder (move semantics, not copy)
- **Drag visual feedback** — Ghost label follows cursor, source tag dims, cyan drop line shows exact insertion point
- **Precise word insertion** — Dragging words from tokenized area inserts at cursor position, not end of box
- **Text selection fix** — Left-click text selection now works properly in custom boxes
- **Surrogate character filter** — Tkinter embedded window placeholders no longer leak into lookup text

### NLP Install Graceful Degradation
- **No more scary errors** — Whitespace-separated languages (Vietnamese, European) gracefully fall back to basic tokenization instead of showing error dialog
- **Basic mode indicator** — UI shows info-blue "ℹ Installed with basic tokenization" for basic-mode languages
- **`whitespace_separated` field** — `LanguagePack` now tracks whether simple tokenize gives usable Dictionary results
- **`nlp_basic_mode` config** — Persists basic tokenization state across sessions

### Auto-Retry NLP Install
- **Multi-Python discovery** — When post-install verification fails, discovers all Python interpreters via `py -0p` and common install paths
- **Automatic retry** — Cleans custom packages dir and retries pip install with each discovered Python
- **Cached Python path** — Successful Python interpreter path cached in config for future installs

## [1.9.14] - Custom Word Boxes & NLP Install Fix

### Custom Word Boxes
- **Manual phrase composition** — New input boxes in Dictionary popup for composing custom lookup phrases when NLP tokenization doesn't detect the desired word/phrase
- **Typed text to tags** — Type text and press Enter to convert into orange tags (same visual as selected dictionary words)
- **Right-click drag from word area** — Drag tokenized words into custom boxes
- **Dynamic boxes** — Add (+) / remove (-) boxes, up to 5 per lookup
- **Combined lookup** — "Dictionary Lookup" button combines selected words from word area + all box content

### NLP Language Pack Install Fix
- **Post-install verification** — `install()` now verifies packages are actually importable after pip succeeds, instead of trusting pip exit code
- **EXE subprocess fallback** — When bundled Python can't import C extensions (version mismatch), falls back to subprocess tokenization via system Python
- **C extension detection** — `is_installed()` detects `.pyd`/`.so` files in custom packages directory
- **Module cache clearing** — Clears parent modules from `sys.modules` for dotted names (e.g., `ufal.udpipe`) to prevent stale cache

## [1.9.13] - Furigana Reading Guides for Japanese

### Furigana Feature
- **Japanese reading guides** — When translating Japanese text, original text is displayed with furigana (hiragana readings above kanji) to help learn pronunciation
- **Offline generation** — Uses pykakasi library for local kanji-to-hiragana conversion (no extra API call)
- **Embedded frame rendering** — Each kanji+reading pair is an inline frame with `align='baseline'` for perfect vertical alignment with surrounding text
- **Word wrap support** — Long furigana lines wrap naturally using `wrap=tk.CHAR` (CJK-friendly)
- **Toggle in Settings** — Enable/disable in Settings → Hotkeys → "Enable Furigana" checkbox
- **Config key**: `furigana_enabled` (boolean, default `True`)

### Dev Runner
- **`dev_run.bat`** — Development script that kills running CrossTrans instance and restarts with console output for debugging
- Uses PowerShell `Get-CimInstance` to find and kill python processes by command line match

## [1.9.12] - Rename & Documentation Overhaul

### Codebase Rename: Tooltip → Quick Translate
- **Renamed `tooltip.py` → `quick_translate.py`** — Feature now consistently called "Quick Translate" everywhere
- **`TooltipManager` → `QuickTranslateManager`** — Class, variables, methods, callbacks all renamed
- **User-facing text** — All UI strings now say "popup" instead of "tooltip"
- **Documentation updated** — README, CHANGELOG, CLAUDE.md, copilot instructions all consistent

### README Overhaul
- **"Translate Anywhere" highlighted as core advantage** — Works in any app, no plugin needed
- **Two translation methods explained** — Text selection + hotkey, or screenshot OCR for non-selectable text
- **Cross-platform workflow focus** — Browsers, IDEs, chat apps, games, images, videos
- **All screenshots added** — 10 screenshots now included in the repository

### Guide Tab Improvements
- **Hotkeys section moved to top** — First thing users see after Getting Started
- **Hotkey intro line added** — Explains that hotkeys activate Quick Translate

## [1.9.11] - Public Release Hardening

- **Cleaned .gitignore** — Ensured no sensitive or dev-only files leak into the repository
- **Standardized API Settings buttons** — All error dialogs now consistently show "Open API Key Settings" button that navigates directly to Settings > API Key tab
- **Fixed trial dialogs bug** — "Open Settings" button in Trial Exhausted and Trial Feature dialogs now renders correctly
- **DPI awareness** — App respects system scaling on high-DPI displays
- **SmartScreen documentation** — Added first-run guidance for unsigned EXE

## [1.9.10] - Replace in Source App & Dictionary Improvements

### Replace in Source App
- **Replace button** — One-click replace selected text with translation directly in the source app
- **Manual Replace mode** (default) — Preview with strikethrough original and translated text, then Agree/Cancel
- **Quick Replace mode** — Immediate paste without preview for faster workflow
- **Gear icon (⚙)** — Dropdown menu next to Replace button for quick access to settings
- **Replace Mode toggle** — Configurable in Settings → Hotkeys → Replace Mode section
- **WS_EX_NOACTIVATE popup** — Popup doesn't steal focus from source app, keeping text selection alive

### Dictionary Mode Improvements
- **Synonyms & Antonyms** — Dictionary now shows synonyms and antonyms with translations (8-field output)
- **Smart word filtering** — Punctuation, symbols, and pure numbers no longer appear as clickable word buttons
- **Unicode letter detection** — Filter works across all languages (Latin, CJK, Cyrillic, Arabic, Thai, Korean)
- **Dedicated mode only** — Dictionary lookup only through the Dictionary button, no auto-detection on short text

### Generic API Guidance
- Removed provider-specific API key links and pricing from all UI dialogs
- Guide tab now shows generic instructions for any supported provider

## [1.9.9] - Dynamic Remote Config & Auto-Update Overhaul

### Dynamic Remote Model Configuration
- **Models updated without rebuilding EXE** — Provider list, model names, and API URLs fetched from Cloudflare KV
- **3-tier fallback** — Remote → Local cache (24h) → Hardcoded defaults; app never blocks on network
- **15 AI providers, 180+ models** — Updated dynamically without app update

### Auto-Update System Overhaul
- **Versioned EXE rename** — New EXE saved as `CrossTrans_v{version}.exe`, old renamed to `.bak`
- **Registry auto-start sync** — Auto-start path updated automatically after update
- **First-launch retry** — Handles Windows Defender scanning delay on new EXE

## [1.9.8.x] - Performance, Dictionary & Stability

### Performance (v1.9.8.1)
- **Settings window opens instantly** — Lazy loading for heavy tabs (API, Dictionary, Guide)
- **NLP pre-warming** — Dictionary tab loads faster on subsequent opens

### Dictionary Mode (v1.9.8.2)
- **Hyphenated words preserved** — Words like "auto-update" stay as single tokens
- **Better sentence detection** — Expanded punctuation detection (55 characters)

### Stability (v1.9.8)
- **Trial mode auto-recheck** — Automatically re-validates API keys every 24h
- **Version upgrade detection** — Clears cache when upgrading to new version
- **Settings refactored** — Split into modular package structure

## [1.9.7] - Screenshot Translation

- **Screenshot Translation** — Win+Alt+S captures screen region for OCR translation
- **Multi-monitor support** — Works across all connected displays
- **Double-click to Preview** — Open attached files with system default app
- **Auto-check updates** — Non-intrusive toast notification on startup

## [1.9.6] - Dictionary Language Pack Fix

- Critical bug fix for Dictionary Language Pack in EXE builds
- Auto-detects system Python when running from EXE

## [1.9.5] - API Key Fix & Google REST API

- Fixed API Key saving position issue
- Animated "Installing..." text for Dictionary Language Pack
- Google provider now uses REST API (EXE 30MB smaller)

## [1.9.4] - HuggingFace Provider

- HuggingFace provider added (14 AI providers total)
- Test button now saves API key even on test failure

## [1.9.2–1.9.3] - Dictionary Mode & Trial Security

- Dictionary Mode with interactive word selection
- Enhanced Trial mode security
- 180+ models from 14 providers

## [1.7.0–1.9.0] - Trial Mode, Windows Hello & Provider Fallback

- **Trial Mode** — Free daily translations without API key
- **Windows Hello Authentication** — Secure API key protection
- **Smart Provider Fallback** — Auto-switch to backup API on failure
- **Scanned PDF OCR** support
- **Toast notifications** and **Search History**
