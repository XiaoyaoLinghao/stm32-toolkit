# Finalization repeated-bind repair result

Status: ACCEPTED for this bounded product repair. Overall 1.0: NOT_ACCEPTED.
Accepted integration base: `6ea381515457bf4705682b0d812e8a6026e9354d`.
Tested candidate: `ec55b6dac95b5172c9fdda4f37c6a2a0b838da29`.
Integrated code head before this report: `b57ddbcbc6264fe023ae093d78d12ea749bfdd6c`.
Integrated product commit: `8a11caef14df16c5e56c0be2363d4ef5530110eb`.
Implementation: Luna/max public_recovery_impl. Design, complete-diff review,
integration and serial Windows test execution: primary. Independent focused
code/contract review: union20_review; final static verdict accepted.

A new UUID repeating a valid finalization bind previously reached an existing
proof while its temporary association still had envelope=None. Reading that
association's evidence ID raised AttributeError and was translated to an
evidence-integrity failure. The repair resolves the persisted proof root only
for the unbound association, then uses the existing proof reader. Authenticated
associations keep their evidence ID; identity/parent checks and D->E ordering
are preserved. No public schema or error code changed.

Primary regression: 7 PASS, 422.30 seconds, normal exit0. This includes the
complete repeated-bind journey, corrupt existing-root refusal with unchanged
clone/original bytes, persisted round trip, expired proof reuse, authority
rejection, competing proof identity and begin commit timestamp. Prior run1
continuation PASS remains retained without rerun; run1 finalization failure and
its entire raw database remain excluded from accepted native aggregation.

Evidence: r10/e/n95/public-recovery/run2 under the approved v10b-0918 root.
Raw SHA256: 67F84F0EC161D4E21FB82CEB07BAEAB1CED19420A2CD367E10F8772A0C83D2B7.
Independent final static review SHA256:
117A344DEF95A80603A0CE1055E4366680079882395A14A5B2DDBC4ABEDC24E7.
All 148 integration source files match the tested candidate after LF
normalization; raw checkout newline differences are recorded separately.

Coverage reconciliation is pending: union20 remains historical evidence for
runtime465. The changed recovery_workflows.py old arcs must be invalidated in
a copy before the next native union. The independent Diagnostic caller tests
are still being implemented. Mandatory package90, preferred core95, seven
Windows platform checks and final delivery gates are not claimed complete.
VS10-A/B and attempt7 physical evidence retain their existing scope. This
repair involved no hardware, deployment, packaging or remote action.
