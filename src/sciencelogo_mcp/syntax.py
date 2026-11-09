"""ScienceLogo compact text for the constructs the tools write.

The reference reader checks every piece of text written here before it is
saved, so these functions only need to build well-formed text; they do not
judge whether the method is valid.
"""

from __future__ import annotations

import copy
from decimal import Decimal
from typing import Any

STATE_SETS = ("information", "environment", "factors")
PROPOSITION_TYPES = ("hypothesis", "assumption", "conclusion")


def text(value: str) -> str:
    """A ScienceLogo text literal."""
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def number(value: int | float) -> str:
    if isinstance(value, int):
        return str(value)
    formatted = format(Decimal(repr(value)), "f")
    return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted


def value(v: Any) -> str:
    """A ScienceLogo expression for a JSON value.

    None is `unknown`; a dictionary is a record and a list is a list. A
    dictionary of the form {"expr": "..."} is copied as ScienceLogo source,
    for references, operations and other expressions.
    """
    if v is None:
        return "unknown"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int | float):
        return number(v)
    if isinstance(v, str):
        return text(v)
    if isinstance(v, dict):
        if set(v) == {"expr"}:
            return str(v["expr"])
        return record(v)
    if isinstance(v, list):
        return "[" + " ".join(value(item) for item in v) + "]"
    raise ValueError(f"cannot write {v!r} as a ScienceLogo value")


def record(fields: dict[str, Any]) -> str:
    return "[" + " ".join(f"{name} = {value(v)}" for name, v in fields.items()) + "]"


def indent(body: str, spaces: int = 2) -> str:
    pad = " " * spaces
    return "\n".join(pad + line if line.strip() else line for line in body.strip("\n").splitlines())


def about_clause(about: str | None) -> str:
    return f" about {text(about)}" if about else ""


# --- declarations --------------------------------------------------------------


def workflow_header(title: str | None, about: str | None) -> str:
    lines = []
    if title:
        lines.append(f"workflow {text(title)}")
    if about:
        lines.append(f"about {text(about)}")
    return "\n".join(lines)


def performer(name: str, fields: dict[str, Any]) -> str:
    return f"performer {name} {record(fields)}"


def resource(name: str, fields: dict[str, Any]) -> str:
    return f"resource {name} {record(fields)}"


def proposition(kind: str, name: str, statement: str | None, children: str | None) -> str:
    if kind not in PROPOSITION_TYPES:
        raise ValueError(f"a proposition is one of {', '.join(PROPOSITION_TYPES)}")
    parts = []
    if statement is not None:
        parts.append(f"text = {text(statement)}")
    if children:
        parts.append(children.strip())
    return f"{kind} {name} [" + " ".join(parts) + "]"


def field_declaration(field: dict[str, Any]) -> str:
    """One interface field.

    `name` is required. `type` is number, text, boolean, list, record or an
    interface name; `default` is a value; `unit` makes the field a nested
    record with `value` and `unit`.
    """
    name = field["name"]
    kind = field.get("type")
    if field.get("unit") is not None:
        inner = "value = " + value(field.get("default"))
        if kind:
            inner += f" {kind}"
        return f"{name} [{inner} unit = {text(field['unit'])}]"
    if "default" in field:
        return f"{name} = {value(field['default'])}" + (f" {kind}" if kind else "")
    if kind:
        return f"{name} is {kind}"
    return name


def interface(
    name: str,
    fields: list[dict[str, Any]],
    extends: list[str] | None = None,
    version: str | None = None,
    body: str | None = None,
) -> str:
    entries: list[str] = []
    if version:
        entries.append(f"version {text(version)}")
    entries.extend(f"extends {parent}" for parent in extends or [])
    required = [field_declaration(f) for f in fields if f.get("required", True)]
    optional = [field_declaration(f) for f in fields if not f.get("required", True)]
    if required:
        entries.append("must [" + " ".join(required) + "]")
    entries.extend(optional)
    if body:
        entries.append(body.strip())
    return f"interface {name} [" + " ".join(entries) + "]"


def uncertainty(sources: list[dict[str, Any]]) -> str:
    """A `u [...]` suffix from sources with a name, a description and
    optionally omitted = true."""
    groups: dict[str, list[str]] = {"declared": [], "omitted": []}
    for source in sources:
        group = "omitted" if source.get("omitted") else "declared"
        groups[group].append(f"{source['name']} = [text = {text(source.get('description', ''))}]")
    parts = [f"{group} = [" + " ".join(items) + "]" for group, items in groups.items() if items]
    return "u [" + " ".join(parts) + "]"


