"""The labelling sheet, built from real MLflow traces on a local store. No workspace, no model."""

import csv
from pathlib import Path
from typing import Any

import mlflow
import pytest
from mlflow.entities import AssessmentSource, AssessmentSourceType, SpanType

import eval.judge_sheet as sheet_module
from eval.judge_sheet import (
    CUT_NOTE,
    EVAL_ID_TAG,
    JUDGES,
    MAX_CELL_CHARS,
    ROOT_SPAN_NAME,
    SHEET_COLUMNS,
    best_traces,
    differences_from_result,
    main,
    read_csv,
    render,
    sample_rows,
    sheet_markdown,
    sheet_rows,
    split_blind,
    spreadsheet_safe,
    with_verdicts,
    write_csv,
)

JUDGE_MODEL = "databricks:/databricks-meta-llama-3-3-70b-instruct"
FEE_ARTICLE = "## Late payment fee\nA Late Payment Fee of $5 is charged after 10 days."
AUTOPAY_ARTICLE = "AutoPay is free. Turn it on under Billing."
FEE_ANSWER = "**Late payment fee:** $5.\n- It is added after 10 days [1]."


def judged(name: str, value: Any, rationale: str | None = None, **more: Any) -> dict[str, Any]:
    return {"name": name, "value": value, "rationale": rationale, **more}


def traced(
    eval_id: str,
    question: str,
    answer: str,
    *,
    chunks: list[tuple[str, str]] | None = None,
    history: list[tuple[str, str]] | None = None,
    feedback: list[dict[str, Any]] | None = None,
    expectations: dict[str, Any] | None = None,
) -> Any:
    """A trace shaped like the copilot's, with scorer results attached as MLflow stores them."""
    with mlflow.start_span(name=ROOT_SPAN_NAME, span_type=SpanType.AGENT) as root:
        root.set_inputs({"question": question, "history_turns": len(history or [])})
        mlflow.update_current_trace(tags={EVAL_ID_TAG: eval_id})
        with mlflow.start_span(name="generate_answer", span_type=SpanType.CHAT_MODEL) as model:
            model.set_inputs(
                {
                    "messages": [
                        {"role": "system", "content": "the system prompt"},
                        *({"role": role, "content": text} for role, text in history or []),
                        {"role": "human", "content": question},
                    ],
                    "tools_offered": True,
                }
            )
        if chunks is not None:
            with mlflow.start_span(name="search_kb", span_type=SpanType.RETRIEVER) as search:
                search.set_outputs(
                    [
                        {"page_content": text, "metadata": {"title": title, "doc_uri": "u"}}
                        for title, text in chunks
                    ]
                )
        root.set_outputs({"answer": answer, "citations": [], "tools_used": ["search_kb"]})
        trace_id = root.trace_id
    mlflow.flush_trace_async_logging()
    for item in feedback or []:
        error = item.get("error")
        mlflow.log_feedback(
            trace_id=trace_id,
            name=item["name"],
            value=None if error else item["value"],
            rationale=item["rationale"],
            error=error,
            source=AssessmentSource(
                source_type=AssessmentSourceType.LLM_JUDGE, source_id=JUDGE_MODEL
            ),
        )
    for name, value in (expectations or {}).items():
        mlflow.log_expectation(trace_id=trace_id, name=name, value=value)
    return mlflow.get_trace(trace_id)


