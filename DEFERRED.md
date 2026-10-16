# CrossTrans — Deferred Items

> Work that was identified, deliberately not done, and should not be lost. Review at milestone
> starts: flag anything whose trigger condition is now met, and delete an entry once it ships.
>
> Nothing here is a bug report from a user — these are findings from implementation work that were
> left alone on purpose, mostly under the "touch only what the task requires" rule.

---

### D11 - Eight providers' hardcoded default models are still unverified

**Found**: 2026-09-07, while replacing Groq's (Decision 15). **Narrowed twice on 2026-09-08**:
Google (Decision 19) and OpenRouter (Decision 20). Each check made the finding worse before it
made it smaller - every provider examined so far had a **completely** dead default list.
**Effort**: Small per provider, and it needs a key for each.

`STATIC_DEFAULT_MODELS_BY_PROVIDER` in `cloudflare_worker.js` - the table the 12-hourly cron
copies into KV **without regenerating** - is what auto-detection and `_try_model_rotation()` read
whenever the model field is blank. Three of its thirteen entries have been checked and all three
were entirely dead. The other eight have not:

| Provider | Claims | Checked |
|---|---|---|
| Google | `gemini-2.5-flash`, `-flash-lite`, `gemini-flash-latest` | yes - real call, 2026-09-08 |
| Groq | `openai/gpt-oss-120b`, `-20b` | yes - real call, 2026-09-08 |
| Cerebras | `gpt-oss-120b`, `qwen-3.8-27b` | yes - real call; dead ones 404, live ones 402 (no credit) |
| SambaNova | `Meta-Llama-3.3-70B-Instruct`, `gemma-4-31B-it` | **listing only** - 402 precedes model validation |
| OpenRouter | `google/gemma-4-31b-it:free`, `nvidia/nemotron-3.5-lightning:free` | partly - routable, but no completion call |
| OpenAI | `gpt-4o-mini`, `gpt-4o`, `gpt-3.5-turbo` | no |
| Anthropic | `claude-3-5-sonnet-20241022`, `-haiku-20241022`, `claude-3-haiku-20240307` | no |
| DeepSeek | `deepseek-chat`, `deepseek-coder` | no |
| xAI | `grok-2`, `grok-beta` | no |
| Mistral | `mistral-large-latest`, `mistral-small-latest` | no |
| Perplexity | `sonar`, `sonar-pro` | no |
| Together | `meta-llama/Llama-3.3-70B-Instruct-Turbo`, `-3.1-70B-...` | no |
| SiliconFlow | `deepseek-ai/DeepSeek-V3`, `Qwen/Qwen2.5-72B-Instruct` | no |

**Five checked, five entirely or half dead.** Google 3/3 dead, Groq 3/3 dead, Cerebras 2/2 dead,
OpenRouter 2/2 dead, SambaNova 1/2 dead. Not one provider's table was clean. Assume the remaining
eight are broken until shown otherwise rather than the other way round.

**Read the reply code, and know what each provider checks first.** Cerebras validates the model
before billing, so `404` and `402` genuinely distinguish gone from exists. SambaNova checks
billing first and returns `402` even for a model absent from its own catalogue, so a `402` there
proves nothing at all.

`grok-2`, `grok-beta`, `gpt-3.5-turbo` and the dated `claude-3-5-*-20241022` pins look retired on
sight, and every `llama-3.3-70b` variant is now doubly suspect: Groq, Cerebras **and** SambaNova
have each dropped theirs.

**And check the key pattern, not only the model.** `API_KEY_PATTERNS` has no entry for OpenAI,
DeepSeek, Mistral, Together, SiliconFlow or SambaNova, and `_detect_provider_from_key()` falls
back to **Google** when nothing matches - so any of those users on Provider='Auto' with a blank
model field is handed a Gemini model and sends it to their own provider's endpoint. Cerebras had
exactly this bug until `csk-` was added on 2026-09-08. SambaNova cannot be fixed this way (bare
UUID keys); the others have distinguishable prefixes and should be checked when their keys are at
hand.

**Still open on OpenRouter specifically**: both new defaults are confirmed routable but neither
has been sent a real translation. The thing to check is **latency**: this path sends no
`max_tokens`, but `_call_generic_openai_style` uses `timeout=10`, and both of these lean
reasoning/agentic. On Groq the comparable reasoning model took 1.3 s where gpt-oss took 0.7 s, so
this is a live risk, not a formality.

