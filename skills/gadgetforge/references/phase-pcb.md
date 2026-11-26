# Schematic, board shape, placement and routing

Use KiCad by default when available. Keep native project/library files. Check the exact installed KiCad CLI version and commands. A passing design-rule check supports a narrow claim about the applied rule set.

| Step | Minimum inputs | Output roles and visual | Check |
| --- | --- | --- | --- |
| `schematic` | Accepted contracts, component definitions, pin mapping, recipe/reference circuits | `schematic` editable source, `visual` annotated schematic | `electrical` checks ratings, power, pin/footprint mapping, applicable boot and programming, and electrical rules. |
| `arrangement` | Current schematic, board envelope and origin, connectors, footprints, keepouts and supplier limits | `board` native placement snapshot, `arrangement` dimensional contract, `visual` dimensioned outline and populated PCB view | `mechanical` and `placement` check board outline, thickness, stack height, hole geometry, accessibility and fit. Show the draft early, iterate across PCB and rough enclosure, then capture the agreed arrangement. |
| `routing` | Current arrangement, connectivity, stackup, board rules, model/recipe layout obligations | `board` native routed board, `visual` routed views | `layout` uses current connectivity and DRC results plus relevant review of power/return paths and manufacturer limits. |

Load [PCB routing](pcb-routing.md) before routing. Preserve upstream milestone snapshots in their own paths. Use current component models for 3D visuals and label proxies. For a user review, capture the mechanically significant parts and any untested clearances rather than inferring fit from a pretty rendering.

When placement is tight or the user wants few vias, inspect the ratsnest with fixed parts in place. Rotate movable packages so related pins face each other, group bus devices along their route, and leave a continuous corridor past holes, flex tails and probe pads. Preserve mating and probe access. For a controller, [compare pin assignments and package orientations](mcu-pin-assignment.md) before committing the breakout.

Try a breakout from the densest package and a critical route on a disposable copy before accepting the arrangement. A bounded whole-board trial can expose clusters of layer changes while placement is still easy to revise. Use [Reducing avoidable vias](pcb-routing.md#reducing-avoidable-vias) to compare drafts and the [optional autorouting workflow](pcb-routing.md#optional-autorouting) for tool setup.

Export a dimensioned board assembly at the arrangement milestone when enclosure work needs it. Use the agreed origin and distinguish verified part geometry from proxies. Refresh it after mechanical changes and for the [final enclosure fit check](phase-enclosure.md#model-the-assembly-and-check-worst-case-fit).

For a circuit behavior question during schematic or board work, use the [optional ngspice check](pcb-spice.md). Run it for the relevant circuit block and use its report as evidence for the modeled claim. Repeat a targeted check after routing when parasitics or revised parts affect that claim.

## Placement rules of thumb

- **Place the mechanically constrained parts first.** Set board outline, mounting points, connectors, controls and displays from the agreed fit. In the populated-board view, check the mating plug, component heights, and access to screws, programming pads and probes. Reserve antenna clearance in the board and case when the selected module calls for it. [Espressif module placement and housing guidance](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html#general-principles-of-pcb-layout-for-modules-positioning-a-module-on-a-base-board)
- **Lay out functional blocks before filling spare space.** Put parts that form a critical path near each other. Separate noisy clocks and switch nodes from low-level analog inputs and references. Sketch the critical signal routes and return paths while parts are still easy to move. [Analog Devices mixed-signal layout guidance](https://www.analog.com/en/resources/analog-dialogue/articles/2022/09/02/02/40/what-are-the-basic-guidelines-for-layout-design-of-mixed-signal-pcbs.html)
- **Give location-sensitive parts first claim on their space.** Place local bypass capacitors at the relevant supply pins with a short supply-to-capacitor-to-return loop. Follow the device layout for switching-power and feedback components. Where signal-line ESD protection is used, put it near the external connector and reserve its discharge path. [TI power layout](https://www.ti.com/document-viewer/lit/html/SSZTAL0/GUID-CF03725F-911C-4A96-9391-0E639F290409), [TI ESD layout](https://www.ti.com/lit/an/slva785/slva785.pdf#page=5)
- **Allow room for assembly.** Check footprint courtyards, orientation and polarity markings, and the selected assembler's edge and panel requirements. Include rails, fiducials and depanelization clearance where the service calls for them. Review the as-delivered board outline against the case. [KiCad PCB Editor](https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html), [JLCPCB rails and fiducials](https://jlcpcb.com/help/article/how-to-add-edge-rails-fiducials-for-pcb-assembly-order), [assembly orientation](https://jlcpcb.com/help/article/pcb-assembly-faqs-part-2)

Highlight these items and any remaining routing or fit risk on the arrangement preview. The exact component documentation, agreed case dimensions and selected assembly service supply the limits for this board.
