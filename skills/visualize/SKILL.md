---
name: visualize
description: Render a plan, architecture, data flow, or system model as a single self-contained HTML page, open it in the browser, and read back the user's annotations. Use when the user asks to visualize, diagram, or map out a system or plan, or wants something they can look at and share.
---

# visualize

Turn a plan or system model into one HTML file the user can open, mark up, and send to anyone.

This produces an **artifact to look at**, not a source file to commit. For committed
diagram sources, use `/diagram` instead.

## Choosing the diagram type

Pick by modeling job and audience, not by habit. This choice matters more than the syntax.

| Job | Type | Audience |
|---|---|---|
| Message order between services or actors | `sequenceDiagram` | developers, debugging a flow |
| Lifecycle, valid transitions, invalid states | `stateDiagram-v2` | developers, domain modelling |
| Control flow, branching, ownership handoffs | `flowchart` | mixed, process discussion |
| System boundary and neighbours | `C4Context` | stakeholders, onboarding |
| Services, stores, and their relationships | `C4Container` | architects |
| Tables, keys, cardinality | `erDiagram` | data modelling |
| Dependency or coupling structure | `flowchart` + subgraphs | refactoring, blast radius |

If the system needs more than one abstraction level, write multiple `##` sections rather
than one dense diagram. Section nav appears automatically when there is more than one.

## Producing a visualization

1. Write the source to `docs/viz/<slug>.md`:
   - One `#` title.
   - One `##` per view. Short prose, then a ```mermaid fence.
   - Write markdown normally. **Do not hand-escape anything** — `assemble.sh` does it.
   - Prefer stable, meaningful Mermaid node ids (`auth-svc`, not `n1`). Annotations
     anchor to them, so renaming a node orphans its notes.

2. Assemble and open:

```bash
mkdir -p docs/viz
<skill-dir>/assemble.sh docs/viz/<slug>.md docs/viz/<slug>.html "<Title>"
open docs/viz/<slug>.html        # macOS; xdg-open on Linux, start on Windows
```

**Read what `assemble.sh` prints on stderr.** It reports every character it escaped
for you and every hazard it would not touch, as `docs/viz/<slug>.md:LINE: …`. Warnings
never block the build, so a page still opens — but a `warning:` line means a diagram
may not render, and the fix belongs in the `.md`.

3. Tell the user the path and that they can mark it up:

> Opened `docs/viz/<slug>.html`. Select any text to highlight it and leave a comment,
> or use the toolbar to add notes, circle nodes, strike things out, or draw arrows —
> then **Copy for agent** and paste it back, or **Save** to keep a copy with your markup.

Mention the file is ~1.7 MB (Mermaid is inlined so it works offline) if they plan to email it.

## Writing Mermaid that parses

`;` and `#` are not ordinary characters in Mermaid. `;` ends a statement and `#` opens
a comment, in every diagram type. In a `sequenceDiagram` the damage is invisible until
it fails: note and message text is lexed as `[^#\n;]*`, so

```
Note over A: re-validated at completion; a NEW action cancels it
```

ends the note at the semicolon and tries to parse the rest as a fresh statement, which
produces a page-long list of expected token names pointing at the wrong thing.

**You do not need to escape these by hand.** `assemble.sh` rewrites `;` to `#59;` and
`#` to `#35;` inside `sequenceDiagram` text — after `Note …:`, after a message arrow's
`:`, after `alt`/`else`/`opt`/`loop`/`par`/`and`/`critical`/`option`/`break`/`rect`/`box`,
and after `title`. It skips `%%` comments and `link`/`links`/`properties`/`details`
lines, where URLs and JSON need those characters intact, and it never double-escapes a
code you wrote yourself. Mermaid decodes `#NN;` before parsing and restores it after
rendering, so the reader sees a normal semicolon.

What it will **not** fix, and warns about instead:

| Warning | Fix in the `.md` |
|---|---|
| `;` or `#` in an unquoted flowchart label | quote it — `a["cost; per tick"]` |
| `end` used as a flowchart node id | rename it; `end` is a keyword |
| `layout: elk` | remove it — ELK is not in the bundle |
| unclosed ` ```mermaid ` fence | close it |
| unrecognised diagram type | the first line must name the type |

Parentheses and brackets inside a flowchart label break it the same way; quoting fixes
those too. When a diagram does fail, the page now shows the offending source line with
a caret and a plain-English cause rather than the raw parser message, so read the
rendered page before guessing.

## Writing Mermaid that parses

`;` and `#` are not ordinary characters in Mermaid. `;` ends a statement and `#` opens
a comment, in every diagram type. In a `sequenceDiagram` the damage is invisible until
it fails: note and message text is lexed as `[^#\n;]*`, so

