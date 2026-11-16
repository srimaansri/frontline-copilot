"""The fingerprint that ties a saved evaluation to the code and settings it measured."""

from pathlib import Path

from eval.fingerprint import (
    ANSWER_PATH_MODULES,
    behaviour_fingerprint,
    changed_files,
    file_digest,
)


def make_repo(root: Path) -> None:
    (root / "src" / "copilot").mkdir(parents=True)
    (root / "config").mkdir()
    (root / "eval").mkdir()
    (root / "src" / "copilot" / "agent.py").write_text(
        'PROMPT = "Answer plainly."\n\n\ndef run(question):\n    return question\n',
        encoding="utf-8",
    )
    (root / "config" / "settings.yaml").write_text("router: model\n", encoding="utf-8")
    (root / "eval" / "eval_set.jsonl").write_text('{"id": "E001"}\n', encoding="utf-8")
    (root / "eval" / "scorers.py").write_text("X = 1\n", encoding="utf-8")
    # Not something that decides behaviour, so it is not part of the fingerprint.
    (root / "README.md").write_text("hello\n", encoding="utf-8")


def test_the_fingerprint_covers_the_code_the_settings_and_the_evaluation_set(
    tmp_path: Path,
) -> None:
    make_repo(tmp_path)

    fingerprint = behaviour_fingerprint(tmp_path)

    assert list(fingerprint["files"]) == [  # type: ignore[call-overload]
        "config/settings.yaml",
        "eval/eval_set.jsonl",
        "eval/scorers.py",
        "src/copilot/agent.py",
    ]
    assert fingerprint == behaviour_fingerprint(tmp_path)


def test_a_comment_or_a_reformat_does_not_change_it_but_a_prompt_does(tmp_path: Path) -> None:
    make_repo(tmp_path)
    agent = tmp_path / "src" / "copilot" / "agent.py"
    before = behaviour_fingerprint(tmp_path)["sha256"]

    agent.write_text(
        '# A note.\nPROMPT = "Answer plainly."\n\ndef run( question ):\n    return question\n',
        encoding="utf-8",
    )
    assert behaviour_fingerprint(tmp_path)["sha256"] == before

    agent.write_text(
        'PROMPT = "Answer briefly."\n\n\ndef run(question):\n    return question\n',
        encoding="utf-8",
    )
    assert behaviour_fingerprint(tmp_path)["sha256"] != before


def test_a_change_of_setting_or_of_a_question_changes_it(tmp_path: Path) -> None:
    make_repo(tmp_path)
    before = behaviour_fingerprint(tmp_path)

    (tmp_path / "config" / "settings.yaml").write_text("router: rules\n", encoding="utf-8")
    after = behaviour_fingerprint(tmp_path)

    assert after["sha256"] != before["sha256"]
    assert changed_files(before["files"], after["files"]) == ["config/settings.yaml"]  # type: ignore[arg-type]

    (tmp_path / "src" / "copilot" / "router.py").write_text("Y = 2\n", encoding="utf-8")
    assert changed_files(before["files"], behaviour_fingerprint(tmp_path)["files"]) == [  # type: ignore[arg-type]
        "config/settings.yaml",
        "src/copilot/router.py",
    ]


def test_a_module_off_the_answering_path_is_not_part_of_it(tmp_path: Path) -> None:
    make_repo(tmp_path)
    before = behaviour_fingerprint(tmp_path)

    (tmp_path / "src" / "copilot" / "compliance.py").write_text("Z = 3\n", encoding="utf-8")

    assert behaviour_fingerprint(tmp_path) == before


def test_a_run_saved_when_more_files_counted_is_not_stale_for_the_ones_dropped() -> None:
    saved = {"src/copilot/agent.py": "1", "src/copilot/compliance.py": "9"}
    current = {"src/copilot/agent.py": "1"}

    assert changed_files(saved, current) == []
    assert changed_files(saved, {"src/copilot/agent.py": "2"}) == ["src/copilot/agent.py"]
    assert changed_files(saved, {**current, "src/copilot/router.py": "1"}) == [
        "src/copilot/router.py"
    ]


def test_every_module_the_agent_imports_is_on_the_list() -> None:
    """A new module on the answering path must be added to the fingerprint by hand."""
    import ast

    seen: set[str] = set()
    queue = ["agent"]
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        tree = ast.parse(Path(f"src/copilot/{name}.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("copilot.")
            ):
                queue.append(node.module.split(".", 1)[1])

    assert seen <= set(ANSWER_PATH_MODULES), sorted(seen - set(ANSWER_PATH_MODULES))


def test_line_endings_do_not_change_a_text_file_s_digest(tmp_path: Path) -> None:
    unix = tmp_path / "a.yaml"
    windows = tmp_path / "b.yaml"
    unix.write_bytes(b"router: model\nrouter_endpoint: x\n")
    windows.write_bytes(b"router: model\r\nrouter_endpoint: x\r\n")

    assert file_digest(unix) == file_digest(windows)


def test_the_repository_has_a_fingerprint() -> None:
    fingerprint = behaviour_fingerprint()

    assert "src/copilot/agent.py" in fingerprint["files"]  # type: ignore[operator]
    assert "config/settings.yaml" in fingerprint["files"]  # type: ignore[operator]
    assert len(str(fingerprint["sha256"])) == 64
