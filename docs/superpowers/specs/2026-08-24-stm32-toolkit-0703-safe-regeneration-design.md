# STM32 Toolkit 0.7 VS07-C Safe Regeneration Design

> **Status:** Approved for execution on 2026-08-24 under the user's delegated
> approval authority.

## 1. Ledger and accepted base

- Module/phase: STM32 Toolkit 0.7 / VS07-C.
- Full accepted base: `fcdcd1ab9c1f358df78fbfb8b12ed9b0397c534d`.
- Specification and plan owner: GPT-5.6-sol primary agent.
- Implementation owner: one GPT-5.6-luna agent at reasoning `max`.
- Independent reviewer/acceptor: GPT-5.6-sol primary agent.
- Branch/worktree: `codex/STM32TK-0703-SAFE-REGENERATION` /
  `C:/tmp/stm32tk-0703-safe-regeneration`.
- Remote authority: none. No push, PR mutation, merge, tag, release, remote
  branch operation, installation, or hardware action is authorized.

VS07-B is accepted at this base. Its public creation behavior, CubeMX 6.18
adapter, schema-3 native project, ownership manifest, managed configuration,
Debug/Release build, and activation contracts are reused rather than copied.

## 2. Runnable user scenarios

1. **Preview and apply one IOC change.** A caller edits the project-local IOC,
   obtains a read-only regeneration plan, explicitly authorizes an isolated
   CubeMX preview, reviews a bounded exact file diff, then consumes one
   authorization. Apply reproduces the same preview, preserves user files,
   configures and builds Debug and Release, and atomically activates the new
   project.
2. **Protect user and Toolkit bytes.** Files below declared `App/` and `Tests/`
   roots survive byte-for-byte. Drift in CubeMX-owned files other than the one
   declared IOC, drift in Toolkit-managed files/model, or an unknown path
   outside the closed ownership classes blocks before project mutation.
3. **Recover from failure.** Preview mismatch, CubeMX failure, candidate
   validation failure, configure/build failure, activation race, or activation
   failure leaves the prior project active or recoverable and returns one typed
   result. No half-regenerated success is claimed.
4. **Keep the Keil path isolated.** A schema-2 Keil/GCC project receives a
   typed `REGENERATION_NOT_CUBEMX_PROJECT` refusal. Its files and existing
   migration/configure/build capabilities remain byte-for-byte unchanged.

## 3. Explicit non-goals

- No MCU/board creation changes, Keil regeneration, Keil write-back, hardware
  flash/debug/monitor, VS08 resumability, release matrix, coverage gate, Linux
  audit, package installation, or Python expansion beyond CPython
  `>=3.12,<3.13`.
- No arbitrary overwrite switch, user-drift override, generator-version
  override, conflict-merging engine, CubeMX USER CODE parser, background
  cleanup daemon, provider/plugin system, second project model, or hand-built
  MCU database.
- This slice supports a VS07-B CubeMX destination below a Git workspace root.
  It does not replace a workspace root or move a `.git` directory.
- `App/` and `Tests/` are preserved ownership roots; this slice does not invent
  new build membership for files the schema does not already reference.

## 4. Public API

The CLI adds exactly:

```text
stm32-toolkit project regenerate-plan --project-root ROOT --destination REL --json
stm32-toolkit project regenerate-prepare --project-root ROOT --destination REL --plan-id ID --action-digest DIGEST --authorized --json
stm32-toolkit project regenerate-apply --project-root ROOT --authorization-digest DIGEST --authorized --json
```

The MCP server adds exactly:

```text
stm32_project_regenerate_plan(destination)
stm32_project_regenerate_prepare(destination, planId, actionDigest, authorized)
stm32_project_regenerate_apply(authorizationDigest, authorized)
```

CLI and MCP remain thin adapters over these neutral functions:

```python
plan_regeneration_workflow(request, *, support_profile=None, repository=None)
prepare_regeneration_workflow(
    request, *, plan_id, action_digest, authorized,
    support_profile=None, repository=None, store=None,
)
apply_regeneration_workflow(
    request, *, authorization_digest, authorized,
    support_profile=None, repository=None, store=None,
)
```

`RegenerationWorkflowRequest` contains only absolute `workspace_root`, absolute
Toolkit `data_root`, safe `session_id`, and portable non-empty `destination`.
The project-local IOC, target, framework, language, and ownership roots are
derived from the current schema-3 CubeMX project; callers cannot substitute
them at apply time.

