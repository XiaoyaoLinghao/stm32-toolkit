"""Identity-bound CMake/CTest Host discovery and execution."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from multiprocessing.connection import Listener
import os
from pathlib import Path
import re
import sys
import threading
import unicodedata
from typing import cast
from uuid import uuid4
from xml.etree import ElementTree

from stm32_toolkit.evidence import ArtifactRef, EvidenceIdentity
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.process import ProcessError, ProcessRequest, ProcessResult, run_process
from stm32_toolkit.project_model import HostTestConfig

from .artifacts import TestArtifactCollector
from ._ctest_junit_bridge import BridgeFrameError, MAX_FRAME_BYTES, decode_frame
from .native_output import NativeExitMismatch, NativeOutputError, parse_ctest_431_text
from .model import (
    CASE_STATES,
    MAX_RUN_STREAM_BYTES,
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


_ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_UNTRUSTED_CREDENTIAL = re.compile(
    r"(?i)(?:authorization\s*[:=]\s*(?:bearer|basic)\s+\S+|"
    r"(?:password|passwd|secret|token|api[-_]?key)\s*[:=]\s*\S+)"
)
_UNTRUSTED_PATH = re.compile(
    r"(?i)(?:\bfile:[\\/]+|(?<![A-Za-z0-9_.-])[A-Za-z]:[\\/]|"
    r"(?<![A-Za-z0-9_.:/-])(?:\\\\|//)[^\\/\s]+[\\/]|"
    r"(?<![A-Za-z0-9_.*?-])/(?:home|Users|tmp|var|opt|etc)/)"
)


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
            raise protocol_error("TEST_ENVIRONMENT_INVALID", "config must be HostTestConfig")
        names = config.environment_allow
        values = config.environment_values
        if (
            not isinstance(names, tuple)
            or not isinstance(values, Mapping)
            or not all(isinstance(name, str) for name in names)
            or not all(isinstance(name, str) for name in values)
        ):
            raise protocol_error("TEST_ENVIRONMENT_INVALID", "test environment allowlist is invalid")
        allowed = set(names)
        folded = {name.casefold() for name in allowed}
        if (
            len(allowed) != len(names)
            or len(folded) != len(allowed)
            or not set(values) <= allowed
            or not all(
                isinstance(name, str)
                and _ENVIRONMENT_NAME.fullmatch(name) is not None
                and unicodedata.normalize("NFC", name) == name
                and len(name.encode("utf-8")) <= 128
                for name in allowed
            )
            or not all(
                isinstance(value, str)
                and "\x00" not in value
                and unicodedata.normalize("NFC", value) == value
                and len(value.encode("utf-8")) <= 4096
                for value in values.values()
            )
        ):
            raise protocol_error("TEST_ENVIRONMENT_INVALID", "test environment allowlist is invalid")
        environment = {
            name: os.environ[name]
            for name in names
            if name in os.environ
        }
        environment.update(dict(values))
        return environment

    def _execute(
        self, argv: tuple[str, ...], config: HostTestConfig,
        *, inherited_fds: tuple[int, ...] = (),
    ) -> ProcessResult:
        environment = self._environment(config)
        try:
            request = ProcessRequest(
                argv=argv,
                cwd=self.project_root,
                timeout_seconds=config.timeout_seconds,
                env=environment,
                inherited_fds=inherited_fds,
            )
        except (TypeError, ValueError) as exc:
            raise protocol_error("TEST_ENVIRONMENT_INVALID", "test environment is invalid") from exc
        try:
            return self._process_runner(request)
        except ProcessError as exc:
            raise protocol_error("TEST_PROCESS_ERROR", exc.message) from exc

    def _execute_junit_bridge(
        self, argv: tuple[str, ...], config: HostTestConfig, scratch: Path,
    ) -> tuple[ProcessResult, int, bytes, bytes, bytes]:
        """Run CTest without ever exposing the authoritative JUnit pathname."""
        nonce = uuid4().hex + uuid4().hex
        helper = Path(__file__).with_name("_ctest_junit_bridge.py")
        received: list[bytes] = []
        failures: list[BaseException] = []
        inherited_fds: tuple[int, ...] = ()
        listener = None
        write_fd = None
        if sys.platform == "win32":
            channel = rf"\\.\pipe\stm32tk-ctest-{uuid4().hex}"
            listener = Listener(channel, family="AF_PIPE", authkey=bytes.fromhex(nonce))

            def receive() -> None:
                try:
                    connection = listener.accept()
                    try:
                        received.append(connection.recv_bytes(MAX_FRAME_BYTES))
                    finally:
                        connection.close()
                except BaseException as exc:  # transported as one stable Host error below
                    failures.append(exc)
        else:
            read_fd, write_fd = os.pipe()
            os.set_inheritable(write_fd, True)
            channel = str(write_fd)
            inherited_fds = (write_fd,)

            def receive() -> None:
                data = bytearray()
                try:
                    while True:
                        chunk = os.read(read_fd, 65536)
                        if not chunk:
                            break
                        data.extend(chunk)
                        if len(data) > MAX_FRAME_BYTES:
                            raise BridgeFrameError("bridge frame exceeds bound")
                    received.append(bytes(data))
                except BaseException as exc:
                    failures.append(exc)
                finally:
                    os.close(read_fd)

        receiver = threading.Thread(target=receive, daemon=True)
        receiver.start()
        try:
            result = self._execute(
                (
                    sys.executable, str(helper),
                    "named-pipe" if sys.platform == "win32" else "fd",
                    channel, nonce, str(scratch), str(self.project_root), "--", *argv,
                ),
                config,
                inherited_fds=inherited_fds,
            )
        finally:
            if write_fd is not None:
                os.close(write_fd)
            if listener is not None and (result.timed_out if "result" in locals() else True):
                listener.close()
        receiver.join(timeout=5)
        if listener is not None:
            listener.close()
        if result.timed_out:
            raise protocol_error(
                "TEST_PROCESS_TIMEOUT", f"CTest execution timed out; bridge scratch preserved at {scratch}"
            )
        if result.returncode != 0 or result.stdout_truncated or result.stderr_truncated:
            raise protocol_error(
                "TEST_PROCESS_ERROR", f"CTest bridge failed; scratch preserved at {scratch}"
            )
        if receiver.is_alive() or failures or len(received) != 1:
            raise protocol_error(
                "TEST_PROCESS_ERROR", f"CTest bridge transport failed; scratch preserved at {scratch}"
            )
        try:
            ctest_returncode, stdout, stderr, junit = decode_frame(received[0], nonce)
        except BridgeFrameError as exc:
            raise protocol_error(
                "TEST_PROCESS_ERROR", f"CTest bridge frame invalid; scratch preserved at {scratch}"
            ) from exc
        return result, ctest_returncode, stdout, stderr, junit

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
        if discovery.inventory.identity != identity:
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
        bound_identity = replace(
            identity,
            build_id=calculate_host_build_inventory_digest(
                config.build_preset, config.ctest_preset, config.labels, executables
            ),
            elf_sha256=calculate_host_test_executable_inventory_digest(executables),
        )
        inventory = create_inventory("host", bound_identity, cases, self._clock())
        return _Discovery(inventory, artifact, ordinals, executables)

    @staticmethod
    def _parse_discovery(
        payload: object, labels: tuple[str, ...]
    ) -> tuple[tuple[str, ...], tuple[dict[str, object], ...], dict[str, int]]:
        if not isinstance(labels, tuple) or not all(isinstance(label, str) for label in labels):
            raise protocol_error("TEST_DISCOVERY_INVALID", "CTest label selection is invalid")
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
        if (
            not isinstance(case_ids, tuple)
            or not all(isinstance(case_id, str) and case_id for case_id in case_ids)
            or len(case_ids) != len(set(case_ids))
        ):
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
        scratch = self._collector.new_directory("ctest-bridge-private")
        started = self._clock()
        result, ctest_returncode, stdout_bytes, stderr_bytes, junit_bytes = self._execute_junit_bridge(
            (
                *self._ctest, "--preset", config.ctest_preset,
                "--tests-information", selection,
            ),
            config, scratch,
        )
        ended = self._clock()
        try:
            native_outcomes = parse_ctest_431_text(stdout_bytes, exit_code=ctest_returncode)
        except NativeExitMismatch as exc:
            raise protocol_error("TEST_EXIT_MISMATCH", str(exc)) from exc
        except NativeOutputError as exc:
            raise protocol_error("TEST_NATIVE_RESULT_INVALID", str(exc)) from exc
        if {node for node, _outcome in native_outcomes} != set(selected):
            raise protocol_error("TEST_NATIVE_RESULT_INVALID", "CTest text inventory contradicts selection")
        cases = self._parse_junit(
            junit_bytes, tuple(selected), directory, dict(native_outcomes)
        )
        # Raw runner output is published only after every untrusted JUnit byte
        # has passed bounded decoding, portable-text checks, strict parsing,
        # and the authoritative native-text/exit/inventory cross-check.
        raw_events = self._collector.write_and_ingest(
            directory, "ctest-junit.xml", junit_bytes,
            kind="test-events", media_type="application/xml",
        )
        stdout = self._collector.write_and_ingest(
            directory, "ctest-stdout.txt", stdout_bytes,
            kind="test-stdout", media_type="text/plain; charset=utf-8",
        )
        stderr = self._collector.write_and_ingest(
            directory, "ctest-stderr.txt", stderr_bytes,
            kind="test-stderr", media_type="text/plain; charset=utf-8",
        )
        state = self._run_state(cases)
        return TestRunManifest(
            TEST_SCHEMA, uuid4().hex, "host", state, inventory.identity, None, cases,
            started, ended, result.duration_ms, stdout, stderr, raw_events,
        )

    def _parse_junit(
        self, source: bytes | Path, selected: tuple[str, ...], directory: Path,
        authoritative: Mapping[str, str],
    ) -> tuple[TestCaseResult, ...]:
        if (
            not isinstance(authoritative, Mapping)
            or set(authoritative) != set(selected)
            or any(outcome not in {"passed", "failed", "skipped"} for outcome in authoritative.values())
        ):
            raise protocol_error(
                "TEST_NATIVE_RESULT_INVALID", "CTest native text inventory is invalid"
            )
        try:
            raw = source.read_bytes() if isinstance(source, Path) else source
            if not isinstance(raw, bytes) or len(raw) > MAX_RUN_STREAM_BYTES:
                raise ValueError("JUnit byte stream is invalid")
            document = raw.decode("utf-8")
            self._validate_untrusted_junit_document(document)
            root = ElementTree.fromstring(document)
        except (OSError, ElementTree.ParseError, UnicodeError) as exc:
            raise protocol_error("TEST_NATIVE_RESULT_INVALID", "CTest JUnit is invalid XML") from exc
        except (TypeError, ValueError) as exc:
            raise protocol_error("TEST_NATIVE_RESULT_INVALID", "CTest JUnit is invalid") from exc
        for element in root.iter():
            for value in element.attrib.values():
                self._validate_untrusted_junit_text(value)
            self._validate_untrusted_junit_text(element.text)
            self._validate_untrusted_junit_text(element.tail)
        if root.tag.rsplit("}", 1)[-1] not in {"testsuite", "testsuites"}:
            raise protocol_error("TEST_NATIVE_RESULT_INVALID", "CTest JUnit root is invalid")
        nodes = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "testcase"]
        results: dict[str, TestCaseResult] = {}
        for node in nodes:
            name = node.get("name")
            if not name or name in results or name not in selected:
                raise protocol_error("TEST_NATIVE_RESULT_INVALID", "CTest JUnit case inventory is invalid")
            child_nodes = list(node)
            children: dict[str, ElementTree.Element] = {}
            terminals: list[tuple[str, ElementTree.Element]] = []
            for child in child_nodes:
                tag = child.tag.rsplit("}", 1)[-1]
                if tag in {"failure", "error", "skipped"}:
                    terminals.append((tag, child))
                elif tag in {"system-out", "system-err"} and tag in children:
                    raise protocol_error(
                        "TEST_NATIVE_RESULT_INVALID", "CTest JUnit stream child is duplicated"
                    )
                children[tag] = child
            if len(terminals) > 1:
                raise protocol_error(
                    "TEST_NATIVE_RESULT_INVALID", "CTest JUnit case has multiple terminal children"
                )
            status = node.get("status")
            terminal_tag, terminal = terminals[0] if terminals else (None, None)
            if (
                (status == "fail" and terminal_tag == "skipped")
                or (status in {"skip", "notrun"} and terminal_tag in {"failure", "error"})
                or (status in {None, "run"} and terminal_tag in {"failure", "skipped"})
            ):
                raise protocol_error("TEST_NATIVE_RESULT_INVALID", "CTest JUnit terminal contradicts status")
            if terminal_tag == "error":
                state = "error"
            elif terminal_tag == "failure" or status == "fail":
                message_probe = " ".join(
                    value for value in (
                        None if terminal is None else terminal.get("message"),
                        None if terminal is None else terminal.text,
                    ) if value
                )
                state = "timeout" if "timeout" in message_probe.casefold() else "failed"
            elif terminal_tag == "skipped" or status in {"skip", "notrun"}:
                state = "skipped"
            elif status in {None, "run"}:
                state = "passed"
            else:
                raise protocol_error("TEST_NATIVE_RESULT_INVALID", "CTest JUnit status is invalid")
            message = None
            if terminal is not None:
                message = terminal.get("message") or (terminal.text.strip() if terminal.text else None)
            for value in (
                message,
                None if children.get("system-out") is None else children["system-out"].text,
                None if children.get("system-err") is None else children["system-err"].text,
            ):
                self._validate_untrusted_junit_text(value)
            # JUnit status/counts remain a structural cross-check only. CTest
            # verbose stdout and exit are the authoritative per-node facts.
            if authoritative.get(name) != state:
                raise protocol_error(
                    "TEST_NATIVE_RESULT_INVALID", "CTest JUnit contradicts native text"
                )
            self._junit_duration(node.get("time"))
            now = self._clock()
            results[name] = TestCaseResult(
                name, authoritative[name], now, now, 0, None, None, None
            )
        if set(results) != set(selected):
            raise protocol_error(
                "TEST_NATIVE_RESULT_INVALID", "CTest JUnit inventory contradicts native text"
            )
        self._validate_junit_summaries(root, nodes)
        return tuple(results[case_id] for case_id in selected)

    @staticmethod
    def _validate_untrusted_junit_text(value: str | None) -> None:
        if value is None:
            return
        if (
            not isinstance(value, str) or len(value.encode("utf-8")) > 1024 * 1024
            or unicodedata.normalize("NFC", value) != value
            or _UNTRUSTED_CREDENTIAL.search(value) is not None
            or _UNTRUSTED_PATH.search(value) is not None
        ):
            raise protocol_error(
                "TEST_NATIVE_RESULT_INVALID", "CTest JUnit contains unsafe untrusted text"
            )

    @staticmethod
    def _validate_untrusted_junit_document(value: str) -> None:
        if (
            unicodedata.normalize("NFC", value) != value
            or _UNTRUSTED_CREDENTIAL.search(value) is not None
            or _UNTRUSTED_PATH.search(value) is not None
        ):
            raise protocol_error(
                "TEST_NATIVE_RESULT_INVALID", "CTest JUnit contains unsafe untrusted text"
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
        def actual_counts(records: list[ElementTree.Element]) -> dict[str, int]:
            result = {"tests": len(records), "failures": 0, "errors": 0, "skipped": 0, "disabled": 0}
            for node in records:
                status = node.get("status")
                tags = [child.tag.rsplit("}", 1)[-1] for child in node]
                if "error" in tags:
                    result["errors"] += 1
                elif "failure" in tags or status == "fail":
                    result["failures"] += 1
                elif "skipped" in tags or status == "skip":
                    result["skipped"] += 1
                elif status == "notrun":
                    result["disabled"] += 1
            return result

        def declared_counts(container: ElementTree.Element) -> dict[str, int]:
            raw_counts = {
                field: container.get(field, None if field == "tests" else "0")
                for field in ("tests", "failures", "errors", "skipped", "disabled")
            }
            if any(raw is None or not raw.isdecimal() for raw in raw_counts.values()):
                raise protocol_error("TEST_NATIVE_RESULT_INVALID", "CTest JUnit counts are invalid")
            return {field: int(cast(str, raw)) for field, raw in raw_counts.items()}

        for suite in suites:
            suite_nodes = [node for node in suite.iter() if node.tag.rsplit("}", 1)[-1] == "testcase"]
            if declared_counts(suite) != actual_counts(suite_nodes):
                raise protocol_error("TEST_NATIVE_RESULT_INVALID", "CTest JUnit counts contradict cases")
        if root.tag.rsplit("}", 1)[-1] == "testsuites" and declared_counts(root) != actual_counts(nodes):
            raise protocol_error("TEST_NATIVE_RESULT_INVALID", "CTest JUnit root counts contradict suites")
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
