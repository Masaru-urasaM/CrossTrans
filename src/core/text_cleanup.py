"""
Cleanup applied to raw model output, before anyone reads it as an answer.
"""
import re

# DeepSeek-R1, Qwen3, gpt-oss and friends narrate their reasoning inside
# <think>...</think>. It is never part of the answer, and it is emitted by the
# model whether the request was text or vision.
_THINKING_RE = re.compile(r'<think>.*?</think>\s*', re.DOTALL | re.IGNORECASE)


def strip_thinking_tags(text: str) -> str:
    """Remove <think>...</think> blocks from a model response.

    Idempotent and safe on any string, so it can sit on a path that is already
    cleaned further up without changing the result.
    """
    if not text:
        return text

    return _THINKING_RE.sub('', text).strip()
