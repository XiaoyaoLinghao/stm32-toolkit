# Current native coverage result

Qualification accepted base: `ab2fd448a73a319b026a5a6da700b31c2535975f`.
Integrated code/test head before this report: `c789cb0ca87ac3ca5c996008bac0d34be3c04d26`.
Completion-graph plan base: `79d197cbdba28f0ab17a9fbe0b188b4ce91393ae`.
Current runtime: `465249dba5560f7c08b1172794fec8fedd9b8d96`.
Native data verdict: **ACCEPTED**. Monitor overall 90%: **MET**.
Toolkit overall 90% and both preferred core 95% targets: **NOT MET**.

| Package | Covered / total branches | Overall and frozen core | More for 90% | More for 95% |
| --- | ---: | ---: | ---: | ---: |
| Toolkit | 11,769 / 13,578 | 86.6770% | 452 | 1,131 |
| Monitor | 2,653 / 2,940 | 90.2381% | 0 | 140 |
| UI (retained separately) | 784 / 810 | 96.7901% | 0 | 0 |

Union19 adds a public completion-artifact matrix to each package's complete
accepted union18 raw baseline. One selected test passed in 88.25 seconds and
exercised ten semantic variants: a valid completion plus malformed or mismatched
root, envelope, artifact, media type, and canonical JSON representations. Each
variant starts from a valid persisted Diagnostic/Monitor/evidence graph and
checks the returned outcome, public reload, revision, event, and preserved prior
evidence. The matrix adds seven Toolkit native branches; Monitor is unchanged.
Only test code changed. Product bytes, dependencies and earlier physical
evidence remain unchanged.

Union18 retains its earlier 56-branch Toolkit increase and 13 functional PASS
cases, of which ten belonged to complete passing raw batches. Its two failed
initial batches remain preserved and excluded wholesale. No earlier selector
was rerun for this report or union.

Independent review verified input hashes, JUnit/process results, candidate-to-
integration test blobs, source identity, and exact complete raw arc unions.
The complete output raw databases contain Toolkit 86,715 tuples and Monitor
61,225, with zero missing or extra tuples against their input unions. Package-
scoped counts within those databases are 74,912 and 16,461 respectively; output
raw data was not filtered to produce those counts. JSON reports use the frozen
package scopes of 108/18 files and core scopes of 97/16. Branch denominators
remain 13578/2940. Non-core forwarding files have no branch opportunities, so
overall and core ratios coincide. UI is never pooled with Python. Monitor
retains its documented 2,652 explicit executed-branch entries alongside native
summary 2,653; the summary remains the metric. Residuals are Toolkit 1,809 and
Monitor 287 native branches.

One initial report assertion incorrectly treated every normalized JSON pair as
a literal raw arc. The retained raw observations resolve it: diagnostic workflow
JSON pair 1472->1480 represents raw 1476/1477/1478->1480; the other six new pairs
are literal observations. This was a report representation correction, with no
test failure, rerun, synthetic coverage, or changed denominator.

The 148 source files across candidate, review and integration roots match the
frozen source registry after CRLF-to-LF normalization. Historical
creation_environment.py purge entries were handled upstream; union19 has no
new purge, coverage exclusion, or denominator change.
Native raw SHA-256: Toolkit `EB47F1C5DFDA2FEF02B23EAC7C7910D26B3066DBE8EDAA42864092550A5BBFEA`;
Monitor `3DA44F960A1FF374D267D3D793B1104A8C816189466B68A7561234060FDC4877`.
Evidence and reviews: `r10/e/n95/union19/` under `D:/codex-tmp/v10b-0918`.
Independent review SHA-256: `A669B9BBC0CB7B87A868FC1D2A1C77D073BC3F1733A7BF192CACBD76F97E3508`.
Primary review SHA-256: `8271DC435AB527FA79011DC04A4530B8D10E02AF7F6B190FE1CD08F829EC040D`.
Canonical coverage SHA-256: `BB0DA1C56B5B3CAC3243F8478AAF3D747898E2AA98087306B65CD5D1245ECBC8`.

Overall 90% remains mandatory; core 95% remains the user's preferred target.
Earlier A/B physical acceptance and attempt 7 remain unchanged. Seven Windows
native security checks, remaining coverage qualification, final artifacts and
final deployment remain pending. No remote delivery or 1.0 acceptance is claimed.
Further implementation requires a coherent public-contract scenario with a
valid construction and observable state/resource invariants; static residual
counts are not a promise that all guards are reachable.

Earlier rejected cleanup paths remain untouched. One attempt to remove the two
verified union19 disposable roots (t/cg1 and t/u19) was rejected
before process start by automatic approval review: blocked by policy. Nothing
was deleted and no retry occurred; original evidence remains preserved. Read-only
verification confirmed both roots still exist, recorded in union19/cleanup.json.
