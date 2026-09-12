# Feedback sidecar

Two separate opt-ins, asked only after the feature is done and verified:

1. *"Feature complete. Capture this run as feedback for improving /work?"*
2. If yes, and `history.jsonl` now holds more than one record: *"Run
   skill-improver against the accumulated /work feedback now?"*

No on the first ends it. Never mutate this skill from one run's evidence.

## What to capture

Append one record to `.work/feedback/history.jsonl` — durable across features
in the repo, so the improver can see trends rather than a single run. Output
quality and architectural health, not workflow statistics:

```json
{"date": "2026-09-12", "feature": "offline-buffering", "level": "major",
 "files_changed": 8, "modules_changed": 3, "production_loc_delta": 420,
 "new_files": 2, "new_deps": 0, "chunks": 3,
 "review": {"chunk": {"found": 4, "verified": 3}, "final": {"found": 2, "verified": 1}, "blockers_fixed": 1},
 "escalations": 0, "manual_rescue": false,
 "user_note": "review caught the partial-flush bug; plan review was noise"}
```

`files_changed`, `modules_changed`, `production_loc_delta` and `new_files` come
from `git diff --stat <base_ref>`; the review numbers from the verified-findings
files. Ask for `user_note` in one line and accept silence. Useful notes: the
feature later caused a bug · the architecture feels harder to change · too much
ceremony · a review found an excellent issue · a review produced noise ·
implementation needed manual rescue.

The signal that matters over time: comparable features touching more files
than they used to, hotspots growing, duplicated invariants, escaped defects
clustering after a particular phase. Any of those is a workflow finding, not a
composite score. Do not invent a score.

The final review runs both lenses plus verifier once per feature; if
`final.verified` stays at zero across several MAJOR runs, drop its
correctness lens first (per-chunk review already covered it), never its
design lens — that is the only pass that sees all chunks together.

## Improving the skill

Run `skill-improver` with `work` as the target and point it at the history
file as extra evidence beside the transcripts. It reasons across multiple
runs and proposes the smallest change; it distinguishes model failure,
missing context, bad planning, bad implementation, review miss, false-positive
review and plain overhead. A good improvement looks like *"for stateful
changes, include the owning state machine in the correctness pack"*. A bad one
looks like *"add more reviewers"*.
