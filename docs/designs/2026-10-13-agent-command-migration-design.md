# Portable agent commands and review suite

Move the updated Codex, Claude, PR and Rev workflows from Arcanae to four canonical Magicae skills. Magicae owns portable implementation and fixes; Arcanae keeps private workflows and documents this migration. Preserve the selected model defaults and explicit overrides.

## Background completion

A long-running CLI does not guarantee that its caller is resumed. Use background execution only through a host that returns a task handle and provides a completion notification or a wait operation. Retain the handle and wait for process completion. Without that facility, keep the invocation attached. An unrelated question may be answered while useful work continues; never end the task just because a subprocess was launched. Always inspect exit status and final output. Completion is distinct from success. Apply the same rule to review dispatch jobs.

## Packaging

Publish `skills/codex`, `skills/claude`, `skills/pr` and `skills/rev`. Each is independently installable with a local license. Rev includes its existing review playbook, dispatcher, prompts, schema, references, preflight helper and shortcut definitions. Relative paths resolve inside that bundle; no sibling installed skill is required. Preserve rev1/2/3 and panel shortcuts through lightweight command wrappers, while `/rev <mode>` works with an isolated Rev install.

Remove Hawk target-host frontmatter from skill bodies. Replace personal funding assumptions with account-dependent guidance. Document PR's Claude Code `/loop` dependency and an explicit manual-check fallback, and obtain the base branch from the PR/repository instead of hardcoding main. No new scheduler or agent orchestration framework is introduced.

## Migration and validation

Update Magicae's README, complete/individual plugin listings, Hawk manifest and catalog checks. Run isolated dispatcher fixtures with fake CLIs to validate model/effort routing, failed executions and rejected outputs without billing providers. Verify independent Rev bundle paths and scan moved files for private paths/credentials. Only after those checks, refresh the live registry and retain Arcanae/Hawk compatibility mirrors with a pointer to the public canonical source. Preserve activation, installed symlinks, package ownership, and unrelated edits. Keep pre-change copies before refreshing mirrors. The user authorized a public-release audit followed by committing and pushing these changes.
