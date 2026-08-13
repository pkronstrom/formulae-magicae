# Hawk-side transition plan

This document deliberately plans the later Hawk work without changing the
`hawk-hooks` repository during the Formulae Magicae migration.

## Intended end state

- Formulae Magicae is the canonical home for the public, portable custom skills in
  this repository.
- Hawk keeps the Hawk authoring/management skill and any components that exist only
  to operate Hawk itself.
- Hawk can install Formulae Magicae from its Git repository as an optional package;
  the collection is not duplicated as built-ins.
- Private or organization-specific skills move separately to a future private
  repository with the same `skills/<name>/SKILL.md` convention.

## Proposed Hawk changes

1. Wait until Formulae Magicae has a reviewed, tagged release and the private-repo
   installation path works end to end.
2. Add a remote-package entry or documented `hawk install` command for
   `pkronstrom/formulae-magicae`, using its root `hawk-package.yaml`.
3. Verify that package installation preserves every skill's scripts, templates,
   references, executable bits, and bundled licenses.
4. Compare installed Formulae Magicae skills against Hawk's existing built-ins and
   remove only exact migrated duplicates. Keep the Hawk authoring skill in Hawk.
5. Update Hawk tests and documentation so they use an installed fixture/package
   rather than assuming the migrated skills exist in `builtins/skills/`.
6. Add an upgrade note for existing users: install Formulae Magicae, confirm the
   package is enabled for their hosts, then upgrade Hawk.
7. Run Hawk's full package, sync, CLI, and built-in regression suites before making
   the removal commit.

## Safety rules for that later change

- Make the Hawk transition in its own branch and commits; do not mix it with this
  repository's migration history.
- Do not remove a built-in until the remote replacement has a tested installation
  and rollback path.
- Preserve compatibility aliases where they cost little, but remove documentation
  that presents Hawk's registry path as a requirement of the portable skill.
- Keep the old built-ins available in the last pre-transition Hawk release/tag so
  users can roll back cleanly.

## Deferred catalog

`agent-team` and `agent-team-openspec` remain deferred. They need a separate
portability and product-boundary decision before they belong in Formulae Magicae.
Generic Hawk agents, hooks, commands, and the Hawk authoring skill are explicitly
out of scope for this repository.
