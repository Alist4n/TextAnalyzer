"""Работа без интернета: в этих тестах любое сетевое подключение завершается ошибкой."""

import socket

import pytest

from textanalyzer.config import AnalysisOptions, emotion_model_source
from textanalyzer.nlp import emotions
from textanalyzer.nlp.pipeline import Analyzer
from textanalyzer.report import export


@pytest.fixture
def no_network(monkeypatch):
    attempts = []

    def blocked(*args, **kwargs):
        attempts.append(args[:1])
        raise OSError("сеть заблокирована тестом")

    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    return attempts


def test_analysis_and_reports_without_network(no_network, tmp_path, test_lexicon):
    analyzer = Analyzer(AnalysisOptions(emotion_method="lexicon"), lexicon_file=test_lexicon)
    corpus = analyzer.analyze_corpus([("t", "Как же я рад тебя видеть! Вчера было страшно.", None)], log=lambda _m: None)
    written = export(corpus, tmp_path, ["html", "docx", "json"], "r")
    assert set(written) == {"html", "docx", "json"}
    assert no_network == []


def test_missing_model_without_network_gives_clear_error(no_network):
    with pytest.raises(emotions.ModelUnavailableError, match="Только словарь"):
        emotions.EmotionModel("textanalyzer-test/no-such-model")


@pytest.mark.model
def test_local_model_loads_without_network(no_network):
    model = emotions.EmotionModel(emotion_model_source())
    assert model.predict(["Как же я рад тебя видеть!"])[0]["joy"] > 0.5
    assert no_network == []
