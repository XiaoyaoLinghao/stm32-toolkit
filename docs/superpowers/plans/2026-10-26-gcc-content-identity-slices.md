# GCC content identity implementation slices

Owner/reviewer: primary conversation agent. Implementer: local Claude Code CLI, existing provider. Integration base: `715f316e61821fc96c21a42ebefde213cfab6265`; specification commit: `59546694f2d7b79f6b0b318cc512693640145c6c`.

The approved delivery contract is split for reviewability, not to reduce the required outcome. No release, installation, original-project write or hardware operation is authorized by this plan.

## A. Build, managed flash, debug and IDE handoff

Keep firmware identity schema 1 (Git metadata) and schema 2 (input snapshot with explicit null Git fields and unavailable evidence) strictly decoded. Freshness compares current declared inputs, configuration, artifacts and successful build evidence. Current Git availability, HEAD and dirty state do not decide freshness. Records must still agree with each other; do not erase recorded Git metadata, invent a commit or treat null as clean.

Prior-build reuse validates the prior record according to its own schema, including its recorded provenance, not the current environment's Git availability. A subsequent successful build may produce its new truthful metadata. Invalid or cross-schema records, modified inputs/artifacts and incompatible project/target/toolkit identities still fail.

Schema-2 admission must complete exactly the same content, ELF/segment, MAP and memory checks before it returns a fresh firmware. Managed flash retains authorization, target/probe matching, lease, readback and cleanup behavior. New snapshot flash receipts use schemaVersion 2, the legacy fields plus sourceBaseline and gitEvidence, null Git fields; schema-1 receipt serialization stays unchanged. Handoff strictly validates the matching receipt form.

FreshFirmwareFacts and DebugFirmwareBinding carry nullable Git fields only with the explicit snapshot discriminator/evidence. Snapshot binding serialization adds the two discriminator fields; legacy Git serialization stays unchanged. Do not use str(None), bool(None), a synthetic Git revision, or permissive dictionary matching. Debug read and freshness comparisons bind actual snapshot provenance.

Context removes the Git-only policy refusal, still distinguishing configured capability from a probe/target actually checked. Managed outputs use normal build/flash; external import remains for independently supplied images, never a required no-Git workaround.

Allowed product scope: build/runner.py, probe/flash.py, probe/handoff.py, context.py, debug/model.py, debug/firmware.py, debug/read.py, debug/fault.py; one shared provenance helper if needed. Relevant tests only. Later Target/Monitor serializers remain explicit pending work and must not be described as complete in this slice.

Evidence: author tests and independent review on exact committed head, using synthetic projects and recording/fake probes. Include genuine no-Git and unborn repositories, Git HEAD/dirty/availability changes with unchanged inputs, source/model/header/ELF/MAP mutation, malformed/cross-schema identity/result/receipt, no fake clean state, matching snapshot flash-readback/debug/handoff, unchanged legacy serialization. Run existing build snapshot/runner/context/probe flash/handoff/debug test groups. Hardware PASS is prohibited.

## B. Remaining identity consumers

After A, extend evidence, Target and Monitor contracts with explicit snapshot forms and their strict schema validation; preserve legacy record decoding and hashes. Version a persisted contract only where its existing schema discriminator requires it. Audit and eliminate Git-shaped coercions at producer and consumer boundaries. New tests must cover complete snapshot journeys and rejection of mixed/stale provenance. Do not weaken authorization or replay integrity.

## C. Creation and independent migration delivery

Continue the governing delivery plan after identity acceptance. Neither A nor B is completion of the full user request. New-project creation and Keil output staging/dependency closure need their own bounded contracts and offline end-to-end evidence.
