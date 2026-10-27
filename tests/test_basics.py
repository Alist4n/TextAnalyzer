"""Тесты без языковых моделей: переводы разметки и статистика."""

from textanalyzer.nlp import stats
from textanalyzer.nlp.labels import dep_ru, feats_ru, school_pos


def test_feats_ru_translates_spacy_values():
    s = feats_ru({"Person": "First", "Number": "Sing", "StyleVariant": "Short"})
    assert "лицо: 1-е" in s
    assert "число: единственное" in s
    assert "форма: краткая" in s


def test_school_pos():
    assert school_pos("VERB", {"VerbForm": "Part"}) == "причастие"
    assert school_pos("VERB", {"VerbForm": "Conv"}) == "деепричастие"
    assert school_pos("VERB", {"VerbForm": "Inf"}) == "инфинитив"
    assert school_pos("ADJ", {"StyleVariant": "Short"}) == "краткое прилагательное"
    assert school_pos("NOUN", {}) == "существительное"


def test_dep_ru_falls_back_to_base_label():
    assert dep_ru("nsubj") == "подлежащее"
    assert dep_ru("obl:unknownsubtype") == dep_ru("obl")


def test_syllables():
    assert stats.syllables("молоко") == 3
    assert stats.syllables("вс") == 1


def test_mattr_is_length_independent():
    short = ["a", "b", "c", "a"]
    assert stats.mattr(short) == 0.75
    repeated = ["a", "b"] * 200
    assert abs(stats.mattr(repeated, window=50) - 2 / 50) < 1e-9


def test_count_paragraphs():
    assert stats.count_paragraphs("Первый.\n\nВторой.\n\n\nТретий.") == 3
    assert stats.count_paragraphs("строка 1\nстрока 2") == 2
    assert stats.count_paragraphs("") == 0
