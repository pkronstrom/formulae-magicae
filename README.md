# Formulae Magicae

![Formulae Magicae — Ars Automata](assets/formulae-magicae-cover.png)

> **Ars Automata** — a grimoire of small, practical spells for software agents.

Formulae Magicae is Peter Kronström's portable skill collection for Claude Code,
Codex, Hawk, and other hosts that understand the open `SKILL.md` convention. The
repository is private and pre-release while the catalog and distribution story are
being finished.

Each canonical skill lives in `skills/<name>/` with its scripts, templates,
references, and other runtime resources beside it. Vendor manifests are wrappers
around that one source tree; they do not fork the skills.

## The formulae

| Skill | Purpose | Notable dependencies |
| --- | --- | --- |
| [`summon`](skills/summon/) | Send files, folders, or text through an encrypted `croc` transfer unlocked by a spoken incantation. | `croc` |
| [`portal`](skills/portal/) | Open an encrypted agent-to-agent chat over ntfy, or a local same-machine channel. | `curl`, `openssl` |
| [`bento-slides`](skills/bento-slides/) | Build an editable, playable presentation as one offline `.bento.html` file. | A browser |
| [`singlefile`](skills/singlefile/) | Build a shareable app or prototype as one self-contained HTML file. | A browser |
| [`visualize`](skills/visualize/) | Render plans and system models as annotatable, self-contained HTML. | A browser |
| [`transcribe-media`](skills/transcribe-media/) | Turn video or audio into a timestamped transcript, key frames, and contact sheets. | `yt-dlp`, `ffmpeg`, Python tools described by the skill |
| [`tts`](skills/tts/) | Speak text locally with Kokoro or a configured system/custom engine. | Python/Kokoro or a supported fallback |
| [`pr-voice-review`](skills/pr-voice-review/) | Walk through a GitHub pull request aloud while the browser follows the review. | `gh`, browser, optional `tts` |
| [`pr-voice-review-single-file`](skills/pr-voice-review-single-file/) | Build a narrated, offline PR walkthrough as one HTML file. | `gh`, optional Kokoro |
| [`spec-flow`](skills/spec-flow/) | Run a discovery-first, spec-driven workflow around OpenSpec changes. | OpenSpec; optional companion workflow skills |
| [`wire-trigger`](skills/wire-trigger/) | Wait for a one-shot external signal, then continue the current agent turn or an explicit detached target. | Python 3; public or self-hosted ntfy |
| [`skill-vault`](skills/skill-vault/) | Catalog downloaded-but-inactive skills in a personal skill vault, grouped by category, so they don't clutter the active skill set. Bootstraps the vault on first use. | `git` |
| [`mcp-vault`](skills/mcp-vault/) | Stash MCP servers out of the active tool namespace; browse their cached tools, then connect only the one you need. | `mcpc`, `python3` |
| [`skill-improver`](skills/skill-improver/) | Mine the sessions where a skill was actually used, triage what went wrong into red/orange/yellow findings, and apply the approved fixes under version control. | `python3`, `git` |

## Quick install

This is a private repository, so your environment must already have GitHub access.

### Codex — one formula

For example, install Visualize only:

```text
$skill-installer Install skills/visualize from pkronstrom/formulae-magicae.
```

The skill appears in Codex in the next turn.

### Codex — all formulae

Ask the built-in skill installer:

```text
$skill-installer Install all of these skills from pkronstrom/formulae-magicae: skills/bento-slides, skills/portal, skills/mcp-vault, skills/pr-voice-review, skills/pr-voice-review-single-file, skills/singlefile, skills/skill-improver, skills/skill-vault, skills/spec-flow, skills/summon, skills/transcribe-media, skills/tts, skills/visualize, and skills/wire-trigger.
```

Installed Codex skills appear in the next turn.

### Claude Code

Install the complete collection:

```text
/plugin marketplace add pkronstrom/formulae-magicae
/plugin install formulae-magicae@formulae-magicae
```

Or install just one formula, such as Visualize:

