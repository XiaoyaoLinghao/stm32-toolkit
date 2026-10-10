# Release status and retained limitations

## Published v1.0.0

GitHub [v1.0.0](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.0.0) was published
on 2026-10-08. Its fixed product source is `968cbb69b1f54b95a8fdc18a550481f6ff7c1268`.
It was accepted as `LOCAL_ACCEPTED_WITH_USER_APPROVED_COVERAGE_EXCEPTION`; the version number
alone is not proof that every numerical coverage threshold passed.

| Published identity | SHA256 |
| --- | --- |
| Windows x86_64 ZIP | `ba242f2d1d79b625e42ac32306a3f854fa50c15a5bcb64e944d80ef833f22cc6` |
| Source ZIP | `4038f6e6c1cf402c25c3050f0f8ee3db78003dcaddc510935a45396b95518c91` |
| release-manifest.json | `27a2e8a6f00857855a5ba420552d36547baa5f92c351c9c24ee47878f87377fa` |
| Accepted U64 coverage record | `e232e8c2ce82f73109d05e3b6f3e811b56949cec50553cecfd2c4b2112e6c5d2` |

Published assets and their original checksums remain authoritative; repository cleanup does not
rebuild or replace them.

| Branch coverage | Accepted U64 measurement | Permanent threshold | v1.0.0 disposition |
| --- | --- | --- | --- |
| Toolkit overall | 12047/13592, 88.6330% | 90% | Numerically UNMET; one-time user exception |
| Toolkit risk-core-v2 | 11429/12918, 88.4734% | 90% | Numerically UNMET; one-time user exception |
| Monitor overall | 2770/2956, 93.7077% | 90% | Met |
| Monitor risk-core-v2 | 2770/2956, 93.7077% | 95% | Numerically UNMET; one-time user exception |

The exception applies only to the fixed RC4/U64 candidate. It does not lower permanent thresholds,
change membership/denominators/subprocess collection, or authorize any future candidate or remote action.
Unchanged historical physical evidence was reused within its original scope; it is not a new RC4
hardware execution. Package/installation/upgrade/rollback/native Windows evidence retains its actual
source identity and limitations.

Known limitations retained from that acceptance:

- A historical Monitor retention operation timed out at 180 ms, later reported `SQLITE_INTERRUPT`,
  and had already durably deleted 512 values. The precise phase/root cause remains unknown.
  `MONITOR_STORAGE_BUSY` after writes begin does not guarantee rollback or completion. Wait for the
  writer and inspect actual history through normal queries; do not blindly repeat the operation.
- Resource-release evidence does not cover every direct cancellation of a running child/hardware
  session or stale-owner health reclaim. Sending termination is not proof of release.
- The recorded rollback experiment proved recovery after promotion when state replacement was
  rejected by a lock. It does not prove recovery after every successful/partial state write.
- Missing execution of exceptional state combinations remains uncertainty, not proof of absence
  of defects. Later passing checks do not erase the original failures.

Original acceptance and supporting records are retained in Git at
`694c825d29a55a53052a148efa4cc6720c315a04`, including
`docs/testing/2026-10-08-rc4-local-handoff.md` and the 2026-09-19 release plan.
Use `git show <commit>:<path>` to retrieve historical material; it is not an instruction to recreate
old machine-local runtime or evidence paths.

## Published v1.0.1

The user approved [the patch specification](superpowers/specs/2026-10-10-stm32tk-101-patch-design.md)
and [implementation plan](superpowers/plans/2026-10-10-stm32tk-101-patch-plan.md) on 2026-10-10,
including audit-driven removal of obsolete history from the current master tree.
The remote accepted base is `694c825d29a55a53052a148efa4cc6720c315a04`.

Implementation and independent review are complete for all five approved slices. The frozen artifact
source is `0f06c659f5e04aa1f8e53022eae9b5e964da2b4b`; two clean builds produced 13 identical assets,
and bundle, dependency, license and SBOM checks passed. Python related regression passed 1709 tests
with one Windows symlink skip, followed by 381 passed / one skipped in 17 supplementary modules.
The final UI run passed 271 tests. The current tree removes 417 obsolete historical files and updates
the bilingual README and user guidance. Remote delivery is tracked separately through Git refs and pull requests.

