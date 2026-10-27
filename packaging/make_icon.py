"""Рисует значок программы: «Аа» и полоска цветов эмоций, как в отчёте.

Запуск (нужен только при смене значка): .venv\\Scripts\\python packaging\\make_icon.py
Пишет textanalyzer/gui/icon.png (значок окна), packaging/icon.ico (Windows), packaging/icon.icns (macOS).
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from textanalyzer.report.common import ACCENT, EMOTION_COLORS  # noqa: E402

SIZE = 1024
FONTS = ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
         "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONTS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise SystemExit("нет шрифта с кириллицей: " + ", ".join(FONTS))


def draw() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = SIZE // 16
    d.rounded_rectangle((pad, pad, SIZE - pad, SIZE - pad), radius=SIZE // 5, fill=ACCENT)
    d.text((SIZE / 2, SIZE * 0.43), "Аа", font=font(int(SIZE * 0.42)), fill="white", anchor="mm")
    # полоска эмоций: радость, грусть, удивление, страх, гнев
    colors = [EMOTION_COLORS[e] for e in ("joy", "sadness", "surprise", "fear", "anger")]
    left, right, top, height = SIZE * 0.22, SIZE * 0.78, SIZE * 0.70, SIZE * 0.085
    width = (right - left) / len(colors)
    d.rounded_rectangle((left - 8, top - 8, right + 8, top + height + 8), radius=int(height / 2), fill="white")
    for k, color in enumerate(colors):
        d.rectangle((left + k * width, top, left + (k + 1) * width, top + height), fill=color)
    return img


def main() -> None:
    img = draw()
    png = ROOT / "textanalyzer" / "gui" / "icon.png"
    img.resize((256, 256), Image.LANCZOS).save(png)
    img.save(ROOT / "packaging" / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    img.save(ROOT / "packaging" / "icon.icns")
    print("Готово:", png, ROOT / "packaging" / "icon.ico", ROOT / "packaging" / "icon.icns")


if __name__ == "__main__":
    main()
