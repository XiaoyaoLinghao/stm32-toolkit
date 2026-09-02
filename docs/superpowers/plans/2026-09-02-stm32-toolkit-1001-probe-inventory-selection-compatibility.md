# STM32TK-1001 Probe Inventory and Selection Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Repository governance overrides the skill's fresh-agent-per-task default: exactly one `gpt-5.6-luna`/`max` implementation owner owns all implementation and implementation tests; GPT-5.6-sol independently reviews the complete diff.

**Goal:** Safely list arbitrary bounded PyOCD hardware identities, expose portable public probe selectors with confirmation facts, and freshly resolve an explicitly selected probe without changing downstream identifier gates or touching hardware.

**Architecture:** Add one pure selector adapter inside the existing `stm32_toolkit.probe` package. Portable legacy hardware IDs remain their own public selectors; every other admitted raw identity maps to `pyocd:<sha256>`. Expand the existing descriptor and client response validation, then reuse the unchanged worker, service, CLI/MCP list composition, lease, Flash, handoff, Monitor, and target paths.

**Tech Stack:** CPython 3.12.10, pytest 8.4.2, PyOCD 0.45.1 production seam, dataclasses, canonical JSON worker protocol, SHA-256.

## Global Constraints

- Full accepted base for independent review: `74ee5f4c7872af1bb612c9068af36319457e087b`.
- Approved specification head: `372d80388aa2ecd806fce1ba2cc83796106e15e0`.
- Active branch/worktree: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl` at `C:\tmp\stm32tk-1001-legacy-hardware-impl`.
- Exactly one `gpt-5.6-luna` implementation owner at reasoning effort `max`; GPT-5.6-sol owns architecture, complete-diff review, and acceptance.
- Remote authority is none: no fetch-required mutation, push, PR mutation, merge, closure, tag, release, or remote branch deletion.
- Hardware authority is none during implementation/review: no attach, reset, read, program, Monitor session, or physical PASS claim.
- Product changes are limited to one selector adapter plus `probe/backend.py`, `probe/pyocd_backend.py`, and `probe/client.py`.
- If product edits are required in worker, service, hardware workflows, Flash, handoff, lease, Monitor, target testing, schemas, CLI/MCP registration, or any other module, stop and return to Sol design review.
- Do not broaden the existing portable internal identifier grammar or add a backend, registry, cache, runtime, controller, provider, transport, dependency, Python version, CI, or collaboration automation.
- Use TDD: commit RED tests before product code, then commit the minimal GREEN product/test adjustments, then commit the implementation report separately.
- Tests use the system CPython 3.12.10 at `C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe`, explicit current-source `PYTHONPATH`, `-p no:cacheprovider`, and exact external run-owned basetemps.
- After each test run, preserve the minimum result, inspect and remove only that run's attributed basetemp, and never delete source tests, reusable fixtures, campaign evidence, shared caches, or user files.

---

## File structure and ownership

**Product files permitted:**

- Create `tools/stm32-toolkit/src/stm32_toolkit/probe/selector.py` — sole raw-hardware validation, fingerprint, and public-selector mapping authority.
- Modify `tools/stm32-toolkit/src/stm32_toolkit/probe/backend.py` — immutable descriptor facts and public dictionary.
- Modify `tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py` — fresh raw inventory adaptation and exact selector resolution.
- Modify `tools/stm32-toolkit/src/stm32_toolkit/probe/client.py` — closed validation of expanded list descriptors.

**Test files permitted as needed by the frozen cases:**

- Create `tools/stm32-toolkit/tests/test_probe_selector.py`.
- Modify `tools/stm32-toolkit/tests/test_pyocd_backend.py`.
- Modify `tools/stm32-toolkit/tests/test_probe_worker.py`.
- Modify `tools/stm32-toolkit/tests/test_probe_service.py`.
- Modify `tools/stm32-toolkit/tests/test_probe_client.py`.
- Modify `tools/stm32-toolkit/tests/test_hardware_workflows.py`.
- Modify `tools/stm32-toolkit/tests/test_cli_hardware.py` and `tools/stm32-toolkit/tests/test_mcp_hardware.py` only if their existing exact list-response assertions require the additive descriptor facts; do not change tool names or input schemas.

**Reports:**

- Create `docs/codex/returns/STM32TK-1001-PROBE-INVENTORY-SELECTION-COMPAT/implementation-report.md` in a separate Luna/max report commit.
- Create `docs/codex/returns/STM32TK-1001-PROBE-INVENTORY-SELECTION-COMPAT/review-report.md` only after independent Sol review; the Luna implementer must not edit it.

## Task 1: Commit public and security RED tests

**Interfaces:**

- Consumes: approved selector rules and current `ProbeDescriptor`, `PyOCDBackend`, worker/service/client, and public `probe list` behavior.
- Produces: one test-only RED commit that fails for the missing selector adapter, missing confirmation fields, current space rejection, or missing client validation. No product file changes.

- [ ] **Step 1: Audit the implementation worktree before ownership changes**

Run:

```powershell
git status --porcelain=v1 --untracked-files=all
git log --oneline -n 4
git diff --name-status 74ee5f4c7872af1bb612c9068af36319457e087b..HEAD
git log --oneline --left-right origin/codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl...HEAD
```

Require only the approved specification and plan commits beyond `74ee5f4c...`, a clean worktree, and no unexpected pushed/unpushed changes. Record the exact plan head for later product allowlist comparisons.

- [ ] **Step 2: Add pure selector RED cases**

Create `test_probe_selector.py` with literal expectations:

```python
ATK_RAW = "ATK 20210914"
ATK_FINGERPRINT = "91d67402fe525a5d16bf226f59ab5ecea743eb69292e95719167263ed1fcbf8c"
ATK_SELECTOR = f"pyocd:{ATK_FINGERPRINT}"

