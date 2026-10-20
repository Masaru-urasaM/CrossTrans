# Linked reading - Release evidence

**Status:** v1.9.21 accepted and release authorized by the user on 2026-10-20.
Linked reading remains experimental. The 2026-10-20 asset refresh defaults it ON for
new/missing preferences, retaining saved OFF choices (Decision 44). No active implementation tasks.

## Delivered

- Single-response source IDs for eligible translations; no second alignment/repair request.
- Popup/main/cache/History links, shared toggles, ruby-safe highlighting and conservative local legacy maps.
- Both panes expand; Original stays visible and wraps words; Open Translator is at far right.
- Twenty-second shared deadline, cancellation/replacement and stale UI/History/credit protection.
- Output-limit detection and explicit Groq GPT-OSS completion budget with low reasoning.

## Measured evidence

| Check | Result |
|---|---|
| Full local suite | 1946 passed, one intentional clipboard skip; 1947 collected; 113.77 s. |
| Native UI | Word/ruby/selection/link offsets, cache, resize, expansion, timeout and reversed completions checked on a private desktop. |
| Mutation checks | Protocol/hover/cache guards, seven cancellation faults and the word-wrap regression caught; source restored before final smoke/build. |
| User acceptance | Final word-wrap EXE accepted for release. |
| Packaging | Dictionary/four codecs present; all 69 packaged project modules/entry point match source. |
| Groq baseline | Same long source/prompt: length at 3072 completion tokens, including 3070 reasoning; final content empty. |
| Higher output comparison | One explicit-65536 call received 429 at the account's 8000 TPM quota; no retry or full-document success. |

Synthetic English single-paragraph popup timing, eight samples/mode after warmup:

| Source characters | Character wrap | Word wrap |
|---|---|---|
| 1000 | 147.89 ms | 150.81 ms |
| 6000 | 385.49 ms | 416.02 ms |
| 20000 | 2720.12 ms | 2831.05 ms |

These are local show/layout measurements, not API latency or universal bounds.
The long-paragraph baseline was already costly; ordinary word wrapping adds no
API tokens/requests or changes to canonical text. Over-wide tokens can still break.

## Limits retained

The initial expanded prototype had 21/48 API failures and ten successful paired
comparisons with median ratios 1.505x latency and 2.013x completion tokens; mostly
short/medium samples. A literal-JSON escaping issue was observed. This is not proof
of provider-wide quality; code/JSON-like input retains ordinary translation.
The 6000-source-character/120-unit gates apply only to structured links, not input
truncation. Legacy maps are approximate; unsupported structures have no links.
No successful complete 39-paragraph or low-reasoning live comparison was obtained.
Client cancellation cannot guarantee the provider stopped generating/billing.

Decisions 36-42 and [DEFERRED D22](../DEFERRED.md#d22---broader-linked-reading-and-long-document-validation)
retain the acceptance boundary. Raw probes, private inputs, timings and native
captures remain in ignored local logs; they are not release assets or test fixtures.
