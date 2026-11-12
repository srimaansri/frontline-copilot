"""Span matching and the precision / recall arithmetic."""

import pytest

from copilot.span_metrics import (
    Counts,
    Span,
    char_coverage,
    iou,
    match_spans,
    merge_counts,
    micro_total,
)


def test_iou_of_identical_spans_is_one() -> None:
    assert iou(Span(0, 10, "A"), Span(0, 10, "B")) == 1.0


def test_iou_of_disjoint_spans_is_zero() -> None:
    assert iou(Span(0, 5, "A"), Span(5, 10, "A")) == 0.0


def test_iou_of_partial_overlap() -> None:
    assert iou(Span(0, 10, "A"), Span(5, 15, "A")) == pytest.approx(5 / 15)


def test_iou_of_empty_spans_is_zero() -> None:
    assert iou(Span(3, 3, "A"), Span(3, 3, "A")) == 0.0


def test_exact_match_is_a_true_positive() -> None:
    counts = match_spans([Span(0, 10, "PHONE")], [Span(0, 10, "PHONE")])

    assert counts == {"PHONE": Counts(tp=1)}


def test_overlap_at_the_threshold_matches() -> None:
    # intersection 10, union 20 -> IoU exactly 0.5
    counts = match_spans([Span(0, 10, "ADDRESS")], [Span(0, 20, "ADDRESS")])

    assert counts == {"ADDRESS": Counts(tp=1)}


def test_overlap_below_the_threshold_is_a_miss_and_a_false_positive() -> None:
    counts = match_spans([Span(0, 10, "ADDRESS")], [Span(0, 21, "ADDRESS")])

    assert counts == {"ADDRESS": Counts(fp=1, fn=1)}


def test_wrong_type_is_a_miss_and_a_false_positive() -> None:
    counts = match_spans([Span(0, 10, "PHONE")], [Span(0, 10, "ACCOUNT")])

    assert counts == {"PHONE": Counts(fn=1), "ACCOUNT": Counts(fp=1)}


def test_type_can_be_ignored() -> None:
    counts = match_spans([Span(0, 10, "PHONE")], [Span(0, 10, "ACCOUNT")], type_aware=False)

    assert counts == {"PHONE": Counts(tp=1)}


def test_each_prediction_matches_only_one_label() -> None:
    gold = [Span(0, 10, "PERSON"), Span(0, 10, "PERSON")]

    counts = match_spans(gold, [Span(0, 10, "PERSON")])

    assert counts == {"PERSON": Counts(tp=1, fn=1)}


def test_best_overlap_wins() -> None:
    gold = [Span(0, 10, "PERSON")]
    predicted = [Span(0, 16, "PERSON"), Span(0, 10, "PERSON")]

    counts = match_spans(gold, predicted)

    assert counts == {"PERSON": Counts(tp=1, fp=1)}


def test_no_labels_and_no_predictions_gives_no_counts() -> None:
    assert match_spans([], []) == {}


def test_counts_metrics() -> None:
    counts = Counts(tp=8, fp=2, fn=2)

    assert counts.support == 10
    assert counts.precision == pytest.approx(0.8)
    assert counts.recall == pytest.approx(0.8)
    assert counts.f1 == pytest.approx(0.8)


def test_metrics_are_undefined_without_data() -> None:
    empty = Counts()

    assert empty.precision is None
    assert empty.recall is None
    assert empty.f1 is None


def test_f1_is_zero_when_nothing_is_right() -> None:
    assert Counts(fp=1, fn=1).f1 == 0.0


def test_merge_and_micro_total() -> None:
    merged = merge_counts(
        [{"A": Counts(tp=1), "B": Counts(fn=1)}, {"A": Counts(fp=1)}, {"C": Counts(tp=5)}]
    )

    assert merged == {"A": Counts(tp=1, fp=1), "B": Counts(fn=1), "C": Counts(tp=5)}
    assert micro_total(merged, ["A", "B", "MISSING"]) == Counts(tp=1, fp=1, fn=1)


def test_char_coverage_ignores_type_and_counts_characters() -> None:
    gold = [Span(0, 10, "PHONE"), Span(20, 30, "PERSON")]
    predicted = [Span(0, 10, "ACCOUNT"), Span(25, 40, "PERSON")]

    assert char_coverage(gold, predicted) == (15, 20)


def test_char_coverage_with_no_labels() -> None:
    assert char_coverage([], [Span(0, 5, "X")]) == (0, 0)