def test_nonportable_hardware_id_maps_to_full_portable_selector():
    assert valid_hardware_probe_id(ATK_RAW)
    assert probe_fingerprint(ATK_RAW) == ATK_FINGERPRINT
    assert public_probe_selector(ATK_RAW) == ATK_SELECTOR

def test_existing_portable_selectors_remain_exact():
    assert public_probe_selector("probe-a") == "probe-a"
    assert public_probe_selector("0001A0000000") == "0001A0000000"

def test_reserved_prefix_is_never_treated_as_raw_public_selector():
    raw = "pyocd:" + "a" * 64
    assert public_probe_selector(raw) == "pyocd:" + probe_fingerprint(raw)
    assert public_probe_selector(raw) != raw
```

Add a literal table proving printable values such as `r'CMSIS-DAP_QM Rev.B #001 / \\ port *'` and `"探针 Ω Rev.B"` are admitted and mapped, while `None`, `123`, `""`, 513 ASCII bytes, NUL, newline, tab, `\x1b`, `\u202e`, and an isolated surrogate are rejected. Tests must not derive expected selectors using production helpers except where explicitly testing fingerprint composition; include literal SHA values for the two representative identities.

- [ ] **Step 3: Add backend inventory and exact-resolution RED cases**

In `test_pyocd_backend.py`, add cases proving:

- raw `ATK 20210914` lists as `ATK_SELECTOR`, retains exact `hardwareId`, and returns the literal fingerprint;
- `probe-a` keeps `probeId == hardwareId == "probe-a"` and adds its correct fingerprint;
- printable hostile-looking hardware text is data and is never used as a path or match expression;
- invalid raw descriptors fail with `PROBE_DESCRIPTOR_INVALID` and zero sessions;
- `open_attach(ATK_SELECTOR, target)` freshly enumerates, selects exactly the ATK raw probe object, and returns attachment evidence containing `ATK_SELECTOR`;
- stale, partial, case-changed, missing, duplicate-selector, and reserved-prefix cases create zero sessions;
- exact portable legacy selection remains unchanged.

Replace the old expectation that `"probe with spaces"` is malformed. Keep caller-side rejection cases for non-portable public selectors such as raw `"ATK 20210914"`, because callers must use the listed portable selector.

- [ ] **Step 4: Add descriptor propagation and closed-client RED cases**

Update worker/service/client tests so a descriptor's structured output contains exactly:

```python
{
    "probeId": ATK_SELECTOR,
    "hardwareId": ATK_RAW,
    "probeFingerprint": ATK_FINGERPRINT,
    "vendor": "ATK",
    "product": "ATK-HS-V3-CMSIS-DAP",
    "boardName": None,
}
```

Exercise the real worker canonical serializer and service `probe.list` response. Add client cases rejecting missing/extra keys, a non-portable `probeId`, invalid `hardwareId`, non-hex/wrong fingerprint, fingerprint not matching `hardwareId`, malformed display fields, and inconsistent legacy selector mapping. Preserve stable `PROBE_RESPONSE_INVALID` without raw exception text.

- [ ] **Step 5: Add public list parity and no-attach RED cases**

Use the existing `probe_list_workflow` seams and CLI/MCP dispatch tests to prove the same six descriptor fields reach both public adapters and that listing invokes only `list_probes()` plus close/cleanup, never `open_attach`, memory access, reset, or flash. Keep the 48-name MCP inventory assertion unchanged.

- [ ] **Step 6: Run RED against current product bytes**

Prepare a new exact basetemp that does not already exist:

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  tools/stm32-toolkit/tests/test_probe_selector.py `
  tools/stm32-toolkit/tests/test_pyocd_backend.py `
  tools/stm32-toolkit/tests/test_probe_worker.py `
  tools/stm32-toolkit/tests/test_probe_service.py `
  tools/stm32-toolkit/tests/test_probe_client.py `
  tools/stm32-toolkit/tests/test_hardware_workflows.py `
  tools/stm32-toolkit/tests/test_cli_hardware.py `
  tools/stm32-toolkit/tests/test_mcp_hardware.py `
  -p no:cacheprovider --basetemp 'C:\tmp\stm32tk-1001-probe-selector-red-20260902' -q
```

