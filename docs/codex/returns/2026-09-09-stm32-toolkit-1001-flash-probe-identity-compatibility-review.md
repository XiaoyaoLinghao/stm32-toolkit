# STM32TK-1001 flash probe identity compatibility review

Verdict: `ACCEPTED`

Accepted base: `a69c5e0a794ba6dab71bb316182abb0ec165611a`

Reviewed CodeHead: `d1fc72d0d30cfd6c1e6ba1ef720c1d54a95576f8`

The complete base-to-CodeHead diff is limited to the frozen specification and plan, the shared two-form probe comparison in `probe/handoff.py`, removal of the initial-binding pre-hash in `debug/firmware.py`, and focused firmware/read tests. Every caller now supplies the public selector; the validator accepts only that selector or its exact lowercase SHA-256. Workspace and all other flash provenance fields remain literal and strict.

Implementation verification recorded the expected RED for a generic raw-selector record, then `8 passed` focused, `194 passed` for complete firmware/read tests, and `165 passed` for complete fault/handoff tests. Independent review inspected every changed line and ran the eight focused generic-selector, Physical-Target-hash, read/revalidation, wrong-selector, other-selector-hash, arbitrary-identity and old-workspace cases: `8 passed in 12.03s`. Rejection cases retain zero attach/read behavior.

No packaging, deployment, runtime replacement, evidence mutation, hardware or remote operation was performed. Runtime remains c177. Historical attempt 7 remains PASS; the migrated old-workspace record remains rejected; the three observations, Task 9, Task 10 and VS10-A remain incomplete.
