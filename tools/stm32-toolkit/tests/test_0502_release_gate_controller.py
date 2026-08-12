from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
CONTROLLER = REPO_ROOT / "tools" / "release" / "run_0502_windows_gates.ps1"


@pytest.fixture(scope="module")
def controller_text() -> str:
    return CONTROLLER.read_text(encoding="utf-8")


def _powershell_ast(path: Path) -> dict:
    escaped = str(path).replace("'", "''")
    script = (
        "$errors = $null; $tokens = $null; "
        f"[void][System.Management.Automation.Language.Parser]::ParseFile('{escaped}', [ref]$tokens, [ref]$errors); "
        "if ($errors -and $errors.Count -gt 0) { throw ($errors | ForEach-Object { $_.Message }) -join ';' }; "
        "Write-Output 'parse-ok'"
    )
    result = subprocess.run(
        [
            os.environ.get("COMSPEC", "cmd.exe"),
            "/d",
            "/c",
            "powershell.exe",
            "-NoProfile",
            "-Command",
            script,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {"errors": [] if "parse-ok" in result.stdout else [result.stderr]}


def test_controller_parses_and_declares_exact_parameters(controller_text: str) -> None:
    parsed = _powershell_ast(CONTROLLER)
    assert parsed["errors"] == []
    for name in (
        "RepoRoot",
        "EvidenceRoot",
        "SupportRoot",
        "CodeHead",
        "Git",
        "Node",
        "Npm",
        "Python310",
        "Python312",
        "CmdExe",
    ):
        assert f"${name}" in controller_text or f"[string]${name}" in controller_text
        assert f"[Parameter(Mandatory = $true)][string]${name}" in controller_text


def test_controller_has_no_ambient_tool_or_remote_verbs(controller_text: str) -> None:
    text = controller_text.casefold()
    for forbidden in (
        "get-command",
        "where.exe",
        "invoke-expression",
        "git push",
        "git fetch",
        "gh pr",
        "pip install",
    ):
        assert forbidden not in text
    for bare in ("& git", "& node", "& npm", "& python", "& py", "& uv"):
        assert bare not in text


def test_controller_rejects_duplicate_tool_identity_before_gates(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    result = _run_controller(
        tmp_path,
        evidence=evidence,
        git=str(REPO_ROOT / "bin" / "stm32-monitor.cmd"),
        node=str(REPO_ROOT / "bin" / "stm32-monitor.cmd"),
    )
    assert result.returncode != 0
    assert "duplicate tool identity" in result.stderr
    assert not list(evidence.glob("*.log"))


def test_controller_requires_absolute_tool_paths(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    result = _run_controller(tmp_path, evidence=evidence, git="git")
    assert result.returncode != 0
    assert "must be rooted" in result.stderr


def test_controller_requires_clean_empty_evidence_root(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "existing.log").write_text("x", encoding="utf-8")
    result = _run_controller(tmp_path, evidence=evidence)
    assert result.returncode != 0
    assert "must be empty" in result.stderr


def test_controller_requires_code_head_as_full_sha(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    result = _run_controller(tmp_path, evidence=evidence, code_head="short")
    assert result.returncode != 0
    assert "one full SHA" in result.stderr


def _run_controller(
    tmp_path: Path,
    *,
    evidence: Path,
    git: str | None = None,
    node: str | None = None,
    code_head: str = "a" * 40,
) -> subprocess.CompletedProcess[str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    support = tmp_path / "support"
    support.mkdir()
    distinct = [
        str(REPO_ROOT / "bin" / "stm32-toolkit-mcp.cmd"),
        str(REPO_ROOT / "bin" / "stm32-monitor.cmd"),
        str(REPO_ROOT / "bin" / "setup-stm32-env.ps1"),
        str(REPO_ROOT / ".claude-plugin" / "plugin.json"),
        str(REPO_ROOT / "README.md"),
    ]
    selected_git = git or distinct[0]
    selected_node = node or distinct[1]
    return subprocess.run(
        [
            os.environ.get("COMSPEC", "cmd.exe"),
            "/d",
            "/c",
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(CONTROLLER),
            "-RepoRoot",
            str(repo),
            "-EvidenceRoot",
            str(evidence),
            "-SupportRoot",
            str(support),
            "-CodeHead",
            code_head,
            "-Git",
            selected_git,
            "-Node",
            selected_node,
            "-Npm",
            distinct[2],
            "-Python310",
            distinct[3],
            "-Python312",
            distinct[4],
            "-CmdExe",
            str(Path(os.environ.get("COMSPEC", "cmd.exe"))),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
