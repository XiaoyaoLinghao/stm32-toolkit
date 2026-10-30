# pyOCD 0.46.0 — one authorized constructor diagnostic

2026-10-30 verdict: **PASS_CONSTRUCTOR_DIAGNOSTIC_ONLY**.
The sole authorized invocation returned in3172ms; parent and child exited0,
the child-owned lease is released and its parent-held terminal handle is closed.
No further hardware operation followed. This is not Session.open, ordinary flash,
USB-health, target-state or release acceptance. The overall1.3.5 candidate stays
SOFTWARE_COMPLETE_HARDWARE_PENDING.

## Authorization, source and preflight

The user expressly authorized the reviewed card's single constructor diagnostic
with the original board/probe,20s parent budget plus at most2s cooperative waiting,
failure stop and no flash/recovery/runtime replacement/publication. The current
readiness reply confirmed original STM32F429ZG power/probe connection, exclusive
Toolkit use, external IDE/debugger disconnected, and no board/probe/wiring/power/
reflash changes since the previous diagnostic. Primary performed preflight,
orchestration, retained-evidence review and acceptance; no implementation or
test change was needed and no Claude edit call was dispatched.

Actual clean execution HEAD:
`b5873c5ce6f7e915a333a65af4689cf39cf5f705`, branch
codex/v135-pyocd046-entry-review. Product/test CodeHead remains
`694e1e912adfc017c31b52630a323bd733567688`; entry-slice accepted origin is
`22f047189fbb0cf1fa7de98e86a2955eb13c5ac1`. The applicable
[standard procedure](../../../testing/standard-test-procedure.md),
[reviewed card](../../../testing/cards/2026-10-30-pyocd046-constructor.md) and
[independent offline acceptance](implementation-report.md) were read first.

Read-only preflight in the actual launch environment confirmed:

- Real direct CPython3.12.14 and reviewed helper raw hash/PID-entry contract.
  No venv redirector or private test injection.
- Existing isolated pyOCD0.46.0 selected ahead of the read-only old dependency
  layer;347 Python source hashes match the accepted official wheel. Distribution
  and module origins match. Native hidapi0.15.0 binding hash matches.
- Original C:/work/stm32/fresh-out project/model/ELF reference hashes unchanged;
  configured target stm32f429xg and device STM32F429ZGTx. The ELF is not an input
  to this diagnostic and does not identify current board firmware.
- PYOCD_PROJECT_DIR,PYOCD_USB_BACKEND,PYTHONHOME,__PYVENV_LAUNCHER__ absent;
  four default project YAML paths absent including redirects/dangling links.
  Process-local source/SDK/dependency import path, no-bytecode/no-user-site/UTF8
  flags and unique short temp/output roots were bound explicitly.
- Original registry realm retained. Its snapshot was the unchanged old active
  record, hash132553cbf53af352b1503585190328e60fe976955305d8350db7faf184de7d5f.
  Preflight did not query its old owner/health, acquire, delete or force-reclaim;
  actual helper guard admission remained a mandatory gate before GO.

The run-owned authorized card supersedes only the old NONE/UNCONFIRMED authority
and current-identity entries; the independently reviewed operation/budget/stop
contract is unchanged. Evidence is under D:/codex-tmp/st135-p46-hw02:
authorization.json, authorized-preflight.json, execution-card-authorized.md,
hardware-invocation-reserved.json and native-parent-result.json. The Primary
preflight is an identity/metadata reader, not a second backend invocation.

## Sole execution and reconciled evidence

The direct native PowerShell command launched the reviewed helper with the real
Python at2026-10-30 01:03:35 UTC (09:03:35 Asia/Shanghai), using exactly the card's
run/selector/target/project/data/output/deadline arguments. No wrapper imported
or substituted the backend. Helper reported3172ms; native command wall time was
about3.52s. The20s parent deadline was not reached; no terminate.request or2s
cooperative wait was needed.

| Binding/outcome | Recorded value |
| --- | --- |
| Attempt |attempt-d7cbe6675f0b1e40c3695127240dd150 |
| Request digest |59004cf71271f4122f2246f8e32f8bf09aa45eeb89b328fd7813abe8b4ab170b |
| Session |session-2603b1cca09d38ea3e9ba64e219a15b5 |
| Direct child |PID20916; actual return0,alive=false,handleReleased=true |
| Lease |lease-99f82b0dfccd46e291115d4a7791cc51; registry now contains this ID with state=released |
| Grant/records |claim verified; READY matched; one GO; result/events verified; no errors/unexpected entries |
| Narrow facts |driverAcquired=1,enumerations=1,selections=1,sessionConstructed=true,sessionClosed=1,sessionOpened=false |
| One-shot trace |armed/cancelled successfully; native-traceback.txt and child-stderr.txt both0bytes |

Primary independently recomputed requestDigest and matched attempt/request/
claim/READY/GO/result/events PID, sourceDigest, interpreter, request and lease
identities; READY/GO precede the request deadline. The exact ordered12 events
contain one driver/select/construct/close/release path. Driver acquired at2438ms,
probe enumerated/selected at2780ms and trace armed, construction returned, trace
cancelled, close returned and lease released at2797ms in child event time. These
are coarse event-entry timestamps; equal milliseconds do not prove zero latency.
Construction returned before the1s trace delay, so an empty stack is expected.

Postcheck confirmed all8 critical file pins, the native HID binding and all347
SDK Python hashes unchanged, source still clean at the recorded HEAD, no default
YAML appeared, and the actual shared registry is a closed released record for
the matching new lease. No extra owner/health/device query or forced cleanup was
performed. The immutable9-file attempt snapshot plus released-registry bytes
and their hashes are in terminal-evidence-01/manifest.json; Primary's full audit
is attempt-audit.json. Parent stdout equals attempt.json. Current invocation/
readiness records are TERMINAL_SUCCESS_AUTHORITY_CONSUMED, not READY.

## Interpretation and remaining boundary

This one execution did not reproduce the previous20s constructor stall. It is
evidence of the reviewed constructor path returning and process/ownership cleanup
completing with isolated0.46.0 on the original user-confirmed setup. It is not a
controlled causal A/B experiment and does not establish that every original
connection/flash defect is fixed. SDK temporary-open error suppression and the
inert unopened Session.close remain documented limitations; empty stderr and
the declared forbiddenCalls=[] field are not instrumentation of every SDK/native
operation or independent USB-close proof.

Session.open was outside this entry. The frequency=100000 option was passed but
no actual SWD clock is established. Board firmware/CPU state remains UNKNOWN;
there was no flash/readback/reset/halt/resume/register/memory operation, recovery,
runtime replacement, package/release or remote action. No new test run was needed
for this outcome-only documentation; prior offline evidence keeps its original
head/owner. The full ordered goal still needs ordinary connection/100kHz flash
and IPSR/reset/HALTED evidence, plus the retained ABI/CCM engineering disposition.
Any further physical step needs its own reviewed card, fresh finite authority
and current readiness/identity/ownership preflight; this single grant is consumed.
