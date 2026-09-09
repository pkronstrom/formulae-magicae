# Screens and saved review state

The builder needs Python 3 only. It reads `assets/template.html` relative to itself, so it works from Claude Code, Codex, or any agent with filesystem and browser access.

## Manifest

```json
{
  "title": "Issue triage — three directions",
  "frames": [
    {"id": "triage-list", "title": "A · Dense list", "file": "list.html", "w": 1100, "h": 800, "x": 0, "y": 0},
    {"id": "triage-board", "title": "B · Status board", "file": "board.html", "w": 1100, "h": 800, "x": 1180, "y": 0},
    {"id": "triage-focus", "title": "C · One issue at a time", "file": "focus.html", "w": 1100, "h": 800, "x": 2360, "y": 0}
  ]
}
```

`file` is relative to the manifest. IDs are unique nonempty strings. x/y are world coordinates; w/h are screen CSS pixels. Defaults are 390×760 and a three-column mobile grid. Supply positions for wider screens on the first build; remove x/y from the manifest on revisions to preserve user arrangement. Explicit w/h revise screen dimensions; inspect coordinate annotations after a size/layout change, since they anchor to the screen, not individual DOM elements.

Each source is a complete HTML document with its own inline CSS and classic inline scripts if needed. Use real layouts, representative content, and mocked navigation; no build pipeline is required. The iframe `srcdoc` sandbox allows inline scripts but has an opaque origin, no network, and no parent access. Use data URLs for images/fonts and inline SVG. Avoid localStorage inside screens; the parent owns review persistence. Screen-internal transient state is not captured by Save HTML; render important states as separate named frames, or explicitly add serializable state handling if required.

## Persistence contract

`<script id="prototype-data" type="application/json">` sits at the top of the artifact. Parse it as JSON; do not execute the HTML to extract data. Fields:

| Field | Contract |
|---|---|
| `v`, `id`, `revision`, `savedAt` | schema version (1), document identity, design revision, millisecond save timestamp |
| `viewport` | x/y translation in viewport pixels; z scale, clamped to 0.1–3 |
| `frames` | id, title, x/y/w/h, complete authored html |
| `comments` | id, frameId or null for canvas, x/y, text, resolved |
| `strokes` | id, frameId or null, color, width, points as [x,y] arrays |

Annotation coordinates are relative to their frame content origin, or world origin for canvas marks. All positions and drawing widths use unscaled CSS pixels. Frame IDs must survive revisions. Deleted-frame feedback remains exportable but is not painted at a misleading new origin.

Use `scripts/build.py --from-saved user-review.html screens.json next/index.html` to retain annotations and layout while replacing screen content. Without `--from-saved`, an existing output supplies prior state automatically. The builder increments revision and writes atomically. Preserve the user's original review file.

For a full JSON export, use the builder's `write_html(path, data)` to create a temporary saved HTML, then pass it to `--from-saved`. For Copy for agent feedback, first verify document ID/revision against the source artifact; merge comments/strokes and frame coordinates by stable ID, keeping screen HTML from that artifact. If revisions differ, reconcile changes explicitly rather than replacing the current document wholesale.

Serialized data must escape every `<` as `\u003c` to prevent user text or embedded screen code from terminating its script block. `write_html` handles this. Keep the shell classic-script and fully inlined so `file://` works. Never serialize the live iframe DOM as the source of truth.

The shell loads newer browser state only for the same document ID and design revision. Storage keys are `prototype-singlefile:<id>:revision:<revision>` so different revision tabs cannot overwrite each other's autosaves. New revisions start from their embedded state. This avoids stale HTML hiding a revised design. It is not automatic feedback merging or cross-device sync.

## Maintainer checks

The bundled fixture is a three-screen design playground used to exercise the shell. With Playwright available in the test environment (not the output artifact):

```bash
python3 <skill-dir>/scripts/build.py <skill-dir>/tests/fixtures/screens.json /tmp/prototype-check/index.html
node <skill-dir>/tests/browser.cjs /tmp/prototype-check/index.html
```

If Playwright is installed outside the default Node resolution path, set `PLAYWRIGHT_MODULE` to its package directory. The test launches isolated headless Chrome and checks screen-relative marks, scaled dragging, preview interaction, portable saves, invalid imports, revision isolation and keyboard controls. It prints the temporary screenshot/save paths. It requires Google Chrome installed. This test runner is optional tooling; users opening the generated HTML need neither Node nor Playwright.
