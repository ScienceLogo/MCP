"""Workflow and library files: their items, and checked writes.

Every write follows the same steps: the changed files are written, the
reference reader checks the workflow or library from its main file, and if
the reader rejects it every file is put back exactly as it was.
"""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from sciencelogo_mcp import advice
from sciencelogo_mcp.helper import RacketHelper

HEADER = "#lang sciencelogo"

# Kinds as the tools name them, and the reader's kinds for each.
KINDS: dict[str, tuple[str, ...]] = {
    "stage": ("stage", "state-stage"),
    "procedure": ("to",),
    "performer": ("performer",),
    "resource": ("resource",),
    "interface": ("interface",),
    "proposition": ("proposition",),
    "phase": ("phase",),
    "requirement": ("must-call", "must-stage-order"),
    "import": ("import",),
    "include": ("included-file",),
}
READER_KINDS = {reader: kind for kind, readers in KINDS.items() for reader in readers}

# Forms that belong to the simple stage before them.
COMMAND_KINDS = {
    "assignment",
    "path-assignment",
    "path-update-command",
    "call",
    "state-call",
    "sequence",
    "repeat",
    "repeat-until",
    "for-each",
    "while",
    "if",
    "print",
    "output",
    "implement",
}


TEXT_LITERAL = r'"(?:[^"\\]|\\.)*"'
IMPORT_LINE = re.compile(rf"import\s+{TEXT_LITERAL}\s+at\s+{TEXT_LITERAL}\s+as\s+\S+")


class WriteError(ToolError):
    pass


@dataclass
class Item:
    kind: str
    name: str | None
    file: Path
    start: int
    end: int
    lead: int
    reader_kind: str
    start_position: int
    end_position: int

    def describe(self, root: Path) -> dict[str, Any]:
        name = self.name
        if self.kind == "include" and name:
            name = relative(Path(name), root)
        return {"kind": self.kind, "name": name, "file": relative(self.file, root)}


def relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def read_text(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)


def offset(content: str, position: int) -> int:
    """The string index of a reader position.

    Reader positions start at 1 and count a CR LF pair as one character.
    """
    index = position - 1
    for match in re.finditer("\r\n", content):
        if match.start() < index:
            index += 1
        else:
            break
    return index


def skip_space_and_comments(content: str, index: int) -> int:
    while index < len(content):
        if content[index].isspace():
            index += 1
        elif content[index] == ";":
            newline = content.find("\n", index)
            index = len(content) if newline < 0 else newline + 1
        elif content.startswith("#|", index):
            close = content.find("|#", index)
            index = len(content) if close < 0 else close + 2
        else:
            break
    return index


def string_end(content: str, index: int) -> int:
    """The index just after the text literal that starts at `index`."""
    if index >= len(content) or content[index] != '"':
        raise WriteError("expected a text literal")
    i = index + 1
    while i < len(content):
        if content[i] == "\\":
            i += 2
        elif content[i] == '"':
            return i + 1
        else:
            i += 1
    raise WriteError("unterminated text literal")


def header_end(content: str) -> int:
    first_line = content.split("\n", 1)[0].strip()
    if first_line != HEADER:
        raise WriteError(f"the first line must be exactly {HEADER}")
    newline = content.find("\n")
    return len(content) if newline < 0 else newline + 1


def preamble_end(content: str) -> int:
    """Where a file's items begin: after the header and the workflow title, or
    inside the opening bracket of a library."""
    index = header_end(content)
    start = skip_space_and_comments(content, index)
    title = keyword_text(content, start, "workflow")
    if title:
        return title[1]
    library = re.match(
        r'library\s+[^\s\[\]]+(?:\s+language\s+"(?:[^"\\]|\\.)*")?\s*\[', content[start:]
    )
    if library:
        return start + library.end()
    return index


def keyword_text(content: str, index: int, keyword: str) -> tuple[int, int] | None:
    """The span of `keyword "text"` at index, if it is there."""
    if not re.match(rf"{keyword}\s", content[index:]):
        return None
    literal = skip_space_and_comments(content, index + len(keyword))
    return index, string_end(content, literal)


