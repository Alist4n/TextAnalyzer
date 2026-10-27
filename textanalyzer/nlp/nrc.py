"""Словарь эмоций NRC Word-Emotion Association Lexicon (EmoLex) для русского языка.

EmoLex (Saif M. Mohammad, Peter D. Turney, National Research Council Canada) — 14 тыс.
английских слов; для каждого краудсорсингом отмечено, связано ли оно с восемью эмоциями (0/1).
Русские слова — машинный перевод Google Translate (2022) из того же архива NRC.

Лицензия NRC: только некоммерческое исследовательское и учебное использование, данные нельзя
распространять. Поэтому словарь не входит в программу: install() скачивает архив с сайта NRC
и собирает его в формат программы (config.lexicon_path("nrc")). Запускается из окна (меню «Файл»),
командой download-nrc или scripts/download_nrc_lexicon.py.

Сборка: перевод приводится к лемме pymorphy3 (как леммы слов в анализируемом тексте). На одну
русскую лемму часто переведено несколько английских слов (радость ← joy, gladness, cheer);
вес эмоции — доля этих слов, связанных с ней, связи слабее MIN_SHARE отбрасываются как шум
перевода и многозначности; стоп-слова тоже. Используются пять эмоций, которые есть и у нейросети (CEDR):
радость, грусть, удивление, страх, гнев; отвращение, доверие и ожидание EmoLex не берутся.
"""

from __future__ import annotations

import csv
import io
import json
import re
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Callable

NRC_EMOTIONS = ["joy", "sadness", "surprise", "fear", "anger"]
ARCHIVE_NAME = "NRC-Emotion-Lexicon.zip"
RUSSIAN_FILE = "OneFilePerLanguage/Russian-NRC-EmoLex.txt"
MIN_SHARE = 0.5
CYRILLIC_WORD = re.compile(r"^[а-я]+(-[а-я]+)*$")

CREDIT = (
    "Словарь эмоций — NRC Word-Emotion Association Lexicon (EmoLex), авторы Saif M. Mohammad и "
    "Peter D. Turney, National Research Council Canada (NRC); русские слова — машинный перевод "
    "Google Translate из архива NRC."
)
LICENSE_NOTE = (
    "Лицензия NRC: бесплатно только для некоммерческого исследовательского и учебного использования; "
    "данные нельзя распространять (передавать другим) — отправляйте на страницу словаря; "
    "для коммерческого использования нужна лицензия NRC (saif.mohammad@nrc-cnrc.gc.ca)."
)
CITATION = (
    "Mohammad S. M., Turney P. D. Crowdsourcing a Word-Emotion Association Lexicon. "
    "Computational Intelligence, 29(3): 436–465, 2013."
)


def normalize(word: str) -> str:
    return word.strip().lower().replace("ё", "е")


def read_rows(lines) -> list[tuple[str, dict[str, int], str]]:
    """Строки файла языка NRC: (английское слово, {эмоция: 0/1}, перевод)."""
    reader = csv.reader(lines, delimiter="\t")
    header = next(reader)
    try:
        en_col = header.index("English Word")
        ru_col = header.index("Russian Word")
        cols = {e: header.index(e) for e in NRC_EMOTIONS}
    except ValueError as exc:
        raise ValueError(f"неожиданный формат файла NRC EmoLex: {exc}") from None
    rows = []
    for row in reader:
        if len(row) <= max(ru_col, en_col, *cols.values()):
            continue
        rows.append((row[en_col], {e: int(row[c] == "1") for e, c in cols.items()}, row[ru_col]))
    return rows


def _is_citation_form(parse) -> bool:
    """Словарная форма: инфинитив, им. п. ед. ч. (у прилагательных — мужской род), наречие и т. п."""
    g = parse.tag.grammemes
    if "INFN" in g:
        return True
    if "nomn" in g and ("sing" in g or "Pltm" in g):
        return parse.tag.POS != "ADJF" or "masc" in g
    return parse.tag.POS in ("ADVB", "PRED", "INTJ", "COMP")


def lemma_keys(word: str, morph) -> set[str]:
    """Леммы, под которыми перевод попадёт в словарь; пусто — не однословный русский перевод."""
    word = normalize(word)
    if not CYRILLIC_WORD.match(word):
        return set()  # словосочетание, латиница (непереведённое слово), цифры
    parses = morph.parse(word)
    forms = {normalize(p.normal_form) for p in parses}
    citations = [p for p in parses if _is_citation_form(p)]
    if word in forms or citations or not parses:
        keys = {word}
    else:  # перевод в косвенной форме («слёзы») — берём лемму
        keys = {normalize(parses[0].normal_form)}
    # у вариантов лемма pymorphy бывает другой («счастье» -> «счастие») — оставляем обе
    keys |= {normalize(p.normal_form) for p in citations}
    # причастие («испуганный»): spaCy может дать лемму-глагол («испугать») — добавляем и её
    keys |= {normalize(p.normal_form) for p in parses if {"PRTF", "PRTS"} & set(p.tag.grammemes)}
    return keys


