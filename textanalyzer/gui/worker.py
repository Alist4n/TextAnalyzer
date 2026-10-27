"""Анализ в фоновом потоке, чтобы окно не зависало."""

from __future__ import annotations

import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from ..nlp.emotions import ResourceUnavailableError
from ..nlp.pipeline import AnalysisCancelled, Analyzer
from ..report import export


class AnalysisWorker(QObject):
    progress = Signal(float, str)
    log = Signal(str)
    finished = Signal(object, object)   # CorpusResult, dict[формат, Path]
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, analyzer: Analyzer, items: list, out_dir: Path, formats: list[str]) -> None:
        super().__init__()
        self.analyzer = analyzer
        self.items = items
        self.out_dir = out_dir
        self.formats = formats
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    @Slot()
    def run(self) -> None:
        try:
            corpus = self.analyzer.analyze_corpus(
                self.items,
                progress=self.progress.emit,
                cancelled=lambda: self._cancel,
                log=self.log.emit,
            )
            self.progress.emit(1.0, "Формирование отчётов…")
            written = export(corpus, self.out_dir, self.formats) if self.formats else {}
            self.finished.emit(corpus, written)
        except AnalysisCancelled:
            self.cancelled.emit()
        except ResourceUnavailableError as exc:
            self.failed.emit(str(exc))       # нет модели или словаря — понятное сообщение вместо трассировки
        except Exception:  # noqa: BLE001 — показываем пользователю любую ошибку
            self.failed.emit(traceback.format_exc())


class NrcDownloadWorker(QObject):
    """Скачивание и сборка словаря NRC EmoLex в фоновом потоке."""

    progress = Signal(int, int)          # скачано байт, всего
    log = Signal(str)
    finished = Signal(object)            # статистика сборки
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, force: bool = False) -> None:
        super().__init__()
        self.force = force
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    @Slot()
    def run(self) -> None:
        from ..nlp import nrc

        try:
            stats = nrc.install(self.force, self.progress.emit, self.log.emit, lambda: self._cancel)
            self.finished.emit(stats)
        except nrc.DownloadCancelled:
            self.cancelled.emit()
        except OSError as exc:  # нет сети, сайт недоступен, нет места на диске
            self.failed.emit(f"Не удалось скачать словарь: {exc}\n\nПроверьте подключение к интернету.")
        except Exception:  # noqa: BLE001
            self.failed.emit(traceback.format_exc())
