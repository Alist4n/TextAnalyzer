TextAnalyzer — морфологический, синтаксический и эмоциональный анализ русских текстов
=====================================================================================

ЗАПУСК
  Windows: TextAnalyzer.exe (папку целиком можно переложить куда угодно; установка не нужна).
  macOS:   перетащите TextAnalyzer.app в «Программы». Программа не подписана сертификатом Apple,
           поэтому при первом запуске: правый щелчок по TextAnalyzer.app → «Открыть» → «Открыть».
           Если macOS пишет, что приложение «повреждено», выполните в Терминале:
               xattr -dr com.apple.quarantine /Applications/TextAnalyzer.app

  Самый первый запуск после распаковки может занять 1–2 минуты: антивирус (Windows Defender)
  проверяет файлы программы. Дальше окно открывается за несколько секунд, первый анализ
  занимает 15–20 секунд (загружаются модели), следующие — сразу.
  Подробная справка — в программе, клавиша F1.

КОМАНДНАЯ СТРОКА
  Windows: TextAnalyzer-cli.exe analyze тексты\ -o отчёты
  macOS:   /Applications/TextAnalyzer.app/Contents/MacOS/TextAnalyzer-cli analyze тексты -o отчёты
  Все ключи: TextAnalyzer-cli analyze -h

ИНТЕРНЕТ
  Не нужен: нейросеть эмоций, языковая модель и ручной словарь эмоций входят в программу,
  тексты никуда не отправляются.

СЛОВАРЬ ЭМОЦИЙ NRC EmoLex
  Второй словарь эмоций, NRC Word-Emotion Association Lexicon (Saif M. Mohammad, Peter D. Turney,
  National Research Council Canada), в программу не входит: его лицензия разрешает только
  некоммерческое исследовательское и учебное использование и запрещает распространение.
  Пока он не скачан, программа использует ручной словарь эмоций (он входит в программу).
  Каждый пользователь скачивает NRC EmoLex сам, один раз (~25 МБ):
    в окне — меню «Файл → Скачать словарь NRC EmoLex…»;
    в командной строке — TextAnalyzer-cli download-nrc.
  Страница словаря: https://saifmohammad.com/WebPages/NRC-Emotion-Lexicon.htm
  Словарь сохраняется в папку данных пользователя:
    Windows: %LOCALAPPDATA%\TextAnalyzer\nrc-emolex
    macOS:   ~/Library/Application Support/TextAnalyzer/nrc-emolex

ФАЙЛЫ ПРОГРАММЫ
  Настройки окна: Windows — %APPDATA%\TextAnalyzer\TextAnalyzer.ini,
                  macOS — ~/.config/TextAnalyzer/TextAnalyzer.ini
  Журнал ошибок окна: папка данных пользователя (см. выше), файл TextAnalyzer.log.
  Отчёты по умолчанию: Документы/TextAnalyzer/reports.

ОСНОВНЫЕ КОМПОНЕНТЫ И ИХ ЛИЦЕНЗИИ
  Qt и PySide6 (LGPL v3) — интерфейс; QtWebEngine включает Chromium.
  PyTorch (BSD), Hugging Face transformers, tokenizers, safetensors (Apache 2.0) — нейросеть.
  Модель эмоций cointegrated/rubert-tiny2-cedr-emotion-detection: основа rubert-tiny2 (MIT),
    обучена на корпусе CEDR (Apache 2.0); у самой дообученной модели лицензия не указана.
  spaCy, thinc, модель ru_core_news_md (MIT) — морфология и синтаксис.
  pymorphy3 (MIT), словари OpenCorpora (CC BY-SA) — морфологический словарь.
  matplotlib, NumPy, Jinja2, python-docx, openpyxl, charset-normalizer, Pillow — отчёты и файлы
    (лицензии BSD, MIT и аналогичные).
