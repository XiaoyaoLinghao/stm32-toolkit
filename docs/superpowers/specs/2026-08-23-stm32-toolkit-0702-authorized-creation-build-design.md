# STM32 Toolkit VS07-B Authorized Creation and Build Design

**Status:** Approved for implementation under the user's standing approval waiver  
**Date:** 2026-08-23  
**Module/phase:** STM32 Toolkit 0.7 / VS07-B  
**Accepted base:** `bff9cc120923b0e9f2ba29a1b3511f1bcc26ab6e`  
**Specification owner/reviewer:** GPT-5.6-sol primary agent  
**Implementation owner:** one GPT-5.6-luna agent, reasoning `max`  
**Branch:** `codex/STM32TK-0702-CREATION-APPLY`  
**Remote authority:** none

## 1. Outcome and boundaries

VS07-B turns an accepted VS07-A creation plan into one authorized, single-use
operation. It invokes STM32CubeMX once inside an isolated staging directory,
validates the native project, derives the existing Toolkit project model,
configures and builds both Debug and Release, then transactionally activates
the complete project at the planned destination.

Runnable scenarios are:

1. A supported `.ioc` request is prepared, authorized once, generated,
   configured, built in Debug and Release, and activated as one usable project.
2. A supported MCU request follows the same path from CubeMX's installed MCU
   database and an installed offline firmware package.
3. Reuse of an authorization, drift in any plan/tool/repository/destination
   fact, CubeMX failure, invalid native output, or either build failure closes
   without exposing a half-created project.
4. A host without the required offline firmware package reports a typed
   environment fact and does not invoke generation or claim a positive result.

Non-goals are VS07-C regeneration/merge, Keil isolation, flash/debug/hardware,
software or firmware-package installation, remote Git operations, release
matrices, coverage gates, extra Python versions, and any Python runtime outside
`>=3.12,<3.13`.

## 2. Frozen lifecycle and source of truth

The lifecycle is:

`planned -> prepared -> consumed -> staged -> validated -> configured -> built -> activated`

The VS07-A `CreationPlan` remains the source of truth for requested source,
destination, framework, language, inventory, support facts, `planId`, and
`actionDigest`. It is deterministic and therefore is not itself an execution
capability.

`project create-prepare` recomputes the plan, requires the caller's exact
`planId` and `actionDigest`, validates execution prerequisites, and creates a
random, expiring, single-use authorization record outside the project tree.
It does not invoke CubeMX or mutate the destination. The record is the only
source of truth for authorization state.

`project create-apply` accepts only the returned `authorizationDigest` plus an
exact boolean `authorized=true`. Consumption is an atomic create/rename state
transition. One concurrent caller can win; replay receives
`CREATION_AUTHORIZATION_CONSUMED`. A failed attempt never restores the consumed
capability. The caller may explicitly prepare a fresh capability for the same
unchanged plan.

Records live below the Toolkit data root at
`creation/authorizations/<authorizationDigest>.json`. They contain a random
nonce, issue/expiry times, the normalized plan and execution-environment
digests, and state. They contain no credentials. Attempt evidence lives below
`creation/attempts/<attemptId>/` and is bounded.

## 3. Public behavior

### CLI

```text
stm32-toolkit project create-prepare \
  --source-kind ioc|mcu|board --source VALUE --destination PATH \
  --framework hal|ll --language c|cpp \
  --plan-id ID --action-digest DIGEST

stm32-toolkit project create-apply \
  --authorization-digest DIGEST --authorized
```

`create-prepare` returns normalized plan facts, `authorizationDigest`,
`executionEnvironmentDigest`, `expiresAt`, `mutated=false`, and blockers. It
fails before issuing a capability if execution prerequisites are missing.

`create-apply` returns `planId`, `authorizationDigest`, destination portable
path, CubeMX ownership-manifest path/hash, the configuration `planId`, Debug
and Release build reports/identities, and `mutated=true`. Public JSON never
contains the staging directory, isolated user home, absolute tool paths, raw
environment variables, or unbounded process output.

### MCP

The same workflows are exposed as:

- `stm32_project_create_prepare(sourceKind, source, destination, framework,
  language, planId, actionDigest)`
- `stm32_project_create_apply(authorizationDigest, authorized)`

