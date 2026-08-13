---
name: singlefile
description: Build an app, tool, or prototype as one self-contained HTML file that runs from a double-click, stores its own data, and can be emailed to a friend or hosted on GitHub Pages. Use when the user wants something small and shareable, says "single file", "one HTML file", "no build step", "just send it to someone", "host it on gh-pages", or is ideating an app with no server and no accounts.
---

# Single-file HTML apps

One `.html` file. No build, no `node_modules`, no CDN at runtime. Double-click it and it works; mail it and it still works; drop it on GitHub Pages and it's a URL.

Start from `template.html` in this skill directory. It is a working app — open it in a browser before you change anything.

## 1. Fit check — do this before writing code

Say plainly if the idea doesn't fit, and propose the nearest thing that does. It does **not** fit when it needs:

| Requirement | Why it breaks | Nearest fit |
|---|---|---|
| API keys / secrets | Anyone can read the file. There is no "hidden" in a static page | User pastes their own key at runtime, stored in their browser only |
| Shared state between users | No server, no database | Export/import files, or a URL-encoded share link |
| Auth, accounts, permissions | Nothing to enforce them | Drop the requirement, or build a real app |
| Large media (video, big datasets) | Every byte is inlined; the file becomes unmailable | Load from disk via a file picker at runtime |
| Writing to arbitrary local files | Sandboxed | Save/export via the download or file-picker paths below |

Everything else — calculators, planners, trackers, editors, visualizers, generators, dashboards over pasted data, games, config builders — fits well.

## 2. Non-negotiables

1. **One file that opens from `file://`.** Test by double-clicking, not only through a server.
2. **Never `<script type="module">`.** Module scripts are CORS-blocked on `file://` in Chrome, so a double-clicked file silently renders nothing. Use a classic `<script>` with an IIFE. No `import`, no `export`.
3. **No network at runtime.** No CDN `<script src>`/`<link>`, no Google Fonts, no analytics. It must work on a plane. Vendor dependencies *into* the file at authoring time (§5).
4. **Data block first** (§3).
5. **Escape user data into HTML with `textContent`, never `innerHTML`.** It's your own data, but a shared file is an attack surface, and it's the same amount of code.
6. **No `alert`/`confirm`/`prompt`.** Use a `<dialog>` or an inline toast.

### The trap that will bite you

An inline `<script>` is terminated by the byte sequence `</script` **anywhere** inside it — including in a string, a regex, or **a comment**. This is the single most common way a generated single-file app arrives broken:

```js
// WRONG — the code is fine. The COMMENT ends the script element, and
// everything below it gets parsed as HTML:
var json = escapeForBlock(state);   // stop user text closing </script>

// RIGHT — identical code, comment that doesn't spell the sequence:
var json = escapeForBlock(state);   // stop user text closing the data block

// Also fine — escape the slash when you must write it in a regex or string:
html.replace(/(<\/script>)/i, ...)
```

Note which half is the bug: escaping `<` in the serialized JSON (§3) is the *sanctioned* technique, not the trap. Keep it. The comment is the only thing wrong above.

After generating, always run `grep -n '</script' app.html`. The count must exactly equal the number of real closing tags. Anything else means the file is broken.

## 3. The data block is the contract

Put the state at the **top** of the file, as pretty-printed JSON, in a script with a stable `id`:

```html
<script id="app-data" type="application/json">
{
  "v": 1,
  "savedAt": 0,
  "items": []
}
</script>
```

This is deliberate. It means an agent or an external tool can `head -60 app.html`, read the entire document state, rewrite that block, and never touch the code below it. The file is both the app and its own readable save format.

Consequences you must honor:

- **Pretty-print it** (`JSON.stringify(state, null, 2)`). Minified state is not a contract, it's a blob.
- **Version it** with `v`, and migrate on load. A file saved months ago must still open.
- **Validate it, never trust it.** Someone hand-edited it. On bad JSON, show a banner and fall back — do not wipe their data.
- **Escape every `<` in the serialized JSON** to its `u003c` unicode escape (see `serialize()` in the template), so no user text can terminate the block.
- When **modifying an existing** single-file app's content, rewrite only this block. Don't regenerate the whole file.

## 4. Persistence: three tiers

`template.html` wires all three. Keep tier 1 and 2; tier 3 is optional.

| Tier | Purpose |
|---|---|
| **localStorage**, debounced autosave, one namespaced key | working state, survives reload |
| **Save** | Chrome/Edge: writes the file in place after a one-time picker. Elsewhere: downloads `<name>-<date>.html`. Either way the output is the whole app with data baked in |
| **Export JSON / Copy / Import** | data leaving the app — into a spreadsheet, an agent, another instance |

