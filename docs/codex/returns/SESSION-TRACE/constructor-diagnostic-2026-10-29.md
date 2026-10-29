# SESSION-TRACE: authorized constructor diagnostic

2026-10-29 verdict: **TERMINAL_STOPPED / FAILED_AT_CONSTRUCTOR**. Primary
executed the single newly authorized hardware diagnostic, ending at 19:14:28
Asia/Shanghai. Its authority is consumed. The ordered goal remains on item1;
reset/HALTED efficacy, ordinary flash and release qualification have not passed.

## Ownership, source and authorization

Accepted origin: `bee6118339166e7d57a0e8ed1fc29ddf85242d0c`.
Executed clean HEAD, before this report commit:
`90f9a42cd2b37fd597e02eadc434d408c7e2b7b7`.
Diagnostic code/test head: `e8c43322efa454ac5ddc782572c073e566b432fd`.
Branch: `codex/v135-session-trace-runtime`. Primary owns specification,
orchestration, independent review and acceptance; local Claude Code CLI owns
implementation/tests, using the existing configured route. This run changes no
product/test source or installed package; no remote action was authorized/taken.

Existing42/42 delegated and8/8 independent passes qualify unchanged diagnostic
software, not hardware. The full entry review and focused configuration-boundary
review had NO_BLOCKERS; see [entry review](entry-review-2026-10-29.md) and
[supplement](usb-wait-offline-2026-10-29.md).

The human authorized one original-board/original-probe enumeration and Session
construction,20s plus at most2s cooperative join, existing close after return,
no flash/reset/register reads/retry. They confirmed powered/exclusive/unchanged
equipment. Surviving-child UNKNOWN and its lease were explicitly retained;
force termination and forced lease deletion were not authorized.

## Actual execution

Evidence root: `D:/codex-tmp/st135-hw01`. Immutable file snapshot:
`terminal-evidence-01`, including SHA256 manifest, parent/attempt/claim/READY/GO,
request, native trace and lease record. `attempt-audit.json` retains the
correlation. `authorization.json` and `authorized-preflight.json` bind human
responses and preconditions. Current readiness/invocation/coordinator records
now mark the once-only authority consumed, not READY.

The real CPython3.12.14 executable was
`C:/Users/zhy76/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`,
SHA256 `5640e9be2fd33d05a1a9ae1228e2354609a69ab831605995ec4e2bd6da8fff5e`.
It ran the absolute same-tree `docs/codex/returns/SESSION-TRACE/session_trace.py`
with `-B`, `run`, output `D:/codex-tmp/st135-hw01/attempt-01`, shared data root
`C:/data/stm32-toolkit`, target `stm32f429xg`, project
`C:/work/stm32/fresh-out`, deadline20s, and exact selector
`pyocd:91d67402fe525a5d16bf226f59ab5ecea743eb69292e95719167263ed1fcbf8c`.
Full actual argv is in hardware-invocation.json. Explicit PYTHONPATH used
same-tree Toolkit source and existing read-only
`D:/codex-tmp/kx23/venv/Lib/site-packages` with pyOCD0.45.1.
The344-source dependency tree pin is
`ac0f8c335028ce12f2f153c38b334ad7eb9ec4b1e4a19c058c9a3e3eb978d89b`;
helper SHA256 is
`f607dcd4c0dc8f1dad142df6d774b646abf6714a492361fc5c4604ae19991e32`.

| Observation | Actual evidence |
| --- | --- |
| Parent terminal result | Native exit4; work-timeout;22,016ms |
| Child | PID29940; claim/READY/GO match interpreter/source/request |
| Cooperative termination | One request; unsuccessful join; alive at parent exit |
| Completion | No result.json/events.json at snapshot; child exit null |
| Native trace | One-second timer fired;2,770bytes; stderr empty |
| Cleanup/target | Lease release unconfirmed; handleReleased=false; UNKNOWN |

Attempt `attempt-f07662bda635ca0558002a74561219ba` has request digest
`a570c41ff5fc24ebb0497be2b44a2db7bf55d1e3d0c8081558cde638ad5baf84`.
The active lease snapshot belongs to session
`session-b956d8465ff2c196d99ed85080379d58`, lease
`lease-91cc7056d8a4415791db3fbb9c5cd947`, PID29940,
processStartId `filetime-134377460461777774`.
Registry path:
`C:/data/stm32-toolkit/probe-registry/5157ce5dfaee369c1a49c1acf7a2a58fbcb44be85b5f67d1989e8105290bbe3d.lock`.
An active file alone does not prove current liveness. A later read-only exact-PID
check at19:40:45 Asia/Shanghai found it still running with the exact recorded
creation FILETIME and image path; see owned-process-identity-read.json. This
does not authorize termination or substitute for revalidation on one held
process handle before any future cleanup. No kill, lease deletion or device
access followed. Preserve its source/dependency bytes; future implementation
uses another clean tree.

