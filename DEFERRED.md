# CrossTrans — Deferred Items

> Work that was identified, deliberately not done, and should not be lost. Review at milestone
> starts: flag anything whose trigger condition is now met, and delete an entry once it ships.
>
> Nothing here is a bug report from a user — these are findings from implementation work that were
> left alone on purpose, mostly under the "touch only what the task requires" rule.

---

### D11 - Nine providers' hardcoded default models are still unverified

**Found**: 2026-09-07, while replacing Groq's (Decision 15). **Narrowed** 2026-09-08: Google is
done too (Decision 19), and the finding got worse before it got smaller - all three of Google's
defaults were dead as well, on the app's primary provider.
**Effort**: Small per provider, and it needs a key for each.

`STATIC_DEFAULT_MODELS_BY_PROVIDER` in `cloudflare_worker.js` - the table the 12-hourly cron
copies into KV **without regenerating** - is what auto-detection and `_try_model_rotation()` read
whenever the model field is blank. Two of its thirteen entries were verified and both were
entirely dead. The other nine have never been checked:

| Provider | Claims | Checked |
|---|---|---|
| Google | `gemini-2.5-flash`, `-flash-lite`, `gemini-flash-latest` | yes, 2026-09-08 |
| Groq | `openai/gpt-oss-120b`, `-20b` | yes, 2026-09-07 |
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
| OpenRouter | `google/gemini-2.0-flash-exp:free`, `meta-llama/llama-3.3-70b-instruct:free` | no |

`grok-2`, `grok-beta`, `gpt-3.5-turbo` and the dated `claude-3-5-*-20241022` pins look retired on
sight, and every `llama-3.3-70b` variant is suspect after what Groq did. OpenRouter's two are
already provably absent from its own live catalogue.

**Filtering the defaults against `model_provider_map` does not work - measured, not assumed.**
It was simulated across all thirteen providers on 2026-09-08 before being rejected: for Google it
would have *kept* `gemini-2.0-flash`, because OpenRouter still lists a model that answers 404.
For the nine OpenRouter-derived providers the catalogue is exactly as stale as the thing it would
be checking. Shipping it would have looked like protection and been none - see Decision 19.

**What does work** is `fetchGroqModels()` / `fetchGeminiModels()`: ask the provider. That needs a
key per provider in the Worker, and only Cerebras, SambaNova, Groq and Gemini keys exist there -
and Worker secrets cannot be read back, so even those two cannot be verified from a developer
machine.

**Dependency**: an API key per provider. **Trigger**: a provider's auto-pick failing for a user,
or the next time any of these keys is at hand. Whoever holds one: call the model, do not just
look it up - `gemini-2.5-pro` is *listed* by Google's API and 404s when used.