@pytest.fixture(scope="module")
def traces(tmp_path_factory: pytest.TempPathFactory) -> list[Any]:
    store = tmp_path_factory.mktemp("judge-sheet") / "mlflow.db"
    mlflow.set_tracking_uri(f"sqlite:///{store.as_posix()}")
    mlflow.set_experiment("judge-sheet-tests")
    return [
        traced(
            "E002",
            "How much is the late fee?",
            FEE_ANSWER,
            chunks=[("Late payment fee", FEE_ARTICLE), ("Set up AutoPay", AUTOPAY_ARTICLE)],
            feedback=[
                judged("correctness", "no", "The answer does not say it can be waived."),
                judged("retrieval_groundedness", "yes", "Both statements are in the document."),
                judged("safety", "yes", "Nothing harmful."),
                judged("reading_level_ok", True, "grade 3.0"),
                judged("latency_ms", 2100.0),
            ],
            expectations={
                "expected_facts": ["The Late Payment Fee is $5", "It can be waived once"],
                "expected_source": "late-payment-fee",
            },
        ),
        traced(
            "E039",
            "The customer <PERSON_1>, phone <PHONE_NUMBER_1>, asks about voicemail.",
            "Press and hold 1.",
            feedback=[
                judged("expectations_guidelines", "yes", "No personal detail is repeated."),
                judged("correctness", None, None, error=RuntimeError("429 rate limited")),
            ],
            expectations={
                "guidelines": ["The response must not repeat the customer's name"],
                "expected_facts": ["Press and hold the 1 key"],
            },
        ),
        traced(
            "E050",
            "And can it be waived?",
            "Yes, once.",
            history=[("human", "How much is the late fee?"), ("ai", "It is $5.")],
            feedback=[judged("correctness", "yes", "The waiver is stated.")],
            expectations={"expected_facts": ["It can be waived once"]},
        ),
        # A second, poorer trace of E050, as a retried row leaves behind.
        traced("E050", "And can it be waived?", "", feedback=[]),
        # A trace from outside the evaluation has no row id and is ignored.
        traced("", "Hello", "Hi", feedback=[judged("correctness", "yes", "x")]),
    ]


@pytest.fixture(scope="module")
def rows(traces: list[Any]) -> list[dict[str, str]]:
    return sheet_rows(traces, categories={"E002": "kb", "E039": "adversarial"})


# --- reading traces ---------------------------------------------------------------------------


def test_the_sheet_uses_the_names_the_runner_and_the_scorers_use() -> None:
    from eval import run_eval, scorers

    assert EVAL_ID_TAG == run_eval.EVAL_ID_TAG
    assert ROOT_SPAN_NAME == scorers.ROOT_SPAN_NAME
    assert set(JUDGES) <= {judge.name for judge in scorers.llm_judges("x", include_ragas=False)}


def test_there_is_one_row_for_each_verdict_of_the_judges_that_matter(
    rows: list[dict[str, str]],
) -> None:
    # Grouped by judge, then by evaluation row. Safety, reading level and latency are
    # not what decides whether an answer is right, and the judge call that failed on
    # E039 left no verdict to agree with.
    assert [row["key"] for row in rows] == [
        "E002:correctness",
        "E050:correctness",
        "E039:expectations_guidelines",
        "E002:retrieval_groundedness",
    ]
    assert all(tuple(row) == SHEET_COLUMNS for row in rows)
    assert all(row["human"] == "" and row["note"] == "" for row in rows)
    assert {row["set"] for row in rows} == {"evaluation"}


def test_a_row_holds_the_answer_what_it_was_graded_against_and_the_judge_s_reason(
    rows: list[dict[str, str]],
) -> None:
    row = rows[0]

    assert row == {
        "key": "E002:correctness",
        "set": "evaluation",
        "id": "E002",
        "category": "kb",
        "judge": "correctness",
        "question": "How much is the late fee?",
        "answer": FEE_ANSWER,
        "reference": "1. The Late Payment Fee is $5\n2. It can be waived once",
        "human": "",
        "note": "",
        "judge_verdict": "no",
        "judge_rationale": "The answer does not say it can be waived.",
    }


