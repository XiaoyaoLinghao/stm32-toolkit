"""POST134-A: preset-scoped build evidence for debug/release switching.

``arm-debug`` keeps the historical ``artifacts/migration`` receipt pair that
context, flash, debug and Monitor read.  ``arm-release`` publishes to
``artifacts/migration/arm-release``.  These regressions prove that an ordinary
debug -> release -> debug -> release sequence without ``clean`` reuses each
preset's own incremental evidence, that one preset's failure or stale guidance
can never overwrite or describe the other's record, that a pre-patch legacy
*release* record is only consulted when the canonical release record is truly
absent (never from present invalid/failed evidence and never from a debug
record), and that managed debug consumers stay debug-only.

Most scenarios use the existing offline fake ``cmake``/``git`` doubles.  The
final journey builds one synthetic delivered project with the installed ARM GNU
toolchain through the real public build path; a missing tool is an explicit
failure, never a silent skip and never a fake substitute.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from stm32_toolkit.build import BuildRequest, run_build
from stm32_toolkit.build import runner as runner_mod
from stm32_toolkit.context import build_project_context
from stm32_toolkit.probe.flash import _FlashFailure, load_fresh_firmware_facts

from test_build_runner import (
    hit_records,
    install_fake_cmake,
    install_fake_git,
    prepare_project,
    read_json,
)

DEBUG_LOG = "artifacts/migration/build.log"
DEBUG_RESULT = "artifacts/migration/build-result.json"
RELEASE_DIR = "artifacts/migration/arm-release"
RELEASE_LOG = f"{RELEASE_DIR}/build.log"
RELEASE_RESULT = f"{RELEASE_DIR}/build-result.json"


def result_path(root: Path, rel: str) -> Path:
    return root.joinpath(*rel.split("/"))


def debug_identity_path(root: Path) -> Path:
    return root / "build" / "arm-debug" / "firmware-identity.json"


def release_identity_path(root: Path) -> Path:
    return root / "build" / "arm-release" / "firmware-identity.json"


def release_elf_path(root: Path) -> Path:
    return root / "build" / "arm-release" / "firmware.elf"


def artifact_paths(record: dict) -> set[str]:
    return {entry["path"] for entry in record["artifacts"]}


# ---------------------------------------------------------------------------
# schema 1 (Git provenance): debug -> release -> debug -> release, no clean
# ---------------------------------------------------------------------------


def test_schema1_debug_release_switching_reuses_both_incremental_evidences(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    hit_file = install_fake_cmake(monkeypatch, tmp_path)

    debug_first = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert debug_first.ok is True, debug_first
    debug_record_bytes = result_path(root, DEBUG_RESULT).read_bytes()
    debug_log_bytes = result_path(root, DEBUG_LOG).read_bytes()
    assert read_json(result_path(root, DEBUG_RESULT))["preset"] == "arm-debug"

    release_first = run_build(BuildRequest(project_root=root, preset="arm-release"))
    assert release_first.ok is True, release_first
    release_record = read_json(result_path(root, RELEASE_RESULT))
    assert release_record["preset"] == "arm-release"
    assert release_record["status"] == "success"
    assert artifact_paths(release_record) == {
        RELEASE_LOG,
        RELEASE_RESULT,
        "build/arm-release/firmware-identity.json",
        "build/arm-release/firmware.elf",
        "build/arm-release/firmware.map",
    }
    # a release success never rewrites the debug receipt pair
    assert result_path(root, DEBUG_RESULT).read_bytes() == debug_record_bytes
    assert result_path(root, DEBUG_LOG).read_bytes() == debug_log_bytes
    assert read_json(result_path(root, RELEASE_RESULT))["preset"] == "arm-release"

    # Re-entering each preset without --clean-first must reuse its own prior
    # success rather than falling back to a clean rebuild.
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")
    debug_second = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert debug_second.ok is True, debug_second
    assert debug_second.data.identity.build_id == debug_first.data.identity.build_id
    release_second = run_build(BuildRequest(project_root=root, preset="arm-release"))
    assert release_second.ok is True, release_second
    assert release_second.data.identity.build_id == release_first.data.identity.build_id

    # Each preset's receipt still names its own preset and its own artifacts.
    assert read_json(result_path(root, DEBUG_RESULT))["preset"] == "arm-debug"
    assert read_json(result_path(root, RELEASE_RESULT))["preset"] == "arm-release"
    assert artifact_paths(read_json(result_path(root, DEBUG_RESULT))) == {
        DEBUG_LOG,
        DEBUG_RESULT,
        "build/arm-debug/firmware-identity.json",
        "build/arm-debug/firmware.elf",
        "build/arm-debug/firmware.map",
    }
    assert "arm-release" not in json.dumps(
        read_json(result_path(root, DEBUG_RESULT))["artifacts"]
    )
    assert "arm-debug" not in json.dumps(
        read_json(result_path(root, RELEASE_RESULT))["artifacts"]
    )

    # No stage ever requested a clean build, and no module-global path was
    # switched by the preset choice.
    records = hit_records(hit_file)
    assert records, "the cmake double was never invoked"
    assert all("--clean-first" not in record["argv"] for record in records)
    assert runner_mod._LOG_REL == DEBUG_LOG
    assert runner_mod._RESULT_REL == DEBUG_RESULT
    release_paths = runner_mod._preset_evidence_paths("arm-release")
    assert (release_paths.log_rel, release_paths.result_rel) == (
        RELEASE_LOG,
        RELEASE_RESULT,
    )
    debug_paths = runner_mod._preset_evidence_paths("arm-debug")
    assert (debug_paths.log_rel, debug_paths.result_rel) == (DEBUG_LOG, DEBUG_RESULT)


# ---------------------------------------------------------------------------
# schema 2 (input snapshot): the same switching contract without Git
# ---------------------------------------------------------------------------


def test_schema2_debug_release_switching_reuses_snapshot_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path, git_repo=False)
    install_fake_git(monkeypatch, tmp_path, "exit1")
    hit_file = install_fake_cmake(monkeypatch, tmp_path)

    debug_first = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert debug_first.ok is True, debug_first
    release_first = run_build(BuildRequest(project_root=root, preset="arm-release"))
    assert release_first.ok is True, release_first

    debug_identity = read_json(debug_identity_path(root))
    release_identity = read_json(release_identity_path(root))
    for identity, preset in (
        (debug_identity, "arm-debug"),
        (release_identity, "arm-release"),
    ):
        assert identity["schemaVersion"] == 2
        assert identity["sourceBaseline"] == "input-snapshot-v1"
        assert identity["gitHead"] is None and identity["gitDirty"] is None
        assert identity["preset"] == preset
    debug_record = read_json(result_path(root, DEBUG_RESULT))
    release_record = read_json(result_path(root, RELEASE_RESULT))
    assert debug_record["schemaVersion"] == 2 and release_record["schemaVersion"] == 2
    assert debug_record["buildId"] == debug_identity["buildId"]
    assert release_record["buildId"] == release_identity["buildId"]
    assert artifact_paths(debug_record) == {
        DEBUG_LOG,
        DEBUG_RESULT,
        "build/arm-debug/firmware-identity.json",
        "build/arm-debug/firmware.elf",
        "build/arm-debug/firmware.map",
    }
    assert artifact_paths(release_record) == {
        RELEASE_LOG,
        RELEASE_RESULT,
        "build/arm-release/firmware-identity.json",
        "build/arm-release/firmware.elf",
        "build/arm-release/firmware.map",
    }
    debug_log_bytes = result_path(root, DEBUG_LOG).read_bytes()
    debug_record_bytes = result_path(root, DEBUG_RESULT).read_bytes()

    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")
    debug_second = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert debug_second.ok is True, debug_second
    assert debug_second.data.identity.build_id == debug_identity["buildId"]
    # A second debug build republishes its own receipt pair, so its log and
    # record bytes may legitimately differ from the first build's timings.
    # Capture them now to prove the *intervening* release build leaves the
    # debug pair untouched.
    debug_log_bytes = result_path(root, DEBUG_LOG).read_bytes()
    debug_record_bytes = result_path(root, DEBUG_RESULT).read_bytes()
    release_second = run_build(BuildRequest(project_root=root, preset="arm-release"))
    assert release_second.ok is True, release_second
    assert release_second.data.identity.build_id == release_identity["buildId"]

    # The strict schema-2 artifact-set validation accepted exactly each
    # preset's own paths; the intervening release build left the debug pair
    # byte-identical, and matching build IDs prove both presets reused their
    # own prior evidence instead of being forced into a clean rebuild.
    assert result_path(root, DEBUG_LOG).read_bytes() == debug_log_bytes
    assert result_path(root, DEBUG_RESULT).read_bytes() == debug_record_bytes
    assert read_json(result_path(root, RELEASE_RESULT))["schemaVersion"] == 2
    records = hit_records(hit_file)
    assert records, "the cmake double was never invoked"
    assert all("--clean-first" not in record["argv"] for record in records)


# ---------------------------------------------------------------------------
# failure isolation in both directions
# ---------------------------------------------------------------------------


def test_release_failure_cannot_overwrite_debug_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    debug = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert debug.ok is True, debug
    debug_record_bytes = result_path(root, DEBUG_RESULT).read_bytes()
    debug_log_bytes = result_path(root, DEBUG_LOG).read_bytes()
    debug_identity_bytes = debug_identity_path(root).read_bytes()

    monkeypatch.setenv("FAKE_CMAKE_EXIT", "3")
    failed = run_build(BuildRequest(project_root=root, preset="arm-release"))
    assert failed.ok is False
    assert failed.code == "BUILD_CONFIGURE_FAILED"
    # process diagnostics name the selected preset's log
    assert failed.details == {
        "stage": "configure",
        "exitCode": 3,
        "log": RELEASE_LOG,
    }
    failure = read_json(result_path(root, RELEASE_RESULT))
    assert failure["status"] == "failure"
    assert failure["preset"] == "arm-release"
    assert failure["code"] == "BUILD_CONFIGURE_FAILED"
    assert failure["artifacts"] == [{"path": RELEASE_LOG}]
    assert result_path(root, RELEASE_LOG).is_file()
    # no debug byte changed, and no release identity was published
    assert result_path(root, DEBUG_RESULT).read_bytes() == debug_record_bytes
    assert result_path(root, DEBUG_LOG).read_bytes() == debug_log_bytes
    assert debug_identity_path(root).read_bytes() == debug_identity_bytes
    assert not release_identity_path(root).exists()


def test_debug_failure_cannot_overwrite_release_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    release = run_build(BuildRequest(project_root=root, preset="arm-release"))
    assert release.ok is True, release
    release_record_bytes = result_path(root, RELEASE_RESULT).read_bytes()
    release_log_bytes = result_path(root, RELEASE_LOG).read_bytes()
    release_identity_bytes = release_identity_path(root).read_bytes()

    monkeypatch.setenv("FAKE_CMAKE_EXIT", "5")
    failed = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert failed.ok is False
    assert failed.code == "BUILD_CONFIGURE_FAILED"
    assert failed.details["log"] == DEBUG_LOG
    failure = read_json(result_path(root, DEBUG_RESULT))
    assert failure["status"] == "failure" and failure["preset"] == "arm-debug"
    assert result_path(root, RELEASE_RESULT).read_bytes() == release_record_bytes
    assert result_path(root, RELEASE_LOG).read_bytes() == release_log_bytes
    assert release_identity_path(root).read_bytes() == release_identity_bytes


# ---------------------------------------------------------------------------
# present canonical evidence never falls back to the legacy global record
# ---------------------------------------------------------------------------


def _publish_release_then_seed_legacy_global(root: Path) -> bytes:
    """Move the release receipt pair back to its pre-patch global location.

    This reproduces the pre-patch layout (one global receipt pair) in the
    temporary fixture only; the canonical release record is then truly absent
    and the global record is a genuine same-preset release record.
    """
    canonical = result_path(root, RELEASE_RESULT)
    legacy = result_path(root, DEBUG_RESULT)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(canonical.read_bytes())
    result_path(root, DEBUG_LOG).write_bytes(result_path(root, RELEASE_LOG).read_bytes())
    canonical.unlink()
    return legacy.read_bytes()


def test_present_invalid_canonical_release_record_never_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    assert run_build(BuildRequest(project_root=root, preset="arm-release")).ok is True
    _publish_release_then_seed_legacy_global(root)
    # The canonical record is present but malformed: no fallback is allowed.
    result_path(root, RELEASE_RESULT).write_text("{not-json\n", encoding="utf-8")
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    result = run_build(BuildRequest(project_root=root, preset="arm-release"))

    assert result.ok is False
    assert result.code == "BUILD_OUTPUT_STALE"
    details = result.details
    assert details["path"] == "build/arm-release/firmware.elf"
    assert details["rule"] == "unverifiable"
    assert details["reason"] == "prior-evidence-unavailable"
    assert details["preset"] == "arm-release"
    assert "evidenceField" not in details
    assert "evidenceSource" not in details
    # stale guidance names the selected preset's canonical paths
    assert details["logPath"] == RELEASE_LOG
    assert details["resultPath"] == RELEASE_RESULT
    assert details["identityPath"] == "build/arm-release/firmware-identity.json"
    assert details["remediation"]["action"] == "clean-rebuild"


def test_present_failed_canonical_release_record_never_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    assert run_build(BuildRequest(project_root=root, preset="arm-release")).ok is True
    legacy_bytes = _publish_release_then_seed_legacy_global(root)
    # The canonical record is present but records a failure: the legacy
    # global success record must not be consulted instead.
    canonical = json.loads(legacy_bytes.decode("utf-8"))
    canonical["status"] = "failure"
    canonical["stage"] = "configure"
    canonical["code"] = "BUILD_CONFIGURE_FAILED"
    result_path(root, RELEASE_RESULT).write_text(
        json.dumps(canonical, indent=2) + "\n", encoding="utf-8"
    )
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    result = run_build(BuildRequest(project_root=root, preset="arm-release"))

    assert result.ok is False
    assert result.code == "BUILD_OUTPUT_STALE"
    assert result.details["reason"] == "prior-build-not-successful"
    assert result.details["evidenceField"] == "status"
    assert result.details["evidenceSource"] == "record"
    assert result.details["resultPath"] == RELEASE_RESULT


def test_release_outputs_without_release_identity_never_use_the_debug_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    # Only a debug build exists, so the global record is a debug record.
    assert run_build(BuildRequest(project_root=root, preset="arm-debug")).ok is True
    assert read_json(result_path(root, DEBUG_RESULT))["preset"] == "arm-debug"
    # Seed compatible release outputs so the previous outputs are unchanged,
    # which is the condition that consults prior evidence at all.
    release_elf_path(root).parent.mkdir(parents=True, exist_ok=True)
    (root / "build" / "arm-release" / "firmware.elf").write_bytes(
        (root / "build" / "arm-debug" / "firmware.elf").read_bytes()
    )
    (root / "build" / "arm-release" / "firmware.map").write_bytes(
        (root / "build" / "arm-debug" / "firmware.map").read_bytes()
    )
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    result = run_build(BuildRequest(project_root=root, preset="arm-release"))

    assert result.ok is False
    assert result.code == "BUILD_OUTPUT_STALE"
    assert result.details["reason"] == "prior-evidence-unavailable"
    assert result.details["preset"] == "arm-release"


# ---------------------------------------------------------------------------
# legacy pre-patch release migration
# ---------------------------------------------------------------------------


def test_legacy_global_release_record_is_admitted_once_and_republished_canonically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    built = run_build(BuildRequest(project_root=root, preset="arm-release"))
    assert built.ok is True, built
    legacy_bytes = _publish_release_then_seed_legacy_global(root)
    assert not result_path(root, RELEASE_RESULT).exists()
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    reused = run_build(BuildRequest(project_root=root, preset="arm-release"))

    assert reused.ok is True, reused
    assert reused.data.identity.build_id == built.data.identity.build_id
    # The successful release build published only the new release paths and
    # left the legacy global record byte-identical.
    published = read_json(result_path(root, RELEASE_RESULT))
    assert published["status"] == "success"
    assert published["preset"] == "arm-release"
    assert artifact_paths(published) == {
        RELEASE_LOG,
        RELEASE_RESULT,
        "build/arm-release/firmware-identity.json",
        "build/arm-release/firmware.elf",
        "build/arm-release/firmware.map",
    }
    assert result_path(root, DEBUG_RESULT).read_bytes() == legacy_bytes


def test_legacy_schema2_release_record_is_validated_against_its_legacy_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path, git_repo=False)
    install_fake_git(monkeypatch, tmp_path, "exit1")
    install_fake_cmake(monkeypatch, tmp_path)
    built = run_build(BuildRequest(project_root=root, preset="arm-release"))
    assert built.ok is True, built
    assert read_json(result_path(root, RELEASE_RESULT))["schemaVersion"] == 2
    # A pre-patch schema-2 release record named the global log/result pair.
    legacy_record = read_json(result_path(root, RELEASE_RESULT))
    legacy_record["artifacts"] = [
        {"path": DEBUG_LOG}
        if entry["path"] == RELEASE_LOG
        else {"path": DEBUG_RESULT}
        if entry["path"] == RELEASE_RESULT
        else entry
        for entry in legacy_record["artifacts"]
    ]
    legacy = result_path(root, DEBUG_RESULT)
    legacy.write_bytes(json.dumps(legacy_record, indent=2).encode("utf-8") + b"\n")
    result_path(root, DEBUG_LOG).write_bytes(result_path(root, RELEASE_LOG).read_bytes())
    result_path(root, RELEASE_RESULT).unlink()
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    reused = run_build(BuildRequest(project_root=root, preset="arm-release"))

    assert reused.ok is True, reused
    assert reused.data.identity.build_id == built.data.identity.build_id
    published = read_json(result_path(root, RELEASE_RESULT))
    assert published["schemaVersion"] == 2
    assert artifact_paths(published) == {
        RELEASE_LOG,
        RELEASE_RESULT,
        "build/arm-release/firmware-identity.json",
        "build/arm-release/firmware.elf",
        "build/arm-release/firmware.map",
    }


def test_legacy_record_of_the_other_preset_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A legacy global *debug* record cannot become release evidence.

    The global record is a genuine debug success and the release identity is
    present; only the canonical release record is absent.  Reuse must still
    be refused, because the record is not a release record.
    """
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    assert run_build(BuildRequest(project_root=root, preset="arm-debug")).ok is True
    debug_identity = debug_identity_path(root).read_bytes()
    # Reuse the debug byte images as a same-preset release identity, then
    # rewrite the preset fields so only the preset discriminator differs.
    release_identity = json.loads(debug_identity.decode("utf-8"))
    release_identity["preset"] = "arm-release"
    release_identity["elfPath"] = "build/arm-release/firmware.elf"
    release_identity["mapPath"] = "build/arm-release/firmware.map"
    release_identity["buildId"] = runner_mod.compute_build_id(release_identity)
    release_identity_path(root).parent.mkdir(parents=True, exist_ok=True)
    release_identity_path(root).write_text(
        json.dumps(release_identity, indent=2) + "\n", encoding="utf-8"
    )
    (root / "build" / "arm-release" / "firmware.elf").write_bytes(
        (root / "build" / "arm-debug" / "firmware.elf").read_bytes()
    )
    (root / "build" / "arm-release" / "firmware.map").write_bytes(
        (root / "build" / "arm-debug" / "firmware.map").read_bytes()
    )
    legacy_record = dict(
        json.loads(result_path(root, DEBUG_RESULT).read_text(encoding="utf-8"))
    )
    assert legacy_record["preset"] == "arm-debug"
    legacy_record["buildId"] = release_identity["buildId"]
    result_path(root, DEBUG_RESULT).write_text(
        json.dumps(legacy_record, indent=2) + "\n", encoding="utf-8"
    )
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    result = run_build(BuildRequest(project_root=root, preset="arm-release"))

    assert result.ok is False
    assert result.code == "BUILD_OUTPUT_STALE"
    assert result.details["reason"] == "prior-evidence-unavailable"
    assert result.details["preset"] == "arm-release"