def result_interface_name(procedure_name: str) -> str:
    return f"{procedure_name}-result"


def procedure(
    name: str,
    inputs: list[str],
    about: str | None,
    body: str | None,
    result: list[dict[str, Any]] | None = None,
    uncertainty_sources: list[dict[str, Any]] | None = None,
) -> str:
    """A `to` definition, preceded by its result interface when `result` is given.

    Without a body, the procedure outputs an empty record of its result
    interface, or `unknown` when no result is described: the work happens
    outside ScienceLogo and the method only states what it produces.
    """
    head = f"to {name}" + "".join(f" :{i.lstrip(':')}" for i in inputs) + about_clause(about)
    pieces = []
    if result:
        pieces.append(interface(result_interface_name(name), result))
    if body is None:
        output = f"{result_interface_name(name)}.[]" if result else "unknown"
        if uncertainty_sources:
            output += " " + uncertainty(uncertainty_sources)
        body = f"output {output}"
    pieces.append(f"{head} [\n{indent(body)}\n]")
    return "\n".join(pieces)


def stage(name: str, about: str | None, commands: str | None) -> str:
    lines = [f"stage {name}" + about_clause(about)]
    if commands:
        lines.append(commands.strip("\n"))
    return "\n".join(lines)


def state(sets: dict[str, Any]) -> str:
    unknown = set(sets) - set(STATE_SETS)
    if unknown:
        raise ValueError(f"a state has only {', '.join(STATE_SETS)}, not {', '.join(unknown)}")
    return "state [" + " ".join(f"{k} = {value(sets[k])}" for k in STATE_SETS if k in sets) + "]"


def state_call(call: dict[str, Any]) -> str:
    line = f"do {call['procedure']}"
    if call.get("performer"):
        line += f" by {call['performer']}"
    inputs = call.get("inputs") or {}
    if inputs:
        line += " with [" + " ".join(f"{k} at {loc}" for k, loc in inputs.items()) + "]"
    return line + f" into {call['into']}"


def exit_state(entry: dict[str, Any], calls: list[dict[str, Any]]) -> dict[str, Any]:
    """The entry state plus every `into` location, set to unknown where absent."""
    result = copy.deepcopy(entry)
    for call in calls:
        segments = call["into"].split(".")
        if any(s.startswith("[") for s in segments):
            continue
        node = result.setdefault(segments[0], {})
        for segment in segments[1:-1]:
            child = node.get(segment)
            if not isinstance(child, dict) or set(child) == {"expr"}:
                child = {}
                node[segment] = child
            node = child
        node.setdefault(segments[-1], None)
    return result


def paired_stage(
    name: str,
    performer_name: str | None,
    entry: dict[str, Any],
    calls: list[dict[str, Any]],
    about: str | None,
    commands: str | None,
    exit: dict[str, Any] | None,
) -> str:
    head = f"stage {name}" + (f" by {performer_name}" if performer_name else "")
    head += f" from {state(entry)}" + about_clause(about)
    body = [state_call(c) for c in calls]
    if commands:
        body.append(commands.strip("\n"))
    tail = f"end stage with {state(exit if exit is not None else exit_state(entry, calls))}"
    return "\n".join([head, *body, tail])


def phase(name: str, about: str | None, members: list[str]) -> str:
    return f"phase {name}" + about_clause(about) + " [" + " ".join(members) + "]"


def requirement(kind: str, targets: list[str]) -> str:
    if kind == "call":
        if len(targets) != 1:
            raise ValueError("a call requirement names one procedure")
        return f"must do {targets[0]}"
    if kind == "stage_order":
        if len(targets) < 2:
            raise ValueError("a stage order names at least two stages")
        return "must stages in order [" + " ".join(targets) + "]"
    raise ValueError('a requirement is "call" or "stage_order"')


def mapping(target: str, implements: str) -> str:
    destination = text(implements) if implements.endswith(".rkt") else implements
    return f"{target} implement {destination}"


def import_line(url: str, version: str, alias: str) -> str:
    return f"import {text(url)} at {text(version)} as {alias}"


def include_line(path: str) -> str:
    return f"include {text(path)}"


def library_file(name: str, language: str) -> str:
    return f"#lang sciencelogo\nlibrary {name} language {text(language)} [\n]\n"