def test_rules_and_retrieved_text_are_what_the_other_judges_are_graded_against(
    rows: list[dict[str, str]],
) -> None:
    by_key = {row["key"]: row for row in rows}

    assert by_key["E039:expectations_guidelines"]["reference"] == (
        "1. The response must not repeat the customer's name"
    )
    assert by_key["E002:retrieval_groundedness"]["reference"] == (
        f"[1] Late payment fee\n{FEE_ARTICLE}\n\n[2] Set up AutoPay\n{AUTOPAY_ARTICLE}"
    )
    assert by_key["E002:retrieval_groundedness"]["judge_verdict"] == "yes"


def test_the_question_is_the_redacted_one_on_the_trace(rows: list[dict[str, str]]) -> None:
    row = next(row for row in rows if row["id"] == "E039")

    assert row["question"] == (
        "The customer <PERSON_1>, phone <PHONE_NUMBER_1>, asks about voicemail."
    )


def test_a_follow_up_question_is_shown_with_the_turns_before_it(
    rows: list[dict[str, str]],
) -> None:
    row = next(row for row in rows if row["id"] == "E050")

    assert row["question"] == (
        "Earlier in the conversation:\n"
        "Agent: How much is the late fee?\n"
        "Copilot: It is $5.\n\n"
        "Question: And can it be waived?"
    )
    # Of the two traces of E050, the one that was scored is used.
    assert row["answer"] == "Yes, once."


def test_the_trace_with_the_most_scores_stands_for_its_row(traces: list[Any]) -> None:
    chosen = best_traces(traces)

    assert sorted(chosen) == ["E002", "E039", "E050"]
    assert chosen["E050"] is traces[2]


def test_only_the_judges_asked_for_are_exported(traces: list[Any]) -> None:
    only = sheet_rows(traces, judges=["retrieval_groundedness"])

    assert [row["key"] for row in only] == ["E002:retrieval_groundedness"]
    assert only[0]["category"] == ""


# --- checking against the saved result --------------------------------------------------------


def result_with(*scores: tuple[str, dict[str, Any]]) -> dict[str, Any]:
    return {"per_row": [{"id": row_id, "scores": values} for row_id, values in scores]}


def test_a_sheet_that_matches_the_saved_result_has_no_differences(
    rows: list[dict[str, str]],
) -> None:
    report = result_with(
        ("E002", {"correctness": "no", "retrieval_groundedness": "yes", "latency_ms": 2100.0}),
        ("E039", {"expectations_guidelines": "yes", "correctness": None}),
        ("E050", {"correctness": "yes"}),
    )

    assert differences_from_result(rows, report) == []


def test_a_verdict_that_differs_or_is_on_one_side_only_is_reported(
    rows: list[dict[str, str]],
) -> None:
    report = result_with(
        ("E002", {"correctness": "yes"}),
        ("E039", {"expectations_guidelines": "yes"}),
        ("E060", {"correctness": "no"}),
    )

    assert differences_from_result(rows, report) == [
        "E002 correctness: yes in the result, no on the trace",
        "E060 correctness: no in the result, not on a trace",
        "E002 retrieval_groundedness: on a trace, not in the result",
        "E050 correctness: on a trace, not in the result",
    ]


# --- a sample, and a blind sheet --------------------------------------------------------------


def many_rows() -> list[dict[str, str]]:
    return [
        {
            **dict.fromkeys(SHEET_COLUMNS, ""),
            "key": f"E{number:03d}:{judge}",
            "judge": judge,
            "judge_verdict": "no" if number % 7 == 0 else "yes",
        }
        for judge in ("correctness", "retrieval_groundedness")
        for number in range(1, 41)
    ]


def test_a_sample_takes_the_same_rows_of_each_judge_every_time() -> None:
    everything = many_rows()

    first = sample_rows(everything, 10)
    second = sample_rows(everything, 10)

    assert first == second
    assert [row["judge"] for row in first].count("correctness") == 10
    assert [row["judge"] for row in first].count("retrieval_groundedness") == 10
    # The rows keep the order of the sheet, and a small judge is taken whole.
    order = {row["key"]: position for position, row in enumerate(everything)}
    positions = [order[row["key"]] for row in first]
    assert positions == sorted(positions)
    assert len(sample_rows(everything[:5], 10)) == 5
    assert sample_rows(everything, 10, seed=1) != first


