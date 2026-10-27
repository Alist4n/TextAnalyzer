"""Интеграционные тесты анализа: нужна модель spaCy ru_core_news_md."""

import json

import pytest

from textanalyzer.config import AnalysisOptions
from textanalyzer.nlp.pipeline import Analyzer
from textanalyzer.report import export


@pytest.fixture(scope="module")
def analyzer(test_lexicon):
    a = Analyzer(AnalysisOptions(emotion_method="lexicon"), lexicon_file=test_lexicon)
    a.ensure_loaded(log=lambda _m: None)
    return a


def sentence(analyzer, text):
    result = analyzer.analyze_text("t", text)
    assert len(result.sentences) == 1, [s.text for s in result.sentences]
    return result.sentences[0]


def lexicon_hits(analyzer, text):
    return {h.lemma: h for h in sentence(analyzer, text).lexicon_hits}


# --- токенизация и морфология -------------------------------------------------

def test_hyphenated_words_are_single_tokens(analyzer):
    s = sentence(analyzer, "Где-то вдали крепко-крепко спал кто-нибудь.")
    words = [t.text for t in s.tokens if not t.is_punct]
    assert "Где-то" in words and "крепко-крепко" in words and "кто-нибудь" in words


def test_lemma_fixed_by_pymorphy(analyzer):
    s = sentence(analyzer, "Ты не представляешь, как я рада!")
    lemmas = {t.text: t.lemma for t in s.tokens}
    assert lemmas["представляешь"] == "представлять"


# --- синтаксис ---------------------------------------------------------------

@pytest.mark.parametrize(
    "text, structure",
    [
        ("Он пришёл домой, и она обрадовалась.", "сложносочинённое"),
        ("Я знаю, что ты придёшь.", "сложноподчинённое"),
        ("Мальчик читал книгу.", "простое"),
    ],
)
def test_sentence_structure(analyzer, text, structure):
    assert sentence(analyzer, text).structure == structure


@pytest.mark.parametrize(
    "text, purpose",
    [
        ("Ты придёшь завтра?", "вопросительное"),
        ("Приходи завтра пораньше!", "побудительное"),
        ("Давайте начнём урок.", "побудительное"),
        ("Он пришёл вчера.", "повествовательное"),
        ("Мой брат приехал вечером.", "повествовательное"),
    ],
)
def test_purpose(analyzer, text, purpose):
    assert sentence(analyzer, text).purpose == purpose


def test_grammatical_basis(analyzer):
    s = sentence(analyzer, "Старый рыбак медленно чинил сеть.")
    assert s.bases == [["рыбак", "чинил"]]
    assert s.composition == "двусоставное"


def test_nominative_sentence(analyzer):
    s = sentence(analyzer, "Тихая летняя ночь.")
    assert s.composition == "односоставное (назывное)"


def test_participial_and_adverbial_phrases(analyzer):
    s = sentence(analyzer, "Мальчик, читающий книгу, улыбнулся, подняв голову.")
    assert any("читающий книгу" in p for p in s.participial)
    assert any("подняв голову" in p for p in s.adverbial)


def test_tree_depth_is_finite(analyzer):
    s = sentence(analyzer, "Я весь вечер смеялась и не могла поверить своему счастью.")
    assert 1 <= s.depth < 10


# --- словарь эмоций ----------------------------------------------------------

def test_negation_cancels_emotion(analyzer):
    hit = lexicon_hits(analyzer, "Но я совсем не боюсь трудностей.")["бояться"]
    assert hit.negated and hit.weight == 0


def test_negation_through_experience_verb(analyzer):
    assert lexicon_hits(analyzer, "Я не испытываю никакого страха.")["страх"].negated


def test_negated_verb_does_not_cancel_object_emotion(analyzer):
    hit = lexicon_hits(analyzer, "Я никогда не встречал такого хамства!")["хамство"]
    assert not hit.negated and hit.weight > 0


def test_intensifier(analyzer):
    hit = lexicon_hits(analyzer, "Я очень рад тебя видеть.")["рад"]
    assert hit.modifier == "очень" and hit.weight > 1


def test_intensifier_word_is_not_counted_as_emotion(analyzer):
    hits = lexicon_hits(analyzer, "Я страшно рад тебя видеть.")
    assert "рад" in hits
    assert all(h.emotion != "fear" for h in hits.values())