```text
/plugin marketplace add pkronstrom/formulae-magicae
/plugin install visualize@formulae-magicae
```

### OpenSkills (optional)

Use the repository's SSH URL and select formulae interactively:

```sh
npx openskills install git@github.com:pkronstrom/formulae-magicae.git
```

### Hawk

Download and enable the complete collection:

```sh
hawk download git@github.com:pkronstrom/formulae-magicae.git --enable
```

## Install

### Claude Code: complete grimoire

Use the complete-collection commands in [Quick install](#quick-install).

Because the repository is private, GitHub authentication must grant access. Install
one formula instead by replacing the plugin name in the one-formula example above.

The available individual plugin names are the directory names in the table above.
Individual entries use Claude Code's root-`SKILL.md` plugin layout and require
Claude Code 2.1.142 or newer.

#### Migrating from Spellbook

Install Formulae Magicae first and verify the skills you use. Then remove the old
plugin and marketplace identity:

```text
/plugin uninstall spellbook@spellbook
/plugin marketplace remove spellbook
```

The migration is a clean import, not a rename of the old repository. Existing
Spellbook users should switch to `formulae-magicae@formulae-magicae` for updates.

### Codex and other Agent Skills hosts

Install an individual skill from its GitHub subdirectory with the host's skill
installer, or clone the repository and copy/symlink the desired folders into the
host's skill directory. Common user-level locations include:

In Codex, use either built-in installer prompt in
[Quick install](#quick-install).

| Host | Skill directory |
| --- | --- |
| Codex | `~/.agents/skills/` |
| Claude Code | `~/.claude/skills/` |
| Gemini CLI | `~/.gemini/skills/` |
| OpenCode | `~/.config/opencode/skills/` |

For an install-all development checkout:

```sh
git clone git@github.com:pkronstrom/formulae-magicae.git
mkdir -p ~/.agents/skills
for skill in formulae-magicae/skills/*; do
  ln -sfn "$(cd "$skill" && pwd)" "$HOME/.agents/skills/$(basename "$skill")"
done
```

The root [`.codex-plugin/plugin.json`](.codex-plugin/plugin.json) describes the
complete collection for Codex plugin tooling. No personal Codex marketplace entry
is modified by this repository.

As an optional cross-host installer, OpenSkills can scan the private repository and
let you select formulae interactively; see [Quick install](#quick-install).

OpenSkills is a convenience layer, not the canonical package format.

### Hawk

The root [`hawk-package.yaml`](hawk-package.yaml) lets Hawk discover the collection
as one package. The Hawk repository itself remains unchanged during this migration;
use the verified command in [Quick install](#quick-install). The proposed follow-up
is documented in
[`docs/hawk-hooks-transition.md`](docs/hawk-hooks-transition.md).

## Repository layout

```text
formulae-magicae/
├── .claude-plugin/       # Claude marketplace and all-skills plugin metadata
├── .codex-plugin/        # Codex all-skills plugin metadata
├── assets/               # Repository artwork
├── docs/                 # Migration and stewardship notes
├── skills/               # Canonical, portable skill directories
├── tests/                # Repository-level regression and validation tests
├── hawk-package.yaml     # Hawk package metadata
└── LICENSE
```

## Development

Run the migrated regression suite from the repository root:

```sh
python3 -m pytest -q
bash tests/portal/test.sh
```

Before publishing, validate both plugin manifests, run every skill validator and
test, audit licenses and generated files, and scan the full Git history for secrets.
The repository intentionally starts with a clean migration commit rather than the
history of either source repository.

## Security and privacy

Some formulae invoke third-party tools or public relays. Read each `SKILL.md` before
use. In particular, Summon and Portal encrypt payloads but public relays still see
connection metadata; self-host their relays for sensitive work. Never send secrets
merely because a transport is encrypted.

## Credits and licenses

The collection is MIT-licensed; see [`LICENSE`](LICENSE). Bundled fonts retain their
own license files inside the skills that use them. Summon's English wordlist is
derived from the EFF Short Wordlist under CC BY 3.0 US. See
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for attribution and bundled-asset
details.
