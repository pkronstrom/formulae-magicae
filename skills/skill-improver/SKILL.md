---
name: skill-improver
description: Improve an existing skill, slash command, subagent, MCP server, CLAUDE.md, or artifact by mining the real sessions where it was actually used — finding the quirks, wrong turns, ignored rules, wasted tokens and misunderstandings it produced in practice — then proposing a red/orange/yellow triage table of fixes for approval and applying the approved ones under version control. Use this whenever the user runs /skill-improver, says a skill feels sluggish, bloated, unreliable, or "never triggers", asks why an agent keeps making the same mistake with a skill, asks to review, tune, audit, optimize or clean up a skill, or wants to know which of their skills are worth keeping. Prefer this over editing a skill from memory or intuition: the whole point is that the evidence comes from transcripts, not from guessing. Run with no target, or with --survey, when the user asks which skills are worth improving, what they use most, what has never been reviewed, or where to start — it ranks their real usage against review history and recommends a target.
---

# Skill Improver

Skills are written once and then run hundreds of times. Everything you need to
know about whether a skill is any good is already recorded in the transcripts of
those runs — where the model hesitated, re-derived something the skill could have
stated, ignored a rule, wrote the same throwaway helper for the third time, or
got corrected by the user two turns after the skill loaded.

This skill mines that record and turns it into a small set of evidence-backed
edits. The user approves what lands.

The failure mode to avoid is the seductive one: reading the skill file, thinking
hard about it, and producing a list of plausible improvements. That is a rewrite
from intuition wearing the costume of a review. Every finding you propose must
point at a specific moment in a specific transcript. If you cannot cite one, the
finding is a hypothesis — say so, and tier it accordingly.

## The loop

Resolve target → load ledger → find sessions → extract raw episodes →
check the perishable claims → analyse → triage → present → approve →
apply under git → record.

Work through it in order. Steps 1–4.5 are cheap and can run without interrupting
the user; the user's attention is only needed at the triage table.

---

## Step 0 — Survey (no target named, or `--survey`)

When the user asks what is worth improving rather than naming a skill, start
here. Two facts already on disk answer it: how often each target actually ran,
and when it was last reviewed.

```bash
python3 <skill>/scripts/survey.py --days 60
```

It counts distinct sessions per skill, command and MCP server, reads the last
run date from each ledger, and ranks by priority: **never reviewed** first, then
**stale** (reviewed over 90 days ago), then **thin** (fewer than 4 sessions of
new evidence), then **recent**.

Two columns carry the decision. `sess` is total distinct sessions — how much the
target matters. `new` is sessions recorded *since* its last review — how much
fresh evidence a run would actually have to work with. A heavily used skill with
`new` in single digits will mostly re-derive its own last report; say so instead
of running it.

The script counts only unambiguous invocations: the Skill tool's `skill` field,
`<command-name>`, and `mcp__server__` appearing as a tool_use `name`. The loose
form of that last pattern matches the deferred-tool listing in every session's
system prompt, which reports availability rather than use — it buried the real
signal under thousands of phantom hits before the pattern was tightened. Harness
built-ins (`/clear`, `/model`) and names that resolve to no editable file are
dropped, because there is nothing to improve.

Present the top rows and recommend one target, with the reason in a clause:
heavy use and never reviewed, or a big backlog since a stale review. Then ask
which to run, and continue from Step 1 with their answer.

## Step 1 — Resolve the target and its home

The user names a skill (`/skill-improver bento-slides`) or gestures at one
("the transcribe thing keeps failing"). Resolve it to a directory:

```bash
ls -d "$HOME"/.*/skills/<name> "$HOME"/.*/plugins/*/skills/<name> \
      .*/skills/<name> ~/.skill-vault/*/<name> 2>/dev/null
```

Read the whole target — `SKILL.md` plus every bundled reference and script. You
cannot judge whether a section is dead weight without knowing it exists.

Note the **home directory**: the directory the skill lives in (or its skills
root — whatever this host calls it). Step 7 puts that under version control.

Targets other than skills work the same way: a slash command is its markdown
file, an MCP server is its tool surface plus config entry, a `CLAUDE.md` is
itself, an artifact is its source HTML. The mining is identical; only the
"what can I edit" surface changes.

## Step 2 — Load the ledger

State lives at `~/.claude/skill-improver/<target>/`:

```
ledger.md        every finding ever raised, with its verdict
snapshots/       pre-change copies, only when the home has no git
```

Read `ledger.md` before analysing. It exists to stop you re-proposing what the
user already declined — a reviewer that resurfaces the same rejected idea every
month trains the user to stop reading the table. It also tells you which past
edits were meant to fix what, so you can check whether they actually did.

