"""Чтение входных текстов из файлов.

Поддерживаются .txt / .text (обычный текст), .md (Markdown читается как обычный
текст), .docx (только абзацы основного текста) и таблицы .csv / .tsv / .xlsx
(каждая строка — отдельный текст, см. tables.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

TEXT_EXTENSIONS = {
    ".txt": "обычный текст",
    ".text": "обычный текст",
    ".md": "Markdown",
    ".docx": "документ Word",
}
TABLE_EXTENSIONS = {
    ".csv": "таблица CSV",
    ".tsv": "таблица TSV",
    ".xlsx": "таблица Excel",
    ".xlsm": "таблица Excel",
}
SUPPORTED_EXTENSIONS = {**TEXT_EXTENSIONS, **TABLE_EXTENSIONS}
SUPPORTED_LIST = ".txt, .md, .docx, .csv, .xlsx"

# Подсказки для частых неподдерживаемых форматов
UNSUPPORTED_HINTS = {
    ".doc": "формат Word 97–2003 — откройте в Word и сохраните как .docx",
    ".pdf": "PDF не поддерживается — скопируйте текст в редактор программы или сохраните как .txt",
    ".rtf": "RTF не поддерживается — откройте в Word и сохраните как .docx или .txt",
    ".odt": "формат LibreOffice — сохраните как .docx или .txt",
    ".html": "HTML не поддерживается — скопируйте текст страницы в редактор",
    ".htm": "HTML не поддерживается — скопируйте текст страницы в редактор",
    ".epub": "электронные книги не поддерживаются — сохраните текст как .txt",
    ".fb2": "электронные книги не поддерживаются — сохраните текст как .txt",
    ".xls": "старый формат Excel 97–2003 — откройте в Excel и сохраните как .xlsx или .csv",
    ".ods": "таблица LibreOffice — сохраните как .xlsx или .csv",
    ".numbers": "таблица Numbers — экспортируйте в .xlsx или .csv",
}

ENCODING_NAMES = {
    "utf_8": "UTF-8",
    "utf-8": "UTF-8",
    "utf_16": "UTF-16",
    "cp1251": "Windows-1251",
    "koi8_r": "KOI8-R",
    "cp866": "CP866 (DOS)",
    "mac_cyrillic": "Mac Cyrillic",
}


class UnsupportedFileError(ValueError):
    pass


@dataclass
class LoadedText:
    path: Path
    text: str
    kind: str                  # «обычный текст», «Markdown», «документ Word»
    encoding: str | None = None

    def describe(self) -> str:
        enc = f", кодировка {self.encoding}" if self.encoding else ""
        chars = f"{len(self.text):,}".replace(",", " ")
        return f"{self.kind}{enc}, {chars} символов"


@dataclass
class FileSelection:
    files: list[Path] = field(default_factory=list)
    unsupported: list[Path] = field(default_factory=list)   # явно указанные файлы других форматов
    skipped_in_folders: int = 0                             # файлы других форматов внутри папок


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS and not path.name.startswith("~$")


def is_table(path: Path) -> bool:
    return path.suffix.lower() in TABLE_EXTENSIONS


def unsupported_reason(path: Path) -> str:
    ext = path.suffix.lower()
    if path.name.startswith("~$"):
        return "временный файл Word или Excel, его открывать не нужно"
    return UNSUPPORTED_HINTS.get(ext, f"формат {ext or 'без расширения'} не поддерживается")


# Однобайтовые кириллические кодировки, из которых выбираем для не-UTF файлов
RUSSIAN_ENCODINGS = [
    ("cp1251", "Windows-1251"),
    ("koi8_r", "KOI8-R"),
    ("cp866", "CP866 (DOS)"),
    ("mac_cyrillic", "Mac Cyrillic"),
]


def _is_cyr_lower(ch: str) -> bool:
    return "а" <= ch <= "я" or ch == "ё"


def _is_cyr_upper(ch: str) -> bool:
    return "А" <= ch <= "Я" or ch == "Ё"


def _russian_score(text: str) -> tuple[float, bool]:
    """Насколько текст похож на русский и есть ли в нём кириллица.

    В верной кодировке буквы в основном строчные, а заглавные стоят в начале слов.
    В неверной появляются заглавные посреди слова — «дБ», «дЮ» (KOI8-R вместо cp1251) —
    или псевдографика и символы (CP866)."""
    score = 0.0
    has_cyrillic = False
    prev = ""
    for ch in text:
        if _is_cyr_lower(ch):
            score += 1
            has_cyrillic = True
        elif _is_cyr_upper(ch):
            has_cyrillic = True
            if _is_cyr_lower(prev):
                score -= 2  # заглавная сразу после строчной
        elif "Ѐ" <= ch <= "ӿ":
            score -= 3  # нерусские кириллические буквы (Џ, Љ, ђ…) — признак чужой кодировки
        elif ord(ch) > 0x7F and not ch.isalpha() and ch not in "«»—–…№“”„’  ":
            score -= 3
        prev = ch
    return score, has_cyrillic


def read_text_file(path: Path) -> tuple[str, str]:
    """Возвращает текст и название кодировки."""
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace"), "UTF-8"
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16"), "UTF-16"
    try:
        return raw.decode("utf-8"), "UTF-8"
    except UnicodeDecodeError:
        pass

    # Универсальные детекторы на коротких русских текстах путают cp1251 с cp1125 и т. п.,
    # поэтому сначала выбираем лучшую из русских кодировок.
    candidates = []
    for codec, label in RUSSIAN_ENCODINGS:
        try:
            text = raw.decode(codec)
        except UnicodeDecodeError:
            continue
        score, has_cyrillic = _russian_score(text)
        if has_cyrillic:
            candidates.append((score, text, label))
    if candidates:
        # при равенстве побеждает первая в списке — Windows-1251, самая распространённая
        score, text, label = max(candidates, key=lambda c: c[0])
        if score >= 0:
            return text, label

    from charset_normalizer import from_bytes

    best = from_bytes(raw).best()
    if best is not None:
        return str(best), ENCODING_NAMES.get(best.encoding, best.encoding)
    return raw.decode("cp1251", errors="replace"), "Windows-1251"


def read_docx(path: Path) -> str:
    import docx
    from docx.opc.exceptions import PackageNotFoundError

    try:
        document = docx.Document(str(path))
    except (PackageNotFoundError, KeyError, ValueError) as exc:
        raise UnsupportedFileError(
            "файл повреждён или это не документ Word (возможно, .doc, переименованный в .docx)"
        ) from exc
    return "\n".join(p.text for p in document.paragraphs)


def load_file(path: str | Path) -> LoadedText:
    path = Path(path)
    if not is_supported(path):
        raise UnsupportedFileError(unsupported_reason(path))
    if is_table(path):
        raise ValueError(f"{path.name}: таблицы читаются через tables.read_table")
    kind = SUPPORTED_EXTENSIONS[path.suffix.lower()]
    if path.suffix.lower() == ".docx":
        return LoadedText(path, read_docx(path), kind)
    text, encoding = read_text_file(path)
    return LoadedText(path, text, kind, encoding)


def read_file(path: str | Path) -> str:
    return load_file(path).text


DEFAULT_SEPARATOR = "==="


def separator_title(line: str, separator: str) -> str | None:
    """Если строка — разделитель, возвращает название следующего текста («» — без названия), иначе None.

    «=== Отзыв 1», «=== Глава 2 ===» и просто «=====» — разделители для «===»."""
    s = line.strip()
    if not separator or not s.startswith(separator):
        return None
    # по краям названия срезаем только знаки разделителя, а не буквы: «Текст: тест» -> «тест»
    edge_chars = "".join(ch for ch in separator if not ch.isalnum()) + " \t"
    return s[len(separator):].strip().strip(edge_chars)


def split_texts(text: str, separator: str | None) -> list[tuple[str | None, str]]:
    """Делит текст на части по строкам-разделителям: [(название или None, текст), …].

    Без разделителей возвращает весь текст одной частью. Пустые части пропускаются."""
    sep = (separator or "").strip()
    if not sep:
        return [(None, text)]
    parts: list[tuple[str | None, str]] = []
    title: str | None = None
    lines: list[str] = []
    found = False
    for line in text.splitlines():
        next_title = separator_title(line, sep)
        if next_title is None:
            lines.append(line)
            continue
        found = True
        body = "\n".join(lines).strip()
        if body:
            parts.append((title, body))
        title, lines = next_title or None, []
    if not found:
        return [(None, text)]
    body = "\n".join(lines).strip()
    if body:
        parts.append((title, body))
    return parts


def split_items(
    items: list[tuple[str, str, str | None]], separator: str | None
) -> list[tuple[str, str, str | None]]:
    """(название, текст, источник) -> то же, но тексты с разделителями разбиты на несколько.

    Части без названия получают имя «исходное — 1», «исходное — 2»…"""
    result = []
    for name, text, source in items:
        parts = split_texts(text, separator)
        if len(parts) == 1 and parts[0][0] is None:
            result.append((name, parts[0][1], source))
            continue
        n = len(parts)
        for k, (title, body) in enumerate(parts, 1):
            part_name = title or (name if n == 1 else f"{name} — {k}")
            where = source or name
            result.append((part_name, body, f"{where}, текст {k} из {n}" if n > 1 else source))
    return result


def collect_files(paths: list[str | Path]) -> FileSelection:
    """Разворачивает папки (с подпапками) в список поддерживаемых файлов."""
    selection = FileSelection()
    for p in map(Path, paths):
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if not f.is_file() or f.name.startswith("~$"):
                    continue
                if is_supported(f):
                    selection.files.append(f)
                elif not f.name.startswith("."):
                    selection.skipped_in_folders += 1
        elif p.is_file():
            if is_supported(p):
                selection.files.append(p)
            else:
                selection.unsupported.append(p)
    return selection
