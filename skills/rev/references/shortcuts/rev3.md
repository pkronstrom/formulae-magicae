---
name: rev3
description: Deep 3-agent review — code quality + design docs + architecture via /review-work
---

Use the bundled `review/SKILL.md` playbook to review recent changes. Run Step 2.5's preflight and confirm before dispatching. Skip Step 2 — go directly with **Deep** mode (3 agents: code quality + design doc alignment + architecture), using `gpt-6-astra` at `high` reasoning effort.

This is the security-audit / pre-merge gate: three Astra agents, so it is the expensive mode — reach for it on critical or wide-blast-radius changes, not routine diffs. For complex bug hunting on a narrow diff, override the code-quality agent to `xhigh` rather than raising all three.
