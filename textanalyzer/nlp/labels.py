"""Перевод разметки Universal Dependencies на русскую лингвистическую терминологию."""

from __future__ import annotations

from typing import Mapping

POS_RU = {
    "NOUN": "существительное",
    "PROPN": "имя собственное",
    "VERB": "глагол",
    "AUX": "вспомогательный глагол",
    "ADJ": "прилагательное",
    "ADV": "наречие",
    "PRON": "местоимение",
    "DET": "местоимение-прилагательное",
    "NUM": "числительное",
    "ADP": "предлог",
    "CCONJ": "сочинительный союз",
    "SCONJ": "подчинительный союз",
    "PART": "частица",
    "INTJ": "междометие",
    "PUNCT": "знак препинания",
    "SYM": "символ",
    "X": "другое",
    "SPACE": "пробел",
}

# Части речи школьной грамматики, которых нет в UD как отдельных тегов.
SCHOOL_POS_RU = {
    "PART_VERB": "причастие",
    "CONV": "деепричастие",
    "INF": "инфинитив",
    "ADJ_SHORT": "краткое прилагательное",
    "PART_SHORT": "краткое причастие",
}

POS_SHORT_RU = {
    "существительное": "сущ.",
    "имя собственное": "имя собств.",
    "глагол": "гл.",
    "вспомогательный глагол": "всп. гл.",
    "прилагательное": "прил.",
    "краткое прилагательное": "кр. прил.",
    "наречие": "нар.",
    "местоимение": "мест.",
    "местоимение-прилагательное": "мест.-прил.",
    "числительное": "числ.",
    "предлог": "предл.",
    "сочинительный союз": "союз",
    "подчинительный союз": "союз",
    "частица": "част.",
    "междометие": "межд.",
    "причастие": "прич.",
    "краткое причастие": "кр. прич.",
    "деепричастие": "дееприч.",
    "инфинитив": "инф.",
    "знак препинания": "",
    "символ": "симв.",
    "другое": "",
}

FEAT_NAMES_RU = {
    "Case": "падеж",
    "Gender": "род",
    "Number": "число",
    "Animacy": "одушевлённость",
    "Aspect": "вид",
    "Tense": "время",
    "Mood": "наклонение",
    "Person": "лицо",
    "VerbForm": "форма глагола",
    "Voice": "залог",
    "Degree": "степень сравнения",
    "Variant": "форма",
    "StyleVariant": "форма",
    "Polarity": "полярность",
    "Foreign": "иноязычное",
    "Abbr": "сокращение",
}

FEAT_VALUES_RU = {
    "Case": {
        "Nom": "именительный",
        "Gen": "родительный",
        "Dat": "дательный",
        "Acc": "винительный",
        "Ins": "творительный",
        "Loc": "предложный",
        "Par": "партитив",
        "Voc": "звательный",
    },
    "Gender": {"Masc": "мужской", "Fem": "женский", "Neut": "средний"},
    "Number": {"Sing": "единственное", "Plur": "множественное"},
    "Animacy": {"Anim": "одушевлённое", "Inan": "неодушевлённое"},
    "Aspect": {"Perf": "совершенный", "Imp": "несовершенный"},
    "Tense": {"Past": "прошедшее", "Pres": "настоящее", "Fut": "будущее"},
    "Mood": {"Ind": "изъявительное", "Imp": "повелительное", "Cnd": "условное"},
    "Person": {"1": "1-е", "2": "2-е", "3": "3-е", "First": "1-е", "Second": "2-е", "Third": "3-е"},
    "VerbForm": {
        "Fin": "личная",
        "Inf": "инфинитив",
        "Part": "причастие",
        "Conv": "деепричастие",
    },
    "Voice": {"Act": "действительный", "Pass": "страдательный", "Mid": "возвратный"},
    "Degree": {"Pos": "положительная", "Cmp": "сравнительная", "Sup": "превосходная"},
    "Variant": {"Short": "краткая", "Long": "полная"},
    "StyleVariant": {"Short": "краткая", "Long": "полная"},
    "Polarity": {"Neg": "отрицательная", "Pos": "утвердительная"},
    "Foreign": {"Yes": "да"},
    "Abbr": {"Yes": "да"},
}

# Порядок вывода признаков в разборе.
FEAT_ORDER = [
    "VerbForm", "Mood", "Aspect", "Tense", "Voice", "Person",
    "Gender", "Number", "Case", "Animacy", "Degree", "Variant", "StyleVariant", "Polarity",
    "Abbr", "Foreign",
]

