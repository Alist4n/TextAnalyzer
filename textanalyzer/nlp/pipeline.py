"""Конвейер анализа: модели загружаются один раз и переиспользуются для всех текстов."""

from __future__ import annotations

import re
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Sequence

from .. import __version__
from ..config import SPACY_MODEL, AnalysisOptions, emotion_model_source, lexicon_path, lexicon_rules_path
from . import emotions as emo
from . import morphology, stats, syntax
from .labels import ENTITY_RU, dep_ru, feats_ru, school_pos
from .models import CorpusResult, EntityInfo, SentenceInfo, TextResult, TokenInfo

ProgressFn = Callable[[float, str], None]
LogFn = Callable[[str], None]


class AnalysisCancelled(Exception):
    pass


def _noop_progress(_fraction: float, _message: str) -> None:
    pass


def split_paragraphs(text: str) -> list[str]:
    """Перевод строки считаем границей предложения: заголовки и строки без точки не склеиваются."""
    return [ln.strip() for ln in re.split(r"\n+", text) if ln.strip()]


def keep_hyphenated_words(nlp) -> None:
    """Не делить «где-то», «по-русски», «крепко-крепко» на три токена.

    Модели ru_core_news обучены на корпусе Nerus (токенизация razdel), где такие слова
    цельные, а стандартный токенизатор spaCy режет дефис между буквами.
    """
    from spacy.lang.char_classes import ALPHA
    from spacy.util import compile_infix_regex

    # шаблон ищем по поведению, а не по тексту: его запись меняется между версиями spaCy
    infixes = [p for p in nlp.Defaults.infixes if not re.search(p, "где-то")]
    if len(infixes) != len(nlp.Defaults.infixes):
        # длинные тире и двойной дефис между словами по-прежнему отделяем
        infixes.append(r"(?<=[{a}0-9])(?:—|–|--+)(?=[{a}])".format(a=ALPHA))
        nlp.tokenizer.infix_finditer = compile_infix_regex(infixes).finditer


