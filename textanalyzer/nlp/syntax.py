"""Синтаксический анализ предложения поверх UD-дерева зависимостей spaCy.

Члены предложения и тип сложного предложения выводятся эвристически:
грамматическая основа и границы частей определяются надёжно, второстепенные
члены — приближённо (в UD нет прямого соответствия школьной классификации).
"""

from __future__ import annotations

from collections import Counter
from typing import Callable, Iterable

from spacy.tokens import Span, Token

from .labels import MEMBER_BY_DEP

SUBJECT_DEPS = {"nsubj", "nsubj:pass", "csubj", "csubj:pass"}
SUBORDINATE_DEPS = {"ccomp", "advcl", "acl:relcl", "csubj", "csubj:pass"}
CLAUSE_DEPS = SUBORDINATE_DEPS | {"parataxis"}
PREDICATE_PARTS = {"aux", "aux:pass", "cop"}
NON_FINITE = {"Inf", "Part", "Conv"}
NEGATIONS = {"не", "ни"}
IMPERATIVE_STARTERS = {"давай", "давайте", "пусть", "пускай"}
FUNCTION_DEPS = {"case", "mark", "cc", "punct", "fixed", "discourse"}
FUNCTION_POS = {"PART", "INTJ", "CCONJ", "SCONJ", "ADP", "PUNCT"}
NOMINAL_POS = {"NOUN", "PROPN", "PRON", "NUM"}

# Совместимые части речи для однородных членов
POS_GROUP = {
    "NOUN": "noun", "PROPN": "noun", "PRON": "noun", "NUM": "noun",
    "VERB": "verb", "AUX": "verb",
    "ADJ": "adj", "DET": "adj",
    "ADV": "adv",
}


def is_root(tok: Token) -> bool:
    # spaCy создаёт объекты Token при каждом обращении, поэтому сравниваем индексы, а не `is`
    return tok.head.i == tok.i


def dep(tok: Token) -> str:
    """Связь в нижнем регистре: spaCy пишет корень как 'ROOT'."""
    return "root" if is_root(tok) or tok.dep_ == "ROOT" else tok.dep_.lower()


def verb_form(tok: Token) -> str | None:
    vf = tok.morph.get("VerbForm")
    return vf[0] if vf else None


def is_word(tok: Token) -> bool:
    return not (tok.is_punct or tok.is_space or tok.pos_ in ("PUNCT", "SYM", "SPACE")) and any(
        ch.isalnum() for ch in tok.text
    )


def has_subject(tok: Token) -> bool:
    return any(dep(c) in SUBJECT_DEPS for c in tok.children)


def pos_group(tok: Token) -> str:
    if verb_form(tok) == "Part":
        return "adj"  # причастие однородно с прилагательным
    return POS_GROUP.get(tok.pos_, tok.pos_)


def is_nominative_sentence_head(tok: Token) -> bool:
    """Назывное предложение («Ночь.», «Дорогая Аня!»): именной корень без подлежащего и связки."""
    return (
        dep(tok) == "root"
        and tok.pos_ in NOMINAL_POS
        and not has_subject(tok)
        and not any(dep(c) in PREDICATE_PARTS for c in tok.children)
    )


def word_count(tok: Token) -> int:
    return sum(1 for t in tok.subtree if is_word(t))


def is_clause_head(tok: Token) -> bool:
    """Является ли токен вершиной предикативной части (простого предложения в составе сложного)."""
    d = dep(tok)
    if d == "root":
        return True
    if d in CLAUSE_DEPS:
        if verb_form(tok) in NON_FINITE and not has_subject(tok):
            return False  # причастный/деепричастный оборот, инфинитив
        if d == "parataxis" and not has_subject(tok) and word_count(tok) < 3:
            return False  # вводное слово или сочетание: «кажется», «может быть»
        return True
    if d == "conj":
        # однородное сказуемое со своим подлежащим — отдельная часть сложносочинённого
        return is_clause_head(tok.head) and has_subject(tok) and verb_form(tok) not in NON_FINITE
    return False


