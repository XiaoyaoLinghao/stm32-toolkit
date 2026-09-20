# Current native coverage result

Qualification accepted base: `ab2fd448a73a319b026a5a6da700b31c2535975f`.
Integrated code/test head before this report: `53c0b78cc2ece6b4d40d53e947ad32321f4c4983`.
Current runtime: `465249dba5560f7c08b1172794fec8fedd9b8d96`.
Native data verdict: **ACCEPTED**. Monitor overall 90%: **MET**.
Toolkit overall 90% and both preferred core 95% targets: **NOT MET**.

| Package | Covered / total branches | Overall and frozen core | More for 90% | More for 95% |
| --- | ---: | ---: | ---: | ---: |
| Toolkit | 11,762 / 13,578 | 86.6254% | 459 | 1,138 |
| Monitor | 2,653 / 2,940 | 90.2381% | 0 | 140 |
| UI (retained separately) | 784 / 810 | 96.7901% | 0 | 0 |

Union18 combines each package's accepted union17 baseline with three complete
passing offline batches: acceptance workflows 5 PASS, DWARF 2 PASS, and hardware
workflows 3 PASS. It adds 56 Toolkit native branches: acceptance 13, DWARF 8,
hardware workflows 33, and probe service 2. Monitor is unchanged. Product bytes,
dependencies and earlier physical evidence remain unchanged.

Two failed initial batches remain preserved and are excluded wholesale from the
raw union. Their failures were test construction defects: a DWARF enum oracle
expected 4 signed bytes while the checked-in ELF specifies 1 unsigned byte; and
an uppercase session identifier was rejected before probe backend dispatch.
Only corrected or previously unexecuted selectors ran again. Two unchanged SVD
PASS cases and one unchanged preflight PASS case remain functional evidence,
without adding their failed-batch raw coverage. The wave therefore retains 13
functional PASS cases while this union accepts 10 complete-batch cases.
Five unobserved hardware source-pair candidates are not counted as coverage.

Independent review verified input hashes, JUnit/process results, candidate-to-
integration test blobs, source identity, and exact complete raw arc unions:
Toolkit 86,690 tuples and Monitor 61,186, with zero missing or extra tuples.
Package file scopes remain 108/18, core scopes 97/16, and denominators 13578/2940.
Non-core forwarding files have no branch opportunities, so overall and core ratios
coincide. UI is never pooled with Python. Monitor retains its documented 2,652
explicit executed-branch entries alongside native summary 2,653; the summary
remains the metric. Residuals are Toolkit 1,816 and Monitor 287 native branches.

The 148 source files across seven roots match after CRLF-to-LF normalization.
Historical creation_environment.py purge entries were handled upstream; there
is no new purge, coverage exclusion, or denominator change in union18.
Native raw SHA-256: Toolkit `86E492CE7CB712AEAC790A377582FFE2BC739A3CFE08590B5FBD9704807E8BAB`;
Monitor `0B442BC9F840CD2F5769A1F448ED2461216A3C74B51E90A379CB29DAA457BCB1`.
Evidence and reviews: `r10/e/n95/union18/` under `D:/codex-tmp/v10b-0918`.
Independent review SHA-256: `00E7D9FB7FA687BD058318B0252C8EE538E1736A5562A231C2C932734654784B`.
Primary review SHA-256: `59FA3CE84746C3FD1653038F4BD580CA8D13F62D44C8BDBE213656EDDF1AE12A`.
Canonical coverage SHA-256: `3B3A747D4E8FDBD7EB2CA0AA4794DCA991DF113A2C0814D8E08095DF4EAE70C6`.

Overall 90% remains mandatory; core 95% remains the user's preferred target.
Earlier A/B physical acceptance and attempt 7 remain unchanged. Seven Windows
native security checks, remaining coverage qualification, final artifacts and
final deployment remain pending. No remote delivery or 1.0 acceptance is claimed.
The remaining-gap review requires a reusable valid public evidence graph before
further implementation; it does not promise that all residual guards are reachable.

Earlier rejected cleanup paths remain untouched. One attempt to remove the six
verified union18 disposable roots (t/a2, t/d1, t/d2, t/h1, t/h2, t/u18) was rejected
before process start by automatic approval review: blocked by policy. Nothing
was deleted and no retry occurred; original evidence remains preserved.
