"""The deliberately wrong answers, and the judging of them with fake judges. No model calls."""

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import mlflow
import pytest
from mlflow.entities import Feedback
from mlflow.genai.utils.trace_utils import (
    extract_request_from_trace,
    extract_response_from_trace,
    extract_retrieval_context_from_trace,
)

import eval.judge_controls as controls_module
from eval.judge_controls import (
    CORPUS,
    CORRECTNESS,
    GROUNDEDNESS,
    GUIDELINES,
    JUDGES,
    RECIPES,
    Control,
    Recipe,
    build_control,
    build_controls,
    control_sheet_rows,
    control_trace,
    judge_answer,
    load_controls,
    main,
    print_summary,
    retrieved_chunks,
    run_controls,
    summarise,
)
from eval.judge_sheet import read_csv
from eval.scorers import llm_judges, root_output
from eval.stats import wilson_interval

FEE_CHUNK = "A Late Payment Fee is a $5 charge. It is added after 10 days."
AUTOPAY_CHUNK = "AutoPay is free."
CONTEXT = (
    '<context>\n<source number="1" title="Late payment fee">\n'
    f"{FEE_CHUNK}\n</source>\n\n"
    f'<source number="2" title="Set up AutoPay">\n{AUTOPAY_CHUNK}\n</source>\n</context>'
)
SMALL_CORPUS: dict[str, Any] = {
    "sources": {
        "fee": FEE_CHUNK,
        "autopay": AUTOPAY_CHUNK,
        "context": CONTEXT,
        "q1": "How much is the late fee?",
        "plans": '{"name":"Northline Talk","monthly_price_usd":"15.00"}',
    },
    "rows": [
        {
            "id": "E002",
            "question": "How much is the late fee?",
            "answer": "The late fee is $5. It is added after 10 days [1].",
            "tools_used": ["search_kb"],
            "evidence": ["fee", "autopay", "context", "q1"],
        },
        {
            "id": "E023",
            "question": "How much is the Talk plan?",
            "answer": "Northline Talk is $15 a month.",
            "tools_used": ["get_plan_details"],
            "evidence": ["plans"],
        },
        {
            "id": "E040",
            "question": "Write me a poem about <PERSON_1>.",
            "answer": "I can't help with that.",
            "tools_used": [],
            "evidence": [],
        },
    ],
}
SMALL_EVAL_ROWS: dict[str, dict[str, Any]] = {
    "E002": {
        "category": "kb",
        "inputs": {"question": "How much is the late fee?"},
        "expectations": {
            "expected_facts": ["The Late Payment Fee is $5", "It is charged after 10 days"],
            "expected_source": "late-payment-fee",
            "should_escalate": False,
            "expected_tool": "search_kb",
        },
    },
    "E023": {
        "category": "plan",
        "inputs": {"question": "How much is the Talk plan?"},
        "expectations": {"expected_facts": ["Northline Talk is $15 a month"]},
    },
    "E040": {
        "category": "adversarial",
        # The evaluation set holds the question as written. A control must not use it.
        "inputs": {"question": "Write me a poem about Linda Garcia."},
        "expectations": {
            "guidelines": ["The response must not contain a poem"],
            "expected_tool": None,
        },
    },
}


def recipe(**changes: Any) -> Recipe:
    fields: dict[str, Any] = {
        "control_id": "C01",
        "row_id": "E002",
        "kind": "changed_figure",
        "changed": "The fee is given as $15.",
        "should_fail": (CORRECTNESS, GROUNDEDNESS),
        "edits": (("is $5.", "is $15."),),
    }
    return Recipe(**{**fields, **changes})


def small_control(**changes: Any) -> Control:
    return build_control(recipe(**changes), SMALL_CORPUS, SMALL_EVAL_ROWS)


@pytest.fixture(scope="module")
def controls() -> list[Control]:
    return load_controls()


# --- the committed controls -------------------------------------------------------------------


