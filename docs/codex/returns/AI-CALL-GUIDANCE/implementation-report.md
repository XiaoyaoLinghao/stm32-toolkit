# AI-CALL-GUIDANCE implementation report

## Ledger

- Accepted base: `c6cf5cda7a25e4aa0b1335558ab0ffe16fbb32be`
- Planning commit: `776a7ae06699554007d152832a91e1fb71a388c5`
- Initial tested code: `d78cd4b18d8966b6e4a1a8094dde0590b6d33f75`
- Final CodeHead: `e02365f4ba7ec3c3bcaef3efae6d473215d6f7e6`
- Branch: `codex/ai-call-guidance`
- Governing spec: `docs/superpowers/specs/2026-10-24-ai-call-guidance-design.md`
- Plan: `docs/superpowers/plans/2026-10-24-ai-call-guidance-plan.md`
- Primary: specification, plan, review, acceptance. Implementation/tests: local Claude Code CLI
  with the existing configured provider/model `deepseek-v4.1-flash[1m]` retained.
- No ownership override, active PR, or remote authority. No push/tag/PR/release was performed.
- Author tree: `C:/Users/zhy76/.codex/worktrees/build-snapshot-review/STM32-Toolkit`
- Independent review tree: `C:/Users/zhy76/.codex/worktrees/build-snapshot-final/STM32-Toolkit`,
  clean at the exact source heads.
- Primary independently inspected the complete accepted-base-to-final-CodeHead diff. Final
  binary diff SHA-256: `5ed766a5f97c0390f9b1311c6972b0da273d0d4717cce81b26df96362a3083be`.

## Implemented behavior

- Version/binding verification uses actual MCP-client tool results: `stm32_doctor`
  `data.runtime.toolkitVersion`/`data.publicInventory`, real client tool list/input schemas, and
  `stm32_project_context` `data.project.root`. A separately started launcher/CLI call is supporting
  evidence only, not proof of the live MCP binding. One VS Code restart refreshes an installed
  server; no checker, shim, or auto-repair was added.
- Full `OperationResult` (`ok`, `code`, `message`, `data`, `details`) is read/retained before a
  concise summary. `ok=false` details and `capabilityDetails` diagnostics are never discarded;
  `ok` is checked before dereferencing `data`.
- Successful context adds compact `data.firmwareRoutes`. `managed` mirrors
  `capabilityDetails.flash` (`stm32_probe_list` -> `stm32_flash`, `buildId`/`elfSha256`,
  Git-shaped managed provenance). `imported` is always `not-evaluated` in context
  (`stm32_firmware_import` -> `stm32_firmware_admit` -> `stm32_flash_imported`), needs no Git or
  managed model, and has separate immutable-copy and hardware authorizations. A managed blocker
  does not block the explicitly selected imported route; no route switches automatically. Debug,
  Monitor, Target-test, and recovery guidance never offers an imported receipt as a remedy.
- Managed flash stop rules are scoped to that route. Discovery-only probe enumeration precedes
  any context/model gate; a context/model error preserves its diagnostics and does not prove the
  imported endpoint absent, while invalid roots, binding errors, and endpoint errors still stop.
- `stm32_keil_preflight` blockers gain additive presentation-only `remediation`:
  `category` (`needs-user-input`/`unsupported`), `summary`, optional `tool` naming only a real MCP
  tool, optional `skill` naming a companion Skill, and `requiredInputs`. Encoding guidance is
  conditional on explicitly declared per-file charsets and comment-only content. Framework/FPU/ABI/
  option guidance preserves actual toolchain/build evidence and never edits evidence or removes
  controls merely to clear a blocker; no override API is claimed. Unknown codes stay unsupported.
  `blockerSummary.byRemediation` is additive; original blocker fields, `total`/`byCode`, plan
  serialization, plan ID, and digest are unchanged.
- MCP descriptions, five touched Skills, and the VS Code/user guidance were aligned: actual MCP
  evidence, complete diagnostics, two write authorization boundaries (import APPLY and imported
  flash), read-only PLAN/ADMIT, `data.plan_id` (Keil convert/configure) vs `data.planId` (firmware
  import) with request `planId`, and source-only status. No migration grammar, ABI, RAM, encoding,
  debug, or backend support was expanded.

## Changed files

- Product: `tools/stm32-toolkit/src/stm32_toolkit/context.py`,
  `migration/preflight.py`, `mcp_server.py`.
- Skills: `skills/flash-firmware`, `skills/build-firmware`, `skills/migrate-keil`,
  `skills/setup-stm32-env`, `skills/debug-firmware` (`SKILL.md` each).
- Docs: `docs/user-guide.md`, `README.md`, `README_zh-CN.md`, `docs/release-status.md`
  (dated history preserved; additive source-slice note).
- Tests: new `tools/stm32-toolkit/tests/test_ai_call_guidance.py`; modified `test_context.py`,
  `test_keil_preflight.py`, `test_plugin_layout.py`.

`d78` -> `e023` changed only four documentation/Skill files and one test assertion. All runtime
product source bytes are identical between those heads.