**Two shortcuts that do NOT work - both measured, so nobody spends the effort again:**

1. **Filtering the defaults against `model_provider_map`**, which is what D11 originally proposed.
   Simulated across all thirteen providers on 2026-09-08: for Google it would have *kept*
   `gemini-2.0-flash`, because OpenRouter still lists a model that answers 404. For the
   OpenRouter-derived providers the catalogue is exactly as stale as the thing it would check.
   See Decision 19.
2. **Reading OpenRouter's per-model `/endpoints` resource** to learn which upstreams serve a
   model, and inferring the native IDs from that. It lists **Groq** as serving
   `meta-llama/llama-3.3-70b-instruct`; Groq's own catalogue, fetched with a real Groq key the
   same morning, has no llama-3.3 at all. It reflects OpenRouter's routing deals, not what a
   user's own key can call. See Decision 20.

**What does work** is `fetchGroqModels()` / `fetchGeminiModels()`: ask the provider directly. That
needs a key per provider in the Worker, and only Cerebras, SambaNova, Groq and Gemini keys exist
there - and Worker secrets cannot be read back, so even those two cannot be verified from a
developer machine.

**Dependency**: an API key per provider. **Trigger**: a provider's auto-pick failing for a user,
or the next time any of these keys is at hand. Whoever holds one: call the model, do not just look
it up - `gemini-2.5-pro` is *listed* by Google's API and 404s when used.

**And check the routing, not only the model.** A default must also *identify* as its own provider:
`_identify_provider()` matches `model_provider_map` first, then prefix rules in which `google/`
means Together and `meta-llama/` means Together. A slash-prefixed default that is missing from the
map gets sent to the wrong endpoint entirely - which is what both dead OpenRouter defaults were
doing on top of being retired. `tests/test_default_model_routing.py` guards this for all thirteen.

---

### D12 - Thirteen model IDs are claimed by two providers at once

**Found**: 2026-09-08, while adding Cerebras's and SambaNova's real catalogues.
**Effort**: Medium - it changes shared routing logic, so it wants its own change and its own tests.

`_identify_provider()` resolves a model name by walking `model_provider_map` and returning the
**first** provider whose list contains it. Thirteen IDs appear under two providers, so for one of
the two the answer is always wrong:

| Model | Claimed by | Resolves to |
|---|---|---|
| `gpt-oss-120b` | Cerebras, SambaNova | Cerebras |
| `meta-llama/llama-3.3-70b-instruct` | OpenRouter, HuggingFace | OpenRouter |
| `meta-llama/llama-3.1-70b-instruct` | OpenRouter, HuggingFace | OpenRouter |
| `deepseek-ai/deepseek-r1` | Together, SiliconFlow | Together |
| `qwen/qwq-32b-preview` | Together, SiliconFlow | Together |
| `google/gemma-2-27b-it`, `-9b-it` | Together, HuggingFace | Together |
| `mistralai/mistral-7b-instruct-v0.3` | Together, HuggingFace | Together |
| `mistralai/mixtral-8x7b-instruct-v0.1` | Together, HuggingFace | Together |
| `qwen/qwen2.5-{7,14,32,72}b-instruct` | SiliconFlow, HuggingFace | SiliconFlow |

Twelve of these predate this work; `gpt-oss-120b` was added on 2026-09-08 with SambaNova's real
catalogue. It was **not** removed to hide the clash - SambaNova genuinely serves it, and dropping
a real model from the dropdown to flatter a heuristic is the wrong trade.

**It only bites under `provider='Auto'`.** A user who names their provider never reaches
`_identify_provider()`, and that is the normal case for a second provider on a shared model.

**The clash is not resolvable from the model name** - the same open-weight model really is served
by several providers, so any ordering is wrong for somebody. The fix is to consult the API key
first: `_identify_provider()` already reads `api_key_patterns` at step 4, but step 1 wins before
it. Making the exact-match step prefer the provider the key belongs to would resolve every row
above where the key is distinguishable.

**Blocked on the same gap as D11**: `API_KEY_PATTERNS` covers only Groq, Anthropic, xAI,
OpenRouter, Perplexity, HuggingFace and (since 2026-09-08) Cerebras. Together, SiliconFlow and
SambaNova have no pattern - SambaNova's keys are bare UUIDs and cannot get one - so the key-first
rule would fix `gpt-oss-120b` and the OpenRouter/HuggingFace rows and leave the
Together/SiliconFlow ones exactly as they are.