Plan is project- and data-read-only and never starts CubeMX. Prepare requires
JSON boolean `true`, runs one bounded preview generation, writes only the
single-use authorization below the Toolkit data root, and cleans preview,
control, generation, and activation roots before returning. Apply requires
JSON boolean `true`, consumes the authorization on every attempted execution,
runs CubeMX once, and mutates the destination only after all revalidation,
preview, configure, and build gates pass.

## 5. Frozen models and digests

`RegenerationPlan` is a frozen value with:

- schema version, normalized request, logical project ID, device, IOC path;
- exact IOC current SHA-256 and prior owned SHA-256;
- Git HEAD and project state digest;
- CubeMX ownership-manifest digest and managed-manifest/model digest;
- execution-environment digest and exact recorded/current generator/package
  facts;
- counts for CubeMX-owned, Toolkit-owned, user-owned, and derived files;
- ordered blockers, expiry, `planId`, `actionDigest`, and `mutated:false`.

The project state digest hashes the canonical request plus every classified
portable path, type, size, and SHA-256, including the changed IOC and all user
files. Derived build/artifact bytes are validated as safe disposable paths but
are excluded from the semantic state digest. `planId` binds the complete plan
except time/display fields. `actionDigest` additionally binds the operation,
destination canonical path, exact environment, and current destination state.

`RegenerationPreview` has:

- `previewDigest`, summary counts, and ordered change records;
- each change record contains portable path, `added|modified|deleted`, before
  and after SHA-256/size when present, and an optional bounded UTF-8 unified
  diff;
- the digest is computed from the complete untruncated replacement inventory
  and ownership transition, not from the display subset;
- individual text diffs are limited to 64 KiB and aggregate public preview is
  limited to 1 MiB. Exceeding the record/display bound fails with
  `REGENERATION_PREVIEW_TOO_LARGE`; no partial preview is authorized.

Prepare creates an internal ephemeral store-issued creation capability for
the authorized preview invocation. It then issues the persistent application
capability using preview-bound plan/action digests. No preview bytes or staging
directory survive prepare. Apply recomputes the base plan and exact preview;
both preview-bound digests must equal the consumed capability before any
destination mutation.

## 6. One ownership source of truth

Classification precedence is exact and case-fold collision checked:

1. **Toolkit-owned:** paths listed in
   `.stm32-toolkit/generated-files.json`, plus `.stm32-project.json`,
   `.stm32-toolkit/generated-files.json`, and
   `.stm32-toolkit/cubemx-ownership.json`.
2. **CubeMX-owned:** remaining paths in the strict schema-1 CubeMX ownership
   manifest. Every current byte must match its recorded size/hash except the
   single project-local IOC named by `generation.cubeMxIoc`.
3. **User-owned:** safe regular files and ordinary directories only below the
   declared `generation.userDirectories`, which must remain the closed
   `App`/`Tests` roots for this slice. They are copied byte-for-byte to the
   candidate and rehashed immediately before activation.
4. **Derived/disposable:** `build/**`, `artifacts/**`, and
   `.stm32-toolkit/build.lock`. They are safely inventoried, never copied, and
   are recreated by configure/build.

Any other file or directory is `REGENERATION_UNKNOWN_PATH`. Any symlink,
junction/reparse point, special file, path escape, duplicate, case-fold
collision, depth/size/count overflow, unreadable byte, or mid-read change is
`REGENERATION_PATH_UNSAFE` or `REGENERATION_STATE_CHANGED`. Inventory uses the
existing native bounds: at most 200,000 files, 256 MiB aggregate, 32 MiB per
file, depth 32, and 4,096 UTF-8 bytes per relative path.

Toolkit-managed entries and the canonical loaded model must match the managed
manifest before preview. The IOC is the only allowed owned-source drift. A
CubeMX/package name, version, executable hash, or package hash difference from
the ownership manifest is `REGENERATION_GENERATOR_DRIFT`; there is no override
in VS07-C.

## 7. Preview and apply lifecycle

Prepare performs, in order:

1. Recompute the exact plan, Git HEAD, ownership, source, destination, and
   environment; compare exact caller plan/action digests.
2. Require `authorized is True`; issue and consume an internal ephemeral
   capability; run CubeMX once in a fresh sibling generation container.
