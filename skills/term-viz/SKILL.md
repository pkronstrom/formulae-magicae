---
name: term-viz
description: Draw diagrams as text right in the terminal reply — block/architecture, dependency graph, UML class, sequence, state machine, flowchart, timeline/gantt, bars and sparklines. Use when asked to draw, sketch, diagram or visualize something, or when a picture explains a structure, flow or plan faster than prose. /term-viz.
---

# term-viz

Show it, don't describe it — in the reply itself, no files, no browser.

## When

- **Asked:** "draw", "diagram", "show me how X connects", /term-viz.
- **Unasked:** when a picture beats prose — architecture, data flow, a plan's phases,
  before/after of a change, a call order. **One diagram per reply at most.** Skip it when
  the point fits in two sentences.

## Rules

- Always inside a ` ```text ` fence. ≤ 80 columns. No ANSI colour.
- Glyphs: `┌─┐│└┘├┤┬┴┼` boxes · `──▶ ◀── │ ▼ ▲` arrows · `╌╌▶` async/reply ·
  `◆` composition · `◇` decision · `█▇▅▃▁` bars.
- Label every edge whose meaning isn't obvious (`──HTTP──▶`).
- Use real names from the code (`auth_service`, not `Service A`).
- **Before sending, check alignment:** box edges in one column, every line in a box the
  same width. Misaligned art is worse than none.
- Add one line under the diagram only if it needs a key or a takeaway.

## Pick the type

| Showing | Draw | How |
|---|---|---|
| Components and their links | **Block** | hand |
| Who imports/calls whom | **Dependency tree** (`├──`, `──▶` for cross-links) | hand |
| Types, fields, relations | **UML class** (name / fields / methods, `1 *` cardinality) | hand |
| Message order between actors | **Sequence** (lifelines `│`, `──▶` call, `◀╌╌` reply) | hand; renderer if > 4 actors |
| Lifecycle, valid transitions | **State** (labelled edges, one per direction) | hand |
| Branching logic | **Flowchart** (`◇ cond? ◇──yes──▶`) | hand; renderer if > 8 nodes |
| Phases over time | **Gantt** (`████` per row, date header) | hand |
| Numbers | **Bars / sparkline / table** (`▁▂▃▅▇█`, scale shown) | hand |

## Renderer (big flowcharts and sequences only)

Write Mermaid, render it, and paste the output into the fence:

```bash
printf '%s\n' 'graph TD' '  a -->|HTTP| b' | <skill-dir>/mermaid-ascii.sh
```

Needs `node` and `npm`. The first run installs a pinned `beautiful-mermaid` into
`~/.cache/term-viz` (~10s). Don't use it for class or state diagrams: it
drops members and merges opposing edges. If it fails, hand-draw a smaller view instead.

## Too big?

Over ~12 nodes, split it: an overview diagram plus a zoom on the part that matters. For a
diagram meant to be kept or shared, use `/visualize` (HTML) or `/diagram` (source files).

## Shapes to copy

```text
┌────────┐ HTTP ┌──────┐ SQL ┌──────────┐
│ client │─────▶│ api  │────▶│ postgres │
└────────┘      └──┬───┘     └──────────┘
                   │ enqueue
                   ▼
              ┌────────┐
              │ worker │
              └────────┘
```

```text
 client       api         db
   │  POST /x  │           │
   │──────────▶│  INSERT   │
   │           │──────────▶│
   │           │◀╌╌╌ ok ╌╌╌│
   │◀╌╌ 201 ╌╌╌│           │
```

```text
┌────────────────┐ 1    * ┌──────────────┐
│ Order          │◆──────▶│ LineItem     │
├────────────────┤        ├──────────────┤
│ id: UUID       │        │ sku: str     │
│ total(): Money │        │ qty: int     │
└────────────────┘        └──────────────┘
```

```text
┌───────┐ submit ┌─────────┐ approve ┌──────────┐
│ draft │───────▶│ pending │────────▶│ approved │
└───────┘        └────┬────┘         └──────────┘
    ▲     reject      │
    └─────────────────┘
```

```text
 phase    18  19  20  21  22
 design   ████████
 build            ██████████
 review                   ████

 p50  ▁▂▂▃▅▇█▆▄▃  42ms
 api  ███████████████  68%
 db   ███████          31%
```