Format and lifecycle: `references/ledger.md`. Create the directory and an empty
ledger on first run.

## Step 3 — Find the sessions

```bash
python3 <skill>/scripts/find_sessions.py <target> --limit 12 [--since YYYY-MM-DD]
```

It scans `~/.claude/projects/**/*.jsonl` for four traces of use — the Skill tool,
a slash command, a read of the skill's `SKILL.md`, an `mcp__<name>__` tool call —
and reports which matched, newest first. Matching is broad on purpose; a `git
log` line mentioning the skill's name will occasionally match. Discard those in
the next step rather than tightening the search, because a missed real usage
costs more than a discarded false positive.

Pick how many to mine. 8–12 episodes is usually enough for patterns to repeat;
below 4 you are looking at anecdotes and should say so in the table. If the skill
has barely been used, that is itself the finding — report it and ask whether the
user wants a trigger audit (Step 9) instead of a usage review.

## Step 4 — Extract the episodes

```bash
python3 <skill>/scripts/extract_usage.py <transcript.jsonl> <target> \
        -o <workdir>/ep-<N>.md --max-turns 12
```

Use a scratch directory for the extracts. Each file gets a metrics header (active
wall clock with idle gaps separated out, output/fresh-input/cache token split,
tool-call histogram, error and interruption counts) and then the trace: user
turns, Claude's text, tool calls with truncated inputs, tool results, and any
interruption or permission denial.

Read the extracts. Do not summarise them first and analyse the summaries — an
ablation on exactly this setup found that a reviewer with raw traces beat one fed
LLM-written summaries of the same traces, and the summaries recovered none of the
lost signal. The value is in the small surprises, and summarisation is precisely
the operation that deletes small surprises.

For long or numerous episodes, delegate the reading to parallel subagents — one
per episode, each returning findings in the Step 5 shape with quotes. Below
about three episodes the coordination costs more than it saves; just read them. Give each
subagent the target's `SKILL.md` too, so it can tell "the model improvised" from
"the model followed the skill and the skill was wrong".

## Step 4.5 — Check the perishable claims

Before you read a single transcript, take the skill's factual assertions and run
them against the thing they describe.

This is the one class of defect the transcripts cannot show you. A skill that
says a flag exists, a service is not running, a binary is missing, a directory
has one name — states it once, and from then on every session reads it and
believes it. Nothing retries, nothing errors, nobody corrects course. The
episodes are silent because the model did what it was told and the instruction
was wrong. Mining friction will never surface it; only asking the world will.

It has been the single highest-value step on every target where it was run.
`/codex` documented `--full-auto` through nine invocations after the flag was
removed — `codex exec --help` said `error: unexpected argument`. The `aarni`
skill said in bold that backups were installed but unscheduled and to report
them as broken; both systemd timers were active and had run ten hours earlier.

So: list every claim in the file that can rot, then check it.

- versions, flags, model names, CLI surfaces → run `--help`, run `--version`
- "X is not installed", "Y is not scheduled", "Z is stopped" → look on the box
- counts, inventories, tables of what exists → enumerate the real thing
- paths and directory names → `ls` them
- "the config lives at …", "there is no …" → resolve it

Two rules keep this honest. **A claim you cannot check is not a finding** — say
it is unverified and move on. And **check the negative assertions hardest**:
"there is no CLAUDE.md", "no timer is active", "it needs gum" — a sentence
telling the model something is absent is the one nobody ever tests, and the one
that ages worst.

Findings from this step are usually red and usually one-line content fixes. They
carry no `k/n`; cite the command you ran and what it returned.

## Step 5 — Analyse

You are looking for the gap between what the skill says and what actually
happened. `references/signals.md` is the full catalogue with worked examples —
read it before your first analysis pass. The short version, by family:

- **Friction** — retries, tool errors, permission denials, interruptions, the
  user correcting course right after the skill loaded.
- **Waste** — re-derived facts the skill could have stated, re-read files,
  re-written throwaway helpers, sections loaded but never used, tool output
  pulled in bulk and then mostly ignored.
- **Drift** — a documented rule the model reliably ignores. This is a signal
  about the *skill*, not the model: a rule violated in most episodes needs
  structural enforcement or deletion, not louder capitals.
- **Gaps** — the same edge case handled ad hoc every time; a step the model
  always adds that the skill never mentions.
- **Dead weight** — a section no episode ever needed. Skills pay their token
  cost on every single invocation, so an unused section is a permanent tax.
- **Staleness** — a claim that was true when written and is not now. Step 4.5
  finds these; carry its results into the triage table alongside the rest.
