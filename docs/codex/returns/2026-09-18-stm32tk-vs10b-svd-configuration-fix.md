# VS10-B SVD configuration correction — 2026-09-18

Verdict: **CONFIGURATION_OFFLINE_ACCEPTED**. CFG-001 is closed for the active B configuration. VS10-B physical acceptance remains incomplete; no hardware operation, Target prepare/action, attempt, runtime deployment or remote mutation occurred during this correction.

## Change and ownership

User authority: “开始进行修复”, followed by “继续”, for the reviewed configuration proposal. Firmware base `822d75758f5a705fd9ef1093f3bf9d8101191570`; candidate `d29281dcaec546f8d2b430e71620067fa0586c34`, branch `codex/vs10b-svd-configuration`, active project `D:\codex-tmp\v10b-0918\p\b`. The original Luna/max firmware agent implemented the change and ran its SVD check and fresh Debug build. Only `.stm32-project.json` / `debug.readableRegions` changed, from one4-byte region to the twelve approved same-MCU ranges. Every other JSON field, raw prefix/suffix, tracked source and the full vendor SVD are unchanged. Future Watch selection remains testtime and GPIOE.ODR.

Both assigned agents subsequently hit their usage limit before final reporting/review completion. The primary, who did not implement this patch, completed independent full-base-to-head review in clean detached `D:\codex-tmp\v10b-0918\svd-review`, independently validated the actual project using existing installed functions, and prepared the later input-only source intent as integration evidence. No implementation ownership exception was used. Do not attribute the final acceptance or prediction to the quota-stopped agents.

Toolkit documentation baseline is `ad63f2424f8dc0333f1f5e9a6d12117b1faf0408`; installed product remains source `12df4fe0569104d6f0e7a827496341d999e1f3ea` at `D:\codex-tmp\v10b-0918\dgdep\data\runtime\0.9.0`. Runtime-state SHA256 remains `c878c9a6e8db4ad878d0a27061a3b65e19f630b3edc2867b7aa36c62ae58fd9e`.

## Evidence and identities

| Check | Actual result |
| --- | --- |
| Owner existing select_svd on edited active manifest, before build | PASS;1536 registers /12 ranges |
| One public arm-debug clean build | exit0; no warnings; no Release/broad matrix repeated |
| Primary complete diff/unchanged data check | PASS; exactly one file/one JSON field |
| Primary actual SVD and fresh physical-build authority | PASS; existing functions only, no backend or hardware |
| Firmware ELF/MAP compared to prior fault build | Both byte-identical; no D3 source fix applied |

New raw manifest SHA256: `6cba36b1af42b12d05f2fd5ce83fc90851a4cec976b8fbc116dbe3405cff4a50`.
New build ID: `db585b5cb902b7ee4f7f53281bbed4f7af1e26fd2a39e8b3e767bbf25d8f96b6`.
New full InputSnapshot: `75b64c62c914ed6470279e85fce5683e7d42c20b2541599867b35f97c9c49377`.
ELF: `dd8bd1cf4975d9302b1caf5e0139f7bc8f767e669e2e922d2d31be0c01bfb80b`.
MAP: `1e0b8dafaa9134e1f26ca138c124e8401fd91d351cc1a736fb57ad32529102e2`.
Actual vendor SVD remains `2b7de1e383ee415f45339b776942fe01f7b48215316629c3cc280e12661c2400`.

The fresh detached review checkout converted SVD LF to CRLF, giving raw SHA `05b491022cf05779bd40e8f8ec279408361c1d6821faf6d5c413c8c3e487c281`. The initial independent hash assertion stopped on this ENVIRONMENT difference. The follow-up preserved that failure, proved normalized bytes and all1536 parsed register objects equal, and separately selected the unchanged raw active SVD successfully. No source normalization, rebuild or product fix followed. Final independent command exited0 after3875ms.

Owner evidence: `evidence/svd-config-fix/{svd-selection.stdout.json,debug-build.command.txt,debug-build.stdout.json,debug-build.exit.json}`. Final independently run checks and complete diff: `evidence/svd-config-review/{primary-check-r2.command.json,primary-check-r2.stdout.json,primary-check-r2.exit.json,complete-base-to-head.diff,primary-review.json}`.

## Retained boundaries and next use

The older receipt/Target failure still proves the old configuration's physical execution. It does not bind the new build/input hashes even though ELF is identical. Old attempt, digests, single-use Monitor marker and source authorization remain untouched. The existing closed-loop03 card stays stopped, and the hard-coded old Monitor output directory must not be reused for a new attempt; any future run needs a reviewed entry binding to a fresh authorized output directory, not deletion of the consumed marker.

A fresh input-only D3 one-statement prediction was derived from actual current fault bytes using existing SourceChangeIntent and _derive_physical_intent. Expected after InputSnapshot is `a4dabccbffb59ac9e9200e51d01b9eaa26b07f0b902826405aeb9c7d5750c6c3`; intent digest `4358ff76297e196de36dc8f544ed2b10e7f36d39cd4231bd3c97b5922eb4fae4`. Files `evidence/svd-config-review/source-intent-cli-input.json` and `source-intent-prediction.json` are **NOT_AUTHORIZATION**. No fixed-after source/build or live sampling has occurred.

The next separately bounded physical attempt requires fresh Target flash/readback/receipt identity after this manifest change, followed by the originally specified before/after Monitor and Diagnostic chain. Already valid Toolkit deployment, NORMAL/IDE/CLI/MCP, VS10-A and historical attempt7 evidence are preserved. Do not repackage for this configuration/documentation correction.

Do not start a timed attempt until its entire execution capacity is ready: Luna/max currently has a usage-limit failure and must be available for the later authorized firmware source change; the primary's independent review role does not permit implementing that source change. This is a remaining execution prerequisite, not an unresolved defect in this accepted configuration patch.

## Execution-path deviation and preservation

The owner's build wrapper incorrectly set TEMP/TMP/TMPDIR to `D:\codex-tmp\v10b\t\sc`, a sibling outside the narrower approved run root but still below the user's D:\codex-tmp boundary. This was an actual invocation error, not a report typo. The owner recorded that the directory exists and contains no files at audit time; that does not prove no temporary files existed earlier. Source/build/evidence outputs stayed in the approved B root. The successful build is retained. Primary's subsequent independent process explicitly checked all three variables and tempfile.gettempdir() resolve to `D:\codex-tmp\v10b-0918\t\sr`. Evidence: `evidence/svd-config-fix/environment-path-audit.json`. No deletion/move or policy bypass was attempted.

Previous cleanup rejection remains preserved; this turn did not retry it. Review trees, active build/runtime, reusable preparation scripts and necessary failure evidence remain on hold. No native-memory or curated-lesson writes.
