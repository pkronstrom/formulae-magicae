import json
import os
import re
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
EXPECTED_SKILLS = {
    "bento-slides",
    "portal",
    "pr-voice-review",
    "pr-voice-review-single-file",
    "singlefile",
    "spec-flow",
    "summon",
    "transcribe-media",
    "tts",
    "visualize",
}
VERSION = "1.0.0"
SKILLS_WITH_BUNDLED_THIRD_PARTY_ASSETS = {
    "bento-slides",
    "portal",
    "summon",
    "visualize",
}


def load_json(relative_path: str):
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def skill_name(skill_md: Path) -> str:
    match = re.search(r"(?m)^name:\s*([^\n]+)$", skill_md.read_text(encoding="utf-8"))
    assert match, f"missing name frontmatter in {skill_md}"
    return match.group(1).strip()


def test_catalog_is_exact_and_skill_names_match_directories():
    directories = {path.name for path in SKILLS.iterdir() if path.is_dir()}
    assert directories == EXPECTED_SKILLS
    for name in directories:
        skill_md = SKILLS / name / "SKILL.md"
        assert skill_md.is_file()
        assert skill_name(skill_md) == name


def test_claude_marketplace_has_complete_and_individual_plugins():
    marketplace = load_json(".claude-plugin/marketplace.json")
    plugins = marketplace["plugins"]
    names = [plugin["name"] for plugin in plugins]
    assert len(names) == len(set(names))
    assert set(names) == EXPECTED_SKILLS | {"formulae-magicae"}

    for plugin in plugins:
        assert plugin["version"] == VERSION
        source = plugin["source"]
        assert source.startswith("./")
        source_path = (ROOT / source).resolve()
        assert source_path.is_relative_to(ROOT.resolve())
        assert source_path.exists()
        if plugin["name"] != "formulae-magicae":
            assert (source_path / "SKILL.md").is_file()
            assert (source_path / "LICENSE").is_file()
            if plugin["name"] in SKILLS_WITH_BUNDLED_THIRD_PARTY_ASSETS:
                assert (source_path / "THIRD_PARTY_NOTICES.md").is_file()


def test_complete_plugin_manifests_point_at_canonical_skills():
    claude = load_json(".claude-plugin/plugin.json")
    codex = load_json(".codex-plugin/plugin.json")
    assert claude["name"] == codex["name"] == "formulae-magicae"
    assert claude["version"] == codex["version"] == VERSION
    assert codex["skills"] == "./skills/"
    assert (ROOT / codex["skills"]).is_dir()


