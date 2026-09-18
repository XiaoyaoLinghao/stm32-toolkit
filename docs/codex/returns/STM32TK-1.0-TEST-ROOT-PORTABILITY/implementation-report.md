# STM32TK-1.0-TEST-ROOT-PORTABILITY Implementation Report

## Delivery identity

- Status: `IMPLEMENTED` for the bounded fixture slice; independent review and
  release integration acceptance are pending.
- Accepted product base: `1df30a0f4070805488687a67f907dbaa1867d681`
- Branch: `codex/STM32TK-1.0-test-root-portability`
- Code head before this report commit:
  `646ba7740b6f20b640a71b0d0586fe9cfb09bb50`
- Scope owner: one Luna/max implementation agent; primary owns integration and
  acceptance.

This report intentionally does not contain the final commit SHA that contains
the report itself.

## Delivered scope

The ten specified Toolkit test modules now allocate actual fixture directories
through `pytest.TempPathFactory.mktemp`, with short names preserved for the
generated-project tests. The diagnostic, evidence, host-testing, publication,
verifier, and feasibility fixtures no longer call `tempfile.mkdtemp` with a
`C:\\tmp` directory. The gate-controller coverage and Win32 directory-lock
tests use the fixture-owned parent for sibling evidence and the fixture path
for the locked directory; their cleanup is limited to those attributed paths.
The controller's development-coverage entry point has one private pytest-only
`_coverage_temporary_root` keyword, whose default remains `C:\\tmp`. The seam
rejects a non-default root without `PYTEST_CURRENT_TEST`, and passes the same
explicit root through location checks, native locking, and revalidation. The
affected tests explicitly pass their fixture-owned parent.

Parser, negative-input, frozen-argv, and support-profile `C:\\tmp` literals
remain unchanged. No public product/runtime behavior, release version,
packaging, dependency, hardware, or remote behavior was changed.

## Verification evidence

Environment: Windows, CPython 3.12.10, pytest 8.4.2. The preflight bound
`TEMP`, `TMP`, and `TMPDIR` to `D:\\codex-tmp\\v10b-0918\\r10\\t` and recorded
`tempfile.gettempdir()` resolving to the same path. Source identity and every
command, stdout, and exit record are retained below
`D:\\codex-tmp\\v10b-0918\\r10\\e\\fixture`.

| Gate | Result |
|---|---|
| Representative allocation/workflow/host/release tests | 8 passed, exit 0, 2.98 s |
| Native Win32 directory-lock identity test | 1 passed, exit 0, 0.44 s |
| Collection of all ten owned modules | 1,069 collected, exit 0, 0.98 s |
| `py_compile` for the controller and owned coverage test module | exit 0 |
| `git diff --check` before and after code staging | exit 0 |
| Corrected coverage seam focused tests | 5 passed, exit 0, 0.67 s |
| Corrected `test_dev_coverage` coverage subset | 107 passed, 343 deselected, exit 0, 4.81 s |

The representative allocation evidence is in `alloc/`, native lock evidence is
in `lock/`, the initial retained coverage failure is in `coverage-sibling/`,
and corrected seam evidence is in `coverage-seam-revision/` (with the focused
rerun and full coverage subset below it). Collection evidence is in `collect/`,
and the environment/source records are `preflight.*` and `source-identity.txt`
under the retained fixture evidence root.

The first coverage-sibling command remains retained as exit-1 evidence: it
reached the accepted-base `C:\\tmp` guard before the runner. The private seam
then routed the same native lock and pipe contract through the approved
D-drive fixture parent; the corrected focused and coverage-subset commands
passed without changing the frozen basetemp token or safety assertions.

Two earlier command-entry attempts are retained as infrastructure evidence:
pytest rejected the unsupported `--cache-dir` option (exit 4), then rejected an
incorrect node id (exit 4). The corrected command passed and its records are
`alloc/command-final.txt`, `alloc/stdout-final.txt`, and `alloc/exit-final.txt`.

## Review and non-claimed evidence

- Independent full-diff review is pending a non-implementing reviewer.
- The final Python release matrix, including performance and browser timing,
  belongs to the primary integration run and was not duplicated here.
- No hardware, deployment, packaging, or remote evidence is claimed.
