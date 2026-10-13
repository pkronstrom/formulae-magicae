---
name: pr
description: Create, monitor, and babysit pull requests — CI checks, reviews, and auto-fixes
---

# PR

All-in-one PR command: create new PRs or babysit existing ones.

## Model defaults

Run PR creation and monitoring in the active session; `/pr` does not switch that session's model. Use `gather` to inspect without implementing fixes; `auto-fix` authorizes the documented fix, commit, and push loop.

When delegating implementation, follow the installed `/codex` or `/claude` command rather than copying its entire model list here. Checked 2026-10-13:

| Task | Codex | Claude Code |
|------|-------|-------------|
| Routine CI or review fix | `gpt-6.1-sol` at `medium` | `opus` (5.5) at `medium` |
| Review a proposed fix | `gpt-6.1-sol` at `high` | `opus` at `high` |
| Hard reasoning or security-sensitive fix | `gpt-6-astra` at `high` | `opus` (5.5) at `high` |

Honor explicit model/effort choices and account restrictions. Monitoring polls use `gh`; they do not need a new model run. Use `/rev` for a full review and its roster definitions for reviewer selection.

## Step 1: Determine Context

```bash
git branch --show-current
gh pr view --json number,url,title,state,baseRefName 2>/dev/null
gh repo view --json defaultBranchRef --jq '.defaultBranchRef.name'
```

Parse the arguments (if any) to determine intent:

| Argument | Intent |
|----------|--------|
| (none) | Ask user what to do |
| `create` | Create a new PR |
| `auto-fix` | Babysit current branch PR in auto-fix mode |
| `gather` | Babysit current branch PR in gather mode |
| `<number>` | Babysit that PR number |
| `<url>` | Babysit that PR URL |
| `<number> auto-fix` | Babysit that PR in auto-fix mode |
| `<number> gather` | Babysit that PR in gather mode |

### If no arguments:

- If current branch has no PR → ask: "No PR found. Create one?"
- If current branch has a PR → ask: "PR #N exists. Babysit it?"

Use the PR's `baseRefName` for an existing PR and the repository's default branch for a new PR, unless the user supplies another base. If on that base branch with no arguments, stop and tell the user to switch to a feature branch or pass a PR number. Do not assume the base is named `main`.

---

## Create Flow

### Gather info

```bash
BASE=$(gh repo view --json defaultBranchRef --jq '.defaultBranchRef.name')
git log --oneline "$BASE"..HEAD
git diff --stat "$BASE"..HEAD
```

Use the chosen base instead of the default in those commands when the user requested one. If there are uncommitted changes, ask whether to commit first.

### Ask options (one at a time):

1. **Draft or ready?**
   - Draft PR (default — safe for early feedback)
   - Ready for review

2. **Supervisor notes?**
   - Ask: "Any comments to add to the PR? (Goes in as-is under 'Supervisor notes')"
   - If yes: capture exactly what the user types, no rewording or summarizing
   - If no: skip

3. **Babysit after creation?**
   - Yes → ask babysit mode (auto-fix or gather)
   - No → create and stop

### Push and create

```bash
git push -u origin HEAD
```

```bash
# Draft:
gh pr create --draft --base "$BASE" --title "<title>" --body-file <body-file>

# Ready:
gh pr create --base "$BASE" --title "<title>" --body-file <body-file>
```

Write the exact PR body to a file and pass it with `--body-file` to preserve newlines and avoid shell interpolation.

### PR body format

```markdown
## Summary
- <1-3 bullet points describing what changed and why>

## Supervisor notes
> <user's comments verbatim, if provided>

## Test plan
- [ ] <how to verify this works>
```

Omit the "Supervisor notes" section entirely if the user had nothing to add.

Show the PR URL. If not babysitting, stop here.

---

## Babysit Flow

### Resolve the PR

In order of priority:

1. PR number or URL from arguments
2. PR on current branch (from Step 1)
3. If neither found, stop and tell the user

Confirm: "Babysitting PR #N: <title> (<url>)"

### Determine mode

If mode was passed as argument or already chosen during create flow, use it. Otherwise ask:

- **Auto-fix** — automatically fix test failures and address review comments, commit and push
- **Gather** — collect all issues and present them for review before any changes

### Start monitoring

In an interactive Claude Code session with `/loop` available, start a `/loop 5m` cycle. This is a Claude Code scheduling facility, not a feature of `gh` or Codex CLI, and requires the session to remain open. Save the scheduled job ID and cancel it when an exit condition is reached; returning a message alone does not cancel a recurring job.

On a different host, use its supported scheduling/wait mechanism if one is available and the monitoring request authorizes it. Otherwise perform one complete check and report that continuous monitoring is unavailable in this host; provide the next manual check rather than claiming a loop is running. Do not create an unattended daemon or detach a shell loop to emulate session scheduling.

#### Each iteration:

1. **Check CI status:**
   ```bash
   gh pr checks <pr-number> --watch=false
   ```

2. **Check review comments:**
   ```bash
   gh api repos/{owner}/{repo}/pulls/{pr-number}/reviews
   gh api repos/{owner}/{repo}/pulls/{pr-number}/comments
   ```
   Track which comments have already been seen to only report new ones.

3. **If all checks pass and no blocking reviews** — report success and stop.

4. **If a CI check failed:**
   - Inspect the failed check logs:
     ```bash
     gh run view <run-id> --log-failed
     ```
   - Determine: is this a **flaky test** or a **real failure**?
   - If flaky: rerun the failed jobs:
     ```bash
     gh run rerun <run-id> --failed
     ```
   - If real failure, behavior depends on mode:
     - **Auto-fix:** fix the bugs, commit, push, continue the loop
     - **Gather:** add failures to the issues list and continue monitoring

5. **If new review comments found:**
   - Summarize new comments (reviewer, file, comment)
   - Flag actionable items vs informational comments
   - If Greptile or bot reviews: highlight any blocking suggestions
   - **Auto-fix:** address actionable comments, commit, push
   - **Gather:** add to the issues list

#### Loop exit conditions:

- All CI checks green + no unresolved blocking reviews
- User manually stops
- 10 iterations without resolution (ask user how to proceed)
- **Gather mode:** also stop when new issues are found and present the full list

---

## Wrap-up

### Auto-fix mode (PR is green):

```
## PR Status: Ready

**PR:** <url>
**Checks:** All passing

### Issues caught and fixed:
- <description of bug/test failure and how it was fixed>
- <description of review feedback and how it was addressed>

### Flaky tests rerun:
- <test name> (rerun N times)
```

### Gather mode (issues collected):

```
## PR Status: Needs attention

**PR:** <url>
**Checks:** <passing/failing>

### CI failures:
- <test name> — <failure reason + log excerpt>

### Review comments to address:
- <reviewer>: <file:line> — <comment summary>

### Flaky tests rerun:
- <test name> (rerun N times)
```

If no issues were caught, just confirm the PR is green and ready to merge.

## Examples

```
/pr                        # asks what to do based on context
/pr create                 # create a new PR
/pr auto-fix               # babysit current branch PR, auto-fix mode
/pr gather                 # babysit current branch PR, gather mode
/pr 142                    # babysit PR #142, asks mode
/pr 142 auto-fix           # babysit PR #142, auto-fix
/pr https://github.com/org/repo/pull/142
```