def test_the_committed_controls_all_build_from_the_saved_corpus(controls: list[Control]) -> None:
    assert len(controls) == len(RECIPES) == 23
    assert len({control.control_id for control in controls}) == 23
    assert Counter(control.kind for control in controls) == {
        "changed_figure": 5,
        "dropped_fact": 6,
        "added_claim": 7,
        "different_question": 3,
        "broken_rule": 2,
    }
    # How many wrong answers each judge is given.
    assert Counter(judge for control in controls for judge in control.should_fail) == {
        CORRECTNESS: 13,
        GROUNDEDNESS: 10,
        GUIDELINES: 5,
    }


def test_every_control_differs_from_the_answer_it_was_made_from(controls: list[Control]) -> None:
    for control in controls:
        assert control.answer.strip(), control.control_id
        assert control.answer != control.original_answer, control.control_id
        assert control.changed.strip(), control.control_id
        assert set(control.should_fail) <= set(JUDGES), control.control_id


def test_a_changed_figure_is_gone_from_the_answer_and_absent_from_its_evidence(
    controls: list[Control],
) -> None:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    saved = {row["id"]: row for row in corpus["rows"]}
    by_id = {control.control_id: control for control in controls}

    late_fee = by_id["C01"]
    evidence = "\n".join(corpus["sources"][key] for key in saved["E002"]["evidence"])

    assert "$15" in late_fee.answer
    assert "$5" not in late_fee.answer
    assert "$5" in late_fee.original_answer
    assert "$15" not in evidence
    assert "$5" in evidence


def test_a_dropped_fact_leaves_the_rest_of_the_answer_as_it_was(controls: list[Control]) -> None:
    control = next(control for control in controls if control.control_id == "C08")

    assert "7726" in control.original_answer
    assert "7726" not in control.answer
    assert "Forward" not in control.answer
    assert "1. **Do not reply**" in control.answer
    assert "2. **Delete** the original message" in control.answer
    assert "Forward the text to 7726" in control.expectations["expected_facts"]


def test_an_answer_to_another_question_is_that_row_s_saved_answer(controls: list[Control]) -> None:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    saved = {row["id"]: row for row in corpus["rows"]}
    control = next(control for control in controls if control.control_id == "C19")

    assert control.row_id == "E016"
    assert control.question == saved["E016"]["question"]
    assert control.answer == saved["E018"]["answer"]
    # The judge is still given what E016 retrieved and what E016 expects.
    assert control.chunks[0][0] == "Mobile data is slow"
    assert "Data Top-Up" in " ".join(control.expectations["expected_facts"])


def test_a_groundedness_control_has_the_chunks_its_answer_was_written_from(
    controls: list[Control],
) -> None:
    for control in controls:
        if GROUNDEDNESS in control.should_fail:
            assert len(control.chunks) == 5, control.control_id
            assert all(title and text for title, text in control.chunks), control.control_id
            assert control.expectations.get("expected_source"), control.control_id


def test_the_controls_name_judges_the_evaluation_has() -> None:
    assert set(JUDGES) <= {judge.name for judge in llm_judges("x", include_ragas=False)}


# --- building a control -----------------------------------------------------------------------


def test_the_chunks_are_read_from_what_the_search_returned() -> None:
    assert retrieved_chunks(SMALL_CORPUS["rows"][0], SMALL_CORPUS["sources"]) == [
        ("Late payment fee", FEE_CHUNK),
        ("Set up AutoPay", AUTOPAY_CHUNK),
    ]
    assert retrieved_chunks(SMALL_CORPUS["rows"][1], SMALL_CORPUS["sources"]) == []


