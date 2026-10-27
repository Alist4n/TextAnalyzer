"""Структуры результатов анализа. Все сериализуются в JSON через to_dict()."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class TokenInfo:
    i: int                  # индекс внутри предложения
    text: str
    lemma: str
    pos: str                # UD-тег
    pos_ru: str             # часть речи по-русски (школьная грамматика)
    feats: dict[str, str]
    feats_ru: str
    dep: str
    dep_ru: str
    head: int               # индекс вершины внутри предложения (у корня — свой)
    member: str             # член предложения (приближённо)
    is_punct: bool
    space_after: bool
    is_stop: bool = False   # служебное/частое слово (для частотных словарей)


@dataclass
class LexiconHit:
    token: str
    lemma: str
    emotion: str
    weight: float           # итоговый вклад с учётом усилителей; 0 при отрицании
    negated: bool = False
    modifier: str = ""      # слово-усилитель/ослабитель
    token_i: int = -1       # индекс токена в предложении


@dataclass
class SentenceInfo:
    index: int
    text: str
    n_words: int
    tokens: list[TokenInfo] = field(default_factory=list)
    # синтаксис: грамматические основы [подлежащее, сказуемое] по частям предложения
    bases: list[list[str]] = field(default_factory=list)
    purpose: str = ""           # повествовательное / вопросительное / побудительное
    exclamatory: bool = False
    structure: str = ""         # простое / сложносочинённое / сложноподчинённое / ...
    composition: str = ""       # двусоставное / односоставное
    n_clauses: int = 0
    depth: int = 0
    mean_dep_distance: float = 0.0
    participial: list[str] = field(default_factory=list)
    adverbial: list[str] = field(default_factory=list)
    homogeneous: list[list[str]] = field(default_factory=list)
    # эмоции
    emotion: dict[str, float] | None = None     # вероятности модели
    emotion_dominant: str | None = None
    lexicon_hits: list[LexiconHit] = field(default_factory=list)


@dataclass
class TextStats:
    n_chars: int = 0
    n_chars_no_spaces: int = 0
    n_words: int = 0
    n_sentences: int = 0
    n_paragraphs: int = 0
    n_unique_lemmas: int = 0
    avg_sentence_len: float = 0.0       # слов
    avg_word_len: float = 0.0           # букв
    avg_syllables: float = 0.0          # слогов на слово
    ttr: float = 0.0                    # уникальные леммы / слова
    mattr: float = 0.0                  # скользящий TTR (окно 50)
    hapax_ratio: float = 0.0            # доля лемм, встретившихся один раз
    lexical_density: float = 0.0        # доля знаменательных слов


@dataclass
class EntityInfo:
    text: str
    label: str
    label_ru: str
    count: int


@dataclass
class EmotionSummary:
    method: str
    # средневзвешенные вероятности модели по тексту
    profile: dict[str, float] | None = None
    dominant: str | None = None          # с учётом «нейтрально»
    leading_emotion: str | None = None   # самая сильная из собственно эмоций
    # доля предложений, где эмоция доминирует
    sentence_share: dict[str, float] | None = None
    # словарь: сумма весов по эмоциям и плотность на 100 слов
    lexicon_totals: dict[str, float] | None = None
    lexicon_density: dict[str, float] | None = None
    lexicon_dominant: str | None = None
    lexicon_top: dict[str, list[tuple[str, int]]] | None = None
    lexicon_negated: list[tuple[str, int]] | None = None


@dataclass
class TextResult:
    name: str
    source: str | None
    text: str
    stats: TextStats
    sentences: list[SentenceInfo]
    pos_distribution: dict[str, int] = field(default_factory=dict)
    feature_distributions: dict[str, dict[str, int]] = field(default_factory=dict)
    top_lemmas: dict[str, list[tuple[str, int]]] = field(default_factory=dict)
    unknown_words: list[tuple[str, int]] = field(default_factory=list)
    ambiguity_rate: float = 0.0
    dep_distribution: dict[str, int] = field(default_factory=dict)
    purpose_distribution: dict[str, int] = field(default_factory=dict)
    structure_distribution: dict[str, int] = field(default_factory=dict)
    syntax_summary: dict[str, float] = field(default_factory=dict)
    entities: list[EntityInfo] = field(default_factory=list)
    emotions: EmotionSummary | None = None
    elapsed: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CorpusResult:
    texts: list[TextResult]
    options: dict
    created: str
    app_version: str
    models: dict[str, str] = field(default_factory=dict)
    elapsed: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)
