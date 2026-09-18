# VS10-B offline implementation — 2026-09-18

Status: **IN_PROGRESS**. This report does not accept VS10-B or authorize deployment, hardware access, or remote mutation.

Accepted base: `16a6e59dff7fed2999fae611e3d936b0b04bbabd`. The primary conversation owns design, integration, independent review and acceptance. `/root/vs10b_host_impl` and `/root/vs10b_firmware_impl` are the two separate Luna/max implementation owners. User approval is “开始实施”; the reviewed specification and plan are under `docs/superpowers/` with date `2026-09-18` and slice name `1002-cubemx-real-board-closed-loop`.

## Reviewed CubeMX creation correction

The original public `create-prepare` failed with `CUBEMX_MCU_DESCRIPTOR_INVALID` before authorization or native generation. The installed official `families.xml` uniquely maps the exact MCU `STM32F429ZGTx` to `STM32F429Z(E-G)Tx.xml`; the accepted-base parser only searched for an exact leaf filename. This is a product discovery defect, not physical board evidence.

Code head `7a6dcfa97b7595a147cfc5a35cf725fa924ba39d` is **ACCEPTED for this bounded correction**. The changed product file is `creation_environment.py`; three existing test files cover the environment, adapter and public workflow. Index fallback occurs only when no exact descriptor exists. It binds the index path/hash to the execution environment, keeps the exact leaf token for CubeMX, and preserves the old exact-descriptor payload and digest. It does not change the installed runtime.

The primary and `/root/vs10a_probe_review` reviewed the full base-to-`83a47a68a0fc238560a76b01f09bc8befa7fabaf` diff. The sole alphabet finding was corrected by the original implementer in `7a6dcfa` and independently checked by the primary. Evidence records 66 original owner checks, 24 affected environment checks after correction, and three primary checks of the public drift guard, exact adapter token and unchanged exact-mode facts; these are separate scopes, not an aggregate test count. Native generation and firmware builds remain to be proven by actual outputs.

The subsequent fresh public apply reached native output validation and failed with `CUBEMX_NATIVE_OUTPUT_INVALID: native MCU identity is missing`. It did not configure, build or activate the destination. The existing failure cleanup removed the generated IOC. One new offline generation with a pass-through capture at the existing default-validator seam retained the actual generated project and propagated the same original error. The raw IOC has `Mcu.Name=STM32F429Z(E-G)Tx` and `Mcu.UserName=STM32F429ZGTx`, SHA256 `c3d31d0dbe513e7ca2e6d92207e81e238f9f777b767b87ef1780391b82ac6a40`. The parser reads only the grouped Name and rejects its parentheses. A bounded correction for authenticated indexed-MCU identity is frozen in specification section 7; the original firmware implementer owns it. Its verification must use this retained raw project before another native generation.

## Accepted host adaptation

Host code head `8d4e6fd8da398ee553cb57bb9fae6a6451a9504d` is **ACCEPTED for host software**. It adds B attempt `/4`, recovery policy `/3` and `new-cubemx-physical-repair/1`. Both reviews of initial candidate `b4d13852c9ef7f6127021a5bca17187e9124d260` required typed rejection for non-string scenario inputs, exact unknown-schema rejection before dispatch, and B full-chain verification. The original Luna implementation owner corrected all three; the primary reviewed the full correction diff and `/root/vs10b_host_review` independently accepted the complete base-to-final behavior. The existing persisted physical-chain test now covers A and B through revision 7 with source intent, authorization, expiry/CAS and final FixVerification. Raw corrected-suite output and exit 0 are in `evidence/host/correction-final.*`; this is software contract evidence, not physical PASS.

The primary compared the existing A public scenario/policy serializer output to the installed accepted A runtime. The complete output is byte-identical, SHA256 `0cb7a5435d5ea0990225f0c42a033e950231b0bda88c4b8e5ec98bc184e24d5e`. A physical `/2`, continuation `/3`, replay `/1`, historical attempt 7 and VS10-A acceptance remain unchanged.

The local integrated code head is `f5ef465e2b870c9bb86b6edbd941c673acf2bdca` on `codex/STM32TK-1002-CUBEMX-REAL-BOARD-integration`. Its product/test files match the two accepted implementation heads exactly. The primary ran ten targeted integration checks covering the B persisted chain, corrected error dispatch and creation safeguards; exit 0. A serializer output remains byte-identical. Evidence: `integration-checks-result.json` and its raw stdout/stderr under the B evidence root. The indexed native identity correction and real firmware preparation remain outstanding, so this does not mark the whole software phase complete.

## Evidence and remaining boundary

Current local ledger: `D:\codex-tmp\v10b-0918\evidence\implementation-ledger.json`. Raw implementation, review, compatibility and original failure evidence is retained below that evidence root. The earlier `preflight-summary.json` is explicitly historical and points to this current ledger.

Actual installed DFP `3.1.1` metadata supports `STM32F429ZGTx`; VS Code `1.129.1` and Cortex-Debug `1.12.1` are present. These are read-only dependency facts, not backend/IDE/hardware PASS. B real creation, customized normal/fault firmware, final build identities, deployment and physical acceptance are not complete.

Seven verified disposable native-test roots were inventoried, but automatic approval review rejected the PowerShell deletion command before execution with only `blocked by policy`. No directory was removed or retried through another mechanism. The preservation inventory and rejection record are `native-test-cleanup-inventory.json` and `native-test-cleanup-result.json` under the evidence root; this does not invalidate the passed checks.
