import pytest

from sciencelogo_mcp import syntax
from sciencelogo_mcp.workspace import offset


def test_values():
    assert syntax.value(None) == "unknown"
    assert syntax.value(True) == "true"
    assert syntax.value(0.00001) == "0.00001"
    assert syntax.value(10) == "10"
    assert syntax.value('say "hi"\n') == '"say \\"hi\\"\\n"'
    assert syntax.value([1, "a"]) == '[1 "a"]'
    assert syntax.value({"kind": "human", "age": None}) == '[kind = "human" age = unknown]'
    assert syntax.value({"expr": "trial.unit"}) == "trial.unit"


def test_interface_fields():
    text = syntax.interface(
        "fit",
        [
            {"name": "period", "type": "number", "unit": "seconds"},
            {"name": "label", "type": "text"},
            {"name": "note", "default": "none", "required": False},
        ],
        extends=["base"],
        version="1",
    )
    assert text == (
        'interface fit [version "1" extends base '
        'must [period [value = unknown number unit = "seconds"] label is text] '
        'note = "none"]'
    )


def test_procedure_describes_its_result():
    text = syntax.procedure(
        "time-swings",
        ["count"],
        "Time the swings.",
        None,
        [{"name": "elapsed", "type": "number", "unit": "seconds"}],
        [{"name": "reaction", "description": "Reaction time."}],
    )
    assert text.splitlines() == [
        'interface time-swings-result [must [elapsed [value = unknown number unit = "seconds"]]]',
        'to time-swings :count about "Time the swings." [',
        '  output time-swings-result.[] u [declared = [reaction = [text = "Reaction time."]]]',
        "]",
    ]


def test_procedure_without_result_outputs_unknown():
    assert "output unknown" in syntax.procedure("step", [], "Do it.", None)


def test_exit_state_adds_into_locations():
    entry = {"information": {"count": 10}}
    calls = [{"procedure": "p", "into": "information.result.value"}]
    assert syntax.exit_state(entry, calls) == {
        "information": {"count": 10, "result": {"value": None}}
    }
    assert entry == {"information": {"count": 10}}


def test_requirements():
    assert syntax.requirement("call", ["fit"]) == "must do fit"
    assert syntax.requirement("stage_order", ["A", "B"]) == "must stages in order [A B]"
    with pytest.raises(ValueError):
        syntax.requirement("stage_order", ["A"])


def test_reader_positions_count_crlf_once():
    content = "#lang sciencelogo\r\nperformer a []\r\nperformer b []\n"
    assert content[offset(content, 19) :].startswith("performer a")
    assert content[offset(content, 34) :].startswith("performer b")
