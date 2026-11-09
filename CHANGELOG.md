# Changelog

The first two numbers of each version name the ScienceLogo language version
it supports: version `0.2.x` works with language version `0.2`. The third
number counts the server's own releases for that language version.

## 0.2.0

### Added

- An MCP server, over stdio, for writing and maintaining ScienceLogo
  workflows and libraries with language version 0.2.
- Every write is checked by the ScienceLogo reference reader before it is
  saved; a write the reader rejects leaves every file as it was.
- Reading and checking: `check` (reader, structural assessment and
  readability advice), `outline`, `read_workflow` in verbose or compact
  syntax, and `language_reference` for the manual, grammar, changelog and
  examples of the installed release.
- Writing: `create_workflow`, `create_library`, `write_fragment`,
  `remove_item`, `move_item`, and one tool for each construct: `set_workflow`,
  `declare_performer`, `declare_resource`, `declare_proposition`,
  `declare_interface`, `declare_procedure`, `add_stage`, `add_paired_stage`,
  `add_phase`, `add_requirement`, `add_mapping`, `import_library` and
  `add_include`.
- A guide for agents and the manual pages as MCP resources.
- A container image with Racket 9.3 and ScienceLogo 0.2, published to the
  GitHub Container Registry and the MCP Registry for each version tag.
