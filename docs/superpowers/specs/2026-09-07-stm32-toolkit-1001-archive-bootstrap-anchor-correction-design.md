# STM32TK-1001 Archive Bootstrap Anchor Correction Design

## Status and ownership

- Status: frozen for the bounded Task 8 recovery.
- Full accepted base: `5b48eadf5a857f7670856b43e3e72228ea01e832`.
- Specification and acceptance owner: GPT-5.6-sol primary.
- Implementation and implementation-test owner: the existing GPT-5.6-luna/max Task 8 implementer.
- Independent reviewer: GPT-5.6-sol in a clean detached exact-head worktree.
- Active local branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`.
- Remote, hardware, release, tag, PR, and merge authority: none for this correction.

## Problem statement

The 0.9.0 release builder correctly treats the exact `git archive` members as the source bytes
delivered to an extracted Toolkit root. `bin/setup-stm32-env.ps1` must therefore freeze the SHA-256
of the release utility and release policy bytes inside that archive before either file can execute.

At the accepted base, the two frozen constants equal the CRLF-filtered Windows worktree bytes:

- release utility: `30f77206434d79d5ee8f912b754f75a4c43d24766c3b4f2c8d739b39957d13e0`;
- release policy: `d5226dbd38a63e011d9a4456f9fbd89750244becef5ea49f99210affcebf7b66`.

The exact accepted-base `git archive` instead contains these authoritative bytes:

- release utility: `6c6c457bff2606157a78c9b2215f77d4ecbd18e5d74d9ee97194754fe780aec8`;
- release policy: `8bb1db7ed69941ced78ac0dac8c4aa600fc2dcb0300365a197cd8e85bade0ee7`.

Consequently a clean source-bound offline candidate fails closed with
`bootstrap trust anchor does not match the committed release utility and policy`. The failure is
not permission to weaken or bypass the trust check.

## Runnable scenarios

### Scenario 1: exact archived source is accepted

From a clean detached accepted head whose packaged source raw bytes equal the Git blobs, the
existing release builder creates its source archive. The setup helper's two frozen constants equal
the SHA-256 of the archive's exact release utility and policy members, so the bootstrap-anchor gate
passes and candidate construction may continue to all existing verification gates.

### Scenario 2: checkout filters cannot become trust authority

Changing only checkout newline presentation must not change the authoritative digests. The
archive members at the exact commit remain the source of truth. A CRLF worktree hash is not copied
into the setup trust root when the delivered archive bytes are LF.

### Scenario 3: replaced utility or policy still fails before execution

If an extracted utility or policy differs from either frozen archive digest, setup continues to
reject it before executing the utility or creating runtime staging. Existing replacement,
after-read mutation, hash, path, and source-conflict protections remain byte-for-byte unchanged.

### Scenario 4: Task 8 runtime recovery remains single-path and offline

After the correction is independently accepted, Task 8 may rebuild one candidate from the exact
accepted head and existing closed 66-wheel input, verify the bundle, and fresh-replace the unique
campaign runtime through the shipped setup path. The correction itself performs no runtime,
project, network, hardware, or remote action.

## Frozen contract

`git archive` members are the sole authority for the two bootstrap digests. The bounded product
change is exactly the values of `$ReleaseUtilitySha256` and `$ReleasePolicySha256` in
`bin/setup-stm32-env.ps1`. The release utility and policy bytes, hashing algorithm, validation
order, error semantics, setup lifecycle, runtime-state schema, downgrade/source-conflict rules,
and atomic staging behavior do not change.

## Non-goals

- Do not change `tools/release/build_0900_artifacts.py` or its policy.
- Do not make anchors dynamic, hash worktree files, normalize bytes at verification time, or accept
  multiple hashes.
- Do not weaken the pre-execution trust boundary or any malicious-input rejection.
- Do not add a runtime, installer, backend, provider, MCP registration, agent integration, CI, or
  collaboration automation.
- Do not rebuild or replace the runtime before independent product acceptance.
- Do not access hardware or perform any remote/release action.

## Acceptance evidence

- In a clean `core.autocrlf=false` detached worktree, the pre-change archive-anchor regression is
  RED and names the two exact expected/observed digest mismatches.
- After changing only the two constants, the archive-anchor regression is GREEN.
- The three existing setup tests for replaced utility, policy swap, and changed-after-read utility
  remain GREEN and retain pre-execution/no-staging assertions.
- `git diff --check` passes and the product diff contains only the two setup constants.
- GPT-5.6-sol reviews the complete accepted-base-to-code-head diff and independently reruns the
  focused tests before issuing a verdict.