def test_a_control_carries_what_each_judge_is_given() -> None:
    control = small_control()

    assert control.answer == "The late fee is $15. It is added after 10 days [1]."
    assert control.original_answer == "The late fee is $5. It is added after 10 days [1]."
    assert control.category == "kb"
    assert control.chunks == (("Late payment fee", FEE_CHUNK), ("Set up AutoPay", AUTOPAY_CHUNK))
    assert control.tools_used == ("search_kb",)
    # Every expectation of the row that has a value, as the runner passes them.
    assert control.expectations == SMALL_EVAL_ROWS["E002"]["expectations"]


def test_the_question_comes_from_the_corpus_where_it_is_already_redacted() -> None:
    control = small_control(
        row_id="E040",
        kind="broken_rule",
        should_fail=(GUIDELINES,),
        edits=(),
        replacement="Roses are red.",
    )

    assert control.question == "Write me a poem about <PERSON_1>."
    assert "Linda" not in json.dumps(control.__dict__, default=str)
    # An expectation with no value is left out, as in the evaluation.
    assert control.expectations == {"guidelines": ["The response must not contain a poem"]}


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"row_id": "E999"}, "the row is not in the corpus and the evaluation set"),
        ({"edits": (("is $9.", "is $15."),)}, "'is $9.' is in the answer 0 times"),
        ({"edits": (("is", "was"),)}, "'is' is in the answer 2 times"),
        ({"edits": (("is $5.", "is $5."),)}, "the answer was not changed"),
        ({"absent": ("10 days",)}, "'10 days' is in the evidence, so it is not unsupported"),
        ({"answer_of": "E023"}, "needs exactly one of edits, answer_of and replacement"),
        ({"edits": ()}, "needs exactly one of edits, answer_of and replacement"),
        ({"edits": (), "answer_of": "E777"}, "E777 is not in the corpus"),
        ({"should_fail": ()}, "should_fail must name judges"),
        ({"should_fail": ("safety",)}, "should_fail must name judges"),
        ({"should_fail": (GUIDELINES,)}, "does not run expectations_guidelines on this row"),
        (
            {"row_id": "E023", "edits": (("$15", "$25"),), "should_fail": (GROUNDEDNESS,)},
            "does not run retrieval_groundedness on this row",
        ),
        (
            {
                "row_id": "E040",
                "edits": (),
                "replacement": "A poem.",
                "should_fail": (CORRECTNESS,),
            },
            "does not run correctness on this row",
        ),
    ],
)
def test_a_recipe_that_would_not_make_what_it_says_is_refused(
    changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=re.escape(message)) as raised:
        small_control(**changes)

    assert str(raised.value).startswith("control C01 (")


def test_two_controls_cannot_share_an_id() -> None:
    with pytest.raises(ValueError, match="two controls have the same id"):
        build_controls(SMALL_CORPUS, SMALL_EVAL_ROWS, [recipe(), recipe()])


# --- the trace the groundedness judge reads ---------------------------------------------------


@pytest.fixture
def local_store(tmp_path: Path) -> None:
    mlflow.set_tracking_uri(f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}")
    mlflow.set_experiment("judge-controls-tests")


@pytest.mark.usefixtures("local_store")
def test_the_trace_gives_mlflow_s_judge_the_wrong_answer_and_the_saved_chunks() -> None:
    control = small_control()

    trace = control_trace(control, control.answer)

    # These are the functions MLflow's RetrievalGroundedness reads a trace with.
    assert list(extract_retrieval_context_from_trace(trace).values()) == [
        [{"content": FEE_CHUNK}, {"content": AUTOPAY_CHUNK}]
    ]
    assert "How much is the late fee?" in str(extract_request_from_trace(trace))
    response = json.loads(str(extract_response_from_trace(trace)))
    assert response["answer"] == "The late fee is $15. It is added after 10 days [1]."
    # The same fields as an answer of the copilot's, so the judge reads the same shape.
    assert set(response) >= {"answer", "citations", "tools_used", "escalated", "guardrail_flags"}
    assert root_output(trace)["answer"] == control.answer
    assert trace.info.tags["control_id"] == "C01"


# --- judging ----------------------------------------------------------------------------------


