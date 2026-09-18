# STM32TK-1.0-TEST-ROOT-PORTABILITY Implementation Report

## Delivery identity

- Status: `IMPLEMENTED` for the bounded fixture slice; independent review and
  release integration acceptance are pending.
- Accepted product base: `1df30a0f4070805488687a67f907dbaa1867d681`
- Branch: `codex/STM32TK-1.0-test-root-portability`
- Code head before this report commit:
  `4fa47ed645483bc431a9a8e293d45daa02b42d6d`
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

Parser, negative-input, frozen-argv, and support-profile `C:\\tmp` literals
remain unchanged. No product, release-version, packaging, dependency,
hardware, or remote files were changed.

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
| `git diff --check` before and after code staging | exit 0 |
| Coverage sibling cleanup/raw-publication test | exit 1 at the accepted-base production location guard; classified as an integration boundary below |

The representative allocation evidence is in `alloc/`, native lock evidence is
in `lock/`, coverage evidence is in `coverage-sibling/`, collection evidence is
in `collect/`, and the environment/source records are `preflight.*` and
`source-identity.txt` under the retained fixture evidence root.

The coverage sibling test reaches
`tools/release/run_0600_gates.py::_validate_coverage_attempt_location`, which
still requires a direct child of `C:\\tmp`. The changed test correctly creates
its evidence sibling under the approved D-drive fixture parent, so the current
accepted-base production policy rejects it before the runner starts. Production
path policy is outside this slice and is deferred to the primary's release
integration owner; no production file was changed here.

Two earlier command-entry attempts are retained as infrastructure evidence:
pytest rejected the unsupported `--cache-dir` option (exit 4), then rejected an
incorrect node id (exit 4). The corrected command passed and its records are
`alloc/command-final.txt`, `alloc/stdout-final.txt`, and `alloc/exit-final.txt`.

## Deferred and non-claimed evidence

- Independent full-diff review is pending a non-implementing reviewer.
- The final Python release matrix, including performance and browser timing,
  belongs to the primary integration run and was not duplicated here.
- The coverage sibling gate remains pending the separately owned production
  path-policy integration and rerun.
- No hardware, deployment, packaging, or remote evidence is claimed.
