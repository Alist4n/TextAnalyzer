"""Определение эмоций: нейросетевой классификатор и словарный анализатор.

Модель — rubert-tiny2, дообученная на корпусе CEDR (мультиметочная
классификация предложений: радость, грусть, удивление, страх, гнев, нет эмоции).
Словарь даёт объяснимость: какие слова указывают на эмоцию, с учётом отрицаний
(«не рад») и усилителей («очень страшно») по дереву зависимостей.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable, Sequence

from spacy.tokens import Span, Token

from .models import EmotionSummary, LexiconHit, SentenceInfo

NEUTRAL = "no_emotion"
EMOTIONS = ["joy", "sadness", "surprise", "fear", "anger"]
ALL_LABELS = [NEUTRAL] + EMOTIONS
# ниже этого среднего уровня эмоция не считается «ведущей» (текст по сути нейтрален)
LEADING_THRESHOLD = 0.1

EMOTION_RU = {
    "joy": "радость",
    "sadness": "грусть",
    "surprise": "удивление",
    "fear": "страх",
    "anger": "гнев",
    NEUTRAL: "нейтрально",
}

ProgressFn = Callable[[int, int], None]

MODEL_HUB_HOST = "huggingface.co"
MODEL_MISSING_MESSAGE = (
    "Модель эмоций не найдена на диске, а скачать её нельзя: нет подключения к интернету.\n\n"
    "Скачайте модель один раз, когда интернет будет: .venv\\Scripts\\python scripts\\download_models.py "
    "(она сохранится в папку models, дальше интернет не нужен).\n\n"
    "Или выберите метод эмоций «Только словарь» (в командной строке --emotions lexicon): "
    "он работает без модели."
)


LEXICON_MISSING_MESSAGE = (
    "Словарь эмоций NRC EmoLex ещё не скачан.\n\n"
    "Скачайте его один раз, когда будет интернет (около 25 МБ): в окне программы — меню «Файл», "
    "пункт «Скачать словарь NRC EmoLex…», в командной строке — команда download-nrc "
    "(TextAnalyzer-cli download-nrc или python -m textanalyzer download-nrc). "
    "Лицензия NRC: бесплатно только для некоммерческого исследовательского и учебного использования.\n\n"
    "Или выберите словарь эмоций «Ручной (TextAnalyzer)» (в командной строке --lexicon manual) — "
    "он входит в программу, — или метод эмоций «Только нейросеть» (--emotions model)."
)


class ResourceUnavailableError(RuntimeError):
    """Нужного для анализа файла (модели, словаря) нет на диске — текст ошибки объясняет, что делать."""


class ModelUnavailableError(ResourceUnavailableError):
    """Модели эмоций нет ни в папке models, ни в кэше HuggingFace, и сети тоже нет."""


class LexiconUnavailableError(ResourceUnavailableError):
    """Словарь NRC EmoLex не скачан (его нельзя распространять вместе с программой)."""


def _norm(word: str) -> str:
    return word.lower().replace("ё", "е")


def hub_reachable(host: str = MODEL_HUB_HOST, timeout: float = 3.0) -> bool:
    import socket

    try:
        socket.create_connection((host, 443), timeout=timeout).close()
        return True
    except OSError:
        return False


class EmotionModel:
    def __init__(self, source: str, device: str | None = None) -> None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self._torch = torch
        self.source = source
        try:
            # сначала только с диска (папка models или кэш HuggingFace) — без обращений к сети;
            # иначе без интернета transformers около минуты повторяет запросы к хабу
            self.tokenizer = AutoTokenizer.from_pretrained(source, local_files_only=True)
            self.model = AutoModelForSequenceClassification.from_pretrained(source, local_files_only=True)
        except (OSError, ValueError):
            if Path(source).is_dir():
                raise  # локальная копия есть, но повреждена — показываем исходную ошибку
            if not hub_reachable():
                raise ModelUnavailableError(MODEL_MISSING_MESSAGE) from None
            self.tokenizer = AutoTokenizer.from_pretrained(source)
            self.model = AutoModelForSequenceClassification.from_pretrained(source)
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device).eval()
        id2label = self.model.config.id2label
        self.labels = [id2label[i] for i in range(self.model.config.num_labels)]

    def predict(self, texts: Sequence[str], batch_size: int = 32, progress: ProgressFn | None = None) -> list[dict[str, float]]:
        torch = self._torch
        out: list[dict[str, float]] = []
        with torch.inference_mode():
            for start in range(0, len(texts), batch_size):
                batch = list(texts[start : start + batch_size])
                enc = self.tokenizer(batch, return_tensors="pt", padding=True, truncation=True, max_length=512)
                enc = {k: v.to(self.device) for k, v in enc.items()}
                probs = torch.sigmoid(self.model(**enc).logits).cpu().tolist()
                for row in probs:
                    out.append({self.labels[i]: round(float(p), 4) for i, p in enumerate(row)})
                if progress:
                    progress(min(start + batch_size, len(texts)), len(texts))
        return out


class EmotionLexicon:
    """Эмоциональные слова (path: NRC EmoLex или ручной словарь) + правила анализа (rules_path: усилители, отрицания)."""

    def __init__(self, path: Path, rules_path: Path | None = None, missing_message: str = LEXICON_MISSING_MESSAGE) -> None:
        path = Path(path)
        if not path.exists():
            raise LexiconUnavailableError(missing_message)
        self.path = path
        data = json.loads(path.read_text(encoding="utf-8"))
        rules = json.loads(Path(rules_path).read_text(encoding="utf-8")) if rules_path else data
        self.meta: dict = data.get("_meta", {})
        self.entries: dict[str, list[tuple[str, float]]] = defaultdict(list)
        for emotion in EMOTIONS:
            for word, weight in data.get(emotion, {}).items():
                if float(weight) > 0:
                    self.entries[_norm(word)].append((emotion, float(weight)))
        self.modifiers: dict[str, float] = {_norm(k): float(v) for k, v in rules.get("modifiers", {}).items()}
        self.negations: set[str] = {_norm(w) for w in rules.get("negations", ["не", "ни", "нет"])}
        self.negating_preps: set[str] = {_norm(w) for w in rules.get("negating_prepositions", ["без"])}
        self.transparent_verbs: set[str] = {_norm(w) for w in rules.get("negation_transparent_verbs", [])}

    def __len__(self) -> int:
        return len(self.entries)

    @property
    def name(self) -> str:
        return self.meta.get("name", "")

    def lookup(self, tok: Token) -> list[tuple[str, float]]:
        # только по лемме: поиск по словоформе даёт ложные совпадения («вина» от «вино»)
        return self.entries.get(_norm(tok.lemma_), [])

    def _is_negated(self, tok: Token) -> bool:
        children = list(tok.children)
        if any(_norm(c.text) in self.negations for c in children):
            return True
        if any(c.dep_ == "case" and _norm(c.text) in self.negating_preps for c in children):
            return True
        if tok.i > 0 and _norm(tok.doc[tok.i - 1].text) in self.negations:
            return True
        head = tok.head
        if head.i == tok.i:
            return False
        head_negated = any(_norm(c.text) in self.negations for c in head.children)
        if tok.dep_ in ("obj", "iobj", "obl", "nsubj"):
            if _norm(head.text) in self.negations:  # «нет радости»
                return True
            if head_negated and _norm(head.lemma_) in self.transparent_verbs:
                return True  # «не испытываю страха»
        if tok.dep_ == "xcomp" and head_negated:
            return True  # «не хочу грустить», «не стану бояться»
        return False

    def _modifier(self, tok: Token) -> tuple[float, Token | None]:
        for c in tok.children:
            if c.dep_ == "advmod" and _norm(c.text) in self.modifiers:
                return self.modifiers[_norm(c.text)], c
        if tok.i > 0:
            prev = tok.doc[tok.i - 1]
            if _norm(prev.text) in self.modifiers and prev.head.i == tok.i:
                return self.modifiers[_norm(prev.text)], prev
        return 1.0, None

    def analyze(self, span: Span) -> list[LexiconHit]:
        hits: list[LexiconHit] = []
        modifier_tokens: set[int] = set()
        candidates = []
        for tok in span:
            if tok.pos_ == "PROPN" or tok.is_punct:
                continue
            if tok.dep_ == "advmod" and _norm(tok.text) in self.modifiers:
                continue  # «ужасно устал», «слабо верится» — степень, а не эмоция
            entries = self.lookup(tok)
            if entries:
                mult, mod = self._modifier(tok)
                if mod is not None:
                    modifier_tokens.add(mod.i)
                candidates.append((tok, entries, mult, mod))
        for tok, entries, mult, mod in candidates:
            if tok.i in modifier_tokens:
                continue  # «страшно» в «страшно рад» — усилитель, а не страх
            negated = self._is_negated(tok)
            for emotion, weight in entries:
                hits.append(
                    LexiconHit(
                        token=tok.text,
                        lemma=tok.lemma_.lower(),
                        emotion=emotion,
                        weight=0.0 if negated else round(weight * mult, 3),
                        negated=negated,
                        modifier=mod.text if mod is not None else "",
                        token_i=tok.i - span.start,
                    )
                )
        return hits


def summarize(sentences: Sequence[SentenceInfo], n_words: int, method: str, top_n: int = 15) -> EmotionSummary:
    summary = EmotionSummary(method=method)

    scored = [s for s in sentences if s.emotion]
    if scored:
        weights = [max(1, s.n_words) for s in scored]
        total_w = sum(weights)
        labels = list(scored[0].emotion.keys())
        profile = {
            lab: round(sum(s.emotion[lab] * w for s, w in zip(scored, weights)) / total_w, 4)
            for lab in labels
        }
        summary.profile = profile
        summary.dominant = max(profile, key=profile.get)
        emo_only = {k: v for k, v in profile.items() if k != NEUTRAL}
        if emo_only:
            best = max(emo_only, key=emo_only.get)
            summary.leading_emotion = best if emo_only[best] >= LEADING_THRESHOLD else None
        dom_counts = Counter(s.emotion_dominant for s in scored)
        summary.sentence_share = {lab: round(dom_counts.get(lab, 0) / len(scored), 4) for lab in labels}

    all_hits = [h for s in sentences for h in s.lexicon_hits]
    if method in ("both", "lexicon"):
        totals = {e: 0.0 for e in EMOTIONS}
        tops: dict[str, Counter] = {e: Counter() for e in EMOTIONS}
        negated: Counter[str] = Counter()
        for h in all_hits:
            if h.negated:
                negated[f"{h.lemma} ({EMOTION_RU[h.emotion]})"] += 1
                continue
            totals[h.emotion] += h.weight
            tops[h.emotion][h.lemma] += 1
        summary.lexicon_totals = {e: round(v, 3) for e, v in totals.items()}
        summary.lexicon_density = {e: round(v / n_words * 100, 3) if n_words else 0.0 for e, v in totals.items()}
        best = max(totals, key=totals.get)
        summary.lexicon_dominant = best if totals[best] > 0 else None
        summary.lexicon_top = {e: c.most_common(top_n) for e, c in tops.items() if c}
        summary.lexicon_negated = negated.most_common(top_n)
    return summary


def dominant_label(probs: dict[str, float]) -> str:
    return max(probs, key=probs.get)
