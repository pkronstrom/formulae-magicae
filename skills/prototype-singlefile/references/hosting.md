# Hosting a prototype canvas

The deliverable is a static HTML file. Prefer the user's existing preview infrastructure and its current deployment instructions. Hosting is optional; opening the HTML locally needs no service.

When the user asks for a URL, establish the intended host from their request or available project context. Reuse prior authorization. If the destination or public/private visibility is materially unresolved, prepare and verify the HTML first, then ask only for that missing decision. Do not assume a publicly accessible provider for confidential mockups.

Deploy a dedicated directory containing only the final `index.html` and any explicitly intended downloadable artifacts. The assembled HTML already includes the screens. Do not publish source workspaces, review exports, or unrelated repository files. Use the host's supported CLI/API and consult current documentation rather than relying on a hardcoded deployment recipe.

For GitHub Pages, use the repository's existing Pages setup or create a minimal workflow using current official instructions when authorized. For a local preview, `python3 -m http.server 8000 --bind 127.0.0.1 --directory <output-dir>` is sufficient; this is a localhost preview, not a remotely accessible hosted URL.

After deployment, open the actual URL and check screens, comments, drawing, and Save HTML. Supply that verified URL. Explain the persistence model in one sentence: edits stay in this browser until Save HTML, Export JSON, or Copy for agent; the URL itself is a published starting document, not a shared live review session.

If the user needs automatic shared comments or multiuser editing, a backend or hosted collaboration product is a separate scope decision. Do not quietly pretend localStorage provides it.
