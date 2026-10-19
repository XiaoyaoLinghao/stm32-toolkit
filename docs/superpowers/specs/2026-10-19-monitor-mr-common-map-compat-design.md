# GNU common-symbol MAP preamble compatibility

Accepted base `c97d3e8753537809e9458ec050076220dcfa7243`; product bytes before this slice are `41b5cc37f60d26da2ed323dd7b934fc980b3df61`. The user requests real MR stable firmware programming/Monitor testing through the existing Toolkit, with further development approval already granted. A necessary bounded correction to the existing GNU MAP adapter is authorized by that scope; no new compiler/programmer backend is introduced.

Primary owns specification, orchestration, full-diff review and acceptance. One gpt-6-sol/max implementer owns only map_file.py, its focused tests/generic fixture and implementation report. Independent gpt-6-sol/max reviewer reads the complete accepted-base to frozen-head diff; author cannot accept. Branch `codex/monitor-mr-map-compat`, clean initial tree `D:\codex-tmp\mr1019\toolkit-fix`. No primary product-code exception. No remote/version/install/browser/hardware action is granted to this slice's implementer.

## Three runnable scenarios

1. A valid GNU ld MAP with `Allocating common symbols` informational preamble, including long wrapped names followed by one hex size and an object path, parses normally. Only actual declared regions and output sections affect memory usage. Real MR -fcommon MAP/ELF replay must pass without rewriting either artifact.
2. Real wrapped output sections in the authoritative memory map still parse and reconcile against ELF flags, address, size and NOBITS evidence. Region order, overlap, unknown/missing ELF section and all current VMA/LMA accounting remain unchanged.
3. A malformed output row, malformed continuation or duplicate section remains BUILD_MAP_INVALID. An informational common header placed after memory configuration/region or output-section parsing must not hide bad authoritative rows; reject such a misplaced header rather than entering skip mode. Legacy accepted headerless inputs retain their current semantics.

Non-goals: general MAP grammar rewrite, accept arbitrary ambiguous rows, edit MR variable declarations or -fcommon behavior, normalize/sanitize produced MAPs, change memory accounting/error ABI, compiler switches, build identity, ELF/flash validation, UI, dependencies, version or new engines.

## Frozen parser behavior

The current _WRAPPED_SECTION_NAME_RE matches the bare long symbol in the common table before memory configuration and then mistakes its indented size/object continuation for an output section. Treat only the recognized common-symbol preamble as informational context. This context may begin only before any Memory Configuration header, declared region or output section; resume ordinary strict parsing at GNU's following known structural heading (including Memory Configuration, Discarded input sections, Linker script and memory map as appropriate). Do not broadly ignore indented/unrecognized rows in the actual section area. No pending output-section continuation may be discarded to enter/leave this preamble. EOF or missing actual regions/sections still fails by the existing stable error rules.

Preserve the parser's existing public signatures, immutable ELF evidence, bounded stable details, duplicate/malformed/unknown checks and interval-union accounting. Do not change firmware to avoid a valid common-symbol table.

## Proportionate evidence

Implementer runs new positive/negative parser regressions, the affected MAP/ELF/build-runner integration selection and a real MR MAP/ELF replay using the current installed GNU result under mr1019/p. Exact artifact hashes, model regions, commands/stdout/exit and code head must be recorded; provisional MR replay is not a final MR build identity or physical PASS. Keep committed fixtures generic; do not embed private MR source or full MAP into the public Toolkit repository. Main independently verifies frozen code/tests in an exact clean review tree, reviewer checks complete diff, then primary supplies the accepted Toolkit root/head to firmware and operations owners. The MR final public build must run on that accepted code.

All run artifacts remain under D:\codex-tmp\mr1019, with TEMP/TMP/TMPDIR and caches bound before execution. Logs and necessary failure evidence are retained; dispose only owned redundant temporaries once safe. Any policy-denied path is not retried or bypassed. Browser and physical testing remain separate, owned by primary after both firmware and scripts are accepted.