3. Validate the one native child with the existing strict CubeMX parser.
4. Classify old/new CubeMX bytes, compute the complete replacement inventory
   and bounded preview, and ensure target/device/framework/language/linker/
   package facts remain compatible.
5. Clean every owned preview/control root, then issue one expiring persistent
   apply capability bound to the preview digests. Preview cleanup failure
   returns a typed failure and issues no usable capability.

Apply performs, in order:

1. Consume the capability exactly once, then revalidate Git HEAD, project
   state, IOC hash, ownership, environment, destination, and absence of all
   sibling transaction collisions.
2. Run CubeMX once in a fresh generation container, validate the native child,
   recompute the complete preview, and require exact preview-bound plan/action
   equality.
3. Copy only the validated `App/` and `Tests/` trees into the candidate; write
   new CubeMX/project ownership manifests; seed/reuse managed configuration.
4. Relocate the child to a separate activation staging root and remove the
   generation container before configure/build, following the accepted VS07-B
   lock-safe ordering.
5. Reuse existing configure plus `arm-debug` and `arm-release` builds. Any
   failure removes owned staging and leaves the current destination untouched.
6. Under one destination activation lock, revalidate the project/user state,
   rename the current destination to an owned backup, rename activation staging
   to the destination, and remove the backup. An activation failure rolls the
   exact old directory back. A post-activation backup-cleanup failure returns
   `REGENERATION_CLEANUP_REQUIRED` with a bounded relative recovery name; it
   never claims clean success and never deletes an unowned collision.

Success returns the preview digest, destination, new ownership-manifest hash,
Debug/Release results, attempt ID, and `mutated:true`. All failure details are
bounded and sanitized; no raw CubeMX output, absolute private path, or
credential enters public results.

## 8. Stable failure semantics

Public regeneration-specific codes are:

```text
REGENERATION_INPUT_INVALID
REGENERATION_NOT_CUBEMX_PROJECT
REGENERATION_PROJECT_INVALID
REGENERATION_OWNERSHIP_INVALID
REGENERATION_USER_DRIFT
REGENERATION_TOOLKIT_DRIFT
REGENERATION_UNKNOWN_PATH
REGENERATION_PATH_UNSAFE
REGENERATION_GENERATOR_DRIFT
REGENERATION_PLAN_CHANGED
REGENERATION_AUTHORIZATION_REQUIRED
REGENERATION_AUTHORIZATION_INVALID
REGENERATION_AUTHORIZATION_CONSUMED
REGENERATION_AUTHORIZATION_EXPIRED
REGENERATION_PREVIEW_FAILED
REGENERATION_PREVIEW_TOO_LARGE
REGENERATION_PREVIEW_CHANGED
REGENERATION_STATE_CHANGED
REGENERATION_CONFIGURATION_FAILED
REGENERATION_DEBUG_BUILD_FAILED
REGENERATION_RELEASE_BUILD_FAILED
REGENERATION_ACTIVATION_FAILED
REGENERATION_ROLLBACK_FAILED
REGENERATION_CLEANUP_REQUIRED
```

Existing exact `CUBEMX_*`, build, Git, and environment codes may pass through
when they identify the actual failing owner. Failures are classified PRODUCT,
ENVIRONMENT, INFRASTRUCTURE, PLATFORM, HARDWARE, TEST, or REPORT before code
changes. CubeMX/package absence is ENVIRONMENT. No fake or fixture result is
reported as a real native PASS.

## 9. Acceptance evidence

The Luna implementer owns TDD RED/GREEN evidence, the exact slice run, one
fresh real CubeMX regeneration software scenario, commits, and implementation
report. The real scenario changes `ProjectManager.HeapSize` from `0x200` to
`0x300` in a copied accepted VS07-B captured-IOC project, preserves seeded
`App/` and `Tests/` byte hashes, completes preview/apply plus Debug/Release,
and proves no transaction/control residue or new persistent CubeMX/Java PID.

Sol reviews the complete
`fcdcd1ab9c1f358df78fbfb8b12ed9b0397c534d..final-head` diff in a new clean
detached worktree, repeats the exact slice, runs independent drift/preview/
rollback probes, repeats the fresh native scenario and a read-only Keil
refusal, and issues the only acceptance verdict. Hardware is not part of this
slice.
