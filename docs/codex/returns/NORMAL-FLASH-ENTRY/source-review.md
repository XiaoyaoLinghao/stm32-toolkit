# Normal connection and100kHz managed flash: source review

Primary analysis at accepted base65e5b637069342b2472fad50fcf771801e7337c8;
product/test head694e1e912adfc017c31b52630a323bd733567688 unchanged. No hardware,
worker/lease/health call, runtime installation or product/test edit occurred.
Independent public and SDK source verdicts are recorded in the implementation
report. The old constructor PASS did not exercise Session.open or programming.

| Stage | Actual entry / effects / failure boundary |
| --- | --- |
| Public CLI |python -B -m stm32_toolkit.cli flash; cli.main parses, then hardware dispatch creates FlashWorkflowRequest. No package __main__.py entry. --frequency100000, --authorized and exact pins; recovery flag omitted=false. Parser-only observation does not authorize or execute the command. |
| Workflow admission |hardware_workflows._prepare validates roots/model/debug/probe/build/ELF, then flash_workflow requires authorized is True and validates frequency before _one_shot creates session/supervisor. Production worker config, no private test seams. |
| Ownership/start |Supervisor spawns the owned SDK worker and starts service; actual shared guard/lease and endpoint identity gate client access. Startup/preflight/cleanup may run before any target connection; no substitute registry or manual stale lease deletion. |
| Normal connection |flash_firmware calls client.attach once in the same CLI invocation. MODIFY open_attach requests connect_mode=halt,dap_protocol=swd,frequency100000,auto_unlock=false,no_config=true,user_script=nul,resume_on_disconnect=false; calls Session.open, verifies target identity and HALTED. It is not observe-preserve or the constructor-only helper. |
| Toolkit pre-program preparation |Backend flash_elf checks programming policy and gets driver, then _prepare_for_programming calls reset_and_halt(Target.ResetType.SYSRESETREQ) once for normal; _require_programming_halt requires state=halted. Reset failure=>pre-program-reset; state unavailable/non-halted=>pre-program-halt. No programmer/readback/success receipt after these failures. Under-reset is outside this card. |
| SDK reset behavior |CortexM.reset_and_halt arms reset catch, resets, polls and clears catch; halt timeout can log a warning, so returned call alone is insufficient. SYSRESETREQ performs DP/core accessibility recovery; dap.post_reset_recovery can auto-reconnect DP within its configured polling interval. This is intrinsic SDK behavior requiring disclosure, not an agent-authorized second workflow. |
| Programming |Default driver creates FileProgrammer with sector,trust_crc=false,keep_unwritten=true,progress=None and programs accepted in-memory ELF. SDK loader builds/erases/programs relevant regions; flash algorithm is loaded to RAM and uses CPU registers/halt/resume to execute subroutines. Flash.init(reset=False) normally halts; its reset branch exists. No promise that a full flash involves only one physical reset or no SDK controls. |
| Readback/receipt |After programmer success, Toolkit independently reads two admitted flash ranges and compares61516bytes. Fresh identity is checked again before atomic flash-result.json write. Receipt occurs before workflow cleanup. postFlash reports targetState=unknown,runVerified=false; no application run is verified. |
| Attach failure cleanup |Partial normal attach can resume candidate and verify running before close. Entered5s deadline gets1s terminal wait; late MODIFY success also resumes/state-checks/closes and still fails. Otherwise owned worker abort terminate/join1s, then kill/join1s if needed. These internal cleanup effects must be in future authority. |
| Program/readback failure cleanup |The workflow closes client, then service/supervisor/owned worker and lease. Preparation failure has no attach-restoration resume branch; normal close uses resume_on_disconnect=false. SDK algorithm uninit/disconnect may perform debug operations; neither failure stop nor lease release proves physical rollback, CPU state or independent USB close. Unresolved child/cleanup forbids subsequent hardware, even if registry says released. |

Budget scopes:5s attach success deadline; SDK per-HID-read10s; program30s;
two separate readbacks each30s; worker startup10s, ordinary RPC30s, flash RPC300s,
close5s. The service program deadline remains30s and can abort that longer RPC;
HTTP envelope305s. Existing cleanup adds its own waits and may await owned tasks;
no uniform5/8/20/22/180s CLI wall-time promise. Future180s observation cutoff
means retain unfinished/UNKNOWN/lease/handle evidence and stop later hardware,
not force-kill or assert programming stopped. Actual future scope/budget must be
explicitly authorized after review; no deadline is enlarged to make a test pass.

## Candidate blocking evidence gap

hardware_workflows.py:_one_shot cleanup.failed starts details={} and preserves
controlledSnapshot or attachDiagnostic, not ordinary flash programDiagnostic.
The current path therefore appears to hide the initiating programming error if
client/service cleanup also fails. Existing ordinary non-flash tests deliberately
expect empty details for sanitization, so copying arbitrary result.details would
be unsafe and outside a minimal fix. A closed flash-specific diagnostic/cleanup
projection, if required, needs a bounded Claude implementation and regression.
Independent review must confirm this gap against the source before acceptance.

Firmware observation is a pure file-admission and parser check: buildId
8d3368750cce364ad38e9ed0a6c0f6d6067779c52bc5d8e3a95115ee0ef4abcc;
ELF SHA256b8d5f2c15963552f732ba5650c3150b9471a0d532f3d8c4712748e66fd06bf53,
file1046128bytes; segments0x08000000/61368 and0x0800efb8/148, total61516bytes.
The input snapshot baseline has null Git fields with explicit unavailable-Git
evidence; do not invent clean Git provenance. Model/identity/build/ELF/old flash
receipt hashes were unchanged by this observation. No rebuild or board operation.

Before future hardware archive the old flash-result bytes; attach failure can
leave that old receipt in place, and cleanup failure can coexist with a newly
written receipt. Success requires the fresh matching session/build/ELF receipt,
final public ok=true, full readback and reconciled ownership/worker cleanup.
flashOptions and last progress stage are policy/entry evidence, not proof of
physical execution or exact timing. No error triggers re-enumeration, retry,
under-reset, reset/run or firmware rebuild as an automatic fallback.