def clause_link(tok: Token) -> str | None:
    """Тип связи части с главной: сочинительная / подчинительная / бессоюзная."""
    d = dep(tok)
    if d in SUBORDINATE_DEPS:
        return "подчинительная"
    if d == "conj":
        return "сочинительная" if any(dep(c) == "cc" for c in tok.children) else "бессоюзная"
    if d == "parataxis":
        return "бессоюзная"
    return None


def subtree_text(tok: Token) -> str:
    words = [t for t in tok.subtree if not (t.is_punct or t.is_space)]
    if not words:
        return tok.text
    doc = tok.doc
    return doc[words[0].i : words[-1].i + 1].text


def _phrase_text(tokens: Iterable[Token]) -> str:
    return " ".join(t.text for t in sorted(tokens, key=lambda t: t.i))


def subject_text(head: Token) -> str:
    subjects = [c for c in head.children if dep(c) in SUBJECT_DEPS]
    parts = []
    for s in subjects:
        group = [s]
        group += [c for c in s.children if dep(c) in ("flat", "flat:name", "fixed")]
        conj = [c for c in s.children if dep(c) == "conj" and pos_group(c) == pos_group(s)]
        if dep(s).startswith("csubj"):
            parts.append(subtree_text(s))
            continue
        parts.append(_phrase_text(group))
        parts.extend(_phrase_text([c] + [g for g in c.children if dep(g) in ("flat", "flat:name")]) for c in conj)
    return ", ".join(parts)


def predicate_tokens(head: Token) -> list[Token]:
    """Сказуемое: вершина + связка/вспомогательный глагол + инфинитив составного сказуемого + «не»."""
    toks = [head]
    for c in head.children:
        d = dep(c)
        if d in PREDICATE_PARTS:
            toks.append(c)
        elif d == "xcomp" and verb_form(c) == "Inf":
            toks.append(c)
            toks.extend(g for g in c.children if dep(g) in PREDICATE_PARTS)
        elif c.lower_ in NEGATIONS and c.i < head.i:
            toks.append(c)
        elif c.lower_ == "бы":
            toks.append(c)
    return sorted(toks, key=lambda t: t.i)


def homogeneous_predicates(head: Token) -> list[Token]:
    return [c for c in head.children if dep(c) == "conj" and not is_clause_head(c) and c.pos_ in ("VERB", "AUX", "ADJ")]


def predicate_text(head: Token) -> str:
    heads = [head] + homogeneous_predicates(head)
    return ", ".join(_phrase_text(predicate_tokens(h)) for h in heads)


def member_of(tok: Token, _depth: int = 0) -> str:
    """Член предложения в терминах школьной грамматики (приближённо)."""
    if _depth > 20:
        return ""
    d = dep(tok)
    if d in FUNCTION_DEPS or tok.is_punct or (tok.pos_ in FUNCTION_POS and d != "root"):
        return ""
    if is_nominative_sentence_head(tok):
        return "главный член"
    if d in ("conj", "flat", "flat:name", "flat:foreign"):
        if d == "conj" and is_clause_head(tok):
            return "сказуемое"
        return member_of(tok.head, _depth + 1)
    if is_clause_head(tok):
        return "сказуемое"
    if d in PREDICATE_PARTS and is_clause_head(tok.head):
        return "сказуемое"
    if d == "xcomp":
        if verb_form(tok) == "Inf" and is_clause_head(tok.head):
            return "сказуемое"
        return "дополнение"
    if tok.lower_ in NEGATIONS:
        return ""
    if d == "advcl":
        return "обстоятельство"
    if d == "acl":
        return "определение"
    return MEMBER_BY_DEP.get(d, MEMBER_BY_DEP.get(d.split(":", 1)[0], ""))