MCP uses the runtime-pinned support profile, Toolkit data root, and client-root
containment. It offers no caller-supplied executable, repository, environment,
command, script, timeout, or staging override.

CLI and MCP serialize the same workflow results and typed failures.

## 4. Execution environment and closed support

VS07-B adds an immutable `CreationExecutionEnvironment`; it does not widen the
frozen VS07-A `ToolSupportProfile`. It binds:

- the already-discovered CubeMX executable and content hash;
- the sibling `jre/bin/java.exe` regular-file identity and content hash;
- the CubeMX version and supported command protocol;
- one trusted offline Cube firmware repository and its bounded inventory;
- the existing CubeCLT/GCC/CMake/Ninja facts used by configure/build;
- a digest over all normalized facts.

The repository comes from an explicit trusted CLI configuration or the
canonical CubeMX updater configuration. MCP uses only its startup-pinned
configuration. A repository must be a safe regular directory, contain exactly
the required `STM32Cube_FW_*` family package for the planned source, and expose
parseable package metadata. Ambiguous, redirected, missing, or malformed facts
close with `CUBEMX_REPOSITORY_MISSING`, `CUBEMX_REPOSITORY_INVALID`,
`CUBEMX_PACKAGE_MISSING`, or `CUBEMX_PACKAGE_AMBIGUOUS`.

Observed host fact on 2026-08-23: CubeMX `6.18.1-RC2` is installed at the
registered App Paths location and is safely invokable through its sibling Java
runtime. Its updater configuration names
`C:/Users/ZhangYang/STM32Cube/Repository/`, but that directory and any
`STM32Cube_FW_*` package are absent. This is an `ENVIRONMENT` blocker for a real
positive VS07-B acceptance run. The product must demonstrate the closed
negative behavior; no installation is authorized.

## 5. CubeMX adapter

The CubeMX adapter is internal and accepts a consumed-authorization capability,
not a public boolean. Direct calls without that capability fail with
`CREATION_AUTHORIZATION_REQUIRED`. The orchestration layer may invoke it at
most once per consumed authorization.

On Windows the fixed process shape is the supported CubeMX CLI form:

```text
<CubeMX sibling java.exe> <fixed JVM properties> -jar <STM32CubeMX.exe>
  -q <generated script>
```

The fixed JVM properties set an isolated `user.home`, disable system proxies,
and point HTTP/HTTPS proxies at a non-listening loopback endpoint. The adapter
uses the existing bounded process runner with a closed environment, bounded
stdout/stderr, a timeout, and child-tree termination/reaping. It never uses the
detaching Windows wrapper directly and never emits `login`, `swmgr`, `xcubedl`,
or another network/install command.

The script is generated only from validated values. Supported commands are
`load`/`config load`, project name/path, CMake toolchain, GCC compiler,
structure/library options, `project generate`, and `exit`. Success requires the
expected command echoes, an `OK` for every required command, final `Bye bye`,
exit zero, no `KO`, no timeout, and no truncation. Unrelated updater/ad log
severity text is not the protocol and cannot override a successful protocol.

HAL is the default supported generation mode. LL is supported for `.ioc` input
only when the input already and unambiguously encodes LL driver selection;
MCU/board LL requests fail `CREATION_LL_CONFIGURATION_REQUIRED`. The adapter
does not guess per-peripheral `setDriver` commands.

CubeMX 6.18 exposes no verified project-language command. C is supported.
C++ is supported only for `.ioc` input that already encodes C++ generation and
whose native output validates as C++; other C++ requests fail
`CREATION_CPP_CONFIGURATION_REQUIRED`. The adapter never silently returns C
for a C++ request.

## 6. Native-output validation and ownership

Generation occurs in a random sibling staging directory on the destination's
volume. The validator bounds file count, total bytes, individual bytes, path
depth, and relative-path length. It rejects symlinks/reparse points, special
files, absolute or escaping references, unexpected redirects, missing required
files, malformed UTF-8 metadata, and duplicate/ambiguous build facts.

The existing CubeMX CMake output is the authoritative generated-build model.
The parser accepts a closed subset of its generated CMake variables for
sources, assembly, include directories, defines, target CPU/FPU/ABI flags, and
linker script. It does not evaluate CMake, expand arbitrary commands, or infer
an MCU support matrix. The `.ioc`, linker memory regions, and offline-package
metadata must agree. These facts synthesize the existing schema-2
`.stm32-project.json`; the logical project UUID is deterministically derived
from `planId`, so a newly prepared retry preserves project identity.

