"""The plugin's structure, its references to real published tools, and the exact command pipeline its agents run."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "fixtures" / "shop"
PUBLISHED = json.loads((Path(__file__).parent / "published_tools.json").read_text())
ALL_TOOLS = {t for s in PUBLISHED.values() for t in s["tools"]}


def frontmatter(path: Path) -> tuple[dict, str]:
    text = path.read_text("utf8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    assert m, f"{path.name}: missing frontmatter"
    return yaml.safe_load(m.group(1)), m.group(2)


def test_manifests_and_servers():
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    assert plugin["name"] == market["plugins"][0]["name"] == "release-readiness"
    servers = json.loads((ROOT / ".mcp.json").read_text())["mcpServers"]
    assert set(servers) == set(PUBLISHED) == {"release-gate", "playwright-qa", "selenium-qa", "api-contract-qa",
                                              "api-functional-qa", "llm-assure"}
    for name, s in servers.items():
        assert s["command"] in ("uvx", "npx")
        assert any(a.startswith("k11-") for a in s["args"]), name


def test_agents_and_skill_frontmatter():
    agents = sorted((ROOT / "agents").glob("*.md"))
    assert [a.stem for a in agents] == ["api-contract-evidence", "api-functional-evidence", "llm-evidence", "ui-evidence"]
    for a in agents:
        fm, body = frontmatter(a)
        assert fm["name"] == a.stem and len(fm["description"]) > 40 and fm.get("model") in ("sonnet", "opus", "haiku")
        assert "don't decide the release" in body.lower() or "you don't decide" in body.lower()
    fm, body = frontmatter(ROOT / "skills/check/SKILL.md")
    assert fm["name"] == "check" and "argument-hint" in fm
    for a in agents:  # the skill delegates to every agent by its plugin-qualified name
        assert f"release-readiness:{a.stem}" in body


def test_every_referenced_tool_exists_in_the_published_servers():
    known_words = {"heal-ci", "contract-ci"}
    text = "\n".join(p.read_text("utf8") for p in [ROOT / "skills/check/SKILL.md", *sorted((ROOT / "agents").glob("*.md"))])
    referenced = set(re.findall(r"`([a-z]+(?:_[a-z]+)+)`", text)) - {"ui_heal", "api_tests"}
    assert referenced, "no tool references found"
    missing = sorted(t for t in referenced if t not in ALL_TOOLS and t not in known_words)
    assert not missing, f"tools referenced but not in any published server: {missing}"
    for must in ("plan_checks", "evaluate_release", "collect_evidence", "list_environments"):
        assert must in referenced and must in ALL_TOOLS


def test_published_versions_have_what_the_agent_needs():
    assert "plan_checks" in PUBLISHED["release-gate"]["tools"]
    assert tuple(map(int, PUBLISHED["release-gate"]["version"].split("."))) >= (0, 2, 0)


# ---- the exact pipeline the agents run, with the published CLIs -------------------------------------

def _exe(name: str) -> str:
    found = shutil.which(name, path=str(Path(sys.executable).parent)) or shutil.which(name)
    if not found:
        pytest.skip(f"{name} not installed")
    return found


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=cwd, check=True,
                   capture_output=True)


def run(cwd, *cmd, env=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env={**os.environ, **(env or {})})


def test_agent_pipeline_end_to_end(tmp_path):
    gate, contract, functional = (_exe("k11-release-gate-mcp"), _exe("k11-api-contract-qa-mcp"),
                                  _exe("k11-api-functional-qa-mcp"))
    repo = tmp_path / "shop"
    shutil.copytree(FIXTURE, repo, ignore=shutil.ignore_patterns("__pycache__", "*.db"))
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "base")
    git(repo, "tag", "base")

    # The change under review: GET /orders/{id} stops returning `total` (breaks the critical mobile app)
    spec = (repo / "openapi.yaml").read_text()
    spec = spec.replace("required: [id, customerId, status, total, channel, items]", "required: [id, customerId, status, channel, items]")
    spec = spec.replace("        total: { type: number }\n", "")
    (repo / "openapi.yaml").write_text(spec)
    env = {"QA_MCP_ROOT": str(repo), "PYTHONIOENCODING": "utf-8"}

    # 1. plan (the skill's step 1)
    p = run(repo, gate, "plan", "--base", "base", env=env)
    assert p.returncode == 0, p.stderr
    assert "NEEDED  API contract" in p.stdout and "NEEDED  API functional tests" in p.stdout
    assert "skip    LLM red-team" in p.stdout and "skip    UI tests" in p.stdout

    # 2. contract evidence (api-contract-evidence agent's command)
    c = run(repo, contract, "contract-ci", "--spec", "openapi.yaml", "--base", "base", "--fail-on", "never", env=env)
    assert c.returncode == 0, c.stderr
    assert (repo / ".qa-mcp/contract-report/contract-report.json").is_file()

    # 3. API functional evidence (api-functional-evidence agent's command), against the running service
    sys.path.insert(0, str(repo))
    try:
        from server import Shop
        shop = Shop(repo / "shop.db", 0)
    finally:
        sys.path.remove(str(repo))
        sys.modules.pop("server", None)
    try:
        f = run(repo, functional, "run", "--env", "local", "--fail-on", "never",
                env={**env, "SHOP_URL": shop.url, "SHOP_TOKEN": "test-token"})
    finally:
        shop.close()
    assert f.returncode == 0, f.stderr
    assert (repo / ".qa-mcp/api-test-report/api-test-report.json").is_file()

    # 4. decide (the skill's step 4)
    d = run(repo, gate, "evaluate", "--base", "base", "--label", "pr-123", "--fail-on", "never", env=env)
    assert d.returncode == 0, d.stderr
    decision = json.loads((repo / ".qa-mcp/release-gate/release-decision.json").read_text("utf8"))
    rules = {f["rule"] for f in decision["findings"]}
    assert decision["verdict"] == "block"
    assert "contract.breaks_critical_consumer" in rules      # mobile-app reads `total`
    assert "api.flow_failed" in rules                         # the shop's wrong order total
    assert decision["plan"]["needed"] == ["contract", "api_tests"]
    assert "llm" in decision["not_tested"] and "ui_heal" in decision["not_tested"]
