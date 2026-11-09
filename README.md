# ScienceLogo MCP server

An [MCP](https://modelcontextprotocol.io/) server that lets AI agents, and
through them people, write and maintain
[ScienceLogo](https://github.com/ScienceLogo/Language) workflows and
libraries. It works the same way in Claude Code, Codex, Goose and other MCP
clients.

The ScienceLogo reference reader checks every write before it is saved. A
write the reader rejects changes nothing, and the agent gets the reader's
message with the file, line and column.

## Tools

Items are named `kind:name`, for example `stage:Measure`. Every tool that
writes is checked by the reader, and a construct tool replaces an item of the
same kind and name.

**Reading and checking**

| Tool | What it does |
| --- | --- |
| `check` | Runs the reader, the structural assessment and readability advice. |
| `outline` | Lists every item, with the stages, phases, procedures, performers and imports. |
| `read_workflow` | Returns a workflow in verbose or compact syntax, whole or one item; a file the current reader rejects is returned as stored. |
| `language_reference` | Returns a manual page, the grammar, the changelog or an example of the installed release. |
| `describe_library` | Shows what a library provides, its procedures and record interfaces, before it is imported. |

**Starting and changing the structure**

| Tool | What it does |
| --- | --- |
| `create_workflow` | Starts a workflow with its title and summary. |
| `create_library` | Starts a library project. |
| `write_fragment` | Writes any ScienceLogo text, at the end of a file or next to or in place of an item. |
| `remove_item` | Removes an item. |
| `move_item` | Moves an item to another file, keeping the method's order. |
| `convert_syntax` | Rewrites files in verbose or compact syntax, keeping comments. |

**Writing each construct**

| Tool | What it writes |
| --- | --- |
| `set_workflow` | The workflow's title and summary. |
| `declare_performer` | Who or what carries out work. |
| `declare_resource` | A resource the method uses, such as an instrument. |
| `declare_proposition` | A hypothesis, assumption or conclusion. |
| `declare_interface` | A record interface: the fields a record must or may have. |
| `declare_procedure` | A procedure, with its result's fields and units and its uncertainty. |
| `add_stage` | A simple stage, in its own file under `stages/` by default. |
| `add_paired_stage` | A stage with entry and exit state; the exit state is derived from the calls. |
| `add_phase` | A named group of stages with its own summary. |
| `add_requirement` | A required call or stage order. |
| `add_mapping` | A statement that a record implements an interface. |
| `import_library` | A library import pinned to a tag or commit. |
| `add_include` | An include of an existing file. |

**Resources:** a guide for agents (`sciencelogo://guide`) and the manual
pages (`sciencelogo://docs/{topic}`). No model knows ScienceLogo, so the
server teaches it.

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
