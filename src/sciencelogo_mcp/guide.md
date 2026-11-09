# Writing ScienceLogo with this server

ScienceLogo describes a scientific method as text that people can read and
the reference reader can check. This server writes the files for you. The
reader checks every write, and a write it rejects changes nothing. Read this
guide first, then look up details with `language_reference`.

## A workflow

```
#lang sciencelogo
workflow "Pendulum period"
about "Does the period of a pendulum change as its swing gets smaller?"
include "stages/01-setup.rkt"
performer researcher [kind = "human" role = "scientist"]
resource timer [kind = "stopwatch"]
hypothesis constant-period [text = "The period stays constant as the swing diminishes."]
interface timing [must [period [value = unknown number unit = "seconds"]]]
to calculate-period :duration :count about "Divide the elapsed time by the swing count." [
  output timing.[] u [declared = [hand-timing = [text = "Reaction time when starting and stopping the timer."]]]
]
stage Measure by researcher from state [information = [elapsed = unknown swing-count = 10]]
do calculate-period with [duration at information.elapsed count at information.swing-count] into information.period
end stage with state [information = [elapsed = unknown swing-count = 10 period = unknown]]
stage Report about "Report the period."
print 3
phase Measurement about "Prepare and time the pendulum." [Setup Measure]
must do calculate-period
must stages in order [Setup Measure Report]
```

- The first line of every file is exactly `#lang sciencelogo`. Only the main
  file has `workflow`, its `about` and the `import` lines, in that order.
- A simple stage is `stage Name about "..."` followed by its commands, up to
  the next stage.
- A paired stage states what is known when it starts and when it ends
  (`information`, `environment`, `factors`). Its calls name where each input
  comes from and where the result goes.
- A procedure is `to name :input about "..." [ ... ]`. The `about` goes before
  the opening bracket.
- `unknown` is a value not known when the method is written. `u [...]`
  declares where a value's uncertainty comes from.
- A record interface declares the fields of a record; `name.[]` is an empty
  record of it.
- A phase groups stages, or other phases, under a name with its own `about`.
- `include "stages/01-setup.rkt"` reads another file in place. Included files
  start with `#lang sciencelogo` and have no title.

## A method, not a trace

Never write file paths, script names or references to code into a workflow.
For a step done outside ScienceLogo, use `declare_procedure` and describe it
as a method: what it does, its inputs, the kind, fields and units of its
result, its uncertainty, and the performer who carries it out.

## Readable structure

A reader goes from the broad description down to the details:

- the main file is the overview: title, about, performers, phases and the
  includes, in method order;
- each stage has its own file under `stages/` (the default of `add_stage`);
- procedures used by several stages go to `procedures/shared.rkt`;
- every workflow, phase, stage and procedure has an `about`.

The server's advice after each write points out what to improve. It never
blocks a write.

## Tools

1. `check`, `outline` and `read_workflow` show what exists.
2. `create_workflow` starts a workflow; `create_library` starts a library.
3. The construct tools write each kind of item, and replace an item with the
   same name: `set_workflow`, `declare_performer`, `declare_resource`,
   `declare_proposition`, `declare_interface`, `declare_procedure`,
   `add_stage`, `add_paired_stage`, `add_phase`, `add_requirement`,
   `add_mapping`, `import_library`, `add_include`.
4. `write_fragment` writes any other ScienceLogo text, such as commands in a
   stage or an interface with conditions.
5. `remove_item` and `move_item` change the structure. Items are named
   `kind:name`, for example `stage:Measure` or `procedure:calculate-period`.
6. `describe_library` shows what a library provides before you import it;
   reuse its procedures instead of writing them again.
7. `convert_syntax` rewrites files in verbose or compact syntax.

## Older workflows

A workflow written for an older release may fail the current reader.
`read_workflow` still returns its files as stored. Rewrite them in the
current release with the tools above; `language_reference("changelog")`
lists what changed.

## Language reference

`language_reference` with no topic lists the manual's topics and the
examples. `grammar-ebnf` is the full grammar; `changelog` the release notes.
