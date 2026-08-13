# Escape Mermaid text hazards, and warn about the ones we will not rewrite.
#
# Reads the markdown source, writes it to stdout with sequence-diagram text
# payloads escaped, and reports findings on stderr as `src:line: message`.
#
# Why escaping works at all: mermaid's Diagram.fromText() runs encodeEntities()
# over the RAW SOURCE before the lexer sees it, rewriting `#\w+;` codes to
# private-use characters, and decodeEntities() restores them after render. So
# `#59;` and `#35;` are safe in every diagram type — including sequenceDiagram,
# whose lexer otherwise treats `;` as a statement separator and lexes note and
# message text as `[^#\n;]*`, i.e. stopping dead at `;` or `#`.
#
# Usage: awk -f mermaid-lint.awk -v src=path/to/source.md path/to/source.md

function warn(lineno, msg) {
  printf "%s:%d: %s\n", src, lineno, msg > "/dev/stderr"
}

# Escape `;` and `#` left-to-right, copying well-formed entity codes through
# untouched. One pass is what makes escaping BOTH characters correct — two
# passes would corrupt the codes produced by the first.
function esc(s,   out, c) {
  out = ""
  while (length(s) > 0) {
    if (match(s, /^#[A-Za-z0-9]+;/)) {
      out = out substr(s, RSTART, RLENGTH)
      s = substr(s, RLENGTH + 1)
      continue
    }
    c = substr(s, 1, 1)
    if (c == "#")      { out = out "#35;"; nesc++ }
    else if (c == ";") { out = out "#59;"; nesc++ }
    else               { out = out c }
    s = substr(s, 2)
  }
  return out
}

function diagtype(t) {
  if (t ~ /^sequenceDiagram([ \t]|$)/)                     return "sequence"
  if (t ~ /^(flowchart|graph)([ \t]|$)/)                   return "flowchart"
  if (t ~ /^(stateDiagram-v2|stateDiagram|erDiagram|classDiagram|journey|gantt|pie|gitGraph|mindmap|timeline|quadrantChart|requirementDiagram|sankey-beta|xychart-beta|block-beta|packet-beta|kanban|architecture-beta|radar-beta|treemap|C4Context|C4Container|C4Component|C4Dynamic|C4Deployment)([ \t]|$)/) return "other"
  return "unknown"
}

# The start offset of a sequenceDiagram line's free-text payload, or 0.
function payload_at(body, base,   rest, ci) {
  if (body ~ /^%%/)                                        return 0
  # URLs and JSON live here; `#` and `;` are load-bearing.
  if (body ~ /^(link|links|properties|details)([ \t]|$)/)   return 0

  if (body ~ /^[Nn]ote([ \t]|$)/) {
    ci = index(body, ":")
    return ci ? base + ci : 0
  }
  if (body ~ /^title:/)      return base + 6
  if (body ~ /^title[ \t]/)  return base + 5
  if (body ~ /^(alt|else|opt|loop|par_over|par|and|critical|option|break|rect|box)([ \t]|$)/) {
    match(body, /^[A-Za-z_]+/)
    return base + RLENGTH
  }
  # A message line: text begins at the first `:` after the arrow token.
  if (match(body, /(<<-->>|<<->>|-->>|->>|-->|->|--x|-x|--\)|-\))/)) {
    rest = substr(body, RSTART + RLENGTH)
    ci = index(rest, ":")
    if (ci) return base + RSTART + RLENGTH + ci - 1
  }
  return 0
}

function lint_flowchart(line, lineno) {
  # An unquoted bracketed label containing `;` or `#`. Flowchart treats `;` as a
  # statement separator and `#` as a comment, exactly as sequence does — but the
  # label spans are too structurally varied to rewrite unattended, so we report.
  if (line ~ /[[({][^"'\])}]*[;#]/ && line !~ /#[A-Za-z0-9]+;/)
    warn(lineno, "warning: `;` or `#` inside an unquoted label ends the statement — quote it: A[\"text; here\"]")
  # `end` is a flowchart keyword; as a node id it breaks subgraph parsing.
  if (line ~ /(^|[ \t])end[ \t]*[[({]/)
    warn(lineno, "warning: `end` is a reserved flowchart keyword — rename this node")
}

BEGIN { infence = 0; infront = 0; type = ""; fencestart = 0 }

{
  if (!infence) {
    if ($0 ~ /^[ \t]*```mermaid[ \t]*$/) {
      infence = 1; infront = 0; type = ""; fencestart = NR
    }
    print
    next
  }

  if ($0 ~ /^[ \t]*```[ \t]*$/) {
    if (type == "") warn(fencestart, "warning: ```mermaid block has no diagram type")
    infence = 0; infront = 0; type = ""
    print
    next
  }

  body = $0
  sub(/^[ \t]+/, "", body)

  # Optional YAML frontmatter inside the fence, e.g. `config:` / `layout:`.
  if (infront) {
    if (body ~ /^layout:[ \t]*elk/)
      warn(NR, "warning: `layout: elk` is not available — ELK is not in the bundle; remove it")
    if (body ~ /^---[ \t]*$/) infront = 0
    print
    next
  }

  if (type == "" && body != "" && body !~ /^%%/) {
    if (body ~ /^---[ \t]*$/) { infront = 1; print; next }
    type = diagtype(body)
    if (type == "unknown") {
      match(body, /^[A-Za-z0-9_-]+/)
      warn(NR, "warning: unrecognised diagram type \"" substr(body, 1, RLENGTH) "\" — the first line must name the type (flowchart TD, sequenceDiagram, stateDiagram-v2, …)")
    }
  }

  if (type == "sequence") {
    at = payload_at(body, length($0) - length(body))
    if (at > 0) {
      nesc = 0
      fixed = substr($0, 1, at) esc(substr($0, at + 1))
      if (nesc > 0) {
        warn(NR, "escaped " nesc " `;`/`#` in sequenceDiagram text (auto-fixed)")
        $0 = fixed
      }
    }
  } else if (type == "flowchart") {
    lint_flowchart($0, NR)
  }

  print
}

END {
  if (infence) warn(fencestart, "warning: unclosed ```mermaid fence")
}
