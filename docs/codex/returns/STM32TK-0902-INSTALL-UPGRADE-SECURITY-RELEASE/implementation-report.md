# STM32TK-0902 VS09-B implementation report

## Ownership and frozen inputs

- Module/slice: STM32 Toolkit 0.9, VS09-B installation, upgrade, security, and release artifacts.
- Implementer: GPT-5.6-luna, reasoning effort `max`.
- Independent reviewer/acceptor: GPT-5.6-sol primary agent. This report does not issue a review
  verdict.
- Accepted VS09-A slice base: `22bff0061e54e37eba22d892a3b8c34949c3b130`.
- Version accepted base: `9a5a132b74638a39b346848cfad0eeb7db9a0539`.
- Frozen specification commit: `4f91a92dcdd1a3b5a0efb2b535fb0274ee075d1b`.
- Frozen implementation-plan commit: `d452d5e782d5829efacc9f961e4d4c0847ed1e76`.
- Branch: `codex/STM32TK-0902-INSTALL-UPGRADE-RELEASE`.
- Product CodeHead recorded before this report commit:
  `07427d04be38e10b44ba267f28c75dfad1262b9e`.
- Worktree: `C:/tmp/stm32tk-0902-install-upgrade-release`.

The implementation retains one setup/runtime lifecycle and registration authority, the accepted
48 MCP tools and 8 Skills, and adds no controller/provider/backend, Agent-specific product logic,
second runtime, additional Python/platform target, CI, collaboration automation, hardware
behavior, VS10, or remote mutation.

## Product changes

The implementation surface changed from the accepted VS09-A base in these files:

- `LICENSE`
- `README.md`
- `README_zh-CN.md`
- `bin/setup-stm32-env.ps1`
- `schemas/stm32-release.schema.json`
- `skills/setup-stm32-env/SKILL.md`
- `tools/release/build_0900_artifacts.py`
- `tools/release/release_0900_policy.json`
- `tools/stm32-monitor/pyproject.toml`
- `tools/stm32-monitor/tests/test_package_boundary.py`
- `tools/stm32-toolkit/pyproject.toml`
- `tools/stm32-toolkit/tests/release/test_0900_artifacts.py`
- `tools/stm32-toolkit/tests/test_0900_security.py`
- `tools/stm32-toolkit/tests/test_setup_runtime.py`

The correction round closed the extracted source/release member set, binds the exact verified
manifest and utility facts through setup staging and promotion, and binds each product wheel to
the archived source. The verifier now requires exact product identity, normalized distribution
names, closed wheel metadata/RECORD/license/tag and dependency/version closure, exact official
repository provenance, and strict marker parsing. Candidate licenses contain canonical SPDX text
and all selected-wheel license/NOTICE/COPYING material. The SPDX document has unique package
authority and `DESCRIBES`, `DEPENDS_ON`, and `GENERATED_FROM` relationships. Setup performs one
offline binary-only install and publishes one generation-bound runtime state; refusals happen
before staging or quarantine.

## TDD evidence and classifications

Baseline and RED failures were classified before product edits. The correction-round artifact RED
run was:

```text
PYTHONPATH=tools/stm32-toolkit/src
py -3.12 -m pytest tools/stm32-toolkit/tests/release/test_0900_artifacts.py -q -p no:cacheprovider --basetemp C:/tmp/p0902-r1-artifact-red
```

It produced 6 expected failures covering extracted source extra/tampered members, release extra
members, a self-consistent tampered product wheel, missing provenance, malformed requirements,
and the stale SBOM fixture. These were PRODUCT/TEST RED findings and were corrected before the
Product CodeHead. Earlier baseline RED covered absent bundle/state validation and hostile runtime
state inputs; those were likewise classified PRODUCT before correction.

Affected GREEN evidence at the Product CodeHead:

- `test_0900_artifacts.py`: **33 passed**.
- `test_0900_security.py`: **27 passed**.
- `test_setup_runtime.py`: complete setup suite passed.
- `test_plugin_layout.py` plus `test_public_inventory.py`: **23 passed**.
- `py -3.12 -m py_compile tools/release/build_0900_artifacts.py`: exit 0.
- `git diff --check 22bff0061e54e37eba22d892a3b8c34949c3b130..07427d04be38e10b44ba267f28c75dfad1262b9e`: exit 0.

The first broad collection probe omitted the Monitor source root and failed with five
`ModuleNotFoundError: stm32_monitor` errors; this was ENVIRONMENT, not PRODUCT. A corrected,
non-gating full-toolkit probe was allowed to finish at the parent’s request, emitted unrelated
failures outside the frozen affected matrix, and was classified OUT-OF-SCOPE/ENVIRONMENT. It was
not used as release evidence and no unrelated product code was changed. The planned affected
slices above are the governing GREEN evidence.

## Candidate, reproducibility, and security evidence

The exact disposable Windows CPython 3.12 binary wheelhouse was assembled from read-only public
downloads. Candidate assembly and final verification used no index; no upload, authentication,
Git/GitHub mutation, or release publication was performed.

Two byte-identical candidates were built from Product CodeHead `07427d04be38e10b44ba267f28c75dfad1262b9e` using the same wheelhouse. Recursive relative-path, size, and SHA-256 comparison returned `same=True` for all 13 files; external `CHECKSUMS.sha256` verification returned **12/12**. The duplicate and wheelhouse were removed after evidence. The retained candidate is:

