# pyOCD 0.46.0 constructor diagnostic execution card

Status: **BLOCKED_NOT_EXECUTED — OFFLINE PREPARATION ONLY**.
Primary owns this card and acceptance. The user authorized only offline review
and tests on2026-10-30; hardware, runtime replacement and publication are forbidden.
No old hardware grant is reusable. This card authorizes no command below.
Independent review/evidence is recorded in
[PYOCD046-ENTRY](../../codex/returns/PYOCD046-ENTRY/implementation-report.md).
The maintained authority is [standard procedure](../standard-test-procedure.md),
including its0.46.0 budget/interpretation section.

## Source and environment identity

| Item | Actual prepared identity / required launch gate |
| --- | --- |
| Accepted source origin |22f047189fbb0cf1fa7de98e86a2955eb13c5ac1; branch codex/v135-pyocd046-entry-review |
| Product/test CodeHead |694e1e912adfc017c31b52630a323bd733567688; only Primary documentation changes in this review. Freeze actual clean execution HEAD/card SHA in the external review manifest, then recheck before any future launch; no moving HEAD substituted silently. |
| Author checkout/helper |C:/Users/zhy76/.codex/worktrees/v135-pyocd046-hid/STM32-Toolkit/docs/codex/returns/SESSION-TRACE/session_trace.py; raw SHA2568a883179a44646d128dd231e6777e88a4486b408f5163deda5ed0cfa06687b1d. Historical other-checkout LF hash is not this raw identity. |
| Real interpreter |C:/Users/zhy76/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe; actual3.12.14; SHA2565640e9be2fd33d05a1a9ae1228e2354609a69ab831605995ec4e2bd6da8fff5e. No venv redirector or interpreter substitution. |
| SDK |D:/codex-tmp/st135-pyocd046/candidate-site/pyocd,0.46.0;347 Python files match official wheel SHA256f37c1ef65a1e78b42c9bccf4f34fbde98c4ea225e87534ee872e324aae230ba5. Record actual selected distribution/module origins before launch, without enumeration. |
| Other dependencies |Existing read-only D:/codex-tmp/kx23/venv/Lib/site-packages, including hidapi0.15.0. Do not select its old pyocd0.45.1 ahead of candidate-site or write its modules/caches. Native binding identity is in offline-inventory-supplement.json. |
| Child import path |Process-local PYTHONPATH ordered: this checkout/tools/stm32-toolkit/src; candidate-site; existing dependency site. Direct Python for parent/child, -B and PYTHONDONTWRITEBYTECODE=1, PYTHONNOUSERSITE=1; no test bootstrap/private injection, no PYTHONHOME or __PYVENV_LAUNCHER__. Stop on inherited conflicting entry settings rather than silently mutate global configuration. |
| Project/data |C:/work/stm32/fresh-out; C:/data/stm32-toolkit. Original shared registry only; no substitute registry or forced stale-record deletion. |
| Project model |SHA25665e5cda589bcb732866e46629153c18717c9845ad9a25e2d32d0f941c521561c,4693 bytes, observed offline2026-10-30. |
| Local ELF, reference only |C:/work/stm32/fresh-out/build/arm-debug/LWIP.elf; SHA256b8d5f2c15963552f732ba5650c3150b9471a0d532f3d8c4712748e66fd06bf53,1046128 bytes. Not input to this diagnostic; neither board firmware nor running state is established. |
| Exact target / original probe |stm32f429xg / pyocd:91d67402fe525a5d16bf226f59ab5ecea743eb69292e95719167263ed1fcbf8c. Original physical board described as STM32F429ZG. Current presence/identity/power/exclusivity/changes are **UNCONFIRMED**, target state UNKNOWN. |
| New output / temporary root |Proposed D:/codex-tmp/st135-p46-hw02/attempt-01, must not exist before launch. TEMP/TMP/TMPDIR process-local D:/codex-tmp/st135-p46-hw02/tmp. No overwrite/reuse of st135-hw01 evidence. |

Full pins: D:/codex-tmp/st135-p46-entry01/offline-inventory.json and
offline-inventory-supplement.json; frozen reviewed HEAD/card/source packet hashes
are in review-manifest.json. Snapshot facts must be rechecked at the future
authorized entry, not treated as present hardware facts.

## Preconditions before READY

1. New explicit one-shot hardware authority must name this constructor-only
   operation and20s+2s budget; current original board/probe power, exclusive use,
   external IDE/debugger disconnection and changes since the last failure must
   be confirmed. None is inferred from the2026-10-29 confirmation.
