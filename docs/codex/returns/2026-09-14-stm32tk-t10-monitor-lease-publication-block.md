# T10 publication blocked by cross-operation lease equality

P4 preparation completed its exact in-memory source-intent check and preservation of the full P3 build set, but no firmware edit, build, new acceptance attempt or hardware operation occurred. The before-fixture's successful programming and 300-batch Monitor PASS remain valid. T10/VS10-A remain incomplete.

The installed public command `python -I -B -m stm32_monitor physical publish` returned `INCOMPATIBLE_IDENTITY`, message `physical TestRun and Monitor history identity differ`. It loaded the real TestRun and committed history, then failed `_physical_validate_binding` at `tools/stm32-monitor/src/stm32_monitor/replay.py:1976`, before transcript/reference publication. This is a PRODUCT evidence-contract mismatch, not a new board, sampling or programming failure.

| Field | Expected by current check | Actual | Source |
| --- | --- | --- | --- |
| lease_id | lease-203e4bda26ec46bd9b7424c26f36cfec | lease-8adfb28e758f48759ce46b91594d85f6 | Expected: authoritative Target TestRun root.metadata.lease_id; actual: stored Monitor batch.binding.lease_id |

The existing authoritative loaders read Target run `target-v2-53b0c81ffeb50ab65bd6c0ad815ad273` and all 300 committed batches of Monitor run `6a8508ee-95ec-43f0-a638-73d37d7038c5`. A direct comparison of all 26 binding/context/scenario conditions found only the lease mismatch. Workspace/project/session, probe selector and hash, physical/logical target, flash session, build, ELF, input snapshot, Git head/dirty and origin/import fields matched. Both actual operation leases are already released. No metadata or history was altered to satisfy the comparison.

The serial flow intentionally releases Target ownership and opens a new Monitor connection. A lease belongs to that operation's ownership interval. Requiring equality across those operations conflicts with this flow. Existing publication factories give both sides `lease-01` (`tests/test_physical_publication.py:340,383`), explaining why those fixture cases do not exercise this natural distinct-lease boundary; this does not claim an exhaustive historical test audit.

The installed publisher and current source are identical after CRLF normalization; raw file hashes differ only by line endings. Source SHA256 `09ac247d3be2b60c682233714e081b2dd2f0be36f2bd38408d003890b44097e1`, installed SHA256 `8d6fdefb7d75afcb1c14d490516809926c886f3e82fd687a0d1aca7dccb20a34`.

Minimum correction: preserve both true operation leases, associate their evidence through all existing stable identity fields, and retain strict lease consistency within each Monitor window/transcript/reference. Proposed scope is only publisher and its existing tests; see the matching specification and plan. Product implementation is pending user approval of this newly discovered contract change.

Evidence: `D:\codex-tmp\t10-d3-p4-20260914\before-monitor-publication.json`, `physical-publication-field-comparison.json`, `publisher-source-check.json`, `source-change-intent.json`, `derived-intent-preview.json`, and `p3-preserved\sha256-manifest.json`. No publication retry was attempted after the actual identity failure. Earlier local invocation mistakes (`-m stm32_monitor.cli` only imported the module, and a loader import used the wrong module) were corrected before the real operation/comparison; neither accessed hardware nor produced a physical reference.

The main agent's earlier campaign preparation omitted this cross-operation publication check. Static schema preparation and sampling PASS did not prove end-to-end evidence publication. Subsequent dependent P4 work remains stopped at this concrete boundary; no timer was started and no old authorization reused.
