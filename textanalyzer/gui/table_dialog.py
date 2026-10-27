"""Окно импорта таблицы: лист, заголовки, столбец с текстом и столбец с названием, предпросмотр."""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..tables import (
    Table,
    TableSpec,
    column_names,
    guess_spec,
    read_table,
    table_texts,
    with_names,
)

PREVIEW_ROWS = 30
NO_TITLE = -1


class TableImportDialog(QDialog):
    def __init__(self, table: Table, spec: TableSpec | None = None, parent=None,
                 position: str = "", remaining: int = 0) -> None:
        super().__init__(parent)
        self.table = table
        self._updating = False
        title = f"Импорт таблицы — {table.path.name}"
        self.setWindowTitle(f"{title} ({position})" if position else title)
        self.resize(900, 620)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Каждая строка таблицы станет отдельным текстом. Выберите столбец с текстом и, если есть, "
            "столбец с названием — оно будет заголовком текста в отчёте. Строки с пустым текстом пропускаются."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self.sheet_combo = QComboBox()
        self.sheet_combo.addItems(table.sheet_names)
        self.sheet_combo.setToolTip("Лист книги Excel, из которого брать тексты")
        if table.sheet_names:
            self.sheet_combo.setCurrentText(table.sheet or table.sheet_names[0])
            form.addRow("Лист:", self.sheet_combo)
        self.header_cb = QCheckBox("Первая строка — заголовки столбцов")
        self.header_cb.setToolTip("Если отмечено, первая строка не считается текстом, а её ячейки — названия столбцов")
        form.addRow(self.header_cb)
        self.text_combo = QComboBox()
        self.text_combo.setToolTip("Столбец, в котором записаны тексты для анализа")
        form.addRow("Столбец с текстом:", self.text_combo)
        self.title_combo = QComboBox()
        self.title_combo.setToolTip(
            "Столбец с названием текста (товар, автор, ID…). Без него тексты называются по номеру строки."
        )
        form.addRow("Столбец с названием:", self.title_combo)
        layout.addLayout(form)

        self.info = QLabel()
        self.info.setWordWrap(True)
        layout.addWidget(self.info)

        self.preview = QTableWidget()
        self.preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.preview.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.preview.setWordWrap(False)
        layout.addWidget(self.preview, 1)

        self.rest_cb = QCheckBox(
            f"Применить этот выбор к остальным таблицам ({remaining}) — столбцы ищутся по заголовкам"
        )
        self.rest_cb.setVisible(remaining > 0)
        layout.addWidget(self.rest_cb)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Добавить")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Пропустить таблицу")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        spec = spec or guess_spec(table)
        self.header_cb.setChecked(spec.has_header)
        self._fill_columns(spec)

        self.sheet_combo.currentTextChanged.connect(self._on_sheet_changed)
        self.header_cb.toggled.connect(self._on_header_toggled)
        self.text_combo.currentIndexChanged.connect(self._update)
        self.title_combo.currentIndexChanged.connect(self._update)
        self._update()

    # ------------------------------------------------------------------
    def _fill_columns(self, spec: TableSpec) -> None:
        self._updating = True
        names = column_names(self.table, self.header_cb.isChecked())
        self.text_combo.clear()
        self.title_combo.clear()
        self.title_combo.addItem("(нет — называть по номеру строки)", NO_TITLE)
        for i, name in enumerate(names):
            self.text_combo.addItem(name, i)
            self.title_combo.addItem(name, i)
        if names:
            self.text_combo.setCurrentIndex(min(spec.text_col, len(names) - 1))
        title_idx = self.title_combo.findData(spec.title_col if spec.title_col is not None else NO_TITLE)
        self.title_combo.setCurrentIndex(max(0, title_idx))
        self._updating = False

    def _on_sheet_changed(self, sheet: str) -> None:
        try:
            self.table = read_table(self.table.path, sheet)
        except Exception as exc:  # noqa: BLE001 — показываем причину в окне
            self.info.setText(f"Не удалось прочитать лист «{sheet}»: {exc}")
            return
        spec = guess_spec(self.table)
        self.header_cb.blockSignals(True)
        self.header_cb.setChecked(spec.has_header)
        self.header_cb.blockSignals(False)
        self._fill_columns(spec)
        self._update()

    def _on_header_toggled(self, _checked: bool) -> None:
        current = self.spec()
        self._fill_columns(current)
        self._update()

    def spec(self) -> TableSpec:
        text_col = self.text_combo.currentData()
        title_col = self.title_combo.currentData()
        spec = TableSpec(
            text_col=text_col if text_col is not None else 0,
            title_col=None if title_col in (None, NO_TITLE) else title_col,
            has_header=self.header_cb.isChecked(),
        )
        return with_names(self.table, spec)

    @property
    def apply_to_rest(self) -> bool:
        return self.rest_cb.isVisible() and self.rest_cb.isChecked()

    def _update(self, *_args) -> None:
        if self._updating:
            return
        spec = self.spec()
        texts = table_texts(self.table, spec)
        data_rows = len(self.table.rows) - (1 if spec.has_header else 0)
        skipped = data_rows - len(texts)
        msg = f"{self.table.describe()}. Будет добавлено текстов: <b>{len(texts)}</b>"
        if skipped:
            msg += f" (строк с пустым текстом пропущено: {skipped})"
        if not texts:
            msg += ". <b>В выбранном столбце нет текста — выберите другой.</b>"
        self.info.setText(msg)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(texts))
        self._fill_preview(spec)

    def _fill_preview(self, spec: TableSpec) -> None:
        names = column_names(self.table, spec.has_header)
        start = 1 if spec.has_header else 0
        rows = self.table.rows[start : start + PREVIEW_ROWS]
        self.preview.clear()
        self.preview.setColumnCount(len(names))
        self.preview.setRowCount(len(rows))
        bold = QFont()
        bold.setBold(True)
        for c, name in enumerate(names):
            role = "\n[текст]" if c == spec.text_col else "\n[название]" if c == spec.title_col else ""
            header = QTableWidgetItem(name + role)
            if role:
                header.setFont(bold)
            self.preview.setHorizontalHeaderItem(c, header)
        for r, row in enumerate(rows):
            self.preview.setVerticalHeaderItem(r, QTableWidgetItem(str(self.table.first_row + start + r)))
            for c in range(len(names)):
                value = row[c] if c < len(row) else ""
                shown = value.replace("\n", " ⏎ ")
                item = QTableWidgetItem(shown if len(shown) <= 200 else shown[:200] + "…")
                item.setToolTip(value[:2000])
                if c in (spec.text_col, spec.title_col):
                    item.setFont(bold)
                self.preview.setItem(r, c, item)
        self.preview.resizeColumnsToContents()
        for c in range(len(names)):
            self.preview.setColumnWidth(c, min(self.preview.columnWidth(c), 420))
