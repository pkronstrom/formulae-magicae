---
name: review-work
description: Compatibility entry point for the review playbook bundled with Rev
---

Locate the installed `rev` skill, then read its `review/SKILL.md` playbook. In the playbook, `<skill-base>` means the absolute path to that skill's `review/` directory.

Pass `$ARGUMENTS` unchanged to the playbook as scope, mode and roster. Preserve the original mode names (`quick`, `focused`, `deep`, `full`, `panel`, `custom`); do not route these through `/rev`'s compact numeric-mode parser. No separate `review-work` skill is required.
