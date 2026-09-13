# cad-studio: storage, iteration loop, outputs

Date: 2026-09-13. Extends `skills/cad-studio/` (router skill). Status: approved in brainstorm.

## Storage

- Root `~/Designs/`, overridable by `CAD_STUDIO_HOME`.
- Layout `~/Designs/<type>/<name>/`. `<type>` is suggested from the brief (furniture,
  buildings, prints, vehicles, sites …), open vocabulary, never enforced.
- First reply of a new design proposes the path; nothing is written until the user
  accepts. A new `<type>` folder is created on acceptance. An existing folder whose
  `design.md` names the same object is reused.
- `design.md` is the index and the only file the router reads to resume: authoritative
  file, derived files with dates, brief, provenance ledger, changelog.
- `list.sh` beside `SKILL.md` finds every `design.md` under the root (any depth) and prints
  `type/name · last change · authoritative file`. The router uses it at "inspect" so
  cross-design references resolve by name.
- No git per design. Changelog is the history, newest first.

## Loop

```text
brief → suggest path, accept → iterate … → done signal → suggest outputs → write → update design.md
```

- Brief: ask only what changes the shape (object, 1–2 known dimensions, purpose).
  Everything else is an ASSUMED ledger entry.
- Iterate: parameter edits to the authoritative source + a preview. No final exports during
  iteration; the preview artifact is overwritten each round. One changelog line per accepted
  iteration.
- Done signal ("good", "that's it", "export", "send me the…"): a named output is generated
  directly; otherwise the skill suggests 1–3 outputs from what the design is, waits for the
  pick, generates — printable part → STL; timber build → cut list +
  drawings; furniture → drawings + STEP; placement study → renders — then "anything else?".
  No level/tier menu is shown to the user. Fidelity levels remain the router's internal
  reasoning aid only.
- Outputs go to `<design>/outputs/` and `<design>/drawings/`; each is recorded under
  Derived in `design.md` with a date so edits know what is stale.
- Resume: read `design.md`; never rely on conversation memory.

## Preview

Preference: live browser viewer from a vaulted skill (Nimbalyst / kernelCAD) if installed →
PNG views rendered from the model and opened → dimension table. State which is in use the
first time per design; user can override. The skill owns no viewer code.

## Out of scope

Own viewer, own export implementations (routed specialist skill produces files; an
unavailable output is named with the reason), per-design git, cataloguing beyond `list`.

## Consequences for the skill files

- `SKILL.md`: add storage section, done-signal behaviour, preview preference; remove the
  fidelity table from user-facing behaviour (keep as internal heuristic in a reference).
- `references/project-layout.md`: root becomes `~/Designs/<type>/<name>/`.
- New `list.sh`.
- Provenance: INFERRED never feeds fabrication; promote to KNOWN or ASSUMED first.
