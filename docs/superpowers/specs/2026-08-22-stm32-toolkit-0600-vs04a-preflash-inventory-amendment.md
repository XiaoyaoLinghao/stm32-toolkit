# VS04-A Pre-flash Inventory Amendment

## Decision

This amendment replaces the live pre-flash inventory-discovery requirements in the original VS-04
design and production-composition amendment. It follows two rejected implementations whose fake
backends hid an impossible source-change sequence: after rebuilding fixed firmware, the board still
runs old firmware and cannot report the new build's inventory before it is flashed.

The accepted product base remains `5d6e06845a2c1d991181c5ff84a9194dfcc49c8c`.

## Authorized inventory contract

Physical preparation requires a non-empty, unique, canonical, complete `caseIds` tuple. Empty means
invalid; it never means "discover all". Case IDs are user-selected behavior, not caller-provided
identity facts.

Toolkit derives the expected new-firmware `EvidenceIdentity` from validated Project v3 and fresh
build facts, then computes:

```text
inventory_digest = calculate_inventory_digest("target", expected_identity, caseIds)
```

The action digest therefore binds the new build, ELF, input snapshot, target device, exact complete
case inventory, transport, probe/board identity, timeout, and project/session identity without
requiring the old firmware to know anything about the new one.

## Revised prepare sequence

Preparation:

1. validates Project v3 and fresh build facts;
2. derives transport/support configuration and expected new-firmware identity;
3. opens one non-halting OBSERVE supervisor/client only to confirm physical board, MCU, target ID,
   and probe hash;
4. does **not** open a Target test transport and does **not** read a live inventory frame;
5. computes the expected inventory digest from the new identity and required complete case IDs;
6. persists the canonical prepared intent.

The board may contain unrelated, failing-before, fixed-after, blank, or otherwise different
firmware during prepare. Hardware identity must match; runtime firmware identity is deliberately not
a prepare precondition.

## Revised execute sequence

Execution atomically consumes the digest, revalidates Project/build/ELF/snapshot/transport/cases,
opens the single MODIFY supervisor/client, and revalidates physical target identity. It performs no
pre-flash Target inventory discovery.

The same client flashes the authorized firmware. The physical Target run then opens the authorized
transport and treats its first inventory frame as post-flash proof. That frame must contain:

- the exact authorized new-firmware identity;
- exactly the authorized complete case IDs;
- the precomputed inventory digest.

The run-start selection must equal the same complete case tuple. Any mismatch is an identity or
inventory failure after an authorized flash, not a domain test failure. The digest remains consumed,
valid flash/diagnostic evidence remains append-only, and no authoritative TestRun root is created.
A new preparation and explicit authorization are required for another MODIFY attempt.

## Acceptance that prevents recurrence

The production-shaped test must keep the fake board on failing-before firmware while preparing the
fixed-after digest. Prepare must succeed without Target transport traffic. Execute must show this
order:

```text
consume -> static/hardware preflight -> one flash -> board identity changes to fixed-after
-> first inventory frame validates fixed-after identity/cases/digest -> run -> publication
```

A fake backend that reports current build identity before flash is invalid test evidence. Tests also
cover post-flash old identity, wrong/extra/missing cases, wrong inventory digest, and transport
failure: all consume authorization, publish no TestRun root, and require a new digest.

