# PYOCD046-HID bounded implementation plan

Base `62bede1d55a513f3dfd8d634b2d3116b0de41890`; governing
[specification](../specs/2026-10-29-pyocd046-hid-design.md).
Worktree C:/Users/zhy76/.codex/worktrees/v135-pyocd046-hid/STM32-Toolkit,
branch codex/v135-pyocd046-hid. Primary spec/reviewer/acceptance owner; local
Claude Code CLI implementer via shared dispatch.py, unchanged configured model.
No remote action, hardware or active-runtime replacement authorized.

## Authorized three-file continuation, 2026-10-29

After the retained unaccepted first invocation and Primary complete-diff review
at c7b91d2afad06be4838a365d7e5afa8469922643, the human explicitly authorized
one continuation and separate offline acceptance. Start from the clean branch
after report d1d2c844dad633f0e1d9155c058472a5b23b57d6 and this plan update.
Accepted diff origin remains62bede1d55a513f3dfd8d634b2d3116b0de41890.

The continuation may write ONLY test_pyocd_hid_timeout.py under the existing
Toolkit tests directory, skills/setup-stm32-env/SKILL.md and CHANGELOG.md.
Read/Grep/Glob scope is now this isolated repository, a new explicit permission
for this call only, not retroactive acceptance of the first call. Supply actual
SDK HID/Interface source excerpts in task text; do not read installed sources.
No shell/tests/installation/hardware/remote action during edit.

Add actual0.46.0 fake-device HID finite-timeout/normal-response/empty-response
tests; distinguish Unreleased/next1.3.5 source from published1.3.4 with0.45.1 in
the setup skill, preserving current metadata/path; remove only newly introduced
one-megahertz wording in the new changelog paragraph. Keep every other source,
test and old admission fixture byte unchanged relative to the retained candidate.

At most ONE native Edit original-text-not-found error may receive one same-file
Read followed by a short corrected Edit. Primary records actual consumption in
the external one-shot ledger; this allowance expires with the call. Any other
error, refusal, policy/permission boundary or scope deviation stops the call.
No full restart or other retry is authorized. Retain first-call logs and verdict.
After native edit audit and complete-diff review, freeze CodeHead, run the
already planned affected matrix through separate exact-command verify tasks
and independently accept/reject. Existing isolated dependencies are reused;
no active-runtime replacement, new hardware or remote authority.

## Initial file-only implementation (historical scope)

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
retry/context-correction grant in the initial call; only the explicit allowance
in the continuation section applies to the new call. Genuine tool/scope/refusal
errors otherwise stop and are reported. File completion does not prove tests
passed.

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
