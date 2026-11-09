"""The language documentation and examples of the installed release."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from sciencelogo_mcp.helper import RacketHelper


class LanguageDocs:
    def __init__(self, helper: RacketHelper) -> None:
        self._helper = helper
        self._dir: Path | None = None
        self._version: str | None = None

    def _package(self) -> Path:
        if self._dir is None:
            package = self._helper.request("package")
            self._dir = Path(package["dir"]).parent
            self._version = package["version"]
        return self._dir

    @property
    def version(self) -> str:
        self._package()
        return self._version or ""

    def topics(self) -> list[str]:
        manual = sorted(p.stem for p in (self._package() / "scribblings").glob("*.scrbl"))
        return [*manual, "grammar-ebnf", "changelog"]

    def topic(self, name: str) -> str:
        root = self._package()
        if name == "grammar-ebnf":
            return (root / "spec" / "compact.ebnf").read_text(encoding="utf-8")
        if name == "changelog":
            return (root / "CHANGELOG.md").read_text(encoding="utf-8")
        path = root / "scribblings" / f"{name}.scrbl"
        if name not in self.topics() or not path.is_file():
            raise KeyError(name)
        return path.read_text(encoding="utf-8")

    def examples(self) -> list[str]:
        root = self._package() / "examples"
        return sorted(p.relative_to(root).as_posix() for p in root.rglob("*.rkt"))

    def example(self, name: str) -> str:
        if name not in self.examples():
            raise KeyError(name)
        return (self._package() / "examples" / name).read_text(encoding="utf-8")


def agents_guide() -> str:
    return files("sciencelogo_mcp").joinpath("guide.md").read_text(encoding="utf-8")
