"""Готовит собранную для Windows программу к передаче: кладёт README.txt рядом и упаковывает
dist/TextAnalyzer/ в dist/TextAnalyzer-<версия>-windows.zip. (Образ .dmg для macOS делает build_macos.sh.)
"""

from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from textanalyzer import __version__  # noqa: E402

DIST = ROOT / "dist"


def main() -> None:
    folder = DIST / "TextAnalyzer"
    if not (folder / "TextAnalyzer.exe").exists():
        raise SystemExit(f"Нет собранной программы в {folder}: сначала PyInstaller")
    shutil.copy(ROOT / "packaging" / "README-dist.txt", folder / "README.txt")
    archive = DIST / f"TextAnalyzer-{__version__}-windows.zip"
    files = sorted(p for p in folder.rglob("*") if p.is_file())
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for k, path in enumerate(files, 1):
            zf.write(path, Path("TextAnalyzer") / path.relative_to(folder))
            if k % 500 == 0 or k == len(files):
                print(f"\r  {k}/{len(files)} файлов", end="", flush=True)
    print(f"\nАрхив: {archive} ({archive.stat().st_size / 2**20:.0f} МБ)")


if __name__ == "__main__":
    main()
