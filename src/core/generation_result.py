"""Do not mistake an output-limit response for a complete generation."""
import logging


class IncompleteGenerationError(Exception):
    """A response ended without returning a complete answer; never auto-retry."""


def check_generation_result(result):
    reason = None
    usage = result.get('usage') or result.get('usageMetadata') or {}
    if not isinstance(usage, dict):
        usage = {}
    if result.get('choices'):
        reason = result['choices'][0].get('finish_reason')
    elif result.get('candidates'):
        reason = result['candidates'][0].get('finishReason')
    elif 'stop_reason' in result:
        reason = result.get('stop_reason')
    counters = {key: value for key, value in usage.items()
                if key in ('prompt_tokens', 'completion_tokens', 'total_tokens',
                           'input_tokens', 'output_tokens', 'promptTokenCount',
                           'candidatesTokenCount', 'thoughtsTokenCount', 'totalTokenCount')
                and type(value) is int}
    details = usage.get('completion_tokens_details')
    if isinstance(details, dict) and type(details.get('reasoning_tokens')) is int:
        counters['reasoning_tokens'] = details['reasoning_tokens']
    logging.info('[Generation] finish_reason=%s usage=%s', reason or 'unspecified', counters)
    if str(reason).upper() in ('LENGTH', 'MAX_TOKENS', 'MAX_COMPLETION_TOKENS', 'MODEL_LENGTH'):
        raise IncompleteGenerationError(
            'Incomplete response: the model reached its output-token limit before finishing. '
            'Use a model with a larger output budget or translate smaller sections. '
            'No complete translation has been saved.')
    if str(reason).upper() in ('CONTENT_FILTER', 'SAFETY', 'RECITATION', 'BLOCKLIST',
                               'PROHIBITED_CONTENT', 'TOOL_CALLS', 'FUNCTION_CALL'):
        raise IncompleteGenerationError(
            f'Incomplete response: generation stopped with {reason}. No complete translation has been saved.')


def google_text(result):
    parts = result['candidates'][0]['content']['parts']
    text = ''.join(part.get('text', '') for part in parts if not part.get('thought'))
    if not text.strip():
        raise ValueError('No final text in Google response')
    return text.strip()


def anthropic_text(result):
    text = ''.join(block.get('text', '') for block in result['content']
                   if block.get('type', 'text') == 'text')
    if not text.strip():
        raise ValueError('No final text in Anthropic response')
    return text.strip()
