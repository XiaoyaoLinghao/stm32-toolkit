# SESSION-TRACE: return to execution and verification integration design

Primary design after two correction attempts; no third local helper patch.
Accepted diff origin `bee6118339166e7d57a0e8ed1fc29ddf85242d0c`;
reviewed, unqualified candidate `1c8d32c3f0a8fe166034ed934bf2d87347502c14`.
Original branch codex/v135-session-trace remains at that candidate. Reuse its
clean isolated checkout on codex/v135-session-trace-runtime. Primary owns this
integration design, orchestration, independent full-diff review and acceptance;
local Claude Code CLI owns the one test-file adaptation, unchanged configured
route. No installation, hardware, packaging or remote authority.

## Evidence that changes the entry contract

All40 current test functions were actually executed once on the candidate in
short source-bound groups:26pass/14fail/0skip/0error, tracked hashes unchanged.
The6pass/1fail c02 result and c03–c09 matrix are retained under D:/codex-tmp/st135;
both verify invocations are unaccepted, with no native pending/scope/command
deviation. Model/CLI success is not software acceptance.

1. The test replaces global subprocess.Popen with a function before the first
   Toolkit backend import. Windows asyncio.windows_utils defines a Popen subclass;
   the replacement therefore causes a TypeError during import. Primary's separate
   unpatched import/lazy-backend observation succeeds; the patched import-only
   observation reproduces the stdlib error. Scope the spy to the launch call and
   restore it before backend import/acquisition. Do not weaken the assertion.
2. The chosen Windows venv executable is a redirector. In c04, parent Popen.pid
   is10492 while READY's actual Python PID is29520; attempt/request/source hashes
   and interpreter strings all match. This is not stale evidence. Primary's one
   inert stdlib-only observation independently records launcher11732, Python22744,
   Python's parent11732, exit0. Popen does not own the Python handle assumed by the
   design. The strict PID refusal is correct and must stay.

The pinned [CPython3.12.14 launcher source](https://github.com/python/cpython/blob/v3.12.14/PC/launcher.c)
explains VENV_REDIRECT and its second process; [venv documentation](https://docs.python.org/3.12/library/venv.html)
also documents Windows redirectors. Do not transfer current-main implementation
details to this installed version. The failed initial source URL is retained in
the conversation; the version-pinned launcher.c path is the applicable source.

## Fixed direct-runtime lane, selected before execution

Do not relax PID/source/request/lease checks, discover a descendant, take over
another PID, or automatically switch interpreter after a failure. This helper
is run-specific, not a universal interpreter launcher. The supported next
qualification lane explicitly starts both parent and child with this existing
real CPython image, selected by the coordinator before launch:

`C:/Users/zhy76/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`

SHA256 `5640e9be2fd33d05a1a9ae1228e2354609a69ab831605995ec4e2bd6da8fff5e`;
Python3.12.14. Keep existing dependencies read-only at
`D:/codex-tmp/kx23/venv/Lib/site-packages`, including pyocd0.45.1 and pytest8.4.2.
Child-only PYTHONPATH names same-tree Toolkit/Monitor/test sources followed by
that exact existing site directory. Isolate temp/cache/report roots. Clear only
child Python-home/venv-launcher context as declared by the coordinator; do not
alter global environment, permissions, credentials, packages or Claude settings.
Require actual sys.executable to equal the selected real image before tests.
There is no fallback lane and no silent launch via the old venv redirector.

Primary already completed two new non-test/non-hardware observations: direct
Popen PID23792 equals Python PID23792 (parent18856), exit0; a separate explicit
child-env/source-first import reports this actual executable, this review-tree
Toolkit source, pyocd0.45.1 from the existing site and an unacquired lazy driver.
No helper/Toolkit child operation, enumeration or USB was executed. These establish
feasibility only, not a passing helper matrix or hardware readiness. Records are
venv-launcher-observation.json, direct-runtime-observation.json and
direct-import-env-observation.json under D:/codex-tmp/st135.

The old venv lane remains26pass/14fail and unqualified. New lane results must all
be fresh; no old passes qualify the changed execution contract. The original
physical Session timeout is still unresolved and no1MHz gate is reintroduced.

## Bounded test-adapter implementation

Write only `tools/stm32-toolkit/tests/test_session_trace.py`. The helper and all
product runtime files remain byte-identical to the candidate; this phase changes
the execution/verification interface, not helper behavior.

- Scope the Popen spy with an explicit restoration boundary before backend
  import/acquisition, including an assertion that it has been restored. Keep
  default launcher/source/interpreter and lazy production-backend assertions.
  Test the actual removed SESSION_TRACE_PRIVATE_FAKE_* variable names, and clean
  their inheritance inside test-created processes. No fake mode is added back.
- Add the missing overall terminal-handle-close failure test after an otherwise
  successful inert child/result: use a small explicit Python-only owned-process
  test adapter; assert parent ok=false/nonzero and retained constructor facts.
  Close any actual proven-terminal test handle in finite test-owned cleanup.
  Do not merely repeat the utility-function test or close a live/unknown handle.
- Strengthen lease-release failure coverage so construction and Session close
  first succeed and cleanup is the sole failing phase. Prefer a fixed test-child
  fault adapter with the real temporary lease/health contract. Preserve failures
  and use only existing safe registry reclamation after proven child exit; no
  fake live owner/health success, forced takeover or altered liveness logic.
- Keep all existing40 functions/assertions and finite budgets; add only these
  proportional integration cases. Do not skip/soften failing cases, shorten away
  the surviving-child interval or substitute hand-written CLI exit paths.

One new edit invocation needs explicit bounded human authorization. A new once-
only benign same-file Edit context correction can be included only if approved;
the previous unused allowance expired. All genuine refusal/scope/other-error
boundaries remain. Writing and executing tests are separate tasks.

## Qualification and next boundary

After file-only edit, Primary freezes and reviews the complete new diff in a
clean exact-head checkout, including all fixed bootstrap paths. The stable
Claude dispatcher supplies native PowerShell inventory/smoke, then exact short
test commands using the selected real executable. An external coordinator-only
pytest runner may select the declared runtime/dependency paths and capture head,
source hashes, argv, actual exits and fresh JUnit; it is not another Claude
launcher or product dispatch automation. Preserve old runner/evidence hashes.

Run every original and added case fresh in this lane, with actual native stack,
real child PID/lease, normal and cancelled main exit, registry/handle cleanup and
overall negative outcomes. Primary independently checks the final risk cases.
No passing unit subset can replace those entry/lifetime gates. Record helper
bytes unchanged. If failures reveal another helper contract defect, return to
design; this phase does not grant a third local helper patch.

Only a qualified lane permits preparing a separately reviewed one-shot constructor
hardware card with actual identities and fresh user authorization. The full
three-item goal is not complete when this diagnostic's tests pass. No physical
state, IPSR/reset efficacy, ABI evidence or CCM reserve decision is invented.
