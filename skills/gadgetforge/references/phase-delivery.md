# Delivery and manufacturing release

Use this guide in the brief/architecture and again at release. Record destination region, quantity, delivered budget, date target, supplier requirements/preferences and acceptable work on arrival. Distinguish files, fabricated/assembled PCB, kit, and finished device. Assign each operation to a party, including enclosure sourcing, factory programming if wanted, final assembly, and shipping. Check unavailable or unusually difficult parts before finalizing placement. A split or local route uses the same checks.

| Starting point | Verify for this project |
| --- | --- |
| [JLCPCB PCB capabilities](https://jlcpcb.com/capabilities/pcb-capabilities), [PCBA](https://jlcpcb.com/capabilities/pcb-assembly-capabilities), [parts](https://jlcpcb.com/parts) | Service tier, board thickness/material/stackup, precise manufacturer parts and placement eligibility, fees, panel/assembly restrictions. |
| [PCBWay PCB capabilities](https://www.pcbway.com/capabilities.html), [assembly and box build](https://www.pcbway.com/pcb-assembly.html) | Sourcing, footprint/placement process, quote scope for needed programming, tests or complete assembly. |
| [Seeed Fusion](https://wiki.seeedstudio.com/Service_for_Fusion_PCB/) | Fab/assembly file formats, source mapping and quoted programming/testing work. |
| [JLC3DP process guidance](https://jlc3dp.com/help/article/3d-printing-design-guideline) | Material, tolerances, clearance, wall details and finishing. Likewise verify any local provider's specific process. |

Store the source, date, applicable service tier and quote validity in the gadget repo. Distinguish hard requirements, preferences and needs-confirmation items from each other. A stock listing does not confirm placement. A public capabilities table does not represent an accepted order. Include setup, quantity minima, material, placement, shipping and applicable taxes/duties in estimates or state what is missing. Feed confirmed limits into the PCB and enclosure contract and recheck affected work if they change.

Use the [manufacturer cost estimate](phase-pricing.md) for the early supplier comparison. For a delivery release, reconcile the selected supplier's file-based quote against the early estimate and explain material differences in price or scope. Register the quote used by the release with `--uses`.

**Capture `release`.** Minimum inputs are current routed board, applicable enclosure, destination/scope and vetted supplier rules when necessary. For factory programming, also require the accepted firmware build, exact image and agreed loading and verification instructions. Output roles are `manifest` and `visual` (assembly view or drawing and handoff). Use the exact fab files, drill files, BOM/order codes, placement file, assembly notes, applicable enclosure/programming/test files, and route/quote/omissions. Register constituent files with `--uses`. Record who will install each omitted component and what the user does on arrival, including loading firmware for an unprogrammed board delivery. The `release` check compares revisions, assumptions, file consistency and deliverable scope. Package-only work can end before quotes. A supplier-confirmed delivery requires the exact service/quantity/variant and written scope. Capture the explicit release review separately from authorization to place that exact order. Use no order or contact step without the user's direction.

## Finish with the repository

The user can stop with an accepted design (`--target design`) or with a checked manufacturing package (`--target package`). Refresh the offline review board and leave the specification, editable sources, visuals and relevant checks together in the repository. Identify the accepted design revision and state what has yet to be checked on a physical unit. Both endpoints work without a quote or order. Keep later purchasing and assembly optional.

## Optional PDF design booklet

If requested at either endpoint, borrow the illustrated, step-by-step booklet format from `cad-construction-pdf` when available. Use the current Gadgetforge evidence and an available PDF export route. A short electronics booklet can include:

- A cover with the product render, design revision, configuration and status.
- The product specification and a readable block diagram or schematic. Include full schematic sheets as needed.
- Populated PCB views, dimensioned enclosure sections and an exploded view of how the board fits.
- The parts and hardware list, with explicit substitutions and any user-supplied parts.
- Illustrated assembly steps, with programming or bring-up only where in scope. Show the part or connector being installed in each relevant view.
- An optional UI walkthrough using screenshots from Wokwi or a similar emulator. Show the user action next to the display state it produces and label the screenshots with the firmware revision and their simulated status. If the booklet ships before a firmware build is available, use clearly labeled interaction mockups when helpful. Link to an interactive simulation when the user has an accessible link they want to include. The printed sequence should make sense on its own.
- The checks completed, open assumptions, and paths to the editable sources and any manufacturing package.

Generate the booklet from one revision, label provisional content as draft, and distinguish CAD or simulated evidence from tests on a physical unit. Open the finished PDF and check the revision, legibility of schematics and dimensions, and assembly-page order. Save the PDF as a derived artifact with its source revision. Keep Gerbers, drill files, placement data and editable CAD separately when those are part of the deliverable. Rebuild the booklet when its source artifacts change.