# ---------------------------------------------------------------------------
# redirected receipt paths are refused, never read as absence
# ---------------------------------------------------------------------------


def _mark_redirect(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    """Report ``path`` as a Windows reparse point through the runner's seam.

    Creating a native junction/symlink needs a privilege this suite cannot
    assume, so the redirect is injected at the runner's owned ``lstat`` seam
    (the same evidence a real junction produces).  The real filesystem stays
    ordinary, which is exactly what lets the test prove the product wrote
    nothing to the selected receipt path.
    """
    real_lstat = runner_mod._lstat
    marked = os.path.normcase(str(path.resolve(strict=False)))

    def fake_lstat(candidate):
        info = real_lstat(candidate)
        try:
            candidate_path = os.path.normcase(str(Path(candidate).resolve(strict=False)))
        except (OSError, RuntimeError, ValueError):
            candidate_path = os.path.normcase(str(candidate))
        if candidate_path == marked:
            return SimpleNamespace(
                st_mode=info.st_mode,
                st_file_attributes=getattr(
                    stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400
                ),
            )
        return info

    monkeypatch.setattr(runner_mod, "_lstat", fake_lstat)


def _prior_evidence(root: Path):
    """The release build's own prior-evidence admission decision."""
    return runner_mod._load_prior_evidence(
        root, "arm-release", runner_mod._preset_evidence_paths("arm-release")
    )


def test_redirected_canonical_release_record_refuses_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A present but redirected canonical receipt is refused state.

    The legacy global release record is tempting here: the canonical receipt
    holds exactly the same release bytes.  Following that redirect (or
    treating it as absence) would admit another path's record, so admission
    must refuse it entirely.
    """
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    assert run_build(BuildRequest(project_root=root, preset="arm-release")).ok is True
    legacy_bytes = _publish_release_then_seed_legacy_global(root)
    canonical = result_path(root, RELEASE_RESULT)
    canonical.write_bytes(legacy_bytes)
    identity_bytes = release_identity_path(root).read_bytes()
    # Control: the ordinary canonical receipt is admitted as this preset's
    # own prior evidence, so the refusal below is about the redirect only.
    admitted = _prior_evidence(root)
    assert admitted is not None
    assert admitted.paths.result_rel == RELEASE_RESULT

    _mark_redirect(monkeypatch, canonical)

    # No prior pair is admitted at all: matching build IDs, paths and hashes
    # are not enough while the receipt path is redirected.
    assert _prior_evidence(root) is None
    result = run_build(BuildRequest(project_root=root, preset="arm-release"))
    assert result.ok is False
    # Publication is refused as well, so the redirected receipt and its
    # legacy global twin keep their exact bytes: nothing was written through
    # the redirect and no failure record displaced present evidence.
    assert result.code == "BUILD_EVIDENCE_FAILED"
    assert result.details == {"path": RELEASE_RESULT, "phase": "result"}
    assert canonical.read_bytes() == legacy_bytes
    assert result_path(root, DEBUG_RESULT).read_bytes() == legacy_bytes
    assert release_identity_path(root).read_bytes() == identity_bytes


def test_redirected_canonical_release_record_refuses_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Nothing is ever written through a redirected selected receipt path."""
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path, env={"FAKE_CMAKE_EXIT": "3"})
    canonical = result_path(root, RELEASE_RESULT)
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text("{prior canonical bytes\n", encoding="utf-8")
    before = canonical.read_bytes()
    _mark_redirect(monkeypatch, canonical)

    result = run_build(BuildRequest(project_root=root, preset="arm-release"))

    assert result.ok is False
    assert result.code == "BUILD_EVIDENCE_FAILED"
    assert result.details == {"path": RELEASE_RESULT, "phase": "result"}
    # The redirected receipt and its sibling log were not rewritten.
    assert canonical.read_bytes() == before
    assert not result_path(root, DEBUG_RESULT).exists()
    assert not result_path(root, DEBUG_LOG).exists()


