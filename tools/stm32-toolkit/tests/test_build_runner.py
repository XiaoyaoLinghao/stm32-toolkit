"""Build runner contract tests (STM32TK-0305).

The runner drives ``cmake --preset`` configure and ``cmake --build --preset``
stages through the bounded process layer, validates the resulting ELF/MAP
evidence, and publishes log -> identity -> result atomically with the result
as the freshness commit point.  A fake ``cmake`` executable replaces the real
toolchain (real CMake/Ninja/ARM GNU builds are a Codex gate).
"""

from __future__ import annotations

import json
import os
import shutil
import struct
import sys
from pathlib import Path

import pytest

import stm32_toolkit.build.identity as identity_mod
import stm32_toolkit.build.runner as runner_mod
from stm32_toolkit.build.identity import BuildError, validate_identity_document
from stm32_toolkit.build.model import BuildRequest, MemoryUsage
from stm32_toolkit.build.runner import run_build

FIXTURE = Path(__file__).parent / "fixtures" / "minimal-gcc"

# A Python fake for the `cmake` executable.  It is written to a disposable
# bin directory at test time and placed first on PATH.  The real toolchain
# gate (CMake 4.3.1, Ninja 1.13.2, ARM GNU 14.3.1) is a Codex gate.
FAKE_CMAKE = r'''#!/usr/bin/env python3
import json
import os
import struct
import sys


def write_elf(path):
    def shstrtab(names):
        out = b"\x00"
        offsets = {}
        for name in names:
            offsets[name] = len(out)
            out += name.encode("ascii") + b"\x00"
        return out, offsets

    shstr, sh_offs = shstrtab([".shstrtab", ".isr_vector", ".text", ".symtab", ".strtab"])
    strtab = b"\x00Reset_Handler\x00main\x00"
    syms = struct.pack("<IIIBBH", 0, 0, 0, 0, 0, 0)
    syms += struct.pack("<IIIBBH", 1, 0x08000401, 2, 0x12, 0, 3)
    syms += struct.pack("<IIIBBH", 14, 0x08000405, 2, 0x12, 0, 3)
    isr_off = 52 + 40 * 6
    text_off = isr_off + 0x400
    symtab_off = text_off + 0x10
    strtab_off = symtab_off + len(syms)
    shstr_off = strtab_off + len(strtab)
    specs = [(".shstrtab", 3, 0, 0, shstr_off, len(shstr))]
    specs.append((".isr_vector", 1, 2, 0x08000000, isr_off, 0x400))
    specs.append((".text", 1, 6, 0x08000400, text_off, 0x10))
    symtab_index = len(specs)
    specs.append((".symtab", 2, 0, 0, symtab_off, len(syms)))
    strtab_index = len(specs)
    specs.append((".strtab", 3, 0, 0, strtab_off, len(strtab)))
    shdrs = [struct.pack("<IIIIIIIIII", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)]
    for index, (name, typ, flags, addr, off, size) in enumerate(specs):
        link = strtab_index if index == symtab_index else 0
        info = 1 if index == symtab_index else 0
        entsize = 16 if index == symtab_index else 0
        align = 4 if index == symtab_index else 1
        shdrs.append(struct.pack("<IIIIIIIIII", sh_offs[name], typ, flags, addr, off,
                                 size, link, info, align, entsize))
    header = struct.pack(
        "<16sHHIIIIIHHHHHH",
        b"\x7fELF" + bytes([1, 1, 1, 0]) + b"\x00" * 8,
        2, 40, 1, 0x08000401, 0, 52, 0x05000000, 52, 0, 0, 40, len(shdrs), 1,
    )
    with open(path, "wb") as f:
        f.write(header + b"".join(shdrs))
        f.write(b"\x00" * (isr_off - 52 - 40 * len(shdrs)))
        f.write(b"\x00" * 0x400)
        f.write(b"\x00" * 0x10)
        f.write(syms + strtab + shstr)


def write_map(path):
    text = """Memory Configuration

Name             Origin             Length             Attributes
FLASH            0x0000000008000000 0x0000000000100000 xr
RAM              0x0000000020000000 0x0000000000040000 rw
*default*        0x0000000000000000 0xffffffffffffffff

Linker script and memory map

.isr_vector      0x0000000008000000     0x400
 .isr_vector     0x0000000008000000       0x400 Startup/startup.o
                 0x0000000008000000                g_pfnVectors

.text            0x0000000008000400     0x2c8
 .text           0x0000000008000400       0x2c8 Src/main.o
                 0x0000000008000400                Reset_Handler
                 0x0000000008000401                main

.ARM.exidx       0x00000000080006c8     0x8
 .ARM.exidx      0x00000000080006c8        0x8 Src/main.o

.data            0x0000000020000000     0x18 load address 0x00000000080006d0
 .data           0x0000000020000000       0x18 Src/main.o

.bss             0x0000000020000018     0x200
 .bss            0x0000000020000018       0x200 Src/main.o

.heap            0x0000000020000218     0x1000
                0x0000000020000218                __end__ = .

.stack           0x0000000020001218     0x400
                0x0000000020001218                __StackTop = .
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main(argv):
    preset = None
    mode = "configure"
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--preset":
            preset = argv[index + 1]
            index += 2
            continue
        if arg == "--build":
            mode = "build"
        index += 1
    if preset is None:
        print("fake cmake: missing preset", file=sys.stderr)
        sys.exit(2)
    build_dir = os.path.join("build", preset)
    os.makedirs(build_dir, exist_ok=True)
    with open(os.path.join(build_dir, "fake-argv.txt"), "a", encoding="utf-8") as f:
        f.write(json.dumps(argv) + "\n")
    if mode == "configure":
        if os.environ.get("FAKE_CMAKE_CONFIGURE_FAIL") == "1":
            print("fake configure failed", file=sys.stderr)
            sys.exit(5)
        print("fake configure: " + preset)
        sys.exit(0)
    if os.environ.get("FAKE_CMAKE_SLEEP") == "1":
        import time
        time.sleep(60)
    if os.environ.get("FAKE_CMAKE_BUILD_FAIL") == "1":
        print("fake build failed", file=sys.stderr)
        sys.exit(3)
    with open(".stm32-project.json", encoding="utf-8") as f:
        model = json.load(f)
    elf_path = os.path.join("build", preset, os.path.basename(model["build"]["elf"]))
    map_path = elf_path[:-4] + ".map"
    if os.environ.get("FAKE_CMAKE_NO_ARTIFACTS") != "1":
        write_elf(elf_path)
        write_map(map_path)
    print("fake build: " + preset)
    sys.exit(0)


if __name__ == "__main__":
    main(sys.argv[1:])
'''


