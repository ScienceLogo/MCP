# ScienceLogo MCP server

An [MCP](https://modelcontextprotocol.io/) server that lets AI agents, and
through them people, write and maintain
[ScienceLogo](https://github.com/ScienceLogo/Language) workflows and
libraries. It works the same way in Claude Code, Codex, Goose and other MCP
clients.

The ScienceLogo reference reader checks every write before it is saved. A
write the reader rejects changes nothing, and the agent gets the reader's
message with the file, line and column.

## What it does

- **Reading and checking:** `check` runs the reader, the structural
  assessment and readability advice; `outline` lists every item;
  `read_workflow` returns a workflow in verbose or compact syntax, whole or
  one item; `language_reference` returns the manual, the grammar, the
  changelog and the examples of the installed release.
- **Writing:** `create_workflow` and `create_library` start a project.
  One tool writes each construct of the language: the workflow title and
  summary, performers, resources, propositions, record interfaces,
  procedures, stages, paired stages, phases, requirements, mappings, library
  imports and includes. `write_fragment` writes any other ScienceLogo text,
  and `remove_item` and `move_item` change the structure.
- **Teaching:** no model knows ScienceLogo, so the server offers a guide for
  agents (`sciencelogo://guide`) and the manual pages
  (`sciencelogo://docs/{topic}`) as resources.

Steps done outside ScienceLogo are described as a method, never by file
paths or code: `declare_procedure` asks for what the step does, its inputs,
the kind, fields and units of its result, and its uncertainty.

New stages get their own file under `stages/`, and the advice returned with
each write helps keep the workflow readable from the broad description down
to the details.

## MCP access

The server is published with this identity:

- registry name: `io.github.ScienceLogo/sciencelogo-mcp`
- OCI image: `ghcr.io/sciencelogo/sciencelogo-mcp:<release-version>`, with
  Racket and ScienceLogo inside
- transport: `stdio`
- official registry: `https://registry.modelcontextprotocol.io/`

It is discoverable in the official MCP Registry under
`io.github.ScienceLogo/sciencelogo-mcp`:

- `https://registry.modelcontextprotocol.io/?q=sciencelogo`

Local client configuration, with the package installed and Racket with the
`sciencelogo` package on the `PATH` (or named by `SCIENCELOGO_MCP_RACKET`):

```json
{
  "mcpServers": {
    "sciencelogo": {
      "command": "sciencelogo-mcp"
    }
  }
}
```

The registry metadata is declared in [`server.json`](server.json). The
publish workflow fills in the release version and image tag when publishing.

## Versions

The first two numbers of the server's version name the ScienceLogo language
version it supports: `0.2.x` works with language 0.2. See
[CHANGELOG.md](CHANGELOG.md).

## Development

```
scripts/validate-local.sh
```

runs ruff, builds the image and runs the tests inside it, against the
image's Racket and ScienceLogo. Set `CONTAINER=podman` to use Podman.

Pushing a tag `vX.Y.Z` builds the image, pushes it to the GitHub Container
Registry and publishes `server.json` to the MCP Registry.

## Licence

MIT, copyright 2026 Riccardo Boero. See [LICENSE](LICENSE).
