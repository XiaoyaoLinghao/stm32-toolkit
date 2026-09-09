# STM32TK-1001 flash probe identity compatibility design

Accepted base: `a69c5e0a794ba6dab71bb316182abb0ec165611a`

Owners: GPT-5.6-sol specifies and independently accepts; one GPT-5.6-luna/max agent implements product code and tests.

## Scenarios

1. A generic `stm32_flash` record containing the public probe selector binds and passes one subsequent debug read/revalidation seam for that selector.
2. A Physical Target record containing the exact SHA-256 of that public selector binds and passes the same read/revalidation seam.
3. A different selector, a digest belonging to another selector, an arbitrary identifier, or another workspace is rejected before attach/read.

## Contract

Every `_validate_flash` caller supplies the public probe selector. The shared validator accepts `flash-result.json:/probeId` only when it equals that selector or `SHA256(selector)` in lowercase hexadecimal. This is a closed compatibility set for the two existing producers. All workspace, session, build, ELF, target, Git, snapshot, timestamp, telemetry and error checks retain their current strict behavior.

Product ownership is limited to `probe/handoff.py`, which owns the shared comparison, and `debug/firmware.py`, which removes the a69 consumer-side pre-hash. `debug/read.py`, `debug/fault.py`, producers and public schemas remain unchanged because they already pass or produce one of the two defined forms.

## Non-goals

- Do not migrate, edit, regenerate or weaken old workspace evidence.
- Do not choose one existing producer form as invalid or add arbitrary identifier compatibility.
- Do not package, deploy, replace a runtime, touch hardware, or perform remote operations.
- Do not alter historical attempt 7/OBSERVE evidence or claim pending observation, Task 9, Task 10 or VS10-A gates complete.
