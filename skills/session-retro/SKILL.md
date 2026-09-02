---
name: session-retro
description: Run a retrospective on the work session that just finished — where the time actually went, which instruction in CLAUDE.md, AGENTS.md, a skill or a hook caused it, and what to remove, add or change so the next session is cheaper. Produces a fixed report — what worked, what cost time, proposed edits, working-practice and test changes — and applies only the edits the user approves. Accepts a session id from Claude Code, Codex or OpenCode (`/session-retro <session-id>`) to retro a session you were not part of, and has an experimental group mode that samples similar sessions from the same project and reports only what recurs. Use this whenever the user runs /session-retro, says "let's do a retro", "post-mortem", "what did we learn", "why was that so slow", "that took way too long", asks why the agent keeps doing something pointless, or wonders whether the project's agent instructions are helping or hurting. Offer it unprompted at the end of a long, painful, or surprising piece of work — the evidence is in this session's context and is gone once the session ends.
---

# Session Retro

An agent follows written instructions literally and consistently. That is the
good part — it is why a rule you write once keeps holding at 2am on the
hundredth run. It is also why a badly scoped rule is not a small annoyance but a
permanent tax: nobody notices the rule is wrong, because the agent never
complains, it just pays the cost again every session.

The real example this skill was built from: a project's instructions said *run
the tests when something is updated*. A human reads that and applies obvious
judgement — a typo fix in a README does not need the full suite. The agent does
not. It ran the entire test suite for a documentation-only change, every time,
for weeks. The fix was one line: run the tests when **code** changes, skip them
for documentation-only changes.

That class of defect is invisible from inside the instruction file and obvious
from inside a session that just paid for it. This skill catches it while the
evidence is still in context.

## When to run it

At the end of a substantial piece of work, before the session is closed. Also
mid-session when something has clearly gone sideways and the user asks why.

If the user has not asked, it is fine to offer once — "want a quick retro on
that?" — and drop it if they say no. Do not offer it after small, clean tasks;
a retro on a two-minute edit is noise.

## Whose work this is

Yours. The session is the evidence and you were in it — you know which command
was retried, which file you read three times, and which sentence in AGENTS.md
sent you there. Do the analysis, answer your own questions from the transcript,
and arrive with conclusions.

Do not turn this into an interview. A retro that opens by asking the user what
they thought went wrong has handed the work back to the person who has the least
visibility into it — they saw the output, you saw the run. The user's attention
is needed at exactly one place: approving the proposed changes.

Some questions genuinely need them — whether a costly rule was deliberate,
whether a slow check is protecting something you cannot see. Carry those into
the report as *open questions* alongside your best guess, rather than stopping
to ask. One or two are a sign you looked carefully; six mean you did not.

The scope is everything the session touched, not just the instruction files:
the repo's scripts and test layout, the tooling you wished existed, the
approvals that interrupted you, how the work was sequenced. Anything that would
make the same session cheaper next time is in scope.

## Step 0 — Which session

**No argument: the session you are in.** Its evidence is already in context,
which is the cheapest and richest case. Skip to Step 1.

**A session id pasted in** — `/session-retro 2a5582a4-81b8-…`, or a Codex
`019be546-…`, or an OpenCode `ses_3dba80…` — means a session you were not part
of, possibly from another host. Locate it:

```bash
python3 <skill>/scripts/find_session.py resolve <session-id>
```

The script searches Claude Code, Codex and OpenCode transcript stores and prints
the host, working directory and transcript path. Ids may be a unique prefix.
`list` (optionally `--project <dir>`, `--host`, `--since`) shows recent sessions
newest-first when the user does not have an id to hand — offer that rather than
asking them to go find one.

The three hosts store sessions differently, and the script papers over it: for
Claude and Codex the path is a single JSONL transcript; for OpenCode it is a
directory of per-message JSON files, with the session's metadata file listed
separately.

### Reading a transcript you were not in

Transcripts are far larger than they look — do not read one end to end. Pull the
skeleton first, then read only around what looks expensive:

- **The user's turns are the highest-signal slice.** Read those first, in order.
  They contain the goal, every correction, and every sign of frustration.
  In Claude's JSONL these are records with `.type == "user"`; in Codex's rollout
  they sit inside `response_item` payloads with `role: user`; in OpenCode they
  are message files with `"role": "user"`.
- **Then the shape of the work**: which tools ran, in what order, and which ones
  repeat. Counting tool names is usually enough to spot the loop.
- **Then read the specific moments** — the retried command, the correction, the
  long stretch — in full.

A retro on a foreign transcript is weaker than one on a live session: you can
see what happened but not what the agent was weighing. Say so if it matters, and
prefer findings that rest on visible facts — commands run, files touched, things
the user said.

## The rule that makes this useful

