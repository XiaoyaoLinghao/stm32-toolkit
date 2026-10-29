# PYOCD046-HID: finite Windows HID reads through the upstream dependency

Accepted base: `62bede1d55a513f3dfd8d634b2d3116b0de41890`.
Primary Codex owns requirements/spec/plan/orchestration/full-diff review and
acceptance. Local Claude Code CLI owns implementation/tests, unchanged current
configured route; no Codex implementation fallback. User authorized isolated
official0.46.0 dependency preparation and offline implementation/verification.
No existing-runtime installation, hardware, packaging or remote authority.

## Problem and public behavior

The one-shot diagnostic captured pyOCD0.45.1 waiting in Windows HID read while
Session construction queried DAP_Info/MAX_PACKET_COUNT, before SWD setup. See
[hardware report](../../codex/returns/SESSION-TRACE/constructor-diagnostic-2026-10-29.md).
Upstream0.46.0 includes a finite HID timeout and empty-response error. Use that
official release through coherent dependency/setup/handoff contracts, without
monkeypatching or vendoring SDK code. This bounds that dependency read; it does
not prove this probe responds, fix IPSR=3, or qualify ordinary flash.

1. Probe optional dependency and both release-policy pins become exactly0.46.0.
   Change only the two pyocd values in policy, preserving all other bytes. Its
   expected SHA256 is
   e897775325a8bdd4828a4066913e64e4fa561179ae1d9f7d2b0d334b5a391aaf.
   Setup's trusted policy anchor must match it; utility anchor is unchanged.
2. Setup uses0.46.0 and preserves the existing PEP440 range-check mechanism with
   new bounds >=0.46.0,<0.47. Test old0.45.1/0.45.1.post1, below-minimum/prerelease
   and next-stable0.47.0 refusal;0.46.0 and0.46.0.post1 acceptance. A bounded
   distribution range is not qualification of every version it admits; release
   policy and handoff still pin0.46.0 exactly. No runtime-version1.3.5 promotion.
3. Cortex-Debug handoff profile and skill require pyocd0.46.0, while1.12.1
   Cortex-Debug, ticket/raw-ID identity, script suppression and exact paths
   remain governed by existing contracts. Setup skill agrees with new pins/range.
4. Current installed-API tests require the current policy's actual pyocd pin;
   retained0.45.1 component-admission files stay immutable historical evidence,
   with their own closed hash checks still enforced. Fresh actual0.46.0 fake-HID,
   bounded-fake RTT/semihost and backend tests provide new software-only evidence.
   No copied version string may stand in for fresh execution or hardware proof.
5. The Unreleased changelog explains upstream finite-read dependency repair and
   pending hardware qualification without rewriting published1.3.4 history.

## Boundaries and environment

Ordinary default remains100kHz. No1MHz gate, frequency/backend override,
limit-packets workaround, skipped metadata query, retry, recovery or deadline
increase. Production service5s versus SDK default HID10s remains an explicit
limitation: outer failure may still precede SDK timeout. Do not call that root
cause solved or change its lifecycle in this dependency slice. Keep existing
disabled-debug-sequence workaround unless source/API evidence shows a separate
change is necessary; report such a finding rather than expanding this task.

Real CPython3.12.14 image:
C:/Users/zhy76/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe.
Candidate-only SDK layer: D:/codex-tmp/st135-pyocd046/candidate-site; other deps
borrowed read-only at D:/codex-tmp/kx23/venv/Lib/site-packages. Official wheel
SHA256 f37c1ef65a1e78b42c9bccf4f34fbde98c4ea225e87534ee872e324aae230ba5.
All17 applicable metadata requirements are satisfied; actual APIs still need
fresh tests. Never import/use the old venv redirector as the diagnostic image.
Use short, separate D:/codex-tmp test/evidence directories and no shared caches.

## Required evidence and verdict

Primary records original child cleanup separately: same held Windows handle
matched PID29940/creation FILETIME/image/attempt/lease, one authorized terminate,
confirmed exit238, original lease bytes unchanged. Target remains UNKNOWN; this
is operational cleanup, not a successful attach/flash or lease-release claim.

Claude edit is file-only with actual matched native inventory/events and exact
scope. Separate verify tasks run only coordinator-supplied native PowerShell
commands after real inventory/smoke. Fresh output/JUnit/source/runtime hashes
must show: setup range/anchors and fake-bundle regressions; handoff/profile and
plugin contracts; actual0.46.0 HID read receiving a finite timeout argument,
normal response and empty-response error using a fake HID device; real SDK RTT/
semihost APIs against existing bounded fakes; backend/reset/attach regressions.
Do not enumerate USB or access a device in any test. Capture real selected SDK
module origin/version; mismatched dependencies fail rather than skip.

Primary independently reviews the complete accepted-base-to-CodeHead diff in a
clean exact-head worktree, verifies policy trust bytes and selected real-SDK/
contract cases, and records source identity, native commands, actual subprocess
exits, fresh reports and limitations. SOFTWARE_COMPLETE_HARDWARE_PENDING is the
maximum overall verdict without new physical evidence. No previous hardware
authorization or success is reused for this upgraded SDK.
