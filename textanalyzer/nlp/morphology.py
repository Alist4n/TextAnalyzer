"""Морфологическая статистика по тексту."""

from __future__ import annotations

import re
from collections import Counter
from functools import lru_cache
from typing import Iterable, Sequence

from spacy.tokens import Token

from .labels import FEAT_VALUES_RU, school_pos

CONTENT_POS = {"NOUN", "PROPN", "VERB", "ADJ", "ADV"}
CYRILLIC_WORD = re.compile(r"^[а-яё]+(?:-[а-яё]+)*$", re.IGNORECASE)

# (название в отчёте, UD-признак, части речи, по которым считаем)
FEATURE_GROUPS = [
    ("Падеж", "Case", {"NOUN", "PROPN", "PRON", "ADJ", "DET", "NUM"}),
    ("Число (сущ.)", "Number", {"NOUN", "PROPN"}),
    ("Род (сущ.)", "Gender", {"NOUN", "PROPN"}),
    ("Одушевлённость", "Animacy", {"NOUN", "PROPN"}),
    ("Вид глагола", "Aspect", {"VERB"}),
    ("Время глагола", "Tense", {"VERB", "AUX"}),
    ("Наклонение", "Mood", {"VERB", "AUX"}),
    ("Лицо", "Person", {"VERB", "AUX", "PRON"}),
    ("Форма глагола", "VerbForm", {"VERB"}),
    ("Залог", "Voice", {"VERB"}),
    ("Степень сравнения", "Degree", {"ADJ", "ADV"}),
]

TOP_POS = {
    "all": None,
    "NOUN": {"NOUN"},
    "VERB": {"VERB"},
    "ADJ": {"ADJ"},
    "ADV": {"ADV"},
    "PROPN": {"PROPN"},
}


def display_lemma(tok: Token) -> str:
    lemma = tok.lemma_ or tok.text
    if tok.pos_ == "PROPN":
        return lemma[:1].upper() + lemma[1:]
    return lemma.lower()


def pos_distribution(words: Sequence[Token]) -> dict[str, int]:
    counts = Counter(school_pos(t.pos_, t.morph.to_dict()) for t in words)
    return dict(counts.most_common())


