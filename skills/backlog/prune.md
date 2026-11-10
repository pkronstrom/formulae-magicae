# Prune

Replaces all `done` and `dropped` tasks with one summary. Only when the user asks.

1. Note the commit: `git rev-parse --short HEAD`.
2. Write `backlog/archive/<highest pruned ID>-pruned-<date>.md`, through a cheaper
   subagent if you can start one (give it the file list and this format):

   ```markdown
   # Pruned <date>

   Originals: `git show <commit>:backlog/<file>`

   ## 0007 Fix login redirect (done)
   The outcome in a sentence or two. Decisions worth keeping.
   ```

3. `git rm` the pruned files and commit them with the summary.
