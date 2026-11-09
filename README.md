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

## Use it

The server runs as a container image with Racket and ScienceLogo inside. It
works on the ScienceLogo files of the folder it is started in, so that folder
is mounted into the container at the same path:

```
docker run -i --rm --user "$(id -u):$(id -g)" -v "$PWD:$PWD" -w "$PWD" \
  ghcr.io/sciencelogo/sciencelogo-mcp:0.2.0
```

`--user` keeps the files it writes owned by you. Podman works the same way.

**Claude Code**, from the project folder:

```
claude mcp add sciencelogo -- docker run -i --rm --user "$(id -u):$(id -g)" \
  -v "$PWD:$PWD" -w "$PWD" ghcr.io/sciencelogo/sciencelogo-mcp:0.2.0
```

**Codex**, in `~/.codex/config.toml`, with the project folder written out:

```toml
[mcp_servers.sciencelogo]
command = "docker"
# --user takes your user and group ids, from `id -u` and `id -g`.
args = ["run", "-i", "--rm", "--user", "1000:1000",
        "-v", "/path/to/project:/path/to/project", "-w", "/path/to/project",
        "ghcr.io/sciencelogo/sciencelogo-mcp:0.2.0"]
```

**Goose** and other clients: add a stdio server that runs the `docker`
command above.

The server is also listed in the MCP Registry as
`io.github.ScienceLogo/sciencelogo-mcp`.

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
