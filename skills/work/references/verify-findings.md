# Verify findings

Strong model, fresh context, read-only. Runs when two or more reviewers ran
and at least one found something. Pack in `context.md`.

Parallel reviewers produce noise; only verified findings reach the worker.

For each candidate: deduplicate against the others; open the code and confirm
the claim is true *as stated* — the scenario really occurs, the invariant
really is violated, the abstraction really has one implementation; reject
what does not hold and say in one clause why; keep or adjust the severity;
name the smallest appropriate correction.

Be skeptical of confident prose. A finding with no `file:line` and no
scenario is a hypothesis; verify it or drop it. Do not add findings of your
own unless verifying one exposes another in the same lines.

## Output

```markdown
# Verified findings — chunk 02
1. BLOCKER  src/store/queue.ts:88 — flush() drops rows on partial write failure.
   Fix: mark rows sent only after the batch ack; see invariant "never silently disappear".
2. DESIGN   src/store/queue.ts:12 — QueueStrategy has one implementation. Fix: inline.

Rejected: "race in enqueue" — enqueue holds the same lock as flush (queue.ts:40).
```

Write it to `.work/handoffs/<phase>-findings.md`; reply with the path and
count. The coordinator hands the file, unedited, to the fix pass.
