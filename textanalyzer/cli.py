"""Командная строка: пакетный анализ без GUI.

Примеры:
    python -m textanalyzer analyze samples -o out
    python -m textanalyzer analyze a.txt b.docx --formats html,json --emotions lexicon
    python -m textanalyzer analyze samples --lexicon manual
    python -m textanalyzer analyze --text "Как же я рад тебя видеть!"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import EMOTION_METHODS, LEXICONS, AnalysisOptions, default_lexicon, default_output_dir
from .loaders import (
    DEFAULT_SEPARATOR,
    SUPPORTED_LIST,
    UnsupportedFileError,
    collect_files,
    is_table,
    load_file,
    split_items,
    split_texts,
    unsupported_reason,
)
from .report import FORMATS, export

INPUT_HELP = f"""\
входные файлы:
  {SUPPORTED_LIST} — один файл = один текст (отдельный раздел отчёта);
  в таблицах — одна строка = один текст.
  .txt/.md: кодировка определяется автоматически (UTF-8, UTF-16, Windows-1251, KOI8-R, CP866);
            разметка Markdown не удаляется.
  .docx:    читаются только абзацы основного текста (без таблиц, колонтитулов, сносок).
  Папка: берутся все подходящие файлы, включая подпапки. Перевод строки = граница предложения.
  Не поддерживаются: .doc, .pdf, .rtf, .odt, .html — сохраните их как .docx или .txt.

несколько текстов в одном файле:
  Строка, начинающаяся с разделителя (по умолчанию {DEFAULT_SEPARATOR}), начинает новый текст;
  слова после разделителя — название текста в отчёте:
      {DEFAULT_SEPARATOR} Отзыв 1
      Текст первого отзыва…
      {DEFAULT_SEPARATOR} Отзыв 2
      Текст второго…
  Файл без разделителей — один текст. Другой разделитель: --separator "***"; отключить: --no-split.

