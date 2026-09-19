# Deployment documentation portability correction

Accepted base: `746393d59c6e7aed7d484c655d9900b1de533125`.
Implementation integration head: `f41404ed6dfaa3966b5d7c77123a3f6bfa9aa523`.
Code head before this report commit: `8f8479fc1781afefa76ba558df1b8a8d41e104f0`.
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
  created and removed; result: `D:\codex-tmp\v10b-0918\r10\e\deployment-doc-portability\temp-root-check.txt`.
- The original PowerShell AST result remains at
  `D:\codex-tmp\v10b-0918\r10\e\deployment-doc-portability\powershell-ast.json`. The correction
  parser then found zero errors in nine standalone blocks (three per document), confirmed that
  each mutation block contains only its selected mode, and confirmed the preserved host adapter
  Check command; result:
  `D:\codex-tmp\v10b-0918\r10\e\deployment-doc-portability\correction-powershell-ast.json`.
- Python AST parsing of `tools/release/build_0900_artifacts.py` and PowerShell AST parsing of
  `bin/setup-stm32-env.ps1` passed in the initial implementation check; result:
  `D:\codex-tmp\v10b-0918\r10\e\deployment-doc-portability\source-syntax-check.json`.
- The correction invoked the existing `build_0900_artifacts._assert_bootstrap_trust_anchor` once
  against a source-archive-shaped byte set and checked the updated troubleshooting layout. The
  utility hash and setup literal both equal
  `9fe8b91e3834156b974850f13a89c7c899b49444403d0bbc0ab73b16332d671c`; result:
  `D:\codex-tmp\v10b-0918\r10\e\deployment-doc-portability\correction-source-pin-check.txt`.
- The correction content check confirms the legacy-upgrade wording, preserved host Check command,
  neutral release paths, and extracted-root guide wording; result:
  `D:\codex-tmp\v10b-0918\r10\e\deployment-doc-portability\correction-content-check-final.json`.
- Existing regression node passed:
  `D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -I -B -m pytest -q tools/stm32-toolkit/tests/release/test_0900_artifacts.py::test_bootstrap_anchor_binds_git_archive_bytes_not_worktree_filter_bytes --basetemp D:\codex-tmp\v10b-0918\r10\t\dd\anchor -o cache_dir=D:\codex-tmp\v10b-0918\r10\t\dd\anchor/pytest-cache`
  with exit code `0`; result:
  `D:\codex-tmp\v10b-0918\r10\e\deployment-doc-portability\bootstrap-anchor-pytest.txt`. This
  existing anchor test was not rerun for the documentation-only correction.
- `git diff --check HEAD^ HEAD` passed. No installer, package build, deployment, hardware,
  performance, full-suite, or remote operation was run.
- The correction diff check is retained at
  `D:\codex-tmp\v10b-0918\r10\e\deployment-doc-portability\correction-diff-check.txt`.

Primary retains cleanup ownership. The durable evidence root is
`D:\codex-tmp\v10b-0918\r10\e\deployment-doc-portability`; no cleanup was performed by the
implementer.
