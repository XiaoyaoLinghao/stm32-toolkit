# v1.3.2 version and qualification plan

This is phase 2 of the accepted v1.3.2 diagnostics plan, at accepted base
`cb2a1d2c78fcc4a5c886e77fb06d0ac01eddbab5`. Behavior scope remains the three
advisory improvements. Primary owns the plan/review/qualification and Claude CLI
owns product/test/documentation implementation. No extra plan-approval stop.

- Align active Toolkit, Monitor, plugin, UI package metadata/lock root, launchers,
  setup, release utility/policy and release schema to 1.3.2. Keep dependency versions
  (notably pyusb/lark 1.3.1) and historical fixture/evidence versions unchanged.
- Add 1.3.1 to existing legacy runtime and generation producer lists. Retain
  authorized Repair, quarantine, final-location verification, rollback,
  same-version source conflict and downgrade guards. Do not introduce migration.
- Update active examples and Skills to the matching runtime. Keep 1.3.1 identified
  as the observed current public Latest until 1.3.2 is actually published; describe
  1.3.2 as a local candidate with conditional version-matched downloads. Remove
  contradictory stale current-version prose without rewriting historical reports.
  Add a scoped changelog entry. Permanent qualification gates remain unchanged.
- Update current-version assertions and add 1.3.1 legacy cases. Preserve old fixture
  identities unless the assertion requires the current producer/runtime. Audit
  future-version refusal cases so 1.3.2 is not accidentally still the future case.
- Recompute setup's existing release utility/policy integrity pins from canonical
  committed bytes; no guard is weakened. File-only authorship stays separated from
  exact-command tests. Primary supplies computed pin values to Claude if needed.
- Execute affected complete test files, release utility/schema/inventory tests,
  setup's isolated offline temporary fixtures, Monitor package boundary/CLI checks,
  and full suites of any additional modified test files. Final real installation,
  IDE and hardware remain outside this patch's agent execution scope.
- Native branch evidence may reuse only unchanged source blobs from the retained
  v1.3.1 aggregate. Remove every changed file's old arcs before combining new native
  data. Report full denominators and gates without transferring prior exceptions;
  changed source with missing evidence is incomplete. UI implementation/dependencies
  remain unchanged; distinguish package metadata from UI execution evidence.
- Freeze source after review, perform two official independent builds, verify all
  13 assets and safely extracted bundle, then prepare exact candidate qualification
  disposition. Obtain any necessary candidate-specific exception only after the
  artifact/evidence is concrete. Existing user request authorizes v1.3.2 delivery;
  do not re-request push/Release authority already given for this version.

## Test-launcher correction identified before phase-2 execution

The existing setup test fixtures in test_setup_runtime.py and two cases in
 test_plugin_layout.py use powershell.exe with ExecutionPolicy Bypass. They have
not been executed in this v1.3.2 turn. Claude will change only these test launchers
to available native PowerShell7 without ExecutionPolicy flags, preserving every
assertion and real failure. This follows the user's existing PowerShell7 permission
and execution-policy requirement; it does not modify global policy or production
installation behavior. The verified executable is
C:/Users/zhy76/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe.

The same review found active README and setup Skill command examples still using
ExecutionPolicy Bypass. In the already allowed README.md, README_zh-CN.md and
skills/setup-stm32-env/SKILL.md, Claude must remove that override, show native
PowerShell7 (`pwsh`) explicitly, and explain checking the selected interpreter
before execution. A policy denial stops the step; changing policy or switching
shells after denial requires resolving that prerequisite, not an automatic retry.
This is caller-guidance consistency, not a production runtime change. Update the
corresponding test_plugin_layout.py assertions to protect the command boundary
while preserving explicit host-substituted path arguments and checksum checks.