**Dependency**: none technically; it wants a decision about whether Auto-mode ambiguity is worth
changing shared routing for. **Trigger**: a user reporting that a model they picked went to the
wrong provider, or the next time `_identify_provider()` is touched for another reason.

---

### D17 - The History dialog takes about a second to open with 100 entries

**Found**: 2026-10-15, measuring the History-row readings (the plan's J9; the plan, `TODO.md`, is archived: `git show 5cc8736:TODO.md`). **Effort**: Medium.

With 100 entries the dialog takes **0.93-0.95 s** to open on the development PC *without*
readings (1.6 s the first time in a process), under a ttkbootstrap root - the readings add about
0.33 s on top (J9 kept that low by drawing each annotated line on one canvas; the first version,
a frame and two labels per segment, took 4.1 s). The baseline is the dialog's own construction:
eight Tk widgets per row (frame, top row, two labels, time, delete, separator, plus the content
labels), every one a native child window on Windows, each passed through ttkbootstrap's style
wrapper, then one geometry pass over all of them. TODO.md J9 budgeted 300 ms for the whole
dialog; the baseline alone is three times that.

**Fix candidates**: build only the rows in view and add the rest as the list scrolls; or draw
each row on one canvas as `RubyLine` does for its lines; or page the list. **Dependency**: none.
**Trigger**: a user reporting a slow History window, or the next change to `history_dialog.py`.

---

### D18 - Dead code met during the language-identity work

**Found**: 2026-10-15. **Effort**: Small.

- `TranslationService.do_translation()` (`src/core/translation.py`) has no live caller -
  `tests/test_callback_wiring.py` asserts the hotkey path uses `do_translate_or_fix()` instead.
  It was left out of J6 on purpose (TODO.md section 10), so it still generates its source block
  without the J6 hint; anyone reviving it would get the old rule.
- `TranslatorApp._open_settings_dictionary_tab()` (`src/app.py`) has no caller.

Both predate this work and were left alone under Rule 3. **Trigger**: the next cleanup pass, or
anyone about to call either.

---

### D19 - pykakasi, the one reading provider every install has, misreads common words

**Found**: 2026-10-16, running the suite on a clean venv (Phase K1). **Effort**: Small to Large,
by option.

A fresh install has one reading provider, pykakasi. fugashi + UniDic arrives only with the
Japanese NLP pack (Settings -> Dictionary), so a user who never opens that tab - most users -
reads every Japanese surface through pykakasi. Measured on 3000 random Tatoeba sentences that
contain kanji (CC-BY 2.0 FR, `random.seed(20261016)` over the 244 364 such sentences): **898
(30%)** have at least one word the two providers read differently; 165 distinct differences.
Not every difference is a pykakasi error - 私 わたし / わたくし and 明日 あした / あす are both
valid, and in お母さん it is fugashi's はは that is wrong - but the most frequent include plain
mistakes:

| Word | pykakasi | fugashi | Sentences (of 3000) | Example |
|---|---|---|---|---|
| 人 | にん | ひと | 85 | 私が頼れる人を |
| 彼 | か | かれ | 66 | 彼の自尊心 (pykakasi reads 彼の as かの) |
| 君 | くん | きみ | 54 | 君の計画 |
| 金 | きん | かね | 27 | その金を渡した |
| 入 | い | はい | 12 | 本題に入る |
| 今日 | こんにち | きょう | 10 | 今日は気分が悪い (the greeting entry 今日は) |
| 怒 | いか | おこ | 10 | 怒って電話を切った |

That is "blank beats a wrong reading" (Decision 8) failing in the default configuration, not in
an edge case. It predates the language-identity work: the provider chain is F1's, and its
docstring already names 今日 -> こんにち as the reason fugashi is preferred.

**Options**:
1. **Ship fugashi + unidic-lite in the EXE** - every user gets the provider the tests are written
   against. unidic-lite is 249 MB installed (a 47 MB download); the EXE is 66 MB today.
2. **Point Japanese readers at the pack** - a one-time hint the first time pykakasi draws a
   reading, linking to Settings -> Dictionary.
3. **Correct pykakasi's worst entries by hand** (彼の, 今日は, 人...) - whack-a-mole, and every
   correction is itself a guess about context, which is what the principle forbids.
4. **Leave it**, and say so in the README.

**Dependency**: the user's choice - it trades download size against reading quality. **Trigger**:
that decision, or a user reporting a wrong reading.
