# Complete source preparation: retained intermediate state

Verdict: **REVISION_REQUIRED**; this is a retained intermediate result, not M3b2 acceptance. Date: 2026-10-26.

- Accepted base: `136ca7ed236f39d1a0fb90f89980e1b6ebe0c864` (M3b1 public WFI route).
- Plan: `7c9309ddf1e86bbc28bbe9e3f4549aea01a41feb`, [source preparation](../../../superpowers/plans/2026-10-26-gcc-source-preparation.md).
- Guidance candidate CodeHead before this report: `2aa0f71f2c2ca3f157c760d529142531896e9b85`.
- Branch: `codex/gcc-source-route`; no remote, version or release action.
- Primary owns specification, orchestration, independent review and acceptance. Local Claude Code CLI with the existing `deepseek-v4.1-flash[1m]` route authored the six guidance files; no primary implementation fallback.

The candidate shortens the migration entry and adds conditional source-preparation/options references. It describes declared charsets for sources and needed headers, reviewed partial converted copies, complete prepared source trees, independent GCC delivery and explicit WFI normal-return intent. The normalizer implementation is unchanged. Current published-package and unintegrated branch limitations remain explicit.

Global run `source-preparation-global-guidance`, main session `82f2168a-f23f-43ed-8f4d-2f7b5272d68d`, registered the exact five file tools and completed native edits without scope violations. One no-op Edit returned `old_string and new_string are exactly the same`; it changed no bytes. The wrapper therefore reports `accepted=false` while separately reporting `file_edit_completed=true`. No shell or tests executed in that file-only call; its logs are retained.

Primary reviewed the guidance against the source and ran the existing migration guidance group in the clean detached review checkout at the exact candidate: `sgp` **34 passed, 0 failed, 0 skipped**, exit 0, source unchanged. Exact command:

```powershell
& 'D:/codex-tmp/kx23/venv/Scripts/python.exe' -X utf8 'D:/codex-tmp/gcc26/run_checks.py' 'C:/Users/zhy76/.codex/worktrees/gcc-delivery-review/STM32-Toolkit' '2aa0f71f2c2ca3f157c760d529142531896e9b85' 'sgp' 'migration-guidance'
```

`D:/codex-tmp/gcc26/sgp` retains owner, argv, head, source hashes, stdout, fresh JUnit and coverage. This primary check does not replace the planned Claude verification or establish complete-project compiler evidence.

Remaining work:

1. Clarify `.git` handling in complete preparation. `migration/delivery.py::_scan_tree` excludes only `.git` source entries; the new copy guidance currently says every file without this distinction. Explicitly exclude VCS metadata without dropping source/resources or adding arbitrary ignores, so a prepared project does not inherit an unrelated worktree pointer or require copying Git internals.
2. Implement the planned combined synthetic GBK-header/startup/include/placement/external-RAM/WFI/no-Git fixture through Claude. Use real normalizer and public migration calls, then actual ARM GCC and output-only rebuild after source/prepared roots are unavailable. It has not been written or run.
3. Run author checks and primary final-head combined-fixture verification; finish the complete diff review and record final acceptance. Existing doc-contract checks already pass; do not rewrite them merely to match prose.
4. Integrate content-provenance managed hardware support and remove temporary branch restrictions only after integration. Normal fake-flash/readback and the second new-project journey remain integration gates. Backed-up global skill synchronization remains later work.

An independent Toolkit diagnostic implementation invocation returned a provider API refusal before any native tool call (`monitor-diagnostic-global-core`, session `a72bbba5-6927-4781-b292-19e5fb3f15b1`). It was stopped, with no model switch, retry or Codex implementation fallback. This already-running guidance task was preserved separately. Original projects, installed runtime, global configuration, hardware and remote state remain unchanged. No complete-product or release acceptance is claimed.
