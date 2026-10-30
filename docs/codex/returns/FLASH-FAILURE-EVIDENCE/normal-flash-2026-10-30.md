# One ordinary100kHz managed-flash hardware verification

2026-10-30 Asia/Shanghai verdict: **PASS_ONE_NORMAL_100KHZ_MANAGED_FLASH**.
The new single-use authorization is **CONSUMED / TERMINAL_SUCCESS**; no follow-on
hardware is authorized and this record is not READY for replay. No recovery,
runtime replacement, installation, packaging, push or publication occurred.

## Authorization, ownership and frozen entry

The user explicitly requested one ordinary100kHz flash on the original board/probe,
per the reviewed card, failure-stop/no automatic recovery. Current readiness was
confirmed: original STM32F429ZG board powered, original probe connected, external
IDE/debugger detached, exclusive; no board/probe/wiring/power/reflash change.
Primary performed preflight, orchestration, physical execution, evidence review
and reporting. No product/test code changed and no implementation fallback was used.

Executed source HEAD:e8e3c5f8d77490eaa0fae3e8ab8586237f30935c, clean branch
codex/v135-flash-failure-evidence. Product/test CodeHead:
bfa56c21fa67e53649ec0c9c15b5ab4e9b79ae4d. The original reviewed card at execution
is retained separately with its SHA; the run-local authorized card refreshes only
current grant/readiness/identity facts, retaining all operation/stop boundaries.

- Direct CPython3.12.14: C:/Users/zhy76/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe,
  SHA2565640e9be2fd33d05a1a9ae1228e2354609a69ab831605995ec4e2bd6da8fff5e.
- Official isolated pyOCD0.46.0: D:/codex-tmp/st135-pyocd046/candidate-site;
  all347 Python source hashes unchanged. hidapi0.15.0 binding/source identity pinned.
- Project C:/work/stm32/fresh-out; actual shared data root C:/data/stm32-toolkit.
- Probe pyocd:91d67402fe525a5d16bf226f59ab5ecea743eb69292e95719167263ed1fcbf8c;
  debug target stm32f429xg, declared device STM32F429ZGTx.
- Session st135-normal-flash-hw03; workspace
  e3cc8ecd06ccc0e77c31f095c0918bac89cbf5fc72a6ed8db544b3e98719440e.
- BuildId8d3368750cce364ad38e9ed0a6c0f6d6067779c52bc5d8e3a95115ee0ef4abcc;
  ELF build/arm-debug/LWIP.elf,1046128 filebytes,
  SHA256b8d5f2c15963552f732ba5650c3150b9471a0d532f3d8c4712748e66fd06bf53.
- Snapshot09b178c4a285f3033ac35ae9dafbc2431028a0bbbd73de3b9daa89809b0e66d8;
  Git explicitly unavailable/null, not invented clean provenance.

The public module entry was used once: pinned Python -B -m stm32_toolkit.cli flash,
with exact project/data/session/probe/build/ELF pins, --frequency100000,
--authorized and --json; no recovery flag/private fake seam. Exact argv is retained
in authorized-preflight.json and hardware-invocation.json, not reconstructed from
the result. Parent and worker used process-local source/SDK/dependency paths and
unique temp roots; installed runtime was untouched. No extra probe list, attach,
constructor diagnostic, target query or post-flash run was issued.

## Preflight and actual result

Pure current firmware admission/parser checks passed. Source/runtime/SDK/native
HID identities matched; four default override variables absent, four project YAML
names absent at both CLI/worker cwd and firmware project, no supplied-root startup
customization. Session/output was fresh; actual registry was released and left
unchanged for real guard arbitration. Old flash receipt was archived before launch.

One pure preflight initially failed an over-strict assertion: importing Toolkit
backend class definitions was incorrectly forbidden. probe.__init__ imports those
definitions without constructing a backend or loading pyOCD. Source inspection
and corrected preflight confirmed SDK unloaded/no hardware; the original script
and failure are retained. This was before the only CLI spawn, not a hardware retry.

