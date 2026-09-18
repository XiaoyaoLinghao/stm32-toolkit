# STM32TK 1.0 local release: TestRun publication qualification

## Scope

This bounded, test-only slice qualifies the first three remaining public TestRun publication scenarios in the 1.0 local release plan:

1. Target replay publication rejects a valid manifest identity or terminal state that differs from the descriptor. This scenario has two focused nodes.
2. Target replay publication rejects a descriptor parent whose valid import_workspace_id contradicts the import binding supplied to the public publisher.
3. Host authoritative reload rejects duplicate JSON keys in the stored manifest provider payload.

The first two cases are the two minimal forms of the plan identity/state disagreement scenario. The descriptor and manifest inputs remain structurally valid at their public model boundaries. Each replay refusal asserts EVIDENCE_CORRUPT, records the expected parent-validation read stage, proves that the collector directory/write seams and envelope publication are not reached, and compares every evidence-store and results-tree file byte-for-byte before and after the call. The parent-binding case reaches the binding check before artifact reads. The Host case uses the public Repository.load path and the existing stored-byte provider seam; it asserts one manifest read, EVIDENCE_CORRUPT, and unchanged root, envelope, manifest, and evidence bytes.

The tests reuse _bundle, _fixture, _publisher, and the public publish_target_replay/Repository.load entry points. Scenario 4, the non-boolean PublishedTestRun.public_data selector, was intentionally skipped. No private decoder or validator was called directly, no generic mutation matrix was added, and no product source, integration code, build, package, deployment, hardware, or remote state was changed.

The accepted integration base is 4e86a1fb1e2fed2a14852cd410f2664f2970a06b. Product imports were pinned to the frozen verification sources at product revision 15b1a70e9bd684285da5557104deff529f537e49:

    D:\codex-tmp\v10b-0918\r10\verify\tools\stm32-toolkit\src
    D:\codex-tmp\v10b-0918\r10\verify\tools\stm32-monitor\src

The implementation code head before this report commit was 87d7b4cf9dfc4286a3920d0249ec10b073fee689. This report intentionally records no report-commit SHA.

## Added qualification nodes

- tools/stm32-toolkit/tests/test_target_replay_publication.py::test_target_replay_publication_rejects_valid_identity_contradiction_before_publication changes only the valid build digest in a replay manifest. The public publisher reads the two descriptor artifacts, raises EVIDENCE_CORRUPT, and performs no collector or envelope publication.
- tools/stm32-toolkit/tests/test_target_replay_publication.py::test_target_replay_publication_rejects_valid_state_contradiction_before_publication supplies a valid passed manifest and passed case tuple against the failed descriptor. It reaches the descriptor state refusal before stream matching or publication.
- tools/stm32-toolkit/tests/test_target_replay_publication.py::test_target_replay_publication_rejects_contradictory_parent_binding_before_publication rebuilds the descriptor envelope with a different valid SHA-256 import binding. The public publisher raises EVIDENCE_CORRUPT before reading parent artifacts or publishing the parent, collector output, or root.
- tools/stm32-toolkit/tests/test_testing_publication.py::test_repository_rejects_duplicate_json_keys_from_authoritative_manifest_provider publishes a valid Host run, then makes the stored manifest provider return canonical JSON with a duplicated run_id key. Public authoritative reload raises EVIDENCE_CORRUPT without repairing or republishing the record.

## Verification

The final focused invocation was run from D:\codex-tmp\v10b-0918\r10\tp after verifying that all four selector files existed. The pinned interpreter and frozen import paths were used. TEMP, TMP, TMPDIR, pytest cache, basetemp, and the explicit tempfile preflight were all under the approved r10\t\tp\run3 root. The exact selected environment is recorded in environment.json.

