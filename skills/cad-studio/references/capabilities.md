# Capabilities: what to look for, what to bootstrap

Categories the router searches for, in the order it usually needs them. These are
categories, not skill names — inspect what is present.

| Category | Typical skill / tool names | Precision |
| --- | --- | --- |
| Parametric CAD | build123d, CadQuery, Replicad/OpenCascade, FreeCAD, OpenSCAD | buildable, fabrication |
| CAD preview / inspection | Replicad + Three.js viewer, screenshots, measurements | buildable |
| Woodworking / joinery / timber | woodworking, joinery, furniture, pergola/deck | buildable, fabrication |
| 3D-print design | FDM constraints, clearances, printability check | fabrication |
| Architecture / site / interior | building design, room layout, site plan | concept, layout |
| Photo / sketch reconstruction | reference-image → parametric model | any |
| Scene / environment | Blender, Three.js, terrain, glTF pipeline | layout, presentation |
| Rendering | Blender Cycles/Eevee, Three.js screenshot | presentation |
| Drawings | SVG/PDF orthographic views, sections, dimensions | buildable, fabrication |
| Fabrication output | cut list, stock list, hardware count, CSV, STL/3MF/STEP | fabrication |

## Bootstrap when nothing is installed

Install the single smallest thing that unlocks the precision needed. Prefer library-only routes
(no GUI app) so the agent can run headless.

| Precision needed | Install | Why this one |
| --- | --- | --- |
| buildable / fabrication (general) | `uv pip install build123d` (or `uv run --with build123d`) | Python, headless, STEP/STL out, measurable in code; the base of agentic-3d-modeling |
| buildable with live browser preview (preferred preview) | `npm i replicad replicad-opencascadejs` | Same OpenCascade kernel, live Three.js preview; base of ShapeItUp, kernelCAD, Nimbalyst |
| fabrication, 3D print | build123d + a slicer-independent check (manifold, min wall) | STL/3MF is all the printer needs |
| layout / presentation, browser | Three.js skills (often already in a skill vault under `threejs-*`) | Boxes with real dimensions, GLB import, screenshots — no Blender install |
| presentation, real render | Blender (`brew install --cask blender`), drive via `blender -b -P script.py` | Only when the user asks for a rendered image or terrain/landscaping |

## Candidate projects to pull skills or patterns from

None are dependencies. Pull one when a real project needs the capability and nothing
better is installed.

| Project | Gives | URL |
| --- | --- | --- |
| ShapeItUp | Replicad/OpenCascade agent CAD: headless modelling, validation, joints/collisions, STEP/STL/3MF | https://github.com/asbis/ShapeItUp |
| kernelCAD | Editable source → deterministic evaluation → validation → revision → browser review → export | https://github.com/w1ne/kernelCAD-web |
| Nimbalyst Replicad | Reference only — extension for the Nimbalyst app; ideas for measurements/screenshots | https://github.com/nimbalyst/nimbalyst-replicad |
| ShopPrentice | Woodworking/furniture CAD on Fusion 360 (MCP add-in, needs Fusion running); joinery/stock text reusable without it | https://github.com/ShopPrentice/shopprentice |
| agentic-3d-modeling | build123d photo → geometry → model → render views → measure → compare → revise loop | https://github.com/evnchn-agentic/agentic-3d-modeling |
| Claude-To-Print | Generate-and-verify loop for printable CAD | https://github.com/OzAILabs/Claude-To-Print |

## Where to look first

Runtime discovery (SKILL.md step 3) is mandatory; this only says where hits usually are.

- Skill vault, `cad/` category (`find cad`, `build123d`, `woodwork`): `agentic-3d-modeling`
  (build123d, photo → model loop; first choice for reconstruction and headless CAD),
  `Claude-To-Print/text-to-cad` (small print-part loop), `ShapeItUp` (Replicad MCP server via
  npx), `kernelCAD-web` (Replicad CLI + MCP + browser review — the live-preview candidate).
  `shopprentice`: execution needs Fusion 360, but its `docs/joinery/*.md`, `docs/types/*.md`,
  `docs/angled-construction.md` and `docs/templates-and-hardware.md` are app-free woodworking
  rules — read the relevant ones, then build the geometry with `agentic-3d-modeling`. Weak fit: `nimbalyst-replicad` is a plugin for the Nimbalyst
  app, not standalone. `threejs-*` and `blender-web-pipeline` sit under `games`.

## Gaps seen in use

Append a line when a real project needed something no skill covered. Three entries on
the same gap means it is time to add or pull a specialist skill — not to grow this router.

- 2026-09-13 a-frame-cabin: asked how rafters attach to the floor frame. No vaulted skill covers timber-framing joints (rafter/joist tie, gussets, collar ties, hold-downs); ShopPrentice has one line ("notch or birdsmouth"). Answered from general knowledge.
