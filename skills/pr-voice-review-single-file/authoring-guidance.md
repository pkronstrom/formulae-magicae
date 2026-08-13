# PR walkthrough authoring guidance

Read this before authoring the walkthrough. It defines the narration, review depth,
triage, overview, ordering, and wrap-up rules used by this standalone skill.

## Narration

`seg.speech` must stand alone: explain what the file does, where it sits in the
system, and why it changes in this PR. When a small patch changes a large file, read
the file itself as well as the patch so the explanation has enough context.

- Put the conclusion in the first sentence.
- Keep a guided observation at 40 spoken words or fewer.
- Use 60–90 words when file-level speech carries the whole file.
- Keep answers and follow-up investigations at 80 spoken words or fewer.
- Split two observations into two notes instead of making one long speech block.
- Put exact identifiers, line references, and qualifications in card `text`; put the
  plain-language point in `speech`.
- Translate identifiers into concepts instead of spelling punctuation aloud.

## Review lens

Ask for one lens before authoring and keep it fixed for the artifact:

| Lens | Unit | Coverage |
|---|---|---|
| `guided` | observation anchored to lines | every observation gets a card and speech |
| `focused` | detailed on risky files, higher-level elsewhere | every observation gets a card; only crucial files get note speech |
| `architect` | file anchored to the system | 60–90 word file speech; only 0–3 cards worth stopping on; no note speech |

Architect is not truncated guided narration. It orients the reviewer to every file
from the system level while they read the lines themselves.

## Triage and overview

Triage by risk, not line count:

- `crucial` and `normal`: one or more notes with natural line anchors. Use one note
  per observation.
- `skim`: one role line; read the patch only if something looks suspicious.
- `ignore`: the role line is the full coverage.

Segment 0 is the overview and has no selected file. Write it in this order:

1. The problem before the PR, in plain language.
2. The shape of the fix and why it resolves that problem.
3. The triage: risky files, accepted trade-offs, open threads, and what to watch.

Write the problem and fix without file paths, identifiers, or symbol names. Use the
ticket when available; otherwise use the PR body and diff. Include a small inline SVG
only when the change's flow materially benefits from a diagram.

Judge the overall approach once. A proportionate change gets one short verdict. A
negative verdict must name a concretely smaller alternative and what it removes; if
you cannot name the smaller version, do not claim the PR is over-engineered.

## Scope and patch selection

Match the artifact to the exact GitHub diff the reviewer supplied:

| Input | Scope |
|---|---|
| `…/pull/714` or `…/pull/714/files` | Whole pull request |
| `…/pull/714/changes/<sha>` | Only that commit |
| `…/pull/714/files/<base>..<head>` | That comparison range |
| “what changed since I last looked” | Last review's `commit_id` through the current head |

Scope both the file list and every patch. Never pair a commit-level file list with
the pull request's cumulative patches: observations and line anchors would point at
content the reviewer cannot see. Say the scoped file count explicitly so the reviewer
can confirm you are looking at the same diff.

## Story order

Order segments as a story rather than a risk ranking. Start where the feature enters,
then follow its flow through wiring, core logic, shared rules, persistence or sync,
and finish with the tests that prove each layer. Each file's `role` should explain why
it follows the previous file.

## Wrap-up

Treat saved comments and flags as a backlog. A flag means “worth more attention,” not
automatically “post a review comment.” Present each item with three choices:

- `comment`: prepare it as an inline PR review comment.
- `dig`: investigate it and return with a diagnosis and concrete proposed change.
- `drop`: mark it resolved or not important enough to pursue.

The static artifact cannot submit a review itself. When the annotated file returns,
read the embedded feedback, settle every flag, show the resulting notes, and obtain
confirmation before submitting anything to GitHub.
