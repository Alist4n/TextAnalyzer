"""Выбор словаря эмоций: NRC EmoLex или ручной словарь TextAnalyzer (настройка lexicon, ключ --lexicon)."""

import json

import pytest

from textanalyzer import cli
from textanalyzer.config import LEXICONS, AnalysisOptions, lexicon_path, lexicon_rules_path, package_dir
from textanalyzer.nlp import pipeline
from textanalyzer.nlp.emotions import EmotionLexicon, LexiconUnavailableError
from textanalyzer.nlp.pipeline import Analyzer

TEXT = "Я очень рад тебя видеть."


def quiet(_message):
    pass


def test_manual_lexicon_is_bundled():
    path = lexicon_path("manual")
    assert path.is_relative_to(package_dir())  # входит в программу, скачивать не нужно
    lex = EmotionLexicon(path, lexicon_rules_path())
    assert lex.name == "Ручной словарь TextAnalyzer"
    assert len(lex) == 649
    assert "credit" not in lex.meta and lex.meta["description"]
    assert ("joy", 1.0) in lex.entries["рад"]
    assert lex.modifiers["очень"] > 1  # правила — общие, из lexicon_rules_ru.json


def test_default_lexicon_is_nrc():
    assert LEXICONS == ("nrc", "manual")
    assert AnalysisOptions().lexicon == "nrc"
    assert lexicon_path() == lexicon_path("nrc") != lexicon_path("manual")


def test_analyzer_switches_lexicon_between_runs(monkeypatch, test_lexicon):
    # «NRC» здесь — маленький тестовый словарь, чтобы не зависеть от скачивания
    monkeypatch.setattr(pipeline, "lexicon_path", lambda lexicon="nrc": test_lexicon if lexicon == "nrc" else lexicon_path(lexicon))
    analyzer = Analyzer(AnalysisOptions(emotion_method="lexicon", lexicon="manual"))
    corpus = analyzer.analyze_corpus([("t", TEXT, None)], log=quiet)
    assert {h.lemma for h in corpus.texts[0].sentences[0].lexicon_hits} == {"рад"}
    assert corpus.models["lexicon"] == "Ручной словарь TextAnalyzer, 649 слов"
    assert "Составлен вручную" in corpus.models["lexicon_note"]
    assert corpus.options["lexicon"] == "manual"

    analyzer.options = AnalysisOptions(emotion_method="lexicon", lexicon="nrc")  # так делает окно
    corpus = analyzer.analyze_corpus([("t", TEXT, None)], log=quiet)
    assert analyzer._lexicon.path == test_lexicon
    assert "Ручной" not in corpus.models["lexicon"]

    analyzer.options = AnalysisOptions(emotions=False)
    corpus = analyzer.analyze_corpus([("t", TEXT, None)], log=quiet)
    assert "lexicon" not in corpus.models  # словарь загружен, но в этом анализе не участвовал


def test_missing_nrc_suggests_manual_lexicon(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "lexicon_path", lambda lexicon="nrc": tmp_path / "нет.json")
    analyzer = Analyzer(AnalysisOptions(emotion_method="lexicon"))
    with pytest.raises(LexiconUnavailableError, match="--lexicon manual"):
        analyzer.ensure_loaded(log=quiet)


def test_cli_lexicon_key():
    parser = cli.build_parser()
    assert parser.parse_args(["analyze", "a.txt"]).lexicon is None  # по умолчанию — default_lexicon()
    assert parser.parse_args(["analyze", "a.txt", "--lexicon", "manual"]).lexicon == "manual"
    with pytest.raises(SystemExit):
        parser.parse_args(["analyze", "a.txt", "--lexicon", "other"])


def test_default_lexicon_follows_nrc_download(monkeypatch, tmp_path):
    from textanalyzer import config

    monkeypatch.setattr(config, "nrc_dir", lambda: tmp_path)
    assert config.default_lexicon() == "manual"   # только что полученная программа: NRC ещё нет
    (tmp_path / "lexicon_ru.json").write_text("{}", encoding="utf-8")
    assert config.default_lexicon() == "nrc"


def test_cli_falls_back_to_manual_without_nrc(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli, "default_lexicon", lambda: "manual")
    code = cli.main(["analyze", "--text", TEXT, "--emotions", "lexicon", "--formats", "json",
                     "-o", str(tmp_path), "--name", "r"])
    assert code == 0
    assert "используется ручной словарь" in capsys.readouterr().out
    data = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert data["options"]["lexicon"] == "manual"


def test_cli_manual_lexicon_report(tmp_path, capsys):
    from docx import Document

    code = cli.main(["analyze", "--text", TEXT, "--emotions", "lexicon", "--lexicon", "manual",
                     "--formats", "html,docx,json", "-o", str(tmp_path), "--name", "r"])
    assert code == 0, capsys.readouterr().err
    data = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert data["options"]["lexicon"] == "manual"
    assert data["texts"][0]["emotions"]["lexicon_dominant"] == "joy"
    html = (tmp_path / "r.html").read_text(encoding="utf-8")
    assert "Ручной словарь TextAnalyzer" in html and "Составлен вручную" in html
    assert "Mohammad" not in html  # благодарность NRC — только когда отчёт построен по NRC
    docx_text = "\n".join(p.text for p in Document(tmp_path / "r.docx").paragraphs)
    assert "Составлен вручную" in docx_text and "lexicon_note" not in docx_text
