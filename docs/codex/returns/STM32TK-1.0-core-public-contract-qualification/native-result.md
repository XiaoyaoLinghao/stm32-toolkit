# Current native coverage result

Accepted code/test base: `ab2fd448a73a319b026a5a6da700b31c2535975f`.
Current runtime: `547af36ca3d2cbc74729c1958e8dcdfe7cea261c`.
Native data verdict: **ACCEPTED**. Coverage targets: **NOT MET**.

| Package | Covered / total branches | Overall and frozen core | More for 90% | More for 95% |
| --- | ---: | ---: | ---: | ---: |
| Toolkit | 10,837 / 13,576 | 79.8247% | 1,382 | 2,061 |
| Monitor | 2,554 / 2,940 | 86.8707% | 92 | 239 |
| UI (retained) | 784 / 810 | 96.7901% | 0 | 0 |

The independent seven-input union review verified exact file/arc sets and
unchanged original hashes. Only older Toolkit `generation/configure.py` arcs
were removed from copies; the corrected source's measured arcs were retained.
The Toolkit decrease from the prior measurement is a current-source recording
gap, not a failed functional regression. CRLF/LF equivalence for `replay.py`
was separately proved; its raw bytes were not described as equal.

Native raw SHA-256: Toolkit
`F862E0F96C2B483AA9993535C124C2A7809A386BF7E26068BD822512DF97B646`;
Monitor `EFB7D66F489C7F21EF847323B7504BFF4C60F9190D8DB7BA4F877DEB85976D40`.
Evidence and independent review: `r10/e/core95/union/` under the approved
`D:/codex-tmp/v10b-0918` run root. `primary-result-review.json` supersedes the
historical prepared-entry state without rewriting executed data.

The remaining-native-qualification plan is active for four non-overlapping
Luna/max test owners. Source scope and denominators remain frozen. Seven native
Windows security checks, final artifact builds and final deployment remain
pending; no new physical or release acceptance is claimed.