- **Under-service** — the run was quick and clean and the result was wrong,
  unverified, or quietly narrower than what was asked. Look for it deliberately:
  every other family here is a way of noticing that the skill made the model do
  too much, and a review that only ever finds too-much will, over enough
  rounds, tune a skill into one that finishes fast and checks nothing.

Two disciplines that decide whether this is worth running twice:

**Count the episodes, not the impressions.** Every finding carries `k/n` — seen
in k of n mined episodes. That number does the triage work and keeps you honest
about a vivid one-off.

**Fix at the lowest level that can express the fix.** A stale fact is a one-line
content fix, not a workflow redesign. Reach for restructuring only when a cluster
of failures survives the cheaper fix.

**Ask whether the skill could have prevented it at all.** Some failures in the
episodes are the task being hard, the model having a bad day, or a tool being
broken — they would have happened against any version of this skill. Those are
not findings, and mining them produces edits that add weight and change nothing.
The test is concrete: name the sentence that would have prevented it. If you
cannot, drop it.

### The counterfactual pass

Signals catch what went wrong line by line. Once per run, do one pass that
catches what no line-by-line reading can: take two or three of the mined
episodes and sketch **the shortest run that would have reached the same result**
— the four or five steps a model holding a perfect version of this skill would
have taken. Diff that against what the episodes actually did.

The gap is where the structural findings live, and they are the ones worth the
run: a step order that makes the model read the file twice, three steps that
should be one script, a decision the skill asks the model to make that it could
have made for it, a middle section that turned out to be reference material the
model consulted once. None of these show up as friction in any single episode,
because nothing went wrong — it just cost more than it had to.

## Step 6 — Triage

| Tier | Meaning |
|------|---------|
| 🔴 Red | Costs correctness or real user time on most runs. Wrong instructions, contradictions, a rule broken in the majority of episodes, a step that reliably fails. Usually `k/n ≥ ½`. |
| 🟠 Orange | Recurring friction or waste. Repeated across ≥2 episodes but survivable — re-derivation, a missing edge case, an unbundled helper, avoidable tokens. |
| 🟡 Yellow | Polish and single-episode observations. Dead sections, wording, description tuning, plausible-but-unconfirmed hypotheses. |

Rank within tier by evidence strength, then by how much the fix costs.

Keep red and orange to about five between them. A table of a dozen weighty
findings gets none of them applied — the user skims, feels the cost, and defers
the lot. Push the rest down to yellow or into the ledger as deferred; they will
still be there next run, with more evidence behind them. Yellows can run longer,
since they are cheap to batch-approve, but the moment a yellow needs a paragraph
of justification it was never yellow.

## Step 7 — Present

Print the findings in the terminal. This is the user's decision surface, so it
has to be scannable in one pass. Three weights carry three kinds of information:
a boxed title says what is wrong, plain text says how often, an italic line says
what to do about it.

Open with a one-line legend, then one block per finding, ranked. No prose
paragraphs above the list.

Emit exactly this markdown (the four-backtick fence below is only so you can see
the source — your real output is not fenced, or none of it renders):

````markdown
🔴 correctness or user time, most runs · 🟠 recurring friction · 🟡 polish, single episode

🔴 F1 │ `sleep-polled a backgrounded codex → blocked`            8/14
      │ *Add "Running it": launch with run_in_background, then stop.*
      │ *The completion notification wakes the session.*

🟡 F6 │ `stated default terra/medium nearly always overridden`  13/14
      │ *Your call: restate the default as sol/high, or keep*
      │ *terra/medium as the unspecified-run fallback.*
````

Four mechanics keep it from falling apart in the renderer:

- Markdown collapses runs of spaces, so pad the evidence column and indent the
  continuation gutter with non-breaking spaces (U+00A0), never ordinary ones.
- End every line with two trailing spaces, or the renderer joins them into one
  paragraph and the whole shape collapses.
- Don't nest inline code inside an italic span. It is the one combination that
  renders inconsistently; rephrase so the command sits in a plain-italic line.
- Keep each fix to one or two lines. A fix that needs more is two findings.

Below the blocks, give the evidence for anything red — quote the moment, cite the
episode — and show the before/after of the edit.

If there are more than roughly eight findings, or the diffs are too long to read
comfortably in a terminal, **ask** whether the user wants a self-contained HTML
review page instead — per-finding accept/reject/comment with full diffs, exporting
a summary to paste back. Default to the terminal; the page is for when the
terminal genuinely stops working as a review surface.