**The user-authorized v1.0.1 coverage exception is accepted:** every measured scope is at least the
published v1.0.0 fraction. This is a new conditional decision, not inheritance of the old exception.

| Branch coverage | v1.0.0 | v1.0.1 | No-regression condition |
| --- | --- | --- | --- |
| Toolkit overall / broad-core-v1 | 12047/13592 (88.6330%) | 12124/13674 (88.6646%) | PASS |
| Toolkit risk-core-v2 | 11429/12918 (88.4734%) | 11494/12988 (88.4971%) | PASS |
| Monitor overall / broad-core-v1 / risk-core-v2 | 2770/2956 (93.7077%) | 2770/2956 (93.7077%) | PASS |
| UI aggregate | 784/810 (96.7901%) | 796/822 (96.8370%) | PASS |

UI also retains its 90% gate for every positive-denominator source file (25 PASS, four N/A).
Toolkit's permanent overall90/risk90 and Monitor core95 remain numerically unmet; those thresholds,
membership and native denominators were not lowered. Changed Python files use combined current
native data; only unchanged Git blobs reuse accepted U64 data. Earlier measurements remain retained.

GitHub [v1.0.1](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.0.1) was published
on 2026-10-10 at 11:03:42 UTC and is marked Latest. All 13 uploaded assets were downloaded and
independently matched by name, size and SHA256 against the frozen local artifacts and GitHub digests.
The annotated tag `080cec43a36401f1bf8824e779d423c0e8e54a36` resolves to the fixed package source
`0f06c659f5e04aa1f8e53022eae9b5e964da2b4b`. The v1.0.0 tag and 13 assets remain intact.

**The scoped installation and physical qualification checks passed.** PR #16 was merged at
`0b3e3bbf9fa4dcb11dac647faed2dfec86a3bac5`. The user subsequently authorized current physical
verification and v1.0.1 Release publication, confirming the same STM32F429ZGTx board and that its
firmware need not be preserved. Final-package fresh installation and isolated 1.0.0 to 1.0.1 Repair
passed, including runtime state, dependency checks and retained user markers. Installed MonitorRuntime
HTTP/authentication/normal-stop smoke passed; this does not cover the long-running CLI serve lifecycle.

The first current physical Target execute failed with `TEST_EXECUTION_FAILED` and empty public details;
that attempt produced no TestRun or successful flash receipt. Its lease was released and worker exited,
and follow-up hardware operations stopped. The original cause remains unresolved. A separately reviewed
attach-only diagnostic then passed, followed by a freshly prepared full Target attempt using an
observational exception-capture wrapper around the unchanged installed CLI.

On the confirmed STM32F429ZGTx/CMSIS-DAP setup, the fresh under-reset/SWD 100 kHz attempt verified
7812 flash bytes and passed the physical `d3-heartbeat` case (2200 ms, one passed/zero failed);
authoritative show agreed. A variable read, a finite sample window and one `GPIOE.ODR` read passed
their fixed criteria, with source/build/ELF/session identity consistent throughout and leases released.
The 1000 ms / eight-slot sample delivered three increasing values, dropped five slots and reported
seven deadline misses (about 0.372 Hz). This does not establish sustained 1 Hz delivery. The register
read returned `0x00000010`; it is a point observation, not an external waveform measurement.

The historical project's native linker does not independently exercise the new generated stack aliases;
their accepted linker/software evidence remains separate. Browser UI, CLI serve/Ctrl-C, IDE handoff,
complete Fault, visual LED and external waveform checks were outside this current physical scope.
The original failed attempt and the sampling limitation remain part of the release record.
See [final qualification](codex/returns/STM32TK-101/qualification.md) for fixed artifact hashes,
evidence ownership, retained limitations and published release provenance, and
[the execution ledger](codex/returns/STM32TK-101/execution.md) for slice reviews and test records.
Later documentation and UI-test commits do not change the source identity of the existing artifacts.

The exact authorized baseline fractions and unchanged collection rules are in
[release qualification](testing/release-qualification.md). Numerical acceptance uses exact fractions
before rounding and is bound to the measured candidate source.
