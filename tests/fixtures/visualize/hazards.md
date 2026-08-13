# Mermaid hazards

## Sequence text that must be escaped

```mermaid
sequenceDiagram
  participant A as Registry
  participant E as Event log

  Note over A: re-validated at completion;<br/>a NEW action cancels it
  A->>E: queued; then resolved
  A-->>E: costs #5 per tick
  alt invalid; rejected
    A->>E: intent-rejected (reason)
  end
  Note over E: already escaped #59; stays as written
  Note over E: entity #quot;quoted#quot; survives
  link A: Docs @ https://example.com/docs#anchor
  %% a comment; with a semicolon
```

## Flowchart hazards that must only warn

```mermaid
flowchart LR
  a[label; with semicolon] --> b
  c[costs #5 per tick] --> d
  e["quoted; is fine"] --> f
  end[bad node id] --> g
```

## A block with no diagram type

```mermaid
  a --> b
```