| Evidence | Observed result |
| --- | --- |
| Native public CLI |PID14408, actual exit0, ok=true, operation stm32_flash, code OK |
| Whole invocation |19656ms, below180s observation budget; no coordinator termination |
| Firmware workflow timestamps |2026-10-30T02:47:16.052435Z to02:47:32.124064Z, i.e.10:47:16–10:47:32 Asia/Shanghai; inner16.071629s is not an isolated programming-duration measure |
| Selected options |requested/configured100000Hz, normal, sysresetreq, preProgramHaltRequired=true, automaticRetry=false |
| Readback |verifiedBytes61516; accepted source splits two segments into three RPCs:0x08000000/32768,0x08008000/28600,0x0800efb8/148 |
| Backend programming statistics |bytes/sectors null; physical changed/erased byte counts are not established |
| Fresh receipt |success/OK, same session/workspace/probe/build/ELF, modify/authorized, snapshot baseline preserved |
| Cleanup |CLI observed terminal, public result has no cleanup failure, owned endpoint file absent, new lease released |
| Output |stdout1272bytes, structured JSON parsed; stderr0bytes |
| Post-flash |targetState=unknown, runVerified=false |

The new receipt hash is
fbfbcc0980085a2bfb4c497a1e1f023bc72e21c96e25b91a918bbd0a01d3cc60;
the archived old receipt hash was
db8165a19ee8f8bf0f101f77bd3c4cd822baeae2f8ef349453fa0d07e222a4a0.
They differ, and all receipt result fields match this invocation. The real released
lease is lease-d81537f673194289b4889f07cb89e8f6, different from the prior constructor's
lease; registry hashf1575fc532ad12bcc12482ceed7a82fd4a62d0999bb95c041dbb48b4bc59e51e.
Source/runtime/HID and347 SDK files stayed unchanged; model, firmware identity,
ELF and build receipt (four protected project files) stayed byte-identical.
Only the intended flash receipt/runtime session and ownership lifecycle changed.

## Meaning and limits

This establishes one successful ordinary100kHz managed-flash case on this original
pair with the pinned candidate and existing image. The API succeeded through
normal connection, source-enforced identity/initial HALTED, controlled SYSRESETREQ
and fresh HALTED gate, programmer return and exact readback, followed by existing
cleanup. Configured flashOptions alone are not actuation evidence; this conclusion
uses the completed public path and verified source, matching fresh receipt and
terminal ownership facts jointly. No independent register/state query was added.

Worker cleanup is inferred from that accepted source path and public success plus
released lease/removed endpoint; a separate SDK-worker PID trace/USB health query
was not captured. Lease release alone is not proof. No claim is made that SDK
close had no internal actions, that only one physical reset occurred, or that the
wire frequency was measured. No extra coordinator kill/reset/reconnect/recovery.

The old IPSR=3/connection failure did not recur in this run, but this is not a
controlled root-cause A/B experiment or a universal probe/board guarantee. Backend
statistics are null, so do not claim all image bytes physically changed or sectors
were erased. There is no user-firmware-running, ABI-equivalence or CCM-reserve
acceptance. Physical CPU/application state remains unknown. No1MHz gate is added.

Receipt toolkitVersion still reads1.3.4 because version alignment is outstanding;
executed candidate source and isolated SDK are pinned above. This result does not
qualify the published/installed v1.3.4 runtime or constitute v1.3.5 release acceptance.

Evidence: D:/codex-tmp/st135-normal-flash-hw03 — authorization/preflight/authorized
card, one-shot ledger, raw CLI streams/parsed result, before/after receipt and
registry, native terminal record, hardware-audit.json and immutable terminal-evidence-01.
No endpoint auth-token file was read/copied. All subsequent checks were local
file/metadata reads; the one hardware grant is consumed and no further device
operation is authorized by this report.
