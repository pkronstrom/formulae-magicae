# Serving and deploying

## Locally

```bash
open app.html            # macOS — the normal case, works for everything in this skill
```

If you need a server (you usually don't), any of these serve the current directory:

```bash
python3 -m http.server 8000
npx serve .
```

Reach for a server only when the app uses `fetch()` against a local file, a service worker, or ES modules — all of which the rules in `SKILL.md` steer you away from anyway.

## Sharing directly

The file *is* the artifact. Mail it, drop it in Slack, put it on a USB stick. The recipient double-clicks it. If they were sent a **Save**d copy, their data is already inside it.

Slack and Gmail may strip or preview `.html` attachments — zip it, or send a Pages link.

## GitHub Pages, no build step

Put the app at `index.html` in the repo root, then add `.github/workflows/deploy.yml`:

```yaml
name: Deploy to GitHub Pages

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/upload-pages-artifact@v3
        with:
          path: .
      - id: deployment
        uses: actions/deploy-pages@v4
```

No `build` job, no Node, no install — there is nothing to build. One job instead of two.

Then, once, in the repo: **Settings → Pages → Source → GitHub Actions**. Without that, the workflow runs and the deploy step fails.

Notes:

- `path: .` uploads the whole repo, including `README.md`. That's usually fine. To publish only the app, move it into `site/` and use `path: site`.
- The hosted copy is always the **pristine** app. Visitors' data lives in their own browser, or in the file they saved. Pushing a new version never touches anyone's data — but it does mean a returning visitor with localStorage gets their old state against your new code, which is exactly what the `v` field and migrations in `SKILL.md` §3 are for.
- Pages serves gzipped, so the "gzip" column in the dependency table is the number that reaches users.
- Custom domain: add a `CNAME` file next to the app.

## Escape hatch: when one file stops being enough

Stay with the single hand-authored file as long as you can. Graduate only when you hit a real wall:

- the file is past ~3000 lines and you're losing track of it
- you need a dependency that only ships as an npm package with its own imports
- you want TypeScript or JSX

The target stays the same — **one self-contained HTML file** — you just generate it now. esbuild does this in one command:

```bash
npm i -D esbuild
npx esbuild src/main.js --bundle --minify --format=iife --outfile=dist/app.js
```

Then inline `dist/app.js` into your HTML shell, or use a plugin that inlines it for you. Keep `--format=iife`, not `esm`, so the output still runs from `file://`.

The CI workflow then grows the build job back:

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - run: npm ci
      - run: npm run build
      - uses: actions/upload-pages-artifact@v3
        with:
          path: dist

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

Everything in `SKILL.md` still applies to the built output: one file, no runtime network, data block on top, and the same six checks before you call it done.
