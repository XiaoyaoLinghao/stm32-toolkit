# GCC delivery implementation sequence

Governing specification: ../specs/2026-10-26-gcc-delivery-contract.md.
Accepted integration base: `715f316e61821fc96c21a42ebefde213cfab6265`.
User authorized starting the correction; separate implementation-plan approval
is waived. Primary reviews and accepts each slice before integration.

1. Inventory hard Git dependencies and record schema/consumer contracts. Verify
   Claude native PowerShell registration and exact harmless execution, then use
   read-only/file-only authoring separately from exact-command verification.
2. GCC-CONTENT-IDENTITY: preserve strict content/target/artifact admission while
   supporting snapshot firmware; propagate explicit source provenance through
   affected downstream consumers. Git metadata is optional and cannot gate
   unchanged build inputs. Version remains unchanged during the software slices.
3. GCC-CREATION: remove the creation-prepare Git prerequisite and verify existing
   staged create/configure/build activation without Git or source damage.
4. GCC-MIGRATION-DELIVERY: introduce explicit destination delivery with input
   snapshot planning, source-preserving staged adaptation/configuration and
   complete dependency copying. Integrate reviewed comment normalization and
   bounded source-intent repair into destination preparation. Validate precise
   portable output paths and existing fixed-section/startup/layout rules.
5. GCC-DELIVERY-INTEGRATION: run both complete source-to-GCC-to-offline-flash
   journeys, output-only clean rebuild, negative integrity/authorization cases,
   and related regression files. Sync CLI/MCP/VS Code/Skill guidance to actual
   supported paths; retain historical evidence and reported limitations.
6. Freeze accepted software and report actual outstanding physical/user checks.
   Resume version alignment/release only after the product correction is ready;
   do not publish the interrupted partial v1.3.3 candidate.

Owner/environment: Claude implementation and tests; primary independent review,
run-local orchestration and acceptance. Existing Windows PowerShell7, CPython3.12,
ARM GCC/CMake/Ninja; tests under independent short D:/codex-tmp roots. No shared
mutable test roots, global policy changes, original-project writes or hardware.
