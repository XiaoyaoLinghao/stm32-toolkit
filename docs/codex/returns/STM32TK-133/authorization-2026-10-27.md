# v1.3.3 frozen-candidate authorization

Date: 2026-10-27. Disposition: **USER_APPROVED_EXCEPTION**.

The user explicitly answered “仅批准此 v1.3.3 候选例外并发布 Latest” to the
candidate-specific question identifying frozen source
`46ca09084bbe39f670714d19d7d55f9365ef06be`, the reproducible 13 files and the
following disclosed limitations. This authorizes non-forced source/tag push and
publication of that exact package as Latest. It does not approve another candidate,
change permanent gates, or turn unmet/skipped checks into PASS.

- Toolkit overall 15,211/18,418 = 82.5877%, risk 14,157/17,176 = 82.4231%, below 90%.
- Monitor risk 3,292/3,564 = 92.3681%, below 95%.
- Original Monitor performance failure retained (124.9428 ms p95 against 50 ms);
  bounded old/candidate monitor-only comparisons passed at 21.4292/19.5793 ms.
  The original cause is not established and no full-file post-comparison rerun is claimed.
- Source-bound evidence reuse, platform and historical-data skips are explicit;
  this is not a final-head complete repository rerun.
- Actual CubeMX vendor generation is unverified because the offline package is unavailable.
- Final actual installation and independent VS Code testing remain user-owned,
  **USER_VALIDATION_PENDING**. Original firmware projects and hardware are not accessed.

The two official builds and extracted bundle check passed before the question.
Windows ZIP: 116,350,730 bytes, SHA-256
`52829b90bdd2ebf5b8dd61825ba7c423f5679597b23a35487bf3f8ca4c51378a`.
See [frozen candidate](candidate-build.md), [version review](version-review.md)
and [native evidence mapping](release-evidence.json). The candidate report retains
its pre-approval state; this later decision supplies its disposition.

Primary owns release orchestration and independent verification. Claude Code CLI
continues to own any code/test or user-guide changes. Publication is not yet claimed;
the later delivery record will bind observed remote identities and downloaded hashes.
