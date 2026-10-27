"""Точка входа собранной программы: командная строка (TextAnalyzer-cli analyze …, download-nrc)."""

import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from textanalyzer.cli import main

    sys.exit(main())
