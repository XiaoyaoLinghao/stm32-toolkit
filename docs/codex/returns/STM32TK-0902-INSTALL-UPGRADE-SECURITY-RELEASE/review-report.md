# STM32TK-0902 Sol independent review report

## Verdict

`ACCEPTED`

- Version accepted base: `9a5a132b74638a39b346848cfad0eeb7db9a0539`.
- Accepted VS09-A slice base: `22bff0061e54e37eba22d892a3b8c34949c3b130`.
- Returned report head reviewed: `e28861c5da046b1cd65d67849894f37a1b4c0059`.
- Product CodeHead: `464878d6f08eddcfaa641ffac96834a13b2d70b6`.
- Sole implementer: GPT-5.6-luna/max, `/root/vs09b_implementer`.
- Independent reviewer/acceptor: GPT-5.6-sol primary agent.
- Final review worktree: clean detached `C:/tmp/stm32tk-0902-sol-acceptance`.
- Remote/hardware actions: none.

Sol reviewed the complete VS09-B range
`22bff0061e54e37eba22d892a3b8c34949c3b130..e28861c5da046b1cd65d67849894f37a1b4c0059`
and the complete version range
`9a5a132b74638a39b346848cfad0eeb7db9a0539..e28861c5da046b1cd65d67849894f37a1b4c0059`.
No unresolved product defect remains in VS09-A or VS09-B.

## Finding reconciliation

1. **Release/source closure — ADDRESSED.** The manifest, extracted source, release tree, product
   wheels, Monitor assets, licenses and six named artifacts are closed and hash-bound to one full
   Product CodeHead. Unlisted, missing, substituted, duplicate and case-fold-colliding members
   fail closed.
2. **Bootstrap trust — ADDRESSED.** The externally checksummed setup script validates frozen
   utility and policy digests before execution, retains the exact bytes it read and passes them to
   isolated CPython for in-memory compilation. Replacing the extracted utility cannot create a
   marker or runtime/staging/quarantine state.
3. **License and SBOM authority — ADDRESSED.** The candidate contains 80 wheel-shipped license or
   notice members plus six complete, source-controlled and hash-bound SPDX texts. The SPDX graph
   has 491 unique package authorities and no duplicate or `NOASSERTION` license authority.
4. **Windows checkout bytes — ADDRESSED.** Root `LICENSE` is explicitly LF. Canonical SPDX files
   preserve their upstream byte hashes while a path-scoped whitespace attribute prevents those
   authoritative trailing spaces and blank EOF lines from making the full diff check fail.
5. **Runtime lifecycle — ADDRESSED.** One existing Check/Bootstrap/Repair engine installs only
   verified manifest wheels with no index or resolver, publishes one schema-1 runtime state,
   preserves/quarantines legacy state, and refuses downgrade, future state and same-version source
   conflicts before mutation.
6. **Scope — CLEAN.** The diff adds no Agent-specific product behavior, second runtime/MCP
   registration/controller/provider/backend, Python/platform range, CI, collaboration automation,
   hardware claim or VS10 work.

## Independent verification

All checks ran on Windows with CPython 3.12.10 against the clean returned-head worktree.

- Artifact plus malicious-input suites: **64 passed** (`37 + 27`).
- Setup bootstrap trust subset: **4 passed**.
- Public inventory, plugin layout and doctor suite: exit `0`, 100%, no failures.
- `git diff --check` returned exit `0` for both the VS09-B slice range and the complete
  accepted-version-base range.
- `git check-attr` reported `LICENSE eol: lf` and canonical SPDX
  `whitespace: -trailing-space`; root LICENSE and SPDX MIT were byte-identical with SHA-256
  `55edb314745f2b0d3fe09e512726c3bf67cb20ba99fa3cd66859a64f3e6b6af5`.

The retained candidate `C:/tmp/p0902-final-candidate-vs09b-r3` has 13 top-level files.
`CHECKSUMS.sha256` verified 12/12 entries. Independent parsing confirmed 64 wheels, six artifact
entries, source commit `464878d6f08eddcfaa641ffac96834a13b2d70b6`, inventory 48 MCP/eight
Skills, 86 license members and these SBOM counts:
`DESCRIBES=2`, `DEPENDS_ON=96`, `GENERATED_FROM=427`, duplicate authority 0 and
`NOASSERTION` 0.

Sol extracted a fresh copy of the final Windows archive and replaced its release utility with code
that would write an attacker marker and return plausible facts. Check exited 0 with
`bundle.status=invalid`; Bootstrap exited 2; the marker, DataRoot, staging and quarantine were
all absent.

Sol separately extracted the unmodified final archive into fresh explicit roots with hostile
Python and pip environment variables removed and `PIP_NO_INDEX=1`. Bootstrap and Check exited 0,
the runtime was healthy, bundle/state were `ok/matching`, generation was 1, managed
`pip check` reported no broken requirements, and doctor reported Toolkit/Monitor 0.9.0,
48 MCP tools and eight Skills.

## Candidate hashes

| Artifact | SHA-256 |
| --- | --- |
| `CHECKSUMS.sha256` | `94b9442edfbe935d976ce9b31435b095145ea83be517ac7de846f53dc0a11762` |
| `release-manifest.json` | `c63b502fb39d645375ed18a1b41f269a8bf13b646a9c03ba73d46dbc1fcf4c60` |
| `licenses.zip` | `676323df0c214c3440dc67e1fa496a8a7fe6adb63a77a5c784377afa957432eb` |
| `sbom.spdx.json` | `9b917cfe1f12369843365854a59df3a028c861eda217fdee1c44a30950943a48` |
| source ZIP | `95ba4739f80fbda8af7538c21f6c89f49909b6aa5e166533bb6715c09969863e` |
| Windows ZIP | `d33aa28cf91b099b69399f590dee68bd239656c5fcdc3c99676b04c900a0943d` |

## Cleanup and boundary

The exact Sol attack, install and basetemp roots are run-scoped and are removed after this report
is committed. The retained r3 candidate is not disposable. The implementation branch remains
local, unpushed and without upstream. No push, PR mutation, merge, tag, release, remote branch,
upload, authentication, hardware or other external mutation occurred. Work stops at accepted
VS09-B and does not enter VS10.
