#!/bin/bash
# Сборка TextAnalyzer для macOS: dist/TextAnalyzer.app и образ dist/TextAnalyzer-<версия>-macos-arm64.dmg.
#
# Запускать на Mac с Apple Silicon (M1 и новее): PyInstaller не собирает программу для другой
# системы, а PyTorch для Mac на Intel больше не выпускается. Нужен Python 3.11–3.12
# (python.org или Homebrew: brew install python@3.12) и интернет для установки зависимостей.
#
#   bash packaging/build_macos.sh
#   PYTHON=python3.12 bash packaging/build_macos.sh   # если python3 — другая версия
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"
if [ ! -x .venv/bin/python ]; then
  "$PYTHON" -m venv .venv
fi
PY=.venv/bin/python
$PY -m pip install -q --upgrade pip
$PY -m pip install -q torch      # на macOS обычная сборка torch — без CUDA
$PY -m pip install -q -r requirements.txt -r packaging/requirements-build.txt
$PY -c "import ru_core_news_md" 2>/dev/null || $PY -m spacy download ru_core_news_md
if [ ! -f models/rubert-tiny2-cedr-emotion-detection/config.json ]; then
  $PY scripts/download_models.py
fi

$PY -m PyInstaller --noconfirm --clean packaging/textanalyzer.spec

VERSION=$($PY -c "import textanalyzer; print(textanalyzer.__version__)")
STAGE=dist/dmg
DMG="dist/TextAnalyzer-$VERSION-macos-$(uname -m).dmg"
rm -rf "$STAGE" "$DMG"
mkdir -p "$STAGE"
cp -R dist/TextAnalyzer.app "$STAGE/"
cp packaging/README-dist.txt "$STAGE/README.txt"
ln -s /Applications "$STAGE/Applications"   # в окне образа: перетащить программу в «Программы»
hdiutil create -volname TextAnalyzer -srcfolder "$STAGE" -ov -format UDZO "$DMG"
rm -rf "$STAGE"

# проверка: собранная программа анализирует текст без интернета
dist/TextAnalyzer.app/Contents/MacOS/TextAnalyzer-cli analyze --text "Как же я рад тебя видеть!" \
  --lexicon manual --formats json -o dist/selftest --name selftest
echo "Готово: $DMG"
