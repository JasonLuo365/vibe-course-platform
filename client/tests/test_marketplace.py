import json
from pathlib import Path

from vibe_submit import __version__


MARKETPLACE_ROOT = Path(__file__).parents[1] / "marketplace"
PLUGIN_ROOT = MARKETPLACE_ROOT / "plugins" / "vibe-submit"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_formal_marketplace_pins_the_packaged_client_version():
    marketplace = read_json(MARKETPLACE_ROOT / ".agents" / "plugins" / "marketplace.json")
    plugin = read_json(PLUGIN_ROOT / ".codex-plugin" / "plugin.json")
    mcp = read_json(PLUGIN_ROOT / ".mcp.json")

    assert marketplace["plugins"][0]["name"] == "vibe-submit"
    assert marketplace["plugins"][0]["source"]["path"] == "./plugins/vibe-submit"
    assert plugin["name"] == "vibe-submit"
    assert plugin["version"] == __version__
    assert plugin["skills"] == "./skills/"
    assert plugin["mcpServers"] == "./.mcp.json"
    assert mcp["mcpServers"]["vibe-submit"]["args"] == [
        "--from",
        "git+https://github.com/JasonLuo365/vibe-course-marketplace.git"
        f"@v{__version__}#subdirectory=packages/vibe-submit",
        "vibe-submit-mcp",
    ]


def test_formal_plugin_skill_requires_preview_and_confirmation():
    skill = (PLUGIN_ROOT / "skills" / "submit-homework" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "preview_submission" in skill
    assert "confirmed=true" in skill
    assert "force_confirmed=true" in skill
    assert "submit_homework" in skill
