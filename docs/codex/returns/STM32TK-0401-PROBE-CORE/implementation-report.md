# STM32TK-0401-PROBE-CORE Implementation Report

## Delivery identity

- Status: `IMPLEMENTED`
- Accepted product base: `f2d0b0c875779a680cad86f02f9a58f8fd07e1a9`
- Plan commit: `e8e229ad3f1fbcf64b9101b950569f78f64de05b`
- Branch: `codex/STM32TK-0401-PROBE-CORE`
- Code head before this report commit:
  `8ad405ed12fa9c14f5b4e6c5400ff78cffc8d74b`
- Specification, implementation, and review owner: Codex, following the user's
  explicit pause of OpenClaw implementation after STM32TK-0306.
- Pull request: <https://github.com/XiaoyaoLinghao/stm32-toolkit/pull/8>

This report intentionally does not contain the final commit SHA that contains
the report itself.

## Delivered scope

The code head changes exactly 19 product and test paths relative to the plan
commit (4,308 insertions and 1 deletion):

- root and packaged byte-identical `probe-protocol.schema.json`;
- immutable protocol models, strict request decoder, deterministic response
  encoder, stable operation levels and bounded request contracts;
- portable global lease registry using a hashed evidence record plus an OS-held
  guard lock, exact process identity, authenticated loopback health evidence,
  heartbeat, conservative stale-owner recovery, forged-release protection, and
  Windows/POSIX lock implementations;
- narrow `ProbeBackend` protocol and a deterministic FakeProbe covering exact
  attach, reads, control/modify calls, disconnect/reconnect, partial failures,
  and blocked-operation shutdown;
- authenticated `127.0.0.1` dynamic-port aiohttp service and strict client with
  token/session/lease/version/operation checks, Host/Origin/content constraints,
  bounded request and response bodies, serialized backend dispatch, cancellation
  propagation, no late dispatch of queued timed-out operations, tracked backend
  completion, heartbeat-failure cleanup, and idempotent shutdown;
- read-only Doctor evidence for aiohttp/PyOCD availability and probe-registry
  path safety;
- focused protocol, lease, backend, service, client, Doctor, packaging, and
  Windows NTFS/cross-process regression tests;
- one runtime dependency: `aiohttp>=3.9,<4`. PyOCD and Monitor/UI dependencies
  remain outside this packet.

## TDD and review corrections

Initial RED collection failed because `stm32_toolkit.probe` did not exist. The
implementation proceeded through focused RED/GREEN slices. The final staged
review then reproduced and corrected these additional defects before the code
commit:

1. a junction in an ancestor of `data_root` allowed registry/session creation
   outside the lexical plugin-data root;
2. the endpoint loader accepted incompatible protocol and Toolkit versions;
3. heartbeat lease loss left a half-stopped service and live backend;
4. concurrent HTTP requests entered the same non-thread-safe backend;
5. a timed-out request waiting for the backend lock executed later;
6. a timed-out running backend exception reached the event loop as an
   unretrieved task error;
7. health URLs accepted userinfo and leaked raw invalid-port exceptions;
8. the default lease health checker never contacted the authenticated service;
9. response correlation and response body allocation were not strict/bounded;
10. Doctor did not classify an ancestor junction as unsafe;
11. incomplete request bodies had no independent receive deadline, and the
    initial single-read implementation did not prove whole-body receipt;
12. the final checklist lacked direct tests for truncated records, real crashed
    owners, missing credentials, Host attacks, protocol/session/lease skew, and
    rejection of non-loopback bind configuration.

Each correction was observed failing in a focused test before the product
change and was rerun GREEN. The complete focused and full suites were rerun
after the last product change.

## Verification evidence

Environment: Microsoft Windows 11 Pro 10.0.26200 build 26200, AMD64, CPython
3.12.13, pytest 8.3.5, jsonschema 4.23.0, aiohttp 3.14.3.

| Gate | Result |
|---|---|
| Focused protocol/lease/backend/service/client/Doctor suite | 141 passed, exit 0 |
| Full Toolkit suite | 1,323 passed, 3 skipped, 1,326 collected, exit 0 |
| Full branch coverage | 91%, required minimum 90% |
| New module coverage | backend 96%, client 81%, lease 80%, model 95%, protocol 86%, service 84% |
| `compileall` | exit 0 |
| accepted-base/code-head and staged `git diff --check` | exit 0 |
| root/packaged schema identity | byte-identical; SHA-256 `35EC85B314795AEF6102C0FCADEB1606F04F5D22FC42D9C16CAEF7AB437B271D` |
| forbidden process/shell/placeholder/credential scan on changed paths | no matches |
| Windows real cross-process lease contention | owner blocked; successor acquired after release |
| Windows real NTFS junction gate | `PROBE_REGISTRY_UNSAFE`; target remained unmodified |
| Cancellation/shutdown and queued-timeout gates | pass; no late dispatch or unretrieved task exception |
| Default authenticated health check | live exact lease accepted; wrong lease rejected |
| Fresh external wheel install | pass on CPython 3.12.13; protocol, aiohttp, and packaged schema loaded from outside the repository |

The final full command was:

`python -m pytest tools/stm32-toolkit/tests -q --cov=stm32_toolkit --cov-branch --cov-report=term`

It completed in 663.0 seconds. The three skips are pre-existing platform/fixture
skips; this packet added no skip or xfail.

## Deferred and non-claimed evidence

- The same real path/lock/cancellation suite on Linux is
  `DEFERRED_TO_STM32TK-0405-CLI-MCP-RELEASE`, where Windows and Linux are the
  named unified 0.4.0 release environments. POSIX code exists but is not
  mislabeled as a real Linux PASS from this Windows host.
- Real PyOCD/probe hardware is not claimed by STM32TK-0401. Exact PyOCD adapter
  and available real-probe smoke evidence belong to STM32TK-0402.
- No Monitor service or UI dependency, storage, or behavior was introduced.

## Known limitations

- Probe-module branch coverage below 90% is limited primarily to alternate
  POSIX and unavailable/error branches. The repository-wide branch gate is
  satisfied, and STM32TK-0402 through 0405 will exercise the real backend,
  supervision, flash, typed reads, CLI/MCP, and Linux release paths.
- Endpoint-file Windows ACL hardening and clean-profile installation remain part
  of the unified 0.4.0 packaging/security gate; this packet uses inherited
  user-data ACLs and explicit POSIX mode `0600` where supported.