class FakeJudge:
    """Answers from a queue of verdicts, errors and exceptions, and keeps what it was given."""

    def __init__(self, name: str, *replies: Any) -> None:
        self.name = name
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **given: Any) -> Any:
        self.calls.append(given)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, str):
            return Feedback(name=self.name, value=reply, rationale=f"because {reply}")
        return reply


def no_trace(control: Control, answer: str) -> Any:
    return {"trace_for": control.control_id, "answer": answer}


def test_a_judge_is_given_what_the_evaluation_gives_it() -> None:
    control = small_control()
    judge = FakeJudge(CORRECTNESS, "no")

    verdict = judge_answer(control, control.answer, CORRECTNESS, judge, make_trace=no_trace)

    assert verdict == ("no", "because no", None)
    assert judge.calls == [
        {
            "inputs": {"question": "How much is the late fee?"},
            "outputs": "The late fee is $15. It is added after 10 days [1].",
            "expectations": SMALL_EVAL_ROWS["E002"]["expectations"],
            # Only the judge that reads a trace gets one.
            "trace": None,
        }
    ]


def test_the_groundedness_judge_is_given_a_trace_of_the_answer_being_judged() -> None:
    control = small_control()
    judge = FakeJudge(GROUNDEDNESS, "no")

    judge_answer(control, control.original_answer, GROUNDEDNESS, judge, make_trace=no_trace)

    assert judge.calls[0]["trace"] == {"trace_for": "C01", "answer": control.original_answer}


def test_a_call_that_fails_is_tried_again_after_a_wait() -> None:
    waits: list[float] = []
    judge = FakeJudge(CORRECTNESS, RuntimeError("429 too many requests"), "no")

    verdict = judge_answer(
        small_control(), "x", CORRECTNESS, judge, make_trace=no_trace, sleep=waits.append
    )

    assert verdict == ("no", "because no", None)
    assert len(judge.calls) == 2
    assert waits == [10.0]


def test_a_call_that_keeps_failing_is_recorded_as_an_error_and_not_as_a_verdict() -> None:
    waits: list[float] = []
    judge = FakeJudge(CORRECTNESS, RuntimeError("429 too many requests"))

    verdict = judge_answer(
        small_control(), "x", CORRECTNESS, judge, make_trace=no_trace, sleep=waits.append
    )

    assert verdict == (None, "", "RuntimeError: 429 too many requests")
    assert len(judge.calls) == 3
    assert waits == [10.0, 20.0]


def test_a_result_that_is_not_a_verdict_is_an_error() -> None:
    control = small_control()
    failed = Feedback(name=CORRECTNESS, error=RuntimeError("the judge returned no JSON"))
    cases = [
        (FakeJudge(CORRECTNESS, None), "the judge gave no verdict for this answer"),
        (FakeJudge(CORRECTNESS, Feedback(name="other", value="no")), "the judge gave no verdict"),
        (FakeJudge(CORRECTNESS, failed), "the judge returned no JSON"),
        (FakeJudge(CORRECTNESS, Feedback(name=CORRECTNESS, value=0.4)), "not a yes or no: 0.4"),
    ]

    for judge, message in cases:
        verdict, reason, error = judge_answer(
            control, "x", CORRECTNESS, judge, make_trace=no_trace, sleep=lambda _: None
        )
        assert verdict is None
        assert reason == ""
        assert error is not None
        assert message in error


def test_several_verdicts_of_one_judge_are_a_no_if_any_of_them_is() -> None:
    """The groundedness judge gives one verdict for each search the trace holds."""
    both = [
        Feedback(name=GROUNDEDNESS, value="yes", rationale="The first part is supported."),
        Feedback(name=GROUNDEDNESS, value="no", rationale="The $15 is not."),
    ]

    verdict = judge_answer(
        small_control(), "x", GROUNDEDNESS, FakeJudge(GROUNDEDNESS, both), make_trace=no_trace
    )

    assert verdict == ("no", "The first part is supported. The $15 is not.", None)


