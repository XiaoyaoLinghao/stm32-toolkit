# STM32TK-0402 PyOCD Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fail-closed PyOCD adapter and supervised in-process Probe Service lifecycle that attach to one explicitly selected probe and target without halting, expose bounded observation, and never terminate unrelated processes.

**Architecture:** `PyOCDBackend` owns exactly one PyOCD `Session` and hides PyOCD types behind the existing `ProbeBackend` protocol. It enumerates all probes, applies an exact case-sensitive unique-ID match itself, opens with fixed attach/no-unlock/no-config options, and maps dependency or hardware failures to stable `ProbeBackendError` values. `ProbeServiceSupervisor` constructs and tears down only its own backend and service objects; later CLI/MCP packets can reuse it without a second hardware path.

**Tech Stack:** Python 3.10+, PyOCD 0.45.x as the optional `probe` extra, aiohttp, pytest, FakeProbe-style deterministic doubles.

## Global Constraints

- Accepted base is `8e16c4bef4fe52b29e8edea501e6b4d5bed37ff4`, the merge commit for `STM32TK-0401-PROBE-CORE`.
- Develop only on `codex/STM32TK-0402-PYOCD-BACKEND`; do not edit or commit on `master`.
- The Probe Service remains the only owner of a PyOCD Session; no CLI, MCP, Monitor, test, or helper may open another hardware path.
- Probe selection is exact and case-sensitive. Empty IDs, partial IDs, wildcard-like IDs, no match, and duplicate exact IDs fail with structured codes.
- Every session uses `connect_mode=attach`, `dap_protocol=swd`, `auto_unlock=false`, `resume_on_disconnect=false`, `no_config=true`, `pack.debug_sequences.enable=false`, `primary_core=0`, an explicit target override, and an inert explicit user script. Observation must not intentionally halt, reset, unlock, or erase on connect.
- PyOCD 0.45.1 `Session.open()` necessarily enables the debug port and may initialize a target; this packet promises non-halting attach, not a physically side-effect-free debug connection. Runtime register reads require an already halted core and never halt implicitly.
- Passive enumeration does not query `associated_board_info`, because the CMSIS-DAP implementation may temporarily open hardware merely to populate that property. Displayed board name is therefore absent until a later attached evidence path owns the session.
- A failed Session/probe cleanup prevents replacement attach. A failed partial open directly closes a probe still reported open, and multi-core targets are rejected until a later packet defines explicit core selection.
- Do not signal or terminate any process. Do not invoke `Stop-Process`, `taskkill`, `pkill`, `kill`, or a PyOCD command-line subprocess.
- No Option Bytes, arbitrary writes, chip erase, flash, or public control operations are added in this packet. The adapter's flash method fails closed until `STM32TK-0403-FLASH-HANDOFF` supplies identity and authorization gates.
- Backend methods independently bound addresses, read lengths, register batches, identifiers, and text even when the authenticated protocol has already validated them.
- Raw PyOCD exceptions, filesystem paths, serials other than the explicitly listed probe ID, tokens, and user configuration never enter returned messages or details.
- Python branch coverage remains at least 90%; no new skip or xfail may hide an implementable software failure.
- A deterministic fake-driver gate proves software behavior. Real-probe evidence is claimed only if `pyocd list` reports an available probe during this packet.

## File Structure

- Create `tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py`: lazy PyOCD binding, exact selection, attach/read/control adapter, stable error mapping, and fail-closed flash.
- Create `tools/stm32-toolkit/src/stm32_toolkit/probe/supervisor.py`: one-owner backend/service construction, idempotent start/stop, startup cleanup, and async context management.
- Modify `tools/stm32-toolkit/src/stm32_toolkit/probe/__init__.py`: export the two new public runtime entry points without importing PyOCD eagerly.
- Modify `tools/stm32-toolkit/pyproject.toml`: add the narrowly pinned optional `probe` extra.
- Create `tools/stm32-toolkit/tests/fakes/fake_pyocd.py`: complete fake probe/session/target/driver structures matching the adapter boundary.
- Create `tools/stm32-toolkit/tests/test_pyocd_backend.py`: adapter selection, session, read, error, cleanup, and dependency tests.
- Create `tools/stm32-toolkit/tests/test_probe_supervisor.py`: lifecycle, cleanup, restart, and unrelated-process survival tests.
- Create `docs/codex/returns/STM32TK-0402-PYOCD-BACKEND/implementation-report.md`: accepted-base, code-head, inventory, environment, gates, and deferred real-hardware evidence.

---

### Task 1: Freeze the PyOCD Driver Boundary and Exact Enumeration