**Every finding cites something that actually happened in this session.** A
symptom, a moment, a command, a correction the user made. The seductive failure
mode is to read the project's CLAUDE.md, think hard, and produce a list of
plausible improvements — that is a rewrite from intuition wearing the costume of
a retro, and it makes the instruction files worse by accretion.

If you cannot point at the moment, say it is a hypothesis and mark it as such.
If the session genuinely went well, the correct report proposes nothing. A
retro that always finds three changes is a retro nobody will trust.

## Step 1 — Reconstruct where the effort went

Count before you judge. A session leaves real numbers behind, and they settle
arguments that impressions cannot: how many tool calls it took, how many times
the same command ran, how often a file was re-read, how many retries, how long
the slowest command took, whether the context was compacted. "The suite ran four
times at six minutes" is an argument. "It felt slow" is not.

Then look for:

- **The biggest single cost.** The longest-running command, the largest file
  reads, the step that was retried. What was it, and was it necessary?
- **Repetition.** The same command, search, or file read more than twice.
  Repetition is usually a fact that should have been written down once.
- **Re-derivation.** Anything you had to work out that a line of documentation
  could have stated: the test command, the dev server port, where config lives,
  which of two similar directories is canonical.
- **User corrections.** Every "no, not like that" is a rule that was missing,
  wrong, or unfindable. These are the highest-signal findings in the session.
- **Wrong turns.** Dead ends, tools that failed, approaches abandoned halfway.
- **Context spent, not just time.** Whole files read where a targeted read would
  do, raw command output dumped into the thread, a fan-out search that belonged
  in a subagent, a skill that loaded and turned out not to apply. Wasted context
  is a distinct failure from wasted minutes and takes different fixes. Be
  careful with the subagent finding in particular: below roughly three
  independent subtasks, the coordination costs more context than it saves.
- **Friction that was not the work.** Approval prompts that interrupted a
  sequence, a tool that needed three tries to call correctly, output that had to
  be reformatted by hand. These have concrete fixes — an allowlist entry, a
  flag, a script — and they never appear in anyone's memory of the session.
- **What was skipped.** This is the one a retro will miss unless it asks
  deliberately. Something not run, not checked, not asked about, that had to be
  paid for later in the session or is still unpaid. A retro that only hunts for
  over-doing quietly optimises for an agent that ships faster and verifies less;
  ask both questions or the file drifts in one direction.

### The counterfactual

Then ask the question that no good/bad list produces on its own: **what is the
shortest path that would have reached this same result?** Sketch it — the four
or five steps an agent who already knew everything you learned would have taken.
Diff that against what actually happened.

The gap is the finding, and it is usually a better one than anything in the list
above, because it catches the costs that had no single culprit: the hour of
building before a question that should have come first, forty tool calls where
five would have done, work sequenced serially that had no dependency between its
halves.

If the session was compacted, do not retro from what you remember of the early
part. A summary written under context pressure drops goals and user constraints
first — exactly the material a retro needs — and it reads as authoritative
afterwards. The transcript is still on disk, as the session's own JSONL log
under the agent's project session directory. Read the start of it.

## Step 2 — Trace each cost to its cause

For each expensive thing, ask what made it happen. The candidates, roughly in
order of how often they are the culprit:

- **A project instruction file** — `CLAUDE.md`, `AGENTS.md`, or a nested one in
  a subdirectory. Check for nested files; a rule two directories down is easy to
  forget and still binding.
- **The user-level instruction file**, which applies to every project and is
  therefore the worst place for a project-specific rule.
- **A skill or command** that loaded and steered the work.
- **A hook or settings entry** that ran something automatically.
- **Nothing written down at all** — the cost came from a missing fact, not a bad
  rule. That is an *add*, and it is just as valuable as a *remove*.

Quote the offending line and name its file. "The instructions are too broad" is
not actionable; `AGENTS.md:14 — "always run the full test suite before
finishing"` is.

Distinguish the two failure shapes, because they need opposite fixes:

- **Wrong trigger** — the rule is right but fires in cases it should not (tests
  on a docs change). Fix by scoping the trigger and naming the exception.
- **Wrong action** — the trigger is right but what it asks for is too broad
  (whole suite where a targeted path would do). Fix by narrowing the command.

## Step 3 — Write the report

Use this structure. Keep each bullet to one or two lines; this is a working
document, not a write-up.

```markdown
# Retro: <what the session was trying to do>

## What worked
- <what demonstrably saved time, and the moment it did — worth keeping>

## What cost time
- <symptom> — <measured cost: calls, retries, minutes> — <cause, with file:line quoted>

## The shorter path
- <the 4-5 steps that would have reached the same result, and where we diverged>

## Proposed changes
<the table from Step 5 — this is the part the user acts on>

## Repo, tooling and ways of working
- <change to what exists or how the work is done, not to what is written down>

## Open questions
- <question only the user can answer> — my guess: <your best answer>

## Not worth changing
- <thing that was annoying but is cheaper to live with than to encode>
```

