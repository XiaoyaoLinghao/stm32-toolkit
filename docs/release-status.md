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

## v1.0.1 in development

The user approved [the patch specification](superpowers/specs/2026-10-10-stm32tk-101-patch-design.md)
and [implementation plan](superpowers/plans/2026-10-10-stm32tk-101-patch-plan.md) on 2026-10-10,
including audit-driven removal of obsolete history from the current master tree.
The remote accepted base is `694c825d29a55a53052a148efa4cc6720c315a04`.

This is not yet a published release. Current implementation, accepted CodeHeads and test results are
recorded in [the execution ledger](codex/returns/STM32TK-101/execution.md). Final artifact identity,
upgrade validation, independent review and current release qualification must be recorded before
publication. RC4 coverage exceptions and old hardware authorizations do not transfer automatically.
