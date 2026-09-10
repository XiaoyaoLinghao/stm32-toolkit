# T9 identity handoff software review

Status: **SOFTWARE_COMPLETE_HARDWARE_PENDING**. Independent reviewer verdict: **ACCEPTED_SOFTWARE**. Task 9 physical acceptance is not complete.

- Accepted slice base: `4b79ad97c51a3bc62f7c57c4637489ac9d5c6da1`.
- Reviewed CodeHead: `6b3b786bded32c78728e53b8732c7e8175c6863a`.
- Local integration code head before this report: `0dc205eb982b3594641bf8e519ddd21015693963`; product bytes and affected usage documentation match the reviewed head exactly.
- Design/integration/acceptance owner: primary conversation. Implementation/tests: the existing Luna/max T9 owner. Independent complete-diff reviewer: `acceptance_regression_ledger`; primary independently verified affected paths in a clean detached worktree.
- Branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`. No remote action or ownership exception.

Successful handoff now returns the exact attached probe's raw `boardId` and requested `targetId` for Cortex-Debug, without re-enumeration or widening ordinary attach evidence. A ticket-bound companion preserves the external configuration across worker shutdown. Its corruption cannot prevent a valid ticket from ending ownership. Static generation no longer advertises nonexistent handoff tasks; live IDE configuration belongs outside project inputs.

The private metadata request owns a five-second deadline including queue and IPC, followed only when needed by a separate bounded three-second cleanup. All unsuccessful exits after dispatch use one cleanup boundary. Proxy closure alone never proves child termination: unresolved execution keeps the lease, endpoint and supervisor reference unavailable for competing use. The original review findings are closed by the reviewed code; the two-round lifecycle reconsideration is recorded in the T9 plan.

## Evidence

- Implementer: affected worker, service, handoff, backend/PyOCD and supervisor checks passed at their recorded code heads. Unchanged checks were retained through the final service correction.
- Primary at `b083cc12`: seven targeted regression nodes passed, covering queue/IPC expiry, bounded cleanup and companion recovery.
- Primary at final `6b3b786b`: four targeted nodes passed, including a real child still alive behind a closed proxy, positive child-stop contrast, queue expiry and cancellation cleanup. A separate direct invocation of the existing supervisor/worker fixtures proved normal attach -> metadata -> stop without premature abort or retained ownership.
- Final evidence: `D:\codex-tmp\stm32tk-t9-identity-verification-6b3b786b-20260910\verification-summary.json`, `pytest.txt`, `normal-worker-check.json`.
- Interpreter: CPython 3.12.10 at the existing non-temporary system installation. The prescribed D runtime lacks pytest; its product dependencies were matched earlier. No installation or hardware test is inferred from these offline checks.
- Complete accepted-base-to-final-CodeHead diff was independently reviewed in a clean detached worktree. No remaining T9 software blocker was found.

Actual Cortex-Debug/PyOCD attach, normal IDE detach, Toolkit reacquisition/typed read, and CLI/MCP physical equivalence remain pending. T10 and VS10-A remain incomplete. Current deployed runtime is still source `a46310cbad431ed0f8c56d822db9054d426c4c14`; no candidate was deployed or hardware accessed in this review. P2, -12 100ms physical PASS and historical attempt 7 PASS are preserved.

The previously policy-blocked verification temporary directory remains preserved without retry. Final deployment and run-scoped cleanup are recorded by the combined T9/T10 delivery, not asserted complete here.
