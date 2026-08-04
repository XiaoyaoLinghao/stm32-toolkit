# MODULE-ID ATTEMPT Implementation Report

Copy this file to `docs/openclaw/returns/{MODULE-ID}/{ATTEMPT}-implementation-report.md` and replace every instructional value before returning work.

Status: `IMPLEMENTED` or `BLOCKED`
Branch: `openclaw/{MODULE-ID}/{ATTEMPT}`
Accepted base commit: full 40-character SHA
Code head before report commit: full 40-character SHA
Final branch head: supplied only in the return message and PR metadata
PR/compare URL: GitHub URL
Work order: exact repository-relative path

## 1. Outcome

- Observable result: exact observed result
- Scope completed: complete item list
- Known limitations: `NONE` or an explicit list
- Deviations: `NONE` or an explicit list with reason

## 2. Complete changed-path inventory

| Status | Path | Work-order section | Purpose |
|---|---|---|---|
| A/M/D/R | exact repository-relative path | section number | purpose |

Reconcile this table with the accepted-base-to-code-head diff. Include this report path as the final report-only addition. Do not record a moving commit total.

## 3. Public contracts delivered

- Types/signatures: exact list
- Commands/events/configuration/schemas: exact list
- External interfaces: exact list or `NONE`

## 4. Environment-separated verification

| Gate/command | Evidence owner | Environment/tool versions | Commit tested | Exit | Observed result | Status |
|---|---|---|---|---:|---|---|
| exact command | OpenClaw/Codex/User | OS/runtime versions | full SHA | numeric exit | count/result | PASS/FAIL/DEFERRED/BLOCKED |

Do not report another actor’s command as OpenClaw evidence. A deferment must name the later owner and gate.

### Manual and visual evidence

| Gate | Owner | Observed result | Evidence path/status |
|---|---|---|---|
| exact step or viewport | named owner | result | repository-relative path or named deferment |

### Artifacts

| Artifact | Path | Size/checksum |
|---|---|---|
| exact name | repository-relative or external artifact path | value |

## 5. Security, privacy, performance, accessibility, and compatibility

- Security checks: commands and results
- Privacy/redaction checks: results
- Performance measurements: method, result, and budget
- Accessibility/input checks: results or `NOT_APPLICABLE` with reason
- Compatibility checks: targets and results

## 6. Blockers and residual risks

- Blockers: `NONE` or exact evidence
- Residual risks: `NONE` or explicit list
- Follow-up recommendation: `NONE` or an out-of-scope recommendation; do not implement it silently

## 7. Author checklist

- [ ] Accepted base and code head are full SHAs.
- [ ] Final head will be returned out of band after this report commit.
- [ ] Inventory matches the complete implementation diff and report addition.
- [ ] Every required OpenClaw gate has direct observed evidence.
- [ ] Other-environment gates are accurately attributed or deferred.
- [ ] No credentials, private data, caches, build output, or unredacted diagnostics are committed.
- [ ] No unrelated file, agent instruction, approved work order, or remote policy changed.
- [ ] Every instructional value in this report is replaced with actual evidence.