**At most three proposed changes.** Rank by measured cost and cut the rest into
`Not worth changing`. A retro with twelve proposals gets none of them applied;
three land, and the next retro can have the next three.

`What worked` is held to the same citation rule as everything else — name the
instruction, script or tool that actually saved time and the moment it did.
Without that it becomes filler, and it is worth keeping precisely because a rule
nobody can remember the reason for eventually gets deleted by someone tidying up.

`Not worth changing` is the section that keeps the instruction files small. Some
friction is one-off. Say so out loud instead of quietly encoding it.

## Step 4 — Propose good edits, not more edits

Every line in an instruction file is loaded into every session forever, whether
or not it is relevant. Additions are cheap to write and expensive to keep, so
hold them to a standard:

- **Scope the trigger.** "When source code changes" beats "when something is
  updated". Name the exception explicitly — the agent will not infer that docs
  are different, and the whole point is that it does not exercise judgement
  where you did not ask for it.
- **Name the exact command.** `pytest tests/test_repository.py` is followable;
  "run the relevant tests" makes every session re-derive what is relevant.
- **One behaviour per line.** Compound rules fire half-right.
- **Say when not to do it.** The costly cases are almost always missing
  exceptions rather than missing rules.
- **Prefer replacing a line to adding one.** Propose deletions as eagerly as
  additions: a rule that never fired, or one that fires on everything, is
  costing context and buying nothing.
- **But do not confuse specific with bloated.** Repeated rounds of "delete what
  seems excessive" collapse an instruction file toward short, generic advice and
  strip out the hard-won domain specifics that were carrying the value —
  measurably below where it started. Delete a rule because it is *wrong*, fires
  on the wrong trigger, or has never fired; never because it is long or narrow.
  Narrow and specific is what a good rule looks like.
- **Put it in the right home.** Project-specific facts belong in the project's
  instruction file; a habit that follows the user across projects belongs in
  user-level instructions or memory; a multi-step procedure belongs in a skill,
  not in an ever-growing list of rules.
- **Fix it at the shallowest level that works.** A missing fact wants a line of
  documentation, not a rule; a wrong default wants a config change, not a
  process. Machinery proposed where a fact would have done is the most common
  over-correction a retro makes.
- **Prefer a fix that cannot be ignored.** A written rule is the weakest fix
  available — it competes for attention with every other line in the file. If
  the same outcome can be had from a script, a make target, a `--json` flag, a
  test that fails when the mistake is made, a permission allowlist entry, or a
  default changed in config, propose that instead. The best retro outcome is
  often one line **removed** from an instruction file and one line **added** to
  a Makefile.

**Worked example — wrong trigger:**

```
Before: Run the tests whenever something is updated.
After:  Run the tests when source code changes. Skip them for
        documentation-only changes (*.md, docs/).
```

**Worked example — wrong action:**

```
Before: Before finishing, run the full test suite.
After:  Before finishing, run the tests covering the files you changed
        (`pytest <path>`). Run the full suite only when you touched shared
        config, dependencies, or CI.
```

The `Working practices, tests and tooling` section covers what a written rule
cannot fix: a missing script for a five-command sequence you ran by hand, a test
that would have caught the bug you found late, a check that is slow because it
does too much, work that should have been done in parallel or handed to a
subagent, a question that should have been asked before an hour of building.

## Step 5 — Present the changes as a decision table

Everything above this point is analysis. This is the only part the user has to
read, so it has to be scannable in one pass and approvable in a few keystrokes —
that is what makes a retro a fast route to an improvement rather than another
document to get through.

Print it in the terminal. Three weights carry three kinds of information: a boxed
title says what is wrong, plain text says what it cost, an italic line says what
to do about it. Rank by cost, worst first. No prose paragraphs above the list.

| Tier | Meaning |
|------|---------|
| 🔴 Red | Cost real time or correctness this session, and will again next session. A rule that misfires, a wrong instruction, a check that was skipped and shouldn't have been. |
| 🟠 Orange | Recurring friction or waste. Survivable, repeatedly annoying, cheap to fix. |
| 🟡 Yellow | Polish, a single occurrence, or a hypothesis you could not fully evidence. Say which. |

The evidence column carries the measurement from Step 1 — runs, retries, minutes,
tool calls. In group mode it carries `k/n` sessions instead.

Emit exactly this shape (the four-backtick fence is only so you can see the
source — your real output is not fenced, or none of it renders):

````markdown
🔴 cost time this session and will again · 🟠 recurring friction · 🟡 polish or hypothesis

🔴 R1 │ `full suite runs on docs-only changes`                4 runs · 24 min
      │ *AGENTS.md:14 — scope it to source changes, exclude*
      │ *docs/ and *.md.*

