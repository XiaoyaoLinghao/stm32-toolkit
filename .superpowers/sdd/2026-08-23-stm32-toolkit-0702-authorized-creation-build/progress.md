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
