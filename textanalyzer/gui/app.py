"""Запуск графического интерфейса."""

from __future__ import annotations

import sys


def run_gui() -> int:
    # На Windows torch нужно импортировать до Qt, иначе возможна ошибка
    # инициализации DLL (WinError 1114) при последующей загрузке модели эмоций.
    try:
        import torch  # noqa: F401
    except Exception:  # noqa: BLE001 — без torch просто не будет нейросетевого анализа
        pass

    # QtWebEngine должен быть импортирован до создания QApplication
    try:
        from PySide6 import QtWebEngineWidgets  # noqa: F401
    except ImportError:
        pass

    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from ..config import APP_NAME, package_dir
    from .main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setWindowIcon(QIcon(str(package_dir() / "gui" / "icon.png")))
    # кнопки стандартных окон («Да», «Нет», «Отмена») — по-русски, как и весь интерфейс
    translator = QTranslator(app)
    if translator.load(QLocale(QLocale.Language.Russian), "qtbase", "_",
                       QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)
    window = MainWindow()
    window.show()
    return app.exec()
