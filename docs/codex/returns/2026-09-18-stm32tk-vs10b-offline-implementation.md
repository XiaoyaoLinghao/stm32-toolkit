# VS10-B offline implementation — 2026-09-18

Status: **IN_PROGRESS**. This report does not accept VS10-B or authorize deployment, hardware access, or remote mutation.

Accepted base: `16a6e59dff7fed2999fae611e3d936b0b04bbabd`. The primary conversation owns design, integration, independent review and acceptance. `/root/vs10b_host_impl` and `/root/vs10b_firmware_impl` are the two separate Luna/max implementation owners. User approval is “开始实施”; the reviewed specification and plan are under `docs/superpowers/` with date `2026-09-18` and slice name `1002-cubemx-real-board-closed-loop`.

## Reviewed CubeMX creation correction

The original public `create-prepare` failed with `CUBEMX_MCU_DESCRIPTOR_INVALID` before authorization or native generation. The installed official `families.xml` uniquely maps the exact MCU `STM32F429ZGTx` to `STM32F429Z(E-G)Tx.xml`; the accepted-base parser only searched for an exact leaf filename. This is a product discovery defect, not physical board evidence.

Code head `7a6dcfa97b7595a147cfc5a35cf725fa924ba39d` is **ACCEPTED for this bounded correction**. The changed product file is `creation_environment.py`; three existing test files cover the environment, adapter and public workflow. Index fallback occurs only when no exact descriptor exists. It binds the index path/hash to the execution environment, keeps the exact leaf token for CubeMX, and preserves the old exact-descriptor payload and digest. It does not change the installed runtime.

The primary and `/root/vs10a_probe_review` reviewed the full base-to-`83a47a68a0fc238560a76b01f09bc8befa7fabaf` diff. The sole alphabet finding was corrected by the original implementer in `7a6dcfa` and independently checked by the primary. Evidence records 66 original owner checks, 24 affected environment checks after correction, and three primary checks of the public drift guard, exact adapter token and unchanged exact-mode facts; these are separate scopes, not an aggregate test count. Native generation and firmware builds remain to be proven by actual outputs.

The subsequent fresh public apply reached native output validation and failed with `CUBEMX_NATIVE_OUTPUT_INVALID: native MCU identity is missing`. It did not configure, build or activate the destination. The existing failure cleanup removed the generated IOC. The original failure is retained; one new offline generation with a pass-through capture at the existing default-validator seam is permitted solely to preserve the raw generated files before unchanged validation. Until those fields are available, the parser cause and correction are not asserted.

## Host adaptation under correction

Candidate `b4d13852c9ef7f6127021a5bca17187e9124d260` adds B attempt `/4`, recovery policy `/3` and `new-cubemx-physical-repair/1`. Both independent reviews returned **REVISION_REQUIRED**: non-string scenario inputs must retain typed rejection; unknown persisted schemas must be rejected before dispatch; B must exercise the existing full persisted recovery chain rather than only revisions 0–1. The same implementation owner is addressing these findings.

The primary compared the existing A public scenario/policy serializer output to the installed accepted A runtime. The complete output is byte-identical, SHA256 `0cb7a5435d5ea0990225f0c42a033e950231b0bda88c4b8e5ec98bc184e24d5e`. A physical `/2`, continuation `/3`, replay `/1`, historical attempt 7 and VS10-A acceptance remain unchanged.

## Evidence and remaining boundary

Current local ledger: `D:\codex-tmp\v10b-0918\evidence\implementation-ledger.json`. Raw implementation, review, compatibility and original failure evidence is retained below that evidence root. The earlier `preflight-summary.json` is explicitly historical and points to this current ledger.

Actual installed DFP `3.1.1` metadata supports `STM32F429ZGTx`; VS Code `1.129.1` and Cortex-Debug `1.12.1` are present. These are read-only dependency facts, not backend/IDE/hardware PASS. B real creation, customized normal/fault firmware, final build identities, deployment and physical acceptance are not complete.

Seven verified disposable native-test roots were inventoried, but automatic approval review rejected the PowerShell deletion command before execution with only `blocked by policy`. No directory was removed or retried through another mechanism. The preservation inventory and rejection record are `native-test-cleanup-inventory.json` and `native-test-cleanup-result.json` under the evidence root; this does not invalidate the passed checks.
