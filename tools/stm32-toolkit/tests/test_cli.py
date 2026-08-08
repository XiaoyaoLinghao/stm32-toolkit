import json
from pathlib import Path

from stm32_toolkit.cli import main
from stm32_toolkit.result import OperationResult

MIGRATE_EXPLANATION = (
    "Inspect the Keil project and convert ARMCC sources to GCC "
    "with a read-only plan and explicit authorization."
)


def test_version_command_writes_only_the_package_version(capsys):
    assert main(["version"]) == 0

    captured = capsys.readouterr()
    assert captured.out == "0.4.0\n"
    assert captured.err == ""


def test_detect_command_emits_a_json_result_envelope(tmp_path: Path, capsys):
    (tmp_path / "legacy.uvprojx").write_text("<Project/>", encoding="utf-8")

    assert main(["--project-root", str(tmp_path), "project", "detect", "--json"]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["operation"] == "project.detect"
    assert payload["data"] == {
        "kind": "keil",
        "files": ["legacy.uvprojx"],
        "recommended_action": {
            "id": "migrate-keil",
            "available": True,
            "explanation": MIGRATE_EXPLANATION,
        },
    }
    assert captured.err == ""


def test_context_failure_is_json_on_stdout_and_returns_two(tmp_path: Path, capsys):
    (tmp_path / ".stm32-project.json").write_text("{}", encoding="utf-8")

    assert main([
        "project",
        "context",
        "--project-root",
        str(tmp_path),
        "--data-root",
        str(tmp_path.parent / "data"),
        "--session-id",
        "session-a",
        "--json",
    ]) == 2

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["operation"] == "project.context"
    assert captured.err == ""


def test_json_commands_preserve_the_current_working_directory(tmp_path: Path, capsys):
    before = Path.cwd()

    assert main(["doctor", "--project-root", str(tmp_path), "--json"]) == 0

    assert Path.cwd() == before
    assert json.loads(capsys.readouterr().out)["operation"] == "doctor"


def test_unexpected_cli_error_goes_to_stderr_without_json(monkeypatch, tmp_path: Path, capsys):
    def explode(project_root: Path):
        raise RuntimeError("unexpected")

    monkeypatch.setattr("stm32_toolkit.cli.run_doctor", explode)

    assert main(["doctor", "--project-root", str(tmp_path), "--json"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "unexpected" in captured.err


def test_unserializable_doctor_result_goes_to_stderr_without_json(monkeypatch, tmp_path: Path, capsys):
    monkeypatch.setattr(
        "stm32_toolkit.cli.run_doctor",
        lambda project_root: OperationResult.success("doctor", {"invalid": object()}),
    )

    assert main(["doctor", "--project-root", str(tmp_path), "--json"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "internal error" in captured.err


def test_detect_filesystem_error_is_a_machine_readable_result(
    monkeypatch, tmp_path: Path, capsys
):
    """Catches detection I/O errors escaping to the generic stderr channel."""
    def unavailable(project_root: Path):
        raise OSError("directory unavailable")

    monkeypatch.setattr("stm32_toolkit.cli.detect_project", unavailable)

    exit_code = main([
        "project", "detect", "--project-root", str(tmp_path), "--json"
    ])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert payload["operation"] == "project.detect"
    assert payload["code"] == "PROJECT_DETECTION_UNAVAILABLE"
    assert payload["details"] == {"path": str(tmp_path)}
    assert captured.err == ""


# ---------------------------------------------------------------------------
# keil inspect / convert
# ---------------------------------------------------------------------------


def test_keil_inspect_command_emits_a_json_result_envelope(tmp_path: Path, capsys):
    root = _keil_repo(tmp_path)

    assert main(["keil", "inspect", "--project", str(root), "--json"]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["operation"] == "keil-inspect"
    assert payload["ok"] is True
    assert list(payload["data"]) == ["inspection", "baseline"]
    assert payload["data"]["inspection"]["device"] == "STM32F429ZGTx"
    assert captured.err == ""


def test_keil_inspect_accepts_project_root_alias_and_no_baseline(
    tmp_path: Path, capsys
):
    root = _keil_repo(tmp_path)

    assert main([
        "--project-root", str(root),
        "keil", "inspect", "--no-baseline", "--json",
    ]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["operation"] == "keil-inspect"
    assert payload["data"]["baseline"] is None


def test_keil_convert_dry_run_emits_a_deterministic_plan(tmp_path: Path, capsys):
    root = _keil_repo(tmp_path)

    assert main(["keil", "convert", "--project", str(root), "--dry-run", "--json"]) == 0
    first = json.loads(capsys.readouterr().out)

    assert main(["keil", "convert", "--project", str(root), "--dry-run", "--json"]) == 0
    second = json.loads(capsys.readouterr().out)

    assert first["operation"] == "keil-conversion-plan"
    assert first["ok"] is True
    assert first["data"]["plan_id"] == second["data"]["plan_id"]
    assert len(first["data"]["plan_id"]) == 64


def test_keil_convert_apply_is_authorized_two_phase(tmp_path: Path, capsys):
    root = _keil_repo(tmp_path)

    assert main(["keil", "convert", "--project", str(root), "--dry-run", "--json"]) == 0
    plan_id = json.loads(capsys.readouterr().out)["data"]["plan_id"]

    assert main([
        "keil", "convert", "--project", str(root),
        "--apply", "--plan-id", plan_id, "--authorized", "--json",
    ]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["operation"] == "keil-conversion-apply"
    assert payload["ok"] is True
    assert (root / ".stm32-project.json").is_file()
    assert captured.err == ""


def test_keil_convert_stale_plan_is_an_expected_failure(tmp_path: Path, capsys):
    root = _keil_repo(tmp_path)
    (root / "Main" / "main.c").write_text(
        (root / "Main" / "main.c").read_text(encoding="utf-8") + "/* edit */\n",
        encoding="utf-8",
    )

    assert main([
        "keil", "convert", "--project", str(root),
        "--apply", "--plan-id", "0" * 64, "--authorized", "--json",
    ]) == 2

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["operation"] == "keil-conversion-apply"
    assert payload["code"] == "PLAN_CHANGED"
    assert captured.err == ""


def test_keil_mode_conflicts_and_invalid_types_fail_without_mutation(
    tmp_path: Path, capsys
):
    root = _keil_repo(tmp_path)
    before = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }

    for argv in (
        ["keil", "convert", "--project", str(root), "--dry-run", "--apply", "--json"],
        ["keil", "convert", "--project", str(root), "--apply", "--json"],
        ["keil", "convert", "--project", str(root), "--authorized", "--json"],
        ["build", "--project", str(root)],
        ["build", "--project", str(root), "--preset", "arm-fast"],
    ):
        assert main(argv) == 2
        captured = capsys.readouterr()
        assert captured.out == ""

    # apply without the explicit --authorized flag is an expected domain
    # failure: exit 2, one JSON document on stdout, empty stderr, no writes.
    assert main([
        "keil", "convert", "--project", str(root),
        "--apply", "--plan-id", "0" * 64, "--json",
    ]) == 2
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["code"] == "AUTHORIZATION_REQUIRED"
    assert captured.err == ""

    after = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }
    assert after == before


def test_unexpected_workflow_error_is_internal_failure(
    monkeypatch, tmp_path: Path, capsys
):
    root = _keil_repo(tmp_path)

    def explode(project_root, **kwargs):
        raise RuntimeError("adapter exploded")

    monkeypatch.setattr("stm32_toolkit.cli.inspect_keil_workflow", explode)

    assert main(["keil", "inspect", "--project", str(root), "--json"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "adapter exploded" in captured.err


# ---------------------------------------------------------------------------
# project configure
# ---------------------------------------------------------------------------


def test_project_configure_dry_run_emits_a_plan(tmp_path: Path, capsys):
    root = _configured_repo(tmp_path)

    assert main(["project", "configure", "--project", str(root), "--dry-run", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["operation"] == "project-configuration-plan"
    assert payload["ok"] is True
    assert len(payload["data"]["plan_id"]) == 64


def test_project_configure_apply_requires_authorization(tmp_path: Path, capsys):
    root = _configured_repo(tmp_path)

    assert main([
        "project", "configure", "--project", str(root),
        "--apply", "--plan-id", "0" * 64, "--authorized", "--json",
    ]) == 2

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["operation"] == "project-configuration-apply"
    assert payload["code"] == "PLAN_CHANGED"
    assert captured.err == ""


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


def test_build_command_emits_json_by_default(tmp_path: Path, monkeypatch, capsys):
    from test_build_runner import install_fake_cmake

    root = _configured_repo(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)

    assert main(["build", "--project", str(root), "--preset", "arm-debug"]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["operation"] == "build"
    assert payload["ok"] is True
    assert payload["data"]["identity"]["preset"] == "arm-debug"
    assert captured.err == ""


def test_build_command_accepts_clean_and_timeout(tmp_path: Path, monkeypatch, capsys):
    from test_build_runner import install_fake_cmake

    root = _configured_repo(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)

    assert main([
        "build", "--project", str(root), "--preset", "arm-debug",
        "--clean", "--timeout-seconds", "120", "--json",
    ]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True


# ---------------------------------------------------------------------------
# end-to-end gate through the CLI
# ---------------------------------------------------------------------------


def test_end_to_end_inspect_convert_configure_build(tmp_path: Path, monkeypatch, capsys):
    """The complete two-phase workflow chain through the CLI grammar."""
    import hashlib
    import subprocess

    from test_mcp_migration_build import convertible_fixture_copy

    root = convertible_fixture_copy(tmp_path)
    from test_build_runner import install_fake_cmake

    install_fake_cmake(monkeypatch, tmp_path)

    # inspect
    assert main(["keil", "inspect", "--project", str(root), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["operation"] == "keil-inspect"

    # conversion plan -> apply
    assert main(["keil", "convert", "--project", str(root), "--dry-run", "--json"]) == 0
    plan_id = json.loads(capsys.readouterr().out)["data"]["plan_id"]
    assert main([
        "keil", "convert", "--project", str(root),
        "--apply", "--plan-id", plan_id, "--authorized", "--json",
    ]) == 0
    applied = json.loads(capsys.readouterr().out)
    assert applied["operation"] == "keil-conversion-apply"

    # The generated manifest is used exactly as produced: the debug spec
    # stays empty and build-only configuration must still succeed.
    manifest_path = root / ".stm32-project.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schemaVersion"] == 2
    assert manifest["debug"] == {}

    # configuration plan -> apply
    assert main(["project", "configure", "--project", str(root), "--dry-run", "--json"]) == 0
    configure_id = json.loads(capsys.readouterr().out)["data"]["plan_id"]
    assert main([
        "project", "configure", "--project", str(root),
        "--apply", "--plan-id", configure_id, "--authorized", "--json",
    ]) == 0
    configured = json.loads(capsys.readouterr().out)
    assert configured["operation"] == "project-configuration-apply"
    launch = json.loads((root / ".vscode" / "launch.json").read_text(encoding="utf-8"))
    assert launch["configurations"] == []

    # build
    assert main(["build", "--project", str(root), "--preset", "arm-debug"]) == 0
    built = json.loads(capsys.readouterr().out)
    assert built["operation"] == "build"
    assert built["ok"] is True

    # linked evidence chain
    report = json.loads(
        (root / "artifacts" / "migration" / "conversion-report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["planId"] == plan_id
    assert (root / ".stm32-toolkit" / "generated-files.json").is_file()
    build_result = json.loads(
        (root / "artifacts" / "migration" / "build-result.json").read_text(
            encoding="utf-8"
        )
    )
    assert build_result["status"] == "success"
    assert build_result["gitHead"] == report["gitHead"]
    identity = built["data"]["identity"]
    elf = (root / "build" / "arm-debug" / "legacy.elf").read_bytes()
    assert identity["elfSha256"] == hashlib.sha256(elf).hexdigest()
    assert identity["gitHead"] == report["gitHead"]
    assert subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip() == report["gitHead"]


# ---------------------------------------------------------------------------
# fixture helpers
# ---------------------------------------------------------------------------

COMMON_C = (
    "/* common.c */\n"
    '#include "stm32f4xx.h"\n'
    "\n"
    "__irq void systick_isr(void)\n"
    "{\n"
    "    __nop();\n"
    "    __wfi();\n"
    "}\n"
    "\n"
    '__asm("nop");\n'
    "\n"
    '__attribute__((section(".common.data"))) int shared_value;\n'
    "__attribute__((at(0x20000000))) int pinned_value;\n"
    "\n"
    "int common_work(void) { return 0; }\n"
)

MAIN_C = (
    "/* main.c */\n"
    '#include "stm32f4xx.h"\n'
    "\n"
    "__irq void early_init(void) { __nop(); }\n"
    "\n"
    "int main(void) { return 0; }\n"
)


def _keil_repo(tmp_path: Path) -> Path:
    from test_migration_apply import build_repo

    return build_repo(
        tmp_path,
        files={"Main/main.c": MAIN_C, "Common/common.c": COMMON_C},
        gitignore="build/\n.stm32-toolkit/build.lock\n__pycache__/\n*.pyc\n",
    )


def _configured_repo(tmp_path: Path) -> Path:
    from test_build_runner import prepare_project

    return prepare_project(tmp_path)
