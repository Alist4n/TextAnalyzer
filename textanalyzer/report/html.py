"""HTML-отчёт: один самодостаточный файл.

Графики строятся из HTML/CSS и встроенного SVG, без matplotlib: так отчёт по сотням
текстов (например, строк таблицы) собирается за секунды, а текст на графиках
остаётся чётким и поиск по странице его находит.
"""

from __future__ import annotations

from html import escape
from typing import Callable, Iterable, Mapping, Sequence

from jinja2 import Environment, PackageLoader, select_autoescape
from markupsafe import Markup

from ..nlp.emotions import ALL_LABELS, EMOTION_RU, EMOTIONS, NEUTRAL
from ..nlp.labels import DEP_RU, DEP_SHORT_RU, dep_ru, dep_short_ru, pos_short_ru
from ..nlp.models import CorpusResult, SentenceInfo, TextResult
from ..nlp.syntax import format_bases
from .common import EMOTION_COLORS, corpus_overview, dynamics_window, rolling


def highlight_sentence(s: SentenceInfo) -> Markup:
    """Текст предложения с подсветкой слов из эмоционального словаря."""
    hits: dict[int, list] = {}
    for h in s.lexicon_hits:
        hits.setdefault(h.token_i, []).append(h)
    parts = []
    for t in s.tokens:
        word = escape(t.text)
        if t.i in hits:
            hs = hits[t.i]
            main = max(hs, key=lambda h: h.weight)
            title = "; ".join(
                f"{EMOTION_RU[h.emotion]}: {h.weight:g}"
                + (" (отрицание)" if h.negated else "")
                + (f", модификатор «{h.modifier}»" if h.modifier else "")
                for h in hs
            )
            cls = f"emo emo-{main.emotion}" + (" neg" if main.negated else "")
            word = f'<mark class="{cls}" title="{escape(title)}">{word}</mark>'
        parts.append(word + (" " if t.space_after else ""))
    return Markup("".join(parts).strip())


def emotion_bar(probs: dict[str, float] | None, wide: bool = False) -> Markup:
    """Полоска из долей эмоций (вероятности нормированы к 100%)."""
    if not probs:
        return Markup("")
    total = sum(probs.values()) or 1.0
    segs = []
    for lab in ALL_LABELS:
        p = probs.get(lab, 0.0)
        if p / total < 0.01:
            continue
        segs.append(
            f'<span style="width:{p / total * 100:.1f}%;background:{EMOTION_COLORS[lab]}" '
            f'title="{EMOTION_RU[lab]}: {p:.0%}"></span>'
        )
    cls = "ebar wide" if wide else "ebar"
    return Markup(f'<div class="{cls}">{"".join(segs)}</div>')


def _fmt_number(v: float) -> str:
    if float(v).is_integer():
        return f"{int(v):,}".replace(",", " ")
    return f"{v:.1f}"


def hbars(
    items: Iterable[tuple[str, float]],
    title: str = "",
    color: str = "var(--accent)",
    colors: Sequence[str] | None = None,
    value_fmt: Callable[[float], str] | None = None,
) -> Markup:
    """Горизонтальная столбчатая диаграмма на HTML/CSS."""
    items = [(str(k), float(v)) for k, v in items]
    if not items:
        return Markup("")
    top = max(v for _, v in items) or 1.0
    rows = []
    for i, (label, v) in enumerate(items):
        fill = colors[i] if colors else color
        shown = value_fmt(v) if value_fmt else _fmt_number(v)
        rows.append(
            f'<span class="bar-label" title="{escape(label)}">{escape(label)}</span>'
            f'<span class="bar-track"><span class="bar-fill" style="width:{v / top * 100:.1f}%;background:{fill}"></span></span>'
            f'<span class="bar-value">{escape(shown)}</span>'
        )
    head = f'<div class="chart-title">{escape(title)}</div>' if title else ""
    return Markup(f'<div class="chart">{head}<div class="bars">{"".join(rows)}</div></div>')


def emotion_hbars(values: Mapping[str, float] | None, title: str, percent: bool = True,
                  labels: Sequence[str] = ALL_LABELS) -> Markup:
    if not values:
        return Markup("")
    keys = [k for k in labels if k in values]
    scale = 100 if percent else 1
    fmt = (lambda v: f"{v:.1f}%") if percent else _fmt_number
    return hbars([(EMOTION_RU[k], values[k] * scale) for k in keys], title,
                 colors=[EMOTION_COLORS[k] for k in keys], value_fmt=fmt)