def tree_depth(span: Span) -> int:
    best = 0
    for tok in span:
        d, cur = 0, tok
        while not is_root(cur) and d < 100:
            cur = cur.head
            d += 1
        best = max(best, d)
    return best


def mean_dependency_distance(span: Span) -> float:
    dists = [abs(t.i - t.head.i) for t in span if not is_root(t) and not t.is_punct]
    return sum(dists) / len(dists) if dists else 0.0


def purpose_of(span: Span, clause_heads: list[Token], is_imperative: Callable[[Token], bool] | None = None) -> str:
    text = span.text.strip()
    tail = text[-3:]
    if "?" in tail:
        return "вопросительное"
    words = [t for t in span if is_word(t)]
    imperative = any(h.morph.get("Mood") == ["Imp"] for h in clause_heads)
    if words:
        imperative = imperative or words[0].lower_ in IMPERATIVE_STARTERS
        if is_imperative is not None:
            imperative = imperative or is_imperative(words[0])
    return "побудительное" if imperative else "повествовательное"


def format_bases(bases: list[list[str]]) -> str:
    """[[подлежащее, сказуемое], ...] -> «я + рада; ты + не представляешь»."""
    parts = []
    for subj, pred in bases:
        if subj and pred:
            parts.append(f"{subj} + {pred}")
        else:
            parts.append(subj or pred)
    return "; ".join(p for p in parts if p)


def analyze_sentence(span: Span, is_imperative: Callable[[Token], bool] | None = None) -> dict:
    """Возвращает поля SentenceInfo, относящиеся к синтаксису."""
    root = span.root
    clause_heads = [t for t in span if is_clause_head(t)]
    links = Counter(link for t in clause_heads if (link := clause_link(t)))

    if len(clause_heads) <= 1:
        structure = "простое"
    elif len(links) == 1:
        kind = next(iter(links))
        structure = {
            "сочинительная": "сложносочинённое",
            "подчинительная": "сложноподчинённое",
            "бессоюзная": "бессоюзное сложное",
        }[kind]
    else:
        structure = "сложное с разными видами связи"

    nominative = is_nominative_sentence_head(root)
    composition = ""
    if structure == "простое":
        if nominative:
            composition = "односоставное (назывное)"
        else:
            composition = "двусоставное" if has_subject(root) else "односоставное"

    bases = []
    for h in clause_heads:
        if h.i == root.i and nominative:
            bases.append([_phrase_text([h] + [c for c in h.children if dep(c) in ("flat", "flat:name")]), ""])
        else:
            bases.append([subject_text(h), predicate_text(h)])

    participial = []
    adverbial = []
    for tok in span:
        vf = verb_form(tok)
        if vf == "Part" and dep(tok) != "root" and not is_clause_head(tok):
            phrase = subtree_text(tok)
            if len(phrase.split()) >= 2:
                participial.append(phrase)
        elif vf == "Conv" and not is_clause_head(tok):
            adverbial.append(subtree_text(tok))

    # однородные члены (в т.ч. сказуемые): в UD все сочинённые элементы висят на первом
    homogeneous = []
    for tok in span:
        if tok.is_punct:
            continue
        conj = [
            c for c in tok.children
            if dep(c) == "conj" and not is_clause_head(c) and pos_group(c) == pos_group(tok)
        ]
        if conj:
            homogeneous.append([t.text for t in sorted([tok] + conj, key=lambda t: t.i)])

    text = span.text.strip()
    return {
        "bases": bases,
        "purpose": purpose_of(span, clause_heads, is_imperative),
        "exclamatory": "!" in text[-3:],
        "structure": structure,
        "composition": composition,
        "n_clauses": max(1, len(clause_heads)),
        "depth": tree_depth(span),
        "mean_dep_distance": round(mean_dependency_distance(span), 3),
        "participial": participial,
        "adverbial": adverbial,
        "homogeneous": homogeneous,
    }
