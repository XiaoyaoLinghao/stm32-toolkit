# ATTACH-PROGRESS — offline Session localization and frequency rationale

Date: 2026-10-29. Owner: Primary Codex. Result:
**OFFLINE_LOCALIZATION_ADVANCED_PHYSICAL_CAUSE_UNRESOLVED**.

Source/report HEAD before this report:
`75e18b7a1f9a8c04eb07d53a7dc7438d540d0d68`; accepted base
`e4d9118e1c83f139db2959acbd4076a357c37992`; product/test CodeHead remains
`e8d7e16436dc7130ec70b6fea0efdc8650ce791a`, branch
`codex/v135-attach-progress`. Primary read the standard procedure, current
checkpoint and latest hardware report before the diagnostic. No product/test
implementation, hardware access, installation or remote action occurred.

## What the new trace establishes

The [single hardware attempt](hardware-validation-2026-10-29.md) last received
`session-create@3688ms`; neither the next target-resolution entry nor session-open
was received. Its normal attach budget remained 5 seconds, followed by the existing
1-second terminal wait. At that receipt time, the remaining nominal attach budget
was only approximately 1.31 seconds. Parent receipt timing is approximate; missing
markers cannot prove that subsequent target actions never occurred.

Offline inspection of the actual existing pyOCD 0.45.1 environment at
`D:/codex-tmp/kx23/venv/Lib/site-packages/pyocd` gives a more specific candidate:

1. `core/session.py:169,253`: the Session constructor imports Board and invokes
   `probe.create_associated_board()` before returning.
2. `probe/cmsis_dap_probe.py:217-254`: CMSIS-DAP associated-board resolution enters
   `_TemporaryOpen(self._link)` to inspect protocol/board/target information.
3. The same file at lines 61-80 temporarily opens/closes that USB link. In
   `probe/pydapaccess/dap_access_cmsis_dap.py:746-817`, opening can open the USB
   interface and perform packet-count, protocol-version, packet-size and capability
   queries; supported versions can add firmware/board/target-name queries.
4. `core/session.py:658-660` opens the probe and calls
   `set_clock(options['frequency'])` only inside the later `Session.open()`.

Thus `auto_open=False` does not mean that Session construction performs no USB
I/O. USB opening/information exchange is a priority candidate within the observed
construction boundary. No call stack or inner timestamps establish which of these
operations actually stalled. Actual HID/bulk transport and probe firmware version
were not captured; no USB/backend/board defect is asserted.

The configured 1 MHz value has not been shown to reach the set-clock operation in
this failed attempt. Changing that option does not directly change the earlier
USB information exchange in the inspected implementation. It therefore cannot yet
be accepted as a fix for this particular timeout.

## One pure-import diagnostic

Primary ran one fresh Python process with the existing interpreter and explicit
candidate source path. The run-local script only imports the backend, constructs
its default driver import wrapper, then imports Board. It never enumerates probes,
constructs Session, opens USB or accesses a target. Main is guarded and `-B` avoids
writing bytecode into the borrowed environment. Actual command:

```text
D:/codex-tmp/kx23/venv/Scripts/python.exe -B -X utf8 D:/codex-tmp/ap135-offline-20261029/cold_import_diagnostic.py
```

Exit 0. Backend import: 0.812474 s; default driver import: 0.577104 s. Board was
already loaded after driver import; explicit Board import took about 0.000006 s.
Six inspected dependency source hashes are retained with the result. This is one
fresh-process sample with existing OS caches, not a cold-machine benchmark,
hardware reproduction, test-suite PASS or explanation of the observed 2.983 s
driver receipt gap. It does not support assuming that Board's initial module import
was deferred to the observed Session-construction stall in this environment.

Evidence root: `D:/codex-tmp/ap135-offline-20261029`.

| Artifact | SHA-256 |
| --- | --- |
| cold-import-result.json | 07819b21d6599e624eaa0780d3072fc7aa32a38d12c2a62dbe70c54594a6effc |
| cold_import_diagnostic.py | 1c9743f14ef03894d6412290dc2c18b81abeedd25b15b849421045db4fa1035c |

## Why 1 MHz was selected

Subsequent [requirements-origin audit](frequency-requirement-origin-2026-10-29.md)
locates the explicit 1 MHz default in the 2026-08-07 implementation plan before
the code below. The original product requirements and overall probe plan did not
mandate it. Matching pyOCD's default does not establish the historical decision's
motivation; that rationale was not recorded in the earliest plan.

The initial backend already supplied `frequency_hz=1_000_000` in commit
`65f1ea637a4f47183c3d40fe36deae51b6f2f012`; worker configuration later retained it
in `58f38a610e0255921eb45bb106cf1677ca01a259`. Current defaults remain in
`probe/pyocd_backend.py:403` and `probe/worker.py:86`.
[pyOCD documents the same 1 MHz default](https://pyocd.io/docs/options.html).
This establishes an inherited product default consistent with the dependency,
not a board-specific minimum, measured capability or user throughput requirement.
The recent physical attempts retained it as the ordinary-path regression condition,
with explicit user authorization of each single attempt.

This frequency is the SWD/JTAG debug communication clock, not the MCU application
clock. The [CMSIS-DAP clock command](https://arm-software.github.io/CMSIS_5/5.8.0/DAP/html/group__DAP__SWJ__Clock.html)
requests a maximum SWCLK/TCK frequency. Toolkit's accepted numeric range and
configuredFrequencyHz report are not measured physical-clock or stable-link proof.

The [STM32F429 family datasheet](https://www.st.com/resource/en/datasheet/stm32f429bi.pdf)
confirms SWD/JTAG support, including STM32F429ZG. It does not qualify this specific
probe/firmware/cable/board combination at 1 MHz. Stable ordinary 1 MHz flashing of
the current combination has not passed our validation; it also has not been shown
to fail because the frequency is unsupported. The prior successful receipt proves
the combined **100 kHz plus under-reset** workflow with 61,516 verified bytes,
not ordinary 100 kHz behavior or a frequency-only cause.

## Assessment of a 100 kHz default

A conservative ordinary CMSIS-DAP default of 100 kHz is a reasonable product choice
when compatibility takes priority over throughput. There is no discovered firmware
correctness requirement to insist on 1 MHz. Preserve an explicit frequency option
and keep frequency independent of normal versus under-reset connection policy.
Changing the default must not silently select recovery or add control operations.

The main cost is slower SWD-bound transfers, especially RAM algorithm upload and
complete readback. Dividing the wire rate by ten does not make the entire flash
workflow exactly ten times slower: USB overhead and target-side erase/program
execution contribute separately. Relevant finite RPC/workflow budgets and large
image performance need proportionate verification; do not automatically extend
deadlines or claim that unchanged values remain sufficient.

100 kHz can be evaluated as a compatibility policy, but it must not hide the
independent construction/USB timeout or be declared its confirmed repair.
Next diagnosis should isolate construction-time USB open/query/close and total
startup-budget consumption. Product changes and implementation tests remain owned
by local Claude Code CLI and require Primary independent review. No default,
deadline or reset policy was changed here. The previous hardware authorization
remains consumed; further physical work requires a separately bounded operation.
