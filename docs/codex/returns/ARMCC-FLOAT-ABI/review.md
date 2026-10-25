# ARMCC-FLOAT-ABI independent review

Verdict: **ACCEPTED_WITH_FIXES** for this bounded offline source slice.

Accepted base `386d63bc2fc5c633c1296c87601ae188cf09ebfd`; tested CodeHead `1bf7a7a3b44538a13d826e1790d15bde2bf15532`. Primary owns specification, orchestration, independent complete-diff review and acceptance. Local Claude Code CLI with the existing `deepseek-v4.1-flash[1m]` configuration owns implementation, tests and product guidance. Author branch `codex/armcc-float-abi`; no ownership override or remote authority. Review used the separate clean detached `build-snapshot-final/STM32-Toolkit` tree at the exact CodeHead, then reviewed the documentation-only follow-up. See [design](../../../superpowers/specs/2026-10-25-armcc-float-abi-design.md), [plan](../../../superpowers/plans/2026-10-25-armcc-float-abi-plan.md), [author report](implementation-report.md) and [machine evidence](evidence.json).

## Conclusion and accepted behavior

The evidence does not support a blanket replacement of ARMCC/FPU2 hard with softfp. The official Arm compiler/migration references in the design distinguish hardware arithmetic from calling convention; a bare-metal hardware-FPU rule does not establish the Linux softfp default. This slice retains only the narrow historical ARMCC/Cortex-M4/FPU2 hard candidate and labels it inferred. Original binary compatibility is not established.

Unsupported numeric uFloatingPoint mappings to soft/softfp are removed. Literal soft/softfp/hard remains a project declaration, not verified binary evidence. Inspection captures selected-target ArmAdsMisc/RvdsVP raw text. Absent/empty/2 preserves the narrow historical candidate; other nonempty selectors block that FPU2 normalization even with an explicit literal declaration. This is a bounded compatibility rule, not a verified generic numeric decoder. Unsupported compiler/FPU cases and existing C target/group/file misc-control blockers retain their refusal behavior; no ABI override parameter, control stripping or automatic ABI switch was added.

The same derived floatAbi evidence is returned in preflight analysis, PLAN and conversion report. It includes origin, selectedAbi, raw settings, rule/reason, warning, nextStep and baselineVerified=false. It participates in plan identity and fresh APPLY comparison rather than becoming caller-controlled authority. Inferred evidence can coexist with an unrelated misc-control blocker: consumers must inspect the full blocker list. A blocked diagnostic plan can be returned when Git/root/selection prerequisites permit; its ID cannot authorize application. Readiness, plan existence, authorization and baseline verification are distinct.

The real project observation was read-only: Project/LWIP.uvprojx SHA256 `037236a2ae7cd4cebfa59944a881367b042f2c36627ad6169d63ae1ff20f4567` before and after, ARMCC5.06u3/Cortex-M4/FPU2/RvdsVP2, absent uFloatingPoint; expected Project/OBJ/LWIP.axf and Project/LIST/LWIP.map unavailable. No original source was edited or built. No object/library ABI parsing or comparison was performed, so this is not proof of equivalence with the original firmware or libraries.

## Review findings and disposition

| Finding | Disposition |
| --- | --- |
| Draft comments presented XML numeric meanings and RvdsVP2 as officially established. | Claude replaced those assertions with evidence-limited language and a historical compatibility rule. Compiler facts and original-binary facts remain separate. |
| New selected-target inspection test passed simple_project's returned uvprojx file as an inspection root. | Both owners reproduced the same single failure. Claude changed exactly two calls to `.parent`; assertions and product validation remain intact. The verifier's initial environment attribution was rejected by the primary: this was a test-code defect. |
| Fresh Skill simulation correctly refused unsafe progression but said blocked A/B could not generate any PLAN. | Claude clarified the Skill and user-guide against workflows.py: diagnostic read-only PLAN can return blockers if prerequisites permit; APPLY remains blocked. This clarification occurred after CodeHead and changed no code/tests. |