def test_skill_text_is_free_of_source_repo_and_host_install_assumptions():
    banned = {
        "builtins/skills": "source-repository layout",
        "hawk sync": "Hawk-only update workflow",
        "hawk add": "Hawk-only update workflow",
        "hawk-hooks repo": "source-repository documentation",
    }
    violations = []
    for path in SKILLS.rglob("*"):
        if not path.is_file() or path.suffix in {".b64", ".pyc"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for needle, reason in banned.items():
            if needle in text:
                violations.append(f"{path.relative_to(ROOT)}: {needle} ({reason})")
    assert not violations, "\n".join(violations)

    migrated_skill_docs = [
        path for path in SKILLS.rglob("*.md")
        if path != SKILLS / "bento-slides/reference/agents.md"
    ]
    hard_coded = [
        str(path.relative_to(ROOT))
        for path in migrated_skill_docs
        if "~/.claude/skills" in path.read_text(encoding="utf-8")
    ]
    assert not hard_coded, "\n".join(hard_coded)


def test_individual_plugins_do_not_depend_on_sibling_skill_files():
    portal = SKILLS / "portal"
    assert (portal / "wordlist.fi.txt").is_file()
    assert (portal / "wordlist.en.txt").is_file()
    assert "../summon" not in (portal / "portal.sh").read_text(encoding="utf-8")

    standalone = SKILLS / "pr-voice-review-single-file"
    assert (standalone / "authoring-guidance.md").is_file()
    assert "../pr-voice-review/SKILL.md" not in (
        standalone / "SKILL.md"
    ).read_text(encoding="utf-8")
    standalone_text = (standalone / "SKILL.md").read_text(encoding="utf-8")
    assert "<sibling>" not in standalone_text
    assert "sibling's §" not in standalone_text


def test_readme_quick_install_documents_every_supported_install_path():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    quick_heading = "## Quick install"
    h2_matches = list(re.finditer(r"(?m)^## [^\n]+$", readme))
    h2_headings = [match.group() for match in h2_matches]
    assert quick_heading in h2_headings, "README is missing the Quick install section"
    quick_index = h2_headings.index(quick_heading)
    assert quick_index + 1 < len(h2_matches), "Quick install must be followed by Install"
    next_h2 = h2_matches[quick_index + 1]
    assert next_h2.group() == "## Install"

    quick_start = h2_matches[quick_index].end()
    quick_section = readme[quick_start:next_h2.start()]
    expected_identifiers = {
        "pkronstrom/formulae-magicae",
        "formulae-magicae@formulae-magicae",
        "npx openskills install",
        "hawk download",
    }
    for identifier in expected_identifiers:
        assert identifier in quick_section

    codex_heading = "### Codex — all formulae"
    h3_matches = list(re.finditer(r"(?m)^### [^\n]+$", quick_section))
    h3_headings = [match.group() for match in h3_matches]
    assert h3_headings == [
        "### Codex — one formula",
        codex_heading,
        "### Claude Code",
        "### OpenSkills (optional)",
        "### Hawk",
    ]
    codex_index = h3_headings.index(codex_heading)
    codex_start = h3_matches[codex_index].end()
    codex_end = (
        h3_matches[codex_index + 1].start()
        if codex_index + 1 < len(h3_matches)
        else len(quick_section)
    )
    codex_block = quick_section[codex_start:codex_end]
    assert "$skill-installer" in codex_block
    for name in EXPECTED_SKILLS:
        assert f"skills/{name}" in codex_block



def test_pr_voice_review_tts_resolution_supports_bundle_and_isolation(tmp_path):
    env = {**os.environ, "PATH": "/usr/bin:/bin", "TTS_PATH": ""}

    bundle = tmp_path / "bundle"
    shutil.copytree(SKILLS / "pr-voice-review", bundle / "pr-voice-review")
    shutil.copytree(SKILLS / "tts", bundle / "tts")
    bundled = subprocess.run(
        [bundle / "pr-voice-review" / "bootstrap.sh", "--resolve-tts"],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert bundled.stdout.strip() == str(bundle / "tts" / "tts.sh")

    isolated = tmp_path / "isolated"
    shutil.copytree(SKILLS / "pr-voice-review", isolated / "pr-voice-review")
    standalone = subprocess.run(
        [isolated / "pr-voice-review" / "bootstrap.sh", "--resolve-tts"],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert standalone.stdout == "\n"


def test_bento_portability_guidance_is_not_patched_into_vendored_reference():
    vendored = (SKILLS / "bento-slides/reference/agents.md").read_text(encoding="utf-8")
    assert "VENDORED" in vendored and "do not edit by hand" in vendored
    assert '"<skill-dir>/bento.sh"' not in vendored
    skill_text = (SKILLS / "bento-slides/SKILL.md").read_text(encoding="utf-8")
    assert "preserve the entire directory" in skill_text


def test_no_generated_python_cache_is_tracked():
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    assert any(tracked), "git index is empty; cache check would be vacuous"
    generated = [path for path in tracked if b"__pycache__" in path or path.endswith(b".pyc")]
    assert not generated


def test_shell_entrypoints_keep_executable_bits():
    scripts = list(SKILLS.rglob("*.sh"))
    assert scripts
    not_executable = [path.relative_to(ROOT) for path in scripts if not os.access(path, os.X_OK)]
    assert not not_executable


def test_readme_cover_exists():
    assert (ROOT / "assets/formulae-magicae-cover.png").is_file()
