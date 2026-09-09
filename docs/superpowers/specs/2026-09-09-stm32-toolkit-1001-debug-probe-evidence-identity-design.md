# STM32TK-1001 debug probe evidence identity design

Accepted base: `c1777b6be911e26b942c1b127baa799f503d071d`

Owner: GPT-5.6-sol specification and acceptance; GPT-5.6-luna/max implementation and implementation tests.

## Scenarios

1. A production flash result stores `probeId = SHA256(public probe selector)`. A debug binding request for the same public selector and workspace accepts that evidence and may proceed to attach.
2. A flash result for another probe remains `DEBUG_FLASH_MISMATCH`, and rejection occurs before `client.attach`.
3. A flash result bound to another workspace remains `DEBUG_FLASH_MISMATCH`, and rejection occurs before `client.attach`.

## Contract

The flash producer already defines `evidenceProbeId` as the lowercase SHA-256 digest of the public probe selector and writes it to `flash-result.json:/probeId`. The debug binding consumer must derive that same evidence identifier before calling the existing strict flash validator. The validator's literal comparison, workspace check, session check, firmware identity checks, and public error semantics remain unchanged.

Only `debug/firmware.py` owns the conversion at the failing consumer boundary. Use the standard-library SHA-256 implementation already used by the producer. Do not add a public helper or change probe enumeration/public descriptor shapes.

## Non-goals

- Do not rebind, rewrite, migrate, or regenerate old flash evidence.
- Do not weaken workspace identity or accept an arbitrary probe identifier.
- Do not deploy, package, enumerate hardware, attach, reset, flash, sample, or change remote state.
- Do not change historical attempt 7 or OBSERVE evidence, or claim the pending observation/Task 9/Task 10/VS10-A gates complete.