def test_redirected_release_parent_with_absent_canonical_never_borrows_legacy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A redirected canonical *parent* is never mistaken for true absence.

    This is the reported hazard: the canonical release receipt is missing
    inside a redirected ``arm-release`` directory, so a leaf-only check sees
    "absent" and borrows the legacy global record.  Under a real junction the
    publication would then also land outside the project.  Both must be
    refused: no legacy fallback, and no write through the redirected parent.
    """
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    assert run_build(BuildRequest(project_root=root, preset="arm-release")).ok is True
    legacy_bytes = _publish_release_then_seed_legacy_global(root)
    canonical_dir = result_path(root, RELEASE_DIR)
    assert not result_path(root, RELEASE_RESULT).exists()
    # Control: with the canonical receipt genuinely absent and the legacy
    # global record genuine, migration *is* admitted.  The refusal below is
    # therefore caused by the redirect alone.
    admitted = _prior_evidence(root)
    assert admitted is not None
    assert admitted.paths.log_rel == DEBUG_LOG
    assert admitted.paths.result_rel == DEBUG_RESULT

    def inventory() -> dict[str, bytes]:
        return {
            path.name: path.read_bytes()
            for path in canonical_dir.iterdir()
            if path.is_file()
        }

    legacy_log_bytes = result_path(root, DEBUG_LOG).read_bytes()
    before = inventory()
    assert before, "the canonical release directory must hold the prior log"
    _mark_redirect(monkeypatch, canonical_dir)
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    # The redirected parent is refused state, never true absence.
    assert _prior_evidence(root) is None
    result = run_build(BuildRequest(project_root=root, preset="arm-release"))

    assert result.ok is False
    assert result.code == "BUILD_EVIDENCE_FAILED"
    assert result.details == {"path": RELEASE_LOG, "phase": "log"}
    # Nothing was published through the redirected parent: the legacy global
    # pair and the canonical directory are byte-identical, so no success or
    # failure record was written.
    assert result_path(root, DEBUG_RESULT).read_bytes() == legacy_bytes
    assert result_path(root, DEBUG_LOG).read_bytes() == legacy_log_bytes
    assert inventory() == before


# ---------------------------------------------------------------------------
# debug-only consumers keep working after a release build
# ---------------------------------------------------------------------------


def test_debug_context_and_managed_admission_survive_a_release_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A release build never disturbs the debug context/consumer view.

    The offline fake ``cmake`` double writes a build-only ELF fixture with no
    ``PT_LOAD`` segment, so managed flash admission correctly refuses it with
    ``FLASH_IMAGE_INVALID``.  This test therefore asserts the debug consumer
    *context* and the bounded admission refusal; the genuine managed
    admission assertions run in
    :func:`test_real_gcc_debug_release_debug_keeps_both_presets_current`
    against a real compiler-produced ELF.
    """
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    debug = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert debug.ok is True, debug
    release = run_build(BuildRequest(project_root=root, preset="arm-release"))
    assert release.ok is True, release
    debug_build_id = debug.data.identity.build_id
    debug_elf_sha = debug.data.identity.elf_sha256

    context = build_project_context(root, tmp_path.parent / "data", "session-a")
    assert context.ok is True
    evidence = context.data["build"]
    assert evidence["elfFresh"] is True
    assert evidence["preset"] == "arm-debug"
    assert evidence["buildId"] == debug_build_id
    assert evidence["elfSha256"] == debug_elf_sha
    assert evidence["identityPath"] == "build/arm-debug/firmware-identity.json"
    assert evidence["buildResultPath"] == DEBUG_RESULT
    assert evidence["buildLogPath"] == DEBUG_LOG

    # Admission is not mocked: the fixture ELF genuinely carries no PT_LOAD
    # segment, so the real product segment validation refuses it.  That
    # refusal is the correct product behavior for this fixture, which is why
    # the genuine admitted-firmware facts are asserted against the real
    # compiler journey below.
    with pytest.raises(_FlashFailure) as caught:
        load_fresh_firmware_facts(root)
    assert caught.value.code == "FLASH_IMAGE_INVALID"
    assert caught.value.details == {
        "path": "build/arm-debug/firmware.elf",
        "rule": "segments",
    }