@pytest.fixture
def fake_toolchain(tmp_path: Path, monkeypatch) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    cmake = bin_dir / "cmake"
    cmake.write_text(FAKE_CMAKE, encoding="utf-8")
    cmake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return bin_dir


@pytest.fixture
def build_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    shutil.copytree(FIXTURE, root)
    _git("init", root, "-b", "main")
    _git("add", root, ".")
    _git(
        "commit",
        root,
        "-m",
        "initial",
        "-c",
        "user.name=test",
        "-c",
        "user.email=test@example.com",
    )
    return root


def _git(command: str, cwd: Path, *args: str) -> None:
    from stm32_toolkit.process import ProcessRequest, run_process

    result = run_process(
        ProcessRequest(argv=("git", command, *args), cwd=cwd, timeout_seconds=15.0)
    )
    assert result.returncode == 0


def _request(root: Path, **kwargs) -> BuildRequest:
    values = dict(project_root=root, preset="arm-debug", timeout_seconds=30.0)
    values.update(kwargs)
    return BuildRequest(**values)


def _result_files(root: Path, preset: str = "arm-debug") -> dict[str, Path]:
    base = root / ".stm32-toolkit" / "build" / preset
    return {
        "log": base / "build.log",
        "identity": base / "firmware-identity.json",
        "result": base / "build-result.json",
        "lock": root / ".stm32-toolkit" / "build.lock",
    }


def test_build_success_publishes_evidence_chain(build_project: Path, fake_toolchain: Path):
    result = run_build(_request(build_project))

    assert result.ok is True
    assert result.operation == "project.build"
    report = result.data
    assert report.success is True
    assert report.returncode == 0
    assert report.preset == "arm-debug"
    assert report.clean_first is False
    assert report.timed_out is False
    assert report.error_code is None
    assert report.elf_path == "build/arm-debug/firmware.elf"
    assert report.map_path == "build/arm-debug/firmware.map"
    assert report.log_path == ".stm32-toolkit/build/arm-debug/build.log"
    assert report.identity_path == ".stm32-toolkit/build/arm-debug/firmware-identity.json"
    assert report.result_path == ".stm32-toolkit/build/arm-debug/build-result.json"
    assert report.identity is not None
    assert report.identity.schema_version == 1
    assert report.memory_usage == (
        MemoryUsage("FLASH", 0x08000000, 0x100000, 0x6D0, 0.17),
        MemoryUsage("RAM", 0x20000000, 0x40000, 0x1618, 2.16),
    )

    files = _result_files(build_project)
    assert files["log"].is_file()
    assert files["identity"].is_file()
    assert files["result"].is_file()
    assert files["lock"].is_file()

    log_text = files["log"].read_text(encoding="utf-8")
    assert "fake configure: arm-debug" in log_text
    assert "fake build: arm-debug" in log_text

    identity = json.loads(files["identity"].read_text(encoding="utf-8"))
    validate_identity_document(identity)
    assert identity["status"] == "success"
    assert identity["preset"] == "arm-debug"
    assert identity["elf"]["path"] == "build/arm-debug/firmware.elf"
    assert identity["map"]["path"] == "build/arm-debug/firmware.map"
    assert identity["inputSnapshot"]["sha256"] == report.identity.input_snapshot.sha256
    assert len(identity["buildId"]) == 64

    result_record = json.loads(files["result"].read_text(encoding="utf-8"))
    assert result_record == report.to_dict()
    assert result_record["status"] == "success"
    assert result_record["buildId"] == identity["buildId"]