Require collection success and failures caused only by the missing adapter/fields/current raw-space rejection or missing closed client validation. Import errors, fixture errors, unrelated failures, or tests that already pass for the target behavior stop implementation for test-design review.

- [ ] **Step 7: Inspect and clean RED artifacts, then commit tests only**

Preserve the command, exit code, failing node names, and expected failure reason. Resolve and inspect only `C:\tmp\stm32tk-1001-probe-selector-red-20260902`; verify it is under `C:\tmp` and matches the exact run-owned name before removing it recursively. Do not touch campaign or source paths.

Run:

```powershell
git diff --check
git diff --name-only
git status --short
```

Require only the allowed test paths and no product/report changes. Commit:

```powershell
git add -- tools/stm32-toolkit/tests
git commit -m "test(vs10a): define portable opaque probe selection"
```

## Task 2: Implement the minimal adapter and expanded descriptor

**Interfaces:**

- Consumes: Task 1 RED tests and the current portable identifier grammar.
- Produces: `valid_hardware_probe_id`, `probe_fingerprint`, `public_probe_selector`, expanded `ProbeDescriptor`, fresh selector resolution, and closed client validation. No downstream grammar change.

- [ ] **Step 1: Implement the pure selector adapter**

Create `probe/selector.py` with no I/O or mutable state. Use the existing portable regex bytes unchanged. The implementation shape is:

```python
_PORTABLE_SELECTOR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_RESERVED_PREFIX = "pyocd:"
_MAX_HARDWARE_ID_BYTES = 512

def valid_hardware_probe_id(value: object) -> bool:
    if not isinstance(value, str) or not value or not value.isprintable():
        return False
    try:
        return len(value.encode("utf-8", errors="strict")) <= _MAX_HARDWARE_ID_BYTES
    except UnicodeEncodeError:
        return False

def probe_fingerprint(hardware_id: str) -> str:
    if not valid_hardware_probe_id(hardware_id):
        raise ValueError("hardware probe identifier is invalid")
    return sha256(hardware_id.encode("utf-8")).hexdigest()

def public_probe_selector(hardware_id: str) -> str:
    fingerprint = probe_fingerprint(hardware_id)
    if _PORTABLE_SELECTOR.fullmatch(hardware_id) and not hardware_id.startswith(_RESERVED_PREFIX):
        return hardware_id
    return f"{_RESERVED_PREFIX}{fingerprint}"
```

