import json
import os
import subprocess
from pathlib import Path

import pytest

from stm32_toolkit.cli import main
from stm32_toolkit.result import OperationResult

MIGRATE_EXPLANATION = (
    "Inspect the Keil project and convert ARMCC sources to GCC "
    "with a read-only plan and explicit authorization."
)


def test_version_command_writes_only_the_package_version(capsys):
    assert main(["version"]) == 0

    captured = capsys.readouterr()
    assert captured.out == "1.3.3\n"
    assert captured.err == ""


def test_doctor_without_explicit_project_root_fails_before_workflow(monkeypatch, capsys):
    called = False

    def unexpected(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("workflow must not run")

    monkeypatch.setattr("stm32_toolkit.cli._operation_result", unexpected)
    assert main(["doctor", "--json"]) == 2
    assert called is False
    assert capsys.readouterr().err == "stm32-toolkit: invalid arguments\n"


def test_project_detect_without_explicit_root_never_uses_current_directory(
    monkeypatch, capsys
):
    with monkeypatch.context() as context:
        context.setattr(
            "stm32_toolkit.cli.Path.cwd",
            lambda: (_ for _ in ()).throw(AssertionError("cwd fallback")),
        )
        assert main(["project", "detect", "--json"]) == 2
    assert capsys.readouterr().err == "stm32-toolkit: invalid arguments\n"


def test_version_is_the_only_root_free_command(capsys):
    assert main(["version"]) == 0
    assert capsys.readouterr().out == "1.3.3\n"


@pytest.mark.parametrize(
    "argv",
    [
        [
            "--project-root",
            "C:/one",
            "build",
            "--project-root",
            "C:/two",
            "--preset",
            "arm-debug",
            "--json",
        ],
        [
            "--project-root",
            "C:/one",
            "probe",
            "list",
            "--project-root",
            "C:/two",
            "--data-root",
            "C:/data",
            "--session-id",
            "s",
            "--json",
        ],
        [
            "--project-root",
            "C:/one",
            "test",
            "discover",
            "--project-root",
            "C:/two",
            "--data-root",
            "C:/data",
            "--session-id",
            "s",
            "--mode",
            "host",
            "--json",
        ],
        [
            "--project-root",
            "C:/one",
            "diagnose",
            "start",
            "run-1",
            "--project-root",
            "C:/two",
            "--data-root",
            "C:/data",
            "--session-id",
            "s",
            "--operation-id",
            "op",
            "--json",
        ],
    ],
)
def test_workflow_contexts_reject_global_and_command_local_project_roots(argv):
    with pytest.raises(SystemExit) as raised:
        from stm32_toolkit.cli import _build_parser

        _build_parser().parse_args(argv)
    assert raised.value.code == 2


@pytest.mark.parametrize(
    "argv",
    [
        [
            "--project-root",
            "C:/one",
            "probe",
            "list",
            "--data-root",
            "C:/data",
            "--session-id",
            "s",
            "--json",
        ],
        [
            "--project-root",
            "C:/one",
            "test",
            "discover",
            "--data-root",
            "C:/data",
            "--session-id",
            "s",
            "--mode",
            "host",
            "--json",
        ],
        [
            "--project-root",
            "C:/one",
            "diagnose",
            "start",
            "run-1",
            "--data-root",
            "C:/data",
            "--session-id",
            "s",
            "--operation-id",
            "op",
            "--json",
        ],
    ],
)
def test_global_project_root_satisfies_each_local_context(argv):
    from stm32_toolkit.cli import _build_parser

    args = _build_parser().parse_args(argv)
    assert args.project_root == Path("C:/one")


@pytest.mark.parametrize("value", ["", "${PROJECT_ROOT}", "relative"])
def test_invalid_project_root_values_fail_before_workflow(monkeypatch, capsys, value):
    called = False

    def unexpected(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("workflow must not run")

    monkeypatch.setattr("stm32_toolkit.cli._operation_result", unexpected)
    assert main(["doctor", "--project-root", value, "--json"]) == 2
    assert called is False
    assert capsys.readouterr().err == "stm32-toolkit: invalid arguments\n"


def test_parser_rejects_relative_project_root_before_dispatch():
    from stm32_toolkit.cli import _build_parser

    with pytest.raises(SystemExit):
        _build_parser().parse_args(["doctor", "--project-root", "relative", "--json"])


@pytest.mark.skipif(os.name != "nt", reason="Windows directory junction")
def test_redirected_project_root_fails_before_workflow(monkeypatch, tmp_path: Path, capsys):
    target = tmp_path / "target"
    target.mkdir()
    redirected = tmp_path / "redirected"
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(redirected), str(target)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip("directory junctions unavailable")

    called = False

    def unexpected(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("workflow must not run")

    monkeypatch.setattr("stm32_toolkit.cli._operation_result", unexpected)
    assert main(["doctor", "--project-root", str(redirected), "--json"]) == 2
    assert called is False
    assert capsys.readouterr().err == "stm32-toolkit: invalid arguments\n"


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

    assert main(
        [
            "doctor",
            "--project-root",
            str(tmp_path),
            "--skip-vscode-extensions",
            "--json",
        ]
    ) == 0

    assert Path.cwd() == before
    assert json.loads(capsys.readouterr().out)["operation"] == "doctor"


def test_doctor_cli_propagates_observation_options(monkeypatch, tmp_path: Path, capsys):
    calls: list[dict[str, object]] = []

    def capture(project_root: Path, **kwargs):
        calls.append({"project_root": project_root, **kwargs})
        return OperationResult.success("doctor", {})

    monkeypatch.setattr("stm32_toolkit.cli.run_doctor", capture)
    vscode = tmp_path / "Code.exe"
    uv4 = tmp_path / "UV4.exe"
    armcc = tmp_path / "armcc.exe"

    assert main(
        [
            "doctor",
            "--project-root",
            str(tmp_path),
            "--skip-vscode-extensions",
            "--vscode-path",
            str(vscode),
            "--uv4-path",
            str(uv4),
            "--armcc-path",
            str(armcc),
            "--json",
        ]
    ) == 0

    assert calls == [
        {
            "project_root": tmp_path,
            "probe_vscode_extensions": False,
            "vscode_path": vscode,
            "uv4_path": uv4,
            "armcc_path": armcc,
        }
    ]


def test_doctor_cli_defaults_to_extension_probing(monkeypatch, tmp_path: Path, capsys):
    calls: list[dict[str, object]] = []

    def capture(project_root: Path, **kwargs):
        calls.append(kwargs)
        return OperationResult.success("doctor", {})

    monkeypatch.setattr("stm32_toolkit.cli.run_doctor", capture)

    assert main(["doctor", "--project-root", str(tmp_path), "--json"]) == 0

    assert calls == [
        {
            "probe_vscode_extensions": True,
            "vscode_path": None,
            "uv4_path": None,
            "armcc_path": None,
        }
    ]


def test_unexpected_cli_error_goes_to_stderr_without_json(monkeypatch, tmp_path: Path, capsys):
    def explode(project_root: Path, **_kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr("stm32_toolkit.cli.run_doctor", explode)

    assert main(["doctor", "--project-root", str(tmp_path), "--json"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "unexpected" in captured.err


def test_unserializable_doctor_result_goes_to_stderr_without_json(monkeypatch, tmp_path: Path, capsys):
    monkeypatch.setattr(
        "stm32_toolkit.cli.run_doctor",
        lambda project_root, **_kwargs: OperationResult.success(
            "doctor", {"invalid": object()}
        ),
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


def _destination(tmp_path: Path, name: str = "gcc-project") -> Path:
    parent = tmp_path / "delivery"
    parent.mkdir(parents=True, exist_ok=True)
    return parent / name


def test_keil_convert_dry_run_emits_a_deterministic_delivery_plan(
    tmp_path: Path, capsys
):
    root = _keil_repo(tmp_path)
    destination = _destination(tmp_path)

    assert main([
        "keil", "convert", "--project", str(root), "--destination", str(destination),
        "--dry-run", "--json",
    ]) == 0
    first = json.loads(capsys.readouterr().out)

    assert main([
        "keil", "convert", "--project", str(root), "--destination", str(destination),
        "--dry-run", "--json",
    ]) == 0
    second = json.loads(capsys.readouterr().out)

    assert first["operation"] == "keil-conversion-plan"
    assert first["ok"] is True
    assert first["data"]["planId"] == second["data"]["planId"]
    assert len(first["data"]["planId"]) == 64
    assert first["data"]["built"] is False
    assert first["data"]["flashed"] is False
    assert not destination.exists()


def test_keil_convert_requires_a_destination(tmp_path: Path, capsys):
    root = _keil_repo(tmp_path)

    assert main([
        "keil", "convert", "--project", str(root), "--dry-run", "--json",
    ]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["operation"] == "keil-conversion-plan"
    assert payload["code"] == "DELIVERY_DESTINATION_REQUIRED"
    assert payload["details"]["field"] == "destination"


def test_keil_convert_apply_is_authorized_two_phase(tmp_path: Path, capsys):
    root = _keil_repo(tmp_path)
    destination = _destination(tmp_path)

    assert main([
        "keil", "convert", "--project", str(root), "--destination", str(destination),
        "--dry-run", "--json",
    ]) == 0
    plan_id = json.loads(capsys.readouterr().out)["data"]["planId"]

    assert main([
        "keil", "convert", "--project", str(root), "--destination", str(destination),
        "--apply", "--plan-id", plan_id, "--authorized", "--json",
    ]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["operation"] == "keil-conversion-apply"
    assert payload["ok"] is True
    assert payload["data"]["outputRoot"] == str(destination)
    assert payload["data"]["built"] is False
    assert payload["data"]["flashed"] is False
    assert (destination / ".stm32-project.json").is_file()
    assert not (root / ".stm32-project.json").exists()
    assert captured.err == ""


def test_keil_convert_stale_plan_is_an_expected_failure(tmp_path: Path, capsys):
    root = _keil_repo(tmp_path)
    destination = _destination(tmp_path)
    (root / "Main" / "main.c").write_text(
        (root / "Main" / "main.c").read_text(encoding="utf-8") + "/* edit */\n",
        encoding="utf-8",
    )

    assert main([
        "keil", "convert", "--project", str(root), "--destination", str(destination),
        "--apply", "--plan-id", "0" * 64, "--authorized", "--json",
    ]) == 2

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["operation"] == "keil-conversion-apply"
    assert payload["code"] == "PLAN_CHANGED"
    assert not destination.exists()
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
    assert payload["data"]["vscodeGuidance"]["bindingMode"] == "user-settings"


def test_project_configure_cli_guidance_and_failure_status_are_preserved(
    tmp_path: Path, capsys
):
    root = _configured_repo(tmp_path)

    assert main([
        "project", "configure", "--project", str(root), "--dry-run", "--json",
    ]) == 0
    plan = json.loads(capsys.readouterr().out)
    guidance = plan["data"]["vscodeGuidance"]
    assert list(guidance["requiredUserSettings"]) == [
        "stm32-toolkit.executablePath",
        "stm32-toolkit.compilerPath",
    ]
    assert guidance["userSettingsChecked"] is False
    assert [entry["code"] for entry in guidance["diagnostics"]] == [
        "VSCODE_EXECUTABLE_SETTINGS_REQUIRED"
    ]

    # A failed apply keeps its nonzero status, structured code, and null data;
    # no guidance is invented for a failure.
    assert main([
        "project", "configure", "--project", str(root),
        "--apply", "--plan-id", plan["data"]["plan_id"], "--json",
    ]) == 2
    captured = capsys.readouterr()
    failure = json.loads(captured.out)
    assert failure["ok"] is False
    assert failure["code"] == "AUTHORIZATION_REQUIRED"
    assert failure["data"] is None
    assert captured.err == ""

    assert main([
        "project", "configure", "--project", str(root),
        "--apply", "--plan-id", plan["data"]["plan_id"], "--authorized", "--json",
    ]) == 0
    applied = json.loads(capsys.readouterr().out)
    assert applied["operation"] == "project-configuration-apply"
    assert applied["data"]["vscodeGuidance"]["bindingMode"] == "user-settings"
    assert [
        entry["code"] for entry in applied["data"]["vscodeGuidance"]["diagnostics"]
    ] == ["VSCODE_EXECUTABLE_SETTINGS_REQUIRED"]


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


def test_build_command_returns_stale_guidance_json(
    tmp_path: Path, monkeypatch, capsys
):
    from test_build_runner import hit_records, install_fake_cmake

    from stm32_toolkit.build import runner as runner_mod

    root = _configured_repo(tmp_path)
    hit_file = install_fake_cmake(monkeypatch, tmp_path)
    assert main(["build", "--project", str(root), "--preset", "arm-debug"]) == 0
    capsys.readouterr()

    (root / "Src" / "main.c").write_text(
        "int main(void) { return 45; }\n", encoding="utf-8"
    )
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    assert main([
        "build", "--project", str(root), "--preset", "arm-debug",
        "--timeout-seconds", "321",
    ]) == 2

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["operation"] == "build"
    assert payload["code"] == "BUILD_OUTPUT_STALE"
    details = payload["details"]
    assert details["reason"] == "input-snapshot-mismatch"
    assert details["evidenceField"] == "inputSnapshotSha256"
    assert details["cleanRequested"] is False
    remediation = details["remediation"]
    assert remediation["action"] == "clean-rebuild"
    assert remediation["cli"]["executable"] == "caller-verified-stm32-toolkit"
    assert remediation["cli"]["workingDirectory"] == "project-root"
    project_root_binding = remediation["cli"]["projectRoot"]
    assert project_root_binding == {
        "option": "--project-root",
        "valueFrom": "same-bound-project-root",
        "required": True,
    }
    arguments = remediation["cli"]["arguments"]
    assert arguments == [
        "build", "--preset", "arm-debug", "--clean", "--timeout-seconds", "321",
    ]
    assert remediation["mcp"]["arguments"] == {
        "preset": "arm-debug", "clean": True, "timeoutSeconds": 321,
    }
    assert "authorized" not in remediation["mcp"]["arguments"]

    # ``arguments`` is only the command tail.  Even with the project root as
    # the current directory, the explicit absolute binding is required, so
    # the bare tail must be rejected before CMake runs.
    monkeypatch.chdir(root)
    hits_before = len(hit_records(hit_file))
    assert main(arguments) == 2
    capsys.readouterr()
    assert len(hit_records(hit_file)) == hits_before

    # Replay the returned tokens through the public grammar in the same bound
    # project root, using the returned metadata for the required option.
    # Removing the no-output switch makes the synthetic clean build write
    # fresh outputs, so this proves the advice is accepted.
    monkeypatch.delenv("FAKE_CMAKE_NO_OUTPUT")
    timeouts: list[int] = []
    real_run_process = runner_mod.run_process

    def recording_run_process(request):
        timeouts.append(request.timeout_seconds)
        return real_run_process(request)

    monkeypatch.setattr(runner_mod, "run_process", recording_run_process)

    assert main([project_root_binding["option"], str(root), *arguments]) == 0

    replay = json.loads(capsys.readouterr().out)
    assert replay["ok"] is True
    assert replay["data"]["identity"]["preset"] == "arm-debug"
    assert timeouts == [321, 321]

    log_text = (
        root / "artifacts" / "migration" / "build.log"
    ).read_text(encoding="utf-8")
    assert "[stage:configure]" in log_text
    assert "[stage:build]" in log_text
    assert '"--clean-first"' in log_text
    assert '"--preset", "arm-debug"' in log_text

    records = [
        json.loads(line)
        for line in hit_file.read_text(encoding="utf-8").splitlines()
    ]
    build_calls = [
        item["argv"]
        for item in records
        if item["argv"][:2] == ["--build", "--preset"]
    ]
    assert build_calls[-1] == [
        "--build", "--preset", "arm-debug", "--clean-first",
    ]


# ---------------------------------------------------------------------------
# end-to-end gate through the CLI
# ---------------------------------------------------------------------------


def test_end_to_end_inspect_convert_configure_build(tmp_path: Path, monkeypatch, capsys):
    """Independent delivery -> configure -> build through the CLI grammar."""
    import hashlib

    from test_mcp_migration_build import convertible_fixture_copy
    from test_migration_apply import snapshot_tree

    root = convertible_fixture_copy(tmp_path)
    from test_build_runner import install_fake_cmake

    install_fake_cmake(monkeypatch, tmp_path)
    source_before = snapshot_tree(root)
    destination = _destination(tmp_path, "delivered-project")

    # inspect
    assert main(["keil", "inspect", "--project", str(root), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["operation"] == "keil-inspect"

    # conversion plan -> apply into a new independent output root
    assert main([
        "keil", "convert", "--project", str(root), "--destination", str(destination),
        "--dry-run", "--json",
    ]) == 0
    plan = json.loads(capsys.readouterr().out)
    plan_id = plan["data"]["planId"]
    assert plan["data"]["built"] is False
    assert main([
        "keil", "convert", "--project", str(root), "--destination", str(destination),
        "--apply", "--plan-id", plan_id, "--authorized", "--json",
    ]) == 0
    applied = json.loads(capsys.readouterr().out)
    assert applied["operation"] == "keil-conversion-apply"
    assert applied["data"]["outputRoot"] == str(destination)
    assert applied["data"]["built"] is False
    assert applied["data"]["flashed"] is False
    # The Keil source tree is untouched; the output is a separate project.
    assert snapshot_tree(root) == source_before
    assert not (root / ".stm32-project.json").exists()

    # The generated manifest is used exactly as produced: the debug spec
    # stays empty and build-only configuration must still succeed.
    manifest_path = destination / ".stm32-project.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schemaVersion"] == 3
    assert manifest["debug"] == {}

    # configuration plan -> apply at the delivered output root
    assert main([
        "project", "configure", "--project", str(destination), "--dry-run", "--json",
    ]) == 0
    configure_id = json.loads(capsys.readouterr().out)["data"]["plan_id"]
    assert main([
        "project", "configure", "--project", str(destination),
        "--apply", "--plan-id", configure_id, "--authorized", "--json",
    ]) == 0
    configured = json.loads(capsys.readouterr().out)
    assert configured["operation"] == "project-configuration-apply"
    launch = json.loads(
        (destination / ".vscode" / "launch.json").read_text(encoding="utf-8")
    )
    assert launch["configurations"] == []

    # build at the delivered output root (no Git repository was delivered)
    assert main(["build", "--project", str(destination), "--preset", "arm-debug"]) == 0
    built = json.loads(capsys.readouterr().out)
    assert built["operation"] == "build"
    assert built["ok"] is True
    assert built["data"]["identity"]["sourceBaseline"] == "input-snapshot-v1"
    assert built["data"]["identity"]["gitHead"] is None
    assert built["data"]["identity"]["gitDirty"] is None

    # linked evidence chain: schema-2 report content identity, then build
    report = json.loads(
        (
            destination / "artifacts" / "migration" / "conversion-report.json"
        ).read_text(encoding="utf-8")
    )
    assert report["schemaVersion"] == 2
    assert report["contentId"] == applied["data"]["contentId"]
    assert "planId" not in report
    assert "gitHead" not in report
    assert (
        destination / ".stm32-toolkit" / "generated-files.json"
    ).is_file()
    build_result = json.loads(
        (
            destination / "artifacts" / "migration" / "build-result.json"
        ).read_text(encoding="utf-8")
    )
    assert build_result["status"] == "success"
    assert build_result["sourceBaseline"] == "input-snapshot-v1"
    assert build_result["gitHead"] is None
    identity = built["data"]["identity"]
    elf = (destination / "build" / "arm-debug" / "legacy.elf").read_bytes()
    assert identity["elfSha256"] == hashlib.sha256(elf).hexdigest()
    assert identity["buildId"] == build_result["buildId"]
    assert not (destination / ".git").exists()


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


# ---------------------------------------------------------------------------
# internal-error boundaries and hardware failure names
# ---------------------------------------------------------------------------


def _hardware_argv(command: list[str]) -> list[str]:
    return [
        *command,
        "--project",
        str(Path.cwd()),
        "--data-root",
        str(Path.cwd().parent / "data"),
        "--session-id",
        "session-a",
    ]


def test_long_internal_error_message_is_truncated(monkeypatch, tmp_path: Path, capsys):
    def explode(project_root: Path, **_kwargs):
        raise RuntimeError("x" * 1000)

    monkeypatch.setattr("stm32_toolkit.cli.run_doctor", explode)

    assert main(["doctor", "--project-root", str(tmp_path), "--json"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "stm32-toolkit: internal error: " in captured.err
    # 500 x's survive, then an ellipsis is appended in place of the tail.
    assert "x" * 500 in captured.err
    assert not captured.err.endswith("x")
    assert captured.err.rstrip().endswith("...")


def test_bounded_int_rejects_non_integer(monkeypatch, tmp_path: Path, capsys):
    assert main(
        _hardware_argv(
            [
                "read",
                "sample",
                "--probe",
                "probe-a",
                "--expected-build-id",
                "b" * 64,
                "--expected-elf-sha256",
                "e" * 64,
                "--expression",
                "counter",
                "--interval-ms",
                "abc",
            ]
        )
    ) == 2
    assert capsys.readouterr().out == ""


def test_authorized_requires_apply_mode(monkeypatch, tmp_path: Path, capsys):
    root = _keil_repo(tmp_path)

    assert main(
        ["keil", "convert", "--project", str(root), "--dry-run", "--authorized", "--json"]
    ) == 2
    assert capsys.readouterr().out == ""


def test_hardware_failures_map_to_stable_operation_names(
    monkeypatch, tmp_path: Path, capsys
):
    root = _keil_repo(tmp_path)
    data_root = str(root.parent / "data")
    session_id = "session-a"
    probe = "probe-a"
    build_id = "b" * 64
    elf = "e" * 64

    def explode(*_args, **_kwargs):
        raise RuntimeError("SECRET hardware failure")

    cases = [
        (
            ["probe", "list"],
            "stm32_probe_list",
            "stm32_toolkit.cli.probe_list_workflow",
        ),
        (
            [
                "flash",
                "--probe", probe,
                "--expected-build-id", build_id,
                "--expected-elf-sha256", elf,
            ],
            "stm32_flash",
            "stm32_toolkit.cli.flash_workflow",
        ),
        (
            [
                "debug", "handoff", "begin",
                "--probe", probe,
                "--expected-build-id", build_id,
                "--expected-elf-sha256", elf,
            ],
            "stm32_debug_handoff_begin",
            "stm32_toolkit.cli.handoff_begin_workflow",
        ),
        (
            ["debug", "handoff", "end", "--probe", probe, "--ticket", "ticket-1"],
            "stm32_debug_handoff_end",
            "stm32_toolkit.cli.handoff_end_workflow",
        ),
        (
            [
                "read", "variable",
                "--probe", probe,
                "--expected-build-id", build_id,
                "--expected-elf-sha256", elf,
                "--expression", "counter",
            ],
            "stm32_variable_read",
            "stm32_toolkit.cli.variable_read_workflow",
        ),
        (
            [
                "read", "sample",
                "--probe", probe,
                "--expected-build-id", build_id,
                "--expected-elf-sha256", elf,
                "--expression", "counter",
                "--interval-ms", "1000",
                "--count", "1",
            ],
            "stm32_variable_sample",
            "stm32_toolkit.cli.variable_sample_workflow",
        ),
        (
            [
                "read", "register",
                "--probe", probe,
                "--expected-build-id", build_id,
                "--expected-elf-sha256", elf,
                "--path", "GPIOA.IDR",
            ],
            "stm32_register_read",
            "stm32_toolkit.cli.register_read_workflow",
        ),
        (
            [
                "fault",
                "--probe", probe,
                "--expected-build-id", build_id,
                "--expected-elf-sha256", elf,
            ],
            "stm32_fault_analyze",
            "stm32_toolkit.cli.fault_workflow",
        ),
    ]

    for argv, operation, target in cases:
        monkeypatch.setattr(target, explode)
        args = [*argv, "--project", str(root), "--data-root", data_root, "--session-id", session_id]
        assert main(args) == 2, operation
        captured = capsys.readouterr()
        assert captured.out, operation
        payload = json.loads(captured.out)
        assert payload["operation"] == operation
        assert payload["code"] == "HARDWARE_INTERNAL_ERROR"
        assert captured.err == ""
        assert "SECRET" not in captured.out


def test_operation_result_asserts_on_unhandled_command():
    from types import SimpleNamespace

    from stm32_toolkit.cli import _operation_result

    with pytest.raises(AssertionError):
        _operation_result(SimpleNamespace(command="bogus"), Path.cwd())


def test_main_guard_raises_system_exit_when_run_as_module(monkeypatch, capsys):
    import runpy
    import sys

    monkeypatch.setattr(sys, "argv", ["stm32-toolkit", "version"])
    with pytest.raises(SystemExit) as caught:
        runpy.run_module("stm32_toolkit.cli", run_name="__main__")
    assert caught.value.code == 0


def test_package_lazy_attributes_and_unknown_attribute_error() -> None:
    import stm32_toolkit
    from stm32_toolkit import MonitorObservationRequest, open_monitor_observation

    assert stm32_toolkit.__version__ == "1.3.3"
    assert callable(MonitorObservationRequest)
    assert callable(open_monitor_observation)
    # The lazily imported attribute is cached on the package.
    assert stm32_toolkit.open_monitor_observation is open_monitor_observation
    with pytest.raises(AttributeError):
        stm32_toolkit.no_such_attribute
