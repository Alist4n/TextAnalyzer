"""Общее для HTML- и DOCX-отчётов: цвета эмоций, сглаживание рядов, сводка по набору текстов."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Sequence

from ..nlp.emotions import EMOTIONS, NEUTRAL
from ..nlp.models import CorpusResult

EMOTION_COLORS = {
    "joy": "#E8A500",
    "sadness": "#3B6FB6",
    "surprise": "#8E5BC4",
    "fear": "#2E8B57",
    "anger": "#D64541",
    NEUTRAL: "#9AA0A6",
}
ACCENT = "#4A6FA5"
CONTENT_POS = {"NOUN", "PROPN", "VERB", "ADJ", "ADV"}


def rolling(values: Sequence[float], window: int) -> list[float]:
    """Скользящее среднее; в начале ряда — по имеющимся значениям."""
    if window <= 1:
        return list(values)
    out, acc = [], 0.0
    for i, v in enumerate(values):
        acc += v
        if i >= window:
            acc -= values[i - window]
        out.append(acc / min(i + 1, window))
    return out


def dynamics_window(n_sentences: int) -> int:
    return max(1, min(7, n_sentences // 15))


@dataclass
class CorpusOverview:
    """Сводка «все тексты вместе» для отчётов по нескольким текстам."""
    n_texts: int = 0
    n_words: int = 0
    n_sentences: int = 0
    avg_words: float = 0.0
    # сколько текстов с какой ведущей эмоцией («нейтрально» — эмоции почти нет)
    leading_counts: dict[str, int] = field(default_factory=dict)
    leading_source: str = ""                       # «модель» или «словарь»
    profile: dict[str, float] | None = None        # средний профиль, взвешенный по числу слов
    lexicon_totals: dict[str, float] | None = None
    lexicon_top: dict[str, list[tuple[str, int]]] = field(default_factory=dict)
    pos_distribution: dict[str, int] = field(default_factory=dict)
    top_lemmas: list[tuple[str, int]] = field(default_factory=list)


def corpus_overview(corpus: CorpusResult, top_n: int = 20) -> CorpusOverview:
    texts = corpus.texts
    ov = CorpusOverview(n_texts=len(texts))
    if not texts:
        return ov
    ov.n_words = sum(t.stats.n_words for t in texts)
    ov.n_sentences = sum(t.stats.n_sentences for t in texts)
    ov.avg_words = round(ov.n_words / len(texts), 1)

    with_profile = [t for t in texts if t.emotions and t.emotions.profile]
    if with_profile:
        ov.leading_source = "модель"
        ov.leading_counts = dict(Counter(t.emotions.leading_emotion or NEUTRAL for t in with_profile).most_common())
        weights = [max(1, t.stats.n_words) for t in with_profile]
        labels = list(with_profile[0].emotions.profile)
        ov.profile = {
            lab: round(sum(t.emotions.profile[lab] * w for t, w in zip(with_profile, weights)) / sum(weights), 4)
            for lab in labels
        }

    with_lexicon = [t for t in texts if t.emotions and t.emotions.lexicon_totals is not None]
    if with_lexicon:
        totals = Counter()
        tops = {e: Counter() for e in EMOTIONS}
        for t in with_lexicon:
            totals.update(t.emotions.lexicon_totals)
            for e, words in (t.emotions.lexicon_top or {}).items():
                tops[e].update(dict(words))
        ov.lexicon_totals = {e: round(totals.get(e, 0.0), 3) for e in EMOTIONS}
        ov.lexicon_top = {e: c.most_common(top_n) for e, c in tops.items() if c}
        if not with_profile:
            ov.leading_source = "словарь"
            ov.leading_counts = dict(
                Counter(t.emotions.lexicon_dominant or NEUTRAL for t in with_lexicon).most_common()
            )

    pos = Counter()
    lemmas = Counter()
    for t in texts:
        pos.update(t.pos_distribution)
        for s in t.sentences:
            for tok in s.tokens:
                if tok.pos in CONTENT_POS and not tok.is_punct and not tok.is_stop:
                    lemmas[tok.lemma] += 1
    ov.pos_distribution = dict(pos.most_common())
    ov.top_lemmas = lemmas.most_common(top_n)
    return ov
