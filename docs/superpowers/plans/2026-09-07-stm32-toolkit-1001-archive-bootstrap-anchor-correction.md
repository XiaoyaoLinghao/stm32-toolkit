# STM32TK-1001 Archive Bootstrap Anchor Correction Implementation Plan

**Goal:** Restore the existing archive-byte bootstrap trust contract by updating only the two
frozen setup digests, then resume Task 8's already-approved single-runtime offline flow only after
independent acceptance.

**Architecture:** The source archive remains the immutable byte authority. Setup remains the
bootstrap trust root and compares the extracted release utility and policy with two static SHA-256
constants before execution. No validation path or lifecycle changes.

**Accepted base:** `5b48eadf5a857f7670856b43e3e72228ea01e832`.

**Owners:** GPT-5.6-sol owns this plan, review, and acceptance. The existing GPT-5.6-luna/max Task 8
implementer uniquely owns the bounded product edit and its implementation evidence.

## Task 1: Prove the archive-byte mismatch

- [ ] Reuse the clean detached exact-base worktree with `core.autocrlf=false`; require clean status,
  exact HEAD, and raw-byte equality for all Toolkit/Monitor packaged sources.
- [ ] Run only
  `tools/stm32-toolkit/tests/release/test_0900_artifacts.py::test_bootstrap_anchor_binds_git_archive_bytes_not_worktree_filter_bytes`
  with CPython 3.12 and an external unique basetemp.
- [ ] Preserve RED showing archive utility SHA
  `6c6c457bff2606157a78c9b2215f77d4ecbd18e5d74d9ee97194754fe780aec8` and policy SHA
  `8bb1db7ed69941ced78ac0dac8c4aa600fc2dcb0300365a197cd8e85bade0ee7` do not equal the two setup
  constants. Do not edit a test to manufacture RED.

## Task 2: Apply the bounded product correction

- [ ] In the implementation branch, change only `$ReleaseUtilitySha256` and
  `$ReleasePolicySha256` in `bin/setup-stm32-env.ps1` to the exact archived-byte digests above.
- [ ] Do not edit the release utility, policy, setup logic, schemas, runtime behavior, or tests.
- [ ] Run the exact archive-anchor test to GREEN in the clean LF-byte worktree.
- [ ] Run the three affected setup security tests:
  `test_setup_rejects_replaced_release_utility_before_execution`,
  `test_setup_rejects_policy_swap_at_bootstrap_boundary`, and
  `test_setup_rejects_changed_after_read_utility_before_staging`.
- [ ] Clean only the external basetemps/bytecode created by these runs after preserving results.
- [ ] Require `git diff --check`, exact changed-path inventory, and a diff containing only the two
  constants plus these frozen documents. Commit product code separately from any report update.

## Task 3: Independent Sol review

- [ ] Create a new clean detached worktree at the returned code head with `core.autocrlf=false`.
- [ ] Review the complete `5b48eadf5a857f7670856b43e3e72228ea01e832..CodeHead` diff.
- [ ] Recompute the exact two archive member digests, compare them with setup, and independently run
  the four focused tests with CPython 3.12 and an external unique basetemp.
- [ ] Confirm utility/policy bytes and every setup validation branch are unchanged; confirm no
  product, runtime, network, hardware, or remote scope expansion.
- [ ] Issue `ACCEPTED` only with no unresolved product/security/report finding.

## Task 4: Resume the previously frozen Task 8 flow

- [ ] Only after Sol `ACCEPTED`, return ownership to the same Luna/max Task 8 implementer.
- [ ] Build one new offline candidate from the accepted clean LF-byte worktree and existing exact
  66-wheel closed set; verify archive, bundle, checksums, source binding, inventory, and assets.
- [ ] Preserve old runtime state/manifest/package hashes and no-holder evidence, then use only the
  shipped setup Check plus fresh Bootstrap replacement path. Same-version Repair remains forbidden.
- [ ] Require exactly one active 0.9.0 runtime bound to the accepted head, then resume public Task 8
  configure/build/MAP/ELF/decoder/digest/no-write evidence and project commit/report.
- [ ] Stop before hardware and every remote/release action unless separately authorized.
