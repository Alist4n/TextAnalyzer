"""Окно программы: справка, подсказки, отказ от неподдерживаемых файлов. Без показа на экране."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")


@pytest.fixture(scope="module")
def mw(tmp_path_factory):
    try:
        import torch  # noqa: F401 — как в run_gui: до Qt
    except ImportError:
        pass
    from PySide6 import QtWebEngineWidgets  # noqa: F401 — до создания QApplication
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    # настройки — во временной папке, а не в %APPDATA% пользователя
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path_factory.mktemp("settings")))
    _app = QApplication.instance() or QApplication([])
    from textanalyzer.gui import main_window

    yield main_window


def test_first_run_opens_help_once(mw):
    first = mw.MainWindow()
    assert first.tabs.currentIndex() == mw.TAB_HELP
    text = first.help_view.toPlainText()
    for section in ("Какие файлы принимаются", "Требования к тексту", "Настройки анализа", "Отчёты"):
        assert section in text
    second = mw.MainWindow()
    assert second.tabs.currentIndex() == mw.TAB_TEXT


def test_controls_have_tooltips(mw):
    w = mw.MainWindow()
    for widget in (w.cb_morph, w.cb_syntax, w.cb_emotions, w.cb_entities, w.max_trees,
                   w.cb_html, w.cb_docx, w.cb_json, w.out_dir_edit, w.run_button):
        assert widget.toolTip(), widget
    assert ".docx" in w.editor.placeholderText()


def test_add_files_rejects_unsupported_with_reason(mw, tmp_path, monkeypatch):
    warnings = []
    monkeypatch.setattr(mw.QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    (tmp_path / "a.txt").write_bytes("Привет, мир.".encode("cp1251"))
    (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "empty.txt").write_text("   ", encoding="utf-8")

    w = mw.MainWindow()
    w.add_files([tmp_path / "a.txt", tmp_path / "b.pdf", tmp_path / "empty.txt"])

    assert w.text_list.count() == 1  # стартовый пустой «Текст 1» заменён файлом
    assert len(w.text_list.selectedItems()) == 1
    item = w.text_list.item(0)
    assert item.text() == "a"
    assert "Windows-1251" in item.toolTip()
    assert len(warnings) == 1
    assert "b.pdf — PDF не поддерживается" in warnings[0]
    assert "empty.txt — в файле нет текста" in warnings[0]


def test_adding_many_files_selects_only_last(mw, tmp_path):
    for k in range(3):
        (tmp_path / f"{k}.txt").write_text("Текст.", encoding="utf-8")
    w = mw.MainWindow()
    w.add_files([tmp_path])
    assert w.text_list.count() == 3
    assert [i.text() for i in w.text_list.selectedItems()] == ["2"]


def test_several_texts_in_one_file(mw, tmp_path):
    (tmp_path / "отзывы.txt").write_text("=== Первый\nХорошо.\n=== Второй\nПлохо.\n===\nСредне.", encoding="utf-8")
    w = mw.MainWindow()
    w.add_files([tmp_path / "отзывы.txt"])
    item = w.text_list.item(0)
    assert item.text() == "отзывы  ·  текстов: 3"
    assert "текстов для анализа: 3" in w.list_info.text()
    assert [name for name, _, _ in w.collect_items()] == ["Первый", "Второй", "отзывы — 3"]

    w.separator_edit.setText("###")          # другой разделитель — файл снова один текст
    assert item.text() == "отзывы"
    w.separator_edit.setText("===")
    w.split_cb.setChecked(False)              # деление выключено
    assert item.text() == "отзывы"
    assert len(w.collect_items()) == 1


def test_table_import(mw, tmp_path, monkeypatch):
    from textanalyzer.tables import guess_spec

    asked = []

    def fake_ask(self, table, spec, position="", remaining=0):
        asked.append(table.path.name)
        return table, guess_spec(table), True  # «применить к остальным таблицам»

    monkeypatch.setattr(mw.MainWindow, "_ask_table_spec", fake_ask)
    (tmp_path / "a.csv").write_text("Товар;Отзыв\nЧайник;Отличный чайник, рекомендую.\nУтюг;Сломался через день.\n",
                                    encoding="utf-8")
    (tmp_path / "b.csv").write_text("Отзыв;Товар\nНормально, без претензий.;Миксер\n", encoding="utf-8")
    w = mw.MainWindow()
    width_before = w.minimumSizeHint().width()
    w.add_files([tmp_path])

    assert asked == ["a.csv"]  # для b.csv выбор применён по заголовкам, без окна
    assert [w.text_list.item(i).text() for i in range(2)] == ["a  ·  текстов: 2 (таблица)", "b  ·  текстов: 1 (таблица)"]
    items = w.collect_items()
    assert [name for name, _, _ in items] == ["Чайник", "Утюг", "Миксер"]
    assert items[1][2].endswith("a.csv, строка 3")
    assert "текстов для анализа: 3" in w.list_info.text()

    w.text_list.setCurrentRow(0)
    assert w.editor.isReadOnly() and w.columns_button.isVisibleTo(w)
    # длинное описание таблицы под редактором переносится и не распирает окно
    assert w.minimumSizeHint().width() <= width_before + 120
    assert "Отличный чайник" in w.editor.toPlainText()
    w.text_list.setCurrentRow(1)
    w._on_remove_selected()
    assert len(w._tables) == 1


def test_lexicon_choice(mw, monkeypatch):
    w = mw.MainWindow()
    combo = w.lexicon_combo
    assert combo.toolTip() and "Словарь эмоций" in w.help_view.toPlainText()
    assert [combo.itemData(i) for i in range(combo.count())] == ["nrc", "manual"]

    w.emotion_method.setCurrentIndex(w.emotion_method.findData("model"))
    assert not combo.isEnabled()                 # нейросети словарь не нужен
    w.emotion_method.setCurrentIndex(w.emotion_method.findData("both"))
    assert combo.isEnabled()
    w.cb_emotions.setChecked(False)
    assert not combo.isEnabled()
    w.cb_emotions.setChecked(True)

    combo.setCurrentIndex(combo.findData("manual"))
    assert w.current_options().lexicon == "manual"
    w._save_settings()
    assert mw.MainWindow().lexicon_combo.currentData() == "manual"  # выбор запоминается
    combo.setCurrentIndex(combo.findData("nrc"))
    w._save_settings()

    monkeypatch.setattr(mw, "lexicon_path", lambda lexicon="nrc": mw.Path("нет-такого-словаря.json"))
    missing = mw.MainWindow().lexicon_combo
    assert missing.itemText(missing.findData("nrc")) == "NRC EmoLex — не скачан"

    # выбора ещё не было, NRC не скачан (программу только что получили) — ручной словарь
    w.settings.remove("lexicon")
    monkeypatch.setattr(mw, "default_lexicon", lambda: "manual")
    assert mw.MainWindow().lexicon_combo.currentData() == "manual"


def test_nrc_download_worker(mw, monkeypatch):
    from textanalyzer.gui.worker import NrcDownloadWorker
    from textanalyzer.nlp import nrc

    def fake_install(force, progress, log, cancelled):
        progress(10, 20)
        log("Сборка русского словаря…")
        return {"emotional_lemmas": 5}

    monkeypatch.setattr(nrc, "install", fake_install)
    worker = NrcDownloadWorker()
    got = []
    worker.progress.connect(lambda d, t: got.append((d, t)))
    worker.finished.connect(lambda stats: got.append(stats))
    worker.run()                                   # синхронно, без потока
    assert got == [(10, 20), {"emotional_lemmas": 5}]

    def offline(*_args):
        raise OSError("нет сети")

    monkeypatch.setattr(nrc, "install", offline)
    failed = []
    worker.failed.connect(failed.append)
    worker.run()
    assert "нет сети" in failed[0] and "интернет" in failed[0]


def test_missing_nrc_offers_download(mw, monkeypatch):
    calls = []
    monkeypatch.setattr(mw.QMessageBox, "question", lambda *args: mw.QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(mw.MainWindow, "download_nrc", lambda self, ask=True: calls.append(ask))
    w = mw.MainWindow()
    w._on_failed(mw.LEXICON_MISSING_MESSAGE)
    assert calls == [False]                        # условия NRC уже были в сообщении
    file_menu = w.menuBar().actions()[0].menu()
    assert any("NRC EmoLex" in a.text() for a in file_menu.actions())


def test_help_anchor_navigation(mw):
    w = mw.MainWindow()
    w.show_help("files")
    assert w.tabs.currentIndex() == mw.TAB_HELP


def test_error_message_shown_in_full_or_last_traceback_line(mw, monkeypatch):
    from textanalyzer.nlp.emotions import MODEL_MISSING_MESSAGE

    shown = []
    monkeypatch.setattr(mw.QMessageBox, "critical", lambda *args: shown.append(args[2]))
    w = mw.MainWindow()
    w._on_failed(MODEL_MISSING_MESSAGE)
    assert MODEL_MISSING_MESSAGE in shown[-1]
    w._on_failed('Traceback (most recent call last):\n  File "x.py", line 1\nValueError: плохо')
    assert shown[-1].endswith("ValueError: плохо") and "File" not in shown[-1]
