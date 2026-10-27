"""Сборка русского словаря из NRC EmoLex: на синтетическом файле в формате NRC и на скачанном словаре."""

import json
import zipfile

import pymorphy3
import pytest

from textanalyzer.config import lexicon_path, lexicon_rules_path
from textanalyzer.nlp import nrc
from textanalyzer.nlp.emotions import EmotionLexicon, LexiconUnavailableError

HEADER = ["English Word", "anger", "anticipation", "disgust", "fear", "joy", "negative", "positive",
          "sadness", "surprise", "trust", "Russian Word"]
ORDER = HEADER[1:-1]


def row(en, ru, *emotions):
    return "\t".join([en, *("1" if e in emotions else "0" for e in ORDER), ru])


SAMPLE = "\n".join([
    "\t".join(HEADER),
    row("joy", "радость", "joy", "positive"),
    row("gladness", "радость", "joy"),
    row("cheer", "радость", "joy", "surprise", "trust"),     # удивление 1 из 3 — шум, отбрасывается
    row("fear", "страх", "fear", "anger"),
    row("dread", "страх", "fear", "anticipation"),            # гнев 1 из 2 — остаётся с весом 0.5
    row("felicity", "Счастье", "joy"),                        # pymorphy: лемма «счастие»
    row("tears", "слезы", "sadness"),                         # перевод в косвенной форме
    row("sorely", "очень", "sadness"),                        # стоп-слово
    row("at a loss", "в растерянности", "fear"),              # словосочетание
    row("okay", "ok", "joy"),                                 # не переведено
    row("disgusting", "отвратительный", "disgust"),           # отвращение не используется
])


@pytest.fixture(scope="module")
def morph():
    return pymorphy3.MorphAnalyzer()


def test_build_shares_lemmas_and_filters(morph):
    rows = nrc.read_rows(SAMPLE.splitlines())
    lexicon, stats = nrc.build(rows, morph, stop_words={"очень"})
    assert lexicon["joy"]["радость"] == 1.0
    assert "радость" not in lexicon["surprise"]
    assert lexicon["fear"]["страх"] == 1.0 and lexicon["anger"]["страх"] == 0.5
    assert lexicon["joy"]["счастье"] == 1.0 and lexicon["joy"]["счастие"] == 1.0
    assert lexicon["sadness"]["слеза"] == 1.0
    all_words = {w for d in lexicon.values() for w in d}
    assert "очень" not in all_words and "отвратительный" not in all_words
    assert stats["not_single_russian_word"] == 2
    assert stats["stop_words_dropped"] == ["очень"]


def test_build_from_zip_keeps_credit_and_readme(tmp_path, morph):
    archive = tmp_path / "NRC-Emotion-Lexicon.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("NRC-Emotion-Lexicon/" + nrc.RUSSIAN_FILE, SAMPLE)
        zf.writestr("NRC-Emotion-Lexicon/README.txt", "TERMS OF USE")
    out = tmp_path / "nrc" / "lexicon_ru.json"
    nrc.build_from_zip(archive, out, morph)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "Mohammad" in data["_meta"]["credit"] and "некоммерческ" in data["_meta"]["license"]
    assert data["joy"]["радость"] == 1.0
    assert (out.parent / "README-NRC.txt").read_text() == "TERMS OF USE"
    lex = EmotionLexicon(out, lexicon_rules_path())
    assert lex.name.startswith("NRC") and len(lex) > 0


def test_missing_lexicon_explains_how_to_get_it(tmp_path):
    with pytest.raises(LexiconUnavailableError, match="Скачать словарь NRC EmoLex.*download-nrc"):
        EmotionLexicon(tmp_path / "нет.json", lexicon_rules_path())


@pytest.fixture
def nrc_site(tmp_path, monkeypatch):
    """«Сайт NRC» — локальный архив по file://, словарь собирается во временную папку."""
    from textanalyzer import config

    archive = tmp_path / "site" / "NRC-Emotion-Lexicon.zip"
    archive.parent.mkdir()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("NRC-Emotion-Lexicon/" + nrc.RUSSIAN_FILE, SAMPLE)
    monkeypatch.setattr(config, "NRC_URL", archive.as_uri())
    monkeypatch.setattr(config, "nrc_dir", lambda: tmp_path / "user" / "nrc-emolex")
    return tmp_path / "user" / "nrc-emolex"


def test_install_downloads_and_builds(nrc_site):
    seen, logs = [], []
    stats = nrc.install(progress=lambda done, total: seen.append((done, total)), log=logs.append)
    assert stats["per_emotion"]["joy"] >= 1
    assert (nrc_site / nrc.ARCHIVE_NAME).exists() and (nrc_site / "lexicon_ru.json").exists()
    assert seen and seen[-1][0] == seen[-1][1] > 0
    assert not list(nrc_site.glob("*.part"))

    logs.clear()
    nrc.install(log=logs.append)                      # архив уже есть — второй раз не качаем
    assert any("уже скачан" in m for m in logs)

    (nrc_site / nrc.ARCHIVE_NAME).write_bytes(b"broken")  # оборванная загрузка — качаем заново
    nrc.install(log=logs.append)
    assert any("повреждён" in m for m in logs)


def test_install_can_be_cancelled(nrc_site):
    with pytest.raises(nrc.DownloadCancelled):
        nrc.install(cancelled=lambda: True, log=lambda _m: None)
    assert not list(nrc_site.glob("*"))               # ни архива, ни .part


def test_cli_download_nrc(nrc_site, capsys):
    from textanalyzer import cli

    assert cli.main(["download-nrc"]) == 0
    out = capsys.readouterr().out
    assert "некоммерческ" in out and "Готово." in out
    assert (nrc_site / "lexicon_ru.json").exists()


def test_frozen_app_keeps_nrc_in_user_folder(monkeypatch):
    import sys

    from textanalyzer import config

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert config.nrc_dir() == config.user_data_dir() / config.NRC_DIRNAME
    assert config.lexicon_path("nrc").is_relative_to(config.user_data_dir())
    monkeypatch.setattr(sys, "frozen", False)
    assert config.nrc_dir() == config.models_dir() / config.NRC_DIRNAME


@pytest.mark.skipif(not lexicon_path().exists(), reason="NRC EmoLex не скачан (scripts/download_nrc_lexicon.py)")
def test_downloaded_nrc_lexicon():
    lex = EmotionLexicon(lexicon_path(), lexicon_rules_path())
    assert len(lex) > 2000
    assert ("joy", 1.0) in lex.entries["радость"]
    assert any(e == "fear" for e, _ in lex.entries["страх"])
    assert "очень" not in lex.entries
    assert "Mohammad" in lex.meta["credit"]