DEP_RU = {
    "root": "корень (сказуемое)",
    "nsubj": "подлежащее",
    "nsubj:pass": "подлежащее при страдательном залоге",
    "csubj": "подлежащее-придаточное",
    "csubj:pass": "подлежащее-придаточное (страд.)",
    "obj": "прямое дополнение",
    "iobj": "косвенное дополнение",
    "obl": "косвенное дополнение / обстоятельство",
    "obl:agent": "агенс при страдательном залоге",
    "obl:tmod": "обстоятельство времени",
    "advmod": "обстоятельство (наречие)",
    "advcl": "обстоятельственное придаточное / деепричастный оборот",
    "amod": "согласованное определение",
    "nmod": "несогласованное определение",
    "nummod": "количественный модификатор",
    "nummod:gov": "количественный модификатор (управляющий)",
    "nummod:entity": "числовой модификатор",
    "det": "определение (местоимение)",
    "appos": "приложение",
    "acl": "причастный оборот / определительная конструкция",
    "acl:relcl": "определительное придаточное",
    "ccomp": "изъяснительное придаточное",
    "xcomp": "часть составного сказуемого / инфинитив",
    "conj": "однородный член / сочинённая часть",
    "cc": "сочинительный союз",
    "mark": "подчинительный союз",
    "case": "предлог",
    "cop": "связка",
    "aux": "вспомогательный глагол",
    "aux:pass": "вспомогательный глагол (страд.)",
    "punct": "пунктуация",
    "parataxis": "бессоюзная связь / вводная конструкция",
    "discourse": "дискурсивный элемент (частица, вводное)",
    "vocative": "обращение",
    "fixed": "устойчивое сочетание",
    "flat": "неделимое наименование",
    "flat:name": "имя (ФИО)",
    "flat:foreign": "иноязычное наименование",
    "compound": "сложное слово",
    "expl": "формальный элемент",
    "orphan": "эллипсис",
    "list": "перечень",
    "dislocated": "вынесенный элемент",
    "goeswith": "часть разорванного слова",
    "reparandum": "оговорка",
    "dep": "неопределённая связь",
}

DEP_SHORT_RU = {
    "root": "",
    "nsubj": "подл",
    "nsubj:pass": "подл",
    "csubj": "подл-прид",
    "obj": "доп",
    "iobj": "к.доп",
    "obl": "обл",
    "obl:agent": "агенс",
    "advmod": "обст",
    "advcl": "обст-прид",
    "amod": "опр",
    "nmod": "н.опр",
    "nummod": "числ",
    "nummod:gov": "числ",
    "det": "опр",
    "appos": "прил",
    "acl": "опр-об",
    "acl:relcl": "опр-прид",
    "ccomp": "изъясн",
    "xcomp": "сост",
    "conj": "одн",
    "cc": "союз",
    "mark": "союз",
    "case": "предл",
    "cop": "связка",
    "aux": "всп",
    "aux:pass": "всп",
    "parataxis": "бессоюз",
    "discourse": "дискурс",
    "vocative": "обращ",
    "fixed": "фикс",
    "flat": "имя",
    "flat:name": "имя",
    "flat:foreign": "имя",
}

# Члены предложения (школьная грамматика) — приближение по UD-связям.
MEMBER_BY_DEP = {
    "nsubj": "подлежащее",
    "nsubj:pass": "подлежащее",
    "csubj": "подлежащее",
    "root": "сказуемое",
    "cop": "сказуемое",
    "aux": "сказуемое",
    "aux:pass": "сказуемое",
    "obj": "дополнение",
    "iobj": "дополнение",
    "obl:agent": "дополнение",
    "obl": "обстоятельство / дополнение",
    "obl:tmod": "обстоятельство",
    "advmod": "обстоятельство",
    "advcl": "обстоятельство",
    "amod": "определение",
    "det": "определение",
    "nmod": "определение",
    "acl": "определение",
    "appos": "приложение",
    "nummod": "определение",
    "nummod:gov": "определение",
    "vocative": "обращение",
}

ENTITY_RU = {
    "PER": "персона",
    "LOC": "место",
    "ORG": "организация",
}


def dep_ru(dep: str) -> str:
    if dep in DEP_RU:
        return DEP_RU[dep]
    base = dep.split(":", 1)[0]
    return DEP_RU.get(base, dep)


def dep_short_ru(dep: str) -> str:
    if dep in DEP_SHORT_RU:
        return DEP_SHORT_RU[dep]
    base = dep.split(":", 1)[0]
    return DEP_SHORT_RU.get(base, base)


def feats_ru(feats: Mapping[str, str]) -> str:
    """'Case=Gen|Number=Sing' -> 'падеж: родительный, число: единственное'."""
    parts = []
    ordered = [k for k in FEAT_ORDER if k in feats] + [k for k in feats if k not in FEAT_ORDER]
    for key in ordered:
        value = feats[key]
        name = FEAT_NAMES_RU.get(key, key)
        value_ru = FEAT_VALUES_RU.get(key, {}).get(value, value)
        parts.append(f"{name}: {value_ru}")
    return ", ".join(parts)


def school_pos(pos: str, feats: Mapping[str, str]) -> str:
    """Часть речи в терминах школьной грамматики (причастие и деепричастие — отдельно)."""
    verb_form = feats.get("VerbForm")
    short = "Short" in (feats.get("Variant"), feats.get("StyleVariant"))
    if pos in ("VERB", "AUX", "ADJ"):
        if verb_form == "Part":
            return SCHOOL_POS_RU["PART_SHORT"] if short else SCHOOL_POS_RU["PART_VERB"]
        if verb_form == "Conv":
            return SCHOOL_POS_RU["CONV"]
    if pos in ("VERB", "AUX") and verb_form == "Inf":
        return SCHOOL_POS_RU["INF"]
    if pos == "ADJ" and short:
        return SCHOOL_POS_RU["ADJ_SHORT"]
    return POS_RU.get(pos, pos)


def pos_short_ru(pos_ru: str) -> str:
    return POS_SHORT_RU.get(pos_ru, pos_ru)