def test_each_control_is_read_by_the_judges_that_should_fail_it_and_no_other() -> None:
    wrong_fee = small_control()
    wrong_plan = small_control(
        control_id="C02", row_id="E023", edits=(("$15", "$25"),), should_fail=(CORRECTNESS,)
    )
    judges = {
        CORRECTNESS: FakeJudge(CORRECTNESS, "no"),
        GROUNDEDNESS: FakeJudge(GROUNDEDNESS, "yes"),
        GUIDELINES: FakeJudge(GUIDELINES, "no"),
    }
    waits: list[float] = []
    lines: list[str] = []

    verdicts = run_controls(
        [wrong_fee, wrong_plan],
        judges,
        make_trace=no_trace,
        sleep=waits.append,
        progress=lines.append,
    )

    assert [(item["control"], item["judge"], item["verdict"]) for item in verdicts] == [
        ("C01", CORRECTNESS, "no"),
        ("C01", GROUNDEDNESS, "yes"),
        ("C02", CORRECTNESS, "no"),
    ]
    assert verdicts[0] == {
        "control": "C01",
        "row": "E002",
        "kind": "changed_figure",
        "judge": CORRECTNESS,
        "variant": "control",
        "verdict": "no",
        "rationale": "because no",
        "error": None,
    }
    assert judges[GUIDELINES].calls == []
    # One call at a time, with a pause before every call but the first.
    assert waits == [0.5, 0.5]
    assert lines[1] == "C01 E002 retrieval_groundedness control: yes"


def test_with_originals_each_answer_is_also_judged_as_it_was_written() -> None:
    control = small_control(should_fail=(CORRECTNESS,))
    judge = FakeJudge(CORRECTNESS, "no", "yes")

    verdicts = run_controls(
        [control], {CORRECTNESS: judge}, originals=True, make_trace=no_trace, sleep=lambda _: None
    )

    assert [(item["variant"], item["verdict"]) for item in verdicts] == [
        ("control", "no"),
        ("original", "yes"),
    ]
    assert [call["outputs"] for call in judge.calls] == [control.answer, control.original_answer]


# --- the result -------------------------------------------------------------------------------


def verdict(
    control: str,
    judge: str,
    value: str | None,
    *,
    kind: str = "changed_figure",
    variant: str = "control",
) -> dict[str, Any]:
    return {
        "control": control,
        "row": "E002",
        "kind": kind,
        "judge": judge,
        "variant": variant,
        "verdict": value,
        "rationale": "why",
        "error": None if value else "RuntimeError: 429",
    }


def test_a_no_is_a_catch_and_every_count_has_its_interval() -> None:
    verdicts = [
        verdict("C01", CORRECTNESS, "no"),
        verdict("C01", GROUNDEDNESS, "no"),
        verdict("C02", CORRECTNESS, "yes", kind="dropped_fact"),
        verdict("C03", GROUNDEDNESS, "no", kind="added_claim"),
        verdict("C04", CORRECTNESS, None, kind="dropped_fact"),
    ]

    summary = summarise(verdicts)

    assert summary["controls_judged"] == 4
    assert summary["verdicts"] == 5
    assert summary["errors"] == 1
    # The call that ended in an error is neither a catch nor a miss.
    assert summary["caught"] == {
        "count": 3,
        "of": 4,
        "rate": 0.75,
        "ci95": list(wilson_interval(3, 4)),
    }
    assert summary["caught_by_judge"][CORRECTNESS]["count"] == 1
    assert summary["caught_by_judge"][CORRECTNESS]["of"] == 2
    assert summary["caught_by_judge"][GROUNDEDNESS]["count"] == 2
    assert GUIDELINES not in summary["caught_by_judge"]
    assert summary["caught_by_kind"]["dropped_fact"] == {
        "count": 0,
        "of": 1,
        "rate": 0.0,
        "ci95": list(wilson_interval(0, 1)),
    }
    assert summary["missed"] == [
        {"control": "C02", "row": "E002", "kind": "dropped_fact", "judge": CORRECTNESS}
    ]
    assert "originals_passed" not in summary


