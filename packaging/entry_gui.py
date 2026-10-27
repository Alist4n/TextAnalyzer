"""Точка входа собранной программы: окно TextAnalyzer."""

import faulthandler
import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    # у оконной сборки нет консоли (sys.stdout/stderr = None): вывод библиотек и падения — в журнал
    if sys.stdout is None or sys.stderr is None:
        from textanalyzer.config import user_data_dir

        log_dir = user_data_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        log = open(log_dir / "TextAnalyzer.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log
        faulthandler.enable(log)

    from textanalyzer.gui.app import run_gui

    sys.exit(run_gui())
