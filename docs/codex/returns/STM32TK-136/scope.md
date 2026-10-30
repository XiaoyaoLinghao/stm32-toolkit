# v1.3.6 verification scope and source ledger

Accepted base: `37f69ca4acc2b879d4227a099384241ec39080f4` (master).
Initial integrated CodeHead: `51ee43b1a0abbe4f2e5436d4cda5211d67ad17c0`.
Specification, orchestration, independent review and acceptance: primary Codex.
Implementation and implementation tests: local Claude Code CLI, preserving the
configured `deepseek-v4.1-flash[1m]` route. No implementation fallback.
Branch: `codex/v136-tool-evidence`; no PR. User authorizes the v1.3.6 source
integration into master, release build and Release upload/publication. This does
not grant installed-runtime replacement, original-project edits or hardware use.

Before aggregating release coverage, add the complete new
`tools/stm32-toolkit/src/stm32_toolkit/build/abi_evidence.py` to Toolkit
`risk-core-v2`: it owns unique report containment, bounded input parsing and
semantic provenance validation. Existing risk membership and native branch
denominators remain intact. No score was used to select this addition. No
existing file is removed or excluded, and permanent 90%/95% gates are unchanged.
The v1.3.5 non-regression exception is version-specific and does not transfer.

Verification uses disposable fixture projects and offline probe doubles. The
existing real GNU build/preset journey uses only synthetic disposable source;
it does not access hardware. All test files are assigned exact commands, fresh
JUnit/terminal reports and source hashes in the run-local evidence directory.
The initial focused integration runs bind the initial integrated CodeHead.
Later changed tests and code need bounded new evidence; unchanged source-bound
passes may be retained with explicit identity reconciliation, never described
as a single final-head rerun. Failures and skipped platform capability remain
separate from passing evidence.

Run-local logs and task JSON: `D:/codex-tmp/v136-evidence`.
Migration and build original edit invocations have out-of-scope reads and remain
NOT_ACCEPTED invocations; their retained candidate diffs require independent
review and tests. The first migration check had 35 passes and two serialization
assertion failures. The two corrected nodes subsequently passed; they are not
counted as additional distinct cases. The version-fixture launcher completed
its native accepted edit but its outer summary print failed under GBK. Future
launcher invocations explicitly select UTF-8 using the same verified Python;
the original outer exit and saved native evidence are preserved.
