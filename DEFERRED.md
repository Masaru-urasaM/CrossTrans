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
| OpenAI | `gpt-4o-mini`, `gpt-4o` (`gpt-3.5-turbo` dropped) | replaced 2026-10-16 (K15) from the docs - listed, not called |
| Anthropic | `claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-haiku-4-5` | replaced 2026-10-16 (K15) from the docs - listed, not called |
| DeepSeek | `deepseek-flash`, `deepseek-v4-pro` | replaced 2026-10-16 (K15) from the docs - listed, not called |
| xAI | `grok-4.20-0309-non-reasoning`, `grok-4.3` | replaced 2026-10-16 (K15) from the docs - listed, not called |
| Mistral | `mistral-large-latest`, `mistral-small-latest` | no |
| Perplexity | `sonar`, `sonar-pro` | no |
| Together | `meta-models/Muse-Glimmer-30B`, `zai-org/GLM-5.3-Flash` | replaced 2026-10-16 (K15) from the docs - listed, not called |
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

**Replaced, 2026-10-16** (K15, the user: "do it now"). The five lists their own providers document
as dead or going now hold the providers' current models - in `api_manager`'s tier 3 and in the
Worker's `STATIC_DEFAULT_MODELS_BY_PROVIDER` alike, every new ID also listed under its provider in
`MODEL_PROVIDER_MAP` / `STATIC_PROVIDER_MODELS` (no prefix rule knows `meta-models/` or
`zai-org/`), and `tests/test_default_model_routing.py` now also fails on a default its provider
has retired. Fast, non-reasoning models first. Checked: a local `wrangler dev` run of the cron
served all thirteen lists, and each default routed to its own provider through that config.
**What is still open**, and why this entry stays: no key, so not one replacement has answered a
real call; OpenAI's two remaining defaults expire on 2027-01-14 (replacement named:
`gpt-6-luna`); Perplexity's endpoint question; SiliconFlow unconfirmed; the key patterns above;
and the dropdown lists still offer the dead IDs (`grok-2`, `deepseek-chat`, ...) - only the
defaults were replaced. **The user, 2026-10-19: no keys for these providers - skip the real calls
for now.** The trigger stands: a key at hand, or a user's auto-pick failing.

**Deployed, 2026-10-19** (the user: "do it now"; version `fd9a6b08`, KV rebuilt at once). Users
receive the new lists now, whatever their version. **Eight providers, not five**: the Cerebras,
SambaNova and OpenRouter rows above and `csk-` were changed in the file on 2026-09-08 *after* that
day's last deploy (12:13 JST; saved 14:03), so the served config still held the dead lists those
rows replaced - found by downloading the deployed code and diffing it before deploying. Details
and checks in CHANGELOG "Worker deploy". Still served, from OpenRouter's catalogue rather than the
static tables: Cerebras's `llama-3.3-70b`, `llama3.1-70b`, `llama3.1-8b`, `qwen-3-32b` and
SambaNova's four 3.1/3.2 Llamas, `DeepSeek-R1` and both Qwen2.5 - the dropdown item above.

**K8's reasoning, superseded by the two paragraphs above:** not changed in code, on purpose: the replacements are what the providers name, not what a call
proved (the rule above), and the table users actually receive is the Worker's, whose deploy is
the user's to approve. **Next step**: with a key per provider, call the named replacement, then
change `STATIC_DEFAULT_MODELS_BY_PROVIDER` and the tier-3 copy together - Anthropic, xAI and
DeepSeek first (entirely dead), Together and OpenAI before 2026-10-22/23.

**And check the routing, not only the model.** A default must also *identify* as its own provider:
`_identify_provider()` matches `model_provider_map` first, then prefix rules in which `google/`
means Together and `meta-llama/` means Together. A slash-prefixed default that is missing from the
map gets sent to the wrong endpoint entirely - which is what both dead OpenRouter defaults were
doing on top of being retired. `tests/test_default_model_routing.py` guards this for all thirteen.

**At tier 1 that test cannot see everything** (found on the served config, 2026-10-19). Put through
the app's own `_identify_provider()` with a key shaped like its provider's, 27 of the 28 served
defaults came back to their provider; SambaNova's `gemma-4-31B-it` went to **Google**. Google's
tier-1 list is Gemini's own catalogue (`fetchGeminiModels()`), which carries `gemma-4-31b-it`; the
map match ignores case, so both providers claim it, and `_claimant_for_key()` cannot rule Google
out - Google, the key fallback, has no prefix in `API_KEY_PATTERNS` - so with a SambaNova key,
which has none either, the first claimant wins. **No user path reaches it**: defaults are read only
by auto-detection and rotation, which call the provider they were given; re-identification happens
only under Provider='Auto', where a SambaNova key is read as Google anyway; and a typed
`gemma-4-31B-it` under Auto went to Google before the deploy too. The tier-3 test could not see it
(`constants.py`'s Google list has no Gemma), nor could K15's `wrangler dev` run (no Gemini key
locally, so `gemini_source` was static). 15 IDs in the served map are shared only when case is
ignored (`deepseek-r1` and `deepseek-v3.2` between DeepSeek and SambaNova, ...). **A possible fix,
not made**: `'AIza': 'Google'` in both key-pattern tables (Google API keys have begun `AIza` so far
- check first), so a key without it stops counting as Google's; it changes Decision 31's
tie-break, so it is the user's call. **Trigger**: a SambaNova user on Auto, or the next change to
`_claimant_for_key()`.

---

### D20 - The popup's `WS_EX_NOACTIVATE` has never been in effect

**Found**: 2026-10-19, while giving the new icon tooltips the same style (Decision 34).
**Effort**: Small to apply; deciding is the hard part.

`QuickTranslateManager._apply_noactivate()` sets `WS_EX_NOACTIVATE` right after the Toplevel is
created - before Tk has made the window that carries the style. Tk creates that wrapper when it
first maps the Toplevel; until then `GetParent(winfo_id())` is 0, so the bit lands on Tk's inner
window and is lost. Measured on the code before this work (`53fee8e`) and after it: once shown, the
wrapper's extended style is `0x80` (`WS_EX_TOOLWINDOW`; `0x80080` with the new alpha's
`WS_EX_LAYERED`), never `0x08000000`. CLAUDE.md said the popup never takes the focus; it can.

What that means today (not measured - the private desktop takes no input): a click on the popup
should activate it like any window. That is also what makes two things work which the documented
design would break - **Ctrl+C on a selection made in the popup** (`RubyText`'s `<<Copy>>` override
needs the keyboard) and **Esc once the popup was clicked**. Replace works either way: the popup
closes before the paste and Windows hands the focus back.

**Options**: (1) leave it, docs corrected (done: CLAUDE.md "Replace Button"); (2) make it effective
after mapping, as the tooltips now are (`<Map>`) - the popup never takes the focus, and Ctrl+C and
Esc go to the user's app; (3) effective, plus a way to copy part of a translation without the
keyboard. **The user's call.** **Trigger**: a user reporting that a click on the popup takes the
focus from their app - or one wanting Ctrl+C there; either way the trade-off above.
