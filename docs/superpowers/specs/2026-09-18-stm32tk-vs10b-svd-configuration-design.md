# VS10-B SVD configuration correction

Status: approved by the user's “开始进行修复”, referring to the reviewed minimal proposal. This is an offline configuration repair, not authority for a new hardware attempt.
Firmware accepted base: `822d75758f5a705fd9ef1093f3bf9d8101191570`.
Toolkit documentation baseline: `ad63f2424f8dc0333f1f5e9a6d12117b1faf0408`; deployed code remains `12df4fe0569104d6f0e7a827496341d999e1f3ea`.

Runnable scenarios:
1. The current B project loads its unchanged full STM32F429 SVD through existing installed `select_svd`; all1536 register intervals fit the explicit trusted regions.
2. The fault application remains byte-identical, while a fresh Debug build and input snapshot bind the corrected manifest. A later one-statement D3 fix prediction is recomputed from these current bytes but not applied or authorized.

Only implementation file: `D:\codex-tmp\v10b-0918\p\b\.stm32-project.json`, JSON field `debug.readableRegions`. Replace its GPIOE_ODR-only entry with the exact12 ranges in `evidence/closed-loop-03/svd-existing-ranges-proposal-validated.stdout.json`; preserve every other JSON value and all other tracked files. The full vendor SVD SHA remains `2b7de1e383ee415f45339b776942fe01f7b48215316629c3cc280e12661c2400`.

Contract: full SVD containment remains enforced; the range declaration is read-only authority, not a request to read every register. Future Monitor Watch scope stays testtime + GPIOE.ODR. No parser, error-code, firmware logic, tests, source-intent schema, runtime, package, IDE or existing evidence changes. No target access, attempt creation, new Target action, source authorization or old receipt/digest/marker reuse.

Primary owns design/integration/acceptance and cleanup; existing Luna/max firmware agent owns the manifest and offline build; existing host reviewer independently reviews the full822d757→candidate diff in a clean detached project worktree. No remote actions authorized.