**Files:**
- Create: `tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py`
- Create: `tools/stm32-toolkit/tests/fakes/fake_pyocd.py`
- Create: `tools/stm32-toolkit/tests/test_pyocd_backend.py`

**Interfaces:**
- Consumes: `ProbeBackendError` and `ProbeDescriptor` from `stm32_toolkit.probe.backend`.
- Produces: `PyOCDBackend(driver: PyOCDDriver | None = None, *, frequency_hz: int = 1_000_000)` and the internal `PyOCDDriver.list_probes()/create_session()` boundary.

- [x] **Step 1: Write the exact-enumeration RED tests**

  Add literal expectations proving deterministic descriptor ordering, case-sensitive equality, duplicate-exact rejection, partial/wildcard rejection, and stable dependency/enumeration failures. The key behavioral tests use this shape:

  ```python
  def test_partial_or_case_changed_probe_id_never_selects_a_probe():
      backend = backend_with_probes("ABC123", "ABC999")
      for probe_id in ("ABC", "abc123", "*"):
          with pytest.raises(ProbeBackendError) as error:
              backend.open_attach(probe_id, "stm32f407vg")
          assert error.value.code in {"PROBE_NOT_FOUND", "PROBE_SELECTION_REQUIRED"}
      assert backend.driver.created_sessions == []


  def test_duplicate_exact_ids_are_ambiguous_and_open_nothing():
      backend = backend_with_probes("ABC123", "ABC123")
      with pytest.raises(ProbeBackendError) as error:
          backend.open_attach("ABC123", "stm32f407vg")
      assert error.value.code == "PROBE_SELECTION_AMBIGUOUS"
      assert backend.driver.created_sessions == []
  ```

- [x] **Step 2: Run the new file and verify RED**

  Run: `C:\tmp\stm32tk-0402-venv\Scripts\python.exe -m pytest tools/stm32-toolkit/tests/test_pyocd_backend.py -q`

  Expected: collection fails because `stm32_toolkit.probe.pyocd_backend` and `fakes.fake_pyocd` do not exist.

- [x] **Step 3: Implement the minimal lazy driver and enumeration path**

  Define this narrow boundary and load PyOCD only when the default driver is first needed:

  ```python
  class PyOCDDriver(Protocol):
      def list_probes(self) -> tuple[object, ...]: ...
      def create_session(
          self, probe: object, *, options: Mapping[str, object]
      ) -> object: ...


  class PyOCDBackend:
      def __init__(
          self,
          driver: PyOCDDriver | None = None,
          *,
          frequency_hz: int = 1_000_000,
      ) -> None: ...
  ```

  The default driver imports `DebugProbeAggregator` and `Session` inside its constructor. Import failure maps to `PROBE_BACKEND_UNAVAILABLE`. `list_probes()` enumerates without a filter, validates each full `unique_id`, bounds display strings, and sorts by `probe_id` without exposing Python exception text.

- [x] **Step 4: Run enumeration tests GREEN and commit**

  Run: `C:\tmp\stm32tk-0402-venv\Scripts\python.exe -m pytest tools/stm32-toolkit/tests/test_pyocd_backend.py -q`

  Expected: enumeration and selection tests pass.

  Commit:

  ```powershell
  git add tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py tools/stm32-toolkit/tests/fakes/fake_pyocd.py tools/stm32-toolkit/tests/test_pyocd_backend.py
  git commit -m "test(STM32TK-0402): define exact PyOCD selection"
  ```

### Task 2: Open a Safe Attach Session and Map Observation Failures

