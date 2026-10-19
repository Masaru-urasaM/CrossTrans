# CrossTrans — Design Decisions

Significant architecture / library / data-model decisions. Prevents re-proposing rejected
approaches. Newest first.

---

### Decision 34 - The quick-translate popup is sized by measuring its real layout, and laid out for reading

**Date**: 2026-10-19
**Status**: RESOLVED - the approach ("B + C") and its details (every TODO.md §3 question as
recommended), the user's choices on 2026-10-19; ships in 1.9.21

**Problem**: The popup was sized before it existed, from constants - `MIN_WIDTH` 670,
`VERTICAL_PADDING` 100, a "+1 line" buffer, `ceil(width / available)` for word wrap - and the
constants had drifted from the widgets. Measured on 13 cases (TODO.md §4): the action bar needs
735 px, so on every short result the close button is not drawn - and Copy does not close the
popup; one word sits in a 670×161 box of which the text covers 1%; every text has a
~28 px blank band under it; Latin lines run 99-111 characters (WCAG 1.4.8: at most 80); a long
Japanese source with readings made the popup 1012 px tall on a 1080 px screen, across the cursor's
line, with 156 px of the source hidden and no scrollbar.

**Options considered**:
1. **A - patch the estimator** (the minimum width from the real bar, the constants corrected, a
   scrollbar) - Pros: small. Cons: the bar still holds every popup at 735 px or more, lines stay
   long, and the next widget change drifts again.
2. **B - measure the real layout, size for reading** - Pros: exact on every machine, font and DPI;
   a readable line length; a height cap with a scrollbar; the translation first; never over the
   cursor. Cons: a two-step show; reopens "measure the built widget", rejected in Decision 8
   (Phase 1 addendum) and Decision 10 (option 4).
3. **C - lay the popup out again** - a header with an always-visible close button, a compact action
   bar, a collapsible original block, optionally resizable. Pros: lets a short result be small.
   Cons: changes a familiar look; supersedes Decision 3.
4. **B + C.**

**Resolution**: **B + C**, chosen by the user on 2026-10-19 ("do B + C"). Why the earlier
rejection of measuring no longer holds - each premise measured the same day on a private desktop:
- *"The window must be sized before the widget exists"* - still true of a **withdrawn** window:
  Tk does not lay out the children of an unmapped Toplevel (the box stays 1 px wide; `count
  -ypixels` gave 10180 px for a paragraph needing 160). But a window mapped at `-alpha 0` is laid
  out normally, and Tk 8.6.15's `text sync -command` (TIP 438) signals when the line heights are
  current. Requested sizes (`winfo_reqwidth/height`) are known even before mapping, so the width is
  decided first and only the heights wait.
- *"It would flash at the wrong position"* - it is transparent until it has been measured and
  placed.
- *"Rendering off-screen doubles the construction cost"* - nothing is built twice. The measuring
  step costs 2-8 ms on 11 of the 13 cases, 17 ms on a Japanese paragraph with readings, 114 ms at
  the 3000-character annotation cap (whose `show()` already takes 278 ms).
- The alternative, a pure word-wrap model, matched Tk on 61 of 65 (width, text) pairs - close, not
  exact.

Rejected: **A** alone - it treats the symptoms and keeps the 735 px floor. **Decision 3** (one wide
bar) is superseded; the bar's new style is the user's choice (TODO.md Q1).

**Implemented, 2026-10-19** (P1-P4 in one pass, at the user's request; branch
`feature/popup-sizing`). `src/ui/popup_layout.py` makes the decisions as pure numbers;
`QuickTranslateManager` measures and applies them. The same 17 popups before and after
(`tools/popup_gallery.py` on the TODO.md corpus):

| | Before | After |
|---|---|---|
| Close button drawn | 12 of 17 | 17 of 17 |
| Blank band under the text | 2-37 px (28 typical) | 0 px in every case |
| Characters per line, Latin, worst paragraph | 99-111 | 66 |
| One word | 670×161 | 395×136 |
| Kanji term with the trial line and the chooser row | 670×232, "Get Free API Key" cut | 395×209, nothing cut |
| Long Japanese with readings | 800×1012 across the cursor's line, 156 px hidden, no scrollbar | 521×619 (the 60% cap), below the cursor's line, scrollbars |

Three lessons from the first full run, each now in the code and in a test:
- **The provisional height is the cap, not a guess.** A guess shorter than the chrome had the
  packer squeeze the translation box out altogether; it never got its width, so step 2 never came
  (case L).
- **Visible only after the redraw.** Turned visible together with the final geometry, the first
  composed frame still held the drawing at the provisional size, cut to the new one - the
  gallery's screenshots caught it. The popup turns visible `POPUP_REVEAL_DELAY_MS` (30) later.
- **`WS_EX_NOACTIVATE` must be set once mapped** - Tk creates the window that carries it then. The
  popup's own has therefore never been in effect: DEFERRED D20, left as it is for the user to
  decide.

"Over the selection" (TODO.md S6) overstated it: the old popups overlapped the cursor's *line*, to
the right of the cursor, not the cursor itself. The new placement keeps the popup wholly above or
below that line.

