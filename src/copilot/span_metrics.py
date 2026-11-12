"""Precision, recall and F1 for predicted spans against labeled spans.

A predicted span matches a labeled span when their intersection-over-union is
at least ``min_overlap`` (0.5 by default) and, unless told otherwise, they have
the same entity type. Each span is matched at most once.

``char_coverage`` answers a different question, the one that matters for
leakage: of all labeled characters, how many were covered by *any* predicted
span, whatever its type.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    """A half-open character range ``[start, end)`` with an entity type."""

    start: int
    end: int
    entity_type: str


@dataclass(frozen=True)
class Counts:
    """True positives, false positives and false negatives."""

    tp: int = 0
    fp: int = 0
    fn: int = 0

    def __add__(self, other: Counts) -> Counts:
        """Sum two sets of counts."""
        return Counts(self.tp + other.tp, self.fp + other.fp, self.fn + other.fn)

    @property
    def support(self) -> int:
        """Number of labeled spans."""
        return self.tp + self.fn

    @property
    def precision(self) -> float | None:
        """TP / (TP + FP), or None when nothing was predicted."""
        predicted = self.tp + self.fp
        return self.tp / predicted if predicted else None

    @property
    def recall(self) -> float | None:
        """TP / (TP + FN), or None when nothing was labeled."""
        return self.tp / self.support if self.support else None

    @property
    def f1(self) -> float | None:
        """Harmonic mean of precision and recall, or None when either is undefined."""
        precision, recall = self.precision, self.recall
        if precision is None or recall is None:
            return None
        if precision + recall == 0:
            return 0.0
        return 2 * precision * recall / (precision + recall)


def iou(a: Span, b: Span) -> float:
    """Intersection over union of two spans' character ranges."""
    intersection = max(0, min(a.end, b.end) - max(a.start, b.start))
    union = (a.end - a.start) + (b.end - b.start) - intersection
    return intersection / union if union else 0.0


def match_spans(
    gold: Sequence[Span],
    predicted: Sequence[Span],
    *,
    min_overlap: float = 0.5,
    type_aware: bool = True,
) -> dict[str, Counts]:
    """Match predictions to labels within one text and count the outcomes per type.

    Pairs are matched greedily from the highest overlap down. An unmatched label
    is a false negative for its type; an unmatched prediction is a false
    positive for its type. With ``type_aware=False`` a match is credited to the
    label's type.
    """
    candidates = sorted(
        (
            (iou(g, p), gold_index, predicted_index)
            for gold_index, g in enumerate(gold)
            for predicted_index, p in enumerate(predicted)
            if not type_aware or g.entity_type == p.entity_type
        ),
        key=lambda item: -item[0],
    )
    matched_gold: set[int] = set()
    matched_predicted: set[int] = set()
    for overlap, gold_index, predicted_index in candidates:
        if overlap < min_overlap:
            break
        if gold_index in matched_gold or predicted_index in matched_predicted:
            continue
        matched_gold.add(gold_index)
        matched_predicted.add(predicted_index)

    counts: dict[str, Counts] = {}

    def bump(entity_type: str, delta: Counts) -> None:
        counts[entity_type] = counts.get(entity_type, Counts()) + delta

    for gold_index, g in enumerate(gold):
        bump(g.entity_type, Counts(tp=1) if gold_index in matched_gold else Counts(fn=1))
    for predicted_index, p in enumerate(predicted):
        if predicted_index not in matched_predicted:
            bump(p.entity_type, Counts(fp=1))
    return counts


def merge_counts(parts: Iterable[Mapping[str, Counts]]) -> dict[str, Counts]:
    """Add up per-type counts from several texts."""
    total: dict[str, Counts] = {}
    for part in parts:
        for entity_type, counts in part.items():
            total[entity_type] = total.get(entity_type, Counts()) + counts
    return total


def micro_total(per_type: Mapping[str, Counts], entity_types: Iterable[str]) -> Counts:
    """Sum the counts of the given types (micro-average)."""
    total = Counts()
    for entity_type in entity_types:
        total = total + per_type.get(entity_type, Counts())
    return total


def char_coverage(gold: Sequence[Span], predicted: Sequence[Span]) -> tuple[int, int]:
    """Return ``(covered, total)`` labeled characters, ignoring entity types."""
    labeled: set[int] = set()
    for span in gold:
        labeled.update(range(span.start, span.end))
    masked: set[int] = set()
    for span in predicted:
        masked.update(range(span.start, span.end))
    return len(labeled & masked), len(labeled)
