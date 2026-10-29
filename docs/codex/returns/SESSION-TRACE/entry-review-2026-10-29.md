# SESSION-TRACE: conditional constructor entry review

2026-10-29 verdict: **NO_BLOCKERS for the offline procedure/card review**.
Hardware remains **BLOCKED_NOT_EXECUTED**: no current hardware authorization,
power/exclusivity confirmation or physical target-state evidence. This is not
READY, a root-cause fix, ordinary flash acceptance or release qualification.

Primary authored the procedure/card and owns orchestration/acceptance. A fresh
local Claude Code CLI invocation independently reviewed that entry contract,
retaining the existing deepseek-v4.1-flash[1m] route and permissions. Accepted
origin is `bee6118339166e7d57a0e8ed1fc29ddf85242d0c`; reviewed clean source HEAD
before this report commit is `60daa9cc0e38438fa7acf555bdd37f58b644fd08`, code/test
head `e8c43322efa454ac5ddc782572c073e566b432fd`. Only documentation changed after
the42/42 delegated and8/8 Primary offline passes. The software and its retained
abnormal-call/failed-test history are recorded in [the implementation report](implementation-report.md).

The reviewer used only16 exact ordinary source-view commands, after actual
PowerShell-only inventory and harmless smoke. Primary checked every matched
native result, all25 complete source segments and each numbered line, including
the full2225-line helper; no truncation, command/scope deviation, pending result
or retry. Native successful numeric exits remain null; CLI exited0. These are
read-only source checks, not tests. Source-view Python processes really ran;
the reviewed helper, pyOCD/Toolkit backend, lease/health, enumeration and USB
operation did not. No product or test source was edited by this review.

Evidence is D:/codex-tmp/st135-hw01: entry-review-run contains raw native events,
entry-review-verdict.md the full independent findings, entry-review-audit.json
the Primary evidence audit. The original reviewed card SHA256 is
81562ddeb955d361648f287a1bbbb2e8ce0c799077acb58ca4bb2d2c8f870e34;
task SHA256c58cf89a32115c50fbb8b9b8e0b4902d11945a5f5127f68f9febba8f12d216db.
Primary's first audit expected a trailing stdout newline that native PowerShell
strips; that preparation failure is preserved. Only transport newline handling
was corrected, then the already-executed outputs were audited again; no source
view, Claude call, test or hardware action was rerun.

## Review scope and retained limits

The review verifies fixed real-image/PID/source/request/lease identity; actual
argv/parser and original shared data realm; claim/READY/GO and real ownership
gates; one enumeration/selection/constructor without Session.open or target
control; physical-state/frequency limits; finite parent/termination budgets,
surviving-child UNKNOWN/lease and handle rules; trace/success/failure evidence;
and absent authority/readiness gates. In pyOCD0.45.1 the constructor initializes
Session._closed=true, so its returned Session.close call can be inert. It is
not independent evidence of USB/target cleanup or physical state. Temporary
metadata USB open/close is inside the associated-board path, and set_clock is
inside Session.open, which this helper never calls.

Three non-blocking observations are retained, with offline supplements:

1. The reviewed card pinned Session source but not the transport tree. The
   additional read-only dependency-source-pins.json now records344 pyOCD Python
   sources, deterministic path/hash tree SHA256ac0f8c335028ce12f2f153c38b334ad7eb9ec4b1e4a19c058c9a3e3eb978d89b.
   It includes reviewed CMSIS-DAP source SHA256a5f66a61e16195b39d181c9e91d49d7257874ab31736e0fc5c4dba4b677d76b3
   and pydapaccess SHA256e820b41633782f3bc7abe4b030cc2c50159feb2c0e6605f64168249805325200.
   This is source identity, not behavior proof or a pin of external USB DLLs,
   Windows drivers, probe firmware or physical target identity.
2. sessionOpened=false/forbiddenCalls=[] are schema/code-path declarations,
   not runtime instrumentation of every internal pyOCD call. Absence of explicit
   target-control calls is supported by source review; no physical-state or
   side-effect absence claim follows from those fields alone.
3. Exact version and normal-path option comparison were not shown in the
   independent excerpts. Primary retained runtime-version.json showing the
   pinned real executable's actual3.12.14 version, without backend import.
   Primary also statically read the normal default100000Hz constructor setting
   and open_attach option dict at pyocd_backend.py:403 and1077–1093. With normal
   policy, non-preserve mode, this project cwd and target, the helper's listed
   constructor options match that profile. No open_attach was executed; this
   is a separate Primary source comparison, not extra independent coverage.

These supplements add evidence/limitations, not another reviewed code path or
hardware permission. Current original-project model SHA25665e5cda5...1561c and
ELF SHA256b8d5f2c1...bf53 match the read-only snapshot; local ELF identity still
does not identify the firmware on the board. Shared lease record was released
in that snapshot, not proof of present free guard or ownership. A pure parser
observation validates the exact planned argv without main/run_attempt/child.

## Next authorized boundary

After a new explicit hardware authorization and current original-board/probe
power/exclusivity/change confirmation, update only the card's identities/status,
recheck exact clean source/runtime/helper/dependency/project pins and absent
output, then permit the single proposed USB constructor operation. Do not
operate before those gates. Twenty-second parent budget plus at most2-second
cooperative wait does not promise that a blocked native USB child was killed;
UNKNOWN and its child-owned lease remain if it survives. No flash, reset,
register read, automatic recovery, forced kill or lease deletion belongs to
that proposal. The original physical timeout and remaining goal items stay open.
