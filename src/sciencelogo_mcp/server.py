"""The ScienceLogo MCP server, over stdio.

Paths are relative to the server's working directory, the user's folder.
Items are named `kind:name`, for example `stage:Measure`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlparse

import anyio
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ResourceError

from sciencelogo_mcp import __version__, syntax
from sciencelogo_mcp.docs import LanguageDocs, agents_guide
from sciencelogo_mcp.helper import RacketHelper
from sciencelogo_mcp.workspace import (
    HEADER,
    KINDS,
    Workspace,
    WriteError,
    read_text,
    relative,
)

INSTRUCTIONS = (
    "Writes and checks ScienceLogo workflows and libraries. Read the resource "
    "sciencelogo://guide before writing; every write is checked by the ScienceLogo "
    "reader and a rejected write changes nothing."
)


def item_ref(ref: str | None) -> tuple[str, str] | None:
    """`kind:name` as (kind, name)."""
    if not ref:
        return None
    kind, sep, name = ref.partition(":")
    if not sep or not name or kind not in KINDS:
        raise WriteError(f"name items as kind:name, with kind one of {', '.join(KINDS)}")
    return kind, name


def create_server(helper: RacketHelper | None = None, root: Path | None = None) -> MCPServer:
    helper = helper or RacketHelper()
    workspace = Workspace(helper, root)
    docs = LanguageDocs(helper)
    server = MCPServer(name="sciencelogo", version=__version__, instructions=INSTRUCTIONS)

    def share_client_folders(ctx: Context) -> None:
        """Work in the folders the client shares with the server, when it shares
        any; otherwise in the folder the server was started in."""
        try:
            capabilities = ctx.client_capabilities
            if capabilities is None or capabilities.roots is None:
                return
            listed = anyio.from_thread.run(ctx.session.list_roots)
        except Exception:
            return
        folders = [
            Path(unquote(urlparse(str(root.uri)).path)).resolve()
            for root in listed.roots
            if str(root.uri).startswith("file://")
        ]
        workspace.roots = folders or list(workspace.default_roots)

    def declare(
        entry: str,
        kind: str,
        name: str,
        text: str,
        file: str | None = None,
        after: str | None = None,
        before: str | None = None,
        also_replaces: list[tuple[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Replace the item of this kind and name, or add it."""
        path = workspace.entry_path(entry)
        existing = workspace.find(path, kind, name)
        if existing is None:
            return workspace.insert(
                path, text, file=file, after=item_ref(after), before=item_ref(before)
            )
        # Replace the item; remove the other items it brings with it, such as a
        # procedure's result interface, so they are not declared twice.
        edits: dict[Path, list[tuple[int, int, str]]] = {
            existing.file: [(existing.start, existing.end, text)]
        }
        for other_kind, other_name in also_replaces or []:
            other = workspace.find(path, other_kind, other_name)
            if other is not None:
                edits.setdefault(other.file, []).append((other.lead, other.end, ""))
        changes: dict[Path, str | None] = {}
        for file_path, spans in edits.items():
            content = read_text(file_path)
            for start, end, new in sorted(spans, reverse=True):
                content = content[:start] + new + content[end:]
            changes[file_path] = content
        return workspace.commit(path, changes)

    # --- reading and checking ----------------------------------------------------

    @server.tool()
    def check(entry: str, *, ctx: Context) -> dict[str, Any]:
        """Check a workflow or library with the ScienceLogo reader, without running it.

        `entry` is the main file; the files it includes are read too. Returns
        status "valid" with the structural assessment and readability advice,
        or status "invalid" with the reader's message, file, line and column.
        """
        share_client_folders(ctx)
        path = workspace.entry_path(entry)
        result = workspace.check(path)
        if result["status"] == "valid" and workspace.kind_of(path) == "workflow":
            from sciencelogo_mcp import advice

            result["advice"] = advice.readability(workspace, path)
        return result

    @server.tool()
    def outline(entry: str, *, ctx: Context) -> dict[str, Any]:
        """The structure of a valid workflow or library: its title and summary,
        every item with its kind, name and file, and its stages, phases,
        procedures, performers and imports."""
        share_client_folders(ctx)
        path = workspace.entry_path(entry)
        status = workspace.check(path)
        if status["status"] != "valid":
            return status
        structure = workspace.structure(path)
        items = workspace.items(path, structure)
        root = path.parent

        def where(entry_ref: Any) -> Any:
            if isinstance(entry_ref, dict):
                return {"file": relative(Path(entry_ref["file"]), root), "line": entry_ref["line"]}
            return None

        return {
            "kind": workspace.kind_of(path),
            "title": structure["title"],
            "about": structure["about"],
            "items": [item.describe(root) for item in items],
            "stages": [
                {
                    "name": s["name"],
                    "about": s["about"],
                    "performer": s["performer"],
                    "in_procedure": s["in_procedure"],
                    "at": where(s["start"]),
                }
                for s in structure["stages"]
            ],
            "phases": [
                {"name": p["name"], "about": p["about"], "members": p["members"]}
                for p in structure["phases"]
            ],
            "procedures": [
                {"name": p["name"], "inputs": p["inputs"], "about": p["about"]}
                for p in structure["procedures"]
            ],
            "performers": structure["performers"],
            "imports": structure["imports"],
        }

    @server.tool()
    def read_workflow(
        entry: str,
        syntax_form: Literal["verbose", "compact"] = "verbose",
        item: str | None = None,
        *,
        ctx: Context,
    ) -> dict[str, Any]:
        """The text of a workflow or library, in verbose (default) or compact syntax.

        With `item` (`kind:name`), only that item. A workflow the current reader
        rejects is returned as stored, with the reader's error, so it can be
        rewritten in the current release.
        """
        share_client_folders(ctx)
        path = workspace.entry_path(entry)
        root = path.parent
        status = workspace.check(path)
        if status["status"] != "valid":
            files = {relative(path, root): read_text(path)}
            for match in re.finditer(r'include\s+"([^"]+)"', read_text(path)):
                included = (root / match.group(1)).resolve()
                if included.is_file():
                    files[relative(included, root)] = read_text(included)
            return {"status": "invalid", "error": status, "files": files}
        if item:
            kind, name = item_ref(item)
            found = workspace.find(path, kind, name)
            if found is None:
                raise WriteError(f"no {kind} named {name}")
            if syntax_form == "compact":
                text = read_text(found.file)[found.start : found.end]
            else:
                text = helper.request(
                    "translate",
                    file=str(found.file),
                    to="verbose",
                    start=found.start_position,
                    end=found.end_position,
                )["text"]
            return {"item": item, "file": relative(found.file, root), "text": text}
        files = [path] + [
            Path(i.name)
            for i in workspace.items(path)
            if i.kind == "include" and i.name and Path(i.name).is_file()
        ]
        return {
            "status": "valid",
            "files": {
                relative(f, root): helper.request("translate", file=str(f), to=syntax_form)["text"]
                for f in files
            },
        }

    @server.tool()
    def language_reference(topic: str | None = None, *, ctx: Context) -> dict[str, Any]:
        """The ScienceLogo documentation of the installed release.

        With no topic, the list of topics and examples. A topic is a manual
        page (such as "stages" or "procedures"), "grammar-ebnf", "changelog",
        or "example:<name>" for an example file.
        """
        share_client_folders(ctx)
        if not topic:
            return {
                "language_version": docs.version,
                "topics": docs.topics(),
                "examples": [f"example:{name}" for name in docs.examples()],
            }
        try:
            if topic.startswith("example:"):
                return {"topic": topic, "text": docs.example(topic.removeprefix("example:"))}
            return {"topic": topic, "text": docs.topic(topic)}
        except KeyError:
            raise WriteError(f"no topic {topic}; call language_reference with no topic") from None

    # --- free writing ------------------------------------------------------------

    @server.tool()
    def create_workflow(
        file: str, title: str, about: str | None = None, *, ctx: Context
    ) -> dict[str, Any]:
        """Start a new workflow in a new main file, with its title and summary."""
        share_client_folders(ctx)
        path = workspace.resolve(file)
        if path.exists():
            raise WriteError(f"{file} already exists")
        if path.suffix != ".rkt":
            raise WriteError("ScienceLogo files end in .rkt")
        content = f"{HEADER}\n{syntax.workflow_header(title, about)}\n"
        return workspace.commit(path, {path: content})

    @server.tool()
    def create_library(
        file: str, name: str, language: str | None = None, *, ctx: Context
    ) -> dict[str, Any]:
        """Start a library project in a new main file (usually library.rkt).

        A library holds procedures, record interfaces, includes and imports.
        `language` is the language version it is written for (default: the
        installed release).
        """
        share_client_folders(ctx)
        return workspace.create_library(file, name, language or docs.version)

    @server.tool()
    def write_fragment(
        entry: str,
        text: str,
        file: str | None = None,
        after: str | None = None,
        before: str | None = None,
        replaces: str | None = None,
        include_after: str | None = None,
        *,
        ctx: Context,
    ) -> dict[str, Any]:
        """Write any ScienceLogo text, checked by the reader before it is saved.

        By default the text goes at the end of `file` (relative to the main file;
        default the main file itself). `after`, `before` or `replaces` place it
        next to or in place of an item (`kind:name`). A new `file` gets its
        header and an `include` line in the main file, after `include_after` or
        after the last include.
        """
        share_client_folders(ctx)
        return workspace.insert(
            workspace.entry_path(entry),
            text,
            file=file,
            after=item_ref(after),
            before=item_ref(before),
            replaces=item_ref(replaces),
            include_after=item_ref(include_after),
        )

    @server.tool()
    def remove_item(entry: str, item: str, *, ctx: Context) -> dict[str, Any]:
        """Remove an item (`kind:name`) with the comments just before it."""
        share_client_folders(ctx)
        kind, name = item_ref(item)
        return workspace.remove(workspace.entry_path(entry), kind, name)

    @server.tool()
    def move_item(entry: str, item: str, to_file: str, *, ctx: Context) -> dict[str, Any]:
        """Move an item (`kind:name`) with its comments to another file.

        A new file is created and included where the item was, so the method
        keeps its order.
        """
        share_client_folders(ctx)
        kind, name = item_ref(item)
        return workspace.move(workspace.entry_path(entry), kind, name, to_file)

    # --- one tool per construct --------------------------------------------------

    @server.tool()
    def set_workflow(
        entry: str, title: str | None = None, about: str | None = None, *, ctx: Context
    ) -> dict[str, Any]:
        """Set the workflow's title and its summary (about); either can be left as it is."""
        share_client_folders(ctx)
        return workspace.set_header(workspace.entry_path(entry), title, about)

    @server.tool()
    def declare_performer(
        entry: str, name: str, fields: dict[str, Any], file: str | None = None, *, ctx: Context
    ) -> dict[str, Any]:
        """Declare who or what carries out work, for example
        fields {"kind": "human", "role": "scientist"}. Values are JSON; null is
        unknown; {"expr": "..."} is a ScienceLogo expression."""
        share_client_folders(ctx)
        return declare(entry, "performer", name, syntax.performer(name, fields), file)

    @server.tool()
    def declare_resource(
        entry: str, name: str, fields: dict[str, Any], file: str | None = None, *, ctx: Context
    ) -> dict[str, Any]:
        """Declare a resource the method uses, such as an instrument or a data
        source, with its fields (values as in declare_performer)."""
        share_client_folders(ctx)
        return declare(entry, "resource", name, syntax.resource(name, fields), file)

    @server.tool()
    def declare_proposition(
        entry: str,
        type: Literal["hypothesis", "assumption", "conclusion"],
        name: str,
        statement: str,
        children: str | None = None,
        file: str | None = None,
        *,
        ctx: Context,
    ) -> dict[str, Any]:
        """Declare a hypothesis, assumption or conclusion. `children` is optional
        ScienceLogo text for nested propositions, such as
        `hypotheses = [h1 = [text = "..."]]`."""
        share_client_folders(ctx)
        text = syntax.proposition(type, name, statement, children)
        return declare(entry, "proposition", name, text, file)

    @server.tool()
    def declare_interface(
        entry: str,
        name: str,
        fields: list[dict[str, Any]],
        extends: list[str] | None = None,
        version: str | None = None,
        body: str | None = None,
        file: str | None = None,
        *,
        ctx: Context,
    ) -> dict[str, Any]:
        """Declare a record interface: the fields a record must or may have.

        Each field has a `name` and optionally `type` (number, text, boolean,
        list, record or an interface), `default`, `unit` and `required`
        (default true). `body` is optional ScienceLogo text for conditions and
        other interface entries.
        """
        share_client_folders(ctx)
        text = syntax.interface(name, fields, extends, version, body)
        return declare(entry, "interface", name, text, file)

    @server.tool()
    def declare_procedure(
        entry: str,
        name: str,
        inputs: list[str],
        about: str,
        result: list[dict[str, Any]] | None = None,
        uncertainty: list[dict[str, Any]] | None = None,
        body: str | None = None,
        file: str | None = None,
        *,
        ctx: Context,
    ) -> dict[str, Any]:
        """Declare a procedure. For a step done outside ScienceLogo, describe it as
        a method, never by file paths or code: `about` says what it does,
        `inputs` what goes in, `result` the fields of what comes out (each with
        name, type and unit), and `uncertainty` where the result's uncertainty
        comes from (each with name and description, or omitted: true). The
        server writes the result's record interface and an output of that
        record. `body` is ScienceLogo commands, when the work is written in
        ScienceLogo itself.
        """
        share_client_folders(ctx)
        text = syntax.procedure(name, inputs, about, body, result, uncertainty)
        interface_name = syntax.result_interface_name(name)
        return declare(
            entry,
            "procedure",
            name,
            text,
            file,
            also_replaces=[("interface", interface_name)] if result else None,
        )

    def stage_placement(
        entry: str, name: str, file: str | None, after: str | None, before: str | None
    ) -> str | None:
        """New stages get their own file under stages/ unless placed otherwise."""
        path = workspace.entry_path(entry)
        if file or after or before or workspace.kind_of(path) == "library":
            return file
        if workspace.find(path, "stage", name) is not None:
            return None
        return workspace.stage_file(path, name)

    @server.tool()
    def add_stage(
        entry: str,
        name: str,
        about: str | None = None,
        commands: str | None = None,
        file: str | None = None,
        after: str | None = None,
        before: str | None = None,
        *,
        ctx: Context,
    ) -> dict[str, Any]:
        """Add or replace a simple stage: a named section of the method with its
        commands (ScienceLogo text). A new stage gets its own file under stages/
        unless `file`, `after` or `before` place it."""
        share_client_folders(ctx)
        text = syntax.stage(name, about, commands)
        target = stage_placement(entry, name, file, after, before)
        return declare(entry, "stage", name, text, target, after, before)

    @server.tool()
    def add_paired_stage(
        entry: str,
        name: str,
        entry_state: dict[str, Any],
        calls: list[dict[str, Any]] | None = None,
        performer: str | None = None,
        about: str | None = None,
        commands: str | None = None,
        exit_state: dict[str, Any] | None = None,
        file: str | None = None,
        after: str | None = None,
        before: str | None = None,
        *,
        ctx: Context,
    ) -> dict[str, Any]:
        """Add or replace a paired stage, which states what is known when it
        starts and ends.

        `entry_state` has information, environment and factors (records as
        JSON). Each call has `procedure`, optional `performer`, `inputs`
        (input name to location, such as "information.elapsed") and `into` (a
        location). The exit state is derived from the entry state plus every
        `into` location unless `exit_state` is given.
        """
        share_client_folders(ctx)
        text = syntax.paired_stage(
            name, performer, entry_state, calls or [], about, commands, exit_state
        )
        target = stage_placement(entry, name, file, after, before)
        return declare(entry, "stage", name, text, target, after, before)

    @server.tool()
    def add_phase(
        entry: str,
        name: str,
        members: list[str],
        about: str | None = None,
        file: str | None = None,
        *,
        ctx: Context,
    ) -> dict[str, Any]:
        """Add or replace a phase: a named group of workflow-level stages or other
        phases, in method order, with its own summary."""
        share_client_folders(ctx)
        return declare(entry, "phase", name, syntax.phase(name, about, members), file)

    @server.tool()
    def add_requirement(
        entry: str,
        kind: Literal["call", "stage_order"],
        targets: list[str],
        file: str | None = None,
        *,
        ctx: Context,
    ) -> dict[str, Any]:
        """Require that the method calls a procedure (`call`, one target) or runs
        stages in order (`stage_order`, two or more stages)."""
        share_client_folders(ctx)
        text = syntax.requirement(kind, targets)
        return declare(entry, "requirement", " ".join(targets), text, file)

    @server.tool()
    def add_mapping(
        entry: str,
        target: str,
        implements: str,
        file: str | None = None,
        after: str | None = None,
        *,
        ctx: Context,
    ) -> dict[str, Any]:
        """State that a record (`target`) implements a record interface."""
        share_client_folders(ctx)
        return workspace.insert(
            workspace.entry_path(entry),
            syntax.mapping(target, implements),
            file=file,
            after=item_ref(after),
        )

    @server.tool()
    def import_library(
        entry: str, url: str, version: str, alias: str, *, ctx: Context
    ) -> dict[str, Any]:
        """Import a library pinned to a Git tag or commit, under an alias. The
        reader fetches it with Git when it checks the workflow. `describe_library`
        shows what a library provides."""
        share_client_folders(ctx)
        path = workspace.entry_path(entry)
        line = syntax.import_line(url, version, alias)
        existing = workspace.find(path, "import", alias)
        if existing is not None:
            return declare(entry, "import", alias, line)
        content = read_text(path)
        if workspace.kind_of(path) == "library":
            return workspace.commit(path, {path: workspace.appended(path, path, content, line)})
        return workspace.commit(path, {path: workspace.add_after_preamble(content, line)})

    @server.tool()
    def describe_library(url: str, version: str, *, ctx: Context) -> dict[str, Any]:
        """What a library provides, before importing it: its name, the language
        version it is written for, and its procedures (inputs and summary) and
        record interfaces (fields). The reader fetches it with Git, pinned to
        `version` (a tag or commit)."""
        share_client_folders(ctx)
        return helper.request("library", url=url, version=version)

    @server.tool()
    def convert_syntax(
        entry: str, to: Literal["verbose", "compact"], file: str | None = None, *, ctx: Context
    ) -> dict[str, Any]:
        """Rewrite the files of a workflow or library in verbose or compact
        syntax with the reference translator, keeping comments. With `file`,
        only that file."""
        share_client_folders(ctx)
        return workspace.convert(workspace.entry_path(entry), to, file)

    @server.tool()
    def add_include(
        entry: str, path: str, after: str | None = None, *, ctx: Context
    ) -> dict[str, Any]:
        """Include an existing file (relative to the main file), after the item
        `after` or after the last include."""
        share_client_folders(ctx)
        main = workspace.entry_path(entry)
        target = workspace.target_path(main, path)
        if not target.is_file():
            raise WriteError(f"{path} does not exist")
        rel = relative(target, main.parent)
        return workspace.commit(main, {main: workspace.with_include(main, rel, item_ref(after))})

    # --- resources -----------------------------------------------------------------

    @server.resource("sciencelogo://guide", name="guide", mime_type="text/markdown")
    def guide() -> str:
        """How to write ScienceLogo with this server. Read it first."""
        return agents_guide()

    @server.resource("sciencelogo://docs/{topic}", name="docs", mime_type="text/plain")
    def manual(topic: str) -> str:
        """A page of the ScienceLogo manual of the installed release."""
        try:
            return docs.topic(topic)
        except KeyError:
            raise ResourceError(f"no manual page {topic}") from None

    return server


def main() -> None:
    create_server().run("stdio")
