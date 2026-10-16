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

**Desk check of the other eight, 2026-10-16** (K8 - the providers' own deprecation pages, no key,
no call; the tier-3 table in `api_manager.DEFAULT_MODELS_BY_PROVIDER` carries the same IDs). It
cannot confirm a model is alive, only that its provider says it is gone or going - and four
more lists are:

| Provider | Defaults | What the provider's own documentation says |
|---|---|---|
| Anthropic | all three | **All retired**: `claude-3-5-sonnet-20241022` 2025-10-28, `claude-3-5-haiku-20241022` 2026-02-19, `claude-3-haiku-20240307` 2026-04-20; "requests to retired models will fail". Replacements it names: `claude-sonnet-5-5`, `claude-haiku-4-5-20251001`; `claude-haiku-5-5` is listed Active ([model deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations)) |
| xAI | `grok-2`, `grok-beta` | **Neither is on the model list** - only the grok-4.x family is ([models](https://docs.x.ai/docs/models)) |
| DeepSeek | `deepseek-chat`, `deepseek-coder` | **Neither is in the API docs any more**; the current names are `deepseek-flash` and `deepseek-v4-pro`, with the legacy `deepseek-v4-flash` still accepted ([API docs](https://api-docs.deepseek.com/)). Secondary sources date the retirement of `deepseek-chat` to 2026-07-24 |
| Together | both | `meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo` **removed 2026-02-25**; `meta-llama/Llama-3.3-70B-Instruct-Turbo` **to be removed 2026-10-22**, replacement `meta-models/Muse-Glimmer-30B` ([deprecations](https://docs.together.ai/docs/deprecations)) |
| OpenAI | `gpt-4o-mini`, `gpt-4o`, `gpt-3.5-turbo` | `gpt-3.5-turbo` **shuts down 2026-10-23** (replacement `gpt-5.6-terra`); the `gpt-4o` and `gpt-4o-mini` snapshots on 2027-01-14 (`gpt-6-luna`) ([deprecations](https://developers.openai.com/api/docs/deprecations)) |
| Mistral | `mistral-large-latest`, `mistral-small-latest` | Expected alive: by policy a `-latest` alias moves to the newer model by itself ([model lifecycle](https://docs.mistral.ai/inference/model-lifecycle)) |
| SiliconFlow | `deepseek-ai/DeepSeek-V3`, `Qwen/Qwen2.5-72B-Instruct` | Not among the discontinued models in the release notes ([release notes](https://api-docs.siliconflow.cn/docs/release-notes/overview)) - unconfirmed either way |
| Perplexity | `sonar`, `sonar-pro` | Still priced, but the July 2026 changelog says "Sonar Chat Completions is now Agent API" ([changelog](https://docs.perplexity.ai/changelog)); third parties date the end of `/chat/completions` for Sonar to 2026-09-27. **The risk may be the endpoint the app calls, not just the model** |

Not changed in code, on purpose: the replacements are what the providers name, not what a call
proved (the rule above), and the table users actually receive is the Worker's, whose deploy is
the user's to approve. **Next step**: with a key per provider, call the named replacement, then
change `STATIC_DEFAULT_MODELS_BY_PROVIDER` and the tier-3 copy together - Anthropic, xAI and
DeepSeek first (entirely dead), Together and OpenAI before 2026-10-22/23.

**And check the routing, not only the model.** A default must also *identify* as its own provider:
`_identify_provider()` matches `model_provider_map` first, then prefix rules in which `google/`
means Together and `meta-llama/` means Together. A slash-prefixed default that is missing from the
map gets sent to the wrong endpoint entirely - which is what both dead OpenRouter defaults were
doing on top of being retired. `tests/test_default_model_routing.py` guards this for all thirteen.

---

### D19 - pykakasi, the one reading provider every install has, misreads common words

**Found**: 2026-10-16, running the suite on a clean venv (Phase K1). **Effort**: Small to Large,
by option.

A fresh install has one reading provider, pykakasi. fugashi + UniDic arrives only with the
Japanese NLP pack (Settings -> Dictionary), so a user who never opens that tab - most users -
reads every Japanese surface through pykakasi. Measured on 3000 random Tatoeba sentences that
contain kanji (CC-BY 2.0 FR, `random.seed(20261016)` over the 244 364 such sentences; reproduce
with `tools/measure_cjk_evidence.py readings`): **898
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
