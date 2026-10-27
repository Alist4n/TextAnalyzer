"""Общая статистика текста: объём, средние длины, разнообразие лексики."""

from __future__ import annotations

import re
from collections import Counter
from typing import Sequence

from .models import TextStats

VOWELS = set("аеёиоуыэюяaeiouy")
CONTENT_POS = {"NOUN", "PROPN", "VERB", "ADJ", "ADV"}


def syllables(word: str) -> int:
    return max(1, sum(ch in VOWELS for ch in word.lower()))


def mattr(items: Sequence[str], window: int = 50) -> float:
    """Moving-Average Type-Token Ratio: не зависит от длины текста, в отличие от TTR."""
    if not items:
        return 0.0
    if len(items) <= window:
        return len(set(items)) / len(items)
    counts = Counter(items[:window])
    total = len(counts) / window
    for i in range(window, len(items)):
        out, inc = items[i - window], items[i]
        counts[out] -= 1
        if counts[out] == 0:
            del counts[out]
        counts[inc] += 1
        total += len(counts) / window
    return total / (len(items) - window + 1)


def count_paragraphs(text: str) -> int:
    blocks = [b for b in re.split(r"\n\s*\n", text) if b.strip()]
    if len(blocks) > 1:
        return len(blocks)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return max(1, len(lines)) if text.strip() else 0


def compute_stats(text: str, n_sentences: int, words, lemmas: Sequence[str]) -> TextStats:
    """words — токены spaCy без пунктуации, lemmas — их леммы."""
    n_words = len(words)
    stats = TextStats(
        n_chars=len(text),
        n_chars_no_spaces=sum(not ch.isspace() for ch in text),
        n_words=n_words,
        n_sentences=n_sentences,
        n_paragraphs=count_paragraphs(text),
    )
    if not n_words:
        return stats

    letters = [sum(ch.isalpha() for ch in t.text) for t in words]
    syl = [syllables(t.text) for t in words]
    lemma_counts = Counter(lemmas)

    stats.n_unique_lemmas = len(lemma_counts)
    stats.avg_sentence_len = round(n_words / max(1, n_sentences), 2)
    stats.avg_word_len = round(sum(letters) / n_words, 2)
    stats.avg_syllables = round(sum(syl) / n_words, 3)
    stats.ttr = round(len(lemma_counts) / n_words, 3)
    stats.mattr = round(mattr(list(lemmas)), 3)
    stats.hapax_ratio = round(sum(1 for c in lemma_counts.values() if c == 1) / len(lemma_counts), 3)
    stats.lexical_density = round(sum(1 for t in words if t.pos_ in CONTENT_POS) / n_words, 3)
    return stats