The final command is recorded at:

    D:\codex-tmp\v10b-0918\r10\e\testrun-publication\r3\command.txt

    D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -m pytest -o "addopts=" -o "cache_dir=D:\codex-tmp\v10b-0918\r10\t\tp\run3\pytest-cache" --basetemp "D:\codex-tmp\v10b-0918\r10\t\tp\run3\basetemp" --junitxml "D:\codex-tmp\v10b-0918\r10\e\testrun-publication\r3\junit.xml" "--cov=stm32_toolkit" "--cov=stm32_monitor" --cov-branch "--cov-fail-under=0" "--cov-report=term-missing" "--cov-report=json:D:\codex-tmp\v10b-0918\r10\e\testrun-publication\r3\coverage.json" -x tools/stm32-toolkit/tests/test_target_replay_publication.py::test_target_replay_publication_rejects_valid_identity_contradiction_before_publication tools/stm32-toolkit/tests/test_target_replay_publication.py::test_target_replay_publication_rejects_valid_state_contradiction_before_publication tools/stm32-toolkit/tests/test_target_replay_publication.py::test_target_replay_publication_rejects_contradictory_parent_binding_before_publication tools/stm32-toolkit/tests/test_testing_publication.py::test_repository_rejects_duplicate_json_keys_from_authoritative_manifest_provider

Result:

    collected 4 items
    4 passed in 10.39s
    pytest exit code: 0

JUnit records four tests, zero failures, zero errors, and zero skips. Branch coverage was enabled for both packages and --cov-fail-under=0 was used because the release 90% threshold is an aggregate release gate rather than a valid threshold for this bounded selector set. The retained final aggregate coverage JSON reports 38,013 statements, 13,564 branches, 460 covered branches, and 342 partial branches. The targeted frozen Toolkit publication module reports 58 of 232 branches covered with 46 partial branches; the final stdout coverage table reports the same module at 34% line coverage. The Toolkit-only selectors did not import stm32_monitor; pytest-cov emitted the retained module-not-imported warning in stderr.txt, and no Monitor source branch result is attributed to this slice.

The raw coverage database is retained at:

    D:\codex-tmp\v10b-0918\r10\e\testrun-publication\r3\coverage\.coverage

The final evidence root also contains coverage.json, junit.xml, stdout.txt, stderr.txt, exit-code.txt, command.txt, environment.json, and the child tempfile containment files. The preflight exited 0 and reported the effective tempfile directory as:

    D:\codex-tmp\v10b-0918\r10\t\tp\run3\tmpdir

The child tempfile was created below that directory and the containment result was true.

## Earlier invocation evidence

The first bounded invocation is preserved at:

    D:\codex-tmp\v10b-0918\r10\e\testrun-publication\r1

It collected the same four selectors, passed the identity node, then stopped at the state node because the initial test builder used replace(manifest, state="passed") while retaining a failed case. The frozen public model correctly raised TEST_EVENT_SEQUENCE_INVALID before the publisher call. This was a test-input construction failure, not a product behavior result; it exited 1 and produced no coverage JSON or binary database. Its command, environment, stdout, stderr, JUnit, exit, and tempfile containment evidence are retained.

The second bounded invocation is preserved at:

    D:\codex-tmp\v10b-0918\r10\e\testrun-publication\r2

It passed the two identity/state nodes, then stopped while constructing the contradictory parent because dataclasses.replace retained the old envelope evidence ID after metadata changed. The frozen EvidenceEnvelope constructor correctly raised EVIDENCE_INVALID before the publisher call. This was also a test-input construction failure, not a product behavior result; it exited 1 and produced no coverage JSON or binary database. Its command, environment, stdout, stderr, JUnit, exit, and tempfile containment evidence are retained.

The corrected final invocation used the same four selectors and no broader module or suite rerun. All three run-scoped temporary roots and all evidence roots remain preserved for the primary agent review and aggregation; no cleanup was performed by this implementation agent.

This report records implementation evidence only. Independent review of the complete accepted-base-to-code-head diff and acceptance remain with the primary agent or another reviewer; the implementation agent does not accept its own changes.
