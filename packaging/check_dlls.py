"""Проверка собранной программы: каждой DLL хватает того, что лежит в сборке, и самой Windows.

Ловит библиотеки, которые на компьютере разработчика берутся из System32 (VC++ Redistributable
и т. п.), а на «чистом» компьютере отсутствуют — тогда программа падает при запуске с
«WinError 126 … не найден указанный модуль».

Запуск после сборки: python packaging/check_dlls.py [dist/TextAnalyzer]
Выход с кодом 1, если что-то не нашлось. Нужен pefile (ставится вместе с PyInstaller).
"""
import os
import sys
from pathlib import Path

import pefile

# библиотеки, которых нет в «голой» Windows: ставятся отдельными пакетами
REDISTRIBUTABLE = ("vcruntime", "msvcp", "concrt", "vcomp", "vccorlib", "mfc", "msvcr", "ucrtbased")
# плагины Qt, которые программа не загружает (QML-отладка и т. п.): их зависимости не проверяем
SKIP_DIRS = ("pyside6/plugins/qmltooling",)


def imported_dlls(path: Path) -> list[str]:
    try:
        pe = pefile.PE(str(path), fast_load=True)
    except pefile.PEFormatError:
        return []
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    return [entry.dll.decode().lower() for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", [])]


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/TextAnalyzer")
    system32 = Path(os.environ["SystemRoot"]) / "System32"
    files = [f for f in root.rglob("*") if f.suffix.lower() in (".dll", ".pyd", ".exe")]
    # DLL из другой папки сборки к этому моменту уже загружена (Qt6Core для плагинов Qt,
    # python312 для модулей) — Windows находит её по имени
    bundled = {f.name.lower() for f in files}
    problems = []
    for f in files:
        rel = f.relative_to(root).as_posix()
        if rel.lower().startswith(tuple(f"_internal/{d}" for d in SKIP_DIRS)):
            continue
        for dll in imported_dlls(f):
            if dll.startswith(("api-ms-win-", "ext-ms-")):
                continue  # наборы API Windows
            if dll in bundled:
                continue
            if (system32 / dll).exists() and not dll.startswith(REDISTRIBUTABLE):
                continue  # часть Windows
            problems.append(f"{rel}: нужна {dll} — в сборке её нет"
                            + (" (на этом компьютере она есть только в System32)" if (system32 / dll).exists() else ""))
    for line in problems:
        print(line)
    print(f"Проверено файлов: {len(files)}; проблем: {len(problems)}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
