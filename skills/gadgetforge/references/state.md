# Project state and evidence

Use `python3 <skill-dir>/scripts/forge.py --project <project-dir> COMMAND` below. `.gadgetforge/workflow.json` is the project's pinned phase definition. `.gadgetforge/project.json` holds the selected scope, candidate hashes, evidence, milestone decisions and feedback. Track both files, preview snapshots, native sources and supporting decisions in the gadget repo. Use scoped Git commits for coherent revisions. The validator evaluates the working files directly, including local edits.

The phase graph expresses acceptance dependencies. A candidate may be explored while upstream work is open, but capture waits for its applicable prerequisites. The current workflow adds a firmware dependency to release only for `--factory-programming`. Earlier pinned workflows retain their original dependency definitions. The validator computes each phase's state whenever asked:

| State | Meaning |
| --- | --- |
| Ready | Applicable prerequisites are current and accepted. |
| Blocked | At least one applicable prerequisite needs attention. |
| Needs checks | A current candidate exists and named evidence is missing, unsuccessful, or out of date. |
| Awaiting review | Required evidence is current and the milestone awaits the user's decision. |
| Accepted | Applicable evidence and milestone decisions match the current candidate. |
| Stale | The captured candidate no longer matches a tracked input, output or prerequisite. |
| Not applicable | The selected scope excludes this work. |

- Read `status --json` for required output and check names. Capture with `capture brief --output brief=brief.md --output visual=concept.svg`. Add `--uses path` for every consequential source outside the accepted prerequisite outputs, including a selected recipe, BOM observation or manually maintained constraint. For multiple source files, use repeated flags or track a manifest and register its constituent files explicitly. A filename mentioned inside Markdown is not automatically tracked.
- Capture later PCB milestones as successive native snapshots. For example, keep `pcb/review-placement.kicad_pcb` as arrangement evidence and route from a working copy. Rewriting that same placement snapshot during routing would invalidate routing's prerequisite. If routing reveals an actual placement change, return to arrangement deliberately. Capture current work after the change.
- Run appropriate tools or perform the scoped review before recording `evidence brief direction --result pass --note "Reviewed the brief against the scoped goal and concept"`. Add `--report reports/brief-review.md` when there is a report. Record `fail` or `unknown` where appropriate. Evidence is an assertion about work actually done. A named check can rely on tool output, a qualified manual comparison or external evidence. Record the method, limits and artifact identities. The runner checks the binding and presence of evidence, not its engineering truth.
- For a human milestone, show the candidate visual, conditions and consequential tradeoffs. A clear decision in chat is sufficient. If the user explicitly settles a tradeoff and the resulting candidate matches that direction, carry the decision forward. Ask again only when the candidate introduces a new consequential choice or agreement is unclear. Once the phase checks pass, the agent records the decision as ordinary phase evidence using `evidence brief review --result pass --note "User agreed in session to the current brief and centered display"`. Use the actual decision and matching candidate. The user can also return a milestone decision through the board. Order authorization is a separate decision on the exact order.
- A changed source, report, required scope or dependency can reopen downstream work. Use the first stale phase and its reason to calculate the actual engineering impact. Separate ordinary log entries from new consequential decisions. If a check cannot run yet, keep the corresponding claim open. Pick a qualifying alternate if available.
- `board` generates the HTML from project records. `import-feedback <saved-html-or-json>` copies the explicit feedback items into the inbox. `feedback` shows pending and conflicted items. Resolve them with `resolve-feedback <id> --note "<how it was handled>"` after addressing or consciously deferring the intent. Imports never change the engineering artifacts or grant an approval on their own.

Recognize completion from its evidence. Design complete covers the accepted design scope. A manufacture-ready package adds a consistent release manifest. An agreed order, shipment and unit-level physical validation are separately recorded project events. Keep these distinctions on the board. Optional physical work does not hold design/package work open.
