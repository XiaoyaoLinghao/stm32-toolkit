# Serial acceptance: P2 attempt 01

Status: **TERMINAL_STOPPED**. No T9, T10 or VS10-A physical acceptance is claimed.

The user authorized starting serial acceptance. One normal P2 Target prepare/execute ran through the deployed candidate `5f036363383e6c85cc87426da1b4a1c20dfe7acc`, using fresh session `vs10a-t9t10-p2-20260911-01`, case `d4-heartbeat`, and the newly prepared action digest. No retry or under-reset fallback was performed. All subsequent hardware stages stopped on failure.

Prepare exited 0. Execute exited 2 with `TEST_EXECUTION_FAILED` and no details. The actual flash receipt from this session records success and 54,896 verified bytes, matching P2 build `77d787ee83f744831316f9531b825935ef276520472221a8174f7a7d4cfe57f9` and ELF SHA256 `10df523425dbe8567d5876e5e790714d1314a5dd3d545e4d43a063c300fd6ead`. The full build identity is authoritative in the retained receipt. Probe connection and flash/readback succeeded; there is no published TestRun or retained raw Target stream. The precise post-flash failure is not established by the public error alone.

The user subsequently asked whether D4 was constantly lit. This is a field-observation clue, not an independently captured GPIO/core-state measurement. A steady LED would differ from the expected P2 heartbeat; neither successful flash nor the LED state proves normal execution or a specific halt/reset fault.

Cleanup evidence records the lease as released and zero matching runtime processes. P2 source/ELF, -12 100ms continuous no-halt physical PASS and attempt 7 historical PASS hashes remain preserved. The prior canonical flash receipt was copied before execution; the canonical receipt now represents this new successful flash and must not be mixed with old sessions.

All current evidence is retained under `D:\codex-tmp\t9t10-p2-20260911-01`: `result.json`, prepare/execute responses, `flash-result.json`, prior flash receipt, prepared binding, consumed marker, released lease, session file inventory and preserved hashes. The empty run-owned temporary directory was removed. No hardware command was issued after the terminal failure. Root cause and any repair require offline analysis first; a hardware retry requires new explicit authority.
