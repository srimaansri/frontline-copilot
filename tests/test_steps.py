"""The plain-language account of what the copilot did, built from an answer's own record."""

from copilot.schemas import Citation, CopilotAnswer
from copilot.steps import describe_steps

CITATION = Citation(number=1, title="Late payment fee", url="https://x.example/late-payment-fee")


def answer(**fields: object) -> CopilotAnswer:
    return CopilotAnswer(answer="A.", **fields)  # type: ignore[arg-type]


def titles(steps: list) -> list[str]:  # type: ignore[type-arg]
    return [step.title for step in steps]


def test_a_cited_help_answer_reads_as_four_clean_steps() -> None:
    steps = describe_steps(answer(tools_used=["search_kb"], citations=[CITATION]))

    assert [step.stage for step in steps] == [
        "redaction",
        "input_check",
        "tool",
        "output_check",
        "output_check",
    ]
    assert titles(steps) == [
        "No personal details found",
        "Request allowed",
        "Searched the help articles",
        "Citations checked",
        "No personal details in the answer",
    ]
    assert all(step.status == "ok" for step in steps)
    assert steps[2].tool == "search_kb"
    assert steps[2].detail == "1 source cited."


def test_removed_personal_details_are_named_in_plain_words() -> None:
    flags = [
        "pii_in_question:PERSON",
        "pii_in_question:PHONE_NUMBER",
        "pii_in_question:SSN_LAST4",
    ]

    first = describe_steps(answer(guardrail_flags=flags))[0]
    single = describe_steps(answer(guardrail_flags=["pii_in_question:EMAIL_ADDRESS"]))[0]
    unknown = describe_steps(answer(guardrail_flags=["pii_in_question:NEW_KIND"]))[0]

    assert first.title == "Personal details removed"
    assert first.status == "notice"
    assert first.detail == (
        "A name, a phone number and Social Security digits were replaced before the "
        "question was processed or logged."
    )
    assert single.detail.startswith("An email address was replaced")
    assert unknown.detail.startswith("New kind was replaced")


def test_an_account_request_shows_the_hand_off() -> None:
    steps = describe_steps(
        answer(
            tools_used=["escalate_to_human"],
            escalated=True,
            guardrail_flags=["account_action_requested"],
        )
    )

    assert steps[1].title == "Account request: handed to a person"
    assert steps[1].status == "warning"
    assert steps[2].title == "Opened a hand-off"
    assert "reason redacted" in steps[2].detail


def test_an_override_attempt_is_shown_as_blocked_with_no_tool() -> None:
    steps = describe_steps(answer(guardrail_flags=["injection_suspected"]))

    assert steps[1].title == "Override attempt blocked"
    assert steps[1].status == "blocked"
    assert [step.stage for step in steps].count("tool") == 0


def test_each_tool_has_its_own_line() -> None:
    steps = describe_steps(
        answer(tools_used=["get_plan_details", "summarize_call", "something_new"])
    )
    tools = [step for step in steps if step.stage == "tool"]

    assert [step.title for step in tools] == [
        "Looked up the plan catalogue",
        "Summarized the call",
        "Used something_new",
    ]
    assert "not from memory" in tools[0].detail
    assert "redacted transcript only" in tools[1].detail


def test_search_results_that_were_empty_or_uncited_are_said_plainly() -> None:
    nothing = describe_steps(answer(tools_used=["search_kb"], guardrail_flags=["no_context"]))
    uncited = describe_steps(answer(tools_used=["search_kb"], guardrail_flags=["no_citation"]))
    two = describe_steps(answer(tools_used=["search_kb"], citations=[CITATION, CITATION]))

    assert (nothing[2].detail, nothing[2].status) == ("No article matched.", "notice")
    assert uncited[2].detail == "Articles were found. The answer cites none of them."
    assert two[2].detail == "2 sources cited."


def test_a_failed_lookup_is_a_warning_on_that_tool() -> None:
    steps = describe_steps(
        answer(tools_used=["summarize_call"], guardrail_flags=["tool_error:summarize_call"])
    )

    assert steps[2].status == "warning"
    assert steps[2].detail == "The lookup failed, and the copilot said so."


def test_every_output_check_that_fired_is_listed() -> None:
    flags = [
        "tool_limit_reached",
        "empty_answer",
        "answer_simplified",
        "invalid_citation_removed",
        "pii_removed_from_answer:PHONE_NUMBER",
    ]

    steps = describe_steps(answer(tools_used=["search_kb"], guardrail_flags=flags))
    checks = {step.title: step for step in steps if step.stage == "output_check"}

    assert list(checks) == [
        "Stopped after the lookup limit",
        "No answer was produced",
        "Rewritten in plainer words",
        "A citation was removed",
        "Personal details kept out of the answer",
    ]
    assert checks["A citation was removed"].status == "warning"
    assert "a phone number" in checks["Personal details kept out of the answer"].detail


def test_the_hand_off_step_carries_the_ticket_reference_from_the_answer() -> None:
    handed_off = CopilotAnswer(
        answer="This needs a person. Your reference is ESC-B695DE84. They will take it from here.",
        tools_used=["escalate_to_human"],
        escalated=True,
        guardrail_flags=["account_action_requested"],
    )
    without_one = CopilotAnswer(answer="Passed on.", tools_used=["escalate_to_human"])
    searched = CopilotAnswer(answer="See ESC-B695DE84.", tools_used=["search_kb"])

    assert [step.reference for step in describe_steps(handed_off)] == [
        None,
        None,
        "ESC-B695DE84",
        None,
    ]
    assert all(step.reference is None for step in describe_steps(without_one))
    # Only a hand-off step may carry a reference, whatever the answer text says.
    assert all(step.reference is None for step in describe_steps(searched))


def test_a_dropped_earlier_message_is_reported() -> None:
    steps = describe_steps(answer(guardrail_flags=["history_turn_dropped"]))

    assert titles(steps) == [
        "No personal details found",
        "Request allowed",
        "An earlier message was left out",
        "No personal details in the answer",
    ]
    assert steps[2].status == "notice"
