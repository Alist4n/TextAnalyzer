"""Пути к ресурсам и настройки анализа."""

from __future__ import annotations

import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

APP_NAME = "TextAnalyzer"

SPACY_MODEL = "ru_core_news_md"
EMOTION_MODEL_ID = "cointegrated/rubert-tiny2-cedr-emotion-detection"
EMOTION_MODEL_DIRNAME = "rubert-tiny2-cedr-emotion-detection"

# словарь эмоций NRC EmoLex: лицензия запрещает распространять данные, поэтому он не входит
# в программу, а скачивается с сайта NRC (scripts/download_nrc_lexicon.py) в models/
NRC_HOME = "https://saifmohammad.com/WebPages/NRC-Emotion-Lexicon.htm"
NRC_URL = "https://saifmohammad.com/WebDocs/Lexicons/NRC-Emotion-Lexicon.zip"
NRC_DIRNAME = "nrc-emolex"


def is_frozen() -> bool:
    """Запущена собранная программа (PyInstaller), а не исходники."""
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """Корень приложения: папка проекта или распакованный PyInstaller-бандл."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def package_dir() -> Path:
    return Path(__file__).resolve().parent


def models_dir() -> Path:
    return app_root() / "models"


def emotion_model_source() -> str:
    """Локальная копия модели эмоций, если скачана, иначе id на HuggingFace."""
    local = models_dir() / EMOTION_MODEL_DIRNAME
    if (local / "config.json").exists():
        return str(local)
    return EMOTION_MODEL_ID


def user_data_dir() -> Path:
    """Папка данных пользователя: %LOCALAPPDATA%\\TextAnalyzer, ~/Library/Application Support/TextAnalyzer."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_NAME


def nrc_dir() -> Path:
    # папка собранной программы может быть недоступна для записи (Program Files, подписанный .app),
    # поэтому собранная программа скачивает словарь в папку данных пользователя
    if is_frozen():
        return user_data_dir() / NRC_DIRNAME
    return models_dir() / NRC_DIRNAME


def lexicon_path(lexicon: str = "nrc") -> Path:
    """Эмоциональные слова: русский NRC EmoLex, собранный scripts/download_nrc_lexicon.py,
    или ручной словарь TextAnalyzer (свой, входит в программу)."""
    if lexicon == "manual":
        return package_dir() / "nlp" / "data" / "lexicon_manual_ru.json"
    return nrc_dir() / "lexicon_ru.json"


def default_lexicon() -> str:
    """NRC EmoLex, если он скачан; иначе ручной словарь — чтобы первый анализ в только что
    полученной программе прошёл без ошибки (NRC каждый скачивает сам)."""
    return "nrc" if lexicon_path("nrc").exists() else "manual"


def lexicon_rules_path() -> Path:
    """Правила словарного анализа (усилители, отрицания) — свои, входят в программу."""
    return package_dir() / "nlp" / "data" / "lexicon_rules_ru.json"


def default_output_dir() -> Path:
    return Path.home() / "Documents" / APP_NAME / "reports"


EMOTION_METHODS = ("both", "model", "lexicon")
# словари эмоций: "nrc" — NRC EmoLex (скачивается отдельно), "manual" — ручной словарь TextAnalyzer
LEXICONS = ("nrc", "manual")


@dataclass
class AnalysisOptions:
    morphology: bool = True
    syntax: bool = True
    emotions: bool = True
    entities: bool = True
    # "both" | "model" | "lexicon"
    emotion_method: str = "both"
    # "nrc" | "manual"
    lexicon: str = "nrc"
    # сколько деревьев зависимостей рисовать в HTML на один текст
    max_trees: int = 50
    # строк в таблице морфологического разбора (HTML / DOCX)
    max_token_rows_html: int = 3000
    max_token_rows_docx: int = 400
    # длина частотных списков
    top_n: int = 20
    # подробные разделы (графики, таблицы, деревья) — для первых N текстов;
    # остальные в HTML показываются компактно, в DOCX — только в сводной таблице
    detailed_texts: int = 30

    @property
    def use_model(self) -> bool:
        return self.emotions and self.emotion_method in ("both", "model")

    @property
    def use_lexicon(self) -> bool:
        return self.emotions and self.emotion_method in ("both", "lexicon")

    def to_dict(self) -> dict:
        return asdict(self)
