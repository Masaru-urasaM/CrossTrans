"""Measure the Japanese-vs-Chinese evidence and the reading providers on real text (manual).

No API calls and no config writes: it reads public sentence lists and the app's own
code. Two measurements, each the record behind a decision:

    python tools/measure_cjk_evidence.py evidence
    python tools/measure_cjk_evidence.py readings --sample 3000

`evidence` (K6, Decision 30): how many Chinese sentences the app cannot place by
their glyphs, how many `lang_id.grammar_evidence()` settles, and whether it ever
calls Japanese text Chinese - on Tatoeba's Japanese sentences, on every all-kanji
word of pykakasi's dictionary (as a term, as a one-word sentence, in lists), and on
a stress set of two such words that each hold a listed character.

`readings` (K1, DEFERRED D19): how often pykakasi - the one reading provider a fresh
install has - reads a word differently from fugashi + UniDic (the Japanese NLP
pack), on a fixed random sample of Tatoeba's Japanese sentences. Needs fugashi.

Data: Tatoeba's per-language sentence exports (CC-BY 2.0 FR,
https://tatoeba.org), downloaded once into logs/eval/tatoeba/ (git-ignored) and
parsed as text. Results: logs/eval/cjk_<mode>.json.
"""
import argparse
import bz2
import collections
import json
import os
import random
import sys
import urllib.request
from typing import Callable, Dict, Iterable, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import src.core  # noqa: E402,F401  (must precede `config`: see project CLAUDE.md)
from src.core import lang_id  # noqa: E402
from src.core.source_marker import cjk_dominant  # noqa: E402

EVAL_DIR = os.path.join(ROOT, 'logs', 'eval')
TATOEBA_DIR = os.path.join(EVAL_DIR, 'tatoeba')
TATOEBA_URL = 'https://downloads.tatoeba.org/exports/per_language/{lang}/{lang}_sentences.tsv.bz2'
SEED = 20261016
STRESS_SEED = 7


def tatoeba(lang: str) -> List[str]:
    """Every sentence of one language's Tatoeba export, downloading it once."""
    path = os.path.join(TATOEBA_DIR, f'{lang}_sentences.tsv.bz2')
    if not os.path.exists(path):
        os.makedirs(TATOEBA_DIR, exist_ok=True)
        print(f"downloading {TATOEBA_URL.format(lang=lang)}")
        urllib.request.urlretrieve(TATOEBA_URL.format(lang=lang), path)
    sentences = []
    with bz2.open(path, 'rt', encoding='utf-8') as fh:
        for line in fh:
            parts = line.rstrip('\n').split('\t')
            if len(parts) >= 3:
                sentences.append(parts[2])
    return sentences


def kanji_words() -> List[str]:
    """Every all-kanji entry of 2+ characters in pykakasi's dictionary (SKK-JISYO)."""
    from pykakasi.kanji import Kanwa
    return sorted({word for table in Kanwa()._jisyo_table.values() for word in table
                   if len(word) >= 2 and all(lang_id.HAN_RE.match(ch) for ch in word)})


def open_by_glyphs(text: str) -> bool:
    """What the app asked about before K6: mostly CJK, no kana, no glyph evidence."""
    return (cjk_dominant(text) and not lang_id.has_kana(text)
            and lang_id.han_evidence(text) is None)


def chinese_by_grammar(text: str) -> bool:
    verdict = lang_id.text_evidence(text)
    return verdict is not None and verdict.evidence == 'zh-grammar'


def japanese_sets(japanese_sentences: Iterable[str], words: Iterable[str]) -> Dict[str, List[str]]:
    """The Japanese texts a Chinese rule must leave alone (see the module docstring)."""
    open_words = [w for w in words if open_by_glyphs(w)]
    rng = random.Random(SEED)
    lists: List[str] = []
    if len(open_words) >= 2:
        pairs = min(5000, len(open_words))
        lists = [f'{a}，{b}。' for a, b in zip(rng.sample(open_words, pairs),
                                              rng.sample(open_words, pairs))]
        lists += [f'{a}、{b}。' for a, b in zip(rng.sample(open_words, pairs),
                                               rng.sample(open_words, pairs))]
    listed = lang_id.CHINESE_FUNCTION_CHARS | set('我的了')
    holders = [w for w in open_words if set(w) & listed]
    stress_rng = random.Random(STRESS_SEED)
    stress = [a + b + '。' for a, b in zip(stress_rng.choices(holders, k=20000),
                                          stress_rng.choices(holders, k=20000))] if holders else []
    return {
        'tatoeba sentences': [t for t in japanese_sentences if open_by_glyphs(t)],
        'dictionary words': open_words,
        'one-word sentences': [w + '。' for w in open_words],
        'lists': lists,
        'stress compounds': stress,
    }


