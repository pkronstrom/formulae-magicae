---
name: gadgetforge
description: Use when designing a physical electronic gadget or resuming an existing gadget project, from product intent through parts, schematic, PCB, enclosure, firmware handoff and manufacturing. Supports design-only work, fabricated packages, and supplier delivery planning.
---

# Gadgetforge

Build the smallest design that can answer the next important question. Put product intent, native sources, prose decisions, checks and visual evidence in the gadget's Git project. A phase can produce several visibly provisional drafts. Accept one only against its current inputs and applicable checks. Old evidence remains useful history.

## Find the next work

1. Read [bootstrap](references/bootstrap.md) for a new or inherited project. On resume, run `python3 <skill-dir>/scripts/forge.py --project <project-dir> status`. Read pending feedback and actual source changes before repeating work. Reconcile accepted changes into their owned files and rerun status. A note alone leaves the current evidence in place.
2. Work from the first relevant state. Recapture stale work, supply missing checks, or take the named milestone to the user. For blocked work, follow the named prerequisite. Use the table below to load its guide. Candidate investigation may overlap phases. Capture and acceptance use the pinned prerequisites in the project's workflow file.
3. Record sources, a visual and check evidence. Use [state and verification](references/state.md) for commands, currentness, reviews and safe iteration. Refresh the [offline review board](references/project-board.md) for meaningful drafts and after decisions.
4. Let routine work advance on current passing evidence. Ask for human decisions at planning, arrangement and release and when a consequential choice exceeds granted authority. A clear decision in the session is enough. Record it with the current candidate's evidence and carry on. The user separately authorizes a specific order, if requested.

| When | Read |
| --- | --- |
| Idea, quick concept or delivery intent | [Product brief](references/phase-idea.md), [delivery route](references/phase-delivery.md) |
| Choose parts, qualify risks or simulate | [Architecture and feasibility](references/phase-architecture.md) |
| Estimate the delivered cost across manufacturers | [Manufacturer cost estimate](references/phase-pricing.md) after architecture, alongside feasibility |
| Agree responsibilities and physical/electrical interfaces | [Contracts and obligations](references/phase-contracts.md) |
| Schematic, board shape, placement or routing | [PCB](references/phase-pcb.md) |
| Rough packaging, existing case or final enclosure | [Enclosure](references/phase-enclosure.md) |
| Defined programmable hardware | [Firmware handoff](references/phase-firmware.md), then the sibling `gadgetforge-firmware` skill if implementation is requested |
| Release files, quotes or assembly scope | [Delivery](references/phase-delivery.md) |
| Physical work explicitly in scope | [Physical validation](references/phase-validation.md) |
| Adding a capability, workflow or recipe | [Maintaining Gadgetforge](references/maintaining.md#adding-a-capability) |

Start product form early. Reconcile the real PCB, enclosure and firmware interfaces before accepting the corresponding outputs. Feed supplier constraints into design early when delivery matters. For an existing object such as a mint tin, measure its usable space and design the populated board around it.

Release ordinary hardware as soon as its own checks pass. Firmware can be handed off and built independently once the hardware is defined. A release with factory programming explicitly in scope also requires an accepted firmware build.

Brainstorm consequential choices with recommendations. Use a deeper interview for unresolved engineering requirements that could materially change the design. In hobbyist mode explain practical consequences and choose routine defaults within agreed authority. In professional mode surface assumptions, limits and alternatives. Evidence requirements are the same in both modes. Record authority and scope in the brief.

The main session owns product decisions, project state and integration. When delegation is available and authorized, give a research or production agent a specific part, fixed inputs and an expected artifact. Verify critical findings against primary sources before adopting them. A delegate can return a proposed contract change but cannot agree it for the project.
