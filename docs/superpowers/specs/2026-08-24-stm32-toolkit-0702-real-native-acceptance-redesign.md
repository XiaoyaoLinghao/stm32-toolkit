# STM32 Toolkit VS07-B Real Native Acceptance Redesign

**Status:** Approved under the user's standing approval waiver

**Date:** 2026-08-24

**Accepted base:** `bff9cc120923b0e9f2ba29a1b3511f1bcc26ab6e`

**Redesign input:** `0553c6e71812d648d0642b2f9d66688aa8cd0084`

**Owner/reviewer:** GPT-5.6-sol primary agent

**Implementation owner:** the same sole GPT-5.6-luna/max VS07-B implementer

## 1. New authoritative native facts

The user installed the official package at
`C:/Users/ZhangYang/STM32Cube/Repository/STM32Cube_FW_F4_V1.28.3`. It contains
`package.xml`, Drivers, Projects, Documentation, and the F4 HAL driver. The
Repository also legitimately contains downloaded archives
`stm32cube_fw_f4_v1280.zip` and `stm32cube_fw_f4_v1283.zip`.

Sol ran isolated probes in `C:/tmp/p0702-native-capture-r5` through `r8`.
Those probes established:

- treating archive names as package directories makes the current environment
  resolver reject an official CubeMX repository;
- without isolated `TEMP` and `TMP`, JNA cannot extract `jnidispatch.dll` and
  CubeMX exits 1 before reading the script;
- the normalized identity `STM32F429ZITX` is accepted by `load` but later
  reported unsupported by the CMake generator; the installed descriptor
  `db/mcu/STM32F429ZITx.xml` binds the required native token through
  `Mcu/@RefName`;
- forward-slash Windows `project path` values produce duplicated absolute
  source paths and omit `sysmem.c` and `syscalls.c`; a quoted native Windows
  path generates both files and portable `${CMAKE_CURRENT_SOURCE_DIR}` lists;
- CubeMX creates `<project-path>/<project-name>`, not directly in the supplied
  project path;
- the successful native stdout contains 425 lines. Required protocol events
  are the eight exact command echoes in order, `OK` after the first seven, and
  `exit` followed by `Bye bye`. Normal INFO/WARN/ERROR network log lines occur
  between those events. Stderr contains a Java preferences warning even on
  success;
- the real nested CMake define list contains the exact configuration expression
  `$<$<CONFIG:Debug>:DEBUG>`, and the IOC package fact is
  `STM32Cube FW_F4 V1.28.3`;
- the real native project root contains 1,458 files and uses the verified
  global/subdirectory CMake dialect.

The probe did not touch user projects, hardware, Git remotes, or installation
state. Its captured stdout, stderr, generated IOC, and CMake files are the
source evidence for the committed sanitized fixtures.

## 2. Frozen environment and native-token boundary

Repository discovery considers only matching directory entries as package
candidates. A matching regular `.zip` archive is ignored. A matching symlink,
junction, special file, unsafe directory, or ambiguous safe directory still
fails closed. Exactly one safe F4 package directory is required.

For an MCU request, `CreationExecutionEnvironment` resolves one native MCU
descriptor below the verified CubeMX `db/mcu` directory by case-insensitive
filename identity. The descriptor is a bounded, non-reparse regular XML file;
its exact `Mcu/@RefName` must case-fold to the normalized request value. The
environment stores and digests `native_source_token`, descriptor-relative path,
and descriptor SHA-256. Missing, duplicate, malformed, redirected, oversized,
or mismatched descriptors close with a typed execution-environment error.

Board source spelling remains the validated board token. IOC generation uses
the already-authorized IOC bytes. No caller can override the resolved native
token, repository, descriptor, child environment, or paths.

The closed child environment adds `TEMP` and `TMP`, both set to one isolated
directory below the external control root. The directory is created before
launch and removed on every exit. Ambient temp, credentials, proxies, and user
home remain excluded.

## 3. Frozen adapter ownership and script boundary

The apply layer creates one same-volume generation container beside the final
destination. CubeMX receives:

- project path: the quoted native Windows spelling of the container;
- project name: the validated destination leaf;
- MCU source: the environment-bound native token.

The only accepted native output root is
`<generation-container>/<project-name>`. It must be a safe non-reparse
directory, the container must contain no other entries, and the project root
must stay on the same volume. Native parsing, ownership-manifest creation, and
the host-path scan run while that child remains under the generation container.
The validated child is then atomically renamed to a distinct sibling activation
staging root and the now-empty generation container is removed before Toolkit
configuration or either build begins. Configuration and both builds operate on
the activation staging root; final activation moves that root to the planned
destination and has no parent generation container left to clean up.

The adapter owns its control root with one `try/finally` lifecycle. It never
returns a live control path. Setup errors, IOC drift, invalid runner results,
nonzero exit, timeout, truncation, protocol failure, native validation failure,
configuration/build failure, and activation failure all leave no control root.
Apply owns only generation-container and project-root cleanup.

IOC bytes are opened/read once under the existing safe-file checks, bounded to
the IOC limit, hashed, and the same byte object is written to control input.
There is no hash-then-reread race.

## 4. Frozen protocol evidence

Tests commit a static sanitized transcript derived from r8. Timestamps, PIDs,
user paths, and absolute temp roots are replaced by fixed literals, but event
order, representative log noise, all required echoes/responses, the Java
preferences warning, and exit tail are retained. No test helper may generate
responses from the script under test.