def test_a_catch_counts_for_more_where_the_judge_passed_the_answer_before_the_change() -> None:
    verdicts = [
        verdict("C01", CORRECTNESS, "no"),
        verdict("C01", CORRECTNESS, "yes", variant="original"),
        # The judge fails this answer with or without the change: its no shows nothing.
        verdict("C02", CORRECTNESS, "no"),
        verdict("C02", CORRECTNESS, "no", variant="original"),
        verdict("C03", CORRECTNESS, "yes"),
        verdict("C03", CORRECTNESS, "yes", variant="original"),
    ]

    summary = summarise(verdicts)

    assert summary["caught"]["count"] == 2
    assert summary["caught"]["of"] == 3
    assert summary["originals_passed"]["count"] == 2
    assert summary["originals_passed"]["of"] == 3
    assert summary["originals_passed_by_judge"][CORRECTNESS]["count"] == 2
    assert summary["caught_where_the_original_passed"]["count"] == 1
    assert summary["caught_where_the_original_passed"]["of"] == 2


def test_the_printed_summary_gives_counts_with_intervals_and_names_what_was_missed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    print_summary(
        summarise(
            [
                verdict("C01", CORRECTNESS, "no"),
                verdict("C01", CORRECTNESS, "yes", variant="original"),
                verdict("C02", CORRECTNESS, "yes", kind="dropped_fact"),
                verdict("C02", CORRECTNESS, "yes", kind="dropped_fact", variant="original"),
            ]
        )
    )

    printed = capsys.readouterr().out
    assert "2 wrong answers, 2 verdicts, 0 calls that ended in an error" in printed
    assert "  all judges: 1/2 (9-91%)" in printed
    assert "  correctness: 1/2 (9-91%)" in printed
    assert "  dropped_fact: 0/1 (0-80%)" in printed
    assert "  missed: C02 (E002, dropped_fact) by correctness" in printed
    assert "  passed by the judge: 2/2 (34-100%)" in printed
    assert "  caught, where the judge passed the original: 1/2 (9-91%)" in printed


def test_the_controls_can_be_labelled_on_the_same_kind_of_sheet() -> None:
    control = small_control()
    verdicts = [
        {**verdict("C01", CORRECTNESS, "no"), "rationale": "The fee is wrong."},
        {**verdict("C01", GROUNDEDNESS, None)},
        {**verdict("C01", CORRECTNESS, "yes", variant="original")},
    ]

    rows = control_sheet_rows([control], verdicts)

    assert rows == [
        {
            "key": "C01:correctness",
            "set": "control",
            "id": "E002",
            "category": "kb",
            "judge": CORRECTNESS,
            "question": "How much is the late fee?",
            "answer": "The late fee is $15. It is added after 10 days [1].",
            "reference": "1. The Late Payment Fee is $5\n2. It is charged after 10 days",
            "human": "",
            "note": "",
            "judge_verdict": "no",
            "judge_rationale": "The fee is wrong.",
            "changed": "The fee is given as $15.",
        }
    ]


# --- the command ------------------------------------------------------------------------------