The first coordinator preflight failed before helper startup: identical344-file
membership/bytes had case-sensitive versus WindowsPath sort order. Original
script/failure remain. Only the comparison was corrected to exact membership,
count, every byte hash and original-order aggregate pin; successful preflight
then preceded the sole hardware invocation. No override/config was cleared.
The four default YAMLs and two environment inputs were absent as required.

Post-run project SHA256 stayed
`65e5cda589bcb732866e46629153c18717c9845ad9a25e2d32d0f941c521561c`;
`build/arm-debug/LWIP.elf` stayed1,046,128bytes, SHA256
`b8d5f2c15963552f732ba5650c3150b9471a0d532f3d8c4712748e66fd06bf53`.
These filesystem checks do not establish board firmware/state.

## Localized defect and limits

The main-thread one-second native stack in the pinned SDK is:

```text
Session.__init__:253 -> create_associated_board:255
 -> associated_board_info:222 -> _TemporaryOpen.__enter__:65
 -> DAPAccess.open:767 -> identify(MAX_PACKET_COUNT):901
 -> dap_info:185 -> hidapi_backend.read:324 -> device.read(packet_size)
```

MAX_PACKET_COUNT is DAP_Info ID0xfe. The Windows0.45.1 read supplies no explicit
timeout. The sampled waiting location and the dependency defect permitting an
unbounded read are now identified. This does not establish that the same frame
persisted for all22s, or why this probe did not return that response.

This precedes Session.open/SWD clock configuration. The100kHz option is not an
observed configured clock; this run does not test frequency, reset preparation,
HALTED or IPSR=3. The reviewed helper never calls Session.open/target-control/
programming APIs. Missing child result does not prove successful Session/USB
close or target state. Parent armed=false/cancelled=false are fallback trace
fields without child completion; the actual dump proves the timer fired.

## Upstream repair and next bounded slice

Official [issue2009](https://github.com/pyocd/pyOCD/issues/2009) describes Windows
first-connection hanging. The [merged repair2011](https://github.com/pyocd/pyOCD/pull/2011/files)
adds a Windows HID read timeout and rejects empty responses. The
[0.46.0 release](https://github.com/pyocd/pyOCD/releases/tag/v0.46.0), published
2026-10-19, includes it; the [tagged source](https://raw.githubusercontent.com/pyocd/pyOCD/v0.46.0/pyocd/probe/pydapaccess/interface/hidapi_backend.py)
contains the change. This matches the captured software defect; an upgrade has
not demonstrated probe responsiveness or successful ordinary flash. Do not
automatically increase outer deadlines, force another backend, skip queries or
patch the installed SDK.

Official [PyPI metadata](https://pypi.org/pypi/pyocd/0.46.0/json) records Python
>=3.9.0, wheel pyocd-0.46.0-py3-none-any.whl,14,809,569bytes, SHA256
`f37c1ef65a1e78b42c9bccf4f34fbde98c4ea225e87534ee872e324aae230ba5`.
Requires-Dist lists equal0.45.1; metadata-only review found all17 applicable
requirements satisfied by existing borrowed versions without importing
pyOCD/HID/USB; see dependency-metadata-review.json. This is not API/native behavior
qualification. Only metadata was fetched; no wheel/install occurred.

The next dependency slice must reconcile pyproject, release-policy direct and
resolved pins/trusted hash, setup admission (currently rejects0.46.0), handoff
profile, two relevant skills and affected tests. Keep historical0.45.1 reference
qualification/admission fixtures truthful; obtain fresh API-only evidence for
the new version. Review the disabled-debug-sequence workaround against the new
SDK before changing it. No new SDK feature, frequency, timeout, recovery or
hardware authority follows from a version change.

Any proposed process cleanup must bind one handle to PID, exact creation FILETIME
and image plus attempt/lease identity; stop on mismatch/refusal; terminate only
that owned child with a finite wait. No lease deletion, target operation or
safe-state claim. New explicit authority is required because the executed card
forbids force cleanup. Preparing an isolated0.46.0 package layer also requires
new authority under the retained no-install boundary. Existing installed1.3.4
and the borrowed environment remain untouched.

Item1 remains open. Item2 needs separately authorized normal100kHz hardware
evidence after connection is available. Item3 keeps ABI unverified and the
observed256B CCM margin pending engineering disposition; original ARMCC binary
evidence is unavailable. No install, packaging, push or release occurred.
