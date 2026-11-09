"""Readability advice. It never blocks a write.

It helps keep a workflow readable from the broad description down to the
details: every level opens with a summary, files and stages stay short, and
details move into procedures, included files and libraries.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sciencelogo_mcp.workspace import Workspace

LONG_FILE_LINES = 150
LONG_STAGE_LINES = 60


def readability(workspace: Workspace, entry: Path) -> list[str]:
    from sciencelogo_mcp.workspace import read_text, relative

    try:
        structure = workspace.structure(entry)
    except Exception:  # advice is optional; a failure here must not fail a write
        return []
    notes: list[str] = []
    if structure.get("about") in (None, "null"):
        notes.append("The workflow has no about text: add a summary of the whole method.")
    for phase in structure["phases"]:
        if phase["about"] in (None, "null"):
            notes.append(f"Phase {phase['name']} has no about text.")
    for stage in structure["stages"]:
        if stage["in_procedure"]:
            continue
        if stage["about"] in (None, "null"):
            notes.append(f"Stage {stage['name']} has no about text.")
        start, end = stage.get("start"), stage.get("end")
        if isinstance(start, dict) and isinstance(end, dict):
            length = end["line"] - start["line"] + 1
            if length > LONG_STAGE_LINES:
                notes.append(
                    f"Stage {stage['name']} is {length} lines long: move detail into "
                    "procedures or an included file."
                )
    for procedure in structure["procedures"]:
        if procedure["about"] in (None, "null"):
            notes.append(f"Procedure {procedure['name']} has no about text.")
    files: set[str] = {
        item["file"] for item in structure["items"] if item.get("file") not in (None, "null")
    }
    for file in sorted(files):
        path = Path(file)
        lines = read_text(path).count("\n") + 1
        if lines > LONG_FILE_LINES:
            notes.append(
                f"{relative(path, entry.parent)} is {lines} lines long: split it into "
                "included files."
            )
    for item in workspace.items(entry, structure):
        if item.kind == "procedure":
            body = read_text(item.file)[item.start : item.end]
            if "output unknown" in body:
                notes.append(
                    f"Procedure {item.name} outputs unknown: describe its result "
                    "(kind, fields, units) and its uncertainty."
                )
    return notes
