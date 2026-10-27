@echo off
rem Запуск графического интерфейса TextAnalyzer
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" -m textanalyzer %*
