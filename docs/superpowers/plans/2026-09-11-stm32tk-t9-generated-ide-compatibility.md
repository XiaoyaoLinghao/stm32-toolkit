# T9 generated Cortex-Debug attach compatibility correction

Accepted base: `f27931ff85be33bb0466b69300777a9c07455ed4`, branch `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`. User requests “开始修正” after the remaining original generated-configuration defect was identified. This authorizes the bounded code correction and offline verification; no new deployment, IDE session, hardware access or remote action is part of this slice. Main owns design/integration; one Luna/max owner implements/tests; an independent reviewer checks the complete base-to-CodeHead diff. Main is clean, 100 commits ahead of the locally recorded upstream; no fetch/push is implied.

## Scenarios and boundaries

1. The generated handoff fragment can be wrapped in a workspace-level Cortex-Debug configuration without the `folder` callback object: its `cwd` is the canonical absolute project root from the validated begin request.
2. With Cortex-Debug 1.12.1 and PyOCD 0.45.1, the generated service arguments select the exact raw probe ID, including spaces, in attach mode, and the ready matcher accepts the actual GDB listening message while rejecting the separate STDIO message.
3. Repeated begin/recovery of an existing valid companion returns the same corrected configuration with no extra metadata or attach; tampered identities remain rejected and end/lease lifecycle stays intact.

Non-goals: static launch generation (already intentionally empty), automatic task generation, automatic discovery of IDE/GDB/PyOCD/pack installations, alternate backends, firmware changes, protocol/version changes, extra retries or increased timeouts. Environment wrapping still supplies `name`, `type`, verified `serverpath`, `gdbPath` and `cmsisPack`. Unchanged Target, handoff/end and corrected MCP physical evidence remains historical evidence at its recorded source; offline checks do not establish a new IDE physical PASS.

## Frozen field and lifecycle contract

- Production change is confined to `tools/stm32-toolkit/src/stm32_toolkit/probe/handoff.py`: `CortexDebugAttachContract` serialization and `_ticket`'s three return paths. Tests belong to existing `test_debug_handoff.py`, plus narrowly affected existing tests only when required.
- Add a required keyword-only `project_root: Path` to the internal attach data class. It receives the canonical existing root returned by `_validate_request`; require an absolute path without control characters, render `cwd` using forward slashes, and do not resolve or probe hardware in serialization. Invalid direct construction fails before a usable configuration can be emitted. All production/reentry `_ticket` calls supply that same validated root. Do not infer cwd from process cwd or a missing VS Code folder.
- Keep internal `board_id`, its selector/raw-ID relationship checks, the stored companion `boardId`, and persisted schema 1 field sets unchanged. Keep returned `serialNumber` and target/targetId fields. Remove only the launch fragment's `boardId`, because Cortex-Debug 1.12.1 maps it to unsupported `--board`.
- Emit `serverArgs=["--uid", board_id, "--connect", "attach"]` as an argv list. Raw ID comes exclusively from validated current metadata or the matching companion; never from a cached machine ID or selector substitution. No automatic first-probe selection, shell command, reset or reset-run.
- Emit `overrideGDBServerStartedRegex="GDB server (?:started (?:at|on)|listening on) port [0-9]+"`. Preserve the ready timeout and existing attach behavior.
- Keep executable's validated relative source and `${workspaceFolder}/...` representation. Preserve ticket identity, state transitions, companion validation/tamper handling, stop/reacquire behavior and error semantics. No new error-code family or evidence schema.
- `to_dict` now contains strings plus `serverArgs: list[str]`; update its return annotation accurately. Returned raw identity remains available through `serverArgs`; sensitive repr treatment remains as before.

Local interface evidence: installed extension `dist/extension.js` uses `t.cwd||e.uri.fsPath` and dereferences the folder again for a relative cwd. Its `dist/debugadapter.js` PyOCD controller emits `--board` from boardId, appends serverArgs, and defaults to `/GDB server started (at|on) port/`. Continuation 09's preserved configuration/logs prove the bounded compatible settings; the previous delivery report records the acceptance limitation.

## Necessary verification and review

Reuse existing handoff tests/fixtures for fresh begin, existing-companion reentry, tampered identity, end and lifecycle regressions. Add focused assertions for absolute cwd and invalid root, raw IDs containing spaces and selector hashing, exact argv/no `--board`, the ready positive/negative cases, and unchanged companion schema. Before running tests use CPython 3.12 and a new D-owned pytest basetemp, TEMP/TMP; no old C temporary paths. No generic diagnostic script/framework is needed.

Main additionally verifies actual installed Cortex-Debug argument/cwd code and current PyOCD parser offline, consuming the corrected generated fragment; never start the GDB service to check its parser. Test helpers must be a small bounded seam in existing tests or an inline invocation, not a second product adapter. Tests that only duplicate the dictionary are insufficient without lifecycle and real-consumer evidence.

Owner returns local CodeHead, clean state, exact changed files and executed checks. Independent reviewer inspects the full diff in a detached clean worktree and checks no persistence/lifecycle or authorization expansion. Record SOFTWARE_COMPLETE_HARDWARE_PENDING if software gates pass; plan a later single generated-config IDE check only under fresh authorization, not a repeat of flash/Target/MCP sampling.