def feature_distributions(words: Sequence[Token]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for title, feat, pos_set in FEATURE_GROUPS:
        counts: Counter[str] = Counter()
        for t in words:
            if t.pos_ not in pos_set:
                continue
            values = t.morph.get(feat)
            if values:
                counts[FEAT_VALUES_RU.get(feat, {}).get(values[0], values[0])] += 1
        if counts:
            result[title] = dict(counts.most_common())
    return result


def top_lemmas(words: Sequence[Token], n: int) -> dict[str, list[tuple[str, int]]]:
    result = {}
    for key, pos_set in TOP_POS.items():
        counts = Counter(
            display_lemma(t)
            for t in words
            if t.pos_ in (pos_set or CONTENT_POS) and not t.is_stop
        )
        if counts:
            result[key] = counts.most_common(n)
    return result


# UD-часть речи -> допустимые части речи OpenCorpora (pymorphy3)
UD_TO_OC = {
    "NOUN": {"NOUN"},
    "PROPN": {"NOUN"},
    "ADJ": {"ADJF", "ADJS", "COMP", "PRTF", "PRTS"},
    # причастие, которое в словаре записано как прилагательное («мятая» -> «мятый»)
    "VERB": {"VERB", "INFN", "PRTF", "PRTS", "GRND", "ADJF", "ADJS"},
    "AUX": {"VERB", "INFN"},
    "ADV": {"ADVB", "PRED", "COMP"},
    "PRON": {"NPRO"},
    "DET": {"ADJF", "NPRO"},
    "NUM": {"NUMR", "ADJF"},
}
UD_CASE_TO_OC = {
    "Nom": {"nomn"},
    "Gen": {"gent", "gen2"},
    "Dat": {"datv"},
    "Acc": {"accs", "acc2"},
    "Ins": {"ablt"},
    "Loc": {"loct", "loc2"},
    "Par": {"gen2"},
    "Voc": {"voct"},
}
NAME_TAGS = {"Name", "Surn", "Patr", "Geox", "Orgn"}


def _restore_case(word: str, like: str) -> str:
    return word[:1].upper() + word[1:] if like[:1].isupper() else word


class MorphExtras:
    """Сведения pymorphy3: исправление лемм, нормализация имён, словарность, омонимия."""

    def __init__(self) -> None:
        import pymorphy3

        self.morph = pymorphy3.MorphAnalyzer()
        self._parse = lru_cache(maxsize=200_000)(self.morph.parse)
        self._known = lru_cache(maxsize=100_000)(self.morph.word_is_known)
        self._n_parses = lru_cache(maxsize=100_000)(self._count_parses)

    def _count_parses(self, word: str) -> int:
        return len({(p.normal_form, p.tag.POS) for p in self._parse(word)})

    def _best_parse(self, tok: Token, prefer_names: bool = False):
        """Разбор pymorphy3, согласованный с частью речи и падежом, выбранными моделью spaCy."""
        allowed = UD_TO_OC.get(tok.pos_)
        parses = [p for p in self._parse(tok.lower_) if allowed is None or p.tag.POS in allowed]
        if not parses:
            return None
        case = tok.morph.get("Case")
        if case and case[0] in UD_CASE_TO_OC:
            same_case = [p for p in parses if p.tag.case in UD_CASE_TO_OC[case[0]]]
            parses = same_case or parses
        if prefer_names:
            named = [p for p in parses if NAME_TAGS & set(p.tag.grammemes)]
            parses = named or parses
        return parses[0]

    def is_imperative(self, tok: Token) -> bool:
        """Повелительное наклонение по pymorphy3 — страховка, когда тэггер spaCy ошибся
        («Приходи завтра!» в начале предложения он размечает как существительное)."""
        if tok.morph.get("Mood"):
            return tok.morph.get("Mood") == ["Imp"]
        parses = self._parse(tok.lower_)
        return bool(parses) and parses[0].tag.POS == "VERB" and parses[0].tag.mood == "impr"

    def fix_lemmas(self, docs: Iterable) -> None:
        """Лемматизатор spaCy при расхождении тегов возвращает словоформу как есть — подставляем лемму pymorphy3."""
        for doc in docs:
            for tok in doc:
                w = tok.lower_
                if tok.lemma_.lower() != w or tok.pos_ not in UD_TO_OC or not CYRILLIC_WORD.match(w):
                    continue
                p = self._best_parse(tok)
                if p is None and self._known(w):
                    # тэггер ошибся с частью речи («мятая» как существительное), а слово словарное —
                    # берём самый вероятный разбор pymorphy3
                    p = self._parse(w)[0]
                if p is not None and p.normal_form != w:
                    tok.lemma_ = p.normal_form

    def normalize_entity(self, ent) -> str:
        """Имя сущности в именительном падеже: «Ирине Соколовой» -> «Ирина Соколова»."""
        root = ent.root
        if ent.label_ == "PER":
            to_inflect = set(range(ent.start, ent.end))
        else:
            to_inflect = {root.i} | {c.i for c in root.children if c.dep_ == "amod" and ent.start <= c.i < ent.end}
        words = []
        for t in ent:
            text = t.text
            if t.i in to_inflect and not (text.isupper() and len(text) > 1) and t.morph.get("Case") != ["Nom"]:
                p = self._best_parse(t, prefer_names=True)
                inflected = p.inflect({"nomn"}) if p is not None else None
                if inflected is not None:
                    text = _restore_case(inflected.word, t.text)
            words.append(text)
        return " ".join(words)

    def analyze(self, words: Sequence[Token], n: int) -> tuple[list[tuple[str, int]], float]:
        unknown: Counter[str] = Counter()
        ambiguous = total = 0
        for t in words:
            w = t.lower_
            if not CYRILLIC_WORD.match(w) or t.pos_ == "PROPN" or t.ent_type_:
                continue
            total += 1
            if not self._known(w):
                unknown[w] += 1
            elif self._n_parses(w) > 1:
                ambiguous += 1
        rate = ambiguous / total if total else 0.0
        return unknown.most_common(n), rate
