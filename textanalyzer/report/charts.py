"""Графики для отчётов: SVG-строка для HTML, PNG-байты для DOCX."""

from __future__ import annotations

import io
import re
from typing import Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from ..nlp.emotions import ALL_LABELS, EMOTION_RU, EMOTIONS, NEUTRAL  # noqa: E402
from ..nlp.models import SentenceInfo, TextResult  # noqa: E402
from .common import ACCENT, EMOTION_COLORS, dynamics_window, rolling  # noqa: E402

TEXT_COLOR = "#2B2B2B"
GRID_COLOR = "#E3E3E3"

plt.rcParams.update(
    {
        "svg.fonttype": "none",
        "font.family": ["Segoe UI", "DejaVu Sans", "Arial", "sans-serif"],
        "font.size": 10,
        "axes.edgecolor": GRID_COLOR,
        "axes.labelcolor": TEXT_COLOR,
        "xtick.color": TEXT_COLOR,
        "ytick.color": TEXT_COLOR,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.titleweight": "bold",
        "axes.titlesize": 11,
        "figure.dpi": 100,
    }
)

_SVG_HEAD = re.compile(r"^.*?(<svg\b)", re.S)


def render(fig, fmt: str) -> str | bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format=fmt, bbox_inches="tight", dpi=160 if fmt == "png" else None, transparent=fmt == "svg")
    plt.close(fig)
    data = buf.getvalue()
    if fmt != "svg":
        return data
    # размеры в pt оставляем: в HTML график показывается в натуральную величину
    # и только ужимается (max-width: 100%), поэтому шрифты на всех графиках одинаковые
    svg = _SVG_HEAD.sub(r"\1", data.decode("utf-8"), count=1)
    return svg.replace("<svg ", '<svg class="chart" ', 1)


def _hbar(ax, labels: Sequence[str], values: Sequence[float], colors, fmt: str = "{:g}") -> None:
    y = range(len(labels))
    bars = ax.barh(list(y), values, color=colors, height=0.65)
    ax.set_yticks(list(y), labels)
    ax.invert_yaxis()
    ax.grid(axis="x", color=GRID_COLOR, linewidth=0.8)
    ax.set_axisbelow(True)
    vmax = max(values) if values else 1
    for bar, v in zip(bars, values):
        ax.text(bar.get_width() + vmax * 0.01, bar.get_y() + bar.get_height() / 2, fmt.format(v),
                va="center", fontsize=9, color=TEXT_COLOR)
    ax.set_xlim(0, vmax * 1.15 if vmax else 1)


def bar_chart(data: Mapping[str, float], title: str, fmt: str, top: int = 15, color: str = ACCENT):
    items = list(data.items())[:top]
    if not items:
        return None
    fig, ax = plt.subplots(figsize=(6.4, 0.32 * len(items) + 0.9))
    _hbar(ax, [k for k, _ in items], [v for _, v in items], color)
    ax.set_title(title, loc="left")
    return render(fig, fmt)


def emotion_profile_chart(profile: Mapping[str, float], title: str, fmt: str):
    labels = [lab for lab in ALL_LABELS if lab in profile]
    fig, ax = plt.subplots(figsize=(6.4, 2.6))
    _hbar(ax, [EMOTION_RU[lab] for lab in labels], [profile[lab] * 100 for lab in labels],
          [EMOTION_COLORS[lab] for lab in labels], fmt="{:.1f}%")
    ax.set_title(title, loc="left")
    return render(fig, fmt)


def emotion_counts_chart(counts: Mapping[str, int], title: str, fmt: str):
    labels = [lab for lab in ALL_LABELS if counts.get(lab)]
    if not labels:
        return None
    fig, ax = plt.subplots(figsize=(6.4, 0.32 * len(labels) + 0.9))
    _hbar(ax, [EMOTION_RU[lab] for lab in labels], [counts[lab] for lab in labels],
          [EMOTION_COLORS[lab] for lab in labels], fmt="{:g}")
    ax.set_title(title, loc="left")
    return render(fig, fmt)


def lexicon_chart(totals: Mapping[str, float], title: str, fmt: str):
    if not totals or not any(totals.values()):
        return None
    labels = [e for e in EMOTIONS if e in totals]
    fig, ax = plt.subplots(figsize=(6.4, 2.3))
    _hbar(ax, [EMOTION_RU[e] for e in labels], [totals[e] for e in labels],
          [EMOTION_COLORS[e] for e in labels], fmt="{:.1f}")
    ax.set_title(title, loc="left")
    return render(fig, fmt)


def emotion_dynamics_chart(sentences: Sequence[SentenceInfo], fmt: str):
    scored = [s for s in sentences if s.emotion]
    if len(scored) < 2:
        return None
    window = dynamics_window(len(scored))
    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    x = [s.index + 1 for s in scored]
    for e in EMOTIONS:
        ys = rolling([s.emotion.get(e, 0.0) for s in scored], window)
        ax.plot(x, ys, color=EMOTION_COLORS[e], label=EMOTION_RU[e], linewidth=1.8)
    ax.set_ylim(0, 1)
    ax.set_xlim(x[0], x[-1])
    ax.set_xlabel("номер предложения")
    ax.set_ylabel("вероятность")
    ax.grid(color=GRID_COLOR, linewidth=0.8)
    ax.set_axisbelow(True)
    suffix = f" (скользящее среднее по {window})" if window > 1 else ""
    ax.set_title("Динамика эмоций по ходу текста" + suffix, loc="left")
    ax.legend(ncol=5, fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.22))
    return render(fig, fmt)


def corpus_emotions_chart(texts: Sequence[TextResult], fmt: str):
    rows = [t for t in texts if t.emotions and t.emotions.profile]
    if len(rows) < 2:
        return None
    fig, ax = plt.subplots(figsize=(7.2, 0.45 * len(rows) + 1.2))
    names = [t.name if len(t.name) <= 40 else t.name[:37] + "…" for t in rows]
    left = [0.0] * len(rows)
    for lab in ALL_LABELS:
        shares = []
        for t in rows:
            total = sum(t.emotions.profile.values()) or 1
            shares.append(t.emotions.profile.get(lab, 0.0) / total * 100)
        ax.barh(names, shares, left=left, color=EMOTION_COLORS[lab], label=EMOTION_RU[lab], height=0.6)
        left = [a + b for a, b in zip(left, shares)]
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("доля в эмоциональном профиле, %")
    ax.set_title("Сравнение эмоциональных профилей текстов", loc="left")
    ax.legend(ncol=6, fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.25))
    return render(fig, fmt)