def test_build_identity_matches_git_and_snapshot_evidence(
    build_project: Path, fake_toolchain: Path
):
    from stm32_toolkit.build.identity import git_evidence, snapshot_inputs
    from stm32_toolkit.project_model import load_project_model

    result = run_build(_request(build_project))
    model = load_project_model(build_project)
    snapshot = snapshot_inputs(build_project, model)
    git = git_evidence(build_project)

    identity = result.data.identity
    assert identity.git_head == git.head
    assert identity.git_branch == git.branch
    assert identity.git_target == git.target
    assert identity.input_snapshot.sha256 == snapshot.sha256
    assert identity.input_snapshot.files == snapshot.files


def test_build_clean_first_passes_flag(build_project: Path, fake_toolchain: Path):
    result = run_build(_request(build_project, clean_first=True))

    assert result.ok is True
    argv_log = (
        build_project / "build" / "arm-debug" / "fake-argv.txt"
    ).read_text(encoding="utf-8")
    assert '"--build"' in argv_log
    assert '"--clean-first"' in argv_log


def test_build_configure_failure_does_not_publish(
    build_project: Path, fake_toolchain: Path, monkeypatch
):
    monkeypatch.setenv("FAKE_CMAKE_CONFIGURE_FAIL", "1")

    result = run_build(_request(build_project))

    assert result.ok is False
    assert result.code == "BUILD_FAILED"
    assert result.data is None
    assert result.details == {
        "stage": "configure",
        "preset": "arm-debug",
        "returncode": 5,
        "timedOut": False,
    }
    files = _result_files(build_project)
    assert not files["log"].exists()
    assert not files["identity"].exists()
    assert not files["result"].exists()


def test_build_stage_failure_does_not_publish(
    build_project: Path, fake_toolchain: Path, monkeypatch
):
    monkeypatch.setenv("FAKE_CMAKE_BUILD_FAIL", "1")

    result = run_build(_request(build_project))

    assert result.ok is False
    assert result.code == "BUILD_FAILED"
    assert result.details["stage"] == "build"
    assert result.details["returncode"] == 3
    assert not _result_files(build_project)["result"].exists()


def test_build_timeout_terminates_and_reports(build_project: Path, fake_toolchain: Path, monkeypatch):
    monkeypatch.setenv("FAKE_CMAKE_SLEEP", "1")

    result = run_build(_request(build_project, timeout_seconds=1.0))

    assert result.ok is False
    assert result.code == "BUILD_TIMEOUT"
    assert result.details["timedOut"] is True
    assert result.details["stage"] == "build"
    assert not _result_files(build_project)["result"].exists()


def test_build_busy_while_lock_held(build_project: Path, fake_toolchain: Path):
    import fcntl

    lock_path = build_project / ".stm32-toolkit" / "build.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        result = run_build(_request(build_project))

    assert result.ok is False
    assert result.code == "BUILD_BUSY"


def test_build_busy_when_lock_fd_fails(build_project: Path, fake_toolchain: Path, monkeypatch):
    monkeypatch.setattr(runner_mod, "_lock_fd", lambda _fileobj: False)

    result = run_build(_request(build_project))

    assert result.ok is False
    assert result.code == "BUILD_BUSY"


def test_build_environment_error_on_lock_failure(
    build_project: Path, fake_toolchain: Path, monkeypatch
):
    def failing(_fileobj):
        raise OSError("lock error")

    monkeypatch.setattr(runner_mod, "_lock_fd", failing)

    result = run_build(_request(build_project))

    assert result.ok is False
    assert result.code == "BUILD_ENVIRONMENT_ERROR"


