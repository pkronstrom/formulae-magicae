# Authoring and portable contract

Skill release: **0.1.0**. The embedded package format remains **share-card v1**; these versions describe different contracts.

`share.py` uses Python 3 and the standard library. Paths in `source` and `cover` are relative to the spec file (absolute paths also work). Each `path` is the portable destination name inside the ZIP. Explicit regular files only; no directory recursion or symlink inputs. Output must be new.

```json
{
  "title": "Nettle Courier",
  "creator": "Your name",
  "edition": "01",
  "rarity": "rare",
  "type": "Polygonster",
  "level": 17,
  "tagline": "Woodland · Chaotic hungry",
  "vitals": "HP 42 / 42",
  "skill": {"name": "Plausible Den-ability", "description": "Steals your lunch, then helps you look for it.", "kind": "Passive", "cost": "Cost: 0 shame"},
  "description": "Raised by wolves. Banned by the picnic committee.",
  "lore": "Banished from Mossroot after the Great Cheese Disappearance. Claims the cheese left willingly.",
  "cover": "cover.png",
  "provenance": "Actual renderer screenshot. Describe authorship and relevant tools here.",
  "license": "State the actual sharing/reuse terms; unknown if unverified.",
  "stats": {"Triangles": "12.4k", "Bones": 36, "Clips": 7},
  "files": [
    {"source": "fox.glb", "path": "models/fox.glb", "role": "Mesh, skeleton and animation clips"},
    {"source": "LICENSE.txt", "path": "LICENSE.txt", "role": "Reuse terms"}
  ]
}
```

Only title, cover and a nonempty files list are required. Up to three technical stats appear on the reverse. The front shows a playful type, funny description, one fictional funny skill and optional short `lore` note. For characters, frame the upper two-thirds of the body and keep the character centered, place the face near the upper golden-ratio height, and avoid clipping ears or crowding the direction of the gaze. Foil is always on, with no viewer control. Only the card is visible; clicking it flips to details and download. Art fills the upper 66% with an intentional zoom/crop. Omit unmeasured stats. Optional `background` points to a PNG/JPEG/WebP illustration embedded behind the cover. Pair it with a native transparent asset render (prefer three-quarter view). Render at least twice the final displayed pixel dimensions; avoid upscaling a small review capture or excessive denoising that softens the face. If omitted, the screenshot fills the image area by itself. Levels must be integers from 0 to 99; the default is 1. `tagline`, `vitals`, `skill.kind` and `skill.cost` are optional fictional game flavor. Cover supports PNG, JPEG or WebP; it is embedded separately and is not automatically included in the ZIP. `license` text describes terms; preserve upstream license files when required. Do not invent licenses.

The builder uses `assets/card.html`. For major visual changes, copy the skill into a temporary directory, change only that template and build with the copied script; don't mutate the installed default for a one-off card.

## Contract v1

Near the beginning, inert JSON in `script#share-manifest` declares `format: "share-card"`, `version: 1`, display metadata, `files` (relative `path`, integer `bytes`, hex `sha256`, descriptive `role`) and `archive` (base64 ZIP encoding, decoded `bytes`, decoded ZIP `sha256`). Source machine paths are excluded. The final `script#share-payload` holds a single base64 ZIP. JSON is escaped against HTML closing-tag injection.

The browser offers the intact ZIP; its checksum is checked before download when Web Crypto is available. The standalone Python unpacker checks the archive hash, exact inventory, member sizes and every file hash. It rejects unsafe/colliding paths, symlinks, existing destinations and unsupported versions. All validation occurs before extraction. A 512 MiB uncompressed cap bounds ordinary bundle memory; this is a sharing format, not an untrusted-archive sandbox.

`pre#share-extractor` contains the full Python unpacker as HTML-escaped text. A recipient can recover it with `HTMLParser`/an HTML parser's text-content API, review it, and run `python3 unpack.py card.html new-folder`. The pre element has the `hidden` attribute: instructions and code are available in HTML source without being shown to the viewer. Their agent needs no installed skill. Running without a destination verifies/lists only. The card includes the same directions in an early HTML comment.

## Visual references

Interaction inspiration: [Simey's foil gallery](https://poke-holo.simey.me/), [Hover Tilt](https://github.com/simeydotme/hover-tilt), [shader card study](https://github.com/BrannySG/card-renderer). The included CSS and JavaScript are original implementations; no upstream card graphics, texture files or code are vendored.