```
Note over A: re-validated at completion; a NEW action cancels it
```

ends the note at the semicolon and tries to parse the rest as a fresh statement, which
produces a page-long list of expected token names pointing at the wrong thing.

**You do not need to escape these by hand.** `assemble.sh` rewrites `;` to `#59;` and
`#` to `#35;` inside `sequenceDiagram` text — after `Note …:`, after a message arrow's
`:`, after `alt`/`else`/`opt`/`loop`/`par`/`and`/`critical`/`option`/`break`/`rect`/`box`,
and after `title`. It skips `%%` comments and `link`/`links`/`properties`/`details`
lines, where URLs and JSON need those characters intact, and it never double-escapes a
code you wrote yourself. Mermaid decodes `#NN;` before parsing and restores it after
rendering, so the reader sees a normal semicolon.

What it will **not** fix, and warns about instead:

| Warning | Fix in the `.md` |
|---|---|
| `;` or `#` in an unquoted flowchart label | quote it — `a["cost; per tick"]` |
| `end` used as a flowchart node id | rename it; `end` is a keyword |
| `layout: elk` | remove it — ELK is not in the bundle |
| unclosed ` ```mermaid ` fence | close it |
| unrecognised diagram type | the first line must name the type |

Parentheses and brackets inside a flowchart label break it the same way; quoting fixes
those too. When a diagram does fail, the page now shows the offending source line with
a caret and a plain-English cause rather than the raw parser message, so read the
rendered page before guessing.

## Revising

Edit `docs/viz/<slug>.md` and re-run `assemble.sh` over the **same** output path. It
carries the existing `#viz-marks` block forward, so annotations survive. Never delete the
`.html` before regenerating — that discards the user's feedback.

## Reading feedback back

If the user pastes the export, use it directly. If they point at a saved file:

```bash
head -40 <path-to-html>
```

The `viz-marks` JSON block sits in the first 40 lines by design — before the markdown
source, which is unbounded. Each mark carries:

| Field | Meaning |
|---|---|
| `kind` | `note` \| `circle` \| `strike` \| `arrow` \| `pen` \| `highlight` |
| `section` | heading slug the mark belongs to |
| `node` | the Mermaid source id it anchors to, or `null` for a section-level note |
| `nodes` | for `circle`: every node inside the drawn box |
| `to` | for `arrow`: the target node id |
| `quote` | for `highlight`: the exact prose that was selected |
| `prefix`, `suffix` | for `highlight`: ~32 characters either side, so the quote re-anchors after an edit nearby |
| `text` | the user's words |

A `highlight` is feedback on the **prose**, not on a diagram. Its `quote` is the
sentence to edit, and the export prints it under the section heading:

```
- ▮ highlight "The mind is advisory only"
    "is this still true after the M2.5 ControlledMind wrap?"
```

Editing that sentence in the `.md` orphans the highlight — correctly, since the words
it referred to are gone. Orphans still appear under `## Unanchored` in the export, so
address them before assuming they were noise.

Every `<` in that block is written as the JSON escape `\u003c`, so annotation text can
never terminate the data block. Decode it before quoting the user's words back.

## Exporting a figure

Each figure's control bar carries two exports:

- **copy** — that diagram's Mermaid source with its annotations prepended as `%%`
  comments. Still valid Mermaid, so it pastes anywhere.
- **✎** — a `.excalidraw` file: the figure as editable shapes *plus* the annotations
  (circle → ellipse, strike → line, arrow → arrow, pen → freedraw, note → text). Open it
  at excalidraw.com, in the VS Code extension, or the desktop app.

The Excalidraw export is **flowcharts only** — sequence, state, ER and C4 become boxes
whose positions carry no reusable meaning, so it refuses rather than emitting a mess. It is
also **one-way**: once edited in Excalidraw, regenerating the `.md` cannot reach it. Offer
it as a starting draft, not a synced view.

## Constraints

Self-contained, offline, no server, no network. Do not add CDN references to
`template.html` — a test enforces this, along with script-tag balance and the absence of
module scripts. Mermaid is pinned; `layout: "elk"` is unavailable because ELK is not in
the bundle.