def test_build_environment_error_when_cmake_missing(build_project: Path, monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent-path")

    result = run_build(_request(build_project))

    assert result.ok is False
    assert result.code == "BUILD_ENVIRONMENT_ERROR"
    assert result.details["stage"] == "configure"


def test_build_request_validation_errors(build_project: Path, fake_toolchain: Path):
    for kwargs, rule in (
        ({"preset": ""}, "preset"),
        ({"preset": 7}, "preset"),
        ({"timeout_seconds": 0.5}, "timeout"),
        ({"timeout_seconds": 4000.0}, "timeout"),
        ({"clean_first": "yes"}, "cleanFirst"),
    ):
        result = run_build(_request(build_project, **kwargs))
        assert result.ok is False
        assert result.code == "BUILD_REQUEST_INVALID"
        assert result.details == {"rule": rule}


def test_build_rejects_undeclared_preset(build_project: Path, fake_toolchain: Path):
    result = run_build(_request(build_project, preset="arm-extra"))

    assert result.ok is False
    assert result.code == "BUILD_MODEL_INVALID"
    assert result.details == {"preset": "arm-extra", "rule": "undeclaredPreset"}


def test_build_rejects_missing_model(build_project: Path, fake_toolchain: Path):
    (build_project / ".stm32-project.json").unlink()

    result = run_build(_request(build_project))

    assert result.ok is False
    assert result.code == "BUILD_MODEL_INVALID"


def test_build_evidence_invalid_when_artifacts_missing(
    build_project: Path, fake_toolchain: Path, monkeypatch
):
    monkeypatch.setenv("FAKE_CMAKE_NO_ARTIFACTS", "1")

    result = run_build(_request(build_project))

    assert result.ok is False
    assert result.code == "BUILD_EVIDENCE_INVALID"
    assert result.details["rule"] == "missingElf"


def test_build_evidence_invalid_when_map_malformed(
    build_project: Path, fake_toolchain: Path, monkeypatch
):
    monkeypatch.setattr(
        identity_mod,
        "read_text_bounded",
        lambda path, limit: "not a map at all\n",
    )

    result = run_build(_request(build_project))

    assert result.ok is False
    assert result.code == "BUILD_EVIDENCE_INVALID"
    assert result.details["rule"] == "memoryConfiguration"


def test_build_publication_failure_keeps_log_but_not_result(
    build_project: Path, fake_toolchain: Path, monkeypatch
):
    def failing_write(path: Path, data) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(identity_mod, "write_json_atomic", failing_write)

    result = run_build(_request(build_project))

    assert result.ok is False
    assert result.code == "BUILD_PUBLICATION_FAILED"
    files = _result_files(build_project)
    assert files["log"].is_file()
    assert not files["identity"].exists()
    assert not files["result"].exists()


def test_build_identity_schema_failure_publishes_nothing(
    build_project: Path, fake_toolchain: Path, monkeypatch
):
    def failing_validation(payload: dict) -> None:
        raise BuildError("BUILD_IDENTITY_INVALID", "identity invalid", {"rule": "const"})

    monkeypatch.setattr(identity_mod, "validate_identity_document", failing_validation)

    result = run_build(_request(build_project))

    assert result.ok is False
    assert result.code == "BUILD_IDENTITY_INVALID"
    files = _result_files(build_project)
    assert not files["log"].exists()
    assert not files["identity"].exists()
    assert not files["result"].exists()


def test_build_releases_lock_after_failure_and_success(
    build_project: Path, fake_toolchain: Path, monkeypatch
):
    import fcntl

    monkeypatch.setenv("FAKE_CMAKE_BUILD_FAIL", "1")
    assert run_build(_request(build_project)).ok is False

    monkeypatch.delenv("FAKE_CMAKE_BUILD_FAIL")
    assert run_build(_request(build_project)).ok is True

    lock_path = build_project / ".stm32-toolkit" / "build.lock"
    with lock_path.open("a+b") as probe:
        fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(probe.fileno(), fcntl.LOCK_UN)


def test_build_report_stdout_stderr_are_captured(
    build_project: Path, fake_toolchain: Path
):
    result = run_build(_request(build_project))

    assert "fake build: arm-debug" in result.data.stdout
    assert result.data.stderr == ""


def test_build_success_elf_sha_matches_artifact(
    build_project: Path, fake_toolchain: Path
):
    from stm32_toolkit.build.identity import sha256_file

    result = run_build(_request(build_project))
    elf_path = build_project / "build" / "arm-debug" / "firmware.elf"
    digest, size = sha256_file(elf_path, identity_mod._MAX_ARTIFACT_BYTES, "elfSize")

    assert result.data.identity.elf_sha256 == digest
    assert result.data.identity.elf_size == size