Do not export the regex or add vendor-specific behavior.

- [ ] **Step 2: Expand and validate `ProbeDescriptor`**

In `probe/backend.py`, retain the existing first four constructor arguments and append optional internal construction fields `hardware_id: str | None = None` and `probe_fingerprint: str | None = None`. In `__post_init__`, default `hardware_id` to `probe_id` for trusted legacy fake construction, derive the fingerprint when omitted, and require:

- admitted `hardware_id`;
- `probe_id == public_probe_selector(hardware_id)`;
- supplied fingerprint equals `probe_fingerprint(hardware_id)`.

Use `object.__setattr__` only for the two derived immutable facts. `to_dict()` returns the exact six-key public shape in the specification.

- [ ] **Step 3: Adapt PyOCD inventory and fresh exact selection**

In `probe/pyocd_backend.py`:

- keep `_valid_identifier()` byte-for-byte for target/profile/internal fields;
- replace raw-probe validation with `valid_hardware_probe_id()`;
- build descriptors with `probe_id=public_probe_selector(raw_id)`, `hardware_id=raw_id`, and the full fingerprint;
- sort by `(descriptor.probe_id, descriptor.hardware_id)`;
- change `_select_probe(public_probe_id)` to enumerate raw probes, compute each public selector, collect exact matches, and retain existing not-found/ambiguous errors;
- return and store the caller's public selector in attachment evidence and existing identity hashing;
- pass the selected PyOCD object to session creation exactly as before.

Do not alter `dap_protocol`, frequency, connect mode, target validation, session options, close behavior, raw exception redaction, or any target operation.

- [ ] **Step 4: Close the client list-response contract**

In `probe/client.py`, validate every `probe.list` item before returning it:

- exact six keys;
- portable `probeId` under the existing regex;
- admitted `hardwareId`;
- exact mapping `probeId == public_probe_selector(hardwareId)`;
- exact lowercase fingerprint match;
- `vendor` and `product` as non-empty stripped strings of at most 128 characters with no character below U+0020;
- `boardName` as `None` or the same bounded stripped display-string form;
- no duplicate public selectors in one response.

On any mismatch, raise the existing `_response_error()` / `PROBE_RESPONSE_INVALID`. Do not change endpoint probe validation, attach response validation, request schema, or other client operations.

- [ ] **Step 5: Run the focused GREEN suite**

Use a new external basetemp:

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  tools/stm32-toolkit/tests/test_probe_selector.py `
  tools/stm32-toolkit/tests/test_pyocd_backend.py `
  tools/stm32-toolkit/tests/test_probe_worker.py `
  tools/stm32-toolkit/tests/test_probe_service.py `
  tools/stm32-toolkit/tests/test_probe_client.py `
  tools/stm32-toolkit/tests/test_hardware_workflows.py `
  tools/stm32-toolkit/tests/test_cli_hardware.py `
  tools/stm32-toolkit/tests/test_mcp_hardware.py `
  tools/stm32-toolkit/tests/test_probe_lease.py `
  tools/stm32-toolkit/tests/test_flash.py `
  tools/stm32-toolkit/tests/test_debug_handoff.py `
  tools/stm32-toolkit/tests/test_monitor_observation.py `
  tools/stm32-toolkit/tests/test_physical_target_workflows.py `
  -p no:cacheprovider --basetemp 'C:\tmp\stm32tk-1001-probe-selector-green-20260902' -q
```

The downstream files are included because arbitrary selectors previously tempted grammar changes; their product bytes must stay unchanged while their portable fixtures remain green. Any failure is classified before code changes. Do not edit a downstream product module to make this matrix pass.

