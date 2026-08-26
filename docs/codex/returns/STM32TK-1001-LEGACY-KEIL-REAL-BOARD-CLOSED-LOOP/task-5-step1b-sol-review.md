# Task 5 Step 1b Sol Review

## Verdict

`ACCEPTED`

The frozen five-path proposal is authorized for one exact local apply to the campaign project. No unresolved product defect remains in this proposal. Conversion apply, configuration, build, hardware access, and remote operations remain outside this authorization until the local five-path commit exists.

## Ledger

- Module/phase: STM32TK-1001 VS10-A, H1 Task 5 Step 1b.
- Accepted campaign base: `b83b404c8da6993658586fa1b553d715f95993c1`, tree `a7d38844454ab22ab23ddd768675dd9e15bc210c`.
- Specification/plan owner and reviewer: GPT-5.6-sol primary.
- Implementer: one GPT-5.6-luna/max agent.
- Proposal commit: `59315ab5fa1108d0b88cc44470e2def772dd94fd`, tree `2990239f436c259ae3652cc0df48b9411b14b381`.
- Active branch/PR: local campaign repository is detached/no-remote; no VS10 PR exists.
- Remote action authorized: none.
- Bounded override: none.

## Complete Diff Review

The complete accepted-base-to-proposal diff contains exactly five paths and 23 insertions/23 deletions:

- `Common/common.c`: replace ARMCC function-form inline assembly with CMSIS Cortex-M4 intrinsics.
- `MALLOC/malloc.c`: express alignment with GNU syntax and fixed external SRAM/CCM pool/map addresses as typed pointers.
- `Main/string.h`: preserve the entire legacy ARMCC body behind the non-GNU branch and forward GNU builds with `#include_next`.
- `Project/LWIP.gcc.uvprojx`: promote `USER/IWDG` to the target include set, clear only the two group include overrides, and correct the derived startup C path.
- `USER/usart1/usart1.c`: remove only the ARMCC no-semihosting pragma and trailing empty line.

The canonical diff is 6,292 bytes with SHA-256 `a37d69e60c635674bff401268293b49749cead14f899b5a28e8d7f7a7fb39d8d`. All five before/after file hashes and Git blobs matched the formal evidence. `git -c core.whitespace=cr-at-eol diff --check` passed; the CRLF/LF contract contains no CRCRLF sequence.

## Independent Verification

- Formal JSON: 414,385 bytes, SHA-256 `d23c844d0baae9addd18bfda5f036ac1507f38ada85aea24666d0d042c666097`; embedded null-field self hash independently recomputed as `1f1019a71c0a96ce37a0b89af973d07966aa392e893dbdb98a593a6093c19bef`.
- Isolated review tree reproduced proposal tree `2990239f436c259ae3652cc0df48b9411b14b381`.
- Independent direct GCC compile: 3 attempted/3 passed; one recorded pre-existing warning per unit; object hashes matched implementer evidence.
- Independent public inspect: exit 0/`OK`, STM32F429ZGTx/SPL, 53 C sources, 0 assembly, 38 unique target include paths, `USER/IWDG` exactly once, one target scoped option, zero group/file scoped options.
- Independent public convert dry-run: two runs, both exit 0/`OK`, zero blockers, identical output within the review root, and inspection SHA-256 `ea9f6aa1135f6fff4aef599658f553db922fe7a4b2228ed2c9f6d54296bc0208`.
- Accepted implementer full-compile evidence: 53 attempted/53 passed, 111 warnings recorded, 18 `string.h` consumers resolved through the proposal header to pinned CubeCLT newlib; common/allocator/header-usart semantic proofs all `PASS`.

The independent review-root plan ID differs from the implementer-root plan ID because plan identity binds the explicit project root. Both repeated runs were deterministic in their own root, while the input inspection SHA remained identical; this is expected public behavior, not drift.

## Authorization

Single-use authorization is recorded at `C:\tmp\stm32tk-vs10a-legacy-campaign\evidence\portability-authorization-v3.json` with SHA-256 `7f962a696793d5d5afa9d18f7109d35612f00a90ababd72ac8bba99bce74ff81`. It binds the exact base/tree, proposal commit/tree, evidence and diff digests, five-path set, runtime source commit, and independent verdict. Any pin drift invalidates it before apply.

## Boundaries

- Campaign main remained clean at the accepted base during proposal and review.
- Active runtime remained the single 0.9.0 generation-1 runtime sourced from `3db9e0013bd2f62c478598e0f95fe2c27aeefdfa`.
- Golden project, hardware, network, and remote Git were not accessed.
- Full 53-unit compilation was not repeated by Sol because the implementer evidence is self-contained and the independent review repeated the three directly changed units plus public inspection/dry-run behavior.
