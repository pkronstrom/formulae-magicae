---
name: prototype-singlefile
description: Use when exploring UI screens or design alternatives on a Figma-style pan-and-zoom canvas, with draggable frames, pinned comments, drawing, and portable HTML saves. Also use for /prototype-singlefile and revising a saved prototype canvas.
---

# Prototype singlefile

Make a working UI design board the user can arrange, mark up, save, and return for revision. The deliverable is **one self-contained HTML file**, usable by double-click or a static hosting URL. Use the bundled canvas shell; spend design effort on the screens.

## Shape the screens

Use the user's existing request and project context. Resolve routine choices yourself; ask only for missing information that materially changes the design. A request to build an already described prototype is enough to proceed.

- For a flow, show its distinct views and relevant states together.
- For alternative designs, default to three structurally different options: change hierarchy, layout, or interaction, not just colours. Use the app's real design system and realistic content where available.
- State the design question briefly. Build screens at the intended device dimensions, with enough detail to judge them. Use mock data and local interactions.
- The board is a design artifact, not production code. Keep it outside production routes. Fold accepted design decisions into the real app separately.

## Build with the included shell

Read [references/authoring.md](references/authoring.md) for the manifest, screen constraints, and revision contract. Resolve all paths below relative to **this skill's actual directory**, not the project directory.

1. Write standalone screen HTML files and `screens.json` in a working directory, normally `docs/prototypes/<slug>/`. Give every screen a meaningful stable ID.
2. Assemble:

   ```bash
   python3 <skill-dir>/scripts/build.py docs/prototypes/<slug>/screens.json docs/prototypes/<slug>/index.html
   ```

3. Open `index.html` in a browser. The built HTML includes every screen; source files need not be shipped. Fit the board and inspect each screen at 100%.

The shell provides pan/zoom, frame title dragging and keyboard nudging, select/hand/comment/draw/preview modes, frame-relative annotations, undo/redo, comment edit/resolve/delete, browser autosave, portable Save HTML, JSON import/export, and Copy for agent. Preview enables screen controls; canvas tools intercept screen interactions in the other modes. The canvas is not a vector design editor: changing internal layout or styling is an agent revision unless additional editing controls were requested.

Keep the shell's state, coordinate transforms, sandboxing, and save logic intact when styling it. Treat screen HTML as authored code; treat annotation text as text. No runtime CDNs, remote fonts, imports, API calls, credentials, or required local servers. Inline assets. Screen scripts are sandboxed and cannot access the parent document.

## Review and revise

Ask the user to use **Save HTML** or **Export JSON** before returning their review. **Copy for agent** provides annotations, frame positions, and drawing geometry, but omits screen source. Browser autosave is local to that browser; a hosted URL does not sync edits to the agent or other users.

Before regenerating, read the user's latest saved/exported review. Keep stable screen IDs, frame positions, comments, strokes, and resolution states. Do not overwrite their saved artifact. Build a new revision with `--from-saved <review.html>`, or rebuild the existing output after merging feedback into its `prototype-data` block. Explicit manifest coordinates override saved positions, so omit x/y on ordinary revisions.

Removed-screen annotations stay in state as unanchored feedback. Mention those and resolve them deliberately; do not silently delete them. Autosave keys include the document ID and revision, so older tabs cannot overwrite a new revision's edits. Each revision retains its own browser state. Obtain the latest review **before** revision; browser storage is not a merge mechanism.

## Verify and deliver

Exercise these behaviors in the actual generated artifact:

- Open from `file://`; all screens render without console errors or external asset requests.
- Pan and zoom; drag a frame at non-100% zoom. Place a comment and draw on it, then move it again: both follow the screen.
- Undo/redo; edit and resolve a comment. In Preview, screen controls work; they do not accidentally drag frames.
- Reload: edits survive. Save HTML and open the saved copy in a fresh browser context: edits and screens survive.
- Export/import round trip; malformed data leaves current work intact. Copy for agent includes frame IDs, comments and drawings.
- Check a narrow viewport and keyboard access to tools and frame titles. Run `python3 -m unittest discover -s <skill-dir>/tests` if modifying the builder.

Report the file/URL, the design question and views, a short usage cue, and what was actually verified. If browser testing is unavailable, say which checks remain unverified.

## Hosting

When hosting is requested, follow [references/hosting.md](references/hosting.md). Reuse an authorized existing preview host when available. Serve the assembled HTML only, verify the URL, and explain that edits are browser-local until saved/exported. Do not assume that invoking this skill authorizes public publication or the creation of paid infrastructure.

Example request: `/prototype-singlefile Explore three layouts for our issue triage screen. Put them on one canvas so I can comment and draw, and give me a saved HTML file.`
