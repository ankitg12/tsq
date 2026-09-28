"""CLI behavior for Logseq goal completion notes."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def goals(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / "tsq.py"
    spec = importlib.util.spec_from_file_location("tsq", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "JOURNALS_DIR", tmp_path)
    return module


def invoke(goals, monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["tsq", *args])
    return goals.main()


def test_add_status_sets_initial_marker_without_changing_list_filter(
    goals, tmp_path, monkeypatch, capsys
):
    page = tmp_path / "2026_09_25.md"
    assert (
        invoke(goals, monkeypatch, "add", "-s", "now", "active", "--date", "2026-09-25")
        == 0
    )
    capsys.readouterr()
    assert invoke(goals, monkeypatch, "add", "waiting", "--date", "2026-09-25") == 0
    capsys.readouterr()
    assert (
        invoke(
            goals,
            monkeypatch,
            "add",
            "--status",
            "DoNe",
            "finished",
            "--date",
            "2026-09-25",
        )
        == 0
    )
    capsys.readouterr()
    assert page.read_text() == (
        "- [[Goals]]\n\t- NOW active\n\t- LATER waiting\n\t- DONE finished\n"
    )
    assert invoke(goals, monkeypatch, "--status", "now", "--date", "2026-09-25") == 0
    assert capsys.readouterr().out == "1. [ ] active\n"
    assert invoke(goals, monkeypatch, "-s", "done", "--date", "2026-09-25") == 0
    assert capsys.readouterr().out == "3. [x] finished\n"


def test_add_rejects_unknown_status_without_writing(
    goals, tmp_path, monkeypatch, capsys
):
    page = tmp_path / "2026_09_25.md"
    with pytest.raises(SystemExit) as error:
        invoke(goals, monkeypatch, "add", "-s", "active", "new", "--date", "2026-09-25")
    assert error.value.code == 2
    assert not page.exists()
    assert "invalid choice" in capsys.readouterr().err
    with pytest.raises(SystemExit) as help_exit:
        invoke(goals, monkeypatch, "add", "-h")
    assert help_exit.value.code == 0
    help_text = capsys.readouterr().out
    assert "--status {NOW,LATER,DONE}" in help_text
    assert "default: LATER" in help_text


def test_done_note_is_nested_and_visible(goals, tmp_path, monkeypatch, capsys):
    page = tmp_path / "2026_09_25.md"
    page.write_text(
        "- [[Goals]]\n\t- LATER first\n\t- LATER check new llm\n"
        "\t\tid:: existing\n- journal entry\n"
    )
    assert (
        invoke(
            goals,
            monkeypatch,
            "done",
            "2",
            "added gpt 6 models",
            "--date",
            "2026-09-25",
        )
        == 0
    )
    assert page.read_text() == (
        "- [[Goals]]\n\t- LATER first\n\t- DONE check new llm\n"
        "\t\tid:: existing\n\t\t- added gpt 6 models\n- journal entry\n"
    )
    assert capsys.readouterr().out == (
        "LATER:\n1. [ ] first\n\nDONE:\n2. [x] check new llm\n   added gpt 6 models\n"
    )
    assert invoke(goals, monkeypatch, "--date", "2026-09-25") == 0
    assert "2. [x] check new llm\n   added gpt 6 models" in capsys.readouterr().out
    assert invoke(goals, monkeypatch, "undo", "2", "--date", "2026-09-25") == 0
    assert (
        "\t- LATER check new llm\n\t\tid:: existing\n\t\t- added gpt 6 models"
        in page.read_text()
    )


def test_read_sorts_completed_last_without_writing_or_changing_numbers(
    goals, tmp_path, monkeypatch, capsys
):
    page = tmp_path / "2026_09_25.md"
    original = (
        "- [[Goals]]\n\t- DONE first\n\t- LATER second\n"
        "\t- DONE third\n\t\t- completion note\n\t- NOW fourth\n"
    )
    page.write_text(original)
    assert invoke(goals, monkeypatch, "--date", "2026-09-25") == 0
    assert capsys.readouterr().out == (
        "NOW:\n4. [ ] fourth\n\nLATER:\n2. [ ] second\n"
        "\nDONE:\n1. [x] first\n3. [x] third\n   completion note\n"
    )
    assert invoke(goals, monkeypatch, "3", "--date", "2026-09-25") == 0
    assert capsys.readouterr().out == "3. [x] third\n   completion note\n"
    assert page.read_text() == original


def test_done_moves_goal_and_note_after_existing_completed_goals(
    goals, tmp_path, monkeypatch, capsys
):
    page = tmp_path / "2026_09_25.md"
    page.write_text(
        "- [[Goals]]\n\t- LATER first\n\t- LATER second\n"
        "\t- DONE old\n\t\t- old note\n- journal entry\n"
    )
    assert (
        invoke(
            goals, monkeypatch, "done", "1", "proof", "recorded", "--date", "2026-09-25"
        )
        == 0
    )
    assert page.read_text() == (
        "- [[Goals]]\n\t- LATER second\n\t- DONE old\n\t\t- old note\n"
        "\t- DONE first\n\t\t- proof recorded\n- journal entry\n"
    )
    assert capsys.readouterr().out == (
        "LATER:\n1. [ ] second\n\nDONE:\n2. [x] old\n   old note\n"
        "3. [x] first\n   proof recorded\n"
    )


def test_set_done_moves_last_and_undo_returns_to_open_group(
    goals, tmp_path, monkeypatch, capsys
):
    page = tmp_path / "2026_09_25.md"
    page.write_text("- [[Goals]]\n\t- LATER first\n\t- LATER second\n\t- DONE old\n")
    assert (
        invoke(goals, monkeypatch, "1", "set", "status", "done", "--date", "2026-09-25")
        == 0
    )
    assert page.read_text() == (
        "- [[Goals]]\n\t- LATER second\n\t- DONE old\n\t- DONE first\n"
    )
    capsys.readouterr()
    assert invoke(goals, monkeypatch, "undo", "2", "--date", "2026-09-25") == 0
    assert page.read_text() == (
        "- [[Goals]]\n\t- LATER second\n\t- LATER old\n\t- DONE first\n"
    )
    assert capsys.readouterr().out == (
        "LATER:\n1. [ ] second\n2. [ ] old\n\nDONE:\n3. [x] first\n"
    )


def test_writing_normalizes_goals_checked_in_logseq(
    goals, tmp_path, monkeypatch, capsys
):
    page = tmp_path / "2026_09_25.md"
    page.write_text(
        "- [[Goals]]\n\t- DONE first\n\t\t- proof\n"
        "\t- LATER second\n\t- DONE third\n\t- NOW fourth\n"
    )
    assert invoke(goals, monkeypatch, "mv", "2", "2", "--date", "2026-09-25") == 0
    assert page.read_text() == (
        "- [[Goals]]\n\t- LATER second\n\t- NOW fourth\n"
        "\t- DONE first\n\t\t- proof\n\t- DONE third\n"
    )
    assert capsys.readouterr().out == (
        "NOW:\n2. [ ] fourth\n\nLATER:\n1. [ ] second\n"
        "\nDONE:\n3. [x] first\n   proof\n4. [x] third\n"
    )


def test_status_filters_keep_journal_numbers_and_do_not_write(
    goals, tmp_path, monkeypatch, capsys
):
    page = tmp_path / "2026_09_25.md"
    original = (
        "- [[Goals]]\n\t- DONE first\n\t- LATER second\n"
        "\t- NOW third\n\t\t- in progress\n\t- LATER fourth\n\t- DONE fifth\n"
    )
    page.write_text(original)
    for flag, marker, expected in (
        ("--status", "now", "3. [ ] third\n   in progress\n"),
        ("-s", "LATER", "2. [ ] second\n4. [ ] fourth\n"),
        ("--status", "done", "1. [x] first\n5. [x] fifth\n"),
    ):
        assert invoke(goals, monkeypatch, flag, marker, "--date", "2026-09-25") == 0
        assert capsys.readouterr().out == expected
        assert page.read_text() == original
    assert invoke(goals, monkeypatch, "3", "--date", "2026-09-25") == 0
    assert capsys.readouterr().out == "3. [ ] third [NOW]\n   in progress\n"


def test_status_filter_empty_result_and_invalid_uses(
    goals, tmp_path, monkeypatch, capsys
):
    page = tmp_path / "2026_09_25.md"
    original = "- [[Goals]]\n\t- LATER only\n"
    page.write_text(original)
    assert invoke(goals, monkeypatch, "-s", "now", "--date", "2026-09-25") == 0
    assert capsys.readouterr().out == ""
    for args in (("--status", "active"), ("--status", "now", "add", "new")):
        with pytest.raises(SystemExit) as error:
            invoke(goals, monkeypatch, *args, "--date", "2026-09-25")
        assert error.value.code == 2
        capsys.readouterr()
        assert page.read_text() == original


def test_done_without_note_keeps_existing_behavior(goals, tmp_path, monkeypatch):
    page = tmp_path / "2026_09_25.md"
    page.write_text("- [[Goals]]\n\t- LATER one\n")
    assert invoke(goals, monkeypatch, "done", "1", "--date", "2026-09-25") == 0
    assert page.read_text() == "- [[Goals]]\n\t- DONE one\n"


def test_invalid_note_does_not_change_journal(goals, tmp_path, monkeypatch, capsys):
    page = tmp_path / "2026_09_25.md"
    original = "- [[Goals]]\n\t- LATER one\n"
    page.write_text(original)
    assert invoke(goals, monkeypatch, "done", "1", "bad\nline") == 2
    assert "BAD_NOTE" in capsys.readouterr().err
    assert page.read_text() == original


def test_done_only_list_stays_visible(goals, tmp_path, monkeypatch, capsys):
    (tmp_path / "2026_09_25.md").write_text("- [[Goals]]\n\t- DONE only\n")
    assert invoke(goals, monkeypatch, "--date", "2026-09-25") == 0
    assert capsys.readouterr().out == "DONE:\n1. [x] only\n"


def test_get_one_and_note_preserve_status_and_other_blocks(
    goals, tmp_path, monkeypatch, capsys
):
    page = tmp_path / "2026_09_25.md"
    page.write_text(
        "- [[Goals]]\n\t- LATER first\n\t- DONE second\n"
        "\t\tid:: existing\n\t\t- earlier note\n- journal entry\n"
    )
    assert (
        invoke(
            goals,
            monkeypatch,
            "--date",
            "2026-09-25",
            "set",
            "2",
            "note",
            "next",
            "step",
        )
        == 0
    )
    assert page.read_text() == (
        "- [[Goals]]\n\t- LATER first\n\t- DONE second\n"
        "\t\tid:: existing\n\t\t- earlier note\n"
        "\t\t- next step\n- journal entry\n"
    )
    capsys.readouterr()
    assert invoke(goals, monkeypatch, "get", "2", "--date", "2026-09-25") == 0
    assert capsys.readouterr().out == "2. [x] second\n   earlier note\n   next step\n"
    assert invoke(goals, monkeypatch, "--date", "2026-09-25") == 0
    assert capsys.readouterr().out == (
        "LATER:\n1. [ ] first\n\nDONE:\n2. [x] second\n   earlier note\n   next step\n"
    )
    assert invoke(goals, monkeypatch, "mv", "2", "1", "--date", "2026-09-25") == 0
    capsys.readouterr()
    assert invoke(goals, monkeypatch, "get", "2", "--date", "2026-09-25") == 0
    assert capsys.readouterr().out == "2. [x] second\n   earlier note\n   next step\n"


def test_get_missing_and_bad_notes_do_not_change_file(
    goals, tmp_path, monkeypatch, capsys
):
    page = tmp_path / "2026_09_25.md"
    original = "- [[Goals]]\n\t- LATER first\n"
    page.write_text(original)
    with pytest.raises(SystemExit) as error:
        invoke(goals, monkeypatch, "get", "2", "--date", "2026-09-25")
    assert error.value.code == 2
    assert "NO_SUCH_TASK: 2" in capsys.readouterr().err
    for args in (("set", "1", "note", "bad\nline"), ("set", "1", "note", "   ")):
        assert invoke(goals, monkeypatch, *args, "--date", "2026-09-25") == 2
        assert "BAD_VALUE" in capsys.readouterr().err
        assert page.read_text() == original
    with pytest.raises(SystemExit) as error:
        invoke(goals, monkeypatch, "set", "2", "note", "text", "--date", "2026-09-25")
    assert error.value.code == 2
    assert page.read_text() == original


def test_set_text_preserves_status_and_notes(goals, tmp_path, monkeypatch, capsys):
    page = tmp_path / "2026_09_25.md"
    page.write_text("- [[Goals]]\n\t- DONE old title\n\t\t- earlier note\n")
    assert (
        invoke(
            goals,
            monkeypatch,
            "set",
            "1",
            "text",
            "new",
            "title",
            "--date",
            "2026-09-25",
        )
        == 0
    )
    assert page.read_text() == "- [[Goals]]\n\t- DONE new title\n\t\t- earlier note\n"
    capsys.readouterr()
    assert invoke(goals, monkeypatch, "get", "1", "--date", "2026-09-25") == 0
    assert capsys.readouterr().out == "1. [x] new title\n   earlier note\n"
    with pytest.raises(SystemExit) as error:
        invoke(goals, monkeypatch, "get")
    assert error.value.code == 2
    with pytest.raises(SystemExit) as error:
        invoke(goals, monkeypatch, "show", "1")
    assert error.value.code == 2


def test_optional_fields_replace_without_duplication(
    goals, tmp_path, monkeypatch, capsys
):
    page = tmp_path / "2026_09_25.md"
    original = "- [[Goals]]\n\t- LATER first\n\t\tid:: existing\n"
    page.write_text(original)
    for field, value in (
        ("evidence", "a passing case"),
        ("due", "2026-09-26"),
        ("blocked-on", "testbed access"),
        ("evidence", "case log"),
    ):
        assert (
            invoke(goals, monkeypatch, "set", "1", field, value, "--date", "2026-09-25")
            == 0
        )
        capsys.readouterr()
    assert page.read_text() == (
        original + "\t\tevidence:: case log\n\t\tdue:: 2026-09-26\n"
        "\t\tblocked-on:: testbed access\n"
    )
    assert invoke(goals, monkeypatch, "get", "1", "--date", "2026-09-25") == 0
    assert capsys.readouterr().out == (
        "1. [ ] first\n   evidence: case log\n   due: 2026-09-26\n"
        "   blocked-on: testbed access\n"
    )
    assert (
        invoke(
            goals, monkeypatch, "set", "1", "due", "2026-02-30", "--date", "2026-09-25"
        )
        == 2
    )
    assert "BAD_DUE" in capsys.readouterr().err
    assert page.read_text().count("due::") == 1


def test_numbered_help_lists_available_set_fields(goals, monkeypatch, capsys):
    assert invoke(goals, monkeypatch, "2", "-h") == 0
    help_text = capsys.readouterr().out
    assert "usage: tsq 2" in help_text
    assert "tsq 2 set FIELD VALUE" in help_text
    assert "tsq 2 now|later|done" in help_text
    assert "text, status, note, evidence, due, blocked-on" in help_text
    assert "LATER, NOW, DONE" in help_text
    assert "--date YYYY-MM-DD" in help_text
    assert invoke(goals, monkeypatch, "--date", "2026-09-25", "2", "-h") == 0
    assert "tsq 2 set FIELD VALUE" in capsys.readouterr().out
    assert invoke(goals, monkeypatch, "2", "set", "-h") == 0
    set_help = capsys.readouterr().out
    assert "usage: tsq 2 set" in set_help
    assert "{text,status,note,evidence,due,blocked-on}" in set_help
    assert "status values: LATER, NOW, DONE" in set_help
    assert "usage: tsq set" not in set_help


def test_goal_first_read_and_lowercase_status(goals, tmp_path, monkeypatch, capsys):
    page = tmp_path / "2026_09_25.md"
    page.write_text("- [[Goals]]\n\t- LATER first\n\t\t- existing note\n")
    assert invoke(goals, monkeypatch, "--date", "2026-09-25", "1") == 0
    assert capsys.readouterr().out == "1. [ ] first\n   existing note\n"
    assert (
        invoke(goals, monkeypatch, "1", "set", "status", "now", "--date", "2026-09-25")
        == 0
    )
    assert page.read_text() == "- [[Goals]]\n\t- NOW first\n\t\t- existing note\n"
    assert "NOW:\n1. [ ] first\n" in capsys.readouterr().out
    assert invoke(goals, monkeypatch, "1", "--date", "2026-09-25") == 0
    assert capsys.readouterr().out == "1. [ ] first [NOW]\n   existing note\n"
    assert invoke(goals, monkeypatch, "get", "1", "--date", "2026-09-25") == 0
    assert capsys.readouterr().out == "1. [ ] first [NOW]\n   existing note\n"


def test_number_first_status_changes_preserve_notes_and_date(
    goals, tmp_path, monkeypatch, capsys
):
    page = tmp_path / "2026_09_25.md"
    page.write_text(
        "- [[Goals]]\n\t- LATER first\n\t\t- existing note\n\t- DONE finished\n"
    )
    assert invoke(goals, monkeypatch, "--date", "2026-09-25", "1", "now") == 0
    assert page.read_text() == (
        "- [[Goals]]\n\t- NOW first\n\t\t- existing note\n\t- DONE finished\n"
    )
    assert "NOW:\n1. [ ] first\n" in capsys.readouterr().out
    assert invoke(goals, monkeypatch, "1", "DONE", "--date", "2026-09-25") == 0
    assert page.read_text() == (
        "- [[Goals]]\n\t- DONE finished\n\t- DONE first\n\t\t- existing note\n"
    )
    assert "2. [x] first" in capsys.readouterr().out
    assert invoke(goals, monkeypatch, "2", "later", "--date", "2026-09-25") == 0
    assert page.read_text() == (
        "- [[Goals]]\n\t- LATER first\n\t\t- existing note\n\t- DONE finished\n"
    )
    assert "1. [ ] first" in capsys.readouterr().out


def test_set_now_status_preserves_goal_and_rejects_unknown_status(
    goals, tmp_path, monkeypatch, capsys
):
    page = tmp_path / "2026_09_25.md"
    page.write_text("- [[Goals]]\n\t- LATER first\n\t\t- existing note\n")
    assert (
        invoke(goals, monkeypatch, "set", "1", "status", "NOW", "--date", "2026-09-25")
        == 0
    )
    assert page.read_text() == "- [[Goals]]\n\t- NOW first\n\t\t- existing note\n"
    assert "NOW:\n1. [ ] first\n   existing note" in capsys.readouterr().out
    assert invoke(goals, monkeypatch, "get", "1", "--date", "2026-09-25") == 0
    assert capsys.readouterr().out == "1. [ ] first [NOW]\n   existing note\n"
    assert (
        invoke(
            goals, monkeypatch, "set", "1", "status", "ACTIVE", "--date", "2026-09-25"
        )
        == 2
    )
    assert "BAD_STATUS" in capsys.readouterr().err
    assert page.read_text() == "- [[Goals]]\n\t- NOW first\n\t\t- existing note\n"


def test_configured_second_graph_preserves_other_blocks(tmp_path):
    graph_one = tmp_path / "first" / "journals"
    graph_two = tmp_path / "second" / "journals"
    graph_one.mkdir(parents=True)
    graph_two.mkdir(parents=True)
    date = "2026-09-25"
    graph_one_page = graph_one / "2026_09_25.md"
    graph_one_page.write_text("- [[Goals]]\n\t- LATER keep this\n")
    second_page = graph_two / "2026_09_25.md"
    second_page.write_text("- 09:00 unrelated journal entry\n")
    env = {**os.environ, "TSQ_JOURNALS_DIR": str(graph_two)}
    script = Path(__file__).resolve().parents[1] / "tsq.py"
    added = subprocess.run(
        [
            sys.executable,
            str(script),
            "add",
            "-s",
            "now",
            "draft review",
            "--date",
            date,
        ],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    assert "NOW:\n1. [ ] draft review\n" in added.stdout
    assert second_page.read_text() == (
        "- [[Goals]]\n\t- NOW draft review\n- 09:00 unrelated journal entry\n"
    )
    assert graph_one_page.read_text() == "- [[Goals]]\n\t- LATER keep this\n"
    listed = subprocess.run(
        [sys.executable, str(script), "-s", "now", "--date", date],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    assert listed.stdout == "1. [ ] draft review\n"


def test_carry_copies_open_goals_with_notes_but_not_block_ids(
    goals, tmp_path, monkeypatch, capsys
):
    (tmp_path / "2026_09_25.md").write_text(
        "- [[Goals]]\n\t- NOW first\n\t\tid:: 66f0-abc\n\t\t- step one\n"
        "\t- LATER second\n\t- DONE finished\n\t- CANCELED dropped\n- 09:00 log\n"
    )
    # 09-26 and 09-27 have no goals, so 09-25 is the source.
    (tmp_path / "2026_09_27.md").write_text("- 10:00 weekend note\n")
    today = tmp_path / "2026_09_28.md"
    today.write_text("- [[Goals]]\n\t- LATER second\n- 11:00 standup\n")
    assert invoke(goals, monkeypatch, "carry", "--date", "2026-09-28") == 0
    out = capsys.readouterr().out
    assert out.startswith("CARRIED 1 from 2026-09-25, 1 already present\n")
    assert today.read_text() == (
        "- [[Goals]]\n\t- LATER second\n\t- NOW first\n\t\t- step one\n"
        "- 11:00 standup\n"
    )
    before = today.read_text()
    assert invoke(goals, monkeypatch, "carry", "--date", "2026-09-28") == 0
    assert capsys.readouterr().out == "CARRIED 0 from 2026-09-25, 2 already present\n"
    assert today.read_text() == before


def test_carry_explicit_source_and_missing_source(goals, tmp_path, monkeypatch, capsys):
    (tmp_path / "2026_09_20.md").write_text("- [[Goals]]\n\t- LATER old\n")
    assert (
        invoke(
            goals, monkeypatch, "carry", "--from", "2026-09-20", "--date", "2026-09-28"
        )
        == 0
    )
    assert "CARRIED 1 from 2026-09-20" in capsys.readouterr().out
    assert invoke(goals, monkeypatch, "carry", "--date", "2026-01-01") == 1
    assert capsys.readouterr().out.startswith("NO_SOURCE")
    assert not (tmp_path / "2026_01_01.md").exists()
