# GCC delivery contract correction

Accepted integration base: `715f316e61821fc96c21a42ebefde213cfab6265`.
The user confirmed and authorized implementation of these product requirements:

1. Existing Keil projects with source migrate into a separate, independently
   buildable GCC/CMake project, then use the normal build/flash route.
2. Newly created STM32 projects use that same GCC build/flash route.
3. Git is optional traceability, never mandatory eligibility for these workflows.

Primary owns architecture, bounded plans, orchestration, independent complete-diff
review and acceptance. Local Claude Code CLI using the existing provider/model
owns implementation and tests. No Codex implementation subagents. No original
firmware/user-test-copy edits, hardware, runtime/global installation, or remote
publication. The interrupted v1.3.3 version work remains preserved separately;
release is paused until this corrected core delivery is accepted.

## Common identity and continuation

Fresh source/configuration/dependency snapshots, target/preset/model, actual
ELF/MAP bytes and successful build evidence govern firmware freshness. Existing
Git evidence remains truthful optional metadata. Never invent a commit or map
null into the string "None" or false/clean. Git initialization, a commit containing
unchanged build inputs, missing Git, unborn HEAD and unrelated dirty files cannot
alone disqualify otherwise current firmware. Changed relevant inputs/artifacts,
invalid/cross-schema evidence, wrong target/probe and absent action authorization
must still fail before effects. Old schemas keep explicit decoding rules; no
blanket nullable-field acceptance. Downstream debug/handoff/Monitor/Target bindings
must carry the actual content identity rather than impose a hidden Git prerequisite.

## Independent migration delivery

Source and destination are explicit, disjoint directories. The source is read-only;
the destination is absent or verified empty and is never silently overwritten.
Planning works without Git, binds input inventory, selected target, exact changes,
destination and migration choices, and displays missing decisions. Apply revalidates
that plan before staged writes and publishes only complete output. Preserve source
layout/required dependencies and licenses, supply GCC startup/linker/CMake/presets/
Toolkit model and appropriate editor guidance. Output build inputs cannot depend
on the original source directory. Missing or unsupported dependencies are reported
before claiming success. Existing imported-firmware support remains independent;
it is not a workaround required for the toolkit's own GCC output.

Encoding preparation applies only to reviewed destination copies and includes
necessary headers. Explicit WFI normal-return repair is a source-intent decision
shown in the migration diff, not a claim of binary equivalence or a requirement
for Keil disassembly. Unknown assembly remains unsupported. Reuse plan/input
binding and existing authorization scope rather than create a separate approval
framework. Generate/configure/build/physical flash outcomes remain distinct.

## Evidence

Each slice has one exact CodeHead, Claude-executed affected test groups and an
independent primary review in a clean checkout. Use real GCC compilation for the
delivery integration and recording/fake probe providers for offline hardware
workflow assertions; those are not physical PASS. Verify zero original-file changes,
destination collision/failure behavior, source/ELF tampering refusal and recovery
ownership. Complete two offline journeys, including an isolated output-only build
for migration, before claiming software completion. Real hardware and final user
installation/VS Code remain separately owned and authorized. No release exception
is inherited from a previous frozen candidate.
