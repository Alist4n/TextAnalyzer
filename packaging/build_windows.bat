@echo off
rem Build TextAnalyzer for Windows: dist\TextAnalyzer\ (TextAnalyzer.exe, TextAnalyzer-cli.exe)
rem and the archive dist\TextAnalyzer-<version>-windows.zip. Can be started from any folder.
rem Keep this file ASCII with CRLF line endings: cmd.exe misreads UTF-8 / LF-only batch files.
setlocal
cd /d "%~dp0.."

if not exist .venv\Scripts\python.exe (
    echo No .venv found: install the project first, see README.md
    exit /b 1
)
if not exist models\rubert-tiny2-cedr-emotion-detection\config.json (
    .venv\Scripts\python scripts\download_models.py || exit /b 1
)
.venv\Scripts\python -m pip install -q -r packaging\requirements-build.txt || exit /b 1
.venv\Scripts\python -m PyInstaller --noconfirm --clean packaging\textanalyzer.spec || exit /b 1
.venv\Scripts\python packaging\make_zip.py || exit /b 1