The full accepted-base diff, including new helper/tests and all documentation, has no remaining blocking source finding. Existing empty-path legacy blocker validation may report MIGRATION_PLAN_INVALID for target misc controls or unsupported compiler plans; the new tests preserve this refusal rather than widening that unrelated contract.

After the guidance correction, a second fresh read-only Claude CLI simulation correctly allowed conditional diagnostic PLAN for blocked A/B, refused APPLY, and treated C's softfp declaration as requiring a reviewed plan and authorization without proving library compatibility. Both raw responses are retained. This validates the relevant guidance choices in synthetic cases, not an actual VS Code session, installation, tool execution or comprehensive factual audit of every sentence in the evaluator's prose. The corrected Skill also passed structural validation.

## Verification and retained evidence

Windows CPython3.12.14, same-tree Toolkit/Monitor PYTHONPATH, read-only installed dependencies, run-owned D:/codex-tmp/ab25 roots. Fixtures are synthetic; GNU-related consumer checks are offline software evidence and do not prove ARMCC equivalence or hardware behavior.

| Owner / source | Result |
| --- | --- |
| Primary / accepted base |172 migration baseline tests passed. |
| Claude and primary independently / 4eea45d6 |Each671 passed,1 failed,0 skipped out of672; failure retained. |
| Claude and primary independently / tested CodeHead |Each672 passed,0 failed/errors/skipped:32 new ABI,118 inspection,98 plan,55 apply,20 preflight,12 AI guidance,19 MCP,318 generation. |
| Primary / 4eea45d6 |311 additional shared-fixture consumer tests passed,0 failed/skipped: common syntax/compiler, startup/generation, RAM/external regions, scoped includes, debug configuration, linker compiler, CLI/workflows. Reused because the only subsequent code/test change was the two inspection-test call sites; these product and consumer bytes are unchanged. |
| Primary / CodeHead and documentation follow-up |migrate-keil Skill structural validator passed; git diff whitespace check passed. |

There are983 distinct applicable passing cases with the stated reuse; no claim of a final full repository/release matrix rerun. Exact argv, hashes, JUnit and primary actual subprocess exits are retained in evidence.json and the run root. Author execution is supported by actual native PowerShell tool_use/tool_result plus JUnit. Initial pytest explicitly returned exit1; final native output did not print an exit code, so CLI exit0 is not substituted for pytest exit0. Primary final subprocess exit0 is recorded. Non-failing pydantic_settings/runpy warnings are retained; no dependency changes were made.

The first file-only author invocation attempted an unavailable Bash tool. Its result said Bash was disabled; no shell ran. Primary stopped the exact owned process, preserved the log and confirmed no edits, then restarted file-only work without widening permissions or retrying the denied operation. Two later65-turn file-only limits preserved work and were continued; code editing and exact-command native verification remained separate. This is not a claim that the earlier unavailable call succeeded.

## Delivery boundary

Current-source VS Code/Skill guidance is synchronized; existing installed/frozen1.3.0 does not acquire these patches by restarting the IDE. Toolkit stays1.3.0. The user-designated integration/release target is **v1.3.1 after the remaining agreed improvements**. Original project modification, hardware, runtime/global skill installation, packaging, remote publication/push/PR/tag/merge did not occur. No new release or hardware qualification is granted; existing deferred platform/release obligations remain for that phase.

Remaining sequence: stale-build/clean guidance, generated VS Code paths/tasks, doctor toolchain/extensions readiness, flash frequency/failure guidance, memory margin warnings, combined integration and authorized release/IDE/hardware verification. This acceptance does not finish that backlog.

Automatic approval policy rejected cleanup of passed disposable pytest/cache directories under D:/codex-tmp/ab25, returning only `blocked by policy`. No deletion executed and no alternate deletion tool or bypass was used; temporary roots, failed fixtures and evidence remain. See cleanup.json in the run root.
