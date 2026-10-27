"""Экспорт результатов анализа в HTML / DOCX / JSON."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

from ..nlp.models import CorpusResult

FORMATS = ("html", "docx", "json")


def write_json(corpus: CorpusResult, path: Path) -> Path:
    path.write_text(json.dumps(corpus.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_html(corpus: CorpusResult, path: Path) -> Path:
    from .html import render_html

    path.write_text(render_html(corpus), encoding="utf-8")
    return path


def report_basename(corpus: CorpusResult) -> str:
    try:
        stamp = datetime.fromisoformat(corpus.created).strftime("%Y-%m-%d_%H-%M-%S")
    except ValueError:
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"report_{stamp}"


def export(corpus: CorpusResult, out_dir: Path, formats: Iterable[str], basename: str | None = None) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = basename or report_basename(corpus)
    written: dict[str, Path] = {}
    for fmt in formats:
        path = out_dir / f"{base}.{fmt}"
        if fmt == "html":
            written[fmt] = write_html(corpus, path)
        elif fmt == "docx":
            from .docx import write_docx

            written[fmt] = write_docx(corpus, path)
        elif fmt == "json":
            written[fmt] = write_json(corpus, path)
        else:
            raise ValueError(f"Неизвестный формат отчёта: {fmt}")
    return written
