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
| Groq | `openai/gpt-oss-120b`, `-20b` | yes - real call, 2026-09-07 |
| OpenRouter | `google/gemma-4-31b-it:free`, `nvidia/nemotron-3.5-lightning:free` | partly - routable, but no completion call |
| OpenAI | `gpt-4o-mini`, `gpt-4o`, `gpt-3.5-turbo` | no |
| Anthropic | `claude-3-5-sonnet-20241022`, `-haiku-20241022`, `claude-3-haiku-20240307` | no |
| DeepSeek | `deepseek-chat`, `deepseek-coder` | no |
| xAI | `grok-2`, `grok-beta` | no |
| Mistral | `mistral-large-latest`, `mistral-small-latest` | no |
| Perplexity | `sonar`, `sonar-pro` | no |
| Cerebras | `llama-3.3-70b`, `llama3.1-70b` | no |
| SambaNova | `Meta-Llama-3.3-70B-Instruct`, `-3.1-70B-Instruct` | no |
| Together | `meta-llama/Llama-3.3-70B-Instruct-Turbo`, `-3.1-70B-...` | no |
| SiliconFlow | `deepseek-ai/DeepSeek-V3`, `Qwen/Qwen2.5-72B-Instruct` | no |

`grok-2`, `grok-beta`, `gpt-3.5-turbo` and the dated `claude-3-5-*-20241022` pins look retired on
sight, and every `llama-3.3-70b` variant is suspect after what Groq did.

**Still open on OpenRouter specifically**: both new defaults are confirmed routable but neither
has been sent a real translation. The thing to check is the failure already measured on Groq -
`max_tokens` is 1024, and a reasoning model that spends that budget inside `<think>` truncates the
answer. Both of these lean reasoning/agentic, so this is a live risk, not a formality.

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
