import asyncio
import re
from importlib.resources import files

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from sciencelogo_mcp.server import create_server

ENTRY = "pendulum/workflow.rkt"


@pytest.fixture
def call(helper, tmp_path):
    server = create_server(helper=helper, root=tmp_path)

    def run(tool, **arguments):
        result = asyncio.run(server.call_tool(tool, arguments))
        assert not result.is_error, result.content
        return result.structured_content

    run.root = tmp_path
    return run


@pytest.fixture
def pendulum(call):
    assert call(
        "create_workflow",
        file=ENTRY,
        title="Pendulum period",
        about="Does the period change as the swing gets smaller?",
    )["saved"]
    return call


def text(call, path):
    return (call.root / "pendulum" / path).read_text(encoding="utf-8")


def test_construct_tools_build_a_valid_workflow(pendulum):
    call = pendulum
    saves = [
        call("declare_performer", entry=ENTRY, name="researcher", fields={"kind": "human"}),
        call("declare_resource", entry=ENTRY, name="timer", fields={"kind": "stopwatch"}),
        call(
            "declare_proposition",
            entry=ENTRY,
            type="hypothesis",
            name="constant-period",
            statement="The period stays constant.",
        ),
        call(
            "declare_procedure",
            entry=ENTRY,
            name="time-swings",
            inputs=["count"],
            about="Time a number of full swings with a stopwatch.",
            result=[{"name": "elapsed", "type": "number", "unit": "seconds"}],
            uncertainty=[{"name": "reaction-time", "description": "Reaction time."}],
        ),
        call("add_stage", entry=ENTRY, name="Setup", about="Set up the pendulum."),
        call(
            "add_paired_stage",
            entry=ENTRY,
            name="Measure",
            performer="researcher",
            about="Time the swings.",
            entry_state={"information": {"swing-count": 10}},
            calls=[
                {
                    "procedure": "time-swings",
                    "inputs": {"count": "information.swing-count"},
                    "into": "information.elapsed",
                }
            ],
        ),
        call("add_phase", entry=ENTRY, name="Measurement", about="Measure.", members=["Setup"]),
        call("add_requirement", entry=ENTRY, kind="stage_order", targets=["Setup", "Measure"]),
        call("add_requirement", entry=ENTRY, kind="call", targets=["time-swings"]),
    ]
    assert all(s["saved"] for s in saves), saves
    assert text(call, "stages/02-measure.rkt").splitlines()[-1] == (
        "end stage with state [information = [swing-count = 10 elapsed = unknown]]"
    )
    main = text(call, "workflow.rkt")
    assert main.index('include "stages/01-setup.rkt"') < main.index('include "stages/02-measure')
    outline = call("outline", entry=ENTRY)
    assert [s["name"] for s in outline["stages"]] == ["Setup", "Measure"]
    assert outline["phases"] == [{"name": "Measurement", "about": "Measure.", "members": ["Setup"]}]
    assert call("check", entry=ENTRY)["advice"] == []


def test_a_rejected_write_changes_nothing(pendulum):
    before = text(pendulum, "workflow.rkt")
    result = pendulum("write_fragment", entry=ENTRY, text="stage Broken [")
    assert result["saved"] is False
    assert "expected ]" in result["message"]
    assert result["file"] == "workflow.rkt"
    assert text(pendulum, "workflow.rkt") == before

    result = pendulum("write_fragment", entry=ENTRY, text="stage Lost [", file="stages/lost.rkt")
    assert result["saved"] is False
    assert not (pendulum.root / "pendulum" / "stages" / "lost.rkt").exists()
    assert text(pendulum, "workflow.rkt") == before


def test_declaring_again_replaces(pendulum):
    pendulum("declare_performer", entry=ENTRY, name="researcher", fields={"role": "a"})
    pendulum("declare_performer", entry=ENTRY, name="researcher", fields={"role": "b"})
    main = text(pendulum, "workflow.rkt")
    assert main.count("performer researcher") == 1
    assert 'role = "b"' in main