🟠 R2 │ `test command re-derived from scratch`               3 lookups
      │ *CLAUDE.md — state it once: pytest tests/ -q.*

🟡 R3 │ `permission prompt on every gh call`                 7 interruptions
      │ *settings.json allowlist entry — guessing this is why*
      │ *the PR steps kept stalling; unconfirmed.*
````

Four mechanics keep it from collapsing in the renderer:

- Markdown collapses runs of spaces, so pad the evidence column and indent the
  continuation gutter with non-breaking spaces (U+00A0), never ordinary ones.
- End every line with two trailing spaces, or the renderer joins the lines into
  one paragraph and the shape is lost.
- Don't nest inline code inside an italic span — it is the one combination that
  renders inconsistently. Rephrase so a command sits in a plain-italic line.
- Keep each fix to one or two lines. A fix needing more is two findings.

Below the blocks, show the before/after for anything red, and quote the moment it
came from. Red earns the diff; orange and yellow can wait until they are picked.

**Then ask which to act on, and invite counter-proposals.** Approval by id or
tier is the fast path — "R1 and R3", "all red, skip the rest" — but say plainly
that changing a proposal is just as welcome as accepting or rejecting it. The
user knows things the transcript does not: that a rule was deliberate, that the
wording should be narrower, that the fix belongs in a different file, or that
they would rather have a script than a rule. When they reshape one, re-draft that
block and show it again before applying — a proposal rewritten in the user's own
terms is the best outcome the table has.

A "no, because…" is worth more than a yes. It says what the instructions are
actually for, and it is what should stop the next retro from proposing the same
thing again — so put it in the rejection note verbatim.

## Step 6 — Approve, then apply

Once the table has verdicts:

- Apply only what was approved, and only the approved wording.
- Edit surgically — change the lines named in the report, and leave the rest of
  the file alone. A retro that reflows a whole CLAUDE.md is unreviewable.
- Make sure the file is under version control, or say plainly that it is not
  before editing it.
- Show the resulting diff, briefly.

State what you expect to change. You cannot measure an instruction edit from
inside the session that proposed it — the evidence for whether it worked lands
in the *next* session. So for each applied change, say in one clause what should
look different next time ("the suite should no longer run on docs-only
changes"). That is what makes the following retro able to check it instead of
re-deriving the same finding.

Keep the rejections too. A proposal the user turned down will look just as
appealing to the next retro, and re-proposing it every month is how a useful
tool becomes background noise. A few lines at the bottom of the report — or a
short log beside the instruction file — naming what was rejected and why is
enough. Read it before proposing.

If nothing is approved, that is a fine outcome — the report itself is the value,
and the user may want to sit with it.

## Experimental — a retro across a group of sessions

One session tells you what went wrong once. A defect worth changing an
instruction file for usually went wrong five times. When the user asks for a
retro over recent work rather than one session — or passes `--similar` — widen
the evidence:

```bash
python3 <skill>/scripts/find_session.py similar <session-id> --limit 10
python3 <skill>/scripts/find_session.py list --project <dir> --since <date>
```

`similar` groups by working directory, which is the cheap and honest definition
of "similar": the same repository, the same instruction files, the same
toolchain. It spans hosts, so a Codex session and a Claude session in the same
repo land in the same group — that is often where the sharpest finding hides,
because the same rule is being read by two agents that behave differently.

Then work group-wise rather than session-wise:

1. **Sample, don't exhaust.** Five to ten sessions is plenty, and skimming ten
   cheaply beats reading three thoroughly. Prefer recent ones, and include the
   painful ones the user names.
2. **Extract per session, cheaply** — the goal, the two or three biggest costs,
   every user correction. Nothing else. Subagents are a good fit here: one per
   session. Require each to return the raw evidence with its summary — the
   command as it ran, the user's words verbatim, the file and line — because a
   model's paraphrase of a transcript reliably loses the detail that would have
   made the finding actionable. Before proposing an edit off the back of a
   summary, go read the moment it points at.
3. **Report only what recurs.** A finding must appear in at least two sessions
   to make the group report, and each one carries the session ids it came from
   and how many of the sampled sessions showed it. A one-off belongs in that
   session's own retro, not in an edit to a file that loads every time.
4. **Rank by frequency × cost**, not by how annoying the last one felt.

Use the same report structure, with the counts made visible:

```markdown
## What cost time
- <symptom> — seen in 6/8 sessions (<ids>) — <cause, file:line>
```

Two limits worth stating out loud when you present a group retro. The sample is
what you read, not what happened — say how many sessions you sampled out of how
many exist. And recurrence measures the instructions, not the work: a pattern
that shows up in every session may be the project's nature rather than a defect.
Ask whether removing it would actually have been correct before proposing it.
