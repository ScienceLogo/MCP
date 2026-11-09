"""The ScienceLogo MCP server, over stdio."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server import MCPServer

from sciencelogo_mcp import __version__
from sciencelogo_mcp.helper import RacketHelper


def create_server(helper: RacketHelper | None = None) -> MCPServer:
    helper = helper or RacketHelper()
    server = MCPServer(name="sciencelogo", version=__version__)

    @server.tool()
    def check(entry: str) -> dict[str, Any]:
        """Check a ScienceLogo workflow with the reference reader, without running it.

        `entry` is the workflow's main file; the files it includes are read too.
        Returns status "valid", or status "invalid" with the reader's message and
        the file, line and column of the error.
        """
        return helper.request("check", entry=str(Path(entry).resolve()))

    return server


def main() -> None:
    create_server().run("stdio")