def test_degree_word_is_not_emotion(analyzer):
    # «ужасно» есть в словаре (грусть), но здесь это усилитель при глаголе
    assert "ужасно" not in lexicon_hits(analyzer, "Я ужасно устал.")


def test_no_wordform_false_positive(analyzer):
    # «вина» здесь — форма слова «вино», а не «вина» (чувство вины)
    assert "вино" not in lexicon_hits(analyzer, "Папа достал старую бутылку вина.")


# --- сущности ----------------------------------------------------------------

def test_entity_normalized_to_nominative(analyzer):
    result = analyzer.analyze_text("t", "Вчера я долго говорил с Ириной Соколовой о Новосибирске.")
    names = {e.text for e in result.entities}
    assert "Ирина Соколова" in names
    assert "Новосибирск" in names


# --- отчёты ------------------------------------------------------------------

def test_export_all_formats(analyzer, tmp_path):
    corpus = analyzer.analyze_corpus(
        [("Радость", "Как я рада! Мы весь вечер смеялись.", None), ("Тревога", "Мне страшно. Где-то завыла сирена.", None)],
        log=lambda _m: None,
    )
    written = export(corpus, tmp_path, ["html", "docx", "json"], "r")
    assert set(written) == {"html", "docx", "json"}
    html = written["html"].read_text(encoding="utf-8")
    assert "Радость" in html and "<svg" in html
    assert "удобочитаем" not in html.lower()                # показатель убран из отчёта
    data = json.loads(written["json"].read_text(encoding="utf-8"))
    assert len(data["texts"]) == 2
    assert "readability" not in data["texts"][0]["stats"]
    assert data["texts"][0]["emotions"]["lexicon_dominant"] == "joy"
    assert written["docx"].stat().st_size > 10_000


def test_many_texts_compact_report(analyzer, tmp_path):
    analyzer.options.detailed_texts = 2
    try:
        corpus = analyzer.analyze_corpus(
            [(f"Отзыв {k}", f"Я очень рад покупке номер {k}. Всё работает.", None) for k in range(5)],
            log=lambda _m: None,
        )
    finally:
        analyzer.options.detailed_texts = 30
    written = export(corpus, tmp_path, ["html", "docx"], "r")
    html = written["html"].read_text(encoding="utf-8")
    assert html.count('<details class="box text"') == 2      # подробные разделы — только первые два
    assert html.count('<details class="compact"') == 3       # остальные — компактно
    assert 'id="overview"' in html and "Тексты по ведущей эмоции" in html
    assert "matplotlib" not in html                          # графики HTML без matplotlib
    import docx

    headings = [p.text for p in docx.Document(str(written["docx"])).paragraphs if p.style.name.startswith("Heading")]
    assert "Все тексты вместе" in headings
    assert "3. Отзыв 2" not in headings and "2. Отзыв 1" in headings


def test_report_sections_are_collapsible(analyzer, tmp_path):
    corpus = analyzer.analyze_corpus(
        [("Первый", "Я рад. Всё хорошо.", None), ("Второй", "Мне страшно.", None)], log=lambda _m: None
    )
    html = export(corpus, tmp_path, ["html"], "r")["html"].read_text(encoding="utf-8")
    # крупные разделы и подразделы — <details>, по умолчанию раскрыты
    for section_id in ("summary", "overview", "text-1", "text-2"):
        assert f'id="{section_id}" open' in html
    for title in ("Общие показатели", "Эмоции", "Морфология", "Синтаксис", "Предложения"):
        assert html.count(f"<summary><h3>{title}</h3>") == 2
    assert '<details class="sub" id="glossary">' in html     # справочник обозначений свёрнут
    for action in ("expand", "collapse", "collapse-sub"):
        assert f'data-toggle="{action}"' in html
    assert "beforeprint" in html


@pytest.mark.model
def test_emotion_model_profile(tmp_path):
    a = Analyzer(AnalysisOptions(emotion_method="model", syntax=False, entities=False))
    result = a.analyze_corpus([("t", "Меня это просто бесит! Сколько можно обманывать людей!", None)], log=lambda _m: None)
    emotions = result.texts[0].emotions
    assert emotions.leading_emotion == "anger"