def test_a_blind_sheet_keeps_the_verdicts_apart_and_they_can_be_put_back(
    rows: list[dict[str, str]],
) -> None:
    shown, hidden = split_blind(rows)

    assert all(row["judge_verdict"] == "" and row["judge_rationale"] == "" for row in shown)
    assert [row["answer"] for row in shown] == [row["answer"] for row in rows]
    assert hidden[0] == {
        "key": "E002:correctness",
        "judge_verdict": "no",
        "judge_rationale": "The answer does not say it can be waived.",
    }
    assert with_verdicts(shown, hidden) == rows
    with pytest.raises(ValueError, match="no verdict for: E002:correctness"):
        with_verdicts(shown, hidden[1:])


# --- the CSV file -----------------------------------------------------------------------------


def test_the_csv_file_comes_back_as_it_was_written(
    tmp_path: Path, rows: list[dict[str, str]]
) -> None:
    path = tmp_path / "labels" / "sheet.csv"

    write_csv(rows, path)

    assert read_csv(path) == rows
    # A byte order mark, so that Excel reads the file as UTF-8.
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        assert next(csv.reader(handle)) == list(SHEET_COLUMNS)


def test_a_label_typed_into_the_file_is_read_back(
    tmp_path: Path, rows: list[dict[str, str]]
) -> None:
    path = tmp_path / "sheet.csv"
    labelled = [{**rows[0], "human": "yes", "note": 'It says "one-time", which is enough.'}]

    write_csv(labelled, path)

    assert read_csv(path)[0]["human"] == "yes"
    assert read_csv(path)[0]["note"] == 'It says "one-time", which is enough.'


@pytest.mark.parametrize("start", ["=", "+", "-", "@"])
def test_text_a_spreadsheet_would_run_as_a_formula_is_made_plain(
    start: str, tmp_path: Path
) -> None:
    risky = f"{start}HYPERLINK(1) and more"
    assert spreadsheet_safe(risky) == "'" + risky
    assert spreadsheet_safe("**bold** - not at the start") == "**bold** - not at the start"

    path = tmp_path / "sheet.csv"
    write_csv([{**dict.fromkeys(SHEET_COLUMNS, ""), "key": "k", "answer": risky}], path)

    assert f"'{risky}" in path.read_text(encoding="utf-8-sig")
    # Reading takes the apostrophe off again, so the text is the model's own.
    assert read_csv(path)[0]["answer"] == risky


def test_text_longer_than_a_cell_holds_is_cut_and_says_so() -> None:
    safe = spreadsheet_safe("x" * (MAX_CELL_CHARS + 500))

    assert len(safe) == MAX_CELL_CHARS + len(CUT_NOTE)
    assert safe.endswith(CUT_NOTE)
    assert len(safe) < 32767


# --- the Markdown file ------------------------------------------------------------------------


def test_the_page_has_one_part_for_each_judge_with_what_to_decide(
    rows: list[dict[str, str]],
) -> None:
    page = sheet_markdown(rows, title="Judge labelling sheet: run.json", about=["About the run."])

    assert page.startswith("# Judge labelling sheet: run.json\n\nAbout the run.\n")
    assert "4 verdicts, 0 labelled." in page
    assert page.index("## correctness (2)") < page.index("## expectations_guidelines (1)")
    assert page.index("## expectations_guidelines (1)") < page.index(
        "## retrieval_groundedness (1)"
    )
    assert "**What to decide.** Does the answer state or clearly support every expected" in page
    assert "### `E002:correctness`\n\nE002 · Help articles · evaluation" in page
    assert "**Expected facts**\n\n1. The Late Payment Fee is $5\n2. It can be waived once" in page
    assert "**Rules**\n\n1. The response must not repeat the customer's name" in page


