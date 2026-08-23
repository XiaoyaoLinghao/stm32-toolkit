# SDD ledger — VS07-B authorized creation and build

- Module/phase: STM32 Toolkit 0.7 / VS07-B.
- Accepted base: \`bff9cc120923b0e9f2ba29a1b3511f1bcc26ab6e\`.
- Specification/plan owner: GPT-5.6-sol primary agent.
- Implementer: \`/root/vs07b_implementer\`, GPT-5.6-luna, reasoning max.
- Reviewer/acceptor: GPT-5.6-sol primary agent.
- Branch/worktree: \`codex/STM32TK-0702-CREATION-APPLY\` /
  \`C:/tmp/stm32tk-0702-creation-apply\`.
- Remote/install/hardware authority: none; no push, PR, merge, release,
  package/software installation, hardware action, or VS07-C work.
- CodeHead before the separate report/ledger commit:
  \`e24205f4329e531331c64b8761fbdc1736fc53d1\`.
- Product recovery commit:
  \`7c23c7a95c7011872d2fa58e43e15386724b3d61\`.
- Test-only activation-worker cleanup correction:
  \`e24205f4329e531331c64b8761fbdc1736fc53d1\`.

## History and recovery

- The accepted VS07-A baseline was \`bff9cc12\`; the original dirty
  \`D:/workspace/stm32-toolkit\` worktree was preserved and untouched.
- Sol's first review returned REVISION_REQUIRED with F1-F6. Sol's clean
  round-2 review then recorded 630 collected / 629 passed plus one
  \`CREATION_ACTIVATION_FAILED\` independent activation process, and native
  observations disproved the old protocol/updater/parser contracts.
- Local patching stopped at that non-converged boundary. The approved
  interface-level recovery design/plan replaced native protocol, parser,
  isolated-home, and lock boundaries together. VS07-C remains frozen.
- Tasks 1R-3R were executed sequentially by this sole implementer. Native
  protocol transcripts and parser fixtures came from installed CubeMX 6.18
  template/help facts; no native generation was claimed.

## RED/GREEN and verification ledger

- Task 1R RED command:
  \`py -3.12 -m pytest tools/stm32-toolkit/tests/test_cubemx_adapter.py -q
  --basetemp C:\\tmp\\p0702-r1-task1-red\` with
  \`PYTHONPATH=tools/stm32-toolkit/src\`: 10 failed, 9 passed. GREEN:
  basetemp \`p0702-r1-task1-green2\`, 19 passed.
- Task 2R RED command:
  \`py -3.12 -m pytest tools/stm32-toolkit/tests/test_cubemx_project.py -q
  --basetemp C:\\tmp\\p0702-r1-task2-red\`: 6 failed, 10 passed. GREEN:
  basetemp \`p0702-r1-task2-green5\`, 15 passed.
- Task 3R focused durable-lock command:
  authorization independent-consumer plus activation independent-process
  tests, basetemp \`p0702-r1-task3-green-lock1\`: 2 passed. The complete
  authorization/apply focused set passed 22/22.
- A bounded real-process activation proof ran 20 fresh roots: exactly one
  holder before release, two completion markers, and two exit-0 children for
  every run. Five repetitions of the independent authorization-consumer test
  each returned exactly one \`OK\` and one
  \`CREATION_AUTHORIZATION_CONSUMED\`.
- Initial affected recovery run
  \`C:\\tmp\\p0702-r3-affected.xml\`: 89 tests, one failure, no errors/skips.
  The failing assertion timed out before child communication; this was
  classified TEST (harness cleanup), not PRODUCT. The test now releases and
  communicates/kills children in \`finally\`, committed as the separate
  \`e24205f4\` correction.
- Final affected recovery set: 89/89, 0 failures/errors/skips.
- Exact public CLI/MCP set: 76/76, 0 failures/errors/skips; only the existing
  runpy warning.
- Exact approved 16-file slice: 642/642, 0 failures/errors/skips/xfails,
  JUnit \`C:\\tmp\\p0702-r3-slice-final.xml\`.
- Compileall exited 0:
  \`py -3.12 -m compileall -q tools/stm32-toolkit/src/stm32_toolkit\`.
- Accepted-base diff check exited 0:
  \`git diff --check bff9cc120923b0e9f2ba29a1b3511f1bcc26ab6e..e24205f4329e531331c64b8761fbdc1736fc53d1\`.
- Final pre-report product worktree was clean, local, and unpushed.

## Environment evidence and state

- Fresh read-only workspace:
  \`C:\\tmp\\p0702-real-observe-recovery-r3\`.
- Doctor and create-plan exited 0. Plan ID:
  \`b49c2763d7442009cda4b3189448bac8a8efc191d0e22158e005264cad694b63\`.
  Action digest:
  \`003904ff6685bd1ec796cedca5f09e364ab48a281cb224b2e7a7621577fc9cef\`.
- Create-prepare exited 2 with typed
  \`CUBEMX_REPOSITORY_MISSING\`; no authorization record was issued.
- CubeMX 6.18.1-RC2 and CubeCLT facts were discovered, but
  \`C:\\Users\\ZhangYang\\STM32Cube\\Repository\` and all
  \`STM32Cube_FW_*\` packages were absent. The \`generated\` destination stayed
  absent and no CubeMX/java/javaw process remained.
- Classification: PRODUCT evidence is the code/tests and checks above;
  TEST is the corrected child-cleanup harness defect; ENVIRONMENT is the
  missing offline firmware repository; REPORT has no format/diff failure.
- Maximum state is \`IMPLEMENTATION_COMPLETE_ENVIRONMENT_BLOCKED\`, pending
  Sol's independent complete accepted-base-to-final-head review.

## Sol independent review round 3

- Review input: `4120fe47ac1d502aa75a37a1d0e1af4dd5022c6f` in the clean detached
  worktree `C:/tmp/stm32tk-0702-recovery-review`; the reviewed range was the
  complete accepted-base-to-final-head diff.
- Exact 16-file slice: 642/642 passed, zero failures/errors/skips, JUnit
  `C:/tmp/p0702-sol-r3-slice.xml`. `compileall` and accepted-base
  `git diff --check` exited 0. Five repetitions of the two independent-process
  authorization/activation tests passed 10/10.
- Fresh read-only observation in `C:/tmp/p0702-sol-r3-observe/workspace`:
  doctor and create-plan exited 0; create-prepare exited 2 with typed
  `CUBEMX_REPOSITORY_MISSING`; the workspace snapshot was unchanged,
  `generated` stayed absent, and no CubeMX/Java process remained.
- Verdict: `REWRITE_REQUIRED`. Finding R3-F1 is a recurrence of the recovered
  F2 boundary: `test_cubemx_adapter.py::_native_618_transcript` still
  manufactures a command/OK sequence from the generated script instead of
  using a captured, sanitized native 6.18 transcript, contrary to the recovery
  design's explicit prohibition. The green adapter tests therefore do not
  independently establish the frozen native protocol.
- Finding R3-F2: an authorized IOC source drift returns the correct
  `CREATION_PLAN_CHANGED` code but leaves `.stm32tk-cubemx-control-*` on disk.
  Sol reproduced this in `C:/tmp/p0702-sol-ioc-drift-cleanup`; the recovery
  contract requires control-root removal on every exit path.
- Finding R3-F3: the authorized IOC file is read once for its hash and a second
  time for the staged copy, so the copied bytes are not necessarily the bytes
  whose digest was authorized. Finding R3-F4: host-path scanning calls
  `read_bytes()` across native output before the parser enforces file and
  aggregate byte bounds. Both violate the frozen integrity/bounded-output
  boundary.
- Finding R3-F5 is REPORT-only: the implementation report and the rewritten
  portion of this ledger contain literal escaped Markdown backticks. It does
  not invalidate passing product evidence but must not be described as a clean
  report result.
- Per the recovery plan's explicit stop condition, recurrence of the recovered
  native interface is a design blocker, not another local patch opportunity.
  No correction round was dispatched. VS07-B is not accepted and VS07-C
  remains frozen. No remote, install, hardware, or release action occurred.

## 2026-08-24 real-native redesign

- The user installed the one official package directory
  `STM32Cube_FW_F4_V1.28.3`; package.xml, Drivers, Projects, Documentation, and
  the F4 HAL driver are present. The prior ENVIRONMENT blocker is resolved.
- Sol probes r5-r8 established four additional PRODUCT boundary facts before
  product changes: official repository ZIP siblings must not be treated as
  directories; isolated TEMP/TMP is required for JNA; the normalized MCU needs
  the case-correct `db/mcu/.../Mcu@RefName` native token; and CubeMX requires a
  native Windows project path and generates `<path>/<project-name>`.
- Probe r8 exited 0 with 425 stdout lines, 10 stderr warning lines, no
  truncation/timeout, 1,458 generated files, and present sysmem/syscalls. It is
  the source for static sanitized protocol and real-template fixtures. Current
  parsing of that real tree closes at the actual Debug generator expression,
  confirming the parser rewrite is required.
- Approved replacement design/plan:
  `docs/superpowers/specs/2026-08-24-stm32-toolkit-0702-real-native-acceptance-redesign.md`
  and
  `docs/superpowers/plans/2026-08-24-stm32-toolkit-0702-real-native-acceptance-rewrite.md`.
  Tasks 1RR-3RR remain sequential checkpoints for the same sole Luna/max
  implementer. VS07-C remains frozen pending Sol acceptance of VS07-B.
