# Precision scale (internal)

The router's own reasoning aid for picking tools. Never shown to the user as levels or
tiers; never a menu.

| Internal name | User wants | Geometry | Cue words |
| --- | --- | --- | --- |
| concept | ideas, proportions, alternatives | approximate | sketch, rough, what if, ideas |
| layout | sizes and spatial relationships (room, yard, van interior, site) | boxes with real dimensions | fits, place, layout, where |
| buildable | precise enough to reason about real construction | parametric, editable | exactly, must be, real sizes |
| fabrication | cuts, holes, angles, BOM, fasteners, print files | validated, exported | cut list, screws, STL, print, build it |
| presentation | how it looks: materials, context, cameras, render | mesh copy of the source | show, render, how it would look |

Pick the lowest reading that satisfies the request. When two readings would produce
materially different work, ask one question. A design moves up only when the user asks
for something the current precision can't honestly give.
