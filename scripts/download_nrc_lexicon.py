"""Скачивает словарь эмоций NRC EmoLex с сайта NRC и собирает русский словарь программы.

Запуск: .venv\\Scripts\\python scripts\\download_nrc_lexicon.py [--force]
То же самое: python -m textanalyzer download-nrc, в собранной программе — меню «Файл».

Лицензия NRC: только некоммерческое исследовательское и учебное использование, данные нельзя
распространять. Поэтому словарь не входит в программу и скачивается каждым пользователем сам.
Архив (~25 МБ) и собранный словарь лежат в models/nrc-emolex/.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from textanalyzer.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["download-nrc", *sys.argv[1:]]))