Ownership is explicit:

- CubeMX-generated files: every validated native file and hash in
  `.stm32-toolkit/cubemx-ownership.json`;
- Toolkit-managed files: existing `.stm32-toolkit/generated-files.json`;
- user-owned files: `App/` and `Tests/`, initially empty and never generated by
  CubeMX or Toolkit in this slice.

The ownership manifest also binds normalized source facts, CubeMX executable
hash/version, repository/package digest, plan ID, and action digest. It contains
portable project-relative paths only. VS07-C will consume this manifest; VS07-B
does not regenerate or merge an existing project.

## 7. Configure, build, and activation

The existing configure and build workflows are reused rather than duplicated.
They run inside staging: configure once, then build Debug and Release. Both
build identities, map/artifact evidence, and reports must be valid before any
destination activation. No Git repository or commit is created. The planned
workspace must already satisfy existing Git identity requirements; otherwise
prepare closes with the existing Git/configuration error.

The destination remains absent or exactly empty while work is staged. An
exclusive operation lock plus a fresh inventory/action-digest recheck prevents
an activation race. For an absent destination, staging is renamed into place.
For an empty destination, the empty directory is renamed to a sibling backup,
staging is renamed into place, and the backup is removed. Any failure rolls
back to the exact absent/empty state. A rollback failure reports
`CREATION_ACTIVATION_ROLLBACK_FAILED` and preserves bounded evidence; it is not
reported as success. This is destination-level transactional activation, not a
claim that multiple filesystem renames are one syscall.

Staging is removed after a normal failure. Bounded sanitized failure evidence
is preserved outside the project tree. No partial native or Toolkit project is
left at the destination.

## 8. Error semantics

Public failures use the existing typed JSON error envelope and are classified
before product changes. In addition to the environment/package codes above,
the closed set includes:

- `CREATION_PLAN_CHANGED`, `CREATION_AUTHORIZATION_REQUIRED`,
  `CREATION_AUTHORIZATION_INVALID`, `CREATION_AUTHORIZATION_EXPIRED`,
  `CREATION_AUTHORIZATION_CONSUMED`;
- `CREATION_DESTINATION_CHANGED`, `CREATION_EXECUTION_ENVIRONMENT_CHANGED`,
  `CREATION_LL_CONFIGURATION_REQUIRED`,
  `CREATION_CPP_CONFIGURATION_REQUIRED`;
- `CUBEMX_EXECUTION_FAILED`, `CUBEMX_TIMEOUT`, `CUBEMX_OUTPUT_TRUNCATED`,
  `CUBEMX_PROTOCOL_INVALID`, `CUBEMX_NATIVE_OUTPUT_INVALID`;
- `CREATION_CONFIGURATION_FAILED`, `CREATION_DEBUG_BUILD_FAILED`,
  `CREATION_RELEASE_BUILD_FAILED`, `CREATION_ACTIVATION_FAILED`, and
  `CREATION_ACTIVATION_ROLLBACK_FAILED`.

Errors expose portable paths and bounded evidence identifiers, never raw host
output or credentials. A fake or fixture success is `TEST`, not physical or
native `PASS`.

## 9. Verification and acceptance

The Luna implementer owns TDD, focused slice tests, report/ledger updates, and
local commits. Sol independently reviews the full
`bff9cc120923b0e9f2ba29a1b3511f1bcc26ab6e..final-HEAD` diff in a new clean
worktree and runs the plan's exact slice command.

Required product evidence covers authorization replay/concurrency, drift,
direct-adapter rejection, fixed process/script behavior, protocol failures,
native-output validation, both destination states and rollback, Debug/Release
reuse, CLI/MCP parity, client roots, and the real missing-repository observation.
When an appropriate offline package is present, acceptance also requires one
real `.ioc` and one real MCU request to generate/configure/build both Debug and
Release. Until then, implementation may be complete and test-green, but VS07-B
positive native acceptance remains `ENVIRONMENT` blocked and VS07-C product
implementation must not start.

No release matrix, dual-platform audit, coverage gate, hardware operation,
installation, or remote operation belongs to this slice.