def measure_evidence(chinese: Iterable[str], japanese: Dict[str, List[str]],
                     rule: Callable[[str], bool] = chinese_by_grammar) -> dict:
    """Chinese sentences settled by `rule`, and the Japanese texts it calls Chinese."""
    chinese_open = [t for t in chinese if open_by_glyphs(t)]
    settled = sum(1 for t in chinese_open if rule(t))
    report = {
        'chinese_open_by_glyphs': len(chinese_open),
        'chinese_settled': settled,
        'chinese_settled_share': round(settled / len(chinese_open), 4) if chinese_open else 0.0,
        'japanese_called_chinese': {},
    }
    for name, texts in japanese.items():
        called = [t for t in texts if rule(t)]
        report['japanese_called_chinese'][name] = {
            'count': len(called), 'of': len(texts), 'examples': called[:10]}
    return report


def reading_pairs(segments) -> Dict[tuple, str]:
    """{(offset, base): reading} for the segments that carry a reading."""
    pairs, pos = {}, 0
    for seg in segments:
        if seg.ruby:
            pairs[(pos, seg.base)] = seg.ruby
        pos += len(seg.base)
    return pairs


def measure_readings(sentences: List[str], sample: int) -> dict:
    """pykakasi alone vs fugashi first, on the same sentences."""
    from src.core import furigana as F
    if not F._FUGASHI.is_available():
        raise SystemExit("readings needs the Japanese NLP pack (fugashi + unidic-lite)")
    with_kanji = [t for t in sentences if F.has_kanji(t)]
    chosen = random.Random(SEED).sample(with_kanji, min(sample, len(with_kanji)))

    def annotate(providers, text):
        saved = F._PROVIDERS[:]
        F._PROVIDERS[:] = providers
        try:
            F.clear_cache()
            return F.annotate(text, lang_id.JAPANESE)
        finally:
            F._PROVIDERS[:] = saved

    differences = collections.Counter()
    examples = {}
    differing = 0
    for text in chosen:
        both = reading_pairs(annotate([F._FUGASHI, F._KAKASI], text))
        alone = reading_pairs(annotate([F._KAKASI], text))
        found = [(key[1], alone[key], both[key]) for key in alone
                 if key in both and alone[key] != both[key]]
        differing += bool(found)
        for item in found:
            differences[item] += 1
            examples.setdefault(item, text)
    return {
        'sample': len(chosen),
        'sentences_with_a_difference': differing,
        'distinct_differences': len(differences),
        'top': [{'word': w, 'pykakasi': k, 'fugashi': f, 'sentences': n,
                 'example': examples[(w, k, f)]}
                for (w, k, f), n in differences.most_common(40)],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('mode', choices=('evidence', 'readings'))
    parser.add_argument('--sample', type=int, default=3000,
                        help='readings: how many Japanese sentences (default 3000)')
    args = parser.parse_args(argv)

    if args.mode == 'evidence':
        report = measure_evidence(tatoeba('cmn'), japanese_sets(tatoeba('jpn'), kanji_words()))
        print(f"Chinese sentences open by glyphs: {report['chinese_open_by_glyphs']}, "
              f"settled by grammar: {report['chinese_settled']} "
              f"({100 * report['chinese_settled_share']:.1f}%)")
        for name, row in report['japanese_called_chinese'].items():
            print(f"Japanese {name} called Chinese: {row['count']}/{row['of']} {row['examples'][:4]}")
    else:
        report = measure_readings(tatoeba('jpn'), args.sample)
        print(f"{report['sentences_with_a_difference']} of {report['sample']} sentences read "
              f"differently; {report['distinct_differences']} distinct differences")
        for row in report['top'][:15]:
            print(f"  {row['sentences']:4d}  {row['word']}  pykakasi={row['pykakasi']}  "
                  f"fugashi={row['fugashi']}")

    os.makedirs(EVAL_DIR, exist_ok=True)
    out = os.path.join(EVAL_DIR, f'cjk_{args.mode}.json')
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    print(f"-> {out}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
