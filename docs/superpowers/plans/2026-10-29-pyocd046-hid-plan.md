# PYOCD046-HID bounded implementation plan

Base `62bede1d55a513f3dfd8d634b2d3116b0de41890`; governing
[specification](../specs/2026-10-29-pyocd046-hid-design.md).
Worktree C:/Users/zhy76/.codex/worktrees/v135-pyocd046-hid/STM32-Toolkit,
branch codex/v135-pyocd046-hid. Primary spec/reviewer/acceptance owner; local
Claude Code CLI implementer via shared dispatch.py, unchanged configured model.
No remote action, hardware or active-runtime replacement authorized.

## File-only implementation

Exact allowed writes, no other source/config/report/fixture file:

- bin/setup-stm32-env.ps1
- tools/stm32-toolkit/pyproject.toml
- tools/release/release_0900_policy.json
- tools/stm32-toolkit/src/stm32_toolkit/probe/handoff.py
- skills/setup-stm32-env/SKILL.md
- skills/debug-firmware/SKILL.md
- CHANGELOG.md
- tools/stm32-toolkit/tests/test_setup_runtime.py
- tools/stm32-toolkit/tests/test_plugin_layout.py
- tools/stm32-toolkit/tests/test_debug_handoff.py
- tools/stm32-toolkit/tests/test_target_transports.py
- tools/stm32-toolkit/tests/test_pyocd_hid_timeout.py (new)

Read scope: those targets and their related Toolkit source/tests/fixtures,
release module, bin, two skills, AGENTS and this spec/plan. No installed sources,
external project, credentials or root-global discovery. Read/Grep/Glob are
available within those related modules; known files should use exact paths.
Instructions/source ledger are supplied, so no shell or Git discovery is needed.

Change the two policy value tokens without reformatting; use the coordinator's
expected policy SHA in setup. Preserve utility, runtime version, old API fixtures
and qualified-reference release text. Update current fake wheels/expectations
only where they represent this candidate; keep generic old-version doctor mocks
truthful. Add actual installed-SDK HID boundary tests with fake devices, avoiding
enumeration. Existing target API admission hash test continues to validate the
historical fixture; current-version/API assertion uses current candidate policy.
No shell, test execution, installation or hardware in edit mode. No automatic
retry/context-correction grant; genuine tool/scope/refusal/error stops and is
reported. File completion does not prove tests passed.

## Verification and independent acceptance

Freeze code, audit native editing events and all paths, commit CodeHead. Primary
prepares finite command groups and verified real interpreter/dependency paths.
Claude verify is separate, native PowerShell only, each command exact and once,
with actual inventory/smoke and fresh per-group JUnit. Run affected modules:
test_setup_runtime, test_plugin_layout, test_debug_handoff,
test_target_transports, new test_pyocd_hid_timeout, test_pyocd_backend and release
test_0900_artifacts. These are offline unit/API/fake-bundle tests, not real
packaging/deployment or firmware operations. Partition slow setup cases into
small groups; a worker pending result ends that worker, and Primary reconciles
the already-started run before scheduling genuinely unexecuted commands.

Primary reviews all base-to-CodeHead files in a clean exact-head tree and runs
independent selected risks: real-SDK HID finite argument/empty-response error,
current policy/pins/trust anchors, handoff/profile, actual bounded-fake target API
and setup old-version rejection/new acceptance. Review reused old fixture bytes
against base. New dependencies invalidate affected API evidence; do not reuse
old0.45.1 execution as proof of0.46.0. No broader full-repo/release matrix unless
an observed risk requires it.

Record verdict in docs/codex/returns/PYOCD046-HID/implementation-report.md,
CodeHead before report commit, exact commands/results/source state, preserved
errors and remaining5s/10s/physical limits. Primary updates standard checkpoint
and ordered goal. A correction returns to Claude within a separately bounded
task; abnormal invocation retry needs explicit authorization, and two
unconverged correction rounds return to design. No push/PR/tag/release.