**Always close by asking which findings to act on.** The table is not the
deliverable; the decision is. Ask for approval by id or tier ("all red, F4, skip
the rest"), and say plainly if any finding needs an answer from the user rather
than a verdict — a question you cannot decide for them blocks its own edit, so
surface it here rather than guessing later.

Invite comments while you are asking. A "no, because…" is the most valuable
output of the whole run: it tells the next run what the skill is actually for,
and it belongs in the ledger verbatim.

## Step 8 — Apply

Put the change under version control before making it — but resolve where the
file *really* lives first. Skill and command directories are commonly a tree of
symlinks into a registry that some installer populates from a source repo, and
each of those layers is a different answer to "where do I commit":

```bash
real=$(readlink -f <target-file>)          # the file the edit actually lands on
git -C "$(dirname "$real")" rev-parse --show-toplevel 2>/dev/null
```

Two traps this avoids, both of which silently produce a useless baseline:

- **Committing the symlink.** A repo initialised over the link directory stores
  the link target — a few dozen bytes — so `git status` reports clean no matter
  how much the content changed, and the "baseline" restores nothing.
- **Editing a generated copy.** If the resolved file is a copy that an installer
  writes from a source repo, the edit is live now and gone at the next sync.
  Search the source repo for a file of the same name; if one exists and matches
  the pre-edit content, that is the real target. Apply there, then let the
  installer propagate — or copy across and commit both.

Before copying an edited file back to a source repo, diff it against the source
to confirm the only differences are your own edits. A registry copy that had
already drifted will otherwise lose that drift silently.

If it is not a repo, offer to initialise one:

> "`<skills root>` isn't a git repo. Want me to `git init` it so every
> skill edit from here on is tracked and revertable? I'll commit the current
> state first, then the changes."

If the user agrees: `git init`, commit everything as a baseline, then apply, then
commit the edits with a message naming the findings (`skill-improver(bento-slides):
F1,F2 — stop re-reading config; enforce snapshot via script`). If the user
declines, copy the target to `snapshots/<date>/` before editing.

Then apply the approved edits, and only those. Two rules about *how*:

**Edit incrementally; never regenerate the file.** Letting a model rewrite an
accumulated context artefact wholesale is a documented way to collapse it — the
rewrite drops the hard-won specifics and lands below where it started. Make each
approved finding a targeted edit.

**Watch for brevity bias.** The pull toward short, generic, tidy instructions is
strong and it deletes exactly the domain-specific detail that made the skill
worth having. Removing a section because no episode used it is good. Removing a
sentence because it felt verbose is how skills get worse while looking cleaner.

When you bundle a repeated helper into `scripts/`, run it once to confirm it
works before pointing the skill at it. A broken bundled script is worse than the
improvisation it replaced.

**Write down what should change.** You cannot measure an edit from inside the
run that proposed it; the evidence lands in the episodes that come after. So for
each applied finding, record in one clause what a later run should be able to
see — "no episode should re-read the config after Step 3", "the snapshot should
appear in every episode, not two thirds". That clause is what makes Step 9 a
check rather than a fresh act of interpretation.

## Step 9 — Record, and check the last round

Append every finding to the ledger with its verdict — applied, declined (with
the user's reason), or deferred. Declined findings stay declined.

Then close the previous loop: for each finding applied in an earlier run, read
the observable it was recorded with, look only at the episodes that happened
*after* it landed, and say plainly whether the problem stopped. A self-improvement loop with no feedback on its own edits is just a
change generator. Report the honest answer, including "no episodes since — can't
tell yet".

## Optional — Trigger audit

If the complaint is "it never fires" rather than "it fires and misbehaves", the
description is the thing to fix, and the evidence is different: sessions where
the skill *should* have triggered and didn't. Search transcripts for the skill's
subject matter without its usage markers, and read what the user actually typed.
Real user phrasings beat invented test queries.

The description is the only part of a skill always in context, so it is doing two
jobs: saying what the skill does, and saying when. Models undertrigger skills, so
make the "when" concrete and a little pushy — name the phrasings, the file types,
the situations, including the ones where the user won't use the skill's own
vocabulary. `skill-creator` (in the vault under `anthropic/skills/skills/`) has a
scripted description optimiser if you want the measured version.

## Guardrails

**Don't let the improver optimise the measure.** Token counts, tool-call counts
and duration are proxies. A skill that runs faster because it now skips a check
the user needed has gotten worse on the only axis that matters. When a metric and
the user's stated intent disagree, the intent wins.

**Evidence outranks eloquence.** A well-argued finding with no transcript behind
it is yellow at best, and should be labelled a hypothesis.

**One target per run.** If the analysis turns up something about a *sibling*
skill, note it for the user rather than editing outside the approved target.

**The user's declines are data, not obstacles.** Repeated declines in one area
usually mean you have misread what the skill is for. Say so in the next run.