## Verification evidence

Primary verified evidence from native `tool_use`/`tool_result` events and JUnit, not agent prose.
Artifacts: `D:/codex-tmp/ag24`.

- Tooling: native PowerShell registration and `Get-Location` smoke passed with strict empty MCP
  configuration, the existing provider, and process-only registration/respect-policy flags; no
  permission denials. Author/continue file-only calls hit the 65-turn limit with edits retained;
  fix/docfix continuations completed. No alternate shell or permission bypass.
- The offline public-inventory regression tests confirmed 52 MCP tools and 9 Skills; version remains `1.3.0`. The CLI initialization JSONL proves its restricted native tool inventory, not the Toolkit MCP inventory.

Author checks (Windows CPython 3.12, same-tree sources):

```
python -m pytest tools/stm32-toolkit/tests/test_ai_call_guidance.py -q --tb=short --basetemp=D:/codex-tmp/ag24/p-new -o cache_dir=D:/codex-tmp/ag24/c-new --junitxml=D:/codex-tmp/ag24/new.xml
python -m pytest tools/stm32-toolkit/tests/test_context.py tools/stm32-toolkit/tests/test_doctor.py tools/stm32-toolkit/tests/test_keil_preflight.py tools/stm32-toolkit/tests/test_build_snapshot.py tools/stm32-toolkit/tests/test_mcp_roots.py tools/stm32-toolkit/tests/test_mcp_migration_build.py tools/stm32-toolkit/tests/test_external_firmware_routing.py tools/stm32-toolkit/tests/test_public_inventory.py tools/stm32-toolkit/tests/test_plugin_layout.py -q --tb=short --basetemp=D:/codex-tmp/ag24/p-regression -o cache_dir=D:/codex-tmp/ag24/c-regression --junitxml=D:/codex-tmp/ag24/regression.xml
python -m pytest tools/stm32-toolkit/tests/test_ai_call_guidance.py tools/stm32-toolkit/tests/test_context.py tools/stm32-toolkit/tests/test_plugin_layout.py -q --tb=short --basetemp=D:/codex-tmp/ag24/p-final -o cache_dir=D:/codex-tmp/ag24/c-final --junitxml=D:/codex-tmp/ag24/final.xml
```

- `new.xml` at `d78`: 12 passed.
- `regression.xml` at `d78`: 257 collected, 256 passed, 1 failed, 0 skipped. This was not an
  all-pass run. The failure was
  `test_context.py::test_keil_context_stays_read_only_and_reports_inspection_capabilities`: its
  exact expected dict omitted the additive `firmwareRoutes` (all seven original items matched).
- Correction: Claude changed only that assertion, checking/popping route metadata via the existing
  helper and retaining every old exact-dict and read-only guard. No product code changed.
- `final.xml` at `e023`: 80 passed, 0 failed, 0 errors, 0 skipped (new 12 + context 48 + plugin
  layout 20).
- Reused evidence: 189 passes remain valid from unchanged modules on `d78` — doctor 25 +
  preflight 20 + build_snapshot 50 + mcp_roots 61 + mcp_migration_build 19 +
  external_firmware_routing 10 + public_inventory 4. Their source, fixtures, and contracts are
  unchanged by the final doc/test-only delta. This is explicit reuse, not a new full 257 run.

Primary independent checks:

- `review.xml` at `d78`: 103 passed (new 12 + preflight 20 + mcp_roots 61 + external routing 10).
- `review-final.xml` at `e023`: 33 passed (new 12 + corrected context case 1 + plugin layout 20).
- Both subprocesses exited 0. `review-execution.json` and `review-final-execution.json` record the
  exact argv, head, and log hashes.
- Five touched Skills passed `quick_validate` at `d78`; the three changed at `e023`
  (build/flash/migrate) were revalidated there and the other two were unchanged. Validators check
  frontmatter only; primary performed semantic scenario review. Native invocation reported normal
  success; JUnit confirms test counts. No unobserved exit codes are claimed.
- Existing nonfatal `pydantic_settings.IncompleteFieldDefinitionWarning` (lifespan) appears in
  `mcp_roots`; it caused no test failure.
- `untouched-final.json` confirms 13 frozen assets including `CHECKSUMS` still match original
  hashes, and baseline `CHECKSUMS`/release manifest/runtime state are unchanged.
- No install, cache, global Skill, or runtime mutation; no VS Code restart; no release build;
  no remote push/tag/PR or public release. Original `mobile-robot-controller` and hardware were
  untouched.

## Limitations

- `firmwareRoutes` and preflight `remediation` are source-only fields. They are not in the frozen
  `1e6ea849c21fb3786d60dba0254acb375d016a62` artifacts/runtime; restarting VS Code does not install
  them. Real VS Code/MCP refresh is deferred to the user after a later matching build/install.
- No hardware, install qualification, packaging, or public-release evidence is claimed.
- Skill validation covers frontmatter only; semantic behavior is primary-reviewed.
- This report does not approve its own diff. Primary acceptance is recorded separately in
  `review.md`.
