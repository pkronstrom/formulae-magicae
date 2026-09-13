#!/usr/bin/env bash
# List every cad-studio design: path · newest change · authoritative file.
# Changelog in design.md is newest-first, so its first dated line is the newest change.
set -euo pipefail
root="${CAD_STUDIO_HOME:-$HOME/Designs}"
[ -d "$root" ] || { echo "no designs yet ($root)"; exit 0; }
found=0
while IFS= read -r f; do
  found=1
  rel=${f#"$root"/}; rel=${rel%/design.md}
  auth=$(awk '/^Authoritative:/{sub(/^Authoritative:[[:space:]]*/,""); print; exit}' "$f")
  last=$(awk '/^## Changelog/{c=1;next} c && /^[0-9]{4}-[0-9]{2}-[0-9]{2}/{print $1; exit}' "$f")
  printf '%-32s %-11s %s\n' "$rel" "${last:-—}" "${auth:-—}"
done < <(find "$root" -name design.md -type f | sort)
[ "$found" = 1 ] || echo "no designs yet ($root)"
