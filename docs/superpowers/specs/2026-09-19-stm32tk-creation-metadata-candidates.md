# Creation package metadata candidate correction

Accepted code/test base: `ab2fd448a73a319b026a5a6da700b31c2535975f`.
Accepted runtime: `547af36ca3d2cbc74729c1958e8dcdfe7cea261c`.
Failing Project qualification candidate: `52068273342588d4dd54364bc831bfbda5555402`.
Primary owns this design, independent review and acceptance. Luna/max owns the
implementation. This necessary correction is within the active local release
goal; it adds no remote, deployment or hardware operation.

## Proven product defect

Project run2 returned 3 PASS / 1 FAIL, exit 1. Public
`discover_creation_environment` rejects a valid JSON-only firmware package.
`creation_environment.py:130` declares package.xml, .pack and package.json in
priority order. Its lstat at line 133 raises FileNotFoundError for absent XML,
which the broad OSError handler at lines 151-152 immediately classifies invalid.
The existing later candidate can never be inspected. The package is present,
regular, correctly named and contains parseable JSON; no hardware was involved.
This contradicts the source's existing candidate list and the parseable-metadata
contract in the approved 0702 authorized-creation design, lines 124-130.

## Three public scenarios

1. The first optional metadata filename is absent: inspect the next existing
   candidate. XML, .pack-as-existing-XML and JSON retain their current priority
   and parser rules. A valid later candidate returns its bound name/version.
2. A candidate exists but is malformed, unreadable or oversized: retain the
   typed CUBEMX_PACKAGE_INVALID refusal. Do not hide corruption by selecting a
   lower-priority valid file. Other file/directory/reparse protections remain.
3. No usable metadata candidate exists: fail CUBEMX_PACKAGE_INVALID. Directory
   naming alone is not parseable package metadata. A version may still fall
   back to the existing directory convention after actual metadata was parsed.

Handle FileNotFoundError narrowly around lstat of the optional candidate. A
file disappearing during read is still an invalid observed fact, not permission
to fall through. All other I/O failures retain their existing classification.
The query remains read-only and produces no generated project or repository
mutation. Public models, error codes, authorization and digest rules stay fixed.

## Scope and evidence

Only tools/stm32-toolkit/src/stm32_toolkit/creation_environment.py and its
existing test_creation_environment.py are implementation-owned. Keep the
failing public JSON test and add the smallest public tests distinguishing later
candidate fallback, no metadata, and malformed-priority rejection. Reuse the
existing fixture. No generic framework, private-only tests, format expansion,
new package discovery backend, hardware or unchanged release matrix.

Run the affected environment test file once at the corrected source, then the
previously unrun Project functions. The first 3 PASS remain historical but the
changed discovery function justifies its affected regression. Save native raw
data on any normal failure. Old creation_environment.py arcs must be removed
from copies before final native union; no stale line mapping may be reused.
Unaffected product/hardware evidence remains valid within its original scope.