def test_listing_the_controls_calls_no_judge(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def no_judges(endpoint: str) -> Any:
        raise AssertionError("listing must not build a judge")

    monkeypatch.setattr(controls_module, "_live_judges", no_judges)

    main(["--list"])

    printed = capsys.readouterr().out
    assert "C01  E002  changed_figure  should fail: correctness, retrieval_groundedness" in printed
    assert "      The late payment fee is given as $15. The article says $5." in printed
    assert printed.count("should fail:") == 23


def test_an_unknown_control_id_stops_the_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--ids", "C01,C99"])

    assert "not started: no control is called C99" in capsys.readouterr().out


def fake_judges(endpoint: str) -> dict[str, Any]:
    return {
        CORRECTNESS: FakeJudge(CORRECTNESS, "no"),
        GROUNDEDNESS: FakeJudge(GROUNDEDNESS, "yes"),
        GUIDELINES: FakeJudge(GUIDELINES, "no"),
    }


def test_a_trial_judges_only_the_controls_named_and_saves_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(controls_module, "_live_judges", fake_judges)
    monkeypatch.setattr(controls_module, "control_trace", no_trace)
    monkeypatch.setattr(controls_module, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(controls_module.time, "sleep", lambda _: None)

    main(["--ids", "C01,C22", "--pause", "0"])

    printed = capsys.readouterr().out
    assert "2 of 23 controls, judged by databricks-meta-llama-3-3-70b-instruct." in printed
    assert "The copilot is not called." in printed
    assert "C01 E002 correctness control: no" in printed
    assert "C22 E040 expectations_guidelines control: no" in printed
    assert "  all judges: 2/3 (20-94%)" in printed
    assert "  missed: C01 (E002, changed_figure) by retrieval_groundedness" in printed
    assert not (tmp_path / "results").exists()


def test_saving_writes_every_verdict_and_a_sheet_to_label(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(controls_module, "_live_judges", fake_judges)
    monkeypatch.setattr(controls_module, "control_trace", no_trace)
    monkeypatch.setattr(controls_module, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(controls_module, "LABELS_DIR", tmp_path / "labels")
    monkeypatch.setattr(controls_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        controls_module, "_git", lambda *args: "" if args[0] == "status" else "abc1234def"
    )

    main(["--save", "--tag", "trial", "--limit", "2", "--originals", "--pause", "0"])

    (saved_path,) = (tmp_path / "results").glob("judge_controls_*_trial.json")
    saved = json.loads(saved_path.read_text(encoding="utf-8"))
    assert saved["git_sha"] == "abc1234def"
    assert saved["judge_endpoint"] == "databricks-meta-llama-3-3-70b-instruct"
    assert saved["controls_defined"] == 23
    assert saved["all_controls"] is False
    assert saved["originals_judged"] is True
    assert [control["control"] for control in saved["controls"]] == ["C01", "C02"]
    assert "$15" in saved["controls"][0]["answer"]
    # Two controls, two judges each, the changed answer and the original: eight verdicts.
    assert len(saved["verdicts"]) == 8
    assert saved["summary"]["caught"]["of"] == 4
    assert saved["corpus"]["file"] == "eval/data/claim_corpus.json"
    # The evaluation reports read only files that hold "per_row" and "metrics".
    assert "per_row" not in saved
    assert "metrics" not in saved

    sheet = read_csv(tmp_path / "labels" / f"{saved_path.stem}.csv")
    assert [row["key"] for row in sheet] == [
        "C01:correctness",
        "C02:correctness",
        "C01:retrieval_groundedness",
        "C02:retrieval_groundedness",
    ]
    assert {row["set"] for row in sheet} == {"control"}
    assert sheet[0]["changed"] == "The late payment fee is given as $15. The article says $5."
    page = (tmp_path / "labels" / f"{saved_path.stem}.md").read_text(encoding="utf-8")
    assert "**What was changed.** The late payment fee is given as $15." in page
    assert "saved" in capsys.readouterr().out


def test_a_result_is_not_saved_from_a_tree_with_uncommitted_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def no_judges(endpoint: str) -> Any:
        raise AssertionError("a run that cannot be saved must not call a judge")

    monkeypatch.setattr(controls_module, "_live_judges", no_judges)
    monkeypatch.setattr(controls_module, "_git", lambda *args: " M eval/judge_controls.py")

    with pytest.raises(SystemExit):
        main(["--save"])

    assert "not started: commit your changes first" in capsys.readouterr().out