таблицы .csv, .tsv, .xlsx:
  Каждая строка — отдельный текст. Столбец с текстом и столбец с названием угадываются
  (текст — самые длинные значения; название — заголовок вроде «Название», «Товар», «ID»)
  или задаются по заголовку, букве (A, B…) или номеру с 1:
      --text-column "Отзыв" --title-column "Товар"
  Без названия тексты называются по номеру строки: --title-column none.
  Кодировка и разделитель CSV (; , табуляция |) определяются автоматически.
  Лист Excel — --sheet "Лист2" (по умолчанию активный); --no-header — первая строка тоже текст.
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="textanalyzer",
        description="Морфологический, синтаксический и эмоциональный анализ русских текстов",
        epilog=INPUT_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="command")

    sub.add_parser("gui", help="запустить графический интерфейс (по умолчанию)")
    d = sub.add_parser("download-nrc", help="скачать словарь эмоций NRC EmoLex с сайта NRC и собрать русский словарь")
    d.add_argument("--force", action="store_true", help="скачать архив заново, даже если он уже есть")

    a = sub.add_parser(
        "analyze",
        help="проанализировать файлы/папки и сохранить отчёт",
        epilog=INPUT_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    a.add_argument("paths", nargs="*", help=f"файлы {SUPPORTED_LIST} или папки с ними")
    a.add_argument("--text", action="append", default=[], help="текст прямо в командной строке (можно несколько раз)")
    a.add_argument("-o", "--out", type=Path, default=None, help=f"папка для отчётов (по умолчанию {default_output_dir()})")
    a.add_argument("--formats", default="html,docx,json", help="через запятую: " + ",".join(FORMATS))
    a.add_argument("--name", default=None, help="имя файлов отчёта без расширения")
    a.add_argument("--emotions", choices=list(EMOTION_METHODS) + ["off"], default="both", help="метод определения эмоций")
    a.add_argument("--lexicon", choices=LEXICONS, default=None,
                   help="словарь эмоций: nrc — NRC EmoLex (скачивается отдельно командой download-nrc), "
                        "manual — ручной словарь TextAnalyzer (входит в программу); "
                        "по умолчанию nrc, если он скачан, иначе manual")
    a.add_argument("--no-morphology", action="store_true")
    a.add_argument("--no-syntax", action="store_true")
    a.add_argument("--no-entities", action="store_true")
    a.add_argument("--max-trees", type=int, default=AnalysisOptions.max_trees, help="деревьев зависимостей на текст в HTML")
    a.add_argument("--detailed", type=int, default=AnalysisOptions.detailed_texts,
                   help="подробные разделы (графики, таблицы) — для первых N текстов; остальные компактно")
    a.add_argument("--separator", default=DEFAULT_SEPARATOR,
                   help=f"строка-разделитель нескольких текстов в одном файле (по умолчанию {DEFAULT_SEPARATOR})")
    a.add_argument("--no-split", action="store_true", help="не делить файлы на тексты, каждый файл — один текст")
    a.add_argument("--text-column", help="таблицы: столбец с текстом (заголовок, буква или номер)")
    a.add_argument("--title-column", help="таблицы: столбец с названием текста; none — по номеру строки")
    a.add_argument("--sheet", help="таблицы Excel: лист (по умолчанию активный)")
    a.add_argument("--no-header", action="store_true", help="таблицы: первая строка — не заголовки, а данные")
    return p


def table_spec_from_args(table, args: argparse.Namespace):
    """Выбор столбцов: угаданный, с поправками из ключей командной строки."""
    from .tables import guess_spec, resolve_column, with_names

    spec = guess_spec(table, False if args.no_header else None)
    if args.text_column:
        spec.text_col = resolve_column(table, spec.has_header, args.text_column)
        if spec.title_col == spec.text_col:
            spec.title_col = None
    if args.title_column:
        if args.title_column.strip().lower() in ("none", "нет", "-"):
            spec.title_col = None
        else:
            spec.title_col = resolve_column(table, spec.has_header, args.title_column)
    return with_names(table, spec)


def load_table_items(path: Path, args: argparse.Namespace) -> list[tuple[str, str, str]]:
    from .tables import describe_spec, read_table, table_items, table_texts

    table = read_table(path, args.sheet)
    if args.sheet and table.sheet != args.sheet:
        raise ValueError(f"листа «{args.sheet}» нет; есть: {', '.join(table.sheet_names)}")
    if not table.rows:
        raise ValueError("таблица пустая")
    spec = table_spec_from_args(table, args)
    texts = table_texts(table, spec)
    print(f"{path}: {table.describe()}; {describe_spec(table, spec)}; текстов: {len(texts)}")
    return table_items(path.stem, table, texts)


def run_analyze(args: argparse.Namespace) -> int:
    separator = None if args.no_split else args.separator
    items: list[tuple[str, str, str | None]] = []
    selection = collect_files(args.paths)
    for path in selection.unsupported:
        print(f"Пропущен {path}: {unsupported_reason(path)}", file=sys.stderr)
    if selection.skipped_in_folders:
        print(f"В папках пропущено файлов других форматов: {selection.skipped_in_folders}", file=sys.stderr)
    for path in selection.files:
        if is_table(path):
            try:
                rows = load_table_items(path, args)
            except (UnsupportedFileError, ValueError, OSError) as exc:
                print(f"Пропущен {path}: {exc}", file=sys.stderr)
                continue
            if not rows:
                print(f"Пропущен {path}: в выбранном столбце нет текста", file=sys.stderr)
            items.extend(rows)
            continue
        try:
            loaded = load_file(path)
        except (UnsupportedFileError, OSError) as exc:
            print(f"Пропущен {path}: {exc}", file=sys.stderr)
            continue
        if not loaded.text.strip():
            print(f"Пропущен {path}: в файле нет текста", file=sys.stderr)
            continue
        n_parts = len(split_texts(loaded.text, separator))
        parts_note = f", текстов по разделителю «{separator}»: {n_parts}" if n_parts > 1 else ""
        print(f"{path}: {loaded.describe()}{parts_note}")
        items.extend(split_items([(path.stem, loaded.text, str(path))], separator))
    for k, text in enumerate(args.text, 1):
        items.extend(split_items([(f"Текст {k}", text, None)], separator))
    if not items:
        print(f"Нет входных текстов: укажите файлы {SUPPORTED_LIST}, папки с ними или --text.", file=sys.stderr)
        return 2

    formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]
    unknown = set(formats) - set(FORMATS)
    if unknown:
        print(f"Неизвестные форматы: {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2

    lexicon = args.lexicon or default_lexicon()
    if args.lexicon is None and lexicon == "manual" and args.emotions in ("both", "lexicon"):
        print("Словарь NRC EmoLex не скачан — используется ручной словарь "
              "(скачать NRC: команда download-nrc; выбрать явно: --lexicon).")
    options = AnalysisOptions(
        morphology=not args.no_morphology,
        syntax=not args.no_syntax,
        entities=not args.no_entities,
        emotions=args.emotions != "off",
        emotion_method=args.emotions if args.emotions != "off" else "both",
        lexicon=lexicon,
        max_trees=args.max_trees,
        detailed_texts=args.detailed,
    )

    from .nlp.emotions import ResourceUnavailableError
    from .nlp.pipeline import Analyzer

    def progress(fraction: float, message: str) -> None:
        print(f"\r[{fraction * 100:5.1f}%] {message[:90]:<90}", end="", flush=True)

    try:
        corpus = Analyzer(options).analyze_corpus(items, progress=progress, log=lambda m: print(f"\n{m}"))
    except ResourceUnavailableError as exc:
        print(f"\n\n{exc}", file=sys.stderr)
        return 1
    print()
    written = export(corpus, args.out or default_output_dir(), formats, args.name)
    for fmt, path in written.items():
        print(f"{fmt.upper()}: {path}")
    return 0


def run_download_nrc(args: argparse.Namespace) -> int:
    from .config import NRC_HOME, lexicon_path
    from .nlp import nrc

    print(nrc.CREDIT)
    print(nrc.LICENSE_NOTE)
    print(f"Страница словаря: {NRC_HOME}\n")

    def progress(done: int, total: int) -> None:
        if total:
            print(f"\r  {done / 2**20:5.1f} из {total / 2**20:.1f} МБ", end="", flush=True)

    try:
        stats = nrc.install(args.force, progress, log=lambda m: print(f"\n{m}" if m.startswith("Сборка") else m))
    except OSError as exc:  # нет сети, сайт недоступен, нет места на диске
        print(f"\nНе удалось скачать словарь: {exc}", file=sys.stderr)
        return 1
    print(f"Словарь: {lexicon_path('nrc')}")
    print(f"  английских слов: {stats['english_words']}, из них без однословного русского перевода: "
          f"{stats['not_single_russian_word']}")
    print(f"  русских лемм: {stats['russian_lemmas']}, эмоциональных: {stats['emotional_lemmas']}")
    print("  по эмоциям: " + ", ".join(f"{e} {n}" for e, n in stats["per_emotion"].items()))
    print("Готово.")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(argv)
    if args.command == "analyze":
        return run_analyze(args)
    if args.command == "download-nrc":
        return run_download_nrc(args)
    from .gui.app import run_gui

    return run_gui()
