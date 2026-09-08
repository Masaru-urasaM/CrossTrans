# CrossTrans — Deferred Items

> Work that was identified, deliberately not done, and should not be lost. Review at milestone
> starts: flag anything whose trigger condition is now met, and delete an entry once it ships.
>
> Nothing here is a bug report from a user — these are findings from implementation work that were
> left alone on purpose, mostly under the "touch only what the task requires" rule.

---

### D5 — Structured (JSONL) logging with rotation

**Found**: 2026-09-07, while moving the frozen app's log out of the PyInstaller temp directory.
**Effort**: Medium.

Global Rule 10 asks for `{"ts","level","tag","msg"}` JSON Lines with ring-buffer rotation. The log
is still `%(asctime)s [%(levelname)s] %(message)s`, one file per day, now pruned after 14 days
(Decision 13). Changing the format touches every call site's readability and every existing log
file anyone still has.

**Trigger**: the first time a log has to be parsed by a tool rather than read by a person.

---

### D10 — No CI

**Found**: 2026-09-07. `.github/` holds only `copilot-instructions.md`.
**Effort**: Medium.

593 tests only ever run on one machine, by hand. A `windows-latest` workflow could run them on
every push; the widget tests need a desktop session, and the ones that pop a real dialog
(`TestItReallyExits`) would need checking there.

**Trigger**: a second contributor, or the first regression that reaches a release.

---

### D11 — The other providers' hardcoded default models are unverified

**Found**: 2026-09-07, while replacing Groq's (Decision 15).
**Effort**: Small per provider, Medium to do them all properly.

Closing D6/D7 proved that `STATIC_DEFAULT_MODELS_BY_PROVIDER` in `cloudflare_worker.js` — the
table the 12-hourly cron copies into KV **without regenerating** — had a Groq entry in which both
models were decommissioned. Only Groq was checked, because only Groq was in scope. The same table
still claims `gemini-1.5-flash` / `gemini-1.5-pro`, `gpt-3.5-turbo`,
`claude-3-5-sonnet-20241022`, `grok-2` / `grok-beta`, `deepseek-coder`, `llama-3.3-70b` (Cerebras)
and `Meta-Llama-3.1-70B-Instruct` (SambaNova). Several of those look retired. The mirrored copy
in `api_manager.DEFAULT_MODELS_BY_PROVIDER` carries the same values.

This is not a fallback path: it is what auto-detection and `_try_model_rotation()` read on every
run where the model field is blank. A wrong entry costs the user a failed attempt per model, in
silence.

**Dependency**: an API key per provider to check against, the way Groq's was checked. Cerebras
and SambaNova keys exist only as Worker secrets, which cannot be read back.
**Trigger**: a provider's auto-pick fails for a user, or the next time any of these keys is at
hand. Better still, teach the cron to derive this table the way `fetchGroqModels()` already does
for the model map, so it cannot rot again.