def build(rows, morph, min_share: float = MIN_SHARE,
          stop_words: set[str] = frozenset()) -> tuple[dict[str, dict[str, float]], dict]:
    """stop_words — служебные и самые частые слова: их связь с эмоцией в переводе — артефакт
    («очень» ← sorely: грусть, «больше» ← more: удивление), такие слова не берутся."""
    stop = {normalize(w) for w in stop_words}
    sources: dict[str, list[dict[str, int]]] = defaultdict(list)
    skipped = 0
    for _en, assoc, ru in rows:
        keys = lemma_keys(ru, morph)
        if not keys:
            skipped += 1
        for key in keys:
            sources[key].append(assoc)
    lexicon: dict[str, dict[str, float]] = {e: {} for e in NRC_EMOTIONS}
    weak = 0
    stop_dropped = sorted(w for w in sources if w in stop and any(a[e] for a in sources[w] for e in NRC_EMOTIONS))
    for lemma, assocs in sources.items():
        if lemma in stop:
            continue
        for e in NRC_EMOTIONS:
            share = sum(a[e] for a in assocs) / len(assocs)
            if share >= min_share:
                lexicon[e][lemma] = round(share, 2)
            elif share > 0:
                weak += 1
    for e in NRC_EMOTIONS:
        lexicon[e] = dict(sorted(lexicon[e].items()))
    stats = {
        "english_words": len(rows),
        "not_single_russian_word": skipped,
        "russian_lemmas": len(sources),
        "emotional_lemmas": len({w for d in lexicon.values() for w in d}),
        "weak_links_dropped": weak,
        "stop_words_dropped": stop_dropped,
        "per_emotion": {e: len(lexicon[e]) for e in NRC_EMOTIONS},
    }
    return lexicon, stats


def build_from_zip(zip_path: Path, out_path: Path, morph=None) -> dict:
    """Собирает русский словарь из архива NRC-Emotion-Lexicon.zip; возвращает статистику."""
    if morph is None:
        import pymorphy3

        morph = pymorphy3.MorphAnalyzer()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        name = next((n for n in zf.namelist() if n.endswith(RUSSIAN_FILE)), None)
        if name is None:
            raise ValueError(f"в архиве {zip_path.name} нет файла {RUSSIAN_FILE}")
        readme = next((n for n in zf.namelist() if n.endswith("NRC-Emotion-Lexicon/README.txt")), None)
        text = zf.read(name).decode("utf-8-sig")
        if readme:  # условия использования и уведомления NRC остаются рядом со словарём
            (out_path.parent / "README-NRC.txt").write_bytes(zf.read(readme))
    from spacy.lang.ru.stop_words import STOP_WORDS

    lexicon, stats = build(read_rows(io.StringIO(text)), morph, stop_words=STOP_WORDS)
    data = {
        "_meta": {
            "name": "NRC Word-Emotion Association Lexicon (EmoLex) v0.92, русский машинный перевод (2022)",
            "credit": CREDIT,
            "license": LICENSE_NOTE,
            "citation": CITATION,
            "home": "https://saifmohammad.com/WebPages/NRC-Emotion-Lexicon.htm",
            "source_file": name,
            "built": date.today().isoformat(),
            "method": f"леммы pymorphy3; вес — доля английских слов-источников, связанных с эмоцией; "
                      f"связи слабее {MIN_SHARE} и стоп-слова spaCy отброшены",
            "stats": stats,
        },
        **lexicon,
    }
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return stats


class DownloadCancelled(Exception):
    pass


ProgressFn = Callable[[int, int], None]  # скачано байт, всего байт (0 — размер неизвестен)


def download(url: str, target: Path, progress: ProgressFn | None = None,
             cancelled: Callable[[], bool] = lambda: False) -> None:
    tmp = target.with_suffix(".part")
    # сайт NRC отвечает 406 на запрос со стандартным User-Agent Python
    request = urllib.request.Request(url, headers={"User-Agent": "TextAnalyzer/0.1", "Accept": "*/*"})
    try:
        with urllib.request.urlopen(request, timeout=60) as resp, open(tmp, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while chunk := resp.read(1 << 16):
                if cancelled():
                    raise DownloadCancelled()
                out.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(target)


def install(force: bool = False, progress: ProgressFn | None = None, log: Callable[[str], None] = print,
            cancelled: Callable[[], bool] = lambda: False) -> dict:
    """Скачивает архив NRC EmoLex (если его ещё нет) и собирает русский словарь; возвращает статистику."""
    from ..config import NRC_URL, lexicon_path, nrc_dir

    zip_path = nrc_dir() / ARCHIVE_NAME
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if force or not zip_path.exists():
        log(f"Загрузка {NRC_URL}")
        download(NRC_URL, zip_path, progress, cancelled)
    else:
        log(f"Архив уже скачан: {zip_path}")
    log("Сборка русского словаря…")
    try:
        return build_from_zip(zip_path, lexicon_path("nrc"))
    except zipfile.BadZipFile:
        if force:
            raise
        log("Архив повреждён — скачиваю заново")
        return install(True, progress, log, cancelled)