class Analyzer:
    def __init__(self, options: AnalysisOptions | None = None, lexicon_file: Path | None = None) -> None:
        self.options = options or AnalysisOptions()
        # явно заданный файл словаря важнее выбора в настройках (тесты подставляют свой маленький)
        self._lexicon_override = Path(lexicon_file) if lexicon_file else None
        self._nlp = None
        self._morph = None
        self._emotion_model = None
        self._lexicon = None

    @property
    def lexicon_file(self) -> Path:
        """Словарь эмоций по настройке options.lexicon: скачанный NRC EmoLex или ручной из пакета."""
        return self._lexicon_override or lexicon_path(self.options.lexicon)

    def unload_lexicon(self) -> None:
        """Файл словаря пересобран (NRC скачан заново) — при следующем анализе прочитать его снова."""
        self._lexicon = None

    # --- загрузка моделей -------------------------------------------------
    def ensure_loaded(self, log: LogFn = print) -> None:
        if self._nlp is None:
            log(f"Загрузка языковой модели {SPACY_MODEL}…")
            import spacy

            self._nlp = spacy.load(SPACY_MODEL)
            self._nlp.max_length = 5_000_000
            keep_hyphenated_words(self._nlp)
        if self._morph is None:
            log("Загрузка морфологического словаря pymorphy3…")
            self._morph = morphology.MorphExtras()
        if self.options.use_model and self._emotion_model is None:
            source = emotion_model_source()
            log(f"Загрузка модели эмоций ({source})…")
            self._emotion_model = emo.EmotionModel(source)
        # окно переиспользует Analyzer между запусками: при смене словаря в настройках загружаем другой
        if self.options.use_lexicon and (self._lexicon is None or self._lexicon.path != self.lexicon_file):
            path = self.lexicon_file
            nrc = self._lexicon_override is None and self.options.lexicon == "nrc"
            missing = emo.LEXICON_MISSING_MESSAGE if nrc else f"Файл словаря эмоций не найден: {path}"
            self._lexicon = emo.EmotionLexicon(path, lexicon_rules_path(), missing)
            log(f"Словарь эмоций: {self._lexicon.name or path.name}, {len(self._lexicon)} слов")

    def models_info(self) -> dict[str, str]:
        # только то, что участвовало в этом анализе: загруженное ранее, но выключенное в настройках, не пишем
        info = {}
        if self._nlp is not None:
            info["spacy"] = f"{self._nlp.meta.get('lang')}_{self._nlp.meta.get('name')} {self._nlp.meta.get('version')}"
        if self._emotion_model is not None and self.options.use_model:
            info["emotions"] = f"{self._emotion_model.source} ({self._emotion_model.device})"
        if self._lexicon is not None and self.options.use_lexicon:
            info["lexicon"] = f"{self._lexicon.name or self._lexicon.path.name}, {len(self._lexicon)} слов"
            if self._lexicon.meta.get("credit"):
                info["lexicon_credit"] = self._lexicon.meta["credit"]
            elif self._lexicon.meta.get("description"):
                info["lexicon_note"] = self._lexicon.meta["description"]
        return info

    # --- анализ -----------------------------------------------------------
    def analyze_corpus(
        self,
        items: Sequence[tuple[str, str, str | None]],
        progress: ProgressFn = _noop_progress,
        cancelled: Callable[[], bool] = lambda: False,
        log: LogFn = print,
    ) -> CorpusResult:
        """items — (название, текст, путь к файлу или None)."""
        progress(0.0, "Загрузка моделей…")
        self.ensure_loaded(log)
        started = time.perf_counter()  # время анализа — без однократной загрузки моделей
        results = []
        n = len(items)
        for k, (name, text, source) in enumerate(items):
            if cancelled():
                raise AnalysisCancelled()

            def sub_progress(fraction: float, message: str, k=k, name=name) -> None:
                progress((k + fraction) / n, f"[{k + 1}/{n}] {name}: {message}")

            results.append(self.analyze_text(name, text, source, sub_progress, cancelled))
            log(f"Готово: {name} — {results[-1].stats.n_words} слов, {results[-1].elapsed:.1f} с")
        progress(1.0, "Анализ завершён")
        return CorpusResult(
            texts=results,
            options=self.options.to_dict(),
            created=datetime.now().isoformat(timespec="seconds"),
            app_version=__version__,
            models=self.models_info(),
            elapsed=round(time.perf_counter() - started, 2),
        )

    def analyze_text(
        self,
        name: str,
        text: str,
        source: str | None = None,
        progress: ProgressFn = _noop_progress,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> TextResult:
        started = time.perf_counter()
        opts = self.options
        text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")

        progress(0.05, "разбор текста")
        disable = [] if opts.entities else ["ner"]
        docs = list(self._nlp.pipe(split_paragraphs(text), disable=disable))
        self._morph.fix_lemmas(docs)
        if cancelled():
            raise AnalysisCancelled()

        spans = [s for d in docs for s in d.sents if any(syntax.is_word(t) for t in s)]
        words = [t for d in docs for t in d if syntax.is_word(t)]
        lemmas = [t.lemma_.lower() for t in words]

        progress(0.4, "морфология и синтаксис")
        sentences = [self._sentence_info(k, span) for k, span in enumerate(spans)]

        result = TextResult(
            name=name,
            source=source,
            text=text,
            stats=stats.compute_stats(text, len(spans), words, lemmas),
            sentences=sentences,
        )

        if opts.morphology:
            result.pos_distribution = morphology.pos_distribution(words)
            result.feature_distributions = morphology.feature_distributions(words)
            result.top_lemmas = morphology.top_lemmas(words, opts.top_n)
            result.unknown_words, ambiguity = self._morph.analyze(words, opts.top_n)
            result.ambiguity_rate = round(ambiguity, 3)

        if opts.syntax:
            self._syntax_summary(result)

        if opts.entities:
            result.entities = self._entities(docs)

        if opts.emotions:
            self._emotions(result, progress, cancelled)

        result.elapsed = round(time.perf_counter() - started, 2)
        progress(1.0, "готово")
        return result

    # --- части анализа ----------------------------------------------------
    def _sentence_info(self, index: int, span) -> SentenceInfo:
        opts = self.options
        info = SentenceInfo(
            index=index,
            text=span.text.strip(),
            n_words=sum(1 for t in span if syntax.is_word(t)),
        )
        for tok in span:
            if tok.is_space:
                continue
            feats = tok.morph.to_dict()
            d = syntax.dep(tok)
            info.tokens.append(
                TokenInfo(
                    i=tok.i - span.start,
                    text=tok.text,
                    lemma=morphology.display_lemma(tok),
                    pos=tok.pos_,
                    pos_ru=school_pos(tok.pos_, feats),
                    feats=feats,
                    feats_ru=feats_ru(feats),
                    dep=d,
                    dep_ru=dep_ru(d),
                    head=tok.head.i - span.start,
                    member=syntax.member_of(tok) if opts.syntax else "",
                    is_punct=tok.is_punct,
                    space_after=bool(tok.whitespace_),
                    is_stop=tok.is_stop,
                )
            )
        if opts.syntax:
            for key, value in syntax.analyze_sentence(span, self._morph.is_imperative).items():
                setattr(info, key, value)
        if self._lexicon is not None and opts.use_lexicon:
            info.lexicon_hits = self._lexicon.analyze(span)
        return info

    @staticmethod
    def _syntax_summary(result: TextResult) -> None:
        sents = result.sentences
        result.dep_distribution = dict(
            Counter(t.dep for s in sents for t in s.tokens if t.dep not in ("punct",)).most_common()
        )
        result.purpose_distribution = dict(Counter(s.purpose for s in sents).most_common())
        result.structure_distribution = dict(Counter(s.structure for s in sents).most_common())
        n = len(sents) or 1
        result.syntax_summary = {
            "avg_depth": round(sum(s.depth for s in sents) / n, 2),
            "max_depth": max((s.depth for s in sents), default=0),
            "avg_clauses": round(sum(s.n_clauses for s in sents) / n, 2),
            "complex_share": round(sum(1 for s in sents if s.n_clauses > 1) / n, 3),
            "exclamatory_share": round(sum(1 for s in sents if s.exclamatory) / n, 3),
            "mean_dep_distance": round(sum(s.mean_dep_distance for s in sents) / n, 3),
            "participial_count": sum(len(s.participial) for s in sents),
            "adverbial_count": sum(len(s.adverbial) for s in sents),
            "homogeneous_count": sum(len(s.homogeneous) for s in sents),
        }

    def _entities(self, docs: Iterable) -> list[EntityInfo]:
        counts: Counter[tuple[str, str]] = Counter()
        for d in docs:
            for ent in d.ents:
                # «Библиотека работает…» в начале предложения NER иногда принимает за имя
                if not any(t.pos_ == "PROPN" or (t.text.isupper() and len(t.text) > 1) for t in ent):
                    continue
                counts[(self._morph.normalize_entity(ent), ent.label_)] += 1
        return [
            EntityInfo(text=t, label=lab, label_ru=ENTITY_RU.get(lab, lab), count=c)
            for (t, lab), c in counts.most_common()
        ]

    def _emotions(self, result: TextResult, progress: ProgressFn, cancelled) -> None:
        opts = self.options
        if self._emotion_model is not None and opts.use_model and result.sentences:
            texts = [s.text for s in result.sentences]

            def model_progress(done: int, total: int) -> None:
                if cancelled():
                    raise AnalysisCancelled()
                progress(0.5 + 0.45 * done / total, f"эмоции {done}/{total}")

            probs = self._emotion_model.predict(texts, progress=model_progress)
            for s, p in zip(result.sentences, probs):
                s.emotion = p
                s.emotion_dominant = emo.dominant_label(p)
        result.emotions = emo.summarize(result.sentences, result.stats.n_words, opts.emotion_method, opts.top_n)
