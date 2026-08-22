# STM32 Toolkit VS04-A Production Replacement Plan

## Ledger

- Product accepted base: `5d6e06845a2c1d991181c5ff84a9194dfcc49c8c`.
- Design-doc base after this plan commit: recorded by the primary in the implementation handoff.
- Rejected candidate: `c0a5d4e262c2ebc42ed8df2acc31f72f693af5d8`; clean, committed,
  unpushed, retained only as failed-attempt evidence.
- Implementer remains the same GPT-5.6-luna/max owner; reviewer remains GPT-5.6-sol.
- Replacement branch: `codex/STM32TK-0600-VS04A-PHYSICAL-TARGET-R2` from the new design-doc head,
  never from the rejected candidate.
- No remote or physical authority. CPython 3.12 only.

## Product result

Deliver the real default prepare -> fresh-process execute -> physical TestRun -> fresh `test.show`
path described by the VS-04 design and production-composition amendment. A default runtime that
intentionally fails until a test seam is injected is not an implementation.

## Allowed files

Toolkit application and domain:

- `src/stm32_toolkit/execution_provenance.py` (new);
- `src/stm32_toolkit/testing/target.py`;
- `src/stm32_toolkit/testing/publication.py`;
- `src/stm32_toolkit/testing_workflows.py`;
- `src/stm32_toolkit/testing/__init__.py` and top-level export only where required;
- `src/stm32_toolkit/cli.py`;
- `src/stm32_toolkit/mcp_server.py`.

Necessary production Probe bridge:

- `src/stm32_toolkit/probe/flash.py`;
- `src/stm32_toolkit/probe/client.py`;
- `src/stm32_toolkit/probe/service.py`;
- `src/stm32_toolkit/probe/pyocd_backend.py`;
- `src/stm32_toolkit/probe/backend.py` only for an exact protocol/type declaration.

Tests:

- create `tests/test_physical_target_workflows.py`;
- directly affected target runner/publication, Probe v2/client/backend/service, CLI/MCP, hardware
  workflow tests only.

Monitor and Diagnostic remain forbidden.

## Execution order

### 1. Red production-path test

Create one production-shaped fake-backend environment with real Project v3/build identity files,
WorkspacePaths, ProbeLeaseManager, supervisor, service, and client. Call the public prepare without
patching its derived binding or session. Assert it discovers inventory and returns a digest with no
MODIFY call or TestRun root. In a fresh context, call public execute and assert one lease/supervisor,
one flash, one transport, one publication, and fresh show.

This test must fail on the accepted base for missing public behavior and must also fail against the
rejected candidate because its default factories are absent.

### 2. Implement the narrow Probe facts and transport bridge

Add the read-only fresh-firmware projection by delegation, correct transport identity propagation,
decouple optional Monitor log transport, and establish the portable semihosting path boundary.
Add affected unit tests for each exact contract. Do not add another backend, lease manager, service,
or provider loader.

### 3. Implement derived prepare

Build every binding field from Project/build/OBSERVE discovery. Generalize Target discovery only
enough to derive its inventory before authorization. Validate requested cases and write the existing
single-use authorization record only after all read-only checks pass. Remove caller inventory from
CLI/MCP schemas.

### 4. Implement consumed execute and single ownership

Add persisted load/atomic consume semantics and immutable physical provenance. Recompute all current
facts before flash. Compose one MODIFY supervisor/client, one bound `flash_firmware` adapter, one
service-backed Target transport, and explicit cleanup ownership. Pass provenance explicitly into
runner publication; never infer it from implementation types.

### 5. Implement authoritative physical publication and thin adapters

Publish and reload the closed physical TestRun/root and extend `test.show`. Add the two CLI/MCP
operations with minimal input and one workflow call. Scan durable/public bytes for raw selector and
absolute-path leakage.

### 6. Focused verification

With exact replacement-worktree sources and one fresh basetemp, run:

```powershell
py -3.12 -m pytest -q tools/stm32-toolkit/tests/test_physical_target_workflows.py tools/stm32-toolkit/tests/test_target_runner.py tools/stm32-toolkit/tests/test_target_replay_publication.py tools/stm32-toolkit/tests/test_probe_protocol_v2.py tools/stm32-toolkit/tests/test_probe_client.py tools/stm32-toolkit/tests/test_probe_service.py tools/stm32-toolkit/tests/test_pyocd_backend.py tools/stm32-toolkit/tests/test_testing_cli.py tools/stm32-toolkit/tests/test_testing_mcp.py tools/stm32-toolkit/tests/test_hardware_workflows.py
py -3.12 -m py_compile <changed Python files>
git diff --check 5d6e06845a2c1d991181c5ff84a9194dfcc49c8c..HEAD
git status --short
```

If an exact test filename differs, use the existing file owning that symbol; do not create a Gate
wrapper. No Monitor suite, release matrix, physical probe, coverage, packaging, or Python 3.10.

The Sol reviewer must run the real public default path with only the backend seam replaced. A
candidate whose CLI/MCP defaults cannot reach a real supervisor/service/client is
`REWRITE_REQUIRED` again and returns to design, not local patching.

Expected commit: `feat(testing): compose physical target runs`.
