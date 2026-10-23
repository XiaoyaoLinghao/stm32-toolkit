# Build snapshot independent review

Verdict: **ACCEPTED_WITH_FIXES** for the local build/Git decoupling software slice. No blocking review findings remain. This does not qualify a release, installed runtime, IDE session or hardware operation.

- Accepted base: `690f579d4efe1d2616e0c1d9289263c24069134a`.
- Final CodeHead: `5908747d0cd5a783ecc660ca3090f9633ca554b2`.
- Implementer report head: `258ab482093f658413abae9907132110574d1993`.
- Implementation branch: `codex/build-snapshot`; primary owns specification, orchestration, independent full-diff review and acceptance. Claude Code CLI 2.1.308 implemented code/tests/corrections using the user's unchanged `deepseek-v4.1-flash[1m]` provider configuration. No Codex-hosted implementation agents.
- Authorized scope: local software and guidance. No remote mutation, version/release change, runtime installation, original robot project edit or physical operation.

## Review and resolved findings

The primary reviewed the complete accepted-base diff in clean isolated review worktrees, including both schema copies, every changed product/test/skill/document file, the new snapshot regression suite and all supplemental corrections. `primary-complete-code.diff` under `D:/codex-tmp/kg23` retains the final full code diff. Schema copies are byte-identical and `git diff --check` passes. The final report was separately reconciled; final wording changes alter no executable behavior.

Git availability is optional only for builds. Existing schema-1 identity/result ordering and strict Git collection remain compatible. Schema-2 evidence explicitly carries an input-snapshot baseline, null Git fields and bounded diagnostics; no commit is invented. Current inputs, model/project/Toolkit identity, safe artifact paths and ELF/MAP hashes govern freshness. No-op reuse cannot adopt stale, failed, malformed or cross-provenance evidence. Valid snapshot identities are refused at shared hardware admission; existing outer wrappers can map the code. Context distinguishes this known blocker from unprobed hardware while probe discovery remains independent.

Review corrections resolved missing nullable record fields being accepted, unhashable diagnostic values raising TypeError, missing current project/Toolkit comparisons, misleading hardware capability states, lost provenance on post-collection failures, and an unintended change to legacy failure records. The final guidance uses actual field names and valid literal examples and does not promise one external error code from every wrapper.

The existing LF linker fixture required a Windows checkout integration fix. Two earlier restore attempts did not rewrite a clean-filtered CRLF file; the approved design amendment added an exact-path `text eol=lf` attribute and restored the unchanged Git blob. An existing review worktree still retained its old CRLF bytes after switching commits, producing one recorded fixture failure in `primary-final.log`; no test was weakened. A newly created clean worktree at the amended head checked out LF correctly and passed both selected tests. The durable rule and this distinction are verified; the failure is retained rather than erased.

## Evidence

All evidence is offline. Existing Python 3.12 venv, explicit same-worktree PYTHONPATH and external unique temporary/cache directories were used. No physical probes were enumerated or attached.

| Owner / source | Check | Result |
| --- | --- | --- |
| Claude CLI / final behavior bytes | Snapshot/build runner; context/flash/debug; identity; MCP/inventory; CLI/workflows/hardware adapters | 146, 236, 101, 61 and 360 passed respectively; commands and original logs identified in implementation-report.md. These are affected suites, not a release matrix. |
| Primary / clean `a3d20144164c4d29f25c9d5193724ad124db7779` | Entire new snapshot suite | 50 passed, exit 0; `primary-snapshot.log`. All exercised behavior and tests remain unchanged at final CodeHead. |
| Primary / clean fresh `61323e58982af27a3784855184cb0c13470f3fa0` | LF linker byte oracle and real non-repository build | 2 passed, exit 0; `primary-fresh.log`. Final changes after this head are guidance/report only. |
| Primary / final CodeHead and report head | Complete diff, schema equality, guidance and evidence reconciliation | Passed; clean reviewed trees and no remaining blocking findings. |

Primary commands:

```text
python -m pytest tools/stm32-toolkit/tests/test_build_snapshot.py --basetemp=D:/codex-tmp/kg23/bt-primary-snapshot -o cache_dir=D:/codex-tmp/kg23/cache-primary-snapshot -ra
python -m pytest tools/stm32-toolkit/tests/test_firmware_identity.py::test_real_linked_toolkit_template_stack_symbols tools/stm32-toolkit/tests/test_build_runner.py::test_non_repository_builds_snapshot_identity --basetemp=D:/codex-tmp/kg23/bt-primary-fresh -o cache_dir=D:/codex-tmp/kg23/cache-primary-fresh -ra
```

The non-repository regression runs the actual installed ARM GNU GCC 14.3.1/CMake toolchain on a synthetic managed fixture and links its ELF successfully. Most other build regressions use fakes. The test named `missing_git_executable` simulates a nonzero Git exit; a separate ProcessError test covers the missing/denied launch class. No real executable was removed. These distinctions were corrected in the implementer report.

## Remaining boundaries

Snapshot builds are build-only; hardware protocol support without Git is not included. Migration plan/apply still require a committed clean Git baseline. The original `D:/WorkSpace/mobile-robot-controller` remains read-only. GBK comment preparation, startup generation and explicit multi-RAM placement continue as separately specified work; native Keil builds, external firmware import and real VS Code extension readiness are not claimed. No source acceptance here updates the installed v1.2.0 runtime or GitHub Release automatically.
