"""Скачивает модель эмоций в папку models/ для офлайн-работы и сборки дистрибутива.

Запуск: .venv\\Scripts\\python scripts\\download_models.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from textanalyzer.config import EMOTION_MODEL_ID, models_dir, EMOTION_MODEL_DIRNAME  # noqa: E402


def main() -> None:
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    target = models_dir() / EMOTION_MODEL_DIRNAME
    target.mkdir(parents=True, exist_ok=True)
    print(f"Загрузка {EMOTION_MODEL_ID} -> {target}")
    AutoTokenizer.from_pretrained(EMOTION_MODEL_ID).save_pretrained(target)
    model = AutoModelForSequenceClassification.from_pretrained(EMOTION_MODEL_ID)
    model.save_pretrained(target)
    print("Метки:", model.config.id2label)
    print("Готово.")


if __name__ == "__main__":
    main()