def file_kind(content: str) -> str:
    """ "library" for a library's main file, otherwise "workflow"."""
    try:
        start = skip_space_and_comments(content, header_end(content))
    except WriteError:
        return "workflow"
    return "library" if re.match(r"library\s", content[start:]) else "workflow"


class Workspace:
    """Reading and checked writing of one workflow or library."""

    def __init__(self, helper: RacketHelper, root: Path | None = None) -> None:
        self.helper = helper
        self.root = (root or Path.cwd()).resolve()
        self._lock = threading.Lock()

    # --- paths -----------------------------------------------------------------

    def entry_path(self, entry: str) -> Path:
        path = (self.root / entry).resolve()
        if not path.is_file():
            raise WriteError(f"{entry} does not exist")
        return path

    def target_path(self, entry: Path, file: str | None) -> Path:
        """A file to write: by default the main file; otherwise relative to it,
        inside the main file's folder."""
        if not file:
            return entry
        path = (entry.parent / file).resolve()
        if not path.is_relative_to(entry.parent):
            raise WriteError(f"{file} is outside the folder of {entry.name}")
        if path.suffix != ".rkt":
            raise WriteError("ScienceLogo files end in .rkt")
        return path

    def kind_of(self, entry: Path) -> str:
        return file_kind(read_text(entry))

    # --- reading ---------------------------------------------------------------

    def check(self, entry: Path) -> dict[str, Any]:
        result = self.helper.request("check", entry=str(entry), kind=self.kind_of(entry))
        if result.get("file") not in (None, ""):
            result["file"] = relative(Path(result["file"]), entry.parent)
        if "message" in result:
            result["message"] = result["message"].replace(f"{entry.parent}{os.sep}", "")
        return result

    def structure(self, entry: Path) -> dict[str, Any]:
        return self.helper.request("structure", entry=str(entry), kind=self.kind_of(entry))

    def items(self, entry: Path, structure: dict[str, Any] | None = None) -> list[Item]:
        """Every named item of a valid workflow or library, with the span of its
        text. Comments and blank lines before an item belong to it."""
        structure = structure or self.structure(entry)
        stage_ends = {
            s["name"]: s["end"] for s in structure["stages"] if s.get("end") not in (None, "null")
        }
        texts: dict[Path, str] = {}
        result: list[Item] = []
        previous_end: dict[Path, int] = {}
        covered_until: dict[Path, int] = {}
        for raw in structure["items"]:
            if raw["file"] in (None, "null") or raw["start"] in (None, "null"):
                continue
            file = Path(raw["file"])
            if file not in texts:
                texts[file] = read_text(file)
                previous_end[file] = preamble_end(texts[file])
            content = texts[file]
            start = offset(content, raw["start"]["position"])
            if start < covered_until.get(file, -1):
                continue  # a command inside a simple stage's section
            reader_kind = raw["kind"]
            end_point = raw["end"]
            if reader_kind == "stage" and raw["name"] in stage_ends:
                end_point = stage_ends[raw["name"]]
            if end_point in (None, "null"):
                if reader_kind == "about":
                    end = string_end(content, skip_space_and_comments(content, start + 5))
                else:
                    continue
            else:
                end = offset(content, end_point["position"])
            lead = previous_end[file]
            previous_end[file] = end
            covered_until[file] = end
            if reader_kind == "about" or reader_kind in COMMAND_KINDS:
                continue
            kind = READER_KINDS.get(reader_kind, reader_kind)
            name = raw["name"] if raw["name"] not in (None, "null") else None
            result.append(
                Item(
                    kind=kind,
                    name=name,
                    file=file,
                    start=start,
                    end=end,
                    lead=lead,
                    reader_kind=reader_kind,
                    start_position=raw["start"]["position"],
                    end_position=end_point["position"] if end_point not in (None, "null") else 0,
                )
            )
        return result

    def find(self, entry: Path, kind: str, name: str) -> Item | None:
        if kind not in KINDS:
            raise WriteError(f"unknown kind {kind}; the kinds are {', '.join(KINDS)}")
        for item in self.items(entry):
            if item.kind != kind:
                continue
            if item.name == name:
                return item
            if kind == "include" and item.name and Path(item.name) == self.target_path(entry, name):
                return item
        return None

    # --- writing ---------------------------------------------------------------

    def commit(self, entry: Path, changes: dict[Path, str | None]) -> dict[str, Any]:
        """Write the changed files, check the workflow, and keep the change only
        if the reader accepts it. None deletes a file."""
        with self._lock:
            before = {path: read_text(path) if path.exists() else None for path in changes}
            try:
                for path, content in changes.items():
                    if content is None:
                        if path.exists():
                            path.unlink()
                    else:
                        write_text(path, content)
                result = self.check(entry)
            except BaseException:
                self._restore(before)
                raise
            if result["status"] != "valid":
                failing = result.get("file")
                if failing and result.get("line") not in (None, "null"):
                    path = (entry.parent / failing).resolve()
                    if path.exists():
                        lines = read_text(path).splitlines()
                        line = result["line"]
                        if 0 < line <= len(lines):
                            result["line_text"] = lines[line - 1]
                self._restore(before)
                return {"saved": False, **result}
        changed = sorted(relative(path, entry.parent) for path in changes)
        report = {"saved": True, "files": changed, **result}
        if self.kind_of(entry) == "workflow":
            report["advice"] = advice.readability(self, entry)
        return report

    @staticmethod
    def _restore(before: dict[Path, str | None]) -> None:
        for path, content in before.items():
            if content is None:
                if path.exists():
                    path.unlink()
            else:
                write_text(path, content)

    def insert(
        self,
        entry: Path,
        fragment: str,
        file: str | None = None,
        after: tuple[str, str] | None = None,
        before: tuple[str, str] | None = None,
        replaces: tuple[str, str] | None = None,
        include_after: tuple[str, str] | None = None,
    ) -> dict[str, Any]:
        """Write a fragment of ScienceLogo text.

        It goes in place of an item (`replaces`), after or before an item, or
        at the end of `file` (by default the main file). A new file gets the
        header and its `include` line in the main file, placed after
        `include_after` or after the last include.
        """
        fragment = fragment.strip("\n")
        if fragment.lstrip().startswith(HEADER):
            fragment = fragment.lstrip()[len(HEADER) :].lstrip("\n")
        anchors = [a for a in (after, before, replaces) if a]
        if len(anchors) > 1:
            raise WriteError("give at most one of after, before and replaces")
        changes: dict[Path, str | None] = {}
        if anchors:
            kind, name = anchors[0]
            item = self.find(entry, kind, name)
            if item is None:
                raise WriteError(f"no {kind} named {name}")
            content = read_text(item.file)
            if replaces:
                content = content[: item.start] + fragment + content[item.end :]
            elif after:
                content = content[: item.end] + "\n" + fragment + content[item.end :]
            else:
                content = content[: item.lead] + "\n" + fragment + content[item.lead :]
            changes[item.file] = content
            return self.commit(entry, changes)

        target = self.target_path(entry, file)
        if target.exists():
            changes[target] = self.appended(entry, target, read_text(target), fragment)
        else:
            changes[target] = f"{HEADER}\n{fragment}\n"
            path = relative(target, entry.parent)
            changes[entry] = self.with_include(entry, path, include_after)
        return self.commit(entry, changes)

    def appended(self, entry: Path, target: Path, content: str, fragment: str) -> str:
        """`content` with the fragment at its end; in a library's main file, at
        the end of the library's bracket."""
        if target == entry and file_kind(content) == "library":
            close = content.rstrip().rfind("]")
            if close < 0:
                raise WriteError("the library has no closing bracket")
            head = content[:close].rstrip("\n")
            return f"{head}\n  {fragment.replace(chr(10), chr(10) + '  ')}\n{content[close:]}"
        if content and not content.endswith("\n"):
            content += "\n"
        return content + fragment + "\n"

    def with_include(self, entry: Path, path: str, include_after: tuple[str, str] | None) -> str:
        content = read_text(entry)
        line = f'include "{path}"'
        if file_kind(content) == "library":
            return self.appended(entry, entry, content, line)
        includes = [i for i in self.items(entry) if i.kind == "include" and i.file == entry]
        if include_after:
            anchor = self.find(entry, *include_after)
            if anchor is None or anchor.file != entry:
                raise WriteError(f"no {include_after[0]} named {include_after[1]} in the main file")
        elif includes:
            anchor = includes[-1]
        else:
            anchor = None
        if anchor is not None:
            return content[: anchor.end] + "\n" + line + content[anchor.end :]
        return self.add_after_preamble(content, line)

    def add_after_preamble(self, content: str, line: str) -> str:
        """`line` after the header, the workflow title, the about text and the imports."""
        index = header_end(content)
        while True:
            start = skip_space_and_comments(content, index)
            span = (
                keyword_text(content, start, "workflow")
                or keyword_text(content, start, "about")
                or self._import_span(content, start)
            )
            if span is None:
                break
            index = span[1]
        if index == header_end(content):
            return content[:index] + line + "\n" + content[index:]
        return content[:index] + "\n" + line + content[index:]

    @staticmethod
    def _import_span(content: str, start: int) -> tuple[int, int] | None:
        match = IMPORT_LINE.match(content[start:])
        return (start, start + match.end()) if match else None

    def set_header(self, entry: Path, title: str | None, about: str | None) -> dict[str, Any]:
        """Set the workflow's title and about text, keeping whichever is not given."""
        content = read_text(entry)
        index = skip_space_and_comments(content, header_end(content))
        spans = {}
        for keyword in ("workflow", "about"):
            span = keyword_text(content, index, keyword)
            if span:
                spans[keyword] = span
                index = skip_space_and_comments(content, span[1])
        from sciencelogo_mcp import syntax

        lines = []
        for keyword, new in (("workflow", title), ("about", about)):
            if new is not None:
                lines.append(f"{keyword} {syntax.text(new)}")
            elif keyword in spans:
                lines.append(content[spans[keyword][0] : spans[keyword][1]])
        start = min((s[0] for s in spans.values()), default=header_end(content))
        end = max((s[1] for s in spans.values()), default=header_end(content))
        block = "\n".join(lines)
        if not spans:
            block += "\n"
        return self.commit(entry, {entry: content[:start] + block + content[end:]})

    def remove(self, entry: Path, kind: str, name: str) -> dict[str, Any]:
        item = self.find(entry, kind, name)
        if item is None:
            raise WriteError(f"no {kind} named {name}")
        content = read_text(item.file)
        changes: dict[Path, str | None] = {item.file: content[: item.lead] + content[item.end :]}
        return self.commit(entry, changes)

    def move(self, entry: Path, kind: str, name: str, to_file: str) -> dict[str, Any]:
        """Move an item, with its comments, to another file of the workflow."""
        item = self.find(entry, kind, name)
        if item is None:
            raise WriteError(f"no {kind} named {name}")
        target = self.target_path(entry, to_file)
        if target == item.file:
            raise WriteError(f"the {kind} {name} is already in {to_file}")
        source = read_text(item.file)
        text = source[item.lead : item.end].strip("\n")
        changes: dict[Path, str | None] = {item.file: source[: item.lead] + source[item.end :]}
        if target.exists():
            base = changes.get(target) or read_text(target)
            changes[target] = self.appended(entry, target, base, text)
        else:
            changes[target] = f"{HEADER}\n{text}\n"
            path = relative(target, entry.parent)
            # The include goes where the item was when it moves out of the main file,
            # so the method keeps its order.
            if item.file == entry:
                line = f'include "{path}"'
                changes[entry] = source[: item.lead] + "\n" + line + source[item.end :]
            else:
                changes[entry] = self.with_include(entry, path, None)
        return self.commit(entry, changes)

    def create_library(self, file: str, name: str, language: str) -> dict[str, Any]:
        from sciencelogo_mcp import syntax

        path = (self.root / file).resolve()
        if path.exists():
            raise WriteError(f"{file} already exists")
        if not path.is_relative_to(self.root):
            raise WriteError(f"{file} is outside {self.root}")
        return self.commit(path, {path: syntax.library_file(name, language)})

    def stage_file(self, entry: Path, name: str) -> str:
        """The default file for a new stage: stages/NN-name.rkt."""
        stages = entry.parent / "stages"
        count = len(list(stages.glob("[0-9][0-9]-*.rkt"))) if stages.is_dir() else 0
        slug = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower() or "stage"
        return os.path.join("stages", f"{count + 1:02d}-{slug}.rkt")
