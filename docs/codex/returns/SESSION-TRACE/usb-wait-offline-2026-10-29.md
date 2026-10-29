# SESSION-TRACE: offline USB wait branches and enumeration defaults

Primary source review on2026-10-29, source HEAD before this report commit
`79924428af0f8ae03392be0f49d5c00f17617b69`, code/test head
`e8c43322efa454ac5ddc782572c073e566b432fd`. No hardware, backend import,
enumeration, package/config modification or product/test edit occurred. Fresh
hardware authorization and current power/exclusivity/change confirmation are
still absent. This is source evidence and interpretation preparation, not an
identified physical root cause or a timeout-policy fix.

Sources are the existing pinned pyocd0.45.1 Python files under
D:/codex-tmp/kx23/venv/Lib/site-packages/pyocd. The344-file source-tree pin is
ac0f8c335028ce12f2f153c38b334ad7eb9ec4b1e4a19c058c9a3e3eb978d89b,
recorded in D:/codex-tmp/st135-hw01/dependency-source-pins.json.

## What the one-shot stack can distinguish

The selected-probe Session constructor calls create_associated_board, then
CMSIS-DAP associated_board_info uses _TemporaryOpen. DAPAccess.open queries
packet count, protocol version, packet size and capabilities, with conditional
firmware/board/target metadata queries. identify caches DAP_Info results;
cmsis_dap_core.py:166–212 implements write then interface.read. These are USB
metadata operations before Session.open sets the SWD clock.

| Candidate frame/branch | Static behavior | Interpretation limit |
| --- | --- | --- |
| interface/interface.py:25–26 | Default USB timeout is10s/10000ms | Not a universal bound on every native backend call |
| pyusb_v2_backend.py:175–177,243 | Receive endpoint uses10000ms; caller waits up to10s for its response queue | The original selected backend and the actual missing response remain unknown |
| pywinusb_backend.py:31,83–107 | Exclusive-open contention can use a60s retry loop; read has a10s loop | Does not prove another process owns this physical probe |
| hidapi_backend.py:321–324 | Windows calls device.read(packet_size) directly without an explicit timeout argument here | Cannot infer a10s bound or the binding's native behavior from this wrapper alone |
| pyusb_v2_backend.py:270–283 | Metadata close can wait on its receive thread join | A constructor stack may be in temporary-close cleanup, not a DAP_Info read |

The historical Toolkit operation's service budget was5s and its last received
session-create marker was near3.688s. A dependency10s timeout can therefore
outlast that outer budget if this path is selected. This is a candidate reason
the outer service error might preempt a useful underlying USB error; it neither
proves the original device waited10s nor authorizes raising product deadlines.
No frequency or backend switch follows from it. The approved one-shot diagnostic
still has the same20s parent budget plus up to2s cooperative join, no retry or
force kill; a native call can survive it and keep UNKNOWN/its child-owned lease.

Use only the captured correlated stack/events/result after that separately
authorized operation to classify the actual branch. Missing stack, a fast
constructor, or a subsequent class-only error is incomplete evidence, not a
root-cause fix or permission to reconnect. Do not force v1/v2 or alter
PYOCD_USB_BACKEND to make a hypothesis appear true.

## Enumeration's options-only Session is a separate configuration boundary

pydapaccess/dap_access_cmsis_dap.py:72–94 enumerates existing v1/v2 interfaces
and reads Session.get_current().options['cmsis_dap.prefer_v1']. Session.get_current
at core/session.py:116–136 lazily creates Session(None) if none exists. That
options-only object can use PYOCD_PROJECT_DIR or cwd, load the four default YAML
names, and configure logging before returning early because probe is None.
It does not create another selected-probe hardware session or call Session.open.
The explicit no_config=true/user_script=os.devnull options of the later
selected-probe Session do not retroactively govern that enumeration default.

The fixed production child cwd is C:/work/stm32/fresh-out. Primary checked only
presence, not config contents: pyocd.yaml, pyocd.yml, .pyocd.yaml, .pyocd.yml all
absent; PYOCD_PROJECT_DIR and PYOCD_USB_BACKEND both absent in the process.
Record: D:/codex-tmp/st135-hw01/default-session-boundary.json. No environment
value or user configuration was changed, no unrelated directory followed and
no pyOCD/Toolkit package imported by this check.

Keep those absent inputs as this run's explicit preconditions and recheck them
in the actual launching process before hardware READY. If a config or override
appears, stop offline for reconciliation; do not read/delete it or clear an
override to force the old snapshot. Clarify the card's count as one selected-
probe Session construction, with a possible internal probe=None options object.
This missed prerequisite requires a focused independent supplement review of
the procedure/card before a hardware step; the original entry review remains
retained but is not evidence that it inspected this get_current branch.

The normal1MHz gate remains retired; ordinary source default100kHz is unchanged.
No product deadline, launch/PID/lease rule, operation count or hardware authority
changes in this offline continuation. The full three-item goal is still open.
