#!/usr/bin/env python3
"""Copy the agent-harness config that is actually active into a scan directory.

Scanning ~/.claude or ~/.codex directly reads session logs, job worktrees and
marketplace source clones, which buries the real findings and can run to tens
of gigabytes once skill symlinks are followed. This keeps only live surfaces.

Usage: stage.py <out-dir> [--project <repo>]
Prints one line per staged root: <root-dir> <files>.
"""
import json
import shutil
import sys
from pathlib import Path

HOME = Path.home()
MAX_BYTES = 512 * 1024
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".tmp",
             # ecc-agentshield 1.6.0 crashes (EISDIR) on a directory with this name
             ".clinerules"}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".glb", ".gltf", ".usdz",
                 ".obj", ".blend", ".mp4", ".mov", ".wav", ".mp3", ".zip", ".jsonl",
                 ".sqlite", ".db", ".lock", ".pdf"}


def ignore(directory, names):
    skipped = []
    for name in names:
        path = Path(directory) / name
        if name in SKIP_DIRS or name.endswith("-lock.json"):
            skipped.append(name)
        elif path.is_file() and (path.suffix.lower() in SKIP_SUFFIXES
                                 or path.stat().st_size > MAX_BYTES):
            skipped.append(name)
    return skipped


def copy(src: Path, dst: Path):
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, symlinks=False, ignore=ignore,
                        ignore_dangling_symlinks=True, dirs_exist_ok=True)
    elif src.stat().st_size <= MAX_BYTES:
        shutil.copy2(src, dst)


def stage_claude(out: Path):
    src = HOME / ".claude"
    for name in ["CLAUDE.md", "settings.json", "settings.local.json", "mcp.json",
                 "hooks", "agents", "commands", "skills", "rules"]:
        copy(src / name, out / name)
    settings = json.loads((src / "settings.json").read_text()) if (src / "settings.json").exists() else {}
    status = (settings.get("statusLine") or {}).get("command", "").split()
    if status:
        copy(Path(status[0]).expanduser(), out / "statusline" / Path(status[0]).name)
    # Only plugins that are installed and enabled; marketplace clones are not loaded.
    enabled = {k for k, v in (settings.get("enabledPlugins") or {}).items() if v}
    installed = HOME / ".claude/plugins/installed_plugins.json"
    if installed.exists():
        for key, records in json.loads(installed.read_text()).get("plugins", {}).items():
            if key in enabled:
                for record in records:
                    path = Path(record["installPath"])
                    copy(path, out / "plugins" / path.relative_to(src / "plugins"))


def stage_codex(out: Path):
    src = HOME / ".codex"
    for name in ["config.toml", "hooks.json", "AGENTS.md", "mcp.json", "rules", "agents",
                 "skills", "prompts"]:
        copy(src / name, out / name)
    copy(HOME / ".agents/skills", out / "skills")


def stage_project(repo: Path, out: Path):
    for name in [".claude", ".mcp.json", "CLAUDE.md", "AGENTS.md", ".codex", ".agents",
                 ".cursor", ".gemini", "opencode.json", ".npmrc", ".yarnrc.yml",
                 "pnpm-workspace.yaml", ".vscode/tasks.json"]:
        copy(repo / name, out / name)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    out = Path(sys.argv[1]).resolve()
    if out.exists():
        shutil.rmtree(out)
    roots = {"claude": stage_claude, "codex": stage_codex}
    for name, stage in roots.items():
        stage(out / name)
    if "--project" in sys.argv:
        stage_project(Path(sys.argv[sys.argv.index("--project") + 1]).resolve(), out / "project")
    for root in sorted(p for p in out.iterdir() if p.is_dir()):
        print(root, sum(1 for f in root.rglob("*") if f.is_file()))


if __name__ == "__main__":
    main()