def test_replacing_a_procedure_replaces_its_result_interface(pendulum):
    for unit in ("seconds", "minutes"):
        pendulum(
            "declare_procedure",
            entry=ENTRY,
            name="fit",
            inputs=[],
            about="Fit.",
            result=[{"name": "period", "type": "number", "unit": unit}],
        )
    main = text(pendulum, "workflow.rkt")
    assert main.count("interface fit-result") == 1
    assert '"minutes"' in main and '"seconds"' not in main


def test_set_workflow_keeps_what_is_not_given(pendulum):
    pendulum("set_workflow", entry=ENTRY, about="A new summary.")
    lines = text(pendulum, "workflow.rkt").splitlines()
    assert lines[1:3] == ['workflow "Pendulum period"', 'about "A new summary."']


def test_move_keeps_method_order_and_remove(pendulum):
    pendulum("add_stage", entry=ENTRY, name="First", about="One.", file="workflow.rkt")
    pendulum("add_stage", entry=ENTRY, name="Second", about="Two.", file="workflow.rkt")
    assert pendulum("move_item", entry=ENTRY, item="stage:First", to_file="stages/first.rkt")[
        "saved"
    ]
    outline = pendulum("outline", entry=ENTRY)
    assert [s["name"] for s in outline["stages"]] == ["First", "Second"]
    assert pendulum("remove_item", entry=ENTRY, item="stage:Second")["saved"]
    assert "Second" not in text(pendulum, "workflow.rkt")


def test_read_workflow(pendulum):
    pendulum("add_stage", entry=ENTRY, name="Report", about="Report.", commands="x = 2\nprint x")
    item = pendulum("read_workflow", entry=ENTRY, item="stage:Report", syntax_form="compact")
    assert item["text"] == 'stage Report about "Report."\nx = 2\nprint x'
    verbose = pendulum("read_workflow", entry=ENTRY)
    assert "set x to 2" in verbose["files"]["stages/01-report.rkt"]


def test_read_workflow_returns_a_rejected_workflow_as_stored(call):
    old = call.root / "old" / "workflow.rkt"
    old.parent.mkdir()
    old.write_text('#lang sciencelogo\nto plan [about "Inside." output 1]\n', encoding="utf-8")
    result = call("read_workflow", entry="old/workflow.rkt")
    assert result["status"] == "invalid"
    assert result["files"]["workflow.rkt"] == old.read_text(encoding="utf-8")


def test_library_project(call):
    assert call("create_library", file="timing/library.rkt", name="timing")["saved"]
    assert call(
        "declare_procedure",
        entry="timing/library.rkt",
        name="time-swings",
        inputs=["count"],
        about="Time the swings.",
        result=[{"name": "elapsed", "type": "number", "unit": "seconds"}],
    )["saved"]
    library = (call.root / "timing" / "library.rkt").read_text(encoding="utf-8")
    assert library.startswith('#lang sciencelogo\nlibrary timing language "0.2" [\n')
    assert library.rstrip().endswith("]")
    assert call("outline", entry="timing/library.rkt")["kind"] == "library"


def test_tool_errors_are_reported(pendulum):
    with pytest.raises(ToolError, match="kind:name"):
        pendulum("remove_item", entry=ENTRY, item="nothing")
    with pytest.raises(ToolError, match="outside"):
        pendulum("write_fragment", entry=ENTRY, text="stage X", file="../elsewhere.rkt")


def test_the_guide_example_is_valid(call):
    guide = files("sciencelogo_mcp").joinpath("guide.md").read_text(encoding="utf-8")
    example = re.search(r"```\n(#lang sciencelogo\n.*?)```", guide, re.S).group(1)
    folder = call.root / "guide"
    (folder / "stages").mkdir(parents=True)
    (folder / "workflow.rkt").write_text(example, encoding="utf-8")
    (folder / "stages" / "01-setup.rkt").write_text(
        '#lang sciencelogo\nstage Setup about "Set up the pendulum."\n', encoding="utf-8"
    )
    assert call("check", entry="guide/workflow.rkt")["status"] == "valid"


def test_language_reference(call):
    listing = call("language_reference")
    assert "stages" in listing["topics"] and "changelog" in listing["topics"]
    assert "phase" in call("language_reference", topic="grammar-ebnf")["text"]
