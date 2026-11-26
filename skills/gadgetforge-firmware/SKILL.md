---
name: gadgetforge-firmware
description: Use when writing, building or resuming device firmware from a Gadgetforge hardware handoff with a selected controller and revision-specific electrical interfaces.
---

# Gadgetforge firmware

1. Read the [handoff and implementation contract](references/handoff.md). Verify the exact hardware revision, schematic, pin map, electrical domains, behavior and programming/recovery paths before depending on them.
   For an independent UI prototype while the board evolves, follow [parallel PCB and firmware work](references/handoff.md#parallel-pcb-and-firmware-work).
2. Confirm intended behavior and fault handling. Use a small state or interaction diagram for meaningful user-visible behavior. From the first prototype, [build and run automated firmware checks in Docker](references/docker.md). Select the toolchain for the hardware target or declared simulator proxy. Start with the smallest testable slice.
3. Retain editable source, dependencies, build commands, artifact hashes and verification. Host tests or a simulator answer only the properties they exercise. Label hardware checks untested when no device was used.
   Offer an optional [hands-on simulator review](references/handoff.md#hands-on-review-during-development) when trying the controls would help settle a user-visible behavior.
4. Return a build manifest and behavior visual for the hardware project's firmware phase. If the handoff is stale or the new work needs a hardware change, record the conflict and send the proposed change back through Gadgetforge. A firmware change cannot silently redefine a hardware seam.