**Files:**
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py`
- Modify: `tools/stm32-toolkit/tests/fakes/fake_pyocd.py`
- Modify: `tools/stm32-toolkit/tests/test_pyocd_backend.py`

**Interfaces:**
- Consumes: the exact selected probe object from Task 1.
- Produces: the complete existing `ProbeBackend` method surface; observation works, control methods remain internal to the backend contract, and `flash_file()` returns `PROBE_MODIFY_UNAVAILABLE`.

- [x] **Step 1: Add safe-session and observation RED tests**

  Add tests proving the session receives this literal option mapping and that the adapter does not halt on connect:

  ```python
  assert driver.created_sessions[0].options == {
      "auto_unlock": False,
      "connect_mode": "attach",
      "dap_protocol": "swd",
      "frequency": 1_000_000,
      "no_config": True,
      "pack.debug_sequences.enable": False,
      "primary_core": 0,
      "project_dir": os.getcwd(),
      "resume_on_disconnect": False,
      "target_override": "stm32f407vg",
      "user_script": os.devnull,
  }
  assert target.calls == []
  ```

  Add independently derived boundary cases for `address=0`, the final 32-bit address, zero/65,537-byte reads, address overflow, 257 registers, malformed names, exact-length memory, partial data, one failed register, disconnect, session-open failure, and repeated `close()`.

- [x] **Step 2: Run the focused file and verify RED**

  Run: `C:\tmp\stm32tk-0402-venv\Scripts\python.exe -m pytest tools/stm32-toolkit/tests/test_pyocd_backend.py -q`

  Expected: tests fail because attach/read/control/cleanup behavior is absent.

- [x] **Step 3: Implement minimal attach, read, control, and cleanup behavior**

  `open_attach()` must reject `halt_on_connect=True`, validate target syntax and length, close a previous session before opening a replacement, and call `session.open()` only after exact selection. After open, require a non-null board target. If construction/open/target discovery fails, close the created session once and leave the backend detached.

  `read_memory()` calls `target.read_memory_block8(address, length)` and requires the returned iterable to contain exactly `length` integer bytes in `0..255`; mismatch maps to `PROBE_PARTIAL_READ` with only `address`, `expectedLength`, and `actualLength`. `read_core_registers()` reads each requested name separately with `read_core_registers_raw([name])`, so one failure reports `PROBE_REGISTER_UNAVAILABLE` with only that name and does not detach the session.

  `halt()`, `resume()`, `step()`, and `reset()` call the matching target methods for use by the next packet but are not exposed through service routes here. `flash_file()` always raises `PROBE_MODIFY_UNAVAILABLE`. `close()` is idempotent and clears local state before calling the external close so a close exception cannot leave a falsely attached backend.

- [x] **Step 4: Run adapter and existing backend contract tests GREEN**

  Run: `C:\tmp\stm32tk-0402-venv\Scripts\python.exe -m pytest tools/stm32-toolkit/tests/test_pyocd_backend.py tools/stm32-toolkit/tests/test_probe_backend.py -q`

  Expected: all selected tests pass with no warnings.

- [x] **Step 5: Commit the adapter behavior**

  ```powershell
  git add tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py tools/stm32-toolkit/tests/fakes/fake_pyocd.py tools/stm32-toolkit/tests/test_pyocd_backend.py
  git commit -m "feat(STM32TK-0402): attach PyOCD exactly and safely"
  ```

### Task 3: Supervise One In-Process Service Without Process Termination

**Files:**
- Create: `tools/stm32-toolkit/src/stm32_toolkit/probe/supervisor.py`
- Create: `tools/stm32-toolkit/tests/test_probe_supervisor.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/__init__.py`

**Interfaces:**
- Consumes: `ProbeService`, `ProbeLeaseManager`, `OperationLevel`, and a zero-argument `backend_factory`.
- Produces: `ProbeServiceConfig` and `ProbeServiceSupervisor.start()/stop()/endpoint`, plus async context-manager support.

- [x] **Step 1: Write lifecycle RED tests**

  Cover concurrent/idempotent start, idempotent stop, restart with a new endpoint/lease, backend-factory failure, service-start failure cleanup, context-manager cleanup after cancellation, and stop after a backend close error. Start an unrelated sleeping Python subprocess as a sentinel, exercise supervisor start/stop, and assert the sentinel remains alive until the test itself terminates it.

  The public construction shape is:

  ```python
  config = ProbeServiceConfig(
      probe_id="probe-a",
      workspace_id="workspace-a",
      session_id="session-a",
      operation_level=OperationLevel.OBSERVE,
      session_root=data_root / "projects" / "workspace-a" / "sessions" / "session-a",
  )
  supervisor = ProbeServiceSupervisor(
      config=config,
      lease_manager=ProbeLeaseManager(data_root),
      backend_factory=lambda: fake_backend,
  )
  endpoint = await supervisor.start()
  ```

- [x] **Step 2: Run supervisor tests and verify RED**

  Run: `C:\tmp\stm32tk-0402-venv\Scripts\python.exe -m pytest tools/stm32-toolkit/tests/test_probe_supervisor.py -q`

  Expected: collection fails because `stm32_toolkit.probe.supervisor` does not exist.

- [x] **Step 3: Implement owned-object supervision**

  Use one `asyncio.Lock` to serialize lifecycle transitions. `start()` creates one backend and one `ProbeService`, publishes state only after `service.start()` succeeds, and closes the newly created backend if any startup step fails. `stop()` clears supervisor references before awaiting service shutdown, calls backend close only when no service ever owned it, and returns safely when already stopped. It never enumerates OS processes or invokes a subprocess.

- [x] **Step 4: Run lifecycle and service integration tests GREEN**

  Run: `C:\tmp\stm32tk-0402-venv\Scripts\python.exe -m pytest tools/stm32-toolkit/tests/test_probe_supervisor.py tools/stm32-toolkit/tests/test_probe_service.py tools/stm32-toolkit/tests/test_probe_client.py -q`

  Expected: all selected tests pass and the sentinel-process assertion proves unrelated ownership is preserved.

- [x] **Step 5: Commit supervision**

  ```powershell
  git add tools/stm32-toolkit/src/stm32_toolkit/probe/supervisor.py tools/stm32-toolkit/src/stm32_toolkit/probe/__init__.py tools/stm32-toolkit/tests/test_probe_supervisor.py
  git commit -m "feat(STM32TK-0402): supervise one probe service"
  ```

### Task 4: Package, Integrate, Verify, and Report Packet 0402

**Files:**
- Modify: `tools/stm32-toolkit/pyproject.toml`
- Modify: `docs/superpowers/plans/2026-08-07-stm32-toolkit-codex-continuation.md`
- Create: `docs/codex/returns/STM32TK-0402-PYOCD-BACKEND/implementation-report.md`

**Interfaces:**
- Consumes: the completed adapter and supervisor.
- Produces: installable `stm32-toolkit[probe]`, exact package evidence, a reviewed Codex branch, and a truthful implementation report.

- [x] **Step 1: Add package/import RED coverage**

  Add a test proving ordinary `import stm32_toolkit.probe` does not import `pyocd`, while constructing the default backend without the optional dependency returns `PROBE_BACKEND_UNAVAILABLE`. Add a subprocess smoke that imports and enumerates through installed PyOCD 0.45.1; zero connected probes is a valid structured empty result, not a real-hardware PASS.

- [x] **Step 2: Add the optional dependency and exports**

  Add exactly:

  ```toml
  probe = ["pyocd>=0.45.1,<0.46"]
  ```

  Preserve the existing `test` extra. Export `PyOCDBackend`, `ProbeServiceConfig`, and `ProbeServiceSupervisor` from `stm32_toolkit.probe` without importing PyOCD at package import time.

- [x] **Step 3: Run focused, full, static, and package gates**

  Run these commands from the worktree root:

  ```powershell
  uv pip install --python C:\tmp\stm32tk-0402-venv\Scripts\python.exe -e ".\tools\stm32-toolkit[test,probe]"
  C:\tmp\stm32tk-0402-venv\Scripts\python.exe -m pytest tools\stm32-toolkit\tests\test_pyocd_backend.py tools\stm32-toolkit\tests\test_probe_supervisor.py tools\stm32-toolkit\tests\test_probe_backend.py tools\stm32-toolkit\tests\test_probe_service.py tools\stm32-toolkit\tests\test_probe_client.py -q
  C:\tmp\stm32tk-0402-venv\Scripts\python.exe -m pytest tools\stm32-toolkit\tests -q --cov=stm32_toolkit --cov-branch --cov-report=term
  C:\tmp\stm32tk-0402-venv\Scripts\python.exe -m compileall -q tools\stm32-toolkit\src tools\stm32-toolkit\tests
  git diff --check 8e16c4bef4fe52b29e8edea501e6b4d5bed37ff4..HEAD
  pyocd --version
  pyocd list
  ```

  Build a wheel, install it into a new venv outside the repository, run `from stm32_toolkit.probe import PyOCDBackend, ProbeServiceSupervisor`, and call `PyOCDBackend().list_probes()`. Search the complete diff for token-like credentials, raw exception serialization, process termination APIs, shell strings, skip/xfail additions, and generated caches.

- [x] **Step 4: Run available platform and hardware evidence**

  On Windows, run the focused suite against real NTFS and record PyOCD 0.45.1 enumeration. If `pyocd list` shows a physical probe, attach non-halting to the explicitly selected ID/target, read one harmless bounded location, close, and record the exact target/probe environment outside source history. If no probe is listed, record `DEFERRED_TO_AVAILABLE_REAL_PROBE` and retain the release-level real gate for 0405/1.0.

- [x] **Step 5: Reconcile plan checkboxes and write the report**

  Mark the previously completed 0401 clean-worktree and merge steps in the continuation plan. Write the report with accepted base `8e16c4bef4fe52b29e8edea501e6b4d5bed37ff4`, the code head before the report commit, exact changed-path inventory, commands/versions/counts, Windows evidence, and named deferred Linux/real-probe gates. Do not write the report's own final SHA inside it.

- [ ] **Step 6: Commit report, push, review, and merge**

  Commit product/tests before the report-only commit. Push `codex/STM32TK-0402-PYOCD-BACKEND`, create one PR targeting `master`, review the exact accepted-base-to-remote-head diff in a clean worktree, rerun required gates there, and merge only after all non-deferred gates pass. Preserve the remote branch.
