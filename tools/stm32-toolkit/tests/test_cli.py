import json
from pathlib import Path

from stm32_toolkit.cli import main
from stm32_toolkit.result import OperationResult


def test_version_command_writes_only_the_package_version(capsys):
    assert main(["version"]) == 0

    captured = capsys.readouterr()
    assert captured.out == "0.2.0\n"
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
            "available": False,
            "explanation": "Keil migration is planned but unavailable in this foundation release.",
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
