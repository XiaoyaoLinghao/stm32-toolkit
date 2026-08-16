"""Identity-bound CMake/CTest Host discovery and execution."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import threading
from typing import cast
from uuid import uuid4
from xml.etree import ElementTree

from stm32_toolkit.evidence import ArtifactRef, EvidenceIdentity
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.process import ProcessError, ProcessRequest, ProcessResult, run_process
from stm32_toolkit.project_model import HostTestConfig

from .artifacts import TestArtifactCollector
from .model import (
    CASE_STATES,
    TEST_SCHEMA,
    TestCaseResult,
    TestInventory,
    TestRunManifest,
    calculate_host_build_inventory_digest,
    calculate_host_test_executable_inventory_digest,
    create_inventory,
    protocol_error,
    validate_host_identity,
)


_ENVIRONMENT_LOCK = threading.RLock()


@dataclass(frozen=True)
class _Discovery:
    inventory: TestInventory
    artifact: ArtifactRef
    ordinals: Mapping[str, int]
    executables: tuple[dict[str, object], ...]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _prefix(value: str | Sequence[str], field: str) -> tuple[str, ...]:
    if isinstance(value, str):
        result = (value,)
    elif isinstance(value, Sequence):
        result = tuple(value)
    else:
        result = ()
    if not result or not all(isinstance(member, str) and member for member in result):
        raise ValueError(f"{field} must be a non-empty argv prefix")
    return result


class HostTestRunner:
    """Run exact Host test presets and retain native artifacts in EvidenceStore."""

    def __init__(
        self,
        *,
        project_root: Path,
        evidence_store: EvidenceStore,
        results_root: Path,
        cmake_executable: str | Sequence[str] = "cmake",
        ctest_executable: str | Sequence[str] = "ctest",
        process_runner: Callable[[ProcessRequest], ProcessResult] = run_process,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        if not isinstance(project_root, Path):
            raise TypeError("project_root must be a Path")
        self.project_root = project_root.resolve(strict=True)
        if not self.project_root.is_dir():
            raise ValueError("project_root must be a directory")
        self._collector = TestArtifactCollector(
            results_root, evidence_store, project_root=self.project_root
        )
        self._cmake = _prefix(cmake_executable, "cmake_executable")
        self._ctest = _prefix(ctest_executable, "ctest_executable")
        if not callable(process_runner) or not callable(clock):
            raise TypeError("process_runner and clock must be callable")
        self._process_runner = process_runner
        self._clock = clock
        self._discoveries: dict[str, tuple[HostTestConfig, _Discovery]] = {}
        self.discovery_artifact: ArtifactRef | None = None

    @staticmethod
    def _environment(config: HostTestConfig) -> dict[str, str]:
        if not isinstance(config, HostTestConfig):
            raise TypeError("config must be HostTestConfig")
        allowed = set(config.environment_allow)
        folded = {name.casefold() for name in allowed if isinstance(name, str)}
        if (
            len(allowed) != len(config.environment_allow)
            or len(folded) != len(allowed)
            or not set(config.environment_values) <= allowed
            or not all(isinstance(name, str) and name for name in allowed)
            or not all(isinstance(value, str) for value in config.environment_values.values())
        ):
            raise protocol_error("TEST_ENVIRONMENT_INVALID", "test environment allowlist is invalid")
        environment = {
            name: os.environ[name]
            for name in config.environment_allow
            if name in os.environ
        }
        environment.update(dict(config.environment_values))
        return environment

    def _execute(self, argv: tuple[str, ...], config: HostTestConfig) -> ProcessResult:
        request = ProcessRequest(
            argv=argv,
            cwd=self.project_root,
            timeout_seconds=config.timeout_seconds,
        )
        environment = self._environment(config)
        with _ENVIRONMENT_LOCK:
            original = dict(os.environ)
            os.environ.clear()
            os.environ.update(environment)
            try:
                return self._process_runner(request)
            except ProcessError as exc:
                raise protocol_error("TEST_PROCESS_ERROR", exc.message) from exc
            finally:
                os.environ.clear()
                os.environ.update(original)

    @staticmethod
    def _check_process(result: ProcessResult, *, operation: str) -> None:
        if result.timed_out:
            raise protocol_error("TEST_PROCESS_TIMEOUT", f"{operation} timed out")
        if result.stdout_truncated or result.stderr_truncated:
            raise protocol_error("TEST_PROCESS_OUTPUT_LIMIT", f"{operation} output exceeded its bound")
        if result.returncode != 0:
            raise protocol_error("TEST_PROCESS_FAILED", f"{operation} exited nonzero")

    def discover(self, config: HostTestConfig, identity: EvidenceIdentity) -> TestInventory:
        validate_host_identity(identity)
        build = self._execute(
            (*self._cmake, "--build", "--preset", config.build_preset), config
        )
        self._check_process(build, operation="CMake build")
        discovery = self._discover_only(config, identity)
        if (
            identity.build_id != calculate_host_build_inventory_digest(
                config.build_preset, config.ctest_preset, config.labels, discovery.executables
            )
            or identity.elf_sha256
            != calculate_host_test_executable_inventory_digest(discovery.executables)
        ):
            raise protocol_error(
                "TEST_IDENTITY_MISMATCH",
                "Host identity differs from the canonical build or executable inventory",
            )
        self._discoveries[discovery.inventory.inventory_digest] = (config, discovery)
        self.discovery_artifact = discovery.artifact
        return discovery.inventory

    def _discover_only(self, config: HostTestConfig, identity: EvidenceIdentity) -> _Discovery:
        result = self._execute(
            (*self._ctest, "--preset", config.ctest_preset, "--show-only=json-v1"),
            config,
        )
        self._check_process(result, operation="CTest discovery")
        raw = result.stdout.encode("utf-8")
        directory = self._collector.new_directory("ctest-discovery")
        artifact = self._collector.write_and_ingest(
            directory, "ctest-discovery.json", raw,
            kind="test-discovery", media_type="application/json",
        )
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise protocol_error("TEST_DISCOVERY_INVALID", "CTest discovery is invalid JSON") from exc
        cases, executables, ordinals = self._parse_discovery(payload, config.labels)
        inventory = create_inventory(
            "host", identity, cases, self._clock(), executable_inventory=executables
        )
        return _Discovery(inventory, artifact, ordinals, executables)

    @staticmethod
    def _parse_discovery(
        payload: object, labels: tuple[str, ...]
    ) -> tuple[tuple[str, ...], tuple[dict[str, object], ...], dict[str, int]]:
        if not isinstance(payload, dict):
            raise protocol_error("TEST_DISCOVERY_INVALID", "CTest discovery must be an object")
        version = payload.get("version")
        tests = payload.get("tests")
        if (
            payload.get("kind") != "ctestInfo"
            or version != {"major": 1, "minor": 0}
            or not isinstance(tests, list)
        ):
            raise protocol_error("TEST_DISCOVERY_INVALID", "CTest json-v1 header is invalid")
        selected: list[tuple[str, list[str], int]] = []
        for ordinal, item in enumerate(tests, start=1):
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                raise protocol_error("TEST_DISCOVERY_INVALID", "CTest test record is invalid")
            name = cast(str, item["name"])
            command = item.get("command")
            properties = item.get("properties", [])
            if (
                not name
                or not isinstance(command, list)
                or not command
                or not all(isinstance(member, str) and member for member in command)
                or not isinstance(properties, list)
            ):
                raise protocol_error("TEST_DISCOVERY_INVALID", "CTest test command is invalid")
            native_labels: set[str] = set()
            for member in properties:
                if not isinstance(member, dict) or set(member) != {"name", "value"}:
                    raise protocol_error("TEST_DISCOVERY_INVALID", "CTest test property is invalid")
                if member["name"] == "LABELS":
                    value = member["value"]
                    if isinstance(value, list) and all(isinstance(label, str) for label in value):
                        native_labels.update(value)
                    elif isinstance(value, str):
                        native_labels.add(value)
                    else:
                        raise protocol_error("TEST_DISCOVERY_INVALID", "CTest LABELS property is invalid")
            if labels and not set(labels) <= native_labels:
                continue
            selected.append((name, cast(list[str], command), ordinal))
        ids = [item[0] for item in selected]
        if len(ids) != len(set(ids)):
            raise protocol_error("TEST_DUPLICATE_CASE", "CTest discovery has duplicate case IDs")
        selected.sort(key=lambda item: item[0].encode("utf-8"))
        cases = tuple(item[0] for item in selected)
        executables = tuple({"case_id": name, "command": command} for name, command, _ in selected)
        ordinals = {name: ordinal for name, _command, ordinal in selected}
        return cases, executables, ordinals

    def run(self, inventory: TestInventory, case_ids: tuple[str, ...]) -> TestRunManifest:
        if not isinstance(inventory, TestInventory) or inventory.mode != "host":
            raise protocol_error("TEST_IDENTITY_MISMATCH", "Host run requires a Host inventory")
        validate_host_identity(inventory.identity)
        known = self._discoveries.get(inventory.inventory_digest)
        if known is None or known[1].inventory != inventory:
            raise protocol_error("TEST_INVENTORY_CHANGED", "inventory was not frozen by this runner")
        config, discovery = known
        if not isinstance(case_ids, tuple) or len(case_ids) != len(set(case_ids)):
            raise protocol_error("TEST_CASE_NOT_FOUND", "requested case IDs are invalid")
        requested = inventory.case_ids if not case_ids else case_ids
        if any(case_id not in inventory.case_ids for case_id in requested):
            raise protocol_error("TEST_CASE_NOT_FOUND", "requested test case was not discovered")
        selected = tuple(case_id for case_id in inventory.case_ids if case_id in requested)
        fresh = self._discover_only(config, inventory.identity)
        self.discovery_artifact = fresh.artifact
        if fresh.inventory.inventory_digest != inventory.inventory_digest:
            raise protocol_error("TEST_INVENTORY_CHANGED", "CTest inventory changed after discovery")
        numbers = sorted(fresh.ordinals[case_id] for case_id in selected)
        selection = "0,0,0," + ",".join(str(number) for number in numbers)
        directory = self._collector.new_directory("ctest-run")
        junit_path = self._collector.output_path(directory, "ctest-junit.xml")
        started = self._clock()
        result = self._execute(
            (
                *self._ctest, "--preset", config.ctest_preset,
                "--tests-information", selection,
                "--output-junit", str(junit_path),
            ),
            config,
        )
        if result.timed_out:
            raise protocol_error("TEST_PROCESS_TIMEOUT", "CTest execution timed out")
        if result.stdout_truncated or result.stderr_truncated:
            raise protocol_error("TEST_PROCESS_OUTPUT_LIMIT", "CTest execution output exceeded its bound")
        ended = self._clock()
        raw_events = self._collector.ingest_existing(
            junit_path, kind="test-events", media_type="application/xml", stream_limit=True
        )
        stdout = self._collector.write_and_ingest(
            directory, "ctest-stdout.txt", result.stdout.encode("utf-8"),
            kind="test-stdout", media_type="text/plain; charset=utf-8",
        )
        stderr = self._collector.write_and_ingest(
            directory, "ctest-stderr.txt", result.stderr.encode("utf-8"),
            kind="test-stderr", media_type="text/plain; charset=utf-8",
        )
        cases = self._parse_junit(junit_path, tuple(selected), directory)
        state = self._run_state(cases)
        native_failure = state != "passed"
        if (result.returncode == 0) == native_failure:
            raise protocol_error("TEST_EXIT_MISMATCH", "CTest exit code contradicts JUnit")
        return TestRunManifest(
            TEST_SCHEMA, uuid4().hex, "host", state, inventory.identity, None, cases,
            started, ended, result.duration_ms, stdout, stderr, raw_events,
        )

    def _parse_junit(
        self, path: Path, selected: tuple[str, ...], directory: Path
    ) -> tuple[TestCaseResult, ...]:
        try:
            root = ElementTree.fromstring(path.read_bytes())
        except (OSError, ElementTree.ParseError, UnicodeError) as exc:
            raise protocol_error("TEST_NATIVE_RESULT_INVALID", "CTest JUnit is invalid XML") from exc
        if root.tag.rsplit("}", 1)[-1] not in {"testsuite", "testsuites"}:
            raise protocol_error("TEST_NATIVE_RESULT_INVALID", "CTest JUnit root is invalid")
        nodes = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "testcase"]
        results: dict[str, TestCaseResult] = {}
        for index, node in enumerate(nodes):
            name = node.get("name")
            if not name or name in results or name not in selected:
                raise protocol_error("TEST_NATIVE_RESULT_INVALID", "CTest JUnit case inventory is invalid")
            children = {child.tag.rsplit("}", 1)[-1]: child for child in node}
            status = node.get("status")
            terminal = next(
                (children[tag] for tag in ("failure", "error", "skipped") if tag in children),
                None,
            )
            if "error" in children:
                state = "error"
            elif "failure" in children or status == "fail":
                message_probe = " ".join(
                    value for value in (
                        None if terminal is None else terminal.get("message"),
                        None if terminal is None else terminal.text,
                    ) if value
                )
                state = "timeout" if "timeout" in message_probe.casefold() else "failed"
            elif "skipped" in children or status in {"skip", "notrun"}:
                state = "skipped"
            elif status in {None, "run"}:
                state = "passed"
            else:
                raise protocol_error("TEST_NATIVE_RESULT_INVALID", "CTest JUnit status is invalid")
            message = None
            if terminal is not None:
                message = terminal.get("message") or (terminal.text.strip() if terminal.text else None)
            stdout = self._case_artifact(children.get("system-out"), directory, index, "stdout")
            stderr = self._case_artifact(children.get("system-err"), directory, index, "stderr")
            duration = self._junit_duration(node.get("time"))
            now = self._clock()
            results[name] = TestCaseResult(name, state, now, now, duration, message, stdout, stderr)
        for case_id in selected:
            if case_id not in results:
                now = self._clock()
                results[case_id] = TestCaseResult(
                    case_id, "error", now, now, 0, "case ended without a terminal result", None, None
                )
        self._validate_junit_summaries(root, nodes)
        return tuple(results[case_id] for case_id in selected)

    def _case_artifact(
        self, node: ElementTree.Element | None, directory: Path, index: int, stream: str
    ) -> ArtifactRef | None:
        if node is None or not node.text:
            return None
        return self._collector.write_and_ingest(
            directory, f"case-{index}-{stream}.txt", node.text.encode("utf-8"),
            kind=f"test-case-{stream}", media_type="text/plain; charset=utf-8",
        )

    @staticmethod
    def _junit_duration(value: str | None) -> int:
        if value is None:
            return 0
        try:
            duration = Decimal(value)
        except InvalidOperation as exc:
            raise protocol_error("TEST_NATIVE_RESULT_INVALID", "CTest JUnit duration is invalid") from exc
        milliseconds = duration * 1000
        if not duration.is_finite() or duration < 0 or milliseconds != milliseconds.to_integral_value():
            raise protocol_error("TEST_NATIVE_RESULT_INVALID", "CTest JUnit duration is invalid")
        result = int(milliseconds)
        if result > 2**63 - 1:
            raise protocol_error("TEST_NATIVE_RESULT_INVALID", "CTest JUnit duration is invalid")
        return result

    @staticmethod
    def _validate_junit_summaries(
        root: ElementTree.Element, nodes: list[ElementTree.Element]
    ) -> None:
        suites = [suite for suite in root.iter() if suite.tag.rsplit("}", 1)[-1] == "testsuite"]
        if not suites:
            raise protocol_error("TEST_NATIVE_RESULT_INVALID", "CTest JUnit summary is missing")
        for suite in suites:
            suite_nodes = [node for node in suite.iter() if node.tag.rsplit("}", 1)[-1] == "testcase"]
            raw_counts = {
                field: suite.get(field, None if field == "tests" else "0")
                for field in ("tests", "failures", "errors", "skipped", "disabled")
            }
            if any(raw is None or not raw.isdecimal() for raw in raw_counts.values()):
                raise protocol_error("TEST_NATIVE_RESULT_INVALID", "CTest JUnit counts are invalid")
            counts = {field: int(cast(str, raw)) for field, raw in raw_counts.items()}
            failed = sum(
                node.get("status") == "fail"
                or any(child.tag.rsplit("}", 1)[-1] in {"failure", "error"} for child in node)
                for node in suite_nodes
            )
            skipped = sum(
                node.get("status") in {"skip", "notrun"}
                or any(child.tag.rsplit("}", 1)[-1] == "skipped" for child in node)
                for node in suite_nodes
            )
            if (
                counts["tests"] != len(suite_nodes)
                or counts["failures"] + counts["errors"] != failed
                or counts["skipped"] + counts["disabled"] != skipped
            ):
                raise protocol_error("TEST_NATIVE_RESULT_INVALID", "CTest JUnit counts contradict cases")
        if not nodes:
            raise protocol_error("TEST_NO_CASES", "CTest JUnit inventory is empty")

    @staticmethod
    def _run_state(cases: tuple[TestCaseResult, ...]) -> str:
        states = {case.state for case in cases}
        if states & {"error", "timeout"}:
            return "error"
        if "failed" in states:
            return "failed"
        return "passed"
