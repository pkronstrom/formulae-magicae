# Module seams and obligations

**Minimum inputs.** Current architecture, feasibility findings, applicable supplier assumptions and constraints. Define one owner for each fact. A board outline can be generated from a case envelope, or be an output of placement that CAD consumes. Stop if both tools are independently editing the same fact.

**Capture `contracts`.** Output roles `contracts`, `acceptance` and `visual`. Keep stable module IDs across component changes. Record provided/required seams covering rails, buses, pin maps, temporal behavior, shared coordinate origin, occupied volumes, mounting, connector access and manufacturing as applicable. The visual may be a labeled block/interface diagram with a side section. The acceptance matrix connects each requirement and variant to its qualifying evidence and owner. Distinguish required limits, preferences and facts awaiting confirmation.

Convert component/recipe obligations to a structured project checklist. Each entry needs an ID, source, applicability reason, owner, affected phases, decision/implementation deadline, state and evidence references. Keep `decided`, `implemented` and `verified` separate. A boot strategy is a decision, a routed access path implements it, and a demonstrated boot supplies verification. Handoff-only work can state physical verification is untested. An analog build skips programming and firmware.

The `interfaces` check reconciles seams and shared resource budgets. The `obligations` check checks requirements due now and keeps future ones visible. Pass each only at the declared scope. Record conditional items as inapplicable with a reason. An unresolved required claim blocks the deliverable that needs it. It can remain open for a scoped investigation whose claims exclude it.

For a programmable controller, use [MCU pin assignment](mcu-pin-assignment.md) with the rough floorplan. Record fixed functions and legal alternatives in the pin contract. Keep flexible choices provisional until the actual footprint and breakout have been checked at arrangement.

Reopen downstream work by affected interface, recipe, assumption or native file. Register relevant additional inputs with `capture --uses`. Follow the [state guide](state.md) for version-bound evidence and candidate progress.
