#!/bin/sh
# Usage: mermaid-ascii.sh < diagram.mmd
#
# Renders Mermaid from stdin as Unicode box art via beautiful-mermaid,
# installed once (pinned) into a user cache directory.
set -eu

VERSION=1.1.3
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/term-viz/beautiful-mermaid-$VERSION"
ENTRY="$CACHE/node_modules/beautiful-mermaid/dist/index.js"

if [ ! -f "$ENTRY" ]; then
  mkdir -p "$CACHE"
  npm install --prefix "$CACHE" --ignore-scripts --no-audit --no-fund --silent \
    "beautiful-mermaid@$VERSION" >&2
fi

ENTRY="$ENTRY" node --input-type=module -e '
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
const { renderMermaidAscii } = await import(pathToFileURL(process.env.ENTRY).href);
process.stdout.write(renderMermaidAscii(readFileSync(0, "utf8")) + "\n");
'
