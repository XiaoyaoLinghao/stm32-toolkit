# T10 retrospective hypothesis assessment delivery

Primary integration acceptance, 2026-09-18 Asia/Shanghai. Task 10 Step 3 is complete under the explicitly approved retrospective amendment. It does not assert that the three-alternative assessment happened before the original repair. Original Steps 1/2/4/5/6 retain their separate evidence and acquisition dates.

Accepted software CodeHead: `e059ba14d3d8e0072206171d612f686e90329c2d`; deployed integration source: `227f8ea8b6895d4c2eaa14bd2483cfbce668b4b9`. Luna/max implemented the bounded selector/assessment correction. The independent reviewer closed the first three findings; primary inspected the full final Store correction and independently passed its append/fresh-replay regression. This record is integration evidence, not implementer self-acceptance.

One candidate was built and bootstrapped at `D:\stm32tk-data\fault-controlled-20260911\candidates\hypothesis-20260917`. Bundle verification and final Check passed: runtime healthy, state matching. All 122 Toolkit and 25 Monitor package members matched the verified wheels. The installed pyOCD launcher returned 0.45.1. The previous runtime-state SHA-256 remained `fb19f130596be014a90efae6f2195883556f4595ec73b65a6297031424c381c6`. Deployment proof is retained under `D:\codex-tmp\t10h-0917\logs` and `evidence\installed-identity.json`.

The installed public CLI created supplementary Diagnostic `f92ceecdd24b892591d0c1ea305189ce` from the original failed P3 TestRun and reached revision 14, `INVESTIGATING`. It recorded five authenticated observations with values `[1,1,3,3,3]`, all matching their expectations. These respectively establish original P3 timer variation, P3 PE3 held low, P3 PE4 variation, and original P4 PE3/PE4 variation within the captured windows.

| Alternative | Supporting assessments | Refuting assessments | Bounded conclusion |
| --- | ---: | ---: | --- |
| Timer/interrupt stopped throughout P3 window | 0 | 2 | Refuted within the captured window by typed timer and independent PE4 activity |
| GPIO/board path necessary to explain held D3 | 0 | 2 | Weighed against by register observations; electrical or intermittent faults are not measured or universally excluded |
| Intentional periodic application write holds PE3 low | 3 | 0 | Supported by original P3/P4 observations, exact authorized source change, and active-low schematic mapping |

The hypotheses correctly remain `open`/`unrated`; their seven supporting/refuting records carry the assessments. This is not a new resolution or a new physical fix. The original Diagnostic `2781df6812f2dc0ba067e0b1b9d07b5a` remains RESOLVED, original FixVerification remains PASSED, and original v3 remains COMPLETED. A fresh CLI process successfully loaded the complete supplementary chain. All 131 pinned original evidence/diagnostic/session files retained their original lengths and SHA-256 values.

Exact command arguments, stdout, stderr and exits for the 15 production calls, actual derived identifiers, and verification summary are in `D:\codex-tmp\t10h-0917\production-results`. The input files and original-file hash baseline are in the adjacent `inputs` and `evidence` directories. No hardware operation, new physical sample, or remote Git mutation occurred for this delivery. A preliminary invocation used a nonexistent console-script name and never started a process; the verified installed `stm32-toolkit.exe` entry was then used. A concurrent preservation read encountered the active Diagnostic lock; the final post-command read successfully checked all 131 files.

T10 is complete in the amended scope. Task 7's retrospective uninstrumented-board evidence, Task 11's formal bundle and Task 12's final complete-range acceptance remain separate. The existing cleanup policy hold is recorded at `D:\codex-tmp\t10h-0917\evidence\cleanup-policy-hold.json`; no rejected deletion was bypassed.