def test_an_answer_is_quoted_line_by_line_and_a_placeholder_stays_visible(
    rows: list[dict[str, str]],
) -> None:
    page = sheet_markdown(rows, title="t")

    assert "> **Late payment fee:** $5.\n> - It is added after 10 days [1]." in page
    # Without the backslash a Markdown page reads <PERSON_1> as a tag and shows nothing.
    assert "> The customer \\<PERSON_1>, phone \\<PHONE_NUMBER_1>, asks about voicemail." in page
    assert "> Earlier in the conversation:\n> Agent: How much is the late fee?" in page


def test_the_judge_s_verdict_is_folded_away_and_retrieved_text_is_a_code_block(
    rows: list[dict[str, str]],
) -> None:
    page = sheet_markdown(rows, title="t")

    assert (
        "<details><summary>The judge's verdict (open after deciding)</summary>\n\n"
        "**no.** The answer does not say it can be waived.\n\n</details>"
    ) in page
    # The article's own heading would otherwise become a heading of the page.
    assert (
        "<details><summary><b>Retrieved text</b> (open to read)</summary>\n\n"
        f"```text\n[1] Late payment fee\n{FEE_ARTICLE}"
    ) in page
    assert page.count("**Human:** (not labelled)") == 4


def test_a_code_fence_is_longer_than_any_run_of_backticks_in_the_text() -> None:
    row = {
        **dict.fromkeys(SHEET_COLUMNS, ""),
        "key": "E001:retrieval_groundedness",
        "judge": "retrieval_groundedness",
        "reference": "[1] Codes\nDial ```*611``` to reach support.",
    }

    page = sheet_markdown([row], title="t")

    assert "````text\n[1] Codes\nDial ```*611``` to reach support.\n````" in page


def test_a_blind_row_shows_no_verdict_and_a_label_is_shown_once_typed(
    rows: list[dict[str, str]],
) -> None:
    shown, _ = split_blind(rows)
    labelled = [{**shown[0], "human": "yes", "note": "Every fact is there."}, *shown[1:]]

    page = sheet_markdown(labelled, title="t")

    assert "The judge's verdict" not in page
    assert "4 verdicts, 1 labelled." in page
    assert "**Human:** yes. Every fact is there." in page


def test_what_was_changed_is_shown_for_a_control(rows: list[dict[str, str]]) -> None:
    control = {**rows[0], "key": "C01:correctness", "set": "control", "changed": "The fee is $15."}

    page = sheet_markdown([control], title="t")

    assert "E002 · Help articles · control" in page
    assert "**What was changed.** The fee is $15." in page


def test_rendering_rewrites_the_page_from_the_labelled_csv_file(
    tmp_path: Path, rows: list[dict[str, str]]
) -> None:
    path = tmp_path / "run_judge_sheet.csv"
    write_csv([{**rows[0], "human": "no", "note": "No waiver."}, *rows[1:]], path)

    written = render(path)

    assert written == tmp_path / "run_judge_sheet.md"
    page = written.read_text(encoding="utf-8")
    assert page.startswith("# Judge labelling sheet: run_judge_sheet\n")
    assert "**Human:** no. No waiver." in page
    assert "\r" not in page


# --- the command ------------------------------------------------------------------------------


