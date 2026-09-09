# STM32TK-1001 debug probe evidence identity review

Verdict: `ACCEPTED`

Accepted base: `c1777b6be911e26b942c1b127baa799f503d071d`

Implementation CodeHead: `2a6761c55c8d8875ceb01961b15027cf260a7ed7`

Reviewed CodeHead: `388f8b0a209fa0f5d77e1953f4688706cf9d7718`

The complete accepted-base-to-reviewed-head diff is limited to the frozen specification and plan, one consumer conversion in `debug/firmware.py`, and focused `test_debug_firmware.py` coverage. Debug binding now derives the producer-defined SHA-256 evidence probe identifier before the unchanged strict flash validator. Incorrect probe evidence and another workspace still return `DEBUG_FLASH_MISMATCH` before attach.

Implementation verification reported a focused RED (`F..`, matching production evidence rejected), focused GREEN (`4 passed`), and the complete `test_debug_firmware.py` reaching 100% collection progress without failures. Independent review verified the four focused cases: same-probe fixture reaches attach (`1 passed`), genuine production flash evidence is consumed, wrong probe is rejected without attach, and wrong workspace is rejected without attach (`3 passed`). Initial review execution failed during fixture staging because its long D-drive basetemp exceeded the Windows path budget; the same unchanged tests passed with a shorter run-owned D-drive basetemp, so this is classified `ENVIRONMENT`.

No packaging, deployment, runtime replacement, hardware operation, evidence rewrite, or remote action was performed. The old migrated workspace evidence remains intentionally rejected. Historical attempt 7 remains PASS; the three observations, Task 9, Task 10, and VS10-A remain incomplete.
