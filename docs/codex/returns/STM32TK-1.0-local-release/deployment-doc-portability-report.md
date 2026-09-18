# Deployment documentation portability correction

Accepted base: `746393d59c6e7aed7d484c655d9900b1de533125`.
Implementation integration head: `f41404ed6dfaa3966b5d7c77123a3f6bfa9aa523`.
Code head before this report commit: `7728dd9e29acf4e71e10eaef83dcb4429e3c9611`.
The implementation commit changes only the two READMEs, the setup Skill, the generated
troubleshooting function, and the matching `ReleaseUtilitySha256` literal.

The standalone Windows PowerShell examples now define absolute user-replaceable
`ToolkitRoot`, `DataRoot`, and `ProjectRoot` paths, run read-only `Check` first, and require an
explicit choice between `Bootstrap` and `Repair`. Release-owner examples use neutral local paths.
Generated troubleshooting explains the guide location in the companion source archive and in an
extracted bundle, including the `release/` relative location. Installer modes, dependencies,
runtime behavior, and package artifacts were not changed; the retained 15b artifacts remain
historical and were not regenerated.

## Verification

All Python commands below used `D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -I -B` after
binding `TMPDIR`, `TEMP`, and `TMP` to `D:\codex-tmp\v10b-0918\r10\t\dd`.

- The actual Python `tempfile.gettempdir()` was checked against that root, with a temporary file
  created and removed; result: `evidence/deployment-doc-portability/temp-root-check.txt`.
- PowerShell AST parsing of the three setup command blocks found zero errors and confirmed the
  three absolute paths, `Check`, `Bootstrap`, and `Repair`, with no host placeholders;
  result: `evidence/deployment-doc-portability/powershell-ast.json`.
- Python AST parsing of `tools/release/build_0900_artifacts.py` and PowerShell AST parsing of
  `bin/setup-stm32-env.ps1` passed; result: `evidence/deployment-doc-portability/source-syntax-check.json`.
- The existing `build_0900_artifacts._assert_bootstrap_trust_anchor` check passed against a
  source-archive-shaped byte set. The utility hash and setup literal both equal
  `47c6c1fa2eebcbfcf30aaae4ef11a86bf920b44f1d4294d9ea4402cef569a856`; result:
  `evidence/deployment-doc-portability/source-pin-troubleshooting-check.txt`.
- Existing regression node passed:
  `D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -I -B -m pytest -q tools/stm32-toolkit/tests/release/test_0900_artifacts.py::test_bootstrap_anchor_binds_git_archive_bytes_not_worktree_filter_bytes --basetemp D:\codex-tmp\v10b-0918\r10\t\dd\anchor -o cache_dir=D:\codex-tmp\v10b-0918\r10\t\dd\anchor/pytest-cache`
  with exit code `0`; result: `evidence/deployment-doc-portability/bootstrap-anchor-pytest.txt`.
- `git diff --check HEAD^ HEAD` passed. No installer, package build, deployment, hardware,
  performance, full-suite, or remote operation was run.

Primary retains cleanup ownership. The durable evidence root is
`D:\codex-tmp\v10b-0918\r10\e\deployment-doc-portability`; no cleanup was performed by the
implementer.
