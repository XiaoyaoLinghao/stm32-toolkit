from __future__ import annotations

import json
import os
import shutil
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


def _write_support_manifest(support: Path, wheelhouse: Path, npm_cache: Path) -> Path:
    wheelhouse.mkdir(parents=True, exist_ok=True)
    npm_cache.mkdir(parents=True, exist_ok=True)
    manifest = support / "support-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "wheelhouse": str(wheelhouse.resolve()),
                "npmCache": str(npm_cache.resolve()),
                "git": str(REPO_ROOT / "bin" / "stm32-toolkit-mcp.cmd"),
                "node": str(REPO_ROOT / "bin" / "stm32-monitor.cmd"),
                "npm": str(REPO_ROOT / "bin" / "setup-stm32-env.ps1"),
                "python310": str(REPO_ROOT / ".claude-plugin" / "plugin.json"),
                "python312": str(REPO_ROOT / "README.md"),
                "cmdexec": str(Path(os.environ.get("COMSPEC", "cmd.exe"))),
                "chromium": str(REPO_ROOT / ".gitattributes"),
                "hashes": {},
            }
        ),
        encoding="utf-8",
    )
    return manifest


def _run_controller(
    tmp_path: Path,
    *,
    evidence: Path,
    git: str | None = None,
    node: str | None = None,
    code_head: str = "a" * 40,
    repo: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    repo = repo or (tmp_path / "repo")
    repo.mkdir(exist_ok=True)
    support = tmp_path / "support"
    support.mkdir()
    _write_support_manifest(support, tmp_path / "wheelhouse", tmp_path / "npm-cache")
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
        timeout=120,
    )


def test_controller_requires_support_manifest_in_support_root(tmp_path: Path) -> None:
    # The release verifier refuses a support root without support-manifest.json.
    verify = REPO_ROOT / "tools" / "release" / "verify_0502_release.py"
    support = tmp_path.resolve() / "support"
    support.mkdir()
    real_py = str(shutil.which("python3") or shutil.which("python") or "python")
    result = subprocess.run(
        [real_py, str(verify), "--support", str(support)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert result.returncode != 0
    assert "support-manifest.json" in result.stdout


def test_controller_rejects_head_not_equal_to_code_head_before_gates(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    real_git = str(shutil.which("git") or "git")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "tk-test")
    _git(repo, "config", "user.email", "tk-test@example.com")
    (repo / "f.txt").write_text("one\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "one")
    actual_head = _git(repo, "rev-parse", "HEAD").strip()
    # Request a DIFFERENT (still valid 40-hex) head so the identity gate fails.
    wrong = "0" * 40 if actual_head != "0" * 40 else "1" * 40
    result = _run_controller(tmp_path, evidence=evidence, code_head=wrong, git=real_git, repo=repo)
    assert result.returncode != 0
    assert "does not equal CodeHead" in result.stderr
    assert not list(evidence.glob("node-npm-ci.log"))
    # A failure must still produce the per-gate summary evidence.
    assert (evidence / "summary.json").exists()
    summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
    assert summary["overall"] == "FAIL"
    assert any(gate["gate"] == "git-head-identity" and gate["status"] == "FAIL" for gate in summary["gates"])


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