`C:/tmp/p0902-r1-candidate-release-a`

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `CHECKSUMS.sha256` | 1073 | `609d4e9040acb923f85fa0dca20413c11e54a4a10a179f34d9ff6318b1535795` |
| `compatibility.md` | 1742 | `309159534892c68f938000c09177b1ad34a34594f690be2828c64ca6ea6fa439` |
| `LICENSE` | 1075 | `55edb314745f2b0d3fe09e512726c3bf67cb20ba99fa3cd66859a64f3e6b6af5` |
| `licenses.zip` | 375550 | `bab50ffe7d84056cdc44047855c1b50139cbf8a003664242e8a7932119591cfc` |
| `monitor-assets.json` | 975 | `e08692c6b519cc90c82cae2ce972ae9f9636ea6796196d6418fe44c4479403c6` |
| `release-manifest.json` | 15813 | `acbb847b53e6db9f2ce508683b78ff1104500afebedd45d97527b3f31cef729e` |
| `sbom.spdx.json` | 191430 | `03b779a22ff570a3c3518fdba2fad0c22f2d83d59dff82a6a7fa38572fc4e2e1` |
| `stm32_monitor-0.9.0-py3-none-any.whl` | 1244802 | `d64315c6d441e69c75cd8b1325e28814447577ff3691188d3e192aefb4df9951` |
| `stm32_toolkit-0.9.0-py3-none-any.whl` | 2510618 | `e38f6d951d24adf8cc8de382956a208c28177fa513e5d429646490410d673d9f` |
| `stm32-toolkit-0.9.0-source.zip` | 12853664 | `55a73fbb59349d3351ce4295c71ab95e2fd8f4ac9f640089b86757c1305c5863` |
| `stm32-toolkit-0.9.0-windows-x86_64.zip` | 98693440 | `0d1f1a37a438084f19be66121dfceaa2caf396a7478cd88c3c95d444488c452d` |
| `THIRD-PARTY-NOTICES.md` | 2615 | `c9a740027186fc46351903a24913ccbfbcaf4341c86ed5d782bfd47e3151f1ea` |
| `troubleshooting.md` | 675 | `86d99f7cdb22964ec039887aafc4bf41a9c0a22a5def8fa24418b52da0976762` |

The manifest passed `schemas/stm32-release.schema.json` validation and contains 64 wheels (62
external closure wheels plus Toolkit and Monitor), 6 artifacts, source commit
`07427d04be38e10b44ba267f28c75dfad1262b9e`, and public inventory `mcpTools=48`, `skills=8`.
All manifest distribution names are normalized. The license archive has 86 members: 80
wheel-shipped license/NOTICE/COPYING materials and 6 canonical SPDX texts under
`licenses/spdx/`. The SBOM has 491 unique package authorities (62 Python, 2 product, 427 UI),
with relationships `DESCRIBES=2`, `DEPENDS_ON=96`, and `GENERATED_FROM=427`; duplicate authority
count is 0 and `NOASSERTION` license count is 0.

Fresh extracted-root security probes failed closed with subprocess return code 2 before staging:

- appended source member plus an extra source file: `extracted source closure is invalid`;
- extra release member: `release member closure is invalid`;
- replaced `release/licenses.zip`: `invalid ZIP artifact`;
- modified a product wheel and rewrote its valid RECORD/manifest facts: `bundle product wheel is not bound to its source`.

## Candidate installation, upgrade, refusal, and storage evidence

With `PYTHONPATH`, `PYTHONHOME`, `PIP_*`, and hostile PATH/user package variables removed, the
fresh extracted candidate profile produced:

- read-only Check: exit 0, bundle valid, runtime initially absent, state absent, no mutation;
- offline Bootstrap: exit 0, managed CPython 3.12.10 healthy, Toolkit/Monitor 0.9.0, state
  generation 1 matching the candidate manifest/source, exact 48 MCP tools/8 Skills, and doctor
  validation;
- post-Bootstrap Check: exit 0; managed-runtime `pip check`: exit 0, `No broken requirements found`;
- legacy Repair: exit 0 from a 0.3.0 runtime with a marker and absent state; the marker was
  preserved under `runtime/.quarantine`, state schema 1 generation 1 was created, and the
  explicit project remained unchanged;
- downgrade refusal: exit 2 for recorded highest version 1.0.0, before staging/quarantine;
- source-conflict refusal: exit 2 for mismatched manifest/source identity, before staging/quarantine.

The downgrade and source-conflict profiles remained byte-equivalent, with no `.staging` or
`.quarantine` created. Existing explicit project upgrade and Monitor storage preservation/rollback
paths remained covered by the affected regression. No real user data, network service, hardware,
or board was used; hardware and platform-only evidence remains deferred to the named later owner.

## Cleanup and Git state

All disposable p0902 candidate copies, extracted profiles, wheelhouse, basetemps, logs, failure
outputs, and generated `Testing` data were removed using verified exact paths. The generated
tracked-tree `native-outcomes/ctest-pipe/Testing` directory was removed while its source-controlled
`CTestTestfile.cmake` fixture was preserved. Exactly one final named candidate directory remains:
`C:/tmp/p0902-r1-candidate-release-a`. Sol’s independent review evidence root
`C:/tmp/p0902-sol-r1-tamper` was retained untouched.

The branch is clean, local, unpushed, and has no upstream. No push, PR, merge, tag, release,
remote branch deletion, authentication, upload, or other remote mutation was performed. This
report is committed separately after the Product CodeHead and intentionally contains neither its
own final commit SHA nor an acceptance verdict.
