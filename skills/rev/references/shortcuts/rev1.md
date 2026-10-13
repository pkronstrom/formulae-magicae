---
name: rev1
description: Quick 1-agent code quality review via /review-work
---

Use the bundled `review/SKILL.md` playbook to review recent changes. Run Step 2.5's preflight and confirm before dispatching. Skip Step 2 — go directly with **Quick** mode (1 agent: code quality only), using `gpt-6.1-sol` at `high` reasoning effort.

This is the daily-driver review: one Sol 6.1 agent, high effort. Escalate to `/rev3` (or a `gpt-6-astra` override) only for security-critical or hard-to-reason-about diffs.