# ---------------------------------------------------------------------------
# real ARM GNU toolchain journey: debug -> release -> debug, no clean
# ---------------------------------------------------------------------------


def _deliver_real_gcc_project(root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Deliver one real no-Git GCC project with the existing helper flow."""

    from gcc_delivery_integration_helpers import (
        EXTRA_SRAM2,
        MAIN_RAM_LAYOUT,
        STARTUP_SOURCE,
        STARTUP_STRATEGY,
        TARGET_NAME,
        UVPROJX,
        WFI_RETURNS,
        apply_toolchain_path,
        build_no_git_project,
        copy_reviewed_comments,
        prepare_complete_project,
        preview_source_comments,
    )
    from stm32_toolkit.workflows import (
        configure_project_workflow,
        convert_keil_workflow,
        preflight_keil_workflow,
    )

    apply_toolchain_path(monkeypatch)
    source = build_no_git_project(root)
    prep = root / "prep"
    prep.mkdir(parents=True, exist_ok=True)
    preview_payload, _plan = preview_source_comments(source, prep / "preview")
    _copy_payload, copy_manifest = copy_reviewed_comments(
        source, preview_payload, prep / "copy"
    )
    prepared = prep / "prepared"
    prepare_complete_project(source, prep / "copy", copy_manifest, prepared)
    options = {
        "uvprojx": UVPROJX,
        "target_name": TARGET_NAME,
        "startup_strategy": STARTUP_STRATEGY,
        "startup_source": STARTUP_SOURCE,
        "memory_layout": dict(MAIN_RAM_LAYOUT),
        "extra_regions": [dict(EXTRA_SRAM2)],
        "wfi_returns": [dict(entry) for entry in WFI_RETURNS],
    }
    preflight = preflight_keil_workflow(prepared, **options)
    assert preflight.ok is True, preflight.to_dict()
    destination = root / "out" / "gcc-project"
    destination.parent.mkdir(parents=True, exist_ok=True)
    planned = convert_keil_workflow(prepared, destination=destination, **options)
    assert planned.ok is True, planned.to_dict()
    applied = convert_keil_workflow(
        prepared,
        destination=destination,
        plan_id=planned.to_dict()["data"]["planId"],
        authorized=True,
        **options,
    )
    assert applied.ok is True, applied.to_dict()
    configuring = configure_project_workflow(
        destination, debug_backend="pyocd", debug_target="stm32f429zgtx"
    )
    assert configuring.ok is True, configuring.to_dict()
    configured = configure_project_workflow(
        destination,
        plan_id=configuring.to_dict()["data"]["plan_id"],
        authorized=True,
        debug_backend="pyocd",
        debug_target="stm32f429zgtx",
    )
    assert configured.ok is True, configured.to_dict()
    return destination


def test_real_gcc_debug_release_debug_keeps_both_presets_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Real debug -> release -> debug without clean keeps both presets current.

    The delivered synthetic project names its output from the migrated Keil
    target (``app.elf``/``app.map``), not ``firmware.elf``.  Every artifact
    path asserted here therefore comes from the returned identity, so the
    journey proves the actual product naming rather than a fixture name.
    """
    destination = _deliver_real_gcc_project(tmp_path, monkeypatch)

    first = run_build(
        BuildRequest(project_root=destination, preset="arm-debug", timeout_seconds=600)
    )
    assert first.ok is True, first.to_dict()
    first_identity = read_json(debug_identity_path(destination))
    assert first_identity["preset"] == "arm-debug"
    debug_elf_path = first.data.identity.elf_path
    debug_map_path = first.data.identity.map_path
    assert debug_elf_path == first_identity["elfPath"]
    assert debug_map_path == first_identity["mapPath"]
    assert debug_elf_path.startswith("build/arm-debug/")
    assert result_path(destination, debug_elf_path).is_file()
    assert result_path(destination, debug_map_path).is_file()
    debug_elf_bytes = result_path(destination, debug_elf_path).read_bytes()
    debug_record = read_json(result_path(destination, DEBUG_RESULT))
    assert artifact_paths(debug_record) == {
        DEBUG_LOG,
        DEBUG_RESULT,
        "build/arm-debug/firmware-identity.json",
        debug_elf_path,
        debug_map_path,
    }

    release = run_build(
        BuildRequest(project_root=destination, preset="arm-release", timeout_seconds=600)
    )
    assert release.ok is True, release.to_dict()
    release_identity = read_json(release_identity_path(destination))
    release_elf_path = release.data.identity.elf_path
    release_map_path = release.data.identity.map_path
    assert release_identity["preset"] == "arm-release"
    assert release_elf_path == release_identity["elfPath"]
    assert release_map_path == release_identity["mapPath"]
    # Release reuses the debug basename under its own preset directory.
    assert release_elf_path == "build/arm-release/" + debug_elf_path.rsplit("/", 1)[-1]
    assert release_map_path == "build/arm-release/" + debug_map_path.rsplit("/", 1)[-1]
    release_record = read_json(result_path(destination, RELEASE_RESULT))
    assert release_record["status"] == "success"
    assert artifact_paths(release_record) == {
        RELEASE_LOG,
        RELEASE_RESULT,
        "build/arm-release/firmware-identity.json",
        release_elf_path,
        release_map_path,
    }
    assert artifact_paths(read_json(result_path(destination, DEBUG_RESULT))) == {
        DEBUG_LOG,
        DEBUG_RESULT,
        "build/arm-debug/firmware-identity.json",
        debug_elf_path,
        debug_map_path,
    }
    # the release build never reused or overwrote debug evidence
    assert result_path(destination, debug_elf_path).read_bytes() == debug_elf_bytes

    # Genuine managed admission immediately after the release build, before any
    # second debug build can repair the damage: the debug preset is still the
    # admitted one and its identity, digest, path and target are unchanged from
    # the first debug build.  Checking only after the second debug build would
    # hide damage the intervening release caused.
    after_release_facts = load_fresh_firmware_facts(destination)
    assert after_release_facts.build_id == first.data.identity.build_id
    assert after_release_facts.build_id == first_identity["buildId"]
    assert after_release_facts.elf_sha256 == first.data.identity.elf_sha256
    assert after_release_facts.elf_sha256 == first_identity["elfSha256"]
    assert after_release_facts.elf_path == debug_elf_path
    assert after_release_facts.elf_path == first_identity["elfPath"]
    assert after_release_facts.target_device == first.data.identity.target_device
    assert after_release_facts.target_device == first_identity["targetDevice"]

    after_release_context = build_project_context(
        destination, tmp_path.parent / "data", "session-a"
    )
    assert after_release_context.ok is True
    assert after_release_context.data["build"]["elfFresh"] is True
    assert (
        after_release_context.data["build"]["buildId"]
        == first.data.identity.build_id
    )
    assert after_release_context.data["build"]["elfSha256"] == (
        first.data.identity.elf_sha256
    )
    assert after_release_context.data["build"]["preset"] == "arm-debug"
    assert after_release_context.data["build"]["buildResultPath"] == DEBUG_RESULT
    assert (
        after_release_context.data["build"]["identityPath"]
        == "build/arm-debug/firmware-identity.json"
    )

    # Back to debug without a clean build: the real incremental rebuild either
    # reproduces identical outputs (reused prior evidence) or produces changed
    # outputs (accepted as new evidence).  Both are valid successes; the debug
    # completeness claims are checked below.
    second = run_build(
        BuildRequest(project_root=destination, preset="arm-debug", timeout_seconds=600)
    )
    assert second.ok is True, second.to_dict()
    assert second.data.identity.preset == "arm-debug"
    assert second.data.identity.elf_path == debug_elf_path
    assert read_json(result_path(destination, DEBUG_RESULT))["status"] == "success"
    assert read_json(result_path(destination, RELEASE_RESULT))["status"] == "success"
    # release evidence still names release paths after the second debug build
    assert artifact_paths(read_json(result_path(destination, RELEASE_RESULT))) == {
        RELEASE_LOG,
        RELEASE_RESULT,
        "build/arm-release/firmware-identity.json",
        release_elf_path,
        release_map_path,
    }

    context = build_project_context(
        destination, tmp_path.parent / "data", "session-a"
    )
    assert context.ok is True
    assert context.data["build"]["elfFresh"] is True
    assert context.data["build"]["buildId"] == second.data.identity.build_id
    assert context.data["build"]["buildResultPath"] == DEBUG_RESULT
    assert result_path(destination, release_elf_path).read_bytes()[:4] == b"\x7fELF"

    # Genuine managed admission of the real compiler output: the debug preset
    # is the admitted one after returning from the release build, and the
    # release build never replaced the debug consumer's evidence.
    facts = load_fresh_firmware_facts(destination)
    assert facts.build_id == second.data.identity.build_id
    assert facts.elf_path == debug_elf_path
    assert facts.elf_sha256 == second.data.identity.elf_sha256
    assert facts.target_device == second.data.identity.target_device

    # Both presets were configured with the verified installed ARM GNU
    # compiler, not a host default or a fake binary.
    for preset in ("arm-debug", "arm-release"):
        cache = (destination / "build" / preset / "CMakeCache.txt").read_text(
            encoding="utf-8", errors="replace"
        )
        normalized = os.path.normcase(cache.replace("/", os.sep))
        assert "arm-none-eabi-gcc" in normalized, preset
