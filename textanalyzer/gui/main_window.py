"""Главное окно: список текстов, редактор, настройки анализа, предпросмотр отчёта."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, QSettings, Qt, QThread, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QProgressDialog,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..config import (
    APP_NAME,
    NRC_HOME,
    AnalysisOptions,
    default_lexicon,
    default_output_dir,
    lexicon_path,
    nrc_dir,
)
from ..loaders import (
    DEFAULT_SEPARATOR,
    SUPPORTED_LIST,
    UnsupportedFileError,
    collect_files,
    is_table,
    load_file,
    split_items,
    split_texts,
    unsupported_reason,
)
from ..nlp.emotions import LEXICON_MISSING_MESSAGE
from ..nlp.pipeline import Analyzer
from ..tables import Table, TableSpec, describe_spec, guess_spec, read_table, reuse_spec, table_items, table_texts
from .help import HELP_HTML
from .table_dialog import TableImportDialog
from .worker import AnalysisWorker, NrcDownloadWorker

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
except ImportError:  # без WebEngine показываем отчёт ссылкой на браузер
    QWebEngineView = None

ITEM_ROLE = Qt.ItemDataRole.UserRole
EMOTION_METHOD_LABELS = [
    ("both", "Нейросеть + словарь",
     "Нейросеть оценивает предложения, словарь показывает, какие слова выражают эмоцию (рекомендуется)"),
    ("model", "Только нейросеть", "Оценка нейросетью без подсветки эмоциональных слов"),
    ("lexicon", "Только словарь",
     "Быстрее и полностью объяснимо, но не понимает контекст и иронию; нейросеть не загружается"),
]
LEXICON_LABELS = [
    ("nrc", "NRC EmoLex",
     "Связи 14 тыс. английских слов с эмоциями (Mohammad, Turney, NRC Canada) в машинном переводе:\n"
     "около 2400 русских лемм. Находит больше слов, но и больше случайных связей («дерево» — радость).\n"
     "Скачивается отдельно, только для некоммерческого использования."),
    ("manual", "Ручной (TextAnalyzer)",
     "649 лемм, отобранных вручную: только слова, которые явно выражают эмоцию.\n"
     "Охват меньше, зато почти без шума. Входит в программу."),
]
FILE_FILTER = (
    "Поддерживаемые файлы (*.txt *.text *.md *.docx *.csv *.tsv *.xlsx *.xlsm);;"
    "Обычный текст (*.txt *.text);;Markdown (*.md);;Документ Word (*.docx);;"
    "Таблицы CSV и Excel (*.csv *.tsv *.xlsx *.xlsm)"
)
TAB_TEXT, TAB_REPORT, TAB_LOG, TAB_HELP = range(4)
TABLE_PREVIEW_TEXTS = 200  # сколько текстов таблицы показывать в редакторе


@dataclass
class TableSource:
    """Таблица в списке текстов: каждая непустая строка выбранного столбца — отдельный текст."""
    table: Table
    spec: TableSpec
    texts: list[tuple[int, str | None, str]]

    def describe(self) -> str:
        return f"{self.table.describe()}; {describe_spec(self.table, self.spec)}"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — морфологический, синтаксический и эмоциональный анализ")
        self.resize(1320, 820)
        self.setAcceptDrops(True)

        # INI-файл в %APPDATA%\TextAnalyzer: его легко найти и сбросить, а тесты подменяют путь через QSettings.setPath
        self.settings = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, APP_NAME, APP_NAME)
        self.analyzer = Analyzer()
        self.analysis_thread: QThread | None = None
        self.worker: AnalysisWorker | None = None
        self.nrc_thread: QThread | None = None
        self.nrc_worker: NrcDownloadWorker | None = None
        self.last_report: Path | None = None
        self.last_out_dir: Path | None = None
        self._loading_item = False
        self._counter = 0
        # таблицы хранятся отдельно: в данных элемента списка — только их номер
        self._tables: dict[int, TableSource] = {}
        self._next_table_id = 1

        self._build_ui()
        self._build_menu()
        self._restore_settings()
        self.add_text_item(self._next_name(), "", None)
        # при первом запуске сразу показываем справку
        if not self.settings.value("help_seen", False, type=bool):
            self.show_help()
            self.settings.setValue("help_seen", True)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_center())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([260, 760, 300])
        self.setCentralWidget(splitter)
        self.statusBar().showMessage("Добавьте тексты: вставьте в редактор, откройте файлы или перетащите их в окно")

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 4, 8)
        title = QLabel("Тексты")
        title.setStyleSheet("font-weight: 600; font-size: 14px;")
        layout.addWidget(title)

        hint = QLabel(
            f"Файлы <b>{SUPPORTED_LIST}</b>. Можно перетащить файлы или папку в окно. "
            "В таблицах каждая строка — отдельный текст; в текстовых файлах тексты "
            "разделяются строкой-разделителем. <a href='files'>Какие файлы подходят?</a>"
        )
        hint.setWordWrap(True)
        hint.setTextFormat(Qt.TextFormat.RichText)
        hint.linkActivated.connect(self.show_help)
        hint.setStyleSheet("color: palette(placeholder-text);")
        layout.addWidget(hint)

        self.text_list = QListWidget()
        self.text_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.text_list.setToolTip(
            "Тексты для анализа. Выберите текст, чтобы посмотреть или поправить его.\n"
            "Каждый текст анализируется отдельно; пустые тексты пропускаются."
        )
        self.text_list.currentItemChanged.connect(self._on_current_item_changed)
        layout.addWidget(self.text_list, 1)
        QShortcut(QKeySequence.StandardKey.Delete, self.text_list, self._on_remove_selected)

        buttons = [
            ("Новый", "Создать пустой текст, чтобы ввести или вставить его в редактор (Ctrl+N)", self._on_new_text),
            ("Файлы…", f"Добавить файлы {SUPPORTED_LIST} (Ctrl+O).\n"
                       "Каждый файл — отдельный текст; в таблицах CSV и Excel — каждая строка.", self._on_add_files),
            ("Папка…", f"Добавить все файлы {SUPPORTED_LIST} из папки и её подпапок", self._on_add_folder),
            ("Удалить", "Убрать выбранные тексты из списка (Delete).\nФайлы на диске не удаляются.", self._on_remove_selected),
        ]
        row = QHBoxLayout()
        for label, tip, slot in buttons:
            b = QToolButton()
            b.setText(label)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            row.addWidget(b)
        layout.addLayout(row)

        split_tip = (
            "Строка, которая начинается с разделителя, начинает новый текст;\n"
            "слова после разделителя станут названием текста в отчёте:\n\n"
            f"    {DEFAULT_SEPARATOR} Отзыв 1\n    Текст первого отзыва…\n"
            f"    {DEFAULT_SEPARATOR} Отзыв 2\n    Текст второго…\n\n"
            "Работает для файлов и для текста в редакторе. Файлы без разделителей\n"
            "остаются одним текстом. В списке видно, на сколько текстов разделится элемент."
        )
        self.split_cb = QCheckBox("Несколько текстов в одном файле")
        self.split_cb.setChecked(True)
        self.split_cb.setToolTip(split_tip)
        layout.addWidget(self.split_cb)
        sep_row = QHBoxLayout()
        sep_label = QLabel("Разделитель:")
        sep_label.setToolTip(split_tip)
        sep_row.addWidget(sep_label)
        self.separator_edit = QLineEdit(DEFAULT_SEPARATOR)
        self.separator_edit.setToolTip(
            split_tip + "\n\nРазделитель можно заменить, например на *** или ###.\n"
            "Выбирайте то, что не встречается в начале обычных строк текста."
        )
        sep_row.addWidget(self.separator_edit, 1)
        help_link = QLabel("<a href='multi'>Как это работает?</a>")
        help_link.linkActivated.connect(self.show_help)
        sep_row.addWidget(help_link)
        layout.addLayout(sep_row)
        self.split_cb.toggled.connect(self.separator_edit.setEnabled)
        self.split_cb.toggled.connect(self._refresh_labels)
        self.separator_edit.textChanged.connect(self._refresh_labels)

        self.list_info = QLabel()
        self.list_info.setStyleSheet("color: palette(placeholder-text);")
        layout.addWidget(self.list_info)
        return panel

    def _build_center(self) -> QWidget:
        self.tabs = QTabWidget()

        editor_page = QWidget()
        v = QVBoxLayout(editor_page)
        v.setContentsMargins(6, 6, 6, 6)
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Название:"))
        self.name_edit = QLineEdit()
        self.name_edit.setToolTip("Название текста в отчёте. Для файла — имя файла без расширения.")
        self.name_edit.textEdited.connect(self._on_name_edited)
        name_row.addWidget(self.name_edit, 1)
        self.columns_button = QPushButton("Столбцы…")
        self.columns_button.setToolTip("Выбрать другой лист, столбец с текстом или столбец с названием")
        self.columns_button.clicked.connect(self._on_change_columns)
        self.columns_button.setVisible(False)
        name_row.addWidget(self.columns_button)
        v.addLayout(name_row)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText(
            "Вставьте (Ctrl+V) или введите текст на русском языке.\n\n"
            f"Или добавьте файлы {SUPPORTED_LIST} кнопками слева либо перетащите их в окно — "
            "каждый файл станет отдельным текстом, а в таблицах CSV и Excel — каждая строка "
            "(столбцы с текстом и названием выбираются при добавлении). Несколько текстов "
            "анализируются вместе и сравниваются в общем отчёте.\n\n"
            f"Чтобы вставить сразу несколько текстов, начните каждый со строки «{DEFAULT_SEPARATOR} Название» — "
            "так же можно оформить и файл.\n\n"
            "Перевод строки считается границей предложения: если текст скопирован из PDF "
            "и предложения разорваны переносами, соедините строки.\n\n"
            "Подробнее — вкладка «Справка» (F1)."
        )
        font = QFont("Segoe UI", 11)
        self.editor.setFont(font)
        self.editor.textChanged.connect(self._on_editor_changed)
        v.addWidget(self.editor, 1)
        self.editor_info = QLabel()
        # без переноса длинное описание таблицы растягивает всё окно по ширине
        self.editor_info.setWordWrap(True)
        self.editor_info.setStyleSheet("color: palette(placeholder-text);")
        v.addWidget(self.editor_info)
        self.tabs.addTab(editor_page, "Текст")

        if QWebEngineView is not None:
            self.report_view = QWebEngineView()
            self.report_view.setHtml(self._placeholder_html())
        else:
            self.report_view = QTextBrowser()
            self.report_view.setOpenExternalLinks(True)
            self.report_view.setHtml(self._placeholder_html())
        self.tabs.addTab(self.report_view, "Отчёт")

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Consolas", 9))
        self.tabs.addTab(self.log_view, "Журнал")

        self.help_view = QTextBrowser()
        self.help_view.setOpenLinks(False)  # якоря обрабатываем сами, внешние ссылки — в браузер
        self.help_view.anchorClicked.connect(self._on_help_link)
        self.help_view.document().setDefaultStyleSheet(
            "h2, h3 { margin-top: 14px; } td, th { vertical-align: top; } "
            "pre { font-family: Consolas, 'Courier New', monospace; margin-left: 16px; }"
        )
        self.help_view.setHtml(HELP_HTML)
        self.help_view.setFont(QFont("Segoe UI", 10))
        self.tabs.addTab(self.help_view, "Справка")

        self.tabs.setTabToolTip(TAB_TEXT, "Название и содержимое выбранного текста")
        self.tabs.setTabToolTip(TAB_REPORT, "Результат последнего анализа")
        self.tabs.setTabToolTip(TAB_LOG, "Ход работы, пути к сохранённым отчётам, описание ошибок")
        self.tabs.setTabToolTip(TAB_HELP, "Как пользоваться программой и какие файлы она принимает (F1)")
        return self.tabs

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 8, 8, 8)

        analysis = QGroupBox("Анализ")
        form = QFormLayout(analysis)
        self.cb_morph = QCheckBox("Морфология")
        self.cb_morph.setToolTip(
            "Части речи (причастие и деепричастие — отдельно), падеж, время, вид и другие признаки,\n"
            "частотный словарь, слова вне словаря, таблица разбора каждого слова"
        )
        self.cb_syntax = QCheckBox("Синтаксис")
        self.cb_syntax.setToolTip(
            "Грамматические основы, тип предложения по цели и по строению,\n"
            "причастные и деепричастные обороты, однородные члены, деревья зависимостей"
        )
        self.cb_emotions = QCheckBox("Эмоции")
        self.cb_emotions.setToolTip(
            "Радость, грусть, удивление, страх, гнев — для всего текста и каждого предложения,\n"
            "динамика по ходу текста, эмоциональные слова"
        )
        self.cb_entities = QCheckBox("Именованные сущности")
        self.cb_entities.setToolTip("Упоминания людей, мест и организаций (в именительном падеже)")
        for cb in (self.cb_morph, self.cb_syntax, self.cb_emotions, self.cb_entities):
            cb.setChecked(True)
            form.addRow(cb)
        self.emotion_method = QComboBox()
        for key, label, tip in EMOTION_METHOD_LABELS:
            self.emotion_method.addItem(label, key)
            self.emotion_method.setItemData(self.emotion_method.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
        self.emotion_method.setToolTip("Как определять эмоции. Наведите курсор на вариант в списке, чтобы увидеть разницу.")
        form.addRow("Метод эмоций:", self.emotion_method)
        self.lexicon_combo = QComboBox()
        for key, label, _tip in LEXICON_LABELS:
            self.lexicon_combo.addItem(label, key)
        self._refresh_lexicon_labels()
        self.lexicon_combo.setToolTip(
            "Каким словарём искать эмоциональные слова (методы со словарём).\n"
            "Наведите курсор на вариант в списке, чтобы увидеть разницу."
        )
        form.addRow("Словарь эмоций:", self.lexicon_combo)
        self.cb_emotions.toggled.connect(self._update_emotion_controls)
        self.emotion_method.currentIndexChanged.connect(self._update_emotion_controls)
        self.max_trees = QSpinBox()
        self.max_trees.setRange(0, 10_000)
        self.max_trees.setValue(AnalysisOptions.max_trees)
        self.max_trees.setToolTip(
            "Сколько деревьев зависимостей рисовать в HTML-отчёте для каждого текста (0 — не рисовать).\n"
            "Для больших текстов деревья сильно увеличивают размер отчёта."
        )
        form.addRow("Деревьев на текст:", self.max_trees)
        layout.addWidget(analysis)

        report = QGroupBox("Отчёт")
        rv = QVBoxLayout(report)
        fmt_row = QHBoxLayout()
        self.cb_html = QCheckBox("HTML")
        self.cb_html.setToolTip(
            "Основной отчёт: графики, подсветка эмоциональных слов, деревья зависимостей.\n"
            "Открывается в программе и в любом браузере."
        )
        self.cb_docx = QCheckBox("DOCX")
        self.cb_docx.setToolTip(
            "Документ Word для печати и правки. Без деревьев зависимостей;\n"
            "разбор — первые 400 слов, предложения — первые 300."
        )
        self.cb_json = QCheckBox("JSON")
        self.cb_json.setToolTip("Все результаты полностью, в машиночитаемом виде — для Python, Excel (Power Query) и т. п.")
        for cb in (self.cb_html, self.cb_docx, self.cb_json):
            cb.setChecked(True)
            fmt_row.addWidget(cb)
        rv.addLayout(fmt_row)
        detail_row = QHBoxLayout()
        detail_label = QLabel("Подробных разделов:")
        self.detailed_texts = QSpinBox()
        self.detailed_texts.setRange(0, 100_000)
        self.detailed_texts.setValue(AnalysisOptions.detailed_texts)
        detail_tip = (
            "Для скольких первых текстов строить подробные разделы с графиками, таблицами и деревьями.\n"
            "Остальные тексты в HTML показываются компактно (разбор предложений), в DOCX — только в сводной\n"
            "таблице. Нужна при анализе больших таблиц: сотни подробных разделов делают отчёт огромным.\n"
            "В JSON всегда попадает всё."
        )
        detail_label.setToolTip(detail_tip)
        self.detailed_texts.setToolTip(detail_tip)
        detail_row.addWidget(detail_label)
        detail_row.addWidget(self.detailed_texts, 1)
        rv.addLayout(detail_row)
        rv.addWidget(QLabel("Папка для отчётов:"))
        dir_row = QHBoxLayout()
        self.out_dir_edit = QLineEdit(str(default_output_dir()))
        self.out_dir_edit.setToolTip(
            "Куда сохранять отчёты. Имена файлов: report_ГГГГ-ММ-ДД_ЧЧ-ММ-СС.html / .docx / .json —\n"
            "старые отчёты не перезаписываются. Если не выбран ни один формат, отчёт только показывается."
        )
        dir_row.addWidget(self.out_dir_edit, 1)
        browse = QToolButton()
        browse.setText("…")
        browse.setToolTip("Выбрать папку для отчётов")
        browse.clicked.connect(self._on_choose_out_dir)
        dir_row.addWidget(browse)
        rv.addLayout(dir_row)
        layout.addWidget(report)

        self.run_button = QPushButton("Анализировать")
        self.run_button.setMinimumHeight(40)
        self.run_button.setStyleSheet("font-weight: 600; font-size: 14px;")
        self.run_button.setToolTip(
            "Проанализировать все непустые тексты из списка (F5).\n"
            "Первый запуск дольше (~15 с): загружаются языковые модели."
        )
        self.run_button.clicked.connect(self.start_analysis)
        layout.addWidget(self.run_button)

        self.cancel_button = QPushButton("Отмена")
        self.cancel_button.setToolTip("Прервать анализ; отчёт не будет создан")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._on_cancel)
        layout.addWidget(self.cancel_button)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.progress_label = QLabel()
        self.progress_label.setWordWrap(True)
        self.progress_label.setStyleSheet("color: #555;")
        layout.addWidget(self.progress_label)

        self.open_browser_button = QPushButton("Открыть отчёт в браузере")
        self.open_browser_button.setEnabled(False)
        self.open_browser_button.setToolTip("Открыть последний отчёт в браузере по умолчанию")
        self.open_browser_button.clicked.connect(self._on_open_in_browser)
        layout.addWidget(self.open_browser_button)
        self.open_folder_button = QPushButton("Открыть папку с отчётами")
        self.open_folder_button.setToolTip("Открыть в Проводнике папку, куда сохраняются отчёты")
        self.open_folder_button.clicked.connect(self._on_open_folder)
        layout.addWidget(self.open_folder_button)

        layout.addStretch(1)
        return panel

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("&Файл")
        actions = [
            ("Новый текст", QKeySequence.StandardKey.New, self._on_new_text),
            ("Добавить файлы…", QKeySequence.StandardKey.Open, self._on_add_files),
            ("Добавить папку…", None, self._on_add_folder),
            (None, None, None),
            ("Анализировать", QKeySequence("F5"), self.start_analysis),
            (None, None, None),
            ("Скачать словарь NRC EmoLex…", None, lambda: self.download_nrc()),
            (None, None, None),
            ("Выход", QKeySequence.StandardKey.Quit, self.close),
        ]
        for label, shortcut, slot in actions:
            if label is None:
                menu.addSeparator()
                continue
            act = QAction(label, self)
            if shortcut is not None:
                act.setShortcut(shortcut)
            act.triggered.connect(slot)
            menu.addAction(act)
        help_menu = self.menuBar().addMenu("&Справка")
        help_actions = [
            ("Как пользоваться", QKeySequence.StandardKey.HelpContents, lambda: self.show_help()),
            ("Какие файлы принимаются", None, lambda: self.show_help("files")),
            ("Настройки анализа", None, lambda: self.show_help("settings")),
            ("Отчёты и как их читать", None, lambda: self.show_help("reports")),
            (None, None, None),
            ("О программе", None, self._on_about),
        ]
        for label, shortcut, slot in help_actions:
            if label is None:
                help_menu.addSeparator()
                continue
            act = QAction(label, self)
            if shortcut is not None:
                act.setShortcut(shortcut)
            act.triggered.connect(slot)
            help_menu.addAction(act)

    @staticmethod
    def _placeholder_html() -> str:
        return (
            "<html><body style='font-family:Segoe UI,sans-serif;color:#667;padding:40px;line-height:1.5'>"
            "<h2 style='color:#334'>Отчёт появится здесь</h2>"
            "<ol>"
            f"<li>Добавьте тексты слева: вставьте текст в редактор на вкладке «Текст» или откройте файлы {SUPPORTED_LIST}.</li>"
            "<li>Справа выберите, что анализировать и в каких форматах сохранить отчёт.</li>"
            "<li>Нажмите «Анализировать» (F5).</li>"
            "</ol>"
            "<p>Подробная инструкция и список поддерживаемых файлов — на вкладке «Справка» (F1).</p>"
            "</body></html>"
        )

    def show_help(self, anchor: str | None = None) -> None:
        self.tabs.setCurrentIndex(TAB_HELP)
        if anchor:
            self.help_view.scrollToAnchor(anchor)
        else:
            self.help_view.verticalScrollBar().setValue(0)

    def _on_help_link(self, url: QUrl) -> None:
        if url.scheme() in ("http", "https", "file"):
            QDesktopServices.openUrl(url)
        else:
            self.help_view.scrollToAnchor(url.fragment() or url.toString().lstrip("#"))

    # ------------------------------------------------------------ тексты
    def _next_name(self) -> str:
        self._counter += 1
        return f"Текст {self._counter}"

    def current_separator(self) -> str | None:
        sep = self.separator_edit.text().strip()
        return sep if self.split_cb.isChecked() and sep else None

    def parts_count(self, text: str) -> int:
        """На сколько текстов разделится элемент списка при анализе."""
        if not text.strip():
            return 0
        return len(split_texts(text, self.current_separator()))

    def table_of(self, data: dict) -> TableSource | None:
        table_id = data.get("table_id")
        return self._tables.get(table_id) if table_id else None

    def item_count(self, data: dict) -> int:
        """Сколько текстов даст элемент списка: строки таблицы или части по разделителю."""
        source = self.table_of(data)
        if source is not None:
            return len(source.texts)
        return self.parts_count(data["text"])

    def _item_label(self, data: dict) -> str:
        name = data["name"] or "(без названия)"
        n = self.item_count(data)
        if self.table_of(data) is not None:
            return f"{name}  ·  текстов: {n} (таблица)"
        return f"{name}  ·  текстов: {n}" if n > 1 else name

    def _refresh_labels(self, *_args) -> None:
        for row in range(self.text_list.count()):
            item = self.text_list.item(row)
            item.setText(self._item_label(item.data(ITEM_ROLE)))
        self._update_list_info()
        self._update_editor_info()

    def add_text_item(self, name: str, text: str, path: str | None, tooltip: str | None = None,
                      table: TableSource | None = None) -> QListWidgetItem:
        data = {"name": name, "text": text, "path": path, "table_id": None}
        if table is not None:
            data["table_id"] = self._next_table_id
            self._tables[self._next_table_id] = table
            self._next_table_id += 1
        item = QListWidgetItem(self._item_label(data))
        item.setData(ITEM_ROLE, data)
        item.setToolTip(tooltip or path or "Текст, введённый вручную")
        self.text_list.addItem(item)
        # без ClearAndSelect в режиме множественного выбора выделенными остаются все добавленные
        # элементы, и Delete убрал бы их все
        self.text_list.setCurrentItem(item, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        self._update_list_info()
        return item

    def add_files(self, paths: list[str | Path]) -> None:
        selection = collect_files(paths)
        problems = [f"{p.name} — {unsupported_reason(p)}" for p in selection.unsupported]
        loaded = []
        table_files = [f for f in selection.files if is_table(f)]
        tables = self._import_tables(table_files, problems)
        for f in selection.files:
            if is_table(f):
                continue
            try:
                item = load_file(f)
            except UnsupportedFileError as exc:
                problems.append(f"{f.name} — {exc}")
                continue
            except Exception as exc:  # noqa: BLE001 — сообщаем о любой ошибке чтения
                problems.append(f"{f.name} — не удалось прочитать: {exc}")
                continue
            if not item.text.strip():
                note = " (в .docx читаются только абзацы, таблицы и надписи — нет)" if f.suffix.lower() == ".docx" else ""
                problems.append(f"{f.name} — в файле нет текста{note}")
                continue
            loaded.append(item)

        folders = [p for p in map(Path, paths) if p.is_dir()]
        if folders and not selection.files:
            problems.append(f"В папке нет файлов {SUPPORTED_LIST}")

        if loaded or tables:
            # пустой стартовый «Текст 1» заменяем файлами
            if self.text_list.count() == 1:
                only = self.text_list.item(0).data(ITEM_ROLE)
                if not only["text"].strip() and not only["path"] and not self.table_of(only):
                    self.text_list.takeItem(0)
            for item in loaded:
                self.add_text_item(item.path.stem, item.text, str(item.path), f"{item.path}\n{item.describe()}")
                self.log_view.appendPlainText(f"Добавлен: {item.path} — {item.describe()}")
            for source in tables:
                path = source.table.path
                self.add_text_item(path.stem, "", str(path), f"{path}\n{source.describe()}", table=source)
                self.log_view.appendPlainText(f"Добавлена таблица: {path} — {source.describe()}, текстов: {len(source.texts)}")

        n_files = len(loaded) + len(tables)
        status = f"Добавлено файлов: {n_files}"
        n_parts = sum(self.parts_count(item.text) for item in loaded) + sum(len(s.texts) for s in tables)
        if n_parts > n_files:
            status += f" (текстов: {n_parts})"
        if selection.skipped_in_folders:
            status += f"; в папке пропущено файлов других форматов: {selection.skipped_in_folders}"
        self.statusBar().showMessage(status, 8000)
        if problems:
            for p in problems:
                self.log_view.appendPlainText(f"Не добавлен: {p}")
            QMessageBox.warning(
                self,
                APP_NAME,
                "Не добавлены:\n\n" + "\n".join(f"• {p}" for p in problems)
                + f"\n\nПрограмма принимает файлы {SUPPORTED_LIST}. "
                "Подробнее — вкладка «Справка», раздел «Какие файлы принимаются».",
            )

    def _ask_table_spec(self, table: Table, spec: TableSpec | None, position: str = "",
                        remaining: int = 0) -> tuple[Table, TableSpec, bool] | None:
        """Окно выбора столбцов. None — пользователь пропустил таблицу."""
        dialog = TableImportDialog(table, spec, self, position, remaining)
        if not dialog.exec():  # 0 — «Пропустить таблицу» или закрытие окна
            return None
        return dialog.table, dialog.spec(), dialog.apply_to_rest

    def _import_tables(self, files: list[Path], problems: list[str]) -> list[TableSource]:
        sources = []
        template: TableSpec | None = None   # выбор «для остальных таблиц»
        for k, f in enumerate(files):
            try:
                table = read_table(f)
                if template is not None and template.sheet in table.sheet_names and template.sheet != table.sheet:
                    table = read_table(f, template.sheet)
            except Exception as exc:  # noqa: BLE001 — сообщаем о любой ошибке чтения
                problems.append(f"{f.name} — {exc}")
                continue
            if not table.rows:
                problems.append(f"{f.name} — таблица пустая")
                continue
            spec = reuse_spec(table, template) if template is not None else None
            if spec is None:
                position = f"{k + 1} из {len(files)}" if len(files) > 1 else ""
                answer = self._ask_table_spec(table, guess_spec(table), position, len(files) - k - 1)
                if answer is None:
                    self.log_view.appendPlainText(f"Таблица пропущена: {f}")
                    continue
                table, spec, apply_to_rest = answer
                if apply_to_rest:
                    template = spec
            texts = table_texts(table, spec)
            if not texts:
                problems.append(f"{f.name} — в выбранном столбце нет текста")
                continue
            sources.append(TableSource(table, spec, texts))
        return sources

    def _on_change_columns(self) -> None:
        item = self.text_list.currentItem()
        source = self.table_of(item.data(ITEM_ROLE)) if item is not None else None
        if source is None:
            return
        answer = self._ask_table_spec(source.table, source.spec)
        if answer is None:
            return
        table, spec, _ = answer
        source.table, source.spec, source.texts = table, spec, table_texts(table, spec)
        item.setToolTip(f"{table.path}\n{source.describe()}")
        item.setText(self._item_label(item.data(ITEM_ROLE)))
        self._on_current_item_changed(item, None)
        self._update_list_info()
        self.log_view.appendPlainText(f"Столбцы изменены: {table.path} — {source.describe()}, текстов: {len(source.texts)}")

    @staticmethod
    def _table_preview(source: TableSource) -> str:
        lines = []
        for row, title, text in source.texts[:TABLE_PREVIEW_TEXTS]:
            lines.append(f"── строка {row}" + (f" · {title}" if title else "") + " ──")
            lines.append(text)
            lines.append("")
        rest = len(source.texts) - TABLE_PREVIEW_TEXTS
        if rest > 0:
            lines.append(f"… и ещё {rest} текстов (в анализ попадут все)")
        return "\n".join(lines)

    def _on_new_text(self) -> None:
        self.add_text_item(self._next_name(), "", None)
        self.tabs.setCurrentIndex(TAB_TEXT)
        self.editor.setFocus()

    def _on_add_files(self) -> None:
        start = self.settings.value("last_input_dir", str(Path.home()))
        files, _ = QFileDialog.getOpenFileNames(self, "Добавить тексты", start, FILE_FILTER)
        if files:
            self.settings.setValue("last_input_dir", str(Path(files[0]).parent))
            self.add_files(files)

    def _on_add_folder(self) -> None:
        start = self.settings.value("last_input_dir", str(Path.home()))
        folder = QFileDialog.getExistingDirectory(self, "Папка с текстами", start)
        if folder:
            self.settings.setValue("last_input_dir", folder)
            self.add_files([folder])

    def _on_remove_selected(self) -> None:
        for item in self.text_list.selectedItems():
            self._tables.pop(item.data(ITEM_ROLE).get("table_id"), None)
            self.text_list.takeItem(self.text_list.row(item))
        if self.text_list.count() == 0:
            self.add_text_item(self._next_name(), "", None)
        self._update_list_info()

    def _on_current_item_changed(self, current: QListWidgetItem | None, _previous) -> None:
        self._loading_item = True
        try:
            if current is None:
                self.name_edit.clear()
                self.editor.clear()
                return
            data = current.data(ITEM_ROLE)
            source = self.table_of(data)
            self.name_edit.setText(data["name"])
            # текст таблицы показывается только для просмотра: правится сама таблица или выбор столбцов
            self.editor.setReadOnly(source is not None)
            self.editor.setPlainText(self._table_preview(source) if source is not None else data["text"])
            self.columns_button.setVisible(source is not None)
            self._update_editor_info()
        finally:
            self._loading_item = False

    def _on_editor_changed(self) -> None:
        if self._loading_item:
            return
        item = self.text_list.currentItem()
        if item is None or self.table_of(item.data(ITEM_ROLE)) is not None:
            return
        data = item.data(ITEM_ROLE)
        data["text"] = self.editor.toPlainText()
        item.setData(ITEM_ROLE, data)
        item.setText(self._item_label(data))
        self._update_editor_info()

    def _on_name_edited(self, name: str) -> None:
        item = self.text_list.currentItem()
        if item is None:
            return
        data = item.data(ITEM_ROLE)
        data["name"] = name
        item.setData(ITEM_ROLE, data)
        item.setText(self._item_label(data))

    def _update_editor_info(self) -> None:
        item = self.text_list.currentItem()
        source = self.table_of(item.data(ITEM_ROLE)) if item is not None else None
        if source is not None:
            self.editor_info.setText(
                f"{source.describe()}. Текстов: {len(source.texts)}. "
                "Здесь — только просмотр; другой лист или столбцы — кнопка «Столбцы…»."
            )
            return
        text = self.editor.toPlainText()
        info = f"Символов: {len(text):,}   Слов (прибл.): {len(text.split()):,}".replace(",", " ")
        n = self.parts_count(text)
        if n > 1:
            info += f"   Текстов по разделителю «{self.current_separator()}»: {n}"
        self.editor_info.setText(info)

    def _update_list_info(self) -> None:
        count = self.text_list.count()
        total = sum(self.item_count(self.text_list.item(r).data(ITEM_ROLE)) for r in range(count))
        info = f"В списке: {count}"
        if total != count:
            info += f", текстов для анализа: {total}"
        self.list_info.setText(info)

    def collect_items(self) -> list[tuple[str, str, str | None]]:
        """Тексты для анализа в порядке списка: строки таблиц, части текстов по разделителю, тексты целиком."""
        items = []
        separator = self.current_separator()
        for row in range(self.text_list.count()):
            data = self.text_list.item(row).data(ITEM_ROLE)
            name = data["name"] or f"Текст {row + 1}"
            source = self.table_of(data)
            if source is not None:
                items.extend(table_items(name, source.table, source.texts))
            elif data["text"].strip():
                items.extend(split_items([(name, data["text"], data["path"])], separator))
        return items

    # ---------------------------------------------------------- drag & drop
    def dragEnterEvent(self, event) -> None:  # noqa: N802 — Qt API
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 — Qt API
        # неподдерживаемые файлы не отсеиваем молча: add_files объяснит, почему они не добавлены
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.add_files(paths)

    # -------------------------------------------------------------- анализ
    def current_options(self) -> AnalysisOptions:
        return AnalysisOptions(
            morphology=self.cb_morph.isChecked(),
            syntax=self.cb_syntax.isChecked(),
            emotions=self.cb_emotions.isChecked(),
            entities=self.cb_entities.isChecked(),
            emotion_method=self.emotion_method.currentData(),
            lexicon=self.lexicon_combo.currentData(),
            max_trees=self.max_trees.value(),
            detailed_texts=self.detailed_texts.value(),
        )

    def current_formats(self) -> list[str]:
        return [fmt for fmt, cb in (("html", self.cb_html), ("docx", self.cb_docx), ("json", self.cb_json)) if cb.isChecked()]

    def start_analysis(self) -> None:
        if self.analysis_thread is not None:
            return
        items = self.collect_items()
        if not items:
            QMessageBox.information(self, APP_NAME, "Нет текстов для анализа: введите текст или добавьте файлы.")
            return
        out_dir = Path(self.out_dir_edit.text().strip() or default_output_dir())
        formats = self.current_formats()
        self.analyzer.options = self.current_options()
        self._save_settings()

        self.log_view.appendPlainText(f"=== Анализ: текстов {len(items)}, форматы: {', '.join(formats) or 'нет'} ===")
        self._set_busy(True)

        self.analysis_thread = QThread(self)
        self.worker = AnalysisWorker(self.analyzer, items, out_dir, formats)
        self.worker.moveToThread(self.analysis_thread)
        self.analysis_thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.log.connect(self.log_view.appendPlainText)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.cancelled.connect(self._on_cancelled)
        for sig in (self.worker.finished, self.worker.failed, self.worker.cancelled):
            sig.connect(self.analysis_thread.quit)
        self.analysis_thread.finished.connect(self._cleanup_thread)
        self.analysis_thread.start()

    def _on_progress(self, fraction: float, message: str) -> None:
        self.progress.setValue(int(fraction * 1000))
        self.progress_label.setText(message)

    def _on_finished(self, corpus, written: dict) -> None:
        for fmt, path in written.items():
            self.log_view.appendPlainText(f"{fmt.upper()}: {path}")
        report = written.get("html")
        if report is None:
            # HTML нужен для предпросмотра, даже если его не просили сохранять
            from ..report import write_html

            preview_dir = Path(tempfile.gettempdir()) / APP_NAME
            preview_dir.mkdir(parents=True, exist_ok=True)
            report = write_html(corpus, preview_dir / "preview.html")
        self.last_report = Path(report)
        self.last_out_dir = Path(next(iter(written.values()))).parent if written else None
        self._show_report(self.last_report)
        words = sum(t.stats.n_words for t in corpus.texts)
        msg = f"Готово: {len(corpus.texts)} текст(ов), {words} слов, {corpus.elapsed} с"
        self.progress_label.setText(msg + (f"\nОтчёты: {self.last_out_dir}" if self.last_out_dir else ""))
        self.statusBar().showMessage(msg, 10000)
        self.open_browser_button.setEnabled(True)

    def _on_failed(self, tb: str) -> None:
        self.log_view.appendPlainText(tb)
        self.progress_label.setText("Ошибка — подробности на вкладке «Журнал»")
        if tb.startswith("Traceback"):
            message = tb.strip().splitlines()[-1]
        else:  # готовое сообщение для пользователя (например, нет модели и интернета)
            message = tb.strip() or "неизвестная ошибка"
        if message == LEXICON_MISSING_MESSAGE.strip():
            # словарь можно скачать прямо отсюда; условия NRC уже есть в тексте сообщения
            answer = QMessageBox.question(self, APP_NAME, f"{message}\n\nСкачать словарь NRC EmoLex сейчас?")
            if answer == QMessageBox.StandardButton.Yes:
                self.download_nrc(ask=False)
            return
        QMessageBox.critical(self, APP_NAME, f"Анализ завершился с ошибкой:\n\n{message}")

    def _on_cancelled(self) -> None:
        self.log_view.appendPlainText("Анализ отменён")
        self.progress_label.setText("Отменено")
        self.progress.setValue(0)

    def _on_cancel(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            self.cancel_button.setEnabled(False)
            self.progress_label.setText("Отмена…")

    def _cleanup_thread(self) -> None:
        if self.worker is not None:
            self.worker.deleteLater()
        if self.analysis_thread is not None:
            self.analysis_thread.deleteLater()
        self.worker = None
        self.analysis_thread = None
        self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self.run_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        for w in (self.cb_morph, self.cb_syntax, self.cb_emotions, self.cb_entities, self.emotion_method,
                  self.lexicon_combo, self.max_trees, self.split_cb, self.separator_edit, self.detailed_texts,
                  self.columns_button):
            w.setEnabled(not busy)
        if not busy:
            self._update_emotion_controls()
            self.separator_edit.setEnabled(self.split_cb.isChecked())

    def _update_emotion_controls(self) -> None:
        on = self.cb_emotions.isChecked()
        self.emotion_method.setEnabled(on)
        # «Только нейросеть» словарь не использует
        self.lexicon_combo.setEnabled(on and self.emotion_method.currentData() != "model")

    def _refresh_lexicon_labels(self) -> None:
        """Пометка «не скачан» у NRC EmoLex; после скачивания из меню она снимается."""
        nrc_ready = lexicon_path("nrc").exists()
        for i, (key, label, tip) in enumerate(LEXICON_LABELS):
            if key == "nrc" and not nrc_ready:
                label += " — не скачан"
                tip += "\n\nСловарь ещё не скачан: меню «Файл → Скачать словарь NRC EmoLex…»"
            self.lexicon_combo.setItemText(i, label)
            self.lexicon_combo.setItemData(i, tip, Qt.ItemDataRole.ToolTipRole)

    # ------------------------------------------------------- словарь NRC
    def download_nrc(self, ask: bool = True) -> None:
        if self.nrc_thread is not None or self.analysis_thread is not None:
            return
        from ..nlp.nrc import CREDIT, LICENSE_NOTE

        force = lexicon_path("nrc").exists()
        if ask:
            question = (
                f"{CREDIT}\n\n{LICENSE_NOTE}\n\n"
                + ("Словарь уже скачан. Скачать и собрать заново?" if force else
                   "Словарь (около 25 МБ) будет скачан с сайта NRC. Скачать?")
                + f"\n\nПапка словаря: {nrc_dir()}"
            )
            if QMessageBox.question(self, "Словарь NRC EmoLex", question) != QMessageBox.StandardButton.Yes:
                return

        dialog = QProgressDialog("Подключение к сайту NRC…", "Отмена", 0, 0, self)
        dialog.setWindowTitle("Словарь NRC EmoLex")
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)

        def on_progress(done: int, total: int) -> None:
            if total:
                dialog.setMaximum(total)
                dialog.setValue(done)
            dialog.setLabelText(f"Загрузка: {done / 2**20:.1f}" + (f" из {total / 2**20:.1f}" if total else "") + " МБ")

        def on_log(message: str) -> None:
            self.log_view.appendPlainText(message)
            if message.startswith("Сборка"):
                dialog.setRange(0, 0)
                dialog.setLabelText(message)
                dialog.setCancelButton(None)  # сборка занимает секунды и не прерывается

        def on_finished(stats: dict) -> None:
            dialog.close()
            self.analyzer.unload_lexicon()  # при повторной сборке — перечитать
            self._refresh_lexicon_labels()
            self.log_view.appendPlainText(f"Словарь NRC EmoLex: {lexicon_path('nrc')}")
            QMessageBox.information(
                self, "Словарь NRC EmoLex",
                f"Словарь установлен: {stats['emotional_lemmas']} эмоциональных лемм.\n\nПапка: {nrc_dir()}",
            )

        def on_failed(message: str) -> None:
            dialog.close()
            self.log_view.appendPlainText(message)
            QMessageBox.warning(self, "Словарь NRC EmoLex", message.strip().splitlines()[-1]
                                if message.startswith("Traceback") else message)

        def on_cancelled() -> None:
            dialog.close()
            self.log_view.appendPlainText("Загрузка словаря NRC EmoLex отменена")

        self.nrc_thread = QThread(self)
        self.nrc_worker = NrcDownloadWorker(force)
        self.nrc_worker.moveToThread(self.nrc_thread)
        self.nrc_thread.started.connect(self.nrc_worker.run)
        self.nrc_worker.progress.connect(on_progress)
        self.nrc_worker.log.connect(on_log)
        self.nrc_worker.finished.connect(on_finished)
        self.nrc_worker.failed.connect(on_failed)
        self.nrc_worker.cancelled.connect(on_cancelled)
        dialog.canceled.connect(self.nrc_worker.cancel)
        for sig in (self.nrc_worker.finished, self.nrc_worker.failed, self.nrc_worker.cancelled):
            sig.connect(self.nrc_thread.quit)
        self.nrc_thread.finished.connect(self._cleanup_nrc_thread)
        self.nrc_thread.start()
        dialog.show()

    def _cleanup_nrc_thread(self) -> None:
        if self.nrc_worker is not None:
            self.nrc_worker.deleteLater()
        if self.nrc_thread is not None:
            self.nrc_thread.deleteLater()
        self.nrc_worker = None
        self.nrc_thread = None

    def _show_report(self, path: Path) -> None:
        url = QUrl.fromLocalFile(str(path))
        if QWebEngineView is not None and isinstance(self.report_view, QWebEngineView):
            self.report_view.load(url)
        else:
            self.report_view.setHtml(
                f"<p>Отчёт сохранён: <a href='{url.toString()}'>{path}</a></p>"
                "<p>Встроенный просмотр недоступен (нет QtWebEngine) — откройте отчёт в браузере.</p>"
            )
        self.tabs.setCurrentIndex(TAB_REPORT)

    def _on_open_in_browser(self) -> None:
        if self.last_report:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_report)))

    def _on_open_folder(self) -> None:
        folder = self.last_out_dir or Path(self.out_dir_edit.text().strip() or default_output_dir())
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _on_choose_out_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Папка для отчётов", self.out_dir_edit.text())
        if folder:
            self.out_dir_edit.setText(folder)

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            f"О программе {APP_NAME}",
            f"<b>{APP_NAME} {__version__}</b><br><br>"
            "Морфологический и синтаксический анализ русских текстов (spaCy, pymorphy3) "
            "и определение эмоций (нейросеть rubert-tiny2-cedr + словарь эмоций).<br><br>"
            "Словарь эмоций на выбор: ручной словарь TextAnalyzer (входит в программу) или "
            "NRC Word-Emotion Association Lexicon (EmoLex), созданный "
            "Saif M. Mohammad и Peter D. Turney в National Research Council Canada (NRC): "
            f"<a href=\"{NRC_HOME}\">страница словаря</a>. NRC EmoLex скачивается отдельно и бесплатен "
            "только для некоммерческого исследовательского и учебного использования; "
            "распространять его данные нельзя.",
        )

    # ------------------------------------------------------------ настройки
    def _restore_settings(self) -> None:
        s = self.settings
        geometry = s.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        out_dir = s.value("out_dir")
        if out_dir:
            self.out_dir_edit.setText(out_dir)
        for key, cb in self._checkboxes().items():
            value = s.value(key)
            if value is not None:
                cb.setChecked(str(value).lower() in ("true", "1"))
        method = s.value("emotion_method")
        if method:
            idx = self.emotion_method.findData(method)
            if idx >= 0:
                self.emotion_method.setCurrentIndex(idx)
        # выбор пользователя сохраняется; без него — NRC, если скачан, иначе ручной словарь
        lexicon = s.value("lexicon") or default_lexicon()
        idx = self.lexicon_combo.findData(lexicon)
        if idx >= 0:
            self.lexicon_combo.setCurrentIndex(idx)
        trees = s.value("max_trees")
        if trees is not None:
            self.max_trees.setValue(int(trees))
        separator = s.value("separator")
        if separator:
            self.separator_edit.setText(separator)
        detailed = s.value("detailed_texts")
        if detailed is not None:
            self.detailed_texts.setValue(int(detailed))
        self._update_emotion_controls()
        self.separator_edit.setEnabled(self.split_cb.isChecked())

    def _save_settings(self) -> None:
        s = self.settings
        s.setValue("geometry", self.saveGeometry())
        s.setValue("out_dir", self.out_dir_edit.text())
        for key, cb in self._checkboxes().items():
            s.setValue(key, cb.isChecked())
        s.setValue("emotion_method", self.emotion_method.currentData())
        s.setValue("lexicon", self.lexicon_combo.currentData())
        s.setValue("max_trees", self.max_trees.value())
        s.setValue("separator", self.separator_edit.text())
        s.setValue("detailed_texts", self.detailed_texts.value())

    def _checkboxes(self) -> dict[str, QCheckBox]:
        return {
            "morphology": self.cb_morph,
            "syntax": self.cb_syntax,
            "emotions": self.cb_emotions,
            "entities": self.cb_entities,
            "split_texts": self.split_cb,
            "fmt_html": self.cb_html,
            "fmt_docx": self.cb_docx,
            "fmt_json": self.cb_json,
        }

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt API
        if self.analysis_thread is not None:
            if QMessageBox.question(self, APP_NAME, "Анализ ещё идёт. Прервать и выйти?") != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            if self.worker is not None:
                self.worker.cancel()
            self.analysis_thread.quit()
            self.analysis_thread.wait(5000)
        if self.nrc_thread is not None:
            if self.nrc_worker is not None:
                self.nrc_worker.cancel()
            self.nrc_thread.quit()
            self.nrc_thread.wait(5000)
        self._save_settings()
        event.accept()