def dynamics_svg(sentences: Sequence[SentenceInfo]) -> Markup:
    """Линии вероятностей эмоций по ходу текста (встроенный SVG)."""
    scored = [s for s in sentences if s.emotion]
    if len(scored) < 2:
        return Markup("")
    window = dynamics_window(len(scored))
    width, height, left, right, top, bottom = 720, 190, 34, 12, 10, 26
    n = len(scored)

    def x(i: int) -> float:
        return left + (width - left - right) * i / (n - 1)

    def y(v: float) -> float:
        return top + (height - top - bottom) * (1 - v)

    parts = [f'<svg class="dyn" viewBox="0 0 {width} {height}" role="img" aria-label="Динамика эмоций">']
    for v in (0.0, 0.5, 1.0):
        parts.append(f'<line x1="{left}" x2="{width - right}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>')
        parts.append(f'<text x="{left - 6}" y="{y(v) + 4:.1f}" text-anchor="end">{v:g}</text>')
    ticks = sorted({0, n - 1} | {round(k * (n - 1) / 5) for k in range(1, 5)})
    for i in ticks:
        parts.append(f'<text x="{x(i):.1f}" y="{height - 8}" text-anchor="middle">{scored[i].index + 1}</text>')
    for e in EMOTIONS:
        ys = rolling([s.emotion.get(e, 0.0) for s in scored], window)
        points = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(ys))
        parts.append(f'<polyline points="{points}" fill="none" stroke="{EMOTION_COLORS[e]}" stroke-width="2">'
                     f'<title>{EMOTION_RU[e]}</title></polyline>')
    parts.append("</svg>")
    title = "Динамика эмоций по ходу текста" + (f" (скользящее среднее по {window})" if window > 1 else "")
    legend = "".join(
        f'<span><i style="background:{EMOTION_COLORS[e]}"></i>{EMOTION_RU[e]}</span>' for e in EMOTIONS
    )
    return Markup(
        f'<div class="chart"><div class="chart-title">{title}</div>{"".join(parts)}'
        f'<div class="legend small">{legend}<span class="muted">по оси X — номер предложения</span></div></div>'
    )


def dep_tree_svg(s: SentenceInfo) -> Markup:
    from spacy import displacy

    words = [t for t in s.tokens if not t.is_punct]
    if len(words) < 2:
        return Markup("")
    pos = {t.i: k for k, t in enumerate(words)}
    arcs = []
    for t in words:
        if t.dep == "root" or t.head == t.i or t.head not in pos:
            continue
        a, b = pos[t.i], pos[t.head]
        arcs.append({
            "start": min(a, b),
            "end": max(a, b),
            "label": dep_short_ru(t.dep),
            "dir": "left" if a < b else "right",
        })
    data = {"words": [{"text": t.text, "tag": pos_short_ru(t.pos_ru)} for t in words], "arcs": arcs}
    svg = displacy.render(
        data,
        style="dep",
        manual=True,
        minify=True,
        options={
            "compact": True,
            "distance": 105,
            "word_spacing": 28,
            "arrow_spacing": 10,
            "font": "inherit",
            "bg": "transparent",
            "color": "#26323f",
            "offset_x": 30,
        },
    )
    return Markup(svg)


def all_tokens(t: TextResult) -> list:
    return [tok for s in t.sentences for tok in s.tokens]


def dep_glossary() -> list[tuple[str, str]]:
    """Сокращения на дугах дерева -> расшифровка (одинаковые сокращения объединены)."""
    merged: dict[str, list[str]] = {}
    for code, short in DEP_SHORT_RU.items():
        if short:
            desc = DEP_RU.get(code, code)
            if desc not in merged.setdefault(short, []):
                merged[short].append(desc)
    return [(short, " / ".join(descs)) for short, descs in merged.items()]


def dep_items(t: TextResult, limit: int = 15) -> list[tuple[str, int]]:
    return [(f"{dep_ru(k)} ({k})", v) for k, v in list(t.dep_distribution.items())[:limit]]


def _env() -> Environment:
    env = Environment(
        loader=PackageLoader("textanalyzer", "report/templates"),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["pct"] = lambda v, digits=0: f"{(v or 0) * 100:.{digits}f}%"
    env.filters["num"] = lambda v: f"{v:,}".replace(",", " ") if isinstance(v, int) else f"{v:g}"
    env.globals.update(
        highlight_sentence=highlight_sentence,
        emotion_bar=emotion_bar,
        hbars=hbars,
        emotion_hbars=emotion_hbars,
        dynamics_svg=dynamics_svg,
        dep_tree_svg=dep_tree_svg,
        dep_items=dep_items,
        all_tokens=all_tokens,
        dep_glossary=dep_glossary,
        format_bases=format_bases,
        EMOTION_RU=EMOTION_RU,
        EMOTION_COLORS=EMOTION_COLORS,
        EMOTIONS=EMOTIONS,
        ALL_LABELS=ALL_LABELS,
        NEUTRAL=NEUTRAL,
    )
    return env


def render_html(corpus: CorpusResult) -> str:
    opts = corpus.options
    template = _env().get_template("report.html.j2")
    multi = len(corpus.texts) > 1
    return template.render(
        corpus=corpus,
        opts=opts,
        detailed=max(0, int(opts.get("detailed_texts", 30))),
        overview=corpus_overview(corpus, opts.get("top_n", 20)) if multi else None,
    )
