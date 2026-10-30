# pyOCD 0.46.0 connection, timeout and exit source review

Primary source review,2026-10-30. Accepted base
`22f047189fbb0cf1fa7de98e86a2955eb13c5ac1`; product/test head remains
`694e1e912adfc017c31b52630a323bd733567688`. This document is analysis, not a new
hardware result. Independent entry review and fresh selected test evidence are
recorded separately in [the final report](implementation-report.md).

The selected dependency is the already prepared official0.46.0 wheel at
D:/codex-tmp/st135-pyocd046/candidate-site. All347 Python sources again match the
verified wheel SHA256
f37c1ef65a1e78b42c9bccf4f34fbde98c4ea225e87534ee872e324aae230ba5.
Exact read-only excerpts and source SHA256s are in
D:/codex-tmp/st135-p46-entry01/source-packets.json; no SDK module was imported by
source viewing. Published0.45.1 and installed runtime are unchanged.

## Connection and cleanup path

| Source boundary | Observed behavior and interpretation |
| --- | --- |
| Toolkit _DefaultPyOCDDriver:156–193; _select_probe/open_attach:1027–1112 | Lazy import then one aggregator enumeration/exact selection; Session(auto_open=False) construction precedes explicit Session.open. One aggregator call can enumerate several backend/interface families and devices; it is not one OS USB call restricted to the selected device. |
| SDK pydapaccess _get_interfaces:72–94; Session.get_current:122–141 | v1/v2 enumeration reads options; a default Session(None) may be instantiated before the selected-probe Session. Session:206–258 changes cwd and reads default project YAML/logging config. Later no_config=true does not retroactively protect enumeration. |
| SDK Session:216–228; Board:69–121 | cbuild_run is only loaded when explicitly set; this card passes none, and its default-options Session has no YAML input under the required absence precondition. target_override is explicit; no pack path is supplied. New trace/cbuild features are not implicitly selected by the reviewed entry. |
| SDK Session:260–264; cmsis_dap_probe:214–258 | Selected constructor invokes associated_board_info, temporarily opens USB and requests metadata. This is hardware access despite auto_open=False. |
| SDK dap_access_cmsis_dap:746–814,890–903; cmsis_dap_core:166–208 | Opening the link queries MAX_PACKET_COUNT, version, size/capabilities and conditional information. DAP_Info writes then reads. Interface.open/write/enumerate/close and the whole sequence are not bounded by the HID read timeout alone. |
| SDK hidapi_backend:218–245,269–328; interface:25–26 | Windows uses direct HID read(packet_size,timeout_ms=10000); empty data raises DAPAccessIntf.DeviceError. There is no Windows RX thread to join here. The finite argument is tested with a fake device, not a measured native timing guarantee. |
| SDK _TemporaryOpen:61–85; DAPAccess.open:752–814 | Temporary open may suppress a DAPAccess error. If underlying interface open succeeded but an identify read fails before link.open returns, _did_open_link remains false and _is_open is not yet set; exit need not close that partial interface. This is a static possible branch, not proof it occurred on the original probe. |
| SDK Session:182,664–739 | Unopened Session starts _closed=true and close may be inert. Session.open opens the probe, sets SWD clock and initializes the board/target; it is forbidden in the constructor-only diagnostic. Session.close can log/suppress SDK close errors after an opened session; lack of a raised exception alone is not independent native cleanup proof. |
| Toolkit helper:1739–1790,1952–2117 | GO-gated driver/select/constructor; one delayed native trace; constructor-return flag then one existing Session.close call; lease/health/result cleanup. Internal SDK suppression is not promoted into helper construction errors. Treat ok as narrow helper completion, never healthy USB/connected CPU proof. |

The current raw helper SHA256 is
8a883179a44646d128dd231e6777e88a4486b408f5163deda5ed0cfa06687b1d.
It differs from the historical other-worktree raw hash because checkout line
endings differ; the Git blob is unchanged. The new card must use these actual
bytes, not copy the old sourceDigest. The previous complete helper/ownership
review and software tests remain at their original source and evidence owners;
new SDK source paths and these changed interpretation limits receive fresh review.

## Budget disposition

| Budget | Scope and retained decision |
| --- | --- |
| Client attach_timeout_ms=5000, client:268,387–391 | Default request deadline remains5s. Flash attaches before programming; its30s programming/readback option does not override this attach value. |
| Service:970–997,1404–1495 | OBSERVE lifecycle queue consumes the same request deadline. Queue timeout cancels without dispatch. Entered attach waits shielded until deadline, then grants one1s terminal wait and preserves timeout/cancellation as primary. A still-running production worker uses existing owned abort. |
| Service:1550–1668 | Late MODIFY success is not accepted: existing cleanup resumes, checks running, then closes, before reporting timeout. This can control the target and has its own RPC waits; future normal-flash card must explicitly disclose it. Late OBSERVE success closes without that MODIFY resume. |
| Worker:604–768,832–838 | Ordinary RPC default30s; normal close5s; abort terminate/join1s then kill/join1s if alive. These are process containment, not target recovery, and are distinct from helper cooperative-only exit. Native process operations and service awaits do not justify a universal5s/8s CLI-return bound. |
| Client:278–285 | aiohttp total305s is a generic outer transport envelope, not5s+cleanup, not a new hardware budget or reason to wait for305s in a diagnostic. |
| SDK interface:25–26; hidapi_backend:321–328 |10s per Windows read; not constructor/Session.open/service success deadline, not an extension of request5s. A service timeout may preempt the SDK's eventual empty-read exception. |
| Helper:1031,1267–1312,822–869 | One20s parent deadline covers startup/GO/work/result/exit plus at most2s cooperative wait. It does not use ProbeClient/Service.attach and need not fit5s. Two reads could exhaust20s, and a native call/child can survive. No forced termination is granted by this card. |

Decision: preserve existing5s/10s public/library settings and20s+2s diagnostic
scope. Distinguish a deadline for accepting success from time spent settling
ownership. Do not enlarge a deadline simply to obtain a passing result. No
product/test source change is required for this documentary preparation.
If later evidence supports changing latency or aggregate production cleanup,
that is a separately bounded product design/Claude implementation task.

## Next evidence and stop boundary

The [execution card](../../../testing/cards/2026-10-30-pyocd046-constructor.md)
proposes only one constructor diagnostic, subject to fresh authority/ownership.
Even a clean constructor exit cannot qualify Session.open, ordinary100kHz flash,
SYSRESETREQ/HALTED, IPSR=3, readback or board firmware. Suppressed errors or an
ambiguous trace remain inconclusive; no automatic retry or follow-on flash.
Ordinary production connection/flash needs its own source/runtime/action card,
including the existing late-MODIFY cleanup side effects and a distinct finite
operation budget. No packaging or installed-runtime replacement is needed to
complete this offline review.