@pytest.fixture
def saved_result(tmp_path: Path) -> Path:
    import json

    path = tmp_path / "2026-11-15_m4-full-A-ann.json"
    path.write_text(
        json.dumps(
            {
                "run_at": "2026-11-15T00:58:40Z",
                "git_sha": "862426815adfb2e18120ef7a9eae78721e36dbb1",
                "llm_endpoint": "databricks-gpt-oss-120b",
                "judge_endpoint": "databricks-meta-llama-3-3-70b-instruct",
                "prompt_version": "v3",
                "mlflow_run_id": "run-1",
                "per_row": [
                    {
                        "id": "E002",
                        "category": "kb",
                        "scores": {"correctness": "no", "retrieval_groundedness": "yes"},
                    },
                    {
                        "id": "E039",
                        "category": "adversarial",
                        "scores": {"expectations_guidelines": "yes"},
                    },
                    {"id": "E050", "category": "kb", "scores": {"correctness": "no"}},
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_the_command_writes_the_csv_file_and_the_page_and_reports_differences(
    tmp_path: Path,
    saved_result: Path,
    traces: list[Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    asked: list[str] = []
    monkeypatch.setattr(sheet_module, "read_traces", lambda run_id: asked.append(run_id) or traces)
    out = tmp_path / "labels"

    main([str(saved_result), "--out-dir", str(out)])

    assert asked == ["run-1"]
    stem = "2026-11-15_m4-full-A-ann_judge_sheet"
    assert sorted(path.name for path in out.iterdir()) == [f"{stem}.csv", f"{stem}.md"]
    written = read_csv(out / f"{stem}.csv")
    assert [row["key"] for row in written][:2] == ["E002:correctness", "E050:correctness"]
    assert written[0]["category"] == "kb"
    page = (out / f"{stem}.md").read_text(encoding="utf-8")
    assert "run on 2026-11-15 (UTC) at commit `8624268`" in page
    assert "judged by `databricks-meta-llama-3-3-70b-instruct`" in page
    printed = capsys.readouterr().out
    assert "differs from the result file: E050 correctness: no in the result, yes on" in printed
    assert "correctness: 2 verdicts (1 yes, 1 no)" in printed
    assert "5 traces read, 1 differences from the result file." in printed


def test_a_blind_export_keeps_every_verdict_out_of_the_sheet_and_the_page(
    tmp_path: Path,
    saved_result: Path,
    traces: list[Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sheet_module, "read_traces", lambda run_id: traces)
    out = tmp_path / "labels"

    main([str(saved_result), "--out-dir", str(out), "--blind", "--sample", "1"])

    stem = "2026-11-15_m4-full-A-ann_judge_sheet"
    sheet = read_csv(out / f"{stem}.csv")
    assert len(sheet) == 3
    assert all(row["judge_verdict"] == "" and row["judge_rationale"] == "" for row in sheet)
    hidden = read_csv(out / f"{stem}_verdicts.csv")
    assert [row["key"] for row in hidden] == [row["key"] for row in sheet]
    assert {row["judge_verdict"] for row in hidden} <= {"yes", "no"}
    page = (out / f"{stem}.md").read_text(encoding="utf-8")
    assert "This sheet is blind" in page
    assert "This is a sample: at most 1 verdicts of each judge" in page
    assert "The judge's verdict" not in page
    assert "does not say it can be waived" not in page
    # The counts of yes and no would give the verdicts away, so they are not printed.
    printed = capsys.readouterr().out
    assert "correctness: 1 verdicts\n" in printed
    assert " yes, " not in printed


def test_the_command_stops_when_the_run_has_no_verdict_to_label(
    tmp_path: Path,
    saved_result: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sheet_module, "read_traces", lambda run_id: [])

    with pytest.raises(SystemExit):
        main([str(saved_result), "--out-dir", str(tmp_path / "labels")])

    assert "no verdict of correctness" in capsys.readouterr().out
    assert not (tmp_path / "labels").exists()


def test_the_command_renders_a_csv_file_without_reading_any_trace(
    tmp_path: Path,
    rows: list[dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def no_workspace(run_id: str) -> list[Any]:
        raise AssertionError("rendering must not read traces")

    monkeypatch.setattr(sheet_module, "read_traces", no_workspace)
    path = tmp_path / "sheet.csv"
    write_csv(rows, path)

    main(["--render", str(path)])

    assert (tmp_path / "sheet.md").exists()
    assert "wrote" in capsys.readouterr().out