**References**: TODO.md (§4 findings, §5 design, phases P0-P5); `src/ui/quick_translate.py`;
[WCAG 2.2 Understanding 1.4.8](https://www.w3.org/WAI/WCAG22/Understanding/visual-presentation);
[Tk TIP 438](https://core.tcl-lang.org/tips/doc/trunk/tip/438.md); Decisions 3, 8, 10, 32.

---

### Decision 33 - UniDic is a download in Settings -> Dictionary, not part of the EXE

**Date**: 2026-10-16
**Status**: RESOLVED (the user's choice, DEFERRED D19)

**Problem**: pykakasi, the one reading provider every install has, reads a word differently from
fugashi + UniDic in 30% of real sentences (898 of 3000 Tatoeba sentences, K1), with plain
mistakes among the most frequent (彼 か, 君 くん, 人 にん, 今日 こんにち). UniDic (unidic-lite)
installs to 249 MB; the EXE is 66 MB.

**Options considered** (D19):
1. **Bundle fugashi + unidic-lite in the EXE** - every user reads right. Cons: the EXE grows about
   fourfold for a feature only Japanese readers use.
2. **Offer it where language packs already are** - the Japanese pack in Settings -> Dictionary
   installs fugashi + unidic-lite, and furigana uses it the moment it is there. Cons: a user who
   never opens the tab keeps pykakasi's readings.
3. **Correct pykakasi's worst entries by hand** - every correction is itself a guess about
   context, which "blank beats a wrong reading" forbids.
4. **Leave it.**

**Resolution**: **Option 2**, chosen by the user ("put it in Settings, in the Dictionary language
section; the user downloads it and applies it"). `furigana.refresh_providers()` runs after every
install and uninstall of the pack, so it applies without a restart; the Dictionary tab says which
reader is in use and what the pack costs. In the EXE the pack is pip-installed by the system
Python into `~/.crosstrans/nlp_packages`, so fugashi loads only when that Python is the app's
version; otherwise the tab says the reader could not be loaded, and pykakasi stays.

**References**: `src/core/furigana.py` (`refresh_providers`), `src/ui/settings/dictionary_tab.py`
(`_apply_to_furigana`, `furigana_reader_note`), `tests/test_furigana_reader_choice.py`, CHANGELOG
"Phase K14"

---

### Decision 32 - Tests run on a private desktop and cannot leave the test session

**Date**: 2026-10-16
**Status**: RESOLVED (the user: the tests threw windows over the screen, interrupted other work and
used up the translation quota. The options below were proposed; the goal's stop hook asked for a
fix before the user chose, so the recommended ones were built). Approved by the user on 2026-10-16, with Decisions 28-32.

**Problem**: The Tk tests mapped real windows on the developer's desktop, and the app's windows
take the focus by design. Nothing kept a test off the network, the clipboard or the keyboard, and
the eval tools spent real quota without showing a count first.

**Options considered**:
1. **A private desktop for the Tk thread** (`CreateDesktopW` + `SetThreadDesktop`) - Pros: the
   windows stay real (mapped, measured, focusable - measured 2026-10-16); no test changes; plain
   `pytest` and the mutation runner are covered. Cons: Windows only; must happen before the thread
   owns a window or a hook; desktops share the window station's clipboard, so it is not covered.
2. **Offscreen geometry and no-op `focus_force` / `lift` / `-topmost`** - Cons: changes the
   behaviour under test (the dialog tests assert topmost and focus); a newly mapped window is still
   activated and still gets a taskbar button.
3. **Skip the Tk tests locally** - Cons: about 350 fewer tests where they matter; breaks "the
   test count never goes down".
4. **A private window station**, which would isolate the clipboard too - refused for this user:
   Windows error 5.
5. For the one real-clipboard test: **save and restore around it** - Cons: cannot put every
   format back (files copied in Explorer, some images), and a clipboard history records it anyway;
   **only on CI or when asked for** - Cons: one local skip.

**Resolution**: Option 1, plus refusals for the network (but loopback, and never the lock port),
clipboard writes (Tk's clipboard kept in memory), keystrokes, hotkeys, browser windows and registry
writes - each recorded, so a swallowed refusal still fails its test. The real-clipboard test runs
on CI or with `CROSSTRANS_TESTS_REAL_CLIPBOARD=1`: the proposal said save and restore, dropped once
the lost-format case was seen. The eval tools send nothing until `--confirm-calls N` matches.

**References**: `tests/quiet_session.py`, `tests/conftest.py`, `tests/test_quiet_session.py`,
`tools/eval_dictionary_prompt.py`, `tools/eval_ocr_prompt.py`

---

### Decision 31 - Between providers that list the same model, the key decides

**Date**: 2026-10-16
**Status**: RESOLVED (DEFERRED D12 asked for "a decision about whether Auto-mode ambiguity is worth
changing shared routing for"; the user asked for every proposed item to be done). Approved by the user on 2026-10-16, with Decisions 28-32.

**Problem**: Thirteen model IDs appear under two providers in `model_provider_map`, and
`_identify_provider()` returned the first, so under provider 'Auto' one provider's users always
sent their key to the other's API.

**Options considered**:
1. **Reorder or delete entries** - Cons: any order is wrong for somebody; deleting a model a
   provider really serves hides it from its users (rejected in D12 itself).
2. **The key, positively**: the claimant whose prefix the key carries - Pros: exact where a prefix
   exists. Cons: SambaNova (bare UUID keys), Together and SiliconFlow have none, so gpt-oss-120b
   stays Cerebras's for SambaNova users.
3. **The key, positively and by elimination**: as 2, then drop a claimant whose known prefix the key
   lacks - Pros: also settles every row where only one claimant is prefix-less (SambaNova, and
   Together/SiliconFlow against HuggingFace). Cons: relies on a provider never issuing a key
   without its prefix - the same assumption step 4 of `_identify_provider()` already makes.

**Resolution**: **Option 3** (`AIAPIManager._claimant_for_key()`); only between claimants, only with
a key - no key, or a key no claimant's rule settles, keeps the first, as before. Together vs
SiliconFlow (two prefix-less claimants) is left as it was.

**References**: `src/core/api_manager.py`, `tests/test_provider_claims.py`, CHANGELOG "Phase K8".

---

### Decision 30 - Chinese by its function words: two of 是很們這嗎呢吧麼你她它, in a sentence

**Date**: 2026-10-16
**Status**: RESOLVED (measured, as the proposal asked; decided while doing the post-J12 follow-ups
the user asked for in full). Approved by the user on 2026-10-16, with Decisions 28-32.

**Problem**: Half of all Chinese sentences (46 634 of Tatoeba's 89 179) hold no glyph that only
Chinese writes, so the app treats them like kanji-only Japanese: a marker clause on every
translation, and "Japanese or Chinese?" in the main window's Dictionary for 這是我的書。. Which
text-level rule could settle them without ever calling Japanese text Chinese - which costs more
than the question: evidence is stated to the model, readings vanish, and no row offers to undo it?

**Options considered** (Chinese = share of the 46 634 settled; Japanese = called Chinese among the
100 open Tatoeba sentences, the 177 555 all-kanji dictionary words as terms / one-word sentences /
10 000 lists, and 20 000 stress compounds of two words each holding a listed character):
1. **A long kanji-only sentence** (6+ hanzi ending 。！？) - 81% Chinese; 14 of the 100 Japanese
   sentences. Rejected.
2. **A fullwidth comma ，** - 13% Chinese; 0 sentences, but every academic-style list 東京，大阪
   turns Chinese by construction. Rejected.
3. **Two distinct of 是很們這嗎呢吧麼你她它 + 的了我**, punctuated - 49% Chinese; 1 one-word
   sentence (我們。) and **31%** of the stress compounds (目的完了。, 是正完了。). Rejected: Japanese
   writes 的, 了 and 我 in compounds.
4. **Two distinct of 是很們這嗎呢吧麼你她它**, punctuated - **17.3%** Chinese; **0** on every
   Japanese set, 4 of 20 000 stress compounds (all nonsense: 腹這是川。).
5. **No rule** - Pros: nothing to get wrong. Cons: the question and the marker stay on half of
   all Chinese sentences.

**Resolution**: **Option 4** (`lang_id.grammar_evidence()`, evidence `'zh-grammar'`, after kana and
glyphs and never against a Japanese-only glyph). The modest share is the price of a rule that
measured clean; the sentences it leaves go to the model, which reads a sentence correctly. A text
without punctuation is a term, and terms stay the model's and the user's (Decision 29).

**Re-measured and confirmed by the user, 2026-10-19.** The proposal's two rules, measured again on
the same data: "a long sentence without kana" calls real Japanese sentences Chinese at every
length tried (14 of the 100 at 6+ hanzi, 10 at 8+, 5 at 10+, 3 at 12+ and 15+, 2 at 20+). "A
fullwidth comma, in a sentence ending 。！？" calls no real Japanese sentence Chinese and settles
4 782 more Chinese ones (17.3% -> 27.6% together with option 4), but every list written
`東京，大阪。` by construction. Offered with those numbers, the user declined it: option 4 alone
stays.

**References**: `src/core/lang_id.py`, `tools/measure_cjk_evidence.py`, CHANGELOG "Phase K6",
Decisions 21, 22, 24.

---

### Decision 29 - A placed term can be changed; a placed sentence cannot

**Date**: 2026-10-16
**Status**: RESOLVED (decided while doing the post-J12 follow-ups the user asked for in full).
Approved by the user on 2026-10-16, with Decisions 28-32.

**Problem**: When a model places kanji-only text confidently and wrongly - measured: 汽車 and 工作
alone came back Chinese - the popup offered no way to say otherwise; the J6 row appeared only
for Unknown. Where should a "read as the other language" control appear?

**Options considered**:
1. **On every text whose language a model (or the user) settled** - Pros: always reachable.
   Cons: a row under every Traditional-Chinese sentence whose glyphs prove nothing - the models
   read those correctly, so it is noise on the commonest case.
2. **Only on terms** (no whitespace, no sentence punctuation) - Pros: exactly where the models
   were measured wrong - a word alone has no context; quiet on sentences. Cons: a sentence a
   model misread cannot be flipped from the popup (none was seen in the measurements).
3. **Nowhere; rely on the Dictionary dialog** - Cons: the Dictionary does not ask once a verdict
   exists (Decision 26), so a confident mistake would stick.

**Resolution**: **Option 2** (`source_marker.source_row()` -> `ROW_CHANGE`). The row names what
the text was read as and offers the other language; answering re-translates with it stated
(Decision 27) and keeps it over the model's verdict (Decision 28). The same rule drives the main
window's row (K5).

**References**: `src/core/source_marker.py`, `src/ui/quick_translate.py`, CHANGELOG "Phase K4",
Decisions 22, 27, 28.

---

### Decision 28 - The user's answer is a verdict, and it replaces a model's in History

**Date**: 2026-10-16
**Status**: RESOLVED (decided while doing the post-J12 follow-ups the user asked for in full).
Approved by the user on 2026-10-16, with Decisions 28-32.

**Problem**: The Dictionary's "Kanji-only text: Japanese or Chinese?" answer was used for one
lookup and forgotten. Keeping it raises two questions: where, and what happens to a model's
verdict for the same text already stored in History.

**Options considered**:
1. **Session memory only** - Pros: no stored data changes. Cons: lost on restart; History's rows
   for that text stay unread.
2. **Memory, plus History's entries of that text - only those without a verdict** - Pros: never
   overwrites a model. Cons: when the model said Chinese and the user says Japanese, the
   model's answer keeps coming back from History after a restart.
3. **Memory, plus every History entry of that text, replacing a model's verdict and the label**
   - Pros: Decision 22 puts what the user knows ahead of everything else; one answer per text,
   whichever entry is read. Cons: History no longer records what that model said.

**Resolution**: **Option 3** (`remember_user_source()` -> `set_source_verdict()`). The label is
rewritten with the verdict so the History list says what the readings now assume. A pick of a
pack that is neither Japanese nor Chinese is not a verdict and is not kept. History records
what the app believes about the text, not an audit of the models - the log keeps that
(`[LangID] translation verdict=..`).

**References**: `src/core/translation.py`, `src/core/history.py`, `src/ui/dictionary_popup.py`,
CHANGELOG "Phase K3", Decisions 22 and 26.

---

### Decision 27 - The popup's answer to "Japanese or Chinese?" re-translates; it does not just add readings

**Date**: 2026-10-15
**Status**: RESOLVED (TODO.md J6 left the choice to this phase; decided on J4's measurements)

**Problem**: When a hotkey translation of kanji-only text comes back without a source language
(the model said Unknown, or wrote no marker), the popup offers "Japanese / Chinese". What should
an answer do?

**Options considered**:
1. **Re-translate with the stated source** - Pros: the meaning follows the answer; the readings
   and the translation agree. Cons: one more request (only when the user answers).
2. **Only add the readings** - Pros: free, instant. Cons: J4 measured that a translation the
   model could not place may carry the other language's sense (Groq: 先生 → "Mr.", 床 → "bed/floor";
   Gemini: 結構 → "Structure") - readings for せんせい above "Mr." would look right and be wrong.

**Resolution**: **Option 1.** The answer is stated in the prompt (`stated_clause`) and stored as
the text's verdict (`source_verdict` in memory and History), so the Dictionary and later lookups
of the same text need not ask again. The question is a row inside the popup, not a dialog:
the translation stays readable and nothing is blocked while it stands.

**References**: `QuickTranslateManager._asks_source()` / `_build_source_chooser()`,
`TranslatorApp._on_quick_translate_choose_source()`, `TranslationService.redo_translation()`,
CHANGELOG "Phase J6", Decisions 22 and 25.

---

### Decision 26 - Ambiguous kanji in the Dictionary: reuse a verdict, else ask - no identification call

**Date**: 2026-10-15
**Status**: RESOLVED (the user left this open in TODO.md J5; decided on J4's measurements -
revisit if the user prefers the call)

**Problem**: After J5 the Dictionary knows when kanji-only text proves nothing. Decision 22 says
the model decides, then the user. When the text was translated, a model verdict already exists
(J4). When the user typed into the main window and pressed Dictionary without translating, none
does.

**Options considered**:
1. **One short identification call** ("Japanese, Chinese or Unknown?") - Pros: the model
   decides, as Q1 asked. Cons: a request (and trial quota) and a wait before the window opens;
   measured on a word alone (J4), 2 in 10 answers confidently wrong (汽車, 工作) and 3-4 Unknown -
   so the user would often see the dialog anyway, or a wrong window with no prompt to fix it.
2. **Ask the user directly** - Pros: instant, free, and the user knows what they typed. Cons:
   one click.
3. **Assume Japanese** - declined as Q1 option (c)-like; never.

**Resolution**: **Option 2, after reusing any verdict** for that exact text
(`TranslationService.source_verdict()`, this session or History). The dialog lists Japanese and
the Chinese packs first and pre-selects the first, so Enter answers it - the user still confirms.
A verdict-opened window states the language to the lookup prompt (it is the model's decision).

**References**: `DictionaryPopup._open_ambiguous_kanji()`, `nlp_manager.AMBIGUOUS_CJK_CONFIDENCE`,
CHANGELOG "Phase J5", Decision 22, Decision 25.

---

### Decision 25 - How a translation prompt asks the model for the source language

**Date**: 2026-10-15
**Status**: RESOLVED

**Problem**: Decision 22 lets the AI model decide whether ambiguous kanji-only text is Japanese or
Chinese, and Q7 made the ordinary translation prompts source-aware. The model's decision has to
come back out of a call whose answer is shown to the user, pasted by Replace and cached in History.

**Options considered**:
1. **A marker line in the answer** (`[[SOURCE: Japanese]]`), read and removed by the app - Pros:
   no extra call; measured compliance 10/10 on both providers. Cons: depends on the model; a stray
   marker must never reach the user.
2. **A separate identification call** - Pros: clean output. Cons: one more call (and trial quota)
   on every ambiguous selection.
3. **Structured output (JSON)** - Cons: the providers differ in support, and a JSON envelope
   around a translation is fragile in exactly the uncensored, verbatim cases the prompts protect.

**Resolution**: **Option 1**, only for mostly-CJK text that the characters cannot place; text they
can place has its language *stated* instead, and every other text is sent unchanged. Details that
were weighed:
- **The request goes last** in the prompt, after the rules it is an exception to ("output only the
  result").
- **No favourite**: the wording never says which language is likelier, and its example (娘,
  "daughter" / "mother") is not one of the measured words (Decision 21's lesson).
- **Unknown is allowed** and means no verdict. Measured: 3-4 in ten - that is where the user is
  asked (J6). Confidently wrong answers (汽車 "car", 工作 "work") are not caught by this; only
  context or the user can.
- **The cache is not namespaced by verdict.** An entry made before J4 has no verdict and serves
  as before; Re-translate gets a fresh one. Namespacing would re-ask every cached kanji-only text
  once, for a marker most of them do not need.
- **The verdict has its own field** (`source_verdict`), never `source_lang`: History has always
  filled `source_lang` from the characters, which says "Chinese" for every kanji-only text.
- **Mixed text is left alone** below 50% kanji + kana among its letters ("I love 你" is English),
  and Hangul excludes Korean.

**References**: `src/core/source_marker.py`, `TranslationService._call_with_source()` /
`source_verdict()`, `HistoryManager.find_source_verdict()`, CHANGELOG "Phase J4",
`logs/eval/translate_before.jsonl` / `translate_after.jsonl`, TODO.md J4.

---

### Decision 24 - Glyph evidence: "Japanese-only" excludes Big5-HKSCS, not just Big5

**Date**: 2026-10-15
**Status**: RESOLVED

**Problem**: `src/core/lang_id.py` reads evidence from single characters: a kanji only Japanese
writes proves Japanese, one Japanese cannot write proves Chinese. "Only Japanese writes" means
"in a Japanese character set and in no Chinese one". TODO.md F9 measured the rule with CP932
minus GB2312 minus Big5 (959 code points) and found no Chinese word called Japanese - but its
Traditional samples were Taiwan-style. Hong Kong writes 衆 裏 綫 衞 啓 峯 where Taiwan writes
眾 裡 線 衛 啟 峰, and those Hong Kong forms are outside Big5 and inside CP932.

**Options considered** (measured on `tests/test_lang_id.py`'s fixtures):
1. **Big5** - Pros: 959 Japanese-only glyphs; 77 of 311 Japanese words settled by glyph.
   Cons: **12 of 13 Hong Kong strings called Japanese** (這裏, 公衆, 路綫, 衞生 ...): Japanese
   readings on Chinese text, the outcome Decision 8 ranks worst.
2. **Big5-HKSCS** (a superset of Big5) - Pros: no Hong Kong string called Japanese. Cons: HKSCS
   also carries Japanese forms (駅 発 円 県 込 鉄), so 959 -> 571 Japanese-only glyphs and 55 of
   311 Japanese words settled by glyph; the 22 that lose it become ambiguous (never Chinese).
3. **Big5 plus a hand-kept list of Hong Kong forms** - Pros: keeps more coverage. Cons: a
   curated list nobody can verify is complete; it fails silently on the form it misses.
4. **GBK / GB18030 as the Chinese set** - Cons: they hold almost every ideograph, so nothing
   would be Japanese-only (already rejected in F9).

**Resolution**: **Option 2.** "Blank beats a wrong reading" decides it: a word that loses its
glyph evidence is still settled by kana, its context, a model's verdict or the user, while a
Hong Kong text called Japanese would be annotated wrongly with nothing to stop it. Do not swap
back to Big5 to "recover coverage". JIS X 0213 (not CP932) stays the "can be Japanese" set, for
the 2010 Jōyō kanji 剝 頰 塡.

**References**: `src/core/lang_id.py` (module docstring, `glyph_class()`), TODO.md F9 and J2,
`tests/test_lang_id.py` (`test_hong_kong_forms_are_never_japanese`, `test_coverage_is_recorded`).

---

### Decision 23 - One Dictionary mode: the popup delegates to `DictionaryPopup`

**Date**: 2026-10-15
**Status**: RESOLVED

**Problem**: Dictionary mode - NLP check, language detection, the "Select Source Language"
dialog, the word window and the lookup - existed twice: `src/ui/dictionary_popup.py` for the main
window's button and ~400 lines inside `src/ui/quick_translate.py` for the popup's, plus a third
copy of the lookup in `app.py`. The copies had drifted (D15: one used `grab_set()`, the other the
safe pattern; window sizes and dialog placement differed) and shared one bug (D14). Phases J3, J5
and J6 of the language-identity work would each have been written twice more. The user first
chose to change both in lockstep (TODO.md Q8), then asked for the consolidation itself.

**Options considered**:
1. **Keep both, change them in lockstep** - Pros: no refactor. Cons: every change twice, and the
   copies drift anyway; this was the state that produced D14/D15.
2. **A new shared module** that both classes call - Pros: neutral ownership. Cons: a third place,
   and both classes keep thin wrappers that still have to agree.
3. **`DictionaryPopup` owns the flow; the popup only asks for it** - Pros: `DictionaryPopup` was
   already the extracted owner of Dictionary mode (it shows its results through
   `QuickTranslateManager` too); the popup's part shrinks to "this text, into this language,
   beside me". Cons: the main window's and the popup's small differences (where the window opens,
   whose target language) become parameters.

**Resolution**: **Option 3.** `open_from_text(text, *, target_language=None, anchor=None)`;
`QuickTranslateManager` gets one callback, `on_open_dictionary(text, target_lang, popup)`, which
`TranslatorApp._on_quick_translate_open_dictionary()` forwards. Placement is the pure
`word_window_geometry()` / `dialog_geometry()`, so the one real difference between the buttons -
"beside the popup" vs "centred" - is tested without a window manager. Deliberately unified rather
than parameterised: window size (700x350, the main window's), dialog position (next to the
pointer, the popup's), the not-installed dialog (the main window's text), the dialogs' modality
(the popup's safe pattern). `tests/test_dictionary_flow.py` asserts the popup keeps no copy.

**References**: CHANGELOG "Phase D13-D15", TODO.md Q8, CLAUDE.md "Dictionary Mode",
`tests/test_dictionary_flow.py`.

---

### Decision 22 - Ambiguous kanji-only text: evidence first, then the model, then the user

**Date**: 2026-10-15
**Status**: RESOLVED (principle - the user's choice). The mechanism (TODO.md §3.1) is proposed and
awaits approval phase by phase (J4-J6).

**Problem**: "Furigana everywhere Japanese appears" runs into text written only in kanji. Without
kana it cannot always be told from Chinese: of 54 kanji-only Japanese words sampled, 32 carry a
Japanese-only glyph (経, 気, 駅 ...) and **22 carry nothing** (勉強, 手紙, 東京大学, 先生). Today such
text gets no readings wherever the caller does not already know the language, and
`nlp_manager.detect_language()` calls every one of them "Chinese (Simplified)".

**Options considered**:
1. **A Settings choice** - "Text written only in kanji is: Auto / Japanese / Chinese / Unknown",
   Auto inferred from the Windows UI language, locales and keyboard layouts (this PC: system
   locale 0x0411 and a Japanese keyboard → Japanese). Pros: offline, deterministic, free. Cons:
   under a Japanese default an ambiguous Chinese *word* gets Japanese readings; one more setting.
   **Recommended in TODO.md, declined by the user.**
2. **Keep today's rule** (no readings without proof). Cons: does not meet the request.
3. **Always Japanese.** Cons: wrong readings on Chinese, for every user.
4. **The AI model decides; when it cannot, the user decides in a window.** Pros: uses judgement
   the app already pays for - a translation or lookup of that text is being made anyway. Cons:
   depends on prompt compliance, which differs by provider and must be measured; a verdict
   exists only after a call.

**Resolution**: **Option 4, chosen by the user** (2026-10-15). The order is: what the caller
knows (a translation's target; the user's pick) → evidence in the text (kana, Japanese-only or
Chinese-only glyphs) → evidence in its context → the language a model call *reported* for that
exact text → otherwise the user, through a window - but only where the app cannot continue
without a language (Dictionary mode; a popup whose translation reported "Unknown"). Passive
surfaces (Reading pane, History rows, word chips) never open a window; they stay plain.
**Evidence overrides the model**: kana in the text beats a model that said "Chinese".

The verdict is collected from calls already being made - dictionary field 2 (Decision 21), a
marker line in the translation prompts for ambiguous text only (Q7, also the user's choice), a
section in the OCR prompt - so ambiguity costs no extra call in the common case.

"Blank beats a wrong reading" (Decision 8) still holds: a model verdict is consulted only for
text the evidence cannot settle, and "Unknown" never produces a reading.

**Do not re-propose** a Settings default or Windows-locale inference for this, and do not tell a
model which language to prefer: a frequency tie-break already measured as a Chinese bias
(Decision 21), and a Japanese tie-break would be option 1 in disguise.

**References**: TODO.md §3 (Q1, Q7) and §3.1, Decision 8, Decision 21, findings F4/F9 in TODO.md.

---

### Decision 21 - The dictionary prompt states the source language only when it is evidence, and sends the sentence

**Date**: 2026-10-15
**Status**: RESOLVED

**Problem**: The dictionary prompt carried the target language and the bare headwords, and asked
the model to "detect" the source language in field 2. A kanji-only headword is ambiguous alone -
手紙 is "letter" in Japanese, "toilet paper" in Chinese - and both Dictionary windows already
knew a language (their titles said "Dictionary (Japanese → Vietnamese)") but dropped it, along
with the sentence the word came from. Measured with the old prompt on ten false friends:
gemini-2.5-flash, gpt-oss-120b and the trial's llama-3.3-70b each gave the Chinese sense for
汽車, 工作 and 床 (7/10 Japanese each). A model that decides "Chinese" writes a Chinese entry, and
the result window, which takes its reading hint from field 2, then shows it without furigana.

**Options considered**:
1. **State the window's language, always.** Simplest. Cons: the window's language is often a
   guess - `detect_language()` answers "Chinese (Simplified)" for *any* kanji-only text and the
   first installed European pack for any Latin text - and a guess stated as fact makes the model
   follow it: 勉強 selected alone would be looked up as Chinese on purpose.
2. **State it only when it is evidence** - the user picked it in the dialog, or detection proved
   Japanese (it needs kana to say so) - otherwise say "not given" and let the model decide and
   name its decision in field 2. Send the sentences that contain the headword either way.
3. **Fix detection first, then the prompt.** Cons: nothing improves until the language-identity
   core exists, and the lookup would still lose the sentence.

**Resolution**: Option 2. `src/core/dictionary_prompt.py` builds the prompt as pure logic;
`dictionary_source_language(language, user_chosen)` is the trust rule; `extract_context()` sends
the sentences containing a headword (cap 600 characters - an educated guess); the pronunciation
follows the source (Japanese: hiragana only, the user's choice; Chinese: pinyin; Korean: Revised
Romanization; else /IPA/ + a target phonetic); source = target gives a monolingual entry. With a
Japanese sentence sent and the source stated, all three providers gave the Japanese sense **10/10**.

**A tie-break that looked neutral and was not.** The first wording of "not given" told the model,
without context, to choose "the language in which it is more commonly written exactly as given".
gpt-oss-120b then answered 先生 alone as Chinese "Mr." (the old prompt: "teacher"); without the
sentence, "teacher" again. One run each - weak evidence - but the bias is structural: Chinese text
is more abundant, so "more common" means Chinese for every shared spelling. Removed, with a test.
**Do not reintroduce a frequency tie-break**, and per Decision 22 not a Japanese lean either.

**Known limit**: a headword alone, with no source and no context, is no better than before
(gpt-oss-120b 6/10 against 7/10, within noise) - there is nothing new to decide from. Decision
22's later phases remove the case: the Dictionary opens in the language the translation's model
verdict or the user settled, and that language is then stated.

**Also seen**: the trial model translated 床 as "floor" and gave its reading as とこ (the bed/alcove
reading; "floor" is ゆか). Field 5 is printed as text, not as furigana, so it is a wrong
pronunciation line rather than a wrong reading over the word; no prompt fixes a weak model.

**References**: `src/core/dictionary_prompt.py`, `TranslationService.dictionary_lookup()`,
`src/ui/dictionary_popup.py`, `src/ui/quick_translate.py`, `src/app.py`,
`tests/test_dictionary_prompt.py`, `tools/eval_dictionary_prompt.py` and its local output
`logs/eval/dictionary_{before,after}.jsonl`, TODO.md J0/J1, Decision 22.

---

### Decision 20 - OpenRouter's defaults stay free, and a default must route to its own provider

**Date**: 2026-09-08
**Status**: RESOLVED

**Problem**: OpenRouter's two defaults - `google/gemini-2.0-flash-exp:free` and
`meta-llama/llama-3.3-70b-instruct:free` - were both gone. Unlike Google and Groq this needed no
key to establish: they are absent from OpenRouter's public 428-model catalogue **and** their
per-model `/endpoints` resource returns zero routable endpoints. The two signals agreed on all
twenty IDs checked, so either is a sound test for death.

Replacing them was not obvious, because the free tier OpenRouter had in 2024 no longer exists.
Every recognisable brand-name free model is gone; the sixteen that remain are niche
(nemotron, inkling, poolside, finance- and health-tuned ling, gemma-4), and **each has exactly
one endpoint** - which is precisely how the two dead defaults died.

**Options considered**:

1. **Free only.** Preserves the original intent - an OpenRouter key with no credit still
   translates. Cost: single-endpoint models, unmeasured translation quality, and a near-certain
   repeat of this same failure.
2. **Cheap paid only.** `meta-llama/llama-3.3-70b-instruct` has thirteen endpoints and 100%
   one-day uptime at $0.10/$0.32 per million tokens - roughly 12,000 translations per US$1. Robust,
   but it spends a user's money on a model they never chose.
3. **Free first, paid fallback.** `default_models_by_provider` is a rotation list tried in order,
   so a free entry followed by a paid one keeps the zero-cost intent and still lands somewhere
   alive.

**Resolution**: **Option 1, chosen by the developer** after the single-endpoint risk was put in
front of them explicitly. `['google/gemma-4-31b-it:free', 'nvidia/nemotron-3.5-lightning:free']` -
the two most general-purpose of the free set, deliberately on **different upstreams** (Google AI
Studio and Nvidia) so that they fail independently rather than together. Option 3 was recommended
and declined; do not re-propose a paid default without asking.

**Unverified, and knowingly so**: no OpenRouter key was available, so both were confirmed
*routable* but neither was confirmed to translate well. The risk to test when a key appears is
**latency**, not truncation: `_call_generic_openai_style` sends no `max_tokens`, but it does use
`timeout=10`, and both of these lean reasoning/agentic. On Groq the same shape of model took
1.3 s against gpt-oss's 0.7 s; a slower one fails the timeout with a perfectly good answer.

**The second half of this decision came out of the fix.** Choosing a default is not enough - it
must also *identify* as its own provider. `_identify_provider()` tries an exact match in
`model_provider_map`, then a list of prefix rules in which `google/` means **Together**. The new
default `google/gemma-4-31b-it:free` was not in the map, so at tier 3 it identified as Together
and, under `provider='Auto'`, would have sent an `sk-or-v1-` key to Together's endpoint. **Both
dead defaults did the same thing** - they were mis-routed as well as retired. The fix is to list
every default in `MODEL_PROVIDER_MAP` for its provider so the exact match wins;
`tests/test_default_model_routing.py` now asserts the round-trip for all thirteen providers, and
the guard was probed by removing the entries and watching it fail.

**A shortcut that does not work, so nobody tries it again**: OpenRouter's `/endpoints` resource
names the upstream providers serving a model, which looks like a free way to verify the other
providers' native model IDs. It is not. It lists **Groq** as serving
`meta-llama/llama-3.3-70b-instruct`, while Groq's own catalogue - fetched with a real Groq key the
same morning - contains no llama-3.3 at all. It describes OpenRouter's routing arrangements, not
what a user's own key can call. Decision 19's lesson in a third form.

**References**: `src/constants.py`, `src/core/api_manager.py` (`DEFAULT_MODELS_BY_PROVIDER`,
`_identify_provider`), `cloudflare_worker.js` (`STATIC_DEFAULT_MODELS_BY_PROVIDER`),
`docs/models_config_template.json`, `tests/test_default_model_routing.py`, Decisions 15 and 19,
DEFERRED D11.

---

### Decision 19 - Ask the provider. Filtering against the catalogue is theatre.

**Date**: 2026-09-08
**Status**: RESOLVED

**Problem**: D11 said the hardcoded `default_models_by_provider` entries for providers other than
Groq were unverified. Google was checked first, being the app's primary provider, and **all three
of its defaults answered 404**: `gemini-2.0-flash`, `gemini-1.5-flash` and `gemini-1.5-pro` are
retired. Six of the eight entries in `MODEL_PROVIDER_MAP['Google']` were dead as well. This is
not a fallback path - it is what auto-detection and `_try_model_rotation()` read on every run
where the model field is blank, so a user with a Gemini key and no model chosen got three silent
failures and nothing else.

D11 itself proposed the durable fix: derive the table instead of writing it by hand.

**Options considered**:

1. **Filter the curated defaults against `model_provider_map`** and drop whatever is not in it -
   the same shape as `getProviderModels()`. Cheap, no keys needed, covers all thirteen providers
   at once.
2. **Query each provider's own `/models`**, the way `fetchGroqModels()` already does, and let
   that be the catalogue.
3. **Verify by hand and re-hardcode.** Correct today, stale again by definition.

**Resolution**: **Option 1 was simulated across all thirteen providers and rejected.** For
Google it would have *kept* `gemini-2.0-flash`, because OpenRouter - where the map comes from -
still lists a model that 404s. For the nine OpenRouter-derived providers the catalogue is exactly
as stale as the thing it would be checking, so the filter would have removed nothing real while
looking like a safeguard. That is the failure Decision 18 was written against, one layer down:
protection that is believed rather than true. It was not shipped.

**Option 2 for Google**, as `fetchGeminiModels()` + Step 5.6, mirroring Groq: query
`generativelanguage.googleapis.com/v1beta/models`, keep what supports `generateContent`, and
subtract `GEMINI_NON_CHAT_PATTERNS`. `supportedGenerationMethods` alone is not the filter - the
same endpoint serves tts, image, transcribe, robotics, computer-use, lyria (music), nano-banana
(image) and the agentic deep-research / antigravity families, all of which report it. Measured
against the live list: 22 of 40 excluded, and the 18 that remain are all general chat models.
Fails closed to the static list on a missing key, an HTTP error, an empty response or an
exception - all four verified by running the shipped function under Node against the real payload.

**Option 3 for the defaults themselves**, because there is no deriving them: which model to pick
unattended is a judgement, not a fact. `['gemini-2.5-flash', 'gemini-2.5-flash-lite',
'gemini-flash-latest']` keeps the old intent - a mid-tier flash model first - adds a faster one
to rotate to when the first is busy (`gemini-2.5-flash` really did answer 503 during the check),
and ends on an **alias**, which is the closest thing to a default that cannot rot.

**The lesson worth keeping: presence in a listing is not usability.** `gemini-2.5-pro` appears in
Google's own `/models` output and answers `404 no longer available to new users` when called.
Every model named in this change was verified with a real translation request, and the reply
codes were read rather than counted - `404` is dead, `503` is busy and `429` is out of quota, and
two of the models that looked dead on a first pass were neither.

**References**: `cloudflare_worker.js` (`fetchGeminiModels`, `GEMINI_NON_CHAT_PATTERNS`,
Step 5.6, `STATIC_DEFAULT_MODELS_BY_PROVIDER`, `STATIC_PROVIDER_MODELS`), `src/constants.py`,
`src/core/api_manager.py`, `docs/models_config_template.json`, Decision 15, DEFERRED D11.

---

### Decision 18 - CI checks its own green tick

**Date**: 2026-09-08
**Status**: RESOLVED

**Problem**: The suite only ever ran on one machine, by hand (D10). Adding a workflow is trivial;
making it *mean* something is not. `tests/conftest.py`'s `tk_root` fixture calls `pytest.skip`
when Tk cannot open a display - correct for a developer on a headless shell - and **312 of the
630 tests need it**. A GitHub runner without a usable desktop session would skip roughly half the
suite, pytest would exit 0, and the badge would be green.

That is worse than no CI. No CI is a known gap; a green tick over an untested half is a false
one, and it is exactly the failure the project's own Rule 4 warns about ("any decrease in test
count = regression") - except silent, because nothing was counting.

**Options considered**:

1. **Just add the workflow.** Pros: five minutes. Cons: the failure above, undetected.
2. **Make `tk_root` fail instead of skip under CI** (e.g. when `$CI` is set). Pros: no extra
   tooling. Cons: turns one broken runner into 312 identical red tests with no summary, and
   couples a fixture to an environment variable that has nothing to do with what it does.
3. **Count the results and judge them.** Have pytest write JUnit XML and check it: fail when more
   tests were skipped than a healthy run explains, or when barely anything was collected.

**Resolution**: **Option 3**, as `tools/check_test_counts.py`, run with `if: always()` so the
counts are reported even when pytest itself failed. The ceiling (`DEFAULT_MAX_SKIPPED = 10`)
leaves room for the genuinely environment-dependent skips - the clipboard round trip yields when
another process owns the clipboard (D9) - and sits far below the 312 a missing display produces.
`--min-total 500` catches the other empty outcome, a collection error that finds almost nothing.

The guard is a script with its own tests rather than an inline shell one-liner, because a check
that silently stops working is precisely the thing being guarded against. The headless scenario
is pinned by feeding it a synthetic report with 312 skips.

`windows-latest` only: the app registers global hotkeys, reads the registry and the clipboard
through pywin32, and draws Tk widgets. There is nothing meaningful to run on Linux, so a matrix
would buy nothing but minutes.

**Not verified**: whether the runner actually has a usable Tk display. That cannot be known
without a push. Both outcomes are handled - a diagnostic step reports Tk's availability, and the
guard turns the bad one into a clear failure rather than a quiet pass.

**References**: `.github/workflows/tests.yml`, `tools/check_test_counts.py`,
`tests/test_ci_guard.py`, `tests/conftest.py` (`tk_root`), global Rule 4.

---

### Decision 17 - The log file is JSON, the console is not, and the tag is derived

**Date**: 2026-09-08
**Status**: RESOLVED

**Problem**: Global Rule 10 wants `{"ts","level","tag","msg"}` JSON Lines. The app has ~458
logging calls, essentially all of them `logging.info("...")` on the root logger with no tag
anywhere, and D5 was deferred precisely because "changing the format touches every call site".

**Options considered**:

1. **Add a tag argument at all ~458 call sites.** Pros: explicit. Cons: a 458-site mechanical
   edit for a formatting change, every one of them a chance to typo, and every future call site a
   chance to forget. Rejected as soon as it was priced.
2. **Derive the tag from the LogRecord.** Pros: zero call-site changes; new code gets a tag for
   free. Cons: `record.module` is a file name, not a concept - `api_manager` where the message
   really means "model rotation".
3. **Derive it, but honour the convention already in the codebase.** 55 of the 458 messages open
   with a bracketed tag - `[ModelRotation]`, `[Trial]`, `[TOKENIZE]`, `[Auto-Model]`. Those are
   *better* tags than any module name.

**Resolution**: **Option 3.** `JsonLinesFormatter` lifts a leading `[Bracket]` into `tag` and
removes it from `msg` (so it is not said twice); everything else gets `record.module`. `mod` is
added only when it differs from the tag, so nothing is duplicated. An informal convention became
structured data and not one call site moved - and `logging.info("[Thing] ...")` keeps working as
the way to set a tag.

**The console keeps the old human format.** `python main.py` prints to a terminal somebody is
watching; JSON there serves nobody. Rule 10 is about a log a *tool* reads, which is the file.

**Local time with a real UTC offset**, not UTC and not a bare local stamp. A log is read beside a
user saying "it broke at three" and by a tool that must not have to guess which three;
`2026-09-08T11:56:18.651+09:00` satisfies both. `ensure_ascii=False` for the same reason - a
Japanese translation in a log should read as Japanese, not as escapes.

**Rotation caps size as well as age.** Retention (Decision 13) bounds a quiet app but not one
runaway loop inside a single day, so the handler is a `RotatingFileHandler`
(`LOG_MAX_BYTES` x `1 + LOG_BACKUP_COUNT` per day). That created a second, quieter leak:
`prune_old_logs` globbed `translator_*.log` and matched `^translator_\d{8}\.log$`, so the rotated
`translator_20260908.log.1` siblings were neither globbed nor matched and would have survived
forever - converting unbounded growth *within* a day into unbounded growth *across* days. Both
patterns were widened, and a test pins that `.bak`, `.logged` and `translator_2026.log.1` are
still spared.

**Buffering was rejected, though Rule 10 suggests it.** Every ending this app actually has skips
cleanup: the updater exits with `os._exit(0)` (CLAUDE.md), the crash hook writes as the process
dies, and the already-running watchdog force-exits (Decision 12). A buffer would drop precisely
the lines anyone would want. `delay=True` is used instead, which costs nothing and stops a run
that never logs from leaving an empty file.

**Migration**: existing daily files are plain text and new ones are JSONL, with one day's file
possibly holding both. A reader that skips non-JSON lines handles it, and retention removes the
overlap within 14 days. Not worth a converter.

**References**: `src/utils/logging_setup.py`, `tests/test_logging_setup.py`, Decisions 12 and 13,
global Rule 10.

---

### Decision 16 — A second instance must be acknowledged, not merely connected

**Date**: 2026-09-08
**Status**: RESOLVED

**Problem**: The lock socket has always been `listen()`ing with nobody accepting, so launching
CrossTrans twice produced a dialog pointing at the system tray (D4). Making the running instance
raise its window instead is easy; knowing whether it *will* is not. Every build ever shipped
accepts the connection into the backlog, because `listen(1)` predates the accept loop by years.

**Options considered**:

1. **Connect and assume** - if the socket accepts, the running instance got the message.
   Pros: no protocol, no waiting. Cons: **wrong against every existing build**. The connection
   lands in the backlog and is never read, so a user who upgrades and then double-clicks the icon
   gets a second process that exits silently having done nothing - no window, and not even the
   old dialog. Confirmed empirically on 2026-09-08 against the running 1.9.20: `netstat` showed
   the suite's connection sitting in `CLOSE_WAIT`, accepted by nobody.
2. **Wait for an acknowledgement**, and fall back to the notice when it does not come.
   Pros: tells a version that will act from one that will not, which is the only thing that
   matters here. Cons: the second instance waits up to `SIGNAL_TIMEOUT_S` before showing the
   dialog in the fallback case.
3. **Version-stamp the lock** (write the running version somewhere the second instance can read).
   Pros: no waiting. Cons: a second source of truth that can go stale, and it still says nothing
   about whether that build's accept loop is actually alive.

**Resolution**: **Option 2.** `signal_running_instance()` returns True only on `SHOW_ACK`; `main`
falls back to `_warn_already_running()` otherwise, so the Decision 12 dialog and its watchdog
stay exactly as they are. 1.5 s is the whole cost, and only on the path that was already showing
a modal dialog.

Three details are load-bearing and each is pinned by a test that was verified to fail without it:

- **A token, not a bare connection.** The port is on loopback, reachable by any local process; a
  stray connect must not throw a window onto the user's screen.
- **The ACK is sent before the window is raised**, so the second instance exits on its own
  schedule rather than waiting on this one's UI.
- **The accept loop outlives its handler.** A bad connection, or an exception out of the UI
  callback, must not leave every later double-click unanswered. The thread is a daemon and ends
  when the socket closes - it can never be the reason a process outlives its window, which is
  the failure Decision 12 was about.

**What "show yourself" means was already decided.** D4 listed it as an open question, but
`app.show_main_window()` has answered it since the tray menu was written: it marshals itself onto
the UI thread and, when a popup is already open, raises that instead of building a second one.
The accept loop reuses it rather than inventing a second path - `on_second_instance` only adds
the toast, handed over in the same `after(0, ...)`.

**A toast, not silence** (the user's call): the window appearing is the real answer, but a
two-second "CrossTrans is already running" removes any doubt about whether a second copy started.

**Testability shaped the API.** `signal_running_instance` takes `port` because LOCK_PORT belongs
to whatever CrossTrans is running on the developer's machine. Reaching for it made nine tests
skip on this machine and would, once the running build understands the request, have raised the
user's window mid-suite - the same class of environment dependence D9 was about.

**References**: `src/utils/single_instance.py`, `main.py`, `src/app.py`
(`on_second_instance`, `_raise_for_second_instance`, `SECOND_INSTANCE_TOAST*`),
`tests/test_second_instance_signal.py`, `tests/test_single_instance_notice.py`, Decision 12.

---

### Decision 15 — The Groq lists are curated, not mirrored; the trial pool excludes by measured behaviour

**Date**: 2026-09-07
**Status**: RESOLVED

**Problem**: Groq decommissioned its entire Llama chat line. 15 of the 17 IDs hardcoded in
`constants.py` were gone, and so were the models named in four other tables. Two questions had to
be answered before replacing them: what should the hardcoded lists contain, and what should the
trial proxy be allowed to reach for.

**Options considered**:

1. **Mirror the live catalog** - copy whatever Groq's `/models` returns.
   Pros: never stale again, one obvious source. Cons: the catalog is 14 entries of which 7 are
   speech, TTS or safety classifiers, and the remainder includes agentic and Arabic-specialist
   models. `constants.py` is the **tier-3 fallback**, reached only when the remote config is
   unreachable *and* there is no cache - a first run with no internet. Handing that user a
   dropdown of `whisper-large-v3` and `canopylabs/orpheus-arabic-saudi` to translate with is
   exactly the failure the old list already caused.
2. **Curate: general-purpose chat models only** - the four IDs that can actually translate.
   Pros: every entry works; a short list is honest about being a safety net rather than pretending
   to be a catalog. Cons: needs revisiting when Groq's lineup moves again.
3. **Delete the hardcoded Groq list** and rely on remote + cache.
   Pros: nothing to go stale. Cons: removes Groq from the dropdown entirely in the one situation
   tier-3 exists for.

**Resolution**: **Option 2**, with the split made explicit. Two lists exist and they answer
different questions, so they get different contents:

- `MODEL_PROVIDER_MAP['Groq']` = *what exists on this provider* -> all four general chat models
  (`openai/gpt-oss-120b/20b`, `qwen/qwen3.6-27b`, `qwen/qwen3.8-27b`). It also drives
  `_identify_provider()` step 1, and without the entries `openai/gpt-oss-120b` falls through to
  **OpenAI** on `'gpt' in name` and `qwen/qwen3.6-27b` to **SiliconFlow** on `'qwen' in name`
  whenever no API key is supplied. Listing them is what makes routing correct, not just tidy.
- `DEFAULT_MODELS_BY_PROVIDER['Groq']` = *what to pick unattended* -> only `gpt-oss-120b/20b`.
  Measured 2026-09-07: gpt-oss answers in ~0.8 s using 46-84 completion tokens with no reasoning
  preamble; qwen3.6 spent 239 tokens on the same three-word input, nearly all of it inside
  `<think>`. **Correction (2026-09-08)**: the original entry explained this as qwen3 exhausting
  `max_tokens: 1024`. That mechanism is wrong - `_call_generic_openai_style` sends **no**
  `max_tokens` at all, and the 1024 cap belongs to `_call_anthropic` alone. The measurements and
  the conclusion stand on their own: re-measured with a real call, qwen3.6-27b needs 509
  completion tokens and 1.3 s where gpt-oss-120b needs 134 and 0.7 s, it puts `<think>` inline in
  `content` (so it leans on `strip_thinking_tags()`) where gpt-oss returns a separate `reasoning`
  field, and qwen3.8-27b answered `429 Request too large ... on output` on one of two attempts.
  The real hard limit on this path is `timeout=10`, which a slow reasoning model can exceed.
  A model a user picks deliberately is their call; a model the app substitutes silently must be
  boring and fast.

For the trial pool the rule is **measured behaviour, not model category**. D6 asked for
qwen3 / gpt-oss / deepseek-r1 / compound to be excluded. gpt-oss is nominally a reasoning model
and was excluded from that exclusion, because measurement disagreed with the category: it emits
no `<think>` and answers in under a second, and dropping it would leave Groq's pool empty, which
is a worse outcome than the one being prevented. The deny list is therefore
`*compound*` (agentic - outlives the 15 s timeout), `*qwen3*`, `*deepseek-r1*`, `*-r1`
(budget-exhausting reasoning) and `*allam*` (4k-context Arabic specialist). It **fails open**:
if the filter would empty a provider's pool the unfiltered list is used, because a slow model
beats falling through to the next provider with nothing.

`reasoning_format: 'hidden'` is sent **only to Groq**, via a per-provider `extraBody` spread into
the request. `callOpenAIAPI` is shared with Cerebras and SambaNova, and the field is not
OpenAI-standard; sending it to all three to save a line would risk a 400 on providers that were
working. Measured accepted by Groq on a non-reasoning model (`openai/gpt-oss-120b` -> 200 OK,
output unchanged), so it is safe to send unconditionally *within* Groq.

**Rejected**: mirroring the catalog (option 1) - `GROQ_NON_CHAT_PATTERNS` already strips speech
and classifier models on the Worker's live path, and duplicating that judgement as raw data in
`constants.py` is how the old list rotted in the first place.

**References**: `src/constants.py` (`MODEL_PROVIDER_MAP`, `VISION_MODELS`),
`src/core/api_manager.py` (`DEFAULT_MODELS_BY_PROVIDER`, `_identify_provider`),
`cloudflare_worker.js` (`TRIAL_MODEL_DENY_PATTERNS`, `getProviderModels`, `PROVIDERS.groq.extraBody`,
`STATIC_VISION_PATTERNS`), `docs/models_config_template.json`, DEFERRED D6/D7 (both closed).

---

### Decision 14 — Reasoning tags are stripped at the dispatch point, not at the callers

**Date**: 2026-09-07
**Status**: RESOLVED

**Problem**: `<think>...</think>` was removed on the five text paths (all inside
`TranslationService`) and on none of the vision ones. Image translation, screenshot OCR and
scanned-PDF OCR call `AIAPIManager` directly and never see the service.

**Options considered**:
1. **Strip at the three vision callers** — Pros: no shared layer, each caller decides. Cons:
   three edits for one rule, a fourth caller would silently miss it, and `translate_image` /
   `translate_multimodal` each have two return paths (normal and model rotation) — so really six
   places, which is how this was missed the first time.
2. **Strip inside `_generate_content` / `_generate_content_multimodal`** — Pros: one site per
   modality; every caller, every rotation substitute and every future caller is covered by
   construction. It is exactly where `_record_attribution` already lives, for the same reason.
   Cons: text results are then stripped twice (once here, once in the service). The function is
   idempotent, so the second pass is a no-op.
3. **Move the whole cleanup into the service and route vision through it** — Pros: one owner.
   Cons: `pdf_ocr.py` has an API manager and no service; giving it one to clean a string is a
   large change for a small rule.

**Resolution**: option 2. `src/core/text_cleanup.strip_thinking_tags()` is the single
implementation; the two dispatch methods call it, and `TranslationService._strip_thinking_tags()`
delegates to it — kept, because the trial proxy does not go through the API manager at all.

**References**: `src/core/text_cleanup.py`, `src/core/api_manager.py`
(`_generate_content`, `_generate_content_multimodal`, `_dispatch_call`),
`tests/test_vision_cleanup.py`. Same one-site argument as [Decision 11].

---

### Decision 13 — The frozen app logs to %APPDATA%, and prunes after 14 days

**Date**: 2026-09-07
**Status**: RESOLVED

**Problem**: `setup_logging()` derived its directory from `__file__`. Under a PyInstaller onefile
build that is inside `_MEIxxxxx`, the temp directory deleted on exit — so the shipped app's log,
the only artefact a bug report can be diagnosed from, was discarded every run.

**Options considered**:
1. **Next to the EXE** (`dirname(sys.executable)/logs`) — Pros: obvious, portable-friendly.
   Cons: the EXE may sit in `Program Files`, where a normal user cannot write; the auto-updater
   also renames and moves it.
2. **`%APPDATA%/CrossTrans/logs`** — Pros: always writable, survives an update, sits beside
   `config.json` and `models_config.json`, so support asks for one folder. Cons: nothing ever
   cleans it up.
3. **`%TEMP%/CrossTrans`** — Pros: self-cleaning-ish. Cons: the same disappearing act, just
   slower, and users are told to look in a folder Windows may empty.

**Resolution**: option 2, with retention as the price of it — `prune_old_logs()` deletes daily
files older than `LOG_RETENTION_DAYS` (14) at startup, matching only the exact
`translator_YYYYMMDD.log` name so nothing else in the folder is at risk. Rewriting the format as
JSONL (global Rule 10) is deliberately **not** part of this: it changes every log line and every
reader, and the location bug is worth fixing on its own. Tracked in `DEFERRED.md`.

**References**: `src/utils/logging_setup.py`, `tests/test_logging_setup.py`,
`config.py` (`CONFIG_DIR`, the same root).

---

### Decision 12 — The "already running" notice is a native dialog with a watchdog

**Date**: 2026-09-07
**Status**: RESOLVED

**Problem**: the second instance's notice hung the process forever, invisibly. ttkbootstrap's
`Messagebox` builds its dialog with `transient=<the root>`; `main.py` withdraws that root; Tk
withdraws a transient window whose master is withdrawn. The dialog was never mapped and `show()`
waited in `wait_window()` for a click that could not be given. Measured with py-spy on a process
resident since 2026-08-19.

**Options considered**:
1. **Deiconify the root before showing the dialog** — Pros: one line. Cons: flashes an empty main
   window at someone who did not ask for one, and leaves the modality trap in place for the next
   dialog built this way.
2. **Stdlib `tkinter.messagebox`** — Pros: on Windows it is a native dialog (verified: window
   class `#32770`, visible), so a withdrawn owner cannot hide it; no `grab_set`, no transient.
   Cons: it does not match the app's theme — acceptable for a one-line notice that appears once.
3. **Signal the running instance to show itself** — the lock socket is already listening, so the
   second instance could connect and the first could raise its window. Pros: what most apps do,
   and strictly better UX. Cons: needs an accept loop in the app's lifecycle, which is well
   beyond fixing a hang. Deferred, not rejected.

**Resolution**: option 2, plus a daemon `threading.Timer` that calls `os._exit(0)` after
`ALREADY_RUNNING_TIMEOUT_S` (60 s). The dialog fix removes the known hang; the watchdog makes the
whole path incapable of stranding a process, whatever a future dialog does. `os._exit` rather
than `sys.exit` for the reason already documented for the updater: `SystemExit` is catchable, and
Tk catches it. Option 3 is recorded in `DEFERRED.md`.

**References**: `main.py` (`_warn_already_running`), `tests/test_single_instance_notice.py`,
CLAUDE.md → Known Issues (the `grab_set()` entry this extends).

---

### Decision 11 — The popup's model credit is read from the service, not carried in the queue

**Date**: 2026-09-02
**Status**: RESOLVED

**Problem**: the popup should say which model produced the result. The value has to travel from a
background worker thread to a Tk callback, and it has to survive three paths that do not share a
shape: the translation queue (whose tuple length already encodes *which kind* of result it is —
4, 5 or 6 items), the screenshot handler (which calls the API manager directly and never touches
the queue), and a cache hit (where no model ran at all).

**Options considered**:
1. **Add a 7th element to the queue tuple** — Pros: the credit travels with the result it
   describes, no shared state. Cons: the tuple is already overloaded as a type tag; every
   producer (nine `put()` sites) and the single consumer would need updating, and the screenshot
   path still bypasses it. Rejected: the cost is spread over a lot of code for one string.
2. **A callback the popup calls when it renders** — Pros: no plumbing. Cons: the popup would ask
   "who answered?" at paint time, which is not when the answer was true; a re-render after any
   later call shows the wrong model.
3. **Record it on the service, read it at show time** (chosen) — Pros: one attribute, one
   producer (`_call_model`), one default (`show_quick_translate`); the screenshot path opts in
   with one assignment. Cons: it is shared mutable state, so two translations genuinely in
   flight at once could cross. They cannot be, in this app — a hotkey translation blocks on the
   cooldown and the popup shows one result at a time — but it is the real limitation.

**Resolution**: option 3. `AIAPIManager` records `(model, provider)` inside `_generate_content` /
`_generate_content_multimodal`, the two functions every successful call funnels through, so
auto-detection and rotation substitutes are named correctly without eight bookkeeping sites.
`TranslationService._call_model()` snapshots it immediately after its own call.
`app.show_quick_translate()` defaults `model_info` from it, which covers the queue and the
screenshot handler at once.

**On cache hits**: the stored entry's `model_used` is the credit, marked `, cached` — which is
why `add_entry()` is finally passed a real value instead of always defaulting to `'Auto'`.
Entries written before this carry `'Auto'`, which names nothing; those show **no note at all**.
Rejected: falling back to the most recent live model. A note that quietly names the wrong model
is worse than no note, because it looks like evidence.

**Rejected wording**: "Translated with X" on a grammar fix (it was not translated — the popup
says "Fixed with X"), and any note on a failure popup (nothing was produced to credit).

**References**: `src/core/api_manager.py` (`last_attribution`, `_record_attribution`),
`src/core/translation.py` (`_call_model`, `_cached_attribution`), `src/core/history.py`
(`find_cached_entry`), `src/ui/quick_translate.py` (`ATTRIBUTION_*`), `tests/test_attribution.py`

---

### Decision 10 — Word-like ruby: lift the plain text, drop the plate

**Date**: 2026-08-28
**Status**: RESOLVED

**Problem**: two defects reported together. (1) Selecting annotated text and pressing Ctrl+C put
only the *unannotated* characters on the clipboard — every word carrying a reading vanished.
(2) Plain text and annotated words on the same line did not sit on the same baseline, so a
Japanese sentence read as a jumble instead of a line. The ask was Word's behaviour: base
characters level and evenly spaced, readings above them.

**Measured cause**: `Text.get()` returns zero characters for an embedded window, and Tk's default
`<<Copy>>` exports the selected characters. Separately, `window_create(align='baseline')` aligns
the *bottom of the window* with the line's baseline, so the base characters inside the frame end
up one descent + the frame's bottom padding above it — 6 px with Yu Gothic 11. All four `align`
values were measured; none produces a shared baseline.

**Options considered**:
1. **Clip the frame at the base label's baseline** — Pros: no compensation anywhere else. Cons:
   the descent has to go somewhere; a Frame clips its children, so glyphs get their bottoms cut.
   Rejected outright.
2. **Lift the plain text of every widget that has any ruby** — Pros: one flag, no per-line
   bookkeeping. Cons: every plain row in that widget grows 5 px. In the dictionary result window
   that is ~20 rows — it would silently grow back most of the ~150 px D1 had just removed.
3. **Lift only the logical lines that carry ruby** (chosen) — Pros: a ruby line barely changes
   height (47 → 42 px, it actually *shrinks*, because the plain text no longer hangs below the
   frame's baseline); plain paragraphs are untouched. Cons: `layout_rows()` needs a third row
   kind for plain rows that share a line with ruby, and the tag must be re-applied after each
   insertion since a Tk tag does not grow into text appended after its range.
4. **Measure the built widget instead of modelling it** — Pros: exact. Cons: the popup sizes its
   `overrideredirect` Toplevel before the widget exists; the model is not optional. *(Revisited in
   Decision 34, 2026-10-19: mapped at alpha 0, the popup can be measured after layout.)*

**Resolution**: option 3, plus the `<<Copy>>` override (`get_plain()` over the selection, bases
only — 日本語, not 日本語(にほんご)), plus the Word look the user chose: the ruby pair takes the
widget's own background instead of the `#363636` plate, and `FURIGANA_RUBY_PAD_X` drops to 0, so
an annotated word is exactly as wide as its characters. Verified on real widgets: baseline delta
0 px on every annotated word (was −6), frame width equal to the plain width of the same
characters (was +4), Ctrl+C round-trips the source text exactly. `FURIGANA_RUBY_BG` is kept as
the fallback and as an opt-in `ruby_bg=` for a deliberate plate; `RubyRow` chips are untouched.

**References**: `src/ui/ruby_text.py` (`_on_copy`, `_refresh_lift`, `LIFT_TAG`,
`tk_layout_model`, `layout_rows`); `src/constants.py` (`FURIGANA_RUBY_PAD_X`,
`FURIGANA_RUBY_BG`); `tests/test_ruby_text.py` (`TestCopySelection`, `TestBaselineAlignment`,
`TestWordLikeRhythm`); CLAUDE.md "Renderer: src/ui/ruby_text.py".

### Decision 9 — Furigana readings stay blue (`#80b8ff`)

**Date**: 2026-08-28
**Status**: RESOLVED

**Problem**: readings render blue. Before Phase F2 they rendered white — but not by choice.
ttkbootstrap was silently discarding the explicit colour kwarg at widget construction, so the
blue the code had always asked for never reached the screen. F2 fixed the mechanism
(`NO_AUTOSTYLE`), which made the blue visible for the first time. So the question was never
"should we change the colour" but "which of the two was ever intended".

**Options considered**:
1. **Keep blue `#80b8ff`** — Pros: what the code always specified; separates the reading from the
   base character at a glance, which is the whole point of a reading; survives on the `#363636`
   plate. Cons: less like print furigana, which is monochrome.
2. **Revert to white `#ffffff`** — Pros: what users actually saw for two releases; closer to
   Word/print. Cons: reinstates a bug's side effect as a design choice; a white reading over a
   white base character is hard to tell apart at 7pt.

**Resolution**: keep blue. Confirmed by the user on 2026-08-28. `FURIGANA_RUBY_FG` is unchanged —
this decision exists so the question is not reopened from the white-was-intended angle again.

**References**: `src/constants.py` (`FURIGANA_RUBY_FG`); CLAUDE.md Known Issues (the ttkbootstrap
entry); `src/ui/ruby_text.py` (`NO_AUTOSTYLE`); was D3 in `DEFERRED.md`.

### Decision 8 — Furigana everywhere: annotate at render time, structured segments, fail-safe readings

**Date**: 2026-08-04 (addenda: Phase 1 2026-08-05, Phase 4 2026-08-07, Phases 5-6 2026-08-10,
Phase 7 2026-08-17)
**Status**: RESOLVED (Phases 0-7 implemented; feature complete)

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
on the UI thread for content that is already capped at `MAX_ANNOTATE_CHARS`. *(Revisited for the
quick-translate popup in Decision 34, 2026-10-19: built once at alpha 0 and measured after
layout - nothing is built twice and nothing flashes.)*

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

**Phase 7 addendum — prewarming has to do the work, not ask whether it can.** `prewarm()` was
written in Phase 0 and never called by anything, so the dictionary load had been landing on the
UI thread at the first Japanese render for the whole feature's life. Wiring it up was not enough:
the obvious body — probe `active_provider_name()` — stops at the **first** available provider,
but `_refine_compounds()` consults pykakasi on *every* annotation even when fugashi is active, so
the larger half of the cost stayed where it was. Measured cold, fugashi installed: probe 315 ms,
and the first annotation after it still 407 ms. It therefore annotates a real sample. The sample
must contain kanji **and** kana, because `should_annotate()` rejects kanji-only text without a
language hint and prewarm passes none — a wrong sample would make the whole thing a silent no-op,
which is why a test pins it. Result: first UI-thread annotation 217.7 ms → 0.6 ms.

Moving work to a thread meant admitting what was already true: `annotate()` is reached from the
UI thread at render time *and* from the translation worker via `generate_furigana()`, and a MeCab
tagger is not documented thread-safe. The providers now serialize on the lock their constructors
already held. Prewarm carries no error handling of its own — `annotate()` already swallows
everything and falls back to plain text, so a local `try` would be unreachable code implying a
failure mode that does not exist.

The tuning knobs moved to `src/constants.py` under a `FURIGANA_` prefix and are aliased back to
their local names, so a value has exactly one definition and no call site changed. Equality tests
alone would not catch a literal pasted back in, so a second test asserts the modules do not
re-declare the names at all.

The build guard exists because this feature's failure mode is **silence**: without
`kanwadict4.db` the provider logs a `FileNotFoundError` and renders plain text, so an EXE with no
furigana in it looks like a successful build — and pykakasi is the only provider a fresh install
has, since fugashi/UniDic arrives later and only if the user installs the Japanese pack. It
checks twice, because the two failures are different: the environment can be missing the file
(pre-flight, aborts) or the spec can fail to bundle it (post-build, warns). The post-build check
reads PyInstaller's own `CArchiveReader` TOC rather than searching the binary for the filename,
so it cannot be satisfied by the name appearing in some unrelated blob.

**Phase 6 addendum — whose tokenization wins.** The word chips are already tokenized, by
`nlp_manager`, and the obvious move is to annotate each chip. Measurement killed that: this
tokenizer splits 日本語 into 日本 + 語, and 日本 annotated alone reads **にっぽん** where the
compound is にほん — so per-chip annotation prints a wrong reading on exactly the words a learner
is looking up. `annotate_tokens()` therefore annotates the **line** and hands the readings out,
leaving a token bare when it cuts through one. The decision is a single join check — the per-token
form of I1 — rather than a boundary guard: a ruby run is never clipped, so an overhanging run
cannot produce a string equal to the token. A plain run *is* clipped, because splitting text that
carries no reading cannot make it wrong, and that is what lets 会い keep 会[あ].

Two measured layout facts came with it. `window_create` defaults to `align='center'`, which lifts
the plain chips **7 px** off an annotated chip's baseline; `align='baseline'` brings both to within
1 px. And `CustomWordBox(height=1)` clips its own tags, because `height` counts base-font rows —
the same unit confusion as Phase 1, in a second place — so the row count is derived from font
metrics instead.

Chips and tags differ deliberately: a **chip** is a fragment of a sentence and takes its reading
from that sentence; a **tag** is one lookup phrase the user typed or composed, with no larger
context, so it is annotated on its own.

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
**Status**: SUPERSEDED by Decision 34 (2026-10-19) - the bar grew to need 735 px, so at 670 px
the close button is not drawn on any short result

**Problem**: R1 + R2 add two buttons (Re-translate, Custom Prompt) to an already 5-element
bar, making 7 actions + close — crowded.

**Options considered**:
1. **Single wide bar** — widen popup minimum 560→670px. Simple, all actions visible.
2. **Two-row bar** — keep width, wrap to a second row. Adds height.
3. **"⋯" overflow menu** — keep narrow, hide less-used actions. More code, less discoverable.

**Resolution**: Developer chose **single wide bar** ("One row, widened") — simplest, lowest
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