Protocol parsing consumes stdout order only. Stderr is separately bounded and
retained for failure classification. Exact `KO`, missing/duplicate/reordered
command echoes, missing/duplicate `OK`, missing/duplicate `Bye bye`, nonzero
exit, timeout, or truncation fail. Log lines, including known offline connection
errors, do not by themselves establish success or failure. Success additionally
requires the exact output root and strict native-project validation, so exit 0
plus `OK` cannot bless the incomplete r6 tree.

## 5. Frozen native validation boundary

Validation inventories and bounds the native project before any whole-file
host-path scan. Subsequent scans read only inventory entries already bounded by
per-file and aggregate limits.

The global parser consumes the actual r8 CMake/IOC facts. It accepts the exact
`$<$<CONFIG:Debug>:DEBUG>` define expression as configuration metadata and
does not publish it as an unconditional common define. Other generator
expressions remain invalid. Package comparison canonicalizes separator spelling
and requires exact family and version agreement between
`STM32Cube FW_F4 V1.28.3` and the bound environment.

All path values must resolve inside the native project root. The real portable
`${CMAKE_CURRENT_SOURCE_DIR}/../..` lists pass. Absolute generated source paths,
missing listed sources, the incomplete r6 tree, unbounded files, unsafe CMake,
and mixed dialects fail closed.

The real F4 include list declares both
`Drivers/STM32F4xx_HAL_Driver/Inc` and its compiler-significant child
`Drivers/STM32F4xx_HAL_Driver/Inc/Legacy`. The project model preserves both
include declarations. Build-input inventory treats the exact same portable
directory reached first through recursive parent inventory and later through
that explicit child declaration as one idempotent evidence traversal. It does
not discard either compiler include path and does not relax case-fold
collisions, alternate aliases, redirects, escapes, or non-directory failures.

The existing build identity contract also requires the planned workspace to
have a resolvable local Git HEAD. The public plan remains read-only and does
not invent repository state. Prepare validates the workspace with the existing
bounded Git-evidence primitive before environment discovery or authorization
record creation; a missing, unborn, or invalid repository returns the existing
`BUILD_GIT_INVALID` code and bounded rule. Product code never runs `git init`,
creates a commit, changes Git configuration, or contacts a remote. Positive
native acceptance creates an isolated local repository and initial commit as
test setup, with command-scoped identity and no remote, before invoking the
public plan/prepare/apply path.

Two local attempts to reconstruct the CubeMX runtime from memory regions did
not converge: after resolving startup/newlib symbols, real linking still found
absolute location-counter errors in the reconstructed heap/stack sections.
That reconstruction strategy is superseded.

For a native CubeMX project, CubeMX remains the sole owner of the device-level
linker/runtime script it generated. `NativeProjectModel.linker_script` is
published as an optional, portable `generation.nativeLinkerScript` field in the
schema-3 manifest. It must be a bounded, non-redirecting regular file already
present in the strict native inventory and CubeMX ownership manifest. Toolkit
does not copy, reinterpret, or generate `linker/stm32tk.ld` for that native
mode. It owns the CMake target, presets, editor configuration, managed-file
manifest, build identity, and drift checks; its CMake target references the
bound native linker and uses compiler-managed start files, the installed
`nano.specs` and `nosys.specs`, and `libm`.

The native linker is a configuration input and a build-snapshot input, so its
exact bytes affect configuration and firmware identities and drift is rejected.
The managed-file manifest omits the generic linker target in native mode and
never mislabels vendor bytes as a Toolkit template. Projects without
`generation.nativeLinkerScript` retain the pre-redesign generic linker and link
behavior byte-for-byte. This is one mode switch on an existing public model,
not a second parser or build backend.

Two real runs against that native-linker boundary configured and built both
firmware presets, then Windows refused the post-build `rmdir` of the now-empty
generation container. A bounded one-second retry did not converge; both runs
restored the exact absent destination and removed all residue. Post-build
container cleanup is therefore superseded by the pre-build relocation boundary
above, not extended with another retry.

The pre-build cleanup still rechecks that the owned generation container is
empty before every attempt and retries only its `rmdir` at most 20 times with
50 ms between failed attempts. An entry appearing in the container fails
immediately. Relocation or cleanup failure occurs before configuration/build or
destination mutation, removes both owned roots, and returns the existing
bounded activation/staging failure semantics. Renames, backup cleanup, locks,
destination validation, and all other failures are never retried. The native
model and ownership paths remain portable and byte-identical across relocation;
no parse, host-path scan, or arbitrary vendor input read is repeated afterward.

## 6. Acceptance and sequencing

The implementer must first prove every old defect RED, then implement this
replacement boundary and run the exact VS07-B slice. After unit/integration
GREEN, it must run one real MCU creation using `STM32F429ZITx` and one real IOC
creation using the captured r8 IOC in fresh disposable roots. Both must parse,
configure, build Debug and Release, activate, and leave no control/container or
CubeMX/Java process. This is native software evidence, not hardware evidence.

Sol reviews the complete accepted-base-to-final-head diff in a new clean
worktree, repeats the exact slice and both disposable native scenarios, and
issues the only acceptance verdict. VS07-C remains frozen until that verdict is
`ACCEPTED`. No push, PR, merge, tag, release, install, hardware, expanded Python
support, release matrix, dual-platform audit, or coverage gate is authorized.