2. Recheck clean exact source/helper/runtime/SDK/binding/project pins and absent
   output. Recheck PYOCD_PROJECT_DIR/PYOCD_USB_BACKEND unset and no pyocd.yaml,
   pyocd.yml,.pyocd.yaml,.pyocd.yml in the project, including redirects/dangling
   links. They were absent in the2026-10-30 offline snapshot. Stop if changed;
   do not read/delete configuration or clear an override to force this card.
   No cbuild_run/pack/user-script override is passed; user_script=os.devnull.
3. Old PID29940 termination was confirmed once on2026-10-29T11:49:16Z, exit238.
   This is historical, not a new process lookup. Its active lease file remains
   byte-preserved SHA256132553cbf53af352b1503585190328e60fe976955305d8350db7faf184de7d5f
   in C:/data/stm32-toolkit/probe-registry/5157ce5dfaee369c1a49c1acf7a2a58fbcb44be85b5f67d1989e8105290bbe3d.lock.
   No manual delete/release/reclaim. Only the existing lease manager in a newly
   authorized invocation may apply its real owner/health checks; BUSY/refusal
   stops. A read-only lease snapshot never proves free guard or ownership.
4. Independently reviewed procedure/card and the recorded selected offline
   checks must be accepted. Any changed entry contract receives new review;
   old0.45.1 review is insufficient for new SDK behavior. No unresolved offline
   finding may be relabeled a physical deferment.

## Proposed single operation, not executed

Parent cwd is the author checkout; child cwd is the original project. After the
above gates only, one direct real-Python invocation would use these literal args:

```text
C:/Users/zhy76/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe -B C:/Users/zhy76/.codex/worktrees/v135-pyocd046-hid/STM32-Toolkit/docs/codex/returns/SESSION-TRACE/session_trace.py run --output-dir D:/codex-tmp/st135-p46-hw02/attempt-01 --data-root C:/data/stm32-toolkit --probe pyocd:91d67402fe525a5d16bf226f59ab5ecea743eb69292e95719167263ed1fcbf8c --target stm32f429xg --project-dir C:/work/stm32/fresh-out --deadline-seconds 20
```

Parent owns exactly one direct child. Real OBSERVE lease and claim/READY must
match actual PID, sourceDigest, interpreter, attempt/request/lease and live
deadline before one GO. Before GO no USB. After GO one driver acquisition,
one aggregator enumeration/exact selection, one selected Session construction,
then its existing close. Enumeration may inspect multiple backend interfaces
and create a no-probe default-options Session; it is not restricted to one USB
request or one library Session instance. Selected options match normal100kHz:
auto_unlock=false,connect_mode=halt,dap_protocol=swd,frequency=100000,
no_config=true,pack.debug_sequences.enable=true,primary_core=0,
project_dir=original project,resume_on_disconnect=false,target_override=stm32f429xg,
user_script=os.devnull; Session auto_open=false. Frequency is an option only:
without Session.open no actual SWD clock claim.

Forbidden: Session.open, reset/halt/resume, target register/memory reads,
flash/readback, under-reset, second enumeration/constructor, fallback backend,
automatic recovery/retry, force-kill, registry deletion or installed-runtime
replacement. Source viewer/parser checks are not this physical invocation.

## Budget, success interpretation and failure stop

20s is the original absolute parent work/result/exit deadline, not20s per phase;
one terminate.request permits at most2s cooperative waiting. This helper does
not use service5s attach. SDK10s applies per Windows HID read only, not native
enumeration/open/write/close or the whole constructor; multiple reads may exceed
the parent budget. Native/OS/persistence overhead is not a hard22s wall promise.
No timer is extended and no hardware fallback is scheduled after timeout.

Preserve request/claim/READY/GO/result/events/attempt, child-stderr and one native
faulthandler snapshot after1s (repeat=false,exit=false); cancel on constructor
return. A fast return need not produce a nonempty stack. Overall helper success
needs matched records, child exit0, one constructor/close call and successful
trace/lease/health/terminal-handle cleanup. It establishes only **constructor
completion with process/ownership evidence**. _TemporaryOpen can suppress an
open/identify error and leave partial interface state; unopened Session.close
can return without closing USB. ok/sessionClosed do not qualify USB health,
physical state or normal flash. Suppressed-error indications or ambiguous
trace remain **INCONCLUSIVE for responsiveness**, even if helper exit is0.

On any failure/refusal/timeout/cancellation/identity/persistence/cleanup problem,
preserve initiating and cleanup outcomes and stop all later hardware. If the
child survives or startup is unknown: keep UNKNOWN, lease and live/unknown handle
evidence, no forced cleanup. A terminated child alone is not board-state proof.
No automatic follow-on production connection or flash after either success or
failure; any such step needs a separately reviewed card and fresh authority,
including existing late-MODIFY attach resume/state-check/close effects.