**Save** is progressive enhancement, and in Chrome it works from `file://` too — verified there: `showSaveFilePicker` is available and not origin-blocked, and `isSecureContext` is `true`, so the clipboard path works from a double-clicked file as well. That was checked in Chrome only; engines differ on whether `file://` counts as trustworthy, which is exactly why the template keeps a `document.execCommand` copy fallback and a Blob-download save path. Chrome and Edge get Bento-style silent in-place rewriting after the first pick; Firefox and Safari get a download. Both paths produce an identical file — only the delivery differs. The handle lives for the page session; after a reload the user picks once more. Persisting handles across reloads needs IndexedDB plus a permission re-request — only add it if asked.

**Load precedence**, when both a baked-in block and localStorage exist: whichever has the newer `savedAt`. A file you were just sent wins on first open; after you edit it, your local copy wins. Without this rule, reloading an edited file silently discards the edits.

`localStorage` on `file://` is shared across local files in some browsers, so namespace the key per app (`APP_ID`). Two copies of the *same* app opened from disk share a key — the `savedAt` rule keeps that mostly sane; say so if it matters to the user.

## 5. Dependencies

Default to none. Check the platform first — `<dialog>`, `<details>`, `<input type=color|date|range>`, `Intl.NumberFormat`, `Intl.DateTimeFormat`, `crypto.randomUUID`, `structuredClone`, `URL.createObjectURL`, CSS grid, `:has()`, container queries. Most "I need a library" moments are already solved.

If you genuinely need one, vendor it — download the minified source and paste it inside a `<style>` or `<script>` tag. Never link it.

```bash
curl -s https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.fluid.classless.min.css
```

Measured costs (raw bytes are what lands in your file; gzip is what Pages serves):

| Dependency | Raw | Gzip | When |
|---|---|---|---|
| Pico v2 classless | 71 KB | 10.3 KB | Form-heavy UI. Styles semantic HTML with **zero class names** |
| Water.css | 22.7 KB | 3.6 KB | Prose/document pages |
| Simple.css | 9.4 KB | 2.8 KB | Prose, smaller still |
| Open Props | 29.6 KB | 7.7 KB | Design tokens only, no components |
| Alpine.js | 46 KB | 16.7 KB | Declarative interactivity, no build |
| Preact + htm | 12.6 KB | 5.5 KB | Component model without JSX/build |

Fonts and images: `data:` URIs, or skip them. System fonts cost nothing and look native. An emoji or inline SVG favicon avoids a second file.

**Size budget:** under 1 MB is comfortable and mailable. Past ~5 MB, say so and ask before continuing.

## 6. CSS baseline

`template.html` ships framework-free: design tokens, a sticky-header app shell, and one grid rule that handles all responsive behavior with no media queries:

```css
grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr));
```

Theming is `color-scheme: light dark` plus `light-dark()` custom properties, so each colour is declared **once** with both themes side by side:

```css
--bg: light-dark(#fbfbfa, #16161a);
```

The manual toggle then only flips `color-scheme` on `[data-theme]`, and every token follows automatically — no second copy of the palette to drift out of sync. `light-dark()` has been Baseline since May 2024; on an older engine the declarations are invalid and you get default black-on-white, which is degraded but readable. If a specific old browser is a hard requirement, duplicate the tokens under `@media (prefers-color-scheme: dark)` instead and accept the two copies.

**Upgrade path:** if the app is form-heavy, replace the `<style>` contents with vendored Pico (command above) and delete the token block. Because Pico is classless, you keep writing plain `<article>`, `<button>`, `<input>` — no class names to invent, and no design drift over a long generation. That's why it's the recommended framework here despite the 71 KB.

**JS:** vanilla first — a `state` object, a `render()` that rebuilds the view, and delegated event listeners cover most apps in ~40 lines, as in the template. Reach for Alpine only when the UI is genuinely form- and interaction-heavy.

## 7. Definition of done

Not done until you have actually run these:

```bash
grep -c '</script' app.html      # must equal the real closing-tag count
```

1. Open it from `file://` — **zero console errors**.
2. Add data → reload → data is still there.
3. Save → open the saved file → the data is in it.
4. Check the saved file's `head -30` shows a clean, pretty-printed data block.
5. Narrow the window to phone width — still usable.
6. Keyboard: Tab reaches every control, focus is visible.

State that you ran these. If you couldn't run one, say which.

For local serving and GitHub Pages deployment, read `deploy.md` in this skill directory.
