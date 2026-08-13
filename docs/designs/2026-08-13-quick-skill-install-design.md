# Quick skill installation design

**Status:** Approved for implementation.

## Goal

Make the shortest supported installation path obvious to a reader who has just
opened the repository, especially a Codex user, without adding an installer script
or another package format.

## README structure

Add a compact **Quick install** section immediately before the existing detailed
installation material. It provides copy-pasteable routes in this order:

1. **Codex** — show `$skill-installer` prompts for one named formula and for the
   complete `skills/` catalog from `pkronstrom/formulae-magicae`. Note that the
   private repository requires existing GitHub credentials and that newly installed
   skills become available on the next turn.
2. **Claude Code** — show the two existing marketplace/plugin commands for the
   complete collection, plus the existing one-skill form.
3. **OpenSkills** — show the existing SSH installation command as an optional
   cross-host route.
4. **Hawk** — show only a command verified against Hawk's current CLI. If the
   current CLI does not expose an unambiguous install command for this repository,
   link to `hawk-package.yaml` and the Hawk transition plan instead of inventing one.

Keep the longer installation sections below for Spellbook migration, manual
symlinks, host directories, and explanatory detail. Remove duplicated command
blocks where the quick section makes them unnecessary, but retain information that
is not present in the quick path.

## Constraints

- Documentation only: no shell installer, bootstrap command, workflow, or manifest
  changes.
- Commands must be directly copyable and must not imply that this private repository
  can be accessed without GitHub authentication.
- Prefer native host mechanisms. OpenSkills remains explicitly optional.
- Do not claim support for a Hawk command that the checked-in CLI does not provide.

## Verification

- Run the repository documentation/contract tests.
- Validate that every named skill in the Codex all-skills prompt matches a directory
  under `skills/`.
- Check every displayed repository name, marketplace name, and plugin name against
  the manifests.
- Inspect the README section to ensure the quick path precedes detailed material and
  does not duplicate contradictory instructions.
