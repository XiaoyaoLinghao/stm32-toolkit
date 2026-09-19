# Current native coverage result

Accepted wave base: `ab2fd448a73a319b026a5a6da700b31c2535975f`.
Integrated code/test head before this report: `f17fc0dc706ba510c1952817e8cfc21c6711027f`.
Current runtime: `465249dba5560f7c08b1172794fec8fedd9b8d96`.
Native data verdict: **ACCEPTED**. Coverage targets: **NOT MET**.

| Package | Covered / total branches | Overall and frozen core | More for 90% | More for 95% |
| --- | ---: | ---: | ---: | ---: |
| Toolkit | 11,009 / 13,578 | 81.0797% | 1,212 | 1,891 |
| Monitor | 2,567 / 2,940 | 87.3129% | 79 | 226 |
| UI (retained) | 784 / 810 | 96.7901% | 0 | 0 |

The independent native union review verified exact file/arc sets for twelve
inputs per package and unchanged original hashes. Nine Toolkit copies had only
old `creation_environment.py` data purged; current-source measurements replaced
it. Its accepted optional-metadata correction adds two branch opportunities.
No Monitor data was purged. `generation/configure.py` source identity was
verified by equal Git blobs and LF-normalized text despite CRLF byte differences.
The 108/18 overall file scopes and 97/16 core file scopes remain unchanged;
the forwarding files outside the Python core have zero branch opportunities.

Native raw SHA-256: Toolkit
`F94E826F30A8275B2E4A0C0B09D0B20EBEEC2B2E50E614A22990E1325EE92221`;
Monitor `5EBD56BF1AF7D36482C923ED678F988DFCBA0766C730EA478C5D59F4CA76415E`.
Evidence and independent review: `r10/e/n95/union/` under the approved
`D:/codex-tmp/v10b-0918` run root. `primary-result-review.json` supersedes the
historical prepared-entry state without rewriting executed data.

The Monitor continuation has twelve final functional PASS cases. Its first and
third runs remain historical exit-1 events with classified test defects; the
invalid-minimum second run is excluded. Project configuration has 135 unique
PASS cases; two affected cases passed again after the test helper captured
localized `mklink` output as bytes. Those reruns are not additional unique cases.
The later Authority analysis-guards batch is excluded from this native union;
five cases passed and one fixture/reachability claim remains under review.

The remaining-native-qualification plan is active for four non-overlapping
Luna/max test owners. Source scope and denominators remain frozen. Seven native
Windows security checks, final artifact builds and final deployment remain
pending; no new physical or release acceptance is claimed.
