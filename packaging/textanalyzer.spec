# -*- mode: python ; coding: utf-8 -*-
"""Сборка TextAnalyzer PyInstaller'ом — одна и та же для Windows и macOS.

Запуск из корня проекта: packaging\\build_windows.bat или packaging/build_macos.sh
(или напрямую: pyinstaller --noconfirm packaging/textanalyzer.spec).

Результат — папка dist/TextAnalyzer:
  Windows: TextAnalyzer.exe (окно) и TextAnalyzer-cli.exe (командная строка) + _internal/
  macOS:   dist/TextAnalyzer.app (внутри Contents/MacOS — оба исполняемых файла)

Внутрь входят модель эмоций из models/, языковая модель spaCy, словари pymorphy3 и ручной
словарь эмоций. NRC EmoLex НЕ входит: его лицензия запрещает распространение — собранная
программа скачивает его сама (меню «Файл» или TextAnalyzer-cli download-nrc).
"""

import os
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).parent  # noqa: F821 — SPECPATH задаёт PyInstaller
APP = "TextAnalyzer"
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "textanalyzer" / "__init__.py").read_text()).group(1)

MODEL = ROOT / "models" / "rubert-tiny2-cedr-emotion-detection"
if not (MODEL / "config.json").exists():
    raise SystemExit(f"Нет модели эмоций в {MODEL}: сначала запустите scripts/download_models.py")

datas = [
    (str(ROOT / "textanalyzer" / "nlp" / "data"), "textanalyzer/nlp/data"),
    (str(ROOT / "textanalyzer" / "report" / "templates"), "textanalyzer/report/templates"),
    (str(ROOT / "textanalyzer" / "gui" / "icon.png"), "textanalyzer/gui"),
    (str(MODEL), "models/rubert-tiny2-cedr-emotion-detection"),
]
binaries = []
hiddenimports = ["textanalyzer.cli", "textanalyzer.gui.app"]

# spaCy находит модель, архитектуры и словари pymorphy3 через метаданные пакетов (entry points),
# поэтому вместе с файлами нужны и *.dist-info
for package in ("ru_core_news_md", "spacy_legacy", "spacy_loggers", "pymorphy3", "pymorphy3_dicts_ru"):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h


def _transformers_modules(name: str) -> bool:
    # transformers подгружает свои модули по строкам (ленивый импорт), анализ их не видит;
    # из тысяч моделей нужна только BERT (rubert-tiny2) и автоклассы
    parts = name.split(".")
    if len(parts) >= 3 and parts[1] == "models":
        return parts[2] in ("auto", "bert")
    return parts[1:2] not in (["commands"], ["cli"], ["pipelines"], ["trainer"], ["data"])


hiddenimports += collect_submodules("transformers", filter=_transformers_modules)

excludes = ["tkinter", "pytest", "_pytest", "IPython", "PyInstaller"]

# одна общая проверка зависимостей для обоих исполняемых файлов
a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "entry_gui.py"), str(ROOT / "packaging" / "entry_cli.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)


def _needed(dest: str) -> bool:
    """Без того, что программе не нужно: так сборка меньше примерно на 200 МБ."""
    path = dest.replace("\\", "/")
    name = path.rsplit("/", 1)[-1]
    if name.endswith((".cpp", ".c", ".pyx", ".pxd", ".pxi")):
        return False  # исходники C-расширений spaCy, thinc и др. (собранные .pyd/.so остаются)
    if not path.startswith("PySide6/"):
        return True
    if ".debug." in name or name.startswith("qtwebengine_devtools_resources"):
        return False  # отладочные ресурсы и инструменты разработчика Chromium
    if "/qml/" in path:
        return False  # QML/Qt Quick: окно на виджетах, отчёт — QWebEngineView
    if "/qtwebengine_locales/" in path:
        return name in ("ru.pak", "en-US.pak")
    if "/translations/" in path:
        return name.endswith("_ru.qm")  # интерфейс только русский: «Да/Нет» в стандартных окнах
    return True


a.datas = [entry for entry in a.datas if _needed(entry[0])]
a.binaries = [entry for entry in a.binaries if _needed(entry[0])]

if sys.platform == "win32":
    # Библиотеки Visual C++ (VC++ Redistributable) кладём в сборку сами: на компьютере без
    # свежего VC++ Redistributable PyTorch иначе не загружается («WinError 126 … shm.dll»).
    # PyInstaller берёт только DLL, нужные самому Python (версии из его установки), а
    # vcruntime140_threads.dll, нужную torch_cpu.dll, не берёт вовсе. Берём один комплект
    # из System32 — он новее, а библиотеки VC++ совместимы только «старое с новым».
    SYSTEM32 = Path(os.environ["SystemRoot"]) / "System32"
    VC_RUNTIME = ("vcruntime140.dll", "vcruntime140_1.dll", "vcruntime140_threads.dll",
                  "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "msvcp140_atomic_wait.dll")
    missing = [name for name in VC_RUNTIME if not (SYSTEM32 / name).exists()]
    if missing:
        raise SystemExit("Нет " + ", ".join(missing) + " в System32: установите Microsoft Visual C++ "
                         "Redistributable x64 (https://aka.ms/vs/17/release/vc_redist.x64.exe)")
    a.binaries = [entry for entry in a.binaries if entry[0].lower() not in VC_RUNTIME]
    for name in VC_RUNTIME:
        a.binaries.append((name, str(SYSTEM32 / name), "BINARY"))
    # torch загружает свои DLL из torch/lib, и их зависимости ищутся в этой папке и в System32,
    # а не в _internal (в командной строке PySide6 не загружает VC++ заранее) — копия и туда
    for name in VC_RUNTIME:
        a.binaries.append((f"torch/lib/{name}", str(SYSTEM32 / name), "BINARY"))

pyz = PYZ(a.pure)  # noqa: F821


def _scripts_without(script: str):
    """a.scripts — служебные скрипты запуска + обе точки входа; каждому exe — своя."""
    return [entry for entry in a.scripts if entry[0] != script]


icon_file = ROOT / "packaging" / ("icon.ico" if sys.platform == "win32" else "icon.icns")
icon = str(icon_file) if icon_file.exists() else None

gui = EXE(  # noqa: F821
    pyz,
    _scripts_without("entry_cli"),
    exclude_binaries=True,
    name=APP,
    console=False,
    icon=icon,
    upx=False,
)
cli = EXE(  # noqa: F821
    pyz,
    _scripts_without("entry_gui"),
    exclude_binaries=True,
    name=f"{APP}-cli",
    console=True,
    icon=icon,
    upx=False,
)
coll = COLLECT(gui, cli, a.binaries, a.datas, name=APP, upx=False)  # noqa: F821

if sys.platform == "darwin":
    app = BUNDLE(  # noqa: F821
        coll,
        name=f"{APP}.app",
        icon=icon,
        bundle_identifier="local.textanalyzer",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": APP,
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
        },
    )