- [ ] **Step 6: Perform mutation and scope checks**

Confirm tests would fail for: returning raw ATK as `probeId`, truncating the hash, accepting a reserved raw prefix unchanged, using substring/case-insensitive selection, omitting fresh enumeration, allowing invalid controls, trusting a mismatched fingerprint, or attaching the first probe.

Run:

```powershell
git diff --check
git diff --name-only
git status --short
```

Compare product paths against the four-file allowlist. Stop on any other product change. Inspect and remove only the exact GREEN basetemp after preserving the result.

- [ ] **Step 7: Commit code and tests**

Stage only allowed product/test files and commit:

```powershell
git add -- `
  tools/stm32-toolkit/src/stm32_toolkit/probe/selector.py `
  tools/stm32-toolkit/src/stm32_toolkit/probe/backend.py `
  tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py `
  tools/stm32-toolkit/src/stm32_toolkit/probe/client.py `
  tools/stm32-toolkit/tests
git commit -m "fix(vs10a): adapt opaque PyOCD probe identities"
```

Record this full code head before any report commit.

## Task 3: Commit the implementation report separately

**Interfaces:**

- Consumes: accepted base, approved spec/plan, RED commit, GREEN code head, focused verification, cleanup, and exact local/remote state.
- Produces: one accurate report-only commit; it does not claim Sol acceptance or hardware PASS.

- [ ] **Step 1: Write the report**

Create the implementation report with:

- full accepted base `74ee5f4c...`;
- full approved spec and plan commits;
- exact RED and GREEN/code-head commits;
- one Luna/max implementer and Sol reviewer ownership;
- exact RED failure reasons and GREEN command/count/outcome;
- changed product/test paths and proof downstream product paths remained unchanged;
- classification `PRODUCT_COMPATIBILITY` for the original failure;
- cleanup result and any exact residue classified separately;
- Toolkit worktree/branch/upstream and pushed/unpushed state;
- explicit `HARDWARE NOT RUN`, `SOL REVIEW PENDING`, and `REMOTE ACTION NONE`.

Do not include the report commit's own SHA or claim H2/VS10-A acceptance.

- [ ] **Step 2: Verify and commit report only**

Run:

```powershell
git diff --check
git diff --name-only
git status --short
```

Require only the report path, then commit:

```powershell
git add -- docs/codex/returns/STM32TK-1001-PROBE-INVENTORY-SELECTION-COMPAT/implementation-report.md
git commit -m "docs(vs10a): report probe selection compatibility"
```

Return full report head, code head, tree IDs, test totals, cleanup, and remote state to Sol. Do not push.

## Task 4: Independent Sol review and acceptance gate

This task is owned by GPT-5.6-sol, not the Luna implementer.

- [ ] **Step 1: Create a clean detached review worktree at the returned report head**

Reconstruct accepted base, spec/plan, implementation owner, RED/GREEN/report commits, tracked/untracked state, and remote authority. Review the complete `74ee5f4c7872af1bb612c9068af36319457e087b`-to-code-head product/test diff and the report-only delta separately.

- [ ] **Step 2: Verify contract and scope**

Require exactly the four allowed product paths, applicable test/report paths, preserved downstream product bytes, exact selector mapping, closed response validation, fresh unique resolution, unchanged attach/session options, and no hidden cache/registry/auto-selection. Run `git diff --check`.

- [ ] **Step 3: Run only risk-triggered independent verification**

Run the focused selector/backend/worker/service/client/public list suite first. Expand to downstream regression files only if complete-diff review or focused failures create a concrete risk trigger. Use a new Sol-owned external basetemp and clean only that exact run-owned path.

- [ ] **Step 4: Record one verdict**

Create the Sol-owned review report with `ACCEPTED`, `REVISION_REQUIRED`, or `REWRITE_REQUIRED`. On correctable findings, return to the same Luna/max implementation owner. Do not self-patch product code as Sol. If accepted, stop before runtime rebuild or passive hardware enumeration unless the user separately continues that phase.
